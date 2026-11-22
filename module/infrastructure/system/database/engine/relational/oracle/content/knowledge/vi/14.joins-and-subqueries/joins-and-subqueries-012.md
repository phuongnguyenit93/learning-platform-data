# LATERAL, CROSS APPLY và OUTER APPLY theo phiên bản hỗ trợ trong Oracle

## 1. Khi nào một truy vấn con cần nhìn thấy hàng của truy vấn bên ngoài?

Một báo cáo có thể cần lấy **hai đơn hàng mới nhất của từng khách hàng**, tìm mức lương cao nhất trong từng phòng ban, hoặc tính một nhóm thông tin phụ thuộc vào từng hàng của bảng đang truy vấn. Truy vấn con trong `FROM` thông thường là một inline view độc lập: nó không thể tùy ý tham chiếu alias của bảng đứng bên cạnh. Oracle cung cấp các cấu trúc **`LATERAL`**, **`CROSS APPLY`** và **`OUTER APPLY`** để diễn đạt loại truy vấn có tương quan đó.

Ví dụ yêu cầu: với mỗi khách hàng, lấy tối đa hai đơn hàng gần nhất:

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) recent;
```

Subquery bên phải `CROSS APPLY` sử dụng `c.customer_id` từ bảng đứng trước. Nó được đánh giá trong ngữ cảnh của từng khách hàng và có thể trả về **không hàng nào, một hàng hoặc nhiều hàng**.

Ba khái niệm có liên hệ chặt chẽ:

- **`LATERAL`** cho phép inline view tham chiếu các bảng xuất hiện trước nó trong mệnh đề `FROM`.
- **`CROSS APPLY`** kết hợp bảng bên trái với một nguồn dữ liệu tương quan bên phải theo hành vi tương tự inner lateral join.
- **`OUTER APPLY`** cũng cho phép tương quan, nhưng giữ hàng bên trái ngay cả khi nguồn bên phải không trả về hàng nào; các cột bên phải khi đó được mở rộng thành NULL.

Bài học thuộc chương **JOIN và truy vấn con**, tập trung vào cú pháp, phạm vi tương quan, khác biệt giữa `CROSS APPLY` và `OUTER APPLY`, phiên bản Oracle hỗ trợ, các mẫu top-N theo từng nhóm, cách thay thế trên phiên bản cũ và lưu ý hiệu năng.

## 2. Phiên bản Oracle hỗ trợ

Oracle hỗ trợ **lateral inline view, `CROSS APPLY` và `OUTER APPLY` từ Oracle Database 12c Release 1 (12.1)**. Các phiên bản 12c về sau và các dòng hiện đại tiếp tục hỗ trợ những cấu trúc này.

| Phiên bản | `LATERAL` | `CROSS APPLY` / `OUTER APPLY` | Ghi chú |
|---|---|---|---|
| Oracle 11g và cũ hơn | Không hỗ trợ cú pháp Oracle này | Không hỗ trợ | Dùng correlated subquery, analytic function hoặc join thay thế |
| Oracle 12c Release 1 (12.1) | Có | Có | Cũng có row limiting clause như `FETCH FIRST` |
| Oracle 12c Release 2 (12.2) | Có | Có | Tiếp tục hỗ trợ |
| Oracle 18c, 19c và các bản mới hơn | Có | Có | Kiểm tra thêm các hạn chế cụ thể của release/patch nếu dùng cú pháp nâng cao |

Không nên chỉ dựa vào tên sản phẩm “Oracle” để kết luận câu SQL sẽ chạy. Ứng dụng có thể kết nối nhiều môi trường với phiên bản khác nhau, hoặc một hệ thống có database mới nhưng công cụ kiểm thử lại dùng database cũ.

### 2.1. Kiểm tra phiên bản database

Với quyền đọc view phù hợp:

```sql
SELECT product, version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Một số môi trường cho phép xem thêm:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

`V$VERSION` có thể yêu cầu quyền truy cập view hệ thống. Nếu không có quyền, dùng `PRODUCT_COMPONENT_VERSION` hoặc hỏi quản trị viên database.

### 2.2. Lưu ý về `FETCH FIRST`

Ví dụ top-N trong bài dùng:

```sql
ORDER BY order_date DESC
FETCH FIRST 2 ROWS ONLY
```

Row limiting clause `FETCH FIRST` cũng được Oracle hỗ trợ từ 12c Release 1. Nếu hệ thống cũ hơn, không thể chỉ thay `CROSS APPLY` bằng một cú pháp tương tự mà vẫn giữ `FETCH FIRST`; hãy dùng `ROW_NUMBER()` hoặc cách phân trang tương thích phiên bản.

## 3. Inline view thông thường và giới hạn tương quan

Inline view là một truy vấn con xuất hiện trong `FROM`:

```sql
SELECT c.customer_id,
       x.order_count
FROM customers c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
  ON x.customer_id = c.customer_id;
```

Inline view `x` tự tính số đơn theo `customer_id`; nó không cần tham chiếu alias `c` ở truy vấn bên ngoài.

Nếu cố viết:

```sql
-- Không phải inline view thông thường có thể tham chiếu tùy ý alias c:
SELECT c.customer_id, x.order_id
FROM customers c
JOIN (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
) x
  ON 1 = 1;
```

