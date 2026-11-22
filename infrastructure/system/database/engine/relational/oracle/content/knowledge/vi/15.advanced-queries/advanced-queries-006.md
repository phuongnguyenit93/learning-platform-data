# Top-N toàn cục và Top-N trong từng nhóm trong Oracle Database

Trong các hệ thống báo cáo và ứng dụng nghiệp vụ, rất thường gặp yêu cầu lấy **N bản ghi đứng đầu**: 10 đơn hàng có giá trị lớn nhất, 20 sản phẩm bán chạy nhất, 5 nhân viên có doanh số cao nhất trong từng phòng ban, hoặc 3 giao dịch gần nhất của mỗi tài khoản. Nhóm yêu cầu này được gọi là **Top-N query**.

Trong Oracle Database, có nhiều cách triển khai Top-N:

- **Top-N toàn cục (global Top-N):** xếp hạng toàn bộ tập kết quả rồi lấy N hàng đầu.
- **Top-N trong từng nhóm (Top-N per group):** chia dữ liệu thành các nhóm, xếp hạng riêng trong mỗi nhóm rồi lấy N hàng đầu của từng nhóm.
- **Top-N có đồng hạng (ties):** quyết định có lấy thêm các hàng bằng điểm với hàng cuối cùng hay không.
- **Top-N trên dữ liệu tổng hợp:** tính `SUM`, `COUNT`, `AVG` theo nhóm trước, sau đó mới xếp hạng các nhóm hoặc sản phẩm.

Điểm quan trọng nhất là phải xác định rõ **N hàng chính xác hay N mức giá trị xếp hạng**, **cách xử lý tie**, **thứ tự sắp xếp có ổn định hay không**, và **phiên bản Oracle hỗ trợ cú pháp nào**. Một câu SQL có thể chạy đúng cú pháp nhưng vẫn trả kết quả sai yêu cầu nếu dùng `ROW_NUMBER` thay cho `RANK`, hoặc đặt `ROWNUM` sai vị trí so với `ORDER BY`.

## 1. Top-N là gì?

Giả sử bảng đơn hàng có các cột `ORDER_ID`, `CUSTOMER_ID`, `AMOUNT`, `CREATED_AT`. Yêu cầu “lấy 5 đơn hàng có giá trị cao nhất” là Top-N toàn cục:

```sql
SELECT order_id, customer_id, amount
FROM orders
ORDER BY amount DESC, order_id
FETCH FIRST 5 ROWS ONLY;
```

Yêu cầu “lấy 5 đơn hàng có giá trị cao nhất **cho mỗi khách hàng**” là Top-N trong từng nhóm:

```sql
SELECT order_id, customer_id, amount
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY amount DESC, order_id
           ) AS rn
    FROM orders o
)
WHERE rn <= 5
ORDER BY customer_id, rn;
```

Hai câu truy vấn khác nhau ở phạm vi xếp hạng:

```text
GLOBAL TOP-N
Tất cả hàng -----------------> Sắp xếp chung ------> Lấy N hàng

TOP-N PER GROUP
Tất cả hàng --> Chia nhóm --> Xếp hạng từng nhóm --> Lấy N/nhóm
```

Nếu có 10 phòng ban, Top-3 toàn cục trả tối đa 3 hàng cho toàn công ty; Top-3 theo phòng ban có thể trả tối đa 30 hàng. Đừng nhầm hai yêu cầu chỉ vì đều chứa cụm từ “Top 3”.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng bảng giả `LAB_EMP_SALES`, gồm nhân viên, phòng ban, doanh số, ngày giao dịch và trạng thái. Dữ liệu cố ý có **doanh số bằng nhau**, nhiều hàng trong mỗi phòng ban và một số giá trị `NULL` để minh họa tie và cách xử lý dữ liệu thiếu.

Chỉ tạo bảng trong schema **DEV/TEST** được cấp quyền `CREATE TABLE` và quota. Trước khi chạy DDL, xác nhận đúng service, PDB và user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Tạo bảng lab

```sql
CREATE TABLE lab_emp_sales (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    sales_amount  NUMBER(12, 2),
    sold_at       DATE NOT NULL,
    status        VARCHAR2(20 CHAR) NOT NULL
);
```

`SALES_AMOUNT` cho phép `NULL` để có thể thảo luận cách xếp hạng dữ liệu chưa có doanh số. Trong hệ thống thật, cần xác định `NULL` nghĩa là chưa đo được, không có doanh số hay không áp dụng; không tự đổi thành 0 nếu chưa có quy tắc nghiệp vụ.

### 2.2. Nạp dữ liệu giả

```sql
INSERT ALL
    INTO lab_emp_sales VALUES (1,  'An',     10, 9500, DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (2,  'Binh',   10, 9000, DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (3,  'Chi',    10, 9000, DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (4,  'Dung',   10, 7000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (5,  'Em',     10, NULL, DATE '2026-11-05', 'PENDING')
    INTO lab_emp_sales VALUES (6,  'Giang',  20, 12000,DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (7,  'Ha',     20, 11000,DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (8,  'Khanh',  20, 11000,DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (9,  'Lan',    20, 8000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (10, 'Minh',   30, 6000, DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (11, 'Nhi',    30, 5000, DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (12, 'Oanh',   30, 5000, DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (13, 'Phuc',   30, 3000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (14, 'Quynh',  30, NULL, DATE '2026-11-05', 'PENDING')
SELECT 1 FROM dual;

COMMIT;
```

Dữ liệu có ba phòng ban: `10`, `20`, `30`. Phòng ban 10 có hai nhân viên cùng doanh số 9000; phòng ban 20 có hai nhân viên cùng doanh số 11000; phòng ban 30 có hai nhân viên cùng doanh số 5000. Hai nhân viên đang chờ có doanh số `NULL`.

### 2.3. Xem dữ liệu nguồn

```sql
SELECT employee_id, employee_name, department_id,
       sales_amount, sold_at, status
FROM lab_emp_sales
ORDER BY department_id, sales_amount DESC NULLS LAST, employee_id;
```

