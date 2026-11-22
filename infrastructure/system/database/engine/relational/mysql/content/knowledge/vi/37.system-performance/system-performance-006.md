# innodb_io_capacity, background flush và đặc tính thiết bị lưu trữ

InnoDB ghi thay đổi vào redo log trước để bảo đảm khả năng phục hồi, sau đó các trang dữ liệu đã thay đổi được ghi dần từ buffer pool xuống data files. Công việc ghi trang nền này được gọi là background flushing. Nếu flush quá chậm, trang bẩn và checkpoint age có thể tăng đến mức InnoDB phải flush gấp, làm truy vấn foreground bị chậm. Nếu flush quá mạnh, hoạt động nền lại tranh chấp I/O với truy vấn đọc/ghi đang phục vụ ứng dụng.

Hai biến cấu hình quan trọng để điều tiết công việc nền là **innodb_io_capacity** và **innodb_io_capacity_max**. Chúng giúp InnoDB ước lượng khả năng I/O mà thiết bị có thể dành cho các tác vụ nền như flush dirty pages và merge change buffer. Giá trị phù hợp phụ thuộc vào loại thiết bị, IOPS và throughput thực tế, độ trễ, workload, cấu hình lưu trữ và mức I/O mà các tiến trình khác đang sử dụng.

Bài học thuộc chương **Hiệu năng hệ thống** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, hiểu background flushing và đặc tính thiết bị giúp điều chỉnh cấu hình InnoDB dựa trên bằng chứng, giữ checkpoint ổn định và bảo vệ latency của workload.

## 1. Đường đi của một thay đổi trong InnoDB

Khi transaction sửa một bản ghi, InnoDB thay đổi trang tương ứng trong buffer pool và đánh dấu trang đó là dirty page. Thông tin redo mô tả thay đổi được ghi vào redo log để InnoDB có thể phục hồi sau crash. Trang dữ liệu trong tablespace có thể được ghi xuống storage sau đó.

Quá trình này tách hai loại công việc:

- **Redo logging** ghi lại thông tin cần thiết để phục hồi thay đổi. Nó là một phần của đường commit và chịu ảnh hưởng bởi cấu hình durability.
- **Data page flushing** ghi các dirty page từ buffer pool xuống data files. InnoDB có thể thực hiện việc này nền, theo nhu cầu cấp trang sạch, áp lực checkpoint và các ngưỡng flushing.

Vì vậy, COMMIT thành công không có nghĩa mọi dirty page của transaction đã được ghi ngay xuống vị trí cuối cùng trong data file. Khi cấu hình durability phù hợp, redo log đã được ghi/flush theo quy tắc commit; dirty page có thể được ghi sau đó. Khi crash, InnoDB dùng redo để roll forward những thay đổi cần thiết và xử lý recovery.

Sơ đồ khái quát:

~~~text
Ứng dụng UPDATE / INSERT / DELETE
              |
              v
       InnoDB buffer pool
       (trang dữ liệu dirty)
              |
              +----------------------+
              |                      |
              v                      v
         Redo log              Background flush
      (log records)            (dirty data pages)
              |                      |
              v                      v
      Commit durability          Data files
      và crash recovery          / tablespaces
~~~

Redo log và data page flushing liên quan chặt chẽ nhưng không phải cùng một luồng I/O. Tăng innodb_io_capacity không làm redo log commit tự động bền vững hơn và cũng không thay thế cấu hình innodb_flush_log_at_trx_commit hoặc sync_binlog.

## 2. Dirty page, flush list và LRU flushing

Một trang trong buffer pool trở thành dirty khi nội dung trong bộ nhớ khác nội dung đã ghi xuống data file. InnoDB cần ghi dirty page xuống storage để giải phóng bộ nhớ, duy trì checkpoint và bảo đảm có đủ trang sạch phục vụ truy vấn.

Có hai mục tiêu flushing thường cần phân biệt:

**LRU flushing** tạo thêm trang sạch ở đầu danh sách LRU để buffer pool có thể nạp trang mới khi cần. Nếu không có trang sạch sẵn và truy vấn cần đọc một trang mới, foreground thread có thể phải chờ InnoDB flush một dirty page.

**Flush-list flushing** ghi các dirty page theo thứ tự phù hợp với tiến độ checkpoint. Các trang được sắp xếp theo thông tin LSN liên quan đến lần sửa đổi gần nhất. Khi các trang cũ hơn được ghi xuống data files, checkpoint có thể tiến lên và giải phóng không gian redo log đã không còn cần cho crash recovery.

Hai mục tiêu này có thể tạo ra các mẫu I/O khác nhau. LRU flushing tập trung duy trì nguồn trang sạch; flush-list flushing giúp kiểm soát checkpoint age. Khi xem thống kê, đừng suy luận mọi lần flush đều phục vụ cùng một mục đích.

Các page cleaner thread của InnoDB thực hiện phần lớn công việc flush dirty page. InnoDB cũng có các hoạt động nền khác như purge undo history và merge change buffer. innodb_io_capacity là một tham số ngân sách I/O cho nhiều tác vụ nền, không chỉ một câu lệnh ghi cụ thể.

## 3. Checkpoint và áp lực redo log

