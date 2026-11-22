# Bao phủ NULL, chuỗi rỗng, số âm và giá trị biên

Một truy vấn SQL có thể chạy đúng với dữ liệu thông thường nhưng sai khi gặp **NULL, chuỗi rỗng, số âm, số 0, giá trị sát giới hạn kiểu dữ liệu hoặc dữ liệu có định dạng đặc biệt**. Dữ liệu mẫu thường chỉ gồm tên không rỗng, số dương nhỏ, ngày ở giữa tháng và khóa luôn tồn tại, nên các lỗi biên dễ bị bỏ sót.

Bài này trình bày cách xây dựng bộ kiểm thử biên cho database: xác định miền giá trị hợp lệ, tạo ma trận đầu vào, kiểm tra ngữ nghĩa NULL, chuỗi, số và ngày giờ, xác nhận constraint, transaction và hành vi của các DBMS khác nhau.

Các nhóm cần bao phủ:

- **NULL:** giá trị không có/không xác định, logic ba giá trị, aggregate, JOIN, UNIQUE và CHECK.
- **Chuỗi rỗng:** empty string, chuỗi chỉ có khoảng trắng, tab, newline, Unicode và giới hạn độ dài.
- **Số âm và giá trị biên:** số âm nhỏ nhất, zero, số dương nhỏ nhất, MIN/MAX của kiểu, vượt miền, overflow, scale và rounding.
- **Ngày giờ:** đầu/cuối miền hỗ trợ, thời điểm sát ranh giới, độ chính xác, timezone và khoảng thời gian.
- **Tính toàn vẹn:** NOT NULL, CHECK, UNIQUE, FOREIGN KEY, DEFAULT và trigger.
- **Kiểm thử thực thi:** bind parameter, rollback, concurrency, property-based test và fuzzing.

Bài thuộc **Database SQL → Kiểm thử và gỡ lỗi → Bao phủ NULL, chuỗi rỗng, số âm và giá trị biên**. Ví dụ chính dùng PostgreSQL để minh họa; khác biệt quan trọng của SQL Server, MySQL, Oracle và SQLite được ghi riêng. Cần chạy test trên đúng DBMS và phiên bản ứng dụng đang sử dụng.

---

## 1. Vì sao phải kiểm thử giá trị biên?

Giả sử ứng dụng tính tiền:

```sql
SELECT quantity * unit_price AS line_total
FROM order_items;
```

Với quantity = 2 và unit_price = 10.00, kết quả là 20.00. Nhưng điều gì xảy ra khi quantity là NULL, bằng 0, bằng -2, unit_price có scale vượt quá cột DECIMAL, phép nhân vượt giới hạn kiểu kết quả, hoặc ứng dụng gửi chuỗi rỗng vào cột số?

Nếu chỉ test một giá trị dương thông thường, ta chưa kiểm tra được những quy tắc này.

### 1.1. Boundary value analysis

Giá trị biên là giá trị nằm tại hoặc sát ranh giới miền hợp lệ. Với miền số nguyên từ 1 đến 100, tập kiểm thử cơ bản nên có:

| Nhóm | Giá trị | Mục tiêu |
| --- | ---: | --- |
| Dưới min | 0 | Phải bị từ chối nếu miền là 1..100 |
| Min | 1 | Giá trị hợp lệ nhỏ nhất |
| Ngay trên min | 2 | Kiểm tra lân cận |
| Giá trị giữa | 50 | Hành vi bình thường |
| Ngay dưới max | 99 | Kiểm tra lân cận |
| Max | 100 | Giá trị hợp lệ lớn nhất |
| Trên max | 101 | Phải bị từ chối |
| Số âm | -1 | Kiểm tra dấu |
| NULL | NULL | Kiểm tra optional/required |
| Sai định dạng | abc | Kiểm tra chuyển kiểu |

### 1.2. Biên nghiệp vụ và biên kiểu dữ liệu

Có hai loại giới hạn:

- **Biên nghiệp vụ:** ví dụ tuổi phải từ 0 đến 120, quantity phải lớn hơn 0, discount không vượt 50%.
- **Biên kỹ thuật:** ví dụ cột SMALLINT, DECIMAL(8,2), VARCHAR(30), giới hạn timestamp của DBMS.

Một giá trị có thể nằm trong miền kiểu SQL nhưng vi phạm nghiệp vụ. Ví dụ quantity = -1 hợp lệ với kiểu INTEGER nhưng có thể bị CHECK từ chối.

Ngược lại, giá trị nghiệp vụ có thể hợp lệ nhưng không biểu diễn được bằng kiểu đã chọn. Ví dụ số tiền có nhiều chữ số hơn scale của DECIMAL.

### 1.3. Bốn kết quả cần kiểm tra

Mỗi test biên nên xác định rõ:

1. Đầu vào được chấp nhận hay bị từ chối?
2. Giá trị được lưu chính xác hay bị chuyển đổi/round?
3. Số hàng bị tác động là bao nhiêu?
4. Transaction và dữ liệu liên quan có ở trạng thái đúng sau thành công/lỗi không?

Chỉ kiểm tra “query không ném exception” là chưa đủ. DBMS có thể âm thầm chuyển đổi dữ liệu theo SQL mode hoặc kiểu dữ liệu.

---

## 2. Tạo bảng lab để thực hành

Tạo bảng thử nghiệm riêng trong database/schema lab:

```sql
CREATE TABLE lab_boundary_417 (
    test_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    required_text VARCHAR(20) NOT NULL,
    optional_text VARCHAR(20),
    quantity      INTEGER NOT NULL CHECK (quantity BETWEEN 0 AND 100),
    amount        NUMERIC(8, 2) NOT NULL CHECK (amount >= 0),
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Bảng này có các quy tắc:

- required_text: không được SQL NULL.
- optional_text: cho phép SQL NULL.
- quantity: bắt buộc từ 0 đến 100.
- amount: bắt buộc, không âm, có tối đa 8 chữ số tổng cộng và 2 chữ số thập phân.
- note: cho phép NULL và chuỗi rỗng.
- created_at: tự nhận DEFAULT nếu INSERT không cung cấp cột.

Một INSERT hợp lệ:

```sql
INSERT INTO lab_boundary_417 (
    required_text, optional_text, quantity, amount, note
)
VALUES (
    'valid', NULL, 0, 0.00, ''
);
```

Trong PostgreSQL, hàng này hợp lệ: optional_text là SQL NULL; quantity và amount bằng 0; note là empty string khác NULL.

Một INSERT vi phạm:

```sql
INSERT INTO lab_boundary_417 (
    required_text, optional_text, quantity, amount
)
VALUES (
    'bad', NULL, -1, 10.00
);
```

Câu lệnh bị CHECK từ chối vì quantity âm. Không nên sửa dữ liệu đầu vào thành 0 một cách âm thầm nếu nghiệp vụ yêu cầu từ chối.

Các lệnh tạo bảng trên dùng kiểu identity và TIMESTAMPTZ của PostgreSQL. Khi thực hành trên hệ khác, tạo bảng tương đương theo kiểu và cú pháp của DBMS đó.

---

## 3. NULL không phải chuỗi rỗng, số 0 hay DEFAULT

NULL trong SQL biểu diễn giá trị không có/không xác định theo ngữ nghĩa của cột. Nó khác:

| Giá trị | Ý nghĩa |
| --- | --- |
| SQL NULL | Null marker |
| Empty string | Chuỗi có độ dài 0, nếu DBMS phân biệt |
| Một dấu cách | Chuỗi có một ký tự space |
| 0 | Số không |
| FALSE | Boolean false |
| DEFAULT | Giá trị mặc định do schema/câu lệnh cung cấp |

Không nên tự coi các giá trị này là tương đương.

### 3.1. So sánh NULL bằng IS NULL

Không viết:

```sql
SELECT *
FROM lab_boundary_417
WHERE optional_text = NULL;
```

Phép so sánh với NULL tạo UNKNOWN, không phải TRUE. Dùng:

```sql
SELECT *
FROM lab_boundary_417
WHERE optional_text IS NULL;
```

Và để tìm giá trị khác NULL:

```sql
WHERE optional_text IS NOT NULL
```

### 3.2. SQL dùng logic ba giá trị

Điều kiện SQL có thể là TRUE, FALSE hoặc UNKNOWN.

```sql
SELECT
    NULL = NULL AS equal_null,
    NULL <> 5 AS not_equal_five,
    NULL IS NULL AS is_null;
