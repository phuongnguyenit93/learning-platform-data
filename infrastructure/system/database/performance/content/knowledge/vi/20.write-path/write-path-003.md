# Group commit và ảnh hưởng của số phiên ghi đồng thời

## Vì sao số phiên ghi ảnh hưởng đến hiệu năng commit?

Khi một transaction ghi dữ liệu và yêu cầu COMMIT, hệ quản trị phải bảo đảm thông tin cần thiết để khôi phục transaction đã được ghi bền vững theo chính sách durability đang áp dụng. Với cơ sở dữ liệu dùng write-ahead logging (WAL) hoặc transaction log, các bản ghi log tương ứng phải được ghi và flush xuống tầng lưu trữ trước khi hệ thống xác nhận commit trong chế độ đồng bộ thông thường.

Một lần flush log có độ trễ nhất định. Nếu mỗi transaction phải tự chờ một lần flush riêng, chi phí này có thể giới hạn throughput của workload ghi, đặc biệt khi mỗi transaction chỉ thay đổi ít dữ liệu. Group commit là cơ chế cho phép nhiều transaction cùng chia sẻ một lần flush log khi các commit đến gần nhau. Thay vì mỗi transaction gây ra một lần flush riêng, hệ quản trị có thể gom các commit record đã sẵn sàng vào cùng một log flush và chỉ xác nhận chúng sau khi dữ liệu log cần thiết đã bền vững.

Số phiên ghi đồng thời ảnh hưởng đến khả năng hình thành nhóm commit. Khi chỉ có một phiên ghi, ít commit đến cùng lúc nên cơ hội gom nhóm có thể thấp. Khi tăng số phiên, nhiều transaction có thể chờ commit trong cùng khoảng thời gian và một lần flush có thể phục vụ nhiều transaction hơn. Tuy nhiên, tăng concurrency không mang lại lợi ích vô hạn: lock contention, tranh chấp latch, CPU, bộ nhớ, hàng đợi log và I/O có thể trở thành nút thắt mới. Độ trễ của từng transaction cũng có thể tăng khi hàng đợi dài.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần phân biệt ba mục tiêu:

- **Throughput:** số transaction hoặc commit hoàn tất trong một đơn vị thời gian.
- **Commit latency:** thời gian từ lúc ứng dụng gửi COMMIT đến khi nhận xác nhận.
- **Durability:** mức bảo đảm rằng transaction đã được xác nhận vẫn tồn tại sau sự cố theo cấu hình của hệ quản trị.

Group commit có thể tăng throughput bằng cách chia sẻ chi phí flush, nhưng phải giữ đúng chính sách durability. Tối ưu số phiên ghi cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê log, wait events và hành vi lưu trữ; không thể chỉ tăng số connection rồi kết luận hệ thống đã nhanh hơn.

## Write-ahead log và đường đi của một transaction ghi

### Vì sao cần transaction log?

Hệ quản trị cần duy trì khả năng phục hồi sau crash, rollback và bảo đảm tính nhất quán. Thay vì phải ghi ngay mọi trang dữ liệu đã thay đổi xuống vị trí cuối cùng của chúng trước khi commit, nhiều hệ quản trị ghi mô tả thay đổi vào log theo nguyên tắc write-ahead logging.

Nguyên tắc cơ bản là log record cần thiết phải được ghi bền vững trước khi trang dữ liệu tương ứng được ghi xuống vị trí lưu trữ chính. Nhờ vậy, sau sự cố, hệ quản trị có thể đọc log để redo các thay đổi đã commit hoặc undo những thay đổi chưa commit tùy kiến trúc và trạng thái phục hồi.

Các khái niệm thường gặp:

- **WAL / transaction log:** chuỗi bản ghi mô tả thay đổi và thông tin cần cho phục hồi.
- **Log buffer:** vùng bộ nhớ chứa các log record trước khi ghi xuống log file.
- **Log flush:** ghi log buffer hoặc phần log đã sẵn sàng xuống tầng lưu trữ.
- **Durable commit:** commit chỉ được xác nhận sau khi log cần thiết đạt mức bền vững mà cấu hình yêu cầu.
- **Checkpoint:** điểm phục hồi giúp giảm lượng công việc redo; checkpoint không thay thế yêu cầu flush log khi commit.
- **Log sequence number (LSN) hoặc vị trí log tương đương:** vị trí tuần tự xác định tiến độ log; tên gọi và chi tiết khác nhau theo engine.

