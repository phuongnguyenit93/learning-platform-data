# Nhật ký truy cập, kiểm toán và xử lý dữ liệu nhạy cảm trong PostgreSQL

Một hệ thống PostgreSQL an toàn phải trả lời được hai nhóm câu hỏi:

1. **Ai đã truy cập hoặc thay đổi dữ liệu, vào thời điểm nào, từ đâu, bằng cách nào?**
2. **Trong quá trình ghi nhận sự kiện, hệ thống có vô tình làm lộ dữ liệu nhạy cảm không?**

Hai mục tiêu này đôi khi xung đột. Ghi toàn bộ câu SQL và tham số có thể giúp điều tra một sự cố, nhưng cũng có thể làm rò mật khẩu, email, số điện thoại, access token hoặc dữ liệu sức khỏe vào file log. Ngược lại, chỉ ghi “có một truy vấn xảy ra” thì chưa đủ để xác định bản ghi nào bị thay đổi.

PostgreSQL cung cấp nhiều lớp quan sát và kiểm soát:

- **Server log**: đăng nhập, ngắt kết nối, lỗi, câu lệnh DDL và câu lệnh chậm theo cấu hình.
- **pgAudit** (extension tùy chọn): sự kiện kiểm toán ở mức statement/object class, tùy cách cấu hình.
- **Audit table + trigger**: ghi lịch sử thay đổi ở mức hàng cho `INSERT`/`UPDATE`/`DELETE`.
- **Application log/trace**: danh tính người dùng nghiệp vụ, request ID, quyết định phân quyền và tương tác với hệ thống ngoài.
- **Privileges, RLS, views và kỹ thuật bảo vệ dữ liệu**: giới hạn ai có thể đọc dữ liệu gốc hoặc log.
- **Backup, retention, encryption và quy trình điều tra**: bảo đảm nhật ký có ích, được bảo vệ và không tồn tại vô hạn.

~~~mermaid
flowchart TD
    U["Người dùng / service"] --> API["API: xác thực, phân quyền, request_id"]
    API --> DB["PostgreSQL session"]
    DB --> SQL["Câu SQL"]
    DB --> SLOG["Server log: connect/error/statement/duration"]
    SQL --> PA["pgAudit nếu đã cài và cấu hình"]
    SQL --> TR["DML triggers: audit thay đổi hàng"]
    TR --> AT["Audit table trong cùng transaction"]
    API --> AL["App log / trace an toàn"]
    SLOG --> SIEM["Log pipeline / SIEM có kiểm soát"]
    PA --> SIEM
    AL --> SIEM
    AT --> AUD["Audit reviewer có quyền tối thiểu"]
~~~

Bài này thuộc chương **Bảo mật**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ so sánh các cách ghi nhận, thực hành audit bảng chứa dữ liệu cá nhân nhưng **không sao chép giá trị nhạy cảm vào log**, và thiết kế chính sách truy cập, giữ lại, xóa, mã hóa và ứng phó sự cố.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt log hệ thống, audit thao tác, audit dữ liệu và telemetry hiệu năng.
2. Nhận biết PostgreSQL server log ghi được gì và không ghi được gì.
3. Cấu hình có chủ đích `log_connections`, `log_disconnections`, `log_statement`, `log_min_duration_statement` và `log_line_prefix`.
4. Hiểu rủi ro lộ literal/parameter values trong SQL, server logs và error messages.
5. Giải thích vai trò và giới hạn của extension **pgAudit**.
6. Thiết kế audit trigger không lưu toàn bộ `OLD`/`NEW` khi có dữ liệu nhạy cảm.
7. Hiểu audit trigger và dữ liệu nghiệp vụ **rollback cùng transaction**.
8. Biết vì sao trigger DML **không theo dõi được SELECT** và không thay thế access audit.
9. Dùng `session_user`, `current_user`, `application_name` và request ID có nhận thức về độ tin cậy.
10. Phân quyền đọc bảng audit/log theo nguyên tắc least privilege.
11. Giảm dữ liệu nhạy cảm trong view, SQL text, application log, query plans và thống kê.
12. Phân biệt encryption at rest, TLS, field-level encryption và hashing/HMAC.
13. Thiết kế retention, backup và yêu cầu kiểm toán phù hợp pháp lý/nghiệp vụ.
14. Xây runbook điều tra với khả năng tương quan sự kiện và chống chỉnh sửa log ở mức cần thiết.
15. Thực hành các câu truy vấn kiểm chứng và xử lý các trường hợp lỗi.

## 2. Threat model: những gì cần bảo vệ

Trước khi bật một log thật nhiều chi tiết, hãy liệt kê:

| Tài sản | Nguy cơ | Kiểm soát có thể cần |
| --- | --- | --- |
| Thông tin đăng nhập DB | Lộ credential/connection string | Secret manager, TLS, rotate, log redaction |
| Dữ liệu cá nhân | Log ghi lại email/điện thoại/địa chỉ | Data minimization, mask, ACL |
| Mã xác thực, token, API key | In trong SQL/log/errors | Không log, secret scrubbing, rotate khi lộ |
| Lịch sử giao dịch | Bị xóa hoặc sửa dấu vết | Tách quyền, xuất log tập trung, lưu trữ bất biến khi cần |
| Danh tính người thao tác | Log chỉ có tài khoản DB dùng chung | App identity, request ID, mapping đáng tin |
| Kế hoạch SQL/câu truy vấn | Lộ tên bảng, schema, giá trị literal | Phân quyền monitoring, giới hạn query text |
| File log và backup | Bị đọc hoặc lưu quá hạn | Encryption, access review, retention, secure deletion |

Một hệ thống có audit thật chi tiết nhưng cho mọi developer đọc log thô chứa dữ liệu khách hàng **không an toàn hơn** một hệ thống được thiết kế thu thập tối thiểu.

### Điều cần ghi từ đầu

- Loại dữ liệu nào thuộc **PII** (personally identifiable information), tài chính, dữ liệu sức khỏe, dữ liệu bí mật thương mại?
- Loại sự kiện nào bắt buộc phải chứng minh?
- Có bao nhiêu thời gian cần giữ log?
- Ai được xem, export, xóa hoặc cấu hình log?
- Bằng chứng cần có tính chống sửa đổi ở cấp độ nào?
- Người dùng/đối tác có yêu cầu xóa hoặc hạn chế lưu dữ liệu không?

Không có một cấu hình log phù hợp cho mọi ngành và mọi khu vực pháp lý.

## 3. Bốn lớp log thường bị nhầm lẫn

| Lớp | Ví dụ | Trả lời được | Giới hạn |
| --- | --- | --- | --- |
| **Connection log** | Session từ host A đăng nhập role X | Role/địa chỉ kết nối, thời gian | Không chứng minh người dùng web thực |
| **Statement log** | Role X chạy một `UPDATE` | Lệnh SQL diễn ra khi bật logging | Không mặc nhiên biết các giá trị OLD/NEW thực tế |
| **Row audit** | Customer 101 đổi status active → blocked | Hàng nào đổi, giá trị được chọn | Không quan sát được SELECT bằng DML trigger |
| **Application audit** | User 42 phê duyệt yêu cầu 9001 | Ý định nghiệp vụ, actor, request ID | Phải liên kết với DB transaction và bảo vệ integrity |

### Tránh một hiểu nhầm lớn

**Có một câu UPDATE được log không đồng nghĩa UPDATE đã commit thành công.** Statement có thể lỗi hoặc transaction có thể bị rollback sau đó.

Tương tự, row audit trong cùng database transaction mô tả thay đổi **được commit** khi transaction hoàn thành; nó không ghi bền mọi **lần thử bị từ chối**.

## 4. PostgreSQL server log chứa gì?

Tùy cấu hình và phiên bản, server log có thể chứa:

- Kết nối thành công, ngắt kết nối, lỗi xác thực.
- Thông điệp ERROR, FATAL, PANIC và ngữ cảnh liên quan.
- Statement được chọn theo loại hoặc thời lượng.
- Deadlock, lock wait, checkpoint, autovacuum, replication events theo cấu hình.
- Chi tiết error/context, có khi là SQL text hoặc tham số nhạy cảm.
- Tên role/database, application name, process ID, client endpoint.

**Server log không mặc định là một bảng SQL** có thể SELECT để xem lịch sử mọi hành động. PostgreSQL thường ghi file hoặc gửi tới stderr, syslog, event log hoặc đích được cấu hình khác.

### Câu hỏi thiết kế

Bạn muốn log phục vụ **troubleshooting** hay **compliance audit**? Hai nhu cầu có overlap nhưng không đồng nhất:

- Troubleshooting muốn tìm lệnh chậm/lỗi.
- Compliance muốn biết hoạt động nào xảy ra và ai được ủy quyền.
- Forensics có thể cần liên hệ nhiều nguồn độc lập và bảo toàn bằng chứng.

## 5. Chọn log_destination và logging_collector

Ví dụ một **cấu hình tham khảo** trong `postgresql.conf`:

~~~conf
# Ví dụ tham khảo, KHÔNG sao chép nguyên vào production.
log_destination = 'csvlog'
logging_collector = on
log_connections = on
log_disconnections = on
log_statement = 'ddl'
log_min_duration_statement = '500ms'
log_min_error_statement = error
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%r tx=%x '
~~~

### Ý nghĩa

- `csvlog`: định dạng có cấu trúc cột, thuận tiện đưa vào log pipeline.
- `logging_collector`: PostgreSQL quản lý việc thu log tới file khi sử dụng cơ chế này.
- `log_connections`: ghi sự kiện kết nối theo tùy chọn/version.
- `log_disconnections`: ghi sự kiện ngắt kết nối.
- `log_statement='ddl'`: log một lớp lệnh thay đổi định nghĩa schema.
- `log_min_duration_statement='500ms'`: ghi câu chạy từ ngưỡng thời gian được chọn.
- `log_min_error_statement=error`: log statement liên quan đến lỗi ở mức được chọn.
- `log_line_prefix`: thêm metadata để tương quan dòng log, đặc biệt hữu ích khi dùng log text; các định dạng có cấu trúc có trường riêng.

### Chú ý phạm vi thay đổi

Một số tham số như `logging_collector` hoặc `shared_preload_libraries` cần **server restart**, không chỉ reload. Những tham số khác có thể reload hoặc set ở phạm vi session/role tùy `context`. Hãy xem `pg_settings.context` trên phiên bản thật thay vì giả định tất cả dùng `SELECT pg_reload_conf()` là đủ.

**Cấu hình trên là ví dụ giáo dục, không phải security baseline universal.** Log statement chậm/DDL có thể chứa SQL literals nhạy cảm; một hệ thống PII nghiêm ngặt có thể chọn ngưỡng/chế độ khác.

## 6. Phân biệt stderr, csvlog và jsonlog

