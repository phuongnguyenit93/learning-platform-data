# Theo dõi phiên đang chạy, giao dịch đang mở và truy vấn chờ

Khi cơ sở dữ liệu phản hồi chậm, các chỉ số tổng thể như CPU, bộ nhớ hay I/O chỉ cho biết hệ thống đang chịu áp lực ở đâu. Để tìm nguyên nhân cụ thể, người vận hành cần quan sát những phiên kết nối đang làm việc, giao dịch nào vẫn còn mở, câu truy vấn nào đang chờ và phiên nào đang giữ tài nguyên khiến phiên khác không thể tiếp tục.

Trong phạm vi **DATABASE_PERFORMANCE**, phương pháp tối ưu hiệu năng phải dựa trên đo đạc tải, thống kê, kế hoạch thực thi và cơ chế truy cập dữ liệu. Theo dõi phiên, giao dịch và truy vấn chờ là một phần quan trọng của khả năng quan sát hệ thống (system observability). Nó giúp nối các biểu hiện như độ trễ tăng hoặc throughput giảm với hoạt động cụ thể bên trong cơ sở dữ liệu.

Bài học này trình bày cách phân biệt phiên, truy vấn và giao dịch; cách đọc trạng thái đang chạy và đang chờ; cách nhận diện giao dịch mở lâu, phiên chặn và phiên bị chặn; cách lấy mẫu theo thời gian; cùng những lưu ý khi điều tra trên PostgreSQL và MySQL.

## 1. Phân biệt phiên, truy vấn và giao dịch

Ba khái niệm thường xuất hiện cùng nhau nhưng mô tả các phạm vi khác nhau.

### Phiên kết nối (session)

Phiên là ngữ cảnh kết nối giữa ứng dụng hoặc người dùng với hệ quản trị cơ sở dữ liệu. Một phiên có thể thực hiện nhiều câu SQL theo thời gian. Trong mô hình kết nối thông thường, một connection tương ứng với một session hoặc một backend xử lý; chi tiết phụ thuộc kiến trúc và hệ quản trị.

Thông tin hữu ích của một phiên thường gồm:

- Mã phiên hoặc process ID.
- Người dùng cơ sở dữ liệu và cơ sở dữ liệu đang kết nối.
- Tên ứng dụng, máy khách hoặc địa chỉ nguồn.
- Trạng thái phiên.
- Thời điểm phiên chuyển sang trạng thái hiện tại.
- Sự kiện chờ và tài nguyên liên quan.
- Câu SQL hiện tại hoặc câu SQL gần nhất.

Một phiên đang mở không đồng nghĩa với một truy vấn đang chạy. Ứng dụng thường giữ kết nối trong connection pool để tái sử dụng. Một phiên ở trạng thái nhàn rỗi có thể hoàn toàn bình thường.

### Truy vấn hoặc câu lệnh (statement)

Truy vấn là một câu SQL được gửi để thực thi. Một phiên có thể thực hiện nhiều câu lệnh tuần tự. Một câu lệnh có thể đang chạy, đang chờ tài nguyên hoặc đã hoàn thành.

Khi quan sát truy vấn, hãy phân biệt:

- Thời điểm câu lệnh bắt đầu.
- Thời gian câu lệnh đã chạy hoặc đã chờ.
- Trạng thái thực thi.
- CPU time, thời gian chờ và thời gian I/O nếu có số liệu.
- Số dòng đọc, số dòng trả về và lượng dữ liệu trung gian.
- Kế hoạch thực thi và các sự kiện chờ liên quan.

Một câu SQL mất 5 giây chưa chắc tiêu thụ 5 giây CPU. Nó có thể chỉ dùng CPU trong một phần nhỏ thời gian và dành phần còn lại để đợi khóa hoặc I/O.

### Giao dịch (transaction)

Giao dịch là một đơn vị công việc gồm một hoặc nhiều câu lệnh, được quản lý theo các quy tắc nhất quán và cô lập của hệ quản trị. Giao dịch thường kết thúc bằng COMMIT hoặc ROLLBACK.

Một giao dịch có thể chứa nhiều câu lệnh đã hoàn thành. Vì vậy, khi phiên không còn thực thi SQL nhưng giao dịch chưa kết thúc, nó vẫn có thể giữ khóa hoặc tài nguyên. Trường hợp này đặc biệt đáng chú ý khi ứng dụng để transaction mở trong lúc xử lý logic, gọi dịch vụ khác hoặc chờ người dùng.

