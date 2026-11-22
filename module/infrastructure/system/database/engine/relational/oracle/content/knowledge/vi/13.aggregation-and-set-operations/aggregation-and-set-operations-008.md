# UNION, UNION ALL, INTERSECT và MINUS trong Oracle

Trong một hệ thống dữ liệu, đôi khi cần ghép kết quả từ nhiều câu truy vấn thành một tập kết quả chung. Ví dụ, báo cáo cần danh sách khách hàng xuất hiện trong dữ liệu năm nay hoặc năm trước; cần tìm nhân viên có mặt trong cả hai danh sách; hoặc tìm mã sản phẩm có trong hệ thống mới nhưng chưa có trong hệ thống cũ. Oracle SQL cung cấp các **set operators** để giải quyết những bài toán này: `UNION`, `UNION ALL`, `INTERSECT` và `MINUS`.

Các toán tử này kết hợp kết quả truy vấn theo chiều dọc: chúng ghép các **hàng** từ nhiều query block có cùng cấu trúc cột. Điều đó khác với `JOIN`, vốn ghép các cột của những hàng có quan hệ với nhau. Khác biệt lớn nhất giữa bốn toán tử là cách xử lý hàng trùng:

- `UNION` ghép hai tập và loại bỏ hàng trùng.
- `UNION ALL` ghép hai tập và giữ nguyên mọi lần xuất hiện.
- `INTERSECT` trả các hàng xuất hiện ở cả hai tập, mỗi hàng một lần.
- `MINUS` trả các hàng có ở tập bên trái nhưng không có ở tập bên phải, mỗi hàng một lần.

Bài học thuộc chủ đề **Gom nhóm và tập hợp** của *Database Engine Relational Oracle*. Bạn sẽ học cú pháp, thứ tự xử lý, so sánh NULL và kiểu dữ liệu, cách chọn toán tử đúng mục tiêu, ảnh hưởng tới execution plan/PGA/TEMP, cùng các ví dụ thực hành.

## 1. Set operators kết hợp hàng như thế nào?

Giả sử có hai nguồn mã nhân viên:

**Danh sách A**

| EMPLOYEE_ID |
| ---: |
| 10 |
| 20 |
| 30 |

**Danh sách B**

| EMPLOYEE_ID |
| ---: |
| 20 |
| 30 |
| 40 |

Kết quả của từng toán tử:

| Toán tử | Kết quả |
| --- | --- |
| `A UNION B` | 10, 20, 30, 40 |
| `A UNION ALL B` | 10, 20, 30, 20, 30, 40 |
| `A INTERSECT B` | 20, 30 |
| `A MINUS B` | 10 |
| `B MINUS A` | 40 |

Hãy chú ý `MINUS` có hướng: đổi vị trí hai tập có thể đổi kết quả. `UNION` và `INTERSECT` không phụ thuộc thứ tự hai đầu vào về mặt tập giá trị, còn `UNION ALL` vẫn giữ số lần xuất hiện của từng hàng.

### Set operation khác JOIN

~~~sql
-- Set operator: ghép các hàng cùng cấu trúc từ hai nguồn.
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT employee_id, employee_name
FROM archived_employees;

-- JOIN: ghép cột của hai bảng theo khóa liên kết.
SELECT e.employee_id, e.employee_name, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Set operator đòi hỏi hai query block có cùng số cột tương ứng và kiểu dữ liệu tương thích. JOIN không có yêu cầu hai danh sách SELECT phải cùng số cột; nó tạo hàng kết hợp dựa trên điều kiện nối.

## 2. Cú pháp chung của compound query

Một compound query có thể dùng một hoặc nhiều set operator:

~~~sql
SELECT select_list
FROM source_a
WHERE condition_a

UNION

SELECT select_list
FROM source_b
WHERE condition_b;
~~~

Mỗi câu SELECT thành phần được gọi là một query block. Các toán tử nối kết quả của những query block đó. Ví dụ:

~~~sql
SELECT employee_id
FROM employees_2024
WHERE status = 'ACTIVE'

UNION

SELECT employee_id
FROM employees_2025
WHERE status = 'ACTIVE';
~~~

Truy vấn trả danh sách ID khác nhau có mặt trong ít nhất một năm. Nếu cùng một nhân viên có trong cả hai bảng, kết quả chỉ chứa một ID.

### Quy tắc về số cột và vị trí cột

Hai query block phải:

1. Trả về **cùng số lượng cột**.
2. Có các cột tương ứng theo **vị trí**, không phải tên.
3. Có kiểu dữ liệu tương thích theo nhóm kiểu dữ liệu Oracle.

Ví dụ hợp lệ:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id, full_name
FROM archived_workers;
~~~

Tên cột khác nhau không gây vấn đề: cột thứ nhất được ghép với cột thứ nhất, cột thứ hai với cột thứ hai. Tên/alias của kết quả compound query thường lấy từ danh sách SELECT đầu tiên; vì vậy nên đặt alias rõ ràng ở query block đầu.

