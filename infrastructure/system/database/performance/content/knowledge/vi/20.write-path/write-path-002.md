# Độ bền dữ liệu, đồng bộ xuống đĩa và chi phí xác nhận giao dịch

## 1. Vì sao COMMIT có thể chậm dù câu lệnh đã chạy xong?

Một giao dịch có thể thực hiện các lệnh `INSERT`, `UPDATE` hoặc `DELETE` rất nhanh trong bộ nhớ, nhưng thời điểm `COMMIT` vẫn mất nhiều mili giây hoặc lâu hơn. Nguyên nhân thường nằm ở đường ghi (write path): hệ quản trị phải bảo đảm thông tin cần thiết để khôi phục giao dịch được ghi an toàn vào transaction log, có thể phải chờ thiết bị lưu trữ xác nhận flush, chờ nhóm giao dịch khác cùng flush, hoặc chờ replica theo cấu hình đồng bộ.

Độ bền (durability) là chữ D trong ACID. Khi hệ quản trị xác nhận một giao dịch đã commit theo mức bảo đảm đã cấu hình, giao dịch đó phải được khôi phục sau sự cố thuộc phạm vi bảo vệ của hệ thống. Điều này không có nghĩa mọi trang dữ liệu đã được ghi xuống file dữ liệu ngay tại thời điểm `COMMIT`. Nhiều hệ quản trị dùng write-ahead logging (WAL) hoặc cơ chế redo log: ghi bền vững thông tin log trước, còn các trang dữ liệu có thể được ghi xuống sau.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần hiểu ranh giới giữa ghi log, flush log, ghi trang dữ liệu, checkpoint và xác nhận giao dịch. Nếu chỉ tắt đồng bộ để giảm thời gian commit, ứng dụng có thể mất những giao dịch vừa được xác nhận khi máy chủ hoặc hệ điều hành gặp sự cố. Nếu cấu hình đồng bộ quá chặt hoặc lưu trữ không đáp ứng, commit latency và throughput có thể suy giảm dưới tải.

Bài học này trình bày đường đi của một giao dịch ghi, WAL/redo log, dirty page, flush/fsync, group commit, checkpoint, đồng bộ replica và các yếu tố quyết định commit latency. Các chi tiết và tên cấu hình khác nhau giữa PostgreSQL, SQL Server, MySQL/InnoDB và những hệ quản trị khác; hãy đối chiếu tài liệu đúng phiên bản trước khi thay đổi cấu hình production.

## 2. Độ bền trong ACID và ý nghĩa của xác nhận COMMIT

ACID gồm bốn thuộc tính:

- **Atomicity:** các thay đổi trong giao dịch được áp dụng như một đơn vị; khi rollback, hệ thống không để lại một phần thay đổi nghiệp vụ.
- **Consistency:** giao dịch đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo ràng buộc và quy tắc ứng dụng.
- **Isolation:** các giao dịch đồng thời quan sát và ảnh hưởng lẫn nhau theo mức cô lập đã chọn.
- **Durability:** sau khi commit được xác nhận theo cấu hình, thay đổi đã commit có thể được phục hồi sau sự cố thuộc phạm vi bảo vệ.

Ứng dụng thường hiểu phản hồi thành công từ `COMMIT` là tín hiệu có thể thông báo cho người dùng, phát sự kiện hoặc thực hiện bước tiếp theo. Vì vậy, mức bảo đảm của phản hồi commit là một phần của hợp đồng giữa database và ứng dụng.

Nếu hệ quản trị xác nhận commit trước khi log được lưu bền vững, sự cố ngay sau đó có thể làm mất giao dịch mà ứng dụng đã nhận xác nhận. Nếu hệ thống chỉ chờ log bền vững trên máy chính nhưng chưa chờ replica, giao dịch có thể sống sót sau lỗi máy chính nhưng chưa chắc có trên replica vừa được promote. Hai ranh giới này cần được phân biệt rõ khi thiết kế RPO (Recovery Point Objective) và chiến lược failover.

### 2.1. Commit thành công không đồng nghĩa data page đã xuống đĩa

Trong hệ thống dùng WAL, khi một giao dịch cập nhật hàng, trang dữ liệu thường được sửa trong buffer pool trước. Trang đã sửa nhưng chưa ghi xuống file dữ liệu được gọi là dirty page. Hệ quản trị tạo log record mô tả thay đổi và bảo đảm log tương ứng được flush bền vững trước khi trang dữ liệu có thể được ghi ra storage.

Do đó, khi commit trả về thành công:

1. Log record cần thiết và commit record đã đạt ranh giới bền vững theo cấu hình.
2. Trang dữ liệu tương ứng có thể vẫn chỉ nằm trong buffer pool.
3. Checkpoint hoặc background writer sẽ ghi dirty page xuống file dữ liệu sau đó.
4. Nếu sự cố xảy ra trước khi dirty page được ghi, recovery dùng log để redo thay đổi đã commit và xử lý giao dịch chưa commit theo cơ chế của engine.

Đây là lý do WAL có thể vừa bảo đảm độ bền vừa tránh phải ghi đồng bộ mọi trang dữ liệu tại từng lần commit. Log thường tuần tự hơn và nhỏ hơn tổng các trang dữ liệu bị tác động, giúp đường commit hiệu quả hơn.

### 2.2. Phạm vi của từ “bền vững”

Độ bền luôn gắn với mô hình sự cố và tầng lưu trữ được tin cậy. Cần hỏi hệ thống có bảo vệ trước:

- Tiến trình database bị crash nhưng máy vẫn chạy.
- Hệ điều hành hoặc kernel bị crash.
- Mất điện đột ngột.
- Thiết bị lưu trữ hoặc controller bị lỗi.
- Mất toàn bộ node hoặc availability zone.
- Mất cả primary và replica trong cùng một sự cố.

Một flush thành công tới page cache của hệ điều hành không nhất thiết tương đương dữ liệu đã nằm trên media không mất điện. Database dựa vào hợp đồng của hệ điều hành, driver, controller và thiết bị về lệnh flush, write barrier, FUA hoặc cache có bảo vệ nguồn. Nếu thiết bị báo hoàn tất khi dữ liệu vẫn nằm trong cache volatile không được bảo vệ, bảo đảm durability có thể yếu hơn giả định của database.

Vì vậy, tối ưu commit không chỉ là chỉnh một tham số trong database. Cần xác nhận storage stack thực sự tuân thủ semantics flush và có cơ chế bảo vệ cache phù hợp.

## 3. Đường ghi tổng quát của một giao dịch

