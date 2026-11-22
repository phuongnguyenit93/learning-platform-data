# SHOW PROCESSLIST và phân biệt kết nối chờ với truy vấn đang chạy

Khi MySQL chậm hoặc hết khả năng nhận kết nối, bước quan sát thường bắt đầu bằng danh sách process. SHOW PROCESSLIST cho biết các thread client đang kết nối, lệnh hiện tại, trạng thái và thời gian ở trạng thái đó. Tuy nhiên, một kết nối Sleep không đồng nghĩa với một transaction đã kết thúc; ngược lại, một dòng Query cũng không chứng minh server đang dùng CPU để thực thi vì truy vấn có thể đang chờ khóa, I/O hoặc metadata lock.

Trong module DATABASE_MYSQL, bài học này hướng dẫn đọc đúng các cột của process list, phân biệt kết nối nhàn rỗi với câu lệnh đang chạy hoặc đang chờ, sử dụng SHOW FULL PROCESSLIST, truy vấn Performance Schema và đối chiếu transaction InnoDB để tìm kết nối ngủ nhưng còn giữ transaction mở.

## 1. Process list cho biết điều gì?

Process list là ảnh chụp trạng thái các thread client tại thời điểm truy vấn. Mỗi dòng thường tương ứng với một kết nối client và cho biết:

- Ai đang kết nối và kết nối đến từ host nào.
- Kết nối đang ở trạng thái chờ lệnh mới hay đang xử lý một command.
- Câu SQL hiện tại, nếu có.
- Thread đã ở trạng thái hiện tại bao lâu.

Process list không phải lịch sử truy vấn và không phải biểu đồ CPU. Một câu lệnh chạy rất ngắn có thể kết thúc trước khi bạn kịp chụp process list. Một câu lệnh xuất hiện lâu trong danh sách có thể đang chờ tài nguyên chứ không tiêu thụ CPU liên tục.

Để chẩn đoán, cần kết hợp process list với Performance Schema, transaction metadata, lock information và metrics của máy chủ.

## 2. Xem danh sách bằng SHOW PROCESSLIST

Câu lệnh cơ bản:

~~~sql
SHOW PROCESSLIST;
~~~

Để xem đầy đủ nội dung cột Info:

~~~sql
SHOW FULL PROCESSLIST;
~~~

SHOW PROCESSLIST thông thường rút gọn nội dung SQL trong cột Info (thường giới hạn 100 ký tự). SHOW FULL PROCESSLIST hiển thị nội dung đầy đủ hơn, trong giới hạn metadata SQL của server.

Kết quả là một snapshot tại thời điểm câu lệnh chạy. Nếu một truy vấn chỉ tồn tại vài mili giây, snapshot có thể không bắt gặp nó. Với truy vấn ngắn hoặc cần xem lịch sử gần đây, hãy dùng statement instrumentation trong Performance Schema thay vì chỉ lặp lại SHOW PROCESSLIST.

## 3. Quyền PROCESS và phạm vi nhìn thấy

Tài khoản có quyền PROCESS có thể xem các thread của mọi user. Nếu không có quyền này, tài khoản thông thường chỉ thấy các thread thuộc chính mình.

Điều này có nghĩa:

- DBA có PROCESS có thể quan sát toàn bộ kết nối client.
- Tài khoản ứng dụng không có PROCESS thường chỉ nhìn thấy kết nối của chính nó.
- Một danh sách trống hoặc thiếu kết nối không nhất thiết chứng minh server không có workload; hãy kiểm tra quyền và phạm vi quan sát.

PROCESS là quyền rộng vì thông tin process list có thể tiết lộ user, host, tên database và nội dung SQL của kết nối khác. Chỉ cấp quyền cho nhóm vận hành cần quan sát toàn server; tránh cấp quyền này cho tài khoản ứng dụng thông thường.

Kiểm tra quyền hiện tại:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

## 4. Ý nghĩa các cột trong process list

