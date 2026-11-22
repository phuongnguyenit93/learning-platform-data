# Loại bỏ phân vùng (partition pruning) và điều kiện truy vấn phù hợp

Phân vùng dữ liệu chia một bảng logic thành nhiều phần vật lý theo một hoặc nhiều khóa phân vùng. Khi truy vấn có điều kiện phù hợp với khóa và ranh giới phân vùng, hệ quản trị có thể loại bỏ những phân vùng chắc chắn không chứa hàng cần tìm. Cơ chế này gọi là partition pruning hoặc partition elimination. Nếu truy vấn không thể xác định phạm vi phân vùng từ predicate, DBMS có thể phải mở và quét nhiều phân vùng, dù mỗi phân vùng đều có index.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Phân vùng dữ liệu** giúp người học hiểu cách loại bỏ phân vùng và viết điều kiện truy vấn phù hợp với khóa phân vùng. Bài học trình bày cách partition pruning dựa trên ranh giới RANGE, LIST và HASH; cách kiểu dữ liệu, phép chuyển đổi, hàm, biểu thức OR, tham số và phép nối ảnh hưởng đến khả năng pruning; đồng thời hướng dẫn đọc execution plan và đo số phân vùng thực sự được truy cập.

Sau bài học, người học có thể:

- Giải thích partition pruning và phân biệt nó với index seek/scan.
- Viết predicate trực tiếp trên partition key để giới hạn phạm vi dữ liệu.
- Chọn điều kiện nửa mở cho truy vấn theo khoảng thời gian.
- Nhận diện hàm, cast, phép tính hoặc kiểu dữ liệu không phù hợp có thể cản trở pruning.
- Hiểu khác biệt giữa RANGE, LIST và HASH partitioning khi xác định phân vùng cần đọc.
- Phân biệt pruning tại thời điểm lập kế hoạch với pruning khi thực thi.
- Đọc dấu hiệu partition elimination trong PostgreSQL, SQL Server, MySQL và Oracle.
- Đánh giá pruning qua JOIN, tham số bind, prepared statement và truy vấn nhiều bảng.
- Xác định khi nào index cục bộ hoặc toàn cục vẫn cần thiết sau khi đã pruning.
- Kiểm chứng lợi ích bằng số phân vùng, số trang đọc, độ trễ và tải ghi.

## 1. Partition pruning là gì?

### 1.1. Bảng phân vùng vẫn là một bảng logic

Ứng dụng có thể truy vấn một bảng logic như **events**, trong khi DBMS lưu dữ liệu ở nhiều phân vùng con. Mỗi phân vùng quản lý một phần miền giá trị của khóa phân vùng hoặc một phần dữ liệu được ánh xạ theo quy tắc hash.

Ví dụ, bảng sự kiện được phân vùng theo tháng của **occurred_at**:

~~~sql
CREATE TABLE events (
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload TEXT
) PARTITION BY RANGE (occurred_at);

CREATE TABLE events_2026_01
PARTITION OF events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE events_2026_02
PARTITION OF events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE events_2026_03
PARTITION OF events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
~~~

Truy vấn trên bảng cha vẫn dùng tên **events**. DBMS xác định phân vùng nào có thể chứa giá trị cần tìm dựa trên điều kiện và ranh giới đã khai báo.

~~~sql
SELECT event_id, occurred_at, event_type
FROM events
WHERE occurred_at >= TIMESTAMP '2026-02-10 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-11 00:00:00';
~~~

Với phân vùng tháng, chỉ phân vùng tháng 02/2026 cần được truy cập. Các phân vùng tháng 01 và tháng 03 có thể bị loại bỏ vì ranh giới của chúng không giao với khoảng truy vấn.

### 1.2. Loại bỏ phân vùng trước khi đọc hàng

Partition pruning sử dụng metadata về ranh giới hoặc ánh xạ phân vùng để xác định phần dữ liệu không thể chứa kết quả. Khi một phân vùng bị loại bỏ, DBMS không cần scan bảng con hoặc index của phân vùng đó.

Cần phân biệt ba tầng quyết định:

1. **Pruning:** chọn phân vùng có thể chứa hàng phù hợp.
2. **Access path bên trong phân vùng:** dùng sequential/table scan, B-tree index, bitmap hoặc cách truy cập khác.
3. **Filter:** kiểm tra các điều kiện còn lại trên hàng được đọc.

Ví dụ, predicate theo ngày có thể giữ lại một phân vùng tháng. Bên trong phân vùng tháng đó, điều kiện **tenant_id = 42** vẫn có thể cần B-tree index hoặc scan tùy độ chọn lọc và thống kê.

Pruning làm giảm phạm vi dữ liệu phải xét, nhưng không bảo đảm truy vấn trong phân vùng còn lại sẽ nhanh. Nếu một phân vùng chứa hàng trăm triệu dòng và predicate không có index phù hợp, DBMS vẫn có thể phải scan nhiều dữ liệu trong phân vùng đó.

### 1.3. Pruning khác với index lookup

| Cơ chế | Phạm vi hoạt động | Tác dụng |
|---|---|---|
| Partition pruning | Giữa các phân vùng | Loại bỏ toàn bộ phân vùng không thể chứa kết quả |
| Index seek/scan | Bên trong một bảng hoặc phân vùng | Tìm các khóa hoặc hàng phù hợp |
| Filter | Trên các hàng đã được truy cập | Loại các hàng không thỏa điều kiện |
| Partition-wise join | Giữa các tập phân vùng tương ứng | Có thể nối từng cặp phân vùng thay vì xử lý toàn bộ hai bảng cùng lúc |

Một truy vấn có thể pruning còn một phân vùng rồi dùng index scan bên trong phân vùng đó. Cũng có truy vấn không loại bỏ được phân vùng nào, hoặc vẫn phải scan toàn bộ các phân vùng vì không có điều kiện trên partition key.

### 1.4. Vì sao pruning quan trọng với bảng lớn?

Bảng phân vùng thường được dùng cho dữ liệu theo thời gian, tenant, vùng hoặc nhóm nghiệp vụ. Nếu truy vấn chỉ cần một khoảng nhỏ nhưng DBMS phải mở mọi phân vùng, chi phí có thể tăng theo số lượng phân vùng:

- Nhiều bảng con hoặc segment cần được xét.
- Nhiều index cục bộ cần được kiểm tra.
- Nhiều trang dữ liệu có thể được đọc.
- Tăng số lần mở quan hệ, metadata và iterator trong kế hoạch.
- Tăng CPU để hợp nhất kết quả.
- Tăng áp lực cache và I/O.
- Tăng thời gian lập kế hoạch với thiết kế có quá nhiều phân vùng.

