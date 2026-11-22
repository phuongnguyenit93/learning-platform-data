# Phân quyền công cụ, ghi nhật ký thao tác và xác minh sau thực hiện

## 1. Vì sao thao tác vận hành Cassandra cần cả quyền, bằng chứng và hậu kiểm?

Một cụm **Apache Cassandra** có thể phục vụ hàng triệu phép đọc/ghi nhờ partition key, token ring, replication và consistency level. Nhưng chính tính phân tán đó khiến một thao tác quản trị thiếu kiểm soát có thể ảnh hưởng nhiều node, nhiều datacenter và cả khả năng khôi phục dữ liệu.

Hãy xét một tình huống: người vận hành thấy ổ đĩa của N2 gần đầy sau khi thêm node N4, bèn chạy `nodetool cleanup` trên N2. Lệnh trả về exit code 0, ticket được đóng. Vài giờ sau, ứng dụng báo thiếu dữ liệu ở một số partition. Hóa ra quá trình bootstrap/streaming chưa được kiểm chứng đầy đủ và không ai ghi lại **ai chạy lệnh, trên node nào, với tham số nào, vào thời điểm nào**, cũng như **trạng thái replica trước/sau**.

Một quy trình vận hành đáng tin cậy phải trả lời **ba câu hỏi độc lập**:

1. **Ai được phép làm gì?** Người dùng ứng dụng, DBA, SRE, automation và tài khoản quản trị không được có cùng quyền mặc định.
2. **Đã thực hiện chính xác hành động gì?** Cần ghi danh tính, thời gian, mục tiêu, lệnh đã chuẩn hóa, kết quả và liên kết tới phiên thay đổi, nhưng không lộ bí mật.
3. **Có đạt hậu điều kiện mong đợi không?** Lệnh được khởi chạy hoặc trả về thành công **không luôn đồng nghĩa cluster đã ở trạng thái an toàn**.

**Mục tiêu học tập:** phân biệt quyền **CQL RBAC** với quyền **JMX/nodetool và hệ điều hành**, dùng nguyên tắc least privilege, thiết kế audit trail, chuẩn hóa quy trình *before → execute → verify*, thực hành CQL và công cụ quản trị, đồng thời biết cách điều tra trường hợp thao tác chạy một phần hoặc tạo tác dụng phụ.

**Giới hạn:** Cassandra có nhiều thế hệ và cách triển khai. CQL permissions, audit logging, JMX security, cú pháp `nodetool`, cơ chế vận hành qua SSH/container hoặc nền tảng quản lý có thể khác theo phiên bản. Các mẫu là **khung runbook** và lab; không chạy trực tiếp trên production nếu chưa đối chiếu tài liệu và cấu hình thật.

## 2. Bản đồ bề mặt quản trị: không chỉ có một loại “quyền Cassandra”

~~~mermaid
flowchart TD
    A["Người vận hành / Automation"] --> B["Bastion / IAM / SSO / approval"]
    B --> C["CQL qua cqlsh / Java Driver"]
    B --> D["nodetool qua JMX"]
    B --> E["SSH, Kubernetes, systemd, OS"]
    C --> F["Cassandra authn/authz: roles + CQL permissions"]
    D --> G["JMX authentication/authorization + network/TLS"]
    E --> H["OS/service account, sudo, container RBAC"]
    F --> I["Keyspace/table/role/schema operations"]
    G --> J["Node management và JMX MBeans"]
    H --> K["Config, restart, file/log/snapshot access"]
    I --> L["Audit và post-change verification"]
    J --> L
    K --> L
~~~

| Kênh truy cập | Danh tính/ủy quyền điển hình | Ví dụ | Sai lầm phổ biến |
| --- | --- | --- | --- |
| **CQL native protocol** | Cassandra `Authenticator`, `Authorizer`, roles và permissions nếu được bật | `SELECT`, `INSERT`, `ALTER TABLE`, `GRANT` | Tưởng role chỉ có `SELECT` cũng chạy được mọi lệnh `nodetool`. |
| **JMX/nodetool** | JMX authentication, authorization/MBean access và bảo vệ mạng theo bản triển khai | `status`, `repair`, `snapshot`, `cleanup` | Tưởng quyền CQL tự động giới hạn `nodetool repair`. |
| **OS/service manager** | SSH/SSO, sudo, file ACL, systemd/service account | Đọc log, đổi cấu hình, restart node | Cho mọi người quyền `root` hoặc quyền ghi thư mục SSTable. |
| **Container/orchestrator** | Kubernetes/cluster RBAC, admission policies, workload identity | `kubectl exec`, thay secret, restart pod | Đánh đồng quyền vào namespace với quyền đọc/ghi Cassandra. |
| **Backup/monitoring** | IAM, secret store, object storage policy, JMX exporter/API credentials | Lấy snapshot, xuất backup, xem metrics | Cho tài khoản chỉ đọc dashboard quyền xóa backup. |
| **CI/CD/automation** | Service identity, secret ngắn hạn, approval/policy của pipeline | Schema migration, runbook bảo trì | Dùng chung một tài khoản superuser cho mọi pipeline. |

**Điểm mấu chốt:** một người có thể bị giới hạn `SELECT` trong CQL nhưng vẫn gây thay đổi lớn nếu họ có **SSH root** hoặc quyền **JMX quản trị không hạn chế**. Đánh giá quyền phải đi từ **mọi đường có thể tác động đến dữ liệu**, không chỉ câu lệnh `GRANT`.

## 3. Xác thực, phân quyền và nguyên tắc least privilege

### 3.1. Tách authentication khỏi authorization

- **Authentication:** xác định *ai đang kết nối* (password, chứng chỉ, identity của automation hay cơ chế được cấu hình).
- **Authorization:** xác định danh tính đó **được phép thực hiện hành động nào** trên tài nguyên nào.
- **Audit/accountability:** giữ bằng chứng có thể đối chiếu việc *danh tính nào đã thử và thực hiện điều gì*.

Trong Cassandra, cấu hình authn/authz thường được khai báo ở server; ở các triển khai có thể tồn tại `PasswordAuthenticator`, `CassandraAuthorizer` hoặc nhà cung cấp khác. **Không suy rằng cluster đang bật RBAC chỉ vì câu CQL `GRANT` tồn tại trong tài liệu.** Phải xác minh cấu hình thật, phân quyền đang được thực thi, kết nối native protocol có TLS phù hợp và tài khoản mặc định đã được bảo vệ.

### 3.2. Thiết kế nhóm vai trò thay vì cấp quyền tràn lan

