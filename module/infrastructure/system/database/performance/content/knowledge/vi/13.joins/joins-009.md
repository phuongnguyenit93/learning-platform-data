# Nối nhiều bảng: giảm tập dữ liệu trung gian và kiểm chứng kết quả

Một truy vấn nối nhiều bảng có thể tạo ra lượng dữ liệu trung gian lớn hơn rất nhiều so với số hàng cuối cùng cần trả về. Khi các bảng có quan hệ một-nhiều hoặc nhiều-nhiều, mỗi hàng ở một phía có thể khớp với nhiều hàng ở phía kia. Nếu nối nhiều tập dữ liệu lớn trước khi lọc hoặc tổng hợp, hệ quản trị có thể phải xử lý, lưu trữ, sắp xếp và truyền qua nhiều toán tử một lượng hàng không cần thiết.

Trong chương **Phép nối** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách đọc quan hệ giữa các bảng, kiểm soát số hàng trung gian và kiểm chứng kết quả khi tối ưu truy vấn nhiều phép nối. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, mục tiêu là giảm công việc mà hệ quản trị phải thực hiện trong khi vẫn giữ nguyên ngữ nghĩa, số lượng hàng và giá trị kết quả mà nghiệp vụ yêu cầu.

## 1. Vì sao nối nhiều bảng dễ tạo chi phí lớn?

Giả sử một hệ thống bán hàng có các bảng:

- customers: một hàng cho mỗi khách hàng.
- orders: nhiều đơn hàng có thể thuộc về một khách hàng.
- order_items: mỗi đơn hàng có thể có nhiều dòng hàng.
- payments: một đơn hàng có thể có nhiều lần thanh toán hoặc hoàn tiền.
- products: một sản phẩm có thể xuất hiện trong nhiều dòng đơn hàng.

Một báo cáo muốn hiển thị khách hàng, đơn hàng, tổng tiền hàng và tổng tiền đã thanh toán. Nếu nối trực tiếp orders với order_items và payments, một đơn hàng có 5 dòng hàng và 3 giao dịch thanh toán có thể tạo ra 15 hàng trung gian. Khi đó, tổng tiền hàng và tổng thanh toán có thể bị nhân lên nếu tính SUM sau phép nối.

Đây là hiện tượng fan-out: số hàng tăng khi một hàng ở bảng cha khớp với nhiều hàng ở bảng con, hoặc khi nhiều quan hệ một-nhiều được kết hợp. Fan-out không phải lúc nào cũng sai; truy vấn chi tiết có thể cần tất cả các tổ hợp. Nhưng nếu kết quả cuối chỉ cần một hàng cho mỗi đơn hàng, tạo ra các tổ hợp chi tiết rồi mới gom lại thường là công việc dư thừa và có nguy cơ làm sai tổng hợp.

Chi phí có thể phát sinh ở nhiều nơi:

- Đọc nhiều hàng và trang dữ liệu hơn cần thiết.
- Tạo tập kết quả trung gian lớn trong bộ nhớ.
- Hash join hoặc sort phải dùng nhiều bộ nhớ, thậm chí tràn ra vùng tạm.
- Nhiều vòng lặp tìm kiếm ở nested loop.
- Truyền nhiều hàng giữa các toán tử.
- Tăng CPU cho lọc, nối, loại trùng và tổng hợp.
- Tăng I/O khi tập trung gian vượt bộ nhớ hoặc dữ liệu không nằm trong cache.

Muốn tối ưu, trước hết phải hiểu kết quả mong muốn và lực lượng của từng quan hệ, sau đó mới chọn cách lọc, nối và tổng hợp.

## 2. Bắt đầu từ ngữ nghĩa và quan hệ dữ liệu

Trước khi thay đổi thứ tự JOIN hoặc viết lại SQL, hãy mô tả quan hệ giữa các bảng:

| Quan hệ | Bội số thường gặp | Ý nghĩa |
|---|---|---|
| customers → orders | Một-nhiều | Một khách hàng có thể có nhiều đơn |
| orders → order_items | Một-nhiều | Một đơn hàng có nhiều dòng hàng |
| orders → payments | Một-nhiều | Một đơn hàng có thể có nhiều lần thanh toán |
| products → order_items | Một-nhiều | Một sản phẩm có thể xuất hiện trong nhiều đơn |
| orders ↔ products | Nhiều-nhiều qua order_items | Một đơn có nhiều sản phẩm và một sản phẩm nằm trong nhiều đơn |

Bội số phải dựa trên khóa và ràng buộc dữ liệu thực tế. Nếu order_items.order_id tham chiếu orders.order_id, một hàng order_items thuộc về một đơn hàng, nhưng một đơn hàng có thể có nhiều dòng. Nếu payments cho phép nhiều lần thử thanh toán, quan hệ orders–payments cũng là một-nhiều.

