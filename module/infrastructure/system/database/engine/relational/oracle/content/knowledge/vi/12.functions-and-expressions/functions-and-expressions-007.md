# TO_CHAR, TO_NUMBER, TO_DATE và TO_TIMESTAMP trong Oracle Database

## 1. Chuyển đổi kiểu dữ liệu: từ giá trị sang chuỗi và từ chuỗi về giá trị

Một ứng dụng nhận ngày dưới dạng text `2026-11-14`, một file CSV có giá `1.234,50`, hoặc API gửi thời điểm `2026-11-14T09:30:15.123456`. Oracle cần biết **kiểu dữ liệu thực sự** trước khi so sánh, tính toán hoặc lưu vào cột. Bốn hàm chuyển đổi thường dùng nhất là:

- **`TO_CHAR`**: chuyển `NUMBER`, `DATE`, `TIMESTAMP` hoặc một số kiểu dữ liệu khác thành `VARCHAR2` theo format model.
- **`TO_NUMBER`**: chuyển chuỗi ký tự thành `NUMBER`, có thể chỉ rõ dấu thập phân, phân nhóm và ký hiệu tiền tệ.
- **`TO_DATE`**: phân tích chuỗi thành kiểu `DATE`.
- **`TO_TIMESTAMP`**: phân tích chuỗi thành kiểu `TIMESTAMP`, có thể giữ phần giây lẻ.

Hãy phân biệt **chuyển kiểu dữ liệu** với **định dạng hiển thị**. Một ngày trong database không phải chuỗi `14-NOV-2026`; `DATE` là giá trị ngày giờ. `TO_CHAR` chỉ tạo ra chuỗi để hiển thị/gửi đi. Tương tự, số `1234.5` không phải chuỗi `1.234,50`; đó chỉ là một cách biểu diễn theo quy ước địa phương.

| Hàm | Hướng chuyển đổi | Kiểu trả về | Ví dụ |
| --- | --- | --- | --- |
| `TO_CHAR(number, fmt, nlsparam)` | NUMBER → text | `VARCHAR2` | `TO_CHAR(1234.5, 'FM9G999D00')` |
| `TO_CHAR(datetime, fmt, nlsparam)` | DATE/TIMESTAMP → text | `VARCHAR2` | `TO_CHAR(SYSDATE, 'YYYY-MM-DD')` |
| `TO_NUMBER(char, fmt, nlsparam)` | text → NUMBER | `NUMBER` | `TO_NUMBER('1.234,50', '9G999D99', ...)` |
| `TO_DATE(char, fmt, nlsparam)` | text → DATE | `DATE` | `TO_DATE('2026-11-14', 'YYYY-MM-DD')` |
| `TO_TIMESTAMP(char, fmt, nlsparam)` | text → TIMESTAMP | `TIMESTAMP` | `TO_TIMESTAMP('2026-11-14 09:30:15.123', ...)` |

> Nội dung tập trung vào cú pháp Oracle Database 19c. Format model và hành vi NLS cần đối chiếu với phiên bản database/driver thực tế. Các ví dụ tên bảng và dữ liệu là minh họa; lệnh DDL/DML chỉ chạy trong schema lab được phép.

## 2. Format model là gì?

Tham số format như `YYYY-MM-DD` hay `9G999D00` được gọi là **format model**. Nó mô tả cách Oracle đọc hoặc trình bày một giá trị, không thay đổi kiểu dữ liệu của cột.

~~~text
Giá trị NUMBER 1234.5
       │
       ├── TO_CHAR(..., 'FM9G999D00') ──► '1,234.50'
       │
       └── TO_CHAR(..., 'FM9990D000') ──► '1234.500'

Chuỗi '2026-11-14'
       │
       └── TO_DATE(..., 'YYYY-MM-DD') ──► một giá trị DATE
                                          không còn là chuỗi
~~~

Một format model có thể có các thành phần:

- **Format elements**: `YYYY`, `MM`, `DD`, `HH24`, `MI`, `SS`, `FF`, `9`, `0`, `G`, `D`...
- **Punctuation/literal**: dấu gạch ngang, dấu hai chấm, dấu chấm hoặc ký tự đặt trong dấu ngoặc kép.
- **Modifier**: `FM` (fill mode), `FX` (format exact), `TM` (text minimum) và một số modifier theo kiểu dữ liệu.
- **NLS parameter**: quy định cách diễn giải dấu thập phân, ký hiệu tiền tệ hoặc tên tháng/ngày theo ngôn ngữ.

Không dùng format model của NUMBER thay cho format model DATE/TIMESTAMP. Ví dụ `YYYY` có ý nghĩa năm trong datetime; `9` có ý nghĩa vị trí chữ số trong number format.

## 3. TO_CHAR với NUMBER: định dạng số thành chuỗi

### 3.1. Cú pháp và mục đích

~~~sql
TO_CHAR(number [, format_model [, nlsparam]])
~~~

Ví dụ:

~~~sql
SELECT TO_CHAR(1234.5, 'FM9G999D00') AS formatted_number
FROM   dual;
~~~

Kết quả phụ thuộc NLS của session. Nếu ký tự thập phân là dấu chấm và phân nhóm là dấu phẩy, kết quả là `1,234.50`. Trong môi trường khác, `D` và `G` có thể tạo ký tự khác.

**TO_CHAR trả về VARCHAR2**, vì vậy sau khi định dạng, kết quả không còn thích hợp để cộng/trừ như một giá trị NUMBER nếu không chuyển đổi trở lại. Hãy giữ dữ liệu số ở kiểu NUMBER trong database; chỉ định dạng tại ranh giới trình bày hoặc xuất dữ liệu.

### 3.2. Những format element số thường gặp

| Element | Ý nghĩa | Ví dụ format / cách hiểu |
| --- | --- | --- |
| `9` | Một vị trí chữ số; vị trí không cần thiết có thể là khoảng trắng | `9999` |
| `0` | Một vị trí chữ số; điền số 0 nếu không có chữ số | `0000` |
| `D` | Ký tự thập phân theo `NLS_NUMERIC_CHARACTERS` | `999D99` |
| `G` | Ký tự phân nhóm theo `NLS_NUMERIC_CHARACTERS` | `9G999G999` |
| `L` | Ký hiệu tiền tệ địa phương theo NLS | `L9G999D00` |
| `C` | Ký hiệu ISO currency theo territory | `C999D00` |
| `$` | Ký hiệu dollar | `$999D00` |
| `S` | Dấu âm/dương | `S9990` |
| `MI` | Dấu âm ở cuối (với số âm) | `9990MI` |
| `PR` | Số âm được đặt trong dấu ngoặc góc theo format model | `9990PR` |
| `EEEE` | Ký hiệu scientific notation | `9.99EEEE` |
| `V` | Nhân số với lũy thừa 10 để hiển thị, không dùng dấu thập phân trong model | `999V99` |
| `FM` | Bỏ blank padding ở đầu/cuối | `FM9990D00` |