| Cột | Ý nghĩa | Cách đọc khi điều tra |
|---|---|---|
| Id | Connection ID của client | Dùng để đối chiếu với PROCESSLIST_ID và lệnh KILL |
| User | Tài khoản MySQL của kết nối | Xác định ứng dụng hoặc nhóm người dùng |
| Host | Host client, thường kèm port | Tìm node ứng dụng hoặc nguồn kết nối |
| db | Database mặc định của session | Có thể NULL nếu session chưa chọn database |
| Command | Loại command thread đang xử lý | Sleep thường là chờ client gửi lệnh tiếp |
| Time | Số giây thread ở trạng thái hiện tại | Là thời gian ở state hiện tại, không phải tổng tuổi connection |
| State | Mô tả trạng thái xử lý hiện tại | Có thể cho biết thread đang chờ khóa, sort, gửi dữ liệu hoặc làm việc khác |
| Info | Câu lệnh hiện tại nếu có | Thường NULL khi Sleep; có thể bị cắt nếu không dùng FULL |

Time cần được diễn giải cùng Command và State. Với Sleep, nó thường thể hiện thời gian kết nối ở trạng thái chờ. Với một câu query đang chạy, nó cho biết thread đã ở state hiện tại bao lâu; state có thể thay đổi trong suốt vòng đời câu lệnh.

## 5. Phân biệt Sleep và Query

Hai trường hợp phổ biến:

| Dấu hiệu | Kết nối Sleep | Kết nối đang xử lý Query |
|---|---|---|
| Command | Sleep | Thường là Query |
| Info | Thường NULL | Có SQL hiện tại |
| Ý nghĩa | Server đang chờ client gửi command mới | Thread đang xử lý command SQL |
| Có thể giữ transaction mở? | Có | Có |
| Có nhất thiết dùng CPU? | Không đáng kể khi thực sự idle | Không; có thể đang chờ tài nguyên |

Sleep có nghĩa là server chưa nhận command mới từ client trên connection đó. Nó không nói rằng connection không giữ transaction, không giữ session state hoặc không chiếm tài nguyên kết nối.

Một connection trong pool có thể Sleep bình thường để tái sử dụng. Một connection Sleep lâu nhưng còn transaction mở có thể giữ snapshot, khóa hoặc làm tăng undo history. Cần kiểm tra transaction metadata trước khi kết luận kết nối đó an toàn.

## 6. Ví dụ đọc process list

Chạy:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Giả sử có các dòng minh họa:

| Id | User | Command | Time | State | Info |
|---:|---|---|---:|---|---|
| 101 | app_user | Sleep | 12 | NULL | NULL |
| 102 | app_user | Query | 3 | Sending data | SELECT ... |
| 103 | report_user | Query | 48 | Waiting for table metadata lock | ALTER/SELECT ... |
| 104 | app_user | Sleep | 420 | NULL | NULL |

Có thể diễn giải sơ bộ:

- ID 101 là kết nối đang chờ client gửi lệnh mới; 12 giây Sleep tự nó chưa phải sự cố.
- ID 102 đang thực hiện một truy vấn; Sending data có thể bao gồm đọc và xử lý hàng, không chỉ truyền bytes qua mạng.
- ID 103 đang bị chặn bởi metadata lock; thời gian dài không có nghĩa câu lệnh đang chạy CPU liên tục.
- ID 104 đã Sleep lâu; cần kiểm tra xem có transaction InnoDB mở hay không trước khi đóng kết nối.

Bảng trên chỉ là dữ liệu minh họa. State cụ thể thay đổi theo câu lệnh, engine và phiên bản MySQL.

## 7. SHOW FULL PROCESSLIST không phải bộ đo thời gian truy vấn

Không diễn giải Time như thời lượng tổng chính xác của câu SQL trong mọi tình huống:

- Thread có thể chuyển qua nhiều state trong một câu lệnh.
- Một câu lệnh có thể chờ lock lâu rồi mới thực hiện phần xử lý.
- Time phản ánh thời gian ở state hiện tại theo process list.
- Một truy vấn kết thúc trước lúc chụp snapshot sẽ không còn xuất hiện.
- Một connection Sleep lâu có thể không có câu SQL đang chạy.

Để đo thời lượng statement và số hàng đã đọc, hãy xem events_statements_current hoặc history trong Performance Schema nếu instrumentation và consumer tương ứng được bật.

## 8. Các state thường gặp

