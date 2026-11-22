# Bộ đệm lạnh sau khởi động, triển khai hoặc chuyển đổi máy chủ

Sau khi cơ sở dữ liệu khởi động lại, ứng dụng triển khai phiên bản mới hoặc hệ thống chuyển sang máy chủ dự phòng, hiệu năng có thể giảm rõ rệt trong một khoảng thời gian. Các truy vấn vốn chạy nhanh bắt đầu đọc nhiều trang từ storage, độ trễ p95/p99 tăng, I/O và hàng đợi đọc tăng, trong khi CPU có thể chưa phải nút thắt chính. Một nguyên nhân phổ biến là bộ đệm dữ liệu đang lạnh (cold cache): các trang dữ liệu và chỉ mục mà workload thường dùng chưa có trong bộ nhớ của máy chủ vừa hoạt động.

Trong DATABASE_PERFORMANCE, cần hiểu cold cache là trạng thái của nhiều lớp bộ nhớ, nhận diện đúng lớp nào bị mất nội dung, xây dựng quy trình warm-up có kiểm soát và đo thời gian phục hồi. Khởi động lại database, triển khai ứng dụng và failover không tạo ra cùng một trạng thái cache. Một số cache có thể còn tồn tại ở hệ điều hành hoặc storage, trong khi buffer pool của instance mới hoàn toàn trống. Kế hoạch thực thi (plan cache) cũng có thể lạnh độc lập với data cache.

Mục tiêu không phải nạp toàn bộ dữ liệu vào RAM bằng mọi giá. Mục tiêu là đưa working set quan trọng trở lại trạng thái nóng đủ nhanh, không làm quá tải storage, không chiếm hết cache bằng dữ liệu ít dùng và không tạo một đợt tải đồng loạt khi traffic quay lại.

## 1. Cold cache là gì?

Cache là vùng lưu trữ tạm thời giữ dữ liệu hoặc kết quả thường được truy cập để tránh đọc hoặc tính toán lại. Cold cache là trạng thái mà các mục cần thiết cho workload hiện tại chưa có trong cache phù hợp, vì vậy truy vấn phải lấy chúng từ tầng lưu trữ chậm hơn hoặc xây dựng lại thông tin.

Ví dụ, một truy vấn lấy đơn hàng gần đây thường đọc các trang index và data page đã nằm trong RAM. Sau khi database chuyển sang máy chủ khác, buffer pool của máy chủ mới chưa có các trang đó. Truy vấn đầu tiên phải đọc từ storage; các truy vấn tiếp theo có thể nhanh hơn khi trang đã được nạp vào cache.

Cold cache không nhất thiết có nghĩa mọi cache đều trống. Trang dữ liệu có thể còn trong page cache của hệ điều hành, cache của storage controller hoặc cache của thiết bị. Ngược lại, buffer pool của database có thể mất toàn bộ nội dung khi process hoặc instance khởi động lại. Cần phân biệt cache nào đang lạnh trước khi chọn cách khắc phục.

### 1.1. Dấu hiệu thường gặp

- Physical reads tăng mạnh so với mức bình thường.
- Read IOPS, throughput đọc và độ trễ storage tăng khi traffic quay lại.
- Buffer cache hit ratio giảm trong giai đoạn đầu.
- p95/p99 latency cao hơn nhiều so với median.
- Truy vấn đọc các bảng hoặc index phổ biến chậm hơn, sau đó cải thiện dần.
- Wait event liên quan đến đọc trang hoặc I/O tăng.
- CPU có thể thấp hơn bình thường nếu truy vấn đang chờ storage; hoặc tăng nếu warm-up tạo quá nhiều scan và giải nén.
- Throughput ứng dụng giảm dù số request chưa tăng tương ứng.

Các dấu hiệu này không đủ để kết luận cold cache. Storage chậm, query plan thay đổi, thống kê lỗi thời, thiếu RAM, checkpoint, recovery hoặc contention cũng có thể tạo biểu hiện tương tự. Cần so sánh với baseline và kiểm tra nhiều chỉ số cùng lúc.

### 1.2. Cache lạnh và cache miss thông thường

Cache miss là một lần truy cập không tìm thấy mục trong cache. Miss là hiện tượng bình thường ngay cả khi hệ thống đã ổn định. Cold cache là trạng thái rộng hơn: một phần đáng kể working set chưa được nạp, khiến tỷ lệ miss và chi phí đọc cao trong một giai đoạn.

Không nên cố đạt hit ratio 100%. Một số truy vấn đọc dữ liệu mới hoặc dữ liệu hiếm gặp sẽ luôn gây cache miss. Việc cố giữ mọi trang trong RAM có thể làm cache chứa dữ liệu ít giá trị và đẩy working set quan trọng ra ngoài.

## 2. Các lớp cache cần phân biệt

Một request đọc dữ liệu có thể đi qua nhiều tầng:

1. Cache ở ứng dụng hoặc dịch vụ: kết quả truy vấn, object cache, Redis hoặc cache nghiệp vụ.
2. Cache dữ liệu của database: buffer pool hoặc buffer cache giữ data page và index page.
3. Cache kế hoạch: lưu execution plan hoặc thông tin chuẩn bị câu lệnh.
4. Page cache của hệ điều hành: cache các block/page đọc từ file nếu cấu hình và đường I/O sử dụng nó.
5. Cache của storage controller, SAN, hypervisor hoặc thiết bị: giữ block ở tầng hạ tầng.

