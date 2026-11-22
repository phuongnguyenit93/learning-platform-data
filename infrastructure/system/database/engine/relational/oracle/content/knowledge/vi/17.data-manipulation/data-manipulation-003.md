# UPDATE một bảng, cập nhật nhiều cột và cập nhật từ truy vấn con trong Oracle

## 1. UPDATE dùng để làm gì?

`UPDATE` thay đổi giá trị của một hoặc nhiều cột trên các hàng đang tồn tại trong bảng. Bạn có thể cập nhật một giá trị cố định, tính giá trị mới từ dữ liệu hiện có của chính hàng đó, hoặc lấy dữ liệu từ một truy vấn con.

Ví dụ, tăng lương 5% cho nhân viên thuộc phòng ban 10:

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
```

Ví dụ cập nhật đồng thời lương và thời điểm sửa:

```sql
UPDATE employees
SET salary = salary * 1.05,
    updated_at = SYSTIMESTAMP
WHERE department_id = 10;
```

Ví dụ lấy mức lương mới từ bảng điều chỉnh:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`UPDATE` là lệnh DML (Data Manipulation Language). Nó thay đổi dữ liệu trong transaction hiện tại; thay đổi chỉ được xác nhận lâu dài khi transaction được `COMMIT`, hoặc bị hủy bằng `ROLLBACK`.

Bài học thuộc chương **Thay đổi dữ liệu**, tập trung vào cập nhật một bảng, cập nhật nhiều cột trong một câu lệnh và cập nhật từ truy vấn con. Các nội dung chính gồm cú pháp `SET`, điều kiện `WHERE`, scalar subquery, subquery gán nhiều cột, truy vấn con tương quan, kiểm soát trường hợp không có hoặc có nhiều hàng nguồn, kiểm tra kết quả và quản lý transaction.

## 2. Cú pháp UPDATE cơ bản

Mẫu cú pháp thường dùng:

```sql
UPDATE table_name
SET column_name = expression
    [, column_name = expression ...]
[WHERE condition];
```

Trong đó:

- `table_name`: bảng đích cần thay đổi.
- `SET`: khai báo cột và giá trị mới.
- `expression`: literal, phép tính, hàm, biểu thức `CASE` hoặc truy vấn con phù hợp.
- `WHERE`: xác định hàng nào được cập nhật.

Ví dụ:

```sql
UPDATE products
SET unit_price = 125000
WHERE product_id = 1001;
```

Lệnh thay `UNIT_PRICE` của sản phẩm có mã 1001 bằng 125000. Những hàng khác không bị tác động.

### 2.1. UPDATE không có WHERE

```sql
UPDATE products
SET discontinued_flag = 'N';
```

Không có `WHERE` nghĩa là cập nhật **mọi hàng** trong bảng `PRODUCTS`. Đây có thể là chủ đích khi chuẩn hóa toàn bộ dữ liệu, nhưng cũng là lỗi nguy hiểm nếu người viết quên điều kiện.

Trước khi chạy một lệnh UPDATE trên dữ liệu thật, nên chạy SELECT với cùng điều kiện:

```sql
SELECT product_id, unit_price
FROM products
WHERE product_id = 1001;
```

Sau khi xác nhận đúng tập hàng, mới chạy UPDATE với điều kiện tương ứng.

### 2.2. WHERE có thể dùng các điều kiện thông thường

```sql
UPDATE employees
SET commission_pct = 0.10
WHERE department_id = 20
  AND commission_pct IS NULL;
```

Điều kiện lọc có thể kết hợp `AND`, `OR`, `IN`, `BETWEEN`, `EXISTS`, subquery và các phép kiểm tra NULL. Nếu cột nullable, hãy dùng `IS NULL`/`IS NOT NULL`; phép so sánh `= NULL` không tìm được hàng NULL.

### 2.3. WHERE chỉ định hàng đích, không phải giá trị nguồn

Phân biệt hai phần:

```sql
UPDATE employees e
SET salary = salary * 1.05             -- Giá trị mới
WHERE department_id = 10;             -- Hàng đích
```

Nếu dùng subquery:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.department_id = 10;
```

`WHERE e.department_id = 10` giới hạn nhân viên được cập nhật. Điều kiện bên trong subquery xác định giá trị mới tương ứng cho từng nhân viên.

## 3. Cập nhật một cột

### 3.1. Gán một giá trị cố định

```sql
UPDATE customers
SET status = 'ACTIVE'
WHERE customer_id = 501;
```

### 3.2. Tính từ giá trị hiện tại

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 2001;
```

Oracle tính biểu thức từ giá trị hiện tại của hàng được cập nhật. Cần bổ sung điều kiện nghiệp vụ nếu không cho phép số lượng âm:

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = 2001
  AND quantity >= 3;
```

Sau UPDATE, ứng dụng nên kiểm tra số hàng bị tác động. Nếu không có hàng nào được cập nhật, có thể sản phẩm không tồn tại hoặc không đủ số lượng.

### 3.3. Dùng CASE để cập nhật theo điều kiện

```sql
UPDATE employees
SET salary = CASE
                 WHEN performance_score >= 90 THEN salary * 1.10
                 WHEN performance_score >= 75 THEN salary * 1.05
                 ELSE salary
             END
WHERE review_year = 2026;
```

`CASE` tính giá trị mới cho từng hàng. Các hàng không thỏa nhánh đầu sẽ được kiểm tra nhánh tiếp theo; `ELSE salary` giữ nguyên lương với những trường hợp còn lại.

Nếu không có `ELSE`, biểu thức CASE trả NULL khi không nhánh nào khớp. Điều này có thể làm cột bị đặt thành NULL ngoài dự kiến.

### 3.4. Đặt cột về NULL hoặc DEFAULT

```sql
UPDATE customers
SET secondary_phone = NULL
WHERE customer_id = 501;
```

Chỉ hợp lệ nếu cột cho phép NULL và các constraint liên quan vẫn được thỏa mãn.

Nếu muốn dùng giá trị mặc định đã khai báo của cột:

```sql
UPDATE orders
SET priority_code = DEFAULT
WHERE order_id = 9001;
```

`DEFAULT` sử dụng default được định nghĩa cho cột. Nếu cột không có default, hành vi cần được kiểm tra theo định nghĩa schema và phiên bản Oracle đang sử dụng; không coi DEFAULT là cách tự tạo một giá trị nghiệp vụ.

