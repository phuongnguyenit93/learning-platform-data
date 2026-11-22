# ROWNUM và lỗi giới hạn kết quả trước khi sắp xếp trong Oracle Database

## 1. Vấn đề: “lấy 5 người có lương cao nhất” nhưng SQL trả sai

Giả sử bảng nhân viên có hàng nghìn bản ghi. Yêu cầu của ứng dụng là **trả 5 nhân viên có lương cao nhất**, nếu bằng lương thì nhân viên có mã nhỏ hơn đứng trước. Người mới học Oracle có thể viết:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  ROWNUM <= 5
ORDER BY salary DESC;
```

Truy vấn này **không bảo đảm** lấy 5 người có lương cao nhất trong toàn bảng. Oracle có thể lấy **5 dòng đáp ứng điều kiện `ROWNUM <= 5` theo thứ tự truy cập**, rồi **sắp xếp chính 5 dòng đó** theo `salary DESC`. Nếu năm dòng đầu theo đường truy cập không có nhân viên lương cao nhất, kết quả sẽ sai mục tiêu nghiệp vụ dù output trông đã được sắp xếp.

Đó là lỗi **giới hạn trước, sắp xếp sau** (*limit before sort*).

Cách viết đúng trên Oracle 12c trở lên, trong đó có Oracle Database 19c:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Hoặc theo cú pháp `ROWNUM` truyền thống:

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   employees
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5;
```

**Thông điệp chính:** Khi cần **Top-N theo tiêu chí xếp hạng**, phải xác định rõ thứ tự **trước khi chọn N dòng** về mặt ngữ nghĩa truy vấn. `ROWNUM` không phải một chức năng xếp hạng tự động và không mặc nhiên được tính sau `ORDER BY` của cùng một query block.

> Các ví dụ dưới đây tập trung vào Oracle Database 19c và so sánh cách dùng tương thích 11g với `row_limiting_clause` có từ 12c. Tên bảng và dữ liệu là ví dụ trong schema lab. Optimizer có thể thay đổi thứ tự thực thi vật lý miễn vẫn bảo toàn ngữ nghĩa SQL; những sơ đồ sau mô tả logic để hiểu câu truy vấn, không phải cam kết một execution plan duy nhất.

## 2. `ROWNUM` thực sự là gì?

**`ROWNUM`** là một **pseudocolumn** Oracle gán cho các dòng được chọn trong một **query block**. Nó không tồn tại như cột dữ liệu trong table, không phải khóa chính, không phải `ROWID`, không phải thứ tự chèn và không phải thứ tự sau `ORDER BY` nếu `ORDER BY` ở cùng query block.

Từ tài liệu Oracle:

- Dòng đầu tiên được chấp nhận vào kết quả theo cơ chế `ROWNUM` có `ROWNUM = 1`.
- Dòng tiếp theo có `ROWNUM = 2`, rồi 3, 4...
- Dòng nào xuất hiện trước còn phụ thuộc đường truy cập dữ liệu do optimizer lựa chọn: full table scan, index, join strategy, filter...
- Nếu trong cùng query block có `ORDER BY`, Oracle có thể gán `ROWNUM` **trước khi sắp xếp kết quả cuối cùng**.

Ví dụ:

```sql
SELECT employee_id, employee_name, ROWNUM AS rn
FROM   employees;
```

Câu SQL trên cho các dòng số 1, 2, 3... trong **lần thực hiện đó**. Nó **không** chứng minh `rn = 1` là nhân viên được tạo đầu tiên, có lương cao nhất hay ID nhỏ nhất.

### 2.1. Ba đại lượng dễ nhầm

| Khái niệm | Định nghĩa | Có ổn định như business key? | Dùng cho việc gì? |
| --- | --- | --- | --- |
| `ROWNUM` | Số thứ tự dòng Oracle lựa chọn trong query block | **Không** | Giới hạn dòng theo thứ tự truy cập, mẫu Top-N với query block lồng |
| `ROW_NUMBER()` | Hàm phân tích đánh số theo `OVER (ORDER BY ...)`, có thể chia nhóm | Không phải business key; ổn định trong một snapshot nếu thứ tự là toàn phần | Xếp hạng và Top-N/Top-N theo nhóm |
| `ROWID` | Pseudocolumn chỉ định vị trí/định danh hàng ở mức lưu trữ theo cấu trúc Oracle | **Không nên** dùng làm khóa nghiệp vụ lâu dài | Truy cập/định vị row theo khả năng của Oracle |

Nếu cần một ID không đổi cho nhân viên/đơn hàng, hãy dùng **primary key** với identity column hoặc sequence phù hợp. Không lấy `ROWNUM` của một lần SELECT để lưu như ID nghiệp vụ.

### 2.2. Query block là đơn vị cần phân biệt

Xét:

```sql
-- Chỉ có một query block:
SELECT *
FROM   employees
WHERE  ROWNUM <= 5
ORDER BY salary DESC;
```

và:

```sql
-- Có hai query blocks:
SELECT *
FROM (
    SELECT *
    FROM   employees
    ORDER BY salary DESC
)
WHERE ROWNUM <= 5;
```

Trong truy vấn thứ hai, `ORDER BY` của inner query block xác định tập giá trị được sắp xếp; `ROWNUM` nằm ở **outer query block**, nên giới hạn áp dụng trên các dòng đã được chọn theo thứ tự trong inner block. Optimizer có thể thực hiện tối ưu `STOPKEY` nhưng phải giữ kết quả tương đương yêu cầu Top-N.

## 3. Vì sao `WHERE ROWNUM <= N ORDER BY ...` có thể sai?

Hãy hình dung một tập bốn nhân viên, không giả định về thứ tự vật lý:

| EMPLOYEE_ID | EMPLOYEE_NAME | SALARY |
| ---: | --- | ---: |
| 10 | An | 3.000 |
| 20 | Bình | 8.000 |
| 30 | Chi | 5.000 |
| 40 | Dũng | 10.000 |

Giả sử **trong một execution plan cụ thể**, Oracle đọc theo thứ tự `10 → 30 → 20 → 40`. Với:

```sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  ROWNUM <= 2
ORDER BY salary DESC;
```

có thể xảy ra:

```text
Nguồn dữ liệu theo một đường truy cập có thể có:
  (10, An,   3000)
  (30, Chi,  5000)
  (20, Binh, 8000)
  (40, Dung, 10000)
           │
           ▼  Giới hạn ROWNUM <= 2
  (10, An,   3000)
  (30, Chi,  5000)
           │
           ▼  ORDER BY salary DESC
  (30, Chi,  5000)
  (10, An,   3000)
```

Đây là **hai dòng được chọn sớm nhất trong đường truy cập**, sau đó được sắp xếp. Kết quả đúng của **Top-2 lương cao nhất** phải là `(40, Dũng, 10000)` và `(20, Bình, 8000)`.

**Cẩn thận:** Thực tế một index theo `salary` hoặc một plan khác có thể tình cờ cho kết quả mong đợi ngay cả với câu SQL sai. Chính sự “tình cờ đúng” này làm bug khó phát hiện: thêm index, cập nhật statistics, chuyển phiên bản optimizer hoặc đổi lượng dữ liệu có thể thay đổi năm dòng được chọn. Không lấy vài lần test đúng làm bảo đảm ngữ nghĩa.

### 3.1. Sơ đồ hai phép toán không giao hoán

```text
Sai cho yêu cầu Top-N:

    LIMIT N  ──► SORT
  (chọn trước)  (sắp xếp N dòng)

Đúng cho yêu cầu Top-N:

    SORT     ──► LIMIT N
 (xếp toàn bộ) (chọn N dòng đầu)
```

Về hiệu năng, Oracle **không nhất thiết phải sort toàn bộ** trong plan đúng. Nó có thể dùng index đã sắp xếp hoặc `SORT ORDER BY STOPKEY` để tối ưu Top-N. Điều bắt buộc là **tập N dòng được trả phải tương đương với sort rồi giới hạn**, không phải thuật toán vật lý phải lưu mọi dòng đã sort.

## 4. Bộ dữ liệu thực hành có kết quả dự đoán được

Để kiểm tra các cách viết, tạo một bảng lab chứa 12 nhân viên, nhiều mức lương trùng và một lương `NULL`.

