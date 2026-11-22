# AWR, ASH, ADDM và kiểm tra quyền sử dụng Diagnostics Pack

Oracle Database có nhiều công cụ giúp DBA và developer tìm hiểu hiệu năng hệ thống. Ba thành phần thường được dùng cùng nhau là **Automatic Workload Repository (AWR)**, **Active Session History (ASH)** và **Automatic Database Diagnostic Monitor (ADDM)**. Chúng giúp trả lời các câu hỏi khác nhau:

- AWR ghi nhận và lưu trữ các số liệu workload theo những khoảng thời gian để so sánh hiệu năng.
- ASH lấy mẫu các session đang hoạt động để chỉ ra session, SQL, wait event và đối tượng liên quan đến thời điểm có vấn đề.
- ADDM phân tích dữ liệu workload trong AWR và đưa ra các phát hiện cùng khuyến nghị điều tra.

Các tính năng này thuộc **Oracle Diagnostics Pack**. Trước khi truy cập AWR, ASH hoặc ADDM, cần xác minh quyền sử dụng Diagnostics Pack theo hợp đồng và điều kiện triển khai thực tế. Tham số CONTROL_MANAGEMENT_PACK_ACCESS cho biết các tính năng management pack được bật hay tắt trong database; giá trị tham số **không phải bằng chứng rằng tổ chức đã mua hoặc được cấp quyền sử dụng license**.

## 1. AWR, ASH và ADDM giải quyết vấn đề gì?

Khi người dùng báo cáo hệ thống chậm, cần biết vấn đề xuất hiện lúc nào, session nào đang hoạt động, SQL nào tiêu tốn tài nguyên và bottleneck nằm ở CPU, I/O, concurrency hay một nguyên nhân khác. AWR, ASH và ADDM bổ sung cho nhau:

| Công cụ | Dữ liệu chính | Câu hỏi thường trả lời |
|---|---|---|
| AWR | Thống kê workload và snapshot theo thời gian | Database đã làm bao nhiêu công việc trong khoảng thời gian có vấn đề? |
| ASH | Mẫu các session đang hoạt động | Session/SQL nào đang tiêu tốn thời gian và đang chờ điều gì? |
| ADDM | Phân tích workload dựa trên AWR | Oracle nhận diện bottleneck nào và đề xuất điều tra hoặc cải thiện gì? |

Có thể hình dung luồng phân tích:

~~~text
Hoạt động của database
        |
        v
  AWR snapshots ---------> Dữ liệu lịch sử theo khoảng thời gian
        |                               |
        |                               v
        |                         ADDM analysis
        |                               |
        v                               v
  ASH samples                    Findings / recommendations
        |
        v
 Session, SQL, wait event
        |
        v
 Xác định thời điểm và đối tượng cần điều tra
~~~

AWR giúp đặt vấn đề trong bối cảnh workload tổng thể. ASH giúp khoanh vùng hoạt động của session trong một khoảng thời gian ngắn. ADDM cung cấp phân tích và hướng điều tra. Không công cụ nào tự thay thế việc đọc SQL, execution plan, dữ liệu ứng dụng và cấu hình hệ thống.

## 2. Automatic Workload Repository (AWR)

AWR là kho lưu trữ các thống kê hiệu năng của Oracle Database. Oracle định kỳ thu thập các số liệu về instance, session, wait event, SQL, I/O, segment và một số thành phần workload khác, rồi lưu các snapshot để phân tích lịch sử.

Một snapshot là tập dữ liệu thống kê tại một thời điểm. Khi so sánh hai snapshot, AWR có thể tính delta của các bộ đếm tích lũy trong khoảng thời gian giữa chúng. Nhờ đó, DBA có thể xem workload thay đổi như thế nào trong một khoảng thời gian cụ thể.

### Những loại thông tin trong AWR

Tùy phiên bản và cấu hình, AWR report có thể chứa:

