# Chuyển kiểu ngầm định, NLS và nguyên nhân mất đường truy cập chỉ mục

Oracle cho phép nhiều biểu thức SQL dùng các giá trị có kiểu dữ liệu khác nhau. Khi cần, database có thể tự chuyển một toán hạng sang kiểu của toán hạng còn lại. Cơ chế này gọi là **implicit data type conversion** (chuyển kiểu ngầm định). Nó giúp câu SQL ngắn gọn, nhưng có thể làm kết quả phụ thuộc NLS session, gây lỗi dữ liệu, tăng CPU và quan trọng nhất là làm thay đổi biểu thức trên cột khiến optimizer không dùng được đường truy cập chỉ mục mà người viết mong đợi.

Một câu SQL có thể chạy đúng trên máy phát triển nhưng lỗi ở production vì NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS khác nhau. Một predicate tưởng như so sánh trực tiếp cột với bind value có thể trở thành TO_NUMBER(column) = :bind; khi đó index thông thường trên column có thể không còn phù hợp. Tương tự, NLS_SORT, collation, kiểu bind từ JDBC/ODP.NET và các hàm như UPPER, TRUNC, NVL có thể thay đổi cách Oracle so sánh dữ liệu hoặc chọn access path.

Sau bài học, bạn có thể:

- Nhận diện implicit conversion trong phép so sánh, join, arithmetic và function call.
- Hiểu quy tắc chuyển kiểu phổ biến giữa NUMBER, character, DATE và TIMESTAMP.
- Tránh phụ thuộc NLS_DATE_FORMAT và NLS_NUMERIC_CHARACTERS.
- Phân biệt conversion ở bind/constant với conversion bọc quanh cột.
- Giải thích vì sao conversion trên cột có thể làm mất index range scan hoặc partition pruning.
- Hiểu ảnh hưởng của CHAR, VARCHAR2, NCHAR, NVARCHAR2 và collation.
- Nhận biết tác động của NLS_COMP, NLS_SORT và session settings.
- Bind dữ liệu bằng đúng datatype trong ứng dụng.
- Dùng explicit conversion, format model và NLS parameter rõ ràng.
- Thiết kế function-based index hoặc virtual column khi truy vấn theo biểu thức là yêu cầu ổn định.
- Đọc Predicate Information để tìm conversion trong execution plan.
- Chẩn đoán ORA-01722, ORA-01843, ORA-01861 và các lỗi chuyển kiểu thường gặp.

> Quy tắc conversion, collation và tính năng SQL có thể khác theo phiên bản Oracle và datatype. Ví dụ trong bài tập trung vào các kiểu phổ biến; hãy kiểm tra SQL Language Reference đúng release, driver và NLS settings của hệ thống.

## 1. Kiểu dữ liệu là một phần của semantics SQL

### 1.1. Vì sao datatype quan trọng?

Datatype quyết định:

- Giá trị nào có thể lưu.
- Phép toán nào có ý nghĩa.
- Cách so sánh và sắp xếp.
- Cách chuyển đổi giữa dữ liệu và text.
- Độ chính xác, scale, character set và length semantics.
- Access path mà optimizer có thể sử dụng.

NUMBER, VARCHAR2 và DATE không chỉ là các cách lưu cùng một giá trị. NUMBER được so sánh theo số học; VARCHAR2 được so sánh theo quy tắc ký tự/collation; DATE biểu diễn ngày và thời gian tới giây. Nếu so sánh NUMBER với VARCHAR2, Oracle phải chọn một quy tắc conversion để tạo biểu thức có thể đánh giá.

### 1.2. Explicit và implicit conversion

Explicit conversion do người viết chỉ rõ:

```sql
SELECT TO_NUMBER('1250') + 10
FROM dual;

SELECT TO_DATE(
           '2026-11-14',
           'YYYY-MM-DD'
       )
FROM dual;
```

Implicit conversion do Oracle thực hiện theo quy tắc datatype:

```sql
SELECT 1250 + '10'
FROM dual;
```

Oracle có thể chuyển character value '10' thành NUMBER để thực hiện phép cộng. Câu lệnh có thể chạy, nhưng người đọc không thấy rõ conversion và input không phải chuỗi số hợp lệ có thể gây lỗi.

### 1.3. Conversion không phải lúc nào cũng vô hại

Một conversion có thể:

- Thay đổi cách so sánh.
- Phụ thuộc NLS session.
- Làm mất thông tin hoặc độ chính xác.
- Phát sinh lỗi chỉ khi một hàng cụ thể được đánh giá.
- Bọc function quanh indexed column.
- Ngăn partition pruning trong một số biểu thức.
- Làm optimizer ước lượng cardinality khác.

Vì vậy, explicit conversion và bind đúng kiểu là một phần của thiết kế SQL, không chỉ là vấn đề phong cách.

## 2. Quy tắc chuyển kiểu ngầm định phổ biến

### 2.1. Character và NUMBER

Trong nhiều phép so sánh NUMBER với character, Oracle chuyển character expression sang NUMBER. Ví dụ:

```sql
SELECT *
FROM products
WHERE product_id = '100';
```

Nếu PRODUCT_ID là NUMBER, Oracle có thể chuyển literal '100' thành NUMBER. Vì literal là hằng số, biểu thức cuối cùng vẫn có thể tương đương:

```sql
WHERE product_id = 100
```

Index trên PRODUCT_ID vẫn có thể được dùng. Tuy nhiên, không nên dựa vào conversion ngầm; dùng bind NUMBER hoặc literal đúng kiểu.

### 2.2. Character column so với NUMBER

Nếu cột là VARCHAR2 nhưng bind/literal là NUMBER:

```sql
SELECT *
FROM legacy_products
WHERE product_code = 100;
```

Oracle có thể chuyển cột character thành NUMBER:

```sql
WHERE TO_NUMBER(product_code) = 100
```

Khi conversion nằm quanh cột, index B-tree thông thường trên PRODUCT_CODE không còn khớp trực tiếp với predicate expression. Ngoài ra, nếu một hàng chứa A100 hoặc giá trị không phải số, câu SQL có thể phát sinh ORA-01722.

### 2.3. Character và DATE

So sánh DATE với chuỗi có thể khiến chuỗi được chuyển thành DATE theo NLS_DATE_FORMAT:

```sql
SELECT *
FROM orders
WHERE order_date = '14-11-2026';
```

Kết quả phụ thuộc định dạng ngày của session. Nếu session mong DD-MON-RR, chuỗi trên có thể lỗi; nếu session dùng DD-MM-YYYY, nó có thể chạy. Dùng DATE literal hoặc TO_DATE với format mask rõ ràng.

### 2.4. DATE và TIMESTAMP

DATE và TIMESTAMP có thể được chuyển đổi để hai vế có datatype tương thích. DATE không lưu fractional seconds hoặc time zone; TIMESTAMP có fractional seconds; TIMESTAMP WITH TIME ZONE có thông tin múi giờ/offset.

Khi so sánh, cần hiểu datatype được nâng/chuyển như thế nào và độ chính xác nào được giữ. Không giả định DATE và TIMESTAMP mang cùng một lượng thông tin.

### 2.5. NUMBER và binary floating point

Oracle NUMBER là kiểu số thập phân có độ chính xác cao theo giới hạn của Oracle; BINARY_FLOAT và BINARY_DOUBLE là kiểu floating point nhị phân. Khi trộn các kiểu số, Oracle có quy tắc numeric precedence. Kết quả có thể mang semantics làm tròn khác với NUMBER.

Với tiền tệ, số lượng và giá trị cần decimal semantics, dùng NUMBER với precision/scale phù hợp; tránh chuyển qua binary floating point nếu không có lý do rõ ràng.

### 2.6. Không dựa vào “Oracle tự hiểu”

Không nên dựa vào việc Oracle tự chuyển:

- Chuỗi ngày theo format mặc định.
- Chuỗi số theo dấu thập phân của session.
- Mã định danh thành số.
- NCHAR/VARCHAR2 theo character set không rõ.
- Bind text thành DATE/NUMBER trong SQL nghiệp vụ.

Hãy xác định datatype tại ranh giới ứng dụng và chuyển đổi explicit khi input thực sự là text.