## 4. Cập nhật nhiều cột trong một UPDATE

Khi một thao tác nghiệp vụ thay đổi nhiều thuộc tính của cùng một hàng, có thể liệt kê nhiều phép gán trong một mệnh đề `SET`.

### 4.1. Cú pháp gán từng cột

```sql
UPDATE employees
SET salary = salary * 1.05,
    commission_pct = 0.12,
    updated_at = SYSTIMESTAMP
WHERE employee_id = 100;
```

Ba cột được cập nhật trong cùng một câu lệnh:

- `SALARY` tăng 5%.
- `COMMISSION_PCT` được đặt thành 0.12.
- `UPDATED_AT` nhận thời điểm hiện tại của hệ thống.

### 4.2. Biểu thức của các cột có thể độc lập

```sql
UPDATE products
SET unit_price = unit_price * 1.08,
    tax_amount = unit_price * 0.08,
    updated_at = SYSDATE
WHERE category_id = 30;
```

Trong một câu UPDATE, các biểu thức bên phải được đánh giá từ giá trị hàng trước khi cập nhật; không nên dựa vào thứ tự liệt kê để làm cột sau đọc giá trị mới của cột trước. Trong ví dụ trên, `TAX_AMOUNT` được tính từ `UNIT_PRICE` cũ.

Nếu muốn tính thuế dựa trên giá mới, viết biểu thức đầy đủ:

```sql
UPDATE products
SET unit_price = unit_price * 1.08,
    tax_amount = unit_price * 1.08 * 0.08
WHERE category_id = 30;
```

Hoặc tính giá mới trong một biểu thức có cấu trúc rõ ràng. Không dùng chuỗi UPDATE nhiều lần nếu một câu lệnh có thể biểu đạt đầy đủ thay đổi của cùng một hàng.

### 4.3. Cập nhật nhiều cột với điều kiện khác nhau

```sql
UPDATE customer_profiles
SET phone_verified = CASE
                         WHEN phone_number IS NOT NULL THEN 'Y'
                         ELSE 'N'
                     END,
    email_verified = CASE
                         WHEN email_address IS NOT NULL THEN 'Y'
                         ELSE 'N'
                     END,
    updated_at = SYSTIMESTAMP
WHERE profile_status = 'PENDING';
```

Mỗi cột có biểu thức riêng nhưng cùng áp dụng cho tập hàng được chọn bởi `WHERE`.

## 5. Gán nhiều cột từ một subquery

Oracle cho phép gán một danh sách cột bằng một subquery trả về các biểu thức tương ứng:

```sql
UPDATE target_table t
SET (column_a, column_b) = (
    SELECT source_a, source_b
    FROM source_table s
    WHERE s.key_id = t.key_id
)
WHERE ...;
```

Điều kiện quan trọng:

1. Số biểu thức trong SELECT list phải bằng số cột ở vế trái.
2. Thứ tự biểu thức phải tương ứng đúng với thứ tự cột.
3. Subquery dùng cho một hàng đích phải trả về tối đa một hàng.
4. Kiểu dữ liệu của từng biểu thức phải có thể gán cho cột đích.

### 5.1. Ví dụ cập nhật địa chỉ và mã vùng

Giả sử bảng `customers` cần nhận địa chỉ chuẩn hóa từ `customer_address_updates`:

```sql
UPDATE customers c
SET (address_line, postal_code) = (
    SELECT u.address_line,
           u.postal_code
    FROM customer_address_updates u
    WHERE u.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM customer_address_updates u
    WHERE u.customer_id = c.customer_id
);
```

Với mỗi khách hàng có bản ghi cập nhật, Oracle lấy hai giá trị từ cùng hàng nguồn rồi gán lần lượt:

- `u.address_line` vào `c.address_line`.
- `u.postal_code` vào `c.postal_code`.

`WHERE EXISTS` bảo đảm chỉ cập nhật khách hàng có dữ liệu nguồn. Nếu bỏ điều kiện này, những khách hàng không có hàng trong `CUSTOMER_ADDRESS_UPDATES` vẫn có thể bị cập nhật và hai cột đích bị đặt thành NULL.

### 5.2. Cột nguồn và cột đích được ghép theo vị trí

Ví dụ:

```sql
SET (first_name, last_name) = (
    SELECT s.last_name,
           s.first_name
    FROM staging_names s
    WHERE s.employee_id = e.employee_id
)
```

Số cột khớp nhưng thứ tự sai về ý nghĩa: `LAST_NAME` nguồn sẽ được gán vào `FIRST_NAME`. Oracle không tự ghép theo tên alias. Hãy kiểm tra từng vị trí:

| Vị trí | Cột đích | Biểu thức nguồn |
|---:|---|---|
| 1 | `FIRST_NAME` | `S.FIRST_NAME` |
| 2 | `LAST_NAME` | `S.LAST_NAME` |

### 5.3. Cập nhật nhiều cột với giá trị tính toán

```sql
UPDATE products p
SET (unit_price, updated_at) = (
    SELECT ROUND(s.proposed_price, 2),
           SYSTIMESTAMP
    FROM price_staging s
    WHERE s.product_id = p.product_id
)
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
);
```

Ví dụ giả định `PRICE_STAGING` có tối đa một dòng cho mỗi `PRODUCT_ID`. Nếu có nhiều dòng nguồn cho cùng sản phẩm, subquery có thể gây lỗi nhiều hàng.

### 5.4. Một subquery cho nhiều cột giúp lấy dữ liệu cùng hàng nguồn

Nếu `FIRST_NAME`, `LAST_NAME` và `EMAIL` phải lấy từ cùng một bản ghi staging, gán theo nhóm:

```sql
UPDATE employees e
SET (first_name, last_name, email) = (
    SELECT s.first_name,
           s.last_name,
           s.email
    FROM employee_staging s
    WHERE s.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM employee_staging s
    WHERE s.employee_id = e.employee_id
);
```

Cách viết này thể hiện các giá trị được lấy từ cùng một hàng nguồn. Nếu tách thành ba scalar subquery độc lập, mỗi truy vấn phải có điều kiện và quy tắc chọn hàng nhất quán; nếu dữ liệu nguồn thay đổi giữa các bước, việc gộp một câu UPDATE cũng giúp thao tác nhất quán hơn trong một statement.

