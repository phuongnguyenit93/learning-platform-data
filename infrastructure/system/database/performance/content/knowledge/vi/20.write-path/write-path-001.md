# Nhật ký giao dịch, WAL hoặc redo và quá trình commit

Khi ứng dụng ghi dữ liệu, DBMS không nhất thiết ghi ngay mọi trang dữ liệu đã thay đổi xuống các file bảng. Hệ quản trị cần bảo đảm transaction có thể được phục hồi sau lỗi tiến trình, mất điện hoặc khởi động lại. Để làm được điều đó, DBMS ghi lại thông tin thay đổi vào nhật ký giao dịch trước khi các trang dữ liệu tương ứng được ghi bền vững. Cơ chế này thường được mô tả bằng nguyên tắc Write-Ahead Logging (WAL); nhiều hệ quản trị gọi phần nhật ký phục hồi là redo log hoặc transaction log.

Quá trình commit là điểm mà DBMS xác nhận transaction đã hoàn tất theo mức bảo đảm durability được cấu hình. Với chế độ commit đồng bộ, DBMS thường phải bảo đảm các bản ghi log cần thiết, bao gồm commit record, đã được flush tới vùng lưu trữ bền vững trước khi trả thành công cho ứng dụng. Các data page có thể vẫn nằm trong buffer cache và được ghi xuống sau đó. Đây là lý do log write và log flush có thể quyết định độ trễ của một transaction ngay cả khi thao tác cập nhật bảng rất nhỏ.

Trong chương **Đường ghi dữ liệu**, bài học này giải thích vai trò của nhật ký giao dịch, WAL/redo và quá trình commit trong mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Ta sẽ theo dõi đường đi của một transaction, phân biệt log với data page, hiểu group commit và checkpoint, nhận diện các điểm nghẽn I/O, rồi kiểm chứng thay đổi bằng số liệu thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao DBMS ghi log trước khi ghi các data page đã thay đổi.
- Phân biệt transaction log, WAL, redo log, undo log, binary log và log phục vụ audit.
- Mô tả các bước chính từ UPDATE/INSERT đến commit acknowledgement.
- Hiểu commit record, log sequence number (LSN) và yêu cầu flush log.
- Phân biệt durability của commit với việc data page đã được ghi xuống file bảng.
- Giải thích group commit, checkpoint và crash recovery.
- Nhận diện cách PostgreSQL, MySQL/InnoDB, SQL Server và Oracle tổ chức log ở mức khái niệm.
- Đọc các chỉ số log write, log flush, wait, checkpoint và replication để tìm nút thắt.
- Đánh giá ảnh hưởng của transaction size, commit frequency, storage latency và cấu hình durability.
- Thiết kế phép đo trước/sau mà vẫn giữ đúng yêu cầu bền vững của dữ liệu.

## 1. Nhật ký giao dịch giải quyết vấn đề gì?

Một transaction có thể cập nhật nhiều dòng hoặc nhiều trang dữ liệu. Nếu hệ thống gặp sự cố giữa chừng, DBMS phải xác định thay đổi nào đã được commit và thay đổi nào cần được hoàn tác hoặc bỏ qua.

Hãy xét transaction chuyển tiền:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

COMMIT;
~~~

Hai cập nhật phải được xem là một đơn vị nguyên tử. Nếu máy chủ dừng sau câu UPDATE thứ nhất nhưng trước khi transaction commit, khi phục hồi DBMS không được để tài khoản 10 bị trừ tiền mà tài khoản 20 chưa được cộng tiền. Nếu commit đã được xác nhận bền vững trước khi máy chủ dừng, DBMS phải có khả năng phục hồi kết quả của cả transaction, kể cả khi một số data page chưa từng được ghi xuống file bảng.

Nhật ký giao dịch cung cấp bằng chứng và thông tin cần thiết để phục hồi. Tùy kiến trúc DBMS, log có thể chứa thông tin redo, undo hoặc dạng record phục vụ cả hai mục tiêu. DBMS dùng log sequence, transaction state và checkpoint để quyết định phần nào cần phát lại hoặc hoàn tác.

### 1.1. Log không phải là bản sao của file dữ liệu

Transaction log thường ghi các thay đổi theo một định dạng tối ưu cho việc append tuần tự. Nó không nhất thiết lưu toàn bộ bản ghi như một bản sao đầy đủ của bảng. Log record có thể mô tả trang, vị trí, transaction, thao tác hoặc dữ liệu cần thiết để tái tạo thay đổi.

Data file và log file phục vụ mục đích khác nhau:

- **Data file:** lưu các trang dữ liệu và index ở trạng thái được quản lý bởi DBMS.
- **Transaction log/WAL/redo:** lưu lịch sử thay đổi cần cho phục hồi và, tùy hệ thống, replication.
- **Undo information:** hỗ trợ rollback hoặc đọc phiên bản nhất quán trong các engine có cơ chế undo riêng.
- **Binary/logical change log:** có thể mô tả thay đổi ở mức logic để replication, CDC hoặc tích hợp hệ thống.
- **Audit log:** ghi ai đã làm gì theo mục tiêu kiểm toán; không mặc nhiên thay thế transaction log.

Một transaction có thể làm tăng log bytes nhiều hơn lượng dữ liệu ứng dụng gửi vào vì DBMS còn ghi metadata, index changes, page information và thông tin phục hồi.

### 1.2. WAL là nguyên tắc ghi trước

WAL là viết tắt của Write-Ahead Logging. Quy tắc cốt lõi là log record mô tả thay đổi phải được ghi bền vững trước khi data page chứa thay đổi đó được ghi xuống nơi lưu trữ bền vững.

Ví dụ, một trang bảng trong buffer cache được thay đổi. DBMS gắn thông tin log với thay đổi đó. Trước khi ghi trang xuống data file, hệ thống phải bảo đảm phần log cần thiết đã được flush. Nhờ vậy, nếu trang dữ liệu được ghi dở hoặc máy chủ dừng đột ngột, DBMS có thể dùng log để phục hồi.