| State | Cách hiểu thực tế |
|---|---|
| Sending data | Thread đang đọc, xử lý hoặc gửi kết quả; không chỉ là truyền dữ liệu mạng |
| Creating sort index | Đang tạo cấu trúc phục vụ sort hoặc xử lý thứ tự |
| Sorting result | Đang sắp xếp kết quả |
| statistics | Đang thu thập/thẩm định thông tin để chọn kế hoạch |
| Waiting for table metadata lock | Đang chờ metadata lock trên object |
| Waiting for ... lock | Đang chờ loại khóa hoặc tài nguyên được nêu trong state |
| Creating tmp table | Đang tạo temporary table cho xử lý truy vấn |
| Copying to tmp table | Đang đưa dữ liệu vào temporary table |
| Sleep | Connection chờ command mới từ client |

Danh sách state không cố định và có thể thay đổi theo phiên bản MySQL. Đừng chẩn đoán chỉ từ tên state; hãy xem SQL, transaction, lock metadata và lịch sử statement đi kèm.

### Sending data không đồng nghĩa chỉ gửi kết quả

Tên state dễ gây hiểu nhầm. Trong quá trình này MySQL có thể đọc hàng từ storage engine, kiểm tra điều kiện, join, xử lý biểu thức và tạo kết quả. Một truy vấn ở Sending data lâu có thể do quét nhiều hàng hoặc join tốn kém, không nhất thiết do mạng chậm.

### Waiting for table metadata lock

State này thường xuất hiện khi câu lệnh cần metadata lock nhưng một transaction hoặc statement khác đang giữ lock xung đột. Ví dụ DDL như ALTER TABLE có thể chờ transaction đang sử dụng bảng kết thúc. Kiểm tra metadata lock đang chờ và holder trước khi quyết định xử lý.

## 9. Lọc process list bằng Performance Schema

Từ MySQL 8.0.22, Performance Schema có bảng performance_schema.processlist như một giao diện process list. Bảng này là lựa chọn phù hợp để lọc, sắp xếp và join với metadata khác bằng SQL.

INFORMATION_SCHEMA.PROCESSLIST bị đánh dấu deprecated từ MySQL 8.0.22. Với truy vấn có cấu trúc, ưu tiên performance_schema.processlist hoặc performance_schema.threads thay vì xây công cụ mới dựa trên bảng INFORMATION_SCHEMA cũ.

Ví dụ chỉ xem connection không ở trạng thái Sleep:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM performance_schema.processlist
WHERE COMMAND <> 'Sleep'
ORDER BY TIME DESC;
~~~

Xem các kết nối Sleep lâu:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    TIME AS sleep_seconds
FROM performance_schema.processlist
WHERE COMMAND = 'Sleep'
ORDER BY TIME DESC;
~~~

Các truy vấn trên chỉ lọc snapshot hiện tại. Ngưỡng Sleep lâu cần được xác định theo connection pool, timeout và đặc tính ứng dụng; không có một ngưỡng chung phù hợp mọi hệ thống.

## 10. Dùng performance_schema.threads

performance_schema.threads chứa metadata thread của MySQL. Với thread client, các cột PROCESSLIST_* cung cấp thông tin tương tự process list:

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
ORDER BY PROCESSLIST_TIME DESC;
~~~

Phân biệt:

- THREAD_ID là định danh nội bộ của Performance Schema.
- PROCESSLIST_ID là connection ID mà client nhìn thấy và dùng trong process list.

Khi join statement events, dùng THREAD_ID. Khi đối chiếu SHOW PROCESSLIST hoặc transaction metadata, thường dùng PROCESSLIST_ID.

Không nhầm background thread nội bộ của InnoDB với kết nối client. Lọc TYPE = 'FOREGROUND' và PROCESSLIST_ID IS NOT NULL để tập trung vào connection.

## 11. Lấy statement hiện tại và số liệu thực thi

performance_schema.events_statements_current ghi nhận statement event hiện tại của thread nếu instrumentation/consumer liên quan được bật:

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_COMMAND AS command_name,
    t.PROCESSLIST_TIME AS processlist_seconds,
    t.PROCESSLIST_STATE AS processlist_state,
    esc.SQL_TEXT,
    esc.ROWS_EXAMINED,
    esc.ROWS_SENT,
    esc.ROWS_AFFECTED,
    esc.LOCK_TIME
FROM performance_schema.threads AS t
LEFT JOIN performance_schema.events_statements_current AS esc
    ON esc.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'FOREGROUND'
  AND t.PROCESSLIST_ID IS NOT NULL
  AND t.PROCESSLIST_COMMAND <> 'Sleep'