- Load Profile: số giao dịch, user calls, parses, executions, logical reads và các chỉ số tính theo giây hoặc theo transaction.
- Instance Efficiency Percentages: một số tỷ lệ hiệu quả hoạt động của instance.
- Top Timed Events: các wait event và thành phần thời gian chiếm tỷ trọng lớn.
- Host CPU và Instance CPU: mức sử dụng CPU của host và database.
- I/O Statistics: hoạt động đọc/ghi và thời gian liên quan đến I/O.
- SQL Statistics: các SQL tiêu tốn elapsed time, CPU, buffer gets, disk reads hoặc số lần thực thi.
- Segment Statistics: các segment có hoạt động đáng chú ý.
- Memory Statistics: thông tin liên quan đến PGA, SGA và workarea.
- Wait Statistics: các loại chờ của session và instance.

Các mục xuất hiện phụ thuộc release, workload, quyền truy cập và loại report. Không nên giả định mọi report đều có đủ mọi mục.

### Snapshot và khoảng thời gian

Oracle thường tự động tạo AWR snapshot định kỳ thông qua background process. Khoảng snapshot và retention có thể cấu hình; giá trị mặc định có thể khác theo phiên bản hoặc môi trường triển khai. Không nên coi một giờ hoặc tám ngày là giới hạn cố định cho mọi database.

Khi có quyền và license phù hợp, thông tin điều khiển AWR có thể được xem bằng:

~~~sql
SELECT snap_interval,
       retention,
       topnsql
  FROM dba_hist_wr_control;
~~~

View DBA_HIST_WR_CONTROL và các dữ liệu AWR là một phần của chức năng Diagnostics Pack. Chỉ truy vấn trong môi trường đã xác minh quyền sử dụng tương ứng.

Snapshot không phải bản sao đầy đủ của mọi thao tác SQL. AWR lưu các thống kê và thông tin lịch sử được chọn, được tổng hợp hoặc lấy mẫu. Vì vậy, một truy vấn ngắn xảy ra giữa hai snapshot có thể không được thể hiện đầy đủ như khi xem trace chi tiết.

### AWR report

AWR report so sánh thống kê giữa snapshot bắt đầu và snapshot kết thúc. Report giúp xác định:

- Khoảng thời gian database chịu tải cao.
- CPU time và DB time thay đổi thế nào.
- Wait event nào chiếm nhiều thời gian.
- SQL nào có tổng elapsed time hoặc CPU cao.
- Logical reads, physical reads và I/O tăng bất thường.
- Segment hoặc hoạt động nào có mức truy cập đáng chú ý.

Một AWR report không chỉ là danh sách SQL chậm. Nó mô tả workload của cả instance trong một khoảng thời gian, nên cần chọn đúng snapshot tương ứng với thời điểm người dùng gặp vấn đề.

## 3. DB Time và cách đọc workload trong AWR

DB Time là tổng thời gian hoạt động của các foreground session, bao gồm thời gian chạy trên CPU và thời gian chờ các non-idle wait event. DB Time cộng dồn qua các session, vì vậy có thể lớn hơn thời gian đồng hồ thực tế của khoảng đo.

Ví dụ, trong một phút có 20 session cùng hoạt động trung bình 30 giây, tổng DB Time có thể đạt khoảng 600 giây. Điều này không có nghĩa một phút đã trôi qua 10 phút; nó phản ánh tổng thời gian hoạt động của nhiều session.

DB CPU là phần DB Time mà foreground session thực sự sử dụng CPU. Phần còn lại có thể liên quan đến I/O wait, concurrency wait, network hoặc các wait event khác.

Khi đọc AWR:

1. Xác định DB Time và DB CPU trong khoảng đo.
2. So sánh với thời gian thực và số transaction để hiểu cường độ workload.
3. Xem Top Timed Events để nhận diện loại chờ chiếm tỷ trọng lớn.
4. Kiểm tra SQL Statistics để biết SQL nào đóng góp nhiều DB Time hoặc CPU.
5. Đối chiếu Host CPU để phân biệt CPU database với CPU toàn host.

Không nên chỉ nhìn một tỷ lệ hoặc một wait event rồi kết luận nguyên nhân. Ví dụ, wait event liên quan đến I/O có thể là triệu chứng của SQL đọc quá nhiều block, storage chậm, hoặc cả hai.

## 4. Cách tạo và đọc AWR report

Trong SQL*Plus hoặc SQLcl, Oracle cung cấp script tạo AWR report trong thư mục quản trị của Oracle Home. Trên môi trường đã có quyền Diagnostics Pack, có thể chạy:

~~~sql
@?/rdbms/admin/awrrpt.sql
~~~

