# Chú thích, dấu kết thúc câu lệnh và định dạng SQL

Một câu truy vấn SQL không chỉ gồm các từ khóa như `SELECT`, `FROM` hay `WHERE`. Khi viết và đọc SQL, bạn còn cần hiểu **chú thích (comment)**, **dấu chấm phẩy kết thúc câu lệnh** và **cách xuống dòng, thụt lề, căn chỉnh truy vấn**. Đây là các yếu tố giúp trình phân tích SQL nhận ra ranh giới câu lệnh, đồng thời giúp con người hiểu đúng logic, nhất là khi một tệp chứa nhiều truy vấn.

Bài học tập trung vào cú pháp và ngữ nghĩa chung của SQL, có đối chiếu những điểm khác nhau giữa PostgreSQL, MySQL, SQL Server và một số công cụ chạy SQL. Các ví dụ SQL cơ bản có thể đọc độc lập; ví dụ dùng bảng `employees`, `orders`… giả định đã có bảng tương ứng trong cơ sở dữ liệu.

## 1. Trước hết: SQL phân biệt nội dung có ý nghĩa và cách trình bày

Khi nhận một đoạn SQL, hệ quản trị cơ sở dữ liệu (DBMS) cần nhận diện **từ khóa**, **tên bảng/cột**, **toán tử**, **giá trị**, **chú thích** và **ranh giới câu lệnh**. Trong phần lớn trường hợp, nhiều dấu cách và các dòng trống nằm *giữa các thành phần cú pháp* chỉ có tác dụng trình bày.

Hai cách viết sau truyền đạt cùng một truy vấn:

```sql
SELECT id, full_name FROM employees WHERE is_active = TRUE;
```

```sql
SELECT
    id,
    full_name
FROM employees
WHERE is_active = TRUE;
```

Tuy nhiên, **không phải mọi khoảng trắng hay dấu câu đều có thể tùy tiện thêm, xóa hoặc chuyển vị trí**:

- Cần có cách phân tách các từ khóa và tên: `SELECT id` khác với chuỗi ký tự `SELECTid`.
- Khoảng trắng **bên trong chuỗi** là dữ liệu: `'Nguyen Van A'` khác `'NguyenVanA'`.
- Dấu phẩy phân tách biểu thức/cột; dấu ngoặc nhóm biểu thức hoặc chỉ ra tham số; dấu chấm phẩy phân tách hoặc kết thúc câu lệnh tùy ngữ cảnh.
- Chú thích khiến một phần văn bản **không còn được phân tích như SQL thông thường**; vì vậy vị trí dấu mở/đóng chú thích có thể làm thay đổi đoạn SQL thực sự được thực thi.
- Cách viết hoa/thường của *tên đối tượng* phụ thuộc DBMS và quy tắc về định danh có dấu nháy; đừng mặc định đổi chữ hoa/thường của mọi tên bảng, tên cột đều vô hại.

Để đọc chính xác một truy vấn, hãy phân biệt ba lớp: **mã SQL được thực thi**, **chú thích giải thích mã** và **quy ước định dạng nhằm dễ đọc**.

## 2. Viết chú thích trong SQL

Chú thích giúp người đọc hiểu tại sao truy vấn được viết như vậy, giải thích giả định dữ liệu, quy tắc nghiệp vụ hoặc quyết định thiết kế. Phần chú thích thông thường không tạo ra kết quả truy vấn.

### 2.1. Chú thích một dòng với `--`

Cú pháp phổ biến, thuộc SQL chuẩn, bắt đầu bằng **hai dấu gạch ngang** và kéo dài đến hết dòng:

```sql
-- Lấy danh sách nhân viên còn làm việc.
SELECT id, full_name
FROM employees
WHERE is_active = TRUE;
```

Có thể đặt sau một phần SQL trên cùng dòng:

```sql
SELECT
    id,         -- Khóa định danh của nhân viên.
    full_name   -- Họ tên để hiển thị.
FROM employees;
```

