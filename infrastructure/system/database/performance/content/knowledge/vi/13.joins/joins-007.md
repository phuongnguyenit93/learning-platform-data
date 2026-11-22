# Chẩn đoán nhân bản số hàng và tích Descartes ngoài ý muốn

## Vì sao phép nối có thể làm số hàng tăng bất thường?

JOIN kết hợp hàng từ nhiều bảng theo một điều kiện liên kết. Số hàng kết quả có thể lớn hơn số hàng ở từng bảng vì một hàng bên trái khớp với nhiều hàng bên phải. Đây là hành vi đúng của phép nối khi quan hệ dữ liệu là một-nhiều hoặc nhiều-nhiều. Tuy nhiên, nếu người viết truy vấn kỳ vọng mỗi đơn hàng chỉ xuất hiện một lần mà kết quả có hàng chục dòng cho cùng một đơn, cần xác định đó là quan hệ nghiệp vụ hợp lệ hay lỗi trong điều kiện nối.

Một dạng lỗi nghiêm trọng là tích Descartes ngoài ý muốn (unintended Cartesian product): hai tập hàng được kết hợp mà thiếu điều kiện liên kết cần thiết, hoặc điều kiện nối không đủ để xác định đúng cặp hàng. Khi đó số hàng có thể tăng theo tích kích thước hai tập, gây tốn CPU, bộ nhớ, I/O, mạng và làm sai kết quả tổng hợp.

Trong tối ưu hiệu năng cơ sở dữ liệu, chẩn đoán hiện tượng này cần kết hợp hiểu biết về khóa và cardinality với kế hoạch thực thi, thống kê dữ liệu và tải thực tế. Một JOIN có nhiều hàng không tự động là sai; một JOIN có ít hàng cũng không tự động đúng. Cần biết mức độ chi tiết (grain) mà mỗi hàng đại diện, quan hệ giữa các bảng và số hàng được kỳ vọng sau từng bước nối.

Bài học này tập trung vào cách nhận diện nhân bản số hàng, phát hiện tích Descartes, tìm điều kiện nối thiếu hoặc sai, xử lý quan hệ nhiều-nhiều và kiểm chứng rằng truy vấn trả đúng kết quả với chi phí hợp lý.

## Grain và cardinality của bảng

### Grain: mỗi hàng đại diện cho điều gì?

Grain là mức độ chi tiết của dữ liệu trong một bảng hoặc một tập kết quả. Ví dụ:

- Bảng customers có một hàng cho mỗi khách hàng.
- Bảng orders có một hàng cho mỗi đơn hàng.
- Bảng order_items có một hàng cho mỗi dòng hàng trong đơn.
- Bảng payments có thể có nhiều hàng cho một đơn vì đơn có thể được thanh toán nhiều lần.
- Bảng order_status_history có nhiều hàng cho một đơn vì trạng thái được ghi lại qua thời gian.

Trước khi JOIN, hãy diễn đạt grain của từng nguồn bằng một câu. Nếu không biết mỗi hàng đại diện cho một thực thể hay một sự kiện nào, rất khó xác định việc nhân bản là hợp lệ.

Ví dụ, khi nối orders với order_items, kết quả thường có một hàng cho mỗi dòng hàng, không còn một hàng cho mỗi đơn. Nếu một đơn có bốn dòng hàng, thông tin đơn hàng sẽ xuất hiện bốn lần. Đây không phải lỗi JOIN; đó là thay đổi grain từ đơn hàng sang dòng hàng.

### Cardinality: quan hệ giữa hai tập hàng

Cardinality mô tả số hàng hoặc số lượng giá trị khác nhau trong một tập dữ liệu, và trong ngữ cảnh JOIN còn mô tả số hàng kết quả dự kiến từ quan hệ giữa hai phía.

Các kiểu quan hệ phổ biến:

| Quan hệ | Ý nghĩa | Ví dụ |
|---|---|---|
| Một-một (1:1) | Mỗi hàng ở A khớp tối đa một hàng ở B và ngược lại | Người dùng và hồ sơ mở rộng duy nhất |
| Một-nhiều (1:N) | Một hàng ở A có thể khớp nhiều hàng ở B | Một đơn hàng có nhiều dòng hàng |
| Nhiều-một (N:1) | Nhiều hàng ở A cùng tham chiếu một hàng ở B | Nhiều đơn hàng thuộc một khách hàng |
| Nhiều-nhiều (N:M) | Nhiều hàng ở mỗi phía có thể khớp nhiều hàng phía kia | Sinh viên đăng ký nhiều môn, mỗi môn có nhiều sinh viên |

