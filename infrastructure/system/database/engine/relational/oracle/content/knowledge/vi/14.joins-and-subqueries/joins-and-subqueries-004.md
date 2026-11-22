# Vị trí điều kiện trong ON/WHERE và ảnh hưởng đến OUTER JOIN trong Oracle

Khi viết truy vấn lấy phòng ban cùng nhân viên, ta thường muốn hiển thị **mọi phòng ban**, kể cả phòng ban chưa có nhân viên. Câu lệnh phù hợp là `LEFT OUTER JOIN`. Nhưng nếu sau đó thêm điều kiện lọc trạng thái nhân viên vào `WHERE`, những phòng ban không có nhân viên có thể biến mất khỏi kết quả. Truy vấn vẫn chạy bình thường, không báo lỗi, nhưng ý nghĩa đã thay đổi.

Đây là một trong những lỗi logic JOIN phổ biến nhất: **đặt một điều kiện ở `ON` hay `WHERE` có thể làm thay đổi kết quả OUTER JOIN**. Hai vị trí không thể hoán đổi tùy ý. `ON` xác định hai phía có khớp để tạo một hàng JOIN hay không; `WHERE` lọc các hàng của kết quả JOIN sau khi Oracle đã tạo những hàng NULL mở rộng cho phía không có đối tác.

Bài học thuộc nhóm **JOIN và truy vấn con** của Oracle Database. Ta sẽ dùng ví dụ phòng ban/nhân viên để phân biệt `INNER JOIN`, `LEFT OUTER JOIN`, `RIGHT OUTER JOIN` và `FULL OUTER JOIN`; xem điều kiện trên phía được bảo toàn và phía được ghép; xử lý NULL; viết anti-join và đọc các lỗi thường gặp.

Sau bài này, bạn có thể:

- Giải thích vai trò của điều kiện kết nối trong `ON` và điều kiện lọc kết quả trong `WHERE`.
- Dự đoán điều gì xảy ra khi đặt điều kiện của bảng bên phải vào `ON` hoặc `WHERE` của `LEFT JOIN`.
- Nhận biết khi nào một điều kiện trong `WHERE` làm OUTER JOIN có kết quả giống INNER JOIN.
- Hiểu vì sao `WHERE right_table.column IS NULL` có thể dùng để tìm dòng không có đối tác, và vì sao phải kiểm tra một cột khóa không NULL.
- Viết điều kiện nhiều cột, điều kiện ngày giờ, `OR`, `IS NULL` và điều kiện có nhiều bảng mà không vô tình loại mất hàng được bảo toàn.
- Phân biệt ngữ nghĩa SQL với cách Oracle optimizer biến đổi execution plan.

> **Phạm vi ví dụ:** Cú pháp dùng ANSI JOIN trong Oracle Database 19c. Các bảng `DEPARTMENTS` và `EMPLOYEES` ở phần thực hành là bảng lab độc lập. Không dùng DDL hoặc dữ liệu mẫu trên schema ứng dụng đang hoạt động.

## 1. Hai nơi đặt điều kiện có vai trò khác nhau

Một câu SELECT có JOIN thường có cấu trúc:

~~~sql
SELECT ...
FROM table_a a
LEFT JOIN table_b b
    ON a.key_col = b.key_col
WHERE ...;
~~~

Hãy phân biệt:

| Vị trí | Câu hỏi nó trả lời | Thời điểm logic |
| --- | --- | --- |
| `ON` | Hai dòng từ hai nguồn có được coi là một cặp khớp nhau không? | Khi xác định các cặp JOIN |
| `WHERE` | Sau khi JOIN tạo result set, dòng nào được giữ lại? | Sau JOIN và bước NULL extension của OUTER JOIN |

Ví dụ:

~~~sql
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
WHERE d.department_id < 50;
~~~

- Điều kiện `e.department_id = d.department_id` xác định quan hệ phòng ban/nhân viên.
- Điều kiện `e.status = 'ACTIVE'` xác định nhân viên nào được phép khớp với phòng ban.
- Điều kiện `d.department_id < 50` lọc các phòng ban trong kết quả cuối.

Với `LEFT JOIN`, nếu một phòng ban không có nhân viên ACTIVE phù hợp, Oracle vẫn giữ dòng phòng ban và đặt các cột của `EMPLOYEES` thành NULL. Đây là điểm khác biệt quan trọng so với việc chuyển điều kiện trạng thái xuống `WHERE`.

### 1.1. Luồng xử lý khái niệm của LEFT OUTER JOIN

~~~text
Bang ben trai (DEPARTMENTS)       Bang ben phai (EMPLOYEES)
              |                              |
              +--------------+---------------+
                             |
                             v
                       DIEU KIEN ON
                  Xac dinh cap dong khop nhau
                             |
               +-------------+-------------+
               |                           |
             Co khop                   Khong co khop
               |                           |
               v                           v
          Ghep hai dong              Giu dong ben trai
                                     cot ben phai = NULL
               |                           |
               +-------------+-------------+
                             |
                             v
                       KET QUA JOIN
                             |
                             v
                       DIEU KIEN WHERE
                             |
                             v
                    CAC DONG CON LAI
~~~

Đây là cách hiểu ngữ nghĩa, không phải thứ tự vật lý bắt buộc của các bước trong execution plan. Oracle optimizer có thể đẩy điều kiện, đổi thứ tự join hoặc dùng thuật toán hash/nested loops/merge join nếu vẫn giữ nguyên kết quả theo ngữ nghĩa SQL.

## 2. INNER JOIN: điều kiện ON và WHERE thường có thể tương đương

Với `INNER JOIN`, chỉ những cặp dòng thỏa điều kiện kết nối mới được giữ lại. Ví dụ:

~~~sql
-- Dieu kien loc nhan vien nam ngay trong ON:
SELECT d.department_id, e.employee_id, e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';