Một đường ghi điển hình trong hệ quản trị dùng WAL/redo log có thể hình dung như sau:

```text
Ứng dụng gửi INSERT / UPDATE / DELETE
                 |
                 v
       Database xử lý giao dịch
                 |
        +--------+---------+
        |                  |
        v                  v
   Sửa buffer page     Tạo log record
   (dirty page)        trong log buffer
        |                  |
        |                  v
        |           Ghi log ra OS/storage
        |                  |
        |                  v
        |            Flush / durable
        |                  |
        |                  v
        |          Commit được xác nhận
        |                  |
        v                  v
 Background writer / checkpoint ghi data page
                 |
                 v
           File dữ liệu bền vững
```

Đây là sơ đồ khái niệm. Thứ tự nội bộ, log buffer, commit record, flush queue và cơ chế ghi trang khác nhau giữa các engine. Ý tưởng chung của WAL là log mô tả thay đổi phải được lưu bền vững trước khi trang dữ liệu chứa thay đổi đó được ghi xuống vị trí lưu trữ chính.

### 3.1. Các bước chính

1. **Nhận lệnh ghi:** database phân tích SQL, kiểm tra quyền, kiểu dữ liệu, constraint và xác định các trang cần đọc/sửa.
2. **Sửa trang trong bộ nhớ:** dữ liệu được thay đổi trong buffer pool; trang trở thành dirty. Các khóa hoặc latch cần thiết được giữ theo cơ chế concurrency control.
3. **Sinh log record:** engine tạo thông tin đủ để redo, undo hoặc phục hồi thay đổi theo thiết kế của nó. Log record có thể mô tả thay đổi hàng, index, metadata và ranh giới giao dịch.
4. **Ghi commit record:** khi ứng dụng yêu cầu commit, engine ghi thông tin xác nhận giao dịch vào log stream.
5. **Flush log:** log được đẩy qua các tầng cache đến mức bền vững mà cấu hình yêu cầu. Commit có thể phải chờ vị trí log của giao dịch được flush.
6. **Trả kết quả:** sau khi đạt điều kiện commit, database trả thành công cho ứng dụng.
7. **Ghi data page sau:** background writer hoặc checkpoint ghi dirty page xuống file dữ liệu theo lịch và áp lực buffer.

Một số hệ quản trị dùng undo log, redo log hoặc kết hợp nhiều loại log. Không phải mọi engine đều triển khai đúng sơ đồ byte-level trên, nhưng cần phân biệt rõ log durability với thời điểm data page được ghi.

### 3.2. Log sequence number và ranh giới flush

Trong nhiều hệ quản trị, log record có vị trí tuần tự như log sequence number (LSN) hoặc vị trí tương đương. Một giao dịch có thể được xác nhận khi log đã được flush ít nhất tới vị trí cần thiết của commit record.

Nếu log record của giao dịch T kết thúc ở vị trí LSN 10500 và commit record nằm ở LSN 10620, engine phải bảo đảm log bền vững tới vị trí cần thiết bao gồm commit record trước khi trả xác nhận theo chế độ synchronous local durability. Việc flush có thể đồng thời bao phủ log của nhiều giao dịch trước đó.

LSN là khái niệm cụ thể trong một số engine; tên và cách quản lý vị trí log có thể khác. Điều quan trọng là commit phụ thuộc vào ranh giới log đã được lưu bền vững, không nhất thiết vào việc tất cả data page đã được ghi.

## 4. WAL, redo log và khả năng phục hồi

### 4.1. Write-ahead logging

WAL là nguyên tắc ghi log trước khi ghi trang dữ liệu chứa thay đổi. Nếu data page được ghi trước log cần thiết, crash có thể khiến file dữ liệu chứa trạng thái mới nhưng log không đủ thông tin để phục hồi nhất quán.

Nguyên tắc thường có hai phần:

- Trước khi ghi một dirty page xuống storage, log cần thiết để phục hồi page đó phải được flush tới vị trí yêu cầu.
- Trước khi xác nhận commit trong chế độ synchronous durability, commit record và log record cần thiết phải đạt mức bền vững mà cấu hình quy định.

WAL cho phép database trì hoãn ghi data page, gom nhiều thay đổi trên cùng trang và ghi tuần tự log. Đổi lại, hệ thống phải quản lý log, checkpoint và recovery đúng cách.

### 4.2. Redo và undo khi phục hồi

Sau crash, engine kiểm tra log và trạng thái dữ liệu để đưa database về trạng thái nhất quán. Khái niệm phổ biến:

- **Redo:** áp dụng lại những thay đổi cần thiết đã được ghi log nhưng data page chưa được ghi đầy đủ trước crash.
- **Undo:** loại bỏ hoặc đảo ngược những thay đổi của giao dịch chưa commit nếu engine dùng cơ chế undo trong recovery.
- **Analysis/recovery scan:** xác định giao dịch, trang và log record cần xử lý; thuật toán cụ thể tùy engine.

Một giao dịch đã commit và log commit đã bền vững có thể được redo sau crash, kể cả khi data page chưa từng được ghi trước sự cố. Giao dịch chưa commit không được hiển thị như giao dịch hoàn tất sau recovery; engine sẽ phục hồi trạng thái phù hợp.

### 4.3. Log không thay thế backup

Transaction log/WAL giúp phục hồi crash và hỗ trợ point-in-time recovery khi kết hợp backup và chuỗi log cần thiết. Nó không phải bản backup độc lập cho mọi tình huống. Nếu file dữ liệu, log và bản sao lưu cùng mất hoặc bị phá hủy, khả năng phục hồi vẫn có thể không tồn tại.

Hãy duy trì backup, kiểm tra khả năng restore, bảo vệ log archive và thử quy trình khôi phục. Durability của commit trên primary không thay thế backup, replication hoặc disaster recovery.

## 5. Buffer pool, dirty page và background writer

### 5.1. Buffer pool

Buffer pool là vùng bộ nhớ database dùng để cache các trang dữ liệu và index. Khi giao dịch sửa một trang, thay đổi thường được áp dụng trong buffer pool trước khi ghi xuống file dữ liệu. Trang đó trở thành dirty page.

Việc giữ trang trong bộ nhớ giúp nhiều giao dịch đọc/ghi cùng trang mà không phải truy cập storage mỗi lần. Nó cũng cho phép database gom nhiều thay đổi trên cùng trang trước khi ghi. Tuy nhiên, nếu dirty page tích tụ quá nhiều, checkpoint hoặc background writer phải ghi một lượng lớn dữ liệu, gây áp lực I/O và làm tăng độ trễ của workload.

