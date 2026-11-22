# Wait event, wait class, DB time và phân biệt CPU với thời gian chờ

Khi một câu SQL chậm, câu hỏi đầu tiên thường là “Oracle đang dùng CPU hay đang chờ?”. Một session có thể tiêu tốn thời gian chạy trên CPU, hoặc phải đợi I/O, khóa, redo commit, network, tài nguyên RAC hay một thành phần khác. Nếu chỉ nhìn elapsed time của câu SQL, rất khó biết phần thời gian nào có thể tối ưu bằng SQL, phần nào cần xử lý ở storage, concurrency, ứng dụng hoặc cấu hình hệ thống.

Oracle ghi nhận thời gian hoạt động của foreground sessions bằng các chỉ số time model và ghi nhận các lần chờ bằng wait events. **Wait event** mô tả một sự kiện chờ cụ thể; **wait class** nhóm các sự kiện có tính chất tương tự; **DB time** đo tổng thời gian database calls của foreground sessions, gồm CPU và các lần chờ không thuộc nhóm idle. Đối chiếu DB time với DB CPU và wait time giúp xác định hệ thống đang tiêu tốn thời gian ở đâu.

Bài học này trình bày:
- Wait event, wait class, foreground/background session và trạng thái ON CPU/WAITING.
- DB time, DB CPU, non-idle wait time và Average Active Sessions (AAS).
- Phân biệt CPU-bound, I/O-bound, lock-bound, commit-bound và network-bound.
- Các wait event thường gặp trong Oracle.
- Đọc V$SESSION, V$SYSTEM_EVENT, V$SYSTEM_WAIT_CLASS và V$SYS_TIME_MODEL.
- Đo delta theo khoảng thời gian thay vì đọc counter tích lũy một lần.
- Dùng ASH/AWR/ADDM và SQL trace đúng phạm vi, lưu ý quyền/license.
- Quy trình điều tra từ hệ thống đến session, SQL và operation.
- Lab thực hành và checklist chẩn đoán.

Các ví dụ dùng Oracle Database 19c. Tên event, view và chi tiết instrument có thể thay đổi theo release, platform, RAC và cấu hình; hãy đối chiếu Reference đúng phiên bản. Một số tính năng AWR/ASH/ADDM và SQL Monitor thuộc Diagnostics Pack hoặc Tuning Pack; cần xác nhận license trước khi sử dụng.

## 1. Wait event là gì?

Wait event là sự kiện Oracle ghi nhận khi một session phải tạm dừng để chờ một tài nguyên hoặc một điều kiện hoàn tất. Ví dụ:
- Đợi một block dữ liệu được đọc từ storage.
- Đợi session khác nhả row lock.
- Đợi LGWR ghi redo và xác nhận COMMIT.
- Đợi message hoặc dữ liệu qua network.
- Đợi một latch/mutex bảo vệ cấu trúc bộ nhớ dùng chung.
- Đợi tài nguyên CPU theo Resource Manager.

Một wait event có tên cụ thể, thường kèm tham số P1/P2/P3 giúp mô tả đối tượng hoặc tài nguyên đang chờ. Wait event không tự động có nghĩa hệ thống gặp lỗi. Một số wait là hoạt động bình thường của workload; cần xem thời gian, tần suất, session, SQL và tác động người dùng.

### 1.1. Ví dụ một câu SELECT

Một session chạy:

~~~sql
SELECT *
FROM orders
WHERE order_id = :p_order_id;
~~~

Trong lúc thực thi, session có thể:
1. Chạy trên CPU để parse, tối ưu và xử lý logic.
2. Đợi block index hoặc table từ storage.
3. Đợi block đang được session khác giữ hoặc đang được đọc bởi session khác.
4. Trở lại CPU xử lý row.
5. Gửi kết quả cho client.

Thời gian elapsed của request là tổng các giai đoạn theo đường thực thi. Wait event giúp chỉ ra một phần thời gian session đã bị chặn bởi một điều kiện cụ thể.

### 1.2. Wait không đồng nghĩa với lỗi

Ví dụ **db file sequential read** là wait event bình thường khi Oracle đọc một block qua đường single-block I/O, thường gặp trong index access. Nó chỉ đáng chú ý khi số lần đọc, latency hoặc tổng thời gian ảnh hưởng workload.

Tương tự **log file sync** là một phần của quy trình COMMIT. Một lượng wait nhất định là bình thường. Chỉ khi latency hoặc số lần commit quá lớn mới cần điều tra.

### 1.3. Foreground và background sessions

- Foreground session phục vụ request từ client hoặc thực hiện công việc foreground của database. DB time được định nghĩa dựa trên thời gian foreground sessions trong database calls.
- Background process như DBWn, LGWR, CKPT, PMON, SMON thực hiện công việc nền. CPU/wait của background process không được cộng trực tiếp vào DB time foreground theo cách định nghĩa time model.

Điều này rất quan trọng: DB time không phải tổng mọi giây CPU và wait của tất cả process trên máy chủ. Khi LGWR ghi redo, foreground có thể chờ **log file sync**; bản thân thời gian background LGWR ghi file được đo ở event/background context riêng.

## 2. Wait class là gì?

Wait class là nhóm các wait events có đặc điểm tương tự. Thay vì phải đọc hàng trăm event riêng lẻ ngay từ đầu, DBA có thể xem nhóm nào đang chiếm thời gian lớn rồi đi sâu vào event cụ thể.

Các wait class phổ biến trong Oracle gồm:

| Wait class | Ý nghĩa tổng quát | Ví dụ event |
| --- | --- | --- |
| Administrative | Chờ do hoạt động quản trị | Một số thao tác maintenance/DDL |
| Application | Chờ do logic ứng dụng hoặc lock ứng dụng | enq: TX - row lock contention |
| Cluster | Chờ giao tiếp/đồng bộ giữa instance RAC | gc current request, gc cr request |
| Commit | Chờ hoàn tất commit | log file sync |
| Concurrency | Chờ đồng bộ cấu trúc hoặc tài nguyên đồng thời | buffer busy waits, mutex waits |
| Configuration | Chờ liên quan cấu hình/tài nguyên hệ thống | Một số log file switch waits |
| Idle | Session đang rảnh, chờ client hoặc timer | SQL*Net message from client |
| Network | Chờ network/protocol | SQL*Net more data to client |
| Other | Các wait không thuộc nhóm phổ biến khác | Tùy event |
| Scheduler | Chờ scheduler/resource manager | resmgr:cpu quantum |
| System I/O | I/O cho hoạt động hệ thống/background | control file sequential read, log file parallel write |
| User I/O | I/O phục vụ truy cập dữ liệu của user | db file sequential read, db file scattered read |