> Chỉ tạo bảng trong schema lab có quyền `CREATE TABLE`. `CREATE TABLE` là DDL có implicit commit. Nếu không có quyền tạo bảng, dùng bảng có sẵn nhưng phải thay column names/dữ liệu và điều chỉnh kết quả mong đợi.

```sql
CREATE TABLE rownum_staff_lab (
    employee_id   NUMBER
      CONSTRAINT rownum_staff_lab_pk PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    dept_code     VARCHAR2(12 CHAR) NOT NULL,
    salary        NUMBER(10,2),
    hired_on      DATE NOT NULL
);

INSERT INTO rownum_staff_lab VALUES
    (101, 'An',    'FIN', 1200, DATE '2024-01-10');
INSERT INTO rownum_staff_lab VALUES
    (102, 'Binh',  'FIN', 3000, DATE '2022-01-15');
INSERT INTO rownum_staff_lab VALUES
    (103, 'Chi',   'IT',  4500, DATE '2025-04-03');
INSERT INTO rownum_staff_lab VALUES
    (104, 'Dung',  'IT',  3000, DATE '2023-04-07');
INSERT INTO rownum_staff_lab VALUES
    (105, 'Em',    'IT',  6000, DATE '2021-01-01');
INSERT INTO rownum_staff_lab VALUES
    (106, 'Giang', 'OPS', 2500, DATE '2024-06-01');
INSERT INTO rownum_staff_lab VALUES
    (107, 'Ha',    'OPS', 4500, DATE '2023-09-10');
INSERT INTO rownum_staff_lab VALUES
    (108, 'Khanh', 'OPS', 1200, DATE '2024-11-01');
INSERT INTO rownum_staff_lab VALUES
    (109, 'Linh',  'FIN', 6000, DATE '2020-02-01');
INSERT INTO rownum_staff_lab VALUES
    (110, 'Minh',  'FIN', NULL, DATE '2024-02-03');
INSERT INTO rownum_staff_lab VALUES
    (111, 'Nam',   'HR',  4500, DATE '2022-07-03');
INSERT INTO rownum_staff_lab VALUES
    (112, 'Oanh',  'HR',  3200, DATE '2022-09-19');

COMMIT;
```

Để có **thứ tự xác định** cho một snapshot dữ liệu cố định, luôn thêm khóa phân xử trùng lặp:

```sql
SELECT employee_id, employee_name, dept_code, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

Kết quả logic theo thứ tự:

| Vị trí | EMPLOYEE_ID | Tên | SALARY |
| ---: | ---: | --- | ---: |
| 1 | 105 | Em | 6000 |
| 2 | 109 | Linh | 6000 |
| 3 | 103 | Chi | 4500 |
| 4 | 107 | Ha | 4500 |
| 5 | 111 | Nam | 4500 |
| 6 | 112 | Oanh | 3200 |
| 7 | 102 | Binh | 3000 |
| 8 | 104 | Dung | 3000 |
| 9 | 106 | Giang | 2500 |
| 10 | 101 | An | 1200 |
| 11 | 108 | Khanh | 1200 |
| 12 | 110 | Minh | NULL |

Khi thêm/bớt/cập nhật row, thứ tự Top-N tự nhiên có thể đổi. Trong lab, không tạo index theo `salary` chỉ để “ép” thứ tự cho `ROWNUM`: mục tiêu là hiểu rằng kết quả đúng đến từ SQL có `ORDER BY` đúng phạm vi, không phải từ kỳ vọng index/physical access path.

## 5. Cách sai và cách đúng khi dùng `ROWNUM`

### 5.1. Cách sai: `ROWNUM` và `ORDER BY` trong cùng query block

```sql
-- Sai mục tiêu: năm nhân viên lương cao nhất của toàn bảng.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id;
```

Đầu ra **có thể** đã sắp xếp theo lương, nhưng không bảo đảm tập năm dòng gồm `105, 109, 103, 107, 111`. Không suy từ hình thức output “đã giảm dần” rằng nó chọn đúng global Top-5.

### 5.2. Cách đúng: inline view sắp xếp, outer query giới hạn

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5;
```

Kết quả Top-5 theo thứ tự của tiêu chí trong inner view là các ID:

```text
105 → 109 → 103 → 107 → 111
```

Ở đây `ROWNUM` được tạo ở outer query block **sau khi kết quả inner view đã được sắp xếp về mặt ngữ nghĩa**. Đây là mẫu Oracle Top-N cổ điển, dùng được từ trước khi xuất hiện `FETCH FIRST`.

**Một tinh chỉnh cho lớp hiển thị:** nếu client phải nhận kết quả **được bảo đảm trình bày theo thứ tự**, hãy thêm `ORDER BY` ở query block ngoài cùng, không chỉ dựa vào thứ tự trung gian:

```sql
SELECT employee_id, employee_name, salary
FROM (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
WHERE ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

Inner `ORDER BY` quyết định **những row nào thuộc Top-5**. Outer `ORDER BY` là hợp đồng rõ ràng cho **thứ tự output cuối cùng**. Việc lặp lại này có thể được optimizer tối ưu; không nên đánh đồng hai nhiệm vụ.

### 5.3. Một cách khác dùng CTE

```sql
WITH ranked_source AS (
    SELECT employee_id, employee_name, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id ASC
)
SELECT employee_id, employee_name, salary
FROM   ranked_source
WHERE  ROWNUM <= 5;
```

CTE (`WITH` clause) giúp đọc dễ khi source query phức tạp. Nhưng không phải `WITH` tự làm SQL đúng: điểm thiết yếu vẫn là **ROWNUM ở query block bên ngoài nguồn đã sắp xếp**.

### 5.4. Chỉ muốn “bất kỳ 5 dòng” thì `ROWNUM` cùng block không sai

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5;
```

Câu này hợp lệ cho nhu cầu **lấy tối đa năm dòng bất kỳ** (ví dụ thử connectivity hoặc preview sơ bộ). Không có `ORDER BY`, **không có cam kết năm dòng nào sẽ được trả**, ngay cả khi cùng bảng, cùng SQL ở các lần gọi khác nhau.

Vì thế “ROWNUM sai” là kết luận quá rộng. **Sai là dùng ROWNUM để tạo Top-N theo thứ tự mong muốn mà không đưa thứ tự vào đúng query block.**

## 6. Vì sao `WHERE ROWNUM > 1` không trả kết quả?

Đây là đặc điểm gây ngạc nhiên của `ROWNUM`.

```sql
SELECT employee_id, employee_name
FROM   rownum_staff_lab
WHERE  ROWNUM > 1;
```

Câu truy vấn trả **không có row**. Giải thích:

1. Oracle xét một dòng có thể trở thành dòng đầu của kết quả: `ROWNUM = 1`.
2. Điều kiện `ROWNUM > 1` là **FALSE**, dòng đó không được chấp nhận.
3. Dòng kế tiếp vẫn là ứng viên **đầu tiên** được chấp nhận, nên lại có `ROWNUM = 1`.
4. Điều kiện tiếp tục FALSE; lặp lại đến khi hết các dòng ứng viên.

```text
Row ứng viên A  → ROWNUM 1 → 1 > 1?  FALSE → bỏ
Row ứng viên B  → ROWNUM 1 → 1 > 1?  FALSE → bỏ
Row ứng viên C  → ROWNUM 1 → 1 > 1?  FALSE → bỏ
...
Không có “row kết quả đầu tiên” được nhận,
nên ROWNUM không tiến lên 2.
```

Những predicate ở cùng query block cũng có vấn đề tương tự:

```sql
-- Không thể lấy “từ dòng thứ 6” theo cách này:
WHERE ROWNUM > 5

-- Không thể phân trang bằng khoảng ROWNUM trực tiếp:
WHERE ROWNUM BETWEEN 6 AND 10

-- ROWNUM = 2 cũng không chọn “dòng thứ 2”:
WHERE ROWNUM = 2
```

Đối chiếu:

```sql
WHERE ROWNUM = 1       -- Có thể nhận một dòng đầu.
WHERE ROWNUM <= 5      -- Có thể nhận tối đa năm dòng đầu.
WHERE ROWNUM < 6       -- Tương tự <= 5 với số nguyên.
WHERE ROWNUM > 1       -- Không có dòng ở cùng query block.
```

