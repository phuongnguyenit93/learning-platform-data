# Kích thước giao dịch, tốc độ nạp và áp lực lên bản sao

Một luồng nạp dữ liệu có thể ghi rất nhanh vào máy chủ chính nhưng vẫn làm hệ thống chậm đi nếu transaction quá lớn, log tăng nhanh hoặc replica không theo kịp. Ngược lại, chia mọi lần ghi thành transaction quá nhỏ có thể tạo quá nhiều lần commit, round trip và chi phí đồng bộ log. Tối ưu đường ghi vì vậy cần cân bằng ba yếu tố: **kích thước transaction**, **tốc độ nạp dữ liệu** và **khả năng tiếp nhận, ghi lại log của replica**.

Trong tối ưu hiệu năng cơ sở dữ liệu, số hàng mỗi batch không phải mục tiêu độc lập. Cần đo số byte log sinh ra, thời gian giữ lock, thời gian commit, tốc độ áp dụng thay đổi ở replica, độ trễ truy vấn đọc và khả năng phục hồi sau lỗi. Một batch phù hợp phải đủ lớn để giảm overhead, đủ nhỏ để giới hạn rollback và lock duration, đồng thời giữ cho tốc độ sinh log không vượt quá khả năng xử lý bền vững của hệ thống sao chép.

Bài học này trình bày mối quan hệ giữa transaction size, bulk load, log và replication lag; cách chọn kích thước batch; cách nạp theo lô có checkpoint và retry an toàn; các chỉ số cần theo dõi trên máy chủ chính và replica; cùng quy trình benchmark và điều tiết tải.

## 1. Ba đại lượng cần tối ưu cùng nhau

### 1.1. Kích thước transaction

Kích thước transaction có thể được đo theo nhiều cách:

- Số hàng được INSERT, UPDATE hoặc DELETE.
- Tổng số byte dữ liệu thay đổi.
- Số byte WAL, redo log hoặc transaction log được sinh ra.
- Thời gian từ BEGIN đến COMMIT.
- Số trang, index entry và đối tượng bị sửa đổi.
- Số lock hoặc tài nguyên được giữ trong suốt transaction.

Hai transaction cùng ghi 10.000 hàng có thể có chi phí rất khác nhau. Hàng có payload JSON lớn, nhiều index, trigger hoặc foreign key có thể sinh nhiều log và I/O hơn bảng chỉ có vài cột số nguyên.

### 1.2. Tốc độ nạp dữ liệu

Thông lượng nạp có thể được biểu diễn bằng:

- Rows/second: số hàng được ghi mỗi giây.
- Bytes/second: lượng dữ liệu đầu vào mỗi giây.
- Commits/second: số transaction hoàn tất mỗi giây.
- Log bytes/second: lượng WAL, redo hoặc transaction log sinh ra mỗi giây.

Rows/second hữu ích để so sánh các batch có cấu trúc tương tự. Nhưng khi payload hoặc số index thay đổi, log bytes/second và I/O thường phản ánh áp lực thực tế tốt hơn.

### 1.3. Khả năng theo kịp của replica

Replica phải nhận, lưu và áp dụng các thay đổi do primary phát ra. Tùy kiến trúc, nó có thể nhận WAL stream, binlog, transaction log hoặc redo record; sau đó ghi log xuống đĩa và áp dụng thay đổi vào dữ liệu.

Nếu primary sinh log nhanh hơn tốc độ replica có thể xử lý trong một khoảng thời gian kéo dài, backlog sẽ tăng. Backlog này thường được gọi là replication lag, nhưng cần phân biệt:

- **Transport/send lag:** log chưa được chuyển hết đến replica.
- **Receive/flush lag:** replica đã nhận nhưng chưa ghi bền vững toàn bộ log.
- **Apply/replay lag:** log đã nhận nhưng replica chưa áp dụng xong vào trạng thái dữ liệu có thể đọc.

Một hệ thống có thể có send lag thấp nhưng apply lag cao. Chỉ nhìn một con số độ trễ tổng hợp có thể bỏ sót nút thắt.

## 2. Vì sao transaction quá nhỏ hoặc quá lớn đều tốn kém?

### 2.1. Transaction quá nhỏ

Nếu mỗi transaction chỉ ghi một vài hàng, hệ thống có thể phải trả overhead cho mỗi lần:

- Mở và kết thúc transaction.
- Gửi COMMIT qua mạng.
- Flush hoặc đồng bộ log theo durability policy.
- Thực hiện kiểm tra constraint, trigger và bookkeeping.
- Ghi metadata và cập nhật trạng thái transaction.
- Tạo nhiều thông điệp hoặc nhóm log nhỏ cho hệ thống replication.

Với workload có độ trễ commit đáng kể, nhiều transaction nhỏ làm giảm throughput dù tổng số hàng ghi không đổi. Nếu ứng dụng gửi từng câu INSERT riêng qua mạng, round trip có thể trở thành nút thắt.

### 2.2. Transaction quá lớn

Một transaction kéo dài và thay đổi quá nhiều hàng có thể:

- Giữ row lock, key lock hoặc các tài nguyên đồng bộ lâu hơn.
- Tăng nguy cơ chặn truy vấn đọc/ghi khác và deadlock.
- Sinh lượng WAL/redo/transaction log lớn.
- Tạo áp lực lên buffer pool, memory, checkpoint và I/O.
- Làm rollback tốn thời gian nếu thất bại gần cuối.
- Giữ phiên bản dữ liệu cũ lâu hơn trong các hệ thống MVCC.
- Tạo một đơn vị công việc lớn mà replica phải xử lý hoặc commit theo ranh giới transaction.
- Làm tăng thời gian phục hồi sau sự cố và khó xác định điểm tiếp tục.

Transaction lớn có thể ghi nhanh trong một lần chạy cô lập nhưng làm p95/p99 của toàn hệ thống xấu đi khi chạy cùng workload đọc/ghi bình thường.

### 2.3. Transaction không chỉ lớn theo số hàng

Khi chọn batch size, cần xem độ rộng hàng và lượng thay đổi. Cập nhật một cột nhỏ trên bảng có nhiều index có thể sinh log lớn vì mỗi index liên quan cần được duy trì. Xóa một hàng cha có thể kích hoạt kiểm tra hoặc cascade tới nhiều hàng con. Trigger có thể ghi thêm dữ liệu vào các bảng khác.

Do đó, nên đo cả số hàng và số byte log của một batch mẫu. Nếu kích thước hàng thay đổi theo dữ liệu, batch cố định 5.000 hàng có thể tạo ra transaction nhỏ ở lần này nhưng rất lớn ở lần khác.

## 3. Mối quan hệ giữa tốc độ sinh log và replication lag

Có thể mô hình hóa backlog log theo cách đơn giản:

**Tốc độ tăng backlog ≈ tốc độ primary sinh log − tốc độ replica áp dụng log.**

Nếu primary sinh 80 MB log mỗi giây và replica áp dụng được 60 MB mỗi giây trong cùng điều kiện, backlog tăng khoảng 20 MB mỗi giây. Nếu chênh lệch kéo dài, replica ngày càng tụt lại.

Khi primary tạm dừng hoặc giảm tải, replica có thể bắt kịp nếu tốc độ áp dụng cao hơn tốc độ log mới được sinh ra. Thời gian bắt kịp gần đúng phụ thuộc backlog hiện tại chia cho phần công suất dư của replica:

\[
T_{catchup}\approx\frac{B}{R_{apply}-R_{new}}
\]

Trong đó B là backlog log, R_apply là tốc độ áp dụng và R_new là tốc độ log mới tiếp tục sinh ra. Công thức chỉ là ước lượng: log có thể nén, có transaction lớn, thay đổi theo loại thao tác, và replica còn chịu ảnh hưởng của I/O, CPU, checkpoint hoặc xung đột truy vấn đọc.

Ví dụ:

- Backlog hiện tại: 12 GB.
- Replica có thể áp dụng: 120 MB/s.
- Primary tiếp tục sinh: 80 MB/s.
- Công suất dư: 40 MB/s.

Thời gian bắt kịp lý thuyết khoảng 12 GB chia cho 40 MB/s, tức khoảng 5 phút nếu các tốc độ ổn định và không có yếu tố khác. Nếu R_apply không lớn hơn R_new, replica không thể bắt kịp khi primary tiếp tục chạy ở tốc độ đó.

Điểm cần nhớ là tăng tốc độ nạp trên primary không phải lúc nào cũng tăng thông lượng hữu ích toàn hệ thống. Nếu replica là thành phần chậm nhất, tăng tải chỉ làm backlog và độ trễ đọc tăng.

## 4. Transaction lớn tác động đến replica như thế nào?

Replica thường nhận các bản ghi log theo thứ tự mà hệ thống replication yêu cầu. Cách áp dụng phụ thuộc công nghệ:

- Physical/log shipping có thể truyền và replay các thay đổi ở mức log hoặc page record.
- Logical replication thường truyền các thay đổi logic theo bảng và transaction.
- Một số hệ thống hỗ trợ apply song song nhưng vẫn phải tôn trọng ràng buộc thứ tự, xung đột và ranh giới commit.

Một transaction lớn có thể tạo lượng log lớn và làm tăng thời gian xử lý trước khi trạng thái replica phản ánh đầy đủ thay đổi. Với logical apply, một transaction chứa nhiều hàng có thể cần nhiều công việc trên replica và có thể bị giới hạn bởi số worker, thứ tự transaction hoặc conflict.

### 4.1. Transaction lớn và khả năng đọc trên replica

Ứng dụng đọc từ replica có thể nhìn thấy dữ liệu trễ hơn primary. Với báo cáo hoặc màn hình trạng thái, điều này có thể gây ra:

- Bản ghi vừa ghi chưa xuất hiện khi đọc ngay từ replica.
- Số dư hoặc trạng thái hiển thị cũ hơn.
- Một báo cáo chỉ phản ánh một phần dữ liệu mới nếu các bảng hoặc transaction khác nhau được áp dụng ở thời điểm khác nhau.
- Độ trễ đọc tăng trong thời gian bulk load.