Đây là thứ tự hiển thị có chủ đích để quan sát bảng. Nó không thay đổi dữ liệu và không tạo một thứ tự cố định cho các truy vấn khác nếu các truy vấn đó không có `ORDER BY` riêng.

## 3. Top-N toàn cục bằng ORDER BY và FETCH FIRST

Với Oracle Database **12c Release 1 trở lên**, row limiting clause cho phép viết Top-N trực tiếp bằng `FETCH FIRST` hoặc `FETCH NEXT`.

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

Truy vấn:

1. Lọc các nhân viên `ACTIVE`.
2. Sắp xếp doanh số giảm dần.
3. Dùng `EMPLOYEE_ID` làm tiêu chí phụ để thứ tự ổn định khi doanh số bằng nhau.
4. Lấy 5 hàng đầu của toàn bộ tập kết quả.

Kết quả theo dữ liệu lab là các nhân viên có ID `6`, `7`, `8`, `1`, `2` (với tie 11000 được phân định bởi ID 7 trước ID 8; tie 9000 được phân định bởi ID 2 trước ID 3). Chỉ có **5 hàng toàn cục**, không phải 5 hàng trong mỗi phòng ban.

### 3.1. FETCH FIRST và FETCH NEXT

Hai cách viết sau có cùng mục đích khi không có `OFFSET`:

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC, employee_id
FETCH NEXT 5 ROWS ONLY;
```

`FIRST` và `NEXT` là hai từ khóa được dùng trong row limiting clause; khi có offset, `NEXT` thường dễ đọc theo nghĩa “lấy tiếp N hàng sau phần đã bỏ qua”.

### 3.2. OFFSET để phân trang

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;
```

Truy vấn bỏ qua 5 hàng đầu rồi lấy 5 hàng tiếp theo. `OFFSET` và `FETCH` hoạt động trên **kết quả đã được sắp xếp**. Nếu thiếu `ORDER BY`, các hàng bị bỏ qua và các hàng được lấy không có thứ tự ổn định.

### 3.3. TOP-N với tỷ lệ phần trăm

Oracle hỗ trợ dạng row limiting theo phần trăm ở các phiên bản có row limiting clause:

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 25 PERCENT ROWS ONLY;
```

`PERCENT` lấy một tỷ lệ của số hàng đủ điều kiện trong kết quả. Số hàng thực tế phụ thuộc quy tắc làm tròn của row limiting clause và tổng số hàng sau lọc; không nên thay thế bằng phép tính ước lượng ở ứng dụng nếu cần đúng ngữ nghĩa Oracle.

## 4. Top-N toàn cục có đồng hạng: WITH TIES

Yêu cầu “lấy 5 nhân viên có doanh số cao nhất, **bao gồm tất cả người đồng hạng với vị trí thứ 5**” khác với yêu cầu “lấy đúng 5 hàng”. Oracle hỗ trợ:

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

`WITH TIES` yêu cầu `ORDER BY`. Oracle lấy ít nhất 5 hàng và bổ sung các hàng tiếp theo có cùng giá trị sort key với hàng cuối cùng. Với dữ liệu lab, các vị trí đầu là:

| Thứ hạng theo doanh số | Nhân viên | Doanh số |
|---:|---|---:|
| 1 | Giang | 12000 |
| 2 | Ha | 11000 |
| 2 | Khanh | 11000 |
| 4 | An | 9500 |
| 5 | Binh | 9000 |
| 5 | Chi | 9000 |

Kết quả `WITH TIES` có **6 hàng**, vì cả Binh và Chi đồng hạng ở mức doanh số của hàng thứ 5.

### 4.1. Không thêm khóa phụ nếu muốn tie theo doanh số

So sánh:

```sql
-- Bao gồm mọi người bằng doanh số với hàng thứ 5.
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

với:

```sql
-- Nếu employee_id duy nhất, không còn hàng nào tie theo toàn bộ sort key.
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS WITH TIES;
```

`WITH TIES` xét **toàn bộ các biểu thức trong `ORDER BY`**. Nếu thêm `EMPLOYEE_ID` duy nhất vào sort key, hai người có cùng doanh số nhưng ID khác nhau không còn được coi là tie. Vì vậy:

- Muốn lấy đúng N hàng ổn định: thêm khóa duy nhất làm tiêu chí phụ và dùng `ONLY`.
- Muốn lấy tất cả hàng đồng hạng theo doanh số: chỉ xếp theo `SALES_AMOUNT` trong truy vấn `WITH TIES`.
- Nếu cần thứ tự trình bày ổn định trong nhóm đồng hạng, bọc truy vấn Top-N có ties rồi sắp xếp bên ngoài theo `SALES_AMOUNT DESC, EMPLOYEE_ID`.

Ví dụ:

```sql
SELECT employee_id, employee_name, sales_amount
FROM (
    SELECT employee_id, employee_name, sales_amount
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
    ORDER BY sales_amount DESC
    FETCH FIRST 5 ROWS WITH TIES
)
ORDER BY sales_amount DESC, employee_id;
```

### 4.2. WITH TIES khác RANK và DENSE_RANK

`WITH TIES` trong row limiting clause là cách thuận tiện cho Top-N toàn cục theo sort key. Với Top-N từng nhóm, analytic ranking thường phù hợp hơn vì mỗi partition cần một giới hạn riêng. Phần sau giải thích rõ `ROW_NUMBER`, `RANK` và `DENSE_RANK`.

## 5. Top-N toàn cục bằng ROWNUM trên Oracle phiên bản cũ

Trước Oracle 12c, cách phổ biến để lấy Top-N toàn cục là **sắp xếp trong inline view rồi lọc `ROWNUM` ở query bên ngoài**.

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM (
    SELECT employee_id, employee_name, department_id, sales_amount
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
    ORDER BY sales_amount DESC, employee_id
)
WHERE ROWNUM <= 5;
```

Đây là mẫu Top-N cổ điển. `ORDER BY` ở query trong tạo thứ tự cần xếp hạng; query ngoài mới giới hạn `ROWNUM`.

### 5.1. Vì sao không viết ROWNUM và ORDER BY cùng cấp?

Không nên viết:

```sql
-- Sai ý nghĩa Top-N: ROWNUM được gán trước khi ORDER BY của query block hoàn tất.
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
  AND ROWNUM <= 5
