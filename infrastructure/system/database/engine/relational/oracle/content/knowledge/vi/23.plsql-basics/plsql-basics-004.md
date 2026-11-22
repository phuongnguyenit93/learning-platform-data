# Kiểu số, chuỗi, ngày giờ và BOOLEAN trong PL/SQL

PL/SQL là ngôn ngữ thủ tục của Oracle Database. Một chương trình PL/SQL khai báo biến, hằng, tham số và record bằng hệ thống kiểu dữ liệu có liên hệ chặt chẽ với kiểu dữ liệu SQL. Chọn đúng kiểu giúp phép tính chính xác, tránh chuyển đổi ngầm, kiểm soát NULL và làm cho chương trình dễ bảo trì.

Bốn nhóm cần nắm vững trong PL/SQL cơ bản là:

- **Kiểu số:** NUMBER, PLS_INTEGER, BINARY_FLOAT và BINARY_DOUBLE.
- **Kiểu chuỗi:** CHAR, VARCHAR2, NCHAR, NVARCHAR2 và các kiểu LOB.
- **Kiểu ngày giờ:** DATE, TIMESTAMP, các kiểu có múi giờ và INTERVAL.
- **BOOLEAN:** kiểu logic ba trạng thái TRUE, FALSE và NULL trong PL/SQL.

Một điểm cần phân biệt là kiểu dữ liệu của biến PL/SQL và kiểu dữ liệu của cột SQL. Chẳng hạn, trong Oracle Database 19c, PL/SQL có BOOLEAN nhưng bảng SQL không có cột BOOLEAN; hỗ trợ kiểu BOOLEAN trong SQL được bổ sung từ Oracle Database 23c. Bài học nêu rõ các khác biệt này và dùng cú pháp tương thích rộng với Oracle 19c, trừ nơi ghi chú riêng.

## 1. Khai báo biến và kiểu dữ liệu trong PL/SQL

Biến được khai báo trong phần DECLARE của block, procedure, function hoặc package:

~~~sql
DECLARE
    l_count       PLS_INTEGER := 0;
    l_amount      NUMBER(14,2) := 125000.50;
    l_customer    VARCHAR2(100 CHAR);
    l_created_at  TIMESTAMP WITH TIME ZONE := SYSTIMESTAMP;
    l_is_active   BOOLEAN := TRUE;
BEGIN
    l_count := l_count + 1;
    DBMS_OUTPUT.PUT_LINE('Count = ' || l_count);
END;
/
~~~

Khai báo biến thường có dạng:

~~~sql
variable_name data_type [NOT NULL] [:= initial_value];
~~~

Các điểm cần nhớ:

- Biến PL/SQL chưa được gán giá trị mặc định có giá trị ban đầu là NULL.
- NOT NULL buộc biến luôn có giá trị khác NULL; biến phải có giá trị khởi tạo.
- Toán tử := dùng để gán giá trị trong PL/SQL.
- CONSTANT khai báo hằng và yêu cầu khởi tạo.
- Một biến chỉ có phạm vi trong block hoặc chương trình nơi nó được khai báo, trừ khi khai báo ở package scope.

Ví dụ:

~~~sql
DECLARE
    c_tax_rate CONSTANT NUMBER(5,4) := 0.0850;
    l_net      NUMBER(14,2) := 100000;
    l_tax      NUMBER(14,2);
BEGIN
    l_tax := l_net * c_tax_rate;
    DBMS_OUTPUT.PUT_LINE('Tax = ' || TO_CHAR(l_tax, 'FM9999990D00'));
END;
/
~~~

## 2. Nhóm kiểu dữ liệu số

### 2.1 NUMBER

NUMBER là kiểu số thập phân tổng quát của Oracle. Nó phù hợp với tiền tệ, số lượng, tỷ lệ và các phép tính cần độ chính xác thập phân.

Các dạng khai báo thường gặp:

~~~sql
DECLARE
    l_value       NUMBER;
    l_amount      NUMBER(12,2);
    l_percentage  NUMBER(7,4);
    l_whole       NUMBER(8,0);
BEGIN
    NULL;
END;
/
~~~

Ý nghĩa:

- NUMBER: không khai báo precision/scale cụ thể; Oracle lưu giá trị số trong phạm vi hỗ trợ.
- NUMBER(p): giới hạn số chữ số có nghĩa theo precision p, scale mặc định bằng 0.
- NUMBER(p,s): p là precision, s là scale.

Precision của NUMBER có thể từ 1 đến 38 chữ số. Scale xác định số chữ số ở bên phải dấu thập phân khi dương; scale âm làm tròn ở bên trái dấu thập phân. Scale có phạm vi rộng hơn precision, vì vậy cần chọn theo yêu cầu nghiệp vụ.

Ví dụ:

~~~sql
DECLARE
    l_price    NUMBER(10,2) := 1234.567;
    l_quantity NUMBER(8,0) := 12;
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_price);
    DBMS_OUTPUT.PUT_LINE(l_quantity);
END;
/
~~~

Khi gán một giá trị có nhiều chữ số thập phân vào NUMBER(10,2), Oracle làm tròn theo scale của biến. Nếu số chữ số cần lưu vượt precision cho phép, phép gán có thể phát sinh lỗi giá trị/độ chính xác như VALUE_ERROR trong PL/SQL.

Không nên dựa vào việc cột hoặc biến tự làm tròn để thay thế quy tắc tiền tệ. Nếu nghiệp vụ quy định cách làm tròn cụ thể, hãy dùng ROUND với scale rõ ràng tại đúng bước tính:

~~~sql
l_total := ROUND(l_unit_price * l_quantity, 2);
~~~

### 2.2 Precision và scale

Với NUMBER(7,2):

- Tổng cộng tối đa 7 chữ số có nghĩa.
- Hai chữ số dành cho phần thập phân.
- Phần nguyên có tối đa 5 chữ số.

Ví dụ các giá trị có thể biểu diễn trong giới hạn:

| Giá trị | Ý nghĩa |
|---:|---|
| 12345.67 | 5 chữ số nguyên và 2 chữ số thập phân |
| 0.25 | Giá trị nhỏ hơn 1 |
| -99999.99 | Biên âm theo độ rộng khai báo |

Một giá trị như 123456.78 vượt giới hạn precision của NUMBER(7,2). Một giá trị có nhiều hơn hai chữ số thập phân sẽ được làm tròn theo scale khi lưu/gán; sau khi làm tròn, nếu phần nguyên vẫn vượt giới hạn thì phát sinh lỗi.

### 2.3 INTEGER, SMALLINT, DECIMAL và NUMERIC

