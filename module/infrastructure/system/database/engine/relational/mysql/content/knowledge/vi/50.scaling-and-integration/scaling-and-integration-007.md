# Chia dữ liệu theo tenant/khóa và phân biệt sharding với partitioning

Khi dữ liệu MySQL tăng, một bảng lớn có thể khó quản lý, truy vấn hoặc duy trì trong giới hạn tài nguyên của một máy chủ. Có hai kỹ thuật thường được nhắc đến: **partitioning** và **sharding**. Partitioning chia một bảng thành nhiều phân vùng do cùng một MySQL instance quản lý; sharding phân phối các phần dữ liệu qua nhiều MySQL instance hoặc cụm độc lập. Hai kỹ thuật có thể cùng xuất hiện trong một hệ thống, nhưng giải quyết các bài toán khác nhau.

Việc chọn tenant ID hoặc một khóa nghiệp vụ làm khóa phân chia quyết định dữ liệu nào được đặt cùng nhau, truy vấn nào cần định tuyến và thao tác nào có thể thực hiện trong một transaction cục bộ. Một shard key tốt giúp các truy vấn thường xuyên chạm ít máy chủ, phân phối tải tương đối đều và giữ các giao dịch liên quan trong cùng phạm vi dữ liệu. Một shard key kém có thể tạo hot shard, fan-out query, khó bảo đảm uniqueness hoặc làm việc mở rộng trở nên tốn kém.

Bài học thuộc chương **Mở rộng hệ thống** của module DATABASE_MYSQL. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Ví dụ tập trung vào MySQL 8.0 và InnoDB; kiểm tra giới hạn partitioning, DDL và hành vi replication trên phiên bản triển khai thực tế.

Sau bài học, bạn có thể:

- Phân biệt partitioning trong một instance với sharding qua nhiều instance.
- Chọn tenant ID hoặc khóa nghiệp vụ làm partition key/shard key.
- So sánh chia theo range, hash và directory mapping.
- Thiết kế primary key, unique key và index cho dữ liệu đa tenant.
- Dùng partition pruning và kiểm tra bằng EXPLAIN PARTITIONS.
- Nhận diện hot tenant, hot key, skew và truy vấn phải fan-out.
- Hiểu ảnh hưởng của sharding tới transaction, join và uniqueness.
- Lập kế hoạch di chuyển dữ liệu, resharding và kiểm chứng sau cutover.

## 1. Vì sao phải chia dữ liệu?

Khi bảng tăng lên hàng trăm triệu hàng hoặc workload có nhiều tenant, các vấn đề có thể xuất hiện:

- Index và dữ liệu chiếm nhiều dung lượng, thời gian backup/restore kéo dài.
- Một số truy vấn chỉ cần một tenant nhưng phải đọc phạm vi dữ liệu quá lớn.
- Một máy chủ tiến gần giới hạn CPU, memory, IOPS hoặc network.
- Một tenant lớn tạo tải ghi/đọc vượt xa các tenant khác.
- Bảo trì và xóa dữ liệu cũ trở nên tốn thời gian.
- Một workload ảnh hưởng đến latency của các workload khác.

Chia dữ liệu có thể cải thiện locality, quản lý vòng đời và phân phối tài nguyên. Tuy nhiên, nó cũng tăng độ phức tạp của schema, routing, migration, backup, monitoring và truy vấn. Không nên chia chỉ vì bảng đã lớn; trước hết phải đo bottleneck và xác định cách chia có hỗ trợ access pattern thực tế hay không.

Các câu hỏi cần trả lời trước:

1. Truy vấn phổ biến lọc theo tenant, khách hàng, tài khoản, thời gian hay một khóa khác?
2. Dữ liệu của một tenant cần được xử lý cùng nhau trong transaction không?
3. Tải giữa các tenant có cân bằng không?
4. Một tenant có thể tăng lớn đến mức cần shard riêng không?
5. Có truy vấn tổng hợp toàn hệ thống hoặc join giữa nhiều tenant không?
6. Mục tiêu là quản lý bảng, giảm scan, tăng dung lượng hay cô lập tải?
7. Đội vận hành có khả năng quản lý nhiều MySQL instance và quy trình chuyển dữ liệu không?

## 2. Partitioning là gì?

Partitioning chia một table logic thành nhiều partition vật lý do cùng một MySQL Server quản lý. Ứng dụng vẫn truy cập table bằng một tên duy nhất:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE tenant_id = 42;
~~~

MySQL xác định partition cần đọc dựa trên partitioning expression và điều kiện truy vấn. Nếu optimizer xác định được những partition không thể chứa hàng phù hợp, nó có thể loại bỏ chúng khỏi kế hoạch truy cập. Cơ chế này gọi là **partition pruning**.

Các partition vẫn thuộc cùng một instance:

- Cùng server process và tài nguyên CPU.
- Cùng bộ nhớ, buffer pool và cơ chế quản lý InnoDB.
- Cùng storage subsystem và giới hạn I/O của máy chủ.
- Cùng failure domain của instance.
- Cùng quyền quản trị và kết nối database.

Vì vậy, partitioning giúp quản lý một bảng lớn và có thể giảm lượng dữ liệu cần truy cập cho truy vấn phù hợp, nhưng không tự phân phối CPU hoặc memory sang máy chủ khác.

