# EXISTS, NOT EXISTS và kiểm tra quan hệ tồn tại trong Oracle Database

Khi truy vấn dữ liệu quan hệ, có nhiều câu hỏi không cần lấy thông tin chi tiết từ bảng con. Ta chỉ cần biết **có ít nhất một dòng liên quan hay không**, hoặc **không có dòng nào thỏa điều kiện**. Ví dụ:

- Liệt kê khách hàng đã từng đặt hàng.
- Tìm sản phẩm chưa từng được bán.
- Tìm phòng ban có ít nhất một nhân viên đang hoạt động.
- Tìm hóa đơn chưa có thanh toán.
- Chỉ lấy tài khoản chưa có giao dịch bị đánh dấu rủi ro.

Oracle SQL cung cấp hai điều kiện truy vấn phù hợp:

- **EXISTS** đúng khi truy vấn con trả về ít nhất một dòng.
- **NOT EXISTS** đúng khi truy vấn con không trả về dòng nào.

Hai điều kiện này thường được viết với **correlated subquery** (truy vấn con tương quan), tức truy vấn con tham chiếu cột của dòng hiện tại ở truy vấn ngoài. Về mặt tư duy quan hệ, EXISTS thường tương ứng với phép **semi-join**, còn NOT EXISTS tương ứng với **anti-join**. Cách viết này biểu đạt trực tiếp ý định kiểm tra quan hệ tồn tại, tránh nhân bản dòng của bảng cha khi có nhiều dòng con.

Bài học giải thích cú pháp, cách liên kết truy vấn trong Oracle, sự khác nhau giữa EXISTS và JOIN, các bẫy NULL của NOT IN, cách dùng trong DML, hiệu năng, tính đúng đắn khi có giao dịch đồng thời và bài lab thực hành.

## 1. EXISTS kiểm tra điều gì?

EXISTS là một điều kiện logic. Nó chỉ quan tâm truy vấn con có trả về **ít nhất một dòng** hay không. Giá trị trong SELECT list của truy vấn con không phải điều kiện quyết định.

Cú pháp:

~~~sql
WHERE EXISTS (
    subquery
)
~~~

Ví dụ:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT NULL
    FROM dual
);
~~~

Truy vấn con đọc một dòng từ DUAL, vì vậy EXISTS đúng. Dù SELECT list là NULL, dòng đó vẫn tồn tại.

Ngược lại:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT 1
    FROM dual
    WHERE 1 = 0
);
~~~

Truy vấn con không trả dòng nào nên EXISTS sai; kết quả ngoài không có dòng.

### 1.1 SELECT 1, SELECT NULL hay SELECT *?

Các dạng sau đều có thể dùng trong EXISTS:

~~~sql
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)
~~~

~~~sql
WHERE EXISTS (SELECT NULL FROM orders o WHERE o.customer_id = c.customer_id)
~~~

~~~sql
WHERE EXISTS (SELECT * FROM orders o WHERE o.customer_id = c.customer_id)
~~~

Về ý nghĩa kiểm tra tồn tại, chúng tương đương: Oracle chỉ cần biết truy vấn con có dòng hay không. Dùng SELECT 1 là quy ước dễ đọc vì nó thể hiện rõ rằng người viết không cần giá trị của cột con.

SELECT 1 không phải một mẹo bắt buộc để tăng tốc. Optimizer của Oracle có thể biến đổi truy vấn và không cần đọc toàn bộ các cột được liệt kê trong SELECT list của EXISTS nếu chúng không ảnh hưởng semantics.

### 1.2 EXISTS không đếm số dòng

Nếu truy vấn con có 1 dòng hay 10.000 dòng thỏa điều kiện, EXISTS vẫn chỉ trả một giá trị logic đúng. Nó không trả về số dòng con.

Nếu cần số lượng, dùng COUNT:

~~~sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
~~~

Nếu chỉ cần biết có hay không, EXISTS thường diễn đạt ý định rõ hơn COUNT(*) > 0.

### 1.3 Cảnh báo: aggregate không GROUP BY có thể luôn sinh một dòng

Truy vấn:

~~~sql
SELECT 1
FROM dual
WHERE EXISTS (
    SELECT COUNT(*)
    FROM orders o
    WHERE o.customer_id = -999
);
~~~

EXISTS ở đây vẫn đúng, kể cả không có đơn hàng cho customer_id -999. Lý do: truy vấn aggregate COUNT(*) không có GROUP BY trả về một dòng chứa COUNT bằng 0 khi không có đầu vào. Dòng aggregate đó vẫn tồn tại.

Nếu muốn kiểm tra sự tồn tại, viết:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

Hoặc nếu đã có lý do dùng aggregate, kiểm tra điều kiện COUNT > 0 bên trong một lớp truy vấn thích hợp. Nhưng với bài toán tồn tại đơn thuần, không cần COUNT.

## 2. Correlated subquery: truy vấn con tương quan

Một subquery là **correlated** khi nó tham chiếu cột của query block bên ngoài. Ví dụ:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Đọc theo ý nghĩa:

1. Xét một khách hàng c ở truy vấn ngoài.
2. Tìm trong ORDERS ít nhất một dòng o có CUSTOMER_ID bằng mã khách hàng hiện tại.
3. Nếu tìm thấy, giữ khách hàng đó.
4. Nếu không tìm thấy, loại khách hàng đó.

