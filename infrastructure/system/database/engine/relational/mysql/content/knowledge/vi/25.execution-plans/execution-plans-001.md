# EXPLAIN dạng bảng, FORMAT=JSON và FORMAT=TREE

Khi một truy vấn MySQL chạy chậm, cần biết máy chủ đang đọc bảng theo cách nào, dùng index nào, kết hợp các bảng theo thứ tự nào và ước lượng bao nhiêu dòng sẽ đi qua từng bước. Lệnh **EXPLAIN** cho phép xem kế hoạch mà optimizer dự định sử dụng. MySQL cung cấp nhiều cách biểu diễn kế hoạch: dạng bảng truyền thống, dạng JSON và dạng cây iterator.

Ba định dạng mô tả cùng một kế hoạch ở những mức độ chi tiết và cách trình bày khác nhau. Dạng bảng thuận tiện để kiểm tra nhanh access type và index; JSON biểu diễn cấu trúc lồng nhau và nhiều thông tin chi phí; TREE làm rõ thứ tự các iterator và cách dữ liệu đi qua các bước. Với MySQL 8.0.18 trở lên, **EXPLAIN ANALYZE** còn thực thi truy vấn SELECT và bổ sung số liệu thực tế để so sánh với ước lượng.

Bài học thuộc chương **Kế hoạch thực thi** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, khả năng đọc kế hoạch là nền tảng để xác định nút thắt, đánh giá index và tối ưu truy vấn dựa trên bằng chứng.

## 1. EXPLAIN cho biết điều gì?

MySQL optimizer phân tích câu SQL, thống kê bảng và index, điều kiện lọc, thứ tự join cùng các lựa chọn thực thi có thể có. Optimizer ước lượng chi phí cho các phương án rồi chọn một kế hoạch. EXPLAIN hiển thị kế hoạch được chọn tại thời điểm phân tích.

Cần phân biệt ba loại thông tin:

- **Access path**: cách MySQL tìm dòng trong từng bảng, ví dụ quét toàn bảng, quét index hoặc tìm theo một phạm vi index.
- **Join strategy**: cách kết hợp dòng giữa các bảng, thứ tự đọc bảng và thuật toán join.
- **Estimates**: số dòng, tỷ lệ lọc và chi phí mà optimizer dự kiến.

EXPLAIN thông thường không chạy câu SELECT để đo thời gian thực tế. Nó hiển thị ước lượng từ optimizer. Vì vậy, một kế hoạch trông có vẻ tốt vẫn có thể chậm nếu thống kê sai, dữ liệu lệch, cache khác dự kiến hoặc môi trường đang chịu tải cao.

Các định dạng thường dùng:

~~~sql
EXPLAIN
SELECT ...;
~~~

~~~sql
EXPLAIN FORMAT=JSON
SELECT ...;
~~~

~~~sql
EXPLAIN FORMAT=TREE
SELECT ...;
~~~

MySQL cũng cho phép chọn định dạng mặc định cho phiên bằng biến explain_format ở các phiên bản hỗ trợ. Trong tài liệu và quy trình điều tra, chỉ định FORMAT ngay trong câu lệnh thường dễ đọc và dễ tái lập hơn vì người xem biết chính xác đầu ra đang được yêu cầu.

## 2. Chuẩn bị ví dụ để đọc kế hoạch

