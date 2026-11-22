# Nhận diện nghẽn CPU, I/O, redo, undo và temporary space trong Oracle Database

Một hệ thống Oracle chậm không có nghĩa database server thiếu CPU hoặc storage chậm. Để tìm đúng điểm nghẽn, cần xác định session đang dành thời gian ở đâu, SQL nào tạo ra tải, operation nào tiêu thụ tài nguyên và tài nguyên đó có thực sự bão hòa hay không.

Có năm nhóm tài nguyên thường cần điều tra:

- **CPU:** thời gian xử lý SQL/PLSQL, parse, join, sort, tính toán và parallel execution.
- **I/O:** đọc/ghi datafile, index, tempfile và redo log trên storage.
- **Redo:** ghi lại thay đổi để phục hồi database và xác nhận COMMIT.
- **Undo:** giữ thông tin trước thay đổi để rollback và consistent read.
- **Temporary space (TEMP):** vùng lưu trung gian khi sort, hash, analytic operation hoặc một số thao tác LOB không thể xử lý hoàn toàn trong bộ nhớ.

Các nhóm này liên quan với nhau. Ví dụ, một câu SQL có thể dùng CPU cao để xử lý hàng triệu bản ghi, spill sort ra TEMP, tạo I/O lớn và đồng thời làm tăng redo/undo nếu nó thực hiện DML. Vì vậy, hãy đo workload theo cùng một khoảng thời gian, xác định nơi session tiêu tốn thời gian rồi mới chọn biện pháp.

Tài liệu lấy Oracle Database 19c làm mốc. Một số view cần quyền đọc dictionary; AWR, ASH và ADDM thuộc phạm vi Oracle Diagnostics Pack theo điều khoản cấp phép tương ứng. Hãy xác nhận license của môi trường trước khi sử dụng các tính năng thuộc pack.

## 1. Hiểu thế nào là bottleneck?

### 1.1. Tải cao chưa chắc là nghẽn

Một hệ thống có thể sử dụng CPU 80% trong giờ cao điểm nhưng vẫn đáp ứng SLA. Ngược lại, CPU chỉ 25% nhưng ứng dụng vẫn chậm vì session đang đợi I/O, redo log, lock hoặc một dịch vụ bên ngoài.

**Bottleneck** là tài nguyên hoặc bước xử lý đang giới hạn throughput hay kéo dài response time của workload cần phục vụ. Muốn kết luận cần đối chiếu ít nhất:

- Mức sử dụng tài nguyên.
- Thời gian chờ hoặc thời gian xử lý.
- Số lượng công việc hoàn thành.
- Latency quan sát từ ứng dụng.
- Thay đổi so với baseline cùng loại workload.

Không nên kết luận chỉ từ một phần trăm CPU, một wait event đứng đầu hoặc một lần xem TEMP.

### 1.2. DB time và DB CPU

Oracle dùng các chỉ số time model để phân biệt thời gian database xử lý và thời gian CPU.

- **DB time:** tổng thời gian foreground session dành cho công việc database, gồm CPU và non-idle wait time.
- **DB CPU:** phần thời gian foreground session thực sự chạy trên CPU.

DB time là tổng qua các session, vì vậy có thể lớn hơn thời gian đồng hồ thực tế khi nhiều session hoạt động đồng thời. DB time tăng có thể do CPU, I/O, commit, lock hoặc các loại wait khác.

Có thể xem số liệu tích lũy trong instance:

~~~sql
SELECT stat_name,
       value / 1000000 AS seconds
FROM   v$sys_time_model
WHERE  stat_name IN ('DB time', 'DB CPU')
ORDER  BY stat_name;
~~~

Giá trị time model được lưu theo microsecond. Đây là số liệu tích lũy từ khi instance khởi động hoặc reset counter; muốn biết tải trong một khoảng thời gian, lấy hai snapshot rồi tính delta.

### 1.3. Wait event không tự động là bottleneck

Một wait event có tổng thời gian lớn có thể chỉ phản ánh workload có nhiều request. Cần xem:
- Số lần wait.
- Tổng thời gian wait.
- Thời gian trung bình mỗi wait.
- Số session đồng thời.
- Tác động đến response time.
- Wait có thuộc idle class hay không.

Một session chờ một lần 10 giây khác với 10.000 session mỗi session chờ 1 millisecond. Cả hai có thể tạo tổng thời gian lớn nhưng nguyên nhân và cách xử lý khác nhau.

### 1.4. Một quy trình điều tra có thể lặp lại

~~~text
Xác định triệu chứng và khoảng thời gian
                 |
                 v
Đo DB time, DB CPU và workload
                 |
                 v
Session đang chạy CPU hay đang WAIT?
          /                    \
       CPU                      WAIT
        |                         |
        v                         v
Top SQL, parse,          Phân loại wait event
plan, parallelism        I/O / redo / undo / TEMP
        |                         |
        +------------+------------+
                     |
                     v
Đối chiếu OS, storage, PGA/TEMP,
redo/undo và số liệu ứng dụng
                     |
                     v
Xác định nguyên nhân có bằng chứng
                     |
                     v
Thử một thay đổi có kiểm soát
                     |
                     v
Đo lại cùng workload và so với baseline
~~~

## 2. Thu thập baseline trước khi điều tra

### 2.1. Ghi lại triệu chứng

Trước khi chạy truy vấn chẩn đoán, ghi lại:
- Ứng dụng hoặc service bị chậm.
- SQL/API bị ảnh hưởng.
- Thời điểm bắt đầu và kết thúc.
- Số request, số transaction hoặc batch size.
- Latency p50/p95/p99 nếu ứng dụng có.
- Số session và mức concurrency.
- Có deploy, thay đổi statistics, index, tham số hoặc batch job gần thời điểm đó không.

Nếu không biết workload đã thay đổi hay chưa, rất dễ quy lỗi cho database dù nguyên nhân là request tăng gấp nhiều lần.

### 2.2. Lấy delta thay vì chỉ nhìn số tích lũy

Nhiều cột trong V$SYSSTAT, V$SYSTEM_EVENT và V$SQL là counter tích lũy. Ví dụ TOTAL_WAITS hoặc TIME_WAITED_MICRO tăng từ khi instance khởi động.

Để đo khoảng 5 phút:
1. Ghi snapshot lúc bắt đầu.
2. Chờ workload tiếp tục trong 5 phút.
3. Ghi snapshot thứ hai.
4. Tính hiệu số.
5. Chia cho thời gian hoặc số transaction để có rate/average phù hợp.

Không so sánh counter từ hai instance khác nhau hoặc sau khi counter reset mà không chuẩn hóa.

