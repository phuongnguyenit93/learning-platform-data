# Không gian tìm kiếm thứ tự nối và ảnh hưởng của nhiều bảng

Khi một câu SQL kết hợp nhiều bảng, hệ quản trị phải quyết định không chỉ cách đọc từng bảng mà còn thứ tự kết hợp các tập dòng. Cùng một kết quả logic có thể được tạo ra bằng nhiều thứ tự nối (join order) và nhiều cấu trúc cây nối (join tree). Những phương án tương đương về kết quả có thể khác nhau rất lớn về số dòng trung gian, lượng dữ liệu phải đọc, bộ nhớ cần dùng và thời gian hoàn thành.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, thống kê, kế hoạch thực thi và cơ chế truy cập dữ liệu. Khi truy vấn liên quan nhiều bảng, hiểu không gian tìm kiếm của bộ tối ưu (query optimizer) giúp giải thích vì sao một thứ tự nối nhanh hơn thứ tự khác, vì sao sai lệch ước lượng số dòng có thể làm kế hoạch kém hiệu quả, và khi nào cần xem lại SQL, chỉ mục hoặc thống kê.

Bài học này trình bày cách hình thành không gian tìm kiếm join, cách bộ tối ưu đánh giá thứ tự nối, ảnh hưởng của số lượng bảng và các loại quan hệ, cùng phương pháp đọc execution plan và kiểm chứng lựa chọn tối ưu.

## 1. Thứ tự nối là gì?

Phép nối kết hợp các dòng từ hai quan hệ dựa trên điều kiện nối. Với hai bảng, ví dụ:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Hệ quản trị có thể đọc customers trước rồi tìm các dòng orders tương ứng, hoặc đọc orders trước rồi tra cứu customers. Tùy dữ liệu, chỉ mục, số dòng và phương pháp nối, một hướng có thể rẻ hơn hướng còn lại.

Khi có ba bảng trở lên, số lựa chọn tăng nhanh. Ví dụ:

~~~sql
SELECT c.customer_name, o.order_id, p.product_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE c.region = 'NORTH'
  AND o.created_at >= DATE '2026-01-01';
~~~

Các bảng có thể được kết hợp theo nhiều thứ tự hợp lệ, chẳng hạn:

- Lọc customers trước, nối orders, rồi order_items và products.
- Lọc orders theo ngày trước, nối customers, rồi order_items và products.
- Nối orders với order_items trước, sau đó mới kết hợp customers và products.
- Nối order_items với products trước rồi ghép kết quả với orders và customers.

Các phương án có thể cho kết quả logic giống nhau đối với inner join, nhưng kích thước dữ liệu trung gian có thể khác nhau rất nhiều. Nếu một nhánh sớm giảm tập dữ liệu từ hàng triệu dòng xuống vài trăm dòng, các phép nối phía sau có thể xử lý ít dữ liệu hơn.

## 2. Không gian tìm kiếm của join order

Không gian tìm kiếm là tập hợp các thứ tự và cấu trúc nối mà bộ tối ưu xem xét khi xây dựng kế hoạch thực thi.

### Hoán đổi và kết hợp phép nối

Với inner join, trong điều kiện phù hợp, phép nối có tính giao hoán:

\[
A \Join B \equiv B \Join A
\]

và tính kết hợp:

\[
(A \Join B) \Join C \equiv A \Join (B \Join C)
\]

Điều đó cho phép optimizer thay đổi thứ tự nối mà vẫn giữ nguyên kết quả. Ví dụ, với các điều kiện nối tương ứng:

~~~sql
(A JOIN B ON A.id = B.a_id)
JOIN C ON B.c_id = C.id
~~~

có thể được biểu diễn lại thành:

~~~sql
A JOIN (B JOIN C ON B.c_id = C.id)
  ON A.id = B.a_id
~~~

Tính tương đương này áp dụng cho các phép nối inner join trong điều kiện ngữ nghĩa phù hợp. Không thể tùy ý hoán đổi mọi loại join trong mọi truy vấn.

### Join tree

Một kế hoạch nối thường được biểu diễn như một cây nhị phân. Mỗi nút trong là phép nối hai đầu vào; đầu vào có thể là bảng gốc hoặc kết quả của một phép nối trước đó.

Với ba quan hệ A, B và C, một số cấu trúc có thể là:

~~~text
Left-deep:
        JOIN
       /    \
     JOIN    C
    /   \
   A     B

Right-deep:
        JOIN
       /    \
      A     JOIN
           /    \
          B      C

Bushy:
        JOIN
       /    \
     JOIN  JOIN
    /  \   /  \
   A    B C    D
~~~

- **Left-deep tree:** đầu vào bên phải thường là một bảng hoặc quan hệ đơn, còn đầu vào bên trái là kết quả nối trước đó. Cấu trúc này dễ kết hợp với nhiều chiến lược truy cập và thường được nhiều optimizer ưu tiên trong quá trình tìm kiếm.
- **Right-deep tree:** có nhánh phải tiếp tục là một phép nối. Tùy engine và phương pháp thực thi, cấu trúc này có thể hỗ trợ pipeline hoặc hash join theo cách khác.
- **Bushy tree:** cả hai nhánh của một phép nối đều có thể là kết quả của những phép nối con. Cấu trúc này mở rộng lựa chọn, cho phép xây dựng hai nhánh độc lập trước khi kết hợp.

