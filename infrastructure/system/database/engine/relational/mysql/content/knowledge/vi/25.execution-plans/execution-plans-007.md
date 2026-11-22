# Actual rows, loops, thời gian khởi tạo và thời gian hoàn tất

EXPLAIN thông thường cho biết optimizer dự đoán kế hoạch sẽ xử lý bao nhiêu hàng và chọn access path nào. Nhưng ước lượng không phải kết quả thực tế. MySQL 8.0.18 trở lên cung cấp EXPLAIN ANALYZE để thực thi câu SELECT và ghi nhận số hàng thực tế, số lần iterator được gọi cùng thời gian iterator tạo ra hàng đầu tiên và hoàn tất việc trả hàng.

Trong output dạng TREE, một iterator có thể xuất hiện như sau:

    (actual time=0.120..0.450 rows=8 loops=1)

Hai mốc thời gian có ý nghĩa khác nhau: mốc đầu là thời gian để iterator trả hàng đầu tiên; mốc thứ hai là thời gian để iterator trả hết các hàng của lần thực thi đó. rows là số hàng trung bình iterator trả về trong mỗi lần chạy, còn loops là số lần iterator được chạy. Khi đọc các giá trị này, cần phân biệt thời gian khởi động với thời gian hoàn tất, hiểu việc lấy trung bình qua nhiều vòng lặp và tránh cộng thời gian của các node lồng nhau như thể chúng độc lập.

Bài học này tập trung vào cách đọc actual rows, loops, startup time và completion time, cách tìm iterator gây chậm, cách diễn giải nested loop và sort/materialization, cũng như giới hạn của số liệu EXPLAIN ANALYZE khi so sánh với latency mà ứng dụng quan sát.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích EXPLAIN ANALYZE và khác biệt với EXPLAIN thông thường.
- Đọc actual time=a..b, rows và loops trong từng iterator.
- Phân biệt thời gian đến hàng đầu tiên và thời gian hoàn tất iterator.
- Hiểu rows và actual time được lấy trung bình khi iterator có nhiều loops.
- Ước lượng tổng số hàng được trả qua nhiều lần gọi bằng rows nhân loops.
- Phân tích loops trong nested loop join và các iterator được gọi lặp lại.
- Nhận biết startup delay do sort, materialization hoặc xử lý đầu vào trước khi trả hàng.
- So sánh estimated rows với actual rows trên cùng cơ sở.
- Tìm điểm đầu tiên có sai lệch lớn trong cây thực thi.
- Phân biệt thời gian iterator với tổng thời gian end-to-end của ứng dụng.
- Dùng EXPLAIN ANALYZE an toàn và tránh đo sai do cache, tham số hoặc tải hệ thống.

## 1. EXPLAIN và EXPLAIN ANALYZE khác nhau

EXPLAIN thông thường yêu cầu optimizer lập kế hoạch và trả về ước lượng. Nó không thực thi SELECT để thu thập số hàng và thời gian thực tế.

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

EXPLAIN ANALYZE thực thi câu truy vấn, đo các iterator trong kế hoạch và trả về cây thực thi có actual metrics:

    EXPLAIN ANALYZE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

Các điểm cần nhớ:

- EXPLAIN ANALYZE được hỗ trợ từ MySQL 8.0.18.
- Output của EXPLAIN ANALYZE sử dụng định dạng TREE.
- Câu truy vấn được thực thi để thu thập số liệu; đây không phải thao tác chỉ đọc kế hoạch.
- Các iterator báo số hàng thực tế, loops và timing.
- Kết quả vẫn chịu ảnh hưởng của dữ liệu, cache, tải server và overhead đo.

Không chạy EXPLAIN ANALYZE một truy vấn nặng trên production chỉ vì muốn xem thử. Trước khi chạy, cần hiểu phạm vi dữ liệu mà SELECT có thể đọc và tài nguyên truy vấn có thể tiêu thụ.

## 2. Cấu trúc một dòng actual metrics

Một node trong output TREE có thể trông như sau:

    -> Index lookup on o using idx_order_customer
       (customer_id=1001)
       (cost=1.20 rows=4)
       (actual time=0.020..0.035 rows=5 loops=1)

Ý nghĩa:

| Thành phần | Ý nghĩa |
|---|---|
| cost=1.20 | Chi phí ước lượng của optimizer theo cost model |
| rows=4 trong cost block | Số hàng optimizer ước lượng iterator sẽ trả/đọc theo ngữ cảnh kế hoạch |
| actual time=0.020..0.035 | Thời gian thực tế đến hàng đầu tiên và hoàn tất iterator |
| rows=5 trong actual block | Số hàng thực tế trung bình iterator trả về mỗi loop |
| loops=1 | Iterator được thực thi một lần |

