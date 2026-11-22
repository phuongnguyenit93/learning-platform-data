# Chế độ hoạt động hạn chế và cửa sổ bảo trì

Một hệ thống PostgreSQL production cần có cách tiếp tục phục vụ trong lúc vận hành viên bảo trì database, hệ điều hành, storage hoặc ứng dụng. Có những thay đổi chỉ cần reload cấu hình; có thay đổi cần restart; có thao tác yêu cầu chặn writes, ngắt sessions hoặc tạm ngừng toàn bộ application traffic. Nếu không chuẩn bị trước, một thao tác quản trị có thể tạo lock waits, connection storms, replication lag, transaction failures hoặc downtime kéo dài hơn dự kiến.

**Chế độ hoạt động hạn chế** là trạng thái trong đó hệ thống chỉ cho phép một tập hoạt động được xác định, chẳng hạn chỉ đọc, chỉ cho một nhóm operator truy cập, tạm dừng writes hoặc chỉ nhận health checks. **Cửa sổ bảo trì** là khoảng thời gian được lập kế hoạch để thực hiện thay đổi có ảnh hưởng đến availability, performance hoặc data safety. Hai khái niệm liên quan nhưng không giống nhau: maintenance window là lịch và quy trình điều phối; restricted mode là trạng thái kỹ thuật được áp dụng trong khoảng thời gian đó.

PostgreSQL có nhiều cơ chế hỗ trợ vận hành hạn chế như transaction read-only, default_transaction_read_only, server-level default_transaction_read_only, pg_hba.conf, role privileges, connection limits, hot standby read-only behavior, session termination và controlled restart. Tuy nhiên, một setting đơn lẻ không tạo ra maintenance mode hoàn chỉnh. Ứng dụng có thể còn ghi qua connections đã mở, background workers có thể tiếp tục chạy, scheduled jobs có thể phát sinh transactions và proxy có thể giữ stale endpoints. Vì vậy, maintenance cần được phối hợp ở database, application, network và orchestration layers.

Bài học thuộc chương **Quản trị** của module **Database Engine Relational PostgreSQL**. Nội dung giải thích cách chọn chế độ hạn chế phù hợp, lên lịch và thực hiện maintenance window, bảo vệ consistency, giảm downtime, kiểm soát quyền truy cập, xác nhận phục hồi và diễn tập quy trình.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt maintenance window, restricted mode, read-only mode và full outage.
- Chọn chế độ hạn chế theo loại thao tác quản trị.
- Hiểu transaction read-only, default_transaction_read_only và role privileges.
- Kiểm soát admission của ứng dụng, connections và background jobs.
- Drain traffic và sessions trước thay đổi có rủi ro.
- Phân biệt reload, restart, switchover và failover.
- Lập kế hoạch DDL, index maintenance, vacuum, backup và upgrades.
- Bảo vệ replication, WAL archive và recovery path trong maintenance.
- Xác định preconditions, stop conditions, rollback và validation.
- Điều phối maintenance qua application, DBA, infrastructure và business teams.
- Đo downtime, maintenance duration, RPO/RTO và user impact.
- Xây dựng runbook, thông báo, checklist và lab thực hành.

## 2. Maintenance window là gì?

Maintenance window là khoảng thời gian được phê duyệt để thực hiện các hoạt động quản trị có thể ảnh hưởng tới service.

### 2.1. Planned maintenance

Các thay đổi đã biết trước như minor version update, OS patch, storage migration, schema migration, certificate rotation hoặc cấu hình cần restart.

### 2.2. Emergency maintenance

Thay đổi cần thực hiện sớm vì security vulnerability, disk exhaustion, corruption risk hoặc lỗi production. Có thể không có thời gian thông báo đầy đủ, nhưng vẫn cần decision record và stop conditions.

### 2.3. Maintenance window không đồng nghĩa downtime

Một số công việc có thể thực hiện online như tạo index concurrently, analyze, một số schema changes hoặc rolling maintenance trên HA cluster. Window có thể là khoảng thời gian kiểm soát rủi ro thay vì ngừng service.

### 2.4. Scope và ownership

Mỗi window cần nêu hệ thống, databases, nodes, applications, regions, owners, dependencies và những thao tác được phép.

### 2.5. Entry và exit criteria

Entry criteria xác nhận hệ thống đủ điều kiện bắt đầu. Exit criteria xác nhận database, replication, application và monitoring đã trở lại trạng thái chấp nhận được.

## 3. Chế độ hoạt động hạn chế

Restricted mode giới hạn một hoặc nhiều loại hoạt động trong thời gian có mục tiêu cụ thể.

| Chế độ | Hành vi chính | Trường hợp dùng |
|---|---|---|
| Read-only | Cho phép reads, từ chối writes theo transaction policy | Reporting, cutover, bảo vệ dữ liệu |
| Application maintenance | App từ chối requests hoặc chỉ cho maintenance endpoint | Schema/data migration |
| Restricted access | Chỉ operator/role/network được kết nối | Emergency repair |
| Drained | Không nhận request mới, chờ request hiện tại hoàn tất | Switchover/restart |
| Quiesced writes | Dừng writers/jobs, giữ reads nếu an toàn | Backup/cutover/DDL |
| Offline | Không phục vụ clients | Restart/upgrade/restore |

### 3.1. Chọn mức hạn chế nhỏ nhất phù hợp

Nếu chỉ cần dừng một batch job, không cần đưa toàn database offline. Giảm scope giúp hạn chế business impact.

### 3.2. Chế độ phải có owner

Một người hoặc controller phải chịu trách nhiệm bật/tắt restricted mode, ghi thời điểm và xác nhận kết quả.

### 3.3. Chế độ phải có thời hạn

Maintenance mode bị quên bật có thể làm service unavailable lâu hơn dự kiến. Đặt expiration/alert và quy trình kiểm tra sau window.

### 3.4. Phân biệt access restriction với data protection

Chặn application connections không bảo vệ khỏi operator role hoặc background processes còn chạy. Data protection cần privileges, transaction controls và backup.

### 3.5. Không có một switch maintenance mode chung cho mọi PostgreSQL

PostgreSQL cung cấp các primitives riêng; application/proxy/orchestrator thường cung cấp admission/drain behavior. Runbook phải phối hợp chúng.

## 4. Transaction read-only

PostgreSQL hỗ trợ transaction read-only để cấm phần lớn thao tác ghi trong transaction đó.

~~~sql
BEGIN READ ONLY;

SELECT count(*)
FROM public.orders;

COMMIT;
~~~

### 4.1. SET TRANSACTION READ ONLY

Có thể đặt mode cho transaction hiện tại ngay sau BEGIN, trước khi thực hiện statement khác.

~~~sql
BEGIN;
SET TRANSACTION READ ONLY;
SELECT now();
COMMIT;
~~~

### 4.2. Read-only không phải read-only snapshot toàn cluster

Transaction chỉ có semantics read-only theo PostgreSQL. Nó không chặn các session khác ghi vào primary.

### 4.3. Những thao tác bị giới hạn

Read-only transaction từ chối các thao tác ghi thông thường và nhiều lệnh có side effects. Một số thao tác quản trị/temporary objects có rules riêng; kiểm tra tài liệu theo version và command cụ thể.

### 4.4. Consistency của reads

Transaction read-only vẫn dùng snapshot isolation semantics của transaction isolation level. READ COMMITTED có thể thấy snapshot mới ở mỗi statement; REPEATABLE READ giữ snapshot nhất quán trong transaction.

### 4.5. Không dùng read-only như security boundary duy nhất

Một client có thể mở transaction khác hoặc kết nối bằng role khác. Dùng role privileges và connection policy để enforce access.

## 5. default_transaction_read_only

Setting này đặt default transaction mode cho sessions mới hoặc transaction chưa được chỉ định mode khác.

~~~sql
SHOW default_transaction_read_only;

SET default_transaction_read_only = on;
~~~

### 5.1. Session-level setting

