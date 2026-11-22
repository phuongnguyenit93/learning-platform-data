# Commit chậm, redo log switch và nghẽn vùng phục hồi

Commit chậm, redo log switch kéo dài và vùng phục hồi (Fast Recovery Area - FRA) đầy thường xuất hiện cùng nhau trong các sự cố Oracle Database. Chúng có liên quan vì Oracle phải ghi redo để bảo đảm transaction có thể được khôi phục, chuyển sang redo log group kế tiếp và lưu archived redo log khi database chạy ARCHIVELOG mode. Tuy nhiên, mỗi triệu chứng có nguyên nhân và cách xử lý riêng.

Khi một ứng dụng báo commit mất nhiều giây, cần xác định foreground session đang chờ LGWR ghi redo, LGWR bị chậm ở thiết bị lưu trữ, database chuyển log không kịp, hay synchronous Data Guard đang chờ standby xác nhận. Khi log switch bị chậm, cần phân biệt checkpoint chưa hoàn tất với archive destination không ghi được. Khi FRA đầy, cần tìm loại file đang chiếm dung lượng và xác định file nào thực sự có thể reclaim theo chính sách backup, archive và flashback.

Các nguyên tắc cốt lõi:

- COMMIT phải bảo đảm redo cần thiết được ghi bền vững theo commit semantics đang cấu hình.
- Wait event log file sync thường cho biết foreground session đang chờ LGWR hoàn tất ghi redo cho commit.
- Wait event log file parallel write phản ánh thời gian LGWR chờ thao tác ghi redo log xuống storage.
- Log switch là hoạt động bình thường; switch quá thường xuyên hoặc không thể tái sử dụng log group mới là dấu hiệu cần điều tra.
- FRA đầy có thể làm archive log không ghi được, từ đó ngăn log group được tái sử dụng và làm transaction hoặc database bị ảnh hưởng.
- Không xóa file trong FRA bằng lệnh hệ điều hành để giải phóng chỗ. Dùng RMAN và chính sách retention/deletion phù hợp.
- Không đổi COMMIT sang NOWAIT, tắt ARCHIVELOG hoặc giảm bảo vệ Data Guard chỉ để che triệu chứng.

## 1. Đường đi của COMMIT trong Oracle

Oracle dùng redo để ghi lại thông tin cần thiết nhằm phục hồi thay đổi. Khi transaction thay đổi block dữ liệu, thông tin redo được tạo trong redo log buffer ở SGA. Khi transaction commit, Oracle ghi commit record vào redo và yêu cầu LGWR ghi redo cần thiết xuống online redo log.

Mô hình đơn giản:

    Client application
          |
          | COMMIT
          v
    Foreground server process
          |
          | commit record / redo
          v
    Redo log buffer (SGA)
          |
          | request LGWR flush
          v
    LGWR process
          |
          | synchronous write
          v
    Online redo log files
          |
          | durable commit acknowledgment
          v
    Foreground returns success
          |
          v
    Client receives COMMIT success

Với commit semantics mặc định thông dụng là WAIT, foreground chỉ trả thành công sau khi redo cần thiết được LGWR ghi theo cơ chế durability của Oracle. Oracle có thể gom nhiều commit gần nhau vào một lần ghi (group commit), nên không phải mỗi transaction luôn tạo một thao tác I/O riêng.

### 1.1. Redo log buffer

Redo log buffer là vùng nhớ trong SGA lưu các redo entries trước khi LGWR ghi xuống online redo log. Foreground process tạo redo khi thay đổi dữ liệu và đưa redo vào buffer.

Redo buffer không phải nơi lưu transaction bền vững. Khi instance bị mất trước khi redo cần thiết được ghi xuống online redo log, những thay đổi chưa được bảo vệ bởi redo durable có thể bị mất; Oracle dùng redo và undo để phục hồi trạng thái database sau sự cố.

Nếu LGWR không theo kịp tốc độ tạo redo, foreground có thể chờ do thiếu chỗ trong redo log buffer. Wait event thường gặp là log buffer space. Đây là vấn đề khác với log file sync: một bên là chờ không gian trong buffer để ghi redo, bên kia là chờ LGWR hoàn tất flush phục vụ commit.

### 1.2. LGWR

LGWR (Log Writer) ghi redo từ redo log buffer xuống online redo log files. LGWR hoạt động theo nhiều điều kiện, trong đó có commit request, buffer cần được giải phóng và các điều kiện nội bộ khác.

Khi một transaction commit, foreground thông báo cho LGWR rằng redo đến commit record phải được ghi. LGWR có thể gom yêu cầu của nhiều transaction vào cùng một lần ghi. Đây là group commit, giúp giảm số lần I/O cần thiết khi nhiều session commit gần nhau.

Nếu storage redo log có độ trễ cao, LGWR ghi chậm và foreground session chờ lâu. Nếu LGWR bị thiếu CPU, bị scheduling delay hoặc có cạnh tranh tài nguyên, commit cũng có thể chậm dù storage không phải nguyên nhân duy nhất.

### 1.3. Online redo log

Online redo log gồm nhiều group. Mỗi group có một hoặc nhiều member. Oracle ghi redo vào group hiện tại theo thread; khi group đầy hoặc có yêu cầu switch, database chuyển sang group tiếp theo.

Các member trong cùng một group là các bản sao multiplexed để bảo vệ khỏi lỗi một file/member. Thêm member không làm tăng dung lượng redo của group; nó tăng khả năng chịu lỗi cho redo log. Tăng kích thước group hoặc số group mới thay đổi khoảng thời gian trước khi group cần được tái sử dụng.

### 1.4. Archived redo log

Trong ARCHIVELOG mode, trước khi online redo log group được tái sử dụng, Oracle cần archive redo của group đó theo chính sách archive destination. ARCn hoặc tiến trình archiving phù hợp đọc online redo log và tạo archived redo log.

Archived redo log là thành phần quan trọng cho media recovery, backup và Data Guard. Nếu archive destination không khả dụng hoặc hết dung lượng, Oracle có thể không tái sử dụng được log group cần thiết.

### 1.5. FRA

Fast Recovery Area là vùng lưu trữ được Oracle quản lý cho các file liên quan đến recovery, chẳng hạn archived redo log, flashback log, RMAN backup piece, control file autobackup và một số file recovery khác tùy cấu hình.

FRA có giới hạn dung lượng cấu hình. Khi đạt giới hạn, Oracle cố reclaim file đủ điều kiện theo retention policy và deletion policy. Nếu không còn file nào có thể reclaim và không thể ghi thêm file cần thiết, archive hoặc backup có thể thất bại.

## 2. Hiểu các wait event liên quan commit và redo

Để chẩn đoán đúng, trước tiên phải phân biệt foreground wait, LGWR I/O và log switch/archive wait.

| Wait event | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| log file sync | Foreground chờ LGWR hoàn tất ghi redo phục vụ commit | Commit frequency, LGWR latency, storage, scheduling, Data Guard |
| log file parallel write | LGWR chờ ghi online redo log xuống storage | Độ trễ redo storage, I/O path, multipath/ASM, thiết bị |
| log buffer space | Foreground chờ có chỗ trong redo log buffer | Redo generation rate, LGWR throughput, buffer pressure |
| log file switch (checkpoint incomplete) | Không thể tái sử dụng group vì checkpoint chưa hoàn tất | Checkpoint, DBWR, datafile I/O, log size/group count |
| log file switch (archiving needed) | Group chưa thể tái sử dụng vì archive chưa xong | ARCn, archive destination, FRA, Data Guard/archive policy |
| log file switch completion | Foreground chờ log switch hoàn tất | Switch operation, checkpoint, archive, group availability |