trên cách viết inline view thông thường, tham chiếu `c.customer_id` từ truy vấn ngoài không được chấp nhận theo phạm vi tên thông thường. Đây là nhu cầu mà lateral correlation giải quyết.

Với `LATERAL` hoặc `APPLY`, inline view bên phải được phép nhìn thấy các bảng đứng trước nó trong `FROM`.

## 4. `LATERAL`: inline view có thể tham chiếu bảng đứng trước

### 4.1. Cú pháp khái quát

Một cách viết Oracle thường gặp:

```sql
SELECT ...
FROM left_table l,
     LATERAL (
         SELECT ...
         FROM right_table r
         WHERE r.key = l.key
     ) x;
```

`LATERAL` đặt trước subquery trong `FROM`. Bên trong subquery, alias `l` của bảng đứng trước có thể được tham chiếu như một biến tương quan.

### 4.2. Ví dụ với khách hàng và đơn hàng

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
     ) x;
```

Với mỗi khách hàng, subquery tìm các đơn hàng thuộc khách hàng đó. Nếu khách hàng có ba đơn hàng, truy vấn có thể trả ba hàng cho khách hàng ấy.

Vì ví dụ dùng cú pháp nối kiểu cross trong `FROM`, khách hàng không có đơn hàng phù hợp sẽ không xuất hiện. Đây là hành vi inner/cross lateral join.

### 4.3. LATERAL với top-N cho từng khách hàng

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 2 ROWS ONLY
     ) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Điểm quan trọng là `FETCH FIRST 2 ROWS ONLY` nằm **bên trong truy vấn tương quan**. Giới hạn hai hàng được áp dụng cho kết quả đơn hàng của từng khách hàng, không phải cho toàn bộ kết quả sau khi nối.

`ORDER BY` ngoài cùng sắp xếp kết quả trả về cho người dùng. Không dựa vào thứ tự bên trong subquery để bảo đảm thứ tự cuối cùng của toàn bộ SELECT.

### 4.4. Phạm vi tham chiếu

Trong cấu trúc:

```sql
FROM customers c,
     LATERAL (
         SELECT ...
         WHERE orders.customer_id = c.customer_id
     ) x
```

subquery lateral có thể tham chiếu `c` vì `customers c` đã xuất hiện trước nó. Không viết subquery ở trước bảng mà nó cần tham chiếu rồi kỳ vọng alias phía sau sẽ tự khả kiến.

Hãy đặt bảng cung cấp giá trị tương quan ở bên trái và lateral view ở bên phải. Điều này cũng làm rõ luồng dữ liệu khi người khác đọc truy vấn.

## 5. `CROSS APPLY`: phép kết hợp tương quan dạng inner

### 5.1. Cú pháp

```sql
SELECT ...
FROM left_table l
CROSS APPLY (
    SELECT ...
    FROM right_table r
    WHERE r.key = l.key
) x;
```

`CROSS APPLY` cho phép nguồn bên phải tham chiếu alias từ nguồn bên trái. Kết quả có ngữ nghĩa gần với một inner lateral join:

- Nếu subquery bên phải trả nhiều hàng, hàng bên trái được lặp tương ứng với từng hàng phải.
- Nếu subquery bên phải trả đúng một hàng, có một hàng kết quả cho hàng trái đó.
- Nếu subquery bên phải không trả hàng nào, hàng bên trái không xuất hiện trong kết quả.

### 5.2. Ví dụ đơn giản

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id
FROM customers c
CROSS APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
) recent;
```

Khách hàng không có đơn hàng bị loại. Khách hàng có nhiều đơn hàng tạo ra nhiều hàng kết quả.

### 5.3. Top 2 đơn hàng gần nhất

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC NULLS LAST,
             o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) recent
ORDER BY c.customer_id,
         recent.order_date DESC NULLS LAST,
         recent.order_id DESC;
```

Nếu khách hàng không có đơn hàng, không có hàng tương ứng trong kết quả. Đây là khác biệt quan trọng với `OUTER APPLY`.

### 5.4. APPLY có thể trả nhiều cột và nhiều hàng

Subquery bên phải không bị giới hạn ở một giá trị scalar:

```sql
SELECT d.department_id,
       d.department_name,
       top_emp.employee_id,
       top_emp.salary
FROM departments d
CROSS APPLY (
    SELECT e.employee_id, e.salary
    FROM employees e
    WHERE e.department_id = d.department_id
    ORDER BY e.salary DESC NULLS LAST,
             e.employee_id
    FETCH FIRST 3 ROWS ONLY
) top_emp;
```

Mỗi phòng ban có thể tạo tối đa ba hàng, tương ứng ba nhân viên có lương cao nhất trong phòng ban đó. Phòng ban không có nhân viên phù hợp sẽ bị loại vì dùng `CROSS APPLY`.

## 6. `OUTER APPLY`: giữ hàng bên trái khi bên phải không có kết quả

### 6.1. Cú pháp

```sql
SELECT ...
FROM left_table l
OUTER APPLY (
    SELECT ...
    FROM right_table r
    WHERE r.key = l.key
) x;
```

`OUTER APPLY` có ngữ nghĩa gần với **left outer lateral join**:

- Nếu subquery trả hàng, kết quả ghép theo từng hàng.
- Nếu subquery không trả hàng, Oracle vẫn giữ hàng bên trái.
- Các cột lấy từ subquery bên phải được trả về NULL khi không có hàng tương ứng.

### 6.2. Ví dụ giữ tất cả khách hàng

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) recent
ORDER BY c.customer_id;
```

