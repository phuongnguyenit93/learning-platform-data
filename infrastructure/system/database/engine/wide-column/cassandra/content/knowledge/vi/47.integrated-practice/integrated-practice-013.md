# Thực hành tổng hợp: Backup/restore Cassandra cùng quyền truy cập và TLS

## 1. Tình huống và mục tiêu

Một dịch vụ Java lưu nhật ký hoạt động trên **Apache Cassandra**, sử dụng bảng wide-column được thiết kế theo tenant và ngày. Đội vận hành cần sao lưu dữ liệu để khôi phục sau khi một cụm gặp sự cố, nhưng cụm đang bật **xác thực tài khoản CQL**, **phân quyền theo vai trò** và **TLS cho kết nối client**. Nếu chỉ giữ các file SSTable mà quên schema, quyền, chứng chỉ và cấu hình mạng, dữ liệu có thể còn nhưng ứng dụng vẫn không truy cập được, hoặc quá trình khôi phục có nguy cơ làm lộ dữ liệu.

Bài này đặt trọng tâm vào câu hỏi:

> Làm thế nào tạo, kiểm chứng và phục hồi bản sao lưu Cassandra khi phải bảo đảm cả **đúng dữ liệu**, **đúng quyền truy cập** và **kết nối TLS hợp lệ**?

Bài thực hành kết hợp các đặc tính nền tảng của Cassandra: replication trên nhiều node, dữ liệu chia theo partition key, CQL, consistency level, snapshot SSTable, compaction, repair, lỗi từng node và Java Driver.

**Đầu ra phải có:**

1. Một bảng nhật ký có dữ liệu mẫu trên cụm Cassandra dùng xác thực và TLS.
2. Một bộ backup có thể kiểm tra được: snapshot trên các node liên quan, schema, manifest và bản ghi cấu hình bảo mật **đã loại bí mật**.
3. Một cụm đích thử nghiệm được phục hồi từ backup qua công cụ phù hợp với phiên bản Cassandra.
4. Bằng chứng rằng tài khoản chỉ đọc **đọc được**, **không ghi được**, còn ứng dụng Java kết nối qua TLS và chỉ thấy dữ liệu được cấp quyền.
5. Báo cáo RPO/RTO, giới hạn của snapshot và các lỗi đã mô phỏng.

### Phạm vi, giả định và nguyên tắc an toàn

- Dùng **cụm lab độc lập**, ví dụ ba node trong DC `datacenter1` và `NetworkTopologyStrategy` với replication factor (RF) bằng 3. Tên DC phải được thay theo kết quả thực tế của `system.local`.
- Câu lệnh minh họa theo Cassandra **4.x với cú pháp công cụ phổ biến**. Trước khi chạy trên 4.0, 4.1, 5.x hoặc bản phân phối khác, kiểm tra `nodetool help`, `sstableloader --help` và định dạng SSTable tương thích.
- Đặt CQL native transport ở cổng 9042, TLS bắt buộc, xác thực `PasswordAuthenticator`, phân quyền `CassandraAuthorizer`. Nếu cấu hình khác, điều chỉnh phần vận hành tương ứng.
- Dùng dữ liệu giả không nhạy cảm. Không đưa mật khẩu, private key hay token thật vào repository, bản backup hoặc log.
- Thực hiện **restore lên cụm đích riêng và rỗng**. Không nạp snapshot trực tiếp vào cụm production đang phục vụ request.
- Bài không triển khai hệ thống backup tự động toàn diện hoặc bảo đảm point-in-time recovery (PITR). Snapshot chỉ là một phần của kế hoạch phục hồi.

## 2. Hiểu thành phần nào được sao lưu

Cassandra lưu dữ liệu ứng dụng theo partition key trên tập replica. Với bảng theo `((tenant_id, event_day), occurred_at, event_id)`, một snapshot của **một node** chỉ bao gồm SSTable đang có trên node đó; nó không mặc nhiên chứa toàn bộ partition trong cluster.

`nodetool snapshot` tạo snapshot trên **node được gọi**, chủ yếu bằng hard link tới các thành phần SSTable. Mặc định công cụ flush dữ liệu trước khi snapshot, trừ khi chỉ định bỏ flush. Snapshot là bản sao dữ liệu bền vững tại node, **không phải giao dịch nhất quán toàn cụm tại cùng một thời điểm**. Để có bản sao lưu bao phủ các token range và replica, cần tổ chức chụp trên các node theo kế hoạch và theo dõi trạng thái thành công của từng node. Trong lab, tạm dừng ghi ứng dụng trong khoảng chụp để có mốc dữ liệu rõ ràng.

| Thành phần | Có nằm trong snapshot của keyspace ứng dụng? | Cách bảo vệ/phục hồi |
| --- | --- | --- |
| SSTable của bảng dữ liệu | Có, trên từng node có bản sao dữ liệu | Snapshot từng node liên quan; sao chép ra lưu trữ ngoài node; kiểm tra checksum |
| Schema keyspace, table, indexes, UDT | Không nên dựa duy nhất vào snapshot để phục hồi schema | Xuất CQL DDL, lưu bản versioned có kiểm tra |
| Vai trò, thông tin xác thực, `GRANT` | Không nằm trong snapshot **keyspace ứng dụng** | Xuất danh sách role/grant đã kiểm duyệt; tạo lại qua quy trình bảo mật |
| Mật khẩu và private key | Không nên đi kèm bản backup dữ liệu | Lưu trong secret manager/PKI; cấp lại hoặc xoay vòng khi restore |
| `cassandra.yaml`, cấu hình TLS, topology | Không nằm trong snapshot bảng dữ liệu | Backup cấu hình đã che secrets; quản lý cấu hình bằng cơ chế riêng |
| Thay đổi sau mốc snapshot | Không được snapshot bảo đảm chứa | Incremental backups/commitlog archiving và quy trình PITR nếu có triển khai, kiểm thử |
| Dữ liệu đã hết TTL/tombstone | Phụ thuộc thời điểm ghi, TTL và trạng thái SSTable | Không giả định restore làm sống lại dữ liệu hết hạn |

