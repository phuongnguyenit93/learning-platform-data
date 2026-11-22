# Chỉ mục theo partition và đánh đổi khi truy vấn nhiều vùng

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Khi một bảng InnoDB được partition, mỗi partition có các cấu trúc index cục bộ riêng. Optimizer có thể loại bỏ partition không liên quan trước khi truy cập index, nhưng truy vấn chạm nhiều partition vẫn phải xử lý nhiều vùng dữ liệu và nhiều index cục bộ.

MySQL không cung cấp global index cho bảng partitioned. Quy tắc này ảnh hưởng trực tiếp đến khóa duy nhất, thiết kế composite index và truy vấn theo khóa không chứa partition key. Partitioning có thể giúp giới hạn dữ liệu cần đọc hoặc quản lý vòng đời dữ liệu lớn, nhưng không tự làm mọi truy vấn nhanh hơn. Cần thiết kế partition key, index và điều kiện truy vấn cùng nhau, sau đó xác minh bằng EXPLAIN.

## 1. Partition và index phối hợp như thế nào?

Partitioning chia một bảng logic thành nhiều vùng dữ liệu vật lý theo một biểu thức phân vùng. Ứng dụng vẫn truy vấn một tên bảng; MySQL xác định partition nào cần tham gia dựa trên điều kiện truy vấn và kế hoạch thực thi.

Với InnoDB, mỗi partition duy trì các cấu trúc index cục bộ. Có thể hình dung:

~~~text
event_log (một bảng logic)
|
+-- p2026_01
|   +-- clustered index cục bộ
|   +-- secondary index cục bộ
|
+-- p2026_02
|   +-- clustered index cục bộ
|   +-- secondary index cục bộ
|
+-- p2026_03
    +-- clustered index cục bộ
    +-- secondary index cục bộ
~~~

Các partition có cùng định nghĩa index, nhưng mỗi partition lưu cây index riêng trên phần dữ liệu của nó. Người dùng khai báo index ở cấp bảng; không khai báo một bộ index khác nhau cho từng partition.

### 1.1. Local index

Local index là index chỉ bao phủ dữ liệu trong một partition. Khi truy vấn chỉ cần một partition, MySQL có thể tìm kiếm trong index cục bộ của partition đó. Khi truy vấn cần nhiều partition, engine có thể phải tra cứu index tương ứng ở nhiều partition rồi kết hợp kết quả.

### 1.2. MySQL không có global index cho bảng partitioned

Global index là một cấu trúc index duy nhất bao phủ hàng ở mọi partition. MySQL partitioning không cung cấp loại index này. Mỗi index trên bảng partitioned là index cục bộ theo partition.

Hệ quả:

- Truy vấn theo partition key có thể được pruning xuống một số partition rồi dùng local index.
- Truy vấn không có điều kiện trên partition key có thể phải kiểm tra nhiều hoặc tất cả partition.
- Unique key không thể chỉ dựa vào một cột không thuộc partition key để bảo đảm duy nhất toàn bảng.
- Một secondary index trên cột không phân vùng vẫn có thể được dùng trong từng partition, nhưng không biến thành một global lookup duy nhất.

### 1.3. Partitioning không thay thế indexing

Partition pruning loại bỏ những partition không cần truy cập. Index giúp tìm hàng hiệu quả bên trong partition còn lại. Hai cơ chế giải quyết hai phạm vi khác nhau:

| Cơ chế | Phạm vi tác động | Mục tiêu |
|---|---|---|
| Partition pruning | Chọn partition | Bỏ qua vùng dữ liệu không liên quan |
| Local index | Bên trong mỗi partition được chọn | Tìm hàng phù hợp mà không quét toàn bộ partition |
| Covering index | Cột cần đọc trong local index | Giảm việc truy cập thêm clustered record khi đủ điều kiện |

Một truy vấn có thể pruning đúng nhưng vẫn chậm nếu phải full scan partition được chọn. Ngược lại, một index tốt vẫn có thể phải được tra cứu trên rất nhiều partition nếu điều kiện không cho phép pruning.

## 2. Ví dụ bảng partition theo thời gian

Một bảng nhật ký sự kiện thường có dữ liệu tăng theo ngày hoặc tháng. Có thể partition theo RANGE COLUMNS trên cột ngày:

~~~sql
CREATE TABLE event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON,
    PRIMARY KEY (event_date, event_id),
    KEY ix_event_tenant_date (tenant_id, event_date),
    KEY ix_event_type_date (event_type, event_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

Trong ví dụ, mỗi partition chứa một khoảng ngày kết thúc tại mốc VALUES LESS THAN. Partition đầu tiên nhận các ngày nhỏ hơn 2026-02-01; partition p2026_02 nhận các ngày từ 2026-02-01 đến trước 2026-03-01.

### 2.1. Vì sao primary key chứa event_date?

Partition expression dùng event_date. MySQL yêu cầu mọi cột được dùng trong partitioning expression phải có mặt trong mọi unique key, bao gồm primary key. Vì vậy, PRIMARY KEY (event_date, event_id) hợp lệ; PRIMARY KEY (event_id) không đáp ứng quy tắc này.

Primary key trên cặp (event_date, event_id) bảo đảm cặp giá trị duy nhất. Nó không bảo đảm event_id duy nhất toàn bảng nếu cùng event_id xuất hiện ở hai ngày khác nhau.

### 2.2. Secondary index không unique

Hai index:

- (tenant_id, event_date)
- (event_type, event_date)

là secondary index không unique. Chúng có thể hỗ trợ các truy vấn theo tenant hoặc event type bên trong mỗi partition. Chúng không cần chứa partition key chỉ vì là secondary index không unique; quy tắc bắt buộc bao gồm partition columns áp dụng cho unique key.

### 2.3. Mọi partition dùng cùng định nghĩa index

Khi khai báo KEY ix_event_tenant_date, MySQL tạo cấu trúc index cục bộ tương ứng trên các partition. Không thể khai báo index tenant cho partition tháng này nhưng bỏ index đó ở partition tháng khác trong cùng một bảng partitioned.

Điều này giúp cấu trúc truy cập nhất quán nhưng cũng có nghĩa mỗi index được khai báo sẽ có chi phí lưu trữ và bảo trì trên các partition.

## 3. Partition pruning và index lookup

Partition pruning là bước optimizer loại các partition chắc chắn không chứa hàng thỏa điều kiện. Sau pruning, MySQL chọn access method và index trên những partition còn lại.

Ví dụ truy vấn khoảng thời gian:

~~~sql
SELECT event_id, tenant_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date <  '2026-02-18'
  AND tenant_id = 42;
~~~

Điều kiện event_date giới hạn truy vấn vào partition chứa khoảng ngày đó. Index (tenant_id, event_date) có thể được cân nhắc để tìm các hàng tenant 42 trong phạm vi ngày ở từng partition được chọn.

### 3.1. Pruning không đồng nghĩa chỉ đọc một partition

Nếu khoảng ngày đi qua nhiều tháng, nhiều partition sẽ được giữ lại. Ví dụ truy vấn từ cuối tháng 1 đến đầu tháng 3 có thể cần p2026_01, p2026_02 và p2026_03 tùy các ranh giới đã khai báo.

Partition pruning chỉ loại vùng không liên quan; nó không bảo đảm mọi truy vấn chỉ truy cập một partition.

### 3.2. Điều kiện trực tiếp trên partition key

Với RANGE COLUMNS(event_date), nên viết điều kiện trực tiếp trên event_date:

~~~sql
WHERE event_date >= '2026-02-01'
  AND event_date <  '2026-03-01'
~~~

Khoảng nửa mở [đầu, cuối) giúp tránh lỗi ở thời điểm cuối ngày khi dùng DATETIME/TIMESTAMP và thường dễ suy luận ranh giới partition.

### 3.3. Tránh bọc partition key trong hàm nếu không cần

Ví dụ:

~~~sql
WHERE YEAR(event_date) = 2026
~~~

Biểu thức hàm có thể khiến optimizer khó suy ra các partition cần thiết, tùy partition expression và phiên bản. Với partition theo ngày, nên viết:

~~~sql
WHERE event_date >= '2026-01-01'
  AND event_date <  '2027-01-01'
~~~

Nếu bảng được partition bằng chính biểu thức YEAR(event_date), cách viết phù hợp có thể khác. Hãy viết điều kiện tương thích với partitioning expression và xác nhận cột partitions trong EXPLAIN.

### 3.4. Điều kiện kết hợp

~~~sql
SELECT event_id
FROM event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND event_type = 'LOGIN';
~~~

Partition key giúp chọn vùng tháng 2; index (event_type, event_date) có thể giúp tìm event LOGIN trong vùng đó. Việc index nào được chọn còn phụ thuộc số hàng, selectivity và thống kê.

## 4. Quy tắc unique key trên bảng partitioned

Quy tắc này là một trong những đánh đổi lớn nhất khi chọn partition key trong MySQL:

**Mọi unique key của bảng phải chứa tất cả các cột được dùng trong partitioning expression.**

### 4.1. Unique key không chứa partition column bị từ chối

Giả sử partition theo event_date. Định nghĩa sau không hợp lệ:

~~~sql
CREATE TABLE invalid_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

Primary key không chứa event_date nên không đáp ứng quy tắc partitioning của MySQL.

### 4.2. Unique key kết hợp partition column

Định nghĩa hợp lệ:

~~~sql
CREATE TABLE valid_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    PRIMARY KEY (event_date, event_id),
    UNIQUE KEY uq_date_event (event_date, event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

Trong thực tế, không cần tạo thêm unique index giống hệt primary key; ví dụ trên chỉ minh họa rằng unique key phải chứa partition column. Thường chỉ giữ primary key cần thiết.

### 4.3. Partition key làm thay đổi ý nghĩa duy nhất

Nếu dùng:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

thì hai hàng có cùng event_id nhưng event_date khác nhau vẫn có thể tồn tại. Nếu nghiệp vụ đòi hỏi event_id duy nhất toàn bảng, cặp khóa này chưa đủ để thực thi quy tắc đó.

### 4.4. Giải pháp khi cần ID duy nhất toàn bảng

Một lựa chọn là dùng bảng registry không partitioned để giữ unique key toàn cục:

~~~sql
CREATE TABLE event_id_registry (
    event_id BIGINT NOT NULL,
    event_date DATE NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
~~~

Khi thêm sự kiện, ứng dụng ghi registry và bảng partitioned trong cùng transaction:

~~~sql
START TRANSACTION;

INSERT INTO event_id_registry (event_id, event_date)
VALUES (700001, '2026-02-12');

INSERT INTO event_log (
    event_date, event_id, tenant_id, event_type, payload
)
VALUES (
    '2026-02-12', 700001, 42, 'LOGIN', JSON_OBJECT('source', 'web')
);

COMMIT;
~~~

Nếu một INSERT thất bại, ứng dụng rollback cả transaction để registry và event_log không lệch nhau. Cách này thêm một lần ghi và một bảng cần quản lý; chỉ dùng khi yêu cầu unique toàn cục thực sự cần được database bảo đảm.

Các lựa chọn khác gồm dùng ID sinh toàn cục từ ứng dụng hoặc dịch vụ ID, nhưng phải xác định rõ xác suất va chạm và quy tắc retry. Không dựa vào một local unique index để tuyên bố event_id duy nhất xuyên partition.

## 5. Chọn thứ tự cột trong composite index

Partition pruning và thứ tự cột trong index là hai quyết định khác nhau. Partition key xác định vùng; thứ tự cột trong composite index xác định cách tìm kiếm bên trong vùng.

### 5.1. Truy vấn ưu tiên tenant rồi đến ngày

~~~sql
SELECT event_id, event_type
FROM event_log
WHERE tenant_id = 42
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Index (tenant_id, event_date) phù hợp với equality trên tenant_id rồi range trên event_date. Trong từng partition được pruning, optimizer có thể dùng leftmost prefix và range scan.

### 5.2. Truy vấn ưu tiên loại sự kiện rồi đến ngày

~~~sql
SELECT event_id, tenant_id
FROM event_log
WHERE event_type = 'LOGIN'
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Index (event_type, event_date) có thể phù hợp. Nếu event_type có độ chọn lọc thấp hoặc tenant/date có phân bố khác, optimizer có thể chọn index khác hoặc scan partition.

### 5.3. Index bắt đầu bằng partition key

Index (event_date, tenant_id) có thể phù hợp với truy vấn bắt đầu bằng range ngày và sau đó lọc tenant. Tuy nhiên, khi cột đầu tiên là range, khả năng sử dụng cột tiếp theo để thu hẹp range scan có thể khác với equality-prefix rồi range.

Không có một thứ tự cột đúng cho mọi truy vấn. Hãy lập danh sách query shape thường chạy và chọn index theo equality, range, order/group và covering columns.

### 5.4. Covering index vẫn có ích trong partition

Nếu truy vấn chỉ đọc các cột đã nằm trong secondary index, local index có thể là covering index cho từng partition được chọn. Điều đó giảm nhu cầu tra clustered record, nhưng không xóa chi phí phải truy cập từng partition trong tập đã chọn.

### 5.5. Tránh index dư thừa trên mọi partition

Mỗi index khai báo ở cấp bảng được duy trì trên tất cả partition. Thêm nhiều index làm tăng:

- Dung lượng index tổng thể.
- Chi phí INSERT/UPDATE/DELETE.
- Công việc cập nhật khi partition được reorganize hoặc dữ liệu di chuyển.
- Thời gian và tài nguyên cho bảo trì index.

Trước khi thêm index, kiểm tra SHOW INDEX, workload và EXPLAIN. Một index chỉ giúp một truy vấn hiếm có thể không đáng với chi phí ghi thường xuyên trên bảng lớn.

## 6. Truy vấn không có partition key và chi phí fan-out

Đây là tình huống cần đặc biệt chú ý với local index.

Ví dụ:

~~~sql
SELECT event_date, event_id, tenant_id
FROM event_log
WHERE event_id = 700001;
~~~

Truy vấn không có điều kiện event_date. Optimizer không thể xác định partition chỉ từ event_id nếu partition expression dựa trên event_date. Nó có thể phải kiểm tra nhiều partition.

Nếu có local index trên event_id, MySQL có thể dùng index đó trong từng partition cần truy cập. Nhưng vì không có global index, không có một B-tree toàn cục duy nhất chỉ ra partition chứa event_id.

### 6.1. Fan-out qua nhiều partition

Khi truy vấn chạm nhiều partition, chi phí có thể gồm:

- Xác định và mở các partition cần thiết.
- Tra cứu local index tương ứng ở nhiều partition.
- Đọc và kết hợp kết quả từ nhiều vùng.
- Sắp xếp hoặc loại trùng trên tập kết quả hợp nhất nếu query yêu cầu.
- Duy trì nhiều cấu trúc index và metadata hơn so với truy cập một vùng.

Số partition tăng không làm mọi truy vấn chậm theo cùng một tỷ lệ; chi phí phụ thuộc plan, dữ liệu và cache. Tuy nhiên, fan-out rộng là dấu hiệu cần xem xét khi query không lọc theo partition key.

### 6.2. Thêm index trên event_id có giải quyết hoàn toàn không?

Có thể tạo:

~~~sql
CREATE INDEX ix_event_id
ON event_log (event_id);
~~~

Index này cho phép tra event_id trong local index của mỗi partition. Nó có thể giảm chi phí so với quét dữ liệu từng partition, nhưng vẫn không biến thành global index và không bảo đảm lookup chỉ truy cập một partition.

Nếu truy vấn event_id là luồng truy cập chủ đạo, cần cân nhắc lại partition key, bảng registry hoặc thiết kế lưu trữ khác thay vì chỉ thêm index.

### 6.3. Partition key nên phản ánh cách truy vấn

Partition theo thời gian hợp lý khi phần lớn truy vấn và bảo trì có phạm vi thời gian. Nếu phần lớn truy vấn chỉ tìm theo tenant_id và không có điều kiện ngày, partition theo thời gian có thể làm truy vấn tenant phải fan-out qua nhiều partition.

Không chọn partition key chỉ vì cột đó tăng đều hoặc có cardinality cao. Hãy dựa vào query workload và yêu cầu retention.

## 7. Truy vấn qua một, vài và tất cả partition

Có thể chia workload thành ba nhóm:

| Kiểu truy vấn | Ví dụ | Đánh đổi |
|---|---|---|
| Một partition | Một ngày hoặc một tháng | Pruning tốt; local index nhỏ hơn |
| Một vài partition | Báo cáo quý hoặc khoảng ngày đi qua vài tháng | Fan-out vừa phải, cần kết hợp kết quả |
| Nhiều/tất cả partition | Tìm theo event_id không có ngày hoặc báo cáo toàn lịch sử | Có thể phải tra nhiều local index hoặc scan nhiều vùng |

### 7.1. Truy vấn một partition

~~~sql
SELECT COUNT(*)
FROM event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Với partition theo tháng và ranh giới khớp, truy vấn chỉ cần partition tháng 2. Đây là trường hợp partition pruning dễ phát huy tác dụng.

### 7.2. Truy vấn vài partition

~~~sql
SELECT event_type, COUNT(*) AS event_count
FROM event_log
WHERE event_date >= '2026-01-15'
  AND event_date < '2026-03-15'
GROUP BY event_type;
~~~

Truy vấn có thể chạm nhiều partition. Mỗi vùng được đọc và aggregate theo kế hoạch; sau đó kết quả được tổng hợp. Partitioning không loại bỏ chi phí đọc dữ liệu cần cho báo cáo.

### 7.3. Truy vấn toàn bộ partition

~~~sql
SELECT event_type, COUNT(*) AS event_count
FROM event_log
GROUP BY event_type;
~~~

Không có điều kiện partition key, nên nhiều hoặc toàn bộ partition có thể tham gia. Nếu đây là báo cáo thường xuyên, cân nhắc summary table, aggregate do ứng dụng duy trì hoặc pipeline phân tích phù hợp.

## 8. Kiểm tra partition và index trong EXPLAIN

Không đoán partition pruning từ câu SQL. Hãy xem plan.

### 8.1. EXPLAIN dạng tabular

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

Trong output truyền thống, cột partitions liệt kê các partition được optimizer chọn. Các cột type, possible_keys, key, rows, filtered và Extra cho biết access path và ước lượng đọc dữ liệu.

Nếu cột partitions chỉ liệt kê một partition khi truy vấn chỉ nằm trong tháng 2, pruning có hiệu lực. Nếu xuất hiện nhiều partition, kiểm tra lại ranh giới và điều kiện.

### 8.2. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

JSON thể hiện thông tin partition trong table access cùng với index, estimated rows và các chi tiết kế hoạch khác. Dùng nó khi cần phân tích tự động hoặc lưu lại plan để so sánh.

### 8.3. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

TREE giúp xem iterator và thứ tự thực thi. Tùy phiên bản, partition detail có thể hiển thị khác với tabular/JSON; khi cần danh sách partition rõ ràng, kiểm tra output truyền thống hoặc JSON.

### 8.4. EXPLAIN ANALYZE

MySQL 8.0.18+ hỗ trợ EXPLAIN ANALYZE cho SELECT tương thích:

~~~sql
EXPLAIN ANALYZE
SELECT event_id, event_type
FROM event_log
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18'
  AND tenant_id = 42;
~~~

EXPLAIN ANALYZE thực thi truy vấn thật và báo thời gian, số hàng thực tế, loops. Đối chiếu với estimated rows để phát hiện sai lệch thống kê. Chạy trên lab hoặc staging khi có thể; không coi đây là lệnh chỉ đọc metadata miễn phí.

### 8.5. So sánh truy vấn có và không có partition key

~~~sql
EXPLAIN
SELECT event_id
FROM event_log
WHERE event_date = '2026-02-12'
  AND event_id = 700001;

EXPLAIN
SELECT event_id
FROM event_log
WHERE event_id = 700001;
~~~

So sánh cột partitions và index được chọn. Truy vấn thứ nhất có thể pruning theo event_date; truy vấn thứ hai không có điều kiện partition key và có thể cần tìm trên nhiều partition.

## 9. Partition selection tường minh

MySQL hỗ trợ cú pháp chỉ định partition:

~~~sql
SELECT event_id, event_type
FROM event_log PARTITION (p2026_02)
WHERE event_date >= '2026-02-10'
  AND event_date < '2026-02-18';
~~~

Cú pháp này giới hạn truy vấn vào partition được nêu. Nó không chỉ là hint cho optimizer; nếu hàng cần tìm nằm ở partition khác, truy vấn có thể không trả hàng đó.

Chỉ dùng partition selection khi ứng dụng thực sự biết chắc partition cần truy cập và có cơ chế quản lý tên partition. Với truy vấn thông thường, để optimizer tự pruning từ điều kiện dữ liệu sẽ an toàn và dễ bảo trì hơn.

## 10. Partition key ảnh hưởng đến thiết kế khóa và truy vấn

Partition key cần được đánh giá cùng primary key, unique key và index.

### 10.1. Khóa chính composite

Với partition theo event_date:

~~~sql
PRIMARY KEY (event_date, event_id)
~~~

Khóa chính vừa thỏa quy tắc unique key vừa hỗ trợ truy vấn theo event_date và event_id. Tuy nhiên, thứ tự cột trong clustered index ảnh hưởng cách truy cập:

- Tìm theo event_date hoặc event_date + event_id có thể tận dụng leftmost prefix.
- Tìm chỉ theo event_id không tận dụng được leftmost prefix như một lookup trực tiếp.
- Một local secondary index trên event_id có thể hỗ trợ tìm trong từng partition, nhưng vẫn có fan-out.

### 10.2. Auto-increment

Nếu bảng partitioned dùng AUTO_INCREMENT, cột auto-increment vẫn phải được đánh index theo quy tắc MySQL và mọi unique key vẫn phải chứa partition columns. Thiết kế khóa chính composite có thể khiến việc bảo đảm ID duy nhất toàn bảng khác với một primary key chỉ gồm ID.

Hãy kiểm tra các ràng buộc AUTO_INCREMENT và unique key của phiên bản đang dùng trước khi chuyển một bảng hiện hữu sang partitioning. Không giả định thêm partition sẽ giữ nguyên mọi semantics của khóa.

### 10.3. Foreign key

InnoDB partitioned tables có giới hạn quan trọng: MySQL không hỗ trợ foreign key trên bảng InnoDB được partition, cả trường hợp bảng partitioned chứa foreign key lẫn trường hợp bảng khác tham chiếu đến nó. Nếu schema dựa vào foreign key, partitioning có thể đòi hỏi thay đổi thiết kế toàn vẹn dữ liệu.

Không bỏ foreign key chỉ để partition một bảng mà chưa chuyển trách nhiệm kiểm tra quan hệ sang cơ chế ứng dụng hoặc quy trình dữ liệu có kiểm soát.

## 11. Khi nào partitioning giúp ích?

Partitioning thường có giá trị khi:

- Dữ liệu lớn và truy vấn thường lọc theo partition key.
- Dữ liệu có vòng đời theo thời gian, ví dụ log, event, giao dịch lịch sử.
- Cần loại bỏ dữ liệu cũ theo partition thay vì DELETE hàng triệu record.
- Công việc bảo trì có thể giới hạn trong một số partition.
- Mỗi partition có kích thước phù hợp với cách vận hành và lưu trữ.

### 11.1. Retention bằng DROP PARTITION

Với dữ liệu hết hạn theo tháng, DBA có thể bỏ partition cũ:

~~~sql
ALTER TABLE event_log
DROP PARTITION p2026_01;
~~~

Đây là thao tác DDL làm loại bỏ toàn bộ dữ liệu của partition đó. Nó thường nhanh hơn DELETE từng hàng khi mục tiêu là bỏ trọn một vùng dữ liệu, nhưng cần kiểm tra backup, replication, quyền và kế hoạch vận hành trước khi chạy.

### 11.2. Partition không tự tăng tốc truy vấn không liên quan

Nếu ứng dụng thường truy vấn WHERE tenant_id = ? mà không lọc event_date, partition theo thời gian có thể khiến truy vấn phải fan-out qua nhiều partition. Local index (tenant_id) vẫn có thể được tra trong từng partition nhưng không có một global index duy nhất.

### 11.3. Partitioning không phải sharding

Partitioning giữ một bảng logic trong cùng một MySQL server/instance. Nó không tự phân phối dữ liệu sang nhiều máy chủ như sharding. Nếu nút thắt là CPU, RAM hoặc I/O của một server, partitioning không tự mở rộng tài nguyên tính toán theo chiều ngang.

## 12. Đánh đổi khi có nhiều partition

Nhiều partition có thể giúp chia nhỏ dữ liệu và quản lý retention, nhưng cũng tăng chi phí quản trị và có thể làm query fan-out lớn hơn.

### 12.1. Chi phí metadata và planning

Optimizer và server cần quản lý metadata của các partition. Bảng có quá nhiều partition có thể làm tăng chi phí mở bảng, chuẩn bị statement, lập kế hoạch và bảo trì. Mức ảnh hưởng phụ thuộc phiên bản, số partition được chạm và workload.

### 12.2. Chi phí local index

Mỗi index được khai báo có cấu trúc tương ứng trên từng partition. Nhiều partition và nhiều index làm tăng số cấu trúc cần quản lý, dung lượng và công việc bảo trì.

### 12.3. Query fan-out

Truy vấn đi qua nhiều partition phải phối hợp nhiều local index hoặc scan nhiều vùng. Với query không có partition predicate, lợi ích pruning gần như không có.

### 12.4. DDL và bảo trì

Thêm, bỏ, chia hoặc gộp partition có thể cần metadata lock và công việc tái tổ chức dữ liệu tùy thao tác. Hãy đánh giá thời gian, dung lượng tạm, replication lag và ảnh hưởng workload trước khi thay đổi partition layout.

### 12.5. Số partition không nên chọn theo cảm tính

Không tạo một partition cho mỗi ngày nếu workload và retention không cần. Cũng không gom quá nhiều năm vào một partition nếu việc bỏ dữ liệu theo tháng là yêu cầu quan trọng. Chọn granularity dựa trên:

- Khối lượng dữ liệu mỗi ngày/tháng.
- Khoảng thời gian phổ biến của truy vấn.
- Thời hạn retention.
- Tốc độ phát sinh partition mới.
- Chi phí DDL và giới hạn phiên bản.

## 13. Quy trình thiết kế index cho bảng partitioned

Một quy trình thực tế:

1. Thu thập query workload: cột lọc, join, order, group và khoảng thời gian.
2. Chọn partition key dựa trên truy vấn và retention.
3. Xác định unique key/primary key có thể chứa đủ partition columns hay không.
4. Phân loại query thành một partition, vài partition hoặc toàn bộ partition.
5. Thiết kế local index theo equality prefix, range columns và covering needs.
6. Kiểm tra các query không có partition key có fan-out quá rộng không.
7. Dùng EXPLAIN để xác minh pruning và index access.
8. Dùng EXPLAIN ANALYZE trên dữ liệu đại diện để đo actual rows và thời gian.
9. Đo chi phí ghi, dung lượng index và tốc độ DDL.
10. Theo dõi sau triển khai và điều chỉnh dựa trên workload thực.

### 13.1. Ma trận query và index

Ví dụ workload:

| Query shape | Partition key filter | Local index có thể đánh giá |
|---|---|---|
| Tenant trong một tháng | Có | (tenant_id, event_date) |
| Loại sự kiện trong một tháng | Có | (event_type, event_date) |
| Event theo ngày và ID | Có | Primary key (event_date, event_id) |
| Tìm event_id không có ngày | Không | (event_id) có thể giảm scan từng partition nhưng vẫn fan-out |
| Báo cáo toàn lịch sử theo loại | Không | (event_type, event_date) hoặc summary table tùy cardinality |

Đây là điểm bắt đầu để đo, không phải danh sách index bắt buộc. Không thêm toàn bộ index nếu workload không cần.

## 14. Bài thực hành: quan sát local index và partition pruning

Thực hiện trên MySQL 8.0 trong database lab. Bài tạo bảng event partitioned, kiểm tra query plan và so sánh truy vấn có/không có partition key.

### 14.1. Tạo bảng lab

~~~sql
CREATE TABLE lab_event_log (
    event_date DATE NOT NULL,
    event_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (event_date, event_id),
    KEY ix_lab_tenant_date (tenant_id, event_date),
    KEY ix_lab_type_date (event_type, event_date),
    KEY ix_lab_event_id (event_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

### 14.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO lab_event_log
    (event_date, event_id, tenant_id, event_type)
VALUES
    ('2026-01-10', 1001, 10, 'LOGIN'),
    ('2026-01-20', 1002, 20, 'PAYMENT'),
    ('2026-02-05', 1003, 10, 'LOGIN'),
    ('2026-02-12', 1004, 10, 'PAYMENT'),
    ('2026-02-18', 1005, 30, 'LOGIN'),
    ('2026-03-03', 1006, 20, 'PAYMENT'),
    ('2026-03-15', 1007, 10, 'LOGIN');
~~~

### 14.3. Bước 1 — Query trong một partition

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND tenant_id = 10;
~~~

Quan sát cột partitions. Partition tháng 2 được chọn. Xem index key và rows estimate; dữ liệu nhỏ có thể khiến optimizer chọn scan.

### 14.4. Bước 2 — Query đi qua nhiều partition

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-01-15'
  AND event_date < '2026-03-15'
  AND tenant_id = 10;
~~~

Quan sát các partition được chọn và so sánh với bước 1. Truy vấn đi qua ranh giới tháng nên cần nhiều partition hơn.

### 14.5. Bước 3 — Query thiếu partition key

~~~sql
EXPLAIN
SELECT event_date, event_id, tenant_id
FROM lab_event_log
WHERE event_id = 1004;
~~~

Quan sát cột partitions. Vì event_id không phải partition key, optimizer có thể phải xét nhiều partition. Index ix_lab_event_id là local index ở mỗi partition; nó không phải global index.

### 14.6. Bước 4 — So sánh composite index

~~~sql
EXPLAIN
SELECT event_id
FROM lab_event_log
WHERE tenant_id = 10
  AND event_date >= '2026-02-01'
  AND event_date < '2026-03-01';
~~~

Đọc key và access type. Xem optimizer có chọn ix_lab_tenant_date hay không. Với bảng nhỏ, scan có thể rẻ hơn index lookup; điều đó là quyết định chi phí của optimizer.

### 14.7. Bước 5 — Xem danh sách partition

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    TABLE_ROWS
FROM information_schema.partitions
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lab_event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

TABLE_ROWS của InnoDB là ước lượng, không phải lúc nào cũng chính xác tuyệt đối. Dùng truy vấn COUNT theo partition key nếu cần số hàng chính xác cho bài lab.

### 14.8. Bước 6 — Đo bằng EXPLAIN ANALYZE

Trên MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
SELECT event_id, event_type
FROM lab_event_log
WHERE event_date >= '2026-02-01'
  AND event_date < '2026-03-01'
  AND tenant_id = 10;
~~~

Đọc actual rows, loops và thời gian. Dữ liệu mẫu quá nhỏ để đánh giá hiệu năng thực tế; mục tiêu là hiểu sự khác nhau giữa partition pruning và index access.

### 14.9. Bước 7 — Dọn bảng lab

~~~sql
DROP TABLE lab_event_log;
~~~

Chỉ xóa bảng lab vừa tạo.

**Kết quả cần đạt:** giải thích được local index, vì sao MySQL không có global index cho partitioned table, vì sao unique key phải chứa partition columns, cách đọc pruning trong EXPLAIN và đánh đổi của truy vấn không có partition key.

## 15. Nguyên tắc cần ghi nhớ

- Mỗi partition InnoDB có cấu trúc index cục bộ; định nghĩa index được khai báo ở cấp bảng và áp dụng cho mọi partition.
- MySQL không hỗ trợ global index cho bảng partitioned; truy vấn không có partition key có thể phải tra local index ở nhiều partition.
- Partition pruning loại partition không liên quan; index tiếp tục tìm hàng bên trong partition được chọn.
- Partitioning không thay thế index và không tự làm mọi truy vấn nhanh hơn.
- Mọi unique key, gồm primary key, phải chứa tất cả cột được dùng trong partitioning expression.
- Primary key composite chứa partition key có thể không bảo đảm ID nghiệp vụ duy nhất toàn bảng.
- Nếu cần uniqueness toàn cục trên cột không thuộc partition key, cân nhắc registry table hoặc ID toàn cục và giữ consistency bằng transaction.
- Chọn thứ tự composite index theo equality, range, ordering và covering needs; partition key và index column order là hai quyết định riêng.
- Truy vấn qua nhiều partition có thể tạo fan-out qua nhiều local index, tăng chi phí đọc và kết hợp kết quả.
- Viết predicate trực tiếp trên partition key để optimizer dễ pruning; xác minh bằng cột partitions trong EXPLAIN.
- Partition selection tường minh giới hạn dữ liệu được đọc và có thể bỏ sót hàng nếu chọn sai partition.
- InnoDB partitioned table không hỗ trợ foreign key; đánh giá tác động lên toàn vẹn dữ liệu trước khi partition.
- Partitioning phù hợp với workload có điều kiện partition key và nhu cầu retention; không thay thế sharding.
- Nhiều partition làm tăng metadata, index structures và chi phí quản trị; chọn granularity theo workload.
- Dùng EXPLAIN/JSON để xem partition và index; EXPLAIN ANALYZE để đo thực thi thật trên MySQL 8.0.18+.

Thiết kế partition và index cần bắt đầu từ cách ứng dụng truy vấn dữ liệu. Khi truy vấn lọc tốt theo partition key, pruning giảm số vùng phải truy cập và local index tìm hàng trong các vùng đó. Khi truy vấn bỏ qua partition key, local index có thể phải được tra cứu trên nhiều partition; khi đó lợi ích phân vùng giảm và chi phí fan-out trở thành yếu tố cần đo đạc.
