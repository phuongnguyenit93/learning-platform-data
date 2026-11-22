# Quản lý thay đổi cấu hình và xác minh sau triển khai

## Mục tiêu học tập

Sau khi học bài này, người học có thể:

1. Phân biệt **cấu hình mong muốn** (*desired state*) với **cấu hình đang có hiệu lực** (*effective state*) ở ứng dụng Java, connection pool, PostgreSQL và hạ tầng.
2. Đánh giá tác động của việc đổi timeout, pool size, isolation, replication, cache, schema, quyền và TLS đối với tính đúng đắn, hiệu năng và khả năng phục hồi.
3. Thiết kế quá trình quản lý thay đổi có owner, phiên bản, kiểm tra, phê duyệt, phát hành từng phần và rollback.
4. Lập các bước **baseline → preflight → canary → xác minh hậu triển khai → mở rộng rollout → theo dõi**.
5. Dùng SQL và metrics để kiểm tra DB configuration, transaction, kết nối, WAL, replica và query performance.
6. Phân biệt “đã triển khai”, “đã bật cấu hình”, “đã đạt SLO” và “đã giữ bất biến dữ liệu”.
7. Viết validation Java tại startup và smoke test JDBC an toàn, không làm thay đổi dữ liệu production.
8. Xác định ngưỡng dừng triển khai, kế hoạch rollback/forward fix và tập bằng chứng cần lưu.

Bài thuộc chương **Quan sát và vận hành** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module nghiên cứu dữ liệu bền vững trong Java: mô hình, schema, truy vấn/chỉ mục, transaction, cô lập, đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, backup và hiệu năng. Một thay đổi cấu hình persistence không chỉ làm đổi tốc độ: nó có thể thay đổi việc **giao dịch nào được xác nhận, dữ liệu nào được đọc và những sự cố nào còn có thể phục hồi**.

## 1. Deployment thành công chưa đủ để kết luận thay đổi thành công

Ví dụ dịch vụ xử lý đơn hàng dùng Java, HikariCP và PostgreSQL. Nhóm vận hành tăng pool mỗi instance từ 10 lên 40 để giảm thời gian chờ lấy connection. Pipeline báo:

~~~text
Build SUCCESS
Deployment SUCCESS
Container READY
GET /health -> HTTP 200
~~~

Những điều trên chưa chứng minh:

- Mọi instance đã nạp `maximumPoolSize=40`, không giữ pool cũ ở tiến trình chưa restart.
- Ứng dụng kết nối đúng primary, database, môi trường, role và tenant.
- PostgreSQL có đủ connection slot nếu số replica tự tăng.
- Connection wait giảm mà lock contention, I/O và p99 transaction không tăng.
- Transaction rollback/commit và retry vẫn đúng khi mất kết nối.
- Không có thay đổi ngoài ý muốn trong RPO, replication hoặc backup.
- Đường đọc cache/replica không trả stale data trái hợp đồng.
- Quy tắc bảo mật/RLS và idempotency không bị phá.

**Deployment success** phản ánh controller đã áp dụng một phiên bản. **Change success** cần chứng minh hệ thống chạy **đúng cấu hình** và duy trì **đúng hành vi nghiệp vụ**.

### 1.1. Bốn tầng bằng chứng

~~~text
Ý định thay đổi
      |
      v
Nguồn cấu hình đã version-control
      |
      v
Cấu hình effective trên từng instance/session/DB
      |
      v
Hành vi và kết quả dữ liệu quan sát được
~~~

| Tầng | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Intent | Đổi để đạt điều gì? | Change request, owner, giả thuyết, phạm vi rủi ro |
| Desired config | Nguồn cấu hình ghi giá trị nào? | Git revision, deployment manifest, secret version |
| Effective config | Runtime nào thực dùng giá trị đó? | Startup metadata, pool settings, `pg_settings`, runtime probes |
| Behavior | Có cải thiện và vẫn đúng không? | SLI/SLO, số lần ghi, query plan, transaction/replication metrics, test bất biến |

Một YAML trong Git là **ý định**, không tự chứng minh giá trị đã tới mọi pod. Một pod khỏe mạnh là **tín hiệu**, không tự chứng minh nghiệp vụ đã giữ tính nhất quán.

## 2. Phân loại cấu hình và vòng đời áp dụng

| Tầng | Ví dụ | Khi thay đổi có hiệu lực |
| --- | --- | --- |
| Mã Java | Logic retry, mapping JPA, SQL query | Khi phiên bản code mới chạy |
| Spring Boot | Datasource, HikariCP, transaction properties | Thường khi bean/process/pool khởi tạo lại; tùy thuộc tính |
| Environment/secret | JDBC URL, DB password, TLS config | Sau khi process/connection nhận giá trị mới |
| JDBC driver | `connectTimeout`, `socketTimeout`, `ApplicationName` | Theo connection được tạo với các thuộc tính |
| Pool | `maximumPoolSize`, `connectionTimeout`, `maxLifetime` | Theo API pool hoặc cấu hình khi khởi tạo, tùy bản triển khai |
| Session/transaction PostgreSQL | `statement_timeout`, `transaction_isolation`, `search_path` | Theo `SET`, `SET LOCAL` và phạm vi session/transaction |
| DB instance | `max_connections`, WAL/replication parameters | Có tham số reload được, có tham số cần restart |
| Schema | Table, index, constraint, RLS policy | Theo migration/DDL được thực thi và commit |
| Hạ tầng | Firewall, DNS, routing, proxy, autoscaling | Theo trạng thái controller và propagation |
| Cache/bus | TTL, key prefix, topic, ACL, consumer concurrency | Theo client/worker/store và cách rollout |

Cần phân biệt rõ:

- **Build time:** giá trị đóng vào artifact hoặc code; phải build/redeploy.
- **Startup time:** giá trị được đọc khi khởi tạo; sửa env chưa chắc đổi một process đang chạy.
- **Dynamic:** có API thay đổi runtime nhưng phải bảo đảm mọi instance nhận đúng.
- **Session/transaction-scoped:** session A đổi không nghĩa session B đổi.
- **Reload/restart:** PostgreSQL áp dụng tùy tham số; config file mới không đủ nếu server chưa reload/restart.
- **Migration/data state:** thay đổi schema không phải chỉ là một toggle, có thể không rollback bằng cách redeploy.

### 2.1. Configuration drift

~~~text
Git desired:
  DB_POOL_MAX_SIZE = 20

Pod A -> Hikari max = 20
Pod B -> Hikari max = 10 (chưa restart)
Pod C -> Hikari max = 20
Pod D -> crash-loop vì secret sai

PostgreSQL:
  max_connections = 200
~~~

Một dashboard tổng hợp có thể che drift. Cần gắn metadata không nhạy cảm như `app_version`, `config_revision`, `region`, `instance` và `deployment_id` để phân biệt các nhóm; **không gắn password, token, request key hoặc PII thành label**.

## 3. Bắt đầu từ mục tiêu và rủi ro, không bắt đầu từ một giá trị mới

Một thay đổi nên mô tả:

~~~text
CHANGE: PERSIST-042
Owner: Persistence/platform
Phạm vi: order-service production region A
Lý do: pool acquisition p99 tăng ở cao điểm
Giá trị cũ: pool max 10
Giá trị thử: pool max 20
Giả thuyết: giảm pending, không làm DB bão hòa
Bất biến: stock >= 0, một request key chỉ một kết quả,
          không lộ dữ liệu chéo tenant
SLO: checkout success rate / p95 / p99 giữ trong budget
Đường triển khai: staging -> 1 canary -> 25% -> 100%
Điều kiện dừng: lỗi, latency, saturation hoặc data anomaly
Rollback: quay về image/config revision cũ
Bằng chứng: cấu hình effective, metrics, SQL, smoke tests
~~~

Các giá trị là minh họa; giới hạn thực tế phải dựa vào baseline/SLO đã được phê duyệt.

### 3.1. Ma trận đánh giá rủi ro

| Đổi cấu hình | Lợi ích kỳ vọng | Rủi ro cần quan sát |
| --- | --- | --- |
| Tăng Hikari pool | Bớt chờ lấy connection | Quá `max_connections`, nhiều lock/I/O hơn |
| Giảm pool acquisition timeout | Fail fast | Tăng lỗi dưới tải, retry storm |
| Tăng socket timeout | Chịu được mạng chậm | Giữ tài nguyên lâu, commit outcome chưa rõ |
| Giảm `statement_timeout` | Chặn truy vấn quá lâu | Hủy giao dịch hợp lệ, tăng `57014` |
| Đổi isolation | Kiểm soát read skew/lost update | Tăng `40001`, khác visibility |
| Giảm `synchronous_commit` | Commit nhanh hơn | Tăng rủi ro mất commit khi crash |
| Chuyển read sang replica | Giảm tải primary | Replica lag, vi phạm read-your-writes |
| Tăng cache TTL | Giảm tải DB | Stale reads và invalidation race |
| Đổi RLS/tenant context | Phân quyền/hiệu năng | Rò rỉ hoặc mất khả năng đọc dữ liệu |
| Tự đồng bộ schema bằng ORM | Ít thao tác migration | DDL/lock bất ngờ, mất tương thích phiên bản |
| Tăng retry | Giảm lỗi thoáng qua | Ghi trùng, áp lực kết nối và DB |
| Đổi backup/replication | Đổi availability/durability | RPO/RTO, mất khả năng restore |
| Tăng `max_connections` | Nhiều kết nối đồng thời | RAM/backend overhead, cần restart |

Những thay đổi tác động đến **safety** (tính đúng đắn của dữ liệu) cần điều kiện phê duyệt và thử nghiệm mạnh hơn thay đổi chỉ tác động đến giao diện hiển thị.

## 4. Quản lý cấu hình có phiên bản và quyền thay đổi

Một quy trình có thể kiểm toán cần:

1. Có **source of truth** cho config không nhạy cảm, thường trong Git hoặc hệ quản lý cấu hình được phê duyệt.
2. Dùng secret manager riêng cho password, token, TLS private key và vật liệu mã hóa.
3. Mỗi deployment gắn với code artifact, config revision, schema/migration revision và thời điểm triển khai.
4. Có **diff** cũ/mới và reviewer phù hợp với mức rủi ro.
5. Phân biệt ai được đổi ở dev, staging, production; pipeline không dùng chung credential đặc quyền.
6. Cấm fallback âm thầm từ staging sang production khi thiếu biến môi trường.
7. Xử lý emergency config change bằng audit và đồng bộ lại về nguồn chính sau sự cố.
8. Lưu khả năng rollback nhưng xác định những tác động **không đảo ngược** bằng rollback config.

### 4.1. Ví dụ Spring Boot

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-primary
      maximum-pool-size: ${DB_POOL_MAX:10}
      minimum-idle: ${DB_POOL_MIN_IDLE:2}
      connection-timeout: ${DB_POOL_WAIT_MS:2000}
      validation-timeout: ${DB_VALIDATION_MS:1000}
      max-lifetime: ${DB_MAX_LIFETIME_MS:1800000}
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
~~~

Đây là ví dụ cho stack Spring Boot/HikariCP tương thích với các key nêu trên, không phải cấu hình khuyến nghị chung. Các giá trị mặc định chỉ phục vụ giải thích; cần xác định theo workload và version của framework.

- `url` phải chỉ đến đúng DB/environment và dùng TLS phù hợp.
- `maximum-pool-size` là giới hạn cho **một pool**; nếu nhiều instance thì phải tính cộng dồn.
- `connection-timeout` là thời gian chờ **pool cấp connection**, không phải timeout socket hoặc HTTP.
- `max-lifetime` phải xét connection lifetime của proxy/DB/network, tránh connection chết bất ngờ; không giữ một con số cố định cho mọi topology.
- `ddl-auto: validate` kiểm tra sự tương thích mapping theo provider, **không thay thế schema migration** và không chứng minh mọi native SQL đều hợp lệ.