**Phân biệt ba cơ chế:** snapshot giữ một tập SSTable ở một mốc; incremental backup của Cassandra lưu liên kết/bản sao SSTable mới tạo theo cơ chế cấu hình; commitlog archiving có thể cung cấp nguồn dữ liệu để xây dựng quy trình khôi phục tới mốc gần hơn. **Chỉ bật incremental backup hoặc chỉ lưu commitlog chưa tự động tạo ra PITR đúng**: cần manifest, thứ tự áp dụng, schema tương ứng, kiểm soát trùng lặp, kiểm thử replay và kế hoạch dọn retention.

### Mục tiêu phục hồi

- **RPO (Recovery Point Objective):** chênh lệch dữ liệu chấp nhận mất. Snapshot lúc 10:00 và sự cố lúc 10:20 có thể khiến những ghi sau snapshot không nằm trong backup, tức RPO quan sát có thể tới 20 phút nếu không có cơ chế bổ sung.
- **RTO (Recovery Time Objective):** thời gian từ khi xảy ra sự cố đến lúc dịch vụ hoạt động trở lại. RTO gồm dựng cụm, cấp chứng chỉ, khôi phục schema/role, truyền SSTable, kiểm chứng và chuyển lưu lượng.
- Với snapshot theo node, “10:00” chỉ là **mốc điều phối**, không phải bảo đảm tất cả node có snapshot logic giống hệt lúc 10:00. Cần ghi thời gian thực của từng node và tình trạng write quiescence.

## 3. Kiến trúc lab và đường đi an toàn

~~~mermaid
flowchart LR
    APP["Ứng dụng Java / cqlsh"] -->|"CQL qua TLS: 9042"| C["Cassandra: 3 node"]
    ADM["Operator qua kênh quản trị an toàn"] -->|"nodetool + JMX"| C
    C -->|"snapshot trên từng node"| S["SSTable snapshots"]
    S -->|"bản sao mã hóa + checksum"| B["Kho backup tách khỏi cụm"]
    B -->|"khôi phục vào staging"| L["sstableloader"]
    L -->|"stream qua mạng phù hợp cấu hình"| R["Cụm restore riêng"]
    R -->|"CQL qua TLS + RBAC"| T["Kiểm tra Java, quyền và dữ liệu"]
~~~

| Bề mặt | Cơ chế chính | Điều cần kiểm tra |
| --- | --- | --- |
| Java/cqlsh tới Cassandra | TLS + CQL authentication + authorization | Chứng chỉ hợp lệ, từ chối plaintext, đúng `GRANT` |
| Node tới node | Internode TLS nếu bật | Cấu hình `server_encryption_options` đồng bộ toàn cụm |
| Operator tới JMX/nodetool | JMX authentication/TLS hoặc chạy cục bộ trên node qua SSH kiểm soát | Quyền JMX khác với CQL roles |
| Node tới kho backup | ACL, mã hóa truyền tải và mã hóa lưu trữ | Backup không thể bị sửa/xóa bởi app role |
| Restore operator tới cụm đích | Quyền hệ điều hành, mạng streaming, tài khoản phục hồi | Chỉ vận hành trên cluster đích đã phê duyệt |

Một role được `GRANT SELECT` trong CQL **không** có quyền đọc file SSTable hoặc chạy `nodetool snapshot` chỉ vì CQL cho phép SELECT. Ngược lại, người có quyền truy cập trực tiếp vào file dữ liệu có thể vượt qua kiểm soát CQL. Vì vậy snapshot phải được bảo vệ ở mức lưu trữ và vận hành, kể cả khi ứng dụng có RBAC tốt.

## 4. Chuẩn bị cụm, TLS và xác thực

### 4.1. Điều kiện trước khi bật bảo mật

Cần có chứng chỉ máy chủ do CA mà client tin tưởng ký, với SAN khớp hostname dùng kết nối (`cassandra-1.lab`, `cassandra-2.lab`, ...). Không dùng một certificate không kiểm tra danh tính cho mọi node. Trong lab, quản trị viên chuẩn bị truststore và keystore; trên production nên dùng PKI/quản lý bí mật có xoay vòng định kỳ.

Ví dụ *cấu trúc* cấu hình trong `cassandra.yaml` của từng node:

~~~yaml
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager

client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/tls/node-keystore.jks
  keystore_password: "<cấp từ cơ chế quản lý bí mật>"
  require_client_auth: false
~~~

- `enabled: true` bật TLS cho native CQL; `optional: false` yêu cầu client sử dụng TLS. Không để plaintext hoạt động trong bài thực hành.
- `keystore` chứa khóa/chứng chỉ của node; client cần CA/truststore tương ứng. Nếu bật **mutual TLS**, cấu hình `require_client_auth: true` và truststore phía server, đồng thời client trình chứng chỉ phù hợp.
- Nếu yêu cầu mã hóa lưu lượng **giữa các node**, cấu hình thêm `server_encryption_options`, ví dụ `internode_encryption: all` cùng keystore/truststore thích hợp. Đây là đường mạng khác với client TLS; thay đổi phải có kế hoạch tương thích/rolling deployment và kiểm thử riêng.
- File cấu hình có thông tin bí mật phải giới hạn quyền file hoặc nhận secret qua cơ chế triển khai an toàn. Các giá trị trong dấu góc là placeholder, **không** phải mật khẩu hợp lệ để giữ nguyên.
- Bật authentication/authorization trên cụm đã vận hành cần kế hoạch bootstrap admin và bảo đảm keyspace `system_auth` có replication phù hợp; không đổi đột ngột trên production. Bài này giả định cụm lab đã được cấu hình và khởi động lại đúng quy trình.

