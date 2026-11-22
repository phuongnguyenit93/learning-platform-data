# Tự động hóa hạ tầng, cấu hình và tài liệu bàn giao PostgreSQL

Một PostgreSQL deployment có thể chạy tốt sau khi cài đặt nhưng vẫn khó vận hành nếu hạ tầng được tạo thủ công, cấu hình nằm rải rác trên nhiều máy và không có tài liệu cho người tiếp quản. Khi cần mở rộng, thay đổi version, khôi phục sự cố hoặc chuyển giao đội vận hành, những khác biệt nhỏ giữa các môi trường có thể dẫn đến downtime và lỗi khó tái hiện.

Tự động hóa triển khai cần quản lý đồng thời ba lớp:

1. **Hạ tầng:** máy chủ/VM/container, network, storage, firewall, DNS, load balancer, backup target và monitoring.
2. **Cấu hình và dịch vụ PostgreSQL:** packages, data directory, parameters, authentication, TLS, roles, extensions, replication, backup agents và service lifecycle.
3. **Vận hành và bàn giao:** source of truth, change history, runbooks, recovery procedures, ownership, access model, monitoring expectations và known limitations.

Infrastructure as Code (IaC) mô tả tài nguyên hạ tầng bằng code có thể review và version control. Configuration management đưa hệ điều hành và PostgreSQL về trạng thái mong muốn. Deployment automation phối hợp các bước theo thứ tự và kiểm tra kết quả. Tài liệu bàn giao giúp đội tiếp nhận hiểu hệ thống, biết cách vận hành và có thể phục hồi khi xảy ra sự cố.

Bài **“Tự động hóa hạ tầng, cấu hình và tài liệu bàn giao”**, thuộc chương **Triển khai** của module **Database Engine Relational PostgreSQL**, trình bày cách thiết kế quy trình tự động hóa an toàn, quản lý cấu hình có kiểm soát, triển khai PostgreSQL nhất quán giữa các môi trường và chuẩn bị tài liệu vận hành có thể sử dụng thực tế.

> **Nguyên tắc:** mọi thay đổi quan trọng cần có source of truth, owner, cách triển khai, cách xác minh và phương án phục hồi. Tự động hóa tốt tạo ra trạng thái có thể tái lập và quan sát được, thay vì chỉ chạy một chuỗi lệnh thành công.

---

## 1. Vì sao cần tự động hóa triển khai?

Cài đặt PostgreSQL thủ công thường bắt đầu đơn giản: cài package, tạo data directory, sửa configuration, tạo users và khởi động service. Khi có nhiều servers, môi trường staging/production hoặc HA, thao tác thủ công dễ tạo drift.

Các rủi ro phổ biến:

- Parameter khác nhau giữa các nodes.
- Một host thiếu extension package.
- Firewall hoặc TLS configuration không đồng nhất.
- Backup agent chưa được bật.
- Replication slot hoặc monitoring target bị bỏ sót.
- Người triển khai quên một bước trong runbook.
- Không biết ai đã thay đổi file cấu hình.
- Recovery procedure chỉ tồn tại trong trí nhớ của một người.

Tự động hóa giảm số thao tác lặp lại, làm rõ dependencies và cung cấp evidence sau deployment.

## 2. Phân biệt provisioning, configuration management và deployment

| Hoạt động | Mục tiêu | Ví dụ |
|---|---|---|
| Provisioning | Tạo tài nguyên cần thiết | VM, subnet, disk, firewall |
| Configuration management | Đưa host về trạng thái mong muốn | OS packages, users, sysctl, files |
| Database deployment | Cài và cấu hình PostgreSQL | initdb, roles, extensions, parameters |
| Application deployment | Kết nối ứng dụng tới database | connection pool, secret reference |
| Operations automation | Thực hiện công việc định kỳ | backup, monitoring, failover drills |

Các hoạt động liên quan nhưng không nên gộp thành một script lớn không có ranh giới hoặc trạng thái trung gian.

## 3. Infrastructure as Code

IaC mô tả hạ tầng bằng cấu hình được lưu trong version control. Công cụ phổ biến gồm Terraform, OpenTofu, cloud-native templates và các nền tảng provisioning tương ứng.

Ví dụ một tài nguyên VM có thể được mô tả bằng HCL:

~~~hcl
resource "example_compute_instance" "postgres" {
  name         = "postgres-primary"
  machine_type = "database-optimized"
  zone         = var.database_zone
  tags         = ["postgres", "private"]
}
~~~

Đây là ví dụ minh họa; resource type và arguments thực tế phụ thuộc provider.

IaC giúp review changes, tạo môi trường nhất quán và quản lý dependency giữa network, storage, compute và security policies.

## 4. Source of truth

Chọn nơi lưu trạng thái mong muốn:

- Repository IaC cho cloud resources.
- Repository configuration management cho OS/PostgreSQL config.
- Migration repository cho schema/database objects.
- Secret manager cho credentials.
- Monitoring configuration repository cho alerts/dashboards.
- Documentation repository cho runbooks và architecture.

Không duy trì nhiều bản cấu hình độc lập mà không xác định bản nào có thẩm quyền.

