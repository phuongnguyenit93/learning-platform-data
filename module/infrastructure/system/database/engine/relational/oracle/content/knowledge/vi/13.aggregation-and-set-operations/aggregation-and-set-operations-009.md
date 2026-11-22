# Điều kiện tương thích kiểu dữ liệu giữa các nhánh tập hợp trong Oracle

## 1. Vì sao các nhánh UNION phải tương thích kiểu?

Một báo cáo có thể cần hợp nhất khách hàng từ hai hệ thống, ghép các giao dịch hiện tại với dữ liệu lịch sử, hoặc lấy phần giao/hiệu giữa hai danh sách mã. Trong Oracle SQL, các toán tử tập hợp như `UNION`, `UNION ALL`, `INTERSECT` và `MINUS` kết hợp kết quả của nhiều câu `SELECT` thành một tập kết quả.

Ví dụ đơn giản:

```sql
SELECT employee_id
FROM current_employees
UNION ALL
SELECT employee_id
FROM former_employees;
```

Hai câu SELECT có cùng một cột kết quả và cả hai cột đều mang kiểu dữ liệu tương thích. Nhưng nếu một nhánh trả `NUMBER`, nhánh kia trả `VARCHAR2`, Oracle không mặc định chuyển đổi xuyên nhóm kiểu chỉ vì chuỗi trông giống số:

```sql
-- Có thể gặp ORA-01790:
SELECT 100 AS item_id FROM dual
UNION ALL
SELECT '200' AS item_id FROM dual;
```

`100` là literal số, còn `'200'` là literal ký tự. Khi kết hợp bằng toán tử tập hợp, các biểu thức ở cùng vị trí phải tương thích theo quy tắc kiểu dữ liệu của Oracle.

Bài học thuộc chương **Gom nhóm và tập hợp**, tập trung vào:

- Điều kiện về số lượng và thứ tự cột giữa các nhánh.
- Quy tắc nhóm kiểu dữ liệu (datatype groups) của Oracle.
- Chuyển đổi số theo độ ưu tiên kiểu số.
- Chuẩn hóa `CHAR`, `VARCHAR2`, `NCHAR`, `NVARCHAR2`.
- Xử lý `DATE`, `TIMESTAMP`, `NULL` và literal.
- Dùng `CAST` và các hàm chuyển đổi để thống nhất kiểu kết quả.
- Nhận biết lỗi thường gặp như `ORA-01789` và `ORA-01790`.

Mục tiêu không chỉ là làm cho câu SQL chạy được, mà còn bảo đảm **kiểu kết quả phản ánh đúng ý nghĩa dữ liệu** và không làm mất thông tin khi hợp nhất.

## 2. Các toán tử tập hợp và điều kiện cấu trúc

Oracle hỗ trợ các toán tử tập hợp phổ biến:

| Toán tử | Ý nghĩa |
|---|---|
| `UNION` | Hợp hai tập kết quả và loại bỏ các hàng trùng |
| `UNION ALL` | Hợp hai tập kết quả, giữ cả hàng trùng |
| `INTERSECT` | Lấy các hàng xuất hiện trong cả hai tập |
| `MINUS` | Lấy các hàng thuộc tập bên trái nhưng không thuộc tập bên phải |

Các toán tử này có điểm chung: mỗi nhánh phải trả về cùng số cột và các cột tương ứng phải có kiểu tương thích.

### 2.1. Số cột phải bằng nhau

```sql
-- Hai nhánh có cùng một cột:
SELECT employee_id
FROM current_employees
UNION
SELECT employee_id
FROM former_employees;
```

Ví dụ sai:

```sql
-- Nhánh đầu có 2 cột, nhánh sau chỉ có 1:
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT employee_id
FROM former_employees;
```

Oracle báo lỗi:

```text
ORA-01789: query block has incorrect number of result columns
```

Nếu nghiệp vụ cần hai cột, hãy bổ sung biểu thức tương ứng ở nhánh còn thiếu, có thể dùng NULL được CAST về kiểu thích hợp:

```sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT employee_id, CAST(NULL AS VARCHAR2(100)) AS employee_name
FROM former_employees;
```

Không thêm một giá trị placeholder tùy tiện như `'N/A'` nếu NULL mới đúng ý nghĩa “không có tên trong nguồn này”.

### 2.2. Thứ tự cột phải tương ứng về ý nghĩa

Toán tử tập hợp ghép cột theo **vị trí**, không ghép theo tên alias:

```sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT department_id, department_name
FROM departments;
```

Câu SQL có thể hợp lệ về số lượng và kiểu, nhưng kết quả không có nghĩa nếu cột thứ nhất ở nhánh đầu là mã nhân viên còn cột thứ nhất ở nhánh sau là mã phòng ban. Alias của nhánh đầu thường quyết định tên cột đầu ra; alias ở nhánh sau không làm Oracle tự sắp xếp lại các cột.

Trước khi viết `UNION`, hãy xác định hợp đồng kết quả:

| Vị trí | Ý nghĩa thống nhất | Nhánh A | Nhánh B |
|---:|---|---|---|
| 1 | Mã đối tượng | `customer_id` | `legacy_customer_id` |
| 2 | Tên hiển thị | `customer_name` | `old_name` |
| 3 | Ngày tạo | `created_at` | `imported_at` |
| 4 | Nguồn dữ liệu | literal `'CURRENT'` | literal `'LEGACY'` |

Mỗi nhánh phải đặt biểu thức đúng vị trí và chuẩn hóa về kiểu phù hợp.

## 3. Quy tắc nhóm kiểu dữ liệu của Oracle

Với toán tử tập hợp, Oracle kiểm tra kiểu dữ liệu của các biểu thức tương ứng. Các kiểu có thể được chuyển đổi trong cùng nhóm theo quy tắc của Oracle, nhưng **không được giả định Oracle tự chuyển đổi giữa các nhóm kiểu khác nhau**.

Ví dụ điển hình:

```sql
-- NUMBER và VARCHAR2 thuộc hai nhóm kiểu khác nhau:
SELECT 1 AS value FROM dual
UNION ALL
SELECT '1' AS value FROM dual;
```

Truy vấn có thể báo:

```text
ORA-01790: expression must have same datatype as corresponding expression
```

Ngay cả khi `'1'` có thể chuyển thành NUMBER trong một phép tính hoặc phép so sánh khác, điều đó **không có nghĩa** Oracle sẽ tự chuyển kiểu cho nhánh của một set operator.

### 3.1. Nhóm số

Các kiểu số như `NUMBER`, `BINARY_FLOAT`, `BINARY_DOUBLE` thuộc nhóm numeric. Oracle áp dụng quy tắc độ ưu tiên kiểu số khi các nhánh có kiểu số khác nhau.

### 3.2. Nhóm ký tự

Các kiểu ký tự như `CHAR`, `VARCHAR2`, `NCHAR`, `NVARCHAR2` có quy tắc tương thích ký tự riêng. Oracle có thể chuyển đổi trong phạm vi kiểu ký tự tương thích, nhưng cần chú ý khác biệt giữa database character set và national character set, độ dài và kiểu đầu ra.

### 3.3. Nhóm ngày giờ

Các kiểu `DATE` và `TIMESTAMP` mô tả dữ liệu ngày giờ nhưng có độ chính xác khác nhau. Khi hợp nhất các cột thời gian, hãy chọn một kiểu kết quả thống nhất. Ví dụ, nếu cần giữ phần lẻ giây, chuẩn hóa các nhánh về `TIMESTAMP`; nếu chuyển về `DATE`, phần lẻ giây sẽ mất.

Đối với `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE`, phải xác định semantics múi giờ cần giữ. Không ép về `TIMESTAMP` không timezone chỉ để làm hết lỗi kiểu nếu nghiệp vụ cần offset/region.

### 3.4. Không dựa vào chuyển đổi ngầm giữa nhóm

Các ví dụ sau thể hiện những trường hợp cần chuẩn hóa:

| Nhánh trái | Nhánh phải | Vấn đề |
|---|---|---|
| `NUMBER` | `VARCHAR2` | Numeric và character |
| `DATE` | `VARCHAR2` | Ngày giờ và ký tự |
| `TIMESTAMP` | `NUMBER` | Ngày giờ và số |
| `NUMBER` | `DATE` | Số và ngày giờ |

Hãy chuyển đổi có chủ đích trước khi kết hợp, thay vì chờ Oracle đoán.

## 4. Nhóm NUMBER: numeric precedence và kiểu kết quả

Oracle có thứ tự ưu tiên giữa các kiểu số phổ biến:

```text
BINARY_DOUBLE
      >
BINARY_FLOAT
      >
NUMBER
```

Khi các biểu thức tương ứng thuộc nhóm numeric nhưng khác kiểu, Oracle chuyển các biểu thức về kiểu có độ ưu tiên cao hơn theo quy tắc của toán tử tập hợp.

Ví dụ minh họa:

```sql
SELECT CAST(10 AS NUMBER) AS numeric_value
FROM dual
UNION ALL
SELECT CAST(20 AS BINARY_DOUBLE) AS numeric_value
FROM dual;
```

Kiểu số kết quả được xác định theo numeric precedence; trong ví dụ này `BINARY_DOUBLE` có độ ưu tiên cao hơn `NUMBER`.

### 4.1. Vì sao phải quan tâm đến BINARY_FLOAT/BINARY_DOUBLE?

`NUMBER` là kiểu số thập phân của Oracle, phù hợp với nhiều dữ liệu nghiệp vụ cần độ chính xác thập phân như tiền tệ. `BINARY_FLOAT` và `BINARY_DOUBLE` là kiểu số dấu phẩy động nhị phân. Khi một nhánh đưa kiểu binary floating point vào set operation, kiểu kết quả có thể trở thành binary floating point.

Điều này có thể ảnh hưởng:

- Độ chính xác biểu diễn số thập phân.
- Cách hiển thị và làm tròn.
- Cách ứng dụng JDBC nhận giá trị.
- Các phép tính tiếp theo trên kết quả hợp nhất.

Nếu nghiệp vụ cần `NUMBER(12,2)`, hãy chuẩn hóa **mọi nhánh** về kiểu này thay vì để một nhánh `BINARY_DOUBLE` làm thay đổi kiểu kết quả:

```sql
SELECT CAST(current_amount AS NUMBER(12, 2)) AS amount
FROM current_orders
UNION ALL
SELECT CAST(legacy_amount AS NUMBER(12, 2)) AS amount
FROM legacy_orders;
```

Chỉ dùng precision/scale phù hợp với giới hạn nghiệp vụ. `CAST` có thể làm tròn hoặc báo lỗi khi giá trị vượt giới hạn; không chọn kiểu đích nhỏ hơn dữ liệu thật.

### 4.2. Chuỗi số phải parse thành số, không chỉ nhìn giống số

Sai:

```sql
SELECT 100 AS amount FROM dual
UNION ALL
SELECT '200' AS amount FROM dual;
```

Đúng nếu `'200'` thực sự là dữ liệu số:

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT TO_NUMBER('200', '999') AS amount
FROM dual;
```

Nếu chuỗi chứa dấu thập phân/phân nhóm theo locale, cần format model và NLS parameter:

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM dual;
```

Kết quả ở nhánh thứ hai là số 1234.56. Nếu chuỗi nguồn có dữ liệu sai, `TO_NUMBER` sẽ báo lỗi; không nên che lỗi bằng cách chuyển sang ký tự chỉ để set operation chạy.

## 5. Nhóm ký tự: CHAR, VARCHAR2 và kiểu national

Các kiểu ký tự có thể khác nhau về độ dài cố định/biến thiên, padding, character set và semantics BYTE/CHAR. Vì vậy, khi hợp nhất nguồn dữ liệu, nên chuẩn hóa kiểu kết quả.

### 5.1. CHAR và VARCHAR2