Muốn lấy dòng **vị trí 6 đến 10**, phải **gán số thứ tự trong inner block** rồi lọc alias ở outer block, hoặc dùng `OFFSET/FETCH` hay `ROW_NUMBER()`.

## 7. Cách hiện đại: `ORDER BY ... FETCH FIRST ... ROWS ONLY`

Từ Oracle Database **12c**, `SELECT` có `row_limiting_clause`, thường dễ đọc và ít nhầm hơn việc lồng `ROWNUM`.

### 7.1. Top-5 với cú pháp mới

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Oracle thực hiện ý nghĩa: **lấy những row đứng đầu theo thứ tự đã khai báo**. Với bảng lab cố định, kết quả gồm `105, 109, 103, 107, 111`.

Một số cách viết tương đương:

```sql
FETCH FIRST 5 ROWS ONLY
FETCH NEXT  5 ROWS ONLY
FETCH FIRST 5 ROW  ONLY
```

`FIRST`/`NEXT` và `ROW`/`ROWS` có thể được dùng tương đương theo cú pháp, dù `NEXT` thường dễ hiểu hơn khi có `OFFSET`.

### 7.2. Top-N sau điều kiện lọc

```sql
-- Năm nhân viên IT có lương cao nhất (bảng lab có ít hơn năm).
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Về mặt ngữ nghĩa, Oracle xác định tập row đáp ứng `dept_code='IT'`, xếp theo lương/ID, rồi chọn tối đa năm row. Đừng viết:

```sql
-- Không bảo đảm Top-5 lương trong IT:
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
AND    ROWNUM <= 5
ORDER BY salary DESC NULLS LAST;
```

Nếu bảng IT có hơn năm người, cách sai có thể chỉ sort năm nhân viên được truy cập trước.

### 7.3. `FETCH FIRST n PERCENT ROWS ONLY`

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 25 PERCENT ROWS ONLY;
```

Đây là lựa chọn khi yêu cầu dựa trên **tỷ lệ số row**, không phải N tuyệt đối. Với report có số row tăng giảm liên tục, số row trả về cũng thay đổi theo tổng row. Nếu cần SLA trả đúng tối đa 20 row, dùng `ROWS` chứ không dùng `PERCENT`.

### 7.4. Tham số `OFFSET`/`FETCH` và số lượng bất thường

Theo Oracle 19c SQL Language Reference:

- `OFFSET n ROWS` bỏ qua `n` row trước khi bắt đầu trả dữ liệu; không có OFFSET thì tương đương 0.
- Giá trị OFFSET âm được xử lý như 0; phần lẻ được bỏ.
- `FETCH FIRST n ROWS ONLY` lấy tối đa `n` row còn lại; nếu ít hơn thì trả ít hơn.
- Với `FETCH`, `n = 0` hoặc `n = NULL` cho 0 row; giá trị âm cũng được xử lý thành 0.
- Nếu bỏ `rowcount` sau `FETCH FIRST` trong cú pháp hợp lệ, mặc định lấy 1 row.

Ứng dụng vẫn nên **validate page size và offset** ở API: không phó mặc đầu vào âm/NULL cho SQL engine, không cho phép client tùy ý yêu cầu hàng triệu row.

## 8. Giải quyết trường hợp bằng điểm: `ONLY` hay `WITH TIES`?

Ở bảng lab có:

```text
SALARY = 6000: employee 105, 109
SALARY = 4500: employee 103, 107, 111
SALARY = 3200: employee 112
...
```

### 8.1. `ONLY` giới hạn theo số dòng

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 3 ROWS ONLY;
```

Trả ba người: `105`, `109`, `103`. Nhân viên `107` và `111` cũng có lương 4500 nhưng bị loại do chỉ lấy **ba row**. Đây là đúng nếu yêu cầu thật sự là “lấy đúng ba nhân viên”.

### 8.2. `WITH TIES` cho phép vượt N nếu cùng sort key

```sql
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST
FETCH FIRST 3 ROWS WITH TIES;
```

Kết quả gồm **năm** người: cả hai người lương 6000 và cả ba người lương 4500. Vì **row thứ ba** có lương 4500, mọi row khác có **cùng giá trị biểu thức ORDER BY** được lấy thêm.

| Tiêu chí | `ONLY` | `WITH TIES` |
| --- | --- | --- |
| Mục tiêu | Tối đa N dòng | Ít nhất N dòng nếu đủ dữ liệu; có thể thêm các dòng đồng hạng cuối |
| Với bảng lab, `FETCH FIRST 3` theo `salary DESC` | 3 | 5 |
| Sắp thứ tự trong nhóm cùng lương | Không xác định nếu chỉ sort salary | Không xác định nếu chỉ sort salary |
| Có cần `ORDER BY` hợp lý? | **Có**, nếu muốn kết quả ổn định | **Có** để xác định tie key và ý nghĩa ranking |

**Một bẫy quan trọng:** Nếu viết:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
FETCH FIRST 3 ROWS WITH TIES
```

thì mỗi row thường có **bộ khóa sort khác nhau** vì `employee_id` là duy nhất. `WITH TIES` sẽ **không thêm** các nhân viên có cùng salary nhưng khác ID. Khi business định nghĩa “đồng hạng theo lương”, hãy xếp tie theo **salary** mà thôi, hoặc dùng `RANK`/`DENSE_RANK` trong một query riêng. Khi business muốn **Top-N đúng N dòng**, hãy thêm ID để phân xử.

Trong cả hai trường hợp, nếu nhiều row có cùng sort key, muốn thứ tự **hiển thị trong nhóm đồng hạng** ổn định phải có xử lý trình bày khác; không giả định thứ tự giữa các row đồng hạng.

### 8.3. `RANK` và `DENSE_RANK` giúp diễn tả “hạng”

```sql
SELECT employee_id,
       employee_name,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank,
       DENSE_RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_dense_rank
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC;
```

Các nhân viên có lương 6000 đều có `RANK=1`, lương 4500 đều có `RANK=3` (vì hai row đứng trước); `DENSE_RANK` cho nhóm lương 4500 hạng 2 (không bỏ hạng). Muốn “top ba **mức lương**” thì `DENSE_RANK <= 3` sẽ khác “ba **người**” hay `RANK <= 3`.

## 9. Phân trang: tại sao `ROWNUM > offset` trực tiếp không chạy?

Yêu cầu thường gặp của REST API:

```text
Page size = 5
Trang 1: vị trí 1–5
Trang 2: vị trí 6–10
Trang 3: vị trí 11–15
```

### 9.1. Cách sai

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
WHERE  ROWNUM BETWEEN 6 AND 10
ORDER BY salary DESC;
```

Truy vấn sẽ không trả row vì `ROWNUM >= 6` không thể trở thành TRUE cho dòng đầu tiên của **chính query block đó**.

### 9.2. Cách dễ đọc nhất trên Oracle 12c+: `OFFSET` và `FETCH`

```sql
-- Trang 1, 5 row đầu.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY;

-- Trang 2, bỏ 5 row đầu và lấy 5 row tiếp.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;

-- Trang 3, bỏ 10 row và lấy tối đa 5 row.
SELECT employee_id, employee_name, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id ASC
OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY;
```

Với dữ liệu lab không đổi:

| Trang | Vị trí | EMPLOYEE_ID dự kiến |
| --- | --- | --- |
| 1 | 1–5 | 105, 109, 103, 107, 111 |
| 2 | 6–10 | 112, 102, 104, 106, 101 |
| 3 | 11–15 | 108, 110 |

Tính offset ở ứng dụng theo công thức:

```text
offset = (pageNumber - 1) * pageSize
```

Trang đánh số từ 1, `pageNumber >= 1` và `pageSize > 0`. Cần giới hạn giá trị để tránh input lỗi/overflow, đồng thời bảo vệ database khỏi truy vấn quá tốn tài nguyên.

### 9.3. Phân trang bằng `ROWNUM` truyền thống

Trên Oracle 11g hoặc khi cần tương thích cú pháp cũ, có thể dùng **ba tầng**:

```sql
SELECT employee_id, employee_name, salary, rn
FROM (
    SELECT ordered_staff.employee_id,
           ordered_staff.employee_name,
           ordered_staff.salary,
           ROWNUM AS rn
    FROM (
        SELECT employee_id, employee_name, salary
        FROM   rownum_staff_lab
        ORDER BY salary DESC NULLS LAST, employee_id ASC
    ) ordered_staff
    WHERE ROWNUM <= 10
)
WHERE rn > 5
ORDER BY rn;
```

Đây là **trang 2 với page size 5**: chấp nhận tối đa 10 row theo thứ tự trong cùng một nhánh, đặt `rn=1..10` ở tầng giữa, rồi dùng tầng ngoài lọc `rn > 5`. Cột `rn` ở ngoài **đã là một giá trị được gán trong inner query**, khác pseudocolumn `ROWNUM` mới của outer block.

Sơ đồ:

```text
Tầng 1 (trong cùng):
    Sort toàn tập row theo salary DESC, employee_id ASC
                      │
                      ▼