Script thường yêu cầu chọn định dạng report, DBID, instance number, snapshot bắt đầu và snapshot kết thúc. Hãy chọn hai snapshot bao phủ đúng khoảng thời gian cần phân tích.

Các điểm cần chú ý khi tạo report:

- Chọn cùng một database và instance nếu đang tạo instance-level report.
- Chọn snapshot bắt đầu trước khi sự cố xảy ra và snapshot kết thúc sau khi sự cố kết thúc.
- Tránh khoảng đo quá dài nếu mục tiêu là tìm một spike ngắn; khoảng quá dài có thể làm loãng dấu hiệu.
- Tránh khoảng đo quá ngắn nếu workload ít hoặc số liệu delta chưa đủ ổn định.
- Ghi lại múi giờ và thời điểm thực tế mà người dùng báo cáo.

Trong môi trường RAC, cần phân biệt report theo instance và report toàn cluster. Oracle có script báo cáo global tương ứng; chọn loại report theo phạm vi cần phân tích và phiên bản đang dùng.

### Một số khu vực nên đọc trước

| Khu vực trong AWR | Điều cần tìm |
|---|---|
| Report Summary | Thời gian đo, DB Time, DB CPU và thông tin instance |
| Load Profile | Số transaction, user calls, executions, logical reads theo workload |
| Top Timed Events | Wait event và thành phần DB Time nổi bật |
| SQL ordered by Elapsed Time | SQL đóng góp nhiều elapsed time |
| SQL ordered by CPU Time | SQL tiêu tốn CPU lớn |
| SQL ordered by Gets/Reads | SQL đọc nhiều buffer hoặc block từ storage |
| I/O Statistics | Mức độ và độ trễ I/O |
| Instance Activity Stats | Các bộ đếm hoạt động của instance |
| Segment Statistics | Segment có hoạt động đọc/ghi đáng chú ý |

Một SQL có elapsed time lớn chưa chắc là nguyên nhân gốc. Nó có thể chạy nhiều lần với thời gian mỗi lần nhỏ, hoặc bị chờ do contention. Hãy xem executions, elapsed time per execution, CPU, buffer gets và wait profile cùng nhau.

## 5. Active Session History (ASH)

ASH là cơ chế lấy mẫu các session đang hoạt động. Một session được xem là active khi đang chạy trên CPU hoặc đang chờ một non-idle wait event. ASH ghi nhận thông tin tại các thời điểm lấy mẫu để DBA có thể xem hoạt động trong khoảng thời gian ngắn.

Các trường thường dùng trong ASH gồm:

- SAMPLE_TIME: thời điểm lấy mẫu.
- SESSION_ID và SESSION_SERIAL#: định danh session trong mẫu.
- SQL_ID và SQL_EXEC_ID: SQL và lần thực thi liên quan khi có.
- SESSION_STATE: trạng thái ON CPU hoặc WAITING.
- EVENT và WAIT_CLASS: wait event và nhóm chờ.
- MODULE, ACTION, PROGRAM, MACHINE: thông tin nhận diện ứng dụng hoặc client.
- BLOCKING_SESSION: session gây blocking nếu có.
- CURRENT_OBJ#: object đang liên quan đến hoạt động khi có.
- INSTANCE_NUMBER: instance trong môi trường RAC.

ASH giúp trả lời câu hỏi: trong khoảng thời gian 10 phút mà ứng dụng chậm, session nào hoạt động, chạy SQL nào, đang chờ gì và có bị chặn hay không?

### In-memory ASH và historical ASH

Oracle cung cấp hai dạng dữ liệu thường gặp:

- V$ACTIVE_SESSION_HISTORY: các mẫu ASH còn trong vùng nhớ của instance. Đây là dữ liệu ngắn hạn và có thể bị ghi đè khi buffer quay vòng.
- DBA_HIST_ACTIVE_SESS_HISTORY: dữ liệu ASH được lưu lịch sử trong AWR theo cơ chế lấy mẫu/ghi nhận có chọn lọc. Nó thường thưa hơn dữ liệu in-memory và phụ thuộc retention của AWR.

Không nên giả định dữ liệu lịch sử có đủ mọi mẫu của V$ACTIVE_SESSION_HISTORY. Khi điều tra sự cố cũ, độ chi tiết có thể thấp hơn dữ liệu in-memory tại thời điểm sự cố.