Không phải mọi hệ quản trị đều xét đầy đủ mọi cây. Việc giới hạn không gian tìm kiếm giúp kiểm soát thời gian lập kế hoạch và bộ nhớ của optimizer.

### Số lượng phương án tăng nhanh

Nếu chỉ xét thứ tự tuyến tính của n bảng, số hoán vị có thể lên tới n! trước khi loại các phương án tương đương hoặc không hợp lệ. Với 5 bảng có 120 thứ tự; với 10 bảng có 3.628.800 thứ tự. Nếu xét cả các cấu trúc cây bushy, số cấu trúc còn tăng nhanh hơn.

Trong thực tế, optimizer không nhất thiết duyệt mọi hoán vị. Nó dùng thông tin điều kiện nối, thống kê, giới hạn cấu trúc, quy tắc cắt tỉa và thuật toán tìm kiếm để tập trung vào những phương án có triển vọng. Tuy nhiên, truy vấn kết hợp rất nhiều bảng vẫn có thể làm thời gian lập kế hoạch tăng hoặc khiến optimizer phải dùng phương pháp tìm kiếm gần đúng.

## 3. Join graph mô tả quan hệ giữa các bảng

Có thể biểu diễn truy vấn nhiều bảng bằng đồ thị nối (join graph):

- Mỗi đỉnh là một bảng hoặc quan hệ đầu vào.
- Mỗi cạnh biểu diễn điều kiện nối giữa hai quan hệ.
- Điều kiện lọc trên một bảng là thông tin giúp thu hẹp đỉnh đó.
- Điều kiện nối nhiều bảng hoặc biểu thức phức tạp có thể tạo quan hệ phụ thuộc rộng hơn.

Ví dụ truy vấn customers, orders, order_items và products tạo thành một chuỗi:

~~~text
customers -- orders -- order_items -- products
                 |
              payments
~~~

Đồ thị giúp nhận biết các bảng có quan hệ trực tiếp và nơi có thể áp dụng điều kiện lọc. Nếu truy vấn thiếu điều kiện nối giữa hai bảng, nó có thể tạo tích Descartes (Cartesian product), làm số dòng trung gian tăng đột biến.

### Điều kiện nối và điều kiện lọc

Phân biệt hai loại điều kiện:

- **Join predicate:** xác định cách các dòng của hai quan hệ liên kết, ví dụ orders.customer_id = customers.customer_id.
- **Filter predicate:** loại bỏ các dòng không cần thiết, ví dụ customers.region = 'NORTH'.

Điều kiện lọc có thể được đẩy xuống gần bảng nguồn (predicate pushdown) khi ngữ nghĩa cho phép. Thu hẹp tập dữ liệu trước khi nối thường giảm số dòng trung gian. Tuy nhiên, việc đẩy điều kiện qua outer join, subquery, aggregation hoặc biểu thức có tác dụng phụ cần tuân thủ quy tắc ngữ nghĩa của SQL.

## 4. Vì sao thứ tự nối ảnh hưởng lớn đến chi phí?

Chi phí của một phép nối phụ thuộc vào:

- Số dòng đầu vào của hai nhánh.
- Độ rộng mỗi dòng và lượng dữ liệu phải giữ trong bộ nhớ.
- Số dòng đầu ra ước lượng.
- Điều kiện nối và độ chọn lọc của từng nhánh.
- Chỉ mục sẵn có và khả năng truy cập dữ liệu.
- Thuật toán nối được chọn.
- Bộ nhớ cấp phát, khả năng tràn ra đĩa và mức đồng thời.
- Chi phí khởi tạo so với chi phí xử lý toàn bộ kết quả.

Một thứ tự nối có thể tạo ra tập trung gian rất lớn. Nếu optimizer kết hợp hai bảng lớn trước khi áp dụng điều kiện lọc chọn lọc, nó có thể phải xử lý hàng triệu dòng mà kết quả cuối cùng chỉ cần vài trăm dòng.

### Ví dụ số dòng trung gian

Giả sử có:

| Quan hệ | Số dòng ban đầu | Điều kiện lọc | Dòng còn lại ước lượng |
|---|---:|---|---:|
| customers | 2.000.000 | region = 'NORTH' | 20.000 |
| orders | 30.000.000 | created_at trong năm hiện tại | 600.000 |
| order_items | 90.000.000 | Chưa lọc | 90.000.000 |
| products | 500.000 | category = 'ELECTRONICS' | 15.000 |

Nếu lọc customers và products sớm, rồi nối theo quan hệ khóa ngoại và tiếp tục lọc orders, optimizer có thể giảm số dòng cần mang qua các bước tiếp theo. Nếu nối orders với order_items trước mà chưa tận dụng điều kiện ngày, nó có thể tạo ra một tập trung gian lớn.