## 6. Scalar subquery trong mệnh đề SET

Scalar subquery là truy vấn con được dùng như một biểu thức đơn trị. Trong `SET`, nó có thể lấy một giá trị từ bảng khác:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.employee_id = 100;
```

Subquery phải trả về tối đa một hàng cho mỗi hàng đích được cập nhật.

### 6.1. Subquery trả đúng một hàng

Nếu tìm được một dòng điều chỉnh cho nhân viên 100, `SALARY` nhận `NEW_SALARY`.

### 6.2. Subquery trả không hàng nào

Một scalar subquery không trả hàng nào cho giá trị NULL. Vì vậy:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

Nếu nhân viên không có dòng điều chỉnh, `SALARY` của nhân viên đó có thể bị đặt thành NULL. Nếu cột là NOT NULL, lệnh có thể thất bại do constraint. Đây là một nguyên nhân phổ biến khiến câu UPDATE chạy trên nhiều hàng nhưng vô tình xóa giá trị hiện tại ở những hàng không có nguồn.

### 6.3. Subquery trả nhiều hơn một hàng

Nếu có hai dòng điều chỉnh cho cùng một nhân viên, scalar subquery không biết phải chọn dòng nào và Oracle báo:

```text
ORA-01427: single-row subquery returns more than one row
```

Không xử lý bằng cách thêm `ROWNUM = 1` một cách tùy tiện. Trước hết hãy xác định vì sao nguồn có nhiều hàng và quy tắc nghiệp vụ chọn bản ghi nào.

### 6.4. Bảo vệ UPDATE bằng EXISTS

Mẫu phổ biến:

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`EXISTS` loại hàng đích không có bản ghi nguồn. Nó không tự giải quyết trường hợp có nhiều hàng nguồn; tính duy nhất của dữ liệu nguồn vẫn phải được bảo đảm.

## 7. UPDATE với truy vấn con tương quan

Subquery tương quan (correlated subquery) tham chiếu cột của hàng đang được UPDATE. Oracle đánh giá biểu thức theo ngữ cảnh hàng đích.

### 7.1. Lấy giá trị từ bảng khác

```sql
UPDATE employees e
SET department_id = (
    SELECT m.new_department_id
    FROM employee_department_map m
    WHERE m.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM employee_department_map m
    WHERE m.employee_id = e.employee_id
);
```

`e.employee_id` là giá trị của hàng đang cập nhật. Subquery tìm ánh xạ tương ứng cho hàng đó.

### 7.2. Cập nhật bằng giá trị tổng hợp từ bảng con

Ví dụ cập nhật tổng chi tiêu của mỗi khách hàng:

```sql
UPDATE customers c
SET total_spent = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Subquery `SUM` không có `GROUP BY` trả về một hàng aggregate. Nếu không có đơn hàng, `SUM` là NULL. Điều kiện EXISTS giúp không cập nhật khách hàng chưa có đơn hàng.

Nếu nghiệp vụ quy định khách hàng không có đơn hàng có tổng chi tiêu bằng 0 và muốn cập nhật cả những khách hàng đó:

```sql
UPDATE customers c
SET total_spent = NVL((
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
), 0);
```

Ở đây không có WHERE nên mọi khách hàng được cập nhật; khách hàng không có đơn sẽ nhận 0. Chỉ dùng khi đó là quy tắc nghiệp vụ đã thống nhất.

### 7.3. Cập nhật từ giá trị mới nhất trong bảng lịch sử

```sql
UPDATE customer_profiles p
SET last_order_date = (
    SELECT MAX(o.order_date)
    FROM orders o
    WHERE o.customer_id = p.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = p.customer_id
);
```

`MAX` trả một hàng và giá trị ngày lớn nhất. Đây là cách đơn giản nếu chỉ cần một giá trị tổng hợp. Nếu cần lấy nhiều cột từ cùng đơn hàng mới nhất, hãy dùng một subquery có quy tắc chọn hàng xác định hoặc cân nhắc `MERGE`/inline view phù hợp.

### 7.4. Cập nhật từ chính bảng đó

Subquery có thể đọc lại bảng đích để tính giá trị mới:

```sql
UPDATE employees e
SET salary = (
    SELECT ROUND(AVG(e2.salary), 2)
    FROM employees e2
    WHERE e2.department_id = e.department_id
)
WHERE e.department_id = 10;
```

Ví dụ này đặt lương của từng nhân viên trong phòng ban 10 bằng lương trung bình của phòng ban theo dữ liệu được đọc bởi subquery. Đây chỉ là ví dụ kỹ thuật; khi áp dụng thực tế, cần cân nhắc liệu có đúng nghiệp vụ khi thay mọi lương cá nhân bằng trung bình phòng ban hay không.

## 8. Khi không có hàng nguồn: giữ nguyên, đặt NULL hay đặt giá trị mặc định?

Đây là quyết định quan trọng nhất khi UPDATE từ subquery.

Giả sử bảng đích có:

| employee_id | salary hiện tại |
|---:|---:|
| 101 | 10000 |
| 102 | 12000 |
| 103 | 15000 |

Bảng nguồn chỉ có điều chỉnh cho nhân viên 101 và 102.

### 8.1. Muốn chỉ cập nhật hàng có nguồn

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

Nhân viên 103 không có nguồn nên được giữ nguyên.

### 8.2. Muốn cập nhật mọi hàng, không có nguồn thì đặt NULL

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

Nhân viên 103 sẽ nhận NULL từ scalar subquery rỗng. Chỉ dùng khi yêu cầu thực sự là xóa giá trị cũ ở những hàng không có bản ghi nguồn.

### 8.3. Muốn cập nhật mọi hàng, không có nguồn thì giữ giá trị cũ

Có thể dùng `NVL` nếu NULL chỉ xuất hiện khi không có kết quả hoặc nguồn trả NULL:

```sql
UPDATE employees e
SET salary = NVL((
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
), e.salary);
```

Nhưng cách này gộp hai tình huống:

1. Không có hàng nguồn.
2. Có hàng nguồn nhưng `NEW_SALARY` là NULL.

Nếu hai tình huống mang ý nghĩa khác nhau, hãy dùng `EXISTS` hoặc kiểm tra riêng cột nguồn:

```sql
UPDATE employees e
SET salary = CASE
    WHEN EXISTS (
        SELECT 1
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
          AND a.new_salary IS NOT NULL
    )
    THEN (
        SELECT a.new_salary
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
          AND a.new_salary IS NOT NULL
    )
    ELSE e.salary
END;
```

Ví dụ này giữ lương cũ nếu không có giá trị lương mới non-NULL. Cần bảo đảm subquery vẫn trả tối đa một hàng.

### 8.4. Dùng CASE để thể hiện chính sách rõ ràng

```sql
UPDATE employees e
SET salary = CASE
    WHEN EXISTS (
        SELECT 1
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    THEN (
        SELECT a.new_salary
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    ELSE e.salary
END;
```

Điều kiện EXISTS xác định có hàng nguồn; nhánh THEN mới lấy giá trị. Nếu hàng nguồn tồn tại nhưng `NEW_SALARY` NULL, giá trị đích cũng được đặt NULL. Đây có thể là chính sách đúng hoặc sai tùy nghiệp vụ.

## 9. Kiểm soát dữ liệu nguồn có nhiều hàng

Subquery gán một giá trị cho một hàng đích phải có kết quả đơn trị. Trước khi UPDATE, hãy kiểm tra khóa nguồn:

```sql
SELECT employee_id,
       COUNT(*) AS source_count
FROM salary_adjustments
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

Nếu truy vấn trả hàng, có nhiều bản ghi nguồn cho một nhân viên. Cần quyết định:

- Dữ liệu trùng là lỗi và phải sửa nguồn.
- Chỉ lấy bản ghi có trạng thái được duyệt.
- Lấy bản ghi có thời gian hiệu lực mới nhất.
- Tổng hợp các hàng nguồn theo một quy tắc nghiệp vụ.

### 9.1. Chọn bản ghi mới nhất bằng ROW_NUMBER

Nếu bảng nguồn có nhiều phiên bản nhưng nghiệp vụ quy định lấy bản ghi mới nhất:

```sql
UPDATE employees e
SET salary = (
    SELECT new_salary
    FROM (
        SELECT a.new_salary,
               ROW_NUMBER() OVER (
                   PARTITION BY a.employee_id
                   ORDER BY a.effective_at DESC, a.adjustment_id DESC
               ) AS rn
        FROM salary_adjustments a
        WHERE a.employee_id = e.employee_id
    )
    WHERE rn = 1
)
WHERE EXISTS (
    SELECT 1
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
);
```

`adjustment_id` là tie-breaker để thứ tự chọn hàng xác định nếu nhiều điều chỉnh có cùng `EFFECTIVE_AT`. Subquery trong SET vẫn phải trả tối đa một hàng.

Nếu có thể, hãy bảo đảm tính duy nhất bằng constraint phù hợp thay vì chỉ dựa vào truy vấn. Việc chọn “mới nhất” phải có định nghĩa rõ về thời gian hiệu lực và trạng thái hợp lệ.

### 9.2. Tổng hợp nguồn trước khi cập nhật

Nếu yêu cầu là tổng hợp doanh thu đơn hàng:

```sql
UPDATE customers c
SET total_spent = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Aggregate không có GROUP BY trả một hàng, nên `SUM` là một giá trị scalar. Nếu cần nhiều chỉ tiêu, có thể gán tuple:

```sql
UPDATE customers c
SET (total_spent, order_count) = (
    SELECT SUM(o.total_amount),
           COUNT(*)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Subquery aggregate trả một hàng cho mỗi khách hàng được xử lý. `WHERE EXISTS` trong ví dụ giới hạn chỉ khách hàng có ít nhất một đơn hàng.

## 10. UPDATE từ truy vấn con với điều kiện phức tạp

### 10.1. Chỉ cập nhật khi giá trị nguồn khác giá trị hiện tại

```sql
UPDATE products p
SET unit_price = (
    SELECT s.proposed_price
    FROM price_staging s
    WHERE s.product_id = p.product_id
)
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
      AND s.proposed_price <> p.unit_price
);
```

Nếu một trong hai giá trị có thể NULL, phép `<>` có thể cho UNKNOWN. Nếu cần phát hiện thay đổi bao gồm NULL, phải biểu đạt riêng quy tắc so sánh NULL-safe:

```sql
WHERE EXISTS (
    SELECT 1
    FROM price_staging s
    WHERE s.product_id = p.product_id
      AND (
             s.proposed_price <> p.unit_price
          OR (s.proposed_price IS NULL AND p.unit_price IS NOT NULL)
          OR (s.proposed_price IS NOT NULL AND p.unit_price IS NULL)
      )
)
```

### 10.2. Cập nhật từ một truy vấn đã GROUP BY

```sql
UPDATE departments d
SET annual_sales = (
    SELECT SUM(o.total_amount)
    FROM orders o
    WHERE o.department_id = d.department_id
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2027-01-01'
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.department_id = d.department_id
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2027-01-01'
);
```

Đây là scalar aggregate theo từng phòng ban. Điều kiện khoảng nửa mở giúp bao gồm toàn bộ ngày trong năm 2026 nếu `ORDER_DATE` có phần thời gian.

### 10.3. Cập nhật nhiều cột từ một nhóm dữ liệu

```sql
UPDATE customers c
SET (total_order_count, total_spent, last_order_date) = (
    SELECT COUNT(*),
           SUM(o.total_amount),
           MAX(o.order_date)
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Các chỉ tiêu được tính từ cùng tập đơn hàng của khách hàng. `COUNT(*)` đếm hàng; `SUM` và `MAX` bỏ qua giá trị NULL ở biểu thức tương ứng.

## 11. UPDATE với truy vấn con ở WHERE

Subquery không chỉ nằm trong SET. Nó còn có thể xác định hàng đích.

### 11.1. Dùng IN

```sql
UPDATE employees
SET bonus = 1000
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

Những nhân viên thuộc phòng ban ở địa điểm 1700 được cập nhật.

### 11.2. Dùng EXISTS

```sql
UPDATE customers c
SET status = 'VIP'
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.total_amount >= 100000000
);
```

Khách hàng được đặt trạng thái VIP nếu tồn tại ít nhất một đơn hàng đạt ngưỡng. `EXISTS` không nhân bản hàng đích khi có nhiều đơn hàng phù hợp.

### 11.3. Kết hợp SET subquery và WHERE subquery

```sql
UPDATE employees e
SET salary = (
    SELECT a.new_salary
    FROM salary_adjustments a
    WHERE a.employee_id = e.employee_id
)
WHERE e.department_id = 20
  AND EXISTS (
      SELECT 1
      FROM salary_adjustments a
      WHERE a.employee_id = e.employee_id
  );