Dùng ví dụ đơn giản với khách hàng và đơn hàng. Giả sử bảng đã có dữ liệu đủ lớn để các phương án truy cập khác nhau có ý nghĩa:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    region_code CHAR(2) NOT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE KEY uq_customers_email (email),
    KEY ix_customers_region (region_code)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    KEY ix_orders_customer_created (customer_id, created_at),
    KEY ix_orders_status_created (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
~~~

Các câu lệnh CREATE TABLE ở trên mô tả cấu trúc minh họa. Khi áp dụng vào hệ thống, hãy dùng đúng kiểu dữ liệu, tên bảng và ràng buộc của schema thực tế.

Truy vấn đại diện:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

Truy vấn này có điều kiện lọc ở cả hai bảng, phép join theo customer_id, khoảng thời gian trên orders và yêu cầu sắp xếp kết quả. Kế hoạch cần cho biết bảng nào được đọc trước, index nào được chọn, bao nhiêu dòng ước lượng đi qua mỗi bước và MySQL có phải sắp xếp bổ sung hay không.

Chạy cùng một câu SQL ở ba định dạng để so sánh:

~~~sql
EXPLAIN
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

Không giả định trước bảng customers hay orders sẽ được đọc trước. Optimizer có thể thay đổi thứ tự join dựa trên thống kê, index, điều kiện và giới hạn LIMIT. Hãy đọc kế hoạch trả về thay vì suy luận từ thứ tự bảng viết trong FROM.

## 3. Đọc EXPLAIN dạng bảng truyền thống

Kết quả EXPLAIN dạng bảng thường có các cột sau:

| Cột | Ý nghĩa khi đọc |
|---|---|
| id | Số định danh của SELECT block. |
| select_type | Loại SELECT block, ví dụ SIMPLE, PRIMARY, SUBQUERY, DERIVED hoặc UNION. |
| table | Bảng hoặc đối tượng được đọc ở bước này. Có thể là tên bảng, bí danh hoặc nhãn của bảng dẫn xuất. |
| partitions | Các partition được optimizer xem xét hoặc sử dụng, nếu bảng được partition. |
| type | Kiểu truy cập dữ liệu như const, eq_ref, ref, range, index hoặc ALL. |
| possible_keys | Các index có thể dùng cho bước truy cập. |
| key | Index thực tế được chọn. NULL nghĩa là không chọn index cho bước đó. |
| key_len | Độ dài phần index được sử dụng. |
| ref | Giá trị hoặc cột được so sánh với key để tìm dòng. |
| rows | Số dòng được ước lượng cần đọc ở bước này cho mỗi lần truy cập. |
| filtered | Tỷ lệ phần trăm dòng được ước lượng còn lại sau điều kiện lọc bổ sung. |
| Extra | Thông tin bổ sung về cách lọc, đọc index, join hoặc sắp xếp. |

### id và select_type

**id** giúp phân biệt các SELECT block trong truy vấn có subquery, derived table hoặc UNION. Với truy vấn đơn giản chỉ có một SELECT, thường chỉ có một id. Đừng hiểu id là thứ tự thời gian hoặc số thứ tự thực thi tuyệt đối của mọi thao tác.

**select_type** mô tả vai trò của SELECT block:

- **SIMPLE**: truy vấn đơn giản, không có subquery hoặc UNION phức tạp.
- **PRIMARY**: SELECT ngoài cùng của truy vấn phức tạp.
- **SUBQUERY**: subquery độc lập trong SELECT list hoặc điều kiện.
- **DEPENDENT SUBQUERY**: subquery phụ thuộc giá trị từ truy vấn bên ngoài, có thể được thực thi lặp theo dòng ngoài.
- **DERIVED**: bảng dẫn xuất được tạo từ subquery trong FROM.
- **MATERIALIZED**: subquery được materialize thành cấu trúc trung gian trong một số kế hoạch.
- **UNION** và **UNION RESULT**: các nhánh UNION và bước kết hợp kết quả.

Tên và cách biểu diễn có thể khác nhau tùy cấu trúc truy vấn và phiên bản. Với truy vấn join đơn giản ở ví dụ trên, các dòng thường có select_type là SIMPLE.

### type: kiểu truy cập dữ liệu

Cột **type** là một trong những tín hiệu quan trọng nhất, nhưng không nên biến nó thành thang điểm máy móc. Cần xem số dòng, index, điều kiện và chi phí cùng lúc.

Một số giá trị thường gặp:

| type | Cách truy cập | Cách diễn giải |
|---|---|---|
| system | Bảng hệ thống có một dòng | Trường hợp rất nhỏ, hiếm gặp. |
| const | Tìm tối đa một dòng qua khóa PRIMARY hoặc UNIQUE với điều kiện hằng | Thường rất hiệu quả. |
| eq_ref | Với mỗi tổ hợp dòng trước đó, tìm đúng một dòng qua PRIMARY/UNIQUE | Phổ biến trong join khóa duy nhất. |
| ref | Tìm các dòng khớp một giá trị qua index không duy nhất | Có thể tốt nếu số dòng khớp nhỏ. |
| ref_or_null | Tìm giá trị bằng và cả NULL qua index | Dùng cho một số điều kiện có OR IS NULL. |
| range | Đọc một phạm vi index | Thường gặp với BETWEEN, so sánh lớn/nhỏ hoặc IN. |
| index | Quét toàn bộ index | Đọc mọi entry của index; không đồng nghĩa chỉ đọc một dòng. |
| ALL | Quét toàn bảng | Có thể hợp lý với bảng nhỏ hoặc truy vấn cần phần lớn dòng; cần điều tra khi bảng lớn. |

MySQL còn có thể hiển thị các dạng như index_merge, fulltext, unique_subquery hoặc index_subquery. Hãy đọc tài liệu đúng phiên bản khi gặp kiểu ít phổ biến.

Một truy vấn dùng ALL chưa chắc là lỗi. Nếu bảng chỉ có vài chục dòng hoặc điều kiện trả về gần hết bảng, full scan có thể rẻ hơn việc duyệt index rồi đọc lại nhiều dòng. Ngược lại, ALL trên bảng lớn với điều kiện chỉ khớp vài dòng là tín hiệu cần kiểm tra index và thống kê.

### possible_keys, key và key_len

**possible_keys** liệt kê các index optimizer cân nhắc cho bước truy cập. **key** cho biết index thực tế được chọn. Nếu possible_keys có index nhưng key là NULL, optimizer đã quyết định không dùng các ứng viên đó theo ước lượng chi phí hiện tại.

**key_len** biểu diễn độ dài phần key được sử dụng, tính theo byte. Với index ghép, giá trị này giúp xem optimizer đã sử dụng bao nhiêu phần của index. Tuy nhiên, không thể chỉ nhìn key_len rồi kết luận chính xác cột nào được dùng nếu không xét kiểu dữ liệu, nullable, charset và cấu trúc index. Đối chiếu thêm với SHOW INDEX hoặc FORMAT=JSON.

### rows và filtered

**rows** là ước lượng số dòng MySQL cần đọc ở bước truy cập. Nó không phải số dòng cuối cùng trả về cho ứng dụng và cũng không phải số đo thực tế.

**filtered** là tỷ lệ phần trăm dòng được ước lượng còn lại sau các điều kiện lọc bổ sung. Có thể dùng tích rows × filtered / 100 để hình dung gần đúng số dòng ước lượng được chuyển tiếp từ bước đó, nhưng đây chỉ là phép diễn giải sơ bộ, không phải số đo runtime.

Ví dụ, nếu rows là 10.000 và filtered là 5, optimizer ước lượng khoảng 500 dòng còn lại sau bước lọc đó. Nếu ước lượng thực tế chênh lệch lớn, cần kiểm tra thống kê, histogram, phân bố lệch và cách viết điều kiện.

### Extra

Một số giá trị trong Extra cần nhận diện:

- **Using where**: có điều kiện WHERE được áp dụng để lọc dòng. Điều này không tự động có nghĩa truy vấn chậm.
- **Using index**: truy vấn có thể lấy các cột cần thiết trực tiếp từ index (covering index), không cần đọc thêm dòng trong clustered index cho bước đó.
- **Using index condition**: Index Condition Pushdown (ICP) cho phép kiểm tra một phần điều kiện ngay trong quá trình đọc index, giảm số dòng phải đọc đầy đủ từ bảng.
- **Using temporary**: MySQL dùng bảng tạm cho một bước như GROUP BY hoặc DISTINCT. Bảng tạm không nhất thiết nằm trên đĩa.
- **Using filesort**: MySQL cần một bước sắp xếp bổ sung. Tên filesort không có nghĩa chắc chắn đã ghi file ra đĩa; việc sắp xếp có thể diễn ra trong bộ nhớ.
- **Using join buffer**: dùng join buffer cho một chiến lược join; một số phiên bản/kế hoạch có thể hiển thị hash join.
- **Using where; Using index**: có thể vừa lọc điều kiện vừa chỉ đọc từ index.

Không nên tối ưu chỉ bằng cách loại bỏ chữ Using filesort hoặc Using temporary. Hãy xem số dòng tham gia, kích thước dữ liệu, loại truy vấn và thời gian thực tế. Một bước sắp xếp trên 50 dòng có thể không đáng lo; sắp xếp hàng triệu dòng mới là vấn đề cần đo.

## 4. Đọc FORMAT=JSON

FORMAT=JSON biểu diễn kế hoạch theo cấu trúc đối tượng lồng nhau. Cách này hữu ích khi truy vấn có nhiều join, subquery, derived table hoặc nhiều bước xử lý mà bảng truyền thống khó thể hiện rõ quan hệ cha-con.

Chạy:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

JSON thường có một đối tượng **query_block** ở cấp cao nhất. Bên trong có thể gặp:

- **select_id**: tương ứng SELECT block.
- **cost_info**: thông tin chi phí ước lượng.
- **table**: mô tả bước truy cập một bảng.
- **nested_loop**: các bảng được kết hợp theo cấu trúc nested-loop.
- **ordering_operation**: bước xử lý ORDER BY.
- **grouping_operation**: bước xử lý GROUP BY.
- **materialized_from_subquery**: nguồn subquery đã được materialize.
- **attached_subqueries**: subquery gắn với một bước trong kế hoạch.

Trong đối tượng table, các trường quan trọng có thể gồm:

| Trường JSON | Ý nghĩa |
|---|---|
| table_name | Bảng hoặc bí danh đang được đọc. |
| access_type | Kiểu truy cập tương ứng với type trong dạng bảng. |
| possible_keys | Các index ứng viên. |
| key | Index được chọn. |
| used_key_parts | Các phần/cột index được dùng. |
| key_length | Độ dài key được dùng. |
| ref | Giá trị tham chiếu khi truy cập qua index. |
| rows_examined_per_scan | Số dòng ước lượng được đọc mỗi lần quét. |
| rows_produced_per_join | Số dòng ước lượng được tạo ra sau bước join hiện tại. |
| filtered | Tỷ lệ phần trăm ước lượng còn lại sau lọc. |
| attached_condition | Điều kiện được gắn vào bước truy cập. |
| index_condition | Điều kiện có thể được kiểm tra trong quá trình đọc index, nếu có. |
| using_index | Cho biết có thể dùng covering index. |
| cost_info | Chi tiết chi phí đọc, đánh giá và chi phí tích lũy. |

Một ví dụ rút gọn về cấu trúc JSON để nhận diện:

~~~json
{
  "query_block": {
    "select_id": 1,
    "nested_loop": [
      {
        "table": {
          "table_name": "c",
          "access_type": "ref",
          "possible_keys": ["ix_customers_region"],
          "key": "ix_customers_region",
          "used_key_parts": ["region_code"],
          "rows_examined_per_scan": 120,
          "filtered": 100
        }
      },
      {
        "table": {
          "table_name": "o",
          "access_type": "ref",
          "possible_keys": ["ix_orders_customer_created"],
          "key": "ix_orders_customer_created",
          "used_key_parts": ["customer_id"],
          "rows_examined_per_scan": 8,
          "filtered": 10
        }
      }
    ]
  }
}
~~~

Đây là ví dụ minh họa cấu trúc, không phải kết quả cố định từ schema ở mục 2. Số dòng và index thực tế phụ thuộc dữ liệu, thống kê, phiên bản và optimizer.

### Hiểu nested_loop

Với nested-loop join, MySQL lấy dòng từ bảng ngoài rồi dùng giá trị của dòng đó để tìm dòng phù hợp ở bảng trong. Vì vậy, thứ tự phần tử trong nested_loop rất quan trọng. Nếu bảng ngoài tạo ra quá nhiều dòng, bước truy cập bảng trong có thể được lặp lại rất nhiều lần.

Ví dụ, bảng customers tạo ra 100.000 dòng sau lọc; với mỗi khách hàng, MySQL tìm orders. Nếu mỗi lần tìm đọc trung bình 20 dòng, lượng công việc ở bảng trong có thể lớn. Khi đọc JSON, hãy xem rows_examined_per_scan và rows_produced_per_join, đồng thời xem index dùng cho điều kiện join.

Không nên cộng các giá trị rows_examined_per_scan như thể mọi bước chỉ chạy một lần. Trong join lồng nhau, một bước trong có thể được thực hiện lặp theo từng dòng từ bước ngoài. FORMAT=TREE và EXPLAIN ANALYZE giúp nhìn rõ hơn cấu trúc này.

### Đọc cost_info

cost_info thường chứa các ước lượng như:

- **read_cost**: chi phí ước lượng để đọc dữ liệu.
- **eval_cost**: chi phí ước lượng để đánh giá điều kiện trên các dòng.
- **prefix_cost**: chi phí tích lũy đến bước hiện tại.
- **data_read_per_join**: lượng dữ liệu ước lượng cần đọc cho join.

Đây là đơn vị chi phí nội bộ của optimizer, không phải mili giây. Không dùng query_cost hoặc prefix_cost để khẳng định một truy vấn mất bao nhiêu thời gian. Hãy dùng chúng để so sánh các kế hoạch trong cùng bối cảnh, sau đó đo runtime bằng công cụ phù hợp.

## 5. Đọc FORMAT=TREE

FORMAT=TREE trình bày kế hoạch theo các iterator. Mỗi nhánh thể hiện một bước lấy dữ liệu hoặc xử lý dữ liệu; các bước bên dưới cung cấp đầu vào cho bước phía trên.

Chạy:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

Một đầu ra minh họa có thể trông như sau:

~~~text
-> Limit: 50 row(s)
    -> Sort: o.created_at DESC
        -> Nested loop inner join
            -> Index lookup on c using ix_customers_region
               (region_code='VN')
            -> Filter: (o.status = 'PAID')
                -> Index lookup on o using ix_orders_customer_created
                   (customer_id=c.customer_id)
~~~

Đây là sơ đồ khái niệm để đọc cấu trúc, không phải output được bảo đảm cho truy vấn ví dụ. Optimizer có thể chọn thứ tự join, index, range scan, hash join hoặc cách sắp xếp khác tùy dữ liệu.

Khi đọc TREE:

1. Bắt đầu từ iterator gốc ở trên cùng để hiểu kết quả cuối cùng cần tạo ra.
2. Lần xuống các iterator con để xem dữ liệu được lấy từ đâu.
3. Xác định iterator nào lọc dòng, iterator nào join, iterator nào sort hoặc aggregate.
4. Kiểm tra index lookup hoặc table scan ở các nhánh lá.
5. Xem ước lượng số dòng và chi phí để tìm bước có khả năng tạo ra nhiều công việc.

Một số iterator thường gặp:

- **Table scan**: đọc các dòng từ bảng.
- **Index range scan**: đọc một phạm vi trong index.
- **Index lookup**: tìm dòng qua một giá trị key.
- **Filter**: loại bỏ dòng không thỏa điều kiện.
- **Nested loop**: lấy dòng từ một nhánh rồi tìm dòng khớp ở nhánh khác.
- **Hash join**: xây dựng và tra cứu cấu trúc hash để kết hợp hai tập dòng.
- **Sort**: sắp xếp dòng theo thứ tự yêu cầu.
- **Aggregate**: tính kết quả tổng hợp.
- **Limit/Offset**: giới hạn hoặc bỏ qua dòng ở đầu ra.

TREE giúp hình dung thứ tự xử lý tốt hơn bảng truyền thống, đặc biệt với join và các bước xử lý lồng nhau. Tuy nhiên, nó vẫn là kế hoạch ước lượng nếu chỉ chạy EXPLAIN FORMAT=TREE.

## 6. EXPLAIN ANALYZE: so sánh ước lượng với thực tế

Từ MySQL 8.0.18, có thể dùng EXPLAIN ANALYZE để thực thi SELECT và hiển thị số liệu runtime theo iterator. Định dạng đầu ra là TREE.

~~~sql
EXPLAIN ANALYZE
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.email
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'VN'
  AND o.status = 'PAID'
  AND o.created_at >= '2026-10-01'
  AND o.created_at <  '2026-11-01'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

Một iterator trong EXPLAIN ANALYZE có thể hiển thị thông tin dạng:

~~~text
(actual time=0.050..1.200 rows=40 loops=100)
~~~

Ý nghĩa:

- **actual time**: thời gian thực tế của iterator từ khi tạo dòng đầu tiên đến khi hoàn thành phần dòng được xử lý, thường hiển thị trung bình theo mỗi lần lặp.
- **rows**: số dòng thực tế trung bình được iterator tạo ra trong một lần lặp.
- **loops**: số lần iterator được gọi.

Khi iterator được lặp nhiều lần, đừng nhìn riêng rows mà bỏ qua loops. Ví dụ rows=40 và loops=100 có nghĩa iterator tạo trung bình 40 dòng mỗi lần gọi, tổng cộng xấp xỉ 4.000 dòng qua các lần gọi. Với thời gian, cũng cần xét loops để hiểu tổng công việc. Các số liệu là phép đo của lần chạy đó và có thể thay đổi do cache, tải hệ thống và dữ liệu.

So sánh estimated rows trong EXPLAIN với actual rows trong EXPLAIN ANALYZE:

- Nếu ước lượng 10 dòng nhưng thực tế 10.000 dòng, optimizer đánh giá thấp quy mô công việc rất nhiều.
- Nếu ước lượng 50.000 dòng nhưng thực tế 100 dòng, optimizer đánh giá cao lượng dữ liệu phải xử lý.
- Nếu sai lệch xuất hiện ở iterator đầu tiên, hãy kiểm tra thống kê bảng, cardinality, histogram và điều kiện lọc.
- Nếu các iterator đầu gần đúng nhưng số dòng tăng mạnh sau join, hãy xem quan hệ join, tính duy nhất của khóa và phân bố dữ liệu giữa các bảng.
- Nếu số dòng phù hợp nhưng thời gian cao, cần xem I/O, truy cập clustered index, sort, temporary table, CPU và mức độ tranh chấp tài nguyên.

EXPLAIN ANALYZE thực sự chạy câu SELECT đến khi hoàn tất. Truy vấn có thể đọc rất nhiều dữ liệu hoặc gọi biểu thức tốn kém; hãy giới hạn phạm vi, chọn thời điểm phù hợp và cân nhắc chạy trên môi trường kiểm thử hoặc replica. Không dùng EXPLAIN ANALYZE cho câu lệnh ghi với giả định nó chỉ mô phỏng; cú pháp này được thiết kế để đo thực thi truy vấn SELECT.

## 7. Đọc một kế hoạch join theo từng bước

Khi truy vấn có nhiều bảng, hãy phân tích theo trình tự sau.

**Bước 1 — Xác định bảng được đọc đầu tiên**

Trong bảng truyền thống, xem thứ tự các dòng và id. Trong JSON, xem các phần tử nested_loop hoặc cấu trúc query_block. Trong TREE, xem iterator con nào cung cấp dữ liệu đầu vào cho join.

Bảng được đọc đầu tiên thường quyết định số dòng đầu vào cho các bước sau. Nếu điều kiện lọc trên bảng ngoài quá rộng, những bước join tiếp theo có thể bị lặp nhiều lần.

**Bước 2 — Xác định cách truy cập bảng kế tiếp**

Với mỗi bảng, kiểm tra type/access_type, key, key_len hoặc used_key_parts. Trong join theo khóa ngoại, kiểm tra index trên cột tham chiếu ở bảng con. Index phù hợp có thể biến việc tìm dòng khớp thành ref hoặc eq_ref thay vì quét nhiều dòng.

**Bước 3 — Kiểm tra số dòng qua mỗi bước**

So sánh rows, filtered, rows_produced_per_join và actual rows. Đặc biệt chú ý bước mà số dòng tăng mạnh hoặc ước lượng sai lệch lớn. Một phép join tạo ra nhiều dòng trung gian có thể là nguyên nhân chính dù từng lần lookup riêng lẻ có vẻ nhanh.

**Bước 4 — Kiểm tra sort và aggregate**

ORDER BY, GROUP BY và DISTINCT có thể tạo bước sort hoặc temporary table. Kiểm tra Extra trong dạng bảng, ordering_operation/grouping_operation trong JSON và iterator Sort/Aggregate trong TREE. Xem có thể dùng index theo thứ tự phù hợp hay không, nhưng vẫn cần đo lợi ích so với chi phí index.

**Bước 5 — Kiểm tra LIMIT**

LIMIT có thể cho phép MySQL dừng sớm khi thứ tự và access path phù hợp. Nhưng nếu phải đọc hoặc sắp xếp một tập lớn trước khi lấy 50 dòng đầu, LIMIT không tự động làm truy vấn rẻ. Xem TREE để xác định Limit nằm trên bước nào và có thể dừng iterator con sớm hay không.

## 8. Từ kế hoạch đến quyết định tối ưu

Một kế hoạch là bằng chứng để đặt câu hỏi, không phải chỉ dẫn tự động rằng phải tạo index mới. Dùng các tín hiệu sau để chọn bước điều tra:

| Tín hiệu | Câu hỏi cần kiểm tra |
|---|---|
| type = ALL trên bảng lớn | Có index phù hợp với điều kiện WHERE hoặc JOIN không? Điều kiện có chọn lọc không? |
| key = NULL | Index có thiếu, không phù hợp tiền tố hoặc có chi phí cao hơn full scan không? |
| rows ước lượng rất lớn | Điều kiện lọc có thực sự thu hẹp dữ liệu không? Có cần index ghép không? |
| estimated rows lệch mạnh actual rows | Thống kê có cũ? Dữ liệu có skew? Histogram có phù hợp? |
| iterator trong join có loops rất cao | Bảng ngoài có tạo quá nhiều dòng? Bảng trong có index lookup phù hợp? |
| Using temporary hoặc Sort | Sắp xếp/aggregate có xử lý quá nhiều dòng? Có thể tận dụng index không? |
| Using filesort | Có cần thứ tự kết quả đó không? Index có thể hỗ trợ ORDER BY không? |
| covering index chưa được dùng | Truy vấn có lấy thêm cột ngoài index? Chi phí index có đáng không? |

Một quy trình thực tế:

1. Ghi lại SQL, tham số, độ trễ, tần suất chạy và số dòng trả về.
2. Chạy EXPLAIN dạng bảng để xem nhanh access type, key, rows và Extra.
3. Chạy FORMAT=JSON để hiểu cấu trúc join, điều kiện gắn với từng bước và cost_info.
4. Chạy FORMAT=TREE để hình dung luồng iterator.
5. Dùng EXPLAIN ANALYZE trên SELECT phù hợp để so sánh ước lượng với số liệu thực tế.
6. Xác định bước tạo ra nhiều dòng hoặc tiêu tốn thời gian nhất.
7. Kiểm tra index, thống kê, histogram, điều kiện join và cách viết truy vấn.
8. Thử một thay đổi tại một thời điểm rồi đo lại bằng cùng tham số và điều kiện tương đương.

Không nên chỉ tối ưu truy vấn bằng cách giảm số dòng trong một iterator mà bỏ qua số lần lặp. Một lookup 1 ms được thực hiện 100.000 lần có thể tốn hơn một scan 50 ms chỉ chạy một lần. Hãy đọc rows và loops cùng nhau.

## 9. Một số lệnh hữu ích khi điều tra

### Xem kế hoạch và index hiện tại

~~~sql
EXPLAIN SELECT ...;
SHOW INDEX FROM orders;
ANALYZE TABLE orders;
~~~

ANALYZE TABLE cập nhật thống kê; nó không phải lệnh đo thời gian thực thi của câu truy vấn. Sau khi làm mới thống kê, chạy lại EXPLAIN và so sánh.

### Xem kế hoạch của câu lệnh đang chạy trên connection khác

Trong một số tình huống vận hành, có thể dùng:

~~~sql
EXPLAIN FOR CONNECTION 123;
~~~

Thay 123 bằng connection ID cần kiểm tra. Cần quyền phù hợp để quan sát connection khác. Kế hoạch chỉ có thể xem khi connection đang thực thi câu lệnh có thể giải thích; nếu câu lệnh đã kết thúc hoặc trạng thái không còn phù hợp, lệnh có thể không trả được kế hoạch hữu ích. Không nhầm connection ID với THREAD_ID của Performance Schema.

### Xem cảnh báo hoặc thông tin bổ sung sau EXPLAIN

Có thể dùng SHOW WARNINGS sau EXPLAIN khi cần kiểm tra thông tin mở rộng mà MySQL cung cấp cho câu lệnh vừa phân tích:

~~~sql
EXPLAIN SELECT *
FROM orders
WHERE customer_id = 1001;

SHOW WARNINGS;
~~~

SHOW WARNINGS phải được chạy trong cùng session ngay sau câu lệnh cần kiểm tra vì nó hiển thị cảnh báo của các câu lệnh gần nhất trong session đó.

## 10. Những lỗi đọc kế hoạch thường gặp

**Thấy type = ALL là kết luận truy vấn sai.** Full scan có thể là phương án rẻ nhất với bảng nhỏ hoặc truy vấn lấy phần lớn dữ liệu. Cần xét rows, filtered, chi phí và actual runtime.

**Thấy key khác NULL là kết luận truy vấn đã tối ưu.** Một index vẫn có thể đọc hàng trăm nghìn entry, tạo nhiều lần truy cập clustered index hoặc không hỗ trợ sort. Hãy kiểm tra số dòng và thời gian.

**Nhầm rows với số dòng trả về.** rows là ước lượng dòng đọc ở bước truy cập; filtered mô tả tỷ lệ còn lại. Số dòng cuối cùng phụ thuộc các bước lọc và join tiếp theo.

**Coi cost là mili giây.** Cost là mô hình nội bộ để optimizer so sánh phương án. Dùng EXPLAIN ANALYZE hoặc công cụ đo runtime để xem thời gian thực tế.

**Đọc JSON như danh sách phẳng.** JSON có cấu trúc lồng nhau; nested_loop và query_block biểu diễn quan hệ giữa các bước. Cần giữ nguyên quan hệ cha-con khi đọc.

**Coi TREE là số liệu thực thi.** EXPLAIN FORMAT=TREE vẫn là kế hoạch ước lượng. Chỉ EXPLAIN ANALYZE mới bổ sung thời gian, rows và loops thực tế.

**Bỏ qua loops trong EXPLAIN ANALYZE.** Một iterator trả ít dòng mỗi lần nhưng được gọi rất nhiều lần vẫn có thể là nút thắt. Đánh giá rows, loops và actual time cùng nhau.

**Cho rằng Using filesort luôn ghi ra đĩa.** Filesort là tên của cơ chế sắp xếp bổ sung; nó có thể chạy trong bộ nhớ. Hãy đánh giá quy mô và thời gian thực tế.

**Cho rằng LIMIT 50 luôn chỉ đọc 50 dòng.** Nếu phải sort hoặc lọc một tập lớn trước khi lấy 50 dòng, công việc phía dưới LIMIT vẫn có thể lớn.

**Chạy EXPLAIN ANALYZE trên truy vấn không kiểm soát phạm vi.** Lệnh thực thi truy vấn thật. Một SELECT lớn có thể tiêu tốn tài nguyên production; cần hiểu truy vấn trước khi chạy.

## 11. Bài thực hành

Dùng schema thử nghiệm có customers và orders như mục 2.

1. Chạy EXPLAIN dạng bảng cho truy vấn join. Ghi lại thứ tự bảng, type, possible_keys, key, rows, filtered và Extra.
2. Chạy EXPLAIN FORMAT=JSON. Tìm query_block, nested_loop, table_name, access_type, key và cost_info. So sánh thứ tự join với kết quả dạng bảng.
3. Chạy EXPLAIN FORMAT=TREE. Vẽ lại các iterator từ nhánh lấy dữ liệu đến join, sort và limit.
4. Thêm hoặc thay đổi index thử nghiệm trên bảng orders theo truy vấn lọc status và created_at. Chạy lại cả ba định dạng và ghi nhận thay đổi.
5. Dùng EXPLAIN ANALYZE trên truy vấn SELECT giới hạn phạm vi. So sánh estimated rows với actual rows và loops ở từng iterator.
6. Tạo phân bố dữ liệu lệch cho status, ví dụ một trạng thái chiếm phần lớn và một trạng thái rất hiếm. So sánh kế hoạch cho từng giá trị.
7. Chạy ANALYZE TABLE rồi kiểm tra lại EXPLAIN. Ghi nhận liệu ước lượng có thay đổi và kế hoạch có cải thiện không.
8. Giải thích vì sao một kế hoạch có key vẫn có thể chậm và vì sao một kế hoạch có ALL đôi khi lại hợp lý.

Kết thúc thực hành, khôi phục schema thử nghiệm hoặc xóa các index chỉ được tạo cho bài tập.

## 12. Checklist đọc EXPLAIN

Trước khi đề xuất tối ưu, hãy bảo đảm đã trả lời:

- Truy vấn có bao nhiêu SELECT block và bảng tham gia?
- Bảng nào được đọc trước và thứ tự join là gì?
- Mỗi bảng dùng access type nào?
- Index nào là possible_keys và index nào thực sự được chọn?
- Bao nhiêu phần của index ghép được sử dụng?
- rows và filtered ước lượng quy mô dòng ra sao?
- Có điều kiện nào được áp dụng tại bước index hoặc sau khi đọc dòng?
- Có sort, temporary table, grouping hoặc materialization không?
- Trong JSON, nested_loop và query_block cho thấy quan hệ bước như thế nào?
- Trong TREE, iterator nào tạo nhiều đầu vào hoặc nằm trên đường xử lý tốn kém?
- Estimated rows có gần actual rows không?
- Iterator có loops cao không?
- Thay đổi index hoặc thống kê có cải thiện toàn bộ workload không?

EXPLAIN dạng bảng giúp đọc nhanh, JSON giúp xem cấu trúc và chi phí chi tiết, còn TREE giúp hình dung luồng iterator. Khi kết hợp cả ba với EXPLAIN ANALYZE, bạn có thể đi từ kế hoạch optimizer dự kiến đến bằng chứng thực thi thực tế, xác định đúng bước gây tốn kém và chọn thay đổi có cơ sở.