```

Hai biểu thức đầu cho UNKNOWN; biểu thức cuối cho TRUE.

Trong WHERE, chỉ hàng có điều kiện TRUE được giữ. FALSE và UNKNOWN đều bị loại.

| Biểu thức | Kết quả logic | WHERE giữ hàng? |
| --- | --- | --- |
| 5 = 5 | TRUE | Có |
| 5 = 6 | FALSE | Không |
| NULL = 5 | UNKNOWN | Không |
| NULL <> 5 | UNKNOWN | Không |
| NULL IS NULL | TRUE | Có |
| NULL IS NOT NULL | FALSE | Không |

Đây là lý do test NULL phải bao gồm phép so sánh, IS NULL, IS NOT NULL, AND, OR và NOT.

### 3.3. NOT có thể làm kết quả bất ngờ

```sql
SELECT *
FROM lab_boundary_417
WHERE NOT (optional_text = 'blocked');
```

Nếu optional_text là NULL, biểu thức bên trong là UNKNOWN; NOT UNKNOWN vẫn UNKNOWN, nên hàng không được trả về.

Nếu yêu cầu là “lấy mọi hàng trừ hàng có text bằng blocked, bao gồm cả NULL”, phải viết rõ:

```sql
WHERE optional_text IS NULL
   OR optional_text <> 'blocked';
```

Đừng giả định NOT tự biến UNKNOWN thành TRUE.

### 3.4. NULL trong AND và OR

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Ví dụ:

```sql
SELECT *
FROM lab_boundary_417
WHERE quantity > 0
  AND optional_text <> 'blocked';
```

Nếu quantity > 0 là TRUE nhưng optional_text NULL, toàn điều kiện là UNKNOWN và hàng bị loại. Đây có thể đúng hoặc sai tùy yêu cầu nghiệp vụ; phải viết test xác nhận.

---

## 4. COALESCE, NULLIF và DEFAULT

### 4.1. COALESCE

COALESCE(a, b, c) trả biểu thức đầu tiên khác NULL:

```sql
SELECT COALESCE(optional_text, '(not provided)')
FROM lab_boundary_417;
```

COALESCE xử lý NULL, không xử lý chuỗi rỗng trong PostgreSQL, SQL Server, MySQL và SQLite. Nếu optional_text = empty string, kết quả vẫn là empty string.

### 4.2. NULLIF

NULLIF(a, b) trả NULL nếu hai biểu thức bằng nhau:

```sql
SELECT NULLIF(optional_text, '')
FROM lab_boundary_417;
```

Câu trên chuyển empty string thành NULL trên các hệ phân biệt hai giá trị này. Nó không tự chuyển chuỗi chỉ có khoảng trắng thành NULL.

Có thể chuẩn hóa khoảng trắng theo chính sách:

```sql
NULLIF(TRIM(optional_text), '')
```

Nhưng phải xác định TRIM có loại bỏ đúng các ký tự cần thiết không. Tab, newline, non-breaking space và ký tự Unicode không nhất thiết được xử lý giống dấu cách ASCII trên mọi DBMS.

### 4.3. DEFAULT không giống NULL

```sql
INSERT INTO lab_boundary_417 (
    required_text, quantity, amount
)
VALUES ('created', 1, 10.00);
```

Cột created_at nhận DEFAULT. Nhưng nếu ghi rõ:

```sql
INSERT INTO lab_boundary_417 (
    required_text, quantity, amount, created_at
)
VALUES ('created', 1, 10.00, NULL);
```

thì DEFAULT không tự được dùng; câu lệnh cố ghi SQL NULL và sẽ vi phạm NOT NULL.

Muốn yêu cầu default tường minh, có thể dùng từ khóa DEFAULT trong VALUES khi DBMS hỗ trợ ở ngữ cảnh đó:

```sql
INSERT INTO lab_boundary_417 (
    required_text, quantity, amount, created_at
)
VALUES ('created', 1, 10.00, DEFAULT);
```

### 4.4. Test ba trường hợp riêng

Với cột nullable, ít nhất phải có test:

1. Bỏ cột khỏi INSERT.
2. Gửi SQL NULL.
3. Gửi empty string (nếu là cột chuỗi).

Ba trường hợp có thể tạo ba trạng thái lưu khác nhau.

---

## 5. Chuỗi rỗng và khoảng trắng

### 5.1. Empty string

Trong PostgreSQL:

```sql
SELECT
    '' = '' AS same_empty,
    LENGTH('') AS empty_length,
    '' IS NULL AS empty_is_null;
```

Chuỗi rỗng khác SQL NULL và có độ dài 0.

```sql
SELECT *
FROM lab_boundary_417
WHERE optional_text = '';
```

Câu này tìm empty string, không tìm SQL NULL.

### 5.2. Chuỗi chỉ có khoảng trắng

Các giá trị sau khác nhau:

```text
''
' '
'  '
tab
newline
'  text  '
```

Một trường có thể không rỗng nhưng vẫn không có nội dung hữu ích sau chuẩn hóa.

```sql
SELECT
    LENGTH('') AS len_empty,
    LENGTH(' ') AS len_one_space,
    LENGTH('  ') AS len_two_spaces,
    LENGTH(TRIM('  ')) AS len_trimmed;
```

### 5.3. TRIM không phải chuẩn hóa mọi whitespace

TRIM thường loại bỏ dấu cách ở đầu/cuối theo quy tắc của DBMS. Không giả định nó tự loại mọi tab, newline, carriage return, non-breaking space hoặc Unicode whitespace.

Nếu nghiệp vụ cần chuẩn hóa, hãy định nghĩa rõ:

- Ký tự nào được coi là whitespace?
- Chỉ loại ở đầu/cuối hay thay chuỗi nhiều khoảng trắng ở giữa?
- Có chuẩn hóa Unicode NFC/NFKC không?
- Có phân biệt chữ hoa/thường không?
- Có giữ nguyên nội dung người dùng để hiển thị không?

Nên thực hiện normalization ở một lớp được quy định rõ và test cùng bộ dữ liệu Unicode.

### 5.4. Oracle coi chuỗi rỗng như NULL

Oracle SQL coi chuỗi ký tự có độ dài 0 trong kiểu ký tự như NULL. Do đó:

```sql
INSERT INTO some_table (text_col) VALUES ('');
```

không tạo một empty string phân biệt như PostgreSQL. So sánh text_col = empty string cũng không phải cách tìm empty string trong Oracle; dùng IS NULL.

Đây là khác biệt quan trọng khi chuyển ứng dụng giữa Oracle và hệ phân biệt empty string. Nếu nghiệp vụ cần phân biệt “không gửi” với “gửi chuỗi rỗng”, phải giữ thêm cờ/trạng thái hoặc biểu diễn khác khi lưu vào Oracle.

### 5.5. Bảng so sánh empty string

| DBMS | Empty string trong kiểu chuỗi |
| --- | --- |
| PostgreSQL | Khác NULL; độ dài 0 |
| SQL Server | Khác NULL; chuỗi rỗng được lưu |
| MySQL | Khác NULL; chuỗi rỗng được lưu |
| Oracle | Được coi như NULL trong kiểu ký tự SQL |
| SQLite | Khác NULL; giá trị text rỗng |

Kiểm thử migration phải xác nhận dữ liệu rỗng trước/sau khi chuyển DBMS, không chỉ so sánh số lượng hàng.

---

## 6. Kiểm thử NULL trong hàm tổng hợp

Hàm aggregate thường bỏ qua SQL NULL đối với đối số, nhưng có khác biệt quan trọng giữa COUNT(*), COUNT(column) và các hàm khác.

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(optional_text) AS non_null_text_count,
    COUNT(quantity) AS non_null_quantity_count,
    SUM(quantity) AS quantity_sum,
    AVG(quantity) AS quantity_avg,
    MIN(quantity) AS min_quantity,
    MAX(quantity) AS max_quantity
FROM lab_boundary_417;
```

- COUNT(*) đếm hàng.
- COUNT(column) đếm giá trị khác NULL.
- SUM/AVG/MIN/MAX thường bỏ qua NULL.
- Nếu không có giá trị phù hợp, SUM/AVG/MIN/MAX có thể trả NULL.

### 6.1. SUM và COALESCE

```sql
SELECT COALESCE(SUM(quantity), 0)
FROM lab_boundary_417
WHERE test_id = -1;
```

Không có hàng phù hợp: SUM trả NULL; COALESCE biến thành 0.

Nhưng 0 và “không có dữ liệu” không phải lúc nào cũng giống nhau. Nếu báo cáo cần phân biệt, trả cả COUNT(*) và SUM thay vì chỉ COALESCE.

### 6.2. AVG và dữ liệu NULL

Giả sử quantity gồm 10, 20 và NULL. AVG là 15, không phải 10 vì NULL không được tính vào mẫu số. Nếu ứng dụng coi NULL là 0, phải viết:

```sql
AVG(COALESCE(quantity, 0))
```

Hai phép tính có ngữ nghĩa khác nhau. Đây là test cần có khi tính điểm, tỷ lệ hoặc thống kê.

### 6.3. COUNT DISTINCT

COUNT(DISTINCT column) thường không tính NULL. Nếu báo cáo cần đếm cả “chưa xác định” như một nhóm, phải biểu diễn rõ nhóm đó bằng cách khác, không mặc định aggregate sẽ đếm NULL.

---

## 7. NULL trong JOIN, NOT IN và EXISTS

### 7.1. Outer join và điều kiện WHERE

```sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Điều kiện WHERE loại hàng không có order vì o.status là NULL và so sánh cho UNKNOWN. Query thực tế gần với inner join cho điều kiện này.

Nếu muốn giữ mọi customer và chỉ ghép order PAID:

```sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

Test cần có customer không có order, customer có order pending và customer có order paid.

### 7.2. NOT IN có NULL

Giả sử subquery trả các giá trị 1, 2, NULL:

```sql
SELECT *
FROM accounts a
WHERE a.account_id NOT IN (
    SELECT blocked_id
    FROM blocked_accounts
);
```

Nếu danh sách có NULL, phép NOT IN có thể thành UNKNOWN cho các giá trị không khớp, khiến query không trả hàng như mong đợi.

Nếu ý nghĩa là “không tồn tại hàng khớp”, dùng NOT EXISTS:

```sql
SELECT *
FROM accounts a
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_accounts b
    WHERE b.blocked_id = a.account_id
);
```

Nếu account_id có thể NULL, cần quy định rõ nó có được giữ không. NOT EXISTS không tự làm NULL bằng một giá trị cụ thể.

### 7.3. So sánh NULL an toàn

| DBMS | Cách so sánh null-safe |
| --- | --- |
| PostgreSQL | IS NOT DISTINCT FROM và IS DISTINCT FROM |
| SQL Server | IS NULL; IS [NOT] DISTINCT FROM từ SQL Server 2022 |
| MySQL | <=> là null-safe equality |
| Oracle | Điều kiện tường minh hoặc DECODE trong một số ngữ cảnh |
| SQLite | IS/IS NOT; IS xử lý NULL an toàn |

Ví dụ PostgreSQL:

```sql
SELECT
    NULL IS NOT DISTINCT FROM NULL AS same_null,
    NULL IS DISTINCT FROM 0 AS different;
```

Kết quả TRUE, TRUE.

Không thay mọi phép equality bằng null-safe equality. Chỉ dùng khi yêu cầu nghiệp vụ thực sự coi hai NULL là “khớp nhau”.

---

## 8. NULL trong UNIQUE, PRIMARY KEY và CHECK

### 8.1. PRIMARY KEY

PRIMARY KEY ngụ ý NOT NULL và duy nhất. Không thể insert NULL vào cột primary key.

### 8.2. UNIQUE và NULL khác nhau giữa DBMS

Unique constraint kiểm soát các giá trị trùng, nhưng cách xử lý NULL không hoàn toàn giống nhau:

| DBMS | Hành vi phổ biến của UNIQUE với NULL |
| --- | --- |
| PostgreSQL | Mặc định cho phép nhiều NULL; PostgreSQL 15+ hỗ trợ NULLS NOT DISTINCT trong unique index/constraint phù hợp |
| MySQL | UNIQUE index cho phép nhiều NULL |
| SQL Server | UNIQUE index một cột thường chỉ cho một NULL |
| Oracle | UNIQUE cho phép nhiều NULL; khóa ghép có quy tắc riêng khi thành phần NULL |
| SQLite | UNIQUE cho phép nhiều NULL |

Đây là khác biệt có thể làm migration thất bại hoặc cho phép dữ liệu trùng sau chuyển đổi.

### 8.3. CHECK và NULL

Một điều dễ bỏ sót:

```sql
CHECK (quantity >= 0)
```

Nếu quantity là NULL, biểu thức quantity >= 0 là UNKNOWN. Trong SQL, CHECK thường chỉ từ chối khi biểu thức FALSE; UNKNOWN không tương đương FALSE. Vì vậy CHECK này không tự ngăn NULL.

Nếu cột bắt buộc, phải khai báo cả:

```sql
quantity INTEGER NOT NULL CHECK (quantity >= 0)
```

### 8.4. Test constraint

| Input | NOT NULL | CHECK quantity >= 0 | Kỳ vọng nếu cả hai cùng có |
| --- | --- | --- | --- |
| NULL | Vi phạm | UNKNOWN | Bị từ chối bởi NOT NULL |
| -1 | Hợp lệ riêng | FALSE | Bị từ chối bởi CHECK |
| 0 | Hợp lệ | TRUE | Chấp nhận |
| 1 | Hợp lệ | TRUE | Chấp nhận |
| Vượt miền kiểu | Lỗi chuyển kiểu/overflow | Không tới CHECK bình thường | Bị từ chối |

Test từng constraint riêng và kết hợp để biết lỗi đến từ đâu.

---

## 9. Số âm, số 0 và miền số nguyên

### 9.1. Đừng giả định mọi số phải dương

Số âm có thể hợp lệ cho số dư tài khoản, bút toán điều chỉnh, nhiệt độ, chênh lệch, lượng hoàn trả hoặc giá trị biến động.

Số âm có thể không hợp lệ cho số lượng hàng tồn vật lý, số lần retry, tuổi, số ghế đặt hoặc số lượng item trong giỏ.

Quy tắc phải đến từ nghiệp vụ, không đến từ giả định “số âm luôn sai”.

### 9.2. Test các mốc cho miền quantity

Với CHECK 0..100:

| Input | Kết quả |
| ---: | --- |
| -1 | Reject |
| 0 | Accept |
| 1 | Accept |
| 99 | Accept |
| 100 | Accept |
| 101 | Reject |
| NULL | Reject nếu NOT NULL |

SQL kiểm thử giá trị hợp lệ:

```sql
INSERT INTO lab_boundary_417 (
    required_text, quantity, amount
)
VALUES ('q-min', 0, 0.00);

INSERT INTO lab_boundary_417 (
    required_text, quantity, amount
)
VALUES ('q-max', 100, 1.00);
```

Các test -1, 101 và NULL nên được chạy riêng trong transaction/test case để xác nhận bị từ chối.

### 9.3. Biên kiểu integer

Một số miền số nguyên signed thông dụng:

| Kiểu | Miền |
| --- | --- |
| SMALLINT / INT2 | -32.768 đến 32.767 |
| INTEGER / INT | -2.147.483.648 đến 2.147.483.647 |
| BIGINT / INT8 | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Miền chính xác phụ thuộc DBMS và thuộc tính signed/unsigned. MySQL có kiểu số nguyên UNSIGNED; SQL Server có TINYINT unsigned 0..255; không copy miền từ một hệ sang hệ khác.

Với một cột SMALLINT, test MIN hợp lệ, MIN - 1 (overflow), -1, 0, 1, MAX hợp lệ và MAX + 1 (overflow).

### 9.4. Test signed và unsigned

Nếu chuyển cột MySQL UNSIGNED sang PostgreSQL signed, miền dữ liệu có thể thay đổi. Một giá trị lớn hơn signed maximum của kiểu đích không thể lưu nguyên trạng.

Test migration phải tìm mọi giá trị nằm ngoài miền kiểu đích trước khi chuyển đổi.

---

## 10. DECIMAL/NUMERIC: precision, scale và rounding

DECIMAL(p,s) hoặc NUMERIC(p,s) định nghĩa:

- p: tổng số chữ số tối đa.
- s: số chữ số ở phần thập phân.
- Số chữ số phần nguyên tối đa là p - s.

Ví dụ NUMERIC(8,2):

- Tối đa 8 chữ số tổng.
- Có 2 chữ số thập phân.
- Số chữ số phần nguyên tối đa là 6.
- Giá trị dương lớn nhất là 999999.99.
- Giá trị âm nhỏ nhất tương ứng là -999999.99.

### 10.1. Ma trận test NUMERIC(8,2)

| Giá trị | Kỳ vọng cần kiểm tra |
| --- | --- |
| 0 | Hợp lệ |
| -0.01 | Kiểu cho phép, CHECK nghiệp vụ có thể từ chối |
| 0.01 | Hợp lệ |
| 1.234 | Có thể được làm tròn theo DBMS/kiểu; xác nhận chính sách |
| 999999.99 | Biên dương hợp lệ |
| -999999.99 | Biên âm kiểu; CHECK có thể từ chối |
| 1000000.00 | Vượt precision |
| NULL | NOT NULL từ chối nếu cột bắt buộc |
| abc | Lỗi chuyển kiểu |