Nếu yêu cầu nghiệp vụ cần read-after-write, ứng dụng có thể đọc từ primary trong một khoảng thời gian, dùng cơ chế chờ replica đạt một vị trí log nhất định nếu DBMS hỗ trợ, hoặc định tuyến theo session consistency. Không nên mặc định replica luôn cập nhật tức thời.

### 4.2. Transaction lớn và giới hạn apply

Một số hệ thống replication có thể áp dụng nhiều transaction độc lập song song, nhưng transaction phụ thuộc hoặc xung đột vẫn phải chờ. Transaction lớn có thể chiếm worker hoặc tài nguyên apply lâu hơn, khiến các thay đổi khác bị chậm theo.

Chia một công việc lớn thành nhiều transaction nhỏ có thể giúp replica áp dụng từng phần sớm hơn, nhưng sẽ thay đổi tính nguyên tử của công việc. Nếu nghiệp vụ yêu cầu toàn bộ dữ liệu xuất hiện cùng lúc, cần dùng staging và bước publish/merge có kiểm soát thay vì tự ý commit từng phần.

## 5. Chọn kích thước batch từ phép đo

Không có số hàng cố định phù hợp với mọi bảng. Batch size nên được chọn dựa trên độ rộng hàng, index, tốc độ commit, lock duration, log generation và năng lực replica.

### 5.1. Bắt đầu với batch nhỏ có kiểm soát

Một cách thực tế là chọn một batch ban đầu vừa phải, đo thời gian và lượng log, rồi tăng dần. Ví dụ thử 500, 1.000, 2.000 và 5.000 hàng nếu dữ liệu và môi trường cho phép. Các mức này chỉ là điểm khởi đầu minh họa, không phải khuyến nghị phổ quát.

Với mỗi mức, ghi:

- Số hàng và số byte đầu vào.
- Thời gian từ đầu transaction đến commit.
- Rows/second và log bytes/second.
- Số lần retry, deadlock hoặc lock wait.
- CPU, memory, I/O và log flush latency.
- Send/receive/apply lag của replica.
- Độ trễ truy vấn đọc và ghi khác.

### 5.2. Dùng cả giới hạn số hàng và giới hạn thời gian

Batch chỉ giới hạn theo số hàng có thể không an toàn khi payload biến động. Có thể dừng batch khi đạt một trong các điều kiện:

- Đạt số hàng tối đa.
- Đạt giới hạn byte ước lượng.
- Đạt thời gian transaction tối đa.
- Đạt ngưỡng log hoặc backlog cho phép.

Ví dụ, một job có thể commit sau mỗi 2.000 hàng hoặc khi transaction đã chạy 2 giây, tùy điều kiện nào đến trước. Ngưỡng thực tế phải được hiệu chỉnh từ số đo và mục tiêu của hệ thống.

### 5.3. Đừng tối ưu chỉ theo tốc độ cao nhất

Một batch lớn hơn có thể tăng throughput trong benchmark đơn luồng nhưng làm:

- p99 commit latency tăng.
- Replica apply lag tăng kéo dài.
- Lock wait và deadlock tăng.
- Truy vấn OLTP bị chậm do I/O hoặc cache pressure.
- Rollback và retry trở nên đắt đỏ.

Hãy chọn batch đạt throughput bền vững trong khi giữ độ trễ replica và truy vấn khác trong giới hạn chấp nhận được.

## 6. Bulk load và các phương thức nạp dữ liệu

Khi nạp số lượng lớn, dùng cơ chế bulk load của DBMS thường hiệu quả hơn gửi từng INSERT riêng lẻ. Các công cụ bulk có thể giảm round trip, gom thao tác và tối ưu đường ghi.

| Hệ quản trị | Cơ chế thường dùng | Điểm cần kiểm tra |
|---|---|---|
| PostgreSQL | COPY FROM, INSERT ... SELECT, multi-row INSERT | WAL, trigger/constraint, index maintenance, transaction size và replication slot |
| MySQL/InnoDB | LOAD DATA, multi-row INSERT, INSERT ... SELECT | redo/undo, binlog, autocommit, secondary index và replica apply |
| SQL Server | BULK INSERT, bcp, SqlBulkCopy | recovery model, minimal logging conditions, lock behavior, transaction log và availability group |
| Oracle | SQL*Loader, direct-path insert, INSERT ... SELECT | direct-path restrictions, redo/undo policy, indexes, constraints và Data Guard apply |

Bulk load không có nghĩa là không sinh log hoặc không cần kiểm tra constraint. Mức logging, tính nguyên tử, lock và replication phụ thuộc chế độ, phiên bản, recovery configuration và loại thao tác.

### 6.1. PostgreSQL COPY

Ví dụ nạp dữ liệu từ luồng hoặc file:

~~~sql
COPY staging_events (event_id, tenant_id, occurred_at, event_type)
FROM STDIN
WITH (FORMAT csv, HEADER true);
~~~

COPY thường giảm overhead so với gửi từng câu INSERT. Nếu nạp trực tiếp vào bảng được logical/physical replication theo dõi, thay đổi vẫn có thể tạo WAL và ảnh hưởng replica. Cần đo WAL generation, replication lag và dung lượng slot.

