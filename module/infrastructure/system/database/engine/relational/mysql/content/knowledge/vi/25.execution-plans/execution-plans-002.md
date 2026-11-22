# EXPLAIN ANALYZE và việc truy vấn thực sự được chạy

EXPLAIN thông thường cho biết MySQL dự định thực hiện truy vấn như thế nào dựa trên ước lượng của optimizer. EXPLAIN ANALYZE đi thêm một bước: MySQL thực sự chạy câu truy vấn rồi hiển thị kế hoạch dạng cây cùng số hàng và thời gian đo được ở từng iterator. Vì vậy, đây là công cụ quan trọng để so sánh ước lượng với hành vi thực tế, đồng thời cũng là một thao tác có thể tiêu tốn tài nguyên như chính truy vấn được phân tích.

Trong module DATABASE_MYSQL, bài học này giúp đọc EXPLAIN ANALYZE đúng cách: hiểu actual time, rows, loops, nhận diện iterator chậm, tìm sai lệch giữa estimated rows và actual rows, và chọn môi trường phù hợp trước khi thực thi phân tích.

## 1. EXPLAIN và EXPLAIN ANALYZE khác nhau ở đâu?

EXPLAIN thông thường yêu cầu optimizer xây dựng kế hoạch thực thi. Nó cung cấp thông tin ước lượng như access type, index, số hàng dự kiến và chi phí. Câu truy vấn được giải thích không cần chạy để tạo ra các ước lượng đó.

EXPLAIN ANALYZE thực thi câu truy vấn rồi đo những gì xảy ra trong quá trình chạy. Kết quả bao gồm:

- Kế hoạch dạng cây (TREE) với các iterator.
- Ước lượng cost và rows của optimizer.
- Thời gian thực tế, số hàng thực tế và số lần iterator được gọi.

| Công cụ | Có thực thi truy vấn được phân tích? | Dữ liệu chính |
|---|---|---|
| EXPLAIN SELECT ... | Không thực thi phần SELECT để lấy kết quả | Kế hoạch và ước lượng |
| EXPLAIN FORMAT=TREE SELECT ... | Không thực thi phần SELECT để lấy kết quả | Kế hoạch dạng cây và ước lượng |
| EXPLAIN FORMAT=JSON SELECT ... | Không thực thi phần SELECT để lấy kết quả | Kế hoạch có cấu trúc JSON và ước lượng |
| EXPLAIN ANALYZE SELECT ... | Có, câu SELECT được chạy thật | Kế hoạch dạng cây, ước lượng và số liệu thực tế |

EXPLAIN ANALYZE được giới thiệu trong MySQL 8.0.18. Hãy kiểm tra phiên bản server trước khi dùng:

~~~sql
SELECT VERSION();
~~~

Trong MySQL, EXPLAIN ANALYZE hiển thị kết quả theo TREE. Không xem nó là một tùy chọn chỉ thêm số liệu vào JSON; định dạng TREE là định dạng dùng cho kết quả phân tích thực thi.

## 2. Vì sao EXPLAIN ANALYZE thực thi truy vấn thật?

Optimizer chỉ có thể ước lượng số hàng, chi phí và lựa chọn đường truy cập dựa trên thống kê cùng thông tin schema. Các ước lượng có thể khác với dữ liệu thực tế vì:

- Phân bố dữ liệu lệch, ví dụ một customer_id có rất nhiều đơn hàng hơn các khách hàng khác.
- Thống kê index đã cũ hoặc không mô tả tốt phân bố dữ liệu.
- Các điều kiện lọc có tương quan với nhau nhưng optimizer ước lượng chúng như những yếu tố độc lập.
- Một iterator bên trong vòng lặp được gọi nhiều lần hơn dự kiến.
- Chi phí truy cập thực tế bị ảnh hưởng bởi cache, I/O, CPU và tải đồng thời.

EXPLAIN ANALYZE chạy truy vấn để đo số hàng và thời gian của iterator. Nó giúp trả lời các câu hỏi:

- Optimizer dự đoán một iterator trả về 10 hàng nhưng thực tế trả về 50.000 hàng?
- Một index lookup riêng lẻ nhanh nhưng bị lặp hàng trăm nghìn lần?
- Phần nào của kế hoạch đang tiêu tốn nhiều thời gian?
- Một phép lọc loại bỏ phần lớn hàng sau khi MySQL đã đọc chúng?

