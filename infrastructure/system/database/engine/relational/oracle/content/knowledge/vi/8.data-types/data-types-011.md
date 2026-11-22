# NULL, chuỗi rỗng và logic ba giá trị trong Oracle

Trong Oracle Database, một cột có thể chứa giá trị hợp lệ hoặc **`NULL`**, nghĩa là không có giá trị được biết/được cung cấp trong ngữ cảnh dữ liệu. Điểm đặc biệt quan trọng của Oracle là **chuỗi ký tự có độ dài bằng 0 (`''`) hiện được xử lý như `NULL`** đối với các giá trị ký tự thông thường. Ngoài ra, các phép so sánh với `NULL` không cho kết quả đúng hoặc sai như phép so sánh số thông thường, mà tạo ra trạng thái thứ ba: **UNKNOWN**.

Ba điều này ảnh hưởng trực tiếp đến cách viết `WHERE`, `JOIN`, `CHECK`, `COUNT`, xử lý tham số từ ứng dụng Java và thiết kế mô hình dữ liệu. Một biểu thức nhìn có vẻ hợp lý như `WHERE note = ''` hoặc `WHERE status <> 'DONE'` có thể bỏ qua những dòng bạn muốn tìm. Bài học này xây dựng mô hình chính xác và minh họa bằng các câu SQL có thể chạy trên Oracle Database.

Sau bài học, bạn có thể:

- Giải thích `NULL` là gì và phân biệt với `0`, `FALSE`, dấu cách và giá trị mặc định.
- Hiểu vì sao `''` trở thành `NULL` với `VARCHAR2`/`CHAR`, đồng thời phân biệt với LOB rỗng như `EMPTY_CLOB()`.
- Đọc bảng chân trị của **TRUE / FALSE / UNKNOWN** với `AND`, `OR` và `NOT`.
- Dùng đúng `IS NULL`, `IS NOT NULL`, `NVL`, `COALESCE`, `NULLIF` và `CASE`.
- Dự đoán kết quả khi `NULL` xuất hiện trong lọc dữ liệu, `NOT IN`, outer join, tổng hợp và ràng buộc.
- Thiết kế kiểm thử cho các trường hợp dữ liệu thiếu, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.

> Phạm vi: hành vi SQL của Oracle Database đối với các kiểu ký tự thông dụng và `NULL`. Oracle đã ghi nhận quy tắc hiện tại “zero-length character string is NULL” nhưng lưu ý rằng hành vi này có thể thay đổi trong tương lai. Vì vậy, mã ứng dụng cần mô tả rõ ý nghĩa dữ liệu, tránh dựa vào việc có thể lưu riêng `''` và `NULL` trong cột `VARCHAR2` của Oracle.

## 1. `NULL` thực sự biểu thị điều gì?

Trong cơ sở dữ liệu quan hệ, một cột nullable có thể không có giá trị cho một hàng. Oracle biểu thị trường hợp này bằng `NULL`. Tùy mô hình nghiệp vụ, nguyên nhân có thể là:

- Dữ liệu **chưa được cung cấp**, ví dụ ngày giao hàng của đơn mới.
- Dữ liệu **chưa biết**, ví dụ số điện thoại chưa được xác minh.
- Dữ liệu **không áp dụng**, ví dụ ngày hoàn tiền của giao dịch chưa từng hoàn tiền.

Đây là các **diễn giải nghiệp vụ khác nhau** nhưng có thể cùng được lưu bằng một marker `NULL`. Nếu ứng dụng cần phân biệt “chưa biết” với “không áp dụng”, phải có thêm trạng thái/thuộc tính thích hợp; chỉ một giá trị `NULL` không tự nói rõ nguyên nhân.

### 1.1. Những giá trị không phải `NULL`

| Giá trị | Ý nghĩa | Có phải `NULL` trong Oracle? |
| --- | --- | --- |
| `NULL` | Không có giá trị xác định | Có |
| `0` | Số không | Không |
| `'0'` | Chuỗi chứa ký tự 0 | Không |
| `' '` | Một dấu cách | Không |
| `'   '` | Ba dấu cách | Không |
| `'N/A'` | Chuỗi có ba ký tự biểu diễn “not applicable” | Không |
| `'UNKNOWN'` | Chuỗi văn bản “UNKNOWN” | Không |
| `DATE '1900-01-01'` | Một ngày cụ thể thường được dùng làm sentinel | Không |
| `''` | Chuỗi độ dài 0 | **Được Oracle xem là `NULL`** với dữ liệu ký tự thông thường |

`NULL` không phải số 0, không phải khoảng trắng và cũng không phải một chuỗi chứa chữ “NULL”. Việc dùng `'N/A'` hoặc `0` để đại diện dữ liệu thiếu cần là **quyết định nghiệp vụ được ghi rõ**, vì nó làm thay đổi ý nghĩa so sánh và tổng hợp.

### 1.2. `NULL` có kiểu dữ liệu không?

`NULL` là marker có thể xuất hiện ở nhiều kiểu dữ liệu, không chỉ ở cột ký tự:

```sql
SELECT
    CAST(NULL AS NUMBER)       AS unknown_amount,
    CAST(NULL AS DATE)         AS unknown_date,
    CAST(NULL AS VARCHAR2(20)) AS unknown_note
FROM dual;
```

Cả ba biểu thức đều có giá trị `NULL` nhưng được gán kiểu rõ ràng để dùng trong biểu thức, phép toán hay `UNION` thích hợp. Khi tự tạo biểu thức phức tạp hoặc dùng bind parameters, việc chọn đúng **kiểu dữ liệu** vẫn rất quan trọng, mặc dù giá trị thực tế là `NULL`.

### 1.3. Phép toán với `NULL`

Phần lớn phép toán thông thường có một toán hạng `NULL` sẽ trả về `NULL`:

```sql
SELECT
    10 + CAST(NULL AS NUMBER) AS add_result,
    10 * CAST(NULL AS NUMBER) AS multiply_result,
    LENGTH(CAST(NULL AS VARCHAR2(20))) AS length_result
FROM dual;
```

Kết quả các cột trên là `NULL`. Tuy nhiên **không áp dụng quy tắc “cứ thấy NULL thì kết quả luôn NULL” cho mọi SQL function/operator**: `NVL`, `COALESCE`, `COUNT`, `IS NULL`, `DECODE` và phép nối chuỗi của Oracle có những quy tắc riêng sẽ được giải thích sau.

## 2. Oracle xử lý chuỗi rỗng `''` như thế nào?

### 2.1. Chuỗi rỗng trong `VARCHAR2` và `CHAR`

Với các giá trị ký tự SQL thông thường, Oracle hiện xem chuỗi độ dài 0 như `NULL`. Ví dụ:

```sql
SELECT
    CASE WHEN '' IS NULL THEN 'IS NULL' ELSE 'NOT NULL' END AS empty_check,
    NVL('', 'gia tri thay the') AS empty_with_nvl,
    LENGTH('') AS empty_length,
    LENGTH(' ') AS one_space_length
FROM dual;
```

Kết quả có ý nghĩa:

| Biểu thức | Giá trị kỳ vọng |
| --- | --- |
| `'' IS NULL` | TRUE |
| `NVL('', 'gia tri thay the')` | `gia tri thay the` |
| `LENGTH('')` | `NULL` |
| `LENGTH(' ')` | `1` |

`LENGTH('')` **không trả về 0** theo quy tắc hiện hành của Oracle cho chuỗi ký tự này; vì `''` đã được xem là `NULL` nên kết quả `LENGTH` cũng là `NULL`.

Điều tương tự xuất hiện khi ghi vào cột `VARCHAR2`:

```sql
CREATE TABLE lab_empty_string (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(30)
);

INSERT INTO lab_empty_string (id, description)
VALUES (1, '');

INSERT INTO lab_empty_string (id, description)
VALUES (2, NULL);

INSERT INTO lab_empty_string (id, description)
VALUES (3, ' ');

COMMIT;

SELECT
    id,
    CASE WHEN description IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS state,
    LENGTH(description) AS character_count
FROM lab_empty_string
ORDER BY id;
```

Hàng 1 và 2 có `DESCRIPTION IS NULL`; hàng 3 chứa một dấu cách nên khác `NULL`. Thử nghiệm này tạo một bảng chỉ dùng cho lab; nếu bảng đã tồn tại, đổi tên để tránh ảnh hưởng dữ liệu hiện có.

**Hệ quả của `NOT NULL`:** nếu cột `DESCRIPTION` có ràng buộc `NOT NULL`, việc `INSERT` với `''` bị Oracle xem là chèn `NULL` và có thể phát sinh `ORA-01400`. Khi dùng giá trị rỗng từ ứng dụng, không nên mặc định cột `NOT NULL` chấp nhận chuỗi có độ dài 0.

### 2.2. Dấu cách, `TRIM` và `CHAR` cố định độ dài

`' '` là một ký tự khoảng trắng, khác chuỗi rỗng. Nhưng hàm `TRIM` có thể loại bỏ toàn bộ dấu cách và cho ra chuỗi độ dài 0, sau đó Oracle xem kết quả đó là `NULL`:

```sql
SELECT
    LENGTH('   ') AS before_trim,
    LENGTH(TRIM('   ')) AS after_trim,
    CASE
        WHEN TRIM('   ') IS NULL THEN 'TRIM RESULT IS NULL'
        ELSE 'TRIM RESULT HAS TEXT'
    END AS trim_state
FROM dual;
```

Kết quả: `BEFORE_TRIM` là 3, `AFTER_TRIM` là `NULL`. Đây là lý do phép kiểm tra “để trống hoặc chỉ nhập khoảng trắng” thường cần kết hợp `TRIM` với `IS NULL`.

Kiểu `CHAR(n)` cố định độ dài thường có quy tắc **blank padding** cho giá trị được lưu và cho một số phép so sánh. Chẳng hạn `'A'` trong cột `CHAR(5)` có thể được lưu như `'A    '`. Đừng suy ra chuỗi chứa dấu cách là `NULL`: giá trị toàn dấu cách vẫn không phải `NULL` khi được lưu như nội dung ký tự. Khi viết ứng dụng, nên nắm rõ khác biệt `CHAR` và `VARCHAR2` về padding, độ dài và so sánh; với dữ liệu text biến độ dài, `VARCHAR2` thường dễ sử dụng hơn.

### 2.3. Ngoại lệ quan trọng: CLOB rỗng có thể khác `NULL`

Oracle hỗ trợ **large object (LOB)** như `CLOB`. Hàm `EMPTY_CLOB()` tạo một locator LOB rỗng với độ dài 0, **không đồng nghĩa với giá trị LOB `NULL`**:

```sql
SELECT
    CASE
        WHEN EMPTY_CLOB() IS NULL THEN 'NULL'
        ELSE 'NOT NULL'
    END AS clob_state,
    DBMS_LOB.GETLENGTH(EMPTY_CLOB()) AS clob_length
FROM dual;
```

Trong trường hợp được hỗ trợ theo cách gọi trên, `CLOB_STATE` là `NOT NULL` và `CLOB_LENGTH` bằng 0. Đây là khác biệt quan trọng giữa **zero-length LOB** và **zero-length character string** của `VARCHAR2`/`CHAR`.

Vì vậy, phát biểu đúng là: *Oracle hiện xem chuỗi ký tự độ dài 0 như `NULL` đối với các giá trị ký tự thông thường; một LOB rỗng được tạo đúng cách có thể có độ dài 0 mà không phải `NULL`.*

### 2.4. PL/SQL và tham số ứng dụng

Quy tắc chuỗi rỗng cũng xuất hiện khi dùng biến `VARCHAR2` trong PL/SQL:

```sql
DECLARE
    v_text VARCHAR2(20) := '';
BEGIN
    IF v_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('v_text is NULL');
    END IF;
END;
/
```

Trong ứng dụng Java dùng JDBC, một giá trị `String` có độ dài 0 được bind vào cột `VARCHAR2` của Oracle không nên được kỳ vọng sẽ lưu thành một chuỗi rỗng phân biệt với SQL `NULL`. Cần thiết kế rõ contract giữa frontend, API và database cho các trạng thái **field bị bỏ qua**, **null**, **empty** và **blank**.

## 3. Logic ba giá trị: TRUE, FALSE và UNKNOWN

SQL sử dụng **three-valued logic (3VL)** trong các điều kiện có khả năng xuất hiện `NULL`:

- **TRUE:** biểu thức được xác định là đúng.
- **FALSE:** biểu thức được xác định là sai.
- **UNKNOWN:** không thể xác định TRUE/FALSE từ dữ liệu hiện có, thường do một toán hạng là `NULL`.

`UNKNOWN` là **giá trị logic của biểu thức điều kiện**, không phải chuỗi `'UNKNOWN'` lưu trong bảng. Trong SQL, `NULL` có thể tạo ra UNKNOWN khi tham gia so sánh.

### 3.1. So sánh bằng `=` và `<>` với `NULL`

| Biểu thức | Kết quả logic |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 7` | FALSE |
| `5 = NULL` | UNKNOWN |
| `5 <> NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL <> NULL` | UNKNOWN |
| `NULL = ''` | UNKNOWN, vì `''` được xử lý như `NULL` |

Hai giá trị thiếu dữ liệu **không được coi là bằng nhau bởi toán tử `=` thông thường**. SQL không thể chứng minh chúng cùng đại diện cho một giá trị thực. Vì vậy, để kiểm tra cột không có giá trị, hãy dùng:

```sql
WHERE phone_number IS NULL
```

Hoặc ngược lại:

```sql
WHERE phone_number IS NOT NULL
```

**Tránh**:

```sql
WHERE phone_number = NULL