| Định dạng/đích | Ưu điểm | Lưu ý |
| --- | --- | --- |
| `stderr` + collector | Dễ dùng, phổ biến | Cần parser nếu đưa vào SIEM |
| `csvlog` | Có cột rõ, dễ ingest | Cần kiểm soát file và quoting đúng chuẩn CSV |
| `jsonlog` | Structured JSON | Có từ PostgreSQL 15; kiểm tra major version |
| `syslog` | Tích hợp hệ thống log của OS | Metadata/format và quyền phụ thuộc nền tảng |
| OS/event logging | Có thể gắn với infra | Không tự cung cấp mọi trường audit nghiệp vụ |

Việc chọn định dạng **không làm log an toàn mặc định**. JSON/CSV vẫn có thể chứa query text, parameters, PII và error detail như text log.

### Quản lý file log

- Chọn thư mục có ACL phù hợp, không public qua web server.
- Rotate để tránh đầy disk; kiểm tra `log_rotation_age` và `log_rotation_size` khi áp dụng.
- Đặt retention và quyền xóa theo chính sách.
- Xuất log về hệ thống tập trung khi cần kiểm toán/incident response.
- Mã hóa storage/backup và bảo vệ đường truyền tới collector.

## 7. log_line_prefix: tương quan nhưng không đồng nghĩa định danh người thật

Ví dụ:

~~~conf
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%r tx=%x '
~~~

Các placeholder thông dụng:

| Placeholder | Mục đích |
| --- | --- |
| `%m` | Timestamp có milliseconds |
| `%p` | Process ID |
| `%u` | Database user |
| `%d` | Database name |
| `%a` | application_name |
| `%r` | Remote host và port |
| `%x` | Transaction ID, nếu được cấp/phù hợp |
| `%c` | Session ID hữu ích để nhóm dòng log |
| `%l` | Số thứ tự dòng trong session |

Một prefix được thiết kế đúng giúp liên hệ log lỗi với một session và khoảng thời gian, nhất là khi nhiều connection cùng gửi queries.

### Cảnh báo

`application_name` thường do client cung cấp hoặc có thể thay đổi trong session. Nó hữu ích để phân loại dịch vụ, **không phải bằng chứng chống giả mạo về danh tính con người**.

Tương tự, client IP có thể là IP của proxy, pooler hoặc host ứng dụng, không phải IP cuối của người dùng.

## 8. log_statement: mức nào phù hợp?

Các giá trị thường gặp:

| Giá trị | Ý nghĩa tổng quát |
| --- | --- |
| `none` | Không ghi statement chỉ theo cơ chế log_statement |
| `ddl` | Ghi nhóm lệnh định nghĩa dữ liệu |
| `mod` | Ghi DDL và nhóm câu thay đổi dữ liệu |
| `all` | Ghi mọi statement thuộc phạm vi cơ chế |

### log_statement=all có rủi ro gì?

- Log lớn, chi phí IO/CPU/dung lượng cao.
- Query text chứa literal như `WHERE email = '...'` có thể bị ghi lại.
- Một số cấu hình/loại execute có thể ghi bind parameters.
- Lệnh SQL quản trị hoặc query text có thể chứa cấu trúc bí mật.
- Tăng phạm vi dữ liệu cần bảo vệ và chi phí điều tra.

**Không bật `log_statement='all'` trên production nhạy cảm chỉ vì “cần audit”** mà không có threat model, load test, policy và biện pháp bảo vệ log.

### Log statement không chắc chứng minh kết quả

Một `UPDATE` được log trước khi thực thi hoàn chỉnh có thể:

- Vi phạm constraint.
- Bị deadlock và rollback.
- Bị transaction rollback sau đó.
- Chạm 0 row.
- Chạm nhiều row.

Server log text không tự cung cấp một row-change history hoàn chỉnh.

## 9. log_min_duration_statement và truy vấn chậm

~~~conf
log_min_duration_statement = '500ms'
~~~

Mục đích là nhận biết statements vượt ngưỡng. Nếu dùng giá trị `-1` theo semantics tham số, cơ chế log theo thời lượng bị tắt.

### Tại sao vẫn có rủi ro PII?

Một truy vấn chậm có thể chứa text:

~~~sql
-- ANTI-PATTERN: có dữ liệu cá nhân literal trong SQL text.
SELECT *
FROM accounts
WHERE email = 'private-person@example.test';
~~~

Dù không bật `log_statement='all'`, query vẫn có thể được log do chậm hoặc lỗi. **Parameterized query giúp tránh SQL injection và giảm literal trong query text, nhưng không cam kết mọi hệ thống log đều che mọi bind parameter.**

### Sampling

PostgreSQL hỗ trợ những cơ chế log/sampling câu lệnh chậm theo version, chẳng hạn `log_min_duration_sample` và `log_statement_sample_rate`. Dùng chúng có thể giảm volume, nhưng sampling **không phải kiểm toán đầy đủ**: một sự kiện cụ thể có thể không được ghi.

## 10. Tham số truy vấn có thể bị lộ qua log

Các phiên bản PostgreSQL hỗ trợ cấu hình về độ dài parameter được log, ví dụ:

~~~conf
# Ví dụ chọn hạn chế ghi parameter values khi có hỗ trợ.
log_parameter_max_length = 0
log_parameter_max_length_on_error = 0
~~~

Đây là những tham số cần xác nhận theo **major version** và cơ chế log thực tế.

### Không hứa “parameterization = không lộ bí mật”

Prepared statements:

~~~sql
SELECT customer_id
FROM customers
WHERE email = $1;
~~~

thường loại literal email khỏi text câu SQL. Nhưng:

- Driver/server/monitoring có thể ghi bind values theo cấu hình.
- Application có thể log request payload trước khi bind.
- Error messages/context có thể chứa giá trị.
- SQL động vẫn có thể nối literal vào text.
- `pg_stat_activity.query` và log công cụ bên thứ ba có thể hiện câu query gần đây.

Nếu phải xử lý token/mật khẩu, **không log giá trị** và giảm việc đưa bí mật qua các câu SQL không cần thiết.

## 11. Các cấu hình log khác cần được hiểu đúng

| Cấu hình | Mục đích | Rủi ro/đánh đổi |
| --- | --- | --- |
| `log_min_messages` | Mức severity server log | Quá chi tiết tạo volume |
| `log_min_error_statement` | Log statement khi thông điệp lỗi đạt ngưỡng | Query text có thể nhạy cảm |
| `log_error_verbosity` | Độ chi tiết error | Context/DETAIL có thể lộ nội dung |
| `log_lock_waits` | Quan sát lock waits lâu | Thêm log, không thay phân tích concurrency |
| `deadlock_timeout` | Tham số liên quan phát hiện deadlock/log lock wait | Không chỉ là logging knob |
| `log_checkpoints` | Thông tin checkpoint theo version | Volume và phân tích IO |
| `log_autovacuum_min_duration` | Thông tin autovacuum dài | Hữu ích vận hành, không phải access audit |
| `log_duration` | Thời lượng statements | Dễ tăng volume |
| `log_temp_files` | Theo dõi temp files | Không là bằng chứng truy cập PII |

Bật log gì phải dựa vào mục tiêu. Một error log đầy đủ **không thay audit SELECT**; một audit SELECT đầy đủ **không thay monitoring latency**.

## 12. pgAudit: extension cho audit ở mức câu lệnh

**pgAudit** là extension riêng cho PostgreSQL, **không mặc nhiên có trong core installation**.

Khi đã được cài và cấu hình, pgAudit có thể hỗ trợ log các lớp thao tác như:

- READ: SELECT và những hoạt động đọc thuộc phạm vi cấu hình.
- WRITE: INSERT/UPDATE/DELETE/TRUNCATE và các hoạt động ghi thuộc phạm vi.
- DDL: thay đổi schema.
- ROLE: thay đổi quyền/role theo phạm vi.
- FUNCTION/MISC hoặc những lớp khác tùy phiên bản pgAudit.

### Giá trị của pgAudit

- Cung cấp cấu trúc audit detail hơn một log statement đơn giản.
- Phân loại hoạt động SQL.
- Có thể ghi các object được tham chiếu theo mode cấu hình.
- Hữu ích để đáp ứng yêu cầu “ai đã thực hiện lớp thao tác gì và lên object nào”.

### Giới hạn

- Không mặc nhiên cho biết **chính xác các hàng SELECT trả về**.
- Không thay row-change audit nếu cần giá trị OLD/NEW.
- Có thể ghi tên object/statement/query parameter nhạy cảm.
- Làm tăng log volume và IO.
- Phụ thuộc major version PostgreSQL/pgAudit, package installation và cấu hình server.

**pgAudit không phải một nút “bật là đạt tuân thủ pháp lý”.** Bạn vẫn cần phân quyền log, retention, chứng minh độ toàn vẹn và test coverage.

## 13. Cấu hình pgAudit: không ghi đè preload libraries

Một môi trường hỗ trợ có thể cần thêm `pgaudit` vào `shared_preload_libraries` và restart server theo hướng dẫn extension.

Ví dụ **minh họa configuration**:

~~~conf
# Chỉ áp dụng sau khi đã cài pgAudit tương thích version.
# KHÔNG ghi đè các preload libraries đang được hệ thống dùng.
shared_preload_libraries = 'pgaudit'
pgaudit.log = 'read, write, ddl, role'
pgaudit.log_parameter = off
~~~

**Không sao chép nguyên `shared_preload_libraries='pgaudit'`** vào một server đã dùng các library khác như `pg_stat_statements` hoặc monitoring agents: như vậy có thể loại bỏ các library cần thiết khỏi danh sách preload. Quản trị viên phải **thêm vào danh sách hiện tại**, đánh giá restart và compatibility.

Khi extension đã được preload/cài phù hợp:

~~~sql
-- Thực hiện bởi DBA trên database có nhu cầu và đủ quyền.
CREATE EXTENSION IF NOT EXISTS pgaudit;
~~~

Lưu ý:

- Package pgAudit có thể không có sẵn trên managed PostgreSQL.
- Cấu hình và availability khác theo nhà cung cấp cloud.
- Không phải mọi thay đổi `pgaudit.*` đều có cùng phạm vi session/system.
- `pgaudit.log_parameter=off` giảm rủi ro log bind values ở lớp pgAudit nhưng **không chặn mọi nơi khác ghi tham số**.
- Muốn log đầy đủ, phải kiểm tra coverage bằng test trong môi trường thật.

## 14. Audit SELECT không làm được bằng trigger DML

Một nhầm lẫn thường gặp:

> “Tôi thêm AFTER SELECT trigger lên bảng customers, vậy mọi lần đọc đều được lưu.”

PostgreSQL **không có row-level SELECT trigger thông thường** như `AFTER INSERT/UPDATE/DELETE` trên bảng.

~~~sql
-- CỐ Ý SAI, không phải cú pháp trigger table hợp lệ:
CREATE TRIGGER audit_select
AFTER SELECT ON customers
FOR EACH ROW
EXECUTE FUNCTION audit_read();
~~~

