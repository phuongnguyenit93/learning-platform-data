# NULL trong ràng buộc UNIQUE, CHECK và khóa ghép

## 1. Vì sao `NULL` làm thay đổi cách hiểu ràng buộc?

Trong một hệ thống sử dụng Oracle Database, bảng khách hàng có thể có email chưa được khai báo, đơn hàng có ngày hoàn thành chưa biết, hoặc một mã định danh từ hệ thống đối tác chỉ xuất hiện sau khi đồng bộ. Những giá trị chưa có đó thường được biểu diễn bằng **`NULL`**.

Người mới học SQL dễ dự đoán sai hai hành vi:

- “Cột có `UNIQUE` thì không được chứa hai hàng `NULL`.”
- “Ràng buộc `CHECK (amount > 0)` sẽ từ chối cả `NULL`, vì `NULL` không lớn hơn 0.”

Trong Oracle, **cả hai phát biểu đều không đúng với cách dùng thông thường**. Một ràng buộc `UNIQUE` một cột cho phép nhiều hàng có `NULL`, còn `CHECK` chỉ từ chối biểu thức trả về **`FALSE`**; biểu thức trả về **`UNKNOWN`** do `NULL` thường vẫn thỏa ràng buộc.

Với **khóa ghép** gồm nhiều cột, tình huống còn tinh tế hơn: `UNIQUE (a, b)` không có quy tắc đơn giản là “hễ có bất kỳ `NULL` nào thì có thể lặp tùy ý”. Oracle có hành vi khác nhau khi **tất cả thành phần đều NULL** và khi **chỉ một số thành phần NULL**.

Bài học thuộc chương **Bảng và ràng buộc**, tập trung vào:

1. Ý nghĩa của `NULL` và logic ba giá trị trong biểu thức SQL.
2. Sự khác nhau giữa `UNIQUE`, `NOT NULL`, `CHECK` và `PRIMARY KEY`.
3. Cách Oracle xử lý `NULL` trong `UNIQUE` một cột và `UNIQUE` khóa ghép.
4. Các tình huống `NULL` khi dùng khóa chính/khóa ngoại ghép.
5. Viết ràng buộc theo đúng quy tắc nghiệp vụ, tránh “lọt” dữ liệu không hợp lệ.
6. Đọc metadata, nhận biết lỗi và thực hành bằng SQL có thể quan sát được.

> Các ví dụ dưới đây dành cho **schema thực hành**, không sử dụng bảng đang phục vụ ứng dụng thật. Những lệnh `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `ALTER` và `DROP` thay đổi database; phần giải thích kết quả không phải output đã chạy trên một hệ thống cụ thể.

## 2. `NULL` không phải 0, chuỗi rỗng hay một giá trị thông thường

Trong Oracle, `NULL` biểu thị **không có giá trị được biết/ghi nhận** cho một trường dữ liệu. Nó không giống:

| Giá trị | Ý nghĩa |
|---|---|
| `0` | Một giá trị số cụ thể bằng không |
| `'0'` | Chuỗi gồm ký tự số `0` |
| `' '` | Chuỗi chứa dấu cách, không phải `NULL` |
| `DATE '2026-01-01'` | Một ngày cụ thể |
| `NULL` | Không có giá trị xác định cho biểu thức/cột |

Ví dụ:

```sql
SELECT CASE WHEN 0 IS NULL THEN 'YES' ELSE 'NO' END AS zero_is_null,
       CASE WHEN ' ' IS NULL THEN 'YES' ELSE 'NO' END AS space_is_null,
       CASE WHEN NULL IS NULL THEN 'YES' ELSE 'NO' END AS null_is_null
FROM dual;
```

Kết quả về mặt ý nghĩa: `0` và `' '` không phải `NULL`, còn `NULL IS NULL` là `TRUE`.

### 2.1. Đặc điểm của chuỗi rỗng trong Oracle

Ở các phiên bản Oracle Database hiện hành, chuỗi có độ dài bằng 0 (`''`) thuộc các kiểu ký tự thông thường được Oracle xử lý như `NULL`:

```sql
SELECT CASE
           WHEN '' IS NULL THEN 'IS NULL'
           ELSE 'IS NOT NULL'
       END AS empty_string_behavior
FROM dual;
```

Do đó việc đưa `''` vào một cột `VARCHAR2` có thể có tác động giống đưa `NULL` vào cột đó, kể cả khi xét `NOT NULL`, `UNIQUE` và `CHECK`. Nhưng chuỗi chỉ có một hay nhiều **dấu cách** không phải chuỗi rỗng. Nếu ứng dụng coi `"   "` là “không nhập gì”, hãy quy định cách chuẩn hóa và kiểm tra dữ liệu thay vì mặc định Oracle tự coi nó là `NULL`.

### 2.2. Không so sánh `NULL` bằng dấu `=`

Những biểu thức sau không tương đương:

```sql
-- Không phải cách tìm NULL:
SELECT * FROM customers WHERE email = NULL;

-- Cách đúng:
SELECT * FROM customers WHERE email IS NULL;
```

`email = NULL` trả về **`UNKNOWN`**, kể cả khi `email` đang `NULL`. Trong mệnh đề `WHERE`, chỉ hàng có điều kiện **`TRUE`** được chọn. Vì thế `WHERE email = NULL` không tìm được các hàng NULL như người viết mong đợi.

Tương tự:

```sql
-- Không dùng để kiểm tra khác NULL:
WHERE email <> NULL

-- Dùng:
WHERE email IS NOT NULL
```

Nếu cần so sánh hai giá trị cho mục đích nghiệp vụ và muốn `NULL` ở cả hai phía được coi là tương đương, phải viết rõ **null-safe comparison** phù hợp với phiên bản Oracle và tình huống. Điều này khác với quy tắc đánh giá ràng buộc `UNIQUE`.

## 3. Logic ba giá trị: TRUE, FALSE, UNKNOWN

SQL không chỉ có `TRUE` và `FALSE` khi biểu thức có thể chứa `NULL`; nó còn có **`UNKNOWN`**. Đây là cơ sở để hiểu vì sao `CHECK` thường cho qua một giá trị NULL.

| Biểu thức | Kết quả logic |
|---|---|
| `5 > 0` | `TRUE` |
| `-5 > 0` | `FALSE` |
| `NULL > 0` | `UNKNOWN` |
| `NULL = 5` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |

Để quan sát bằng Oracle SQL, có thể dùng `CASE WHEN`:

```sql
SELECT CASE
           WHEN 5 > 0 THEN 'TRUE'
           ELSE 'NOT TRUE'
       END AS positive_number,
       CASE
           WHEN CAST(NULL AS NUMBER) > 0 THEN 'TRUE'
           ELSE 'NOT TRUE'
       END AS null_comparison
