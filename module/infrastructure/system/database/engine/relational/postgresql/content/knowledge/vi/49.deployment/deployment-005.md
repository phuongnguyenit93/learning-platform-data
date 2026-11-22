# Quản lý cấu hình, thông tin bí mật và TLS theo môi trường

Một PostgreSQL deployment thường có nhiều môi trường như development, test, staging, production và disaster recovery. Các môi trường cần cùng một cấu trúc cấu hình có kiểm soát, nhưng giá trị cụ thể khác nhau: hostname, port, database name, connection limits, memory budgets, logging, backup destinations, authentication policies và certificate identities. Nếu cấu hình bị sửa thủ công ở từng máy, các môi trường dễ drift, khó tái hiện lỗi và có thể vô tình dùng credentials hoặc certificates sai nơi.

Thông tin bí mật và TLS cần được quản lý như một phần của deployment lifecycle. Password, private key, client certificate, replication credential và API secret phải có nguồn cấp phát, quyền truy cập, rotation, thu hồi và audit rõ ràng. TLS bảo vệ dữ liệu trên đường truyền, đồng thời xác thực server/client theo policy; chỉ bật mã hóa mà không xác minh danh tính server vẫn có thể để client kết nối nhầm endpoint. Cấu hình PostgreSQL, ứng dụng, pooler, monitoring và replication phải nhất quán về certificate trust và credential lifecycle.

Bài học thuộc chương **Triển khai** của module **Database Engine Relational PostgreSQL**. Nội dung trình bày cách tổ chức cấu hình theo môi trường, hiểu precedence và reload/restart, tách secrets khỏi configuration thường, quản lý role/password, triển khai TLS server/client, cấu hình pg_hba.conf, rotation và vận hành an toàn trên HA/managed services.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt configuration thường, credentials và cryptographic material.
- Tổ chức PostgreSQL settings nhất quán giữa development, test, staging, production và DR.
- Hiểu postgresql.conf, postgresql.auto.conf, include/include_dir và configuration precedence.
- Dùng pg_settings, pg_file_settings, SHOW và pg_reload_conf để kiểm tra cấu hình.
- Phân biệt reloadable settings với settings cần restart.
- Quản lý roles, SCRAM password authentication và password rotation.
- Bảo vệ client passwords bằng passfiles/secret managers.
- Bật TLS server và xác minh certificate chain/hostname ở client.
- Cấu hình client certificate authentication và pg_hba.conf.
- Quản lý TLS cho application, pooler, replication và FDW connections.
- Lập kế hoạch certificate/secret rotation không gây outage.
- Kiểm tra configuration drift, audit, observability và failure recovery.

## 2. Ba nhóm thông tin cần quản lý

Không phải mọi cấu hình đều có cùng mức độ nhạy cảm hoặc cùng lifecycle.

| Nhóm | Ví dụ | Cách quản lý |
|---|---|---|
| Configuration | max_connections, work_mem, host, port, log settings | Version control/config management |
| Secret | Password, replication credential, client private key passphrase | Secret manager, access control, rotation |
| Trust material | CA certificate, server/client certificate, public key | PKI/certificate management, expiry tracking |

### 2.1. Configuration

Configuration mô tả hành vi và endpoint của hệ thống. Nó cần review, versioning, validation và promotion giữa các môi trường.

### 2.2. Secret

Secret cho phép xác thực hoặc truy cập tài nguyên. Nếu bị lộ, người khác có thể giả mạo identity hoặc truy cập dữ liệu. Secret không nên nằm trong source code, logs, screenshots hoặc tickets.

### 2.3. Trust material

CA certificates và public certificates xác định identities được tin cậy. Private keys phải được bảo vệ như secrets; certificate expiry và revocation cần được theo dõi.

### 2.4. Không dùng một file cho mọi thứ

Tách configuration khỏi secrets giúp cấp quyền khác nhau, rotate độc lập và tránh việc người đọc cấu hình thông thường thấy password/private key.

### 2.5. Data classification

Xác định mức nhạy cảm, owner, retention và permitted access cho từng loại. Các giá trị có thể không phải password nhưng vẫn nhạy cảm, như internal hostnames, database names và topology.

## 3. Environment-specific configuration

Mỗi environment nên có cùng một cấu trúc khai báo, với values được inject từ nguồn phù hợp.

### 3.1. Development

Có thể dùng local PostgreSQL, disposable containers và test credentials riêng. Không tái sử dụng production passwords/certificates.

### 3.2. Test/CI

Dùng cấu hình deterministic, credentials ngắn hạn và certificates do test CA cấp. Test environment phải mô phỏng TLS/authentication production nếu đó là release requirement.

### 3.3. Staging

Staging nên tương đồng production về PostgreSQL major version, authentication, TLS policy, pooler, extensions và network boundaries. Dùng secrets/certificates staging độc lập.

### 3.4. Production

Dùng approved configuration baseline, secret manager/PKI, least privilege, audit và change control. Không phụ thuộc thao tác sửa file thủ công không có record.

### 3.5. Disaster recovery

DR cần credentials/certificates có thể truy cập khi primary region unavailable. Diễn tập access path, secret manager failover, CA trust và certificate renewal ở DR.

## 4. Cùng cấu trúc, values khác nhau

Một cách triển khai phổ biến là giữ template/config schema trong repository và cung cấp values theo environment.

~~~text
deployment/
  postgres/
    postgresql.conf.template
    pg_hba.conf.template
    settings/
  environments/
    development/
    test/
    staging/
    production/
    disaster-recovery/
  secret references:
    database role credentials
    TLS private keys
    client certificates
    CA bundles
~~~

### 4.1. Template

Template mô tả các settings cần thiết và kiểu dữ liệu mong đợi. Không nhúng password hoặc private key vào template.

### 4.2. Environment values

Mỗi environment cung cấp hostname, resource limits, storage paths, monitoring endpoints và authentication policy phù hợp.

### 4.3. Secret references

Configuration nên tham chiếu secret path/identity, không chứa secret value. Runtime/deployment system lấy secret từ secret manager theo quyền đã cấp.

### 4.4. Validation

Validate generated files trước khi apply. Kiểm tra syntax, duplicate settings, required parameters, path existence, file permissions và certificate expiry.

### 4.5. Promotion

Promote cùng versioned configuration artifact qua environments, thay values và secret references theo environment. Tránh tạo một bản config riêng không có lineage cho production.

## 5. PostgreSQL configuration files

PostgreSQL thường dùng nhiều files để cấu hình server.

### 5.1. postgresql.conf

File chính chứa server parameters như memory, connections, WAL, logging, replication và SSL.

### 5.2. postgresql.auto.conf

ALTER SYSTEM ghi settings vào postgresql.auto.conf trong data directory. File này được PostgreSQL đọc cùng configuration files và thường dùng cho overrides do ALTER SYSTEM tạo.

### 5.3. pg_hba.conf

Host-based authentication file quyết định client connections được phép và authentication method. Nó có lifecycle reload riêng.

### 5.4. pg_ident.conf

Map external identities sang PostgreSQL roles cho authentication methods hỗ trợ identity mapping, chẳng hạn certificate/ident.

### 5.5. Certificate/key files

Server certificate, private key, CA certificate và CRL thường nằm ngoài SQL catalogs. Path và file permissions phải phù hợp với service account và OS policy.

## 6. Configuration include và tổ chức files

Có thể tách cấu hình thành nhiều files để phân chia ownership và giảm conflict.

~~~conf
# postgresql.conf
include_dir = 'conf.d'
include_if_exists = 'local-overrides.conf'
~~~

### 6.1. include

Đọc file được chỉ định tại vị trí include trong configuration stream.

### 6.2. include_if_exists

Cho phép bỏ qua file không tồn tại. Dùng cẩn thận vì thiếu file có thể khiến một setting quan trọng không được áp dụng.

### 6.3. include_dir

Đọc các files cấu hình trong directory theo thứ tự được PostgreSQL quy định. Không dựa vào thứ tự ngẫu nhiên của deployment tooling.

### 6.4. Ownership theo file

Có thể chia files theo domain: connections, memory, WAL/replication, logging, SSL. Chỉ định owner/reviewer cho từng domain.

### 6.5. Tránh duplicate/conflicting settings

Một setting có thể được khai báo nhiều nơi; giá trị cuối cùng được áp dụng phụ thuộc thứ tự đọc/nguồn override. Dùng pg_settings.source và pg_file_settings để tìm nguồn effective value.

## 7. Configuration precedence và nguồn giá trị

Không nên chỉ đọc file rồi giả định PostgreSQL đang dùng giá trị đó.

### 7.1. Effective value

SHOW parameter hoặc pg_settings.setting cho biết giá trị PostgreSQL đang áp dụng trong session/server context.

~~~sql
SHOW max_connections;

SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'shared_buffers',
    'work_mem',
    'ssl',
    'shared_preload_libraries'
)
ORDER BY name;
~~~

### 7.2. Source

pg_settings.source cho biết nguồn setting, ví dụ default, configuration file, command line, database/role/session setting hoặc ALTER SYSTEM tùy context/version.

### 7.3. Source file và line

sourcefile/sourceline giúp truy nguyên file/line đã cung cấp giá trị. Một số nguồn không có file location.

### 7.4. pending_restart

pending_restart=true cho biết giá trị cấu hình mới cần restart để có hiệu lực. Giá trị đang chạy vẫn có thể khác giá trị file mong muốn.

### 7.5. Runtime overrides

SET ở session/role/database có thể làm giá trị session khác global default. Kiểm tra bằng đúng application role/session khi điều tra.

## 8. Kiểm tra file settings và lỗi cấu hình