Các tầng có vòng đời và phạm vi khác nhau. Restart ứng dụng có thể làm mất cache ở process nhưng không làm mất buffer pool của database. Restart database có thể làm mất buffer pool nhưng hệ điều hành vẫn giữ page cache. Failover sang máy chủ khác thường làm mất cache trong RAM của instance đích dù dữ liệu nằm trên shared storage.

| Lớp cache | Nội dung | Sự kiện có thể làm lạnh | Cách phục hồi thường gặp |
|---|---|---|---|
| Application cache | Object, response hoặc kết quả nghiệp vụ | Restart ứng dụng, đổi cache key, flush | Warm-up theo API hoặc job có kiểm soát |
| Database data cache | Data page và index page | Restart instance, failover sang node khác, thay đổi working set | Workload warm-up hoặc cơ chế prewarm của engine |
| Plan cache | Execution plan, prepared statement hoặc metadata thực thi | Restart, flush plan, thay đổi schema/compile context | Compile lại qua workload đại diện và kiểm tra plan |
| OS page cache | File page/block đã đọc | Reboot host, memory pressure, file cache eviction | Đọc có chọn lọc từ storage |
| Storage cache | Block ở controller/device | Failover storage, power cycle, cache policy thay đổi | Phụ thuộc hạ tầng và hệ thống storage |

## 3. Những tình huống thường làm cache lạnh

### 3.1. Database restart hoặc host reboot

Khi database process dừng, vùng nhớ riêng của instance như buffer pool thường mất nội dung. Nếu host cũng reboot, page cache của hệ điều hành có thể bị xóa. Sau khi dịch vụ lên lại, các truy vấn đầu tiên phải đọc lại working set từ storage.

Database có thể cần thời gian recovery để áp dụng log hoặc khôi phục trạng thái giao dịch trước khi nhận traffic bình thường. Recovery time và cache warm-up là hai giai đoạn khác nhau: hoàn tất recovery không đồng nghĩa buffer cache đã nóng.

### 3.2. Triển khai ứng dụng

Rolling deployment có thể khởi động process mới, làm mất application cache, connection pool và prepared statement ở process cũ. Nếu database không restart, data cache của database có thể vẫn nóng. Tuy nhiên, workload mới có thể truy cập bảng, cột hoặc đường truy vấn khác, làm working set dịch chuyển.

Một bản phát hành thay đổi SQL, ORM mapping, tham số truy vấn hoặc luồng nghiệp vụ cũng có thể làm plan cache được sử dụng khác đi. Cần tách tác động của application cache, plan cache và data cache khi đo.

### 3.3. Failover hoặc chuyển đổi máy chủ

Trong failover, node dự phòng có thể đã đồng bộ dữ liệu nhưng chưa giữ các trang nóng trong RAM. Shared storage hoặc replication bảo đảm dữ liệu sẵn có không đồng nghĩa cache trong bộ nhớ được chia sẻ. Máy chủ đích cần tự nạp working set của nó.

Nếu failover xảy ra trong giờ cao điểm, lượng truy vấn đầu tiên có thể đồng thời đẩy một lượng lớn page read xuống storage. Đây là tình huống dễ tạo read storm và làm p99 tăng mạnh.

### 3.4. Thay đổi working set hoặc áp lực bộ nhớ

Ngay cả khi không restart, một batch scan lớn, báo cáo nặng hoặc workload mới có thể đẩy các trang quan trọng ra khỏi buffer pool. Cache khi đó có thể lạnh tương đối đối với truy vấn giao dịch chính.

Tăng kích thước buffer pool không phải lúc nào cũng giải quyết được. Nếu working set lớn hơn RAM khả dụng hoặc có scan liên tục, hệ thống vẫn có thể churn cache.

## 4. Data cache và plan cache là hai vấn đề riêng

Data cache giữ trang dữ liệu và index để giảm I/O. Plan cache giữ kế hoạch thực thi đã biên dịch hoặc thông tin chuẩn bị để giảm chi phí compile/optimize.

Sau restart, cả hai có thể lạnh, nhưng biểu hiện khác nhau:

- Data cache lạnh thường làm physical reads và storage latency tăng.
- Plan cache lạnh có thể làm compile/optimization CPU tăng và thời gian chuẩn bị truy vấn dài hơn.
- Plan mới có thể khác plan cũ do statistics, schema, tham số, phiên bản engine hoặc môi trường khác.
- Một truy vấn có thể có plan tốt nhưng vẫn chậm vì data page chưa nóng.
- Một truy vấn có thể có data cache nóng nhưng vẫn chậm do plan regression.

Không dùng một chỉ số để kết luận cả hai. Hãy theo dõi physical reads và buffer hit cho data cache; theo dõi compilation, plan reuse, query store hoặc thông tin prepared statement cho plan cache.

### 4.1. Kế hoạch truy vấn thay đổi sau triển khai

Schema migration, thay đổi statistics hoặc phiên bản ứng dụng có thể khiến optimizer chọn kế hoạch khác. Nếu một truy vấn trước đây dùng index seek nhưng sau deploy lại scan bảng, warm-up chỉ làm truy vấn scan nhanh hơn trong thời gian ngắn; nó không sửa được plan regression.