Kết quả là danh sách khách hàng **đã từng có ít nhất một đơn hàng**.

### 2.1 Vì sao cần alias?

Alias c và o giúp phân biệt nguồn cột:

- c.customer_id là mã khách hàng ở truy vấn ngoài.
- o.customer_id là mã khách hàng lưu trên đơn hàng.

Nếu cả hai bảng đều có CUSTOMER_ID mà không chỉ rõ nguồn, câu SQL có thể mơ hồ hoặc dễ đọc sai. Dùng alias tường minh là thói quen tốt.

### 2.2 Correlated không có nghĩa Oracle bắt buộc chạy lặp tuần tự

Về logic, có thể hình dung subquery được kiểm tra cho từng dòng khách hàng. Nhưng không nên suy ra Oracle luôn thực thi bằng cách chạy một truy vấn con độc lập cho từng hàng.

Optimizer có thể **unnest** subquery và chuyển EXISTS thành semi-join hoặc một chiến lược truy cập khác. Kế hoạch thực thi phụ thuộc thống kê, index, số dòng, điều kiện lọc và phiên bản Oracle.

Vì vậy, correlated subquery là cách diễn đạt logic; không phải lời cam kết về cách engine thực hiện vật lý.

### 2.3 EXISTS với nhiều điều kiện liên quan

Ví dụ chỉ lấy khách hàng có đơn hàng đã thanh toán và tổng đơn lớn hơn một ngưỡng:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.total_amount >= 1000000
);
~~~

Truy vấn con chỉ cần một dòng thỏa **tất cả** điều kiện. Không cần lấy toàn bộ đơn hàng ra rồi lọc ở ứng dụng.

### 2.4 EXISTS với điều kiện ngày giờ

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.created_at >= DATE '2026-11-01'
      AND o.created_at <  DATE '2026-12-01'
);
~~~

Ví dụ này tìm khách hàng có ít nhất một đơn trong tháng 11/2026. Khoảng nửa mở tránh bỏ sót thời điểm cuối ngày và không cần đặt mốc 23:59:59.

## 3. NOT EXISTS: kiểm tra không có dòng liên quan

NOT EXISTS đúng khi truy vấn con trả về **không dòng nào**:

~~~sql
WHERE NOT EXISTS (
    subquery
)
~~~

Ví dụ tìm khách hàng chưa từng đặt hàng:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Với mỗi khách hàng:

- Nếu có ít nhất một đơn hàng phù hợp, EXISTS đúng và NOT EXISTS sai.
- Nếu không có đơn hàng phù hợp, EXISTS sai và NOT EXISTS đúng.

### 3.1 NOT EXISTS không có nghĩa cột con bằng NULL

NOT EXISTS kiểm tra **không có dòng nào thỏa điều kiện**, không kiểm tra một cột cụ thể có NULL hay không.

So sánh:

~~~sql
-- Khách hàng chưa có đơn hàng:
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
-- Khách hàng có đơn hàng mà ngày giao hàng chưa được ghi:
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.shipped_at IS NULL
)
~~~

Truy vấn đầu hỏi quan hệ khách hàng - đơn hàng có tồn tại không. Truy vấn thứ hai hỏi có tồn tại đơn hàng với trạng thái thiếu ngày giao hay không. Hai yêu cầu khác nhau.

### 3.2 Điều kiện trong NOT EXISTS quyết định quan hệ nào bị loại

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

Kết quả là sản phẩm chưa từng xuất hiện trong bất kỳ dòng chi tiết đơn hàng nào.

Nếu thêm điều kiện:

~~~sql
AND o.status = 'PAID'
~~~

trong một truy vấn có JOIN tới ORDERS, ý nghĩa sẽ đổi thành sản phẩm không xuất hiện trong đơn đã thanh toán. Hãy đặt điều kiện vào đúng quan hệ cần kiểm tra; thiếu hoặc đặt sai predicate có thể làm báo cáo trả kết quả quá rộng hoặc quá hẹp.

### 3.3 NOT EXISTS với trạng thái nghiệp vụ

Tìm đơn hàng chưa có thanh toán:

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments p
    WHERE p.order_id = o.order_id
);
~~~

Nếu nghiệp vụ chỉ coi thanh toán đã xác nhận là thanh toán hoàn tất:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
~~~

Khi đó đơn hàng có bản ghi thanh toán PENDING hoặc FAILED vẫn được trả về. Tên điều kiện phải phản ánh chính xác trạng thái mà nghiệp vụ xem là đã hoàn thành.

## 4. EXISTS như semi-join và NOT EXISTS như anti-join

Đây là cách nhìn quan hệ hữu ích khi so sánh với JOIN.

### 4.1 Semi-join: chỉ giữ dòng cha có ít nhất một dòng con

EXISTS thường biểu đạt **semi-join**: trả về dòng từ phía bảng cha nếu có ít nhất một dòng phù hợp ở phía bảng con.

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Một khách hàng có 1 đơn hay 100 đơn vẫn xuất hiện một lần trong kết quả, nếu không có nguồn nhân bản khác ở truy vấn ngoài.

### 4.2 JOIN có thể nhân bản dòng cha

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