Danh sách và phân loại event cụ thể nên được tra trong V$EVENT_NAME của chính database. Không nên phân loại bằng cách nhớ tên event từ một phiên bản khác.

### 2.1. Tại sao phải loại Idle wait?

Một session chờ client gửi lệnh tiếp theo thường có event **SQL*Net message from client**. Đây là idle wait: database không thực hiện công việc cần hoàn tất cho request trong khoảng đó.

Nếu cộng idle wait vào tổng wait time để kết luận database đang chậm, kết quả sẽ sai. DB time loại trừ idle wait. Khi phân tích workload, tập trung vào active sessions và non-idle waits.

### 2.2. Wait class chỉ là điểm bắt đầu

Nếu User I/O chiếm nhiều thời gian, cần tìm event cụ thể, SQL, object và storage latency. Nếu Application wait cao, tìm blocker và transaction giữ lock. Nếu Commit wait cao, kiểm tra commit frequency, redo path và LGWR. Nếu Concurrency cao, xác định latch/mutex/buffer contention cụ thể.

Không thay đổi cấu hình chỉ dựa vào tên wait class.

## 3. DB time và DB CPU

Oracle time model cung cấp các bộ đếm thời gian ở cấp database và session.

### 3.1. DB time

DB time là tổng thời gian foreground sessions dành cho database calls. Nó bao gồm:
- Thời gian foreground session chạy trên CPU trong database call.
- Thời gian foreground session chờ các wait events không thuộc nhóm idle.

DB time được tích lũy qua tất cả foreground sessions. Vì vậy, trong một phút thực tế, DB time có thể tăng hơn 60 giây nếu nhiều session cùng hoạt động đồng thời.

Ví dụ:
- 10 session mỗi session hoạt động 6 giây trong cùng một phút.
- Tổng DB time có thể là 60 giây, dù đồng hồ chỉ trôi qua 60 giây.
- Nếu 100 session cùng hoạt động, DB time có thể tăng nhanh hơn elapsed wall-clock time nhiều lần.

DB time là tổng thời gian session, không phải thời gian người dùng đơn lẻ nhìn thấy và không phải uptime của instance.

### 3.2. DB CPU

DB CPU là tổng thời gian CPU mà foreground sessions tiêu thụ khi thực hiện database calls. Nó không bao gồm toàn bộ CPU của máy chủ, chẳng hạn CPU do background processes, agent, OS hoặc ứng dụng khác sử dụng.

DB CPU là một phần của DB time. Phần còn lại chủ yếu là thời gian foreground sessions chờ non-idle events.

Cách diễn giải gần đúng trong một khoảng đo:

~~~text
DB time ≈ DB CPU + non-idle wait time
~~~

Đây là quan hệ ở mức time model tổng hợp. Khi đối chiếu các view và khoảng đo khác nhau, có thể có chênh lệch do timing, sampling, scope foreground/background và cách tổng hợp counter.

### 3.3. Truy vấn time model

~~~sql
SELECT
    stat_name,
    ROUND(value / 1000000, 2) AS seconds
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

V$SYS_TIME_MODEL lưu VALUE theo microseconds. Chia cho 1.000.000 để chuyển sang giây.

Các giá trị trên là counter tích lũy từ khi instance khởi động hoặc từ thời điểm counter được khởi tạo. Không dùng giá trị tuyệt đối để so sánh workload giữa hai ngày; cần lấy delta giữa hai thời điểm.

### 3.4. Time model theo session

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    tm.stat_name,
    ROUND(tm.value / 1000000, 3) AS seconds
FROM v$sess_time_model tm
JOIN v$session s
  ON s.sid = tm.sid
WHERE s.type = 'USER'
  AND tm.stat_name IN ('DB time', 'DB CPU')
ORDER BY s.sid, tm.stat_name;
~~~

Truy vấn cho biết DB time/DB CPU tích lũy theo session. Với session sống lâu, các counter tăng dần; hãy lấy snapshot hai thời điểm để tính mức tiêu thụ trong khoảng cần phân tích.

## 4. Average Active Sessions (AAS)

AAS là số session trung bình đang hoạt động trong database trong một khoảng thời gian. Một session được xem là active khi đang chạy trên CPU hoặc đang chờ một non-idle wait event.

Công thức:

~~~text
AAS = Delta DB Time (seconds) / Delta Elapsed Time (seconds)
~~~

Ví dụ trong một phút:
- DB time tăng 240 giây.
- Elapsed time là 60 giây.
- AAS = 240 / 60 = 4.

Có thể hiểu trung bình có bốn foreground sessions active trong suốt khoảng đo.

### 4.1. AAS và DB CPU AAS

Tương tự:

~~~text
DB CPU AAS = Delta DB CPU / Delta Elapsed
Non-idle Wait AAS ≈ AAS - DB CPU AAS
~~~

Ví dụ:
- DB time tăng 300 giây trong 60 giây.
- DB CPU tăng 180 giây.
- AAS = 5.
- DB CPU AAS = 3.
- Non-idle wait AAS xấp xỉ 2.

Diễn giải: trung bình khoảng ba session đang tiêu thụ CPU và hai session đang chờ non-idle trong khoảng đo. Đây là mô hình trung bình; tại từng thời điểm số session có thể khác.

### 4.2. AAS có thể lớn hơn số CPU cores

AAS bao gồm cả session đang chờ. Vì vậy AAS = 30 trên máy có 8 vCPU không có nghĩa máy cần 30 CPU cores. Có thể 4 session chạy trên CPU và 26 session đang chờ I/O, lock, commit hoặc network.

DB CPU AAS gần với số CPU cores mà foreground database workload đang tiêu thụ trung bình. Để kết luận CPU saturation, cần so sánh với số CPU khả dụng, OS CPU utilization, run queue, CPU throttling và các process khác trên host.

### 4.3. AAS không phải số connection

Một connection đang idle không đóng góp vào AAS. Một connection đang chạy SQL hoặc chờ non-idle event có đóng góp. Số connection trong pool có thể rất lớn trong khi AAS thấp.

## 5. Phân biệt CPU-bound và wait-bound

