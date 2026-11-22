# Performance Schema: instrument, consumer và chi phí thu thập

Performance Schema là cơ chế quan sát tích hợp trong MySQL, ghi nhận hoạt động bên trong máy chủ như câu lệnh SQL, stage thực thi, wait event, khóa đồng bộ, I/O, transaction, thread và bộ nhớ. Đây là nguồn dữ liệu nền tảng để tìm câu lệnh tốn thời gian, xác định điểm nghẽn I/O, phân tích contention và theo dõi tài nguyên.

Muốn dùng Performance Schema hiệu quả, cần phân biệt hai khái niệm. **Instrument** là bộ phận tạo sự kiện đo lường; **consumer** là nơi tiếp nhận và lưu sự kiện để truy vấn. Bật quá nhiều instrument, bật đo thời gian cho mọi hoạt động hoặc giữ lịch sử dài có thể làm tăng CPU, bộ nhớ và chi phí đồng bộ. Ngược lại, tắt sai consumer có thể khiến dữ liệu cần phân tích không được ghi nhận.

Trong module **DATABASE_MYSQL**, bài học này giải thích kiến trúc instrument/consumer, các bảng cấu hình, luồng current/history/summary, timer, bộ lọc thread/object, chi phí thu thập và cách bật instrumentation có chọn lọc. Các ví dụ tập trung vào MySQL 8.4; tên instrument, consumer và biến cấu hình có thể khác theo phiên bản hoặc storage engine, vì vậy cần kiểm tra trực tiếp trên instance đang vận hành.

## 1. Performance Schema dùng để làm gì?

Performance Schema cung cấp dữ liệu quan sát nội bộ của MySQL. Các nhóm hoạt động thường được theo dõi gồm:

- Statement: câu lệnh SQL và số liệu thực thi.
- Stage: các giai đoạn bên trong quá trình xử lý câu lệnh.
- Wait: thời gian chờ I/O, mutex, condition, lock và các tài nguyên khác.
- Transaction: thời lượng và trạng thái transaction.
- File và table I/O: hoạt động đọc/ghi file, table handle và socket.
- Memory: lượng bộ nhớ được cấp phát theo instrument.
- Thread: thread foreground của client và thread background của server.
- Metadata lock: trạng thái chờ khóa metadata.

Performance Schema giúp trả lời những câu hỏi vận hành như:

- Câu SQL nào tiêu tốn tổng thời gian nhiều nhất?
- Câu nào chạy lâu bất thường hoặc đọc quá nhiều hàng?
- Thread đang chờ loại tài nguyên nào?
- Có nhiều thời gian chờ file I/O, mutex hay metadata lock không?
- Nhóm câu lệnh nào tạo nhiều lượt gọi hoặc lỗi?
- Instrument nào đang tiêu thụ nhiều bộ nhớ?

Performance Schema là hệ thống đo lường trong bộ nhớ, không phải kho lưu lịch sử dài hạn. Dữ liệu trong các bảng sự kiện và summary thường được khởi tạo lại khi MySQL khởi động lại; bảng history có dung lượng giới hạn và dữ liệu cũ có thể bị ghi đè. Nếu cần lưu số liệu dài hạn, cần thu thập định kỳ sang hệ thống monitoring hoặc telemetry bên ngoài.

### 1.1. Phân biệt Performance Schema với các công cụ khác

| Công cụ | Mục đích chính | Dữ liệu điển hình |
|---|---|---|
| Performance Schema | Quan sát hoạt động bên trong MySQL | Statement, wait, stage, thread, memory, I/O |
| sys schema | View và helper dễ đọc dựa trên Performance Schema | Top statement, wait latency, memory, lock waits |
| Slow query log | Ghi câu lệnh vượt ngưỡng hoặc tiêu chí log | SQL text, thời gian, số hàng theo cấu hình |
| General query log | Ghi nhận kết nối và câu lệnh ở mức tổng quát | Query log theo thứ tự nhận |
| Audit plugin | Ghi sự kiện phục vụ yêu cầu kiểm toán | Kết nối, truy cập và hoạt động theo chính sách audit |
| Hệ thống metrics bên ngoài | Theo dõi xu hướng và cảnh báo theo thời gian | CPU, RAM, disk, replication lag, latency |