Đây chỉ là minh họa về quy mô. Số dòng thực tế của phép nối còn phụ thuộc tính duy nhất của khóa, số dòng khớp, NULL, phân bố dữ liệu và tương quan giữa các cột. Không thể nhân số dòng hai bảng một cách máy móc mà bỏ qua điều kiện nối.

## 5. Cardinality estimation quyết định chất lượng tìm kiếm

Cardinality là số dòng mà một quan hệ hoặc một nút trong kế hoạch được ước lượng sẽ tạo ra. Optimizer sử dụng ước lượng này để đánh giá chi phí các phương án.

Với một inner join A và B, một mô hình ước lượng đơn giản có thể dựa trên:

\[
|A \Join B| \approx |A| \times |B| \times s
\]

trong đó s là hệ số chọn lọc của điều kiện nối. Công thức này chỉ minh họa cách số dòng đầu vào và độ chọn lọc ảnh hưởng đến kết quả; hệ quản trị có thể dùng thống kê chi tiết hơn như số giá trị khác nhau, histogram, ràng buộc duy nhất và khóa ngoại.

### Sai lệch ước lượng lan truyền qua cây nối

Nếu optimizer ước lượng nhánh A chỉ có 100 dòng nhưng thực tế có 500.000 dòng, một nested loop có thể bị đánh giá rẻ hơn thực tế. Khi nhánh đó được nối tiếp với C và D, sai lệch có thể lan truyền, làm optimizer chọn thứ tự tiếp theo không phù hợp.

Ngược lại, nếu optimizer ước lượng một nhánh có hàng triệu dòng trong khi thực tế chỉ có vài trăm, nó có thể chọn hash join hoặc quét dữ liệu rộng dù một index lookup đơn giản có thể đủ.

Các nguyên nhân thường gặp:

- Thống kê đã cũ sau khi dữ liệu tăng hoặc thay đổi mạnh.
- Phân bố dữ liệu lệch, một số giá trị phổ biến hơn nhiều.
- Điều kiện lọc trên nhiều cột có tương quan.
- Biểu thức, hàm hoặc ép kiểu làm giảm khả năng ước lượng.
- Thiếu ràng buộc primary key, unique hoặc foreign key mà optimizer có thể tận dụng.
- Thống kê theo từng cột không mô tả đủ quan hệ giữa nhiều cột.
- Tham số thực tế khác xa giá trị dùng khi lập kế hoạch.

### Đọc estimated rows và actual rows

Khi xem execution plan có số liệu thực tế, hãy tìm node đầu tiên có sai lệch lớn giữa estimated rows và actual rows. Sau đó kiểm tra:

1. Thống kê của bảng và cột liên quan.
2. Tần suất giá trị phổ biến và độ lệch dữ liệu.
3. Tương quan giữa các điều kiện lọc.
4. Số dòng sau mỗi phép nối.
5. Số vòng lặp (loops) của node.
6. Lượng buffer đọc và dữ liệu trung gian.

Nếu node đầu tiên đã ước lượng sai, các node phía sau có thể chỉ đang phản ánh hệ quả của sai lệch ban đầu. Cải thiện thống kê hoặc viết lại điều kiện ở vị trí đó có thể giúp toàn bộ kế hoạch.

## 6. Ba thuật toán join phổ biến và quan hệ với join order

Thứ tự nối và thuật toán nối liên quan chặt chẽ với nhau. Một thứ tự phù hợp cho nested loop chưa chắc phù hợp cho hash join hoặc merge join.

### Nested loop join

Nested loop lặp qua các dòng của đầu vào ngoài, rồi tìm dòng tương ứng ở đầu vào trong.

Chi phí khái quát phụ thuộc số dòng của đầu vào ngoài nhân với chi phí tìm kiếm ở đầu vào trong. Nếu đầu vào ngoài nhỏ và đầu vào trong có chỉ mục trên cột nối, nested loop có thể rất hiệu quả.

Ví dụ, lọc một khách hàng cụ thể rồi tra cứu đơn hàng theo customer_id có thể tạo một tập nhỏ trước khi thực hiện các lần index lookup.

Nếu đầu vào ngoài có hàng triệu dòng và đầu vào trong phải quét lại nhiều lần, nested loop có thể rất đắt. Khi đọc plan, xem actual rows, loops và thời gian của node bên trong.

### Hash join

Hash join thường xây dựng bảng băm từ một đầu vào (build side), rồi quét đầu vào còn lại (probe side) để tìm các dòng khớp.

Hash join phù hợp với nhiều phép nối bằng giữa các tập dữ liệu lớn khi không có thứ tự sẵn và bộ nhớ đủ cho bảng băm. Optimizer cần chọn phía build hợp lý; nếu ước lượng sai kích thước, hash table có thể lớn hơn dự kiến và tràn ra vùng nhớ tạm.

Khi đọc plan, chú ý:

- Số dòng và độ rộng của build side.
- Bộ nhớ được cấp phát.
- Số batch của hash join.
- Temp read/write hoặc spill.
- Thời gian tạo hash table và probe.

Nếu nhánh được chọn làm build side lớn hơn dự kiến, hiệu năng có thể giảm mạnh.

### Merge join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Nếu dữ liệu đã có thứ tự phù hợp từ chỉ mục hoặc từ bước trước, merge join có thể tránh chi phí sort. Nếu chưa có thứ tự, hệ quản trị có thể phải sắp xếp một hoặc cả hai đầu vào.

Merge join có thể phù hợp với tập dữ liệu lớn, đặc biệt khi hai đầu vào đã có thứ tự tương thích. Chi phí sort và bộ nhớ cần được tính vào tổng kế hoạch.

### So sánh khái quát

| Thuật toán | Thường phù hợp khi | Rủi ro cần quan sát |
|---|---|---|
| Nested loop | Một đầu vào nhỏ, đầu vào còn lại có index lookup hiệu quả | Nhiều vòng lặp và truy cập ngẫu nhiên khi đầu vào ngoài lớn |
| Hash join | Nối bằng trên các tập dữ liệu lớn, bộ nhớ đủ | Hash table lớn, spill ra đĩa, chọn sai build side |
| Merge join | Hai đầu vào đã có thứ tự hoặc sort có chi phí hợp lý | Chi phí sort, bộ nhớ và dữ liệu đầu vào lớn |

Không nên kết luận một thuật toán luôn tốt hơn thuật toán khác. Hãy đánh giá cùng cardinality, điều kiện nối, thứ tự dữ liệu và tài nguyên.

## 7. Các chiến lược optimizer dùng để tìm thứ tự nối

Không có một thuật toán duy nhất được mọi hệ quản trị sử dụng. Các chiến lược phổ biến gồm:

### Dynamic programming

Quy hoạch động xây dựng các kế hoạch tốt cho những tập con quan hệ, rồi kết hợp chúng để tìm kế hoạch cho tập lớn hơn. Ý tưởng là lưu lại chi phí tốt nhất đã tìm được cho một tập quan hệ thay vì đánh giá lại mọi cấu trúc từ đầu.

Ví dụ, với A, B, C, D, optimizer có thể đánh giá các tập {A,B}, {A,C}, {B,C} trước, sau đó dùng kết quả tốt của tập con để xây dựng kế hoạch cho ba hoặc bốn bảng.

Ưu điểm là có thể tìm được phương án tốt trong không gian được xét và tái sử dụng kết quả tập con. Nhược điểm là số tập con và phương án kết hợp tăng nhanh khi số bảng lớn. Optimizer thường áp dụng giới hạn hoặc cắt tỉa để kiểm soát chi phí lập kế hoạch.

### Greedy search

Chiến lược tham lam chọn một bước nối có vẻ rẻ nhất tại thời điểm hiện tại rồi tiếp tục với phần còn lại. Cách này giảm thời gian tìm kiếm nhưng lựa chọn tốt cục bộ không đảm bảo tạo ra kế hoạch tốt nhất toàn cục.

Một phép nối có chi phí thấp ngay lúc đầu có thể tạo ra tập trung gian lớn, khiến các bước sau đắt hơn. Vì vậy, greedy search thường cần heuristic và ước lượng tốt.

### Heuristic và pruning

Optimizer có thể loại sớm các phương án bị đánh giá quá đắt, giới hạn kiểu cây hoặc ưu tiên các quan hệ có điều kiện nối. Cắt tỉa (pruning) giảm số phương án phải xét nhưng có thể bỏ qua một kế hoạch tốt nếu ước lượng ban đầu không chính xác.

Các heuristic thường dựa trên:

- Điều kiện nối có sẵn.
- Khả năng lọc sớm.
- Số dòng ước lượng.
- Khả năng dùng chỉ mục.
- Chi phí tạo và lưu tập trung gian.
- Giới hạn bộ nhớ và tài nguyên lập kế hoạch.

### Tìm kiếm gần đúng hoặc ngẫu nhiên

Với truy vấn có nhiều quan hệ, một số hệ quản trị dùng thuật toán gần đúng, heuristic nâng cao hoặc tìm kiếm ngẫu nhiên để tránh thời gian lập kế hoạch bùng nổ. Một ví dụ là Genetic Query Optimizer (GEQO) trong PostgreSQL, có thể được sử dụng khi số quan hệ nối vượt ngưỡng cấu hình.

Phương pháp gần đúng giúp tìm kế hoạch trong thời gian hữu hạn, nhưng không cam kết tìm được kế hoạch có chi phí thấp nhất trong toàn bộ không gian. Ngưỡng, thuật toán và cách cấu hình phụ thuộc hệ quản trị và phiên bản.

## 8. Vì sao truy vấn nhiều bảng khó tối ưu hơn?

Số bảng tăng không chỉ làm tăng số hoán vị. Nó còn làm số quan hệ trung gian và các tương quan dữ liệu phức tạp hơn.

### Kích thước trung gian tăng