Để quan sát hoạt động đọc, cân nhắc:

1. Server statement logging hoặc pgAudit READ.
2. Application/API access audit với actor và resource được phép.
3. Hệ thống truy cập qua view/function có kiểm soát, khi phù hợp.
4. Tương quan kết nối và request trace.

### “SELECT được thực thi” khác “dữ liệu nào đã được xem”

Một câu `SELECT * FROM customers WHERE status='active'` được log không chứng minh người dùng thật đã đọc từng dòng hiển thị trên UI, cũng không chứng minh có bao nhiêu hàng thực tế được gửi cho client.

Muốn chứng minh danh sách đối tượng người dùng truy cập ở tầng nghiệp vụ, có thể cần audit ở API/service với IDs đã được authorization, nhưng cũng phải kiểm soát việc ghi ID để không lộ thêm PII.

## 15. Application log cần bổ sung danh tính nghiệp vụ

Một connection pool thường dùng cùng database role, ví dụ `shop_api`, để phục vụ nhiều người dùng.

PostgreSQL nhìn thấy:

~~~sql
SELECT
    session_user,
    current_user,
    current_setting('application_name', true) AS application_name;
~~~

- `session_user`: danh tính session authorization của DB.
- `current_user`: effective role; có thể thay đổi khi `SET ROLE` hoặc trong `SECURITY DEFINER`.
- `application_name`: thông tin client có thể đặt/đổi.

**Không có trường nào tự chứng minh một người dùng web cụ thể đã bấm nút**.

### Application audit event gợi ý

Một sự kiện nên có những trường được phép:

~~~json
{
  "event_type": "customer.status_changed",
  "actor_id": "user-42",
  "request_id": "req-7f31",
  "resource_type": "customer",
  "resource_id": "101",
  "old_status": "active",
  "new_status": "blocked",
  "result": "success"
}
~~~

Đây là cấu trúc minh họa; không dùng những ID dạng trên như dữ liệu thực. **Không tự thêm email, số định danh, access token hay request body đầy đủ** vào event nếu không bắt buộc.

Ứng dụng phải lấy actor từ cơ chế xác thực tin cậy, không đơn giản chấp nhận trường `actor_id` do request client tự gửi.

## 16. Request correlation và thông tin nào đáng tin?

Một service có thể dùng request ID từ gateway/tracing để liên kết:

~~~text
request_id -> app audit -> DB session / transaction -> pgAudit/server log
~~~

Ở PostgreSQL có thể đặt metadata session/transaction:

~~~sql
BEGIN;

SET LOCAL application_name = 'shop-api';

SET LOCAL app.request_id = 'req-lab-391';
SET LOCAL app.actor_id = 'user-42';

-- Các câu SQL nghiệp vụ ở đây.

COMMIT;
~~~

### Ranh giới độ tin cậy

Tên setting `app.request_id` và `app.actor_id` là custom GUC. Nhiều vai trò có thể tự đặt giá trị của các custom settings đó.

Vì vậy:

- **Không dùng `current_setting('app.actor_id')` làm cơ chế authorization chính** nếu DB client không tin cậy có thể tự thay đổi.
- Không coi nó là bằng chứng chống giả mạo.
- Dùng service/gateway tin cậy thiết lập, kiểm soát DB credentials và quyền.
- Với connection pooling, dùng `SET LOCAL` trong transaction rõ ràng và test reset.
- Nếu cần bằng chứng mạnh, dùng cơ chế ký/chứng thực ngoài database hoặc audit service đáng tin cậy.

## 17. pg_stat_activity là ảnh chụp, không phải lịch sử đầy đủ

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start,
    query_start,
    wait_event_type
FROM pg_stat_activity
WHERE datname = current_database();
~~~

`pg_stat_activity` phản ánh hoạt động phiên/backend ở thời điểm quan sát, không phải bảng lưu mọi câu SQL đã từng chạy.

### Cẩn thận với cột query

Cột `query` có thể chứa text SQL hiện tại/gần nhất, trong đó có literal nhạy cảm. Quyền nhìn thấy chi tiết session của người khác bị giới hạn theo role/privilege và cấu hình; các predefined monitoring roles như `pg_read_all_stats` có thể mở rộng quan sát.

**Không cấp quyền monitoring rộng cho người không được phép xem nội dung truy vấn.** Không tự đưa `pg_stat_activity.query` lên dashboard không kiểm soát.

### Query idle không cho biết người dùng đã xem dữ liệu gì

Một session state `idle` không có nghĩa session không từng truy cập PII. Và nhìn thấy câu query trong `pg_stat_activity` không chứng minh kết quả đã được UI hiển thị.

## 18. pg_stat_statements không phải forensic audit log

Extension `pg_stat_statements` giúp thống kê workload SQL theo nhóm query (thường normalized/fingerprinted), tổng số lần gọi, thời gian, blocks và các chỉ số theo phiên bản.

Nó hữu ích cho:

- Tối ưu truy vấn phổ biến.
- Nhận diện CPU/IO hotspots.
- Xác định workload cần lập index.
- Quan sát thay đổi hiệu năng theo thời gian.

Nó **không thay**:

- Audit từng request.
- Bằng chứng mọi lần đọc dữ liệu.
- Lịch sử OLD/NEW mỗi row.
- User-level business actor logs.

Thông tin query text/stats của extension cũng cần phân quyền. Khi bật `pg_stat_statements` có thể cần preload và extension creation theo version; không tự gỡ `pgaudit` khỏi `shared_preload_libraries` nếu cùng dùng.

## 19. Lab: bảng khách hàng có dữ liệu nhạy cảm

Ta sẽ tạo một schema thực hành riêng gồm:

- `customers`: dữ liệu định danh và liên hệ.
- `change_audit`: chỉ ghi **metadata thay đổi**, không ghi trực tiếp email/điện thoại.
- Một trigger function `SECURITY DEFINER` để viết audit.
- Một view chỉ hiển thị email đã che.

**Cảnh báo:** `DROP SCHEMA IF EXISTS sec_audit_lab CASCADE` xóa mọi đối tượng trong schema đó. Chỉ chạy trên **database thực hành riêng**, không chạy production hoặc nơi chứa dữ liệu cần giữ.

~~~sql
-- CHỈ CHẠY TRÊN DATABASE LAB.
DROP SCHEMA IF EXISTS sec_audit_lab CASCADE;
CREATE SCHEMA sec_audit_lab;

CREATE TABLE sec_audit_lab.customers (
    customer_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    email text NOT NULL,
    phone text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked', 'deleted')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE TABLE sec_audit_lab.change_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    operation text NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_status text,
    new_status text,
    contact_changed boolean NOT NULL DEFAULT false,
    occurred_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    db_session_role name NOT NULL,
    db_effective_role name NOT NULL,
    request_id text,
    actor_claim text,
    transaction_id bigint NOT NULL
);
~~~

### Vì sao không đặt FK audit.customer_id -> customers.customer_id?

Nếu cần giữ lịch sử việc xóa customer, FK từ audit tới bảng customers có thể làm khó hoặc ngăn DELETE parent, tùy action. Audit table lưu một ID lịch sử như metadata chứ không nhất thiết giữ FK tồn tại tới row đã xóa.

**Không có FK không đồng nghĩa audit chứa dữ liệu được tin vô điều kiện.** Function và quyền ghi audit phải được kiểm soát.

### Dữ liệu lab

~~~sql
INSERT INTO sec_audit_lab.customers (
    customer_id, display_name, email, phone, status
)
VALUES
    (101, 'Lan', 'lan@example.test', '+00-000-101', 'active'),
    (102, 'Minh', 'minh@example.test', '+00-000-102', 'active'),
    (103, 'Hoa', 'hoa@example.test', NULL, 'blocked');
~~~

`example.test` và số điện thoại trên là dữ liệu giả, không phải người thật.

## 20. Thiết kế audit table không sao chép PII

Cách rất tiện nhưng nguy hiểm:

~~~sql
-- ANTI-PATTERN với bảng chứa PII:
INSERT INTO audit_log(old_row, new_row)
VALUES (to_jsonb(OLD), to_jsonb(NEW));
~~~

Nếu bảng có email, phone, address, tax ID hoặc token, cách này có thể tạo **bản sao dữ liệu nhạy cảm ở audit table**, nơi thường được giữ lâu hơn và được nhiều người vận hành truy cập hơn.

Lab chọn trường tối thiểu:

- `customer_id`: khóa tham chiếu nghiệp vụ (vẫn có thể là dữ liệu cá nhân khi liên kết).
- `operation`: INSERT/UPDATE/DELETE.
- `old_status/new_status`: chỉ trạng thái.
- `contact_changed`: boolean cho biết email/phone có thay đổi.
- Timestamp, database session role, function effective role, transaction ID.
- Request/actor claims do ứng dụng đưa vào nhưng **không được xem là chống giả mạo**.

### Không lưu email cũ/mới có đánh đổi gì?

Bạn có thể biết “thông tin liên hệ đã được sửa” nhưng không khôi phục chính xác email cũ từ audit table. Đây là chủ đích **minimization**.

Nếu pháp lý/nghiệp vụ thật sự cần truy vết giá trị cũ, phải thiết kế phân quyền, encryption, retention và quyền truy cập riêng, không tự động `to_jsonb(OLD)` trên toàn row.

## 21. Viết audit trigger có phạm vi rõ

Hàm dưới đây là demo cho PostgreSQL PL/pgSQL. Nó dùng `SECURITY DEFINER` vì khi phân quyền nghiêm ngặt, ứng dụng không nên có direct `INSERT` vào bảng audit.