Ví dụ sai vì số cột không khớp:

~~~sql
-- Query đầu có hai cột, query sau chỉ có một.
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id
FROM archived_workers;
~~~

Oracle thường báo `ORA-01789: query block has incorrect number of result columns`.

## 3. UNION: ghép và loại bỏ hàng trùng

`UNION` trả các hàng xuất hiện trong ít nhất một query block và **loại bỏ duplicate trên toàn bộ danh sách cột kết quả**.

~~~sql
SELECT 10 AS employee_id FROM dual
UNION
SELECT 20 FROM dual
UNION
SELECT 10 FROM dual;
~~~

Kết quả có hai hàng: 10 và 20. Hàng 10 xuất hiện hai lần trong đầu vào nhưng chỉ một lần trong kết quả.

### Duplicate được xét trên cả hàng

~~~sql
SELECT 10 AS department_id, 'DEV' AS job_code FROM dual
UNION
SELECT 10, 'DEV' FROM dual
UNION
SELECT 10, 'QA' FROM dual;
~~~

Kết quả gồm hai hàng: `(10, DEV)` và `(10, QA)`. Mặc dù `DEPARTMENT_ID` giống nhau, hai hàng không trùng vì `JOB_CODE` khác nhau.

Nếu chỉ muốn danh sách phòng ban, hãy chỉ SELECT `DEPARTMENT_ID`:

~~~sql
SELECT department_id FROM current_employees
UNION
SELECT department_id FROM archived_employees;
~~~

Không thêm cột mô tả hoặc ID riêng nếu mục tiêu cần duy nhất theo mã phòng ban; thêm cột sẽ thay đổi định nghĩa duplicate.

### UNION thường cần bước duplicate elimination

Để loại trùng, Oracle có thể sử dụng sort hoặc hash, tùy execution plan:

- `SORT UNIQUE`: sắp xếp các hàng rồi chỉ giữ một bản sao của mỗi tổ hợp.
- `HASH UNIQUE`: dùng cấu trúc hash để nhận diện các tổ hợp đã xuất hiện.

Nếu hai nguồn lớn, nhiều hàng trùng hoặc mỗi hàng rộng, bước loại trùng có thể tốn CPU và PGA; nếu workarea không đủ, Oracle có thể spill dữ liệu trung gian xuống TEMP. Vì vậy, UNION không phải lúc nào cũng nhanh hơn UNION ALL.

## 4. UNION ALL: giữ tất cả hàng và số lần xuất hiện

`UNION ALL` ghép kết quả của các query block **mà không loại bỏ duplicate**:

~~~sql
SELECT 10 AS employee_id FROM dual
UNION ALL
SELECT 20 FROM dual
UNION ALL
SELECT 10 FROM dual;
~~~

Kết quả có ba hàng: 10, 20, 10. Thứ tự hiển thị không được bảo đảm nếu không có `ORDER BY`.

### Khi nào UNION ALL phù hợp?

- Ghép các phân vùng dữ liệu có khóa/miền giá trị không giao nhau theo thiết kế.
- Ghép log hoặc sự kiện mà mỗi lần xuất hiện đều có ý nghĩa.
- Ghép các nguồn đã được kiểm soát tính duy nhất và không cần database loại trùng thêm.
- Xây dựng báo cáo cần giữ số lần giao dịch, số lần sự kiện hoặc dữ liệu lặp hợp lệ.

Ví dụ:

~~~sql
SELECT transaction_id, amount, 'CURRENT' AS source_name
FROM current_transactions
UNION ALL
SELECT transaction_id, amount, 'ARCHIVE' AS source_name
FROM archived_transactions;
~~~

Ở đây `SOURCE_NAME` còn là một phần của hàng kết quả. Ngay cả khi hai bảng có cùng transaction ID và amount, giá trị source khác nhau khiến hai hàng không trùng nếu sau này chuyển thành UNION. Nếu mục tiêu là giữ mọi bản ghi và nhận diện nguồn, UNION ALL thể hiện ý định rõ ràng.

### UNION ALL không có nghĩa dữ liệu nguồn không trùng

Toán tử chỉ giữ các hàng đầu vào. Nó không xác minh khóa duy nhất, không loại bản ghi nhập lặp và không sửa dữ liệu nguồn. Nếu ứng dụng yêu cầu một giao dịch chỉ được ghi một lần, cần cơ chế idempotency/unique constraint phù hợp; UNION ALL không thay thế lớp bảo vệ đó.

### Tại sao UNION ALL thường tiết kiệm chi phí?

Khi không cần loại trùng toàn cục, Oracle có thể ghép các luồng kết quả mà không cần một bước sort/hash unique. Điều này thường giảm CPU, memory và TEMP. Tuy nhiên, query block vẫn có thể cần sort, hash join, aggregate hoặc thao tác khác; optimizer cũng có thể áp dụng biến đổi phức tạp. Chỉ kết luận bằng actual plan và số liệu thực thi.