ORDER BY sales_amount DESC;
```

Trong cùng query block, Oracle gán `ROWNUM` khi chọn hàng; `ORDER BY` sau đó sắp xếp các hàng đã được chọn. Câu trên có thể lấy 5 hàng theo đường truy cập rồi sắp xếp 5 hàng đó, **không bảo đảm lấy 5 doanh số cao nhất toàn bảng**.

Đặt truy vấn sắp xếp vào inline view giúp Oracle thực hiện logic Top-N đúng:

```text
Inline view:
    FROM -> WHERE -> ORDER BY
                |
                v
        Tập đã sắp xếp theo doanh số
                |
                v
Query ngoài:
    WHERE ROWNUM <= 5
                |
                v
             Top 5
```

### 5.2. ROWNUM > 1 không hoạt động như nhiều người nghĩ

`ROWNUM` được gán tuần tự cho hàng được chọn trong query block. Điều kiện:

```sql
WHERE ROWNUM > 1
```

ở một query block đơn giản thường không trả hàng nào: hàng đầu tiên được xét nhận `ROWNUM = 1` và bị loại; vì hàng đó không được trả ra nên hàng tiếp theo vẫn được xét như hàng đầu tiên với `ROWNUM = 1`, tiếp tục bị loại. Đây là lý do không thể dùng trực tiếp `ROWNUM > :offset` cho phân trang.

### 5.3. Phân trang kiểu ROWNUM

Với Oracle cũ chưa hỗ trợ `OFFSET ... FETCH`, có thể dùng hai tầng inline view:

```sql
SELECT employee_id, employee_name, sales_amount
FROM (
    SELECT ordered_rows.*,
           ROWNUM AS rn
    FROM (
        SELECT employee_id, employee_name, sales_amount
        FROM lab_emp_sales
        WHERE status = 'ACTIVE'
        ORDER BY sales_amount DESC, employee_id
    ) ordered_rows
    WHERE ROWNUM <= :offset_value + :page_size
)
WHERE rn > :offset_value
ORDER BY sales_amount DESC, employee_id;
```

Query trong cùng sắp xếp dữ liệu; tầng giữa giới hạn đến hàng cuối của trang; tầng ngoài loại các hàng trước offset. Bind `:offset_value` và `:page_size` phải được kiểm tra là số không âm, và `page_size` phải có giới hạn phù hợp để tránh truy vấn trả quá nhiều dữ liệu.

## 6. Top-N trong từng nhóm bằng ROW_NUMBER

Đây là yêu cầu phổ biến nhất của Top-N per group. Oracle analytic function cho phép chia dữ liệu thành các partition và đánh số hàng bên trong từng partition.

```sql
SELECT employee_id, employee_name, department_id, sales_amount, rn
FROM (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
WHERE rn <= 2
ORDER BY department_id, rn;
```

Giải thích:

- `PARTITION BY department_id`: chia dữ liệu thành các nhóm phòng ban. Mỗi phòng ban bắt đầu đánh số lại từ 1.
- `ORDER BY sales_amount DESC NULLS LAST, employee_id`: doanh số lớn hơn đứng trước; null đứng cuối; ID dùng để phân định tie.
- `ROW_NUMBER()`: gán một số thứ tự duy nhất cho từng hàng trong partition.
- Query ngoài `WHERE rn <= 2`: giữ hai hàng đầu trong mỗi phòng ban.
- `ORDER BY department_id, rn` ở ngoài: sắp kết quả cuối để dễ đọc.

Kết quả theo dữ liệu lab:

| Phòng ban | `RN` | Nhân viên | Doanh số |
|---:|---:|---|---:|
| 10 | 1 | An | 9500 |
| 10 | 2 | Binh | 9000 |
| 20 | 1 | Giang | 12000 |
| 20 | 2 | Ha | 11000 |
| 30 | 1 | Minh | 6000 |
| 30 | 2 | Nhi | 5000 |

Mỗi phòng ban có tối đa 2 hàng, tổng cộng 6 hàng. Vì `ROW_NUMBER` cần một thứ tự xác định nếu muốn kết quả lặp lại, hãy đưa một cột duy nhất như `EMPLOYEE_ID` vào cuối `ORDER BY` khi tie cần được phân định.

### 6.1. Vì sao cần query ngoài để lọc rn?

Trong Oracle, analytic functions được tính sau các bước `FROM`, `WHERE`, `GROUP BY` và `HAVING` của cùng query block. Vì vậy không thể lọc trực tiếp alias analytic trong `WHERE` cùng cấp:

```sql
-- Không hợp lệ trong cùng query block:
SELECT employee_id,
       ROW_NUMBER() OVER (ORDER BY sales_amount DESC) AS rn
FROM lab_emp_sales
WHERE rn <= 5;
```

Alias `RN` chưa có tại giai đoạn `WHERE`; cách này thường gây `ORA-00904` hoặc lỗi tham chiếu alias. Bọc trong inline view/CTE để lọc ở query block bên ngoài:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id, sales_amount, rn
FROM ranked_sales
WHERE rn <= 2
ORDER BY department_id, rn;
```

CTE giúp đặt tên bước “xếp hạng” và làm truy vấn dài dễ đọc hơn.

## 7. Top-N per group có ties: RANK và DENSE_RANK

`ROW_NUMBER` luôn gán số duy nhất cho từng hàng, kể cả khi hai hàng có cùng doanh số. Nhưng nghiệp vụ đôi khi yêu cầu **giữ tất cả nhân viên đồng hạng**, thay vì tùy tiện chọn một người ở ranh giới Top-N. Khi đó cần hiểu hai analytic function:

- `RANK()`: các hàng đồng hạng có cùng rank; vị trí kế tiếp bị nhảy.
- `DENSE_RANK()`: các hàng đồng hạng có cùng rank; vị trí kế tiếp tăng liên tục, không có khoảng trống.

### 7.1. Bảng minh họa ba loại ranking

Giả sử doanh số giảm dần:

| Nhân viên | Doanh số | `ROW_NUMBER` | `RANK` | `DENSE_RANK` |
|---|---:|---:|---:|---:|
| A | 100 | 1 | 1 | 1 |
| B | 95 | 2 | 2 | 2 |
| C | 95 | 3 | 2 | 2 |
| D | 90 | 4 | 4 | 3 |
| E | 80 | 5 | 5 | 4 |

Với cùng giá trị 95:

- `ROW_NUMBER` gán 2 và 3 (thứ tự giữa B/C không xác định nếu thiếu tie-breaker).
- `RANK` gán cả hai bằng 2, sau đó rank tiếp theo là 4.
- `DENSE_RANK` gán cả hai bằng 2, sau đó rank tiếp theo là 3.

### 7.2. RANK <= N: Top-N vị trí có xét đồng hạng

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 2
ORDER BY department_id, sales_rank, employee_id;
```

Ở mỗi phòng ban, tất cả người đồng hạng với vị trí thứ 2 được giữ. Phòng 10 giữ An, Binh và Chi (rank 1, 2, 2); phòng 20 giữ Giang, Ha và Khanh (rank 1, 2, 2); phòng 30 giữ Minh, Nhi và Oanh (rank 1, 2, 2). Tổng cộng 9 hàng, nhiều hơn `ROW_NUMBER <= 2`.

**Không đưa `EMPLOYEE_ID` vào `ORDER BY` bên trong `RANK` nếu muốn tie theo doanh số**, vì ID khác nhau sẽ phá tie. Có thể dùng ID ở `ORDER BY` ngoài để sắp xếp các hàng cùng hạng mà không ảnh hưởng rank đã tính.

### 7.3. DENSE_RANK <= N: N mức doanh số khác nhau

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_dense_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_dense_rank
FROM ranked_sales
WHERE sales_dense_rank <= 2
ORDER BY department_id, sales_dense_rank, employee_id;
```

Với dữ liệu lab, kết quả giống `RANK <= 2` vì các tie nằm ở mức thứ hai. Nhưng trong ví dụ A=100, B/C=95, D=90:

- `RANK <= 3` giữ A, B, C; D có rank 4 nên bị loại.
- `DENSE_RANK <= 3` giữ A, B, C, D vì đó là ba mức doanh số khác nhau.

Do đó, phải chọn function dựa trên cách nghiệp vụ định nghĩa “Top N”.

### 7.4. So sánh nhanh ROW_NUMBER, RANK, DENSE_RANK

| Hàm | Giá trị tie | Khoảng rank | Số hàng khi lọc `<= N` | Câu hỏi nghiệp vụ |
|---|---|---|---|---|
| `ROW_NUMBER` | Mỗi hàng có số riêng | Không có khoảng trống | Tối đa N hàng mỗi nhóm | Chọn đúng N bản ghi |
| `RANK` | Cùng giá trị rank | Có khoảng trống sau tie | Có thể hơn N hàng | Lấy các hàng nằm trong N vị trí đầu, gồm đồng hạng |
| `DENSE_RANK` | Cùng giá trị rank | Không có khoảng trống | Có thể hơn N hàng | Lấy N mức giá trị/xếp hạng khác nhau đầu tiên |

## 8. NULL trong Top-N và thứ tự NULLS FIRST/LAST

Nếu cột xếp hạng có thể `NULL`, phải xác định null được coi là thấp nhất, cao nhất hay cần loại khỏi tập xếp hạng.

Oracle có mặc định:

- `ORDER BY value ASC`: `NULLS LAST`.
- `ORDER BY value DESC`: `NULLS FIRST`.

Vì vậy, câu:

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS ONLY;
```

có thể đưa các hàng doanh số `NULL` lên đầu theo mặc định của Oracle khi sắp xếp giảm dần. Nếu `NULL` nghĩa là “chưa có số liệu” và không nên đứng Top-N, hãy ghi rõ:

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

Hoặc loại null trước:

```sql
WHERE status = 'ACTIVE'
  AND sales_amount IS NOT NULL
```

Hai cách khác nhau nếu Top-N cần giữ hàng null ở cuối khi N đủ lớn. Chọn theo nghiệp vụ.

### 8.1. NULL trong analytic ranking

Với Top-N per group, cũng cần ghi rõ:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY sales_amount DESC NULLS LAST, employee_id
)
```

Nếu bỏ `NULLS LAST`, các hàng doanh số null có thể được xếp trước trong `DESC` và lọt vào Top-N. Nếu loại null bằng `WHERE sales_amount IS NOT NULL` trong query trong, các hàng đó không được xếp hạng; nếu chỉ đặt `NULLS LAST`, chúng vẫn được xếp nhưng ở cuối partition.

## 9. Top-N per group sau khi tổng hợp dữ liệu

Một yêu cầu thực tế hơn: “Lấy 3 sản phẩm có doanh thu cao nhất trong từng khu vực”. Bảng giao dịch có thể chứa nhiều hàng cho cùng sản phẩm. Cần **tổng hợp trước**, rồi mới xếp hạng sản phẩm trong mỗi khu vực.

```sql
WITH product_totals AS (
    SELECT region_id,
           product_id,
           SUM(quantity * unit_price) AS revenue
    FROM sales_transactions
    WHERE transaction_status = 'COMPLETED'
    GROUP BY region_id, product_id
), ranked_products AS (
    SELECT region_id,
           product_id,
           revenue,
           ROW_NUMBER() OVER (
               PARTITION BY region_id
               ORDER BY revenue DESC, product_id
           ) AS rn
    FROM product_totals
)
SELECT region_id, product_id, revenue, rn
FROM ranked_products
WHERE rn <= 3
ORDER BY region_id, rn;
```

Trình tự logic:

1. `WHERE` loại giao dịch không hoàn thành.
2. `GROUP BY region_id, product_id` tạo doanh thu từng sản phẩm trong từng vùng.
3. `SUM` tính tổng doanh thu.
4. `ROW_NUMBER` xếp hạng sản phẩm riêng trong từng vùng.
5. Query ngoài lọc ba sản phẩm đầu mỗi vùng.

Nếu xếp hạng từng giao dịch trước khi `GROUP BY`, kết quả không còn trả lời đúng câu hỏi “sản phẩm có tổng doanh thu cao nhất”. Hãy xác định **đơn vị được xếp hạng** là giao dịch, sản phẩm, nhân viên hay nhóm tổng hợp.

### 9.1. Top-N nhóm toàn cục sau GROUP BY

Nếu cần 10 khách hàng chi tiêu nhiều nhất toàn hệ thống:

```sql
SELECT customer_id,
       SUM(order_amount) AS total_spend
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
ORDER BY total_spend DESC, customer_id
FETCH FIRST 10 ROWS ONLY;
```

Đây là Top-N toàn cục trên **các nhóm khách hàng sau aggregate**, không phải 10 đơn hàng có giá trị cao nhất. `FETCH FIRST` áp dụng sau khi các nhóm đã được tạo và sắp xếp.

### 9.2. Top-N nhóm có tie theo tổng doanh thu

```sql
SELECT customer_id,
       SUM(order_amount) AS total_spend
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
ORDER BY total_spend DESC
FETCH FIRST 10 ROWS WITH TIES;
```

Truy vấn giữ tất cả khách hàng đồng hạng với vị trí thứ 10 theo `TOTAL_SPEND`. Nếu thêm `CUSTOMER_ID` duy nhất vào `ORDER BY`, tie theo toàn bộ sort key sẽ biến mất; chỉ thêm khóa phụ nếu yêu cầu là đúng 10 nhóm có thứ tự xác định.

## 10. Top-N trong từng nhóm với nhiều tiêu chí xếp hạng

Top-N có thể cần tiêu chí phụ: doanh số cao trước, nếu bằng nhau thì đơn gần đây trước, nếu vẫn bằng thì ID nhỏ trước.

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           sold_at,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST,
                        sold_at DESC,
                        employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sold_at, rn
FROM ranked_sales
WHERE rn <= 3
ORDER BY department_id, rn;
```

Thứ tự trong `OVER (...)` quyết định **cách xếp hạng**; `ORDER BY` cuối quyết định **cách trình bày kết quả**. Hai danh sách có thể khác nhau và phục vụ hai mục đích khác nhau.

### 10.1. Tie chỉ dựa trên một metric

Nếu yêu cầu đồng hạng chỉ dựa trên doanh số, nhưng kết quả cần sắp xếp ổn định, hãy tách rank và sort:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 3
ORDER BY department_id, sales_rank, employee_id;
```

`EMPLOYEE_ID` chỉ xuất hiện ở `ORDER BY` ngoài nên không phá tie trong rank. Đây là mẫu dễ tái sử dụng khi báo cáo cần đồng hạng nhưng thứ tự hiển thị phải ổn định.

## 11. ROW_NUMBER, RANK và DENSE_RANK với Top-N toàn cục

Ba analytic function không chỉ dùng cho Top-N từng nhóm; có thể dùng cho toàn bộ bảng bằng cách bỏ `PARTITION BY`.

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id, sales_amount
FROM ranked_sales
WHERE rn <= 5
ORDER BY rn;
```

Đây là cách viết Top-5 toàn cục bằng analytic function. So với `FETCH FIRST`, nó dài hơn nhưng hữu ích khi cần giữ thêm rank, join với dữ liệu khác hoặc áp dụng nhiều bộ lọc sau xếp hạng.

Với tie:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           sales_amount,
           RANK() OVER (
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 5
ORDER BY sales_rank, employee_id;
```

Mẫu này tương tự ý nghĩa “Top 5 vị trí có ties” toàn cục. Với query chỉ cần một giới hạn đơn giản, `FETCH FIRST ... WITH TIES` ngắn gọn hơn.

## 12. Top-N per group và danh sách nhóm không có dữ liệu

Một điểm cần chú ý: nếu truy vấn xếp hạng bắt đầu từ bảng fact như `LAB_EMP_SALES`, những phòng ban **không có hàng nào** sẽ không xuất hiện trong kết quả. Nếu báo cáo phải hiển thị mọi phòng ban, kể cả nhóm không có nhân viên/doanh số, cần bắt đầu từ bảng danh mục phòng ban rồi `LEFT JOIN` với tập Top-N.

Ví dụ khái niệm:

```sql
WITH ranked_employees AS (
    SELECT employee_id,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT d.department_id,
       d.department_name,
       r.employee_id,
       r.sales_amount,
       r.rn
FROM departments d
LEFT JOIN ranked_employees r
  ON r.department_id = d.department_id
 AND r.rn <= 3
ORDER BY d.department_id, r.rn;
```

Đặt `r.rn <= 3` trong `ON` giữ phòng ban không có nhân viên xếp hạng; nếu đặt ở `WHERE`, các hàng null phía phải bị loại và `LEFT JOIN` có thể hoạt động như inner join. `DEPARTMENTS`/`EMPLOYEES` là tên bảng nghiệp vụ giả định.

## 13. Top-N per group bằng LATERAL/CROSS APPLY (khi phù hợp)

Trong các phiên bản Oracle hỗ trợ `CROSS APPLY`/`OUTER APPLY` và row limiting clause, có thể lấy Top-N riêng cho từng hàng cha bằng một truy vấn tương quan:

```sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name,
       e.sales_amount
FROM departments d
CROSS APPLY (
    SELECT employee_id, employee_name, sales_amount
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
    ORDER BY e.sales_amount DESC NULLS LAST, e.employee_id
    FETCH FIRST 3 ROWS ONLY
) e
ORDER BY d.department_id, e.sales_amount DESC, e.employee_id;
```

`CROSS APPLY` chạy truy vấn bên phải theo từng hàng phòng ban và chỉ giữ phòng ban có ít nhất một hàng phù hợp. Nếu muốn giữ cả phòng ban không có nhân viên, dùng `OUTER APPLY` theo khả năng hỗ trợ của phiên bản. Đây là một cách viết khác, nhưng **analytic `ROW_NUMBER` thường tổng quát và dễ dùng cho nhiều nhóm**. Hãy chọn theo phiên bản, optimizer plan và độ phức tạp truy vấn.

## 14. Top-N theo thời gian: bản ghi mới nhất trong từng nhóm

Một dạng Top-N rất phổ biến là lấy 1 hoặc N bản ghi gần nhất cho mỗi tài khoản, thiết bị, đơn hàng hoặc khách hàng.

```sql
WITH ranked_events AS (
    SELECT event_id,
           account_id,
           event_type,
           occurred_at,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY occurred_at DESC, event_id DESC
           ) AS rn
    FROM account_events
)
SELECT event_id, account_id, event_type, occurred_at
FROM ranked_events
WHERE rn <= 3
ORDER BY account_id, occurred_at DESC, event_id DESC;
```

Mỗi tài khoản lấy tối đa ba sự kiện mới nhất. `EVENT_ID` là tiêu chí phụ giúp kết quả ổn định khi nhiều sự kiện có cùng timestamp. Nếu nghiệp vụ muốn giữ **mọi sự kiện đồng thời tại thời điểm thứ ba**, hãy dùng `RANK` trên `OCCURRED_AT` và chỉ dùng `EVENT_ID` để sắp xếp ngoài.

### 14.1. Lấy bản ghi mới nhất duy nhất mỗi nhóm

Mẫu `ROW_NUMBER() = 1` thường dùng để chọn bản ghi mới nhất:

```sql
WITH latest_event AS (
    SELECT event_id,
           account_id,
           event_type,
           occurred_at,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY occurred_at DESC, event_id DESC
           ) AS rn
    FROM account_events
)
SELECT event_id, account_id, event_type, occurred_at
FROM latest_event
WHERE rn = 1;
```

Nếu `OCCURRED_AT` có thể `NULL`, hãy định nghĩa null đứng đầu hay cuối. Với yêu cầu “mới nhất” thông thường, `NULLS LAST` là lựa chọn rõ ràng nếu null nghĩa là thiếu thời gian:

```sql
ORDER BY occurred_at DESC NULLS LAST, event_id DESC
```

## 15. Top-N trong từng nhóm với điều kiện lọc: lọc trước hay sau ranking?

Vị trí của `WHERE` ảnh hưởng trực tiếp đến tập dữ liệu được xếp hạng. Ví dụ cần lấy 3 nhân viên `ACTIVE` có doanh số cao nhất mỗi phòng ban:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales e
    WHERE status = 'ACTIVE'
)
SELECT employee_id, department_id, sales_amount
FROM ranked
WHERE rn <= 3;
```

`WHERE status = 'ACTIVE'` ở bên trong chạy trước analytic function; chỉ nhân viên active được xếp hạng. Nếu chuyển điều kiện status ra ngoài:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales e
)
SELECT employee_id, department_id, sales_amount
FROM ranked
WHERE rn <= 3
  AND status = 'ACTIVE';
```