ASH thuộc Diagnostics Pack. Việc truy vấn V$ACTIVE_SESSION_HISTORY hoặc DBA_HIST_ACTIVE_SESS_HISTORY để phân tích workload cần được kiểm tra quyền sử dụng theo license và điều khoản áp dụng.

### Đếm mẫu ASH theo SQL và wait event

Ví dụ sau minh họa cách nhóm các mẫu in-memory theo SQL và wait event trong 10 phút gần nhất:

~~~sql
SELECT sql_id,
       session_state,
       wait_class,
       event,
       COUNT(*) AS sample_count
  FROM v$active_session_history
 WHERE sample_time >= SYSTIMESTAMP - INTERVAL '10' MINUTE
   AND session_type = 'FOREGROUND'
 GROUP BY sql_id,
          session_state,
          wait_class,
          event
 ORDER BY sample_count DESC;
~~~

Kết quả giúp nhận diện SQL và loại hoạt động xuất hiện nhiều trong các mẫu. COUNT(*) là số mẫu, không phải số lần thực thi SQL và cũng không phải thời gian chính xác tuyệt đối. ASH là dữ liệu lấy mẫu nên các kết luận phải được xem cùng AWR, SQL statistics và dữ liệu ứng dụng.

### Xem các session đang hoạt động

~~~sql
SELECT sample_time,
       session_id,
       session_serial#,
       sql_id,
       session_state,
       wait_class,
       event,
       module,
       action,
       blocking_session
  FROM v$active_session_history
 WHERE sample_time >= SYSTIMESTAMP - INTERVAL '5' MINUTE
 ORDER BY sample_time DESC;
~~~

Truy vấn có thể giúp quan sát session nào đang ON CPU, session nào WAITING và thông tin blocking nếu có. Nếu dữ liệu đã cũ hơn vùng nhớ ASH, cần xem historical ASH trong AWR nếu có quyền và license.

### ASH report

Oracle cung cấp script tạo ASH report:

~~~sql
@?/rdbms/admin/ashrpt.sql
~~~

Script thường yêu cầu chọn report type, khoảng thời gian và các thông tin liên quan. ASH report tập trung vào hoạt động session được lấy mẫu, nên phù hợp để điều tra spike ngắn, wait event, SQL và module trong khoảng thời gian hẹp.

Trong RAC, có thể cần report global hoặc lựa chọn instance phù hợp. Chọn report theo phạm vi sự cố thay vì mặc định chỉ xem một instance.

## 6. Automatic Database Diagnostic Monitor (ADDM)

ADDM là công cụ phân tích hiệu năng tự động dựa trên dữ liệu AWR. ADDM xem workload trong một khoảng snapshot, tìm các vấn đề có ảnh hưởng đáng kể đến DB Time và đưa ra findings cùng recommendations.

ADDM có thể nhận diện các nhóm vấn đề như:

- CPU bottleneck.
- I/O bottleneck.
- SQL tiêu tốn nhiều DB Time.
- Concurrency hoặc contention.
- Thiếu tài nguyên hoặc áp lực bộ nhớ.
- Một số vấn đề liên quan đến cấu hình và hoạt động của instance.

ADDM thường được chạy tự động sau các AWR snapshot theo cơ chế của Oracle. DBA cũng có thể xem báo cáo ADDM cho một khoảng snapshot bằng script quản trị tương ứng:

~~~sql
@?/rdbms/admin/addmrpt.sql
~~~

Script sẽ yêu cầu các thông tin cần thiết để chọn khoảng phân tích. Cần dùng trong môi trường đã xác minh quyền Diagnostics Pack.

### Findings và recommendations

Một finding thường mô tả:

- Tên hoặc loại vấn đề.
- Mức ảnh hưởng ước tính đến DB Time.
- Các nguyên nhân hoặc đối tượng liên quan.
- SQL, wait event hoặc thành phần hệ thống có liên quan.
- Recommendation để điều tra hoặc cải thiện.

Recommendation của ADDM là hướng dẫn phân tích, không phải lệnh phải thực hiện ngay. Ví dụ, ADDM có thể đề xuất xem xét SQL tuning, điều chỉnh cấu hình hoặc xử lý I/O. Trước khi thay đổi, DBA cần xác nhận bằng execution plan, runtime statistics, workload và yêu cầu nghiệp vụ.