Không nên kết luận “database chậm vì CPU” chỉ từ CPU utilization cao hoặc “database chậm vì I/O” chỉ từ một wait event. Cần so sánh DB time, DB CPU, non-idle waits, AAS và host metrics trong cùng khoảng thời gian.

### 5.1. CPU-bound

Dấu hiệu thường gặp:
- DB CPU chiếm phần lớn DB time.
- DB CPU AAS cao so với số CPU cores khả dụng.
- OS CPU utilization cao, run queue tăng hoặc CPU throttling.
- Wait time không chiếm phần lớn DB time.
- SQL thực hiện nhiều phép tính, parse, function, join/sort/hash hoặc xử lý quá nhiều hàng.

Hướng điều tra:
- Tìm SQL có DB CPU/elapsed time cao.
- Xem execution plan, E-Rows/A-Rows, số hàng xử lý và buffer gets.
- Kiểm tra parse calls, hard parse, PL/SQL/function overhead.
- Giảm lượng dữ liệu đọc và xử lý.
- Dùng set-based SQL, tránh lặp truy vấn từ ứng dụng.
- Kiểm tra parallelism có làm tăng tranh chấp CPU không.

CPU cao không tự động có nghĩa cần thêm CPU. Một SQL có thể tiêu thụ CPU vì xử lý hàng triệu row không cần thiết hoặc plan không phù hợp.

### 5.2. Wait-bound

Dấu hiệu:
- DB time cao nhưng DB CPU chiếm tỷ lệ thấp hơn.
- Non-idle wait AAS cao.
- Một hoặc vài wait class/event chiếm nhiều thời gian.
- OS CPU có thể chưa bão hòa, nhưng request vẫn chậm.

Tiếp theo phải phân loại wait:
- User I/O: truy cập block dữ liệu.
- Application: lock hoặc chờ do logic ứng dụng.
- Commit: đồng bộ redo commit.
- Concurrency: latch, mutex, buffer contention.
- Network: truyền dữ liệu/chờ client.
- Cluster: giao tiếp cache giữa RAC instances.
- Scheduler: Resource Manager cấp CPU.

Wait-bound không đồng nghĩa database server thiếu tài nguyên. Có thể ứng dụng gửi COMMIT quá thường xuyên, giữ transaction lâu, trả quá nhiều dữ liệu hoặc có một session chặn nhiều session khác.

### 5.3. Bảng so sánh nhanh

| Chỉ số/dấu hiệu | CPU-bound | Wait-bound |
| --- | --- | --- |
| DB CPU / DB time | Thường cao | Thường thấp hơn |
| DB CPU AAS | Có thể gần giới hạn CPU | Thường thấp hơn AAS |
| Non-idle wait AAS | Tương đối thấp | Cao |
| Host CPU | Có thể bão hòa/run queue cao | Có thể còn dư CPU |
| Wait event | Không có một event chi phối | Có event/class chi phối |
| Hướng xử lý | Giảm CPU work, sửa SQL/plan | Xác định tài nguyên/session gây wait |
| Ví dụ | Sort/hash quá lớn, parse nhiều | I/O latency, row lock, log file sync |

Đây là dấu hiệu định hướng, không phải luật tuyệt đối. Một hệ thống có thể vừa CPU-bound vừa có wait do contention.

## 6. Các wait event thường gặp

### 6.1. User I/O

| Event | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| db file sequential read | Đọc single block, thường gặp trong index access | Index access pattern, random I/O latency, số lần lookup |
| db file scattered read | Đọc nhiều block, thường gặp trong full scan/buffered multiblock read | Full scan có hợp lý không, table size, MBRC, storage throughput |
| direct path read | Đọc trực tiếp vào PGA/buffer riêng theo đường direct read | Large scan, parallel query, direct path workload |
| direct path read temp | Đọc dữ liệu từ temporary tablespace | Sort/hash spill, PGA, workarea size |
| read by other session | Session chờ block đang được session khác đọc | Hot block/read concurrency, I/O latency |

db file sequential read không nhất thiết có nghĩa truy vấn dùng index sai; lookup theo primary key có thể là hành vi mong muốn. Cần xem tổng số wait, average latency và số hàng được trả về.

### 6.2. Commit và redo

| Event | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| log file sync | Foreground chờ LGWR xác nhận redo commit đã được ghi | Commit frequency, redo write latency, LGWR workload |
| log file parallel write | LGWR chờ hoàn tất ghi redo log files | Redo storage latency, I/O path, log configuration |
| log buffer space | Session không thể ghi redo mới vì log buffer thiếu chỗ trống phù hợp | Redo generation rate, LGWR throughput, redo path |
| log file switch completion | Chờ hoàn tất chuyển redo log group | Log sizing, checkpoint/archive throughput |

log file sync là foreground wait; log file parallel write thường là background LGWR wait. Nếu foreground log file sync cao, cần liên hệ với LGWR write latency nhưng không được cộng hai counter như hai phần độc lập của DB time.

Một nguyên nhân phổ biến là ứng dụng COMMIT sau từng row. Batch nhiều DML trong một transaction có thể giảm số lần commit round trip và log file sync, nhưng phải giữ đúng yêu cầu atomicity và lock duration.

### 6.3. Application và row lock

| Event | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| enq: TX - row lock contention | Session chờ transaction khác nhả khóa hàng | Blocker session, transaction mở lâu, cùng row được cập nhật |
| enq: TM - contention | Chờ enqueue liên quan table/DML lock | DDL/DML, khóa bảng, foreign key/index và transaction |
| enq: TX - allocate ITL entry | Chờ transaction slot trong block | Concurrent modifications, INITRANS, block contention |

Để tìm blocker, kiểm tra BLOCKING_SESSION, FINAL_BLOCKING_SESSION, ROW_WAIT_* và transaction của blocker. Không kill session ngay khi thấy lock wait; xác định chủ sở hữu nghiệp vụ và tác động rollback trước.

### 6.4. Concurrency, latch và mutex

| Event | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| buffer busy waits | Chờ buffer block đang bị session khác sử dụng/điều chỉnh | Hot block, segment contention, concurrent DML |
| cursor: pin S wait on X | Chờ mutex/pin của cursor | Parse/DDL/invalidation và SQL concurrency |
| library cache: mutex X | Chờ mutex bảo vệ library cache | Hard parse, cursor contention, shared SQL |
| latch: cache buffers chains | Chờ latch trên buffer chain | Hot block, access pattern và concurrent reads |