Tài liệu cần chỉ rõ repository, branch/tag, owner và quy trình phê duyệt.

## 5. Tách môi trường

Dev, test, staging và production thường có yêu cầu khác nhau về kích thước, availability, retention và security.

Dùng cùng một cấu trúc automation với variables theo môi trường:

~~~text
inventory/
  dev/
  staging/
  production/
config/
  common/
  postgresql/
  monitoring/
environments/
  dev.tfvars
  staging.tfvars
  production.tfvars
~~~

Không copy toàn bộ file production rồi sửa thủ công cho staging. Dùng shared modules và environment-specific inputs để giảm drift.

## 6. Thiết kế module và reusable components

Tách các thành phần có trách nhiệm rõ:

- Network module.
- Compute module.
- Storage module.
- PostgreSQL installation role.
- PostgreSQL configuration role.
- Database bootstrap role.
- Backup/monitoring integration.
- HA/replication role.

Module nên có inputs, outputs, assumptions và versioning. Tránh module khổng lồ có nhiều side effects không liên quan.

## 7. Idempotency

Một automation idempotent có thể chạy nhiều lần mà vẫn đưa hệ thống về cùng trạng thái mong muốn, không tạo thêm resources hoặc lặp lại side effects ngoài dự kiến.

Ví dụ configuration management nên đảm bảo package được cài đúng version, service được enable, directory có owner/mode mong muốn, file cấu hình được render từ template và role/database được tạo nếu chưa tồn tại.

Idempotency không có nghĩa mọi lệnh SQL đều an toàn để chạy lặp lại. Dùng state-aware tasks, migrations hoặc upsert semantics phù hợp.

## 8. Desired state và actual state

Automation so sánh trạng thái thực tế với trạng thái mong muốn.

| Thuộc tính | Desired state | Actual state |
|---|---|---|
| PostgreSQL major | 17 | 17 |
| Package version | approved build | installed build |
| Port | 5432 | 5432 |
| TLS | required | enabled |
| Backup | WAL archive active | configured |
| Monitoring | all required alerts | one alert missing |

Khi có drift, cần xác định nguồn gốc: thay đổi hợp lệ, thao tác khẩn cấp, automation chưa chạy hay cấu hình bị sửa ngoài quy trình.

## 9. Drift detection

Drift là khác biệt giữa cấu hình đã khai báo và trạng thái đang chạy.

Có thể phát hiện bằng IaC plan/refresh, configuration management check mode, hash của managed files, PostgreSQL settings inventory, package version inventory, cloud resource policies và scheduled compliance reports.

Không tự động overwrite mọi drift. Một thay đổi khẩn cấp có thể cần được đưa ngược vào source of truth trước khi chạy reconciliation.

## 10. State management của IaC

Một số công cụ IaC giữ state để biết resource nào đã được quản lý.

State cần được lưu ở backend phù hợp, có access control, locking nếu công cụ hỗ trợ, backup/versioning và không chứa secrets plaintext trong repository.

Không sửa state file thủ công nếu không hiểu resource identity và provider behavior. Khi state bị mất hoặc lệch, import/reconcile cần có kế hoạch.

## 11. Quản lý secrets

Database credentials, replication passwords, TLS private keys và backup credentials không nên hardcode trong IaC, Git hoặc shell history.

Dùng secret manager hoặc hệ thống quản lý credentials phù hợp:

- Secret manager của cloud.
- Vault hoặc enterprise secret store.
- Short-lived credentials nếu được hỗ trợ.
- OS-protected files với quyền tối thiểu.

Repository chỉ nên chứa secret references và cách inject secrets, không chứa secret values.

## 12. Rotation credentials

Runbook cần mô tả ai được phép rotate, credential nào phụ thuộc credential đó, cách cập nhật database role/password, cách cập nhật secret store, cách restart/reload consumers, cách xác minh kết nối mới và cách rollback nếu client chưa chuyển.

Không rotate database password mà chưa xác định connection pools, jobs, replication và backup agents đang dùng credential nào.

## 13. OS baseline cho PostgreSQL host

Trước khi cài PostgreSQL, chuẩn hóa:

- OS distribution và release.
- Kernel và supported filesystem.
- Time synchronization.
- Locale/encoding packages.
- User/group cho PostgreSQL.
- Limits và service manager.
- Firewall và routing.
- Monitoring/logging agent.
- Security updates.
- Backup mount/permissions.

Không chạy PostgreSQL bằng root. Dùng service account riêng và giới hạn quyền đọc/ghi vào data, WAL, log và backup paths.

## 14. Package repositories và version pinning

Cài PostgreSQL từ repository được phê duyệt và pin major/minor/package versions theo release policy.

Ví dụ Debian-based system:

~~~bash
sudo apt-get update
sudo apt-get install postgresql-17 postgresql-client-17
~~~

Đây là ví dụ; package naming và repository phụ thuộc distro. Production automation cần kiểm tra repository signing, package origin, version policy và update channel.

Không dùng package source tùy tiện hoặc để môi trường production tự nâng major version theo latest package.

## 15. Cài extension packages

Nếu database dùng native extensions, automation phải cài đúng package cho PostgreSQL major version và OS architecture.