-- Dieu kien loc nhan vien dat trong WHERE:
SELECT d.department_id, e.employee_id, e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

Trong ví dụ này, hai truy vấn có cùng ngữ nghĩa kết quả: chỉ các cặp phòng ban/nhân viên có cùng department và nhân viên ACTIVE được trả về. Với INNER JOIN, điều kiện chỉ tham chiếu đến các nguồn trong phép join có thể thường được đặt trong `ON` hoặc `WHERE` mà không đổi tập kết quả.

Tuy nhiên, nên giữ điều kiện **quan hệ giữa hai bảng** trong `ON` và điều kiện **lọc nghiệp vụ** trong `WHERE` để SQL dễ đọc:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
  AND d.location_id = 1700;
~~~

Đối với INNER JOIN, optimizer có thể biến đổi điều kiện giữa ON/WHERE. Nhưng không suy rộng kết luận này sang OUTER JOIN: ở OUTER JOIN, việc giữ lại hàng không khớp là một phần của ngữ nghĩa.

## 3. LEFT OUTER JOIN: phía trái được bảo toàn

### 3.1. LEFT JOIN cơ bản

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Oracle trả:

- Mỗi cặp phòng ban/nhân viên có department_id khớp.
- Một dòng cho mỗi phòng ban không có nhân viên khớp, với các cột phía nhân viên là NULL.
- Nếu một phòng ban có nhiều nhân viên, phòng ban xuất hiện nhiều dòng, một dòng cho mỗi nhân viên khớp.

`LEFT JOIN` là cách viết ngắn của `LEFT OUTER JOIN`.

### 3.2. Điều kiện trên bảng phải đặt trong ON

Yêu cầu: hiển thị **mọi phòng ban**, kèm nhân viên đang ACTIVE nếu có.

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

Điều kiện trạng thái là một phần của quy tắc khớp nhân viên. Những nhân viên INACTIVE không được ghép. Nếu một phòng ban chỉ có nhân viên INACTIVE, phòng ban vẫn xuất hiện với cột nhân viên NULL.

### 3.3. Đặt cùng điều kiện trong WHERE làm đổi kết quả

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

Truy vấn này chỉ giữ các hàng sau JOIN mà `e.status = 'ACTIVE'` là TRUE. Với phòng ban không có nhân viên, `e.status` là NULL do NULL extension; biểu thức `NULL = 'ACTIVE'` không phải TRUE, nên hàng bị WHERE loại bỏ. Nhân viên INACTIVE cũng bị loại.

Kết quả thường giống INNER JOIN có điều kiện ACTIVE:

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

Điều này thường được gọi là **null-rejecting predicate** đối với phía phải: điều kiện WHERE không chấp nhận hàng mà các cột phía phải đã bị NULL mở rộng. Một điều kiện như vậy có thể khiến LEFT JOIN mất tác dụng bảo toàn hàng trái.

### 3.4. Ví dụ kết quả đối chiếu

Giả sử dữ liệu:

| Department | Department ID | Employee | Status |
| --- | ---: | --- | --- |
| Sales | 10 | An | ACTIVE |
| Sales | 10 | Bình | INACTIVE |
| IT | 20 | Chi | INACTIVE |
| HR | 30 | *(không có)* | *(NULL)* |
| Legal | 40 | *(không có)* | *(NULL)* |

Kết quả khi lọc trạng thái trong `ON`:

~~~sql
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE'
~~~

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| IT | NULL | NULL |
| HR | NULL | NULL |
| Legal | NULL | NULL |

Kết quả khi lọc trạng thái trong `WHERE`:

~~~sql
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
~~~

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |

IT, HR và Legal đã biến mất. Đây không phải lỗi cú pháp; truy vấn thứ hai đang yêu cầu một kết quả khác.

## 4. Điều kiện của bảng trái trong ON hay WHERE?

Một nhầm lẫn khác là nghĩ rằng mọi điều kiện lọc đều nên đặt vào `ON` để “lọc sớm”. Với LEFT JOIN, điều kiện trên **phía trái được bảo toàn** có ý nghĩa khác:

~~~sql
-- A: loc phong ban trong WHERE
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN';

-- B: dieu kien phong ban dat trong ON
SELECT d.department_id, d.department_name, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN';
~~~

**Truy vấn A:** phòng ban CLOSED bị loại khỏi kết quả. Đây thường là ý định khi báo cáo chỉ muốn xem phòng ban OPEN.

**Truy vấn B:** mọi phòng ban vẫn được bảo toàn vì DEPARTMENTS là phía trái. Với phòng ban CLOSED, điều kiện ON sai nên không có nhân viên nào khớp; Oracle vẫn trả phòng ban đó với cột nhân viên NULL.

Do đó:

- Điều kiện trên phía **được bảo toàn** thường đặt ở `WHERE` nếu muốn loại các dòng phía đó.
- Điều kiện trên phía **được ghép** thường đặt ở `ON` nếu muốn giới hạn đối tác mà không loại dòng phía được bảo toàn.

Đây là nguyên tắc đọc ý định truy vấn, không phải quy định rằng một loại điều kiện luôn bắt buộc nằm ở một vị trí. Nếu mục tiêu nghiệp vụ khác, vị trí cần thay đổi tương ứng.

## 5. NULL extension và logic ba giá trị

### 5.1. Tại sao điều kiện WHERE loại hàng không khớp?

Trong SQL, điều kiện có thể cho kết quả:

- TRUE
- FALSE
- UNKNOWN (thường do tham gia phép so sánh với NULL)

`WHERE` chỉ giữ hàng khi biểu thức điều kiện là **TRUE**. FALSE và UNKNOWN đều bị loại.

Ví dụ:

| Biểu thức | Kết quả |
| --- | --- |
| `'ACTIVE' = 'ACTIVE'` | TRUE |
| `'INACTIVE' = 'ACTIVE'` | FALSE |
| `NULL = 'ACTIVE'` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

