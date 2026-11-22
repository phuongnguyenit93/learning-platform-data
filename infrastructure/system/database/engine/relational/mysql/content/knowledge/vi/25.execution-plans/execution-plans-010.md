# Nested-loop, hash join và thay đổi theo phiên bản

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Mô tả cách Nested-Loop Join (NLJ) truyền từng hàng từ bảng ngoài sang bảng trong.
- Giải thích vì sao index trên cột join có thể làm NLJ hiệu quả.
- Nhận diện giới hạn của nested loop khi bảng trong phải bị quét lặp lại.
- Phân biệt Block Nested-Loop (BNL) lịch sử, Batched Key Access (BKA) và Hash Join.
- Mô tả hai pha build và probe của hash join, cùng giới hạn bộ nhớ của join buffer.
- Đọc EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE để nhận diện thuật toán join.
- Hiểu các thay đổi quan trọng từ MySQL 8.0.18, 8.0.19, 8.0.20 đến MySQL 8.4.
- Kiểm soát thuật toán ở phạm vi session hoặc bằng optimizer hint khi cần kiểm thử.
- Chọn cách tối ưu dựa trên số hàng, index, join order, bộ nhớ và số liệu thực thi.

Khi JOIN hai bảng, MySQL cần một thuật toán để ghép các hàng thỏa điều kiện. Hai thuật toán quan trọng trong MySQL hiện đại là Nested-Loop Join và Hash Join.

Nested loop đọc một hàng từ bảng ngoài, sau đó tìm các hàng phù hợp ở bảng trong. Nếu bảng trong có index trên cột join, mỗi lần lặp có thể trở thành một index lookup nhanh. Nếu không có index và phải quét lại bảng trong cho mỗi hàng ngoài, chi phí có thể tăng rất mạnh.

Hash join giải quyết một nhóm trường hợp khác: MySQL đọc một đầu vào để xây dựng bảng băm trên khóa join, sau đó đọc đầu vào còn lại và dò bảng băm. Thuật toán này đặc biệt hữu ích khi không có index phù hợp trên điều kiện join và cần ghép nhiều hàng. Từ MySQL 8.0.18, hash join bắt đầu xuất hiện; từ 8.0.20, nó thay thế Block Nested-Loop trong các trường hợp thuật toán đó từng được sử dụng.

## 1. Join algorithm và join order

Một câu JOIN có hai quyết định liên quan nhưng khác nhau:

- Join order: bảng nào được đọc trước, bảng nào được đọc sau.
- Join algorithm: MySQL dùng cách nào để ghép hàng giữa các bảng.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

Optimizer có thể chọn customer làm đầu vào ngoài và sales_order làm đầu vào trong, hoặc thay đổi thứ tự nếu ước lượng chi phí cho thấy cách khác tốt hơn.

Join order ảnh hưởng đến số hàng phải truyền vào bước tiếp theo. Nếu điều kiện WHERE làm giảm customer từ một triệu hàng xuống còn 20 hàng, việc đọc customer trước có thể giúp giảm số lần dò ở bảng trong. Nếu đầu vào ngoài quá lớn, NLJ có thể thực hiện rất nhiều vòng lặp.

Không nên suy luận thuật toán chỉ từ cú pháp JOIN. MySQL chọn kế hoạch dựa trên thống kê, index, điều kiện lọc, kích thước dữ liệu và chi phí ước lượng.

## 2. Nested-Loop Join hoạt động như thế nào?

Nested-Loop Join (NLJ) là thuật toán ghép hàng theo vòng lặp lồng nhau. MySQL đọc hàng từ bảng ngoài, rồi dùng hàng đó để xử lý bảng trong. Quá trình lặp lại cho đến khi hết hàng ở bảng ngoài.

Với hai bảng, mô hình khái quát:

~~~text
for each row in outer_table:
    for each matching row in inner_table:
        output joined row
~~~

Với ba bảng, vòng lặp có thể lồng sâu hơn:

~~~text
for each row in t1:
    for each matching row in t2:
        for each matching row in t3:
            output joined row
~~~

Mỗi bảng nằm ở vòng trong có thể được truy cập nhiều lần. Đây là lý do join order và index của bảng trong rất quan trọng.

### 2.1. NLJ kết hợp index lookup

Giả sử customer có khóa chính customer_id và sales_order có index trên customer_id.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

MySQL có thể thực hiện:

1. Dùng PRIMARY KEY để tìm khách hàng 101.
2. Dùng index trên sales_order.customer_id để tìm các đơn của khách hàng đó.
3. Trả về các hàng kết hợp.

Nếu chỉ có một khách hàng được chọn, số lần lookup ở bảng đơn hàng rất nhỏ. Đây là mẫu NLJ thường hiệu quả: bảng ngoài đã được lọc mạnh và bảng trong có index hỗ trợ điều kiện join.

### 2.2. Chi phí NLJ tăng khi đầu vào ngoài lớn

Giả sử bảng ngoài có 50.000 hàng và mỗi hàng phải tìm trong bảng trong. Nếu mỗi lần tìm là một index lookup, MySQL vẫn phải thực hiện nhiều lookup. Nếu mỗi lần tìm phải quét toàn bộ bảng trong gồm 2 triệu hàng, công việc có thể trở nên cực kỳ tốn kém.

Có thể hình dung chi phí gần đúng:

- Có index phù hợp: số lần lặp ngoài nhân với chi phí lookup index và số hàng khớp.
- Không có index, phải quét bảng trong mỗi lần: số hàng ngoài nhân với số hàng bảng trong.

Đây chỉ là mô hình giúp suy luận, không phải công thức cost model đầy đủ của MySQL. Bộ nhớ đệm, số page đã nằm trong buffer pool, điều kiện lọc, kích thước hàng và các tối ưu khác đều ảnh hưởng chi phí thật.

### 2.3. Đọc NLJ trong EXPLAIN TREE

Với MySQL hỗ trợ TREE format:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

Một kế hoạch nested loop có thể được trình bày theo dạng:

~~~text
-> Nested loop inner join
    -> Single-row index lookup on c using PRIMARY
    -> Index lookup on o using idx_order_customer
       (customer_id = c.customer_id)
~~~

Tên iterator và chi tiết có thể khác theo phiên bản, thống kê và schema. Hãy nhận diện cấu trúc: một đầu vào được đọc trước, sau đó một iterator bên trong được gọi theo các hàng đầu vào.

### 2.4. NLJ không có index trên bảng trong

Nếu bảng trong không có index phù hợp, NLJ đơn giản có thể phải quét bảng trong cho mỗi hàng của bảng ngoài. Đây là tình huống cần điều tra.

Trong các phiên bản cũ, Block Nested-Loop có thể dùng join buffer để gom nhiều hàng từ vòng ngoài, nhờ đó giảm số lần quét bảng trong. Từ MySQL 8.0.20, BNL đã bị loại bỏ; hash join được dùng trong các trường hợp BNL từng xử lý.

## 3. Block Nested-Loop là thuật toán lịch sử

Block Nested-Loop (BNL) mở rộng nested loop bằng cách lưu nhiều hàng từ các vòng ngoài vào join buffer. Khi buffer đầy, MySQL quét bảng trong một lần và so sánh mỗi hàng của bảng trong với nhiều tổ hợp hàng đang nằm trong buffer.

Mô hình đơn giản:

~~~text
read a batch of outer rows into join buffer

for each row in inner_table:
    compare it with each outer row in the buffer
    output matching combinations

repeat with the next batch
~~~

Nếu một batch chứa 100 hàng ngoài, một lần quét bảng trong có thể kiểm tra với cả 100 hàng đó. BNL vì vậy giảm số lần quét bảng trong so với NLJ đơn giản không có index.

Tuy nhiên, BNL không còn là thuật toán join được sử dụng từ MySQL 8.0.20. Nội dung về BNL vẫn quan trọng để hiểu lịch sử phiên bản và tên các thiết lập điều khiển còn được giữ lại.

### 3.1. Vì sao tên block_nested_loop vẫn còn?

Biến block_nested_loop trong optimizer_switch và các hint BNL/NO_BNL vẫn được giữ lại. Từ MySQL 8.0.20, chúng điều khiển việc dùng hash join, không có nghĩa server vẫn thực thi thuật toán BNL cũ.

Đây là một điểm dễ gây nhầm lẫn khi đọc cấu hình hoặc tài liệu cũ. Khi làm việc với MySQL 8.4, hãy hiểu block_nested_loop là cờ điều khiển hash join.

## 4. Hash Join hoạt động như thế nào?

Hash join thường gồm hai pha:

1. Build: đọc một đầu vào và xây dựng bảng băm theo cột hoặc biểu thức join.
2. Probe: đọc đầu vào còn lại, tính hash key cho từng hàng và dò các hàng khớp trong bảng băm.