Hãy xác định rõ:

- Khóa chính của từng bảng.
- Khóa ngoại và cột nối.
- Ràng buộc UNIQUE có bảo đảm một-một hay không.
- Quan hệ có thể thiếu hàng con hay không.
- Truy vấn cần một hàng cho mỗi thực thể hay cần tất cả hàng chi tiết.
- Hàng không có quan hệ có cần được giữ lại không.

Các câu hỏi này quyết định dùng INNER JOIN, LEFT JOIN, EXISTS, phép tổng hợp hay một cách kết hợp khác. Nếu chọn sai kiểu nối, truy vấn có thể nhanh hơn nhưng trả về sai tập hàng.

## 3. Cardinality: số hàng ở từng bước nối

Cardinality là số hàng được tạo ra hoặc dự kiến tại một bước của kế hoạch. Bộ tối ưu cần ước lượng cardinality để chọn thứ tự nối, thuật toán nối và cách truy cập dữ liệu.

Với một phép nối bằng, số hàng kết quả phụ thuộc vào số hàng ở hai phía và phân bố giá trị khóa nối. Không thể chỉ lấy số hàng bảng A nhân số hàng bảng B rồi coi đó là kết quả; số khớp thực tế phụ thuộc vào khóa, độ trùng lặp và điều kiện lọc.

Ví dụ:

| Tập dữ liệu | Số hàng |
|---|---:|
| customers sau khi lọc khu vực | 20.000 |
| orders của các khách hàng đó | 180.000 |
| order_items của các đơn hàng đó | 720.000 |
| payments của các đơn hàng đó | 210.000 |

Nếu truy vấn cần danh sách chi tiết từng dòng hàng, 720.000 hàng order_items có thể là kết quả trung gian hợp lý. Nhưng nếu báo cáo chỉ cần tổng tiền theo đơn hàng, giữ toàn bộ 720.000 dòng đến cuối rồi mới GROUP BY có thể không cần thiết.

Hãy đọc số hàng ở từng toán tử trong EXPLAIN. Với công cụ hỗ trợ số liệu thực tế, so sánh estimated rows với actual rows. Sai lệch lớn ở bước đầu có thể làm các phép nối sau bị ước lượng sai và chọn kế hoạch không phù hợp.

### 3.1. Ước lượng sai lan truyền như thế nào?

Giả sử bộ tối ưu dự đoán một khách hàng có 2 đơn hàng, nhưng thực tế một khách hàng lớn có 20.000 đơn. Khi nối tiếp với order_items, số hàng thực tế có thể tăng mạnh hơn dự kiến. Một kế hoạch nested loop được chọn cho tập nhỏ có thể trở nên rất tốn kém khi đầu vào thực tế lớn.

Nguyên nhân sai lệch có thể gồm:

- Thống kê cũ hoặc lấy mẫu chưa đại diện.
- Phân bố khóa nối bị lệch.
- Các cột lọc có tương quan.
- Một số khách hàng hoặc tenant có quy mô khác biệt lớn.
- Điều kiện lọc và khóa nối không được mô tả đủ trong thống kê.
- Tham số truy vấn thay đổi giữa các lần thực thi.

Nếu actual rows lớn hơn estimated rows nhiều lần, hãy kiểm tra thống kê, phân bố khóa, tham số và vị trí đầu tiên xuất hiện sai lệch. Không nên chỉ nhìn toán tử cuối cùng vì nguyên nhân có thể bắt đầu từ một bộ lọc hoặc phép nối trước đó.

## 4. Lọc sớm để giảm đầu vào của phép nối

Predicate pushdown là việc đưa điều kiện lọc đến gần bảng nguồn nhất có thể, để loại bỏ hàng không cần thiết trước khi chúng đi qua các phép nối tiếp theo.

Ví dụ, báo cáo chỉ cần đơn hàng đã hoàn tất trong một khoảng thời gian:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region = :region
  AND o.status = 'COMPLETED'
  AND o.created_at >= :start_time
  AND o.created_at < :end_time;
~~~

Các điều kiện trên customers và orders có thể được áp dụng tại bước đọc từng bảng trước khi nối, nếu bộ tối ưu chứng minh phép biến đổi giữ nguyên ngữ nghĩa. Nhờ đó, chỉ các khách hàng trong khu vực cần thiết và các đơn hàng phù hợp mới đi vào phép nối.

Không cần viết lại truy vấn thành subquery chỉ để ép lọc sớm. Nhiều hệ quản trị tự đẩy điều kiện qua các phép nối phù hợp. Điều quan trọng là điều kiện rõ ràng, kiểu dữ liệu tương thích và kế hoạch cho thấy bộ lọc được áp dụng ở vị trí hiệu quả.