Với LEFT JOIN không có đối tác, các cột phía phải được điền NULL. Vì thế `WHERE e.status = 'ACTIVE'` không giữ hàng chưa khớp.

### 5.2. Không phải mọi điều kiện WHERE trên phía phải đều loại hàng NULL mở rộng

Điều kiện:

~~~sql
WHERE e.employee_id IS NULL
~~~

là TRUE cho hàng không có nhân viên khớp. Điều kiện này được dùng trong anti-join ở phần sau.

Điều kiện:

~~~sql
WHERE e.status IS NULL
~~~

cũng có thể giữ hàng không khớp, nhưng nó còn giữ cả nhân viên **đã khớp** có `STATUS` thực sự NULL. Nếu mục tiêu là tìm phòng ban không có nhân viên, hãy kiểm tra cột khóa nhân viên bắt buộc NOT NULL như `EMPLOYEE_ID`, không dựa vào một cột thuộc tính có thể NULL.

### 5.3. OR không tự khôi phục mọi hàng đã mất

Một cách viết thường gây nhầm:

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
   OR e.employee_id IS NULL;
~~~

Người viết có thể nghĩ điều kiện `OR e.employee_id IS NULL` sẽ giữ mọi phòng ban không có nhân viên ACTIVE. Nhưng phòng ban IT trong ví dụ chỉ có nhân viên INACTIVE:

1. ON ghép IT với dòng Chi vì department_id khớp.
2. Vì đã có dòng khớp, Oracle không tạo thêm một dòng NULL mở rộng cho IT.
3. WHERE thấy `e.status = 'ACTIVE'` là FALSE và `e.employee_id IS NULL` cũng FALSE.
4. IT bị loại.

Nếu yêu cầu là **mọi phòng ban và chỉ nhân viên ACTIVE**, đặt trạng thái trong ON:

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';
~~~

Đây là khác biệt sâu sắc giữa “không có nhân viên nào” và “không có nhân viên thỏa điều kiện ACTIVE”. Hai yêu cầu không giống nhau.

## 6. Điều kiện nhiều cột và điều kiện thời gian trong ON

### 6.1. Ghép theo khóa và chỉ lấy dòng hợp lệ

Ví dụ lấy mọi khách hàng, kèm các đơn hàng đã thanh toán:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Khách hàng không có đơn PAID vẫn xuất hiện. Nếu đưa `o.status = 'PAID'` vào WHERE, khách hàng không có đơn phù hợp sẽ bị loại.

### 6.2. Điều kiện ngày giờ của phía phải

Yêu cầu: hiển thị mọi khách hàng cùng các đơn được tạo trong tháng 11/2026:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
   AND o.created_at <  TIMESTAMP '2026-12-01 00:00:00'
ORDER BY c.customer_id, o.created_at;
~~~

Khách hàng chỉ có đơn cũ hơn tháng 11 vẫn xuất hiện với các cột đơn hàng NULL, vì không có đơn nào thỏa **toàn bộ điều kiện ON**. Nếu chuyển hai điều kiện ngày sang WHERE, khách hàng không có đơn trong tháng 11 sẽ bị loại.

Khoảng nửa mở `>= đầu tháng` và `< đầu tháng sau` bao phủ toàn bộ phần lẻ giây, không cần đoán giá trị cuối ngày. Kiểu literal phải phù hợp kiểu cột; ví dụ trên giả định `CREATED_AT` là TIMESTAMP không timezone.

### 6.3. Điều kiện nối nhiều khóa

Một quan hệ có thể cần nhiều thành phần:

~~~sql
SELECT
    a.account_id,
    t.transaction_id
FROM accounts a
LEFT JOIN transactions t
    ON t.account_id = a.account_id
   AND t.tenant_id = a.tenant_id
   AND t.currency_code = a.currency_code
   AND t.status = 'POSTED';
~~~

Mỗi điều kiện ON góp phần xác định một giao dịch có phải đối tác phù hợp của tài khoản hay không. Nếu bỏ nhầm điều kiện tenant/currency, truy vấn có thể ghép dữ liệu sai; nếu chuyển điều kiện trạng thái sang WHERE, tài khoản không có giao dịch POSTED sẽ biến mất.

### 6.4. Điều kiện có OR trong ON

~~~sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND (o.status = 'PAID' OR o.status = 'SHIPPED');
~~~

Đây là cách giới hạn đối tác theo hai trạng thái. Dùng ngoặc để thể hiện rõ logic khi kết hợp AND/OR. Nếu biểu thức phức tạp, hãy xem xét tạo CTE lọc bảng orders trước rồi LEFT JOIN vào tập đã lọc:

~~~sql
WITH eligible_orders AS (
    SELECT order_id, customer_id, status
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
)
SELECT c.customer_id, o.order_id, o.status
FROM customers c
LEFT JOIN eligible_orders o
    ON o.customer_id = c.customer_id;
~~~

CTE diễn đạt rõ “tập đơn hàng đủ điều kiện” trước khi ghép. Cách này tương đương về mục tiêu nếu điều kiện lọc chỉ áp dụng lên nguồn orders và query không có logic khác làm thay đổi ngữ nghĩa. Optimizer có thể inline CTE; không mặc định nó luôn tạo bảng tạm vật lý.

## 7. RIGHT OUTER JOIN: phía phải được bảo toàn

`RIGHT JOIN` là ảnh đối xứng của `LEFT JOIN`. Nó bảo toàn mọi hàng của bảng bên phải, kể cả khi không có hàng phù hợp ở bên trái.

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    e.employee_name
FROM departments d
RIGHT OUTER JOIN employees e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN';
~~~

Mọi nhân viên vẫn xuất hiện. Nếu phòng ban không tồn tại hoặc không OPEN, các cột của `DEPARTMENTS` được NULL mở rộng.