thì nhân viên `PENDING` cũng tham gia xếp hạng trước; sau đó mới bị loại. Kết quả có thể chỉ còn 2 nhân viên active ở một phòng ban, dù phía dưới còn người active đủ điều kiện. Hai truy vấn trả lời **hai câu hỏi khác nhau**:

- Top-3 trong tập nhân viên active.
- Top-3 trong toàn bộ nhân viên, sau đó chỉ hiển thị những người active.

Khi viết Top-N, hãy xác định rõ bộ lọc nào giới hạn **tập ứng viên được xếp hạng**, bộ lọc nào chỉ giới hạn **kết quả hiển thị**.

## 16. Tối ưu hiệu năng Top-N

Top-N không chỉ là cú pháp; trên bảng lớn, cách tổ chức truy vấn và index có thể ảnh hưởng đáng kể thời gian thực thi.

### 16.1. Index theo cột lọc và thứ tự xếp hạng

Với truy vấn:

```sql
SELECT employee_id, department_id, sales_amount
FROM lab_emp_sales
WHERE department_id = :department_id
  AND status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

có thể đánh giá index bắt đầu bằng các cột lọc và tiếp theo là các cột xếp hạng, ví dụ:

```sql
CREATE INDEX ix_lab_sales_dept_status_top
ON lab_emp_sales (
    department_id,
    status,
    sales_amount DESC,
    employee_id
);
```

Đây chỉ là **ứng viên index để đo**, không phải khuyến nghị tạo tự động cho mọi bảng. Hiệu quả phụ thuộc selectivity của `DEPARTMENT_ID`/`STATUS`, kích thước bảng, phân bố doanh số, số cột cần trả về, DML và optimizer statistics. Với query Top-N toàn cục không lọc department, index bắt đầu bằng department có thể không phù hợp.

### 16.2. Top-N per group khó hơn Top-N toàn cục

Global Top-N có thể dừng sau khi tìm đủ N hàng theo một đường truy cập phù hợp. Top-N per group cần tìm đủ hàng đầu cho **mỗi partition**; nếu có nhiều nhóm hoặc dữ liệu phân tán, Oracle có thể phải xử lý và xếp hạng nhiều hàng hơn. Analytic function thường là cách diễn đạt rõ nhất, nhưng execution plan có thể bao gồm sort/window operation và dùng TEMP khi dữ liệu lớn.

### 16.3. Không thêm cột vào ORDER BY nếu không cần

Thêm tiêu chí phụ duy nhất làm kết quả `ROW_NUMBER` ổn định, nhưng có thể thay đổi cách tie được định nghĩa trong `RANK` hoặc `WITH TIES`. Phải tách hai mục tiêu:

- **Tie semantics:** cột nào xác định hai hàng đồng hạng?
- **Display determinism:** cần thêm cột nào để sắp xếp ổn định khi hiển thị?

Với `RANK`, chỉ đưa metric nghiệp vụ vào `ORDER BY` trong analytic clause; thêm khóa phụ ở `ORDER BY` ngoài.

### 16.4. Chọn đúng số cột

Tránh `SELECT *` trong truy vấn Top-N lớn nếu ứng dụng chỉ cần một số cột. Lấy ít cột hơn có thể giảm I/O, băng thông và bộ nhớ sort, đồng thời giúp optimizer có thêm lựa chọn index phù hợp. Tuy nhiên, không tạo covering index quá rộng chỉ để tránh table access nếu chi phí DML/storage không xứng đáng.

### 16.5. Đọc execution plan

Khi truy vấn chậm, kiểm tra:

- Có predicate nào lọc sớm được không?
- `ORDER BY` có cần sort toàn bộ dữ liệu hay có index phù hợp?
- Analytic window có partition/sort quá lớn không?
- Ước lượng cardinality có lệch do statistics không?
- TEMP/PGA, parallelism và số hàng đầu ra có hợp lý không?

Đừng ép `INDEX` hint hoặc đổi `ROW_NUMBER` thành `ROWNUM` chỉ vì muốn nhanh hơn khi chưa đo. Tính đúng đắn của Top-N và tính ổn định tie là điều kiện đầu tiên.

## 17. Các lỗi thường gặp

| Triệu chứng/nhận định | Nguyên nhân | Cách xử lý |
|---|---|---|
| Top-5 không phải 5 giá trị lớn nhất | Lọc `ROWNUM <= 5` cùng query block với `ORDER BY` | Đặt `ORDER BY` trong inline view rồi lọc ROWNUM bên ngoài, hoặc dùng FETCH FIRST |
| `ROWNUM > 1` không trả hàng | ROWNUM được gán khi chọn hàng trong query block | Dùng analytic `ROW_NUMBER` hoặc mẫu phân trang hai tầng |
| Top-3 mỗi phòng ban chỉ trả 3 hàng toàn công ty | Dùng FETCH FIRST/ROWNUM toàn cục | Dùng `ROW_NUMBER() OVER (PARTITION BY ...)` rồi lọc ở query ngoài |
| Top-N per group không lọc được alias rn | Analytic alias không có ở WHERE cùng query block | Dùng CTE hoặc inline view |
| Nhân viên đồng doanh số bị mất khỏi kết quả | Dùng ROW_NUMBER và chỉ lấy N hàng | Dùng RANK hoặc DENSE_RANK theo định nghĩa tie |
| Kết quả có nhiều hơn N hàng | `RANK <= N`, `DENSE_RANK <= N` hoặc WITH TIES | Xác định cần đúng N hàng hay bao gồm đồng hạng |
| Hai người cùng điểm không còn tie | Đưa ID duy nhất vào ORDER BY của RANK/WITH TIES | Chỉ dùng metric tie trong ranking; sắp ổn định ở ngoài |
| Hàng NULL lọt vào Top-N DESC | Mặc định DESC có thể đặt NULLS FIRST | Ghi `NULLS LAST` hoặc lọc `IS NOT NULL` |
| Top-N sau GROUP BY sai đơn vị | Xếp hạng giao dịch trước khi tổng hợp | Aggregate trước, analytic ranking sau |
| Top-N per group bỏ nhóm không có hàng | Bắt đầu từ fact table | LEFT JOIN từ danh mục nhóm; đặt điều kiện rank trong ON |
| Trang tiếp theo trùng/thiếu hàng | ORDER BY không duy nhất hoặc dữ liệu thay đổi | Thêm khóa phụ; cân nhắc keyset pagination/snapshot |
| Truy vấn khác kết quả giữa các lần chạy | Tie không có tie-breaker hoặc không có ORDER BY ngoài | Xác định thứ tự đầy đủ và ổn định |
| Dùng cú pháp FETCH FIRST trên release cũ | Database chưa hỗ trợ row limiting clause | Dùng mẫu ROWNUM/analytic phù hợp phiên bản |

## 18. Thực hành có kiểm soát

Các bài tập dưới đây dùng `LAB_EMP_SALES`. Chỉ chạy trên DEV/TEST, đúng schema được cấp quyền. Không chạy DDL hoặc thao tác dọn dẹp trên production.

### Bài 1 — Top-5 toàn cục

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

Xác nhận có 5 hàng và giải thích vai trò của `EMPLOYEE_ID` trong tie.

### Bài 2 — Top-5 có đồng hạng

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

Đếm số hàng. Thêm `EMPLOYEE_ID` vào `ORDER BY` và quan sát vì sao số hàng có thể giảm còn đúng 5.

### Bài 3 — Top-2 mỗi phòng ban

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE rn <= 2
ORDER BY department_id, rn;
```