| Vai trò nghiệp vụ | Quyền cần cân nhắc | Không nên có theo mặc định |
| --- | --- | --- |
| **Ứng dụng đọc dữ liệu** | `SELECT` trên các bảng phục vụ đọc. | `MODIFY`, `DROP`, `ALTER`, `AUTHORIZE`, quyền JMX. |
| **Ứng dụng ghi dữ liệu** | `MODIFY` trên bảng cần ghi; `SELECT` nếu cần kiểm tra. | `CREATE ROLE`, `ALTER KEYSPACE`, quyền xoá snapshot/file. |
| **Service analytics** | `SELECT` trên bảng/projection được phép, có rate limit. | Quyền thay đổi schema, truy cập mọi tenant khi không cần. |
| **Nhóm schema migration** | Quyền schema cần thiết theo dự án và thời hạn. | Superuser tồn tại vĩnh viễn, quyền restart node. |
| **SRE quan sát** | Read-only JMX/metrics, trạng thái và log có lọc dữ liệu nhạy cảm. | Lệnh thao tác `repair`, `cleanup`, `drain`, `stop` khi không cần. |
| **SRE bảo trì** | Quyền chạy runbook cụ thể trong cửa sổ được duyệt. | Quyền rộng vô thời hạn trên mọi DC. |
| **Backup operator** | Tạo/xuất snapshot, ghi vùng backup được chỉ định. | Xóa backup theo ý muốn hoặc sửa dữ liệu CQL. |
| **Security/auditor** | Đọc audit event đã bảo vệ và báo cáo quyền. | Sửa hoặc xóa audit event gốc. |

Nguyên tắc **least privilege** nghĩa là cấp ít quyền nhất **đủ làm công việc**, ở phạm vi **bảng/keyspace/node/DC** hẹp nhất, với **thời hạn** hợp lý. Dùng danh tính riêng cho từng người và service; không chia sẻ password `cassandra` hoặc tài khoản root.

### 3.3. Quyền sửa schema và quyền đọc dữ liệu là hai loại rủi ro khác nhau

Thay schema như `ALTER TABLE`, `DROP TABLE`, thay RF của keyspace có thể ảnh hưởng **toàn cluster**. Đọc dữ liệu cũng có rủi ro bảo mật và tải, nhất là `ALLOW FILTERING` hoặc quét nhiều partition. Vì vậy:

- Phân quyền CQL phải kết hợp **giới hạn truy vấn, rate limiting và guardrail**.
- `SELECT` không đồng nghĩa vô hại: truy vấn read-heavy có thể chiếm I/O trên replica.
- `MODIFY` thường bao gồm khả năng ghi/xóa dữ liệu trên tài nguyên được phép; không cấp cho role chỉ cần đọc.
- Thao tác sửa schema quan trọng phải đi qua **pipeline/migration approval**, không được xem là thay đổi cấu hình bình thường của ứng dụng.

## 4. CQL RBAC lab: một vai trò chỉ đọc và cách kiểm tra thực quyền

### 4.1. Tạo dữ liệu demo

Giả sử cluster lab có DC `dc1`, đủ node cho RF = 3 và đã bật authentication/authorization phù hợp:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_ops
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_ops.device_events (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO telemetry_ops.device_events
  (device_id, event_day, event_time, event_id, event_type)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T10:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'heartbeat');
~~~

**Mô hình dữ liệu:** partition key `(device_id, event_day)` phục vụ đọc theo thiết bị/ngày; clustering `event_time, event_id` phục vụ thứ tự thời gian. Cách thiết kế này giảm nguy cơ một partition tăng vô hạn, nhưng không thay nhu cầu giám sát partition size và SLO.

### 4.2. Tạo role không có quyền login làm nhóm phân quyền

Các lệnh sau **chỉ được chạy bằng tài khoản DBA có quyền phù hợp trong lab**, không phải tài khoản ứng dụng:

~~~sql
-- Role nhóm không thể đăng nhập trực tiếp.
CREATE ROLE IF NOT EXISTS telemetry_event_viewer
WITH LOGIN = false;

-- Chỉ cho phép đọc đúng bảng, không cấp MODIFY.
GRANT SELECT ON TABLE telemetry_ops.device_events
TO telemetry_event_viewer;

-- Liệt kê quyền để đối chiếu với policy.
LIST ALL PERMISSIONS OF telemetry_event_viewer;
~~~

Khi provisioning một tài khoản đăng nhập của con người/service bằng hệ thống quản lý danh tính và secret phù hợp, administrator có thể gán membership:

~~~sql
-- analyst_identity là role đăng nhập đã được cấp riêng theo quy trình.
GRANT telemetry_event_viewer TO analyst_identity;

-- Xem quyền hiệu lực theo cú pháp/phiên bản được hỗ trợ.
LIST ALL PERMISSIONS OF analyst_identity;
~~~

**Không chạy dòng `GRANT ... TO analyst_identity` khi role đó chưa được provisioning**. Tránh nhúng password thực trong ví dụ/tutorial, shell history hoặc ticket. Nếu phải tạo role với password, dùng công cụ provisioning an toàn, cơ chế cấp secret được phê duyệt và thay đổi/thu hồi đúng chính sách.

### 4.3. Kiểm tra bằng cả “cho phép” lẫn “từ chối”

Trong lab, đăng nhập bằng tài khoản đã gán role viewer, kiểm tra:

~~~sql
-- Phải được phép nếu các điều kiện authz đúng:
SELECT event_time, event_type
FROM telemetry_ops.device_events
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

-- KHÔNG thực thi trên dữ liệu thật chỉ để kiểm thử!
-- Thử trên bảng lab riêng có rollback và xác minh lệnh bị từ chối:
-- DELETE FROM telemetry_ops.device_events
-- WHERE device_id = 'device-7' AND event_day = '2026-11-21';
~~~

Trong ví dụ này role viewer chỉ nên đọc. Nếu `DELETE` hoặc `ALTER TABLE` vẫn thành công khi chạy qua tài khoản chỉ đọc, cần kiểm tra **role membership gián tiếp, quyền được cấp ở cấp keyspace rộng hơn, superuser và trạng thái authorizer**; không chỉ nhìn một dòng `GRANT SELECT`.

**Sau kiểm thử:** dùng công cụ xem quyền/role của phiên bản (ví dụ `LIST ALL PERMISSIONS`, `LIST ROLES` khi hỗ trợ), đồng thời đối chiếu sự kiện audit. **Một lệnh trả lỗi Unauthorized chứng minh một phép thử bị từ chối**, không tự chứng minh toàn bộ mô hình phân quyền đã an toàn trước mọi đường JMX/OS.

## 5. Phân quyền `nodetool`: ranh giới giữa JMX và CQL

`nodetool` thường sử dụng **JMX** để giao tiếp với MBeans quản trị của Cassandra. Một vài lệnh mang tính đọc:

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool listsnapshots
~~~

Một số lệnh có thể thay đổi trạng thái hoặc tạo tải:

~~~bash
# MINH HỌA CÚ PHÁP, KHÔNG chạy toàn bộ trên production:
nodetool snapshot -t ops-lab-01 telemetry_ops
nodetool repair telemetry_ops
nodetool cleanup telemetry_ops device_events
nodetool flush telemetry_ops device_events
~~~

