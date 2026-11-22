# Health check, readiness và kiểm tra khả năng phục vụ thực tế

Một PostgreSQL server có thể đang chạy nhưng ứng dụng vẫn không thể phục vụ yêu cầu. Tiến trình có thể mở cổng TCP nhưng từ chối kết nối trong lúc recovery; database có thể nhận kết nối nhưng role ứng dụng thiếu quyền; truy vấn `SELECT 1` có thể thành công trong khi bảng hoặc schema mà ứng dụng cần chưa được migration; primary có thể hoạt động nhưng replica đã trễ quá giới hạn; connection pool có thể cạn dù PostgreSQL vẫn khỏe.

Vì vậy, health check cần trả lời đúng câu hỏi của từng lớp hệ thống. **Liveness** cho biết tiến trình có còn hoạt động hay cần khởi động lại. **Readiness** cho biết instance có thể nhận loại lưu lượng cụ thể ngay lúc này. **Health check của PostgreSQL** quan sát trạng thái server, database và các khả năng mà ứng dụng thực sự phụ thuộc. Một phép kiểm tra tốt phải nhẹ, có timeout, chạy bằng danh tính phù hợp và phản ánh được lỗi có thể ảnh hưởng đến người dùng.

## 1. Phân biệt liveness, readiness và startup

Ba khái niệm thường được dùng trong bộ điều phối container, load balancer và hệ thống giám sát.

| Loại kiểm tra | Câu hỏi | Hành động khi thất bại | Ví dụ |
|---|---|---|---|
| Liveness | Tiến trình có còn sống và có khả năng tiếp tục chạy không? | Có thể khởi động lại tiến trình nếu thất bại liên tục | Process tồn tại, event loop không bị treo |
| Readiness | Instance có thể nhận yêu cầu mới không? | Tạm ngừng gửi traffic đến instance | Kết nối DB, schema và dependency bắt buộc sẵn sàng |
| Startup | Ứng dụng đã hoàn tất khởi động ban đầu chưa? | Chờ thêm trước khi áp dụng liveness/readiness | Migration, warm-up cache hoặc khôi phục kết nối ban đầu |

Không nên dùng một endpoint duy nhất cho cả ba mục đích nếu chúng có hành vi khác nhau. Ví dụ, PostgreSQL đang recovery sau restart có thể chưa nhận kết nối. Việc liên tục restart một container database vì readiness thất bại sẽ không giúp recovery hoàn tất; nó có thể khiến database lặp lại quá trình khởi động.

Với ứng dụng kết nối PostgreSQL, liveness thường nên tập trung vào tiến trình ứng dụng. Readiness có thể kiểm tra kết nối qua pool, quyền truy cập schema và dependency bắt buộc. Startup probe cho phép ứng dụng có đủ thời gian khởi tạo trong khi các probe khác chưa bắt đầu đánh giá.

## 2. Xác định phạm vi của một health check

Health check cần có phạm vi rõ ràng. Một kiểm tra cấp TCP, một kiểm tra PostgreSQL protocol và một truy vấn nghiệp vụ có thể cho kết quả khác nhau.

1. **Process:** tiến trình PostgreSQL hoặc ứng dụng có tồn tại không?
2. **Network:** host, port, DNS, route và firewall có cho phép kết nối không?
3. **Protocol:** server có phản hồi PostgreSQL startup packet và trạng thái kết nối không?
4. **Authentication:** client có xác thực được bằng role và phương thức dự kiến không?
5. **Database:** database cần dùng có tồn tại và chấp nhận kết nối không?
6. **SQL capability:** role có chạy được truy vấn cần thiết không?
7. **Schema contract:** bảng, view, function và phiên bản migration cần thiết đã có chưa?
8. **Read/write capability:** đường đọc hoặc ghi mà workload cần có đang hoạt động không?
9. **Replication/failover:** instance có đúng vai trò primary/standby và đủ mới để phục vụ không?
10. **Service capacity:** connection pool, lock, I/O và latency có còn trong giới hạn phục vụ không?

Không phải endpoint readiness nào cũng cần thực hiện đủ mười bước. Hãy chọn những điều kiện bắt buộc cho loại traffic mà instance nhận. Ví dụ, một read replica phục vụ báo cáo có thể chấp nhận chỉ đọc và một mức lag nhất định; primary nhận ghi cần có khả năng commit; một worker ETL có thể cần quyền đọc nguồn và ghi vào database đích.

## 3. Dùng `pg_isready` để kiểm tra PostgreSQL có nhận kết nối

`pg_isready` là tiện ích đi kèm PostgreSQL client. Nó kiểm tra trạng thái phản hồi của server PostgreSQL trên host/port/database được chỉ định. Đây là phép kiểm tra nhanh cho trạng thái server, thường phù hợp với probe ở mức hạ tầng.

Ví dụ:

```bash
pg_isready -h db.internal -p 5432 -d appdb -U app_health -t 3
```

Các tham số thường dùng:

- `-h`: hostname hoặc địa chỉ máy chủ.
- `-p`: port PostgreSQL.
- `-d`: tên database được kiểm tra.
- `-U`: tên user được cung cấp trong startup packet.
- `-t`: thời gian chờ phản hồi, tính bằng giây.

### Mã thoát

`pg_isready` cung cấp mã thoát để script có thể xử lý:

| Mã thoát | Ý nghĩa |
|---:|---|
| `0` | Server đang chấp nhận kết nối |
| `1` | Server phản hồi nhưng đang từ chối kết nối, chẳng hạn trong lúc startup hoặc shutdown |
| `2` | Không nhận được phản hồi từ server |
| `3` | Không có nỗ lực kết nối, thường do tham số không hợp lệ |