Tầng 2:
    Nhận row đã sort, gán rn = ROWNUM
    WHERE ROWNUM <= :upper_bound   (offset + page_size)
                      │
                      ▼
Tầng 3:
    WHERE rn > :lower_bound        (offset)
    ORDER BY rn
```

Trong mã thực dùng bind variables `:upper_bound` và `:lower_bound` sau khi kiểm tra chúng; không nối chuỗi số từ request vào SQL. Nên đặt giới hạn **trên** ở tầng giữa để tránh lấy dư dữ liệu rồi chỉ lọc trang ở cuối.

### 9.4. Hai tầng không đủ nếu dùng sai vị trí alias

```sql
-- Sai: không thể dùng alias rn được tạo trong SELECT
-- trong WHERE của chính query block đó.
SELECT ROWNUM AS rn, employee_id
FROM   rownum_staff_lab
WHERE  rn BETWEEN 6 AND 10;
```

Trong Oracle, alias của select list thông thường không được dùng trực tiếp trong `WHERE` của cùng query block. Phải tạo alias trong **inner query** và lọc nó ở **outer query**.

## 10. Trật tự sắp xếp phải đủ rõ để phân trang ổn định

### 10.1. Thứ tự không duy nhất khiến page “nhảy” dù dữ liệu không đổi

Nếu chỉ dùng:

```sql
ORDER BY salary DESC
```

ba nhân viên có lương 4500 đồng hạng. Oracle không được yêu cầu phân định `103`, `107` hay `111` đứng trước. Nếu ranh giới trang cắt qua nhóm này, lần gọi trang 1 và trang 2 có thể cho ra những nhân viên **trùng hoặc bị bỏ sót** vì tie order không được bảo đảm.

Sửa bằng thứ tự **toàn phần (total order)**:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
```

`employee_id` là PK và duy nhất, nên với **cùng một snapshot dữ liệu** mọi row có vị trí được xác định. Nếu sort theo ngày, cũng thêm PK:

```sql
ORDER BY hired_on DESC, employee_id DESC
```

### 10.2. Dữ liệu thay đổi giữa các trang vẫn có thể gây sai lệch

Ngay cả khi sort có khóa phân xử duy nhất, `OFFSET` không tự “đóng băng” một tập kết quả qua nhiều HTTP requests.

Giả sử client lấy trang 1 gồm 5 row. Trước khi client lấy trang 2, một nhân viên mới có lương rất cao được chèn lên đầu danh sách. Những dòng cũ dịch vị trí xuống một bậc, khiến `OFFSET 5` có thể **lặp lại một dòng đã xuất hiện ở trang 1**. Xóa một row đầu danh sách có thể gây **bỏ sót**.

Đây là lỗi **pagination dưới concurrent modifications**, khác lỗi `ROWNUM` chọn trước sort.

Các biện pháp tùy yêu cầu:

- Có **ORDER BY toàn phần** để xử lý tie ordering.
- Với feed lớn/liên tục thay đổi, cân nhắc **keyset/seek pagination**.
- Nếu yêu cầu nhiều trang phải cùng ảnh dữ liệu tại một thời điểm, cân nhắc cơ chế **consistent snapshot**, chẳng hạn query theo một SCN/Flashback Query khi quyền và undo retention cho phép, hoặc chiến lược snapshot khác.
- Chấp nhận rằng ứng dụng browsing realtime có thể nhìn thấy dữ liệu thay đổi; ghi rõ semantics trong API thay vì cam kết “mọi trang luôn không trùng” mà không kiểm soát snapshot.

### 10.3. Keyset pagination (seek method) theo ngày và PK

Với `hired_on NOT NULL` và `employee_id PK`, sắp theo:

```sql
SELECT employee_id, employee_name, hired_on
FROM   rownum_staff_lab
ORDER BY hired_on DESC, employee_id DESC
FETCH FIRST 5 ROWS ONLY;
```

Client lưu khóa của **row cuối cùng** trong kết quả: `last_hired_on` và `last_employee_id`. Trang tiếp theo:

```sql
SELECT employee_id, employee_name, hired_on
FROM   rownum_staff_lab
WHERE  hired_on < :last_hired_on
   OR (hired_on = :last_hired_on
       AND employee_id < :last_employee_id)
ORDER BY hired_on DESC, employee_id DESC
FETCH FIRST 5 ROWS ONLY;
```

Điều kiện con trỏ này chọn những row **đứng sau** row cuối trang trước theo thứ tự giảm dần. Các bind `:last_hired_on`, `:last_employee_id` phải lấy từ kết quả thật, đúng datatype và timezone/precision nếu là timestamp. Khi có sort key `NULL`, hướng tăng/giảm hỗn hợp, hoặc filter thay đổi, predicate seek cần thiết kế thêm; không chép công thức này cho mọi ORDER BY.

**Keyset thường tránh việc phải “bỏ qua” một offset lớn**, nhưng không tự tạo snapshot bất biến và không giải quyết mọi vấn đề nếu bản ghi được sửa sort key giữa các requests.

## 11. `ROW_NUMBER()`: khi cần đánh số theo thứ tự thật

Oracle có analytic function:

```sql
ROW_NUMBER() OVER (ORDER BY salary DESC NULLS LAST, employee_id ASC)
```

Khác với `ROWNUM`, `ROW_NUMBER()` **định nghĩa thứ tự đánh số ngay trong `OVER (ORDER BY ...)`**. Nó có thể phân nhóm bằng `PARTITION BY`.

### 11.1. Gán thứ hạng cho toàn bộ row

```sql
SELECT employee_id,
       employee_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id ASC
       ) AS rn
FROM   rownum_staff_lab
ORDER BY rn;
```

Với bảng lab, `rn=1` thuộc `employee_id=105`, `rn=2` thuộc `109`, `rn=3` thuộc `103`...

**Hai ORDER BY làm hai việc:**

- `ORDER BY` bên trong `OVER` quy định **cách tính giá trị `rn`**.
- `ORDER BY rn` ngoài cùng quy định **thứ tự trình bày các row cho client**.

Không có outer `ORDER BY`, output SQL vẫn không nên được xem là có thứ tự hiển thị được cam kết chỉ vì analytic function đã đánh số.

### 11.2. Top-N bằng analytic function

```sql
SELECT employee_id, employee_name, salary, rn
FROM (
    SELECT employee_id,
           employee_name,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id ASC
           ) AS rn
    FROM   rownum_staff_lab
)
WHERE rn <= 5
ORDER BY rn;
```

Hàm analytic được tính trong inner query; filter `rn <= 5` phải nằm ở outer query trong cách viết Oracle 19c này. Không dùng analytic function trực tiếp trong `WHERE` của cùng query block, vì analytic được xử lý ở giai đoạn SQL khác.

### 11.3. Vì sao `ROW_NUMBER` vẫn cần tie-breaker?

Nếu chỉ:

```sql
ROW_NUMBER() OVER (ORDER BY salary DESC)
```

hai nhân viên cùng lương 6000 phải được gán hai số khác nhau, nhưng thứ tự tương đối không được xác định bởi expression. Với Top-N cắt ngang nhóm đồng hạng, nhân viên nào được giữ lại có thể khác giữa các lần chạy. Thêm `employee_id` để có thứ tự toàn phần khi yêu cầu **đúng N row**.