Nếu khách hàng có ba đơn, dòng khách hàng có thể xuất hiện ba lần. Đó là hành vi đúng của JOIN vì truy vấn đang trả về các cặp khách hàng - đơn hàng.

Nếu mục tiêu chỉ là danh sách khách hàng đã mua hàng, EXISTS thường sát ý định hơn. Dùng JOIN rồi DISTINCT có thể cho cùng danh sách trong một số trường hợp, nhưng phải tạo các dòng kết hợp trước khi loại trùng theo logic truy vấn.

### 4.3 NOT EXISTS như anti-join

NOT EXISTS thường biểu đạt **anti-join**: trả về dòng phía cha mà không có dòng con phù hợp.

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

Đây là sản phẩm không có quan hệ chi tiết đơn hàng. Cách viết trực tiếp hơn so với LEFT JOIN rồi kiểm tra một cột con IS NULL, đặc biệt khi cột được kiểm tra có thể nullable.

### 4.4 LEFT JOIN ... IS NULL cũng có thể biểu đạt anti-join

Một cách viết khác:

~~~sql
SELECT p.product_id,
       p.product_name
FROM products p
LEFT JOIN order_items oi
  ON oi.product_id = p.product_id
WHERE oi.product_id IS NULL;
~~~

Trong ví dụ này, điều kiện kiểm tra cột con là khóa dùng trong điều kiện JOIN và giả định khóa đó không NULL trong một dòng khớp hợp lệ. Nếu chọn một cột con nullable không phù hợp, có thể phân loại nhầm dòng khớp thành dòng không khớp.

NOT EXISTS diễn đạt ý định “không có dòng con thỏa điều kiện” trực tiếp, nên thường dễ đọc và ít phụ thuộc vào việc chọn đúng cột sentinel ở phía bảng con.

### 4.5 Khi nào cần JOIN thay vì EXISTS?

| Mục tiêu | Cách thường phù hợp |
|---|---|
| Chỉ cần biết có ít nhất một dòng con | EXISTS |
| Chỉ cần biết không có dòng con phù hợp | NOT EXISTS |
| Cần hiển thị cột của cả cha và con | JOIN |
| Cần tổng số dòng con | JOIN + GROUP BY hoặc scalar COUNT |
| Cần một giá trị con cụ thể theo quy tắc ưu tiên | JOIN với logic chọn dòng, analytic function hoặc scalar subquery |
| Cần giữ cha dù không có con, đồng thời hiển thị cột con | LEFT JOIN |

Đừng chọn EXISTS chỉ vì nó thường nhanh. Chọn theo **shape của kết quả và ý nghĩa nghiệp vụ** trước, sau đó mới đo hiệu năng.

## 5. NULL và NOT IN: bẫy rất quan trọng

Một trong những lý do phổ biến để chọn NOT EXISTS là tránh bẫy NULL của NOT IN.

### 5.1 NOT IN có thể trả về không dòng nào khi subquery chứa NULL

Giả sử:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

Nếu subquery trả về danh sách có ít nhất một NULL, biểu thức NOT IN của một giá trị không khớp có thể trở thành UNKNOWN thay vì TRUE. WHERE chỉ giữ dòng có điều kiện TRUE, nên các dòng dự kiến là “không có đơn” có thể biến mất.

Đây là hệ quả của logic ba giá trị SQL:

- TRUE: điều kiện đúng.
- FALSE: điều kiện sai.
- UNKNOWN: không thể kết luận đúng/sai, thường xuất hiện khi so sánh với NULL.

Ví dụ đơn giản:

~~~sql
SELECT 1 AS value
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

Truy vấn không trả dòng, vì phép so sánh với NULL làm kết quả NOT IN không thể là TRUE.

### 5.2 NOT EXISTS không bị bẫy NULL trong subquery theo cách đó

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Nếu một dòng ORDERS có CUSTOMER_ID NULL, nó không thỏa điều kiện bằng với một mã khách hàng cụ thể. Dòng NULL đó không tự làm mọi khách hàng bị loại. NOT EXISTS chỉ hỏi có dòng nào thỏa quan hệ bằng hiện tại hay không.

Đây là khác biệt thực tế quan trọng giữa NOT EXISTS và NOT IN.

### 5.3 NOT IN vẫn có thể dùng nếu loại NULL rõ ràng

Nếu chắc chắn subquery không có NULL, hoặc đã lọc:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

có thể tránh bẫy NULL trong danh sách con. Tuy nhiên, nếu yêu cầu là kiểm tra quan hệ tồn tại, NOT EXISTS thường biểu đạt ý định trực tiếp hơn.

### 5.4 NULL ở khóa phía ngoài

Xét:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

Nếu c.customer_id là NULL, phép so sánh o.customer_id = NULL không TRUE cho bất kỳ dòng nào. Vì vậy subquery không tìm thấy dòng phù hợp và NOT EXISTS có thể đúng. Kết quả có thể bao gồm dòng cha có khóa NULL.

Nếu nghiệp vụ yêu cầu chỉ xét khách hàng có mã hợp lệ, thêm:

~~~sql
AND c.customer_id IS NOT NULL
~~~

Đừng nhầm NOT EXISTS với phép kiểm tra NOT NULL. Muốn loại khóa NULL phải nói rõ bằng IS NOT NULL.