```

Điều kiện ngoài giới hạn phòng ban; EXISTS bảo đảm có nguồn; subquery SET lấy giá trị mới. Ba phần có trách nhiệm riêng và nên được đọc tách bạch.

## 12. UPDATE từ truy vấn con và UPDATE ... FROM theo phiên bản

Trong nhiều phiên bản Oracle truyền thống, cách phổ biến để cập nhật một bảng từ bảng khác là dùng **scalar subquery hoặc tuple subquery trong SET**, thường đi kèm `EXISTS`:

```sql
UPDATE target_table t
SET target_value = (
    SELECT s.source_value
    FROM source_table s
    WHERE s.key_id = t.key_id
)
WHERE EXISTS (
    SELECT 1
    FROM source_table s
    WHERE s.key_id = t.key_id
);
```

Không bê nguyên cú pháp `UPDATE ... FROM` của PostgreSQL hoặc SQL Server sang một database Oracle cũ và giả định nó được hỗ trợ. Cú pháp `UPDATE ... FROM` là khả năng phụ thuộc phiên bản Oracle; nếu hệ thống đích có hỗ trợ phần mở rộng này, hãy xác nhận cú pháp trong SQL Language Reference đúng release đang chạy và kiểm tra tính duy nhất của nguồn join. Các ví dụ trong bài dùng subquery truyền thống để dễ áp dụng trên nhiều phiên bản Oracle hơn.

### 12.1. Khi nào nên cân nhắc MERGE?

Nếu yêu cầu là đồng bộ dữ liệu từ một nguồn và có cả hai trường hợp:

- Hàng đích đã tồn tại: cập nhật.
- Hàng đích chưa tồn tại: thêm mới.

thì `MERGE` thường diễn đạt rõ hơn:

```sql
MERGE INTO employees e
USING employee_updates s
   ON (e.employee_id = s.employee_id)
WHEN MATCHED THEN
    UPDATE SET
        e.salary = s.new_salary,
        e.department_id = s.new_department_id;
```

Ví dụ trên chỉ cập nhật hàng đã khớp. Nếu cần thêm mới, có thể bổ sung `WHEN NOT MATCHED THEN INSERT (...) VALUES (...)` theo quy tắc dữ liệu. `MERGE` là một câu lệnh riêng, không phải một cách viết khác của `UPDATE`; bài này tập trung vào UPDATE một bảng.

### 12.2. MERGE cũng cần kiểm soát nguồn trùng

Nếu nguồn có nhiều hàng cùng khớp một hàng đích, `MERGE` có thể báo lỗi như `ORA-30926` trong tình huống một hàng đích bị tác động nhiều lần. Hãy chuẩn hóa nguồn về một hàng cho mỗi khóa trước khi MERGE.

## 13. RETURNING: nhận giá trị sau UPDATE

Oracle hỗ trợ `RETURNING ... INTO` để lấy giá trị của cột được cập nhật mà không cần chạy một SELECT riêng trong một số trường hợp.

Ví dụ cập nhật một nhân viên:

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE employee_id = 100
RETURNING salary INTO :new_salary;
```

` :new_salary` là bind/host variable do công cụ hoặc ứng dụng cung cấp. Trong PL/SQL:

```sql
DECLARE
    v_new_salary employees.salary%TYPE;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = 100
    RETURNING salary INTO v_new_salary;

    DBMS_OUTPUT.PUT_LINE('New salary: ' || v_new_salary);
END;
/
```

Ví dụ giả định điều kiện cập nhật tối đa một hàng. Nếu UPDATE tác động nhiều hàng, cách nhận kết quả cần dùng cơ chế phù hợp, chẳng hạn `RETURNING BULK COLLECT INTO` trong PL/SQL khi thích hợp.

`RETURNING` không tự `COMMIT`; transaction vẫn do caller quản lý.

## 14. UPDATE, constraint và trigger

### 14.1. Constraint được kiểm tra

UPDATE phải tuân thủ constraint của bảng:

- `NOT NULL`: không được đặt cột bắt buộc thành NULL.
- `CHECK`: giá trị mới phải thỏa điều kiện kiểm tra.
- `UNIQUE`: giá trị mới không được tạo trùng theo phạm vi constraint.
- `PRIMARY KEY`: khóa chính vẫn phải duy nhất và non-NULL.
- `FOREIGN KEY`: giá trị tham chiếu phải hợp lệ theo quan hệ và hành động tham chiếu.

Ví dụ:

```sql
UPDATE inventory
SET quantity = -5
WHERE product_id = 100;
```

Nếu có `CHECK (quantity >= 0)`, UPDATE sẽ thất bại vì vi phạm constraint. Oracle thường báo lỗi constraint tương ứng; transaction statement bị lỗi và cần xử lý theo trạng thái transaction.

### 14.2. Trigger có thể chạy khi UPDATE

Nếu bảng có trigger `BEFORE UPDATE` hoặc `AFTER UPDATE`, trigger có thể thực hiện logic bổ sung khi câu UPDATE tác động hàng. Vì vậy, kết quả thực tế có thể bao gồm các thay đổi do trigger thực hiện.

Trước khi chạy UPDATE hàng loạt trên bảng nghiệp vụ, hãy hiểu các trigger liên quan và tác động của chúng. Không vô hiệu hóa trigger chỉ để làm câu lệnh chạy nhanh nếu chưa có quy trình quản trị được phê duyệt.

### 14.3. Cập nhật giá trị giống giá trị cũ

Một câu UPDATE vẫn có thể nhắm đến hàng ngay cả khi biểu thức mới bằng giá trị cũ. Điều này có thể kích hoạt trigger và tạo undo/redo. Nếu chỉ muốn cập nhật khi giá trị thay đổi, thêm điều kiện so sánh phù hợp và xử lý NULL rõ ràng.

## 15. Transaction, khóa hàng và tính an toàn

### 15.1. UPDATE tạo thay đổi trong transaction

Ví dụ:

```sql
UPDATE accounts
SET status = 'SUSPENDED'
WHERE account_id = 5001;

-- Kiểm tra kết quả trong cùng transaction:
SELECT account_id, status
FROM accounts
WHERE account_id = 5001;

-- Xác nhận:
COMMIT;

-- Hoặc hủy thay đổi chưa commit:
-- ROLLBACK;
```

Trong môi trường tương tác, hãy kiểm tra số hàng bị tác động và giá trị mới trước khi commit nếu quy trình cho phép. Trong ứng dụng, transaction boundary thường do service hoặc transaction manager quản lý.

### 15.2. SAVEPOINT để quay lui một phần

```sql
SAVEPOINT before_price_update;

UPDATE products
SET unit_price = unit_price * 1.10
WHERE category_id = 30;

-- Nếu cần hủy riêng thay đổi sau savepoint:
ROLLBACK TO before_price_update;
```

`ROLLBACK TO SAVEPOINT` quay lui các thay đổi sau savepoint mà không hủy toàn bộ transaction trước đó. Sau đó có thể tiếp tục công việc hoặc rollback toàn transaction.

### 15.3. UPDATE khóa các hàng được tác động

Oracle sử dụng khóa hàng để điều phối các transaction cùng thay đổi dữ liệu. Một UPDATE lớn có thể giữ nhiều khóa đến khi commit hoặc rollback, làm transaction khác phải chờ nếu cùng cập nhật các hàng đó.

Thực hành tốt:

- Giới hạn tập hàng bằng WHERE chính xác.
- Chia lô khi cập nhật khối lượng rất lớn nếu nghiệp vụ cho phép.
- Giữ transaction ngắn.
- Tránh gọi API hoặc chờ thao tác người dùng trong lúc đang giữ transaction mở.
- Xử lý retry có kiểm soát khi gặp deadlock/lock wait theo chính sách ứng dụng.

### 15.4. Không tự COMMIT sau mọi câu UPDATE

`COMMIT` xác nhận tất cả thay đổi của transaction hiện tại, không chỉ câu UPDATE vừa chạy. Trong ứng dụng nhiều bước, hãy đặt commit tại ranh giới nghiệp vụ thích hợp. Nếu mỗi câu lệnh tự commit, bạn có thể không rollback được toàn bộ thao tác khi bước sau thất bại.

## 16. UPDATE với JDBC

Trong Java, dùng `PreparedStatement` để truyền giá trị qua bind parameter. Không nối dữ liệu người dùng vào chuỗi SQL.

### 16.1. Cập nhật một cột

```java
String sql = """
    UPDATE employees
    SET salary = ?
    WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("25000.00"));
    ps.setLong(2, 100L);

    int rowsUpdated = ps.executeUpdate();
    if (rowsUpdated == 0) {
        // Không có nhân viên phù hợp.
    } else if (rowsUpdated == 1) {
        // Đã cập nhật đúng một nhân viên.
    } else {
        // Điều kiện không duy nhất như kỳ vọng; xử lý theo nghiệp vụ.
    }
}
```

Text block `"""` yêu cầu Java 15 trở lên. Với Java cũ hơn, viết SQL thành chuỗi nối dòng bằng dấu `+`.

### 16.2. Cập nhật nhiều cột

```java
String sql =
    "UPDATE employees " +
    "SET salary = ?, commission_pct = ?, updated_at = SYSTIMESTAMP " +
    "WHERE employee_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("28000.00"));
    ps.setBigDecimal(2, new BigDecimal("0.12"));
    ps.setLong(3, 100L);

    int rowsUpdated = ps.executeUpdate();
}
```

`executeUpdate()` trả về số hàng bị tác động. Không dùng `executeQuery()` cho câu UPDATE.

### 16.3. Truyền NULL có kiểu

```java
if (newSalary == null) {
    ps.setNull(1, java.sql.Types.NUMERIC);
} else {
    ps.setBigDecimal(1, newSalary);
}
```

Bind SQL NULL cần kiểu JDBC phù hợp. Trước khi đặt cột về NULL, phải biết cột có cho phép NULL hay không và ý nghĩa nghiệp vụ của thao tác.

### 16.4. Quản lý transaction

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory SET quantity = quantity - ? WHERE product_id = ?")) {
    ps.setInt(1, 3);
    ps.setLong(2, 2001L);

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new IllegalStateException("Unexpected update count: " + rows);
    }

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
```

Đoạn code minh họa transaction do ứng dụng quản lý; trong ứng dụng thực tế, cần bảo đảm rollback cũng được gọi nếu lỗi xảy ra trước khi vào phần `try` thích hợp, đồng thời khôi phục trạng thái auto-commit theo chính sách quản lý connection/pool.

## 17. Quy trình an toàn trước khi chạy UPDATE

Một quy trình thực tế có thể gồm:

**Bước 1 — Xác định hàng đích**

Viết điều kiện WHERE trước và chạy SELECT với cùng điều kiện:

```sql
SELECT employee_id, salary
FROM employees
WHERE department_id = 20
  AND status = 'ACTIVE';
```

**Bước 2 — Kiểm tra nguồn nếu có subquery**

```sql
SELECT employee_id, COUNT(*) AS source_rows
FROM salary_adjustments
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

Đảm bảo nguồn có tối đa một hàng cho mỗi khóa đích, hoặc đã có quy tắc chọn/tổng hợp.

**Bước 3 — Xác định chính sách không có nguồn**

Quyết định giữ giá trị cũ, đặt NULL, đặt default hay chỉ cập nhật hàng có nguồn. Dùng `EXISTS`, `CASE` hoặc `NVL` phù hợp.

**Bước 4 — Xác định kiểu và constraint**

Kiểm tra precision, scale, độ dài, NOT NULL, CHECK, UNIQUE, khóa ngoại và trigger.

**Bước 5 — Chạy UPDATE và kiểm tra số hàng**

Trong SQL Developer hoặc SQLcl, quan sát thông báo số hàng được cập nhật. Trong JDBC, đọc kết quả `executeUpdate()`.

**Bước 6 — Kiểm tra dữ liệu sau cập nhật**

```sql
SELECT employee_id, salary
FROM employees
WHERE department_id = 20
  AND status = 'ACTIVE';
```

**Bước 7 — COMMIT hoặc ROLLBACK**