## 3. Conversion ở phía nào của predicate?

### 3.1. Cột được giữ nguyên, bind/literal được chuyển

Giả sử có index trên ORDERS.ORDER_ID và ORDER_ID là NUMBER:

```sql
SELECT *
FROM orders
WHERE order_id = '12345';
```

Nếu Oracle chuyển literal thành NUMBER, predicate có dạng tương đương:

```sql
WHERE order_id = 12345
```

Cột vẫn xuất hiện trực tiếp. Index range scan có thể khả dụng nếu cost và selectivity phù hợp.

### 3.2. Conversion bọc quanh cột

Giả sử LEGACY_CODE là VARCHAR2 và index trên cột:

```sql
SELECT *
FROM legacy_items
WHERE TO_NUMBER(legacy_code) = :p_id;
```

Index thường trên LEGACY_CODE lưu giá trị character, còn predicate tìm theo biểu thức TO_NUMBER(LEGACY_CODE). Oracle không thể coi hai biểu thức là cùng một key nếu không có function-based index tương ứng hoặc transformation hợp lệ.

### 3.3. Sargability

Một predicate được gọi là sargable khi optimizer có thể dùng nó để tìm kiếm qua access path như index hoặc partition pruning thay vì phải tính biểu thức trên nhiều hàng trước khi lọc. Thuật ngữ này là cách nói thực hành; khả năng dùng index còn phụ thuộc cost, statistics, index type và toàn query.

Ví dụ sargable:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Ví dụ có function trên cột:

```sql
WHERE TRUNC(order_date) = DATE '2026-11-14'
```

Predicate thứ hai có thể cần tính TRUNC trên giá trị cột. Nếu không có function-based index tương ứng, index thường trên ORDER_DATE có thể không được dùng cho equality lookup của biểu thức TRUNC.

### 3.4. Conversion ở bind side thường dễ tối ưu hơn

Nếu cột NUMBER và ứng dụng nhận text, chuyển bind text một lần:

```sql
WHERE order_id = TO_NUMBER(:p_order_id_text)
```

Khi bind là chuỗi số hợp lệ và format được quy định, conversion nằm ở phía bind expression; cột ORDER_ID vẫn nguyên dạng. Tuy nhiên, tốt hơn nữa là ứng dụng bind trực tiếp NUMBER để tránh parse text trong database.

### 3.5. Không phải cứ thấy function là index chắc chắn mất

Oracle có thể dùng function-based index, virtual column index hoặc transformation phù hợp. Ngoài ra, optimizer có thể chọn full table scan vì cost thấp hơn. Chẩn đoán phải dựa vào predicate expression và actual execution plan, không dựa riêng vào hình thức SQL.

## 4. Implicit conversion và index access

### 4.1. Ví dụ NUMBER column

Giả sử:

```sql
CREATE TABLE lab_number_codes (
    code_id NUMBER PRIMARY KEY,
    description VARCHAR2(100)
);
```

Predicate đúng kiểu:

```sql
SELECT *
FROM lab_number_codes
WHERE code_id = :p_code_id;
```

Ứng dụng bind :p_code_id kiểu NUMBER. Optimizer có thể dùng unique index/primary key index.

### 4.2. Ví dụ VARCHAR2 column

Giả sử:

```sql
CREATE TABLE lab_text_codes (
    code VARCHAR2(30) PRIMARY KEY,
    description VARCHAR2(100)
);
```

Predicate:

```sql
SELECT *
FROM lab_text_codes
WHERE code = 100;
```

Nếu Oracle phải chuyển CODE thành NUMBER, dữ liệu 00100, 100A và 100 có thể không còn semantics phân biệt như mã ký tự. Conversion có thể lỗi ở hàng không phải số và index trên CODE có thể không được sử dụng theo access path dự kiến.

Nếu CODE là identifier, hãy bind chuỗi:

```sql
WHERE code = :p_code
```

và bind :p_code bằng VARCHAR2.

### 4.3. Join giữa hai cột khác datatype

Ví dụ:

```sql
SELECT *
FROM numeric_accounts n
JOIN legacy_accounts l
  ON n.account_id = l.account_code;
```

Nếu ACCOUNT_ID là NUMBER và ACCOUNT_CODE là VARCHAR2, Oracle có thể chuyển character side thành NUMBER. Điều này có thể:

- Bọc TO_NUMBER quanh L.ACCOUNT_CODE.
- Ngăn sử dụng index thường trên ACCOUNT_CODE cho join key.
- Gây ORA-01722 nếu dữ liệu legacy chứa ký tự không phải số.
- Làm join cardinality và cost estimate kém chính xác.

Giải pháp bền vững là chuẩn hóa datatype hai phía ở schema/ETL, không ép mọi query phải convert.

### 4.4. Join key có leading zeros

Nếu 000123 và 123 là hai mã khác nhau về nghiệp vụ, không chuyển chúng sang NUMBER. Conversion sẽ làm mất leading zeros và khiến hai key bị coi như cùng một giá trị số.

Identifier là text nên dùng character datatype ở cả hai bảng và bind string. Nếu thực sự là số học, lưu NUMBER thống nhất.

### 4.5. Implicit conversion trong UNION/CASE/COALESCE

Các biểu thức trả về nhiều kiểu dữ liệu có thể yêu cầu Oracle chọn kiểu chung:

```sql
SELECT CASE
         WHEN is_active = 'Y' THEN amount
         ELSE '0'
       END AS result_value
FROM invoices;
```

Một nhánh NUMBER, nhánh còn lại VARCHAR2. Oracle phải giải quyết datatype compatibility; conversion có thể làm lỗi hoặc khiến kiểu kết quả không như mong đợi. Viết rõ:

```sql
SELECT CASE
         WHEN is_active = 'Y' THEN amount
         ELSE 0
       END AS result_value
FROM invoices;
```

Giữ các nhánh cùng kiểu dữ liệu và explicit cast khi contract yêu cầu.

## 5. NLS là gì và ảnh hưởng tới SQL như thế nào?

### 5.1. NLS settings

NLS (National Language Support) là nhóm thiết lập ảnh hưởng cách Oracle diễn giải, định dạng và so sánh dữ liệu theo ngôn ngữ/vùng. Các setting thường gặp:

| Setting | Ảnh hưởng |
| --- | --- |
| NLS_DATE_FORMAT | Format mặc định khi chuyển DATE sang/ từ character trong một số ngữ cảnh |
| NLS_TIMESTAMP_FORMAT | Format mặc định cho TIMESTAMP |
| NLS_TIMESTAMP_TZ_FORMAT | Format mặc định cho TIMESTAMP WITH TIME ZONE |
| NLS_NUMERIC_CHARACTERS | Ký tự thập phân và phân nhóm hàng nghìn |
| NLS_DATE_LANGUAGE | Tên tháng/ngày và token ngôn ngữ trong date conversion |
| NLS_TERRITORY | Mặc định vùng, định dạng ngày/số và quy tắc liên quan |
| NLS_SORT | Quy tắc sắp xếp/so sánh ngôn ngữ |
| NLS_COMP | Chế độ so sánh ký tự |
| NLS_LENGTH_SEMANTICS | Mặc định BYTE/CHAR khi tạo cột character trong một số ngữ cảnh |

Session có thể có NLS khác nhau tùy client, connection pool và câu ALTER SESSION. Không giả định cấu hình trên máy developer giống session production.

### 5.2. Kiểm tra NLS session

```sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
```

Có thể kiểm tra database/instance parameters tương ứng bằng NLS_DATABASE_PARAMETERS hoặc NLS_INSTANCE_PARAMETERS. Khi điều tra lỗi, session parameters là điểm bắt đầu vì conversion thường chịu ảnh hưởng setting của session.

### 5.3. NLS không phải datatype

NLS_DATE_FORMAT không thay đổi cột DATE thành VARCHAR2. Nó ảnh hưởng cách biểu diễn/parse character trong một số conversion. Tương tự NLS_NUMERIC_CHARACTERS không thay đổi NUMBER thành text; nó ảnh hưởng cách dấu thập phân và dấu phân nhóm được diễn giải/định dạng.

Không dùng NLS setting làm thay thế cho datatype rõ ràng.