Ví dụ shell:

```bash
if pg_isready -h db.internal -p 5432 -d appdb -t 3; then
  echo "PostgreSQL accepts connections"
else
  status=$?
  echo "PostgreSQL is not ready; pg_isready exit=$status"
  exit 1
fi
```

### Giới hạn của `pg_isready`

`pg_isready` không chứng minh rằng role có thể đăng nhập thành công hoặc chạy truy vấn. Server có thể báo đang nhận kết nối ngay cả khi thông tin user, database hoặc password được cung cấp không đúng; các lần thử có thể xuất hiện trong log server dưới dạng lỗi xác thực. Công cụ này không thay thế một truy vấn SQL được thực thi bằng tài khoản của ứng dụng.

Do đó, có thể dùng `pg_isready` để kiểm tra server và network nhanh, nhưng readiness của ứng dụng cần kiểm tra sâu hơn qua driver hoặc `psql` với secret và role thực tế.

## 4. Kiểm tra kết nối và SQL bằng role thực tế

Để biết ứng dụng có thể làm việc với PostgreSQL, hãy thực hiện truy vấn nhỏ qua cùng đường kết nối, cùng database, cùng role và cấu hình TLS mà ứng dụng sử dụng.

Ví dụ với `psql`:

```bash
psql "$DATABASE_URL" \
  -X \
  -v ON_ERROR_STOP=1 \
  -c 'SELECT 1;'
```

`-X` không đọc file `psqlrc` của người dùng, giúp kết quả script ít phụ thuộc môi trường. `ON_ERROR_STOP` khiến `psql` trả lỗi khi câu lệnh thất bại. Biến `DATABASE_URL` nên được cấp từ secret manager hoặc môi trường runtime được bảo vệ; không in chuỗi kết nối chứa password ra log.

Một truy vấn có thêm thông tin chẩn đoán:

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    pg_is_in_recovery() AS is_standby,
    current_setting('transaction_read_only') AS transaction_read_only,
    now() AS checked_at;
```

Truy vấn giúp xác nhận database, role và vai trò recovery của server mà client đã kết nối. `pg_is_in_recovery() = true` thường cho biết instance đang ở chế độ standby/recovery. `transaction_read_only` cho biết trạng thái read-only của transaction hiện tại; không nên suy ra chỉ từ một trường này rằng toàn bộ hệ thống có khả năng ghi.

### Kiểm tra bằng ứng dụng

Nếu ứng dụng dùng JDBC, Npgsql, psycopg hoặc driver khác, probe readiness nên đi qua chính connection pool và driver đó. Một lệnh `psql` chạy được từ container giám sát không chứng minh rằng ứng dụng có thể resolve DNS, lấy secret, mở kết nối hoặc mượn connection từ pool.

Một readiness handler có thể mượn một connection từ pool, đặt timeout ngắn, chạy `SELECT 1`, xác nhận kết quả rồi trả connection về pool. Handler không nên tạo một kết nối mới mỗi lần được gọi nếu ứng dụng đã quản lý pool.

## 5. Kiểm tra quyền và schema mà ứng dụng cần

`SELECT 1` không truy cập bảng nghiệp vụ và không kiểm tra quyền trên schema ứng dụng. Nếu ứng dụng cần đọc `app.orders`, readiness có thể thực hiện một truy vấn nhẹ trên chính đối tượng đó:

```sql
SELECT id
FROM app.orders
ORDER BY id
LIMIT 1;
```

Truy vấn này xác nhận role có thể đọc đối tượng và đối tượng tồn tại. Nếu bảng rỗng, truy vấn vẫn thành công và trả về không hàng; điều đó thường đủ cho kiểm tra khả năng truy cập, nhưng không xác nhận dữ liệu nghiệp vụ có mặt.

Để kiểm tra quyền rõ ràng hơn, có thể dùng hàm kiểm tra privilege:

```sql
SELECT
    has_schema_privilege(current_user, 'app', 'USAGE') AS can_use_schema,
    has_table_privilege(current_user, 'app.orders', 'SELECT') AS can_read_orders;