### 10.2. Scale không phải lúc nào cũng bị từ chối

Khi insert 1.239 vào NUMERIC(8,2), một DBMS có thể làm tròn thành 1.24 thay vì từ chối vì có ba chữ số thập phân. Vì vậy test phải xác nhận **giá trị lưu thực tế**, không chỉ kiểm tra query thành công.

PostgreSQL numeric làm tròn về scale đã khai báo khi lưu; quy tắc rounding của numeric khác floating-point. Các DBMS và SQL mode có thể khác về rounding, truncation hoặc warning/error.

### 10.3. Overflow trong phép tính

Hai giá trị riêng lẻ có thể hợp lệ nhưng phép cộng/nhân có thể vượt kiểu kết quả:

```sql
SELECT CAST(999999.99 AS NUMERIC(8,2))
     * CAST(999999.99 AS NUMERIC(8,2));
```

Kiểu kết quả được suy ra theo quy tắc DBMS. Test cần bao phủ phép tính trung gian, CAST và cột đích. Đừng chỉ kiểm tra input có vừa cột hay không.

### 10.4. Tránh FLOAT cho tiền

FLOAT/REAL là số dấu phẩy động xấp xỉ. Với tiền tệ và phép so sánh chính xác, ưu tiên DECIMAL/NUMERIC hoặc số nguyên lưu đơn vị nhỏ nhất (ví dụ cent) theo thiết kế. Nếu dùng floating point, test sai số và tolerance rõ ràng.

---

## 11. Chuỗi: giới hạn độ dài, Unicode và collation

### 11.1. Test sát độ dài cột

Với VARCHAR(20), thử 0, 1, 19, 20 và 21 ký tự; chuỗi có emoji hoặc ký tự supplementary; chuỗi có combining mark.

Không giả định length của ngôn ngữ ứng dụng, số ký tự Unicode, số code point, số UTF-16 code unit và số byte là cùng một đại lượng.

### 11.2. Khác biệt theo DBMS

| DBMS | Lưu ý về chuỗi |
| --- | --- |
| PostgreSQL | VARCHAR(n) giới hạn số ký tự theo định nghĩa PostgreSQL, không phải số byte UTF-8 |
| SQL Server | VARCHAR(n) tính theo byte; NVARCHAR(n) dùng n byte-pairs UTF-16, ký tự supplementary có thể cần hai byte-pairs |
| MySQL | VARCHAR(n) giới hạn số ký tự; dung lượng byte phụ thuộc character set và row-size limits |
| Oracle | VARCHAR2 có thể dùng BYTE hoặc CHAR length semantics tùy khai báo/cấu hình |
| SQLite | Kiểu khai báo VARCHAR(n) không cưỡng chế giới hạn n như nhiều DBMS khác; cần CHECK hoặc validation nếu muốn giới hạn |

### 11.3. Test Unicode

Ví dụ tập test:

```text
ASCII:       hello
Vietnamese:  Tiếng Việt
Combining:   e + combining acute accent
Emoji:       🙂
Whitespace:  tab, newline, non-breaking space
```

Hai chuỗi nhìn giống nhau có thể khác chuỗi code point. Nếu cần so sánh không phân biệt cách biểu diễn Unicode, chuẩn hóa ở tầng được quy định rõ rồi test cả dữ liệu trước và sau normalization.

### 11.4. Collation và so sánh

So sánh chuỗi phụ thuộc collation:

- Có phân biệt hoa/thường không?
- Có phân biệt dấu không?
- Có coi hai dạng Unicode tương đương không?
- Dấu cách cuối có ảnh hưởng equality không?
- Sort order có đúng locale nghiệp vụ không?

SQL Server, MySQL và Oracle có nhiều lựa chọn collation/linguistic comparison. PostgreSQL có collation theo locale/ICU trong cấu hình phù hợp. SQLite thường phụ thuộc collation được khai báo hoặc extension.

Đừng viết test chỉ bằng ASCII nếu cột được dùng để tìm tên tiếng Việt, mã quốc tế hoặc khóa có quy tắc Unicode.

---

## 12. Ngày giờ và biên thời gian

Giá trị ngày giờ dễ lỗi tại ranh giới: nửa đêm, cuối ngày, ngày cuối tháng, ngày nhuận 29/02, cuối năm và đầu năm, thời điểm chuyển DST, timestamp có độ chính xác phần giây, timezone khác nhau và giá trị sát min/max mà kiểu DBMS hỗ trợ.

### 12.1. Dùng khoảng nửa mở

Thay vì:

```sql
WHERE created_at BETWEEN
    TIMESTAMP '2026-05-01 00:00:00'
    AND TIMESTAMP '2026-05-31 23:59:59.999';
```

thường nên dùng khoảng nửa mở:

```sql
WHERE created_at >= TIMESTAMP '2026-05-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-06-01 00:00:00';
```

Cách này không phụ thuộc timestamp có precision milliseconds, microseconds hay cao hơn và không bỏ sót phần cuối ngày.

### 12.2. Test ngày nhuận

| Ngày | Kỳ vọng |
| --- | --- |
| 2024-02-28 | Hợp lệ |
| 2024-02-29 | Hợp lệ (năm nhuận) |
| 2024-03-01 | Hợp lệ |
| 2025-02-29 | Không hợp lệ |
| 2025-03-01 | Hợp lệ |

DBMS có thể từ chối hoặc chuyển đổi ngày không hợp lệ theo mode/cách parse. Hãy dùng typed parameter hoặc literal chuẩn, không dựa vào định dạng ngày phụ thuộc locale.

### 12.3. Timezone và DST

Một timestamp local có thể không tồn tại hoặc bị lặp khi chuyển giờ mùa hè ở một số vùng. Test thời điểm trước/sau chuyển DST, timestamp có offset tường minh, cùng instant nhưng hai timezone khác nhau, timestamp có/không timezone và quy tắc lưu UTC/hiển thị local.

PostgreSQL TIMESTAMP WITH TIME ZONE chuẩn hóa instant và hiển thị theo timezone session; SQL Server có datetimeoffset; MySQL có TIMESTAMP và DATETIME với semantics khác; Oracle có TIMESTAMP WITH TIME ZONE/LOCAL TIME ZONE; SQLite không có kiểu timestamp native bắt buộc.

### 12.4. Precision phần giây

Nếu cột chỉ lưu milliseconds hoặc scale thấp hơn, giá trị có microseconds có thể bị làm tròn/cắt. Test một timestamp đúng tại ranh giới precision và xác nhận dữ liệu đọc lại.

---

## 13. DEFAULT, NOT NULL và dữ liệu bị bỏ qua

Các test INSERT nên phân biệt:

```sql
-- Cột optional_text bị bỏ qua
INSERT INTO lab_boundary_417 (required_text, quantity, amount)
VALUES ('A', 1, 1.00);

-- Cột optional_text được gán SQL NULL
INSERT INTO lab_boundary_417 (
    required_text, optional_text, quantity, amount
)
VALUES ('B', NULL, 1, 1.00);

-- Cột optional_text nhận chuỗi rỗng
INSERT INTO lab_boundary_417 (
    required_text, optional_text, quantity, amount
)
VALUES ('C', '', 1, 1.00);
```

Trong PostgreSQL, ba trạng thái cột có thể là DEFAULT, SQL NULL và empty string. Trong Oracle, empty string ở cột ký tự được coi như NULL. Trong các hệ khác, thường phân biệt.

### Test DEFAULT

```sql
CREATE TABLE lab_defaults_417 (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'NEW',
    retry_count INTEGER NOT NULL DEFAULT 0
);

INSERT INTO lab_defaults_417 (id) VALUES (1);
INSERT INTO lab_defaults_417 (id, status, retry_count)
VALUES (2, DEFAULT, DEFAULT);

SELECT id, status, retry_count
FROM lab_defaults_417
ORDER BY id;
```

Thử gửi NULL tường minh để xác nhận NOT NULL được thực thi, thay vì nhầm default tự thay NULL.

---

## 14. Test ràng buộc CHECK và tổ hợp điều kiện

```sql
CREATE TABLE lab_discount_417 (
    discount_pct NUMERIC(5,2) NOT NULL,
    CONSTRAINT ck_discount_range
        CHECK (discount_pct BETWEEN 0 AND 100)
);
```

Test:

| Input | Kỳ vọng |
| --- | --- |
| NULL | Vi phạm NOT NULL |
| -0.01 | Vi phạm CHECK |
| 0 | Hợp lệ |
| 0.01 | Hợp lệ |
| 50 | Hợp lệ |
| 100 | Hợp lệ |
| 100.01 | Vi phạm CHECK |
| Giá trị vượt precision | Lỗi kiểu/overflow |

### CHECK nhiều cột

```sql
CREATE TABLE lab_date_range_417 (
    starts_at TIMESTAMP NOT NULL,
    ends_at   TIMESTAMP NOT NULL,
    CHECK (ends_at >= starts_at)
);
```

Test hai mốc bằng nhau, end sau start một đơn vị precision, end trước start một đơn vị precision, một cột NULL và cả hai NULL.

NOT NULL cần tách riêng vì CHECK với UNKNOWN có thể không từ chối NULL.

Constraint là lớp bảo vệ tại database, nhưng không phải mọi quy tắc nghiệp vụ đều có thể diễn đạt bằng CHECK đơn giản. Quy tắc liên quan nhiều hàng/bảng cần unique, foreign key, trigger hoặc transaction logic.

---

## 15. Foreign key và NULL

Foreign key nullable thường cho phép NULL: khi cột FK là NULL, không có giá trị parent cần match theo quy tắc thông thường.

```sql
CREATE TABLE lab_parent_417 (
    parent_id INTEGER PRIMARY KEY
);

CREATE TABLE lab_child_417 (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES lab_parent_417(parent_id)
);
```

Test:

1. parent_id NULL: chấp nhận nếu FK nullable.
2. parent_id trỏ tới parent tồn tại: chấp nhận.
3. parent_id trỏ tới parent không tồn tại: từ chối.
4. Xóa parent khi child còn tham chiếu: hành vi theo ON DELETE.
5. Cập nhật khóa parent: hành vi theo ON UPDATE nếu DBMS hỗ trợ.

Nếu nghiệp vụ bắt buộc phải có parent, khai báo thêm NOT NULL. Foreign key một mình không bắt buộc giá trị phải khác NULL.

Với khóa ngoại ghép nhiều cột, semantics khi một hoặc nhiều cột NULL có thể khác theo MATCH SIMPLE/FULL và hỗ trợ của DBMS. Hãy test tổ hợp NULL của từng thành phần.

---

## 16. Kiểm thử bằng transaction và rollback

Để test constraint và dữ liệu tạm, có thể chạy trong transaction rồi rollback:

```sql
BEGIN;

INSERT INTO lab_boundary_417 (
    required_text, optional_text, quantity, amount, note
)
VALUES (
    'boundary-test', '', 100, 999999.99, 'temporary'
);

SELECT *
FROM lab_boundary_417
WHERE required_text = 'boundary-test';

ROLLBACK;
```

Dữ liệu kiểm thử không được giữ lại sau ROLLBACK nếu mọi thao tác nằm trong cùng transaction và không có tác động ngoài transaction.

### 16.1. Test một lỗi trong transaction

Trong PostgreSQL, một statement lỗi làm transaction ở trạng thái aborted cho đến ROLLBACK hoặc rollback về savepoint. Vì vậy không thể tiếp tục chạy câu lệnh bình thường trong cùng transaction đã lỗi mà không phục hồi trạng thái.

Có thể cô lập từng trường hợp bằng savepoint:

```sql
BEGIN;
SAVEPOINT before_bad_insert;

INSERT INTO lab_boundary_417 (
    required_text, quantity, amount
)
VALUES ('bad', -1, 1.00);

-- Sau lỗi, client cần chạy:
ROLLBACK TO SAVEPOINT before_bad_insert;
ROLLBACK;
```

Ví dụ trên cần được chạy qua client có khả năng dừng/điều khiển sau lỗi; nếu gửi toàn bộ script trong chế độ stop-on-error, client có thể dừng trước các lệnh rollback.

### 16.2. Mỗi test nên độc lập

Một test lỗi không được làm hỏng state của test sau. Dùng transaction, savepoint, database/schema tạm hoặc fixture được dọn đúng cách. Không chạy test phá dữ liệu trên bảng production.

---

## 17. Viết ma trận test có thể kiểm chứng

| ID | Cột | Input | Kỳ vọng | Điều cần xác nhận |
| --- | --- | --- | --- | --- |
| T01 | required_text | NULL | Reject | NOT NULL |
| T02 | optional_text | NULL | Accept | IS NULL |
| T03 | optional_text | empty | Accept trên hệ phân biệt | Empty khác NULL |
| T04 | optional_text | whitespace | Theo policy | Trim/normalize |
| T05 | quantity | -1 | Reject | CHECK |
| T06 | quantity | 0 | Accept | Min hợp lệ |
| T07 | quantity | 100 | Accept | Max hợp lệ |
| T08 | quantity | 101 | Reject | Trên max |
| T09 | amount | 1.239 | Theo rounding policy | Scale |
| T10 | amount | 1000000.00 | Reject | Precision overflow |
| T11 | required_text | 21 ký tự | Reject/truncate theo engine/schema | Length |
| T12 | text | Unicode/emoji | Theo contract | Encoding/collation |
| T13 | created_at | nửa đêm đầu kỳ | Accept | Range inclusive |
| T14 | created_at | nửa đêm đầu kỳ tiếp theo | Exclude | Range exclusive |
| T15 | FK | khóa không tồn tại | Reject | Referential integrity |

Mỗi dòng nên có setup/fixture, statement hoặc API call, expected result, expected SQLSTATE/vendor error nếu reject, expected row count, expected persisted value và cleanup.

Không ghi kỳ vọng chung chung như “chạy được” hoặc “báo lỗi”. Ghi rõ trạng thái mong muốn.

---

## 18. SQLSTATE và kiểm tra lỗi

Khi test dữ liệu biên bị từ chối, hãy xác nhận đúng loại lỗi:

- NOT NULL violation.
- CHECK violation.
- UNIQUE violation.
- FOREIGN KEY violation.
- Numeric out of range/overflow.
- String truncation.
- Invalid text representation/conversion.
- Invalid datetime.
- Deadlock/serialization failure.

Không nên chỉ assert “có exception”, vì lỗi kết nối hoặc syntax cũng có thể làm test đỏ nhưng không chứng minh constraint đang hoạt động.

Một số SQLSTATE thường gặp trong PostgreSQL:

| SQLSTATE | Ý nghĩa |
| --- | --- |
| 23502 | Not null violation |
| 23503 | Foreign key violation |
| 23505 | Unique violation |
| 23514 | Check violation |
| 22003 | Numeric value out of range |
| 22001 | String data right truncation |
| 22007 | Invalid datetime format |
| 22P02 | Invalid text representation |

Mã cụ thể và cách driver trả lỗi khác nhau theo DBMS. Test cross-database nên map lỗi về nhóm nghiệp vụ ở tầng test adapter, đồng thời giữ mã gốc để chẩn đoán.

Nếu test mong CHECK violation nhưng nhận connection timeout, test phải thất bại. Chỉ chấp nhận đúng SQLSTATE/vendor code dự kiến.

---

## 19. Test prepared statement và chuyển kiểu đầu vào

Ứng dụng thường nhận input dưới dạng string rồi bind vào kiểu số/ngày. Hãy test chuỗi số hợp lệ, chuỗi rỗng, whitespace, chuỗi không phải số, số âm, số vượt miền, ký hiệu thập phân theo locale và ký hiệu cộng/leading zero/exponent nếu được phép.

### 19.1. Bind kiểu phù hợp

JDBC:

```java
String sql = """
    INSERT INTO lab_boundary_417
        (required_text, quantity, amount)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "test");
    ps.setInt(2, 0);
    ps.setBigDecimal(3, new BigDecimal("10.25"));
    ps.executeUpdate();
}
```

Đối với optional NULL:

```java
ps.setNull(2, Types.INTEGER);
```

Dùng setNull với SQL type phù hợp, hoặc API setObject theo driver/kiểu đích. Không bind chuỗi "NULL" để đại diện SQL NULL.

### 19.2. Đừng dựa vào implicit conversion

Nếu bind abc vào cột INTEGER, DBMS/driver có thể báo lỗi chuyển kiểu. Nhưng nếu ứng dụng tự parse và chuyển abc thành 0 hoặc NULL trước khi bind, database không còn thấy dữ liệu sai ban đầu.

Test cần xác định lớp nào chịu trách nhiệm validation và kiểm tra cả API contract lẫn database constraint.

---

## 20. Property-based testing và fuzzing

Boundary testing thủ công bao phủ các mốc đã biết. Property-based testing bổ sung bằng cách tạo nhiều input theo miền và kiểm tra invariant.

Ví dụ property:

- Quantity lưu được luôn nằm trong 0..100.
- Amount lưu được luôn không âm.
- Mọi SKU chỉ có tối đa một hàng.
- UPSERT cùng idempotency key nhiều lần không tạo thêm bản ghi.
- Với input hợp lệ, đọc lại trả giá trị theo quy tắc rounding đã định.
- Transaction bị rollback không để lại thay đổi nghiệp vụ.

### 20.1. Sinh giá trị sát biên

Với miền [min, max], sinh tập:

```text
min - 1
min
min + 1
random valid value
max - 1
max
max + 1
NULL
```

Với decimal, thêm nhiều hơn scale một chữ số, giá trị đúng nửa đơn vị làm tròn, giá trị lớn nhất vừa precision và giá trị vừa vượt precision.

Với chuỗi, thêm độ dài n-1, n, n+1; empty và whitespace; Unicode nhiều byte; ký tự quote, backslash, delimiter; ký tự điều khiển nếu được phép/không được phép.

### 20.2. Fuzz input không đồng nghĩa fuzz SQL text

Fuzz **giá trị bind** để tìm lỗi chuyển kiểu, constraint, Unicode và boundary. Không tạo raw SQL fragment từ dữ liệu fuzz rồi thực thi tùy tiện trong database thật.

Test injection nên chạy trong môi trường cô lập, với quyền thấp và đối tượng test riêng.

### 20.3. Seed cố định để tái hiện

Khi property-based test phát hiện lỗi, lưu seed và input tối thiểu để tái hiện. Một test ngẫu nhiên không thể tái hiện làm khó điều tra regression.

---

## 21. Concurrency test cho giá trị biên

Giá trị biên cũng có thể lộ lỗi chỉ xuất hiện khi nhiều transaction chạy đồng thời:

- Hai session cùng insert một unique key.
- Hai session cùng tăng counter từ giá trị sát MAX.
- Hai transaction cùng tiêu thụ tồn kho đang bằng 1.
- Một transaction đổi trạng thái trong khi transaction khác đọc NULL.
- Hai transaction cùng cập nhật version.

Ví dụ invariant tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BK-01'
  AND quantity > 0;
```

Kiểm tra affected rows:

- 1 hàng: đã trừ thành công.
- 0 hàng: không tồn tại SKU hoặc quantity không còn > 0; cần xác định riêng nếu API cần phân biệt.

Nếu quantity bắt buộc không âm, thêm CHECK quantity >= 0. Điều kiện UPDATE và CHECK bổ trợ nhau.

### Test hai session

1. Khởi tạo quantity = 1.
2. Hai session cùng chạy UPDATE trừ 1 với điều kiện quantity > 0.
3. Commit cả hai.
4. Kiểm tra quantity cuối là 0, không âm.
5. Chỉ một thao tác thành công theo row count.

Test này cần hai connection thực sự độc lập, không chỉ hai câu tuần tự trong một transaction.

---

## 22. Khác biệt cần chú ý giữa các DBMS

### 22.1. NULL và empty string

| DBMS | Empty string có khác NULL? |
| --- | --- |
| PostgreSQL | Có |
| SQL Server | Có |
| MySQL | Có |
| Oracle | Không, chuỗi rỗng kiểu ký tự được coi là NULL |
| SQLite | Có |

### 22.2. So sánh NULL

| DBMS | Cách viết thường dùng |
| --- | --- |
| PostgreSQL | IS NULL, IS DISTINCT FROM, IS NOT DISTINCT FROM |
| SQL Server | IS NULL; IS [NOT] DISTINCT FROM từ SQL Server 2022 |
| MySQL | IS NULL, <=> |
| Oracle | IS NULL; điều kiện tường minh/DECODE trong trường hợp phù hợp |
| SQLite | IS NULL, IS, IS NOT |

Không dùng phép = NULL trong SQL portable.

### 22.3. UNIQUE với NULL

Các hệ khác nhau về số NULL được phép trong unique key. Nếu migration yêu cầu cùng semantics, có thể phải dùng filtered/partial unique index, expression index, NULLS NOT DISTINCT hoặc quy tắc dữ liệu riêng theo DBMS.

### 22.4. Kiểu và miền số

- MySQL có UNSIGNED cho một số kiểu số nguyên.
- SQL Server có TINYINT không âm.
- PostgreSQL SMALLINT/INTEGER/BIGINT là signed.
- Oracle thường dùng NUMBER với precision/scale.
- SQLite có dynamic typing; STRICT table và CHECK giúp tăng tính chặt chẽ nhưng không giống kiểu số cố định của các hệ khác.

### 22.5. Độ dài chuỗi

- PostgreSQL VARCHAR(n) giới hạn ký tự.
- SQL Server VARCHAR tính byte; NVARCHAR dùng byte-pair UTF-16.
- MySQL VARCHAR(n) giới hạn số ký tự nhưng storage phụ thuộc charset.
- Oracle VARCHAR2 có BYTE/CHAR semantics.
- SQLite không tự cưỡng chế VARCHAR(n) mặc định.

Khi chuyển DBMS, hãy test dữ liệu thực tế, đặc biệt tiếng Việt có dấu và emoji.

---

## 23. Test migration và regression

Một thay đổi schema có thể làm dữ liệu biên trước đây hợp lệ trở thành lỗi: giảm VARCHAR(100) xuống VARCHAR(50), đổi nullable thành NOT NULL, đổi DECIMAL(12,4) thành DECIMAL(10,2), thêm CHECK, thay collation, chuyển Oracle sang PostgreSQL hoặc chuyển từ SQLite sang DBMS kiểu tĩnh hơn.

### Checklist migration

1. Đếm số NULL hiện có.
2. Đếm chuỗi rỗng và whitespace-only.
3. Tìm số âm và giá trị ngoài miền mới.
4. Tìm chuỗi dài hơn giới hạn đích.
5. Tìm decimal có scale vượt giới hạn mới.
6. Kiểm tra dữ liệu ngày giờ không hợp lệ hoặc ngoài range.
7. Tìm duplicate theo unique key mới.
8. Tìm orphan rows theo foreign key mới.
9. Xác định cách chuyển đổi/clean dữ liệu và ghi lại số hàng.
10. Test rollback và phục hồi trong môi trường staging.

Ví dụ PostgreSQL tìm quantity ngoài miền mới:

```sql
SELECT COUNT(*) AS invalid_rows
FROM inventory
WHERE quantity IS NULL
   OR quantity < 0
   OR quantity > 100;
```

Tìm chuỗi rỗng/whitespace:

```sql
SELECT COUNT(*) AS blank_rows
FROM customers
WHERE name IS NULL
   OR BTRIM(name) = '';
```

BTRIM trong ví dụ PostgreSQL không đại diện cho mọi Unicode whitespace. Nếu quy tắc trim rộng hơn, chuẩn hóa theo một định nghĩa rõ.

---

## 24. Những lỗi thường gặp khi test giá trị biên

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ test giá trị bình thường | Bỏ sót NULL/overflow/empty | Tạo ma trận biên min/max và invalid |
| Dùng = NULL | Không tìm được NULL | Dùng IS NULL |
| Coi empty string là NULL trên mọi DBMS | Sai khi chuyển dữ liệu | Ghi nhận khác biệt Oracle |
| Dùng COALESCE để che mọi NULL | Mất phân biệt “không có” và 0/empty | Xác định semantics trước |
| Cho rằng CHECK ngăn NULL | NULL có thể làm CHECK UNKNOWN | Kết hợp NOT NULL |
| Dùng NOT IN với subquery có NULL | Kết quả có thể rỗng ngoài ý muốn | NOT EXISTS hoặc lọc NULL có chủ đích |
| Dùng COUNT(*) thay COUNT(col) | Đếm cả hàng có giá trị NULL | Chọn aggregate đúng mục tiêu |
| Coi TRIM xử lý mọi whitespace | Tab/Unicode space còn sót | Định nghĩa tập ký tự cần chuẩn hóa |
| Test chuỗi theo byte ở hệ đếm ký tự | Sai giới hạn VARCHAR | Xét charset và length semantics |
| Chỉ test decimal vừa cột | Bỏ sót rounding/overflow ở phép tính | Test scale, precision và kết quả trung gian |
| Dùng FLOAT cho tiền | Sai số dấu phẩy động | DECIMAL/NUMERIC hoặc integer minor unit |
| Dùng BETWEEN đến 23:59:59.999 | Bỏ sót timestamp precision cao hơn | Khoảng nửa mở |
| Dựa vào locale parse ngày | Kết quả phụ thuộc session | Typed parameter/ISO format |
| Bắt mọi SQLException là test pass | Che syntax/connection error | Assert SQLSTATE/vendor code đúng |
| Test lỗi không rollback | Dữ liệu test làm ảnh hưởng case sau | Transaction/savepoint/fixture |
| Chỉ test một connection | Bỏ sót race condition | Test nhiều session |
| Không kiểm tra dữ liệu đọc lại | Bỏ sót truncation/rounding | Assert persisted value |
| Test Oracle empty string như PostgreSQL | Sai semantics | Test NULL mapping khi migration |
| Giả định SQLite VARCHAR(n) enforce length | Dữ liệu dài vẫn có thể lưu | CHECK hoặc validation |
| Giả định unique NULL giống nhau mọi hệ | Migration tạo/cho phép dữ liệu khác | Test unique key có NULL trên engine đích |

---

## 25. Bộ test mẫu cho ứng dụng

Một test case nên được viết như một hợp đồng.

Test hợp lệ:

```text
Tên: quantity ở giá trị tối thiểu
Given:
  inventory row chưa tồn tại