Ở ví dụ trên, mỗi dấu `--` khiến phần còn lại của **chính dòng đó** trở thành chú thích. Xuống dòng tiếp theo, SQL lại được phân tích bình thường.

**Lưu ý về khả năng tương thích:** MySQL yêu cầu dạng chú thích `--` phải có ký tự trắng hoặc ký tự điều khiển theo sau dấu gạch ngang thứ hai. Hãy luôn viết `-- ghi chú` (có dấu cách) để tránh khác biệt giữa các hệ quản trị. Không nhầm `--` của SQL với `//` trong Java/JavaScript: `//` không phải cú pháp chú thích một dòng SQL phổ quát.

### 2.2. Chú thích khối với `/* ... */`

Cặp ký hiệu `/*` và `*/` bao một đoạn chú thích, có thể chiếm một phần dòng hoặc nhiều dòng:

```sql
/*
  Báo cáo này chỉ lấy những đơn hàng đã thanh toán.
  Cột total_amount là số tiền của mỗi đơn hàng.
*/
SELECT order_id, total_amount
FROM orders
WHERE payment_status = 'PAID';
```

Chú thích khối cũng có thể nằm **giữa các thành phần của câu lệnh**:

```sql
SELECT order_id, /* mã đối soát */ total_amount
FROM orders;
```

Ví dụ trên vẫn lấy hai cột `order_id` và `total_amount`.

**Không lồng chú thích khối nếu cần tính tương thích giữa các DBMS.** PostgreSQL cho phép chú thích `/* ... */` lồng nhau, nhưng hành vi này không đồng nhất trên tất cả hệ quản trị. Cách an toàn, dễ đọc là dùng nhiều khối chú thích riêng biệt hoặc viết lại nội dung không cần lồng.

### 2.3. Chú thích có thể xuất hiện cạnh dữ liệu dạng chuỗi

Các dấu trông giống ký hiệu chú thích **bên trong chuỗi ký tự đã được mở đúng cách** chỉ là dữ liệu:

```sql
SELECT
    'A -- B' AS text_with_dashes,
    '/* ví dụ */' AS text_with_slashes,
    'Mục 1; Mục 2' AS text_with_semicolon;
```

Trong truy vấn này, `--`, `/* ... */` và `;` nằm trong các chuỗi, nên không tạo ra chú thích hay kết thúc sớm câu lệnh. Tương tự, khi một dấu nháy đơn thuộc chính nội dung chuỗi, cú pháp SQL thông dụng viết hai dấu nháy đơn liên tiếp để biểu diễn ký tự đó, chẳng hạn `'O''Brien'`.

Khả năng xác định đâu là chuỗi, chú thích hoặc định danh có trích dẫn thuộc về **bộ phân tích cú pháp của DBMS**. Vì vậy, việc tự tìm `--` hoặc `;` bằng cách cắt chuỗi văn bản đơn giản không đủ để phân tích SQL tổng quát.

### 2.4. Chú thích đúng chỗ và có ích

Một chú thích hiệu quả giải thích **lý do**, **ý nghĩa nghiệp vụ**, **giới hạn** hoặc **điều kiện đặc biệt**:

```sql
-- Không tính đơn đã hủy vì chưa ghi nhận doanh thu.
SELECT order_id, total_amount
FROM orders
WHERE order_status = 'COMPLETED';
```

So với chú thích lặp lại cú pháp:

```sql
-- Chọn order_id và total_amount từ bảng orders.
SELECT order_id, total_amount
FROM orders;
```

Chú thích thứ hai gần như không cung cấp thêm thông tin nào so với chính câu SQL.

Khi viết truy vấn nhiều bước, bạn có thể dùng chú thích để chia các phần logic:

```sql
-- Bước 1: Chọn giao dịch hợp lệ.
WITH valid_orders AS (
    SELECT customer_id, total_amount
    FROM orders
    WHERE order_status = 'COMPLETED'
)
-- Bước 2: Tính doanh thu của từng khách hàng.
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM valid_orders
GROUP BY customer_id;
```

