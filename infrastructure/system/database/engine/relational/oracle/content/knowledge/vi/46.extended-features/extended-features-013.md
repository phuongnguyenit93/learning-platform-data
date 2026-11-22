# Đánh giá tính năng mở rộng bằng bài toán, dữ liệu và điều kiện triển khai thực tế

Oracle Database cung cấp nhiều tính năng mở rộng để xử lý dữ liệu lớn, tăng khả năng sẵn sàng, cải thiện hiệu năng, hỗ trợ phân tích, tích hợp hệ thống và bảo vệ dữ liệu. Tuy nhiên, một tính năng mạnh về mặt kỹ thuật không mặc nhiên phù hợp với mọi hệ thống. Partitioning có thể giúp quản lý bảng lịch sử hàng tỷ dòng nhưng không làm mọi truy vấn nhanh hơn. RAC có thể tăng khả năng phục vụ khi một node lỗi và hỗ trợ mở rộng workload, nhưng đòi hỏi kiến trúc cluster, storage, interconnect và vận hành phức tạp hơn. Compression giảm dung lượng nhưng có thể tăng CPU. Parallel execution rút ngắn một số truy vấn lớn nhưng cũng có thể chiếm tài nguyên của workload giao dịch.

Vì vậy, đánh giá tính năng mở rộng cần bắt đầu từ bài toán nghiệp vụ, đo dữ liệu và workload thực tế, sau đó kiểm tra điều kiện triển khai. Câu hỏi cần trả lời không chỉ là “tính năng này làm được gì?” mà còn là:

- Vấn đề hiện tại cụ thể là gì và ảnh hưởng đến người dùng hoặc vận hành ra sao?
- Tập dữ liệu, tốc độ tăng trưởng và mẫu truy cập có phù hợp với cơ chế của tính năng không?
- Lợi ích có đo được trên workload đại diện không?
- Tính năng yêu cầu edition, option, license, hạ tầng hoặc phiên bản nào?
- Đội ngũ có thể triển khai, giám sát, khôi phục và xử lý sự cố không?
- Có thể triển khai từng bước, quay lui hoặc giảm tác động khi kết quả không đạt không?

Bài học này trình bày một phương pháp đánh giá có thể áp dụng cho các tính năng Oracle như Partitioning, Real Application Clusters (RAC), Data Guard, In-Memory, compression, parallel execution, Advanced Queuing (AQ), Flashback và các khả năng bảo mật. Mục tiêu là lựa chọn dựa trên bằng chứng và điều kiện của hệ thống, thay vì triển khai chỉ vì tính năng có sẵn.

## 1. Bắt đầu từ bài toán cần giải quyết

Một yêu cầu như “database đang chậm” chưa đủ để chọn tính năng. Cùng một biểu hiện có thể xuất phát từ nhiều nguyên nhân:

- SQL thiếu index hoặc có execution plan không phù hợp.
- Truy vấn đọc quá nhiều dữ liệu vì thiếu predicate hoặc partition pruning.
- I/O storage không đáp ứng workload.
- CPU bão hòa do xử lý, parse, conversion hoặc concurrency.
- Lock contention hoặc transaction giữ khóa quá lâu.
- Connection pool cấu hình chưa hợp lý.
- Batch chạy cùng giờ với OLTP.
- Dữ liệu tăng trưởng khiến tác vụ bảo trì không còn hoàn thành trong cửa sổ cho phép.
- Hệ thống cần RTO/RPO thấp hơn nhưng kiến trúc hiện tại chưa đáp ứng.

Nếu chưa xác định nguyên nhân, việc bật một tính năng mới có thể làm tăng độ phức tạp mà không giải quyết được bottleneck.

### 1.1. Viết vấn đề thành một phát biểu có thể đo

Một phát biểu tốt nêu rõ workload, điều kiện, chỉ số hiện tại và mục tiêu. Ví dụ:

| Phát biểu chưa đủ rõ | Phát biểu có thể đánh giá |
|---|---|
| Báo cáo chạy chậm | Báo cáo doanh thu tháng trên 24 tháng dữ liệu mất p95 95 giây; yêu cầu dưới 20 giây trong giờ cao điểm |
| Bảng quá lớn | Bảng ORDERS có 1,8 tỷ dòng, tăng 20 triệu dòng/tháng; purge dữ liệu quá hạn mất 7 giờ và ảnh hưởng OLTP |
| Cần HA tốt hơn | Dịch vụ chấp nhận tối đa 5 phút gián đoạn và RPO không quá 30 giây; kiến trúc hiện tại cần 45 phút để phục hồi |
| Cần mở rộng | CPU primary đạt trên 85% trong 3 giờ cao điểm mỗi ngày; throughput không tăng khi tăng thêm application instance |
| Backup quá lâu | Full backup vượt cửa sổ 6 giờ và làm tăng I/O latency của giao dịch |

Mỗi phát biểu nên có một chủ sở hữu nghiệp vụ và một chủ sở hữu kỹ thuật. Chủ sở hữu nghiệp vụ xác nhận tác động và mức ưu tiên; DBA/architect xác định cách đo, nguyên nhân và ràng buộc kỹ thuật.

### 1.2. Xác định mục tiêu và ngưỡng chấp nhận

Đừng chỉ ghi “nhanh hơn” hoặc “sẵn sàng hơn”. Hãy đặt ngưỡng:

- Response time: p50, p95, p99 và thời gian tối đa.
- Throughput: giao dịch/giây, dòng/giây hoặc job/giờ.
- Availability: thời gian gián đoạn tối đa theo tháng/năm.
- RTO: thời gian tối đa để dịch vụ trở lại.
- RPO: lượng dữ liệu tối đa có thể mất tính theo thời gian.
- Storage: dung lượng dữ liệu, index, backup và archive.
- Batch window: thời gian cho phép hoàn tất xử lý.
- Recovery: thời gian restore, recover, failover và validate.
- Cost: license, hạ tầng, vận hành, lưu trữ và nhân lực.

Mục tiêu phải có thể kiểm tra bằng số liệu. Nếu không có baseline hoặc ngưỡng đạt, POC dễ kết thúc bằng nhận xét chủ quan.

## 2. Thu thập dữ liệu và workload đại diện

Tính năng mở rộng thường có lợi ích phụ thuộc rất mạnh vào hình dạng dữ liệu. Cần hiểu cả kích thước hiện tại, tốc độ tăng trưởng, phân bố giá trị và cách ứng dụng truy cập.

### 2.1. Hồ sơ dữ liệu

Thu thập tối thiểu:

| Thuộc tính | Cần biết | Tác động đến lựa chọn |
|---|---|---|
| Số dòng | Tổng dòng và dòng theo thời gian | Partitioning, index, batch |
| Dung lượng | Table, index, LOB, backup | Compression, storage, archive |
| Tăng trưởng | Dòng/ngày, GB/tháng, mùa vụ | Capacity planning, retention |
| Phân bố | Skew, hot key, NULL, cardinality | Partition key, index, parallelism |
| Tuổi dữ liệu | Hot, warm, cold, retention | Partition lifecycle, compression, archive |
| Kích thước row | Số cột, LOB, payload | I/O, cache, compression |
| Quan hệ | Foreign key, join, cascade | Partition design, query design |
| Tính toàn vẹn | Unique, check, referential rules | Partitioning và index constraints |
| Độ nhạy | PII, tài chính, bí mật | Encryption, access control, audit |

Không dùng chỉ một con số tổng dung lượng để ra quyết định. Hai bảng cùng 2 TB có thể có hành vi hoàn toàn khác nếu một bảng chủ yếu append theo ngày, còn bảng kia bị cập nhật ngẫu nhiên liên tục.

### 2.2. Hồ sơ workload

Phân loại các workload đang chạy:

- OLTP: giao dịch ngắn, nhiều session, cần latency thấp.
- Reporting/BI: truy vấn đọc nhiều dòng, join và aggregate.
- Batch/ETL: tải hoặc biến đổi khối lượng lớn theo lịch.
- Maintenance: index rebuild, statistics, purge, backup, partition maintenance.
- Integration: message, CDC, API hoặc đồng bộ giữa hệ thống.
- Recovery: backup, restore, failover và kiểm tra tính sẵn sàng.

Với từng workload, ghi nhận:

- Số lần chạy và thời điểm chạy.
- SQL hoặc nhóm SQL chiếm nhiều DB time.
- Số dòng đọc/ghi và số block truy cập.
- CPU, physical read/write, redo, undo và TEMP.
- Concurrency và số session đồng thời.
- Thời gian giữ transaction/lock.
- Kích thước bind và mức độ thay đổi tham số.
- Tỷ lệ thành công, timeout, retry và lỗi.

Cần đo trong thời gian đủ dài để bao gồm giờ cao điểm, batch, cuối tháng/cuối quý và các đợt tăng tải. Một giờ yên tĩnh không đại diện cho hệ thống production.

### 2.3. Lấy số liệu từ Oracle

Một số truy vấn dictionary giúp lập hồ sơ kích thước object:

~~~sql
SELECT owner,
       segment_name,
       segment_type,
       tablespace_name,
       bytes / 1024 / 1024 AS size_mb
FROM dba_segments
WHERE owner = 'APP'
ORDER BY bytes DESC;
~~~

Xem thống kê table:

~~~sql
SELECT owner,
       table_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed
FROM dba_tables
WHERE owner = 'APP'
ORDER BY num_rows DESC;
~~~

NUM_ROWS và các thống kê liên quan là giá trị ước lượng tại lần gather statistics gần nhất, không phải số dòng tức thời. Nếu thống kê stale hoặc chưa được thu thập, cần xác nhận trước khi dùng để so sánh.

Kiểm tra cột và kiểu dữ liệu:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM dba_tab_columns
WHERE owner = 'APP'
ORDER BY table_name, column_id;
~~~

Trong môi trường không có quyền DBA, có thể dùng USER_* hoặc ALL_* view theo phạm vi truy cập.

### 2.4. Dùng số liệu hiệu năng đúng phạm vi và quyền

AWR, ASH, SQL Monitor và một số báo cáo hiệu năng thuộc các gói quản lý/giấy phép riêng tùy phiên bản, sản phẩm và hợp đồng Oracle. Trước khi sử dụng, xác nhận quyền sử dụng và entitlement hiện có. Nếu chưa có quyền, dùng các nguồn được phép như V$ views, execution plan, SQL trace/TKPROF, application metrics và monitoring đã được phê duyệt.

Không bật hoặc trích xuất dữ liệu từ một pack chỉ vì lệnh có thể chạy được. Khả năng kỹ thuật và quyền sử dụng thương mại là hai điều kiện khác nhau.

## 3. Xây dựng baseline trước khi thử tính năng

Baseline là số đo của hệ thống hiện tại trong cùng điều kiện sẽ dùng để so sánh với phương án mới. Không có baseline, không thể kết luận tính năng cải thiện bao nhiêu hoặc tạo ra tác động phụ nào.

### 3.1. Bộ chỉ số cơ bản

| Nhóm | Chỉ số |
|---|---|
| Response time | p50, p95, p99, max |
| Throughput | transaction/s, request/s, rows/s |
| CPU | DB host CPU, process CPU, CPU time/query |
| I/O | read/write latency, IOPS, MB/s, physical reads |
| Memory | SGA/PGA, buffer/cache pressure, JVM heap nếu liên quan |
| Concurrency | active sessions, waits, lock time |
| Transaction | redo generation, undo, commit rate, transaction duration |
| SQL | execution count, plan, logical reads, rows processed |
| Storage | table/index size, TEMP, archive, backup size |
| Availability | downtime, failover duration, replication lag |
| Operations | thời gian backup, maintenance, deployment và recovery |

Không chỉ lấy giá trị trung bình. p95/p99 thường phản ánh trải nghiệm của người dùng tốt hơn vì average có thể che giấu những request chậm.

### 3.2. Baseline cần có điều kiện tái lập

Ghi lại:

- Database version, edition, patch level và initialization parameters.
- Server CPU/RAM, storage, network và virtualization/cloud configuration.
- Schema version, object statistics và index.
- Dataset size, phân bố dữ liệu và trạng thái cache.
- Application version, connection pool, concurrency và request mix.
- Thời điểm chạy, job nền và các workload cạnh tranh.
- Công cụ, script và cách thu thập metric.

Khi so sánh hai phương án, giữ các điều kiện này càng giống nhau càng tốt. Nếu thay đổi đồng thời storage, SQL, index và tính năng mới, sẽ khó xác định yếu tố nào tạo ra kết quả.

### 3.3. Baseline theo từng use case

Một tính năng có thể cải thiện workload A nhưng làm workload B xấu đi. Ví dụ parallel query giúp báo cáo chạy nhanh hơn nhưng chiếm CPU khiến OLTP có p99 cao hơn. Do đó phải đo cả workload mục tiêu và workload bị ảnh hưởng.

## 4. Phương pháp đánh giá một tính năng Oracle

Có thể dùng quy trình tám bước:

1. **Mô tả bài toán**: xác định triệu chứng, nguyên nhân giả định, người dùng bị ảnh hưởng và mục tiêu.
2. **Lập hồ sơ dữ liệu/workload**: kích thước, phân bố, tăng trưởng, SQL, concurrency và lịch chạy.
3. **Kiểm tra tính phù hợp**: cơ chế của tính năng có giải quyết đúng bottleneck không?
4. **Kiểm tra điều kiện triển khai**: phiên bản, edition, license, hạ tầng, bảo mật và dependency.
5. **Thiết kế POC**: chọn dataset đại diện, workload, kịch bản lỗi và metric.
6. **Đánh giá chi phí toàn phần**: license, hạ tầng, vận hành, backup, đào tạo và rủi ro.
7. **Lập kế hoạch triển khai**: rollout, compatibility, monitoring, rollback hoặc forward recovery.
8. **Quyết định dựa trên ngưỡng**: triển khai, thử nghiệm thêm, chọn phương án khác hoặc không làm.