When:
  insert sku = "BK-01", quantity = 0
Then:
  statement thành công
  đúng 1 hàng được ghi
  quantity đọc lại bằng 0
  không có hàng duplicate
```

Test reject:

```text
Tên: quantity âm
Given:
  schema có NOT NULL và CHECK quantity >= 0
When:
  insert quantity = -1
Then:
  database từ chối
  lỗi thuộc nhóm CHECK violation
  không có hàng được ghi
  transaction được rollback/khôi phục đúng
```

Test NULL:

```text
Tên: optional_text là SQL NULL
Given:
  optional_text nullable
When:
  bind SQL NULL
Then:
  insert thành công
  SELECT ... IS NULL tìm thấy hàng
  SELECT ... = empty không tìm thấy hàng trong PostgreSQL
```

Test empty string:

```text
Tên: optional_text là empty string
Given:
  DBMS phân biệt empty string với NULL
When:
  bind chuỗi ""
Then:
  insert thành công
  LENGTH = 0 theo hàm phù hợp
  IS NULL là false
```

Trên Oracle, test cuối có expected behavior khác: empty string kiểu ký tự được coi là NULL.

---

## 26. Bài tập thực hành

### Bài 1. NULL khác empty

Trong PostgreSQL, phân biệt NULL, empty string, một dấu cách và 0. Viết điều kiện tìm từng loại cho cột chuỗi và cột số.

### Bài 2. Ba giá trị logic

Dự đoán kết quả NULL = 5, NULL <> 5, NULL IS NULL, NOT (NULL = 5). Biểu thức nào giữ hàng trong WHERE?

### Bài 3. NOT IN

Một subquery trả 1, 2, NULL. Vì sao x NOT IN (subquery) có thể không trả các giá trị x không khớp? Viết cách diễn đạt bằng NOT EXISTS.

### Bài 4. COALESCE

Nếu cột text là empty string, COALESCE(text_col, 'N/A') trả gì trên PostgreSQL? Muốn chuyển empty thành NULL dùng biểu thức nào?

### Bài 5. Oracle empty string

Vì sao empty string trong Oracle không thể được kiểm tra như một giá trị riêng biệt giống PostgreSQL? Cần lưu thêm thông tin gì nếu nghiệp vụ cần phân biệt empty và missing?

### Bài 6. COUNT

Bảng có 5 hàng, trong đó cột amount có 2 NULL. So sánh COUNT(*), COUNT(amount) và COUNT(DISTINCT amount).

### Bài 7. CHECK và NULL

Vì sao CHECK(quantity >= 0) không thay thế NOT NULL? Viết định nghĩa cột bắt buộc quantity không âm.

### Bài 8. UNIQUE NULL

Nêu khác biệt cơ bản giữa PostgreSQL mặc định, MySQL và SQL Server khi tạo UNIQUE trên cột nullable. Vì sao migration cần test lại?

### Bài 9. Số nguyên biên

Với SMALLINT signed, nêu MIN/MAX và hai giá trị ngoài miền cần test.

### Bài 10. Số âm theo nghiệp vụ

Một cột balance cho phép số âm, một cột item_count không cho phép số âm. Thiết kế CHECK khác nhau như thế nào?

### Bài 11. DECIMAL(8,2)

Nêu số chữ số phần nguyên tối đa và giá trị dương lớn nhất. Những test nào cần có cho scale và overflow?

### Bài 12. Rounding

Cột DECIMAL(8,2) nhận 1.239. Vì sao phải đọc lại giá trị lưu thay vì chỉ assert INSERT thành công?

### Bài 13. Chuỗi dài

Với VARCHAR(20), lập test độ dài 19, 20, 21 và một chuỗi emoji. Vì sao kết quả có thể khác theo DBMS?

### Bài 14. Whitespace

Tại sao TRIM('  ') không chứng minh tab và non-breaking space cũng được loại bỏ? Hãy mô tả cách định nghĩa normalization.

### Bài 15. Date range

Viết điều kiện lấy mọi timestamp trong tháng 5/2026 bằng khoảng nửa mở. Vì sao không nên dùng 23:59:59.999?

### Bài 16. Ngày nhuận

Năm 2024 và 2025, ngày 29/02 có hợp lệ không? Nêu test cho parser ngày.

### Bài 17. DEFAULT và NULL

Khác biệt giữa bỏ cột khỏi INSERT, chỉ định NULL và chỉ định DEFAULT là gì?

### Bài 18. Foreign key NULL

Một child.parent_id nullable và có FOREIGN KEY. Khi parent_id NULL, có cần hàng parent khớp không? Nếu nghiệp vụ bắt buộc parent thì thêm gì?

### Bài 19. Outer join

Vì sao đặt điều kiện right_table.status = 'PAID' trong WHERE có thể làm mất hàng bên trái không có hàng phải? Cách sửa?

### Bài 20. Bind NULL qua JDBC

Viết cách bind SQL NULL cho cột INTEGER bằng PreparedStatement. Vì sao không bind chuỗi "NULL"?

### Bài 21. SQLSTATE

Test mong CHECK violation nhưng nhận lỗi connection timeout. Vì sao không được coi mọi exception là test pass?

### Bài 22. Transaction test

Mô tả cách dùng transaction/rollback để chạy test INSERT mà không để lại fixture. PostgreSQL cần chú ý gì sau một statement lỗi?

### Bài 23. Concurrency tồn kho

Quantity đang là 1. Hai session cùng chạy UPDATE quantity = quantity - 1 WHERE quantity > 0. Kết quả đúng cần có là gì?

### Bài 24. Migration Oracle sang PostgreSQL

Một cột Oracle có giá trị empty string. Sau chuyển sang PostgreSQL, vì sao semantics có thể thay đổi? Cần kiểm kê dữ liệu nào?

### Bài 25. Thiết kế ma trận

Thiết kế ma trận test cho discount_pct NUMERIC(5,2) NOT NULL CHECK (discount_pct BETWEEN 0 AND 100), gồm NULL, âm, 0, 0.01, 100, 100.01, quá scale và overflow.

---

## 27. Gợi ý lời giải

### Bài 1

Trong PostgreSQL:

- SQL NULL: col IS NULL.
- Empty: col = empty string.
- Một dấu cách: col = một dấu cách.
- Số 0: number_col = 0.

Các giá trị khác kiểu không so sánh trực tiếp như thể cùng một loại.

### Bài 2

- NULL = 5: UNKNOWN.
- NULL <> 5: UNKNOWN.
- NULL IS NULL: TRUE.
- NOT (NULL = 5): UNKNOWN.

Chỉ biểu thức TRUE giữ hàng trong WHERE; IS NULL giữ hàng.

### Bài 3

NULL trong danh sách khiến phép NOT IN có thể thành UNKNOWN cho giá trị không khớp. Dùng:

```sql
SELECT a.*
FROM accounts a
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_accounts b
    WHERE b.blocked_id = a.account_id
);
```

Nếu account_id nullable, quy định rõ hành vi cho nó.

### Bài 4

Trên PostgreSQL, COALESCE trả empty string vì empty khác NULL. Dùng:

```sql
COALESCE(NULLIF(text_col, ''), 'N/A')
```

nếu muốn cả NULL và empty thành N/A.

### Bài 5

Oracle coi zero-length character string là NULL trong SQL. Nếu cần phân biệt empty với missing, lưu thêm cờ như was_provided, trạng thái nguồn hoặc một biểu diễn riêng được chuẩn hóa trước khi ghi.

### Bài 6

- COUNT(*) = 5.
- COUNT(amount) = 3.
- COUNT(DISTINCT amount) phụ thuộc số giá trị khác NULL phân biệt; NULL không được tính.

### Bài 7

CHECK(quantity >= 0) với NULL tạo UNKNOWN và CHECK thường không từ chối UNKNOWN. Dùng:

```sql
quantity INTEGER NOT NULL CHECK (quantity >= 0)
```

### Bài 8

PostgreSQL mặc định và MySQL cho phép nhiều NULL trong unique key; SQL Server unique index một cột thường chỉ cho một NULL. PostgreSQL 15+ có NULLS NOT DISTINCT để thay đổi semantics. Migration phải xác nhận dữ liệu và index đích.

### Bài 9

SMALLINT signed: -32768 đến 32767. Test -32769 và 32768 để kiểm tra overflow.

### Bài 10

Balance:

```sql
balance NUMERIC(12,2) NOT NULL
```

Item count:

```sql
item_count INTEGER NOT NULL CHECK (item_count >= 0)
```

Nếu balance có miền hữu hạn theo nghiệp vụ, thêm CHECK tương ứng.

### Bài 11

NUMERIC(8,2) có 6 chữ số phần nguyên tối đa; max dương 999999.99. Test 1.239, giá trị tối đa, vượt max, số âm, NULL và kết quả phép tính trung gian.

### Bài 12

DBMS có thể làm tròn hoặc chuyển đổi scale khi lưu. INSERT thành công không chứng minh giá trị được lưu là 1.239; đọc lại và so với rounding policy đã định.

### Bài 13

Test 19, 20 và 21 ký tự cùng emoji. PostgreSQL đếm ký tự theo quy tắc của nó; SQL Server VARCHAR tính byte và NVARCHAR dùng byte-pairs; MySQL/Oracle có charset/length semantics; SQLite không cưỡng chế VARCHAR(n) mặc định.

### Bài 14

TRIM mặc định không nhất thiết loại tab, newline hoặc Unicode whitespace. Định nghĩa rõ code point cần loại, đầu/cuối hay toàn chuỗi, chuẩn hóa Unicode nào; dùng cùng quy tắc trong ứng dụng và test.

### Bài 15

```sql
WHERE created_at >= TIMESTAMP '2026-05-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-06-01 00:00:00'
```

Khoảng nửa mở tránh phụ thuộc precision phần giây và bao phủ mọi timestamp trong tháng.

### Bài 16

2024 là năm nhuận nên 29/02 hợp lệ; 2025 không phải năm nhuận nên không hợp lệ. Test typed date input/ISO date và assert lỗi đúng, không phụ thuộc locale.

### Bài 17

- Bỏ cột: DBMS áp dụng DEFAULT nếu có.
- Ghi NULL: cố lưu SQL NULL; NOT NULL sẽ từ chối.
- Ghi DEFAULT: yêu cầu giá trị mặc định tường minh nếu cú pháp hỗ trợ.

### Bài 18

FK nullable thường cho phép NULL mà không cần hàng parent. Nếu nghiệp vụ bắt buộc parent, khai báo NOT NULL thêm.

### Bài 19

WHERE trên cột bảng phải loại hàng NULL-extended vì điều kiện UNKNOWN. Đưa điều kiện vào ON để giữ hàng trái:

```sql
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
```

### Bài 20

```java
ps.setNull(2, Types.INTEGER);
```

Chuỗi "NULL" là bốn ký tự text, không phải SQL NULL.

### Bài 21

Connection timeout không chứng minh CHECK constraint hoạt động. Test phải assert SQLSTATE/vendor code của lỗi mong đợi; lỗi kết nối phải làm test thất bại.

### Bài 22

Bắt đầu transaction, thực hiện INSERT và SELECT kiểm tra, sau đó ROLLBACK. Trong PostgreSQL, sau statement lỗi transaction ở trạng thái aborted; dùng ROLLBACK hoặc ROLLBACK TO SAVEPOINT trước khi tiếp tục.

### Bài 23

Chỉ một session nên giảm quantity từ 1 xuống 0; session còn lại cập nhật 0 hàng vì điều kiện quantity > 0 không còn đúng. Giá trị cuối không âm. Kiểm tra row count và CHECK.

### Bài 24

Oracle empty string được coi như NULL, trong khi PostgreSQL phân biệt. Cần kiểm kê NULL, empty và whitespace theo cách biểu diễn có thể còn trong nguồn, rồi xác định mapping khi migration.

### Bài 25

| Input | Kỳ vọng |
| --- | --- |
| NULL | Reject bởi NOT NULL |
| -0.01 | Reject bởi CHECK |
| 0 | Accept |
| 0.01 | Accept |
| 100 | Accept |
| 100.01 | Reject bởi CHECK |
| 1.239 | Kiểm tra rounding thành scale 2 theo DBMS |
| Giá trị vượt precision NUMERIC(5,2) | Reject/overflow |

NUMERIC(5,2) có tối đa 3 chữ số phần nguyên; miền kiểu dương lớn nhất là 999.99. CHECK giới hạn nghiệp vụ hẹp hơn là 0..100.

---

## 28. Checklist kiểm thử trước khi phát hành

Với mỗi cột quan trọng, xác nhận:

- [ ] NULL có được phép không? Nếu được, có nghĩa gì?
- [ ] Empty string có khác NULL trên DBMS đích không?
- [ ] Chuỗi whitespace-only được giữ, trim hay từ chối?
- [ ] Độ dài tính theo ký tự, byte hay byte-pair?
- [ ] Unicode và collation có được kiểm tra?
- [ ] Số âm có hợp lệ theo nghiệp vụ?
- [ ] Zero là giá trị hợp lệ hay có ý nghĩa đặc biệt?
- [ ] Min/max kiểu và min/max nghiệp vụ đã được test?
- [ ] Decimal rounding, scale và overflow đã được xác nhận?
- [ ] Phép tính trung gian có thể overflow không?
- [ ] Ngày nhuận, đầu/cuối kỳ, timezone và precision đã được test?
- [ ] NOT NULL, CHECK, UNIQUE và FOREIGN KEY hoạt động đúng?
- [ ] DEFAULT khác NULL tường minh đã được test?
- [ ] Aggregate, JOIN, NOT IN và NULL logic có expected result?
- [ ] Lỗi được assert bằng SQLSTATE/vendor code đúng?
- [ ] Test rollback và cleanup không để lại dữ liệu?
- [ ] Concurrency được kiểm tra với nhiều connection?
- [ ] Migration có test riêng cho khác biệt DBMS?
- [ ] Giá trị bind đúng kiểu và không phụ thuộc implicit conversion?
- [ ] Kết quả đọc lại có đúng giá trị đã lưu theo policy?

## 29. Kết luận

Kiểm thử giá trị biên là kiểm thử **hợp đồng dữ liệu** giữa ứng dụng và database. Một bộ test tốt phải kiểm tra cả đầu vào được chấp nhận, đầu vào bị từ chối, giá trị thực sự được lưu, lỗi được phát ra và trạng thái transaction sau lỗi.

Các nguyên tắc cần nhớ:

1. **NULL khác 0, empty string và DEFAULT.** SQL dùng logic ba giá trị; dùng IS NULL và test AND/OR/NOT.
2. **Empty string phụ thuộc DBMS.** Oracle coi chuỗi rỗng kiểu ký tự là NULL; PostgreSQL, SQL Server, MySQL và SQLite phân biệt.
3. **Số âm và số 0 theo nghiệp vụ.** Không tự giả định mọi số âm đều sai; đặt CHECK phù hợp và test min/max.
4. **DECIMAL cần test precision, scale và rounding.** Phép tính trung gian cũng có thể overflow.
5. **Chuỗi cần test length, Unicode, whitespace và collation.** Đơn vị độ dài không giống nhau giữa DBMS.
6. **Ngày giờ cần test khoảng nửa mở, leap day, timezone và precision.**
7. **CHECK không thay NOT NULL.** UNKNOWN không giống FALSE; unique NULL semantics khác nhau theo hệ.
8. **Assert đúng lỗi và dữ liệu đọc lại.** Một exception bất kỳ không chứng minh constraint đang hoạt động.
9. **Dùng transaction/rollback và nhiều session.** Test cả atomicity, cleanup và race condition.
10. **Kiểm tra trên DBMS/version đích.** Không giả định semantics của một phương ngữ sẽ giữ nguyên khi migrate.

Hãy bắt đầu từ miền dữ liệu của từng cột, chọn các điểm sát ranh giới và ghi rõ kết quả mong đợi. Khi mọi test đều kiểm tra được giá trị lưu, lỗi, số hàng và transaction state, bộ kiểm thử mới có thể phát hiện những lỗi chỉ xuất hiện ở dữ liệu thực tế.