Không đưa mật khẩu, token hay thông tin nhạy cảm vào chú thích, vì chúng có thể được lưu trong file SQL, lịch sử lệnh hoặc nhật ký truy vấn. Cũng tránh giữ lại quá nhiều đoạn SQL đã vô hiệu hóa bằng chú thích: chúng làm truy vấn khó đọc và dễ gây hiểu lầm về logic đang chạy.

### 2.5. Ngoại lệ theo hệ quản trị

Ngoài hai cách thông dụng trên, một số DBMS có cú pháp riêng:

| Hệ quản trị | Chú thích một dòng | Chú thích khối | Lưu ý |
|---|---|---|---|
| PostgreSQL | `-- ghi chú` | `/* ghi chú */` | Hỗ trợ chú thích khối lồng nhau |
| MySQL | `-- ghi chú` hoặc `# ghi chú` | `/* ghi chú */` | Với `--`, cần ký tự trắng/điều khiển ngay sau; `#` là mở rộng riêng |
| SQL Server | `-- ghi chú` | `/* ghi chú */` | Có hỗ trợ cú pháp khối lồng nhau theo T-SQL |
| SQLite | `-- ghi chú` | `/* ghi chú */` | Không nên dựa vào hành vi lồng khối |
| Oracle Database | `-- ghi chú` | `/* ghi chú */` | Một số dạng chú thích đặc biệt được dùng để truyền optimizer hint |

Ở một số hệ quản trị, các cú pháp **trông giống chú thích** có ý nghĩa đặc biệt: ví dụ Oracle có optimizer hint dạng `/*+ ... */`; MySQL có chú thích phiên bản dạng `/*! ... */` có thể chứa nội dung được xử lý đặc biệt. Không giả định mọi đoạn giữa `/*` và `*/` đều là văn bản không ảnh hưởng đến hành vi trong mọi SQL dialect.

## 3. Dấu chấm phẩy `;` và ranh giới câu lệnh

Trong script SQL, `;` thường đánh dấu **kết thúc một câu lệnh**, giúp DBMS hoặc công cụ chạy SQL nhận biết câu tiếp theo bắt đầu từ đâu:

```sql
SELECT 1 AS first_value;
SELECT 2 AS second_value;
```

Đây là hai câu lệnh riêng: câu đầu trả về giá trị `1`, câu sau trả về giá trị `2`. Viết chúng trên cùng một dòng vẫn có thể đúng nếu công cụ hỗ trợ chạy nhiều câu lệnh:

```sql
SELECT 1 AS first_value; SELECT 2 AS second_value;
```

Tuy nhiên, mỗi câu trên một dòng hoặc một khối riêng sẽ dễ quan sát, kiểm tra và sửa lỗi hơn.

### 3.1. Khi nào phải viết dấu chấm phẩy?

Quy tắc thực hành dễ nhớ:

- **Trong file script có nhiều câu lệnh:** kết thúc mỗi câu bằng `;` trừ khi công cụ/ngôn ngữ thủ tục yêu cầu cách khác.
- **Trong terminal tương tác:** nhiều client, chẳng hạn `psql`, chờ cho đến khi gặp dấu kết thúc để gửi câu lệnh SQL hoàn chỉnh. Một số client còn có lệnh thực thi riêng.
- **Trong GUI:** khi chọn và chạy một câu lệnh riêng lẻ, một số công cụ có thể gửi câu đó dù bạn chưa gõ `;`. Điều này là hành vi của **client/editor**, không phải lý do để bỏ dấu kết thúc trong script.
- **Trong ứng dụng:** API hoặc driver có thể yêu cầu chỉ một câu lệnh cho một lần gọi và có quy định riêng về dấu `;`. Ví dụ, khi dùng prepared statement, nên gửi đúng một câu SQL theo yêu cầu của driver, không ghép nhiều câu lệnh thành chuỗi.

Viết dấu `;` ở cuối câu lệnh SQL độc lập là thói quen hữu ích khi học SQL; khi dùng stored procedure, batch script hoặc công cụ đặc thù, cần hiểu thêm quy tắc của môi trường đang chạy.