### 4.1. Đưa điều kiện vào ON hay WHERE?

Với INNER JOIN, điều kiện tương ứng đặt trong ON hoặc WHERE thường có thể được biến đổi tương đương. Nhưng với OUTER JOIN, vị trí điều kiện có thể làm thay đổi kết quả.

Ví dụ, muốn giữ tất cả khách hàng nhưng chỉ nối đơn hàng đã hoàn tất:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'COMPLETED';
~~~

Nếu chuyển điều kiện trạng thái xuống WHERE:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'COMPLETED';
~~~

Hàng khách hàng không có đơn hàng phù hợp sẽ có các cột orders là NULL và bị loại bởi điều kiện WHERE. Kết quả lúc này gần với INNER JOIN đối với điều kiện đó, không còn giữ tất cả khách hàng.

Vì vậy, không đẩy điều kiện qua OUTER JOIN chỉ để giảm hàng mà chưa kiểm tra ngữ nghĩa hàng không khớp.

## 5. Chọn thứ tự nối dựa trên tập dữ liệu và điều kiện lọc

Khi truy vấn nối nhiều bảng, bộ tối ưu có thể cân nhắc nhiều thứ tự kết hợp. Với INNER JOIN, nhiều thứ tự có thể tương đương về kết quả, nên hệ quản trị thường được phép sắp xếp lại để giảm cardinality trung gian và chi phí.

Một nguyên tắc thường hữu ích là bắt đầu từ tập dữ liệu được lọc mạnh nếu điều đó làm giảm đáng kể số hàng đầu vào. Tuy nhiên, không có quy tắc luôn bắt đầu từ bảng nhỏ nhất. Chi phí truy cập, chỉ mục, phân bố khóa, thứ tự cần thiết và thuật toán nối đều ảnh hưởng.

Ví dụ, truy vấn tìm đơn hàng của khách hàng tại một khu vực:

~~~sql
SELECT o.order_id, o.created_at, c.customer_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region = :region
  AND o.created_at >= :start_time
  AND o.created_at < :end_time;
~~~

Nếu region chỉ chọn ra 1% khách hàng và mỗi khách hàng có ít đơn trong khoảng đó, bắt đầu từ customers đã lọc rồi tìm orders có thể hiệu quả. Nếu khoảng thời gian chọn ra rất ít đơn trên toàn hệ thống, bắt đầu từ orders theo thời gian rồi nối customers có thể tốt hơn.

Hãy kiểm tra:

- Số hàng sau từng bộ lọc.
- Số hàng sau từng phép nối.
- Số lần lặp của toán tử.
- Khả năng tìm kiếm qua chỉ mục ở từng phía.
- Bộ nhớ và I/O của thuật toán nối.
- Khả năng loại bỏ phân vùng hoặc đọc dữ liệu theo thứ tự.

Không dựa vào thứ tự bảng được viết trong FROM để kết luận thứ tự thực thi. Kế hoạch thực thi mới cho biết hệ quản trị đã chọn thứ tự nào.

## 6. Hiểu các thuật toán nối

### 6.1. Nested loop join

Nested loop thường lấy từng hàng từ đầu vào bên ngoài rồi tìm hàng khớp ở đầu vào bên trong. Nếu đầu vào ngoài nhỏ và phía trong có chỉ mục trên khóa nối, đây có thể là phương án rất hiệu quả.

Ví dụ, lọc ra 100 khách hàng rồi tìm các đơn hàng theo customer_id qua chỉ mục có thể chỉ cần một số lần tìm kiếm nhỏ.

Nhưng nếu đầu vào ngoài có hàng triệu hàng và mỗi vòng lặp phải quét nhiều dữ liệu ở phía trong, chi phí có thể tăng mạnh. Khi đọc kế hoạch, hãy xem số vòng lặp, số hàng mỗi vòng và tổng số lần truy cập.

### 6.2. Hash join

Hash join thường xây dựng bảng băm từ một đầu vào rồi dò tìm các hàng khớp từ đầu vào còn lại. Nó phù hợp với nhiều phép nối bằng khi hai tập dữ liệu có kích thước đáng kể và không có thứ tự phù hợp sẵn.

Hash join cần bộ nhớ. Nếu tập dữ liệu xây dựng lớn hơn ngân sách bộ nhớ, hệ quản trị có thể chia partition hoặc ghi dữ liệu trung gian ra vùng tạm. Một truy vấn có thể nhanh ở tải thấp nhưng chậm khi nhiều hash join đồng thời cạnh tranh bộ nhớ.

### 6.3. Merge join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Nếu dữ liệu đã có thứ tự từ chỉ mục hoặc toán tử trước đó, merge join có thể tránh một phần chi phí sort. Nếu chưa có thứ tự, việc sắp xếp hai phía có thể tạo thêm CPU, bộ nhớ và I/O.