Hãy lưu execution plan và số liệu trước/sau triển khai. Kiểm tra estimated rows so với actual rows, index được chọn, join order, sort/hash spill và tham số thực tế. Chỉ thực hiện plan forcing hoặc hint khi có bằng chứng, đánh giá phạm vi ảnh hưởng và kế hoạch gỡ bỏ.

## 5. Working set và thứ tự ưu tiên warm-up

Working set là tập trang dữ liệu và index được workload truy cập thường xuyên trong một khoảng thời gian. Warm-up hiệu quả tập trung vào working set có giá trị cao, thay vì đọc tuần tự mọi bảng.

Có thể phân loại:

- Critical working set: trang phục vụ luồng giao dịch chính, xác thực, tra cứu khách hàng, tồn kho hoặc đơn hàng đang hoạt động.
- Secondary working set: báo cáo thường dùng nhưng không ảnh hưởng trực tiếp đến mọi request.
- Cold/archive data: dữ liệu lịch sử hiếm khi truy cập.
- One-time scan data: dữ liệu chỉ được đọc trong một batch hoặc báo cáo đặc biệt.

Ưu tiên dựa trên tần suất, tác động nghiệp vụ, độ trễ mục tiêu, kích thước và khả năng dùng lại. Một bảng lớn nhưng ít truy cập không nên tự động được warm trước một index nhỏ phục vụ hầu hết request.

### 5.1. Lập danh sách mục tiêu

Nguồn dữ liệu hữu ích:

- Top query theo tổng thời gian, số lần chạy và physical reads.
- Top bảng/index theo số lần đọc hoặc buffer usage.
- Query Store, performance schema hoặc thống kê workload của engine.
- APM và trace ứng dụng để xác định endpoint quan trọng.
- Báo cáo thời gian cao điểm và luồng nghiệp vụ quan trọng.
- Kế hoạch triển khai, lịch batch và thời điểm traffic dự kiến tăng.

Không dùng một danh sách truy vấn duy nhất cho mọi node nếu workload của primary, replica, reporting node và worker khác nhau.

### 5.2. Kích thước working set so với RAM

Nếu working set quan trọng lớn hơn phần RAM có thể dành cho database cache, không thể giữ tất cả trang nóng cùng lúc. Cần ưu tiên theo xác suất truy cập và chi phí miss, xem lại truy vấn, index, partitioning và phân tầng dữ liệu.

RAM dành cho buffer pool còn phải chừa chỗ cho:

- Bộ nhớ của hệ điều hành.
- Connection, sort/hash, query execution và temporary workspace.
- Các process phụ của database.
- Cache ở ứng dụng và agent giám sát.
- Các dịch vụ khác cùng host nếu có.

Không cấu hình buffer pool chiếm gần hết RAM vật lý mà bỏ qua peak memory của query. Khi host swap hoặc memory pressure, latency có thể tệ hơn nhiều so với lợi ích tăng cache.

## 6. Warm-up có kiểm soát

Warm-up là chủ động đọc hoặc truy cập các dữ liệu quan trọng để đưa chúng vào cache trước khi tải thật tăng. Có thể dùng:

- Workload replay từ truy vấn đại diện đã được lọc và ẩn dữ liệu nhạy cảm.
- Các truy vấn đọc nhỏ, giới hạn phạm vi và có thứ tự ưu tiên.
- Cơ chế prewarm chuyên biệt của database.
- Tải lại cache ở tầng ứng dụng sau khi database sẵn sàng.
- Chuyển traffic từng phần sau khi các chỉ số warm-up đạt ngưỡng.

Warm-up cần có giới hạn concurrency, IOPS, CPU và thời gian. Nếu chạy quá nhiều truy vấn đồng thời, chính quá trình warm-up có thể làm storage quá tải, gây tranh chấp và làm truy vấn production chậm hơn.

### 6.1. Warm-up theo lớp ưu tiên

Một thứ tự thường phù hợp:

1. Kiểm tra database đã hoàn tất recovery và sẵn sàng nhận truy vấn.
2. Nạp các index và trang cần cho luồng giao dịch quan trọng.
3. Warm-up các bảng nhỏ, lookup/reference data thường dùng.
4. Chạy truy vấn đại diện cho endpoint có tần suất cao.
5. Mở rộng sang workload thứ cấp.
6. Tăng traffic theo từng bước và theo dõi read latency, queue depth, p95/p99.

Thứ tự cụ thể phải dựa trên access pattern. Một truy vấn warm-up có thể đọc nhiều trang không cần thiết nếu nó quét toàn bảng hoặc chọn plan không phù hợp.

### 6.2. Giới hạn tài nguyên

Đặt giới hạn rõ ràng:

- Số truy vấn warm-up chạy đồng thời.
- Tốc độ đọc tối đa hoặc I/O budget.
- Thời gian tối đa cho mỗi nhóm mục tiêu.
- Số hàng và kích thước kết quả trả về.
- Mức CPU có thể dùng.
- Điều kiện dừng khi p95/p99 hoặc storage latency vượt ngưỡng.

Ưu tiên truy vấn chỉ đọc và tránh các câu lệnh có side effect. Không gọi hàm nghiệp vụ, trigger hoặc stored procedure ghi dữ liệu chỉ để làm nóng cache.