## 6. NLS_DATE_FORMAT và lỗi ngày tháng

### 6.1. Implicit date conversion

Ví dụ nguy hiểm:

```sql
SELECT *
FROM orders
WHERE order_date = '14-11-2026';
```

Oracle cần chuyển character literal thành DATE. Nếu NLS_DATE_FORMAT là DD-MM-YYYY, có thể parse; nếu là MM/DD/RR, chuỗi có thể lỗi hoặc mang nghĩa khác.

### 6.2. DATE literal

Dùng ANSI DATE literal cho ngày cố định:

```sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

DATE literal dùng format YYYY-MM-DD, không phụ thuộc NLS_DATE_FORMAT. DATE có cả ngày và thời gian tới giây; equality với DATE literal là nửa đêm của ngày đó, vì vậy range thường đúng hơn khi cần mọi thời điểm trong một ngày.

### 6.3. TO_DATE với format mask

Nếu input từ người dùng là text:

```sql
WHERE order_date >= TO_DATE(
    :p_start_text,
    'YYYY-MM-DD'
)
```

Nếu tháng là tên theo ngôn ngữ, chỉ rõ NLS_DATE_LANGUAGE:

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=American'
       )
FROM dual;
```

Không dựa vào tên tháng theo language mặc định của session.

### 6.4. TIMESTAMP literal

Dùng timestamp literal:

```sql
SELECT TIMESTAMP '2026-11-14 08:30:00.123456'
FROM dual;
```

Với timestamp có timezone, dùng datatype/literal phù hợp hoặc TO_TIMESTAMP_TZ với format mask và timezone rõ ràng. Không parse một instant thành DATE nếu cần giữ offset/time zone.

### 6.5. Tránh TO_CHAR trên cột DATE trong WHERE