Kết quả mong đợi: 6 hàng, hai nhân viên mỗi phòng ban.

### Bài 4 — Top-2 có ties mỗi phòng ban

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS rnk
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE rnk <= 2
ORDER BY department_id, rnk, employee_id;
```

Giải thích vì sao kết quả có thể là 9 hàng dù yêu cầu chứa số 2.

### Bài 5 — Top-2 mức doanh số khác nhau

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS drnk
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE drnk <= 2
ORDER BY department_id, drnk, employee_id;
```

Đối chiếu với `RANK <= 2`. Tạo một tập dữ liệu có tie ở vị trí thứ ba để thấy sự khác biệt của rank có khoảng trống và dense rank.

### Bài 6 — Top-3 sau khi tổng hợp

Từ bảng giao dịch giả định, viết CTE tính `SUM(quantity * unit_price)` theo `region_id, product_id`, rồi dùng `ROW_NUMBER` với `PARTITION BY region_id` để lấy ba sản phẩm đầu mỗi vùng. Xác định rõ filter giao dịch nào được chạy trước aggregate.

### Bài 7 — Bản ghi mới nhất trong mỗi nhóm

Từ một bảng event giả định, dùng `ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY occurred_at DESC NULLS LAST, event_id DESC)` và lọc `rn = 1`. Giải thích vì sao cần khóa phụ `EVENT_ID`.