ADDM dựa trên dữ liệu trong khoảng phân tích. Nếu chọn snapshot không đúng thời điểm, workload thay đổi mạnh hoặc sự cố quá ngắn, finding có thể không phản ánh vấn đề mà người dùng gặp.

## 7. Kết hợp AWR, ASH và ADDM trong một cuộc điều tra

Một quy trình thực tế có thể triển khai theo thứ tự:

1. Xác định thời gian bắt đầu/kết thúc sự cố từ log ứng dụng, monitoring hoặc phản hồi người dùng.
2. Chọn AWR snapshots bao phủ khoảng thời gian đó.
3. Đọc AWR để xác định workload, DB Time, CPU, wait event và SQL nổi bật.
4. Dùng ASH để khoanh vùng session, SQL, module, wait event và blocking trong thời điểm cụ thể.
5. Đọc ADDM findings để biết Oracle đã nhận diện bottleneck nào và các recommendation liên quan.
6. Lấy SQL_ID đáng chú ý, xem execution plan và runtime statistics bằng công cụ phù hợp.
7. Đối chiếu với log ứng dụng, thay đổi cấu hình, deploy và hoạt động hạ tầng.
8. Đề xuất một thay đổi có giả thuyết rõ ràng, thử trong môi trường phù hợp và đo lại.

Ví dụ, AWR cho thấy DB Time tăng mạnh và wait event liên quan đến I/O chiếm tỷ trọng lớn. ASH chỉ ra một SQL_ID xuất hiện trong nhiều mẫu WAITING trên sự kiện đọc dữ liệu. ADDM cũng chỉ ra SQL này có đóng góp đáng kể. Bước tiếp theo là lấy SQL text, execution plan, A-Rows, Buffers, Reads và kiểm tra liệu truy vấn đang đọc quá nhiều dữ liệu hay storage thực sự chậm.

Nếu AWR cho thấy DB CPU chiếm phần lớn DB Time, ASH có thể giúp xác định SQL nào thường ở trạng thái ON CPU. Khi đó, cần xem CPU time, số lần thực thi, plan, phép tính, join và lượng hàng xử lý.

Nếu ASH cho thấy session WAITING với blocking_session, cần điều tra transaction và khóa liên quan. AWR/ADDM cung cấp bối cảnh, nhưng việc giải quyết blocking cần xem session, SQL và transaction cụ thể.

## 8. Phân biệt Diagnostics Pack và Tuning Pack

Oracle chia các tính năng quản trị nâng cao thành các management pack. Với phạm vi bài học này, cần nhớ:

| Thành phần/tính năng | Pack liên quan |
|---|---|
| AWR và AWR reports | Diagnostics Pack |
| ASH và ASH reports | Diagnostics Pack |
| ADDM | Diagnostics Pack |
| SQL Tuning Advisor | Tuning Pack |
| SQL Access Advisor | Tuning Pack |
| Một số khả năng SQL Monitoring nâng cao | Tuning Pack theo điều kiện áp dụng |

Tuning Pack có quan hệ phụ thuộc với Diagnostics Pack theo chính sách cấp phép của Oracle. Không nên suy luận rằng có quyền Diagnostics Pack thì tự động có quyền Tuning Pack.

Danh sách tính năng, quyền sử dụng, edition và điều kiện cấp phép có thể thay đổi theo phiên bản, hình thức triển khai và hợp đồng. Khi cần xác nhận chính thức, phải đối chiếu tài liệu cấp phép hiện hành và hợp đồng cụ thể của tổ chức.

## 9. Kiểm tra CONTROL_MANAGEMENT_PACK_ACCESS

Oracle cung cấp tham số khởi tạo CONTROL_MANAGEMENT_PACK_ACCESS để kiểm soát việc bật các tính năng management pack trong database. Có thể xem giá trị hiện tại bằng SQL*Plus:

~~~sql
SHOW PARAMETER control_management_pack_access;
~~~

Hoặc truy vấn:

~~~sql
SELECT name,
       value,
       issys_modifiable
  FROM v$parameter
 WHERE name = 'control_management_pack_access';
~~~