pg_file_settings giúp xem các entries đọc từ configuration files và phát hiện lỗi.

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

### 8.1. applied

Cho biết entry có được áp dụng trong quá trình parse configuration hay không. Một entry có thể không được áp dụng vì bị override hoặc lỗi.

### 8.2. error

Hiển thị parse/validation issue. Kiểm tra trước reload/restart để tránh đưa config sai vào production.

### 8.3. Duplicate entries

Nhiều declarations cho cùng parameter có thể hợp lệ nhưng dễ gây nhầm. Xóa duplicate không cần thiết trong source of truth.

### 8.4. Permission/path errors

File include/certificate không đọc được có thể khiến reload/startup fail hoặc giữ config cũ. Kiểm tra service account permissions và server logs.

### 8.5. Không sửa file khi server đang dùng source khác

Nếu config được quản lý bởi operator, container image, orchestration hoặc cloud parameter group, sửa file trực tiếp có thể bị ghi đè. Thay đổi qua đúng control plane.

## 9. ALTER SYSTEM và giới hạn sử dụng

ALTER SYSTEM ghi một parameter vào postgresql.auto.conf.

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';
SELECT pg_reload_conf();
~~~

### 9.1. Use cases

ALTER SYSTEM hữu ích cho thay đổi server-level được DBA thực hiện có chủ đích và cần persist qua restart.

### 9.2. Không phải session command

ALTER SYSTEM không tương đương SET. Nó ghi cấu hình persistent cho cluster, không chỉ session hiện tại.

### 9.3. Không hỗ trợ mọi parameter context

Một số settings không thể thay bằng ALTER SYSTEM, chẳng hạn settings chỉ cho session/user context hoặc bị hạn chế theo parameter semantics.

### 9.4. Configuration drift

Nếu dùng ALTER SYSTEM ngoài config management, repository có thể không phản ánh runtime. Ghi change vào source of truth và reconcile auto.conf.

### 9.5. Không lưu secrets bằng ALTER SYSTEM

Không dùng auto.conf làm secret store. File có thể được đọc bởi users có quyền filesystem/DBA và thường được backup cùng data directory.

## 10. Reload và restart

Mỗi parameter có context xác định cách áp dụng.

| Context | Cách áp dụng điển hình |
|---|---|
| postmaster | Restart server |
| sighup | Reload configuration |
| superuser-backend | Backend/session mới hoặc privileged session theo setting |
| backend | Backend mới |
| superuser | Superuser có thể SET |
| user | User có thể SET |

### 10.1. Reload

pg_reload_conf() hoặc service reload gửi tín hiệu để PostgreSQL đọc lại các files reloadable như postgresql.conf và pg_hba.conf.

### 10.2. Restart

Settings có context postmaster cần server restart. Lên kế hoạch HA/maintenance khi restart ảnh hưởng availability.

### 10.3. Kiểm tra context

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN ('ssl', 'ssl_cert_file', 'shared_preload_libraries',
               'max_connections', 'log_min_duration_statement');
~~~

### 10.4. Reload không thay đổi mọi sessions

Một số settings được áp dụng cho backend mới hoặc connections mới. Existing sessions có thể giữ session-level values/SSL state đã thương lượng.

### 10.5. Xác nhận sau apply

Kiểm tra pg_settings, pg_file_settings, logs, pg_hba behavior và actual client connections. Command reload thành công không chứng minh mọi intended changes đã áp dụng.


## 11. Cấu hình theo database và role

Không phải mọi khác biệt giữa applications đều cần thay postgresql.conf. PostgreSQL cho phép đặt defaults theo database và role.

### 11.1. ALTER ROLE SET

~~~sql
ALTER ROLE reporting_app
SET statement_timeout = '30s';
~~~

Setting áp dụng cho sessions mới của role, trừ khi database/session có override theo precedence phù hợp.

### 11.2. ALTER DATABASE SET

~~~sql
ALTER DATABASE analytics
SET work_mem = '16MB';
~~~

Dùng khi database có workload/resource profile riêng. Đánh giá tổng memory theo số concurrent operations.

### 11.3. ALTER ROLE IN DATABASE

Có thể đặt setting cho một role trong một database cụ thể:

~~~sql
ALTER ROLE reporting_app IN DATABASE analytics
SET statement_timeout = '20s';
~~~

### 11.4. Session SET

Application có thể SET/SET LOCAL cho transaction/session nếu parameter context cho phép. SET LOCAL chỉ có hiệu lực tới hết transaction.

### 11.5. Reset và precedence

ALTER ROLE/DATABASE defaults được áp dụng khi session khởi tạo; application SET có thể override. Kiểm tra current_setting() trong đúng session khi debug.

## 12. Parameter context và môi trường

Không nên dùng cùng một giá trị cho mọi môi trường nếu capacity và workload khác nhau.

### 12.1. Connections

max_connections và pool sizing phụ thuộc instance size, app replicas, admin headroom và replication/worker connections.

### 12.2. Memory

shared_buffers, work_mem, maintenance_work_mem và effective_cache_size phải được chọn dựa trên RAM, concurrency và workload. work_mem có thể được dùng nhiều lần trong một query.

### 12.3. WAL/replication

wal_level, max_wal_senders, max_replication_slots, archive_mode và retention cần phù hợp topology. Một staging single-node không thể tự chứng minh production HA config.

### 12.4. Logging

log_min_duration_statement, log_line_prefix, log_connections/disconnections và logging_collector cần cân bằng visibility với storage/privacy.

### 12.5. SSL/authentication

Production thường cần policy TLS/authentication nghiêm hơn local development. Staging phải mô phỏng policy để phát hiện lỗi trước release.

## 13. Configuration drift

Configuration drift xảy ra khi runtime environments khác nhau ngoài những khác biệt đã được phê duyệt.

### 13.1. Drift sources

Manual edits, ALTER SYSTEM, emergency SET/ALTER ROLE, operator reconciliation, package defaults và deployment scripts có thể tạo drift.

### 13.2. Snapshot effective config

Định kỳ export pg_settings gồm name, setting, unit, source, context và pending_restart. Không export secret values từ mapping/password files.

### 13.3. Compare by policy

So sánh mỗi environment với baseline tương ứng. Một số values phải khác theo capacity/host, nhưng security parameters cần đạt cùng minimum policy.

### 13.4. Detect unknown overrides

Tìm source='database', 'user', 'client' hoặc file path không nằm trong expected inventory. Điều tra trước khi reset.

### 13.5. Reconcile

Đưa emergency changes vào source of truth hoặc revert bằng change record. Không để auto.conf/role settings tồn tại ngoài quản lý.

## 14. Cấu hình trong containers và orchestration

Containerized PostgreSQL vẫn cần một nguồn cấu hình có version và secret lifecycle rõ ràng.

### 14.1. Immutable image

Image chứa PostgreSQL binaries và packages/extensions; tránh build image chứa production secrets.

### 14.2. ConfigMap/config volume

Các settings không bí mật có thể được mount/inject qua orchestration config resources. Kiểm tra file ownership/path và reload strategy.

### 14.3. Secret volume

Passwords, private keys và certificates có thể được mount từ secret resources/CSI provider. Giới hạn service account access và filesystem permissions.

### 14.4. Reload behavior

Secret/config volume update không đồng nghĩa PostgreSQL tự reload. Controller/operator cần trigger reload hoặc rolling restart phù hợp.

### 14.5. Pod replacement

Khi pod thay thế, xác nhận secret version, cert, data volume, permissions và readiness probes đã đồng bộ. Không đưa secret vào image layer hoặc logs.

## 15. Secret lifecycle

Secret cần được quản lý từ lúc tạo đến lúc thu hồi.

### 15.1. Generate

Sinh secret bằng cryptographically secure random generator và độ dài/entropy phù hợp. Không dùng username, hostnames hoặc values đoán được.

### 15.2. Store

Lưu trong secret manager/vault/KMS-backed system hoặc secure OS credential store. Encrypt at rest và giới hạn principals có thể đọc.

### 15.3. Distribute

Cấp secret chỉ cho service identity cần sử dụng. Ưu tiên workload identity/short-lived credentials khi platform hỗ trợ.

### 15.4. Use

Inject ở runtime hoặc mount file có permission chặt. Tránh ghi secret vào command line, environment dumps, debug logs hoặc crash reports.

### 15.5. Rotate/revoke

Có owner, expiry/rotation cadence, overlap window, rollback procedure và cách thu hồi credential cũ sau khi consumers đã chuyển.

## 16. Secrets thường gặp trong PostgreSQL deployment

Inventory cần bao gồm cả credentials trực tiếp lẫn private keys.

| Secret | Consumer | Rotation consideration |
|---|---|---|
| Application DB password | Application/pooler | Dual credential hoặc staged rollout |
| Replication password | Standby/subscriber | Update sender/receiver config |
| Backup credential | Backup agent | Test backup/restore access |
| Monitoring password | Monitoring agent | Update scrape/exporter secrets |
| FDW remote password | postgres_fdw mapping | Update mapping và cached connections |
| Client private key | Application/client | Renew certificate/key pair |
| Server private key | PostgreSQL server | Deploy cert/key and reload/restart as required |
| Secret-manager token | Runtime workload | Short TTL and workload identity |

### 16.1. Per-service identity

Dùng role riêng cho application, migration, monitoring, backup, replication và FDW. Một password dùng chung làm tăng blast radius.

### 16.2. Environment separation

Không reuse credentials giữa staging và production. Nếu một environment bị compromise, credential đó không được mở đường vào environment khác.

### 16.3. Ownership

Mỗi secret có owner/service, purpose, consumers, expiry, rotation procedure và incident contact.

### 16.4. Inventory without values