### 3.2. Đặt dấu kết thúc đúng vị trí

Không đặt `;` giữa các mệnh đề của **cùng một câu lệnh**:

```sql
-- Sai: SELECT đã bị kết thúc trước mệnh đề WHERE.
SELECT id, full_name
FROM employees;
WHERE is_active = TRUE;
```

```sql
-- Đúng: WHERE vẫn thuộc cùng một câu SELECT.
SELECT id, full_name
FROM employees
WHERE is_active = TRUE;
```

Dấu kết thúc cũng phải nằm **ngoài chuỗi ký tự và ngoài chú thích** nếu bạn muốn nó phân tách câu lệnh:

```sql
SELECT 'Dấu ; ở đây chỉ là dữ liệu' AS description;
-- Dấu ; ở đây nằm trong chú thích, không tạo lệnh mới.
SELECT 3 AS count_value;
```

Đừng nhầm `;` với `,`: dấu phẩy phân cách cột hoặc biểu thức trong danh sách, còn dấu chấm phẩy kết thúc cả câu lệnh.

### 3.3. Chú thích một dòng và dấu `;`

Vị trí chú thích có thể vô tình làm dấu chấm phẩy **không còn được nhận diện**:

```sql
-- Dễ gây lỗi trong script/terminal: dấu ; bị chú thích cùng phần sau.
SELECT id FROM employees -- lấy mã nhân viên;
```

Trong ví dụ trên, phần `-- lấy mã nhân viên;` là chú thích; dấu `;` nằm cuối dòng cũng thuộc chú thích. Một terminal đang đợi dấu chấm phẩy có thể tiếp tục chờ đầu vào.

Cách sửa:

```sql
-- Đặt dấu kết thúc trước chú thích cuối dòng.
SELECT id FROM employees; -- Lấy mã nhân viên.
```

Hoặc giữ `;` ở cuối dòng SQL thực thi:

```sql
SELECT id
FROM employees -- Chỉ lấy danh sách ID.
;
```

Dạng thứ hai có thể chạy được nhưng kém tự nhiên; ưu tiên đặt dấu chấm phẩy ngay sau biểu thức SQL cuối cùng.

### 3.4. `;` khác với `COMMIT`

Dấu `;` chỉ **kết thúc câu lệnh**. Nó không tự động đồng nghĩa với **xác nhận giao dịch (commit)**:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Đây là ví dụ minh họa một giao dịch trong môi trường có cú pháp tương ứng như PostgreSQL; giả định bảng `accounts` đã tồn tại. Hai câu `UPDATE` đều có dấu `;`, nhưng thay đổi trong giao dịch được xác nhận bằng `COMMIT`. Trạng thái auto-commit, cú pháp bắt đầu giao dịch và hành vi commit cụ thể tùy DBMS/client. Đừng chạy ví dụ thay đổi số dư trên dữ liệu thực khi chưa có môi trường thử nghiệm.

## 4. Phân biệt câu lệnh SQL với lệnh điều khiển của công cụ

Một số ký hiệu có vẻ là dấu kết thúc SQL nhưng thực tế do **client** nhận biết. Đây là nguyên nhân hay gặp khi chuyển cùng một script giữa terminal, GUI và driver ứng dụng.

| Công cụ/ngữ cảnh | Ví dụ | Vai trò |
|---|---|---|
| SQL thông thường | `SELECT 1;` | `;` phân tách/kết thúc câu lệnh |
| SQL Server Management Studio hoặc `sqlcmd` | `GO` trên dòng riêng | Lệnh **phân tách batch của client**, không phải câu lệnh T-SQL gửi trực tiếp đến engine |
| MySQL command-line client | `DELIMITER //` | Thay **ký hiệu kết thúc do client dùng** khi nhập cấu trúc có dấu `;` bên trong |
| SQL*Plus/SQLcl của Oracle | `/` trên dòng riêng | Yêu cầu client thực thi nội dung SQL/PL/SQL trong bộ đệm theo quy tắc của công cụ |
| PostgreSQL `psql` | `\g` | Gửi bộ đệm truy vấn hiện tại đến server; là **meta-command** của `psql` |