### 2.3. Chụp các chỉ số cơ bản

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'user commits',
           'user rollbacks',
           'redo size',
           'redo writes',
           'redo buffer allocation retries',
           'parse count (total)',
           'parse count (hard)',
           'CPU used by this session',
           'session logical reads',
           'physical reads',
           'physical writes'
       )
ORDER  BY name;
~~~

Các tên statistic có thể khác theo release hoặc ngữ cảnh. Đây là snapshot tích lũy, nên lưu lại theo thời điểm để tính delta.

### 2.4. Xem session đang hoạt động

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER  BY wait_class, seconds_in_wait DESC;
~~~

ACTIVE không đồng nghĩa session đang chạy CPU. Session có STATUS ACTIVE có thể đang chờ một event. Khi STATE là WAITING, EVENT và WAIT_CLASS giúp xác định nó đang đợi gì; khi session chạy CPU, event có thể không mô tả một wait hiện tại.

Để điều tra một thời điểm cụ thể, cần lấy snapshot lặp lại thay vì chỉ xem một lần.

### 2.5. Xác định quyền và công cụ được phép

Các view V$ thường cần quyền SELECT_CATALOG_ROLE hoặc quyền đọc trực tiếp phù hợp do DBA cấp. Chỉ cấp quyền tối thiểu cho tài khoản giám sát.

AWR/ASH/ADDM và một số tính năng giám sát SQL có điều kiện license riêng. Nếu chưa có license phù hợp, dùng các V$ view, DBMS_XPLAN và công cụ OS được cấp phép; không mặc định mọi tính năng chẩn đoán đều được bao gồm.

## 3. Nhận diện nghẽn CPU

### 3.1. Dấu hiệu thường gặp

CPU có thể là bottleneck khi đồng thời thấy:
- Host CPU bão hòa trong khoảng thời gian sự cố.
- Run queue cao hoặc process runnable phải chờ CPU.
- DB CPU tăng mạnh cùng với latency/throughput xấu đi.
- Nhiều foreground/background process tiêu thụ CPU.
- SQL có CPU_TIME cao, buffer gets lớn hoặc parse CPU cao.
- Các wait event không phải CPU không giải thích được phần lớn DB time.

CPU utilization cao đơn lẻ chưa đủ. Cần kiểm tra số CPU được database nhìn thấy, CPU quota/VM limit và tải của process khác trên host.

### 3.2. DB CPU và DB time

~~~sql
SELECT stat_name,
       ROUND(value / 1000000, 2) AS seconds
FROM   v$sys_time_model
WHERE  stat_name IN ('DB time', 'DB CPU');
~~~

Lấy delta hai lần để xem DB CPU/DB time tăng bao nhiêu trong khoảng đo. Nếu DB CPU chiếm phần lớn DB time và OS CPU bão hòa, CPU contention là giả thuyết mạnh.

Nếu DB time cao nhưng DB CPU thấp, hãy tập trung vào wait events. Nếu DB CPU cao nhưng host còn nhiều CPU headroom, có thể SQL đang tốn CPU nhưng chưa phải bottleneck hệ thống.

### 3.3. Xem CPU và OS statistics

~~~sql
SELECT stat_name,
       value
FROM   v$osstat
WHERE  stat_name IN (
           'NUM_CPUS',
           'NUM_CPU_CORES',
           'BUSY_TIME',
           'IDLE_TIME',
           'USER_TIME',
           'SYS_TIME',
           'IOWAIT_TIME',
           'LOAD'
       )
ORDER  BY stat_name;
~~~

Tên statistic và đơn vị phụ thuộc nền tảng. Dùng Oracle Database Reference để xác nhận đơn vị, đặc biệt khi tính phần trăm từ counter.

Đối chiếu với hệ điều hành:
- Linux: top, vmstat, mpstat, sar.
- Windows: Performance Monitor, CPU utilization, processor queue, process CPU.
- VM/container: kiểm tra vCPU quota, CPU limit và host contention.

### 3.4. Tìm SQL tiêu thụ CPU

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

CPU_TIME và ELAPSED_TIME trong V$SQL là số tích lũy theo cursor. SQL có nhiều execution có thể đứng đầu vì tổng công việc lớn. Để đánh giá một execution, chia delta CPU/elapsed cho delta executions trong cùng khoảng đo; không chỉ nhìn tổng.

Có thể bổ sung CPU mỗi execution:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_cpu_ms,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_elapsed_ms,
       buffer_gets,
       rows_processed
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time / NULLIF(executions, 0) DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Đây là trung bình tích lũy từ lúc cursor được nạp, không nhất thiết phản ánh đúng giai đoạn sự cố. Với workload thay đổi, dùng snapshot delta hoặc công cụ giám sát theo thời gian.

### 3.5. CPU do parse

Hard parse và parse liên tục có thể tiêu thụ CPU. Xem:
- parse count (total).
- parse count (hard).
- parse time cpu.
- executions và parse_calls trong V$SQL.
- Số child cursor và version_count.

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'parse count (total)',
           'parse count (hard)',
           'parse time cpu'
       );
~~~

Tỷ lệ hard parse cao trong workload có SQL lặp thường gợi ý ứng dụng ghép literal, không tái sử dụng prepared statement hoặc có nhiều child cursor không tương thích. Không chỉ nhìn tỷ lệ; hãy so với số execution và tải thực tế.

### 3.6. CPU do SQL plan kém

SQL có thể tiêu thụ CPU cao do:
- Full scan quá nhiều dữ liệu.
- Join tạo số hàng trung gian lớn.
- Predicate không sargable hoặc implicit conversion.
- Sort/hash trên tập dữ liệu lớn.
- PL/SQL gọi SQL lặp lại theo từng hàng.
- Cardinality estimate sai khiến optimizer chọn join method không phù hợp.
- Parallel execution tạo nhiều worker và tăng tổng CPU.

Dùng DBMS_XPLAN.DISPLAY_CURSOR để xem plan và runtime statistics. Tập trung vào A-Rows, E-Rows, Starts, Buffers và operation có lượng hàng lớn.

### 3.7. CPU và parallel execution

Parallel query có thể giảm elapsed time cho tác vụ lớn bằng cách dùng nhiều CPU, nhưng tổng CPU consumption có thể tăng. Nếu nhiều câu SQL song song cùng chạy, hệ thống có thể bị oversubscribe.

Kiểm tra:
- Degree of Parallelism thực tế.
- Số PX server đang hoạt động.
- Queue và wait liên quan parallel execution.
- CPU của host và database.
- Throughput tổng, không chỉ thời gian một query.

Không tăng DOP chỉ vì một truy vấn chạy chậm. Tăng parallelism có thể làm workload OLTP khác chậm hơn.

### 3.8. Biện pháp xử lý CPU

