# Chọn khoảng đo, tính chênh lệch bộ đếm và tránh diễn giải sai số tổng

Khi theo dõi hiệu năng Oracle Database, nhiều chỉ số được lưu dưới dạng **bộ đếm tích lũy**. Giá trị trong một view như V$SYSSTAT thường cho biết tổng số lần hoặc tổng lượng đã phát sinh kể từ một mốc reset, chẳng hạn thời điểm instance khởi động. Con số tại một thời điểm không tự cho biết hệ thống đang hoạt động nhanh hay chậm trong vài phút vừa qua.

Để đo một khoảng thời gian, cần chụp giá trị ở hai thời điểm, xác nhận hai mẫu thuộc cùng đối tượng và cùng vòng đời, rồi tính:

\[
\Delta C = C_{\text{cuối}} - C_{\text{đầu}}
\]

Nếu cần tốc độ phát sinh:

\[
\text{Rate} = \frac{\Delta C}{\text{Thời gian thực tế giữa hai mẫu}}
\]

Công thức đơn giản này chỉ đúng khi bộ đếm không bị reset, đối tượng đo không bị thay thế và hai mẫu có cùng phạm vi. Nếu instance restart, session kết thúc, cursor bị nạp lại hoặc bộ đếm giảm, phép trừ có thể không còn ý nghĩa.

Bài học này tập trung vào cách chọn khoảng đo, nhận diện vòng đời của bộ đếm, tính delta/rate/ratio, đọc số liệu theo instance, session và SQL cursor, cũng như tránh các kết luận sai khi cộng tổng hoặc so sánh những khoảng thời gian khác nhau.

## 1. Phân biệt bộ đếm, số đo tức thời và tỷ lệ

Trước khi tính toán, phải biết cột đang đọc biểu diễn loại dữ liệu nào. Không phải mọi cột tên VALUE hoặc COUNT đều là bộ đếm tích lũy.

### 1.1. Bộ đếm tích lũy (cumulative counter)

Bộ đếm tăng khi một sự kiện xảy ra hoặc một lượng công việc được hoàn thành. Ví dụ:

- Số lần thực thi SQL.
- Số lần commit.
- Số block được đọc logic.
- Số block được đọc vật lý.
- Số byte redo được tạo.
- Tổng thời gian CPU hoặc thời gian chờ đã tích lũy.
- Số lần parse.

Ví dụ, nếu V$SYSSTAT cho thấy statistic có tên redo size là 8.000.000.000 tại thời điểm hiện tại, đó là giá trị tích lũy theo phạm vi của statistic và instance. Nó không có nghĩa database tạo 8 GB redo trong giây hiện tại.

Muốn biết lượng redo được tạo trong 10 phút vừa qua, lấy giá trị cuối trừ giá trị đầu của chính khoảng 10 phút đó.

### 1.2. Số đo tức thời (gauge)

Gauge biểu diễn trạng thái tại thời điểm đọc, có thể tăng hoặc giảm. Ví dụ:

- Số session đang hoạt động.
- Số process hiện tại.
- Số request đang chờ.
- Mức sử dụng tablespace tại thời điểm truy vấn.
- Số lượng cursor đang mở.

Không lấy giá trị cuối trừ đầu của gauge rồi gọi đó là tổng hoạt động. Ví dụ, active sessions giảm từ 40 xuống 20 chỉ cho biết số session hoạt động tại hai thời điểm khác nhau; delta -20 không phải số session đã kết thúc trong khoảng đo.

Với gauge, thường cần lưu chuỗi mẫu để xem xu hướng, min/max, percentile hoặc thời gian ở trạng thái cao.

### 1.3. Tỷ lệ và số trung bình

Một số view cung cấp tỷ lệ hoặc số trung bình được tính từ các bộ đếm. Ví dụ average wait, hit ratio hoặc average elapsed time.

Không phải lúc nào cũng được lấy tỷ lệ cuối trừ tỷ lệ đầu. Nếu muốn biết average wait trong khoảng đo, cần lấy delta tổng thời gian chờ chia cho delta số lần chờ:

\[
\text{Average wait} =
\frac{\Delta \text{Wait time}}{\Delta \text{Wait count}}
\]

Nếu muốn biết hit ratio của một khoảng, hãy tính lại từ delta của numerator và denominator. Không lấy trung bình cộng các hit ratio của từng snapshot trừ khi phép tính có trọng số phù hợp.

### 1.4. Không cộng mọi cột VALUE thành một tổng

Mỗi statistic có đơn vị và ý nghĩa riêng. Ví dụ:

| Statistic | Đơn vị thường gặp | Ý nghĩa |
| --- | --- | --- |
| session logical reads | buffer/block | Số lần đọc block logic trong session |
| physical reads | block | Số block đọc vật lý |
| redo size | byte | Lượng redo được tạo |
| execute count | lần thực thi | Số lần execute |
| user commits | transaction commit | Số commit do user |
| DB time trong time model | microsecond | Thời gian database call đã tích lũy theo định nghĩa của statistic |

Không cộng 100 byte redo với 20 lần execute và 5 block đọc để tạo ra một con số tổng. Một phép cộng chỉ có ý nghĩa khi các thành phần cùng đơn vị hoặc được chuyển đổi bằng một mô hình được định nghĩa rõ.

## 2. Xác định câu hỏi đo trước khi chọn statistic

Đừng bắt đầu bằng cách chọn một view có nhiều cột. Hãy viết câu hỏi hiệu năng thành một phép đo có thể kiểm chứng.

Ví dụ:

- Database tạo bao nhiêu byte redo mỗi giây?
- Một workload đọc bao nhiêu block vật lý trong 5 phút?
- Số lần execute tăng bao nhiêu trên mỗi transaction?
- Thời gian chờ trung bình của một wait event trong khoảng đo là bao nhiêu?
- Một SQL_ID tiêu tốn bao nhiêu CPU trong khoảng vừa qua?
- Một session cụ thể phát sinh bao nhiêu logical reads trong request?

Với mỗi câu hỏi, xác định sáu yếu tố:

1. **Metric**: statistic hoặc event nào trả lời câu hỏi?
2. **Unit**: byte, block, call, wait, microsecond hay số lượng session?
3. **Scope**: toàn instance, một instance RAC, một PDB, session hay SQL cursor?
4. **Lifetime/reset point**: bộ đếm bắt đầu từ khi nào và có thể reset khi nào?
5. **Window**: khoảng thời gian nào cần đo?
6. **Workload denominator**: có cần chuẩn hóa theo request, transaction, row hoặc execution không?

Ví dụ, “redo tăng nhanh” chưa đủ rõ. Câu hỏi tốt hơn là “trong 300 giây vừa qua, instance 2 tạo bao nhiêu byte redo và tốc độ byte/giây là bao nhiêu?”. Câu hỏi này xác định được metric, unit, scope và window.

## 3. Chọn phạm vi đo trong Oracle

Oracle có nhiều tầng thống kê. Chọn đúng tầng giúp tránh gán nhầm công việc của một session cho toàn database hoặc ngược lại.

### 3.1. Instance/system-level statistics

V$SYSSTAT cung cấp các system statistics tích lũy cho instance hiện tại. Đây là nơi thường dùng để đo tổng hoạt động của instance giữa hai thời điểm.

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
)
ORDER BY name;
~~~

Các giá trị trong kết quả là số tích lũy tại thời điểm truy vấn. Muốn có delta, cần lưu kết quả ở thời điểm bắt đầu và kết thúc.

Tên statistic có thể thay đổi theo phiên bản hoặc tính năng được cài đặt. Hãy kiểm tra V$STATNAME và tài liệu phiên bản Oracle đang chạy thay vì hard-code statistic number.

### 3.2. Session-level statistics