### 2.1. Các kiểu partitioning thường gặp

| Kiểu | Cách chia | Trường hợp phù hợp |
|---|---|---|
| RANGE | Chia theo khoảng giá trị | Dữ liệu theo thời gian, ID hoặc ngưỡng nghiệp vụ. |
| RANGE COLUMNS | Chia theo khoảng của một hoặc nhiều cột | Dữ liệu ngày giờ hoặc giá trị cột mà không cần biểu thức số học. |
| LIST | Chia theo danh sách giá trị | Một tập nhóm giá trị được xác định trước. |
| LIST COLUMNS | Chia theo danh sách giá trị của cột | Nhóm theo mã vùng, loại hoặc thuộc tính phân loại. |
| HASH | Dùng biểu thức hash để phân phối hàng | Cần phân phối tương đối đều theo một giá trị số. |
| KEY | MySQL dùng thuật toán hash nội bộ trên cột khóa | Phân phối theo cột như tenant ID, kể cả kiểu chuỗi được hỗ trợ. |

Chọn kiểu dựa trên cách truy vấn và quản lý dữ liệu. RANGE thường thuận lợi cho việc loại bỏ dữ liệu cũ theo khoảng; KEY/HASH phù hợp hơn khi cần phân phối đều theo khóa. Không có kiểu nào tự động tối ưu mọi truy vấn.

## 3. Sharding là gì?

Sharding chia dữ liệu theo chiều ngang qua nhiều database instance hoặc cụm độc lập. Mỗi shard lưu một phần hàng của cùng mô hình dữ liệu logic. Ứng dụng hoặc một lớp routing xác định shard cần truy cập.

Ví dụ hệ thống có bốn shard:

~~~text
                  Ứng dụng
                     |
                Shard Router
          ___________|___________
         |           |           |
       Shard 0     Shard 1     Shard 2     Shard 3
      tenant A    tenant B    tenant C    tenant D
~~~

Mỗi shard có thể có:

- MySQL Server riêng hoặc một cụm HA riêng.
- Buffer pool, CPU, storage và connection pool riêng.
- Schema tương tự các shard khác.
- Backup, replication, monitoring và lịch bảo trì riêng.
- Một tập tenant hoặc khóa được giao quản lý.

Sharding có thể mở rộng dung lượng và throughput bằng cách thêm máy chủ, đồng thời cô lập một phần tải. Đổi lại, ứng dụng phải định tuyến truy vấn, xử lý dữ liệu liên shard và quản lý schema đồng nhất trên nhiều shard.

Một shard không nhất thiết là một máy chủ đơn. Trong production, mỗi shard logic thường có thể là một nhóm primary/replica hoặc một cụm HA. Sharding phân chia dữ liệu giữa các nhóm; replication cung cấp bản sao và khả năng sẵn sàng bên trong từng nhóm. Hai khái niệm này không thay thế nhau.

## 4. So sánh partitioning và sharding

| Tiêu chí | Partitioning | Sharding |
|---|---|---|
| Phạm vi | Một table trong một MySQL instance | Nhiều instance/cụm |
| Quản lý kết nối | Một endpoint database thông thường | Router hoặc logic định tuyến |
| Tài nguyên CPU/memory | Dùng chung instance | Phân phối qua nhiều máy chủ |
| Partition pruning | Có thể loại bỏ partition không liên quan | Router chọn shard; mỗi shard vẫn tối ưu truy vấn nội bộ |
| Transaction | Transaction InnoDB trong cùng instance | Transaction cục bộ trong shard; liên shard phức tạp hơn |
| Join | Join table trong cùng instance theo SQL bình thường | Join liên shard cần fan-out hoặc xử lý ở tầng ứng dụng |
| Uniqueness | Bị ràng buộc bởi quy tắc unique key của partitioned table | Thường phải thiết kế ID/registry để duy trì uniqueness toàn hệ thống |
| Mở rộng dung lượng | Vẫn bị giới hạn bởi máy chủ | Có thể thêm shard để tăng tổng tài nguyên |
| Vận hành | Quản lý partition và DDL | Quản lý routing, rebalance, nhiều backup và nhiều topology |

Một table có thể được partition bên trong từng shard. Ví dụ, ứng dụng chia tenant qua tám shard; trong mỗi shard, bảng event tiếp tục partition theo tháng để quản lý retention. Cần có lý do cụ thể cho cả hai lớp vì mỗi lớp làm tăng độ phức tạp.

## 5. Chọn khóa chia dữ liệu

Khóa chia dữ liệu (partition key hoặc shard key) quyết định cách hàng được phân vùng hoặc định tuyến. Một khóa tốt thường có các đặc điểm:

- Có mặt trong phần lớn truy vấn quan trọng.
- Ổn định, ít hoặc không thay đổi sau khi tạo hàng.
- Có đủ cardinality để phân phối tải.
- Không tập trung phần lớn dữ liệu hoặc ghi vào một giá trị.
- Giúp đặt các hàng thường được truy cập cùng nhau vào cùng partition/shard.
- Phù hợp với unique key và transaction của nghiệp vụ.
- Có thể được truyền qua các tầng ứng dụng một cách nhất quán.