Ưu tiên theo bằng chứng:
1. Tối ưu SQL tiêu thụ CPU lớn nhất.
2. Giảm số hàng và cột không cần xử lý.
3. Sửa join cardinality, predicate và datatype.
4. Giảm hard parse bằng bind variables và statement reuse.
5. Kiểm tra PL/SQL row-by-row và thay bằng xử lý theo tập hợp khi phù hợp.
6. Điều chỉnh parallelism theo workload.
7. Chỉ tăng CPU capacity sau khi xác định tải hợp lệ đã vượt năng lực hiện tại.

## 4. Nhận diện nghẽn I/O

### 4.1. Phân biệt các loại I/O

Oracle đọc/ghi nhiều loại file:
- Datafile chứa table/index segments.
- Tempfile chứa temporary segments khi cần.
- Online redo log nhận redo records.
- Archive log là bản sao redo phục vụ recovery/standby.

Một wait event chỉ ra loại thao tác đang chờ, nhưng không tự nói storage có lỗi. Phải đối chiếu latency, throughput, queue và thiết bị vật lý.

### 4.2. Một số wait event thường gặp

| Wait event | Ý nghĩa thường gặp | Hướng điều tra |
| --- | --- | --- |
| db file sequential read | Đọc một block, thường gặp trong index lookup hoặc table access theo ROWID | Index access, random I/O, cache hit, storage latency |
| db file scattered read | Đọc nhiều block, thường gặp trong full scan hoặc multiblock read | Scan volume, segment size, multiblock throughput |
| direct path read | Đọc trực tiếp vào PGA, thường gặp với scan lớn/parallel | Data volume, storage throughput, parallelism |
| direct path read temp | Đọc dữ liệu trung gian từ TEMP | Sort/hash spill, PGA, tempfile latency |
| direct path write temp | Ghi dữ liệu trung gian ra TEMP | Workarea spill, volume, tempfile throughput |
| log file parallel write | LGWR ghi redo log members | Redo storage latency, log configuration |
| control file sequential read | Đọc control file block | Control file I/O, workload và storage |
| db file parallel read | Nhiều block được đọc trong một thao tác | Batch/index access, storage response |

Tên event có thể thay đổi theo loại operation, release và nền tảng. Hãy xác nhận ý nghĩa theo Oracle Database Reference.

### 4.3. db file sequential read không mặc định là lỗi

Index range scan có thể tạo nhiều single-block reads và là access path hoàn toàn hợp lý. Nếu buffer cache đã có block, không cần physical read.

Cần xem:
- Số lần wait và tổng thời gian.
- Average wait time.
- Physical reads so với logical reads.
- Số block được truy cập.
- SQL_ID và plan operation liên quan.
- Storage latency tại cùng thời điểm.

Nếu SQL thực hiện hàng triệu index lookup và mỗi lần đọc chỉ vài millisecond, tổng elapsed có thể lớn dù storage từng request không bất thường.

### 4.4. db file scattered read và full scan

Full table scan thường dùng multiblock read. Đây không tự động là xấu: scan bảng lớn tuần tự có thể hiệu quả hơn hàng triệu index lookup ngẫu nhiên.

Hãy kiểm tra:
- Có predicate chọn lọc cao nhưng vẫn scan toàn bảng không?
- Có partition pruning không?
- Segment có lớn bất thường không?
- Scan có phải tác vụ báo cáo/batch được mong đợi không?
- Storage throughput có đủ không?
- Có thể giảm dữ liệu hoặc chỉ đọc cột cần thiết không?

### 4.5. Đọc I/O wait từ instance

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(
           time_waited_micro / NULLIF(total_waits, 0) / 1000,
           3
       ) AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class = 'User I/O'
ORDER  BY time_waited_micro DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SYSTEM_EVENT là counter tích lũy. Lấy delta trong khoảng sự cố để tránh nhầm event lâu đời với bottleneck hiện tại. Một số event I/O thuộc wait class khác tùy operation; xem toàn bộ event liên quan thay vì chỉ lọc một class.

### 4.6. Đối chiếu với hệ điều hành/storage

Trên Linux, có thể dùng:
- iostat -x: utilization, await, queue và throughput theo thiết bị.
- vmstat: runnable processes, blocked processes, swap và CPU.
- sar: xu hướng CPU/I/O theo thời gian.
- multipath hoặc công cụ SAN/cloud provider để kiểm tra path và volume.

Trên Windows, dùng Performance Monitor để xem:
- Physical Disk: Avg. Disk sec/Read và Avg. Disk sec/Write.
- Disk Reads/sec, Writes/sec, Bytes/sec.
- Current Disk Queue Length.
- CPU, memory và paging.

Tên counter và cách diễn giải tùy nền tảng. Đối chiếu đúng volume chứa datafile, tempfile hoặc redo log; không lấy một ổ đĩa không liên quan làm bằng chứng.

### 4.7. I/O latency, IOPS và throughput

Ba khái niệm cần phân biệt:
- **Latency:** thời gian hoàn tất một yêu cầu I/O.
- **IOPS:** số yêu cầu I/O mỗi giây.
- **Throughput:** lượng byte đọc/ghi mỗi giây.

Một volume có throughput cao nhưng latency random read vẫn lớn. Một workload tuần tự có thể đạt throughput tốt với IOPS thấp hơn. Xem cả kích thước I/O và pattern truy cập.

### 4.8. Biện pháp xử lý I/O

- Tối ưu SQL và giảm block cần đọc.
- Kiểm tra index, partition pruning và clustering factor.
- Tránh quét lại cùng dữ liệu do nested loop/subquery không phù hợp.
- Tách workload batch và OLTP nếu chúng tranh chấp storage.
- Đánh giá buffer cache dựa trên workload, không chỉ tăng SGA theo cảm giác.
- Kiểm tra cấu hình storage, queue depth, multipath và latency của nhà cung cấp.
- Không đặt redo/data/temp vào storage khác nhau chỉ vì tên gọi; cần đo workload và đặc tính thiết bị trước.

## 5. Nhận diện nghẽn REDO và COMMIT

### 5.1. Redo dùng để làm gì?

Redo ghi lại các thay đổi cần thiết để Oracle phục hồi database sau sự cố. Khi transaction thay đổi block, Oracle tạo redo records. LGWR ghi redo buffer ra online redo log theo cơ chế của database.

Redo khác undo:
- Redo hỗ trợ roll-forward/recovery.
- Undo lưu thông tin trước thay đổi để rollback và consistent read.

Một transaction có thể tạo cả redo và undo.

### 5.2. log file sync

Foreground session thường đợi event log file sync khi COMMIT hoặc một số thao tác cần xác nhận redo đã được LGWR ghi tới vị trí cần thiết.