-- Oracle cũng không dùng mẫu này để tìm chuỗi rỗng:
WHERE phone_number = ''
```

Hai điều kiện trên đều không trả về TRUE cho những hàng có `NULL`.

### 3.2. Bảng chân trị của NOT

| P | NOT P |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Do đó, **`NOT (col = 10)` không tự bao gồm `col IS NULL`**, vì `NOT UNKNOWN` vẫn là UNKNOWN.

### 3.3. Bảng chân trị của AND

| P | Q | P AND Q |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

Ví dụ `FALSE AND UNKNOWN = FALSE`: một vế đã chắc chắn sai nên toàn bộ điều kiện AND không thể đúng, bất kể vế kia chưa biết.

### 3.4. Bảng chân trị của OR

| P | Q | P OR Q |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

Ví dụ `TRUE OR UNKNOWN = TRUE`: chỉ cần một vế đã chắc chắn đúng.

### 3.5. Tự quan sát UNKNOWN bằng CASE

SQL client không nhất thiết in ra từ `UNKNOWN`. Ta có thể nhận diện nó bằng biểu thức `CASE`:

```sql
SELECT CASE
           WHEN CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER)
               THEN 'TRUE'
           WHEN NOT (CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER))
               THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS comparison_result
FROM dual;
```

Kết quả là `UNKNOWN`. Cả điều kiện trong `WHEN` đầu tiên lẫn điều kiện phủ định thứ hai đều **không TRUE**, nên `ELSE` được chọn.

> Trong một searched `CASE`, Oracle chọn nhánh `WHEN` khi điều kiện là **TRUE**. Khi điều kiện là FALSE hoặc UNKNOWN, Oracle xét nhánh kế tiếp. Nếu không nhánh nào TRUE và không có `ELSE`, kết quả của `CASE` là `NULL`.

## 4. `WHERE` và `HAVING` giữ lại những dòng nào?

Điều quan trọng nhất khi đọc truy vấn SQL là: **`WHERE` chỉ giữ các hàng có điều kiện TRUE**. Hàng cho FALSE **hoặc UNKNOWN** đều bị loại khỏi kết quả.

Giả sử có bảng `LAB_TICKETS`:

| ID | STATUS |
| ---: | --- |
| 1 | `OPEN` |
| 2 | `DONE` |
| 3 | `NULL` |

Truy vấn:

```sql
SELECT id, status
FROM lab_tickets
WHERE status <> 'DONE';
```

Chỉ trả hàng 1 (`OPEN`). Hàng 3 có `STATUS <> 'DONE'` là UNKNOWN, nên **không được trả về**, dù nó cũng không chứa giá trị `DONE`.

Nếu yêu cầu nghiệp vụ là “mọi ticket chưa DONE, kể cả chưa có trạng thái”, phải viết:

```sql
SELECT id, status
FROM lab_tickets
WHERE status <> 'DONE'
   OR status IS NULL;
```

Ngược lại, nếu yêu cầu “chỉ ticket có trạng thái xác định và chưa DONE”, điều kiện `status <> 'DONE'` là đúng.

### 4.1. `BETWEEN`, `LIKE`, `IN` cũng có thể cho UNKNOWN

Những predicate thông thường như `price > 100`, `created_at < DATE '2026-01-01'`, `name LIKE 'A%'` và `score BETWEEN 50 AND 100` sẽ không thành TRUE khi chính giá trị cột cần xét là `NULL`.

```sql
SELECT id
FROM lab_tickets
WHERE status IN ('OPEN', 'WAITING');
```

Hàng có `STATUS IS NULL` không được giữ. Nếu muốn bao gồm hàng thiếu status, phải thêm `OR status IS NULL`.

### 4.2. Searched CASE và Simple CASE

**Searched CASE** cho phép kiểm tra `IS NULL`:

```sql
SELECT id,
       CASE
           WHEN status IS NULL THEN 'MISSING'
           WHEN status = 'DONE' THEN 'COMPLETE'
           ELSE 'OTHER'
       END AS status_label
FROM lab_tickets;
```

Trong **simple CASE**, viết `WHEN NULL` không phải cách kiểm tra thiếu dữ liệu:

```sql
SELECT CASE status
           WHEN NULL THEN 'MISSING'
           WHEN 'DONE' THEN 'COMPLETE'
           ELSE 'OTHER'
       END AS status_label
FROM lab_tickets;
```

Đối với status `NULL`, simple CASE dùng phép so khớp bình thường và không chọn `WHEN NULL`; nhánh `ELSE` được thực thi. Hãy dùng searched CASE khi một nhánh cần xác định `IS NULL`.

### 4.3. `HAVING` cũng cần suy nghĩ về NULL

`HAVING` lọc **các nhóm** sau khi aggregate; điều kiện phải TRUE để nhóm được giữ. Ví dụ:

```sql
SELECT department_id, SUM(bonus) AS total_bonus
FROM employee_bonus
GROUP BY department_id
HAVING SUM(bonus) > 1000;
```

Nếu mọi `BONUS` trong một nhóm đều `NULL`, `SUM(bonus)` trả `NULL`; điều kiện `NULL > 1000` là UNKNOWN nên nhóm đó bị loại. Có thể dùng `HAVING COALESCE(SUM(bonus), 0) > 1000` nếu nghiệp vụ cho phép coi tổng không có giá trị là 0.

## 5. `NVL`, `COALESCE`, `NVL2` và `NULLIF`

Oracle có các hàm xử lý `NULL`, nhưng **thay giá trị thiếu bằng một giá trị mặc định sẽ làm thay đổi ngữ nghĩa**. Chỉ dùng khi biết rõ ý nghĩa nghiệp vụ.

### 5.1. `NVL(expression, replacement)`

`NVL` trả `replacement` nếu `expression` là `NULL`; ngược lại trả `expression`:

```sql
SELECT NVL(CAST(NULL AS NUMBER), 0) AS missing_as_zero,
       NVL(CAST(NULL AS VARCHAR2(20)), '(chua co)') AS missing_as_text
FROM dual;
```

Ví dụ hiển thị `NULL` thành 0 có thể phù hợp cho **bảng báo cáo**, nhưng có thể không đúng nếu 0 nghĩa là một số tiền được xác định. Đối với số liệu tài chính, “không biết giá” khác “giá bằng 0”.

### 5.2. `COALESCE`: giá trị không NULL đầu tiên

`COALESCE` trả biểu thức không `NULL` đầu tiên trong danh sách:

```sql
SELECT COALESCE(
           CAST(NULL AS VARCHAR2(30)),
           'ten hien thi mac dinh',
           'backup'
       ) AS display_name