| Đối tượng | Trả lời câu hỏi | Ví dụ trạng thái |
|---|---|---|
| Phiên | Ai đang kết nối và phiên đang ở trạng thái nào? | active, idle, sleeping |
| Truy vấn | Câu SQL nào đang thực thi hoặc chờ? | running, waiting, completed |
| Giao dịch | Đơn vị đọc ghi nào đã bắt đầu và chưa kết thúc? | open, committed, rolled back |

Khi chẩn đoán, hãy nối ba phạm vi này. Phiên đang chờ có thể đang chạy một truy vấn bị chặn bởi giao dịch lâu năm trong một phiên khác.

## 2. Đọc trạng thái phiên và sự kiện chờ

Tên trạng thái và cách biểu diễn thay đổi theo hệ quản trị, nhưng có thể nhóm thành các loại khái quát sau:

- **Đang hoạt động:** phiên đang thực thi câu lệnh hoặc xử lý công việc.
- **Nhàn rỗi:** phiên đang chờ ứng dụng gửi câu lệnh tiếp theo.
- **Nhàn rỗi trong giao dịch:** phiên không chạy câu lệnh nhưng vẫn ở trong một transaction chưa kết thúc.
- **Đang chờ tài nguyên:** phiên cần khóa, I/O, bộ nhớ hoặc một tài nguyên khác để tiếp tục.
- **Bị chặn:** phiên không thể tiếp tục vì một phiên khác đang giữ tài nguyên cần thiết.

Không nên xem mọi trạng thái chờ là lỗi. Một số sự kiện chờ ngắn là bình thường. Điều cần quan tâm là thời lượng, tần suất, số phiên bị ảnh hưởng, tác động đến độ trễ và throughput, cùng nguyên nhân tạo ra hàng đợi.

### Sự kiện chờ (wait event)

Wait event mô tả lý do một tiến trình hoặc phiên đang chờ. Các nhóm thường gặp gồm:

| Nhóm chờ | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Lock / khóa | Đang chờ một khóa do phiên khác giữ | Tìm phiên chặn, giao dịch mở lâu và phạm vi dòng bị khóa |
| I/O | Đang chờ đọc hoặc ghi dữ liệu | Đối chiếu I/O latency, lượng block đọc/ghi và kế hoạch truy vấn |
| Buffer / memory | Đang chờ buffer, bộ nhớ hoặc cấu trúc dùng chung | Xem áp lực bộ nhớ, buffer contention và số phiên đồng thời |
| Latch / internal synchronization | Đang chờ đồng bộ nội bộ của hệ quản trị | Xem loại latch, điểm nóng cấu trúc và mẫu workload |
| Client / network | Cơ sở dữ liệu hoặc tiến trình đang chờ phía client | Kiểm tra ứng dụng có đọc kết quả chậm, giữ kết nối hoặc ngừng gửi dữ liệu |
| Connection pool | Ứng dụng chờ lấy kết nối trước khi SQL được gửi | Xem pool metrics ở tầng ứng dụng; DB có thể chưa ghi nhận yêu cầu đang chờ |

Một wait event chỉ mô tả điều đang xảy ra tại thời điểm lấy mẫu. Nó chưa tự chứng minh nguyên nhân gốc. Ví dụ, chờ I/O có thể do thiết bị lưu trữ chậm, nhưng cũng có thể do một truy vấn đọc quá nhiều dữ liệu. Chờ khóa có thể bắt nguồn từ một giao dịch giữ khóa lâu, hoặc do nhiều giao dịch cùng cập nhật một điểm nóng.

### Phân biệt thời gian chạy và thời gian chờ

Độ trễ câu lệnh có thể gồm nhiều thành phần:

- Thời gian lập kế hoạch.
- Thời gian xử lý CPU.
- Thời gian chờ khóa.
- Thời gian chờ đọc/ghi I/O.
- Thời gian chờ đồng bộ hoặc tài nguyên nội bộ.
- Thời gian truyền dữ liệu và trao đổi với client.

Nếu hệ quản trị không cung cấp đầy đủ breakdown, có thể kết hợp wait events, thống kê câu lệnh, số liệu hệ điều hành và thời gian đo từ ứng dụng. Không nên suy ra CPU time chỉ từ thời gian đồng hồ của câu truy vấn.

## 3. Vì sao cần theo dõi giao dịch đang mở?

Một giao dịch mở lâu có thể ảnh hưởng đến hiệu năng và khả năng vận hành theo nhiều cách:

1. Giữ khóa lâu hơn cần thiết, khiến các phiên khác phải đợi.
2. Giữ snapshot hoặc phiên bản dữ liệu cũ, làm tăng công việc dọn dẹp phiên bản trong các hệ quản trị dùng MVCC.
3. Làm tăng nguy cơ deadlock khi giao dịch khác tiếp tục lấy khóa theo thứ tự khác nhau.
4. Chiếm connection pool ở ứng dụng và giảm số kết nối sẵn sàng phục vụ.
5. Làm khó xác định ranh giới của một thay đổi dữ liệu khi xảy ra lỗi hoặc rollback.
6. Làm chậm tác vụ bảo trì hoặc dọn dẹp tùy hệ quản trị và loại giao dịch.

### Giao dịch mở lâu không phải lúc nào cũng bất thường

Một giao dịch dài có thể là công việc báo cáo hoặc batch được thiết kế chạy lâu. Điều cần đánh giá là:

- Giao dịch có giữ khóa ảnh hưởng đến workload khác không?
- Nó có tạo snapshot lâu khiến vacuum hoặc cơ chế dọn dẹp bị trì hoãn không?
- Nó có đang chờ ứng dụng trong khi vẫn mở transaction không?
- Thời lượng hiện tại có vượt ngưỡng vận hành của nghiệp vụ không?
- Tần suất và mức độ ảnh hưởng có tăng bất thường không?

Đặc biệt chú ý trạng thái “idle in transaction” hoặc trạng thái tương đương. Phiên không chạy SQL nhưng transaction vẫn mở thường cho thấy ứng dụng đã hoàn thành một câu lệnh mà chưa commit/rollback. Nếu giao dịch đó giữ khóa hoặc snapshot, các tác động có thể kéo dài dù không có truy vấn đang hoạt động.

### Các nguyên nhân thường gặp

- Ứng dụng bắt đầu transaction quá sớm rồi mới thực hiện kiểm tra hoặc gọi dịch vụ ngoài.
- Một nhánh code thoát sớm mà không commit hoặc rollback.
- Xử lý từng bản ghi trong một transaction lớn.
- Người dùng mở màn hình chỉnh sửa nhưng transaction đã được mở từ trước và giữ xuyên suốt thao tác.
- Batch chạy lâu và cập nhật lượng dữ liệu lớn trong một transaction duy nhất.
- Lỗi kết nối hoặc timeout khiến trạng thái giao dịch không được xử lý như dự kiến.

Hướng cải thiện thường là thu hẹp phạm vi transaction, kết thúc giao dịch ngay sau phần đọc ghi cần thiết, chia batch thành lô có kích thước hợp lý và bảo đảm mọi nhánh xử lý đều kết thúc transaction.

## 4. Nhận diện phiên chặn và phiên bị chặn

Trong tranh chấp khóa, cần phân biệt:

- **Blocking session:** phiên đang giữ khóa hoặc tài nguyên khiến phiên khác không thể tiếp tục.
- **Blocked session:** phiên đang đợi tài nguyên do phiên khác giữ.
- **Wait chain:** chuỗi phụ thuộc khi một phiên bị chặn bởi phiên thứ hai, còn phiên thứ hai lại bị chặn bởi phiên thứ ba.

Một phiên có thể vừa là blocked session đối với giao dịch phía trước, vừa là blocking session đối với giao dịch phía sau. Vì vậy, chỉ xem một cặp phiên đôi khi chưa đủ; cần dựng chuỗi chặn nếu hệ quản trị hỗ trợ.

### Sơ đồ chuỗi chặn

~~~text
Phiên A
  |
  | giữ khóa trên bản ghi X
  v
Phiên B
  |
  | đang chờ khóa X, đồng thời giữ khóa Y
  v
Phiên C
  |
  | đang chờ khóa Y
  v
Hàng đợi các yêu cầu phía sau
~~~

Trong ví dụ này, phiên A là blocker gốc. Phiên B vừa là nạn nhân của A, vừa là blocker của C. Xử lý phiên C riêng lẻ thường không giải quyết được nguyên nhân của chuỗi.

### Các dấu hiệu cần ghi nhận

- PID hoặc connection ID của phiên chờ và phiên chặn.
- Người dùng, ứng dụng, máy chủ nguồn và database.
- Loại khóa, đối tượng, bảng, index hoặc dòng bị tranh chấp nếu hệ quản trị cung cấp.
- Thời điểm bắt đầu giao dịch và thời gian chờ.
- Câu SQL hiện tại hoặc câu SQL gần nhất của hai phiên.
- Số lượng phiên đang bị ảnh hưởng.
- Trạng thái và thời gian giữ khóa của blocker.
- Wait chain nếu có nhiều tầng chặn.

Đừng mặc định phiên có truy vấn dài nhất là blocker. Phiên chặn có thể đang ở trạng thái nhàn rỗi trong transaction và câu SQL hiển thị chỉ là câu lệnh gần nhất đã chạy. Cần đối chiếu transaction age, lock ownership và wait graph.