Khóa chính, unique constraint và foreign key là bằng chứng quan trọng về quan hệ. Nếu cột được dùng để nối ở phía B có UNIQUE, mỗi hàng A có thể khớp tối đa một hàng B theo cột đó. Nếu cột không duy nhất, JOIN có thể nhân bản hàng A.

Foreign key đảm bảo giá trị tham chiếu có quy tắc toàn vẹn theo cấu hình schema, nhưng không tự đảm bảo phía được tham chiếu là duy nhất trừ khi cột tham chiếu là khóa hoặc có ràng buộc UNIQUE. Cần xem đúng cột và đúng tổ hợp cột được dùng trong JOIN.

### Công thức số hàng của phép nối bằng

Với một khóa nối k, giả sử phía A có a(k) hàng mang khóa k và phía B có b(k) hàng mang khóa k. Số cặp hàng khớp cho khóa đó là:

~~~text
a(k) * b(k)
~~~

Tổng số hàng của INNER JOIN theo khóa bằng là tổng tích trên tất cả khóa có mặt ở cả hai phía:

~~~text
Rows(A JOIN B) = SUM over matching k of a(k) * b(k)
~~~

Nếu khóa ở phía B là duy nhất thì b(k) không vượt quá 1, vì vậy mỗi hàng A khớp tối đa một hàng B. Nếu cả hai phía đều có nhiều hàng cho cùng khóa, số cặp có thể tăng nhanh.

Ví dụ: một mã khách hàng xuất hiện 3 lần trong bảng A và 4 lần trong bảng B. JOIN theo mã đó tạo 12 hàng cho riêng mã này. Nếu nghiệp vụ kỳ vọng chỉ có một hồ sơ khách hàng, dữ liệu trùng hoặc điều kiện nối thiếu có thể là nguyên nhân.

## Nhận diện tích Descartes ngoài ý muốn

### Tích Descartes là gì?

Tích Descartes kết hợp mỗi hàng của tập A với mọi hàng của tập B. Nếu A có m hàng và B có n hàng, kết quả có m × n hàng, trước khi áp dụng bộ lọc khác.

Trong SQL, CROSS JOIN thể hiện rõ tích Descartes:

~~~sql
SELECT *
FROM regions AS r
CROSS JOIN currencies AS c;
~~~

Nếu regions có 20 hàng và currencies có 8 hàng, kết quả có 160 hàng. Đây có thể là mục đích hợp lệ khi cần mọi tổ hợp vùng và loại tiền. Nhưng nếu truy vấn báo cáo đơn hàng vô tình tạo tích giữa orders và order_items, số hàng tăng theo tích hai bảng và có thể gây sai tổng tiền.

Một số dạng viết cũ hoặc lỗi có thể tạo tích Descartes:

~~~sql
-- Thiếu điều kiện nối giữa hai bảng
SELECT o.order_id, c.customer_name
FROM orders AS o, customers AS c;
~~~

Hoặc:

~~~sql
-- JOIN có điều kiện luôn đúng
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON 1 = 1;
~~~

Một số hệ quản trị từ chối cú pháp JOIN thiếu ON trong một số dạng viết, nhưng comma join hoặc điều kiện luôn đúng vẫn có thể tạo kết quả tích Descartes. Không dựa vào việc parser chấp nhận hay từ chối; hãy kiểm tra logic của mọi cặp bảng trong FROM.

### Dấu hiệu trong kế hoạch thực thi

Các dấu hiệu cần điều tra:

- Một toán tử tạo ra số hàng lớn hơn nhiều số hàng đầu vào.
- Nested Loops có nhánh trong được thực hiện rất nhiều lần.
- Hash Join hoặc Merge Join tạo số hàng đầu ra lớn hơn dự kiến.
- Một nhánh có số hàng ước lượng thấp nhưng số hàng thực tế tăng đột biến.
- Điều kiện nối bị thiếu, không chọn lọc hoặc chỉ nối một phần khóa ghép.
- Bộ lọc quan trọng xuất hiện sau một bước kết hợp dữ liệu rất lớn.
- Sort, hash table, memory grant hoặc vùng lưu trữ tạm tăng mạnh.
- Thời gian, CPU, logical reads và dữ liệu truyền về ứng dụng tăng đột biến.

Không phải mọi Nested Loops đều là lỗi và cũng không phải mọi đầu ra lớn đều là tích Descartes. Một phép nối đơn hàng với dòng hàng vốn phải tăng số hàng. Hãy đối chiếu số hàng thực tế với grain và cardinality nghiệp vụ.