FROM dual;
```

`COALESCE` hữu ích khi ưu tiên nhiều nguồn dữ liệu, ví dụ số điện thoại đã xác minh rồi số điện thoại phụ, sau cùng là thông báo chưa có. Các biểu thức cần có kiểu dữ liệu tương thích với quy tắc suy luận/chuyển kiểu của Oracle.

`COALESCE` dùng đánh giá ngắn mạch (short-circuit) theo thứ tự biểu thức. Với `NVL`, không nên giả định mọi biểu thức thay thế có tác động phụ đều được bỏ qua khi giá trị đầu không NULL. Tránh đưa các lời gọi có side effects vào cả hai nhánh chỉ để tạo giá trị hiển thị.

### 5.3. `NVL2`: hai nhánh cho có/không có giá trị

```sql
SELECT NVL2(
           CAST(NULL AS VARCHAR2(10)),
           'HAS VALUE',
           'MISSING'
       ) AS label
FROM dual;
```

`NVL2(expr, when_not_null, when_null)` chọn nhánh thứ hai hoặc thứ ba tùy `expr` có `NULL` hay không. Có thể viết lại bằng searched `CASE` khi muốn dễ hiểu hơn.

### 5.4. `NULLIF(a, b)`: chuyển hai giá trị bằng nhau thành NULL

`NULLIF(a, b)` trả `NULL` khi `a = b` là TRUE; nếu khác nhau, trả `a`. Một tình huống hay dùng là tránh phép chia cho 0:

```sql
SELECT sales_amount / NULLIF(item_count, 0) AS sales_per_item
FROM sales_summary;
```

Nếu `ITEM_COUNT = 0`, mẫu số trở thành `NULL` và thương số trở thành `NULL` thay vì phát sinh chia cho 0. Nhưng đó cũng có nghĩa kết quả biểu diễn “không thể tính” và cần được ứng dụng xử lý, **không phải tự động xem là 0**.

**Đừng dùng `NULLIF(column, '')` với kỳ vọng phân biệt rõ `''` và `NULL` trong Oracle**: `''` vốn được xem như `NULL`. Khi muốn chuẩn hóa chuỗi chỉ có khoảng trắng, có thể dùng `TRIM` kết hợp `IS NULL` hoặc quy tắc nhập liệu rõ ràng.

### 5.5. Cẩn trọng với giá trị sentinel

Giả sử `quantity` có thể bằng -1 như một giá trị đặc biệt hợp lệ. Cách viết:

```sql
WHERE NVL(quantity, -1) = -1
```

sẽ trộn lẫn **quantity là NULL** với **quantity thực sự bằng -1**. Nếu muốn tìm null, dùng `quantity IS NULL`. Nếu nghiệp vụ muốn cả hai, mô tả rõ:

```sql
WHERE quantity IS NULL OR quantity = -1
```

Việc bọc cột trong hàm cũng có thể ảnh hưởng khả năng Oracle sử dụng index theo cách thông thường; hãy xét execution plan và các index phù hợp khi lọc bảng lớn.

## 6. Phép nối chuỗi với NULL là ngoại lệ đáng nhớ

Trong Oracle, toán tử nối chuỗi `||` có hành vi riêng khi một bên là `NULL` hoặc chuỗi độ dài 0:

```sql
SELECT
    'Ma: ' || CAST(NULL AS VARCHAR2(20)) AS label_1,
    CAST(NULL AS VARCHAR2(20)) || 'X' AS label_2,
    CAST(NULL AS VARCHAR2(20)) ||
        CAST(NULL AS VARCHAR2(20)) AS label_3
FROM dual;
```

Theo hành vi hiện hành, `LABEL_1` chứa `'Ma: '`, `LABEL_2` chứa `'X'`, còn `LABEL_3` là `NULL`. Đây là một ngoại lệ đối với ý tưởng “bất cứ phép toán nào có NULL đều cho NULL”.

Tuy nhiên **nối chuỗi không phải kiểm tra NULL**. Nếu ứng dụng cần ghi “không có mã” khi mã trống, hãy nói rõ trong `CASE` hoặc `COALESCE`:

```sql
SELECT CASE
           WHEN tracking_code IS NULL THEN '(chua co ma)'
           ELSE 'Ma: ' || tracking_code
       END AS tracking_label
FROM shipments;
```

Đừng phụ thuộc việc nối với `NULL` tạo ra chuỗi trống để quyết định nghiệp vụ.

## 7. Aggregate và GROUP BY xử lý NULL khác phép so sánh

Trong SQL, các aggregate thông dụng có quy tắc riêng:

- `COUNT(*)` đếm **mọi hàng** trong tập/nhóm, kể cả hàng có tất cả cột `NULL`.
- `COUNT(column)` chỉ đếm những hàng mà **column không `NULL`**.
- `COUNT(DISTINCT column)` đếm số giá trị phân biệt **không `NULL`**.
- `SUM(column)`, `AVG(column)`, `MIN(column)`, `MAX(column)` thông thường **bỏ qua các giá trị `NULL`**.
- Nếu không có giá trị không `NULL` nào để tổng hợp, `SUM`/`AVG`/`MIN`/`MAX` trả `NULL`, trong khi `COUNT(column)` trả 0.

### 7.1. Ví dụ COUNT và AVG

Xét dữ liệu:

| ID | BONUS |
| ---: | ---: |
| 1 | 100 |
| 2 | `NULL` |
| 3 | 300 |

```sql
WITH sample_data (id, bonus) AS (
    SELECT 1, 100 FROM dual UNION ALL
    SELECT 2, CAST(NULL AS NUMBER) FROM dual UNION ALL
    SELECT 3, 300 FROM dual
)
SELECT
    COUNT(*) AS total_rows,
    COUNT(bonus) AS known_bonus_count,
    SUM(bonus) AS bonus_sum,
    AVG(bonus) AS avg_known_bonus,
    AVG(NVL(bonus, 0)) AS avg_treat_missing_as_zero
FROM sample_data;
```

Kết quả dự kiến:

| TOTAL_ROWS | KNOWN_BONUS_COUNT | BONUS_SUM | AVG_KNOWN_BONUS | AVG_TREAT_MISSING_AS_ZERO |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 2 | 400 | 200 | khoảng 133,33 |

`AVG(bonus)` tính trên **hai** giá trị biết được, không tự lấy 0 cho hàng thiếu dữ liệu. `AVG(NVL(bonus, 0))` có ý nghĩa thống kê khác: nó chủ động coi hàng thiếu là 0. Việc chọn biểu thức nào là quyết định nghiệp vụ.

### 7.2. GROUP BY và DISTINCT gom NULL theo nhóm

Trong `GROUP BY`, các hàng có cùng biểu thức nhóm là `NULL` được gom vào **một nhóm NULL**:

```sql
WITH sample_data (team) AS (
    SELECT 'A' FROM dual UNION ALL
    SELECT 'A' FROM dual UNION ALL
    SELECT CAST(NULL AS VARCHAR2(10)) FROM dual UNION ALL
    SELECT CAST(NULL AS VARCHAR2(10)) FROM dual
)
SELECT team, COUNT(*) AS members
FROM sample_data
GROUP BY team
ORDER BY team NULLS LAST;
```

Kết quả gồm nhóm `A` có 2 hàng và một nhóm `NULL` có 2 hàng. Điều này **không mâu thuẫn** với `NULL = NULL` là UNKNOWN: `GROUP BY` và `DISTINCT` áp dụng quy tắc xác định nhóm/trùng lặp riêng, không phải chỉ dùng phép `=` trong điều kiện `WHERE`.

Tương tự, `SELECT DISTINCT team ...` thường chỉ xuất hiện một hàng `NULL` nếu nguồn có nhiều hàng `NULL`.

### 7.3. ORDER BY và vị trí của NULL

Oracle hỗ trợ điều khiển vị trí `NULL`:

```sql
SELECT order_id, shipped_at
FROM orders
ORDER BY shipped_at ASC NULLS LAST;