SET thay đổi setting trong session hiện tại. Có thể dùng để kiểm thử hoặc cho một connection pool riêng.

### 5.2. Role/database defaults

ALTER ROLE hoặc ALTER DATABASE ... SET có thể đặt default cho sessions của role/database tương ứng. Điều này hữu ích cho reporting users.

~~~sql
ALTER ROLE reporting_user
SET default_transaction_read_only = on;
~~~

### 5.3. Server-level default

postgresql.conf có thể đặt default_transaction_read_only cho toàn server. Thay đổi thường có thể reload; kiểm tra context trong pg_settings và version.

### 5.4. Không phải absolute write lock

Superusers và một số privileged contexts có thể thay đổi setting hoặc thực hiện các thao tác đặc biệt. Role privileges vẫn là lớp bảo vệ cần thiết.

### 5.5. Kiểm tra hiệu lực

Kết nối bằng đúng application role, chạy SHOW default_transaction_read_only và thử một thao tác write trong test transaction. Không kiểm tra chỉ bằng admin account.

## 6. Role privileges và read-only users

Database privileges là lớp enforcement bền vững hơn việc chỉ dựa vào client convention.

### 6.1. Tạo role đọc

~~~sql
CREATE ROLE reporting_reader
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOINHERIT;
~~~

Thiết kế role membership theo quyền thực tế và policy của môi trường.

### 6.2. Cấp CONNECT và schema usage

~~~sql
GRANT CONNECT ON DATABASE appdb TO reporting_reader;
GRANT USAGE ON SCHEMA reporting TO reporting_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting
TO reporting_reader;
~~~

### 6.3. Default privileges

Để tables tạo trong tương lai có quyền đọc phù hợp, cấu hình default privileges dưới role tạo objects:

~~~sql
ALTER DEFAULT PRIVILEGES
IN SCHEMA reporting
GRANT SELECT ON TABLES TO reporting_reader;
~~~

Default privileges gắn với object-creating role; cần cấu hình cho từng owner thích hợp.

### 6.4. Thu hồi quyền ghi

Không cấp INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER hoặc sequence privileges nếu role không cần. Kiểm tra inherited role memberships và PUBLIC grants.

### 6.5. Role không thay thế network controls

Một role chỉ bảo vệ database authorization. Kết hợp pg_hba.conf, TLS, network allowlists và secret management.

## 7. Read-only standby và primary read-only

Hot standby trong recovery state vốn chỉ cho phép read-only queries. Đây là behavior khác với đặt default_transaction_read_only trên một primary đang chạy.

### 7.1. Hot standby

Standby có thể phục vụ SELECT khi hot_standby được bật và recovery cho phép queries. Writes thông thường bị từ chối.

### 7.2. Primary read-only policy

Primary vẫn là writable node về mặt role, nhưng có thể được cấu hình/điều phối để ứng dụng chỉ thực hiện reads. Cần enforcement rõ ràng ở database/application layer.

### 7.3. Promotion changes behavior

Khi standby được promote, nó trở thành primary và không còn tự động read-only theo recovery semantics. Nếu muốn giữ read-only, cần policy riêng.

### 7.4. Recovery conflicts

Read queries trên standby có thể xung đột với WAL replay. Maintenance/read-only workload dài cần xem max_standby delays và hot_standby_feedback trade-offs.

### 7.5. Replica lag

Read-only không có nghĩa dữ liệu mới nhất. Trước khi cutover hoặc validation, kiểm tra replay progress và consistency requirements.

## 8. Application maintenance mode

Application layer thường là nơi tốt nhất để từ chối writes có thông báo thân thiện và ngăn jobs phát sinh transactions mới.

### 8.1. Admission control

API gateway/service có thể trả maintenance response cho requests mới, trong khi health checks và operator endpoints vẫn hoạt động.

### 8.2. Read-only application mode

Ứng dụng có thể cho phép GET/query endpoints nhưng từ chối commands thay đổi dữ liệu. Cần kiểm tra cả endpoints phụ, GraphQL mutations, admin tools và internal APIs.

### 8.3. Background workers

Tạm dừng queue consumers, schedulers, cron jobs, ETL, event handlers và retry workers. Một API đã read-only nhưng worker vẫn ghi có thể phá maintenance plan.

### 8.4. Idempotency và queue retention

Giữ jobs ở queue thay vì drop. Đảm bảo retries sau window idempotent và có thể xử lý backlog.

### 8.5. User communication

Trả maintenance status/code có thể retry, hiển thị expected window và hướng dẫn thao tác. Không để client retry liên tục gây traffic storm.

## 9. Draining traffic và sessions

Drain là ngừng nhận công việc mới và cho công việc đang chạy hoàn tất có kiểm soát.

### 9.1. Stop admission trước

Đưa gateway/service vào maintenance state hoặc remove node khỏi load balancer trước khi thay đổi database.

### 9.2. Drain in-flight requests

Chờ requests đang xử lý hoàn tất trong một deadline. Requests vượt deadline phải được cancel/return retryable error theo policy.

### 9.3. Stop writers and workers

Pause writers, scheduled tasks, consumers và integration jobs. Kiểm tra các service accounts có thể ghi trực tiếp vào database.

### 9.4. Drain connection pools

Pooler/app nên ngừng mở connections mới tới node sắp bảo trì và đóng/recycle connections theo kế hoạch. Connection idle vẫn có thể giữ session state.

### 9.5. Xác nhận không còn writers

Kiểm tra pg_stat_activity, application metrics và logs. Một số maintenance commands cần sessions khác đã kết thúc hoặc lock đã được lấy.


## 10. Giới hạn kết nối ở database và role

PostgreSQL có thể giới hạn số connections theo database và role. Đây là công cụ admission control, nhưng không thay thế việc drain sessions hiện có.

### 10.1. CONNECTION LIMIT theo role

~~~sql
ALTER ROLE app_writer CONNECTION LIMIT 0;
~~~

Connection limit 0 ngăn các kết nối mới của role theo cơ chế giới hạn; các sessions đã kết nối không tự bị ngắt.

### 10.2. CONNECTION LIMIT theo database

~~~sql
ALTER DATABASE appdb CONNECTION LIMIT 20;
~~~

Giới hạn áp dụng cho database connections mới và không tính superuser connections theo cùng cách như ordinary roles. Kiểm tra behavior theo version.

### 10.3. ALLOW_CONNECTIONS

~~~sql
ALTER DATABASE appdb WITH ALLOW_CONNECTIONS false;
~~~

Setting này ngăn các kết nối mới tới database. Nó không tự chấm dứt các sessions đang tồn tại.

### 10.4. Kiểm tra sessions còn lại

~~~sql
SELECT pid, usename, application_name, state
FROM pg_stat_activity
WHERE datname = 'appdb';
~~~

Xác định sessions cần giữ lại (operator/monitoring) và sessions phải drain/terminate.

### 10.5. Mở lại connections

~~~sql
ALTER DATABASE appdb WITH ALLOW_CONNECTIONS true;
~~~

Chỉ mở lại sau khi schema/config/data validation và application readiness đạt.

## 11. pg_hba.conf trong restricted access

pg_hba.conf quyết định client authentication/connection admission theo địa chỉ, database, user và phương thức xác thực.

### 11.1. Rule order

PostgreSQL sử dụng rule đầu tiên khớp. Một reject rule đặt sau rule allow rộng có thể không bao giờ được áp dụng.

### 11.2. Chỉ cho operator network

Có thể giới hạn connections vào database trong maintenance bằng rules cụ thể cho operator/bastion subnets và reject các client application networks.

### 11.3. Reload HBA

Sau khi sửa file, reload configuration để đọc rules mới:

~~~sql
SELECT pg_reload_conf();
~~~

### 11.4. HBA không chấm dứt sessions hiện có

Connections đã xác thực trước khi rule thay đổi có thể tiếp tục hoạt động. Cần drain hoặc terminate sessions theo kế hoạch.

### 11.5. Validate rule