### 5.2. Vì sao không ghi mọi data page ngay tại COMMIT?

Một giao dịch có thể thay đổi nhiều trang. Nếu phải ghi đồng bộ tất cả các trang đó trước khi trả commit, latency sẽ phụ thuộc vào số trang, vị trí lưu trữ, index và thứ tự ghi. WAL cho phép chỉ cần flush log để xác nhận commit; việc ghi các trang dữ liệu được thực hiện sau theo lịch tối ưu hơn.

Điều này không có nghĩa dirty page có thể giữ trong RAM vô hạn. Database phải ghi chúng trước khi buffer cần được tái sử dụng hoặc theo chính sách checkpoint, và phải tuân thủ WAL khi ghi.

### 5.3. Buffer pressure và writeback

Nếu workload ghi nhanh hơn khả năng background writer/checkpoint ghi trang, dirty page tăng và buffer pool có thể chịu áp lực. Khi đó database có thể buộc một tiến trình foreground ghi trang để giải phóng buffer, làm truy vấn vốn nhanh bị chậm đột ngột.

Các dấu hiệu cần theo dõi:

- Dirty page/buffer dirty ratio tăng kéo dài.
- Checkpoint write hoặc background write tăng mạnh.
- Foreground write xuất hiện trong truy vấn.
- Buffer eviction và physical write tăng.
- Storage write latency hoặc queue depth tăng.
- Transaction log/WAL tăng nhanh hoặc checkpoint thường xuyên hơn dự kiến.

Tăng buffer pool không tự động giải quyết được vấn đề nếu storage không ghi kịp hoặc checkpoint bị cấu hình không phù hợp. Cần đo tốc độ sinh dirty page, tốc độ writeback và năng lực I/O thực tế.

## 6. Flush, fsync và độ bền của storage

### 6.1. Phân biệt write và flush

Một lời gọi write thường chuyển dữ liệu từ tiến trình database sang kernel hoặc tầng cache tiếp theo. Điều đó chưa chắc chứng minh dữ liệu đã nằm trên thiết bị lưu trữ không mất điện. Flush/fsync yêu cầu hệ điều hành đẩy dữ liệu liên quan tới trạng thái bền vững theo hợp đồng của hệ thống.

Các thuật ngữ thường gặp:

- **Write:** gửi dữ liệu xuống tầng I/O tiếp theo; có thể chỉ tới page cache của OS.
- **Flush:** yêu cầu đẩy dữ liệu đang đệm xuống tầng thấp hơn; semantics tùy API và thiết bị.
- **fsync/fdatasync:** API yêu cầu đồng bộ nội dung file và, tùy API, metadata cần thiết theo semantics của hệ điều hành.
- **Write barrier/FUA:** cơ chế bảo đảm thứ tự ghi hoặc yêu cầu ghi không nằm lại trong cache volatile theo khả năng thiết bị.
- **Battery-backed/flash-backed write cache:** cache có bảo vệ nguồn, có thể xác nhận ghi an toàn trước khi dữ liệu được chuyển tới media cuối.

Tên API và bảo đảm thực tế phụ thuộc hệ điều hành, filesystem, driver, controller và thiết bị. Không được coi một lời gọi `write()` thành công là bằng chứng commit đã bền vững.

### 6.2. Vì sao fsync latency ảnh hưởng commit?

Trong chế độ synchronous durability, commit thường phải đợi log flush. Nếu mỗi lần flush mất 8 ms, một giao dịch đơn lẻ có thể phải chờ gần mức đó chỉ riêng cho bước đồng bộ, chưa kể lock wait, CPU và queueing. Nếu storage có latency dao động, p99 commit có thể tăng mạnh dù average vẫn thấp.

Flush latency phụ thuộc:

- Thiết bị lưu trữ, network storage và đường đi I/O.
- Số lượng yêu cầu đồng thời và độ sâu hàng đợi.
- Kích thước log cần ghi và cách batching.
- Cache của OS, controller và thiết bị.
- File system, mount option, virtualization layer và hypervisor.
- Write barrier, flush command và cơ chế bảo vệ cache.
- Tải I/O từ data file, checkpoint, backup hoặc workload khác.

Nếu log và data file dùng chung storage hoặc cùng một queue bão hòa, checkpoint có thể làm commit flush chậm dù log volume riêng không lớn. Tách log và data sang các thiết bị độc lập chỉ có ích khi thật sự giảm tranh chấp vật lý hoặc queue; nếu cùng một backend storage, việc tách đường dẫn file không nhất thiết cải thiện.

### 6.3. Xác minh storage stack

Trước khi tối ưu bằng cấu hình database, xác nhận nền tảng lưu trữ hỗ trợ flush đúng cách. Với thiết bị có write cache volatile, cần pin/flash-backed cache hoặc cấu hình tắt cache không an toàn theo hướng dẫn của nhà cung cấp. Kiểm tra firmware, controller battery/flash health, hypervisor và semantics của network block storage.

Không tắt fsync, write barrier hoặc cơ chế bảo vệ cache để cải thiện benchmark nếu chưa chấp nhận rõ nguy cơ mất giao dịch đã xác nhận. Một kết quả benchmark nhanh hơn có thể chỉ phản ánh dữ liệu còn nằm trong cache volatile.

## 7. Group commit: nhiều giao dịch dùng chung một lần flush

### 7.1. Nguyên lý

Nếu mỗi giao dịch phải gọi flush riêng, workload có nhiều giao dịch nhỏ có thể bị giới hạn bởi số lần flush và latency của storage. Group commit cho phép nhiều giao dịch cùng tham gia một đợt flush log. Khi log đã được flush tới vị trí bao phủ commit record của nhóm, database có thể xác nhận nhiều giao dịch cùng lúc.

Ví dụ, 50 giao dịch hoàn tất ghi log trong một khoảng ngắn. Thay vì thực hiện 50 lần đồng bộ riêng, engine có thể gom log và thực hiện một lần flush bao phủ cả 50 giao dịch. Nhờ đó, số lần flush trên mỗi giao dịch giảm và throughput tăng.

### 7.2. Sơ đồ thời gian

```text
Thời gian  ---------------------------------------------------->

Tx A:  ghi log ---- chờ nhóm -------------------- COMMIT trả về
Tx B:       ghi log ---- chờ nhóm --------------- COMMIT trả về
Tx C:            ghi log ---- chờ nhóm ---------- COMMIT trả về
Tx D:                 ghi log ---- chờ nhóm ----- COMMIT trả về
                              |
                              v
                      Một lần log flush
                 bao phủ commit record A-D
```