### Phân biệt Cartesian product với many-to-many hợp lệ

Nếu cả hai bảng có nhiều hàng trên cùng khóa, phép nối bằng có thể tạo nhiều cặp. Điều này có thể là đúng nếu mô hình nghiệp vụ thực sự là nhiều-nhiều. Ví dụ, một đơn hàng có nhiều mã khuyến mại áp dụng và mỗi mã có nhiều quy tắc điều kiện; nếu truy vấn cần mọi tổ hợp tương ứng, số hàng tăng có thể hợp lệ.

Điều cần xác minh:

1. Có bảng liên kết (bridge/junction table) thể hiện quan hệ nhiều-nhiều không?
2. Khóa nối có đầy đủ các cột xác định quan hệ không?
3. Có điều kiện hiệu lực theo thời gian hoặc trạng thái bị thiếu không?
4. Kết quả có đang thể hiện đúng grain mà người dùng cần không?
5. Số tổ hợp có đúng theo quy tắc nghiệp vụ hay chỉ là trùng dữ liệu?

Một phép nối nhiều-nhiều hợp lệ vẫn có thể rất tốn kém. Khi kết quả cần tổng hợp, có thể phải tổng hợp trước từng phía hoặc dùng EXISTS thay cho việc tạo mọi cặp hàng.

## Tìm điều kiện JOIN thiếu hoặc sai

### Chỉ nối một phần khóa ghép

Nhiều bảng được định danh bằng khóa ghép (composite key), gồm từ hai cột trở lên. Nếu chỉ nối một phần khóa, hàng từ các nhóm khác nhau có thể khớp nhầm.

Ví dụ, bảng order_items có khóa ghép (order_id, line_no), còn bảng item_adjustments tham chiếu đến từng dòng hàng:

~~~sql
-- Sai nếu adjustment thuộc về một dòng hàng cụ thể
SELECT oi.order_id, oi.line_no, a.adjustment_amount
FROM order_items AS oi
JOIN item_adjustments AS a
  ON a.order_id = oi.order_id;
~~~

Nếu một đơn có 4 dòng và 3 điều chỉnh cho 3 dòng khác nhau, nối chỉ theo order_id có thể ghép mỗi điều chỉnh với cả 4 dòng. Điều kiện đúng cần bao gồm line_no nếu đó là khóa xác định quan hệ:

~~~sql
SELECT oi.order_id, oi.line_no, a.adjustment_amount
FROM order_items AS oi
JOIN item_adjustments AS a
  ON a.order_id = oi.order_id
 AND a.line_no = oi.line_no;
~~~

Không phải cứ thêm nhiều cột vào ON là đúng. Phải dùng đúng khóa ngoại hoặc quy tắc liên kết đã được định nghĩa trong nghiệp vụ.

### Nối nhầm cột có cùng kiểu hoặc tên gần giống

Hai cột cùng kiểu dữ liệu có thể mang ý nghĩa khác nhau, ví dụ customer_id và created_by_id đều là số nguyên. Nối nhầm có thể không gây lỗi cú pháp nhưng tạo kết quả sai hoặc số hàng tăng bất thường.

Hãy kiểm tra:

- Tên và ý nghĩa nghiệp vụ của cột.
- Khóa chính/khóa ngoại hoặc unique constraint liên quan.
- Tỷ lệ giá trị khớp và số hàng không khớp.
- Mẫu dữ liệu thực tế của các cặp khóa.
- Mức độ duy nhất ở mỗi phía.

Không dựa vào tên cột hoặc kiểu dữ liệu đơn thuần để suy ra quan hệ.

### Thiếu điều kiện theo tenant, tổ chức hoặc phạm vi dữ liệu

Trong hệ thống đa tenant, một mã thực thể có thể chỉ duy nhất trong từng tenant. Ví dụ, customer_id = 100 có thể tồn tại ở nhiều tenant. Nếu chỉ nối theo customer_id mà bỏ tenant_id, dữ liệu của các tenant khác nhau có thể bị kết hợp.

Ví dụ:

~~~sql
-- Thiếu tenant_id nếu customer_id chỉ duy nhất trong tenant
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
~~~

Nếu khóa nghiệp vụ là (tenant_id, customer_id), điều kiện cần nối cả hai cột:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
~~~

Quy tắc tương tự có thể áp dụng cho region, company, source_system, locale hoặc namespace. Bỏ một thành phần của khóa phạm vi có thể gây nhân bản hoặc rò rỉ dữ liệu giữa các miền nghiệp vụ.