Ví dụ join theo customer_id:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id;
~~~

Nếu không có index nào dùng được cho điều kiện join, MySQL có thể chọn hash join:

- Đọc một bảng và tạo hash table theo customer_id.
- Đọc bảng còn lại.
- Với mỗi hàng, tính hash từ customer_id và tìm các hàng cùng khóa.
- Kiểm tra điều kiện join và trả về kết quả phù hợp.

Optimizer chọn đầu vào build và probe dựa trên kế hoạch, kích thước ước lượng và chi phí. Không nên giả định bảng đứng bên trái trong SQL luôn là bảng build.

### 4.1. Minh họa build và probe

~~~text
Input A                         Input B
customer_id, customer_name      customer_id, order_id
        |                               |
        v                               v
  Build hash table                 Probe hash table
  key = customer_id                key = customer_id
        |                               |
        +------------+------------------+
                     |
                     v
              Matching rows
                     |
                     v
                Join result
~~~

Hash join tránh việc quét lại toàn bộ bảng trong cho từng hàng ngoài như NLJ đơn giản không có index. Nó vẫn phải đọc các đầu vào và xử lý kết quả khớp; nếu có nhiều hàng trùng khóa, số hàng đầu ra có thể rất lớn.

### 4.2. Khi nào hash join phù hợp?

Hash join thường phù hợp khi:

- Điều kiện join có equality (equi-join).
- Không có index dùng được cho điều kiện join.
- Cả hai đầu vào có nhiều hàng và cần so khớp theo khóa.
- Quét đầu vào và xây dựng hash table có chi phí thấp hơn việc thực hiện nhiều index lookup.

Hash join cũng có thể xuất hiện khi một hoặc nhiều index chỉ hỗ trợ điều kiện lọc riêng của từng bảng, nhưng không có index dùng được cho điều kiện nối giữa hai bảng.

Nếu một đầu vào được lọc còn vài hàng và bảng kia có index phù hợp trên cột join, NLJ với index lookup thường là lựa chọn cạnh tranh hơn.

Từ MySQL 8.0.20, hash join còn được dùng trong một số trường hợp trước đây dùng BNL dù join không có điều kiện equality, gồm inner non-equi join, semijoin, antijoin và outer join. Hash join cũng có thể được dùng cho Cartesian product khi truy vấn không có điều kiện join. Vì vậy, phạm vi hash join trong phiên bản mới rộng hơn ví dụ equi-join cơ bản ở trên.

### 4.3. Hash join không loại bỏ chi phí đọc dữ liệu

Hash join vẫn phải đọc dữ liệu từ các đầu vào. Nếu bảng rất lớn, bộ nhớ không đủ chứa hash table, MySQL có thể dùng file trên đĩa để xử lý phần vượt bộ nhớ.

Ngoài ra, hash join không làm giảm số hàng đầu ra của quan hệ many-to-many. Nếu một customer_id xuất hiện 1.000 lần ở bảng A và 2.000 lần ở bảng B, join theo khóa đó có thể tạo tới 2 triệu tổ hợp hàng cho khóa ấy.

Hãy kiểm tra cardinality, điều kiện join và số hàng đầu ra trước khi kết luận thuật toán là nguyên nhân duy nhất của truy vấn chậm.

## 5. Hash join và bộ nhớ join_buffer_size

Biến hệ thống join_buffer_size giới hạn bộ nhớ mà một hash join có thể sử dụng. Nếu hash join cần nhiều bộ nhớ hơn giới hạn, MySQL xử lý phần dữ liệu bằng các file trên đĩa.

Kiểm tra thiết lập hiện tại:

~~~sql
SELECT
    @@GLOBAL.join_buffer_size AS global_join_buffer_size,
    @@SESSION.join_buffer_size AS session_join_buffer_size,
    @@GLOBAL.open_files_limit AS open_files_limit;
~~~

Đọc giá trị theo byte. Không tăng join_buffer_size chỉ vì nhìn thấy hash join. Hãy xác nhận hash join có spill ra đĩa, thời gian chờ I/O và số lượng truy vấn đồng thời trước khi điều chỉnh.

### 5.1. Hash join spill ra đĩa

Khi bộ nhớ không đủ, hash join dùng file để xử lý. Điều này có thể làm tăng I/O và thời gian thực thi. Số file mà một hash join có thể sử dụng còn chịu giới hạn open_files_limit.

