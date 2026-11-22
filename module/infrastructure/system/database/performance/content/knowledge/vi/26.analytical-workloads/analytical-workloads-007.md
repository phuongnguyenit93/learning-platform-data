# Cô lập tải báo cáo để bảo vệ độ trễ giao dịch

Hệ thống giao dịch trực tuyến (OLTP) và hệ thống phân tích (OLAP) thường dùng chung dữ liệu nhưng có đặc điểm truy cập rất khác nhau. Giao dịch thường đọc hoặc cập nhật một số ít hàng, cần phản hồi nhanh và ổn định. Báo cáo thường quét nhiều hàng, nối nhiều bảng, tổng hợp dữ liệu và có thể chạy trong nhiều giây hoặc nhiều phút. Khi hai loại tải chạy trên cùng tài nguyên, một báo cáo nặng có thể chiếm CPU, bộ nhớ, I/O, worker, buffer cache hoặc khóa, làm p95 và p99 của giao dịch tăng dù câu SQL giao dịch không thay đổi.

Trong DATABASE_PERFORMANCE, cô lập tải báo cáo là thiết kế đường chạy, giới hạn tài nguyên và chính sách điều phối để truy vấn phân tích không làm suy giảm SLO của giao dịch. Cô lập có thể thực hiện bằng replica đọc, kho dữ liệu riêng, resource governance trong database, pool kết nối riêng, admission control, lịch chạy báo cáo và dữ liệu tổng hợp. Không có một cơ chế duy nhất giải quyết mọi tranh chấp: read replica giúp tách phần lớn I/O và CPU nhưng có độ trễ đồng bộ; resource group giới hạn một số loại tài nguyên nhưng không nhất thiết kiểm soát mọi I/O; queue giảm đồng thời nhưng không làm truy vấn tự nhanh hơn.

Mục tiêu là bảo vệ độ trễ và thông lượng của luồng giao dịch trong khi vẫn cung cấp báo cáo với độ mới dữ liệu và thời gian hoàn thành đã thống nhất. Thiết kế cần bắt đầu từ workload và SLO, sau đó chọn mức cô lập phù hợp, đo tác động và kiểm thử khi tải tăng.

## 1. Khác biệt giữa tải giao dịch và tải phân tích

### 1.1. Tải giao dịch OLTP

OLTP phục vụ các thao tác nghiệp vụ thường xuyên như tạo đơn, cập nhật tồn kho, ghi nhận thanh toán, đăng nhập hoặc thay đổi trạng thái. Đặc điểm thường gặp:

- Truy cập một số ít hàng theo khóa chính hoặc chỉ mục có độ chọn lọc cao.
- Transaction ngắn, thường gồm một vài thao tác đọc/ghi.
- Có nhiều request đồng thời và tần suất cao.
- Cần độ trễ thấp, đặc biệt ở p95 và p99.
- Cần tính nhất quán và quy tắc toàn vẹn rõ ràng.
- Một số hàng hoặc khóa có thể trở thành điểm nóng khi nhiều request cùng cập nhật.

Với OLTP, một truy vấn mất thêm 100 ms có thể làm chậm cả chuỗi xử lý của API, giữ connection lâu hơn và tăng hàng đợi ở tầng ứng dụng.

### 1.2. Tải phân tích OLAP

OLAP phục vụ báo cáo, dashboard, phân tích xu hướng, đối soát, dự báo và truy vấn khám phá. Đặc điểm thường gặp:

- Đọc nhiều hàng hoặc nhiều partition.
- Nối nhiều bảng và tổng hợp theo nhóm.
- Dùng sort, hash join, hash aggregate hoặc window function.
- Có thể cần bộ nhớ lớn và spill ra vùng lưu trữ tạm.
- Thời gian chạy có thể dài và kích thước kết quả lớn.
- Nhiều người dùng có thể cùng chạy báo cáo tương tự vào đầu giờ hoặc cuối ngày.

Một báo cáo doanh thu theo tháng có thể đọc hàng chục triệu dòng trong khi API tạo đơn chỉ cần đọc một khách hàng và ghi một đơn. Hai truy vấn dùng chung database có thể cạnh tranh CPU, I/O và buffer cache dù chúng không truy cập cùng một hàng.

### 1.3. Cùng dữ liệu nhưng khác mục tiêu

OLTP tối ưu cho số lượng thao tác nhỏ, transaction ngắn và độ trễ ổn định. OLAP tối ưu cho quét dữ liệu rộng, scan tuần tự, nén và tổng hợp. Một thiết kế chỉ mục hoặc cấu trúc lưu trữ tốt cho OLTP chưa chắc tốt cho báo cáo.

Ví dụ:

| Đặc điểm | OLTP | OLAP |
|---|---|---|
| Truy cập | Point lookup, range nhỏ | Scan lớn, nhiều chiều |
| Ghi | Thường xuyên, transaction ngắn | Thường nạp theo batch hoặc cập nhật tổng hợp |
| Độ trễ | ms đến vài trăm ms theo SLO | giây đến phút tùy báo cáo |
| Chỉ mục | Khóa chọn lọc, lookup và cập nhật nhanh | Scan, partition pruning, columnar hoặc index theo phân tích |
| Đồng thời | Nhiều transaction ngắn | Ít hơn nhưng mỗi truy vấn tiêu thụ tài nguyên lớn |
| Mục tiêu | p95/p99 và throughput giao dịch | thời gian hoàn thành, độ mới và độ đúng của báo cáo |