V$SESSTAT chứa statistic theo session. Kết hợp V$STATNAME để tìm tên statistic:

~~~sql
SELECT ss.sid,
       sn.name,
       ss.value
FROM v$sesstat ss
JOIN v$statname sn
  ON sn.statistic# = ss.statistic#
WHERE ss.sid = :sid
  AND sn.name IN (
      'session logical reads',
      'physical reads',
      'execute count'
  )
ORDER BY sn.name;
~~~

Session statistics phù hợp khi cần biết một session đã phát sinh bao nhiêu công việc trong vòng đời của session. Nó không phải tổng hoạt động của toàn database.

Một SID có thể được tái sử dụng sau khi session kết thúc. Khi so sánh hai mẫu, phải xác nhận đó là cùng session bằng SID và SERIAL#, đồng thời giữ LOGON_TIME và INST_ID nếu cần. Chỉ so SID có thể ghép nhầm hai session khác nhau.

### 3.3. SQL cursor statistics

V$SQL chứa thống kê của các child cursor đang có trong shared SQL area. Các cột thường dùng gồm EXECUTIONS, ELAPSED_TIME, CPU_TIME, BUFFER_GETS và DISK_READS.

Các giá trị này thường tích lũy theo vòng đời của cursor. Cursor có thể bị invalidated, aged out hoặc được nạp lại; child cursor khác cũng có thể xuất hiện. Vì vậy, khi so sánh hai mẫu cần giữ ít nhất:

- INST_ID trong RAC.
- SQL_ID.
- CHILD_NUMBER.
- PLAN_HASH_VALUE.
- CON_ID nếu môi trường multitenant có phạm vi theo container.
- Dấu hiệu cursor còn cùng vòng đời, chẳng hạn FIRST_LOAD_TIME và các thuộc tính nhận diện phù hợp.

Không ghép chỉ theo SQL_ID rồi mặc định hai hàng V$SQL là cùng một bộ đếm. Một SQL_ID có thể có nhiều child cursor với plan hoặc môi trường khác nhau.

### 3.4. Wait event statistics

V$SYSTEM_EVENT chứa số lần chờ và thời gian chờ tích lũy theo event trong phạm vi instance. V$SESSION_EVENT chứa thống kê chờ theo session.

~~~sql
SELECT event,
       total_waits,
       time_waited_micro
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Khi tính average wait cho một khoảng, sử dụng delta của time_waited_micro chia delta của total_waits. Không lấy AVERAGE_WAIT ở hai thời điểm rồi trừ nhau.

### 3.5. Time model statistics

V$SYS_TIME_MODEL và V$SESS_TIME_MODEL cung cấp các chỉ số thời gian tích lũy. Nhiều giá trị time model được tính bằng microsecond.

~~~sql
SELECT stat_name,
       value
FROM v$sys_time_model
ORDER BY stat_name;
~~~

Kiểm tra đơn vị của từng statistic trước khi đổi sang millisecond hoặc second. Không giả định mọi cột thời gian trong mọi view đều dùng cùng đơn vị.

### 3.6. Chọn scope theo câu hỏi

| Câu hỏi | Scope nên bắt đầu |
| --- | --- |
| Instance tạo bao nhiêu redo? | V$SYSSTAT |
| Một session đọc bao nhiêu block? | V$SESSTAT |
| Một SQL child cursor dùng bao nhiêu CPU? | V$SQL |
| Instance chờ event nào nhiều? | V$SYSTEM_EVENT |
| Một session có bao nhiêu DB time? | V$SESS_TIME_MODEL |
| Toàn cluster RAC tạo bao nhiêu redo? | GV$SYSSTAT, tính delta riêng từng instance rồi mới cộng |

## 4. Chọn khoảng đo phù hợp

Khoảng đo quá ngắn dễ bị nhiễu bởi thời điểm lấy mẫu, hoạt động nền và chi phí truy vấn thống kê. Khoảng đo quá dài có thể làm mờ một đợt chậm ngắn hoặc gộp nhiều loại workload khác nhau vào cùng một con số.

### 4.1. Đo theo thời gian của hiện tượng

Chọn window theo câu hỏi:

- Sự cố kéo dài vài giây: cần sampling dày hoặc trace theo request; snapshot cách nhau 15 phút sẽ bỏ lỡ chi tiết.
- Xu hướng tải trong một giờ: có thể dùng các khoảng 1–5 phút tùy tốc độ thay đổi.
- So sánh batch 30 phút: lấy mẫu đúng trước và sau batch, đồng thời ghi lại thời điểm thực tế.
- So sánh workload hàng ngày: cần cùng giờ, cùng quy mô dữ liệu, cùng workload và nhiều lần chạy.

Các khoảng trên chỉ là điểm khởi đầu. Không có một sampling interval đúng cho mọi hệ thống.

### 4.2. Khoảng đo phải bao trùm công việc cần đánh giá

Nếu đo batch, lấy mẫu trước khi batch bắt đầu và sau khi batch kết thúc. Không chụp mẫu bắt đầu sau khi batch đã chạy một phần hoặc chụp mẫu cuối trước khi các commit/flush liên quan hoàn tất.

Nếu muốn đo một request cụ thể, tốt hơn là gắn request với session/module/action/client identifier hoặc tracing ID để lấy số liệu đúng phạm vi. Delta toàn instance có thể bị ảnh hưởng bởi workload khác chạy đồng thời.

### 4.3. Ghi thời gian thực tế, không giả định khoảng đo đúng kế hoạch

Một job được dự kiến chạy 300 giây nhưng thực tế kéo dài 327 giây. Khi tính rate, dùng elapsed time thực tế giữa hai mẫu, không chia cho 300 chỉ vì đó là lịch dự kiến.

Dùng SYSTIMESTAMP để ghi thời điểm có timezone:

~~~sql
SELECT SYSTIMESTAMP AS captured_at
FROM dual;
~~~

Nếu hai timestamp là TIMESTAMP WITH TIME ZONE, hiệu thời gian cho ra INTERVAL DAY TO SECOND. Tính elapsed seconds từ interval đó hoặc dùng một biểu thức đã được kiểm tra. Không trộn timestamp của máy ứng dụng với timestamp database mà không đồng bộ timezone/clock.

### 4.4. Lấy mẫu ở trạng thái ổn định

Khi benchmark:
1. Hoàn tất startup và warm-up cần thiết.
2. Chờ cache, connection pool và workload đạt trạng thái mục tiêu.
3. Chụp mẫu đầu.
4. Chạy workload đã định nghĩa.
5. Chụp mẫu cuối.
6. Lặp lại nhiều lần nếu cần so sánh.
7. Ghi nhận concurrency, dữ liệu, plan và cấu hình liên quan.

Không trộn warm-up với steady-state nếu câu hỏi là hiệu năng ổn định. Ngược lại, nếu người dùng thực sự quan tâm thời gian khởi động/warm-up, hãy đo giai đoạn đó riêng.

### 4.5. Cân bằng độ phân giải và overhead

Mỗi lần truy vấn view thống kê đều có chi phí. Chụp quá dày có thể tạo overhead và lượng dữ liệu giám sát lớn; chụp quá thưa bỏ lỡ spike. Chọn tần suất đủ để trả lời câu hỏi, rồi xác nhận chi phí monitoring không làm thay đổi đáng kể workload.

## 5. Công thức delta, elapsed time và rate

Với một bộ đếm C:

\[
\Delta C = C_1 - C_0
\]

Trong đó C0 là giá trị tại mẫu đầu và C1 là giá trị tại mẫu cuối.

Elapsed seconds:

\[
T = t_1 - t_0
\]

Rate:

\[
R = \frac{\Delta C}{T}
\]

Ví dụ, redo size tăng từ 2.000.000.000 byte lên 2.600.000.000 byte trong 120 giây:

\[
\Delta redo = 600.000.000\ bytes
\]

\[
redo\ rate = 600.000.000 / 120 = 5.000.000\ bytes/s
\]

Có thể đổi sang MB/s bằng cách chia cho 1.048.576 nếu dùng MiB, hoặc 1.000.000 nếu dùng MB thập phân. Ghi rõ quy ước đơn vị trong báo cáo.

### 5.1. Delta bằng 0

Nếu C1 = C0, delta bằng 0. Điều này có thể có nghĩa:
- Không có sự kiện phát sinh trong window.
- Statistic không được cập nhật bởi workload này.
- Sampling interval quá ngắn hoặc statistic có độ phân giải khác.
- Scope/filter không bao gồm workload cần đo.

Delta 0 không tự chứng minh hệ thống không hoạt động.

### 5.2. Delta âm

Với bộ đếm tích lũy được kỳ vọng không giảm, delta âm là dấu hiệu cần điều tra:

- Instance restart hoặc statistic bị reset.
- Session kết thúc và SID được tái sử dụng.
- SQL cursor bị unload/reload hoặc child cursor thay đổi.
- Hai mẫu thuộc hai instance/container khác nhau.
- Bộ đếm có semantics đặc biệt hoặc wraparound đã được tài liệu hóa.
- Dữ liệu lấy mẫu bị ghép sai.

Không dùng ABS(delta), không đổi delta âm thành 0 và không tiếp tục tính rate như thể dữ liệu hợp lệ. Trước hết xác định lý do counter giảm.

### 5.3. Counter wraparound

Một số hệ thống hoặc bộ đếm có thể có giới hạn độ rộng và wrap về đầu khi vượt giới hạn. Chỉ hiệu chỉnh wraparound nếu tài liệu của statistic xác định rõ độ rộng và hành vi đó, đồng thời có đủ dữ kiện để biết số lần wrap trong window.

Không tự giả định một counter Oracle là 32-bit hoặc 64-bit rồi áp công thức modulo. Khi không biết chính xác semantics, đánh dấu interval không hợp lệ và lấy một khoảng mới.

### 5.4. Phần trăm thay đổi

Phần trăm thay đổi so với baseline:

\[
\%\ change = \frac{C_1-C_0}{C_0}\times100
\]

Nếu C0 bằng 0, phần trăm thay đổi không xác định. Khi đó báo delta tuyệt đối và rate thay vì tự đặt phần trăm bằng 0 hoặc vô cực.

Phần trăm tăng của một bộ đếm cũng không tự cho biết hiệu năng tốt lên hay xấu đi. Redo tăng có thể là do workload tăng; logical reads tăng có thể là do xử lý nhiều request hơn hoặc do một truy vấn kém hiệu quả.

## 6. Chụp mẫu V$SYSSTAT có định danh rõ ràng

Một mẫu tốt không chỉ lưu statistic name và value. Cần lưu thời điểm, DBID, instance, startup time và container context để biết hai giá trị có thể so sánh hay không.

### 6.1. Tạo bảng lưu mẫu minh họa

~~~sql
CREATE TABLE perf_counter_sample (
    sample_id        NUMBER NOT NULL,
    captured_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    dbid             NUMBER NOT NULL,
    instance_number  NUMBER NOT NULL,
    startup_time     DATE NOT NULL,
    container_name   VARCHAR2(128),
    statistic_name   VARCHAR2(64) NOT NULL,
    statistic_value  NUMBER NOT NULL,
    CONSTRAINT perf_counter_sample_pk
        PRIMARY KEY (
            sample_id,
            dbid,
            instance_number,
            container_name,
            statistic_name
        )
);
~~~

Đây là bảng mẫu phục vụ bài thực hành. Trong production, có thể bổ sung host, service, PDB identity, run ID, workload label, build version và người vận hành. Nếu CONTAINER_NAME có thể NULL trong môi trường cụ thể, điều chỉnh khóa chính/khóa thay thế cho phù hợp.

### 6.2. Chụp mẫu đầu

~~~sql
INSERT INTO perf_counter_sample (
    sample_id,
    captured_at,
    dbid,
    instance_number,
    startup_time,
    container_name,
    statistic_name,
    statistic_value
)
SELECT
    1,
    SYSTIMESTAMP,
    d.dbid,
    i.instance_number,
    i.startup_time,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    s.name,
    s.value
FROM v$database d
CROSS JOIN v$instance i
CROSS JOIN v$sysstat s
WHERE s.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
);

COMMIT;
~~~

Lưu ý:
- sample_id = 1 là định danh mẫu đầu trong ví dụ.
- Statistic name là tên dễ đọc, giúp tránh phụ thuộc statistic number.
- Ghi startup_time để phát hiện instance restart.
- Ghi container context và chỉ so các mẫu cùng phạm vi container.
- Trong môi trường multitenant, kiểm tra semantics và cột CON_ID của các view theo phiên bản; không so số liệu PDB với CDB root nếu chưa xác định rõ phạm vi.

### 6.3. Chụp mẫu cuối

Sau khi workload hoàn thành, chụp mẫu thứ hai với sample_id khác:

~~~sql
INSERT INTO perf_counter_sample (
    sample_id,
    captured_at,
    dbid,
    instance_number,
    startup_time,
    container_name,
    statistic_name,
    statistic_value
)
SELECT
    2,
    SYSTIMESTAMP,
    d.dbid,
    i.instance_number,
    i.startup_time,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    s.name,
    s.value
FROM v$database d
CROSS JOIN v$instance i
CROSS JOIN v$sysstat s
WHERE s.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
);

COMMIT;
~~~

Không dùng lại sample_id nếu cần giữ lịch sử. Mỗi run nên có ID riêng và lưu hai mốc trong cùng measurement run.

## 7. Tính delta và rate từ hai mẫu

Truy vấn sau ghép mẫu đầu với mẫu cuối theo database, instance, container và statistic. Nó đồng thời phát hiện mẫu cuối bị thiếu, instance restart hoặc counter giảm.

~~~sql
WITH paired AS (
    SELECT
        b.statistic_name,
        b.statistic_value AS begin_value,
        e.statistic_value AS end_value,
        b.startup_time AS begin_startup,
        e.startup_time AS end_startup,
        b.captured_at AS begin_time,
        e.captured_at AS end_time,
        e.sample_id AS end_sample_id
    FROM perf_counter_sample b
    LEFT JOIN perf_counter_sample e
      ON e.sample_id = 2
     AND e.dbid = b.dbid
     AND e.instance_number = b.instance_number
     AND e.container_name = b.container_name
     AND e.statistic_name = b.statistic_name
    WHERE b.sample_id = 1
),
calculated AS (
    SELECT
        statistic_name,
        begin_value,
        end_value,
        CASE
            WHEN end_sample_id IS NULL THEN 'MISSING_END_SAMPLE'
            WHEN begin_startup <> end_startup THEN 'INSTANCE_RESTARTED'
            WHEN end_value < begin_value THEN 'COUNTER_DECREASED'
            ELSE 'OK'
        END AS validation_status,
        CASE
            WHEN end_time IS NOT NULL THEN
                EXTRACT(DAY FROM (end_time - begin_time)) * 86400
              + EXTRACT(HOUR FROM (end_time - begin_time)) * 3600
              + EXTRACT(MINUTE FROM (end_time - begin_time)) * 60
              + EXTRACT(SECOND FROM (end_time - begin_time))
        END AS elapsed_seconds,
        CASE
            WHEN end_sample_id IS NOT NULL
             AND begin_startup = end_startup
             AND end_value >= begin_value
            THEN end_value - begin_value
        END AS delta_value
    FROM paired
)
SELECT
    statistic_name,
    begin_value,
    end_value,
    validation_status,
    elapsed_seconds,
    delta_value,
    CASE
        WHEN validation_status = 'OK'
        THEN delta_value / NULLIF(elapsed_seconds, 0)
    END AS rate_per_second