Redo log lưu thông tin thay đổi để phục hồi. Mỗi thay đổi được gắn với Log Sequence Number (LSN). Có thể hiểu checkpoint là mốc mà InnoDB đã bảo đảm các thay đổi trước mốc đó cần thiết cho recovery đã được ghi xuống data files.

Checkpoint age thường được diễn giải gần đúng bằng:

\[
\text{Checkpoint age} =
\text{Current LSN} - \text{Last checkpoint LSN}
\]

Khi ứng dụng tạo redo nhanh hơn tốc độ InnoDB có thể flush dirty page, checkpoint age tăng. Nếu nó tiến gần giới hạn redo log capacity, InnoDB cần tăng cường flushing để tránh cạn không gian redo có thể tái sử dụng. Điều này có thể làm I/O nền tăng mạnh và ảnh hưởng latency foreground.

Một số dấu hiệu cần quan sát:

- Dirty page percentage tăng liên tục thay vì ổn định quanh một vùng.
- Checkpoint age tăng nhanh hoặc thường xuyên tiến gần giới hạn redo capacity.
- I/O write latency tăng trong lúc background flushing tăng.
- Foreground thread phải chờ trang sạch; Innodb_buffer_pool_wait_free tăng.
- Throughput ghi của ứng dụng giảm khi InnoDB thực hiện flush gấp.
- Log hoặc InnoDB status cho thấy checkpoint tiến chậm so với tốc độ sinh redo.

Không nên chỉ nhìn tỷ lệ dirty pages để kết luận checkpoint pressure. Một buffer pool có tỷ lệ dirty cao vẫn có thể ổn định nếu flush rate đủ nhanh và checkpoint age còn xa giới hạn. Ngược lại, dirty percentage vừa phải nhưng workload sinh redo rất nhanh cũng có thể gây áp lực checkpoint.

## 4. innodb_io_capacity điều khiển điều gì?

innodb_io_capacity biểu diễn ước lượng số thao tác I/O mỗi giây mà InnoDB có thể dành cho các tác vụ nền. Tham số này ảnh hưởng đến mức độ InnoDB chủ động thực hiện các công việc như:

- Flush dirty pages từ buffer pool xuống data files.
- Thực hiện một phần công việc merge change buffer.
- Điều tiết hoạt động nền liên quan đến duy trì trang sạch và checkpoint.

Đây là một giá trị ngân sách/ước lượng dành cho background work. Nó không phải giới hạn cứng tổng IOPS của thiết bị, không phải giới hạn tất cả I/O do MySQL phát sinh và không điều khiển trực tiếp mọi lần đọc do truy vấn foreground yêu cầu.

Ví dụ, nếu đặt innodb_io_capacity bằng 2.000, không có nghĩa toàn bộ MySQL chỉ được thực hiện tối đa 2.000 I/O mỗi giây. Truy vấn đọc, ghi đồng bộ redo, binlog, backup, filesystem và các tiến trình khác vẫn tạo I/O theo cơ chế riêng. Giá trị này giúp InnoDB ước lượng khả năng thực hiện tác vụ nền.

Xem giá trị hiện tại:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_io_capacity';
~~~

Hoặc:

~~~sql
SELECT
    @@global.innodb_io_capacity AS io_capacity,
    @@global.innodb_io_capacity_max AS io_capacity_max;
~~~

Giá trị mặc định và phạm vi hợp lệ phụ thuộc phiên bản MySQL. Hãy đọc giá trị thực tế của server và tài liệu đúng phiên bản trước khi thay đổi; không sao chép một con số từ máy chủ khác mà chưa đo thiết bị và workload.

## 5. innodb_io_capacity_max là giới hạn cho giai đoạn flush mạnh

innodb_io_capacity_max xác định mức I/O nền tối đa mà InnoDB có thể sử dụng khi cần flush mạnh hơn mức thông thường do innodb_io_capacity định hướng.

Có thể hình dung:

- innodb_io_capacity là ngân sách hoạt động nền thông thường.
- innodb_io_capacity_max là mức trần cao hơn có thể được sử dụng trong các giai đoạn cần tăng tốc flushing.

Nếu capacity_max quá thấp so với nhu cầu thực tế, InnoDB có thể khó bắt kịp tốc độ sinh dirty page hoặc redo trong thời điểm tải ghi tăng. Nếu quá cao so với khả năng thiết bị hoặc phần I/O còn lại dành cho ứng dụng, background flush có thể chiếm dụng hàng đợi storage, làm latency đọc/ghi foreground tăng.

Xem cả hai biến:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_io_capacity',
    'innodb_io_capacity_max'
);
~~~

Không đặt capacity_max bằng một con số lớn chỉ để làm dirty page giảm nhanh. Cần kiểm tra thiết bị có duy trì được mức IOPS/throughput đó trong thời gian đủ dài và latency có còn nằm trong SLO hay không.

Một cấu hình có capacity thấp nhưng capacity_max rất cao có thể tạo ra những đợt flush mạnh khi áp lực checkpoint xuất hiện. Nếu storage có giới hạn burst hoặc bị throttling sau một khoảng ngắn, các đợt này có thể làm latency biến động mạnh. Hãy quan sát cả mức trung bình và p95/p99 của I/O latency.

## 6. Adaptive flushing và các ngưỡng dirty page