Kiểm tra pg_hba_file_rules trên versions hỗ trợ để phát hiện parse errors và thứ tự rules. Giữ một access path đã thử cho operator, tránh khóa chính mình khỏi database.

## 12. Kết hợp restricted mode ở nhiều lớp

Một maintenance mode đáng tin cậy cần nhiều lớp enforcement.

~~~text
Client traffic
     |
     v
API / Gateway admission
     |
     +---- reject new writes
     |
     v
Application workers / schedulers
     |
     +---- pause consumers and jobs
     |
     v
Connection pool / proxy
     |
     +---- drain or block new sessions
     |
     v
PostgreSQL
     |
     +---- role privileges / read-only / connection policy
~~~

### 12.1. Gateway

Chặn requests mới hoặc chỉ cho phép read endpoints/maintenance page. Giữ health checks hoạt động để orchestration không hiểu nhầm maintenance là outage.

### 12.2. Application

Từ chối write commands trong toàn bộ code paths, gồm admin APIs và internal service calls.

### 12.3. Workers

Pause scheduled jobs và consumers; ghi nhận offsets/checkpoints để resume không mất events.

### 12.4. Database

Dùng role privileges, transaction read-only, connection controls và HBA rules theo scope.

### 12.5. Infrastructure

Drain load balancer, thay đổi routing và giới hạn network paths nếu maintenance cần restart/upgrade node.

## 13. Dừng writes mà vẫn giữ reads

Một số maintenance tasks cần ngăn data changes nhưng vẫn cho phép users xem dữ liệu hiện có.

### 13.1. Read-only application mode

Application chuyển sang read-only banner/API behavior. Write requests được từ chối bằng response có thể xử lý/retry theo contract.

### 13.2. Read-only role separation

Ứng dụng đọc dùng reader role; writer role bị disable hoặc không được cấp cho application trong window. Tách pools để operator vẫn truy cập.

### 13.3. Database default read-only

Có thể đặt default_transaction_read_only cho application role/database như defense-in-depth, nhưng privileged users có thể thay đổi setting.

### 13.4. Existing transactions

Transaction write đang mở có thể commit sau khi mode thay đổi nếu không được drain. Cần xác định và kết thúc các in-flight writers trước cutover.

### 13.5. Validate read paths

Test các query critical, views, functions và replicas. Một số functions có side effects hoặc gọi external services dù câu lệnh bên ngoài là SELECT.

## 14. Maintenance với application hoàn toàn offline

Một số thao tác yêu cầu database không có client traffic.

### 14.1. Stop application admission

Đưa gateway vào maintenance, dừng writer services và background jobs.

### 14.2. Stop connection poolers

Drain PgBouncer/proxy pools hoặc chuyển target khỏi node. Giữ một management path đã kiểm soát.

### 14.3. Terminate remaining sessions

Sau khi xác nhận không có critical transaction, có thể terminate client backends còn lại theo database/application scope.

~~~sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'appdb'
  AND pid <> pg_backend_pid()
  AND usename = 'app_writer';
~~~

Đây là thao tác có side effects: sessions bị terminate sẽ rollback transaction. Xem owner/query age trước khi thực hiện.

### 14.4. Keep operator path

Duy trì superuser/break-glass access qua local socket hoặc bastion đã thử. Không chặn toàn bộ admin path cùng lúc.

### 14.5. Xác nhận quiescence

Kiểm tra active sessions, transactions, prepared transactions, replication workers và background jobs. Database không có app sessions vẫn có thể chạy autovacuum/checkpointer.

## 15. Prepared transactions và long-running transactions

Drain không hoàn tất nếu còn transaction state có thể ảnh hưởng maintenance.

### 15.1. Long transactions

Transaction dài có thể giữ locks, snapshots và prevent vacuum cleanup. Kiểm tra xact_start, backend_xmin và query age.

### 15.2. Idle in transaction

Session idle in transaction có thể giữ transaction mở dù không chạy SQL. Xác định application bug/owner trước khi terminate.

### 15.3. Prepared transactions

Two-phase commit có thể để lại prepared transactions sau khi client/coordinator mất kết nối. Kiểm tra pg_prepared_xacts và chỉ commit/rollback theo transaction coordinator/business decision.

### 15.4. Replication slots và logical consumers

Logical replication slots/decoding consumers có thể giữ WAL dù application traffic đã dừng. Xem slot activity và retained WAL.

### 15.5. Maintenance preflight

Trước DDL/restart/upgrade, kiểm tra locks, prepared transactions, replication slots, long snapshots và active backups.


## 16. Reload hay restart?

Không phải mọi thay đổi cấu hình PostgreSQL đều yêu cầu restart. pg_settings.context và documentation theo major version cho biết cách áp dụng.

### 16.1. Reloadable settings

Một số settings có context sighup; thay đổi có thể được áp dụng sau reload.

~~~sql
SELECT pg_reload_conf();
~~~

### 16.2. Restart-required settings

Các settings có context postmaster cần restart server để có hiệu lực. Ví dụ một số memory/process settings như shared_buffers và max_connections.

### 16.3. Kiểm tra context

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'max_connections',
    'work_mem',
    'log_min_duration_statement'
);
~~~

### 16.4. pending_restart

Nếu pending_restart true, setting đã thay đổi nhưng chưa có hiệu lực do cần restart. Không báo maintenance hoàn tất trước khi restart/verify.

### 16.5. Tránh restart không cần thiết

Restart làm disconnect sessions và tạo recovery/reconnect load. Dùng reload khi setting hỗ trợ, nhưng phải xác nhận application behavior.

## 17. Shutdown modes của PostgreSQL

PostgreSQL hỗ trợ các shutdown modes khác nhau qua server control tools.

### 17.1. Smart shutdown

Smart shutdown chờ clients disconnect trước khi dừng. Nếu sessions không tự thoát, shutdown có thể chờ rất lâu.

### 17.2. Fast shutdown

Fast shutdown disconnect clients, abort active transactions và shutdown sạch theo cơ chế server. Đây là cách thường dùng cho controlled restart.

### 17.3. Immediate shutdown

Immediate shutdown dừng ngay mà không shutdown sạch; lần khởi động sau cần crash recovery. Chỉ dùng khi có lý do đặc biệt và hiểu recovery impact.

### 17.4. pg_ctl

pg_ctl cung cấp các chế độ stop/restart và status. Chọn mode theo runbook và service manager; không chạy nhiều control paths cùng lúc.

### 17.5. Verify stopped state

Xác nhận process/service state, socket/port, logs và control-plane status. Một lệnh stop trả thành công cần được đối chiếu với trạng thái thực tế.

## 18. Planned restart và connection storm

Sau restart, hàng nghìn clients có thể reconnect cùng lúc và tạo tải đột biến.

### 18.1. Stagger application startup

Khởi động application instances theo batch hoặc jitter để giảm simultaneous connection attempts.

### 18.2. Pooler warm-up

Khởi động/refresh connection pools theo giới hạn. Kiểm tra authentication, DNS và TLS handshake capacity.

### 18.3. Background jobs

Không resume toàn bộ queues/schedulers ngay khi database process vừa start. Đợi database và downstream dependencies ổn định.

### 18.4. Recovery duration

Crash recovery, WAL replay và startup checks có thể kéo dài. Đặt readiness theo SQL/application checks thay vì process running.

### 18.5. Throttled traffic restoration

Mở traffic từng bước, theo dõi CPU, connections, locks, WAL và p95/p99. Có thể giữ restricted mode lâu hơn để validation.


## 19. DDL trong maintenance window

DDL có thể lấy locks mạnh và làm query production chờ. Cần đánh giá lock mode, table size, transaction duration và version behavior trước khi deploy.

### 19.1. ALTER TABLE

Nhiều ALTER TABLE operations cần ACCESS EXCLUSIVE lock trong ít nhất một giai đoạn. Lock có thể được lấy rất nhanh nếu không có blockers, hoặc chờ lâu sau một transaction cũ.

### 19.2. Lock timeout