| Lệnh | Rủi ro vận hành chính | Hậu điều kiện cần xác minh |
| --- | --- | --- |
| `status`, `info` | Chủ yếu quan sát; có thể lộ topology/thông tin vận hành | Kết quả thu được từ đúng cluster và đúng thời điểm. |
| `snapshot` | Giữ SSTable cũ, có thể làm dung lượng tăng về sau | Snapshot tag xuất hiện trên **đúng node/bảng**; retention và backup plan rõ. |
| `repair` | Validation, streaming, CPU/disk/network; có thể kéo dài | Phiên repair hoàn tất theo scope/ranges và logs, không chỉ lệnh được gọi. |
| `cleanup` | Loại dữ liệu node không còn sở hữu; nguy hiểm nếu topology đang chuyển | Bootstrap/streaming trước đó đã hoàn tất; dữ liệu còn đúng trên natural replicas. |
| `flush` | Ghi memtable ra SSTable, phát sinh I/O/compaction | Flush kết thúc, node còn headroom; không nhầm với backup. |
| `compact` | Có thể tạo SSTable lớn và tiêu thụ disk tạm | Compaction không gây đầy disk và backlog không tăng mất kiểm soát. |
| `drain`, `stop`, `decommission` | Ảnh hưởng khả năng phục vụ/topology, có thể gây mất quorum | Chỉ dùng theo runbook riêng với điều kiện trước/sau rất chặt. |

### 5.1. JMX security cần được kiểm soát riêng

**CQL role không mặc nhiên bảo vệ JMX.** Với các triển khai Cassandra dùng remote JMX (cổng thường gặp trong một số cấu hình là `7199`), cần đánh giá:

- Endpoint JMX có chỉ được phép truy cập từ mạng quản trị/bastion không? Có bị mở ra Internet hoặc mạng ứng dụng không?
- Đã bật cơ chế **JMX authentication/authorization** phù hợp và mã hóa đường truyền theo phiên bản chưa?
- Có thể phân biệt quyền **đọc metrics** với quyền **invoke MBean operation thay đổi trạng thái** không?
- Công cụ `nodetool` thực tế sử dụng credentials nào; mật khẩu có nằm trên command line/log/shell history không?
- Có cách nào đi vòng JMX qua SSH root, container exec hoặc JMX agent không được quản lý?

Các thuộc tính JVM/JMX và cách giới hạn MBean access khác nhau theo Cassandra/JDK. **Không sao chép mù cấu hình JMX security của phiên bản khác.** Đặc biệt, không tắt authentication/TLS hoặc mở cổng quản trị rộng chỉ để “cho `nodetool` chạy được”.

### 5.2. Mô hình triển khai ít quyền

~~~text
SRE xem trạng thái
  → SSO + bastion → read-only monitoring/JMX capability (nếu hỗ trợ)

SRE cần repair
  → change ticket + approval + temporary credential
  → automation chạy nodetool trên node được duyệt
  → lưu logs/session ID/exit status + kiểm tra postconditions

Ứng dụng Java
  → native CQL với role SELECT/MODIFY tối thiểu
  → không có SSH root hoặc quyền JMX manage
~~~

Trong hệ thống chưa thể phân quyền JMX chi tiết, nên đặt **automation wrapper/runbook** ở lớp điều phối với allowlist tham số, kiểm tra phạm vi và chính sách duyệt. Không cho người dùng tùy ý truyền shell command vào automation có quyền cao.

## 6. Quyền truy cập log, dữ liệu và backup cũng là vấn đề bảo mật

Một tài khoản chỉ đọc log vẫn có thể nhìn thấy **CQL text, địa chỉ node, dữ liệu nhận dạng, partition key, trace ID, stack trace hoặc kết nối nhạy cảm** tùy logging level. Backup/snapshot có thể chứa toàn bộ dữ liệu người dùng, nên quyền `download snapshot` cần được xem gần với quyền **truy cập dữ liệu thực**, không phải một quyền “vận hành vô hại”.

| Tài nguyên | Quyền cần kiểm soát | Khuyến nghị |
| --- | --- | --- |
| System/debug/GC logs | Đọc, thay retention, xóa/ghi đè | Tách viewer với log admin; lọc bí mật, chỉ giữ trong thời gian cần thiết. |
| `system_traces` và CQL audit logs | Đọc nội dung truy vấn và trace event | Dùng RBAC, retention, hạn chế payload, không gửi toàn bộ sang hệ thống không tin cậy. |
| Snapshot/backup storage | Tạo, đọc, tải xuống, xóa và đặt retention | Mã hóa, least privilege, tách người tạo và người xóa, bảo vệ backup không thể sửa nếu khả thi. |
| Cassandra data directories | Đọc/ghi SSTable, commit log, hints | Chỉ service account và runbook có quyền đặc biệt; không xóa thủ công. |
| Secret/config files | Password, TLS key, JMX credentials | Secret manager và ACL chặt, không đưa vào ticket, stdout hoặc artifact của CI. |
| Metrics endpoints | Topology, IP, throughput, error patterns | Giới hạn mạng/truy cập, không coi metrics là public mặc định. |

**Không ghi mật khẩu hoặc key trực tiếp vào dòng lệnh** khi cách đó có thể lộ qua process list, shell history hay nhật ký pipeline. Cách cung cấp credential an toàn phụ thuộc công cụ/OS, nhưng nguyên tắc chung là dùng **secret manager, identity ngắn hạn và redaction**; không biến yêu cầu audit thành việc xuất bí mật vào log.

## 7. Ghi nhật ký thao tác: audit phải nối được danh tính với hậu quả

### 7.1. Bản ghi audit tối thiểu

Một sự kiện quản trị hữu ích phải giúp một người khác tái dựng việc **ai làm gì, ở đâu, tại sao và kết quả ra sao**:

~~~text
change_id            : CHG-2026-11-21-0042
action_id            : 8b31... (ID riêng cho lần thực thi)
actor_identity       : sre.maintenance@example.invalid
effective_identity   : temporary-ops-role / automation-runner-01
approval_id          : CAB-1842
cluster              : cassandra-prod-main
datacenter           : dc1
node                 : cassandra-dc1-n2
operation            : nodetool.snapshot
approved_scope       : keyspace=telemetry_ops, node=dc1-n2
arguments_redacted   : snapshot tag=CHG-2026-11-21-0042
started_at_utc       : 2026-11-21T10:10:00Z
finished_at_utc      : 2026-11-21T10:10:18Z
execution_status     : command-exit-0
postcheck_status     : verified / failed / pending
evidence_refs        : log-archive-id, snapshot-inventory-id
rollback_or_recovery : reference-to-runbook
~~~

**Đây là schema audit do hệ vận hành thiết kế**, không phải bảng Cassandra mặc định. Không dùng email giả lập trong ví dụ làm định danh production và không lưu credentials, payload người dùng hoặc token phiên đăng nhập trong `arguments_redacted`.

Quan trọng nhất là **tách `execution_status` khỏi `postcheck_status`**. Exit code 0 chỉ là tín hiệu **công cụ cho rằng lệnh đã hoàn tất**; chưa chứng minh dữ liệu/replica/dung lượng sau thao tác đúng mục tiêu.

### 7.2. Những sự kiện cần ghi