SELECT order_id, shipped_at
FROM orders
ORDER BY shipped_at DESC NULLS FIRST;
```

Trong Oracle, nếu không chỉ rõ, **`ASC` mặc định `NULLS LAST`**, còn **`DESC` mặc định `NULLS FIRST`**. Nên viết rõ `NULLS FIRST`/`NULLS LAST` khi logic hiển thị hoặc phân trang phụ thuộc thứ tự các hàng thiếu dữ liệu. Để phân trang ổn định, còn cần thêm cột sắp xếp phụ đủ phân biệt khi nhiều hàng cùng giá trị.

## 8. NULL trong JOIN và truy vấn con

### 8.1. INNER JOIN với khóa NULL

Với điều kiện join thông thường:

```sql
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON c.customer_id = o.customer_id;
```

Nếu `o.customer_id` là `NULL`, biểu thức `c.customer_id = o.customer_id` thường cho UNKNOWN, nên không tạo match từ điều kiện đó. **Hai cột đều NULL cũng không match bằng `=`.**

Nếu nghiệp vụ muốn coi hai giá trị thiếu giống nhau trong một phép đối chiếu, cần chủ động viết **NULL-safe comparison**. Ví dụ dùng searched `CASE` hoặc predicate:

```sql
ON (
       a.external_code = b.external_code
    OR (a.external_code IS NULL AND b.external_code IS NULL)
   )
```

Trong điều kiện `ON`, chỉ TRUE tạo match, vì vậy mẫu trên có thể coi hai `NULL` là khớp nhau. Nhưng hãy cân nhắc: việc nối tất cả các hàng không có mã với nhau có thể tạo **nhiều dòng kết quả ngoài ý muốn**, nhất là nếu có nhiều hàng `NULL` ở cả hai bảng. Kết nối các khóa thiếu theo kiểu này chỉ hợp lý khi nghiệp vụ xác nhận `NULL` thực sự cùng đại diện một nhóm.

### 8.2. OUTER JOIN và bẫy lọc trong WHERE

`LEFT JOIN` giữ các hàng bên trái, kể cả khi không có đối tượng phù hợp bên phải. Với các hàng không match, cột của phía phải xuất hiện `NULL` trong kết quả.

Ví dụ:

```sql
SELECT c.customer_id, p.payment_id
FROM customers c
LEFT JOIN payments p
  ON p.customer_id = c.customer_id
WHERE p.status = 'PAID';
```

Các hàng khách hàng không có payment sẽ bị `WHERE p.status = 'PAID'` loại vì biểu thức là UNKNOWN. Kết quả có thể giống inner join theo điều kiện này, không còn giữ mọi khách hàng.

Nếu yêu cầu là **hiển thị tất cả khách hàng và chỉ ghép payment đã thanh toán**, hãy đặt điều kiện ở `ON`:

```sql
SELECT c.customer_id, p.payment_id
FROM customers c
LEFT JOIN payments p
  ON p.customer_id = c.customer_id
 AND p.status = 'PAID';
```

Đây là **hai bài toán khác nhau**. Trước khi di chuyển predicate từ `WHERE` sang `ON`, phải xác nhận tập kết quả thực sự mong muốn.

### 8.3. Bẫy `NOT IN` khi tập con chứa NULL

`NOT IN` với một tập chứa `NULL` là lỗi logic rất thường gặp:

```sql
SELECT 3 AS candidate
FROM dual
WHERE 3 NOT IN (1, 2, NULL);
```

Truy vấn **không trả hàng nào**. Về logic:

```text
3 NOT IN (1, 2, NULL)
  tương đương
3 <> 1 AND 3 <> 2 AND 3 <> NULL
  = TRUE AND TRUE AND UNKNOWN
  = UNKNOWN
```

Vì `WHERE` chỉ giữ TRUE, hàng bị loại. Một `NULL` trong tập con có thể làm `NOT IN` không trả những hàng được mong đợi, ngay cả khi giá trị đang xét khác mọi giá trị không NULL.

Khi cần tìm bản ghi **không có bản ghi liên quan**, có thể ưu tiên `NOT EXISTS`:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers b
    WHERE b.customer_id = c.customer_id
);
```

`NOT EXISTS` kiểm tra không tồn tại hàng thỏa điều kiện tương quan, nên một hàng trong `blocked_customers` có `customer_id NULL` không tự “đầu độc” toàn bộ phép lọc. Tuy nhiên nếu `c.customer_id` có thể `NULL`, điều kiện `=` cũng không match; hãy bổ sung quy tắc `IS NULL` phù hợp nếu nghiệp vụ cần loại/giữ khóa thiếu dữ liệu.

Nếu nhất định dùng `NOT IN`, có thể lọc `NULL` ở subquery:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers b
    WHERE b.customer_id IS NOT NULL
);
```

Nhưng mẫu trên vẫn có vấn đề với **`c.customer_id NULL`**. Điều kiện chính xác phụ thuộc việc có muốn coi hàng bên trái thiếu mã là hợp lệ không; đối với khóa chính, `NOT NULL` thường giúp loại sự mơ hồ.

### 8.4. `IN (NULL)` và `NOT (column = value)`

`value IN (NULL)` không phải cách tìm `value NULL`; kết quả so sánh không trở thành TRUE. Tương tự, `NOT (status = 'DONE')` không trả hàng thiếu status vì `NOT UNKNOWN = UNKNOWN`. Để lọc cả trạng thái khác và trạng thái thiếu, viết biểu thức `OR status IS NULL` rõ ràng.

## 9. NULL trong ràng buộc dữ liệu

### 9.1. NOT NULL và PRIMARY KEY

Một cột `NOT NULL` phải có giá trị không NULL. Vì `''` thành `NULL` trong Oracle, cột `VARCHAR2 NOT NULL` cũng không chấp nhận chuỗi rỗng theo quy tắc hiện hành:

```sql
CREATE TABLE lab_required_code (
    code VARCHAR2(20) NOT NULL
);