FROM dual;
```

`CASE WHEN` chỉ chọn nhánh `THEN` khi điều kiện là `TRUE`; nhánh `ELSE` ở ví dụ trên gộp cả `FALSE` lẫn `UNKNOWN`, nên nó chỉ dùng để minh họa việc điều kiện NULL **không phải TRUE**.

### 3.1. AND, OR và NOT khi có UNKNOWN

Một số kết quả cốt lõi:

| Biểu thức | Kết quả |
|---|---|
| `TRUE AND UNKNOWN` | `UNKNOWN` |
| `FALSE AND UNKNOWN` | `FALSE` |
| `TRUE OR UNKNOWN` | `TRUE` |
| `FALSE OR UNKNOWN` | `UNKNOWN` |
| `NOT UNKNOWN` | `UNKNOWN` |

Quy tắc này ảnh hưởng cả ràng buộc có nhiều điều kiện như:

```sql
CHECK (start_date <= end_date AND status = 'ACTIVE')
```

Nếu `start_date` là NULL thì phép so sánh đầu có thể là `UNKNOWN`. Nếu phần còn lại là `TRUE`, kết quả tổng thể sẽ là `UNKNOWN` và ràng buộc `CHECK` có thể **cho qua** hàng đó. Nếu phần còn lại là `FALSE`, `UNKNOWN AND FALSE` thành `FALSE`, nên hàng bị từ chối.

Muốn diễn đạt đúng quy tắc nghiệp vụ, phải xác định **cột nào được phép thiếu giá trị**, cột nào bắt buộc, và tổ hợp trạng thái nào là hợp lệ.

## 4. Oracle áp dụng các ràng buộc thế nào?

| Ràng buộc | Mục tiêu | Khi gặp `NULL` |
|---|---|---|
| `NOT NULL` | Cột phải có giá trị khác `NULL` | **Từ chối** `NULL` |
| `UNIQUE (c)` | Không có hai giá trị không-NULL trùng nhau ở cột `c` | Cho phép nhiều `NULL` trong trường hợp một cột |
| `UNIQUE (a,b)` | Đảm bảo tính duy nhất của khóa ghép theo ngữ nghĩa Oracle | Cho phép nhiều hàng toàn-NULL; phần-NULL có quy tắc riêng |
| `CHECK (expression)` | Điều kiện nghiệp vụ ở mức hàng | Từ chối `FALSE`; chấp nhận `TRUE` hoặc `UNKNOWN` |
| `PRIMARY KEY` | Định danh hàng duy nhất | **Mọi thành phần khóa không được NULL**, và tổ hợp khóa phải duy nhất |
| `FOREIGN KEY` | Tham chiếu khóa của bảng cha | Các thành phần NULL trong khóa ngoại ghép có ngữ nghĩa đặc biệt |

`UNIQUE` và `PRIMARY KEY` đều có tính duy nhất, nhưng **`PRIMARY KEY` bao hàm yêu cầu không NULL**. Một bảng chỉ có một khóa chính, trong khi có thể khai báo nhiều ràng buộc `UNIQUE` phục vụ những khóa ứng viên khác nhau.

Đừng gộp ba yêu cầu riêng thành một:

1. **Phải có dữ liệu?** → `NOT NULL`.
2. **Không được trùng với giá trị của hàng khác?** → `UNIQUE`.
3. **Giá trị hoặc mối quan hệ giữa các cột phải hợp lệ?** → `CHECK` hoặc cơ chế ràng buộc phù hợp.

Một cột có thể cần cả `NOT NULL`, `UNIQUE` và `CHECK`, tùy quy tắc nghiệp vụ.

## 5. `UNIQUE` trên một cột: nhiều `NULL` thường được phép

### 5.1. Bài toán email chưa được cung cấp

Giả sử mỗi email khi có giá trị chỉ được gán cho một tài khoản, nhưng một số người dùng chưa cung cấp email:

```sql
CREATE TABLE demo_unique_email (
    customer_id NUMBER CONSTRAINT pk_due PRIMARY KEY,
    email       VARCHAR2(120),
    CONSTRAINT uq_due_email UNIQUE (email)
);
```

Những lệnh sau minh họa:

```sql
-- Thành công: hai khách hàng đều chưa có email.
INSERT INTO demo_unique_email (customer_id, email)
VALUES (1, NULL);

INSERT INTO demo_unique_email (customer_id, email)
VALUES (2, NULL);

-- Thành công: email đã có giá trị cụ thể.
INSERT INTO demo_unique_email (customer_id, email)
VALUES (3, 'lan@example.test');

-- Thất bại: email không-NULL bị trùng.
-- INSERT INTO demo_unique_email (customer_id, email)
-- VALUES (4, 'lan@example.test');
```

Khi thực hiện dòng cuối (bỏ comment) và ràng buộc có hiệu lực, Oracle thường báo:

```text
ORA-00001: unique constraint (...) violated
```

Trong ví dụ, **hai dòng `NULL` không vi phạm `UNIQUE (email)`**, còn hai email `'lan@example.test'` giống nhau không được phép.

### 5.2. Vì sao đây không phải mâu thuẫn?

`NULL` không phải một giá trị được so bằng `=` với giá trị khác. Quy tắc của Oracle đối với `UNIQUE` một cột là không coi các giá trị NULL lặp lại như những giá trị khóa xác định trùng nhau. Không suy luận rằng Oracle đang thực hiện phép `NULL = NULL` và nhận `TRUE`.

Ngoài ra, một **B-tree index thông thường** của Oracle không lưu mục khóa khi **toàn bộ thành phần khóa index đều NULL**. Đây là một góc nhìn hữu ích về việc nhiều hàng NULL có thể cùng tồn tại ở ràng buộc một cột, nhưng quy tắc `UNIQUE` vẫn nên được hiểu ở **cấp ràng buộc**, không chỉ qua cơ chế index.

### 5.3. Muốn email vừa bắt buộc vừa không trùng

Khai báo:

```sql
CREATE TABLE demo_required_email (
    customer_id NUMBER PRIMARY KEY,
    email       VARCHAR2(120) NOT NULL,
    CONSTRAINT uq_dre_email UNIQUE (email)
);
```

Bây giờ:

- `NULL` bị **`NOT NULL`** từ chối.
- Email đã có giá trị trùng nhau bị **`UNIQUE`** từ chối.
- Email khác nhau được phép theo ràng buộc, miễn không vi phạm điều kiện khác.

**`UNIQUE` một mình không thay `NOT NULL`**; thêm `NOT NULL` khi yêu cầu nghiệp vụ là “mọi tài khoản phải có email”.

### 5.4. Trùng dữ liệu sau khi chuẩn hóa

Ràng buộc duy nhất trên `email` không tự đảm bảo mọi biến thể như `Lan@Example.test` và `lan@example.test` được xem là cùng một email. Hành vi so sánh chuỗi còn phụ thuộc collation và thiết kế schema.

Nếu quy tắc nghiệp vụ là email không được trùng **sau khi chuẩn hóa về một dạng cụ thể**, hãy định nghĩa phương pháp chuẩn hóa nhất quán. Trong những môi trường phù hợp, một function-based unique index có thể hữu ích:

```sql
-- Minh họa: duy nhất theo UPPER(email) khi có giá trị.
CREATE UNIQUE INDEX ux_dre_email_upper
ON demo_required_email (UPPER(email));
```

Nhưng nếu bảng đã có `UNIQUE(email)`, index thứ hai có thể thừa hoặc xung đột về chính sách thiết kế. `UPPER` chỉ là một ví dụ; quy tắc email thực tế có thể phức tạp hơn, và cách chuyển hoa/thường phụ thuộc đặc tính dữ liệu/collation. Không tự giả định `UPPER()` là bộ chuẩn hóa duy nhất đúng cho mọi email hoặc mọi ngôn ngữ.

## 6. `UNIQUE` trên khóa ghép: trường hợp tất cả NULL và một phần NULL

### 6.1. Khóa ghép là gì?

Một **khóa ghép** (composite key) được tạo từ **hai hoặc nhiều cột**. Ví dụ, mã nhân viên chỉ cần duy nhất **trong từng công ty**:

```sql
CREATE TABLE demo_company_employee (
    company_id    NUMBER,
    employee_code VARCHAR2(20),
    full_name     VARCHAR2(100),
    CONSTRAINT uq_dce_company_code UNIQUE (company_id, employee_code)
);
```

Ràng buộc bảo vệ **tổ hợp** `(company_id, employee_code)`, không làm mỗi cột trở thành duy nhất độc lập.

Ví dụ:

```text
company_id  employee_code
----------  -------------
10          E001
10          E002
20          E001
```

Ba hàng trên không trùng **cặp khóa**, dù `company_id = 10` và `employee_code = E001` xuất hiện ở nhiều hàng.

### 6.2. Quy tắc NULL quan trọng của Oracle

Với ràng buộc `UNIQUE (company_id, employee_code)`:

- Nếu **cả hai cột đều `NULL`**, hàng tự đáp ứng phần duy nhất của ràng buộc và nhiều hàng `(NULL, NULL)` được phép.
- Nếu khóa ghép **có ít nhất một thành phần không NULL**, Oracle kiểm tra tính duy nhất theo ngữ nghĩa composite unique key; các hàng lặp cùng tổ hợp giá trị không-NULL và vị trí NULL có thể **vi phạm**.
- Vì vậy, **không** có quy tắc “chỉ cần một thành phần NULL thì Oracle bỏ qua UNIQUE”.

Thực hành từng trường hợp:

```sql
-- Cả hai hàng đều toàn-NULL: được phép.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, NULL);

INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, NULL);

-- Một phần NULL: hàng đầu được phép.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (10, NULL);

-- Trùng phần khóa không-NULL, cùng vị trí NULL: vi phạm UNIQUE.
-- INSERT INTO demo_company_employee (company_id, employee_code)
-- VALUES (10, NULL);

-- Trường hợp tương tự khi cột đầu NULL.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (NULL, 'E100');

-- Vi phạm với tổ hợp đã tồn tại.
-- INSERT INTO demo_company_employee (company_id, employee_code)
-- VALUES (NULL, 'E100');

-- Các tổ hợp khác nhau: được phép.
INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (20, NULL);