Không nên áp cùng một ngân sách thời gian hoặc mức ưu tiên cho hai loại tải nếu nghiệp vụ có yêu cầu khác nhau.

## 2. Vì sao báo cáo làm chậm giao dịch?

### 2.1. Tranh chấp CPU

Truy vấn báo cáo có thể dùng nhiều CPU cho join, sort, aggregate, biểu thức, giải nén và xử lý dữ liệu. Nếu database đã gần bão hòa CPU, báo cáo làm các transaction ngắn phải chờ được lập lịch.

Dấu hiệu thường gặp:

- CPU database tăng khi báo cáo bắt đầu.
- Thời gian CPU của truy vấn phân tích cao.
- Throughput giao dịch giảm hoặc p95 tăng cùng thời điểm.
- Wait event liên quan đến CPU scheduling hoặc runnable queue tăng tùy hệ quản trị.

### 2.2. Tranh chấp I/O

Full scan hoặc range scan lớn có thể tạo lượng đọc lớn. Khi storage đạt giới hạn IOPS hoặc throughput, truy vấn giao dịch đọc một vài trang cũng phải chờ lâu hơn.

Một báo cáo có thể không gây lock contention nhưng vẫn làm chậm OLTP do đọc cạnh tranh trên cùng volume, storage pool hoặc thiết bị. Vì vậy, chỉ kiểm tra lock wait sẽ bỏ sót một nguyên nhân quan trọng.

### 2.3. Áp lực bộ nhớ và spill

Hash join, sort và aggregate cần workspace memory. Nếu truy vấn nhận nhiều memory grant hoặc vượt bộ nhớ được cấp, engine có thể spill dữ liệu ra tempdb, temporary tablespace hoặc file tạm. Spill tạo thêm I/O và làm tăng thời gian chạy.

Nếu nhiều báo cáo chạy cùng lúc, tổng workspace memory có thể lớn dù từng truy vấn riêng lẻ có vẻ hợp lý. Database có thể phải giảm memory grant của truy vấn khác, tăng spill hoặc chịu memory pressure.

### 2.4. Cache pollution

Một scan lớn có thể đưa nhiều page ít được tái sử dụng vào buffer cache, đẩy các page nóng của giao dịch ra ngoài. Sau báo cáo, các truy vấn OLTP phải đọc lại page từ storage.

Tác động có thể kéo dài sau khi báo cáo kết thúc. Đo physical reads và cache behavior trước, trong và sau báo cáo để xác định cache pollution.

### 2.5. Khóa và transaction dài

Một báo cáo đọc lâu có thể giữ snapshot hoặc khóa tùy isolation level và engine. Nếu báo cáo dùng locking read hoặc chạy trong transaction dài, nó có thể chặn cập nhật hoặc trì hoãn việc dọn phiên bản dữ liệu.

Với MVCC, truy vấn đọc thường giảm blocking với writer nhưng không miễn phí: snapshot lâu có thể giữ phiên bản cũ, làm tăng vacuum/undo pressure hoặc tạo xung đột với quá trình apply log trên replica. Cần hiểu chính sách isolation và read consistency của hệ quản trị.

### 2.6. Kết nối và worker

Một truy vấn báo cáo chạy lâu giữ connection và worker lâu hơn giao dịch thông thường. Nếu báo cáo dùng chung connection pool với API, một số báo cáo có thể chiếm hết connection sẵn có, làm request OLTP phải chờ ở ứng dụng ngay cả khi database còn tài nguyên.

Pool riêng giúp phân bổ giới hạn kết nối theo workload. Tuy nhiên, pool riêng không tự cô lập CPU hoặc I/O nếu cả hai pool vẫn truy cập cùng một database instance.

## 3. Xác định SLO và ngân sách cho từng loại tải

Trước khi chọn kiến trúc, xác định rõ điều gì cần được bảo vệ:

- Độ trễ p50, p95 và p99 của API giao dịch.
- Throughput giao dịch và tỷ lệ lỗi.
- Thời gian tối đa của transaction.
- Tỷ lệ timeout và lock wait được chấp nhận.
- Thời gian hoàn thành báo cáo.
- Độ mới dữ liệu báo cáo, ví dụ trễ tối đa 1 phút, 5 phút hoặc 1 giờ.
- Khung giờ báo cáo được phép chạy.
- Mức đồng thời của người dùng báo cáo.

Ví dụ một hệ thống thương mại điện tử có thể đặt:

| Chỉ tiêu | Luồng giao dịch | Báo cáo |
|---|---|---|
| Mục tiêu độ trễ | p95 dưới 200 ms | phần lớn báo cáo dưới 30 giây |
| Mức đồng thời | nhiều request ngắn | tối đa 4 truy vấn nặng cùng lúc |
| Độ mới dữ liệu | dữ liệu primary hiện hành | trễ tối đa 2 phút |
| Ưu tiên | cao | trung bình |
| Timeout | theo deadline API | theo loại báo cáo |

Các con số chỉ minh họa. SLO phải được thống nhất với nghiệp vụ và xác nhận bằng tải thực tế. Nếu báo cáo tài chính cần dữ liệu đồng bộ ngay tại thời điểm chốt sổ, độ mới dữ liệu có thể quan trọng hơn việc chạy trên replica có lag.

### 3.1. Phân loại truy vấn báo cáo

Không phải mọi truy vấn đọc đều là OLAP. Có thể phân loại:

- Lookup đọc một vài hàng phục vụ màn hình nghiệp vụ.
- Báo cáo tương tác nhỏ với filter chọn lọc và thời gian chạy ngắn.
- Báo cáo tổng hợp đọc nhiều partition hoặc nhiều tháng.
- Export lớn tạo file với hàng triệu dòng.
- Ad hoc query do người dùng tự thiết kế.

Mỗi loại cần giới hạn đồng thời, timeout, mức ưu tiên và nguồn dữ liệu khác nhau. Một truy vấn lookup trên replica có thể vẫn cần độ trễ thấp; một export dài nên chạy nền và trả kết quả qua file/object storage.

## 4. Các mức cô lập tải

Có thể cô lập theo nhiều lớp, từ thay đổi ít đến thay đổi kiến trúc lớn:

1. Giới hạn concurrency, timeout và queue ở ứng dụng.
2. Tách connection pool và workload identity.
3. Dùng resource group hoặc workload management của database.
4. Dùng read replica để chuyển tải đọc.
5. Dùng kho dữ liệu hoặc hệ thống phân tích riêng.
6. Dùng bảng tổng hợp, materialized view hoặc data mart để giảm truy vấn trên dữ liệu giao dịch.

Các lớp có thể kết hợp. Ví dụ báo cáo tương tác đọc từ replica, export lớn chạy trên warehouse, trong khi resource group giới hạn truy vấn ad hoc trên replica.

## 5. Tách tải bằng read replica

Read replica là bản sao dữ liệu được cập nhật từ primary thông qua replication. Ứng dụng có thể định tuyến truy vấn đọc sang replica, giảm CPU và I/O đọc trên primary.

Kiến trúc khái quát:

~~~mermaid
flowchart LR
    API[API giao dịch] --> P[Primary database]
    P -->|WAL / binlog / redo| R[Read replica]
    P -->|CDC hoặc ETL| W[Data warehouse]
    Report[Dashboard và báo cáo] --> R
    Export[Export lớn và phân tích sâu] --> W
~~~

Primary tiếp tục xử lý transaction và phát log thay đổi. Replica áp dụng log để cập nhật dữ liệu đọc. Warehouse nhận dữ liệu qua CDC/ETL và có thể tổ chức lại schema cho truy vấn phân tích.

### 5.1. Lợi ích

- Tách phần lớn CPU và I/O đọc khỏi primary.
- Có thể tạo nhiều replica cho các nhóm workload khác nhau.
- Cho phép tối ưu cấu hình và index đọc theo truy vấn báo cáo nếu kiến trúc hỗ trợ.
- Giảm nguy cơ một báo cáo scan lớn ảnh hưởng trực tiếp tới transaction trên primary.
- Có thể triển khai reporting pool riêng và giới hạn concurrency độc lập.

### 5.2. Giới hạn của replica

Replica không phải lúc nào cũng có dữ liệu mới nhất. Với asynchronous replication, có khoảng thời gian giữa commit trên primary và apply trên replica. Báo cáo có thể đọc dữ liệu cũ hơn primary.

Replica cũng tiêu thụ CPU và I/O khi apply log. Nếu báo cáo nặng chiếm toàn bộ tài nguyên replica, replication apply có thể chậm và lag tăng. Với một số engine, truy vấn đọc dài còn có thể xung đột với việc apply thay đổi hoặc giữ phiên bản dữ liệu.

Không định tuyến tất cả SELECT sang replica một cách mù quáng. Các thao tác đọc sau ghi (read-your-writes), kiểm tra trạng thái thanh toán hoặc tồn kho cần thấy commit mới có thể phải đọc primary hoặc dùng cơ chế chờ replica bắt kịp.

### 5.3. Chính sách read-after-write

Một luồng có thể:

1. Ghi đơn hàng trên primary.
2. Nhận xác nhận commit.
3. Ngay sau đó đọc đơn hàng để hiển thị trạng thái.

Nếu bước 3 đi tới replica đang lag, người dùng có thể chưa thấy bản ghi vừa tạo. Các lựa chọn:

- Đọc primary trong một khoảng thời gian sau ghi.
- Gắn session consistency token hoặc commit position và chờ replica áp dụng tới vị trí đó nếu engine hỗ trợ.
- Chỉ chuyển báo cáo có yêu cầu freshness phù hợp sang replica.
- Trả trạng thái đã ghi từ kết quả transaction thay vì đọc lại ngay.

Chính sách phải được thể hiện rõ trong data access layer, không để mỗi endpoint tự đoán.

### 5.4. Giám sát replication lag

Theo dõi:

- Thời gian trễ apply.
- Khoảng cách log nhận được và log đã áp dụng.
- Throughput replication.
- Queue hoặc backlog log.
- Trạng thái replica và lỗi apply.
- Độ trễ truy vấn báo cáo.

Đặt ngưỡng định tuyến: nếu lag vượt mức freshness cho phép, dừng gửi báo cáo yêu cầu dữ liệu mới sang replica hoặc chuyển sang nguồn phù hợp. Không chuyển mọi báo cáo về primary khi replica lag mà không kiểm soát; điều đó có thể tạo thêm tải lên primary đúng lúc hệ thống đang căng.

## 6. Tách tải bằng kho dữ liệu phân tích

Khi báo cáo cần scan dữ liệu lớn, truy vấn ad hoc hoặc lịch sử nhiều năm, read replica có thể vẫn chưa đủ. Data warehouse hoặc analytical database riêng tạo ranh giới tài nguyên và mô hình dữ liệu phù hợp hơn cho OLAP.

### 6.1. Luồng CDC/ETL