**Lưu ý về các lớp TLS:** TLS client không tự động mã hóa inter-node, JMX hay backup lưu trên đĩa. Kiểm tra từng đường truyền độc lập.

### 4.2. Kiểm tra data center, topology và TLS

Đăng nhập bằng role quản trị của lab (không đưa mật khẩu vào shell history) rồi chạy:

~~~sql
SELECT cluster_name, data_center, release_version FROM system.local;
~~~

Trên máy có CA public của lab, kiểm tra bắt tay TLS và chuỗi chứng chỉ:

~~~bash
openssl s_client \
  -connect cassandra-1.lab:9042 \
  -servername cassandra-1.lab \
  -CAfile /secure/lab-ca.pem \
  -verify_return_error
~~~

Kiểm tra chain và SAN của chứng chỉ, đồng thời bật **hostname verification** trong client. Một kết nối TLS thành công chỉ chứng minh đường mã hóa đang hoạt động; nếu client bỏ xác minh hostname thì chưa đủ chống giả mạo endpoint.

Ví dụ file `~/.cassandra/cqlshrc` của máy thực hành:

~~~ini
[ssl]
certfile = /secure/lab-ca.pem
validate = true
~~~

Kết nối bằng client TLS:

~~~bash
cqlsh cassandra-1.lab 9042 --ssl -u lab_admin
~~~

Nhập password qua prompt/cơ chế bí mật phù hợp; tránh `-p actual-password` trong lịch sử shell và tham số tiến trình. Thử kết nối không có `--ssl` (trong lab) và xác nhận server từ chối handshake. Nếu dùng mTLS, cấu hình thêm client key/certificate của `cqlsh` và kiểm tra hành vi khi thiếu chứng chỉ.

### 4.3. Phân quyền tối thiểu cho ứng dụng

Dưới role admin, tạo hai role ứng dụng và chỉ cấp quyền cần thiết. Ví dụ sau dùng placeholder; **thay bằng bí mật riêng được cấp từ vault, không commit script có mật khẩu thật**.

~~~sql
CREATE ROLE IF NOT EXISTS lab_reader
WITH LOGIN = true
AND SUPERUSER = false
AND PASSWORD = '<READER_SECRET>';

CREATE ROLE IF NOT EXISTS lab_writer
WITH LOGIN = true
AND SUPERUSER = false
AND PASSWORD = '<WRITER_SECRET>';
~~~

Sau khi tạo bảng ở phần kế tiếp, cấp quyền:

~~~sql
GRANT SELECT ON TABLE lab_audit.activity_by_tenant_day TO lab_reader;
GRANT MODIFY ON TABLE lab_audit.activity_by_tenant_day TO lab_writer;

LIST ALL PERMISSIONS OF lab_reader;
LIST ALL PERMISSIONS OF lab_writer;
~~~

Kỳ vọng: `lab_reader` chỉ SELECT trên bảng; `lab_writer` có MODIFY (INSERT/UPDATE/DELETE) nhưng không được tự động cấp SELECT. Quyền thực tế có thể gồm quyền kế thừa từ role khác; phải kiểm tra cả cây role nếu lab có cấp quyền bổ sung.

**Chú ý:** quyền CQL không thay thế quyền JMX, quyền tài khoản hệ điều hành và quyền đọc kho backup. Không cấp SUPERUSER cho tài khoản ứng dụng.

## 5. Tạo dữ liệu có thể kiểm chứng trước và sau snapshot

### 5.1. Tạo keyspace và bảng

Trong lab với DC `datacenter1` có đủ ba node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_audit
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_audit.activity_by_tenant_day (
    tenant_id   text,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    actor_id    text,
    action      text,
    resource_id text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
)
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Bảng này minh họa nguyên tắc **thiết kế theo truy vấn**. Partition key `(tenant_id, event_day)` giữ hoạt động của một tenant trong một ngày UTC; clustering columns sắp xếp theo thời gian giảm dần. Snapshot phải bảo toàn dữ liệu các partition theo phân phối thực trên cụm. Không dùng `ALLOW FILTERING` để kiểm đếm dữ liệu trên toàn hệ thống.

Trong `cqlsh` trên cụm ba replica, đặt consistency cho lab:

~~~sql
CONSISTENCY LOCAL_QUORUM;
~~~

Với RF=3 trong một DC, `LOCAL_QUORUM` cần phản hồi từ ít nhất hai replica local cho mỗi đọc/ghi. Lab một node phải đổi RF/consistency tương ứng, nhưng khi đó không kiểm thử được lỗi replica với quorum.

### 5.2. Ghi dữ liệu gốc

~~~sql
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T08:00:00Z',
 11111111-1111-4111-8111-111111111111,
 'user-1', 'LOGIN', 'session-1');

INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T09:00:00Z',
 22222222-2222-4222-8222-222222222222,
 'user-1', 'CREATE', 'order-1');

INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-b', '2026-11-20', '2026-11-20T07:30:00Z',
 33333333-3333-4333-8333-333333333333,
 'user-2', 'LOGIN', 'session-2');
~~~

Trước khi backup, kiểm tra riêng từng partition:

~~~sql
SELECT occurred_at, event_id, actor_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

SELECT occurred_at, event_id, actor_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-b' AND event_day = '2026-11-20';
~~~