~~~sql
CREATE OR REPLACE FUNCTION sec_audit_lab.audit_customer_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, sec_audit_lab
AS $fn$
DECLARE
    v_customer_id bigint;
    v_old_status text;
    v_new_status text;
    v_contact_changed boolean := false;
    v_request_id text;
    v_actor_claim text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_customer_id := NEW.customer_id;
        v_old_status := NULL;
        v_new_status := NEW.status;

    ELSIF TG_OP = 'UPDATE' THEN
        v_customer_id := NEW.customer_id;
        v_old_status := OLD.status;
        v_new_status := NEW.status;
        v_contact_changed :=
            OLD.email IS DISTINCT FROM NEW.email
            OR OLD.phone IS DISTINCT FROM NEW.phone;

    ELSIF TG_OP = 'DELETE' THEN
        v_customer_id := OLD.customer_id;
        v_old_status := OLD.status;
        v_new_status := NULL;

    ELSE
        RAISE EXCEPTION 'Unsupported trigger operation: %', TG_OP;
    END IF;

    -- Hai claims này do session/app đặt; KHÔNG chống giả mạo.
    v_request_id := nullif(
        left(current_setting('app.request_id', true), 100),
        ''
    );

    v_actor_claim := nullif(
        left(current_setting('app.actor_id', true), 100),
        ''
    );

    INSERT INTO sec_audit_lab.change_audit (
        customer_id,
        operation,
        old_status,
        new_status,
        contact_changed,
        db_session_role,
        db_effective_role,
        request_id,
        actor_claim,
        transaction_id
    )
    VALUES (
        v_customer_id,
        TG_OP,
        v_old_status,
        v_new_status,
        v_contact_changed,
        session_user,
        current_user,
        v_request_id,
        v_actor_claim,
        txid_current()
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_customers_90_audit
AFTER INSERT OR UPDATE OR DELETE
ON sec_audit_lab.customers
FOR EACH ROW
EXECUTE FUNCTION sec_audit_lab.audit_customer_change();
~~~

### Vì sao dùng SECURITY DEFINER một cách thận trọng?

Trong một function `SECURITY DEFINER`, các quyền SQL bên trong được xét trong ngữ cảnh quyền của **owner function**. Điều này cho phép app ghi customers, còn audit function ghi vào audit table mà app không cần direct INSERT ở đó.

Nhưng:

- Owner function phải được quản trị chặt.
- `search_path` phải an toàn.
- Bảng đích phải schema-qualified.
- Không ghép SQL dynamic từ input không tin cậy.
- Kiểm tra `EXECUTE` privileges và quyền tạo/sửa function/trigger.
- Không để app role sở hữu/sửa trigger function hoặc audit table.
- `current_user` bên trong SECURITY DEFINER thường là **function owner**, không phải login actor.

### Vì sao không ghi toàn bộ OLD/NEW?

Trigger dùng `OLD`/`NEW` để so sánh, nhưng audit table chỉ nhận trạng thái và cờ `contact_changed`. Điều này tránh tạo bản sao email/phone trên mỗi UPDATE.

## 22. Lệnh INSERT trước khi tạo trigger có được audit không?

Không. Trigger mới bắt đầu phản ứng với các DML event **sau khi được tạo** (và trong các chế độ kích hoạt phù hợp). Ba customer seed được chèn **trước** trigger nên không có audit INSERT tương ứng.

Đây là điểm quan trọng khi triển khai thật:

- Không kỳ vọng `CREATE TRIGGER` tự scan các hàng quá khứ.
- Nếu compliance yêu cầu initial snapshot, xây bước **backfill** riêng.
- Phân biệt initial state/backfill event với một INSERT đã thật sự xảy ra tại thời điểm hiện tại.
- Tránh tạo “sự kiện giả” mang timestamp hiện tại khiến điều tra hiểu lầm.

## 23. Thử UPDATE và xem audit metadata

~~~sql
BEGIN;

SET LOCAL app.request_id = 'req-lab-391';
SET LOCAL app.actor_id = 'user-42';

UPDATE sec_audit_lab.customers
SET
    status = 'blocked',
    email = 'lan-updated@example.test',
    updated_at = clock_timestamp()
WHERE customer_id = 101;

SELECT
    audit_id,
    customer_id,
    operation,
    old_status,
    new_status,
    contact_changed,
    occurred_at,
    db_session_role,
    db_effective_role,
    request_id,
    actor_claim,
    transaction_id
FROM sec_audit_lab.change_audit
WHERE customer_id = 101
ORDER BY audit_id;

ROLLBACK;
~~~

Trong transaction trước rollback, dự kiến audit:

| Trường | Ý nghĩa |
| --- | --- |
| customer_id | 101 |
| operation | UPDATE |
| old_status | active |
| new_status | blocked |
| contact_changed | true |
| request_id | req-lab-391 |
| actor_claim | user-42 |
| transaction_id | ID transaction được cấp |
| db_effective_role | Function owner theo SECURITY DEFINER |

**Email mới và cũ không được ghi vào audit.**

### Sau ROLLBACK

Cả UPDATE customers và row mới ở `change_audit` đều bị hoàn tác. Identity sequence `audit_id` có thể đã tăng và không hoàn nguyên số đã cấp; khoảng trống audit_id **không tự chứng minh có bản ghi audit đã commit rồi bị mất**.

## 24. Thử INSERT và DELETE

~~~sql
BEGIN;

SET LOCAL app.request_id = 'req-lab-392';

INSERT INTO sec_audit_lab.customers (
    customer_id, display_name, email, status
)
VALUES (
    104, 'Demo', 'demo@example.test', 'active'
);

DELETE FROM sec_audit_lab.customers
WHERE customer_id = 104;

SELECT
    customer_id, operation, old_status, new_status
FROM sec_audit_lab.change_audit
WHERE customer_id = 104
ORDER BY audit_id;

ROLLBACK;
~~~

Trong transaction, dự kiến có:

- Một audit row `INSERT` cho customer 104.
- Một audit row `DELETE` cho customer 104.

Sau `ROLLBACK`, customer 104 và hai audit rows đều không tồn tại.

### DELETE và chính sách bảo vệ dữ liệu

Ghi một customer_id vào audit sau khi xóa row có thể phù hợp mục tiêu điều tra, nhưng ID đó vẫn có thể là dữ liệu cá nhân khi liên kết nguồn khác. Hãy đánh giá yêu cầu xóa dữ liệu, retention và khả năng deanonymization; không mặc định “chỉ lưu ID thì không còn PII”.

## 25. Audit cùng transaction: lợi ích và giới hạn

**Lợi ích:**

- Không có thay đổi customer đã commit nếu trigger audit bắt buộc gặp lỗi không được xử lý.
- Audit row và business row commit cùng transaction.
- Có thể xem OLD/NEW với ngữ cảnh DML.
- Dễ truy vấn bằng SQL theo ID và thời gian.

**Giới hạn:**

- Transaction rollback → audit INSERT cũng rollback.
- DML trigger không nhìn thấy SELECT.
- Một chủ bảng/superuser hoặc role có quyền DDL đặc biệt có thể can thiệp trigger/audit.
- Audit table có thể tạo overhead ghi, index, WAL và vacuum.
- Không tự cung cấp bằng chứng tamper-evident trước đối thủ có quyền quản trị cao nhất.

### Cần audit cả lần thử thất bại?

Dùng **application/security logs hoặc server/pgAudit logs** ngoài transaction tương ứng, với chính sách lưu trữ đáng tin. Không cố bắt exception rồi INSERT vào bảng audit **trong cùng transaction đang rollback** và mong dòng đó commit độc lập.

PostgreSQL trigger/PL/pgSQL exception handler không mặc nhiên là một **autonomous transaction**.

## 26. Không dùng audit trigger để che lỗi ghi dữ liệu

Một anti-pattern:

~~~sql
-- ANTI-PATTERN trong audit trigger:
BEGIN
    INSERT INTO audit_table (...);
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

Nếu audit là yêu cầu bắt buộc, nuốt mọi lỗi sẽ khiến hàng business được ghi mà không có audit; mục tiêu kiểm toán bị phá.

Nếu audit là best-effort, vẫn phải có thiết kế rõ cách nhận biết/log lỗi và không phụ thuộc một exception handler trong cùng transaction để bảo đảm event đã tồn tại bên ngoài.

**Chính sách nên nói rõ “audit failure có chặn business write không?”** và test khi tablespace đầy, quyền bị thu hồi, constraint audit lỗi hoặc hệ thống log pipeline mất kết nối.

## 27. Phân quyền bảng chứa PII và bảng audit

Lý tưởng là:

- App role chỉ có quyền cột/hàng phục vụ chức năng.
- App role **không sở hữu** customer/audit table.
- App role không có direct INSERT/UPDATE/DELETE audit.
- Audit function có owner độc lập và quyền tối thiểu.
- Auditor role chỉ đọc metadata audit cần thiết.
- Role DBA/superuser được giám sát riêng.
- Log exporter có quyền đọc file log theo chính sách, không nhất thiết được SELECT mọi PII.

### Một mô hình role minh họa

Các câu sau tạo role **cấp cluster**. Chỉ chạy trong môi trường lab/quản trị phù hợp và không dùng tên trùng role production.

~~~sql
-- Chỉ chạy bằng role có quyền tạo role.
CREATE ROLE sec391_writer NOLOGIN;
CREATE ROLE sec391_auditor NOLOGIN;

GRANT USAGE ON SCHEMA sec_audit_lab
TO sec391_writer, sec391_auditor;

GRANT SELECT (customer_id, display_name, status)
ON TABLE sec_audit_lab.customers
TO sec391_writer;

GRANT INSERT (customer_id, display_name, email, phone, status),
      UPDATE (display_name, status)
ON TABLE sec_audit_lab.customers
TO sec391_writer;

GRANT SELECT
ON TABLE sec_audit_lab.change_audit
TO sec391_auditor;
~~~

Ví dụ writer này không có direct quyền đọc email/phone qua table SELECT grant. Nó còn cần membership từ một login role được quản trị riêng; lab không tạo mật khẩu để tránh secret trong script.

### Audit function có chạy khi writer không có audit INSERT?

Với SECURITY DEFINER được cấu hình đúng, trigger function có thể ghi audit bằng quyền function owner. **Không cấp writer quyền audit trực tiếp chỉ để khắc phục permission denied** mà chưa xác định đúng owner, trigger function và quyền.

### Kiểm tra quyền

~~~sql
SELECT
    has_table_privilege(
        'sec391_writer',
        'sec_audit_lab.change_audit',
        'INSERT'
    ) AS writer_can_insert_audit,
    has_table_privilege(
        'sec391_auditor',
        'sec_audit_lab.change_audit',
        'SELECT'
    ) AS auditor_can_read_audit;
~~~

Với grants lab và không có đường đặc quyền khác, dự kiến writer_can_insert_audit=false, auditor_can_read_audit=true. Nếu role còn membership, PUBLIC grant hoặc ownership khác, kết quả có thể khác.

## 28. Audit function SECURITY DEFINER có rủi ro gì?

`SECURITY DEFINER` chạy với đặc quyền owner function, nên có thể trở thành đường leo thang nếu viết sai.

Một số yêu cầu:

1. Owner function phải là một role tin cậy, không phải app writer được phép ALTER FUNCTION.
2. Cố định `search_path` an toàn; tránh schema writable bởi untrusted users.
3. Schema-qualify các bảng/function quan trọng.
4. Không xây dynamic SQL từ field do người dùng nhập nếu không quote/validate đúng.
5. Hạn chế quyền `EXECUTE` và quản trị trigger.
6. Không coi `current_user` trong function là login user.
7. Kiểm thử dưới application role thực tế, không chỉ superuser.

### Tại sao session_user vẫn chưa đủ?

Nếu 10.000 người dùng web dùng chung DB login `shop_api`, `session_user` chỉ là `shop_api` cho tất cả request. Actor nghiệp vụ phải được xác thực ở ứng dụng và liên kết bằng một giao thức đáng tin.

Nếu cần chứng minh danh tính người thao tác cho yêu cầu tuân thủ cao, có thể cần audit service ngoài DB hoặc một cơ chế ký có thể kiểm chứng thay vì tin tuyệt đối custom session settings.

## 29. View che dữ liệu: chỉ cấp quyền vào view

Một view cho báo cáo có thể hiển thị email đã che:

~~~sql
CREATE VIEW sec_audit_lab.customer_public AS
SELECT
    customer_id,
    display_name,
    CASE
        WHEN position('@' IN email) > 0 THEN
            left(email, 1)
            || '***'
            || substring(email FROM position('@' IN email))
        ELSE '***'
    END AS masked_email,
    status
FROM sec_audit_lab.customers;
~~~

Ví dụ:

~~~sql
SELECT customer_id, masked_email
FROM sec_audit_lab.customer_public
ORDER BY customer_id;
~~~

Kết quả ý nghĩa:

~~~text
101 | l***@example.test
102 | m***@example.test
103 | h***@example.test
~~~

### Masking không đủ nếu có direct base-table SELECT

Nếu người dùng vừa có `SELECT` trên view, vừa có `SELECT(email)` trên bảng gốc, họ có thể bypass mask bằng cách đọc base table.

Do đó:

- Chỉ cấp quyền SELECT view cho role báo cáo cần thiết.
- Không cấp SELECT(email) trên base table cho role đó.
- Xem xét view ownership và RLS interaction.
- Với PostgreSQL 15+, view có các tùy chọn `security_invoker`/`security_barrier` phục vụ mục tiêu khác nhau; phải hiểu semantics khi kết hợp RLS và quyền bảng nền.

**Một view che email không tự là ẩn danh hoàn toàn**. Domain email có thể nhạy cảm; ID và display_name vẫn có thể nhận diện người.

## 30. RLS không thay data masking

**Row-level security (RLS)** trả lời: role có thể thấy **những hàng nào**?

**Column privileges/view masking** trả lời: role có thể thấy **những cột hoặc dạng biểu diễn nào**?

Ví dụ khái niệm:

~~~sql
-- Chỉ minh họa; cần bảng có tenant_id và trust model phù hợp.
ALTER TABLE some_schema.customer_records
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_read
ON some_schema.customer_records
FOR SELECT
USING (
    tenant_id = current_setting('app.tenant_id')::bigint
);
~~~

Không chạy nguyên ví dụ khi chưa có bảng/schema. `current_setting('app.tenant_id')` nếu do client không tin cậy tự đặt thì **không phải nguồn định danh tenant đáng tin**.

RLS còn có trường hợp owner/superuser/`BYPASSRLS` được phép bypass theo quy tắc. Audit privilege phải tính đến các đường này.

Nếu user có quyền đọc 1000 hàng theo RLS nhưng chỉ nên thấy email đã che, **RLS không tự che email**. Hai cơ chế giải quyết hai chiều khác nhau.

## 31. Dữ liệu nhạy cảm có thể xuất hiện ở những nơi nào?

Không chỉ bảng chính:

- Table và index.
- WAL, physical replication/standby.
- Backup/snapshot/base backup và PITR.
- Logical replication/change streams.
- Temporary files/spill khi sort/hash.
- Server logs, pgAudit logs, app logs.
- Metrics/traces/error tracking.
- `pg_stat_activity.query` và một số thống kê query text.
- SQL dump và xuất CSV.
- Test fixtures, staging clone, notebook, BI exports.
- Client-side logs, browser network traces.
- `psql` command history, shell history, CI output.
- Database error DETAIL/CONTEXT.
- Các audit tables chứa OLD/NEW.

### Hệ quả

“Xóa email ở bảng customers” **không có nghĩa mọi bản sao trong backup, log và audit biến mất ngay lập tức**. Cần retention/deletion strategy cho từng nơi và đánh giá yêu cầu pháp lý.

## 32. Data classification và tối thiểu hóa

Một ma trận phân loại minh họa:

| Loại | Ví dụ | Cách xử lý gợi ý |
| --- | --- | --- |
| Công khai | Mã sản phẩm public | Logging phù hợp chính sách |
| Nội bộ | ID tài liệu không chứa PII | Role-limited logs |
| PII | Email, số điện thoại, địa chỉ | Minimize, mask, retention ngắn hợp lý |
| Rất nhạy cảm | Số định danh, tài chính, y tế | ACL nghiêm, encryption và audit access |
| Bí mật xác thực | Password, refresh token, API key, private key | Không ghi log; secret manager và rotate |

Phân loại là đầu vào cho:

- Quyền truy cập table/view/log.
- Dữ liệu được phép xuất audit.
- Thời gian lưu.
- Mức độ masking.
- Chính sách export sang bên thứ ba.
- Quy trình xóa theo yêu cầu hợp lệ.

**Đừng lấy “chúng tôi cần audit” làm lý do mặc định thu thập toàn bộ PII.** Chỉ lưu những trường đáp ứng một mục tiêu đã được xác định.

## 33. Mã hóa ở các lớp khác nhau

| Cơ chế | Bảo vệ chính | Không tự bảo vệ |
| --- | --- | --- |
| TLS client↔PostgreSQL | Dữ liệu trên đường truyền | Người có quyền đọc DB/log |
| Disk/volume encryption | Ổ đĩa bị lấy cắp/snapshot offline tùy threat model | Query hợp lệ, superuser trong DB |
| Encrypted backups | Backup copy | Server đang chạy và app |
| Field-level encryption | Giá trị ở cột theo cơ chế/khóa riêng | Metadata, query result khi đã giải mã |
| App-side encryption | Plaintext có thể không vào DB theo thiết kế | Secrets/keys ở app, searchable metadata |
| HMAC/tokenization | Tra cứu/đối chiếu với giá trị giả danh | Khả năng liên kết nếu key lộ hoặc thiết kế sai |

### pgcrypto có thể hữu ích nhưng không giải quyết quản lý khóa

PostgreSQL có extension `pgcrypto` với các hàm mã hóa/hashing. Tuy nhiên nếu ứng dụng gửi cả plaintext và khóa giải mã tới PostgreSQL, hai thứ vẫn phải được bảo vệ trên đường truyền, trong quá trình xử lý và trong hệ thống logs.

**Mã hóa cột không thay mô hình quyền, audit và key rotation.** Cần xác định ai giữ khóa, giải mã ở đâu và cách xử lý khi khóa bị lộ.

## 34. Hash PII không đồng nghĩa đã ẩn danh

Một anti-pattern phổ biến:

~~~text
SHA256(email) rồi lưu trong audit => dữ liệu hoàn toàn ẩn danh
~~~

Không chính xác. Email thường có miền khả đoán; hash không secret có thể bị brute force/dictionary attack. Nếu một giá trị hash ổn định được dùng ở nhiều hệ thống, nó còn giúp liên kết hồ sơ.

### Khi cần đối chiếu mà không lưu plaintext

Có thể xem xét:

- HMAC với secret key được quản lý ở nơi phù hợp.
- Tokenization qua dịch vụ được kiểm soát.
- Salt/pepper và cơ chế rotation theo mô hình dữ liệu.
- Chỉ lưu một chỉ số boolean như `contact_changed` nếu nghiệp vụ không cần đối chiếu giá trị.

HMAC vẫn có thể là **pseudonymized data**, không phải dữ liệu vô danh tuyệt đối. Ai có khóa hoặc dữ liệu đối chiếu có thể tái liên kết.

### Password đặc biệt khác PII lookup

Mật khẩu phải dùng password hashing/KDF chuyên dụng có cơ chế salt/work factor phù hợp, không dùng SHA-256 thô hay encryption có thể giải ngược. Không log password, kể cả bản hash nếu không cần.

## 35. SQL injection và log có mối liên quan

Dùng JDBC/prepared statements giúp phân tách SQL code và input:

~~~java
String sql = """
    SELECT customer_id, status
    FROM sec_audit_lab.customers
    WHERE customer_id = ?
    """;

try (PreparedStatement statement =
        connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

### Tránh anti-pattern chứa secret

~~~java
// KHÔNG NÊN:
logger.info("Lookup email=" + userEmail + ", token=" + token);

// KHÔNG NÊN:
String sql = "SELECT * FROM customers WHERE email='" + userEmail + "'";
~~~

Prepared statements phòng SQL injection và giảm raw literals trong SQL text. Nhưng driver/logging stack vẫn có thể ghi parameters nếu bật verbose tracing; phải quản trị cả cấu hình đó.

**Không dùng một câu “đã parameterize nên dữ liệu nhạy cảm không bao giờ bị log”**.

## 36. SQL query comments và application_name không phải nơi lưu secret

Một số framework chèn trace identifiers vào SQL comments:

~~~sql
SELECT 1 /* request_id=req-lab-391 */;
~~~

Nếu comments chứa email, token hoặc dữ liệu cá nhân, statement logging có thể ghi nguyên nội dung đó.

Tương tự:

~~~sql
SET application_name = 'shop-api';
~~~

`application_name` có thể xuất hiện trong server logs, `pg_stat_activity` và monitoring. Chỉ đặt tên service hoặc định danh ngắn đã được policy chấp thuận, không nhúng JWT, email hay session secrets vào application_name.

### Request IDs cũng cần kiểm soát

Một request ID ngẫu nhiên, không chứa PII, có TTL và phạm vi phù hợp thường hữu ích. Nhưng nếu nó cho phép tra cứu hồ sơ nhạy cảm trực tiếp ở một hệ thống khác, phải phân quyền nơi có thể sử dụng nó.

## 37. Ghi lại SELECT ở tầng ứng dụng khi cần biết resource ID

Một API như:

~~~text
GET /customers/101
~~~

có thể tạo audit event:

~~~json
{
  "action": "customer.read",
  "actor_id": "user-42",
  "resource_id": "101",
  "result": "allowed",
  "request_id": "req-lab-393"
}
~~~

### Tránh tự tạo false evidence

- Event `allowed` chỉ nên được ghi sau khi authorization đúng theo contract.
- Nếu query lỗi, status phải phản ánh lỗi; không ghi “read success” vô điều kiện.
- Không nên ghi full response payload.
- Một API có thể đọc nhiều customer records; phải chọn độ chi tiết phù hợp mục tiêu và chi phí.
- Cached responses có thể không gọi DB; server SQL audit đơn độc không theo dõi được lần đọc từ cache.

Muốn kiểm toán người dùng đã được phép truy xuất dữ liệu nào, **ứng dụng là nguồn quan trọng** vì nó hiểu identity, cache, authorization và business resource.

## 38. Audit DDL và quyền thay đổi chính sách

Một vụ lộ dữ liệu có thể bắt đầu từ:

~~~sql
GRANT SELECT ON TABLE sensitive_customers TO PUBLIC;
~~~

hoặc:

~~~sql
ALTER TABLE sensitive_customers DISABLE ROW LEVEL SECURITY;
~~~

Do đó audit không chỉ là dữ liệu được đọc/sửa, mà còn cần theo dõi **các thay đổi quyền và schema**.

Các nguồn có thể gồm:

- Server `log_statement='ddl'` (không phải mọi GRANT/role action đều là DDL theo cách phân loại giống nhau).
- pgAudit lớp `DDL` và `ROLE` theo cấu hình.
- Change/migration records.
- Event triggers với các event DDL được PostgreSQL hỗ trợ.
- Catalog snapshots/role and grants review.
- Logs của hệ thống CI/CD và cloud control plane.

### Event trigger khác DML trigger

PostgreSQL có `CREATE EVENT TRIGGER` cho một số nhóm DDL events, không phải per-row SELECT/UPDATE audit.

Nó có giới hạn event types, permissions và phiên bản. Không phải mọi thay đổi cấu hình hay mọi SQL statement đều được bao phủ bằng một event trigger.

**Không dùng một DML trigger gắn lên customers rồi tưởng nó ghi được thay đổi GRANT, ALTER ROLE hoặc CREATE EXTENSION.**

## 39. Audit các thao tác admin đặc quyền cao

Role DBA, superuser và chủ object có khả năng can thiệp ACL, RLS, trigger, extensions hoặc server logging theo quyền.

Do đó một audit table nằm **trong cùng cluster** không tự là bằng chứng bất biến trước một đối thủ có superuser hoặc quyền OS.

Các biện pháp có thể cần:

1. Gửi server logs tới log service ngoài DB/host với quyền ghi/đọc tách biệt.
2. Hạn chế quyền xóa, sửa, disable collector.
3. Dùng immutable/WORM storage hoặc signature phù hợp nếu compliance yêu cầu.
4. Bảo toàn clock synchronization và metadata nguồn.
5. Giám sát thay đổi log configuration, role grants, RLS, SECURITY DEFINER functions.
6. Quản trị privileged access theo quy trình phê duyệt và ghi nhật ký.
7. Có quy trình incident response khi nghi ngờ mất tính toàn vẹn của log.

### Hash chain trong bảng có đủ không?

Một hash chain lưu ngay trong DB có thể phát hiện một số sửa đổi, nhưng người có toàn quyền đổi cả dữ liệu và tính lại chuỗi hash có thể làm mất giá trị bảo vệ.

Muốn tamper-evidence mạnh hơn, cần **neo bằng chứng ra khỏi miền quyền của hệ thống bị kiểm toán** hoặc dùng cơ chế ký/immutable storage độc lập.

## 40. Retention là một quyết định bảo mật

Giữ log mãi mãi có những rủi ro:

- Tăng phạm vi dữ liệu nhạy cảm nếu log bị lộ.
- Tăng chi phí storage, backup và phân tích.
- Có thể không phù hợp nghĩa vụ xóa/hạn chế lưu dữ liệu.
- Dễ mất hiệu quả search/audit khi log quá lớn.
- Tạo nhiều bản sao ở SIEM, object storage, staging exports.

### Một retention policy nên xác định

| Nội dung | Câu hỏi |
| --- | --- |
| Loại log | Connection, SQL audit, row audit hay app audit? |
| Mục đích | Điều tra sự cố, vận hành, tuân thủ? |
| Thời hạn | Bao lâu theo yêu cầu hợp lệ của tổ chức/pháp luật? |
| Truy cập | Ai được xem/export/xóa? |
| Nơi lưu | DB, local files, SIEM, object storage? |
| Xóa | Cơ chế xóa, backup lifecycle, legal hold? |
| Encryption | At rest, transit, key management? |
| Review | Ai định kỳ kiểm tra thay đổi policy? |

**Không tự đặt một con số retention “chuẩn chung” như 30 ngày hoặc 7 năm cho mọi ngành.** Cần yêu cầu pháp lý/khách hàng/nghiệp vụ cụ thể.

## 41. Xóa dữ liệu cá nhân và audit trail

Giả sử một người dùng yêu cầu xóa dữ liệu. Hệ thống có thể có:

- Customer row.
- Audit row chứa customer_id.
- Server log ghi email trong câu SQL trước đây.
- Backup snapshot.
- BI export.
- Object storage chứa CSV.
- Cache/search index.
- External system nhận notification.

Xóa customer row không tự xóa những bản sao kia.

### Một hướng thiết kế

1. Lập data inventory và data flow.
2. Xác định bản sao/retention cho từng hệ.
3. Phân biệt dữ liệu phải xóa và dữ liệu phải giữ hợp pháp cho audit.
4. Nếu cần giữ audit, giảm khả năng tái nhận diện (minimization/pseudonymization) theo chính sách.
5. Đặt hạn lưu/cleanup cho logs và backups.
6. Kiểm tra downstream exports, search index, monitoring.
7. Có bằng chứng quy trình hoàn tất, nhưng không tự ghi lại nhiều PII hơn trong log xóa.

Yêu cầu cụ thể phụ thuộc pháp luật và contract. Đây là hướng kỹ thuật, không phải tư vấn pháp lý.

## 42. Kiểm tra log pipeline có mất hoặc trùng sự kiện không

Một hệ thống audit tập trung có thể gặp:

- Network outage.
- Log rotation chưa ship xong.
- Collector restart.
- Trùng event khi retry.
- Clock skew giữa app và database.
- Producer queue đầy.
- Parse lỗi định dạng CSV/JSON.
- Delivery “at least once” từ agent.

Cần xem:

- Có sequence/offset/metadata nguồn để phát hiện gaps không?
- Event có timestamp với timezone chuẩn không?
- Event ID/request ID có thể giúp de-duplicate không?
- Mất log có cảnh báo/gián đoạn các nghiệp vụ quan trọng không?
- Raw log có được lưu bản gốc hợp pháp để kiểm tra parser không?
- Ai được quyền xóa/đổi pipeline?

**Một dashboard hiện “không có cảnh báo” không phải bằng chứng rằng không có sự kiện bị bỏ sót** nếu ingestion thiếu kiểm soát.

## 43. Log masking phải thực hiện ở đúng vị trí

Nếu chỉ mask tại dashboard nhưng raw server log vẫn chứa PII, người có quyền đọc file log có thể thấy dữ liệu.

Các lớp có thể dùng:

1. **Source minimization:** tránh đưa PII vào SQL literal/query comments và app log.
2. **Driver/application redaction:** không in body, tokens, credentials.
3. **DB log configuration:** hạn chế statement/parameter logging phù hợp.
4. **Collector filtering:** loại hoặc token hóa field khi cần.
5. **Storage ACL/encryption:** bảo vệ cả raw log và đã xử lý.
6. **Dashboard/view masking:** chỉ hiển thị đúng role.
7. **Retention/deletion:** hủy dữ liệu không cần giữ.

Không chỉ dựa một regex ở collector để xóa tất cả dạng PII. Dữ liệu có thể mã hóa, escape, nhiều ngôn ngữ, được split qua nhiều field, hoặc nằm trong error context; regex chỉ là một lớp giảm rủi ro.

## 44. Monitoring nào nên cảnh báo?

Những tín hiệu có thể hữu ích:

- Tăng authentication failures bất thường.
- Login từ nguồn/khu vực chưa được chấp thuận theo policy.
- Đột biến SELECT trên bảng nhạy cảm.
- Batch export/COPY dữ liệu lớn.
- GRANT/REVOKE, ALTER ROLE, thay đổi RLS/privileges.
- Tắt logging collector, pgAudit, audit triggers.
- Audit insertion failure và transaction rollback tăng.
- Log shipping lag/drop.
- Superuser access ngoài maintenance window.
- Query chứa token/key literal không mong đợi.
- Tăng bất thường lượng data returned từ API nhạy cảm.

### Giảm false positives

- Tách migration/backfill hợp lệ khỏi hành vi bất thường.
- Có whitelist theo change window được phê duyệt.
- Đo baseline theo service/role.
- Giữ audit của chính việc thay đổi rule/whitelist.
- Không tự động chặn truy vấn production chỉ dựa vào một metric mơ hồ nếu chưa có policy.

## 45. Runbook điều tra một sự kiện

Giả sử phát hiện một nhân viên truy cập hồ sơ nhạy cảm sai thẩm quyền.

Một quy trình:

1. Ghi nhận **khoảng thời gian**, hệ thống, tenant/resource cần điều tra.
2. Bảo vệ bằng chứng server/app/pgAudit logs và audit rows.
3. Kiểm tra thời gian đồng bộ/timezone, cấu hình log lúc sự kiện xảy ra.
4. Tương quan `request_id`, `session_user`, `current_user`, DB pid/session ID, client address.
5. Kiểm tra permissions/RLS và role grants tại thời điểm đó, không chỉ hiện tại.
6. Xác định SELECT đã chạy hay API đã trả dữ liệu, có cache/export không.
7. Kiểm tra transaction commit/rollback đối với DML.
8. Hạn chế truy cập, rotate credentials nếu có dấu hiệu compromise.
9. Lưu bằng chứng theo chain-of-custody quy định.
10. Viết kết luận phân biệt **quan sát được**, **suy luận**, **chưa có đủ bằng chứng**.

**Không kết luận “user đã nhìn thấy toàn bộ customer records” chỉ vì thấy một statement SELECT *** trong log.** Query có thể lỗi, bị RLS lọc, trả ít hàng, hoặc không được client hiển thị.

## 46. Câu SQL kiểm tra cấu hình logging thực tế

Các truy vấn đọc-only:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'log_destination',
    'logging_collector',
    'log_connections',
    'log_disconnections',
    'log_statement',
    'log_min_duration_statement',
    'log_min_error_statement',
    'log_line_prefix',
    'log_parameter_max_length',
    'log_parameter_max_length_on_error'
)
ORDER BY name;
~~~

### Ý nghĩa

- `setting`: giá trị đang hiệu lực theo ngữ cảnh query.
- `unit`: đơn vị nếu có.
- `context`: phạm vi thay đổi tham số (postmaster, sighup, user, superuser, …).
- `source`: nguồn cấu hình được dùng.

Một số tham số có thể **không tồn tại ở PostgreSQL major version cũ**; query `WHERE name IN (...)` không lỗi nếu tên không có, mà chỉ không trả hàng tương ứng.

### Kiểm tra pgAudit

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname IN ('pgaudit', 'pg_stat_statements');
~~~

Kết quả không có pgAudit trong database hiện tại không tự chứng minh hệ điều hành/server không có package extension, và có package cũng không đồng nghĩa session audit đã được cấu hình. Cần kiểm tra preload, settings và sự kiện thử nghiệm phù hợp.

## 47. Đừng dùng pg_stat_activity để lưu lịch sử lâu dài

Một câu đọc:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start
FROM pg_stat_activity;
~~~

chỉ thể hiện trạng thái hiện tại, không phải lịch sử sau restart hay một bảng sự kiện tự bền vững.

Nếu muốn có lịch sử:

- Server logs/pgAudit được thu theo thời gian.
- Application audit events.
- Row audit được thiết kế cho DML.
- Log shipping và retention.

Không liên tục poll `pg_stat_activity.query` rồi tự lưu tất cả text vào một bảng mà không xét nguy cơ nhân bản secrets và overhead.

## 48. Kiểm tra catalog của audit trigger

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid) AS trigger_definition
FROM pg_trigger
WHERE tgrelid = 'sec_audit_lab.customers'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Điều này cho biết trigger nào đang gắn lên bảng và trạng thái cơ bản.

