# DECODE và khác biệt cần chú ý khi so sánh NULL trong Oracle

Trong Oracle SQL, `NULL` không có nghĩa là số 0, chuỗi rỗng hay một giá trị mặc định. Nó biểu thị **không có giá trị hoặc chưa biết giá trị**. Vì vậy, phép so sánh `NULL = NULL` không trả về `TRUE` mà trả về `UNKNOWN`. Đây là nguồn gốc của nhiều lỗi khi lọc dữ liệu, kiểm tra trạng thái và viết biểu thức điều kiện.

Oracle có hàm `DECODE` với một hành vi đặc biệt: **khi biểu thức cần kiểm tra và một giá trị search đều là NULL, DECODE xem chúng là khớp nhau**. Điều này khác với phép so sánh bằng thông thường và cũng khác cách viết simple `CASE expr WHEN NULL`. Hiểu đúng sự khác biệt giúp chuyển đổi SQL cũ, xử lý cột nullable và tránh kết quả ngoài dự kiến.

Bài học thuộc chủ đề **Hàm và biểu thức** của *Database Engine Relational Oracle*. Nội dung tập trung vào cú pháp và cách đánh giá `DECODE`, semantics NULL, khác biệt với `CASE`/`IS NULL`/`NVL`/`COALESCE`, chuyển kiểu ngầm, kiểu trả về, short-circuit và các tình huống bảo trì SQL legacy.

## 1. NULL trong SQL và logic ba giá trị

Trong SQL, `NULL` biểu thị giá trị không xác định hoặc không hiện diện. Nó không phải một giá trị cụ thể có thể đem so sánh như số hay chuỗi thông thường. Một cột `commission_pct` có thể NULL vì nhân viên không có thông tin hoa hồng hoặc vì hệ thống chưa ghi nhận dữ liệu. SQL không tự phân biệt hai nguyên nhân đó nếu đều được lưu thành NULL.

Điều kiện SQL có thể cho ba kết quả:

| Kết quả | Ý nghĩa |
| --- | --- |
| `TRUE` | Điều kiện được xác định là đúng. |
| `FALSE` | Điều kiện được xác định là sai. |
| `UNKNOWN` | Không đủ thông tin để xác định đúng hay sai, thường do có NULL. |

~~~sql
SELECT
    CASE WHEN NULL = NULL THEN 'TRUE'
         WHEN NULL <> NULL THEN 'FALSE'
         ELSE 'UNKNOWN'
    END AS equality_result,
    CASE WHEN NULL IS NULL THEN 'TRUE'
         ELSE 'FALSE'
    END AS is_null_result
FROM dual;
~~~

Kết quả đầu tiên là `UNKNOWN`; kết quả thứ hai là `TRUE`. Để kiểm tra NULL, hãy dùng `IS NULL` hoặc `IS NOT NULL`:

~~~sql
SELECT employee_id, commission_pct
FROM employees
WHERE commission_pct IS NULL;
~~~

Không viết `WHERE commission_pct = NULL`. Biểu thức đó trả `UNKNOWN` cho mọi hàng và không chọn được hàng nào. Tương tự, `WHERE commission_pct <> NULL` cũng không chọn những hàng khác NULL; hãy viết `IS NOT NULL`.

Trong `WHERE`, chỉ hàng có điều kiện là `TRUE` được giữ. Hàng có điều kiện `FALSE` hoặc `UNKNOWN` đều bị loại. `NOT UNKNOWN` vẫn là `UNKNOWN`, chứ không trở thành TRUE.

## 2. Cú pháp và cách hoạt động của DECODE

`DECODE` so sánh một biểu thức với các giá trị search theo thứ tự. Khi tìm được giá trị khớp đầu tiên, hàm trả về result tương ứng; nếu không có giá trị khớp, hàm trả default nếu được khai báo, nếu không thì trả NULL.

~~~sql
DECODE(
    expression,
    search_1, result_1,
    search_2, result_2,
    ...,
    default_value
)
~~~

Ví dụ:

~~~sql
SELECT employee_id,
       DECODE(
           job_id,
           'IT_PROG', 'Developer',
           'SA_REP',  'Sales',
           'Other'
       ) AS job_group
FROM employees;
~~~

Oracle lần lượt so sánh `job_id` với `'IT_PROG'` rồi `'SA_REP'`. Nếu không khớp cả hai, kết quả là `'Other'`. Nếu bỏ đối số cuối, trường hợp không khớp sẽ trả NULL.

| Thành phần | Vai trò |
| --- | --- |
| `expression` | Giá trị cần so sánh. |
| `search_n` | Giá trị ứng viên được so với expression. |
| `result_n` | Giá trị trả về khi search tương ứng khớp. |
| `default_value` | Kết quả khi không search nào khớp; tùy chọn. |

`DECODE` đánh giá các search theo thứ tự và dùng short-circuit: khi một search khớp, những search sau không cần được đánh giá. Vì thế, thứ tự các cặp search/result ảnh hưởng kết quả nếu có điều kiện chồng lấn hoặc biểu thức search khác nhau.

~~~sql
SELECT DECODE(
           2,
           1, 'First',
           2, 'Second',
           3, 'Third',
           'No match'
       ) AS decoded_value