Kết quả:

| Khách hàng | Có đơn hàng? | `order_id` trong kết quả |
|---|---|---|
| Khách hàng A | Có | ID đơn hàng mới nhất |
| Khách hàng B | Không | NULL |
| Khách hàng C | Có | ID đơn hàng mới nhất |

Khách hàng B vẫn xuất hiện vì dùng `OUTER APPLY`. Nếu thay bằng `CROSS APPLY`, B sẽ bị loại.

### 6.3. Chỉ lấy đơn hàng PAID nhưng vẫn giữ mọi khách hàng

Đặt điều kiện trạng thái **bên trong** subquery:

```sql
SELECT c.customer_id,
       c.customer_name,
       paid.order_id,
       paid.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) paid;
```

Khách hàng không có đơn hàng PAID vẫn được giữ, với các cột `paid` là NULL.

Nếu đặt điều kiện sau APPLY:

```sql
-- Có thể loại các hàng đã được OUTER APPLY mở rộng NULL:
SELECT c.customer_id, paid.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.status
    FROM orders o
    WHERE o.customer_id = c.customer_id
) paid
WHERE paid.status = 'PAID';
```

Với khách hàng không có đơn hàng, `paid.status` là NULL và điều kiện `= 'PAID'` trả UNKNOWN; `WHERE` loại hàng. Kết quả khi đó có thể giống inner behavior đối với điều kiện này. Khi muốn giữ hàng trái, hãy đặt bộ lọc thuộc nguồn phải trong subquery APPLY.

## 7. So sánh LATERAL, CROSS APPLY và OUTER APPLY

| Cấu trúc | Cho subquery bên phải tham chiếu bảng bên trái? | Không có hàng bên phải | Ngữ nghĩa khái quát |
|---|---|---|---|
| Inline view thông thường | Không theo phạm vi tương quan thông thường | Không áp dụng nếu độc lập | Subquery độc lập |
| `, LATERAL (subquery)` | Có | Hàng trái bị loại nếu subquery rỗng | Cross/inner lateral |
| `CROSS APPLY (subquery)` | Có | Hàng trái bị loại | Inner lateral apply |
| `OUTER APPLY (subquery)` | Có | Giữ hàng trái, cột phải NULL | Left outer lateral apply |

`LATERAL` là cách đánh dấu một inline view có khả năng tương quan. `CROSS APPLY` và `OUTER APPLY` là các toán tử kết hợp nguồn dữ liệu tương quan, với khác biệt chính ở việc giữ hay loại hàng bên trái khi nguồn bên phải rỗng.

Không nên xem `LATERAL` và `OUTER APPLY` là hai từ khóa thay thế trực tiếp trong mọi câu SQL. Cú pháp `FROM t, LATERAL (...) x` có hành vi cross; muốn giữ hàng trái khi không có kết quả phải chọn cách outer phù hợp, chẳng hạn `OUTER APPLY`.

## 8. APPLY khác correlated scalar subquery như thế nào?

Correlated scalar subquery thường xuất hiện trong danh sách SELECT:

```sql
SELECT c.customer_id,
       c.customer_name,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

Scalar subquery trả về một giá trị:

- Không có hàng phù hợp: giá trị scalar là NULL.
- Có một hàng: lấy giá trị của hàng đó.
- Có nhiều hơn một hàng trong ngữ cảnh scalar: có thể phát sinh `ORA-01427: single-row subquery returns more than one row`.

`APPLY` cho phép subquery bên phải trả về **nhiều cột và nhiều hàng**, vì vậy phù hợp với top-N per parent hoặc một nhóm kết quả chi tiết.

| Nhu cầu | Cấu trúc phù hợp |
|---|---|
| Một giá trị tổng hợp cho mỗi khách hàng | Correlated scalar subquery hoặc APPLY |
| Hai đơn hàng mới nhất của mỗi khách hàng | `CROSS APPLY`/`OUTER APPLY` với top-N |
| Giữ khách hàng dù không có đơn hàng | `OUTER APPLY` |
| Lấy danh sách con nhiều hàng cho mỗi hàng cha | `APPLY` hoặc lateral inline view |
| Chỉ kiểm tra có tồn tại hàng con hay không | `EXISTS` thường rõ ràng hơn |

Không phải cứ có correlated subquery là phải đổi sang APPLY. Chọn cấu trúc diễn đạt đúng số hàng và ý nghĩa kết quả.

## 9. Top-N theo từng nhóm: mẫu sử dụng quan trọng

Một truy vấn top-N toàn cục:

```sql
SELECT order_id, customer_id, order_date
FROM orders
ORDER BY order_date DESC
FETCH FIRST 10 ROWS ONLY;
```

chỉ lấy 10 đơn hàng mới nhất của **toàn bảng**. Nó không phải 10 đơn hàng mới nhất của từng khách hàng.

### 9.1. Top 3 đơn hàng của mỗi khách hàng bằng OUTER APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date,
       x.total_amount
FROM customers c
OUTER APPLY (
    SELECT o.order_id,
           o.order_date,
           o.total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC NULLS LAST,
             o.order_id DESC
    FETCH FIRST 3 ROWS ONLY
) x
ORDER BY c.customer_id,
         x.order_date DESC NULLS LAST,
         x.order_id DESC;
```