| Giai đoạn | Event nên lưu | Mục đích |
| --- | --- | --- |
| **Yêu cầu** | Người đề xuất, lý do, rủi ro, scope, dự kiến impact | Giải thích tại sao thao tác được phép. |
| **Duyệt** | Người duyệt độc lập, thời hạn, điều kiện chạy | Tránh tự duyệt hành động rủi ro cao. |
| **Chuẩn bị** | Phiên bản Cassandra, topology, RF/CL, node health, backup, precheck | Có baseline so sánh và khả năng rollback/khôi phục. |
| **Thực thi** | Actor, effective identity, command template + tham số đã che bí mật, mốc UTC | Truy vết hành động và phạm vi thật. |
| **Kết quả công cụ** | Exit status, stdout/stderr đã lọc, session ID, warnings, lỗi | Phân biệt lệnh thất bại, thành công, hoặc chỉ khởi chạy công việc nền. |
| **Hậu kiểm** | Metrics/log/trạng thái replica, kết quả truy vấn mẫu, snapshot inventory | Xác minh mục tiêu thực sự đạt. |
| **Đóng change** | Kết luận, người xác nhận, tồn đọng, bước follow-up | Không bỏ quên tác vụ chạy dở và rủi ro kéo dài. |

Audit phải lưu **theo UTC, có đồng bộ đồng hồ, append-only/immutable khi khả thi**, được xuất khỏi node trước khi người có quyền hệ thống có thể xóa hoặc thay log. Hệ thống cần quy định retention, quyền đọc và thời điểm purge theo yêu cầu bảo mật.

### 7.3. Không chỉ dựa vào audit CQL

Cassandra phiên bản hiện đại có thể hỗ trợ **audit logging** cho các hoạt động CQL theo cấu hình. Tuy nhiên **không phải mọi** phiên bản/edition/triển khai đều ghi mọi hành động giống nhau. Đặc biệt:

- CQL audit có thể ghi `CREATE/ALTER/GRANT/SELECT` theo nhóm sự kiện được bật, nhưng **không mặc nhiên ghi toàn bộ thao tác `nodetool` qua JMX**.
- Hành động OS như đổi `cassandra.yaml`, restart service, xóa file hoặc truy cập secret store nằm **ngoài phạm vi CQL audit**.
- Khi log bị tắt, đầy disk, exporter lỗi hoặc node chết, có thể thiếu audit event. **Thiếu log không chứng minh thao tác không diễn ra**.
- Ghi quá chi tiết mọi `SELECT` có thể tạo I/O/chi phí rất lớn và gây rủi ro dữ liệu nhạy cảm. Cần lọc, sampling/retention và bảo vệ quyền.

Vì vậy hãy kết hợp **CQL audit (nếu có)**, **bastion/SSH session recording**, **JMX management wrapper logs**, **CI/CD activity**, **OS/service logs** và **monitoring/tracing** thành một chuỗi bằng chứng. Audit logging có thể có tác động hiệu năng; việc bật/cấu hình theo version phải được thử nghiệm.

## 8. Quy trình chuẩn before → execute → verify → close

~~~mermaid
flowchart TD
    A["Nhận yêu cầu thao tác"] --> B["Xác định actor, quyền, scope và impact"]
    B --> C{"Có ticket, approval, window hợp lệ?"}
    C -->|Không| Z["Dừng / xin phê duyệt"]
    C -->|Có| D["Precheck: topology, RF/CL, disk, logs, backup"]
    D --> E{"Điều kiện an toàn đạt?"}
    E -->|Không| Z
    E -->|Có| F["Cấp credential tạm / chạy lệnh đã allowlist"]
    F --> G["Lưu action ID, UTC, tham số đã che, exit/log/session"]
    G --> H["Postcheck nhiều nguồn, cả dữ liệu và tài nguyên"]
    H --> I{"Đạt hậu điều kiện?"}
    I -->|Có| J["Thu hồi quyền tạm, đóng change và lưu bằng chứng"]
    I -->|Không / chưa rõ| K["Giữ change mở, điều tra / khôi phục theo runbook"]
    K --> H
~~~

### 8.1. Before: điều kiện tiền đề

Một checklist phổ quát cho lệnh có tác động:

1. **Xác định mục tiêu:** cluster, DC, node, keyspace, table, token range, snapshot tag hoặc session ID.
2. **Xác định tác động:** chỉ đọc, tạo file, stream dữ liệu, sửa topology hay xóa dữ liệu không còn thuộc sở hữu?
3. **Kiểm tra quyền:** actor có quyền đúng scope, effective identity không phải tài khoản chia sẻ, credential sắp hết hạn chưa?
4. **Kiểm tra RF/CL và health:** có node `DN`, `UJ`, `UL`, sửa topology/repair khác đang chạy không?
5. **Kiểm tra tài nguyên:** free disk/headroom, compaction backlog, network/streaming, heap/GC, read/write p99 và error rate.
6. **Kiểm tra recovery:** backup/snapshot đang khả dụng, có quy trình khôi phục thực tế, người chịu trách nhiệm và ranh giới rollback chưa?
7. **Kiểm tra lịch:** khung bảo trì, concurrency, tránh overlap các tác vụ nặng, kế hoạch thông báo nếu ảnh hưởng người dùng.
8. **Ghi baseline:** UTC, phiên bản Cassandra/JDK, `nodetool status`, metric và trạng thái dữ liệu mẫu liên quan.

### 8.2. Execute: thao tác nhỏ, có thể truy dấu

Ưu tiên **một lệnh có phạm vi hẹp trước**, đặt tên snapshot/tag/session gắn change ID và thu nhận log ngay. Nếu cần chạy trên nhiều node:

- Chỉ định **thứ tự node**, giới hạn số node/lệnh song song.
- Không chạy đồng thời các thao tác có thể làm **mất quorum** hoặc tranh disk/network nặng.
- Giữ một phiên bản cấu hình/topology nhất quán trong cả kế hoạch; nếu cluster đổi ownership giữa chừng, phải replan.
- Không đưa command string người dùng vào shell với quyền cao mà thiếu **allowlist, escaping và validation**.
- Không sửa `cassandra.yaml` hoặc thay đổi `GRANT` khác ngoài phạm vi duyệt.

### 8.3. Verify: xác minh độc lập với exit code

Một thao tác có thể có **hai loại kết quả**:

~~~text
Tool outcome:         command exited 0 / command failed / disconnected / unknown
System postcondition: verified / failed / pending / inconclusive
~~~

Ví dụ `nodetool repair` trả kết quả ở một node không đủ để kết luận **mọi token range, mọi replica/DC và mọi bảng** đều hội tụ. `nodetool snapshot` báo thành công chưa đủ để kết luận **backup đã xuất khỏi máy và khôi phục được**. Tạo role CQL thành công chưa chứng minh role thực sự thiếu những quyền được thừa kế ngoài ý muốn.

Hậu kiểm cần **bằng chứng từ thành phần nhận tác động**, ví dụ:

- CQL permission: đăng nhập role thực, thử lệnh cho phép và lệnh phải bị từ chối.
- Replica/repair: kiểm tra repair session logs, phạm vi đã xử lý, node health và error counters.
- Snapshot: inventory `listsnapshots`, backup manifest, dữ liệu sao lưu và thử restore theo quy trình.
- Topology: `status`, token map, streaming completion, natural endpoints và read/write kiểm soát.
- Hiệu năng: p95/p99, timeout, disk free, compaction/GC/hints trước và sau.

## 9. Postcheck theo từng loại thao tác phổ biến

