# CASE dạng đơn giản và CASE dạng điều kiện

Trong Oracle SQL, **`CASE`** là biểu thức dùng để chọn một giá trị kết quả dựa trên điều kiện. Nó giúp viết quy tắc phân loại ngay trong câu truy vấn: xếp hạng đơn hàng theo số tiền, đổi mã trạng thái thành nhãn dễ đọc, phân nhóm nhân viên theo mức lương, hoặc tính tổng có điều kiện.

Oracle có hai dạng chính:

- **Simple CASE (CASE dạng đơn giản):** so sánh một biểu thức với lần lượt các giá trị `WHEN`.
- **Searched CASE (CASE dạng điều kiện):** đánh giá lần lượt các điều kiện logic trong từng `WHEN`.

Hai dạng có cú pháp gần nhau nhưng giải quyết những bài toán khác nhau. Simple CASE phù hợp khi một biểu thức cần so sánh bằng với nhiều giá trị cụ thể; searched CASE linh hoạt hơn khi cần dùng khoảng, toán tử, nhiều cột, NULL hoặc điều kiện kết hợp.

## 1. Cấu trúc chung của CASE

### 1.1. CASE dạng đơn giản

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ...
    [ELSE default_result]
END
```

Oracle đánh giá `expression`, so sánh với các giá trị `WHEN` theo thứ tự từ trên xuống và trả về `result` của nhánh đầu tiên khớp. Nếu không có nhánh nào khớp, Oracle trả về `ELSE`; nếu bỏ `ELSE`, kết quả mặc định là **NULL**.

Ví dụ:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW'       THEN 'Mới tạo'
        WHEN 'PAID'      THEN 'Đã thanh toán'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Trạng thái khác'
    END AS status_label
FROM lab_orders
ORDER BY order_id;
```

Ở đây `status` chỉ được đem so sánh với các giá trị cụ thể. Không cần lặp lại tên cột ở từng nhánh.

### 1.2. CASE dạng điều kiện

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ...
    [ELSE default_result]
END
```

Mỗi `WHEN` là một điều kiện SQL. Oracle đánh giá từ trên xuống và chọn nhánh đầu tiên có điều kiện **TRUE**.

Ví dụ:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    CASE
        WHEN salary IS NULL THEN 'Chưa có lương'
        WHEN salary >= 5000  THEN 'Cao'
        WHEN salary >= 3000  THEN 'Trung bình'
        WHEN salary > 0      THEN 'Thấp'
        ELSE 'Không hợp lệ'
    END AS salary_band
FROM lab_employees
ORDER BY employee_id;
```

Searched CASE có thể dùng `IS NULL`, `BETWEEN`, `IN`, `LIKE`, `EXISTS`, phép so sánh, phép kết hợp `AND`/`OR` và các biểu thức điều kiện khác. Đây là dạng nên chọn khi quy tắc không đơn thuần là “một giá trị bằng một trong những mã”.

### 1.3. CASE là biểu thức, không phải câu lệnh điều khiển

`CASE` trả về **một giá trị**. Vì vậy, nó có thể nằm trong danh sách `SELECT`, phép tính, `ORDER BY`, aggregate hoặc một điều kiện khác:

```sql
SELECT
    order_id,
    amount,
    CASE WHEN amount >= 1000 THEN amount * 0.05 ELSE 0 END AS discount
FROM lab_orders;
```

Đây là **CASE expression** trong SQL. PL/SQL còn có **CASE statement** dùng để điều khiển luồng lệnh; hai khái niệm có cú pháp và ngữ cảnh sử dụng khác nhau. Bài này tập trung vào biểu thức CASE trong SQL.

## 2. Tạo dữ liệu thực hành

Các ví dụ sau sử dụng bảng đơn hàng nhỏ để có thể kiểm tra kết quả. Hãy chạy trong **schema thực hành riêng** có quyền tạo bảng và quota tablespace; không dùng bảng nghiệp vụ có sẵn để thử DDL.

### 2.1. Tạo bảng

```sql
CREATE TABLE lab_case_orders (
    order_id    NUMBER PRIMARY KEY,
    customer    VARCHAR2(60 CHAR) NOT NULL,
    status      VARCHAR2(12 CHAR),
    amount      NUMBER(12, 2),
    priority    NUMBER(1),
    created_at  DATE NOT NULL
);
```

### 2.2. Chèn dữ liệu

```sql
INSERT INTO lab_case_orders VALUES
    (1, 'An',   'NEW',       250, 1, DATE '2024-01-10');
INSERT INTO lab_case_orders VALUES
    (2, 'Bình', 'PAID',     1500, 2, DATE '2024-01-11');
INSERT INTO lab_case_orders VALUES
    (3, 'Chi',  'CANCELLED', 800, 3, DATE '2024-01-12');
INSERT INTO lab_case_orders VALUES
    (4, 'Dũng', 'PAID',     5200, 1, DATE '2024-02-01');
INSERT INTO lab_case_orders VALUES
    (5, 'Hà',   'NEW',       NULL, 2, DATE '2024-02-03');
INSERT INTO lab_case_orders VALUES
    (6, 'Lan',  NULL,        400, NULL, DATE '2024-02-05');
INSERT INTO lab_case_orders VALUES
    (7, 'Minh', 'PAID',     1000, 3, DATE '2024-02-10');
INSERT INTO lab_case_orders VALUES
    (8, 'Nga',  'NEW',       250, 2, DATE '2024-02-11');

COMMIT;
```

Các trường hợp có chủ ý:

| ORDER_ID | CUSTOMER | STATUS | AMOUNT | PRIORITY |
| ---: | --- | --- | ---: | ---: |
| 1 | An | NEW | 250 | 1 |
| 2 | Bình | PAID | 1500 | 2 |
| 3 | Chi | CANCELLED | 800 | 3 |
| 4 | Dũng | PAID | 5200 | 1 |
| 5 | Hà | NEW | NULL | 2 |
| 6 | Lan | NULL | 400 | NULL |
| 7 | Minh | PAID | 1000 | 3 |
| 8 | Nga | NEW | 250 | 2 |

Bảng có giá trị NULL ở `STATUS`, `AMOUNT` và `PRIORITY` để kiểm tra hành vi CASE với dữ liệu chưa được cung cấp.

## 3. Simple CASE: một biểu thức, nhiều giá trị cần so sánh

### 3.1. Phân loại theo mã trạng thái

Khi một cột có một tập mã rời rạc, simple CASE dễ đọc:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW'       THEN 'Mới'
        WHEN 'PAID'      THEN 'Đã thanh toán'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Không xác định'
    END AS status_name
FROM lab_case_orders
ORDER BY order_id;
```

| STATUS | STATUS_NAME |
| --- | --- |
| NEW | Mới |
| PAID | Đã thanh toán |
| CANCELLED | Đã hủy |
| NULL | Không xác định |

Hàng có `STATUS NULL` đi vào `ELSE` vì không có giá trị WHEN nào so sánh bằng với NULL. Nếu bỏ `ELSE`, kết quả `STATUS_NAME` của hàng đó sẽ là NULL.

### 3.2. Phân loại mã số

```sql
SELECT
    order_id,
    priority,
    CASE priority
        WHEN 1 THEN 'Khẩn cấp'
        WHEN 2 THEN 'Bình thường'
        WHEN 3 THEN 'Có thể chờ'
        ELSE 'Chưa gán mức ưu tiên'
    END AS priority_label
FROM lab_case_orders
ORDER BY order_id;
```

Simple CASE phù hợp vì `PRIORITY` chỉ được so sánh với các giá trị 1, 2 và 3. Nó không phải lựa chọn tốt để mô tả khoảng như “từ 1.000 đến dưới 5.000”, vì simple CASE không cho viết điều kiện dạng `WHEN amount >= 1000`.

### 3.3. Simple CASE không phải chuỗi IF/ELSE tùy ý

Không thể viết:

```sql
CASE amount
    WHEN amount >= 1000 THEN 'Lớn'
    WHEN amount < 1000  THEN 'Nhỏ'
END
```

Ở simple CASE, mỗi `WHEN` là **giá trị cần so sánh bằng** với biểu thức sau `CASE`. Đoạn trên đang trộn biểu thức số `amount` với điều kiện logic. Hãy dùng searched CASE:

```sql
CASE
    WHEN amount >= 1000 THEN 'Lớn'
    WHEN amount < 1000  THEN 'Nhỏ'
    ELSE 'Chưa xác định'
END
```

## 4. Searched CASE: nhiều điều kiện logic

### 4.1. Phân loại theo khoảng giá trị

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount IS NULL THEN 'Chưa có số tiền'
        WHEN amount >= 5000 THEN 'Rất lớn'
        WHEN amount >= 1000 THEN 'Lớn'
        WHEN amount >= 500  THEN 'Trung bình'
        WHEN amount > 0     THEN 'Nhỏ'
        ELSE 'Bằng 0 hoặc âm'
    END AS amount_band
FROM lab_case_orders
ORDER BY order_id;
```

Các khoảng được kiểm tra theo thứ tự:

| Điều kiện | Khoảng được nhận sau khi các nhánh trước đã thất bại |
| --- | --- |
| `amount IS NULL` | Giá trị chưa có |
| `amount >= 5000` | Từ 5.000 trở lên |
| `amount >= 1000` | Từ 1.000 đến dưới 5.000 |
| `amount >= 500` | Từ 500 đến dưới 1.000 |
| `amount > 0` | Lớn hơn 0 và dưới 500 |
| `ELSE` | Bằng 0 hoặc âm |

Thứ tự nhánh quan trọng. Nếu đặt `WHEN amount >= 500 THEN ...` lên trước `WHEN amount >= 5000 THEN ...`, mọi số từ 5.000 trở lên cũng khớp nhánh 500 và không bao giờ đến nhánh “Rất lớn”.

### 4.2. Kết hợp nhiều cột

```sql
SELECT
    order_id,
    status,
    amount,
    CASE
        WHEN status = 'CANCELLED' THEN 'Không tính doanh thu'
        WHEN status = 'PAID' AND amount >= 1000 THEN 'Đã thu - giá trị cao'
        WHEN status = 'PAID' THEN 'Đã thu - giá trị thường'
        WHEN status = 'NEW' AND amount IS NULL THEN 'Chờ bổ sung số tiền'
        WHEN status = 'NEW' THEN 'Chờ thanh toán'
        ELSE 'Cần kiểm tra'
    END AS business_state
FROM lab_case_orders
ORDER BY order_id;
```

Searched CASE cho phép mỗi nhánh phối hợp nhiều thuộc tính. Ví dụ `status = 'PAID' AND amount >= 1000` cần đồng thời thỏa cả hai điều kiện.

### 4.3. Dùng BETWEEN, IN và LIKE

```sql
SELECT
    order_id,
    customer,
    amount,
    CASE
        WHEN amount BETWEEN 1000 AND 3000 THEN 'Trong khoảng mục tiêu'
        WHEN amount IN (250, 400, 800) THEN 'Giá trị mẫu'
        WHEN customer LIKE 'N%' THEN 'Tên bắt đầu bằng N'
        ELSE 'Nhóm khác'
    END AS classification
FROM lab_case_orders
ORDER BY order_id;
```