ORDER BY t.PROCESSLIST_TIME DESC;
~~~

Với event đang chạy, TIMER_END và TIMER_WAIT có thể chưa có giá trị cuối cùng; vì vậy truy vấn hiện tại tập trung vào SQL và bộ đếm hàng, không dùng TIMER_WAIT để khẳng định thời lượng hoàn tất. Trong history của statement đã kết thúc, TIMER_WAIT được biểu diễn theo picosecond; chia cho 10^12 để quy đổi sang giây. PROCESSLIST_TIME và TIMER_WAIT là hai loại thời gian với ngữ nghĩa khác nhau, không thay thế cho nhau.

Một số cột có thể NULL nếu statement event chưa được ghi nhận hoặc instrumentation chưa bật. SQL_TEXT cũng có thể bị giới hạn bởi cấu hình độ dài SQL text. Cần kiểm tra consumer và instrument trước khi kết luận không có statement.

## 12. Xem lịch sử statement gần đây

events_statements_current chỉ phản ánh event hiện tại. Để xem statement đã kết thúc gần đây, có thể truy vấn events_statements_history hoặc events_statements_history_long nếu các consumer tương ứng được bật:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 3) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    ROWS_AFFECTED
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
  AND TIMER_WAIT IS NOT NULL
ORDER BY TIMER_END DESC
LIMIT 50;
~~~

History là bộ đệm có giới hạn, không phải kho lưu trữ lâu dài. Dữ liệu cũ có thể bị ghi đè khi workload tiếp tục. Nếu cần lịch sử phục vụ audit hoặc phân tích dài hạn, hãy thiết kế hệ thống thu thập riêng và kiểm soát dữ liệu nhạy cảm trong SQL text.

## 13. Kết nối Sleep nhưng còn transaction mở

Đây là trường hợp cần chú ý. Ứng dụng có thể:

1. Mở transaction bằng START TRANSACTION.
2. Đọc hoặc cập nhật một số hàng.
3. Trả connection về pool mà quên COMMIT/ROLLBACK.
4. Connection chuyển sang Sleep vì client chưa gửi câu lệnh mới.

Transaction InnoDB vẫn có thể tồn tại dù process list hiển thị Command = Sleep. Transaction mở lâu có thể giữ row lock, giữ read view, làm chậm purge và tăng lượng undo cần duy trì.

Đối chiếu process list với information_schema.innodb_trx:

~~~sql
SELECT
    p.ID AS connection_id,
    p.USER,
    p.HOST,
    p.COMMAND,
    p.TIME AS processlist_seconds,
    p.STATE,
    trx.trx_id,
    trx.trx_state,
    trx.trx_started,
    TIMESTAMPDIFF(SECOND, trx.trx_started, NOW()) AS transaction_age_seconds,
    trx.trx_rows_locked,
    trx.trx_rows_modified,
    trx.trx_query
FROM performance_schema.processlist AS p
JOIN information_schema.innodb_trx AS trx
    ON trx.trx_mysql_thread_id = p.ID
ORDER BY trx.trx_started;
~~~

Nếu COMMAND là Sleep nhưng join vẫn trả về transaction, connection đang idle ở process list nhưng transaction chưa kết thúc. Kiểm tra owner, tuổi transaction và tác động khóa trước khi xử lý.

## 14. Phân biệt query đang chạy với query đang chờ lock

Một thread có Command = Query nghĩa là connection đang xử lý một command SQL. Nó có thể:

- Đang đọc và xử lý hàng.
- Đang sort hoặc tạo temporary table.
- Đang chờ row lock của InnoDB.
- Đang chờ metadata lock.
- Đang chờ I/O hoặc tài nguyên khác.

Vì vậy, Query không đồng nghĩa CPU đang chạy. Hãy xem State, statement event và lock metadata.

### Kiểm tra metadata lock đang chờ

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_STATE AS processlist_state,
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS
FROM performance_schema.metadata_locks AS ml
JOIN performance_schema.threads AS t
    ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
ORDER BY t.PROCESSLIST_ID;
~~~

PENDING là lock request chưa được cấp. Để xác định blocker, đối chiếu các lock GRANTED trên cùng object và transaction/statement đang giữ chúng. Không kết luận chỉ từ một dòng PENDING rằng thread đang bị row lock InnoDB; metadata lock là một loại khóa khác.

