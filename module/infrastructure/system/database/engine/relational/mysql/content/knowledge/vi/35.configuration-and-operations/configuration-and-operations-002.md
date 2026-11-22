# Biến GLOBAL, SESSION, read-only và biến có thể thay đổi động

MySQL dùng system variable để điều khiển hành vi của server và từng kết nối. Một biến có thể có phạm vi GLOBAL, SESSION hoặc cả hai; một số biến chỉ đọc được ở runtime, trong khi các biến khác có thể thay đổi động mà không cần khởi động lại server. Hiểu đúng phạm vi và khả năng thay đổi giúp quản trị viên cấu hình an toàn, tránh tác động ngoài ý muốn đến kết nối đang chạy và biết khi nào cần lưu cấu hình qua lần restart.

Trong module DATABASE_MYSQL, bài học này tập trung vào cách đọc giá trị biến, phân biệt GLOBAL với SESSION, thay đổi biến bằng SET, nhận diện biến động và biến chỉ cấu hình lúc khởi động, sử dụng SET PERSIST/SET PERSIST_ONLY, kiểm tra nguồn giá trị và quản lý quyền thay đổi cấu hình.

## 1. System variable là gì?

System variable là tham số cấu hình do MySQL cung cấp để điều khiển hoạt động của server hoặc session. Ví dụ:

- max_connections giới hạn số kết nối đồng thời mà server chấp nhận.
- sql_mode xác định một số quy tắc xử lý SQL và dữ liệu.
- time_zone điều khiển múi giờ dùng trong session.
- sort_buffer_size ảnh hưởng bộ nhớ sort của session.
- read_only và super_read_only điều khiển chế độ hạn chế ghi dữ liệu.

Giá trị biến có thể đến từ mặc định được biên dịch, file cấu hình, tham số dòng lệnh, file cấu hình persisted hoặc lệnh SET trong runtime. Khi điều tra một giá trị bất ngờ, cần kiểm tra cả giá trị hiện tại lẫn nguồn đã thiết lập nó.

System variable khác user-defined variable. System variable có tên như @@GLOBAL.max_connections và được MySQL quản lý. User-defined variable do session đặt với cú pháp @name và không phải tham số cấu hình server.

## 2. Hai phạm vi chính: GLOBAL và SESSION

GLOBAL là phạm vi toàn server. SESSION là phạm vi một kết nối hiện tại.

| Phạm vi | Tác động | Thời gian tồn tại |
|---|---|---|
| GLOBAL | Giá trị chung của server; thường là giá trị khởi tạo cho session mới | Trong runtime hiện tại; có thể mất sau restart nếu không persist |
| SESSION | Chỉ tác động kết nối hiện tại | Đến khi session kết thúc hoặc được đặt lại |

Một số biến có cả hai phạm vi. Một số biến chỉ có GLOBAL, một số chỉ có SESSION. Không được suy luận rằng mọi biến đều có thể đọc hoặc đặt ở cả hai phạm vi.

Ví dụ sql_mode có giá trị GLOBAL và SESSION:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

Hai giá trị có thể khác nhau vì session hiện tại có thể đã đặt sql_mode riêng. Khi kết nối mới được tạo, session thường nhận giá trị ban đầu từ biến GLOBAL tại thời điểm kết nối.

## 3. Đọc biến bằng @@GLOBAL và @@SESSION

Cú pháp đọc tường minh:

~~~sql
SELECT @@GLOBAL.max_connections;
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
~~~

Nếu biến có cả hai phạm vi, có thể dùng @@variable_name để đọc giá trị SESSION:

~~~sql
SELECT @@sql_mode;
~~~

Để tránh hiểu nhầm khi chẩn đoán, ưu tiên viết rõ @@GLOBAL hoặc @@SESSION. Nếu biến chỉ có GLOBAL, tham chiếu @@SESSION.variable_name có thể báo lỗi vì biến không có phạm vi session.

## 4. Liệt kê biến bằng SHOW VARIABLES

SHOW VARIABLES hiển thị giá trị biến trong phạm vi SESSION theo mặc định:

~~~sql
SHOW VARIABLES;
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'time_zone';
~~~

Để xem giá trị GLOBAL:

~~~sql
SHOW GLOBAL VARIABLES;
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'read_only';
~~~

SHOW SESSION VARIABLES thể hiện rõ phạm vi session:

~~~sql
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

Khi so sánh cấu hình, hãy truy vấn cả hai phạm vi nếu biến hỗ trợ cả GLOBAL và SESSION. Một giá trị SESSION khác GLOBAL không nhất thiết là lỗi; nó có thể được đặt có chủ đích bởi ứng dụng hoặc connection initialization.

## 5. Xem biến qua Performance Schema

Performance Schema cung cấp các bảng metadata để truy vấn system variable:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_variables
WHERE VARIABLE_NAME IN (
    'max_connections',
    'sql_mode',
    'read_only'
);
~~~

Giá trị SESSION:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.session_variables
WHERE VARIABLE_NAME IN (
    'sql_mode',
    'time_zone',
    'sort_buffer_size'
);
~~~

Để tìm nguồn cấu hình và thông tin thiết lập, có thể dùng performance_schema.variables_info:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'sql_mode',
    'innodb_buffer_pool_size'
);
~~~

Các cột metadata giúp điều tra biến được lấy từ mặc định, file cấu hình, dòng lệnh, persisted configuration hoặc được thay đổi trong runtime. Thông tin và giá trị cụ thể phụ thuộc phiên bản MySQL; kiểm tra schema Performance Schema trên server mục tiêu trước khi tự động hóa báo cáo.

## 6. Biến chỉ GLOBAL, chỉ SESSION và cả hai phạm vi

Ba nhóm phạm vi:

| Nhóm | Có thể đọc | Có thể đặt |
|---|---|---|
| GLOBAL-only | @@GLOBAL hoặc SHOW GLOBAL VARIABLES | Chỉ theo phạm vi GLOBAL nếu biến cho phép thay đổi |
| SESSION-only | @@SESSION hoặc SHOW SESSION VARIABLES | Chỉ trong session hiện tại nếu biến cho phép |
| GLOBAL và SESSION | Có thể đọc cả hai giá trị | Có thể đặt theo phạm vi tương ứng nếu biến cho phép |

Ví dụ max_connections là biến GLOBAL-only:

~~~sql
SELECT @@GLOBAL.max_connections;
~~~

Biến sql_mode có cả GLOBAL và SESSION:

~~~sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
~~~

Khi đọc tài liệu cho một biến, cần kiểm tra ba thuộc tính riêng: scope, dynamic và quyền cần thiết. Scope trả lời biến tồn tại ở đâu; dynamic trả lời có đổi được trong runtime không; privilege trả lời tài khoản nào được phép đổi.

## 7. Đặt biến SESSION bằng SET SESSION

SET SESSION thay đổi giá trị cho kết nối hiện tại:

~~~sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
~~~

Ví dụ đặt múi giờ cho session:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT @@SESSION.time_zone;
~~~

Thay đổi SESSION không ảnh hưởng các kết nối khác và không tự ghi vào cấu hình server. Khi session kết thúc, giá trị riêng của session đó không còn.

Đây là cách phù hợp khi một tác vụ cần hành vi riêng, chẳng hạn xuất dữ liệu theo múi giờ hoặc chạy một báo cáo với SQL mode xác định. Ứng dụng dùng connection pool cần khởi tạo hoặc reset session state một cách nhất quán khi mượn và trả connection.

## 8. Đặt biến GLOBAL bằng SET GLOBAL

SET GLOBAL thay đổi giá trị chung của server trong runtime:

~~~sql
SET GLOBAL max_connections = 300;

SELECT @@GLOBAL.max_connections;
~~~

Thay đổi GLOBAL thường ảnh hưởng đến các session mới hoặc các thao tác tham chiếu trực tiếp giá trị GLOBAL. Nó không tự ghi đè bản sao SESSION đã được tạo trong những kết nối đang tồn tại.

Ví dụ với sql_mode:

~~~sql
SET GLOBAL sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
~~~