Không xử lý mọi concurrency wait bằng cách tăng INITRANS hoặc thêm index. Cần xác định đúng resource, segment, SQL và mẫu truy cập.

### 6.5. Network

| Event | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| SQL*Net more data to client | Database gửi thêm dữ liệu cho client | Result set lớn, fetch pattern, network throughput |
| SQL*Net more data from client | Database chờ thêm dữ liệu từ client | Payload/client send behavior, application latency |
| SQL*Net message from client | Database chờ client gửi lệnh tiếp theo; thường là idle | Không tính như bottleneck DB time |

Nếu SQL*Net more data to client cao, kiểm tra số hàng/cột trả về, LOB, fetch size và network. Nếu SQL*Net message from client cao, session thường idle giữa các request; không kết luận database đang nghẽn network chỉ từ event này.

### 6.6. RAC Cluster

Một số event trong RAC:
- gc current request
- gc cr request
- gc buffer busy acquire
- gc current block busy
- gc cr block busy

Chúng liên quan Global Cache Service và việc lấy current/consistent-read block từ instance khác. Cần phân tích theo instance, object/block, interconnect latency và workload phân tán. Không áp dụng chẩn đoán RAC cho database single-instance.

### 6.7. Scheduler và Resource Manager

Event như resmgr:cpu quantum có thể cho thấy session bị điều tiết theo Resource Manager plan. Nó không giống chờ CPU vật lý đơn thuần. Kiểm tra consumer group, plan directive, CPU utilization và workload priority.

## 7. Xem wait event của session hiện tại

V$SESSION hiển thị trạng thái và wait hiện tại của session.

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    wait_class,
    state,
    seconds_in_wait,
    blocking_session,
    final_blocking_session,
    module,
    action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

Ý nghĩa:
- STATUS = ACTIVE cho biết session đang trong database call; nó có thể chạy CPU hoặc chờ non-idle event.
- EVENT là event hiện tại/gần nhất theo state.
- WAIT_CLASS nhóm event.
- STATE cho biết session đang WAITING hoặc trạng thái wait đã kết thúc.
- BLOCKING_SESSION là SID blocker nếu Oracle xác định được.
- MODULE/ACTION giúp gắn session với ứng dụng/endpoint.

Không đọc một snapshot đơn lẻ rồi kết luận event đó chiếm phần lớn thời gian request. Một session có thể chuyển event liên tục; cần quan sát theo khoảng thời gian hoặc dùng tracing/sampling.

### 7.1. Chỉ xem session đang thực sự WAITING

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    seconds_in_wait,
    state,
    p1text,
    p1,
    p2text,
    p2,
    p3text,
    p3
FROM v$session
WHERE type = 'USER'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

P1/P2/P3 là tham số event-specific. Ý nghĩa thay đổi theo event; xem V$EVENT_NAME để biết tên tham số và tài liệu event tương ứng.

### 7.2. Session đang chạy CPU có thể không có wait event

Khi session thực hiện CPU work, nó có thể không ở trạng thái WAITING. V$SESSION.STATUS có thể là ACTIVE, còn EVENT/STATE không biểu thị một wait đang diễn ra. Do đó:
- ACTIVE không đồng nghĩa đang chờ.
- Không thấy wait event không đồng nghĩa session idle.
- Muốn biết CPU time, dùng time model/session stats hoặc sampling phù hợp.

## 8. Xem wait class ở cấp hệ thống

V$SYSTEM_WAIT_CLASS tổng hợp số wait và thời gian theo wait class từ khi instance khởi động.