Các giao dịch không nhất thiết bắt đầu cùng lúc. Giao dịch đến trước có thể chờ thêm một khoảng ngắn để nhóm lớn hơn, nhưng sau flush chung có nhiều commit được xác nhận.

### 7.3. Trade-off giữa throughput và latency

Group commit thường cải thiện throughput vì chi phí flush được chia cho nhiều giao dịch. Tuy nhiên, giao dịch đến đầu nhóm có thể phải chờ thêm để nhóm hình thành. Một khoảng gom nhóm quá dài có thể tăng commit latency, đặc biệt p95/p99, dù số flush giảm.

Nhiều engine tự điều chỉnh group commit dựa trên tải và scheduler. Một số cung cấp tham số trì hoãn hoặc batching. Không nên đặt delay lớn chỉ để tăng kích thước nhóm; hãy đo transactions per flush, flush frequency, commit latency và throughput trong workload thực tế.

### 7.4. Group commit không làm giảm mức durability

Nếu flush chung được thực hiện đúng theo chế độ synchronous, mỗi giao dịch trong nhóm chỉ được xác nhận sau khi commit record của nó đã nằm trong phạm vi log bền vững. Group commit thay đổi cách gom các lần flush, không đồng nghĩa bỏ flush.

## 8. Checkpoint và ảnh hưởng đến commit latency

### 8.1. Checkpoint là gì?

Checkpoint là quá trình đưa các thay đổi trong bộ nhớ xuống file dữ liệu và ghi nhận một điểm phục hồi trong log. Sau checkpoint, recovery thường không cần phát lại toàn bộ log từ đầu mà có thể bắt đầu từ điểm phù hợp gần checkpoint, tùy engine.

Checkpoint không phải là điều kiện để từng giao dịch commit thành công trong hệ thống WAL. Commit có thể đã được xác nhận khi log bền vững, trong khi data page vẫn còn dirty. Checkpoint giúp kiểm soát lượng dirty page và thời gian recovery.

### 8.2. Checkpoint quá dày hoặc quá gắt

Nếu checkpoint diễn ra quá thường xuyên hoặc cố gắng ghi quá nhiều trang trong thời gian ngắn, nó có thể tạo write burst, làm storage queue tăng và cạnh tranh với log flush. Khi đó commit latency tăng dù log record của mỗi giao dịch nhỏ.

Nếu checkpoint quá thưa, dirty page và lượng WAL cần giữ có thể tăng, recovery có thể lâu hơn và storage có thể phải xử lý burst lớn khi checkpoint đến. Cần cân bằng giữa:

- Thời gian recovery mục tiêu.
- Khả năng ghi tuần tự và ngẫu nhiên của storage.
- Tốc độ sinh WAL/redo log.
- Lượng dirty page và buffer pressure.
- Tác động đến latency của workload đang chạy.

### 8.3. Theo dõi checkpoint

Quan sát thời gian checkpoint, số trang ghi, write rate, checkpoint frequency, WAL/redo volume, log reuse, buffer dirty và storage latency. Nếu commit chậm theo chu kỳ checkpoint, đối chiếu timestamp của flush log với write burst và queue depth để xác định tương quan.

Không tắt checkpoint để giảm latency. Làm vậy có thể tăng log cần phục hồi, tăng áp lực bộ nhớ và gây sự cố dung lượng. Hãy điều chỉnh tốc độ ghi, khoảng checkpoint và dung lượng log theo khuyến nghị của engine, rồi đo lại.

## 9. Đồng bộ replica và ý nghĩa của xác nhận giao dịch

### 9.1. Local durability và remote durability là hai ranh giới khác nhau

Một primary có thể xác nhận giao dịch sau khi log đã bền vững trên local storage. Nếu replication bất đồng bộ, log có thể chưa được gửi hoặc áp dụng ở replica tại thời điểm primary trả commit. Nếu primary mất hoàn toàn và replica được promote ngay, một số giao dịch vừa xác nhận có thể chưa có trên replica.

Replication đồng bộ bổ sung một điều kiện chờ remote. Tùy hệ thống, primary có thể chờ replica:

- Nhận log vào bộ đệm hoặc hệ điều hành.
- Ghi log bền vững xuống storage của replica.
- Phát lại log và làm thay đổi có thể nhìn thấy trên replica.

Các mức này có độ trễ và bảo đảm khác nhau. Chờ replica flush bền vững thường bảo vệ tốt hơn trước mất primary so với chỉ chờ nhận dữ liệu; chờ replay còn thêm thời gian apply.

### 9.2. Synchronous replication làm tăng commit latency

Khi commit phải đợi replica, latency phụ thuộc cả local log flush và thời gian truyền/flush/replay trên remote. Nếu replica ở xa, mạng có RTT cao hoặc replica đang bận apply log, commit p95/p99 có thể tăng.

Các yếu tố cần đo:

- Network RTT, packet loss và throughput giữa primary/replica.
- Replication send queue và write/flush/replay lag.
- Tốc độ apply log trên replica.
- Số replica được yêu cầu xác nhận và quorum policy.
- Thời gian chờ remote acknowledgement theo từng giao dịch.
- Hành vi khi replica mất kết nối hoặc vượt timeout.

### 9.3. Chọn mức đồng bộ theo RPO/RTO

RPO là lượng dữ liệu tối đa có thể chấp nhận mất khi xảy ra sự cố; RTO là thời gian mục tiêu để khôi phục dịch vụ. Replication đồng bộ có thể giảm RPO nhưng tăng latency và phụ thuộc availability của replica. Replication bất đồng bộ thường giảm ảnh hưởng lên commit nhưng có thể mất một đoạn log chưa truyền khi failover.

Không có một mức đồng bộ tốt cho mọi giao dịch. Hệ thống tài chính, sổ cái hoặc giao dịch không thể tái tạo thường cần durability chặt hơn; telemetry hoặc dữ liệu có thể nạp lại có thể chấp nhận cửa sổ mất dữ liệu nhỏ nếu nghiệp vụ cho phép. Quyết định phải được chủ sở hữu dữ liệu và kiến trúc hệ thống xác nhận.

### 9.4. PostgreSQL: synchronous_commit và standby

Trong PostgreSQL, `synchronous_commit` điều khiển mức chờ xác nhận WAL. Với cấu hình thông thường:

- `on` chờ local WAL flush; nếu có synchronous standby được cấu hình, còn có thể chờ xác nhận remote theo chính sách đồng bộ.
- `remote_write` chờ synchronous standby ghi WAL tới hệ điều hành của nó, nhưng chưa nhất thiết flush bền vững xuống storage.
- `remote_apply` chờ standby replay WAL để thay đổi có thể nhìn thấy ở standby.
- `local` chờ local flush nhưng không chờ synchronous standby.
- `off` cho phép trả commit trước khi local WAL được flush; hệ thống vẫn ghi WAL nền nhưng có một cửa sổ mất giao dịch gần đây khi crash.

Tên và semantics cụ thể cần kiểm tra theo phiên bản PostgreSQL và cấu hình `synchronous_standby_names`. `synchronous_commit=off` không đồng nghĩa database mất nhất quán sau mọi crash; nó nới lỏng durability của các giao dịch gần đây đã được xác nhận, có thể mất trong sự cố hệ điều hành hoặc máy chủ. Nó không nên được bật chỉ vì một benchmark cho thấy commit nhanh hơn.

## 10. Các cấu hình durability thường gặp theo hệ quản trị

### 10.1. PostgreSQL

PostgreSQL dùng WAL. Trong cấu hình durability thông thường, commit chờ WAL flush theo `synchronous_commit`. `fsync` và các tham số liên quan tới WAL/commit delay ảnh hưởng tới bảo đảm và cách gom ghi. Tắt `fsync` có thể làm tăng nguy cơ hỏng dữ liệu sau crash hoặc mất điện; không dùng như biện pháp tối ưu thông thường.

Một số điểm cần hiểu:

- `fsync=on` là thiết lập cần thiết cho độ bền theo mô hình hỗ trợ của storage stack.
- `synchronous_commit` điều khiển thời điểm xác nhận local/remote.
- `wal_sync_method` chọn phương thức đồng bộ WAL tùy nền tảng.
- `commit_delay` và `commit_siblings` có thể ảnh hưởng group commit trong một số workload; giá trị không phù hợp có thể làm tăng latency.
- `checkpoint_timeout`, `max_wal_size` và các tham số checkpoint ảnh hưởng write burst, WAL retention và recovery.

Không sao chép giá trị cấu hình giữa hai máy khác tải hoặc khác storage. Hãy đo WAL write/sync time, số transaction mỗi flush, checkpoint stats và commit latency trước/sau.

### 10.2. MySQL/InnoDB

InnoDB dùng redo log để phục hồi thay đổi. `innodb_flush_log_at_trx_commit` là tham số quan trọng điều khiển việc ghi và flush redo log quanh thời điểm commit. Ở cấu hình `1`, InnoDB ghi và flush log theo yêu cầu durability của mỗi commit, có thể kết hợp group commit để gom I/O. Giá trị `2` thường ghi log tới hệ điều hành tại commit và flush theo chu kỳ; giá trị `0` thường ghi và flush theo chu kỳ thay vì tại mỗi commit. Cả `0` và `2` đều có thể mất các giao dịch gần đây khi OS hoặc máy bị crash, tùy sự cố và tầng cache.

Nếu dùng binary log, `sync_binlog` cũng ảnh hưởng độ bền của binlog. Bảo đảm giữa InnoDB redo log và binary log cần được xem xét cùng nhau để tránh trạng thái phục hồi hoặc replication không như mong đợi. Các giá trị và semantics phải được xác minh theo phiên bản MySQL/MariaDB và cấu hình storage.

Không đặt `innodb_flush_log_at_trx_commit=0` hoặc `2` chỉ để giảm latency mà không đánh giá RPO. Nếu ứng dụng yêu cầu mọi commit đã xác nhận phải tồn tại sau crash, cần giữ chế độ đồng bộ phù hợp và tối ưu storage/group commit thay vì bỏ flush.

### 10.3. SQL Server

SQL Server sử dụng transaction log và log hardening để bảo đảm commit. Trong delayed durability, SQL Server có thể trả commit trước khi log record được flush; điều này giảm thời gian chờ nhưng có nguy cơ mất các giao dịch gần đây khi có sự cố. Delayed durability có thể được cấu hình theo database hoặc transaction tùy phiên bản và chế độ.

Wait type `WRITELOG` thường là tín hiệu session đang chờ log flush, nhưng cần xem cùng log flush latency, số byte ghi, số lần flush và tải storage. Nếu log file nằm trên storage chậm hoặc nhiều giao dịch cạnh tranh cùng log, commit latency có thể tăng.

Không bật delayed durability cho mọi giao dịch chỉ để loại bỏ `WRITELOG`. Hãy xác định giao dịch nào có thể chấp nhận mất dữ liệu gần đây, cách ứng dụng retry/idempotency và tác động đến HA/DR.

## 11. Các yếu tố quyết định commit latency

Commit latency là tổng hợp nhiều khoảng chờ, không chỉ là thời gian fsync. Các thành phần thường gặp:

| Thành phần | Mô tả | Dấu hiệu cần kiểm tra |
|---|---|---|
| Lock wait | Giao dịch phải chờ khóa trước khi có thể commit hoặc hoàn tất | Blocking session, lock duration, deadlock |
| Log generation | Tạo log record cho thay đổi dữ liệu và index | Log bytes/transaction, transaction size |
| Log buffer pressure | Log buffer hoặc pipeline ghi log không theo kịp | Log waits, buffer usage, producer/flush rate |
| Flush latency | Chờ log được lưu bền vững | fsync/write/sync latency, storage queue |
| Group commit queue | Chờ nhóm flush hoặc chờ vị trí log được bao phủ | Transactions per flush, commit delay |
| Remote acknowledgement | Chờ replica nhận, flush hoặc replay log | Network RTT, send/flush/replay lag |
| CPU/scheduler | Chờ CPU, context switch hoặc worker | CPU saturation, runnable queue, scheduling |
| Checkpoint/I/O contention | Data page write cạnh tranh với log write | Checkpoint burst, disk queue, write latency |

Một giao dịch có thể đã hoàn thành mọi câu lệnh nhưng vẫn chờ log flush. Một giao dịch khác có thể mất phần lớn thời gian vì lock wait trước khi đến bước commit. Chỉ nhìn thời gian API `commit()` không đủ để xác định nguyên nhân.

### 11.1. Kích thước giao dịch

Giao dịch lớn tạo nhiều log record, giữ khóa lâu hơn và có thể tăng thời gian rollback/recovery. Nhưng commit latency không nhất thiết tỷ lệ tuyến tính với số hàng: log đã được ghi trong quá trình giao dịch, group commit có thể gom nhiều transaction và storage có batching.

