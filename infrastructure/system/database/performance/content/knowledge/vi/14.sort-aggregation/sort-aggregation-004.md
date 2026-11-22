# GROUP BY với tổng hợp băm hoặc tổng hợp theo thứ tự

Khi một truy vấn dùng GROUP BY, hệ quản trị phải gom các dòng có cùng khóa nhóm và tính các giá trị tổng hợp như COUNT, SUM, AVG, MIN hoặc MAX. Có nhiều cách thực hiện công việc này. Hai chiến lược phổ biến là tổng hợp băm (hash aggregation) và tổng hợp theo thứ tự (sort-based hoặc stream aggregation). Chúng tạo cùng kết quả logic nhưng có yêu cầu khác nhau về thứ tự đầu vào, bộ nhớ, I/O và số nhóm cần xử lý.

Trong phạm vi **DATABASE_PERFORMANCE**, việc tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Với GROUP BY, cần hiểu optimizer chọn thuật toán dựa trên số dòng, số nhóm ước lượng, thứ tự dữ liệu và tài nguyên ra sao. Một kế hoạch Hash Aggregate không mặc nhiên tốt hơn Sort/Group Aggregate; ngược lại, một bước Sort cũng không phải lúc nào là chi phí dư thừa.

Bài học này trình bày nguyên lý của hai chiến lược, điều kiện phù hợp, cách chỉ mục hỗ trợ tổng hợp, cách nhận diện tràn bộ nhớ ra đĩa và cách kiểm chứng lựa chọn của optimizer trên workload thực tế.

## 1. GROUP BY và phép tổng hợp

GROUP BY chia tập dòng đầu vào thành các nhóm dựa trên một hoặc nhiều biểu thức. Mỗi nhóm tạo ra một dòng kết quả, trong đó các hàm tổng hợp tính toán trên các dòng thuộc nhóm đó.

Ví dụ, bảng sales có các cột sale_id, region, product_id, quantity và amount. Truy vấn sau tính doanh thu và số giao dịch theo khu vực:

~~~sql
SELECT
    region,
    COUNT(*) AS transaction_count,
    SUM(amount) AS revenue,
    AVG(amount) AS average_amount
FROM sales
GROUP BY region;
~~~

Nếu bảng có 50 triệu dòng nhưng chỉ 8 region, kết quả chỉ có 8 nhóm. Hệ quản trị phải đọc các dòng đầu vào, xác định nhóm tương ứng và cập nhật các giá trị tổng hợp.

Một truy vấn có thể nhóm theo nhiều cột:

~~~sql
SELECT
    region,
    product_id,
    SUM(quantity) AS units_sold,
    SUM(amount) AS revenue
FROM sales
GROUP BY region, product_id;
~~~

Số nhóm có thể lớn hơn rất nhiều. Nếu có hàng trăm region và hàng triệu product_id, số tổ hợp thực tế có thể lên đến hàng triệu. Số nhóm này ảnh hưởng trực tiếp đến bộ nhớ cần cho hash aggregation và lượng công việc của sort-based aggregation.

### Các khái niệm cần phân biệt

- **Input rows:** số dòng được đưa vào toán tử tổng hợp sau các bước lọc và nối.
- **Group key:** một hoặc nhiều cột/biểu thức xác định một nhóm.
- **Number of groups (NDV):** số giá trị khác nhau hoặc số tổ hợp khóa nhóm.
- **Aggregate state:** trạng thái tạm được duy trì cho từng nhóm, ví dụ tổng hiện tại và số lượng dòng.
- **Output rows:** số nhóm được tạo ra.
- **HAVING:** điều kiện lọc nhóm sau khi các giá trị tổng hợp đã được tính.

Số dòng đầu vào và số nhóm đầu ra là hai đại lượng khác nhau. Một bảng lớn có thể có rất ít nhóm; một bảng nhỏ hơn có thể có số nhóm gần bằng số dòng.

## 2. Tổng hợp băm (Hash Aggregate)

Hash aggregation dùng cấu trúc bảng băm để gom các dòng theo group key. Với mỗi dòng đầu vào, hệ quản trị tính giá trị băm từ khóa nhóm, tìm hoặc tạo entry tương ứng, rồi cập nhật trạng thái của các hàm tổng hợp.

Quy trình khái quát:

~~~text
Đọc một dòng đầu vào
        |
        v
Tính hash từ group key
        |
        v
Tìm entry trong hash table
        |
   +----+----+
   |         |
 Đã có     Chưa có
   |         |
   v         v
Cập nhật   Tạo entry
aggregate  và khởi tạo state
   |         |
   +----+----+
        |
        v
   Đọc dòng tiếp theo
        |
        v
  Xuất một dòng cho mỗi nhóm
~~~

Ví dụ, với GROUP BY region, hash table có một entry cho mỗi region xuất hiện. Khi đọc một dòng có region = 'NORTH', hệ quản trị tìm entry NORTH và cộng amount vào tổng tương ứng.

### Chi phí của Hash Aggregate

Hash Aggregate thường cần:

- Đọc toàn bộ dòng đầu vào.
- Tính hash cho từng group key.
- Tìm hoặc tạo entry trong hash table.
- Giữ trạng thái tổng hợp cho tất cả nhóm đang được xử lý.
- Xử lý va chạm hash và mở rộng cấu trúc khi cần.

Nếu số nhóm ít và aggregate state nhỏ, hash table có thể vừa trong bộ nhớ. Khi đó, hệ quản trị không cần sắp xếp toàn bộ đầu vào theo group key.

Nếu số nhóm lớn, khóa nhóm rộng hoặc aggregate state chiếm nhiều bộ nhớ, hash table có thể vượt ngân sách bộ nhớ. Tùy hệ quản trị, toán tử có thể chia dữ liệu thành nhiều batch, ghi dữ liệu trung gian ra vùng tạm hoặc xin memory grant lớn hơn. Spill ra đĩa làm tăng I/O và thời gian thực thi.

### Hash Aggregate không bảo đảm thứ tự kết quả

Hash table tổ chức dữ liệu theo hash chứ không theo thứ tự khóa. Kết quả có thể được xuất theo thứ tự nội bộ không ổn định. Nếu ứng dụng cần thứ tự cụ thể, phải chỉ định ORDER BY:

~~~sql
SELECT
    region,
    SUM(amount) AS revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Optimizer có thể phải thêm Sort sau Hash Aggregate. Không dựa vào thứ tự tình cờ quan sát được khi truy vấn không có ORDER BY.

## 3. Tổng hợp theo thứ tự (Sort-Based hoặc Stream Aggregate)

Tổng hợp theo thứ tự xử lý các dòng đã được sắp xếp theo group key. Khi các dòng cùng khóa nằm liên tiếp, hệ quản trị chỉ cần giữ trạng thái của nhóm hiện tại. Khi group key thay đổi, nó xuất kết quả nhóm trước và bắt đầu nhóm mới.

Ví dụ đầu vào đã được sắp xếp theo region:

~~~text
NORTH, 100
NORTH, 250
NORTH,  80
SOUTH, 120
SOUTH,  90
WEST,  300
~~~

Toán tử đọc lần lượt:

- Với NORTH, cộng 100 + 250 + 80.
- Khi gặp SOUTH, xuất kết quả NORTH và bắt đầu nhóm SOUTH.
- Khi gặp WEST, xuất SOUTH và bắt đầu nhóm WEST.
- Cuối đầu vào, xuất nhóm cuối cùng.

~~~text
Dòng đã sắp xếp theo group key
              |
              v
     Đọc liên tiếp từng dòng
              |
              v
       Cùng group key?
          /       \
        Có         Không
        |             |
        v             v
   Cập nhật       Xuất nhóm cũ,
   aggregate      khởi tạo nhóm mới
          \       /
              v
       Kết quả nhóm
~~~

### Khi nào cần Sort trước?

Nếu đầu vào chưa được sắp xếp theo group key, hệ quản trị có thể phải thực hiện một bước Sort rồi mới chạy Stream Aggregate hoặc Group Aggregate.

~~~text
Table Scan
    |
    v
  Sort by region
    |
    v
Stream / Group Aggregate
    |
    v
  Result
~~~

Sort có thể tiêu tốn CPU, bộ nhớ và I/O tạm, đặc biệt khi đầu vào lớn. Tuy nhiên, nếu dữ liệu đã có thứ tự phù hợp từ index scan, merge join hoặc một toán tử trước đó, bước Sort riêng có thể được loại bỏ.

### Lợi thế về bộ nhớ

Với tổng hợp theo thứ tự đơn giản, toán tử có thể chỉ cần giữ trạng thái của nhóm hiện tại thay vì một entry cho mọi nhóm. Bộ nhớ của chính toán tử tổng hợp có thể nhỏ hơn Hash Aggregate.

Dù vậy, nếu cần Sort đầu vào, thao tác sắp xếp vẫn cần bộ nhớ để giữ dữ liệu và có thể spill ra đĩa. Vì vậy, không nên kết luận sort-based aggregation luôn ít tốn bộ nhớ hơn nếu phải tính cả bước Sort.

### Đầu ra có thứ tự không thay thế ORDER BY

Stream Aggregate thường nhận dữ liệu theo group key và có thể xuất các nhóm theo thứ tự đó. Tuy nhiên, hợp đồng SQL vẫn không bảo đảm thứ tự kết quả nếu thiếu ORDER BY. Nếu thứ tự là yêu cầu của ứng dụng, hãy khai báo rõ ràng.

## 4. So sánh Hash Aggregate và Sort/Stream Aggregate