Log thường được ghi tuần tự hoặc theo các vùng log tuần tự. Thiết kế này giúp cơ sở dữ liệu ghi log hiệu quả hơn so với việc ghi rải rác ngay từng trang dữ liệu. Tuy nhiên, tốc độ commit vẫn phụ thuộc latency flush, kích thước log, mức độ batching, số transaction đồng thời và khả năng xử lý của thiết bị.

### Đường đi khái quát của commit

Một transaction ghi có thể đi qua các bước sau:

1. Ứng dụng gửi câu lệnh INSERT, UPDATE hoặc DELETE.
2. Hệ quản trị kiểm tra ràng buộc, khóa, isolation và thực hiện thay đổi logic.
3. Các thay đổi và thông tin phục hồi được tạo thành log record trong log buffer.
4. Ứng dụng gửi COMMIT.
5. Hệ quản trị xác định vị trí log cần bền vững cho transaction.
6. Một log flush được thực hiện; có thể gom log record của nhiều transaction đang chờ.
7. Sau khi flush đáp ứng chính sách durability, hệ quản trị đánh dấu transaction đã commit và trả xác nhận cho ứng dụng.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Ứng dụng gửi DML] --> B[Kiểm tra khóa và thực hiện thay đổi]
    B --> C[Tạo log record trong log buffer]
    C --> D[Ứng dụng gửi COMMIT]
    D --> E[Đưa commit vào hàng đợi flush]
    E --> F{Có commit khác sẵn sàng?}
    F -->|Có| G[Gom log của nhiều transaction]
    F -->|Không| H[Flush log cho nhóm hiện tại]
    G --> H
    H --> I{Flush đáp ứng durability?}
    I -->|Có| J[Xác nhận các commit đủ điều kiện]
    I -->|Không| K[Tiếp tục chờ hoặc báo lỗi]
~~~

Đây là mô hình khái quát. Thứ tự nội bộ, cách lập nhóm, số luồng log writer, cách ghi log và điều kiện xác nhận commit khác nhau giữa PostgreSQL, SQL Server, MySQL/InnoDB, Oracle và các hệ thống phân tán.

### Log flush khác data page flush

Commit đồng bộ thường cần log record bền vững, không có nghĩa mọi trang dữ liệu đã thay đổi đều phải được ghi ngay xuống data file. Dirty page có thể được ghi sau bởi background writer, checkpoint hoặc cơ chế tương đương. WAL bảo đảm log cần thiết đi trước trang dữ liệu.

Vì vậy, một transaction có thể commit nhanh dù data page chưa được ghi xuống vị trí cuối cùng. Khi crash, hệ quản trị dùng log để phục hồi. Đừng đánh đồng log flush với checkpoint hoặc data page write; chúng là các hoạt động khác nhau và có thể tạo các loại wait khác nhau.

## Group commit hoạt động như thế nào?

### Gom nhiều commit vào một lần flush

Giả sử bốn transaction hoàn tất công việc ghi gần như cùng thời điểm. Mỗi transaction đã tạo log record và yêu cầu commit. Hệ quản trị có thể xác định log position lớn nhất cần flush cho nhóm, ghi log đến vị trí đó một lần, rồi xác nhận tất cả transaction có commit record nằm trong phần log đã bền vững.

Ví dụ minh họa:

~~~text
Không gom nhóm:
T1: COMMIT -> flush A -> xác nhận T1
T2: COMMIT -> flush B -> xác nhận T2
T3: COMMIT -> flush C -> xác nhận T3
T4: COMMIT -> flush D -> xác nhận T4

Có group commit:
T1: COMMIT ----\
T2: COMMIT -----+-> một log flush -> xác nhận T1, T2, T3, T4
T3: COMMIT -----+
T4: COMMIT ----/
~~~

Group commit giảm số lần flush cần thiết trên mỗi transaction. Nó không loại bỏ yêu cầu ghi log bền vững; các transaction trong nhóm vẫn chỉ được xác nhận sau khi log tương ứng đạt điều kiện durability.

### Điều kiện để hình thành nhóm