Oracle có các tên kiểu số quen thuộc tương thích với cú pháp SQL:

- INTEGER và SMALLINT là các subtype của NUMBER với scale bằng 0.
- DECIMAL và NUMERIC là các tên subtype của NUMBER có thể khai báo precision/scale.
- REAL và DOUBLE PRECISION trong ngữ cảnh SQL Oracle là tên kiểu số ánh xạ theo quy tắc Oracle; chúng không nên bị nhầm với BINARY_FLOAT/BINARY_DOUBLE.

Với biến PL/SQL, có thể dùng NUMBER(p,0) hoặc PLS_INTEGER tùy miền giá trị và nhu cầu. Với cột bảng, hãy kiểm tra kiểu dữ liệu được định nghĩa trong DDL thay vì suy đoán từ tên kiểu chuẩn SQL.

### 2.4 PLS_INTEGER và BINARY_INTEGER

PLS_INTEGER là kiểu số nguyên có dấu 32-bit, có miền giá trị:

~~~text
-2,147,483,648 đến 2,147,483,647
~~~

Nó thường phù hợp với:

- Biến đếm vòng lặp.
- Chỉ số collection.
- Số lần thử.
- Các phép tính số nguyên nhỏ trong logic PL/SQL.

Ví dụ:

~~~sql
DECLARE
    l_counter PLS_INTEGER := 0;
BEGIN
    FOR i IN 1 .. 5 LOOP
        l_counter := l_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(l_counter);
END;
/
~~~

BINARY_INTEGER là tên kiểu cũ tương đương về cơ bản với PLS_INTEGER trong PL/SQL hiện đại. Code mới thường dùng PLS_INTEGER để thể hiện rõ ý định.

Nếu phép tính PLS_INTEGER vượt miền biểu diễn, có thể phát sinh NUMERIC_OVERFLOW/VALUE_ERROR. Không dùng PLS_INTEGER cho tổng tiền lớn hoặc số nguyên có thể vượt 32-bit.

### 2.5 SIMPLE_INTEGER

SIMPLE_INTEGER là subtype của PLS_INTEGER có ràng buộc NOT NULL. Nó được thiết kế cho những trường hợp tính toán số nguyên trong PL/SQL cần hiệu năng cao và giá trị luôn khác NULL.

~~~sql
DECLARE
    l_counter SIMPLE_INTEGER := 0;
BEGIN
    l_counter := l_counter + 1;
END;
/
~~~

Chỉ dùng SIMPLE_INTEGER khi miền giá trị, quy tắc NULL và hành vi số học đã được hiểu rõ. Tối ưu hiệu năng của nó phụ thuộc cách biên dịch PL/SQL và môi trường thực thi; không thay PLS_INTEGER bằng SIMPLE_INTEGER một cách máy móc.

### 2.6 Các subtype số nguyên có sẵn

PL/SQL cung cấp một số subtype dựa trên PLS_INTEGER:

| Subtype | Miền giá trị/đặc điểm |
|---|---|
| NATURAL | Số nguyên từ 0 trở lên trong miền PLS_INTEGER |
| NATURALN | Như NATURAL và không cho phép NULL |
| POSITIVE | Số nguyên dương trong miền PLS_INTEGER |
| POSITIVEN | Như POSITIVE và không cho phép NULL |
| SIGNTYPE | Chỉ nhận -1, 0 hoặc 1 |
| SIMPLE_INTEGER | PLS_INTEGER có ràng buộc NOT NULL |

Các subtype này giúp thể hiện ý nghĩa dữ liệu, nhưng không thay thế validation nghiệp vụ. Ví dụ POSITIVE không tự chứng minh số lượng hàng trong kho đang hợp lệ theo quy tắc ứng dụng.

### 2.7 BINARY_FLOAT và BINARY_DOUBLE

Đây là các kiểu dấu phẩy động nhị phân theo chuẩn IEEE:

- BINARY_FLOAT: độ chính xác đơn, 32-bit.
- BINARY_DOUBLE: độ chính xác kép, 64-bit.

Chúng phù hợp với tính toán khoa học, đo lường hoặc dữ liệu xấp xỉ mà hiệu năng dấu phẩy động quan trọng.

~~~sql
DECLARE
    l_measure  BINARY_FLOAT := 12.5;
    l_distance BINARY_DOUBLE := 123456.789;
BEGIN
    l_measure := l_measure * 1.1;
    l_distance := l_distance / 3;
END;
/
~~~

Số thập phân như 0.1 có thể không được biểu diễn chính xác bằng dạng nhị phân hữu hạn. Vì vậy, kết quả phép tính floating-point có thể có sai số nhỏ.

Với tiền tệ hoặc số liệu cần đối chiếu chính xác theo chữ số thập phân, ưu tiên NUMBER thay vì BINARY_FLOAT/BINARY_DOUBLE.

### 2.8 Chọn NUMBER hay PLS_INTEGER?

| Nhu cầu | Kiểu thường phù hợp |
|---|---|
| Số tiền, thuế, tỷ lệ thập phân | NUMBER(p,s) |
| Số lượng hàng lớn hoặc số nguyên có miền rộng | NUMBER(p,0) |
| Bộ đếm, chỉ số collection trong miền 32-bit | PLS_INTEGER |
| Tính toán đo lường xấp xỉ | BINARY_FLOAT hoặc BINARY_DOUBLE |
| Giá trị luôn khác NULL và tối ưu số nguyên có kiểm soát | Có thể cân nhắc SIMPLE_INTEGER |

Không chọn kiểu chỉ vì tên ngắn hơn. Hãy xét miền giá trị, độ chính xác, phép toán và cách dữ liệu được lưu trong SQL.

## 3. Nhóm kiểu chuỗi

### 3.1 CHAR và VARCHAR2

CHAR là kiểu ký tự có độ dài cố định. Giá trị ngắn hơn độ dài khai báo được đệm bằng khoảng trắng ở cuối.

VARCHAR2 là kiểu ký tự có độ dài thay đổi. Nó chỉ lưu phần dữ liệu thực tế cùng overhead nội bộ.

Ví dụ khai báo biến:

~~~sql
DECLARE
    l_country_code CHAR(2) := 'VN';
    l_customer_name VARCHAR2(100 CHAR) := 'Nguyen An';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_country_code);
    DBMS_OUTPUT.PUT_LINE(l_customer_name);
END;
/
~~~

CHAR thường phù hợp với mã có độ dài cố định, chẳng hạn mã quốc gia 2 ký tự. VARCHAR2 phù hợp với tên, địa chỉ, mô tả hoặc giá trị có độ dài thay đổi.