### Thiếu điều kiện hiệu lực theo thời gian

Bảng lịch sử hoặc bảng phiên bản có thể chứa nhiều hàng cho cùng một business key. Ví dụ, customer_history lưu từng phiên bản thông tin khách hàng theo khoảng thời gian hiệu lực. Nếu JOIN chỉ theo customer_id, một đơn hàng có thể khớp với mọi phiên bản lịch sử của khách hàng.

Mô hình khoảng hiệu lực thường cần điều kiện tương tự:

~~~sql
SELECT o.order_id, h.customer_segment
FROM orders AS o
JOIN customer_history AS h
  ON h.customer_id = o.customer_id
 AND o.created_at >= h.valid_from
 AND o.created_at <  h.valid_to;
~~~

Điều kiện thời gian phải phản ánh chính xác quy tắc dữ liệu. Cần xác định khoảng đóng/mở, cách biểu diễn phiên bản hiện tại và xử lý valid_to NULL. Nếu các khoảng hiệu lực bị chồng lấn do dữ liệu sai, ngay cả điều kiện thời gian đầy đủ vẫn có thể trả nhiều phiên bản.

### Điều kiện lọc đặt sai vị trí với OUTER JOIN

LEFT JOIN giữ hàng bên trái không có hàng khớp bên phải và điền NULL cho cột phía phải. Nếu đưa điều kiện lọc cột bên phải vào WHERE, những hàng NULL có thể bị loại, làm kết quả hoạt động giống INNER JOIN đối với điều kiện đó.

Ví dụ:

~~~sql
-- Loại khách hàng không có đơn READY vì điều kiện ở WHERE
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'READY';
~~~

Nếu mục tiêu là giữ mọi khách hàng và chỉ lấy các đơn READY khi có, đặt điều kiện vào ON:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'READY';
~~~

Đây chủ yếu là vấn đề ngữ nghĩa và số hàng bị loại, không nhất thiết là nguyên nhân nhân bản. Nhưng khi chẩn đoán cardinality, phải phân biệt điều kiện nối với điều kiện lọc sau nối để hiểu đúng tập hàng.

## Fan-out khi nối nhiều bảng con

### Nhân bản do hai bảng con độc lập

Một lỗi báo cáo thường gặp là nối một bảng cha với hai bảng con có quan hệ một-nhiều độc lập. Ví dụ:

- Một đơn có 3 dòng hàng.
- Một đơn có 2 lần thanh toán.

Nếu nối orders với order_items rồi nối tiếp payments chỉ theo order_id, kết quả có 3 × 2 = 6 hàng cho đơn đó. Mỗi dòng hàng xuất hiện hai lần và mỗi khoản thanh toán xuất hiện ba lần.

~~~sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
JOIN payments AS p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
~~~

Truy vấn trên có thể tính sai cả item_total và paid_total do fan-out. Với đơn có 3 dòng hàng và 2 khoản thanh toán, mỗi dòng hàng bị lặp hai lần, mỗi khoản thanh toán bị lặp ba lần.

Đây không phải tích Descartes toàn bảng, vì hai nhánh vẫn liên kết qua order_id. Nhưng nó là tích các tập con theo từng khóa cha và tạo nhân bản ngoài ý muốn đối với phép tổng hợp.

### Tổng hợp từng nhánh trước khi nối

Nếu cần tổng tiền dòng hàng và tổng tiền thanh toán theo đơn, hãy tổng hợp từng bảng con về đúng grain một hàng mỗi đơn trước:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM orders AS o
LEFT JOIN item_totals AS i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals AS p
  ON p.order_id = o.order_id;
~~~

Mỗi CTE tạo tối đa một hàng cho mỗi order_id. Khi nối vào orders, hai nhánh không còn nhân bản lẫn nhau. Hãy kiểm tra điều kiện khóa và đảm bảo mỗi CTE thật sự có grain một hàng mỗi đơn.

Một CTE không mặc nhiên được materialize trong mọi hệ quản trị. Optimizer có thể inline hoặc biến đổi truy vấn, nhưng ngữ nghĩa nhóm vẫn bảo đảm mỗi khóa có tối đa một hàng trong kết quả tổng hợp. Nếu kế hoạch vẫn tốn kém, kiểm tra việc quét và tổng hợp bảng con, chỉ mục trên order_id, cùng khả năng đẩy bộ lọc.

### Dùng EXISTS khi chỉ cần biết có hàng liên quan