Group commit có hiệu quả khi nhiều transaction phát sinh commit đủ gần nhau để được gom vào cùng một đợt flush. Khả năng này chịu ảnh hưởng bởi:

- Số phiên ghi đồng thời.
- Thời gian thực thi phần DML trước commit.
- Độ phân tán thời điểm commit giữa các phiên.
- Độ trễ flush log.
- Cách engine lập nhóm và đánh thức log writer.
- Kích thước log buffer và áp lực log generation.
- CPU scheduling và mức tải hệ thống.
- Hàng đợi I/O và khả năng xử lý đồng thời của thiết bị.

Nếu transaction kéo dài nhiều giây vì xử lý ứng dụng hoặc giữ khóa, tăng số connection chưa chắc làm commit đến cùng lúc. Ngược lại, workload gồm nhiều transaction ngắn và commit dồn dập có thể tận dụng group commit rõ rệt.

### Vì sao concurrency quá thấp có thể làm throughput thấp?

Với một phiên duy nhất, mỗi transaction có thể ghi một lượng nhỏ log rồi chờ flush. Nếu không có commit khác sẵn sàng trong cùng cửa sổ, mỗi transaction khó chia sẻ chi phí flush. Khi tăng lên vài phiên độc lập, các transaction có thể tiến triển xen kẽ và cùng chờ một lần flush.

Ví dụ, nếu một lần flush mất vài mili giây, việc chỉ có một transaction chờ có thể khiến phần lớn thời gian commit là thời gian chờ I/O. Khi nhiều transaction cùng chờ, một lần flush có thể xác nhận nhiều commit. Tổng số transaction hoàn tất mỗi giây có thể tăng dù thời gian chờ của mỗi nhóm không giảm tương ứng.

### Vì sao concurrency quá cao làm hệ thống chậm lại?

Khi số phiên tăng vượt khả năng xử lý, hệ thống có thể xuất hiện:

- Nhiều transaction tranh chấp cùng hàng, trang, index page hoặc metadata.
- Lock wait và deadlock tăng.
- Latch hoặc spinlock contention trong cấu trúc nội bộ.
- Log buffer và log writer trở thành điểm nóng.
- Hàng đợi ghi log hoặc storage queue kéo dài.
- CPU tăng do context switching, xử lý lock và lập lịch.
- Connection pool cạn, request phải chờ trước khi vào database.
- Transaction giữ khóa lâu hơn do phải chờ log flush.
- p95/p99 commit latency tăng dù throughput tổng thể đã bão hòa.

Do đó, mục tiêu là tìm mức concurrency đạt throughput tốt trong giới hạn latency và tài nguyên, không phải tối đa hóa số phiên.

## Group commit khác với batch commit

Hai khái niệm này thường bị nhầm lẫn:

- **Group commit:** hệ quản trị tự gom commit của nhiều transaction độc lập vào cùng một lần flush log; mỗi transaction vẫn giữ ranh giới commit riêng.
- **Batching trong một transaction:** ứng dụng thực hiện nhiều câu lệnh ghi trong một transaction rồi commit một lần; nhiều thay đổi cùng thuộc một đơn vị atomicity.

Ví dụ batching:

~~~sql
BEGIN;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (1001, 501, 2),
    (1001, 502, 1),
    (1001, 503, 4);

COMMIT;
~~~

Ví dụ group commit có thể gồm ba phiên khác nhau, mỗi phiên chạy transaction riêng và gửi COMMIT gần nhau. Hệ quản trị có thể gom log của cả ba nhưng vẫn xác nhận ba transaction độc lập.

### Đánh đổi của batching

Batching có thể giảm số lần commit trên mỗi hàng và amortize overhead transaction, nhưng transaction lớn hơn có thể:

- Giữ khóa lâu hơn.
- Tăng lượng log cần ghi trong một transaction.
- Tăng thời gian rollback khi thất bại.
- Tạo burst I/O và áp lực bộ nhớ.
- Tăng nguy cơ deadlock hoặc blocking nếu nhiều hàng được cập nhật theo thứ tự khác nhau.
- Làm tăng độ trễ của hàng đầu tiên trong batch.
- Thay đổi ngữ nghĩa atomicity so với commit từng hàng.