Tên event và chi tiết đo lường có thể thay đổi theo Oracle release. Hãy xem đúng event đang xuất hiện trong V$SESSION, V$SYSTEM_EVENT và tài liệu release.

### 2.1. log file sync

Đây là wait event thường được quan sát khi ứng dụng nói commit chậm. Foreground session chờ LGWR xác nhận redo đã được ghi theo commit mode.

Nguyên nhân có thể gồm:

- Redo log storage có latency cao.
- LGWR bị CPU scheduling delay hoặc cạnh tranh tài nguyên.
- Ứng dụng commit quá thường xuyên, tạo nhiều request nhỏ.
- Nhiều session đồng thời commit và tạo tải redo lớn.
- Data Guard synchronous transport làm tăng thời gian acknowledgment.
- Hệ thống virtualization/storage có vấn đề với synchronous write.
- Một số trường hợp có contention hoặc queue ở tầng I/O.

Không thể kết luận storage chậm chỉ từ việc log file sync tăng. Cần đối chiếu với log file parallel write và số liệu I/O của storage.

### 2.2. log file parallel write

Event này phản ánh thời gian LGWR chờ các thao tác ghi redo log. Nếu event này có latency cao cùng thời điểm log file sync cao, storage path của redo là nghi phạm quan trọng.

Cần kiểm tra:

- Latency ghi của volume/ASM disk group chứa redo.
- IOPS và queue depth.
- Throughput và write cache policy.
- SAN/NVMe/virtual disk health.
- Multipath path failover hoặc path degraded.
- Storage contention với datafile, archive log và backup.
- Sự khác biệt giữa các member của cùng log group.

Redo log thường nhạy với write latency hơn throughput thuần. Một workload có nhiều commit nhỏ cần nhiều synchronous write; thiết bị có latency cao có thể làm response time xấu dù bandwidth còn dư.

### 2.3. log buffer space

Event này cho biết foreground không thể cấp thêm redo buffer space đủ nhanh. Nó có thể xuất hiện khi tốc độ sinh redo vượt tốc độ LGWR giải phóng buffer.

Điều tra:

- LGWR có đang bị chậm ở storage không.
- Redo generation tăng đột biến do bulk DML, index maintenance hoặc batch.
- Redo log buffer allocation retries có tăng không.
- Có transaction hoặc workload tạo redo rất lớn không.
- Storage và CPU có đang bão hòa không.

Tăng LOG_BUFFER không phải cách sửa đầu tiên. Nếu LGWR không thể ghi redo đủ nhanh, buffer lớn hơn chỉ trì hoãn thời điểm bị nghẽn và có thể làm tăng memory usage. Hãy tìm nguyên nhân LGWR throughput thấp trước.

### 2.4. log file switch (checkpoint incomplete)

Oracle muốn chuyển sang group tiếp theo nhưng group đó chưa thể tái sử dụng vì checkpoint của group cũ chưa hoàn tất. DBWR cần ghi dirty buffers tương ứng xuống datafiles để checkpoint tiến triển.

Nguyên nhân có thể là:

- Redo log groups quá nhỏ so với redo generation rate.
- Quá ít log groups nên thời gian giữa các lần tái sử dụng ngắn.
- Datafile storage ghi chậm.
- DBWR bị cạnh tranh CPU/I/O.
- Workload tạo redo burst lớn.

Tăng kích thước redo log có thể kéo dài thời gian giữa các lần switch; thêm group có thể tăng khoảng thời gian trước khi một group cần được tái sử dụng. Tuy nhiên, nếu datafile I/O hoặc DBWR là nút thắt, cần xử lý checkpoint/storage thay vì chỉ thêm log group.

### 2.5. log file switch (archiving needed)

Oracle cần tái sử dụng một group nhưng archived redo log của group đó chưa hoàn tất hoặc archive destination không thể nhận file.

Nguyên nhân thường gặp:

- FRA đầy.
- Archive destination filesystem/ASM disk group đầy.
- Archive destination bị lỗi hoặc không mount.
- ARCn thiếu khả năng xử lý so với redo generation rate.
- Network destination hoặc standby archive transport gặp sự cố.
- Deletion policy ngăn xóa archived log vì chưa backup hoặc chưa apply trên standby.

Trong trường hợp này, thêm redo log group có thể trì hoãn thời điểm bị nghẽn, nhưng không giải quyết nguyên nhân archive destination không ghi được. Phải khôi phục khả năng archive.

## 3. Đo commit latency và redo I/O

Không chỉ nhìn một snapshot. Cần lấy số liệu theo khoảng thời gian để xác định xu hướng, so sánh giờ bình thường với giờ xảy ra sự cố và phân biệt session cụ thể với toàn hệ thống.

### 3.1. Xem foreground session đang chờ

    SELECT
        sid,
        serial#,
        username,
        module,
        action,
        event,
        wait_class,
        state,
        seconds_in_wait,
        blocking_session
    FROM v$session
    WHERE wait_class <> 'Idle'
      AND event IN (
        'log file sync',
        'log file switch completion',
        'log file switch (checkpoint incomplete)',
        'log file switch (archiving needed)',
        'log buffer space'
      )
    ORDER BY seconds_in_wait DESC;

Truy vấn này cho thấy session đang chờ tại thời điểm truy vấn. Nó không thay thế lịch sử wait. Một wait ngắn có thể kết thúc trước khi DBA chạy query.

Đặt MODULE/ACTION trong ứng dụng giúp nhận diện service hoặc code path đang tạo commit. Nếu mọi session dùng cùng một database user và không có module, việc xác định caller sẽ khó hơn.

### 3.2. So sánh tổng wait và average wait

    SELECT
        event,
        total_waits,
        ROUND(time_waited_micro / 1000000, 2) AS total_wait_seconds,
        ROUND(
          time_waited_micro / NULLIF(total_waits, 0) / 1000,
          3
        ) AS average_wait_ms
    FROM v$system_event
    WHERE event IN (
      'log file sync',
      'log file parallel write',
      'log buffer space',
      'log file switch completion',
      'log file switch (checkpoint incomplete)',
      'log file switch (archiving needed)'
    )
    ORDER BY time_waited_micro DESC;

Các giá trị trong V$SYSTEM_EVENT là bộ đếm tích lũy từ khi instance khởi động hoặc theo cơ chế reset tương ứng. Lấy hai snapshot cách nhau một khoảng thời gian rồi tính delta sẽ hữu ích hơn đọc tổng từ startup.

Average wait có thể che giấu tail latency. Nếu có sẵn công cụ theo dõi histogram hoặc lịch sử wait, hãy xem phân phối p95/p99 thay vì chỉ nhìn trung bình.

### 3.3. Histogram của wait event

    SELECT
        event,
        wait_time_milli,
        wait_count
    FROM v$event_histogram
    WHERE event IN (
      'log file sync',
      'log file parallel write'
    )
    ORDER BY event, wait_time_milli;