**Không đặt password trực tiếp trong YAML được commit vào repo.** Để xác minh secret rotation, ghi nhận định danh version an toàn thay vì tiết lộ giá trị.

## 5. Sizing connection pool có tính đến autoscaling

Một phép kiểm tra cấp cao:

~~~text
Max potential application connections
  = tổng (maximumPoolSize của mỗi pool
          × số replica có thể đồng thời tồn tại)
~~~

Ví dụ:

~~~text
12 replicas × pool max 10 = 120 potential connections
12 replicas × pool max 40 = 480 potential connections

PostgreSQL max_connections = 300
=> Giới hạn mới có thể vượt nguồn lực DB rất xa.
~~~

Đây là **trần cấu hình**, không phải số connection đang mở tức thì. Hikari có thể chưa mở hết pool. Nhưng nếu autoscaling hoặc rolling deployment tạo số instance cao hơn dự kiến, hệ thống có thể chạm trần khi tải tăng.

Khi tính capacity, còn phải dự trù:

- Những service khác cùng kết nối.
- Pool read/write riêng và background job.
- Admin, migration, monitoring, replication/maintenance.
- Rolling rollout có **surge instances** và job chạy đồng thời.
- Connection proxy như PgBouncer nếu có: phân biệt app→proxy và proxy→PostgreSQL.
- Headroom cho xử lý sự cố.

### 5.1. Pool lớn có thể làm database chậm hơn

Connection pool không làm biến mất:

- SQL thiếu/chọn sai index.
- ORM tạo N+1 queries.
- Transaction giữ row lock lâu.
- CPU và I/O bão hòa.
- WAL flush hoặc synchronous standby latency.
- Những request giữ connection trong khi gọi API bên ngoài.

Nếu mở thêm connection khiến nhiều query tranh chấp cùng một hàng, `pool pending` có thể giảm nhưng `lock wait` và p99 tăng. Vì vậy cần đo **cả ứng dụng lẫn DB**, không chỉ kích thước pool.

## 6. Phân biệt các timeout trong chuỗi ghi

~~~text
HTTP deadline
   |
   +-- Chờ pool cấp connection
   +-- TCP connect / authentication nếu tạo connection mới
   +-- Bắt đầu transaction
   +-- Chờ khóa
   +-- Thực thi SQL
   +-- COMMIT và đợi ACK
   +-- Trả HTTP response
~~~

| Timeout | Điều bị giới hạn | Cảnh báo |
| --- | --- | --- |
| HTTP/gRPC deadline | Thời gian chờ của caller | Server có thể vẫn xử lý sau khi caller hết hạn |
| Pool acquisition | Chờ lấy connection khả dụng | Không đồng nghĩa DB statement timeout |
| TCP connect | Thiết lập kết nối | Không kiểm soát query sau khi kết nối |
| Socket read | Đợi dữ liệu từ DB | Timeout ở COMMIT có thể tạo outcome chưa rõ |
| PostgreSQL `lock_timeout` | Chờ khóa | Statement có thể thất bại, transaction cần xử lý |
| PostgreSQL `statement_timeout` | Thời gian statement | Hủy statement, không tự quản request deadline |
| `idle_in_transaction_session_timeout` | Session idle khi vẫn mở transaction | Server có thể kết thúc session và rollback |
| Transaction manager timeout | Transaction do framework điều phối | Quy tắc rollback/cancel theo framework |
| Hikari maxLifetime | Vòng đời connection trong pool | Không phải query timeout |

Một lỗi phổ biến là retry mọi lỗi timeout. `23514` là lỗi dữ liệu, không nên retry. `40001`/`40P01` thường cần **retry toàn transaction**. Lỗi mất phản hồi COMMIT phải được xử lý như **unknown outcome**, kiểm tra idempotency key và đối soát thay vì mặc định ghi lại.

### 6.1. Đổi timeout có thể ảnh hưởng durability

Giảm socket timeout có thể khiến client rời đi sớm hơn, nhưng database có thể đã nhận COMMIT. Nếu client tạo request key mới cho mỗi lần thử, giao dịch có thể bị lặp. Do đó trong gate hậu triển khai phải xem **số kết quả nghiệp vụ duy nhất**, không chỉ số lỗi HTTP.

Tương tự, `idle_in_transaction_session_timeout` có thể giúp chặn transaction bị bỏ quên; nhưng nếu code giữ transaction trong lúc chờ HTTP ngoài, thay đổi sẽ làm lộ lỗi thiết kế đó. Quan sát `transaction age` trước khi bật và sau khi áp dụng.

## 7. PostgreSQL: kiểm tra tham số có hiệu lực

### 7.1. Chỉ đọc những thông tin cấu hình cần thiết

~~~sql
SELECT name,
       setting,
       unit,
       context,
       source,
       pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
    'synchronous_commit',
    'wal_level',
    'archive_mode'
)
ORDER BY name;
~~~

Ý nghĩa:

- `setting`: giá trị theo góc nhìn session hiện tại.
- `unit`: đơn vị của giá trị, cần xét khi so sánh timeout.
- `context`: cấp độ thay đổi được PostgreSQL cho phép.
- `source`: nơi giá trị đang có hiệu lực được lấy từ.
- `pending_restart`: cờ báo thay đổi chưa có hiệu lực vì cần restart.

Không suy rằng `pending_restart = false` ở một instance nghĩa **toàn cluster** đang dùng cùng giá trị. DB primary và standby, role/default và mỗi session có thể khác.

### 7.2. Đọc đúng session đang dùng

~~~sql
SELECT current_database() AS db_name,
       current_user AS db_role,
       current_setting('transaction_isolation') AS isolation,
       current_setting('synchronous_commit') AS sync_commit,
       current_setting('TimeZone') AS timezone,
       pg_backend_pid() AS backend_pid;
~~~