Trong ví dụ này, iterator được gọi một lần và trả 5 hàng, trong khi optimizer ước lượng 4 hàng. Thời gian đến hàng đầu tiên là khoảng 0,020 ms; thời gian hoàn tất là khoảng 0,035 ms. Các số trong ví dụ chỉ minh họa định dạng, không phải benchmark của một server cụ thể.

### 2.1. Đơn vị thời gian

Các giá trị actual time của EXPLAIN ANALYZE được hiển thị theo milliseconds. Ví dụ:

- 0.020 tương đương 20 microseconds.
- 1.500 tương đương 1,5 milliseconds.
- 125.000 tương đương 125 milliseconds.

Đừng nhầm dấu chấm thập phân với dấu phân tách giây. Output actual time=0.120..0.450 biểu thị hai mốc trong đơn vị millisecond.

## 3. Hai mốc thời gian: hàng đầu tiên và hoàn tất

Với:

    actual time=a..b

- a: thời gian từ lúc iterator bắt đầu được thực thi đến khi nó trả hàng đầu tiên.
- b: thời gian từ lúc iterator bắt đầu được thực thi đến khi nó trả hết hàng của lần thực thi đó.

b là mốc hoàn tất tính từ đầu, không phải khoảng thời gian bổ sung sau hàng đầu tiên. Nếu muốn ước lượng phần thời gian từ hàng đầu tiên đến hoàn tất, có thể lấy b - a để hình dung, nhưng không nên xem phép trừ này là một metric độc lập được MySQL báo trực tiếp.

Ví dụ:

    actual time=2.000..12.000 rows=100 loops=1

Có thể diễn giải:

- Iterator mất khoảng 2 ms để tạo hàng đầu tiên.
- Iterator hoàn tất việc trả 100 hàng sau khoảng 12 ms tính từ lúc bắt đầu.
- Sau hàng đầu tiên, còn khoảng 10 ms cho phần xử lý và trả các hàng còn lại.

Hai mốc giúp phân biệt truy vấn có startup delay lớn với truy vấn tạo hàng đầu tiên nhanh nhưng mất nhiều thời gian để hoàn tất.

### 3.1. Hàng đầu tiên nhanh không có nghĩa toàn truy vấn nhanh

Một iterator có thể trả hàng đầu tiên rất sớm nhưng tiếp tục đọc nhiều hàng:

    actual time=0.050..800.000 rows=500000 loops=1

Nó bắt đầu trả kết quả sau khoảng 0,05 ms nhưng mất khoảng 800 ms để hoàn tất. Đây có thể là một scan streaming qua nhiều hàng.

Ngược lại, một iterator có thể phải xử lý gần như toàn bộ đầu vào trước khi trả hàng đầu tiên:

    actual time=450.000..470.000 rows=20 loops=1

Iterator mất khoảng 450 ms trước khi có hàng đầu tiên, sau đó trả 20 hàng và hoàn tất khoảng 470 ms. Đây có thể là một bước sort hoặc materialization cần tiêu thụ đầu vào trước.

### 3.2. Thời gian khởi động không chỉ là thời gian gọi Init()

Tên startup time thường được dùng để mô tả độ trễ trước hàng đầu tiên. Nó không nhất thiết chỉ là thời gian thực thi một hàm khởi tạo riêng lẻ. Iterator có thể gọi iterator con, đọc dữ liệu đầu vào, tạo temporary structure hoặc thực hiện một phần công việc trước khi có thể trả hàng đầu tiên.

Do đó, khi thấy mốc đầu lớn, hãy xem cả cây iterator bên dưới và loại thao tác đang diễn ra. Đừng kết luận rằng chỉ riêng node đó có một bước setup độc lập mất toàn bộ thời gian.

## 4. rows và loops

rows trong actual block là số hàng trung bình iterator trả về trong mỗi lần chạy. loops là số lần iterator được chạy.

Ví dụ:

    actual time=0.010..0.025 rows=3 loops=1

Iterator chạy một lần và trả 3 hàng.

Ví dụ khác:

    actual time=0.005..0.015 rows=2 loops=10

Iterator được chạy 10 lần, trung bình trả 2 hàng mỗi lần. Tổng số hàng trả qua các lần chạy xấp xỉ:

    2 rows/loop * 10 loops = 20 rows

Khi số hàng trung bình là số thập phân, phép nhân vẫn chỉ cho một ước lượng tổng số hàng do cách hiển thị đã làm tròn.

### 4.1. rows không đồng nghĩa rows examined

Actual rows là số hàng iterator trả ra cho iterator cha trong mỗi lần chạy. Nó không nhất thiết là tổng số record mà storage engine đã xem xét hoặc đọc từ đĩa.