Ví dụ `9` và `0`:

~~~sql
SELECT TO_CHAR(7, '999')     AS optional_digits,
       TO_CHAR(7, 'FM999')   AS no_padding,
       TO_CHAR(7, 'FM000')   AS zero_padded,
       TO_CHAR(7.5, 'FM990D00') AS fixed_decimals
FROM   dual;
~~~

Kết quả khái niệm:

| Format | Chuỗi |
| --- | --- |
| `999` | Có thể có khoảng trắng đệm trước `7` |
| `FM999` | `7` |
| `FM000` | `007` |
| `FM990D00` | `7.50` nếu NLS decimal là dấu chấm |

`FM` bỏ các blank padding mà format model tạo ra. Nó không phải lệnh “xóa mọi số 0 ở mọi vị trí”; dùng `0` hay `9` để quy định vị trí chữ số và kiểm tra output theo yêu cầu.

### 3.3. Ký tự thập phân và phân nhóm: D, G

`D` và `G` lấy ký tự từ `NLS_NUMERIC_CHARACTERS`. Cặp ký tự được quy định theo thứ tự **decimal character, group separator**.

Ví dụ muốn dùng dấu chấm thập phân và dấu phẩy phân nhóm một cách tường minh:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount_text
FROM dual;
~~~

Kết quả: `1,234.50`.

Muốn format kiểu dấu chấm phân nhóm và dấu phẩy thập phân:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_text
FROM dual;
~~~

Kết quả: `1.234,50`.

**Không nhầm format literal với NLS parameter:** `D` là placeholder cho dấu thập phân; `G` là placeholder cho dấu phân nhóm. Nếu muốn output cố định độc lập session, truyền NLS parameter rõ ràng hoặc dùng quy ước giao tiếp đã được xác định.

### 3.4. Tiền tệ: L, C, $

~~~sql
SELECT TO_CHAR(
         1250000,
         'FML9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'' NLS_CURRENCY = ''VND'''
       ) AS local_currency
FROM dual;
~~~

`L` dùng `NLS_CURRENCY`, còn `C` dựa trên ISO currency theo territory. Không nên gắn một format tiền tệ cố định cho mọi quốc gia hoặc mặc định ký hiệu tiền tệ tự nó mang đủ thông tin về **mã currency**. Với hệ thống đa tiền tệ, lưu số tiền và mã tiền tệ riêng (ví dụ `amount NUMBER`, `currency_code CHAR(3)`); format chỉ dùng cho presentation.

### 3.5. Làm tròn, độ rộng và dấu âm

Format model có thể làm tròn giá trị theo số vị trí thập phân được yêu cầu. Ví dụ:

~~~sql
SELECT TO_CHAR(12.3456, 'FM990D00',
               'NLS_NUMERIC_CHARACTERS = ''.,''') AS rounded_value
FROM dual;
~~~

Kết quả hiển thị hai chữ số thập phân, thường là `12.35`. **Đừng dùng TO_CHAR như cơ chế lưu giá trị đã làm tròn**; nếu nghiệp vụ cần làm tròn dữ liệu số, dùng `ROUND(number, scale)` và lưu NUMBER theo precision/scale đã thiết kế.

Nếu giá trị không vừa format model, Oracle có thể trả chuỗi dấu `#` thay cho số. Khi thấy `####`, hãy kiểm tra độ rộng format model thay vì giả định cột dữ liệu đã bị thay đổi.

### 3.6. Scientific notation và text minimum

~~~sql
SELECT TO_CHAR(1234567, '9.99EEEE') AS scientific_value
FROM dual;
~~~

`EEEE` cho cách hiển thị dạng lũy thừa 10. `TM` (Text Minimum) có quy tắc riêng để tạo biểu diễn số ngắn nhất phù hợp; không ghép tùy tiện `TM` với mọi element khác. Với output tài chính hoặc file có schema cố định, format rõ số chữ số thập phân thường dễ kiểm soát hơn.

## 4. TO_NUMBER: chuyển chuỗi thành NUMBER

### 4.1. Cú pháp

~~~sql
TO_NUMBER(char [, format_model [, nlsparam]])
~~~

Ví dụ chuỗi `1.234,50` có dấu chấm phân nhóm và dấu phẩy thập phân:

~~~sql
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_number
FROM dual;
~~~

Kết quả là NUMBER có giá trị `1234.5`, không còn là chuỗi. Từ đây có thể tính toán:

~~~sql
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) * 2 AS doubled_amount
FROM dual;
~~~

### 4.2. Khi nào cần format model?

Nếu chuỗi là biểu diễn số đơn giản theo quy ước NLS hiện tại, Oracle có thể chuyển bằng:

~~~sql
SELECT TO_NUMBER('1234.50') FROM dual;
~~~

Nhưng nếu dữ liệu đến từ file/ứng dụng dùng quy ước khác, không dựa vào session mặc định. Hãy chỉ rõ format và `NLS_NUMERIC_CHARACTERS`:

~~~sql
-- Decimal = comma, group = period.
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       )
FROM dual;