Kết quả giữ tất cả khách hàng; mỗi khách hàng có tối đa ba hàng đơn hàng. Nếu không có đơn hàng, các cột `x` là NULL.

### 9.2. Vì sao cần tie-breaker?

Nếu chỉ viết:

```sql
ORDER BY o.order_date DESC
FETCH FIRST 3 ROWS ONLY
```

và nhiều đơn hàng có cùng `order_date`, Oracle có thể chọn các hàng đồng hạng theo thứ tự không ổn định. Bổ sung khóa duy nhất như `order_id`:

```sql
ORDER BY o.order_date DESC, o.order_id DESC
```

giúp thứ tự chọn top-N có tính xác định hơn, giả sử `order_id` là duy nhất.

### 9.3. Top-N WITH TIES

Nếu nghiệp vụ muốn giữ tất cả hàng đồng hạng tại vị trí cuối:

```sql
SELECT c.customer_id,
       x.order_id,
       x.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC
    FETCH FIRST 2 ROWS WITH TIES
) x;
```

`WITH TIES` có thể trả về **nhiều hơn hai hàng** nếu có các đơn hàng đồng hạng theo toàn bộ biểu thức `ORDER BY`. Nếu thêm `order_id` duy nhất vào `ORDER BY`, hầu như không còn tie ở toàn bộ khóa sắp xếp; hãy chọn biểu thức sắp xếp theo đúng định nghĩa “đồng hạng” của nghiệp vụ.

## 10. APPLY với phép tính và aggregate

### 10.1. Tính giá trị tổng hợp cho từng phòng ban

```sql
SELECT d.department_id,
       d.department_name,
       stats.employee_count,
       stats.average_salary
FROM departments d
CROSS APPLY (
    SELECT COUNT(*) AS employee_count,
           AVG(e.salary) AS average_salary
    FROM employees e
    WHERE e.department_id = d.department_id
) stats;
```

Subquery có aggregate nhưng không có `GROUP BY`, nên nó trả về **một hàng cho mỗi lần đánh giá**, kể cả khi không có nhân viên phù hợp:

- `COUNT(*)` trả 0.
- `AVG(salary)` trả NULL nếu không có giá trị đầu vào non-NULL.

Vì vậy, trong ví dụ này `CROSS APPLY` vẫn có thể giữ phòng ban không có nhân viên: subquery aggregate vẫn trả một hàng.

Đây là điểm dễ gây nhầm. `CROSS APPLY` chỉ loại hàng trái khi subquery bên phải thực sự không trả hàng. Một truy vấn aggregate không nhóm thường vẫn trả một hàng.

### 10.2. GROUP BY có thể làm subquery không trả hàng

```sql
SELECT d.department_id,
       x.employee_count
FROM departments d
CROSS APPLY (
    SELECT e.department_id,
           COUNT(*) AS employee_count
    FROM employees e
    WHERE e.department_id = d.department_id
    GROUP BY e.department_id
) x;
```

Nếu phòng ban không có nhân viên, subquery không tạo group nào và trả 0 hàng. `CROSS APPLY` khi đó loại phòng ban ấy.

Đổi thành `OUTER APPLY` nếu cần giữ mọi phòng ban:

```sql
SELECT d.department_id,
       x.employee_count
FROM departments d
OUTER APPLY (
    SELECT e.department_id,
           COUNT(*) AS employee_count
    FROM employees e
    WHERE e.department_id = d.department_id
    GROUP BY e.department_id
) x;
```

Lúc không có nhóm phù hợp, `x.employee_count` là NULL do outer extension, khác với `COUNT(*) = 0` của aggregate không `GROUP BY`.

### 10.3. Tính một số thông tin gần nhất theo từng tài khoản

```sql
SELECT a.account_id,
       a.account_name,
       x.last_transaction_at,
       x.last_transaction_amount
FROM accounts a
OUTER APPLY (
    SELECT t.transaction_date AS last_transaction_at,
           t.amount AS last_transaction_amount
    FROM transactions t
    WHERE t.account_id = a.account_id
    ORDER BY t.transaction_date DESC,
             t.transaction_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

Đây là một mẫu dễ đọc khi mỗi tài khoản cần một hàng giao dịch mới nhất, đồng thời vẫn giữ tài khoản chưa phát sinh giao dịch.

## 11. APPLY với nhiều bước tương quan

Có thể sử dụng nhiều APPLY nối tiếp, trong đó subquery sau tham chiếu bảng trái và kết quả từ APPLY trước, nếu alias đã nằm trước nó trong `FROM`.

Ví dụ, tìm đơn hàng gần nhất rồi tính số ngày từ ngày đặt đến hôm nay:

```sql
SELECT c.customer_id,
       c.customer_name,
       latest.order_id,
       latest.order_date,
       age_info.days_since_order
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) latest
OUTER APPLY (
    SELECT TRUNC(SYSDATE) - TRUNC(latest.order_date) AS days_since_order
    FROM dual
    WHERE latest.order_date IS NOT NULL
) age_info;
```

APPLY thứ hai tham chiếu `latest.order_date` từ APPLY trước. Với khách hàng không có đơn hàng, `latest.order_date` NULL; điều kiện trong subquery thứ hai không TRUE, nên `OUTER APPLY` giữ khách hàng và trả `days_since_order` NULL.

Khi chuỗi APPLY dài, hãy cân nhắc đặt tên alias theo ý nghĩa và kiểm soát số hàng mỗi bước có thể tạo ra. Nếu một APPLY trả nhiều hàng, APPLY tiếp theo có thể được áp dụng cho từng hàng kết quả đó, làm số hàng tăng theo quan hệ nhân.

## 12. LATERAL và các mẫu JOIN khác

### 12.1. So với JOIN thông thường

Nếu subquery phải không cần tham chiếu bảng trái, JOIN thông thường thường đủ:

```sql
SELECT c.customer_id, x.order_count
FROM customers c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
  ON x.customer_id = c.customer_id;