Inventory secret names/IDs, version, owner và last rotation. Không đưa raw secret values vào report.

### 16.5. Emergency revocation

Có thể disable/revoke compromised credential nhanh, nhưng phải biết impact tới services/standbys/jobs trước khi thực hiện.

## 17. PostgreSQL role passwords

PostgreSQL lưu password verifier trong system catalog, không nên dùng plaintext password ở application configuration.

### 17.1. SCRAM-SHA-256

SCRAM-SHA-256 là password authentication method hiện đại được khuyến nghị thay cho MD5 trong deployments hỗ trợ.

### 17.2. Password encryption setting

~~~sql
SHOW password_encryption;
~~~

Đặt password_encryption='scram-sha-256' trước khi thiết lập/đổi passwords cho roles mới.

### 17.3. Tạo role

~~~sql
CREATE ROLE app_orders
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

### 17.4. Đặt password an toàn

Dùng psql command \password để tránh gõ plaintext password trực tiếp vào SQL command history theo cách dễ lộ. Tuân thủ secret manager và audit process của tổ chức.

### 17.5. Existing MD5 verifiers

Đổi password_encryption không tự chuyển verifier cũ. Cần rotate/reset password để tạo SCRAM verifier và cập nhật pg_hba.conf authentication method theo rollout plan.

## 18. pg_hba.conf và authentication policy

pg_hba.conf quyết định authentication method theo loại connection, database, role và client address.

~~~conf
# Local Unix socket example
local   all       all                         scram-sha-256

# Encrypted TCP clients
hostssl appdb     app_orders  10.20.0.0/16     scram-sha-256

# Reject unencrypted TCP for this database
hostnossl appdb   all         0.0.0.0/0        reject
~~~

### 18.1. First matching rule

PostgreSQL dùng rule đầu tiên match. Nếu authentication thất bại, nó không thử rule tiếp theo; thứ tự entries rất quan trọng.

### 18.2. hostssl

hostssl chỉ match TCP/IP connections dùng SSL/TLS. Nó không ép tất cả connections trong cluster phải TLS nếu có rules host/local khác cho phép.

### 18.3. hostnossl

hostnossl match TCP connections không dùng SSL. Có thể dùng reject rules để cấm plaintext cho các databases/subnets.

### 18.4. CIDR scope

Giới hạn source ranges theo application subnet, bastion, monitoring hoặc replication network. Tránh mở 0.0.0.0/0 nếu không có lý do/policy rõ.

### 18.5. Reload and inspect

Sau khi sửa pg_hba.conf, reload và xem pg_hba_file_rules để phát hiện parse errors/entries không như dự kiến.

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

## 19. Server-side TLS

TLS trên PostgreSQL bảo vệ network traffic giữa client và server và có thể cung cấp server identity.

### 19.1. Bật SSL

~~~conf
ssl = on
~~~

Parameter này thường cần restart server khi thay đổi từ off sang on hoặc ngược lại.

### 19.2. Server certificate

ssl_cert_file trỏ tới PEM certificate chain/server certificate. Certificate phải có subject alternative name (SAN) khớp hostname clients sử dụng.

### 19.3. Private key

ssl_key_file trỏ tới private key tương ứng. Bảo vệ file khỏi users không cần thiết; trên Unix-like systems thường dùng owner postgres và mode 0600.

### 19.4. Client CA

ssl_ca_file có thể chỉ CA dùng để verify client certificates khi server authentication yêu cầu client cert. Nó không thay thế việc client trust CA của server.

### 19.5. TLS protocol

Dùng ssl_min_protocol_version và certificate/cipher policy phù hợp với security baseline. Không bật protocol cũ chỉ để hỗ trợ client không còn được duy trì.


## 20. Client-side TLS verification

Client phải xác minh server certificate để chống kết nối nhầm hoặc man-in-the-middle.

### 20.1. sslmode

libpq cung cấp sslmode values như disable, allow, prefer, require, verify-ca và verify-full. Production clients nên dùng verify-full khi có thể.

### 20.2. verify-ca

Client xác minh certificate chain theo trusted CA nhưng không kiểm tra hostname identity đầy đủ như verify-full.

### 20.3. verify-full

Client xác minh certificate chain và hostname/IP mà client kết nối phải khớp certificate SAN. Đây là lựa chọn mạnh cho server identity verification.

### 20.4. sslrootcert

Chỉ định CA certificate bundle mà client tin cậy. Bảo vệ nguồn CA và chỉ phân phối trusted roots đã được phê duyệt.

### 20.5. Hostname consistency

Dùng DNS hostname nằm trong SAN. Kết nối bằng IP hoặc alias không có trong certificate có thể fail verify-full; không tắt verification để che lỗi hostname.

## 21. Client certificates và mutual TLS

Mutual TLS (mTLS) bổ sung client certificate authentication. Server xác minh client certificate theo CA trust policy.

### 21.1. Client certificate

Client giữ certificate và private key riêng. Certificate cần identity/subject phù hợp với role mapping policy.

### 21.2. Server trust

Server dùng ssl_ca_file để trust CA phát hành client certificate. CA nên được giới hạn theo PKI policy.

### 21.3. pg_hba cert method

~~~conf
hostssl appdb app_client 10.20.0.0/16 cert
~~~

Với cert method, PostgreSQL xác minh client certificate và đối chiếu certificate identity với database role hoặc identity mapping.

### 21.4. clientcert verification option

Có thể yêu cầu client certificate validation cùng authentication method khác bằng clientcert=verify-ca hoặc verify-full trên hostssl rule, theo version support.

### 21.5. pg_ident mapping

Nếu certificate CN không trùng role name, dùng pg_ident.conf map external identity sang PostgreSQL role và tham chiếu map trong pg_hba rule.

## 22. Phân biệt server authentication và client authentication

Hai hướng xác minh giải quyết hai câu hỏi khác nhau.

| Hướng | Cơ chế | Câu hỏi |
|---|---|---|
| Client xác minh server | sslmode=verify-full, sslrootcert | Tôi có kết nối đúng PostgreSQL server không? |
| Server xác minh client | ssl_ca_file, clientcert/cert, pg_ident | Client này có identity được tin cậy không? |
| Password authentication | SCRAM-SHA-256 | Client có biết credential hợp lệ không? |
| Network admission | pg_hba.conf | Connection source/database/role có được phép không? |

### 22.1. TLS không tự cấp quyền SQL

TLS xác minh/bảo vệ channel. PostgreSQL role privileges, schema/table grants và RLS vẫn quyết định dữ liệu client được truy cập.

### 22.2. Password qua TLS

SCRAM bảo vệ password authentication protocol; TLS tiếp tục bảo vệ traffic/query/results và xác minh server identity khi client dùng verify-full.

### 22.3. Certificate không thay role privileges

Client certificate xác thực identity theo rule, nhưng role đó vẫn cần CONNECT và object privileges.

### 22.4. Network controls

Firewall/security groups và pg_hba.conf vẫn cần policy rõ. TLS không thay thế network segmentation.

### 22.5. Layered policy

Kết hợp network admission, TLS identity, SCRAM/cert authentication, least-privilege roles và SQL authorization.

## 23. Cấu hình libpq client

libpq clients như psql, applications và nhiều drivers hỗ trợ TLS parameters.

~~~bash
psql "host=db.prod.example.internal port=5432 dbname=appdb user=app_orders sslmode=verify-full sslrootcert=/run/secrets/db-ca.pem"
~~~

### 23.1. sslmode

Đặt verify-full để yêu cầu mã hóa và kiểm tra hostname/certificate chain.

### 23.2. sslrootcert

Path tới CA bundle trusted. Cập nhật CA bundle theo rotation policy trước khi server chuyển sang CA mới nếu có overlap.

### 23.3. sslcert và sslkey

Chỉ định client certificate/private key nếu server yêu cầu certificate authentication hoặc client identity.

### 23.4. Connection URI

Connection URI có thể mang host, port, dbname, user và SSL parameters. Không nhúng password trong URI được log/monitor.

### 23.5. Service file

libpq service file có thể lưu connection parameters không nhạy cảm và tham chiếu passfile riêng. Phân quyền file theo OS account.

## 24. Bảo vệ password file và client credentials

Không nên truyền database password qua command line hoặc để lộ trong process listings/logs.

### 24.1. .pgpass

Trên Unix-like systems, libpq có thể đọc password file mặc định ~/.pgpass. File phải có permissions chặt, thường chmod 0600.

### 24.2. PGPASSFILE

Có thể chỉ định file khác qua PGPASSFILE để phân tách credentials theo service/environment.

### 24.3. Format và escaping

Mỗi dòng gồm host:port:database:username:password. Dấu colon và backslash trong fields cần escaping theo pgpass rules.

### 24.4. PGPASSWORD caution

Environment variable PGPASSWORD có thể bị lộ qua process environment/diagnostics trên một số platforms. Ưu tiên passfile hoặc secret injection mechanism an toàn.

### 24.5. Service identity

Passfile/private key phải được đọc bởi đúng OS account chạy PostgreSQL client/agent. Tránh quyền read rộng hoặc mount cùng một secret vào mọi containers.

## 25. Application connection configuration

Application nên nhận connection settings và credentials từ runtime configuration/secret provider.

### 25.1. Separate parameters

Giữ host, port, database, user, SSL mode và timeout thành cấu hình có thể validate. Secret password được inject riêng.

### 25.2. No secret in source

Không commit DSN có password, production .env, private keys hoặc client certificates vào Git.

### 25.3. No secret in logs

Redact passwords, tokens, full connection strings và sensitive certificate paths trong error reports/telemetry.

### 25.4. Connection pool