FROM calculated
ORDER BY statistic_name;
~~~

Nếu validation_status không phải OK, không sử dụng delta/rate đó để kết luận. Nếu một statistic không có ở mẫu cuối, nó sẽ được hiển thị là MISSING_END_SAMPLE thay vì bị âm thầm bỏ qua.

Trong ví dụ, sample_id được cố định là 1 và 2. Khi dùng thực tế, truyền ID của run vào bind variable hoặc bảng metadata của measurement run.

### 7.1. Đọc kết quả theo đúng đơn vị

| Statistic | Delta có nghĩa | Rate có nghĩa |
| --- | --- | --- |
| redo size | byte redo phát sinh trong window | byte/second |
| physical reads | block đọc vật lý trong window | block/second |
| session logical reads | logical buffer reads trong window | buffer/second |
| execute count | số execute trong window | execute/second |
| user commits | số commit trong window | commit/second |

Không gọi tất cả rate là throughput nếu chưa xác định một đơn vị công việc nghiệp vụ. Ví dụ, execute/second không tương đương request/second nếu một request có thể chạy nhiều câu SQL.

## 8. Đọc đơn vị và định nghĩa của statistic

Statistic name không nói hết đơn vị hoặc cách đếm. Hãy kiểm tra tài liệu Oracle cho đúng release và kiểm tra V$STATNAME.

~~~sql
SELECT statistic#,
       name,
       class
FROM v$statname
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
)
ORDER BY name;
~~~

V$STATNAME mô tả statistic có trong instance. Cột CLASS là phân loại nội bộ; không nên xem nó như đơn vị đo.

Ví dụ đơn vị thường gặp:
- redo size: byte.
- physical reads: block.
- consistent gets và db block gets: block/buffer operations.
- execute count: số lần execute.
- user commits: số commit.
- TIME_WAITED_MICRO: microsecond.
- ELAPSED_TIME trong V$SQL: microsecond.

Tên statistic có thể giữ nguyên nhưng cách diễn giải hoặc phạm vi có thể có chi tiết riêng theo phiên bản. Không chuyển đổi sang MB, GB, ms hoặc giây nếu chưa xác nhận unit.

### 8.1. Byte, block và row không thể thay thế nhau

Một physical read có thể đọc nhiều block. Một logical read đếm thao tác đọc buffer theo định nghĩa statistic. Số row trả về không nhất thiết bằng số block đọc. Một câu SQL có thể thực hiện nhiều execute hoặc một execute trả về rất nhiều row.

Khi báo cáo, luôn ghi rõ:
- Giá trị là byte hay block.
- Block size nếu quy đổi block thành byte.
- Count là execute, parse, fetch, commit hay request.
- Time là microsecond, millisecond hay second.
- Metric ở instance, session hay SQL cursor.

### 8.2. Đừng suy ra MB từ số block nếu chưa biết block size

Nếu statistic đếm block, muốn ước tính byte cần biết block size của tablespace/database liên quan và hiểu statistic có bao gồm nhiều loại block hoặc đường đọc đặc biệt hay không. Không mặc định mọi block đều là 8 KB.

## 9. Tính rate, average và ratio từ delta

Delta cho biết lượng phát sinh trong window. Rate và average giúp so sánh các window có độ dài khác nhau hoặc workload khác nhau.

### 9.1. Rate trên giây

\[
R = \frac{\Delta counter}{elapsed\ seconds}
\]

Ví dụ:
- Delta redo size = 900 MB.
- Elapsed = 180 giây.
- Rate = 5 MB/s nếu dùng cùng quy ước MB.

Rate cho phép so sánh window dài 3 phút với window dài 5 phút. Tuy nhiên, rate trung bình không cho biết spike bên trong window; cần sampling dày hơn nếu quan tâm peak.

### 9.2. Average wait time

Giả sử có delta:
- time_waited_micro = 2.400.000.000 microsecond.
- total_waits = 120.000 lần.

Average wait:

\[
2.400.000.000 / 120.000 = 20.000\ microseconds
\]

Tức 20 ms mỗi wait.

Trong SQL:

~~~sql
SELECT
    delta_time_waited_micro /
        NULLIF(delta_total_waits, 0) / 1000
        AS average_wait_ms
FROM interval_wait_delta;
~~~

Nếu delta_total_waits bằng 0, average không xác định. Trả NULL hoặc ghi N/A; không chia cho 0 và không tự gán bằng 0 ms.

### 9.3. Average elapsed time per execution

Nếu có delta elapsed time và delta executions:

\[
\text{Elapsed per execution} =
\frac{\Delta elapsed\_time}{\Delta executions}
\]

Nếu elapsed_time được lưu bằng microsecond, kết quả là microsecond/execute. Chỉ so sánh khi SQL_ID, child cursor, plan và phạm vi giống nhau. Một SQL có thể có nhiều execution với thời gian rất khác nhau; average không thể hiện tail latency.

### 9.4. Tính ratio bằng tổng delta

Ví dụ tỷ lệ parse trên execute trong một khoảng:

\[
\text{Parse per execute} =
\frac{\Delta parse\ count}{\Delta execute\ count}
\]

Ví dụ tỷ lệ block reads vật lý trên tổng logical gets:

\[
\text{Physical read ratio} =
\frac{\Delta physical\ reads}
{\Delta db\ block\ gets + \Delta consistent\ gets}
\]

Nếu muốn biểu diễn phần trăm, nhân 100. Công thức buffer cache hit ratio thường gặp là:

\[
\text{Illustrative hit ratio} =
\left(
1 - \frac{\Delta physical\ reads}
{\Delta db\ block\ gets + \Delta consistent\ gets}
\right)\times100
\]

Đây chỉ là chỉ báo tham khảo, không phải điểm sức khỏe database phổ quát. Direct path reads, workload mix, scan lớn và các đường truy cập khác có thể làm tỷ lệ khó diễn giải. Xem thêm wait, I/O latency, execution plan và workload thực tế.

### 9.5. Không lấy trung bình cộng các tỷ lệ snapshot

Giả sử:
- Window A có 10 lần chờ, average 1 ms.
- Window B có 1.000 lần chờ, average 10 ms.

Trung bình cộng hai average là 5,5 ms, nhưng average của toàn bộ 1.010 wait là:

\[
\frac{10\times1 + 1000\times10}{1010}
\approx 9,91\ ms
\]

Cách đúng là cộng tổng thời gian chờ và tổng số wait, rồi chia. Đây là weighted average theo số lần chờ.

## 10. Vì sao tổng số tích lũy dễ gây hiểu lầm

Một con số lớn thường trông có vẻ đáng chú ý, nhưng không có ngữ cảnh thì nó không trả lời câu hỏi hiệu năng.

### 10.1. Giá trị lớn có thể chỉ phản ánh instance đã chạy lâu

Instance chạy 200 ngày có thể có redo size lớn hơn instance mới khởi động dù tốc độ tạo redo hiện tại thấp hơn nhiều.

So sánh giá trị tích lũy giữa hai instance có uptime khác nhau là không công bằng. So delta trong cùng một window hoặc rate đã chuẩn hóa.

### 10.2. Tổng toàn hệ thống che giấu một instance bất thường

Trong RAC, tổng redo của 4 instance có thể bình thường trong khi một instance chịu tải cao bất thường. Hãy xem từng instance trước, sau đó mới tổng hợp cluster.

### 10.3. Tổng nhiều session không nhất thiết bằng tổng workload