Không nên dùng CHAR cho chuỗi có độ dài biến thiên nếu khoảng trắng đệm gây khó khăn khi so sánh hoặc hiển thị.

### 3.2 BYTE và CHAR length semantics

Khai báo VARCHAR2 có thể chỉ độ dài theo byte hoặc theo ký tự:

~~~sql
VARCHAR2(100 BYTE)
VARCHAR2(100 CHAR)
~~~

- BYTE giới hạn số byte lưu trữ.
- CHAR giới hạn số ký tự theo semantics của Oracle.

Trong bộ ký tự đa byte như AL32UTF8, một ký tự có thể chiếm nhiều byte. Vì vậy, VARCHAR2(100 BYTE) không nhất thiết chứa được 100 ký tự tiếng Việt hoặc ký tự Unicode.

Trong PL/SQL, biến CHAR/VARCHAR2 có giới hạn tối đa 32.767 byte. Kiểu SQL trong bảng có giới hạn riêng phụ thuộc cấu hình MAX_STRING_SIZE và phiên bản; không suy luận giới hạn cột SQL từ giới hạn biến PL/SQL.

Để tránh mơ hồ, khai báo CHAR/BYTE tường minh khi yêu cầu ứng dụng phụ thuộc độ dài. Các hàm thường dùng:

~~~sql
LENGTH(value)   -- Độ dài theo ký tự
LENGTHB(value)  -- Độ dài theo byte
~~~

Ví dụ:

~~~sql
DECLARE
    l_text VARCHAR2(20 CHAR) := 'Việt Nam';
BEGIN
    DBMS_OUTPUT.PUT_LINE('Characters=' || LENGTH(l_text));
    DBMS_OUTPUT.PUT_LINE('Bytes=' || LENGTHB(l_text));
END;
/
~~~

Số byte phụ thuộc bộ ký tự database; không gán một kết quả cố định cho mọi môi trường.

### 3.3 NCHAR và NVARCHAR2

NCHAR và NVARCHAR2 dùng national character set:

- NCHAR: độ dài cố định.
- NVARCHAR2: độ dài thay đổi.

Chúng có thể cần thiết trong hệ thống có yêu cầu cụ thể về national character set. Trong nhiều hệ thống hiện đại dùng AL32UTF8 làm database character set, VARCHAR2 đã hỗ trợ Unicode đầy đủ; không cần chọn NVARCHAR2 chỉ vì chuỗi có dấu tiếng Việt.

Khi trộn VARCHAR2 với NVARCHAR2 hoặc CHAR với NCHAR, Oracle có thể phải chuyển đổi kiểu ký tự. Hãy thống nhất kiểu dữ liệu trong schema và bind variable.

### 3.4 CLOB và NCLOB

CLOB lưu lượng văn bản lớn; NCLOB lưu văn bản lớn theo national character set. Chúng phù hợp với nội dung dài như tài liệu, nội dung bài viết hoặc payload văn bản.

Ví dụ cột:

~~~sql
CREATE TABLE documents (
    document_id NUMBER PRIMARY KEY,
    title       VARCHAR2(300 CHAR),
    body        CLOB
);
~~~

Trong PL/SQL, biến CLOB có thể chứa nội dung lớn hơn nhiều so với VARCHAR2. Thao tác nối, cắt, đọc và ghi LOB có các API như DBMS_LOB; không nên giả định mọi phép toán chuỗi ngắn đều áp dụng trực tiếp với LOB mà không có giới hạn.

### 3.5 Chuỗi rỗng và NULL trong Oracle

Trong Oracle hiện nay, chuỗi ký tự có độ dài bằng 0 như chuỗi literal hai dấu nháy đơn được xem là NULL đối với CHAR/VARCHAR2. Đây là khác biệt quan trọng so với một số hệ quản trị khác.

Ví dụ:

~~~sql
DECLARE
    l_text VARCHAR2(10) := '';
BEGIN
    IF l_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Value is NULL');
    END IF;
END;
/
~~~

Một chuỗi chỉ có dấu cách như ba ký tự khoảng trắng không phải NULL. Nó là chuỗi chứa các ký tự khoảng trắng.

Hệ quả:

- Không thể dùng chuỗi rỗng để phân biệt trạng thái “chuỗi rỗng” với “không có giá trị” trong VARCHAR2 theo cách thông thường.
- LENGTH của chuỗi rỗng trả về NULL.
- So sánh cột với chuỗi rỗng không phải cách tìm một giá trị rỗng độc lập; trong Oracle nó tương đương so sánh với NULL và không trả TRUE.
- Dùng IS NULL để kiểm tra NULL.

Oracle đã duy trì quy tắc này lâu dài, nhưng tài liệu Oracle lưu ý ứng dụng không nên dựa vào việc chuỗi rỗng luôn đồng nhất với NULL trong mọi tương lai.

### 3.6 Chuỗi có dấu nháy và q-quoting

Chuỗi literal thường đặt trong dấu nháy đơn. Muốn chứa dấu nháy đơn, viết hai dấu nháy:

~~~sql
DECLARE
    l_message VARCHAR2(100) := 'User''s account is active';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

Với nội dung có nhiều dấu nháy, PL/SQL hỗ trợ alternative quoting:

~~~sql
DECLARE
    l_message VARCHAR2(200) := q'[It is Oracle PL/SQL]';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

Ký tự mở và đóng trong q-quoting có thể chọn theo nội dung, giúp tránh phải escape nhiều dấu nháy đơn.

## 4. Nhóm kiểu ngày giờ

### 4.1 DATE

DATE lưu năm, tháng, ngày, giờ, phút và giây. DATE của Oracle không chỉ lưu ngày lịch; nó có cả phần thời gian đến giây, nhưng không lưu fractional seconds và không lưu timezone.

Ví dụ:

~~~sql
DECLARE
    l_created_at DATE := DATE '2026-11-14';
BEGIN
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(
        l_created_at,
        'YYYY-MM-DD HH24:MI:SS'
    ));
END;
/
~~~

Date literal DATE '2026-11-14' có thời gian mặc định 00:00:00. Nếu cần giờ cụ thể, dùng TO_DATE với format mask:

~~~sql
DECLARE
    l_meeting_at DATE;
BEGIN
    l_meeting_at := TO_DATE(
        '14-11-2026 09:30:00',
        'DD-MM-YYYY HH24:MI:SS'
    );
END;
/
~~~

### 4.2 TIMESTAMP

TIMESTAMP mở rộng DATE bằng fractional seconds. Độ chính xác fractional seconds có thể khai báo từ 0 đến 9 chữ số; mặc định thường là 6.