`ROW_NUMBER()` khác `RANK()`:

| SALARY | Số row trong nhóm lương | ROW_NUMBER (mỗi row) | RANK | DENSE_RANK |
| ---: | ---: | --- | ---: | ---: |
| 6000 | 2 | 1, 2 | 1 | 1 |
| 4500 | 3 | 3, 4, 5 | 3 | 2 |
| 3200 | 1 | 6 | 6 | 3 |

Nếu câu hỏi là “ba mức lương đứng đầu” thì `DENSE_RANK <= 3` khác “ba nhân viên đầu tiên” (`ROW_NUMBER <= 3`).

## 12. Top-N **trong từng nhóm**: bài toán `ROWNUM` đơn giản không giải được

Yêu cầu: **mỗi phòng ban lấy hai nhân viên lương cao nhất**. Đây không phải một global Top-2.

### 12.1. Sai: một `ROWNUM` trên toàn câu truy vấn

```sql
SELECT dept_code, employee_id, employee_name, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 2
ORDER BY dept_code, salary DESC;
```

Chỉ có **tối đa hai row tổng cộng**, không phải hai row cho mỗi `dept_code`.

### 12.2. Đúng: `PARTITION BY dept_code`

```sql
SELECT dept_code,
       employee_id,
       employee_name,
       salary
FROM (
    SELECT dept_code,
           employee_id,
           employee_name,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST, employee_id ASC
           ) AS rn
    FROM   rownum_staff_lab
)
WHERE rn <= 2
ORDER BY dept_code, salary DESC NULLS LAST, employee_id ASC;
```

Oracle đánh số **lại từ 1 cho từng phòng ban** vì `PARTITION BY dept_code`.

Kết quả dự kiến của bảng lab:

| DEPT_CODE | EMPLOYEE_ID | SALARY | Lý do |
| --- | ---: | ---: | --- |
| FIN | 109 | 6000 | Hạng 1 FIN |
| FIN | 102 | 3000 | Hạng 2 FIN |
| HR | 111 | 4500 | Hạng 1 HR |
| HR | 112 | 3200 | Hạng 2 HR |
| IT | 105 | 6000 | Hạng 1 IT |
| IT | 103 | 4500 | Hạng 2 IT |
| OPS | 107 | 4500 | Hạng 1 OPS |
| OPS | 106 | 2500 | Hạng 2 OPS |

### 12.3. Top hai **mức lương** mỗi nhóm, giữ đồng hạng

Nếu business muốn “mọi nhân viên nằm trong **hai mức lương cao nhất** của phòng ban”, dùng `DENSE_RANK`:

```sql
SELECT dept_code, employee_id, employee_name, salary
FROM (
    SELECT dept_code,
           employee_id,
           employee_name,
           salary,
           DENSE_RANK() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST
           ) AS salary_level_rank
    FROM rownum_staff_lab
)
WHERE salary_level_rank <= 2
ORDER BY dept_code, salary DESC NULLS LAST, employee_id;
```

Số row mỗi phòng ban có thể **lớn hơn 2** khi có đồng hạng. Đây là lựa chọn chủ đích về semantics, không phải SQL trả dư ngoài ý muốn.

## 13. Top-N trên dữ liệu JOIN: giới hạn là **số row output**, không phải số parent

Giả sử có hai bảng:

```text
ORDERS(order_id, created_at, customer_id)
ORDER_ITEMS(order_id, line_no, sku, quantity)
```

Một đơn hàng có thể có nhiều item. Câu SQL:

```sql
SELECT o.order_id, o.created_at, i.line_no, i.sku
FROM   orders o
JOIN   order_items i ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 10 ROWS ONLY;
```

lấy **10 row của phép JOIN**, **không phải 10 đơn hàng**. Nếu đơn hàng mới nhất có 15 item, mười row đầu có thể chỉ thuộc **một đơn hàng**, và các item còn lại của chính đơn đó bị cắt.

Nếu yêu cầu là **10 đơn hàng mới nhất cùng toàn bộ item của chúng**, hãy chọn parent trước rồi JOIN:

```sql
WITH latest_orders AS (
    SELECT o.order_id, o.created_at
    FROM   orders o
    ORDER BY o.created_at DESC, o.order_id DESC
    FETCH FIRST 10 ROWS ONLY
)
SELECT o.order_id, o.created_at, i.line_no, i.sku
FROM   latest_orders o
LEFT JOIN order_items i
       ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC, i.line_no;
```

CTE bảo đảm tập **10 parent orders** được chọn theo thứ tự. Kết quả cuối có thể gồm **nhiều hơn 10 row** vì có nhiều item trên mỗi order. `LEFT JOIN` giữ cả đơn hàng không có item, nếu nghiệp vụ muốn hiển thị chúng.

**Quy tắc tổng quát:** Xác định “N cái gì?” — N joined rows, N parent entities, N distinct groups hay N phần tử trong mỗi group. Việc đặt `FETCH`/`ROWNUM` ở sai tầng quan hệ rất dễ tạo kết quả không đúng ý.

## 14. Top-N sau `GROUP BY` và aggregate

Yêu cầu: “lấy ba phòng ban có quỹ lương cao nhất”:

```sql
SELECT dept_code,
       SUM(salary) AS salary_total
FROM   rownum_staff_lab
GROUP BY dept_code
ORDER BY salary_total DESC NULLS LAST, dept_code ASC
FETCH FIRST 3 ROWS ONLY;
```

Đây là **Top-3 groups sau aggregation**, không phải lấy 3 nhân viên trước rồi tổng hợp.

Hãy phân biệt:

```sql
-- SAI mục tiêu tổng lương Top-3 phòng ban:
SELECT dept_code, SUM(salary) AS salary_total
FROM (
    SELECT dept_code, salary
    FROM   rownum_staff_lab
    WHERE  ROWNUM <= 3
)
GROUP BY dept_code
ORDER BY salary_total DESC;
```

Câu sai chỉ tổng hợp dữ liệu của ba nhân viên lấy sớm, chứ không tính tổng toàn bộ phòng ban.

Về mặt kết quả, bài toán đúng cần:

```text
Nguồn row nhân viên
        │
        ▼
GROUP BY dept_code, SUM(salary)
        │
        ▼
ORDER BY salary_total DESC
        │
        ▼
FETCH FIRST 3 ROWS ONLY
```

`HAVING` (nếu có) lọc các group sau aggregation trước khi xét Top-N. Một lần nữa, **vị trí giới hạn ở query block nào** mới quyết định nghĩa.

## 15. `DISTINCT`, `UNION` và giới hạn kết quả

### 15.1. `DISTINCT` phải chọn toàn bộ giá trị khác nhau trước khi Top-N

Nếu muốn “ba mức lương khác nhau cao nhất”:

```sql
SELECT DISTINCT salary
FROM   rownum_staff_lab
WHERE  salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 3 ROWS ONLY;
```

Kết quả: `6000, 4500, 3200`, không phải ba nhân viên. Cú pháp và semantics của `DISTINCT` giải quyết trùng lặp trước row limiting ở cấp kết quả đó.

Đừng viết:

```sql
-- Chỉ lấy 3 row bất kỳ trước, DISTINCT sau:
SELECT DISTINCT salary
FROM (
    SELECT salary
    FROM   rownum_staff_lab
    WHERE  ROWNUM <= 3
);
```

và mong nhận Top-3 lương khác nhau: nội dung subquery đã bị cắt tùy thứ tự truy cập.

### 15.2. `UNION ALL` và giới hạn từng nhánh hay toàn bộ

Giả sử hai nguồn `current_orders` và `archived_orders`. Hai yêu cầu khác:

1. **Top-10 trên hợp của hai nguồn**: `UNION ALL` trong CTE/inline view rồi **ORDER BY/FETCH trên tập hợp ngoài**.
2. **Top-10 ở mỗi nguồn, rồi ghép tối đa 20 row**: áp Top-N **riêng từng nhánh** trước khi `UNION ALL`.