Quy tắc này cho phép DBMS trả commit mà không cần đồng bộ ghi tất cả data page của transaction ngay tại thời điểm commit. Thay vào đó, log được flush theo yêu cầu durability; data page được ghi sau theo lịch của buffer manager và checkpoint.

## 2. Đường đi của một transaction ghi

Một transaction ghi thường đi qua các bước khái niệm sau. Chi tiết nội bộ khác nhau theo DBMS, nhưng mô hình này giúp hiểu nơi phát sinh độ trễ.

~~~text
Ứng dụng gửi INSERT / UPDATE / DELETE
                |
                v
        DBMS kiểm tra quyền,
        constraint và khóa
                |
                v
        Đọc trang vào buffer
        và thay đổi trang trong RAM
                |
                v
        Tạo log record trong
        log/WAL buffer
                |
                v
        Ứng dụng yêu cầu COMMIT
                |
                v
        Ghi commit record và
        flush log đến commit LSN
                |
                v
        Xác nhận COMMIT cho ứng dụng
                |
                v
        Data page được ghi xuống
        file dữ liệu sau đó
        bởi background writer/checkpoint
~~~

Đây là luồng khái quát. Một số engine tạo log record xen kẽ với việc thay đổi page; một số có nhiều tầng log hoặc đồng bộ với binary log. Không nên hiểu sơ đồ là thứ tự lệnh nội bộ chính xác cho mọi sản phẩm.

### 2.1. Đọc và sửa trang trong buffer pool

DBMS thường đọc trang chứa dòng cần cập nhật vào bộ nhớ đệm nếu trang chưa có sẵn. Engine kiểm tra khóa, visibility, constraint và các điều kiện cần thiết, sau đó thay đổi phiên bản dòng hoặc cấu trúc trang.

Trang đã thay đổi nhưng chưa được ghi xuống data file được gọi là dirty page. Dirty page có thể tồn tại trong buffer cache một khoảng thời gian. DBMS không cần ghi nó ngay tại mỗi UPDATE.

### 2.2. Tạo log record

Khi dữ liệu thay đổi, DBMS tạo log record mô tả thay đổi theo định dạng của engine. Log có thể bao gồm transaction identifier, page identifier, LSN, thông tin redo/undo hoặc dữ liệu cần thiết để phục hồi.

Log record thường được đưa vào log buffer trong RAM trước khi được ghi xuống file log. Việc gom nhiều record vào buffer giúp giảm số lần I/O nhỏ.

### 2.3. COMMIT và commit record

Khi ứng dụng gửi COMMIT, DBMS xác định các log record thuộc transaction và tạo record đánh dấu transaction commit. Một số hệ thống còn phải phối hợp với các log khác hoặc replication.

Trong chế độ synchronous durability, DBMS không nên trả thành công trước khi log đã được flush bền vững đến vị trí cần thiết. Vị trí này thường được biểu diễn bằng LSN hoặc một sequence tương đương.

### 2.4. Commit acknowledgement

Sau khi điều kiện durability đã thỏa mãn, DBMS gửi phản hồi thành công về ứng dụng. Ứng dụng có thể tiếp tục xử lý hoặc xác nhận nghiệp vụ với người dùng.

Nếu cấu hình cho phép delayed/asynchronous commit, thời điểm trả lời có thể sớm hơn thời điểm log thực sự được flush. Điều này giảm độ trễ nhưng tạo cửa sổ mà transaction vừa được báo thành công vẫn có thể mất khi hệ thống gặp sự cố nghiêm trọng. Cần hiểu rõ cấu hình và mức rủi ro trước khi sử dụng.

### 2.5. Data page được ghi sau

Sau commit, dirty page có thể được ghi xuống data file bởi background writer, page cleaner hoặc checkpoint. Khi DBMS phục hồi sau crash, log được dùng để đưa các trang về trạng thái nhất quán.

Vì vậy, **commit đã bền vững** không đồng nghĩa **mọi data page của transaction đã được ghi xuống file bảng**. Đây là một đặc tính thiết kế chủ đích của WAL.

## 3. Write-ahead rule và log sequence number

### 3.1. Log sequence number

Nhiều DBMS dùng một số thứ tự log tăng dần để định vị tiến trình ghi. SQL Server gọi là Log Sequence Number (LSN); PostgreSQL dùng vị trí WAL; các engine khác có sequence hoặc offset tương đương.

Một trang dữ liệu có thể ghi nhận LSN gần nhất liên quan đến thay đổi của trang. Trước khi flush trang đó, DBMS phải bảo đảm log đã được flush ít nhất đến vị trí cần thiết. Đây là cách thực thi write-ahead rule.

LSN giúp DBMS:

- Xác định log đã được ghi đến đâu.
- So sánh trạng thái trang với log trong recovery.
- Xác định ranh giới checkpoint.
- Theo dõi tiến độ replication hoặc backup trong những hệ thống hỗ trợ.
- Phát hiện log record cần thiết cho một trang đã được flush hay chưa.

Không phải mọi DBMS công khai cùng một loại LSN hoặc cùng cách biểu diễn. Ý nghĩa khái niệm là thứ tự log và điểm phục hồi.

### 3.2. Vì sao log thường ghi tuần tự?

Log thường được thiết kế để append theo thứ tự thay đổi. Ghi tuần tự có thể tận dụng hiệu quả throughput của storage hơn nhiều thao tác ghi ngẫu nhiên vào các data page rải rác.

Một transaction có thể thay đổi nhiều trang ở nhiều vị trí khác nhau trong data file, nhưng log records có thể được gom và ghi theo một luồng có thứ tự. Điều này giúp commit chỉ cần chờ log flush thay vì chờ từng data page.

Tuy nhiên, log write vẫn có thể là nút thắt nếu storage có latency flush cao, throughput không đủ, queue quá dài hoặc nhiều transaction cạnh tranh cùng một luồng log.