~~~sql
DECLARE
    l_event_time TIMESTAMP(6);
BEGIN
    l_event_time := TIMESTAMP '2026-11-14 09:30:15.123456';
END;
/
~~~

TIMESTAMP phù hợp khi cần độ chính xác thời gian nhỏ hơn một giây. Nó vẫn không tự chứa timezone nếu không dùng biến thể có timezone.

### 4.3 TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE lưu thời điểm cùng thông tin múi giờ/offset. Ví dụ:

~~~sql
DECLARE
    l_event_time TIMESTAMP WITH TIME ZONE;
BEGIN
    l_event_time := TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:15 Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS TZR'
    );
END;
/
~~~

Có thể dùng offset như +07:00 hoặc tên vùng như Asia/Ho_Chi_Minh. Dùng tên vùng khi quy tắc daylight saving time và lịch sử múi giờ có ý nghĩa.

### 4.4 TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE được chuẩn hóa theo database time zone khi lưu và hiển thị theo session time zone khi đọc. Kiểu này không giữ lại timezone ban đầu của client như một phần giá trị trả về.

Nó hữu ích khi ứng dụng muốn lưu các thời điểm được chuẩn hóa nhưng hiển thị theo múi giờ session. Cần cấu hình database time zone và session time zone có chủ đích.

### 4.5 So sánh các kiểu ngày giờ

| Kiểu | Có phần thời gian? | Fractional seconds? | Có timezone? |
|---|---|---|---|
| DATE | Có, tới giây | Không | Không |
| TIMESTAMP | Có | Có | Không |
| TIMESTAMP WITH TIME ZONE | Có | Có | Có offset/region |
| TIMESTAMP WITH LOCAL TIME ZONE | Có | Có | Chuẩn hóa khi lưu, hiển thị theo session |

Chọn kiểu theo ngữ nghĩa dữ liệu:

- Ngày nghiệp vụ không cần múi giờ: DATE có thể đủ.
- Thời điểm cần độ chính xác cao: TIMESTAMP.
- Thời điểm đến từ nhiều múi giờ: TIMESTAMP WITH TIME ZONE.
- Thời điểm lưu chuẩn hóa và hiển thị theo timezone session: cân nhắc TIMESTAMP WITH LOCAL TIME ZONE.

### 4.6 SYSDATE, SYSTIMESTAMP, CURRENT_DATE và CURRENT_TIMESTAMP

Các hàm thời gian thường gặp:

| Hàm | Kiểu trả về | Ngữ nghĩa |
|---|---|---|
| SYSDATE | DATE | Ngày giờ theo đồng hồ hệ điều hành của database server |
| SYSTIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp theo đồng hồ hệ thống của database server, có timezone/offset |
| CURRENT_DATE | DATE | Ngày giờ hiện tại theo session time zone |
| CURRENT_TIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp hiện tại theo session time zone |
| LOCALTIMESTAMP | TIMESTAMP | Timestamp hiện tại theo session time zone nhưng không giữ timezone trong kết quả |

Đừng thay thế các hàm này cho nhau nếu ứng dụng phụ thuộc timezone. Một session ở múi giờ khác có thể nhận CURRENT_DATE/CURRENT_TIMESTAMP khác cách hiển thị so với SYSDATE/SYSTIMESTAMP.

### 4.7 DATE arithmetic

Với DATE, cộng hoặc trừ một NUMBER diễn giải số ngày:

~~~sql
DECLARE
    l_start DATE := DATE '2026-11-14';
    l_next  DATE;
BEGIN
    l_next := l_start + 1;
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(l_next, 'YYYY-MM-DD'));
END;
/
~~~

Ví dụ:

- date_value + 1: cộng một ngày.
- date_value + 1/24: cộng một giờ.
- date_value - 7: lùi bảy ngày.
- date_value_2 - date_value_1: trả số ngày dạng NUMBER, có thể gồm phần lẻ.

Với dữ liệu có timezone và yêu cầu lịch địa phương, không nên mặc định “một ngày lịch” luôn giống đúng 24 giờ trong mọi tình huống chuyển đổi DST. Hãy xác định nghiệp vụ đang cần khoảng thời gian tuyệt đối hay ngày lịch theo một vùng.

### 4.8 INTERVAL YEAR TO MONTH

INTERVAL YEAR TO MONTH biểu diễn khoảng thời gian theo năm và tháng:

~~~sql
DECLARE
    l_contract_period INTERVAL YEAR TO MONTH;
BEGIN
    l_contract_period := INTERVAL '2-6' YEAR TO MONTH;
END;
/
~~~

Giá trị ví dụ biểu diễn 2 năm 6 tháng. Dùng cho thời hạn hợp đồng, kỳ hạn hoặc phép tính lịch theo tháng/năm.

### 4.9 INTERVAL DAY TO SECOND

INTERVAL DAY TO SECOND biểu diễn ngày, giờ, phút, giây và fractional seconds:

~~~sql
DECLARE
    l_timeout INTERVAL DAY TO SECOND;
BEGIN
    l_timeout := INTERVAL '0 00:05:30' DAY TO SECOND;
END;
/
~~~

Giá trị trên biểu diễn 5 phút 30 giây. Kiểu này phù hợp với duration, timeout, thời gian xử lý và khoảng cách giữa hai timestamp.

### 4.10 DATE và TIMESTAMP subtraction

Trừ hai DATE:

~~~sql
SELECT DATE '2026-11-14' - DATE '2026-11-10' AS days_between
FROM dual;
~~~

trả về số ngày.

Trừ hai TIMESTAMP:

~~~sql
SELECT TIMESTAMP '2026-11-14 10:00:00'
     - TIMESTAMP '2026-11-14 09:30:00' AS elapsed_time
FROM dual;
~~~

trả về INTERVAL DAY TO SECOND.

### 4.11 NUMTOYMINTERVAL và NUMTODSINTERVAL

Hai hàm này chuyển số sang interval:

~~~sql
SELECT NUMTOYMINTERVAL(3, 'MONTH') AS three_months,
       NUMTODSINTERVAL(90, 'MINUTE') AS ninety_minutes
FROM dual;
~~~

Chúng hữu ích khi cần biểu diễn khoảng thời gian động trong SQL/PLSQL. Cần xác định rõ đơn vị nghiệp vụ, đặc biệt khi tính hạn theo tháng, cuối tháng hoặc ngày lịch.

## 5. Chuyển đổi ngày giờ và định dạng

### 5.1 Dùng literal chuẩn

DATE literal:

~~~sql
DATE '2026-11-14'
~~~

TIMESTAMP literal:

~~~sql
TIMESTAMP '2026-11-14 09:30:15.123456'
~~~

Literal chuẩn giúp tránh phụ thuộc NLS_DATE_FORMAT hoặc định dạng ngày theo ngôn ngữ session.

### 5.2 TO_DATE

Chuyển chuỗi thành DATE:

~~~sql
DECLARE
    l_date DATE;
BEGIN
    l_date := TO_DATE('14/11/2026', 'DD/MM/YYYY');
END;
/
~~~

Luôn chỉ rõ format mask khi chuyển chuỗi thành ngày. Nếu bỏ format mask, kết quả phụ thuộc NLS_DATE_FORMAT của session.

### 5.3 TO_TIMESTAMP và TO_TIMESTAMP_TZ

~~~sql
DECLARE
    l_ts    TIMESTAMP(6);
    l_ts_tz TIMESTAMP WITH TIME ZONE;
BEGIN
    l_ts := TO_TIMESTAMP(
        '2026-11-14 09:30:15.123456',
        'YYYY-MM-DD HH24:MI:SS.FF6'
    );

    l_ts_tz := TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:15 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    );
END;
/
~~~

Format mask cần khớp dữ liệu đầu vào. FF biểu diễn fractional seconds; TZH:TZM biểu diễn offset giờ/phút; TZR dùng timezone region.

### 5.4 TO_CHAR

Chuyển ngày giờ thành chuỗi hiển thị:

~~~sql
SELECT TO_CHAR(
           SYSTIMESTAMP,
           'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
       ) AS formatted_time
FROM dual;
~~~

Định dạng đầu ra chỉ phục vụ trình bày. Không nên lưu ngày giờ thành VARCHAR2 chỉ để giữ một định dạng hiển thị; lưu bằng DATE/TIMESTAMP để có thể so sánh, tính toán và index đúng kiểu.

### 5.5 Tránh implicit conversion

Không nên viết:

~~~sql
WHERE order_date = '14/11/2026'
~~~

vì Oracle phải chuyển chuỗi sang kiểu ngày theo NLS settings. Hãy dùng:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

hoặc bind một biến DATE đúng kiểu từ ứng dụng.

Không gọi TO_DATE trên một cột vốn đã là DATE. TO_DATE nhận chuỗi và trả DATE. Khi đưa DATE vào TO_DATE, Oracle có thể phải chuyển DATE thành chuỗi ngầm trước, phụ thuộc NLS, vừa không cần thiết vừa có thể làm sai dữ liệu hoặc ảnh hưởng index access.

### 5.6 NLS và ngôn ngữ hiển thị

Tên tháng, tên ngày và dấu phân cách số có thể phụ thuộc NLS settings. Nếu cần định dạng ổn định:

- Chỉ rõ format mask.
- Chỉ rõ NLS_DATE_LANGUAGE khi format có tên tháng/ngày.
- Chỉ rõ NLS_NUMERIC_CHARACTERS khi chuyển số theo chuỗi.
- Dùng bind variable đúng kiểu dữ liệu thay vì ghép chuỗi SQL.

Ví dụ:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

## 6. Kiểu BOOLEAN trong PL/SQL

BOOLEAN là kiểu logic dùng trong PL/SQL. Nó có ba trạng thái:

- TRUE.
- FALSE.
- NULL (chưa xác định/unknown).

Ví dụ:

~~~sql
DECLARE
    l_is_valid BOOLEAN := TRUE;
    l_is_paid  BOOLEAN := FALSE;
    l_is_ready BOOLEAN;
BEGIN
    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    END IF;

    IF l_is_paid = FALSE THEN
        DBMS_OUTPUT.PUT_LINE('Not paid');
    END IF;

    IF l_is_ready IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Ready state is unknown');
    END IF;
END;
/
~~~

Biến BOOLEAN chưa được khởi tạo có giá trị NULL, không phải FALSE.

### 6.1 BOOLEAN khác NUMBER(1) hoặc CHAR(1)

Một số hệ thống dùng NUMBER(1) hoặc CHAR(1) để biểu diễn cờ:

| Kiểu | Giá trị thường dùng |
|---|---|
| BOOLEAN trong PL/SQL | TRUE, FALSE, NULL |
| NUMBER(1) | 1, 0, NULL |
| CHAR(1) | 'Y', 'N', NULL |

BOOLEAN thể hiện trực tiếp ý nghĩa logic trong code. NUMBER(1)/CHAR(1) là cách mô hình hóa ở cột SQL trong các phiên bản chưa hỗ trợ SQL BOOLEAN hoặc khi schema có quy ước riêng.

Không tự coi mọi giá trị NUMBER khác 0 là TRUE nếu ứng dụng chỉ cho phép 0 và 1. Hãy dùng CHECK constraint để bảo vệ miền giá trị:

~~~sql
CREATE TABLE feature_flags (
    flag_name VARCHAR2(100) PRIMARY KEY,
    is_enabled NUMBER(1) NOT NULL,
    CONSTRAINT ck_feature_flag_enabled
        CHECK (is_enabled IN (0, 1))
);
~~~

### 6.2 TRUE, FALSE và NULL trong điều kiện IF

Trong PL/SQL, nhánh IF chỉ chạy khi biểu thức là TRUE. Nếu biểu thức là FALSE hoặc NULL, nhánh THEN không chạy.

~~~sql
DECLARE
    l_approved BOOLEAN;
BEGIN
    IF l_approved THEN
        DBMS_OUTPUT.PUT_LINE('Approved');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not approved or unknown');
    END IF;
END;
/
~~~

Vì l_approved là NULL, chương trình chạy nhánh ELSE. Nếu cần phân biệt FALSE với NULL, phải kiểm tra NULL riêng:

~~~sql
IF l_approved IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Not decided');
ELSIF l_approved THEN
    DBMS_OUTPUT.PUT_LINE('Approved');
ELSE
    DBMS_OUTPUT.PUT_LINE('Rejected');
END IF;
~~~

### 6.3 Logic ba trạng thái

BOOLEAN trong PL/SQL tuân theo logic ba trạng thái. Một số kết quả:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | NULL | NULL | TRUE |
| FALSE | NULL | FALSE | NULL |
| NULL | NULL | NULL | NULL |

Phép NOT:

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| NULL | NULL |

Ví dụ:

~~~sql
DECLARE
    l_has_stock BOOLEAN := NULL;
BEGIN
    IF NOT l_has_stock THEN
        DBMS_OUTPUT.PUT_LINE('No stock');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Stock exists or state is unknown');
    END IF;
END;
/
~~~