Batching phù hợp khi nghiệp vụ chấp nhận một nhóm thay đổi cùng thành công hoặc cùng thất bại. Group commit phù hợp khi nhiều transaction độc lập cùng ghi và engine có thể chia sẻ chi phí flush mà vẫn giữ ranh giới transaction.

## Ảnh hưởng của số phiên ghi đồng thời

### Quan hệ giữa concurrency, throughput và latency

Ở mức concurrency thấp, tăng số phiên thường giúp khai thác CPU, I/O và group commit tốt hơn. Khi đạt điểm bão hòa, throughput tăng chậm hoặc không tăng nữa. Nếu tiếp tục tăng concurrency, hàng đợi và tranh chấp có thể làm latency tăng mạnh.

Một mô hình khái quát:

~~~text
Concurrency thấp:
- Ít transaction sẵn sàng commit cùng lúc
- Khả năng gom nhóm thấp
- Tài nguyên có thể chưa được sử dụng hết

Concurrency phù hợp:
- Nhiều commit có thể chia sẻ log flush
- CPU và storage được khai thác tốt
- Throughput tăng, latency còn trong mục tiêu

Concurrency quá cao:
- Lock/latch và log queue contention
- Context switching và connection wait
- Throughput bão hòa hoặc giảm
- p95/p99 commit latency tăng
~~~

Không có một số phiên tối ưu chung. Một workload ghi log tuần tự vào các hàng độc lập khác với workload cập nhật một số hàng nóng. Kết quả còn phụ thuộc thiết bị lưu trữ, kích thước transaction, isolation level, schema, chỉ mục và cấu hình durability.

### Transaction ngắn và transaction dài

Transaction ngắn thường tạo log ít và giải phóng khóa nhanh. Nếu có nhiều transaction ngắn, group commit có thể giảm chi phí flush trên mỗi transaction.

Transaction dài có thể tạo nhiều log, giữ khóa và snapshot lâu, làm tăng áp lực phục hồi hoặc version store. Chúng cũng có thể khiến các phiên khác chờ. Tăng concurrency trong khi còn transaction dài có thể làm throughput xấu đi.

Hãy đo thời gian từ BEGIN đến COMMIT, thời gian DML, thời gian chờ khóa và thời gian commit riêng. Nếu commit latency cao, cần xác định thời gian đang nằm ở phần thực thi DML, chờ lock hay chờ log flush.

### Tranh chấp trên hàng nóng

Giả sử hàng nghìn transaction cùng cập nhật một bộ đếm hoặc số dư tài khoản duy nhất. Dù group commit có thể gom log, các transaction vẫn phải tuần tự hóa hoặc chờ khóa trên hàng nóng. Thêm phiên chỉ làm tăng số waiter và context switching.

Các giải pháp có thể gồm:

- Giảm số lần cập nhật cùng một hàng bằng cách gom sự kiện hoặc cập nhật theo lô nếu nghiệp vụ cho phép.
- Phân tán bộ đếm thành nhiều bucket rồi tổng hợp khi đọc.
- Dùng hàng đợi hoặc một luồng xử lý có thứ tự cho tài nguyên tranh chấp.
- Rút ngắn transaction và không giữ khóa trong lúc gọi dịch vụ ngoài.
- Chuẩn hóa thứ tự cập nhật nhiều hàng để giảm deadlock.
- Thiết kế lại mô hình dữ liệu để giảm điểm ghi tập trung.

Không dùng partitioning để kỳ vọng tự giải quyết lock trên cùng một row. Phân vùng thay đổi nơi lưu trữ; nó không loại bỏ xung đột logic khi nhiều transaction sửa cùng thực thể.

## Durability và cấu hình đồng bộ

### Commit đồng bộ

Trong chế độ commit đồng bộ thông thường, ứng dụng chỉ nhận xác nhận sau khi log cần thiết đã được flush đến mức bền vững mà hệ quản trị cam kết. Đây là nền tảng cho durability sau crash trong phạm vi cấu hình và hạ tầng được hỗ trợ.

Nếu thiết bị hoặc hệ thống lưu trữ báo hoàn tất flush nhưng không thực sự bảo đảm dữ liệu qua mất điện, cam kết durability còn phụ thuộc controller, cache bảo vệ bằng pin, filesystem, hypervisor và dịch vụ lưu trữ. Cấu hình database không thể bù cho tầng lưu trữ không thực hiện đúng hợp đồng flush.