FROM dual;
~~~

Kết quả là `Second`. Oracle giới hạn `DECODE` ở tối đa **255 components** tính cả expression, các search/result và default. Khi có quá nhiều nhánh hoặc logic phức tạp, nên cân nhắc `CASE` để dễ đọc và bảo trì.

## 3. Khác biệt quan trọng: DECODE xem NULL khớp NULL

**Trong DECODE, hai giá trị NULL được xem là tương đương để tìm kiếm match.**

~~~sql
SELECT
    DECODE(NULL, NULL, 'MATCH', 'NO MATCH') AS decode_result,
    CASE
        WHEN NULL = NULL THEN 'MATCH'
        ELSE 'NO MATCH'
    END AS searched_case_result,
    CASE NULL
        WHEN NULL THEN 'MATCH'
        ELSE 'NO MATCH'
    END AS simple_case_result
FROM dual;
~~~

| Biểu thức | Kết quả |
| --- | --- |
| `DECODE(NULL, NULL, 'MATCH', 'NO MATCH')` | `MATCH` |
| `CASE WHEN NULL = NULL THEN ...` | `NO MATCH` vì điều kiện là UNKNOWN |
| `CASE NULL WHEN NULL THEN ...` | `NO MATCH` vì simple CASE dùng phép so sánh thông thường |

Hai kiểu CASE không giống nhau:

- **Simple CASE:** `CASE expression WHEN value THEN ...`. NULL không match NULL bằng phép so sánh thông thường.
- **Searched CASE:** `CASE WHEN condition THEN ...`. Có thể dùng `IS NULL` để kiểm tra NULL tường minh.

Để viết logic tương đương DECODE, dùng searched CASE:

~~~sql
CASE
  WHEN expression IS NULL THEN 'MATCH'
  WHEN expression = search_value THEN 'MATCH'
  ELSE 'NO MATCH'
END
~~~

Trong ví dụ tổng quát, đặt các điều kiện theo đúng thứ tự ưu tiên nghiệp vụ. Nếu có nhiều search value, viết rõ từng nhánh; không thay `IS NULL` bằng `= NULL`.

### Ví dụ trên bảng có NULL

~~~sql
CREATE TABLE lab_decode_status (
    item_id NUMBER(6) PRIMARY KEY,
    status_code VARCHAR2(20 CHAR)
);

INSERT INTO lab_decode_status VALUES (1, 'A');
INSERT INTO lab_decode_status VALUES (2, 'I');
INSERT INTO lab_decode_status VALUES (3, NULL);
INSERT INTO lab_decode_status VALUES (4, 'A');
COMMIT;

SELECT item_id,
       status_code,
       DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Not assigned',
           'Unknown code'
       ) AS decode_label
FROM lab_decode_status
ORDER BY item_id;
~~~

Hàng có `status_code IS NULL` nhận `Not assigned` vì search thứ ba là NULL. Viết lại bằng searched CASE:

~~~sql
SELECT item_id,
       status_code,
       CASE
         WHEN status_code = 'A' THEN 'Active'
         WHEN status_code = 'I' THEN 'Inactive'
         WHEN status_code IS NULL THEN 'Not assigned'
         ELSE 'Unknown code'
       END AS case_label
FROM lab_decode_status
ORDER BY item_id;
~~~

Hai truy vấn cho cùng phân loại trong ví dụ này. Khi chuyển DECODE phức tạp sang CASE, kiểm tra lại nhánh NULL, thứ tự search, chuyển kiểu và kiểu trả về.

## 4. DECODE không thay thế IS NULL trong mọi ngữ cảnh

Một cách viết sai thường gặp là:

~~~sql
-- Sai mục tiêu: khi status_code NULL, điều kiện không bao giờ TRUE.
SELECT item_id
FROM lab_decode_status
WHERE status_code = NULL;
~~~

Viết đúng:

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NULL;
~~~

Nếu mục tiêu là tạo nhãn, có thể dùng DECODE:

~~~sql
SELECT item_id,
       DECODE(status_code, NULL, 'Missing', 'Present') AS status_label
FROM lab_decode_status;
~~~

Hoặc searched CASE:

~~~sql
SELECT item_id,
       CASE
         WHEN status_code IS NULL THEN 'Missing'
         ELSE 'Present'
       END AS status_label
FROM lab_decode_status;
~~~

**DECODE là một hàm ánh xạ giá trị**, không phải cách thay thế cú pháp kiểm tra NULL ở mọi nơi. Trong `WHERE`, `JOIN ON` hoặc điều kiện ràng buộc, dùng `IS NULL`/`IS NOT NULL` khi đó là điều bạn thực sự muốn diễn đạt.

### NULL trong điều kiện JOIN

Giả sử cần ghép hai bảng theo mã tùy chọn:

~~~sql
SELECT *
FROM table_a a
JOIN table_b b
  ON a.optional_code = b.optional_code;
~~~

Hai hàng có `optional_code` đều NULL **không match** trong phép JOIN trên vì `NULL = NULL` là UNKNOWN. Nếu nghiệp vụ quy định hai giá trị NULL phải được xem như cùng một nhóm để ghép, hãy diễn đạt điều đó rõ:

~~~sql
SELECT *
FROM table_a a
JOIN table_b b
  ON a.optional_code = b.optional_code
  OR (a.optional_code IS NULL AND b.optional_code IS NULL);
~~~

Đây là quyết định nghiệp vụ có tác động tới số hàng JOIN. Không thêm nhánh NULL chỉ để “làm cho giống DECODE”; nhiều hệ thống chủ ý không ghép hai giá trị chưa biết.

## 5. DECODE, CASE, NVL và COALESCE

Các cấu trúc này đều có thể xuất hiện trong logic xử lý NULL nhưng nhiệm vụ không giống nhau:

| Cấu trúc | Mục đích | Cách xử lý NULL |
| --- | --- | --- |
| `DECODE(expr, search, result, ...)` | So khớp expression với nhiều giá trị | NULL trong expression match NULL trong search. |
| `CASE expr WHEN value THEN ...` | Chọn nhánh theo giá trị bằng nhau | NULL không match NULL bằng phép so sánh thông thường. |
| `CASE WHEN expr IS NULL THEN ...` | Chọn nhánh theo điều kiện tùy ý | Kiểm tra NULL tường minh bằng `IS NULL`. |
| `NVL(expr, replacement)` | Thay NULL bằng một giá trị | Không phải hàm nhiều nhánh; chỉ xử lý NULL của expression. |
| `COALESCE(a,b,c,...)` | Trả về biểu thức đầu tiên khác NULL | Chọn giá trị có sẵn đầu tiên. |
| `NULLIF(a,b)` | Trả NULL nếu hai biểu thức bằng nhau, nếu không trả a | Dùng phép so sánh thông thường; không coi hai NULL là bằng nhau. |

~~~sql
SELECT
    DECODE(status_code, NULL, 'Missing', 'Present') AS by_decode,
    CASE WHEN status_code IS NULL
         THEN 'Missing' ELSE 'Present'
    END AS by_case,
    NVL(status_code, 'N/A') AS by_nvl,
    COALESCE(status_code, 'N/A') AS by_coalesce
FROM lab_decode_status;
~~~

`DECODE` và searched `CASE` ở đây tạo nhãn. `NVL` và `COALESCE` thay giá trị NULL bằng chuỗi `N/A`. Một nhóm phân loại, nhóm còn lại trả giá trị thay thế.

### NVL không phải DECODE rút gọn

~~~sql
NVL(status_code, 'UNKNOWN')
~~~

chỉ thay NULL. Nó không thể trực tiếp ánh xạ `'A'` thành `'Active'`, `'I'` thành `'Inactive'` và các giá trị khác thành default như DECODE.

### COALESCE chọn giá trị đầu tiên có sẵn

~~~sql
SELECT COALESCE(
           preferred_phone,
           mobile_phone,
           office_phone,
           'No phone'
       ) AS contact_phone
FROM contacts;
~~~

`COALESCE` chọn giá trị đầu tiên khác NULL theo thứ tự. Nó không so sánh một expression với danh sách search/result. Khi mục tiêu là “chọn giá trị thay thế đầu tiên”, COALESCE thường rõ nghĩa hơn việc lồng nhiều `NVL`.

## 6. Chuyển kiểu ngầm trong DECODE

Một điểm dễ gây lỗi khi bảo trì SQL là **kiểu dữ liệu của expression, search và result không đồng nhất**. Oracle áp dụng quy tắc chuyển kiểu ngầm trong DECODE. Nếu không thiết kế rõ kiểu dữ liệu, truy vấn có thể:

- So sánh theo kiểu không như mong đợi.
- Gặp lỗi chuyển đổi dữ liệu khi chạy.
- Trả kết quả với kiểu dữ liệu khác dự định.
- Có hành vi khác khi đổi thứ tự các cặp search/result.

### Kiểu so sánh phụ thuộc search đầu tiên

Oracle chuyển expression và các search value theo quy tắc kiểu của search đầu tiên trước khi so sánh; có quy tắc numeric precedence riêng khi cặp search-result đầu tiên là numeric. Vì vậy, nên giữ các search cùng kiểu với expression.

Ví dụ an toàn, kiểu chuỗi nhất quán:

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           'Unknown'
       ) AS status_label
FROM lab_decode_status;
~~~

Ví dụ số nhất quán:

~~~sql
SELECT DECODE(
           priority_no,
           1, 'Critical',
           2, 'Normal',
           'Other'
       ) AS priority_label
FROM tasks;
~~~

Tránh trộn chuỗi và số tùy tiện:

~~~sql
-- Không nên dựa vào implicit conversion không rõ ràng.
SELECT DECODE(
           status_code,
           1, 'One',
           'A', 'Letter A',
           'Other'
       )
FROM lab_decode_status;
~~~

Nếu expression là chuỗi nhưng search đầu tiên là số, Oracle có thể phải chuyển kiểu để so sánh. Chuỗi không phải số có thể gây lỗi chuyển đổi. Hãy chuẩn hóa kiểu đầu vào:

~~~sql
SELECT DECODE(
           TO_NUMBER(priority_text),
           1, 'Critical',
           2, 'Normal',
           'Other'
       )