NOT NULL vẫn là NULL. Vì vậy, điều kiện IF NOT l_has_stock không chạy khi biến là NULL. Nếu nghiệp vụ phải phân biệt không có hàng với chưa biết tồn kho, hãy xử lý trạng thái NULL riêng.

### 6.4 BOOLEAN và toán tử so sánh

So sánh với NULL bằng dấu bằng hoặc khác không tạo ra TRUE/FALSE như mong đợi:

~~~sql
-- Không dùng để kiểm tra NULL:
IF l_flag = NULL THEN
    NULL;
END IF;
~~~

Phải dùng:

~~~sql
IF l_flag IS NULL THEN
    NULL;
END IF;
~~~

Tương tự với các biểu thức số/chuỗi/ngày giờ, dùng IS NULL hoặc IS NOT NULL thay cho = NULL.

### 6.5 BOOLEAN trong SQL trước và từ Oracle Database 23c

Trong Oracle Database 19c:

- BOOLEAN là kiểu PL/SQL.
- Không khai báo được cột BOOLEAN trong bảng SQL.
- Không dùng biến BOOLEAN như một cột SQL thông thường.
- Một function trả BOOLEAN không thể được gọi trực tiếp từ câu SQL theo cách gọi function trả kiểu SQL thông thường.

Từ Oracle Database 23c, SQL có kiểu dữ liệu BOOLEAN, có thể dùng trong SQL table, expression và PL/SQL với hỗ trợ của phiên bản.

Nếu ứng dụng phải tương thích Oracle 19c, hãy dùng quy ước lưu trữ như NUMBER(1) hoặc CHAR(1) và chuyển đổi sang BOOLEAN trong tầng PL/SQL. Nếu triển khai trên 23c trở lên, kiểm tra driver, công cụ và compatibility settings trước khi thay đổi schema/API.

### 6.6 Ví dụ chuyển cờ SQL thành BOOLEAN trong PL/SQL

Với schema dùng NUMBER(1):

~~~sql
DECLARE
    l_flag_value NUMBER(1);
    l_is_enabled BOOLEAN;
BEGIN
    SELECT is_enabled
    INTO l_flag_value
    FROM feature_flags
    WHERE flag_name = 'NEW_CHECKOUT';

    l_is_enabled := (l_flag_value = 1);

    IF l_is_enabled THEN
        DBMS_OUTPUT.PUT_LINE('Feature enabled');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Feature disabled');
    END IF;
END;
/
~~~

Ví dụ giả định cột IS_ENABLED NOT NULL và chỉ có 0/1. Nếu cột cho phép NULL, phép so sánh l_flag_value = 1 có thể tạo BOOLEAN NULL; ứng dụng cần quyết định NULL nghĩa là gì.

## 7. Chuyển đổi giữa các kiểu dữ liệu

Oracle có thể thực hiện implicit conversion, nhưng code rõ ràng nên dùng explicit conversion khi kiểu dữ liệu khác nhau.

### 7.1 Chuyển số

~~~sql
DECLARE
    l_text   VARCHAR2(30) := '12345.67';
    l_amount NUMBER(12,2);