### Commit bất đồng bộ hoặc delayed durability

Một số hệ quản trị cho phép xác nhận commit trước khi log đã được flush bền vững. Điều này có thể giảm latency nhưng tạo cửa sổ mà transaction đã được ứng dụng xem là thành công vẫn có thể mất khi hệ thống gặp sự cố.

Ví dụ khái niệm:

- PostgreSQL có các mức synchronous_commit khác nhau, trong đó cấu hình không chờ local WAL flush có thể thay đổi bảo đảm về mất dữ liệu khi crash; các mức liên quan replication còn phụ thuộc synchronous standby.
- SQL Server hỗ trợ delayed durability trong các cấu hình phù hợp; commit có thể được xác nhận trước khi log record được flush.
- MySQL/InnoDB có các tham số như innodb_flush_log_at_trx_commit và sync_binlog ảnh hưởng chu kỳ flush redo log và binary log.

Tên tham số và hành vi chi tiết phụ thuộc phiên bản, topology và cấu hình. Không thay đổi durability chỉ để tăng tốc benchmark. Trước khi dùng chế độ bất đồng bộ, phải xác định rõ RPO, khả năng mất giao dịch đã xác nhận, quy trình phục hồi và sự chấp thuận của chủ hệ thống.

### Replication và commit

Trong hệ thống có replication đồng bộ, commit có thể phải chờ xác nhận từ một hoặc nhiều replica tùy cấu hình. Khi đó, độ trễ mạng và khả năng flush của replica có thể chi phối commit latency. Group commit cục bộ vẫn có thể tồn tại, nhưng không loại bỏ thời gian chờ xác nhận từ replica.

Với replication bất đồng bộ, ứng dụng có thể nhận commit trước khi replica áp dụng log. Điều này tạo replication lag và có thể ảnh hưởng đọc sau ghi nếu ứng dụng đọc từ replica. Hãy phân biệt local durable commit, remote log receipt và remote apply; chúng là các mốc khác nhau.

## Đo group commit và xác định nút thắt

### Chỉ số cần thu thập

Để đánh giá group commit, cần đo cả log và workload:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Workload | Transactions/sec, commits/sec | Tốc độ hoàn tất transaction |
| Workload | Số phiên hoạt động và số phiên chờ | Mức concurrency thực tế |
| Latency | Commit latency p50/p95/p99 | Thời gian chờ xác nhận commit |
| Log | Log bytes generated/sec | Tốc độ phát sinh log |
| Log | Flushes/sec và bytes/flush | Số lần flush và mức gom nhóm trung bình |
| Log | Log flush wait/time | Thời gian chờ ghi log |
| Storage | Write latency, IOPS, throughput, queue depth | Khả năng đáp ứng của thiết bị |
| Lock | Lock wait, deadlock, latch/spinlock wait | Tranh chấp đồng thời |
| CPU | CPU utilization, context switches | Mức sử dụng và overhead lập lịch |
| Application | Pool wait, request latency, timeout | Tắc nghẽn trước và sau database |

Một chỉ số tham khảo là số transaction commit trung bình trên mỗi lần flush, có thể ước lượng từ commits và log flushes trong cùng khoảng đo nếu hệ quản trị cung cấp số liệu tương thích. Tuy nhiên, không phải mọi flush đều chỉ phục vụ commit; checkpoint, background writer hoặc flush nội bộ khác có thể làm mẫu số thay đổi. Hãy dùng chỉ số chính thức của engine nếu có và đọc định nghĩa trước khi so sánh.

### Phân biệt log flush wait với lock wait

Commit latency cao không đồng nghĩa group commit kém. Cần xem wait event hoặc thống kê tương ứng:

- Chờ log flush: transaction đã sẵn sàng commit nhưng phải chờ log được ghi bền vững.
- Chờ lock: transaction chưa thể tiếp tục vì transaction khác giữ khóa.
- Chờ latch/spinlock: tranh chấp cấu trúc nội bộ trong engine.
- Chờ CPU: có công việc nhưng không được cấp CPU kịp thời.
- Chờ I/O khác: đọc dữ liệu, checkpoint, temp spill hoặc hoạt động lưu trữ không phải log commit.
- Chờ network/replication: cần xác nhận từ node khác hoặc truyền log.