Pooler/application pool cần TLS settings đúng cho từng hop. Client-to-pooler TLS không tự đảm bảo pooler-to-PostgreSQL TLS.

### 25.5. Fail closed

Nếu production yêu cầu TLS verification, lỗi CA/hostname phải làm connection fail. Không tự fallback về plaintext/prefer để khắc phục outage.

## 26. TLS với connection poolers

Pooler có thể tạo hai TLS connections riêng: frontend client tới pooler và backend pooler tới PostgreSQL.

### 26.1. Frontend TLS

Ứng dụng xác minh pooler certificate. Pooler giữ server cert/key và có thể yêu cầu client cert tùy policy.

### 26.2. Backend TLS

Pooler xác minh PostgreSQL server certificate bằng CA/hostname policy và dùng client cert nếu remote PostgreSQL yêu cầu.

### 26.3. Authentication mapping

Pooler có thể xác thực client rồi dùng backend credentials khác để kết nối PostgreSQL. Xác định rõ trust boundary và audit identity.

### 26.4. Certificate rotation

Rotate frontend/backend certs theo từng hop, kiểm tra reload semantics và reconnect pool connections.

### 26.5. End-to-end identity

Nếu cần end-to-end client identity, thiết kế cách truyền/ủy quyền identity và audit rõ ràng. Không giả định PostgreSQL nhìn thấy certificate của application khi có pooler trung gian.

## 27. TLS cho replication và logical subscribers

Replication connections là database connections và cần cùng tiêu chuẩn TLS/authentication.

### 27.1. Physical standby

primary_conninfo có thể chứa host, user, passfile, sslmode và sslrootcert. Không ghi plaintext password vào configuration nếu có thể dùng passfile/secret mechanism.

### 27.2. Replication role

Tạo role REPLICATION/LOGIN riêng, giới hạn source network và không dùng superuser nếu không cần.

### 27.3. pg_hba replication rule

~~~conf
hostssl replication repl_user 10.30.0.0/16 scram-sha-256
~~~

### 27.4. Logical replication

Publisher/subscriber connection strings cũng cần SSL mode, CA trust, credential rotation và pg_hba policies. DDL/data replication không thay thế certificate management.

### 27.5. Failover readiness

Standby/DR node cần CA bundle, passfile/certificates và network policy đủ để tiếp tục kết nối sau promotion/repointing.

## 28. TLS cho postgres_fdw và các integrations

Mọi outbound database connection cần xác minh endpoint và secret lifecycle.

### 28.1. postgres_fdw server options

Có thể cấu hình sslmode, sslrootcert, sslcert, sslkey và libpq options phù hợp trong foreign server/user mapping options theo option support.

### 28.2. Per-user mapping

Remote password thuộc user mapping; giới hạn ai có thể inspect/manage mapping options và dùng remote roles ít quyền.

### 28.3. Remote server certificate

Dùng verify-full với hostname có trong SAN và CA bundle đúng. Không dùng verify-ca như tương đương hostname verification.

### 28.4. Rotation

Cập nhật credentials/certificates, test kết nối mới và quản lý cached FDW connections. Connection cũ có thể tiếp tục dùng session đã thiết lập.

### 28.5. Other integrations

Backup tools, monitoring exporters, ETL workers và migration runners cũng cần TLS/secret configuration riêng; không mặc định chúng kế thừa client settings của PostgreSQL server.

## 29. Certificate lifecycle

Certificate cần được quản lý từ issuance tới revocation.

### 29.1. Certificate request

Xác định subject/SAN, key algorithm/size, intended usage, validity period và CA policy.

### 29.2. Issuance

Dùng internal PKI hoặc public CA phù hợp. Server certificate phải có SAN khớp DNS names mà clients dùng.

### 29.3. Private key handling

Sinh/lưu private key trong protected path hoặc KMS/HSM-backed workflow nếu platform hỗ trợ. Không gửi private key qua chat/email hoặc commit vào repository.

### 29.4. Expiry monitoring

Theo dõi notBefore/notAfter, chain expiry và renewal lead time. Alert đủ sớm để test/deploy certificate mới.

### 29.5. Revocation

Có quy trình thu hồi compromised/obsolete certificates bằng CA/CRL hoặc identity policy. Test client/server behavior khi cert bị revoked.


## 30. Certificate rotation không gây outage

Rotation nên dùng overlap giữa trust cũ và mới để clients/servers có thời gian chuyển đổi.

### 30.1. Issue certificate mới

Tạo certificate/key mới từ approved CA, kiểm tra SAN, chain, validity và key permissions trước deployment.

### 30.2. Trust overlap

Nếu thay CA, phân phối CA bundle chứa cả CA cũ và CA mới tới clients trước khi server chuyển certificate. Chỉ loại CA cũ sau khi mọi clients đã migrate.

### 30.3. Deploy server certificate

Cài certificate/private key mới vào protected paths. Kiểm tra owner, permissions, chain order và file readability.

### 30.4. Reload/restart theo context

Kiểm tra pg_settings.context của SSL parameters. Reload hoặc restart theo requirement; sau đó mở kết nối mới và xác nhận certificate mới được sử dụng.

### 30.5. Drain old sessions

Existing TLS sessions đã thương lượng với certificate cũ không tự đổi certificate giữa connection. Recycle pool connections theo kế hoạch và xác nhận mọi clients đã chuyển.

## 31. Password rotation cho application roles

Password rotation phải tính cả clients, poolers, scheduled jobs và sessions đang tồn tại.

### 31.1. Inventory consumers

Liệt kê ứng dụng, poolers, migration runners, monitoring, batch jobs và admin tools đang dùng credential.

### 31.2. Same-role rotation

Đổi password của role làm authentication cho connections mới dùng credential mới. Existing sessions thường vẫn tiếp tục hoạt động cho tới khi disconnect.

### 31.3. Overlap strategy

Một role PostgreSQL chỉ có một password verifier hiện hành. Nếu cần overlap credentials, tạo login role mới với membership tương đương, chuyển consumers rồi disable/revoke login role cũ.

### 31.4. Update and reconnect

Cập nhật secret ở consumers, refresh pool connections và xác nhận new connections thành công. Không chỉ kiểm tra một psql session admin.

### 31.5. Revoke old credential

Sau khi xác nhận tất cả consumers đã chuyển, disable/drop old login role hoặc revoke credential theo plan. Drain old sessions và audit authentication failures.

## 32. Rotation cho replication, FDW và service accounts

Các integrations thường giữ connections dài hạn hoặc cache credentials.

### 32.1. Replication credentials

Cập nhật secret trong standby/subscriber connection configuration và kiểm tra receiver reconnect. Giữ replication role có privileges tối thiểu.

### 32.2. postgres_fdw mappings

ALTER USER MAPPING để cập nhật remote credentials. Xác định cached connections có cần disconnect/recycle hay không và test query bằng đúng local role.

### 32.3. Backup/monitoring agents

Cập nhật secrets ở agent/runtime config, test backup/restore hoặc scrape/query access rồi thu hồi credential cũ.

### 32.4. Scheduled jobs

Jobs có thể chạy theo lịch thưa và không lộ lỗi ngay sau rotation. Trigger controlled test run trước khi revoke old credential.

### 32.5. Rotation evidence

Ghi secret version, consumers updated, test results, old credential revocation time và exceptions. Không ghi raw secret vào evidence.

## 33. Client certificate rotation

Client certificates có thể được rotate độc lập với server certificate.

### 33.1. Issue client identity

Cấp certificate mới cho workload identity với subject/SAN và extended key usage phù hợp.

### 33.2. Install key/certificate

Cập nhật certificate/private key trên client host/container, bảo đảm ownership/permissions và CA chain.

### 33.3. Server trust

Đảm bảo PostgreSQL tin CA mới qua ssl_ca_file và pg_hba cert/clientcert policy. Reload theo configuration context.

### 33.4. Test new connections

Tạo kết nối mới bằng client certificate mới, kiểm tra authentication và identity mapping qua pg_ident nếu có.

### 33.5. Revoke old certificate

Sau khi tất cả clients đã chuyển, cập nhật CRL/identity policy nếu cần và thu hồi certificate cũ. Theo dõi lỗi certificate còn được dùng.

## 34. CA rotation và trust bundle

CA rotation phức tạp hơn đổi leaf certificate vì ảnh hưởng toàn bộ clients.

### 34.1. Add new CA first

Phân phối trust bundle có cả CA cũ và mới tới clients, poolers, FDW hosts, replication nodes và monitoring agents.

### 34.2. Verify trust deployment

Kiểm tra fingerprint của CA bundle đã triển khai ở từng environment/node. Tránh dùng bundle khác nhau ngoài kế hoạch.

### 34.3. Switch issuer

Phát hành/deploy server/client certificates từ CA mới theo từng nhóm. Duy trì overlap để rollback nếu cần.

### 34.4. Remove old CA

Chỉ bỏ CA cũ sau khi inventory xác nhận không còn active certificates được ký bởi CA đó.

### 34.5. Revocation/incident

Nếu CA cũ bị compromise, overlap có thể không an toàn; áp dụng emergency revocation plan và chấp nhận reconnect/availability impact theo incident policy.

## 35. TLS observability trong PostgreSQL

Cần xác nhận connection thực tế dùng TLS và protocol/cipher mong đợi.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits,
    s.client_dn,
    s.client_serial
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend'
ORDER BY a.application_name, a.usename;
~~~

### 35.1. ssl

Cho biết connection có sử dụng SSL/TLS hay không.

### 35.2. version và cipher

Hiển thị negotiated TLS protocol/cipher cho connection. So với security baseline của environment.

### 35.3. client_dn và client_serial