FROM task_import;
~~~

Ví dụ này chỉ an toàn nếu mọi giá trị khác NULL trong `PRIORITY_TEXT` đều chuyển được sang số theo format/NLS dự kiến. Nếu dữ liệu nguồn không sạch, cần validate và parse có kiểm soát trước; không dùng TO_NUMBER như cách “thử xem có phải số” mà không xử lý lỗi.

### Kiểu trả về phụ thuộc result đầu tiên

Oracle xác định kiểu dữ liệu trả về của DECODE dựa trên các result theo quy tắc của hàm. Điểm đặc biệt: **nếu result đầu tiên là NULL literal hoặc có kiểu CHAR, giá trị trả về được chuyển thành VARCHAR2**. Nếu result đầu tiên là kiểu số, quy tắc numeric precedence có thể quyết định kiểu trả về số.

~~~sql
SELECT
    DUMP(DECODE(1, 1, NULL, 2, 100, 0)) AS first_result_null,
    DUMP(DECODE(1, 1, CAST(NULL AS NUMBER), 2, 100, 0))
        AS typed_null_result
FROM dual;
~~~

Ở biểu thức thứ nhất, NULL literal là result đầu tiên nên kết quả được trả dưới dạng VARCHAR2; ở biểu thức thứ hai, NULL được CAST rõ thành NUMBER để giữ kiểu số theo thiết kế. `DUMP` giúp xem mã kiểu dữ liệu nội bộ trong kết quả kiểm tra.

Đối với DECODE trả số, có thể khai báo rõ:

~~~sql
SELECT DECODE(
           status_code,
           'A', CAST(1 AS NUMBER(3,0)),
           'I', CAST(0 AS NUMBER(3,0)),
           CAST(NULL AS NUMBER(3,0))
       ) AS active_flag
FROM lab_decode_status;
~~~

Kiểu trả về rõ ràng giúp JDBC/ORM và các biểu thức phía ngoài xử lý nhất quán. Khi chuyển DECODE legacy sang CASE, hãy kiểm tra kiểu kết quả của CASE theo quy tắc riêng của CASE; không giả định hai hàm luôn suy luận cùng một kiểu.

## 7. Short-circuit và thứ tự các nhánh

Oracle đánh giá các search của DECODE theo thứ tự và dừng khi tìm thấy match. Điều này có thể quan trọng khi search là biểu thức hoặc hàm cần tính toán.

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS label
FROM lab_decode_status;
~~~

Oracle xét lần lượt `'A'`, `'I'` và NULL. Khi một search khớp, các search sau không cần đánh giá. Không nên viết các nhánh có điều kiện chồng lấn mà không xác định thứ tự ưu tiên.

DECODE so khớp giá trị, không phải cấu trúc phù hợp để phân loại theo khoảng. Với điều kiện như “nhỏ hơn 10” hoặc “từ 10 đến 20”, dùng searched CASE:

~~~sql
SELECT CASE
         WHEN salary IS NULL THEN 'Not provided'
         WHEN salary < 3000 THEN 'Entry'
         WHEN salary < 8000 THEN 'Mid'
         ELSE 'Senior'
       END AS salary_band
FROM employees;
~~~

## 8. DECODE trong WHERE và ảnh hưởng tới index

DECODE thường được dùng để tạo giá trị hiển thị trong `SELECT`. Nếu dùng nó bao quanh cột trong `WHERE`, biểu thức có thể làm truy vấn khó tận dụng index thông thường trên cột đó, tùy optimizer và cách biểu thức được viết.

~~~sql
-- Kiểm tra NULL trực tiếp:
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NULL;

-- Cùng mục tiêu nhưng phải tính DECODE trên cột:
SELECT item_id
FROM lab_decode_status
WHERE DECODE(status_code, NULL, 1, 0) = 1;
~~~

Hai câu có thể cùng mục tiêu, nhưng câu đầu diễn đạt trực tiếp điều kiện NULL và thường là lựa chọn nên ưu tiên. Câu thứ hai yêu cầu tính DECODE cho cột trong predicate; một index B-tree thông thường có những đặc tính riêng đối với NULL. Không nên mặc định optimizer luôn biến đổi predicate DECODE thành `IS NULL`.

Nếu mục tiêu là tìm hàng NULL và cột có index, có thể cân nhắc cách thiết kế index phù hợp (ví dụ composite index có thêm cột không NULL hoặc function-based index) dựa trên workload. Đừng tạo index chỉ vì một câu DECODE; hãy đo execution plan và tần suất truy vấn.

### DECODE trong SELECT không nhất thiết gây vấn đề index

~~~sql
SELECT item_id,
       DECODE(status_code, NULL, 'Missing', status_code) AS display_status
FROM lab_decode_status
WHERE item_id = :item_id;
~~~

Ở đây predicate lọc theo `ITEM_ID`, còn DECODE chỉ định dạng giá trị hiển thị sau khi tìm hàng. Nếu có index phù hợp trên khóa item, biểu thức trong projection không nhất thiết ngăn việc sử dụng index đó.

## 9. Những tình huống NULL dễ gây lỗi logic khác