### 3.3. Log buffer và flush

Log buffer giữ các record mới trong RAM trước khi ghi xuống log file. DBMS flush log khi cần, ví dụ:

- Transaction cần commit với durability đồng bộ.
- Log buffer gần đầy.
- Một background process cần giải phóng buffer.
- Checkpoint hoặc cơ chế bảo trì yêu cầu log tiến đến một vị trí.
- Replication/archiving cần log đã được ghi.

Một transaction nhỏ có thể tạo rất ít log bytes nhưng vẫn phải chờ một lần flush. Vì vậy, độ trễ commit không tỷ lệ tuyến tính với số dòng được cập nhật. Storage flush latency và group commit thường có ảnh hưởng lớn.

## 4. Commit, durability và các mức đồng bộ

### 4.1. Commit bền vững có nghĩa gì?

Trong mô hình durability đồng bộ, khi DBMS trả COMMIT thành công, log cần thiết để phục hồi transaction phải được ghi qua cơ chế bảo đảm bền vững của hệ điều hành và storage. Thông thường DBMS dùng fsync hoặc cơ chế tương đương để yêu cầu flush.

Nếu thiết bị lưu trữ hoặc hypervisor báo hoàn tất flush không đúng với bảo đảm thực tế, durability có thể bị ảnh hưởng. Vì vậy, cấu hình DBMS và đặc tính storage phải được xem xét cùng nhau.

### 4.2. Commit không đòi hỏi flush toàn bộ data page

Tại commit, DBMS thường cần flush log đến commit record, không phải ghi tất cả page đã thay đổi. Điều này giảm latency vì log được ghi tuần tự và có thể gom nhiều transaction.

Data page được ghi sau theo chính sách buffer manager và checkpoint. Nếu xảy ra crash, recovery phát lại các thay đổi cần thiết. Cơ chế này cho phép transaction commit nhanh hơn so với việc buộc ghi đồng bộ mọi trang dữ liệu.

### 4.3. Synchronous và asynchronous/delayed commit

| Chế độ | Hành vi khái quát | Đánh đổi |
|---|---|---|
| Synchronous commit | Chờ log cần thiết được flush trước khi xác nhận | Durability mạnh hơn, latency phụ thuộc log flush |
| Asynchronous/delayed commit | Có thể xác nhận trước khi log được flush | Latency thấp hơn nhưng có thể mất các commit gần nhất khi crash |
| Synchronous replication | Có thể chờ replica xác nhận theo mức cấu hình | Tăng độ bền qua node nhưng latency phụ thuộc mạng và replica |
| Asynchronous replication | Primary không chờ replica xác nhận trước khi trả lời | Độ trễ thấp hơn nhưng replica có thể lag và mất dữ liệu mới nhất khi failover |

Tên gọi, phạm vi và ngữ nghĩa chính xác phụ thuộc DBMS. Synchronous commit ở primary không tự động đồng nghĩa transaction đã được lưu bền vững ở một replica khác. Cần phân biệt local durability và replication durability.

### 4.4. Không tắt durability để benchmark

Nếu tắt fsync, giảm flush hoặc dùng delayed commit chỉ để làm benchmark nhanh hơn, kết quả không còn phản ánh cấu hình durability mà ứng dụng sẽ sử dụng. Có thể dùng một chế độ yếu hơn trong thử nghiệm để xác định chi phí tương đối của log flush, nhưng phải ghi rõ điều kiện và không dùng số đo đó làm cam kết hiệu năng production.

## 5. Group commit: gom nhiều transaction vào một lần flush

### 5.1. Cách hoạt động

Nếu nhiều transaction commit gần nhau, DBMS có thể gom các log record và commit record của chúng rồi flush chung một lần. Khi flush hoàn tất, các transaction có commit record nằm trong phạm vi đó có thể được xác nhận.

Ví dụ khái niệm:

~~~text
Transaction A ----\
Transaction B -----+--> log buffer --> one durable flush --> acknowledge A, B, C
Transaction C ----/
~~~

Group commit giảm số lần flush vật lý trên mỗi transaction. Nó đặc biệt hữu ích khi nhiều client ghi đồng thời và log storage có latency flush đáng kể.

### 5.2. Throughput và latency

Group commit có thể tăng throughput vì một lần flush phục vụ nhiều transaction. Nhưng một transaction có thể phải chờ ngắn để được gom vào nhóm tiếp theo. Cơ chế này cân bằng giữa hiệu quả I/O và thời gian phản hồi.

Ở tải rất thấp, ít transaction đến cùng lúc nên lợi ích gom nhóm có thể nhỏ. Ở tải cao, nhiều transaction có thể chia sẻ một flush nhưng nếu storage đã bão hòa, latency vẫn tăng.

### 5.3. Group commit không thay thế batching ở ứng dụng

Group commit gom log flush ở tầng DBMS. Batching ở ứng dụng gom nhiều thao tác dữ liệu vào một transaction hoặc statement. Hai kỹ thuật khác nhau:

- Group commit giúp nhiều transaction độc lập chia sẻ một lần flush.
- Batch transaction giảm số commit và có thể giảm overhead mỗi dòng.
- Batch quá lớn giữ khóa lâu, tăng log volume và rollback cost.
- Transaction quá nhỏ tạo nhiều commit và nhiều lượt round-trip.

Hãy đo kích thước batch và concurrency phù hợp với SLA, tránh gom toàn bộ công việc thành một transaction khổng lồ.

## 6. Checkpoint và ghi data page

### 6.1. Checkpoint là gì?

Checkpoint là quá trình DBMS ghi nhận một điểm phục hồi và thúc đẩy các dirty page cần thiết xuống data file theo chính sách của engine. Checkpoint giúp giới hạn lượng log phải xem xét khi recovery và quản lý buffer cache.

Checkpoint không phải là COMMIT. Nó không quyết định transaction nào thành công ở tầng nghiệp vụ. Transaction đã commit vẫn được xác định bởi log; transaction chưa commit có thể cần undo hoặc được xử lý theo cơ chế recovery.