- CDC thu thập thay đổi từ transaction log hoặc cơ chế tương đương.
- ETL/ELT chuyển dữ liệu, làm sạch, chuẩn hóa và nạp vào warehouse.
- Data mart hoặc bảng fact/dimension hỗ trợ truy vấn theo chiều phân tích.
- Dashboard và công cụ BI truy vấn warehouse thay vì primary.

### 6.2. Lợi ích

- Tách CPU, memory, I/O và storage khỏi database giao dịch.
- Cho phép dùng columnar storage, partitioning, compression và clustering phù hợp scan.
- Có thể lưu lịch sử dài mà không làm bảng OLTP phình to.
- Có thể chạy truy vấn ad hoc và export lớn mà không chiếm connection của API.
- Dữ liệu có thể được chuẩn hóa thành mô hình phân tích dễ dùng hơn.

### 6.3. Chi phí và giới hạn

- Cần vận hành pipeline CDC/ETL và theo dõi lỗi nạp.
- Dữ liệu thường có độ trễ so với primary.
- Cần quản lý schema evolution, backfill và dữ liệu đến muộn.
- Có chi phí storage, compute và quản trị riêng.
- Phải xác định quy tắc xóa, bảo mật, masking và retention ở warehouse.

Warehouse phù hợp khi khối lượng và độ phức tạp phân tích đủ lớn để biện minh cho một nền tảng riêng. Không nhất thiết phải xây warehouse chỉ để chạy một báo cáo nhỏ mỗi ngày.

## 7. Resource governance trên database dùng chung

Nếu chưa thể tách replica hoặc warehouse, có thể giới hạn tài nguyên theo user, role, workload group hoặc service class. Mục tiêu là đảm bảo truy vấn giao dịch có ưu tiên và truy vấn báo cáo không thể chiếm toàn bộ tài nguyên.

### 7.1. PostgreSQL

PostgreSQL có các thiết lập theo role/database/session như statement_timeout, idle_in_transaction_session_timeout, work_mem và giới hạn kết nối. Có thể tạo role riêng cho báo cáo:

~~~sql
CREATE ROLE report_reader LOGIN;
GRANT CONNECT ON DATABASE appdb TO report_reader;
GRANT USAGE ON SCHEMA reporting TO report_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO report_reader;

ALTER ROLE report_reader SET default_transaction_read_only = on;
ALTER ROLE report_reader SET statement_timeout = '30s';
ALTER ROLE report_reader SET idle_in_transaction_session_timeout = '30s';
~~~

Các quyền SELECT chỉ áp dụng trên schema reporting trong ví dụ; cần cấp quyền cho bảng mới theo chính sách phù hợp. default_transaction_read_only là mặc định phiên, không thay thế phân quyền: role không nên có quyền ghi nếu mục tiêu là chỉ đọc.

work_mem là giới hạn cho từng thao tác sort/hash chứ không phải một ngân sách tổng cho toàn server. Một truy vấn có nhiều sort/hash node, chạy song song hoặc có nhiều session có thể dùng tổng bộ nhớ lớn hơn nhiều giá trị work_mem. Không tăng work_mem toàn cục để làm nhanh một báo cáo mà không tính concurrency.

PostgreSQL không có resource governor tích hợp tương đương SQL Server để áp hard CPU/I/O quota riêng cho role trong mọi cấu hình. Có thể kết hợp role, connection limit, statement timeout, pool riêng, giới hạn concurrency ở ứng dụng, cgroup/container và replica.

### 7.2. SQL Server

SQL Server Resource Governor cho phép phân loại session vào workload group và resource pool, sau đó đặt giới hạn hoặc mức ưu tiên cho CPU, memory grant và một số tài nguyên theo phiên bản/edition. Có thể dùng login, application name hoặc session context làm classifier.

Thiết kế thường gồm:

- Workload group riêng cho báo cáo.
- Resource pool giới hạn phần tài nguyên được cấp.
- Classifier đưa session báo cáo vào đúng group.
- Chính sách kiểm soát memory grant và mức đồng thời theo workload.

Resource Governor không làm truy vấn kém hiệu quả trở nên tốt; nó giúp giới hạn ảnh hưởng và phân phối tài nguyên. Cần kiểm tra edition, phiên bản, cách phân loại connection và hành vi khi classifier không khớp.

### 7.3. Oracle Database

Oracle Database Resource Manager hỗ trợ consumer group, plan và directive để phân bổ CPU, giới hạn mức đồng thời hoặc điều phối session theo chính sách. Có thể gán user báo cáo vào consumer group riêng và ưu tiên giao dịch.

Các cấu hình thường cần:

- Consumer group cho OLTP và reporting.
- Resource plan được kích hoạt đúng thời điểm.
- Directive giới hạn CPU hoặc số session chạy đồng thời theo mục tiêu.
- Mapping user/service/module sang consumer group.
- Theo dõi session bị queue, switch group hoặc bị giới hạn.

Resource Manager cần được thiết kế và kiểm thử theo workload, quyền quản trị và phiên bản. Không mặc định rằng một directive kiểm soát đồng thời cả CPU, I/O, memory và mọi loại wait.

### 7.4. MySQL

MySQL có Resource Groups để gán thread vào nhóm CPU với mức ưu tiên và affinity phù hợp trong các phiên bản hỗ trợ. Resource Groups chủ yếu điều phối CPU; không nên coi chúng là quota tổng quát cho I/O, memory hoặc số truy vấn đồng thời.

Có thể kết hợp:

- User riêng cho reporting với quyền chỉ đọc.
- Connection pool riêng và giới hạn số session.
- max_execution_time cho SELECT phù hợp phiên bản.
- Lịch chạy và admission control ở ứng dụng.
- Read replica hoặc kho dữ liệu riêng khi workload đủ lớn.

### 7.5. Nguyên tắc chung

Resource governance cần một danh tính workload ổn định. Nếu mọi ứng dụng dùng chung một database user và không truyền application name hoặc session context, database khó phân biệt OLTP với reporting.

Tạo user/role riêng, pool riêng và metric riêng giúp định tuyến, giám sát và áp chính sách rõ ràng. Không cấp quyền ghi cho role báo cáo nếu chỉ cần đọc.

## 8. Admission control và giới hạn đồng thời báo cáo

Admission control quyết định có cho truy vấn mới bắt đầu hay phải chờ/từ chối. Thay vì cho 100 báo cáo nặng chạy đồng thời, có thể chỉ cho 4 truy vấn chạy và đưa phần còn lại vào queue có giới hạn.

### 8.1. Vì sao giới hạn concurrency có ích?

Giả sử một báo cáo tiêu thụ 2 CPU core và 8 GB workspace trong thời gian cao điểm. Nếu cho 10 báo cáo chạy đồng thời, tổng nhu cầu có thể vượt xa tài nguyên. Một queue nhỏ giữ các báo cáo chưa chạy, bảo vệ OLTP và tránh memory pressure.

Giới hạn phải dựa trên benchmark. Một truy vấn lookup nhẹ có thể được phép đồng thời nhiều hơn báo cáo scan lớn. Có thể phân loại theo loại báo cáo, chi phí ước lượng, thời gian lịch sử hoặc kích thước kết quả.

### 8.2. Queue có giới hạn

Một queue báo cáo nên xác định:

- Số job tối đa đang chờ.
- Số job tối đa đang chạy.
- Thời gian chờ tối đa trước khi từ chối hoặc hết hạn.
- Deadline của từng loại báo cáo.
- Chính sách ưu tiên hoặc công bằng giữa người dùng.
- Cách hủy job khi người dùng không còn cần kết quả.
- Retry có giới hạn khi replica hoặc warehouse tạm thời không sẵn sàng.

Không để hàng đợi vô hạn. Nếu tốc độ tạo báo cáo cao hơn tốc độ hoàn tất trong thời gian dài, backlog sẽ tăng mãi.

### 8.3. Backpressure

Khi queue gần đầy, ứng dụng có thể:

- Từ chối request mới với thông báo thử lại sau.
- Giới hạn tốc độ theo user hoặc tenant.
- Chuyển export sang xử lý nền.
- Trả kết quả cache hoặc kết quả gần nhất nếu nghiệp vụ cho phép.
- Yêu cầu người dùng thu hẹp khoảng thời gian hoặc filter.

Backpressure giúp bảo vệ hệ thống khỏi overload. Không nên để request đồng bộ chờ nhiều phút trong thread HTTP nếu tác vụ phù hợp với job nền.

## 9. Tối ưu truy vấn báo cáo trước khi tăng tài nguyên

Cô lập không thay thế tối ưu SQL. Một truy vấn có thể gây hại ngay cả khi chạy trên replica nếu nó đọc dữ liệu không cần thiết hoặc tạo spill lớn.

### 9.1. Giới hạn phạm vi dữ liệu

Đưa điều kiện thời gian và tenant rõ ràng vào truy vấn:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= :from_time
  AND created_at < :to_time
  AND tenant_id = :tenant_id
GROUP BY customer_id;
~~~

Khoảng thời gian nửa mở tránh lỗi ở ranh giới timestamp và có thể hỗ trợ partition pruning nếu bảng partition theo created_at. Cần kiểm tra kiểu dữ liệu, timezone và index thực tế.

### 9.2. Chỉ lấy cột cần thiết

Tránh SELECT * khi báo cáo chỉ cần một số cột. Projection nhỏ giảm lượng dữ liệu đọc, truyền qua mạng, memory grant và kích thước kết quả trung gian.

### 9.3. Aggregate trước khi join nếu đúng ngữ nghĩa

Với bảng fact lớn, có thể tổng hợp ở cấp cần thiết trước khi nối dimension. Tuy nhiên, phép viết lại phải bảo toàn cardinality, NULL, duplicate và filter. So sánh actual plan và kết quả trước/sau.

### 9.4. Partitioning và pruning

Partition theo thời gian hoặc khóa nghiệp vụ có thể giúp báo cáo chỉ đọc vùng dữ liệu cần thiết. Điều kiện truy vấn phải phù hợp partition key và optimizer phải thực hiện pruning. Partitioning không tự làm truy vấn nhanh nếu nó vẫn phải đọc mọi partition.

### 9.5. Materialized view và bảng tổng hợp

Nếu cùng một báo cáo chạy thường xuyên trên dữ liệu lớn, tính trước kết quả theo giờ/ngày/tenant có thể giảm scan và aggregate lặp lại. Cần định nghĩa:

- Tần suất refresh.
- Độ trễ dữ liệu được chấp nhận.
- Cách cập nhật tăng dần.
- Xử lý dữ liệu đến muộn hoặc giao dịch bị đảo.
- Cơ chế đồng bộ và kiểm tra kết quả với nguồn.

Materialized view có thể làm tăng chi phí ghi hoặc refresh; hãy đo tổng workload chứ không chỉ thời gian SELECT báo cáo.

## 10. Nhất quán và độ mới của dữ liệu báo cáo