Performance Schema bổ sung cho slow query log và monitoring bên ngoài. Không nên dùng nó như audit log bất biến: history có thể bị ghi đè, dữ liệu chỉ tồn tại trong bộ nhớ và một số câu SQL có thể bị cắt ngắn theo giới hạn cấu hình.

## 2. Kiến trúc instrument và consumer

Có thể hình dung quá trình thu thập như sau:

```text
Hoạt động bên trong MySQL
          |
          v
      Instrument
  (phát hiện sự kiện,
   có thể đo thời gian)
          |
          v
       Consumer
 (chọn loại sự kiện và
  nơi nhận dữ liệu)
          |
          v
  Current / History / Summary
          |
          v
 Performance Schema tables
          |
          v
   SQL query / sys views
          |
          v
 Dashboard, alert, phân tích
```

### 2.1. Instrument là nguồn tạo sự kiện

Instrument mô tả một loại hoạt động MySQL có thể đo lường. Ví dụ:

| Nhóm instrument | Ví dụ tên | Ý nghĩa |
|---|---|---|
| Statement | statement/sql/select | Thực thi câu SELECT |
| Statement | statement/sql/insert | Thực thi câu INSERT |
| Stage | stage/sql/Opening tables | Một stage xử lý SQL |
| File I/O | wait/io/file/sql/binlog | Chờ I/O file binlog |
| Socket I/O | wait/io/socket/sql/client_connection | Hoạt động socket client |
| Metadata lock | wait/lock/metadata/sql/mdl | Chờ metadata lock |
| Mutex | wait/synch/mutex/innodb/% | Chờ mutex InnoDB |
| Memory | memory/innodb/% | Cấp phát bộ nhớ thuộc InnoDB |

Tên instrument thường có cấu trúc phân cấp. Có thể lọc bằng LIKE để chọn cả nhóm hoặc một instrument cụ thể.

Instrument thường có hai thuộc tính quan trọng:

- ENABLED: có thu thập sự kiện của instrument hay không.
- TIMED: có đo thời gian cho sự kiện hay không.

Khi ENABLED=NO, sự kiện tương ứng không được instrument tạo ra. Khi ENABLED=YES và TIMED=NO, MySQL có thể thu thập sự kiện mà không ghi thời lượng; các cột timer tương ứng có thể là NULL. Khi TIMED=YES, MySQL đọc timer để đo thời gian, làm tăng thêm chi phí đo lường.

### 2.2. Consumer là nơi nhận sự kiện

Consumer quyết định loại sự kiện nào được ghi vào các bảng Performance Schema. Một instrument có thể được bật nhưng không có consumer phù hợp để lưu một loại event history; ngược lại, bật consumer không tự tạo sự kiện nếu instrument hoặc thread instrumentation bị tắt.

Những consumer thường gặp:

| Consumer | Vai trò |
|---|---|
| global_instrumentation | Bật tầng thu thập instrumentation toàn cục |
| thread_instrumentation | Cho phép thu thập theo thread |
| events_waits_current | Sự kiện wait đang diễn ra |
| events_waits_history | Lịch sử wait gần đây theo thread |
| events_waits_history_long | Lịch sử wait dùng chung toàn server |
| events_stages_current | Stage đang diễn ra |
| events_stages_history | Lịch sử stage theo thread |
| events_stages_history_long | Lịch sử stage toàn server |
| events_statements_current | Statement đang diễn ra |
| events_statements_history | Lịch sử statement theo thread |
| events_statements_history_long | Lịch sử statement toàn server |
| events_transactions_current | Transaction đang diễn ra |
| events_transactions_history | Lịch sử transaction theo thread |
| events_transactions_history_long | Lịch sử transaction toàn server |
| statements_digest | Thu thập và tổng hợp statement digest |

Danh sách consumer thực tế tùy phiên bản. Không nên giả định mọi tên đều tồn tại trên mọi bản MySQL; hãy đọc bảng setup_consumers trước khi thay đổi.

### 2.3. Quan hệ phụ thuộc giữa các consumer

Một số consumer tạo thành tầng phụ thuộc. Mô hình khái quát:

```text
global_instrumentation
        |
        v
thread_instrumentation
        |
        +-----------------------------+
        |              |              |
        v              v              v
events_waits_current  events_stages_current  events_statements_current
        |              |              |
        v              v              v
history / history_long  history / history_long  history / history_long

statements_digest (consumer tổng hợp digest riêng)
```

Nếu tầng global hoặc thread bị tắt, việc bật consumer ở tầng thấp hơn không có nghĩa dữ liệu sẽ được thu thập như mong muốn. statements_digest là consumer riêng cho tổng hợp digest; không cần bật history_long chỉ để đọc bảng tổng hợp theo digest.

Hãy xem trạng thái thực tế thay vì ghi nhớ một cấu hình cố định:

```sql
SELECT
    NAME,
    ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

## 3. Các bảng cấu hình chính

Performance Schema cung cấp các bảng setup để kiểm soát instrument, consumer, timer và bộ lọc đối tượng/thread.

| Bảng | Vai trò |
|---|---|
| setup_instruments | Bật/tắt instrument và đo thời gian |
| setup_consumers | Bật/tắt consumer |
| setup_timers | Chọn timer cho nhóm event |
| setup_actors | Lọc thread foreground theo user/host/role |
| setup_objects | Lọc instrumentation theo object |
| threads | Thông tin thread và cờ instrument/history |
| performance_timers | Các timer mà server hỗ trợ |

### 3.1. Đọc setup_instruments

Xem các instrument statement:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/sql/%'
ORDER BY NAME
LIMIT 30;
```

Xem các instrument wait:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/%'
ORDER BY NAME
LIMIT 30;
```

Có thể tìm theo một nhóm cụ thể:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/metadata/%';
```

Không phải instrument nào cũng được hỗ trợ bởi mọi engine hoặc build. Một số instrument được bật mặc định, một số tắt mặc định. Dùng dữ liệu trả về để quyết định, không áp đặt một danh sách giả định.

### 3.2. Đọc setup_consumers

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

Truy vấn này cho biết các consumer hiện được bật. Nên lưu kết quả trước khi thay đổi để có thể khôi phục đúng cấu hình ban đầu sau một đợt điều tra.

### 3.3. Đọc setup_timers và performance_timers

Timer được dùng để đo thời lượng wait, stage và statement. Kiểm tra timer được gán cho từng loại event:

```sql
SELECT *
FROM performance_schema.setup_timers;
```

Xem timer khả dụng:

```sql
SELECT *
FROM performance_schema.performance_timers;
```

Các cột timer mô tả tên timer, tần số, độ phân giải và overhead đo lường. Tên timer được chọn phụ thuộc nền tảng và MySQL. Không tự giả định mọi server dùng cùng loại timer hoặc cùng độ phân giải.

### 3.4. setup_actors, setup_objects và threads

setup_actors cho phép áp dụng cấu hình instrumentation cho thread foreground theo user, host và role. Nó hữu ích khi muốn tập trung theo dõi một nhóm kết nối ứng dụng hoặc loại trừ nhóm không cần đo.

setup_objects điều khiển instrumentation cho các đối tượng như schema, table, stored program hoặc event theo các cột filter mà phiên bản hỗ trợ.

Bảng threads cho biết thread của MySQL và các cờ liên quan. Ví dụ:

```sql
SELECT
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    INSTRUMENTED,
    HISTORY
FROM performance_schema.threads
ORDER BY TYPE, THREAD_ID;
```

- INSTRUMENTED cho biết thread có được instrument hay không.
- HISTORY cho biết có lưu lịch sử event cho thread hay không.
- Thread background và foreground có thể có cách áp dụng filter khác nhau.

Không nên tắt instrumentation trên thread chỉ vì chưa cần phân tích. Một thay đổi rộng có thể khiến dữ liệu quan trọng biến mất khỏi các bảng history.

## 4. Nhóm event current, history và history_long

Các bảng event thường có ba dạng lưu trữ:

| Dạng | Phạm vi | Cách hiểu |
|---|---|---|
| current | Event đang diễn ra | Trạng thái hiện thời của mỗi thread/event |
| history | Một vùng lịch sử giới hạn theo thread | Các event gần đây của từng thread |
| history_long | Vùng lịch sử giới hạn dùng chung toàn server | Event gần đây từ nhiều thread |

Ví dụ với statement:

- events_statements_current
- events_statements_history
- events_statements_history_long