MySQL Reference Manual đề cập hai hướng xử lý khi hash join cần nhiều file hơn mức cho phép:

- Tăng join_buffer_size để giảm hoặc tránh spill.
- Tăng open_files_limit nếu số file cần dùng vượt giới hạn.

Đây là thay đổi cấu hình server cần đo đạc và xem xét tài nguyên. Đừng áp dụng trực tiếp trên production chỉ dựa trên một truy vấn.

### 5.2. Join buffer được cấp phát theo nhu cầu

Join buffer của hash join được cấp phát tăng dần. Điều này giúp các truy vấn nhỏ không nhất thiết tiêu thụ ngay toàn bộ giá trị join_buffer_size. Tuy nhiên, outer join có thể cấp phát toàn bộ buffer.

Nếu tăng giới hạn quá cao, nhiều truy vấn đồng thời có thể làm tổng mức sử dụng bộ nhớ tăng đáng kể. Cần tính đến concurrency, số join trong mỗi query và giới hạn RAM của server.

## 6. BKA: một biến thể nested-loop có batch key

Batched Key Access (BKA) là một thuật toán join dùng index access trên bảng được nối và join buffer để gom các key lookup thành batch.

Thay vì gửi từng key riêng lẻ tới storage engine, BKA gom nhiều key rồi dùng Multi-Range Read (MRR) để truy cập các hàng hiệu quả hơn. Nó vẫn là chiến lược dựa trên index lookup, khác với hash join vốn xây dựng hash table.

BKA có thể hữu ích khi bảng trong có index phù hợp nhưng nhiều lookup riêng lẻ gây truy cập dữ liệu không thuận lợi. BKA hỗ trợ inner join, outer join và semijoin trong các trường hợp được optimizer hỗ trợ.

### 6.1. BKA mặc định tắt

Trong MySQL 8.4:

- batched_key_access mặc định là off.
- Để BKA có tác dụng, mrr phải bật.
- Do ước lượng chi phí MRR có thể quá bi quan, tài liệu yêu cầu mrr_cost_based=off để BKA được sử dụng.

Cấu hình thử trong session:

Ví dụ dưới đây dùng hai bảng trong lab ở mục 9. Sau khi tạo dữ liệu và thêm index idx_order_customer ở mục 9.3, có thể thử BKA trên truy vấn join đó:

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch =
    'batched_key_access=on,mrr=on,mrr_cost_based=off';

EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

Thiết lập này chỉ phục vụ thử nghiệm trong session. Optimizer vẫn quyết định có dùng BKA hay không dựa trên điều kiện truy vấn và chi phí. Kiểm tra lại EXPLAIN sau khi bật; không giả định cứ bật flag là BKA chắc chắn xuất hiện.

### 6.2. Phân biệt BKA và hash join

| Tiêu chí | BKA | Hash join |
|---|---|---|
| Cơ chế chính | Nested-loop với batch index lookup | Build hash table rồi probe |
| Cần index trên bảng được dò | Có | Không cần index trên join condition trong trường hợp điển hình |
| Dùng join buffer | Có | Có |
| MRR | Được dùng để gom truy cập | Không phải điều kiện cốt lõi |
| Điều kiện phù hợp | Có index và cần gom lookup | Nhiều hàng, không có index join phù hợp |
| Cấu hình chính | batched_key_access, mrr | block_nested_loop |

Không nên coi BKA là thuật toán thay thế hash join trong mọi trường hợp. Chọn thuật toán phù hợp phụ thuộc index và mẫu dữ liệu.

## 7. Thay đổi thuật toán theo phiên bản MySQL

Lịch sử phiên bản rất quan trọng vì cùng một câu SQL có thể tạo kế hoạch khác khi nâng cấp MySQL.

| Phiên bản | Thay đổi liên quan |
|---|---|
| Trước 8.0.18 | Hash join chưa được hỗ trợ; MySQL dùng nested-loop và biến thể BNL trong các trường hợp phù hợp |
| 8.0.18 | Hash join được giới thiệu cho equi-join khi không có index dùng được cho điều kiện join; có cờ hash_join và hint HASH_JOIN/NO_HASH_JOIN ở phiên bản này |
| 8.0.19 | hash_join và hint HASH_JOIN/NO_HASH_JOIN không còn tác dụng; dùng block_nested_loop và hint BNL/NO_BNL để điều khiển hash join |
| 8.0.20 | BNL bị loại bỏ; hash join thay thế các trường hợp trước đó dùng BNL, mở rộng sang các loại join và điều kiện đã được hỗ trợ |
| 8.4 | Hash join được dùng mặc định khi có thể; block_nested_loop cùng BNL/NO_BNL điều khiển hash join; BKA vẫn là một tùy chọn riêng |