V$SESSTAT chỉ chứa session còn tồn tại tại thời điểm truy vấn. Session đã kết thúc có thể biến mất khỏi view. Nếu cộng các session đang tồn tại ở mẫu đầu và mẫu cuối, tập session có thể khác nhau.

Không dùng tổng V$SESSTAT tại hai thời điểm như thể đó là một bộ đếm hệ thống có cùng lifetime. Muốn tổng workload toàn instance, dùng statistic cấp instance hoặc hệ thống tracing/telemetry có định danh request.

### 10.4. Một SQL_ID có nhiều child cursor

Cộng các child cursor có thể hữu ích nếu mục tiêu là tổng hoạt động của SQL_ID trong cùng window, nhưng trước tiên phải xác định child cursor nào tồn tại ở cả hai mốc và child nào mới xuất hiện hoặc biến mất. Nếu plan thay đổi, gộp các child có thể che khuất vấn đề regression của một plan cụ thể.

### 10.5. Tổng thời gian có thể lớn hơn wall-clock time

Trong môi trường concurrency, tổng DB time hoặc tổng wait time của nhiều session có thể lớn hơn thời gian thực tế của window. Ví dụ, 100 session mỗi session tiêu thụ 1 giây CPU trong cùng một giây wall-clock có thể tạo ra tổng CPU time xấp xỉ 100 giây.

Đây không nhất thiết là lỗi dữ liệu. Các bộ đếm thời gian cộng dồn trên nhiều worker/session; chúng không phải đồng hồ wall-clock của cả hệ thống.

### 10.6. Không cộng các snapshot tích lũy liên tiếp

Giả sử counter có giá trị:
- 10:00 = 1.000.
- 10:05 = 1.500.
- 10:10 = 1.900.

Tổng 1.000 + 1.500 + 1.900 = 4.400 không phải số công việc trong 10 phút. Delta của toàn khoảng là 1.900 - 1.000 = 900. Nếu muốn hai khoảng 5 phút riêng, delta lần lượt là 500 và 400.

## 11. Reset point và tính liên tục của counter

Mọi phép trừ cần một giả định: hai giá trị thuộc cùng một bộ đếm trong cùng vòng đời.

### 11.1. Instance restart

V$SYSSTAT là statistic của instance. Khi instance restart, nhiều statistic bắt đầu lại từ mốc mới. Vì vậy, phải lưu STARTUP_TIME cùng mẫu.

~~~sql
SELECT instance_number,
       startup_time,
       status
FROM v$instance;
~~~

Nếu STARTUP_TIME khác giữa hai mẫu, không lấy delta như một window liên tục. Chia phép đo thành hai giai đoạn hoặc lấy lại baseline sau khi instance ổn định.

### 11.2. Session kết thúc

Session-level counters tồn tại theo session. Khi session disconnect, statistic của session không còn là cùng một đối tượng để so sánh.

Khi lấy mẫu V$SESSTAT, giữ:
- INST_ID trong RAC.
- SID.
- SERIAL#.
- LOGON_TIME.
- CON_ID hoặc container identity khi cần.

Nếu một session biến mất hoặc key nhận diện thay đổi, đánh dấu mẫu không liên tục. Không ghép session mới chỉ vì nó dùng lại SID cũ.

### 11.3. SQL cursor bị thay thế

V$SQL là thống kê của cursor đang có trong shared pool. Cursor có thể bị aged out, invalidated hoặc tạo child mới. Khi cursor được nạp lại, các bộ đếm có thể bắt đầu từ đầu cho cursor mới.

Giữ SQL_ID, CHILD_NUMBER, PLAN_HASH_VALUE, INST_ID và các thông tin nhận diện cursor. Nếu cursor không còn ở mẫu cuối, không coi giá trị thiếu là 0 mà không có chính sách rõ ràng.

### 11.4. Reset thủ công hoặc thay đổi môi trường

Một số thao tác quản trị hoặc thay đổi vòng đời đối tượng có thể làm số liệu bị reset hoặc thay đổi phạm vi. Ghi lại:
- Restart/shutdown/startup.
- Failover hoặc switchover.
- Reconfiguration RAC.
- PDB open/close hoặc chuyển container.
- Cursor invalidation/flush shared pool.
- Thay đổi service/session.
- Công cụ monitoring bị restart hoặc mất mẫu.

### 11.5. Khi nào cần baseline mới?

Nếu phát hiện reset hoặc mất mẫu:
1. Đánh dấu window bị gián đoạn.
2. Không tính rate qua ranh giới reset.
3. Ghi nguyên nhân nếu xác định được.
4. Chụp baseline mới.
5. Tiếp tục đo từ baseline mới.

Không cố “sửa” dữ liệu bằng cách lấy trị tuyệt đối hoặc nội suy khi chưa biết điều gì đã xảy ra.

## 12. Đo trong Oracle RAC

Trong RAC, V$ thường hiển thị view của instance hiện tại. GV$ cung cấp dữ liệu từ nhiều instance và thêm INST_ID.

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
WHERE name IN ('redo size', 'physical reads', 'execute count')
ORDER BY inst_id, name;
~~~

### 12.1. Tính delta riêng từng instance

Mỗi instance có startup time và vòng đời riêng. Quy trình đúng:
1. Chụp giá trị đầu cho từng INST_ID.
2. Lưu startup time của từng instance.
3. Chụp giá trị cuối cho từng INST_ID.
4. Ghép đúng cùng instance, statistic và container.
5. Kiểm tra startup time không đổi.
6. Tính delta riêng.
7. Chỉ sau đó mới cộng delta nếu câu hỏi là tổng cluster.

### 12.2. Instance gia nhập hoặc rời cluster

Nếu instance không có ở một trong hai mốc, không tự coi giá trị thiếu là 0. Có thể instance vừa khởi động, bị stop hoặc không truy vấn được. Báo cluster total là incomplete hoặc tách riêng phần instance không liên tục.

### 12.3. Tổng cluster có điều kiện

Có thể cộng delta của các instance nếu:
- Cùng database và cùng metric.
- Cùng đơn vị.
- Cùng window hoặc elapsed time tương thích.
- Mỗi instance có mẫu đầu/cuối hợp lệ.
- Không có restart/reset trong window.
- Phạm vi container/workload được xác định nhất quán.

Dù có cluster total, vẫn giữ bảng delta theo INST_ID để thấy mất cân bằng tải.

### 12.4. Đừng cộng rate của các instance có window khác nhau một cách tùy tiện

Nếu mỗi instance có elapsed time khác nhau, không cộng các rate rồi gọi là cluster rate. Tính tổng delta và tổng elapsed theo định nghĩa phù hợp, hoặc đồng bộ thời điểm lấy mẫu để mọi instance dùng cùng window. Khi cộng rate, cần hiểu đó là tổng throughput đồng thời của cluster và các interval thực sự tương ứng.

## 13. Đo theo PDB/container

Trong CDB, cùng một database có root và nhiều PDB. Một số dynamic performance view và historical view có cột CON_ID/CON_DBID để chỉ phạm vi container.

Không so:
- Counter ở CDB root với counter của một PDB.
- Counter của PDB A với PDB B.
- Hai mẫu lấy ở hai container khác nhau.
- Số liệu instance-wide với số liệu container-scoped.

Khi dùng GV$ hoặc DBA_HIST_* trong multitenant, kiểm tra các cột CON_ID/CON_DBID có sẵn trong release và view đang dùng. Ghép theo đúng container identity nếu view cung cấp các cột đó. Nếu không thể xác định scope, đừng báo delta như thể hai mẫu tương đương.

## 14. Session counters: xác định đúng session

Ví dụ truy vấn session statistic theo SID và SERIAL#:

~~~sql
SELECT s.sid,
       s.serial#,
       s.logon_time,
       st.name,
       ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname st
  ON st.statistic# = ss.statistic#