InnoDB không chỉ flush theo một con số cố định. Adaptive flushing điều chỉnh tốc độ flush dựa trên tình trạng redo log, tốc độ sinh redo và áp lực checkpoint.

Các biến liên quan gồm:

| Biến | Vai trò |
|---|---|
| innodb_adaptive_flushing | Bật/tắt cơ chế adaptive flushing |
| innodb_adaptive_flushing_lwm | Ngưỡng thấp của redo log capacity để kích hoạt hành vi adaptive flushing theo định nghĩa của phiên bản |
| innodb_max_dirty_pages_pct | Mục tiêu/giới hạn tỷ lệ dirty page trong buffer pool mà InnoDB dùng để điều tiết flushing |
| innodb_max_dirty_pages_pct_lwm | Ngưỡng dirty-page thấp để bắt đầu flush sớm hơn theo cấu hình |
| innodb_io_capacity | Ngân sách I/O nền thông thường |
| innodb_io_capacity_max | Mức I/O nền tối đa cho các giai đoạn cần flush mạnh |

Kiểm tra giá trị thực tế:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_adaptive_flushing',
    'innodb_adaptive_flushing_lwm',
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm',
    'innodb_io_capacity',
    'innodb_io_capacity_max'
);
~~~

Adaptive flushing giúp tránh tình trạng chờ đến khi dirty page hoặc redo log gần đầy mới bắt đầu ghi mạnh. Nó có thể tăng tốc flush khi redo generation nhanh hoặc checkpoint age tiến gần giới hạn.

Không nên tắt adaptive flushing chỉ vì thấy I/O nền cao. I/O đó có thể đang ngăn checkpoint pressure trở thành sự cố foreground. Trước khi thay đổi, hãy xác định dirty page trend, redo generation, checkpoint age, storage latency và mức tải ứng dụng.

Các ngưỡng và hành vi chi tiết có thể thay đổi theo phiên bản. Đừng coi innodb_max_dirty_pages_pct là mục tiêu mà server phải giữ chính xác ở mọi thời điểm; InnoDB có thể flush vì nhiều lý do và dirty percentage có thể dao động.

## 7. innodb_flush_sync và những đợt flush do checkpoint

innodb_flush_sync điều khiển việc InnoDB có được phép bỏ qua innodb_io_capacity trong các đợt I/O mạnh do checkpoint hay không. Khi bật, InnoDB có thể flush vượt mức capacity thông thường để bắt kịp checkpoint pressure.

Điều này giải thích vì sao quan sát thực tế đôi khi thấy background I/O vượt quá con số innodb_io_capacity. Tham số capacity không phải hard throttle cho mọi hoàn cảnh.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_sync';
~~~

Nếu storage bị giới hạn IOPS hoặc có latency rất nhạy, hãy quan sát hành vi flush khi checkpoint age tăng. Không vội tắt innodb_flush_sync chỉ để ép I/O nằm dưới một ngưỡng cố định; việc đó có thể khiến checkpoint tiến quá chậm và tạo rủi ro cạn redo capacity.

Khi điều chỉnh tham số này, cần hiểu rõ trade-off giữa việc bảo vệ latency ngắn hạn và khả năng duy trì checkpoint ổn định. Thử nghiệm trên staging với workload ghi đại diện và có kế hoạch rollback.

## 8. Đặc tính của HDD, SSD, NVMe và storage mạng

innodb_io_capacity phải phản ánh khả năng thực tế của hệ thống lưu trữ, không chỉ tên loại thiết bị.

| Loại storage | Đặc tính thường gặp | Tác động đến InnoDB |
|---|---|---|
| HDD | Random I/O chậm do seek; throughput tuần tự có thể tốt; latency biến động theo vị trí đầu đọc | Flush nhiều page rời rạc có thể tốn seek; ghi các page lân cận có thể hữu ích |
| SATA SSD | Random I/O nhanh hơn HDD, latency thấp hơn, throughput và IOPS có giới hạn theo thiết bị | Có thể chịu nhiều flush ngẫu nhiên hơn HDD; vẫn cần đo khi queue depth tăng |
| NVMe SSD | Độ trễ thấp, nhiều queue và khả năng song song cao | Có thể hỗ trợ I/O nền lớn hơn, nhưng workload đồng thời vẫn có thể làm tăng tail latency |
| Cloud block volume | IOPS và throughput thường phụ thuộc loại volume, kích thước, provisioned limit, burst credit hoặc quota | Có thể bị throttling; benchmark ngắn chưa chắc phản ánh hiệu năng bền vững |
| SAN/RAID | Hiệu năng phụ thuộc số ổ, stripe, controller, cache, write policy và tải dùng chung | Không thể cộng IOPS danh nghĩa của từng ổ mà bỏ qua controller, parity và contention |

HDD thường nhạy với random write và seek. Việc flush các trang lân cận có thể giảm số lần seek trong một số workload. SSD/NVMe không có cơ cấu đầu đọc cơ học nên lợi ích của việc flush neighbors thường thấp hơn; nhiều hệ thống SSD chọn tắt neighbor flushing. Tuy vậy, quyết định phải dựa trên benchmark và giá trị mặc định của phiên bản.