### 6.2. Checkpoint và log retention

DBMS không thể loại bỏ hoặc tái sử dụng mọi phần log cũ tùy ý nếu vẫn cần chúng cho crash recovery, backup, replication hoặc archiving. Checkpoint và tiến độ của các thành phần phụ thuộc log giúp xác định vùng log nào có thể được tái sử dụng hoặc dọn.

Một replica chậm hoặc archive destination bị lỗi có thể giữ log lâu hơn dự kiến. Hậu quả có thể là dung lượng WAL/redo tăng, log disk đầy hoặc tiến trình ghi bị ảnh hưởng.

### 6.3. Checkpoint quá dày hoặc quá thưa

Checkpoint quá dày có thể tạo nhiều data page writes, tăng I/O nền và làm latency biến động. Checkpoint quá thưa có thể khiến recovery phải xử lý lượng log lớn hơn và dirty page tích tụ nhiều hơn.

DBMS có cơ chế tự điều chỉnh và các tham số riêng. Không nên tăng/giảm checkpoint interval chỉ dựa trên một biểu đồ. Hãy quan sát checkpoint duration, write rate, dirty buffers, log generation rate, recovery objective và storage throughput.

### 6.4. Checkpoint spike

Khi nhiều dirty pages được ghi trong thời gian ngắn, storage có thể bị cạnh tranh với log flush và truy vấn đọc. Commit latency p95/p99 có thể tăng dù lượng log của từng transaction không đổi.

Nếu độ trễ commit tăng theo chu kỳ, hãy đối chiếu thời điểm checkpoint, data page writes, storage queue depth và log flush latency. Cần xác định liệu checkpoint tạo áp lực I/O hay một tác vụ nền khác cùng chạy.

## 7. Crash recovery: redo và undo

### 7.1. Vì sao cần recovery?

Máy chủ có thể dừng bất ngờ ở bất kỳ thời điểm nào. Sau khi khởi động lại, DBMS phải đưa database về trạng thái nhất quán, giữ các transaction đã commit bền vững và loại bỏ hiệu ứng của transaction chưa commit theo semantics của engine.

Recovery thường dựa trên log và checkpoint. Ở mức khái niệm, DBMS xác định điểm bắt đầu recovery, phân tích transaction/page state, phát lại thay đổi cần thiết và hoàn tác những thay đổi không được commit nếu kiến trúc engine yêu cầu.

### 7.2. Redo

Redo áp dụng lại thay đổi đã được ghi trong log khi data page trên đĩa chưa phản ánh đầy đủ thay đổi đó. Ví dụ transaction đã commit và log đã flush, nhưng page cập nhật vẫn chỉ nằm trong buffer cache lúc crash. Khi recovery, DBMS dùng redo record để tái tạo trạng thái đã commit.

Redo giúp durability không phụ thuộc vào việc data page được ghi đồng bộ ngay tại commit.

### 7.3. Undo

Undo hoàn tác thay đổi của transaction chưa commit hoặc cần rollback. Cách lưu và áp dụng undo khác nhau theo engine. InnoDB có undo log; SQL Server sử dụng thông tin trong transaction log để phục hồi/rollback theo kiến trúc của engine; Oracle có undo segments phục vụ rollback và read consistency. PostgreSQL sử dụng MVCC tuple versions và cơ chế cleanup khác với mô hình undo log truyền thống của InnoDB/Oracle.

Vì vậy, không nên giả định mọi DBMS đều có một file undo log riêng hoặc dùng cùng thuật toán. Điều cần hiểu là atomicity yêu cầu DBMS loại bỏ hiệu ứng chưa commit sau recovery.

### 7.4. Recovery có thể làm khởi động lâu

Nếu checkpoint xa, log nhiều, storage chậm hoặc transaction dài, recovery có thể mất thời gian. Một số engine cần redo nhiều page và rollback transaction chưa hoàn tất. Điều này ảnh hưởng RTO (Recovery Time Objective).

Checkpoint frequency, log generation rate, transaction size, storage performance và replication/archiving đều có thể tác động thời gian phục hồi. Tối ưu commit latency không nên làm mất khả năng đạt RTO/RPO đã cam kết.

## 8. Các hệ quản trị phổ biến tổ chức log ra sao?

Các sản phẩm dùng thuật ngữ và kiến trúc khác nhau. Phần này giúp nhận diện khái niệm khi đọc tài liệu và metric; không thay thế tài liệu đúng phiên bản.

### 8.1. PostgreSQL: WAL

PostgreSQL ghi WAL records mô tả thay đổi cần thiết để phục hồi. WAL được ghi theo vị trí tăng dần; commit record đánh dấu transaction hoàn tất. Trong chế độ synchronous commit thông thường, PostgreSQL chờ WAL được flush đến vị trí cần thiết trước khi trả thành công.

Các khái niệm liên quan:

- WAL buffers: vùng đệm log trong shared memory.
- WAL writer và backend: các thành phần tham gia ghi WAL.
- WAL flush: ghi log tới storage theo yêu cầu durability.
- Checkpoint: ghi dirty buffers và đánh dấu điểm phục hồi.
- full_page_writes: cơ chế ghi full-page image sau checkpoint trong các điều kiện nhất định để bảo vệ khỏi torn page.
- WAL archiving: lưu các segment để hỗ trợ point-in-time recovery.
- Streaming replication: gửi WAL đến standby.

PostgreSQL không dùng undo log truyền thống giống InnoDB để rollback mọi UPDATE. MVCC lưu các tuple version; VACUUM dọn phiên bản không còn cần thiết. WAL phục vụ crash recovery và replication, còn MVCC tuple visibility là một phần khác của kiến trúc.

Một số tham số có ảnh hưởng đến durability và hiệu năng gồm synchronous_commit, fsync, wal_buffers, checkpoint_timeout, max_wal_size và archive_mode. Tên tham số không phải khuyến nghị thay đổi; hãy hiểu semantics và đo trên phiên bản đang vận hành.