Không nên:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-11-14'
```

Biểu thức áp dụng TO_CHAR lên từng giá trị cột và thường ngăn index range scan trực tiếp trên ORDER_DATE. Dùng range predicate:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Nếu nghiệp vụ thực sự truy vấn theo biểu thức TO_CHAR cố định, có thể xem xét function-based index nhưng cần tính cả NLS/format semantics và chi phí bảo trì.

## 7. NLS_NUMERIC_CHARACTERS và chuyển đổi số

### 7.1. Dấu thập phân và dấu phân nhóm

NLS_NUMERIC_CHARACTERS xác định ký tự thập phân và ký tự phân nhóm hàng nghìn. Ví dụ:

- ., : dấu chấm thập phân, dấu phẩy phân nhóm.
- ,. : dấu phẩy thập phân, dấu chấm phân nhóm.

Chuỗi 1,234.56 và 1.234,56 có thể biểu diễn cùng giá trị theo convention khác nhau. Nếu implicit conversion phụ thuộc NLS session, cùng một input có thể parse khác nhau hoặc lỗi.

### 7.2. TO_NUMBER với format model

Nếu chuỗi đầu vào dùng dấu chấm thập phân và dấu phẩy phân nhóm:

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

Trong format model:

- D là ký tự thập phân theo NLS_NUMERIC_CHARACTERS.
- G là ký tự phân nhóm theo NLS_NUMERIC_CHARACTERS.

Chỉ dùng format model phù hợp với input thực tế. Không cố parse dữ liệu nhiều format bằng một mask mơ hồ.

### 7.3. TO_CHAR NUMBER

Khi sinh text từ NUMBER, dùng format model và NLS parameter rõ:

```sql
SELECT TO_CHAR(
           1234.56,
           'FM999G999D00',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

TO_CHAR output là text theo format đã chọn. Nếu text được dùng để trao đổi giữa service, contract phải cố định dấu thập phân, scale và quy tắc phân nhóm.

### 7.4. Không dùng TO_CHAR rồi implicit convert lại

Pattern không tốt:

```sql
WHERE amount = TO_CHAR(:p_amount)
```

Hai vế khác kiểu; Oracle có thể phải convert ngược hoặc xử lý theo quy tắc datatype. Nếu AMOUNT là NUMBER, bind NUMBER:

```sql
WHERE amount = :p_amount
```

Nếu input là text, parse thành NUMBER ở ranh giới nhận dữ liệu rồi bind NUMBER. Tránh tạo vòng NUMBER → text → NUMBER.

### 7.5. NLS và bind string

Nếu ứng dụng bind số dưới dạng VARCHAR2, Oracle có thể chuyển text thành NUMBER theo NLS session. Hãy dùng driver API bind đúng kiểu:

- JDBC: setBigDecimal cho decimal, setLong/setInt cho integer khi phù hợp.
- ODP.NET: dùng OracleDbType.Decimal/Int32/Int64 tương ứng.
- OCI hoặc driver khác: khai báo bind datatype phù hợp.

Tên API cụ thể phụ thuộc driver, nhưng nguyên tắc là bind đúng datatype của cột và contract.

## 8. CHAR, VARCHAR2, NCHAR và NVARCHAR2

### 8.1. CHAR và VARCHAR2

CHAR có độ dài cố định và được blank-pad tới độ dài khai báo. VARCHAR2 có độ dài biến đổi. Quy tắc so sánh giữa hai biểu thức character có thể khác tùy datatype và semantics blank-padding.

Ví dụ:

```sql
CREATE TABLE lab_char_compare (
    fixed_code CHAR(5),
    variable_code VARCHAR2(5)
);

INSERT INTO lab_char_compare
VALUES ('A', 'A');
```

Không giả định CHAR và VARCHAR2 có cùng behavior khi so sánh chuỗi có trailing spaces. Khi join hoặc compare hai cột khác loại, cần hiểu conversion/blank-padding và kiểm tra dữ liệu thực.

### 8.2. NCHAR và NVARCHAR2

NCHAR/NVARCHAR2 dùng national character set. Khi so sánh với CHAR/VARCHAR2, Oracle có thể cần chuyển đổi giữa database character set và national character set. Conversion có thể ảnh hưởng CPU, khả năng biểu diễn ký tự và biểu thức predicate.

Không chọn NCHAR/NVARCHAR2 chỉ vì dữ liệu có Unicode; database character set AL32UTF8 đã hỗ trợ Unicode. Chọn datatype theo schema hiện tại, contract và chính sách character set.

### 8.3. BYTE và CHAR length semantics

VARCHAR2 có thể khai báo độ dài theo BYTE hoặc CHAR:

```sql
CREATE TABLE lab_text_lengths (
    code_byte VARCHAR2(20 BYTE),
    code_char VARCHAR2(20 CHAR)
);
```

BYTE giới hạn số byte; CHAR giới hạn số ký tự theo semantics Oracle. Với multibyte character set, 20 ký tự có thể cần hơn 20 bytes. NLS_LENGTH_SEMANTICS ảnh hưởng default khi tạo cột nếu không chỉ rõ, nhưng không thay đổi ý nghĩa của cột đã tạo.

### 8.4. So sánh giữa character sets

Nếu hai cột dùng character datatype khác nhau, conversion có thể được thực hiện theo character set compatibility. Ký tự không biểu diễn được trong đích có thể gây lỗi hoặc mất thông tin tùy đường chuyển đổi/cấu hình.

Khi thiết kế schema mới, ưu tiên database character set hỗ trợ Unicode (thường AL32UTF8) và giữ datatype nhất quán. Với hệ thống legacy, kiểm tra character set trước khi migrate hoặc cast.

## 9. NLS_SORT, NLS_COMP và collation

### 9.1. Binary và linguistic comparison

So sánh ký tự có thể dựa trên binary representation hoặc linguistic rules. Ví dụ, quy tắc không phân biệt hoa/thường hoặc dấu có thể làm các chuỗi khác byte được coi là tương đương trong một số phép so sánh/sắp xếp.

NLS_SORT xác định linguistic sort order. NLS_COMP ảnh hưởng cách áp dụng linguistic comparison trong SQL. Setting cụ thể có thể được kế thừa từ database/session và khác nhau giữa connection.

### 9.2. Kiểm tra NLS_COMP và NLS_SORT

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_COMP',
    'NLS_SORT',
    'NLS_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Không thay đổi các setting này trong production để thử nghiệm mà không đánh giá ảnh hưởng đến toàn bộ SQL chạy trên session/connection pool.

### 9.3. LINGUISTIC comparison

Khi dùng NLS_COMP = LINGUISTIC, các phép so sánh character có thể tuân theo NLS_SORT thay vì chỉ binary comparison, theo phạm vi Oracle hỗ trợ. Điều này có thể thay đổi kết quả equality, ORDER BY và access path.

Ví dụ:

```sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT *
FROM lab_names
WHERE person_name = 'smith';
```

BINARY_CI là một sort setting không phân biệt hoa/thường theo quy tắc binary case-insensitive. Hãy kiểm tra availability và semantics của sort name trên phiên bản đang dùng.

### 9.4. Vì sao index thường có thể không phù hợp?

Index B-tree thông thường trên PERSON_NAME được tạo theo biểu thức/key semantics của cột. Nếu query cần so sánh theo NLSSORT hoặc linguistic key khác với key trong index, Oracle có thể cần tính biểu thức chuyển đổi hoặc chọn full scan.

Nếu workload thường xuyên cần một quy tắc case-insensitive/linguistic cụ thể, có thể tạo function-based index theo NLSSORT expression tương ứng, hoặc dùng collation-aware design được hỗ trợ trong release.

### 9.5. Function-based index với NLSSORT

Ví dụ minh họa:

```sql
CREATE INDEX ix_lab_names_ci
ON lab_names (
    NLSSORT(person_name, 'NLS_SORT=BINARY_CI')
);
```

Predicate/query cần dùng expression tương thích:

```sql
SELECT *
FROM lab_names
WHERE NLSSORT(
          person_name,
          'NLS_SORT=BINARY_CI'
      ) = NLSSORT(
          :p_name,
          'NLS_SORT=BINARY_CI'
      );
```

Function-based index có thể hỗ trợ access path theo linguistic key. Xác nhận plan, collation rules và behavior khi nâng cấp Oracle; không trộn expression với NLS settings không nhất quán.

### 9.6. Collation ở mức column

Các phiên bản Oracle hiện đại có hỗ trợ collation ở mức column/expression trong một số cấu hình, ví dụ BINARY_CI hoặc BINARY_AI. Khả năng dùng phụ thuộc release, compatibility và MAX_STRING_SIZE/configuration. Collation declaration có thể làm semantics comparison rõ hơn thay vì đổi NLS_COMP toàn session.

Trước khi dùng, xác nhận collation được hỗ trợ cho datatype/cột/index và client. Không mặc định một cú pháp collation chạy trên mọi Oracle version.

## 10. Hàm trên cột và mất index access

### 10.1. UPPER/LOWER

Predicate:

```sql
SELECT *
FROM customers
WHERE UPPER(email) = UPPER(:p_email);
```

Index thường trên EMAIL không nhất thiết hỗ trợ equality lookup của UPPER(EMAIL). Nếu case-insensitive lookup là workload phổ biến, tạo function-based index:

```sql
CREATE INDEX ix_customers_email_upper
ON customers (UPPER(email));
```

Sau đó query dùng cùng expression. Hoặc chuẩn hóa/lưu canonical email theo một quy tắc rõ ràng, đồng thời giữ giá trị gốc nếu cần.

### 10.2. TRUNC trên DATE

Không nên mặc định:

```sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
```

Ưu tiên range:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Range predicate cho phép index range scan trên CREATED_AT và thường giúp partition pruning nếu partition key là CREATED_AT.

### 10.3. NVL/COALESCE trên cột

Predicate:

```sql
WHERE NVL(status, 'N') = 'Y'
```

Expression NVL(STATUS,'N') có thể không khớp index thường trên STATUS. Trong ví dụ này, biểu thức có thể được viết tương đương:

```sql
WHERE status = 'Y'
```

Vì NULL không bằng 'Y'. Nhưng không rewrite nếu default có semantics khác hoặc datatype conversion khác.

### 10.4. Arithmetic trên cột

Predicate:

```sql
WHERE salary + 1000 > :p_limit
```

Có thể chuyển về:

```sql
WHERE salary > :p_limit - 1000
```

Rewrite này cần chú ý overflow, NULL và numeric datatype/rounding. Với NUMBER thông thường và phép cộng tuyến tính, nó có thể giữ semantics; với kiểu floating point hoặc biểu thức phức tạp, cần xác minh.

### 10.5. CAST và TO_CHAR

CAST(column AS datatype), TO_CHAR(column) hoặc TO_NUMBER(column) đều tạo expression trên cột. Nếu index được tạo trên cột gốc, không mặc định Oracle có thể dùng nó cho biểu thức đã cast. Cân nhắc explicit conversion ở phía bind, sửa datatype schema hoặc tạo function-based index khi biểu thức là yêu cầu ổn định.

### 10.6. OR và nhiều biểu thức

Predicate có nhiều nhánh OR, function hoặc datatype khác nhau có thể làm optimizer chọn OR expansion, bitmap operation hoặc full scan. Không kết luận index mất chỉ do có OR; đọc plan để biết từng branch có access path riêng hay không.

## 11. Bind datatype và ứng dụng

### 11.1. Bind variable có datatype

Bind variable không chỉ là một placeholder chứa giá trị. Khi driver bind, nó gửi datatype, length và các thuộc tính liên quan. Nếu cột là NUMBER nhưng ứng dụng bind VARCHAR2, Oracle có thể phải chuyển đổi. Nếu cột là DATE nhưng ứng dụng bind chuỗi, conversion có thể phụ thuộc NLS.

SQL:

```sql
SELECT *
FROM orders
WHERE order_id = :p_order_id
  AND order_date >= :p_start_date;
```

Ứng dụng nên bind p_order_id là NUMBER và p_start_date là DATE/TIMESTAMP tương ứng, không phải chuỗi format ngày.

### 11.2. JDBC

Với JDBC, chọn setter tương ứng:

- setLong/setInt cho integer theo miền giá trị.
- setBigDecimal cho NUMBER decimal.
- setDate cho SQL DATE khi semantics phù hợp.
- setTimestamp cho TIMESTAMP.
- setString cho VARCHAR2/character.

Không dùng setString cho mọi bind chỉ vì input ban đầu đến từ HTTP form. Parse/validate ở application boundary, sau đó bind datatype đúng.

### 11.3. ODP.NET

Với ODP.NET, khai báo OracleDbType rõ ràng như Decimal, Int32, Date, TimeStamp hoặc Varchar2. Tránh để provider suy luận từ .NET object type khi datatype đích cần semantics chính xác.

### 11.4. Connection pool và session NLS

Connection pool tái sử dụng session. Nếu request A chạy ALTER SESSION thay NLS settings và request B nhận lại cùng physical connection, request B có thể kế thừa setting ngoài dự kiến nếu pool không reset session state.

Không dựa vào NLS session mutable cho parsing business data. Nếu phải đổi session setting, quản lý/reset rõ ràng tại pool boundary và kiểm tra các connection được tái sử dụng.

### 11.5. Bind mismatch và child cursor

Các bind có datatype/size khác nhau hoặc môi trường session không tương thích có thể ảnh hưởng cursor sharing và tạo child cursor trong một số trường hợp. Khi nhiều child cursor bất thường, xem V$SQL_SHARED_CURSOR, V$SQL và bind metadata theo quyền DBA.

Không kết luận mọi bind datatype mismatch chắc chắn tạo child cursor; đây là một yếu tố cần kiểm tra cùng bind sensitivity, optimizer environment và các lý do cursor incompatibility khác.

## 12. Explicit conversion đúng cách

### 12.1. Chuyển text thành NUMBER

Nếu input là text, parse một lần với format model rõ ràng:

```sql
SELECT TO_NUMBER(
           :p_amount_text,
           '9999999990D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
```

Sau đó bind NUMBER vào query nghiệp vụ. Không để mỗi predicate tự parse text theo session NLS.

### 12.2. Chuyển text thành DATE

```sql
SELECT TO_DATE(
           :p_date_text,
           'YYYY-MM-DD'
       )
FROM dual;
```

Nếu có tháng viết bằng chữ, thêm NLS_DATE_LANGUAGE. Nếu input có timezone, dùng TO_TIMESTAMP_TZ và format mask tương ứng; không ép thành DATE nếu cần giữ offset.

### 12.3. CAST và CONVERT

CAST dùng để chuyển datatype theo SQL type system:

```sql
SELECT CAST(:p_value AS NUMBER(12,2))
FROM dual;
```

CONVERT liên quan chuyển character set; nó không phải hàm parse date/number. Đừng nhầm CONVERT với TO_NUMBER/TO_DATE.

### 12.4. Explicit conversion vẫn có thể làm mất index

Explicit không đồng nghĩa tối ưu. Ví dụ:

```sql
WHERE TO_NUMBER(varchar_code) = :p_number
```

Vẫn bọc conversion quanh cột và có thể ngăn index thường trên VARCHAR_CODE. Mục tiêu là đặt conversion ở ranh giới phù hợp, không chỉ thêm TO_ function vào mọi biểu thức.

### 12.5. Dùng VALIDATE_CONVERSION khi phù hợp

Oracle có VALIDATE_CONVERSION trong các release hiện đại để kiểm tra một expression có chuyển được sang datatype đích hay không:

```sql
SELECT varchar_code
FROM legacy_items
WHERE VALIDATE_CONVERSION(
          varchar_code AS NUMBER
      ) = 1;
```

Hàm hữu ích trong data cleansing/staging. Không giả định predicate VALIDATE_CONVERSION sẽ làm index trên cột text trở thành numeric index; nó vẫn có thể cần đánh giá nhiều hàng.

### 12.6. DEFAULT ON CONVERSION ERROR

Một số conversion function hỗ trợ DEFAULT ... ON CONVERSION ERROR theo phiên bản, ví dụ TO_NUMBER/TO_DATE trong các release hỗ trợ:

```sql
SELECT TO_NUMBER(
           'not-a-number' DEFAULT NULL ON CONVERSION ERROR
       )
FROM dual;
```

Đây là cách chủ động chọn kết quả khi conversion thất bại. Không dùng NULL/default để âm thầm chấp nhận dữ liệu sai nếu contract yêu cầu reject.

## 13. Function-based index và virtual column

### 13.1. Khi nào dùng function-based index?

Nếu truy vấn theo một biểu thức là yêu cầu ổn định, ví dụ UPPER(email), TRUNC(order_date) hoặc NLSSORT(name), có thể tạo index trên biểu thức đó:

```sql
CREATE INDEX ix_orders_order_day
ON orders (TRUNC(order_date));
```

Query dùng cùng expression:

```sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
```

Oracle có thể sử dụng function-based index nếu expression tương thích và cost phù hợp.

### 13.2. Virtual column

Virtual column định nghĩa biểu thức ở schema:

```sql
ALTER TABLE legacy_items ADD (
    numeric_code GENERATED ALWAYS AS (
        CASE
            WHEN VALIDATE_CONVERSION(
                     varchar_code AS NUMBER
                 ) = 1
            THEN TO_NUMBER(varchar_code)
        END
    ) VIRTUAL
);

CREATE INDEX ix_legacy_items_numeric_code
ON legacy_items(numeric_code);
```

Đây là ví dụ minh họa; expression và VALIDATE_CONVERSION phải được hỗ trợ trong release. Với dữ liệu legacy, tốt hơn là làm sạch và chuẩn hóa datatype nếu nghiệp vụ thực sự là số.

### 13.3. Function-based index có chi phí

Index expression:

- Tốn storage.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Cần statistics phù hợp.
- Có thể cần rebuild khi function implementation hoặc collation assumptions thay đổi.
- Phải dùng expression tương thích trong query.

Không tạo function-based index chỉ để che một schema mismatch có thể sửa tận gốc.

### 13.4. DETERMINISTIC và user-defined function

Nếu function do người dùng định nghĩa được dùng trong function-based index, Oracle yêu cầu function được khai báo DETERMINISTIC. Người viết phải bảo đảm cùng input tạo cùng output; không phụ thuộc bảng thay đổi, SYSDATE, session NLS hoặc package state.

Không khai báo DETERMINISTIC chỉ để index compile được. Lời khai báo sai có thể làm kết quả/index không còn đúng với dữ liệu hiện tại.

### 13.5. Index expression phải khớp query

Index trên UPPER(email) không tự động hỗ trợ mọi expression khác như LOWER(TRIM(email)) hoặc NLSSORT(email,...). Hãy kiểm tra expression trong index definition và predicate trong plan. Optimizer có thể chuẩn hóa một số biểu thức tương đương, nhưng không nên giả định mọi expression được nhận diện như nhau.

## 14. Conversion và partition pruning

### 14.1. Partition key phải được dùng đúng datatype

Nếu bảng partition theo ORDER_DATE, predicate range trên cột DATE có thể cho phép partition pruning:

```sql
SELECT *
FROM partitioned_orders
WHERE order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01';
```

### 14.2. Function/conversion trên partition key

Predicate:

```sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-11'
```

có thể khiến pruning khó hơn vì expression bọc partition key. Dùng range DATE tương ứng:

```sql
WHERE order_date >= DATE '2026-11-01'
  AND order_date <  DATE '2026-12-01'
```

### 14.3. Static và dynamic pruning

Execution plan có thể hiển thị Pstart/Pstop cụ thể hoặc giá trị KEY cho dynamic pruning. Bind variable, subquery hoặc runtime expression có thể làm pruning được quyết định khi thực thi. Không chỉ nhìn Pstart/Pstop trong EXPLAIN PLAN để kết luận; xem actual cursor plan và partition statistics.

### 14.4. Conversion của bind

Nếu partition key là DATE, bind DATE giúp optimizer hiểu predicate trực tiếp. Nếu bind text, Oracle có thể implicit convert theo NLS hoặc buộc expression khác. Parse text thành DATE ở application boundary rồi bind DATE.

### 14.5. Range boundary và thời gian

Với cột TIMESTAMP hoặc TIMESTAMP WITH TIME ZONE, tạo range có datatype phù hợp. Chú ý timezone/daylight saving nếu range là ngày địa phương. Không dùng DATE literal cho một cột có semantics instant với timezone mà không định nghĩa quy tắc chuyển đổi.

## 15. Conversion và cardinality estimate

### 15.1. Optimizer cần hiểu predicate

CBO ước lượng số hàng thỏa predicate dựa trên statistics, histogram, datatype và expression. Khi predicate bọc function hoặc implicit conversion, optimizer có thể khó sử dụng statistics của cột gốc theo cách trực tiếp.

### 15.2. Histograms và skew

Nếu một cột có phân bố lệch, histogram có thể giúp ước lượng selectivity cho các giá trị cụ thể. Nhưng conversion hoặc expression có thể khiến histogram trên cột gốc không còn mô tả chính xác predicate expression.

### 15.3. Expression statistics

Với expression được dùng thường xuyên, Oracle có thể thu thập statistics liên quan function-based index/virtual column. Cân nhắc tạo virtual column hoặc function-based index để biểu thức có metadata/statistics rõ hơn.

### 15.4. Bind peeking và bind sensitivity

Một query có bind value khác nhau có thể có selectivity khác nhau. Nếu bind datatype không nhất quán hoặc NLS environment thay đổi, ngoài vấn đề conversion còn có thể có nhiều child cursor hoặc plan khác nhau. Kiểm tra actual child cursor và bind metadata thay vì giả định một plan dùng cho mọi request.

### 15.5. Không dùng hint để che conversion sai

INDEX hint không sửa được semantics conversion, dữ liệu không hợp lệ hoặc predicate không sargable. Sửa datatype/bind/expression trước, sau đó đánh giá access path và statistics.

## 16. Đọc execution plan để tìm implicit conversion

### 16.1. Predicate Information

DBMS_XPLAN có thể hiển thị conversion trong Predicate Information. Ví dụ một predicate trên VARCHAR2 bị chuyển sang NUMBER có thể hiện biểu thức tương tự:

```text
filter(TO_NUMBER("L"."ACCOUNT_CODE")=:B1)
```

Đây là dấu hiệu conversion được áp dụng trên cột ACCOUNT_CODE. Nếu index thông thường trên ACCOUNT_CODE, predicate này không khớp trực tiếp với key character.

### 16.2. DISPLAY_CURSOR

Sau khi chạy SQL, xem cursor thực tế:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +PEEKED_BINDS'
    )
);
```

ALLSTATS LAST hữu ích khi runtime row-source statistics được thu thập. PEEKED_BINDS có thể cho thấy bind values được peek ở hard parse nếu thông tin khả dụng; nó không phải bản ghi đầy đủ mọi bind của mọi execution.

### 16.3. ACCESS và FILTER predicates

Trong plan:

- ACCESS predicate thường tham gia xác định key/range cho access operation.
- FILTER predicate được đánh giá để loại hàng ở operation tương ứng.

Một predicate nằm trong FILTER không tự động xấu. Điều cần tìm là conversion/function nào đang được áp dụng, operation nào xử lý nó và có làm tăng số hàng phải đọc hay không.

### 16.4. Index range scan không phải mục tiêu tuyệt đối

Ngay cả predicate sargable cũng có thể dẫn đến TABLE ACCESS FULL nếu phần lớn bảng được chọn, bảng nhỏ hoặc full scan rẻ hơn. Đánh giá:

- E-Rows và A-Rows.
- Buffers, physical reads và elapsed time.
- Index clustering factor và selectivity.
- Predicate Information.
- Partition pruning.
- Bind values và child cursor.

Không ép index chỉ vì query có predicate equality.

### 16.5. EXPLAIN PLAN và actual cursor plan

EXPLAIN PLAN cho biết estimated plan trong ngữ cảnh explain. Nó có thể khác plan runtime do bind values, session settings, adaptive features, child cursor hoặc environment. Dùng DISPLAY_CURSOR để xem cursor thực tế mà ứng dụng chạy khi điều tra production.

## 17. Lỗi thường gặp do conversion

| Lỗi | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| ORA-01722: invalid number | Character value không chuyển được thành NUMBER | Tìm dữ liệu lỗi, validate staging, sửa datatype/bind |
| ORA-01843: not a valid month | Chuỗi ngày không khớp format/language | TO_DATE với mask và NLS_DATE_LANGUAGE rõ |
| ORA-01861: literal does not match format string | Input không khớp format mask | Chuẩn hóa format producer và parser |
| ORA-01830: date format picture ends before converting entire input string | Format mask ngắn hơn input | Sửa mask hoặc input contract |
| ORA-06502: numeric or value error | Buffer/precision/conversion không phù hợp | Kiểm tra datatype, length, precision và conversion |
| ORA-01481: invalid number format model | Format model TO_CHAR/TO_NUMBER sai | Kiểm tra format model theo datatype |
| ORA-00932: inconsistent datatypes | Biểu thức trộn datatype không tương thích | CAST rõ và thống nhất datatype các nhánh |
| ORA-01426: numeric overflow | Kết quả conversion/toán vượt miền NUMBER | Kiểm tra precision, scale và input bounds |
| Index range scan biến mất | Predicate bọc function/conversion quanh cột | Chuyển đổi bind side, sửa schema hoặc FBI |
| Partition pruning kém | Function/conversion trên partition key | Dùng range predicate đúng datatype |
| Kết quả khác giữa môi trường | NLS settings khác nhau | Dùng explicit format/NLS parameter và bind đúng kiểu |

### 17.1. ORA-01722 không nhất thiết chỉ ra dòng lỗi

Nếu query có nhiều predicate, optimizer có thể thay đổi thứ tự đánh giá. Không dựa vào điều kiện kiểm tra chuỗi là numeric được viết trước để bảo đảm TO_NUMBER chỉ chạy với dữ liệu hợp lệ.

Không an toàn:

```sql
WHERE REGEXP_LIKE(code, '^[0-9]+$')
  AND TO_NUMBER(code) = :p_number