Đổi vị trí bảng và dùng LEFT JOIN thường dễ đọc hơn:

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    e.employee_name
FROM employees e
LEFT JOIN departments d
    ON d.department_id = e.department_id
   AND d.status = 'OPEN';
~~~

Hai cách thể hiện cùng ý định bảo toàn bảng employees. Khi đọc truy vấn, hãy xác định **bảng nào phải giữ đủ hàng**; đừng chỉ nhìn từ khóa LEFT/RIGHT mà bỏ qua thứ tự hai nguồn.

Điều kiện của bảng được bảo toàn (ở đây là employees) nếu đặt trong ON sẽ giới hạn đối tác nhưng vẫn giữ hàng của bảng phải. Nếu muốn loại một số nhân viên, đặt điều kiện tương ứng trong WHERE.

## 8. FULL OUTER JOIN: bảo toàn cả hai phía

`FULL OUTER JOIN` giữ:

- Các cặp hàng khớp theo điều kiện ON.
- Các hàng chỉ có ở phía trái, với cột phải NULL.
- Các hàng chỉ có ở phía phải, với cột trái NULL.

Ví dụ:

~~~sql
SELECT
    a.account_id,
    a.account_name,
    b.account_id AS imported_account_id,
    b.account_name AS imported_name
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id;
~~~

Truy vấn có thể dùng để đối chiếu hai nguồn tài khoản, gồm cả bản ghi chỉ có ở một nguồn.

### 8.1. Thêm điều kiện trong ON

~~~sql
SELECT
    a.account_id,
    b.account_id AS imported_account_id
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id
   AND b.is_valid = 'Y';
~~~

Điều kiện `b.is_valid = 'Y'` giới hạn việc ghép cặp. Các hàng không thỏa điều kiện vẫn có thể xuất hiện như hàng chỉ có ở một phía của FULL OUTER JOIN:

- Một hàng A không tìm được B hợp lệ sẽ được giữ ở phía A.
- Một hàng B không hợp lệ không ghép với A và vẫn có thể được giữ ở phía B.

Đây không phải là truy vấn “chỉ lấy B hợp lệ”; ON chỉ điều khiển cặp ghép, còn FULL OUTER bảo toàn hai phía.

### 8.2. Đặt điều kiện phía phải trong WHERE

~~~sql
SELECT
    a.account_id,
    b.account_id AS imported_account_id
FROM accounts a
FULL OUTER JOIN imported_accounts b
    ON b.account_id = a.account_id
WHERE b.is_valid = 'Y';
~~~

WHERE loại hàng A-only vì `b.is_valid` là NULL ở hàng đó. Nó cũng loại các hàng B-only có `IS_VALID` không phải Y hoặc NULL. Truy vấn không còn bảo toàn đầy đủ cả hai phía theo ý nghĩa ban đầu.

Với FULL OUTER JOIN, điều kiện WHERE trên một phía có thể làm mất một trong hai loại hàng không khớp; điều kiện trên cả hai phía có thể làm thay đổi cả hai. Luôn phân tích từng loại hàng:

1. Hàng khớp.
2. Hàng chỉ bên trái.
3. Hàng chỉ bên phải.

Sau đó đánh giá biểu thức WHERE trên từng loại.

## 9. Tìm dòng không có đối tác: anti-join

Một yêu cầu phổ biến: tìm khách hàng **chưa có đơn hàng nào**. Cách viết bằng LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

`ORDER_ID` được giả định là khóa chính NOT NULL. Nếu không có đơn hàng khớp, Oracle tạo hàng mở rộng với `O.ORDER_ID = NULL`; WHERE giữ lại hàng đó. Nếu có ít nhất một đơn hàng, `O.ORDER_ID` không NULL ở các hàng khớp nên khách hàng không xuất hiện.

### 9.1. Tại sao nên kiểm tra khóa chính?

Không nên viết:

~~~sql
WHERE o.note IS NULL
~~~

nếu `NOTE` là cột cho phép NULL. Một khách hàng có đơn hàng thật nhưng `NOTE` không được nhập cũng thỏa điều kiện này, dẫn đến bị nhận nhầm là không có đơn.

Hãy kiểm tra một cột ở phía phải chắc chắn **NOT NULL khi có hàng thật**, thường là primary key.

### 9.2. NOT EXISTS là cách diễn đạt anti-join rõ ràng

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

`NOT EXISTS` diễn đạt trực tiếp “không tồn tại đơn hàng liên quan”. Oracle optimizer thường có thể biến đổi các dạng anti-join phù hợp thành kế hoạch tương ứng. Về ngữ nghĩa, đây là lựa chọn rõ ràng và tránh phải chọn một cột phía phải để kiểm tra NULL.

### 9.3. Tìm khách hàng không có đơn PAID

Yêu cầu này khác “không có đơn hàng nào”:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Khách hàng có đơn PENDING nhưng không có đơn PAID vẫn được trả về. Điều kiện trạng thái là một phần của **định nghĩa đối tác cần tìm**, nên đặt trong subquery của NOT EXISTS.

Viết tương đương bằng LEFT JOIN:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL;
~~~

Điều kiện trạng thái nằm trong ON để xác định “đơn PAID phù hợp”; WHERE kiểm tra không tìm thấy đơn phù hợp. Nếu chuyển `o.status = 'PAID'` sang WHERE, truy vấn sẽ tìm đơn PAID thay vì tìm khách hàng không có đơn PAID.

### 9.4. NOT IN và NULL

Một cách viết khác:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

Nếu subquery có ít nhất một `NULL`, biểu thức `NOT IN` có thể trở thành UNKNOWN cho các giá trị không khớp và không trả kết quả như mong muốn. `NOT EXISTS` thường an toàn, rõ nghĩa hơn cho anti-join khi cột nguồn có thể NULL. Nếu dùng NOT IN, phải kiểm soát NULL trong subquery, ví dụ:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