| Tiêu chí | Hash Aggregate | Sort/Stream Aggregate |
|---|---|---|
| Thứ tự đầu vào | Không cần sắp xếp theo group key | Cần đầu vào có thứ tự theo group key |
| Cách gom nhóm | Hash table, một entry cho mỗi nhóm | Xử lý tuần tự các nhóm liền kề |
| Bộ nhớ tổng hợp | Tăng theo số nhóm và kích thước state | Thường giữ state của nhóm hiện tại |
| Chi phí Sort | Không cần sort chỉ để nhóm | Có thể cần Sort nếu đầu vào chưa có thứ tự |
| Spill | Hash table có thể chia batch hoặc ghi dữ liệu tạm | Sort có thể spill nếu vượt bộ nhớ |
| Độ phù hợp | Đầu vào chưa có thứ tự, số nhóm vừa phải và hash table vừa bộ nhớ | Đầu vào đã có thứ tự hoặc index có thể cung cấp thứ tự rẻ |
| Thứ tự kết quả | Không bảo đảm theo group key | Có thể xuất theo thứ tự đầu vào, nhưng SQL vẫn cần ORDER BY để bảo đảm |
| Tài nguyên đáng theo dõi | Hash memory, số nhóm, batch, temp I/O | Sort memory, sort method, disk spill, temp I/O |

Lựa chọn phụ thuộc tổng chi phí của toàn kế hoạch. Hash Aggregate có thể tốt hơn khi tránh được một lần sort lớn và số nhóm vừa phải. Stream Aggregate có thể tốt hơn khi đầu vào đã được sắp xếp hoặc index cung cấp thứ tự mà không phải đọc quá nhiều trang.

## 5. Optimizer chọn thuật toán dựa trên điều gì?

Optimizer ước lượng chi phí của các phương án dựa trên thống kê và mô hình chi phí. Với GROUP BY, những yếu tố quan trọng gồm:

### Số dòng đầu vào

Số dòng sau WHERE, JOIN và các bước lọc quyết định lượng dữ liệu cần tổng hợp. Nếu truy vấn có thể loại bỏ phần lớn dòng trước khi GROUP BY, chi phí của cả hai phương án có thể giảm đáng kể.

### Số nhóm ước lượng

Số nhóm là yếu tố quan trọng đối với Hash Aggregate. Hash table cần entry cho từng group key. Nếu optimizer đánh giá thấp số nhóm, nó có thể dự đoán bộ nhớ thấp hơn thực tế.

Với Stream Aggregate, số nhóm ảnh hưởng số lần xuất kết quả và trạng thái chuyển nhóm, nhưng chi phí Sort thường phụ thuộc mạnh vào số dòng và độ rộng dữ liệu đầu vào.

### Độ rộng của dòng và khóa nhóm

Group key gồm nhiều cột, chuỗi dài hoặc kiểu dữ liệu lớn có thể làm hash entry lớn hơn. Các aggregate state như DISTINCT hoặc một số hàm tổng hợp đặc biệt có thể cần thêm cấu trúc lưu trữ.

### Thứ tự dữ liệu sẵn có

Nếu một index scan cung cấp dữ liệu theo group key, Stream Aggregate có thể tránh Sort. Nếu đầu vào là kết quả join đã được sắp xếp, optimizer có thể tận dụng thứ tự đó.

### Bộ nhớ khả dụng và mức đồng thời

Một hash table vừa bộ nhớ khi chạy riêng có thể gây áp lực khi nhiều truy vấn cùng chạy. Memory grant hoặc work memory được cấp cho từng toán tử cần được đánh giá cùng số phiên đồng thời.

### Yêu cầu thứ tự và các toán tử phía sau

Nếu truy vấn cần ORDER BY theo group key, sort-based plan có thể tái sử dụng thứ tự. Nếu bước sau cần thứ tự khác, vẫn có thể phải sort thêm. Hãy đánh giá toàn bộ kế hoạch thay vì chỉ nhìn node Aggregate.

## 6. Cardinality estimation và số nhóm

Cardinality estimation là việc optimizer ước lượng số dòng tại mỗi bước. Với GROUP BY, optimizer còn cần ước lượng số nhóm khác nhau.

Giả sử bảng sales có 100 triệu dòng:

- GROUP BY region có thể chỉ tạo 10 nhóm.
- GROUP BY customer_id có thể tạo 5 triệu nhóm.
- GROUP BY region, product_id có thể tạo 20 triệu tổ hợp nhóm.

Ba truy vấn đọc cùng bảng nhưng nhu cầu bộ nhớ và chi phí xử lý rất khác nhau.

### Thống kê hỗ trợ ước lượng

Hệ quản trị có thể dùng:

- Số lượng giá trị khác nhau (distinct count).
- Histogram và tần suất giá trị phổ biến.
- Số dòng bảng và số dòng sau điều kiện lọc.
- Thống kê nhiều cột hoặc extended statistics.
- Ràng buộc unique và quan hệ phụ thuộc giữa các cột.

Nếu các cột group key tương quan mạnh, việc nhân số giá trị khác nhau một cách độc lập có thể làm ước lượng số nhóm sai lệch.

Ví dụ, mỗi tenant chỉ có một region. Nếu GROUP BY tenant_id, region, số nhóm thực tế có thể gần số tenant; ước lượng độc lập từ distinct tenant và distinct region có thể cao hơn đáng kể.

### Dấu hiệu ước lượng sai