## 5. Quan sát phiên và giao dịch trong PostgreSQL

PostgreSQL cung cấp view pg_stat_activity để quan sát từng backend. Các trường thường hữu ích gồm:

- pid: mã tiến trình backend.
- usename: người dùng cơ sở dữ liệu.
- application_name: tên ứng dụng kết nối.
- client_addr: địa chỉ client.
- state: trạng thái phiên.
- state_change: thời điểm trạng thái thay đổi.
- query_start: thời điểm câu lệnh hiện tại bắt đầu nếu đang active; với trạng thái khác, có thể là thời điểm câu lệnh gần nhất bắt đầu.
- xact_start: thời điểm giao dịch hiện tại bắt đầu.
- wait_event_type và wait_event: loại chờ và sự kiện chờ.
- query: câu SQL hiện tại hoặc gần nhất, tùy trạng thái và quyền quan sát.

### Liệt kê phiên đang hoạt động và phiên idle in transaction

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    CASE
        WHEN state = 'active'
        THEN clock_timestamp() - query_start
    END AS active_query_age,
    clock_timestamp() - state_change AS state_age,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 300) AS query_text
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND (
      state = 'active'
      OR state = 'idle in transaction'
      OR state = 'idle in transaction (aborted)'
  )
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
~~~

Cách đọc kết quả:

- active cho biết backend đang thực thi câu lệnh.
- idle in transaction cho biết phiên đang chờ client nhưng transaction vẫn mở.
- idle in transaction (aborted) cho biết transaction đã gặp lỗi và đang ở trạng thái cần được xử lý kết thúc.
- active_query_age chỉ được tính khi state là active.
- state_age cho biết phiên đã ở trạng thái hiện tại bao lâu.
- transaction_age cho biết giao dịch đã mở bao lâu.

Dùng clock_timestamp() để đo thời gian thực tại lúc biểu thức được đánh giá. Trong PostgreSQL, now() trả về thời điểm bắt đầu transaction hiện tại của session gọi hàm; với một truy vấn giám sát chạy trong transaction dài, điều này có thể làm số tuổi thời gian không như mong đợi.

### Liệt kê các giao dịch đang mở lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    clock_timestamp() - state_change AS state_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS last_or_current_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Danh sách này có thể chứa giao dịch hợp lệ đang chạy lâu. Hãy so sánh với ngưỡng theo nghiệp vụ, trạng thái phiên, wait event và tác động lên phiên khác trước khi xem đó là bất thường.

### Tìm phiên đang chờ khóa và phiên chặn