Nếu hai bảng có nhiều dòng khớp, kết quả nối có thể lớn hơn từng bảng. Khi tiếp tục nối với bảng khác, lượng dòng và độ rộng bản ghi có thể tăng thêm. Việc mang theo nhiều cột không cần thiết làm tăng bộ nhớ, I/O và chi phí truyền dữ liệu.

Có thể giảm chi phí bằng cách:

- Chỉ chọn các cột thực sự cần dùng.
- Đẩy điều kiện lọc xuống gần bảng nguồn khi hợp lệ.
- Tận dụng điều kiện nối và ràng buộc khóa.
- Tránh tạo Cartesian product ngoài ý muốn.
- Thu hẹp tập dữ liệu trước khi nối nếu không làm thay đổi ngữ nghĩa.

### Quan hệ nhiều-một và một-nhiều

Nối từ bảng orders sang customers theo khóa ngoại customer_id thường có quan hệ nhiều-một: nhiều đơn hàng có thể thuộc một khách hàng. Nối orders sang order_items thường là một-nhiều: một đơn có nhiều dòng hàng.

Các quan hệ này ảnh hưởng đến cardinality. Nếu optimizer biết customers.customer_id là unique, nó có thể ước lượng mỗi dòng orders khớp tối đa một dòng customer. Nếu thiếu ràng buộc hoặc thống kê, ước lượng có thể kém chính xác.

Đối với quan hệ một-nhiều, số dòng có thể tăng sau join. Nếu chỉ cần kiểm tra có tồn tại dòng con, EXISTS có thể biểu đạt ý định tốt hơn việc nối rồi loại trùng.

### Star schema và truy vấn phân tích

Trong kho dữ liệu, một fact table lớn có thể nối với nhiều dimension table. Đây là mô hình star schema. Optimizer cần đánh giá lọc trên dimension, join vào fact và khả năng tận dụng partition pruning, bitmap hoặc chiến lược join phù hợp.

Nếu lọc một dimension rất chọn lọc, có thể giảm số khóa fact cần xử lý. Nếu dimension filter không chọn lọc, đọc phần lớn fact table có thể là cần thiết. Một số hệ quản trị có tối ưu star join riêng, nhưng khả năng và điều kiện áp dụng khác nhau.

### Subquery, aggregation và outer join

Subquery, aggregation, window function, DISTINCT và outer join có thể hạn chế khả năng biến đổi thứ tự nối. Optimizer cần bảo toàn ngữ nghĩa về NULL, dòng không khớp và số lần đánh giá biểu thức.

Không nên giả định rằng mọi câu SQL có thể được chuyển tự do thành một chuỗi inner join. Đặc biệt, đổi vị trí điều kiện trong ON và WHERE với outer join có thể làm thay đổi kết quả.

## 9. Ràng buộc ngữ nghĩa giới hạn việc đổi thứ tự nối

Optimizer phải bảo đảm kết quả SQL không thay đổi. Một số cấu trúc hạn chế không gian tìm kiếm:

### Outer join

LEFT JOIN giữ lại dòng của phía trái ngay cả khi không có dòng khớp ở phía phải. Đổi thứ tự hoặc đẩy điều kiện từ WHERE xuống ON có thể làm thay đổi tập dòng được giữ lại.

Ví dụ:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Điều kiện WHERE trên o.status loại bỏ các dòng có giá trị NULL ở phía orders, nên kết quả có thể tương đương inner join trong trường hợp này. Nhưng nếu chuyển điều kiện vào ON:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
~~~

các khách hàng không có đơn PAID vẫn được giữ lại với cột orders là NULL. Hai truy vấn có ngữ nghĩa khác nhau. Vì vậy, việc biến đổi join phải xem xét vị trí điều kiện và yêu cầu kết quả.

### Semi join và anti join

EXISTS và NOT EXISTS thường được optimizer biến đổi thành semi join hoặc anti join. Semi join chỉ cần xác định có dòng khớp; anti join xác định không có dòng khớp. Chúng không tương đương với inner join thông thường trong mọi trường hợp vì số dòng đầu ra khác nhau.

### LATERAL và phụ thuộc tương quan

Một subquery LATERAL có thể tham chiếu giá trị từ quan hệ đứng trước. Điều này tạo phụ thuộc thứ tự: subquery cần đầu vào từ phía trước và không thể tùy ý được di chuyển như một quan hệ độc lập.

### Hàm có tác dụng phụ hoặc không ổn định

Các biểu thức volatile, hàm có tác dụng phụ hoặc truy vấn phụ thuộc thứ tự đánh giá có thể giới hạn phép biến đổi mà optimizer được phép thực hiện. Cần tránh dựa vào thứ tự thực thi ngẫu nhiên của SQL nếu ngữ nghĩa không bảo đảm thứ tự đó.

## 10. Đọc execution plan để đánh giá thứ tự nối

Kế hoạch thực thi cho biết thứ tự các phép nối mà optimizer đã chọn. Cách hiển thị tùy hệ quản trị, nhưng các câu hỏi sau hữu ích:

1. Bảng hoặc nhánh nào được truy cập đầu tiên?
2. Điều kiện lọc được áp dụng ở đâu?
3. Số dòng ước lượng và số dòng thực tế ở từng nhánh là bao nhiêu?
4. Thuật toán join là nested loop, hash join hay merge join?
5. Nhánh nào được chọn làm outer, inner, build hoặc probe?
6. Có bước sort, materialize hoặc ghi vùng nhớ tạm không?
7. Số vòng lặp và lượng buffer đọc có bất thường không?
8. Có phép nối tạo ra nhiều dòng trung gian hơn số dòng cuối cùng đáng kể không?

### Ví dụ với PostgreSQL

Có thể dùng EXPLAIN để xem kế hoạch dự kiến:

~~~sql
EXPLAIN
SELECT
    c.customer_name,
    o.order_id,
    p.product_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE c.region = 'NORTH'
  AND o.created_at >= DATE '2026-01-01';
~~~

Để lấy số liệu thực tế và buffer:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_name,
    o.order_id,
    p.product_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
JOIN products AS p
  ON p.product_id = oi.product_id
WHERE c.region = 'NORTH'
  AND o.created_at >= DATE '2026-01-01';
~~~

EXPLAIN ANALYZE thực thi câu truy vấn. Chỉ dùng với truy vấn phù hợp và môi trường có thể chịu tải phát sinh. Với truy vấn đọc có thể tốn tài nguyên đáng kể; với câu lệnh thay đổi dữ liệu, cần hiểu rõ tác động và cơ chế transaction trước khi chạy.

Trong PostgreSQL, plan thường hiển thị cây từ trên xuống theo quan hệ cha-con; dữ liệu được tạo ở các node con rồi truyền lên node cha. Hãy đọc từ các node lá lên trên để hiểu thứ tự truy cập và số dòng được đưa vào từng join.

### Những dấu hiệu cần chú ý

- **Actual rows lớn hơn estimated rows nhiều lần:** có thể sai thống kê, dữ liệu lệch hoặc tương quan cột.
- **Nested loop có loops rất lớn:** có thể đang thực hiện quá nhiều lần lookup.
- **Hash join có nhiều batch hoặc temp I/O:** có thể hash table vượt bộ nhớ dự kiến.
- **Sort lớn trước merge join:** kiểm tra thứ tự đầu vào và khả năng dùng index.
- **Filter loại bỏ phần lớn dòng sau join:** có thể điều kiện chưa được áp dụng sớm hoặc không thể đẩy xuống do ngữ nghĩa.
- **Một nhánh tạo nhiều dòng trung gian:** xem có thể lọc sớm hơn hoặc thay đổi cách biểu đạt truy vấn không.
- **Buffers read/hit cao:** xem lượng dữ liệu phải đọc và khả năng tái sử dụng cache.

Không nên đánh giá thứ tự nối chỉ bằng hình dạng cây. Một kế hoạch có nhiều node không nhất thiết kém hơn. Cần so sánh số dòng, thời gian, I/O, CPU và tải thực tế.

## 11. Ví dụ so sánh hai hướng nối

Giả sử hệ thống có:

- customers: 2 triệu khách hàng, trong đó 1% thuộc region NORTH.
- orders: 30 triệu đơn, mỗi khách hàng có số đơn khác nhau.
- order_items: 90 triệu dòng chi tiết.
- products: 500 nghìn sản phẩm.

Truy vấn cần đơn hàng ở khu vực NORTH từ đầu năm và tên sản phẩm trong từng đơn.

### Hướng A: lọc sớm nhánh khách hàng và đơn hàng

Một kế hoạch khả thi có thể bắt đầu bằng việc lọc customers theo region, sau đó nối với orders và order_items. Nếu điều kiện ngày cũng chọn lọc và có chỉ mục phù hợp, tập đơn hàng có thể được thu hẹp trước khi nối sang chi tiết đơn hàng.

Lợi ích tiềm năng:

- Giảm số khách hàng và đơn hàng đầu vào.
- Giảm số lần tra cứu ở các bước sau.
- Giảm lượng dữ liệu trung gian và bộ nhớ.

Rủi ro:

- Nếu region NORTH thực tế chiếm tỷ lệ lớn hơn ước lượng, nhánh lọc không nhỏ như dự kiến.
- Nếu thiếu chỉ mục phù hợp, lọc sớm có thể vẫn phải quét lượng dữ liệu lớn.
- Nếu orders có phân bố theo ngày và khu vực tương quan, thống kê đơn cột có thể ước lượng sai.

### Hướng B: bắt đầu từ orders theo thời gian

Optimizer có thể bắt đầu bằng việc lọc orders theo created_at, rồi nối order_items, customers và products. Hướng này có thể hợp lý nếu khoảng ngày chọn lọc rất cao hoặc có chỉ mục/partition phù hợp.

Rủi ro:

- Nếu khoảng thời gian rộng, nhiều đơn hàng và chi tiết được đưa vào phép nối.
- Nếu chỉ lọc region sau khi đã nối, nhiều dòng trung gian có thể được tạo rồi mới loại bỏ.
- Nếu order_items có nhiều dòng trên mỗi đơn, số dòng có thể tăng đáng kể trước khi hoàn tất các phép nối.

Không thể kết luận hướng A luôn tốt hơn hướng B. Optimizer cần dữ liệu thực tế để biết điều kiện region hay created_at chọn lọc hơn và chi phí truy cập tương ứng. Người tối ưu cần kiểm chứng các ước lượng và kế hoạch, không chọn thứ tự chỉ dựa trên số dòng bảng ban đầu.

## 12. Khi nào nên viết lại SQL hoặc cung cấp thêm thông tin?

Nếu optimizer không tìm được kế hoạch phù hợp, có thể cần điều chỉnh cách biểu đạt truy vấn hoặc bổ sung thông tin về dữ liệu.

### Viết rõ điều kiện nối

Mỗi quan hệ cần điều kiện nối chính xác. Tránh cú pháp nối ngầm hoặc thiếu điều kiện vì dễ tạo Cartesian product và làm truy vấn khó đọc.

### Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại

Ví dụ cần tìm khách hàng có ít nhất một đơn hàng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

EXISTS diễn đạt ý định kiểm tra sự tồn tại. Optimizer có thể dùng semi join hoặc một chiến lược tương đương. Nếu dùng inner join rồi DISTINCT, hệ thống có thể tạo nhiều dòng trung gian trước khi loại trùng, tùy kế hoạch.

### Chỉ lấy cột cần thiết

Tránh SELECT * trong truy vấn nối nhiều bảng nếu ứng dụng chỉ dùng một vài cột. Dòng trung gian hẹp hơn giúp giảm bộ nhớ, I/O, băng thông và có thể tăng khả năng dùng covering index.

### Cập nhật thống kê và ràng buộc

Thống kê mới, unique constraint, primary key và foreign key chính xác có thể giúp optimizer ước lượng và loại bỏ một số phương án không cần thiết. Không khai báo ràng buộc nếu dữ liệu không bảo đảm điều kiện đó.

### Cân nhắc CTE và materialization

CTE có thể giúp cấu trúc SQL dễ hiểu, nhưng không phải hệ quản trị nào cũng xử lý CTE giống nhau. Một số CTE có thể được inline, một số có thể được materialize hoặc bị giới hạn biến đổi tùy phiên bản và cấu trúc. Không nên dùng CTE chỉ với giả định rằng nó luôn buộc optimizer thực hiện theo một thứ tự cụ thể.

## 13. Hạn chế thời gian lập kế hoạch và truy vấn quá nhiều bảng

Truy vấn nhiều bảng có thể tiêu tốn thời gian đáng kể trong giai đoạn optimizer tìm kiếm kế hoạch. Điều này thường quan trọng trong workload có nhiều truy vấn ad hoc, truy vấn sinh tự động hoặc báo cáo ghép nhiều bảng.

Các hướng kiểm soát:

- Giảm các phép nối không cần thiết và loại bỏ bảng chỉ dùng để lấy dữ liệu không được sử dụng.
- Dùng view hoặc mô hình dữ liệu phù hợp để chuẩn hóa cách truy cập, nhưng vẫn kiểm tra kế hoạch sau khi mở rộng view.
- Tách truy vấn thành các giai đoạn chỉ khi có lý do về cardinality, khả năng tái sử dụng hoặc giới hạn optimizer; cân nhắc chi phí materialization và round trip.
- Giới hạn số bảng được nối động trong bộ tạo báo cáo.
- Đo thời gian lập kế hoạch riêng với thời gian thực thi nếu hệ quản trị cung cấp.
- Kiểm tra cấu hình và ngưỡng chuyển sang thuật toán tìm kiếm gần đúng khi truy vấn có rất nhiều quan hệ.

Việc chia một truy vấn thành nhiều câu lệnh có thể giảm không gian tìm kiếm, nhưng cũng có thể tạo thêm round trip, bảng tạm, ghi đọc trung gian và rủi ro nhất quán giữa các bước. Hãy so sánh tổng chi phí của cả quy trình.

## 14. Quy trình điều tra thứ tự nối kém hiệu quả

Khi một truy vấn nhiều bảng chậm, có thể áp dụng trình tự sau:

1. **Xác định workload:** ghi lại tần suất gọi, tham số đại diện, p50/p95/p99 và mức tải.
2. **Lấy execution plan:** thu thập kế hoạch dự kiến và số liệu thực tế nếu an toàn.
3. **Vẽ join graph:** liệt kê các bảng, điều kiện nối, điều kiện lọc và các quan hệ khóa.
4. **Tìm sai lệch cardinality:** xác định node đầu tiên có estimated rows khác actual rows đáng kể.
5. **Kiểm tra thống kê:** xem histogram, giá trị phổ biến, distinct count và tương quan cột.
6. **Kiểm tra thứ tự và thuật toán:** xem nhánh nào được nối trước, nested loop/hash/merge, loops và kích thước dữ liệu trung gian.
7. **Kiểm tra đường truy cập:** đánh giá index, scan, partition pruning và điều kiện có thể đẩy xuống.
8. **Đưa ra giả thuyết cụ thể:** ví dụ lọc ngày chưa được áp dụng sớm, thống kê tenant sai hoặc hash build side lớn hơn ước lượng.
9. **Thử một thay đổi có kiểm soát:** cập nhật thống kê, điều chỉnh chỉ mục hoặc viết lại SQL theo giả thuyết.
10. **Đo lại:** so sánh cùng tham số, cùng dữ liệu và mức tải; kiểm tra cả truy vấn liên quan.