## 5. INTERSECT: lấy phần giao của hai tập

`INTERSECT` trả những hàng xuất hiện ở **cả hai** query block. Kết quả được loại duplicate, kể cả khi một hàng xuất hiện nhiều lần trong một hoặc cả hai đầu vào.

~~~sql
SELECT employee_id
FROM employees_2024
INTERSECT
SELECT employee_id
FROM employees_2025;
~~~

Truy vấn tìm nhân viên có mặt trong cả hai năm. Nếu ID 20 xuất hiện ba lần ở bảng thứ nhất và hai lần ở bảng thứ hai, kết quả vẫn chỉ có một hàng ID 20.

### INTERSECT trên nhiều cột

~~~sql
SELECT customer_id, product_id
FROM orders_2024
INTERSECT
SELECT customer_id, product_id
FROM orders_2025;
~~~

Kết quả là các cặp khách hàng–sản phẩm xuất hiện trong cả hai nguồn. Nếu khách hàng có ở cả hai năm nhưng sản phẩm khác nhau, các hàng đó không phải cùng tổ hợp.

### Dùng INTERSECT để so sánh hai nguồn

Ví dụ tìm các mã có mặt trong cả bảng nhập và bảng master:

~~~sql
SELECT imported_code
FROM import_stage
INTERSECT
SELECT product_code
FROM products;
~~~

Đây là một cách diễn đạt tập hợp. Nếu cần lấy thêm mô tả từ bảng master, có thể dùng JOIN sau khi đã xác định tập giao; không cố đưa cột không cùng ý nghĩa vào hai query block chỉ để làm cho số cột bằng nhau.

## 6. MINUS: lấy phần chỉ có ở tập bên trái

`MINUS` trả những hàng có trong query block bên trái nhưng **không có** trong query block bên phải. Kết quả không lặp.

~~~sql
SELECT employee_id
FROM employees_2025
MINUS
SELECT employee_id
FROM employees_2024;
~~~

Truy vấn tìm nhân viên có trong năm 2025 nhưng không có trong năm 2024. Đổi vị trí hai query block:

~~~sql
SELECT employee_id
FROM employees_2024
MINUS
SELECT employee_id
FROM employees_2025;
~~~

sẽ tìm ID chỉ có trong năm 2024. **MINUS không giao hoán**: A MINUS B thường khác B MINUS A.

### Dùng MINUS để đối chiếu dữ liệu

Khi chuyển dữ liệu giữa hai hệ thống, có thể tìm mã nguồn chưa được nạp:

~~~sql
SELECT source_customer_id
FROM source_customers
MINUS
SELECT customer_id
FROM target_customers;
~~~

Kết quả là các ID nguồn chưa có trong đích. Chiều ngược lại giúp tìm ID có ở đích nhưng không có ở nguồn:

~~~sql
SELECT customer_id
FROM target_customers
MINUS
SELECT source_customer_id
FROM source_customers;
~~~

Đây là so sánh theo tập giá trị. Nếu cần đối chiếu từng hàng trên nhiều cột, hãy chọn tất cả cột nghiệp vụ cần so sánh theo cùng thứ tự và kiểu dữ liệu.

### MINUS không phải DELETE

`MINUS` chỉ trả kết quả truy vấn. Nó không xóa hàng khỏi bảng bên trái. Nếu muốn xóa dữ liệu không có đối ứng, cần viết `DELETE` với `NOT EXISTS`/điều kiện thích hợp và kiểm soát transaction riêng. Không chuyển một truy vấn đối chiếu thành DML xóa mà chưa xác nhận phạm vi và quy tắc lưu trữ.

## 7. So sánh bốn toán tử

| Toán tử | Quy tắc tập hợp | Loại duplicate? | Có giữ số lần xuất hiện? | Có hướng trái/phải? |
| --- | --- | --- | --- | --- |
| `UNION` | Hợp hai tập | Có | Không | Không |
| `UNION ALL` | Ghép mọi hàng | Không | Có | Thứ tự nguồn trong cú pháp không tạo cam kết thứ tự output |
| `INTERSECT` | Phần giao | Có | Không | Không |
| `MINUS` | Phần chỉ có bên trái | Có | Không | **Có**, trái trừ phải |

Ví dụ dùng cùng hai tập A = `(10, 20, 20, 30)` và B = `(20, 30, 40)`:

| Toán tử | Kết quả tập giá trị |
| --- | --- |
| A UNION B | `10, 20, 30, 40` |
| A UNION ALL B | `10, 20, 20, 30, 20, 30, 40` |
| A INTERSECT B | `20, 30` |
| A MINUS B | `10` |
| B MINUS A | `40` |

Lưu ý: bảng minh họa tập giá trị; kết quả SQL không có `ORDER BY` thì không cam kết thứ tự các hàng.

## 8. NULL trong set operators