Nếu log file sync cao, điều tra:
- Ứng dụng commit quá thường xuyên.
- Mỗi transaction quá nhỏ nhưng số commit lớn.
- LGWR bị chậm do redo storage.
- CPU scheduling hoặc process contention.
- RAC/standby/commit configuration làm tăng độ trễ xác nhận.
- Có nhiều session cùng phát sinh commit đồng thời.

Không kết luận log file sync cao đồng nghĩa redo log disk chậm. Hãy đối chiếu với log file parallel write và OS storage latency.

### 5.3. log file parallel write

Đây là wait của LGWR khi ghi redo log files. Nếu thời gian ghi cao trong cùng khoảng log file sync cao, redo storage là hướng điều tra đáng chú ý.

Kiểm tra:
- Latency của thiết bị redo.
- Số redo log members và vị trí lưu.
- I/O contention từ data/temp/backup.
- Storage cache/persistence policy.
- Network/storage path nếu dùng ASM hoặc shared storage.

### 5.4. log buffer space

Foreground session có thể đợi log buffer space khi cần cấp chỗ trong redo log buffer nhưng LGWR chưa giải phóng đủ buffer.

Nguyên nhân có thể:
- LGWR không ghi kịp redo.
- Redo generation tăng đột biến.
- Storage latency cao.
- Log buffer pressure hoặc workload đặc biệt.

Kiểm tra statistic redo buffer allocation retries, redo size, log writes và các wait event cùng thời điểm. Không tăng LOG_BUFFER như phản xạ đầu tiên; xác định liệu nguyên nhân là LGWR/storage hay redo generation.

### 5.5. log file switch waits

Một số wait event liên quan chuyển redo log:
- log file switch (checkpoint incomplete): cần checkpoint hoàn tất trước khi reuse log group.
- log file switch (archiving needed): cần archive log trước khi reuse.
- log file switch completion: session chờ hoàn tất log switch.

Có thể cần:
- Kiểm tra kích thước và số lượng redo log groups.
- Kiểm tra tần suất log switch.
- Kiểm tra checkpoint và DBWR.
- Kiểm tra ARCH process và archive destination.
- Kiểm tra archive destination có đầy hoặc chậm không.

Không tăng redo log size một cách mù quáng. Hãy dựa trên redo generation rate, thời gian switch, checkpoint và yêu cầu recovery.

### 5.6. Xem redo statistics

~~~sql
SELECT name,
       value
FROM   v$sysstat
WHERE  name IN (
           'redo size',
           'redo writes',
           'redo entries',
           'redo buffer allocation retries',
           'user commits',
           'user rollbacks'
       )
ORDER  BY name;
~~~

Các counter là tích lũy. Tính delta để biết redo bytes/second, commits/second và retries trong khoảng đo.

Redo bytes mỗi transaction có thể hữu ích:

~~~text
Redo per commit = delta redo size / delta user commits
~~~

Đây là chỉ số tổng hợp để so sánh workload, không phải ngưỡng tốt/xấu cố định.

### 5.7. Xem redo log configuration

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM   v$log
ORDER  BY thread#, group#;
~~~

Xem member path:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM   v$logfile
ORDER  BY group#, member;
~~~

Trong RAC, mỗi instance thread có redo log riêng. Hãy xem THREAD# và kiểm tra đúng instance/thread.

### 5.8. Commit batching và transaction design

Nếu ứng dụng commit sau từng dòng trong batch lớn, có thể tạo nhiều log file sync. Gom các thay đổi liên quan vào transaction có kích thước hợp lý có thể giảm số commit và tăng throughput.

Tuy nhiên, transaction quá lớn làm tăng:
- Undo consumption.
- Thời gian giữ row/table locks.
- Khả năng rollback lâu.
- Rủi ro ảnh hưởng concurrency và recovery.

Chọn batch size theo SLA, khả năng rollback và mức độ độc lập nghiệp vụ.

### 5.9. Không tắt redo để tăng tốc

Không dùng NOLOGGING hoặc thay đổi FORCE LOGGING chỉ vì muốn giảm log file sync. NOLOGGING không áp dụng cho mọi thao tác và có thể ảnh hưởng media recovery/standby. Không tắt ARCHIVELOG hoặc giảm bảo vệ redo khi chưa đánh giá yêu cầu phục hồi.

## 6. Nhận diện vấn đề UNDO

### 6.1. Undo dùng để làm gì?

Undo lưu thông tin cần thiết để:
- Rollback transaction.
- Cung cấp consistent read cho query đang chạy.
- Hỗ trợ một số thao tác Flashback.
- Khôi phục trạng thái trước thay đổi trong transaction.

Khi UPDATE hoặc DELETE nhiều hàng, Oracle tạo undo cho các thay đổi. Undo cũng tạo redo để bản thân undo data được bảo vệ bởi recovery.

### 6.2. Undo pressure và các lỗi thường gặp

Hai lỗi thường cần phân biệt:

- ORA-01555: snapshot too old. Query cần phiên bản dữ liệu cũ nhưng undo cần thiết đã bị ghi đè hoặc không còn sẵn.
- ORA-30036: unable to extend segment in undo tablespace. Transaction không thể cấp thêm undo extent trong undo tablespace.

Lỗi có thể liên quan đến:
- Query chạy lâu.
- DML tạo undo lớn.
- Undo tablespace nhỏ hoặc autoextend không phù hợp.
- Undo retention không đáp ứng workload.
- Concurrent transactions tăng đột biến.
- RETENTION GUARANTEE và không gian còn lại.

### 6.3. ORA-01555 không đơn giản chỉ là thiếu dung lượng

Snapshot too old thường xảy ra khi query cần undo cũ hơn thời gian undo còn giữ được. Có thể do:
- Query chạy lâu trong khi cùng bảng bị cập nhật nhiều.
- Undo tablespace không đủ để giữ undo cần thiết.
- Retention thấp so với thời gian query.
- Workload ghi dữ liệu tăng đột biến.

Tăng dung lượng hoặc retention có thể giúp, nhưng trước hết hãy xác định query nào chạy lâu và tốc độ sinh undo.

### 6.4. ORA-30036

Lỗi này cho biết transaction không thể mở rộng segment trong undo tablespace. Kiểm tra:
- Undo tablespace còn bao nhiêu free space.
- Datafile có autoextend không và maxsize là bao nhiêu.
- Transaction nào đang dùng nhiều undo.
- Tỷ lệ sinh undo và concurrency.
- Retention guarantee có đang bật không.

Không xóa undo extent thủ công hoặc can thiệp segment nội bộ để giải phóng không gian.

### 6.5. Xem V$UNDOSTAT

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       maxqueryid,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt
FROM   v$undostat
ORDER  BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