### 7.1. 8.0.18: hash join xuất hiện

Từ MySQL 8.0.18, hash join được sử dụng cho các truy vấn mà mỗi phép join có điều kiện equi-join và không có index dùng được cho điều kiện join.

Ví dụ:

~~~sql
SELECT *
FROM t1
JOIN t2
    ON t1.c1 = t2.c1;
~~~

Nếu không có index phù hợp trên c1 của hai bảng, hash join có thể là lựa chọn. Có thể nhận biết qua EXPLAIN FORMAT=TREE hoặc EXPLAIN ANALYZE.

### 7.2. 8.0.19: thay đổi cách điều khiển

Trong 8.0.18, có thể dùng:

~~~sql
SET SESSION optimizer_switch = 'hash_join=off';
~~~

hoặc các hint HASH_JOIN và NO_HASH_JOIN.

Từ 8.0.19, các tùy chọn này không còn tác dụng. Dùng:

~~~sql
SET SESSION optimizer_switch = 'block_nested_loop=off';
~~~

hoặc hint NO_BNL để tắt hash join cho phạm vi được chỉ định.

### 7.3. 8.0.20: BNL bị loại bỏ

Từ MySQL 8.0.20, BNL không còn được server sử dụng. Hash join được dùng trong các trường hợp mà trước đây BNL sẽ được chọn, bao gồm inner non-equi join, semijoin, antijoin, left outer join và right outer join. Hash join cũng có thể được áp dụng cho Cartesian product khi không có điều kiện join.

Vì vậy, khi đọc tài liệu hoặc log từ MySQL 5.7, 8.0.17 và các bản mới hơn, không nên mặc định cùng một Using join buffer có nghĩa cùng thuật toán.

### 7.4. MySQL 8.4: block_nested_loop không còn có nghĩa BNL

Trong MySQL 8.4, block_nested_loop là cờ điều khiển hash join. Tên biến và hint được giữ lại vì tương thích và lịch sử.

Kiểm tra:

~~~sql
SELECT
    @@version AS mysql_version,
    @@SESSION.optimizer_switch AS optimizer_switch;
~~~

Có thể thấy hash_join vẫn xuất hiện trong một số đầu ra optimizer_switch của MySQL 8.4, nhưng cờ này không có tác dụng. Hãy dùng block_nested_loop để kiểm soát hash join.

## 8. Đọc kế hoạch join bằng EXPLAIN

### 8.1. EXPLAIN FORMAT=TREE

TREE format thể hiện các iterator và quan hệ cha-con của kế hoạch. Đây là cách trực quan để phân biệt nested loop với hash join.

Ví dụ hash join:

~~~sql
EXPLAIN FORMAT=TREE
SELECT *
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;
~~~

Kế hoạch có thể có dạng:

~~~text
-> Inner hash join (o.customer_id = c.customer_id)
    -> Table scan on o
    -> Hash
        -> Table scan on c
~~~

Ví dụ nested loop:

~~~text
-> Nested loop inner join
    -> Index lookup on c using PRIMARY
    -> Index lookup on o using idx_order_customer
       (customer_id = c.customer_id)
~~~

Đây là hình dạng minh họa. Tên iterator, thứ tự build/probe và chi phí thay đổi theo phiên bản và dữ liệu.

### 8.2. EXPLAIN dạng tabular

Trong định dạng truyền thống, hash join có thể được nhận diện ở cột Extra:

~~~text
Using where; Using join buffer (hash join)
~~~

Các bảng tham gia hash join có thể có type = ALL vì MySQL quét đầu vào để xây dựng hoặc dò hash table. Điều đó không tự động có nghĩa kế hoạch xấu; phải xét tổng chi phí và lượng dữ liệu.

### 8.3. EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi câu SELECT và hiển thị số hàng thực tế, số vòng lặp và thời gian iterator.

~~~sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

Khi đọc kết quả, chú ý:

- Iterator nào tạo hash table.
- Iterator nào quét đầu vào probe.
- Số hàng thực tế của mỗi đầu vào.
- Số vòng lặp của nested loop.
- Chênh lệch giữa số hàng ước lượng và thực tế.
- Thời gian của từng iterator và thời gian toàn truy vấn.