Trong các phép set của Oracle, các hàng có NULL tại vị trí tương ứng có thể được xem là cùng tổ hợp để loại trùng hoặc xác định giao/hiệu. Đây là hành vi khác với biểu thức điều kiện `NULL = NULL` trong WHERE.

Thử:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
UNION
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

Kết quả có **một hàng NULL**, không phải hai hàng. UNION loại duplicate và coi hai tổ hợp NULL tương ứng là cùng giá trị trong ngữ cảnh set operation.

INTERSECT:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
INTERSECT
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

Kết quả có một hàng NULL vì hai tập đều chứa tổ hợp NULL.

MINUS:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
MINUS
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

Kết quả rỗng vì hàng NULL bên trái có đối ứng trong tập bên phải theo semantics của set operator.

Điều này **không** làm thay đổi logic ba giá trị của WHERE:

~~~sql
SELECT 1
FROM dual
WHERE CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER);
~~~

Câu truy vấn không trả hàng vì điều kiện là UNKNOWN. Đừng lấy quy tắc duplicate elimination của set operators áp dụng máy móc cho phép so sánh bằng thông thường.

### NULL và COUNT

UNION có thể trả một hàng NULL, nhưng `COUNT(expression)` bỏ qua NULL:

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(value_col) AS non_null_rows
FROM (
    SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
    UNION
    SELECT CAST(NULL AS NUMBER) FROM dual
);
~~~

Kết quả `ALL_ROWS = 1` và `NON_NULL_ROWS = 0`. Đây là sự kết hợp giữa semantics set operation và semantics hàm aggregate.

## 9. Kiểu dữ liệu phải tương thích

Đây là một quy tắc quan trọng khi viết compound query trong Oracle: **các cột tương ứng phải cùng nhóm kiểu dữ liệu**. Oracle không tự chuyển tùy ý giữa nhóm ký tự và nhóm số chỉ để hợp nhất hai query block.

### Cùng số cột và kiểu tương thích

Hợp lệ:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT worker_id, full_name
FROM archived_workers;
~~~

Giả sử hai cột ID đều là NUMBER và hai cột tên đều là kiểu ký tự tương thích.

Không hợp lệ nếu một phía là NUMBER, phía kia là VARCHAR2:

~~~sql
SELECT employee_id
FROM employees
UNION
SELECT employee_code
FROM external_workers;
~~~

Nếu `EMPLOYEE_ID` là NUMBER còn `EMPLOYEE_CODE` là VARCHAR2, Oracle có thể báo `ORA-01790: expression must have same datatype as corresponding expression`. Hãy quyết định semantics dữ liệu rồi chuyển kiểu rõ ràng:

~~~sql
SELECT TO_CHAR(employee_id) AS employee_code
FROM employees
UNION
SELECT employee_code
FROM external_workers;
~~~

Chỉ chuyển ID sang chuỗi khi mục tiêu thật sự là hợp nhất mã văn bản. Nếu cần tính toán hoặc đối chiếu numeric, hãy kiểm tra dữ liệu chuỗi và chuyển sang NUMBER có kiểm soát:

~~~sql
SELECT employee_id
FROM employees
UNION
SELECT TO_NUMBER(employee_code)
FROM external_workers;
~~~

Mẫu thứ hai chỉ an toàn nếu mọi mã nguồn đều là số hợp lệ theo format dự kiến; dữ liệu không hợp lệ có thể gây lỗi chuyển đổi. Không dùng CAST để che một bất đồng mô hình dữ liệu chưa được giải quyết.

### Numeric precedence

Khi các cột tương ứng đều thuộc nhóm số, Oracle áp dụng quy tắc **numeric precedence** để xác định kiểu kết quả:

1. `BINARY_DOUBLE` có precedence cao nhất.
2. Tiếp theo là `BINARY_FLOAT`.
3. `NUMBER` có precedence thấp hơn hai kiểu nhị phân đó.

Ví dụ:

~~~sql
SELECT CAST(1 AS NUMBER) AS numeric_value
FROM dual
UNION ALL
SELECT CAST(2 AS BINARY_DOUBLE)
FROM dual;
~~~

Biểu thức kết quả được xác định theo kiểu số có precedence cao hơn; phía NUMBER có thể được chuyển sang BINARY_DOUBLE. Với dữ liệu tiền hoặc decimal exact, không nên để một query block vô tình đưa BINARY_DOUBLE vào compound query rồi làm thay đổi kiểu kết quả. Hãy CAST các nhánh về kiểu đích được chọn.

### Kiểu CHAR và VARCHAR2

Đối với biểu thức ký tự, độ dài và kiểu trả về còn phụ thuộc các kiểu CHAR/VARCHAR2 tương ứng. Khi một nhánh là VARCHAR2, kết quả thường là VARCHAR2; khi các nhánh đều là CHAR cùng độ dài, kết quả có thể giữ CHAR. Để hợp đồng dữ liệu ổn định giữa các nguồn, có thể CAST tường minh:

~~~sql
SELECT CAST(status_code AS VARCHAR2(20 CHAR)) AS status_code
FROM current_records
UNION ALL
SELECT CAST(old_status AS VARCHAR2(20 CHAR))
FROM archived_records;
~~~

Chọn độ dài và semantics BYTE/CHAR phù hợp với dữ liệu thực tế. CAST về độ dài quá ngắn có thể gây lỗi hoặc cắt dữ liệu tùy ngữ cảnh; không đặt độ dài tùy tiện.

### Kiểu dữ liệu không phù hợp với set operators

Oracle hạn chế một số kiểu dữ liệu trong set operations. Không giả định có thể UNION trực tiếp các cột `BLOB`, `CLOB`, `BFILE`, collection như VARRAY/nested table hoặc kiểu dữ liệu không hỗ trợ so sánh. Với LOB, nếu cần hợp nhất danh tính nội dung, hãy thiết kế khóa hoặc digest thích hợp và có chiến lược xác minh nội dung; hash đơn thuần không chứng minh hai LOB giống nhau vì có khả năng va chạm.

## 10. ORDER BY, alias và thứ tự xử lý các set operators

### ORDER BY đặt ở cuối compound query

`ORDER BY` điều khiển thứ tự của **toàn bộ kết quả** và thường được đặt sau query block cuối:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id, full_name
FROM archived_workers
ORDER BY employee_id;
~~~

Alias của compound result thường lấy từ SELECT đầu tiên. Vì vậy, hãy khai báo alias tại query block đầu và dùng nó trong ORDER BY. Oracle không đảm bảo thứ tự chỉ vì plan dùng sort để loại trùng; một thay đổi plan có thể làm thứ tự hiển thị khác.

Không đặt ORDER BY tự do trong từng query block của compound query:

~~~sql
-- Không dùng ORDER BY giữa hai nhánh theo cách này.
SELECT employee_id
FROM current_employees
ORDER BY employee_id
UNION
SELECT worker_id
FROM archived_workers;
~~~

Nếu từng nguồn cần top-N trước khi ghép, đặt truy vấn con có ORDER BY và row limiting trong subquery/CTE phù hợp với phiên bản Oracle, rồi áp dụng set operator ở ngoài. `ORDER BY` cuối cùng vẫn cần thiết nếu người dùng yêu cầu thứ tự kết quả tổng.

### Thứ tự đánh giá nhiều set operators

Khi một compound query có nhiều toán tử, **không nên dựa vào precedence ngầm**. Các tài liệu Oracle truyền thống mô tả các set operator có cùng mức ưu tiên và được đánh giá từ trái sang phải; Oracle cũng đã lưu ý rằng `INTERSECT` có thể được ưu tiên cao hơn trong một bản phát hành tương lai để phù hợp chuẩn SQL. Khác biệt giữa phiên bản có thể làm thay đổi cách hiểu biểu thức không có ngoặc.

Hãy dùng ngoặc hoặc tách query block thành CTE/subquery để thể hiện ý định:

~~~sql
-- Tính hợp của A và B trước, rồi lấy phần giao với C.
WITH a_union_b AS (
    SELECT employee_id FROM source_a
    UNION
    SELECT employee_id FROM source_b
)
SELECT employee_id
FROM a_union_b
INTERSECT
SELECT employee_id
FROM source_c;
~~~

Để biểu diễn phần giao trước rồi mới hợp với C:

~~~sql
WITH a_intersect_b AS (
    SELECT employee_id FROM source_a
    INTERSECT
    SELECT employee_id FROM source_b
)
SELECT employee_id FROM a_intersect_b
UNION
SELECT employee_id FROM source_c;
~~~

Hai truy vấn trên thể hiện hai ý nghĩa khác nhau. Dùng CTE giúp người đọc hiểu ranh giới tập hợp và giảm phụ thuộc vào quy tắc precedence của phiên bản.

### Kết hợp set operator với FETCH FIRST

Nếu cần giới hạn số hàng của toàn kết quả, đặt row limiting ở compound query ngoài cùng theo cú pháp phiên bản hỗ trợ:

~~~sql
SELECT employee_id FROM current_employees
UNION
SELECT worker_id FROM archived_workers
ORDER BY employee_id
FETCH FIRST 20 ROWS ONLY;
~~~

Nếu muốn giới hạn từng nguồn trước khi ghép, phải đặt mỗi nhánh vào query block riêng có ORDER BY và FETCH FIRST; nếu không, giới hạn cuối chỉ áp dụng cho kết quả hợp nhất. Luôn nêu rõ tiêu chí sắp xếp để top-N có tính xác định.

## 11. Chi phí thực thi và execution plan

Set operators có thể làm thay đổi đáng kể chi phí SQL, nhất là khi nguồn lớn. Khác biệt cốt lõi là **có cần loại bỏ duplicate hay không**:

| Toán tử | Công việc bổ sung thường cần |
| --- | --- |
| `UNION ALL` | Ghép các luồng hàng; không cần loại trùng toàn cục. |
| `UNION` | Loại trùng trên toàn bộ kết quả hợp nhất. |
| `INTERSECT` | Xác định hàng có mặt ở cả hai tập và loại trùng. |
| `MINUS` | Xác định hàng chỉ có ở tập trái và loại trùng. |

Oracle có thể dùng các chiến lược sort, hash, merge hoặc phép join phù hợp. Không có cam kết một toán tử luôn dùng đúng một operation trong execution plan. Ví dụ, plan có thể hiển thị:

- `UNION-ALL`: ghép các luồng mà không loại trùng.
- `SORT UNIQUE`: sort và loại trùng.
- `HASH UNIQUE`: hash và loại trùng.
- `INTERSECTION`: xử lý phần giao.
- `MINUS`: xử lý hiệu tập hợp.
- `SORT JOIN`, `HASH JOIN SEMI` hoặc `HASH JOIN ANTI`: có thể xuất hiện trong kế hoạch thực hiện quan hệ giao/hiệu hoặc truy vấn tương đương.

Tên và tổ hợp operation cụ thể tùy phiên bản, optimizer, thống kê và hình dạng truy vấn. Đọc toàn plan để hiểu các bước đầu vào; không chỉ tìm một dòng operation có tên giống toán tử SQL.

### Vì sao duplicate elimination tốn bộ nhớ?

Để loại trùng, Oracle cần giữ đủ thông tin để nhận biết hàng đã xuất hiện. Với sort, workarea chứa các hàng hoặc khóa sắp xếp; với hash, workarea chứa cấu trúc hash và thông tin hàng/khóa. Chi phí chịu ảnh hưởng bởi:

- Số hàng đầu vào của tất cả nhánh.
- Số tổ hợp khác nhau cần giữ.
- Độ rộng các cột được so sánh.
- Biểu thức tính toán trong select list.
- PGA/workarea được cấp tại thời điểm chạy.
- Số truy vấn đồng thời và mức độ song song.

Nếu workarea không đủ, sort/hash có thể spill xuống temporary tablespace. Khi đó một câu UNION hoặc INTERSECT có thể tạo TEMP I/O đáng kể dù kết quả cuối chỉ có vài hàng. **Số hàng trả về nhỏ không chứng minh công việc xử lý nhỏ.**

### So sánh UNION với UNION ALL

Khi không cần loại trùng, hãy dùng UNION ALL:

~~~sql
SELECT event_id, event_type
FROM live_events
UNION ALL
SELECT event_id, event_type
FROM archived_events;
~~~

Nếu dùng UNION, Oracle còn phải xác định duplicate giữa hai nguồn và cả duplicate nội bộ từng nguồn. UNION ALL thường tiết kiệm công việc đó. Tuy nhiên, nếu nguồn cần được deduplicate riêng theo khóa nghiệp vụ, hãy diễn đạt quy tắc riêng thay vì giả định UNION ALL sẽ làm điều đó.

### Quan sát plan thực tế

Ví dụ thu thập thống kê thực thi:

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id
FROM employees_2024
UNION
SELECT employee_id
FROM employees_2025;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Quan sát:

- Operation nào thực hiện duplicate elimination?
- `E-Rows` có lệch nhiều so với `A-Rows` không?
- Số hàng ở mỗi nhánh trước khi hợp nhất là bao nhiêu?
- `Buffers` và physical reads tăng ở nhánh nào?
- Có thông tin TEMP/workarea spill hay không?
- UNION ALL có tránh được operation loại trùng trong cùng truy vấn hay không?

`ALLSTATS LAST` cần thống kê thực thi được thu thập, ví dụ hint `GATHER_PLAN_STATISTICS` hoặc cấu hình phù hợp. `DBMS_XPLAN.DISPLAY_CURSOR` cần quyền đọc cursor/plan tương ứng. Nếu không có actual statistics, đừng nhầm estimated rows với số hàng thật.

`EXPLAIN PLAN` chỉ cho plan ước lượng; nó không chạy truy vấn để đo thời gian, số hàng thực tế hay TEMP đã dùng:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id FROM employees_2024
UNION
SELECT employee_id FROM employees_2025;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Để đánh giá hiệu năng, hãy dùng cursor thực thi với bind values và dữ liệu đại diện. Không so sánh một truy vấn vừa được cache với truy vấn khác vừa đọc storage rồi kết luận chỉ dựa trên thời gian của một lần chạy.

## 12. Mẫu sử dụng thực tế

### Hợp nhất dữ liệu theo thời gian

Nếu dữ liệu năm hiện tại và dữ liệu lưu trữ được chia thành hai bảng, báo cáo lịch sử có thể ghép bằng UNION ALL:

~~~sql
SELECT order_id, customer_id, order_date, total_amount
FROM orders_current
WHERE order_date >= DATE '2026-01-01'
UNION ALL
SELECT order_id, customer_id, order_date, total_amount
FROM orders_archive
WHERE order_date < DATE '2026-01-01';
~~~