Histogram cho thấy số wait rơi vào từng bucket thời gian. Nó giúp phát hiện các commit có latency rất cao dù average không quá lớn. Cách diễn giải bucket phụ thuộc view/version; hãy đọc tài liệu tương ứng.

### 3.4. Thống kê redo và commit

    SELECT
        name,
        value
    FROM v$sysstat
    WHERE name IN (
      'user commits',
      'user rollbacks',
      'redo size',
      'redo entries',
      'redo writes',
      'redo write time',
      'redo log space requests',
      'redo log space wait time',
      'redo buffer allocation retries'
    )
    ORDER BY name;

Đây cũng là bộ đếm tích lũy. So sánh delta giữa hai thời điểm để biết workload thay đổi thế nào. Một số statistic đo thời gian theo centiseconds hoặc đơn vị riêng; kiểm tra tài liệu Oracle trước khi tự tính latency từ raw value.

Các chỉ số hữu ích:

- User commits tăng nhanh cho biết số transaction commit.
- Redo size cho biết lượng redo sinh ra.
- Redo writes và redo write time giúp quan sát hoạt động LGWR.
- Redo log space requests/wait time có thể chỉ ra foreground phải chờ redo buffer/log space.
- Redo buffer allocation retries tăng là tín hiệu cần xem LGWR và redo buffer pressure.

Không chỉ nhìn tổng redo size. Một hệ thống tạo nhiều redo nhưng commit ít có thể có profile latency khác với hệ thống tạo ít redo nhưng commit hàng nghìn lần mỗi giây.

### 3.5. Kiểm tra LGWR process và I/O

    SELECT
        p.spid,
        p.program,
        s.event,
        s.state,
        s.seconds_in_wait
    FROM v$process p
    JOIN v$session s
      ON s.paddr = p.addr
    WHERE UPPER(p.program) LIKE '%LGWR%';

Cách hiển thị process name phụ thuộc platform/release. Có thể cần kiểm tra background process qua V$BGPROCESS hoặc hệ điều hành. Kết hợp với OS/storage metrics để biết LGWR đang chờ I/O, CPU hay một điều kiện khác.

## 4. Kiểm tra redo log group và tần suất log switch

### 4.1. Xem online redo log groups

    SELECT
        group#,
        thread#,
        sequence#,
        ROUND(bytes / 1024 / 1024) AS size_mb,
        members,
        archived,
        status,
        first_time
    FROM v$log
    ORDER BY thread#, group#;

Các trạng thái thường gặp gồm CURRENT, ACTIVE, INACTIVE và UNUSED. CURRENT là group đang nhận redo. ACTIVE có thể còn cần cho instance recovery/checkpoint; INACTIVE là group không còn cần cho instance recovery và có thể được tái sử dụng theo điều kiện archive.

ARCHIVED cho biết trạng thái archive của group trong ngữ cảnh view. Cần kết hợp với log history và archive destination để hiểu tình trạng thực tế.

### 4.2. Xem member và đường dẫn redo log

    SELECT
        group#,
        type,
        member,
        status,
        is_recovery_dest_file
    FROM v$logfile
    ORDER BY group#, member;

Kiểm tra mỗi group có đủ member theo kiến trúc redundancy. Các member trong một group nên đặt trên failure domain phù hợp nếu yêu cầu bảo vệ chống mất một thiết bị. Đặt hai member cùng một filesystem/disk group duy nhất có thể không tạo được mức bảo vệ mong muốn.

Thêm member không tăng dung lượng group hoặc kéo dài thời gian trước log switch. Nó là cơ chế multiplexing để bảo vệ log file.

### 4.3. Tính số lần switch theo giờ

    SELECT
        TRUNC(first_time, 'HH24') AS switch_hour,
        thread#,
        COUNT(*) AS switch_count
    FROM v$log_history
    WHERE first_time >= SYSDATE - 2
    GROUP BY TRUNC(first_time, 'HH24'), thread#
    ORDER BY switch_hour, thread#;

Tần suất switch cần được so sánh với redo generation và workload. Không có một khoảng switch duy nhất phù hợp với mọi database; các lần switch quá sát nhau trong thời gian tải bình thường là dấu hiệu log groups có thể quá nhỏ hoặc workload tăng đột biến.

### 4.4. Xem thời gian giữa các lần switch

    SELECT
        thread#,
        sequence#,
        first_time,
        first_time - LAG(first_time) OVER (
          PARTITION BY thread#
          ORDER BY first_time
        ) AS interval_days
    FROM v$log_history
    WHERE first_time >= SYSDATE - 1
    ORDER BY thread#, first_time;

INTERVAL_DAYS là khoảng cách theo đơn vị ngày. Nhân với 1440 để đổi ra phút. Xem cả khoảng switch ngắn nhất và thời điểm workload tăng cao.

### 4.5. Log switch bình thường và log switch gây sự cố

Log switch xảy ra khi redo log group đầy hoặc được yêu cầu switch. Nó là hoạt động bình thường. Điều cần điều tra là:

- Switch quá thường xuyên so với tải thông thường.
- Foreground chờ lâu khi switch.
- Group kế tiếp chưa thể tái sử dụng.
- Archive log không được tạo kịp.
- Checkpoint không hoàn tất trước lúc group cần dùng lại.

Đừng cố loại bỏ hoàn toàn log switch. Mục tiêu là có kích thước và số group phù hợp để archive/checkpoint theo kịp redo generation.

## 5. Chẩn đoán từng loại log switch wait

### 5.1. Checkpoint incomplete

Kiểm tra wait event và trạng thái log group:

    SELECT
        group#,
        thread#,
        sequence#,
        status,
        archived,
        ROUND(bytes / 1024 / 1024) AS size_mb
    FROM v$log
    ORDER BY thread#, group#;

Nếu Oracle chờ checkpoint incomplete, group cần tái sử dụng chưa đủ điều kiện. Kiểm tra datafile I/O, DBWR và checkpoint progress.

Một số thống kê cần theo dõi:

    SELECT
        name,
        value
    FROM v$sysstat
    WHERE name IN (
      'background checkpoints started',
      'background checkpoints completed',
      'DBWR checkpoint buffers written',
      'physical writes',
      'physical writes from cache'
    )
    ORDER BY name;

Các statistic này là tổng thể và cần so sánh delta. Để phân tích sâu, dùng metric storage, DBWR wait và checkpoint information phù hợp release.

Hướng xử lý thường gồm:

- Tăng kích thước redo log group để giảm tần suất switch.
- Bổ sung group để kéo dài khoảng thời gian trước khi group cũ cần tái sử dụng.
- Kiểm tra DBWR và datafile storage latency.
- Kiểm tra workload tạo dirty buffers quá nhanh.
- Xem xét checkpoint target và cấu hình recovery time theo chính sách.
- Không ép checkpoint liên tục như biện pháp chữa cháy nếu chưa hiểu tác động I/O.

### 5.2. Archiving needed

Kiểm tra archive destinations:

    SELECT
        dest_id,
        status,
        target,
        destination,
        error
    FROM v$archive_dest
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

Nếu có ERROR, kiểm tra path, mount, ASM disk group, quyền, network và trạng thái standby/destination. Xem log archive gần nhất:

    SELECT
        thread#,
        sequence#,
        dest_id,
        first_time,
        completion_time,
        archived,
        applied,
        deleted,
        status,
        name
    FROM v$archived_log
    WHERE completion_time >= SYSDATE - 1
    ORDER BY completion_time DESC;