```

Optimizer không cam kết đánh giá REGEXP_LIKE trước TO_NUMBER. Hãy chuẩn hóa dữ liệu trước, dùng conversion có xử lý lỗi trong staging hoặc dùng CASE để kiểm soát biểu thức:

```sql
WHERE CASE
          WHEN VALIDATE_CONVERSION(code AS NUMBER) = 1
          THEN TO_NUMBER(code)
      END = :p_number
```

Đây là cách biểu diễn điều kiện an toàn hơn về conversion; nó vẫn có thể cần scan và không thay thế việc làm sạch schema.

### 17.2. Tìm dữ liệu không chuyển được

```sql
SELECT code
FROM legacy_items
WHERE VALIDATE_CONVERSION(code AS NUMBER) = 0;
```

Nếu release không hỗ trợ VALIDATE_CONVERSION, dùng phương án kiểm tra dữ liệu phù hợp với version hoặc xử lý tại ETL/application. Không dùng TO_NUMBER trực tiếp trên mọi hàng chỉ để tìm lỗi vì chính truy vấn có thể dừng bằng ORA-01722.

## 18. Thiết kế schema để tránh conversion

### 18.1. Một business attribute, một datatype chuẩn

Nếu account_id là số học, dùng NUMBER nhất quán ở các bảng liên quan. Nếu account_code là mã định danh, dùng VARCHAR2 nhất quán. Không để cùng một thuộc tính là NUMBER ở bảng A và VARCHAR2 ở bảng B chỉ vì một bảng cũ nhận dữ liệu từ file text.

### 18.2. Chuẩn hóa dữ liệu tại ingress

Ở tầng nhận dữ liệu:

1. Kiểm tra format input.
2. Parse thành datatype đích.
3. Reject giá trị sai hoặc lưu staging để sửa.
4. Bind typed value vào DML.
5. Ghi raw input/hash nếu cần audit theo policy.

Không để mọi query nghiệp vụ tự parse cùng một cột legacy.

### 18.3. Tách raw và canonical value

Nếu cần giữ nguyên chuỗi người dùng gửi và đồng thời cần giá trị chuẩn hóa để join/search, có thể lưu hai cột:

```sql
CREATE TABLE lab_external_ids (
    raw_id VARCHAR2(100),
    canonical_id VARCHAR2(100)
);
```

Quy tắc canonicalization phải rõ và ổn định. Không chuẩn hóa ID sang NUMBER nếu leading zeros hoặc chữ cái có ý nghĩa.

### 18.4. Virtual column cho legacy data

Nếu chưa thể thay schema, virtual column hoặc staging normalized column có thể tạo một datatype canonical cho query. Cần xử lý giá trị lỗi bằng CASE/VALIDATE_CONVERSION và index đúng expression.

### 18.5. Constraints và data quality

Constraint NOT NULL, CHECK, FK và unique constraint giúp optimizer có metadata và bảo vệ dữ liệu. Tuy nhiên, CHECK constraint không nên dùng conversion có thể lỗi với mọi hàng; validate input trước khi insert và giữ domain constraint đơn giản.

### 18.6. Migration datatype

Khi đổi VARCHAR2 sang NUMBER:

- Profile toàn bộ dữ liệu trước.
- Xác định leading zeros, dấu, whitespace và format.
- Xử lý duplicate sau normalization.
- Tạo cột mới hoặc staging để backfill.
- Validate số hàng và giá trị.
- Cập nhật application binds và joins.
- Tạo index/constraints mới.
- Chuyển read/write theo kế hoạch rollback.

Không ALTER datatype trực tiếp khi chưa biết toàn bộ dữ liệu và dependency.

## 19. Bài thực hành: nhận diện conversion làm mất index

Các ví dụ chạy trong schema lab. Dùng schema riêng; không tạo hoặc thay đổi index trên bảng production.

### 19.1. Tạo dữ liệu numeric key

```sql
CREATE TABLE lab_conv_number (
    id NUMBER PRIMARY KEY,
    description VARCHAR2(100)
);