Chuyển báo cáo sang replica hoặc warehouse làm xuất hiện câu hỏi dữ liệu mới đến đâu và một báo cáo có nhìn thấy snapshot nhất quán không.

### 10.1. Độ mới dữ liệu

Độ mới (freshness) là khoảng thời gian giữa thay đổi trên nguồn và thời điểm thay đổi đó xuất hiện ở nơi báo cáo đọc.

Ví dụ:

- Dashboard vận hành có thể chấp nhận trễ 30 giây.
- Báo cáo quản trị hằng ngày có thể chấp nhận trễ 15 phút.
- Đối soát thanh toán cuối ngày có thể cần mốc dữ liệu đã chốt rõ ràng.

Không tự giả định replica luôn chỉ trễ vài mili giây. Lag có thể tăng mạnh khi primary ghi nhiều, replica thiếu tài nguyên hoặc báo cáo cạnh tranh với apply thread.

### 10.2. Snapshot nhất quán

Một báo cáo nối nhiều bảng cần đọc dữ liệu từ một góc nhìn nhất quán. Nếu các bảng được cập nhật trong lúc báo cáo chạy và mỗi statement dùng snapshot khác nhau, kết quả có thể phản ánh các thời điểm khác nhau tùy isolation level.

Chọn mức isolation phù hợp:

- Snapshot/consistent read nếu engine hỗ trợ và cần một góc nhìn ổn định.
- Transaction ngắn hoặc export snapshot có thời hạn cho báo cáo dài.
- Mốc dữ liệu hoặc batch ID cố định trong warehouse.

Transaction snapshot kéo dài có chi phí: giữ phiên bản dữ liệu, tăng undo/vacuum pressure hoặc gây conflict trên standby tùy engine. Không mở transaction trên primary trong nhiều phút chỉ để phân trang báo cáo nếu có lựa chọn khác.

### 10.3. Báo cáo có thể tái lập

Với báo cáo tài chính hoặc kiểm toán, nên lưu mốc dữ liệu, tham số, phiên bản định nghĩa báo cáo và thời điểm chạy. Warehouse có thể dùng batch watermark hoặc snapshot identifier để tái tạo kết quả. Một con số tổng hợp mà không biết nó được tính trên trạng thái dữ liệu nào khó có thể đối chiếu về sau.

## 11. Tách connection pool và đường định tuyến

Ứng dụng nên phân biệt datasource hoặc pool cho OLTP và reporting:

- Pool OLTP có giới hạn phù hợp với SLO giao dịch.
- Pool reporting có giới hạn nhỏ hơn và acquire timeout rõ ràng.
- Reporting connection dùng role chỉ đọc.
- Truy vấn báo cáo được route đến replica hoặc warehouse theo freshness policy.
- Export dài chạy qua worker nền thay vì giữ request HTTP.

Pool riêng không phải resource isolation hoàn chỉnh nếu cùng trỏ tới primary. Nó chỉ kiểm soát số kết nối và hàng đợi ở ứng dụng. Muốn tách CPU/I/O cần resource governance, replica hoặc hệ thống phân tích riêng.

### 11.1. Định tuyến theo loại truy vấn

Một lớp routing có thể phân loại:

| Loại truy vấn | Nguồn đọc đề xuất | Ghi chú |
|---|---|---|
| Đọc sau ghi cần thấy dữ liệu mới | Primary | Bảo đảm read-your-writes |
| Lookup nghiệp vụ cần freshness cao | Primary hoặc replica có consistency token | Theo dõi lag |
| Dashboard chấp nhận trễ ngắn | Read replica | Có timeout và concurrency limit |
| Báo cáo lịch sử lớn | Warehouse | Tối ưu cho scan và aggregate |
| Export rất lớn | Job nền trên warehouse | Ghi kết quả ra object/file storage |
| Truy vấn ad hoc | Sandbox/warehouse hoặc nhóm tài nguyên thấp | Có quota và queue |

Không route chỉ dựa vào việc SQL bắt đầu bằng SELECT. Một SELECT có thể gọi function có side effect, dùng locking clause hoặc phụ thuộc session state. Cần phân loại theo hợp đồng truy vấn, quyền và workload.

## 12. Bảo vệ OLTP bằng chính sách ưu tiên

Khi tài nguyên khan hiếm, transaction nghiệp vụ quan trọng cần được bảo vệ. Chính sách có thể gồm:

- Ưu tiên cao hơn cho role hoặc workload group OLTP.
- Giới hạn CPU/memory/concurrency cho reporting.
- Hạn chế thời gian chạy báo cáo đồng bộ.
- Không cho reporting mở transaction ghi.
- Giới hạn số hàng hoặc khoảng thời gian truy vấn.
- Chặn truy vấn không có filter bắt buộc.
- Tạm dừng báo cáo khi lag, I/O hoặc p99 OLTP vượt ngưỡng.

Ưu tiên không nên tạo starvation vô hạn cho báo cáo. Có thể đặt quota tối thiểu hoặc lịch chạy riêng để báo cáo vẫn hoàn tất trong thời gian cho phép.

### 12.1. Timeout theo loại workload

Không dùng cùng một statement timeout cho API và báo cáo. Ví dụ:

- API lookup: vài trăm mili giây đến vài giây theo SLO.
- Báo cáo tương tác: vài chục giây.
- Export nền: deadline dài hơn nhưng có giới hạn tài nguyên và khả năng tiếp tục.

Đây là ví dụ phân loại, không phải giá trị mặc định. Timeout phải phù hợp với loại truy vấn, độ mới dữ liệu và deadline của client.