Ví dụ một index range scan có thể kiểm tra nhiều index entry, áp dụng điều kiện rồi chỉ trả một phần hàng. Một filter iterator có thể nhận 1.000 hàng từ iterator con nhưng chỉ trả 10 hàng cho node phía trên.

Muốn hiểu số hàng được đọc, số hàng bị lọc và chi phí từng bước, hãy xem toàn bộ cây iterator, access method, điều kiện filter và các công cụ thống kê khác. Không dùng một giá trị actual rows để thay thế mọi khái niệm về rows examined.

### 4.2. loops lớn thường xuất hiện ở iterator bên trong nested loop

Nested loop join chạy iterator phía trong cho từng hàng từ iterator phía ngoài. Nếu phía ngoài trả 100 hàng, iterator lookup phía trong có thể được gọi 100 lần:

    -> Nested loop inner join
       (actual time=... rows=... loops=1)
        -> Table scan on customer
           (actual time=... rows=100 loops=1)
        -> Index lookup on orders using idx_order_customer
           (actual time=... rows=4 loops=100)

Iterator lookup phía trong được gọi 100 lần, trung bình trả 4 đơn mỗi lần. Tổng số hàng mà nó trả ra xấp xỉ 400.

Điều này không có nghĩa MySQL tạo 100 câu SQL độc lập. Đó là cùng một iterator được gọi lặp lại trong quá trình thực thi nested loop.

### 4.3. loops lớn không tự động là vấn đề

Một lookup theo primary key có thể rất rẻ dù chạy hàng nghìn lần. Ngược lại, vài lần gọi một iterator đắt hoặc mỗi lần quét nhiều hàng có thể gây vấn đề.

Khi đánh giá loops, xem đồng thời:

- Thời gian mỗi loop.
- Số hàng mỗi loop.
- Tổng số lần gọi.
- Access path của iterator.
- Số hàng phía ngoài kích hoạt các lần gọi.
- Tác động của iterator đó lên thời gian hoàn tất node cha.

Đừng chỉ tối ưu node có loops cao nhất. Hãy xác định tổng công việc và điểm đóng góp vào độ trễ của truy vấn.

## 5. Thời gian được lấy trung bình khi loops lớn hơn 1

Khi iterator được thực thi nhiều lần, các giá trị actual time và rows trong output được báo theo trung bình mỗi loop.

Ví dụ:

    actual time=0.010..0.030 rows=4 loops=100

Diễn giải:

- Iterator chạy 100 lần.
- Mỗi lần trung bình mất khoảng 0,010 ms để trả hàng đầu tiên.
- Mỗi lần trung bình hoàn tất sau khoảng 0,030 ms tính từ lúc bắt đầu lần đó.
- Mỗi lần trung bình trả 4 hàng.
- Tổng số hàng trả qua các lần chạy xấp xỉ 400.

Không đọc actual time=0.010..0.030 như tổng thời gian cho cả 100 loops. Nó là thời gian trung bình cho một lần chạy iterator.

Có thể nhân thời gian trung bình với loops để có một ước lượng thô về tổng thời gian của riêng iterator qua các lần gọi, nhưng cần thận trọng:

- Giá trị đã được làm tròn.
- Các lần gọi có thể có độ phân tán khác nhau.
- Thời gian node cha và node con có thể chồng lấp về mặt đo lường.
- Tổng thời gian truy vấn không phải phép cộng đơn giản của mọi node.

Vì vậy, dùng phép nhân như công cụ hình dung khối lượng lặp, không dùng nó để tái tạo chính xác wall-clock time của toàn query.

## 6. Đọc cây iterator từ dưới lên

EXPLAIN ANALYZE hiển thị kế hoạch dạng cây. Các iterator con cung cấp dữ liệu cho iterator cha. Để hiểu truy vấn, đọc từ các leaf iterator (scan/lookup) lên các node join, filter, aggregate, sort và cuối cùng là root.

Ví dụ minh họa:

    -> Limit: 20 row(s)
       (actual time=0.120..0.450 rows=20 loops=1)
        -> Sort: o.order_date DESC, limit input to 20 row(s)
           (actual time=0.118..0.440 rows=20 loops=1)
            -> Filter: (o.order_status = 'PAID')
               (actual time=0.050..0.350 rows=80 loops=1)
                -> Index lookup on o using idx_order_customer
                   (customer_id=1001)
                   (actual time=0.040..0.300 rows=500 loops=1)

Diễn giải:

1. Index lookup tìm các đơn của customer 1001 và trả 500 hàng.
2. Filter giữ lại 80 đơn PAID.
3. Sort sắp xếp theo order_date và giới hạn đầu vào theo nhu cầu LIMIT.
4. Limit trả 20 hàng cho client iterator phía trên.