Các nhóm wait, stage và transaction có cấu trúc tương tự nếu phiên bản cung cấp.

### 4.1. Current không phải nhật ký hoàn chỉnh

Bảng current giúp xem hoạt động đang diễn ra tại thời điểm truy vấn. Nếu statement đã kết thúc trước khi truy vấn, nó có thể không còn trong current. Để điều tra event vừa hoàn tất, dùng history hoặc history_long nếu consumer tương ứng được bật.

### 4.2. History có giới hạn

History là vùng đệm vòng. Khi đạt giới hạn, event mới có thể thay thế event cũ. History thường được tổ chức theo thread, trong khi history_long dùng chung cho toàn server.

Do history_long chia sẻ giữa các thread, workload nhiều event có thể ghi đè dữ liệu nhanh hơn. Bật history_long trong thời gian dài có thể tăng bộ nhớ và chi phí ghi event. Dùng nó cho điều tra có mục tiêu, không mặc định bật tất cả lịch sử ở mọi hệ thống.

### 4.3. Summary lưu số liệu tổng hợp

Summary tables tổng hợp số lần, thời gian, lỗi hoặc lượng dữ liệu theo một chiều như event name, thread, account, user, host, table hoặc digest.

Summary thường phù hợp để trả lời câu hỏi xu hướng và xếp hạng top workload. History phù hợp để xem chi tiết một event gần đây. Hai loại dữ liệu có mục đích khác nhau.

## 5. Statement digest và phân tích câu SQL

Digest chuẩn hóa câu lệnh để gom các câu có cấu trúc giống nhau. Ví dụ hai câu:

```sql
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 202;
```

có thể được gom vào cùng một digest vì literal được chuẩn hóa. Digest giúp phân tích workload theo mẫu SQL thay vì từng giá trị tham số.

Bảng events_statements_summary_by_digest cung cấp số liệu tổng hợp theo digest. Consumer statements_digest cần được bật để thu thập digest.

### 5.1. Xếp hạng câu SQL theo tổng thời gian

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_ERRORS,
    SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 15;
```

Timer trong các cột TIMER_WAIT của Performance Schema được biểu diễn theo picosecond. Chia cho 10^12 để đổi sang giây. Khi so sánh, cần phân biệt tổng thời gian với thời gian trung bình: một digest có tổng thời gian cao có thể do chạy nhiều lần, trong khi một digest có thời gian trung bình cao có thể là câu lệnh chậm riêng lẻ.

### 5.2. Tìm câu lệnh đọc quá nhiều hàng

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        2
    ) AS examined_to_sent_ratio,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 15;
```

Tỷ lệ examined/sent lớn có thể gợi ý truy vấn đọc nhiều hàng để trả ít kết quả. Đây chỉ là tín hiệu sàng lọc; truy vấn tổng hợp, báo cáo hoặc phép join có thể cần đọc nhiều hàng theo thiết kế.