Partition pruning giúp giảm phạm vi truy cập, nhưng hiệu quả phụ thuộc vào việc predicate có khớp với cách phân vùng hay không.

## 2. Hiểu khóa phân vùng và ranh giới

### 2.1. RANGE partitioning

RANGE chia dữ liệu thành các khoảng giá trị không chồng lấn. Thường dùng cho ngày, thời gian, số thứ tự hoặc giá trị tăng dần.

Ví dụ:

- Phân vùng tháng 01 chứa [2026-01-01, 2026-02-01).
- Phân vùng tháng 02 chứa [2026-02-01, 2026-03-01).
- Phân vùng tháng 03 chứa [2026-03-01, 2026-04-01).

Điều kiện khoảng trực tiếp trên khóa có thể loại các phân vùng nằm ngoài khoảng đó:

~~~sql
WHERE occurred_at >= TIMESTAMP '2026-02-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-03-01 00:00:00'
~~~

Dùng khoảng nửa mở [start, end) giúp tránh trùng lặp ở ranh giới giữa hai phân vùng và tránh phải đoán độ chính xác phần giây cuối ngày.

### 2.2. LIST partitioning

LIST chia dữ liệu theo một tập giá trị rời rạc, ví dụ mã vùng, loại sự kiện hoặc nhóm trạng thái.

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    customer_name VARCHAR(200)
) PARTITION BY LIST (region_code);

CREATE TABLE customers_north
PARTITION OF customers
FOR VALUES IN ('NORTH');

CREATE TABLE customers_south
PARTITION OF customers
FOR VALUES IN ('SOUTH');

CREATE TABLE customers_other
PARTITION OF customers
DEFAULT;
~~~

Điều kiện equality hoặc IN trên **region_code** có thể giúp DBMS xác định tập phân vùng liên quan:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE region_code IN ('NORTH', 'SOUTH');
~~~

Nếu truy vấn không có điều kiện vùng, DBMS có thể phải truy cập tất cả phân vùng. Phân vùng DEFAULT cũng phải được tính đến khi đánh giá phạm vi giá trị và dữ liệu mới.

### 2.3. HASH partitioning

HASH phân phối hàng vào các phân vùng dựa trên hàm băm của partition key. Mục tiêu thường là phân tán dữ liệu hoặc tải ghi thay vì tạo các khoảng nghiệp vụ dễ đọc.

Ví dụ khái niệm: **tenant_id** được băm thành một trong 16 phân vùng. Khi truy vấn có điều kiện equality trên **tenant_id**, engine có thể tính hash để xác định phân vùng tương ứng nếu DBMS hỗ trợ pruning cho biểu thức đó.

~~~sql
SELECT *
FROM tenant_events
WHERE tenant_id = 420;
~~~

Một điều kiện phạm vi như **tenant_id BETWEEN 100 AND 200** thường không xác định được một tập nhỏ phân vùng hash; nhiều hoặc tất cả phân vùng có thể cần được xét. Khả năng pruning cho HASH phụ thuộc hệ quản trị và dạng predicate được hỗ trợ.

### 2.4. Khóa ghép và thứ tự cột

Một bảng có thể phân vùng theo nhiều cột hoặc dùng partition key là biểu thức. Khi đó, điều kiện truy vấn cần cung cấp đủ thông tin để DBMS xác định ranh giới.

Ví dụ, nếu dữ liệu được phân vùng theo **(tenant_id, occurred_at)**, điều kiện theo tenant và khoảng thời gian có thể thu hẹp tốt hơn chỉ lọc theo thời gian. Nhưng cách xác định miền giá trị ghép phụ thuộc semantics partitioning của engine.

Không nên giả định chỉ cần lọc một cột bất kỳ trong khóa ghép là sẽ pruning tối ưu. Hãy xem tài liệu hệ quản trị và execution plan cho đúng cấu trúc đã khai báo.

### 2.5. Phân vùng theo biểu thức

Một số DBMS cho phép phân vùng theo biểu thức, ví dụ tháng của timestamp hoặc một hàm chuẩn hóa. Khi đó, predicate truy vấn phải tương thích với biểu thức phân vùng hoặc optimizer phải chứng minh được quan hệ tương đương.

Nếu bảng được phân vùng theo **DATE(occurred_at)**, một truy vấn dùng chính biểu thức đó có thể được nhận diện trong một số engine. Nhưng truy vấn dùng biểu thức khác, cast khác hoặc múi giờ khác có thể không cho cùng khả năng pruning.

Thiết kế thường dễ vận hành hơn khi dùng partition key có kiểu dữ liệu rõ ràng và truy vấn trực tiếp trên cột đó. Nếu cần biểu thức phân vùng, hãy chuẩn hóa cách viết predicate và kiểm tra kế hoạch cho mọi dạng truy vấn quan trọng.

## 3. Viết điều kiện truy vấn phù hợp với partition key

### 3.1. So sánh trực tiếp trên cột phân vùng

Cách an toàn và dễ nhận diện nhất là đặt điều kiện trực tiếp trên partition key bằng toán tử mà DBMS hỗ trợ.

Với RANGE theo **occurred_at**:

~~~sql
SELECT event_id, event_type
FROM events
WHERE occurred_at >= TIMESTAMP '2026-02-10 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-11 00:00:00';
~~~

Predicate mô tả chính xác một khoảng thời gian. Optimizer có thể so sánh khoảng này với ranh giới các phân vùng.

Các dạng thường có ích gồm:

- Equality: partition_key = value.
- Range: partition_key >= lower AND partition_key < upper.
- IN: partition_key IN (...) khi engine hỗ trợ pruning cho danh sách giá trị.
- Các điều kiện kết hợp AND có thể thu hẹp miền giá trị.
- Một số biểu thức OR nếu optimizer có thể phân tích từng nhánh.

Khả năng cụ thể phụ thuộc DBMS, kiểu partitioning, kiểu dữ liệu và phiên bản.

### 3.2. Dùng khoảng nửa mở cho dữ liệu thời gian

Với phân vùng theo tháng hoặc ngày, nên dùng:

~~~sql
WHERE occurred_at >= TIMESTAMP '2026-02-01 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-03-01 00:00:00'
~~~

Tránh viết:

~~~sql
WHERE occurred_at BETWEEN
      TIMESTAMP '2026-02-01 00:00:00'
  AND TIMESTAMP '2026-02-28 23:59:59';
~~~

BETWEEN bao gồm cả hai đầu mút. Nếu cột lưu phần giây nhỏ hơn một giây hoặc độ chính xác cao hơn, điều kiện kết thúc 23:59:59 có thể bỏ sót các hàng ở phần còn lại của giây cuối. Khoảng nửa mở tránh vấn đề này và ghép các khoảng liên tiếp không chồng lấn.

### 3.3. Tránh bọc partition key bằng hàm không cần thiết

Một dạng truy vấn thường gặp:

~~~sql
SELECT *
FROM events
WHERE DATE(occurred_at) = DATE '2026-02-10';
~~~

Ở đây, hàm DATE được áp dụng lên cột phân vùng. DBMS có thể không chuyển đổi biểu thức thành khoảng trên **occurred_at**, hoặc khả năng pruning có thể phụ thuộc engine và biểu thức phân vùng.

Viết lại thành:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= TIMESTAMP '2026-02-10 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-11 00:00:00';
~~~

Cách viết này nêu trực tiếp khoảng trên partition key và thường dễ pruning hơn. Nếu nghiệp vụ dùng ngày theo múi giờ địa phương, phải chuyển ngày nghiệp vụ thành hai mốc thời gian đúng múi giờ trước khi bind tham số.

### 3.4. Tránh phép tính trên cột phân vùng

Các dạng như:

~~~sql
WHERE EXTRACT(YEAR FROM occurred_at) = 2026
~~~

hoặc:

~~~sql
WHERE occurred_at + INTERVAL '1 day' >= :cutoff
~~~

có thể làm predicate khó khớp với ranh giới phân vùng. Hãy chuyển phép tính sang phía giá trị tham số để cột vẫn đứng riêng:

~~~sql
WHERE occurred_at >= :start_time
  AND occurred_at < :end_time
~~~

Nếu partition key được định nghĩa bằng một biểu thức cụ thể, truy vấn dùng cùng biểu thức có thể được pruning tùy engine. Nhưng không nên dựa vào optimizer để suy ra mọi phép biến đổi đại số; hãy kiểm tra plan.

### 3.5. Kiểu dữ liệu và implicit cast

Kiểu dữ liệu của tham số nên tương thích với partition key. Nếu cột là TIMESTAMP nhưng tham số được bind dưới kiểu khác, DBMS có thể chèn implicit cast. Tùy hướng chuyển đổi và hệ quản trị, điều này có thể làm thay đổi biểu thức, ngăn pruning hoặc khiến so sánh có semantics khác.

Ví dụ, hãy bind timestamp với kiểu tương ứng thay vì gửi chuỗi tùy ý rồi để DBMS tự chuyển đổi. Nếu cần cast, ưu tiên chuyển giá trị tham số sang kiểu cột, thay vì áp dụng hàm lên cột phân vùng.

Cần chú ý:

- DATE khác TIMESTAMP.
- TIMESTAMP không múi giờ khác TIMESTAMP WITH TIME ZONE.
- Số nguyên và chuỗi số có thể có quy tắc so sánh khác.
- Collation và kiểu chuỗi có thể ảnh hưởng LIST partition.
- Múi giờ session có thể ảnh hưởng việc chuyển đổi giá trị thời gian.

### 3.6. Múi giờ và ranh giới ngày

Nếu dữ liệu lưu thời điểm UTC nhưng báo cáo theo ngày địa phương, khoảng truy vấn phải được chuyển đổi đúng. Một ngày địa phương không phải lúc nào cũng tương đương đúng 24 giờ trong những vùng có quy tắc daylight saving time.

Cách tiếp cận:

1. Xác định múi giờ nghiệp vụ.
2. Tính thời điểm bắt đầu ngày trong múi giờ đó.
3. Tính thời điểm bắt đầu ngày kế tiếp trong cùng múi giờ.
4. Chuyển cả hai mốc về kiểu và múi giờ lưu trữ.
5. Dùng >= start và < end trên partition key.

Không dùng DATE(timestamp_column) một cách tùy tiện chỉ để so với ngày hiển thị. Điều kiện phải phản ánh chính xác semantics thời gian và cho phép DBMS xác định khoảng phân vùng.

### 3.7. Điều kiện OR

Điều kiện OR có thể làm pruning khó hơn nếu mỗi nhánh đề cập đến cột khác nhau hoặc biểu thức phức tạp:

~~~sql
WHERE occurred_at >= :start_time
   OR tenant_id = :tenant_id
~~~

Một trong hai nhánh có thể khớp dữ liệu ở nhiều phân vùng, nên DBMS có thể cần truy cập phạm vi rộng. Nếu mỗi nhánh đều giới hạn partition key, optimizer có thể xác định hợp các phân vùng cần thiết, nhưng không nên giả định mọi dạng OR đều được xử lý giống nhau.

Khi có thể, biểu diễn các phạm vi phân vùng rõ ràng. Với hai truy vấn độc lập, đôi khi UNION ALL có thể làm từng nhánh dễ tối ưu hơn, nhưng phải tránh trùng kết quả và kiểm tra chi phí hợp nhất. Không tách OR thành UNION ALL nếu hai nhánh có thể cùng trả một hàng mà không xử lý trùng lặp đúng cách.

### 3.8. NOT, inequality và điều kiện rộng

Predicate phủ định như **partition_key <> value** hoặc **NOT IN (...)** thường loại một phần nhỏ miền giá trị và có thể vẫn cần hầu hết phân vùng. Với RANGE, điều kiện < hoặc >= có thể pruning một phía của miền; điều kiện phủ định hoặc biểu thức phức tạp thường kém chọn lọc hơn.

Cần đánh giá số phân vùng còn lại sau pruning. Predicate hợp lệ về mặt cú pháp không có nghĩa là nó giúp giảm đáng kể dữ liệu.

## 4. Predicate trên nhiều điều kiện và khóa phân vùng ghép

### 4.1. Kết hợp partition key với filter nghiệp vụ

Bảng sự kiện có thể phân vùng theo **occurred_at** nhưng truy vấn thường lọc thêm **tenant_id** và **event_type**:

~~~sql
SELECT event_id, payload
FROM events
WHERE occurred_at >= :start_time
  AND occurred_at < :end_time
  AND tenant_id = :tenant_id
  AND event_type = :event_type;
~~~

Điều kiện thời gian giúp loại các phân vùng ngoài phạm vi. Các điều kiện tenant và event_type tiếp tục thu hẹp hàng trong những phân vùng còn lại.