Có thể cung cấp thông tin client certificate nếu client certificate được dùng. Không phải mọi password-authenticated TLS connection đều có client certificate.

### 35.4. Session sampling

pg_stat_ssl phản ánh connections hiện tại. Kiểm tra trong lúc application traffic chạy và sau pool recycle để xác nhận clients mới.

### 35.5. Client-side verification

Server view chứng minh TLS được dùng, nhưng client phải tự xác minh server identity bằng verify-full/CA policy. Hai phía cần evidence riêng.

## 36. Kiểm tra kết nối từ psql và libpq

Các công cụ client giúp xác nhận TLS/authentication path.

### 36.1. Connection details

Trong psql, dùng \conninfo để xem connection parameters và trạng thái SSL hiển thị cho client.

### 36.2. Explicit SSL mode

Dùng connection string có sslmode=verify-full và sslrootcert trỏ CA bundle đã phê duyệt.

### 36.3. Negative hostname test

Trong test environment, thử hostname không khớp certificate để xác nhận verify-full từ chối kết nối.

### 36.4. Negative CA test

Thử CA không tin cậy trong lab và xác nhận client từ chối handshake/verification.

### 36.5. No plaintext fallback

Kiểm tra client configuration không tự chuyển sang disable/allow/prefer khi TLS verification fail nếu production policy yêu cầu TLS bắt buộc.

## 37. Logging và audit cho configuration/security changes

Thay đổi config, roles và certificates cần có record để điều tra và compliance.

### 37.1. Change identity

Ghi người/service thực hiện, ticket/change ID, environment, timestamp và approval.

### 37.2. Configuration diff

Lưu diff của non-secret settings trước/sau, effective source và pending_restart. Redact paths/values nhạy cảm khi cần.

### 37.3. Role changes

Audit CREATE/ALTER/DROP ROLE, grants, memberships, password rotation và authentication failures theo policy.

### 37.4. Certificate events

Ghi certificate serial/fingerprint, issuer, validity, deployment nodes, reload/restart result và old certificate retirement.

### 37.5. Logs redaction

Không log passwords, private key contents, tokens hoặc full connection strings có credentials. Kiểm tra cả application logs, CI output và support bundles.

## 38. Environment parity và test matrix

Test authentication/configuration ở mọi đường kết nối và environment.

| Test | Development | CI/Test | Staging | Production/DR |
|---|---|---|---|---|
| Correct config source | Có | Có | Có | Có |
| SCRAM authentication | Có thể | Có | Có | Có |
| TLS encryption | Nên | Có | Bắt buộc theo policy | Bắt buộc theo policy |
| verify-full | Nên | Có | Có | Có |
| Client certificate | Khi cần | Lab test | Nếu production dùng | Nếu production dùng |
| Secret rotation | Test flow | Automated test | Rehearsal | Controlled change |
| Certificate expiry alert | Test | Test | Có | Có |
| Reload/restart behavior | Có | Có | Có | Change-controlled |
| Failover/DR credentials | Không bắt buộc | Simulated | Rehearsal | Có |

### 38.1. Same security baseline

Staging nên dùng cùng authentication/TLS policy với production, dù certificate và credentials khác.

### 38.2. Environment-specific identities

Mỗi environment có DB roles, passwords, client certificates và CA trust theo policy. Không copy production secrets sang lower environments.

### 38.3. Negative tests

Test wrong password, wrong CA, wrong hostname, expired cert, unauthorized role và plaintext connection rejection.

### 38.4. Restart/reload tests

Xác nhận service manager/operator thực hiện đúng reload/restart và readiness checks không báo healthy trước khi server nhận kết nối theo policy.

### 38.5. DR tests

Test secret manager availability, CA trust, certificate expiry và connection strings khi failover sang DR endpoint.

## 39. Managed PostgreSQL services

Managed database có thể giới hạn quyền truy cập filesystem và cách cấu hình.

### 39.1. Parameter groups

Một số settings được cấu hình qua provider parameter groups thay vì sửa postgresql.conf trực tiếp.

### 39.2. Certificate bundles

Provider có thể cung cấp CA bundle và yêu cầu clients cập nhật khi endpoint certificate/CA thay đổi.

### 39.3. Secret integrations

Dùng provider secret manager/workload identity khi có hỗ trợ. Không giả định database service tự inject application credentials.

### 39.4. Authentication features

Client certificate, IAM/token authentication và SCRAM support khác nhau theo provider/version. Kiểm tra service documentation và test endpoint thực tế.

### 39.5. Provider rotation notices

Theo dõi maintenance/CA rotation notices và deadline. Rehearse trust bundle updates trước ngày provider enforce new CA.

## 40. Troubleshooting: cấu hình không có hiệu lực

### 40.1. Effective value

Dùng SHOW và pg_settings để xác định runtime value, source, context và pending_restart.

### 40.2. File parsing

Dùng pg_file_settings để tìm errors, duplicate entries và sourcefile/sourceline.

### 40.3. Include order

Kiểm tra include/include_dir và file precedence. Một setting ở file được đọc sau có thể override giá trị trước.

### 40.4. Restart requirement

Nếu pending_restart=true hoặc context=postmaster, reload không đủ. Lên lịch restart/HA switchover phù hợp.

### 40.5. Control plane

Với operator/managed service, xác định source of truth là custom resource/parameter group. Manual file edits có thể bị reconcile/overwrite.


## 30. Certificate rotation không gây outage

Rotation nên dùng overlap giữa trust cũ và mới để clients/servers có thời gian chuyển đổi.

### 30.1. Issue certificate mới

Tạo certificate/key mới từ approved CA, kiểm tra SAN, chain, validity và key permissions trước deployment.

### 30.2. Trust overlap

Nếu thay CA, phân phối CA bundle chứa cả CA cũ và CA mới tới clients trước khi server chuyển certificate. Chỉ loại CA cũ sau khi mọi clients đã migrate.

### 30.3. Deploy server certificate

Cài certificate/private key mới vào protected paths. Kiểm tra owner, permissions, chain order và file readability.

### 30.4. Reload/restart theo context

Kiểm tra pg_settings.context của SSL parameters. Reload hoặc restart theo requirement; sau đó mở kết nối mới và xác nhận certificate mới được sử dụng.

### 30.5. Drain old sessions

Existing TLS sessions đã thương lượng với certificate cũ không tự đổi certificate giữa connection. Recycle pool connections theo kế hoạch và xác nhận mọi clients đã chuyển.

## 31. Password rotation cho application roles

Password rotation phải tính cả clients, poolers, scheduled jobs và sessions đang tồn tại.

### 31.1. Inventory consumers

Liệt kê ứng dụng, poolers, migration runners, monitoring, batch jobs và admin tools đang dùng credential.

### 31.2. Same-role rotation

Đổi password của role làm authentication cho connections mới dùng credential mới. Existing sessions thường vẫn tiếp tục hoạt động cho tới khi disconnect.

### 31.3. Overlap strategy

Một role PostgreSQL chỉ có một password verifier hiện hành. Nếu cần overlap credentials, tạo login role mới với membership tương đương, chuyển consumers rồi disable/revoke login role cũ.

### 31.4. Update and reconnect

Cập nhật secret ở consumers, refresh pool connections và xác nhận new connections thành công. Không chỉ kiểm tra một psql session admin.

### 31.5. Revoke old credential

Sau khi xác nhận tất cả consumers đã chuyển, disable/drop old login role hoặc revoke credential theo plan. Drain old sessions và audit authentication failures.

## 32. Rotation cho replication, FDW và service accounts

Các integrations thường giữ connections dài hạn hoặc cache credentials.

### 32.1. Replication credentials

Cập nhật secret trong standby/subscriber connection configuration và kiểm tra receiver reconnect. Giữ replication role có privileges tối thiểu.

### 32.2. postgres_fdw mappings

ALTER USER MAPPING để cập nhật remote credentials. Xác định cached connections có cần disconnect/recycle hay không và test query bằng đúng local role.

### 32.3. Backup/monitoring agents

Cập nhật secrets ở agent/runtime config, test backup/restore hoặc scrape/query access rồi thu hồi credential cũ.

### 32.4. Scheduled jobs

Jobs có thể chạy theo lịch thưa và không lộ lỗi ngay sau rotation. Trigger controlled test run trước khi revoke old credential.

### 32.5. Rotation evidence

Ghi secret version, consumers updated, test results, old credential revocation time và exceptions. Không ghi raw secret vào evidence.

## 33. Client certificate rotation

Client certificates có thể được rotate độc lập với server certificate.

### 33.1. Issue client identity

Cấp certificate mới cho workload identity với subject/SAN và extended key usage phù hợp.

### 33.2. Install key/certificate

Cập nhật certificate/private key trên client host/container, bảo đảm ownership/permissions và CA chain.

### 33.3. Server trust

Đảm bảo PostgreSQL tin CA mới qua ssl_ca_file và pg_hba cert/clientcert policy. Reload theo configuration context.

### 33.4. Test new connections

Tạo kết nối mới bằng client certificate mới, kiểm tra authentication và identity mapping qua pg_ident nếu có.

### 33.5. Revoke old certificate

Sau khi tất cả clients đã chuyển, cập nhật CRL/identity policy nếu cần và thu hồi certificate cũ. Theo dõi lỗi certificate còn được dùng.

## 34. CA rotation và trust bundle

CA rotation phức tạp hơn đổi leaf certificate vì ảnh hưởng toàn bộ clients.

### 34.1. Add new CA first

Phân phối trust bundle có cả CA cũ và mới tới clients, poolers, FDW hosts, replication nodes và monitoring agents.

### 34.2. Verify trust deployment