Kết quả mong đợi: tenant A có **hai hàng**, tenant B có **một hàng**; trong tenant A, `09:00 CREATE` đứng trước `08:00 LOGIN`. Lưu bộ khóa `(tenant_id, event_day, occurred_at, event_id)` và checksum nội dung của dữ liệu test làm mốc kiểm chứng. Không kiểm tra bằng cách quét toàn bộ keyspace production.

## 6. Tạo và kiểm chứng bộ backup

### 6.1. Chốt mốc dữ liệu và lưu metadata

Dừng hoặc làm yên luồng ghi của **ứng dụng lab** trong lúc chụp. Đảm bảo cả ba ghi ở bước 5 đã được xác nhận trước đó. Ghi manifest phục hồi tối thiểu:

| Trường manifest | Ví dụ | Mục đích |
| --- | --- | --- |
| `backup_id` | `audit-drill-20261121-a` | Theo dõi duy nhất một bộ backup |
| `source_cluster` / `source_dc` | `lab-source` / `datacenter1` | Xác định cụm và topology |
| `cassandra_version` / `partitioner` | Bản thật lấy từ cụm | Kiểm tra khả năng đọc/stream SSTable |
| `schema_revision` | Hash/file DDL | Phục hồi cấu trúc đúng |
| `snapshot_tag` | `audit-drill-20261121` | Nhận diện snapshot trên từng node |
| `nodes_completed` | Danh sách node, thời gian, tình trạng | Xác nhận bao phủ các node cần thiết |
| `archive_checksums` | SHA-256 của file backup | Phát hiện hỏng/sửa archive |
| `security_profile` | `PasswordAuthenticator`, `CassandraAuthorizer`, client TLS required | Khôi phục chính sách truy cập |
| `roles_and_grants_redacted` | Tên role, quyền; không có password/hash | Tái lập ACL |
| `rpo_reference_time` | Mốc dữ liệu đã ngừng ghi | So sánh sau restore |

Lưu schema CQL theo cách được phiên bản `cqlsh` hỗ trợ:

~~~sql
DESCRIBE KEYSPACE lab_audit;

LIST ROLES;
LIST ALL PERMISSIONS OF lab_reader;
LIST ALL PERMISSIONS OF lab_writer;
~~~

Kết quả `DESCRIBE KEYSPACE` cần được xuất vào kho backup metadata. `LIST ROLES` và danh sách grant dùng để đối chiếu, **không** lưu mật khẩu, credential hash, khóa riêng, token hoặc nội dung nhạy cảm. Nếu có nhiều role hoặc quyền kế thừa, cần ghi đầy đủ những phần liên quan tới dịch vụ, không chỉ hai role trong ví dụ.

### 6.2. Snapshot trên từng node

Trên **mỗi node Cassandra thuộc cụm nguồn**, qua SSH và quyền operator phù hợp, thực hiện:

~~~bash
nodetool snapshot -t audit-drill-20261121 lab_audit
nodetool listsnapshots
~~~

Ghi kết quả riêng cho `node-1`, `node-2` và `node-3`. Không được xem việc lệnh chạy thành công trên một node là backup toàn cụm hoàn thành.

Thư mục snapshot điển hình:

~~~text
/var/lib/cassandra/data/
  lab_audit/
    activity_by_tenant_day-<table-id>/
      snapshots/
        audit-drill-20261121/
          <SSTable-components>
          <manifest/metadata tùy phiên bản>
~~~

Trên từng node, xác định thư mục cần lưu:

~~~bash
find /var/lib/cassandra/data/lab_audit \
  -type d -path '*/snapshots/audit-drill-20261121' -print
~~~

Đường dẫn thực tế phụ thuộc cấu hình `data_file_directories`, container hoặc hệ điều hành. SSTable thường gồm nhiều file thành phần (Data, Index, Statistics, CompressionInfo, v.v.). **Không chỉ sao chép một file `Data.db` rồi cho là backup hoàn chỉnh.**

Snapshot dùng hard link nên bản trên cùng ổ đĩa không chống được lỗi mất node/ổ đĩa. Sao chép **đủ các thành phần** sang kho backup độc lập, giữ quan hệ `node/keyspace/table/snapshot_tag` và metadata; dùng mã hóa khi truyền và lưu, quyền truy cập tối thiểu, retention và chống sửa/xóa ngoài ý muốn. Kiểm tra checksum **sau** khi bản sao đã tới kho lưu trữ. Phần mềm backup có thể nén/mã hóa archive, nhưng cần xác minh khả năng giải nén và checksum ở môi trường restore.

**Chỉ sau khi bản sao ngoài node đã được kiểm tra thành công** mới cân nhắc giải phóng snapshot local theo chính sách, ví dụ:

~~~bash
# Chạy trên node tương ứng, chỉ khi archive đã được xác minh.
nodetool clearsnapshot -t audit-drill-20261121 lab_audit
~~~

Bài lab có thể giữ snapshot local đến cuối buổi thực hành để thuận tiện so sánh. Cần đảm bảo có đủ dung lượng vì hard link giữ SSTable cũ không bị xóa khi compaction tạo file mới.

### 6.3. Tạo thay đổi sau backup để kiểm tra RPO

Sau khi **tất cả node đã hoàn thành snapshot** và đã ghi nhận mốc, cho phép ghi trở lại rồi thêm một sự kiện:

~~~sql
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T10:00:00Z',
 44444444-4444-4444-8444-444444444444,
 'user-1', 'UPDATE', 'order-1');
~~~