BEGIN
    l_amount := TO_NUMBER(
        l_text,
        '999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    );
END;
/
~~~

TO_NUMBER chuyển chuỗi thành số. Format mask và NLS_NUMERIC_CHARACTERS giúp quy định dấu thập phân/dấu phân nhóm thay vì phụ thuộc session.

### 7.2 Chuyển số thành chuỗi

~~~sql
DECLARE
    l_amount NUMBER(12,2) := 12345.6;
    l_text   VARCHAR2(40);
BEGIN
    l_text := TO_CHAR(
        l_amount,
        'FM999G999G990D00',
        'NLS_NUMERIC_CHARACTERS='',.'''
    );
END;
/
~~~

TO_CHAR phục vụ hiển thị. Đừng lưu chuỗi định dạng rồi dùng lại làm giá trị số nếu có thể giữ NUMBER trong suốt quá trình tính toán.

### 7.3 CAST

CAST chuyển biểu thức sang kiểu đích:

~~~sql
SELECT CAST('2026-11-14' AS DATE)
FROM dual;
~~~

Ví dụ này có thể phụ thuộc cách Oracle diễn giải chuỗi ngày theo NLS. Với chuỗi đầu vào có format đã biết, TO_DATE có format mask thường rõ ràng hơn.

### 7.4 Tránh implicit conversion trong predicate

Giả sử EMPLOYEE_ID là NUMBER. Truy vấn bind chuỗi có thể buộc Oracle chuyển kiểu:

~~~sql
WHERE employee_id = '1001'
~~~

Hãy bind số:

~~~sql
WHERE employee_id = :employee_id
~~~

với bind variable có kiểu NUMBER từ driver. Kiểu bind đúng giúp tránh chuyển đổi ngoài ý muốn và có thể hỗ trợ index access tốt hơn.

## 8. NULL trong biến PL/SQL

NULL có nghĩa là chưa có giá trị hoặc không xác định; nó không giống 0, chuỗi khoảng trắng hay FALSE.

Ví dụ:

~~~sql
DECLARE
    l_amount NUMBER;
    l_name   VARCHAR2(100);
    l_flag   BOOLEAN;
BEGIN
    IF l_amount IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Amount is unknown');
    END IF;

    IF l_name IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Name is missing');
    END IF;

    IF l_flag IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Flag is unknown');
    END IF;
END;
/
~~~

### 8.1 Phép toán với NULL

Phần lớn phép toán số học với NULL trả NULL:

~~~sql
DECLARE
    l_amount NUMBER := NULL;
    l_total  NUMBER;
BEGIN
    l_total := l_amount + 100;
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

Kết quả vẫn là NULL. Nếu muốn coi NULL là 0, phải làm rõ quy tắc và dùng NVL/COALESCE:

~~~sql
l_total := NVL(l_amount, 0) + 100;
~~~

Không tự động thay mọi NULL bằng 0. Trong dữ liệu tài chính, NULL có thể nghĩa là chưa xác định, trong khi 0 là giá trị đã biết bằng không.

### 8.2 COALESCE, NVL và NULLIF

- NVL(expr1, expr2): trả expr2 khi expr1 là NULL.
- COALESCE(expr1, expr2, ...): trả biểu thức đầu tiên không NULL.
- NULLIF(expr1, expr2): trả NULL nếu hai biểu thức bằng nhau, ngược lại trả expr1.

Ví dụ:

~~~sql
DECLARE
    l_input  NUMBER := NULL;
    l_amount NUMBER;
BEGIN
    l_amount := COALESCE(l_input, 0);
    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

Trong biểu thức chia:

~~~sql
l_ratio := l_numerator / NULLIF(l_denominator, 0);
~~~

NULLIF giúp tránh chia cho 0 bằng cách biến mẫu số 0 thành NULL. Kết quả khi mẫu số bằng 0 là NULL, không phải 0; hãy xử lý theo ý nghĩa nghiệp vụ.

### 8.3 NOT NULL và giá trị khởi tạo

~~~sql
DECLARE
    l_count PLS_INTEGER NOT NULL := 0;
    l_name  VARCHAR2(100) NOT NULL := 'Unknown';
BEGIN
    l_count := l_count + 1;
END;
/
~~~

Biến NOT NULL không được gán NULL. Nếu cố gán NULL, PL/SQL phát sinh lỗi giá trị. Khởi tạo biến rõ ràng giúp tránh logic phụ thuộc vào trạng thái chưa gán.

## 9. Dùng %TYPE và %ROWTYPE

### 9.1 %TYPE

%TYPE khai báo biến dựa trên kiểu dữ liệu của một cột hoặc biến khác:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    SELECT employee_id, salary
    INTO l_employee_id, l_salary
    FROM employees
    WHERE employee_id = 1001;
END;
/
~~~

Lợi ích:

- Giảm việc lặp lại kiểu dữ liệu.
- Khi kiểu cột thay đổi, khai báo phụ thuộc có thể tự đồng bộ khi biên dịch lại.
- Hạn chế sai lệch giữa biến và cột.

%TYPE không tự động kế thừa mọi constraint/default của cột. Đặc biệt, không nên giả định biến %TYPE sẽ có cùng ràng buộc NOT NULL như cột nguồn; nếu biến cần NOT NULL, khai báo constraint đó rõ ràng.

### 9.2 %ROWTYPE

%ROWTYPE khai báo một record có các field tương ứng với cột của table, view hoặc cursor:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
    DBMS_OUTPUT.PUT_LINE(l_employee.salary);
END;
/
~~~

Mỗi field của record có kiểu tương ứng với cột. %ROWTYPE hữu ích khi cần lấy một hàng đầy đủ; nếu chỉ cần một vài cột, khai báo biến riêng giúp thể hiện rõ dữ liệu thực sự được sử dụng.

### 9.3 %TYPE không thay thế kiểm tra NULL

Một biến khai báo theo employees.salary%TYPE có thể nhận NULL nếu kiểu/logic cho phép, ngay cả khi cột nguồn có NOT NULL. Hãy kiểm tra schema và ràng buộc nghiệp vụ tại nơi sử dụng.

## 10. Kết hợp các kiểu trong một block thực tế

Ví dụ một block tính giá trị đơn hàng và xác định trạng thái:

~~~sql
DECLARE
    l_order_id      orders.order_id%TYPE := 1001;
    l_quantity      PLS_INTEGER := 3;
    l_unit_price    NUMBER(12,2) := 125000.50;
    l_discount_rate NUMBER(5,4) := 0.10;
    l_order_total   NUMBER(14,2);
    l_order_date    DATE := SYSDATE;
    l_confirmed     BOOLEAN := FALSE;
    l_description   VARCHAR2(200 CHAR);
BEGIN
    l_order_total := ROUND(
        l_quantity * l_unit_price * (1 - l_discount_rate),
        2
    );

    l_description := 'Order ' || l_order_id ||
                     ' created at ' ||
                     TO_CHAR(l_order_date, 'YYYY-MM-DD HH24:MI:SS');

    IF l_order_total > 0 THEN
        l_confirmed := TRUE;
    END IF;

    IF l_confirmed IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Confirmation is unknown');
    ELSIF l_confirmed THEN
        DBMS_OUTPUT.PUT_LINE('Confirmed: ' || l_description);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not confirmed');
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Total = ' || TO_CHAR(l_order_total, 'FM9999999990D00')
    );
END;
/
~~~

Ví dụ minh họa nhiều nhóm kiểu trong cùng block. Trong ứng dụng thực tế, giá, số lượng, ngày tạo và trạng thái nên lấy từ dữ liệu/bind parameters và được kiểm tra theo ràng buộc nghiệp vụ.

## 11. Chọn kiểu dữ liệu theo miền nghiệp vụ

| Dữ liệu nghiệp vụ | Kiểu thường cân nhắc | Lưu ý |
|---|---|---|
| Tiền tệ | NUMBER(p,2) hoặc scale theo tiền tệ | Xác định quy tắc làm tròn |
| Phần trăm/tỷ lệ | NUMBER(p,s) | Chọn đủ scale và miền giá trị |
| Bộ đếm | PLS_INTEGER hoặc NUMBER | Xét giới hạn 32-bit |
| Số đo khoa học | BINARY_DOUBLE/BINARY_FLOAT | Chấp nhận sai số nhị phân |
| Mã cố định | CHAR(n) | Cẩn thận padding |
| Tên/địa chỉ | VARCHAR2(n CHAR) | Xét Unicode và giới hạn byte |
| Nội dung dài | CLOB/NCLOB | Dùng API LOB khi cần |
| Ngày nghiệp vụ | DATE | Có cả giờ/phút/giây |
| Thời điểm chính xác | TIMESTAMP | Có fractional seconds |
| Thời điểm đa múi giờ | TIMESTAMP WITH TIME ZONE | Giữ timezone/offset |
| Thời điểm chuẩn hóa theo session | TIMESTAMP WITH LOCAL TIME ZONE | Hiển thị theo session timezone |
| Khoảng năm/tháng | INTERVAL YEAR TO MONTH | Không đồng nhất với số ngày cố định |
| Khoảng thời lượng | INTERVAL DAY TO SECOND | Dùng cho duration |
| Cờ logic trong PL/SQL | BOOLEAN | Có TRUE/FALSE/NULL |
| Cờ lưu trong SQL 19c | NUMBER(1) hoặc CHAR(1) | Dùng CHECK constraint |

## 12. Lỗi thường gặp khi làm việc với kiểu dữ liệu