Ví dụ:

~~~bash
sudo apt-get install postgresql-17-postgis-3
~~~

Tên package minh họa, cần kiểm tra repository thực tế. Extension SQL object được cài riêng trong từng database bằng CREATE EXTENSION.

Package installation và database migration nên là hai tasks có thể quan sát và retry độc lập.

## 16. Filesystem và storage layout

Thiết kế storage dựa trên workload, durability và recovery requirements.

Có thể tách PGDATA, WAL directory nếu kiến trúc yêu cầu, tablespaces, PostgreSQL logs, backup staging và archive/WAL storage.

Không tách chỉ vì thói quen. Đánh giá throughput, IOPS, latency, capacity, failure domain, snapshot semantics và operational complexity.

## 17. Directory ownership và permissions

PostgreSQL data directory phải có ownership/mode đúng theo PostgreSQL requirements. Trên Linux, ví dụ:

~~~bash
sudo install -d -o postgres -g postgres -m 700 /var/lib/postgresql/data
~~~

Không đặt PGDATA trên filesystem có semantics không được hỗ trợ hoặc mount options gây ảnh hưởng durability.

Automation nên kiểm tra free space, mount status, ownership và permissions trước initdb/startup.

## 18. Network và firewall

Xác định rõ client subnets được phép kết nối, replication traffic, monitoring/backup traffic, admin access, DNS names, service endpoints và egress tới secret manager/object storage.

Chỉ mở port cần thiết. Không bind PostgreSQL ra mọi network interface nếu service chỉ cần private network.

Network policy cần đồng bộ với pg_hba.conf và TLS policy.

## 19. DNS và service discovery

Ứng dụng nên dùng endpoint ổn định thay vì hardcode IP của node.

Tài liệu cần chỉ rõ primary/write endpoint, read-only/replica endpoint nếu có, internal DNS names, TTL/cache behavior, cách cập nhật sau failover, health/readiness checks và owner của DNS records.

DNS update không đảm bảo mọi connection pool lập tức reconnect. Có thể cần drain connections và kiểm tra routing.

## 20. TLS configuration

Tự động hóa TLS cần quản lý server certificate, private key, certificate chain, CA trust, file ownership/mode, expiration monitoring và renewal/rotation process.

PostgreSQL settings ví dụ:

~~~text
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'root.crt'
~~~

Các đường dẫn cần khớp host và quyền truy cập. Private key phải được bảo vệ; không đưa key vào Git hoặc artifact công khai.

## 21. pg_hba.conf và authentication

pg_hba.conf điều khiển client authentication theo thứ tự rules.

~~~text
# TYPE  DATABASE  USER          ADDRESS          METHOD
hostssl appdb     app_runtime   10.20.0.0/16     scram-sha-256
hostssl replication repl_user   10.30.0.0/16     scram-sha-256
local   all       postgres                       peer
~~~

Đây là ví dụ minh họa; điều chỉnh theo network và role thực tế.

Automation cần validate syntax và reload cấu hình. Một rule rộng ở đầu file có thể làm rule hẹp phía dưới không bao giờ được áp dụng.

## 22. PostgreSQL configuration files

Các file cấu hình chính thường gồm postgresql.conf, pg_hba.conf, pg_ident.conf, include files nếu sử dụng và service environment/configuration của OS.

Dùng template và variables có version control. Không sửa file bằng search-and-replace không kiểm soát nếu có thể render toàn bộ managed section.

Giữ local overrides có chủ đích và ghi rõ thứ tự include.

## 23. Parameter precedence

Một setting có thể đến từ nhiều nguồn: default, configuration files, command-line options, ALTER SYSTEM, database/role settings hoặc session SET.

View pg_settings cung cấp thông tin về setting hiện hành và source:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
ORDER BY name;
~~~

Không giả định file postgresql.conf là nguồn duy nhất. Khi có nhiều layers, ghi rõ source of truth và cách thay đổi.

## 24. Reload và restart

Một số settings áp dụng bằng reload; một số cần restart PostgreSQL.

~~~sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'max_connections',
    'log_min_duration_statement',
    'shared_preload_libraries'
)
ORDER BY name;
~~~

- sighup: có thể áp dụng sau reload.
- postmaster: cần restart server.
- Các context khác có quy tắc riêng như superuser/backend/superuser-backend.

Dùng pg_reload_conf() hoặc service manager theo quy trình:

~~~sql
SELECT pg_reload_conf();
~~~

Sau thay đổi restart-required settings, kiểm tra pending_restart và lên lịch restart có kiểm soát.

## 25. ALTER SYSTEM

ALTER SYSTEM ghi setting vào postgresql.auto.conf:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';
SELECT pg_reload_conf();
~~~

Đây là một cơ chế thay đổi cấu hình runtime, nhưng có thể làm mờ source of truth nếu automation cũng quản lý postgresql.conf.

Chọn policy rõ: hoặc automation quản lý ALTER SYSTEM/auto.conf, hoặc cấm dùng tùy tiện và yêu cầu thay đổi qua repository. Không để nhiều hệ thống ghi cùng một parameter mà không có precedence documentation.