V$UNDOSTAT cung cấp thống kê theo các interval (thường khoảng 10 phút). Các cột hữu ích:
- UNDOBLKS: số block undo được tiêu thụ trong interval.
- TXNCOUNT: số transaction.
- MAXQUERYLEN: query dài nhất theo thời lượng.
- TUNED_UNDORETENTION: retention được Oracle điều chỉnh.
- SSOLDERRCNT: số lỗi snapshot too old.
- NOSPACEERRCNT: số lỗi không gian undo.
- UNXPSTEALCNT/EXPSTEALCNT: thông tin steal extent theo trạng thái.

Các cột chi tiết và đơn vị cần xác nhận trong Oracle Database Reference đúng release. View có thể không còn interval cũ sau khi dữ liệu được xoay vòng.

### 6.6. Xem transaction dùng undo

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   v$transaction t
JOIN   v$session s
       ON s.taddr = t.addr
ORDER  BY t.used_ublk DESC;
~~~

USED_UBLK và USED_UREC cho biết mức undo mà transaction đang sử dụng. Đây là snapshot tại thời điểm truy vấn; transaction đã kết thúc sẽ không còn ở V$TRANSACTION.

### 6.7. Xem undo extent

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
~~~

Các trạng thái thường gặp gồm ACTIVE, UNEXPIRED và EXPIRED. ACTIVE đang được transaction sử dụng; UNEXPIRED còn trong retention period; EXPIRED có thể được tái sử dụng. Không nên diễn giải UNEXPIRED là dung lượng chắc chắn không bao giờ được tái sử dụng trong mọi cấu hình.

### 6.8. UNDO_RETENTION và RETENTION GUARANTEE

UNDO_RETENTION là mục tiêu thời gian giữ undo. Trong chế độ retention không guarantee, Oracle có thể tái sử dụng undo chưa hết retention khi cần không gian, tùy điều kiện và cấu hình.

RETENTION GUARANTEE yêu cầu giữ undo chưa hết retention, nhưng nếu không còn không gian, DML có thể thất bại thay vì ghi đè undo cần giữ. Đây là đánh đổi giữa bảo đảm consistent read/Flashback và khả năng tiếp tục ghi.

Kiểm tra tablespace:

~~~sql
SELECT tablespace_name,
       retention,
       status,
       contents
FROM   dba_tablespaces
WHERE  contents = 'UNDO';
~~~

Không bật GUARANTEE chỉ để chữa ORA-01555 mà chưa tính đủ dung lượng và tốc độ sinh undo.

### 6.9. Biện pháp xử lý undo

- Rút ngắn query cần consistent read nếu có thể.
- Giảm thời gian transaction mở.
- Chia batch DML thành kích thước hợp lý.
- Tính undo generation rate và dung lượng cần giữ.
- Điều chỉnh UNDO_RETENTION theo thời gian query/Flashback cần hỗ trợ.
- Đánh giá datafile autoextend, maxsize và dung lượng tablespace.
- Cân nhắc RETENTION GUARANTEE chỉ khi có yêu cầu rõ ràng và đủ capacity.
- Tối ưu SQL để tránh scan kéo dài trong lúc dữ liệu liên tục thay đổi.

## 7. Nhận diện nghẽn TEMPORARY SPACE

### 7.1. TEMP dùng để làm gì?

Temporary tablespace lưu các segment tạm cho một số operation, ví dụ:
- Sort lớn.
- Hash join hoặc hash aggregation spill.
- Analytic/window processing.
- DISTINCT và một số phép toán trung gian.
- Một số thao tác LOB hoặc temporary LOB.
- Một số thao tác index/build và các tác vụ SQL khác.

TEMP không phải undo tablespace. TEMP chứa dữ liệu làm việc tạm thời; undo giữ phiên bản dữ liệu cần cho transaction và consistent read.

### 7.2. TEMP đầy và ORA-01652

ORA-01652 thường báo Oracle không thể mở rộng temporary segment trong tablespace. Nguyên nhân có thể:
- TEMP tablespace thiếu dung lượng.
- Tempfile không autoextend hoặc đã chạm MAXSIZE.
- Nhiều session cùng spill.
- Một SQL tạo sort/hash trung gian quá lớn.
- Workarea/PGA không đủ so với workload.
- Dữ liệu trung gian tăng bất thường do plan hoặc join cardinality.

Không phải mọi ORA-01652 đều được giải quyết bằng cách thêm tempfile. Trước hết xác định SQL và operation chiếm TEMP.

### 7.3. Xem session đang dùng TEMP

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       u.tablespace,
       u.segtype,
       u.blocks,
       u.extents
FROM   v$tempseg_usage u
JOIN   v$session s
       ON s.saddr = u.session_addr
      AND s.serial# = u.session_num
ORDER  BY u.blocks DESC;
~~~

V$TEMPSEG_USAGE cho biết session và loại temporary segment. BLOCKS là số block, không phải byte; nhân với block size của tablespace nếu cần quy đổi. Một session có thể có nhiều segment hoặc nhiều dòng metadata.

### 7.4. Xem dung lượng TEMP

~~~sql
SELECT tablespace_name,
       SUM(bytes_used) / 1024 / 1024 AS used_mb,
       SUM(bytes_free) / 1024 / 1024 AS free_mb
FROM   v$temp_space_header
GROUP  BY tablespace_name
ORDER  BY tablespace_name;
~~~

V$TEMP_SPACE_HEADER hiển thị trạng thái không gian theo tempfile. Đây là snapshot; usage có thể thay đổi nhanh khi query kết thúc hoặc session bắt đầu spill.

Kiểm tra tempfile:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_size_mb
FROM   dba_temp_files
ORDER  BY tablespace_name, file_name;
~~~

### 7.5. Workarea: optimal, one-pass và multi-pass

Sort/hash operation dùng workarea trong PGA:
- **Optimal:** xử lý trong memory, không spill dữ liệu operation ra TEMP.
- **One-pass:** cần spill và xử lý qua một lượt partition trung gian.
- **Multi-pass:** phải đọc/ghi nhiều lượt do workarea không đủ; thường có chi phí cao hơn.

Các trạng thái này mô tả cách operation thực thi, không phải trạng thái chung của cả tablespace.

### 7.6. Xem workarea theo SQL

~~~sql
SELECT sql_id,
       child_number,
       operation_type,
       policy,
       estimated_optimal_size,
       last_memory_used,
       last_tempseg_size,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM   v$sql_workarea
ORDER  BY last_tempseg_size DESC NULLS LAST;
~~~

V$SQL_WORKAREA cung cấp thông tin workarea theo cursor/operator. Đây là số liệu lưu theo cursor và execution gần nhất/các counter tích lũy; đọc cùng SQL_ID, child_number và thời điểm đo.

Workarea đang hoạt động:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
FROM   v$sql_workarea_active
ORDER  BY tempseg_size DESC NULLS LAST;
~~~

View active chỉ phản ánh operation đang hoạt động tại thời điểm truy vấn. Một sort đã kết thúc có thể không còn xuất hiện.