Đặt lock_timeout để DDL fail sớm thay vì chờ vô hạn và tạo queue các requests khác:

~~~sql
SET lock_timeout = '5s';
ALTER TABLE public.orders ADD COLUMN source_code text;
~~~

Nếu timeout, điều tra blockers và thử lại trong window phù hợp. Không tăng timeout chỉ để ép DDL chạy.

### 19.3. Statement timeout

statement_timeout giới hạn thời gian statement. Chọn giá trị theo operation; một migration lớn có thể cần deadline riêng và monitoring.

### 19.4. Transactional DDL

Nhiều PostgreSQL DDL commands có thể chạy trong transaction, nhưng một số commands như CREATE INDEX CONCURRENTLY và VACUUM không được chạy trong transaction block. Xác nhận command-specific rules.

### 19.5. Migration compatibility

Deploy application tương thích schema cũ/mới theo expand-and-contract. Không drop/rename column khi còn application instances đang sử dụng schema cũ.

## 20. Tạo index online

CREATE INDEX thông thường có thể block writes vào table trong quá trình build. CREATE INDEX CONCURRENTLY giảm mức chặn writes nhưng tốn thời gian và có thêm phases.

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

### 20.1. Concurrent build

Concurrent build cho phép INSERT/UPDATE/DELETE tiếp tục trong phần lớn quá trình. Nó vẫn cần locks và có thể chờ transactions/snapshots cũ.

### 20.2. Không chạy trong transaction block

CREATE INDEX CONCURRENTLY không được chạy bên trong BEGIN/COMMIT transaction block. Migration tool phải hỗ trợ chạy statement độc lập.

### 20.3. Failed index build

Nếu build fail, có thể để lại invalid index. Kiểm tra pg_index.indisvalid/indisready và drop/retry theo runbook.

### 20.4. Resource impact

Index build đọc table, sort dữ liệu, ghi index và WAL. Theo dõi I/O, CPU, temp files, replication lag và disk free space.

### 20.5. Kiểm tra sau build

Xác nhận index valid, planner có thể dùng và query performance cải thiện. Index mới tăng write amplification và storage.

## 21. REINDEX và index maintenance

Index rebuild có thể giải quyết corruption/bloat hoặc thay đổi storage layout, nhưng tạo tải và yêu cầu disk headroom.

### 21.1. REINDEX thông thường

REINDEX có thể cần lock mạnh và ảnh hưởng reads/writes trên relation tùy loại đối tượng. Lập window và kiểm tra blockers.

### 21.2. REINDEX CONCURRENTLY

Concurrent reindex giảm blocking cho ordinary DML trên các phiên bản hỗ trợ, nhưng có phases, extra disk use và waits. Không chạy trong transaction block.

### 21.3. Disk headroom

Trong lúc build, index cũ và mới có thể cùng tồn tại. Tính thêm temporary files/WAL và khả năng replica/archive retention.

### 21.4. Unique indexes

Unique index build có thể phát hiện duplicate data và fail. Xử lý duplicates theo business rules trước khi chạy.

### 21.5. Validate workload impact

So sánh query plans, latency và write throughput sau rebuild; không kết luận thành công chỉ vì command exit code 0.

## 22. VACUUM, VACUUM FULL và ANALYZE

Các maintenance commands có lock, I/O và transaction-context requirements khác nhau.

### 22.1. VACUUM thường

VACUUM reclaim space cho reuse, cập nhật visibility information và giúp ngăn transaction ID wraparound. Nó thường cho phép reads/writes tiếp tục nhưng tiêu thụ I/O.

### 22.2. VACUUM FULL

VACUUM FULL rewrite table và cần ACCESS EXCLUSIVE lock. Nó có thể thu hồi disk space về filesystem nhưng tạo downtime/lock cho table; cần đủ disk tạm và window.

### 22.3. ANALYZE

ANALYZE cập nhật planner statistics. Nó thường không yêu cầu table downtime, nhưng có I/O/CPU cost và có thể thay đổi query plans.

### 22.4. Không dùng VACUUM FULL như routine

Trước tiên xem dead tuples, long transactions, autovacuum và bloat evidence. VACUUM thường không nhất thiết thu hồi file size về OS nhưng có thể tái sử dụng space bên trong relation.

### 22.5. VACUUM không chạy trong transaction block

Chạy VACUUM/ANALYZE theo command rules và scheduling phù hợp. VACUUM FULL có yêu cầu lock mạnh hơn đáng kể.

## 23. Online schema migration

Migration theo bước giúp giảm thời gian phải chuyển database sang restricted/offline mode.

### 23.1. Expand

Thêm cột/table/index mới ở dạng tương thích với ứng dụng hiện tại. Chọn defaults và nullability theo PostgreSQL version/DDL lock behavior.

### 23.2. Deploy compatible application

Deploy code có thể đọc/ghi cả schema cũ và mới. Với dual-write, cần idempotency và kiểm soát consistency.

### 23.3. Backfill theo batches

Backfill dữ liệu theo batches nhỏ, commit thường xuyên và checkpoint progress. Theo dõi WAL, replica lag, dead tuples và foreground latency.

### 23.4. Switch reads/writes

Sau khi backfill/validation, chuyển application sang schema mới. Giữ đường rollback cho tới khi hết thời gian quan sát.

### 23.5. Contract

Sau khi không còn code cũ và dữ liệu đã xác minh, drop legacy columns/objects trong một migration riêng có lock timeout và rollback plan.

## 24. Backup trong maintenance window

Backup là workload có thể thực hiện online, nhưng vẫn cần lập lịch và kiểm soát tài nguyên.

### 24.1. Physical base backup

Physical backup đọc nhiều data files và có thể tạo network/disk load. Theo dõi replication/WAL retention và backup tool progress.

### 24.2. Logical dump

pg_dump tạo consistent snapshot và đọc tables/indexes. Với database lớn, có thể chạy lâu và ảnh hưởng cache/I/O; chọn parallelism phù hợp.

### 24.3. WAL archiving

Đảm bảo archive_command/archiver health trước và sau maintenance. WAL cần được giữ liên tục để PITR.

### 24.4. Backup trước thay đổi rủi ro

Với migration destructive hoặc upgrade, xác nhận backup gần nhất, WAL coverage và restore procedure. Backup “completed” chưa đủ nếu chưa có restore evidence.

### 24.5. Restore test

Thử restore vào isolated environment và kiểm tra database/application consistency. Không làm restore test bằng cách ghi đè production.

## 25. Minor và major version upgrades

PostgreSQL upgrades có mức downtime và quy trình khác nhau.

### 25.1. Minor update

Minor updates thường giữ data directory compatibility trong cùng major series nhưng vẫn yêu cầu restart và cần kiểm tra release notes/extensions/provider requirements.

### 25.2. Major upgrade với pg_upgrade

pg_upgrade chuyển data directory sang major version mới theo quy trình tương thích. Cần preflight, backup, extension binaries, disk space và downtime/upgrade mode.

### 25.3. Major upgrade với logical replication

Có thể dùng logical replication để đồng bộ source/target và cutover với downtime ngắn hơn, nhưng cần schema, sequence, large objects, DDL và write freeze plan.

### 25.4. Extension compatibility

Kiểm tra extension version, shared libraries, SQL upgrade scripts và compatibility với target PostgreSQL version.

### 25.5. Cutover validation

Trước khi mở writes trên target, kiểm tra row counts/checksums/business invariants, sequences, roles, grants, jobs, replication/backup và application smoke tests.

## 26. Maintenance trên HA cluster

HA có thể giảm downtime, nhưng maintenance từng node vẫn cần đảm bảo quorum, replication và capacity.

### 26.1. Standby-first maintenance

Một số updates có thể thực hiện trên standby trước, sau đó switchover và update node cũ. Phải kiểm tra version compatibility và upgrade procedure.

### 26.2. Rolling maintenance

Chỉ bảo trì từng node nếu cluster topology và replication mode hỗ trợ. Đảm bảo còn đủ standby/quorum và failover protection trong mỗi bước.