Các số liệu ở đây chỉ minh họa cách đọc. Kế hoạch thực tế có thể khác do index, dữ liệu và phiên bản.

### 6.1. Xác định node tạo nhiều hàng

Trong ví dụ, lookup trả 500 hàng nhưng filter chỉ giữ 80. Có thể cần đánh giá:

- Index có đủ chọn lọc không?
- Có thể dùng index ghép (customer_id, order_status, order_date) không?
- Có nên để index hỗ trợ cả filter và thứ tự sort không?
- Query có cần tất cả 500 hàng trước khi sort hay có thể lấy top N hiệu quả hơn?

Không thể kết luận chỉ từ số hàng. Cần xem actual time, estimated rows, key, Extra và workload ghi của bảng.

### 6.2. Không cộng thời gian mọi node

Thời gian ở node cha có thể bao gồm thời gian gọi và tiêu thụ dữ liệu từ node con. Vì vậy, thời gian của parent và child không phải các đoạn độc lập có thể cộng lại.

Ví dụ, nếu root hoàn tất sau 20 ms, một node con báo 15 ms và node khác báo 10 ms, không kết luận tổng truy vấn là 45 ms. Những thời gian đó có thể nằm trong cùng khoảng thực thi lồng nhau.

Hãy dùng root iterator để hình dung thời gian hoàn tất của cây thực thi phía server, rồi xem node con để tìm phần công việc đóng góp vào độ trễ.

## 7. Nested loop: phân tích loops và thời gian mỗi lần lookup

Nested loop thường có một iterator ngoài và một iterator trong:

    for each row from outer iterator:
        execute inner iterator using values from outer row

Ví dụ truy vấn khách hàng và đơn hàng:

    SELECT
        c.customer_id,
        c.customer_name,
        o.order_id,
        o.total_amount
    FROM plan_customer_demo AS c
    JOIN plan_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN'
      AND o.order_status = 'PAID';

Giả sử outer iterator trả 3 khách hàng. Inner index lookup được gọi 3 lần, mỗi lần tìm đơn của một khách.

Output giả định:

    -> Nested loop inner join
       (actual time=0.080..0.420 rows=5 loops=1)
        -> Index lookup on c using idx_customer_country
           (country_code='VN')
           (actual time=0.025..0.040 rows=3 loops=1)
        -> Index lookup on o using idx_order_customer
           (customer_id=c.customer_id)
           (actual time=0.020..0.070 rows=2 loops=3)

Inner lookup trung bình trả 2 hàng qua 3 lần gọi, tổng khoảng 6 hàng đầu vào. Join cuối trả 5 hàng sau khi các điều kiện liên quan được áp dụng. Các con số minh họa không nhất thiết khớp chính xác mọi dạng plan vì filter có thể nằm ở iterator khác.

Khi inner loops lớn:

- Xem outer rows có lớn hơn ước lượng không.
- Xem inner access có dùng index lookup hiệu quả không.
- Xem mỗi lần lookup trả bao nhiêu hàng.
- Kiểm tra có thể lọc outer input sớm hơn không.
- Kiểm tra index ghép cho điều kiện join và filter.
- Đánh giá hash join hoặc chiến lược khác nếu phiên bản và truy vấn hỗ trợ.

Không cố giảm loops bằng mọi giá. Nếu outer có 100 hàng và mỗi inner lookup chỉ mất vài microseconds, nested loop có thể là kế hoạch tốt.

## 8. Sort và materialization thường có startup time cao

Một số iterator cần xử lý nhiều hoặc toàn bộ đầu vào trước khi trả hàng đầu tiên.

### 8.1. Sort

Nếu truy vấn cần ORDER BY mà index không thể cung cấp thứ tự phù hợp, MySQL có thể phải sort tập đầu vào:

    SELECT order_id, total_amount
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY total_amount DESC
    LIMIT 10;

Nếu access path không hỗ trợ thứ tự này, sort iterator có thể cần đọc và xử lý một lượng lớn hàng trước khi trả kết quả đầu tiên. Khi đó, mốc actual time đầu tiên của sort có thể cao.

LIMIT không bảo đảm MySQL chỉ đọc 10 hàng. Nếu phải tìm 10 giá trị lớn nhất trong một tập lớn, server vẫn cần xử lý đủ dữ liệu để xác định top 10, dù có thể dùng chiến lược top-N thay vì sort toàn bộ theo cách đơn giản.

### 8.2. Materialization

Một derived table hoặc subquery có thể được materialize vào internal temporary table. Iterator materialize có thể cần tiêu thụ đầu vào trước khi iterator phía trên bắt đầu đọc kết quả.