- Estimated rows tại node Aggregate khác xa actual rows.
- Hash Aggregate có số nhóm thực tế lớn hơn nhiều dự kiến.
- Kế hoạch cấp phát bộ nhớ quá nhỏ và spill.
- Optimizer chọn Hash Aggregate nhưng thực tế số nhóm cao, trong khi một thứ tự đầu vào có thể giúp Stream Aggregate hiệu quả hơn.
- Hoặc ngược lại, optimizer chọn Sort/Group Aggregate và Sort rất lớn dù số nhóm ít và Hash Aggregate có thể phù hợp.

Khi thấy sai lệch, kiểm tra thống kê trước khi thay đổi cấu hình bộ nhớ hoặc ép thuật toán. Cập nhật thống kê có thể cải thiện ước lượng, nhưng cần kiểm tra xem thống kê hiện có có mô tả đủ phân bố và tương quan hay không.

## 7. Chỉ mục có thể hỗ trợ GROUP BY như thế nào?

Một chỉ mục có thứ tự phù hợp với group key có thể cung cấp đầu vào đã sắp xếp cho Stream Aggregate. Điều này có thể loại bỏ bước Sort.

Ví dụ truy vấn:

~~~sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE tenant_id = 42
GROUP BY tenant_id, status;
~~~

Một B-tree index có thể được cân nhắc:

~~~sql
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status);
~~~

Vì tenant_id được cố định bởi điều kiện bằng, các dòng trong phạm vi tenant có thể được đọc theo thứ tự status. Hệ quản trị có thể dùng thứ tự đó để nhóm theo tenant_id, status mà không cần Sort riêng, nếu optimizer đánh giá access path này có chi phí thấp.

### Chỉ mục bao phủ

Trong PostgreSQL, có thể thêm cột phục vụ tổng hợp bằng INCLUDE:

~~~sql
CREATE INDEX idx_orders_tenant_status_cover
ON orders (tenant_id, status)
INCLUDE (total_amount);
~~~

Điều này có thể giúp index-only scan nếu các điều kiện visibility map cho phép. INCLUDE không làm total_amount trở thành khóa sắp xếp; nó chỉ lưu giá trị để truy xuất từ leaf entry.

Với MySQL InnoDB, secondary index lưu kèm primary key nên cách thiết kế covering index khác. Không áp dụng cú pháp INCLUDE của PostgreSQL cho MySQL.

### Khi index không có lợi

Nếu truy vấn phải đọc phần lớn bảng, index scan có thể tạo nhiều truy cập ngẫu nhiên. Sequential scan rồi Hash Aggregate có thể rẻ hơn. Index cũng có chi phí dung lượng, cache và ghi. Vì vậy, không nên tạo index chỉ vì thấy GROUP BY.

### Thứ tự cột phải phù hợp với điều kiện lọc

Index (tenant_id, status) có thể hỗ trợ nhóm theo status khi tenant_id được cố định. Nhưng nếu truy vấn nhóm theo status trên toàn bộ tenant và không lọc tenant_id, index này không nhất thiết cung cấp thứ tự hữu ích toàn cục theo status.

Hãy xét tiền tố trái, điều kiện bằng, điều kiện phạm vi và thứ tự group key. Các hệ quản trị có thể có khả năng skip scan hoặc chiến lược khác ở một số phiên bản, nhưng không nên giả định chúng luôn áp dụng.

## 8. WHERE, HAVING và giảm dữ liệu trước tổng hợp

WHERE lọc dòng trước khi nhóm; HAVING lọc nhóm sau khi tính aggregate.

Ví dụ:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM payments
WHERE payment_date >= DATE '2026-01-01'
GROUP BY customer_id
HAVING SUM(amount) > 100000;
~~~

WHERE giảm số dòng đầu vào của Aggregate. HAVING cần giá trị tổng hợp nên được áp dụng sau khi nhóm, trừ khi optimizer có thể biến đổi điều kiện một cách tương đương.

Nếu điều kiện chỉ dựa trên group key, có thể biểu đạt bằng WHERE để lọc sớm:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM payments
WHERE payment_date >= DATE '2026-01-01'
  AND customer_id >= 1000
GROUP BY customer_id;
~~~

Không chuyển một điều kiện HAVING sang WHERE nếu nó phụ thuộc kết quả tổng hợp hoặc nếu việc chuyển làm thay đổi ngữ nghĩa.

### Chọn cột trước khi tổng hợp

Chỉ truyền những cột cần cho group key và aggregate vào các bước xử lý sau. Dòng rộng làm tăng bộ nhớ sort, hash và I/O tạm. Một subquery hoặc CTE có thể giúp tổ chức SQL, nhưng không nên mặc định rằng nó luôn materialize hoặc luôn được inline; hành vi phụ thuộc hệ quản trị và phiên bản.

## 9. Tổng hợp song song (Parallel Aggregation)

Một số hệ quản trị có thể chia công việc tổng hợp cho nhiều worker. Thay vì một tiến trình xử lý toàn bộ đầu vào, mỗi worker đọc một phần dữ liệu và tính kết quả trung gian.

Trong PostgreSQL, kế hoạch song song có thể gồm:

- **Partial Aggregate:** mỗi worker tính trạng thái tổng hợp cho phần dữ liệu của mình.
- **Gather hoặc Gather Merge:** thu thập kết quả từ các worker.
- **Finalize Aggregate:** kết hợp các trạng thái trung gian để tạo kết quả cuối.