### 6.3. Tránh cache pollution

Cache pollution xảy ra khi warm-up nạp quá nhiều dữ liệu ít giá trị, đẩy các trang quan trọng ra khỏi cache. Ví dụ chạy một full table scan trên bảng archive rất lớn ngay trước khi mở traffic có thể thay thế phần lớn working set của giao dịch.

Giảm rủi ro bằng cách:

- Chỉ warm các bảng/index có bằng chứng được workload dùng thường xuyên.
- Dùng block range hoặc phân đoạn dữ liệu nếu công cụ hỗ trợ.
- Tránh scan lịch sử toàn bảng khi chỉ cần dữ liệu gần đây.
- Chạy từng nhóm nhỏ, kiểm tra cache hit và physical reads sau mỗi bước.
- Dừng nếu I/O hoặc latency của truy vấn quan trọng tăng.

## 7. PostgreSQL: prewarm và workload thực tế

PostgreSQL dùng shared buffers làm buffer cache chính của instance. Page cache của hệ điều hành cũng có thể tham gia tùy cấu hình I/O.

Extension pg_prewarm cung cấp hàm nạp block của relation vào cache. Ví dụ:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_prewarm;

SELECT pg_prewarm('public.orders', 'buffer');
SELECT pg_prewarm('public.orders_customer_created_idx', 'buffer');
~~~

Chế độ buffer đọc các block vào PostgreSQL shared buffer cache. Extension cũng có các chế độ khác như read hoặc prefetch với hành vi khác nhau; hãy kiểm tra tài liệu đúng phiên bản trước khi sử dụng. Relation lớn có thể chiếm cache và gây pollution, vì vậy có thể cần giới hạn block range thay vì warm toàn bộ.

### 7.1. Kiểm tra trạng thái cache

Có thể dùng extension pg_buffercache để quan sát trang đang nằm trong shared buffers nếu extension đã được cài và quyền cho phép. Không nên cài extension hoặc thay đổi cấu hình production chỉ để có một chỉ số mà không qua quy trình vận hành.

Kết hợp:

- pg_stat_database và pg_stat_io ở phiên bản hỗ trợ để xem block reads và I/O.
- pg_stat_statements để xác định truy vấn có nhiều shared/local/temp blocks.
- EXPLAIN (ANALYZE, BUFFERS) trên truy vấn đại diện.
- wait events và latency của storage.

Shared hit không đồng nghĩa chắc chắn dữ liệu được phục vụ hoàn toàn từ RAM vật lý trong mọi tầng; cần hiểu hệ điều hành và storage cache. So sánh physical reads, buffer reads và latency thực tế.

### 7.2. Sau restart hoặc failover

Một quy trình có thể gồm:

1. Chờ PostgreSQL hoàn tất crash recovery và xác nhận readiness.
2. Khởi chạy warm-up theo truy vấn/quan hệ ưu tiên.
3. Nếu dùng pg_prewarm, chọn relation hoặc block range có giá trị cao.
4. Đo shared buffer activity, physical reads và p95/p99.
5. Mở traffic dần sau khi I/O đã ổn định.

Không coi việc pg_prewarm trả về số block đã nạp là bằng chứng mọi endpoint đã nóng. Nó chỉ xác nhận các block được yêu cầu đã được xử lý theo chế độ đã chọn.

## 8. MySQL InnoDB: lưu và nạp trạng thái buffer pool

InnoDB sử dụng buffer pool để giữ data page và index page. MySQL hỗ trợ dump danh sách page đang có trong buffer pool và nạp lại danh sách này sau restart trên cùng môi trường phù hợp.

Các tùy chọn thường dùng:

- innodb_buffer_pool_dump_at_shutdown: ghi thông tin page của buffer pool khi shutdown.
- innodb_buffer_pool_load_at_startup: nạp lại các page được lưu trong dump khi startup.
- innodb_buffer_pool_dump_pct: giới hạn tỷ lệ page gần đây được ghi vào dump theo chính sách của engine.
- innodb_buffer_pool_load_now và innodb_buffer_pool_dump_now: kích hoạt thao tác nạp hoặc dump theo nhu cầu ở phiên bản hỗ trợ.

Ví dụ cấu hình:

~~~ini
[mysqld]
innodb_buffer_pool_dump_at_shutdown=ON
innodb_buffer_pool_load_at_startup=ON
innodb_buffer_pool_dump_pct=25
~~~

Dump này lưu thông tin nhận diện page cần nạp, không phải bản sao dữ liệu page. Khi startup, InnoDB đọc các page tương ứng từ tablespace vào buffer pool. Nếu file dump không có, page không còn tồn tại hoặc môi trường đã thay đổi, quá trình nạp có thể không khôi phục đúng toàn bộ working set cũ.

### 8.1. Theo dõi quá trình nạp

Tùy phiên bản, có thể theo dõi trạng thái qua status variables như Innodb_buffer_pool_load_status và các thông tin trong SHOW ENGINE INNODB STATUS. Kiểm tra tài liệu phiên bản đang chạy vì tên và khả năng quan sát có thể khác nhau.

Đo thêm:

- Innodb_buffer_pool_reads và Innodb_buffer_pool_read_requests.
- Read IOPS và latency storage.
- Buffer pool pages data/free/dirty.
- Query latency và số rows examined.
- Số request đồng thời trong lúc load.