| Lỗi hoặc triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| VALUE_ERROR khi gán số | Giá trị vượt precision/scale hoặc miền kiểu | Chọn kiểu đủ rộng, kiểm tra phép tính |
| Sai số tiền nhỏ | Dùng floating-point nhị phân | Dùng NUMBER và quy tắc ROUND rõ ràng |
| PLS_INTEGER overflow | Vượt miền 32-bit | Dùng NUMBER hoặc kiểm tra giới hạn |
| Chuỗi bị cắt/lỗi | Độ dài biến quá nhỏ hoặc BYTE/CHAR không đúng | Chọn độ dài và semantics rõ |
| Chuỗi tiếng Việt vượt giới hạn byte | Một ký tự chiếm nhiều byte | Xem LENGTHB và charset |
| Chuỗi rỗng bị coi là NULL | Quy tắc Oracle với chuỗi độ dài 0 | Dùng quy ước riêng nếu cần trạng thái phân biệt |
| DATE sai ngày/tháng | Implicit conversion phụ thuộc NLS | Dùng DATE literal hoặc TO_DATE có format |
| Mất phần giờ | Dùng DATE literal hoặc format không có giờ | Kiểm tra format mask và kiểu dữ liệu |
| Thời điểm hiển thị lệch múi giờ | Nhầm SYSDATE với CURRENT_TIMESTAMP hoặc dùng kiểu không timezone | Chọn hàm/kiểu theo timezone nghiệp vụ |
| IF không chạy dù mong đợi FALSE | BOOLEAN thực tế là NULL; NOT NULL vẫn NULL | Kiểm tra trạng thái NULL riêng |
| Không khai báo được cột BOOLEAN trên 19c | BOOLEAN khi đó chỉ là kiểu PL/SQL | Dùng NUMBER(1)/CHAR(1) hoặc nâng phiên bản |
| Index ngày không được dùng | Hàm/implicit conversion áp lên cột | Dùng bind đúng kiểu và range predicate |

## 13. Bài thực hành tự kiểm tra

Các bài thực hành nên chạy trong schema thử nghiệm.

### Bài 1 — NUMBER precision và scale

Khai báo NUMBER(7,2), gán các giá trị có hai, ba và sáu chữ số thập phân. Quan sát cách làm tròn và thử gán một giá trị vượt precision. Giải thích VALUE_ERROR.

### Bài 2 — PLS_INTEGER và NUMBER

Viết biến đếm PLS_INTEGER và biến tổng tiền NUMBER(14,2). Thử tăng bộ đếm gần biên 32-bit và giải thích vì sao không nên dùng PLS_INTEGER cho mọi phép tính số nguyên.

### Bài 3 — Floating-point

Khai báo BINARY_DOUBLE và NUMBER, cộng nhiều lần giá trị 0.1. So sánh kết quả và giải thích khác biệt giữa biểu diễn nhị phân xấp xỉ và NUMBER thập phân.

### Bài 4 — CHAR và VARCHAR2

Gán chuỗi ngắn vào CHAR(5) và VARCHAR2(5). So sánh LENGTH, LENGTHB và cách hiển thị khoảng trắng đệm.

### Bài 5 — BYTE và CHAR semantics

Tạo biến VARCHAR2(10 BYTE) và VARCHAR2(10 CHAR). Gán chuỗi tiếng Việt có dấu. Quan sát độ dài theo byte và theo ký tự trong database character set hiện tại.

### Bài 6 — Empty string và NULL

Gán chuỗi rỗng và chuỗi có một dấu cách vào hai biến VARCHAR2. Kiểm tra IS NULL, LENGTH và LENGTHB. Giải thích vì sao hai giá trị khác nhau.

### Bài 7 — DATE và TIMESTAMP

Tạo DATE và TIMESTAMP có fractional seconds. Thực hiện phép trừ và so sánh kiểu kết quả. Thử định dạng bằng TO_CHAR.

### Bài 8 — Time zone

So sánh SYSDATE, CURRENT_DATE, SYSTIMESTAMP và CURRENT_TIMESTAMP trong session có timezone khác nhau. Giải thích sự khác nhau giữa server time và session time.

### Bài 9 — BOOLEAN ba trạng thái

Khai báo ba biến TRUE, FALSE và NULL. Thử AND, OR, NOT và IF. Viết nhánh phân biệt FALSE với NULL.

### Bài 10 — %TYPE và %ROWTYPE

Khai báo biến theo employees.salary%TYPE và record employees%ROWTYPE. Thử SELECT INTO. Kiểm tra điều gì xảy ra khi SELECT không có hàng hoặc có nhiều hơn một hàng.

### Bài 11 — Explicit conversion

Chuyển chuỗi ngày theo hai format mask khác nhau. Thử thay NLS_DATE_FORMAT của session và giải thích vì sao implicit conversion không an toàn.

### Bài 12 — Mô hình cờ trong SQL 19c

Tạo cột NUMBER(1) NOT NULL có CHECK (value IN (0,1)). Viết PL/SQL block chuyển giá trị sang BOOLEAN và xử lý trường hợp cột cho phép NULL.

## 14. Ghi nhớ

| Nhóm | Điều cần nhớ |
|---|---|
| NUMBER | Kiểu số thập phân phù hợp tiền và dữ liệu cần chính xác |
| NUMBER(p,s) | Precision và scale giới hạn miền giá trị |
| PLS_INTEGER | Số nguyên 32-bit, phù hợp counter/index |
| BINARY_FLOAT/DOUBLE | Floating-point xấp xỉ |
| CHAR/VARCHAR2 | Cố định và biến độ dài |
| BYTE/CHAR semantics | Byte không đồng nghĩa ký tự trong charset đa byte |
| CLOB/NCLOB | Lưu văn bản lớn |
| Empty string | VARCHAR2/CHAR zero-length được Oracle xem là NULL |
| DATE | Có thời gian tới giây, không có timezone |
| TIMESTAMP | Có fractional seconds |
| TIMESTAMP WITH TIME ZONE | Mang timezone/offset |
| INTERVAL | Biểu diễn khoảng năm-tháng hoặc ngày-giây |
| TO_DATE/TO_TIMESTAMP | Chuyển chuỗi bằng format mask tường minh |
| BOOLEAN | TRUE, FALSE, NULL trong PL/SQL |
| SQL BOOLEAN | Có từ Oracle Database 23c; trước đó không có cột BOOLEAN SQL |
| %TYPE/%ROWTYPE | Neo kiểu biến/record theo cột hoặc hàng |
| NULL | Khác 0, FALSE và chuỗi khoảng trắng |

Chọn kiểu dữ liệu theo miền giá trị và ý nghĩa nghiệp vụ, không chỉ theo sự tiện tay khi khai báo. NUMBER bảo vệ độ chính xác thập phân; PLS_INTEGER phù hợp bộ đếm; VARCHAR2 và CHAR cần phân biệt độ dài; DATE/TIMESTAMP phải đi cùng quy tắc timezone và format; BOOLEAN cần xử lý trạng thái NULL. Dùng kiểu rõ ràng, chuyển đổi tường minh và kiểm tra dữ liệu đầu vào sẽ giúp PL/SQL dễ hiểu và tránh nhiều lỗi khó phát hiện.