Nếu có thể, lưu lại plan identifier, phiên bản hệ quản trị, thống kê tại thời điểm đo và cấu hình liên quan. Điều này giúp giải thích khi kế hoạch thay đổi sau khi dữ liệu tăng hoặc hệ thống được nâng cấp.

## 15. Những sai lầm thường gặp

- **Cho rằng thứ tự bảng viết trong FROM quyết định thứ tự thực thi:** optimizer có thể biến đổi thứ tự join nếu ngữ nghĩa cho phép.
- **Luôn nối bảng nhỏ trước:** số dòng ban đầu không đủ; cần xét điều kiện lọc, số dòng khớp, độ rộng và chi phí truy cập.
- **Chỉ nhìn số bảng:** độ phức tạp còn phụ thuộc join graph, loại join, điều kiện lọc và tương quan dữ liệu.
- **Giả định mọi inner join có chi phí tương đương:** các thứ tự tạo tập trung gian khác nhau có thể có chi phí rất khác.
- **Bỏ qua sai lệch cardinality:** optimizer có thể chọn kế hoạch tồi dù thuật toán join tự nó phù hợp.
- **Ép join order bằng hint quá sớm:** có thể khóa optimizer vào một kế hoạch kém khi dữ liệu hoặc workload thay đổi.
- **Nhầm hash spill với lỗi thuật toán:** cần kiểm tra build side, bộ nhớ và ước lượng trước khi đổi join method.
- **Không xét outer join và NULL:** biến đổi điều kiện hoặc thứ tự có thể làm thay đổi kết quả SQL.
- **Tách truy vấn thành nhiều bước mà không tính chi phí:** materialization, round trip và tính nhất quán có thể làm tổng workload chậm hơn.
- **So sánh hai kế hoạch ở mức tải khác nhau:** không đủ cơ sở để kết luận thứ tự nối mới tốt hơn.

## 16. Checklist đánh giá join order

Khi xem một truy vấn nhiều bảng, hãy trả lời:

1. Có bao nhiêu quan hệ và join graph có kết nối đầy đủ theo điều kiện dự kiến không?
2. Có Cartesian product ngoài ý muốn hoặc điều kiện nối bị thiếu không?
3. Điều kiện lọc nào chọn lọc nhất và có thể áp dụng sớm ở đâu?
4. Các điều kiện lọc có tương quan hoặc dữ liệu lệch khiến cardinality khó ước lượng không?
5. Estimated rows và actual rows lệch từ node nào?
6. Thứ tự nối hiện tại tạo ra tập trung gian lớn ở bước nào?
7. Nested loop, hash join hay merge join phù hợp với kích thước thực tế của hai đầu vào?
8. Hash table hoặc sort có tràn ra vùng nhớ tạm không?
9. Chỉ mục, thứ tự cột và partition pruning có hỗ trợ đường truy cập mong muốn không?
10. Có outer join, semi join, LATERAL hoặc điều kiện khác giới hạn phép đổi thứ tự không?
11. Optimizer có đang tốn nhiều thời gian lập kế hoạch do số bảng quá lớn không?
12. Thay đổi có cải thiện thời gian, I/O, CPU và throughput ở cùng điều kiện tải không?

## Kết luận

Không gian tìm kiếm thứ tự nối gồm nhiều cách sắp xếp và cấu trúc cây để kết hợp các quan hệ. Với inner join, optimizer có thể tận dụng tính giao hoán và kết hợp để thay đổi thứ tự, nhưng outer join, semi join, LATERAL và các phụ thuộc ngữ nghĩa có thể giới hạn phép biến đổi. Khi số bảng tăng, số phương án và độ phức tạp ước lượng cũng tăng, khiến việc tìm kế hoạch phù hợp trở nên khó hơn.

Chất lượng join order phụ thuộc mạnh vào cardinality estimation, thống kê dữ liệu, điều kiện lọc, chỉ mục, thuật toán join và kích thước tập trung gian. Một phương pháp tối ưu hiệu quả cần đọc join graph và execution plan, tìm node sai lệch đầu tiên, xác định nguyên nhân bằng số liệu rồi thử thay đổi có kiểm soát. Đo lại dưới cùng điều kiện workload giúp xác nhận kế hoạch mới thực sự giảm chi phí và giữ hiệu năng ổn định khi truy vấn mở rộng qua nhiều bảng.