```

Nếu subquery phải cần tính top-N dựa trên `c.customer_id`, APPLY/LATERAL giúp diễn đạt trực tiếp mối quan hệ theo từng hàng trái.

### 12.2. So với EXISTS

Nếu chỉ cần biết có đơn hàng hay không:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Không cần `CROSS APPLY` chỉ để kiểm tra tồn tại. `EXISTS` diễn đạt rõ mục tiêu và không nhân bản khách hàng khi có nhiều đơn hàng.

### 12.3. So với correlated scalar subquery

Nếu chỉ cần ngày đơn hàng gần nhất:

```sql
SELECT c.customer_id,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

Scalar aggregate là cách đơn giản cho một giá trị. Nếu cần thêm `order_id`, `status`, `amount` từ **cùng một hàng mới nhất**, APPLY top-1 có thể tránh phải viết nhiều scalar subquery riêng và đảm bảo các cột lấy từ cùng hàng:

```sql
SELECT c.customer_id,
       x.order_id,
       x.order_date,
       x.status,
       x.total_amount
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date, o.status, o.total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

## 13. Thay thế khi database chưa hỗ trợ APPLY/LATERAL

Oracle 11g và các phiên bản cũ hơn không có cú pháp `LATERAL`, `CROSS APPLY`, `OUTER APPLY`. Hãy dùng kỹ thuật SQL đã có trong phiên bản đó.

### 13.1. Thay thế bằng analytic function ROW_NUMBER

Yêu cầu: lấy tối đa hai đơn hàng mới nhất của mỗi khách hàng và vẫn giữ khách hàng không có đơn hàng.

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c
LEFT JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Giải thích:

1. `ROW_NUMBER()` đánh số đơn hàng riêng trong từng khách hàng.
2. Đơn hàng mới nhất có `rn = 1`, tiếp theo `rn = 2`.
3. `LEFT JOIN` giữ khách hàng không có đơn hàng.
4. Điều kiện `x.rn <= 2` nằm trong `ON` để không loại hàng NULL-extended của phía phải.

Nếu đưa `x.rn <= 2` vào `WHERE`, các hàng không match có `x.rn` NULL và bị loại, làm mất ý nghĩa giữ mọi khách hàng.

### 13.2. Thay thế CROSS APPLY bằng INNER JOIN

Nếu chỉ muốn khách hàng có đơn hàng:

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c
JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2;
```

Đây là cách thay thế tương đương cho ví dụ top-N cụ thể. Với subquery tương quan phức tạp hơn, cần chuyển từng điều kiện sang analytic view, join hoặc correlated subquery phù hợp; không phải mọi lateral query đều có một phép biến đổi cơ học duy nhất.

### 13.3. Thay thế bằng correlated scalar subquery khi chỉ cần một giá trị

```sql
SELECT c.customer_id,
       c.customer_name,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

Đây là cách phù hợp khi chỉ cần một giá trị tổng hợp cho mỗi hàng cha. Nó không thay thế trực tiếp APPLY nếu cần trả nhiều hàng con.

### 13.4. Tránh ROWNUM đặt sai vị trí

Ví dụ dễ sai:

```sql
-- Không bảo đảm lấy hai đơn mới nhất:
SELECT order_id, order_date
FROM orders
WHERE ROWNUM <= 2
ORDER BY order_date DESC;
```

`ROWNUM` được gán trong quá trình chọn hàng của query block; sắp xếp ở cùng block không làm nó trở thành top-N theo thứ tự mong muốn. Với phiên bản cũ, sắp xếp trong inline view trước rồi mới giới hạn:

```sql
SELECT order_id, order_date
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = 100
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM <= 2;
```

Đây là top-N cho một khách hàng cụ thể. Để top-N cho mọi khách hàng, analytic `ROW_NUMBER() OVER (PARTITION BY ...)` thường là mẫu phù hợp hơn.

## 14. Những lưu ý khi dùng OUTER APPLY

### 14.1. Phân biệt không có hàng và có hàng với giá trị NULL

Hai tình huống khác nhau:

1. Subquery bên phải không trả hàng nào: `OUTER APPLY` tạo hàng kết quả với các cột bên phải NULL.
2. Subquery trả một hàng nhưng giá trị của cột bên phải vốn NULL: hàng vẫn tồn tại, cột đó cũng NULL.

Chỉ nhìn một cột NULL có thể không phân biệt được hai trường hợp. Nếu cần nhận biết subquery có trả hàng hay không, hãy chọn một khóa của hàng con được bảo đảm NOT NULL:

```sql
SELECT c.customer_id,
       x.order_id,
       CASE
           WHEN x.order_id IS NULL THEN 'NO_MATCH'
           ELSE 'HAS_ORDER'
       END AS match_status