-- Decimal = period, group = comma.
SELECT TO_NUMBER(
         '1,234.50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
~~~

Một chuỗi `1,234` có thể có nghĩa **một nghìn hai trăm ba mươi tư** hoặc **một phẩy hai ba bốn**, tùy quy ước. Không thể xác định nghĩa chỉ từ chuỗi nếu nguồn không cung cấp locale/format contract.

### 4.3. Không dùng TO_NUMBER để che dữ liệu đầu vào bẩn

~~~sql
SELECT TO_NUMBER('12A5') FROM dual;
~~~

Giá trị không phải biểu diễn số hợp lệ theo format sẽ gây lỗi chuyển đổi, thường gặp `ORA-01722: invalid number`. Nếu dữ liệu đến từ CSV/legacy column, hãy:

1. Xác định format hợp lệ của nguồn (dấu thập phân, grouping, currency, dấu âm).
2. Phân loại row hợp lệ và row lỗi trước khi load.
3. Chuyển kiểu một cách tường minh, giữ lại raw value để audit khi cần.
4. Không mặc định thay chuỗi lỗi bằng 0, vì có thể biến dữ liệu sai thành một giá trị nghiệp vụ có vẻ hợp lệ.

Oracle 12.2 trở lên có `VALIDATE_CONVERSION` để kiểm tra khả năng chuyển đổi trong các trường hợp được hỗ trợ:

~~~sql
SELECT raw_amount,
       VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS can_convert
FROM   import_amounts;
~~~

`1` nghĩa là có thể chuyển đổi theo điều kiện đã đưa, `0` nghĩa là không; `NULL` input có thể trả kết quả hợp lệ theo semantics của hàm. Kiểm tra cú pháp và datatype chính xác theo release đang dùng. `VALIDATE_CONVERSION` không xác nhận giá trị **đúng nghiệp vụ**, chỉ xác nhận có thể parse.

### 4.4. Kiểu số không phải tiền tệ

Không nên chuyển một chuỗi có ký hiệu `$`, `€` hoặc `₫` bằng cách xóa ký tự theo phỏng đoán rồi `TO_NUMBER`. Hãy biết rõ format model và NLS currency, hoặc tách currency code khỏi numeric amount. Nếu số nguồn có dấu ngoặc cho số âm, ký hiệu phần trăm hoặc ký hiệu tiền tệ, format model phải phản ánh đúng cú pháp đó.

## 5. DATE, TIMESTAMP và chuỗi hiển thị là ba thứ khác nhau

Trước khi dùng `TO_DATE` và `TO_TIMESTAMP`, cần phân biệt kiểu dữ liệu:

| Kiểu | Lưu thông tin | Có timezone? | Độ chính xác thời gian |
| --- | --- | --- | --- |
| `DATE` | Năm, tháng, ngày, giờ, phút, giây | Không | Đến giây |
| `TIMESTAMP(p)` | Ngày giờ và giây lẻ | Không | `p` chữ số giây lẻ, mặc định 6, tối đa 9 |
| `TIMESTAMP WITH TIME ZONE` | Ngày giờ và thông tin timezone/offset hoặc region | Có | Giây lẻ theo precision |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Timestamp được chuẩn hóa theo timezone database; hiển thị theo session timezone | Không giữ timezone gốc như một giá trị riêng theo cách TSTZ | Giây lẻ theo precision |

`DATE` của Oracle **có cả phần thời gian** đến giây. Nó không chỉ là ngày như một số kiểu DATE ở hệ quản trị khác. Nếu insert `DATE '2026-11-14'`, thời gian là nửa đêm. Nếu so sánh với ngày chỉ có phần date, giá trị có giờ 14:00 sẽ không bằng giá trị midnight cùng ngày.

`TIMESTAMP` giữ được phần giây lẻ, nhưng **không chứa timezone**. Nếu nguồn có offset như `+07:00` hoặc region `Asia/Ho_Chi_Minh`, hãy chọn kiểu và hàm có timezone phù hợp, không bỏ thông tin một cách vô tình.

## 6. TO_DATE: chuyển chuỗi thành DATE

### 6.1. Cú pháp

~~~sql
TO_DATE(char [, format_model [, nlsparam]])
~~~

Ví dụ:

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS order_date
FROM dual;
~~~

Kết quả là một giá trị `DATE`. Format model giải thích cấu trúc của chuỗi nguồn; nó không quyết định cách client hiển thị giá trị sau khi chuyển đổi. SQL Developer/SQL*Plus có thể hiển thị khác nhau tùy `NLS_DATE_FORMAT`.

### 6.2. Format element ngày giờ thường gặp

| Element | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `YYYY` | Năm 4 chữ số | `2026` |
| `RRRR` | Năm 2 hoặc 4 chữ số với quy tắc tương thích RR | `26`, `2026` |
| `YY` | Hai chữ số năm, gắn với thế kỷ hiện tại | `26` |
| `RR` | Hai chữ số năm với quy tắc suy thế kỷ | `26` |
| `MM` | Tháng dạng số | `11` |
| `MON` | Tên tháng viết tắt | `NOV` |
| `MONTH` | Tên tháng đầy đủ | `NOVEMBER` |
| `DD` | Ngày trong tháng | `14` |
| `DDD` | Ngày thứ bao nhiêu trong năm | `318` |
| `DY`, `DAY` | Tên ngày trong tuần dạng ngắn/dài | `SAT`, `SATURDAY` |
| `HH24` | Giờ 00–23 | `17` |
| `HH` / `HH12` | Giờ 1–12 | `05` |
| `MI` | Phút | `30` |
| `SS` | Giây | `45` |
| `AM` / `PM` | Chỉ thị buổi sáng/chiều cho đồng hồ 12 giờ | `PM` |
| `IW` | Tuần ISO | `46` |
| `IYYY` | Năm ISO tương ứng tuần ISO | `2026` |

Ví dụ có thời gian:

~~~sql
SELECT TO_DATE(
         '2026-11-14 17:30:45',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS created_at
FROM dual;
~~~

`DATE` có phần giờ, phút, giây; nhưng **không có phần giây lẻ**. Không dùng `FF` để kỳ vọng lưu fractional seconds trong DATE. Nếu nguồn có `17:30:45.123456`, cần `TO_TIMESTAMP`.

### 6.3. Ngày có tên tháng: NLS date language

Chuỗi `14-NOV-2026` dùng tên tháng. Tên `NOV` được diễn giải theo ngôn ngữ ngày tháng của session, có thể khác nếu session sử dụng ngôn ngữ khác.

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS date_value
FROM dual;
~~~

Nếu nguồn gửi `14-NOV-2026` nhưng session đang dùng ngôn ngữ khác, chuyển đổi có thể thất bại nếu không đặt `NLS_DATE_LANGUAGE`. Với tích hợp, **chuỗi số ISO như `YYYY-MM-DD` thường ít phụ thuộc ngôn ngữ hơn**.

### 6.4. FX: yêu cầu khớp format chặt chẽ

Oracle có thể cho phép một số khác biệt về dấu phân cách hoặc độ rộng thành phần khi parse nếu không bật exact matching. Modifier **`FX`** yêu cầu khớp format model chặt hơn.

~~~sql
-- Cách parse linh hoạt theo format model (không bật FX).
SELECT TO_DATE('2026-3-8', 'YYYY-MM-DD')
FROM dual;

-- Exact matching: input phải theo hình thức model đã chỉ định.
SELECT TO_DATE('2026-03-08', 'FXYYYY-MM-DD')
FROM dual;
~~~

Với `FX`, chuỗi `2026-3-8` không đáp ứng độ rộng hai chữ số của tháng/ngày trong format chính xác. Khi dữ liệu từ hệ thống ngoài có contract cố định, `FX` giúp phát hiện input sai sớm thay vì chấp nhận nhiều biến thể không chủ ý. Punctuation và whitespace cũng phải phù hợp format exact.

### 6.5. YY, RR, YYYY, RRRR: tránh lỗi thế kỷ

**Không dùng năm hai chữ số cho dữ liệu mới nếu có thể tránh.** `YY` diễn giải theo thế kỷ hiện tại. `RR` được tạo để xử lý dữ liệu năm hai chữ số qua ranh giới thế kỷ, nhưng quy tắc phụ thuộc năm hiện tại.

Quy tắc pivot của `RR`:

| Hai chữ số của năm hiện tại | Input `00–49` | Input `50–99` |
| --- | --- | --- |
| Năm hiện tại kết thúc `00–49` | Cùng thế kỷ hiện tại | Thế kỷ trước |
| Năm hiện tại kết thúc `50–99` | Thế kỷ kế tiếp | Cùng thế kỷ hiện tại |

Ví dụ, với current year thuộc nhóm `00–49`, input `49` được suy trong thế kỷ hiện tại, còn `50` thuộc thế kỷ trước. Khi current year thuộc nhóm `50–99`, input `00` được suy trong thế kỷ kế tiếp. Cùng một chuỗi hai chữ số có thể được diễn giải khác ở các thời kỳ khác nhau.

- Dùng `YYYY` cho năm 4 chữ số đầy đủ.
- `RRRR` có thể nhận năm 2 hoặc 4 chữ số theo semantics RR.
- Chỉ giữ `RR` khi phải tương thích dữ liệu legacy hai chữ số đã có quy ước rõ.

### 6.6. Dùng ANSI date literal khi ngày là hằng số SQL

Khi ngày là hằng số trong câu SQL, có thể dùng literal không phụ thuộc `NLS_DATE_FORMAT`:

~~~sql
SELECT *
FROM   orders
WHERE  order_date >= DATE '2026-11-01'
AND    order_date <  DATE '2026-12-01';
~~~

`DATE 'YYYY-MM-DD'` là cú pháp literal SQL chuẩn của Oracle. Nó đại diện thời điểm midnight ở ngày đã nêu. Nếu cần thời gian, có thể dùng `TO_DATE` với format rõ ràng hoặc timestamp literal tương ứng.

### 6.7. TO_DATE chỉ trả DATE, không phải TIMESTAMP hoặc timestamp có timezone

Không dùng `TO_DATE` để parse phần giây lẻ hoặc timezone. `DATE` không có precision fractional và không có timezone. Với chuỗi `2026-11-14 17:30:45.123456`, hãy dùng `TO_TIMESTAMP`; nếu chuỗi có `+07:00`, hãy cân nhắc `TO_TIMESTAMP_TZ`.

## 7. TO_TIMESTAMP: chuyển chuỗi thành TIMESTAMP

### 7.1. Cú pháp

~~~sql
TO_TIMESTAMP(char [, format_model [, nlsparam]])
~~~

Ví dụ chuỗi có sáu chữ số giây lẻ:

~~~sql
SELECT TO_TIMESTAMP(
         '2026-11-14 17:30:45.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS event_timestamp
FROM dual;
~~~

Kết quả thuộc kiểu `TIMESTAMP(6)`. `FF` là format element của **fractional seconds**:

| Format | Ý nghĩa |
| --- | --- |
| `FF` | Giây lẻ; precision được suy từ input/model theo quy tắc hỗ trợ |
| `FF1` | Một chữ số giây lẻ |
| `FF3` | Ba chữ số (millisecond precision) |
| `FF6` | Sáu chữ số (microsecond precision) |
| `FF9` | Chín chữ số (nanosecond precision) |

Nếu datatype column là `TIMESTAMP(3)` nhưng nguồn có 9 chữ số, precision được lưu bị giới hạn bởi cột. Cần thiết kế precision nhất quán giữa source, bind variable, column và output format.

### 7.2. TO_TIMESTAMP không lưu timezone

Chuỗi:

~~~text
2026-11-14 17:30:45.123456
~~~

không nói thời điểm này thuộc UTC, Việt Nam hay múi giờ khác. `TO_TIMESTAMP` tạo `TIMESTAMP` **không timezone**. Nếu hệ thống cần xác định một thời điểm toàn cầu, hãy yêu cầu nguồn cung cấp offset hoặc region và sử dụng `TIMESTAMP WITH TIME ZONE` cùng `TO_TIMESTAMP_TZ`.

### 7.3. Ngày có tên tháng trong TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
         '14-NOV-2026 05:30:45.123 PM',
         'DD-MON-YYYY HH:MI:SS.FF3 PM',
         'NLS_DATE_LANGUAGE = American'
       )
FROM dual;
~~~

Khi format có `HH`/`HH12`, phải dùng chỉ thị `AM`/`PM` nếu nguồn biểu diễn giờ 12 giờ. Nếu dùng `HH24`, không ghép thêm AM/PM như thể đó là cùng một quy ước.

## 8. Timestamp có timezone: TO_TIMESTAMP_TZ

`TO_TIMESTAMP` không phải hàm phù hợp cho chuỗi chứa timezone. Oracle cung cấp **`TO_TIMESTAMP_TZ`** để chuyển thành `TIMESTAMP WITH TIME ZONE`.

### 8.1. Chuỗi có UTC offset

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 17:30:45.123456 +07:00',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS event_time_tz
FROM dual;
~~~

`TZH:TZM` biểu diễn giờ và phút lệch so với UTC. `+07:00` xác định offset tại giá trị được gửi. Nếu dữ liệu là thời điểm Việt Nam và source đã cam kết offset `+07:00`, có thể parse rõ ràng như ví dụ.

### 8.2. Chuỗi có time zone region

Oracle hỗ trợ region format element `TZR` và daylight abbreviation `TZD`:

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 17:30:45 Asia/Ho_Chi_Minh',
         'YYYY-MM-DD HH24:MI:SS TZR'
       ) AS event_time_tz
FROM dual;
~~~

Region giúp thể hiện quy tắc múi giờ của khu vực qua thời gian, thay vì chỉ một offset. Với vùng có daylight saving time, một local wall-clock time có thể mơ hồ hoặc không tồn tại khi đồng hồ chuyển đổi. Khi nguồn có cả region và abbreviation, format có thể dùng `TZR TZD`; dữ liệu cần đúng quy tắc timezone file của Oracle.

### 8.3. Phân biệt ba kiểu timestamp

| Kiểu | Ý nghĩa lưu trữ | Khi hiển thị |
| --- | --- | --- |
| `TIMESTAMP` | Ngày giờ và fractional seconds, không gắn múi giờ | Không tự chuyển theo session timezone |
| `TIMESTAMP WITH TIME ZONE` | Ngày giờ kèm offset/region | Có thông tin timezone của giá trị |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Chuẩn hóa theo timezone database; không giữ timezone gốc như một giá trị riêng | Oracle chuyển sang session time zone khi lấy ra/hiển thị |

Ví dụ `TO_CHAR` một `TIMESTAMP WITH LOCAL TIME ZONE` có thể cho output khác khi hai session đặt `TIME_ZONE` khác nhau. Đây là đặc tính hiển thị, không nhất thiết dữ liệu đã bị thay đổi.

## 9. TO_CHAR với DATE/TIMESTAMP: tạo chuỗi hiển thị

### 9.1. Format datetime cơ bản

~~~sql
SELECT TO_CHAR(
         SYSDATE,
         'YYYY-MM-DD HH24:MI:SS'
       ) AS current_date_text
FROM dual;
~~~

`SYSDATE` trả `DATE` theo đồng hồ hệ điều hành của database server. Kết quả là chuỗi theo format model, không phải `DATE`. Với timestamp:

~~~sql
SELECT TO_CHAR(
         SYSTIMESTAMP,
         'YYYY-MM-DD"T"HH24:MI:SS.FF3 TZH:TZM'
       ) AS current_timestamp_text
FROM dual;
~~~

`"T"` là literal chữ T được đặt trong format model, hữu ích khi tạo chuỗi gần ISO 8601. `SYSTIMESTAMP` trả timestamp kèm timezone/offset của môi trường server.

### 9.2. Tên tháng/ngày phụ thuộc ngôn ngữ

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS english_date
FROM dual;
~~~

Nếu bỏ `NLS_DATE_LANGUAGE`, tên `MON`, `MONTH`, `DY`, `DAY` có thể thay đổi theo session. Đối với file tích hợp hoặc API, format số ISO như `YYYY-MM-DD` thường dễ kiểm soát hơn.

### 9.3. FM loại bỏ khoảng trắng đệm

Format model `DAY` và `MONTH` có thể pad tên ngày/tháng bằng khoảng trắng đến độ dài chuẩn:

~~~sql
SELECT '[' || TO_CHAR(DATE '2026-11-14', 'DAY',
                      'NLS_DATE_LANGUAGE = American') || ']' AS padded_day,
       '[' || TO_CHAR(DATE '2026-11-14', 'FMDAY',
                      'NLS_DATE_LANGUAGE = American') || ']' AS fill_mode_day
FROM dual;
~~~

`FM` bật fill mode, bỏ blank padding. Nó có thể tác động đến cách format các phần tiếp theo trong model; khi cần bật/tắt theo đoạn, Oracle hỗ trợ các lần xuất hiện `FM` tương ứng. Hãy test output thật, nhất là khi tạo fixed-width file.

### 9.4. Tuần ISO và ngày trong tuần

`D` là số ngày trong tuần theo `NLS_TERRITORY`, nên không giả định Sunday luôn là 1 ở mọi môi trường. `IW` và `IYYY` là tuần ISO và năm ISO; **dùng cùng nhau** để tránh nhầm năm lịch với năm tuần ISO:

~~~sql
SELECT TO_CHAR(DATE '2026-01-01', 'YYYY-MM-DD') AS calendar_date,
       TO_CHAR(DATE '2026-01-01', 'IYYY-IW') AS iso_week
FROM dual;
~~~

Một số ngày đầu tháng 1 có thể thuộc tuần ISO cuối của năm trước, và ngược lại. Nếu báo cáo theo tuần ISO, không ghép `YYYY` với `IW` vì đó là hai hệ quy chiếu khác nhau.

## 10. NLS: nguồn gốc của nhiều lỗi chuyển đổi khó tái hiện

**NLS (National Language Support)** điều khiển cách Oracle diễn giải/hiển thị nhiều thành phần phụ thuộc ngôn ngữ và territory.

| NLS parameter | Ảnh hưởng |
| --- | --- |
| `NLS_DATE_FORMAT` | Format mặc định khi chuyển đổi DATE ↔ character trong nhiều ngữ cảnh |
| `NLS_TIMESTAMP_FORMAT` | Format mặc định cho TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Format mặc định cho TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Tên tháng/ngày và một số văn bản datetime |
| `NLS_NUMERIC_CHARACTERS` | Dấu thập phân và phân nhóm |
| `NLS_CURRENCY` | Ký hiệu tiền tệ địa phương |
| `NLS_ISO_CURRENCY` | Ký hiệu ISO currency theo territory |
| `NLS_TERRITORY` | Một số quy ước ngày, tuần, tiền tệ và định dạng |

Kiểm tra NLS của session hiện tại:

~~~sql
SELECT parameter, value
FROM   nls_session_parameters
WHERE  parameter IN (
         'NLS_DATE_FORMAT',
         'NLS_TIMESTAMP_FORMAT',
         'NLS_TIMESTAMP_TZ_FORMAT',
         'NLS_DATE_LANGUAGE',
         'NLS_NUMERIC_CHARACTERS',
         'NLS_CURRENCY',
         'NLS_TERRITORY'
       )
ORDER BY parameter;
~~~

Các giá trị cấu hình database/instance/session có thể khác nhau. Driver và client cũng có thể thiết lập NLS session khi kết nối. Vì thế cùng một SQL dùng conversion ngầm có thể chạy trên máy developer nhưng lỗi ở application server.

### 10.1. Thay NLS session để quan sát

Trong một session lab:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-YYYY';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT SYSDATE,
       TO_CHAR(1234.5, '9G999D00')
FROM dual;
~~~

`ALTER SESSION` chỉ tác động session hiện tại. Trong connection pool, session có thể được tái sử dụng; không để ứng dụng dựa vào trạng thái NLS ngẫu nhiên do một request trước đó thay đổi. Reset hoặc cấu hình session một cách có kiểm soát.

### 10.2. Truyền NLS parameter ngay trong hàm

Thay vì phụ thuộc session:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       )
FROM dual;

SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       )
FROM dual;
~~~

Cách này giúp conversion thể hiện **contract của dữ liệu nguồn** ngay tại chỗ. Với format số/ngày cố định trong file, luôn mô tả rõ format và locale thay vì dùng session default.

## 11. Implicit conversion: Oracle tự chuyển kiểu nhưng không nên dựa vào nó

Oracle có thể tự chuyển đổi kiểu dữ liệu khi so sánh, nối chuỗi hoặc thực hiện biểu thức. Điều này tiện trong câu lệnh ngắn, nhưng có thể tạo phụ thuộc NLS, lỗi runtime và ảnh hưởng index.

### 11.1. So sánh DATE với chuỗi

~~~sql
-- Không nên: chuỗi phụ thuộc NLS_DATE_FORMAT của session.
SELECT *
FROM   orders
WHERE  order_date = '14-NOV-2026';
~~~

Oracle phải chuyển chuỗi sang DATE theo quy tắc mặc định. Nếu session dùng format khác, câu lệnh có thể lỗi `ORA-01861`, `ORA-01843` hoặc cho kết quả khác ý định.

Viết tường minh:

~~~sql
SELECT *
FROM   orders
WHERE  order_date = TO_DATE('14-NOV-2026',
                            'DD-MON-YYYY',
                            'NLS_DATE_LANGUAGE = American');