| Thao tác | Precheck quan trọng | Postcheck quan trọng | Nguy cơ đóng ticket quá sớm |
| --- | --- | --- | --- |
| **CQL schema migration** | Quyền schema, tương thích client, cluster health, migration order. | Schema agreement, metadata đúng, application read/write canary. | Schema đã thay nhưng ứng dụng chưa tương thích. |
| **`GRANT`/`REVOKE`** | Vai trò và quyền hiệu lực hiện tại, membership. | `LIST PERMISSIONS`, test allow/deny bằng account thật, audit event. | Role được kế thừa quyền rộng hơn ngoài dự định. |
| **`snapshot`** | Free disk, tag không trùng, backup retention. | Tag có trong inventory đúng node/bảng, export manifest và restore test. | Tưởng snapshot cục bộ đã là backup ngoài cluster. |
| **`repair`** | RF, DC scope, token ownership, node health, tombstone deadline. | Repair hoàn tất đúng range và participants, streaming/errors đã ổn. | Bỏ sót một DC hoặc subrange bị fail. |
| **`cleanup`** | Bootstrap/streaming hoàn tất, ownership mới ổn định, backup. | Active disk/SSTable trend hợp lý, dữ liệu có trên replica mới. | Dọn bản sao cũ trước khi chuyển đủ dữ liệu. |
| **`flush`** | Disk headroom, compaction backlog. | Flush kết thúc, SSTables và file/queue được quản lý bình thường. | Tưởng flush đã backup hoặc đồng bộ replica. |
| **`compact`** | Disk headroom, compaction policy, tác vụ chồng chéo. | Task kết thúc, không hết disk, read/write latency hồi phục. | File output tạm làm đầy disk. |
| **Thay RF / thêm DC** | NTS, rack/DC, capacity, plan streaming và CL. | Replica mới có dữ liệu, repair/rebuild phù hợp, canary từng DC. | Chỉ `ALTER KEYSPACE` rồi coi đã đủ replica mới. |
| **Restart/decommission** | Sức khỏe quorum, node khác, automation và recovery plan. | Node/trạng thái ring như kỳ vọng, client SLO, data transfer hoàn tất. | Mất thêm node làm quorum không thể phục vụ. |

Lưu ý: một vài lệnh có **thực thi nền hoặc nhiều pha**, một số có thể bị ngắt/timeout sau khi đã tác động một phần. Luôn xem tài liệu lệnh theo phiên bản và **đo hậu điều kiện**, không suy trạng thái từ một dòng stdout.

## 10. Lab: snapshot có giám sát và xác minh

Lab này giúp luyện cách **ghi action ID, precheck và postcheck** mà không yêu cầu chạy repair/cleanup nguy hiểm. Cần node Cassandra lab, quyền được duyệt và keyspace `telemetry_ops` ở mục 4.

### 10.1. Kiểm tra trước khi tạo snapshot

~~~bash
# Trên đúng node lab được phê duyệt.
nodetool status
nodetool info
nodetool compactionstats
nodetool listsnapshots
nodetool help snapshot
~~~

Trong hệ Linux, kiểm tra đúng mount point chứa data directory:

~~~bash
df -h
~~~

Ghi lại **UTC, tên node, cluster, keyspace, phiên bản, free disk và danh sách snapshot hiện có**. Một số triển khai có auto-snapshot trước khi truncate/drop và các snapshot đó cũng chịu retention, nên phải xem inventory trước khi tạo thêm bản mới.

### 10.2. Thực thi đúng node và đúng tag

~~~bash
# Chỉ chạy trong LAB. Tag gắn với action/change ID.
nodetool snapshot -t ops-lab-20261121-01 telemetry_ops
~~~

Nếu phiên bản cho phép chọn table hoặc có tùy chọn snapshot khác, kiểm tra `nodetool help snapshot` của **chính phiên bản đó**. Không chạy một snapshot toàn cluster theo suy luận: `nodetool snapshot` được khởi chạy trên **node chỉ định**, và snapshot nhất quán ở cấp cluster/application có yêu cầu tổ chức riêng.

### 10.3. Xác minh kết quả và khả năng phục hồi

~~~bash
nodetool listsnapshots
nodetool status
nodetool compactionstats
~~~

Checklist kết thúc:

1. Snapshot tag `ops-lab-20261121-01` có xuất hiện trên **đúng node/keyspace/table** không?
2. Không có lỗi snapshot trong system log; disk headroom còn an toàn không?
3. File snapshot và metadata cần cho quy trình restore có được inventory đầy đủ không?
4. Nếu đây là backup thực, đã **xuất ra lưu trữ độc lập**, có manifest/checksum và thử restore chưa?
5. Audit event có ghi **actor, node, tag, thời gian, exit status, verification status** chưa?

**Không tự chạy `clearsnapshot` trên production chỉ để kết thúc bài lab.** Ở lab riêng, chỉ dọn snapshot nếu không còn nhu cầu recovery và theo cú pháp/retention đã kiểm tra; snapshot có thể giữ SSTable cũ qua hard links, nhưng không thể suy số byte thu hồi trực tiếp từ kích thước snapshot hiển thị.

### 10.4. Ví dụ một postcheck record

~~~text
action_id           : ops-lab-20261121-01
cluster/node        : lab / cassandra-lab-02
command             : nodetool snapshot -t ops-lab-20261121-01 telemetry_ops
tool_exit           : 0
observed_tag        : present on cassandra-lab-02
disk_free_after     : measured; not assumed
backup_exported     : no (local snapshot lab only)
restore_verified    : no
postcheck_status    : VERIFIED_LOCAL_SNAPSHOT_ONLY
next_action         : if production backup, export + restore validation
~~~

Kết luận **`VERIFIED_LOCAL_SNAPSHOT_ONLY`** chính xác hơn `BACKUP_COMPLETE`. Đây là ví dụ quan trọng của nguyên tắc **đặt tên trạng thái theo bằng chứng đã có, không theo điều mong muốn**.

## 11. Khi thao tác thất bại giữa chừng: UNKNOWN khác FAILED

Một tình huống điển hình: automation gọi `nodetool repair`, kết nối SSH bị mất sau 30 phút. Shell trả mã lỗi do đường quản trị bị ngắt; nhưng repair session có thể vẫn đang chạy, đã hoàn tất một phần hoặc đã thất bại thật.

~~~mermaid
flowchart TD
    A["Khởi chạy thao tác có action ID"] --> B{"Có xác nhận kết thúc đáng tin?"}
    B -->|Có, thành công| C["Kiểm chứng hậu điều kiện"]
    B -->|Có, thất bại| D["FAILED: xem phần đã tác động"]
    B -->|Không| U["UNKNOWN: không đoán là chưa chạy"]
    U --> E["Đối chiếu log, session ID, trạng thái node/task"]
    D --> E
    E --> F{"Topology/scope còn phù hợp và retry an toàn?"}
    F -->|Có| G["Retry có kiểm soát, cùng action/runbook"]
    F -->|Không| H["Dừng, replan/restore theo quy trình"]
    C --> I{"Postconditions đạt?"}
    I -->|Có| J["VERIFIED và đóng change"]
    I -->|Không| E
~~~