### 6.4. Không có thuật toán nối tốt nhất cho mọi truy vấn

Nested loop, hash join và merge join có điều kiện phù hợp khác nhau. Đừng kết luận hash join luôn nhanh hơn nested loop hoặc merge join luôn tiết kiệm nhất. Hãy so sánh cardinality, số vòng lặp, chi phí sort, bộ nhớ, spill và I/O trong kế hoạch thực tế.

## 7. Giảm fan-out khi nối nhiều quan hệ một-nhiều

Một trong những nguyên nhân phổ biến làm số hàng trung gian tăng mạnh là nối nhiều bảng con một-nhiều trong cùng một truy vấn.

Giả sử mỗi order có:

- 4 dòng order_items.
- 2 bản ghi payments.
- 3 bản ghi shipment_events.

Nối cả ba bảng con trực tiếp với orders có thể tạo 4 × 2 × 3 = 24 hàng cho một order, dù kết quả nghiệp vụ chỉ cần một dòng tổng hợp cho đơn hàng.

Ví dụ dễ gây sai tổng:

~~~sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
~~~

Nếu một order có 4 dòng hàng và 2 payment, phép nối tạo 8 hàng. Mỗi dòng hàng lặp lại hai lần, mỗi payment lặp lại bốn lần. Cả item_total và paid_total đều có thể bị nhân lên.

Không nên chữa lỗi này bằng cách dùng SUM(DISTINCT amount) hoặc SELECT DISTINCT một cách máy móc. Hai payment khác nhau có thể có cùng amount; DISTINCT sẽ loại mất một khoản thanh toán hợp lệ. Phải sửa cấu trúc phép tổng hợp để mỗi quan hệ được tính ở đúng cấp dữ liệu.

## 8. Tổng hợp trước khi nối (pre-aggregation)

Nếu kết quả cuối cần một hàng cho mỗi order, hãy tổng hợp từng bảng con về đúng cấp order trước khi nối chúng với nhau.

Ví dụ:

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
    WHERE status = 'SETTLED'
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
  ON p.order_id = o.order_id
WHERE o.created_at >= :start_time
  AND o.created_at < :end_time;
~~~

Ở đây, item_totals có tối đa một hàng cho mỗi order_id; payment_totals cũng có tối đa một hàng cho mỗi order_id. Khi nối với orders, hai quan hệ con không nhân chéo số hàng với nhau.

Cần xem xét hiệu quả lọc trước khi tổng hợp. Nếu chỉ báo cáo một nhóm order trong một khoảng thời gian, có thể lọc tập order cần thiết trước rồi chỉ tổng hợp các dòng con thuộc các order đó. Cách viết cụ thể tùy hệ quản trị và bộ tối ưu; có thể dùng CTE, derived table, subquery hoặc join với tập khóa đã lọc.

Pre-aggregation không phải lúc nào cũng giảm chi phí. Nếu cần mọi dòng chi tiết ở kết quả cuối, tổng hợp trước sẽ làm mất thông tin. Nếu chỉ một tỷ lệ nhỏ bảng cha được chọn, tổng hợp toàn bộ bảng con rồi mới nối có thể đọc nhiều dữ liệu không cần thiết. Hãy so sánh số hàng đầu vào và kế hoạch thực thi.

### 8.1. Bảo toàn cấp dữ liệu (grain)

Grain là mức chi tiết mà mỗi hàng đại diện. Ví dụ:

- orders: một hàng cho mỗi order.
- order_items: một hàng cho mỗi dòng hàng.
- payments: một hàng cho mỗi giao dịch thanh toán.
- item_totals: một hàng cho mỗi order sau khi tổng hợp dòng hàng.
- payment_totals: một hàng cho mỗi order sau khi tổng hợp thanh toán.

Trước khi nối, hãy xác định grain của từng tập dữ liệu. Hai tập dữ liệu chỉ có thể nối mà không làm tăng số hàng ngoài dự kiến nếu khóa nối và tính duy nhất phù hợp với grain đó.

Nếu một bảng được kỳ vọng có một hàng cho mỗi order nhưng dữ liệu thực tế có nhiều hàng, hãy kiểm tra constraint, dữ liệu trùng và logic tổng hợp. Đừng dựa trên giả định nghiệp vụ mà không xác nhận bằng khóa và dữ liệu.

## 9. Dùng EXISTS hoặc semi join khi chỉ cần kiểm tra sự tồn tại

Nếu truy vấn chỉ cần biết một khách hàng có đơn hàng hay không, nối trực tiếp customers với orders có thể trả về nhiều hàng cho một khách hàng. Nếu kết quả chỉ cần mỗi khách hàng một lần, EXISTS biểu đạt ý định rõ hơn:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'COMPLETED'
);
~~~