Các giá trị thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| NONE | Tắt quyền truy cập các tính năng Diagnostics Pack và Tuning Pack qua cơ chế này |
| DIAGNOSTIC | Bật các tính năng Diagnostics Pack |
| DIAGNOSTIC+TUNING | Bật các tính năng Diagnostics Pack và Tuning Pack |

Tên giá trị thường được Oracle hiển thị dưới dạng chữ hoa. Giá trị tham số chỉ cho biết cấu hình cho phép database expose/use các tính năng pack; nó không xác nhận license đã được mua.

### Kiểm tra quyền sử dụng theo hai lớp

Để kết luận có được dùng AWR, ASH và ADDM hay không, cần tách hai câu hỏi:

1. **Cấu hình database có bật tính năng không?** Kiểm tra CONTROL_MANAGEMENT_PACK_ACCESS.
2. **Tổ chức có quyền license để sử dụng tính năng không?** Kiểm tra hợp đồng, đơn đặt hàng, license metric, edition, deployment model và tài liệu cấp phép áp dụng.

Hai câu hỏi này độc lập. Một database có thể đặt DIAGNOSTIC+TUNING nhưng tổ chức chưa có quyền sử dụng pack. Ngược lại, tổ chức có quyền sử dụng nhưng database có thể đang cấu hình NONE.

Không được coi việc truy vấn thành công, menu OEM hiển thị hoặc script chạy được là bằng chứng cấp phép.

### Nếu không có quyền Diagnostics Pack

Nếu tổ chức không có quyền sử dụng Diagnostics Pack, không sử dụng AWR, ASH hoặc ADDM chỉ vì các view và script đang tồn tại. DBA/licensing owner cần xác nhận chính sách áp dụng và cấu hình CONTROL_MANAGEMENT_PACK_ACCESS phù hợp, thường là NONE nếu không được phép dùng cả Diagnostics Pack và Tuning Pack.

Việc thay đổi tham số cần do DBA có thẩm quyền thực hiện theo quy trình thay đổi của môi trường. Không tự ý thay đổi tham số trên production chỉ để thử một câu truy vấn.

## 10. Quy trình xác minh license trước khi chạy report

Trước khi tạo AWR/ASH/ADDM report, nên thực hiện:

1. Xác định Oracle Database release, edition và nền tảng triển khai.
2. Xem giá trị CONTROL_MANAGEMENT_PACK_ACCESS.
3. Xác định hợp đồng và entitlement của tổ chức cho Diagnostics Pack.
4. Kiểm tra các điều khoản đặc thù nếu database chạy trên cloud hoặc dịch vụ được quản lý.
5. Đối chiếu Oracle Licensing Information User Manual đúng phiên bản và hợp đồng đang áp dụng.
6. Xác nhận với DBA, licensing administrator hoặc bộ phận procurement khi còn điểm chưa rõ.
7. Chỉ sử dụng AWR, ASH, ADDM sau khi đã xác nhận quyền phù hợp.

Không nên dùng một truy vấn trong database để tự kết luận tổ chức có license hay không. Database không phải nguồn đầy đủ về hợp đồng thương mại, metric, quyền sử dụng cloud hoặc các ngoại lệ đã thỏa thuận.

### Ví dụ bảng ghi nhận trước khi sử dụng

| Nội dung | Giá trị cần xác nhận | Nguồn |
|---|---|---|
| Database release | Phiên bản và Release Update | Database inventory/DBA |
| Edition | Enterprise Edition hoặc edition đang triển khai | Database inventory và hợp đồng |
| Deployment | On-premises, OCI hoặc dịch vụ khác | Kiến trúc triển khai/hợp đồng |
| Pack access parameter | NONE / DIAGNOSTIC / DIAGNOSTIC+TUNING | V$PARAMETER hoặc SHOW PARAMETER |
| Diagnostics Pack entitlement | Có/không/phạm vi cụ thể | License agreement, order documents |
| Tuning Pack entitlement | Có/không/phạm vi cụ thể | License agreement, order documents |
| Phê duyệt sử dụng | Người/bộ phận chịu trách nhiệm xác nhận | DBA/licensing owner |

Đây là thông tin quản trị cần được xác minh; không thay thế tài liệu pháp lý hoặc ý kiến của bộ phận licensing.

## 11. Những truy vấn cần thận trọng về license