-- Lệnh sau sẽ bị từ chối vì '' được xem như NULL:
INSERT INTO lab_required_code (code) VALUES ('');
```

**PRIMARY KEY** bao gồm yêu cầu không NULL và tính duy nhất. Do đó khóa chính không nhận giá trị `NULL`. Không nên dùng một khóa có thể thiếu dữ liệu làm primary key rồi hy vọng Oracle tự coi hai NULL là khác nhau.

### 9.2. UNIQUE và NULL

Với **UNIQUE constraint trên một cột nullable**, Oracle có thể chấp nhận **nhiều hàng có `NULL`**. Đó không phải là cách Oracle coi `NULL = NULL` là TRUE, mà là quy tắc ràng buộc duy nhất đối với giá trị thiếu.

```sql
CREATE TABLE lab_unique_email (
    id    NUMBER PRIMARY KEY,
    email VARCHAR2(100) UNIQUE
);

INSERT INTO lab_unique_email VALUES (1, NULL);
INSERT INTO lab_unique_email VALUES (2, NULL);
```

Hai hàng trên có thể cùng tồn tại. Nhưng hai hàng có cùng một email **không NULL** sẽ vi phạm ràng buộc UNIQUE.

**Cẩn trọng với UNIQUE nhiều cột:** Oracle có quy tắc riêng đối với **compound unique key** có các thành phần NULL; đừng áp câu “UNIQUE cho phép vô hạn bản ghi trùng nhau nếu có một cột NULL” cho mọi khóa nhiều cột. Với khóa ghép, các tổ hợp mà phần không NULL trùng nhau có thể bị coi là trùng theo quy tắc của Oracle. Hãy thiết kế ràng buộc dựa trên tổ hợp giá trị có nghĩa nghiệp vụ và kiểm chứng bằng dữ liệu mẫu.

### 9.3. CHECK chỉ bác bỏ FALSE, UNKNOWN có thể được chấp nhận

Một **CHECK constraint** trong SQL chấp nhận hàng khi điều kiện kiểm tra không đánh giá thành FALSE. Vì vậy, `UNKNOWN` do `NULL` thường **không vi phạm CHECK**.

```sql
CREATE TABLE lab_scores (
    student_id NUMBER PRIMARY KEY,
    score      NUMBER,
    CONSTRAINT ck_score_positive CHECK (score >= 0)
);

INSERT INTO lab_scores (student_id, score) VALUES (1, NULL);
```

Hàng có `SCORE NULL` được chấp nhận: `score >= 0` là UNKNOWN, không phải FALSE. Nếu yêu cầu điểm bắt buộc và không âm, phải khai báo **cả hai**:

```sql
CREATE TABLE lab_required_scores (
    student_id NUMBER PRIMARY KEY,
    score NUMBER NOT NULL,
    CONSTRAINT ck_required_score CHECK (score >= 0)
);
```

Khi cần chuỗi không NULL và không toàn dấu cách:

```sql
CREATE TABLE lab_nonblank_name (
    id NUMBER PRIMARY KEY,
    display_name VARCHAR2(100) NOT NULL,
    CONSTRAINT ck_nonblank_name
        CHECK (TRIM(display_name) IS NOT NULL)
);
```

`TRIM('   ')` là `NULL`, nên `IS NOT NULL` là FALSE và hàng toàn dấu cách bị bác bỏ. Đây là ví dụ kiểm soát blank theo khoảng trắng mặc định; nếu nghiệp vụ cần loại cả tab hoặc nhiều loại Unicode whitespace, cần quy tắc chuẩn hóa phù hợp hơn.

### 9.4. FOREIGN KEY nullable

Một foreign key một cột có `NULL` thường được chấp nhận nếu không có ràng buộc `NOT NULL` riêng: hàng thiếu giá trị tham chiếu chưa yêu cầu tìm một khóa cha tương ứng. Nếu quan hệ là bắt buộc, cần thêm `NOT NULL`. Với foreign key nhiều cột, quy tắc với các thành phần NULL cần được xem xét theo ngữ nghĩa khóa ghép và thiết kế dữ liệu cụ thể.

## 10. NULL, index và hiệu năng truy vấn

Oracle B-tree index thông thường có hành vi đặc biệt với `NULL`: **không lưu một khóa khi tất cả các cột khóa của index đều NULL**. Với index một cột:

```sql
CREATE INDEX idx_lab_email
    ON lab_empty_string(description);