~~~sql
SELECT
    wait_class,
    total_waits,
    ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        time_waited_micro / NULLIF(total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_wait_class
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Các counter là tích lũy. Nếu instance chạy nhiều ngày, class đứng đầu có thể phản ánh workload lịch sử chứ không phải vấn đề hiện tại. Để phân tích một incident, cần lấy hai snapshot và tính delta trong khoảng incident.

### 8.1. Xem event cụ thể

~~~sql
SELECT
    e.event,
    n.wait_class,
    e.total_waits,
    ROUND(e.time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        e.time_waited_micro / NULLIF(e.total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_event e
JOIN v$event_name n
  ON n.name = e.event
WHERE n.wait_class <> 'Idle'
ORDER BY e.time_waited_micro DESC
FETCH FIRST 30 ROWS ONLY;
~~~

V$EVENT_NAME mô tả event và wait class. Nếu phiên bản có khác biệt về view columns hoặc multitenant scope, kiểm tra Data Dictionary Reference của release đang dùng.

### 8.2. Average wait không đủ để xếp hạng vấn đề

Một event có average wait 50 ms nhưng chỉ xảy ra 2 lần có thể ít ảnh hưởng hơn event 1 ms xảy ra 2 triệu lần. Hãy xem đồng thời:
- Tổng wait time.
- Số wait.
- Average wait.
- Waits/second trong khoảng đo.
- Session/SQL/object liên quan.
- Ảnh hưởng tới response time.

## 9. Đo delta theo thời gian

Counter trong V$SYS_TIME_MODEL và V$SYSTEM_EVENT tích lũy. Phân tích performance cần so sánh cùng một khoảng thời gian.

### 9.1. Lấy snapshot đầu và cuối

Tại thời điểm T1, lưu:
- DB time và DB CPU từ V$SYS_TIME_MODEL.
- Total waits và TIME_WAITED_MICRO từ V$SYSTEM_EVENT hoặc V$SYSTEM_WAIT_CLASS.
- Thời gian đồng hồ T1.

Sau khoảng quan sát, tại T2 lưu cùng các giá trị. Tính delta:

~~~text
Delta DB time = DB time(T2) - DB time(T1)
Delta DB CPU  = DB CPU(T2) - DB CPU(T1)
Elapsed       = T2 - T1
AAS           = Delta DB time / Elapsed
DB CPU AAS    = Delta DB CPU / Elapsed
~~~

Chỉ so sánh snapshot của cùng instance và cùng container/scope. Nếu instance restart giữa hai snapshot, counter có thể reset; delta khi đó không hợp lệ.

### 9.2. Lấy time model snapshot

~~~sql
SELECT
    SYSTIMESTAMP AS captured_at,
    stat_name,
    value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU');
~~~

Ghi kết quả vào file/monitoring system hoặc bảng snapshot do DBA quản lý. Không tạo bảng snapshot trong schema nghiệp vụ chỉ để chạy một lần chẩn đoán.

### 9.3. Lấy wait class snapshot

~~~sql
SELECT
    SYSTIMESTAMP AS captured_at,
    wait_class,
    total_waits,
    time_waited_micro
FROM v$system_wait_class
WHERE wait_class <> 'Idle';
~~~

Tại T2, lấy lại cùng truy vấn. Với từng class:

~~~text
Delta wait seconds =
    (TIME_WAITED_MICRO_T2 - TIME_WAITED_MICRO_T1) / 1,000,000
~~~

Sau đó chia delta cho elapsed để có wait-class AAS xấp xỉ. Cần giữ cùng instance/container scope và xử lý counter reset.

### 9.4. Không cộng counter tuyệt đối giữa nhiều nguồn

Không cộng DB time với tổng wait time như hai đại lượng độc lập: wait time đã là một phần của DB time. Cũng không cộng log file sync foreground wait với log file parallel write background wait để tính DB time; chúng mô tả hai phía của cùng hoạt động redo.

## 10. Time model và wait event ở cấp session

Khi một hệ thống có nhiều user, cần xác định session nào đóng góp DB time hoặc wait time nhiều nhất.

### 10.1. Session time model

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.module,
    s.action,
    tm.stat_name,
    ROUND(tm.value / 1000000, 3) AS seconds
FROM v$sess_time_model tm
JOIN v$session s
  ON s.sid = tm.sid
WHERE s.type = 'USER'
  AND tm.stat_name IN ('DB time', 'DB CPU')
ORDER BY tm.value DESC;
~~~

Đây là counter tích lũy theo session. Với connection pool, một session có thể phục vụ nhiều request theo thời gian. Gắn MODULE/ACTION và lấy delta theo request/window sẽ giúp phân tích chính xác hơn.

### 10.2. Session event

~~~sql
SELECT
    se.sid,
    s.serial#,
    s.username,
    s.sql_id,
    se.event,
    n.wait_class,
    se.total_waits,
    ROUND(se.time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        se.time_waited_micro / NULLIF(se.total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$session_event se
JOIN v$session s
  ON s.sid = se.sid
JOIN v$event_name n
  ON n.name = se.event
WHERE s.type = 'USER'
  AND n.wait_class <> 'Idle'
ORDER BY se.time_waited_micro DESC;
~~~

V$SESSION_EVENT tổng hợp wait theo session kể từ khi session được tạo hoặc counter được khởi tạo. Một session connection-pool sống lâu có thể mang lịch sử nhiều request. Đọc delta hoặc trace theo request thay vì coi counter là của request hiện tại.

### 10.3. Tìm blocker

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    blocking_session,
    blocking_session_status,
    final_blocking_session,
    seconds_in_wait,
    module,
    action
FROM v$session
WHERE state = 'WAITING'
  AND wait_class <> 'Idle'
  AND blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Sau khi tìm blocker SID, truy vấn thông tin blocker:

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    wait_class,
    last_call_et,
    module,
    action
FROM v$session
WHERE sid = :p_blocker_sid;
~~~

Kiểm tra transaction đang mở, thời điểm bắt đầu, SQL trước đó và ứng dụng sở hữu session. Không kết thúc blocker nếu chưa đánh giá hậu quả rollback và được quy trình vận hành cho phép.

## 11. ASH và AWR: quan sát theo thời gian

Một snapshot V$SESSION chỉ cho biết trạng thái tại một thời điểm. Để hiểu workload thay đổi như thế nào trong một khoảng, Oracle có Active Session History (ASH) và Automatic Workload Repository (AWR).

### 11.1. ASH

ASH lấy mẫu các session đang active theo chu kỳ. Mỗi sample có thể cho biết:
- Session state: ON CPU hoặc WAITING.
- Wait class/event.
- SQL_ID và plan line.
- Module/action.
- Blocking session.
- Object hoặc thông tin liên quan tùy sample.

ASH giúp trả lời “trong khoảng incident, các session active đã dành thời gian ở đâu?” thay vì chỉ xem một event tại thời điểm truy vấn.

Ví dụ truy vấn V$ACTIVE_SESSION_HISTORY:

~~~sql
SELECT
    wait_class,
    event,
    session_state,
    COUNT(*) AS samples
FROM v$active_session_history
WHERE sample_time >= SYSTIMESTAMP - INTERVAL '10' MINUTE
GROUP BY wait_class, event, session_state
ORDER BY samples DESC;
~~~

Mẫu này minh họa cách nhóm sample gần đây. Nó không phải phép đo thời gian chính xác từng microsecond; sample count dùng để ước lượng phân bố active time. Cần chọn đúng time zone, container, instance và SQL/module scope.

### 11.2. ON CPU trong ASH

ASH có thể ghi SESSION_STATE = 'ON CPU' khi session đang chạy trên CPU tại thời điểm sample. Khi WAITING, event và wait class cho biết session đang chờ gì.

Một session không xuất hiện trong ASH vì idle không có nghĩa nó mất tích; ASH tập trung vào active sessions. Vì sampling có thể bỏ qua wait rất ngắn, không dùng sample count như audit đầy đủ mọi wait.

### 11.3. AWR

AWR lưu snapshot performance statistics theo thời gian, hỗ trợ so sánh workload giữa hai khoảng và tạo báo cáo. AWR thường dùng để xem:
- DB time, DB CPU và load profile.
- Top foreground wait events.
- Wait class distribution.
- SQL ordered by elapsed time, CPU, gets hoặc reads.
- Instance activity và time model.

AWR/ASH/ADDM là tính năng thuộc Oracle Diagnostics Pack theo chính sách license của Oracle. Trước khi chạy report hoặc truy vấn các view lịch sử tương ứng, xác nhận license/entitlement và cấu hình control_management_pack_access với DBA. Không mặc định mọi môi trường đều được phép dùng.

### 11.4. AWR không thay thế trace chi tiết

AWR giúp tìm vùng vấn đề ở cấp hệ thống/khoảng thời gian. SQL trace/TKPROF hoặc instrumentation ở ứng dụng có thể cung cấp chi tiết một session/request. Kết hợp nhiều lớp sẽ cho kết luận đáng tin cậy hơn.

## 12. SQL Trace và DBMS_MONITOR

SQL Trace ghi nhận parse, execute, fetch, waits và thống kê cho session/SQL. TKPROF định dạng trace file để phân tích số lần gọi, elapsed time, CPU, disk reads, query/current gets và wait events.

DBMS_MONITOR có thể bật trace theo session, client identifier, service/module/action tùy API và quyền. Ví dụ minh họa trace một session:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => 123,
        serial_num => 456,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
~~~

Tắt trace sau khi thu thập:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => 123,
        serial_num => 456
    );
END;
/
~~~

SID và SERIAL# phải lấy từ session mục tiêu. Không bật binds nếu không cần, vì bind data có thể chứa thông tin nhạy cảm. Trace tạo file và overhead; chỉ bật trong thời gian cần thiết, kiểm soát quyền truy cập và dọn file theo retention policy.

## 13. Các chỉ số bổ sung để phân biệt CPU và wait

### 13.1. Host CPU

DB CPU không phải CPU utilization toàn host. So sánh:
- Host CPU user/system/idle.
- Run queue/load average.
- CPU ready/steal/throttling trong VM/cloud.
- Số CPU cores/vCPU khả dụng.
- CPU của Oracle foreground và background processes.

Nếu host CPU cao nhưng DB CPU thấp, có thể process khác hoặc background workload đang dùng CPU. Nếu DB CPU cao nhưng host còn dư, có thể còn capacity hoặc workload phân tán trên nhiều core.

### 13.2. I/O latency và throughput

Với User I/O, xem:
- Số physical reads.
- Average read latency.
- IOPS và throughput.
- Queue depth.
- Storage tier và ASM/diskgroup.
- SQL/object tạo ra I/O.

Không kết luận storage chậm chỉ vì db file sequential read đứng đầu. Event có thể nhiều do hàng triệu lookup nhỏ; latency trung bình vẫn tốt nhưng tổng thời gian cao.

### 13.3. Redo và commit

Với log file sync, xem:
- Commit count và commits per transaction.
- Redo size/rate.
- LGWR write latency.
- Log file parallel write.
- Storage path của online redo.
- Ứng dụng có commit từng row hay không.

Tăng log buffer không phải giải pháp mặc định cho log file sync. Nếu latency đến từ redo storage hoặc commit quá thường xuyên, thay đổi buffer có thể không giải quyết nguyên nhân.

### 13.4. Lock contention

Với row lock:
- Xác định blocker và waiter.
- Xem SQL đang giữ transaction.
- Tìm transaction dài, user think time trong transaction hoặc lỗi không rollback.
- Xem cùng một row/key bị cập nhật bởi nhiều request.
- Xem foreign key/index phù hợp cho DML liên quan.

Không kill blocker chỉ vì nó đứng đầu wait report. Một session đang chạy transaction nghiệp vụ có thể làm rollback lớn và gây tác động rộng hơn.

### 13.5. Network và fetch

Nếu Network wait tăng:
- Đo round trip ứng dụng/database.
- Xem số hàng/cột trả về.
- Kiểm tra LOB và payload lớn.
- Kiểm tra fetch size, batch fetch và N+1 query.
- Phân biệt database chờ client gửi lệnh với database gửi dữ liệu cho client.

SQL*Net message from client thường là idle wait và không đóng góp DB time. SQL*Net more data to client là event khác, có thể phản ánh truyền result lớn.

## 14. Quy trình chẩn đoán từ hệ thống đến SQL

Khi nhận báo cáo “Oracle chậm”, đi theo thứ tự:

### Bước 1: Xác định khoảng incident

Ghi:
- Thời điểm bắt đầu/kết thúc.
- Database, instance, PDB/service.
- Endpoint hoặc batch bị ảnh hưởng.
- Số người dùng/request.
- Có thay đổi deployment, data load hoặc maintenance không.

Mọi counter cần được so sánh trên cùng khoảng thời gian và scope.

### Bước 2: Tính DB time, DB CPU và AAS

Lấy delta V$SYS_TIME_MODEL. Tính:
- DB time/elapsed.
- DB CPU/elapsed.
- AAS.
- DB CPU AAS.
- Non-idle wait AAS xấp xỉ.

Nếu DB time thấp nhưng người dùng vẫn thấy chậm, kiểm tra network/client/application/pool; thời gian chờ ngoài database call không nằm trong DB time.

### Bước 3: Xem wait class và event

Lấy delta V$SYSTEM_WAIT_CLASS và V$SYSTEM_EVENT, loại Idle. Tìm:
- Wait class chiếm nhiều thời gian.
- Event có tổng wait lớn.
- Average wait và số lần.
- Event tăng bất thường so với baseline.

### Bước 4: Xác định session/SQL

Dùng V$SESSION, V$SESSION_EVENT, V$SESS_TIME_MODEL, tracing hoặc ASH/AWR nếu được cấp phép. Gắn SQL_ID, module/action, blocking session và object.

### Bước 5: Đọc execution plan

Dùng DBMS_XPLAN.DISPLAY_CURSOR khi có quyền và cursor phù hợp. Nếu có runtime stats, so sánh E-Rows/A-Rows/Starts, Buffers, Reads và A-Time.

### Bước 6: Đưa ra giả thuyết theo loại bottleneck

| Bằng chứng | Hướng điều tra |
| --- | --- |
| DB CPU AAS cao, host CPU bão hòa | SQL CPU, plan, parse, parallelism |
| User I/O wait tăng, read latency cao | Storage, access path, data volume |
| User I/O wait nhiều nhưng latency thấp | Quá nhiều reads/lookup, SQL/index design |
| Application wait/row lock tăng | Blocker, transaction duration, hot rows |
| Commit wait tăng | Commit frequency, redo write latency |
| Concurrency wait tăng | Hot block, latch/mutex, parse contention |
| Network wait gửi dữ liệu tăng | Result size, fetch, round trip |
| Scheduler wait tăng | Resource Manager, consumer group, CPU allocation |
| RAC Cluster wait tăng | Interconnect, hot blocks, service placement |

### Bước 7: Kiểm chứng thay đổi

Chỉ thay đổi một yếu tố mỗi lần nếu có thể. So sánh cùng workload:
- DB time và DB CPU.
- AAS và wait class.
- SQL elapsed/CPU/buffers/reads.
- Application p95/p99.
- Error rate và throughput.

Không kết luận thành công chỉ vì một wait event giảm; workload có thể chuyển bottleneck sang nơi khác.

## 15. Lab: quan sát DB time, DB CPU và wait class

Lab chỉ đọc dynamic performance views và chạy truy vấn nhẹ. Cần quyền đọc V$ view. Nếu không có quyền, nhờ DBA chạy hoặc cấp quyền tối thiểu trong môi trường thực hành.

### 15.1. Đọc DB time và DB CPU

~~~sql
SELECT
    stat_name,
    ROUND(value / 1000000, 3) AS seconds
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Ghi lại kết quả ở T1. Chạy workload lab trong một khoảng thời gian xác định rồi truy vấn lại ở T2. Lấy chênh lệch từng statistic.

### 15.2. Tính AAS

Giả sử bạn ghi:
- DB time T1 và T2 tính bằng giây.
- DB CPU T1 và T2 tính bằng giây.
- Elapsed time giữa hai snapshot là 60 giây.

Tính:

~~~text
DB time delta = DB time T2 - DB time T1
DB CPU delta  = DB CPU T2 - DB CPU T1
AAS           = DB time delta / 60
DB CPU AAS    = DB CPU delta / 60
Wait AAS      = AAS - DB CPU AAS
~~~

Nếu wait AAS âm đáng kể, hãy kiểm tra snapshot không cùng scope, counter reset hoặc sai đơn vị. Về nguyên tắc, DB CPU là thành phần của DB time.

### 15.3. Xem wait class

~~~sql
SELECT
    wait_class,
    total_waits,
    ROUND(time_waited_micro / 1000000, 2) AS wait_seconds,
    ROUND(
        time_waited_micro / NULLIF(total_waits, 0) / 1000,
        3
    ) AS avg_wait_ms
FROM v$system_wait_class
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Lưu snapshot hai thời điểm và tính delta. Không dùng số tuyệt đối kể từ startup để mô tả một incident ngắn.

### 15.4. Xem event chi tiết

~~~sql
SELECT
    e.event,
    n.wait_class,
    e.total_waits,
    ROUND(e.time_waited_micro / 1000000, 2) AS wait_seconds
FROM v$system_event e
JOIN v$event_name n
  ON n.name = e.event
WHERE n.wait_class <> 'Idle'
ORDER BY e.time_waited_micro DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Chọn một event đứng đầu và ghi lại số wait, tổng thời gian, average wait. Xác định event có liên quan đến workload lab hay là lịch sử từ workload khác.

### 15.5. Xem session đang chờ

~~~sql
SELECT
    sid,
    serial#,
    username,
    sql_id,
    event,
    wait_class,
    state,
    seconds_in_wait,
    blocking_session,
    module,
    action
FROM v$session
WHERE type = 'USER'
  AND state = 'WAITING'
  AND wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
~~~

Chạy truy vấn khi có workload đang hoạt động. Một snapshot có thể bỏ lỡ wait ngắn; lấy nhiều snapshot hoặc dùng tracing/sampling thích hợp.

## 16. Lab: tạo các tình huống wait có kiểm soát

Thực hiện trong database/schema lab riêng, không chạy trên bảng nghiệp vụ. Một số tình huống cần hai session SQL*Plus/SQLcl.

### 16.1. Tạo bảng khóa

~~~sql
CREATE TABLE lab_wait_lock (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO lab_wait_lock VALUES (1, 100);
COMMIT;
~~~

### 16.2. Tạo row lock

Session A:

~~~sql
UPDATE lab_wait_lock
SET value = value + 1
WHERE id = 1;
-- Chưa COMMIT hoặc ROLLBACK.
~~~

Session B:

~~~sql
UPDATE lab_wait_lock
SET value = value + 10
WHERE id = 1;
~~~

Session B sẽ chờ row lock. Từ session quan sát, xem V$SESSION với EVENT enq: TX - row lock contention, WAIT_CLASS và BLOCKING_SESSION.

Sau khi quan sát, session A:

~~~sql
ROLLBACK;
~~~

Session B sẽ tiếp tục. Sau đó rollback session B để đưa lab về trạng thái ban đầu.

### 16.3. Tạo workload đọc

Chạy một truy vấn đọc nhiều hàng trong bảng lab lớn hơn, hoặc tạo bảng lab có đủ dữ liệu và index. Xem event User I/O. Kết quả phụ thuộc buffer cache và storage; nếu dữ liệu đã cache, có thể không thấy physical read wait đáng kể.

Không dùng hint hoặc flush buffer cache toàn hệ thống chỉ để ép xuất hiện I/O. Thao tác flush ảnh hưởng workload khác và cần quyền DBA.

### 16.4. Quan sát commit wait

Thực hiện một batch DML rồi COMMIT trong session lab. Xem event log file sync ở V$SESSION/V$SYSTEM_EVENT trong khoảng đo. Wait có thể rất ngắn và khó bắt bằng một snapshot; dùng trace hoặc nhiều lần chạy có kiểm soát nếu cần.

Không cố tình tạo lượng COMMIT lớn trên database dùng chung để tạo wait. Chỉ quan sát workload lab được phép.

### 16.5. Dọn bảng lab

~~~sql
DROP TABLE lab_wait_lock PURGE;
~~~

## 17. Những lỗi thường gặp khi đọc wait

| Hiện tượng | Cách hiểu sai | Cách hiểu đúng |
| --- | --- | --- |
| SQL*Net message from client đứng đầu | Database bị nghẽn network | Thường là idle wait, session đang chờ client |
| db file sequential read xuất hiện | Index luôn là nguyên nhân xấu | Đây là single-block read thường gặp; xem latency và volume |
| log file sync cao | Tăng log buffer chắc chắn giải quyết | Kiểm tra commit frequency và redo write latency |
| AAS lớn hơn số CPU | Database cần nhiều CPU hơn AAS | AAS gồm CPU và wait; so sánh DB CPU AAS với host CPU |
| DB time lớn hơn elapsed | Counter sai | DB time cộng thời gian nhiều foreground sessions đồng thời |
| DB CPU thấp, request vẫn chậm | Database không có vấn đề | Có thể wait-bound hoặc chờ ngoài database |
| Một wait event có average cao | Đây chắc chắn là bottleneck lớn nhất | Xem total wait, số lần và impact |
| V$SYSTEM_EVENT time lớn | Đây là thời gian của incident hiện tại | Counter tích lũy từ startup; cần delta |
| Session ACTIVE | Session đang chạy CPU | ACTIVE có thể đang chờ non-idle |
| Không thấy wait event | Session không hoạt động | Có thể session đang ON CPU |
| enq: TX cao | Kill blocker ngay | Xác định blocker, transaction và tác động rollback |
| direct path read temp cao | Storage datafile chậm | Có thể sort/hash spill vào TEMP |
| gc wait cao | Disk I/O chậm | Trong RAC, kiểm tra Global Cache/interconnect |
| resmgr:cpu quantum | CPU hardware bị hỏng | Xem Resource Manager consumer group/plan |
| Cộng DB time và wait time | Tổng active time | Wait time đã nằm trong DB time, không cộng hai lần |

## 18. Checklist báo cáo performance

Một báo cáo wait analysis nên có:
- Khoảng thời gian và timezone.
- Database, instance, PDB/service.
- Số request và workload bị ảnh hưởng.
- Delta DB time và DB CPU.
- AAS, DB CPU AAS và non-idle wait AAS.
- Top wait classes và events theo delta.
- SQL_ID/child cursor và module/action liên quan.
- Blocker/session/object nếu là lock wait.
- Runtime plan và cardinality nếu có.
- Host CPU, run queue, I/O latency, network metrics.
- Giả thuyết nguyên nhân và bằng chứng.
- Thay đổi đã thử và kết quả trước/sau.
- Quyền/license của công cụ lịch sử được sử dụng.

Không gửi bind values, SQL text hoặc trace file chứa dữ liệu nhạy cảm ra ngoài phạm vi được phép.

## 19. Bài tập thực hành

### Bài 1 — Time model

Truy vấn DB time và DB CPU tại hai thời điểm cách nhau một phút. Tính delta và giải thích vì sao counter tích lũy không thể dùng trực tiếp làm thời gian incident.

### Bài 2 — AAS

Một khoảng 120 giây có DB time delta 600 giây và DB CPU delta 420 giây. Tính AAS, DB CPU AAS và non-idle wait AAS. Diễn giải số session active trung bình.

### Bài 3 — CPU-bound

Tạo workload CPU trong schema lab, quan sát DB CPU AAS và host CPU. Đề xuất cách tìm SQL tiêu thụ CPU lớn.

### Bài 4 — User I/O

Chạy workload đọc bảng lớn. So sánh db file sequential read, db file scattered read và direct path read nếu xuất hiện. Ghi lại số lần, tổng thời gian và average latency.

### Bài 5 — Row lock

Thực hiện lab hai session ở mục 16. Tìm waiter và blocker, ghi SQL_ID, SID, SERIAL# và event. Giải thích vì sao waiter không thể tiếp tục.

### Bài 6 — Commit

So sánh workload commit từng row với batch commit trong schema lab. Quan sát số lần log file sync, elapsed time và transaction semantics.

### Bài 7 — Idle và non-idle

Tìm session có SQL*Net message from client. Giải thích vì sao không cộng event này vào database bottleneck analysis.

### Bài 8 — Wait class

Lấy snapshot V$SYSTEM_WAIT_CLASS hai thời điểm, tính delta cho từng class. Xếp hạng class theo wait AAS và nêu event cần điều tra tiếp.

### Bài 9 — Session tracing

Gắn MODULE/ACTION, bật SQL trace cho session lab, tắt trace sau khi chạy. Dùng TKPROF đọc parse/execute/fetch, CPU, elapsed và waits.

### Bài 10 — Incident report

Tạo báo cáo ngắn gồm DB time, DB CPU, AAS, top wait class/event, SQL liên quan, giả thuyết và bằng chứng cần thu thập thêm. Phân biệt điều đã chứng minh với điều mới chỉ là giả thuyết.

## 20. Dọn dẹp và khôi phục môi trường

- Rollback transaction còn mở trong các session lab.
- Drop đúng bảng LAB_WAIT_LOCK và các object do bạn tạo.
- Tắt SQL trace sau khi thu thập.
- Khôi phục STATISTICS_LEVEL nếu đã thay đổi.
- Tắt instrumentation không còn cần thiết.
- Bảo vệ/xóa trace file theo chính sách.
- Không flush buffer cache, kill session hoặc thay đổi Resource Manager trên database dùng chung để tạo lại tình huống lab.

## Tổng kết

Wait event mô tả một lần session phải chờ; wait class nhóm các event; DB time là tổng thời gian foreground sessions dành cho database calls, bao gồm DB CPU và non-idle waits. DB time có thể lớn hơn elapsed wall-clock vì nhiều session hoạt động đồng thời. AAS được tính bằng delta DB time chia elapsed time; DB CPU AAS cho biết phần CPU trung bình, còn chênh lệch AAS với DB CPU AAS ước lượng phần active wait.

Muốn phân biệt CPU-bound và wait-bound, hãy lấy snapshot cùng scope, tính delta, loại idle waits và đối chiếu DB time, DB CPU, wait class, host CPU/I/O/network. Sau đó đi từ wait class tới event, session, SQL_ID và execution plan. log file sync, row lock, User I/O, concurrency, network và RAC cluster waits có nguyên nhân khác nhau; không sửa cấu hình chỉ dựa vào tên event. Dùng V$ views cho quan sát hiện tại/counter, SQL trace cho session cụ thể và ASH/AWR khi môi trường có quyền/license phù hợp. Luôn xác nhận bằng workload và latency trước/sau thay đổi.

## Tài liệu Oracle tham khảo

- [Oracle Database Performance Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — performance methodology, wait events, time model và tuning.
- [Oracle Database Reference — V$SYS_TIME_MODEL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html) — DB time, DB CPU và time model statistics.
- [Oracle Database Reference — V$SESS_TIME_MODEL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESS_TIME_MODEL.html) — time model theo session.
- [Oracle Database Reference — V$SYSTEM_WAIT_CLASS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_WAIT_CLASS.html) — wait totals theo wait class.
- [Oracle Database Reference — V$SYSTEM_EVENT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html) — wait counters theo event.
- [Oracle Database Reference — V$EVENT_NAME (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-EVENT_NAME.html) — tên event, tham số và wait class.
- [Oracle Database Reference — V$SESSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html) — session state, current wait và blocking session.
- [Oracle Database Reference — V$ACTIVE_SESSION_HISTORY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ACTIVE_SESSION_HISTORY.html) — active session samples; lưu ý Diagnostics Pack.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_MONITOR (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html) — SQL trace theo session/service/module/client identifier.
- [Oracle Database Licensing Information User Manual (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — điều kiện license của Diagnostics Pack và Tuning Pack.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu Performance Tuning Guide và Data Dictionary Reference đúng phiên bản, đặc biệt định nghĩa time model, wait class/event, multitenant scope, ASH/AWR và điều kiện license.