**Không tự retry một lệnh nặng hoặc phá hủy chỉ vì client mất kết nối.** Retry có thể trùng phiên repair/compaction hoặc lặp thao tác với state mới. Tương tự:

- `ALTER KEYSPACE` trả timeout: schema metadata có thể đã thay; đọc lại metadata/trạng thái schema agreement trước khi gửi lại.
- `nodetool cleanup` ngắt giữa chừng: có thể có phần SSTable đã được xử lý; kiểm tra topology/data ownership và logs.
- `snapshot` mất kết nối: tag có thể đã tồn tại; kiểm tra inventory trước khi tạo tag mới, tránh trùng/over-retention.
- Lệnh `REVOKE` không rõ kết quả: test permissions **bằng tài khoản hiệu lực**, không chỉ tin API response.

Một runbook nên có **trạng thái `PENDING`, `RUNNING`, `VERIFIED`, `FAILED`, `UNKNOWN`, `NEEDS_REPLAN`**. Trạng thái `UNKNOWN` giúp tách “mất kênh quan sát” khỏi “Cassandra chắc chắn chưa làm gì”.

## 12. Truy vết từ ứng dụng Java: ghi bằng chứng mà không cấp quyền DBA cho app

Ứng dụng **Apache Cassandra Java Driver 4.x** có nhiệm vụ đọc/ghi dữ liệu nghiệp vụ theo CQL role tối thiểu. Nó có thể ghi log **query name, CL, thời gian, kết quả và warning**, nhưng không nên được trao quyền chạy `nodetool`, `ALTER KEYSPACE` hoặc xóa snapshot chỉ để tiện lập trình.

Ví dụ Java chỉ đọc một partition trên keyspace lab:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class AuditedReadExample {
    public static void main(String[] args) {
        // Danh tính/secret/TLS thật phải cấu hình bằng provisioning an toàn.
        // Ví dụ này chỉ định local DC và contact point của lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, event_type " +
                "FROM telemetry_ops.device_events " +
                "WHERE device_id = ? AND event_day = ? LIMIT 20");

            BoundStatement read = prepared.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            // Correlation ID do ứng dụng tạo, dùng để ghép log client.
            // Cassandra không tự nhận ID này nếu không có cơ chế truyền riêng.
            UUID correlationId = UUID.randomUUID();
            Instant startedUtc = Instant.now();
            long startedNanos = System.nanoTime();

            try {
                ResultSet result = session.execute(read);
                ExecutionInfo info = result.getExecutionInfo();
                int count = 0;
                for (Row row : result) {
                    count++;
                }
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedNanos);

                // Thực tế: structured logging, redaction, retention.
                System.out.println("query=read_device_events"
                    + " correlation_id=" + correlationId
                    + " started_utc=" + startedUtc
                    + " cl=LOCAL_QUORUM status=success"
                    + " rows=" + count + " elapsed_ms=" + elapsedMs
                    + " warnings=" + info.getWarnings().size());
            } catch (RuntimeException ex) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedNanos);
                System.err.println("query=read_device_events"
                    + " correlation_id=" + correlationId
                    + " started_utc=" + startedUtc
                    + " cl=LOCAL_QUORUM status=failure"
                    + " elapsed_ms=" + elapsedMs
                    + " error_type=" + ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }
}
~~~

**Những điều cần hiểu đúng:**

1. `LOCAL_QUORUM` với `dc1:3` yêu cầu **hai phản hồi replica** trong local DC. Một SELECT thành công không chứng minh mọi full replica đã đồng nhất.
2. `System.nanoTime()` đo **duration**, `Instant.now()` ghi thời điểm UTC; không dùng monotonic clock như timestamp UTC.
3. `correlationId` trong ví dụ chỉ nằm ở log client; muốn nối tới server phải dùng **trace session ID hoặc cơ chế correlation được triển khai thật**, không giả định server biết ID.
4. `ExecutionInfo.getWarnings()` chỉ có warnings của lần thực thi phù hợp, **không đại diện toàn bộ audit CQL** và không bảo đảm chứa mọi cảnh báo trên cluster.
5. Không ghi `device_id`, toàn bộ `payload`, secret, token đăng nhập hoặc raw CQL kèm literal nhạy cảm vào telemetry diện rộng. `correlation_id` là log field, không nên thành label metric có cardinality vô hạn.
6. Java Driver của ứng dụng **không tự thay thế audit của lớp JMX/OS**. Một hành động vận hành phải có audit riêng dù ứng dụng vẫn đang chạy.

### 12.1. Tại sao cần quyền riêng cho ứng dụng và automation?

Nếu tài khoản Java dùng để đọc sự kiện đồng thời có quyền schema/JMX, một lỗ hổng trong API nghiệp vụ có thể bị khai thác để sửa hoặc phá cluster. Ngược lại, automation repair không nên có quyền đọc mọi bảng chứa dữ liệu nhạy cảm nếu chỉ cần JMX operation cụ thể. Hãy tách **identity và blast radius** giữa workload ứng dụng và hệ điều phối bảo trì.

## 13. Multi-datacenter: phạm vi thao tác không trùng phạm vi hệ quả

Với `NetworkTopologyStrategy`, một keyspace có thể đặt `dc1:3`, `dc2:2`. Một lệnh `nodetool` trên một node thường **không tự chứng minh** đã tác động hoặc xác minh toàn cluster:

- `nodetool status` hiển thị membership nhưng không chứng minh mọi partition đã được repair.
- `snapshot` trên N1 không tạo snapshot đồng thời trên mọi node/DC.
- `repair` có scope node, keyspace/table, token ranges và participant replicas theo tùy chọn phiên bản; chỉ sửa trong `dc1` không bảo đảm `dc2` đã hội tụ.
- `cleanup` dọn dữ liệu cục bộ không còn thuộc node, không tự streaming dữ liệu sang DC mới.
- `ALTER KEYSPACE` thay RF metadata, không tự xác minh dữ liệu cũ đã tới những replica mới.

### 13.1. Checklist dành cho lệnh có phạm vi nhiều DC

| Câu hỏi | Bằng chứng |
| --- | --- |
| RF của keyspace ở mỗi DC là bao nhiêu? | `system_schema.keyspaces`, snitch/DC/rack metadata. |
| Topology có đang bootstrap, move, decommission hoặc replace không? | `nodetool status`, ring, streaming logs. |
| Công cụ chạy trên node/địa chỉ nào? | Action log, node identity, JMX endpoint, cluster ID. |
| Những replica/DC nào tham gia tác vụ? | Tham số command, log session, token ownership và options phiên bản. |
| Có ảnh hưởng yêu cầu read/write CL không? | Monitoring `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM` theo traffic thật. |
| Dữ liệu/tombstone đã hội tụ đủ chưa? | Repair/streaming verification, replica health và canary query phù hợp. |

Đặc biệt với thao tác **thêm/loại node**, tránh chạy đồng thời bảo trì trên nhiều replica khiến quorum không thể đạt. Với RF = 2 trong một DC, `LOCAL_QUORUM` cần **hai trong hai** replica; một replica mất khả dụng có thể làm các request ở CL đó thất bại.

## 14. Sự cố giả lập: ticket ghi “snapshot thành công” nhưng backup không phục hồi

### 14.1. Timeline