```

Những hàng có `DESCRIPTION NULL` không tạo một entry khóa một-cột theo cách thông thường trong index này. Vì thế, predicate `description IS NULL` không phải lúc nào cũng được hỗ trợ bằng truy cập trực tiếp qua index B-tree một cột đó. Oracle có thể chọn full table scan hoặc đường khác tùy cấu trúc index, thống kê và plan.

Với index nhiều cột, nếu **còn ít nhất một cột khóa có giá trị không NULL**, entry có thể được ghi vào index theo quy tắc của Oracle. Function-based index và các thiết kế index khác có thể thay đổi khả năng hỗ trợ predicate `IS NULL`. Đừng kết luận “Oracle không bao giờ dùng index cho `IS NULL`” — điều đó quá rộng.

Ngoài ra, khi viết:

```sql
WHERE NVL(description, 'MISSING') = 'MISSING'
```

bạn đã bọc cột trong một hàm, có thể làm thay đổi khả năng sử dụng index thông thường; đồng thời nếu `MISSING` là chuỗi hợp lệ, điều kiện trộn hai tình huống khác nhau. Dùng `description IS NULL` khi mục đích chính xác là tìm dữ liệu thiếu.

Khi đánh giá hiệu năng, cần xem **execution plan thực tế**, thống kê dữ liệu và độ chọn lọc. Các khuyến nghị index chỉ nên đưa ra sau khi đã hiểu truy vấn và workload.

## 11. NULL trong mã ứng dụng Java và tầng API

Trong Java, một `String` có thể là `null` hoặc `""`, và hai trạng thái này **khác nhau ở bộ nhớ ứng dụng**. Nhưng khi ghi vào cột `VARCHAR2` của Oracle, giá trị `""` có thể được xử lý như SQL `NULL` theo quy tắc hiện hành.

Ví dụ ý tưởng với JDBC:

```java
String note = ""; // Chuỗi Java dài 0, khác null trong Java.

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO lab_empty_string (id, description) VALUES (?, ?)")) {
    ps.setInt(1, 10);
    ps.setString(2, note);
    ps.executeUpdate();
}
```

Nếu cột và driver xử lý theo ngữ nghĩa Oracle thông thường, giá trị được lưu/đọc ở cột `VARCHAR2` không còn phân biệt được trạng thái “Java empty string” với SQL `NULL`. Khi đọc bằng `ResultSet.getString(...)`, cần hiểu khả năng kết quả là Java `null` và sử dụng các phương thức như `wasNull()` khi cần phân biệt một SQL `NULL` với giá trị mặc định của phương thức getter cho các kiểu nguyên thủy.

**Thiết kế API cần nói rõ bốn trường hợp dễ lẫn:**

| Dữ liệu đầu vào | Ý nghĩa có thể được định nghĩa | Đề xuất xử lý |
| --- | --- | --- |
| Trường không xuất hiện trong JSON PATCH | Không thay đổi giá trị đang lưu | Phân biệt với yêu cầu xóa giá trị |
| `"note": null` | Xóa/đặt thiếu giá trị theo contract | Ghi `NULL` nếu cột nullable và quy tắc cho phép |
| `"note": ""` | Chuỗi rỗng có chủ đích | Quyết định reject, normalize về NULL hoặc lưu mô hình riêng nếu cần phân biệt |
| `"note": "   "` | Chỉ có khoảng trắng | Xác định có trim/kiểm tra blank trước khi lưu hay không |

Nếu nghiệp vụ **thật sự yêu cầu phân biệt “chưa nhập” với “đã nhập nhưng cố ý để trống”**, không thể dựa vào hai giá trị `NULL` và `''` trong một cột `VARCHAR2` theo hành vi Oracle hiện tại. Có thể thiết kế thêm cột trạng thái, giá trị enum/flag hoặc một mô hình dữ liệu rõ nghĩa. Không tự sử dụng sentinel khó nhận biết như dấu cách để giả lập chuỗi rỗng.

Trong Java/Spring, xác thực `@NotNull`, `@NotEmpty` và `@NotBlank` (khi sử dụng Jakarta Validation) có những ý nghĩa khác nhau ở tầng ứng dụng. Chúng không thay thế hoàn toàn các ràng buộc dữ liệu Oracle; mọi đường ghi vào database vẫn phải tôn trọng contract.

## 12. Thực hành có thể chạy không cần tạo bảng

Các ví dụ sau dùng `DUAL` và `WITH` để tránh thay đổi dữ liệu. Bạn có thể chạy trong SQL Developer, SQLcl hoặc SQL*Plus. SQL*Plus dùng dấu `;` để kết thúc câu lệnh SQL; với PL/SQL block cần cú pháp gửi block phù hợp.

### Bước 1 — So sánh NULL, chuỗi rỗng và khoảng trắng

```sql
WITH sample (id, text_value) AS (
    SELECT 1, CAST(NULL AS VARCHAR2(10)) FROM dual UNION ALL
    SELECT 2, '' FROM dual UNION ALL
    SELECT 3, ' ' FROM dual UNION ALL
    SELECT 4, 'X' FROM dual
)
SELECT
    id,
    CASE WHEN text_value IS NULL
         THEN 'NULL'
         ELSE 'NOT NULL' END AS value_state,
    LENGTH(text_value) AS text_length,
    CASE WHEN TRIM(text_value) IS NULL
         THEN 'BLANK OR MISSING'
         ELSE 'HAS CONTENT' END AS normalized_state
FROM sample
ORDER BY id;
```

Dự đoán kết quả trước khi chạy:

| ID | VALUE_STATE | TEXT_LENGTH | NORMALIZED_STATE |
| ---: | --- | ---: | --- |
| 1 | NULL | `NULL` | BLANK OR MISSING |
| 2 | NULL | `NULL` | BLANK OR MISSING |
| 3 | NOT NULL | 1 | BLANK OR MISSING |
| 4 | NOT NULL | 1 | HAS CONTENT |

Mục đích là nhìn rõ `''` đi vào cùng nhóm với `NULL`, trong khi dấu cách chỉ bị coi là blank sau bước `TRIM`.

### Bước 2 — Quan sát UNKNOWN

```sql
WITH sample (id, n) AS (
    SELECT 1, 10 FROM dual UNION ALL
    SELECT 2, 20 FROM dual UNION ALL
    SELECT 3, CAST(NULL AS NUMBER) FROM dual
)
SELECT
    id,
    CASE
        WHEN n = 10 THEN 'TRUE'
        WHEN NOT (n = 10) THEN 'FALSE'
        ELSE 'UNKNOWN'
    END AS is_ten