### 5.5 Khi NULL được xem là bằng NULL theo nghiệp vụ

Trong SQL, phép bằng thông thường không coi NULL bằng NULL. Nếu nghiệp vụ muốn hai giá trị NULL được xem là cùng nhóm khi so sánh quan hệ, cần viết điều kiện null-safe rõ ràng:

~~~sql
WHERE (
       o.external_ref = c.external_ref
       OR (o.external_ref IS NULL AND c.external_ref IS NULL)
)
~~~

Ví dụ đầy đủ:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM legacy_orders o
    WHERE o.customer_id = c.customer_id
      AND (
           o.external_ref = c.external_ref
           OR (o.external_ref IS NULL AND c.external_ref IS NULL)
      )
);
~~~

Chỉ dùng cách so sánh NULL-safe khi NULL thật sự đại diện cho cùng một giá trị logic theo quy tắc nghiệp vụ. Nếu NULL có nghĩa “chưa biết”, coi hai NULL là bằng nhau có thể ghép sai bản ghi.

## 6. EXISTS và NOT EXISTS với nhiều quan hệ

### 6.1 Khách hàng có đơn và có thanh toán

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

Đọc từ ngoài vào trong:

1. Tìm khách hàng.
2. Kiểm tra khách hàng có đơn hàng.
3. Với một đơn hàng liên quan, kiểm tra có thanh toán đã xác nhận.
4. Chỉ giữ khách hàng nếu tồn tại một đơn thỏa cả hai quan hệ.

Đây là EXISTS lồng nhau. Nó không nhân bản khách hàng dù một khách có nhiều đơn và một đơn có nhiều dòng thanh toán.

### 6.2 Khách hàng có đơn nhưng chưa có thanh toán xác nhận

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

Truy vấn trả khách hàng có ít nhất một đơn chưa có thanh toán CONFIRMED. Một khách hàng có thể vẫn có những đơn khác đã thanh toán; điều kiện chỉ cần tồn tại một đơn chưa thanh toán xác nhận.

Nếu yêu cầu là khách hàng **có đơn và tất cả đơn đều đã thanh toán**, logic phải khác. Có thể diễn đạt bằng NOT EXISTS lồng để tìm đơn chưa được xác nhận thanh toán rồi phủ định:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM payments p
          WHERE p.order_id = o.order_id
            AND p.payment_status = 'CONFIRMED'
      )
);
~~~

Điều kiện EXISTS đầu tiên đảm bảo khách hàng có ít nhất một đơn. NOT EXISTS thứ hai đảm bảo không tồn tại đơn nào thiếu thanh toán đã xác nhận. Nếu bỏ EXISTS đầu tiên, khách hàng không có đơn nào cũng thỏa điều kiện “không tồn tại đơn chưa thanh toán” theo logic chân không (vacuous truth).

### 6.3 Quan hệ nhiều-nhiều qua bảng nối

Giả sử STUDENTS và COURSES liên kết qua ENROLLMENTS. Tìm sinh viên đã đăng ký ít nhất một khóa:

~~~sql
SELECT s.student_id,
       s.student_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM enrollments e
    WHERE e.student_id = s.student_id
);
~~~

Tìm khóa học chưa có sinh viên đăng ký:

~~~sql
SELECT c.course_id,
       c.course_name
FROM courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM enrollments e
    WHERE e.course_id = c.course_id
);
~~~

Bảng ENROLLMENTS là quan hệ trung gian. EXISTS kiểm tra quan hệ thông qua bảng nối mà không cần trả các dòng đăng ký.

## 7. EXISTS trong SELECT list để tạo cờ

Có thể dùng EXISTS bên trong CASE để trả về nhãn trạng thái:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       CASE
         WHEN EXISTS (
             SELECT 1
             FROM orders o
             WHERE o.customer_id = c.customer_id
         )
         THEN 'HAS_ORDER'
         ELSE 'NO_ORDER'
       END AS order_status
FROM customers c;
~~~

Oracle SQL không dùng một kiểu BOOLEAN thông thường làm kiểu cột kết quả SQL theo cách các ngôn ngữ lập trình làm. CASE chuyển điều kiện EXISTS thành giá trị ký tự để trả về.

Một cách khác là dùng biểu thức số:

~~~sql
CASE WHEN EXISTS (...) THEN 1 ELSE 0 END AS has_order
~~~

Điều này hữu ích cho API hoặc báo cáo cần cờ 0/1. Tuy nhiên nếu chỉ cần lọc khách hàng có đơn, đặt EXISTS trong WHERE sẽ rõ hơn.

## 8. Dùng EXISTS trong UPDATE và DELETE

EXISTS không chỉ dùng trong SELECT. Nó có thể kiểm tra quan hệ trước khi thực hiện DML.

### 8.1 UPDATE dựa trên dữ liệu liên quan

Ví dụ đánh dấu khách hàng là ACTIVE nếu có đơn hàng đã thanh toán:

~~~sql
UPDATE customers c
SET customer_status = 'ACTIVE'
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Điều kiện EXISTS quyết định dòng CUSTOMER nào được cập nhật. Đây là DML thật, thay đổi dữ liệu; cần kiểm tra phạm vi, quyền, transaction và điều kiện WHERE trước khi chạy.