### 26.3. Planned switchover

Drain writes, chờ candidate catch up, xác nhận timeline/LSN, chuyển primary và fence/demote old primary theo HA manager.

### 26.4. Failover protection gap

Trong khi một node đang restart/rebuild, cluster có thể chỉ còn một primary và không có standby khỏe. Đánh dấu degraded protection và giảm rủi ro workload.

### 26.5. Restore redundancy

Sau maintenance, xác nhận standby đã rejoin/catch up, archive/backup hoạt động và HA manager thấy topology healthy trước khi kết thúc window.


## 27. Lập kế hoạch maintenance window

Một maintenance plan tốt mô tả thứ tự thao tác, thời lượng dự kiến, dependencies và quyết định dừng.

### 27.1. Scope

Ghi rõ cluster, database, tables, application services, regions, endpoints, replicas, backup systems và external integrations bị ảnh hưởng.

### 27.2. Impact classification

Phân loại từng thao tác: online, degraded performance, read-only, partial outage hay full outage. Thông báo impact cụ thể thay vì chỉ ghi “maintenance”.

### 27.3. Timeline

Lập các mốc preflight, admission stop, drain, backup/checkpoint, change, validation, traffic restore và closeout. Dành buffer cho rollback và recovery.

### 27.4. Owners và approvals

Chỉ định change owner, DBA, application owner, infrastructure owner, incident commander/on-call và business approver nếu có data loss hoặc extended downtime risk.

### 27.5. Dependencies

Xác nhận access credentials, storage capacity, backup target, DNS/proxy control, certificates, monitoring, vendor support và người có thể approve.

## 28. Preflight checklist trước window

Preflight giúp phát hiện điều kiện không đủ trước khi đưa hệ thống vào restricted mode.

### 28.1. Health

Kiểm tra database availability, error rate, replication state, disk free, CPU/memory headroom, backup/archiver và HA manager.

### 28.2. Data safety

Xác nhận backup thành công, WAL coverage, restore evidence và transaction/LSN baseline. Với migration destructive, lưu rollback/restore point.

### 28.3. Locks và sessions

Kiểm tra long transactions, idle-in-transaction, prepared transactions, blockers, active jobs và replication consumers.

### 28.4. Capacity

Tính disk tạm cho index rebuild/upgrade, memory/CPU cho backfill, WAL growth và replica catch-up. Không bắt đầu nếu headroom thiếu.

### 28.5. Change readiness

Kiểm tra scripts, checksums/artifact versions, approvals, rollback steps, runbook links và test results ở staging.

## 29. Runbook: bắt đầu maintenance window

Thứ tự cụ thể phụ thuộc thao tác, nhưng có thể dùng khung chung.

1. Declare window start và xác nhận owners/on-call có mặt.
2. Chụp baseline: metrics, node roles, LSN/timeline, connections, slots, backup/archive state.
3. Thông báo application/gateway và bật maintenance/read-only mode nếu cần.
4. Stop hoặc pause scheduled jobs, queue consumers và writers.
5. Drain in-flight requests và connection pools.
6. Kiểm tra remaining sessions/transactions; terminate theo policy nếu cần.
7. Xác nhận database ở trạng thái restricted/quiesced mong muốn.
8. Thực hiện thao tác đã phê duyệt và ghi output/timestamps.
9. Validate database, replication, backup, application và business behavior.
10. Resume jobs/traffic từng bước, theo dõi SLO và đóng window.

### 29.1. Không bỏ baseline

Nếu không ghi state trước change, khó phân biệt lỗi mới với vấn đề đã tồn tại.

### 29.2. Freeze point

Ghi thời điểm cuối cùng application được phép ghi. Dùng nó để reconcile events/transactions sau maintenance.

### 29.3. Một change owner điều phối

Tránh nhiều operators chạy commands song song trên cùng cluster mà không biết state của nhau.

### 29.4. Checkpoint từng bước

Ghi hoàn thành/precondition của mỗi step. Nếu phải abort, biết chính xác hệ thống đang ở đâu.

### 29.5. Communication cadence

Gửi update theo mốc đã định, đặc biệt khi duration thay đổi hoặc rollback được kích hoạt.

## 30. Stop conditions và abort criteria

Maintenance phải có tiêu chí dừng trước khi bắt đầu.

### 30.1. Data safety failure

Backup không đọc được, WAL gap, unexpected writes hoặc replication state không xác định là lý do dừng trước thao tác destructive.

### 30.2. Lock wait vượt deadline

Nếu DDL không lấy lock trong lock_timeout hoặc blockers không thể xử lý an toàn, cancel và reschedule.

### 30.3. Capacity threshold

Dừng khi disk headroom, memory, replication lag hoặc WAL retention chạm threshold được phê duyệt.

### 30.4. Unexpected application impact

Nếu error rate, latency hoặc queue backlog vượt abort criteria, dừng bước tiếp theo và đánh giá rollback.

### 30.5. Ambiguous state

Nếu không biết command đã thành công hay chưa, kiểm tra database/catalog/control plane trước khi retry. Không chạy lặp lệnh destructive chỉ vì client timeout.

## 31. Rollback và recovery plan

Rollback phải được định nghĩa theo từng loại thay đổi; không phải mọi database operation đều có rollback đơn giản.

### 31.1. Configuration rollback

Lưu config cũ, thay đổi theo từng setting và có command/approval để khôi phục. Kiểm tra reload/restart requirements.

### 31.2. Schema rollback

DDL destructive có thể không đảo ngược nếu đã drop/transform dữ liệu. Ưu tiên expand-and-contract và backup/restore point cho migration rủi ro.

### 31.3. Index rollback

Có thể drop index vừa tạo nếu gây vấn đề, nhưng cân nhắc locks và query dependency. Concurrent drop có thể phù hợp cho index lớn theo version.

### 31.4. Upgrade rollback

Major version upgrade thường không thể đơn giản khởi động binary cũ trên data directory đã upgrade. Chuẩn bị old cluster snapshot/backup hoặc rollback topology riêng.

### 31.5. PITR thay cho undo

Nếu thay đổi đã commit và lan truyền, restore/PITR có thể là cách phục hồi. Phải tính thời gian restore, data loss sau recovery point và reconciliation writes.

## 32. Kiểm tra sau maintenance

Maintenance chỉ hoàn tất khi hệ thống đã trở lại trạng thái service-ready theo tiêu chí.

### 32.1. Database readiness

Kiểm tra connection, read/write behavior theo intended mode, logs, catalog state, schema version và critical queries.

### 32.2. Replication readiness

Kiểm tra sender/receiver, replay lag, slots, WAL archive và timeline. Với HA cluster, xác nhận standby healthy.

### 32.3. Application readiness

Chạy smoke tests qua endpoint thật: login, read, safe write, transaction commit, queue publish/consume và external integrations.

### 32.4. Business validation

Kiểm tra row counts/aggregates/invariants quan trọng, pending jobs và event backlog. Chỉ mở writes đầy đủ khi business state chấp nhận được.

### 32.5. Restore normal mode

Bật lại connections, roles, gateway admission, workers và scheduled jobs theo thứ tự. Gỡ maintenance flag và xác nhận monitoring nhận traffic bình thường.

## 33. Monitoring trong maintenance window

Trong window, cần dashboard tập trung vào cả tiến độ operation và tác động tới service.

### 33.1. Database activity

Active sessions, locks, transaction age, query latency, deadlocks và errors.

### 33.2. Resource pressure

CPU, memory/swap, disk latency/IOPS/throughput, temp files và free space.

### 33.3. WAL và replication

WAL generation, archive backlog, slot retained bytes, sender/receiver lag và replay progress.

### 33.4. Application impact

Request rate, error rate, p95/p99, pool wait, queue depth và retries.

### 33.5. Maintenance progress

Index build progress, vacuum progress, backup progress, upgrade phases và estimated remaining time nếu tooling cung cấp. Không suy ra ETA chính xác từ một sample.