### 8.2. Giới hạn

Nạp buffer pool quá nhanh có thể cạnh tranh I/O với recovery, replication và traffic production. Dump cũ có thể không đại diện working set sau deploy. Nếu schema, index hoặc dữ liệu thay đổi, danh sách page đã lưu có thể không còn mang lại lợi ích như trước.

Sau failover sang một server khác, cần xác nhận dump file, cấu hình, version và tablespace mapping phù hợp. Không sao chép dump giữa các môi trường khác cấu trúc mà không kiểm tra.

## 9. SQL Server: buffer pool và plan cache

SQL Server dùng buffer pool để giữ data page. Sau restart instance, buffer pool trong bộ nhớ được xây dựng lại khi workload truy cập dữ liệu. Plan cache cũng được xây dựng lại qua compile và thực thi câu lệnh.

SQL Server không có một cơ chế mặc định phổ quát tương đương danh sách page warm-up cho mọi workload. Cách an toàn thường là chạy workload đọc đại diện hoặc công cụ warm-up được kiểm soát, dựa trên các truy vấn quan trọng và index tương ứng.

### 9.1. Theo dõi buffer pool

Có thể quan sát:

- sys.dm_os_buffer_descriptors để xem page đang nằm trong buffer pool.
- sys.dm_io_virtual_file_stats để xem số lần đọc/ghi và độ trễ I/O theo file.
- sys.dm_exec_query_stats và Query Store để xác định truy vấn quan trọng.
- Wait statistics để xem PAGEIOLATCH và các wait liên quan.

Page life expectancy chỉ là một tín hiệu tổng hợp, không nên dùng một ngưỡng cố định cho mọi máy chủ hoặc workload. Xem xu hướng, kích thước RAM, working set và các wait I/O đi kèm.

### 9.2. Warm-up bằng truy vấn đại diện

Chọn truy vấn đọc các index/table quan trọng, với tham số phổ biến và giới hạn concurrency. Nếu dùng Query Store, lịch sử truy vấn và plan giúp xác định workload, nhưng Query Store không tự nạp data page vào buffer pool.

Không chạy DBCC DROPCLEANBUFFERS hoặc DBCC FREEPROCCACHE trên production để “làm mới” cache. Đây là các lệnh thường dùng trong môi trường kiểm thử có kiểm soát; chúng chủ động làm lạnh cache và có thể gây suy giảm nghiêm trọng nếu chạy trên hệ thống đang phục vụ người dùng.

### 9.3. Plan cache sau triển khai

Query Store có thể lưu lịch sử query, runtime statistics và plan theo thời gian, hỗ trợ so sánh sau deploy. Nó không đồng nghĩa với việc plan cache hiện tại đã được warm. Hãy tách:

- Compile CPU và plan reuse.
- Logical reads và physical reads.
- Plan shape và estimated/actual rows.

Nếu plan mới bị regression, warm-up data cache không giải quyết được nguyên nhân. Cần điều tra statistics, parameter sensitivity, schema change và plan selection.

## 10. Oracle Database: buffer cache và shared pool

Oracle Database có database buffer cache để giữ block dữ liệu và shared pool để giữ thông tin như SQL area, cursor và metadata được chia sẻ. Hai vùng này có vai trò khác nhau:

- Buffer cache lạnh làm tăng physical reads.
- Shared pool lạnh có thể làm tăng hard parse hoặc chi phí nạp metadata.

Warm-up thường được thực hiện bằng workload đọc đại diện và quy trình ứng dụng. Oracle có thể cấu hình các buffer pool như KEEP hoặc RECYCLE để điều chỉnh cách một số segment sử dụng cache, nhưng đây là quyết định quản trị dựa trên workload, không phải lệnh warm-up chung cho mọi bảng.

### 10.1. Đo cache và I/O

Các nguồn quan sát có thể gồm:

- V$SYSSTAT và V$SESSTAT cho các thống kê logical/physical reads.
- V$BUFFER_POOL_STATISTICS cho thống kê buffer pool.
- V$SQL và các view liên quan cho cursor và SQL execution.
- V$SYSTEM_EVENT hoặc V$SESSION_WAIT để xem wait event.
- AWR/ASH nếu hệ thống được cấp phép và cấu hình phù hợp.

Không chỉ dựa vào buffer cache hit ratio. Một hệ thống có hit ratio cao vẫn có thể chậm vì các lần physical read còn lại tập trung vào truy vấn quan trọng hoặc storage latency cao.

### 10.2. Sau failover hoặc chuyển node

Node đích có thể cần thời gian nạp lại block và cursor. Nếu dùng Oracle RAC, mỗi instance có cache và hoạt động quản lý cache riêng; việc chuyển workload sang instance khác không bảo đảm tất cả block nóng đều đã có trong cache cục bộ của instance đó. Cần theo dõi interconnect, cache fusion và physical I/O theo kiến trúc triển khai.

## 11. Quy trình warm-up sau restart, deploy hoặc failover

### 11.1. Trước sự kiện