### Một điểm bảo mật

Người có quyền thay đổi schema/trigger có thể can thiệp cơ chế audit. Nên quản lý DDL qua migration, tách quyền owner/deployer và audit thay đổi privileged operations.

Không đọc `tgenabled` rồi kết luận mọi sự kiện trong quá khứ đều đã được audit: trigger có thể đã tắt, bị thay thế hoặc replication apply có semantics khác trong khoảng thời gian đó.

## 49. Chi phí của row audit và server logs

Bảng customers có một row update, trigger ghi thêm audit row:

- Thêm INSERT vào audit table.
- Tăng WAL/dirty pages.
- Tăng index maintenance và storage.
- Tăng autovacuum/retention workload.
- Có thể làm statement thất bại khi audit table không ghi được.

Server log `all`/pgAudit READ trên workload có hàng chục nghìn queries/giây có thể tạo log volume lớn, ảnh hưởng disk/network/collector và chi phí lưu trữ.

### Đo bằng dữ liệu thực tế

Một lab kiểm tra tác động ghi:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE sec_audit_lab.customers
SET
    status = CASE
        WHEN status = 'active' THEN 'blocked'
        ELSE 'active'
    END,
    updated_at = clock_timestamp()
WHERE customer_id = 101;

ROLLBACK;
~~~