### 8.2. MySQL InnoDB: redo, undo và binary log

InnoDB dùng redo log để phục hồi thay đổi ở tầng storage engine. Undo log hỗ trợ rollback và consistent read theo MVCC. MySQL binary log ghi các thay đổi ở tầng server để replication và point-in-time recovery trong các cấu hình phù hợp.

Khi binary logging được bật, commit có thể cần phối hợp giữa InnoDB và binary log qua cơ chế two-phase commit để hai nguồn log không lệch trạng thái khi crash. Vì vậy, commit latency có thể chịu ảnh hưởng từ cả redo log flush lẫn binary log synchronization.

Một số cấu hình thường được nhắc đến:

- innodb_flush_log_at_trx_commit: điều khiển thời điểm flush redo log buffer theo transaction.
- sync_binlog: điều khiển tần suất đồng bộ binary log xuống storage.
- innodb_log_buffer_size: kích thước log buffer của InnoDB.
- innodb_redo_log_capacity: dung lượng redo log được cấu hình ở các phiên bản hỗ trợ.

Ở cấu hình innodb_flush_log_at_trx_commit=1, InnoDB thực hiện flush redo log theo mỗi commit theo semantics của engine. Giá trị 2 thường ghi log qua hệ điều hành mỗi commit và flush định kỳ; giá trị 0 ghi và flush định kỳ. Hai cấu hình sau có thể làm mất các transaction gần nhất khi OS hoặc máy chủ gặp sự cố, tùy loại lỗi và thời điểm flush. Cần đối chiếu tài liệu phiên bản và yêu cầu durability trước khi thay đổi.

### 8.3. SQL Server: transaction log và LSN

SQL Server dùng transaction log để ghi các thay đổi và hỗ trợ redo/undo trong recovery. Log records được định vị bằng LSN. Khi transaction commit với delayed durability tắt, engine thường phải harden log record cần thiết trước khi xác nhận commit.

Các khái niệm cần nhận diện:

- Log buffer và log flush.
- LSN và log block.
- Virtual Log Files (VLFs) trong cấu trúc transaction log.
- Checkpoint và recovery.
- Log backup trong recovery model phù hợp.
- Log reuse wait và log truncation.
- Delayed durability.

Nếu transaction log không thể truncate hoặc reuse do log backup chưa chạy, replication, availability group, transaction dài hoặc nguyên nhân khác, file log có thể tăng. Tăng dung lượng log không tự giải quyết nguyên nhân giữ log.

Delayed durability có thể trả commit trước khi log được harden, giảm latency nhưng có rủi ro mất transaction mới nhất khi crash. Cần phân biệt với group commit và không bật chỉ để đạt một con số benchmark.

### 8.4. Oracle: redo log và LGWR

Oracle ghi redo entries vào redo log buffer trong SGA. Background process LGWR ghi redo xuống online redo log files. Khi COMMIT, session thường chờ redo tương ứng được ghi bền vững; wait event thường được gọi là log file sync, còn LGWR có thể chịu wait liên quan đến log file parallel write.

Oracle còn sử dụng undo data để rollback và cung cấp read consistency. Checkpoint phối hợp việc ghi dirty buffers và tiến trình recovery. Online redo log groups được luân phiên; archive logging lưu các redo log đã đầy để hỗ trợ recovery và standby.

Khi điều tra, cần phân biệt thời gian session chờ commit với thời gian LGWR thực hiện I/O. Nếu log file sync cao nhưng log file parallel write thấp, nguyên nhân có thể liên quan đến lịch gọi commit, CPU hoặc phối hợp foreground/background, không nhất thiết chỉ là storage chậm.

## 9. Transaction log khác binary log, replication log và audit log

Các loại log có thể cùng tồn tại nhưng phục vụ mục tiêu khác nhau.

| Loại log | Mục đích chính | Có thay thế WAL/redo không? |
|---|---|---|
| WAL/redo/transaction log | Crash recovery và durability của storage engine | Là log phục hồi chính của engine |
| Undo log | Rollback và/hoặc consistent read tùy engine | Không thay thế redo |
| Binary log | Ghi thay đổi ở tầng server, replication và PITR trong MySQL | Không thay thế InnoDB redo |
| Logical replication/change stream | Truyền thay đổi logic đến subscriber hoặc hệ thống khác | Không tự thay thế local crash recovery |
| Audit log | Lưu dấu vết hoạt động để kiểm toán | Không thay thế transaction log |
| Application log | Ghi sự kiện và lỗi của ứng dụng | Không bảo đảm database transaction durability |

Khi log replication hoặc audit được bật, ghi thêm log có thể làm tăng CPU, I/O và dung lượng. Nhưng không nên tắt một loại log cần thiết cho recovery, replication hoặc compliance chỉ để giảm commit latency.

## 10. Đọc các chỉ số hiệu năng của log

Tên metric và cách tính khác nhau giữa DBMS. Hãy chọn metric tương ứng trong hệ thống đang dùng và ghi rõ đơn vị, khoảng thời gian, reset point.

### 10.1. Log bytes generated

Lượng log tạo ra trong một giây hoặc trong một transaction cho biết write workload đang sinh bao nhiêu dữ liệu log. So sánh log bytes với rows inserted/updated/deleted để nhận diện thay đổi làm write amplification tăng.

Một UPDATE một dòng có thể tạo nhiều log bytes nếu nó cập nhật nhiều index, page hoặc cấu trúc phụ. Log bytes cao không nhất thiết là lỗi; cần so với workload và mức thay đổi logic.

### 10.2. Log flush latency

Log flush latency đo thời gian DBMS chờ ghi log bền vững hoặc thời gian I/O flush tương ứng. Đây là chỉ số quan trọng với transaction nhỏ có commit đồng bộ.

Nên xem:

- Mean và p95/p99 latency.
- Số lần flush trên giây.
- Bytes mỗi flush.
- Số transaction được phục vụ bởi mỗi flush nếu có metric.
- Storage latency và queue depth.
- Thời gian chờ ở foreground session.

Mean thấp có thể che giấu một số flush rất chậm. Ứng dụng nhạy với p99 có thể vẫn thấy commit chậm dù mean tốt.

### 10.3. Log write throughput và IOPS

Throughput cho biết bytes được ghi mỗi giây; IOPS cho biết số thao tác I/O. Một workload có nhiều flush nhỏ có thể bị giới hạn bởi latency/IOPS dù tổng bytes không cao. Workload log volume lớn có thể bị giới hạn bởi bandwidth.

Hãy đối chiếu với giới hạn storage, queue depth, write latency và các workload khác cùng dùng thiết bị. Một volume có throughput cao nhưng flush latency cao vẫn có thể làm commit chậm.

### 10.4. Log buffer pressure

Nếu log buffer quá nhỏ hoặc log generation tăng đột biến, DBMS có thể phải chờ buffer được giải phóng hoặc ghi thường xuyên hơn. Dấu hiệu có thể gồm log buffer waits, frequent flushes hoặc các wait event tương ứng của DBMS.

Tăng buffer size chỉ giúp khi buffer pressure là nguyên nhân. Nếu nút thắt là storage flush latency, buffer lớn hơn không làm commit bền vững nhanh hơn.

### 10.5. Checkpoint và dirty page metrics

Theo dõi checkpoint duration, dirty pages, data page write rate, checkpoint write latency và log retention. Checkpoint có thể tạo tải I/O nền cạnh tranh với log flush.

Nếu commit latency tăng theo chu kỳ, đối chiếu checkpoint activity và storage queue. Nếu log volume tăng liên tục, kiểm tra replica/archive hoặc transaction dài có đang giữ log hay không.

### 10.6. Wait events

Wait event cho biết session đang chờ tài nguyên hoặc một sự kiện. Một số tên phổ biến:

| DBMS | Ví dụ wait/metric liên quan | Hướng điều tra |
|---|---|---|
| PostgreSQL | WALWrite, WALSync hoặc wait event WAL tương ứng phiên bản | WAL write/flush, storage, contention |
| MySQL InnoDB | Log waits, redo log write/flush metrics | Redo buffer, redo flush, storage |
| SQL Server | WRITELOG | Transaction log flush, log volume, storage latency |
| Oracle | log file sync, log file parallel write | Foreground commit wait và LGWR I/O |

Tên wait và cách phân loại thay đổi theo phiên bản. Một wait cao cho biết thời gian bị chặn, nhưng không tự chứng minh nguyên nhân gốc. Cần ghép với I/O metrics, transaction pattern và tải đồng thời.

## 11. Những nguyên nhân phổ biến làm commit chậm

### 11.1. Storage flush latency cao

Commit đồng bộ cần chờ log được flush. Nếu storage có latency cao hoặc biến động, p95/p99 commit latency sẽ tăng ngay cả khi transaction chỉ cập nhật một dòng.

Kiểm tra latency ghi bền vững, queue depth, IOPS, bandwidth, cache policy và các workload khác cùng sử dụng storage. Xác nhận thiết bị và tầng ảo hóa thực sự bảo đảm flush semantics.

### 11.2. Quá nhiều transaction nhỏ

Nếu ứng dụng mở transaction, ghi một dòng rồi commit cho từng thao tác, số commit/giây có thể rất cao. Mỗi transaction cần coordination và có thể tham gia một lần flush.

Group commit giúp chia sẻ flush, nhưng không loại bỏ toàn bộ overhead. Nếu nghiệp vụ cho phép, batch một số thao tác liên quan trong transaction vừa phải có thể giảm commit frequency. Cần cân bằng với lock duration, rollback cost và latency người dùng.

### 11.3. Transaction quá lớn hoặc kéo dài

Transaction lớn tạo nhiều log, giữ lock lâu và có thể giữ phiên bản dữ liệu hoặc log cần thiết lâu hơn. Khi rollback, engine phải xử lý nhiều thay đổi. Một transaction dài còn có thể ngăn log truncation/reuse trong một số DBMS, khiến log file tăng và recovery phải xử lý phần rollback lớn hơn.

Chia transaction theo lô có thể giảm thời gian giữ khóa và kích thước rollback, nhưng thay đổi semantics nguyên tử. Chỉ chia khi nghiệp vụ cho phép trạng thái trung gian và có cơ chế resume/idempotency.

### 11.4. Log volume tăng do index và cập nhật

Mỗi index cần được duy trì khi các cột liên quan thay đổi. Thêm nhiều index, index rộng hoặc cập nhật cột khóa thường xuyên có thể làm log bytes và I/O tăng.

Kiểm tra số index, độ rộng index, page split, cập nhật generated columns và các cấu trúc phụ. Loại bỏ index dư thừa chỉ sau khi đã xác minh workload và constraint phụ thuộc.

### 11.5. Checkpoint hoặc data writes cạnh tranh

Checkpoint, page cleaner, backup, scan lớn hoặc batch job có thể cạnh tranh storage với log flush. Đo đồng thời log latency và data I/O để phân biệt.

### 11.6. Replication hoặc synchronous standby

Nếu commit chờ replica xác nhận, độ trễ mạng, tải replica hoặc flush ở standby có thể làm tăng commit latency. Cần phân biệt local log flush wait với remote acknowledgement wait. Replica lag hoặc network jitter có thể tạo tail latency lớn.

### 11.7. Autogrowth và log file management

Log file tăng dung lượng trong lúc tải cao có thể tạo pause hoặc I/O spike tùy DBMS và storage. Pre-size hợp lý, theo dõi free space và đặt cảnh báo giúp tránh tăng file bất ngờ.

Không shrink log thường xuyên rồi để nó autogrow lại. Việc shrink/grow lặp lại tạo overhead và có thể làm cấu trúc log phân mảnh hoặc vận hành khó dự đoán.