### 6.2. MySQL LOAD DATA

LOAD DATA có thể nạp nhiều hàng hiệu quả hơn các INSERT đơn lẻ. Cần kiểm tra cấu hình transaction, autocommit, binlog format, index maintenance và khả năng áp dụng trên replica. Việc tắt unique checks hoặc foreign_key_checks chỉ nên làm khi đã có quy trình bảo đảm dữ liệu hợp lệ và kiểm tra lại sau nạp; không được dùng như mẹo mặc định.

### 6.3. SQL Server bulk load

BULK INSERT, bcp hoặc SqlBulkCopy có thể tăng tốc nạp. Điều kiện minimal logging phụ thuộc recovery model, TABLOCK, cấu trúc bảng, index và các yêu cầu khác. Không được giả định mọi bulk load đều minimal-logged hoặc không ảnh hưởng transaction log. Theo dõi log reuse, log backup và replica/availability group queue.

### 6.4. Oracle direct-path load

SQL*Loader hoặc direct-path insert có thể sử dụng đường nạp khác với conventional insert. Mức redo, undo, constraint, trigger và Data Guard behavior phụ thuộc chế độ và cấu hình. Kiểm tra tài liệu phiên bản trước khi chọn NOLOGGING hoặc các tùy chọn giảm logging; giảm logging có thể ảnh hưởng khả năng phục hồi và standby.

## 7. Chia lô mà vẫn giữ được tính đúng đắn

Chia một transaction lớn thành nhiều transaction nhỏ giúp giới hạn tài nguyên, nhưng có thể làm thay đổi ngữ nghĩa nghiệp vụ. Nếu batch 1 commit và batch 2 thất bại, dữ liệu của batch 1 đã tồn tại.

Trước khi chia lô, xác định:

- Toàn bộ công việc có bắt buộc nguyên tử hay không?
- Có thể chấp nhận trạng thái dữ liệu từng phần trong lúc nạp không?
- Cách nhận biết batch đã commit?
- Cách retry khi mất kết nối ngay sau commit nhưng ứng dụng chưa nhận được phản hồi?
- Cách tránh ghi trùng khi retry?
- Cách khôi phục hoặc bù trừ khi batch sau thất bại?

### 7.1. Checkpoint theo khóa ổn định

Một job có thể ghi nhận khóa cuối cùng đã xử lý thành công. Ví dụ, nạp theo dải event_id:

~~~sql
INSERT INTO target_events (event_id, tenant_id, occurred_at, event_type)
SELECT event_id, tenant_id, occurred_at, event_type
FROM staging_events
WHERE event_id > :last_committed_id
  AND event_id <= :batch_end_id
ORDER BY event_id;
~~~

Sau khi transaction commit thành công, cập nhật checkpoint tương ứng. Checkpoint phải được lưu một cách nhất quán với batch: nếu dữ liệu đã commit nhưng checkpoint chưa commit, lần chạy sau có thể lặp lại batch; nếu checkpoint được cập nhật trước dữ liệu, job có thể bỏ sót dữ liệu.

Một cách an toàn là cập nhật dữ liệu và checkpoint trong cùng transaction nếu chúng nằm trong cùng cơ sở dữ liệu và cùng ranh giới commit. Nếu checkpoint nằm ở hệ thống khác, cần thiết kế idempotency hoặc giao thức điều phối phù hợp.

### 7.2. Idempotency và chống trùng

Retry phải không tạo ra kết quả sai. Các cách thường dùng:

- Khóa duy nhất ổn định trên business key hoặc event_id.
- INSERT ... ON CONFLICT/UPSERT với quy tắc cập nhật rõ ràng.
- Bảng staging có batch_id và trạng thái xử lý.
- Ghi nhận từng batch đã commit bằng một khóa idempotency.
- Đối chiếu số hàng và checksum theo phạm vi sau nạp.

Không dùng UPSERT một cách máy móc. Nếu thao tác retry ghi đè dữ liệu mới hơn bằng dữ liệu cũ, hệ thống có thể mất cập nhật hợp lệ. Quy tắc xử lý xung đột phải dựa trên version, timestamp nghiệp vụ hoặc nguồn dữ liệu có thẩm quyền.

### 7.3. Staging rồi publish

Khi cần dữ liệu xuất hiện đầy đủ cho người đọc, có thể nạp vào staging trước, xác minh dữ liệu, rồi chuyển sang trạng thái sẵn sàng bằng một thao tác publish nhỏ. Tùy DBMS, có thể dùng bảng staging, partition exchange/switch, metadata flag hoặc transaction cuối.

Staging không tự động bảo đảm atomic publish. Cần xác minh cách chuyển dữ liệu, index, constraint, quyền truy cập và replication hoạt động trong DBMS cụ thể.

## 8. Index, constraint và trigger làm tăng chi phí nạp

Mỗi hàng ghi có thể kéo theo công việc ngoài việc ghi heap hoặc clustered data:

- Duy trì từng secondary index.
- Kiểm tra unique constraint.
- Kiểm tra foreign key.
- Chạy trigger.
- Cập nhật materialized view hoặc bảng audit.
- Tạo WAL/redo/transaction log cho các thay đổi liên quan.