Các view và script dưới đây liên quan đến tính năng Diagnostics Pack:

- DBA_HIST_* và các report AWR.
- V$ACTIVE_SESSION_HISTORY và DBA_HIST_ACTIVE_SESS_HISTORY.
- Các report và phân tích ADDM.
- Một số công cụ hoặc trang OEM dựa trên dữ liệu Diagnostics Pack.

Nếu chưa xác minh quyền, không chạy các truy vấn này chỉ để thử xem dữ liệu có trả về hay không. Việc view tồn tại trong data dictionary hoặc tài khoản có quyền SELECT không chứng minh quyền license.

Các truy vấn thông tin cấu hình như V$PARAMETER có thể được dùng để đọc CONTROL_MANAGEMENT_PACK_ACCESS. Tuy nhiên, đọc tham số vẫn không thay thế bước kiểm tra hợp đồng.

## 12. Các công cụ thay thế và dữ liệu không thuộc Diagnostics Pack

Nếu chưa có Diagnostics Pack, vẫn có các phương pháp điều tra hiệu năng khác, tùy phiên bản và quyền truy cập:

- EXPLAIN PLAN và DBMS_XPLAN.DISPLAY để xem estimated execution plan.
- SQL trace và TKPROF theo quyền và quy trình được phép.
- V$SESSION để xem trạng thái session hiện tại, SQL_ID và thông tin wait đang diễn ra.
- V$SQL để xem các thống kê cursor hiện có như executions, elapsed time, CPU time, buffer gets và disk reads, theo quyền truy cập và điều khoản áp dụng.
- AWR/ASH/ADDM không được xem là phương án thay thế miễn phí; đây là các tính năng Diagnostics Pack.
- Monitoring ở tầng hệ điều hành, storage, ứng dụng và middleware để xác định CPU, memory, disk latency, network và request latency.

Quyền sử dụng từng view, package hoặc công cụ cần được kiểm tra theo phiên bản và chính sách Oracle áp dụng. Không nên giả định mọi view V$ đều miễn phí hoặc mọi công cụ ngoài database đều thay thế được dữ liệu lịch sử của AWR/ASH.

### EXPLAIN PLAN

EXPLAIN PLAN có thể tạo kế hoạch ước lượng:

~~~sql
EXPLAIN PLAN FOR
SELECT department_id,
       COUNT(*)
  FROM employees
 GROUP BY department_id;

SELECT *
  FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Kế hoạch này không thực thi câu SQL và không cung cấp A-Rows của lần chạy. Nó hữu ích để xem access path và join method dự kiến, nhưng không thay thế runtime statistics.

### SQL trace và TKPROF

SQL trace có thể ghi lại thông tin parse, execute, fetch, CPU, elapsed time, reads và waits ở mức session hoặc call theo cách cấu hình. TKPROF định dạng trace thành báo cáo dễ đọc hơn. Cần dùng đúng quyền, bảo vệ file trace vì có thể chứa SQL text và dữ liệu nhạy cảm, đồng thời kiểm soát overhead và dung lượng.

## 13. Các sai lầm khi đọc AWR, ASH và ADDM

**Chọn sai khoảng snapshot:** report có thể bao gồm cả giờ workload bình thường và giờ có sự cố, làm mờ nguyên nhân. Hãy đối chiếu thời điểm chính xác.

**Coi DB Time là thời gian đồng hồ:** DB Time cộng dồn qua session nên có thể lớn hơn elapsed time của khoảng đo.

**Coi số mẫu ASH là số lần chạy SQL:** ASH là dữ liệu lấy mẫu session đang hoạt động, không phải log đầy đủ mọi execution.

**Kết luận từ một wait event:** wait event lớn có thể là triệu chứng của SQL đọc quá nhiều dữ liệu, contention hoặc hạ tầng. Cần xem SQL và plan liên quan.

**Xem ADDM recommendation như lệnh phải chạy:** recommendation cần được xác nhận bằng workload và thử nghiệm.

**So sánh hai khoảng có workload khác nhau:** lượng transaction, số người dùng, batch và dữ liệu khác nhau có thể làm delta không thể so sánh trực tiếp.

**Dùng AWR để kết luận mọi vấn đề ứng dụng:** AWR mô tả database workload; latency ở application, network hoặc middleware có thể cần công cụ khác.