```

Đối với function hoặc sequence, dùng hàm privilege tương ứng. Tuy nhiên, phép kiểm tra tốt nhất vẫn là truy vấn thực tế qua driver vì nó kiểm tra đồng thời quyền, schema resolution, kiểu dữ liệu và đường kết nối.

### Tránh probe nặng

Không chạy `COUNT(*)` trên bảng lớn, join nhiều bảng hoặc truy vấn báo cáo nặng ở mỗi lần readiness được gọi. Probe được gọi thường xuyên và từ nhiều instance; một health check nặng có thể tự tạo tải khi hệ thống đang quá tải. Ưu tiên `SELECT 1`, kiểm tra metadata hoặc truy vấn giới hạn một hàng có index phù hợp.

## 6. Kiểm tra phiên bản schema và migration

Một ứng dụng có thể kết nối được nhưng chưa sẵn sàng phục vụ vì migration chưa chạy hoặc schema đang ở phiên bản không tương thích. Hãy lưu phiên bản migration trong bảng quản lý, ví dụ bảng do Flyway hoặc Liquibase quản lý, hoặc một bảng phiên bản do ứng dụng kiểm soát.

Ví dụ bảng phiên bản đơn giản:

```sql
CREATE TABLE app.schema_version (
    component text PRIMARY KEY,
    version text NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT now()
);
```

Readiness có thể kiểm tra phiên bản tối thiểu mà ứng dụng hiện tại yêu cầu:

```sql
SELECT version
FROM app.schema_version
WHERE component = 'orders-service';
```

Ứng dụng nên so sánh phiên bản theo quy tắc đã định nghĩa, không so sánh chuỗi phiên bản một cách ngây thơ nếu định dạng có số nhiều chữ số hoặc nhánh release. Khi dùng migration tool, nên đọc bảng lịch sử của công cụ theo API hoặc quy ước ổn định, tránh phụ thuộc vào cấu trúc nội bộ có thể thay đổi.

### Migration khi nhiều replica ứng dụng khởi động

Không nên để mọi replica ứng dụng đồng thời chạy migration độc lập khi khởi động nếu công cụ migration không được cấu hình để khóa/điều phối. Một quy trình triển khai thường chạy migration như một bước riêng, chờ hoàn tất rồi mới mở traffic cho phiên bản ứng dụng yêu cầu schema mới.

Với triển khai rolling, ưu tiên thay đổi tương thích ngược: thêm cột hoặc bảng trước, triển khai ứng dụng có thể đọc/ghi schema cũ và mới, backfill, chuyển traffic, sau đó mới loại bỏ cấu trúc cũ. Readiness cần phản ánh schema mà phiên bản ứng dụng hiện tại thực sự yêu cầu.

## 7. Kiểm tra khả năng đọc và ghi thực tế

Readiness phải khớp với vai trò của instance. Một API chỉ đọc có thể sẵn sàng khi truy vấn đọc hoạt động; một API tạo đơn hàng cần xác nhận đường ghi hoạt động. Không nên kiểm tra write trên replica read-only rồi đánh dấu service không khỏe nếu replica đó vốn chỉ phục vụ đọc.

### Read probe

Một read probe có thể truy vấn một bảng quan trọng với điều kiện có index:

```sql
SELECT id
FROM app.orders
WHERE id = $1;
```

Trong health check định kỳ, không nên dùng một ID tùy ý nếu truy vấn trả về không hàng bị coi là lỗi. Có thể dùng một truy vấn metadata hoặc một bản ghi canary đã được quản lý. Nếu mục tiêu chỉ là kiểm tra quyền SELECT, kết quả rỗng vẫn có thể được coi là thành công.

### Write probe có commit

Để xác nhận khả năng commit thật, có thể dùng một bảng canary riêng với khóa cố định. Ví dụ:

```sql
CREATE TABLE app.health_write_probe (
    probe_name text PRIMARY KEY,
    checked_at timestamptz NOT NULL,
    sequence_no bigint NOT NULL
);
```

Một worker kiểm tra có thể thực hiện upsert:

```sql
INSERT INTO app.health_write_probe (
    probe_name,
    checked_at,
    sequence_no
)
VALUES ('orders-api', clock_timestamp(), 1)
ON CONFLICT (probe_name) DO UPDATE
SET checked_at = EXCLUDED.checked_at,
    sequence_no = app.health_write_probe.sequence_no + 1;
```

Để kiểm tra commit, câu lệnh phải được commit thành công. Nếu transaction bị rollback, probe chỉ xác nhận câu lệnh có thể chạy trong transaction, chưa xác nhận commit được. Write probe cần chạy với role và đường kết nối tương ứng với ứng dụng ghi.

Không nên chạy write probe quá thường xuyên từ mọi replica. Nó tạo WAL, cập nhật tuple và index, có thể kích hoạt trigger hoặc replication. Có thể dùng một probe writer tập trung hoặc chu kỳ dài hơn, đồng thời tách khỏi endpoint readiness được load balancer gọi liên tục.

### Vì sao rollback không chứng minh khả năng commit?

Transaction rollback có thể xác nhận quyền và một phần đường thực thi nhưng không xác nhận transaction commit thành công, WAL flush hoặc các chính sách đồng bộ cần thiết. Nếu yêu cầu là xác nhận commit, hãy dùng canary write có commit, với dữ liệu và tần suất được kiểm soát.

## 8. Kiểm tra vai trò primary và standby

Trong kiến trúc có streaming replication, ứng dụng cần biết endpoint đang trỏ đến primary hay standby. Primary thường nhận ghi; hot standby phục vụ truy vấn chỉ đọc.

```sql
SELECT pg_is_in_recovery() AS is_standby;
```

Nếu endpoint ghi vô tình trỏ đến standby, ứng dụng có thể nhận lỗi khi ghi. Nếu endpoint đọc được thiết kế chỉ phục vụ replica, `is_standby = true` là trạng thái mong đợi. Vì vậy, kết quả cần được so sánh với vai trò dự kiến của endpoint.

Không dùng một giá trị hard-code kiểu “`is_standby` phải false ở mọi nơi”. Trong hệ thống có primary và nhiều replica, readiness cần biết service đang kiểm tra là writer, reader hay node dùng cho backup.

### Kiểm tra read-only transaction

```sql
SHOW transaction_read_only;
```

Giá trị `on` cho biết transaction hiện tại chỉ đọc. Ở standby, transaction thường read-only. Ở primary, session hoặc transaction vẫn có thể bị đặt read-only bởi cấu hình, connection option hoặc `SET TRANSACTION READ ONLY`. Hãy kiểm tra đúng session mà ứng dụng dùng.

## 9. Kiểm tra độ trễ replication

Replica có thể nhận kết nối và chạy truy vấn nhưng dữ liệu đã trễ quá mức nghiệp vụ cho phép. Readiness của một reader có thể cần giới hạn lag, chẳng hạn tối đa vài giây cho màn hình theo dõi gần thời gian thực hoặc vài phút cho báo cáo ít nhạy với độ mới.

### Trên standby

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at,
    now() - pg_last_xact_replay_timestamp() AS time_since_last_replay;
```