## 34. Maintenance trên storage và filesystem

Storage operations có thể cần phối hợp với PostgreSQL vì data files, WAL và temporary files có behavior khác nhau.

### 34.1. Disk expansion

Mở rộng volume/filesystem theo provider procedure, xác nhận filesystem nhìn thấy capacity mới và không làm thay đổi mount/ownership.

### 34.2. Disk migration

Dùng quy trình PostgreSQL-aware để di chuyển data/WAL directories. Stop/copy/sync/permissions và startup validation cần được kiểm soát; không copy active data directory tùy tiện.

### 34.3. WAL directory

Nếu WAL nằm trên volume riêng, kiểm tra mount trước khi start PostgreSQL. Sai mount có thể khiến server ghi vào filesystem root hoặc không khởi động.

### 34.4. Disk full

Disk full có thể ngăn WAL, checkpoints, temp files hoặc logs ghi tiếp. Giữ emergency headroom và runbook xử lý slots/archive/temp files.

### 34.5. Capacity alerts

Alert theo free bytes, percentage, growth rate và time-to-full. Percentage một mình có thể đánh lừa trên volume rất lớn hoặc nhỏ.

## 35. Certificate và credential maintenance

Credential rotation là maintenance bảo mật nhưng có thể làm replication/application connections gián đoạn.

### 35.1. Rotation overlap

Nếu policy cho phép, triển khai credential/certificate mới song song, xác nhận clients reconnect, rồi thu hồi cũ.

### 35.2. TLS certificate

Kiểm tra SAN/hostname, CA chain, expiration, permissions và trust stores ở application, pooler, replication clients.

### 35.3. Replication connections

Rotate replication user secrets trên mọi subscribers/standbys và verify sender/receiver reconnect trước khi thu hồi credential cũ.

### 35.4. Database role rotation

Không thay password một role dùng chung mà chưa inventory mọi clients. Ưu tiên role riêng theo service và secret references.

### 35.5. Audit

Ghi actor, time, secret version và connection validation; không ghi secret value vào logs/tickets.

## 36. Backup và maintenance scheduling

Backup schedule cần tránh conflict với các operations tạo I/O lớn, nhưng không làm giảm backup coverage.

### 36.1. Base backup window

Chọn thời điểm workload thấp nếu backup đọc nhiều data. Đo actual throughput và ảnh hưởng tới cache/replication.

### 36.2. WAL archive continuity

Không pause archive pipeline nếu chưa hiểu retention/recovery consequences. Khi archive backend bảo trì, phải có buffer/alert.

### 36.3. Backup catalog consistency

Ghi backup ID, source node, timeline, start/stop LSN, WAL coverage và retention metadata.

### 36.4. Restore test window

Dành lịch riêng cho restore drills trên isolated infrastructure. Đo RTO và kiểm tra app data.

### 36.5. Backup after upgrade

Sau major upgrade/schema migration, tạo backup mới theo policy và xác nhận WAL archive chain trên topology mới.


## 37. Thông báo và điều phối maintenance

Thông báo tốt giúp application teams chuẩn bị retries, queue handling và user communication.

### 37.1. Thông báo trước

Nêu service/database scope, start/end time, timezone, expected impact, read/write availability, endpoints và support contact.

### 37.2. Reminder

Gửi reminder trước window và xác nhận các owners đã hoàn thành preflight. Thay đổi thời gian phải được thông báo lại.

### 37.3. Live status

Trong window, cập nhật state: scheduled, admission closed, draining, executing, validating, restoring traffic hoặc extended/aborted.

### 37.4. Extension notice

Nếu operation vượt thời gian dự kiến, thông báo lý do, impact hiện tại, risk và ETA mới. Không hứa ETA khi chưa có bằng chứng.

### 37.5. Completion notice

Thông báo service restored, restricted mode đã gỡ, validation đạt và các hạn chế còn tồn tại (nếu có).

## 38. Lịch maintenance và conflict management

Nhiều nhóm có thể lên lịch changes trên cùng cluster; cần một lịch có visibility.

### 38.1. Shared calendar

Ghi windows của database, application, network, storage, identity và cloud platform. Tránh overlap với business peak/events.

### 38.2. Change freeze

Có thể đặt freeze trước các mùa cao điểm hoặc financial close. Emergency security fixes cần exception path.

### 38.3. Dependency order

Ví dụ certificate rotation phải được hoàn thành ở trust stores trước khi server cert đổi; schema expansion phải trước application deploy; database upgrade phải trước extension/application compatibility steps theo plan.

### 38.4. Concurrent maintenance

Không chạy đồng thời backup, index rebuild, storage migration và major batch nếu chúng cùng cạnh tranh I/O mà chưa benchmark.

### 38.5. Review after window

So sánh actual duration/impact với estimate và cập nhật future maintenance duration/sequence.

## 39. Restricted mode theo use case

Chế độ cần được chọn theo operation và mục tiêu bảo vệ.

| Use case | Mode gợi ý | Kiểm soát chính |
|---|---|---|
| Read-only reporting period | Read-only role/transaction | SELECT grants, default read-only |
| Schema migration requiring no writes | App write freeze + drain | Pause writers/jobs, validate sessions |
| Database restart | Full drain/offline | Stop clients, fast shutdown, readiness |
| Emergency data repair | Restricted access | Operator-only path, backup, audit |
| HA switchover | Writer drain/quiesce | Catch-up, fence/demote, route |
| Certificate rotation | Restricted admin change | Overlap certs, reconnect tests |
| Index creation concurrently | Normal service with monitoring | Lock waits, I/O, replication |
| Major upgrade | Offline or logical cutover | Backup, compatibility, validation |

### 39.1. Read-only window

Dùng khi reads có thể tiếp tục nhưng writes phải dừng. Kiểm tra tất cả write paths, gồm jobs và privileged users.

### 39.2. Operator-only window

Dùng khi chỉ DBA/infra cần truy cập. HBA/network allowlists và database connection restrictions cần giữ management path.

### 39.3. Full offline window

Dùng cho thao tác yêu cầu restart/restore hoặc storage operations không tương thích với live access. Draining và recovery checks phải được tính vào window.

### 39.4. Online maintenance

Một số commands có thể chạy khi service hoạt động, nhưng cần monitoring và abort criteria. Concurrent không có nghĩa zero impact.

### 39.5. Degraded service window

Có thể giữ một số read endpoints trong khi writer path bị dừng. Phải thông báo rõ freshness/consistency và endpoint behavior.

## 40. Scheduled jobs và maintenance coordination

Jobs có thể tự khởi động giữa lúc DBA đang bảo trì.

### 40.1. Inventory schedulers

Ghi cron, pg_cron, Kubernetes CronJobs, Airflow, ETL orchestrators, application schedulers và vendor jobs.

### 40.2. Pause/resume

Pause trước freeze point, lưu job state/offset và resume theo thứ tự sau validation. Không xóa schedule để dừng tạm.

### 40.3. Retry behavior

Một job fail trong window có thể retry ngay khi database mở lại và tạo burst. Thêm jitter/backoff và concurrency limits.

### 40.4. Long-running jobs

Quyết định job nào được phép hoàn tất, job nào phải cancel và cách resume. Lưu checkpoints để tránh chạy lại toàn bộ batch.

### 40.5. Job ownership

Mỗi job cần owner, contact, expected duration, write scope và recovery procedure. Không có owner thì khó đánh giá có thể terminate hay không.

## 41. Maintenance với logical/physical replication

Maintenance trên một node có thể ảnh hưởng replication và failover protection.

### 41.1. Trước khi bảo trì publisher

Kiểm tra sender connections, slots, synchronous standbys, archive status và WAL retention. Đảm bảo downstream có đường WAL phù hợp.

### 41.2. Bảo trì standby

Drain read traffic khỏi standby, stop/restart/rebuild theo runbook và xác nhận receiver/replay progress sau khi trở lại.

### 41.3. Logical subscriptions

Nếu subscription/apply worker phải pause, kiểm tra logical slots trên publisher và retained WAL. Không drop slot nếu chưa có resync plan.