Kiểm tra fingerprint của CA bundle đã triển khai ở từng environment/node. Tránh dùng bundle khác nhau ngoài kế hoạch.

### 34.3. Switch issuer

Phát hành/deploy server/client certificates từ CA mới theo từng nhóm. Duy trì overlap để rollback nếu cần.

### 34.4. Remove old CA

Chỉ bỏ CA cũ sau khi inventory xác nhận không còn active certificates được ký bởi CA đó.

### 34.5. Revocation/incident

Nếu CA cũ bị compromise, overlap có thể không an toàn; áp dụng emergency revocation plan và chấp nhận reconnect/availability impact theo incident policy.

## 35. TLS observability trong PostgreSQL

Cần xác nhận connection thực tế dùng TLS và protocol/cipher mong đợi.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits,
    s.client_dn,
    s.client_serial
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend'
ORDER BY a.application_name, a.usename;
~~~

### 35.1. ssl

Cho biết connection có sử dụng SSL/TLS hay không.

### 35.2. version và cipher

Hiển thị negotiated TLS protocol/cipher cho connection. So với security baseline của environment.

### 35.3. client_dn và client_serial

Có thể cung cấp thông tin client certificate nếu client certificate được dùng. Không phải mọi password-authenticated TLS connection đều có client certificate.

### 35.4. Session sampling

pg_stat_ssl phản ánh connections hiện tại. Kiểm tra trong lúc application traffic chạy và sau pool recycle để xác nhận clients mới.

### 35.5. Client-side verification

Server view chứng minh TLS được dùng, nhưng client phải tự xác minh server identity bằng verify-full/CA policy. Hai phía cần evidence riêng.

## 36. Kiểm tra kết nối từ psql và libpq

Các công cụ client giúp xác nhận TLS/authentication path.

### 36.1. Connection details

Trong psql, dùng lệnh \conninfo để xem connection parameters và trạng thái SSL hiển thị cho client.

### 36.2. Explicit SSL mode

Dùng connection string có sslmode=verify-full và sslrootcert trỏ CA bundle đã phê duyệt.

### 36.3. Negative hostname test

Trong test environment, thử hostname không khớp certificate để xác nhận verify-full từ chối kết nối.

### 36.4. Negative CA test

Thử CA không tin cậy trong lab và xác nhận client từ chối handshake/verification.

### 36.5. No plaintext fallback

Kiểm tra client configuration không tự chuyển sang disable/allow/prefer khi TLS verification fail nếu production policy yêu cầu TLS bắt buộc.

## 37. Logging và audit cho configuration/security changes

Thay đổi config, roles và certificates cần có record để điều tra và compliance.

### 37.1. Change identity

Ghi người/service thực hiện, ticket/change ID, environment, timestamp và approval.

### 37.2. Configuration diff

Lưu diff của non-secret settings trước/sau, effective source và pending_restart. Redact paths/values nhạy cảm khi cần.

### 37.3. Role changes

Audit CREATE/ALTER/DROP ROLE, grants, memberships, password rotation và authentication failures theo policy.

### 37.4. Certificate events

Ghi certificate serial/fingerprint, issuer, validity, deployment nodes, reload/restart result và old certificate retirement.

### 37.5. Logs redaction

Không log passwords, private key contents, tokens hoặc full connection strings có credentials. Kiểm tra cả application logs, CI output và support bundles.

## 38. Environment parity và test matrix

Test authentication/configuration ở mọi đường kết nối và environment.

| Test | Development | CI/Test | Staging | Production/DR |
|---|---|---|---|---|
| Correct config source | Có | Có | Có | Có |
| SCRAM authentication | Có thể | Có | Có | Có |
| TLS encryption | Nên | Có | Bắt buộc theo policy | Bắt buộc theo policy |
| verify-full | Nên | Có | Có | Có |
| Client certificate | Khi cần | Lab test | Nếu production dùng | Nếu production dùng |
| Secret rotation | Test flow | Automated test | Rehearsal | Controlled change |
| Certificate expiry alert | Test | Test | Có | Có |
| Reload/restart behavior | Có | Có | Có | Change-controlled |
| Failover/DR credentials | Không bắt buộc | Simulated | Rehearsal | Có |

### 38.1. Same security baseline

Staging nên dùng cùng authentication/TLS policy với production, dù certificate và credentials khác.

### 38.2. Environment-specific identities

Mỗi environment có DB roles, passwords, client certificates và CA trust theo policy. Không copy production secrets sang lower environments.

### 38.3. Negative tests

Test wrong password, wrong CA, wrong hostname, expired cert, unauthorized role và plaintext connection rejection.

### 38.4. Restart/reload tests

Xác nhận service manager/operator thực hiện đúng reload/restart và readiness probes không báo healthy trước khi server nhận kết nối theo policy.

### 38.5. DR tests

Test secret manager availability, CA trust, certificate expiry và connection strings khi failover sang DR endpoint.

## 39. Managed PostgreSQL services

Managed database có thể giới hạn quyền truy cập filesystem và cách cấu hình.

### 39.1. Parameter groups

Một số settings được cấu hình qua provider parameter groups thay vì sửa postgresql.conf trực tiếp.

### 39.2. Certificate bundles

Provider có thể cung cấp CA bundle và yêu cầu clients cập nhật khi endpoint certificate/CA thay đổi.

### 39.3. Secret integrations

Dùng provider secret manager/workload identity khi có hỗ trợ. Không giả định database service tự inject application credentials.

### 39.4. Authentication features

Client certificate, IAM/token authentication và SCRAM support khác nhau theo provider/version. Kiểm tra service documentation và test endpoint thực tế.

### 39.5. Provider rotation notices

Theo dõi maintenance/CA rotation notices và deadline. Rehearse trust bundle updates trước ngày provider enforce new CA.


## 40. Troubleshooting: cấu hình không có hiệu lực

### 40.1. Effective value

Dùng SHOW và pg_settings để xác định runtime value, source, context và pending_restart.

### 40.2. File parsing

Dùng pg_file_settings để tìm errors, duplicate entries và sourcefile/sourceline.

### 40.3. Include order

Kiểm tra include/include_dir và file precedence. Một setting ở file được đọc sau có thể override giá trị trước.

### 40.4. Restart requirement

Nếu pending_restart=true hoặc context=postmaster, reload không đủ. Lên lịch restart/HA switchover phù hợp.

### 40.5. Control plane

Với operator/managed service, xác định source of truth là custom resource/parameter group. Manual file edits có thể bị reconcile/overwrite.

## 41. Troubleshooting: TLS handshake hoặc certificate verification thất bại

### 41.1. Certificate expired/not yet valid

Kiểm tra notBefore/notAfter, clock synchronization trên client/server và intermediate certificate chain.

### 41.2. Hostname mismatch

Đảm bảo hostname trong connection string nằm trong SAN của server certificate. Đổi endpoint alias hoặc cấp certificate đúng SAN; không hạ sslmode để né mismatch.

### 41.3. Unknown CA

Kiểm tra client sslrootcert có đúng CA bundle và chain cần thiết không. Không thêm CA tùy tiện từ certificate không xác minh nguồn.

### 41.4. Key permissions

PostgreSQL có thể từ chối private key có permissions quá rộng hoặc owner không phù hợp. Kiểm tra service account, ownership và mode theo OS.

### 41.5. Protocol/cipher mismatch

Đối chiếu server/client TLS capabilities và ssl_min_protocol_version/cipher policy. Nâng client library thay vì hạ security baseline một cách tùy tiện.

## 42. Troubleshooting: client certificate bị từ chối

### 42.1. Client certificate chain

Xác nhận certificate được ký bởi CA mà server trust qua ssl_ca_file và chain đầy đủ.

### 42.2. Certificate identity

Kiểm tra CN/subject mapping, pg_ident.conf map và role name. Identity mismatch có thể làm cert authentication fail.

### 42.3. pg_hba rule order

Kiểm tra rule đầu tiên match connection. Một rule host/hostssl khác đứng trước có thể chọn auth method khác mong đợi.

### 42.4. Client certificate validity

Kiểm tra expiry, key usage/extended key usage và CRL/revocation state theo PKI policy.

### 42.5. Logs

Đọc PostgreSQL server logs để phân biệt no matching HBA rule, CA verification, certificate identity và SQL privilege errors.

## 43. Troubleshooting: SCRAM authentication failed

### 43.1. Password verifier

Xác nhận password đã được đặt/reset sau khi password_encryption chuyển sang scram-sha-256. Setting mới không tự chuyển verifier cũ.

### 43.2. Client driver support

Kiểm tra libpq/driver version hỗ trợ SCRAM-SHA-256. Nâng driver trước khi chuyển policy production nếu có clients cũ.

### 43.3. Role/login state

Kiểm tra role LOGIN, VALID UNTIL và account state. Xác nhận application dùng đúng role/database.

### 43.4. Mapping/secret version

Đối chiếu secret version đang inject với password hiện tại ở PostgreSQL. Kiểm tra stale pooler/app secrets.

### 43.5. HBA match

Xác định đúng pg_hba rule và authentication method được áp dụng. Đừng sửa một rule không match source connection.

## 44. Troubleshooting: app vẫn dùng credential/certificate cũ

### 44.1. Connection pool

Pool có thể giữ existing sessions sau rotation. Drain/recycle connections theo policy.

### 44.2. Cached credentials

Một process có thể chỉ đọc secret lúc startup. Reload/restart application hoặc secret watcher theo thiết kế.

### 44.3. PostgreSQL backend sessions

Đổi password không tự disconnect authenticated sessions hiện tại. Xác định sessions cũ và terminate/drain có kiểm soát nếu cần.

### 44.4. FDW cached connections