Nếu bảng có nhiều index, bulk load có thể bị giới hạn bởi chi phí cập nhật index hơn là tốc độ đọc dữ liệu đầu vào.

### 8.1. Nạp vào staging rồi xây dựng index

Với bảng mới hoặc batch dữ liệu lớn, đôi khi có thể nạp vào staging trước rồi tạo index sau. Tạo index một lần có thể hiệu quả hơn duy trì index cho từng hàng trong suốt quá trình nạp.

Nhưng cách này có trade-off:

- Trong lúc nạp, dữ liệu chưa có index để truy vấn.
- Tạo index sau đó cần CPU, memory và I/O lớn.
- Có thể phát sinh lock hoặc thời gian bảo trì.
- Unique/FK constraint cần được kiểm tra trước khi publish.
- Replication vẫn phải tiếp nhận thay đổi dữ liệu và có thể cả DDL/index build tùy DBMS.

Không drop index trên bảng production đang phục vụ workload chỉ để tăng tốc một lần nạp nếu chưa đánh giá truy vấn phụ thuộc và thời gian xây dựng lại.

### 8.2. Thứ tự nạp và khóa ngoại

Nếu có quan hệ cha-con, nạp bảng cha trước rồi đến bảng con có thể giảm lỗi tham chiếu. Nếu cần tạm hoãn constraint hoặc dùng cơ chế bulk-specific, phải có bước kiểm tra toàn bộ quan hệ sau nạp và hiểu rõ giới hạn của DBMS.

## 9. Lock duration và tác động đến workload đang chạy

Transaction dài có thể giữ lock lâu. Tác động phụ thuộc isolation level, loại thao tác và DBMS:

- UPDATE/DELETE giữ row/key lock trên hàng bị sửa cho đến commit hoặc rollback trong nhiều hệ quản trị.
- DDL hoặc thao tác partition có thể cần lock ở phạm vi rộng hơn.
- Range scan hoặc predicate lock ở một số isolation level có thể chặn thao tác khác.
- Transaction dài trong MVCC có thể giữ snapshot cũ, làm chậm việc thu hồi phiên bản dữ liệu hoặc vacuum/purge.

Khi bulk load chạy cùng OLTP, cần đo:

- Lock wait time và blocked sessions.
- Deadlock frequency.
- Transaction age và thời gian giữ lock.
- Query latency của workload đọc/ghi bình thường.
- Bloat, undo history hoặc version store nếu DBMS có cơ chế tương ứng.

Chia batch có thể giải phóng lock sau mỗi commit, nhưng cũng có thể làm các giao dịch khác nhìn thấy dữ liệu từng phần. Cần lựa chọn ranh giới commit theo yêu cầu nghiệp vụ.

## 10. Log pressure, checkpoint và dung lượng lưu trữ

Primary phải ghi log đủ để đáp ứng durability và replication. Bulk load làm log tăng nhanh có thể gây:

- Log file/WAL segment tăng dung lượng.
- Checkpoint dày hơn hoặc write burst.
- Log flush latency tăng.
- Disk bandwidth bão hòa.
- Log backup hoặc archive không theo kịp.
- Replication backlog tăng.
- Log không thể tái sử dụng do replica, slot hoặc backup còn giữ tham chiếu.

Từng DBMS quản lý log khác nhau:

- PostgreSQL dùng WAL; replication slot có thể giữ WAL chưa được consumer xác nhận, khiến pg_wal tăng dung lượng.
- MySQL dùng redo log cho crash recovery và binary log cho replication/PITR; đây là hai luồng log khác mục đích.
- SQL Server dùng transaction log và log backup; availability group có send queue và redo queue riêng.
- Oracle dùng redo log và archive log; Data Guard có transport/apply lag và standby redo processing.

Không xóa thủ công file log để giải phóng dung lượng. Hãy xác định nguyên nhân log chưa được tái sử dụng và xử lý theo cơ chế quản trị của DBMS.

## 11. Đo replication lag đúng cách

Một chỉ số thời gian duy nhất có thể không phản ánh đầy đủ backlog. Nên theo dõi cả vị trí log và hàng đợi:

- Log position hoặc sequence trên primary và replica.
- Số byte log chưa gửi.
- Số byte đã nhận nhưng chưa flush.
- Số byte đã flush nhưng chưa replay/apply.
- Thời gian trễ gửi, nhận và áp dụng.
- Tốc độ log generation và apply throughput.
- Kích thước hàng đợi và xu hướng tăng/giảm theo thời gian.

### 11.1. PostgreSQL

Các nguồn quan sát thường dùng:

- pg_stat_replication: trạng thái WAL sender và vị trí write/flush/replay của standby.
- pg_replication_slots: restart_lsn và confirmed_flush_lsn đối với slot tương ứng; slot có thể giữ WAL cần thiết cho consumer.
- pg_stat_wal hoặc các metric WAL liên quan theo phiên bản.
- pg_stat_database và pg_stat_io ở phiên bản hỗ trợ để quan sát I/O.