Đây là phép đo trên lần chạy cụ thể. Kết quả không phải cam kết thời gian cho mọi lần chạy sau, vì cache, dữ liệu, concurrency và tải hệ thống có thể thay đổi.

## 3. Cú pháp cơ bản

Ví dụ:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42;
~~~

MySQL thực thi SELECT và trả về cây iterator kèm số liệu thực tế. Kết quả phân tích thay thế result set thông thường của câu SELECT; nó mô tả quá trình thực thi chứ không phải danh sách hàng của truy vấn.

Có thể dùng EXPLAIN ANALYZE với các SELECT có JOIN, subquery, CTE, aggregation hoặc window function để quan sát những iterator tạo nên kế hoạch. Hãy bắt đầu bằng một truy vấn cụ thể và đặt câu hỏi rõ ràng, chẳng hạn “vì sao join này đọc nhiều hàng?” hoặc “vì sao bộ lọc chỉ giữ lại rất ít hàng?”.

## 4. Đọc cấu trúc cây iterator

Ví dụ minh họa một kết quả TREE:

~~~text
-> Filter: (o.status = 'PAID')
    (cost=120.00 rows=100)
    (actual time=0.080..4.200 rows=90 loops=1)
    -> Index range scan on o using idx_orders_customer_created
        (cost=90.00 rows=1000)
        (actual time=0.050..3.700 rows=1200 loops=1)
~~~

Các con số ở trên chỉ nhằm minh họa cách đọc, không phải kết quả cố định cho mọi database.

Một cây iterator được đọc từ các node con lên node cha:

- Index range scan đọc entry index trong khoảng đã xác định và cung cấp hàng cho node phía trên.
- Filter nhận các hàng đó, đánh giá điều kiện status = 'PAID' rồi chỉ chuyển tiếp hàng thỏa mãn.
- Node cha có thể tiêu tốn thời gian bao gồm cả việc lấy dữ liệu từ node con; không cộng thời gian của mọi node một cách máy móc.

Khi đọc cây, hãy tìm node lá thực hiện table/index access trước, sau đó xem các phép filter, join, sort hoặc aggregate ở phía trên xử lý số hàng đó ra sao.

## 5. Ý nghĩa actual time

Một iterator thường hiển thị:

~~~text
(actual time=0.050..3.700 rows=1200 loops=1)
~~~

Hai giá trị trong actual time biểu thị thời gian trung bình để iterator trả về hàng đầu tiên và thời gian để iterator hoàn thành việc tạo các hàng của nó, tính bằng mili giây:

- Giá trị đầu: thời gian đến khi có hàng đầu tiên.
- Giá trị sau: thời gian đến khi iterator hoàn tất.

Nếu iterator được gọi nhiều lần (loops lớn hơn 1), thời gian hiển thị là trung bình mỗi lần gọi. Vì vậy, khi phân tích nested loop, đừng chỉ nhìn thời gian của một lần gọi; hãy xem cả số loops.

Ví dụ:

~~~text
(actual time=0.010..0.030 rows=2 loops=5000)
~~~

Iterator trả trung bình 2 hàng mỗi lần và được gọi 5.000 lần. Tổng số hàng đầu ra qua các lần gọi xấp xỉ 10.000. Một thao tác nhỏ lặp hàng nghìn lần vẫn có thể tạo chi phí tổng lớn.

Không nên cộng tất cả actual time của node cha và node con để suy ra thời gian toàn truy vấn. Thời gian của iterator cha có thể bao gồm thời gian chờ dữ liệu từ iterator con; các số liệu có quan hệ lồng nhau.

## 6. Ý nghĩa rows và loops

rows trong phần ước lượng cho biết optimizer dự kiến iterator sẽ tạo hoặc đọc bao nhiêu hàng theo mô hình chi phí. actual rows cho biết số hàng iterator thực sự trả ra trong lần chạy.

loops cho biết iterator được gọi bao nhiêu lần. Với iterator nằm ở phía trong của nested loop, loops có thể tăng theo số hàng từ phía ngoài.

Ví dụ:

~~~text
-> Nested loop inner join
    (actual time=0.100..30.000 rows=5000 loops=1)
    -> Table scan on customers
        (actual time=0.020..1.000 rows=1000 loops=1)
    -> Index lookup on orders using idx_orders_customer
        (actual time=0.005..0.020 rows=5 loops=1000)
~~~

Node lookup orders được gọi 1.000 lần, mỗi lần trung bình trả 5 hàng. Tổng số hàng từ các lần lookup xấp xỉ 5.000. Đây là hành vi bình thường của nested loop, nhưng nếu outer side có hàng triệu dòng thì số lần lookup có thể trở thành nút thắt.

Khi loops lớn, hãy đọc actual rows cùng loops; chỉ nhìn rows nhỏ có thể đánh giá thiếu chi phí lặp.

## 7. Phân biệt cost estimate và thời gian thực tế

Ví dụ:

~~~text
(cost=90.00 rows=1000)
(actual time=0.050..3.700 rows=1200 loops=1)
~~~

cost là đơn vị chi phí nội bộ dùng cho việc so sánh kế hoạch của optimizer, không phải mili giây và không thể đọc như thời gian thực thi. actual time mới là số đo thời gian trong lần chạy.

rows ở phần ước lượng và actual rows có thể khác nhau. Sai lệch lớn có thể làm optimizer chọn join order hoặc access method không phù hợp.

Ví dụ:

| Chỉ số | Ước lượng | Thực tế | Nhận xét |
|---|---:|---:|---|
| Rows của index lookup | 10 | 8 | Ước lượng khá gần |
| Rows của filter | 5 | 40.000 | Ước lượng thấp nghiêm trọng |
| Loops của inner lookup | 100 | 80.000 | Phía ngoài tạo nhiều lần gọi hơn dự kiến |

Đây là dữ liệu minh họa. Khi gặp sai lệch, hãy xác định node đầu tiên có estimated rows khác xa actual rows; sai lệch từ node đó có thể lan sang các phép join và filter phía trên.

## 8. Ví dụ thực hành với bảng orders

Tạo bảng thử nghiệm:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE=InnoDB;
~~~

Truy vấn lấy đơn hàng gần đây của một khách hàng:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

Xem kế hoạch ước lượng:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

Sau đó chạy phân tích thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

Với index (customer_id, created_at), MySQL có thể định vị vùng của customer 42 và đọc các entry trong khoảng thời gian. Tuy nhiên, truy vấn còn trả status và total_amount, là các cột không có trong index ví dụ. Với mỗi entry phù hợp, InnoDB có thể cần truy cập clustered record để lấy các cột này.

LIMIT 20 có thể giúp iterator dừng sớm khi đã đủ hàng, nếu kế hoạch có thể cung cấp thứ tự phù hợp. Hãy quan sát tree output để xác định có sort bổ sung hay không và iterator nào thực sự đọc nhiều hàng.

## 9. Tìm node đầu tiên có sai lệch lớn

Khi so sánh estimates và actuals, đừng bắt đầu sửa index ngay. Hãy đi từ node lá lên:

1. Tìm iterator đầu tiên có estimated rows khác xa actual rows.
2. Xác định nguyên nhân có thể đến từ thống kê, độ chọn lọc, phân bố lệch hoặc điều kiện tương quan.
3. Xem sai lệch đó ảnh hưởng đến số loops hoặc join order ở phía trên thế nào.
4. Kiểm tra index và điều kiện truy vấn sau khi đã hiểu sai lệch.

Ví dụ nếu optimizer dự đoán customer_id = 42 có 10 đơn nhưng thực tế có 100.000 đơn, một nested loop phía trên có thể tạo lượng công việc lớn hơn nhiều dự kiến. Hãy xem thống kê index và phân bố customer_id; một giá trị rất phổ biến có thể không đại diện cho các giá trị khác.

Có thể yêu cầu cập nhật thống kê bảng:

~~~sql
ANALYZE TABLE orders;
~~~

Lệnh này cập nhật thống kê dùng bởi optimizer; nó không phải là EXPLAIN ANALYZE và không chạy truy vấn ứng dụng để đo thời gian. Sau khi cập nhật, chạy lại EXPLAIN để xem kế hoạch ước lượng có thay đổi hay không, rồi mới dùng EXPLAIN ANALYZE để đo lần chạy thực tế.