Với destination từ xa, kiểm tra network connectivity, service và Data Guard transport. Với local destination, kiểm tra dung lượng filesystem/ASM và quyền ghi.

Không thêm log groups vô hạn để né archive failure. Khi các group mới cũng đầy và không thể archive, database cuối cùng vẫn có thể bị chặn.

### 5.3. Log file switch completion

Event này có thể phản ánh foreground đang chờ hoàn tất chuyển log group. Cần đối chiếu cùng thời điểm với:

- Checkpoint incomplete.
- Archiving needed.
- LGWR I/O.
- Tần suất log switch.
- Số group và trạng thái từng group.

Nếu chỉ nhìn event completion, có thể bỏ lỡ nguyên nhân gốc là checkpoint hoặc archive.

## 6. Kích thước và số lượng redo log groups

### 6.1. Vì sao log quá nhỏ gây switch thường xuyên?

Redo log group có dung lượng cố định. Khi redo generation rate cao, group đầy nhanh và Oracle phải chuyển sang group khác. Nếu group tiếp theo chưa thể tái sử dụng do checkpoint/archive chưa xong, foreground có thể chờ.

Ước lượng thời gian sử dụng một group:

    Approximate switch interval
      = usable redo bytes per group
        / redo generation rate per second

Ví dụ một group có dung lượng 1 GB và workload sinh redo trung bình 20 MB/s:

    1,024 MB / 20 MB/s ≈ 51 seconds

Đây chỉ là ước lượng đơn giản. Redo rate thay đổi theo workload, thread và overhead; dung lượng usable thực tế và điều kiện switch cũng ảnh hưởng. Dùng peak/representative redo rate thay vì chỉ average trong giờ thấp điểm.

### 6.2. Tăng kích thước group

Tăng kích thước group làm kéo dài khoảng thời gian giữa các lần switch, giảm tần suất archive và checkpoint transition. Tuy nhiên, group lớn hơn có thể làm lượng redo cần archive trong mỗi lần lớn hơn và thời gian xử lý mỗi archive dài hơn.

Kích thước phải phù hợp với:

- Redo generation peak.
- Thời gian archive một group.
- Checkpoint throughput.
- Recovery requirements.
- FRA capacity và archive destination throughput.
- Data Guard transport/apply capability.

Không chọn kích thước chỉ để đạt một số lần switch cố định mà bỏ qua archive/recovery capacity.

### 6.3. Tăng số lượng group

Thêm group làm tăng số group luân phiên trước khi group cũ cần tái sử dụng. Điều này tạo thêm thời gian cho checkpoint và archiving hoàn tất.

Trong RAC, mỗi redo thread có bộ redo log groups riêng; cần kiểm tra thread nào bị nghẽn và cấu hình groups cho từng thread theo kiến trúc.

Thêm group không làm giảm redo generation và không tăng tốc storage. Nếu archive destination bị đầy liên tục, nhiều group chỉ trì hoãn lúc database bị chặn.

### 6.4. Thêm group theo kế hoạch

Ví dụ tạo một group mới:

    ALTER DATABASE ADD LOGFILE GROUP 4 (
      '/u02/oradata/DB/redo04a.log',
      '/u03/oradata/DB/redo04b.log'
    ) SIZE 2G;

Đường dẫn, tên group, size và số member chỉ là ví dụ. Kiểm tra naming, storage redundancy, OMF/ASM, block size, thread và giới hạn của release trước khi chạy.

Không thêm group trùng số hoặc đặt các member trên cùng failure domain nếu yêu cầu multiplexing cần tách storage.

### 6.5. Thay đổi kích thước group hiện có

Oracle không cho resize online redo log group theo cách đơn giản như đổi kích thước một datafile. Quy trình thường là thêm group mới với kích thước mong muốn, chuyển workload qua các group mới, chờ group cũ không còn CURRENT/ACTIVE và không còn cần archive, rồi drop group cũ theo điều kiện cho phép.

Ví dụ drop group:

    ALTER DATABASE DROP LOGFILE GROUP 1;

Chỉ thực hiện khi group có thể drop theo trạng thái và điều kiện của Oracle. Không drop group CURRENT hoặc group còn ACTIVE/chưa archived. Với RAC, phải xem thread và group status tương ứng. Thực hiện trong change window và giữ đủ số group theo yêu cầu database.

### 6.6. Multiplex member đúng cách

Một group có nhiều member bảo vệ trước lỗi member. Nếu một member bị lỗi, Oracle có thể tiếp tục với member còn lại trong một số tình huống, tùy trạng thái và khả năng truy cập.

Multiplex không phải backup. Nếu mọi member cùng nằm trên một thiết bị hoặc failure domain, một sự cố storage có thể làm mất tất cả bản sao. Đặt member trên các disk group hoặc thiết bị độc lập theo thiết kế storage.

## 7. FRA và nguyên nhân vùng phục hồi bị đầy

FRA được Oracle quản lý để lưu file cần cho recovery. Dung lượng bị chiếm có thể đến từ nhiều loại file:

- Archived redo log.
- Flashback log.
- RMAN backup piece.
- Control file autobackup.
- Image copy hoặc file backup liên quan.
- Foreign archived log trong một số cấu hình Data Guard.
- Các file recovery khác theo phiên bản và cấu hình.

FRA đầy không có nghĩa mọi file trong đó đều có thể xóa. Oracle đánh giá file nào có thể reclaim theo retention policy, backup status, archive deletion policy, flashback requirement và các điều kiện recovery.

### 7.1. Kiểm tra dung lượng FRA

    SELECT
        name,
        ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
        ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
        ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
        number_of_files
    FROM v$recovery_file_dest;

Các giá trị quan trọng:

- SPACE_LIMIT: giới hạn FRA cấu hình.
- SPACE_USED: dung lượng đang được FRA quản lý.
- SPACE_RECLAIMABLE: dung lượng Oracle đánh giá có thể reclaim theo chính sách hiện tại.
- NUMBER_OF_FILES: số file đang được quản lý trong FRA.

Nếu reclaimable gần bằng 0 và used gần limit, database có nguy cơ không ghi được archive/backup mới. Nếu reclaimable lớn nhưng không giải phóng được, kiểm tra điều kiện reclaim, retention và thao tác RMAN phù hợp.

### 7.2. Phân tích theo loại file

    SELECT
        file_type,
        percent_space_used,
        percent_space_reclaimable,
        number_of_files
    FROM v$flash_recovery_area_usage
    ORDER BY percent_space_used DESC;

View này giúp xác định archived log, flashback log hay backup piece đang chiếm tỷ lệ lớn. Tên view/cột và loại file có thể khác theo release; kiểm tra data dictionary nếu môi trường dùng phiên bản khác.

### 7.3. Kiểm tra FRA destination và size

    SHOW PARAMETER db_recovery_file_dest;
    SHOW PARAMETER db_recovery_file_dest_size;

Hoặc:

    SELECT name, value
    FROM v$parameter
    WHERE name IN (
      'db_recovery_file_dest',
      'db_recovery_file_dest_size'
    )
    ORDER BY name;