`pg_last_xact_replay_timestamp()` cho biết thời điểm transaction cuối cùng được replay. Chênh lệch `now() - timestamp` không phải lúc nào cũng là replication lag chính xác: nếu primary không có giao dịch mới, giá trị có thể tăng dù replica đã theo kịp; khi chưa replay transaction nào, timestamp có thể là `NULL`. Nên kết hợp với LSN hoặc heartbeat do hệ thống phát ra khi cần đo lag chính xác.

### Trên primary

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Các trường lag trong view thống kê phản ánh khoảng trễ gần đây của các giai đoạn gửi/ghi/flush/replay WAL; chúng có thể trở thành `NULL` khi hệ thống idle hoặc không có số liệu mới. Không nên diễn giải một giá trị `NULL` đơn giản là replica đã hỏng.

### Heartbeat để đo độ mới

Một cách đáng tin cậy hơn cho yêu cầu nghiệp vụ là ghi heartbeat định kỳ trên primary:

```sql
CREATE TABLE ops.replication_heartbeat (
    heartbeat_name text PRIMARY KEY,
    updated_at timestamptz NOT NULL
);

INSERT INTO ops.replication_heartbeat (heartbeat_name, updated_at)
VALUES ('primary', clock_timestamp())
ON CONFLICT (heartbeat_name) DO UPDATE
SET updated_at = EXCLUDED.updated_at;
```

Reader đọc timestamp ở replica và tính độ trễ so với thời gian hiện tại. Heartbeat phải được ghi đủ thường xuyên, dùng đồng hồ đồng bộ và được replicate qua cùng cơ chế cần giám sát. Nếu publisher ngừng ghi heartbeat, kết quả cũng không còn phân biệt được replica lag với primary idle; monitor cần biết trạng thái heartbeat nguồn.

Readiness của replica có thể trả `not ready` nếu lag vượt ngưỡng cấu hình. Tuy nhiên, cần cân nhắc tránh làm tất cả replica bị loại khỏi load balancer trong một đợt tải cao. Có thể dùng ngưỡng cảnh báo và ngưỡng loại traffic riêng.

## 10. Kiểm tra connection pool và giới hạn kết nối

PostgreSQL có giới hạn kết nối. Một server có thể chấp nhận kết nối mới nhưng ứng dụng vẫn không lấy được connection vì pool đã cạn hoặc pooler không thể cấp session. Readiness của ứng dụng cần kiểm tra khả năng mượn connection từ pool, không chỉ mở socket mới.

### Quan sát kết nối trên PostgreSQL

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

So sánh số session hiện tại với `max_connections`:

```sql
SELECT
    current_setting('max_connections')::integer AS max_connections,
    count(*) FILTER (
        WHERE backend_type = 'client backend'
    ) AS client_connections
FROM pg_stat_activity;
```

Đây là ảnh chụp tại thời điểm truy vấn; số kết nối có thể thay đổi ngay sau đó. Một số connection được dành cho role quản trị hoặc replication tùy phiên bản và cấu hình. Không nên đặt ngưỡng readiness chỉ bằng phép so sánh `count = max_connections`; hãy theo dõi xu hướng, connection theo role và pool wait ở phía ứng dụng.

### Kiểm tra ở phía pool

Các metric nên theo dõi:

- Tổng connection trong pool và số connection đang sử dụng.
- Số connection idle có thể cấp ngay.
- Số request đang chờ mượn connection.
- Thời gian chờ trung bình và p95/p99 để lấy connection.
- Số lần timeout khi acquire connection.
- Số lần tạo kết nối mới, reset hoặc loại bỏ connection lỗi.

Nếu pool cạn, endpoint readiness nên phản ánh rằng instance không thể nhận thêm công việc trong giới hạn an toàn. Nhưng không nên trả `not ready` chỉ vì một request ngắn chờ pool trong vài mili giây; cần ngưỡng và thời gian hysteresis để tránh flapping.

### PgBouncer và connection proxy

Nếu ứng dụng kết nối qua PgBouncer hoặc proxy tương tự, hãy kiểm tra cả pooler và PostgreSQL backend. Pooler có thể hoạt động nhưng không còn server connection; PostgreSQL có thể khỏe nhưng pooler không thể phục vụ client. Trong transaction pooling, một số tính năng phụ thuộc session như temporary table, session-level `SET`, advisory lock session hoặc prepared statement cần được xem xét theo phiên bản và cấu hình pooler.

## 11. Kiểm tra lock và truy vấn bị chặn

Một database có thể nhận truy vấn nhưng phần lớn session đang chờ lock. Readiness probe dùng `SELECT 1` có thể chạy nhanh trong khi giao dịch nghiệp vụ bị block trên một bảng nóng.

Kiểm tra session đang chờ:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