1. Ghi baseline p50/p95/p99, throughput, physical reads, IOPS, read latency, CPU và wait events.
2. Xác định critical working set từ query statistics và APM.
3. Ghi lại truy vấn đại diện, tham số và index cần thiết.
4. Xác định lớp cache sẽ bị mất trong sự kiện: application, database, OS hoặc plan cache.
5. Kiểm tra dung lượng RAM, I/O budget và mức tải nền.
6. Chuẩn bị script hoặc job warm-up chỉ đọc, có giới hạn và có thể dừng.
7. Xác định điều kiện readiness và ngưỡng cho phép mở traffic.

### 11.2. Sau khi instance mới sẵn sàng

1. Xác nhận recovery/replication đã đạt trạng thái an toàn theo kiến trúc.
2. Xác nhận schema và index đã ở phiên bản cuối cùng của deployment.
3. Nạp các cache có thể phục hồi từ trạng thái lưu trước đó nếu engine hỗ trợ và dữ liệu còn tương thích.
4. Chạy warm-up cho nhóm truy vấn quan trọng theo thứ tự ưu tiên.
5. Giới hạn concurrency, IOPS và thời gian; dừng khi vượt ngưỡng bảo vệ.
6. Kiểm tra physical reads, buffer activity, storage queue và p95/p99.
7. Mở traffic theo từng đợt nhỏ hoặc tăng dần tỷ lệ traffic.
8. Tiếp tục theo dõi trong giai đoạn ramp-up và điều chỉnh nếu cache churn hoặc read latency tăng.

### 11.3. Sau khi traffic ổn định

- So sánh số liệu với baseline cùng khung thời gian và loại workload.
- Kiểm tra tỷ lệ truy vấn quan trọng đã trở lại mức bình thường.
- Xác định các trang hoặc bảng vẫn gây physical read cao.
- Kiểm tra cache pollution do warm-up hoặc batch.
- Đánh giá thời gian phục hồi thực tế và cập nhật runbook.
- Ghi nhận truy vấn có plan mới hoặc statistics thay đổi.

## 12. Thiết kế warm-up workload

Một warm-up workload tốt mô phỏng cách ứng dụng thực sự truy cập dữ liệu, nhưng có giới hạn để không làm quá tải hệ thống.

### 12.1. Chọn truy vấn đại diện

Ưu tiên:

- Query có tần suất cao và ảnh hưởng lớn đến p95/p99.
- Truy vấn phục vụ login, quyền truy cập, tra cứu và luồng giao dịch cốt lõi.
- Index lookup và data page có tỷ lệ tái sử dụng cao.
- Dữ liệu gần đây hoặc dữ liệu đang hoạt động.
- Truy vấn có thời gian chạy dự đoán được.

Không chọn truy vấn chỉ vì tổng thời gian cao nếu nó là batch hiếm gặp và không ảnh hưởng đến traffic mở đầu. Cần phân biệt tổng tài nguyên tiêu thụ với mức quan trọng khi khởi động.

### 12.2. Dùng tham số có tính đại diện

Truy vấn có thể đọc các vùng dữ liệu khác nhau theo tenant, ngày hoặc trạng thái. Chỉ warm một giá trị tham số có thể không đưa đúng working set vào cache.

Chọn một tập tham số đại diện theo phân bố thực tế:

- Tenant lớn và tenant nhỏ.
- Dữ liệu mới và một số khoảng lịch sử thường dùng.
- Trạng thái phổ biến.
- Khóa có tần suất truy cập cao.

Không cần warm mọi giá trị có thể có. Chọn mẫu theo tần suất và tác động.

### 12.3. Tránh kết quả quá lớn

Warm-up chủ yếu cần đọc page, không cần chuyển hàng triệu dòng về ứng dụng. Dùng truy vấn có projection tối thiểu, giới hạn phạm vi và tránh truyền kết quả lớn qua mạng. Tuy nhiên, LIMIT nhỏ không bảo đảm mọi page cần thiết đã được đọc; hãy xác nhận execution plan và phạm vi page được truy cập.

Nếu truy vấn gọi hàm volatile, stored procedure có side effect hoặc trigger ghi dữ liệu, không dùng nó làm warm-up. Tạo truy vấn đọc chuyên biệt hoặc dùng công cụ prewarm của engine.

### 12.4. Điều khiển concurrency

Bắt đầu với concurrency thấp, đo storage latency và tăng dần. Nếu nhiều worker cùng warm một bảng lớn, chúng có thể gây đọc lặp và tranh chấp cache. Chia mục tiêu thành nhóm nhỏ, tránh các worker nạp cùng một page range không cần thiết.

Thiết lập circuit breaker cho warm-up: nếu p95 production vượt ngưỡng, storage queue tăng quá mức hoặc replication lag xấu đi, giảm concurrency hoặc dừng job.

## 13. Cache warm-up và traffic ramp-up

Warm-up không nên kết thúc bằng việc bật 100% traffic ngay lập tức nếu cache vẫn chưa ổn định. Traffic ramp-up cho phép quan sát phản ứng của hệ thống theo từng mức tải.

Một chiến lược ví dụ:

| Giai đoạn | Tỷ lệ traffic minh họa | Điều kiện tiếp tục |
|---|---:|---|
| Smoke test | 1% | Kết nối, query cơ bản và lỗi ở mức bình thường |
| Canary | 5-10% | p95, physical reads và storage latency ổn định |
| Mở rộng | 25-50% | Không có cache churn hoặc wait tăng bất thường |
| Toàn tải | 100% | Throughput và p95/p99 đạt mục tiêu |