Storage mạng hoặc cloud có thể đạt IOPS cao trong thời gian ngắn nhờ burst, nhưng sau khi hết credit sẽ giảm mạnh. Một volume có thể giới hạn cả IOPS lẫn throughput MB/s; workload ghi các page 16 KB có thể chạm giới hạn IOPS trước, còn ghi tuần tự hoặc backup có thể chạm giới hạn throughput trước.

Ngoài loại thiết bị, cần xem:

- I/O latency p50, p95 và p99.
- IOPS đọc/ghi thực tế và throughput MB/s.
- Queue depth và thời gian chờ I/O.
- Giới hạn của volume, controller hoặc cloud tier.
- Các workload khác đang dùng chung thiết bị.
- Filesystem, mount option, cache và hành vi fsync.
- Vị trí data files, redo logs, binary logs, relay logs và backup.

Không suy ra IOPS khả dụng cho InnoDB bằng cách cộng số IOPS quảng cáo của các ổ mà chưa đo toàn bộ đường đi từ MySQL đến storage.

## 9. innodb_flush_neighbors và việc gom các trang lân cận

innodb_flush_neighbors điều khiển việc InnoDB có flush thêm các dirty page lân cận khi flush một page hay không. Giá trị thường được định nghĩa:

- 0: không flush neighbor pages.
- 1: flush các dirty page lân cận trong cùng extent.
- 2: flush các dirty page lân cận trong cùng extent và các extent liền kề.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_flush_neighbors';
~~~

Với HDD, neighbor flushing có thể giảm seek bằng cách ghi các trang gần nhau trong một lần hoạt động. Với SSD và NVMe, lợi ích này thường ít hơn vì truy cập ngẫu nhiên nhanh; flush thêm page không cần thiết có thể làm tăng write I/O. Giá trị phù hợp phụ thuộc loại storage, workload và phiên bản MySQL.

Không thay đổi biến chỉ dựa trên quy tắc HDD = 1 và SSD = 0. Storage RAID, SAN hoặc cloud có thể có đặc tính khác với thiết bị vật lý đơn. Hãy thử trong điều kiện có thể tái tạo, đo cả write throughput và foreground latency.

## 10. Đo dirty pages và hoạt động flushing

Có thể lấy snapshot các biến InnoDB sau:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_pages_data',
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_free',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_data_writes',
    'Innodb_data_written',
    'Innodb_data_fsyncs',
    'Innodb_data_pending_writes',
    'Innodb_data_pending_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
)
ORDER BY VARIABLE_NAME;
~~~

Một số biến là gauge, một số là counter. Hãy phân loại trước khi tính delta:

| Metric | Loại | Cách diễn giải |
|---|---|---|
| Innodb_buffer_pool_pages_dirty | Gauge | Số dirty page hiện tại |
| Innodb_buffer_pool_pages_free | Gauge | Số page sạch/free hiện tại |
| Innodb_buffer_pool_pages_data | Gauge | Số page thuộc data trong buffer pool |
| Innodb_buffer_pool_pages_flushed | Counter | Số page đã flush tích lũy |
| Innodb_buffer_pool_wait_free | Counter | Số lần InnoDB phải chờ page sạch |
| Innodb_data_writes | Counter | Số thao tác ghi data file theo status variable |
| Innodb_data_written | Counter | Lượng byte ghi data theo status variable |
| Innodb_data_fsyncs | Counter | Số lần fsync data file |
| Innodb_data_pending_writes | Gauge | Số write I/O đang chờ |
| Innodb_data_pending_fsyncs | Gauge | Số fsync đang chờ |
| Innodb_os_log_written | Counter | Lượng byte redo log đã ghi |
| Innodb_log_waits | Counter | Số lần log buffer phải chờ flush để tiếp tục |

Tên biến và tính khả dụng có thể khác theo phiên bản. Nếu một biến không tồn tại, kiểm tra SHOW GLOBAL STATUS LIKE 'tên biến' và tài liệu đúng phiên bản; không tự tạo metric thay thế có ý nghĩa khác.

Để theo dõi tỷ lệ dirty pages, cần biết tổng số page của buffer pool. Có thể lấy:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_total'
);
~~~

Tỷ lệ dirty page gần đúng:

\[
\text{Dirty page percentage} =
\frac{\text{Pages dirty}}{\text{Pages total}} \times 100
\]

Đây là tỷ lệ tại thời điểm chụp. Hãy vẽ thành time series và xem xu hướng, không chỉ đọc một mẫu.

Delta Innodb_buffer_pool_pages_flushed trong 60 giây cho biết số page flush trong khoảng đó. Nếu page size là 16 KiB, có thể ước lượng lượng dữ liệu page được flush bằng delta pages × page size, nhưng số byte I/O vật lý có thể khác do filesystem, doublewrite, write coalescing và storage layer.

## 11. Quan sát checkpoint và trạng thái InnoDB

Lệnh chẩn đoán cơ bản:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Trong mysql client, dạng dọc dễ đọc hơn:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tập trung vào phần LOG, BUFFER POOL AND MEMORY, FILE I/O và TRANSACTIONS. Tùy phiên bản, output có thể hiển thị:

- Log sequence number hiện tại.
- Log flushed up to.
- Last checkpoint at.
- Pending log flushes hoặc pending checkpoint writes.
- Buffer pool size, free buffers, database pages và modified db pages.
- Pending reads/writes và số lần flush.
- I/O thread activity.

So sánh LSN hiện tại với checkpoint LSN để hiểu checkpoint age. Nếu checkpoint tiến chậm trong khi LSN tăng nhanh, hệ thống có thể đang tạo redo nhanh hơn khả năng ghi dirty page.

SHOW ENGINE INNODB STATUS là snapshot tại thời điểm truy vấn. Để biết xu hướng, lưu output theo khoảng đo hoặc trích các giá trị quan trọng vào hệ thống giám sát. Không so sánh hai output mà không ghi timestamp, server_uuid, uptime và cấu hình redo log tương ứng.

Nếu cần xem chi tiết hơn, có thể kiểm tra các bảng InnoDB metrics trong INFORMATION_SCHEMA.INNODB_METRICS khi chúng khả dụng và được bật. Các metric này có thể có trạng thái enable/reset riêng; hãy xác minh tên và định nghĩa trên phiên bản thực tế trước khi xây dashboard phụ thuộc vào chúng.

## 12. Redo log durability khác với background page flushing

Không nên dùng innodb_io_capacity để giải thích trực tiếp thời gian COMMIT. Đường commit còn chịu ảnh hưởng của redo log write/flush, binary log và group commit.

Hai biến cần hiểu riêng:

**innodb_flush_log_at_trx_commit**

- 1: ghi redo log và flush xuống storage theo mỗi transaction commit, theo cơ chế group commit khi phù hợp.
- 2: ghi redo log vào file ở mỗi commit, nhưng flush vật lý thường theo chu kỳ khoảng một giây.
- 0: ghi và flush redo log theo chu kỳ khoảng một giây, thay vì ở mỗi commit.

Giá trị 0 hoặc 2 có thể làm mất các transaction gần nhất khi OS hoặc máy chủ gặp sự cố, dù MySQL process crash có thể có hành vi khác. Lựa chọn phụ thuộc yêu cầu durability và khả năng chấp nhận mất dữ liệu.

**sync_binlog**

Điều khiển tần suất đồng bộ binary log xuống storage. Giá trị 1 thường được dùng khi cần độ bền binlog cao theo từng commit; các giá trị khác thay đổi trade-off giữa hiệu năng và khả năng mất các event binlog khi crash.

innodb_io_capacity không thay thế hai biến durability này. Không giảm durability để che một vấn đề background flush hoặc storage latency nếu chưa có đánh giá rủi ro dữ liệu và phê duyệt nghiệp vụ.

Khi điều tra COMMIT chậm, hãy tách các thành phần: redo log write/fsync, binlog sync, group commit, storage latency, lock wait và hoạt động page flushing. Một hệ thống có dirty page ổn định vẫn có thể COMMIT chậm do fsync latency.

## 13. Tác động của redo log capacity và workload ghi

Redo log capacity xác định lượng redo mà InnoDB có thể giữ trước khi phải thu hồi không gian bằng checkpoint. Capacity lớn hơn có thể giúp hấp thụ các đợt ghi đột biến và giảm nhu cầu flush gấp trong thời gian ngắn. Tuy nhiên, nó không làm storage ghi nhanh hơn và không loại bỏ nhu cầu flush dirty page.

Ở các phiên bản MySQL 8.0 mới, innodb_redo_log_capacity là biến quan trọng để quản lý dung lượng redo log. Các phiên bản cũ hơn sử dụng các biến log file size và số lượng redo log file theo cách cấu hình khác. Hãy kiểm tra phiên bản trước khi đưa lệnh vào runbook.

Khi tăng redo capacity, cân nhắc:

- Thời gian cần để checkpoint tiến đến mức ổn định.
- Lượng dirty page có thể tích lũy trong buffer pool.
- Thời gian recovery sau crash.
- Dung lượng filesystem dành cho redo log.
- Tốc độ sinh redo trong workload cao điểm.
- Mức IOPS và throughput bền vững của storage.

Một redo log lớn có thể làm hệ thống chịu được burst lâu hơn nhưng cũng có thể làm recovery cần xử lý nhiều redo hơn. Đây là quyết định capacity planning, không phải thay thế việc chọn innodb_io_capacity phù hợp.

## 14. Tác động của storage queue và workload dùng chung

IOPS danh nghĩa không thể hiện đầy đủ trải nghiệm của truy vấn. Khi nhiều I/O cùng chờ trên một thiết bị, queue depth tăng và latency có thể tăng nhanh. Background flushing có thể cạnh tranh với:

- Random read từ buffer pool miss.
- Data page write và doublewrite.
- Redo log write/flush.
- Binary log và relay log.
- Backup, snapshot, export và filesystem scan.
- Replication apply hoặc job batch.
- Các tiến trình khác trên cùng volume hoặc storage pool.

Ví dụ, một volume cloud có thể đạt 10.000 IOPS nhưng chỉ duy trì throughput nhất định. Nếu background flush ghi page nhỏ với queue sâu, foreground random read có thể tăng p99 latency dù tổng IOPS chưa chạm giới hạn. Ngược lại, backup tuần tự có thể chiếm throughput MB/s nhưng không làm IOPS đạt giới hạn.