## 26. Kiểm tra file cấu hình có lỗi

View pg_file_settings cho biết các entries đọc được từ configuration files và lỗi parse:

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
ORDER BY sourcefile, sourceline;
~~~

View này giúp phát hiện typo, duplicate settings hoặc file không áp dụng như dự kiến.

Không chỉ kiểm tra automation task exit code. Đọc PostgreSQL configuration state sau khi reload.

## 27. Quản lý shared_preload_libraries

Một số extensions cần được load khi server startup:

~~~text
shared_preload_libraries = 'pg_stat_statements'
~~~

Automation phải cài package/library, render setting, xác minh file tồn tại và đúng build, restart theo maintenance policy, kiểm tra startup logs và xác minh extension hoạt động.

Nếu module thiếu, PostgreSQL có thể không start. Chuẩn bị rollback config file và service recovery procedure.

## 28. Locale, encoding và collation

initdb tạo cluster với encoding và locale choices có ảnh hưởng dài hạn.

Ví dụ:

~~~bash
initdb \
  --pgdata=/var/lib/postgresql/data \
  --encoding=UTF8 \
  --locale=C.UTF-8
~~~

Tên locale có thể khác giữa OS distributions. Ghi lại locale provider, collation version và encoding trong deployment manifest.

Thay đổi collation environment có thể làm index ordering không còn phù hợp; cần đánh giá REINDEX/collation refresh theo PostgreSQL version và workload.

## 29. Bootstrap roles và databases

Automation có thể tạo roles/databases qua SQL scripts hoặc migration tools.

~~~sql
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_runtime LOGIN;

CREATE DATABASE appdb OWNER app_owner;
GRANT CONNECT ON DATABASE appdb TO app_runtime;
~~~

Cần xử lý idempotency và ownership cẩn thận. CREATE DATABASE không chạy trong transaction block, vì vậy thường là task riêng.

Không lưu password plaintext trong SQL file. Inject credentials qua secret manager hoặc provisioning mechanism.

## 30. Quyền và ownership

Phân biệt cluster administrator, database owner, schema owner, migration role, runtime application role, read-only/reporting role, backup/replication role và monitoring role.

Tạo role theo responsibility và cấp grants tối thiểu. Không dùng superuser làm application connection.

Automation phải quản lý cả membership, default privileges và object ownership sau migration.

## 31. Bootstrap scripts và migrations

Bootstrap script chuẩn bị cluster/database mới: roles, database, schema prerequisites và extensions.

Migration thay đổi schema theo version ứng dụng.

Không chạy lại toàn bộ migration như seed nếu migration tool đã có version history. Không đặt các thao tác bootstrap không idempotent vào một script không có trạng thái.

Ghi rõ thứ tự: packages, initdb, service config, roles/databases, extensions, migrations, baseline data và application deployment.

## 32. Backup automation

Backup automation cần mô tả base backup cadence, WAL archiving, retention, encryption, storage location, credentials, monitoring/alerting, restore testing và RTO/RPO.

Ví dụ base backup:

~~~bash
pg_basebackup \
  --host=db-primary.internal \
  --username=backup_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

Đây chỉ là một lệnh minh họa; backup system thực tế cần quản lý WAL, retention, encryption và metadata nhất quán.

## 33. Restore automation

Restore automation cần nhận được backup identifier, target PostgreSQL major version, target host/storage, recovery target time/LSN nếu PITR, WAL archive location, tablespace mapping, extension package inventory và configuration/secrets references.

Sau restore, không tự mở traffic ngay. Chạy startup checks, recovery state checks, database validation và application smoke tests.

## 34. Monitoring và alerting as code

Quản lý dashboards và alerts trong version control nếu nền tảng hỗ trợ.

Các chỉ số quan trọng:

- Connection count và saturation.
- Transaction rate.
- Query latency.
- Locks/deadlocks.
- Cache hit ratio trong ngữ cảnh workload.
- WAL generation và archive failures.
- Replication lag.
- Disk capacity/IOPS/latency.
- Checkpoints và autovacuum.
- Backup age và restore test status.
- Certificate expiration.
- PostgreSQL process/service health.

Alert cần có severity, owner, runbook link và hành động dự kiến. Tránh cảnh báo không có owner hoặc không có cách phản ứng.

## 35. Log management

Chuẩn hóa log destination, log rotation, retention, structured fields nếu có, timezone/timestamp format, slow query thresholds, connection/disconnection logging policy, audit logging và secret/PII redaction.

Không bật verbose logging vô hạn vì có thể gây disk exhaustion và lộ thông tin nhạy cảm.

## 36. HA và replication automation

Với topology primary/standby, automation cần quản lý node inventory, replication credentials, WAL settings, replication slots, standby configuration, failover orchestration, fencing/single-writer protection, rejoin/reseed process và monitoring.

Failover automation phải đảm bảo old primary không tiếp tục nhận writes sau khi standby được promote. Split-brain là rủi ro nghiêm trọng.

Không xem một script promote đơn lẻ là HA automation đầy đủ.

## 37. Upgrade automation

Upgrade major version cần pipeline riêng, có preflight và gates:

1. Inventory source/target versions.
2. Kiểm tra extension packages.
3. Backup và restore rehearsal.
4. Chạy compatibility checks.
5. Chuẩn bị target binaries/config.
6. Chạy pg_upgrade hoặc logical migration.
7. Kiểm tra database/extension state.
8. Analyze và application validation.
9. Cutover.
10. Giữ rollback/recovery window.

Automation không được tự vượt GO/NO-GO gate khi một validation critical thất bại.

## 38. CI/CD cho database infrastructure

Pipeline có thể gồm:

~~~text
Pull request
    |
    v
Static validation / formatting
    |
    v
IaC plan and review
    |
    v
Configuration lint and syntax checks
    |
    v
Build/test database image
    |
    v
Deploy to ephemeral environment
    |
    v
Smoke tests and restore tests
    |
    v
Approval / change window
    |
    v
Deploy to production
    |
    v
Post-deploy verification
~~~

Không để pipeline production dùng quyền rộng hơn mức cần thiết. Tách build identity, deploy identity và runtime service identity.

## 39. Change management

Mỗi change có thể ghi ticket/change ID, mục tiêu và phạm vi, services/nodes/databases ảnh hưởng, owner và approver, preflight checks, planned window, commands/automation version, success criteria, rollback/recovery path, evidence và timestamps.

Emergency changes cần được ghi lại và đưa trở lại source of truth sau khi ổn định.

## 40. Validation sau provisioning

Sau khi automation tạo host/database, xác minh actual state.

OS-level checks:

~~~bash
systemctl status postgresql
df -h
lsblk
timedatectl status
~~~

Database checks:

~~~sql
SELECT version();

SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW port;

SELECT
    current_database(),
    current_user,
    inet_server_addr(),
    inet_server_port();
~~~

Kiểm tra TLS, roles, extensions, backup, replication và monitoring theo topology thực tế.

## 41. Readiness và health checks

Phân biệt liveness với readiness:

- Liveness: process có còn hoạt động không?
- Readiness: database có đủ điều kiện nhận workload không?

Readiness có thể cần xác minh PostgreSQL accepting connections, database mục tiêu tồn tại, role ứng dụng authenticate được, required extensions load được, primary/standby role đúng, replication/backup requirements đạt và disk space bình thường.

Không dùng một TCP port check làm bằng chứng database đã sẵn sàng phục vụ nghiệp vụ.

## 42. Configuration validation trước rollout

Trước khi apply production:

- Parse/format validation cho IaC.
- Plan diff được review.
- Configuration templates được lint.
- PostgreSQL settings được kiểm tra.
- pg_hba rules được review theo thứ tự.
- Secret references tồn tại.
- Package versions được resolve.
- Storage/network dependencies sẵn sàng.
- Rollback artifact có thể truy cập.

Có thể tạo ephemeral database để test rendered configuration trước khi restart production.

## 43. Rolling deployment và maintenance window

Không phải mọi thay đổi PostgreSQL đều rolling-safe.

Phân loại reload-only settings, restart-required settings, extension/library changes, schema migrations, major version upgrades và HA topology changes.

Với HA, cần xác định node order và failover behavior. Một restart replica trước primary có thể an toàn trong một số tình huống, nhưng phải dựa trên topology và version-specific procedure.

Không tự động rolling restart khi chưa xác minh compatibility và quorum/leader semantics của hệ thống HA.

## 44. Rollback automation

Rollback cần xác định artifact/config version trước đó, database state có tương thích với old application không, old package/binaries còn sẵn không, có thể quay lại node cũ hay phải restore, writes sau cutover có thể mất không, DNS/endpoint có thể chuyển lại không, ai quyết định rollback và thời hạn quyết định.

Rollback config file thường đơn giản hơn rollback data/schema. Không giả định revert Git commit tự hoàn tác database migrations hoặc transactions.

## 45. Runbook là gì?

Runbook là hướng dẫn thao tác cho một tình huống vận hành cụ thể.

Một runbook tốt có purpose/scope, preconditions, required access/roles, exact commands hoặc automation entry point, expected output, verification, timeout, failure handling, escalation/contact, evidence capture, last reviewed date và owner.

Hướng dẫn kiểu “restart database nếu có lỗi” không đủ để người trực ca thực hiện an toàn.

## 46. Runbook triển khai PostgreSQL

Một runbook deployment có thể gồm:

1. Xác nhận change window và approval.
2. Xác minh backup gần nhất.
3. Kiểm tra host/storage/network.
4. Xác minh package repository/version.
5. Provision host và directories.
6. Cài PostgreSQL/extension packages.
7. Render configuration và authentication.
8. Khởi tạo hoặc attach data directory theo thiết kế.
9. Start service.
10. Tạo roles/databases/extensions.
11. Cấu hình backup/monitoring/replication.
12. Chạy smoke tests.
13. Ghi evidence và handoff.

Mỗi bước cần owner và expected result.

## 47. Runbook sự cố phổ biến

Nên có runbook riêng cho PostgreSQL service không start, disk sắp đầy, WAL archive thất bại, replication lag tăng, backup job fail, connection saturation, certificate sắp hết hạn, failover, restore/PITR, extension library missing, authentication failure và unexpected restart.