### 8.2 DELETE dựa trên quan hệ không tồn tại

Ví dụ xóa bản ghi tạm không còn liên quan đến khách hàng nào:

~~~sql
DELETE FROM staging_customer s
WHERE NOT EXISTS (
    SELECT 1
    FROM customers c
    WHERE c.customer_id = s.customer_id
);
~~~

Không chạy ví dụ này trên dữ liệu thật nếu chưa xác nhận chính sách lưu trữ. Trong thực tế có thể cần lưu audit, thời hạn retention hoặc xử lý khóa ngoại trước khi xóa.

### 8.3 INSERT ... SELECT ... WHERE NOT EXISTS

Một mẫu phổ biến để chỉ chèn nếu chưa có bản ghi tương ứng:

~~~sql
INSERT INTO customer_flags (customer_id, flag_code)
SELECT :p_customer_id, :p_flag_code
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_flags f
    WHERE f.customer_id = :p_customer_id
      AND f.flag_code = :p_flag_code
);
~~~

Mẫu này giúp tránh chèn trùng trong một số luồng tuần tự. Nhưng nó **không bảo đảm chống trùng khi có nhiều transaction đồng thời**: hai session có thể cùng kiểm tra chưa tồn tại rồi cùng insert trước khi một bên commit.

Nếu tính duy nhất là yêu cầu dữ liệu, hãy tạo UNIQUE constraint hoặc unique index phù hợp và xử lý lỗi duplicate key ở ứng dụng. NOT EXISTS không thay thế ràng buộc toàn vẹn.

## 9. Tính đúng đắn khi có giao dịch đồng thời

Một lỗi thiết kế thường gặp là dùng:

~~~sql
IF NOT EXISTS THEN INSERT
~~~

như thể hai bước kiểm tra và ghi là một thao tác nguyên tử.

Kịch bản:

1. Session A kiểm tra customer_id=10 và flag_code='VIP', chưa thấy dòng.
2. Session B cũng kiểm tra cùng cặp giá trị, chưa thấy dòng.
3. Session A INSERT.
4. Session B INSERT.
5. Nếu không có ràng buộc duy nhất, hai dòng trùng có thể được lưu.

NOT EXISTS chỉ trả lời theo snapshot/khả năng nhìn thấy dữ liệu của statement tại thời điểm thực thi. Nó không khóa một “khoảng trống” logic để ngăn mọi transaction khác insert cùng giá trị.

### 9.1 Dùng UNIQUE constraint cho tính duy nhất

~~~sql
ALTER TABLE customer_flags
ADD CONSTRAINT uq_customer_flag
UNIQUE (customer_id, flag_code);
~~~

Sau đó ứng dụng có thể thử INSERT và xử lý lỗi vi phạm unique constraint theo quy tắc retry/đọc lại phù hợp. Nếu cần UPSERT, cân nhắc MERGE hoặc xử lý duplicate key, nhưng vẫn phải hiểu hành vi cạnh tranh và ràng buộc dữ liệu.

### 9.2 EXISTS để kiểm tra nghiệp vụ, constraint để bảo vệ dữ liệu

Hai cơ chế giải quyết hai câu hỏi khác nhau:

- EXISTS/NOT EXISTS: truy vấn hoặc thao tác có điều kiện dựa trên quan hệ hiện đang thấy.
- PRIMARY KEY/UNIQUE/FOREIGN KEY/CHECK: bảo vệ các bất biến dữ liệu ở database.

Một ứng dụng có thể dùng NOT EXISTS để tránh thử insert không cần thiết, nhưng UNIQUE constraint mới là hàng rào cuối cùng cho yêu cầu không trùng trong mọi transaction được database chấp nhận.

## 10. Hiệu năng và execution plan

### 10.1 Index trên cột liên kết

Với truy vấn:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Các index có thể được cân nhắc tùy workload:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Hoặc nếu thường lọc cả trạng thái:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Thứ tự cột index và quyết định có tạo index hay không phải dựa vào các truy vấn thực tế, độ chọn lọc, số dòng, phân bố dữ liệu, DML và index hiện có. Không tạo cả hai index chỉ vì ví dụ.

### 10.2 NOT EXISTS cũng cần index phù hợp

Ví dụ:

~~~sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
);
~~~

Index trên ORDER_ITEMS(PRODUCT_ID) có thể giúp Oracle kiểm tra sự tồn tại của dòng liên quan hiệu quả. Nhưng nếu bảng con nhỏ hoặc phần lớn sản phẩm được trả về, optimizer có thể chọn chiến lược khác.

### 10.3 Semi-join và anti-join trong plan

Oracle optimizer có thể biến đổi EXISTS thành các phép nối vật lý như:

- NESTED LOOPS SEMI.
- HASH JOIN SEMI.
- MERGE JOIN SEMI.
- Các dạng ANTI tương ứng cho NOT EXISTS.

Tên operation cụ thể phụ thuộc phiên bản, truy vấn và plan. Điều quan trọng là semi-join chỉ cần xác nhận có khớp, không cần trả mọi cặp cha-con như join thông thường.

### 10.4 Unnesting subquery

Oracle có thể chuyển correlated subquery thành join tương đương để tối ưu. Đây thường được gọi là subquery unnesting. Một số cấu trúc, hàm hoặc ràng buộc ngữ nghĩa có thể hạn chế transformation.