**Nhầm tham số pack access với license:** DIAGNOSTIC+TUNING không đồng nghĩa tổ chức đã mua các pack.

**Dùng thành công script làm bằng chứng hợp lệ:** script có thể chạy được do cấu hình và quyền database, nhưng quyền thương mại vẫn phải xác minh riêng.

## 14. Ví dụ điều tra một sự cố chậm

Giả sử người dùng báo cáo thao tác tạo báo cáo chậm trong khoảng 14:00 đến 14:20:

**Bước 1: Xác định thời gian.** Ghi lại múi giờ, database instance, module và thời điểm request bắt đầu/kết thúc. Kiểm tra deploy hoặc batch job trùng thời điểm.

**Bước 2: Xác minh Diagnostics Pack.** Kiểm tra CONTROL_MANAGEMENT_PACK_ACCESS và xác nhận entitlement với licensing owner trước khi mở AWR/ASH/ADDM.

**Bước 3: Chọn AWR snapshots.** Chọn snapshot bao phủ 14:00–14:20, xem report để xác định DB Time, DB CPU, Top Timed Events và SQL nổi bật.

**Bước 4: Khoanh vùng bằng ASH.** Nếu một wait class chiếm ưu thế, lọc ASH theo thời điểm và xem SQL_ID, session, module, event, blocking_session. Nhớ rằng dữ liệu là mẫu và có thể không giữ mọi sự kiện ngắn.

**Bước 5: Đọc ADDM.** Xem findings cho khoảng snapshot tương ứng và đối chiếu các SQL hoặc wait event mà ADDM nêu ra.

**Bước 6: Kiểm tra SQL.** Lấy SQL text, execution plan, runtime row-source statistics bằng công cụ phù hợp và phân tích cardinality, I/O, join, filter.

**Bước 7: Kiểm tra ngoài database.** Đối chiếu application logs, host CPU, memory, storage latency và network.

**Bước 8: Thử giải pháp.** Thay đổi một yếu tố trong môi trường phù hợp, đo lại cùng workload và xác nhận không gây ảnh hưởng xấu đến các truy vấn khác.

Nếu không có quyền Diagnostics Pack, bỏ qua các bước sử dụng AWR/ASH/ADDM và dùng các phương pháp thay thế được phép như execution plan, SQL trace/TKPROF, thông tin session/cursor và monitoring ở tầng ứng dụng/hệ điều hành.

## 15. Checklist vận hành và bảo vệ dữ liệu

Khi tạo hoặc chia sẻ báo cáo hiệu năng:

- Chọn đúng database, instance và khoảng snapshot.
- Ghi rõ múi giờ và điều kiện workload.
- Giữ SQL_ID, child number và thời điểm chạy để đối chiếu.
- Không chia sẻ report chứa literal, tên schema, object hoặc SQL text nhạy cảm khi chưa xử lý phù hợp.
- Lưu report theo chính sách retention và quyền truy cập nội bộ.
- Không thay đổi tham số instance-wide nếu chưa có phê duyệt của DBA.
- Không chạy script AWR/ASH/ADDM trước khi xác minh Diagnostics Pack.
- Tách biệt kết luận kỹ thuật với kết luận về quyền license.

## 16. Kết luận

AWR lưu thống kê workload theo snapshot, ASH lấy mẫu các session đang hoạt động và ADDM phân tích dữ liệu AWR để đưa ra findings cùng recommendations. Kết hợp ba công cụ giúp DBA xác định khoảng thời gian có vấn đề, SQL và session liên quan, wait event nổi bật và hướng điều tra tiếp theo.

AWR, ASH và ADDM thuộc Oracle Diagnostics Pack. Trước khi sử dụng, hãy kiểm tra CONTROL_MANAGEMENT_PACK_ACCESS để biết cấu hình database, sau đó xác minh quyền sử dụng thực tế qua hợp đồng, license metric, edition, nền tảng triển khai và tài liệu Oracle áp dụng. Tham số được bật hoặc script chạy thành công không chứng minh đã có license. Nếu chưa có quyền phù hợp, hãy dùng các phương pháp chẩn đoán khác được phép và nhờ DBA/licensing owner xác nhận trước khi truy cập tính năng thuộc pack.
