# CQL và khác biệt với ngôn ngữ truy vấn quan hệ

**CQL (Cassandra Query Language)** là ngôn ngữ truy vấn của **Apache Cassandra**. Cú pháp của CQL có nhiều điểm giống SQL, chẳng hạn `CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE` và `DELETE`. Tuy nhiên, **CQL không phải SQL trên một cơ sở dữ liệu quan hệ khác tên**: Cassandra phân phối dữ liệu theo **partition key**, sắp xếp hàng bằng **clustering columns**, và tối ưu cho những đường đọc/ghi đã được thiết kế trước. Cú pháp quen thuộc có thể che giấu những khác biệt rất lớn về truy vấn, tính nhất quán và hiệu năng.

Bài thuộc chương **CQL và CqlTemplate** của module **SPRING_DATA_CASSANDRA**. Trong Spring Data Cassandra, developer có thể dùng entity mapping, repository, `CassandraTemplate` hoặc `CqlTemplate` để làm việc với CQL. Hiểu đúng CQL là điều kiện để chọn partition key, viết truy vấn hợp lệ, phân trang và kiểm soát tải của một hệ thống dữ liệu phân tán.

## 1. CQL giống SQL ở cú pháp, khác ở mô hình vận hành

| Khía cạnh | SQL quan hệ thường gặp | CQL trong Cassandra |
| --- | --- | --- |
| Đơn vị tổ chức | Database, schema, table | Keyspace, table, partition |
| Mô hình dữ liệu | Thường chuẩn hóa, liên kết bằng khóa ngoại | Thường **thiết kế bảng theo truy vấn**, có thể nhân bản dữ liệu |
| Khóa chính | Xác định duy nhất hàng, có thể phục vụ index | Xác định **partition** và thứ tự/định danh hàng trong partition |
| Phân phối dữ liệu | Tùy hệ quản trị, có thể không phân tán | Partition key được băm để định tuyến dữ liệu đến replica |
| `JOIN` | Là thao tác phổ biến | **Không hỗ trợ SQL JOIN giữa bảng** |
| `WHERE` | Có nhiều dạng predicate, optimizer chọn plan | Bị ràng buộc mạnh bởi partition key, clustering key và index |
| `ORDER BY` | Có thể sắp xếp tập kết quả rộng, với chi phí tương ứng | Chủ yếu dựa trên **thứ tự clustering trong partition** |
| `GROUP BY`/aggregate | Thường hỗ trợ phân tích đa dạng | Hạn chế; không thay thế công cụ phân tích dữ liệu quy mô lớn |
| `OFFSET` | Có ở nhiều SQL dialect | Không có cơ chế truy cập offset ngẫu nhiên tương đương |
| `INSERT`/`UPDATE` | Có thể có phân biệt tồn tại/chưa tồn tại theo ràng buộc | **Upsert** theo khóa là hành vi thông thường |
| Transaction | Nhiều hệ hỗ trợ giao dịch ACID nhiều hàng/bảng | Không có transaction SQL tổng quát tương đương; có LWT cho điều kiện cụ thể |

Không nên suy ra rằng PostgreSQL/MySQL và Cassandra có cùng bộ tối ưu hóa truy vấn chỉ vì cùng viết `SELECT ... FROM ... WHERE ...`. Trong Cassandra, cách chọn khóa và vị trí dữ liệu là một phần của **thiết kế API truy vấn**, không chỉ là chi tiết lưu trữ.

## 2. Keyspace, replication và bảng đầu tiên

Trong SQL quan hệ, developer thường tạo một database rồi thêm bảng. Trong Cassandra, **keyspace** còn chứa chính sách replication dùng để xác định dữ liệu được nhân bản thế nào.

Ví dụ CQL:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Ý nghĩa:

- `commerce_ks` là tên keyspace.
- `NetworkTopologyStrategy` cho phép cấu hình replication theo datacenter.
- `'dc1': 3` là số replica mục tiêu của keyspace trong datacenter có tên `dc1`.