DB_RECOVERY_FILE_DEST chỉ ra vị trí FRA; DB_RECOVERY_FILE_DEST_SIZE là giới hạn cấu hình. Giới hạn cấu hình không tạo thêm dung lượng vật lý. Nếu dùng ASM, kiểm tra disk group free space; nếu dùng filesystem, kiểm tra mount capacity và inode.

### 7.4. Guaranteed restore point và flashback log

Guaranteed restore point có thể giữ flashback log cần thiết để database có thể flashback về điểm đó. Nếu restore point tồn tại lâu và database tạo nhiều redo, flashback log có thể chiếm FRA đáng kể.

Kiểm tra:

    SELECT
        name,
        time,
        guarantee_flashback_database,
        storage_size
    FROM v$restore_point
    ORDER BY time;

Không drop guaranteed restore point chỉ để giải phóng dung lượng khi chưa xác nhận mục đích và thời hạn bảo vệ của nó. Drop restore point có thể loại bỏ khả năng flashback về mốc đã cam kết. Cần chủ sở hữu change/recovery phê duyệt trước khi thay đổi.

## 8. FRA đầy ảnh hưởng tới archive và commit như thế nào?

Một chuỗi sự cố thường gặp:

    FRA hoặc archive destination đầy
                |
                v
    ARCn không ghi được archived redo log
                |
                v
    Online redo group chưa thể tái sử dụng
                |
                v
    Database chờ log switch / archiving
                |
                v
    Foreground DML và commit bị chậm
                |
                v
    Ứng dụng timeout hoặc không ghi được dữ liệu

Không phải mọi commit chậm đều do FRA. Tuy nhiên, nếu archive destination lỗi và log group sắp hết, log switch wait có thể làm database không còn redo log group trống để tiếp tục ghi.

### 8.1. Lỗi thường gặp khi FRA/archive bị đầy

Một số lỗi thường thấy:

| Oracle error | Ý nghĩa thường gặp |
|---|---|
| ORA-19809 | DB_RECOVERY_FILE_DEST_SIZE đã bị vượt |
| ORA-19804 | Không reclaim đủ dung lượng trong FRA cho yêu cầu |
| ORA-00257 | Archiver error; kết nối có thể bị hạn chế cho tới khi xử lý |
| ORA-16038 | Không archive được redo log sequence |
| ORA-16014 | Không có destination khả dụng để archive log |
| ORA-19504 | Không tạo được file |
| ORA-270xx | Lỗi hệ điều hành/storage khi truy cập file |

Thông điệp cụ thể phụ thuộc lỗi gốc. Đọc alert log, trace ARCn và archive destination error để xác định filesystem, ASM, network hay policy gây lỗi.

### 8.2. ORA-00257

ORA-00257 thường xuất hiện khi archiver không thể archive redo. Khi đó, database có thể chỉ cho phép kết nối SYSDBA hoặc hạn chế hoạt động của client thông thường.

Không chỉ restart database để xóa lỗi. Restart không tạo thêm dung lượng và không sửa destination lỗi. Khôi phục archive destination/FRA, xử lý file reclaimable và xác nhận ARCn tiếp tục archive được.

### 8.3. ORA-19809 và ORA-19804

ORA-19809 cho biết giới hạn FRA đã bị vượt. ORA-19804 cho biết Oracle không thể reclaim đủ byte cần thiết. Cần xem used/reclaimable theo file type, retention policy, guaranteed restore point và destination capacity.

Nếu physical storage còn chỗ, có thể xem xét tăng DB_RECOVERY_FILE_DEST_SIZE. Nếu storage đã đầy, tăng giới hạn chỉ làm cấu hình vượt quá capacity thực và có thể gây lỗi filesystem/ASM tiếp theo.

## 9. Kiểm tra archive destination và archived log

### 9.1. Destination status

    SELECT
        dest_id,
        status,
        target,
        destination,
        error
    FROM v$archive_dest
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

Trạng thái VALID/ERROR và nội dung ERROR giúp xác định destination nào đang lỗi. Một database có nhiều archive destination; cần biết destination nào bắt buộc theo chính sách và destination nào là optional.

### 9.2. Destination runtime status

    SELECT
        dest_id,
        status,
        type,
        database_mode,
        recovery_mode,
        destination,
        error,
        gap_status
    FROM v$archive_dest_status
    WHERE status <> 'INACTIVE'
    ORDER BY dest_id;

Các cột khả dụng tùy release và quyền. Nếu một cột không tồn tại, xem mô tả view của phiên bản đang chạy và điều chỉnh query. Đặc biệt với Data Guard, xem transport/apply status và gap.

### 9.3. Archived log gần nhất

    SELECT
        thread#,
        sequence#,
        dest_id,
        first_time,
        completion_time,
        archived,
        applied,
        deleted,
        status,
        name
    FROM v$archived_log
    WHERE first_time >= SYSDATE - 1
    ORDER BY completion_time DESC;

Có thể có nhiều record cho cùng thread/sequence do nhiều destination hoặc nhiều bản copy. Không đếm mọi row như số sequence duy nhất. Với standby, cột APPLIED có ý nghĩa trong ngữ cảnh phù hợp và không phải lúc nào cũng phản ánh cùng trạng thái ở primary.

### 9.4. Archive process và alert log

Kiểm tra alert log để tìm lỗi tạo file, permission, disk full, ASM dismount, network error hoặc standby transport. Kiểm tra ARCn có hoạt động và có bị thiếu process/resource hay không. Không chỉ nhìn một query destination rồi kết luận archiving ổn.

## 10. Giải phóng FRA an toàn bằng RMAN

FRA được Oracle quản lý; không xóa file archived log hoặc backup piece trực tiếp bằng rm, del hay công cụ filesystem. Xóa ngoài RMAN có thể làm repository metadata không còn khớp file thực tế và phá vỡ khả năng restore/recovery.

### 10.1. Xem RMAN configuration

Trong RMAN:

    SHOW ALL;

Xem các cấu hình quan trọng:

- Retention policy.
- Archived log deletion policy.
- Control file autobackup.
- Backup optimization.
- Channel/device configuration.
- Recovery window hoặc redundancy.

Không thay đổi retention policy chỉ để giải phóng FRA nếu chưa xác định RPO/RTO và yêu cầu recovery.

### 10.2. CROSSCHECK

CROSSCHECK đối chiếu repository metadata với file backup/archive thực tế:

    CROSSCHECK BACKUP;
    CROSSCHECK ARCHIVELOG ALL;

File không còn truy cập được có thể được đánh dấu EXPIRED. CROSSCHECK không tự xóa file hợp lệ và cũng không phải thao tác xóa file vật lý.

Sau CROSSCHECK, kiểm tra danh sách EXPIRED và nguyên nhân trước khi dùng DELETE EXPIRED.

### 10.3. DELETE EXPIRED và DELETE OBSOLETE khác nhau

- DELETE EXPIRED xóa record repository cho file RMAN đã xác nhận không còn tồn tại.
- DELETE OBSOLETE xóa backup không còn cần theo retention policy; RMAN quản lý việc xóa file tương ứng.

Ví dụ:

    DELETE EXPIRED BACKUP;
    DELETE EXPIRED ARCHIVELOG ALL;

    REPORT OBSOLETE;
    DELETE OBSOLETE;