INSERT INTO lab_conv_number
SELECT level, 'Row ' || level
FROM dual
CONNECT BY level <= 10000;
COMMIT;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_CONV_NUMBER',
        cascade => TRUE
    );
END;
/
```

### 19.2. So sánh bind đúng kiểu và literal text

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_number
WHERE id = 500;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE'
    )
);
```

Thử:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_number
WHERE id = '500';
```

Quan sát Predicate Information. Nếu Oracle chuyển literal sang NUMBER và giữ cột ID nguyên dạng, index vẫn có thể được dùng.

### 19.3. Tạo bảng text numeric

```sql
CREATE TABLE lab_conv_text (
    code VARCHAR2(20) PRIMARY KEY,
    description VARCHAR2(100)
);

INSERT INTO lab_conv_text
SELECT TO_CHAR(level, 'FM00000'), 'Code ' || level
FROM dual
CONNECT BY level <= 10000;

INSERT INTO lab_conv_text VALUES ('A100', 'Invalid numeric code');
COMMIT;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_CONV_TEXT',
        cascade => TRUE
    );
END;
/
```

### 19.4. Predicate sai kiểu

```sql
SELECT *
FROM lab_conv_text
WHERE code = 100;
```

Oracle có thể cố chuyển CODE thành NUMBER và gặp ORA-01722 do hàng A100. Thử truy vấn chỉ trên dữ liệu numeric không đủ để chứng minh query an toàn; optimizer có thể đọc hàng khác tùy plan.

### 19.5. Predicate đúng kiểu

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM lab_conv_text
WHERE code = '00100';
```