Tỷ lệ và thời gian phải tùy quy mô hệ thống. Nếu traffic được điều phối qua load balancer hoặc service mesh, cần tránh dồn tất cả request mới vào một node vừa failover trong khi node còn lại có thể chia tải.

### 13.1. Tránh thundering herd

Thundering herd xảy ra khi nhiều request cùng lúc phát hiện cache miss và đồng loạt truy vấn database để lấy cùng một dữ liệu. Sau restart hoặc failover, cache ứng dụng và cache database cùng lạnh có thể khuếch đại hiện tượng này.

Giảm rủi ro bằng:

- Single-flight hoặc request coalescing ở tầng ứng dụng.
- Jitter cho lịch warm-up và refresh cache.
- Giới hạn số request đồng thời cho cùng cache key.
- TTL có jitter để tránh nhiều key hết hạn cùng lúc.
- Stale-while-revalidate nếu nghiệp vụ cho phép dùng dữ liệu cũ trong thời gian ngắn.
- Rate limit và circuit breaker khi database đang phục hồi.

Các kỹ thuật này phải giữ đúng yêu cầu freshness và quyền truy cập. Không dùng dữ liệu cache cũ cho trạng thái tài chính, tồn kho hoặc quyền truy cập nếu nghiệp vụ yêu cầu đọc nhất quán.

## 14. Đo mức độ phục hồi

Không đánh giá warm-up chỉ bằng thời gian job chạy hoặc hit ratio. Hãy đo các tín hiệu liên quan đến workload thực:

| Nhóm đo | Chỉ số | Ý nghĩa |
|---|---|---|
| Độ trễ | p50, p95, p99 theo endpoint/query | Xác định trải nghiệm thực tế |
| Throughput | Request/transaction mỗi giây | Đánh giá khả năng phục vụ tải |
| Cache | Buffer hit, pages read, cache residency | Theo dõi working set được nạp |
| I/O | Read IOPS, MB/s, latency, queue depth | Phát hiện storage bottleneck |
| Query | Physical reads, logical reads, rows examined | Tách chi phí đọc và xử lý |
| CPU | CPU database, compile/parse CPU | Nhận diện plan cache lạnh hoặc scan |
| Wait | Read wait, page I/O wait, lock wait | Phân biệt I/O và contention |
| Ổn định | Error rate, timeout, retry, replication lag | Kiểm soát ảnh hưởng đến dịch vụ |

### 14.1. Buffer cache hit ratio có giới hạn

Hit ratio cao không bảo đảm hệ thống nhanh. Một workload có thể có hit ratio 99% nhưng 1% miss lại tập trung ở truy vấn quan trọng, đọc page rất chậm. Một workload quét dữ liệu lớn có thể làm hit ratio giảm mà vẫn hoàn thành đúng SLA.

Hãy đọc hit ratio cùng:

- Tổng số logical và physical reads.
- Kích thước và độ chọn lọc của working set.
- Read latency của storage.
- Tần suất chạy và độ trễ của truy vấn quan trọng.
- Buffer eviction và cache churn.

### 14.2. Định nghĩa warm-up complete

Đặt điều kiện hoàn tất dựa trên nhiều tiêu chí, ví dụ:

- Các query trọng yếu có p95 dưới ngưỡng trong một cửa sổ thời gian.
- Physical reads trên mỗi request giảm về gần baseline.
- Storage latency và queue depth ổn định.
- Không có cache churn tăng nhanh.
- CPU và wait events không cho thấy warm-up chiếm quá nhiều tài nguyên.
- Error/timeout rate ở mức chấp nhận được.

Không dùng một ngưỡng hit ratio cố định cho mọi database. Ngưỡng phải gắn với dữ liệu baseline, workload và SLO.

## 15. Kiểm thử cold cache có kiểm soát

Để đánh giá khả năng phục hồi sau restart, cần kiểm thử trong môi trường thử nghiệm hoặc cửa sổ bảo trì đã được phê duyệt. Làm lạnh cache trên production có thể gây suy giảm nghiêm trọng.

Các phép thử nên tách riêng:

1. Cold database buffer cache nhưng OS page cache còn nóng, nếu môi trường cho phép.
2. Cold OS page cache và database cache sau host reboot.
3. Cold plan cache nhưng data cache còn nóng.
4. Failover sang node có buffer pool riêng.
5. Cold application cache trong khi database vẫn nóng.

Không dùng lệnh flush cache tùy tiện trên production. Ví dụ, PostgreSQL có thể bị ảnh hưởng bởi thao tác restart hoặc các công cụ làm lạnh cache; SQL Server có DBCC DROPCLEANBUFFERS và FREEPROCCACHE; Oracle có lệnh flush buffer/shared pool; các thao tác này chỉ nên dùng trong môi trường thử nghiệm có kiểm soát và theo đúng quyền vận hành.

### 15.1. Ghi lại baseline và thời gian phục hồi

Đo:

- Thời gian từ khi database sẵn sàng đến khi truy vấn trọng yếu đạt SLA.
- Thời gian từ khi warm-up bắt đầu đến khi physical reads ổn định.
- IOPS và latency cao nhất trong warm-up.
- Số request bị timeout hoặc retry.
- Tỷ lệ cache hit theo từng giai đoạn.
- Sự khác biệt giữa warm-up bằng công cụ chuyên biệt và workload replay.