Khi thấy startup time lớn, hãy xem:

- Có Materialize hoặc temporary table iterator không?
- Derived table có thể merge được không?
- Có GROUP BY, DISTINCT hoặc window operation yêu cầu xử lý đầu vào không?
- Có thể lọc sớm hơn trước khi materialize không?
- Có index phù hợp trên bảng nguồn hoặc cấu trúc trung gian không?

Không phải mọi materialization đều xấu. Nó có thể giảm việc tính lại subquery hoặc hỗ trợ một kế hoạch tổng thể rẻ hơn.

### 8.3. LIMIT và khả năng dừng sớm

Một index phù hợp có thể cho phép MySQL đọc theo thứ tự và dừng sau khi đủ LIMIT:

    CREATE INDEX idx_plan_order_status_date
    ON plan_order_demo (order_status, order_date);

    SELECT order_id, order_date
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY order_date DESC
    LIMIT 10;

Nếu index hỗ trợ điều kiện và thứ tự, iterator có thể trả đủ 10 hàng mà không phải sort toàn bộ tập kết quả. Hãy kiểm tra actual rows và iterator tree để xác nhận kế hoạch thực tế.

## 9. Ví dụ thực hành tự chứa

Tạo hai bảng để quan sát join, filter và loops trong database sandbox:

    CREATE TABLE plan_customer_demo (
        customer_id BIGINT UNSIGNED NOT NULL,
        customer_name VARCHAR(100) NOT NULL,
        country_code CHAR(2) NOT NULL,
        PRIMARY KEY (customer_id),
        KEY idx_customer_country (country_code)
    ) ENGINE = InnoDB;

    CREATE TABLE plan_order_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        order_date DATETIME NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_order_customer (customer_id),
        KEY idx_order_status (order_status),
        KEY idx_order_customer_status (customer_id, order_status)
    ) ENGINE = InnoDB;

    INSERT INTO plan_customer_demo
        (customer_id, customer_name, country_code)
    VALUES
        (1001, 'An', 'VN'),
        (1002, 'Binh', 'VN'),
        (1003, 'Chi', 'VN'),
        (1004, 'Dung', 'US');

    INSERT INTO plan_order_demo
        (order_id, customer_id, order_date, order_status, total_amount)
    VALUES
        (5001, 1001, '2025-01-02 10:00:00', 'PAID',      120.00),
        (5002, 1001, '2025-01-05 11:00:00', 'PENDING',    80.00),
        (5003, 1001, '2025-01-08 12:00:00', 'PAID',      250.00),
        (5004, 1002, '2025-01-10 13:00:00', 'CANCELLED',  40.00),
        (5005, 1002, '2025-01-11 14:00:00', 'PAID',      500.00),
        (5006, 1003, '2025-01-12 15:00:00', 'PAID',       75.00),
        (5007, 1004, '2025-01-13 16:00:00', 'PAID',      300.00);

    ANALYZE TABLE plan_customer_demo, plan_order_demo;

Bảng mẫu nhỏ nên optimizer có thể chọn table scan. Đây là dữ liệu để kiểm tra cú pháp và quan sát output; muốn nghiên cứu kế hoạch ở quy mô lớn, cần dùng dữ liệu đủ lớn và phân bố gần workload thực tế.

### 9.1. Chạy EXPLAIN ANALYZE

    EXPLAIN ANALYZE
    SELECT
        c.customer_id,
        c.customer_name,
        o.order_id,
        o.total_amount
    FROM plan_customer_demo AS c
    JOIN plan_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN'
      AND o.order_status = 'PAID';

Đọc output theo thứ tự:

1. Xác định root iterator và số hàng cuối cùng.
2. Xác định iterator nào lọc customer theo country_code.
3. Xác định iterator truy cập order theo customer_id hoặc index khác.
4. Xem loops của iterator bên trong nested loop.
5. So sánh estimated rows với actual rows ở từng node.
6. Tìm node có startup time hoặc completion time lớn.

### 9.2. Thử một truy vấn có ORDER BY và LIMIT

    EXPLAIN ANALYZE
    SELECT
        order_id,
        order_date,
        total_amount
    FROM plan_order_demo
    WHERE order_status = 'PAID'
    ORDER BY total_amount DESC
    LIMIT 2;

Với schema hiện tại, index status không cung cấp thứ tự total_amount. Kế hoạch có thể cần sort. Thêm index phù hợp có thể thay đổi access path, nhưng chỉ có ích nếu workload và phân bố dữ liệu biện minh cho chi phí index:

    CREATE INDEX idx_order_status_amount
    ON plan_order_demo (order_status, total_amount);