**`EXPLAIN ANALYZE UPDATE` thực thi UPDATE thật**. Chỉ chạy trong transaction rollback trên lab; `WAL` option của EXPLAIN yêu cầu version hỗ trợ (PostgreSQL 13+).

Điều kiện load production, số lượng trigger/index và log pipeline sẽ khác lab nhỏ. Không dự đoán sẵn một con số latency.

## 50. Phân biệt lỗi ứng dụng và bằng chứng audit

Một API trả HTTP 500 có thể do:

- Lỗi kết nối trước khi query.
- Permission denied.
- Constraint violation.
- Timeout/connection termination.
- Transaction rollback do ứng dụng chủ động.
- Lỗi serializable/deadlock cần retry.
- External API failure sau khi DB commit.

Một DB audit row không đủ giải thích mọi trường hợp. Muốn điều tra, cần ghép:

- App request result.
- Transaction outcome.
- DB server errors/statements.
- Audit DML row nếu có.
- External service logs và outbox states.
- Danh tính/permissions tại thời điểm.

**Không báo “DB đã ghi dữ liệu thành công” chỉ vì trigger đã thực thi trước khi transaction bị rollback.**

## 51. Các sai lầm thường gặp

1. **Dùng log_statement=all vô hạn** trên hệ thống nhiều PII mà không kiểm soát volume và quyền đọc log.
2. **Nghĩ prepared statements tuyệt đối che parameters**, bỏ qua driver/server/error logging.
3. **Dùng DML trigger để audit SELECT**, trong khi PostgreSQL không có SELECT row trigger thông thường.
4. **Ghi `to_jsonb(OLD)` và `to_jsonb(NEW)` của bảng chứa PII** vào audit giữ lâu.
5. **Coi audit INSERT cùng transaction là log bền của một lần ghi thất bại**.
6. **Nghĩ audit trigger tự commit**, trong khi outer rollback hủy audit row.
7. **Coi audit table là tamper-proof đối với superuser**.
8. **Coi session_user/current_user là danh tính người dùng web** khi dùng connection pool chung.
9. **Tin custom `app.actor_id` từ client không tin cậy** như một bằng chứng authorization.
10. **Cho app role quyền sửa/xóa audit table**.
11. **Dùng SECURITY DEFINER nhưng search_path không an toàn**.
12. **Mở PUBLIC EXECUTE của function đặc quyền mà không review**.
13. **Bật pgAudit nhưng không kiểm tra package/preload/restart và log thực tế**.
14. **Ghi đè shared_preload_libraries** làm mất library khác.
15. **Tin pg_stat_activity là historical audit**, dù chỉ là snapshot activity.
16. **Dùng pg_stat_statements như log từng request**, dù nó thiên về aggregated workload stats.
17. **Nhầm statement đã được log với statement đã commit**.
18. **Nghĩ log truy vấn SELECT cho biết người dùng đã đọc chính xác mọi hàng**.
19. **Cho dashboard quyền xem query text/raw logs quá rộng**.
20. **Mask chỉ ở giao diện nhưng raw log vẫn chứa secret**.
21. **Bảo rằng SHA-256(email) là ẩn danh tuyệt đối**.
22. **Mã hóa ổ đĩa rồi cho rằng SELECT và query logs không thể lộ dữ liệu**.
23. **Bỏ qua dữ liệu trong WAL, backup, replica, exports** khi xử lý yêu cầu xóa.
24. **Không có retention/rotation**, làm log đầy disk hoặc giữ PII quá lâu.
25. **Không kiểm tra thất bại log shipping/collector**, gây gaps mà không cảnh báo.
26. **Không ghi request ID hoặc đồng bộ timestamp**, khó tương quan điều tra.
27. **Tin application_name/SQL comments là identity bảo mật**, dù client có thể thay đổi.
28. **Không theo dõi GRANT, ALTER ROLE, RLS hoặc việc tắt audit**.
29. **Nuốt mọi lỗi trong audit trigger**, làm nghiệp vụ có thể ghi không có lịch sử bắt buộc.
30. **Chạy EXPLAIN ANALYZE UPDATE trên production như query đọc-only**, gây DML thật.
31. **Test chỉ bằng superuser**, bỏ qua quyền thực tế của application/auditor.
32. **Không phân biệt compliance requirement và tuning/monitoring**.
33. **Gắn audit một lần sau khi có dữ liệu rồi kỳ vọng tự có lịch sử quá khứ**.
34. **Không tính chi phí GIN/index/WAL của audit tables** khi lưu lớn.
35. **Không chuẩn hóa privacy classification** nên từng nhóm log PII tùy ý.