Có thể cần index cục bộ trên **(tenant_id, event_type, occurred_at)** hoặc cấu trúc phù hợp với truy vấn, tùy DBMS và cách tổ chức index. Pruning không thay thế index cho các cột lọc khác.

### 4.2. Không có predicate trên partition key

Ví dụ:

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE tenant_id = 42;
~~~

Nếu chỉ phân vùng theo **occurred_at**, DBMS không biết tenant 42 nằm ở tháng nào. Có thể phải truy cập mọi phân vùng rồi tìm tenant_id bên trong từng phân vùng.

Nếu workload thường xuyên tìm theo tenant mà không giới hạn thời gian, cần xem lại thiết kế:

- Có nên dùng subpartitioning theo tenant hoặc hash tenant trong từng range không?
- Có nên thêm index cục bộ trên tenant_id?
- Có nên duy trì bảng tổng hợp hoặc cấu trúc tra cứu riêng?
- Có cần giới hạn truy vấn theo khoảng thời gian trong API?
- Số phân vùng có quá lớn so với lợi ích pruning không?

Không nên thay partition key chỉ vì một truy vấn đơn lẻ. Hãy thống kê tỷ lệ workload có và không có predicate phân vùng.

### 4.3. Partition key ghép

Nếu partitioning theo nhiều cột, query cần cung cấp predicate phù hợp với quy tắc phân vùng. Ví dụ, dữ liệu phân vùng theo tenant_id và occurred_at có thể cho phép thu hẹp theo tenant trước rồi theo khoảng thời gian.

Tuy nhiên, thứ tự cột và semantics range/list/hash khác nhau giữa các DBMS. Với RANGE nhiều cột, ranh giới có thể được xác định theo thứ tự từ điển hoặc quy tắc riêng. Không suy ra hành vi chỉ từ thứ tự cột trong DDL; kiểm tra tài liệu và EXPLAIN.

### 4.4. Composite partition key không thay thế composite index

Partition key quyết định phân phối hàng vào phân vùng. Index key quyết định cách tìm hàng bên trong index. Hai cấu trúc có thể dùng cùng cột nhưng phục vụ mục tiêu khác nhau.

Ví dụ, partition theo **occurred_at** và local index trên **(tenant_id, occurred_at)**:

- Predicate thời gian loại phân vùng.
- Predicate tenant giúp tìm nhanh trong từng phân vùng còn lại.
- Nếu truy vấn chỉ có tenant_id, pruning có thể không xảy ra nhưng local index vẫn có thể được dùng ở nhiều phân vùng.

Khi đánh giá, cần đếm số phân vùng còn truy cập và số trang đọc trong mỗi phân vùng.

## 5. Pruning tại thời điểm lập kế hoạch và khi thực thi

### 5.1. Static hoặc plan-time pruning

Plan-time pruning xảy ra khi DBMS biết giá trị predicate đủ sớm để xác định phân vùng cần thiết trong lúc lập kế hoạch. Ví dụ, câu SQL có literal ngày cố định hoặc tham số đã được biết khi tạo kế hoạch cụ thể.

Khi các phân vùng bị loại ngay trong kế hoạch, execution plan có thể chỉ chứa những partition scan được giữ lại. Điều này giảm cả công việc thực thi và đôi khi giảm kích thước cây kế hoạch.

### 5.2. Runtime hoặc execution-time pruning

Runtime pruning xảy ra khi giá trị dùng để xác định phân vùng chỉ có khi truy vấn đang chạy, chẳng hạn bind parameter, giá trị từ outer side của nested loop hoặc kết quả của một node khác.

Ví dụ:

~~~sql
SELECT e.event_id, e.occurred_at
FROM selected_tenants AS t
JOIN events AS e
    ON e.tenant_id = t.tenant_id
WHERE t.region_id = :region_id
  AND e.occurred_at >= :start_time
  AND e.occurred_at < :end_time;
~~~

Nếu partitioning cho phép pruning theo điều kiện thời gian, engine có thể xác định phân vùng ở thời điểm chạy. Với một số dạng join, giá trị từ outer input có thể giúp loại phân vùng động. Khả năng này phụ thuộc DBMS và hình dạng kế hoạch.

Runtime pruning không có nghĩa mọi phân vùng đã được mở rồi mới loại; engine có thể tránh thực thi các partition subplan không cần thiết. Hãy xem actual plan và số phân vùng được thực hiện.

### 5.3. Prepared statement và tham số bind

Prepared statement có thể dùng kế hoạch tổng quát hoặc kế hoạch được tối ưu theo giá trị tham số tùy DBMS. Nếu giá trị partition key chỉ được biết lúc execute, runtime pruning có thể cần thiết.

Một kế hoạch tổng quát không nhất thiết phải quét mọi phân vùng. Một số engine hỗ trợ runtime pruning cho bind parameter. Nhưng nếu hệ quản trị hoặc dạng truy vấn không hỗ trợ, plan có thể giữ nhiều nhánh và chỉ filter ở phía trong.

Cần thử với:

- Giá trị tham số nằm trong một phân vùng.
- Giá trị nằm sát ranh giới.
- Khoảng thời gian trải qua nhiều phân vùng.
- Giá trị không thuộc phân vùng nào hoặc rơi vào DEFAULT.
- Nhiều giá trị có độ chọn lọc rất khác nhau.

Không kết luận chỉ từ một lần chạy với literal. Hãy kiểm tra prepared statement thực tế của ứng dụng.

### 5.4. Pruning qua JOIN

Một truy vấn có thể lấy partition key từ bảng khác. Ví dụ bảng tenants chứa thời gian hoặc phạm vi được dùng để truy vấn bảng events. Một số DBMS có thể dùng nested loop parameterized scan, dynamic pruning hoặc partition-wise join.

Nhưng nếu join predicate không chứa partition key, hoặc optimizer chọn kế hoạch không truyền giá trị phù hợp đến partitioned table, tất cả phân vùng có thể vẫn được xét.

Hãy kiểm tra:

- Join key có liên hệ với partition key không?
- Outer input có bao nhiêu dòng và bao nhiêu giá trị phân biệt?
- Partition pruning xảy ra một lần hay lặp theo từng dòng outer?
- Có partition-wise join không?
- Số lần mỗi partition được truy cập là bao nhiêu?
- Chi phí lặp có lớn hơn lợi ích pruning không?

### 5.5. Pruning và constraint exclusion