### 41.4. Failover trong maintenance

Không kết hợp maintenance với planned failover trừ khi đây là mục tiêu đã được diễn tập. Nếu primary fail trong window, chuyển sang incident runbook.

### 41.5. Khôi phục redundancy

Xác nhận mọi standbys/subscriptions đã bắt kịp, slots valid và backup/archive chain liên tục trước khi kết thúc.

## 42. Maintenance và data correction

Sửa dữ liệu trực tiếp có thể tạo side effects và không giống thay đổi schema/configuration.

### 42.1. Xác định phạm vi rows

Dùng SELECT preview với primary keys, count và expected values trước UPDATE/DELETE. Lưu result set hoặc backup cần thiết.

### 42.2. Transaction size

Chia large corrections thành batches có checkpoint để giảm lock duration, WAL burst và rollback cost.

### 42.3. Idempotency

Script phải có điều kiện để chạy lại an toàn hoặc ghi progress marker. Tránh UPDATE toàn bảng lặp mà không biết phần nào đã hoàn tất.

### 42.4. Business approval

Sửa balances, orders, payments, entitlements hoặc audit data cần owner phê duyệt. DBA xác nhận cách thực thi và evidence.

### 42.5. Validate after correction

So sánh affected row counts, aggregates và business invariants. Kiểm tra downstream events/replicas/cache nếu chúng không tự đồng bộ.

## 43. Security và maintenance access

Maintenance window có thể mở rộng quyền truy cập; kiểm soát cần rõ ràng.

### 43.1. Least privilege

Dùng role riêng theo task: read-only inspect, schema migration, backup, replication admin và superuser break-glass. Không dùng một shared superuser cho mọi thao tác.

### 43.2. Time-bound access

Cấp quyền tạm thời trong window và thu hồi sau đó. Kiểm tra memberships, default privileges và credentials đã rotate.

### 43.3. Bastion/network controls

Operator access qua bastion/VPN có MFA và audit. Không mở PostgreSQL port rộng ra internet để tiện bảo trì.

### 43.4. Audit logging

Ghi DDL, role grants, connection changes, configuration changes và privileged actions. Giữ query text/parameters theo privacy policy.

### 43.5. Separation of duties

Với thao tác rủi ro, người đề xuất, người approve và người execute có thể là các vai trò khác nhau. Cách này giảm sai sót và tăng traceability.


## 44. Ví dụ: maintenance window cho schema migration

Một migration thêm cột, backfill và chuyển ứng dụng có thể được thực hiện theo từng giai đoạn.

### 44.1. Trước window

Tạo backup/restore point, kiểm tra replication lag, deploy code tương thích schema cũ/mới và chạy migration trên staging với data volume đại diện.

### 44.2. Expand schema

Thêm cột nullable hoặc cấu trúc mới theo DDL lock policy. Dùng lock_timeout ngắn và abort nếu không lấy được lock nhanh.

### 44.3. Backfill

Pause hoặc throttle batch, update theo key ranges nhỏ, commit theo batches và monitor WAL/replica lag/latency.

### 44.4. Cutover

Bật application path mới sau khi validation counts/checksums đạt. Giữ old column/logic cho rollback window.

### 44.5. Contract sau đó

Drop legacy objects trong maintenance window riêng khi không còn application version cũ. Không gộp destructive cleanup vào lần deploy đầu.

## 45. Ví dụ: maintenance window cho restart/configuration change

### 45.1. Xác định parameter

Dùng pg_settings.context để biết reload hay restart. Kiểm tra parameter values và pending_restart.

### 45.2. Preflight

Xác nhận backup, HA candidate, replication catch-up, disk/CPU headroom và connection drain plan.

### 45.3. Drain

Bật app maintenance, pause jobs, drain poolers và xác nhận không còn critical transactions.

### 45.4. Apply/restart

Áp dụng config qua configuration management; reload hoặc restart bằng service manager theo runbook. Không sửa trực tiếp nhiều sources of truth.

### 45.5. Validate/restore

Kiểm tra SHOW settings, logs, SQL readiness, replication, app smoke tests; mở traffic từng bước và xác nhận protection đã phục hồi.

## 46. Ví dụ: emergency maintenance khi disk gần đầy

### 46.1. Đánh giá nguyên nhân

Kiểm tra filesystem, pg_wal, replication slots, archive backlog, temp files, logs và relation growth. Không xóa WAL files bằng filesystem command.

### 46.2. Giảm tải an toàn

Tạm pause batch/backup hoặc writers theo business priority. Giữ đủ WAL/backup protection và xác định slots/consumers gây retention.

### 46.3. Mở rộng storage nếu cần

Dùng provider-supported volume expansion và filesystem procedure. Xác nhận free space thực tế sau thao tác.

### 46.4. Xử lý slot/archive

Chỉ drop/advance slot hoặc xóa retention khi hiểu subscriber/recovery consequences. Nếu mất WAL cần thiết, standby/consumer có thể phải reseed.

### 46.5. Khôi phục normal operations

Xác nhận WAL generation/archive/replication bắt kịp, disk forecast an toàn, backup chạy và alerts được clear có evidence.

## 47. Bài tập thực hành

### Bài 1 — Khái niệm

Maintenance window là gì?

**Đáp án:** Khoảng thời gian được lập kế hoạch/điều phối để thực hiện thay đổi vận hành có thể ảnh hưởng service.

### Bài 2 — Restricted mode

Restricted mode có nhất thiết phải offline toàn database không?

**Đáp án:** Không; có thể chỉ read-only, operator-only hoặc dừng writes.

### Bài 3 — Transaction read-only

Lệnh nào bắt đầu transaction read-only?

**Đáp án:** BEGIN READ ONLY.

### Bài 4 — Default

default_transaction_read_only có chặn mọi privileged writes không?

**Đáp án:** Không; đây là default transaction behavior, cần kết hợp privileges/controls.

### Bài 5 — Role grants

Vì sao reporting role cần bỏ write privileges?

**Gợi ý:** Enforce read-only tại authorization layer thay vì chỉ dựa vào app code.

### Bài 6 — ALLOW_CONNECTIONS

ALTER DATABASE ... ALLOW_CONNECTIONS false có ngắt sessions đang mở không?

**Đáp án:** Không; nó ngăn connections mới, sessions hiện tại cần drain/terminate riêng.

### Bài 7 — HBA

Thay đổi pg_hba.conf có tác dụng ngay với sessions hiện tại không?

**Đáp án:** Không; reload áp dụng cho connection attempts mới, không terminate sessions đã xác thực.

### Bài 8 — Application mode

Vì sao phải pause queue consumers và schedulers?

**Gợi ý:** Chúng có thể tiếp tục ghi dù API đã chuyển read-only.

### Bài 9 — Drain

Drain có nghĩa gì?

**Đáp án:** Ngừng nhận công việc mới và chờ/cancel công việc đang chạy theo deadline.

### Bài 10 — Long transaction

Vì sao idle in transaction nguy hiểm khi maintenance?

**Đáp án:** Nó có thể giữ locks/snapshot và ngăn vacuum cleanup.

### Bài 11 — Prepared transaction

Có nên tự động rollback mọi prepared transaction trước maintenance không?

**Đáp án:** Không; phải xác định coordinator/business outcome.

### Bài 12 — Reload/restart

Setting nào cho biết một config change cần restart?

**Đáp án:** pg_settings.context, cùng pending_restart để xác nhận trạng thái.

### Bài 13 — Shutdown

Fast shutdown có behavior gì?

**Đáp án:** Ngắt clients, abort active transactions và shutdown sạch theo server mechanism.

### Bài 14 — Immediate shutdown

Vì sao immediate shutdown có risk?

**Đáp án:** Lần startup tiếp theo cần crash recovery.

### Bài 15 — Connection storm

Làm sao giảm reconnect burst sau restart?

**Gợi ý:** Stagger startup, jitter, pool warm-up và throttled traffic restore.