WHERE s.sid = :sid
  AND s.serial# = :serial_number
  AND st.name IN (
      'session logical reads',
      'physical reads',
      'execute count'
  )
ORDER BY st.name;
~~~

Trong RAC, dùng GV$SESSION, GV$SESSTAT và GV$STATNAME; ghép thêm INST_ID.

### 14.1. SID có thể được tái sử dụng

SID là định danh trong instance nhưng có thể được dùng lại sau khi session kết thúc. SERIAL# giúp phân biệt session khác nhau dùng lại SID. LOGON_TIME cung cấp thêm thông tin vòng đời.

### 14.2. Session pooling và request boundary

Một connection pool có thể tái sử dụng cùng database session cho nhiều request. Session counter tích lũy qua nhiều request, nên delta theo session không tự động tương đương delta của một request.

Muốn đo một request:
- Đặt MODULE/ACTION bằng DBMS_APPLICATION_INFO.
- Dùng CLIENT_IDENTIFIER hoặc tracing ID.
- Chụp counter ngay trước/sau request nếu request chiếm session độc quyền trong khoảng đó.
- Hoặc dùng SQL trace/telemetry có correlation ID.
- Không để request khác dùng chung session đồng thời trong khi đo nếu muốn attribution chính xác.

## 15. SQL cursor counters: giữ đúng child cursor

V$SQL có thể trả nhiều hàng cho cùng SQL_ID. Một child cursor có thể khác child khác vì bind metadata, optimizer environment, authorization hoặc lý do khác.

~~~sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads
FROM gv$sql
WHERE sql_id = :sql_id
ORDER BY inst_id, child_number;
~~~

### 15.1. Delta của cursor

Để tính delta:
- So cùng INST_ID.
- So cùng SQL_ID và CHILD_NUMBER.
- Kiểm tra PLAN_HASH_VALUE.
- Kiểm tra cursor chưa bị thay thế.
- Dùng cùng container.
- Dùng thời điểm mẫu tương ứng.

Nếu một child cursor mới xuất hiện ở mẫu cuối, có thể đó là một cursor mới chứ không phải counter tăng từ 0 trong cùng vòng đời cũ. Báo riêng child mới.

### 15.2. SQL_ID aggregate và plan regression

Nếu muốn tổng hoạt động của SQL_ID, có thể tổng hợp delta của các child hợp lệ. Nhưng nếu một child có plan chậm mới xuất hiện, aggregate có thể che mất regression. Luôn xem theo child/plan trước rồi mới tổng hợp.

### 15.3. V$SQLSTATS và AWR

V$SQLSTATS có thể cung cấp thống kê SQL theo SQL_ID với vòng đời hữu ích cho monitoring, nhưng vẫn cần hiểu semantics của view và khả năng reset. Với lịch sử dài hơn, có thể dùng AWR nếu được cấp phép và cấu hình; DBA_HIST_SQLSTAT cung cấp các cột delta theo snapshot. Các cột DELTA đã là lượng phát sinh trong snapshot interval; không lấy chênh lệch lần nữa như thể đó là cumulative value.

## 16. Dùng AWR snapshot để tính delta lịch sử

AWR lưu nhiều loại cumulative system statistics theo snapshot. Có thể so hai snapshot cùng DBID và INSTANCE_NUMBER để tính delta lịch sử.

**Lưu ý license:** AWR và các view DBA_HIST_* thuộc phạm vi tính năng Diagnostics Pack theo điều khoản Oracle. Chỉ dùng khi tổ chức có quyền sử dụng phù hợp. Nếu không có license, cân nhắc Statspack hoặc tự chụp mẫu từ các dynamic performance view được phép sử dụng.

### 16.1. Xác định snapshot window

~~~sql
SELECT snap_id,
       dbid,
       instance_number,
       startup_time,
       begin_interval_time,
       end_interval_time
FROM dba_hist_snapshot
WHERE begin_interval_time >= :from_time
  AND end_interval_time <= :to_time
ORDER BY instance_number, snap_id;
~~~

Chọn snapshot bao trùm khoảng workload cần phân tích. Thời gian thực tế của snapshot có thể không trùng chính xác thời điểm bắt đầu/kết thúc công việc.

### 16.2. Tính delta từ DBA_HIST_SYSSTAT

~~~sql
WITH snapshot_pair AS (
    SELECT
        b.dbid,
        b.instance_number,
        b.snap_id AS begin_snap_id,
        e.snap_id AS end_snap_id,
        b.startup_time AS begin_startup_time,
        e.startup_time AS end_startup_time,
        b.end_interval_time AS begin_time,
        e.end_interval_time AS end_time
    FROM dba_hist_snapshot b
    JOIN dba_hist_snapshot e
      ON e.dbid = b.dbid
     AND e.instance_number = b.instance_number
    WHERE b.snap_id = :begin_snap_id
      AND e.snap_id = :end_snap_id
)
SELECT
    n.stat_name,
    b.value AS begin_value,
    e.value AS end_value,
    e.value - b.value AS delta_value,
    p.begin_startup_time,
    p.end_startup_time,
    p.begin_time,
    p.end_time
FROM snapshot_pair p
JOIN dba_hist_sysstat b
  ON b.dbid = p.dbid
 AND b.instance_number = p.instance_number
 AND b.snap_id = p.begin_snap_id
JOIN dba_hist_sysstat e
  ON e.dbid = b.dbid
 AND e.instance_number = b.instance_number
 AND e.stat_id = b.stat_id
 AND e.snap_id = p.end_snap_id
JOIN dba_hist_stat_name n
  ON n.dbid = b.dbid
 AND n.stat_id = b.stat_id
WHERE p.begin_startup_time = p.end_startup_time
  AND n.stat_name IN ('redo size', 'physical reads', 'execute count')
ORDER BY n.stat_name;
~~~

Nếu startup time khác, không xem hai snapshot là một chuỗi counter liên tục. Truy vấn trên loại bỏ cặp snapshot restart bằng điều kiện startup time bằng nhau.

Trong multitenant, bổ sung điều kiện ghép CON_DBID/CON_ID nếu các cột đó có trong view ở phiên bản đang dùng. Không ghép số liệu khác container.

### 16.3. AWR SQL statistics đã có DELTA

DBA_HIST_SQLSTAT thường cung cấp các cột như EXECUTIONS_DELTA, ELAPSED_TIME_DELTA, CPU_TIME_DELTA, BUFFER_GETS_DELTA và DISK_READS_DELTA. Đây là các lượng thay đổi trong snapshot interval.

Không lấy DELTA cuối trừ DELTA đầu. Muốn tổng một chuỗi interval, cộng các delta không trùng lặp; muốn so một interval, dùng đúng hàng snapshot đó.

### 16.4. Snapshot không phải phép đo đúng request

AWR snapshot thường bao trùm một khoảng rộng hơn request hoặc batch cụ thể. Nếu một snapshot chứa nhiều workload đồng thời, delta phản ánh tất cả hoạt động trong phạm vi đó. Không gán toàn bộ delta của snapshot cho một SQL hoặc một ứng dụng.

## 17. Tổng hợp nhiều interval đúng cách

Khi có nhiều window, phải chọn cách tổng hợp phù hợp với metric.

### 17.1. Tổng delta của các interval không chồng lấn

Nếu có ba interval liên tiếp, cùng scope và không reset:

\[
\Delta_{\text{toàn khoảng}} =
\Delta_1 + \Delta_2 + \Delta_3
\]

Tổng delta phải bằng counter cuối trừ counter đầu nếu chuỗi mẫu liên tục và không mất interval.

Không cộng giá trị cumulative ở từng snapshot.

### 17.2. Rate trung bình theo toàn khoảng