### 5.3. Đọc lịch sử statement gần đây

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS duration_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_START DESC
LIMIT 20;
```

SQL_TEXT có thể bị giới hạn độ dài và có thể chứa literal do client gửi. Không coi history_long là log đầy đủ hoặc nguồn audit. Nếu consumer history_long đang tắt, bảng có thể không chứa event mới.

TIMER_START là giá trị từ timer nội bộ, không phải timestamp lịch treo tường. Khi cần đối chiếu với log ứng dụng, hãy dùng các cột thời gian thực mà bảng cung cấp (nếu có) hoặc ghép theo thread/event và cửa sổ quan sát; không diễn giải TIMER_START trực tiếp thành ngày giờ.

## 6. Phân tích wait và stage

Một câu SQL chậm không nhất thiết tiêu tốn toàn bộ thời gian trên CPU. Nó có thể dành phần lớn thời gian chờ storage, mutex, metadata lock hoặc network.

### 6.1. Xếp hạng wait theo tổng thời gian

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Nhóm wait có tổng thời gian cao có thể chỉ ra khu vực cần điều tra. Cần đọc event name, số lần và thời gian trung bình cùng nhau. Một loại wait có số lần cực lớn nhưng mỗi lần rất ngắn cũng có thể tạo tổng thời gian đáng kể.

### 6.2. Phân biệt wait và stage

- Wait biểu diễn một thread phải chờ tài nguyên hoặc hoạt động bên ngoài.
- Stage biểu diễn một giai đoạn xử lý của câu lệnh, ví dụ mở bảng, tối ưu hóa, gửi dữ liệu hoặc thực hiện sort.

Stage có thể chứa nhiều wait bên trong. Không cộng tổng thời gian stage và wait như các đại lượng độc lập vì có thể đếm trùng khoảng thời gian.

### 6.3. Dùng sys schema để đọc nhanh

sys schema cung cấp các view dễ đọc hơn trên dữ liệu Performance Schema. Ví dụ:

```sql
SELECT *
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
```

Xem wait theo latency:

```sql
SELECT *
FROM sys.waits_global_by_latency
LIMIT 20;
```

Các view sys có thể khác giữa phiên bản. Kiểm tra định nghĩa view hoặc tài liệu trước khi dựa vào tên cột trong dashboard tự xây dựng.

## 7. Bật instrumentation có chọn lọc

Một nguyên tắc quan trọng là bắt đầu từ câu hỏi điều tra. Nếu cần tìm statement chậm, không cần bật toàn bộ instrument mutex, file, memory và socket ngay từ đầu.

### 7.1. Kiểm tra Performance Schema đang hoạt động

```sql
SHOW VARIABLES LIKE 'performance_schema';
```

Nếu Performance Schema bị tắt khi server khởi động, không thể bật nó bằng UPDATE setup_instruments hoặc SET GLOBAL thông thường. Cần cấu hình tham số khởi động phù hợp và restart MySQL theo quy trình bảo trì.

Nếu đã bật, kiểm tra các consumer và instrument cần dùng trước khi thay đổi.

### 7.2. Bật statement instrumentation và digest

Ví dụ bật tầng global/thread, statement current/history và digest:

```sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long',
    'statements_digest'
);
```

Bật nhóm instrument statement và đo thời gian:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'statement/sql/%';
```

Đây là ví dụ cho một đợt điều tra statement. Trước khi chạy, lưu trạng thái ban đầu của các hàng sẽ thay đổi. Nếu hệ thống có nhiều kết nối và workload lớn, chỉ bật history_long khi cần xem event chi tiết gần đây; digest summary có thể đáp ứng nhu cầu xếp hạng tổng hợp với chi phí và dung lượng khác.

### 7.3. Bật wait instrumentation theo nhóm

Nếu giả thuyết là contention hoặc I/O, bật đúng nhóm liên quan. Ví dụ kiểm tra metadata lock:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/metadata/%';
```

Nếu cần xem event wait trong một cửa sổ điều tra, trước hết bật các consumer cần thiết:

```sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_waits_current',
    'events_waits_history',
    'events_waits_history_long'
);
```

Sau đó mới bật nhóm instrument metadata lock:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'wait/lock/metadata/%';
```

Không mở rộng thành tất cả wait/synch hoặc wait/io chỉ vì muốn “có thêm dữ liệu”. Hãy bật nhóm cần thiết, đo chi phí và tắt lại khi đã đủ bằng chứng.

Khi kết thúc, khôi phục chính xác trạng thái ENABLED/TIMED ban đầu đã ghi lại. Chỉ đặt consumer hoặc instrument về NO nếu trạng thái trước điều tra của nó là NO; không dùng một lệnh tắt hàng loạt có thể vô tình làm mất instrumentation vốn đã được hệ thống giám sát sử dụng.

### 7.4. Bật không đồng nghĩa có dữ liệu hồi tố

Khi bật instrument hoặc consumer, MySQL chỉ thu thập event phát sinh sau thời điểm thay đổi. Nó không tái tạo event đã xảy ra trước đó. Vì vậy, hãy để workload chạy đủ lâu sau khi bật rồi mới đọc summary/history.

## 8. Chi phí thu thập và các yếu tố ảnh hưởng

Performance Schema được thiết kế để quan sát với overhead thấp, nhưng không miễn phí. Chi phí phụ thuộc số instrument, loại event, timer, số thread, tần suất event, consumer và kích thước vùng history.

### 8.1. Chi phí của instrument