INSERT INTO demo_company_employee (company_id, employee_code)
VALUES (10, 'E100');
```

Vì Oracle đối xử khác giữa **khóa toàn-NULL** và **khóa chỉ có một phần NULL**, phải kiểm tra cả hai tình huống khi thiết kế bảng. Điều này đặc biệt quan trọng khi một trong hai cột dùng để xác định phạm vi (như công ty, tenant, dự án), cột kia là mã duy nhất trong phạm vi đó.

### 6.3. Bảng minh họa nhanh cho `UNIQUE (a,b)`

Giả sử bảng ban đầu trống và ràng buộc được kiểm tra ngay:

| Hàng chèn | `(a,b)` | Trạng thái theo minh họa | Lý do |
|---|---|---|---|
| 1 | `(NULL,NULL)` | Được phép | Khóa toàn-NULL |
| 2 | `(NULL,NULL)` | Được phép | Có thể lặp khóa toàn-NULL |
| 3 | `(10,NULL)` | Được phép | Tổ hợp này chưa xuất hiện |
| 4 | `(10,NULL)` | **Bị từ chối** | Trùng tổ hợp phần không-NULL đã tồn tại |
| 5 | `(20,NULL)` | Được phép | Giá trị không-NULL khác hàng 3 |
| 6 | `(NULL,'X')` | Được phép | Tổ hợp mới |
| 7 | `(NULL,'X')` | **Bị từ chối** | Trùng tổ hợp với hàng 6 |
| 8 | `(10,'X')` | Được phép | Khác các tổ hợp đã có |
| 9 | `(10,'X')` | **Bị từ chối** | Trùng đầy đủ với hàng 8 |

Ví dụ này cho thấy sự khác biệt giữa `UNIQUE` trên **một cột** và **nhiều cột**. Một giá trị `NULL` trong tổ hợp không đủ để kết luận hàng chắc chắn được phép.

### 6.4. “Duy nhất theo công ty” có nên để `company_id` NULL?

Nếu quy tắc thật là “mỗi nhân viên luôn thuộc một công ty”, hãy khai báo rõ:

```sql
CREATE TABLE demo_employee_strict (
    employee_id   NUMBER PRIMARY KEY,
    company_id    NUMBER NOT NULL,
    employee_code VARCHAR2(20) NOT NULL,
    CONSTRAINT uq_des_company_code UNIQUE (company_id, employee_code)
);
```

Đây là mô hình dễ hiểu:

- Mỗi hàng phải có `company_id`.
- Mỗi hàng phải có `employee_code`.
- Mỗi cặp `(company_id, employee_code)` xuất hiện tối đa một lần.

Nếu mã nhân viên **chưa có lúc tạo hồ sơ**, nhưng công ty bắt buộc, bạn có thể để `employee_code` nullable và vẫn dùng `UNIQUE(company_id, employee_code)`. Tuy nhiên, Oracle có thể chỉ cho một hàng `(10, NULL)` ở cùng phạm vi theo ngữ nghĩa unique key ghép. Nếu nghiệp vụ cần **nhiều nhân viên cùng công ty đang chờ mã**, phải lựa chọn ràng buộc khác phù hợp (xem phần về conditional uniqueness).

## 7. `PRIMARY KEY` ghép: không thành phần nào được NULL

Khóa chính dùng để định danh từng hàng. Với khóa chính ghép:

```sql
CREATE TABLE demo_order_line (
    order_id   NUMBER,
    line_no    NUMBER,
    product_id NUMBER NOT NULL,
    quantity   NUMBER NOT NULL,
    CONSTRAINT pk_dol PRIMARY KEY (order_id, line_no)
);
```

Oracle yêu cầu:

1. `order_id` khác `NULL`.
2. `line_no` khác `NULL`.
3. Cặp `(order_id, line_no)` không được trùng.

Ngay cả khi trong DDL không viết `NOT NULL` trực tiếp sau hai cột, ràng buộc `PRIMARY KEY (order_id, line_no)` **áp dụng tính NOT NULL cho các thành phần khóa chính**.

Ví dụ:

```sql
-- Hợp lệ: cùng order_id, line_no khác nhau.
INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
VALUES (1001, 1, 501, 2);

INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
VALUES (1001, 2, 502, 1);

-- Lỗi: line_no là NULL, khóa chính không được thiếu.
-- INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
-- VALUES (1001, NULL, 503, 3);

-- Lỗi: khóa chính đã tồn tại.
-- INSERT INTO demo_order_line (order_id, line_no, product_id, quantity)
-- VALUES (1001, 1, 504, 1);
```

Những lỗi điển hình:

- `ORA-01400: cannot insert NULL into ...` khi cố chèn NULL vào cột NOT NULL/PK.
- `ORA-00001: unique constraint ... violated` khi trùng tổ hợp khóa.

### `PRIMARY KEY (a,b)` có bằng `UNIQUE(a,b)` không?

**Không**, khi xét nullable:

| Thuộc tính | `PRIMARY KEY(a,b)` | `UNIQUE(a,b)` |
|---|---|---|
| Cặp không được trùng | Có | Có theo quy tắc composite unique |
| `a` được NULL | Không | Có thể |
| `b` được NULL | Không | Có thể |
| Có thể lặp `(NULL,NULL)` | Không, hàng đã không hợp lệ | Có |
| Số lượng mỗi bảng | Tối đa một PK | Có thể có nhiều UNIQUE |
| Vai trò | Khóa định danh chính của bảng | Khóa duy nhất bổ sung |

Nếu muốn cặp có đúng hành vi “không NULL và duy nhất” nhưng không dùng làm khóa chính, có thể khai báo **hai cột `NOT NULL` + một `UNIQUE`**. Nhưng **khóa chính** vẫn mang ý nghĩa rõ ràng hơn trong mô hình dữ liệu cho định danh hàng và quan hệ tham chiếu.

## 8. Khóa ngoại ghép và `NULL`: một góc nhìn bổ sung

**Khóa ngoại ghép** (composite foreign key) tham chiếu đến một khóa phù hợp ở bảng cha. Trong Oracle, khi một hoặc nhiều thành phần của **khóa ngoại ghép** là `NULL`, các giá trị không-NULL còn lại không nhất thiết phải khớp một hàng cha. Đây là hành vi khác với kiểm tra tính duy nhất của khóa ghép.

Ví dụ:

```sql
CREATE TABLE demo_department_parent (
    company_id    NUMBER NOT NULL,
    department_id NUMBER NOT NULL,
    department_name VARCHAR2(100),
    CONSTRAINT pk_ddp PRIMARY KEY (company_id, department_id)
);

CREATE TABLE demo_employee_child (
    employee_id   NUMBER PRIMARY KEY,
    company_id    NUMBER,
    department_id NUMBER,
    CONSTRAINT fk_dec_department
        FOREIGN KEY (company_id, department_id)
        REFERENCES demo_department_parent (company_id, department_id)
);
```

Giả sử bảng cha chưa có phòng ban nào. Oracle có thể chấp nhận:

```sql
-- Cả hai cột khóa ngoại đều NULL.
INSERT INTO demo_employee_child
    (employee_id, company_id, department_id)
VALUES (1, NULL, NULL);

-- Khóa ngoại ghép chỉ có một phần NULL.
INSERT INTO demo_employee_child
    (employee_id, company_id, department_id)