Một số hệ quản trị có cơ chế dùng constraint hoặc metadata để loại bỏ bảng con/phân vùng. Trong PostgreSQL, declarative partition pruning là cơ chế chính cho partitioned table; constraint exclusion là cơ chế liên quan, thường dùng với inheritance partitioning cũ và dựa trên CHECK constraint trong lúc lập kế hoạch.

Không nên đánh đồng hai cơ chế hoặc mặc định mọi cấu hình constraint exclusion có cùng khả năng runtime pruning. Hãy xác định kiểu partitioning và phiên bản đang chạy.

## 6. Đọc partition pruning trong execution plan

### 6.1. PostgreSQL

Dùng EXPLAIN ANALYZE với BUFFERS:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type
FROM events
WHERE occurred_at >= TIMESTAMP '2026-02-10 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-11 00:00:00';
~~~

Plan có thể hiển thị **Append** hoặc **Merge Append** với các scan của partition con. Tùy thời điểm pruning, phân vùng bị loại có thể không xuất hiện trong danh sách node được thực thi hoặc được thể hiện qua thông tin như **Subplans Removed**. Với runtime pruning, một số subplan có thể có **never executed** hoặc số loops bằng 0 trong output phù hợp.

Hãy kiểm tra:

- Có bao nhiêu partition scan được thực thi?
- Có thông tin Subplans Removed không?
- Partition nào có actual rows và loops?
- Shared hit/read và temp I/O phát sinh ở partition nào?
- Có scan toàn bộ partition còn lại hay dùng index?
- Estimated rows và actual rows có sai lệch lớn không?

Không phải mọi phiên bản hay mọi loại plan đều hiển thị cùng một dòng chẩn đoán. Số phân vùng thực sự được thực thi và số block đọc mới là bằng chứng cần đối chiếu.

### 6.2. SQL Server

SQL Server gọi cơ chế tương ứng là partition elimination. Khi predicate phù hợp với partitioning column, optimizer có thể chỉ truy cập những partition liên quan.

Trong execution plan, kiểm tra thuộc tính và thông tin runtime của operator trên partitioned table/index. Actual execution plan có thể cho thấy phạm vi partition được truy cập hoặc số partition thực tế tùy operator và phiên bản. Kết hợp với **SET STATISTICS IO, TIME ON** để xem logical reads và thời gian.

Nếu predicate bọc partition column bằng hàm hoặc gây implicit conversion trên cột, partition elimination có thể không xảy ra như mong muốn. Hãy xem plan thực tế, warning về conversion và cách tham số được bind.

### 6.3. MySQL

MySQL EXPLAIN có thể hiển thị cột **partitions** để liệt kê các phân vùng được xem xét cho truy vấn. Nếu danh sách chứa tất cả partition, predicate có thể chưa pruning hiệu quả hoặc truy vấn thực sự cần toàn bộ dữ liệu.

Dùng EXPLAIN FORMAT=JSON hoặc EXPLAIN ANALYZE ở phiên bản hỗ trợ để xem thêm chi tiết về iterator, actual rows và thời gian. Cú pháp partitioning expression và các điều kiện pruning được hỗ trợ có giới hạn theo loại partitioning và phiên bản MySQL.

Đừng chỉ xem **type** hoặc **key** mà bỏ qua cột partitions. Một truy vấn có thể dùng index bên trong mọi partition nhưng vẫn phải mở quá nhiều phân vùng.

### 6.4. Oracle

Oracle execution plan có thể hiển thị **PARTITION RANGE**, **PARTITION LIST** hoặc **PARTITION HASH**, cùng các cột **Pstart** và **Pstop** trong plan table hoặc công cụ hiển thị plan. Giá trị cụ thể hoặc ký hiệu **KEY** có thể cho biết pruning tĩnh hoặc động tùy kế hoạch.

Cần kiểm tra actual execution statistics, số partition được truy cập, buffer gets, physical reads và thời gian SQL. Khi dùng bind variables, hãy xác minh dynamic pruning có diễn ra với giá trị thực tế hay không.

### 6.5. Đừng kết luận từ tên node đơn lẻ

Một node **Append**, **Partition Iterator** hoặc **Partition Range** chỉ cho biết cấu trúc kế hoạch. Cần xem số phân vùng được thực thi, actual rows, loops, buffers/reads và thời gian. Một truy vấn có thể pruning tốt nhưng vẫn chậm do phân vùng còn lại quá lớn hoặc access path bên trong không phù hợp.

## 7. Ví dụ: truy vấn theo thời gian

### 7.1. Truy vấn không phù hợp

Giả sử **events** được phân vùng RANGE theo **occurred_at** theo tháng. Một báo cáo cần dữ liệu ngày 10/02/2026:

~~~sql
SELECT COUNT(*)
FROM events
WHERE DATE(occurred_at) = DATE '2026-02-10';
~~~

Predicate áp dụng hàm DATE lên cột. Khả năng pruning tùy engine và biểu thức partition key; trong nhiều thiết kế, cách viết này khó khai thác ranh giới trực tiếp.

### 7.2. Viết lại theo khoảng nửa mở

~~~sql
SELECT COUNT(*)
FROM events
WHERE occurred_at >= TIMESTAMP '2026-02-10 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-02-11 00:00:00';
~~~

DBMS có thể xác định chỉ partition tháng 02 cần đọc. Nếu phân vùng tháng có local index phù hợp, access path bên trong còn có thể giảm số trang cần truy cập.

### 7.3. Kiểm tra ranh giới phân vùng

Giả sử phân vùng tháng 02 có miền [2026-02-01, 2026-03-01). Các truy vấn sau có phạm vi khác nhau:

| Predicate | Phân vùng có thể cần đọc |
|---|---|
| occurred_at >= '2026-02-10' AND occurred_at < '2026-02-11' | Tháng 02 |
| occurred_at >= '2026-01-31' AND occurred_at < '2026-02-02' | Tháng 01 và tháng 02 |
| occurred_at >= '2026-02-01' AND occurred_at < '2026-04-01' | Tháng 02 và tháng 03 |
| Không có điều kiện occurred_at | Có thể tất cả phân vùng |

Điều kiện phải được hiểu theo kiểu dữ liệu và múi giờ thực tế. Các literal trong bảng chỉ minh họa ranh giới.

### 7.4. Kiểm tra cả truy vấn theo tenant

Nếu tenant_id là filter thường xuyên nhưng không phải partition key:

~~~sql
SELECT event_id, payload
FROM events
WHERE occurred_at >= :start_time
  AND occurred_at < :end_time
  AND tenant_id = :tenant_id;
~~~

Pruning giới hạn tháng hoặc ngày. Index cục bộ trên tenant_id có thể giảm công việc bên trong từng phân vùng còn lại. Nếu mỗi phân vùng chỉ có một lượng dữ liệu nhỏ, scan tuần tự có thể vẫn rẻ hơn index lookup; optimizer quyết định dựa trên thống kê và chi phí.

## 8. Ví dụ: partition pruning qua JOIN

### 8.1. Truy vấn có partition key trong điều kiện nối

Giả sử bảng **sales** được phân vùng theo **sale_date** và bảng **report_periods** chứa các khoảng báo cáo. Truy vấn:

~~~sql
SELECT
    p.period_id,
    SUM(s.amount) AS total_amount
FROM report_periods AS p
JOIN sales AS s
    ON s.sale_date >= p.start_date
   AND s.sale_date < p.end_date
WHERE p.period_id = :period_id
GROUP BY p.period_id;
~~~

Nếu DBMS có thể truyền các giá trị start_date và end_date vào truy vấn partitioned table, có thể có runtime pruning hoặc kế hoạch parameterized. Nhưng điều này phụ thuộc optimizer và dạng join.

Nếu plan thực tế truy cập mọi partition của sales, có thể cần:

- Lọc report_periods trước để chỉ còn một khoảng.
- Viết lại thành truy vấn có bind start/end rõ ràng nếu ứng dụng đã biết khoảng.
- Kiểm tra kiểu dữ liệu và biểu thức join.
- Xem xét partition-wise hoặc dynamic pruning nếu engine hỗ trợ.
- Đo số lần inner partition scan và loops.

### 8.2. Số vòng lặp có thể làm pruning lặp lại

Nếu outer side có 10.000 dòng và mỗi dòng cung cấp một khoảng thời gian khác nhau, DBMS có thể phải xác định tập phân vùng cần đọc nhiều lần. Nếu nhiều khoảng trùng hoặc giao nhau, chi phí lặp có thể tăng.

Hãy xem số loops của nhánh partitioned scan và số phân vùng được thực thi mỗi lần. Có thể cần hợp nhất các khoảng, loại bỏ trùng lặp hoặc tổng hợp outer input trước khi join nếu ngữ nghĩa cho phép.

### 8.3. Partition-wise join

Một số DBMS hỗ trợ partition-wise join khi hai bảng được phân vùng tương thích theo khóa nối. Khi đó, DBMS có thể nối từng cặp phân vùng tương ứng, giảm kích thước dữ liệu trung gian và tận dụng song song.

Điều kiện để sử dụng phụ thuộc cách phân vùng, khóa nối, tính tương thích và cấu hình. Partition-wise join không đồng nghĩa với pruning; một cơ chế chia phép nối theo phân vùng, cơ chế kia loại bỏ phân vùng không cần thiết. Có thể dùng cả hai trong một kế hoạch.

## 9. Index cục bộ, index toàn cục và pruning

### 9.1. Local index

Local index được chia hoặc căn chỉnh theo từng partition. Khi một partition bị loại bỏ, DBMS có thể không cần truy cập local index của partition đó.

Ưu điểm vận hành thường gồm:

- Bảo trì hoặc rebuild một phân vùng riêng dễ kiểm soát hơn.
- Drop/truncate partition có thể ít ảnh hưởng đến index của các partition khác.
- Index nhỏ hơn theo từng phân vùng.
- Có thể phù hợp với vòng đời dữ liệu và thao tác nạp/xóa theo partition.

Nhưng nếu query không pruning, DBMS có thể phải tra local index trên nhiều partition và hợp nhất kết quả.

### 9.2. Global index

Một số DBMS hỗ trợ global index bao phủ nhiều partition. Global index có thể phục vụ tra cứu theo khóa không phải partition key mà không cần tìm trong mọi local index, nhưng chi phí bảo trì và tính khả dụng khi partition được drop/move có thể phức tạp hơn.

Không phải hệ quản trị nào cũng hỗ trợ cùng loại global index hoặc cùng semantics. PostgreSQL partitioned index có đặc điểm khác với global index của một số hệ thống thương mại. Cần đọc tài liệu đúng engine và phiên bản.

### 9.3. Pruning không thay thế index

Sau khi pruning còn một partition, nếu truy vấn tìm một customer_id trong partition có hàng trăm triệu dòng, index bên trong vẫn có thể rất quan trọng. Ngược lại, nếu partition còn lại chỉ có vài nghìn hàng, scan toàn partition có thể rẻ hơn.

Thiết kế index phải dựa trên access path bên trong partition và workload đọc/ghi. Đừng tạo một index rộng chỉ vì bảng đã được phân vùng.

## 10. Những nguyên nhân làm pruning không hiệu quả

### 10.1. Không có predicate trên partition key

Đây là nguyên nhân phổ biến nhất. Nếu partitioning theo ngày nhưng query chỉ lọc status, DBMS không biết partition nào chứa status cần tìm. Tất cả phân vùng có thể phải được xét.

Giải pháp có thể là thêm khoảng thời gian nếu nghiệp vụ cho phép, thiết kế lại partition key/subpartitioning, hoặc index phù hợp trên từng partition. Không tự thêm điều kiện thời gian giả tạo vì sẽ làm thay đổi kết quả.

### 10.2. Hàm hoặc phép tính trên cột

DATE(partition_key), YEAR(partition_key), CAST(partition_key AS ...) hoặc phép cộng/trừ trực tiếp trên cột có thể cản trở pruning. Hãy chuyển phép tính sang giá trị tham số và so sánh trực tiếp trên cột khi có thể.

### 10.3. Kiểu tham số không khớp

Implicit conversion, collation khác hoặc timezone conversion có thể làm predicate không khớp với metadata partition. Dùng kiểu bind rõ ràng và kiểm tra plan với driver thực tế của ứng dụng.

### 10.4. Predicate quá rộng

Một truy vấn có khoảng thời gian kéo dài 5 năm trên bảng phân vùng theo tháng có thể cần 60 phân vùng. Pruning vẫn hoạt động đúng nhưng không thể loại nhiều phân vùng vì yêu cầu nghiệp vụ thực sự rộng.

Cần xem xét giới hạn khoảng truy vấn, tổng hợp dữ liệu cũ, archive hoặc rollup nếu workload cho phép. Đừng nhầm “pruning đã hoạt động” với “truy vấn chắc chắn rẻ”.