## 52. Bài tập có đáp án

Dùng schema `sec_audit_lab` nếu bài có SQL. Những bài cố ý gây lỗi hoặc thay đổi dữ liệu cần thực hiện trong database lab, sử dụng transaction rollback khi phù hợp.

### Bài 1. Kết nối và dữ liệu thay đổi có cùng log không?

**Đáp án:** Không tự động. Connection log nhận biết session; row audit cần cơ chế riêng cho thay đổi dữ liệu.

### Bài 2. log_statement='all' có chứng minh COMMIT thành công không?

**Đáp án:** Không. Statement có thể lỗi, tác động 0 hàng hoặc bị rollback sau đó.

### Bài 3. pgAudit có phải extension luôn cài sẵn?

**Đáp án:** Không. Cần package/availability tương thích, preload/cấu hình và tạo extension khi phù hợp.

### Bài 4. DML trigger có bắt SELECT không?

**Đáp án:** Không. PostgreSQL không có row-level SELECT trigger thông thường cho table; cần pgAudit/server logs/app access logs nếu muốn quan sát đọc.

### Bài 5. Vì sao không lưu toàn bộ OLD/NEW?

**Đáp án:** Có thể nhân bản email, điện thoại, token và các cột nhạy cảm vào audit, tăng nguy cơ rò rỉ và chi phí lưu/xóa.

### Bài 6. Log của app nên có gì?

**Đáp án:** Event type, actor ID đáng tin, request ID, resource ID cần thiết, thời điểm, kết quả, không chứa secret hoặc payload thừa.

### Bài 7. session_user là người dùng web?

**Đáp án:** Không tự động. Với connection pool, hàng nghìn người có thể dùng cùng một database login.

### Bài 8. current_user trong SECURITY DEFINER là ai?

**Đáp án:** Thường là function owner trong khi thực thi function, không phải người dùng đã gọi request.

### Bài 9. app.actor_id có chống giả mạo không?

**Đáp án:** Không nếu client có thể tự SET custom GUC. Cần app/gateway tin cậy và cơ chế identity phù hợp.

### Bài 10. Thử rollback audit UPDATE

~~~sql
BEGIN;

UPDATE sec_audit_lab.customers
SET status = 'blocked'
WHERE customer_id = 101;

SELECT COUNT(*) AS audit_rows_in_transaction
FROM sec_audit_lab.change_audit
WHERE customer_id = 101;

ROLLBACK;
~~~

**Đáp án:** Dòng audit phát sinh trong transaction sẽ bị rollback cùng UPDATE.

### Bài 11. Vì sao audit_id có thể có gap?

**Đáp án:** Sequence/identity có thể tăng dù transaction rollback. Gap không tự chứng minh audit data bị xóa.

### Bài 12. Tạo một view che email có đủ bảo mật không?

**Đáp án:** Chưa. Nếu role còn SELECT base table, họ vẫn đọc email gốc; cần hạn chế quyền và xét RLS/view semantics.

### Bài 13. RLS bảo vệ cột email không?

**Đáp án:** RLS chủ yếu giới hạn hàng; dùng column privilege/view để giới hạn cột/dạng hiển thị.

### Bài 14. Hash email bằng SHA256 có phải anonymous data?

**Đáp án:** Không chắc. Email có thể đoán và hash cố định hỗ trợ liên kết; cần threat model, có thể HMAC/tokenization.

### Bài 15. SSL/TLS bảo vệ gì?

**Đáp án:** Kênh truyền; không tự ngăn authorized query/logging đọc plaintext sau khi DB xử lý.

### Bài 16. Disk encryption có ngăn DBA SELECT không?

**Đáp án:** Không. Nó chủ yếu bảo vệ dữ liệu lưu trữ offline theo threat model, không thay ACL/RLS.

### Bài 17. pg_stat_activity có thay historical log không?

**Đáp án:** Không. Nó phản ánh hoạt động backend hiện tại/gần nhất, không lưu mọi request bền vững.

### Bài 18. pg_stat_statements có theo dõi mỗi user request không?

**Đáp án:** Không theo cách forensic audit; đó là thống kê workload tổng hợp.

### Bài 19. log_line_prefix dùng để làm gì?

**Đáp án:** Thêm timestamp, PID, role, database, app/client/session identifiers để tương quan log.

### Bài 20. Có nên đặt access token trong application_name không?

**Đáp án:** Không. application_name có thể xuất hiện trong log/monitoring và do client tùy chỉnh.