Instrument càng chi tiết, MySQL càng phải kiểm tra trạng thái và phát sinh event tại các điểm đo. Những nhóm event có tần suất rất cao như mutex, condition, socket hoặc file I/O có thể tạo số lượng lớn event.

Bật một instrument không nhất thiết gây overhead đáng kể trong mọi workload. Cần đánh giá dựa trên tần suất hoạt động thực tế và phép đo trước/sau.

### 8.2. Chi phí của TIMED

Đo thời gian cần đọc timer và ghi giá trị timer vào event. Với instrument tần suất cao, việc đo thời gian có thể tăng chi phí CPU hơn so với chỉ ghi nhận event.

Nếu chỉ cần đếm số lần hoặc phát hiện loại hoạt động, có thể cân nhắc ENABLED=YES nhưng TIMED=NO cho instrument hỗ trợ chế độ này. Khi đó không có số liệu duration để xếp hạng latency.

### 8.3. Chi phí của consumer và history

Consumer current/history làm tăng số event được ghi vào các cấu trúc tương ứng. History_long dùng chung cho toàn server; workload lớn có thể lấp đầy và ghi đè nhanh. Tăng kích thước history giúp giữ nhiều event hơn nhưng làm tăng bộ nhớ được cấp phát.

Một số biến điều chỉnh dung lượng Performance Schema có tiền tố performance_schema_events_..._history_size hoặc performance_schema_max_.... Nhiều tham số sizing được xác định khi server khởi động. Kiểm tra giá trị và phạm vi thay đổi trước khi chỉnh:

```sql
SHOW VARIABLES LIKE 'performance_schema%history%size';
SHOW VARIABLES LIKE 'performance_schema_max%';
```

Không tăng mọi giới hạn tối đa theo suy đoán. Cần tính ngân sách RAM và xác định dữ liệu lịch sử thực sự cần giữ.

### 8.4. Chi phí theo thread và object

Instrument mọi user/host/table có thể làm phạm vi thu thập rộng hơn cần thiết. setup_actors và setup_objects giúp giới hạn đối tượng quan sát theo mục tiêu.

Lọc có thể làm mất dữ liệu cần thiết nếu điều kiện quá hẹp. Trước khi áp dụng filter, xác định thread ứng dụng, background thread và object nào nằm trong phạm vi điều tra.

## 9. Đo chi phí Performance Schema một cách có kiểm soát

Không nên kết luận Performance Schema “nhẹ” hoặc “nặng” chỉ từ cảm giác. Hãy đo trên workload đại diện.

Quy trình gợi ý:

1. Ghi nhận cấu hình Performance Schema hiện tại.
2. Chọn một workload có thể lặp lại.
3. Thu thập baseline CPU, throughput, latency p95/p99, RAM và disk I/O.
4. Bật một nhóm instrument/consumer phục vụ câu hỏi cụ thể.
5. Chạy lại cùng workload trong điều kiện gần tương đương.
6. So sánh latency, throughput, CPU, memory và số event.
7. Tăng phạm vi từng bước nếu chưa đủ dữ liệu.
8. Tắt nhóm không còn cần và ghi lại cấu hình cuối.

Không so sánh hai lần chạy nếu lượng request, cache state, dữ liệu hoặc tải nền khác biệt lớn. Có thể lặp nhiều lần và dùng median/percentile để giảm ảnh hưởng của biến động ngẫu nhiên.

### 9.1. Theo dõi event bị mất

Kiểm tra các status counter liên quan đến Performance Schema:

```sql
SHOW GLOBAL STATUS LIKE 'Performance_schema%lost';
```

Các counter lost có thể chỉ ra cấu trúc hoặc lớp instrumentation không đủ dung lượng cho số lượng event/đối tượng hiện tại. Tên counter tùy phiên bản và loại instrument. Nếu counter tăng, kiểm tra nhóm cụ thể trước khi tăng sizing.

Không phải mọi event bị ghi đè trong history ring buffer đều đồng nghĩa một lỗi lost counter. History được thiết kế để giữ một cửa sổ gần đây; dữ liệu cũ bị thay thế là hành vi bình thường khi buffer đầy.

### 9.2. Theo dõi bộ nhớ được Performance Schema sử dụng

Nếu memory instrumentation khả dụng và được bật, có thể xem memory summary:

```sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
```

Hoặc dùng sys view:

```sql
SELECT *
FROM sys.memory_global_by_current_bytes
LIMIT 20;
```

Số liệu chỉ phản ánh allocation mà MySQL đã instrument. Không xem tổng này là toàn bộ RSS của tiến trình; còn có allocator overhead, shared library, buffer và bộ nhớ không được instrument.

## 10. Bảo mật và giới hạn dữ liệu quan sát

Performance Schema có thể chứa SQL_TEXT, tên user, host, object, schema và thông tin về workload. Một số câu lệnh có literal nhạy cảm trong text; digest chuẩn hóa giúp giảm phụ thuộc vào literal nhưng không xóa mọi thông tin nhận diện.

Thực hành phù hợp:

- Cấp quyền SELECT trên các bảng/view cần thiết, không cấp quyền quản trị rộng cho dashboard.
- Giới hạn người có thể UPDATE setup tables.
- Không xuất SQL_TEXT hoặc hostname nội bộ ra hệ thống không được phép.
- Đặt retention và quyền truy cập cho dữ liệu monitoring bên ngoài.
- Không dùng Performance Schema thay thế audit trail khi cần bằng chứng kiểm toán đầy đủ.
- Xem xét việc truy vấn history có thể trả dữ liệu nhạy cảm trước khi cấp quyền đọc.

Khi chia sẻ kết quả điều tra, loại bỏ password, token, literal chứa dữ liệu cá nhân và thông tin hạ tầng không cần thiết.

## 11. Workflow điều tra một câu SQL chậm

Giả sử ứng dụng phản ánh endpoint danh sách đơn hàng chậm. Một quy trình thực tế:

**Bước 1 — Xác nhận câu SQL hoặc digest**

Dùng events_statements_summary_by_digest để tìm mẫu SQL có tổng thời gian, thời gian trung bình hoặc rows examined cao.

**Bước 2 — Xem event gần đây**

Nếu history_long được bật, đọc SQL_TEXT, TIMER_WAIT, ROWS_EXAMINED, ROWS_SENT và MYSQL_ERRNO. Kiểm tra thời điểm, thread và số lần chạy.

**Bước 3 — Đọc execution plan**

Dùng EXPLAIN hoặc EXPLAIN ANALYZE trong môi trường phù hợp để hiểu access path, index, join và số hàng. Performance Schema chỉ cho số liệu quan sát; nó không thay thế optimizer plan.

**Bước 4 — Kiểm tra wait**

Nếu statement latency cao nhưng CPU không tương ứng, xem wait summary và metadata lock để tìm thời gian chờ I/O, lock hoặc tài nguyên đồng bộ.

**Bước 5 — Thay đổi một yếu tố**

Có thể sửa index, truy vấn, transaction scope hoặc cấu hình. Chỉ thay một yếu tố chính trong mỗi lần đo để dễ quy kết tác động.

**Bước 6 — Đo lại và lưu kết quả**

So sánh cùng digest, cùng workload và cùng cửa sổ thời gian. Ghi lại throughput, p95/p99, rows examined, wait và CPU trước/sau.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Instrument và consumer là một | Instrument tạo event; consumer chọn nơi nhận | Kiểm tra setup_instruments và setup_consumers riêng |
| Bật consumer là đủ | Còn phụ thuộc global/thread và instrument | Kiểm tra cả tầng phụ thuộc |
| Bật TIMED=YES không có chi phí | Timer read và lưu thời lượng có overhead | Bật timing theo nhóm cần đo |
| History lưu mọi event mãi mãi | History là buffer giới hạn, event cũ bị ghi đè | Export định kỳ nếu cần lưu dài hạn |
| History_long là per-thread | Đây là vùng lịch sử dùng chung toàn server | Cân nhắc tải và dung lượng |
| Digest thay thế SQL history | Digest tổng hợp mẫu SQL, không giữ từng lần chạy | Dùng history khi cần event cụ thể |
| Performance Schema là audit log | Dữ liệu trong bộ nhớ, có giới hạn và không bền vững | Dùng audit mechanism chuyên biệt |
| Mọi instrument đều bật mặc định | Trạng thái phụ thuộc phiên bản và cấu hình | Query setup tables |
| Bật instrumentation sẽ có dữ liệu quá khứ | Chỉ event sau thời điểm bật được thu thập | Chờ workload phát sinh rồi truy vấn |
| Lost counter tăng là do history ghi đè | Hai cơ chế khác nhau | Phân biệt lost counters với ring buffer rollover |
| Memory summary bằng RSS tiến trình | Chỉ gồm allocation được instrument | So sánh với OS/container metrics |
| Nên bật toàn bộ instrument để phòng khi cần | Phạm vi rộng tăng overhead và dữ liệu nhạy cảm | Bật theo giả thuyết và thời gian điều tra |