Nếu mục tiêu chỉ là lọc đơn hàng có ít nhất một khoản thanh toán thành công, không cần JOIN toàn bộ payment:

~~~sql
SELECT o.order_id, o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
      AND p.status = 'SUCCESS'
);
~~~

EXISTS kiểm tra sự tồn tại và không nhân bản hàng orders khi có nhiều khoản thanh toán khớp. Optimizer có thể triển khai dưới dạng semi join hoặc chiến lược tương đương.

Nếu cần dữ liệu của từng khoản thanh toán, JOIN là phù hợp; nếu chỉ cần biết có hay không, EXISTS thường diễn đạt đúng mục tiêu và tránh fan-out không cần thiết.

## Xử lý quan hệ nhiều-nhiều

### Bảng liên kết và khóa duy nhất

Quan hệ nhiều-nhiều thường được biểu diễn bằng bảng liên kết. Ví dụ student_courses có student_id và course_id. Mỗi sinh viên có thể có nhiều khóa học và mỗi khóa học có nhiều sinh viên.

Nếu một cặp (student_id, course_id) chỉ được phép xuất hiện một lần, nên có unique constraint trên cặp này. Nếu không, dữ liệu trùng có thể làm JOIN nhân bản ngoài ý muốn.

~~~sql
SELECT s.student_id, s.student_name, c.course_id, c.course_name
FROM students AS s
JOIN student_courses AS sc
  ON sc.student_id = s.student_id
JOIN courses AS c
  ON c.course_id = sc.course_id;
~~~

Kết quả có grain một hàng cho mỗi quan hệ đăng ký sinh viên-khóa học. Một sinh viên xuất hiện nhiều lần là đúng nếu đăng ký nhiều khóa học. Nếu báo cáo cần một hàng mỗi sinh viên, cần tổng hợp hoặc dùng EXISTS tùy mục đích.

### Phân biệt dữ liệu trùng với quan hệ hợp lệ

Không dùng DISTINCT như biện pháp mặc định để chữa nhân bản. DISTINCT có thể che giấu lỗi điều kiện nối, tiêu tốn sort/hash và làm mất các hàng khác nhau hợp lệ nếu cột chọn không thể hiện đầy đủ grain.

Trước khi loại trùng, cần xác định:

- Hai hàng có thật sự đại diện cho cùng một thực thể nghiệp vụ không?
- Khóa nào xác định duy nhất một quan hệ?
- Hàng nào được giữ nếu có nhiều phiên bản?
- Quy tắc chọn hàng có thứ tự xác định không?
- Có nên ngăn trùng ở tầng schema bằng UNIQUE constraint không?

Nếu cần chọn một phiên bản theo thời điểm mới nhất, có thể dùng ROW_NUMBER với thứ tự xác định:

~~~sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY h.updated_at DESC, h.history_id DESC
        ) AS rn
    FROM customer_history AS h
)
SELECT customer_id, customer_segment
FROM ranked
WHERE rn = 1;
~~~

Ví dụ này chỉ phù hợp khi nghiệp vụ thực sự yêu cầu phiên bản mới nhất cho mỗi khách hàng. Cột history_id là tiêu chí phụ để thứ tự không bị tùy ý khi updated_at trùng nhau. Không chọn một hàng tùy tiện chỉ để làm kết quả có vẻ duy nhất.

## Quy trình chẩn đoán nhân bản số hàng

### Bước 1: xác định grain đầu vào và đầu ra

Viết rõ mỗi hàng ở từng bảng đại diện cho điều gì và kết quả mong muốn đại diện cho điều gì. Ví dụ:

| Nguồn | Grain | Khóa hoặc định danh dự kiến |
|---|---|---|
| customers | Một khách hàng | customer_id hoặc (tenant_id, customer_id) |
| orders | Một đơn hàng | order_id |
| order_items | Một dòng hàng | (order_id, line_no) |
| payments | Một giao dịch thanh toán | payment_id |
| order_status_history | Một lần đổi trạng thái | history_id |

Nếu báo cáo cần một hàng mỗi đơn, nhưng đang nối cả order_items và payments, cần xác định cách tổng hợp hai nhánh con trước khi kết hợp.

### Bước 2: đo số hàng sau từng JOIN

Tách truy vấn thành các bước và đếm số hàng ở mỗi bước. Ví dụ:

~~~sql
WITH base_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
      AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
),
with_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        oi.line_no
    FROM base_orders AS o
    JOIN order_items AS oi
      ON oi.order_id = o.order_id
),
with_payments AS (
    SELECT
        wi.order_id,
        wi.line_no,
        p.payment_id
    FROM with_items AS wi
    JOIN payments AS p
      ON p.order_id = wi.order_id
)
SELECT
    (SELECT COUNT(*) FROM base_orders) AS orders_count,
    (SELECT COUNT(*) FROM with_items) AS order_item_rows,
    (SELECT COUNT(*) FROM with_payments) AS joined_rows;
~~~

Đây là cách đo từng bước, không phải truy vấn tối ưu cuối cùng. Khi số hàng tăng, so sánh mức tăng với quan hệ nghiệp vụ. Nếu một đơn có trung bình 4 dòng hàng, số hàng sau nối order_items có thể tăng khoảng bốn lần. Nếu sau khi nối payments tăng thêm trung bình ba lần, hãy kiểm tra fan-out hai nhánh.

### Bước 3: kiểm tra khóa có duy nhất không

Tìm các khóa lặp ở phía được kỳ vọng là một-một hoặc nhiều-một:

~~~sql
SELECT customer_id, COUNT(*) AS occurrences
FROM customers
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu bảng đa tenant, phải kiểm tra theo khóa ghép đúng:

~~~sql
SELECT tenant_id, customer_id, COUNT(*) AS occurrences
FROM customers
GROUP BY tenant_id, customer_id
HAVING COUNT(*) > 1;
~~~

Tương tự, kiểm tra khóa ở bảng liên kết và bảng lịch sử. Nếu có trùng hợp lệ, ghi nhận grain thực tế; nếu trùng vi phạm quy tắc, cần xử lý dữ liệu và ràng buộc schema.

### Bước 4: đo fan-out theo khóa

Đếm số hàng khớp ở phía phải cho từng khóa bên trái:

~~~sql
SELECT
    o.order_id,
    COUNT(oi.line_no) AS item_count
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.order_id
HAVING COUNT(oi.line_no) > 1;
~~~

Truy vấn này tìm đơn có nhiều dòng hàng. Đó có thể là quan hệ hợp lệ. Nếu mong đợi một hàng mỗi đơn, đây là bằng chứng cho thấy kết quả sau JOIN có grain dòng hàng.

Để tìm các khóa có số lượng khớp bất thường, sắp xếp theo số lượng giảm dần và so sánh với phân bố thông thường. Không chỉ xem trung bình; một vài khóa có độ lệch lớn (skew) có thể chi phối thời gian truy vấn.

### Bước 5: kiểm tra hàng không khớp

Dùng anti join để tìm hàng không có đối tác:

~~~sql
SELECT o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM customers AS c
    WHERE c.customer_id = o.customer_id
);
~~~

Nếu có hàng không khớp, cần xác định đó là dữ liệu mồ côi, giá trị NULL, quy tắc tenant bị thiếu hay điều kiện nối sai. Hàng không khớp thường ảnh hưởng tính đầy đủ của INNER JOIN hoặc số hàng NULL ở LEFT JOIN; nó không trực tiếp giải thích fan-out, nhưng giúp xác minh mô hình liên kết.

### Bước 6: đọc kế hoạch thực thi và cardinality estimate

Trong execution plan, xem số hàng ước lượng và thực tế ở mỗi toán tử. Đặc biệt chú ý:

- Estimated Rows và Actual Rows tại từng join.
- Số hàng đầu vào của hai nhánh.
- Số lần lặp (loops) của Nested Loops.
- Số hàng sau join so với số hàng trước join.
- Điều kiện join thực sự được dùng.
- Residual predicate hoặc filter đặt sau join.
- Hash table size, memory grant, spill và sort.
- Logical reads, CPU, elapsed time và I/O wait.

Nếu Actual Rows cao hơn Estimated Rows nhiều lần, optimizer có thể chọn join order hoặc join algorithm không phù hợp. Nguyên nhân có thể là thống kê thiếu chính xác, dữ liệu skew, tương quan giữa các cột hoặc điều kiện nối chưa đầy đủ.

Khi đọc actual plan, cần hiểu cách công cụ báo số hàng và loops. Một số công cụ báo số hàng trung bình mỗi loop, số khác báo tổng. Không nhân hoặc cộng số liệu trước khi hiểu quy ước báo cáo của hệ quản trị.

## Join order và tác động của nhân bản dữ liệu

Optimizer thường có thể thay đổi thứ tự join và lựa chọn Nested Loops, Hash Join hoặc Merge Join. Nếu một nhánh tạo ra tập hàng lớn hơn dự kiến, các toán tử phía sau có thể phải xử lý nhiều dữ liệu hơn.