Mỗi runbook cần phân biệt symptom, diagnosis, mitigation và permanent fix.

## 48. Disaster recovery documentation

DR document cần nêu RTO/RPO, backup topology, backup retention, WAL archive and restore process, recovery region/account, DNS/service endpoint cutover, secrets/certificates recovery, extension packages and versions, validation criteria, decision authority, communication plan và last successful restore drill.

Backup job success không chứng minh DR có thể hoàn tất trong RTO. Cần ghi kết quả restore exercise thực tế.

## 49. Architecture diagram

Tài liệu bàn giao nên có sơ đồ:

~~~text
Application services
        |
        v
Private DB endpoint / connection pool
        |
        v
Load balancer or HA routing
        |
        v
PostgreSQL primary
        |
        +----------> Standby node(s)
        |
        +----------> WAL archive / backup storage
        |
        +----------> Monitoring and log platform
        |
        +----------> Secret manager / KMS
~~~

Sơ đồ thực tế cần ghi network boundaries, ports, replication direction, failure domains, storage, DNS names và owners. Không đưa passwords hoặc private key vào diagram.

## 50. System inventory và configuration manifest

Manifest nên ghi:

| Nhóm | Trường cần ghi |
|---|---|
| Identity | Environment, cluster name, owner |
| Version | PostgreSQL major/minor, OS, extensions |
| Compute | VM/container type, CPU, RAM |
| Storage | PGDATA, WAL, tablespaces, capacity |
| Network | Private endpoints, ports, allowed sources |
| Security | Roles, auth method, TLS, secret references |
| HA | Primary/standby topology, failover manager |
| Backup | Tool, schedule, retention, WAL archive |
| Monitoring | Dashboards, alerts, runbooks |
| Automation | Repository, module version, pipeline |

Manifest phải phản ánh trạng thái hiện hành và có ngày cập nhật.

## 51. Access and ownership handover

Bàn giao cần ghi team chịu trách nhiệm PostgreSQL, on-call/escalation path, DBA/admin roles, application owners, cloud/OS owners, backup/DR owners, monitoring owners, change approvers và secret manager access process.

Không ghi password hoặc token vào tài liệu. Ghi tên secret reference và cách xin quyền truy cập theo policy.

## 52. Operational procedures và routine tasks

Tài liệu nên chỉ rõ tần suất và owner của backup verification, restore testing, capacity review, extension/package updates, PostgreSQL minor updates, certificate rotation, role/access review, replication health review, log/alert review, vacuum/analyze monitoring và disaster recovery exercises.

Một danh sách task không có frequency hoặc owner thường không được thực hiện nhất quán.

## 53. Knowledge transfer

Một buổi handover nên bao gồm:

1. Architecture walkthrough.
2. Deployment pipeline walkthrough.
3. Configuration/source-of-truth walkthrough.
4. Backup and restore demonstration.
5. Failover/rejoin demonstration.
6. Monitoring and alert response.
7. Secret/access process.
8. Known issues and limitations.
9. Escalation and change approval.
10. Q&A và ghi nhận gaps.

Người nhận nên thực hiện một số thao tác dưới giám sát để chứng minh tài liệu có thể sử dụng.

## 54. Documentation versioning

Mỗi tài liệu nên có owner, version hoặc commit, last reviewed date, applicable PostgreSQL version, environment scope, related automation repository, change history và links tới dashboards/tickets/runbooks.

Tài liệu không có ngày review dễ trở nên lỗi thời sau upgrade hoặc topology change.

## 55. Secrets và tài liệu bàn giao

Không đưa vào README/runbook database passwords, private keys, cloud access keys, tokens, connection strings chứa password hoặc unredacted production dumps.

Có thể ghi secret name/path, service identity, quyền cần thiết và quy trình request/rotation. Nếu cần ví dụ connection string, dùng placeholder và không dùng credential thật.

## 56. Known limitations và technical debt

Tài liệu bàn giao nên ghi rõ extension chưa hỗ trợ target version, một số restore steps còn thủ công, backup retention chưa đáp ứng policy, monitoring chưa bao phủ metric nào, capacity headroom hạn chế, failover có downtime dự kiến, external dependencies có SLA riêng và runbook nào chưa được diễn tập.

Ghi owner và next action cho từng gap. Không che giấu giới hạn bằng cách ghi fully automated khi còn bước thủ công.

## 57. Operational acceptance criteria

Hệ thống chỉ nên được coi là sẵn sàng bàn giao khi:

- Infrastructure code nằm trong repository.
- Configuration có source of truth.
- Deployment có thể tái lập.
- Secrets được quản lý an toàn.
- Backup và restore được chứng minh.
- Monitoring/alerts có owner.
- HA/failover được diễn tập nếu yêu cầu.
- Runbooks được review.
- Access model rõ.
- On-call và escalation được xác nhận.
- Known limitations được ghi nhận.
- Người tiếp nhận có thể thực hiện quy trình cơ bản.

## 58. Ví dụ cấu trúc repository