EXISTS chỉ kiểm tra có ít nhất một hàng phù hợp. Bộ tối ưu có thể thực hiện bằng semi join hoặc một toán tử tương đương, và có thể dừng tìm kiếm khi tìm thấy hàng phù hợp.

Nếu cần khách hàng không có đơn hàng, dùng NOT EXISTS:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Không thay EXISTS bằng JOIN rồi SELECT DISTINCT chỉ vì muốn loại hàng trùng nếu ý định thực sự chỉ là kiểm tra sự tồn tại. EXISTS thể hiện ngữ nghĩa trực tiếp và tránh tạo hàng con không cần thiết.

Cần thận trọng khi thay NOT IN bằng NOT EXISTS. Nếu tập con chứa NULL, NOT IN có thể có kết quả theo logic ba giá trị khác với cách kiểm tra không tồn tại. Hãy kiểm tra nullability và ngữ nghĩa mong muốn.

## 10. Giảm số hàng và độ rộng hàng trung gian

Số hàng không phải yếu tố duy nhất. Mỗi hàng trung gian càng rộng thì càng tốn bộ nhớ và băng thông giữa các toán tử.

Một số cách giảm công việc:

- Chỉ chọn cột cần thiết thay vì lấy toàn bộ cột.
- Đẩy điều kiện lọc xuống gần bảng nguồn khi hợp lệ.
- Loại bỏ phép nối không cần thiết nếu ràng buộc và ngữ nghĩa chứng minh có thể bỏ.
- Tổng hợp sớm khi kết quả cuối cần grain tổng hợp.
- Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại.
- Tránh tạo nhiều bản sao dữ liệu trung gian do quan hệ một-nhiều.
- Tránh sort hoặc DISTINCT không cần thiết.

Ví dụ, nếu chỉ cần customer_id và order_id, không nên kéo các cột JSON lớn, ghi chú dài hoặc payload nhị phân qua nhiều bước JOIN rồi mới loại bỏ. Projection pruning có thể được optimizer tự thực hiện, nhưng SQL rõ ràng vẫn giúp người đọc hiểu dữ liệu thực sự cần.

Không được loại cột hoặc phép nối nếu chúng ảnh hưởng đến kết quả, điều kiện lọc, thứ tự hoặc tính duy nhất. Mọi thay đổi phải được xác nhận bằng kiểm tra tương đương.

## 11. Chỉ mục hỗ trợ phép nối nhiều bảng

Chỉ mục có thể giúp tìm hàng khớp ở phía trong của nested loop, lọc bảng trước khi nối hoặc cung cấp thứ tự cho merge join. Nhưng không phải phép nối nào cũng cần chỉ mục ở cả hai phía.

Các câu hỏi cần kiểm tra:

- Cột khóa nối có chỉ mục hoặc constraint phù hợp không?
- Có điều kiện lọc trên bảng nào trước khi nối?
- Phía trong nested loop có cần tìm kiếm lặp theo khóa không?
- Bảng có nhỏ đến mức sequential scan rẻ hơn không?
- Hash join có thể quét hai đầu vào hiệu quả không?
- Thứ tự cột của chỉ mục nhiều cột có phù hợp với điều kiện lọc và nối không?
- Thống kê có mô tả đúng số hàng và phân bố khóa không?

Ví dụ, nếu truy vấn lọc orders theo tenant_id và status rồi nối customers bằng customer_id, một chỉ mục trên orders có thể cần cân nhắc theo mẫu truy vấn. Bảng customers thường có chỉ mục duy nhất trên customer_id nếu đó là khóa chính.

Một chỉ mục ở phía bảng con có thể giúp kiểm tra hoặc tìm các hàng liên quan. Tuy nhiên, nếu truy vấn cần phần lớn hàng của bảng con, quét tuần tự và hash join có thể rẻ hơn nhiều lần lookup.

Không tạo chỉ mục chỉ vì cột xuất hiện trong ON. Hãy xem kế hoạch, số hàng thực tế và workload đọc/ghi.

## 12. OUTER JOIN và việc giữ hàng không khớp

LEFT JOIN giữ tất cả hàng ở phía trái, kể cả khi không có hàng phù hợp ở phía phải. Các cột phía phải được điền NULL cho hàng không khớp. RIGHT JOIN và FULL OUTER JOIN có quy tắc tương tự theo phía được giữ.

Khi tối ưu, hãy kiểm tra:

- Có cần giữ hàng cha không có hàng con không?
- Điều kiện trên bảng phải nằm trong ON hay WHERE?
- Có điều kiện nào vô tình loại hàng NULL-extended?
- Có thể chuyển outer join thành inner join theo ràng buộc và điều kiện không?
- Việc lọc trước bảng con có giữ nguyên hàng cha không khớp không?