~~~

Hoặc với hằng ngày ISO:

~~~sql
SELECT *
FROM   orders
WHERE  order_date >= DATE '2026-11-14'
AND    order_date <  DATE '2026-11-15';
~~~

### 11.2. So sánh NUMBER với chuỗi

~~~sql
-- Không nên dựa vào conversion ngầm:
SELECT *
FROM   invoice_lines
WHERE  amount = '1,234.50';
~~~

Chuỗi có dấu phân nhóm có thể không được parse như dự kiến theo `NLS_NUMERIC_CHARACTERS`. Tốt hơn là bind NUMBER từ ứng dụng hoặc parse chuỗi theo format rõ:

~~~sql
WHERE amount = TO_NUMBER(
  '1,234.50',
  '9G999D99',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
)
~~~

### 11.3. TO_CHAR trong nối chuỗi

Khi nối DATE/NUMBER vào chuỗi, Oracle có thể tự chuyển sang text bằng format mặc định:

~~~sql
-- Kết quả text phụ thuộc NLS session:
SELECT 'Created at ' || created_at
FROM orders;
~~~

Đối với log/API/export, hãy quy định format:

~~~sql
SELECT 'Created at ' ||
       TO_CHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
FROM orders;
~~~

### 11.4. Tránh chuyển đổi ngầm trên cột được index