### Bài 16 — CREATE INDEX CONCURRENTLY

Có thể chạy trong transaction block không?

**Đáp án:** Không.

### Bài 17 — Failed concurrent index

Cần kiểm tra gì?

**Gợi ý:** Index validity/readiness và drop/retry theo runbook nếu build để lại invalid index.

### Bài 18 — VACUUM FULL

Điểm khác biệt quan trọng so với VACUUM thường?

**Đáp án:** Rewrite relation, cần ACCESS EXCLUSIVE lock và có thể gây downtime cho table.

### Bài 19 — Lock timeout

lock_timeout giúp gì?

**Đáp án:** Giới hạn thời gian chờ lock để DDL không chờ vô hạn.

### Bài 20 — Expand-and-contract

Vì sao thêm schema trước rồi mới drop schema cũ?

**Gợi ý:** Cho phép các application versions tương thích cùng tồn tại và giảm downtime.


### Bài 21 — Backup

Backup completed có đủ chứng minh recoverability không?

**Đáp án:** Không; cần WAL coverage và restore test.

### Bài 22 — Major upgrade

Vì sao không thể luôn khởi động binary cũ sau pg_upgrade?

**Đáp án:** Major upgrade có thể chuyển đổi data directory/catalog; cần rollback artifact/backup riêng.

### Bài 23 — HA rolling maintenance

Vì sao cần giữ standby/quorum capacity trong rolling maintenance?

**Đáp án:** Để cluster vẫn có failover protection và không mất coordination.

### Bài 24 — Logical slot

Vì sao không drop slot chỉ để giải phóng disk trong maintenance?

**Đáp án:** Consumer có thể mất WAL cần thiết và phải resync.

### Bài 25 — Stop condition

Nêu hai điều kiện phải dừng maintenance.

**Gợi ý:** Backup/WAL không an toàn, disk headroom thiếu, unexpected writes, lock wait vượt deadline, replication lag quá ngưỡng.

### Bài 26 — Rollback

Mọi DDL đều rollback dễ dàng không?

**Đáp án:** Không; destructive data changes có thể cần restore/PITR.

### Bài 27 — Read-only standby

Standby read-only có đảm bảo dữ liệu mới nhất không?

**Đáp án:** Không; phải xem replay lag/freshness.

### Bài 28 — User communication

Thông báo maintenance cần nêu những gì?

**Gợi ý:** Scope, time zone, impact, read/write availability, endpoints và support contact.

### Bài 29 — Emergency disk

Có được xóa file WAL trực tiếp trong pg_wal để lấy chỗ không?

**Đáp án:** Không; dùng PostgreSQL-aware slot/archive/storage procedures.

### Bài 30 — Completion

Khi nào maintenance window được xem là hoàn tất?

**Đáp án:** Database, replication, backup, application/business validation và monitoring đều đạt exit criteria; restricted mode đã được gỡ đúng.

## 48. Checklist trước maintenance

- [ ] Scope, impact, timezone và window được phê duyệt?
- [ ] Owners/on-call và escalation contacts đã xác nhận?
- [ ] Backup/WAL coverage và restore evidence có sẵn?
- [ ] Database, HA, replication, archive và disk health đạt?
- [ ] Long transactions, prepared transactions, slots và blockers đã kiểm tra?
- [ ] Capacity cho index/upgrade/backfill đủ?
- [ ] Application, gateway, poolers và jobs có maintenance/drain plan?
- [ ] Config/DDL scripts và version compatibility đã thử?
- [ ] Rollback, stop conditions và validation steps rõ?
- [ ] Operator/break-glass access đã thử?
- [ ] Communication/reminder đã gửi?

## 49. Checklist trong và sau maintenance

### Trong window

- [ ] Baseline và freeze point đã ghi?
- [ ] Application admission/writes được kiểm soát?
- [ ] Workers/schedulers/consumers đã pause?
- [ ] Connections/transactions đã drain?
- [ ] Mỗi operation có output/timestamp và checkpoint?
- [ ] CPU/memory/disk/WAL/replication/app SLO được theo dõi?
- [ ] Stop conditions được áp dụng khi cần?

### Sau window

- [ ] Database settings/schema/indexes đã verify?
- [ ] SQL readiness và critical queries đạt?
- [ ] Replication/slots/WAL archive khỏe?
- [ ] Backup mới/backup chain được xác nhận theo policy?
- [ ] Application smoke tests và business invariants đạt?
- [ ] Queues/jobs được resume theo thứ tự?
- [ ] Read-only/connection restrictions đã gỡ đúng?
- [ ] Traffic được mở từng bước và p95/p99 ổn định?
- [ ] Completion notice và change record đã cập nhật?
- [ ] Follow-up issues có owner/deadline?

## 50. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| Maintenance window | Khoảng thời gian điều phối thay đổi |
| Restricted mode | Giới hạn hoạt động được phép |
| BEGIN READ ONLY | Transaction chỉ đọc |
| default_transaction_read_only | Default mode của transactions |
| Role privileges | Enforcement quyền đọc/ghi |
| ALLOW_CONNECTIONS | Cho phép/chặn kết nối mới vào database |
| CONNECTION LIMIT | Giới hạn connections |
| pg_hba.conf | Client authentication/admission rules |
| Drain | Ngừng admission và xử lý in-flight work |
| pg_stat_activity | Sessions và transaction state |
| pg_prepared_xacts | Prepared transactions |
| pg_reload_conf | Reload configuration |
| pg_settings.context | Context áp dụng setting |
| pending_restart | Setting đang chờ restart |
| Smart shutdown | Chờ clients disconnect |
| Fast shutdown | Ngắt clients và shutdown sạch |
| Immediate shutdown | Dừng ngay, cần crash recovery |
| CREATE INDEX CONCURRENTLY | Build index với giảm blocking DML |
| REINDEX CONCURRENTLY | Rebuild index giảm blocking theo version |
| VACUUM | Cleanup/reuse space, visibility maintenance |
| VACUUM FULL | Rewrite table, lock mạnh |
| lock_timeout | Giới hạn thời gian chờ lock |
| statement_timeout | Giới hạn execution duration |
| Expand-and-contract | Migration schema theo bước tương thích |
| pg_upgrade | Major version upgrade tool |
| WAL archive | Recovery chain |
| Exit criteria | Điều kiện kết thúc maintenance |
| Stop condition | Điều kiện phải dừng/abort |

## 51. Kết luận

**Maintenance an toàn cần phối hợp lịch, admission control, restricted mode, database operations và validation.** Transaction read-only, default_transaction_read_only, role privileges, connection limits, ALLOW_CONNECTIONS và pg_hba.conf là các công cụ ở database layer; application gateway, connection poolers, background jobs và network controls quyết định liệu hệ thống có thực sự ngừng nhận writes hay không. Các connections/transactions đã tồn tại không tự biến mất khi đổi setting hoặc reload HBA, nên drain và kiểm tra sessions là bước bắt buộc trong nhiều windows.

Không phải mọi maintenance đều cần downtime. Concurrent index operations, một số DDL, analyze và backup có thể thực hiện online với monitoring/abort criteria. Các thao tác như VACUUM FULL, restart, storage migration hoặc major upgrade có thể cần restricted/offline mode. Phải hiểu lock behavior, transaction-block restrictions, resource impact, WAL/replication retention và rollback limitations trước khi thực hiện.

Một maintenance window cần preflight, owners, timeline, freeze point, stop conditions, rollback/recovery, live monitoring và exit criteria. Sau thay đổi, xác nhận database, replication, archive/backup, application smoke tests và business invariants; mở traffic/workers từng bước rồi gỡ restricted mode. Ghi actual duration, impact và follow-up để cải thiện window tiếp theo.

Nguyên tắc vận hành: **giới hạn đúng loại hoạt động cần dừng, drain mọi nguồn ghi, giữ access path quản trị an toàn, thực hiện thay đổi theo checkpoint và chỉ mở lại service sau khi có bằng chứng validation.**