Chia giao dịch lớn thành batch nhỏ có thể giảm lock duration và log burst, nhưng làm tăng số lần commit, overhead round trip và khả năng giao dịch dở dang giữa các batch. Nếu nghiệp vụ yêu cầu atomicity toàn bộ, không thể chia batch tùy tiện mà không thay đổi semantics.

### 11.2. Ghi nhiều index và secondary structure

Một `INSERT` có thể cập nhật bảng, primary index, nhiều secondary index, foreign key, trigger, materialized structure và log. Số lượng index càng lớn, lượng log và random write có thể tăng. Commit phải chờ log bao phủ tất cả thay đổi cần thiết, dù data page có thể ghi sau.

Nếu commit latency tăng cùng số index hoặc log bytes, hãy xem có index không dùng, index trùng lặp hoặc trigger làm tăng write amplification không. Chỉ loại bỏ index khi đã xác minh workload đọc và ràng buộc nghiệp vụ.

### 11.3. Transaction log trên storage dùng chung

Log thường được thiết kế để ghi tuần tự, nhưng nếu storage backend dùng chung với data files, temp files, backup hoặc workload khác, queue và latency có thể tăng. Một volume log riêng chỉ có tác dụng nếu nó tách được tài nguyên thực sự: thiết bị, controller, queue hoặc giới hạn IOPS/throughput. Hai volume logic trên cùng một pool bão hòa có thể không giúp gì.

## 12. Đo lường độ bền và commit latency

### 12.1. Đo ở tầng ứng dụng

Ghi nhận riêng thời gian thực thi các câu lệnh và thời gian gọi `COMMIT`. Đo latency theo percentile (p50, p95, p99), không chỉ average. Ghi thêm số giao dịch/giây, số hàng mỗi transaction, số byte ghi, retry, timeout và thời gian chờ connection pool.

Nếu ứng dụng dùng autocommit, mỗi câu lệnh ghi có thể tạo một transaction riêng; số lần commit tăng làm log flush thường xuyên hơn. Gom các thao tác liên quan vào transaction hợp lý có thể giảm overhead, nhưng transaction quá dài giữ khóa và tăng lượng log chưa hoàn tất. Chọn ranh giới transaction theo tính đúng đắn nghiệp vụ trước, rồi tối ưu số lần commit.

### 12.2. Đo ở tầng database

Thu thập các metric phù hợp với engine:

- Log bytes generated, log write bytes và log flush count.
- Log flush/sync latency, số lần flush trên mỗi transaction.
- Số transaction commit/rollback và throughput.
- Log buffer waits, log file waits hoặc wait events liên quan.
- Dirty pages, buffer writes, checkpoint duration và checkpoint write rate.
- Storage write latency, IOPS, throughput và queue depth.
- Replication send/flush/replay lag và remote acknowledgement time.
- Lock wait, deadlock, transaction age và session bị block.

Ví dụ tên metric/wait thường gặp:

| Hệ quản trị | Tín hiệu có thể quan sát | Cách diễn giải ban đầu |
|---|---|---|
| PostgreSQL | WAL write/sync statistics, `pg_stat_wal`, `pg_stat_bgwriter` hoặc thống kê checkpoint tương ứng phiên bản, wait event liên quan WAL | Xem WAL bytes, write/sync time, checkpoint và replication lag |
| SQL Server | Wait type `WRITELOG`, log flush wait/bytes, log file I/O statistics | Xem session chờ log hardening, latency của log volume và log throughput |
| MySQL/InnoDB | `Innodb_log_waits`, redo log metrics, Performance Schema waits, binary log sync metrics | Xem log buffer pressure, redo write/flush và binlog durability |

Tên view và metric có thể thay đổi theo phiên bản. Hãy đọc định nghĩa và cách reset counter; so sánh delta trong một khoảng đo thay vì lấy tổng counter từ lúc khởi động.

### 12.3. Đo ở tầng storage

Đối chiếu metric database với storage:

- Read/write latency trung bình và percentile.
- IOPS, throughput và queue depth.
- Flush/FUA latency nếu nền tảng cung cấp.
- Cache hit và trạng thái battery/flash-backed cache.
- Thời điểm checkpoint, backup hoặc job khác chạy.
- Network latency với storage từ xa.

Nếu database báo log sync time tăng cùng storage write latency, khả năng nút thắt nằm ở đường ghi. Nếu storage latency bình thường nhưng commit chậm, xem lock wait, scheduler, group commit, replication acknowledgement và connection pool.

## 13. Ví dụ phân tích: commit tăng từ 3 ms lên 40 ms

Giả sử một dịch vụ thanh toán có p50 commit latency 3 ms nhưng p99 tăng lên 40 ms trong giờ cao điểm. Số giao dịch/giây vẫn tăng, nhưng request timeout xuất hiện. Không nên kết luận ngay rằng ổ đĩa đã hỏng.

### 13.1. Thu thập dữ liệu

Đo theo cùng một khoảng thời gian:

| Metric | Trước cao điểm | Trong cao điểm |
|---|---:|---:|
| Transactions/second | 2.000 | 7.500 |
| p50 commit latency | 3 ms | 5 ms |
| p99 commit latency | 6 ms | 40 ms |
| Log flush latency p95 | 2 ms | 18 ms |
| Transactions per flush | 8 | 24 |
| Log volume/second | 20 MB/s | 95 MB/s |
| Replication flush lag p95 | 1 ms | 12 ms |

Các con số chỉ là ví dụ. Chúng cho thấy throughput và group size tăng, nhưng log flush latency và remote flush lag cũng tăng. p50 vẫn tương đối thấp trong khi p99 tăng, gợi ý hàng đợi hoặc dao động storage/replica ảnh hưởng mạnh đến một phần giao dịch.

### 13.2. Đặt giả thuyết

1. **Log storage bão hòa:** log volume có queue depth và write latency tăng khi throughput cao.
2. **Replica đồng bộ chậm:** commit phải chờ remote flush; replica đang apply hoặc flush không theo kịp.
3. **Checkpoint cạnh tranh I/O:** write burst từ data files dùng chung storage làm log flush chậm.
4. **Lock wait:** một phần giao dịch chờ khóa lâu, dù p50 không thay đổi nhiều.
5. **Group commit delay:** batching giúp throughput nhưng thêm thời gian chờ ở đuôi latency.

### 13.3. Kiểm tra và điều chỉnh