Các trường write_lag, flush_lag và replay_lag phản ánh độ trễ gần đây giữa các mốc WAL trong một số điều kiện; chúng không luôn tương đương thời gian cần để replica bắt kịp toàn bộ backlog. Hãy xem cả LSN distance và xu hướng WAL generation/apply.

### 11.2. MySQL

Các nguồn thường dùng gồm SHOW REPLICA STATUS và Performance Schema replication tables tùy phiên bản. Theo dõi:

- Source log position và replica executed position.
- Relay log space.
- Replica SQL/applier worker status.
- Worker queue hoặc transaction apply bottleneck.
- Seconds_Behind_Source nếu có, nhưng không coi đây là chỉ số duy nhất.

Seconds_Behind_Source có thể không phản ánh đầy đủ backlog trong mọi trạng thái, đặc biệt khi replication dừng, đồng hồ lệch hoặc worker đang xử lý transaction lớn.

### 11.3. SQL Server

Với Always On availability groups, có thể theo dõi log send queue, redo queue, log send rate và redo rate qua các dynamic management views phù hợp. Send queue tăng gợi ý log chưa được gửi/đồng bộ đến secondary; redo queue tăng gợi ý secondary nhận log nhưng chưa redo kịp.

### 11.4. Oracle

Với Data Guard, theo dõi transport lag và apply lag cùng trạng thái archive/redo apply. Cần phân biệt log chưa chuyển đến standby với log đã nhận nhưng chưa apply.

Tên view và trường thay đổi theo phiên bản, quyền và cấu hình. Hãy đối chiếu tài liệu hệ quản trị đang vận hành.

## 12. Điều tiết tốc độ nạp (backpressure)

Một job nạp dữ liệu nên có khả năng giảm tốc hoặc tạm dừng khi primary hoặc replica chịu áp lực. Đây là backpressure: tốc độ producer được điều chỉnh theo khả năng của consumer và giới hạn tài nguyên.

Một chính sách đơn giản có thể:

- Tăng batch khi commit nhanh, log ổn định và replica lag thấp.
- Giữ batch khi throughput đạt mục tiêu và độ trễ không tăng.
- Giảm batch hoặc giảm số worker khi apply lag tăng liên tục.
- Tạm dừng khi backlog vượt ngưỡng, disk log gần đầy hoặc truy vấn OLTP bị ảnh hưởng.
- Tiếp tục sau khi replica bắt kịp và tài nguyên trở lại ngưỡng an toàn.

Ví dụ logic điều tiết:

~~~text
if replica_apply_lag > high_threshold:
    reduce_workers()
    reduce_batch_size()
    wait_for_lag_to_fall()
elif replica_apply_lag < low_threshold
     and primary_resources_are_healthy:
    increase_batch_size_gradually()
else:
    keep_current_rate()
~~~

Ngưỡng phải dựa trên SLO và dung lượng thực tế. Dùng hysteresis hoặc hai ngưỡng cao/thấp để tránh job liên tục tăng giảm tốc. Nên giới hạn mức thay đổi mỗi lần và có tốc độ tối đa đã kiểm thử.

Nếu replica là thành phần phục vụ truy vấn đọc quan trọng, lag threshold cần phản ánh yêu cầu freshness của ứng dụng, không chỉ dung lượng log còn trống.

## 13. Ví dụ nạp dữ liệu theo batch có checkpoint

Giả sử cần nạp 10 triệu sự kiện từ staging sang bảng đích. Mỗi batch chọn dải event_id tăng dần, commit dữ liệu và checkpoint trong cùng transaction.

Ví dụ minh họa cho PostgreSQL:

~~~sql
BEGIN;

INSERT INTO target_events (
    event_id,
    tenant_id,
    occurred_at,
    event_type
)
SELECT
    event_id,
    tenant_id,
    occurred_at,
    event_type
FROM staging_events
WHERE event_id > :last_committed_id
  AND event_id <= :batch_end_id
ORDER BY event_id
ON CONFLICT (event_id) DO NOTHING;

UPDATE load_jobs
SET last_committed_id = :batch_end_id,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id;

COMMIT;
~~~

Đây là mẫu khái niệm; cần xác nhận cú pháp tham số và bảng checkpoint của ứng dụng. Nếu ON CONFLICT DO NOTHING được dùng, phải có quy tắc xử lý khi hàng trùng nhưng nội dung khác. Không được mặc định mọi conflict đều là bản ghi đã nạp đúng.

Quy trình:

1. Lấy checkpoint đã commit.
2. Chọn batch_end_id theo số hàng hoặc giới hạn byte/thời gian.
3. Ghi dữ liệu và cập nhật checkpoint trong cùng transaction.
4. Commit.
5. Ghi nhận rows/s, log bytes, commit latency và replica lag.
6. Điều chỉnh batch hoặc số worker theo backpressure.
7. Khi job khởi động lại, tiếp tục từ checkpoint và bảo đảm thao tác retry idempotent.

Nếu dữ liệu nguồn không có khóa tăng dần hoặc có thể đến muộn, cần dùng cursor ổn định khác, watermark kết hợp với trạng thái nguồn hoặc bảng manifest batch. Không dùng offset của một SELECT không có thứ tự duy nhất làm checkpoint.