Các kết nối đã tồn tại có thể vẫn giữ SESSION sql_mode cũ. Muốn một session hiện tại dùng giá trị mới, đặt SET SESSION riêng hoặc tạo kết nối mới theo quy trình ứng dụng.

SET GLOBAL không có nghĩa là cấu hình được lưu vĩnh viễn. Nếu server restart, giá trị có thể quay về nguồn cấu hình khởi động trước đó trừ khi dùng cơ chế persist hoặc cập nhật file cấu hình.

## 9. Phân biệt thay đổi GLOBAL và SESSION

Ví dụ hai kết nối A và B:

1. A kết nối khi GLOBAL sql_mode có giá trị X; SESSION của A nhận X.
2. B kết nối; SESSION của B cũng nhận X.
3. Quản trị viên SET GLOBAL sql_mode = Y.
4. A và B đang tồn tại vẫn có thể giữ SESSION sql_mode = X.
5. C kết nối mới sau thay đổi; SESSION của C nhận Y.
6. A có thể tự SET SESSION sql_mode = Z; việc đó không đổi B, C hoặc GLOBAL.

Minh họa:

~~~mermaid
flowchart TD
    G[GLOBAL sql_mode = X] --> A[Session A nhận X]
    G --> B[Session B nhận X]
    G2[SET GLOBAL sql_mode = Y] --> NG[Session mới nhận Y]
    A --> AS[SET SESSION sql_mode = Z]
    AS -. không đổi .-> G2
    AS -. không đổi .-> B
~~~

Mô hình này giải thích vì sao thay đổi GLOBAL không nhất thiết làm ứng dụng đang chạy thay đổi hành vi ngay. Khi triển khai thay đổi session-sensitive, cần có kế hoạch reconnect hoặc session reset.

## 10. Dynamic variable là gì?

Dynamic variable có thể thay đổi khi server đang chạy mà không cần restart, miễn là:

- Biến hỗ trợ phạm vi đang đặt.
- Giá trị mới nằm trong miền cho phép.
- Tài khoản có quyền phù hợp.
- Không có điều kiện runtime hoặc phụ thuộc khác ngăn việc thay đổi.

Ví dụ max_connections là biến GLOBAL có thể thay đổi động:

~~~sql
SET GLOBAL max_connections = 400;
~~~

Ví dụ sort_buffer_size hỗ trợ phạm vi SESSION và GLOBAL:

~~~sql
SET SESSION sort_buffer_size = 1048576;
~~~

Thay đổi biến động không có nghĩa là thay đổi không rủi ro. Tăng buffer theo session có thể nhân mức sử dụng bộ nhớ theo số session thực sự dùng thao tác cần buffer. Tăng max_connections cũng làm tăng khả năng server phải phục vụ nhiều kết nối và bộ nhớ liên quan.

Trước khi đổi, đọc mô tả biến, giới hạn min/max, đơn vị, scope, dynamic status và tác động tài nguyên.

## 11. Biến không thể thay đổi động và biến read-only

Một biến không dynamic không thể được thay đổi bằng SET runtime thông thường. Nó thường cần được cấu hình lúc khởi động qua option file hoặc command-line option. Một số biến read-only chỉ phản ánh trạng thái server và không có cách cấu hình giá trị theo ý muốn.

Ví dụ đọc version:

~~~sql
SELECT @@GLOBAL.version;
~~~

version là thông tin do server cung cấp; không thể dùng SET GLOBAL version để thay đổi phiên bản server.

Không đồng nhất các khái niệm:

- Dynamic: có thể thay đổi trong runtime theo scope và quyền.
- Non-dynamic/static: cần cấu hình khi khởi động hoặc theo cơ chế persist-only nếu biến hỗ trợ.
- Read-only: không thể gán bằng SET runtime thông thường.

Một biến có thể là GLOBAL-only và non-dynamic; một biến khác có thể GLOBAL-only nhưng dynamic. Scope và mutability là hai thuộc tính độc lập.

## 12. Read-only system variable khác chế độ read_only của server

Đây là hai ý nghĩa khác nhau:

1. Một system variable được đánh dấu read-only nghĩa là giá trị của chính biến đó không được thay đổi bằng SET runtime thông thường.
2. Biến read_only của MySQL là một công tắc cấu hình server để hạn chế thao tác ghi dữ liệu từ client.

read_only là một system variable có thể thay đổi động trong những điều kiện và quyền phù hợp. super_read_only mở rộng chế độ chỉ đọc và hạn chế cả một số tài khoản có quyền quản trị kết nối mà read_only có thể miễn trừ.

Ví dụ kiểm tra chế độ:

~~~sql
SELECT
    @@GLOBAL.read_only AS read_only_mode,
    @@GLOBAL.super_read_only AS super_read_only_mode;
~~~

Đừng suy luận rằng biến read_only bản thân nó là biến không thể thay đổi. Cũng đừng nhầm việc server đang ở chế độ read-only với thuộc tính read-only của một biến cấu hình khác.

## 13. SET PERSIST: đổi runtime và lưu cho lần khởi động sau

MySQL 8.0.11 giới thiệu cơ chế persisted system variables. SET PERSIST thay đổi biến GLOBAL trong runtime và lưu giá trị để áp dụng lại khi server khởi động:

~~~sql
SET PERSIST max_connections = 400;
~~~

Khác với SET GLOBAL:

- SET GLOBAL chỉ thay đổi runtime.
- SET PERSIST thay đổi runtime và ghi cấu hình persisted.

Giá trị persisted được MySQL quản lý trong file mysqld-auto.cnf trong data directory. Không chỉnh sửa file này bằng tay; hãy dùng SET PERSIST hoặc RESET PERSIST để MySQL quản lý nội dung và metadata.

SET PERSIST chỉ áp dụng cho biến GLOBAL có thể persist và được phiên bản hỗ trợ. Một số biến, giá trị hoặc trạng thái đặc biệt không thể persist.

## 14. SET PERSIST_ONLY: lưu cấu hình mà chưa đổi runtime

SET PERSIST_ONLY ghi giá trị vào persisted configuration nhưng không thay đổi giá trị runtime hiện tại:

~~~sql
SET PERSIST_ONLY some_global_variable = some_value;
~~~

Cú pháp minh họa trên dùng tên và giá trị tượng trưng; phải thay bằng biến GLOBAL thực sự hỗ trợ persist-only và giá trị hợp lệ theo tài liệu phiên bản đang chạy.

SET PERSIST_ONLY hữu ích cho biến chỉ có thể cấu hình khi khởi động. Sau khi ghi persisted value, server hiện tại vẫn chạy với giá trị đang có; giá trị mới chỉ có hiệu lực sau khi restart.

Không phải mọi biến read-only đều có thể persist. Một số biến trạng thái không có ý nghĩa cấu hình; một số biến bị loại khỏi persisted variable mechanism. Kiểm tra danh sách hỗ trợ và privilege trước khi thực hiện.

## 15. RESET PERSIST và hoàn tác cấu hình đã lưu

Để xóa một persisted setting:

~~~sql
RESET PERSIST max_connections;
~~~

Lệnh này xóa giá trị đã lưu cho biến khỏi persisted configuration. Nó không tự động khôi phục giá trị runtime hiện tại về mặc định; nếu biến đã được SET GLOBAL hoặc SET PERSIST trong runtime, giá trị đang chạy có thể tiếp tục giữ nguyên cho đến khi thay đổi hoặc restart.

Để xóa toàn bộ persisted system variable settings:

~~~sql
RESET PERSIST;
~~~

Đây là thao tác có phạm vi rộng. Trước khi dùng, kiểm tra các persisted settings đang tồn tại và chỉ xóa những cấu hình có chủ đích. Sau khi xóa, kiểm tra lại metadata persisted và lập kế hoạch restart nếu cần đưa runtime về nguồn cấu hình còn lại.

Có thể xem các biến đã persist:

~~~sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
~~~

## 16. Nguồn cấu hình và thứ tự ưu tiên

Một biến có thể được thiết lập bởi nhiều nguồn:

- Giá trị mặc định được biên dịch trong MySQL.
- Option file như my.cnf hoặc my.ini.
- Tham số command line khi khởi động mysqld.
- Persisted configuration do SET PERSIST hoặc SET PERSIST_ONLY tạo.
- Lệnh SET GLOBAL trong runtime.
- Lệnh SET SESSION trong một kết nối.

Giá trị hiện tại là kết quả của quá trình khởi tạo và các thay đổi runtime. Một session có thể có giá trị khác global do session override.

Để điều tra nguồn, dùng:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

VARIABLE_SOURCE và VARIABLE_PATH giúp nhận biết nguồn cấu hình theo phiên bản. Với một biến vừa được thay đổi runtime, metadata có thể phản ánh nguồn hoặc thông tin set gần nhất. Không nên suy luận chỉ từ một dòng SHOW VARIABLES rằng giá trị đến từ file nào.

## 17. Quyền cần thiết khi thay đổi system variable

Đọc biến thường cần quyền truy vấn phù hợp trên server và Performance Schema. Thay đổi biến GLOBAL cần quyền quản trị cấu hình.

Trong MySQL 8.0, các dynamic privilege quan trọng gồm:

- SYSTEM_VARIABLES_ADMIN: cho phép thực hiện nhiều thao tác quản trị system variable như SET GLOBAL và SET PERSIST.
- PERSIST_RO_VARIABLES_ADMIN: cho phép persist một số biến read-only bằng SET PERSIST_ONLY theo quy tắc của phiên bản.
- SUPER là quyền cũ đã bị phân rã thành nhiều dynamic privilege; không nên cấp SUPER rộng chỉ để một ứng dụng thay đổi một biến.

Một số biến nhạy cảm còn có điều kiện hoặc quyền bổ sung. Quyền cụ thể cần kiểm tra trong tài liệu của biến và phiên bản MySQL. SET SESSION cho session của chính mình thường không yêu cầu quyền SYSTEM_VARIABLES_ADMIN, nhưng vẫn có thể bị hạn chế bởi loại biến hoặc quyền đặc biệt.

Kiểm tra quyền:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Nguyên tắc vận hành:

1. Chỉ DBA hoặc tài khoản quản trị cấu hình được thay đổi biến GLOBAL.
2. Không cấp quyền quản trị system variable cho tài khoản ứng dụng thông thường.
3. Chỉ cấp dynamic privilege cần thiết cho người vận hành.
4. Ghi nhận người thay đổi, thời điểm, giá trị cũ và mới.
5. Kiểm thử thay đổi trên môi trường staging trước production.

## 18. Giới hạn và validation của giá trị biến

Không phải mọi giá trị đều được chấp nhận. MySQL có thể từ chối khi:

- Giá trị nằm ngoài min/max.
- Kiểu dữ liệu không phù hợp.
- Giá trị enum không nằm trong danh sách hỗ trợ.
- Biến không hỗ trợ scope đang đặt.
- Biến không dynamic.
- Tài khoản thiếu privilege.
- Một điều kiện runtime hoặc phụ thuộc khác không được thỏa.

Ví dụ đặt giá trị session:

~~~sql
SET SESSION max_execution_time = 5000;
~~~

max_execution_time giới hạn thời gian thực thi SELECT ở session theo đơn vị millisecond trong các phiên bản hỗ trợ. Nếu cần thay đổi cho mọi session mới, có thể cân nhắc GLOBAL sau khi kiểm tra scope và chính sách.

Không dùng một lệnh SET hàng loạt để thay đổi nhiều biến trong production nếu chưa kiểm tra từng giá trị và khả năng rollback. Khi một biến không được hỗ trợ hoặc sai phạm vi, cả câu lệnh có thể thất bại.

## 19. Kiểm tra biến trước và sau thay đổi

Một quy trình an toàn:

~~~sql
SELECT
    @@GLOBAL.max_connections AS global_before;

SET GLOBAL max_connections = 400;

SELECT
    @@GLOBAL.max_connections AS global_after;
~~~

Nếu cần lưu cấu hình:

~~~sql
SET PERSIST max_connections = 400;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Sau thay đổi, xác minh:

- Giá trị runtime có đúng không.
- Session mới có nhận giá trị mong muốn không.
- Session cũ có cần reconnect hoặc reset không.
- Persisted configuration có chứa giá trị mong muốn không.
- Log có cảnh báo hoặc lỗi cấu hình không.
- Tài nguyên server có tăng bất thường không.

Đừng chỉ dựa vào việc câu SET trả thành công. Cần đọc lại biến và theo dõi tác động trong workload thực.

## 20. Ví dụ quản lý sql_mode cho ứng dụng

Giả sử server cần đặt SQL mode mặc định cho kết nối mới:

~~~sql
SELECT @@GLOBAL.sql_mode;

SET PERSIST sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
~~~

Một session hiện tại có thể vẫn giữ sql_mode cũ. Để kiểm tra:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS server_default,
    @@SESSION.sql_mode AS this_connection;
~~~

Nếu ứng dụng cần cùng một SQL mode ngay trong connection đang mở, hãy đặt SESSION trong bước khởi tạo connection hoặc reconnect theo kế hoạch. Không giả định SET PERSIST đã cập nhật tất cả session hiện hữu.

Trước khi thay sql_mode, chạy thử bộ kiểm thử dữ liệu và truy vấn. Thay đổi strictness có thể làm các câu INSERT/UPDATE trước đây chấp nhận warning chuyển thành lỗi.

## 21. SET_VAR hint cho một câu lệnh

Một số system variable có thể được đặt tạm thời cho một statement bằng optimizer hint SET_VAR nếu biến và phiên bản hỗ trợ:

~~~sql
SELECT /*+ SET_VAR(sort_buffer_size = 262144) */
       customer_id, total_amount
FROM orders
ORDER BY total_amount DESC
LIMIT 100;
~~~

SET_VAR không giống SET SESSION: nó áp dụng trong phạm vi statement được hint và không biến thành cấu hình lâu dài của connection. Không phải mọi system variable đều được phép dùng với SET_VAR; hãy kiểm tra danh sách hỗ trợ và xác minh hint có được optimizer chấp nhận.

Đây là công cụ tinh chỉnh có phạm vi hẹp. Không dùng hint để che giấu vấn đề thiết kế truy vấn hoặc thiếu index.

## 22. Phân biệt cấu hình runtime và cấu hình khởi động

| Nhu cầu | Cách thường dùng | Hiệu lực |
|---|---|---|
| Thay đổi session hiện tại | SET SESSION | Ngay trong session |
| Thay đổi server runtime | SET GLOBAL | Ngay trong runtime; session cũ có thể giữ giá trị riêng |
| Thay đổi runtime và lưu qua restart | SET PERSIST | Ngay trong runtime và lần khởi động sau |
| Chỉ lưu để áp dụng sau restart | SET PERSIST_ONLY | Sau khi restart |
| Cấu hình từ đầu khi mysqld khởi động | Option file/command line | Khi server khởi động |
| Xóa một persisted override | RESET PERSIST variable | Xóa persisted value; runtime không tự đổi ngược |

Không chọn SET PERSIST chỉ vì nó tiện hơn. Với thay đổi ảnh hưởng lớn như connection limit, buffer pool, logging hoặc replication, cần đánh giá RAM, CPU, I/O, thời gian restart và khả năng rollback.

## 23. Runbook thay đổi biến GLOBAL trong production

1. Xác định đúng tên biến và phiên bản MySQL.
2. Đọc scope, dynamic status, min/max, đơn vị và privilege trong tài liệu.
3. Ghi lại GLOBAL và SESSION values hiện tại.
4. Kiểm tra nguồn cấu hình trong variables_info và persisted_variables nếu có.
5. Đánh giá tác động đến RAM, CPU, I/O, kết nối và workload.
6. Thử trên staging với dữ liệu và tải gần production.
7. Chọn SET GLOBAL, SET PERSIST hoặc thay đổi option file theo yêu cầu tồn tại.
8. Đọc lại giá trị runtime và persisted.
9. Kiểm tra session mới và session đang tồn tại.
10. Theo dõi error log, metrics và độ trễ sau thay đổi.
11. Ghi lại người thực hiện, thời điểm và kế hoạch hoàn tác.
12. Nếu cần restart, thực hiện theo maintenance window và xác minh sau khi server khởi động.