Không chọn khóa chỉ vì nó là primary key hiện tại. Primary key tối ưu nhận diện một hàng; shard key tối ưu định tuyến và locality. Hai vai trò có thể dùng cùng một cột nhưng không bắt buộc.

### 5.1. Tenant ID làm khóa

Với SaaS multi-tenant, tenant ID thường là lựa chọn tự nhiên vì phần lớn truy vấn nghiệp vụ đều thuộc một tenant:

~~~sql
SELECT order_id, status, total_amount
FROM sales.orders
WHERE tenant_id = 42
  AND order_id = 9001;
~~~

Nếu mọi dữ liệu của một tenant được đặt trên cùng shard, các thao tác như đọc khách hàng, đơn hàng và thanh toán của tenant có thể diễn ra trong một database cục bộ. Điều này giúp giảm truy vấn fan-out và giữ nhiều transaction trong cùng shard.

Ưu điểm:

- Định tuyến rõ ràng từ request đã xác thực.
- Dữ liệu của một tenant có thể được co-locate.
- Dễ áp dụng unique key theo tenant.
- Có thể chuyển một tenant sang shard khác mà không cần chia nhỏ toàn bộ hệ thống.

Rủi ro:

- Một tenant lớn có thể trở thành hot tenant.
- Một tenant có thể tăng trưởng vượt khả năng của shard chứa nó.
- Truy vấn quản trị toàn hệ thống phải tổng hợp nhiều shard.
- Nếu tenant ID bị thiếu trong query, ứng dụng có thể đọc nhầm hoặc quét quá rộng.

### 5.2. Khóa nghiệp vụ như customer ID hoặc account ID

Nếu workload chủ yếu truy cập theo khách hàng hoặc tài khoản, khóa đó có thể tạo locality tốt hơn tenant ID. Ví dụ, hệ thống phân tích dữ liệu khách hàng có thể định tuyến theo customer_id.

Nhưng nếu một transaction thường xuyên cập nhật nhiều customer thuộc cùng tenant, dữ liệu có thể nằm trên nhiều shard và thao tác nghiệp vụ trở nên phân tán. Hãy xem xét đơn vị giao dịch và các truy vấn join thường gặp trước khi chọn.

### 5.3. Khóa ghép

Một số hệ thống cần shard theo tenant nhưng nhận diện hàng bằng ID cục bộ trong tenant. Khi đó, khóa logic có thể là (tenant_id, order_id).

~~~sql
CREATE TABLE sales.orders (
  tenant_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  total_amount DECIMAL(19,2) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, order_id),
  KEY idx_tenant_created (tenant_id, created_at),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB;
~~~

Các truy vấn theo tenant và order ID có thể dùng cả hai thành phần khóa. Khi thiết kế repository, API và cache key, luôn mang tenant ID cùng entity ID để tránh coi order_id là duy nhất toàn hệ thống nếu nó chỉ duy nhất trong tenant.

## 6. Tenant isolation không tự có từ partitioning/sharding

Đặt dữ liệu tenant vào partition hoặc shard riêng không tự động tạo ranh giới bảo mật. Một query sai tenant vẫn có thể đọc nhầm dữ liệu nếu account có quyền và câu SQL không lọc đúng.

Các lớp bảo vệ cần có:

1. Lấy tenant ID từ identity/context đã xác thực, không tin trực tiếp giá trị do client gửi.
2. Bắt buộc tenant ID trong repository/query đối với bảng thuộc tenant.
3. Dùng composite primary key/unique key khi uniqueness chỉ có ý nghĩa trong tenant.
4. Kiểm tra tenant ownership trước thao tác đọc/ghi theo entity ID.
5. Đưa tenant ID vào cache key, message, audit log và job nền.
6. Kiểm thử truy cập chéo tenant ở API và tầng persistence.
7. Dùng database account/instance riêng nếu yêu cầu cách ly cần mạnh hơn.

Ví dụ query có phạm vi tenant:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

Nếu chỉ truy vấn WHERE order_id = ?, một ID trùng giữa hai tenant có thể trả về dữ liệu sai nếu khóa không duy nhất toàn cục. Partitioning là kỹ thuật tổ chức dữ liệu và tối ưu truy cập, không phải cơ chế row-level security.

## 7. Partition theo tenant bằng KEY

MySQL KEY partitioning phù hợp khi muốn phân phối hàng theo một hoặc nhiều cột khóa. Ví dụ mọi hàng của cùng tenant đi vào cùng partition:

~~~sql
CREATE TABLE sales.orders_partitioned (
  tenant_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  external_ref VARCHAR(80) NOT NULL,
  status VARCHAR(24) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, order_id),
  UNIQUE KEY uq_tenant_external_ref (tenant_id, external_ref),
  KEY idx_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 16;
~~~

Với PARTITION BY KEY (tenant_id), MySQL dùng hàm hash nội bộ để ánh xạ giá trị tenant ID tới một trong 16 partition. Các hàng có cùng tenant ID được đặt cùng partition trong table này.

Lưu ý:

- 16 partition vẫn nằm trong cùng MySQL instance.
- Số partition không phải số shard và không phải số CPU core.
- Tăng số partition không tự làm truy vấn nhanh hơn.
- Khi thay đổi số partition, MySQL có thể phải phân phối lại dữ liệu và thực hiện DDL tốn tài nguyên.
- Cần kiểm tra giới hạn, index và hỗ trợ partitioning của phiên bản đang dùng.