postgres_fdw có thể giữ remote connections trong backend. Cần test reconnect/disconnect behavior sau user mapping rotation.

### 44.5. Consumer inventory

Tìm cron jobs, workers, exporters và failover nodes chưa được cập nhật. Credential cũ chỉ nên revoke sau khi xác nhận toàn bộ consumers.

## 45. Troubleshooting: pg_hba.conf reload lỗi

### 45.1. pg_hba_file_rules

Kiểm tra error column, line_number, type, database, user_name, address và auth_method.

### 45.2. Syntax

Kiểm tra CIDR, quoting, method options, map names và field separators. Một lỗi cú pháp có thể làm entries không được parse.

### 45.3. First match

Kiểm tra thứ tự rules. Rule đầu tiên match được dùng; PostgreSQL không fallback sang rule tiếp theo khi authentication fail.

### 45.4. Reload confirmation

Gọi pg_reload_conf() và kiểm tra server logs/pg_hba_file_rules. Kết quả true của function chỉ cho biết signal đã được gửi.

### 45.5. Existing sessions

Thay đổi HBA áp dụng cho connection attempts mới; không tự ngắt sessions đã authenticated. Test bằng một kết nối mới từ đúng source network.

## 46. Ví dụ: cấu hình PostgreSQL theo môi trường

Ví dụ minh họa các khác biệt thường gặp. Giá trị phải điều chỉnh theo capacity và security policy.

| Setting | Development | Staging | Production |
|---|---|---|---|
| max_connections | Nhỏ | Gần production topology | Theo pool/capacity budget |
| log_min_duration_statement | Có thể thấp để debug | Theo test policy | Theo observability budget |
| ssl | Theo local policy | On | On |
| Authentication | SCRAM | SCRAM/TLS | SCRAM/TLS hoặc mTLS |
| sslmode client | verify-full khi test TLS | verify-full | verify-full |
| Backup | Disposable/local | Rehearsal | Policy/RPO/RTO |
| Secrets | Local-only | Staging secret scope | Central secret manager |
| Certificates | Test CA | Staging CA | Approved production PKI |

### 46.1. Không copy nguyên production config vào dev

Production values có thể không phù hợp tài nguyên dev và có thể mang internal topology details. Dùng cùng schema/template, values riêng.

### 46.2. Staging là security rehearsal

Staging nên mô phỏng auth/TLS, rotation, HBA, pooler và failover behavior. Nếu staging dùng trust-all còn production verify-full, lỗi certificate sẽ chỉ xuất hiện khi release.

### 46.3. Production baseline

Lưu approved config artifact, parameter source, secret references và certificate fingerprints.

### 46.4. DR parity

DR cần values theo topology DR nhưng cùng security controls, roles, trust chain và secret availability.

### 46.5. Change record

Mỗi deviation cần owner, reason, expiry/review date và rollback path.

## 47. Ví dụ: triển khai server TLS và SCRAM

Các lệnh dưới đây minh họa flow. File paths, role names và addresses cần thay theo environment.

### 47.1. Server configuration

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
password_encryption = 'scram-sha-256'
~~~

Đảm bảo certificate SAN khớp hostname và private key có permissions phù hợp.

### 47.2. HBA policy

~~~conf
hostssl appdb app_orders 10.20.0.0/16 scram-sha-256
hostnossl appdb all       10.20.0.0/16 reject
~~~

Rule order và các rules khác phải được xem trong context toàn bộ file.

### 47.3. Role

~~~sql
CREATE ROLE app_orders
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

Đặt password bằng secure workflow/psql \password và cấp database/schema/table privileges cần thiết.

### 47.4. Apply

Kiểm tra pg_file_settings và pg_hba_file_rules. Reload các settings reloadable; restart nếu context yêu cầu.

### 47.5. Client test

~~~bash
psql "host=db.prod.example.internal dbname=appdb user=app_orders sslmode=verify-full sslrootcert=/run/secrets/db-ca.pem"
~~~

Xác nhận \conninfo, pg_stat_ssl và application logs bằng connection mới.

## 48. Ví dụ: password rotation với role overlap

Một ứng dụng cần chuyển credential mà không phải đổi password verifier của cùng role tại đúng một thời điểm.

### 48.1. Tạo group role

~~~sql
CREATE ROLE app_orders_privileges NOLOGIN;
GRANT CONNECT ON DATABASE appdb TO app_orders_privileges;
GRANT USAGE ON SCHEMA app TO app_orders_privileges;
GRANT SELECT, INSERT, UPDATE ON app.orders TO app_orders_privileges;
~~~

### 48.2. Tạo login identity mới

~~~sql
CREATE ROLE app_orders_v2 LOGIN;
GRANT app_orders_privileges TO app_orders_v2;
~~~

Đặt password riêng cho app_orders_v2 qua secure channel.

### 48.3. Deploy consumer

Cập nhật một nhóm application instances/poolers sang login role mới. Test authentication, grants, RLS, connection pool và query behavior.

### 48.4. Migrate remaining consumers

Chuyển scheduled jobs, workers, monitoring và failover processes. Kiểm tra sessions/connection logs để xác nhận không còn old login.

### 48.5. Revoke old login

Sau khi xác nhận toàn bộ consumers, disable/drop old login role theo policy. Giữ audit record về thời điểm và kết quả rotation.


## 49. Ví dụ: certificate rotation

### 49.1. Kiểm tra expiry

Ghi fingerprint, issuer, SAN và expiry của certificate đang sử dụng. Xác định tất cả clients tin cậy CA hiện tại.

### 49.2. Distribute trust

Nếu CA thay đổi, triển khai CA bundle overlap tới applications, poolers, FDW hosts, replication nodes và monitoring trước.

### 49.3. Deploy new server cert

Cài server certificate/key mới với SAN đúng, kiểm tra chain và permissions.

### 49.4. Reload/restart và verify

Áp dụng theo pg_settings.context, tạo connections mới với verify-full và xác nhận pg_stat_ssl/client verification.

### 49.5. Drain old sessions and retire

Recycle pools, xác nhận không còn connections dùng certificate cũ, sau đó remove old trust/certificate theo rotation plan.

## 50. Configuration and secret deployment checklist

Một deployment change nên đi qua các bước có thể audit và rollback.

1. Xác định environment, owner, change ID và mục tiêu.
2. Lấy config baseline/effective values hiện tại.
3. Thay template/values trong source of truth; không ghi secret values vào repository.
4. Lấy secrets/certificates từ approved manager/PKI.
5. Validate syntax, required settings, paths, file ownership và expiry.
6. Render config và inspect diff đã redact.
7. Test trên staging bằng application/replication/pooler clients thực tế.
8. Deploy theo từng node/role hoặc qua operator/parameter group.
9. Reload/restart theo context và kiểm tra pending_restart.
10. Test new connections, auth/TLS identity, permissions và application health.
11. Theo dõi errors/latency/connection churn và replication.
12. Revoke old secrets/certs sau khi consumer inventory xác nhận đã chuyển.
13. Lưu evidence và cập nhật inventory/expiry/rotation schedule.

## 51. Những lỗi thường gặp

1. Dùng một config file khác nhau hoàn toàn ở từng environment mà không có shared baseline.
2. Chỉ đọc postgresql.conf mà bỏ qua postgresql.auto.conf và include files.
3. Không kiểm tra pg_settings.source/sourcefile/pending_restart.
4. Dùng ALTER SYSTEM ngoài source of truth mà không reconcile.
5. Nghĩ pg_reload_conf áp dụng mọi setting cần restart.
6. Nghĩ reload pg_hba.conf ngắt sessions đã authenticated.
7. Đưa password/private key vào Git, image, command line hoặc logs.
8. Dùng PGPASSWORD trong môi trường có process environment visibility.
9. Reuse database passwords giữa development/staging/production.
10. Dùng một shared login cho application, backup, monitoring và replication.
11. Chuyển pg_hba sang SCRAM trước khi kiểm tra client driver support/verifiers.
12. Bật TLS nhưng client chỉ dùng prefer/không xác minh hostname.
13. Dùng verify-ca và cho rằng nó tương đương verify-full.
14. Certificate thiếu SAN hoặc hostname trong connection string không khớp.
15. Private key có file permissions quá rộng.
16. Cấu hình client TLS nhưng quên pooler backend connection.
17. Rotate password nhưng quên pool connections và scheduled jobs.
18. Rotate CA/certificate mà không có trust overlap hoặc rollback plan.
19. Chỉ kiểm tra một connection admin thay vì application role thật.
20. Không chuẩn bị secrets/certificates ở standby/DR.
21. Không theo dõi expiry/rotation deadlines.
22. Không kiểm tra TLS/authentication failure trong negative tests.

## 52. Bài tập thực hành

### Bài 1 — Phân loại

Phân biệt configuration, secret và trust material.

**Đáp án:** Configuration điều khiển behavior; secret xác thực/truy cập; trust material xác định certificate/key identities được tin cậy.

### Bài 2 — Environment

Vì sao staging cần security policy gần production?

**Đáp án:** Để phát hiện lỗi authentication/TLS/rotation trước khi release.

### Bài 3 — Configuration files

ALTER SYSTEM ghi vào file nào?

**Đáp án:** postgresql.auto.conf trong data directory.

### Bài 4 — Effective setting

View nào cho biết sourcefile và pending_restart?

**Đáp án:** pg_settings.

### Bài 5 — File parse

View nào giúp kiểm tra configuration entries/errors?

**Đáp án:** pg_file_settings.

### Bài 6 — Reload

pg_reload_conf có restart server không?

**Đáp án:** Không; nó yêu cầu reload configuration.

### Bài 7 — Parameter context