## 12. Cải thiện write path mà vẫn giữ durability

### 12.1. Đo trước khi thay đổi

Thu baseline về commit latency, log bytes, flush count, throughput, wait events, storage latency, checkpoint và replication. Ghi cả workload đọc/ghi vì tối ưu write path có thể ảnh hưởng cache và I/O của truy vấn đọc.

### 12.2. Rút ngắn transaction

Giữ transaction chỉ bao gồm các thao tác cần nguyên tử. Tránh thực hiện gọi HTTP, chờ người dùng hoặc tính toán lâu trong khi transaction đang mở.

Transaction ngắn thường giảm thời gian giữ lock và giảm rủi ro transaction dài. Tuy nhiên, nếu tách transaction làm thay đổi tính nguyên tử nghiệp vụ, cần thiết kế trạng thái, retry và idempotency trước.

### 12.3. Batch ở mức hợp lý

Gộp các thao tác ghi có quan hệ vào batch có thể giảm round-trip và số commit. Chọn batch size dựa trên throughput, lock duration, log volume và p95/p99.

Ví dụ, thay vì commit từng dòng độc lập, ứng dụng có thể insert theo nhóm trong một transaction nếu tất cả dòng thuộc cùng đơn vị nghiệp vụ. Không nên gom hàng trăm nghìn dòng vào một transaction chỉ để giảm commit count.

### 12.4. Giảm log generation không cần thiết

Xem xét:

- Loại bỏ index dư thừa sau khi xác minh.
- Tránh UPDATE một dòng nếu giá trị không thay đổi.
- Chỉ cập nhật cột thực sự cần thiết.
- Dùng bulk load hoặc cơ chế nạp dữ liệu chuyên dụng khi phù hợp.
- Tránh ghi đi ghi lại cùng một trạng thái.
- Giảm payload và cấu trúc phụ không cần thiết.

Một số thao tác bulk hoặc minimal logging có điều kiện và có thể làm thay đổi khả năng recovery/replication. Phải kiểm tra semantics và tài liệu DBMS trước khi sử dụng.

### 12.5. Bảo đảm storage phù hợp với log

Transaction log thường nhạy với latency flush hơn là chỉ throughput tuần tự. Hãy đo storage thực tế, bảo đảm cache/flush policy đúng, đủ IOPS và không bị chia sẻ quá mức với workload khác.

Tách log và data sang các volume khác nhau có thể hữu ích nếu chúng đang tranh chấp I/O, nhưng không phải lúc nào cũng tăng tốc nếu cả hai vẫn dùng chung backend storage hoặc bottleneck khác. Cần benchmark trên cấu hình thực tế.

### 12.6. Điều chỉnh cấu hình durability có hiểu biết

Các tham số như synchronous_commit, innodb_flush_log_at_trx_commit, sync_binlog hoặc delayed durability có thể thay đổi thời điểm flush và mức bảo đảm. Chúng không phải nút tối ưu hiệu năng chung.

Trước khi thay đổi, xác định rõ:
- Có thể mất tối đa những transaction nào khi crash?
- Có yêu cầu zero data loss hoặc RPO cụ thể không?
- Replica có nhận log bền vững không?
- Backup và point-in-time recovery còn đáp ứng không?
- Ai phê duyệt thay đổi durability?
- Có phép thử crash/recovery và đo lại phù hợp không?

Không giảm durability nếu yêu cầu nghiệp vụ và vận hành không cho phép.

## 13. Ví dụ: phân tích commit chậm trong hệ thống đặt hàng

Giả sử API tạo đơn hàng thực hiện:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status, total, created_at)
VALUES (900001, 42, 'PENDING', 250.00, CURRENT_TIMESTAMP);

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (900001, 101, 2, 75.00),
    (900001, 205, 1, 100.00);

UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 101;

COMMIT;
~~~

Giả sử SELECT và UPDATE hoàn tất nhanh, nhưng thời gian từ COMMIT đến phản hồi chiếm phần lớn p95. Không nên lập tức tăng log buffer. Hãy phân tích theo trình tự:

1. Đo thời gian transaction từ lúc BEGIN đến COMMIT và tách riêng thời gian commit wait.
2. Thu log bytes và số flush trên mỗi transaction.
3. Kiểm tra wait event liên quan đến log flush.
4. Đo storage write latency, IOPS, queue depth và throughput.
5. Xem group commit có đang gom nhiều transaction hay không.
6. Kiểm tra checkpoint, backup, log archive hoặc replication có trùng thời điểm không.
7. Xác định index và trigger có làm tăng số log record không.
8. Chạy benchmark với cùng transaction ở concurrency khác nhau.
9. Nếu storage latency là nguyên nhân, thử cấu hình storage phù hợp trong môi trường kiểm thử.
10. Nếu commit count quá cao, thử batch nghiệp vụ hợp lý và đo lại lock duration cùng tail latency.

Nếu chỉ số cho thấy local log flush nhanh nhưng session vẫn chờ remote synchronous replica, nút thắt nằm ở replication acknowledgement. Nếu log flush chậm đúng lúc checkpoint, cần điều tra tranh chấp I/O. Nếu log bytes/transaction tăng sau khi thêm index, cần đánh giá write amplification.

Không thay đổi durability trước khi đã xác định yêu cầu RPO và cách ứng dụng xử lý transaction có thể mất.

## 14. Quy trình benchmark và kiểm chứng

### Bước 1: Xác định transaction quan trọng

Chọn query/transaction fingerprint có commit latency hoặc tổng thời gian cao, tần suất lớn hoặc ảnh hưởng trực tiếp đến nghiệp vụ. Ghi kích thước transaction và số lần commit.

### Bước 2: Thu baseline

Đo trong cùng khoảng thời gian:
- Transactions/s và commits/s.
- p50/p95/p99 transaction duration và commit latency.
- Log bytes/s và bytes/transaction.
- Log flushes/s, bytes/flush và flush latency.
- CPU, memory, storage latency, IOPS, bandwidth và queue depth.
- Wait events, lock wait, deadlock và retry.
- Checkpoint, log archive và replication lag.