### 12.2. Hủy truy vấn khi không còn nhu cầu

Nếu người dùng đóng dashboard hoặc hủy export, ứng dụng nên gửi cancel tới driver/server và giải phóng connection đúng cách. Cần xác nhận transaction đã rollback hoặc ở trạng thái sạch trước khi trả connection về pool.

Không để truy vấn báo cáo tiếp tục chạy sau khi request đã hết hạn nếu kết quả không còn được sử dụng. Nhưng cũng không hủy job nền chỉ vì client HTTP đã ngắt kết nối nếu nghiệp vụ yêu cầu job tiếp tục.

## 13. Theo dõi tác động lên giao dịch và báo cáo

Đo riêng hai nhóm workload và đối chiếu cùng thời điểm:

| Nhóm | Chỉ số |
|---|---|
| OLTP | p50/p95/p99, throughput, error rate, transaction duration, lock wait |
| Reporting | runtime, rows scanned, bytes read, queue wait, timeout, concurrency |
| Database | CPU, memory, IOPS, read/write latency, temp spill, worker utilization |
| Connection | active/idle/pending theo từng pool, acquire latency, usage time |
| Replica/CDC | replication lag, apply throughput, backlog, freshness |
| Warehouse | query slot/concurrency, scan bytes, queue time, storage/compute cost |

### 13.1. Đo baseline

Trước khi thay đổi, đo OLTP trong giờ cao điểm với và không có báo cáo. Ghi lại p95/p99, throughput, physical reads, CPU, I/O latency và lock wait.

Nếu có thể, chạy báo cáo thử nghiệm trên bản sao dữ liệu tương đương. Không tạo tải scan lớn trên production chỉ để đo mà không có cửa sổ và giới hạn được phê duyệt.

### 13.2. So sánh trong cùng điều kiện

Sau khi tách workload, dùng cùng bộ truy vấn, tham số, dữ liệu và mức concurrency. So sánh:

- p95/p99 OLTP có trở về mục tiêu không?
- Throughput giao dịch có ổn định hơn không?
- Báo cáo có hoàn thành trong SLA không?
- Replica lag hoặc warehouse freshness có nằm trong ngưỡng không?
- Tổng CPU/I/O và chi phí compute có tăng hợp lý không?
- Có phát sinh queue hoặc timeout ở tầng mới không?

Một giải pháp chỉ chuyển hàng đợi từ primary sang replica mà không giới hạn tải có thể chưa giải quyết được vấn đề tổng thể.

## 14. Ví dụ kiến trúc cho hệ thống đơn hàng

Yêu cầu:

- API tạo và cập nhật đơn hàng cần p95 dưới 200 ms.
- Dashboard vận hành cần dữ liệu trễ không quá 2 phút.
- Báo cáo doanh thu theo quý đọc dữ liệu nhiều năm.
- Export chi tiết có thể tạo hàng triệu dòng.

Thiết kế:

1. API ghi và đọc sau ghi đi tới primary.
2. Dashboard đọc từ read replica, dùng reporting pool giới hạn và timeout ngắn hơn export.
3. Replica lag được theo dõi; khi vượt 2 phút, dashboard hiển thị trạng thái dữ liệu cũ hoặc chuyển theo chính sách đã định.
4. Báo cáo doanh thu nhiều năm đọc từ warehouse có bảng fact theo ngày và dimension khách hàng/sản phẩm.
5. Export lớn chạy dưới dạng background job, có queue và concurrency limit; kết quả lưu vào object storage.
6. Role báo cáo chỉ có quyền SELECT trên schema phù hợp.
7. OLTP và reporting có metric riêng, được theo dõi trong cùng dashboard vận hành.

### 14.1. Ví dụ truy vấn báo cáo có phạm vi

~~~sql
SELECT
    product_id,
    SUM(quantity) AS units_sold,
    SUM(net_amount) AS net_revenue
FROM fact_order_items
WHERE order_date >= :from_date
  AND order_date < :to_date
  AND tenant_id = :tenant_id
GROUP BY product_id;
~~~

Truy vấn giới hạn khoảng ngày và tenant, chỉ chọn cột cần thiết và tổng hợp trên fact table. Warehouse có thể partition theo order_date và clustering/index theo tenant_id tùy công nghệ. Cần kiểm tra plan và số bytes/rows scan; việc dùng warehouse không tự bảo đảm truy vấn hiệu quả.

### 14.2. Điều kiện mở rộng tải

Trước khi tăng số người dùng dashboard hoặc export, kiểm tra:

- OLTP p95/p99 không xấu đi.
- Replica lag dưới ngưỡng freshness.
- Reporting queue còn trong giới hạn.
- CPU/I/O của replica còn khoảng dự phòng.
- Warehouse concurrency và chi phí nằm trong ngân sách.
- Export có timeout, retry và cơ chế hủy rõ ràng.

## 15. Quy trình triển khai cô lập tải báo cáo