Lúc này cụm nguồn có **ba hàng** của tenant A, trong khi bộ snapshot được chụp trong khoảng tạm dừng ghi chỉ có **hai hàng** của tenant A. Không đưa sự kiện `10:00` vào archive. Sự khác biệt dự kiến này giúp đo ranh giới RPO. Trong workload không dừng ghi, không thể tự suy ra một bộ snapshot nhiều node có ranh giới dữ liệu chính xác tương tự.

## 7. Phục hồi vào cụm đích độc lập

### 7.1. Quyết định cách restore

Có hai nhóm kỹ thuật, không nên dùng lẫn mà thiếu kế hoạch:

| Cách | Dùng khi nào | Điều kiện chính |
| --- | --- | --- |
| **Bulk load/stream bằng `sstableloader`** | Khôi phục dữ liệu SSTable vào cụm đích đang chạy | Cụm đích đã có schema tương thích; tool/SSTable tương thích; mạng streaming, auth và TLS được cấu hình |
| Đặt/import SSTable bằng thao tác node-local có kiểm soát | Quy trình disaster recovery đặc thù, có runbook theo phiên bản | Phải tuân thủ quy định về table ID, token ownership, trạng thái node, import/refresh và version; dễ sai nếu copy thẳng vào data directory đang chạy |

**Trong bài này dùng `sstableloader`** để tránh tự thao tác file trong data directory sống. Không copy ngẫu nhiên SSTable từ node nguồn sang node đích rồi khởi động ứng dụng như thể dữ liệu đã được nạp; token ranges, schema/table ID và dữ liệu ở các replica có thể khác.

### 7.2. Dựng cụm đích với chính sách bảo mật

Dựng cụm `lab-restore` độc lập, cấu hình topology, phân quyền, certificates/truststores và TLS đúng yêu cầu đã ghi trong manifest. Nên giữ cùng hoặc phiên bản Cassandra có đường nâng cấp SSTable/loader **được hỗ trợ**, cùng partitioner và schema logic tương thích.

Thứ tự phụ thuộc thực tế, nhưng tối thiểu phải đạt:

1. Các node hoạt động ổn định; `nodetool status` xác nhận trạng thái dự kiến và replication.
2. CQL native TLS hoạt động; client xác minh CA và hostname, plaintext bị từ chối.
3. Role quản trị có thể truy cập bằng cách an toàn; role ứng dụng được tạo lại từ hệ thống quản lý định danh/bí mật.
4. Keyspace và table được tái tạo từ **DDL đã xuất**, với replication thích hợp topology đích. Trong bài lab, có thể chạy lại khối DDL ở phần 5 nếu DDL xuất ra giống hệt.
5. Bảng đích **ban đầu rỗng**, để kết quả kiểm thử có thể dự đoán. Không khôi phục chồng lên dữ liệu ứng dụng đang hoạt động.

**Không tự động khôi phục keyspace `system_auth` từ cụm khác** như cách chuyển role/grant. Metadata xác thực, quyền và cache phụ thuộc cụm/phiên bản và chính sách bảo mật. Với bài lab, tạo role mới bằng mật khẩu mới từ vault, sau đó chạy lại `GRANT` đã được kiểm duyệt.

### 7.3. Chuẩn bị SSTable staging

Giải mã/giải nén backup vào thư mục staging **ngoài data directory của Cassandra đang chạy**. Xác minh checksum từng archive trước khi dùng. Duy trì metadata nguồn cho từng node; khôi phục các snapshot đủ bao phủ dữ liệu, tránh bỏ qua node chứa token range mà node khác không có.

Với `sstableloader`, chuẩn bị đường dẫn theo cấu trúc **keyspace/table** mà phiên bản loader yêu cầu, sao cho các thành phần SSTable nằm ngay trong thư mục bảng staging:

~~~text
/restore/staging/
  lab_audit/
    activity_by_tenant_day-<source-table-id>/
      <SSTable-components-copied-from-snapshot>
~~~

Dấu `<source-table-id>` là placeholder. Nếu phải nạp dữ liệu từ nhiều node, chạy tuần tự cho từng bộ SSTable đã được phục hồi vào staging và theo dõi những bộ đã xử lý. Trùng cùng primary key có thể được Cassandra reconcile khi stream, nhưng stream trùng tăng tải và không thay thế việc hiểu timestamp/tombstone. Không ghi chồng các file SSTable khác nhau khi tên file trùng; phân staging theo nguồn hoặc đổi quy trình import một cách có kiểm soát.

### 7.4. Nạp dữ liệu qua loader

Ví dụ lệnh minh họa cho **máy restore đã được phép kết nối**:

~~~bash
# Placeholder mật khẩu chỉ dùng trong lab, không dùng trực tiếp trong production.
# Kiểm tra lại tên flag bằng: sstableloader --help
sstableloader \
  -d cassandra-restore-1.lab,cassandra-restore-2.lab \
  -u restore_admin \
  -pw '<RESTORE_ADMIN_SECRET>' \
  -ssl \
  -ts /secure/restore-truststore.jks \
  -tspw '<TRUSTSTORE_SECRET>' \
  /restore/staging/lab_audit/activity_by_tenant_day-<source-table-id>/
~~~

- `-d` chỉ các contact point của **cụm đích**; xác minh DNS, IP và hostname trước khi chạy. Không trỏ nhầm vào nguồn.
- `-ssl` và tham số truststore phục vụ kết nối TLS của loader. Nếu server yêu cầu mutual TLS, bổ sung client keystore theo phiên bản công cụ.
- Cần cho phép những kết nối streaming mà loader yêu cầu và bảo đảm tương thích với chính sách inter-node TLS. Quyền CQL đủ để truy vấn **không mặc nhiên** là quyền chạy bulk loader; runbook hạ tầng phải cấp quyền vận hành phù hợp.
- **Mật khẩu trên command line có thể lộ qua process list/log.** Lệnh này dùng placeholder để học cú pháp. Trong môi trường thật, dùng phương án quản lý secret được hỗ trợ và kiểm tra cách tool xử lý credential; không paste mật khẩu production lên terminal.
- Theo dõi output, số SSTable/bytes đã stream và lỗi từng bộ. Nếu công cụ từ chối định dạng SSTable/schema hoặc TLS, dừng và sửa nguyên nhân; không tắt TLS để “cho chạy xong”.