### Bài 8 — So sánh lọc trước và sau ranking

Chạy hai truy vấn ở phần 15, một truy vấn lọc `ACTIVE` trước analytic và một truy vấn lọc sau analytic. Đếm số nhân viên còn lại ở mỗi phòng ban và giải thích hai kết quả trả lời hai câu hỏi khác nhau.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng bảng giả do mình tạo trong DEV/TEST và không có người khác sử dụng:

```sql
DROP TABLE lab_emp_sales PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, không đưa vào recycle bin; đây là DDL có implicit commit. Không chạy trên production hoặc bất kỳ bảng nào ngoài phạm vi bài thực hành.

## 19. Câu hỏi ôn tập

**Câu 1.** Top-5 toàn cục khác Top-5 trong từng phòng ban thế nào?

**Đáp án:** Top-5 toàn cục lấy tối đa 5 hàng từ tất cả dữ liệu; Top-5 per group chia partition và lấy tối đa 5 hàng trong mỗi nhóm.

**Câu 2.** Oracle 12c trở lên có thể viết Top-N toàn cục ngắn gọn bằng cú pháp nào?

**Đáp án:** `ORDER BY ... FETCH FIRST N ROWS ONLY`.

**Câu 3.** Vì sao `WHERE ROWNUM <= 5 ORDER BY sales_amount DESC` không phải mẫu Top-5 đúng?

**Đáp án:** ROWNUM được gán trong query block trước khi ORDER BY cuối cùng sắp xếp; cần sắp trong inline view rồi lọc ROWNUM ngoài.

**Câu 4.** Muốn lấy đúng 3 hàng mỗi phòng ban, kể cả có tie thì vẫn chỉ 3 hàng, dùng hàm nào?

**Đáp án:** `ROW_NUMBER()` với tie-breaker xác định trong `ORDER BY` analytic, sau đó lọc `rn <= 3`.

**Câu 5.** Muốn lấy mọi nhân viên có rank thuộc ba vị trí đầu, bao gồm đồng hạng, dùng hàm nào?

**Đáp án:** `RANK()` và lọc `rank <= 3`.

**Câu 6.** Muốn lấy ba mức doanh số khác nhau cao nhất trong từng phòng ban, dùng hàm nào?

**Đáp án:** `DENSE_RANK()` và lọc `dense_rank <= 3`.

**Câu 7.** Vì sao không thêm `EMPLOYEE_ID` vào `ORDER BY` bên trong `RANK()` khi muốn giữ người đồng doanh số?

**Đáp án:** ID duy nhất làm sort key khác nhau, phá tie theo doanh số. Đưa ID vào `ORDER BY` ngoài để sắp ổn định.

**Câu 8.** Trong Oracle, `ORDER BY sales_amount DESC` mặc định đặt NULL ở đâu?

**Đáp án:** `NULLS FIRST`. Nếu NULL nghĩa là chưa có số liệu, thường cần ghi rõ `NULLS LAST` hoặc lọc null.

**Câu 9.** Khi lấy Top-3 sản phẩm theo doanh thu từng vùng từ bảng giao dịch, cần làm gì trước ranking?

**Đáp án:** `GROUP BY` vùng và sản phẩm, tính tổng doanh thu trước; sau đó xếp hạng các sản phẩm đã tổng hợp trong từng vùng.

**Câu 10.** Vì sao cần query ngoài để lọc `ROW_NUMBER`?

**Đáp án:** Analytic function được tính sau WHERE trong query block; alias analytic chưa thể được tham chiếu ở WHERE cùng cấp.

**Câu 11.** `FETCH FIRST 5 ROWS WITH TIES` xét tie theo những cột nào?

**Đáp án:** Toàn bộ sort key trong `ORDER BY`. Thêm một cột unique có thể phá tie.

**Câu 12.** Không có `ORDER BY`, Top-N có bảo đảm trả cùng hàng qua mọi lần chạy không?

**Đáp án:** Không. Không có thứ tự xác định, Oracle không bảo đảm hàng được chọn hay thứ tự hiển thị ổn định.

## Kết luận

**Top-N toàn cục** lấy N hàng đầu của toàn bộ tập dữ liệu; với Oracle 12c trở lên có thể dùng `ORDER BY ... FETCH FIRST N ROWS ONLY`, hoặc `WITH TIES` nếu cần giữ các hàng đồng hạng ở ranh giới. Trên phiên bản cũ, mẫu `ROWNUM` đúng phải sắp xếp trong inline view trước rồi mới lọc ở query ngoài. Không dùng `ROWNUM` cùng cấp với `ORDER BY` để giả định lấy N giá trị lớn nhất.

**Top-N trong từng nhóm** cần analytic function với `PARTITION BY`: `ROW_NUMBER` cho tối đa N hàng mỗi nhóm, `RANK` giữ đồng hạng theo vị trí và có khoảng trống, `DENSE_RANK` lấy N mức giá trị khác nhau. Khi làm báo cáo, phải quyết định rõ cách xử lý tie, NULL, tiêu chí sắp xếp phụ và vị trí của bộ lọc trước/sau ranking. Nếu Top-N dựa trên doanh thu hoặc số lượng tổng hợp, hãy aggregate trước rồi mới xếp hạng. Cuối cùng, luôn có `ORDER BY` ngoài để trình bày kết quả ổn định và kiểm tra execution plan/index trên workload thực tế.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): cách Oracle gán ROWNUM và mẫu Top-N với inline view.
- [Oracle Database 19c — SELECT: row_limiting_clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp `OFFSET`, `FETCH FIRST/NEXT`, `ONLY`, `WITH TIES` và `PERCENT`.
- [Oracle Database 19c — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): đánh số hàng theo thứ tự trong query partition.
- [Oracle Database 19c — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): xếp hạng có khoảng trống khi có tie.
- [Oracle Database 19c — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): xếp hạng không có khoảng trống khi có tie.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html): tham khảo cú pháp SELECT và row limiting trên tài liệu Oracle AI Database hiện hành.