FROM customers c
OUTER APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

Ví dụ giả định `order_id` là khóa chính nên không NULL khi có hàng.

### 14.2. Aggregate không GROUP BY vẫn trả một hàng

Như đã nêu, subquery:

```sql
SELECT COUNT(*) AS order_count
FROM orders o
WHERE o.customer_id = c.customer_id
```

trả một hàng với `order_count = 0` nếu không có đơn hàng. Do đó `OUTER APPLY` không cần tạo hàng NULL-extended trong trường hợp này; subquery đã có một hàng kết quả. Nếu cần phân biệt không có dữ liệu và kết quả aggregate NULL, xem riêng các giá trị aggregate.

### 14.3. Bộ lọc sau APPLY có thể loại hàng trái

```sql
SELECT c.customer_id, x.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.status
    FROM orders o
    WHERE o.customer_id = c.customer_id
) x
WHERE x.status = 'PAID';
```

Điều kiện `WHERE` ở ngoài loại những hàng không match. Nếu mục tiêu là giữ mọi khách hàng và chỉ lấy các đơn PAID, chuyển `x.status = 'PAID'` vào subquery.

### 14.4. APPLY có thể nhân số hàng

Nếu mỗi khách hàng có 4 hàng từ APPLY thứ nhất và 3 hàng từ APPLY thứ hai, kết quả kết hợp nối tiếp có thể tạo nhiều tổ hợp. Hãy xác định số hàng mong muốn ở từng bước, dùng top-1/top-N hoặc aggregate nếu cần giới hạn.

## 15. Hiệu năng và execution plan

`APPLY` diễn đạt mối quan hệ tương quan, nhưng không nên hiểu rằng Oracle bắt buộc thực hiện một vòng lặp thủ tục đơn giản cho từng hàng trái. Optimizer có thể biến đổi, đẩy điều kiện, chọn nested loops hoặc phương án khác tùy truy vấn, thống kê, index và phiên bản.

### 15.1. Index có thể hữu ích cho top-N

Với truy vấn:

```sql
SELECT ...
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x;
```

Một index được cân nhắc trên bảng con:

```sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date DESC, order_id DESC);
```

Index này có thể giúp tìm đơn hàng theo `customer_id` và hỗ trợ thứ tự cần thiết. Khả năng sử dụng thực tế phụ thuộc cấu trúc index, số hàng, thống kê, điều kiện lọc và execution plan; không tạo index chỉ dựa trên ví dụ.

### 15.2. Xem execution plan

Trong môi trường có quyền phù hợp:

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       x.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` ghi kế hoạch dự kiến vào plan table; nó không nhất thiết phản ánh chính xác mọi điều kiện thực thi runtime. Khi được phép, có thể xem execution plan thực tế cùng thống kê thực thi để đánh giá.

### 15.3. Khi nào APPLY có thể không phải lựa chọn tốt?

- Subquery bên phải rất tốn kém và được yêu cầu cho số lượng hàng trái rất lớn.
- Dữ liệu có thể được tổng hợp một lần theo nhóm rồi JOIN hiệu quả hơn.
- Mục tiêu chỉ là kiểm tra tồn tại, khi đó `EXISTS` thường gọn và rõ.
- Truy vấn có nhiều APPLY nối tiếp làm số hàng tăng ngoài dự kiến.
- Một analytic query có thể xử lý toàn bộ tập dữ liệu hiệu quả hơn việc tìm top-N theo từng khóa.

Hãy so sánh execution plan và đo trên dữ liệu gần với production. Cú pháp ngắn hơn không tự động đồng nghĩa truy vấn nhanh hơn.

## 16. Bài thực hành: top 2 đơn hàng theo khách hàng

Các bước sau tạo bảng riêng trong schema thực hành. Chỉ chạy nếu có quyền `CREATE TABLE`, quota phù hợp và không dùng bảng production.

### Bước 1. Tạo hai bảng

```sql
CREATE TABLE demo_apply_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_apply_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMBER(12, 2),
    status VARCHAR2(20),
    CONSTRAINT fk_dao_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_apply_customers (customer_id)
);
```

### Bước 2. Chèn dữ liệu

```sql
INSERT INTO demo_apply_customers VALUES (1, 'An');
INSERT INTO demo_apply_customers VALUES (2, 'Binh');
INSERT INTO demo_apply_customers VALUES (3, 'Chi');

INSERT INTO demo_apply_orders
VALUES (101, 1, DATE '2026-11-01', 100.00, 'PAID');

INSERT INTO demo_apply_orders
VALUES (102, 1, DATE '2026-11-05', 250.00, 'PAID');

INSERT INTO demo_apply_orders
VALUES (103, 1, DATE '2026-11-10', 75.00, 'NEW');

INSERT INTO demo_apply_orders
VALUES (201, 2, DATE '2026-11-03', 80.00, 'PAID');