Loader stream các mutation/SSTable hợp lệ qua cụm; dữ liệu nhận được vẫn tuân theo ngữ nghĩa timestamp, tombstone, consistency và repair của Cassandra. Việc nạp đủ bytes không đồng nghĩa khôi phục thành công về mặt nghiệp vụ: còn phải đối chiếu nội dung và quyền ở phần sau.

## 8. Kiểm chứng dữ liệu, quyền và TLS sau restore

### 8.1. Kiểm chứng dữ liệu bằng primary key

Trên cụm **đích**, đăng nhập qua TLS bằng tài khoản có SELECT phù hợp và truy vấn:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT occurred_at, event_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

SELECT occurred_at, event_id, action, resource_id
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-b' AND event_day = '2026-11-20';
~~~

Nếu backup lấy hoàn chỉnh sau ba INSERT gốc và trước INSERT mới, mong đợi:

| Partition | Cụm nguồn sau thay đổi | Cụm restore từ snapshot |
| --- | --- | --- |
| `(tenant-a, 2026-11-20)` | 3 hàng: 08:00, 09:00, **10:00** | **2 hàng: 08:00, 09:00** |
| `(tenant-b, 2026-11-20)` | 1 hàng: 07:30 | **1 hàng: 07:30** |

Khớp bản ghi bằng **full primary key** và nội dung, không chỉ tổng số hàng. Với dữ liệu thật, so checksum/manifest theo partition hoặc theo tập khóa có kiểm soát; tránh `SELECT COUNT(*)`/scan toàn cluster production chỉ để kiểm chứng. Nếu bất ngờ có sự kiện `10:00`, kiểm tra có nạp nhầm SSTable tạo sau snapshot, dùng sai source archive hoặc chạy thêm incremental/replay.

### 8.2. Kiểm chứng role và `GRANT`

Trên cụm đích, tạo lại `lab_reader`, `lab_writer`, áp dụng lại hai `GRANT` ở phần 4, dùng mật khẩu **mới** được cấp an toàn. Sau đó mở **phiên cqlsh mới** bằng role reader:

~~~bash
cqlsh cassandra-restore-1.lab 9042 --ssl -u lab_reader
~~~

Trong phiên đó:

~~~sql
-- Phải thành công:
SELECT occurred_at, action
FROM lab_audit.activity_by_tenant_day
WHERE tenant_id = 'tenant-a' AND event_day = '2026-11-20';

-- Phải bị từ chối do không có MODIFY:
INSERT INTO lab_audit.activity_by_tenant_day
(tenant_id, event_day, occurred_at, event_id, actor_id, action, resource_id)
VALUES ('tenant-a', '2026-11-20', '2026-11-20T12:00:00Z',
 55555555-5555-4555-8555-555555555555,
 'forbidden-user', 'DELETE', 'resource-x');
~~~

Lệnh INSERT thứ hai được dùng làm **negative test** và phải lỗi authorization; nếu thành công, kiểm tra quyền kế thừa, SUPERUSER hoặc việc phiên thực tế đang dùng nhầm credential admin. Xóa test record nếu chính sách lab cần dọn dữ liệu sau khi sửa quyền.

Lặp lại với `lab_writer`: thao tác ghi được phép trên bảng được chỉ định, còn truy vấn SELECT không được cấp phải lỗi. Không thử ghi lên dữ liệu thật của người khác. Quyền từ chối là một **kết quả thành công của bài kiểm thử bảo mật**.

### 8.3. Ma trận kiểm thử TLS và khôi phục

| Thử nghiệm | Kỳ vọng |
| --- | --- |
| Client dùng TLS + CA hợp lệ + đúng hostname + role đúng | Kết nối và truy vấn theo quyền |
| Client plaintext tới cổng CQL yêu cầu TLS | Kết nối bị từ chối |
| CA không tin cậy hoặc SAN không khớp hostname | Client có xác minh chứng chỉ từ chối |
| Mật khẩu role sai | Authentication thất bại |
| Role reader thực hiện INSERT | Authorization thất bại |
| Client không có certificate khi `require_client_auth: true` | TLS/mTLS handshake thất bại |
| Backup archive bị thay đổi một byte | Checksum/signature verification thất bại trước restore |
| Thiếu một số node/SSTable trong bộ backup | Restore không đạt đối chiếu dữ liệu hoặc báo incomplete coverage; không công bố thành công |

Trong thực hành, không cần cố làm hỏng cluster để chứng minh mọi dòng. Một số bài kiểm thử có thể chạy trên client riêng hoặc một bản copy archive đã cố ý thay đổi; giữ nguyên backup gốc.

## 9. Kết nối từ ứng dụng Java sau phục hồi

Ví dụ với **Apache/DataStax Cassandra Java Driver 4.x**: đăng nhập bằng role `lab_reader` và dùng TLS với truststore PKCS#12 chứa CA của cluster restore. Mật khẩu nhận từ biến môi trường do môi trường chạy cấp, không hardcode.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.LocalDate;