PostgreSQL có hàm pg_blocking_pids(pid) để lấy PID của các phiên đang chặn một backend. Có thể dùng hàm này để nối phiên chờ với phiên chặn:

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.usename AS waiting_user,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    clock_timestamp() - waiting.query_start AS waiting_query_age,
    blocker.pid AS blocking_pid,
    blocker.usename AS blocking_user,
    blocker.application_name AS blocking_app,
    blocker.state AS blocking_state,
    clock_timestamp() - blocker.xact_start AS blocking_xact_age,
    left(waiting.query, 250) AS waiting_query,
    left(blocker.query, 250) AS blocking_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiting.pid)) AS blocked_by(pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocked_by.pid
WHERE waiting.wait_event_type = 'Lock'
ORDER BY waiting.query_start;
~~~

Kết quả giúp xác định phiên nào đang chờ và phiên nào đang chặn. Nếu blocker ở trạng thái idle in transaction, query của blocker có thể là câu lệnh cuối cùng đã chạy trước khi phiên chuyển sang nhàn rỗi. Cần xem transaction age và application logs để biết vì sao transaction chưa kết thúc.

### Xem thông tin khóa

View pg_locks chứa các khóa đang được giữ hoặc đang được yêu cầu. Có thể dùng nó để phân tích chi tiết hơn khi cần xác định loại đối tượng hoặc trạng thái khóa. Việc nối pg_locks với pg_stat_activity cần dựa trên PID và các trường nhận diện khóa phù hợp. Không nên tự kết luận rằng mọi dòng trong pg_locks đều là khóa gây chặn; nhiều loại khóa được giữ đồng thời là hoạt động bình thường.

Quyền xem query text và thông tin chi tiết của phiên khác có thể phụ thuộc vai trò. PostgreSQL có các vai trò giám sát như pg_read_all_stats; quyền superuser cũng có thể xem nhiều thông tin hơn. Trong môi trường production, nên cấp quyền giám sát tối thiểu cần thiết.

## 6. Quan sát phiên và giao dịch trong MySQL

MySQL cung cấp nhiều nguồn quan sát. Với InnoDB, có thể kết hợp processlist, information_schema.innodb_trx và Performance Schema để hiểu phiên, giao dịch và khóa.

### Liệt kê kết nối và câu lệnh đang xử lý

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    LEFT(INFO, 300) AS statement_text
FROM information_schema.PROCESSLIST
WHERE COMMAND <> 'Sleep'
ORDER BY TIME DESC;
~~~

Một số điểm cần lưu ý:

- COMMAND cho biết loại lệnh hoặc trạng thái kết nối.
- TIME thường biểu thị thời gian ở trạng thái hoặc câu lệnh hiện tại theo cách MySQL trình bày.
- STATE mô tả trạng thái xử lý chi tiết.
- INFO có thể là SQL hiện tại; khi kết nối ngủ, trường này có thể NULL.
- Kết nối Sleep không nhất thiết là lỗi vì connection pool thường giữ kết nối nhàn rỗi để tái sử dụng.

### Liệt kê giao dịch InnoDB đang mở

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_wait_started,
    trx_mysql_thread_id AS connection_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

View này giúp tìm transaction đang tồn tại và thời điểm bắt đầu. Một transaction có thể không có câu SQL hiện tại nếu kết nối đang nhàn rỗi nhưng vẫn giữ transaction. Hãy nối connection_id với processlist để xem ứng dụng và trạng thái kết nối.

### Tìm khóa đang chờ bằng Performance Schema

Trên các phiên bản MySQL hỗ trợ data_locks và data_lock_waits, có thể truy vấn quan hệ giữa khóa được yêu cầu và khóa đang chặn:

~~~sql
SELECT
    waiting_thread.PROCESSLIST_ID AS waiting_connection_id,
    waiting_lock.OBJECT_SCHEMA,
    waiting_lock.OBJECT_NAME,
    waiting_lock.INDEX_NAME,
    waiting_lock.LOCK_MODE AS waiting_lock_mode,
    blocking_thread.PROCESSLIST_ID AS blocking_connection_id,
    blocking_lock.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting_lock
    ON waiting_lock.ENGINE = waits.ENGINE
   AND waiting_lock.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking_lock
    ON blocking_lock.ENGINE = waits.ENGINE
   AND blocking_lock.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS waiting_thread
    ON waiting_thread.THREAD_ID = waits.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS blocking_thread
    ON blocking_thread.THREAD_ID = waits.BLOCKING_THREAD_ID;
~~~

Truy vấn này hiển thị connection ID của phiên yêu cầu khóa và phiên đang giữ khóa xung đột, cùng đối tượng và chế độ khóa. Tên cột, khả năng truy cập và nội dung Performance Schema phụ thuộc phiên bản MySQL và cấu hình instrumentation. Nếu view không có hoặc không có dữ liệu, cần kiểm tra phiên bản, quyền và các consumer/instrument đang được bật.

### Kết hợp giao dịch với kết nối

Có thể nối innodb_trx với processlist để thấy transaction age cùng ứng dụng và trạng thái kết nối:

~~~sql
SELECT
    trx.trx_id,
    trx.trx_state,
    trx.trx_started,
    TIMESTAMPDIFF(SECOND, trx.trx_started, NOW()) AS transaction_age_seconds,
    trx.trx_wait_started,
    process.ID AS connection_id,
    process.USER,
    process.HOST,
    process.DB,
    process.COMMAND,
    process.TIME AS command_age_seconds,
    process.STATE,
    LEFT(COALESCE(trx.trx_query, process.INFO), 300) AS statement_text
FROM information_schema.innodb_trx AS trx
LEFT JOIN information_schema.PROCESSLIST AS process
    ON process.ID = trx.trx_mysql_thread_id
ORDER BY trx.trx_started;
~~~

Đây là điểm bắt đầu để điều tra, không phải kết luận tự động. Nếu transaction đã mở lâu nhưng processlist cho thấy Sleep, ứng dụng có thể đã ngừng gửi câu lệnh mà chưa commit hoặc rollback.

## 7. Lấy mẫu theo thời gian thay vì chỉ chụp một thời điểm

Một truy vấn giám sát chỉ cho biết trạng thái tại thời điểm được lấy mẫu. Một phiên có thể chờ khóa trong vài mili giây rồi tiếp tục trước khi người vận hành kịp quan sát. Ngược lại, một truy vấn có thể xuất hiện ở nhiều mẫu liên tiếp, cho thấy thời gian chờ kéo dài.

### Xây dựng chuỗi quan sát

Nên thu thập các mẫu có timestamp và giữ những trường cần thiết để so sánh:

- Thời điểm lấy mẫu.
- Session ID hoặc PID.
- Trạng thái phiên.
- Query fingerprint hoặc mã truy vấn đã chuẩn hóa.
- Thời điểm bắt đầu truy vấn và transaction.
- Wait event và loại tài nguyên.
- Blocker PID hoặc connection ID.
- Ứng dụng, database và client.
- Số phiên đang active, idle in transaction và waiting.

Khoảng lấy mẫu phụ thuộc mục tiêu và overhead. Một chu kỳ quá dài có thể bỏ lỡ chờ ngắn; chu kỳ quá ngắn có thể tạo tải giám sát và lượng log lớn. Có thể dùng mức lấy mẫu bình thường để theo dõi xu hướng và tăng tần suất trong thời gian điều tra sự cố.

### So sánh các mẫu liên tiếp

Giả sử cùng một phiên xuất hiện trong ba mẫu:

| Thời điểm | Phiên | Trạng thái | Wait event | Blocker |
|---|---:|---|---|---:|
| 10:00:00 | 241 | active | Lock | 188 |
| 10:00:05 | 241 | active | Lock | 188 |
| 10:00:10 | 241 | active | Lock | 188 |

Việc lặp lại cùng blocker trong nhiều mẫu là dấu hiệu phiên chờ kéo dài. Nếu blocker 188 cũng giữ transaction lâu, cần điều tra giao dịch đó và các phiên khác trong wait chain.

Một mẫu duy nhất có thể phản ánh chờ ngắn. Nhiều mẫu liên tiếp cho thấy xu hướng, nhưng vẫn cần kiểm tra timestamp và sự thay đổi trạng thái để tránh hiểu sai khi PID được tái sử dụng sau khi một phiên kết thúc.

### Snapshot và dữ liệu tích lũy

Một số thống kê là bộ đếm tích lũy kể từ lần reset hoặc khởi động. Khi so sánh, hãy lấy hai snapshot và tính chênh lệch trong khoảng thời gian. Không so sánh trực tiếp các bộ đếm có thời gian tích lũy khác nhau.

Với trạng thái phiên, mỗi mẫu là một ảnh chụp tức thời. Với thống kê truy vấn, wait counters hoặc I/O counters, cần biết phạm vi tích lũy và quy tắc reset của hệ quản trị.

## 8. Kết hợp quan sát DB với metrics của ứng dụng

Cơ sở dữ liệu chỉ nhìn thấy các yêu cầu đã đến được nó. Một yêu cầu có thể chờ rất lâu ở tầng ứng dụng trước khi lấy được kết nối, hoặc sau khi database đã trả dữ liệu.

Để có bức tranh đầy đủ, nên đo ở cả hai phía:

| Tầng | Chỉ số nên quan sát | Điều có thể phát hiện |
|---|---|---|
| Ứng dụng | Thời gian chờ connection pool | Hết kết nối khả dụng hoặc pool quá nhỏ |
| Ứng dụng | Connection acquisition, usage và idle count | Kết nối bị giữ lâu hoặc pool cấu hình không phù hợp |
| Ứng dụng | Request latency, timeout, retry | Trải nghiệm người dùng và tác động của retry |
| Cơ sở dữ liệu | Active sessions và transaction age | Mức đồng thời và giao dịch mở lâu |
| Cơ sở dữ liệu | Wait events và blocking sessions | Khóa, I/O hoặc đồng bộ nội bộ |
| Cơ sở dữ liệu | Query duration, rows, buffers và plan | Chi phí của câu SQL và dữ liệu phải xử lý |
| Hệ điều hành | CPU, memory, disk latency và queue | Nút thắt hạ tầng bên dưới database |

Nếu pool wait cao nhưng database có ít phiên hoạt động, vấn đề có thể nằm ở connection bị giữ lâu trong ứng dụng, pool không cân đối giữa các instance hoặc một số luồng không trả kết nối. Nếu DB có nhiều active sessions và lock wait cao, cần điều tra concurrency và transaction.

Retry cũng có thể khuếch đại tải. Khi nhiều yêu cầu timeout cùng retry ngay lập tức, số truy vấn có thể tăng trong lúc hệ thống đang quá tải. Hãy xem tỷ lệ retry và timeout cùng với số phiên và throughput.

## 9. Quy trình điều tra khi có nhiều truy vấn chờ

Khi nhận cảnh báo về truy vấn chậm hoặc lock wait tăng, hãy thực hiện theo trình tự:

### Bước 1: Xác định phạm vi ảnh hưởng

Xác định một API hoặc một nhóm nghiệp vụ bị chậm, hay nhiều ứng dụng cùng bị ảnh hưởng. So sánh p50, p95, p99, throughput và tỷ lệ timeout.

### Bước 2: Chụp trạng thái phiên

Lấy danh sách phiên active, phiên có wait event, phiên idle in transaction và thời gian tồn tại của transaction. Ghi lại timestamp, ứng dụng và database.

### Bước 3: Tìm wait chain

Xác định phiên chờ, phiên chặn và chuỗi chặn. Với khóa, ghi nhận đối tượng, loại khóa, thời gian chờ và transaction age của blocker.

### Bước 4: Xác định câu SQL liên quan

Đọc câu SQL hiện tại hoặc gần nhất, query fingerprint, kế hoạch thực thi và thống kê. Nếu blocker đang idle trong transaction, dùng log ứng dụng để xác định câu lệnh trước đó và nhánh code chưa kết thúc transaction.

### Bước 5: Tìm nguyên nhân gốc

Một giao dịch giữ khóa lâu có thể do truy vấn bên trong transaction chậm, xử lý ứng dụng kéo dài, batch quá lớn hoặc điểm nóng ghi. Một phiên chờ I/O có thể do truy vấn đọc quá nhiều dữ liệu hoặc thiết bị lưu trữ đang bận. Cần kiểm tra dữ liệu hỗ trợ giả thuyết.

### Bước 6: Chọn biện pháp xử lý

Các biện pháp có thể gồm rút ngắn transaction, sửa SQL, thêm hoặc điều chỉnh chỉ mục, chia batch, điều tiết concurrency, thay đổi thứ tự truy cập tài nguyên hoặc xử lý hàng đợi ở tầng ứng dụng.

### Bước 7: Đo lại và xác nhận

Theo dõi số phiên chờ, transaction age, lock wait duration, p95/p99, throughput, timeout và tài nguyên. So sánh trước/sau trong điều kiện tải tương đương.

## 10. Ví dụ tình huống vận hành

### Tình huống A: Nhiều yêu cầu cập nhật đơn hàng cùng chờ khóa

Một đợt nhập dữ liệu làm nhiều worker cập nhật trạng thái đơn hàng. API bắt đầu timeout, CPU cơ sở dữ liệu không quá cao nhưng số phiên chờ khóa tăng.

Quan sát wait graph cho thấy nhiều phiên chờ một blocker. Blocker đã mở transaction từ lâu và đang idle in transaction. Query text hiển thị câu UPDATE cuối cùng nhưng không có SQL đang chạy.

Cách điều tra:

1. Ghi lại PID, application_name và transaction age của blocker.
2. Đối chiếu log ứng dụng để tìm request hoặc worker sở hữu connection.
3. Kiểm tra nhánh xử lý có gọi dịch vụ ngoài hoặc chờ retry trong transaction không.
4. Rút ngắn phạm vi transaction và bảo đảm mọi nhánh đều commit/rollback.
5. Chạy lại với số worker và dữ liệu tương đương, đo lock wait và p99.

### Tình huống B: Phiên active lâu do truy vấn đọc nhiều dữ liệu

Một báo cáo chạy lâu và xuất hiện active trong nhiều mẫu. Không có blocker; wait event thường xuyên liên quan đến I/O. Kế hoạch cho thấy truy vấn quét lượng dữ liệu lớn, trả về ít dòng.

Đây có thể là vấn đề truy cập dữ liệu hoặc nút thắt I/O chứ không phải giao dịch bị khóa. Cần xem điều kiện lọc, chỉ mục, thống kê và buffers. Sau điều chỉnh, so sánh lượng block đọc, thời gian thực thi và độ trễ của các truy vấn khác cùng sử dụng bảng.

### Tình huống C: Connection pool cạn nhưng database ít truy vấn

Ứng dụng báo chờ lấy kết nối và request latency tăng. Trong database, phần lớn session ở trạng thái idle, số active session thấp.

Điều này gợi ý kết nối đang được giữ lâu ở tầng ứng dụng hoặc pool được cấu hình không hợp lý. Cần đo thời gian acquisition, thời gian giữ connection, số connection đang dùng theo instance và các đoạn code giữ connection qua xử lý ngoài database. Chỉ tăng pool có thể làm tổng số phiên tăng mà không sửa được việc kết nối không được trả về đúng lúc.

## 11. Những lỗi thường gặp khi quan sát

- **Coi mọi session idle là lỗi:** connection pool thường giữ kết nối nhàn rỗi để tái sử dụng.
- **Bỏ qua idle in transaction:** phiên không chạy SQL vẫn có thể giữ transaction, snapshot hoặc khóa.
- **Chỉ nhìn câu SQL dài nhất:** blocker có thể không chạy SQL tại thời điểm quan sát.
- **Chỉ lấy một snapshot:** có thể bỏ lỡ chờ ngắn hoặc hiểu nhầm trạng thái nhất thời.
- **Nhầm thời gian truy vấn với CPU time:** thời gian thực thi có thể bao gồm phần lớn thời gian chờ.
- **Hủy blocker ngay lập tức:** có thể gây rollback lớn, làm mất công việc hoặc tạo thêm tải phục hồi.
- **Chỉ theo dõi DB:** không phát hiện được thời gian chờ connection pool, mạng hoặc xử lý sau truy vấn.
- **Không lưu timestamp và định danh phiên:** khó nối các mẫu theo thời gian; cần lưu ý PID có thể được tái sử dụng.
- **Ghi log toàn bộ câu SQL và tham số:** có thể làm lộ dữ liệu nhạy cảm, đồng thời tăng chi phí lưu trữ và xử lý.
- **Chạy truy vấn giám sát quá dày:** chính hoạt động quan sát có thể tạo tải, đặc biệt khi truy vấn catalog hoặc lock metadata phức tạp.

## 12. Quy tắc vận hành và an toàn khi xử lý phiên

Trước khi kết thúc hoặc hủy một phiên, cần xác định rõ:

- Phiên thuộc ứng dụng, người dùng hoặc nghiệp vụ nào.
- Phiên có phải blocker gốc hay chỉ là một mắt xích trong wait chain.
- Transaction đã thực hiện những thay đổi gì và rollback có thể tốn bao lâu.
- Có thể xử lý ở tầng ứng dụng hoặc chờ transaction hoàn tất an toàn không.
- Ai có quyền phê duyệt hành động tác động đến phiên production.

Trong quá trình điều tra, ưu tiên truy vấn giám sát chỉ đọc và lưu lại bằng chứng trước khi thay đổi trạng thái phiên. Lệnh terminate hoặc kill có thể gây rollback, làm tăng I/O và ảnh hưởng nghiệp vụ. Chỉ sử dụng theo quy trình vận hành đã được phê duyệt.

Cần quản lý quyền truy cập vào dữ liệu giám sát. Query text, tên người dùng, địa chỉ client và tham số truy vấn có thể chứa thông tin nhạy cảm. Nên chuẩn hóa câu SQL, ẩn giá trị tham số, giới hạn thời gian lưu log và cấp quyền xem theo vai trò.

## 13. Checklist theo dõi phiên, giao dịch và truy vấn chờ

Khi điều tra sự cố, hãy tự kiểm tra:

1. Đã xác định đúng ứng dụng, nghiệp vụ, database và khoảng thời gian bị ảnh hưởng chưa?
2. Có bao nhiêu phiên active, idle, idle in transaction và waiting?
3. Truy vấn nào đang chạy lâu và thời gian đó gồm CPU hay wait?
4. Có transaction mở lâu hoặc idle in transaction không?
5. Có phiên chờ khóa; blocker gốc là phiên nào?
6. Có wait chain nhiều tầng hoặc nhiều phiên cùng chờ một tài nguyên không?
7. Query text có phải câu đang chạy hay chỉ là câu gần nhất của phiên?
8. Connection pool có đang cạn hoặc giữ kết nối lâu ở tầng ứng dụng không?
9. Các mẫu quan sát có cùng timestamp và có đủ nhiều mẫu để xác nhận xu hướng không?
10. Sau điều chỉnh, lock wait, transaction age, p95/p99, throughput và timeout có cải thiện không?

## Kết luận

Theo dõi phiên đang chạy giúp xác định ai đang sử dụng cơ sở dữ liệu; theo dõi giao dịch đang mở cho biết công việc nào chưa kết thúc và có thể tiếp tục giữ tài nguyên; theo dõi truy vấn chờ giúp tìm loại tài nguyên đang làm tiến trình bị giữ lại. Khi kết nối các dữ liệu này thành wait chain theo thời gian, người vận hành có thể xác định blocker gốc và hiểu phạm vi ảnh hưởng.

Một quy trình quan sát hiệu quả cần kết hợp trạng thái phiên, tuổi giao dịch, wait events, query text, thống kê truy vấn, metrics của ứng dụng và dữ liệu hệ điều hành. Mọi biện pháp xử lý cần được xác minh bằng số liệu trước và sau trong điều kiện tải có thể so sánh. Nhờ vậy, nhóm vận hành có thể tìm đúng nguyên nhân, giảm thời gian chờ và duy trì hiệu năng cơ sở dữ liệu ổn định.