### 7.7. Xem PGA statistics

~~~sql
SELECT name,
       value,
       unit
FROM   v$pgastat
WHERE  name IN (
           'aggregate PGA target parameter',
           'total PGA allocated',
           'total PGA inuse',
           'maximum PGA allocated',
           'over allocation count',
           'cache hit percentage'
       )
ORDER  BY name;
~~~

Cache hit percentage là chỉ số tổng hợp của PGA workarea, không nên dùng một mình để kết luận. Over allocation count tăng có thể là dấu hiệu cần điều tra cấu hình và workload, nhưng phải đối chiếu thời gian và số liệu khác.

### 7.8. TEMP tăng không đồng nghĩa phải tăng PGA

PGA target và TEMP giải quyết hai phần khác nhau. Tăng PGA có thể giảm spill nếu memory pressure là nguyên nhân, nhưng tổng PGA còn phụ thuộc concurrency và process. Nếu có nhiều query đồng thời, một mức PGA lớn hơn cho mỗi operation có thể làm tổng memory vượt năng lực host.

Trước khi tăng PGA:
- Xem số active workarea.
- Xem operation spill và số pass.
- Xem concurrency.
- Kiểm tra SQL có xử lý quá nhiều hàng không.
- Kiểm tra PGA aggregate target/limit và host memory.
- Đo lại dưới tải tương tự.

### 7.9. Biện pháp xử lý TEMP

1. Xác định SQL_ID/session chiếm TEMP.
2. Xem plan để tìm SORT, HASH JOIN, HASH GROUP BY, WINDOW SORT.
3. So sánh E-Rows và A-Rows để phát hiện cardinality sai.
4. Giảm hàng đầu vào nếu đúng ngữ nghĩa.
5. Tránh join nhân bản hàng.
6. Chỉ chọn cột cần thiết để giảm kích thước row.
7. Điều chỉnh PGA/workarea sau khi đánh giá concurrency.
8. Mở rộng TEMP nếu workload hợp lệ cần thêm capacity.
9. Kiểm tra autoextend, maxsize, tempfile I/O và không gian storage.
10. Theo dõi lại sau thay đổi.

## 8. Phân biệt REDO, UNDO và TEMP

| Thành phần | Nội dung lưu | Mục đích | Dùng khi | Lỗi/vấn đề thường gặp |
| --- | --- | --- | --- | --- |
| Redo | Record mô tả thay đổi cần phục hồi | Crash/media recovery, redo transport | DML và nhiều thao tác database | log file sync, log buffer space, log switch waits |
| Undo | Thông tin trước thay đổi | Rollback, read consistency, Flashback | DML transaction và consistent read | ORA-01555, ORA-30036 |
| TEMP | Dữ liệu trung gian tạm | Sort/hash/window và thao tác tạm | SQL operation cần workspace ngoài PGA | ORA-01652, TEMP spill lớn |

Một câu UPDATE lớn có thể:
- Dùng CPU để tìm và thay đổi hàng.
- Đọc data block từ storage.
- Tạo undo cho giá trị cũ.
- Tạo redo bảo vệ thay đổi.
- Ghi redo qua LGWR.
- Dùng TEMP nếu plan có sort/hash trung gian.

Không thể xử lý nghẽn bằng cách tăng một loại tablespace bất kỳ. Phải xác định loại dữ liệu và operation thực sự đang thiếu tài nguyên.

## 9. Wait event và cách đọc đúng ngữ cảnh

### 9.1. Xem wait event tích lũy

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(
           time_waited_micro / NULLIF(total_waits, 0) / 1000,
           3
       ) AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class <> 'Idle'
ORDER  BY time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Counter là tích lũy. Lấy hai snapshot và tính delta để tìm wait tăng trong khoảng sự cố. Không so sánh trực tiếp một instance chạy nhiều tháng với instance vừa khởi động.

### 9.2. Xem session đang đợi

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       p1text,
       p1,
       p2text,
       p2,
       p3text,
       p3
FROM   v$session
WHERE  status = 'ACTIVE'
AND    type = 'USER'
AND    state = 'WAITING'
ORDER  BY seconds_in_wait DESC;
~~~

P1/P2/P3 là tham số event-specific. Diễn giải chúng theo tài liệu wait event; không áp dụng chung cùng một ý nghĩa cho mọi event.

### 9.3. Average wait có thể đánh lừa

Một event có average wait nhỏ nhưng tổng wait lớn vì số lần xảy ra rất nhiều. Một event có average wait lớn nhưng chỉ xảy ra một lần có thể không ảnh hưởng tổng workload.

Luôn xem cả total wait, number of waits, active sessions và latency của request.

### 9.4. Wait class không phải chẩn đoán cuối cùng

Ví dụ:
- User I/O cao: có thể là SQL đọc quá nhiều hoặc storage chậm.
- Commit cao: có thể là commit quá thường xuyên hoặc redo write latency.
- Concurrency cao: có thể là mutex/latch contention hoặc tranh chấp cấu trúc.
- Application cao: có thể là lock do ứng dụng giữ transaction.

Tên class chỉ giúp nhóm hiện tượng. Cần truy đến SQL, session và resource cụ thể.

## 10. Kết hợp số liệu database với hệ điều hành

### 10.1. CPU và memory

Đối chiếu:
- CPU utilization theo core.
- Run queue.
- Process Oracle và process khác.
- Available memory.
- Paging/swap.
- PGA allocation và memory pressure.

Host có CPU cao vì antivirus, backup, agent hoặc process khác không phải lỗi của SQL. Xác định process tiêu thụ CPU tại đúng thời điểm.

### 10.2. Storage

Đối chiếu thiết bị chứa:
- Datafile.
- Redo log.
- Tempfile.
- Archive destination.
- Control file.

Theo dõi latency read/write, queue, IOPS và throughput theo từng volume. Một volume chung có thể bị workload backup hoặc batch làm chậm redo/datafile.

### 10.3. Network

Nếu ứng dụng chậm nhưng DB time thấp, kiểm tra:
- Round-trip latency giữa app và database.
- Số round-trip mỗi request.
- Fetch size và số hàng truyền.
- Payload LOB lớn.
- Connection pool và thời gian lấy connection.
- Network retransmission hoặc packet loss.

Không phải mọi latency ở ứng dụng đều được tính là DB time.

### 10.4. RAC và môi trường cluster

Trong RAC, dùng GV$ views khi cần xem nhiều instance và đối chiếu INST_ID. Các wait liên quan global cache/interconnect như gc current/cr block events có thể phản ánh tranh chấp block hoặc network interconnect. Không gộp chúng thành I/O storage thông thường.