Không nên thêm hint như UNNEST hoặc NO_UNNEST chỉ vì nghĩ correlated subquery luôn chậm. Hãy kiểm tra execution plan và số liệu thực thi trước.

### 10.5 EXPLAIN PLAN

Trong schema lab có quyền:

~~~sql
EXPLAIN PLAN FOR
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN cho biết kế hoạch dự kiến. Khi tuning production, nên xem actual cursor plan và thống kê runtime phù hợp; đừng kết luận tốc độ chỉ từ một dòng operation hoặc số cost ước lượng.

## 11. EXISTS, IN và JOIN: chọn theo ý định

### 11.1 EXISTS và IN

Hai cách có thể tương đương trong một số điều kiện:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Với khóa so sánh không NULL hoặc semantics được kiểm soát, hai truy vấn có thể trả cùng tập khách hàng. Tuy nhiên EXISTS biểu đạt quan hệ tương quan và thường dễ mở rộng thêm điều kiện từ bảng con.

IN kiểm tra giá trị thuộc một tập. EXISTS kiểm tra có dòng thỏa điều kiện tương quan. Chọn theo ý định và chú ý NULL.

### 11.2 NOT EXISTS và NOT IN

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Hai cách không luôn tương đương khi tập con có NULL hoặc khóa ngoài có NULL. NOT IN có thể bị UNKNOWN do NULL trong danh sách; NOT EXISTS kiểm tra quan hệ bằng trực tiếp. Nếu muốn loại cả khóa ngoài NULL, thêm IS NOT NULL một cách tường minh.

### 11.3 EXISTS và JOIN

| Câu hỏi | EXISTS | JOIN |
|---|---|---|
| Có ít nhất một dòng con phù hợp? | Rất phù hợp | Có thể cần DISTINCT hoặc GROUP BY nếu chỉ muốn cha duy nhất |
| Cần cột từ bảng con? | Không trả cột con trực tiếp | Phù hợp |
| Nhiều dòng con trên một cha | Không nhân bản cha chỉ vì nhiều dòng con | Có thể tạo nhiều dòng kết hợp |
| Không có dòng con | NOT EXISTS diễn đạt trực tiếp | LEFT JOIN rồi lọc NULL có thể làm được |
| Cần đếm hoặc tổng hợp con | Dùng scalar aggregate hoặc GROUP BY phù hợp | JOIN + GROUP BY thường tự nhiên |

Không có quy tắc rằng EXISTS luôn nhanh hơn JOIN. Optimizer có thể chuyển đổi các dạng tương đương; dữ liệu và plan quyết định hiệu năng. Trước tiên hãy viết câu truy vấn phản ánh đúng kết quả mong muốn.

## 12. Các mẫu truy vấn thường dùng

### 12.1 Cha có ít nhất một con

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
);
~~~

### 12.2 Cha không có con

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
);
~~~

### 12.3 Có con thỏa nhiều điều kiện

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status = 'READY'
      AND ch.created_at >= DATE '2026-01-01'
);
~~~

### 12.4 Không có con thỏa điều kiện

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status = 'FAILED'
);
~~~

Đây không nhất thiết là cha không có con nào; nó là cha không có con ở trạng thái FAILED.

### 12.5 Có ít nhất một con và không có con nào vi phạm

~~~sql
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
)
AND NOT EXISTS (
    SELECT 1
    FROM child_table ch
    WHERE ch.parent_id = p.parent_id
      AND ch.status <> 'APPROVED'
);
~~~

Ví dụ tìm cha có ít nhất một con và không có con nào có trạng thái khác APPROVED. Cần quyết định riêng cách xử lý STATUS NULL: điều kiện STATUS <> 'APPROVED' không TRUE với NULL, nên nếu NULL cũng là vi phạm, thêm OR STATUS IS NULL.

### 12.6 Kiểm tra một quan hệ trên hai cột

~~~sql
SELECT a.account_id
FROM accounts a
WHERE EXISTS (
    SELECT 1
    FROM account_permissions ap
    WHERE ap.account_id = a.account_id
      AND ap.resource_id = :p_resource_id
      AND ap.permission_code = :p_permission
);
~~~

EXISTS có thể kiểm tra nhiều cột quan hệ và điều kiện nghiệp vụ cùng lúc. Đây là mẫu phổ biến cho kiểm tra quyền ở tầng truy vấn, nhưng không thay thế authorization đầy đủ ở tầng ứng dụng và chính sách bảo mật database.

## 13. Bài lab: khách hàng, đơn hàng và thanh toán

Phần thực hành sử dụng schema lab riêng có quyền tạo bảng và quota phù hợp. Không chạy DDL/DML thử nghiệm trong schema production. Oracle DDL có implicit commit.

### 13.1 Tạo bảng

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL
);

CREATE TABLE lab_orders (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER,
    order_date  DATE NOT NULL,
    status      VARCHAR2(20) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);

CREATE TABLE lab_payments (
    payment_id     NUMBER PRIMARY KEY,
    order_id       NUMBER NOT NULL,
    payment_status VARCHAR2(20) NOT NULL,
    paid_amount    NUMBER(12,2) NOT NULL
);
~~~