Luôn chạy REPORT OBSOLETE trước để xem file nào sẽ bị coi là không còn cần thiết. DELETE OBSOLETE phải tuân theo retention policy và recovery requirements đã được phê duyệt.

### 10.4. Backup archived log rồi xóa input

Một quy trình phổ biến là backup archived log và chỉ xóa input sau khi backup thành công:

    BACKUP ARCHIVELOG ALL DELETE INPUT;

Lệnh này cần được sử dụng cùng archive log deletion policy, Data Guard requirements và chính sách backup. Trong môi trường có nhiều archive destination, DELETE INPUT và DELETE ALL INPUT có hành vi khác nhau; đọc RMAN documentation trước khi chọn. Không dùng lệnh này nếu chưa xác nhận standby đã nhận/apply redo theo deletion policy.

### 10.5. Data Guard deletion policy

Nếu database có standby, archived log có thể phải được giữ cho tới khi standby apply redo hoặc tới khi có backup theo chính sách. RMAN có thể cấu hình archived log deletion policy, ví dụ yêu cầu log đã được applied trên tất cả standby cần thiết.

Kiểm tra:

    SHOW ARCHIVELOG DELETION POLICY;

Không hạ deletion policy để xóa log nhanh hơn khi standby đang lag hoặc có gap. Việc đó có thể làm standby không thể catch up nếu redo cần thiết bị xóa khỏi mọi nơi.

### 10.6. Không xóa archived log thủ công

Không dùng thao tác filesystem để xóa file trong FRA. Nếu RMAN không thể reclaim file, điều tra:

- File có còn cần theo retention policy không.
- File có phải archived log chưa backup/chưa apply không.
- Có guaranteed restore point giữ flashback log không.
- Có backup piece obsolete nhưng repository chưa được xử lý không.
- Có file thuộc Data Guard/foreign archive không.
- Destination hoặc ASM disk group có lỗi không.

Nếu cần dọn file, dùng RMAN command theo chính sách và có log/approval.

## 11. Tăng FRA capacity và thay đổi archive destination

### 11.1. Tăng DB_RECOVERY_FILE_DEST_SIZE

Nếu storage vật lý còn đủ dung lượng và FRA cần thêm capacity, DBA có thể tăng giới hạn:

    ALTER SYSTEM SET db_recovery_file_dest_size = 500G
      SCOPE = BOTH;

500G chỉ là ví dụ. Kiểm tra tham số có thể thay đổi online theo release và cấu hình. Xác nhận ASM/filesystem còn đủ chỗ, có headroom cho backup/flashback/archive trong thời gian vận hành và không ảnh hưởng các workload khác.

Tăng FRA size không thay thế việc kiểm tra retention policy và tốc độ tăng archived log. Nếu redo generation liên tục vượt khả năng backup/archive, FRA sẽ đầy lại.

### 11.2. Kiểm tra storage thực tế

Với filesystem, kiểm tra free bytes, inode, mount status, permission và quota. Với ASM, kiểm tra disk group free space, usable_file_mb, redundancy và rebalance. Không chỉ xem DB_RECOVERY_FILE_DEST_SIZE vì đó là giới hạn logic, không phải dung lượng vật lý.

### 11.3. Chuyển archive destination

Nếu archive destination hiện tại bị đầy hoặc không phù hợp, có thể thiết kế destination khác. Thay đổi LOG_ARCHIVE_DEST_n hoặc FRA path cần được DBA review, đặc biệt với Data Guard, RAC và recovery architecture.

Ví dụ cấu hình destination local chỉ minh họa:

    ALTER SYSTEM SET log_archive_dest_1 =
      'LOCATION=/u04/archivelog'
      SCOPE = BOTH;

Không dùng path ví dụ trực tiếp trên production. Kiểm tra path tồn tại, quyền Oracle, mount, retention/backup, destination state và chính sách Data Guard. Một destination mới không có backup/cleanup plan sẽ chỉ chuyển sự cố sang filesystem khác.

## 12. Commit chậm: xử lý ở phía ứng dụng

Nếu log file sync là wait nổi bật, cần xem transaction pattern của ứng dụng.

### 12.1. Tránh commit sau từng hàng nếu không cần

Mẫu gây nhiều commit:

    FOR each row:
        INSERT one row
        COMMIT

Nếu mỗi hàng là một transaction độc lập theo yêu cầu nghiệp vụ thì có thể phải giữ semantics đó. Nhưng nếu các hàng thuộc cùng một batch nguyên tử, commit mỗi row sẽ tạo nhiều commit request và tăng overhead.

Có thể batch nhiều DML trong một transaction:

    BEGIN
      INSERT INTO staging_table ...;
      INSERT INTO target_table ...;
      UPDATE summary_table ...;
      COMMIT;
    END;

Batch size cần cân bằng giữa commit overhead, undo usage, lock duration, restart/retry cost và khả năng rollback. Một transaction quá lớn cũng có thể giữ lock lâu, tạo undo lớn và làm recovery lâu hơn.

### 12.2. Group commit

Oracle có thể gom nhiều commit request gần nhau vào cùng một redo write. Group commit giúp giảm I/O trên mỗi transaction. Tuy nhiên, nếu ứng dụng tạo nhiều commit tuần tự từ một thread, các commit không nhất thiết tận dụng được nhiều group commit.

Tăng concurrency không phải giải pháp tự động: nó có thể tăng group commit nhưng cũng tăng contention và redo generation. Hãy benchmark theo workload thật.

### 12.3. Kiểm tra transaction boundary

Một service có thể mở transaction trước khi gọi external API, chờ response, rồi mới commit. Điều này kéo dài thời gian giữ connection/lock và làm tải concurrency tăng.

Tách transaction ngắn, xác định rõ atomicity và dùng outbox/saga cho tích hợp phân tán nếu phù hợp. Không thay đổi commit scope chỉ để giảm wait mà làm mất tính nhất quán nghiệp vụ.

### 12.4. Kiểm tra ORM và auto-commit

Với Spring/JPA, xem transaction manager, @Transactional boundary, flush mode và batch behavior. Hibernate có thể flush DML trước commit; thời gian commit quan sát ở Java có thể gồm flush, constraint checking, trigger, network round-trip và commit wait.

Phân biệt thời gian:
- Trước khi gọi commit.
- Flush SQL.
- Thời gian database xử lý commit.
- Thời gian JDBC round-trip.
- Thời gian client nhận response.

Không gán toàn bộ thời gian method commit cho log file sync nếu chưa có trace/metric tách giai đoạn.

## 13. Commit chậm: xử lý ở storage và database

### 13.1. Đo latency redo storage

Redo log write là synchronous I/O quan trọng. Làm việc với storage team để đo latency theo đúng volume/disk group chứa redo, tại thời điểm commit chậm. Kiểm tra cả read/write path nếu thiết bị chia sẻ tài nguyên.

Các điểm cần xem:

- Average và tail write latency.
- Queue depth.
- IOPS và throughput.
- Storage cache và battery-backed/write-through policy.
- Multipath path state.
- Hypervisor/virtual disk latency.
- ASM disk group load.
- Cạnh tranh với datafile, archive và backup.

Đừng chuyển redo log sang một volume khác chỉ dựa trên giả định volume đó nhanh hơn. Cần xác nhận latency, redundancy và failure domain.