Hãy kiểm tra đúng instance, service, node và thread redo. Một node bão hòa CPU hoặc interconnect có thể làm service chậm dù các node khác còn tài nguyên.

## 11. Ma trận triệu chứng và hướng điều tra

| Triệu chứng | Nghi ngờ ban đầu | Bằng chứng cần lấy | Hướng xử lý có thể |
| --- | --- | --- | --- |
| CPU host cao, DB CPU cao | CPU-bound SQL hoặc parallelism | Top SQL CPU, plan, run queue | Tối ưu SQL, giảm work, điều chỉnh DOP |
| DB time cao, DB CPU thấp | Session chờ resource | Top non-idle waits, active sessions | Phân loại wait, xử lý resource gốc |
| db file sequential read cao | Nhiều single-block reads | SQL plan, buffers, I/O latency | Giảm lookup, xem index/access pattern |
| db file scattered read cao | Scan nhiều block | Full scan volume, partition pruning | Giảm dữ liệu scan, tối ưu báo cáo |
| log file sync cao | Commit latency | log file parallel write, commits/sec | Gom transaction hợp lý, kiểm tra redo storage |
| log buffer space | LGWR không giải phóng buffer kịp | redo generation, LGWR wait, storage | Xác định redo burst và LGWR bottleneck |
| log file switch waits | Checkpoint/archive chậm hoặc log nhỏ | V$LOG, archive destination, DBWR | Điều chỉnh log/checkpoint/archive theo đo lường |
| ORA-01555 | Undo không giữ đủ phiên bản cần thiết | V$UNDOSTAT, query duration, DML rate | Rút ngắn query, sizing/retention |
| ORA-30036 | Undo không cấp thêm extent | Undo free space, active transactions | Capacity, autoextend, transaction size |
| ORA-01652 | TEMP không mở rộng được | V$TEMPSEG_USAGE, workarea, tempfile | Tối ưu SQL, PGA hợp lý, thêm TEMP |
| TEMP spill lớn | Sort/hash workarea không đủ hoặc input quá lớn | V$SQL_WORKAREA, plan, A-Rows | Giảm input, sửa plan, đánh giá PGA |
| App chậm, DB time thấp | Network/app/connection pool | App tracing, network, pool metrics | Điều tra ngoài database |

Đây là ma trận định hướng, không phải quy tắc một triệu chứng chỉ có một nguyên nhân.

## 12. Những sai lầm khi xử lý bottleneck

### 12.1. Tăng CPU trước khi tìm SQL

Nếu một câu SQL đọc 100 triệu hàng do predicate sai, tăng CPU chỉ làm hệ thống xử lý công việc thừa nhanh hơn một phần. Tối ưu access path và cardinality có thể mang lại cải thiện lớn hơn.

### 12.2. Tăng SGA/PGA chỉ dựa trên một con số

Buffer cache hit ratio hoặc PGA cache hit percentage không phải chỉ số độc lập để quyết định tăng memory. Hãy xem physical I/O, workarea spill, host memory, concurrency và SLA.

### 12.3. Tăng TEMP mà không tìm session

Thêm tempfile có thể giải quyết thiếu capacity tức thời nhưng không giải quyết query tạo hàng trung gian quá lớn hoặc join sai cardinality. Tìm SQL_ID và operation chiếm TEMP trước.

### 12.4. Tăng UNDO_RETENTION nhưng không tăng capacity

Retention cao hơn cần dung lượng undo phù hợp. Nếu không guarantee, Oracle vẫn có thể tái sử dụng undo chưa hết retention khi áp lực không gian xuất hiện. Nếu guarantee, DML có thể bị chặn khi không gian cạn.

### 12.5. Tăng redo log size mà không xem archive/checkpoint

Log switch thường xuyên có thể liên quan log quá nhỏ, nhưng switch waits cũng có thể do checkpoint hoặc archive backlog. Cần xác định wait event cụ thể và tốc độ redo.

### 12.6. Dựa vào wait event top-1

Một event đứng đầu từ khi instance khởi động có thể không liên quan sự cố hiện tại. Dùng delta trong đúng khoảng thời gian và gắn với SQL/session.

### 12.7. Flush shared pool hoặc buffer cache để thử nghiệm

Flush có thể làm phát sinh hard parse hoặc physical reads hàng loạt, ảnh hưởng toàn bộ workload. Không dùng thao tác này như bước chẩn đoán mặc định trên production.

### 12.8. Bỏ qua transaction và ứng dụng

Commit quá thường xuyên, giữ transaction lâu, fetch quá nhỏ, connection pool sai hoặc gọi database nhiều lần có thể tạo bottleneck dù database configuration hợp lý. Thu thập trace ở tầng ứng dụng và database trong cùng request.

## 13. Runbook điều tra sự cố theo thứ tự

### Bước 1 — Xác định cửa sổ sự cố

Ghi timestamp, service, SQL/API, latency và số lượng request. So sánh với cùng khung giờ ngày thường nếu workload có chu kỳ.

### Bước 2 — Đánh giá DB time và DB CPU

Lấy delta V$SYS_TIME_MODEL. Nếu DB CPU chiếm phần lớn DB time, điều tra CPU. Nếu không, phân loại wait.

### Bước 3 — Xác định session và SQL

Dùng V$SESSION để xem SQL_ID, event, wait class, module/action và blocking session. Tìm top SQL theo CPU, elapsed, buffer gets, disk reads và executions.

### Bước 4 — Xem execution plan thực tế

Dùng DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST, PREDICATE và các tùy chọn phù hợp. So sánh E-Rows/A-Rows, Starts, Buffers và operation.

### Bước 5 — Phân loại tài nguyên

- CPU: DB CPU, OS CPU, run queue, top SQL.
- I/O: wait event, latency và queue trên volume.
- Redo: log file sync, log file parallel write, redo rate và commit rate.
- Undo: V$UNDOSTAT, active transaction, extent usage.
- TEMP: V$TEMPSEG_USAGE, V$SQL_WORKAREA, tempfile capacity.

### Bước 6 — Kiểm tra yếu tố bên ngoài

Kiểm tra storage, network, OS process, VM/container limits, backup, batch job và concurrency.

### Bước 7 — Chọn một thay đổi có giả thuyết

Ví dụ:
- SQL đọc thừa hàng → sửa predicate/index/partition pruning.
- Commit quá nhiều → gom transaction có kiểm soát.
- Sort spill do input quá lớn → giảm input hoặc sửa cardinality.
- Undo thiếu vì transaction quá dài → điều chỉnh batch/query/retention và capacity.
- TEMP thiếu vì workload hợp lệ → tăng capacity sau khi kiểm tra nguyên nhân.

### Bước 8 — Đo lại