VALUES (2, 10, NULL);
```

Với giá trị khóa ngoại đầy đủ `(10,100)`, Oracle đòi cặp này tồn tại ở bảng cha:

```sql
-- Nếu bảng cha chưa có (10,100), câu này vi phạm khóa ngoại.
-- INSERT INTO demo_employee_child
--     (employee_id, company_id, department_id)
-- VALUES (3, 10, 100);
```

Điểm cần chú ý: có thể **nghiệp vụ không cho phép khóa tham chiếu nửa vời**. Khi đó, chỉ có `FOREIGN KEY` chưa đủ để diễn đạt ý định.

### 8.1. Chỉ cho phép cả hai NULL hoặc cả hai có giá trị

Có thể bổ sung một `CHECK`:

```sql
ALTER TABLE demo_employee_child
ADD CONSTRAINT ck_dec_pair_complete
CHECK (
       (company_id IS NULL     AND department_id IS NULL)
    OR (company_id IS NOT NULL AND department_id IS NOT NULL)
);
```

Quy tắc này cho phép:

- `(NULL,NULL)`: nhân viên chưa được gán phòng ban.
- `(10,100)`: cặp định danh đầy đủ, đồng thời phải thỏa foreign key.

Nó không cho phép:

- `(10,NULL)`.
- `(NULL,100)`.

**Trong ví dụ thực hành phía trên đã có hàng `(10,NULL)`**, nên `ALTER TABLE ... ADD CONSTRAINT` sẽ không thành công nếu chưa xử lý hàng đó. Đây là một hệ quả quan trọng của việc bổ sung ràng buộc vào bảng có dữ liệu: trước khi thêm constraint, phải rà soát và xử lý những bản ghi không phù hợp.

Nếu yêu cầu “mọi nhân viên đều phải thuộc một phòng ban”, đơn giản hơn là khai báo **cả hai thành phần khóa ngoại `NOT NULL`** ngay từ đầu, đồng thời dùng foreign key để bảo vệ quan hệ với bảng cha.

### 8.2. Unique key và foreign key khác nhau về mục tiêu

- `UNIQUE(a,b)` kiểm tra **không có tổ hợp khóa bị trùng** trong bảng được ràng buộc.
- `FOREIGN KEY(a,b) REFERENCES parent(a,b)` kiểm tra **quan hệ tham chiếu** khi các thành phần được cung cấp theo quy tắc Oracle.
- `CHECK` bổ sung tính hợp lệ về **tổ hợp NULL/not NULL**.
- `NOT NULL` xác định thành phần nào **bắt buộc có giá trị**.

Một hệ thống quản lý tenant/dự án thường cần phối hợp **nhiều ràng buộc**, không phải chỉ một khóa ghép.

## 9. `CHECK` và `NULL`: FALSE bị chặn, UNKNOWN được chấp nhận

### 9.1. Ví dụ số lượng phải dương

```sql
CREATE TABLE demo_check_quantity (
    item_id  NUMBER PRIMARY KEY,
    quantity NUMBER,
    CONSTRAINT ck_dcq_positive CHECK (quantity > 0)
);
```

Các trường hợp:

| `quantity` | `quantity > 0` | Kết quả `CHECK` |
|---|---|---|
| `5` | `TRUE` | Được phép |
| `0` | `FALSE` | Bị từ chối |
| `-2` | `FALSE` | Bị từ chối |
| `NULL` | `UNKNOWN` | **Được phép** |

Đây là chỗ dễ sai nhất khi viết check constraint. Nếu nghiệp vụ yêu cầu **quantity phải tồn tại và lớn hơn 0**, hãy thêm `NOT NULL`:

```sql
CREATE TABLE demo_check_quantity_required (
    item_id  NUMBER PRIMARY KEY,
    quantity NUMBER NOT NULL,
    CONSTRAINT ck_dcqr_positive CHECK (quantity > 0)
);
```

Bây giờ `NULL` bị `NOT NULL` từ chối; `0` và số âm bị `CHECK` từ chối.

### 9.2. Tại sao Oracle chấp nhận UNKNOWN trong CHECK?

`CHECK` dùng để bảo đảm **không có hàng nào được chứng minh là vi phạm biểu thức**. Khi một thành phần chưa biết (`NULL`), biểu thức có thể chưa xác định đúng/sai. Oracle theo quy tắc SQL cho phép hàng nếu kết quả là **`TRUE` hoặc `UNKNOWN`**, chỉ từ chối khi kết quả là **`FALSE`**.

Điều này khác `WHERE`:

```sql
-- WHERE chỉ chọn hàng khi điều kiện TRUE:
SELECT * FROM demo_check_quantity
WHERE quantity > 0;
```

Các hàng `quantity IS NULL` không được chọn bởi `WHERE quantity > 0`, nhưng vẫn có thể tồn tại trong bảng có `CHECK (quantity > 0)`. **Khả năng được lưu và khả năng được lọc ra bởi WHERE là hai câu hỏi khác nhau.**

### 9.3. `CHECK` với danh sách giá trị

```sql
CREATE TABLE demo_order_status (
    order_id NUMBER PRIMARY KEY,
    status  VARCHAR2(20),
    CONSTRAINT ck_dos_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);
```

Ràng buộc chặn `'UNKNOWN_STATUS'`, nhưng **không tự chặn `NULL`**. Nếu mỗi đơn hàng bắt buộc có trạng thái:

```sql
status VARCHAR2(20) NOT NULL
```

Khi đó `NOT NULL` bảo vệ sự hiện diện, `CHECK` bảo vệ miền giá trị hợp lệ.

Một lỗi hay gặp là viết `CHECK (status IN (...))` rồi nghĩ rằng ứng dụng có thể bỏ `NOT NULL` vì danh sách không chứa `NULL`. Đây là cách hiểu sai logic ba giá trị.

## 10. `CHECK` có nhiều cột và những bẫy của UNKNOWN

### 10.1. Ngày kết thúc phải sau ngày bắt đầu

```sql
CREATE TABLE demo_booking (
    booking_id NUMBER PRIMARY KEY,
    start_at   DATE,
    end_at     DATE,
    CONSTRAINT ck_db_time_order CHECK (end_at > start_at)
);
```

Với hai ngày có giá trị, Oracle kiểm tra thứ tự:

| `start_at` | `end_at` | Kết quả |
|---|---|---|
| 10:00 | 11:00 | Được phép |
| 11:00 | 10:00 | Bị từ chối |
| `NULL` | 11:00 | **Được phép** (`UNKNOWN`) |
| 10:00 | `NULL` | **Được phép** (`UNKNOWN`) |
| `NULL` | `NULL` | **Được phép** (`UNKNOWN`) |

Nếu cả hai ngày đều bắt buộc:

```sql
start_at DATE NOT NULL,
end_at   DATE NOT NULL,
CHECK (end_at > start_at)
```

Nếu chỉ có ngày kết thúc khi lịch đã được xác nhận, cần mô tả điều kiện đó bằng `CHECK` theo trạng thái cụ thể thay vì ép tất cả trường hợp thành một quy tắc.

### 10.2. Bắt buộc ít nhất một trong hai thông tin liên hệ

```sql
CREATE TABLE demo_contact (
    contact_id NUMBER PRIMARY KEY,
    email      VARCHAR2(100),
    phone      VARCHAR2(30),
    CONSTRAINT ck_dc_one_contact
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
);
```

Ở đây, `IS NULL` và `IS NOT NULL` luôn cho kết quả xác định `TRUE` hoặc `FALSE`, nên quy tắc rõ ràng:

| Email | Phone | Kết quả |
|---|---|---|
| Có | Không | Được phép |
| Không | Có | Được phép |
| Có | Có | Được phép |
| Không | Không | Bị từ chối |

Lưu ý `''` thường được Oracle coi là `NULL` đối với kiểu ký tự. Nếu nhập `"   "` (ba dấu cách), giá trị vẫn có thể là không-NULL và vượt qua điều kiện trên. Nếu nghiệp vụ cần ít nhất một thông tin liên hệ **hợp lệ**, nên bổ sung quy tắc định dạng/chuẩn hóa, không chỉ kiểm tra `IS NOT NULL`.

### 10.3. Bắt buộc đúng một trong hai cột

```sql
CREATE TABLE demo_payment_reference (
    payment_id     NUMBER PRIMARY KEY,
    card_ref       VARCHAR2(50),
    bank_ref       VARCHAR2(50),
    CONSTRAINT ck_dpr_exclusive
    CHECK (
        (card_ref IS NOT NULL AND bank_ref IS NULL)
        OR
        (card_ref IS NULL AND bank_ref IS NOT NULL)
    )
);
```

Ràng buộc trên biểu diễn **exclusive OR**: phải có đúng một loại tham chiếu. Cả hai có giá trị hoặc cả hai NULL đều bị từ chối.

Đây là ví dụ cho thấy dùng `IS NULL` trực tiếp thường an toàn và dễ đọc hơn khi xử lý điều kiện có thể thiếu dữ liệu, thay vì cố viết các phép so sánh `= NULL`.

### 10.4. Ràng buộc điều kiện theo trạng thái

Giả sử một đơn hàng có `status` là `NEW`, `PAID` hoặc `CANCELLED`, và mỗi đơn `PAID` phải có `paid_at`:

```sql
CREATE TABLE demo_order_paid (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20) NOT NULL,
    paid_at  DATE,
    CONSTRAINT ck_dop_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    CONSTRAINT ck_dop_paid_date
        CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);