### Kiểm tra InnoDB lock wait

MySQL 8.0 cung cấp performance_schema.data_lock_waits và performance_schema.data_locks để quan sát các lock wait của InnoDB. Bảng data_lock_waits liên kết lock đang chờ với lock đang chặn:

~~~sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx_id,
    req.THREAD_ID AS waiting_thread_id,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx_id,
    blk.THREAD_ID AS blocking_thread_id,
    blk.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Sau đó join THREAD_ID với performance_schema.threads để lấy connection ID và user. Đây là thông tin về InnoDB data lock; metadata lock được xem qua performance_schema.metadata_locks.

## 15. Vì sao process list có thể không đủ?

Process list có một số giới hạn:

- Chỉ là snapshot tại thời điểm đọc.
- Không lưu toàn bộ lịch sử statement.
- TIME không phải CPU time.
- INFO có thể NULL hoặc bị giới hạn độ dài.
- Một câu Query có thể đang chờ lock hoặc I/O.
- Một connection Sleep có thể còn transaction mở.
- Không cho biết đầy đủ rows examined, wait events hay execution stages.

Để phân tích sâu hơn, kết hợp:

| Nguồn | Câu hỏi trả lời |
|---|---|
| SHOW FULL PROCESSLIST | Connection nào đang ở trạng thái gì ngay lúc này? |
| performance_schema.processlist | Có thể lọc/sắp xếp process list như thế nào? |
| performance_schema.threads | Thread nội bộ và connection ID liên hệ ra sao? |
| events_statements_current | Statement hiện tại đọc bao nhiêu hàng, kéo dài bao lâu? |
| events_statements_history_long | Statement nào vừa chạy gần đây? |
| information_schema.innodb_trx | Transaction nào đang mở, bắt đầu khi nào? |
| metadata_locks | Thread nào đang chờ metadata lock? |
| data_lock_waits | Transaction nào đang chờ và transaction nào đang chặn? |
| SHOW ENGINE INNODB STATUS | InnoDB đang có lock wait/deadlock và trạng thái nội bộ nào? |

## 16. SHOW ENGINE INNODB STATUS khi cần ngữ cảnh InnoDB

Khi nghi ngờ lock wait hoặc deadlock, lệnh sau cung cấp snapshot trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Trong client hỗ trợ output dọc, có thể dùng:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Tập trung vào các phần TRANSACTIONS, LATEST DETECTED DEADLOCK và thông tin lock wait. Đây là báo cáo tổng hợp, không thay thế truy vấn có cấu trúc vào Performance Schema. Deadlock report thường chỉ giữ thông tin deadlock gần nhất được ghi nhận.

## 17. KILL QUERY và KILL CONNECTION

Sau khi xác định đúng thread và tác động, MySQL cung cấp hai thao tác khác nhau:

~~~sql
KILL QUERY 12345;
KILL CONNECTION 12345;
~~~

- KILL QUERY dừng statement hiện tại của connection nhưng giữ connection tồn tại.
- KILL CONNECTION kết thúc connection; transaction chưa commit có thể phải rollback.

Không KILL chỉ vì một dòng có Time lớn. Trước tiên xác định user, host, SQL, transaction age, lock đang giữ và ứng dụng sở hữu connection. Rollback một transaction lớn có thể mất thời gian và tạo thêm I/O.

Đặc biệt với connection Sleep đang giữ transaction, KILL QUERY thường không giải quyết vấn đề vì không có statement đang chạy. Nếu đã quyết định chấm dứt connection, cần hiểu rollback và tác động đến ứng dụng.

## 18. Quy trình điều tra một truy vấn chậm

1. Chụp SHOW FULL PROCESSLIST để ghi nhận connection ID, user, host, command, time, state và SQL.
2. Xác định thread là Sleep hay đang xử lý command.
3. Nếu là Query, đọc State để phân biệt xử lý dữ liệu với chờ lock/tài nguyên.
4. Truy vấn performance_schema.processlist và threads để lọc các thread liên quan.
5. Đọc events_statements_current để xem SQL text, rows examined, rows sent và thời gian statement nếu có.
6. Kiểm tra innodb_trx để phát hiện transaction mở lâu, kể cả trên connection Sleep.
7. Nếu có lock wait, kiểm tra metadata_locks hoặc data_lock_waits theo đúng loại lock.
8. Nếu cần, đọc SHOW ENGINE INNODB STATUS để lấy ngữ cảnh InnoDB.
9. Xác định blocker và ứng dụng sở hữu connection trước khi can thiệp.
10. Ghi lại kết quả trước/sau khi xử lý và kiểm tra workload có phục hồi không.