Ví dụ khái niệm:

~~~text
Worker 1: đọc phần dữ liệu 1 -> Partial Aggregate
Worker 2: đọc phần dữ liệu 2 -> Partial Aggregate
Worker 3: đọc phần dữ liệu 3 -> Partial Aggregate
                         |
                         v
                       Gather
                         |
                         v
                 Finalize Aggregate
                         |
                         v
                    Kết quả cuối
~~~

Parallel aggregation có thể tăng throughput khi bảng lớn và CPU còn năng lực. Tuy nhiên, nó cũng có chi phí:

- Khởi tạo worker và điều phối.
- Tổng hợp cục bộ ở từng worker.
- Truyền trạng thái trung gian.
- Tổng hợp cuối.
- Bộ nhớ được sử dụng đồng thời bởi nhiều worker.

Nếu số nhóm rất lớn, mỗi worker có thể tạo nhiều trạng thái riêng, khiến tổng dữ liệu trung gian tăng. Nếu bảng nhỏ hoặc truy vấn trả ít dòng, chi phí parallelism có thể lớn hơn lợi ích.

Không phải mọi hàm tổng hợp hoặc biểu thức đều có thể kết hợp song song trong mọi hệ quản trị. Cần xem plan và khả năng của phiên bản.

## 10. GROUP BY với DISTINCT và nhiều aggregate

Một truy vấn có thể dùng nhiều aggregate trên cùng nhóm:

~~~sql
SELECT
    region,
    COUNT(*) AS row_count,
    COUNT(customer_id) AS customer_values,
    COUNT(DISTINCT customer_id) AS unique_customers,
    SUM(amount) AS revenue,
    MAX(amount) AS largest_sale
FROM sales
GROUP BY region;
~~~

COUNT(*) đếm tất cả dòng trong nhóm. COUNT(customer_id) bỏ qua NULL. COUNT(DISTINCT customer_id) đếm số giá trị khác nhau không NULL trong mỗi nhóm.

DISTINCT thường cần thêm công việc để xác định các giá trị duy nhất. Tùy hệ quản trị, thuật toán có thể dùng hash, sort hoặc cấu trúc trung gian khác. Một Hash Aggregate bên ngoài không có nghĩa mọi aggregate DISTINCT bên trong đều không phát sinh thêm chi phí.

Nếu có nhiều biểu thức DISTINCT khác nhau, bộ nhớ và công việc xử lý có thể tăng. Hãy xem plan chi tiết, temp I/O và thời gian thực tế.

### NULL trong phép tổng hợp

- COUNT(*) đếm cả dòng có giá trị NULL.
- COUNT(expression) chỉ đếm giá trị expression khác NULL.
- SUM, AVG, MIN và MAX thường bỏ qua giá trị NULL; nếu không có giá trị hợp lệ, kết quả có thể là NULL.
- GROUP BY thường gom các dòng có group key NULL vào cùng một nhóm.

Cần hiểu ngữ nghĩa này khi viết lại truy vấn hoặc tiền tổng hợp. Thay COUNT(*) bằng COUNT(column) có thể làm thay đổi kết quả nếu column cho phép NULL.

## 11. Tổng hợp theo nhiều cấp: ROLLUP, CUBE và GROUPING SETS

Một số hệ quản trị hỗ trợ tạo nhiều cấp tổng hợp trong một truy vấn.

Ví dụ:

~~~sql
SELECT
    region,
    product_category,
    SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product_category);
~~~

ROLLUP có thể tạo kết quả theo nhóm region và product_category, subtotal theo region và tổng toàn bộ. CUBE tạo các tổ hợp tổng hợp theo nhiều chiều; GROUPING SETS cho phép chỉ định rõ các tập khóa nhóm cần tính.

Các tính năng này có thể tiết kiệm nhiều lần quét bảng so với chạy từng truy vấn riêng, nhưng số nhóm đầu ra và trạng thái tổng hợp có thể tăng. Khi đọc kết quả, cần phân biệt giá trị NULL tự nhiên trong dữ liệu với NULL được tạo ra để biểu diễn subtotal; hàm GROUPING có thể giúp nhận biết tùy hệ quản trị.

Không nên dùng CUBE trên nhiều chiều mà không ước lượng số grouping sets và quy mô kết quả. Số tổ hợp có thể tăng rất nhanh theo số chiều.

## 12. Spill ra đĩa và áp lực bộ nhớ

Hash Aggregate và Sort đều có thể vượt ngân sách bộ nhớ. Spill là hiện tượng dữ liệu trung gian phải được ghi ra lưu trữ tạm để hoàn thành thao tác.

### Hash Aggregate spill

Hash Aggregate cần giữ trạng thái của các nhóm. Nếu số nhóm hoặc kích thước aggregate state lớn hơn dự kiến, hệ quản trị có thể chia dữ liệu thành nhiều batch hoặc ghi dữ liệu tạm. Việc xử lý nhiều batch làm tăng đọc/ghi và có thể khiến truy vấn chậm hơn đáng kể.