Chỉ commit khi kết quả đúng và transaction đang ở trạng thái phù hợp.

## 18. Lỗi thường gặp khi UPDATE từ subquery

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-01427: single-row subquery returns more than one row` | Subquery SET trả nhiều hàng cho một hàng đích | Kiểm tra uniqueness, lọc trạng thái, aggregate hoặc chọn một hàng có ORDER BY xác định |
| Giá trị đích bất ngờ thành NULL | Scalar subquery không trả hàng và không có điều kiện giới hạn hàng đích | Thêm EXISTS nếu chỉ cập nhật khi có nguồn; hoặc quy định rõ chính sách NULL |
| `ORA-01407: cannot update (...) to NULL` | Cột NOT NULL nhận NULL | Kiểm tra nguồn, NULL policy và constraint |
| `ORA-02290` | Giá trị mới vi phạm CHECK constraint | Điều chỉnh dữ liệu/logic theo miền hợp lệ |
| `ORA-00001` | Giá trị mới vi phạm unique/primary key | Kiểm tra trùng và khóa |
| `ORA-02291` | Giá trị khóa ngoại không có hàng cha | Kiểm tra dữ liệu tham chiếu |
| Cập nhật quá nhiều hàng | Thiếu WHERE hoặc điều kiện không đủ chặt | Chạy SELECT cùng điều kiện, kiểm tra row count |
| Cập nhật không hàng nào | Không có hàng thỏa WHERE, hoặc EXISTS không tìm được nguồn | Kiểm tra khóa, kiểu dữ liệu và dữ liệu nguồn |
| Nhiều cột nhận sai dữ liệu | Thứ tự cột và SELECT list không tương ứng | Đối chiếu từng vị trí của tuple assignment |
| Giá trị tính toán không như mong đợi | Nhầm lẫn giữa giá trị cũ và giá trị mới trong cùng SET | Viết lại biểu thức đầy đủ hoặc dùng subquery/CTE phù hợp |
| UPDATE chậm hoặc chặn session khác | Quá nhiều hàng, index/điều kiện chưa phù hợp, transaction mở lâu | Giới hạn hàng, xem plan, xử lý theo lô và commit đúng ranh giới |

### 18.1. Phân biệt ORA-01427 và dữ liệu trùng nguồn

Không phải cứ thêm `MAX()` là giải quyết đúng lỗi ORA-01427:

```sql
SET salary = (
    SELECT MAX(new_salary)
    FROM salary_adjustments
    WHERE employee_id = e.employee_id
)
```

Câu này chạy được vì aggregate trả một hàng, nhưng nó chọn mức lương cao nhất. Nếu nghiệp vụ cần bản ghi mới nhất theo `EFFECTIVE_AT`, MAX lương có thể sai. Hãy chọn quy tắc nghiệp vụ trước rồi mới chọn SQL.

### 18.2. Subquery aggregate không GROUP BY

```sql
SELECT COUNT(*), SUM(amount)
FROM payments
WHERE customer_id = :id
```

Aggregate không có `GROUP BY` trả một hàng ngay cả khi không có bản ghi phù hợp. `COUNT(*)` là 0, `SUM(amount)` là NULL. Điều này khác subquery thông thường không có hàng, dù một scalar subquery rỗng cũng biểu diễn thành NULL.

## 19. Bài thực hành tổng hợp

Các bước dưới đây tạo bảng riêng trong schema thực hành. Chỉ chạy khi có quyền tạo bảng và không dùng tên bảng trùng với dữ liệu hiện có.

### Bước 1. Tạo bảng nhân viên

```sql
CREATE TABLE demo_update_employees (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER,
    salary NUMBER(12, 2),
    email VARCHAR2(150),
    updated_at TIMESTAMP
);
```

### Bước 2. Tạo bảng nguồn điều chỉnh

```sql
CREATE TABLE demo_salary_updates (
    employee_id NUMBER NOT NULL,
    new_salary NUMBER(12, 2),
    new_email VARCHAR2(150)
);
```

### Bước 3. Chèn dữ liệu mẫu

```sql
INSERT INTO demo_update_employees
VALUES (1, 'An', 10, 10000, 'an@example.test', SYSTIMESTAMP);

INSERT INTO demo_update_employees
VALUES (2, 'Binh', 10, 12000, 'binh@example.test', SYSTIMESTAMP);

INSERT INTO demo_update_employees
VALUES (3, 'Chi', 20, 15000, 'chi@example.test', SYSTIMESTAMP);

INSERT INTO demo_salary_updates
VALUES (1, 11000, 'an.new@example.test');

INSERT INTO demo_salary_updates
VALUES (2, 13200, 'binh.new@example.test');

COMMIT;
```

Nhân viên 3 không có hàng nguồn điều chỉnh.

### Bước 4. Xem hàng đích và nguồn trước UPDATE

```sql
SELECT e.employee_id,
       e.salary AS old_salary,
       s.new_salary,
       e.email AS old_email,
       s.new_email
FROM demo_update_employees e
LEFT JOIN demo_salary_updates s
  ON s.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Xác nhận nhân viên 1 và 2 có nguồn; nhân viên 3 không có nguồn.

### Bước 5. Cập nhật hai cột từ subquery

```sql
UPDATE demo_update_employees e
SET (salary, email) = (
    SELECT s.new_salary,
           s.new_email
    FROM demo_salary_updates s
    WHERE s.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM demo_salary_updates s
    WHERE s.employee_id = e.employee_id
);
```

Chỉ nhân viên 1 và 2 được cập nhật. Nhân viên 3 giữ nguyên lương và email.

### Bước 6. Kiểm tra kết quả

```sql
SELECT employee_id,
       employee_name,
       salary,
       email,
       updated_at
FROM demo_update_employees
ORDER BY employee_id;
```

### Bước 7. Thử tình huống nguồn trùng

Chỉ thực hiện trong bảng demo:

```sql
INSERT INTO demo_salary_updates
VALUES (1, 11500, 'an.second@example.test');

COMMIT;
```

Thử chạy lại câu UPDATE ở bước 5. Subquery cho nhân viên 1 giờ trả hai hàng, nên có thể gặp `ORA-01427`. Sau khi quan sát, kiểm tra:

```sql
SELECT employee_id, COUNT(*) AS source_count
FROM demo_salary_updates
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

### Bước 8. Dọn dữ liệu thử nghiệm

Nếu chỉ muốn xóa dòng trùng vừa thêm:

```sql
DELETE FROM demo_salary_updates
WHERE employee_id = 1
  AND new_salary = 11500;

COMMIT;
```

Sau đó, nếu không cần giữ bảng demo và đã xác nhận đúng đối tượng do mình tạo:

```sql
DROP TABLE demo_salary_updates PURGE;
DROP TABLE demo_update_employees PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 20. Quy tắc ghi nhớ

| Nhu cầu | Cách viết |
|---|---|
| Cập nhật một cột | `SET col = expression` |
| Cập nhật nhiều cột | `SET col1 = expr1, col2 = expr2` |
| Gán nhiều cột từ cùng một hàng nguồn | `SET (col1, col2) = (SELECT expr1, expr2 ...)` |
| Lấy giá trị từ bảng khác | Scalar subquery tương quan trong SET |
| Chỉ cập nhật hàng có dữ liệu nguồn | Kết hợp `WHERE EXISTS (...)` |
| Không có nguồn thì giữ nguyên hàng | Giới hạn hàng bằng EXISTS hoặc CASE |
| Không có nguồn thì đặt NULL | Cho phép scalar subquery rỗng, nhưng phải có chủ đích |
| Nguồn có nhiều hàng | Chuẩn hóa khóa, aggregate hoặc chọn một hàng theo quy tắc xác định |
| Kiểm tra hàng bị tác động | `SELECT` cùng WHERE trước UPDATE; đọc row count sau UPDATE |
| Nhận giá trị sau UPDATE | `RETURNING ... INTO` khi phù hợp |
| Cập nhật hoặc thêm mới | Cân nhắc `MERGE` |
| Quản lý thay đổi | `COMMIT`, `ROLLBACK`, `SAVEPOINT` |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Nếu UPDATE không có WHERE thì điều gì xảy ra?

**Trả lời:** Mọi hàng trong bảng đều nằm trong tập đích của UPDATE.

**Câu 2.** Cách viết nào cập nhật ba cột trong cùng một câu lệnh?

**Trả lời:** Liệt kê ba phép gán trong SET, ngăn cách bằng dấu phẩy.

**Câu 3.** `SET (a,b) = (SELECT x,y ...)` yêu cầu điều gì?

**Trả lời:** Số biểu thức và thứ tự phải khớp với danh sách cột; subquery cho mỗi hàng đích phải trả tối đa một hàng.

**Câu 4.** Scalar subquery trong SET không trả hàng thì giá trị là gì?

**Trả lời:** Giá trị scalar là NULL. Nếu không muốn cập nhật hàng đích thành NULL, hãy giới hạn hàng bằng EXISTS hoặc viết chính sách khác.

**Câu 5.** Subquery trong SET trả nhiều hàng thì lỗi thường gặp là gì?

**Trả lời:** `ORA-01427: single-row subquery returns more than one row`.

**Câu 6.** Vì sao dùng EXISTS cùng scalar subquery?

**Trả lời:** EXISTS ngăn cập nhật các hàng đích không có bản ghi nguồn; nó không thay thế việc bảo đảm subquery nguồn có tối đa một hàng.

**Câu 7.** Aggregate không GROUP BY có trả hàng khi không có dữ liệu phù hợp không?

**Trả lời:** Có. `COUNT(*)` trả 0, `SUM`/`AVG` có thể trả NULL.

**Câu 8.** Có nên thêm MAX vào mọi scalar subquery để tránh ORA-01427 không?

**Trả lời:** Không. MAX chỉ đúng khi nghiệp vụ thực sự cần giá trị lớn nhất; nếu cần bản ghi mới nhất, phải chọn theo thời gian và tie-breaker.

**Câu 9.** UPDATE có tự COMMIT không?

**Trả lời:** Không. DML nằm trong transaction; cần COMMIT hoặc ROLLBACK theo ranh giới nghiệp vụ.

**Câu 10.** Làm sao kiểm tra số hàng JDBC cập nhật?

**Trả lời:** Gọi `PreparedStatement.executeUpdate()` và kiểm tra số nguyên trả về.

**Câu 11.** Nếu cần vừa cập nhật hàng có sẵn vừa thêm hàng chưa có, nên cân nhắc lệnh nào?

**Trả lời:** `MERGE`, với điều kiện nguồn và khóa match được xác định rõ.

**Câu 12.** Tại sao không nên giả định thứ tự các phép gán SET làm cột sau đọc giá trị mới của cột trước?

**Trả lời:** Các biểu thức UPDATE được tính từ giá trị hàng trước khi cập nhật; nếu cần dùng giá trị mới, hãy viết lại biểu thức đầy đủ hoặc cấu trúc subquery phù hợp.

## 22. Kết luận

`UPDATE` thay đổi dữ liệu của một bảng và có thể cập nhật một hoặc nhiều cột trong cùng một câu lệnh. Với giá trị lấy từ truy vấn con, Oracle cho phép dùng scalar subquery trong `SET`, hoặc gán một nhóm cột bằng tuple subquery. Các biểu thức phải đúng thứ tự và subquery cho mỗi hàng đích phải trả tối đa một hàng.

Điểm cần kiểm soát nhất là trường hợp nguồn không có hàng hoặc có nhiều hàng. Scalar subquery rỗng cho giá trị NULL; nếu không có `WHERE EXISTS`, câu UPDATE có thể đặt NULL vào các cột đích ngoài dự kiến. Subquery nhiều hàng gây `ORA-01427`, vì vậy phải bảo đảm tính duy nhất, tổng hợp theo quy tắc nghiệp vụ hoặc chọn một bản ghi có thứ tự xác định. Khi cập nhật nhiều cột, kiểm tra ánh xạ vị trí giữa cột đích và biểu thức nguồn.

Trước khi chạy trên dữ liệu thật, hãy xác nhận tập hàng bằng SELECT, kiểm tra nguồn, constraint và trigger, theo dõi số hàng bị tác động, rồi `COMMIT` hoặc `ROLLBACK` theo transaction. Trong Java/JDBC, dùng bind parameter, `executeUpdate()` và transaction boundary rõ ràng. Những bước này giúp UPDATE vừa chính xác về dữ liệu vừa an toàn trong ứng dụng Oracle.