`BETWEEN` bao gồm cả hai đầu mút. Vì vậy `BETWEEN 1000 AND 3000` tương đương `amount >= 1000 AND amount <= 3000`. Nếu yêu cầu “từ 1.000 đến dưới 3.000”, phải dùng `amount >= 1000 AND amount < 3000`.

## 5. CASE với NULL và logic ba giá trị

Đây là điểm khác biệt quan trọng nhất giữa simple CASE và searched CASE.

### 5.1. Simple CASE không khớp WHEN NULL

Ví dụ:

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN NULL THEN 'Chưa có trạng thái'
        WHEN 'NEW' THEN 'Mới'
        ELSE 'Trạng thái khác'
    END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

Nhánh `WHEN NULL` **không khớp** hàng có `STATUS NULL`. Simple CASE thực hiện phép so sánh tương đương với `status = NULL`; kết quả là UNKNOWN chứ không phải TRUE.

### 5.2. Dùng searched CASE với IS NULL

```sql
SELECT
    order_id,
    status,
    CASE
        WHEN status IS NULL THEN 'Chưa có trạng thái'
        WHEN status = 'NEW' THEN 'Mới'
        WHEN status = 'PAID' THEN 'Đã thanh toán'
        ELSE 'Trạng thái khác'
    END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

Nếu cần nhận diện NULL, dùng **searched CASE + `IS NULL`**. Quy tắc tương tự áp dụng cho số, ngày tháng, locator và các cột có thể NULL.

### 5.3. WHEN chỉ được chọn khi điều kiện TRUE

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Trong searched CASE, một điều kiện `WHEN` đánh giá FALSE hoặc UNKNOWN đều không chọn nhánh đó; Oracle tiếp tục kiểm tra nhánh tiếp theo.

Ví dụ:

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount > 1000 THEN 'Trên 1000'
        WHEN amount <= 1000 THEN 'Không quá 1000'
        ELSE 'Không biết số tiền'
    END AS amount_group
FROM lab_case_orders
ORDER BY order_id;
```

Với `AMOUNT NULL`, cả `NULL > 1000` và `NULL <= 1000` đều UNKNOWN, nên nhánh `ELSE` được chọn. Nếu muốn xử lý NULL riêng, đặt `WHEN amount IS NULL THEN ...` ở đầu.

### 5.4. CASE không tự biến NULL thành 0

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN amount * 0.1
        ELSE 0
    END AS reward
FROM lab_case_orders;
```

Hàng có `AMOUNT NULL` đi vào `ELSE 0` vì điều kiện `amount >= 1000` là UNKNOWN. Nếu nghiệp vụ cần phân biệt “chưa có số tiền” với “không đạt thưởng”, hãy viết nhánh NULL trước:

```sql
CASE
    WHEN amount IS NULL THEN NULL
    WHEN amount >= 1000 THEN amount * 0.1
    ELSE 0
END
```

Không chọn giá trị thay thế theo thói quen; phải xác định rõ ý nghĩa nghiệp vụ.

## 6. Thứ tự WHEN và nguyên tắc nhánh đầu tiên

Oracle kiểm tra các nhánh `WHEN` từ trái sang phải. **Nhánh đầu tiên có điều kiện TRUE sẽ quyết định kết quả**; các nhánh sau không được dùng để ghi đè kết quả đó.

Ví dụ sai thứ tự:

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN 'Từ 1000'
        WHEN amount >= 5000 THEN 'Từ 5000'
        ELSE 'Dưới 1000'
    END AS amount_band
FROM lab_case_orders;
```

Với `AMOUNT = 5200`, nhánh đầu đã TRUE nên kết quả là “Từ 1000”; nhánh “Từ 5000” không bao giờ được tới. Sửa bằng cách đặt điều kiện hẹp hơn/cụ thể hơn trước:

```sql
CASE
    WHEN amount >= 5000 THEN 'Từ 5000'
    WHEN amount >= 1000 THEN 'Từ 1000'
    WHEN amount IS NULL THEN 'Chưa biết'
    ELSE 'Dưới 1000'
END
```

Với khoảng số, nên viết từ ngưỡng cao xuống thấp hoặc dùng các khoảng không chồng lấn. Với các quy tắc nghiệp vụ phức tạp, lập bảng quyết định trước khi chuyển thành CASE để không bỏ sót trường hợp.

### 6.1. Điều kiện chồng lấn

Ví dụ:

```sql
CASE
    WHEN amount >= 1000 THEN 'Nhóm A'
    WHEN amount BETWEEN 500 AND 2000 THEN 'Nhóm B'
    ELSE 'Nhóm khác'
END
```

Khoảng 1.000–2.000 thỏa cả hai nhánh. Do nhánh A đứng trước, toàn bộ giá trị đó được gán A. Nếu đây không phải ý định, hãy điều chỉnh điều kiện hoặc thứ tự.

## 7. ELSE: nhánh dự phòng và dữ liệu ngoài dự kiến

Nếu bỏ `ELSE`, Oracle trả về NULL khi không nhánh nào khớp:

```sql
SELECT
    order_id,
    CASE status
        WHEN 'NEW' THEN 'Mới'
        WHEN 'PAID' THEN 'Đã thanh toán'
    END AS status_label
FROM lab_case_orders;
```

Hàng `CANCELLED` và hàng `STATUS NULL` có `STATUS_LABEL NULL`. Điều này có thể đúng nếu ứng dụng muốn để trống; nhưng thường trong báo cáo, nên quyết định có cần nhãn dự phòng hay không.

Ví dụ:

```sql
CASE status
    WHEN 'NEW' THEN 'Mới'
    WHEN 'PAID' THEN 'Đã thanh toán'
    WHEN 'CANCELLED' THEN 'Đã hủy'
    ELSE 'Khác hoặc chưa xác định'
END
```