Giả sử `orders.order_date` là DATE và có index thường. Câu:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-11-14'
~~~

đưa hàm lên **cột**. Oracle có thể không sử dụng index thông thường trên `order_date` theo cách mong muốn, trừ khi có function-based index phù hợp và optimizer chọn nó.

Viết khoảng ngày:

~~~sql
WHERE order_date >= DATE '2026-11-14'
AND   order_date <  DATE '2026-11-15'
~~~

Điều kiện range giữ cột ở dạng gốc và thường thân thiện với index range scan hơn. Nếu yêu cầu thật sự cần biểu thức `TRUNC(order_date)`/`TO_CHAR(order_date,...)`, đánh giá function-based index, statistics và execution plan.

**Nguyên tắc:** chuyển đổi **bind/input một lần** sang datatype của cột, tránh bọc cột trong hàm ở predicate nếu không cần thiết.

## 12. So sánh ngày có phần giờ: dùng range thay vì bằng ngày

Giả sử `created_at` là DATE và dữ liệu có cả giờ:

| Giá trị | Có thuộc ngày 14/11/2026? |
| --- | --- |
| `2026-11-14 00:00:00` | Có |
| `2026-11-14 09:15:00` | Có |
| `2026-11-14 23:59:59` | Có |
| `2026-11-15 00:00:00` | Không |

Điều kiện:

~~~sql
-- Chỉ bằng midnight; thường bỏ sót row trong ngày có giờ khác 00:00.
WHERE created_at = DATE '2026-11-14'
~~~

khác:

~~~sql
-- Toàn bộ ngày 14/11/2026, không cần đoán 23:59:59.
WHERE created_at >= DATE '2026-11-14'
AND   created_at <  DATE '2026-11-15'
~~~

Đối với TIMESTAMP, nguyên tắc range tương tự:

~~~sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
AND   event_time <  TIMESTAMP '2026-11-15 00:00:00'
~~~

Không tạo “cuối ngày” bằng `23:59:59.999999` vì precision của cột có thể khác, và timestamp có thể giữ nhiều chữ số giây lẻ hơn. Khoảng **đầu ngày inclusive, đầu ngày kế tiếp exclusive** là cách rõ ràng hơn.

## 13. TO_CHAR và TO_DATE không phải hai chiều nghịch đảo hoàn hảo

Một số chuyển đổi có thể mất thông tin:

- `DATE` → `TO_CHAR(..., 'YYYY-MM-DD')` → `TO_DATE(...)`: **mất phần giờ** vì format chỉ có ngày.
- `TIMESTAMP(6)` → format `...FF3` → `TO_TIMESTAMP(...)`: mất các chữ số giây lẻ ngoài ba chữ số.
- `TIMESTAMP WITH TIME ZONE` → chuỗi chỉ gồm `YYYY-MM-DD HH24:MI:SS` → `TO_TIMESTAMP`: mất timezone/offset.
- NUMBER → `TO_CHAR` với hai decimal places → `TO_NUMBER`: có thể mất độ chính xác do format đã làm tròn.

Ví dụ:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14', 'YYYY-MM-DD'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS output
FROM dual;
~~~

Kết quả thời gian là `00:00:00`, vì chuỗi nguồn chỉ chứa ngày. Không có cách nào khôi phục giờ ban đầu nếu giờ đã không được truyền vào.

Nếu cần round-trip dữ liệu, phải chọn format có đủ thông tin và kiểu đích có đủ khả năng lưu. Với timestamp có timezone, format/parse phải giữ cả offset hoặc region theo hợp đồng.

## 14. Format ISO cho tích hợp và API

Đối với trao đổi giữa các hệ thống, ưu tiên format không phụ thuộc ngôn ngữ:

| Loại | Biểu diễn thường dùng | Hàm/cách xử lý |
| --- | --- | --- |
| Date | `2026-11-14` | `TO_DATE(text, 'YYYY-MM-DD')` hoặc ANSI `DATE` literal |
| Local timestamp | `2026-11-14T09:30:15.123456` | `TO_TIMESTAMP(text, 'YYYY-MM-DD"T"HH24:MI:SS.FF6')` |
| Timestamp có offset | `2026-11-14T09:30:15.123456+07:00` | `TO_TIMESTAMP_TZ(..., 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')` |
| Number machine format | `1234.50` | Bind NUMBER hoặc `TO_NUMBER(..., explicit NLS)` |

Format ISO cần được quy định chính xác: có timezone hay không, số chữ số giây lẻ, offset có dấu hai chấm hay không, có dùng `Z` cho UTC không. Nếu source gửi `Z`, format model và cách parse cần tương ứng; không tự coi `Z` là `+00:00` trong mọi format.

### 14.1. JDBC: bind theo datatype thay vì ghép chuỗi

Với Java/JDBC, ưu tiên bind giá trị đã có kiểu:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "SELECT order_id, created_at FROM orders WHERE created_at >= ?"
);
ps.setTimestamp(1, timestampValue);
~~~