### 10.5. Biểu thức OR phức tạp

OR giữa partition key và cột không phải partition key có thể khiến DBMS cần giữ nhiều phân vùng. Chia truy vấn thành nhánh riêng chỉ có ích nếu từng nhánh được pruning và việc loại trùng được xử lý chính xác.

### 10.6. Tham số và kế hoạch tổng quát

Một generic plan có thể không biết giá trị cụ thể tại planning time. Nếu engine không thực hiện runtime pruning cho hình dạng truy vấn đó, kế hoạch có thể truy cập nhiều partition hơn cần thiết. Kiểm tra execution plan khi dùng prepared statement, không chỉ khi chạy literal.

### 10.7. Thống kê không phù hợp

Thống kê thiếu hoặc cũ có thể khiến optimizer chọn access path kém bên trong các partition còn lại, hoặc ước lượng sai số dòng và join order. Cần cập nhật thống kê theo cơ chế DBMS, kiểm tra thống kê cấp bảng cha và từng partition khi phù hợp.

## 11. Quy trình chẩn đoán partition pruning

Khi một truy vấn trên bảng phân vùng chậm, thực hiện theo thứ tự:

1. **Xác định partition key:** tên cột/biểu thức, kiểu dữ liệu, phương thức RANGE/LIST/HASH và ranh giới.
2. **Xác định miền truy vấn:** giá trị hoặc khoảng nào thực sự cần lấy, có bao phủ bao nhiêu phân vùng?
3. **Đọc predicate:** có so sánh trực tiếp trên partition key không, có hàm/cast/OR hoặc implicit conversion không?
4. **Kiểm tra prepared statement:** kiểu bind và giá trị runtime có tương thích không?
5. **Đọc execution plan:** số phân vùng được liệt kê, bị loại và thực thi; static hay runtime pruning?
6. **Đo access path bên trong:** scan hay index, actual rows, loops, buffers, logical/physical reads.
7. **Kiểm tra thống kê:** estimated rows so với actual rows trên các partition liên quan.
8. **Kiểm tra JOIN:** có pruning qua tham số từ outer input không, có lặp nhiều lần không?
9. **Thử một thay đổi:** viết lại predicate, bind đúng kiểu, thêm index phù hợp hoặc giới hạn phạm vi theo nghiệp vụ.
10. **Đo lại:** cùng dữ liệu, tham số, concurrency, cache policy và cửa sổ đo.
11. **Đánh giá vận hành:** số partition, thời gian planning, maintenance, dung lượng và chi phí ghi.
12. **Xác nhận tính đúng:** so sánh kết quả tại ranh giới, NULL, múi giờ và partition DEFAULT.

### 11.1. Bảng kiểm tra nhanh

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Tất cả partition xuất hiện | Thiếu predicate partition key hoặc predicate không nhận diện được | Xem WHERE, kiểu dữ liệu và partition bounds |
| Chỉ một partition được scan nhưng truy vấn vẫn chậm | Partition lớn hoặc access path bên trong kém | Xem index, actual rows, buffers và I/O |
| Literal pruning tốt, prepared query chậm | Runtime pruning hoặc generic plan khác | Xem bind type, plan cache và actual plan |
| Hàm trên partition key | Predicate không sargable với partition bounds | Chuyển thành khoảng trực tiếp trên cột |
| JOIN truy cập nhiều partition lặp lại | Runtime pruning theo outer input và loops cao | Xem loops, số giá trị outer và join order |
| Ước lượng sai nhiều | Thống kê không phản ánh dữ liệu | Analyze/statistics và histogram |
| Truy vấn rộng cần nhiều partition | Phạm vi yêu cầu thực sự rộng | Giới hạn nghiệp vụ, rollup hoặc archive nếu phù hợp |

## 12. Đo lường trước và sau

### 12.1. Xác định workload đại diện

Tập truy vấn thử cần gồm:

- Truy vấn một ngày hoặc một tháng.
- Truy vấn đi qua ranh giới hai phân vùng.
- Truy vấn nhiều tháng.
- Truy vấn không có predicate partition key.
- Truy vấn theo equality, IN và OR.
- Truy vấn dùng prepared statement/bind parameter.
- Truy vấn join có thể kích hoạt runtime pruning.
- Truy vấn đọc phần lớn dữ liệu để làm báo cáo.

Một partition pruning benchmark chỉ dùng truy vấn hẹp có thể phóng đại lợi ích. Cần có cả truy vấn rộng để thấy chi phí thực tế.

### 12.2. Các chỉ số cần ghi

- Số partition được xét, loại bỏ và thực thi.
- Số dòng thực tế đọc từ mỗi partition.
- Estimated rows và actual rows.
- Loops của partition scan và node JOIN.
- Buffer hits, logical reads và physical reads.
- CPU time và elapsed time.
- Temporary I/O và sort/hash spill.
- Planning time và execution time.
- Throughput, p95/p99, timeout và concurrency.
- Kích thước index cục bộ/toàn cục và chi phí ghi.

### 12.3. So sánh công bằng

Trước và sau thay đổi, giữ các yếu tố tương đương:

- Cùng tập dữ liệu và phân bố.
- Cùng tham số và kiểu bind.
- Cùng số client và mức concurrency.
- Cùng cache warm/cold policy.
- Cùng phiên bản DBMS và cấu hình liên quan.
- Cùng cửa sổ đo và trạng thái thống kê.

Nếu thay đổi cả partition key, index và query cùng lúc, khó xác định yếu tố nào tạo ra lợi ích. Hãy tách các thay đổi khi có thể và lưu execution plan để đối chiếu.

### 12.4. Ví dụ kết quả minh họa

Giả sử bảng **events** có 36 phân vùng theo tháng:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Partition được truy cập | 36 | 1 |
| Rows đọc | 18.000.000 | 520.000 |
| Shared/logical reads | 145.000 | 8.400 |
| p95 | 2.800 ms | 240 ms |
| CPU time | 1.900 ms | 170 ms |

Trước thay đổi, truy vấn dùng DATE(occurred_at) = ... và plan không loại được phân vùng. Sau thay đổi, predicate được viết thành khoảng nửa mở trực tiếp trên occurred_at. Số liệu chỉ mang tính minh họa; thực tế còn phụ thuộc kích thước phân vùng, index, cache và tải đồng thời.

Nếu sau khi pruning còn một phân vùng nhưng p95 vẫn cao, hãy tiếp tục phân tích access path và số trang đọc trong phân vùng đó. Không dừng điều tra chỉ vì số partition đã giảm.