Tách data files và redo logs sang volume riêng có thể giảm contention trong một số kiến trúc, nhưng không bảo đảm hai volume không chia sẻ cùng backend storage pool hoặc giới hạn instance. Đo cả host và dịch vụ lưu trữ.

Đừng dùng mỗi CPU utilization để đánh giá MySQL đang khỏe. Một máy chủ có CPU thấp nhưng storage latency cao vẫn có thể có truy vấn chậm do I/O wait. Đối chiếu metric MySQL với iostat, hệ thống giám sát OS hoặc telemetry của cloud volume.

## 15. Chọn innodb_io_capacity theo phép đo

Không có một con số phù hợp cho mọi ổ SSD, NVMe hoặc cloud volume. Quy trình chọn giá trị nên bắt đầu từ workload và I/O budget thực tế:

1. Đo IOPS và throughput bền vững của storage trong điều kiện tương đương production.
2. Xác định phần I/O mà InnoDB có thể dành cho background tasks sau khi tính foreground workload, redo/binlog, backup và các tiến trình dùng chung.
3. Đo baseline dirty pages, pages flushed, checkpoint age, buffer pool wait_free và I/O latency.
4. Chọn giá trị innodb_io_capacity ban đầu thận trọng, tương ứng với phần I/O nền có thể duy trì.
5. Đặt innodb_io_capacity_max cao hơn capacity thông thường nhưng vẫn nằm trong giới hạn thiết bị và latency budget.
6. Quan sát khi workload ghi bình thường và trong burst đại diện.
7. Điều chỉnh từng bước nhỏ, so sánh dirty page trend, checkpoint age, foreground latency và storage queue.
8. Ghi lại giá trị trước/sau, thời điểm, node, workload và cách rollback.

Một thiết bị có thông số 50.000 IOPS không có nghĩa InnoDB nên được cấp 50.000 cho innodb_io_capacity. Một phần IOPS phải dành cho truy vấn foreground, redo, binlog, backup và các workload khác. Ngoài ra, benchmark random read có thể khác đáng kể benchmark write, kích thước block, queue depth và tỷ lệ read/write.

Nếu background flush quá thấp, dirty page và checkpoint age có thể tăng. Nếu quá cao, latency của truy vấn có thể tăng do storage contention. Giá trị tốt là giá trị giữ được checkpoint ổn định mà không làm suy giảm SLO của ứng dụng.

## 16. Quy trình tuning có kiểm soát

Trước khi thay đổi:

- Xác nhận đúng node, server_uuid, MySQL version và vai trò.
- Ghi lại innodb_io_capacity, innodb_io_capacity_max, adaptive flushing và flush-neighbor settings.
- Chụp dirty page percentage, checkpoint LSN/age, buffer pool waits và status counters.
- Lưu baseline IOPS, throughput, p95/p99 latency và queue depth ở storage layer.
- Ghi lại workload: QPS, write rate, batch, backup, replication apply và giờ cao điểm.
- Xác định người phê duyệt, thời gian quan sát và điều kiện rollback.

Kiểm tra biến hiện tại:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'innodb_io_capacity',
    'innodb_io_capacity_max',
    'innodb_adaptive_flushing',
    'innodb_adaptive_flushing_lwm',
    'innodb_flush_sync',
    'innodb_flush_neighbors',
    'innodb_max_dirty_pages_pct',
    'innodb_max_dirty_pages_pct_lwm'
);
~~~

Với biến dynamic trên phiên bản hỗ trợ, có thể thay đổi runtime:

~~~sql
SET GLOBAL innodb_io_capacity = 1500;
SET GLOBAL innodb_io_capacity_max = 3000;
~~~

Các con số trên chỉ là ví dụ minh họa cú pháp, không phải khuyến nghị cho mọi máy chủ. Kiểm tra quyền, phạm vi dynamic, giá trị hợp lệ và tài liệu đúng phiên bản trước khi chạy. Thay đổi runtime có thể không tồn tại sau restart.

Nếu muốn lưu cấu hình cho lần khởi động sau, MySQL 8.0 có cơ chế SET PERSIST trên các biến hỗ trợ:

~~~sql
SET PERSIST innodb_io_capacity = 1500;
SET PERSIST innodb_io_capacity_max = 3000;
~~~

Không dùng SET PERSIST trong bài thực hành trên production nếu chưa có change record và phê duyệt. Cần biết cách xóa persisted override và cách khôi phục giá trị trước đó theo quy trình cấu hình của hệ thống.

Sau khi thay đổi, quan sát đủ lâu để workload đi qua các chu kỳ flush và checkpoint. So sánh cùng loại tải, không chỉ so một phút ngay sau thay đổi với một khoảng cao điểm khác.

## 17. Đọc kết quả sau tuning