### 4.1. Tại sao SQL Server thường có `GO`?

Ví dụ trong SSMS hoặc `sqlcmd`:

```sql
SELECT 1 AS first_value;
GO

SELECT 2 AS second_value;
GO
```

`GO` được công cụ hiểu là mốc kết thúc batch, sau đó công cụ gửi từng batch đến SQL Server. `GO` **không phải câu lệnh SQL chuẩn** và không thể mặc định gửi nguyên văn qua JDBC/ODBC như một câu truy vấn. Nếu chuyển script sang công cụ khác, phải điều chỉnh theo khả năng xử lý batch của công cụ đó.

### 4.2. Vì sao MySQL có lệnh `DELIMITER`?

Một số định nghĩa thủ tục có nhiều câu SQL bên trong. Nếu MySQL CLI luôn coi `;` đầu tiên là kết thúc phần nhập, nó có thể gửi một định nghĩa thủ tục chưa đầy đủ. Vì thế có thể tạm thay dấu kết thúc của **client**:

```sql
DELIMITER //

CREATE PROCEDURE show_message()
BEGIN
    SELECT 'Hello SQL' AS message;
END//

DELIMITER ;

CALL show_message();
```

Trong ví dụ này, `;` bên trong thủ tục là cú pháp của các lệnh trong thân thủ tục; `//` tạm thời kết thúc toàn bộ lệnh `CREATE PROCEDURE` trong MySQL CLI. `DELIMITER` không phải câu SQL để gửi thẳng đến MySQL server. Các GUI hoặc công cụ migration có thể có cách xử lý script thủ tục riêng.

### 4.3. Dấu `/` trong công cụ Oracle

Trong SQL*Plus/SQLcl, một khối PL/SQL có thể được thực thi bằng dấu `/` trên một dòng riêng:

```sql
BEGIN
    NULL;
END;
/
```

Dấu `;` kết thúc các thành phần bên trong khối PL/SQL; `/` là lệnh của client để thực thi khối đã nhập. Không áp dụng tùy tiện `/` sang PostgreSQL/MySQL hoặc API gửi SQL trực tiếp.

**Nguyên tắc:** hãy xác định đoạn đang viết là **SQL gửi cho DBMS**, **khối ngôn ngữ thủ tục**, hay **script dành riêng cho một client**. Không giả định mọi ký hiệu kết thúc đều có cùng nghĩa trên các môi trường.

## 5. Định dạng SQL để dễ đọc và hạn chế nhầm lẫn

Trình bày rõ ràng đặc biệt hữu ích khi truy vấn có nhiều bảng, nhiều điều kiện, phép tổng hợp và truy vấn lồng nhau. Định dạng thông thường không thay đổi kết quả SQL, nhưng giúp người đọc dễ thấy logic cần kiểm tra.

### 5.1. Viết từ khóa nổi bật, tên đối tượng nhất quán

Có thể viết từ khóa SQL bằng chữ hoa để phân biệt với tên bảng/cột:

```sql
SELECT employee_id, full_name
FROM employees
WHERE department_id = 10
ORDER BY full_name;
```

Cách viết `SELECT`, `FROM`, `WHERE`, `ORDER BY` bằng chữ hoa là **quy ước trình bày**, không phải yêu cầu bắt buộc của hầu hết DBMS. Tên bảng và tên cột có thể theo `snake_case` như `employee_id`, hoặc theo quy ước dự án. Hãy nhất quán trong cùng codebase; tránh tự đổi chữ hoa/thường của định danh được đặt trong dấu nháy vì một số DBMS xử lý chúng theo cách khác định danh thông thường.

### 5.2. Mỗi mệnh đề chính ở một dòng; danh sách cột dễ quét

Dạng một dòng khó quan sát:

```sql
select e.employee_id,e.full_name,d.department_name from employees e left join departments d on e.department_id=d.department_id where e.is_active=true order by e.full_name;
```

Cùng logic, được định dạng lại:

```sql
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM employees AS e
LEFT JOIN departments AS d
    ON e.department_id = d.department_id
WHERE e.is_active = TRUE
ORDER BY e.full_name;
```

Dạng này giúp nhanh chóng xác định:

- **`SELECT`**: các cột sẽ trả về;
- **`FROM`** và **`JOIN ... ON`**: nguồn dữ liệu và cách nối;
- **`WHERE`**: điều kiện lọc bản ghi;
- **`ORDER BY`**: thứ tự trình bày kết quả.

Cách thụt lề 2 hoặc 4 dấu cách đều có thể dùng; điều quan trọng là **nhất quán trong cùng dự án**. Khi nhiều bảng có cột trùng tên, đặt bí danh bảng (`e`, `d`) và dùng tiền tố để chỉ rõ cột thuộc bảng nào.

### 5.3. Tách điều kiện dài và làm rõ ưu tiên toán tử

Các điều kiện phức tạp nên được xuống dòng theo từng ý:

```sql
SELECT
    employee_id,
    full_name
FROM employees
WHERE is_active = TRUE
  AND department_id IN (10, 20)
  AND hired_at >= '2026-01-01';
```

Với `AND` và `OR`, dấu ngoặc có thể quyết định **ý nghĩa logic**:

```sql
SELECT employee_id, full_name
FROM employees
WHERE is_active = TRUE
  AND (
      department_id = 10
      OR department_id = 20
  );
```

Câu trên chỉ lấy nhân viên đang hoạt động thuộc phòng 10 **hoặc** 20. Nếu bỏ cặp ngoặc:

```sql
WHERE is_active = TRUE
  AND department_id = 10
   OR department_id = 20
```

…thì theo thứ tự ưu tiên thông thường (`AND` trước `OR`), truy vấn cũng có thể lấy nhân viên **không còn hoạt động** thuộc phòng 20. **Thụt lề không thay thế dấu ngoặc**; hãy dùng dấu ngoặc để diễn đạt rõ nhóm điều kiện.

### 5.4. Tổ chức truy vấn tổng hợp

Đối với truy vấn báo cáo, đặt `GROUP BY`, `HAVING`, `ORDER BY` thành các khối riêng:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE order_status = 'COMPLETED'
GROUP BY customer_id
HAVING SUM(total_amount) >= 1000000
ORDER BY revenue DESC;
```

`WHERE` lọc hàng trước bước nhóm, còn `HAVING` lọc các nhóm đã hình thành. Cách định dạng này giúp thấy thứ tự logic của các mệnh đề, nhưng **không tự sửa được lỗi dùng sai mệnh đề**.

### 5.5. Làm rõ cấu trúc truy vấn con và CTE

Một **common table expression (CTE)** có thể chia một truy vấn lớn thành các bước có tên dễ đọc:

```sql
WITH completed_orders AS (
    SELECT
        customer_id,
        total_amount
    FROM orders
    WHERE order_status = 'COMPLETED'
),
customer_revenue AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM completed_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    revenue
FROM customer_revenue
WHERE revenue >= 1000000
ORDER BY revenue DESC;
```

Tên CTE mô tả mục đích của từng bước; dấu phẩy ngăn cách các CTE, còn `;` chỉ xuất hiện ở cuối **toàn bộ câu lệnh**. Đừng nhầm dấu phẩy giữa hai CTE với dấu kết thúc câu lệnh.

### 5.6. Không để định dạng che giấu hành vi truy vấn

Một số thói quen giúp câu SQL dễ xem xét hơn:

- **Chỉ lấy cột cần dùng** khi có thể, thay vì `SELECT *` trong truy vấn ứng dụng cần duy trì lâu dài.
- **Dùng bí danh có nghĩa** cho cột tính toán, ví dụ `SUM(total_amount) AS revenue`.
- **Đặt dấu phẩy và dấu ngoặc theo một quy ước ổn định**; giữ danh sách cột ngắn trên một dòng, tách dòng khi dài.
- **Để trống một dòng giữa các câu SQL độc lập** trong script, nhất là các lệnh tạo bảng, thêm dữ liệu và truy vấn.
- **Giữ dấu `;` ở cuối câu lệnh** và đặt chú thích gần phần logic cần giải thích.
- **Không nhầm định dạng với tối ưu hóa**: truy vấn đẹp mắt chưa chắc nhanh hơn. Hiệu năng còn phụ thuộc cấu trúc bảng, chỉ mục, số lượng dữ liệu, thống kê và kế hoạch thực thi.

## 6. Những lỗi dễ mắc khi kết hợp chú thích và định dạng

### Lỗi 1: Dấu `;` bị biến thành một phần của chú thích

```sql
-- Không nên
SELECT full_name FROM employees -- danh sách nhân viên;
```

```sql
-- Nên
SELECT full_name
FROM employees; -- Danh sách nhân viên.
```

### Lỗi 2: Chú thích vô tình che một cột, để lại dấu phẩy thừa

```sql
-- Sai: cột full_name đã bị chú thích, chỉ còn dấu phẩy sau id.
SELECT
    id,
    -- full_name