Chạy lại EXPLAIN ANALYZE và so sánh:

- Iterator sort còn xuất hiện không?
- Mốc time đến hàng đầu tiên có thay đổi không?
- Số hàng thực tế được đọc/trả qua các iterator thay đổi ra sao?
- Index mới có làm tăng chi phí ghi không?

Không giả định index mới chắc chắn được chọn trên bảng mẫu nhỏ.

## 10. So sánh estimated rows và actual rows

EXPLAIN ANALYZE hiển thị ước lượng và số liệu thực tế cạnh nhau. Đây là cách tìm sai lệch cardinality:

    -> Index lookup on orders
       (cost=... rows=5)
       (actual time=... rows=500 loops=1)

Optimizer ước lượng khoảng 5 hàng nhưng iterator thực tế trả 500 hàng. Sai lệch 100 lần có thể ảnh hưởng quyết định join order và thuật toán join.

Một cách đánh giá đơn giản là tỷ lệ:

    estimate_error_ratio = max(estimated_rows, actual_rows)
                         / max(1, min(estimated_rows, actual_rows))

Đây chỉ là chỉ báo độ lớn sai lệch, không phải metric chính thức của MySQL. Cần tính trên cùng phạm vi và hiểu rows được báo theo mỗi loop.

### 10.1. So sánh đúng cơ sở khi loops > 1

Nếu output:

    rows=4 loops=100

thì 4 là trung bình mỗi loop, tổng hàng xấp xỉ 400. Khi so với estimated rows của iterator, hãy xác định estimate đang mô tả mỗi lần truy cập hay tổng qua query plan. Không nhân một phía mà quên phía còn lại.

Với nested loop, estimate của inner access thường được diễn giải theo một lần gọi, còn số loops cho biết số lần gọi. Đọc cả outer rows, inner rows và loops để hiểu tổng công việc.

### 10.2. Sai lệch ở node đầu có thể khuếch đại

Giả sử optimizer ước lượng outer iterator trả 10 khách hàng nhưng thực tế trả 10.000. Inner lookup có chi phí 0,1 ms mỗi lần. Kế hoạch dự kiến thực hiện khoảng 10 lần lookup nhưng thực tế phải thực hiện khoảng 10.000 lần.

Trong trường hợp này, nguyên nhân không nhất thiết nằm ở inner index. Sai lệch đầu tiên ở outer cardinality đã làm số loops tăng rất lớn. Hãy tìm node đầu tiên mà actual rows lệch đáng kể so với estimate thay vì chỉ sửa node cuối.

## 11. Đọc thời gian root và thời gian node con

Root iterator là node cuối cùng tạo ra kết quả của kế hoạch. Mốc completion ở root thường là chỉ báo hữu ích cho thời gian thực thi phía iterator của truy vấn trong phép đo EXPLAIN ANALYZE.

Node con giúp phân rã công việc:

- Scan/lookup: đọc dữ liệu đầu vào.
- Filter: loại bỏ hàng không thỏa điều kiện.
- Join: kết hợp hai luồng hàng.
- Aggregate: nhóm hoặc tính toán tổng hợp.
- Sort: sắp xếp dữ liệu.
- Materialize: tạo và lưu kết quả trung gian.
- Limit: dừng sau số hàng cần thiết.

Thời gian node cha có thể bao gồm thời gian gọi và tiêu thụ dữ liệu từ node con. Không cộng completion time của tất cả node để suy ra root time.

Nếu root hoàn tất nhanh nhưng ứng dụng vẫn chậm, kiểm tra các thành phần ngoài iterator:

- Thời gian lấy connection và gửi request.
- Network latency.
- Thời gian truyền/serialize kết quả trong giao thức.
- Client fetch và xử lý hàng.
- Thời gian chờ ở tầng ứng dụng.
- Queueing, connection pool và các service phụ thuộc.

EXPLAIN ANALYZE không thay thế distributed tracing hoặc đo latency end-to-end của ứng dụng.

## 12. Các yếu tố làm số liệu thay đổi giữa những lần chạy

Ngay cả khi SQL và schema không đổi, actual timing có thể khác nhau:

- Buffer pool và OS cache đã nóng hay chưa.
- Dữ liệu đã được đọc gần đây hay phải lấy từ storage.
- CPU contention và I/O contention.
- Background purge, checkpoint, flush và workload đồng thời.
- Lock wait hoặc metadata lock trong lúc truy cập.
- Kết quả truy vấn khác nhau do tham số bind khác.
- Thống kê hoặc kế hoạch đã thay đổi.
- Kết quả có số hàng lớn hơn hoặc nhỏ hơn.
- Overhead do instrumentation và chính EXPLAIN ANALYZE.