EXPLAIN ANALYZE thực sự chạy truy vấn. Hãy dùng dữ liệu và điều kiện có chi phí thực thi chấp nhận được.

## 9. Thực hành: so sánh hash join và nested loop

Bài lab dùng hai bảng độc lập không có foreign key để kiểm soát index join. Ban đầu không có index trên order_demo.customer_id, sau đó thêm index để quan sát kế hoạch thay đổi.

### 9.1. Tạo bảng và dữ liệu

~~~sql
CREATE TABLE customer_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO customer_demo (
    customer_id, customer_name, region_code
)
VALUES
    (101, 'Nguyen An', 'NORTH'),
    (102, 'Tran Binh', 'SOUTH'),
    (103, 'Le Chi', 'NORTH'),
    (104, 'Pham Dung', 'CENTRAL');

INSERT INTO order_demo (
    order_id, customer_id, total_amount, created_at
)
VALUES
    (5001, 101, 1250000.00, '2026-02-01 09:15:00'),
    (5002, 101, 2400000.00, '2026-02-03 11:30:00'),
    (5003, 102,  890000.00, '2026-02-08 14:00:00'),
    (5004, 103, 3400000.00, '2026-02-15 16:45:00'),
    (5005, 101,  450000.00, '2026-02-18 10:20:00'),
    (5006, 104, 5100000.00, '2026-03-02 08:10:00'),
    (5007, 102,  760000.00, '2026-03-05 13:25:00'),
    (5008, 103, 1750000.00, '2026-03-10 17:05:00');
~~~

### 9.2. Quan sát hash join khi không có index join

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

Không có index trên order_demo.customer_id, nên không có index lookup phù hợp cho điều kiện nối. Trong MySQL 8.0.18 trở lên, hash join có thể được chọn.

Kế hoạch dự kiến có một Inner hash join và các table scan. Vì dữ liệu mẫu rất nhỏ, chi phí ước lượng và phiên bản có thể ảnh hưởng kế hoạch cụ thể; hãy đọc kết quả thực tế thay vì yêu cầu một chuỗi output cố định.

### 9.3. Thêm index cho bảng trong

~~~sql
CREATE INDEX idx_order_customer
ON order_demo (customer_id);
~~~

Chạy truy vấn chọn một khách hàng:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

Index trên order_demo.customer_id cho phép MySQL dùng nested loop với index lookup ở bảng trong. Vì điều kiện lọc chỉ chọn một customer, số lần lookup nhỏ.

### 9.4. So sánh thời gian và số hàng

~~~sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

So sánh với truy vấn hash join ở mục 9.2. Dữ liệu mẫu quá nhỏ để rút ra kết luận hiệu năng tổng quát. Hãy tăng số hàng trong môi trường thử nghiệm, giữ nguyên kết quả nghiệp vụ và đo trên cùng điều kiện tải.

### 9.5. Thử tắt hash join trong session

Có thể lưu cấu hình hiện tại, tắt hash join để quan sát kế hoạch thay thế trên dữ liệu nhỏ:

~~~sql
ALTER TABLE order_demo
DROP INDEX idx_order_customer;

SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'block_nested_loop=off';

EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;

SET SESSION optimizer_switch = @saved_optimizer_switch;

CREATE INDEX idx_order_customer
ON order_demo (customer_id);
~~~

Tắt hash join không có nghĩa MySQL sẽ tự động tạo một index lookup. Nếu không có index phù hợp, kế hoạch thay thế có thể phải dùng nested loop với scan ở bảng trong và rất tốn kém trên dữ liệu lớn.

Chỉ thực hiện phép thử này trên dữ liệu nhỏ hoặc môi trường riêng. Luôn khôi phục optimizer_switch sau thử nghiệm.

## 10. Chọn thuật toán dựa trên workload

| Tình huống | Thuật toán có thể phù hợp | Lý do |
|---|---|---|
| Bảng ngoài được lọc còn ít hàng, bảng trong có index join | NLJ với index lookup | Mỗi hàng ngoài chỉ cần một lookup chọn lọc |
| Hai đầu vào lớn, không có index join phù hợp, điều kiện equality | Hash join | Quét đầu vào và dò hash thay cho lặp lại full scan |
| Có index join nhưng cần gom nhiều key lookup | BKA có thể đáng thử | Batch key kết hợp MRR cải thiện cách truy cập bảng trong |
| Join tạo rất nhiều hàng trùng khóa | Cần kiểm tra cardinality trước | Kích thước kết quả có thể là nút thắt dù thuật toán tốt |
| Hash table vượt join_buffer_size | Hash join có thể spill ra đĩa | I/O bổ sung làm tăng thời gian |
| Bảng nhỏ hoặc dữ liệu nằm trong cache | Nhiều kế hoạch có thể có chi phí gần nhau | Cần đo trên dữ liệu đại diện |