Các dấu hiệu cần xem:

- HashAgg batches hoặc số batch lớn hơn một.
- Disk usage hoặc temp blocks tăng.
- Temp read/write xuất hiện.
- Execution time tăng mạnh khi số nhóm tăng.
- Estimated groups khác actual groups đáng kể.

### Sort spill

Sort cần bộ nhớ để giữ và sắp xếp các dòng. Khi dữ liệu không vừa bộ nhớ, hệ quản trị có thể tạo các run đã sắp xếp trên đĩa rồi merge chúng. Spill làm tăng I/O tạm và CPU.

Các dấu hiệu gồm:

- Sort Method có thông tin external merge hoặc disk.
- Disk usage hoặc temp file lớn.
- Temp read/write tăng.
- Sort node chiếm phần đáng kể thời gian truy vấn.

### Cấu hình bộ nhớ theo hệ quản trị

PostgreSQL sử dụng work_mem làm ngân sách cho một số thao tác sort và hash; hash operation còn chịu ảnh hưởng của hash_mem_multiplier ở các phiên bản hỗ trợ. work_mem không phải giới hạn RAM cho toàn bộ server. Một truy vấn có thể có nhiều node cần bộ nhớ và nhiều phiên có thể chạy đồng thời.

SQL Server dùng memory grant cho một số operator như Sort và Hash Match. Grant quá nhỏ có thể dẫn đến spill vào tempdb; grant quá lớn có thể làm giảm số truy vấn chạy đồng thời hoặc gây áp lực bộ nhớ.

MySQL có thể sử dụng cấu trúc bảng tạm nội bộ và các chiến lược sort cho GROUP BY. Khi bảng tạm vượt giới hạn hoặc không thể giữ trong bộ nhớ theo cơ chế của phiên bản, dữ liệu có thể được lưu trên đĩa. Các tham số và thuật toán phụ thuộc phiên bản, storage engine và dạng truy vấn.

Không tăng bộ nhớ chỉ để làm một truy vấn đơn lẻ nhanh hơn. Hãy đo tổng số truy vấn đồng thời, memory grant, temp I/O và mức dùng RAM trước khi điều chỉnh.

## 13. Nhận diện toán tử tổng hợp trong execution plan

Tên toán tử khác nhau giữa các hệ quản trị.

| Hệ quản trị | Tổng hợp băm | Tổng hợp theo thứ tự |
|---|---|---|
| PostgreSQL | HashAggregate, Partial HashAggregate | GroupAggregate, thường cần input đã sắp xếp |
| SQL Server | Hash Match (Aggregate) | Stream Aggregate |
| Oracle | HASH GROUP BY | SORT GROUP BY |
| MySQL | Có thể dùng temporary table và/hoặc chiến lược dựa trên thứ tự/index; tên hiển thị phụ thuộc EXPLAIN và phiên bản | Có thể dùng index order hoặc filesort/temp table |

Đừng chỉ tìm một tên node. Hãy đọc cả các node phía trước và sau để xác định dữ liệu đã được lọc, sắp xếp hoặc materialize ở đâu.

### Ví dụ PostgreSQL

Chạy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01'
GROUP BY tenant_id, status;
~~~

Một kế hoạch có thể dùng HashAggregate sau khi scan các dòng phù hợp. Kế hoạch khác có thể dùng Sort theo tenant_id, status rồi GroupAggregate. Optimizer chọn dựa trên chi phí ước lượng, thống kê, thứ tự sẵn có và bộ nhớ.

Khi đọc output, xem:

- Estimated rows và actual rows của node input.
- Số nhóm ước lượng và số dòng output thực tế.
- Hash batches, memory usage hoặc disk usage nếu được hiển thị.
- Sort Method, memory và disk nếu có.
- Buffers hit/read và temp blocks.
- Planning Time, Execution Time và số loops.

### Ví dụ SQL Server

Trong Actual Execution Plan, quan sát:

- Hash Match (Aggregate): dùng hash để nhóm.
- Stream Aggregate: yêu cầu dữ liệu theo thứ tự group key.
- Sort: bước tạo thứ tự trước Stream Aggregate.
- Memory Grant, spill warning và thông tin tempdb.
- Actual Number of Rows so với Estimated Number of Rows.

### Ví dụ MySQL

Dùng EXPLAIN và EXPLAIN ANALYZE nếu phiên bản hỗ trợ. Kiểm tra:

- Có dùng index để phục vụ GROUP BY không?
- Có Using temporary hoặc Using filesort trong Extra không?
- Số dòng đọc và số dòng còn lại sau điều kiện lọc.
- Thời gian thực tế và iterator nào chiếm nhiều công việc.
- Internal temporary table có phải chuyển ra đĩa không, nếu có công cụ giám sát phù hợp.

Using temporary hoặc Using filesort không tự động đồng nghĩa truy vấn kém. Hãy xét kích thước dữ liệu, thời gian và chi phí tổng thể.

## 14. Ví dụ lựa chọn Hash Aggregate hay Stream Aggregate

Giả sử bảng orders có 120 triệu dòng, với tenant_id, status và total_amount. Ứng dụng có hai mẫu truy vấn.