## 10. Hiểu các iterator thường gặp

Một số iterator thường xuất hiện trong TREE output:

| Iterator | Vai trò | Điều cần xem |
|---|---|---|
| Table scan | Đọc hàng từ bảng | Tổng hàng đọc, có filter phía trên loại bỏ phần lớn không |
| Index range scan | Đọc khoảng entry trong index | Khoảng có quá rộng không, có cần lookup clustered row không |
| Index lookup | Tìm entry theo khóa | Số hàng trả về và số lần lặp |
| Filter | Lọc hàng theo điều kiện | Bao nhiêu hàng bị loại so với đầu vào |
| Nested loop join | Lặp lookup bảng trong cho từng hàng bảng ngoài | Loops của iterator phía trong |
| Hash join | Tạo/tra cứu cấu trúc hash cho join | Số hàng build/probe và bộ nhớ |
| Sort | Sắp xếp hàng | Số hàng cần sort, thời gian và vị trí trong kế hoạch |
| Aggregate | Tính tổng hợp | Số nhóm và lượng hàng đầu vào |
| Materialize | Tạo kết quả trung gian | Kích thước kết quả và số lần sử dụng |

Tên và hình dạng iterator phụ thuộc truy vấn, phiên bản và lựa chọn optimizer. Hãy đọc kế hoạch thực tế thay vì mong đợi một truy vấn luôn sinh ra đúng một cây cố định.

## 11. Khi nào EXPLAIN ANALYZE có thể gây tác động đáng kể?

Vì câu truy vấn được chạy thật, EXPLAIN ANALYZE có thể:

- Đọc nhiều hàng hoặc quét toàn bảng.
- Tạo temporary table hoặc materialize kết quả trung gian.
- Thực hiện sort lớn và dùng CPU/bộ nhớ.
- Gây I/O đáng kể khi dữ liệu không nằm trong buffer pool.
- Chạy lâu, tiêu thụ connection và ảnh hưởng truy vấn khác khi tải cao.
- Đọc dữ liệu theo transaction isolation hiện tại của session.

Không chạy phân tích trên truy vấn nặng ở giờ cao điểm chỉ để xem thử. Bắt đầu bằng EXPLAIN thường để đánh giá quy mô kế hoạch; sau đó dùng EXPLAIN ANALYZE trên dữ liệu thử nghiệm, bản sao phù hợp hoặc thời điểm đã đánh giá tải.

Đối với một SELECT có LIMIT, đừng giả định lượng dữ liệu đọc luôn nhỏ. Nếu kế hoạch phải sort hoặc materialize toàn bộ tập ứng viên trước khi áp dụng LIMIT, truy vấn vẫn có thể xử lý rất nhiều hàng.

## 12. Chọn truy vấn phù hợp để phân tích

Ưu tiên:

- SELECT đại diện cho truy vấn chậm đã được xác định.
- Truy vấn có thể chạy lặp lại mà không làm thay đổi dữ liệu nghiệp vụ.
- Một truy vấn đã biết đầu vào và tham số cụ thể.
- Truy vấn có khối lượng phù hợp với môi trường phân tích.

Tránh chạy tùy tiện:

- SELECT gọi stored function hoặc UDF có side effect.
- Locking read như SELECT ... FOR UPDATE hoặc LOCK IN SHARE MODE khi không chủ đích kiểm tra khóa.
- Truy vấn không giới hạn có thể quét bảng rất lớn.
- Truy vấn có subquery hoặc biểu thức tốn tài nguyên mà chưa đánh giá bằng EXPLAIN thường.

EXPLAIN ANALYZE trong MySQL được dùng để phân tích truy vấn SELECT; không dùng nó như một cơ chế chạy thử UPDATE/DELETE/INSERT rồi tự động rollback. Với DML, dùng dạng EXPLAIN được phiên bản hỗ trợ để xem kế hoạch, và thử thay đổi dữ liệu trong môi trường kiểm thử có thể khôi phục.

## 13. EXPLAIN ANALYZE không phải benchmark hoàn chỉnh

Kết quả một lần chạy chỉ mô tả điều kiện tại thời điểm đo. Thời gian có thể khác do:

- Buffer pool đang nóng hay lạnh.
- Dữ liệu và index có thay đổi.
- CPU, storage và network đang chịu tải khác nhau.
- Cache ở tầng ứng dụng hoặc hệ điều hành.
- Transaction khác đang tranh chấp tài nguyên.
- Tham số đầu vào có độ chọn lọc khác.

Nếu cần benchmark, hãy chạy nhiều lần với bộ tham số đại diện, ghi nhận phân vị latency và tải hệ thống, kiểm soát trạng thái cache và so sánh cùng điều kiện. Không lấy một lần actual time làm cam kết hiệu năng.

## 14. Quy trình phân tích một truy vấn chậm

~~~mermaid
flowchart TD
    A[Chọn truy vấn chậm và tham số thực tế] --> B[Chạy EXPLAIN thường]
    B --> C[Đọc access path, estimates, index và join order]
    C --> D{Có thể chạy an toàn trong môi trường hiện tại?}
    D -->|Không| E[Dùng bản sao hoặc dữ liệu kiểm thử]
    D -->|Có| F[Chạy EXPLAIN ANALYZE]
    E --> F
    F --> G[So estimated rows với actual rows]
    G --> H[Tìm node sai lệch đầu tiên và loops lớn]
    H --> I[Đánh giá index, filter, join và sort]
    I --> J[Thay đổi một yếu tố]
    J --> K[Đo lại cùng truy vấn và tham số]
~~~

Quy trình này giữ được mối liên hệ giữa kế hoạch ước lượng và hành vi thực tế. Thay đổi từng yếu tố giúp biết cải tiến đến từ index, điều kiện lọc, join order hay cách truy vấn.

## 15. Checklist đọc EXPLAIN ANALYZE

1. Kiểm tra phiên bản MySQL có hỗ trợ EXPLAIN ANALYZE không.
2. Xác nhận câu truy vấn có thể được thực thi an toàn và tải phù hợp.
3. Chạy EXPLAIN thường để hiểu kế hoạch và ước lượng trước.
4. Đọc cây từ iterator lá lên iterator cha.
5. So sánh estimated rows với actual rows tại từng iterator.
6. Đọc actual time để biết thời gian đến hàng đầu và thời gian hoàn tất.
7. Đọc loops; nhân số hàng trung bình với số lần lặp để hiểu quy mô xử lý.
8. Tìm node đầu tiên có sai lệch ước lượng lớn.
9. Kiểm tra iterator phía trong nested loop có bị gọi quá nhiều lần không.
10. Xem sort, filter, materialize và table/index access có đọc nhiều dữ liệu không.
11. Không cộng thời gian node cha/con một cách máy móc.
12. Đo lại sau thay đổi trong điều kiện tương đương.

## 16. Bài tập thực hành

1. Tạo bảng orders và index (customer_id, created_at) theo ví dụ.
2. Chạy EXPLAIN FORMAT=TREE cho truy vấn lọc customer_id và khoảng thời gian.
3. Chạy EXPLAIN ANALYZE trên cùng câu SELECT và so sánh estimated rows với actual rows.
4. Ghi lại actual time, rows và loops của từng iterator.
5. Tạo truy vấn JOIN customers với orders; quan sát số loops của index lookup ở phía trong nested loop.
6. Thử một customer_id có ít đơn và một customer_id có rất nhiều đơn; so sánh sai lệch estimates.
7. Chạy ANALYZE TABLE orders, sau đó chạy lại EXPLAIN để xem ước lượng có thay đổi không.
8. Thêm hoặc thay index trong môi trường thử nghiệm, sau đó đo lại cùng câu truy vấn.
9. So sánh truy vấn có ORDER BY/LIMIT khi kế hoạch có thể dùng index order và khi phải sort.
10. Viết ghi chú ngắn xác định node tốn thời gian nhất và thay đổi nào có bằng chứng cải thiện.

Bạn hoàn thành bài khi giải thích được EXPLAIN ANALYZE thực thi SELECT thật, đọc được actual time, rows, loops, tìm được sai lệch estimates và đánh giá được tác động tải trước khi chạy. Hãy dùng kết quả đo để đặt giả thuyết tối ưu, sau đó kiểm chứng lại trong cùng điều kiện.