### 4.1. Ma trận câu hỏi

| Nhóm đánh giá | Câu hỏi |
|---|---|
| Bài toán | Vấn đề nào được giải quyết? Có số liệu xác nhận không? |
| Dữ liệu | Quy mô, phân bố và tăng trưởng có phù hợp không? |
| Workload | Tính năng có cải thiện workload mục tiêu và giữ workload khác trong ngưỡng không? |
| Kiến trúc | Có cần thay đổi application, storage, network hoặc topology không? |
| Tương thích | Version, edition, driver, ORM và công cụ có hỗ trợ không? |
| License | Option/pack có cần entitlement riêng không? |
| Bảo mật | Dữ liệu, quyền và audit có được bảo vệ không? |
| Vận hành | Có monitor, alert, backup, recovery và người chịu trách nhiệm không? |
| Khả năng quay lui | Có thể rollback hay cần forward fix? Dữ liệu đã biến đổi có khôi phục được không? |
| Giá trị | Lợi ích có lớn hơn tổng chi phí và rủi ro không? |

## 5. Đánh giá Partitioning

Partitioning chia một table hoặc index lớn thành các phần nhỏ hơn được quản lý theo partition key. Ứng dụng vẫn truy cập table logic, còn Oracle có thể loại bỏ các partition không cần đọc khi predicate phù hợp (partition pruning).

Partitioning thường hữu ích khi:

- Bảng rất lớn và dữ liệu có chiều thời gian hoặc khóa phân vùng tự nhiên.
- Truy vấn thường lọc theo partition key.
- Cần purge hoặc archive dữ liệu cũ theo kỳ.
- Cần quản lý index và maintenance theo phần dữ liệu.
- ETL hoặc batch có thể xử lý theo partition.

Partitioning không tự động làm mọi query nhanh hơn. Nếu query không có predicate phù hợp, Oracle có thể phải đọc nhiều hoặc tất cả partition. Nếu chọn partition key không phù hợp, workload có thể vẫn bị phân tán hoặc skew.

### 5.1. Kiểm tra dữ liệu và predicate

Giả sử bảng ORDERS có 1,8 tỷ dòng, lưu 5 năm và hầu hết báo cáo lọc ORDER_DATE theo tháng. Range partition theo tháng có thể phù hợp.

Ví dụ DDL khái niệm:

~~~sql
CREATE TABLE orders (
    order_id    NUMBER NOT NULL,
    order_date  DATE NOT NULL,
    customer_id NUMBER NOT NULL,
    status      VARCHAR2(20),
    amount      NUMBER(14,2)
)
PARTITION BY RANGE (order_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

Đây chỉ là ví dụ minh họa cấu trúc. Thiết kế thật cần quy tắc tạo partition tương lai, interval partition nếu phù hợp, index, constraint, retention và quy trình load dữ liệu.

Kiểm tra query có pruning bằng execution plan. Tìm các dấu hiệu partition start/stop hoặc thông tin PSTART/PSTOP tùy plan format. So sánh số partition được truy cập trước và sau.

### 5.2. Đánh giá partition key

Một partition key tốt thường:

- Xuất hiện thường xuyên trong điều kiện lọc.
- Phản ánh cách dữ liệu được quản lý hoặc hết hạn.
- Có phân bố đủ hợp lý, tránh dồn toàn bộ ghi vào một partition.
- Không làm phức tạp các constraint/unique key quan trọng.
- Có kiểu dữ liệu và semantics ổn định.

Không chọn key chỉ vì cột đó có nhiều giá trị distinct. Cần xem query predicate và thao tác lifecycle. Partition theo ngày có thể tốt cho purge, nhưng nếu ứng dụng chủ yếu tìm theo CUSTOMER_ID và không có điều kiện ngày, query có thể vẫn phải truy cập nhiều partition.

### 5.3. Những điều phải đo trong POC

- Logical reads và physical reads của query mục tiêu.
- Thời gian query có và không có pruning.
- Thời gian purge/archive bằng partition drop/truncate/exchange so với DELETE.
- Chi phí tạo/rebuild index và gather statistics.
- Kích thước local/global index.
- Tác động đến insert, update và foreign key.
- Thời gian load dữ liệu vào partition mới.
- Hành vi khi dữ liệu đến muộn hoặc ngày dữ liệu sai.

Cần kiểm tra unique/primary key vì partition key có thể ảnh hưởng khả năng khai báo unique local index. Một số thiết kế buộc dùng global index hoặc thay đổi key; global index có chi phí maintenance khi drop/truncate partition tùy thao tác và phiên bản.

### 5.4. Điều kiện không nên dùng

- Bảng nhỏ, không có vấn đề maintenance hoặc hiệu năng.
- Query không lọc theo partition key và không có lợi ích lifecycle rõ ràng.
- Dữ liệu phân bố lệch khiến một số partition quá nóng.
- Đội ngũ chưa có quy trình tạo partition tương lai, kiểm tra partition thiếu và quản lý index.
- License/edition hiện tại không cho phép sử dụng theo hợp đồng.

## 6. Đánh giá Oracle RAC

Oracle Real Application Clusters cho phép nhiều instance trên các node cùng truy cập một database dùng chung storage. RAC thường được đánh giá khi cần HA ở mức instance/node và/hoặc mở rộng khả năng xử lý workload trên nhiều node.

RAC không đơn giản là “thêm server để query chạy nhanh gấp đôi”. Cache Fusion và interconnect phối hợp block giữa các instance; workload có truy cập cùng block hoặc cùng hot data có thể tạo giao tiếp liên node và contention.

### 6.1. Bài toán phù hợp

- Yêu cầu tiếp tục cung cấp dịch vụ khi một node/instance gặp sự cố.
- Workload có thể phân phối session/service trên nhiều instance.
- Có nhu cầu bảo trì node theo rolling operation trong kiến trúc hỗ trợ.
- Hạ tầng shared storage, interconnect và cluster được thiết kế phù hợp.

### 6.2. Dữ liệu và workload cần đo

- Số session và service theo instance.
- CPU, active sessions và response time mỗi instance.
- Cache Fusion/global cache waits.
- Hot blocks, sequence contention và block pinging.
- Interconnect latency/throughput.
- I/O latency và shared storage capacity.
- Hành vi connection pool, FAN và service failover.
- Tải còn lại khi mất một node.

Một hệ thống có nhiều session nhưng tất cả cùng cập nhật một số block nóng có thể không scale tuyến tính. Cần đo workload thật với data skew và transaction contention.

### 6.3. POC RAC

POC cần thử:

1. Kết nối qua SCAN/service name.
2. Phân phối connection trên các instance.
3. Chạy workload đồng thời và quan sát load balance.
4. Dừng/relocate service theo kịch bản đã duyệt.
5. Mô phỏng instance/node failure trong môi trường kiểm thử.
6. Đo thời gian phát hiện, service restart, reconnect và lỗi request.
7. Đo throughput khi một node không khả dụng.
8. Kiểm tra backup, monitoring, patching và vận hành cluster.

RAC không thay thế backup hoặc Data Guard. Nó giải quyết một lớp sự cố khác. Cần phân biệt lỗi instance/node với lỗi storage, lỗi database logic, thao tác xóa nhầm dữ liệu hoặc lỗi site.

### 6.4. Điều kiện triển khai

RAC yêu cầu Grid Infrastructure/Clusterware, shared storage phù hợp, interconnect ổn định, DNS/SCAN, listener, service placement, fencing và quy trình vận hành cluster. Cần kiểm tra tương thích OS, storage, network, driver, monitoring và license/edition.

Nếu hệ thống chỉ cần khôi phục sau sự cố site hoặc cần bản sao dữ liệu ở site khác, Data Guard có thể phù hợp hơn. Nếu workload không scale do SQL hoặc lock contention, RAC có thể tăng độ phức tạp mà không xử lý nguyên nhân.

## 7. Đánh giá Data Guard

Oracle Data Guard duy trì một hoặc nhiều standby database từ primary thông qua truyền và áp dụng redo. Nó thường được chọn để bảo vệ trước sự cố database/server/site và hỗ trợ switchover/failover.

### 7.1. Bài toán cần làm rõ

- Cần bảo vệ khỏi lỗi node, database hay toàn bộ site?
- RPO tối đa bao nhiêu?
- RTO tối đa bao nhiêu?
- Có cần standby chỉ để DR hay còn dùng cho reporting/backup?
- Ai có quyền quyết định failover?
- Cần tự động failover hay quy trình có người phê duyệt?
- Network giữa primary và standby có đủ băng thông/độ ổn định không?

### 7.2. Chọn protection mode dựa trên RPO và latency

Data Guard có các protection mode với trade-off khác nhau về bảo vệ dữ liệu và độ trễ:

- Maximum Protection: ưu tiên bảo đảm không mất dữ liệu theo semantics của mode; availability có thể bị ảnh hưởng nếu không còn standby đồng bộ theo yêu cầu.
- Maximum Availability: ưu tiên zero data loss khi điều kiện cho phép nhưng có hành vi bảo vệ availability khi standby không sẵn sàng theo thiết kế.
- Maximum Performance: ưu tiên hiệu năng primary, thường cho phép asynchronous transport và có thể có data loss trong tình huống failover tùy redo chưa chuyển.

Không chọn mode chỉ từ tên. Cần xem transport mode SYNC/ASYNC, network RTT, redo rate, standby apply lag và yêu cầu RPO thực tế. Kiểm thử khi link bị chậm hoặc mất kết nối.

### 7.3. Chỉ số cần đo

- Transport lag.
- Apply lag.
- Redo generation rate.
- Network throughput và latency.
- Time to detect failure.
- Time to failover và reopen service.
- Thời gian xác minh dữ liệu sau failover.
- Thời gian reinstate hoặc dựng lại standby.
- Tác động workload khi chạy redo apply.

Data Guard không tự bảo đảm ứng dụng reconnect. Cần service role-based, connect string, DNS/SCAN, broker, client retry và kiểm thử transaction outcome.

### 7.4. POC và điều kiện vận hành

POC cần bao gồm switchover có kế hoạch, failover có kiểm soát, mất network, standby apply chậm, khôi phục standby và quay lại topology mong muốn. Cần có runbook, quyền vận hành, alert lag và người chịu trách nhiệm.

Active Data Guard và các khả năng mở rộng liên quan có thể có yêu cầu license riêng tùy hợp đồng/phiên bản. Không giả định mọi standby read-only hoặc workload trên standby đều được quyền sử dụng; xác minh entitlement trước khi thiết kế.

## 8. Đánh giá In-Memory và tối ưu workload phân tích

Oracle Database In-Memory sử dụng In-Memory Column Store để lưu dữ liệu theo định dạng columnar trong memory, hỗ trợ truy vấn phân tích quét và aggregate. Nó có thể tăng tốc reporting/analytic workload khi truy vấn đọc nhiều cột trên lượng lớn dòng.

Tuy nhiên, không phải query nào cũng được lợi. OLTP truy cập một vài row bằng index có thể không cần column store. In-memory cần đủ RAM, kế hoạch population, compression level và quản lý ưu tiên object.

### 8.1. Bài toán phù hợp

- Truy vấn scan/aggregate lớn đang bị giới hạn bởi I/O hoặc row-oriented processing.
- Nhiều báo cáo đọc một số cột trên tập dữ liệu rộng.
- Cần tăng tốc phân tích gần thời gian thực mà không muốn ETL sang hệ thống khác.
- Có đủ memory headroom sau khi dành SGA/PGA và workload hiện tại.

### 8.2. Dữ liệu và workload cần đo

- Tỷ lệ dữ liệu hot được truy vấn thường xuyên.
- Số cột thực sự được dùng trong báo cáo.
- Kích thước object sau compression.
- Memory cần cho population và workload khác.
- Thời gian population sau startup/reload.
- CPU và I/O trước/sau.
- Tác động đến OLTP và buffer cache.
- Hành vi khi memory pressure hoặc object bị evict.

### 8.3. POC

Chọn một nhóm table/partition và query đại diện. So sánh execution plan, elapsed time, CPU, physical reads, memory consumption và concurrency. Thử cả lúc column store đã population và ngay sau startup/repopulation. Nếu chỉ benchmark sau khi cache đã nóng, kết quả có thể không phản ánh recovery/startup thực tế.

In-Memory có thể là tính năng có license/option riêng. Cần xác minh edition, option, giới hạn và điều khoản hiện hành trước khi triển khai.

## 9. Đánh giá compression

Compression có thể giảm dung lượng table, index, backup hoặc dữ liệu lưu trữ, từ đó giảm I/O và chi phí storage. Đổi lại, một số kiểu compression tiêu thụ CPU khi nén/giải nén và có thể có ràng buộc về workload, DML hoặc license.

Cần phân biệt mục tiêu:

- Giảm dung lượng segment trong database.
- Giảm kích thước backup.
- Giảm dữ liệu truyền qua network.
- Lưu trữ lịch sử ít được truy cập.
- Tăng hiệu năng scan nhờ giảm lượng block đọc.

Một dạng compression không giải quyết tất cả mục tiêu.

### 9.1. Dữ liệu phù hợp

Compression thường có hiệu quả cao hơn khi dữ liệu có tính lặp lại, nhiều giá trị giống nhau hoặc dữ liệu lịch sử ít cập nhật. Dữ liệu đã mã hóa, ngẫu nhiên hoặc chứa payload entropy cao có thể nén ít.

Đánh giá theo table/partition, không chỉ theo database tổng thể. Một bảng giao dịch nóng và bảng lịch sử lạnh có thể cần chính sách khác nhau.

### 9.2. Đo compression

- Segment size trước/sau.
- Tỷ lệ nén thực tế.
- CPU tăng thêm khi insert/update/query.
- Throughput DML.
- Query latency và physical reads.
- Redo/undo và backup size.
- Chi phí rebuild/move/recompress.
- Tác động đến replication và standby.

Không dùng tỷ lệ nén từ một tập mẫu nhỏ làm dự báo cho toàn bộ database. Chọn mẫu có phân bố dữ liệu tương tự từng nhóm table/partition.

### 9.3. Điều kiện và license

Một số tính năng compression nâng cao hoặc cách sử dụng cụ thể có thể thuộc option/license riêng. Cần đối chiếu Oracle licensing documentation và hợp đồng thực tế. Nếu chỉ cần giảm backup, có thể đánh giá backup compression trong RMAN; nếu cần giảm segment size, đánh giá table/index compression theo workload. Hai mục tiêu có thể có license và tác động khác nhau.

## 10. Đánh giá Parallel Execution

Parallel execution chia công việc của một SQL hoặc operation lớn thành nhiều process để xử lý đồng thời. Nó có thể giúp query scan, join, sort, aggregation hoặc maintenance hoàn thành nhanh hơn khi có CPU/I/O headroom.

Parallelism không phải miễn phí. Một query chạy DOP cao có thể sử dụng nhiều process, CPU, PGA, TEMP và I/O. Nếu nhiều query song song cùng chạy, hệ thống có thể bị oversubscribe.

### 10.1. Bài toán phù hợp

- Batch/reporting chạy lâu và có thể chia công việc.
- Query đọc/aggregate lượng dữ liệu lớn.
- ETL hoặc maintenance cần hoàn thành trong cửa sổ ngắn.
- Có CPU, I/O, memory và TEMP đủ dự phòng.

### 10.2. Đo DOP

Thử DOP ở nhiều mức, ví dụ 2, 4, 8 thay vì chỉ bật PARALLEL cao nhất. Ghi nhận:

- Elapsed time.
- CPU time.
- PX process và queue time.
- TEMP usage.
- I/O throughput/latency.
- Ảnh hưởng đến OLTP.
- Hiệu năng khi nhiều query cùng chạy.

Nếu tăng DOP từ 4 lên 8 nhưng elapsed time gần như không đổi, bottleneck có thể là I/O, skew, network, lock hoặc phần serial của plan. Không tiếp tục tăng DOP khi throughput hệ thống giảm.

### 10.3. Điều kiện triển khai

Định nghĩa resource manager plan, giới hạn parallel servers, giờ chạy và nhóm consumer. Cần tránh để batch chiếm tài nguyên của OLTP. Parallel execution phải được đánh giá ở cấp toàn hệ thống, không chỉ một câu SQL chạy riêng lẻ.

## 11. Đánh giá Advanced Queuing và xử lý bất đồng bộ

Oracle Advanced Queuing (AQ) cho phép ứng dụng gửi và nhận message được lưu trong database. Nó hữu ích khi cần tách producer và consumer, xử lý công việc nền hoặc phát sự kiện sau transaction nghiệp vụ.

Ví dụ: giao dịch tạo đơn hàng commit cùng message ORDER_CREATED; worker sau đó xử lý thông báo, đồng bộ hoặc tạo tác vụ tiếp theo.

### 11.1. Bài toán phù hợp

- Không cần xử lý mọi bước đồng bộ trong request người dùng.
- Cần lưu message bền vững trong cùng database.
- Producer và consumer có tốc độ xử lý khác nhau.
- Cần retry, delay, expiration hoặc nhiều subscriber.
- Cần atomicity giữa DML nghiệp vụ và enqueue.

### 11.2. Dữ liệu và workload cần đo

- Message rate trung bình và peak.
- Kích thước payload.
- Backlog tối đa và tốc độ tiêu thụ.
- Consumer processing time.
- Retry/exception rate.
- Retention và dung lượng queue table.
- Transaction size và lock duration.
- Yêu cầu ordering, deduplication và delivery semantics.

AQ không tự giải quyết side effect của hệ thống ngoài database. Nếu consumer gửi email hoặc gọi API, cần idempotency và retry có kiểm soát. Message có thể được giao lại khi consumer rollback; consumer nên idempotent.

### 11.3. POC

Thử producer/consumer ở peak rate, consumer downtime, queue backlog, message lỗi, retry, expiration và phục hồi worker. Đo latency từ enqueue đến xử lý, backlog growth, dung lượng và tác động transaction. Kiểm tra ON_COMMIT khi message cần commit cùng dữ liệu nghiệp vụ.

So sánh AQ với broker ngoài database dựa trên kiến trúc, khả năng vận hành, throughput, integration, license và nhu cầu tách biệt database. Không chọn AQ chỉ vì database đã có sẵn nếu hệ thống cần event streaming hoặc phân phối xuyên nhiều platform ở quy mô khác.

## 12. Đánh giá Flashback và khả năng phục hồi logic

Oracle có các khả năng Flashback để truy vấn hoặc khôi phục dữ liệu/object về trạng thái trước đó trong các điều kiện hỗ trợ. Mỗi cơ chế có phạm vi và yêu cầu khác nhau, ví dụ Flashback Query, Flashback Table, Flashback Drop và Flashback Database.

Cần xác định chính xác tình huống cần xử lý:

- Người dùng cập nhật nhầm một số dòng.
- Bảng bị drop.
- Cần xem dữ liệu tại một thời điểm trước.
- Cần khôi phục database về mốc trước một sự cố.
- Cần điều tra dữ liệu đã thay đổi.

### 12.1. Điều kiện cần kiểm tra

- Undo retention và khả năng giữ undo trong workload thực tế.
- Flashback logs và storage nếu dùng Flashback Database.
- FRA capacity và archive log.
- Database mode/feature prerequisites.
- Tác động đến DML, storage và backup.
- Quy trình xác định mốc thời gian/SCN.
- Quyền sử dụng và license theo cơ chế cụ thể.

Flashback không thay thế backup. Một số tình huống lỗi vật lý, mất storage hoặc mất toàn bộ site vẫn cần backup/restore và DR. Cần diễn tập phục hồi thay vì chỉ xác nhận tham số đã bật.

### 12.2. POC phục hồi

Tạo dữ liệu thử, ghi nhận SCN/time, thực hiện DML hoặc drop object theo kịch bản an toàn, sau đó khôi phục bằng cơ chế dự định. Đo thời gian, mức dữ liệu phục hồi, ảnh hưởng đến transaction và khả năng tiếp tục ứng dụng. Xác minh quyền, dependency, index, constraint và audit sau phục hồi.

## 13. Đánh giá tính năng bảo mật

Các tính năng bảo mật chỉ có giá trị khi gắn với mô hình đe dọa và dữ liệu thực tế.

Các nhóm khả năng có thể xem xét:

- Encryption at rest và TDE.
- Network encryption/TLS.
- Database Vault hoặc kiểm soát đặc quyền.
- Fine-Grained Auditing và Unified Auditing.
- Data Redaction hoặc masking cho môi trường không production.
- Virtual Private Database/row-level access control.
- Quản lý credential, wallet và key lifecycle.

### 13.1. Bắt đầu từ phân loại dữ liệu

Phân loại dữ liệu theo mức độ nhạy cảm: thông tin định danh, tài chính, thông tin sức khỏe, bí mật kinh doanh, dữ liệu công khai. Xác định nơi dữ liệu tồn tại: datafile, redo, archive, backup, export dump, replication, log và môi trường test.

TDE mã hóa dữ liệu ở trạng thái lưu trữ theo phạm vi được cấu hình; nó không tự thay thế quyền truy cập, application authorization hoặc mã hóa dữ liệu trên mọi đường truyền. TLS/network encryption giải quyết lớp truyền thông. Audit ghi lại hành động nhưng không ngăn hành động trái phép. Các tính năng cần được kết hợp theo threat model.

### 13.2. Đo tác động và kiểm tra vận hành

- CPU overhead.
- Backup/restore và export/import.
- Key rotation và wallet availability.
- Quy trình khôi phục khi mất key.
- Audit volume và retention.
- Tác động đến replication, standby và integration.
- Quyền truy cập DBA, application account và service account.

Nếu dùng encryption, quy trình quản lý key là một phần của khả năng phục hồi. Backup có thể còn nguyên nhưng không thể đọc nếu key/wallet thất lạc. Phải kiểm thử key backup, rotation, recovery và phân quyền.

## 14. Đánh giá tính năng theo vòng đời dữ liệu

Một hệ thống có dữ liệu nhiều năm nên phân loại dữ liệu theo mức độ truy cập:

- **Hot**: giao dịch gần đây, truy cập thường xuyên, cần latency thấp.
- **Warm**: dữ liệu cần tra cứu nhưng ít cập nhật.
- **Cold**: dữ liệu hiếm truy cập, phục vụ audit hoặc đối soát.
- **Expired**: dữ liệu hết thời hạn lưu trữ theo chính sách.

Các tính năng có thể kết hợp:

| Nhóm dữ liệu | Cơ chế có thể xem xét |
|---|---|
| Hot | Index, partition phù hợp, memory/cache, storage nhanh |
| Warm | Partitioning, compression phù hợp, read-only workload |
| Cold | Archive, compression, tablespace/storage tier, backup policy |
| Expired | Partition drop/truncate hoặc purge theo retention đã duyệt |

Không quyết định retention chỉ dựa trên dung lượng. Phải xác nhận nghĩa vụ pháp lý, audit, hợp đồng và khả năng khôi phục. Dữ liệu đã xóa khỏi partition có thể không còn truy cập qua database, nhưng vẫn có thể tồn tại trong backup/archive theo chính sách retention.

## 15. Thiết kế Proof of Concept có giá trị

POC nên trả lời một giả thuyết cụ thể. Ví dụ: “Partition theo ORDER_DATE sẽ giảm p95 báo cáo tháng xuống dưới 20 giây và giảm thời gian purge từ 7 giờ xuống dưới 10 phút, trong khi p99 insert OLTP không tăng quá 5%.”

### 15.1. Chọn dataset đại diện

Dataset cần phản ánh:

- Tổng số dòng và dung lượng gần production.
- Phân bố dữ liệu, skew và tỷ lệ NULL.
- Hot/cold data.
- Index, constraint và quan hệ.
- Dữ liệu biên và record bất thường.
- Tỷ lệ insert/update/delete.
- Thời điểm dữ liệu và workload đồng thời.

Dataset nhỏ có thể khiến index vừa bộ nhớ và không đại diện I/O; dữ liệu uniform có thể che giấu skew. Nếu không thể sao chép production, tạo synthetic data có phân bố và pattern tương tự, đồng thời ghi rõ giới hạn.

### 15.2. Workload test

Bao gồm:

1. Workload bình thường.
2. Peak concurrency.
3. Batch/maintenance chạy cùng OLTP.
4. Truy vấn mục tiêu.
5. Truy vấn không mục tiêu nhưng có khả năng bị ảnh hưởng.
6. Data growth hoặc ingest burst.
7. Restart/recovery/failover nếu tính năng liên quan HA.
8. Resource pressure hoặc dependency failure.
9. Kịch bản vận hành: backup, restore, patch, partition maintenance.

### 15.3. Kiểm soát biến thử nghiệm

- Giữ cùng dataset và application version.
- Giữ cùng bind values và request mix.
- Dùng cùng hardware/storage nếu so sánh tính năng.
- Ghi rõ cache cold/warm.
- Chạy đủ vòng để loại ảnh hưởng run đầu.
- Đo đồng thời database và application.
- Không thay đổi nhiều cấu hình một lúc.
- Lưu script, plan, logs và raw metrics.

### 15.4. Bảng kết quả POC

| Chỉ số | Baseline | Phương án mới | Mục tiêu | Đạt? |
|---|---:|---:|---:|---|
| p95 báo cáo tháng | 95 s | 18 s | ≤ 20 s | Có |
| p99 giao dịch | 420 ms | 430 ms | ≤ 450 ms | Có |
| Purge dữ liệu cũ | 7 giờ | 8 phút | ≤ 10 phút | Có |
| Segment size | 1.2 TB | 0.8 TB | ≤ 0.9 TB | Có |
| CPU peak | 78% | 84% | ≤ 85% | Có |

Các con số trong bảng chỉ minh họa cách ghi kết quả; không phải benchmark hoặc cam kết hiệu năng của Oracle. POC thật phải ghi cả điều kiện thử, số vòng, sai số và metric phụ.

## 16. Đánh giá chi phí toàn phần và license

Tổng chi phí không chỉ là license database. Cần tính:

- License database và option/management pack liên quan.
- Subscription/support hoặc cloud service cost.
- CPU/RAM/storage/network bổ sung.
- Shared storage, cluster, backup và DR capacity.
- Monitoring, observability và automation.
- Chi phí migration, test, downtime và rollout.
- Đào tạo DBA, developer, SRE và support.
- Chi phí vận hành định kỳ: patch, failover drill, partition maintenance, key rotation.
- Chi phí khi rollback hoặc khôi phục.
- Chi phí gián đoạn nếu tính năng không hoạt động như dự kiến.

### 16.1. Xác minh quyền sử dụng Oracle

Một số khả năng hoặc cách sử dụng có thể yêu cầu edition hoặc option/pack riêng, tùy phiên bản, deployment model và hợp đồng. Các ví dụ thường cần xác minh kỹ gồm RAC, Partitioning, In-Memory, Advanced Compression, Active Data Guard, Diagnostics Pack và Tuning Pack.

Không suy luận entitlement chỉ từ việc menu, package hoặc parameter xuất hiện trong database. Trước khi bật tính năng hoặc dùng công cụ quản trị, đối chiếu Oracle Database Licensing Information User Manual đúng phiên bản, hợp đồng, metric license và điều khoản cloud/hosting áp dụng. Khi không chắc, cần hỏi bộ phận quản lý license hoặc Oracle licensing specialist.

### 16.2. Tính ROI

Một mô hình đơn giản:

~~~text
Net benefit =
    Benefit over evaluation period
  - Implementation cost
  - License and infrastructure cost
  - Ongoing operation cost
  - Risk-adjusted disruption cost
~~~

Lợi ích có thể quy đổi từ:

- Giảm giờ DBA/operations.
- Giảm thời gian batch.
- Giảm storage/backup.
- Giảm downtime và tổn thất nghiệp vụ.
- Tăng số giao dịch phục vụ được.
- Rút ngắn thời gian ra quyết định từ báo cáo.

Không tính cùng một lợi ích hai lần. Ví dụ giảm backup size và giảm storage có thể là hai cách diễn đạt cùng một khoản tiết kiệm nếu không tách chi phí rõ.

## 17. Điều kiện triển khai thực tế

Một tính năng chỉ sẵn sàng triển khai khi các điều kiện kỹ thuật và tổ chức được đáp ứng.

### 17.1. Phiên bản và tương thích

Kiểm tra:

- Oracle Database version và patch level.
- Edition và option được cấp phép.
- OS/platform, cloud service và storage.
- JDBC driver, ORM, connection pool và application server.
- Migration tool, backup/recovery tool và monitoring.
- API/deprecated behavior và compatibility setting.
- Cấu hình primary/standby hoặc RAC nếu có.

Không chỉ thử trên database version mới nhất nếu production đang chạy phiên bản khác. POC phải tương đương môi trường đích hoặc ghi rõ khác biệt.

### 17.2. Hạ tầng

Đánh giá CPU, RAM, storage latency/IOPS, network bandwidth/latency, interconnect, capacity headroom và failure domain. Với RAC/Data Guard, topology và network thường quyết định khả năng đáp ứng. Với In-Memory/parallelism, memory/CPU headroom rất quan trọng. Với compression, CPU và storage là hai phía trade-off.

### 17.3. Bảo mật và quyền

- Tài khoản triển khai có quyền tối thiểu cần thiết.
- Secrets và wallet được quản lý an toàn.
- Audit và log có retention phù hợp.
- Data masking khi dùng dữ liệu production ở test.
- Network path và firewall đã được duyệt.
- Key management và recovery đã được diễn tập.
- Quyền DBA, application và service account tách biệt.

### 17.4. Năng lực vận hành

Phải có người chịu trách nhiệm và runbook cho:

- Triển khai và cấu hình.
- Monitoring/alerting.
- Backup/restore.
- Failover/switchover.
- Patch/upgrade.
- Capacity planning.
- Troubleshooting.
- Rollback hoặc forward recovery.
- Kiểm tra sau triển khai.

Nếu không có người vận hành hoặc không thể giám sát tính năng, chưa nên coi nó là production-ready.

## 18. Tương thích ứng dụng và chiến lược rollout

Thay đổi database có thể ảnh hưởng nhiều phiên bản ứng dụng cùng chạy trong rolling deployment. Cần kiểm tra schema/API tương thích với code cũ và mới.

Chiến lược expand-and-contract thường hữu ích:

1. Expand schema theo cách tương thích ngược.
2. Deploy code có thể hoạt động với cả cấu trúc cũ và mới.
3. Backfill hoặc chuyển dữ liệu theo batch.
4. Chuyển traffic sang code mới.
5. Quan sát lỗi và dữ liệu.
6. Contract: loại bỏ cấu trúc cũ sau khi không còn caller.

Với tính năng như RAC service hoặc Data Guard role-based service, rollout còn bao gồm connection string, FAN, pool, DNS/SCAN, failover policy và transaction retry. Với Partitioning, cần xác minh query và maintenance scripts. Với AQ, phải có producer/consumer compatibility và message versioning.

### 18.1. Kế hoạch rollback

Không phải mọi thay đổi Oracle đều rollback bằng ROLLBACK. DDL thường có implicit commit; partition move, data conversion hoặc compression có thể làm thay đổi cấu trúc và dữ liệu. Hãy xác định:

- Có thể chạy migration đảo ngược không?
- Có mất dữ liệu khi đảo ngược không?
- Có cần backup/restore hoặc flashback không?
- Có thể forward-fix nhanh hơn rollback không?
- Code cũ có chạy được trên schema mới không?
- Nếu feature bị disable, dữ liệu/metadata có còn sử dụng được không?

Với migration destructive, cần backup/recovery point, kiểm thử restore và phê duyệt rõ. Không coi một file rollback SQL chưa từng chạy thử là kế hoạch phục hồi đầy đủ.

## 19. Quyết định theo bằng chứng: ví dụ tổng hợp

### Tình huống A: bảng lịch sử tăng nhanh

**Bài toán:** ORDERS có hàng tỷ dòng; purge theo retention mất nhiều giờ; báo cáo thường lọc theo tháng.

**Dữ liệu cần:** số dòng theo tháng, query predicate, index, tỷ lệ late-arriving data, FK và retention.

**Tính năng xem xét:** Range/interval partitioning, local index, partition lifecycle.

**POC:** so sánh báo cáo theo tháng, purge bằng partition operation, insert vào partition mới, index maintenance và load dữ liệu đến muộn.

**Điều kiện:** version/edition/license, partition key, constraint, job tạo partition, monitor partition thiếu và migration.

**Quyết định:** chọn nếu pruning và lifecycle tạo lợi ích đo được, đồng thời constraint/index/operations chấp nhận được.

### Tình huống B: cần tăng khả năng sẵn sàng khi node lỗi

**Bài toán:** ứng dụng không chấp nhận downtime dài khi server/database instance gặp sự cố.

**Dữ liệu cần:** service criticality, session/transaction pattern, peak load, node failure domain và RTO/RPO.

**Tính năng xem xét:** RAC cho instance/node availability; Data Guard cho standby/DR; connection service, FAN và application continuity.

**POC:** node/instance failure, service relocation, reconnect, transaction outcome, site failover, recovery.

**Điều kiện:** cluster/shared storage/interconnect hoặc standby site/network, license, runbook, operator training.

**Quyết định:** chọn theo loại sự cố cần bảo vệ. Không coi RAC và Data Guard là hai phương án thay thế hoàn toàn cho nhau; nhiều hệ thống dùng cả hai ở các lớp khác nhau.

### Tình huống C: báo cáo phân tích chậm nhưng OLTP ổn định

**Bài toán:** truy vấn aggregate scan hàng trăm triệu dòng, p95 cao; giao dịch OLTP không được phép bị ảnh hưởng.

**Dữ liệu cần:** cột truy vấn, tỷ lệ hot data, plan, CPU/I/O, memory headroom và concurrency.

**Tính năng xem xét:** In-Memory, partition pruning, materialized view, parallel execution, summary table hoặc replica/reporting workload.

**POC:** chạy báo cáo đồng thời với OLTP, đo p95/p99, CPU, memory, I/O và startup population.

**Điều kiện:** license, RAM, memory policy, workload isolation và vận hành.

**Quyết định:** chọn giải pháp cải thiện query mà không làm p99 OLTP vượt ngưỡng; có thể cần tối ưu SQL/index trước khi thêm option.

### Tình huống D: storage và backup tăng nhanh

**Bài toán:** table lịch sử chiếm phần lớn storage; backup vượt cửa sổ.

**Dữ liệu cần:** tỷ lệ hot/cold, compression ratio, CPU, DML rate, backup throughput và retention.

**Tính năng xem xét:** partitioning theo thời gian, table/partition compression, RMAN backup compression, archive tier.

**POC:** đo từng nhóm dữ liệu và backup, kiểm tra CPU/DML/query, restore time và license.

**Quyết định:** có thể áp dụng chính sách khác nhau cho hot/warm/cold thay vì nén toàn bộ database.

### Tình huống E: tích hợp đồng bộ làm request chậm

**Bài toán:** request phải gọi nhiều hệ thống ngoài; latency và lỗi phụ thuộc dịch vụ downstream.

**Dữ liệu cần:** message rate, payload size, ordering, retry, duplicate, consumer latency và yêu cầu transaction.

**Tính năng xem xét:** AQ hoặc message broker, transactional outbox, background worker.

**POC:** downstream unavailable, backlog, retry, duplicate, poison message, recovery và observability.

**Quyết định:** chọn theo nhu cầu tích hợp, khả năng vận hành và phạm vi hệ thống; AQ phù hợp khi transaction Oracle và queue là trung tâm, broker ngoài có thể phù hợp khi cần phân phối đa nền tảng.

## 20. Ma trận chấm điểm lựa chọn

Có thể dùng ma trận trọng số để làm rõ trade-off. Trọng số phải được thống nhất trước POC; không điều chỉnh sau khi thấy kết quả chỉ để phương án yêu thích thắng.

| Tiêu chí | Trọng số gợi ý | Cách đánh giá |
|---|---:|---|
| Giải quyết bài toán | 25% | Mức đạt mục tiêu định lượng |
| Hiệu năng và khả năng mở rộng | 15% | Throughput, latency, capacity |
| Độ sẵn sàng và phục hồi | 15% | RTO/RPO, failure test |
| Chi phí/license | 15% | Tổng chi phí sở hữu |
| Vận hành | 10% | Monitoring, runbook, kỹ năng |
| Tương thích | 10% | Version, application, migration |
| Bảo mật và tuân thủ | 5% | Access, encryption, audit |
| Rollback và rủi ro | 5% | Khả năng quay lui/forward recovery |

Có thể chấm từng phương án theo thang 1–5:

- 1: không đáp ứng hoặc rủi ro không chấp nhận được.
- 2: đáp ứng một phần, cần nhiều điều kiện chưa có.
- 3: đáp ứng mục tiêu cơ bản, còn trade-off cần quản lý.
- 4: đáp ứng tốt, điều kiện triển khai khả thi.
- 5: đáp ứng tốt và có bằng chứng POC, vận hành/recovery đã kiểm chứng.

Điểm tổng không thay thế các điều kiện bắt buộc. Nếu license chưa được xác nhận, security control chưa đạt hoặc RPO/RTO không đáp ứng, phương án không thể được duyệt chỉ vì tổng điểm cao.

## 21. Tài liệu cần có trước khi quyết định

Một hồ sơ đánh giá tính năng mở rộng nên gồm:

1. Problem statement và impact nghiệp vụ.
2. Baseline workload và dữ liệu.
3. Kiến trúc hiện tại và dependency.
4. Mô tả tính năng cùng giới hạn.
5. Version/edition/license check.
6. Thiết kế POC, dataset và workload.
7. Kết quả benchmark và raw metrics.
8. Phân tích chi phí toàn phần.
9. Security review và operational readiness.
10. Kế hoạch rollout, monitoring và recovery.
11. Quyết định, người phê duyệt và điều kiện còn mở.

Lưu cả kết quả không đạt. Một POC cho thấy compression làm CPU tăng quá ngưỡng hoặc RAC không scale do hot block vẫn có giá trị: nó giúp tránh đầu tư sai.

## 22. Nguyên tắc ra quyết định

- Bắt đầu từ bài toán và tác động nghiệp vụ; không bắt đầu từ danh sách tính năng.
- Thu thập baseline và dữ liệu đại diện trước khi thử nghiệm.
- Đo cả workload mục tiêu và workload bị ảnh hưởng.
- Phân biệt bottleneck SQL, CPU, I/O, lock, memory, network và kiến trúc.
- Chọn feature theo cơ chế giải quyết đúng nguyên nhân.
- Kiểm tra version, edition, option, license và platform trước khi bật.
- POC phải có dữ liệu, concurrency, failure scenario và metric rõ ràng.
- Tính chi phí hạ tầng, license, vận hành, đào tạo và recovery.
- Không xem RAC là thay thế backup hoặc Data Guard; không xem Flashback là thay thế backup.
- Không xem partitioning, compression, In-Memory hoặc parallel execution là tối ưu tự động cho mọi query.
- Thiết kế rollout tương thích với ứng dụng đang chạy và có kế hoạch rollback/forward recovery.
- Chỉ đưa vào production khi có owner, runbook, monitoring, alert và kiểm thử phục hồi.
- Ghi lại giả định, bằng chứng, giới hạn và điều kiện phải đánh giá lại khi dữ liệu/workload thay đổi.

Đánh giá tính năng mở rộng là một quyết định kiến trúc dựa trên dữ liệu và điều kiện thực tế. Khi bài toán được định lượng, workload được đo, POC được kiểm soát và chi phí/vận hành được xem xét đầy đủ, đội ngũ có thể chọn đúng tính năng Oracle, triển khai đúng phạm vi và biết rõ lợi ích cũng như giới hạn của lựa chọn đó.