## 14. Đọc tải và độ trễ dưới concurrency

Bulk load thường không chạy một mình. Nó cạnh tranh CPU, memory, disk bandwidth, log flush, buffer cache và worker với workload OLTP.

Khi tăng số worker nạp:

- Throughput có thể tăng ban đầu nhờ tận dụng nhiều CPU và I/O.
- Sau một điểm, log device hoặc data device có thể bão hòa.
- Nhiều transaction đồng thời làm tăng lock contention và memory pressure.
- Replica apply có thể không song song tương ứng.
- p95/p99 của truy vấn đọc và commit có thể tăng dù rows/second của job vẫn cao.

Hãy benchmark với tải nền đại diện. Một bài đo chỉ chạy bulk load trên môi trường nhàn rỗi không thể dự đoán đầy đủ tác động production.

### 14.1. Chọn số worker

Bắt đầu với ít worker, tăng từng bước và theo dõi throughput cùng các hàng đợi. Nếu số worker tăng nhưng log bytes/s không tăng, trong khi lock wait hoặc I/O queue tăng, thêm worker không còn đem lại lợi ích.

### 14.2. Tránh nhiều batch chồng lấn cùng một vùng dữ liệu

Nếu các worker cùng cập nhật khóa hoặc partition nóng, chúng có thể tranh chấp lock và page latch. Chia công việc theo dải khóa hoặc partition độc lập có thể giảm chồng lấn, nhưng cần bảo đảm không tạo skew và không phá vỡ thứ tự ràng buộc.

### 14.3. Giữ transaction ngắn trong các bước điều phối

Không giữ transaction mở trong lúc ứng dụng đọc file, gọi API hoặc chờ worker khác. Chuẩn bị dữ liệu bên ngoài transaction; chỉ mở transaction trong khoảng cần thiết để ghi và cập nhật checkpoint.

## 15. Khác biệt giữa replication đồng bộ và bất đồng bộ

### Replication bất đồng bộ

Primary có thể commit trước khi replica xác nhận đã nhận hoặc áp dụng log. Cách này giảm phụ thuộc trực tiếp vào tốc độ replica đối với commit latency, nhưng replica có thể tụt lại và mất một phần thay đổi chưa được chuyển khi primary gặp sự cố, tùy cấu hình failover.

Trong bulk load, throughput primary có thể cao hơn tốc độ apply của replica. Cần điều tiết để backlog không tăng ngoài khả năng lưu trữ và yêu cầu freshness.

### Replication đồng bộ

Một số cấu hình yêu cầu primary chờ replica xác nhận log đã được nhận hoặc flush xuống lưu trữ bền vững trước khi commit hoàn tất. Điều này có thể tăng durability và giảm mất dữ liệu trong một số kịch bản, nhưng commit latency phụ thuộc mạng và trạng thái replica.

Phải phân biệt xác nhận nhận log, flush log và apply log. Một replica xác nhận flush chưa chắc đã áp dụng xong để truy vấn đọc nhìn thấy dữ liệu.

Không thay đổi chế độ synchronous/asynchronous chỉ để tăng tốc nạp mà chưa đánh giá yêu cầu RPO, RTO, failover và freshness. Đây là quyết định kiến trúc độ bền dữ liệu.

## 16. Các mẫu lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Phép kiểm tra tiếp theo |
|---|---|---|
| Commit latency tăng khi batch lớn | Flush log, lock duration, checkpoint hoặc transaction bookkeeping | Đo thời gian commit, log flush latency và lock wait |
| Primary ghi nhanh nhưng replica lag tăng | Log generation vượt apply throughput | So sánh log bytes/s với apply rate và backlog theo thời gian |
| Disk log tăng nhanh | WAL/binlog/transaction log bị giữ hoặc không tái sử dụng | Kiểm tra backup, replication slot, archive và log reuse wait |
| Replica nhận log nhanh nhưng dữ liệu đọc vẫn cũ | Apply/redo chậm hoặc transaction lớn chưa hoàn tất | So sánh receive/flush position với replay/apply position |
| Throughput không tăng khi tăng worker | I/O, log device, lock hoặc replica trở thành giới hạn | Đo queue depth, wait events, CPU và apply worker |
| Retry tạo dữ liệu trùng | Batch không idempotent hoặc checkpoint không nhất quán | Kiểm tra unique key, batch manifest và ranh giới commit |
| Bulk load làm OLTP chậm | Cạnh tranh buffer, CPU, I/O, log flush hoặc lock | So sánh p95/p99 OLTP trước/trong/sau load |
| Rollback kéo dài | Transaction thay đổi quá nhiều hàng | Đo rollback time và chia công việc theo ranh giới nghiệp vụ nếu cho phép |

## 17. Quy trình benchmark và điều chỉnh