### 13.2. Tách redo log khỏi workload gây tranh chấp

Nếu redo log, datafile và RMAN backup cùng dùng storage pool bị bão hòa, có thể xuất hiện cạnh tranh I/O. Thiết kế storage có thể tách redo log khỏi workload tuần tự lớn, tùy kiến trúc và khả năng của platform.

Multiplex redo members để bảo vệ lỗi file; không đặt tất cả member cùng một storage failure domain. Thiết kế phải cân bằng durability, latency và availability.

### 13.3. Kiểm tra LGWR CPU/scheduling

Nếu log file sync cao nhưng log file parallel write không cao tương ứng, xem CPU scheduling, LGWR process, OS run queue, virtualization steal time và các background process. Một LGWR bị trì hoãn chạy có thể làm foreground chờ dù storage hoàn tất ghi nhanh khi I/O thực sự được gửi.

### 13.4. Không tăng LOG_BUFFER một cách tùy tiện

LOG_BUFFER là dung lượng redo log buffer. Tăng nó có thể giúp một số workload cụ thể nhưng không sửa được storage redo write chậm hoặc commit I/O latency cao. Trước khi thay đổi, cần bằng chứng log buffer space hoặc redo allocation pressure và kiểm tra tài liệu Oracle.

### 13.5. Không dùng COMMIT NOWAIT như cách chữa cháy

Oracle hỗ trợ các tùy chọn COMMIT WRITE liên quan WAIT/NOWAIT và IMMEDIATE/BATCH. Với WAIT, foreground đợi redo được ghi theo semantics durable. Với NOWAIT, ứng dụng có thể nhận xác nhận commit trước khi redo được ghi bền vững; nếu instance/system gặp sự cố trong khoảng đó, transaction đã được client coi là thành công có thể bị mất.

NOWAIT làm thay đổi durability contract và có thể gây sai lệch nghiêm trọng giữa client với database. Chỉ cân nhắc khi nghiệp vụ chấp nhận rõ ràng rủi ro đó và có thiết kế được phê duyệt. Không dùng để che lỗi storage hoặc LGWR.

BATCH cho phép trì hoãn/nhóm redo writes theo semantics được hỗ trợ; nếu dùng WAIT, foreground vẫn đợi durability theo commit mode. Mặc định và hành vi chi tiết phụ thuộc phiên bản/cấu hình; kiểm tra tài liệu đúng release.

## 14. Data Guard synchronous commit và độ trễ mạng

Trong Data Guard synchronous transport, commit path có thể phụ thuộc việc redo được chuyển tới standby và được xác nhận theo protection mode/transport attributes. Vì vậy, commit latency có thể tăng do:

- Network round-trip giữa primary và standby.
- Latency ghi redo ở standby.
- Standby overloaded hoặc redo transport lag.
- Packet loss, retransmission hoặc network congestion.
- Standby destination hoặc service gặp sự cố.

Nếu dùng SYNC/AFFIRM, acknowledgment có thể chờ standby ghi redo theo semantics tương ứng. NOAFFIRM có hành vi acknowledgment khác và thay đổi durability guarantee. Không đổi SYNC thành ASYNC hoặc AFFIRM thành NOAFFIRM chỉ để giảm commit latency nếu chưa đánh giá protection mode, RPO và chính sách HA.

Kiểm tra Data Guard:

    SELECT
        dest_id,
        status,
        target,
        destination,
        error,
        gap_status
    FROM v$archive_dest_status
    WHERE target = 'STANDBY'
    ORDER BY dest_id;

Có thể xem thống kê Data Guard:

    SELECT
        name,
        value,
        unit,
        time_computed,
        datum_time
    FROM v$dataguard_stats
    ORDER BY name;

Tên cột/view và quyền phụ thuộc release/role. Kết hợp transport/apply lag, alert log, network metrics và wait events phù hợp để xác định commit acknowledgment bị kéo dài ở đâu.

## 15. Các tình huống sự cố mẫu

### 15.1. Ứng dụng commit mất 2 giây, log file sync cao

Điều tra:

1. Xác định service/module và session có log file sync.
2. So sánh average/histogram của log file sync và log file parallel write.
3. Đo redo storage latency tại cùng thời điểm.
4. Xem commit rate, redo generation và transaction duration.
5. Kiểm tra Data Guard synchronous transport nếu có.
6. Kiểm tra LGWR CPU/scheduling.

Nếu log file parallel write cao, ưu tiên điều tra storage. Nếu parallel write thấp nhưng log file sync cao, xem scheduling, group commit pattern, CPU và remote acknowledgment.

### 15.2. Log switch mỗi vài chục giây

Điều tra:

1. Tính redo generation rate theo thời gian.
2. Xem size và số group theo từng thread.
3. Xem switch history theo giờ.
4. Kiểm tra archive throughput và checkpoint completion.
5. Xem wait event checkpoint incomplete hoặc archiving needed.

Nếu switch thường xuyên nhưng không có foreground wait và archive/checkpoint theo kịp, có thể chỉ là thiết kế cần xem lại. Nếu switch gây wait, xác định checkpoint hay archive là nút thắt trước khi tăng size/group.

### 15.3. ORA-00257 và FRA gần 100%

Điều tra:

1. Query V$RECOVERY_FILE_DEST.
2. Query V$FLASH_RECOVERY_AREA_USAGE.
3. Kiểm tra archive destination status/error.
4. Kiểm tra RMAN retention/deletion policy.
5. Kiểm tra archive backup và Data Guard applied status.
6. Kiểm tra guaranteed restore point và flashback log usage.
7. Kiểm tra physical storage capacity.

Khôi phục archive destination, thực hiện backup/cleanup qua RMAN theo policy hoặc tăng FRA limit nếu storage thật sự còn capacity. Sau đó xác nhận ARCn archive được sequence mới và log group được tái sử dụng.

### 15.4. log file switch (checkpoint incomplete)

Điều tra datafile I/O, DBWR, redo generation burst, log size và group count. Tăng log size/group chỉ sau khi xác định checkpoint không theo kịp và storage datafile có capacity phù hợp.

### 15.5. Archive destination từ xa lỗi

Nếu destination Data Guard hoặc remote archive bị lỗi, kiểm tra network, listener/service, credential, destination state, standby role và transport gap. Không xóa archive log cần cho standby để giải phóng chỗ trước khi có kế hoạch khôi phục transport/apply.

## 16. Quy trình ứng phó sự cố theo thứ tự

Khi production bị commit chậm hoặc archive/FRA nghẽn, dùng trình tự dưới đây để khoanh vùng.

### Bước 1: Xác định phạm vi

- Một service hay mọi service?
- Một database instance hay toàn cluster?
- Bắt đầu từ thời điểm nào?
- Có deploy, batch, backup, ETL hoặc storage change gần đó không?
- Database có ARCHIVELOG và Data Guard không?
- Có CDB/PDB hoặc RAC không?

### Bước 2: Kiểm tra wait event

Lấy snapshot V$SESSION và V$SYSTEM_EVENT. Xác định foreground chờ log file sync, log switch, log buffer space hay wait khác.

### Bước 3: Kiểm tra redo log groups

Xem V$LOG và V$LOGFILE. Xác định group CURRENT, ACTIVE, INACTIVE, archive status và member path. Xem switch frequency theo thread.