Chạy lại nhiều lần với cùng dữ liệu và cấu hình để thấy biến động. Không kết luận từ một lần restart duy nhất.

## 16. Runbook minh họa sau failover

Giả sử primary chuyển sang node B. Node B đã đồng bộ dữ liệu và database đã sẵn sàng, nhưng buffer cache của instance còn lạnh.

**Giai đoạn 1 — Xác nhận an toàn**

- Kiểm tra role primary/replica và trạng thái replication.
- Xác nhận recovery hoàn tất và node có thể nhận workload ghi theo kiến trúc.
- Kiểm tra schema, index và statistics tương ứng với phiên bản ứng dụng.
- Xác nhận connection pool đang trỏ đúng endpoint.

**Giai đoạn 2 — Warm-up ưu tiên**

- Chạy truy vấn read-only cho bảng/index phục vụ login và luồng giao dịch chính.
- Warm dữ liệu gần đây và các lookup reference nhỏ.
- Giới hạn concurrency và I/O.
- Theo dõi physical reads, read latency và p95.

**Giai đoạn 3 — Ramp traffic**

- Chuyển một phần traffic sang node B.
- Theo dõi cache hit, p95/p99, timeout và storage queue.
- Tăng dần traffic khi các chỉ số ổn định.
- Giảm hoặc dừng warm-up nếu production latency tăng.

**Giai đoạn 4 — Hoàn tất**

- Xác nhận các query trọng yếu đạt SLA.
- Theo dõi thêm sau khi traffic đạt 100%.
- Ghi thời gian phục hồi và các mục tiêu warm-up đã dùng.
- Cập nhật runbook cho lần failover tiếp theo.

## 17. Những sai lầm thường gặp

- **Cho rằng database sẵn sàng là cache đã nóng:** recovery hoàn tất không đồng nghĩa working set đã được nạp.
- **Gộp data cache và plan cache:** physical read tăng khác với compile CPU tăng.
- **Warm toàn bộ bảng lớn:** dễ gây cache pollution và I/O storm.
- **Chạy warm-up quá nhiều worker:** tăng tranh chấp storage và đọc lặp.
- **Mở toàn bộ traffic ngay sau restart:** tạo thundering herd và đẩy p99 lên cao.
- **Dùng hit ratio làm tiêu chí duy nhất:** bỏ qua latency của truy vấn quan trọng và storage.
- **Dùng truy vấn có side effect để warm cache:** có thể tạo ghi dữ liệu hoặc kích hoạt nghiệp vụ ngoài ý muốn.
- **Không xét tham số đại diện:** warm-up một tenant không làm nóng dữ liệu của tenant lớn khác.
- **Dùng danh sách page dump cũ sau thay đổi schema/index:** working set đã thay đổi và dữ liệu warm-up có thể không còn hữu ích.
- **Nhầm Query Store với buffer cache:** lịch sử plan không nạp data page vào RAM.
- **Dùng lệnh flush cache trên production để kiểm tra:** có thể làm hệ thống chậm trên diện rộng.
- **Không có ngưỡng dừng:** warm-up tiếp tục dù storage hoặc production latency đã vượt giới hạn.
- **Bỏ qua cache của ứng dụng:** database nóng nhưng Redis/object cache lạnh vẫn có thể tạo tải đột biến.

## 18. Checklist cold cache và warm-up

- [ ] Đã xác định sự kiện làm lạnh cache: restart, host reboot, deploy, failover hay memory pressure.
- [ ] Đã phân biệt application cache, database data cache, plan cache, OS page cache và storage cache.
- [ ] Đã lưu baseline query latency, physical reads, IOPS, CPU và wait events.
- [ ] Đã xác định critical working set từ workload thực tế.
- [ ] Đã đánh giá working set so với RAM khả dụng và memory dành cho query.
- [ ] Warm-up chỉ đọc, có giới hạn concurrency, IOPS, CPU và thời gian.
- [ ] Đã chọn truy vấn/quan hệ đại diện và tham số phù hợp.
- [ ] Đã tránh scan lớn, dữ liệu archive và cache pollution không cần thiết.
- [ ] Đã dùng đúng cơ chế prewarm hoặc buffer pool dump/load của hệ quản trị nếu phù hợp.
- [ ] Đã kiểm tra plan cache riêng với data cache.
- [ ] Có traffic ramp-up và điều kiện dừng khi latency/I/O vượt ngưỡng.
- [ ] Đã kiểm soát thundering herd ở tầng ứng dụng.
- [ ] Đã xác định tiêu chí warm-up complete bằng SLA và nhiều chỉ số.
- [ ] Đã kiểm thử cold cache trong môi trường an toàn.
- [ ] Đã ghi thời gian phục hồi và cập nhật runbook sau restart/failover.

Bộ đệm lạnh sau restart, triển khai hoặc failover là trạng thái cần được dự đoán và quản lý như một phần của vận hành hiệu năng. Hãy xác định lớp cache bị mất, chọn working set có giá trị cao, warm-up bằng workload đọc có giới hạn và mở traffic theo từng bước. Phân biệt data cache với plan cache, theo dõi physical reads cùng độ trễ storage và p95/p99, rồi chỉ coi phục hồi hoàn tất khi workload quan trọng trở lại SLA mà không tạo áp lực tài nguyên mới.