Oracle không bảo đảm `ORDER BY` đặt trong các nhánh của set operator có nghĩa là thứ tự cuối. `ORDER BY` tổng hợp cuối cùng phải nằm ở query block ngoài tương ứng. Nếu dùng `FETCH` trong nhánh, nên đặt nhánh thành inline view/CTE rõ ràng và dùng output `ORDER BY` khi cần.

## 16. Dùng `ROWNUM` để dừng sớm: khi nào phù hợp?

### 16.1. Kiểm tra có row phù hợp hay không

```sql
-- Tối đa một row, không yêu cầu “đầu tiên” theo thứ tự nghiệp vụ.
SELECT employee_id
FROM   rownum_staff_lab
WHERE  dept_code = 'IT'
AND    ROWNUM = 1;
```

Phù hợp nếu ứng dụng chỉ muốn biết **có ít nhất một row IT**. Tùy trường hợp, `EXISTS` trong một query khác cũng diễn đạt rõ ý nghĩa tồn tại:

```sql
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM   rownum_staff_lab
    WHERE  dept_code = 'IT'
) THEN 'Y' ELSE 'N' END AS exists_it
FROM dual;
```

`ROWNUM <= 1` có thể giúp dừng sau một row thỏa điều kiện. Tuy nhiên, nếu chỉ cần boolean và ở câu lệnh có logic phức tạp, `EXISTS` thường rõ mục tiêu hơn.

### 16.2. Lấy sample để xem cột dữ liệu

```sql
SELECT employee_id, dept_code, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 10;
```

Đây là **sample tùy ý theo đường truy cập**, không phải **random sample thống kê**. Nó có thể có bias nếu dữ liệu lưu/clustering theo một thuộc tính nào đó. Muốn lấy random sample hay sampling có ý nghĩa thống kê, cần chọn cơ chế sampling phù hợp, không thay bằng `ROWNUM`.

### 16.3. Hạn chế row khi cập nhật/xóa: cảnh báo

```sql
-- KHÔNG chạy trên bảng thật chỉ để thử:
-- DELETE FROM some_table WHERE ROWNUM <= 100;
```

Lệnh trên có thể xóa **bất kỳ 100 row nào Oracle gặp trước**, không bảo đảm 100 row cũ nhất, mới nhất hay theo ID nhỏ nhất. Đối với batch maintenance, phải chọn tập **business keys** hoặc `ROWID` theo chiến lược có thứ tự và khóa/concurrency phù hợp, rồi áp DML có kiểm soát. Không viết `ORDER BY` ở phần SELECT mô tả rồi giả định DELETE đã tự ưu tiên như vậy.

## 17. `ORDER BY` và các vấn đề NULL, NLS/collation, biểu thức

### 17.1. `NULLS FIRST` và `NULLS LAST`

Trong Oracle thông thường:

- `ORDER BY salary ASC` mặc định tương ứng `NULLS LAST`.
- `ORDER BY salary DESC` mặc định tương ứng `NULLS FIRST`.

Vì bảng lab có `salary = NULL` (nhân viên `110`), viết:

```sql
ORDER BY salary DESC
```

có thể đưa người **không có giá trị salary** lên đầu. Nếu mục tiêu “lương cao nhất nhưng NULL không phải lương cao”, hãy ghi rõ:

```sql
ORDER BY salary DESC NULLS LAST, employee_id ASC
```

NULL không đồng nghĩa `0`. `NVL(salary,0)` thay semantics và có thể ảnh hưởng khả năng sử dụng index; không thay NULL bằng 0 chỉ để tránh `NULLS LAST` nếu nghiệp vụ không coi thiếu lương là 0.

### 17.2. Sắp xếp chuỗi theo NLS/collation

Khi `ORDER BY employee_name`, thứ tự có thể phụ thuộc collation, case sensitivity và cấu hình liên quan. Nếu phân trang phải xác định chính xác, cần chốt collation mà ứng dụng yêu cầu và thêm unique key để phân xử. Không suy rằng chuỗi chữ Việt không dấu/có dấu luôn được xếp một cách giống nhau ở mọi môi trường Oracle.

### 17.3. Sắp xếp theo biểu thức

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY NVL(salary, -1) DESC, employee_id ASC
FETCH FIRST 5 ROWS ONLY;
```

Cú pháp hợp lệ cho yêu cầu coi NULL là `-1` khi sort, nhưng semantics khác `NULLS LAST` nếu salary có giá trị thấp hơn -1. Biểu thức trong ORDER BY cũng có thể ảnh hưởng index/optimizer, nên chọn theo yêu cầu nghiệp vụ thay vì chỉ theo “chạy được”.

## 18. Hiệu năng: `STOPKEY` là cách tối ưu, không thay đổi nghĩa SQL

Khi giới hạn Top-N, Oracle optimizer có thể nhận diện rằng **không cần materialize toàn bộ kết quả đã sort** nếu có cách tìm N row đầu hiệu quả.

Những operation có thể gặp trong execution plan:

| Ký hiệu plan | Cách hiểu sơ bộ |
| --- | --- |
| `COUNT STOPKEY` | Hạn chế số row được chấp nhận từ một nguồn |
| `SORT ORDER BY STOPKEY` | Tối ưu sort khi chỉ cần N row đầu theo thứ tự |
| `WINDOW SORT PUSHED RANK` | Tối ưu xử lý analytic ranking và filter trong một số plan |
| `INDEX RANGE SCAN` / `INDEX FULL SCAN DESCENDING` | Khai thác thứ tự index trong trường hợp phù hợp |
| `SORT ORDER BY` | Sort kết quả khi cần; có thể tốn memory/temp và I/O |

**Không suy diễn rằng mọi `FETCH FIRST 10` luôn rẻ:** Nếu query phải JOIN nhiều bảng, aggregate hoặc đánh giá biểu thức phức tạp trước khi biết Top-10, database vẫn có thể xử lý lượng dữ liệu rất lớn. Một index phù hợp với `WHERE` và `ORDER BY` có thể giúp đáng kể, nhưng phải đo execution plan thực tế, selectivity, cardinality, stats, distribution và bind values.

### 18.1. Truy vấn có thể “tình cờ đúng” sau khi tạo index

Giả sử một index:

```sql
-- Chỉ là DDL minh họa, không tự động tạo trong production.
-- CREATE INDEX staff_salary_idx
--   ON rownum_staff_lab(salary DESC, employee_id ASC);
```

Nếu optimizer dùng đường truy cập đã sắp xếp theo index, câu sai `WHERE ROWNUM <= 5 ORDER BY salary DESC` có thể cho đúng năm người cao nhất trong một số tình huống. Nhưng Oracle **không cam kết đường truy cập đó**. Một lúc khác optimizer chọn full scan và kết quả đổi.

**Ngữ nghĩa phải đúng độc lập với execution plan.** Index dùng để tối ưu một câu SQL **đã đúng**.

### 18.2. `OFFSET` lớn có thể đắt

```sql
SELECT employee_id, hired_on
FROM   rownum_staff_lab
ORDER BY hired_on DESC, employee_id DESC
OFFSET 100000 ROWS FETCH NEXT 20 ROWS ONLY;
```

Về mặt logic, Oracle phải xác định và bỏ qua một lượng lớn row đầu. Dù có index, offset tăng thường làm chi phí truy vấn cao hơn và có thể không phù hợp với feed quy mô lớn. **Keyset pagination** thường hữu ích khi người dùng chỉ cần “trang tiếp theo” theo một cursor sort key.

### 18.3. `ROWNUM` có thể ảnh hưởng optimizer transformations

`ROWNUM` ở một query block có thể tác động việc Oracle **merge inline view**, push predicate hoặc thay đổi cách thực thi query. Vì thế, khi tinh chỉnh performance, không tùy tiện dời `ROWNUM` qua lại giữa các query blocks chỉ để query ngắn hơn. Dời vị trí có thể **thay đổi tập row được giới hạn**, không chỉ thay đổi plan.

## 19. Giới hạn `row_limiting_clause` trong Oracle Database 19c

Tài liệu Oracle 19c nêu một số hạn chế đáng chú ý khi dùng `OFFSET/FETCH`:

1. **Không kết hợp trực tiếp với `FOR UPDATE`** trong cùng `SELECT` theo giới hạn của Oracle 19c. Với release mới, kiểm tra lại tài liệu vì tính năng có thể thay đổi.
2. Select list không được chứa sequence pseudocolumns `CURRVAL` hoặc `NEXTVAL` khi dùng row_limiting_clause.
3. Một materialized view có query định nghĩa chứa row_limiting_clause không đủ điều kiện **incremental refresh** theo hạn chế nêu trong tài liệu 19c.
4. Nếu select list có **hai cột trùng tên**, dùng row_limiting_clause có thể gây `ORA-00918`. Đặt alias khác nhau cho cột output.

Ví dụ lỗi trùng tên output:

```sql
-- Có thể gây ORA-00918 khi select list có nhiều cột trùng tên.
SELECT a.id, b.id
FROM   parent_table a
JOIN   child_table b ON b.parent_id = a.id
ORDER BY a.id
FETCH FIRST 10 ROWS ONLY;