`ELSE` có thể gộp hai trường hợp “mã chưa được định nghĩa” và “NULL”. Nếu cần phân biệt, dùng searched CASE:

```sql
CASE
    WHEN status IS NULL THEN 'Chưa nhập trạng thái'
    WHEN status = 'NEW' THEN 'Mới'
    WHEN status = 'PAID' THEN 'Đã thanh toán'
    WHEN status = 'CANCELLED' THEN 'Đã hủy'
    ELSE 'Mã trạng thái chưa được hỗ trợ'
END
```

Trong hệ thống có quy tắc kiểm soát chặt, `ELSE` có thể trả về nhãn “Không hợp lệ” để phát hiện dữ liệu ngoài danh mục. Tuy nhiên, CASE chỉ **phân loại kết quả**; nó không tự chặn dữ liệu sai được ghi vào bảng. Muốn bảo vệ dữ liệu, dùng constraint, khóa ngoại, validation và quy tắc ghi phù hợp.

## 8. Kiểu dữ liệu của các nhánh THEN và ELSE

Mọi nhánh kết quả của CASE phải tương thích về kiểu dữ liệu theo quy tắc Oracle. Nếu các kết quả là kiểu ký tự, hãy dùng các kiểu ký tự tương thích; nếu là số, Oracle áp dụng quy tắc chuyển đổi và độ ưu tiên kiểu số. Tránh trộn chuỗi và số khiến Oracle phải chuyển đổi ngầm.

### 8.1. Ví dụ nhất quán kiểu ký tự

```sql
SELECT
    order_id,
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS amount_code
FROM lab_case_orders;
```

Các nhánh đều trả chuỗi ký tự.

### 8.2. Ví dụ nhất quán kiểu số

```sql
SELECT
    order_id,
    CASE
        WHEN amount >= 5000 THEN 3
        WHEN amount >= 1000 THEN 2
        ELSE 1
    END AS amount_level
FROM lab_case_orders;
```

Các nhánh đều trả số. Có thể dùng kết quả trong phép tính, sắp xếp hoặc aggregate.

### 8.3. Tránh trộn kiểu không cần thiết

Ví dụ không nên viết:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    ELSE 'Thấp'
END
```

Một nhánh trả NUMBER, nhánh khác trả VARCHAR2. Tùy quy tắc xác định kiểu của CASE và ngữ cảnh, Oracle có thể báo lỗi không tương thích kiểu hoặc phát sinh chuyển đổi ngoài ý muốn. Thay vì phụ thuộc implicit conversion, hãy thống nhất kết quả:

```sql
CASE
    WHEN amount >= 1000 THEN '1'
    ELSE 'Thấp'
END
```

hoặc nếu mục tiêu là số:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    ELSE 0
END
```

### 8.4. Ngày tháng và NULL có kiểu

Nếu kết quả cần là ngày:

```sql
CASE
    WHEN status = 'PAID' THEN created_at
    ELSE CAST(NULL AS DATE)
END AS paid_date
```

Nếu cần NULL làm kết quả cho cột kiểu ngày, `CAST(NULL AS DATE)` giúp ý định kiểu dữ liệu rõ ràng. Không thay NULL bằng chuỗi rỗng hoặc ngày giả như `DATE '1900-01-01'` nếu nghiệp vụ không định nghĩa giá trị đó.

### 8.5. Kiểm soát chuyển đổi ngày và số

Không nên dựa vào chuyển đổi ngầm từ chuỗi theo NLS:

```sql
CASE
    WHEN status = 'PAID' THEN TO_DATE('31/12/2024', 'DD/MM/YYYY')
    ELSE CAST(NULL AS DATE)
END
```

Dùng format mask tường minh cho `TO_DATE`/`TO_NUMBER` khi chuyển chuỗi. Một biểu thức CASE chỉ an toàn nếu các nhánh có kiểu và quy tắc chuyển đổi được xác định rõ; định dạng phụ thuộc session có thể làm kết quả khác giữa các môi trường.

## 9. CASE trong SELECT, WHERE, ORDER BY và GROUP BY

### 9.1. Trong SELECT: tạo nhãn kết quả

```sql
SELECT
    order_id,
    customer,
    amount,
    CASE
        WHEN amount IS NULL THEN 'Chưa nhập'
        WHEN amount >= 3000 THEN 'Cao'
        WHEN amount >= 1000 THEN 'Trung bình'
        ELSE 'Thấp'
    END AS amount_label
FROM lab_case_orders;
```

CASE không thay đổi dữ liệu lưu trong bảng; nó chỉ tạo một giá trị trong tập kết quả.

### 9.2. Trong ORDER BY: sắp xếp theo thứ tự nghiệp vụ

Giả sử muốn đơn `NEW` đứng trước `PAID`, rồi `CANCELLED`:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
ORDER BY
    CASE status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END,
    created_at DESC,
    order_id;
```

CASE tạo một **khóa sắp xếp nghiệp vụ**. Nếu bỏ `ELSE`, trạng thái không khớp sẽ trả NULL và thứ tự phụ thuộc quy tắc NULL mặc định; thêm ELSE giúp xác định rõ vị trí dữ liệu ngoài danh mục.

### 9.3. Trong WHERE: điều kiện linh hoạt

Có thể dùng CASE để chọn tiêu chí lọc:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
WHERE
    CASE
        WHEN status = 'PAID' AND amount >= 1000 THEN 1
        WHEN status = 'NEW' THEN 1
        ELSE 0
    END = 1;
```

Truy vấn hợp lệ, nhưng với điều kiện lọc thông thường, biểu thức Boolean rõ ràng thường dễ đọc và có cơ hội tối ưu hơn:

```sql
SELECT order_id, customer, status, amount
FROM lab_case_orders
WHERE (status = 'PAID' AND amount >= 1000)
   OR status = 'NEW';
```

Không dùng CASE chỉ để biến điều kiện thành 1/0 nếu không có lợi ích rõ ràng. Bọc cột trong biểu thức CASE có thể khiến index thông thường khó được sử dụng cho predicate đó; cần xem execution plan và cân nhắc function-based index nếu thật sự cần.

### 9.4. Trong GROUP BY: nhóm theo phân loại

```sql
SELECT
    CASE
        WHEN amount IS NULL THEN 'Chưa có'
        WHEN amount >= 3000 THEN 'Cao'
        WHEN amount >= 1000 THEN 'Trung bình'
        ELSE 'Thấp'
    END AS amount_band,
    COUNT(*) AS order_count
FROM lab_case_orders
GROUP BY
    CASE
        WHEN amount IS NULL THEN 'Chưa có'
        WHEN amount >= 3000 THEN 'Cao'
        WHEN amount >= 1000 THEN 'Trung bình'
        ELSE 'Thấp'
    END
ORDER BY amount_band;
```

Oracle 19c yêu cầu biểu thức không aggregate trong danh sách SELECT phải phù hợp với GROUP BY. Có thể lặp CASE như trên, hoặc tạo một query block bên trong để tính nhãn rồi group ở ngoài:

```sql
SELECT amount_band, COUNT(*) AS order_count
FROM (
    SELECT
        CASE
            WHEN amount IS NULL THEN 'Chưa có'
            WHEN amount >= 3000 THEN 'Cao'
            WHEN amount >= 1000 THEN 'Trung bình'
            ELSE 'Thấp'
        END AS amount_band
    FROM lab_case_orders
)
GROUP BY amount_band
ORDER BY amount_band;
```

Query block ngoài xem `AMOUNT_BAND` như một cột nguồn bình thường.

## 10. Conditional aggregation: tính tổng theo điều kiện

Một ứng dụng phổ biến của CASE là **đưa điều kiện vào trong aggregate** để tính nhiều chỉ số trên cùng một tập hàng.

### 10.1. Đếm đơn theo trạng thái

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END) AS new_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS unknown_status_orders
FROM lab_case_orders;
```

Kết quả dự kiến: 8 đơn; 3 NEW; 3 PAID; 1 CANCELLED; 1 có trạng thái NULL. Mỗi hàng tạo 0 hoặc 1 cho từng nhóm, rồi `SUM` cộng lại.

### 10.2. COUNT(CASE WHEN ...)

Có thể viết:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'NEW' THEN 1 END) AS new_orders
FROM lab_case_orders;
```

Nếu điều kiện không đúng, CASE không có ELSE nên trả NULL; `COUNT(expression)` bỏ qua NULL. Cách này gọn khi chỉ cần đếm hàng thỏa điều kiện.

So sánh:

```sql
SUM(CASE WHEN condition THEN 1 ELSE 0 END)
COUNT(CASE WHEN condition THEN 1 END)
```

Cả hai có thể cho cùng số đếm trong trường hợp thông thường. Tuy nhiên, với `SUM`, bạn cần xác định ELSE; với `COUNT`, nhánh không thỏa phải trả NULL để không bị đếm.

### 10.3. Tổng doanh thu chỉ từ đơn đã thanh toán

```sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN status = 'NEW' THEN amount ELSE 0 END) AS pending_amount
FROM lab_case_orders;
```

`AMOUNT NULL` ở đơn NEW của Hà không đóng góp vào tổng. Vì query có hàng, ELSE 0 giúp nhóm không có giá trị phù hợp trả tổng 0 trong nhiều trường hợp. Nếu muốn phân biệt “không có đơn” với “có đơn nhưng amount đều NULL”, hãy thêm COUNT có điều kiện thay vì chỉ nhìn SUM.

### 10.4. AVG có thể thay đổi ý nghĩa theo ELSE

Hai cách sau không tương đương:

```sql
-- Trung bình trên các đơn PAID; hàng không PAID trả NULL và bị AVG bỏ qua.
SELECT AVG(CASE WHEN status = 'PAID' THEN amount END) AS avg_paid_amount
FROM lab_case_orders;

-- Trung bình trên toàn bộ đơn, coi hàng không PAID là 0.
SELECT AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS avg_with_zero
FROM lab_case_orders;
```

Trong câu đầu, `AVG` tính trên các giá trị amount của hàng PAID, bỏ NULL. Trong câu hai, mọi hàng không PAID đóng góp số 0 vào mẫu số; trung bình vì vậy nhỏ hơn. Phải chọn theo định nghĩa KPI, không chọn chỉ vì cú pháp ngắn.

### 10.5. Conditional aggregation theo nhóm

```sql
SELECT
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount IS NULL THEN 'UNKNOWN'
        ELSE 'LOW'
    END AS amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM lab_case_orders
GROUP BY
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount IS NULL THEN 'UNKNOWN'
        ELSE 'LOW'
    END
ORDER BY amount_band;
```

CASE phân loại từng hàng trước khi nhóm theo biểu thức phân loại. Nhóm UNKNOWN có một hàng và `SUM(AMOUNT)` là NULL. Nếu muốn báo cáo hiển thị 0, có thể dùng `NVL(SUM(amount),0)` nhưng cần giữ một cột đếm để không đánh mất thông tin rằng không có giá trị số.

## 11. CASE lồng nhau và biểu thức phức hợp

Có thể đặt một CASE trong kết quả của CASE khác:

```sql
SELECT
    order_id,
    status,
    amount,
    CASE
        WHEN status = 'PAID' THEN
            CASE
                WHEN amount >= 3000 THEN 'Đã trả - lớn'
                WHEN amount IS NULL THEN 'Đã trả - thiếu số tiền'
                ELSE 'Đã trả - thường'
            END
        WHEN status = 'NEW' THEN
            CASE
                WHEN amount IS NULL THEN 'Chờ bổ sung'
                ELSE 'Chờ thanh toán'
            END
        ELSE 'Trạng thái khác'
    END AS order_label
FROM lab_case_orders
ORDER BY order_id;
```

CASE lồng nhau có thể phản ánh cây quyết định nhiều tầng, nhưng nếu lồng quá sâu sẽ khó đọc và dễ bỏ sót điều kiện. Hãy cân nhắc:

- Viết một searched CASE phẳng nếu các nhánh độc lập.
- Dùng CTE/inline view để đặt tên cho các bước phân loại.
- Tạo bảng danh mục hoặc bảng quy tắc nếu nhãn thay đổi thường xuyên theo nghiệp vụ.
- Đưa quy tắc cần tái sử dụng vào view hoặc hàm phù hợp, có cân nhắc hiệu năng và quyền.

## 12. CASE và DECODE

Oracle còn có hàm legacy `DECODE`:

```sql
SELECT
    order_id,
    DECODE(
        status,
        'NEW', 'Mới',
        'PAID', 'Đã thanh toán',
        'CANCELLED', 'Đã hủy',
        'Khác'
    ) AS status_label
FROM lab_case_orders;
```

Với bài toán ánh xạ giá trị bằng nhau, `DECODE` có thể trông giống simple CASE. Tuy nhiên:

| Tiêu chí | CASE | DECODE |
| --- | --- | --- |
| Chuẩn SQL | Là biểu thức chuẩn SQL được Oracle hỗ trợ | Hàm đặc thù Oracle, có từ lâu |
| So sánh theo điều kiện tùy ý | Searched CASE hỗ trợ | Không linh hoạt như searched CASE |
| NULL | Simple CASE so sánh như `=` nên `WHEN NULL` không khớp; searched CASE dùng `IS NULL` | `DECODE` coi hai NULL là bằng nhau theo ngữ nghĩa riêng |
| Khả năng đọc nhiều điều kiện | Rõ ràng, dễ mở rộng | Dễ khó đọc khi nhiều cặp giá trị |
| Khuyến nghị cho SQL mới | Thường ưu tiên CASE | Chủ yếu để hiểu/bảo trì mã legacy |

Ví dụ khác biệt NULL:

```sql
SELECT
    CASE status
        WHEN NULL THEN 'CASE: NULL'
        ELSE 'CASE: ELSE'
    END AS case_result,
    DECODE(
        status,
        NULL, 'DECODE: NULL',
        'DECODE: ELSE'
    ) AS decode_result
FROM lab_case_orders
WHERE order_id = 6;
```

Với `STATUS NULL`, simple CASE đi vào ELSE; DECODE có thể khớp cặp search NULL theo quy tắc của DECODE. Không chuyển đổi cơ học giữa hai dạng nếu logic NULL có ý nghĩa.

## 13. CASE và các tính năng SQL khác

### 13.1. CASE trong điều kiện UPDATE

CASE có thể dùng để tính giá trị cập nhật:

```sql
UPDATE lab_case_orders
SET priority =
    CASE
        WHEN amount >= 5000 THEN 1
        WHEN amount >= 1000 THEN 2
        WHEN amount IS NULL THEN NULL
        ELSE 3
    END
WHERE status = 'PAID';

COMMIT;
```

Đây là thao tác DML thực sự thay đổi dữ liệu lab. Chỉ chạy trong schema thực hành. Nếu muốn thử mà không lưu, hãy chạy trên dữ liệu copy hoặc rollback trong transaction phù hợp; đừng thực hiện trên bảng thật khi chưa xác định phạm vi hàng.

### 13.2. CASE trong MERGE

CASE có thể xác định giá trị khi cập nhật hoặc chèn:

```sql
MERGE INTO target_orders t
USING source_orders s
ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET t.status =
        CASE
            WHEN s.cancel_flag = 'Y' THEN 'CANCELLED'
            WHEN s.paid_flag = 'Y' THEN 'PAID'
            ELSE 'NEW'
        END
WHEN NOT MATCHED THEN
    INSERT (order_id, status)
    VALUES (
        s.order_id,
        CASE
            WHEN s.cancel_flag = 'Y' THEN 'CANCELLED'
            WHEN s.paid_flag = 'Y' THEN 'PAID'
            ELSE 'NEW'
        END
    );
```

Đây là ví dụ mẫu minh họa vị trí biểu thức; các bảng `TARGET_ORDERS`/`SOURCE_ORDERS` phải tồn tại và điều kiện `ON` phải bảo đảm không làm một hàng target khớp nhiều hàng source. Quy tắc uniqueness và xử lý xung đột của MERGE cần được thiết kế riêng.

### 13.3. CASE trong analytic function

Có thể dùng CASE trong `PARTITION BY`, `ORDER BY` hoặc aggregate analytic:

```sql
SELECT
    order_id,
    status,
    amount,
    SUM(
        CASE WHEN status = 'PAID' THEN amount ELSE 0 END
    ) OVER () AS all_paid_amount
FROM lab_case_orders
ORDER BY order_id;
```

`OVER()` tính tổng có điều kiện trên toàn bộ tập hàng của query block mà không gộp mất các hàng chi tiết. Nếu chỉ muốn tổng theo từng trạng thái, dùng `PARTITION BY status`; nếu muốn tổng lũy kế, thêm cửa sổ `ORDER BY` và frame phù hợp.

## 14. CASE, short-circuit và biểu thức có thể gây lỗi