### 13.2 Nạp dữ liệu mẫu

~~~sql
INSERT INTO lab_customers VALUES (1, 'An');
INSERT INTO lab_customers VALUES (2, 'Binh');
INSERT INTO lab_customers VALUES (3, 'Chi');
INSERT INTO lab_customers VALUES (4, 'Dung');
INSERT INTO lab_customers VALUES (5, 'Empty Customer');

INSERT INTO lab_orders VALUES
    (101, 1, DATE '2026-11-01', 'PAID', 1200000);
INSERT INTO lab_orders VALUES
    (102, 1, DATE '2026-11-05', 'PENDING', 500000);
INSERT INTO lab_orders VALUES
    (103, 2, DATE '2026-11-07', 'CANCELLED', 300000);
INSERT INTO lab_orders VALUES
    (104, 3, DATE '2026-11-10', 'PAID', 2500000);
INSERT INTO lab_orders VALUES
    (105, NULL, DATE '2026-11-11', 'PAID', 900000);

INSERT INTO lab_payments VALUES
    (1001, 101, 'CONFIRMED', 1200000);
INSERT INTO lab_payments VALUES
    (1002, 102, 'FAILED', 0);
INSERT INTO lab_payments VALUES
    (1003, 104, 'CONFIRMED', 2500000);

COMMIT;
~~~

Dữ liệu được thiết kế để có:

- Khách hàng 1 có hai đơn.
- Khách hàng 2 có một đơn CANCELLED.
- Khách hàng 3 có một đơn đã thanh toán.
- Khách hàng 4 và 5 không có đơn.
- Có một đơn với CUSTOMER_ID NULL, để minh họa NULL trong bảng con.
- Đơn 102 có payment FAILED nhưng không có payment CONFIRMED.

### 13.3 Tìm khách hàng có ít nhất một đơn

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả gồm An, Binh và Chi. Mỗi khách hàng xuất hiện một lần dù An có hai đơn.

### 13.4 Tìm khách hàng chưa từng đặt hàng

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả gồm Dung và Empty Customer. Đơn có CUSTOMER_ID NULL không khớp bất kỳ customer_id cụ thể nào và không làm tất cả khách hàng bị loại.

### 13.5 Tìm khách hàng có đơn đã thanh toán

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả gồm An và Chi.

### 13.6 Tìm khách hàng không có đơn đã thanh toán

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả gồm Binh, Dung và Empty Customer. Binh có đơn CANCELLED nhưng không có đơn PAID. Đây không phải danh sách khách hàng chưa từng có đơn.

### 13.7 Tìm đơn chưa có thanh toán CONFIRMED

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.status
FROM lab_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
ORDER BY o.order_id;
~~~

Kết quả gồm các đơn 102, 103 và 105. Đơn 102 có payment FAILED nhưng không có CONFIRMED; đơn 103 và 105 chưa có dòng payment.

### 13.8 Tìm đơn có ít nhất một thanh toán xác nhận

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.total_amount
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'CONFIRMED'
)
ORDER BY o.order_id;
~~~

Kết quả gồm đơn 101 và 104. Mỗi đơn chỉ xuất hiện một lần dù sau này có thể có nhiều dòng payment xác nhận.

### 13.9 So sánh JOIN và EXISTS

JOIN:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

An xuất hiện hai lần vì có hai đơn. EXISTS:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

An chỉ xuất hiện một lần. Hai câu SQL đang trả shape kết quả khác nhau: JOIN trả cặp cha-con; EXISTS trả dòng cha có quan hệ.

### 13.10 So sánh NOT IN và NOT EXISTS khi có NULL

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM lab_orders o
)
ORDER BY c.customer_id;
~~~

Subquery có một CUSTOMER_ID NULL, vì vậy NOT IN có thể không trả khách hàng nào do logic UNKNOWN.

Thử NOT EXISTS:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả là Dung và Empty Customer. Đây là minh họa trực tiếp cho bẫy NULL của NOT IN.

## 14. Cách đọc một truy vấn EXISTS trước khi chạy

Khi gặp EXISTS hoặc NOT EXISTS, hãy trả lời các câu hỏi:

1. **Dòng ngoài là đối tượng nào?** Ví dụ khách hàng, sản phẩm, đơn hàng.
2. **Quan hệ nào cần kiểm tra?** Khóa ngoại, bảng nối, hoặc điều kiện nghiệp vụ.
3. **Điều kiện tương quan nằm ở đâu?** Thường là predicate nối cột con với khóa của dòng ngoài.
4. **Các predicate bổ sung có đúng vị trí không?** Trạng thái, ngày, số tiền và quyền.
5. **NULL có thể xuất hiện ở khóa hoặc dữ liệu lọc không?** Nếu có, xác định semantics.
6. **Kết quả cần dòng cha một lần hay cần các cặp cha-con?** Nếu chỉ cần cha, EXISTS thường phù hợp.
7. **Có yêu cầu duy nhất/concurrency không?** Dùng constraint khi cần bảo vệ bất biến.

Một mẫu đọc:

~~~sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
      AND oi.quantity > 0
);
~~~