| Quan sát | Diễn giải có thể có | Bước tiếp theo |
|---|---|---|
| Dirty pages giảm dần, checkpoint age ổn định, foreground latency không tăng | Flush budget có thể phù hợp hơn | Tiếp tục theo dõi qua giờ cao điểm |
| Dirty pages và checkpoint age vẫn tăng trong workload ghi | Background flush có thể chưa bắt kịp hoặc storage đang bị giới hạn | Xem capacity, max, adaptive flushing, IOPS và throughput |
| Dirty pages giảm nhưng p95/p99 latency tăng | Flush nền có thể đang tranh chấp storage với foreground | Giảm budget hoặc kiểm tra storage queue và workload dùng chung |
| Innodb_buffer_pool_wait_free tăng | Có thời điểm thiếu page sạch cho nhu cầu đọc | Kiểm tra LRU flushing, dirty page, storage latency và buffer pool pressure |
| Pending writes/fsync tăng kéo dài | Storage hoặc đường ghi có thể đang tắc nghẽn | Đối chiếu OS I/O latency, queue depth, redo/binlog và thiết bị |
| Checkpoint age thấp nhưng COMMIT vẫn chậm | Nguyên nhân có thể ở redo/binlog fsync hoặc lock wait | Kiểm tra durability settings, fsync latency, group commit và locks |
| I/O nền vượt innodb_io_capacity | Có thể do innodb_flush_sync hoặc nhu cầu checkpoint đặc biệt | Kiểm tra cấu hình và InnoDB status; không mặc định là lỗi |

Không thay đổi nhiều biến cùng lúc. Nếu vừa tăng capacity, vừa đổi flush_neighbors và redo capacity, bạn sẽ khó xác định thay đổi nào tạo ra kết quả. Mỗi thử nghiệm cần một giả thuyết, metric thành công, điều kiện dừng và kế hoạch rollback.

## 18. Đặc điểm lưu trữ và các biến liên quan khác

Ngoài io_capacity, một số biến có thể ảnh hưởng đến đường I/O:

**innodb_flush_method** liên quan cách InnoDB mở và thực hiện I/O đối với data files và, tùy hệ điều hành/phiên bản, các file log. Các lựa chọn và mặc định phụ thuộc nền tảng. Không đổi từ buffered I/O sang direct I/O hoặc ngược lại chỉ dựa trên một bài benchmark đơn lẻ; cần xem OS cache, filesystem, workload và khuyến nghị phiên bản.

**innodb_flush_neighbors** ảnh hưởng việc ghi các trang lân cận như mục 9. Đánh giá theo random I/O và đặc tính thiết bị.

**innodb_doublewrite** bảo vệ khỏi partial page write trong các tình huống mất điện/crash. Một số storage hoặc cấu hình có hỗ trợ atomic write có thể có cơ chế riêng theo phiên bản. Không tắt doublewrite chỉ để tăng benchmark khi chưa xác minh bảo vệ dữ liệu và hỗ trợ của nền tảng.

**innodb_flush_log_at_trx_commit** và **sync_binlog** ảnh hưởng durability của redo/binlog, không phải ngân sách background page flushing. Đánh giá riêng theo RPO và yêu cầu phục hồi.

**innodb_redo_log_capacity** ảnh hưởng lượng redo có thể giữ trước khi cần checkpoint tiến lên. Capacity lớn hơn có thể hấp thụ burst, nhưng không sửa được storage có throughput bền vững thấp.

**innodb_buffer_pool_size** quyết định quy mô vùng cache dữ liệu/index trong bộ nhớ. Tăng buffer pool có thể giảm đọc vật lý nếu working set phù hợp, nhưng không trực tiếp làm background flush nhanh hơn và cũng có thể làm tăng lượng dirty page tối đa có thể tích lũy.

Đọc các biến hiện tại trước khi thay đổi và ghi rõ phiên bản hỗ trợ. Không xem một biến cấu hình là cách thay thế cho đo lường ở tầng storage.

## 19. Bài thực hành: quan sát flush trên workload ghi

Dùng môi trường thử nghiệm hoặc replica được phép tạo tải. Không chạy benchmark ghi trực tiếp lên production volume nếu chưa có kế hoạch và phê duyệt.

**Phần A — Ghi baseline cấu hình**

~~~sql
SELECT
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version,
    @@global.innodb_io_capacity AS io_capacity,
    @@global.innodb_io_capacity_max AS io_capacity_max,
    @@global.innodb_adaptive_flushing AS adaptive_flushing,
    @@global.innodb_flush_neighbors AS flush_neighbors;
~~~

Lưu thêm các biến adaptive flushing, dirty-page threshold, flush_sync và redo capacity nếu phiên bản hỗ trợ.

**Phần B — Chụp counter và gauge**

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Innodb_buffer_pool_pages_dirty',
    'Innodb_buffer_pool_pages_total',
    'Innodb_buffer_pool_pages_flushed',
    'Innodb_buffer_pool_wait_free',
    'Innodb_data_writes',
    'Innodb_data_written',
    'Innodb_data_fsyncs',
    'Innodb_data_pending_writes',
    'Innodb_data_pending_fsyncs',
    'Innodb_os_log_written',
    'Innodb_log_waits'
);
~~~

Ghi timestamp, server_uuid và Uptime. Chờ một khoảng đo xác định rồi chụp lại. Tính delta cho counter và đọc gauge như giá trị trạng thái.

**Phần C — Quan sát InnoDB và storage**

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Ghi lại LSN, checkpoint, dirty pages, pending writes và các phần FILE I/O. Ở tầng OS hoặc cloud, ghi IOPS đọc/ghi, throughput, queue depth và p95/p99 latency cùng thời điểm.