Nếu interval có độ dài khác nhau:

\[
R_{\text{toàn khoảng}} =
\frac{\sum \Delta C_i}{\sum T_i}
\]

Không lấy trung bình cộng đơn giản của các rate nếu các window có độ dài khác nhau. Công thức trên tương đương weighted average theo thời lượng.

### 17.3. Average wait tổng hợp

\[
W_{\text{toàn khoảng}} =
\frac{\sum \Delta wait\_time_i}
{\sum \Delta wait\_count_i}
\]

Không lấy trung bình các average wait của từng interval nếu số lần chờ khác nhau.

### 17.4. Ratio tổng hợp

\[
Ratio_{\text{toàn khoảng}} =
\frac{\sum \Delta numerator_i}
{\sum \Delta denominator_i}
\]

Không lấy trung bình cộng các phần trăm của từng window trừ khi có trọng số phù hợp và cùng định nghĩa.

### 17.5. Percentile không thể khôi phục từ tổng

Tổng elapsed time và tổng execution count chỉ cho average. Chúng không đủ để tính p95/p99 latency. Muốn percentile, cần histogram, latency sample hoặc dữ liệu tracing đủ chi tiết. Không suy ra tail latency từ một bộ đếm tổng.

## 18. Chuẩn hóa theo workload

Rate trên giây giúp so khoảng dài ngắn khác nhau, nhưng vẫn có thể gây hiểu lầm khi lượng công việc khác nhau.

Ví dụ, redo bytes/second tăng gấp đôi vì số transaction/second cũng tăng gấp đôi. Điều đó chưa chắc là regression.

Có thể bổ sung metric trên đơn vị công việc:

- Redo bytes per transaction.
- Logical reads per execution.
- CPU time per request.
- Physical reads per report.
- Wait time per business operation.
- Rows processed per second.

Công thức:

\[
\text{Work-normalized metric} =
\frac{\Delta resource}{\Delta workload}
\]

Ví dụ:

~~~sql
SELECT delta_redo_bytes /
       NULLIF(delta_transactions, 0) AS redo_bytes_per_transaction
FROM interval_metrics;
~~~

Dùng số transaction thực tế hoặc business request counter đáng tin cậy. Không mặc định user commits bằng số business request: một request có thể commit nhiều lần hoặc nhiều request có thể cùng một transaction.

### 18.1. Cùng workload mới so sánh được

Khi so hai phiên bản ứng dụng:
- Dùng cùng tập dữ liệu hoặc quy mô tương đương.
- Dùng cùng concurrency.
- Dùng cùng tham số và execution plan nếu mục tiêu không phải kiểm tra plan.
- Tách warm-up và steady-state.
- Ghi lại số request/transaction hoàn tất.
- So resource per unit work cùng với latency.

### 18.2. Throughput tăng nhưng latency cũng tăng

Đây có thể là dấu hiệu hệ thống xử lý nhiều request hơn nhưng đang tiến gần giới hạn tài nguyên. Không kết luận tốt/xấu chỉ từ một metric. Cần xem throughput, p95/p99 latency, queueing, CPU, I/O, wait và lỗi.

## 19. Đọc thời gian đúng: CPU, DB time và wall-clock

Các statistic thời gian thường bị diễn giải sai vì chúng có thể được cộng trên nhiều session hoặc nhiều worker.

### 19.1. Wall-clock time

Wall-clock là thời gian thực trôi qua giữa hai timestamp. Đây là mẫu số khi tính rate của counter theo thời gian.

### 19.2. CPU time

CPU time là lượng thời gian CPU đã được sử dụng theo định nghĩa statistic. Tổng CPU time của nhiều session có thể lớn hơn wall-clock time vì nhiều session chạy đồng thời trên nhiều CPU.

### 19.3. DB time

DB time phản ánh thời gian database call được sử dụng bởi foreground sessions theo định nghĩa Oracle. Tổng DB time có thể lớn hơn elapsed wall-clock time do concurrency. Không diễn giải DB time 600 giây trong một window 60 giây là lỗi số học; có thể nhiều session hoạt động đồng thời.

### 19.4. Wait time

Tổng wait time cộng dồn trên các session cũng có thể lớn hơn wall-clock. Average wait cần chia tổng wait time cho số wait tương ứng. Không chia tổng wait time cho elapsed window rồi gọi kết quả là average latency của một request.

### 19.5. Không cộng CPU time và wait time tùy tiện

Một số chỉ số time model có quan hệ định nghĩa riêng. Không tự cộng mọi cột thời gian để tạo “total time” nếu chưa biết các khoảng có chồng lấp hay không. Dùng các metric được Oracle định nghĩa rõ và ghi chú phạm vi của chúng.

## 20. Những lỗi tổng hợp và diễn giải thường gặp

| Cách làm sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Đọc VALUE hiện tại rồi gọi là rate | VALUE là tích lũy | Lấy hai mẫu và tính delta/time |
| Cộng VALUE của nhiều snapshot | Đếm lặp phần lịch sử | Cộng delta của các interval không chồng lấn |
| Lấy ABS(delta) khi counter giảm | Che giấu reset hoặc ghép sai | Đánh dấu interval không hợp lệ và điều tra |
| Chia cho thời gian dự kiến | Elapsed thực tế có thể khác | Dùng timestamp thực tế |
| So hai instance uptime khác nhau bằng total | Mốc reset khác nhau | So delta/rate trong cùng window |
| Ghép session chỉ bằng SID | SID có thể tái sử dụng | Ghép SID, SERIAL#, LOGON_TIME và INST_ID |
| Ghép SQL chỉ bằng SQL_ID | Có nhiều child cursor/plan | Ghép child, plan, instance và vòng đời |
| Cộng statistic khác đơn vị | Tổng không có ý nghĩa | Giữ metric riêng hoặc quy đổi có cơ sở |
| Trung bình cộng các average | Không tính trọng số | Cộng numerator/denominator rồi chia |
| Trung bình cộng các rate có window khác nhau | Window dài/ngắn có trọng số khác | Tổng delta chia tổng elapsed |
| Gọi delta system là delta của một ứng dụng | Có workload khác cùng chạy | Đo theo session/request hoặc tracing |
| Dùng hit ratio làm tiêu chí duy nhất | Ratio không thể hiện latency/tải | Kết hợp I/O, wait, latency và workload |
| Coi DB time lớn hơn wall-clock là sai | Có concurrency | Diễn giải theo tổng thời gian trên nhiều session |
| Coi thiếu mẫu cuối là counter bằng 0 | Đối tượng có thể biến mất | Ghi MISSING/UNKNOWN, không tự gán 0 |
| Coi AWR DELTA là cumulative | DELTA đã là lượng trong interval | Dùng trực tiếp hoặc cộng các interval không trùng |
| Cộng cluster rate mà không đồng bộ window | Các rate không cùng khoảng | Đồng bộ sample hoặc tính từ tổng delta/tổng thời gian |

## 21. Checklist cho một phép đo có thể tin cậy

Trước khi công bố kết quả, xác nhận:

1. Câu hỏi đo được viết rõ.
2. Statistic phù hợp với câu hỏi.
3. Đơn vị của statistic đã được xác nhận.
4. Đã phân biệt counter, gauge, average và ratio.
5. Scope là instance, session, SQL cursor, PDB hay cluster.
6. Có sample ID và timestamp cho từng mốc.
7. Hai mẫu cùng DBID.
8. Hai mẫu cùng INST_ID nếu đo instance.
9. STARTUP_TIME không đổi nếu dùng counter instance.
10. Session identity không đổi nếu đo session.
11. Cursor identity không đổi nếu đo V$SQL.
12. Container identity giống nhau nếu đo PDB.
13. Mẫu đầu và cuối đều tồn tại.
14. Elapsed time được tính từ timestamp thực tế.
15. Counter không giảm hoặc reset trong window.
16. Delta không bị lấy ABS hoặc tự ép về 0.
17. Rate dùng đúng đơn vị.
18. Ratio được tính từ delta numerator/denominator.
19. Average được tính theo trọng số đúng.
20. Các metric được cộng có cùng đơn vị và cùng scope.
21. Workload đồng thời được ghi nhận.
22. Concurrency và workload volume được lưu.
23. Sampling overhead không làm méo phép đo.
24. Nếu dùng AWR, quyền sử dụng license đã được xác nhận.
25. Kết quả được giữ theo từng instance/session/child trước khi aggregate.