## 13. Checklist cấu hình Performance Schema

**Trước khi bật:**

- Xác nhận performance_schema đang ON.
- Lưu trạng thái setup_instruments và setup_consumers hiện tại.
- Xác định câu hỏi điều tra: statement, wait, stage, memory hay lock.
- Chọn instrument và consumer nhỏ nhất đủ trả lời câu hỏi.
- Kiểm tra ngân sách bộ nhớ và các biến history size.
- Xác định quyền đọc/ghi Performance Schema.

**Trong khi thu thập:**

- Bật global/thread consumer nếu cần.
- Chỉ bật nhóm instrument liên quan.
- Chỉ bật TIMED khi cần latency.
- Chỉ bật history_long khi cần event detail trên toàn server.
- Đợi workload phát sinh sau khi bật.
- Theo dõi CPU, latency, memory và lost counters.

**Sau khi điều tra:**

- Export số liệu cần giữ.
- Khôi phục các trạng thái setup ban đầu không còn cần.
- Xác nhận dashboard vẫn có dữ liệu mong muốn.
- Ghi lại thay đổi, khoảng thời gian và overhead đo được.
- Không để instrumentation mở rộng vô thời hạn nếu không có mục tiêu vận hành rõ ràng.

## 14. Ghi nhớ

- Performance Schema quan sát hoạt động nội bộ MySQL bằng dữ liệu trong bộ nhớ.
- Instrument là nguồn phát sinh event; consumer chọn loại event và nơi lưu.
- setup_instruments điều khiển ENABLED và TIMED; setup_consumers điều khiển nơi nhận event.
- global_instrumentation và thread_instrumentation là các tầng quan trọng trong luồng thu thập.
- Current cho hoạt động đang diễn ra; history theo thread; history_long dùng chung toàn server.
- Summary tables và statement digest phù hợp để xếp hạng workload.
- Timer trong các cột TIMER_WAIT được biểu diễn theo picosecond.
- TIMED=YES cung cấp latency nhưng làm tăng chi phí đo lường.
- History có dung lượng giới hạn; tăng history size có thể tăng bộ nhớ.
- setup_actors, setup_objects và threads giúp giới hạn phạm vi thu thập.
- sys schema cung cấp view dễ đọc trên Performance Schema.
- Bật instrument/consumer chỉ thu thập event phát sinh sau thời điểm bật.
- Theo dõi Performance_schema%lost và memory summary để đánh giá giới hạn thu thập.
- SQL_TEXT có thể chứa thông tin nhạy cảm; cấp quyền đọc theo nguyên tắc tối thiểu.
- Không bật tất cả instrument theo mặc định; bắt đầu từ câu hỏi điều tra và đo overhead trước/sau.

Performance Schema hữu ích nhất khi được cấu hình có mục tiêu. Chọn đúng instrument, consumer và mức timing sẽ cung cấp đủ bằng chứng để chẩn đoán workload mà vẫn kiểm soát chi phí CPU, bộ nhớ và độ nhạy cảm của dữ liệu quan sát.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Performance Schema: https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html
- MySQL 8.4 Reference Manual — Performance Schema Quick Start: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-quick-start.html
- MySQL 8.4 Reference Manual — Performance Schema Instrument Naming Conventions: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-instrument-naming.html
- MySQL 8.4 Reference Manual — Performance Schema Event Consumers: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-consumer-config.html
- MySQL 8.4 Reference Manual — Performance Schema Event Timing: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-timing.html
- MySQL 8.4 Reference Manual — Performance Schema Statement Digests: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-statement-digests.html
- MySQL 8.4 Reference Manual — Performance Schema Memory Allocation: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-memory-model.html
- MySQL 8.4 Reference Manual — The sys Schema: https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html