1. **Chọn workload đại diện.** Xác định nguồn dữ liệu, số hàng, độ rộng hàng, index, trigger, constraint và số writer.
2. **Ghi đường cơ sở.** Đo rows/s, bytes/s, commits/s, log bytes/s, commit latency, CPU, I/O, memory và replica lag khi chưa nạp.
3. **Chọn batch ban đầu.** Dùng batch có giới hạn số hàng, byte và thời gian transaction.
4. **Tăng batch có kiểm soát.** Thay đổi một yếu tố mỗi lần và giữ nguyên dữ liệu, cấu hình cùng tải nền.
5. **Tăng worker riêng biệt.** Sau khi chọn được batch hợp lý, thử số worker khác nhau để tìm mức concurrency bền vững.
6. **Theo dõi replica.** Đo send/receive/flush/apply backlog, log generation và apply rate.
7. **Theo dõi workload khác.** Ghi p95/p99 của truy vấn đọc/ghi, lock wait, deadlock và resource queue.
8. **Thử tình huống lỗi.** Ngắt job giữa batch, mất kết nối ngay sau commit, retry và xác nhận không mất/trùng dữ liệu.
9. **Kiểm tra phục hồi.** Xác nhận log, backup, archive và replica có thể tiếp tục đồng bộ; kiểm tra dung lượng lưu trữ.
10. **Chọn cấu hình bền vững.** Ưu tiên mức throughput ổn định mà replica theo kịp và SLO của workload khác vẫn đạt.

Đo nhiều lần và dùng cùng điều kiện. Nếu cache nóng/lạnh hoặc trạng thái replica khác nhau giữa các lần đo, ghi rõ bối cảnh để tránh so sánh sai.

## 18. Những sai lầm thường gặp

- **Tối đa hóa rows/second trên primary.** Tốc độ primary cao có thể làm replica lag và truy vấn đọc xấu đi.
- **Chọn batch chỉ bằng số hàng.** Payload, index và trigger làm lượng log mỗi hàng khác nhau.
- **Gộp toàn bộ job vào một transaction.** Rollback, lock và apply backlog có thể rất lớn.
- **Commit từng hàng.** Commit overhead và round trip có thể áp đảo chi phí ghi.
- **Dùng savepoint thay cho commit batch.** Savepoint không kết thúc transaction, không giải phóng toàn bộ lock và không biến log thành các transaction độc lập cho replica.
- **Tắt logging hoặc constraint mà không có quy trình kiểm tra.** Có thể làm giảm khả năng phục hồi hoặc cho phép dữ liệu sai.
- **Tăng worker vô hạn.** Có thể chỉ làm tăng cạnh tranh I/O và lock.
- **Dựa vào một chỉ số replication lag.** Cần phân biệt send, receive, flush và apply.
- **Coi Seconds_Behind_Source hoặc một time lag là tuyệt đối.** Chỉ số có giới hạn và cần đọc cùng vị trí log, queue và trạng thái applier.
- **Cập nhật checkpoint tách rời dữ liệu mà không có idempotency.** Có thể bỏ sót hoặc ghi trùng khi job lỗi.
- **Chia transaction mà không xem tính nguyên tử.** Người đọc có thể thấy trạng thái dữ liệu dở dang.
- **Thử bulk load trên môi trường không có tải nền rồi áp dụng trực tiếp.** Không phản ánh cạnh tranh tài nguyên trong production.

## 19. Checklist vận hành

- [ ] Đã đo batch size theo số hàng, byte log và thời gian transaction.
- [ ] Đã xác định giới hạn lock duration, rollback time và commit latency.
- [ ] Đã đo rows/s, bytes/s, commits/s và log bytes/s.
- [ ] Đã phân biệt send, receive, flush và apply lag.
- [ ] Đã theo dõi backlog log và tốc độ replica bắt kịp.
- [ ] Đã kiểm tra log retention, archive, backup và replication slot/queue.
- [ ] Đã chọn bulk load phù hợp với DBMS và xác minh điều kiện logging.
- [ ] Đã đánh giá chi phí index, constraint, trigger và foreign key.
- [ ] Đã xác định transaction có thể chia nhỏ mà vẫn giữ ngữ nghĩa nghiệp vụ.
- [ ] Đã có checkpoint nhất quán, idempotency và retry an toàn.
- [ ] Đã có backpressure để giảm tốc hoặc dừng khi replica/resource vượt ngưỡng.
- [ ] Đã benchmark với workload nền và nhiều mức concurrency.
- [ ] Đã kiểm tra p95/p99 của truy vấn đọc/ghi trong lúc nạp.
- [ ] Đã thử khôi phục sau lỗi giữa các batch và sau commit không nhận được phản hồi.
- [ ] Đã xác nhận số hàng, khóa duy nhất, quan hệ tham chiếu và checksum sau nạp.

Kích thước transaction, tốc độ nạp và replication lag là ba mặt của cùng một đường ghi. Transaction quá nhỏ tạo nhiều overhead; transaction quá lớn làm tăng lock duration, log, rollback và thời gian apply; tốc độ nạp vượt năng lực replica khiến backlog tăng liên tục. Hãy chọn batch bằng số đo về thời gian, byte log và tài nguyên, nạp theo lô có checkpoint/idempotency khi nghiệp vụ cho phép, đồng thời điều tiết producer theo khả năng của replica. Một cấu hình tốt là cấu hình duy trì throughput ổn định, độ trễ đọc/ghi trong SLO và khả năng phục hồi rõ ràng trên toàn hệ thống.