### Bước 4: Kiểm tra archive destination

Xem V$ARCHIVE_DEST, V$ARCHIVE_DEST_STATUS, archived log gần nhất, alert log và ARCn errors. Nếu destination lỗi, sửa khả năng ghi trước khi tiếp tục.

### Bước 5: Kiểm tra FRA

Xem limit, used, reclaimable và usage theo file type. Xác định archive, backup hay flashback log đang chiếm dung lượng.

### Bước 6: Chọn remediation đúng nguyên nhân

- Redo storage chậm: xử lý I/O path/latency.
- Commit quá nhiều: tối ưu transaction boundary/batch theo semantics.
- Checkpoint incomplete: kiểm tra DBWR/datafile I/O, log size/group count.
- Archiving needed: sửa destination/FRA/ARCn/Data Guard.
- FRA đầy: backup/cleanup theo RMAN policy hoặc tăng capacity vật lý hợp lệ.
- Data Guard synchronous latency: xử lý network/standby; giữ protection semantics theo yêu cầu.
- Redo buffer space: xử lý LGWR throughput và redo burst.

### Bước 7: Xác nhận sau sửa

- Log switch tiếp tục diễn ra bình thường.
- Archived log mới được tạo.
- FRA used/reclaimable ổn định.
- Wait event giảm trong cùng workload.
- Commit latency và application error rate trở về baseline.
- Data Guard transport/apply không tạo gap ngoài dự kiến.
- Backup/recovery policy vẫn được đáp ứng.

## 17. Những thao tác cần tránh

### 17.1. Xóa file archived log bằng hệ điều hành

Xóa file trong FRA bằng rm/del có thể làm RMAN repository không khớp file thực tế và phá vỡ khả năng restore. Dùng RMAN để crosscheck, backup, delete expired/obsolete hoặc xóa archive theo deletion policy.

### 17.2. Tăng FRA limit vượt physical capacity

DB_RECOVERY_FILE_DEST_SIZE chỉ là giới hạn Oracle. Nếu filesystem hoặc ASM disk group không có dung lượng, tăng limit có thể khiến lỗi storage xuất hiện ở tầng thấp hơn.

### 17.3. Thêm redo log group mà không xử lý archive

Thêm group có thể tạo thêm thời gian nhưng không sửa destination đầy hoặc ARCn lỗi. Khi mọi group lần lượt đầy, database vẫn bị chặn.

### 17.4. Force log switch liên tục

ALTER SYSTEM SWITCH LOGFILE hoặc ARCHIVE LOG CURRENT có thể hữu ích cho một số thao tác DBA/backup, nhưng chạy lặp lại trong production sẽ tạo thêm archive/checkpoint work và có thể làm tình hình xấu hơn. Chỉ dùng khi có mục đích rõ ràng.

### 17.5. Tắt ARCHIVELOG hoặc giảm protection mode để hết lỗi

Tắt ARCHIVELOG làm thay đổi khả năng media recovery và backup strategy. Thay đổi Data Guard protection/transport mode làm thay đổi durability/availability guarantees. Đây là thay đổi kiến trúc và recovery objective, không phải biện pháp dọn FRA thông thường.

### 17.6. Tăng LOG_BUFFER hoặc pool size theo cảm tính

Các thay đổi này không trực tiếp sửa redo storage latency hoặc archive destination failure. Cần đo bottleneck trước khi thay tham số.

## 18. Checklist vận hành

### Khi commit chậm

- Xác định session/service/module đang commit.
- Kiểm tra log file sync và log file parallel write.
- So sánh delta wait, histogram và redo write stats.
- Đo latency storage của redo log.
- Kiểm tra LGWR CPU/scheduling.
- Kiểm tra commit frequency và transaction boundary.
- Kiểm tra synchronous Data Guard transport.
- Không đổi durability mode nếu chưa đánh giá rủi ro.

### Khi log switch chậm

- Xem V$LOG và V$LOGFILE.
- Đo switch frequency theo thread.
- Phân biệt checkpoint incomplete với archiving needed.
- Kiểm tra DBWR/datafile I/O.
- Kiểm tra archive destination và ARCn.
- Tính redo generation rate trước khi tăng log size.
- Bảo đảm đủ group để checkpoint/archive theo kịp.
- Giữ multiplex member trên failure domain phù hợp.

### Khi FRA đầy

- Xem DB_RECOVERY_FILE_DEST và size.
- Xem used/reclaimable trong V$RECOVERY_FILE_DEST.
- Phân loại file qua V$FLASH_RECOVERY_AREA_USAGE.
- Kiểm tra archive destination error.
- Xem RMAN retention/deletion policy.
- Kiểm tra backup và Data Guard apply status.
- Kiểm tra guaranteed restore point/flashback log.
- Chỉ dọn bằng RMAN theo policy.
- Chỉ tăng FRA size khi storage vật lý còn đủ.

### Sau khi khôi phục

- Xác nhận archive log mới được tạo và archive destination VALID.
- Xác nhận log group có thể chuyển và tái sử dụng.
- Kiểm tra FRA không tiếp tục tăng không kiểm soát.
- Kiểm tra commit latency và wait events theo workload.
- Kiểm tra Data Guard transport/apply và backup job.
- Lưu alert log, RMAN output và số liệu trước/sau sự cố.

## 19. Nguyên tắc cần nhớ

- COMMIT thường chờ LGWR ghi redo; log file sync là wait foreground quan trọng cần kiểm tra.
- log file parallel write giúp đánh giá thời gian LGWR ghi redo xuống storage.
- log buffer space cho thấy redo buffer không được giải phóng đủ nhanh.
- log file switch (checkpoint incomplete) liên quan checkpoint/DBWR; log file switch (archiving needed) liên quan archive destination.
- Log switch là bình thường; switch quá dày hoặc group không thể tái sử dụng mới là vấn đề.
- Kích thước group quyết định lượng redo mỗi group; số group tạo thêm thời gian trước khi group cần dùng lại; member bổ sung bảo vệ redundancy chứ không tăng capacity.
- FRA chứa nhiều loại file recovery; xác định đúng loại file chiếm chỗ trước khi dọn.
- Dùng RMAN và deletion policy để quản lý archived log/backup; không xóa file recovery trực tiếp bằng hệ điều hành.
- Guaranteed restore point có thể giữ flashback log; chỉ drop khi đã xác nhận yêu cầu recovery.
- Tăng FRA limit chỉ khi filesystem/ASM còn capacity vật lý.
- Data Guard SYNC/AFFIRM có thể ảnh hưởng commit acknowledgment; không hạ protection mode chỉ để giảm latency.
- Không dùng COMMIT NOWAIT, tắt ARCHIVELOG hoặc force log switch như giải pháp chữa cháy.
- Đo wait, redo, archive, FRA và storage theo cùng một khoảng thời gian để tìm đúng nút thắt.

Commit, redo log switch và FRA là các mắt xích trong cùng chuỗi bảo vệ dữ liệu. Chẩn đoán hiệu quả cần nối wait event ở foreground với hoạt động LGWR, checkpoint, ARCn, archive destination và storage. Khi xác định đúng điểm nghẽn, DBA có thể khôi phục commit latency và khả năng archive mà vẫn giữ nguyên durability, backup và recovery requirements của hệ thống.