## 19. Lỗi diễn giải thường gặp

| Nhận định sai | Vì sao sai | Cách kiểm tra đúng |
|---|---|---|
| Sleep lâu luôn là kết nối rò rỉ | Connection pool có thể giữ kết nối nhàn rỗi có chủ đích | Kiểm tra pool, timeout và transaction mở |
| Sleep nghĩa là transaction đã đóng | Session có thể idle trong khi transaction còn mở | Join innodb_trx |
| Query nghĩa là CPU đang chạy | Thread có thể đang chờ lock hoặc I/O | Đọc State và Performance Schema waits |
| Sending data chỉ là gửi qua mạng | State có thể gồm đọc và xử lý hàng | Xem rows examined, plan và stage |
| Time là tổng thời gian câu SQL | Time là thời gian ở state hiện tại | Đối chiếu statement timer/history |
| Không thấy SQL nghĩa là không có workload | Snapshot có thể bỏ lỡ query ngắn hoặc Info bị NULL/cắt | Dùng statement history và instrumentation |
| KILL QUERY luôn giải phóng transaction | Statement dừng nhưng connection/transaction có thể còn | Kiểm tra transaction sau KILL |
| Một process list là đủ để tìm blocker | Process list không mô tả đầy đủ quan hệ lock | Dùng metadata_locks/data_lock_waits |

## 20. Bảo mật và chi phí quan sát

Process list và statement history có thể chứa literal, email, số tài khoản hoặc thông tin nhạy cảm được nhúng trong SQL. Vì vậy:

- Hạn chế quyền PROCESS.
- Hạn chế quyền đọc Performance Schema theo nguyên tắc tối thiểu.
- Không xuất SQL text ra log hoặc dashboard công khai nếu chưa che dữ liệu nhạy cảm.
- Giới hạn tần suất polling; truy vấn process list liên tục với tần suất quá cao có thể tạo thêm tải.
- Ưu tiên truy vấn có điều kiện và lấy đúng cột cần thiết thay vì quét/hiển thị toàn bộ metadata.
- Bảo vệ dashboard và log observability như dữ liệu vận hành nhạy cảm.

Quan sát phải đủ chi tiết để chẩn đoán nhưng không làm lộ nội dung truy vấn hoặc thông tin kết nối cho người không có trách nhiệm.

## 21. Bài tập thực hành

1. Chạy SHOW PROCESSLIST và SHOW FULL PROCESSLIST; so sánh độ dài cột Info.
2. Xác định các dòng Sleep và Query; giải thích ý nghĩa Command, Time, State và Info.
3. Mở hai session; để một session Sleep và quan sát process list từ session còn lại.
4. Trong môi trường test, mở transaction InnoDB rồi để connection idle; xác nhận process list hiển thị Sleep nhưng innodb_trx vẫn có transaction.
5. Truy vấn performance_schema.processlist để lọc các kết nối không Sleep và sắp xếp theo TIME.
6. Join performance_schema.threads với events_statements_current để lấy SQL_TEXT, ROWS_EXAMINED và ROWS_SENT.
7. Tạo một truy vấn chờ metadata lock trong môi trường thử nghiệm; xác nhận state và metadata_locks có request PENDING.
8. Quan sát một InnoDB lock wait và đối chiếu data_lock_waits với process list.
9. So sánh KILL QUERY và KILL CONNECTION trên connection test; quan sát transaction rollback.
10. Viết runbook điều tra truy vấn lâu với các bước snapshot, statement metrics, transaction, lock và xác nhận phục hồi.

Bạn hoàn thành bài khi đọc được process list, phân biệt kết nối Sleep với statement đang chạy, nhận ra statement có thể đang chờ thay vì dùng CPU, và phát hiện được transaction mở lâu trên connection nhàn rỗi. Process list là điểm bắt đầu của quan sát; kết luận đáng tin cậy cần đối chiếu statement, transaction và lock metadata.