FROM sample
ORDER BY id;
```

Hàng `N=10` có TRUE, hàng `N=20` có FALSE, hàng `N=NULL` có UNKNOWN. Nếu thêm `WHERE n <> 10` ở cấp truy vấn ngoài, hàng NULL sẽ bị loại.

### Bước 3 — Trải nghiệm bẫy NOT IN

```sql
WITH candidates (n) AS (
    SELECT 1 FROM dual UNION ALL
    SELECT 2 FROM dual UNION ALL
    SELECT 3 FROM dual
)
SELECT n
FROM candidates
WHERE n NOT IN (1, NULL);
```

Kết quả không có hàng nào: `1 <> 1` là FALSE, còn với `2` và `3` biểu thức chứa so sánh với NULL nên không TRUE.

Thay bằng:

```sql
WITH candidates (n) AS (
    SELECT 1 FROM dual UNION ALL
    SELECT 2 FROM dual UNION ALL
    SELECT 3 FROM dual
)
SELECT c.n
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1
    FROM (
        SELECT 1 AS blocked_n FROM dual
        UNION ALL
        SELECT CAST(NULL AS NUMBER) FROM dual
    ) b
    WHERE b.blocked_n = c.n
)
ORDER BY c.n;
```

Kết quả có 2 và 3: bản ghi blocked có NULL không làm tất cả candidate biến mất. Trong ví dụ, candidate là các số không NULL, nên không có sự nhập nhằng về khóa phía trái.

### Bước 4 — Phân biệt COUNT và AVG

```sql
WITH scores (score) AS (
    SELECT 100 FROM dual UNION ALL
    SELECT 200 FROM dual UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT
    COUNT(*) AS row_count,
    COUNT(score) AS known_count,
    AVG(score) AS avg_known,
    AVG(NVL(score, 0)) AS avg_missing_as_zero
FROM scores;
```

Dự đoán: `ROW_COUNT=3`, `KNOWN_COUNT=2`, `AVG_KNOWN=150` và `AVG_MISSING_AS_ZERO=100`. Giải thích vì sao hai giá trị AVG diễn đạt **hai cách hiểu khác nhau**.

### Bước 5 — Ràng buộc CHECK và NOT NULL

Không cần tạo bảng để lý giải:

```sql
CREATE TABLE lab_null_constraint (
    id NUMBER PRIMARY KEY,
    age NUMBER CHECK (age >= 0),
    nickname VARCHAR2(30) NOT NULL
);
```

Nếu chọn chạy ví dụ này trong schema lab:

- `AGE=NULL` có thể được chấp nhận nếu nickname hợp lệ, vì `age >= 0` là UNKNOWN.
- `AGE=-1` bị CHECK bác bỏ.
- `NICKNAME=''` bị NOT NULL bác bỏ vì Oracle xem chuỗi rỗng là NULL.
- `NICKNAME=' '` vẫn qua được NOT NULL, trừ khi bổ sung điều kiện loại chuỗi toàn dấu cách.

Nếu chỉ cần học lý thuyết, không cần chạy `CREATE TABLE`. Không chạy trên schema production hoặc ghi đè object có tên trùng.

## 13. Những lỗi thường gặp và cách viết đúng

| Mục tiêu | Cách dễ sai | Cách phù hợp hơn |
| --- | --- | --- |
| Tìm giá trị thiếu | `col = NULL` | `col IS NULL` |
| Tìm chuỗi rỗng trong `VARCHAR2` Oracle | `col = ''` | `col IS NULL` nếu ngữ nghĩa đang dùng coi chuỗi rỗng là thiếu |
| Tìm giá trị đã có | `col <> NULL` | `col IS NOT NULL` |
| Tìm tất cả status khác DONE, gồm cả thiếu | `status <> 'DONE'` | `status <> 'DONE' OR status IS NULL` |
| Tìm row chưa xuất hiện ở bảng con | `NOT IN (SELECT key ...)` khi key có NULL | `NOT EXISTS` với điều kiện tương quan đúng, hoặc loại NULL có chủ đích |
| Tính trung bình giá trị biết được | `AVG(NVL(value, 0))` | `AVG(value)` nếu “thiếu” không nghĩa là số 0 |
| Tìm text toàn khoảng trắng | `text_col = ''` | `TRIM(text_col) IS NULL` khi muốn gom NULL và blank |
| Kiểm tra hai giá trị nullable có giống nhau | `a = b` | So sánh NULL-safe có xét cả `a IS NULL AND b IS NULL` |
| Tránh giá trị NULL ở bảng | Chỉ dùng `CHECK (col > 0)` | Thêm `NOT NULL` nếu bắt buộc |
| Lọc phía phải của LEFT JOIN nhưng giữ mọi hàng bên trái | Đặt mọi điều kiện của phía phải ở `WHERE` | Xét đặt điều kiện ở `ON` theo yêu cầu nghiệp vụ |
| Lưu phân biệt empty và missing | Dùng `''` và `NULL` trong một cột `VARCHAR2` | Thiết kế trạng thái bổ sung hoặc kiểu/mô hình dữ liệu thích hợp |

Không có một phép biến đổi máy móc đúng cho mọi truy vấn. Chẳng hạn `NVL(col,0)` có thể phù hợp trong báo cáo tổng số lượng nhưng sai khi xác định “đã biết giá trị chưa”; `NOT EXISTS` thường tránh bẫy NULL của `NOT IN` nhưng vẫn cần xác định ý nghĩa khóa thiếu bên trái.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Trong Oracle, kết quả của `LENGTH('')` là 0 hay NULL? Vì sao `LENGTH(' ')` lại khác?

**Câu 2.** Với `x=NULL`, biểu thức `x <> 'DONE'` là FALSE hay UNKNOWN? `WHERE` có trả hàng đó không?

**Câu 3.** Dựa vào bảng chân trị, cho biết `TRUE OR UNKNOWN`, `FALSE AND UNKNOWN` và `NOT UNKNOWN`.

**Câu 4.** Một bảng có ba hàng `BONUS`: 10, 20 và NULL. `COUNT(*)`, `COUNT(BONUS)`, `AVG(BONUS)` khác nhau thế nào?

**Câu 5.** Vì sao `WHERE id NOT IN (SELECT blocked_id FROM blacklist)` có thể không trả hàng nào khi `blacklist.blocked_id` chứa NULL? Viết cách khác nếu `id` ở bảng ngoài là primary key.

**Câu 6.** `CHECK (score >= 0)` có cấm `score=NULL` không? Cần bổ sung ràng buộc nào để buộc có điểm?

**Câu 7.** Hai giá trị `NULL` có được ghép với nhau bằng `JOIN ... ON a.code=b.code` không? Nếu chủ động muốn match những mã đều thiếu, bạn phải quan tâm nguy cơ kết quả nào?

**Câu 8.** Ở ứng dụng Java, một trường có thể là `null` và `""`. Vì sao không thể mặc định hai trạng thái này vẫn phân biệt được sau khi lưu vào cột `VARCHAR2` của Oracle?

**Câu 9.** Vì sao `EMPTY_CLOB()` là ví dụ cho thấy không nên tổng quát mọi giá trị “độ dài 0” đều là `NULL` trong toàn bộ hệ kiểu dữ liệu Oracle?

**Câu 10.** Một `LEFT JOIN` đang giữ mọi khách hàng, nhưng sau khi thêm `WHERE payment.status = 'PAID'` thì khách hàng không có payment biến mất. Giải thích bằng logic ba giá trị và cách viết khi muốn giữ mọi khách hàng.

## 15. Mô hình ghi nhớ

```text
       NULL = không có giá trị xác định
                  │
                  ├── khác 0, '0', ' ', 'N/A'
                  │
                  └── trong Oracle, '' hiện được xem như NULL
                       với giá trị ký tự thông thường

       So sánh bằng =, <> với NULL
                  │
                  ▼
                UNKNOWN
                  │
          ┌───────┼─────────┐
          ▼       ▼         ▼
       WHERE    AND/OR     NOT
       chỉ giữ  dùng 3VL   UNKNOWN vẫn UNKNOWN
       TRUE

       Công cụ rõ nghĩa:
       IS NULL / IS NOT NULL
       CASE / NVL / COALESCE / NULLIF
       COUNT(*) khác COUNT(column)
       NOT EXISTS tránh nhiều bẫy NOT IN có NULL
       CHECK và UNIQUE có quy tắc NULL riêng
```

Ba nguyên tắc quan trọng nhất khi làm việc với Oracle:

1. **Dữ liệu thiếu phải được xử lý có chủ đích.** Không dùng phép `= NULL` hoặc `= ''` để kiểm tra một cột thiếu giá trị.
2. **UNKNOWN không phải FALSE.** Trong `WHERE`, cả FALSE và UNKNOWN đều bị loại; trong `AND`/`OR`/`NOT`, UNKNOWN có bảng chân trị riêng.
3. **Quy tắc NULL phụ thuộc vào phép toán và ngữ cảnh.** Aggregate, `GROUP BY`, `UNIQUE`, `CHECK`, outer join, nối chuỗi và LOB rỗng có những quy tắc riêng cần biết.

Khi thiết kế schema, viết SQL hoặc ánh xạ dữ liệu từ Java vào Oracle, hãy xác định rõ trường hợp nào là “chưa biết”, “không áp dụng”, “để trống”, “toàn dấu cách” và “giá trị thực bằng 0”. Những quyết định đó giúp truy vấn đúng kết quả, ràng buộc đúng dữ liệu và tránh lỗi khó phát hiện ở tầng ứng dụng.