### NOT IN có NULL trong danh sách

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code NOT IN ('A', NULL);
~~~

Với giá trị không phải `'A'`, phép kiểm tra tương đương `status_code <> 'A' AND status_code <> NULL`; vế thứ hai là UNKNOWN nên toàn điều kiện không trở thành TRUE. Kết quả có thể rỗng ngoài dự kiến.

Nếu muốn loại một mã và giữ các giá trị khác NULL:

~~~sql
SELECT item_id
FROM lab_decode_status
WHERE status_code IS NOT NULL
  AND status_code <> 'A';
~~~

Nếu muốn xử lý tập loại trừ từ bảng khác, cân nhắc `NOT EXISTS` và xác định rõ cách xử lý NULL trong khóa đối chiếu.

### Chuỗi rỗng trong Oracle

Oracle hiện xử lý chuỗi ký tự độ dài 0 (`''`) như NULL trong SQL. Vì vậy, với cột ký tự, `DECODE(status_code, NULL, ...)` cũng khớp trường hợp chuỗi rỗng được đưa vào như NULL. Đây là đặc tính Oracle cần lưu ý khi chuyển dữ liệu từ hệ quản trị khác, nơi empty string và NULL có thể là hai giá trị riêng.

## 10. Khi nào nên dùng DECODE và khi nào nên dùng CASE?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Bảo trì câu SQL Oracle legacy đã dùng DECODE | Giữ DECODE nếu semantics đã rõ và được kiểm thử | Tránh thay đổi ngoài ý muốn khi refactor. |
| Ánh xạ một biểu thức sang một số giá trị bằng nhau | DECODE hoặc simple CASE | Cú pháp ngắn, dễ đọc nếu kiểu nhất quán và không cần special NULL behavior. |
| Cần xử lý NULL như một nhánh | Searched CASE với `IS NULL` hoặc DECODE có search NULL | CASE tường minh, DECODE có semantics đặc biệt. |
| Cần điều kiện theo khoảng, AND/OR hoặc nhiều cột | Searched CASE | Thể hiện điều kiện tổng quát. |
| Cần SQL dễ chuyển sang hệ quản trị khác | CASE | CASE là biểu thức chuẩn SQL phổ biến; DECODE là hàm đặc thù Oracle. |
| Cần chọn giá trị không NULL đầu tiên | COALESCE | Diễn đạt đúng ý nghĩa ưu tiên giá trị có sẵn. |
| Chỉ cần thay NULL bằng một giá trị | NVL hoặc COALESCE | Không cần nhiều cặp search/result. |

**Không có quy tắc rằng DECODE luôn nhanh hơn CASE hoặc ngược lại.** Optimizer có thể tối ưu nhiều biểu thức tương đương; ưu tiên semantics rõ ràng, kiểu dữ liệu nhất quán và execution plan phù hợp với workload.

### Mẫu chuyển đổi DECODE sang CASE