Oracle tài liệu hóa **short-circuit evaluation** cho CASE: các nhánh WHEN được kiểm tra theo thứ tự và Oracle không cần đánh giá các nhánh sau khi đã tìm được nhánh phù hợp. Điều này hữu ích khi các nhánh sau có biểu thức tốn chi phí hoặc không áp dụng cho hàng hiện tại.

Ví dụ bảo vệ phép chia:

```sql
SELECT
    order_id,
    CASE
        WHEN amount IS NULL OR amount = 0 THEN NULL
        ELSE 1000 / amount
    END AS reciprocal_value
FROM lab_case_orders;
```

CASE giúp không thực hiện phép chia trong nhánh ELSE đối với hàng có amount NULL hoặc 0, theo ngữ nghĩa đánh giá nhánh của CASE.

Tuy nhiên, không nên coi CASE là **hàng rào tuyệt đối chống mọi lỗi ở mọi vị trí**:

- Optimizer có thể biến đổi biểu thức theo quy tắc SQL.
- Một số aggregate hoặc biểu thức được tính ở pha khác có thể được đánh giá trước CASE bao quanh chúng.
- Hàm do người dùng định nghĩa có thể có side effect hoặc hành vi không an toàn khi được gọi trong SQL.
- Một lỗi chuyển đổi kiểu có thể xảy ra trong biểu thức trước khi CASE trả kết quả nếu thiết kế kiểu không nhất quán.

Đối với phép chia, cách viết toán học an toàn và rõ ràng cũng có thể là:

```sql
SELECT
    order_id,
    1000 / NULLIF(amount, 0) AS reciprocal_value
FROM lab_case_orders;
```

`NULLIF(amount,0)` trả NULL khi amount bằng 0; chia cho NULL cho kết quả NULL. Với amount NULL, kết quả cũng NULL. Cách này gọn nếu đúng ý nghĩa nghiệp vụ; CASE thích hợp hơn khi cần nhiều nhánh phân loại.

## 15. Những lỗi thường gặp khi dùng CASE

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `WHEN NULL` trong simple CASE nhưng không khớp | Simple CASE so sánh theo ngữ nghĩa bằng; NULL không bằng NULL | Dùng searched CASE với `WHEN expression IS NULL` |
| Nhánh tổng quát đặt trước nhánh cụ thể | Nhánh đầu tiên TRUE đã quyết định kết quả | Sắp xếp từ điều kiện cụ thể/hẹp đến rộng |
| Giá trị biên rơi sai nhóm | Dùng `BETWEEN` khi cần đầu mút loại trừ hoặc khoảng bị chồng lấn | Ghi rõ `>=`, `<` và kiểm thử tại biên |
| Kết quả CASE là NULL ngoài dự kiến | Bỏ ELSE; không nhánh nào khớp | Thêm ELSE hoặc nhánh xử lý NULL/giá trị lạ |
| ORA lỗi kiểu dữ liệu | Các nhánh THEN/ELSE không tương thích | Chuẩn hóa kiểu kết quả, CAST rõ khi cần |
| Dữ liệu ngày thay đổi giữa máy | Dựa vào implicit conversion/NLS | Dùng DATE literal hoặc TO_DATE với format mask |
| CASE trả 0 cho giá trị NULL | Điều kiện WHEN là UNKNOWN nên rơi vào ELSE | Thêm nhánh IS NULL nếu cần phân biệt |
| COUNT đếm sai trong conditional aggregation | ELSE 0 khiến COUNT(expression) vẫn đếm | Dùng COUNT(CASE WHEN ... THEN 1 END) hoặc SUM(0/1) đúng cách |
| AVG thấp hơn kỳ vọng | ELSE 0 làm các hàng không đạt điều kiện đi vào mẫu số | Dùng ELSE NULL/bỏ ELSE nếu chỉ tính trung bình hàng thỏa |
| CASE trong WHERE làm query chậm | Bọc cột trong expression có thể làm predicate khó dùng index thường | Viết điều kiện rõ hoặc xem xét function-based index |
| Dùng CASE để thay validation | CASE chỉ đổi giá trị kết quả, không chặn DML sai | Dùng CHECK, FK, NOT NULL và validation ở đúng tầng |
| CASE quá sâu, khó bảo trì | Nhồi cả cây quy tắc vào một biểu thức | Chia query block, dùng CTE/view hoặc bảng quy tắc |
| Chuyển DECODE sang CASE nhưng kết quả NULL khác | Hai cấu trúc có ngữ nghĩa NULL khác nhau | Kiểm tra riêng trường hợp NULL khi chuyển đổi |

## 16. Bài tập thực hành

Sử dụng bảng `LAB_CASE_ORDERS` ở mục 2. Hãy dự đoán kết quả trước khi chạy SQL.

### Bài 1 — Simple CASE cho trạng thái

Viết query trả về `ORDER_ID`, `STATUS` và nhãn:

- NEW → Mới tạo
- PAID → Đã thanh toán
- CANCELLED → Đã hủy
- Mọi trường hợp khác → Chưa xác định

**Đáp án gợi ý:**

```sql
SELECT order_id, status,
       CASE status
           WHEN 'NEW' THEN 'Mới tạo'
           WHEN 'PAID' THEN 'Đã thanh toán'
           WHEN 'CANCELLED' THEN 'Đã hủy'
           ELSE 'Chưa xác định'
       END AS status_label
FROM lab_case_orders
ORDER BY order_id;
```

### Bài 2 — Searched CASE cho nhóm số tiền

Phân loại:

- NULL → Chưa nhập
- Từ 3.000 trở lên → Cao
- Từ 1.000 đến dưới 3.000 → Trung bình
- Lớn hơn 0 và dưới 1.000 → Thấp
- Còn lại → Bằng 0 hoặc âm