### Bước 3: Xác định giả thuyết

Ví dụ:
- Flush latency cao do storage.
- Flush count cao do transaction quá nhỏ.
- Log bytes cao do index hoặc update không cần thiết.
- Commit chờ synchronous replica.
- Checkpoint tạo I/O spike.
- Log buffer pressure do burst ghi.

Mỗi giả thuyết phải gắn với metric và khoảng thời gian quan sát được.

### Bước 4: Thay đổi một yếu tố

Thử batch size, transaction duration, index set, storage class hoặc tham số phù hợp trong môi trường được kiểm soát. Không thay nhiều yếu tố cùng lúc nếu cần biết nguyên nhân cải thiện.

### Bước 5: Giữ cùng mức durability

Benchmark trước/sau phải dùng cùng semantics commit và replication nếu đang đánh giá thay đổi ứng dụng hoặc storage. Nếu cố ý thử durability khác, phải tách kết quả thành một kịch bản riêng và ghi rõ rủi ro.

### Bước 6: Chạy tải đại diện

Dùng tỷ lệ đọc/ghi, transaction mix, dữ liệu và concurrency gần production. Chạy đủ lâu để quan sát group commit, checkpoint và background tasks. Đo p95/p99, không chỉ mean.

### Bước 7: Kiểm tra tính đúng đắn và phục hồi

Xác nhận transaction vẫn atomic, constraint không bị vi phạm, replication/backup vẫn hoạt động và recovery đáp ứng mục tiêu. Với thay đổi durability, cần kiểm tra rõ tình huống crash theo quy trình thử nghiệm an toàn.

### Bước 8: Theo dõi sau triển khai

Theo dõi commit latency, log growth, disk free space, checkpoint, replication lag, errors và recovery health. Lưu baseline và kế hoạch rollback.

## 15. Những ngộ nhận thường gặp

**COMMIT có nghĩa mọi data page đã ghi xuống file bảng.** Thông thường commit bền vững cần log flush; data page có thể được ghi sau.

**WAL, redo log và binary log là cùng một thứ.** WAL là nguyên tắc; redo/transaction log phục vụ phục hồi của engine; binary log hoặc logical log có thể phục vụ replication và PITR.

**Tăng log buffer luôn làm commit nhanh hơn.** Nếu bottleneck là storage flush latency, buffer lớn hơn không loại bỏ lần flush bắt buộc.

**Group commit làm mất durability.** Group commit có thể vẫn giữ durability đồng bộ; nhiều transaction chia sẻ một lần flush. Nó khác với delayed commit.

**Checkpoint là commit tất cả transaction.** Checkpoint phục vụ quản lý dirty pages và recovery; transaction state được xác định bởi log và commit record.

**Tăng kích thước log file sẽ tăng tốc commit.** Dung lượng lớn có thể giảm autogrowth hoặc giữ log lâu hơn, nhưng không tự giảm latency của mỗi flush.

**Tắt fsync là cách tối ưu an toàn.** Tắt bảo đảm flush có thể làm mất hoặc hỏng dữ liệu khi sự cố. Không dùng như một tối ưu production mặc định.

**Một wait event log chứng minh storage hỏng.** Wait cho biết session đang chờ; cần đối chiếu storage, group commit, CPU, checkpoint và replication.

**Số commits/s càng cao thì ứng dụng càng nhanh.** Throughput có thể tăng trong khi p99 latency xấu đi hoặc lock contention tăng. Phải xem cả hai.

## 16. Checklist điều tra WAL/redo và commit

- [ ] Đã xác định transaction/query fingerprint cần cải thiện chưa?
- [ ] Đã phân biệt log phục hồi, undo, binary/logical log và audit log chưa?
- [ ] Đã xác định chế độ commit durability đang dùng chưa?
- [ ] Đã đo commit latency p50/p95/p99 chưa?
- [ ] Đã đo log bytes/s, bytes/transaction và flushes/s chưa?
- [ ] Đã đo log flush latency và storage queue depth chưa?
- [ ] Đã kiểm tra log buffer pressure và wait events chưa?
- [ ] Đã kiểm tra group commit và số transaction mỗi flush nếu có metric chưa?
- [ ] Đã đối chiếu checkpoint với data page writes và commit latency chưa?
- [ ] Đã kiểm tra log growth, archive, backup và replication lag chưa?
- [ ] Đã kiểm tra index, trigger và write amplification chưa?
- [ ] Đã đo transaction size, duration, lock wait và batch size chưa?
- [ ] Đã benchmark cùng workload và cùng mức durability trước/sau chưa?
- [ ] Đã xác định rủi ro mất dữ liệu và RPO trước khi thay đổi durability chưa?
- [ ] Đã kiểm tra recovery và phương án rollback chưa?

## Kết luận

Transaction log, WAL và redo là nền tảng để DBMS bảo đảm transaction có thể được phục hồi sau sự cố. Nguyên tắc write-ahead yêu cầu log cần thiết phải được ghi trước data page; commit đồng bộ thường chờ log được flush đến commit record rồi mới xác nhận thành công. Dirty page có thể được ghi sau bởi background writer hoặc checkpoint. Group commit giúp nhiều transaction chia sẻ một lần flush, còn redo/undo và checkpoint phối hợp để phục hồi database nhất quán.

Hiệu năng commit phụ thuộc flush latency, log volume, group commit, transaction size, storage queue, checkpoint, replication và cấu hình durability. Hãy đo cả commit latency lẫn throughput, đối chiếu wait events với I/O thực tế, giữ cùng mức durability khi benchmark và thay đổi từng yếu tố có bằng chứng. Tối ưu write path có ý nghĩa khi giảm chi phí mà vẫn đáp ứng atomicity, durability, replication, backup và mục tiêu phục hồi của hệ thống.