Ví dụ:

```sql
SELECT CAST('A' AS CHAR(5)) AS item_code
FROM dual
UNION ALL
SELECT CAST('B' AS VARCHAR2(20)) AS item_code
FROM dual;
```

Trong các trường hợp ký tự thông thường, Oracle xác định kiểu kết quả ký tự theo quy tắc của các biểu thức: `CHAR` cùng độ dài có thể cho kết quả `CHAR`; nếu độ dài `CHAR` khác nhau hoặc có `VARCHAR2`, kết quả có thể là `VARCHAR2` với độ dài phù hợp. Không dựa vào padding của `CHAR` để giữ mã định danh; nếu mã có số 0 ở đầu hoặc khoảng trắng có ý nghĩa, hãy định nghĩa kiểu và quy tắc chuẩn hóa rõ.

Ví dụ chuẩn hóa về `VARCHAR2(20)`:

```sql
SELECT CAST(current_code AS VARCHAR2(20)) AS item_code
FROM current_items
UNION ALL
SELECT CAST(legacy_code AS VARCHAR2(20)) AS item_code
FROM legacy_items;
```

### 5.2. NCHAR và NVARCHAR2

`NCHAR` và `NVARCHAR2` dùng national character set. Nếu một nhánh trả kiểu national còn nhánh khác trả kiểu ký tự thông thường, hãy xác định rõ kiểu kết quả mong muốn và dùng `CAST`/chuyển đổi phù hợp. Không mặc định rằng mọi kiểu ký tự khác nhau đều có thể kết hợp mà không ảnh hưởng character set hoặc metadata đầu ra.

Ví dụ nếu hợp đồng đầu ra là `NVARCHAR2`:

```sql
SELECT CAST(current_name AS NVARCHAR2(100)) AS display_name
FROM current_customers
UNION ALL
SELECT CAST(legacy_name AS NVARCHAR2(100)) AS display_name
FROM legacy_customers;
```

Nếu hợp đồng đầu ra là `VARCHAR2` trên database dùng `AL32UTF8`, chuẩn hóa cả hai nhánh về `VARCHAR2` có thể phù hợp hơn. Quyết định phải dựa trên schema, character set và ứng dụng tiêu thụ dữ liệu.

### 5.3. Không biến mã định danh thành NUMBER nếu cần giữ số 0 đầu

Hai giá trị:

```text
'00125'
'125'
```

có thể là hai mã khác nhau, dù khi parse thành NUMBER đều trở thành 125. Nếu hợp nhất dữ liệu mã sản phẩm, mã bưu chính hoặc mã khách hàng, kiểu đúng thường là ký tự:

```sql
SELECT CAST(current_code AS VARCHAR2(30)) AS code
FROM current_products
UNION ALL
SELECT CAST(legacy_code AS VARCHAR2(30)) AS code
FROM legacy_products;
```

Chỉ chuyển thành NUMBER khi trường dữ liệu thực sự mang ý nghĩa số và các số 0 ở đầu không có ý nghĩa.

## 6. DATE và TIMESTAMP: thống nhất độ chính xác thời gian

### 6.1. Hợp nhất DATE và TIMESTAMP

Một nguồn cũ có `DATE`, nguồn mới có `TIMESTAMP`:

```sql
SELECT CAST(old_event_date AS TIMESTAMP) AS event_time
FROM old_events
UNION ALL
SELECT new_event_timestamp AS event_time
FROM new_events;
```

Đưa `DATE` lên `TIMESTAMP` giữ ngày/giờ đến giây và phần lẻ giây được bổ sung bằng 0. Nếu cần giữ phần lẻ giây từ nguồn mới, không ép cả hai nhánh xuống `DATE`.

### 6.2. Khi cần kết quả DATE

Nếu hợp đồng đầu ra chỉ cần đến giây:

```sql
SELECT CAST(new_event_timestamp AS DATE) AS event_time
FROM new_events
UNION ALL
SELECT old_event_date AS event_time
FROM old_events;
```

Đây là quyết định có chủ đích: phần lẻ giây của `TIMESTAMP` bị loại khi chuyển về `DATE`.

### 6.3. Không parse ngày bằng chuỗi phụ thuộc NLS

Tránh:

```sql
SELECT '14/11/2026' AS event_date FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date FROM dual;
```

Một nhánh là ký tự, nhánh kia là DATE. Hãy parse chuỗi thành ngày:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

Hoặc chuẩn hóa cả hai về TIMESTAMP nếu hợp đồng đầu ra cần kiểu đó.

### 6.4. Múi giờ là một phần của ý nghĩa dữ liệu

Không nên bỏ timezone chỉ để ép hai nhánh về cùng kiểu:

```sql
-- Cần cân nhắc kỹ trước khi bỏ offset:
CAST(event_time_tz AS TIMESTAMP)
```

Nếu nguồn có `TIMESTAMP WITH TIME ZONE` còn nguồn kia là `TIMESTAMP` không timezone, hãy xác định múi giờ của nhánh không timezone trước. Một giá trị `2026-11-14 16:30:00` không tự cho biết nó là UTC hay giờ Việt Nam.

Nếu kết quả cần giữ thông tin timezone, chuẩn hóa cả hai nhánh về `TIMESTAMP WITH TIME ZONE` theo một quy tắc cụ thể. Nếu chỉ cần mốc UTC, hãy chuyển đổi rõ ràng về UTC trước khi hợp nhất. Không tự gắn `+00:00` cho dữ liệu địa phương chưa xác định timezone.

## 7. NULL trong các nhánh tập hợp: CAST để định nghĩa kiểu

Một nhánh có thể không có dữ liệu cho một cột. Dùng NULL là hợp lý, nhưng nên chỉ định kiểu:

```sql
SELECT customer_id,
       customer_name,
       credit_limit
FROM current_customers
UNION ALL
SELECT legacy_id,
       legacy_name,
       CAST(NULL AS NUMBER(12, 2)) AS credit_limit
FROM legacy_customers;
```