Hãy kiểm thử đúng các biên 0, 1.000 và 3.000 bằng cách thêm các hàng lab hoặc truy vấn trực tiếp với các giá trị mẫu.

### Bài 3 — CASE và NULL

Chạy hai biểu thức:

```sql
SELECT
    CASE status
        WHEN NULL THEN 'NULL branch'
        ELSE 'ELSE branch'
    END AS simple_case_result,
    CASE
        WHEN status IS NULL THEN 'NULL branch'
        ELSE 'ELSE branch'
    END AS searched_case_result
FROM lab_case_orders
WHERE order_id = 6;
```

Giải thích vì sao hai kết quả khác nhau.

### Bài 4 — Thứ tự WHEN

Cho biểu thức:

```sql
CASE
    WHEN amount >= 1000 THEN 'A'
    WHEN amount >= 5000 THEN 'B'
    ELSE 'C'
END
```

Giải thích vì sao amount 5.200 nhận A. Viết lại để nhận B. Sau đó tạo một bảng quyết định cho các ngưỡng của riêng bạn.

### Bài 5 — Conditional aggregation

Viết một query trả một hàng với:

- Tổng số đơn.
- Số đơn NEW, PAID và CANCELLED.
- Tổng tiền PAID.
- Số đơn chưa có STATUS.

Gợi ý dùng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` hoặc `COUNT(CASE WHEN ... THEN 1 END)`.

### Bài 6 — Tính AVG có và không có ELSE 0

So sánh:

```sql
SELECT
    AVG(CASE WHEN status = 'PAID' THEN amount END) AS avg_paid,
    AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS avg_with_zero
FROM lab_case_orders;
```

Tính số hàng đóng góp vào mẫu số của từng AVG và giải thích hai KPI đang đo điều gì.

### Bài 7 — CASE trong ORDER BY

Sắp xếp theo ưu tiên NEW trước, PAID thứ hai, CANCELLED thứ ba, NULL/khác cuối; trong cùng trạng thái, đơn mới hơn đứng trước:

```sql
SELECT order_id, customer, status, created_at
FROM lab_case_orders
ORDER BY
    CASE
        WHEN status = 'NEW' THEN 1
        WHEN status = 'PAID' THEN 2
        WHEN status = 'CANCELLED' THEN 3
        ELSE 4
    END,
    created_at DESC,
    order_id;
```

Giải thích vai trò của ELSE và khóa phụ ORDER_ID.

### Bài 8 — CASE hay DECODE?

Viết cùng một nhãn trạng thái bằng `DECODE` và simple CASE. Thử với hàng có STATUS NULL. Ghi lại sự khác nhau và giải thích vì sao không nên chuyển đổi mã legacy mà không kiểm tra ngữ nghĩa NULL.

### Bài 9 — Sửa biểu thức CASE sai kiểu

Sửa biểu thức sau để có kiểu kết quả nhất quán:

```sql
CASE
    WHEN amount >= 1000 THEN 1
    WHEN amount IS NULL THEN 'UNKNOWN'
    ELSE 0
END
```

Có thể chọn tất cả kết quả là VARCHAR2 (`'1'`, `'UNKNOWN'`, `'0'`) hoặc tất cả là NUMBER với quy ước số phù hợp. Nêu ưu/nhược của từng lựa chọn đối với ứng dụng.

## 17. Dọn bảng thực hành

Chỉ chạy trong schema lab do bạn tạo:

```sql
DROP TABLE lab_case_orders PURGE;
```

`PURGE` bỏ qua recycle bin. Không dùng câu lệnh này trên bảng nghiệp vụ hoặc bảng không thuộc quyền sở hữu của bạn.

## Tổng kết

**Simple CASE** so sánh một biểu thức với các giá trị WHEN; **searched CASE** kiểm tra các điều kiện logic. Cả hai chọn **nhánh đầu tiên phù hợp**, trả kết quả của THEN và dùng ELSE (hoặc NULL nếu bỏ ELSE) khi không nhánh nào được chọn. Simple CASE không dùng `WHEN NULL` để bắt NULL; searched CASE cần `IS NULL`. Các nhánh trả về phải có kiểu tương thích, và thứ tự điều kiện phải phản ánh đúng bảng quyết định nghiệp vụ.

CASE là một công cụ biểu thức linh hoạt: nó tạo nhãn, điều khiển thứ tự sắp xếp, phân nhóm, tính aggregate có điều kiện và xây dựng biểu thức trong nhiều mệnh đề SQL. Hãy dùng nó để mô tả quy tắc rõ ràng, xử lý NULL có chủ đích và giữ các truy vấn dễ kiểm thử. Khi quy tắc trở nên quá phức tạp hoặc thay đổi thường xuyên, cân nhắc đưa quy tắc vào bảng cấu hình, view hoặc tầng nghiệp vụ thay vì mở rộng một CASE lồng nhau khó bảo trì.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — CASE Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CASE-Expressions.html) — cú pháp simple/searched CASE, short-circuit, kiểu dữ liệu và giới hạn biểu thức.
- [Oracle Database SQL Language Reference — DECODE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DECODE.html) — ngữ nghĩa hàm DECODE và xử lý NULL.
- [Oracle Database SQL Language Reference — NULLs (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — logic ba giá trị và điều kiện NULL.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — hành vi aggregate với NULL.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — execution plan và cách đánh giá tác động biểu thức lên truy vấn.

Khi triển khai trên release Oracle khác 19c, hãy đối chiếu tài liệu đúng phiên bản về kiểu dữ liệu, chuyển đổi ngầm và khả năng optimizer. Với SQL được dùng ở nhiều môi trường, ưu tiên CASE có kiểu rõ ràng và không phụ thuộc NLS session ngoài ý muốn.