Để tìm blocker, có thể dùng `pg_blocking_pids(pid)`:

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_application,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_application,
    now() - waiting.query_start AS waiting_for,
    left(waiting.query, 200) AS waiting_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS blocked_by(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocked_by.pid;
```

Health check không nên quét và phân tích toàn bộ lock graph ở mỗi request. Đây là truy vấn giám sát để chạy theo chu kỳ hoặc khi phát hiện latency tăng. Readiness có thể dùng metric tổng hợp như số session chờ lock quá lâu thay vì truy vấn sâu liên tục.

## 12. Kiểm tra khả năng phục vụ truy vấn thực tế

`SELECT 1` kiểm tra một phần rất nhỏ của đường đi. Một service có thể cần truy vấn qua nhiều bảng, function, view hoặc extension. Hãy chọn một hoặc hai truy vấn đại diện nhưng giới hạn chi phí.

Ví dụ readiness cho service đơn hàng:

```sql
SELECT o.id
FROM app.orders AS o
WHERE o.status = 'open'
ORDER BY o.created_at DESC
LIMIT 1;
```

Nếu truy vấn này dùng index phù hợp, nó có thể kiểm tra schema, quyền và đường truy cập gần với ứng dụng. Cần chắc chắn điều kiện và index không làm probe trở nên nặng khi dữ liệu tăng.

Đối với API có nhiều đường đi, không cần readiness kiểm tra mọi endpoint. Nên chọn các dependency bắt buộc cho phần lớn yêu cầu. Một lỗi ở hệ thống báo cáo phụ có thể không nên làm API ghi đơn hàng bị loại khỏi traffic nếu báo cáo không nằm trên đường xử lý giao dịch.

### Kiểm tra function hoặc extension

Nếu ứng dụng phụ thuộc vào một function hoặc extension, có thể chạy phép gọi nhẹ tương ứng. Ví dụ:

```sql
SELECT app.normalize_order_code('health-probe');
```

Chỉ dùng function không có tác dụng phụ. Nếu function ghi dữ liệu, gọi mạng hoặc khóa bảng, không nên chạy ở readiness thường xuyên. Cần kiểm tra function tồn tại, quyền EXECUTE và phiên bản extension theo đúng yêu cầu ứng dụng.

## 13. Kiểm tra transaction và durability

Một truy vấn thành công không bảo đảm rằng mọi loại transaction đều có thể commit. Với workload ghi, khả năng phục vụ có thể phụ thuộc WAL, synchronous commit, dung lượng đĩa, quyền ghi và trạng thái storage.

### Kiểm tra commit bằng canary

Canary write như bảng `health_write_probe` ở phần trước xác nhận một transaction nhỏ có thể commit qua đường ghi. Để có ý nghĩa, nó phải dùng cùng endpoint, role, pool và cấu hình đồng bộ mà ứng dụng sử dụng. Không nên ghi vào bảng nghiệp vụ thật để kiểm tra sức khỏe.

### Không kiểm tra durability bằng transaction rollback

Một transaction `BEGIN; INSERT; ROLLBACK;` không kiểm tra commit và không kiểm tra độ bền của dữ liệu đã commit. Nó có thể hữu ích để thử quyền hoặc trigger transactional, nhưng không thay thế một canary transaction được commit.

### Theo dõi WAL và storage

Các tình huống như filesystem đầy, WAL không thể ghi, archive command lỗi kéo dài hoặc replication slot giữ WAL có thể làm giảm khả năng phục vụ. Health monitoring cần theo dõi dung lượng filesystem chứa data directory và `pg_wal`, tốc độ tăng WAL, lỗi checkpoint/archive và trạng thái backup. Không nên chạy truy vấn đọc file hệ điều hành từ database như một phép kiểm tra thông thường; dùng monitoring agent ở cấp host để quan sát dung lượng và I/O.

## 14. Timeout và thiết kế probe không gây tải

Mỗi probe cần timeout nhỏ hơn timeout của hệ thống gọi nó. Nếu load balancer chờ 10 giây nhưng SQL probe không có timeout, một đợt nghẽn có thể giữ nhiều request health check và làm cạn worker.

Thiết kế thực tế thường có:

- Timeout kết nối ngắn, ví dụ 1–3 giây tùy mạng.
- `statement_timeout` riêng cho probe, ví dụ 1 giây.
- Số lần retry ít và có backoff.
- Một khoảng thời gian duy trì trạng thái lỗi trước khi loại instance để tránh flapping.
- Cache kết quả probe rất ngắn nếu nhiều hệ thống gọi cùng endpoint.
- Giới hạn số truy vấn giám sát đồng thời.

Có thể đặt timeout cho session kiểm tra:

```sql
SET statement_timeout = '1s';
SET lock_timeout = '250ms';
SELECT 1;
```

`statement_timeout` giới hạn tổng thời gian câu lệnh. `lock_timeout` giới hạn thời gian chờ khóa. Probe thông thường không nên cần khóa ứng dụng; nếu bị block do lock, kết quả timeout có thể là tín hiệu hệ thống không phục vụ tốt.

Đặt timeout trong connection string hoặc cấu hình driver nếu cần áp dụng ngay từ lúc thiết lập kết nối. Khi dùng pool, cần reset session state hoặc cấu hình ở mức role/database để tránh ảnh hưởng request khác dùng chung connection.

## 15. Thiết kế endpoint health trong ứng dụng

Một service có thể cung cấp các endpoint riêng:

| Endpoint | Nội dung | Người gọi |
|---|---|---|
| `/live` | Kiểm tra tiến trình và vòng lặp xử lý | Orchestrator |
| `/startup` | Khởi tạo ứng dụng, cấu hình và migration đã xong chưa | Orchestrator |
| `/ready` | Có thể nhận request mới qua pool và dependency bắt buộc không | Load balancer/orchestrator |
| `/health/details` | Metric và trạng thái chi tiết có kiểm soát truy cập | Monitoring/operator |

Endpoint public nên trả trạng thái tổng quát và không tiết lộ hostname nội bộ, tên database, SQL, username hoặc stack trace. Endpoint chi tiết cần được bảo vệ bằng xác thực và mạng quản trị.

### Ví dụ phản hồi JSON

```json
{
  "status": "ready",
  "checks": {
    "postgres_connection": "ok",
    "schema_version": "ok",
    "connection_pool": "ok"
  },
  "checked_at": "2026-11-14T08:00:00Z"
}
```

Chỉ đưa các chi tiết cần thiết vào response. Không trả connection string, secret, dữ liệu người dùng hoặc toàn bộ lỗi SQL ra endpoint public.

### Ví dụ logic readiness

```text
function readiness():
    if application_is_shutting_down:
        return NOT_READY

    connection = pool.acquire(timeout = 1 second)
    if acquisition_failed:
        return NOT_READY

    try:
        set_local_statement_timeout(connection, 1 second)
        row = execute(connection, "SELECT 1")
        if row != 1:
            return NOT_READY

        schema = execute(connection, "SELECT required_schema_version()")
        if schema is incompatible:
            return NOT_READY

        if this service requires a writer:
            if execute(connection, "SELECT pg_is_in_recovery()") is true:
                return NOT_READY

        return READY
    catch timeout_or_database_error:
        return NOT_READY
    finally:
        release(connection)
```

Đây là pseudocode. Hàm `required_schema_version()` chỉ là tên minh họa; trong ứng dụng thật, hãy dùng bảng phiên bản hoặc API migration hiện có. Không tạo một function database mới chỉ để làm ví dụ health check nếu không cần thiết.

## 16. Cấu hình probe trong Kubernetes

Kubernetes phân biệt startup, liveness và readiness probes. Với PostgreSQL chạy trong StatefulSet, có thể dùng `pg_isready` cho kiểm tra trạng thái chấp nhận kết nối ở mức container, nhưng cần cân nhắc thêm kiểm tra SQL và replication/role ở lớp giám sát phù hợp.

Ví dụ minh họa cho một container PostgreSQL:

```yaml
startupProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 60

livenessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3

readinessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

Đây chỉ là cấu hình cơ sở để minh họa cơ chế. Dùng cùng một `pg_isready` cho cả ba probe không đánh giá đầy đủ khả năng phục vụ của ứng dụng. Với database cluster có failover, readiness cần hiểu vai trò node và không được làm restart loop khi server đang recovery. Cần kết hợp operator/cluster manager và probe chuyên biệt theo kiến trúc.

Đối với ứng dụng kết nối PostgreSQL, readiness nên gọi endpoint của ứng dụng thực hiện kiểm tra qua connection pool. Startup probe có thể chờ migration hoặc warm-up. Liveness không nên thất bại chỉ vì PostgreSQL tạm thời mất kết nối, nếu restart ứng dụng không thể khắc phục nguyên nhân và sẽ tạo thêm áp lực reconnect.

## 17. Readiness khi failover và chuyển primary

Trong cluster có failover, node cũ có thể trở thành standby và node mới được promote thành primary. Ứng dụng cần chuyển sang endpoint writer hoặc service discovery trỏ đến primary mới.

Một quy trình readiness cho writer có thể kiểm tra:

1. Kết nối qua endpoint writer hiện tại.
2. `pg_is_in_recovery()` trả `false`.
3. Role ứng dụng có thể thực hiện truy vấn ghi cần thiết.
4. Schema tương thích với phiên bản ứng dụng.
5. Connection pool đã loại bỏ connection cũ và thiết lập connection mới.

Không dựa vào một IP cố định nếu cluster manager dùng virtual IP, DNS hoặc proxy để chuyển primary. DNS cache và connection pool có thể giữ địa chỉ cũ; cần cấu hình TTL, reconnect và xử lý lỗi transaction trong quá trình failover.

Các transaction đang chạy có thể bị ngắt khi failover. Ứng dụng phải phân biệt lỗi kết nối tạm thời với lỗi nghiệp vụ, và chỉ retry transaction theo cách an toàn. Một lệnh ghi có thể đã commit ở primary cũ nhưng client chưa nhận được phản hồi; retry mù có thể tạo dữ liệu trùng. Dùng idempotency key hoặc khóa nghiệp vụ để bảo vệ thao tác.

## 18. Readiness cho read replica

Replica phục vụ đọc cần các điều kiện riêng:

- `pg_is_in_recovery()` phải trả `true` nếu endpoint được thiết kế cho standby.
- Replica phải nhận và replay WAL.
- Lag không vượt ngưỡng của workload.
- Query không bị recovery conflict kéo dài hoặc bị hủy thường xuyên.
- Schema trên replica tương thích với ứng dụng đọc.
- Connection pool và tài nguyên đọc còn đủ năng lực.

Readiness không nên đòi replica bằng primary ở mọi thời điểm nếu kiến trúc chấp nhận eventual consistency. Có thể định nghĩa nhóm traffic nhạy với độ mới đọc primary, còn báo cáo chấp nhận replica có lag trong giới hạn. Một replica lag vượt ngưỡng có thể bị loại khỏi pool reader trong khi các replica khác vẫn phục vụ.

Nếu dùng logical replication thay vì physical streaming replication, cần kiểm tra trạng thái subscription, worker và độ trễ áp dụng theo từng bảng/luồng. Một subscription có thể hoạt động nhưng một bảng cụ thể chưa hoàn tất initial synchronization.

## 19. Readiness cho ETL, CDC và worker nền

Worker ETL không nhất thiết nhận traffic HTTP, nhưng vẫn cần health status. Các điều kiện quan trọng có thể gồm:

- Kết nối nguồn và đích qua credential runtime.
- Đọc được schema/bảng nguồn cần thiết.
- Ghi được vào staging hoặc đích.
- Watermark/offset hợp lệ và có thể tiến lên.
- Replication slot/CDC stream còn tồn tại và không giữ WAL vượt giới hạn.
- Lần chạy gần nhất hoàn tất trong SLA.
- Không có backlog hoặc dead-letter queue vượt ngưỡng.

Một worker đang xử lý batch dài không nên bị xem là unhealthy chỉ vì chưa hoàn tất trong vài giây. Health check nên phân biệt process heartbeat với progress heartbeat. Worker còn sống nhưng không có tiến độ trong thời gian dài có thể cần cảnh báo hoặc bị đánh dấu degraded.

Với CDC, kiểm tra slot `active` không đủ để chứng minh consumer đang xử lý đúng. Hãy theo dõi LSN/offset, thời gian sự kiện mới nhất, tốc độ nhận/áp dụng, lỗi schema và WAL retention. Với batch, theo dõi watermark và số hàng xử lý.

## 20. Phân loại lỗi và phản ứng phù hợp

Không phải mọi lỗi health check đều nên dẫn đến restart. Phản ứng cần phù hợp với nguyên nhân.

| Tình trạng | Lớp có thể lỗi | Phản ứng thường phù hợp |
|---|---|---|
| Process ứng dụng treo | Application liveness | Restart ứng dụng sau ngưỡng xác nhận |
| PostgreSQL đang recovery | Database startup/readiness | Chờ recovery, không restart liên tục |
| DNS hoặc network tạm thời lỗi | Network | Retry có backoff, cảnh báo nếu kéo dài |
| Password hết hạn/sai | Authentication | Sửa secret/rotation, không retry dồn dập |
| Role thiếu quyền bảng | Authorization/schema | Sửa migration hoặc grant; deploy đúng thứ tự |
| Pool cạn | Application capacity | Giảm tải, xử lý connection leak hoặc tăng pool có kiểm soát |
| Replica lag cao | Replication | Loại replica khỏi traffic nhạy độ mới, điều tra WAL/replay |
| Lock wait tăng | Database workload | Tìm blocker và giao dịch dài, không restart database tùy tiện |
| Disk gần đầy | Host/storage | Giải phóng hoặc mở rộng dung lượng theo runbook |
| Migration chưa tương thích | Deployment | Giữ traffic ở phiên bản phù hợp, hoàn tất migration |

Một endpoint readiness chỉ nên trả trạng thái và lý do tổng quát. Hệ thống giám sát nội bộ cần lưu chi tiết để operator tìm nguyên nhân.

## 21. Tránh health check gây hiệu ứng dây chuyền

Khi database gặp sự cố, mọi replica ứng dụng có thể đồng thời mở kết nối mới và chạy probe. Nếu health check quá thường xuyên, hệ thống sẽ tạo thêm connection storm và làm tình trạng xấu hơn.

Các nguyên tắc giảm tải:

- Dùng pool hiện có cho probe ứng dụng thay vì mở connection mới mỗi lần.
- Đặt timeout và giới hạn số lần retry.
- Dùng jitter để các replica không chạy probe cùng một thời điểm.
- Tránh truy vấn full scan, aggregate hoặc join nặng.
- Không thực hiện write probe từ mọi instance ở tần suất cao.
- Không gọi một endpoint chi tiết liên tục từ load balancer công khai.
- Dùng circuit breaker để hạn chế request vào dependency đang lỗi.
- Phân biệt lỗi tạm thời với lỗi cấu hình cần can thiệp.

Nếu toàn bộ ứng dụng đánh dấu not-ready cùng lúc, load balancer có thể không còn backend nào. Hãy thiết kế rollout và failover sao cho còn đủ capacity, đồng thời có cảnh báo trước khi toàn bộ instance bị loại khỏi traffic.

## 22. Bảo mật endpoint và dữ liệu health

Health check thường được gọi từ orchestrator hoặc load balancer. Endpoint công khai nên tránh tiết lộ thông tin có thể giúp dò cấu trúc hạ tầng.

Không trả ra:

- Password, token, connection string hoặc nội dung secret.
- Hostname nội bộ, IP quản trị và topology chi tiết nếu không cần thiết.
- SQL đầy đủ có thể chứa dữ liệu đầu vào nhạy cảm.
- Tên người dùng, email hoặc dữ liệu khách hàng.
- Stack trace và thông báo lỗi chi tiết cho người gọi không tin cậy.

Ghi log nội bộ có thể chứa mã lỗi, correlation ID, database role và thời gian probe, nhưng cần masking dữ liệu và phân quyền truy cập. Endpoint chi tiết nên giới hạn trong mạng quản trị hoặc yêu cầu xác thực.

## 23. Mẫu SQL kiểm tra định kỳ

Các truy vấn sau có thể dùng trong dashboard giám sát nội bộ. Hãy chạy bằng role có quyền đọc thống kê cần thiết và điều chỉnh theo phiên bản PostgreSQL.

### Tổng quan instance

```sql
SELECT
    version() AS server_version,
    current_database() AS database_name,
    current_user AS checked_as,
    pg_is_in_recovery() AS is_standby,
    current_setting('max_connections') AS max_connections,
    now() AS checked_at;
```

### Tình trạng database

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

Các bộ đếm là số tích lũy kể từ lần reset thống kê gần nhất. Muốn biết tốc độ tăng, cần lấy hai mẫu theo thời gian và tính delta; không so sánh tổng tích lũy như một tốc độ tức thời.

### Session và trạng thái chờ

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

### Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Kết hợp các truy vấn với metric cấp host về dung lượng `pg_wal`, CPU, memory và I/O. Một SQL probe không thể quan sát đầy đủ tình trạng filesystem hoặc thiết bị lưu trữ.

## 24. Ví dụ script shell kiểm tra hai lớp

Script sau minh họa kiểm tra nhanh server bằng `pg_isready`, sau đó thực thi một truy vấn SQL bằng `psql`. Nó giả định biến `DATABASE_URL` được cung cấp an toàn trong môi trường chạy.

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be configured}"