### Bài 21. log_parameter_max_length=0 có đảm bảo hết PII trong mọi log?

**Đáp án:** Không. Query literal, app logs, error details hoặc công cụ khác vẫn có thể ghi dữ liệu; còn phụ thuộc PostgreSQL version.

### Bài 22. Out-of-band audit có lợi gì?

**Đáp án:** Giúp lưu bằng chứng ngoài miền quyền/transaction của database chính, quan trọng nếu cần ghi lần thử lỗi hoặc chống sửa đổi bởi admin DB.

### Bài 23. Khi audit table INSERT lỗi, business UPDATE nên thế nào?

**Đáp án:** Phụ thuộc yêu cầu. Nếu audit bắt buộc, lỗi chưa xử lý thường phải làm business statement thất bại; không âm thầm `WHEN OTHERS THEN NULL`.

### Bài 24. Vì sao log_statement=all tốn kém?

**Đáp án:** Tạo nhiều log, IO/network/storage/parse overhead và rủi ro PII cao; phải đo và lựa chọn scope.

### Bài 25. Sao không log request body đầy đủ để điều tra?

**Đáp án:** Dễ ghi token, mật khẩu, dữ liệu nhạy cảm; nên chọn field allowlist và giảm volume.

### Bài 26. Một SQL SELECT trong log chứng minh user nhìn thấy 1000 hàng không?

**Đáp án:** Không. Query có thể bị RLS lọc, trả ít hàng, lỗi, bị cache hoặc client không hiển thị.

### Bài 27. Kiểm tra audit trigger đang bật bằng SQL nào?

~~~sql
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgrelid = 'sec_audit_lab.customers'::regclass
  AND NOT tgisinternal;
~~~

**Đáp án:** Xem metadata hiện tại; không tự chứng minh mọi sự kiện lịch sử đã được ghi.

### Bài 28. Cách xem logging context?

~~~sql
SELECT name, setting, context, source
FROM pg_settings
WHERE name IN ('logging_collector', 'log_statement');
~~~

**Đáp án:** `context` cho biết kiểu thay đổi cần reload/restart/session; phải đối chiếu docs version.

### Bài 29. Cần giữ log bao lâu?

**Đáp án:** Theo mục đích, nghĩa vụ pháp lý/hợp đồng, phân loại dữ liệu và retention policy được duyệt; không có một giá trị đúng cho mọi hệ thống.

### Bài 30. Nếu đã xóa customer row thì xong yêu cầu xóa dữ liệu chưa?

**Đáp án:** Chưa chắc. Cần xem audit, backups, WAL/replica, exports, search index, logs và nghĩa vụ giữ/xóa tương ứng.

### Bài 31. Vì sao role app không nên sở hữu audit table?

**Đáp án:** Owner có thể sửa/drop dữ liệu và schema; tách owner khỏi runtime giúp giảm tác động khi app credentials bị lộ.

### Bài 32. DDL event trigger có thay pgAudit READ không?

**Đáp án:** Không. Event trigger nhắm một số sự kiện DDL, không theo dõi mọi SELECT.

### Bài 33. Điều gì xảy ra nếu log collector bị ngắt?

**Đáp án:** Có thể lag, mất sự kiện hoặc đầy queue/disk tùy hệ thống; cần monitoring, backpressure/retention và runbook.

### Bài 34. Query error log có thể có gì nhạy cảm?

**Đáp án:** SQL literals, parameters theo cấu hình, DETAIL/CONTEXT, tên object và thông điệp chứa nội dung; phải hạn chế quyền xem.

### Bài 35. Vì sao cần audit thay đổi GRANT/RLS?

**Đáp án:** Một thay đổi quyền có thể mở đường đọc dữ liệu nhạy cảm mà không cần INSERT/UPDATE hàng nghiệp vụ.

### Bài 36. Cách kết luận sự cố chính xác?

**Đáp án:** Tương quan nhiều nguồn, xác minh commit/permission/RLS/cache, nêu rõ cái gì quan sát được và cái gì chưa chứng minh, không suy đoán quá mức.

## 53. Checklist thiết kế bảo mật và kiểm toán

- [ ] Có danh mục dữ liệu nhạy cảm/PII và mục đích thu thập log.
- [ ] Tách connection log, statement log, access audit, row audit và app trace.
- [ ] Xác định ai có quyền đọc, export, xóa log.
- [ ] Không log password, token, private key hoặc request body thừa.
- [ ] Dùng bind parameters nhưng không mặc định các params luôn được che.
- [ ] Review `log_statement`, `log_min_duration_statement`, `log_min_error_statement`.
- [ ] Xem version/`pg_settings.context` trước khi thay config/restart.
- [ ] Chọn log format, rotation và ingestion có kiểm soát.
- [ ] Giữ application_name ngắn, không nhạy cảm.
- [ ] Có request ID/trace ID và UTC/time sync.
- [ ] Đánh giá pgAudit package/preload/configuration theo workload.
- [ ] Không cho log READ/WRITE tràn ngập mà chưa benchmark IO/volume.
- [ ] Không dùng DML trigger để giả vờ audit SELECT.
- [ ] Với row audit, chọn trường allowlist; không `to_jsonb(OLD/NEW)` vô điều kiện.
- [ ] Biết audit DB rollback cùng transaction.
- [ ] Không dùng exception handler nuốt lỗi audit bắt buộc.
- [ ] Phân quyền writer và auditor tách biệt, hạn chế app runtime ownership.
- [ ] SECURITY DEFINER phải có owner và search_path an toàn.
- [ ] Không tin actor claim trong custom GUC nếu session có thể tự SET.
- [ ] Coi DB session_user khác human/business actor.
- [ ] Giới hạn quyền xem `pg_stat_activity.query` và query statistics.
- [ ] Dùng view/column privileges khi cần mask cột; RLS cho phân quyền hàng.
- [ ] Mã hóa kênh, storage/backup và quản lý khóa phù hợp threat model.
- [ ] Không xem hash PII thô là anonymous data mặc định.
- [ ] Kiểm kê dữ liệu ở WAL, backup, replica, export, cache và log pipeline.
- [ ] Có retention/delete/legal hold policy với owner chịu trách nhiệm.
- [ ] Theo dõi audit pipeline lag, gaps, duplicate và thay đổi config.
- [ ] Audit GRANT/ALTER ROLE/RLS/trigger changes và đặc quyền admin.
- [ ] Có runbook điều tra và bảo toàn bằng chứng.
- [ ] Kiểm thử dưới application/auditor roles, không chỉ superuser.
- [ ] Đo tác động audit ghi, IO, WAL, latency p95/p99.
- [ ] Kiểm thử committed DML, rollback, failed statement và SELECT access riêng.
- [ ] Không chạy DROP SCHEMA hoặc EXPLAIN ANALYZE DML trên production.

## 54. Tài liệu PostgreSQL chính thức

Dùng tài liệu **đúng major version của server** và tài liệu extension nhà cung cấp:

- [Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — `log_destination`, `logging_collector`, `log_statement`, `log_line_prefix`, parameter logging và rotation.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — monitoring và thống kê.
- [The pg_stat_activity View](https://www.postgresql.org/docs/current/monitoring-stats.html) — session metadata và quyền xem.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html) — xác thực kết nối.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles và quyền.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — quyền truy cập object.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS, policies và bypass.
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html) — `OLD`, `NEW`, `TG_OP`.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — DML trigger events và giới hạn.
- [Event Triggers](https://www.postgresql.org/docs/current/event-triggers.html) — audit/thao tác DDL.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — SECURITY DEFINER và security.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — search_path/privilege an toàn.
- [The pg_stat_statements Module](https://www.postgresql.org/docs/current/pgstatstatements.html) — thống kê query tổng hợp.
- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — TLS cho kết nối.
- [pgcrypto](https://www.postgresql.org/docs/current/pgcrypto.html) — encryption/hashing và các giới hạn.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup/PITR.
- [System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html) — trigger metadata.
- [System View pg_settings](https://www.postgresql.org/docs/current/view-pg-settings.html) — cấu hình và context.
- [pgAudit project documentation](https://github.com/pgaudit/pgaudit) — extension, version compatibility và configuration.

URL `/current/` trỏ tới tài liệu PostgreSQL hiện hành. Các option logging, JSONLOG, pgAudit, quyền monitoring, cấu hình và event trigger có khác biệt theo version; hãy đối chiếu môi trường triển khai thực tế.

## 55. Tổng kết

**Audit có giá trị khi ghi đúng sự kiện, đúng danh tính ở mức có thể tin, lưu đủ nhưng không thừa dữ liệu và bảo vệ được chính bằng chứng.**

Những nguyên tắc quan trọng nhất:

1. **Server logs, pgAudit, row audit và application audit là những lớp bổ sung nhau**, không có lớp nào mặc định thay hoàn toàn lớp còn lại.
2. **DML trigger ghi được INSERT/UPDATE/DELETE nhưng không bắt SELECT thông thường.** Muốn audit đọc, dùng nguồn phù hợp ở DB và ứng dụng.
3. **Audit trigger trong PostgreSQL chạy cùng transaction:** rollback nghiệp vụ cũng rollback audit rows liên quan. Muốn chứng minh lần thử thất bại phải có nguồn log ngoài transaction phù hợp.
4. **Không lưu nguyên `OLD`/`NEW` của bảng chứa PII** nếu chỉ cần biết trạng thái và loại thay đổi.
5. **Không bật statement/parameter logging tối đa một cách mù quáng**: chính log có thể trở thành nơi chứa bí mật.
6. **Prepared statements giúp an toàn SQL nhưng không tự ngăn mọi hệ thống log ghi tham số**.
7. **`session_user`, `current_user`, `application_name` và custom request claims cần hiểu đúng độ tin cậy**. Chúng không tự xác định người dùng web thật.
8. **RLS, column privileges, masking views và SECURITY DEFINER có vai trò riêng**, phải thiết kế kết hợp và test bằng role thực.
9. **Encryption, HMAC, retention và data inventory** là những phần của bảo vệ dữ liệu, không phải tùy chọn thêm sau khi đã triển khai log.
10. **Bằng chứng audit trong cùng DB không chống sửa đổi tuyệt đối trước admin đặc quyền cao**; nếu yêu cầu, cần thu thập/lưu trữ độc lập.
11. **Theo dõi log pipeline và quyền thay đổi chính sách** để không bị mất hoặc làm giả dấu vết.
12. **Điều tra phải phân biệt câu query được log, dữ liệu đã commit, dữ liệu API đã trả và hành vi con người đã được chứng minh**.

Khi chọn đúng các lớp ghi nhận, kiểm soát dữ liệu nhạy cảm ngay từ nguồn và duy trì quy trình quản trị rõ ràng, PostgreSQL có thể hỗ trợ điều tra sự cố và yêu cầu kiểm toán mà không biến hệ thống logging thành một kênh rò rỉ dữ liệu mới.