Ví dụ, nối một bảng giao dịch lớn với bảng danh mục có khóa duy nhất thường không làm tăng số hàng vượt số giao dịch. Nhưng nếu bảng danh mục có nhiều phiên bản cho mỗi mã mà truy vấn chỉ nối theo mã, mỗi giao dịch có thể nhân bản theo số phiên bản. Khi tiếp tục nối với bảng chi tiết khác, fan-out có thể nhân tiếp.

Đừng cố ép join order trước khi xác định nguyên nhân cardinality. Hint hoặc cấu hình ép thứ tự có thể làm một truy vấn cụ thể nhanh hơn trong một trạng thái dữ liệu nhưng dễ suy giảm khi dữ liệu tăng. Trước hết hãy sửa điều kiện nối, thống kê, khóa duy nhất hoặc cách tổng hợp.

## Tối ưu hiệu năng sau khi đã xác nhận ngữ nghĩa

### Tạo chỉ mục trên khóa nối phù hợp

Chỉ mục trên cột JOIN có thể giảm chi phí tìm hàng, đặc biệt với Nested Loops và truy cập chọn lọc. Với khóa ghép, chỉ mục cần được thiết kế theo các cột được dùng trong điều kiện và mẫu truy vấn.

Ví dụ, nếu thường nối theo (tenant_id, customer_id), có thể đánh giá chỉ mục ghép cùng thứ tự phù hợp. Cần xem thêm điều kiện lọc và thứ tự sắp xếp của các truy vấn khác. Chỉ mục không sửa được điều kiện nối sai hoặc dữ liệu bị trùng.

### Lọc sớm khi điều kiện có thể áp dụng an toàn

Đẩy điều kiện lọc gần nguồn dữ liệu có thể giảm số hàng tham gia JOIN. Tuy nhiên, phải bảo toàn ngữ nghĩa, nhất là với OUTER JOIN, NULL và điều kiện phụ thuộc bảng còn lại.

Với LEFT JOIN, di chuyển điều kiện từ WHERE sang ON có thể thay đổi việc giữ hàng không khớp. Không áp dụng phép biến đổi chỉ vì muốn giảm cardinality; hãy xác nhận kết quả trước/sau bằng tập dữ liệu kiểm thử.

### Tổng hợp trước khi nối

Khi báo cáo cần số liệu theo khách hàng hoặc đơn hàng, tổng hợp bảng con về đúng grain trước khi JOIN thường giảm fan-out. Ví dụ, tính tổng payment theo order_id rồi mới nối vào orders. Điều này giúp tránh nhân chéo dòng hàng với giao dịch thanh toán.

### Dùng EXISTS hoặc semi join khi chỉ cần kiểm tra tồn tại

Nếu không cần cột từ bảng liên quan, EXISTS diễn đạt rõ mục tiêu và không nhân bản hàng bên trái theo số lượng hàng khớp. Optimizer thường có thể chuyển thành semi join hiệu quả.

### Dùng DISTINCT đúng mục đích

DISTINCT phù hợp khi yêu cầu nghiệp vụ là tập giá trị duy nhất của các cột được chọn. Nó không phải cách sửa mặc định cho JOIN sai. DISTINCT có thể che giấu dữ liệu trùng, tạo sort/hash bổ sung và làm mất các hàng hợp lệ khác nhau ở grain thấp hơn.

## Ví dụ tổng hợp: báo cáo doanh thu đơn hàng

Một báo cáo cần hiển thị mỗi đơn hàng cùng tổng giá trị dòng hàng và tổng tiền đã thanh toán. Truy vấn ban đầu nối orders, order_items và payments theo order_id. Đơn A có 3 dòng hàng và 2 khoản thanh toán nên kết quả trung gian có 6 hàng. Tổng dòng hàng bị nhân đôi và tổng thanh toán bị nhân ba.

Cách chẩn đoán:

1. Xác nhận grain của orders là một hàng mỗi order_id.
2. Xác nhận order_items là nhiều hàng mỗi order_id.
3. Xác nhận payments cũng là nhiều hàng mỗi order_id.
4. Đếm số hàng sau từng JOIN và kiểm tra fan-out theo từng order_id.
5. Xem actual plan để xác định join nào tạo nhiều hàng nhất và chi phí hash/sort hoặc lookup phát sinh.
6. Tính tổng từng bảng con theo order_id trước khi nối.
7. So sánh kết quả với phép tính độc lập trên một tập đơn hàng mẫu.
8. Đo lại CPU, logical reads, thời gian, memory grant và spill dưới tải đại diện.