if ! pg_isready -d "$DATABASE_URL" -t 2 >/dev/null; then
  echo "database server is not accepting connections" >&2
  exit 1
fi

psql "$DATABASE_URL" \
  -X \
  -v ON_ERROR_STOP=1 \
  -c "SET statement_timeout = '1s'; SELECT 1;" \
  >/dev/null

echo "database SQL probe succeeded"
```

Script không in thông tin xác thực. Nếu `DATABASE_URL` chứa password, cần bảo vệ môi trường process và tránh bật shell tracing (`set -x`). Trong môi trường production, nên dùng `PGPASSFILE` với quyền file hạn chế hoặc secret integration của nền tảng; không ghi password trực tiếp vào script.

`pg_isready` và `psql` là hai phép kiểm tra khác nhau. Bước đầu kiểm tra server có nhận kết nối; bước sau kiểm tra xác thực và thực thi SQL. Ứng dụng vẫn cần readiness qua chính driver/pool của nó nếu muốn xác nhận đường phục vụ cuối cùng.

## 25. Kiểm thử health check trước khi triển khai

Health check phải được thử cả khi hệ thống khỏe và khi có lỗi có kiểm soát trên môi trường staging.

1. **Database sẵn sàng:** `pg_isready` và SQL probe thành công.
2. **Server đang khởi động:** probe phân biệt trạng thái rejecting với no response.
3. **Sai password:** SQL probe thất bại, log không lộ secret.
4. **Thiếu quyền SELECT:** truy vấn trên bảng ứng dụng thất bại và trả lý do phù hợp.
5. **Schema cũ:** readiness không nhận traffic nếu phiên bản schema không tương thích.
6. **Pool cạn:** readiness phản ánh khả năng acquire connection và có timeout.
7. **Primary chuyển thành standby:** writer readiness phát hiện `pg_is_in_recovery()` và ngừng nhận ghi.
8. **Replica lag:** reader readiness áp dụng đúng ngưỡng độ mới.
9. **Lock contention:** monitor phát hiện wait lâu mà probe không tạo tải quá lớn.
10. **Database phục hồi:** service tự trở lại ready sau khi dependency phục hồi, không cần restart loop.
11. **Failover:** pool loại connection cũ, kết nối endpoint mới và retry thao tác an toàn.
12. **Shutdown có kiểm soát:** readiness chuyển not-ready trước khi tiến trình dừng để ngừng nhận request mới.

Nên đo thêm thời gian thực thi và tần suất gọi probe để xác nhận health check không trở thành một workload đáng kể.

## 26. Checklist vận hành

- [ ] Đã xác định riêng liveness, startup và readiness cho từng thành phần.
- [ ] `pg_isready` được dùng đúng mục đích và xử lý đúng mã thoát.
- [ ] SQL probe chạy bằng role, database, TLS và đường kết nối thực tế.
- [ ] Probe xác nhận quyền và schema tối thiểu mà ứng dụng cần.
- [ ] Phiên bản migration được kiểm tra theo hợp đồng tương thích.
- [ ] Writer và reader được kiểm tra theo vai trò mong đợi.
- [ ] Replica lag có ngưỡng và cách xử lý rõ ràng.
- [ ] Connection pool có metric về acquire wait, timeout và số connection.
- [ ] Write capability chỉ được kiểm tra bằng canary có kiểm soát khi thực sự cần.
- [ ] Probe có timeout, retry giới hạn và tránh truy vấn nặng.
- [ ] Endpoint public không tiết lộ secret hoặc thông tin nội bộ.
- [ ] Đã diễn tập startup, outage, failover, recovery và shutdown.
- [ ] Alert gắn với runbook và người chịu trách nhiệm.

## 27. Tài liệu tham khảo PostgreSQL

- PostgreSQL Documentation — `pg_isready`: https://www.postgresql.org/docs/current/app-pg-isready.html
- PostgreSQL Documentation — Server Administration: https://www.postgresql.org/docs/current/admin.html
- PostgreSQL Documentation — System Information Functions: https://www.postgresql.org/docs/current/functions-info.html
- PostgreSQL Documentation — Monitoring Database Activity: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Warm Standby and Streaming Replication: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Hot Standby: https://www.postgresql.org/docs/current/hot-standby.html
- PostgreSQL Documentation — Connection Settings: https://www.postgresql.org/docs/current/runtime-config-connection.html
- PostgreSQL Documentation — Client Authentication: https://www.postgresql.org/docs/current/client-authentication.html
- PostgreSQL Documentation — `pg_stat_activity` and Statistics Views: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — `pg_stat_replication` and Replication Slots: https://www.postgresql.org/docs/current/view-pg-stat-replication.html

Health check có giá trị khi nó phản ánh đúng khả năng mà service cần để phục vụ người dùng. Hãy kết hợp kiểm tra server, SQL, quyền, schema, pool, vai trò primary/standby và độ mới dữ liệu theo từng loại workload; đặt timeout và giới hạn chi phí cho probe; đồng thời dùng monitoring chuyên sâu để phát hiện các vấn đề về lock, WAL, storage và latency. Cách tiếp cận này giúp phân biệt một tiến trình đang chạy với một PostgreSQL instance thực sự sẵn sàng phục vụ.