**Ví dụ giả định datacenter thực sự tên `dc1` và có đủ node.** Không đặt RF = 3 trên cluster một node rồi cho rằng ứng dụng thực sự có ba replica độc lập. Với nhiều datacenter, phải thiết kế số replica cho từng datacenter và tính đến consistency level, capacity, repair.

Tạo bảng đơn hàng:

~~~sql
CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_customer_day (
    customer_id  uuid,
    order_day    date,
    placed_at    timestamp,
    order_id     uuid,
    status       text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Mục tiêu truy vấn đã biết: **“Lấy các đơn hàng gần nhất của một khách hàng trong một ngày.”** Bảng được tổ chức để đáp ứng trực tiếp mẫu đọc đó.

## 3. Primary key không chỉ để chống trùng

Cấu trúc khóa trong ví dụ:

~~~text
PRIMARY KEY (
    (customer_id, order_day),  -- composite partition key
    placed_at,                 -- clustering column 1
    order_id                   -- clustering column 2
)
~~~

| Thành phần | Vai trò |
| --- | --- |
| `customer_id` + `order_day` | Cặp giá trị **partition key**; dùng để tính token và định tuyến đến replica |
| `placed_at` | Clustering column, giúp sắp xếp đơn theo thời gian trong partition |
| `order_id` | Clustering column bổ sung, phân biệt các đơn có cùng thời điểm |
| Cả bốn thành phần | Primary key đầy đủ để định danh một hàng trong bảng |

~~~text
Partition (customer=A, day=2026-11-25)
    ├── placed_at=14:30, order_id=003
    ├── placed_at=09:10, order_id=002
    └── placed_at=08:00, order_id=001

Partition (customer=A, day=2026-11-26)
    └── các đơn ngày 26, ở partition khác

Partition (customer=B, day=2026-11-25)
    └── các đơn của khách B, ở partition khác
~~~

Để chia partition theo **khách hàng và ngày**, phải dùng hai lớp ngoặc ở `PRIMARY KEY ((customer_id, order_day), ...)`. Nếu chỉ dùng:

~~~sql
PRIMARY KEY (customer_id, order_day, placed_at, order_id)
~~~

thì **chỉ `customer_id` là partition key**, còn `order_day` trở thành clustering column. Dữ liệu của một khách có thể dồn vào partition ngày càng lớn, dù cú pháp trông gần như giống nhau.

Clustering columns **không** giúp rải dữ liệu của một partition thành nhiều token. Cần giới hạn số hàng, dung lượng và tốc độ truy cập của partition bằng thiết kế key/time bucket/shard khi cần.

## 4. SELECT theo partition: tình huống CQL hoạt động tốt

Truy vấn gần nhất:

~~~sql
SELECT placed_at, order_id, status, total_amount
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 20;
~~~

Ký hiệu `?` là placeholder dùng cho tham số **bind** trong prepared statement, không phải literal chạy trực tiếp bằng `cqlsh` nếu chưa chuẩn bị statement. Truy vấn cung cấp **đủ partition key**, nên Cassandra có thể định tuyến đến các replica chịu trách nhiệm cho một partition. Thứ tự clustering đã định trong DDL là `placed_at DESC, order_id DESC`.

Đọc trong một khoảng thời gian của cùng partition:

~~~sql
SELECT placed_at, order_id, status
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at >= ?
  AND placed_at < ?
LIMIT 20;
~~~

Ở đây điều kiện equality trên partition key được cung cấp đầy đủ, sau đó range áp dụng cho clustering column đầu tiên. Nếu `order_day` là ngày được tính từ `placed_at` theo UTC, reader và writer phải dùng **cùng quy tắc tính bucket**. Một khoảng thời gian qua ranh giới ngày phải được tách thành nhiều partition ngày, thay vì chỉ thêm điều kiện range trên `placed_at` rồi bỏ `order_day`.

## 5. WHERE không phải bộ lọc tùy ý trên mọi cột

Trong SQL quan hệ, câu sau có thể được optimizer xử lý bằng index hoặc table scan:

~~~sql
-- Ví dụ phong cách SQL quan hệ, không phải truy vấn thích hợp
-- cho bảng Cassandra ở trên.
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Với bảng CQL `orders_by_customer_day`, `status` **không nằm trong partition key hoặc clustering key**, và không có index phục vụ truy vấn này. Viết:

~~~sql
-- Không phù hợp với mô hình khóa của bảng ví dụ.
SELECT *
FROM commerce_ks.orders_by_customer_day
WHERE status = 'PAID';
~~~

thường bị Cassandra từ chối do thiếu đường truy cập phù hợp. Thêm `ALLOW FILTERING` có thể cho phép một số truy vấn chạy, nhưng thường tạo việc đọc/lọc tốn kém và độ trễ khó dự đoán. **Không coi `ALLOW FILTERING` là cách khắc phục thiết kế bảng thiếu đường truy vấn.**

Nếu chức năng thật sự cần **“liệt kê đơn PAID theo ngày”**, hãy xem đó là một **access pattern khác** và thiết kế bảng đọc riêng, ví dụ:

~~~sql
CREATE TABLE commerce_ks.orders_by_status_day (
    status       text,
    order_day    date,
    placed_at    timestamp,
    order_id     uuid,
    customer_id  uuid,
    total_amount decimal,
    PRIMARY KEY ((status, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Khi đó:

~~~sql
SELECT placed_at, order_id, customer_id, total_amount
FROM commerce_ks.orders_by_status_day
WHERE status = 'PAID' AND order_day = ?
LIMIT 20;
~~~

**Đánh đổi:** dữ liệu đơn hàng bị nhân bản giữa hai bảng; service phải duy trì đồng bộ khi trạng thái thay đổi. Nếu chuyển từ `NEW` sang `PAID`, cần cập nhật đường đọc mới và xử lý dữ liệu hàng cũ ở bảng theo status. Không có JOIN hoặc foreign key tự động duy trì mối liên hệ. Partition theo `(status, order_day)` cũng có thể **quá lớn/hot** vì số lượng trạng thái ít; phải đo và cân nhắc shard/bucket khác khi quy mô tăng.

Một số phiên bản Cassandra có **secondary index hoặc Storage-Attached Index (SAI)** phục vụ các trường hợp truy vấn bổ sung. Tuy nhiên index có giới hạn về phiên bản, toán tử và chi phí; không thay thế mặc định cho bảng được thiết kế theo access pattern, nhất là ở những truy vấn tần suất cao.

## 6. Cassandra không thực hiện JOIN giữa những bảng nghiệp vụ

Trong SQL quan hệ, ta có thể dùng:

~~~sql
-- Minh họa truy vấn SQL quan hệ.
SELECT o.order_id, o.total_amount, c.full_name
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_id = ?;
~~~

CQL không cung cấp một phép `JOIN` tổng quát để ghép hai bảng nghiệp vụ giống truy vấn trên. Các lựa chọn thường gặp:

1. **Denormalization:** lưu những thông tin cần hiển thị cùng hàng trong bảng phục vụ truy vấn, khi phù hợp vòng đời dữ liệu và chi phí đồng bộ.
2. **Nhiều truy vấn có kiểm soát:** đọc đơn rồi đọc khách hàng theo một khóa đã biết, sau đó ghép ở tầng service; cần quản lý số lần đọc và consistency.
3. **Bảng theo từng access pattern:** ví dụ `orders_by_customer_day` để liệt kê, `order_by_id` để tìm theo mã đơn, bảng tổng hợp phục vụ báo cáo cụ thể.
4. **Hệ phân tích/tìm kiếm khác:** nếu yêu cầu JOIN ad hoc, thống kê liên bảng phức tạp hoặc tìm kiếm trên dữ liệu rất lớn.

Đừng đưa mô hình chuẩn hóa quan hệ sang Cassandra theo kiểu “mỗi entity một bảng, lúc cần sẽ JOIN” rồi cố xử lý bằng `ALLOW FILTERING`. Trong Cassandra, việc cần đọc dữ liệu thế nào nên được xác định **trước khi quyết định bảng và khóa**.

## 7. ORDER BY chỉ có ý nghĩa trong khuôn khổ clustering

Trong SQL, có thể viết `ORDER BY total_amount DESC` để sắp xếp kết quả bất kỳ (với chi phí xử lý). Trên bảng CQL ở ví dụ, thứ tự tự nhiên đã được tổ chức bằng clustering columns:

~~~sql
WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC)
~~~

Khi đọc **một partition**, Cassandra có thể trả các hàng theo thứ tự clustering được lưu. CQL cho phép điều khiển hướng sắp xếp clustering trong những giới hạn của định nghĩa bảng và phiên bản, **không phải sắp xếp tùy ý theo mọi cột**.

Ví dụ sau không nên kỳ vọng chạy như một SQL query thông thường:

~~~sql
-- total_amount không phải clustering column.
SELECT order_id, total_amount
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
ORDER BY total_amount DESC;
~~~

Thay vì buộc Cassandra sắp xếp theo `total_amount` trên mỗi request, hãy hỏi lại: ứng dụng thực sự cần top đơn theo giá trị lớn nhất? Nếu đó là truy vấn nóng, có thể cần **bảng đọc riêng** với clustering columns phục vụ thứ tự đó.

**Lưu ý:** thứ tự clustering có hiệu lực trong **từng partition**, không tự tạo thứ tự toàn cục của toàn cluster. Khi ghép kết quả từ nhiều partition/ngày, service phải quản lý thứ tự và pagination.

## 8. GROUP BY, DISTINCT và COUNT có phạm vi hẹp

Một truy vấn SQL quan hệ phổ biến:

~~~sql
-- SQL quan hệ minh họa:
SELECT status, COUNT(*)
FROM orders
GROUP BY status;
~~~

CQL không cung cấp mô hình aggregation ad hoc rộng như một hệ phân tích quan hệ. Cassandra có một số phép aggregate và `GROUP BY` nhưng bị **giới hạn theo các thành phần primary key và mẫu truy vấn**; không tự động nhóm/sắp xếp mọi cột trên toàn cluster.

Tương tự, `DISTINCT` trong CQL **không phải** một công cụ lấy mọi giá trị duy nhất của mọi cột tùy ý. Tính năng này được giới hạn bởi cách Cassandra tổ chức partition.

Không dùng định kỳ:

~~~sql
-- Tránh dùng làm metric nóng trên bảng lớn.
SELECT COUNT(*)
FROM commerce_ks.orders_by_customer_day;
~~~

Đếm trên dữ liệu nhiều partition có thể phải đọc rất nhiều hàng/partition và tốn tài nguyên. Để xây dashboard thống kê, cân nhắc bảng tổng hợp được cập nhật theo luồng ghi, hệ thống streaming/analytics, hoặc metrics từ pipeline nhập liệu. Các phép tổng hợp cần được thiết kế cho tính chính xác và chấp nhận độ trễ phù hợp, không đơn giản thay bằng CQL `GROUP BY`.

## 9. INSERT và UPDATE thường mang ngữ nghĩa upsert

Ví dụ thêm đơn:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id, status, total_amount
) VALUES (?, ?, ?, ?, ?, ?);
~~~

Cassandra định danh hàng bằng **toàn bộ primary key**. Nếu ghi lại cùng khóa, các cột được ghi có thể cập nhật giá trị theo timestamp/last-write-wins; không tạo thêm hàng logic có cùng primary key.

Tương tự:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET status = 'PAID'
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Lệnh `UPDATE` thông thường không bắt buộc hàng đã tồn tại từ trước; nó có thể tạo dữ liệu tại khóa được chỉ định. Đây là khác biệt đáng lưu ý so với kỳ vọng “UPDATE ảnh hưởng 0 hàng nếu chưa có bản ghi” trong nhiều RDBMS.

Để thực hiện **“chỉ tạo nếu chưa có”**, CQL hỗ trợ light-weight transaction (LWT):

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id, status
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

LWT có chi phí và hành vi phối hợp replica khác ghi thông thường; cần kiểm tra kết quả **applied** và đánh giá nhu cầu nghiệp vụ. LWT **không** biến Cassandra thành hệ quản trị có giao dịch ACID tổng quát với JOIN và rollback tùy ý trên nhiều bảng.

### TTL và dữ liệu hết hạn

CQL hỗ trợ thời gian sống của giá trị được ghi:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id, status
) VALUES (?, ?, ?, ?, ?)
USING TTL 604800;
~~~

Giá trị `604800` là 7 ngày tính bằng giây. TTL có thể làm dữ liệu hết hạn về mặt logic, nhưng **không đồng nghĩa SSTable được thu hồi ngay sau 7 ngày**: tombstone và compaction quyết định lúc thu hồi vật lý. TTL cũng có thể khác giữa các cell được ghi trong những lần khác nhau.

## 10. DELETE tạo tombstone, không nhất thiết “xóa khỏi đĩa ngay”

~~~sql
DELETE FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Trong hệ phân tán, xóa phải được truyền đạt tới các replica. Cassandra sử dụng **tombstone** để ghi nhận việc xóa, hỗ trợ cơ chế đồng bộ và ngăn dữ liệu cũ xuất hiện trở lại trong những điều kiện vận hành bình thường.

Các hệ quả quan trọng:

- Câu `DELETE` thông thường không tự chứng minh rằng hàng từng tồn tại.
- Xóa/TTL nhiều trong partition rộng có thể tạo chi phí đọc và compaction.
- Đọc trước rồi xóa không thành transaction nguyên tử.
- Khi nghiệp vụ đòi hỏi không mất dấu lịch sử, có thể phù hợp hơn với trạng thái soft-delete hoặc mô hình event append-only.

Trong một số trường hợp, CQL cũng cho phép xóa theo phạm vi của khóa partition/clustering; hãy kiểm tra phạm vi thật trước khi chạy, tránh xóa cả partition khi chỉ muốn một hàng.

## 11. BATCH CQL không phải cách “đổ dữ liệu hàng loạt” mặc định

CQL có cú pháp `BEGIN BATCH ... APPLY BATCH`, ví dụ ghi hai bản ghi phục vụ cùng một nghiệp vụ. Tuy nhiên, **batch Cassandra không có mục đích chính là tăng throughput cho hàng triệu ghi phân tán**.

Điểm cần nhớ:

| Tình huống | Đánh giá |
| --- | --- |
| Vài thay đổi liên quan trong cùng partition | Có thể cân nhắc batch phù hợp ngữ nghĩa |
| Nhiều partition trải rộng cluster | Batch có chi phí phối hợp và có thể tạo tải nóng lên coordinator |
| Muốn bulk import dữ liệu lớn | Dùng cơ chế/pipeline nhập liệu phù hợp, giới hạn concurrency và backpressure |
| Mong batch tương đương SQL transaction toàn cục có rollback | **Không** nên giả định như vậy |

**Logged batch** và **unlogged batch** có ý nghĩa khác nhau về điều phối/khả năng phục hồi, nhưng không nên tóm tắt rằng “batch thì luôn nhanh hơn” hoặc “batch cho phép transaction SQL đầy đủ”. Hãy hiểu ràng buộc tính nguyên tử cụ thể của Cassandra và kiểm thử các trường hợp lỗi/timeout.

## 12. Paging: không có OFFSET ngẫu nhiên như SQL

Một SQL query phổ biến:

~~~sql
-- Ví dụ SQL quan hệ:
SELECT *
FROM orders
ORDER BY placed_at DESC
LIMIT 20 OFFSET 1000;
~~~

Cassandra **không** có cách lấy ngẫu nhiên “bỏ qua 1.000 hàng rồi lấy 20 hàng” tương đương về mặt API/chi phí. Java Driver hỗ trợ **paging state** để tiếp tục một truy vấn từ vị trí đã đọc.

Phân biệt:

1. **`LIMIT`:** giới hạn tổng số hàng cần trả cho truy vấn.
2. **Page size/fetch size:** quy định số hàng driver lấy theo mỗi đợt, không nhất thiết bằng `LIMIT`.
3. **Paging state:** dấu mốc tiếp tục gắn với cùng câu CQL và tham số; không nên dùng lại cho truy vấn khác.
4. **Quét nhiều partition:** cần chiến lược fan-out, sắp xếp/gộp dữ liệu, giữ continuation state; một paging state không tự biểu diễn toàn bộ kết quả ghép.

Với bảng theo ngày, API lịch sử 30 ngày thường cần đọc các partition tương ứng theo thứ tự gần nhất trước, có giới hạn số bucket. Thay vì giả định có `OFFSET`, thiết kế cursor/continuation phù hợp với Cassandra và nhu cầu UI.

Dữ liệu có thể tiếp tục được ghi hoặc xóa giữa các trang, nên paging **không bảo đảm** một snapshot cố định như một số luồng dữ liệu có transaction snapshot trong hệ quan hệ.

## 13. Consistency và replication nằm trong quyết định truy vấn

Trong hệ quan hệ đơn node, developer thường giả định một điểm đọc/ghi. Trong Cassandra, một partition có thể được nhân bản trên nhiều node. **Consistency level (CL)** xác định số replica cần phản hồi đối với thao tác đọc/ghi.

Giả sử keyspace có RF = 3 trong một datacenter phù hợp:

| Consistency level | Yêu cầu minh họa | Đánh đổi |
| --- | --- | --- |
| `ONE` | Một replica phản hồi | Tăng khả năng phản hồi khi ít replica khả dụng, có thể đọc giá trị cũ trong một số trường hợp |
| `LOCAL_QUORUM` | Ít nhất hai trong ba replica cục bộ | Yêu cầu nhiều replica hơn; có thể tăng độ trễ/giảm khả dụng khi replica lỗi |
| `ALL` | Tất cả replica liên quan | Nhạy với lỗi replica, độ sẵn sàng thấp hơn |

CL không thay đổi schema hay giúp CQL truy vấn theo một cột không thuộc khóa/index. Một partition key bị ghi quá nóng vẫn làm các replica của partition chịu tải; chỉ tăng RF không phải chiến lược chia nhỏ partition.

**Lỗi timeout không có nghĩa chắc chắn dữ liệu chưa được ghi.** Cần xử lý retry/idempotency, nhất là khi code tự sinh `order_id` mới mỗi lần retry hoặc có side effect ở hệ thống ngoài.

## 14. CqlTemplate khác CassandraTemplate thế nào?

Trong Spring Data Cassandra có hai lớp tên khá giống nhau nhưng ở **mức trừu tượng khác nhau**:

| Tiêu chí | **CqlTemplate** | **CassandraTemplate** |
| --- | --- | --- |
| Trọng tâm | Thực thi **CQL** và ánh xạ kết quả mức thấp | Thao tác **entity** theo metadata Spring Data |
| Kiểu dữ liệu đầu vào | CQL string/bind và các đối tượng mức driver | Entity, primary key class, `Query`/`Update` |
| Đọc kết quả | Có thể dùng `RowMapper` để tự dựng object | Converter tự map hàng vào entity Java |
| Mức kiểm soát CQL | Rõ ràng hơn, gần truy vấn trực tiếp | Truy vấn được hỗ trợ/bổ sung qua abstraction |
| Đảm bảo hiệu năng | Không tự giải quyết query thiếu khóa | Cũng không tự giải quyết query thiếu khóa |
| Khi nên dùng | CQL tùy biến, chọn cột rõ ràng, kết quả không phải entity | CRUD theo entity và truy vấn có mapping ổn định |

§CqlTemplate§ ở package `org.springframework.data.cassandra.core.cql`, còn `CassandraTemplate` ở package `org.springframework.data.cassandra.core`. Hai lớp đều làm việc với Cassandra, nhưng **CqlTemplate không tự biến kết quả bất kỳ thành entity theo annotation giống CassandraTemplate**.

Ví dụ nhỏ dùng `CqlTemplate` để đọc thông tin của chính node Cassandra mà session kết nối tới:

~~~java
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Service
public class CassandraDiagnostics {

    private final CqlTemplate cqlTemplate;

    public CassandraDiagnostics(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public List<String> localDatacenter() {
        return cqlTemplate.query(
            "SELECT data_center FROM system.local",
            (row, rowNum) -> row.getString("data_center")
        );
    }
}
~~~

Ví dụ dùng truy vấn cố định không có input từ người dùng và cho thấy vai trò của **row mapper**. Cần thêm import `List`, `Service` và cấu hình bean/template phù hợp với phiên bản đang dùng. Các method/signature cụ thể có thể thay đổi giữa phiên bản Spring Data Cassandra; kiểm tra reference API dự án trước khi áp dụng.

### Truy vấn nghiệp vụ phải bind tham số

Với giá trị đầu vào từ HTTP request, **không nối chuỗi CQL** như:

~~~java
// KHÔNG dùng: lắp trực tiếp dữ liệu request vào CQL.
String bad = "SELECT * FROM orders_by_customer_day " +
             "WHERE customer_id = " + requestId;
~~~

Thay vào đó, dùng binding của template theo API phiên bản đang dùng, hoặc **prepared statement** của Java Driver:

~~~java
PreparedStatement prepared = session.prepare("""
    SELECT placed_at, order_id, status, total_amount
    FROM commerce_ks.orders_by_customer_day
    WHERE customer_id = ?
      AND order_day = ?
    LIMIT 20
    """);

BoundStatement statement = prepared.bind(customerId, orderDay);
ResultSet result = session.execute(statement);
~~~

Trong đó `session` là `CqlSession` của Java Driver, `customerId` là `UUID`, `orderDay` là `LocalDate`. Nếu ứng dụng sử dụng `CqlTemplate`, ưu tiên các overload hỗ trợ bind parameters hoặc statement phù hợp **với đúng phiên bản**; không dùng nối chuỗi vì cú pháp dễ lỗi và có nguy cơ injection.

**Prepared statement không thể sửa một truy vấn thiếu partition key.** Nó chỉ chuẩn bị và bind tham số đúng kiểu; cách Cassandra định tuyến dữ liệu vẫn dựa trên schema và khóa.

## 15. CQL với Spring Data Cassandra: ánh xạ đúng khóa

Nếu đã có bảng `orders_by_customer_day`, một entity Spring Data Cassandra có thể dùng:

~~~java
@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "order_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(name = "placed_at", ordinal = 2,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private UUID orderId;

    // Constructor/accessor/equals/hashCode theo mapping thực tế.
}

@Table("orders_by_customer_day")
public class OrderRow {
    @PrimaryKey
    private OrderKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;
}
~~~

Đoạn mã lược bỏ import/constructor và cấu hình Spring Boot. Nó minh họa rằng **Spring Data metadata phải khớp với CQL DDL**: hai cột partitioned ở Java, hai cột clustered đúng ordinal/thứ tự và tên cột tương ứng.

Repository hoặc `CassandraTemplate` giúp giảm code mapping, nhưng **không tự tạo JOIN**, không thực hiện group-by toàn cluster hiệu quả và không thay đổi giới hạn `WHERE` của CQL. Nếu dùng custom converters, giá trị đưa vào predicate cần được chuyển thành đúng kiểu/biểu diễn CQL mà database đã lưu.

## 16. Checklist khi chuyển từ SQL sang CQL

Trước khi viết câu CQL, hãy trả lời:

- [ ] Truy vấn nghiệp vụ chính xác là gì: theo khách/ngày, theo mã đơn, theo trạng thái hay theo khoảng thời gian?
- [ ] Bảng được thiết kế cho **access pattern** nào?
- [ ] Có cung cấp đầy đủ partition key trong `WHERE` không?
- [ ] Clustering columns có hỗ trợ thứ tự và range cần dùng không?
- [ ] Partition lớn nhất dự kiến bao nhiêu hàng/byte, tốc độ ghi/đọc cao điểm thế nào?
- [ ] Có đang cố mô phỏng SQL JOIN, GROUP BY, ORDER BY tùy ý hoặc OFFSET trên Cassandra không?
- [ ] Nếu dùng bảng denormalized, có phương án cập nhật và dữ liệu nhất quán giữa các bảng chưa?
- [ ] Với ghi/xóa, đã hiểu upsert, TTL, tombstone và conditional write chưa?
- [ ] Paging, consistency level và timeout đã được giới hạn/kiểm thử theo tải thực tế chưa?
- [ ] Các tham số đã được bind, không ghép chuỗi CQL từ input chưa tin cậy?
- [ ] Đã biết khi nào nên dùng `CqlTemplate`, `CassandraTemplate` hoặc Java Driver trực tiếp?

### Tự kiểm tra

**Câu 1.** Với khóa `PRIMARY KEY ((customer_id, order_day), placed_at, order_id)`, partition key là gì?

**Đáp án:** Cặp `(customer_id, order_day)`. `placed_at` và `order_id` là clustering columns, không tự tạo thêm partition.

**Câu 2.** Có thể viết `SELECT * FROM orders_by_customer_day WHERE status = 'PAID'` như SQL quan hệ mà không xét thiết kế khóa không?

**Đáp án:** Không nên. `status` không thuộc khóa/index trong ví dụ và truy vấn không xác định partition. Cần bảng/index phù hợp với access pattern, không dựa vào `ALLOW FILTERING` như giải pháp mặc định.

**Câu 3.** CQL `UPDATE` thành công có chứng minh rằng hàng đã tồn tại trước khi cập nhật không?

**Đáp án:** Không. `UPDATE` thông thường có ngữ nghĩa upsert. Khi cần điều kiện, phải dùng cơ chế conditional write/LWT phù hợp.

**Câu 4.** Vì sao Cassandra không phù hợp với `LIMIT 20 OFFSET 1000` như một API phân trang tùy ý?

**Đáp án:** Cassandra phân trang dựa trên paging state/continuation, không có ngẫu nhiên offset rẻ tương đương SQL. Cần thiết kế cursor và giới hạn số partition được đọc.

**Câu 5.** `CqlTemplate` có tự thay đổi ngữ nghĩa `WHERE` của Cassandra so với Java Driver không?

**Đáp án:** Không. Nó hỗ trợ thực thi và ánh xạ kết quả CQL, nhưng quy tắc partition key, clustering, index và consistency vẫn do Cassandra/driver quyết định.

---

**Ghi nhớ:** **CQL có cú pháp giống SQL nhưng được tối ưu cho mô hình dữ liệu phân tán theo partition, không phải JOIN và truy vấn tùy ý**. Hãy bắt đầu từ câu hỏi mà ứng dụng cần trả lời, thiết kế bảng/partition key/clustering key cho câu hỏi đó, rồi dùng `CqlTemplate`, `CassandraTemplate` hoặc repository để thực hiện CQL đúng. Một câu truy vấn có bind chính xác và mapping đẹp vẫn sẽ chậm hoặc không hợp lệ nếu **access pattern không phù hợp với bảng**.