| Thời điểm UTC | Sự kiện | Lỗ hổng quy trình |
| --- | --- | --- |
| 10:00 | Một engineer dùng SSH chung để vào N1. | Không có **attribution** theo cá nhân. |
| 10:05 | Chạy `nodetool snapshot -t backup-01 telemetry_ops`. | Không gắn change ID; không ghi scope nodes/DC. |
| 10:07 | `listsnapshots` cho thấy tag trên N1. | Mới xác minh **snapshot cục bộ**. |
| 10:10 | Đóng ticket với trạng thái `BACKUP_COMPLETE`. | Không kiểm chứng export, manifest hoặc restore. |
| Ngày sau | N1 mất toàn bộ disk; object storage không có snapshot. | Không thể dựa vào snapshot cùng volume để phục hồi. |

### 14.2. Các biện pháp phòng tránh

1. Dùng **danh tính cá nhân qua bastion/SSO**, hạn chế tài khoản SSH chung.
2. Yêu cầu **change ID, scope, approval**, command template chuẩn và timestamp UTC.
3. Tách các mốc `SNAPSHOT_CREATED`, `BACKUP_EXPORTED`, `BACKUP_VERIFIED`, `RESTORE_TESTED`.
4. Kiểm tra snapshot trên **mọi node cần thiết theo backup strategy**, không chỉ N1.
5. Xác minh manifest/checksum và lưu trữ độc lập; định kỳ thử restore trên môi trường cô lập.
6. Lưu audit event ngoài node và giới hạn quyền xóa backup.

**Bài học:** “Lệnh hoàn thành” là một sự kiện vận hành; “khả năng khôi phục được xác minh” là **một kết quả nghiệp vụ khác**, có bằng chứng khác.

## 15. Xử lý khi quyền, audit hoặc postcheck bị lỗi

| Hiện tượng | Giả thuyết | Cách tiếp cận |
| --- | --- | --- |
| Tài khoản chỉ đọc vẫn sửa được bảng | Quyền kế thừa cấp keyspace, superuser hoặc authorizer không bật. | Kiểm tra hiệu lực role bằng account thật, thu hồi quyền thừa qua change duyệt. |
| `cqlsh` bị Unauthorized nhưng `nodetool` vẫn thao tác được | CQL RBAC và JMX/OS có đường ủy quyền riêng. | Kiểm tra JMX security, bastion, OS và credential của công cụ. |
| Không thấy audit CQL cho `nodetool cleanup` | Thao tác JMX nằm ngoài phạm vi CQL audit. | Đối chiếu session recorder, automation logs và JMX/OS events. |
| Audit event có mật khẩu hoặc token trong args | Command được log nguyên văn, thiếu redaction. | Thu hồi/rotate secret, hạn chế quyền đọc và sửa pipeline audit. |
| `repair` mất SSH nhưng không có dòng finish | Mất kênh quan sát, trạng thái thực chưa rõ. | Gắn `UNKNOWN`, kiểm tra repair session/logs trước retry. |
| `snapshot` thành công nhưng `df` không giảm | Snapshot giữ hard links hoặc active SSTable; không liên quan “thành công” của backup. | Xem retention/inode/references và backup plan. |
| Postcheck `status` tốt nhưng read vẫn timeout | Membership chỉ là một lớp; có thể GC/disk/tombstone/network. | Đo client p99, `tpstats`, tracing mẫu, logs và replica latency. |
| Automation lặp một thay đổi sau timeout | Command không idempotent hoặc kết quả trước chưa xác minh. | Dừng, đối chiếu state, dùng action ID và precondition trước chạy lại. |
| Hai SRE chạy repair/compaction cùng lúc | Thiếu change lock và giới hạn concurrency. | Lập lịch/lock theo cluster/DC/node, kiểm soát quyền và audit. |
| Người duyệt cũng chính là người chạy phá hủy backup | Phân tách nhiệm vụ chưa phù hợp. | Áp nguyên tắc **separation of duties** cho hành động rủi ro cao. |

**Không phải mọi thao tác đều rollback được bằng một lệnh ngược.** `REVOKE` có thể khôi phục quyền, nhưng `DROP`/xóa dữ liệu sai có thể cần backup/restore, còn thay topology có bước streaming và repair riêng. Runbook cần phân biệt **rollback cấu hình** với **data recovery**.

## 16. Mẫu runbook kiểm soát thay đổi

~~~text
CHANGE ID:
Mục tiêu và lý do:
Cluster / DC / node / keyspace / table / token range:
Phiên bản Cassandra/JDK và công cụ:
Người đề xuất / người duyệt / người thực thi:
Vai trò và quyền được cấp tạm:
Maintenance window UTC:

PRECHECK
- [ ] Đã xác nhận identity và scope.
- [ ] Đã có approval và đánh giá rủi ro.
- [ ] `nodetool status` và replica placement phù hợp.
- [ ] Không có topology transition bất ngờ.
- [ ] RF/CL và impact tới người dùng đã được đánh giá.
- [ ] Disk/GC/compaction/streaming/repair backlog đủ an toàn.
- [ ] Backup/khôi phục và kế hoạch dừng/rollback đã sẵn sàng.
- [ ] Lưu baseline UTC, metrics và log references.

EXECUTION
- [ ] Sử dụng công cụ/command template đã cho phép.
- [ ] Chạy đúng node, đúng keyspace/table/args.
- [ ] Giới hạn concurrency và không trùng lệnh nặng.
- [ ] Lưu action ID, stdout/stderr đã che bí mật, session/exit.
- [ ] Nếu mất kết nối: đánh trạng thái UNKNOWN, không retry mù.

POSTCHECK
- [ ] Xác nhận tác vụ thật sự kết thúc.
- [ ] Kiểm tra hậu điều kiện riêng cho loại thao tác.
- [ ] Kiểm tra dữ liệu/canary CQL, replica health, RF/CL nếu liên quan.
- [ ] Kiểm tra p95/p99, timeout, disk headroom và lỗi hệ thống.
- [ ] Kiểm tra backup/export/restore nếu mục tiêu là bảo vệ dữ liệu.
- [ ] Ghi rõ VERIFIED / FAILED / PENDING cùng bằng chứng.

CLOSE
- [ ] Thu hồi quyền tạm, đóng phiên bảo trì/credential.
- [ ] Lưu audit event ngoài node, có retention và truy cập phù hợp.
- [ ] Người độc lập review kết quả nếu thay đổi rủi ro cao.
- [ ] Ghi follow-up và cập nhật runbook khi phát hiện thiếu sót.
~~~

Trong các tổ chức lớn, nên đưa mẫu này vào **automation có policy** thay vì phụ thuộc hoàn toàn vào trí nhớ người vận hành. Tuy nhiên, automation cũng cần được kiểm toán, kiểm thử tham số, kiểm soát secrets và có cơ chế dừng an toàn.

## 17. Các nhận định sai thường gặp