Predicate so sánh character với character và có thể dùng primary key index. Kết quả giữ semantics leading zeros.

### 19.6. So sánh function-based index

Trong schema lab, nếu nghiệp vụ thật sự cần numeric interpretation:

```sql
CREATE INDEX ix_lab_conv_text_num
ON lab_conv_text (TO_NUMBER(code));
```

Với dữ liệu có A100, việc tạo index expression có thể thất bại do conversion lỗi. Đây là minh họa tại sao không nên chữa schema bằng function-based index trước khi làm sạch dữ liệu. Không tiếp tục dùng TO_NUMBER trên cột nếu chưa xác định tất cả giá trị hợp lệ.

## 20. Bài thực hành: NLS date và numeric

### 20.1. Thay đổi NLS_DATE_FORMAT trong session lab

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MM-YYYY';

SELECT TO_DATE('14-11-2026')
FROM dual;
```

Thay đổi format:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'MM/DD/YYYY';

SELECT TO_DATE('14-11-2026')
FROM dual;
```

Conversion thứ hai có thể lỗi vì input không phù hợp. Thử DATE literal:

```sql
SELECT DATE '2026-11-14'
FROM dual;
```

Kết quả không phụ thuộc NLS_DATE_FORMAT.

### 20.2. Thay đổi NLS_NUMERIC_CHARACTERS

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
SELECT TO_NUMBER('1,234.56', '9G999D99')
FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
SELECT TO_NUMBER('1.234,56', '9G999D99')
FROM dual;
```

Quan sát cách D và G được diễn giải. Khi viết code ứng dụng, chỉ rõ format model và NLS parameter thay vì phụ thuộc ALTER SESSION.

### 20.3. Khôi phục session

Trong SQL Developer hoặc SQL*Plus, đóng session lab hoặc đặt lại NLS settings theo cấu hình ban đầu. Nếu dùng connection pool, không để session state thay đổi lan sang request khác.

## 21. Bài thực hành: case-insensitive lookup và NLS_SORT

### 21.1. Tạo dữ liệu

```sql
CREATE TABLE lab_names (
    person_id NUMBER PRIMARY KEY,
    person_name VARCHAR2(100)
);

INSERT INTO lab_names VALUES (1, 'Smith');
INSERT INTO lab_names VALUES (2, 'SMITH');
INSERT INTO lab_names VALUES (3, 'smith');
INSERT INTO lab_names VALUES (4, 'Smyth');
COMMIT;

CREATE INDEX ix_lab_names_name
ON lab_names(person_name);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_NAMES',
        cascade => TRUE
    );
END;
/
```

### 21.2. Binary equality

```sql
SELECT person_id, person_name
FROM lab_names
WHERE person_name = 'smith';
```

Kết quả phụ thuộc binary/collation semantics đang áp dụng. Không giả định ba cách viết hoa/thường đều match.

### 21.3. UPPER expression

```sql
SELECT person_id, person_name
FROM lab_names
WHERE UPPER(person_name) = UPPER('smith');
```

Kết quả có thể match Smith, SMITH và smith. Xem plan với index thường trên PERSON_NAME; expression UPPER có thể cần full scan nếu chưa có index phù hợp.

### 21.4. Function-based index

```sql
CREATE INDEX ix_lab_names_upper
ON lab_names(UPPER(person_name));

SELECT /*+ GATHER_PLAN_STATISTICS */
       person_id, person_name
FROM lab_names
WHERE UPPER(person_name) = UPPER(:p_name);
```

Kiểm tra actual plan và statistics. Với bảng lab rất nhỏ, optimizer vẫn có thể chọn full scan vì cost; có thể tăng dữ liệu thử nghiệm để quan sát access path rõ hơn.

### 21.5. Dùng NLSSORT

Thử expression NLSSORT với một sort rule cụ thể và so sánh plan/kết quả. Đảm bảo index expression và query expression giống nhau, và không dùng NLS setting thay đổi theo request nếu index được thiết kế theo một rule cố định.

## 22. Chẩn đoán datatype của cột và bind

### 22.1. Xem datatype cột

```sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    data_precision,
    data_scale
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

Thông tin này giúp xác nhận cột thực tế là NUMBER, DATE, TIMESTAMP, VARCHAR2 hay NCHAR/NVARCHAR2 và độ dài theo BYTE/CHAR.

### 22.2. Xem datatype của bind trong cursor

Thông tin bind có thể được xem qua các dynamic performance views như V$SQL_BIND_CAPTURE, nếu có quyền. Bind capture không ghi nhận mọi bind ở mọi execution và có thể bị giới hạn theo sampling/cursor behavior.

```sql
SELECT
    sql_id,
    name,
    position,
    datatype_string,
    value_string,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY position;
```

Không log giá trị bind nhạy cảm nếu chưa mask. Với dữ liệu production, quyền xem V$SQL_BIND_CAPTURE cần được kiểm soát.

### 22.3. Tìm SQL có conversion trong plan

DBA có thể tìm cursor plan có biểu thức TO_NUMBER/TO_DATE/TO_CHAR trong Predicate Information bằng cách truy vấn V$SQL_PLAN hoặc đọc DBMS_XPLAN. Ví dụ:

```sql
SELECT
    sql_id,
    child_number,
    operation,
    options,
    object_name,
    access_predicates,
    filter_predicates
FROM v$sql_plan
WHERE UPPER(access_predicates) LIKE '%TO_NUMBER%'
   OR UPPER(filter_predicates) LIKE '%TO_NUMBER%'
   OR UPPER(access_predicates) LIKE '%TO_DATE%'
   OR UPPER(filter_predicates) LIKE '%TO_DATE%';
```

Đây là truy vấn điều tra sơ bộ; expression có thể bị lưu ở dạng khác và view có thể chứa nhiều cursor. Không xem kết quả là danh sách đầy đủ mọi implicit conversion.

### 22.4. Kiểm tra NLS ở ứng dụng

Ghi nhận session NLS metadata trong diagnostic khi có lỗi phụ thuộc môi trường. Không nhất thiết log toàn bộ NLS mỗi request; có thể log khi mở connection hoặc khi phát hiện conversion error. Đảm bảo connection pool reset state.

## 23. Lỗi thường gặp và hướng xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-01722: invalid number | Character value không chuyển được thành NUMBER | Tìm dữ liệu lỗi, validate staging, sửa datatype/bind |
| ORA-01843: not a valid month | Chuỗi ngày không khớp format/language | TO_DATE với mask và NLS_DATE_LANGUAGE rõ |
| ORA-01861: literal does not match format string | Input không khớp format mask | Chuẩn hóa format producer và parser |
| ORA-01830 | Format mask ngắn hơn input | Sửa mask hoặc input contract |
| ORA-06502 | Buffer/precision/conversion không phù hợp | Kiểm tra datatype, length, precision và conversion |
| ORA-01481 | Format model TO_CHAR/TO_NUMBER sai | Kiểm tra format model theo datatype |
| ORA-00932: inconsistent datatypes | Biểu thức trộn datatype không tương thích | CAST rõ và thống nhất datatype các nhánh |
| ORA-01426: numeric overflow | Kết quả conversion/toán vượt miền NUMBER | Kiểm tra precision, scale và input bounds |
| Index range scan biến mất | Predicate bọc function/conversion quanh cột | Chuyển đổi bind side, sửa schema hoặc FBI |
| Partition pruning kém | Function/conversion trên partition key | Dùng range predicate đúng datatype |
| Kết quả khác giữa môi trường | NLS settings khác nhau | Dùng explicit format/NLS parameter và bind đúng kiểu |
| Nhiều child cursor | Bind metadata hoặc optimizer environment không tương thích | Kiểm tra V$SQL_SHARED_CURSOR và bind types |