Đừng kết luận một thay đổi cải thiện hiệu năng chỉ từ một lần chạy. Dùng cùng dữ liệu, cùng tham số, cùng cấu hình và nhiều lần đo; so sánh median hoặc percentile phù hợp thay vì chọn lần nhanh nhất.

### 12.1. Warm cache và cold cache

Lần chạy đầu có thể phải đọc trang từ storage; các lần sau có thể lấy dữ liệu từ buffer pool. Vì vậy, lần chạy sau thường nhanh hơn mà không phải do kế hoạch tốt hơn.

Khi so sánh hai kế hoạch:

- Không xóa cache production chỉ để tạo cold run.
- Ghi rõ phép đo là warm-cache hay cold-cache.
- Chạy các phương án trong điều kiện tương đương.
- Xem cả logical work/rows/loops và thời gian.

Nếu kế hoạch A đọc ít hàng hơn nhưng thời gian một lần chạy dài hơn do cache lạnh, cần nhiều phép đo hơn trước khi kết luận.

### 12.2. Tham số có phân bố khác nhau

Một query với customer_id phổ biến có thể trả hàng nghìn đơn; customer_id hiếm chỉ trả vài đơn. Cùng câu SQL nhưng actual rows, loops và timing sẽ khác.

Hãy kiểm tra nhiều nhóm tham số đại diện:

- Giá trị hiếm.
- Giá trị phổ biến.
- Khoảng ngày hẹp.
- Khoảng ngày rộng.
- Trạng thái chiếm tỷ lệ thấp.
- Trạng thái chiếm tỷ lệ cao.

Không tối ưu query cho duy nhất một giá trị tham số nếu ứng dụng dùng nhiều phân bố khác nhau.

## 13. EXPLAIN ANALYZE và thời gian ứng dụng

Có ba khái niệm thời gian nên tách biệt:

| Khái niệm | Đo điều gì? | Công cụ phù hợp |
|---|---|---|
| Iterator startup time | Thời gian từ lúc iterator bắt đầu đến hàng đầu tiên | actual time mốc đầu |
| Iterator completion time | Thời gian từ lúc iterator bắt đầu đến khi trả hết hàng trong lần chạy | actual time mốc thứ hai |
| End-to-end latency | Thời gian ứng dụng quan sát từ lúc gửi request đến khi xử lý xong kết quả | APM, tracing hoặc đo tại client |

Root completion time hữu ích để phân tích phần thực thi iterator ở server, nhưng không phải SLA end-to-end. Một API có thể chậm vì pool connection, mạng, serialization hoặc client fetch dù root iterator chạy nhanh.

Ngược lại, ứng dụng có thể nhận kết quả nhanh một phần từ streaming iterator dù root completion time lớn vì còn nhiều hàng phía sau. Điều này quan trọng với API stream hoặc client đọc kết quả theo từng batch.

## 14. Các iterator có thể tạo độ trễ hàng đầu tiên

Một số iterator thường đáng xem khi mốc đầu lớn:

| Iterator/hoạt động | Lý do có thể chờ trước hàng đầu tiên |
|---|---|
| Sort | Cần đọc và xử lý nhiều đầu vào trước khi xác định hàng đầu |
| Materialize | Cần xây dựng kết quả trung gian trước khi đọc |
| Aggregate | Có thể cần đọc cả nhóm hoặc toàn bộ đầu vào trước khi trả kết quả |
| Hash join build side | Cần xây dựng hash table từ một phía trước khi probe |
| Temporary table | Có thể cần tạo/populate cấu trúc trung gian |
| Window operation | Một số khung tính toán cần xử lý và sắp xếp dữ liệu trước khi trả hàng |

Đây là các xu hướng, không phải quy tắc rằng mọi iterator cùng tên đều phải chờ toàn bộ input. Chi tiết phụ thuộc kế hoạch, thuật toán và khả năng streaming.

## 15. Tìm bottleneck từ actual metrics

Một quy trình phân tích thực tế:

1. Xác định root iterator và completion time.
2. Tìm node có actual time lớn, đồng thời xem nó là thời gian inclusive hay có node con lồng bên dưới.
3. Tìm startup delay lớn nếu ứng dụng cần hàng đầu tiên nhanh.
4. Xem node có nhiều loops và nhân với rows trung bình để ước lượng khối lượng hàng qua các lần gọi.
5. So sánh estimated rows và actual rows để phát hiện cardinality error.
6. Tìm node đầu tiên có sai lệch lớn.
7. Kiểm tra predicate, index, sort, materialization và join order liên quan.
8. Thay đổi từng yếu tố và đo lại trong cùng điều kiện.