Diễn giải chính xác: “Lấy các sản phẩm mà không tồn tại dòng chi tiết đơn hàng có cùng PRODUCT_ID và QUANTITY lớn hơn 0.” Nó không khẳng định sản phẩm chưa từng xuất hiện trong mọi dòng order_items, vì các dòng quantity bằng 0 không thỏa điều kiện.

## 15. Những lỗi thường gặp

| Lỗi hoặc ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| EXISTS cần SELECT một cột không NULL | EXISTS chỉ xét dòng có tồn tại | SELECT 1 là quy ước dễ đọc |
| SELECT NULL làm EXISTS sai | Dòng vẫn tồn tại dù giá trị chọn là NULL | Kiểm tra điều kiện WHERE của subquery |
| EXISTS trả số dòng con | EXISTS chỉ trả điều kiện đúng/sai | Dùng COUNT nếu cần số lượng |
| EXISTS với SELECT COUNT(*) không tìm thấy dòng vẫn sai | Aggregate không GROUP BY trả một dòng COUNT=0 | Dùng SELECT 1 để kiểm tra dòng dữ liệu |
| NOT EXISTS nghĩa là cột con IS NULL | Nó kiểm tra không có dòng thỏa toàn bộ predicate | Viết điều kiện quan hệ đúng |
| JOIN luôn tương đương EXISTS | JOIN có thể nhân bản dòng cha theo số dòng con | Chọn theo shape kết quả |
| NOT IN luôn giống NOT EXISTS | NULL trong subquery có thể làm NOT IN thành UNKNOWN | Dùng NOT EXISTS hoặc loại NULL có chủ đích |
| NOT EXISTS tự loại khóa cha NULL | So sánh với NULL không TRUE, nên NOT EXISTS có thể đúng | Thêm IS NOT NULL nếu nghiệp vụ yêu cầu |
| EXISTS luôn chạy chậm vì correlated | Optimizer có thể unnest thành semi-join | Xem execution plan và runtime |
| NOT EXISTS chống trùng tuyệt đối khi INSERT | Nhiều session có thể cùng kiểm tra rồi cùng insert | Dùng UNIQUE constraint và xử lý lỗi |
| Dùng SELECT * trong EXISTS giúp lấy dữ liệu con | SELECT list không được trả ra ngoài | Chọn 1 để thể hiện ý định |
| HAVING thay cho predicate liên kết | HAVING lọc nhóm, không tự tạo quan hệ | Đặt correlation trong WHERE của subquery |

## 16. Checklist tối ưu và vận hành

Trước khi đưa truy vấn vào ứng dụng:

- Viết predicate tương quan bằng alias rõ ràng, tránh cột không định danh.
- Chỉ đặt các điều kiện cần thiết để định nghĩa “có liên quan”.
- Dùng EXISTS khi cần dòng cha có con; NOT EXISTS khi cần dòng cha không có con thỏa điều kiện.
- Kiểm tra NULL ở khóa ngoài, khóa trong và cột trạng thái.
- Với NOT IN, xác nhận subquery không thể trả NULL hoặc lọc NULL rõ ràng.
- Không dùng COUNT(*) trong EXISTS nếu không cần aggregate; aggregate không GROUP BY có thể luôn trả một dòng.
- Kiểm tra index trên các cột liên kết và predicate lọc theo workload thực tế.
- Xem execution plan và actual runtime trên dữ liệu đại diện.
- Dùng ràng buộc UNIQUE/FOREIGN KEY để bảo vệ tính toàn vẹn; EXISTS không thay thế constraint.
- Với DML, kiểm tra phạm vi dòng bị tác động và transaction trước khi commit.

## 17. Tổng kết

EXISTS và NOT EXISTS là hai điều kiện để kiểm tra quan hệ tồn tại trong Oracle SQL. EXISTS đúng khi truy vấn con có ít nhất một dòng phù hợp; NOT EXISTS đúng khi không có dòng nào phù hợp. Khi correlated subquery tham chiếu dòng ngoài, hai hàm diễn đạt trực tiếp quan hệ giữa bảng cha và bảng con.

Hãy nhớ các nguyên tắc:

- Dùng SELECT 1 trong EXISTS để thể hiện rõ chỉ kiểm tra sự tồn tại; giá trị trong SELECT list không quyết định kết quả.
- EXISTS thường tương ứng semi-join, NOT EXISTS thường tương ứng anti-join; optimizer có thể chuyển đổi truy vấn khi lập kế hoạch.
- EXISTS tránh nhân bản dòng cha do có nhiều dòng con khi mục tiêu chỉ là kiểm tra có quan hệ.
- NOT EXISTS thường an toàn và dễ đọc hơn NOT IN khi subquery có thể chứa NULL.
- NULL ở khóa ngoài vẫn cần chính sách rõ; NOT EXISTS không tự có nghĩa khóa không NULL.
- EXISTS trong DML không thay thế UNIQUE constraint và không tự bảo đảm chống race condition.
- Chọn EXISTS, JOIN, IN hoặc COUNT theo kết quả cần trả về; kiểm tra plan trước khi kết luận hiệu năng.

Khi nắm vững các quy tắc này, bạn có thể viết truy vấn “có ít nhất một”, “không có bất kỳ”, “có quan hệ nhưng chưa có trạng thái” và các điều kiện quan hệ lồng nhau một cách rõ ràng, chính xác và dễ bảo trì.