- So sánh log sync time với storage latency và queue depth.
- Kiểm tra remote flush/replay lag và trạng thái synchronous standby.
- Đối chiếu thời gian checkpoint với các đỉnh p99.
- Phân loại wait event của các transaction chậm để tách lock wait khỏi log flush wait.
- Kiểm tra số log bytes/transaction và index/trigger có làm write amplification tăng không.
- Thử giới hạn tốc độ batch hoặc điều chỉnh concurrency để xem queue và p99 thay đổi thế nào.
- Nếu storage là nút thắt, đánh giá log volume, IOPS/latency guarantee và write cache có bảo vệ.
- Nếu replica là nút thắt, kiểm tra network và khả năng flush/apply; thay đổi chế độ đồng bộ chỉ sau khi đánh giá RPO và failover policy.

Không dùng `synchronous_commit=off`, delayed durability hoặc cấu hình flush lỏng hơn làm cách sửa mặc định. Các lựa chọn đó thay đổi bảo đảm dữ liệu. Nếu nghiệp vụ cần durability chặt, cần giải quyết năng lực log storage, batching và replica thay vì bỏ điều kiện xác nhận.

## 14. Tối ưu commit mà vẫn giữ đúng mức durability

### 14.1. Giảm số log record không cần thiết

Kiểm tra các index trùng hoặc không được workload dùng, trigger ghi lặp, cập nhật cùng một hàng nhiều lần trong một transaction và câu SQL ghi lại giá trị không đổi. Giảm write amplification có thể giảm WAL/redo bytes, log flush pressure và checkpoint work.

Không xóa index chỉ dựa trên một truy vấn. Đánh giá toàn bộ workload đọc/ghi, constraint, foreign key, replication và yêu cầu uniqueness.

### 14.2. Chọn ranh giới transaction hợp lý

Gom nhiều thao tác nhỏ có quan hệ nghiệp vụ vào một transaction có thể giảm số lần commit và số lần ứng dụng chờ flush. Tuy nhiên, transaction dài giữ khóa lâu, tăng log chưa hoàn tất, tăng nguy cơ deadlock và làm rollback tốn kém.

Nếu một lô có 100 bản ghi độc lập, có thể thử batch theo kích thước phù hợp để cân bằng round trip và lock duration. Nếu 100 bản ghi phải atomic cùng nhau, không chia transaction chỉ vì commit chậm.

### 14.3. Tận dụng group commit tự nhiên

Workload có nhiều transaction ngắn đồng thời có thể hưởng lợi từ group commit. Tránh cấu hình delay lớn mà chưa đo. Thử concurrency theo các mức khác nhau và theo dõi transactions per flush, throughput và p99 commit latency.

### 14.4. Cân bằng checkpoint và dirty page writeback

Điều chỉnh checkpoint để tránh write burst và giữ thời gian recovery trong mục tiêu. Giám sát tốc độ sinh WAL, dirty page, checkpoint write và storage queue. Nếu checkpoint gây cạnh tranh log, có thể cần điều tiết tốc độ ghi trang hoặc tách tài nguyên storage thực sự.

### 14.5. Cải thiện đường ghi log

Đảm bảo log storage có latency ổn định, đủ IOPS và write throughput. Kiểm tra log file preallocation/autogrowth, kích thước log, filesystem, controller cache và queue. Log file tăng kích thước đột ngột hoặc storage pool chia sẻ với backup có thể tạo latency spike.

### 14.6. Tối ưu replication theo yêu cầu nghiệp vụ

Nếu đồng bộ replica là bắt buộc, cải thiện network, năng lực flush/apply và vị trí địa lý của replica. Nếu có nhiều lớp xác nhận, xác định lớp nào cần cho từng loại giao dịch. Không hạ mức đồng bộ chung cho toàn hệ thống khi chỉ một nhóm dữ liệu có thể chấp nhận RPO khác.

## 15. Độ bền, HA và khả năng failover

### 15.1. Commit durable trên primary chưa chắc durable trên replica

Với asynchronous replication, primary có thể xác nhận transaction trước khi replica nhận log. Nếu primary mất sau commit và replica được promote, giao dịch gần đây có thể vắng mặt. Ứng dụng có thể đã gửi email, phát thông báo hoặc gọi dịch vụ ngoài dựa trên giao dịch đó, dẫn đến trạng thái hệ thống không nhất quán.

Với synchronous replication, primary chờ một hoặc nhiều replica xác nhận theo chính sách. Điều này giảm nguy cơ mất giao dịch khi failover nhưng có thể làm commit chậm hoặc không khả dụng nếu replica/network mất kết nối. Synchronous replication không tự động bảo vệ trước mọi tình huống như mất đồng thời các node, lỗi cấu hình quorum hoặc lỗi storage chung.

### 15.2. Thiết kế theo RPO và RTO

Hãy xác định:

- RPO bằng 0 hay có thể chấp nhận mất một khoảng log gần nhất?
- RTO bao lâu để promote replica và mở lại traffic?
- Cần bao nhiêu replica xác nhận trước commit?
- Replica nào được phép làm synchronous standby?
- Hành vi khi synchronous standby không sẵn sàng là chờ, timeout hay chuyển sang chế độ khác?
- Cách ngăn split-brain và bảo đảm fencing/quorum khi failover?

RPO thấp hơn thường đòi hỏi thêm xác nhận đồng bộ và có thể tăng latency. RTO thấp đòi hỏi replica khỏe, log apply nhanh, quy trình promotion tự động hoặc đã diễn tập. Không tối ưu riêng commit latency mà bỏ qua tính đúng đắn của failover.

### 15.3. Transactional outbox và side effects

Nếu ứng dụng cần phát sự kiện sau commit, có thể ghi sự kiện vào outbox trong cùng transaction rồi một worker phát ra message broker. Điều này giúp đồng bộ trạng thái database và sự kiện ở mức ghi outbox, nhưng worker vẫn cần xử lý phát lặp bằng idempotency.

Khi dùng durability lỏng hơn hoặc asynchronous replication, cần hiểu rằng giao dịch database đã trả thành công có thể bị mất sau crash/failover trong cửa sổ cho phép. Outbox không khắc phục được một commit đã mất; nó chỉ bảo đảm sự kiện nằm cùng transaction với dữ liệu nếu transaction đó được phục hồi.

## 16. Quy trình điều tra commit chậm