`CAST(NULL AS NUMBER(12,2))` giúp biểu thức ở vị trí thứ ba có kiểu NUMBER rõ ràng.

### 7.1. NULL không có kiểu tường minh trong biểu thức

Ví dụ:

```sql
SELECT CAST(NULL AS DATE) AS closed_at
FROM dual
UNION ALL
SELECT DATE '2026-11-14' AS closed_at
FROM dual;
```

Đây là cách viết rõ ràng cho một cột ngày có thể thiếu giá trị. Đối với kiểu số:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(125.50 AS NUMBER(12, 2)) AS amount
FROM dual;
```

Đối với ký tự:

```sql
SELECT CAST(NULL AS VARCHAR2(100)) AS note
FROM dual
UNION ALL
SELECT CAST('Imported' AS VARCHAR2(100)) AS note
FROM dual;
```

### 7.2. Không dùng NULL thay cho một giá trị giả

Nếu nguồn lịch sử không có `created_at`, `CAST(NULL AS DATE)` thể hiện đúng ý nghĩa “không có ngày tạo trong nguồn này”. Dùng `DATE '1900-01-01'` làm giá trị giả có thể khiến báo cáo hiểu nhầm đó là ngày thật, ảnh hưởng lọc, thống kê và nghiệp vụ.

Nếu ứng dụng muốn hiển thị `N/A`, nên thay thế ở tầng trình bày hoặc dùng `CASE`/`TO_CHAR` có chủ đích; không làm mất bản chất NULL của dữ liệu chỉ để hợp nhất.

## 8. CAST ở từng nhánh: mẫu chuẩn hóa đầu ra

Một cách dễ bảo trì là định nghĩa hợp đồng cột trước, sau đó CAST từng nhánh về cùng kiểu:

```sql
SELECT
    CAST(current_id AS NUMBER(12)) AS entity_id,
    CAST(current_name AS VARCHAR2(100)) AS entity_name,
    CAST(current_created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM current_entities

UNION ALL

SELECT
    CAST(legacy_id AS NUMBER(12)) AS entity_id,
    CAST(legacy_name AS VARCHAR2(100)) AS entity_name,
    CAST(legacy_created_at AS TIMESTAMP(6)) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM legacy_entities;
```

Đoạn SQL giả định dữ liệu nguồn có thể chuyển đổi hợp lệ. Nếu `legacy_id` là chuỗi có ký tự không phải số, `CAST(... AS NUMBER)` có thể thất bại; hãy dùng `TO_NUMBER` theo format phù hợp và xử lý dữ liệu lỗi ở bước staging/validation.

### 8.1. Chuẩn hóa số dạng chuỗi

```sql
SELECT CAST(current_amount AS NUMBER(12, 2)) AS amount
FROM current_payments
UNION ALL
SELECT TO_NUMBER(
           legacy_amount_text,
           'FM999G999G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM legacy_payments;
```

Ở ví dụ này, chuỗi lịch sử được parse theo quy ước cụ thể. Nếu `legacy_amount_text` có giá trị sai, truy vấn có thể lỗi; việc chuẩn hóa kiểu không tự làm sạch dữ liệu.

### 8.2. Chuẩn hóa mã ký tự

```sql
SELECT CAST(current_product_code AS VARCHAR2(30 CHAR)) AS product_code
FROM current_products
UNION ALL
SELECT CAST(legacy_product_code AS VARCHAR2(30 CHAR)) AS product_code
FROM legacy_products;
```

Nếu một nguồn có kiểu `NUMBER`, phải quyết định xem mã có thực sự là số hay không. Chuyển sang `VARCHAR2` có thể làm mất định dạng gốc của mã đã được lưu kiểu số (ví dụ số 0 đầu không còn). Cần chuẩn hóa theo hợp đồng mã, không chỉ theo cú pháp.

## 9. Format model có vai trò gì trong set operators?

Format model không trực tiếp là quy tắc tương thích kiểu. Nó được dùng khi chuyển giữa **văn bản** và **giá trị số/ngày giờ**.

Ví dụ hai nhánh trả về cùng kiểu DATE:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

Format model `DD/MM/YYYY` giúp parse chuỗi đầu tiên thành DATE; sau chuyển đổi, cả hai nhánh đều trả kiểu DATE.

Ngược lại, nếu cần kết quả là văn bản:

```sql
SELECT TO_CHAR(DATE '2026-11-14', 'YYYY-MM-DD') AS event_date_text
FROM dual
UNION ALL
SELECT CAST('2026-11-15' AS VARCHAR2(10)) AS event_date_text
FROM dual;
```

Cả hai nhánh trả về kiểu ký tự. Nhưng lúc này kết quả là **text**, không còn là DATE để so sánh ngày, cộng ngày hay sử dụng hàm thời gian một cách trực tiếp.

### 9.1. Chọn kiểu đầu ra theo nhu cầu tiêu thụ

| Nhu cầu | Kiểu đầu ra phù hợp |
|---|---|
| Sắp xếp/lọc/tính khoảng thời gian | `DATE` hoặc `TIMESTAMP` |
| Tính toán tiền và số lượng | `NUMBER` với precision/scale phù hợp |
| Giữ mã có số 0 đầu | `VARCHAR2` hoặc kiểu ký tự phù hợp |
| Hiển thị ngày theo `DD/MM/YYYY` | Có thể `TO_CHAR` ở lớp báo cáo |
| Gửi timestamp có offset | Kiểu timezone-aware và quy ước UTC/region rõ |
| Cột không có dữ liệu ở một nhánh | `CAST(NULL AS kiểu_đích)` |

Đừng định dạng mọi cột thành chuỗi trước khi `UNION` chỉ để tránh lỗi `ORA-01790`. Cách đó làm mất kiểu gốc và khiến các thao tác phía sau khó đúng hơn.

## 10. Các kiểu dữ liệu đặc biệt và giới hạn của set operators

Không phải mọi kiểu Oracle đều có thể tham gia các toán tử tập hợp theo cách thông thường.

### 10.1. LOB và collection types

Oracle có những giới hạn đối với các kiểu như:

- `BLOB`
- `CLOB`
- `BFILE`
- Kiểu collection như `VARRAY` và nested table

Các kiểu này không được hỗ trợ trực tiếp trong nhiều phép toán tập hợp SQL. `LONG` cũng là kiểu di sản có nhiều hạn chế khi dùng với các toán tử như `UNION`, `INTERSECT`, `MINUS`.

Nếu cần hợp nhất danh sách bản ghi có LOB, thường nên hợp nhất **khóa chính hoặc cột metadata** trước, sau đó truy xuất LOB theo khóa:

```sql
SELECT document_id, source_name
FROM current_documents
UNION ALL
SELECT document_id, source_name
FROM archived_documents;
```

Sau khi có danh sách ID, ứng dụng hoặc một truy vấn tiếp theo có thể đọc nội dung LOB theo từng nguồn. Cách này tránh yêu cầu set operator so sánh trực tiếp nội dung LOB.

### 10.2. Object types và kiểu do người dùng định nghĩa

Các kiểu object do người dùng định nghĩa và collection có quy tắc tương thích riêng, không nên giả định chúng hoạt động như `NUMBER`/`VARCHAR2`. Nếu câu truy vấn trả về object type, cần kiểm tra yêu cầu hỗ trợ của toán tử và phiên bản Oracle; trong nhiều thiết kế, nên chiếu ra các thuộc tính scalar tương ứng rồi hợp nhất.

### 10.3. Kiểm tra phiên bản và tài liệu kiểu dữ liệu

Một số khả năng chuyển đổi/kiểu dữ liệu thay đổi theo phiên bản Oracle. Khi làm việc với LOB, JSON, spatial, object type hoặc các kiểu mở rộng, hãy kiểm tra tài liệu SQL Language Reference của đúng phiên bản đang chạy. Không ép mọi kiểu đặc biệt thành `VARCHAR2` nếu việc đó làm mất dữ liệu, vượt giới hạn độ dài hoặc tạo chi phí chuyển đổi lớn.

## 11. UNION, UNION ALL, INTERSECT và MINUS có khác điều kiện kiểu không?

Về điều kiện tương thích kiểu dữ liệu, các toán tử tập hợp dùng cùng nguyên tắc: số cột tương ứng phải bằng nhau và kiểu phải tương thích. Khác biệt chính giữa chúng nằm ở cách kết hợp hàng:

| Toán tử | Cách xử lý trùng | Yêu cầu tương thích kiểu |
|---|---|---|
| `UNION` | Loại hàng trùng trong kết quả | Có |
| `UNION ALL` | Giữ hàng trùng | Có |
| `INTERSECT` | Trả hàng chung giữa hai tập | Có |
| `MINUS` | Trả hàng chỉ có ở nhánh trái | Có |

`UNION ALL` không phải cách né lỗi kiểu. Ví dụ:

```sql
-- Vẫn không tương thích dù dùng UNION ALL:
SELECT 10 FROM dual
UNION ALL
SELECT '20' FROM dual;
```

Tương tự, `INTERSECT` và `MINUS` cũng không tự chuyển `VARCHAR2` thành `NUMBER` để làm phép so sánh.

### 11.1. Khác biệt trùng lặp không thay đổi hợp đồng cột

```sql
SELECT CAST(10 AS NUMBER) AS value FROM dual
UNION
SELECT CAST(10 AS NUMBER) AS value FROM dual;
```

Kết quả chỉ có một hàng.

```sql
SELECT CAST(10 AS NUMBER) AS value FROM dual
UNION ALL
SELECT CAST(10 AS NUMBER) AS value FROM dual;
```

Kết quả có hai hàng. Cả hai câu vẫn cần kiểu NUMBER tương thích ở vị trí cột thứ nhất.

## 12. ORDER BY và alias trong truy vấn tập hợp

`ORDER BY` của compound query thường đặt **một lần ở cuối** toàn bộ biểu thức:

```sql
SELECT employee_id AS id
FROM current_employees
UNION ALL
SELECT employee_id
FROM former_employees
ORDER BY id;
```

Tên cột đầu ra thường lấy từ nhánh SELECT đầu tiên. Alias ở nhánh sau không định nghĩa lại tên cột kết quả:

```sql
SELECT employee_id AS entity_id
FROM current_employees
UNION ALL
SELECT employee_id AS old_id
FROM former_employees
ORDER BY entity_id;
```

Không đặt `ORDER BY` tùy tiện giữa hai nhánh:

```sql
-- Không viết ORDER BY ở giữa các nhánh như compound query thông thường:
-- SELECT ... FROM current_employees ORDER BY employee_id
-- UNION ALL
-- SELECT ... FROM former_employees;
```

Nếu cần sắp xếp riêng trước một phép xử lý khác, hãy thiết kế subquery/inline view phù hợp. Việc sắp xếp trong một nhánh không thay thế việc sắp xếp kết quả cuối.

## 13. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-01789: query block has incorrect number of result columns` | Các nhánh SELECT có số cột khác nhau | Bổ sung/bỏ cột để mọi nhánh có cùng số lượng |
| `ORA-01790: expression must have same datatype as corresponding expression` | Kiểu ở cùng vị trí không tương thích | Xác định kiểu đích rồi CAST/parse rõ ràng |
| `ORA-00932: inconsistent datatypes` | Một số biểu thức có kiểu không tương thích trong ngữ cảnh chuyển đổi | Kiểm tra kiểu từng biểu thức, chuẩn hóa đầu ra |
| `ORA-01722: invalid number` | Chuỗi nguồn không parse được thành số | Kiểm tra dữ liệu và format/NLS trước `TO_NUMBER` |
| `ORA-01861` hoặc lỗi ORA-018xx | Chuỗi ngày giờ không khớp format hoặc không hợp lệ | Dùng `TO_DATE`/`TO_TIMESTAMP` với format đúng |
| Kết quả mã bị mất số 0 đầu | Mã bị chuyển thành NUMBER | Giữ mã ở kiểu ký tự |
| Timestamp mất phần lẻ giây | Ép TIMESTAMP xuống DATE | Chuẩn hóa về TIMESTAMP nếu cần giữ precision |
| Thời điểm lệch múi giờ | Bỏ timezone hoặc diễn giải timestamp không timezone sai | Xác định timezone và chuẩn hóa rõ |
| Kết quả bị đổi kiểu số | Một nhánh dùng BINARY_FLOAT/BINARY_DOUBLE | CAST các nhánh về NUMBER nếu nghiệp vụ cần |
| NULL có kiểu không rõ hoặc không phù hợp | Dùng NULL trần trong biểu thức kết hợp | `CAST(NULL AS kiểu_đích)` |
| UNION chạy nhưng dữ liệu sai nghĩa | Cột cùng vị trí không cùng ý nghĩa | Xây hợp đồng cột theo vị trí trước khi viết SQL |

### Quy trình xử lý ORA-01790

Khi gặp `ORA-01790`, hãy kiểm tra theo thứ tự:

1. Đếm số biểu thức trong SELECT list của từng nhánh.
2. Đối chiếu cột thứ 1 với cột thứ 1, thứ 2 với thứ 2, v.v.
3. Xem kiểu dữ liệu thực tế của từng biểu thức, không chỉ kiểu cột gốc.
4. Xác định nhóm kiểu và kiểu kết quả mong muốn.
5. Thêm `CAST` hoặc hàm parse ở từng nhánh.
6. Kiểm tra nguy cơ mất precision, số 0 đầu, phần lẻ giây hoặc timezone.
7. Kiểm tra các giá trị nguồn có chuyển đổi được hay không.

Đừng sửa lỗi bằng cách CAST toàn bộ sang `VARCHAR2` trước khi xác định kết quả sẽ được dùng để làm gì.

## 14. Xem kiểu dữ liệu từ data dictionary

Khi không biết cột nguồn có kiểu gì, hãy tra metadata thay vì đoán theo dữ liệu đang hiển thị.

### 14.1. Xem kiểu cột trong schema hiện tại

```sql
SELECT table_name,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       char_length,
       char_used
FROM user_tab_columns
WHERE table_name IN ('CURRENT_ORDERS', 'LEGACY_ORDERS')
ORDER BY table_name, column_id;
```

Các cột metadata hữu ích:

| Cột | Ý nghĩa |
|---|---|
| `DATA_TYPE` | Tên kiểu dữ liệu |
| `DATA_LENGTH` | Độ dài theo byte |
| `DATA_PRECISION` | Precision của kiểu số khi áp dụng |
| `DATA_SCALE` | Scale của kiểu số khi áp dụng |
| `CHAR_LENGTH` | Độ dài theo ký tự của kiểu ký tự |
| `CHAR_USED` | Ngữ nghĩa BYTE (`B`) hoặc CHAR (`C`) khi áp dụng |

Nếu bảng thuộc schema khác và bạn có quyền nhìn thấy metadata, dùng `ALL_TAB_COLUMNS` và lọc thêm `OWNER`. Với góc nhìn quản trị rộng hơn, có thể dùng `DBA_TAB_COLUMNS` nếu được cấp quyền phù hợp.

### 14.2. Xem kiểu biểu thức sau chuyển đổi

Kiểu của biểu thức có thể khác kiểu cột nguồn:

```sql
SELECT CAST(amount_text AS NUMBER(12, 2)) AS amount
FROM import_rows;
```

Kết quả có kiểu NUMBER dù cột gốc là VARCHAR2. Khi kiểm tra set operator, phải xem **kiểu của biểu thức trong SELECT list**, không chỉ đọc metadata cột nguồn.

### 14.3. Kiểm tra kết quả truy vấn bằng công cụ client

SQL Developer, SQLcl hoặc JDBC metadata có thể cho biết kiểu dữ liệu của cột kết quả. Khi truy vấn có `UNION`, hãy kiểm tra kiểu kết quả thực tế sau khi Oracle xác định precedence/character result type, đặc biệt nếu có `BINARY_DOUBLE`, `CHAR` độ dài khác nhau hoặc kiểu national.

## 15. Thiết kế truy vấn hợp nhất dữ liệu thực tế

### 15.1. Hợp nhất khách hàng từ hệ thống mới và cũ

Giả sử:

- `CURRENT_CUSTOMERS.customer_id` là NUMBER.
- `LEGACY_CUSTOMERS.customer_code` là VARCHAR2 nhưng chỉ chứa mã số hợp lệ.
- Hai nguồn có tên khách hàng độ dài khác nhau.
- Nguồn cũ không có `created_at`.

Có thể chuẩn hóa:

```sql
SELECT
    CAST(customer_id AS NUMBER(12)) AS customer_id,
    CAST(customer_name AS VARCHAR2(100)) AS customer_name,
    CAST(created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM current_customers

UNION ALL

SELECT
    TO_NUMBER(customer_code, '999999999999') AS customer_id,
    CAST(legacy_name AS VARCHAR2(100)) AS customer_name,
    CAST(NULL AS TIMESTAMP(6)) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM legacy_customers;
```

Ví dụ giả định `customer_code` có dữ liệu số đúng format. Nếu mã có số 0 đầu mang ý nghĩa, hãy giữ kết quả là VARCHAR2 thay vì TO_NUMBER. Nếu `created_at` nguồn là DATE, CAST lên TIMESTAMP giữ giá trị đến giây và phần lẻ bằng 0.

### 15.2. Hợp nhất số liệu tiền

```sql
SELECT
    CAST(payment_id AS NUMBER(12)) AS payment_id,
    CAST(amount AS NUMBER(14, 2)) AS amount
FROM current_payments

UNION ALL

SELECT
    CAST(old_payment_id AS NUMBER(12)) AS payment_id,
    TO_NUMBER(
        amount_text,
        'FM9G999G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS amount
FROM legacy_payments;
```

Ở đây kết quả cột amount là số, phù hợp cho phép cộng/tổng hợp. Nếu dữ liệu legacy không parse được, cần làm sạch/ghi nhận lỗi ở bước import; không chuyển cột amount sang text chỉ để né lỗi.

### 15.3. Hợp nhất sự kiện từ nhiều vùng thời gian

Nếu cả hai nguồn đã lưu `TIMESTAMP WITH TIME ZONE`, giữ kiểu đó khi kết hợp:

```sql
SELECT event_id,
       event_time_tz
FROM region_a_events
UNION ALL
SELECT event_id,
       event_time_tz
FROM region_b_events;
```

Nếu một nguồn là `TIMESTAMP` không timezone, phải xác định timezone thực tế của nguồn đó và chuyển đổi đúng trước khi hợp nhất. Không có cách CAST nào có thể tự suy ra một vùng thời gian mà dữ liệu không cung cấp.

## 16. Bài thực hành tổng hợp

Các ví dụ sau dùng bảng thử nghiệm tự tạo. Chạy trong schema thực hành có quyền `CREATE TABLE`; không dùng bảng production. Một số câu được ghi là trường hợp cố tình gây lỗi để bạn bỏ comment và quan sát riêng.

### Bước 1. Thử lỗi khác số cột

```sql
-- Cố tình sai: hai nhánh trả số cột khác nhau.
-- SELECT 1 AS id, 'A' AS code FROM dual
-- UNION ALL
-- SELECT 2 AS id FROM dual;
```

Oracle báo `ORA-01789`.

### Bước 2. Thử lỗi khác nhóm kiểu

```sql
-- Cố tình sai: NUMBER và VARCHAR2 ở cùng vị trí.
-- SELECT 1 AS value FROM dual
-- UNION ALL
-- SELECT '2' AS value FROM dual;
```

Oracle có thể báo `ORA-01790`.

### Bước 3. Chuẩn hóa về NUMBER

```sql
SELECT CAST(1 AS NUMBER(10, 2)) AS value
FROM dual
UNION ALL
SELECT CAST(2 AS NUMBER(10, 2)) AS value
FROM dual;
```

Hai nhánh trả cùng kiểu NUMBER(10,2).

### Bước 4. Parse text thành DATE

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS event_date
FROM dual
UNION ALL
SELECT DATE '2026-11-15' AS event_date
FROM dual;
```

Hai nhánh đều trả DATE.

### Bước 5. Dùng NULL có kiểu

```sql
SELECT CAST(100 AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual;
```

Kết quả có một số và một NULL, cùng kiểu NUMBER.

### Bước 6. Quan sát numeric precedence

```sql
SELECT CAST(10 AS NUMBER) AS value
FROM dual
UNION ALL
SELECT CAST(20 AS BINARY_DOUBLE) AS value
FROM dual;
```

Quan sát kiểu kết quả bằng công cụ SQL client hoặc JDBC metadata; kiểu số có độ ưu tiên cao hơn được dùng cho kết quả hợp nhất.

### Bước 7. Tạo bảng hai nguồn

```sql
CREATE TABLE demo_current_source (
    item_id NUMBER,
    item_name VARCHAR2(50),
    amount NUMBER(12, 2),
    created_at DATE
);

CREATE TABLE demo_legacy_source (
    item_code VARCHAR2(20),
    item_name CHAR(30),
    amount_text VARCHAR2(30),
    created_text VARCHAR2(20)
);
```

### Bước 8. Chèn dữ liệu mẫu

```sql
INSERT INTO demo_current_source
VALUES (101, 'Current A', 1250.50, DATE '2026-11-14');

INSERT INTO demo_current_source
VALUES (102, 'Current B', 300.00, DATE '2026-11-15');

INSERT INTO demo_legacy_source
VALUES ('201', 'Legacy A', '1.234,56', '14/11/2026');

INSERT INTO demo_legacy_source
VALUES ('202', 'Legacy B', '450,00', '15/11/2026');

COMMIT;
```

### Bước 9. Hợp nhất với kiểu thống nhất

```sql
SELECT
    CAST(item_id AS NUMBER(12)) AS item_id,
    CAST(item_name AS VARCHAR2(50)) AS item_name,
    CAST(amount AS NUMBER(12, 2)) AS amount,
    CAST(created_at AS TIMESTAMP(6)) AS created_at,
    CAST('CURRENT' AS VARCHAR2(10)) AS source_name
FROM demo_current_source

UNION ALL

SELECT
    TO_NUMBER(item_code, '999999999999') AS item_id,
    CAST(item_name AS VARCHAR2(50)) AS item_name,
    TO_NUMBER(
        amount_text,
        'FM9G999G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS amount,
    CAST(
        TO_DATE(created_text, 'FXDD/MM/YYYY')
        AS TIMESTAMP(6)
    ) AS created_at,
    CAST('LEGACY' AS VARCHAR2(10)) AS source_name
FROM demo_legacy_source;
```

Đầu ra có cùng năm cột theo cùng thứ tự và kiểu đã được chuẩn hóa. Nếu mã legacy là mã định danh có số 0 đầu, thay thiết kế `item_id` đầu ra thành kiểu ký tự ở cả hai nhánh.

### Bước 10. Dọn bảng thử nghiệm

Chỉ sau khi xác nhận đúng bảng vừa tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_legacy_source PURGE;
DROP TABLE demo_current_source PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy trên đối tượng nghiệp vụ hoặc bảng dùng chung.

## 17. Những nguyên tắc nên ghi nhớ

1. **Cùng số cột:** mọi nhánh SELECT phải trả cùng số lượng biểu thức.
2. **Cùng vị trí, cùng ý nghĩa:** cột thứ n của mỗi nhánh phải đại diện cùng một thuộc tính logic.
3. **Tương thích nhóm kiểu:** không dựa vào chuyển đổi ngầm giữa NUMBER và VARCHAR2, hoặc giữa DATE và chuỗi.
4. **Chuẩn hóa kiểu đích:** dùng `CAST` ở từng nhánh khi cần kiểu đầu ra ổn định.
5. **Parse text đúng cách:** dùng `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP` cùng format model/NLS phù hợp.
6. **NULL phải có kiểu khi cần:** dùng `CAST(NULL AS target_type)`.
7. **Giữ precision:** không ép TIMESTAMP xuống DATE hoặc BINARY_DOUBLE xuống NUMBER nếu chưa xác định tác động.
8. **Giữ bản chất mã:** mã có số 0 đầu hoặc ký tự không phải số nên dùng kiểu ký tự.
9. **Không định dạng thành text quá sớm:** `TO_CHAR` dành cho đầu ra hiển thị; dữ liệu dùng để tính toán nên giữ kiểu số/ngày giờ.
10. **UNION ALL vẫn cần tương thích kiểu:** việc giữ bản ghi trùng không làm lỏng quy tắc kiểu dữ liệu.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Hai nhánh `UNION ALL` có thể trả số cột khác nhau không?

**Trả lời:** Không. Mọi nhánh phải trả cùng số lượng biểu thức theo vị trí tương ứng.

**Câu 2.** `SELECT 1 FROM dual UNION ALL SELECT '1' FROM dual` vì sao có thể lỗi?

**Trả lời:** `1` là NUMBER, `'1'` là VARCHAR2. Các biểu thức tương ứng thuộc nhóm kiểu khác nhau; Oracle không tự chuyển đổi xuyên nhóm cho set operator.

**Câu 3.** `UNION ALL` có bỏ qua điều kiện tương thích kiểu vì không loại trùng không?

**Trả lời:** Không. `UNION ALL`, `UNION`, `INTERSECT` và `MINUS` đều cần cấu trúc và kiểu cột tương thích.

**Câu 4.** Khi một nhánh không có ngày tạo, nên dùng gì ở cột ngày?

**Trả lời:** `CAST(NULL AS DATE)` hoặc `CAST(NULL AS TIMESTAMP)` theo kiểu đầu ra đã chọn.

**Câu 5.** Vì sao không nên chuyển mã `'00125'` thành NUMBER trong truy vấn hợp nhất?

**Trả lời:** Khi chuyển thành số, số 0 đầu bị mất; nếu đó là một phần của mã định danh, kết quả sai ý nghĩa.

**Câu 6.** Numeric precedence giữa NUMBER, BINARY_FLOAT và BINARY_DOUBLE theo thứ tự nào?

**Trả lời:** `BINARY_DOUBLE` cao nhất, tiếp theo `BINARY_FLOAT`, rồi `NUMBER`.

**Câu 7.** Khi nguồn có DATE và TIMESTAMP, ép DATE lên TIMESTAMP có làm mất thông tin không?

**Trả lời:** Không làm mất thông tin sẵn có của DATE; phần lẻ giây được bổ sung bằng 0. Chiều TIMESTAMP xuống DATE làm mất phần lẻ giây.

**Câu 8.** Format model có trực tiếp giải quyết ORA-01790 không?

**Trả lời:** Không. Format model chỉ giúp parse/hiển thị dữ liệu. Sau khi parse, cần bảo đảm kiểu kết quả của các nhánh tương thích.

**Câu 9.** Alias ở nhánh SELECT thứ hai có đổi tên cột đầu ra của UNION không?

**Trả lời:** Không. Tên cột đầu ra thường lấy từ nhánh SELECT đầu tiên; các nhánh ghép theo vị trí.

**Câu 10.** Có nên CAST mọi cột thành VARCHAR2 để tránh lỗi kiểu không?

**Trả lời:** Không. Làm vậy có thể mất kiểu số/ngày giờ, làm sai sắp xếp và phép tính. Chọn kiểu đầu ra theo ý nghĩa dữ liệu.

**Câu 11.** Có thể dùng set operator trực tiếp trên CLOB/BLOB/collection như với NUMBER không?

**Trả lời:** Không nên giả định. Oracle có hạn chế với LOB và collection; thường hợp nhất khóa/metadata rồi truy xuất LOB riêng.

**Câu 12.** Khi hai nhánh trả TIMESTAMP WITH TIME ZONE và TIMESTAMP không timezone, điều gì phải làm rõ?

**Trả lời:** Phải xác định timezone của nhánh không timezone và kiểu kết quả cần giữ. Không tự gắn UTC hoặc bỏ offset khi chưa có quy tắc nghiệp vụ.

## 19. Kết luận

Các toán tử `UNION`, `UNION ALL`, `INTERSECT` và `MINUS` kết hợp các tập kết quả theo **vị trí cột**. Mọi nhánh phải trả cùng số cột; các biểu thức tương ứng phải có kiểu tương thích theo quy tắc Oracle. Đặc biệt, Oracle không tự chuyển đổi giữa các nhóm kiểu như `NUMBER` và `VARCHAR2` chỉ vì giá trị văn bản trông giống số. Khi cần, hãy chuẩn hóa rõ ràng bằng `CAST`, `TO_NUMBER`, `TO_DATE` hoặc `TO_TIMESTAMP`.

Hãy định nghĩa hợp đồng đầu ra trước khi viết truy vấn: cột nào là mã, số tiền, ngày giờ, văn bản hoặc NULL; kiểu nào cần được giữ; có yêu cầu precision, số 0 đầu hay timezone hay không. `CAST(NULL AS kiểu_đích)` giúp các nhánh thiếu dữ liệu vẫn có kiểu xác định. Tránh định dạng số/ngày giờ thành chuỗi quá sớm, vì điều đó làm mất khả năng tính toán và so sánh theo kiểu gốc.

Khi gặp `ORA-01789` hoặc `ORA-01790`, kiểm tra số lượng cột, vị trí, kiểu biểu thức và giá trị nguồn theo từng nhánh. Một truy vấn tập hợp tốt không chỉ hết lỗi cú pháp mà còn trả đúng cấu trúc và semantics mà ứng dụng cần.