Nếu wait chủ yếu là lock, tăng group commit không giải quyết gốc rễ. Nếu wait là log flush và bytes/flush thấp, thử tăng concurrency có kiểm soát hoặc kiểm tra cấu hình log writer/storage có thể hữu ích.

### Đo log flush theo hệ quản trị

Tên thống kê khác nhau theo sản phẩm:

- PostgreSQL cung cấp các view thống kê WAL và database như pg_stat_wal, pg_stat_database cùng wait events; trường cụ thể phụ thuộc phiên bản.
- SQL Server có các DMV, wait statistics, transaction log counters và công cụ như Query Store/Extended Events để phân tích log flush và transaction.
- MySQL/InnoDB cung cấp status variables, Performance Schema và các thông tin liên quan redo log, log waits, binary log và I/O; tên trường phụ thuộc phiên bản.

Không chạy một truy vấn thống kê trên mọi hệ quản trị rồi giả định tên cột hoặc ngữ nghĩa giống nhau. Hãy lấy số liệu từ tài liệu phiên bản và công cụ giám sát đang dùng. Khi lấy delta counters, ghi thời điểm bắt đầu/kết thúc và xử lý reset/restart của bộ đếm.

## Thiết kế thử nghiệm concurrency có kiểm soát

### Giữ workload cố định

Để tìm số phiên ghi phù hợp, tạo benchmark đại diện với:

- Cùng schema, chỉ mục và phân bố dữ liệu.
- Cùng kích thước transaction và số log bytes gần tương đương.
- Cùng tỷ lệ INSERT/UPDATE/DELETE.
- Cùng mức cạnh tranh khóa và mẫu truy cập.
- Cùng chính sách durability và replication.
- Cùng loại thiết bị lưu trữ hoặc môi trường tương đương.
- Thời gian warm-up và thời gian đo nhất quán.

Không dùng một bài test chỉ INSERT vào bảng rỗng để đại diện cho production nếu production còn cập nhật index, foreign key, trigger, unique check hoặc nhiều hàng nóng.

### Tăng concurrency theo bậc

Có thể thử lần lượt 1, 2, 4, 8, 16, 32 phiên hoặc các mức phù hợp với giới hạn hệ thống. Ở mỗi mức, ghi:

- Throughput commit.
- p50/p95/p99 commit latency.
- Log flushes/sec và bytes/flush.
- Log flush wait.
- Lock/latch wait và deadlock.
- CPU, I/O latency, queue depth.
- Connection pool wait và timeout.

Mức tối ưu thường nằm gần điểm throughput bắt đầu bão hòa nhưng trước khi p95/p99 và hàng đợi tăng mạnh. Chọn mục tiêu theo SLO, không chỉ theo throughput cực đại.

### Lặp lại và tránh benchmark gây nhiễu

Mỗi mức concurrency nên được chạy đủ lâu để qua giai đoạn khởi động và quan sát dao động. Thử nghiệm nên lặp lại, ghi nhận cache, checkpoint, backup và tác vụ nền. Không chạy các benchmark nặng đồng thời trên cùng thiết bị lưu trữ nếu muốn so sánh chính xác.

Nếu thử nghiệm làm tăng WAL, transaction log hoặc binary log nhanh, phải theo dõi dung lượng trống và replication lag. Dừng thử nghiệm khi có dấu hiệu ảnh hưởng dịch vụ hoặc vượt giới hạn vận hành.

## Điều chỉnh số phiên ghi và kích thước transaction

### Giới hạn concurrency ở tầng ứng dụng

Connection pool quá lớn có thể đưa quá nhiều transaction vào database cùng lúc. Nếu throughput đã bão hòa, tăng pool size chỉ tăng số phiên chờ và tài nguyên tiêu thụ.

Cần chọn giới hạn pool dựa trên số CPU, khả năng I/O, mức lock contention và số workload dùng chung. Có thể dùng hàng đợi ở tầng ứng dụng hoặc backpressure để giữ số transaction đồng thời trong vùng hiệu quả. Pool size không nên được đặt chỉ bằng số request tối đa của web server.

### Điều chỉnh transaction size

Transaction quá nhỏ có thể tạo nhiều commit và flush; transaction quá lớn có thể giữ khóa lâu, tạo log lớn và tăng rollback time. Tìm batch size phù hợp bằng phép đo:

- Số hàng mỗi transaction.
- Log bytes mỗi transaction.
- Commit latency.
- Lock duration.
- Rollback duration khi có lỗi.
- Memory usage và log pressure.
- Khả năng retry và idempotency của ứng dụng.

Nếu tăng batch size làm throughput tăng nhưng p99 hoặc thời gian khóa vượt SLO, cần giảm batch hoặc chia lô theo ranh giới nghiệp vụ.

### Giảm log generation hợp lý

Các thao tác sau có thể giảm lượng log hoặc chi phí ghi, tùy hệ quản trị và yêu cầu phục hồi:

- Chỉ cập nhật cột thực sự thay đổi.
- Tránh ghi lại cùng giá trị nếu không cần trigger hoặc audit event.
- Giảm chỉ mục dư thừa trên bảng ghi nhiều.
- Dùng bulk load hoặc cơ chế nạp dữ liệu chuyên dụng khi phù hợp.
- Tối ưu transaction để không ghi cùng dữ liệu nhiều lần.
- Kiểm soát trigger và cascade có chi phí cao.

Không vô hiệu hóa logging, constraint hoặc durability chỉ để cải thiện số benchmark nếu không có thiết kế phục hồi tương ứng. Minimal logging hoặc bulk operation có điều kiện và giới hạn riêng.

### Đặt log trên storage phù hợp

Log có đặc điểm ghi tuần tự và nhạy với latency flush. Tách log khỏi data file có thể giúp cô lập I/O trong một số cấu hình, nhưng không tự bảo đảm tăng tốc nếu cả hai vẫn dùng chung thiết bị, controller hoặc giới hạn cloud volume.

Đánh giá:

- Latency ghi đồng bộ và tail latency.
- IOPS, throughput và queue depth.
- Bảo vệ write cache và khả năng flush bền vững.
- Giới hạn của volume hoặc storage tier.
- Ảnh hưởng checkpoint, backup và replication.
- Dung lượng log và tốc độ tăng trong giờ cao điểm.

Đừng chỉ nhìn throughput tuần tự tối đa của thiết bị. Commit thường nhạy với độ trễ flush và độ ổn định p95/p99 hơn là băng thông ghi lớn nhất.

## Ví dụ chẩn đoán

Một API ghi trạng thái đơn hàng chạy nhiều transaction ngắn. Mỗi transaction cập nhật một đơn và commit ngay. Khi tải tăng, throughput chỉ tăng đến một mức rồi chững lại; p95 commit latency tăng, trong khi CPU chưa bão hòa.

Nhóm quan sát:

- Log flush wait chiếm phần đáng kể thời gian chờ.
- Số commit trên mỗi giây tăng ít hơn số phiên hoạt động.
- Bytes log trên mỗi transaction nhỏ.
- Log flush latency ổn định nhưng số lần flush cao.
- Lock wait thấp, deadlock gần như không có.
- I/O data file không phải nút thắt chính.

Giả thuyết là chi phí flush trên mỗi transaction đang chi phối. Nhóm tăng concurrency từ từ trong môi trường thử nghiệm và đo bytes/flush, commits/sec cùng p95. Nếu nhiều transaction được xác nhận trên mỗi flush hơn và throughput tăng mà latency còn trong SLO, group commit đang giúp chia sẻ chi phí.

Một kịch bản khác có cùng dấu hiệu throughput chững nhưng lock wait tăng mạnh do mọi phiên cập nhật cùng một hàng tổng số đơn. Khi đó, tăng concurrency không giúp; nó làm hàng đợi lock dài hơn. Nhóm cần giảm điểm ghi nóng hoặc gom cập nhật theo thiết kế nghiệp vụ, sau đó mới đo lại group commit.

Ví dụ bảng số liệu minh họa:

| Phiên ghi đồng thời | Commits/sec | p95 commit | Log flushes/sec | Commits/flush ước lượng | Lock wait |
|---:|---:|---:|---:|---:|---|
| 1 | 180 | 5 ms | 178 | 1,0 | Thấp |
| 4 | 620 | 7 ms | 300 | 2,1 | Thấp |
| 8 | 980 | 9 ms | 360 | 2,7 | Thấp |
| 16 | 1.120 | 18 ms | 410 | 2,7 | Trung bình |
| 32 | 1.130 | 55 ms | 430 | 2,6 | Cao |