## 10. Điều kiện trên bảng thứ ba trong chuỗi OUTER JOIN

Giả sử muốn lấy mọi phòng ban, nhân viên ACTIVE và thông tin vị trí làm việc:

~~~sql
SELECT
    d.department_id,
    e.employee_id,
    l.location_id,
    l.city
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
LEFT JOIN locations l
    ON l.location_id = e.location_id
   AND l.country_id = 'VN'
ORDER BY d.department_id, e.employee_id;
~~~

Ý nghĩa:

- Tất cả phòng ban được giữ.
- Chỉ nhân viên ACTIVE được ghép.
- Thông tin location chỉ được ghép nếu thuộc Việt Nam.
- Nếu nhân viên không có location ở Việt Nam, phòng ban và nhân viên vẫn có thể xuất hiện, còn cột location là NULL.

Nếu thêm `WHERE l.country_id = 'VN'`, các hàng không có location phù hợp sẽ bị loại; chuỗi LEFT JOIN có thể mất tính bảo toàn mà người viết dự định.

Với nhiều OUTER JOIN nối tiếp, hãy xác định từng tầng:

1. Bảng nào được bảo toàn ở mỗi phép join?
2. Điều kiện ON giới hạn đối tác nào?
3. WHERE cuối cùng có loại hàng NULL mở rộng của tầng nào?

Đừng chỉ nhìn query dài và di chuyển mọi predicate xuống cuối cho “gọn”.

## 11. Đặt điều kiện trong inline view/CTE trước khi OUTER JOIN

Một cách tổ chức rõ ràng khác là lọc nguồn phía phải trong subquery:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, employee_name, status
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM departments d
LEFT JOIN active_employees e
    ON e.department_id = d.department_id;
~~~

CTE `ACTIVE_EMPLOYEES` chỉ chứa nhân viên ACTIVE. LEFT JOIN sau đó bảo toàn phòng ban và chỉ ghép vào tập nhân viên đã lọc.

Trong trường hợp đơn giản này, kết quả tương đương đặt `e.status = 'ACTIVE'` trong ON. Cách dùng CTE có thể dễ đọc khi điều kiện lọc phía phải dài, được tái sử dụng hoặc cần phân tách logic nghiệp vụ.

### 11.1. Không lọc sau JOIN nếu muốn giữ phía trái

Đổi thành:

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id, employee_name, status
    FROM employees
)
SELECT
    d.department_id,
    e.employee_id
FROM departments d
LEFT JOIN active_employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

thì điều kiện vẫn nằm ở WHERE và các phòng ban không có nhân viên ACTIVE bị loại. Việc dùng CTE tự nó không thay đổi ngữ nghĩa; **vị trí predicate trong query block chứa OUTER JOIN** vẫn quyết định kết quả.

### 11.2. CTE có thể chứa phép tổng hợp

Ví dụ muốn giữ mọi khách hàng và ghép tổng số đơn PAID:

~~~sql
WITH paid_order_counts AS (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    NVL(p.paid_count, 0) AS paid_count
FROM customers c
LEFT JOIN paid_order_counts p
    ON p.customer_id = c.customer_id;
~~~

Các khách hàng không có đơn PAID không có dòng trong CTE, nhưng vẫn được giữ bởi LEFT JOIN; `NVL` hiển thị số 0. Nếu chuyển điều kiện từ CTE ra WHERE sau join, cần đánh giá lại ý nghĩa NULL và khả năng loại khách hàng.

## 12. Điều kiện trong ON có thể ảnh hưởng số dòng theo nhiều cách

### 12.1. ON không phải lúc nào cũng là phép bằng khóa

LEFT JOIN có thể dùng điều kiện khoảng:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    r.price
FROM products p
LEFT JOIN price_rules r
    ON r.product_id = p.product_id
   AND p.effective_at >= r.valid_from
   AND p.effective_at <  r.valid_to;
~~~

Một sản phẩm được ghép với quy tắc giá có hiệu lực tại thời điểm xác định. Nếu không có rule phù hợp, sản phẩm vẫn xuất hiện với cột rule NULL. Điều kiện ngày nằm trong ON vì nó xác định **rule nào là đối tác phù hợp**, không phải tiêu chí loại sản phẩm.

### 12.2. Nhiều dòng khớp vẫn tạo nhiều dòng kết quả

LEFT JOIN không bảo đảm một hàng trái chỉ xuất hiện một lần. Nếu một phòng ban có 10 nhân viên ACTIVE, kết quả có 10 hàng cho phòng ban đó. Nếu muốn một hàng mỗi phòng ban, hãy tổng hợp phía phải trước:

~~~sql
WITH employee_summary AS (
    SELECT department_id, COUNT(*) AS active_count
    FROM employees
    WHERE status = 'ACTIVE'
    GROUP BY department_id
)
SELECT
    d.department_id,
    d.department_name,
    NVL(s.active_count, 0) AS active_count
FROM departments d
LEFT JOIN employee_summary s
    ON s.department_id = d.department_id;
~~~

Khi CTE có tối đa một dòng cho mỗi department_id, join trở thành một dòng cho mỗi phòng ban (giả sử department_id là khóa duy nhất của DEPARTMENTS).

### 12.3. WHERE có thể lọc theo biểu thức từ hai phía

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN'
  AND (e.salary >= 5000 OR e.employee_id IS NULL);
~~~

Biểu thức này giữ phòng ban OPEN có nhân viên lương ít nhất 5.000 và phòng ban không có nhân viên khớp; nhưng nếu phòng ban chỉ có nhân viên lương thấp hơn 5.000, nó đã có hàng khớp ở ON rồi, và tất cả hàng đó bị WHERE loại. Không có hàng NULL mở rộng bổ sung được tạo sau WHERE.

Nếu mục tiêu là “mọi phòng ban OPEN, chỉ ghép nhân viên lương từ 5.000 trở lên”, hãy chuyển điều kiện lương vào ON:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.salary >= 5000
WHERE d.status = 'OPEN';
~~~

## 13. Cú pháp Oracle cũ với dấu (+)

Oracle từng hỗ trợ cú pháp outer join cũ dùng toán tử `(+)` trong `WHERE`:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d, employees e
WHERE d.department_id = e.department_id(+);
~~~

Dấu `(+)` đặt ở phía được mở rộng NULL, ở ví dụ là bảng `EMPLOYEES`. Để thêm điều kiện trạng thái mà vẫn giữ phòng ban, cú pháp legacy cần đánh dấu phía đó phù hợp:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d, employees e
WHERE d.department_id = e.department_id(+)
  AND e.status(+) = 'ACTIVE';
~~~

Nếu bỏ `(+)` khỏi điều kiện `e.status = 'ACTIVE'`, điều kiện đó có thể loại hàng NULL mở rộng và làm kết quả giống inner join trong tình huống này.

Tuy nhiên, cú pháp `(+)` có nhiều hạn chế so với ANSI JOIN, đặc biệt khi kết hợp nhiều bảng, điều kiện OR, subquery và các biểu thức phức tạp. Không trộn cú pháp `(+)` với `JOIN ... ON` trong cùng query block. Với code mới, ưu tiên ANSI:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE';
~~~

ANSI JOIN làm rõ bảng nào được bảo toàn và predicate nào thuộc quan hệ kết nối, nên dễ đọc và ít nhầm hơn.

## 14. Cách đọc một truy vấn OUTER JOIN trước khi chạy

Khi review SQL, dùng chuỗi câu hỏi sau:

1. **Bảng nào phải được giữ đầy đủ?** Nếu là LEFT JOIN, đó là bảng bên trái của phép join cụ thể.
2. **Điều kiện nào định nghĩa đối tác hợp lệ?** Đặt điều kiện khóa và các tiêu chí đối tác trong ON.
3. **Điều kiện nào loại bản ghi nghiệp vụ khỏi kết quả cuối?** Đặt trong WHERE nếu thực sự muốn loại cả dòng được bảo toàn khi không đạt.
4. **Cột nào sẽ NULL khi không có đối tác?** Xác định các predicate WHERE trên cột đó có trả UNKNOWN/FALSE hay TRUE.
5. **Có nhiều hàng khớp không?** Kiểm tra cardinality để hiểu số dòng kết quả.
6. **Có cần anti-join không?** Dùng NOT EXISTS hoặc kiểm tra khóa chính phía phải IS NULL.
7. **Có nhiều OUTER JOIN liên tiếp không?** Phân tích từng tầng bảo toàn và NULL extension.

### 14.1. Bảng quyết định nhanh cho LEFT JOIN

| Ý định | Vị trí điều kiện phù hợp |
| --- | --- |
| Giữ mọi phòng ban, chỉ ghép nhân viên ACTIVE | `e.status = 'ACTIVE'` trong ON |
| Chỉ xem phòng ban OPEN | `d.status = 'OPEN'` trong WHERE |
| Giữ mọi phòng ban OPEN, chỉ ghép nhân viên lương cao | `e.salary >= ...` trong ON và `d.status = 'OPEN'` trong WHERE |
| Chỉ lấy phòng ban có nhân viên ACTIVE | INNER JOIN với điều kiện ACTIVE hoặc LEFT JOIN + WHERE null-rejecting có chủ đích |
| Tìm phòng ban không có nhân viên nào | LEFT JOIN theo khóa + WHERE khóa nhân viên IS NULL, hoặc NOT EXISTS |
| Tìm phòng ban không có nhân viên ACTIVE | LEFT JOIN với status trong ON + WHERE khóa nhân viên IS NULL, hoặc NOT EXISTS có status |
| Chỉ lấy phòng ban có nhân viên và nhân viên có email | WHERE e.email IS NOT NULL hoặc INNER JOIN tùy ý định |

Điều quan trọng là câu mô tả nghiệp vụ phải nói rõ “không có bất kỳ nhân viên nào” hay “không có nhân viên thỏa điều kiện”. Đó là hai câu hỏi dữ liệu khác nhau.

## 15. Bài thực hành: quan sát ON và WHERE bằng cùng một dữ liệu

Các bước sau tạo hai bảng nhỏ. Thực hiện trên schema lab riêng. Nếu các tên bảng đã tồn tại, chọn tên khác và thay thống nhất trong toàn bộ bài.

### Bước 1 — Tạo bảng phòng ban

~~~sql
CREATE TABLE join_department_lab (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(40 CHAR) NOT NULL,
    status VARCHAR2(10 CHAR) NOT NULL
);

INSERT INTO join_department_lab VALUES (10, 'Sales', 'OPEN');
INSERT INTO join_department_lab VALUES (20, 'IT', 'OPEN');
INSERT INTO join_department_lab VALUES (30, 'HR', 'OPEN');
INSERT INTO join_department_lab VALUES (40, 'Legal', 'CLOSED');

COMMIT;
~~~

### Bước 2 — Tạo bảng nhân viên

~~~sql
CREATE TABLE join_employee_lab (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    employee_name VARCHAR2(40 CHAR) NOT NULL,
    status VARCHAR2(10 CHAR),
    salary NUMBER(10,2),
    CONSTRAINT fk_join_emp_dept_lab
        FOREIGN KEY (department_id)
        REFERENCES join_department_lab(department_id)
);

INSERT INTO join_employee_lab
VALUES (101, 10, 'An', 'ACTIVE', 7000);

INSERT INTO join_employee_lab
VALUES (102, 10, 'Binh', 'INACTIVE', 5000);

INSERT INTO join_employee_lab
VALUES (201, 20, 'Chi', 'INACTIVE', 6000);

COMMIT;
~~~

Dữ liệu được thiết kế có chủ đích:

- Sales có một nhân viên ACTIVE và một INACTIVE.
- IT chỉ có nhân viên INACTIVE.
- HR không có nhân viên.
- Legal không có nhân viên và đang CLOSED.

### Bước 3 — LEFT JOIN không lọc trạng thái

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Kết quả có bốn phòng ban và tổng cộng năm dòng:

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| Sales | Binh | INACTIVE |
| IT | Chi | INACTIVE |
| HR | NULL | NULL |
| Legal | NULL | NULL |

### Bước 4 — Đặt ACTIVE trong ON

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

Kết quả có bốn dòng:

| Department | Employee | Status |
| --- | --- | --- |
| Sales | An | ACTIVE |
| IT | NULL | NULL |
| HR | NULL | NULL |
| Legal | NULL | NULL |

IT vẫn còn dù có nhân viên INACTIVE, vì IT không có nhân viên **đạt điều kiện ON**. HR và Legal cũng không có nhân viên phù hợp.

### Bước 5 — Chuyển ACTIVE sang WHERE

~~~sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
ORDER BY d.department_id, e.employee_id;
~~~

Kết quả chỉ còn Sales/An. IT bị loại vì đã ghép với Chi trước khi WHERE lọc; HR và Legal bị loại vì status NULL.

### Bước 6 — Thử OR IS NULL và giải thích IT bị mất

~~~sql
SELECT d.department_id, e.employee_id, e.status
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE'
   OR e.employee_id IS NULL
ORDER BY d.department_id;
~~~

Kết quả gồm Sales, HR và Legal; IT vẫn không xuất hiện. Giải thích bằng bốn bước ON → match → NULL extension (nếu không có match) → WHERE.

### Bước 7 — Tìm phòng ban không có nhân viên ACTIVE

~~~sql
SELECT d.department_id, d.department_name
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND e.status = 'ACTIVE'
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
~~~

Kết quả gồm IT, HR và Legal. Đây là “không có nhân viên ACTIVE”, nên IT được trả về dù có nhân viên INACTIVE.

### Bước 8 — Viết lại bằng NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM join_department_lab d
WHERE NOT EXISTS (
    SELECT 1
    FROM join_employee_lab e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
)
ORDER BY d.department_id;
~~~

Kết quả phải giống Bước 7. So sánh hai cách diễn đạt và xác định cột khóa được kiểm tra ở cách LEFT JOIN.

### Bước 9 — Điều kiện phòng ban trong ON và WHERE

~~~sql
-- Moi phong ban duoc giu; chi phong ban OPEN co the ghep nhan vien.
SELECT d.department_id, d.status, e.employee_id
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
   AND d.status = 'OPEN'
ORDER BY d.department_id;

-- Chi phong ban OPEN duoc giu.
SELECT d.department_id, d.status, e.employee_id
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
WHERE d.status = 'OPEN'
ORDER BY d.department_id;
~~~

So sánh Legal: truy vấn đầu vẫn giữ Legal với employee NULL; truy vấn thứ hai loại Legal.

### Bước 10 — Đếm nhân viên đúng cách sau LEFT JOIN

~~~sql
SELECT
    d.department_id,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count
FROM join_department_lab d
LEFT JOIN join_employee_lab e
    ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
~~~

Với HR và Legal, `COUNT(*)` là 1 vì mỗi phòng ban vẫn tạo một dòng NULL mở rộng; `COUNT(e.employee_id)` là 0 vì khóa nhân viên NULL. Nếu muốn đếm nhân viên, dùng `COUNT(e.employee_id)` hoặc một cột phía phải chắc chắn NOT NULL.

### Bước 11 — Dọn bảng lab khi không cần

~~~sql
-- Chi chay neu chac chan day la hai bang lab do ban tao.
DROP TABLE join_employee_lab PURGE;
DROP TABLE join_department_lab PURGE;
~~~

Bảng employee có foreign key đến department nên drop bảng con trước. `PURGE` bỏ qua recycle bin; không dùng nếu muốn giữ dữ liệu thực hành.

## 16. Các lỗi và hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa theo ý định |
| --- | --- | --- |
| LEFT JOIN nhưng phòng ban không có nhân viên biến mất | WHERE lọc cột phía phải, loại NULL mở rộng | Chuyển điều kiện đối tác sang ON nếu muốn giữ phòng ban |
| Phòng ban chỉ có nhân viên INACTIVE vẫn biến mất sau `OR e.id IS NULL` | ON đã ghép nhân viên INACTIVE, nên không có hàng NULL mở rộng | Đặt ACTIVE trong ON hoặc dùng NOT EXISTS |
| Dùng `WHERE e.note IS NULL` để tìm không có nhân viên | NOTE có thể NULL ở nhân viên thật | Kiểm tra PK phía phải hoặc dùng NOT EXISTS |
| LEFT JOIN trả nhiều dòng hơn số phòng ban | Một phòng ban có nhiều nhân viên khớp | Tổng hợp phía phải trước nếu muốn một dòng/phòng ban |
| Đổi điều kiện của bảng trái từ WHERE sang ON làm bảng có thêm hàng | Bảng trái là phía được bảo toàn | Giữ predicate lọc bảng trái ở WHERE nếu muốn loại dòng đó |
| FULL OUTER JOIN không còn giữ hàng chỉ có bên trái | WHERE trên cột phía phải loại NULL mở rộng | Đánh giá predicate trên từng loại hàng; đặt điều kiện đối tác vào ON |
| Anti-join bằng NOT IN trả rỗng bất ngờ | Subquery chứa NULL | Dùng NOT EXISTS hoặc lọc NULL trong subquery |
| JOIN đúng khóa nhưng số liệu tổng bị nhân đôi | Quan hệ 1-n hoặc join nhiều bảng detail làm nhân dòng | Xác định grain/cardinality và tổng hợp đúng tầng |
| SQL cũ dùng dấu (+) khó đọc | Cú pháp outer join legacy có hạn chế | Chuyển sang ANSI JOIN trong kế hoạch migration |

### 16.1. ORA-01417 và các vấn đề cú pháp legacy

Khi dùng cú pháp `(+)`, một số cách nối nhiều bảng và nhiều điều kiện có hạn chế theo phiên bản Oracle; lỗi như `ORA-01417` có thể xuất hiện trong mẫu legacy không hợp lệ. Không cố thêm dấu `(+)` tùy tiện vào mọi cột. Hãy viết lại bằng ANSI JOIN, xác định rõ từng quan hệ và kiểm thử kết quả.

### 16.2. Không phải cứ điều kiện trong WHERE là sai

Nếu yêu cầu là “chỉ lấy phòng ban có nhân viên ACTIVE”, điều kiện:

~~~sql
WHERE e.status = 'ACTIVE'
~~~

là đúng, vì ta chủ động muốn loại phòng ban không có nhân viên ACTIVE. Có thể viết INNER JOIN trực tiếp để diễn đạt ý định:

~~~sql
SELECT d.department_id, e.employee_id
FROM departments d
JOIN employees e
    ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

Điểm cần tránh là dùng LEFT JOIN với kỳ vọng giữ đủ phía trái, rồi vô tình đặt điều kiện WHERE loại chính các hàng cần bảo toàn. Vị trí đúng phụ thuộc **ý nghĩa nghiệp vụ**, không phải một quy tắc hình thức áp dụng cho mọi câu SQL.

## 17. Câu hỏi tự kiểm tra

1. `ON` và `WHERE` khác nhau thế nào khi truy vấn có LEFT OUTER JOIN?
2. Với LEFT JOIN, bảng nào được bảo toàn khi không có hàng khớp?
3. Nếu điều kiện `e.status = 'ACTIVE'` nằm trong ON, phòng ban chỉ có nhân viên INACTIVE có xuất hiện không?
4. Nếu cùng điều kiện nằm trong WHERE, vì sao phòng ban không có nhân viên bị loại?
5. `WHERE e.status = 'ACTIVE' OR e.employee_id IS NULL` có giữ được phòng ban chỉ có nhân viên INACTIVE không? Vì sao?
6. Vì sao nên dùng khóa chính phía phải để kiểm tra `IS NULL` trong anti-join?
7. Phân biệt “không có nhân viên nào” và “không có nhân viên ACTIVE”.
8. Viết lại anti-join tìm khách hàng không có đơn PAID bằng NOT EXISTS.
9. Khi điều kiện của bảng trái nằm trong ON của LEFT JOIN, điều gì xảy ra với dòng trái không thỏa điều kiện?
10. Trong FULL OUTER JOIN, điều kiện của bảng phải đặt trong WHERE có thể làm mất loại hàng nào?
11. `COUNT(*)` và `COUNT(e.employee_id)` khác nhau thế nào với phòng ban không có nhân viên?
12. Điều kiện ngày tháng của đơn hàng nên nằm ở ON hay WHERE nếu vẫn muốn giữ mọi khách hàng?
13. Vì sao một phòng ban có thể xuất hiện nhiều lần trong kết quả LEFT JOIN?
14. CTE lọc nhân viên ACTIVE trước khi LEFT JOIN có thể giúp câu SQL dễ hiểu như thế nào?
15. Vì sao không nên cho rằng optimizer đẩy predicate xuống đâu thì kết quả cũng như nhau?

**Gợi ý trả lời:**

1. ON xác định cặp khớp; WHERE lọc result set sau JOIN/NULL extension.
2. Bảng bên trái.
3. Có; phòng ban được giữ với cột nhân viên NULL.
4. Cột phải của hàng không khớp là NULL; phép so sánh trả UNKNOWN và WHERE không giữ.
5. Không. Nhân viên INACTIVE đã khớp ở ON nên không tạo hàng NULL mở rộng; WHERE loại hàng đó.
6. Khóa chính không NULL ở hàng thật, nên NULL biểu thị không có đối tác.
7. Điều kiện thứ hai chỉ loại nhân viên không ACTIVE khỏi tập đối tác; phòng ban có nhân viên INACTIVE vẫn không có nhân viên ACTIVE.
8. Dùng NOT EXISTS với điều kiện customer_id và status='PAID' trong subquery.
9. Dòng trái vẫn được giữ nhưng các cột phải NULL vì không có cặp khớp.
10. Hàng chỉ có bên trái bị loại nếu predicate trên phía phải không chấp nhận NULL; tùy điều kiện, hàng chỉ bên phải cũng có thể bị lọc.
11. COUNT(*) đếm dòng NULL mở rộng (1); COUNT(e.employee_id) đếm 0.
12. Đặt điều kiện đơn hàng trong ON nếu mọi khách hàng phải được giữ.
13. Vì nhiều nhân viên có thể cùng department_id và mỗi cặp tạo một dòng.
14. CTE đặt tên cho tập đối tác đã lọc, tách điều kiện nghiệp vụ khỏi phép nối.
15. Optimizer chỉ được biến đổi khi bảo toàn ngữ nghĩa; người viết phải hiểu predicate và NULL semantics.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp join, outer join, điều kiện ON và WHERE.
- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): quy tắc inner, outer, full outer join và cú pháp ANSI/legacy.
- [Oracle Database SQL Language Reference — Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Conditions.html): điều kiện SQL, NULL và logic ba giá trị.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): `EXISTS` và `NOT EXISTS` trong truy vấn con.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): cách optimizer biến đổi truy vấn, predicate và execution plan.