## 22. Ví dụ thực hành: đo redo và execute rate

Giả sử lấy hai mẫu system statistics:

| Mốc | Thời gian | Redo size | Execute count |
| --- | --- | ---: | ---: |
| Begin | 10:00:00 | 5.000.000.000 byte | 8.000.000 |
| End | 10:02:30 | 5.450.000.000 byte | 8.075.000 |

Elapsed = 150 giây.

Redo delta:

\[
5.450.000.000 - 5.000.000.000 =
450.000.000\ bytes
\]

Redo rate:

\[
450.000.000 / 150 =
3.000.000\ bytes/s
\]

Execute delta:

\[
8.075.000 - 8.000.000 = 75.000
\]

Execute rate:

\[
75.000 / 150 = 500\ executes/s
\]

Không kết luận rằng ứng dụng xử lý 500 request/second. Một request có thể thực hiện nhiều execute. Cũng không kết luận redo tăng là xấu nếu workload transaction tăng. Cần đo redo per transaction hoặc redo per business request để hiểu chi phí tương đối.

## 23. Ví dụ thực hành: phát hiện counter reset

Giả sử:

| Mốc | STARTUP_TIME | physical reads |
| --- | --- | ---: |
| Begin | 08:00 cùng ngày | 9.000.000 |
| End | 08:10 cùng ngày | 120.000 |

Delta thô là âm. Trước khi kết luận, kiểm tra:
- Instance có restart trong window không?
- Hai mẫu có cùng DBID và INST_ID không?
- Có lấy nhầm PDB hoặc container không?
- Có sai sample ID hoặc dữ liệu mẫu không?
- Statistic có semantics reset đặc biệt không?

Nếu STARTUP_TIME khác, đây là hai vòng đời instance khác nhau. Không tính rate xuyên qua restart. Chụp baseline mới sau khi instance ổn định.

## 24. Ví dụ thực hành: tổng hợp hai window có độ dài khác nhau

Giả sử:

| Window | Elapsed | Redo delta | Rate |
| --- | ---: | ---: | ---: |
| A | 60 giây | 120 MB | 2 MB/s |
| B | 300 giây | 900 MB | 3 MB/s |

Rate trung bình của toàn bộ 360 giây:

\[
(120 + 900) / (60 + 300)
= 2,83\ MB/s
\]

Trung bình cộng 2 và 3 là 2,5 MB/s, không đúng vì hai window có độ dài khác nhau.

Nếu tính theo MB/s thập phân hay MiB/s, phải dùng cùng đơn vị ở cả hai window.

## 25. Ví dụ thực hành: tính average wait từ delta

Giả sử một wait event có:

| Mốc | TOTAL_WAITS | TIME_WAITED_MICRO |
| --- | ---: | ---: |
| Begin | 100.000 | 2.000.000.000 |
| End | 130.000 | 2.750.000.000 |

Delta waits = 30.000.

Delta wait time = 750.000.000 microsecond.

Average wait:

\[
750.000.000 / 30.000
= 25.000\ microseconds = 25\ ms
\]

Không lấy AVERAGE_WAIT tại mốc cuối trừ AVERAGE_WAIT tại mốc đầu. Đó không phải average wait trong khoảng.

## 26. Lưu kết quả đo và ghi rõ giới hạn

Một báo cáo performance measurement nên lưu:
- Run ID và mục tiêu đo.
- DBID, instance, container/PDB, service.
- Startup time và version.
- Timestamp đầu/cuối.
- Metric name và unit.
- Giá trị đầu, giá trị cuối và delta.
- Elapsed seconds và rate.
- Validation status.
- Workload volume, concurrency và business request count.
- SQL_ID/plan hoặc session identity nếu có.
- Các event quản trị trong window.
- Phương pháp thu thập và license/tool nếu dùng AWR.

Ví dụ kết luận tốt:

“Trong window 10:00:00–10:02:30, instance 2 không restart. Redo size tăng 450 MB trong 150 giây, tương đương 3 MB/s. Execute count tăng 75.000, tương đương 500 execute/s. Hai chỉ số là system-level; workload khác cũng có thể đóng góp. Cần đối chiếu transaction/request count trước khi quy kết cho một ứng dụng.”

Ví dụ kết luận yếu:

“Redo size hiện tại là 5,45 GB nên database đang tạo redo quá nhiều.”

Câu thứ hai không có window, không có baseline, không có workload denominator và không xác định được mức tăng gần đây.

## 27. Bài tập tự luyện

1. Giải thích khác biệt giữa cumulative counter và gauge.
2. Vì sao V$SYSSTAT.VALUE không phải rate?
3. Tính delta khi counter tăng từ 1.200 lên 1.950.
4. Tính rate nếu delta là 750 trong 150 giây.
5. Vì sao cần dùng elapsed time thực tế?
6. Phân biệt session logical reads và physical reads.
7. Xác định unit của redo size.
8. Vì sao không cộng redo bytes với execute count?
9. Nêu những định danh cần lưu khi đo V$SYSSTAT.
10. Vì sao startup_time cần được kiểm tra?
11. Tại sao SID đơn lẻ không đủ để ghép session?
12. Nêu các định danh cần giữ khi đo V$SQL child cursor.
13. Một delta âm có thể do những nguyên nhân nào?
14. Vì sao không dùng ABS(delta)?
15. Khi nào được hiệu chỉnh counter wraparound?
16. Tính average wait từ delta wait time và delta total waits.
17. Vì sao không lấy trung bình cộng hai average wait có số wait khác nhau?
18. Tính redo per transaction từ hai delta.
19. Vì sao user commits không luôn bằng số business request?
20. Phân biệt DB time và wall-clock time.
21. Vì sao tổng DB time có thể lớn hơn elapsed window?
22. Thiết kế phép đo redo rate cho một instance RAC.
23. Vì sao cần xem từng INST_ID trước khi tính cluster total?
24. Xử lý thế nào khi một RAC instance restart giữa window?
25. Nêu rủi ro khi so counter ở CDB root với PDB.
26. DBA_HIST_SQLSTAT có các cột DELTA. Có cần lấy chênh lệch giữa hai DELTA không?
27. Vì sao AWR snapshot không nhất thiết đại diện cho một request?
28. Tổng hợp hai window 30 giây và 300 giây: tính rate trung bình thế nào?
29. Vì sao hit ratio không nên là chỉ số duy nhất để đánh giá I/O?
30. Thiết kế một measurement report có metric, scope, unit, timestamps, delta, rate, validation status và workload denominator.

**Một bộ đếm tích lũy chỉ trở thành phép đo hiệu năng có ý nghĩa khi có hai mốc cùng phạm vi và cùng vòng đời.** Hãy xác nhận identity/reset point, dùng elapsed time thực tế, tính delta trước rồi mới tính rate, average hoặc ratio. Giữ riêng các đơn vị và scope; chỉ aggregate khi các interval tương thích. Nếu counter giảm, session/cursor biến mất hoặc instance restart, đánh dấu window không hợp lệ và lấy baseline mới thay vì cố biến số liệu thành một kết quả có vẻ hợp lý.