Không có thuật toán tốt nhất cho mọi truy vấn. Một truy vấn join có thể chạy tốt bằng NLJ khi index chọn lọc và chạy kém nếu đầu vào ngoài tăng đột biến. Hash join có thể rất hiệu quả khi thiếu index join, nhưng bị giới hạn bởi bộ nhớ và lượng dữ liệu phải đọc.

## 11. Các lỗi thường gặp khi chẩn đoán join

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Mọi JOIN đều là nested loop | MySQL có thể chọn hash join hoặc biến thể NLJ | Dùng EXPLAIN TREE |
| Hash join luôn nhanh hơn NLJ | NLJ có index lookup có thể rất hiệu quả với đầu vào nhỏ | Đọc join order, index và số hàng |
| Có index bất kỳ là hash join không dùng | Index phải áp dụng được cho điều kiện join; index cho predicate đơn bảng vẫn có thể tồn tại | Kiểm tra index nào hỗ trợ join condition |
| block_nested_loop=on nghĩa server đang dùng BNL | Từ 8.0.20, cờ này điều khiển hash join | Đọc theo phiên bản MySQL |
| hash_join=off là cách tắt hash join trong 8.4 | Cờ hash_join không có tác dụng trong 8.4 | Dùng block_nested_loop=off hoặc NO_BNL |
| Using join buffer luôn là BNL | Có thể là hash join trong phiên bản mới | Đọc phần mô tả cụ thể (hash join) và TREE plan |
| Tăng join_buffer_size luôn cải thiện | Hash join và các join buffer khác có thể tiêu thụ nhiều RAM hơn | Kiểm tra spill, concurrency và I/O |
| EXPLAIN ANALYZE chỉ ước lượng | Lệnh thực sự thực thi SELECT | Dùng trên truy vấn có chi phí chấp nhận được |
| Tắt hash join sẽ ép index lookup | Nếu không có index, NLJ vẫn có thể scan bảng trong lặp lại | Tạo hoặc đánh giá index phù hợp trước |
| BKA và hash join là một | BKA là batch index lookup; hash join dùng hash table | Phân biệt batched_key_access và block_nested_loop |

## 12. Quy trình tối ưu truy vấn JOIN

Khi truy vấn JOIN chậm, làm theo trình tự:

1. Xác định các bảng, điều kiện join và điều kiện lọc.
2. Kiểm tra index trên các cột join, đặc biệt index của bảng trong nếu NLJ được chọn.
3. Chạy EXPLAIN FORMAT=TREE để xác định NLJ hay hash join.
4. Đọc join order và số hàng ước lượng ở từng đầu vào.
5. Chạy EXPLAIN ANALYZE để so sánh actual rows, loops và thời gian.
6. Kiểm tra hash join có spill ra đĩa hoặc NLJ có lookup quá nhiều lần không.
7. Kiểm tra điều kiện join có làm phát sinh many-to-many ngoài dự kiến không.
8. Thử thêm index hoặc thay đổi truy vấn trong môi trường kiểm thử.
9. Nếu cần, thử BKA hoặc thay đổi block_nested_loop ở phạm vi session.
10. Khôi phục cấu hình sau thử nghiệm và đo lại với dữ liệu đại diện.

Sơ đồ ghi nhớ:

~~~mermaid
flowchart TD
    A[Truy vấn JOIN chậm] --> B[EXPLAIN FORMAT=TREE]
    B --> C{Thuật toán đang dùng?}
    C -->|Nested loop| D[Kiểm tra số hàng ngoài và index bảng trong]
    C -->|Hash join| E[Kiểm tra kích thước hai đầu vào và join buffer]
    D --> F{Lookup có chọn lọc?}
    F -->|Không| G[Đánh giá index và join order]
    F -->|Có| H[Đo loops và thời gian thực tế]
    E --> I{Có spill hoặc đầu vào quá lớn?}
    I -->|Có| J[Đo I/O, join_buffer_size và open_files_limit]
    I -->|Không| H
    G --> K[Thử nghiệm thay đổi]
    J --> K
    H --> K
    K --> L[EXPLAIN ANALYZE và so sánh]