1. **Phân loại workload:** tách OLTP, dashboard, báo cáo tương tác, export và ad hoc.
2. **Định nghĩa SLO:** đặt mục tiêu độ trễ giao dịch, throughput, thời gian báo cáo và freshness.
3. **Đo tranh chấp hiện tại:** CPU, I/O, memory grant, spill, cache, lock, connection và queue.
4. **Xác định nguồn gây ảnh hưởng:** truy vấn nào, thời điểm nào và loại tài nguyên nào bị chiếm.
5. **Chọn mức cô lập:** pool riêng, admission control, resource group, replica hoặc warehouse.
6. **Thiết kế routing:** xác định truy vấn nào phải đọc primary, replica hay warehouse.
7. **Định nghĩa consistency:** read-after-write, replica lag, snapshot và mốc dữ liệu báo cáo.
8. **Giới hạn báo cáo:** concurrency, queue, timeout, scan range, result size và quyền chỉ đọc.
9. **Tối ưu SQL:** filter, projection, partition pruning, aggregate, index hoặc materialized view.
10. **Kiểm thử tải hỗn hợp:** chạy giao dịch và báo cáo đồng thời với mức tải đại diện và burst.
11. **Đo lại SLO:** xác nhận p95/p99 OLTP, throughput, report runtime và freshness.
12. **Triển khai theo giai đoạn:** chuyển một phần báo cáo, theo dõi rồi mở rộng.
13. **Chuẩn bị rollback:** định nghĩa cách ngừng routing, giảm concurrency hoặc quay về nguồn đọc cũ khi có lỗi.
14. **Theo dõi liên tục:** cảnh báo lag, queue growth, spill, I/O saturation và OLTP latency.

## 16. Những sai lầm thường gặp

- **Chuyển mọi SELECT sang replica:** có thể vi phạm read-after-write hoặc consistency yêu cầu.
- **Cho rằng replica không thể bị quá tải:** báo cáo nặng vẫn có thể làm lag và tăng I/O trên replica.
- **Dùng pool riêng nhưng vẫn trỏ cùng primary:** chỉ giới hạn connection, chưa cô lập CPU/I/O.
- **Chỉ tăng tài nguyên database:** không giải quyết query scan quá rộng hoặc concurrency không giới hạn.
- **Chạy mọi báo cáo đồng thời:** memory grant, spill và I/O có thể làm toàn hệ thống chậm.
- **Để queue vô hạn:** backlog tăng lâu dài và request hết deadline.
- **Tăng work_mem toàn cục để một báo cáo nhanh hơn:** nhiều session và nhiều plan node có thể nhân mức dùng bộ nhớ.
- **Mở transaction snapshot quá lâu trên primary:** giữ phiên bản cũ, tăng áp lực cleanup hoặc blocking tùy engine.
- **Không đo replication lag:** báo cáo có thể hiển thị dữ liệu cũ mà không được nhận biết.
- **Dùng warehouse nhưng không kiểm soát pipeline:** dữ liệu có thể thiếu, đến muộn hoặc sai sau schema change.
- **Không giới hạn quyền báo cáo:** truy vấn ngoài dự kiến có thể ghi dữ liệu hoặc truy cập bảng nhạy cảm.
- **Chỉ đo thời gian báo cáo:** bỏ qua p95/p99 của giao dịch trong cùng thời điểm.
- **Không thử tải hỗn hợp:** hai workload riêng lẻ chạy tốt không có nghĩa chạy chung vẫn tốt.
- **Không có chính sách cancel:** truy vấn vẫn tiếp tục chiếm tài nguyên sau khi người dùng không cần kết quả.

## 17. Checklist cô lập tải phân tích

- [ ] Đã phân loại OLTP, dashboard, báo cáo lớn, export và ad hoc.
- [ ] Đã xác định SLO p95/p99 cho giao dịch và thời gian hoàn thành báo cáo.
- [ ] Đã định nghĩa độ mới dữ liệu được chấp nhận cho từng báo cáo.
- [ ] Đã đo CPU, I/O, memory grant, spill, cache, lock và connection khi tải hỗn hợp.
- [ ] Đã xác định báo cáo có thể chạy trên primary, replica hay warehouse.
- [ ] Read replica có chính sách lag và read-after-write rõ ràng.
- [ ] Reporting pool tách khỏi OLTP pool và có giới hạn toàn fleet.
- [ ] Role báo cáo chỉ có quyền cần thiết, ưu tiên quyền đọc.
- [ ] Có admission control, queue limit, timeout và backpressure.
- [ ] Resource governance được cấu hình theo workload identity nếu dùng chung instance.
- [ ] Truy vấn có filter, projection và giới hạn phạm vi dữ liệu.
- [ ] Báo cáo lặp lại đã được đánh giá materialized view hoặc bảng tổng hợp.
- [ ] Snapshot và transaction dài có giới hạn và chính sách cleanup.
- [ ] Export lớn chạy nền, có thể tiếp tục hoặc hủy an toàn.
- [ ] Đã kiểm thử đồng thời OLTP và báo cáo dưới tải đại diện.
- [ ] Đã xác nhận p95/p99 OLTP không suy giảm ngoài SLO.
- [ ] Đã xác nhận report runtime, freshness, replica lag và queue nằm trong mục tiêu.
- [ ] Có dashboard, cảnh báo và quy trình rollback khi cô lập tải gặp sự cố.

Cô lập tải báo cáo bảo vệ giao dịch bằng cách tách đường chạy, giới hạn tài nguyên và kiểm soát mức đồng thời. Read replica hoặc warehouse tạo ranh giới tài nguyên rõ hơn; resource governance và admission control giúp điều phối khi còn dùng chung database. Mọi lựa chọn đều có đánh đổi về độ mới dữ liệu, chi phí, độ phức tạp và thời gian hoàn thành báo cáo. Hãy đo tải hỗn hợp, xác định freshness và SLO trước khi chọn kiến trúc, rồi xác minh rằng p95/p99 của giao dịch được bảo vệ trong khi báo cáo vẫn hoàn thành đúng cam kết.