**Phần D — Tạo workload đại diện**

Dùng workload ghi có kích thước batch, tỷ lệ insert/update và độ phân tán key tương tự hệ thống cần đánh giá. Không dùng một vòng lặp ghi đơn giản rồi suy rộng kết quả sang production nếu workload thực có secondary index, transaction lớn, replication và backup đồng thời.

**Phần E — Thử thay đổi từng bước**

Trên môi trường thử nghiệm, thay đổi innodb_io_capacity hoặc innodb_io_capacity_max theo một bước có kiểm soát. Giữ các biến khác không đổi. Chạy lại cùng workload và cùng thời lượng.

**Phần F — Kết luận**

So sánh:

- Dirty page trend và checkpoint age.
- Pages flushed/second và redo bytes/second.
- Innodb_buffer_pool_wait_free.
- Pending writes/fsync.
- Storage IOPS, throughput, queue depth và tail latency.
- Foreground transaction latency, p95/p99 và throughput.
- Tác động đến workload đọc, ghi và replication.

Chỉ giữ cấu hình mới nếu nó cải thiện mục tiêu đã xác định mà không làm xấu các chỉ số bảo vệ khác. Ghi lại giá trị cũ, giá trị mới, điều kiện thử và cách rollback.

## 20. Những lỗi tuning thường gặp

**Coi innodb_io_capacity là giới hạn IOPS toàn server.** Nó là ngân sách/ước lượng cho tác vụ nền, không chặn mọi I/O foreground hoặc I/O của hệ điều hành.

**Đặt capacity bằng IOPS quảng cáo của volume.** Thiết bị còn phải phục vụ truy vấn, redo, binlog, backup và workload khác; cloud storage còn có giới hạn throughput hoặc burst.

**Đặt capacity_max quá cao để ép dirty page giảm.** Background flush có thể làm đầy queue và tăng p99 latency của truy vấn.

**Đặt capacity quá thấp để giữ latency đọc.** Dirty page và checkpoint age có thể tích lũy, dẫn đến flush gấp và foreground stall sau đó.

**Tắt adaptive flushing khi thấy I/O tăng.** I/O nền có thể đang cần thiết để giữ checkpoint trong giới hạn. Hãy xem redo generation và checkpoint age.

**Cho rằng I/O vượt capacity là bug.** innodb_flush_sync có thể cho phép flush vượt mức capacity trong đợt checkpoint. Xem biến và trạng thái trước khi kết luận.

**Dùng cùng flush_neighbors cho mọi storage.** HDD, SSD, NVMe và SAN có đặc tính khác nhau. Đo trước/sau trên workload đại diện.

**Nhầm dirty page percentage với checkpoint pressure.** Cần xem tốc độ sinh redo, checkpoint age và khả năng flush, không chỉ tỷ lệ dirty.

**Tăng redo capacity để thay thế storage chậm.** Redo capacity giúp hấp thụ burst, không tăng IOPS hay throughput bền vững.

**Dùng innodb_io_capacity để xử lý COMMIT chậm.** Kiểm tra redo/binlog fsync, durability, storage latency và lock wait.

**Tắt doublewrite hoặc giảm durability để đạt benchmark.** Hiệu năng đo được không bù được rủi ro mất hoặc hỏng dữ liệu nếu yêu cầu durability không cho phép.

**Thay nhiều biến cùng lúc.** Không thể xác định tác động của từng biến và khó rollback. Thay đổi từng bước và ghi baseline.

## 21. Checklist chọn và kiểm chứng I/O capacity

- Đã xác định đúng server, phiên bản và storage path chưa?
- Thiết bị là HDD, SSD, NVMe, SAN, RAID hay cloud block volume?
- IOPS, throughput và latency bền vững đã được đo chưa?
- Có giới hạn burst, quota hoặc throttling không?
- Data files, redo, binlog, backup và workload khác có dùng chung backend không?
- innodb_io_capacity và innodb_io_capacity_max hiện tại là bao nhiêu?
- Adaptive flushing, flush_sync và dirty-page thresholds đang ở trạng thái nào?
- Dirty page percentage và checkpoint age có xu hướng tăng không?
- Pages flushed, redo bytes, wait_free và pending writes thay đổi ra sao?
- Storage queue và p95/p99 latency có tăng khi background flush mạnh không?
- COMMIT chậm có thực sự do page flushing hay do redo/binlog fsync hoặc lock wait?
- Thay đổi có được thử từng bước với workload đại diện không?
- Có baseline, điều kiện dừng, rollback và người phê duyệt không?
- Sau thay đổi, checkpoint có ổn định và foreground latency có nằm trong SLO không?

innodb_io_capacity và innodb_io_capacity_max giúp InnoDB điều tiết I/O nền, nhưng hiệu quả phụ thuộc vào cách dirty page, redo và checkpoint tương tác với thiết bị lưu trữ. Hãy đo tốc độ sinh redo, khả năng flush, storage latency và workload foreground trong cùng khoảng thời gian. Khi capacity phản ánh đúng phần I/O có thể dành cho background tasks, InnoDB có thể duy trì checkpoint ổn định mà không tạo ra các đợt flush gây ảnh hưởng không cần thiết đến truy vấn ứng dụng.