FROM employees;
```

```sql
-- Đúng khi chỉ lấy id.
SELECT
    id
FROM employees;
```

Khi tạm bỏ một cột hoặc điều kiện, xem lại dấu phẩy, toán tử `AND`/`OR` và dấu ngoặc còn lại.

### Lỗi 3: Thực thi sai vì đặt `;` quá sớm

```sql
-- Sai: WHERE không còn thuộc SELECT.
SELECT *
FROM employees;
WHERE department_id = 10;
```

```sql
-- Đúng.
SELECT *
FROM employees
WHERE department_id = 10;
```

### Lỗi 4: Nghĩ xuống dòng tự kết thúc một câu SQL

```sql
SELECT 1 AS first_value
SELECT 2 AS second_value;
```

Xuống dòng **không tự động** thay dấu kết thúc. Hai câu `SELECT` riêng cần được tách thích hợp:

```sql
SELECT 1 AS first_value;
SELECT 2 AS second_value;
```

### Lỗi 5: Sao chép lệnh của client sang hệ quản trị khác

Ví dụ `GO` của SSMS hay `DELIMITER` của MySQL CLI không phải SQL dùng chung cho mọi công cụ. Script chạy trong GUI, migration tool hoặc chương trình Java có thể cần điều chỉnh cơ chế phân tách và gửi câu lệnh.

### Lỗi 6: Tự ghép SQL bằng chuỗi và cố nhận diện dấu `;`/chú thích

Trong ứng dụng, đừng tự tách câu SQL chỉ bằng các thao tác đơn giản như `split(";")` hoặc loại bỏ chuỗi bắt đầu bằng `--`: các ký tự đó có thể xuất hiện trong chuỗi ký tự, chú thích khối và cấu trúc thủ tục. Với dữ liệu đầu vào của người dùng, ưu tiên **truy vấn tham số hóa** (prepared statement) theo API tương ứng thay vì nối trực tiếp dữ liệu vào SQL; đây là vấn đề về tính đúng đắn và an toàn, ngoài yêu cầu định dạng.

## 7. Thực hành: đọc, chú thích và định dạng một đoạn SQL

### Bài 1: Phân biệt ký tự trong dữ liệu và ký hiệu điều khiển

Đọc rồi chạy trong môi trường hỗ trợ `SELECT` không có `FROM`, chẳng hạn PostgreSQL, MySQL hoặc SQLite:

```sql
-- Kiểm tra dấu chú thích và dấu kết thúc.
SELECT
    'Tầng 2; phòng A -- nội bộ' AS location,
    '/* không phải chú thích */' AS note,
    7 AS seat_count; -- Kết thúc câu lệnh tại dấu ; trước ghi chú này.