~~~text
postgres-platform/
  infra/
    modules/
      network/
      compute/
      storage/
    environments/
      dev/
      staging/
      production/
  config/
    os/
    postgresql/
    pgbouncer/
    monitoring/
  database/
    bootstrap/
    migrations/
    seeds/
  backup/
    policies/
    restore/
  runbooks/
    deploy.md
    failover.md
    restore-pitr.md
    disk-full.md
    certificate-rotation.md
  docs/
    architecture.md
    inventory.md
    security.md
    handover.md
  .github/
    workflows/
~~~

Cấu trúc chỉ là gợi ý. Điều quan trọng là ownership, dependency và release lifecycle phải rõ.

## 59. Ví dụ PostgreSQL settings manifest

Một file YAML có thể mô tả settings mong muốn:

~~~yaml
postgresql:
  port: 5432
  listen_addresses:
    - 10.20.1.10
  timezone: UTC
  max_connections: 200
  shared_buffers: 4GB
  log_min_duration_statement: 500ms
  ssl: true
  password_encryption: scram-sha-256
  shared_preload_libraries:
    - pg_stat_statements
~~~

Đây là ví dụ minh họa, không phải sizing recommendation. Giá trị memory/connection phải được tính theo RAM, workload, connection pooling và platform limits.

Automation cần validate types, units, allowed values và restart context trước khi áp dụng.

## 60. Ví dụ configuration management task

Một Ansible task minh họa:

~~~yaml
- name: Ensure PostgreSQL package is installed
  ansible.builtin.package:
    name: postgresql-17
    state: present

- name: Ensure PostgreSQL data directory exists
  ansible.builtin.file:
    path: /var/lib/postgresql/data
    state: directory
    owner: postgres
    group: postgres
    mode: "0700"

- name: Render PostgreSQL configuration
  ansible.builtin.template:
    src: postgresql.conf.j2
    dest: /etc/postgresql/17/main/postgresql.conf
    owner: postgres
    group: postgres
    mode: "0640"
  notify: Reload PostgreSQL
~~~

Handler có thể gọi service reload:

~~~yaml
- name: Reload PostgreSQL
  ansible.builtin.service:
    name: postgresql
    state: reloaded
~~~

Tên service và đường dẫn phụ thuộc distro. Một số settings cần restart; handler phải phân loại đúng, không dùng reload cho mọi thay đổi.

## 61. Automation safety và failure handling

Mỗi task cần có preconditions, timeout, retry policy phù hợp, failure behavior, idempotency, logging, verification và compensation/rollback nếu có.

Không retry mù quáng một thao tác không idempotent như tạo resource có side effects hoặc chạy migration dữ liệu. Với database migrations, ghi version và transaction semantics.

Automation phải fail fast khi secret thiếu, disk không đủ hoặc target version không được hỗ trợ.

## 62. Hạn chế blast radius

Triển khai theo phạm vi nhỏ: một dev environment, một staging cluster, một canary node nếu topology cho phép, một production cluster theo change window, rồi rollout rộng sau khi có evidence.

Tách quyền deployment theo environment và dùng approvals cho production. Không dùng cùng một credential quản trị cho mọi pipeline.

## 63. Audit trail và evidence

Lưu Git commit/tag, IaC plan/apply output, configuration management run ID, PostgreSQL version/settings snapshot, package inventory, change ticket, start/end timestamps, health/validation results, backup/restore evidence và operator/approver identity.

Redact secrets trước khi lưu logs. Evidence phải đủ để trả lời ai thay đổi gì, ở đâu, lúc nào và kết quả ra sao.

## 64. Checklist bàn giao production

**Hạ tầng**

- Network, storage và firewall được mô tả.
- Compute sizing và capacity headroom được ghi.
- DNS/endpoints được ghi.
- Failure domains và dependencies được vẽ.

**PostgreSQL**

- Version và packages được pin.
- Configuration source of truth rõ.
- pg_hba/TLS/auth được mô tả.
- Roles/ownership/default privileges được ghi.
- Extensions và versions được inventory.
- Backup/restore/HA được xác minh.

**Vận hành**

- Monitoring/alerts có owner.
- Runbooks có preconditions và verification.
- Upgrade/failover/restore được diễn tập.
- Secrets/rotation có quy trình.
- On-call/escalation rõ.
- Known limitations có owner.

**Automation**

- IaC/config repositories được bàn giao.
- Pipeline và access permissions rõ.
- State/backend/locking được bảo vệ.
- Drift detection có lịch.
- Change approval và rollback có tài liệu.

## 65. Câu hỏi thường gặp

### IaC có thay thế configuration management không?

Không hoàn toàn. IaC thường quản lý tài nguyên hạ tầng; configuration management quản lý trạng thái OS/service. Một nền tảng có thể làm cả hai nhưng cần phân định ownership và lifecycle.

### Vì sao automation cần idempotent?

Để chạy lại an toàn sau lỗi hoặc khi cần reconcile drift. Tuy nhiên, migration và thao tác có side effects phải có version/state management riêng.

### Có nên quản lý postgresql.conf bằng ALTER SYSTEM?

Có thể, nhưng cần một policy duy nhất. Nếu automation quản lý file mà operator đồng thời ghi postgresql.auto.conf, source of truth và precedence sẽ khó hiểu.