Nếu cột là DATE, driver/JDBC mapping và lựa chọn `setDate`/`setTimestamp` cần thống nhất với phần thời gian mà ứng dụng muốn giữ. Với `TIMESTAMP WITH TIME ZONE`, xem API Oracle JDBC/Java time tương ứng và driver version; đừng ép qua `String` nếu không cần.

Bind variables giúp:

- Không phụ thuộc NLS khi truyền giá trị đúng datatype.
- Tránh lỗi format và giảm nguy cơ SQL injection do nối chuỗi.
- Hỗ trợ statement reuse và cursor sharing.
- Giữ semantics rõ giữa NUMBER, DATE, TIMESTAMP và VARCHAR2.

Nếu dữ liệu đầu vào vẫn là text, parse/validate ở tầng có hợp đồng format rõ ràng, hoặc dùng conversion tường minh trong SQL; không nối input trực tiếp vào câu SQL.

## 15. Các lỗi ORA thường gặp khi chuyển đổi

| Lỗi | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| `ORA-01722: invalid number` | Chuỗi không parse được thành NUMBER theo format/NLS | Kiểm tra raw value, `NLS_NUMERIC_CHARACTERS`, format model, ký tự lạ |
| `ORA-01481: invalid number format model` | Number format model không hợp lệ | Kiểm tra element `9`, `0`, `D`, `G`, modifier và vị trí |
| `ORA-01830: date format picture ends before converting entire input string` | Format kết thúc trước khi parse hết input | Bổ sung thành phần giờ/giây lẻ hoặc sửa input |
| `ORA-01843: not a valid month` | Tên/tháng không khớp format hoặc NLS language | Kiểm tra `MON`/`MONTH`, `MM`, `NLS_DATE_LANGUAGE` |
| `ORA-01847: day of month must be between 1 and last day of month` | Ngày không tồn tại trong tháng | Kiểm tra dữ liệu như 31/02 |
| `ORA-01858: a non-numeric character was found where a numeric was expected` | Ký tự input không khớp vị trí format số | So input và format element |
| `ORA-01861: literal does not match format string` | Chuỗi không khớp format, thường do dấu phân cách/độ rộng | Dùng format rõ, xem `FX`, đối chiếu input |
| `ORA-01862: the numeric value does not match the length of the format item` | Độ dài thành phần số không phù hợp format exact | Kiểm tra `FX` và số chữ số |
| `ORA-01821: date format not recognized` | Datetime format model không được nhận diện | Kiểm tra token/format có được hỗ trợ cho datatype |

Mã lỗi cụ thể có thể phụ thuộc biểu thức và release. Khi debug:

1. Lấy **raw string** thực tế, giữ nguyên dấu cách/ký tự Unicode.
2. Ghi nhận NLS session của đúng connection bị lỗi.
3. Ghi lại datatype cột và datatype bind variable.
4. Thử conversion độc lập trên đúng input/format/NLS.
5. Không “sửa” dữ liệu bằng cách thay mọi ký tự không phải số thành rỗng; cách đó có thể biến `1.234,50` thành một giá trị sai.

### 15.1. Tên tháng và ký tự Unicode

Tên tháng/ngày có dấu hoặc ký tự ngoài ASCII còn phụ thuộc character set, NLS language và nguồn file. Một chuỗi `Tháng Mười Một` không thể mặc nhiên parse bằng `MON` hoặc `MONTH` tiếng Anh. Tốt nhất hệ thống tích hợp gửi **thành phần số** hoặc chuẩn hóa tên tháng với ngôn ngữ được công bố.

### 15.2. Input có khoảng trắng

Đừng mặc định `TRIM` là bước vô hại: khoảng trắng có thể có ý nghĩa trong format fixed-width, ký hiệu tiền tệ hoặc chuỗi. Nếu nguồn quy định padding, trim đúng phía/đúng ký tự theo contract trước khi parse. Khi bật `FX`, whitespace phải tuân thủ format exact.

## 16. Bài thực hành: NUMBER và NLS

> Các câu lệnh SELECT chỉ đọc. Không cần tạo bảng để học conversion. Có thể chạy trong SQL*Plus, SQLcl hoặc SQL Developer.

### Bài A — Định dạng số với hai locale