```

Tự trả lời:

1. Kết quả có mấy cột?
2. Dấu `;` bên trong giá trị `location` có kết thúc câu SQL không?
3. Vì sao phần `-- nội bộ` trong chuỗi vẫn hiển thị trong kết quả?

**Đáp án:** có 3 cột; dấu `;` và `--` trong dấu nháy đơn là nội dung chuỗi; dấu `;` thực sự kết thúc câu lệnh nằm sau biểu thức `7 AS seat_count`.

### Bài 2: Sửa dấu kết thúc sai

Đoạn sau có lỗi về ranh giới câu lệnh:

```sql
SELECT id, full_name;
FROM employees
WHERE department_id = 10;
```

Hãy viết lại thành một câu lệnh duy nhất, giữ điều kiện lọc và có dấu kết thúc đúng vị trí:

```sql
SELECT
    id,
    full_name
FROM employees
WHERE department_id = 10;
```

### Bài 3: Định dạng truy vấn tổng hợp

Hãy đọc phiên bản gọn sau và chia thành các khối rõ ràng:

```sql
select c.customer_id,c.customer_name,sum(o.total_amount) as revenue from customers c join orders o on o.customer_id=c.customer_id where o.order_status='COMPLETED' group by c.customer_id,c.customer_name having sum(o.total_amount)>=1000000 order by revenue desc;
```

Một cách trình bày:

```sql
-- Tìm khách hàng có tổng doanh thu từ đơn hoàn tất đạt ngưỡng.
SELECT
    c.customer_id,
    c.customer_name,
    SUM(o.total_amount) AS revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'COMPLETED'
GROUP BY
    c.customer_id,
    c.customer_name
HAVING SUM(o.total_amount) >= 1000000
ORDER BY revenue DESC;
```

Các tên bảng/cột trong bài 2 và 3 là ví dụ; cần tạo đúng lược đồ hoặc đổi tên cho phù hợp nếu thực hành trên database khác. Khi định dạng, hãy so sánh **điều kiện nối bảng**, **điều kiện lọc** và **biểu thức tính tổng** để chắc chắn bạn chỉ đổi bố cục, không vô tình đổi nghĩa của truy vấn.

### Bài 4: Chọn lời chú thích hữu ích

Cho truy vấn:

```sql
SELECT order_id
FROM orders
WHERE order_status = 'COMPLETED';
```

Trong hai chú thích sau, chú thích nào cung cấp ngữ cảnh tốt hơn?

- A: `-- SELECT từ bảng orders.`
- B: `-- Chỉ đối soát các đơn hoàn tất; đơn bị hủy không phát sinh doanh thu ghi nhận.`

**Đáp án:** B, vì nêu lý do nghiệp vụ của điều kiện lọc. Khi giải thích những giả định có thể thay đổi, nên xác nhận chúng với quy định nghiệp vụ thực tế.

## 8. Ghi nhớ khi đọc và viết script SQL

| Thành phần | Mục đích chính | Điều cần nhớ |
|---|---|---|
| `-- chú thích` | Giải thích đến hết dòng | Không để `;` cần thiết nằm phía sau `--` |
| `/* chú thích */` | Chú thích một đoạn hoặc nhiều dòng | Tránh lồng khối nếu cần SQL đa hệ quản trị |
| `;` | Phân tách/kết thúc câu SQL | Không đặt giữa `SELECT` và các mệnh đề thuộc chính câu đó |
| Xuống dòng, thụt lề | Giúp người đọc hiểu cấu trúc | Thường không kết thúc câu SQL; không thay thế ngoặc nhóm logic |
| Dấu ngoặc `( )` | Nhóm biểu thức, tham số, truy vấn con | Có thể làm thay đổi ý nghĩa khi kết hợp `AND` và `OR` |
| `GO`, `DELIMITER`, `/` | Điều khiển chạy script ở client riêng | Không xem là các câu lệnh SQL phổ quát |

Một đoạn SQL dễ bảo trì cần có **ranh giới câu lệnh rõ ràng**, **chú thích đúng mục đích** và **cách trình bày nhất quán**. Khi chuyển từ một DBMS hoặc công cụ thực thi sang công cụ khác, hãy kiểm tra quy tắc dấu kết thúc và các lệnh dành riêng cho client trước khi chạy toàn bộ script.