public class VerifyRestoredActivities {
    static SSLContext sslContextFromTruststore() throws Exception {
        char[] secret = System.getenv("CASSANDRA_TRUSTSTORE_PASSWORD")
                              .toCharArray();
        KeyStore truststore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(
                Path.of(System.getenv("CASSANDRA_TRUSTSTORE_PATH")))) {
            truststore.load(input, secret);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "cassandra-restore-1.lab", 9042))
                .withLocalDatacenter("datacenter1")
                .withAuthCredentials(
                    "lab_reader",
                    System.getenv("CASSANDRA_READER_PASSWORD"))
                .withSslContext(sslContextFromTruststore())
                .build()) {

            PreparedStatement stmt = session.prepare(
                "SELECT occurred_at, event_id, action " +
                "FROM lab_audit.activity_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ?");

            var bound = stmt.bind("tenant-a", LocalDate.parse("2026-11-20"))
                            .setConsistencyLevel(
                                DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(bound)) {
                System.out.println(row.getInstant("occurred_at")
                    + " | " + row.getUuid("event_id")
                    + " | " + row.getString("action"));
            }
        }
    }
}
~~~

**Cấu hình cần xác minh thêm trong deployment:** driver phải bật xác minh hostname theo SAN của server certificate (ví dụ tùy chọn `advanced.ssl-engine-factory.hostname-validation` nếu factory/phiên bản hỗ trợ). Việc nạp một truststore vào `SSLContext` **không nên được coi là bằng chứng tự động rằng hostname đã được kiểm tra**. Nếu bật mTLS, tạo `SSLContext` với **KeyManager** chứa client certificate/key ngoài TrustManager. Luôn kiểm thử một hostname sai SAN phải bị từ chối.

Với ứng dụng Java chạy liên tục, dùng lại `CqlSession` theo vòng đời ứng dụng, không mở session mới cho mỗi request. Cấp privilege tối thiểu cho service account. Khi chuyển sang cụm restore, cập nhật contact points/DNS, truststore và thông tin role theo quy trình triển khai; không nới ACL hay tắt TLS để khắc phục kết nối lỗi.

## 10. Những điểm dễ sai trong backup/restore Cassandra

### 10.1. Snapshot không phải ảnh nhất quán toàn cluster

Khi ghi vẫn chạy, snapshot trên node A có thể trước một mutation, còn node B chụp sau mutation. Replication và `LOCAL_QUORUM` giúp chịu lỗi khi đủ replica phản hồi nhưng không khiến ba node chụp cùng một snapshot giao dịch. Đối với nghiệp vụ yêu cầu điểm khôi phục chính xác, cần điều phối write quiescence hoặc kiến trúc backup/PITR chuyên biệt, kết hợp khả năng kiểm toán mutation theo thời gian.

### 10.2. Dữ liệu hết TTL, tombstone và compaction

SSTable có thể chứa TTL/tombstone. Restore giữ ngữ nghĩa timestamp/TTL đã ghi; nó **không** tự reset thời hạn sống của hàng. Bản ghi đã hết TTL vào ngày phục hồi có thể không xuất hiện trong kết quả SELECT dù SSTable vẫn chiếm dung lượng. Sau restore, kiểm tra tốc độ tombstone scan, compaction, dung lượng, chính sách `gc_grace_seconds` và repair. Không hạ `gc_grace_seconds` để “dọn nhanh” nếu replica có thể đã bỏ lỡ tombstone, vì có nguy cơ dữ liệu bị xóa tái xuất hiện.

SSTable được chụp trước/giữa các lần compaction không có nghĩa mọi file là độc lập về nội dung logic. Vì thế không suy luận số hàng chỉ từ số file; phải truy vấn/đối chiếu theo key.

### 10.3. Repair, replication và cấp quyền

Sau khi restore, replica có thể cần được đồng bộ tùy cách nạp dữ liệu và phiên bản Cassandra. Lập lịch/kiểm tra repair theo runbook, quan sát các node nhận đủ dữ liệu. Với cluster RF=3 trong một DC, một replica bị hỏng không nhất thiết làm thất bại `LOCAL_QUORUM`; **hai replica không khả dụng** có thể khiến read/write LOCAL_QUORUM trả `Unavailable` hoặc timeout. Không giảm consistency chỉ để cho màn kiểm chứng “xanh”.

Nếu khôi phục dữ liệu mà chưa khôi phục role/grant, tài khoản ứng dụng có thể lỗi `Unauthorized`. Nếu khôi phục ACL nhưng quên CA/truststore hoặc SAN, client sẽ lỗi TLS trước cả xác thực. Cần phân loại lỗi theo lớp thay vì xử lý mọi lỗi bằng retry.

### 10.4. Checklist xử lý sự cố

| Dấu hiệu | Nghi vấn chính | Hành động |
| --- | --- | --- |
| `NoHostAvailable` / TLS handshake error | Hostname, CA, cổng, TLS mode, cert hết hạn | Kiểm tra certificate chain, SAN, contact points, mạng |
| `AuthenticationException` | Sai mật khẩu, role không LOGIN, auth config | Kiểm tra vault, role tồn tại, cụm đích và auth provider |
| `UnauthorizedException` | Thiếu `GRANT` hoặc role khác | Kiểm tra quyền thực và quyền kế thừa trên table |
| `UnavailableException` / read timeout | Replica local không đạt CL, node chưa sẵn sàng | Kiểm tra `nodetool status`, RF, DC, repair, logs |
| Loader từ chối SSTable | Phiên bản SSTable, partitioner/schema không khớp | Dừng, đối chiếu manifest và compatibility matrix |
| Restore thiếu rows | Thiếu snapshot của node, mất SSTable, TTL, stream lỗi | Kiểm tra coverage, checksum, TTL, mốc snapshot và log |
| Disk tăng dù dữ liệu hết TTL | Tombstone/SSTable đợi compaction hoặc backup hard links | Quan sát compaction, snapshot còn giữ và repair |