```

Nếu `status='PAID'` và `paid_at IS NULL`, hai vế đều FALSE nên hàng bị từ chối. Nếu status khác `PAID`, vế đầu TRUE nên ràng buộc cho phép ngày thanh toán tùy theo quy tắc đã viết. Bởi `status` là `NOT NULL`, biểu thức thứ hai không rơi vào trường hợp UNKNOWN từ trạng thái bị thiếu.

Nếu nghiệp vụ còn yêu cầu **đơn chưa thanh toán không được có `paid_at`**, cần diễn đạt thêm điều kiện hai chiều, ví dụ kết hợp các nhánh `status='PAID'`/`status<>'PAID'` và `IS NULL`/`IS NOT NULL`.

## 11. Không phải mọi quy tắc đều viết được bằng CHECK

Một `CHECK` thông thường đánh giá biểu thức dựa trên **giá trị của hàng đang được thay đổi**, với những giới hạn cú pháp của Oracle. Nó không phải công cụ để đảm bảo mọi bất biến liên quan nhiều hàng hoặc bảng khác.

Ví dụ yêu cầu:

> “Không được có hai tài khoản cùng email trong cùng công ty.”

Một `CHECK` kiểu:

```sql
-- Ý tưởng không hợp lệ: CHECK không dùng subquery để đếm các hàng khác.
-- CHECK ((SELECT COUNT(*) FROM accounts WHERE email = ...) <= 1)
```

không phải cách Oracle hỗ trợ để bảo đảm duy nhất xuyên hàng. Hãy dùng **`UNIQUE`**, một unique index có biểu thức phù hợp, hoặc thiết kế dữ liệu khác.

Tương tự:

> “Mã phòng ban phải tồn tại trong bảng DEPARTMENTS.”

Nên dùng **`FOREIGN KEY`**, không dùng `CHECK` với một `SELECT` tham chiếu bảng khác.

Với các quy tắc nghiệp vụ phức tạp xuyên nhiều hàng, có thể cần transaction, mô hình bảng khác, cơ chế khóa/serialization, các ràng buộc bổ sung hoặc logic ứng dụng; không mặc định trigger có thể thay thế mọi constraint một cách an toàn dưới đồng thời cao.

## 12. Khi UNIQUE cho phép NULL nhưng nghiệp vụ lại muốn quy tắc khác

Những tình huống dưới đây cho thấy vì sao phải bắt đầu từ **ý nghĩa dữ liệu**, không bắt đầu bằng một câu `UNIQUE` rồi hy vọng nó khớp nhu cầu.

### 12.1. Trường hợp A: được thiếu email và không trùng nếu đã có

Quy tắc:

```text
email = NULL                -> Có thể nhiều tài khoản
email = 'a@example.test'    -> Tối đa một tài khoản
```

Sử dụng `UNIQUE(email)` với cột nullable là tự nhiên.

### 12.2. Trường hợp B: email bắt buộc và không trùng

Quy tắc:

```text
email = NULL                -> Không cho phép
email đã xuất hiện          -> Không cho phép trùng
```

Dùng `email NOT NULL` cộng `UNIQUE(email)`.

### 12.3. Trường hợp C: cần duy nhất theo tenant, nhưng được nhiều hàng chưa có mã

Giả sử cần:

```text
tenant_id = 10, code = NULL -> Cho phép nhiều hàng
tenant_id = 10, code = 'A'  -> Chỉ một hàng
tenant_id = 20, code = 'A'  -> Vẫn được phép
```

Đơn thuần `UNIQUE(tenant_id, code)` **không diễn đạt đúng** nhu cầu cho nhiều `(10,NULL)` trong Oracle. Một cách thiết kế có chủ đích là áp dụng **unique index có điều kiện** trên biểu thức chỉ có giá trị khi `code IS NOT NULL`:

```sql
CREATE TABLE demo_tenant_item (
    item_id   NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    code      VARCHAR2(30)
);