~~~

## 13. Bài tập thực hành

### Bài 1: Vẽ nested loop

Dùng hai bảng customer và sales_order. Vẽ vòng lặp ngoài và vòng lặp trong cho câu JOIN theo customer_id. Xác định bảng nào là outer và inner trong kế hoạch thực tế.

### Bài 2: Đánh giá index trên bảng trong

Chạy truy vấn JOIN khi order_demo chưa có index customer_id. Thêm index rồi chạy EXPLAIN TREE. Giải thích thay đổi trong iterator.

### Bài 3: So sánh NLJ và hash join

Chạy cùng truy vấn trên dữ liệu lớn với và không có index join. Ghi lại số hàng, loops và thời gian bằng EXPLAIN ANALYZE.

### Bài 4: Join order

Viết truy vấn có hai điều kiện lọc ở hai bảng. So sánh kế hoạch khi điều kiện lọc ở bảng ngoài chọn lọc hơn và khi dữ liệu phân bố khác nhau.

### Bài 5: Hash join memory

Giữ nguyên truy vấn và thử các giá trị join_buffer_size trong môi trường riêng. Quan sát thời gian và dấu hiệu I/O khi hash join cần xử lý dữ liệu lớn.

### Bài 6: Kiểm tra spill

Tạo dữ liệu lớn hơn khả năng hash table giữ trong bộ nhớ thử nghiệm. Đo thời gian khi hash join phải dùng file trên đĩa. Ghi lại cấu hình open_files_limit.

### Bài 7: BKA

Thêm index trên bảng trong, bật batched_key_access, mrr và mrr_cost_based theo hướng dẫn. Chạy EXPLAIN và xác định optimizer có chọn BKA hay không.

### Bài 8: Thử tắt hash join

Lưu optimizer_switch, tắt block_nested_loop trong session, chạy EXPLAIN trên truy vấn không có index join. So sánh kế hoạch và khôi phục cấu hình ban đầu.

### Bài 9: So sánh phiên bản

Đọc tài liệu MySQL 8.0.18, 8.0.19, 8.0.20 và 8.4. Lập bảng giải thích thay đổi của hash_join, block_nested_loop, BNL và BKA.

### Bài 10: Phân tích truy vấn chậm

Chọn một truy vấn JOIN có thời gian cao. Xác định thuật toán, join order, index, số hàng ước lượng, số hàng thực tế, loops và mức sử dụng bộ nhớ. Đề xuất một thay đổi và chứng minh bằng phép đo.

## Kết luận

Nested-Loop Join đọc hàng từ bảng ngoài rồi tìm hàng phù hợp ở bảng trong. Khi bảng trong có index và đầu vào ngoài nhỏ, NLJ có thể rất hiệu quả. Khi không có index join phù hợp và phải quét nhiều hàng, hash join thường là lựa chọn tốt hơn vì xây dựng bảng băm rồi dò đầu vào còn lại.

Trong MySQL 8.0.18, hash join được giới thiệu; 8.0.19 thay đổi cách điều khiển; 8.0.20 loại bỏ BNL và mở rộng các trường hợp hash join thay thế. Trong MySQL 8.4, block_nested_loop cùng BNL/NO_BNL điều khiển hash join, còn BKA là chiến lược batch index lookup riêng.

Hãy dùng EXPLAIN TREE để nhận diện iterator, EXPLAIN ANALYZE để đo số hàng và vòng lặp, rồi đánh giá index, join order và bộ nhớ. Thuật toán chỉ là một phần của chi phí; cardinality và số hàng đầu ra vẫn quyết định phần lớn công việc mà truy vấn phải thực hiện.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Nested-Loop Join Algorithms: https://dev.mysql.com/doc/refman/8.4/en/nested-loop-joins.html
- MySQL 8.4 Reference Manual — Hash Join Optimization: https://dev.mysql.com/doc/refman/8.4/en/hash-joins.html
- MySQL 8.4 Reference Manual — Block Nested-Loop and Batched Key Access Joins: https://dev.mysql.com/doc/refman/8.4/en/bnl-bka-optimization.html
- MySQL 8.4 Reference Manual — Switchable Optimizations: https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html
- MySQL 8.4 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html
- MySQL 8.4 Reference Manual — Server System Variables (join_buffer_size, open_files_limit): https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- MySQL 8.0 Reference Manual — What Is New in MySQL 8.0: https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html