**Không xử lý lỗi bằng cách** chép file trực tiếp vào data directory đang chạy, dùng `ALLOW FILTERING` để “tìm dữ liệu đã mất”, tắt auth/TLS, hoặc mở quyền SUPERUSER cho mọi tài khoản.

## 11. Bài tập tự triển khai và tiêu chí đánh giá

### Bài A — Chứng minh backup có thể giải mã và khôi phục

Lập manifest có ít nhất các trường ở phần 6, tải archive từ kho backup sang máy restore, kiểm tra checksum, rồi nạp bảng bằng `sstableloader`. Ghi lại số file/SSTable, dung lượng và số hàng kiểm chứng theo partition. Nêu rõ bước nào chứng minh **đọc được file**, bước nào chứng minh **nạp được dữ liệu**, và bước nào chứng minh **ứng dụng dùng được**.

### Bài B — Kiểm tra quyền sau restore

Dùng `lab_reader` và `lab_writer` kiểm thử ma trận SELECT/INSERT. Bổ sung một role `audit_admin` có quyền quản lý cấu trúc hoặc truy cập theo nhu cầu lab; so sánh quyền CQL này với quyền operator cần để chạy `nodetool snapshot`. Giải thích vì sao role read-only không được quyền tải archive SSTable về máy cá nhân.

### Bài C — Chứng chỉ hết hạn hoặc CA thay đổi

Trên môi trường cô lập, thay CA tin cậy của client bằng một CA sai và xác nhận kết nối bị từ chối. Khôi phục đúng truststore và kết nối lại. Đề xuất cách giám sát certificate expiry và cách chuyển CA có giai đoạn tin cậy chồng lấn, tránh làm gián đoạn toàn bộ client.

### Bài D — RPO khác nhau

Làm hai lượt restore: lần 1 chỉ snapshot, lần 2 giả định có chiến lược incremental + commitlog archive được triển khai và kiểm thử. So sánh khả năng khôi phục event `10:00`; giải thích vì sao incremental SSTable alone chưa bảo đảm lấy được mọi ghi mới còn nằm trong memtable/chưa tạo SSTable mới.

### Bài E — Lỗi một replica

Trong cụm lab RF=3, CL=LOCAL_QUORUM, ngắt một node để quan sát truy vấn kiểm chứng. Giải thích vì sao vẫn có thể thành công với hai replica còn lại, và vì sao ngắt hai node có thể thất bại. Ghi chú repair/backup thay vì suy ra các bản sao tự đồng bộ hoàn toàn sau khi node trở lại.

### Tự kiểm tra trước khi nghiệm thu

- [ ] Manifest định danh đúng cluster, DC, phiên bản, schema, tag và danh sách snapshot đủ node.
- [ ] Bản backup đã được sao chép ra ngoài cụm, mã hóa và kiểm checksum sau sao chép; bí mật không nằm trong archive/manifest.
- [ ] DDL, role và quyền đã được lưu/tạo lại qua quy trình tách biệt với SSTable.
- [ ] Restore thực hiện trên cụm độc lập, schema tương thích, có log quá trình stream và bằng chứng kiểm tra dữ liệu.
- [ ] Sau restore, tenant A có hai event cũ và không có event `10:00` trong kịch bản snapshot-only; tenant B có một event.
- [ ] `lab_reader` SELECT được nhưng không INSERT được; `lab_writer` chỉ có những quyền đã cấp.
- [ ] TLS được xác minh bằng CA và hostname; plaintext/bad certificate bị từ chối.
- [ ] Java Driver dùng TLS, credential từ secret manager và role tối thiểu; kiểm tra kết nối sau chuyển cụm.
- [ ] Có báo cáo RPO/RTO, trạng thái replica, compaction/repair và các giới hạn về TTL, tombstone, snapshot.

## 12. Mẫu biên bản kết quả phục hồi

Dùng mẫu sau để trình bày kết quả đã đo thật, không điền “PASS” khi chưa thực thi:

| Hạng mục | Bằng chứng cần ghi | Kết quả |
| --- | --- | --- |
| Backup coverage | Số node hoàn thành; snapshot tag; thời gian chụp | `PASS/FAIL + chi tiết` |
| Bảo vệ archive | Checksum, mã hóa, ACL, vị trí lưu ngoài cluster | `PASS/FAIL + chi tiết` |
| Restore | Phiên bản loader, số SSTable/bytes nạp, lỗi | `PASS/FAIL + chi tiết` |
| Đối chiếu dữ liệu | Khóa và action của 3 event trước snapshot; thiếu event 10:00 | `PASS/FAIL + chi tiết` |
| RBAC | SELECT của reader và INSERT bị từ chối | `PASS/FAIL + chi tiết` |
| TLS | Xác minh CA/SAN; thử plaintext/CA sai | `PASS/FAIL + chi tiết` |
| Ứng dụng Java | Kết nối, read qua prepared statement, CL, log không chứa secret | `PASS/FAIL + chi tiết` |
| RPO/RTO thực đo | Thời điểm mốc backup/sự cố, phục hồi hoàn tất | `RPO/RTO + giới hạn` |

Khi hoàn thành, người học cần giải thích được rằng **phục hồi Cassandra có ba phần gắn chặt nhau**: dữ liệu SSTable được sao lưu đúng phạm vi phân tán; schema, replication và consistency được tái dựng chính xác; cùng quyền truy cập và TLS được kiểm chứng độc lập từ client đến cụm khôi phục. Một bản backup chỉ có giá trị vận hành khi **restore drill đã chứng minh dữ liệu đọc được với đúng mức bảo mật**.