Nếu hai miền ngày được đảm bảo không giao nhau và mỗi bảng có tính duy nhất riêng, UNION ALL thường đúng mục tiêu. Nếu dữ liệu có thể nằm đồng thời ở cả hai bảng và nghiệp vụ yêu cầu loại bản ghi trùng, cần quy định khóa so sánh và dùng UNION hoặc quy tắc dedup rõ ràng.

### Tìm bản ghi chưa được đồng bộ

~~~sql
SELECT source_id
FROM source_customers
MINUS
SELECT target_id
FROM target_customers;
~~~

Kết quả là ID có trong nguồn nhưng chưa có ở đích. Đây là tập ứng viên để đồng bộ; trước khi INSERT, cần kiểm tra lại quyền, trạng thái, dữ liệu liên quan và xử lý cạnh tranh nếu hai tiến trình đồng bộ có thể chạy cùng lúc. MINUS không khóa hai bảng và không tự bảo đảm tính idempotent.

### Tìm ID đồng bộ ở cả hai hệ thống

~~~sql
SELECT source_id
FROM source_customers
INTERSECT
SELECT target_id
FROM target_customers;
~~~

Có thể dùng để thống kê tập ID chung. Nếu cần đối chiếu thuộc tính, mở rộng danh sách SELECT theo các cột tương ứng và cùng kiểu, hoặc JOIN trên khóa để so sánh từng thuộc tính.

### Tìm khác biệt cả hai chiều

Để biết tập nào thiếu dữ liệu, chạy hai phép MINUS:

~~~sql
-- Có ở nguồn nhưng thiếu ở đích.
SELECT source_id FROM source_customers
MINUS
SELECT target_id FROM target_customers;

-- Có ở đích nhưng không còn trong nguồn.
SELECT target_id FROM target_customers
MINUS
SELECT source_id FROM source_customers;
~~~

Hai kết quả hỗ trợ reconciliation. Chúng so sánh **tập giá trị**, không đếm số lần xuất hiện. Nếu một ID lặp 10 lần ở nguồn và 1 lần ở đích, MINUS có thể không cho biết chênh lệch multiplicity. Khi số lần xuất hiện cũng quan trọng, cần GROUP BY và so sánh count theo khóa.

### So sánh cả nội dung hàng

~~~sql
SELECT customer_id, customer_name, status_code
FROM source_customer_snapshot
MINUS
SELECT customer_id, customer_name, status_code
FROM target_customer_snapshot;
~~~

Truy vấn tìm các tổ hợp hàng có ở nguồn nhưng không có ở đích. Chú ý nếu tên khác nhau do khoảng trắng, collation hoặc quy tắc chuẩn hóa, chúng là giá trị khác nhau theo semantics kiểu dữ liệu. Nếu cần bỏ qua khác biệt chữ hoa/thường hoặc khoảng trắng, chuẩn hóa biểu thức một cách tường minh và thống nhất ở hai phía.

### UNION ALL cộng dữ liệu, GROUP BY tổng hợp

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM (
    SELECT customer_id, amount FROM online_sales
    UNION ALL
    SELECT customer_id, amount FROM store_sales
)
GROUP BY customer_id;
~~~

Ở đây UNION ALL giữ các giao dịch trùng giá trị vì mỗi dòng là một sự kiện riêng. GROUP BY mới là bước tổng hợp theo khách hàng. Dùng UNION thay cho UNION ALL có thể làm mất các giao dịch giống hệt nhau và khiến tổng tiền thấp hơn thực tế.

### Đếm hàng khác nhau trong nhiều nguồn

~~~sql
SELECT COUNT(*) AS unique_customer_count
FROM (
    SELECT customer_id FROM online_customers
    UNION
    SELECT customer_id FROM store_customers
);
~~~

Nếu cần đếm NULL như một nhóm, nhớ rằng UNION có thể giữ một hàng NULL nhưng COUNT(*) vẫn đếm hàng đó. Nếu dùng `COUNT(customer_id)` ở query ngoài, NULL bị bỏ qua.