| Nhận định | Kết luận | Lý do |
| --- | --- | --- |
| “Cấp `SELECT` trong CQL là đã cấp quyền xem mọi lệnh `nodetool`.” | **Sai** | JMX/OS dùng cơ chế riêng. |
| “Chặn `DELETE` ở CQL là đủ để bảo vệ dữ liệu khỏi xóa thủ công.” | **Sai** | Root/file access và lệnh quản trị vẫn là đường tác động. |
| “Một SSH account dùng chung giúp dễ quản lý audit.” | **Sai** | Không quy trách nhiệm rõ từng cá nhân. |
| “Lệnh `snapshot` trả exit 0 nghĩa backup khôi phục được.” | **Sai** | Cần export, manifest và restore verification. |
| “`nodetool repair` trên một node chứng minh toàn cluster đã hội tụ.” | **Sai** | Scope/token ranges/participants/DC có thể khác mong đợi. |
| “CQL audit luôn ghi thao tác JMX.” | **Sai** | Hai kênh độc lập; cần session/automation/OS logs. |
| “Mất kết nối SSH giữa lệnh nghĩa thao tác chưa chạy.” | **Sai** | Lệnh có thể vẫn đang chạy hoặc đã tác động một phần. |
| “Ghi toàn bộ command kể cả mật khẩu giúp audit chính xác hơn.” | **Sai** | Audit không được biến thành rò rỉ secret. |
| “Một SELECT thành công đủ chứng minh các replica giống nhau.” | **Sai** | CL chỉ yêu cầu số phản hồi nhất định, không bảo đảm mọi replica đã hội tụ. |
| “Tạm cấp quyền có thời hạn, hậu kiểm độc lập và thu hồi sau thực thi là hợp lý.” | **Đúng** | Giảm blast radius, tăng khả năng truy vết và an toàn. |

## 18. Bài tập có đáp án

**Bài 1.** Role `analytics_viewer` chỉ có `SELECT` trên bảng CQL. Người dùng đó lại SSH được vào node với quyền root. Có thể khẳng định dữ liệu đã được bảo vệ khỏi xóa bởi người dùng đó?

**Đáp án:** **Không.** CQL RBAC không giới hạn root/OS. Cần kiểm soát mọi đường file/JMX/SSH/container, tách quyền và ghi audit.

**Bài 2.** Một lệnh `nodetool snapshot -t backup-01 ks` trả exit 0 và tag có trong `listsnapshots` trên N1. Có thể ghi `BACKUP_COMPLETE` cho toàn cluster không?

**Đáp án:** **Không.** Mới có bằng chứng local snapshot trên N1. Cần xác nhận phạm vi node/DC, export sang lưu trữ độc lập, manifest và kiểm tra restore theo backup policy.

**Bài 3.** CQL audit log không có sự kiện `nodetool cleanup` dù automation ghi rằng đã chạy. Điều này có chứng minh automation nói dối không?

**Đáp án:** **Không.** `cleanup` thường qua JMX; CQL audit không mặc nhiên ghi JMX. Cần kiểm tra bastion/session recorder, automation log và trạng thái node.

**Bài 4.** Sau khi chạy `nodetool repair`, pipeline bị mất kết nối trước khi nhận kết quả. Trạng thái phù hợp là `FAILED`, `VERIFIED` hay `UNKNOWN`?

**Đáp án:** **`UNKNOWN`** cho tới khi có bằng chứng kết thúc và hậu kiểm. Không tự retry khi chưa biết phiên repair có tiếp tục hay đã đồng bộ một phần.

**Bài 5.** Tại sao không log raw command có `--password my-secret` trong hệ thống audit?

**Đáp án:** Process list/shell history/audit storage có thể lộ secret cho nhiều người. Cần redaction, secret manager/identity thích hợp và thu hồi secret nếu đã rò rỉ.

**Bài 6.** RF = 2 tại `dc2`, ứng dụng đọc `LOCAL_QUORUM`. SRE muốn restart một replica bất kỳ của partition khi replica còn lại đang down. Điều kiện an toàn có đạt không?

**Đáp án:** **Không.** Quorum ở dc2 với RF = 2 cần cả hai replica. Nếu một replica đã down, restart replica còn lại có thể khiến request ở CL này hoàn toàn không khả dụng. Cần xử lý health và kế hoạch maintenance trước.

**Bài 7.** Một CQL role viewer có `GRANT SELECT ON TABLE ks.tbl`; phép `DELETE` vẫn thành công khi đăng nhập bằng một account được gán role ấy. Cần điều tra gì?

**Đáp án:** Quyền hiệu lực của account có thể đến từ **role khác**, `MODIFY` ở cấp keyspace, superuser hoặc authorizer không hoạt động như dự kiến. Kiểm tra role membership, effective permissions và thử nghiệm đúng identity.

**Bài 8.** Một `ALTER KEYSPACE` đổi RF của DC mới trả success. Có thể xóa ngay dữ liệu cũ trên node trước đó không?

**Đáp án:** **Không.** CQL đổi metadata không chứng minh đã streaming/rebuild/repair đủ replica mới. Cần postcheck topology, ownership, dữ liệu và backup trước khi cân nhắc cleanup.

**Bài 9.** Một thao tác `flush` hoàn tất nhưng disk gần đầy hơn. Có mâu thuẫn không?

**Đáp án:** **Không.** Flush tạo SSTable mới và có thể làm compaction cần thêm disk tạm. Thành công kỹ thuật của lệnh không bảo đảm trạng thái tài nguyên tốt hơn; phải theo dõi headroom.

**Bài 10.** Cần thiết kế hai loại trạng thái nào trong automation để tránh nhầm “lệnh hoàn tất” với “hệ thống đúng”?

**Đáp án:** Tách **tool execution outcome** (`exit 0`, failed, unknown) và **postcondition verification** (`verified`, failed, pending/inconclusive). Chỉ đóng change khi đã có bằng chứng hậu điều kiện phù hợp.

## 19. Tổng kết bằng sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Có yêu cầu dùng công cụ Cassandra"] --> B{"Đã xác định identity và least privilege?"}
    B -->|Không| C["Cấp đúng role CQL/JMX/OS và hạn dùng"]
    B -->|Có| D["Đánh giá change: scope, approval, recovery"]
    C --> D
    D --> E{"Precheck topology/replica/disk/backup đạt?"}
    E -->|Không| F["Dừng: khắc phục điều kiện thiếu"]
    E -->|Có| G["Thực thi lệnh hẹp qua kênh được audit"]
    G --> H["Lưu actor + UTC + args redacted + result + action ID"]
    H --> I{"Postconditions đã được xác minh?"}
    I -->|Có| J["Thu hồi quyền tạm, lưu evidence, đóng change"]
    I -->|Chưa rõ/không| K["Giữ change mở: điều tra, replan hoặc restore"]
~~~

**Ghi nhớ:** vận hành Cassandra an toàn không chỉ là biết cú pháp `nodetool` hoặc `cqlsh`. Quyền truy cập phải được kiểm soát **theo kênh CQL, JMX, OS và automation**; mỗi hành động cần **danh tính, lý do, phạm vi, timestamp UTC và nhật ký không lộ bí mật**; sau đó phải xác minh **hậu điều kiện dữ liệu, replica, topology, tài nguyên và khả năng khôi phục**. Một lệnh thành công là điểm bắt đầu của bước hậu kiểm, **không phải bằng chứng cuối cùng rằng cluster đã an toàn**.