COMMIT;
```

Khách hàng 1 có ba đơn, khách hàng 2 có một đơn, khách hàng 3 chưa có đơn.

### Bước 3. Thử CROSS APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date,
       x.total_amount
FROM demo_apply_customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date, o.total_amount
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Kết quả kỳ vọng:

- An: đơn 103 và 102.
- Binh: đơn 201.
- Chi: không xuất hiện.

### Bước 4. Thử OUTER APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Khách hàng Chi vẫn xuất hiện với `order_id` và `order_date` là NULL.

### Bước 5. Thử LATERAL

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM demo_apply_orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 2 ROWS ONLY
     ) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Kết quả có hành vi cross lateral: Chi không xuất hiện vì subquery không trả hàng.

### Bước 6. Thử bộ lọc trong APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.status
FROM demo_apply_customers c
OUTER APPLY (
    SELECT o.order_id, o.status, o.order_date
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x
ORDER BY c.customer_id;
```

Tất cả khách hàng vẫn được giữ; khách hàng không có đơn PAID nhận NULL ở các cột bên phải.

### Bước 7. So sánh với analytic function

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c
LEFT JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM demo_apply_orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Đối chiếu kết quả với `OUTER APPLY`: cả hai cách đều giữ khách hàng không có đơn và giới hạn tối đa hai đơn mỗi khách hàng.

### Bước 8. Dọn bảng thực hành

Chỉ sau khi chắc chắn đây là bảng do chính bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_apply_orders PURGE;
DROP TABLE demo_apply_customers PURGE;
```

`DROP TABLE ... PURGE` xóa đối tượng và dữ liệu, bỏ qua recycle bin theo hành vi của lệnh; đây là DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 17. Lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-00933` hoặc lỗi cú pháp trên Oracle 11g | Database chưa hỗ trợ `LATERAL`/`APPLY` | Dùng analytic function, JOIN hoặc correlated subquery |
| `ORA-00904: invalid identifier` cho alias bên trái | Inline view thông thường không có lateral scope, hoặc alias chưa nằm trước lateral view | Dùng `LATERAL`/`APPLY` và đặt bảng tương quan ở trước |
| Khách hàng không có đơn bị mất | Dùng `CROSS APPLY` hoặc cross lateral | Dùng `OUTER APPLY` nếu cần giữ hàng trái |
| Khách hàng không có đơn vẫn mất sau OUTER APPLY | Điều kiện lọc cột bên phải nằm trong WHERE ngoài | Chuyển điều kiện phù hợp vào subquery APPLY |
| Kết quả có nhiều hàng hơn dự kiến | Subquery bên phải trả nhiều hàng cho mỗi hàng trái | Giới hạn top-N, aggregate hoặc kiểm soát cardinality |
| Chỉ lấy hai đơn của toàn bảng | Đặt `FETCH FIRST 2` ở query block ngoài | Đặt row limiting trong subquery tương quan |
| Đơn hàng top-N thay đổi giữa các lần chạy | ORDER BY không xác định thứ tự duy nhất khi tie | Thêm khóa duy nhất làm tie-breaker |
| `OUTER APPLY` trả count bằng 0 thay vì NULL | Aggregate không GROUP BY tự trả một hàng | Hiểu khác biệt giữa aggregate row và zero-row subquery |
| APPLY nối tiếp làm bùng số hàng | Nhiều bước đều trả nhiều hàng và kết hợp theo quan hệ nhân | Xác định cardinality từng bước, dùng top-N/aggregate |
| Dùng APPLY chỉ để kiểm tra tồn tại | Chọn sai cấu trúc so với mục tiêu | Dùng `EXISTS` khi chỉ cần true/false |

### Quy trình chọn cấu trúc

1. Bạn cần một giá trị hay nhiều hàng con?
2. Subquery có cần tham chiếu cột từ bảng đứng trước trong `FROM` không?
3. Nếu subquery không trả hàng, có cần giữ hàng bên trái không?
4. Có cần top-N riêng cho từng hàng cha không?
5. Database đang chạy từ Oracle 12.1 trở lên hay phải hỗ trợ phiên bản cũ?
6. Có thể dùng analytic function hoặc aggregate một lần thay cho nhiều truy vấn tương quan không?
7. Execution plan và index hiện tại có phù hợp với cardinality thật không?

## 18. Quy tắc ghi nhớ

| Nhu cầu | Cấu trúc nên cân nhắc |
|---|---|
| Inline view tham chiếu bảng đứng trước | `LATERAL (...)` |
| Lấy kết quả tương quan, bỏ hàng trái nếu không có kết quả | `CROSS APPLY (...)` |
| Lấy kết quả tương quan, vẫn giữ hàng trái khi không có kết quả | `OUTER APPLY (...)` |
| Chỉ cần biết có hàng con hay không | `EXISTS` |
| Chỉ cần một giá trị tổng hợp | Correlated scalar subquery hoặc APPLY |
| Lấy nhiều hàng top-N theo từng hàng cha | APPLY/LATERAL với `ORDER BY` và row limiting |
| Oracle 11g hoặc cũ hơn | Analytic `ROW_NUMBER()` và JOIN; scalar subquery nếu chỉ cần một giá trị |
| Không muốn mất hàng trái khi lọc nguồn phải | Đặt điều kiện trong subquery APPLY |
| Cần thứ tự kết quả cuối cùng | `ORDER BY` ở query block ngoài cùng |

Những điểm cần nhớ:

- `APPLY` không giới hạn subquery bên phải ở một hàng.
- `CROSS APPLY` loại hàng trái nếu subquery rỗng.
- `OUTER APPLY` giữ hàng trái và mở rộng NULL khi subquery rỗng.
- `OUTER APPLY` không tự tạo NULL-extension nếu subquery aggregate không nhóm đã trả một hàng.
- `FETCH FIRST` phải nằm trong đúng query block nếu giới hạn top-N cho từng nhóm.
- `ORDER BY` cần tie-breaker nếu kết quả top-N phải ổn định.
- Tương quan theo hàng là semantics logic; optimizer vẫn có thể biến đổi cách thực thi.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Oracle hỗ trợ `LATERAL`, `CROSS APPLY` và `OUTER APPLY` từ phiên bản nào?

**Trả lời:** Oracle Database 12c Release 1 (12.1). Oracle 11g và các phiên bản cũ hơn không hỗ trợ trực tiếp cú pháp này.

**Câu 2.** `LATERAL` cho phép inline view làm gì?

**Trả lời:** Tham chiếu alias của những bảng đã xuất hiện trước nó trong mệnh đề `FROM`.

**Câu 3.** `CROSS APPLY` khác `OUTER APPLY` ở điểm nào?

**Trả lời:** CROSS APPLY loại hàng bên trái nếu subquery bên phải không trả hàng; OUTER APPLY giữ hàng trái và trả NULL cho các cột bên phải.

**Câu 4.** Subquery APPLY có thể trả nhiều hàng không?

**Trả lời:** Có. Mỗi hàng bên trái có thể tạo nhiều hàng kết quả theo số hàng mà subquery bên phải trả về.

**Câu 5.** Vì sao `FETCH FIRST 2 ROWS ONLY` cần nằm bên trong subquery APPLY khi lấy hai đơn mới nhất của mỗi khách hàng?

**Trả lời:** Vì row limiting phải áp dụng riêng cho kết quả tương quan của từng khách hàng; đặt ở query ngoài chỉ giới hạn toàn bộ kết quả.

**Câu 6.** Dùng `OUTER APPLY` nhưng vẫn mất khách hàng không có đơn PAID. Nguyên nhân có thể là gì?

**Trả lời:** Điều kiện `status='PAID'` được đặt trong WHERE ngoài; hàng NULL-extended bị loại. Đưa điều kiện vào subquery APPLY.

**Câu 7.** Aggregate `COUNT(*)` không có GROUP BY có trả hàng khi không có dữ liệu phù hợp không?

**Trả lời:** Có. Nó trả một hàng với count bằng 0. Vì vậy CROSS APPLY vẫn giữ hàng trái trong trường hợp này.

**Câu 8.** Khi chỉ cần biết khách hàng có đơn hàng không, nên cân nhắc gì?

**Trả lời:** `EXISTS` thường phù hợp và rõ nghĩa hơn APPLY.

**Câu 9.** Cách phổ biến thay top-N APPLY trên Oracle 11g là gì?

**Trả lời:** Dùng `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` trong inline view rồi JOIN với điều kiện `rn <= N`.

**Câu 10.** Vì sao top-N nên có tie-breaker?

**Trả lời:** Nếu nhiều hàng có cùng giá trị sắp xếp, Oracle không bảo đảm chọn một nhóm hàng ổn định nếu thứ tự không phân định duy nhất.

**Câu 11.** Có thể đặt `WHERE right_table.status='ACTIVE'` sau OUTER APPLY mà vẫn chắc chắn giữ hàng trái không match không?

**Trả lời:** Không. Điều kiện đó có thể loại hàng NULL-extended. Nếu muốn giữ hàng trái, đặt điều kiện trong subquery bên phải.

**Câu 12.** APPLY có nghĩa Oracle bắt buộc chạy một câu SQL riêng biệt theo vòng lặp cho từng hàng trái không?

**Trả lời:** Không. Đó là cách hiểu semantics tương quan; optimizer có thể biến đổi và chọn kế hoạch thực thi khác. Cần xem execution plan thực tế.

## 20. Kết luận

`LATERAL`, `CROSS APPLY` và `OUTER APPLY` giúp viết truy vấn con trong `FROM` có thể tham chiếu các bảng đứng trước nó. **`CROSS APPLY`** có hành vi inner: hàng trái chỉ xuất hiện khi subquery bên phải có kết quả. **`OUTER APPLY`** có hành vi outer: hàng trái vẫn được giữ khi không có hàng phải, các cột phía phải khi đó là NULL. `LATERAL` đánh dấu inline view có phạm vi tương quan; cách dùng với phép nối chéo có hành vi tương tự cross lateral.

Oracle hỗ trợ các cấu trúc này từ **12c Release 1 (12.1)**. Với hệ thống cũ hơn, dùng correlated scalar subquery khi chỉ cần một giá trị, hoặc analytic function như `ROW_NUMBER()` kết hợp JOIN khi cần top-N theo từng nhóm. Khi thiết kế truy vấn, hãy xác định số hàng bên phải, vị trí điều kiện lọc, xử lý NULL, thứ tự top-N và phiên bản database. Cuối cùng, đo execution plan trên dữ liệu thực tế: APPLY giúp diễn đạt logic rõ ràng, còn hiệu năng vẫn phụ thuộc optimizer, thống kê, index và cardinality của từng bước.