## 24. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| SET GLOBAL báo access denied | Thiếu SYSTEM_VARIABLES_ADMIN hoặc quyền tương ứng | Kiểm tra SHOW GRANTS và cấp quyền tối thiểu |
| SET SESSION báo biến không tồn tại trong scope | Biến GLOBAL-only | Dùng GLOBAL nếu được phép |
| SET GLOBAL báo biến read only | Biến không thể thay đổi runtime | Kiểm tra startup-only/read-only và SET PERSIST_ONLY nếu hỗ trợ |
| Thay GLOBAL nhưng session cũ không đổi | Session đã có bản sao riêng | Reconnect hoặc SET SESSION theo kế hoạch |
| Giá trị mất sau restart | Chỉ dùng SET GLOBAL | Dùng SET PERSIST hoặc option file phù hợp |
| SET PERSIST_ONLY không đổi giá trị hiện tại | Đây là hành vi đúng | Restart trong maintenance window để áp dụng |
| RESET PERSIST nhưng runtime vẫn giữ giá trị | RESET chỉ xóa persisted override | SET GLOBAL hoặc restart theo cấu hình còn lại |
| Câu SET bị từ chối | Giá trị sai miền, sai kiểu hoặc biến không dynamic | Kiểm tra mô tả và miền giá trị |
| Ứng dụng có session state không đồng nhất | Connection pool tái sử dụng session | Chuẩn hóa bước initialize/reset connection |
| Nhầm read-only variable với read_only mode | Hai khái niệm khác nhau | Phân biệt mutability của biến và chế độ ghi dữ liệu |

## 25. Bài tập thực hành

1. Dùng SHOW GLOBAL VARIABLES và SHOW SESSION VARIABLES để tìm sql_mode.
2. Đọc @@GLOBAL.sql_mode và @@SESSION.sql_mode trên cùng một connection.
3. Mở hai connection; thay đổi SESSION sql_mode ở connection A và xác nhận connection B không đổi.
4. Thay đổi GLOBAL sql_mode trong môi trường test; xác nhận session mới nhận giá trị mới trong khi session cũ có thể giữ giá trị trước.
5. Đọc max_connections và giải thích vì sao đây là biến GLOBAL-only.
6. Thử đặt SET SESSION max_connections trong môi trường test và quan sát lỗi scope.
7. Kiểm tra version và giải thích vì sao không thể SET GLOBAL version.
8. Thay đổi một biến dynamic trong runtime, đọc lại giá trị và restart môi trường test để quan sát giá trị không persist.
9. Dùng SET PERSIST cho một biến GLOBAL hỗ trợ persist; kiểm tra performance_schema.persisted_variables.
10. Dùng SET PERSIST_ONLY trên một biến được tài liệu xác nhận chỉ áp dụng lúc startup; xác nhận runtime chưa đổi và giá trị sau restart thay đổi.
11. Dùng RESET PERSIST để xóa một override; phân biệt persisted value với runtime value.
12. Truy vấn performance_schema.variables_info để xem nguồn cấu hình.
13. So sánh read-only system variable với biến read_only và super_read_only của server.
14. Viết runbook thay đổi max_connections hoặc một biến buffer có đánh giá tài nguyên, kiểm tra sau thay đổi và kế hoạch rollback.

Bạn hoàn thành bài khi đọc và đặt được biến đúng phạm vi, giải thích được vì sao GLOBAL không tự ghi đè SESSION đang tồn tại, phân biệt dynamic với startup-only/read-only, dùng đúng SET GLOBAL/SESSION/PERSIST/PERSIST_ONLY và kiểm tra được nguồn cấu hình. Thay đổi system variable là một thao tác vận hành có tác động rộng; luôn xác minh scope, quyền, persistence và ảnh hưởng tài nguyên trước khi áp dụng.