~~~sql
SELECT DECODE(
           status_code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS status_label
FROM lab_decode_status;
~~~

Searched CASE tương đương:

~~~sql
SELECT CASE
         WHEN status_code = 'A' THEN 'Active'
         WHEN status_code = 'I' THEN 'Inactive'
         WHEN status_code IS NULL THEN 'Missing'
         ELSE 'Other'
       END AS status_label
FROM lab_decode_status;
~~~

Simple CASE **không tương đương** cho nhánh NULL:

~~~sql
SELECT CASE status_code
         WHEN 'A' THEN 'Active'
         WHEN 'I' THEN 'Inactive'
         WHEN NULL THEN 'Missing'
         ELSE 'Other'
       END AS status_label
FROM lab_decode_status;
~~~

Hàng NULL đi tới `ELSE` vì `CASE status_code WHEN NULL` không sử dụng semantics đặc biệt của DECODE. Khi refactor, hãy thêm searched CASE branch `WHEN status_code IS NULL`.

## 11. DECODE trong báo cáo và conditional aggregation

DECODE thường xuất hiện trong các báo cáo Oracle cũ để biến mã thành nhãn hoặc tính tổng có điều kiện. Với dữ liệu NULL, phải quyết định rõ NULL được xếp vào nhóm nào.

Ví dụ đếm số hàng theo trạng thái:

~~~sql
SELECT
    COUNT(DECODE(status_code, 'A', 1)) AS active_count,
    COUNT(DECODE(status_code, 'I', 1)) AS inactive_count,
    COUNT(DECODE(status_code, NULL, 1)) AS missing_count
FROM lab_decode_status;
~~~

`COUNT(expression)` bỏ qua kết quả NULL. DECODE trả `1` khi khớp và trả NULL khi không khớp (vì không có default), nên mỗi COUNT đếm số hàng của một nhóm. Ở cột `STATUS_CODE` nullable, nhánh search NULL đếm được hàng NULL nhờ semantics riêng của DECODE.

Có thể viết rõ bằng CASE:

~~~sql
SELECT
    SUM(CASE WHEN status_code = 'A' THEN 1 ELSE 0 END) AS active_count,
    SUM(CASE WHEN status_code = 'I' THEN 1 ELSE 0 END) AS inactive_count,
    SUM(CASE WHEN status_code IS NULL THEN 1 ELSE 0 END) AS missing_count
FROM lab_decode_status;
~~~

Hai cách cho cùng mục tiêu trong ví dụ này. CASE thường dễ mở rộng khi điều kiện cần kết hợp nhiều cột hoặc nhiều phép so sánh. Nếu dùng `SUM(DECODE(...))`, hãy bảo đảm biểu thức trả số và xác định default rõ ràng:

~~~sql
SELECT
    SUM(DECODE(status_code, 'A', 1, 0)) AS active_count,
    SUM(DECODE(status_code, 'I', 1, 0)) AS inactive_count,
    SUM(DECODE(status_code, NULL, 1, 0)) AS missing_count
FROM lab_decode_status;
~~~

Ở đây default là 0 nên mỗi hàng đóng góp 0 hoặc 1 vào tổng. Khác với COUNT, SUM cần chú ý trường hợp không có hàng hoặc mọi giá trị là NULL; trong ví dụ này mọi hàng đều trả số 0/1.

## 12. Chuyển đổi SQL legacy có DECODE

Trong hệ thống Oracle lâu năm, DECODE có thể nằm trong SELECT list, WHERE, ORDER BY, GROUP BY, view hoặc materialized view. Không nên thay hàng loạt bằng CASE chỉ dựa trên tìm kiếm văn bản.

### Trình tự chuyển đổi an toàn

1. **Xác định kiểu của expression và search.** Cột là NUMBER, VARCHAR2, DATE hay biểu thức trả kiểu gì? Có implicit conversion không?
2. **Ghi lại hành vi NULL.** Có cặp search NULL không? Expression có thể trả NULL do outer join, hàm hoặc dữ liệu thiếu không?
3. **Ghi lại thứ tự nhánh.** Search có trùng hoặc chồng lấn? Nhánh đầu tiên khớp sẽ quyết định kết quả.
4. **Xác định kiểu result.** Result đầu tiên là CHAR/NULL/numeric? Ứng dụng đang phụ thuộc kiểu trả về nào?
5. **Viết searched CASE tương đương.** Chuyển search NULL thành điều kiện `IS NULL`; các search còn lại thành phép so sánh có kiểu rõ.
6. **So sánh tập kết quả trên dữ liệu đại diện.** Bao gồm NULL, empty string, giá trị biên, kiểu dữ liệu khác nhau và trường hợp không có match.
7. **Đo execution plan nếu biểu thức nằm trong predicate.** Không mặc định CASE hay DECODE sẽ luôn nhanh hơn.

### Ví dụ chuyển đổi có nhiều nhánh và NULL

DECODE legacy:

~~~sql
SELECT employee_id,
       DECODE(
           commission_pct,
           NULL, 'No commission',
           0,    'Zero commission',
           0.1,  'Ten percent',
           'Other rate'
       ) AS commission_label
FROM employees;
~~~

Searched CASE:

~~~sql
SELECT employee_id,
       CASE
         WHEN commission_pct IS NULL THEN 'No commission'
         WHEN commission_pct = 0 THEN 'Zero commission'
         WHEN commission_pct = 0.1 THEN 'Ten percent'
         ELSE 'Other rate'
       END AS commission_label
FROM employees;
~~~

Với cột số kiểu NUMBER, các literal số trong ví dụ cũng là NUMBER. Nếu cột thực tế là kiểu khác hoặc có chuyển kiểu ngầm, phải xử lý theo kiểu cột thật thay vì sao chép nguyên mẫu.

### Không thể thay DECODE bằng NVL một cách máy móc

~~~sql
DECODE(status_code, NULL, 'Missing', 'A', 'Active', 'Other')
~~~

không tương đương với:

~~~sql
NVL(status_code, 'Missing')
~~~

DECODE trả nhãn cho nhiều trường hợp; NVL trả chính giá trị gốc nếu khác NULL. Hai biểu thức có cả mục đích lẫn kiểu dữ liệu trả về khác nhau.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `WHERE col = NULL` không trả hàng | So sánh với NULL cho UNKNOWN | Dùng `IS NULL`. |
| Chuyển DECODE sang simple CASE làm hàng NULL đổi nhãn | `CASE expr WHEN NULL` không match NULL | Dùng searched CASE với `WHEN expr IS NULL`. |
| DECODE trả VARCHAR2 dù các nhánh sau là số | Result đầu tiên là NULL literal hoặc CHAR | CAST result đầu tiên thành kiểu mong muốn. |
| DECODE báo lỗi chuyển kiểu | Expression/search khác kiểu và implicit conversion thất bại | Đồng nhất kiểu hoặc CAST/parse có kiểm soát. |
| Kết quả đổi khi hoán đổi cặp search/result | Thứ tự search ảnh hưởng nhánh match đầu tiên và có thể ảnh hưởng suy luận kiểu | Giữ thứ tự nghiệp vụ, kiểm tra kiểu trước khi refactor. |
| `NOT IN` không trả dữ liệu khi subquery có NULL | Logic ba giá trị khiến phép loại trừ thành UNKNOWN | Dùng `NOT EXISTS` hoặc lọc NULL có chủ đích. |
| Chuỗi rỗng match nhánh NULL ở Oracle | Oracle coi empty string là NULL | Chuẩn hóa hợp đồng dữ liệu khi tích hợp database khác. |
| Predicate bọc cột bằng DECODE chạy chậm | Biểu thức có thể cản trở index thông thường | Viết điều kiện trực tiếp, đo plan; cân nhắc function-based index nếu có cơ sở. |
| Không phân biệt được “không có dữ liệu” và “không áp dụng” | Hai trạng thái nghiệp vụ cùng bị lưu thành NULL | Thiết kế mã trạng thái riêng hoặc metadata bổ sung nếu cần phân biệt. |

### Lưu ý khi dùng DECODE với dữ liệu số

Đối với số, giữ kiểu search nhất quán với expression. Nếu cột là NUMBER, dùng literal NUMBER hoặc CAST rõ ràng. Không dựa vào chuỗi có dấu phân cách hàng nghìn/phần thập phân theo NLS để so sánh số.

~~~sql
-- Dễ hiểu hơn khi cột priority_no là NUMBER:
SELECT DECODE(priority_no, 1, 'High', 2, 'Normal', 'Other')
FROM tasks;

-- Nếu dữ liệu đầu vào là chuỗi, parse rõ và xử lý dữ liệu không hợp lệ:
SELECT CASE
         WHEN VALIDATE_CONVERSION(priority_text AS NUMBER) = 1
         THEN DECODE(TO_NUMBER(priority_text), 1, 'High', 2, 'Normal', 'Other')
         ELSE 'Invalid input'
       END AS priority_label
FROM task_import;
~~~

`VALIDATE_CONVERSION` có trên các phiên bản Oracle hỗ trợ hàm này; nếu phiên bản cũ hơn, cần dùng cơ chế kiểm tra/parse tương thích. Cũng phải truyền format/NLS phù hợp khi chuỗi số có dấu phân cách. Không dùng đoạn SQL mẫu này như một cách bỏ qua quy tắc dữ liệu nguồn.

## 14. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền `CREATE TABLE` và quota phù hợp. DDL có cơ chế implicit commit của Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo dữ liệu

~~~sql
CREATE TABLE lab_decode_values (
    id          NUMBER(6) PRIMARY KEY,
    code        VARCHAR2(10 CHAR),
    description VARCHAR2(80 CHAR)
);

INSERT INTO lab_decode_values VALUES (1, 'A', 'Active row');
INSERT INTO lab_decode_values VALUES (2, 'I', 'Inactive row');
INSERT INTO lab_decode_values VALUES (3, NULL, 'No code');
INSERT INTO lab_decode_values VALUES (4, 'A', 'Another active row');
INSERT INTO lab_decode_values VALUES (5, 'X', 'Other code');
COMMIT;
~~~

### Bước 2: quan sát NULL match trong DECODE

~~~sql
SELECT id,
       code,
       DECODE(
           code,
           'A', 'Active',
           'I', 'Inactive',
           NULL, 'Missing',
           'Other'
       ) AS decode_label
FROM lab_decode_values
ORDER BY id;
~~~

Ghi lại nhãn của hàng có `ID = 3`. Sau đó bỏ cặp `NULL, 'Missing'` và quan sát default.

### Bước 3: so sánh ba cách viết

~~~sql
SELECT
    DECODE(NULL, NULL, 'MATCH', 'NO') AS decode_null,
    CASE NULL
      WHEN NULL THEN 'MATCH'
      ELSE 'NO'
    END AS simple_case_null,
    CASE
      WHEN NULL IS NULL THEN 'MATCH'
      ELSE 'NO'
    END AS searched_case_null
FROM dual;
~~~

Giải thích tại sao chỉ DECODE và searched CASE có nhánh kiểm tra NULL rõ ràng mới cho kết quả MATCH trong ví dụ này.

### Bước 4: kiểm tra WHERE

~~~sql
SELECT id
FROM lab_decode_values
WHERE code = NULL;

SELECT id
FROM lab_decode_values
WHERE code IS NULL;
~~~

So sánh số hàng trả về. Câu đầu không chọn hàng; câu thứ hai chọn hàng `ID = 3`.

### Bước 5: kiểm tra kiểu dữ liệu trả về

~~~sql
SELECT
    DUMP(DECODE(1, 1, NULL, 2, 100, 0)) AS implicit_result_type,
    DUMP(DECODE(1, 1, CAST(NULL AS NUMBER), 2, 100, 0))
        AS explicit_number_type
FROM dual;
~~~

Giải thích tác động của result đầu tiên là NULL literal so với NULL được CAST tường minh thành NUMBER.

### Bước 6: kiểm tra chuỗi rỗng trong Oracle

~~~sql
SELECT
    CASE WHEN '' IS NULL THEN 'EMPTY_IS_NULL'
         ELSE 'NOT_NULL'
    END AS oracle_empty_string,
    DECODE('', NULL, 'MATCHES_NULL', 'NO_MATCH') AS decode_empty
FROM dual;
~~~

Oracle xử lý chuỗi ký tự độ dài 0 như NULL trong SQL, vì vậy biểu thức DECODE có thể match nhánh NULL. Không giả định quy tắc này giống mọi database khác.

### Bước 7: thử conditional aggregation

~~~sql
SELECT
    COUNT(DECODE(code, 'A', 1)) AS active_count,
    COUNT(DECODE(code, 'I', 1)) AS inactive_count,
    COUNT(DECODE(code, NULL, 1)) AS missing_count
FROM lab_decode_values;
~~~

Viết lại bằng searched CASE và `SUM`:

~~~sql
SELECT
    SUM(CASE WHEN code = 'A' THEN 1 ELSE 0 END) AS active_count,
    SUM(CASE WHEN code = 'I' THEN 1 ELSE 0 END) AS inactive_count,
    SUM(CASE WHEN code IS NULL THEN 1 ELSE 0 END) AS missing_count
FROM lab_decode_values;
~~~

Giải thích tại sao `COUNT(DECODE(...))` bỏ qua các hàng mà DECODE trả NULL.

### Bước 8: dọn dữ liệu thử

~~~sql
DROP TABLE lab_decode_values PURGE;
DROP TABLE lab_decode_status PURGE;
~~~

Chỉ chạy nếu bạn đã tạo hai bảng thực hành trong schema của mình và không cần giữ dữ liệu. `DROP TABLE ... PURGE` là DDL, bỏ qua Recycle Bin và không thể rollback như DML chưa commit.

## 15. Câu hỏi tự kiểm tra

1. **`NULL = NULL` trả về gì?** UNKNOWN, không phải TRUE.
2. **Vì sao `DECODE(NULL, NULL, 'Y', 'N')` trả Y?** DECODE có semantics đặc biệt xem hai NULL là khớp.
3. **`CASE NULL WHEN NULL THEN 'Y'` có giống DECODE không?** Không; simple CASE dùng phép so sánh thông thường nên nhánh NULL không match.
4. **Viết CASE đúng để kiểm tra NULL thế nào?** `CASE WHEN expr IS NULL THEN ...`.
5. **`WHERE col = NULL` có thể thay `WHERE col IS NULL` không?** Không; điều kiện đầu là UNKNOWN cho hàng NULL.
6. **DECODE bỏ default thì trả gì khi không có search nào match?** NULL.
7. **DECODE có giới hạn số components không?** Có, tối đa 255 components gồm expression, search, result và default.
8. **DECODE đánh giá search theo thứ tự nào?** Từ trái sang phải và dừng khi tìm thấy match (short-circuit).
9. **Vì sao result đầu tiên là NULL có thể làm kết quả thành VARCHAR2?** Oracle có quy tắc xác định kiểu trả về riêng: first result NULL literal hoặc CHAR dẫn tới trả VARCHAR2.
10. **DECODE có thay thế NVL không?** Không; NVL thay một giá trị NULL, DECODE ánh xạ expression theo nhiều search/result.
11. **Khi nào nên dùng COALESCE?** Khi muốn lấy biểu thức đầu tiên khác NULL trong danh sách.
12. **DECODE có làm NULL ở hai bảng tự JOIN với nhau không?** Không; điều kiện JOIN bằng thông thường vẫn cho UNKNOWN khi cả hai phía NULL, trừ khi viết điều kiện NULL tường minh.
13. **Vì sao DECODE không phải lúc nào cũng là lựa chọn tốt trong WHERE?** Predicate bọc cột có thể làm giảm khả năng dùng index thông thường; IS NULL/equality thường diễn đạt trực tiếp hơn.
14. **Khi chuyển DECODE sang CASE cần kiểm tra những gì?** Nhánh NULL, thứ tự, kiểu search/result, kiểu trả về và conversion.
15. **DECODE có phù hợp để kiểm tra khoảng giá trị không?** Không; dùng searched CASE với điều kiện so sánh khoảng.
16. **Tại sao empty string có thể match search NULL trong Oracle?** Oracle hiện xem chuỗi ký tự độ dài 0 là NULL trong SQL.
17. **`COUNT(DECODE(code, 'A', 1))` đếm điều gì?** Số hàng có code khớp A, vì COUNT bỏ qua kết quả NULL.

## Kết luận

`DECODE` là hàm đặc thù của Oracle để ánh xạ một biểu thức qua các cặp search/result. Quy tắc đáng nhớ nhất là **DECODE coi NULL match NULL**, trong khi phép so sánh `=` và simple `CASE expr WHEN NULL` tuân theo logic ba giá trị nên không match. Nếu cần viết điều kiện NULL bằng CASE, hãy dùng **searched CASE với `IS NULL`**.

Khi bảo trì SQL, hãy xem cả **semantics NULL, thứ tự nhánh và kiểu dữ liệu**. DECODE có thể trả kiểu khác mong đợi nếu result đầu tiên là NULL/CHAR, và chuyển kiểu ngầm có thể làm truy vấn lỗi hoặc thay đổi kết quả. Dùng `CASE` cho logic phức tạp/đa nền tảng, `NVL` hoặc `COALESCE` cho mục đích thay/chọn giá trị NULL, và dùng `IS NULL` trong điều kiện lọc. Chọn đúng cấu trúc giúp câu SQL vừa chính xác vừa dễ đọc và an toàn khi chuyển đổi hệ thống.