Ví dụ, nếu muốn tất cả khách hàng và số đơn hàng đã hoàn tất, có thể tổng hợp orders trước rồi LEFT JOIN kết quả tổng hợp:

~~~sql
WITH completed_order_counts AS (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE status = 'COMPLETED'
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    COALESCE(x.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN completed_order_counts AS x
  ON x.customer_id = c.customer_id;
~~~

Cách này giữ khách hàng không có đơn hoàn tất và tránh nối từng đơn hàng vào kết quả cuối. Nếu cần lọc khách hàng theo điều kiện khác, hãy đặt điều kiện đúng vị trí và xác nhận số hàng đầu ra.

## 13. DISTINCT và GROUP BY không phải thuốc chữa fan-out

DISTINCT loại bỏ các hàng trùng theo toàn bộ danh sách cột được chọn. GROUP BY gom hàng theo các khóa nhóm. Hai thao tác có mục đích riêng, không nên thêm vào chỉ để che kết quả bị nhân do nối sai cấp dữ liệu.

Ví dụ, nếu một đơn hàng có nhiều payment và nhiều item, DISTINCT có thể loại một số hàng giống hệt nhau nhưng không khôi phục được tổng tiền chính xác. Nếu hai payment có cùng số tiền, SUM(DISTINCT amount) có thể bỏ mất một payment hợp lệ.

Khi thấy phải thêm DISTINCT sau một chuỗi JOIN để kết quả “đúng số hàng”, hãy kiểm tra:

- Quan hệ một-nhiều nào đang tạo fan-out?
- Có thực sự cần mọi hàng chi tiết không?
- Có thể dùng EXISTS nếu chỉ cần kiểm tra sự tồn tại không?
- Có cần tổng hợp từng bảng con trước khi nối không?
- Khóa nối có thiếu một phần không?
- Dữ liệu có vi phạm uniqueness mà truy vấn đang giả định không?

Nếu DISTINCT là yêu cầu nghiệp vụ thực sự, hãy giữ nó. Nhưng phải hiểu chi phí sort/hash để loại trùng và bảo đảm nó biểu đạt đúng kết quả cần có.

## 14. Đọc kế hoạch thực thi của truy vấn nhiều phép nối

EXPLAIN hoặc công cụ tương đương cho biết thứ tự nối và toán tử mà hệ quản trị chọn. Khi đọc kế hoạch, tập trung vào:

1. Số hàng đầu vào của từng bảng sau lọc.
2. Số hàng ước lượng và số hàng thực tế tại mỗi phép nối.
3. Thuật toán nối: nested loop, hash join, merge join hoặc biến thể.
4. Số vòng lặp của nested loop và lượng dữ liệu mỗi vòng.
5. Kích thước hash table, sort và dữ liệu tràn ra vùng tạm.
6. Điều kiện nối và điều kiện lọc được áp dụng ở đâu.
7. Chỉ mục và kiểu scan được dùng.
8. Số hàng cuối so với số hàng trung gian.
9. Thời gian, CPU, I/O và wait events nếu công cụ cung cấp.

Ví dụ lệnh tổng quát:

~~~sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE c.region = 'NORTH'
  AND o.status = 'COMPLETED';
~~~

Một số hệ quản trị hỗ trợ EXPLAIN ANALYZE hoặc chế độ thực thi thực tế. Hãy đọc tài liệu trước khi chạy vì chế độ phân tích có thể thực thi câu lệnh. Với INSERT, UPDATE hoặc DELETE, cần đánh giá khả năng thay đổi dữ liệu và dùng môi trường hoặc cơ chế giao dịch an toàn.

Đừng chỉ nhìn cost tổng. Cost thường là đơn vị nội bộ tương đối; hãy tìm nơi cardinality bắt đầu lệch, toán tử đọc nhiều dữ liệu, số vòng lặp bất thường hoặc spill ra đĩa.

## 15. Kiểm chứng kết quả sau khi viết lại truy vấn

Tối ưu truy vấn nối nhiều bảng phải chứng minh hai điều: kết quả không đổi và workload thực tế tốt hơn.

### 15.1. Kiểm tra tương đương kết quả

Dùng cùng một snapshot dữ liệu hoặc một bộ dữ liệu không thay đổi trong lúc so sánh. Kiểm tra:

- Số hàng tổng thể.
- Số hàng theo khóa nghiệp vụ.
- Tổng, đếm, min/max và các phép tổng hợp quan trọng.
- Hàng không có quan hệ con.
- Hàng có nhiều quan hệ con.
- Khóa trùng hoặc NULL ở cột nối.
- Trường hợp nhiều bảng con cùng có nhiều hàng.
- Điều kiện biên của thời gian và trạng thái.

Có thể dùng EXCEPT, MINUS hoặc phép so sánh tương đương tùy hệ quản trị để tìm hàng có trong kết quả này nhưng không có trong kết quả kia. Nếu thứ tự là một phần hợp đồng đầu ra, cần kiểm tra ORDER BY rõ ràng; SQL không bảo đảm thứ tự nếu không có ORDER BY.

### 15.2. Tạo dữ liệu kiểm thử có fan-out

Một bộ dữ liệu kiểm tra nên có:

- Đơn hàng không có dòng hàng.
- Đơn hàng có một dòng hàng.
- Đơn hàng có nhiều dòng hàng.
- Đơn hàng có nhiều payment.
- Đơn hàng có cả nhiều item và nhiều payment.
- Khách hàng không có đơn hàng.
- Hai payment khác nhau nhưng có cùng amount.
- Hàng con có trạng thái bị loại bởi điều kiện.

Những trường hợp này giúp phát hiện lỗi nhân tổng, mất hàng do INNER JOIN hoặc sai kết quả do DISTINCT.

### 15.3. Đo hiệu năng dưới tải đại diện

So sánh trước và sau với cùng dữ liệu, tham số và mức đồng thời:

- p50, p95, p99.
- Thông lượng và tỷ lệ timeout.
- Số hàng và trang đọc.
- CPU, I/O và bộ nhớ.
- Hash/sort spill.
- Lock wait và các wait event.
- Chi phí ghi nếu có thay đổi chỉ mục.

Không kết luận từ một lần chạy đơn lẻ. Cache nóng/lạnh, tải nền và kế hoạch cache có thể làm kết quả dao động. Đo nhiều lần và dùng workload đại diện, bao gồm các tham số có cardinality khác nhau.

## 16. Ví dụ xuyên suốt: báo cáo đơn hàng không nhân tổng tiền

Giả sử cần báo cáo mỗi đơn hàng của một nhóm khách hàng, gồm tên khách hàng, tổng giá trị dòng hàng và tổng tiền đã thanh toán. Bảng order_items và payments đều có quan hệ một-nhiều với orders.

### Cách nối trực tiếp gây fan-out

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
WHERE c.region = :region
GROUP BY o.order_id, c.customer_name;
~~~

Nếu một đơn có 3 dòng hàng và 2 payment, phép nối tạo 6 hàng. Tổng item_total bị nhân hai lần; paid_total bị nhân ba lần. Truy vấn có thể chạy xong nhưng số liệu nghiệp vụ sai.

### Cách tổng hợp từng bảng con

~~~sql
WITH selected_orders AS (
    SELECT
        o.order_id,
        o.customer_id
    FROM orders AS o
    JOIN customers AS c
      ON c.customer_id = o.customer_id
    WHERE c.region = :region
      AND o.created_at >= :start_time
      AND o.created_at < :end_time
),
item_totals AS (
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price) AS item_total
    FROM order_items AS oi
    JOIN selected_orders AS so
      ON so.order_id = oi.order_id
    GROUP BY oi.order_id
),
payment_totals AS (
    SELECT
        p.order_id,
        SUM(p.amount) AS paid_total
    FROM payments AS p
    JOIN selected_orders AS so
      ON so.order_id = p.order_id
    WHERE p.status = 'SETTLED'
    GROUP BY p.order_id
)
SELECT
    so.order_id,
    c.customer_name,
    COALESCE(i.item_total, 0) AS item_total,
    COALESCE(p.paid_total, 0) AS paid_total
FROM selected_orders AS so
JOIN customers AS c
  ON c.customer_id = so.customer_id
LEFT JOIN item_totals AS i
  ON i.order_id = so.order_id
LEFT JOIN payment_totals AS p
  ON p.order_id = so.order_id;
~~~

Trong truy vấn này, selected_orders xác định tập đơn cần báo cáo. item_totals và payment_totals đều có tối đa một hàng cho mỗi order_id. Khi nối các kết quả tổng hợp, mỗi đơn hàng vẫn tạo tối đa một hàng.

Đây là cách tổ chức ngữ nghĩa để tránh nhân chéo. Bộ tối ưu có thể inline CTE hoặc chọn cách thực hiện khác tùy hệ quản trị. Hãy đọc kế hoạch để xem selected_orders có bị tính lại không, bảng con được lọc như thế nào và số hàng trung gian có giảm không. Nếu selected_orders lớn, việc dùng CTE không bảo đảm materialize hay tối ưu hơn; cần đo.

### Kiểm tra kết quả

Chọn một số order có nhiều item và nhiều payment. Tính tổng item và payment riêng bằng truy vấn độc lập, sau đó so sánh với báo cáo. Xác nhận payment chỉ tính trạng thái SETTLED theo đúng quy tắc nghiệp vụ, đơn không có item/payment được xử lý theo yêu cầu và không có đơn bị mất ngoài ý muốn.

Sau đó so sánh kế hoạch và thời gian dưới nhiều vùng khách hàng, khoảng thời gian và mức tải. Một truy vấn đúng nhưng đọc toàn bộ order_items và payments cho mỗi lần gọi có thể vẫn cần cải thiện bằng cách lọc selected_orders sớm, chỉ mục phù hợp hoặc tổng hợp vật hóa nếu workload chứng minh cần thiết.

## 17. Các sai lầm thường gặp

- **Nối tất cả bảng con rồi mới tổng hợp.** Nhiều quan hệ một-nhiều có thể nhân chéo hàng và làm sai SUM/COUNT.
- **Dùng DISTINCT để chữa fan-out.** DISTINCT không khôi phục đúng tổng và có thể loại mất các khoản hợp lệ có giá trị giống nhau.
- **Luôn bắt đầu từ bảng nhỏ nhất.** Bảng nhỏ hơn không nhất thiết có đường truy cập rẻ hơn hoặc tạo kế hoạch tốt hơn.
- **Cho rằng thứ tự viết JOIN là thứ tự thực thi.** Bộ tối ưu có thể sắp xếp lại các inner join.
- **Đẩy mọi điều kiện vào WHERE.** Với LEFT JOIN, điều kiện phía phải trong WHERE có thể loại hàng không khớp.
- **Tổng hợp trước mà không lọc phạm vi.** Có thể đọc và nhóm toàn bộ bảng con dù chỉ cần một phần nhỏ.
- **Chọn thuật toán nối theo mẹo.** Nested loop, hash và merge có điều kiện phù hợp khác nhau.
- **Bỏ qua cardinality estimate.** Sai lệch ước lượng có thể làm kế hoạch nối kém.
- **Thêm chỉ mục cho mọi cột JOIN.** Chỉ mục cần được đánh giá cùng số hàng, kiểu nối và chi phí ghi.
- **Chỉ kiểm tra tốc độ.** Truy vấn nhanh nhưng nhân tổng hoặc làm mất hàng là sai.
- **Chỉ thử dữ liệu đơn giản.** Dữ liệu ít hàng con không bộc lộ fan-out và sai lệch tổng hợp.

## 18. Checklist tối ưu truy vấn nối nhiều bảng

- [ ] Đã xác định grain và bội số quan hệ của từng bảng.
- [ ] Đã xác nhận khóa chính, khóa ngoại và tính duy nhất của khóa nối.
- [ ] Đã xác định số hàng sau từng bộ lọc và từng phép nối.
- [ ] Đã kiểm tra estimated rows so với actual rows.
- [ ] Đã lọc sớm khi phép biến đổi giữ nguyên ngữ nghĩa.
- [ ] Đã kiểm tra vị trí ON/WHERE đối với OUTER JOIN.
- [ ] Đã nhận diện fan-out từ nhiều quan hệ một-nhiều.
- [ ] Đã tổng hợp từng bảng con trước khi nối nếu kết quả cần grain tổng hợp.
- [ ] Đã dùng EXISTS/NOT EXISTS khi chỉ cần kiểm tra tồn tại và đã xét NULL.
- [ ] Đã giảm số cột và độ rộng hàng trung gian khi phù hợp.
- [ ] Đã đọc thuật toán nối, số vòng lặp, memory grant và spill.
- [ ] Đã đánh giá chỉ mục và thống kê trên các cột lọc/nối.
- [ ] Đã kiểm tra kết quả trên dữ liệu có nhiều hàng con, NULL và không có quan hệ.
- [ ] Đã so sánh p50/p95/p99, CPU, I/O, bộ nhớ và timeout.
- [ ] Đã ghi lại kế hoạch và bằng chứng trước/sau điều chỉnh.

## 19. Nguyên tắc cần ghi nhớ

Tối ưu truy vấn nối nhiều bảng bắt đầu bằng việc hiểu grain, khóa và bội số quan hệ. Cardinality ở mỗi bước quyết định lượng dữ liệu trung gian mà hệ quản trị phải xử lý. Lọc sớm, chọn thứ tự nối phù hợp, dùng thuật toán nối đúng với kích thước đầu vào, giảm độ rộng hàng và tổng hợp bảng con trước khi nối có thể giảm đáng kể công việc.

Mỗi phép biến đổi phải giữ nguyên ngữ nghĩa INNER/OUTER JOIN, NULL, số lần xuất hiện của hàng và các phép tổng hợp. Hãy đọc kế hoạch, so sánh số hàng ước lượng với thực tế, kiểm tra dữ liệu có fan-out và đối chiếu kết quả trước/sau. Một truy vấn chỉ thực sự được tối ưu khi vừa giảm chi phí thực thi trên workload đại diện vừa trả về đúng dữ liệu nghiệp vụ.