Dùng cùng SQL, bind distribution, dữ liệu, concurrency và khoảng đo. So sánh latency, throughput, DB time, CPU, waits, I/O, redo/undo/TEMP. Chỉ giữ thay đổi khi kết quả cải thiện và không làm workload khác suy giảm không chấp nhận được.

## 14. Ví dụ truy vấn chẩn đoán tổng hợp

### 14.1. Top session đang active

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       module,
       action
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER  BY seconds_in_wait DESC;
~~~

### 14.2. Top SQL theo CPU

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds,
       buffer_gets,
       disk_reads,
       rows_processed
FROM   v$sql
WHERE  executions > 0
ORDER  BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

### 14.3. Wait event theo thời gian

~~~sql
SELECT event,
       wait_class,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
       ROUND(time_waited_micro / NULLIF(total_waits, 0) / 1000, 3)
           AS avg_wait_ms
FROM   v$system_event
WHERE  wait_class <> 'Idle'
ORDER  BY time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

### 14.4. Redo rate và commit rate

Chụp hai lần V$SYSSTAT rồi tính:

~~~text
Redo bytes per second = delta(redo size) / elapsed seconds
Commits per second    = delta(user commits) / elapsed seconds
Redo per commit       = delta(redo size) / delta(user commits)
~~~

Các công thức chỉ có ý nghĩa khi counter không reset giữa hai snapshot và cùng instance/workload.

### 14.5. Undo trend

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM   v$undostat
ORDER  BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

### 14.6. TEMP consumers

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       u.tablespace,
       u.segtype,
       u.blocks
FROM   v$tempseg_usage u
JOIN   v$session s
       ON s.saddr = u.session_addr
      AND s.serial# = u.session_num
ORDER  BY u.blocks DESC;
~~~

### 14.7. Workarea spill

~~~sql
SELECT sql_id,
       child_number,
       operation_type,
       last_execution,
       last_memory_used,
       last_tempseg_size,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM   v$sql_workarea
ORDER  BY last_tempseg_size DESC NULLS LAST;
~~~

### 14.8. Undo extent distribution

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extents,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM   dba_undo_extents
GROUP  BY tablespace_name, status
ORDER  BY tablespace_name, status;
~~~

## 15. Bài thực hành

Các bài thực hành nên chạy trên schema/database test có dữ liệu đủ lớn. Không tạo tải nặng hoặc thay đổi tablespace/parameter trên production để thử nghiệm.

### Bài 1 — Đo DB time và DB CPU

Lấy hai snapshot V$SYS_TIME_MODEL cách nhau năm phút. Tính delta DB time và DB CPU. So sánh với latency của ứng dụng.

### Bài 2 — Xác định CPU-bound SQL

Chạy một truy vấn xử lý nhiều hàng. Xem V$SQL theo CPU_TIME và dùng DBMS_XPLAN.DISPLAY_CURSOR để xác định operation tốn CPU.

### Bài 3 — Hard parse

Tạo workload test dùng literal khác nhau, sau đó dùng một câu SQL với bind variable. So sánh parse count, SQL_ID và child cursor.

### Bài 4 — I/O single-block và multiblock

Thử truy vấn dùng index lookup và full scan trên bảng test. Quan sát db file sequential read, db file scattered read hoặc direct path read tùy plan.

### Bài 5 — Đối chiếu storage

Trong cùng cửa sổ chạy truy vấn test, ghi iostat hoặc Performance Monitor. So sánh database wait với latency và queue của đúng volume.

### Bài 6 — Redo generation

Thực hiện batch INSERT/UPDATE với nhiều batch size khác nhau. Đo redo size, commits, log file sync và throughput.

### Bài 7 — Commit frequency

So sánh commit từng hàng với commit theo batch hợp lý. Ghi nhận log file sync, elapsed time, undo usage và khả năng rollback.

### Bài 8 — Log switch

Trong database test, quan sát V$LOG, log switch và archive process khi workload tạo redo lớn. Phân biệt archiving needed với checkpoint incomplete.

### Bài 9 — Undo pressure

Chạy query đọc lâu đồng thời thực hiện DML trên bảng liên quan. Quan sát V$UNDOSTAT, query duration và undo extent distribution.

### Bài 10 — Transaction dùng nhiều undo

Chạy transaction UPDATE nhiều hàng trong schema test. Xem V$TRANSACTION.USED_UBLK và USED_UREC. Rollback sau khi đo.

### Bài 11 — TEMP spill

Tạo sort hoặc hash operation trên dữ liệu đủ lớn. Xem V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE và V$TEMPSEG_USAGE.

### Bài 12 — PGA và concurrency

Chạy nhiều truy vấn sort/hash đồng thời trong môi trường test. Quan sát PGA statistics, number_passes và TEMP usage. Không chỉ tăng PGA rồi kết luận.

### Bài 13 — Phân loại sự cố

Dùng một cửa sổ tải test và thu DB time, CPU, wait events, redo, undo, TEMP. Viết giả thuyết bottleneck dựa trên số liệu, không dựa trên tên event đơn lẻ.

### Bài 14 — Báo cáo trước/sau

Chọn một bottleneck đã xác định. Ghi baseline, giả thuyết, thay đổi, kết quả đo lại và tác động tới workload khác. Nêu rõ bằng chứng nào xác nhận hoặc bác bỏ giả thuyết.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database Performance Tuning Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): phương pháp tuning, CPU, I/O, memory và database performance.
- [Oracle Database Reference — V$SYS_TIME_MODEL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html): DB time, DB CPU và time model statistics.
- [Oracle Database Reference — V$SYSTEM_EVENT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html): wait event counters.
- [Oracle Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state, SQL_ID và wait information.
- [Oracle Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo usage, retention và snapshot-too-old counters.
- [Oracle Database Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo tablespace, retention và transaction behavior.
- [Oracle Database Reference — V$TEMPSEG_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMPSEG_USAGE.html): session sử dụng temporary segment.
- [Oracle Database Reference — V$SQL_WORKAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_WORKAREA.html): workarea statistics cho SQL operators.
- [Oracle Database Reference — V$PGASTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PGASTAT.html): PGA statistics.
- [Oracle Database Reference — V$LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html): online redo log groups và trạng thái.
- [Oracle Database Reference — V$LOGFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOGFILE.html): redo log members.

Nhận diện bottleneck phải dựa trên số liệu theo đúng cửa sổ tải. CPU được xác nhận bằng DB CPU cùng mức bão hòa host; I/O cần đối chiếu wait với latency và throughput storage; redo cần phân biệt log file sync với LGWR write và log switch; undo cần xem transaction, retention và lỗi snapshot/space; TEMP cần xác định session, SQL và workarea spill. **Tìm operation tạo ra áp lực, đo trước/sau cùng workload và chỉ thay đổi cấu hình khi bằng chứng chỉ rõ tài nguyên đang giới hạn hệ thống.**