## 13. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ORA-01789` | Các query block có số cột khác nhau | Đối chiếu số cột theo vị trí; bổ sung biểu thức phù hợp. |
| `ORA-01790` | Kiểu dữ liệu cột tương ứng không tương thích | CAST rõ ràng về cùng nhóm/kiểu đích. |
| Kết quả có ít hàng hơn mong đợi | Dùng UNION/INTERSECT/MINUS loại duplicate | Xác định có cần giữ multiplicity; dùng UNION ALL khi cần. |
| Kết quả có duplicate | Dùng UNION ALL | Chọn UNION hoặc dedup theo khóa nghiệp vụ nếu yêu cầu là tập duy nhất. |
| MINUS trả ngược điều mong đợi | Đặt hai query block sai thứ tự | Nhớ MINUS là trái trừ phải. |
| Kết quả sắp xếp không ổn định | Không có ORDER BY cuối | Thêm ORDER BY ở compound query ngoài cùng. |
| ORDER BY báo lỗi biểu thức không được chọn | Tham chiếu cột không có trong danh sách kết quả compound | Chọn/alias biểu thức phù hợp hoặc bọc compound query rồi sắp xếp ở ngoài. |
| UNION lớn chạy chậm hoặc dùng TEMP | Duplicate elimination trên nhiều hàng/rộng | Kiểm tra plan, giảm đầu vào/cột nếu nghiệp vụ cho phép, cân nhắc UNION ALL. |
| Đối chiếu MINUS không phát hiện chênh số lượng duplicate | Set operator bỏ multiplicity | GROUP BY khóa và so sánh COUNT. |
| NULL được xử lý khác WHERE | Set operators dùng semantics duplicate/set, không phải phép so sánh thông thường | Phân biệt ngữ cảnh; dùng IS NULL trong điều kiện. |
| Compound query đổi kiểu số sang floating point | Một nhánh có BINARY_FLOAT/BINARY_DOUBLE | CAST tất cả nhánh về kiểu decimal nếu yêu cầu exact. |

## 14. Bài thực hành tổng hợp

Các ví dụ dùng bảng lab trong schema thực hành có quyền `CREATE TABLE` và quota phù hợp. DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo hai bảng mẫu

~~~sql
CREATE TABLE lab_set_a (
    code NUMBER(6),
    label VARCHAR2(20 CHAR)
);

CREATE TABLE lab_set_b (
    code NUMBER(6),
    label VARCHAR2(20 CHAR)
);

INSERT INTO lab_set_a VALUES (10, 'A');
INSERT INTO lab_set_a VALUES (20, 'B');
INSERT INTO lab_set_a VALUES (20, 'B');
INSERT INTO lab_set_a VALUES (30, 'C');
INSERT INTO lab_set_a VALUES (NULL, 'Missing');

INSERT INTO lab_set_b VALUES (20, 'B');
INSERT INTO lab_set_b VALUES (30, 'C');
INSERT INTO lab_set_b VALUES (40, 'D');
INSERT INTO lab_set_b VALUES (NULL, 'Missing');
INSERT INTO lab_set_b VALUES (NULL, 'Missing');

COMMIT;
~~~

### Bước 2: chạy bốn toán tử

~~~sql
SELECT code, label FROM lab_set_a
UNION
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
UNION ALL
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
INTERSECT
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
MINUS
SELECT code, label FROM lab_set_b;
~~~

Ghi lại số hàng của mỗi kết quả. Giải thích tại sao hàng `(20, 'B')` và `(NULL, 'Missing')` chỉ xuất hiện một lần ở UNION, nhưng có thể xuất hiện nhiều lần ở UNION ALL.

### Bước 3: đảo chiều MINUS

~~~sql
SELECT code, label FROM lab_set_b
MINUS
SELECT code, label FROM lab_set_a;
~~~

Giải thích vì sao hàng `(40, 'D')` xuất hiện ở kết quả này nhưng không xuất hiện khi trừ theo chiều ngược lại.

### Bước 4: quan sát NULL

~~~sql
SELECT code, label FROM lab_set_a
INTERSECT
SELECT code, label FROM lab_set_b;
~~~

Kiểm tra hàng NULL có trong kết quả giao. Sau đó so sánh với:

~~~sql
SELECT code, label
FROM lab_set_a
WHERE code = NULL;

SELECT code, label
FROM lab_set_a
WHERE code IS NULL;
~~~

Giải thích tại sao semantics của set operation không làm phép `= NULL` trong WHERE trở thành TRUE.

### Bước 5: thử lỗi kiểu dữ liệu

~~~sql
-- Cố ý sai: NUMBER ở nhánh đầu, VARCHAR2 ở nhánh sau.
SELECT code FROM lab_set_a
UNION
SELECT label FROM lab_set_b;
~~~

Quan sát lỗi datatype, rồi sửa bằng CAST về cùng kiểu theo mục tiêu. Ví dụ nếu mục tiêu là mã dạng văn bản:

~~~sql
SELECT TO_CHAR(code) AS code_text FROM lab_set_a
UNION
SELECT label FROM lab_set_b;
~~~

### Bước 6: giữ multiplicity khi tổng hợp

~~~sql
SELECT code, COUNT(*) AS occurrence_count
FROM (
    SELECT code FROM lab_set_a
    UNION ALL
    SELECT code FROM lab_set_b
)
GROUP BY code
ORDER BY code;
~~~

So sánh với việc dùng UNION ở subquery. Giải thích tại sao số lần xuất hiện thay đổi và ảnh hưởng tới COUNT.

### Bước 7: dọn bảng

~~~sql
DROP TABLE lab_set_a PURGE;
DROP TABLE lab_set_b PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu. `PURGE` bỏ qua Recycle Bin; DROP TABLE là DDL và không thể rollback như DML chưa commit.