-- Dùng alias duy nhất:
SELECT a.id AS parent_id,
       b.id AS child_id
FROM   parent_table a
JOIN   child_table b ON b.parent_id = a.id
ORDER BY a.id
FETCH FIRST 10 ROWS ONLY;
```

Các tên bảng `PARENT_TABLE`/`CHILD_TABLE` chỉ minh họa, không thuộc bộ dữ liệu lab. Giới hạn ở đây gắn với **SQL Language Reference 19c**; không mặc định áp một-một cho Oracle AI Database 26ai hay release tương lai.

## 20. Lỗi thường gặp: bảng tra cứu nhanh

| Ý định | SQL hoặc triệu chứng sai | Nguyên nhân | Cách viết đúng |
| --- | --- | --- | --- |
| Lấy Top-10 theo lương | `WHERE ROWNUM <= 10 ORDER BY salary DESC` | Giới hạn trước sort trong cùng query block | Inline view sort rồi outer `ROWNUM`, hoặc `FETCH FIRST` |
| Lấy trang 2 | `WHERE ROWNUM > 10` | `ROWNUM=1` của row đầu bị loại mãi mãi | `OFFSET 10` hoặc alias `rn` ở outer query |
| Lấy dòng thứ 5 | `WHERE ROWNUM = 5` | Không có dòng nào làm `ROWNUM` lên 5 | `ROW_NUMBER` sau sort hoặc `OFFSET 4 FETCH NEXT 1` |
| Top-3 theo phòng ban | `WHERE ROWNUM <= 3` | Chỉ là ba row trên toàn query | `ROW_NUMBER OVER(PARTITION BY ... ORDER BY...)` |
| “Top 3 mức lương” | `ROW_NUMBER <= 3` | Đếm người, không đếm mức lương | `DENSE_RANK` theo salary |
| Đủ ba row, có người đồng hạng cuối | `FETCH FIRST 3 ROWS ONLY` | `ONLY` cắt đồng hạng | `WITH TIES` theo đúng tie-key |
| `WITH TIES` nhưng chỉ trả 3 người | `ORDER BY salary DESC, employee_id` | PK làm mọi sort key duy nhất | Nếu muốn đồng hạng theo lương, sort tie theo salary |
| Lương cao nhất nhưng nhân viên NULL đứng đầu | `ORDER BY salary DESC` | DESC mặc định NULLS FIRST | `ORDER BY salary DESC NULLS LAST` |
| Page có row trùng/thiếu khi dữ liệu không đổi | `ORDER BY salary DESC` | Salary trùng, không có tie-breaker | Thêm unique key vào ORDER BY |
| Page trùng khi có INSERT mới | `OFFSET` xuyên nhiều requests | Vị trí row bị dịch giữa requests | Keyset hoặc snapshot theo yêu cầu |
| Lấy 10 đơn mới nhất, nhưng chỉ thấy một đơn | `JOIN ORDER_ITEMS ... FETCH FIRST 10 ROWS` | Giới hạn joined rows, không phải orders | Chọn 10 parent trước rồi join |
| Nhanh nhưng sai sau khi optimizer thay đổi | Câu sai tình cờ dùng index theo sort key | Phụ thuộc access path | Sửa semantics SQL, sau đó tối ưu index |
| `ORA-00918` với `FETCH` | Select list có hai tên cột trùng | Row limiting clause 19c bị hạn chế | Alias output duy nhất |
| Thấy `ORA-00933` hoặc syntax error trên Oracle cũ | Dùng `FETCH FIRST` ở 11g | Version không hỗ trợ row_limiting_clause | Inline view + `ROWNUM` truyền thống |

## 21. Cách đọc yêu cầu nghiệp vụ để chọn kỹ thuật

Trước khi viết câu SQL, hỏi năm câu:

1. **N cái gì?** N row, N parent entities, N group, N rank hay N row trong mỗi group?
2. **Xếp theo tiêu chí nào?** Salary, ngày tạo, tổng doanh thu, mức độ ưu tiên hay nhiều tiêu chí?
3. **Nếu bằng điểm thì sao?** Cắt đúng N row, hay trả thêm mọi row đồng hạng ở ranh giới?
4. **Kết quả phải ổn định giữa những lần gọi không?** Có khóa phân xử duy nhất? Dữ liệu có thay đổi giữa các trang không?
5. **Đang dùng Oracle release nào?** 11g cần `ROWNUM`/analytic pattern; 12c+ dùng `OFFSET/FETCH` khi phù hợp.

Ma trận chọn công cụ:

| Yêu cầu | Mẫu ưu tiên |
| --- | --- |
| Lấy tối đa N dòng bất kỳ, không quan tâm thứ tự | `WHERE ROWNUM <= :n` |
| Top-N toàn bảng theo ORDER BY, Oracle 12c+ | `ORDER BY ... FETCH FIRST :n ROWS ONLY` |
| Top-N toàn bảng trên 11g | `SELECT ... FROM (SELECT ... ORDER BY ...) WHERE ROWNUM <= :n` |
| Trang thứ k trên Oracle 12c+ | `ORDER BY unique_key ... OFFSET :offset ROWS FETCH NEXT :size ROWS ONLY` |
| Trang trên Oracle 11g | Ba tầng query với `ROWNUM AS rn` |
| Duyệt tuần tự feed lớn theo cursor | Keyset/seek pagination |
| N row cao nhất ở từng phòng ban | `ROW_NUMBER() OVER (PARTITION BY dept ORDER BY ...)` |
| Mọi row đồng hạng ở Top-N | `FETCH ... WITH TIES` hoặc `RANK` phù hợp |
| Top-N sau tổng hợp | `GROUP BY ... ORDER BY aggregate DESC FETCH FIRST N` |
| N parent có tất cả child rows | Chọn parent Top-N ở inner CTE rồi JOIN ngoài |

## 22. Bài thực hành so sánh từng kỹ thuật

> Sử dụng bảng `ROWNUM_STAFF_LAB` đã tạo ở phần 4. Các `SELECT` là read-only. Tránh kết luận từ **một kết quả tình cờ** của câu sai; so sánh bằng ngữ nghĩa và tập kết quả đúng từ SQL có ORDER BY rõ ràng.

### Bài A — So sánh query sai và query đúng

```sql
-- A1: Không bảo đảm Top-5 lương lớn nhất.
SELECT employee_id, salary
FROM   rownum_staff_lab
WHERE  ROWNUM <= 5
ORDER BY salary DESC NULLS LAST, employee_id;

-- A2: Top-5 đúng qua inline view + outer ROWNUM.
SELECT employee_id, salary
FROM (
    SELECT employee_id, salary
    FROM   rownum_staff_lab
    ORDER BY salary DESC NULLS LAST, employee_id
)
WHERE ROWNUM <= 5;

-- A3: Top-5 đúng qua FETCH.
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

**Kết quả cần hiểu:** A2 và A3 chọn các ID `105, 109, 103, 107, 111`; A1 **không có cam kết** tập row này, dù có thể trùng do plan hiện tại.

### Bài B — `ROWNUM > 1`

```sql
SELECT employee_id
FROM   rownum_staff_lab
WHERE  ROWNUM > 1;
```

Dự đoán trước khi chạy: **0 row**, dù bảng có 12 row. Sau đó trả lời vì sao Oracle không tăng ROWNUM đến 2 khi không row nào vượt được điều kiện đầu tiên.