### Làm sao biết setting cần restart?

Xem pg_settings.context và pending_restart, đồng thời kiểm tra documentation của parameter/version. Không suy đoán chỉ từ tên setting.

### Có thể reload mọi PostgreSQL configuration không?

Không. Một số settings chỉ được đọc lúc startup và cần restart. Kiểm tra context và pending_restart sau reload.

### Có nên lưu password trong Ansible variables hoặc Terraform state?

Không lưu plaintext trong repository. Terraform state cũng có thể chứa sensitive values dù marked sensitive; dùng secret references, encrypted remote state và access controls.

### Vì sao cần package inventory?

Để tái tạo đúng extension libraries và dependencies khi restore, failover hoặc rebuild host.

### Backup có nằm trong IaC không?

IaC có thể tạo storage, policies và backup resources; nhưng database backup content, WAL retention và restore procedures cần được quản lý bởi backup platform và runbooks.

### Readiness check có thể chỉ dùng pg_isready không?

pg_isready xác nhận server có phản hồi trạng thái connection, nhưng không chứng minh ứng dụng, extensions, replication hoặc business transactions sẵn sàng.

### Tại sao cần ghi lại sourcefile của pg_settings?

Để biết setting đang đến từ file nào và phát hiện override ngoài source of truth.

### Handover document có nên chứa connection password?

Không. Ghi endpoint và secret reference; credential được truy cập qua secret manager theo access policy.

### Ai sở hữu runbook?

Một team hoặc role vận hành cụ thể phải chịu trách nhiệm review/cập nhật. Mỗi runbook nên có owner và ngày review.

### Khi nào nên dùng template database?

Khi schema/extensions/baseline ít thay đổi và cần tạo nhiều test databases nhanh. Template cần version cùng migrations và seed.

### Có thể tự động failover hoàn toàn không?

Có thể với HA platform được thiết kế phù hợp, nhưng cần fencing/single-writer protection, quorum/leader semantics, monitoring và failover drills. Một promote command đơn lẻ không đủ.

### Bàn giao hoàn tất khi nào?

Khi đội tiếp nhận có quyền truy cập phù hợp, hiểu kiến trúc, chạy được deployment/restore/failover procedures, biết owner/escalation và chấp nhận các known limitations.

## 66. Tổng kết

Những nguyên tắc cần nhớ:

1. Tách provisioning, configuration management, database deployment và operations automation.
2. Dùng IaC và configuration repositories làm source of truth.
3. Tách environment bằng variables/modules, không copy config thủ công.
4. Thiết kế automation idempotent và state-aware.
5. Theo dõi drift và đưa emergency changes trở lại source of truth.
6. Bảo vệ IaC state, secrets và deployment identities.
7. Chuẩn hóa OS baseline, packages, storage, network và service account.
8. Pin PostgreSQL và extension package versions.
9. Quản lý PGDATA, WAL, tablespaces, logs và backup storage có chủ đích.
10. Đồng bộ firewall, DNS, TLS và pg_hba.conf.
11. Hiểu parameter precedence, reload context và restart requirements.
12. Dùng pg_settings và pg_file_settings để xác minh cấu hình thực tế.
13. Quản lý roles, ownership và default privileges theo least privilege.
14. Tách bootstrap scripts khỏi schema migrations và test seeds.
15. Tự động hóa backup nhưng luôn kiểm thử restore.
16. Quản lý monitoring/alerts bằng code và gắn owner/runbook.
17. HA automation phải ngăn split-brain và có rejoin procedure.
18. Upgrade automation cần preflight, gates, validation và recovery path.
19. Mọi change cần evidence và audit trail.
20. Runbooks cần exact commands, expected outputs, timeout và escalation.
21. Handover cần architecture, inventory, access model và operational procedures.
22. Không đưa passwords, tokens hoặc private keys vào tài liệu.
23. Ghi rõ known limitations, technical debt và owner.
24. Bàn giao chỉ hoàn tất khi người nhận có thể vận hành và phục hồi hệ thống.

Sơ đồ vòng đời:

~~~text
Requirements and architecture
             |
             v
       Infrastructure as Code
             |
             v
     Provision network/storage/VM
             |
             v
    Configure OS and PostgreSQL
             |
             v
 Bootstrap roles, databases, extensions
             |
             v
     Deploy backup and monitoring
             |
             v
       Validate actual state
             |
             v
       Run acceptance tests
             |
             v
     Handover docs and runbooks
             |
             v
       Operate / monitor / audit
             |
             v
    Review drift, changes and DR
             |
             +------> Update source of truth
~~~

**Kết luận:** triển khai PostgreSQL có thể tái lập khi hạ tầng, cấu hình và database bootstrap được mô tả trong source of truth và tự động hóa theo trạng thái mong muốn. Cấu hình phải được xác minh từ chính PostgreSQL, vì reload/restart, precedence và các overrides có thể làm trạng thái thực tế khác file dự định. Tài liệu bàn giao cần đủ để đội tiếp nhận triển khai, giám sát, backup, failover và phục hồi mà không phụ thuộc vào trí nhớ của người xây dựng ban đầu.