Setting context=postmaster cần gì?

**Đáp án:** Restart PostgreSQL để áp dụng thay đổi.

### Bài 8 — Role defaults

ALTER ROLE SET áp dụng khi nào?

**Đáp án:** Khi sessions mới của role được khởi tạo, trừ khi bị override.

### Bài 9 — Secrets

Vì sao không lưu password trong Git?

**Đáp án:** Repository history/clone/logs làm secret khó thu hồi và mở rộng blast radius.

### Bài 10 — SCRAM

password_encryption='scram-sha-256' có tự convert password verifier cũ không?

**Đáp án:** Không; cần reset/rotate password.

### Bài 11 — HBA

PostgreSQL dùng rule pg_hba.conf nào?

**Đáp án:** Rule đầu tiên match connection; authentication failure không chuyển sang rule kế tiếp.

### Bài 12 — hostssl

hostssl match loại connections nào?

**Đáp án:** TCP/IP connections có SSL/TLS.

### Bài 13 — Server TLS

ssl_cert_file và ssl_key_file chứa gì?

**Đáp án:** Server certificate và private key tương ứng.

### Bài 14 — Client trust

sslrootcert ở libpq dùng làm gì?

**Đáp án:** Cung cấp trusted CA bundle để xác minh server certificate.

### Bài 15 — verify-full

verify-full xác minh thêm điều gì so với verify-ca?

**Đáp án:** Hostname/IP của endpoint khớp certificate identity.

### Bài 16 — mTLS

Server cần gì để xác minh client certificate?

**Đáp án:** Trusted client CA, pg_hba cert/clientcert policy và identity mapping nếu cần.

### Bài 17 — TLS và SQL privileges

TLS có cấp quyền SELECT table không?

**Đáp án:** Không; SQL privileges/RLS vẫn kiểm soát access.

### Bài 18 — Existing sessions

Đổi password có tự ngắt existing sessions không?

**Đáp án:** Không; connections đã authenticated thường tiếp tục cho tới khi disconnect.

### Bài 19 — Rotation overlap

Một PostgreSQL role có thể giữ hai password verifier active đồng thời theo cách thông thường không?

**Đáp án:** Không; dùng role overlap riêng nếu cần chuyển đổi credentials không gián đoạn.

### Bài 20 — Certificate rotation

Vì sao phải phân phối CA mới trước khi đổi server certificate?

**Đáp án:** Clients cần trust CA mới trước khi nhận certificate được CA đó ký.

### Bài 21 — Pooler

TLS client-to-pooler có đảm bảo pooler-to-PostgreSQL được mã hóa không?

**Đáp án:** Không; từng network hop cần TLS policy riêng.

### Bài 22 — Replication

primary_conninfo có thể dùng passfile/sslrootcert không?

**Đáp án:** Có, theo libpq connection parameter support.

### Bài 23 — pg_stat_ssl

View này cho biết thông tin gì?

**Đáp án:** TLS state/protocol/cipher và client certificate metadata cho connections hiện tại.

### Bài 24 — HBA reload

Thay đổi HBA có ảnh hưởng connections đã mở không?

**Đáp án:** Không; nó áp dụng cho connection attempts mới.

### Bài 25 — Configuration drift

Vì sao phải kiểm tra pg_settings.source?

**Đáp án:** Để tìm setting bị override bởi role/database/session/auto.conf hoặc nguồn ngoài dự kiến.

### Bài 26 — Private key

Vì sao cần hạn chế file permissions?

**Đáp án:** Người đọc private key có thể giả mạo server/client identity.

### Bài 27 — Negative test

Nêu hai negative TLS tests.

**Gợi ý:** Sai hostname, CA không tin cậy, certificate hết hạn, plaintext connection bị reject.

### Bài 28 — DR

Vì sao DR cần secret/certificate readiness?

**Đáp án:** Sau failover, services cần kết nối và xác minh identities mà không phụ thuộc primary region.

### Bài 29 — Managed service

Vì sao không thể luôn sửa postgresql.conf trực tiếp trên managed PostgreSQL?

**Đáp án:** Provider có thể quản lý settings qua parameter groups/control plane và reconcile file state.

### Bài 30 — Audit

Nêu metadata cần lưu sau rotation mà không lưu secret value.

**Gợi ý:** Secret/cert version, owner, consumers, fingerprint/serial, timestamps, tests và revocation evidence.


## 53. Checklist cấu hình PostgreSQL theo môi trường

- [ ] Có shared configuration template và environment values riêng?
- [ ] postgresql.conf, auto.conf, include files và HBA/ident paths đã inventory?
- [ ] Effective settings/source/context/pending_restart đã capture?
- [ ] Duplicate/invalid settings và unexpected overrides đã xử lý?
- [ ] Reload/restart requirements được phân loại?
- [ ] Parameter values phù hợp capacity/workload từng environment?
- [ ] Config source of truth là repository/operator/parameter group rõ ràng?
- [ ] Staging parity và DR configuration đã rehearsal?
- [ ] Change diff/owner/approval/rollback được lưu?

## 54. Checklist secrets, authentication và TLS

- [ ] Mỗi service có role/credential riêng và least privilege?
- [ ] Secrets nằm trong approved manager, không trong Git/image/logs?
- [ ] Password encryption/authentication dùng SCRAM theo compatibility?
- [ ] pg_hba rule order/CIDR/method đã kiểm tra?
- [ ] Server certificate SAN/chain/expiry đúng?
- [ ] Private key owner/permissions an toàn?
- [ ] Clients dùng verify-full và CA bundle đúng?
- [ ] Client cert/mTLS mapping đã test nếu áp dụng?
- [ ] Pooler frontend/backend TLS được cấu hình riêng?
- [ ] Replication/FDW/backup/monitoring credentials được inventory?
- [ ] pg_stat_ssl và client-side verification evidence đạt?
- [ ] Negative tests cho wrong CA/hostname/password/plaintext đã chạy?

## 55. Checklist rotation và incident readiness

- [ ] Secret/certificate owners và consumers đã biết?
- [ ] Expiry/rotation alerts được cấu hình?
- [ ] Overlap/rollout order và rollback path rõ?
- [ ] Applications/poolers/jobs có thể reload/reconnect?
- [ ] Existing sessions/cached connections được tính tới?
- [ ] New credential/certificate đã được test trên mọi consumers?
- [ ] Old credential/certificate chỉ revoke sau khi consumers chuyển?
- [ ] Emergency revocation process đã rehearsal?
- [ ] DR có secret-manager/CA access?
- [ ] Audit record không chứa raw secret/private key?

## 56. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| postgresql.conf | Main server configuration |
| postgresql.auto.conf | Persistent overrides từ ALTER SYSTEM |
| pg_hba.conf | Connection admission/authentication rules |
| pg_ident.conf | Map external identity sang database role |
| include/include_dir | Tổ chức nhiều config files |
| pg_settings | Effective setting, source, context, pending_restart |
| pg_file_settings | Parsed configuration entries/errors |
| pg_hba_file_rules | Parsed HBA rules/errors |
| ALTER SYSTEM | Ghi persistent server setting |
| pg_reload_conf | Yêu cầu reload |
| password_encryption | Chọn password verifier format |
| SCRAM-SHA-256 | Password authentication method |
| hostssl | Match TCP connections có TLS |
| ssl | Bật server-side TLS |
| ssl_cert_file | Server certificate |
| ssl_key_file | Server private key |
| ssl_ca_file | CA trust cho client certificate verification |
| ssl_min_protocol_version | TLS protocol floor |
| sslmode=verify-full | Client verifies CA chain and hostname |
| sslrootcert | Client trusted CA bundle |
| sslcert/sslkey | Client certificate/private key |
| .pgpass / PGPASSFILE | libpq password file |
| pg_stat_ssl | TLS state cho active connections |
| pg_stat_activity | Active sessions/queries |
| Secret manager | Secure secret storage/distribution |
| PKI | Certificate issuance/trust/revocation |
| Rotation overlap | Giai đoạn consumers chuyển credentials/certificates |
| DR secret readiness | Khả năng xác thực sau failover |

## 57. Kết luận

**Quản lý cấu hình, secrets và TLS cần một nguồn cấu hình có kiểm soát cùng lifecycle riêng cho credentials và certificates ở từng environment.** postgresql.conf, postgresql.auto.conf, include files, role/database defaults và control plane có thể cùng ảnh hưởng effective settings. Dùng pg_settings, pg_file_settings và pg_hba_file_rules để xác định nguồn, lỗi và trạng thái restart; phân loại parameter context trước khi reload hoặc restart.

Secrets cần được tạo, lưu, phân phối, rotate và revoke theo service identity với least privilege. Dùng SCRAM-SHA-256 cho password authentication khi clients tương thích; không lưu plaintext passwords trong source, command line, image hoặc logs. TLS server certificate bảo vệ server identity, còn client verify-full xác minh CA chain và hostname. Client certificate/mTLS là một lớp identity bổ sung; role privileges và pg_hba vẫn kiểm soát quyền truy cập.

Rotation phải tính tới connection pools, existing sessions, cached FDW connections, replication, scheduled jobs và DR. Dùng trust/credential overlap khi phù hợp, test connections mới, recycle sessions và chỉ revoke credentials cũ sau khi consumers đã chuyển. Managed services/operators cần được cấu hình qua đúng control plane. Evidence gồm effective config, certificate fingerprints/serials, secret version, test results và revocation status; không lưu raw secret values.

Nguyên tắc triển khai: **giữ configuration có thể tái hiện, secrets ngoài source code, xác minh cả hai đầu TLS, cấp identity riêng cho từng service và diễn tập rotation/failover trước khi cần chúng trong production.**