### Mẫu A: nhóm theo trạng thái của một tenant

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE tenant_id = 42
GROUP BY status;
~~~

Nếu tenant_id chọn một phần nhỏ bảng và có index (tenant_id, status) INCLUDE (total_amount), hệ quản trị có thể đọc phạm vi tenant theo thứ tự status. Stream/Group Aggregate có thể tận dụng thứ tự này và tránh Sort.

Nếu chỉ mục không tồn tại hoặc chi phí index scan cao, Hash Aggregate sau khi quét phần dữ liệu phù hợp vẫn có thể rẻ hơn.

### Mẫu B: nhóm toàn bộ đơn theo tenant và trạng thái

~~~sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY tenant_id, status;
~~~

Truy vấn này có thể đọc gần như toàn bộ bảng và tạo số nhóm lớn. Hash Aggregate tránh bước sort nhưng cần hash table lớn; nếu spill nhiều batch, chi phí temp I/O có thể cao.

Nếu dữ liệu đã được tổ chức theo tenant_id, status hoặc một index phù hợp cung cấp thứ tự với chi phí hợp lý, Stream Aggregate có thể cạnh tranh. Tuy nhiên, đọc toàn bộ index rộng có thể đắt hơn table scan. Cần so sánh kế hoạch thực tế.

Hai truy vấn có cùng bảng và hàm tổng hợp nhưng có đặc điểm đầu vào khác nhau. Không thể chọn một thuật toán tối ưu cho mọi GROUP BY trong hệ thống.

## 15. Tối ưu truy vấn tổng hợp theo workload

Một số hướng có thể giảm công việc trước khi đổi thuật toán:

### Lọc càng sớm càng tốt khi ngữ nghĩa cho phép

Đặt điều kiện lọc trên dòng nguồn trong WHERE để giảm số dòng vào Aggregate. Dùng khoảng thời gian có ranh giới rõ ràng thay vì áp dụng hàm lên cột nếu điều đó làm mất khả năng dùng index hoặc partition pruning.

### Chọn đúng group key

Không thêm cột vào GROUP BY nếu nghiệp vụ không cần phân biệt chúng. Mỗi cột bổ sung có thể làm số nhóm tăng và thay đổi kết quả logic.

### Tránh truyền cột rộng không cần thiết

Không dùng SELECT * trong truy vấn tổng hợp. Chỉ giữ group key và biểu thức aggregate cần thiết để giảm kích thước dữ liệu trung gian.

### Cân nhắc pre-aggregation

Nếu một bảng chi tiết rất lớn được nối với bảng khác, đôi khi có thể tổng hợp trước theo khóa nối rồi mới join. Điều này có thể giảm số dòng tham gia join, nhưng chỉ đúng khi phép biến đổi bảo toàn ngữ nghĩa.

Ví dụ, tổng hợp amount theo order_id trước khi nối với orders có thể giảm dữ liệu nếu bảng chi tiết có nhiều dòng mỗi đơn. Nhưng nếu truy vấn cần phân nhóm theo thuộc tính từng dòng chi tiết, hoặc phép nối làm nhân bản dòng, việc đẩy aggregate lên trước có thể làm thay đổi kết quả.

Luôn so sánh số dòng và kết quả logic trước/sau khi viết lại.

### Dùng summary table hoặc materialized view khi phù hợp

Nếu cùng một phép tổng hợp được chạy thường xuyên trên dữ liệu ít thay đổi, có thể cân nhắc summary table hoặc materialized view. Điều này chuyển một phần chi phí từ thời điểm truy vấn sang thời điểm cập nhật dữ liệu hoặc refresh.

Cần tính chi phí duy trì, độ trễ dữ liệu, tính nhất quán, lịch refresh và xử lý cập nhật tăng/giảm. Materialization không làm chi phí biến mất; nó thay đổi thời điểm và cách phân bổ chi phí.

### Tránh ép thuật toán khi chưa có bằng chứng

Hint hoặc cấu hình planner có thể hữu ích trong tình huống đã hiểu rõ và cần kiểm soát, nhưng có thể làm kế hoạch kém khi dữ liệu tăng hoặc phân bố thay đổi. Ưu tiên sửa thống kê, điều kiện truy vấn và access path trước khi cố định thuật toán.

## 16. Quy trình điều tra GROUP BY chậm

Có thể thực hiện theo trình tự sau:

1. **Xác định workload:** ghi lại câu SQL, tần suất gọi, tham số, p50/p95/p99 và mức tải.
2. **Đo đầu vào:** xác định số dòng sau WHERE và JOIN trước khi tổng hợp.
3. **Ước lượng số nhóm:** đo hoặc kiểm tra thống kê về distinct/group key và tương quan giữa các cột.
4. **Đọc execution plan:** xác định Hash Aggregate hay Group/Stream Aggregate, có Sort hay không.
5. **Kiểm tra ước lượng:** so sánh estimated rows/groups với actual rows/output.
6. **Kiểm tra bộ nhớ:** xem hash memory, memory grant, sort memory, batch, spill và temp I/O.
7. **Kiểm tra thứ tự có sẵn:** xem index scan hoặc toán tử trước có thể cung cấp group key order không.
8. **Kiểm tra chỉ mục:** đánh giá composite/covering index và chi phí ghi.
9. **Đưa ra giả thuyết:** ví dụ số nhóm cao hơn ước lượng, Sort spill, hoặc WHERE chưa lọc đủ sớm.
10. **Thử thay đổi có kiểm soát:** cập nhật thống kê, điều chỉnh index, viết lại SQL hoặc điều chỉnh bộ nhớ sau khi tính concurrency.
11. **Đo lại:** dùng cùng dữ liệu, tham số và mức tải; so sánh latency, CPU, I/O, temp I/O và throughput.
12. **Kiểm tra tác động phụ:** xem truy vấn khác, thời gian ghi, RAM và số phiên đồng thời.

## 17. Những sai lầm thường gặp

- **Cho rằng Hash Aggregate luôn nhanh hơn:** hash table lớn có thể spill và tạo I/O tạm.
- **Cho rằng Stream Aggregate luôn ít tốn bộ nhớ:** nếu phải Sort toàn bộ đầu vào, bước sort có thể cần bộ nhớ lớn và spill.
- **Chỉ nhìn số dòng đầu vào:** số nhóm và kích thước group key quyết định đáng kể chi phí hash.
- **Bỏ qua thứ tự do index cung cấp:** có thể tồn tại access path tránh Sort mà chưa được xem xét.
- **Tạo index chỉ vì có GROUP BY:** index có chi phí ghi và có thể không được dùng nếu phải đọc phần lớn bảng.
- **Tăng work_mem hoặc memory grant theo một truy vấn:** nhiều phiên đồng thời có thể làm tổng mức dùng bộ nhớ quá cao.
- **Nhầm Using temporary hoặc filesort với lỗi:** cần đo chi phí thực tế và lượng dữ liệu.
- **Dùng HAVING thay cho WHERE khi điều kiện lọc dòng:** có thể làm tăng số dòng phải tổng hợp.
- **Thêm cột vào GROUP BY mà không xem kết quả:** có thể làm số nhóm tăng và thay đổi ý nghĩa báo cáo.
- **Bỏ qua COUNT(column) và COUNT(*):** NULL khiến hai biểu thức cho kết quả khác nhau.
- **Tổng hợp trước JOIN một cách máy móc:** có thể làm thay đổi số dòng hoặc kết quả khi quan hệ là một-nhiều.
- **So sánh hai kế hoạch ở trạng thái cache và tải khác nhau:** kết luận benchmark không đáng tin cậy.

## 18. Checklist kiểm chứng tổng hợp

Trước khi kết luận cần tối ưu GROUP BY, hãy trả lời:

1. Có bao nhiêu dòng đi vào toán tử Aggregate sau khi lọc và join?
2. Số nhóm thực tế là bao nhiêu và group key gồm những cột nào?
3. Optimizer chọn Hash Aggregate hay Stream/Group Aggregate? Vì sao?
4. Đầu vào đã có thứ tự phù hợp hay phải Sort?
5. Estimated rows và estimated groups có gần số liệu thực tế không?
6. Hash table hoặc Sort có spill ra đĩa không?
7. Temp I/O, buffer reads và CPU chiếm tỷ trọng thế nào?
8. Có index ghép nào cung cấp group key order hoặc covering access không?
9. WHERE có thể giảm input rows trước GROUP BY mà vẫn giữ đúng ngữ nghĩa không?
10. COUNT, DISTINCT, NULL, HAVING và các grouping sets có được xử lý đúng không?
11. Parallel aggregation có giảm thời gian tổng thể sau khi tính chi phí điều phối không?
12. Sau thay đổi, p95/p99, throughput, CPU, bộ nhớ, I/O và chi phí ghi có cải thiện ở cùng mức tải không?

## Kết luận

Hash Aggregate gom dòng bằng hash table, không cần đầu vào đã sắp xếp nhưng bộ nhớ tăng theo số nhóm và trạng thái tổng hợp. Sort/Stream Aggregate xử lý các dòng đã có thứ tự theo group key; nó có thể dùng ít bộ nhớ cho trạng thái nhóm nhưng có thể cần một bước Sort tốn CPU, RAM và I/O tạm.

Optimizer lựa chọn giữa hai chiến lược dựa trên số dòng đầu vào, số nhóm ước lượng, thứ tự sẵn có, độ rộng dữ liệu, chi phí truy cập và bộ nhớ. Chỉ mục có thể cung cấp thứ tự để tránh Sort, nhưng cũng có thể làm truy cập dữ liệu đắt hơn scan khi truy vấn phải đọc phần lớn bảng.

Muốn tối ưu GROUP BY, hãy đo số dòng và số nhóm thực tế, đọc execution plan, kiểm tra spill và temp I/O, đánh giá thống kê và index order, rồi thử một thay đổi có kiểm soát. Xác minh bằng cùng workload và theo dõi cả CPU, bộ nhớ, I/O, throughput cùng chi phí ghi để bảo đảm cải thiện có ý nghĩa đối với toàn hệ thống.