### 23.1. ORA-01722 không nhất thiết chỉ ra dòng lỗi

Nếu query có nhiều predicate, optimizer có thể thay đổi thứ tự đánh giá. Không dựa vào điều kiện kiểm tra chuỗi là numeric được viết trước để bảo đảm TO_NUMBER chỉ chạy với dữ liệu hợp lệ.

Không an toàn:

```sql
WHERE REGEXP_LIKE(code, '^[0-9]+$')
  AND TO_NUMBER(code) = :p_number
```

Optimizer không cam kết đánh giá REGEXP_LIKE trước TO_NUMBER. Hãy chuẩn hóa dữ liệu trước, dùng conversion có xử lý lỗi trong staging hoặc dùng CASE để kiểm soát biểu thức:

```sql
WHERE CASE
          WHEN VALIDATE_CONVERSION(code AS NUMBER) = 1
          THEN TO_NUMBER(code)
      END = :p_number
```

Đây là cách biểu diễn điều kiện an toàn hơn về conversion; nó vẫn có thể cần scan và không thay thế việc làm sạch schema.

### 23.2. Tìm dữ liệu không chuyển được

```sql
SELECT code
FROM legacy_items
WHERE VALIDATE_CONVERSION(code AS NUMBER) = 0;
```

Nếu release không hỗ trợ VALIDATE_CONVERSION, dùng phương án kiểm tra dữ liệu phù hợp với version hoặc xử lý tại ETL/application. Không dùng TO_NUMBER trực tiếp trên mọi hàng chỉ để tìm lỗi vì chính truy vấn có thể dừng bằng ORA-01722.

## 24. Nguyên tắc thực hành tốt

1. **Khai báo datatype nhất quán.** Cùng một business attribute nên có cùng kiểu trên các bảng liên quan.
2. **Bind đúng kiểu.** NUMBER bind NUMBER, DATE bind DATE, TIMESTAMP bind TIMESTAMP và text bind character.
3. **Parse text ở ranh giới.** Dùng TO_NUMBER/TO_DATE với format mask và NLS parameter rõ ràng.
4. **Tránh implicit date/number conversion.** Không phụ thuộc NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS.
5. **Giữ cột nguyên dạng trong predicate khi có thể.** Chuyển đổi bind/literal thay vì bọc function quanh indexed column.
6. **Dùng range predicate cho ngày.** Tránh TRUNC/TO_CHAR trên cột DATE nếu có thể biểu diễn bằng khoảng.
7. **Giữ identifier là character.** Không chuyển mã có leading zeros hoặc chữ cái thành NUMBER.
8. **Kiểm tra join key.** Tránh join NUMBER với VARCHAR2 và conversion trên một phía.
9. **Hiểu NLS_COMP/NLS_SORT.** Linguistic comparison có thể cần NLSSORT/FBI hoặc collation phù hợp.
10. **Dùng function-based index có chọn lọc.** Chỉ tạo khi expression là workload ổn định và có lợi.
11. **Làm sạch dữ liệu legacy.** Không dùng conversion trong mọi query để bù cho cột chứa nhiều kiểu giá trị.
12. **Kiểm tra partition pruning.** Predicate phải phù hợp datatype/partition key.
13. **Đọc Predicate Information.** Tìm TO_NUMBER, TO_DATE, TO_CHAR, CAST và expression quanh cột.
14. **So sánh actual plan.** Xem A-Rows, E-Rows, buffers và runtime, không chỉ EXPLAIN PLAN.
15. **Theo dõi session NLS.** Connection pool phải quản lý session state nhất quán.
16. **Không dùng hint để che lỗi datatype.** Sửa semantics và expression trước khi ép access path.
17. **Kiểm thử nhiều NLS profiles.** Cùng payload phải cho cùng kết quả theo contract.
18. **Kiểm tra sau upgrade.** Conversion, collation và optimizer behavior có thể khác theo release.

## 25. Câu hỏi tự kiểm tra

1. Implicit conversion là gì và vì sao nó có thể làm SQL khó dự đoán?
2. Khi so sánh NUMBER column với character literal, Oracle thường chuyển phía nào?
3. Vì sao so sánh VARCHAR2 column với NUMBER có thể tạo TO_NUMBER(column)?
4. Conversion ở bind side khác conversion quanh indexed column như thế nào?
5. Sargability có nghĩa gì?
6. Vì sao mã 000123 không nên chuyển thành NUMBER nếu leading zeros có ý nghĩa?
7. NLS_DATE_FORMAT ảnh hưởng implicit date conversion ra sao?
8. DATE literal khác TO_DATE string như thế nào?
9. Vì sao equality với DATE literal chỉ match thời điểm nửa đêm?
10. NLS_NUMERIC_CHARACTERS quy định điều gì?
11. D và G trong number format model có ý nghĩa gì?
12. Vì sao nên bind NUMBER thay vì bind text chứa số?
13. CHAR và VARCHAR2 khác nhau về blank-padding thế nào?
14. NCHAR/NVARCHAR2 liên quan national character set ra sao?
15. BYTE và CHAR length semantics khác nhau thế nào?
16. NLS_SORT và NLS_COMP ảnh hưởng comparison như thế nào?
17. Vì sao index thường có thể không phù hợp với linguistic comparison?
18. Function-based index hỗ trợ UPPER/LOWER/NLSSORT như thế nào?
19. Vì sao TRUNC(date_column) có thể cản index range scan?
20. Viết range predicate nào để lọc toàn bộ một ngày?
21. Implicit conversion có thể ảnh hưởng partition pruning ra sao?
22. Vì sao conversion và expression có thể làm cardinality estimate kém chính xác?
23. DISPLAY_CURSOR khác EXPLAIN PLAN như thế nào?
24. Predicate Information giúp nhận diện conversion ra sao?
25. Vì sao REGEXP_LIKE trước TO_NUMBER trong WHERE không bảo đảm thứ tự đánh giá?
26. Khi nào dùng VALIDATE_CONVERSION?
27. Khi nào nên sửa schema thay vì tạo function-based index?
28. Connection pool có thể làm NLS session state rò giữa request như thế nào?

## 26. Mô hình ghi nhớ

```text
PREDICATE SQL
    |
    v
  SO SÁNH DATATYPE
    |
    +-- NUMBER vs CHARACTER
    +-- DATE/TIMESTAMP vs CHARACTER
    +-- CHAR/VARCHAR2/NCHAR
    +-- BINARY vs LINGUISTIC COLLATION
    |
    v
  IMPLICIT CONVERSION
    |
    +-- Phụ thuộc NLS
    +-- Có thể lỗi dữ liệu
    +-- Có thể bọc function quanh cột
    |
    v
  INDEX / PARTITION ACCESS
    |
    +-- Cột nguyên dạng + bind đúng type
    |      -> access path thường khả dụng
    |
    +-- TO_NUMBER(column), TRUNC(column), UPPER(column)
           -> index thường có thể không khớp expression
           -> xem xét range rewrite / FBI / virtual column
    |
    v
  DIAGNOSTICS
    |
    +-- NLS_SESSION_PARAMETERS
    +-- USER_TAB_COLUMNS / bind metadata
    +-- DBMS_XPLAN Predicate Information
    +-- A-Rows / E-Rows / Starts / buffers
```

**Điểm cần nhớ:** implicit conversion có thể đổi semantics, phụ thuộc NLS và làm predicate mất tính sargable. Giữ datatype nhất quán, bind đúng kiểu, parse text bằng format/NLS tường minh, giữ indexed column nguyên dạng khi có thể và xác nhận bằng actual execution plan.