Có thể chạy query này bằng datasource **thực sự phục vụ endpoint**, không chỉ từ console DBA. Nó giúp phát hiện khác biệt role, database hoặc session override.

Cần phân biệt:

- `default_transaction_isolation` và isolation của transaction cụ thể.
- `synchronous_commit=on` và việc **có synchronous standby được cấu hình đúng**.
- `TimeZone` của session và UTC instant trong kiểu `TIMESTAMPTZ`.
- Giá trị mà một transaction dùng qua `SET LOCAL` và giá trị của transaction tiếp theo.

### 7.3. Reload, restart và cấu hình ngoài Git

Một số tham số PostgreSQL đổi bằng `SET` trong session; một số cần reload config, một số đòi restart. Sửa `postgresql.conf` hay gọi `ALTER SYSTEM` chưa chắc làm tham số mới có hiệu lực ngay, và `ALTER SYSTEM` có thể tạo drift so với hệ IaC.

Khi xác minh cần ghi rõ: **node nào, session nào, lúc nào, revision nào và giá trị nào**. Không dump toàn bộ `pg_settings` vào log không kiểm soát; chỉ collect allowlist không nhạy cảm.

## 8. Quan sát connection và transaction tại DB

### 8.1. Phân bố session

~~~sql
SELECT application_name,
       state,
       wait_event_type,
       count(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state, wait_event_type
ORDER BY sessions DESC;
~~~

Nhìn tổng connection thôi chưa đủ. Cần xem session **active**, **idle**, **idle in transaction**, đang chờ lock/I/O hay đang thực thi.

### 8.2. Transaction kéo dài

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

- `xact_start` là thời điểm transaction hiện tại bắt đầu, không phải lúc connection được tạo.
- `wait_event_type` cho biết loại đang chờ nhưng không tự xác định nguyên nhân gốc.
- Vai trò runtime có thể không xem được đầy đủ chi tiết session khác; cần quyền quan sát phù hợp.
- Không log nguyên văn `query` hàng loạt vì có thể chứa dữ liệu nhạy cảm.

### 8.3. Số commit, rollback và deadlock

~~~sql
SELECT datname,
       xact_commit,
       xact_rollback,
       deadlocks,
       stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

Đây là counter theo DB, không phải metric riêng từng service. Khi DB statistics reset, cần xử lý reset trước khi tính tốc độ tăng/giảm. Tổng rollback tăng có thể do số transaction tăng; nên đối chiếu throughput và lỗi theo nghiệp vụ.

### 8.4. Query plan

Nếu thay index/query/ORM config, đối chiếu truy vấn thật:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Query giả định bảng có các cột này. `EXPLAIN ANALYZE` **thực thi SQL**; tránh chạy vô điều kiện với UPDATE/DELETE trên production. Đánh giá actual rows, loops, sort, buffer reads và thời gian, không chỉ xem index có tên như mong muốn.

## 9. Replication, WAL và bảo vệ dữ liệu sau thay đổi

### 9.1. Kiểm tra replica từ primary

~~~sql
SELECT application_name,
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
~~~

Đừng đồng nhất **WAL đã gửi**, **đã ghi ở standby**, **đã flush** và **đã replay**. Những cột lag có thể là NULL và không phải phép đo trực tiếp “nếu failover ngay sẽ mất đúng N giây”.

Với replication async, primary có thể ACK commit trước khi standby nhận đủ WAL. Với synchronous replication được cấu hình đúng, primary có thể chờ ACK của standby theo mức `synchronous_commit` và topology; đổi lại commit latency tăng và ghi có thể bị chặn khi standby cần thiết không sẵn sàng.

**Bật `synchronous_commit=on` không tự chứng minh zero data loss cho mọi thảm họa.** Cần kiểm tra `synchronous_standby_names`, mức flush/apply, cơ chế promote/fencing và RPO đã được nghiệp vụ chấp thuận.

### 9.2. WAL archive và restore

~~~sql
SELECT archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time
FROM pg_stat_archiver;
~~~

Archiver healthy là tín hiệu, **không thay thế restore drill**: cần base backup hợp lệ, WAL liên tục, quyền truy cập, khóa giải mã và khả năng phục hồi tới mốc cần thiết.

Nếu thay cấu hình làm suy giảm độ bền, rollback về tham số cũ **không tái tạo dữ liệu đã mất**. Đây là thay đổi chính sách RPO, không chỉ là tối ưu hóa latency.

## 10. Java 17: kiểm tra cấu hình tại startup

Một số lỗi có thể chặn ngay thay vì đợi production chịu hậu quả. Ví dụ sử dụng Java record:

~~~java
import java.time.Duration;

public record PersistenceSettings(
        int maxReplicas,
        int maxPoolPerReplica,
        int appConnectionBudget,
        Duration poolWait,
        Duration requestDeadline) {

    public PersistenceSettings {
        if (maxReplicas <= 0 || maxPoolPerReplica <= 0
                || appConnectionBudget <= 0) {
            throw new IllegalArgumentException(
                    "Connection capacity configuration must be positive");
        }
        if (poolWait == null || requestDeadline == null
                || poolWait.isZero() || poolWait.isNegative()
                || requestDeadline.isZero()
                || requestDeadline.isNegative()) {
            throw new IllegalArgumentException(
                    "Timeouts must be positive");
        }
        if (poolWait.compareTo(requestDeadline) >= 0) {
            throw new IllegalArgumentException(
                    "Pool wait must leave time for SQL and response");
        }

        long potential = (long) maxReplicas * maxPoolPerReplica;
        if (potential > appConnectionBudget) {
            throw new IllegalArgumentException(
                    "Potential pool capacity exceeds approved DB budget");
        }
    }
}
~~~

Đây là guard ở mức **giả định capacity**:

- `maxReplicas` phải phản ánh autoscaling và surge deployment, không chỉ số instance hiện tại.
- `appConnectionBudget` phải trừ tài nguyên dành cho service khác, admin, monitoring và headroom.
- Nếu ứng dụng có nhiều datasource/pool, phải cộng đúng.
- Phải tính cả socket/statement/transaction timeouts và retry budget ngoài phép so sánh đơn giản.
- Record không nên chứa password/token hoặc bị log toàn bộ nếu có dữ liệu nhạy cảm.

Một service nên **fail closed** khi thiếu credential hoặc DB endpoint bắt buộc; không fallback sang production nếu profile dev bị thiếu cấu hình.

### 10.1. Readiness và liveness

- **Liveness:** tiến trình còn hoạt động và có cần restart không? Không nên cho một database outage tạm thời tạo vòng restart vô tận gây thêm tải.
- **Readiness:** instance có đủ điều kiện phục vụ traffic theo hợp đồng hay chưa? Có thể fail khi DB/schema bắt buộc không tương thích.
- **Startup:** trong giai đoạn khởi động, tránh kill instance vì một bước khởi tạo hợp lệ chưa hoàn tất.

`SELECT 1` chỉ chứng minh một truy vấn đơn giản thành công tại thời điểm đó; nó không chứng minh ghi có thể commit, migration tương thích, RLS đúng hay replica mới nhất.

## 11. Smoke test JDBC đọc an toàn

Sau triển khai, một kiểm tra ít rủi ro nên bắt đầu ở đường **read-only**, từ datasource thực tế của service:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DatabaseSmokeCheck {
    public static void verify(DataSource dataSource)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement readOnly =
                             connection.prepareStatement(
                                     "SET TRANSACTION READ ONLY")) {
                    readOnly.execute();
                }

                try (PreparedStatement statement =
                             connection.prepareStatement("""
                                SELECT current_database(),
                                       current_user,
                                       current_setting('transaction_isolation')
                                """);
                     ResultSet rows = statement.executeQuery()) {
                    if (!rows.next()) {
                        throw new SQLException(
                                "Database did not return metadata");
                    }
                    if (rows.getString(1) == null
                            || rows.getString(2) == null) {
                        throw new SQLException(
                                "Database identity missing");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đây là ví dụ kiểm tra truy cập/metadata, **không phải test đường ghi**. Trong triển khai thực:

- So sánh `current_database()` và `current_user` với allowlist đã phê duyệt theo environment.
- Không in username/password hoặc dữ liệu khách hàng vào log.
- Kiểm tra schema revision và các query nghiệp vụ cần thiết qua role ứng dụng thật.
- Nếu transaction do Spring quản lý, tránh tạo transaction JDBC độc lập xung đột trong cùng workflow.

Nếu cần smoke test **ghi**, dùng staging hoặc tenant synthetic được phép: tạo request key độc lập, kiểm tra commit bằng connection mới và đảm bảo cleanup/idempotency. Không tự tạo đơn hàng thật hoặc chạm vào số dư khách hàng để thử production.

## 12. Trình tự triển khai theo các gate

### 12.1. Giai đoạn trước triển khai

1. Viết mục đích và expected outcome, owner, phạm vi service/region/tenant.
2. Chụp baseline SLO: p95/p99 read/write/commit, error, pool wait, connection/lock/I/O, business success.
3. Phân loại rủi ro về transaction, isolation, durability/RPO, RLS và schema.
4. Xem diff config, thứ tự ưu tiên nguồn, kiểu activation (restart/reload/session) và đơn vị.
5. Tính connection budget ở autoscaling tối đa và surge.
6. Chạy integration/concurrency/fault tests ở staging; kiểm tra code/schema compatibility.
7. Xác nhận backup/WAL/restore health cho thay đổi rủi ro cao.
8. Chuẩn bị rollback/forward-fix có điều kiện và runbook.
9. Xác định canary scope, thời gian quan sát và **ngưỡng abort cụ thể**.
10. Xác minh quyền triển khai production, secret handling và audit.

### 12.2. Canary và rollout từng phần

~~~text
100% instances ở revision R1
            |
            v
Deploy 1 canary revision R2
            |
   +--------+---------+
   |                  |
Effective OK?       FAIL -> PAUSE/ROLLBACK
   |
Smoke & invariants OK?
   |
SLO vs baseline/control group OK?
   |
25% -> 50% -> 100%
 (mỗi bước có gate)
~~~

Không phải mọi DB setting đều canary được theo pod: tham số instance-level, restart DB hoặc replication topology có thể ảnh hưởng cả cluster. Khi đó cần thử shadow/lab, standby hoặc kế hoạch maintenance có điều kiện thay thế.

Canary phải có traffic đại diện. Một batch job chạy mỗi đêm không được xem là đã kiểm thử chỉ vì canary 10 phút ban ngày không có lỗi.

### 12.3. Sau mỗi bước rollout

- Xác minh phiên bản và cấu hình effective của **từng nhóm instance**.
- Xác minh DB role, environment, schema revision, isolation/timeout theo session.
- Theo dõi p95/p99, error classes, pool active/idle/pending, lock wait và transaction age.
- So sánh query count, plan và DB CPU/I/O/WAL với baseline phù hợp.
- Kiểm tra read/write correctness: unique request, stock, tenant scope và transaction outcome.
- Đánh giá replica lag/archiver nếu thay đổi ảnh hưởng độ bền/đọc.
- Quyết định **PROMOTE**, **PAUSE**, hoặc **ROLLBACK** theo tiêu chí đã định.
- Lưu evidence và tiếp tục theo dõi qua peak/batch cycle có ý nghĩa.

Một dashboard “màu xanh” không thay thế bằng chứng **đúng dữ liệu**.

## 13. Metrics cần thu và cách diễn giải

### 13.1. Ứng dụng Java/JDBC

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Error/success rate theo endpoint và revision | Có lỗi mới riêng ở canary? |
| p50/p95/p99 API và commit latency | Tail latency có tăng dù average giảm? |
| Pool active, idle, pending, max | Có saturation, queueing hay leak? |
| Time-to-acquire connection | Đúng mục tiêu của change pool? |
| Query count mỗi request | N+1 hoặc query path mới? |
| Transaction duration/rollback | Có transaction dài/lỗi? |
| SQLSTATE nhóm `08`, `23`, `40`, `57` | Kết nối, ràng buộc, concurrency, cancellation |
| Retry attempts, unknown COMMIT | Có retry storm hoặc ghi trùng? |
| Idempotency conflict và duplicate side effects | Safety của ghi |
| Read-after-write mismatch | Ảnh hưởng cache/replica consistency |
| Tenant authorization/RLS failures | Sai scope, role hoặc session context |

### 13.2. PostgreSQL/hạ tầng

- Sessions theo trạng thái, backend wait, lock và deadlocks.
- Query duration, buffer read/hit, sort spill, I/O latency.
- WAL generation/flush/archive, replication sent/write/flush/replay.
- CPU, memory, disk capacity và network errors.
- Long transaction, idle-in-transaction, autovacuum và DDL lock.
- Failover/switchover và timeline/leader nếu triển khai HA.

Không so một con số tổng hợp giữa hai khoảng traffic khác biệt rồi tự kết luận causality. Canary nên so với nhóm control trong cùng điều kiện, phân tách theo operation và khu vực.

### 13.3. Bảo vệ telemetry

Không đặt `request_key`, user ID, email, SQL raw chứa literal hoặc secret vào label metrics có cardinality cao. Dùng metadata ít biến động: service, region, environment, revision, operation type. Trace/log chi tiết phải có quyền, retention, redaction và sampling phù hợp.

Cache hit ratio cao có thể đi kèm stale data; HTTP 200 có thể chỉ nghĩa yêu cầu được nhận, không phải giao dịch đã commit. **Chỉ số phải phản ánh hợp đồng thực sự của nghiệp vụ.**

## 14. Ví dụ end-to-end: thay đổi pool để sửa độ trễ

Giả định:

- 12 replicas của order-service.
- Pool cũ tối đa 10, pool mới tối đa 20.
- Thời gian chờ connection p99 khoảng 900 ms.
- Đội muốn giảm `connectionTimeout` từ 2.000 ms xuống 1.000 ms.
- Mục tiêu không tăng tỷ lệ lỗi/độ trễ checkout.

### 14.1. Preflight

~~~text
Trần connections trước = 12 × 10 = 120
Trần connections sau   = 12 × 20 = 240

Kiểm tra:
  DB connection budget sau khi trừ headroom
  pool phụ, migration, monitoring và autoscaling surge
  SQL/lock/I/O có phải nguyên nhân gốc?
  transaction có giữ connection khi gọi hệ ngoài?
  timeout/retry có gây unknown COMMIT và ghi trùng?
~~~

### 14.2. Kỳ vọng tại canary

~~~text
Connection wait p95/p99: giảm có ý nghĩa
Pool pending: không tăng
DB lock wait: không tăng ngoài ngưỡng
SQLSTATE 08xxx / 40xxx: không tăng bất thường
Checkout p99: trong SLO
Duplicate request effects: không tăng
DB sessions: trong budget
Replication/backup: không suy giảm
~~~

Nếu pool pending giảm nhưng DB lock wait và checkout p99 tăng, phải **pause hoặc rollback** dù chỉ số pool nhìn tốt. Có thể cần tối ưu SQL, rút ngắn transaction hoặc giới hạn concurrency thay vì thêm connection.

### 14.3. Kết luận sau rollout

Chỉ khi toàn bộ instance áp dụng đúng revision, các gate đạt, smoke test không có bất biến bị phá và đã quan sát đủ chu kỳ tải, mới đóng change record. Nếu còn batch job đêm hoặc traffic hiếm chưa chạy, ghi **rủi ro còn lại và thời điểm kiểm tra tiếp**, không tuyên bố mọi tình huống đã được kiểm chứng.

## 15. Rollback không luôn khôi phục dữ liệu đã bị ảnh hưởng

| Thay đổi | Đưa config cũ trở lại có đủ không? | Điều kiện bổ sung |
| --- | --- | --- |
| Pool size | Thường có thể | Pool phải thực áp giá trị cũ, DB không còn saturation |
| Statement timeout | Thường có thể | Query/transaction đang chạy đã thất bại cần xử lý |
| Isolation level | Không tự đảo giao dịch đã commit | Kiểm tra correctness và lỗi concurrency |
| Read routing sang replica | Không tự xóa cache stale | Read-your-writes, invalidation và version |
| `synchronous_commit` làm giảm bảo vệ | **Không** tạo lại commit đã mất | RPO, đối soát và restore evidence |
| Schema `DROP COLUMN` | **Không** tự khôi phục cột/dữ liệu | Migration tiến về trước hoặc restore có kiểm soát |
| RLS policy lỗi | Không thu hồi dữ liệu đã lộ | Security incident response và audit |
| Key rotation | Có thể cần giai đoạn chuyển tiếp | Đúng key, certificate, permission và re-encryption |
| Failover/promote primary | Không chỉ đổi hostname là xong | Fencing, WAL history và rejoin/rebuild |

**Rollback code ≠ rollback config ≠ rollback schema ≠ rollback data.** Một transaction đã commit hoặc một event đã gửi ra ngoài không tự đảo ngược khi deployment quay về revision cũ.

Với schema dùng nhiều phiên bản ứng dụng, triển khai theo **expand–contract**. Chỉ xóa cột/bảng cũ khi không còn code/consumer phụ thuộc, hết cửa sổ rollback và đã kiểm chứng dữ liệu.

## 16. Bảo mật và phân tách tenant khi thay đổi cấu hình

Một deployment có thể đạt mọi chỉ số performance mà vẫn sai về bảo mật. Phải kiểm tra:

1. **Môi trường:** staging không kết nối/gửi event vào production ngoài quy trình đặc biệt.
2. **Identity:** đúng DB role có quyền tối thiểu; không dùng superuser hoặc `BYPASSRLS` cho traffic ứng dụng.
3. **Tenant scope:** tenant ID do lớp xác thực/ủy quyền cấp; SQL, JOIN, cache key, event đều dùng đúng scope.
4. **Pool reuse:** transaction-local tenant setting được reset khi commit/rollback; request B không thừa hưởng setting tenant A.
5. **TLS:** không bỏ xác thực chứng chỉ server để xử lý lỗi kết nối tức thời.
6. **Secrets:** secret version được rollout đúng; không in password/token/private key.
7. **Audit:** thay RLS/role/credential có owner, thời điểm, change ID và reviewer.

### 16.1. Đổi password không chỉ là đổi một biến

Một quá trình rotation an toàn thường gồm:

~~~text
Tạo credential mới, cấp quyền tối thiểu
     |
Deploy canary dùng secret version mới
     |
Xác nhận new connections/TLS/role đúng
     |
Rollout toàn bộ service và worker
     |
Đợi/đóng connection cũ theo chính sách
     |
Thu hồi credential cũ
     |
Audit + xác minh không có client còn dùng secret cũ
~~~

Không thu hồi credential cũ ngay khi secret manager được cập nhật nếu process chưa refresh hoặc pool còn connection cũ; cũng không để hai credential còn hiệu lực quá thời gian được phép.

## 17. Test hậu triển khai theo mức rủi ro

### 17.1. Read-only smoke

Dùng runtime datasource/role thật để kiểm tra:

- Connection tới đúng database và environment.
- Schema migration revision hợp lệ.
- Query đọc tối thiểu hoạt động trong deadline.
- Session isolation/timeouts theo mong đợi.
- Quyền truy cập dữ liệu tổng hợp/fixture được cấp phép.

Một `SELECT 1` thành công **không chứng minh** mọi đường ghi/transaction/RLS đều đúng.

### 17.2. Write-path smoke

Trong staging hoặc tenant synthetic được phê duyệt:

1. Tạo idempotency key riêng cho phép thử.
2. Ghi một nghiệp vụ thử qua transaction thực, theo đúng constraint.
3. Mở connection mới để kiểm tra commit.
4. Retry cùng key, xác nhận không bị ghi trùng.
5. Thử rollback với failure injection đã được cho phép.
6. Xóa fixture và đối soát event/outbox, không tạo side effect thật.

Không chèn đơn hàng, thanh toán hoặc stock khách thật chỉ để kiểm tra production.

### 17.3. Concurrency/fault tests

Các tình huống có rủi ro cao:

- Hai request cùng tranh chấp stock → không âm.
- Retry sau mất ACK COMMIT → không tạo đơn/giao dịch trùng.
- Deadlock hoặc `40001` → rollback/retry toàn transaction có giới hạn.
- Pool exhausted → xử lý lỗi có kiểm soát, không retry storm.
- Replica lag → API có read-your-writes không đọc lùi.
- Tenant context tái dùng connection → không rò dữ liệu.
- Failover → không split-brain; RPO đúng fault model.

Test kill DB/cắt mạng phải ở lab/staging được phép, không tự động chạy trên production.

## 18. Decision gate: promote, pause hay rollback?

| Gate | Promote khi | Pause/rollback khi |
| --- | --- | --- |
| Effective config | Canary và rollout cohort dùng revision mong muốn | Cấu hình lệch hoặc sai DB |
| Error rate | Trong ngưỡng SLO đã định | Pool/SQL/HTTP lỗi tăng vượt ngưỡng |
| Latency | p95/p99 operation đạt budget | Tail latency tăng có ý nghĩa |
| Pool/DB capacity | Chưa vượt connection, CPU, lock budget | Saturation, transaction bị kẹt |
| Data correctness | Constraint, idempotency và tenant tests đạt | Ghi trùng, stock âm, cross-tenant leak |
| Recovery | WAL/backup/replication đạt mục tiêu | Khả năng bảo vệ commit suy giảm |
| Schema | Code/schema tương thích | Missing column, DDL lock không kiểm soát |
| Security | Role/TLS/RLS và secret scope đúng | Quyền vượt mức hoặc dữ liệu lộ |

Ngưỡng thực phải được lượng hóa trước deploy và có người chịu trách nhiệm quyết định. Nếu monitoring hỏng, sample quá ít hoặc canary không có workload tương ứng, **không coi im lặng là thành công**; dừng và điều tra cho tới khi đủ bằng chứng.

Một SLO tổng thể có thể che tenant hoặc endpoint quan trọng bị lỗi. Cần phân tách theo service version, operation, region và tenant group khi thích hợp.

## 19. Runbook khi change không đạt

~~~text
Gate bị vi phạm
      |
      v
DỪNG rollout, giữ phạm vi nhỏ
      |
      v
Lưu config revision, thời điểm và evidence
      |
      v
Có nguy cơ sai/lộ/mất dữ liệu?
    /                          \
   Có                           Không
    |                             |
    v                             v
Chặn write nguy hiểm,         Rollback config/code
đối soát và incident          theo kế hoạch
    |                             |
    +--------------+--------------+
                   |
                   v
        Kiểm tra effective state mới
                   |
                   v
        Smoke + metrics + bất biến dữ liệu
                   |
                   v
          Ghi kết luận và bài học
~~~

Nếu từng có rò dữ liệu tenant hoặc mất commit do replication, rollback **không đủ** để đóng sự cố. Cần điều tra phạm vi, audit, đối soát và khôi phục theo runbook.

### 19.1. Gói bằng chứng sau thay đổi

Một báo cáo hậu triển khai nên chứa:

- Change ID, owner, reviewer, thời gian triển khai và quyết định.
- Artifact/code revision, config revision, secret version identifier không nhạy cảm.
- Phạm vi instance, region, database, role và migration version.
- Config desired so với effective có dấu thời gian.
- Baseline và post-change SLI/SLO trên workload tương đương.
- SQL/DB metrics phù hợp, trạng thái WAL/replica/backup khi liên quan.
- Kết quả smoke và test dữ liệu, kèm phạm vi chưa kiểm thử.
- Action promote/pause/rollback và trạng thái sau đó.
- Rủi ro còn lại, corrective actions và người theo dõi.

Không lưu password, SQL chứa PII, token hoặc raw request body trong report dùng chung.

## 20. Những ngộ nhận thường gặp

**“YAML đã merge nghĩa là production dùng đúng giá trị.”** Một số process chưa restart hoặc session override vẫn có thể giữ giá trị cũ.

**“Pod ready nghĩa là persistence đúng.”** Health probe không chứng minh transaction, RLS, dữ liệu hay durability.

**“Tăng Hikari pool luôn tăng throughput.”** Database có thể nghẽn lock, CPU, I/O hoặc query plan.

**“max_connections có thể tăng vô hạn.”** Mỗi backend có tài nguyên tiêu thụ và giới hạn vận hành.

**“Timeout của pool là timeout toàn truy vấn.”** Pool, connect, socket, statement, lock và transaction là các giới hạn khác nhau.

**“SQLException khi COMMIT nghĩa là commit đã rollback.”** Mất phản hồi tạo trạng thái chưa rõ; cần idempotency/đối soát.

**“pg_settings của một session cho biết cấu hình mọi node.”** Các session và node có thể có override/version khác nhau.

**“Replication lag gần 0 luôn có RPO=0.”** Cần xác định WAL bền, standby được promote và fault model.

**“EXPLAIN ANALYZE vô hại với mọi SQL.”** Nó thực thi truy vấn, kể cả DML.

**“Canary xanh trong vài phút chứng minh batch đêm an toàn.”** Chưa có workload nghĩa là chưa có bằng chứng.

**“Rollback code cũng hoàn tác dữ liệu.”** Schema, commit, event và side effect có vòng đời riêng.

**“RLS đã bật thì khỏi kiểm tra tenant context.”** Wrong role/session/connection reuse vẫn có thể tạo lỗi.

**“HTTP 200 và hit ratio cao chứng minh dữ liệu mới.”** Cache có thể stale; 200 có thể chỉ là tiếp nhận request.

**“Chỉ cần đo CPU/latency sau deploy.”** Phải đo cả business invariants, quyền, transaction và khả năng phục hồi.

## 21. Bài tập vận dụng

**Bài 1 — desired/effective.** Git khai báo pool=20, nhưng A dùng 20, B dùng 10 và C crash-loop. Hãy đề xuất cách đo trạng thái từng instance và quyết định có được promote hay không.

**Bài 2 — budget.** Cluster có autoscaling tối đa 18 instance, mỗi instance có read pool 12 và write pool 8. Tính tổng trần connection, đề xuất headroom với DB giới hạn do bài tập tự chọn, và lưu ý rolling deployment surge.

**Bài 3 — timeout.** HTTP deadline 3 giây, pool wait 2,5 giây, statement timeout 5 giây và socket timeout 30 giây. Chỉ ra vì sao client có thể timeout trước khi DB hoàn tất, và nêu cơ chế kiểm soát retry/unknown COMMIT.

**Bài 4 — PostgreSQL config.** Trên PostgreSQL lab, đổi `statement_timeout` ở session A, mở session B; dùng `pg_settings` và `current_setting` giải thích vì sao hai connection thấy khác nhau.

**Bài 5 — canary pool.** Tăng pool làm pending giảm 80% nhưng lock wait và p99 checkout tăng. Hãy chọn pause/rollback/promote và đề xuất các query chẩn đoán.

**Bài 6 — durability.** Một thay đổi `synchronous_commit` cải thiện latency nhưng giảm bảo vệ khi mất primary. Xác định điều kiện review RPO, metrics WAL/replica và fault injection test.

**Bài 7 — secret rotation.** Thiết kế rollout đổi password PostgreSQL với 20 instance, pooled connections và rollback window. Làm sao chứng minh instance dùng credential mới mà không log password?

**Bài 8 — RLS.** Sau deploy, tenant B trả danh sách rỗng còn tenant A bình thường. Kiểm tra setting transaction-local, role, pool, RLS và authorization mà không tắt RLS.

**Bài 9 — migration.** Code mới dùng cột `shipping_note`, code cũ dùng `delivery_note`. Dùng expand–contract để thiết kế rolling deployment và chỉ ra mốc không thể rollback về code cũ an toàn.

**Bài 10 — runbook.** Viết change record cho việc giảm `lock_timeout`, gồm mục tiêu, baseline, SQLSTATE kỳ vọng, canary, abort rule, effective config và hậu kiểm.

**Bài 11 — incident dữ liệu.** Một cấu hình sai làm service ghi dữ liệu sang tenant khác trong 5 phút nhưng HTTP error rate không tăng. Hãy nêu bước chặn ảnh hưởng, đối soát, khôi phục và audit.

**Bài 12 — evidence.** Thiết kế một báo cáo sau triển khai có desired/effective config, artifact/schema version, metrics, test result, RPO/backup health và quyết định cuối; xác định trường nào phải redaction.

## Ghi nhớ

**Quản lý cấu hình persistence là quản lý thay đổi hành vi của cả hệ thống, không chỉ cập nhật một file.** Giá trị mong muốn có thể khác giá trị thực có hiệu lực do restart, session override, secret, drift hoặc rollout không đồng đều. Thay đổi pool, timeout, isolation, replica, cache, schema hay RLS đều có thể ảnh hưởng tốc độ, đúng dữ liệu và khả năng phục hồi.

Một thay đổi đáng tin cần có **mục tiêu rõ, baseline, phân tích rủi ro, triển khai từng phần, xác minh effective state, kiểm tra bất biến và ngưỡng dừng**. Sau triển khai, lưu bằng chứng về phiên bản, cấu hình, SQL/metrics, SLO, security và RPO; rollback khi có thể, dùng forward-fix/đối soát khi dữ liệu đã thay đổi. Chỉ tuyên bố hoàn thành khi **hành vi thực và cam kết nghiệp vụ đã được xác minh**, không chỉ khi công cụ triển khai báo thành công.