## 13. Những sai lầm thường gặp

**Cho rằng có partitioning thì mọi query đều nhanh.**  
Nếu query không lọc partition key, DBMS có thể phải truy cập mọi partition.

**Cho rằng pruning thay thế index.**  
Pruning loại partition; index giúp tìm hàng bên trong partition còn lại.

**Bọc partition key bằng hàm cho tiện viết.**  
Hàm có thể cản trở việc so sánh trực tiếp với partition bounds. Dùng khoảng trên cột nếu phù hợp.

**Dùng BETWEEN cho khoảng thời gian liên tiếp mà không tính phần giây cuối.**  
Khoảng nửa mở tránh bỏ sót và trùng lặp ở ranh giới.

**Bind tham số sai kiểu.**  
Implicit cast hoặc timezone conversion có thể làm thay đổi predicate và khả năng pruning.

**Kiểm tra chỉ bằng literal.**  
Ứng dụng thường dùng prepared statement. Cần đo với đúng driver và kiểu bind thực tế.

**Nhầm pruning với partition-wise join.**  
Pruning loại phân vùng; partition-wise join thay đổi cách thực hiện phép nối theo các cặp phân vùng tương thích.

**Tạo quá nhiều phân vùng.**  
Số partition lớn có thể tăng metadata, planning time và chi phí vận hành dù từng truy vấn pruning tốt.

**Chỉ xem số phân vùng mà không xem số trang.**  
Một partition còn lại vẫn có thể rất lớn và cần scan nhiều dữ liệu.

**Dựa vào một execution plan ước lượng.**  
Cần xem actual plan, runtime pruning, loops, buffers và số dòng thực tế.

**Tự thêm điều kiện thời gian để ép pruning.**  
Điều kiện phải đúng nghiệp vụ. Predicate sai có thể làm mất dữ liệu cần trả về.

## 14. Mẫu báo cáo review truy vấn phân vùng

| Hạng mục | Nội dung cần ghi |
|---|---|
| Bảng | Tên bảng cha, số partition và kích thước |
| Partition key | Cột/biểu thức, kiểu dữ liệu, RANGE/LIST/HASH |
| Predicate | Điều kiện trực tiếp, kiểu bind và khoảng giá trị |
| Phạm vi | Số partition có thể khớp theo bounds |
| Pruning | Plan-time hay runtime; số partition bị loại và được thực thi |
| Access path | Scan/index bên trong từng partition |
| Cardinality | Estimated rows, actual rows và loops |
| I/O | Buffers/logical reads/physical reads |
| Join | Có runtime pruning hoặc partition-wise join không |
| Chi phí | Planning, execution, CPU, temp I/O, p95/p99 |
| Tác động ghi | Index maintenance, partition maintenance và dung lượng |
| Kết luận | Thay đổi nào có bằng chứng cải thiện và giới hạn nào còn lại |

Ví dụ kết luận có cơ sở:

“Bảng events được phân vùng theo tháng trên occurred_at. Truy vấn báo cáo một ngày đang dùng DATE(occurred_at), khiến plan truy cập nhiều partition. Viết lại thành khoảng [start, end) với bind parameter kiểu timestamp làm plan chỉ thực thi một partition. Logical reads và p95 giảm trong workload thử. Truy vấn chỉ lọc tenant_id vẫn phải xét nhiều partition; cần đánh giá index cục bộ hoặc điều chỉnh cách truy vấn theo yêu cầu nghiệp vụ.”

## 15. Kết luận

Partition pruning giúp DBMS loại bỏ những phân vùng không thể chứa hàng cần tìm dựa trên partition key và ranh giới đã khai báo. Để cơ chế này hoạt động hiệu quả, predicate cần mô tả rõ miền giá trị trên khóa phân vùng, dùng kiểu dữ liệu tương thích và tránh các phép biến đổi không cần thiết trên cột. Với dữ liệu thời gian, khoảng nửa mở thường là cách viết rõ ràng và an toàn tại ranh giới.

Pruning có thể diễn ra khi lập kế hoạch hoặc khi thực thi, bao gồm các trường hợp tham số bind và một số phép JOIN nếu DBMS hỗ trợ. PostgreSQL, SQL Server, MySQL và Oracle thể hiện partition elimination theo các cách khác nhau; cần đọc actual execution plan và số liệu của đúng engine. Sau khi loại phân vùng, vẫn phải đánh giá index và access path bên trong phần dữ liệu còn lại.

Một thay đổi chỉ được xác nhận khi số partition thực sự truy cập, số trang đọc, độ trễ và tải CPU/I/O cải thiện dưới workload đại diện, đồng thời kết quả truy vấn vẫn đầy đủ và chính xác ở các ranh giới dữ liệu.

## Câu hỏi tự kiểm tra

1. Partition pruning khác index seek ở phạm vi và mục tiêu nào?
2. Vì sao predicate trực tiếp trên partition key thường giúp pruning dễ hơn?
3. Khoảng nửa mở [start, end) giải quyết vấn đề gì khi truy vấn theo ngày?
4. Hàm DATE hoặc YEAR trên cột phân vùng có thể ảnh hưởng pruning ra sao?
5. RANGE, LIST và HASH partitioning khác nhau thế nào về dạng predicate có thể loại phân vùng?
6. Vì sao query chỉ lọc tenant_id có thể truy cập tất cả partition nếu bảng phân vùng theo thời gian?
7. Static pruning và runtime pruning khác nhau ở thời điểm xác định phân vùng nào?
8. Prepared statement cần được kiểm tra thế nào để xác nhận pruning với bind parameter?
9. Partition-wise join có đồng nghĩa với partition pruning không?
10. Vì sao một query chỉ còn một partition vẫn có thể chậm?
11. Cần xem những dấu hiệu nào trong PostgreSQL, SQL Server, MySQL hoặc Oracle để xác nhận partition elimination?
12. Hãy lập kế hoạch benchmark một truy vấn theo ngày trước và sau khi viết lại predicate, bao gồm cả truy vấn qua ranh giới tháng và truy vấn dùng prepared statement.

Khi review một truy vấn trên bảng phân vùng, hãy hỏi: partition key là gì, predicate mô tả miền giá trị nào, DBMS thực sự thực thi bao nhiêu partition và access path bên trong mỗi partition tốn bao nhiêu công việc. Những câu hỏi đó giúp xác định pruning có mang lại lợi ích thực tế hay không.