Các con số chỉ minh họa cách diễn giải. Mức 16 hoặc 32 không thể được chọn chỉ từ bảng này; cần xem SLO, CPU, I/O, transaction mix và độ ổn định qua nhiều lần chạy. Nếu throughput gần như không tăng từ 16 lên 32 nhưng p95 tăng mạnh, 32 phiên có thể chỉ làm tăng queueing.

## Những sai lầm thường gặp

- **Nhầm group commit với batch nhiều câu lệnh trong một transaction:** một cơ chế gom flush nhiều commit độc lập, cơ chế kia thay đổi ranh giới transaction.
- **Cho rằng group commit bỏ qua durability:** log cần thiết vẫn phải được flush theo chính sách đồng bộ.
- **Tăng số connection vô hạn:** concurrency quá cao làm tăng lock/latch contention và queueing.
- **Chỉ nhìn throughput:** bỏ qua p95/p99 commit latency và timeout.
- **Chỉ nhìn commit latency tổng:** không phân biệt thời gian DML, lock wait và log flush wait.
- **Đổ lỗi cho storage khi lock wait chiếm ưu thế:** nút thắt có thể nằm ở hot row hoặc transaction dài.
- **Tăng batch size quá mức:** giảm số commit nhưng kéo dài khóa và rollback.
- **Tắt synchronous durability để chạy benchmark:** kết quả không còn đại diện cho yêu cầu bảo vệ dữ liệu.
- **So sánh cấu hình khác durability:** benchmark không cùng điều kiện thì không thể kết luận chính xác.
- **Bỏ qua replication:** commit có thể chờ remote acknowledgement hoặc gây lag tùy topology.
- **Không kiểm tra log capacity:** thử tải ghi có thể làm đầy transaction log hoặc WAL volume.
- **Dựa vào một lần chạy:** cache, checkpoint và tác vụ nền có thể làm số liệu sai lệch.

## Checklist tối ưu group commit và concurrency

- [ ] Xác định hệ quản trị, phiên bản và chính sách durability đang dùng.
- [ ] Xác định commit đồng bộ, bất đồng bộ và yêu cầu replication.
- [ ] Đo commits/sec, log bytes/sec, flushes/sec và bytes/flush.
- [ ] Đo p50/p95/p99 commit latency.
- [ ] Phân biệt log flush wait, lock wait, latch wait, CPU và I/O wait.
- [ ] Xác định transaction size và log bytes trên mỗi transaction.
- [ ] Kiểm tra hot row, hot key, deadlock và transaction kéo dài.
- [ ] Thử concurrency theo bậc với workload và dữ liệu tương đương.
- [ ] Tìm điểm throughput bão hòa trước khi p95/p99 tăng mạnh.
- [ ] Điều chỉnh connection pool và backpressure theo mức concurrency phù hợp.
- [ ] Cân nhắc batch size mà vẫn giữ đúng atomicity và khả năng rollback.
- [ ] Theo dõi log capacity, storage latency và replication lag.
- [ ] Giữ nguyên durability khi so sánh hiệu năng.
- [ ] Lặp lại phép đo và kiểm chứng cả đọc, ghi cùng workload khác.

## Kết luận

Group commit giúp nhiều transaction độc lập chia sẻ chi phí flush log mà vẫn giữ ranh giới commit riêng. Số phiên ghi đồng thời ảnh hưởng đến khả năng hình thành nhóm, nhưng tăng concurrency quá mức có thể làm lock, latch, CPU, log queue và storage queue trở thành nút thắt. Vì vậy, cần tìm điểm cân bằng giữa throughput và commit latency thay vì tối đa hóa số connection.

Hãy bắt đầu bằng việc đo log flush wait, bytes/flush, commits/sec, p95/p99 và các wait khác. Thử concurrency theo bậc trên workload đại diện, giữ nguyên chính sách durability và kiểm tra tác động đến replication, transaction log cùng các thao tác đọc/ghi khác. Chỉ điều chỉnh connection pool, batch size hoặc cấu hình flush sau khi đã xác định đúng nguyên nhân và kiểm chứng kết quả trong điều kiện tương đương.