1. **Đo commit riêng biệt.** Thu thập p50/p95/p99 của thời gian gọi commit, tần suất giao dịch và số transaction mỗi giây.
2. **Phân loại wait.** Xác định thời gian nằm ở lock, log flush, remote acknowledgement, CPU scheduler hay connection pool.
3. **Đọc metric log.** Kiểm tra log bytes, flush count, sync latency, log buffer wait và transactions per flush.
4. **Đọc metric storage.** Đối chiếu latency, queue depth, IOPS, throughput và flush semantics của thiết bị.
5. **Đọc metric checkpoint/buffer.** Kiểm tra dirty page, background write, checkpoint burst và foreground write.
6. **Đọc metric replication.** Phân biệt send, write, flush và replay lag; xác định commit phải chờ mức nào.
7. **Kiểm tra workload ghi.** Đếm index, trigger, foreign key, số log bytes mỗi transaction và transaction duration.
8. **Lập giả thuyết và thay đổi một yếu tố.** Ví dụ giảm write amplification, điều tiết batch, sửa storage contention hoặc cải thiện replica.
9. **Đo lại trong cùng điều kiện.** So sánh p95/p99 commit, throughput, log flush, I/O, replication lag và correctness.
10. **Xác nhận durability.** Kiểm tra cấu hình sau thay đổi vẫn đáp ứng RPO, crash recovery và failover policy đã cam kết.

## 17. Những lỗi thường gặp

- **Cho rằng COMMIT phải ghi mọi data page:** với WAL, commit thường cần log bền vững; data page có thể ghi sau.
- **Đồng nhất write với durable flush:** write có thể mới tới page cache; cần hiểu semantics fsync/flush của storage stack.
- **Tắt fsync hoặc write barrier để benchmark nhanh:** có thể làm mất giao dịch đã xác nhận hoặc gây hỏng dữ liệu sau sự cố.
- **Hạ durability mà không cập nhật RPO:** thay đổi kỹ thuật có thể vi phạm cam kết nghiệp vụ và quy trình failover.
- **Coi group commit là bỏ flush:** group commit gom nhiều giao dịch vào cùng lần flush nhưng vẫn chờ ranh giới bền vững theo chế độ đồng bộ.
- **Tăng group delay quá cao:** throughput có thể tăng nhưng p95/p99 commit cũng tăng.
- **Nhầm checkpoint với commit:** checkpoint ghi data page và rút ngắn recovery; nó không phải điều kiện để mọi transaction commit.
- **Tăng buffer pool mà không đo storage:** có thể tích tụ thêm dirty page nhưng không tăng năng lực writeback.
- **Chỉ xem average latency:** p99 có thể bị chi phối bởi storage queue, replica hoặc checkpoint burst.
- **Cho rằng local commit đồng nghĩa replica đã có dữ liệu:** cần biết replication synchronous hay asynchronous và mức acknowledgement.
- **Chia transaction quá nhỏ:** giảm lock duration nhưng tăng số lần commit và overhead; có thể phá vỡ atomicity nghiệp vụ.
- **Gom transaction quá lớn:** giảm số lần commit nhưng giữ lock lâu, tăng log và thời gian rollback.
- **Tách volume logic nhưng dùng chung backend bão hòa:** không giảm tranh chấp tài nguyên thực tế.
- **Bỏ qua binary log/redo coordination:** durability của nhiều log stream phải được xem xét cùng nhau.

## 18. Bài tập tự kiểm tra

**Bài 1.** Một transaction cập nhật 20 trang dữ liệu. Vì sao database có thể trả `COMMIT` thành công trước khi cả 20 trang được ghi xuống file dữ liệu?

*Gợi ý:* Với WAL, database flush log record và commit record tới ranh giới bền vững trước. Dirty data page có thể được background writer/checkpoint ghi sau; recovery dùng log để redo nếu crash xảy ra.

**Bài 2.** Storage có write latency 2 ms nhưng log sync latency p99 là 25 ms. Những nguyên nhân nào cần kiểm tra?

*Gợi ý:* Queue depth và tail latency, flush/FUA latency, log volume có dùng chung backend với checkpoint/backup không, group commit, virtualization/storage network, controller cache và metric có cùng phạm vi đo không.

**Bài 3.** Vì sao group commit có thể tăng throughput nhưng làm giao dịch đầu nhóm chờ lâu hơn?

*Gợi ý:* Nhiều transaction dùng chung một lần flush; giao dịch đến trước có thể chờ nhóm hình thành. Số flush trên mỗi transaction giảm nhưng batching delay có thể tăng latency.

**Bài 4.** Primary xác nhận commit sau local WAL flush nhưng replication bất đồng bộ. Điều gì có thể xảy ra nếu primary mất ngay sau đó?

*Gợi ý:* Replica có thể chưa nhận hoặc chưa flush log của giao dịch. Nếu promote replica đó, giao dịch gần đây có thể mất dù ứng dụng đã nhận xác nhận từ primary.

**Bài 5.** Một đội muốn đặt `innodb_flush_log_at_trx_commit=2` để giảm commit latency. Câu hỏi nào phải được trả lời trước?

*Gợi ý:* Ứng dụng có chấp nhận mất các giao dịch gần đây khi OS/máy crash không? RPO là bao nhiêu? Binary log sync ra sao? Storage và group commit đã được đo/tối ưu chưa? Phiên bản và semantics cấu hình là gì?

**Bài 6.** Commit latency tăng theo chu kỳ mỗi khi checkpoint bắt đầu. Bạn sẽ đối chiếu những metric nào?

*Gợi ý:* Checkpoint duration/write rate, dirty pages, log flush latency, storage queue depth, data/log volume contention và p95/p99 commit theo thời gian.

## 19. Ghi nhớ khi tối ưu

Độ bền của giao dịch thường được bảo đảm bằng cách lưu bền vững log trước khi xác nhận commit; các trang dữ liệu có thể được ghi xuống sau thông qua background writer và checkpoint. Flush/fsync, group commit, storage cache và replication acknowledgement quyết định thời điểm ứng dụng nhận xác nhận cũng như mức bảo vệ trước sự cố.

Khi commit chậm, hãy tách thời gian lock wait, log generation, local flush, group commit, checkpoint contention và remote acknowledgement. Đo p95/p99 cùng throughput, log bytes, sync latency, storage queue và replication lag. Tối ưu số log record, transaction boundary, group commit, checkpoint và năng lực storage theo workload thực tế. Chỉ thay đổi mức đồng bộ khi đã xác định rõ RPO/RTO và chấp nhận tác động lên crash recovery/failover; tốc độ commit không thể được đánh đổi một cách mơ hồ với dữ liệu mà ứng dụng tin rằng đã được lưu an toàn.