-- Nếu code NULL, cả hai biểu thức của khóa index đều NULL.
-- Nếu code có giá trị, ràng buộc tính duy nhất theo (tenant_id, code).
CREATE UNIQUE INDEX ux_dti_tenant_code_present
ON demo_tenant_item (
    CASE WHEN code IS NOT NULL THEN tenant_id END,
    CASE WHEN code IS NOT NULL THEN code END
);
```

Giải thích:

- Hàng `(10,NULL)` tạo khóa biểu thức `(NULL,NULL)` nên **không tạo mục khóa non-NULL trong B-tree thông thường** và có thể lặp.
- Hàng `(10,'A')` tạo khóa `(10,'A')`, vì vậy hàng thứ hai có cùng tenant/mã bị chặn.
- Hàng `(20,'A')` có khóa khác `(10,'A')` nên được phép.

Với chức năng này, `tenant_id NOT NULL` quan trọng vì mỗi item phải thuộc một tenant; còn `code` được phép thiếu. Đây là minh họa về **function-based unique index**, có thể cần những quyền và tính năng phù hợp. Cần đánh giá ràng buộc thực tế, đồng thời hiểu rằng index biểu thức khác với một `UNIQUE` constraint trực tiếp.

### 12.4. Trường hợp D: chỉ trạng thái ACTIVE phải duy nhất

Ví dụ một công ty cho phép giữ nhiều bản ghi `INACTIVE` có cùng mã, nhưng chỉ một bản ghi **`ACTIVE`** của mỗi mã trong từng tenant:

```sql
CREATE TABLE demo_tenant_account (
    account_id NUMBER PRIMARY KEY,
    tenant_id  NUMBER NOT NULL,
    code       VARCHAR2(30) NOT NULL,
    status     VARCHAR2(10) NOT NULL,
    CONSTRAINT ck_dta_status CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE UNIQUE INDEX ux_dta_active
ON demo_tenant_account (
    CASE WHEN status = 'ACTIVE' THEN tenant_id END,
    CASE WHEN status = 'ACTIVE' THEN code END
);
```

Với hàng `INACTIVE`, hai biểu thức trong index là NULL; nhiều bản ghi như vậy có thể cùng tồn tại. Với `ACTIVE`, cặp tenant/mã được kiểm tra tính duy nhất. Nếu `status` không `NOT NULL`, cần xem lại biểu thức `CASE` và quy tắc dữ liệu thiếu trạng thái để không có trường hợp ngoài ý muốn lọt qua.

### 12.5. Trường hợp E: chỉ cho phép một giá trị NULL

Đây là yêu cầu đặc biệt, **không phải ngữ nghĩa mặc định của `UNIQUE` một cột**. Nếu nghiệp vụ thực sự muốn xem NULL như một “giá trị” được phép xuất hiện tối đa một lần, một unique index trên biểu thức có thể mô phỏng quy tắc đó:

```sql
CREATE TABLE demo_one_missing_code (
    row_id NUMBER PRIMARY KEY,
    code   VARCHAR2(30),
    CONSTRAINT ck_domc_reserved
        CHECK (code IS NULL OR code <> '#MISSING#')
);

CREATE UNIQUE INDEX ux_domc_null_as_value
ON demo_one_missing_code (NVL(code, '#MISSING#'));
```

Index chuyển `NULL` thành chuỗi đánh dấu `#MISSING#`. Nếu có hai hàng với `code=NULL`, biểu thức của cả hai đều trở thành cùng giá trị, nên unique index từ chối hàng thứ hai. Ràng buộc `CHECK` cấm chính chuỗi đánh dấu xuất hiện như dữ liệu thật để tránh va chạm.

**Cảnh báo thiết kế:** việc xem “chưa có mã” như một thực thể duy nhất thường cần được thảo luận kỹ. Sentinel phải không va chạm, có kiểu/độ dài phù hợp và không bị cách chuẩn hóa dữ liệu làm lộ lỗ hổng. Đây là ví dụ kỹ thuật, không phải lời khuyên dùng `NVL`-index cho mọi cột nullable.

## 13. `UNIQUE` constraint và unique index: liên quan nhưng không đồng nhất

Oracle thường dùng index để hỗ trợ kiểm tra tính duy nhất. Tuy nhiên, ràng buộc logic và cấu trúc truy cập vật lý có vai trò khác nhau:

| Thành phần | Mục tiêu chính | Đặc điểm cần nhớ |
|---|---|---|
| `UNIQUE` constraint | Khẳng định quy tắc dữ liệu ở cấp schema | Được quản lý trong metadata constraint; có tên, trạng thái, cách kiểm tra |
| Unique index | Ngăn các khóa index trùng nhau theo biểu thức/cột index | Có thể dùng biểu thức hoặc `CASE`; không phải mọi unique index là một constraint đã khai báo |
| `PRIMARY KEY` constraint | Định danh mỗi hàng bằng khóa duy nhất và NOT NULL | Có thể được Oracle hỗ trợ qua index thích hợp |

Trong một số trường hợp như **deferrable constraint**, Oracle có thể sử dụng **nonunique index** để duy trì ràng buộc được kiểm tra theo thời điểm phù hợp. Vì thế không thể suy ra chỉ từ tên loại index rằng toàn bộ ngữ nghĩa của `UNIQUE`/`PRIMARY KEY` được quyết định ở đó.

### 13.1. Trạng thái và thời điểm kiểm tra

Ràng buộc thường được tạo **`NOT DEFERRABLE`** (kiểm tra theo quy tắc câu lệnh), còn ràng buộc được khai báo `DEFERRABLE` có thể hỗ trợ trì hoãn việc kiểm tra đến điểm phù hợp, ví dụ `COMMIT` nếu đang ở chế độ `DEFERRED`.

Ví dụ minh họa:

```sql
CREATE TABLE demo_deferred_codes (
    row_id NUMBER PRIMARY KEY,
    code   VARCHAR2(30),
    CONSTRAINT uq_ddc_code
        UNIQUE (code) DEFERRABLE INITIALLY DEFERRED
);
```

Với cấu hình như trên, một transaction có thể có trạng thái trung gian vi phạm tính duy nhất rồi sửa trước `COMMIT`, tùy quy tắc thực thi của Oracle. Nếu đến thời điểm kiểm tra mà vẫn vi phạm, transaction không thể xác nhận hợp lệ.

**Trì hoãn kiểm tra không làm thay đổi quy tắc về `NULL`**: một cột nullable vẫn có ngữ nghĩa `UNIQUE` tương ứng, còn một khóa chính vẫn không chấp nhận NULL. Không tự bật `DEFERRABLE` để giải quyết bài toán nhiều `NULL`; đó là vấn đề khác.

### 13.2. Vì sao cần khai báo constraint ngay trong schema?

Nếu chỉ kiểm tra trùng bằng đoạn ứng dụng:

```text
1. SELECT xem mã đã tồn tại chưa
2. Nếu chưa tồn tại thì INSERT
```

hai request đồng thời có thể cùng thấy “chưa có” và cùng cố `INSERT`. Một ràng buộc `UNIQUE` (hoặc unique index theo quy tắc phù hợp) cho database cơ chế bảo vệ tính duy nhất **ngay dưới concurrency**, không chỉ dựa vào kết quả của truy vấn kiểm tra trước.

Ứng dụng vẫn nên bắt và phân loại lỗi constraint để phản hồi nghiệp vụ, nhưng không nên coi việc kiểm tra tại Java trước khi ghi là thay thế hoàn toàn cho ràng buộc trong database.

## 14. Xem metadata constraint và nullable trong Oracle

Các view từ điển dữ liệu giúp xác định **ràng buộc đã khai báo thực sự**, đặc biệt khi bảng đã có từ trước và DDL ban đầu không còn trong tay.

### 14.1. Tìm constraint của một bảng trong schema hiện tại

```sql
SELECT constraint_name,
       constraint_type,
       status,
       deferrable,
       deferred,
       validated
FROM user_constraints
WHERE table_name = 'DEMO_COMPANY_EMPLOYEE'
ORDER BY constraint_name;
```

Giá trị thường gặp của `CONSTRAINT_TYPE`:

| Mã | Ý nghĩa |
|---|---|
| `P` | Primary key |
| `U` | Unique |
| `R` | Referential/foreign key |
| `C` | Check, trong đó có thể bao gồm biểu diễn metadata của `NOT NULL` |

`STATUS`, `VALIDATED`, `DEFERRABLE` và `DEFERRED` giúp hiểu constraint có đang bật, đã được xác minh theo trạng thái nào và có kiểm tra trì hoãn được không. Với một hệ thống cũ, **có tên constraint trong metadata chưa đủ để kết luận nó đang kiểm tra đúng mọi DML**; phải đọc trạng thái.

### 14.2. Xem thứ tự các cột trong khóa ghép

```sql
SELECT c.constraint_name,
       c.constraint_type,
       cc.position,
       cc.column_name
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'DEMO_COMPANY_EMPLOYEE'
  AND c.constraint_type IN ('P', 'U', 'R')
ORDER BY c.constraint_name, cc.position;
```

`POSITION` cho biết vị trí của cột trong khóa ghép; ví dụ `COMPANY_ID` ở vị trí 1, `EMPLOYEE_CODE` ở vị trí 2. Với những câu SQL kiểm tra metadata trên một database có tên constraint đặc biệt hoặc nhiều schema, cần mở rộng điều kiện/owner cho phù hợp.

### 14.3. Kiểm tra `NULLABLE` của cột

```sql
SELECT column_name,
       data_type,
       nullable
FROM user_tab_columns
WHERE table_name = 'DEMO_COMPANY_EMPLOYEE'
ORDER BY column_id;
```

`NULLABLE='N'` cho biết cột được ghi nhận là không nullable theo metadata Oracle. Đối chiếu với `USER_CONSTRAINTS` để hiểu tại sao cột bị bắt buộc; đừng mặc định một `CHECK (col > 0)` sẽ đổi metadata thành `NULLABLE='N'`.

### 14.4. Xem CHECK condition

Tùy phiên bản/client, nội dung điều kiện check nằm ở cột metadata như `SEARCH_CONDITION`/`SEARCH_CONDITION_VC` (mức hỗ trợ khác nhau). Ví dụ trên phiên bản có `SEARCH_CONDITION_VC`:

```sql
SELECT constraint_name,
       constraint_type,
       search_condition_vc
FROM user_constraints
WHERE table_name = 'DEMO_CHECK_QUANTITY'
  AND constraint_type = 'C';
```

Trước khi dùng câu SQL này trên database cũ, hãy kiểm tra view có cột `SEARCH_CONDITION_VC` hay không; một số phiên bản chỉ có trường `SEARCH_CONDITION` kiểu dữ liệu khó xử lý bằng câu SQL thông thường.

### 14.5. Xem unique index có biểu thức

```sql
SELECT index_name,
       uniqueness,
       table_name
FROM user_indexes
WHERE table_name = 'DEMO_TENANT_ITEM'
ORDER BY index_name;
```

Đối với function-based index:

```sql
SELECT index_name,
       column_position,
       column_expression
FROM user_ind_expressions
WHERE index_name = 'UX_DTI_TENANT_CODE_PRESENT'
ORDER BY column_position;
```

Metadata index cho biết biểu thức nào đang kiểm tra tính duy nhất. Nếu chỉ đọc `USER_CONSTRAINTS` mà bỏ qua unique index được tạo riêng, bạn có thể bỏ sót một quy tắc thực thi ở cấp database.

### 14.6. Khác biệt USER_, ALL_ và DBA_ views

- `USER_...`: đối tượng thuộc schema đang đăng nhập.
- `ALL_...`: đối tượng khả kiến theo quyền và phạm vi của phiên.
- `DBA_...`: góc nhìn quản trị rộng hơn; cần quyền phù hợp.

Trong CDB/PDB, phải kết nối đúng PDB hoặc ngữ cảnh quản trị tương ứng. Hai schema có cùng tên bảng ở hai PDB có thể có constraint khác nhau.

## 15. Thực hành từng bước: quan sát NULL với UNIQUE và CHECK

Hãy thực hiện trong một schema có quyền `CREATE TABLE`, quota phù hợp và không dùng bảng production. Các câu cố tình gây lỗi được **đặt trong comment** để bạn lựa chọn chạy từng lệnh và quan sát phản hồi; không nên chạy cả đoạn lỗi cùng lúc khi muốn theo dõi logic.

### Bước 1. Tạo bảng và UNIQUE một cột

```sql
CREATE TABLE lab_null_unique (
    id    NUMBER PRIMARY KEY,
    code  VARCHAR2(20),
    CONSTRAINT uq_lnu_code UNIQUE (code)
);
```

Chèn các hàng:

```sql
INSERT INTO lab_null_unique (id, code) VALUES (1, NULL);
INSERT INTO lab_null_unique (id, code) VALUES (2, NULL);
INSERT INTO lab_null_unique (id, code) VALUES (3, 'A');
INSERT INTO lab_null_unique (id, code) VALUES (4, 'B');

COMMIT;
```

Xem dữ liệu:

```sql
SELECT id, code
FROM lab_null_unique
ORDER BY id;
```

Hai hàng đầu có `CODE IS NULL` và vẫn tồn tại.

### Bước 2. Thử chèn giá trị không-NULL bị trùng

```sql
-- Bỏ comment để thử trong schema thực hành:
-- INSERT INTO lab_null_unique (id, code) VALUES (5, 'A');
```

Oracle từ chối bởi `UQ_LNU_CODE`; các hàng hợp lệ trước đó không vì thế mà bị xóa. Trong ứng dụng, cần xử lý `ORA-00001` để trả thông báo “mã đã tồn tại” hoặc logic tương đương.

### Bước 3. Tạo bảng khóa ghép

```sql
CREATE TABLE lab_null_composite (
    id NUMBER PRIMARY KEY,
    a  NUMBER,
    b  VARCHAR2(20),
    CONSTRAINT uq_lnc_pair UNIQUE (a, b)
);
```

Chèn:

```sql
INSERT INTO lab_null_composite VALUES (1, NULL, NULL);
INSERT INTO lab_null_composite VALUES (2, NULL, NULL);
INSERT INTO lab_null_composite VALUES (3, 10,   NULL);
INSERT INTO lab_null_composite VALUES (4, 20,   NULL);
INSERT INTO lab_null_composite VALUES (5, NULL, 'X');
INSERT INTO lab_null_composite VALUES (6, 10,   'X');

COMMIT;
```

Thử các tổ hợp trùng:

```sql
-- Mỗi lệnh dưới đây vi phạm UNIQUE ghép với dữ liệu đã có:
-- INSERT INTO lab_null_composite VALUES (7, 10, NULL);
-- INSERT INTO lab_null_composite VALUES (8, NULL, 'X');
-- INSERT INTO lab_null_composite VALUES (9, 10, 'X');
```

Quan sát: hai hàng `(NULL,NULL)` tồn tại, nhưng lặp `(10,NULL)` hoặc `(NULL,'X')` bị chặn. **Không kết luận từ phép `NULL = NULL` rằng Oracle phải cho phép mọi khóa ghép có NULL.**

### Bước 4. Kiểm tra CHECK với UNKNOWN

```sql
CREATE TABLE lab_null_check (
    id     NUMBER PRIMARY KEY,
    amount NUMBER,
    CONSTRAINT ck_lnc_amount CHECK (amount > 0)
);

INSERT INTO lab_null_check VALUES (1, 10);
INSERT INTO lab_null_check VALUES (2, NULL);

-- Lệnh này vi phạm CHECK:
-- INSERT INTO lab_null_check VALUES (3, -1);

COMMIT;
```

Hàng `amount=NULL` được phép vì biểu thức `amount > 0` là UNKNOWN. Nếu muốn không cho thiếu amount, hãy dùng `NOT NULL` trên cột hoặc thiết kế ràng buộc tương ứng theo yêu cầu nghiệp vụ.

### Bước 5. Xem metadata

```sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status
FROM user_constraints
WHERE table_name IN (
    'LAB_NULL_UNIQUE',
    'LAB_NULL_COMPOSITE',
    'LAB_NULL_CHECK'
)
ORDER BY table_name, constraint_name;

SELECT table_name,
       column_name,
       nullable
FROM user_tab_columns
WHERE table_name IN (
    'LAB_NULL_UNIQUE',
    'LAB_NULL_COMPOSITE',
    'LAB_NULL_CHECK'
)
ORDER BY table_name, column_id;
```

Ghi nhận rằng cột `CODE` ở bảng `LAB_NULL_UNIQUE` và `AMOUNT` ở bảng `LAB_NULL_CHECK` vẫn có thể nullable dù có constraint riêng.

### Bước 6. So sánh WHERE, GROUP BY và UNIQUE

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(code) AS rows_with_code
FROM lab_null_unique;
```

`COUNT(*)` đếm mọi hàng, còn `COUNT(code)` chỉ đếm giá trị `CODE` không-NULL. Vì thế hai phép đếm có thể khác nhau.

```sql
SELECT code, COUNT(*) AS row_count
FROM lab_null_unique
GROUP BY code
ORDER BY code;
```

`GROUP BY` tập hợp các hàng có `CODE IS NULL` vào cùng một nhóm phục vụ thống kê, dù `UNIQUE(code)` vẫn cho phép nhiều giá trị NULL. **Ngữ nghĩa nhóm NULL trong aggregate không đồng nghĩa ngữ nghĩa UNIQUE một cột.**

### Bước 7. Dọn bảng thực hành

Chỉ sau khi xác nhận đúng bảng do chính bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE lab_null_check PURGE;
DROP TABLE lab_null_composite PURGE;
DROP TABLE lab_null_unique PURGE;
```

`DROP TABLE ... PURGE` xóa object và dữ liệu, không dùng recycle bin để phục hồi theo hành vi lệnh; đây là DDL có commit ngầm. Không chạy lệnh dọn này trên bảng dùng chung.

## 16. Lỗi và hiện tượng thường gặp trong ứng dụng Java

### 16.1. `ORA-00001` không phải lúc nào cũng do PRIMARY KEY

`ORA-00001` có thể đến từ:

- Primary key bị trùng.
- Unique constraint bị vi phạm.
- Unique index, kể cả unique index trên biểu thức.

Khi xử lý lỗi, hãy xem **tên constraint/index** trong thông tin exception và metadata để biết quy tắc nào thực sự bị vi phạm; đừng vội kết luận một ID bị trùng khi lỗi đến từ `UNIQUE(email)`.

Ví dụ giao tiếp:

```text
Java API: POST /customers
    |
    v
INSERT INTO customers (id, email)
    |
    +-- Chưa trùng email -> DB cho phép
    |
    +-- Trùng email     -> ORA-00001
                             |
                             v
                       Ứng dụng ánh xạ
                       thành lỗi nghiệp vụ phù hợp
```

Việc kiểm tra trùng từ Java trước `INSERT` có thể giúp UX, nhưng **không thay thế được ràng buộc database** vì có hai request đồng thời.

### 16.2. `ORA-02290` khi CHECK sai

Nếu một hàng làm biểu thức `CHECK` trả về `FALSE`, Oracle thường báo:

```text
ORA-02290: check constraint (...) violated
```

Nếu mong rằng `CHECK (amount > 0)` sẽ chặn NULL mà nó không chặn, đó là lỗi **diễn đạt ràng buộc**, không phải Oracle bỏ qua kiểm tra.

### 16.3. `ORA-01400` khi NOT NULL sai

Khi cố `INSERT NULL` vào cột bắt buộc có giá trị, có thể gặp:

```text
ORA-01400: cannot insert NULL into (...)
```

Khi dùng `UPDATE` để đưa cột NOT NULL về NULL, Oracle có thể báo một lỗi liên quan như `ORA-01407`. Mã lỗi khác nhau theo hành động, nhưng quy tắc chung là không được lưu NULL vào cột đã xác định `NOT NULL`.

### 16.4. Java `null` không phải chuỗi `"null"`

Ví dụ sử dụng JDBC:

```java
String sql = "INSERT INTO customers (customer_id, email) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    if (email == null) {
        ps.setNull(2, java.sql.Types.VARCHAR);
    } else {
        ps.setString(2, email);
    }

    ps.executeUpdate();
}
```

`setNull(...)` truyền SQL `NULL`. Gửi `"null"` qua `setString` lại là chuỗi gồm bốn ký tự `n`, `u`, `l`, `l`, không phải giá trị thiếu. Với Oracle, chuỗi rỗng `""` được xử lý như NULL trong những kiểu ký tự thông thường hiện hành; đừng ngầm dựa vào chuyển đổi đó thay cho logic chuẩn hóa của ứng dụng.

Đoạn Java giả định `Connection`, `customerId`, `email` và transaction đã được cấu hình. Để phòng lỗi SQL injection, hãy **bind tham số**, không nối chuỗi input vào SQL.

### 16.5. ORM/Hibernate không tự sửa thiết kế NULL

Một annotation ở ứng dụng có thể yêu cầu nullable/unique, nhưng phải xác minh **DDL thực tế mà schema Oracle nhận được** và trạng thái constraint đang bật. Quan trọng hơn, một `@Column(unique=true)` trên cột nullable không biến nó thành NOT NULL; và một unique constraint trên hai cột nullable có các quy tắc Oracle đã nêu.

Khi dùng migration hoặc Hibernate, nên kiểm tra cả:

- DDL tạo bảng và constraint thực tế.
- Loại khóa đơn/ghép, nullable của từng thành phần.
- Quy tắc nullability từ validation ở API.
- Quy tắc unique index có biểu thức nếu nghiệp vụ cần tính duy nhất có điều kiện.
- Cách ứng dụng phân loại exception từ Oracle.

## 17. Một số thiết kế thường gặp và cách thể hiện

| Yêu cầu nghiệp vụ | Thiết kế ràng buộc tham khảo | Lưu ý về NULL |
|---|---|---|
| Email tùy chọn, nhưng đã có thì không trùng | `email VARCHAR2(...), UNIQUE(email)` | Nhiều email NULL được phép |
| Email bắt buộc và không trùng | `email ... NOT NULL, UNIQUE(email)` | `NOT NULL` giải quyết thiếu giá trị |
| Số lượng bắt buộc dương | `quantity NUMBER NOT NULL CHECK (quantity > 0)` | CHECK một mình cho phép UNKNOWN |
| Ngày kết thúc tùy chọn, nhưng nếu có phải sau bắt đầu | `start_at NOT NULL`, `CHECK (end_at IS NULL OR end_at > start_at)` | Diễn đạt rõ trường hợp thiếu ngày kết thúc |
| Cặp `(order_id,line_no)` định danh hàng | `PRIMARY KEY(order_id,line_no)` | Mọi thành phần không NULL |
| Mã duy nhất trong mỗi công ty, cả hai bắt buộc | `company_id NOT NULL`, `code NOT NULL`, `UNIQUE(company_id,code)` | Tránh partial-NULL |
| Mã duy nhất trong tenant khi mã đã được cấp; nhiều mã chưa cấp | Unique index có `CASE WHEN code IS NOT NULL THEN ... END` | Cần loại bỏ khóa toàn-NULL trong trường hợp code thiếu |
| Hai thành phần khóa ngoại cùng có hoặc cùng thiếu | `FOREIGN KEY(a,b)` + `CHECK ((a IS NULL AND b IS NULL) OR ...)` | FK một mình cho phép một phần NULL |
| Ít nhất một trong email hoặc phone | `CHECK (email IS NOT NULL OR phone IS NOT NULL)` | Xét thêm chuỗi dấu cách và tính hợp lệ |
| Chỉ một trong hai tham chiếu thanh toán | `CHECK ((a IS NOT NULL AND b IS NULL) OR (a IS NULL AND b IS NOT NULL))` | Không cho cả hai NULL |
| Duy nhất cho hàng ACTIVE | Function-based unique index qua `CASE` | Nhánh không áp dụng phải sinh toàn-NULL |

Các ví dụ là phương án kỹ thuật điển hình, không thay thế việc xây dựng **business rules** cụ thể. Trước khi chọn constraint, hãy thử liệt kê các tình huống đầu vào được phép và không được phép, bao gồm **từng cột NULL, tất cả NULL, giá trị trùng và giá trị có dấu cách/chuỗi rỗng**.

## 18. Các nhầm lẫn quan trọng cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| “`NULL = NULL` là TRUE.” | Sai | Trong SQL thông thường, kết quả là UNKNOWN |
| “`WHERE x = NULL` tìm được hàng NULL.” | Sai | Dùng `WHERE x IS NULL` |
| “`UNIQUE(x)` không cho phép hai NULL.” | Sai với Oracle | Nhiều NULL được phép trong ràng buộc một cột |
| “`UNIQUE(a,b)` có một cột NULL thì mọi hàng đều được phép lặp.” | Sai | Khóa ghép một phần NULL có thể vi phạm khi trùng phần không-NULL |
| “Hai hàng `(NULL,NULL)` vi phạm `UNIQUE(a,b)`.” | Sai | Khóa ghép toàn-NULL được phép lặp |
| “`PRIMARY KEY(a,b)` cho phép một thành phần NULL.” | Sai | Mọi thành phần PK phải NOT NULL |
| “`CHECK(x > 0)` sẽ từ chối NULL.” | Sai | NULL làm kết quả UNKNOWN, không bị CHECK từ chối |
| “`CHECK` và `WHERE` đều loại UNKNOWN giống nhau.” | Sai | CHECK chấp nhận UNKNOWN; WHERE chỉ chọn TRUE |
| “`CHECK(x IS NOT NULL)` có thể từ chối NULL.” | Đúng | `IS NOT NULL` trả FALSE khi x NULL |
| “Một foreign key ghép có một thành phần NULL vẫn bắt buộc khớp cha.” | Không đúng trong ngữ nghĩa Oracle thông thường | Cần `CHECK`/`NOT NULL` bổ sung khi cặp không được thiếu nửa vời |
| “`''` và `' '` giống nhau trong Oracle.” | Sai | Chuỗi rỗng được xử lý như NULL ở kiểu ký tự hiện hành; dấu cách là giá trị |
| “`COUNT(col)` và `COUNT(*)` luôn bằng nhau.” | Sai | `COUNT(col)` bỏ qua NULL |
| “Đã kiểm tra trùng bằng SELECT trước INSERT thì không cần UNIQUE.” | Sai | Có nguy cơ race condition khi giao dịch đồng thời |
| “Unique index trên biểu thức luôn đồng nghĩa có UNIQUE constraint khai báo.” | Sai | Hai cấu trúc liên quan nhưng metadata và ý nghĩa quản trị khác nhau |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Bảng `CUSTOMERS` có `UNIQUE(email)` và `email` nullable. Hai hàng có `email=NULL` có hợp lệ không?

**Trả lời:** Có. `UNIQUE` một cột trong Oracle cho phép nhiều NULL.

**Câu 2.** Nếu thêm `NOT NULL` vào cột `email` thì điều gì thay đổi?

**Trả lời:** Hàng thiếu email sẽ bị từ chối. `UNIQUE` tiếp tục kiểm tra giá trị không-NULL trùng nhau.

**Câu 3.** Bảng có `UNIQUE(tenant_id, code)` với cả hai cột nullable. Hai hàng `(NULL,NULL)` có hợp lệ không?

**Trả lời:** Có, Oracle cho phép nhiều hàng mà **toàn bộ** thành phần khóa unique ghép đều NULL.

**Câu 4.** Hai hàng `(10,NULL)` có được phép cùng tồn tại dưới `UNIQUE(tenant_id,code)` không?

**Trả lời:** Không trong ngữ nghĩa Oracle composite unique key thông thường: tổ hợp phần không-NULL trùng và vị trí NULL tương ứng có thể vi phạm ràng buộc.

**Câu 5.** Vì sao `CHECK (price > 0)` chưa đủ nếu mọi sản phẩm bắt buộc có giá?

**Trả lời:** `price=NULL` làm biểu thức trở thành UNKNOWN, được CHECK chấp nhận. Cần thêm `price NOT NULL`.

**Câu 6.** Nếu `start_date=NULL`, biểu thức `CHECK(end_date >= start_date)` sẽ trả gì và kết quả kiểm tra thế nào?

**Trả lời:** Phép so sánh là UNKNOWN, nên CHECK thường cho phép hàng. Nếu `start_date` bắt buộc, cần `NOT NULL` hoặc ràng buộc rõ tương đương.

**Câu 7.** `PRIMARY KEY(order_id,line_no)` cho phép `line_no=NULL` không?

**Trả lời:** Không. Mỗi thành phần của composite primary key bắt buộc khác NULL.

**Câu 8.** Khóa ngoại `(company_id,department_id)` có hàng `(10,NULL)`. Có thể cần thêm ràng buộc gì nếu nghiệp vụ không cho tham chiếu một nửa?

**Trả lời:** Dùng `CHECK` buộc hai thành phần cùng NULL hoặc cùng không NULL, hoặc đặt cả hai `NOT NULL` nếu quan hệ bắt buộc.

**Câu 9.** `CHECK (email IS NOT NULL OR phone IS NOT NULL)` chặn trường hợp nào?

**Trả lời:** Trường hợp cả email và phone đều NULL. Nó không tự kiểm tra độ dài, dấu cách hay định dạng liên hệ.

**Câu 10.** Một hệ thống muốn có nhiều hàng `(tenant_id=10,code=NULL)` nhưng khi code khác NULL phải duy nhất theo tenant. `UNIQUE(tenant_id,code)` có phù hợp không?

**Trả lời:** Không hoàn toàn với Oracle. Có thể dùng unique index biểu thức chỉ tạo khóa non-NULL khi `code` có giá trị, hoặc thiết kế bảng/ràng buộc khác đúng quy tắc.

**Câu 11.** Tại sao `SELECT COUNT(*)` và `SELECT COUNT(email)` khác nhau trong bảng nhiều email NULL?

**Trả lời:** `COUNT(*)` đếm mọi hàng; `COUNT(email)` bỏ qua các hàng có email NULL.

**Câu 12.** Khi gặp `ORA-00001`, làm sao biết khóa chính hay unique constraint nào bị vi phạm?

**Trả lời:** Xem tên constraint/index được Oracle báo, đối chiếu `USER_CONSTRAINTS`, `USER_CONS_COLUMNS` và metadata index của schema phù hợp. Không chỉ dựa vào việc lỗi là `ORA-00001`.

## 20. Kết luận

`NULL` trong Oracle là tình trạng **thiếu giá trị xác định**, không phải một số hoặc chuỗi để so sánh bằng `=`. Khi biểu thức chứa `NULL`, SQL thường vận hành theo **logic ba giá trị** `TRUE`, `FALSE`, `UNKNOWN`. Vì thế, **`WHERE` chỉ chọn TRUE**, còn **`CHECK` cho qua cả TRUE lẫn UNKNOWN**; muốn cột bắt buộc có giá trị, hãy viết `NOT NULL` một cách rõ ràng.

Với `UNIQUE`, **một cột nullable** có thể có nhiều hàng NULL. Với **khóa unique ghép**, Oracle cho phép nhiều hàng có **tất cả thành phần NULL**, nhưng **không được suy ra một thành phần NULL làm vô hiệu kiểm tra duy nhất**: các tổ hợp partial-NULL trùng phần khóa không-NULL có thể bị từ chối. **Khóa chính ghép** khác hẳn: mọi thành phần luôn phải khác NULL. **Khóa ngoại ghép** lại có quy tắc đặc biệt khi thành phần tham chiếu bị thiếu, nên có thể cần `CHECK` hoặc `NOT NULL` để tránh dữ liệu tham chiếu nửa vời.

Thiết kế ràng buộc tốt là **diễn đạt chính xác quy tắc nghiệp vụ ngay trong database**: cột nào được thiếu, cặp giá trị nào phải duy nhất, trạng thái nào hợp lệ và những tổ hợp NULL nào được phép. Khi cần duy nhất có điều kiện, có thể xét unique index biểu thức phù hợp; khi cần validation nhiều cột, kết hợp `CHECK` với `NOT NULL`. Cách tiếp cận này giúp Oracle bảo vệ dữ liệu cả khi nhiều request Java ghi đồng thời, thay vì chỉ phụ thuộc vào kiểm tra ở tầng ứng dụng.