### 7.1. Quy tắc unique key của partitioned table

Trong MySQL, mọi unique key của table được partition phải bao gồm tất cả các cột được dùng trong partitioning expression. Ví dụ partition theo tenant_id thì primary key và unique key phải chứa tenant_id.

Trong ví dụ trên:

- PRIMARY KEY (tenant_id, order_id) chứa partition key.
- UNIQUE (tenant_id, external_ref) cũng chứa partition key.

Nếu thêm UNIQUE(order_id) mà không có tenant_id, MySQL sẽ từ chối thiết kế partition đó. Đây là quy tắc quan trọng ảnh hưởng tới mô hình ID và uniqueness.

Nếu nghiệp vụ cần external_ref duy nhất toàn bộ hệ thống, unique key theo tenant chỉ bảo đảm duy nhất trong từng tenant. Với nhiều shard, database cũng không thể tự bảo đảm một unique index toàn cục giữa các shard. Cần ID toàn cục hoặc một registry/constraint service phù hợp.

## 8. Partition theo thời gian bằng RANGE COLUMNS

Partition theo thời gian hữu ích cho bảng event, log hoặc dữ liệu có retention theo tháng/quý. Ví dụ:

~~~sql
CREATE TABLE analytics.events (
  tenant_id BIGINT UNSIGNED NOT NULL,
  event_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (tenant_id, created_at, event_id),
  KEY idx_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
  PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
  PARTITION p2026q1 VALUES LESS THAN ('2026-04-01'),
  PARTITION p2026q2 VALUES LESS THAN ('2026-07-01'),
  PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Các partition RANGE được xác định bằng cận trên; partition đầu tiên nhận mọi giá trị nhỏ hơn mốc đầu tiên. p_future nhận dữ liệu từ mốc trước đó trở đi.

Truy vấn nên dùng khoảng thời gian trực tiếp trên partition key:

~~~sql
SELECT event_id, event_type
FROM analytics.events
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Dạng range này giúp optimizer có cơ hội loại bỏ partition không liên quan. Tránh bọc cột partition trong hàm nếu không cần:

~~~sql
-- Thường khó tận dụng range access/pruning như điều kiện trực tiếp
WHERE DATE(created_at) = '2026-01-15'
~~~

Có thể viết lại thành khoảng thời gian bắt đầu và kết thúc để giữ điều kiện sargable.

### 8.1. Tác động đến unique key

Trong ví dụ RANGE theo created_at, mọi unique key phải chứa created_at. Primary key (tenant_id, created_at, event_id) tuân thủ quy tắc này.

Điều đó có nghĩa event_id không được bảo đảm duy nhất toàn table chỉ bởi primary key này. Nếu nghiệp vụ cần event ID duy nhất trong tenant trên mọi ngày, cần một cơ chế bổ sung như bảng registry không partition, ID được tạo toàn cục hoặc thiết kế khóa khác. Không thêm UNIQUE(tenant_id, event_id) vì nó thiếu partition column created_at và không phù hợp quy tắc partitioning.

Đây là một trade-off quan trọng: partition theo thời gian thuận lợi cho retention, nhưng có thể làm thay đổi cách biểu diễn uniqueness.

## 9. Partition pruning và kiểm tra execution plan

Partition pruning là khả năng optimizer bỏ qua partition chắc chắn không chứa hàng phù hợp. Nó phụ thuộc vào partitioning expression và predicate của query.

Ví dụ:

~~~sql
EXPLAIN PARTITIONS
SELECT event_id, event_type
FROM analytics.events
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Cột partitions trong output cho biết partition mà kế hoạch dự kiến truy cập. Nếu truy vấn lọc trực tiếp trên created_at, optimizer có thể chỉ chọn partition chứa khoảng thời gian đó.

Nếu truy vấn chỉ lọc theo event_type mà không có điều kiện trên created_at, có thể phải truy cập nhiều hoặc toàn bộ partition. Partitioning không thay thế index. Vẫn cần index phù hợp với các điều kiện lọc, join và sort của workload.

Kiểm tra:

- Truy vấn có predicate trên partition key không?
- Predicate có thể được optimizer đánh giá để pruning không?
- Có bọc partition key trong hàm hoặc ép kiểu không cần thiết không?
- Có index phù hợp bên trong các partition không?
- Số partition bị truy cập có thực sự giảm không?
- Thời gian query có tốt hơn khi so sánh trên dữ liệu đại diện không?

Dùng EXPLAIN và đo thời gian thực tế; không kết luận chỉ từ số partition được tạo.

## 10. Quản lý vòng đời partition

Một lợi ích vận hành của RANGE partitioning là có thể loại bỏ dữ liệu cũ bằng thao tác partition thay vì DELETE hàng triệu hàng. Ví dụ:

~~~sql
ALTER TABLE analytics.events
DROP PARTITION p_before_2026;
~~~

Lệnh này loại bỏ toàn bộ dữ liệu trong partition đó. Đây là thao tác phá hủy dữ liệu; cần xác nhận retention, backup và yêu cầu pháp lý trước khi thực hiện. Dù thao tác metadata có thể nhanh hơn DELETE từng hàng, DDL vẫn có thể cần metadata lock và tạo tác động lên replication hoặc workload.

Khi đã có partition MAXVALUE, để tạo range mới trước khi dữ liệu mới đi vào, có thể chia lại partition tương lai:

~~~sql
ALTER TABLE analytics.events
REORGANIZE PARTITION p_future INTO (
  PARTITION p2026q3 VALUES LESS THAN ('2026-10-01'),
  PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Lập lịch tạo partition trước thời điểm cần dùng. Nếu dữ liệu mới vượt quá partition cuối cùng và không có partition phù hợp, insert có thể thất bại.

Không xóa partition chỉ vì nó cũ theo tên. Kiểm tra chính xác cận giá trị, dữ liệu nằm trong partition và kế hoạch khôi phục trước khi chạy DDL.

## 11. Sharding theo tenant

Với tenant sharding, router ánh xạ tenant ID tới một shard. Ví dụ một shard map:

| Tenant | Shard |
|---|---|
| 1001 | mysql-shard-a |
| 1002 | mysql-shard-a |
| 2001 | mysql-shard-b |
| 3001 | mysql-shard-c |
| 4001 | mysql-shard-d |

Khi request được xác thực, ứng dụng lấy tenant ID từ security context rồi tra shard map:

~~~text
tenant_id
    |
    v
Shard directory / routing map
    |
    v
shard_id
    |
    v
DataSource hoặc connection pool của shard
    |
    v
MySQL instance
~~~

Một tenant được đặt trên một shard trong mô hình đơn giản. Truy vấn tenant đó chỉ cần một pool và một database. Khi tenant tăng lớn, có thể chuyển tenant sang shard khác hoặc chia nhỏ tenant theo sub-key nếu nghiệp vụ cho phép.

Không lấy shard ID trực tiếp từ tham số do client gửi mà không xác thực. Router phải xác định shard từ tenant đã được xác thực và mapping do hệ thống quản lý.

### 11.1. Shard directory

Có hai cách phổ biến để định tuyến:

- Tính shard từ hàm hash của shard key.
- Tra một directory/map để biết key thuộc shard nào.

Hash trực tiếp đơn giản, nhưng thay đổi số shard có thể làm nhiều key đổi vị trí. Directory linh hoạt hơn vì có thể chuyển từng tenant hoặc nhóm key mà không phải thay công thức toàn cục, đổi lại cần quản lý và cache mapping.

Nếu dùng directory, hãy xác định:

- Nguồn dữ liệu có thẩm quyền cho mapping.
- Cách cache và invalidation khi tenant được chuyển shard.
- Phiên bản mapping để tránh request dùng route cũ.
- Quy trình cập nhật mapping đồng bộ với cutover dữ liệu.
- Khả năng phục hồi khi directory không truy cập được.

## 12. Hash sharding, range sharding và directory-based sharding

| Phương pháp | Cách phân phối | Ưu điểm | Rủi ro |
|---|---|---|---|
| Range | Các khoảng key được gán cho shard | Dễ định tuyến theo khoảng, có locality theo thứ tự | Hot range, skew khi key tăng tuần tự |
| Hash | Hash(key) ánh xạ tới shard | Phân phối tương đối đều nếu key/hash phù hợp | Khó range scan, thay đổi số shard có thể di chuyển nhiều key |
| Directory | Tra key hoặc tenant trong shard map | Chuyển tenant/key linh hoạt | Directory là thành phần cần HA, cache và đồng bộ |
| Consistent hashing/virtual buckets | Key ánh xạ vào bucket ảo, bucket gán cho shard | Có thể giảm lượng dữ liệu phải di chuyển khi thêm shard | Cần quản lý bucket map và migration cẩn thận |

### 12.1. Modulo hashing

Ví dụ đơn giản:

~~~text
shard_id = hash(tenant_id) % 4
~~~

Nếu tăng từ 4 shard lên 5, kết quả modulo thay đổi cho nhiều tenant; phần lớn dữ liệu có thể cần di chuyển. Đây là lý do modulo hashing đơn giản có thể khó mở rộng khi topology thay đổi thường xuyên.

### 12.2. Virtual buckets

Có thể tạo nhiều bucket logic hơn số shard vật lý:

~~~text
tenant_id -> hash -> virtual_bucket
virtual_bucket -> shard_id
~~~

Ví dụ có 1.024 bucket logic được phân phối lên 8 shard. Khi thêm shard, hệ thống chỉ chuyển một tập bucket được chọn thay vì tính lại trực tiếp mọi tenant theo số shard mới.

Virtual bucket không tự di chuyển dữ liệu. Cần quy trình copy, đối chiếu, đổi route và xử lý ghi trong lúc di chuyển.

## 13. Hot tenant, hot key và data skew

Một phép hash tốt không thể tự cân bằng workload nếu một tenant tạo nhiều traffic hơn các tenant khác. Ví dụ 1% tenant có thể chiếm 70% số request hoặc dữ liệu. Nếu các tenant đó rơi vào cùng shard, shard đó trở thành bottleneck dù tổng dung lượng được chia khá đều.

Theo dõi theo shard và theo tenant:

- Số hàng và dung lượng table/index.
- Tốc độ đọc/ghi, QPS và bytes.
- CPU, memory, IOPS và disk latency.
- Connection count, active transaction và lock wait.
- Replica lag và binary log growth.
- Query latency p95/p99.
- Top tenant theo traffic và storage.

Các phương án xử lý hot tenant:

- Chuyển tenant lớn sang shard riêng.
- Chia tenant theo sub-key như account_id, region hoặc project_id nếu nghiệp vụ cho phép.
- Cache dữ liệu đọc nhiều và có chính sách invalidation rõ.
- Tách workload analytics khỏi database giao dịch.
- Giới hạn hoặc điều tiết workload nền của tenant.
- Tạo read replica hoặc nhóm đọc nếu mô hình consistency cho phép.

Không chia tenant thành nhiều shard nếu các giao dịch của tenant đó cần cập nhật nhiều phần dữ liệu một cách nguyên tử mà hệ thống chưa có cơ chế phối hợp phù hợp.

## 14. Thiết kế index và truy vấn cho shard key

Shard key thường nên xuất hiện ở đầu index phục vụ truy vấn theo tenant. Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON sales.orders (tenant_id, status, created_at);
~~~

Query tương ứng:

~~~sql
SELECT order_id, total_amount
FROM sales.orders
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
LIMIT 100;
~~~

Composite index được thiết kế theo leftmost prefix. Thứ tự cột phải phù hợp với predicate, sort và cardinality thực tế. Không thêm tenant_id vào mọi index theo thói quen nếu index đó không phục vụ query hoặc ràng buộc cụ thể.

Với sharding, router chọn shard trước, sau đó optimizer của MySQL chọn index bên trong shard. Hai bước cần được kiểm tra riêng:

1. Routing có chọn đúng một shard hoặc số shard tối thiểu không?
2. Query trong shard có dùng index và trả lượng dữ liệu phù hợp không?

Nếu truy vấn không có shard key, hệ thống có thể phải gửi query tới tất cả shard (scatter-gather). Kết quả sau đó được hợp nhất, sắp xếp hoặc phân trang ở tầng ứng dụng. Đây là hoạt động tốn tài nguyên và có latency phụ thuộc shard chậm nhất.

## 15. Cross-shard query, join và transaction

Sharding làm cho các thao tác liên shard phức tạp hơn.

### 15.1. Join liên shard

SQL JOIN thông thường chỉ làm việc trong phạm vi server có thể truy cập các table. Nếu hai table ở hai shard khác nhau, ứng dụng phải:

- Gửi query riêng tới từng shard rồi hợp nhất dữ liệu.
- Duy trì bản sao/denormalized data để query theo một shard.
- Dùng search/analytics service phục vụ truy vấn tổng hợp.
- Thay đổi shard key để các dữ liệu thường join cùng nhau được co-locate.

Fan-out query phải giới hạn số shard, số hàng trả về, timeout và bộ nhớ hợp nhất. Một truy vấn gửi tới 32 shard có thể tạo 32 lần tải và thời gian tổng thể bị chi phối bởi shard chậm nhất.

### 15.2. Transaction liên shard

Transaction InnoDB thông thường bảo đảm atomicity trong một MySQL instance. Nếu một nghiệp vụ cập nhật hai shard, hai transaction cục bộ không tự trở thành một transaction toàn cục.

Có thể dùng XA/two-phase commit trong những hệ thống phù hợp, nhưng nó tăng độ phức tạp, thời gian giữ trạng thái và yêu cầu vận hành. Nhiều hệ thống chọn saga, transactional outbox, event-driven workflow và thao tác bù trừ để điều phối quy trình phân tán.

Thiết kế tốt thường cố gắng giữ các cập nhật cần atomicity trong cùng shard. Nếu nghiệp vụ buộc phải xuyên shard, xác định rõ trạng thái trung gian, retry, deduplication, timeout và hành vi khi một bước thất bại.

## 16. Global ID và uniqueness

Trong một MySQL instance, AUTO_INCREMENT có thể tạo ID duy nhất trong phạm vi table. Khi chia dữ liệu qua nhiều shard, hai shard độc lập có thể cùng tạo giá trị AUTO_INCREMENT giống nhau.

Các cách thiết kế ID toàn cục:

- UUID/UUIDv7 hoặc ULID được tạo ở ứng dụng/thư viện phù hợp.
- Snowflake-style ID kết hợp timestamp, worker ID và sequence.
- ID có shard prefix hoặc vùng ID được cấp phát riêng cho mỗi shard.
- Dịch vụ cấp ID tập trung, nếu hệ thống chấp nhận dependency đó.

Mỗi cách có trade-off về kích thước index, locality, thứ tự thời gian, khả năng va chạm và độ sẵn sàng. UUID ngẫu nhiên có thể làm B-tree phân tán hơn; ID có thứ tự thời gian có thể cải thiện locality nhưng cần thiết kế generator và đồng hồ cẩn thận.

Dù ID toàn cục, vẫn nên dùng unique constraint cục bộ để bảo vệ dữ liệu trong shard. Nếu uniqueness nghiệp vụ phụ thuộc một giá trị như email trên toàn hệ thống, cần registry hoặc quy trình đảm bảo uniqueness toàn cục; unique index cục bộ không đủ.

## 17. Chuyển tenant hoặc key sang shard khác

Resharding là quá trình chuyển một phần dữ liệu từ shard hiện tại sang shard đích. Chuyển một tenant có thể thực hiện theo các giai đoạn:

1. Xác định tập dữ liệu và dependency của tenant.
2. Tạo schema/index tương ứng ở shard đích.
3. Copy snapshot ban đầu.
4. Theo dõi và áp dụng các thay đổi mới phát sinh trong lúc copy bằng CDC, binlog hoặc dual-write có kiểm soát.
5. Đối chiếu row count, checksum và invariant nghiệp vụ.
6. Chuyển routing map sang shard đích tại một điểm cutover được kiểm soát.
7. Theo dõi lỗi và latency sau cutover.
8. Chỉ xóa dữ liệu nguồn sau khi hết thời gian rollback và xác nhận backup/retention.

Nếu dual-write, cần xử lý trường hợp một lần ghi thành công ở nguồn nhưng thất bại ở đích hoặc ngược lại. Outbox/CDC và reconciliation thường dễ kiểm soát hơn việc phát hai lệnh ghi độc lập mà không có cơ chế deduplicate.

### 17.1. Tránh split ownership trong cutover

Tại một thời điểm, phải xác định rõ shard nào là nơi nhận ghi có thẩm quyền cho tenant. Nếu cả nguồn và đích cùng nhận ghi, dữ liệu có thể phân kỳ.

Có thể dùng trạng thái migration trong directory:

| Trạng thái | Định tuyến |
|---|---|
| SOURCE_ACTIVE | Đọc/ghi ở shard nguồn |
| COPYING | Nguồn nhận ghi; thay đổi được capture sang đích |
| CUTOVER | Tạm khóa/điều phối ghi, đối chiếu và chuyển route |
| TARGET_ACTIVE | Đọc/ghi ở shard đích |
| CLEANUP | Nguồn chỉ giữ dữ liệu theo thời hạn rollback/retention |

Trạng thái cụ thể phụ thuộc kiến trúc. Điều quan trọng là router, worker migration và ứng dụng cùng hiểu trạng thái và phiên bản mapping.

## 18. Partitioning và sharding có thể kết hợp

Một kiến trúc có thể dùng:

- Shard theo tenant để phân phối tải qua nhiều MySQL instance.
- Partition theo thời gian bên trong mỗi shard để quản lý event/log.
- Index theo tenant và thời gian để phục vụ truy vấn cục bộ.

Ví dụ:

~~~text
                    Tenant Router
                         |
             ____________|____________
            |            |            |
          Shard A      Shard B      Shard C
            |            |            |
        MySQL 8.0     MySQL 8.0     MySQL 8.0
            |            |            |
        events       events       events
        partitions   partitions   partitions
        by month     by month     by month
~~~

Không cần áp dụng partitioning cho mọi table. Có thể chỉ partition table event lớn, còn table khách hàng/đơn hàng giữ cấu trúc thông thường để hỗ trợ foreign key và transaction trong shard.

Đặc biệt, MySQL 8.0 InnoDB có giới hạn quan trọng: table do người dùng partition không hỗ trợ foreign key và không thể được table khác tham chiếu bằng foreign key. Nếu mô hình dựa nhiều vào foreign key, cần đánh giá kỹ trước khi partition table đó. Xác nhận giới hạn theo phiên bản MySQL đang triển khai.

## 19. Vận hành, backup và schema migration

Khi có nhiều shard, các công việc vận hành cần được thực hiện có điều phối:

- Theo dõi cùng một bộ metric và alert trên tất cả shard.
- Đảm bảo backup và restore test riêng cho từng shard.
- Quản lý schema version đồng nhất nhưng cho phép rollout theo đợt.
- Theo dõi shard map, replica topology và trạng thái chuyển tenant.
- Kiểm tra dung lượng tăng trưởng và ngưỡng mất cân bằng.
- Lập kế hoạch nâng cấp MySQL/Connector/J theo từng nhóm shard.
- Xác nhận job nền và cron không chạy trùng trên mọi shard nếu không cần.
- Giữ log có shard ID, tenant ID đã được bảo vệ và request ID.

Schema migration cần tương thích trong giai đoạn rolling deployment. Một shard được nâng cấp trước có thể có schema mới trong khi shard khác vẫn ở schema cũ. Code ứng dụng phải hỗ trợ cả hai trạng thái trong cửa sổ rollout, hoặc traffic phải được điều phối theo phiên bản schema.

Không chạy DDL lớn đồng thời trên mọi shard mà chưa đánh giá tải và metadata lock. Thực hiện theo batch shard, quan sát kết quả và có kế hoạch dừng nếu latency hoặc replication lag tăng.

## 20. Quy trình chọn chiến lược chia dữ liệu

Dùng quy trình sau trước khi quyết định:

### Bước 1: Đo workload

Thu thập query digest, top query, QPS, read/write ratio, table/index size, tenant distribution, p95/p99 latency, CPU, IOPS và replica lag.

### Bước 2: Nhóm truy vấn theo khóa

Xác định phần trăm request có tenant ID, customer ID, account ID, time range hoặc truy vấn toàn hệ thống. Tìm khóa xuất hiện trong phần lớn truy vấn quan trọng.

### Bước 3: Xác định đơn vị giao dịch

Liệt kê các table thường được cập nhật cùng nhau. Chọn shard key giúp các thao tác cần atomicity nằm trong cùng shard nếu có thể.

### Bước 4: Đánh giá skew và hot key

Đo số hàng, dung lượng và traffic theo tenant/key. Mô phỏng tenant lớn nhất, không chỉ lấy giá trị trung bình.

### Bước 5: Thử partitioning trước khi sharding nếu mục tiêu là quản lý table

Nếu bottleneck là retention hoặc scan trên table lớn, thử RANGE/KEY partitioning trên staging và kiểm tra partition pruning. Nếu bottleneck là CPU/IO của toàn instance hoặc cần mở rộng độc lập, xem xét sharding.

### Bước 6: Đánh giá chi phí liên shard

Mô phỏng join, transaction, unique constraint, báo cáo tổng hợp, backup, migration và resharding. Nếu nhiều nghiệp vụ quan trọng phải fan-out hoặc transaction liên shard, xem lại shard key.

### Bước 7: Thử nghiệm và đặt ngưỡng

Benchmark trên dữ liệu có phân bố giống production. Đặt ngưỡng chuyển tenant, thêm shard, giảm tốc độ migration và rollback.

## 21. Bài tập thực hành

### Bài 1: Chọn shard key cho SaaS

Một hệ thống có 10.000 tenant. Hầu hết request đều truy vấn đơn hàng, khách hàng và hóa đơn của một tenant. Một số tenant lớn gấp hàng trăm lần trung bình. Đề xuất shard key, cách nhận diện hot tenant và kế hoạch chuyển tenant lớn sang shard riêng.

### Bài 2: Partition theo tenant

Tạo table thử nghiệm với PARTITION BY KEY(tenant_id) PARTITIONS 8. Chèn dữ liệu nhiều tenant, chạy query có và không có tenant predicate. Dùng EXPLAIN PARTITIONS quan sát partition được truy cập.

### Bài 3: Partition theo thời gian

Tạo table event partition theo RANGE COLUMNS(created_at). Viết query theo khoảng thời gian, so sánh với query bọc DATE(created_at). Thử tạo partition mới bằng REORGANIZE và kiểm tra dữ liệu.

### Bài 4: Unique key và partition key

Thử tạo partitioned table có UNIQUE(order_id) khi partition theo tenant_id. Quan sát lỗi, sau đó thiết kế UNIQUE(tenant_id, order_id). Giải thích sự khác nhau giữa uniqueness trong tenant và uniqueness toàn hệ thống.

### Bài 5: Mô phỏng shard routing

Tạo bốn database thử nghiệm hoặc bốn schema/endpoint tách biệt. Viết router ánh xạ tenant ID tới shard. Kiểm tra truy vấn tenant chỉ đi tới đúng shard và request không thể tự chỉ định tenant khác để đọc dữ liệu.

### Bài 6: Reshard một tenant

Copy dữ liệu của một tenant từ shard A sang shard B trong môi trường thử nghiệm. Mô phỏng ghi mới trong lúc copy, áp dụng change log, đối chiếu dữ liệu rồi chuyển routing map. Kiểm tra không mất hoặc nhân đôi dữ liệu.

## 22. Checklist trước khi đưa partitioning/sharding vào production

- [ ] Đã đo workload và xác định bottleneck thực tế.
- [ ] Đã chọn partition key/shard key dựa trên query và transaction pattern.
- [ ] Đã đánh giá cardinality, phân bố tải, hot tenant và data skew.
- [ ] Đã phân biệt partitioning trong một instance với sharding qua nhiều instance.
- [ ] Đã kiểm tra quy tắc unique key của partitioned table.
- [ ] Đã xem xét giới hạn foreign key của InnoDB partitioned table.
- [ ] Đã dùng EXPLAIN PARTITIONS để xác nhận partition pruning.
- [ ] Đã thiết kế composite index theo access pattern.
- [ ] Tenant ID được lấy từ context xác thực và có mặt trong query cần thiết.
- [ ] Shard router có mapping, cache invalidation và versioning rõ ràng.
- [ ] Đã xác định chiến lược global ID và uniqueness.
- [ ] Đã giới hạn fan-out query và có cách hợp nhất kết quả.
- [ ] Đã thiết kế cách xử lý transaction liên shard.
- [ ] Có metric theo shard và tenant để phát hiện hot spot.
- [ ] Có quy trình backfill, CDC/dual-write, reconciliation và cutover.
- [ ] Đã thử backup/restore và schema migration trên từng shard.
- [ ] Có kế hoạch rollback và thời gian giữ dữ liệu nguồn sau resharding.
- [ ] Đã kiểm thử isolation giữa tenant và định tuyến đúng shard.

Partitioning giúp chia một table lớn thành các phần do cùng MySQL instance quản lý; sharding phân phối dữ liệu qua nhiều instance để mở rộng tài nguyên và cô lập tải. Tenant ID thường là shard key phù hợp khi nghiệp vụ truy cập theo tenant và cần giữ dữ liệu cùng nhau, nhưng phải tính đến tenant lớn, truy vấn toàn cục và giao dịch liên shard. Hãy chọn khóa từ access pattern, kiểm tra partition pruning hoặc routing bằng dữ liệu thực, rồi triển khai chuyển dữ liệu có checkpoint, đối chiếu và cutover rõ ràng.