Đừng chỉ chọn node có số milliseconds lớn nhất. Một node cha có thể bao gồm thời gian node con; một node có loops cao có thể có thời gian mỗi lần rất thấp. Phải kết hợp cấu trúc cây và số liệu.

## 16. Giới hạn và lưu ý an toàn của EXPLAIN ANALYZE

- EXPLAIN ANALYZE thực thi SELECT; truy vấn có thể đọc lượng dữ liệu lớn và gây tải.
- Nó không phải phép đo latency ứng dụng từ client đến client.
- Instrumentation có overhead; kết quả đo có thể khác chạy query bình thường.
- Output TREE và tên iterator có thể thay đổi giữa phiên bản.
- Actual rows là số hàng iterator trả, không phải mọi record đã examined.
- Timing và rows ở iterator nhiều loops là trung bình theo loop.
- Thời gian ở parent và child có thể chồng lấp; không cộng toàn cây.
- Truy vấn có locking read hoặc side effect qua function không nên được chạy thử nếu chưa hiểu tác động.
- Dùng staging hoặc bản sao dữ liệu khi truy vấn nặng hoặc cần lặp nhiều lần.
- Giới hạn khoảng thời gian và tham số để tránh quét ngoài dự kiến.

## 17. Những lỗi thường gặp

- Đọc mốc actual time thứ hai như thời gian sau hàng đầu tiên, thay vì thời gian hoàn tất tính từ lúc bắt đầu iterator.
- Nghĩ actual time=a..b là hai thời lượng độc lập cần cộng.
- Nghĩ rows là tổng số hàng khi loops lớn hơn 1.
- Nghĩ loops là số hàng hoặc số câu SQL do ứng dụng gửi.
- Quên nhân rows trung bình với loops khi hình dung tổng hàng qua các lần gọi.
- Nhân timing với loops rồi xem kết quả là wall-clock query time chính xác.
- Cộng thời gian parent và child trong cây để tính tổng.
- Nhầm actual rows với rows examined.
- Nghĩ hàng đầu tiên nhanh đồng nghĩa toàn truy vấn hoàn tất nhanh.
- Nghĩ startup time chỉ là chi phí khởi tạo một hàm riêng, không bao gồm xử lý iterator con.
- Nghĩ LIMIT luôn làm MySQL chỉ đọc đúng số hàng LIMIT.
- Không nhận ra sort/materialization có thể tạo startup delay.
- So sánh hai lần chạy với cache và tham số khác nhau.
- Chạy EXPLAIN ANALYZE truy vấn nặng trên production mà không đánh giá tải.
- Dùng EXPLAIN ANALYZE để thay thế đo latency end-to-end.

## 18. Checklist đọc actual rows, loops và timing

- Đã xác nhận phiên bản hỗ trợ EXPLAIN ANALYZE.
- Đã hiểu câu SELECT sẽ được thực thi và đánh giá tải trước khi chạy.
- Đã xác định root iterator và completion time.
- Đã đọc actual time=a..b đúng nghĩa: first row và completion.
- Đã ghi nhớ đơn vị thời gian là milliseconds.
- Đã đọc rows như số hàng trung bình mỗi loop.
- Đã đọc loops như số lần iterator được gọi.
- Đã ước lượng tổng hàng qua rows nhân loops khi cần.
- Đã xem loops của inner iterator trong nested loop.
- Đã phân biệt rows trả ra với rows examined.
- Đã đọc cây từ leaf lên root.
- Đã tránh cộng thời gian parent/child.
- Đã tìm startup delay ở sort, materialize, aggregate hoặc hash build nếu có.
- Đã so sánh estimated rows và actual rows trên cùng cơ sở.
- Đã tìm iterator đầu tiên có sai lệch lớn.
- Đã đo trong điều kiện cache, tham số và tải có thể so sánh.
- Đã phân biệt iterator timing với end-to-end latency của ứng dụng.
- Đã lưu output và ghi lại phiên bản/schema khi kết luận.

EXPLAIN ANALYZE biến kế hoạch ước lượng thành một cây iterator có số hàng, số lần gọi và thời gian thực tế. Mốc đầu của actual time cho biết độ trễ đến hàng đầu tiên; mốc thứ hai cho biết thời gian hoàn tất iterator tính từ lúc bắt đầu. rows và timing được lấy trung bình qua các loops, vì vậy cần đọc chúng cùng nhau, đặc biệt ở phía trong nested loop. Khi chẩn đoán, hãy đi từ leaf lên root, tìm sai lệch estimate/actual đầu tiên, nhận diện startup delay và tránh cộng thời gian các node lồng nhau. Cuối cùng, hãy xem số liệu iterator như công cụ phân tích thực thi phía server; latency end-to-end vẫn cần được đo ở tầng ứng dụng.