~~~sql
SELECT TO_CHAR(
         1234567.89,
         'FM9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS us_style,
       TO_CHAR(
         1234567.89,
         'FM9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS comma_decimal
FROM dual;
~~~

Kết quả dự kiến:

| US-style | Decimal comma |
| --- | --- |
| `1,234,567.89` | `1.234.567,89` |

### Bài B — Parse cùng một số theo đúng quy ước

~~~sql
SELECT TO_NUMBER(
         '1.234.567,89',
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS parsed_amount
FROM dual;
~~~

Kết quả NUMBER là `1234567.89`. Thử đổi NLS parameter sang `''.,''` nhưng giữ nguyên chuỗi input và quan sát lỗi/ý nghĩa khác; sau đó giải thích tại sao không thể suy ra locale chỉ từ dấu phẩy/dấu chấm.

### Bài C — Số có padding

~~~sql
SELECT '[' || TO_CHAR(7, '999') || ']' AS padded,
       '[' || TO_CHAR(7, 'FM999') || ']' AS fill_mode,
       '[' || TO_CHAR(7, 'FM000') || ']' AS zero_fill
FROM dual;
~~~

Giải thích khác biệt giữa khoảng trắng do format, số 0 bắt buộc và giá trị NUMBER gốc.

## 17. Bài thực hành: DATE và TIMESTAMP

### Bài D — Parse DATE độc lập NLS

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS d
FROM dual;
~~~

Sau đó:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 17:30:45',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS formatted_d
FROM dual;
~~~

Kết quả vẫn chứa phần giờ `17:30:45`, vì Oracle DATE lưu đến giây.

### Bài E — Parse TIMESTAMP có giây lẻ

~~~sql
SELECT TO_CHAR(
         TO_TIMESTAMP(
           '2026-11-14 17:30:45.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
         ),
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS timestamp_text
FROM dual;
~~~

Thử thay `FF6` bằng `FF3`, rồi quan sát việc format chỉ hiển thị ba chữ số giây lẻ.

### Bài F — Timestamp có timezone

~~~sql
SELECT TO_CHAR(
         TO_TIMESTAMP_TZ(
           '2026-11-14 17:30:45.123456 +07:00',
           'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
         ),
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS timestamp_with_tz
FROM dual;
~~~

Giải thích tại sao thay bằng `TO_TIMESTAMP` sẽ không bảo toàn offset timezone như một thuộc tính của giá trị.

### Bài G — NLS language cho tên tháng

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS month_english
FROM dual;
~~~

Thử đổi ngôn ngữ sang một giá trị được Oracle hỗ trợ trong môi trường, so sánh output; không dùng kết quả hiển thị để suy ra datatype.

### Bài H — Khoảng ngày đầy đủ

~~~sql
SELECT *
FROM   orders
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-15';
~~~

Đây là ví dụ cho bảng thật `ORDERS`; thay tên cột/table nếu khác. Trả lời vì sao `created_at = DATE '2026-11-14'` có thể bỏ sót row được tạo lúc 09:30 cùng ngày.

## 18. Quy trình xử lý dữ liệu import

Giả sử file CSV có:

~~~text
order_id,amount,order_date
1001,"1.234,50","14-11-2026"
1002,"250,00","15-11-2026"
1003,"invalid","31-02-2026"
~~~

Đừng load trực tiếp text vào cột NUMBER/DATE với conversion ngầm. Một workflow an toàn:

1. Load raw values vào **staging columns kiểu VARCHAR2**.
2. Xác định format nguồn: decimal comma/group period, date `DD-MM-YYYY`.
3. Dùng `VALIDATE_CONVERSION` nếu version hỗ trợ để phân loại parseable/unparseable.
4. Lưu lỗi theo row/source file và giữ raw value để sửa.
5. Chuyển các row hợp lệ bằng `TO_NUMBER`/`TO_DATE` với format/NLS rõ ràng.
6. Đưa dữ liệu vào bảng đích có datatype và constraints phù hợp.
7. Báo cáo số row load thành công, số row reject, lý do reject.

Ví dụ kiểm tra staging:

~~~sql
SELECT order_id,
       raw_amount,
       VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_ok,
       raw_order_date,
       VALIDATE_CONVERSION(
         raw_order_date AS DATE,
         'DD-MM-YYYY'
       ) AS date_ok
FROM   order_import_stage;
~~~

Sau khi xác nhận hợp lệ, conversion:

~~~sql
SELECT order_id,
       TO_NUMBER(
         raw_amount,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount,
       TO_DATE(raw_order_date, 'DD-MM-YYYY') AS order_date
FROM   order_import_stage
WHERE  VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) = 1
AND    VALIDATE_CONVERSION(
         raw_order_date AS DATE,
         'DD-MM-YYYY'
       ) = 1;
~~~

Đây là ví dụ đọc và chuyển dữ liệu, không phải script insert hoàn chỉnh. Khi triển khai, cần xử lý `NULL`, duplicate keys, lỗi nghiệp vụ, transaction batch, logging và các thay đổi giữa lúc validate và insert. Với file lớn, Data Pump/SQL*Loader/external table có các cơ chế phù hợp hơn; staging giúp kiểm soát dữ liệu trước khi đưa vào schema nghiệp vụ.

## 19. Những lỗi thiết kế nên tránh

1. **Lưu ngày dưới dạng VARCHAR2** dù luôn có định dạng ngày cố định. Việc này làm so sánh/sort ngày theo text dễ sai và mất date arithmetic.
2. **Lưu số tiền dưới dạng chuỗi** để giữ dấu phân nhóm. Hãy lưu NUMBER và format khi hiển thị.
3. **Dùng `TO_DATE(date_column, ...)`**. Đầu vào đã là DATE; hàm này có thể gây implicit conversion DATE → text → DATE và mất phần giờ/đổi giá trị theo NLS.
4. **Bỏ format model** khi parse chuỗi ngày/giờ từ API/file.
5. **Dùng YY/RR cho năm mới** khi source có thể gửi đủ bốn chữ số.
6. **Dùng TO_DATE để parse fractional seconds** hoặc offset timezone.
7. **Dùng TO_TIMESTAMP cho input có timezone** rồi bỏ mất offset/region.
8. **Dùng TO_CHAR trên cột trong WHERE** mà không xem xét index/function-based index.
9. **Dựa vào NLS session ngầm** trong connection pool hoặc môi trường nhiều client.
10. **Thay giá trị không parse được bằng 0/01-01-1900** mà không có quy tắc nghiệp vụ và audit.
11. **Format số tiền mà bỏ currency code** trong hệ thống đa tiền tệ.
12. **Dùng BETWEEN với cuối ngày 23:59:59** trong cột TIMESTAMP có giây lẻ; ưu tiên khoảng nửa mở.

## 20. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — TO_CHAR (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_CHAR-number.html): cú pháp, number format model, NLS và kết quả VARCHAR2.
2. [Oracle Database 19c SQL Language Reference — TO_CHAR (datetime)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_CHAR-datetime.html): datetime format model, timestamp/time zone và NLS date language.
3. [Oracle Database 19c SQL Language Reference — TO_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_NUMBER.html): chuyển character sang NUMBER, format model và NLS.
4. [Oracle Database 19c SQL Language Reference — TO_DATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_DATE.html): chuyển chuỗi thành DATE, format, NLS và lưu ý không truyền DATE vào TO_DATE.
5. [Oracle Database 19c SQL Language Reference — TO_TIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_TIMESTAMP.html): chuyển chuỗi thành TIMESTAMP, fractional seconds và NLS.
6. [Oracle Database 19c SQL Language Reference — TO_TIMESTAMP_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_TIMESTAMP_TZ.html): parse timestamp có timezone.
7. [Oracle Database 19c SQL Language Reference — Format Models](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Format-Models.html): number/datetime format elements, `FX`, `FM`, `RR`, `FF`, `TZR`, `TZH`, `TZM`.
8. [Oracle Database 19c SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): implicit conversion và quy tắc so sánh datatype.
9. [Oracle Database 19c SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): kiểm tra khả năng chuyển đổi, dùng cho phân loại dữ liệu staging ở release hỗ trợ.
10. [Oracle Database 19c Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): NLS session, territory, language, numeric/date format và tích hợp đa ngôn ngữ.
11. [Oracle Database 19c JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): binding DATE/TIMESTAMP và chuyển đổi kiểu giữa Java/JDBC với Oracle.

**Nguyên tắc cần nhớ:** Dùng `TO_CHAR` để **trình bày**, `TO_NUMBER` để **parse số**, `TO_DATE` để **parse DATE**, `TO_TIMESTAMP` để **parse timestamp có giây lẻ**; nếu có timezone hãy chọn `TO_TIMESTAMP_TZ`. Luôn chỉ rõ format/NLS cho dữ liệu text, ưu tiên bind variables có datatype thật, và giữ cột ở kiểu dữ liệu gốc trong điều kiện lọc để tránh lỗi NLS và vấn đề hiệu năng.