Sau khi tổng hợp trước, mỗi nhánh có tối đa một hàng mỗi order_id. Kết quả vẫn giữ một hàng mỗi đơn và các tổng không bị nhân bản. Nếu cần xem từng dòng hàng hoặc từng khoản thanh toán, hãy tạo báo cáo ở grain tương ứng thay vì gộp chúng vào một bảng kết quả có ý nghĩa không rõ ràng.

## Những sai lầm thường gặp

- **Coi mọi hàng lặp là lỗi:** quan hệ một-nhiều tạo nhiều hàng là hành vi hợp lệ khi grain kết quả là phía con.
- **Bỏ điều kiện nối hoặc dùng điều kiện luôn đúng:** có thể tạo tích Descartes toàn bộ hoặc một phần dữ liệu.
- **Chỉ nối một phần khóa ghép:** ghép nhầm tenant, dòng hàng, phiên bản hoặc phạm vi nghiệp vụ.
- **Nối hai bảng con độc lập rồi mới tổng hợp:** tạo fan-out m × n và làm sai SUM/COUNT.
- **Dùng DISTINCT để che lỗi:** che mất nguyên nhân và có thể loại hàng hợp lệ.
- **Giả định foreign key đảm bảo duy nhất:** phía được tham chiếu cần khóa hoặc unique constraint phù hợp.
- **Bỏ qua điều kiện thời gian:** một thực thể có nhiều phiên bản hiệu lực có thể khớp cùng một hàng nghiệp vụ.
- **Đặt điều kiện OUTER JOIN sai vị trí:** làm mất hàng không khớp hoặc thay đổi ngữ nghĩa.
- **Chỉ nhìn tổng số hàng cuối:** không biết bước JOIN nào gây tăng đột biến.
- **Chỉ tối ưu join order hoặc thêm chỉ mục:** không giải quyết được cardinality sai từ điều kiện nối hoặc mô hình dữ liệu.

## Checklist chẩn đoán JOIN

- [ ] Xác định grain của từng bảng và grain mong muốn của kết quả.
- [ ] Xác định quan hệ 1:1, 1:N, N:1 hay N:M.
- [ ] Kiểm tra khóa chính, unique constraint và foreign key của các cột nối.
- [ ] Xác nhận đã dùng đủ mọi cột trong khóa ghép, tenant hoặc phạm vi dữ liệu.
- [ ] Kiểm tra điều kiện thời gian, phiên bản và trạng thái hiệu lực.
- [ ] Đo số hàng sau từng JOIN và tỷ lệ fan-out theo khóa.
- [ ] Tìm khóa trùng ở phía được kỳ vọng là duy nhất.
- [ ] Kiểm tra điều kiện JOIN thiếu, sai hoặc luôn đúng.
- [ ] Phân biệt quan hệ nhiều-nhiều hợp lệ với tích Descartes ngoài ý muốn.
- [ ] Kiểm tra fan-out giữa nhiều bảng con và tổng hợp trước khi nối khi phù hợp.
- [ ] Dùng EXISTS nếu chỉ cần biết có hàng liên quan.
- [ ] Đọc Estimated Rows, Actual Rows, loops, memory grant và spill trong kế hoạch.
- [ ] Xác minh kết quả nghiệp vụ trước/sau và đo lại dưới workload đại diện.

## Kết luận

Nhân bản số hàng sau JOIN có thể là kết quả đúng của quan hệ một-nhiều hoặc nhiều-nhiều, cũng có thể là dấu hiệu của điều kiện nối thiếu, khóa không duy nhất, sai grain hoặc tích Descartes ngoài ý muốn. Muốn phân biệt, cần bắt đầu từ ý nghĩa của mỗi hàng, khóa định danh và quan hệ nghiệp vụ; sau đó đo cardinality ở từng bước và đối chiếu với execution plan.

Khi nối nhiều bảng con độc lập, hãy đặc biệt chú ý fan-out vì số hàng có thể nhân chéo và làm sai các phép tổng hợp. Tổng hợp từng nhánh, dùng EXISTS khi chỉ cần kiểm tra sự tồn tại và thiết kế chỉ mục trên khóa nối phù hợp có thể giảm chi phí sau khi ngữ nghĩa đã đúng. Mục tiêu là giữ đúng grain và kết quả nghiệp vụ, đồng thời giảm số hàng trung gian, CPU, bộ nhớ, I/O và thời gian truy vấn.