### Bài C — Phân trang 5 row

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST, employee_id
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;
```

Dự đoán: `112, 102, 104, 106, 101`.

Sau đó chuyển câu SQL sang mẫu ROWNUM ba tầng và đối chiếu **tập row**, không chỉ thứ tự bản in.

### Bài D — Đồng hạng

```sql
SELECT employee_id, salary
FROM   rownum_staff_lab
ORDER BY salary DESC NULLS LAST
FETCH FIRST 3 ROWS WITH TIES;
```

Kết quả **5 row** vì row thứ ba thuộc mức lương 4500 và còn hai người cùng mức lương đó. Thử thêm `employee_id` vào ORDER BY, giải thích vì sao kết quả thay đổi.

### Bài E — Top-2 trong từng nhóm

```sql
SELECT dept_code, employee_id, salary
FROM (
    SELECT dept_code,
           employee_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY dept_code
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM rownum_staff_lab
)
WHERE rn <= 2
ORDER BY dept_code, rn;
```

Kiểm tra tổng row: có 4 phòng ban, mỗi phòng có ít nhất 2 nhân viên → kết quả **8 row**. Không thể đạt điều này bằng một `ROWNUM <= 2` ở query block chung.

### Bài F — Top-3 mức lương khác nhau

```sql
SELECT DISTINCT salary
FROM   rownum_staff_lab
WHERE  salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 3 ROWS ONLY;
```

Dự đoán: `6000, 4500, 3200`. Sau đó thử analytic `DENSE_RANK` để trả **tất cả nhân viên** thuộc ba mức lương này và so sánh số row.

### Bài G — Dọn lab sau khi học xong

```sql
-- CHỈ chạy nếu bảng do chính bạn tạo trong schema lab
-- và không còn dữ liệu cần giữ. DDL không rollback bằng ROLLBACK.
DROP TABLE rownum_staff_lab PURGE;
```

Không chạy `DROP TABLE` trên schema ứng dụng thật. Nếu muốn giữ môi trường cho phần luyện tập sau, bỏ qua bước này.

## 23. Câu hỏi ôn tập

**1.** Câu sau có chắc trả ba nhân viên lương cao nhất không? Vì sao?

```sql
SELECT employee_id, salary
FROM   employees
WHERE  ROWNUM <= 3
ORDER BY salary DESC;
```

**2.** `WHERE ROWNUM = 5` trả row nào, nếu có 100 row ứng viên?

**3.** Vì sao `SELECT ... FROM (SELECT ... ORDER BY salary DESC) WHERE ROWNUM <= 3` có ý nghĩa khác câu ở câu hỏi 1?

**4.** Với `ORDER BY salary DESC` có ba nhân viên bằng lương ở ranh giới, làm sao lấy **đúng 3 row** ổn định? Nếu muốn **bao gồm tất cả người đồng hạng** thì làm sao?

**5.** Tại sao `FETCH FIRST 3 ROWS WITH TIES` có thể trả đúng 3 row sau khi thêm một primary key vào cuối ORDER BY?

**6.** Khi `ORDER BY salary DESC`, một row `salary=NULL` có thể xuất hiện ở đầu không? Viết cách xử lý.

**7.** Muốn lấy 5 row ở trang thứ ba với page size = 5, `OFFSET` phải bằng mấy?

**8.** Một query JOIN `ORDERS` với `ORDER_ITEMS` rồi `FETCH FIRST 10 ROWS ONLY` trả “10 đơn hàng” hay “10 joined rows”?

**9.** Một API dùng `ORDER BY created_at DESC, id DESC OFFSET 20`. Giữa các lần gọi có row mới chèn đầu feed; có thể trùng page dù đã có unique tie-breaker không?

**10.** Nêu điểm khác nhau giữa `ROWNUM` và `ROW_NUMBER() OVER (PARTITION BY dept_code ORDER BY salary DESC)`.

**11.** Muốn top 3 phòng ban theo tổng lương, nên đặt `FETCH` trước hay sau `GROUP BY`/`ORDER BY SUM(salary)`?

**12.** Có thể dùng `SELECT ... FOR UPDATE FETCH FIRST 5 ROWS ONLY` trực tiếp trên Oracle 19c không?

<details>
<summary>Gợi ý đáp án</summary>

1. **Không.** `ROWNUM` giới hạn theo đường truy cập của cùng query block trước khi `ORDER BY` cuối cùng sắp xếp các dòng đã lấy.
2. **Không row nào.** Dòng đầu có ROWNUM 1 không thỏa; mọi dòng tiếp theo lại là ứng viên đầu, vẫn ROWNUM 1.
3. Inner query có `ORDER BY` xác định thứ tự trước, còn `ROWNUM` ở outer query block chọn ba dòng đầu trong kết quả đã xếp.
4. **Đúng 3 row:** thêm PK làm tie-breaker, dùng `FETCH FIRST 3 ROWS ONLY`. **Bao gồm đồng hạng:** `WITH TIES` trên thứ tự theo tiêu chí đồng hạng hoặc `RANK` tương ứng.
5. `WITH TIES` so sánh **tất cả biểu thức ORDER BY**; PK duy nhất khiến không có row khác trùng cả bộ khóa.
6. Có: với DESC, NULL mặc định được xếp trước. Dùng `ORDER BY salary DESC NULLS LAST, employee_id`.
7. `OFFSET 10` vì bỏ qua hai trang đầu (2 × 5).
8. **10 joined rows**, có thể thuộc ít hơn 10 đơn. Chọn đơn hàng Top-N trước rồi JOIN item sau.
9. **Có.** Thứ tự toàn phần xử lý tie, không giữ snapshot bất biến khi dữ liệu thay đổi. Dùng keyset/snapshot nếu yêu cầu.
10. `ROWNUM` là pseudocolumn đánh số theo việc row được chọn trong query block; `ROW_NUMBER` là analytic ranking theo ORDER BY có thể reset theo nhóm `PARTITION BY`.
11. Sau khi tạo group và tính tổng, sort theo tổng, rồi giới hạn Top-3. Không lấy ba nhân viên đầu trước khi aggregate.
12. **Không** theo restrictions của `row_limiting_clause` Oracle 19c; cần thiết kế query/locking khác phù hợp và xem release đang chạy.

</details>

## 24. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): định nghĩa `ROWNUM`, lỗi khi `ORDER BY` đặt cùng query block, mẫu inline view Top-N và lý do `ROWNUM > 1` không trả row.
2. [Oracle Database 19c SQL Language Reference — SELECT (`row_limiting_clause`)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `OFFSET`, `FETCH FIRST/NEXT`, `ONLY`, `WITH TIES`, deterministic ordering và restrictions với `FOR UPDATE`/sequence/select list.
3. [Oracle Database 19c SQL Language Reference — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): analytic numbering, `OVER (ORDER BY...)` và ví dụ Top-N theo department.
4. [Oracle Database 19c SQL Language Reference — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): xếp hạng có khoảng trống sau ties.
5. [Oracle Database 19c SQL Language Reference — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): xếp hạng liên tục cho các nhóm giá trị bằng nhau.
6. [Oracle Database 19c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): vị trí thực thi logic của analytic functions và phạm vi `PARTITION BY`.
7. [Oracle Database 19c SQL Language Reference — Using Subqueries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Using-Subqueries.html): inline view và lồng query blocks.
8. [Oracle Database 19c Data Warehousing Guide — Limiting SQL Rows](https://docs.oracle.com/en/database/oracle/oracle-database/19/dwhsg/): các mẫu Top-N, offset pagination và các kiểu ranking trong phân tích.

**Cách nhớ ngắn:** `ROWNUM` ở cùng query block với `ORDER BY` có thể **chọn dòng trước, sort sau**; để lấy Top-N đúng, dùng **inline view có ORDER BY + outer ROWNUM**, hoặc **ORDER BY ... FETCH FIRST N ROWS ONLY** trên Oracle 12c+. Khi cần **đánh số theo thứ tự hoặc theo từng nhóm**, dùng **ROW_NUMBER() OVER (...)**. Trong mọi trường hợp, hãy xác định **N dòng thuộc tập nào, thứ tự có đủ duy nhất không, tie policy là gì và dữ liệu có thay đổi giữa các lần phân trang không**.
