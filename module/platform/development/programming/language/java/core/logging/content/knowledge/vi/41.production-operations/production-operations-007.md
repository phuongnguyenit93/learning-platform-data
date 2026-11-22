# Phân quyền production log: bảo vệ dữ liệu và hỗ trợ vận hành Java

## 1. Khái niệm và mục tiêu

**Phân quyền production log** là việc xác định và cưỡng chế **ai có thể đọc, tìm kiếm, ghi, xuất, xóa, quản trị hoặc chia sẻ những log nào trong môi trường production**, vào thời điểm nào và với lý do gì. Đó không chỉ là quyền xem một dashboard: application logs có thể đi từ Java logger qua stdout/file, container runtime, collector, backend, snapshot, archive, alert và file export.

Log production thường chứa metadata về giao dịch, request ID, trace ID, user ID, địa chỉ IP, stack trace, tên dịch vụ, chi tiết triển khai và lịch sử truy cập. Một lỗi logging còn có thể đưa mật khẩu, token hoặc dữ liệu cá nhân vào những nơi này. Vì vậy người có quyền xem logs đôi khi có thể suy ra hoạt động khách hàng, cấu trúc nội bộ hoặc nhìn thấy credential bị lộ.

**Mục tiêu kép** của hệ thống quyền là: người trực vận hành vẫn tìm được bằng chứng để xử lý sự cố, **nhưng chỉ truy cập đúng lượng dữ liệu cần thiết**. Các nguyên tắc nền tảng:

- **Least privilege:** chỉ cấp action, dataset, environment và thời hạn cần dùng.
- **Deny by default:** quyền chưa được cấp thì không được thực hiện.
- **Need to know:** quyền gắn với mục đích điều tra, trách nhiệm công việc hoặc yêu cầu hợp lệ.
- **Separation of duties:** quyền ingest, read, export, delete, configure, manage access và audit không gộp tùy tiện.
- **Strong authentication:** xác thực danh tính trước khi xét quyền; MFA/JIT khi rủi ro đòi hỏi.
- **Auditability:** truy vết được ai xem, xuất, xóa, chia sẻ hoặc cấp quyền.
- **Defense in depth:** kiểm soát tại nguồn tạo log, backend truy vấn, runtime/node, nơi lưu phụ và các đường export.

Sau bài này, bạn sẽ phân biệt RBAC/ABAC, thiết kế ma trận quyền, hiểu Kubernetes `pods/log`, thử một ví dụ Java 17 chạy độc lập, kiểm tra quyền từ backend tới archive và xây dựng quy trình truy cập khẩn cấp có kiểm toán.

## 2. Ranh giới dữ liệu: log đi qua những nơi nào?

```text
Java code / SLF4J / Logback / Log4j 2 / JUL
                    |
              Console / File
                    |
           Docker / Kubernetes
                    |
            Collector / Agent
                    |
          Log ingestion endpoint
                    |
        +-----------+-----------+
        |                       |
  Standard log index      Restricted/audit index
        |                       |
        +---- Search API -------+
        |          |            |
    Dashboard    Export      Alert/incident
        |          |            |
        +----------+------------+
                    |
           Archive / backup / snapshot
```

**Mỗi chặng có một hệ quyền riêng:**

1. Ứng dụng: ai được thay log level, enable debug payload, đổi appender hoặc thêm field?
2. Container/node: ai có `docker logs`, `kubectl logs`, quyền đọc file node, `pods/exec` hoặc quyền sửa workload?
3. Collector: danh tính nào được gửi tới dataset/index nào, có được search/export hay không?
4. Backend: authn, quyền query theo tenant/service, lọc document/field và chia sẻ dashboard.
5. Storage: quyền bucket/object, snapshot, backup, khóa giải mã và download.
6. Alert/ticket/chat: các notification có trích nội dung raw log không, ai là người nhận?
7. Administration: ai cấp quyền, xóa dữ liệu, thay retention và xem audit về chính mình?

Ẩn nút “View logs” trong UI **không bảo vệ** khỏi người có Search API token, người có quyền đọc log files trên node hoặc người được phép tải snapshot từ object storage. Chính sách phải áp dụng **theo đường dữ liệu thực tế**, không chỉ một ứng dụng giao diện.

## 3. Phân loại log trước khi cấp quyền

Một mô hình minh họa:

| Classification | Nội dung | Người đọc tham khảo |
| --- | --- | --- |
| `STANDARD` | Event code, route template, status, duration, service, request ID đã kiểm tra | On-call của service theo scope |
| `INTERNAL` | Stack trace đã kiểm soát, dependency alias, internal IDs | Nhóm kỹ thuật thực sự cần chẩn đoán |
| `RESTRICTED` | Audit hoạt động quản trị, hồ sơ điều tra, định danh khách hàng cần lưu theo policy | Nhóm được phê duyệt, quyền hẹp |
| `HIGHLY_RESTRICTED` | Dữ liệu phục vụ sự cố nghiêm trọng hoặc yêu cầu có hạn chế đặc biệt | Quy trình phê duyệt và lưu giữ riêng |

Đây chỉ là **ví dụ**; chính sách của tổ chức quyết định tên và tiêu chí. Không phân loại theo log level một cách máy móc: một dòng `INFO` ghi ai đã xem hồ sơ riêng tư có thể nhạy cảm hơn `ERROR` chỉ chứa tên class và mã lỗi.

**Không tạo “kho raw credential logs” như thực hành bình thường.** Password, access token, refresh token, API key, private key, session cookie và request body chứa bí mật nên bị loại khỏi event trước khi vào logger. RBAC, encryption, retention và masking sau cùng không thể biến việc ghi secret thành an toàn.

Một user ID hoặc IP đã hash vẫn có thể được liên kết giữa các events; việc ẩn vài ký tự không mặc nhiên chuyển dữ liệu thành `STANDARD`.

## 4. Phân quyền theo hành động, không chỉ READ/ADMIN

| Permission khái niệm | Cho phép | Không mặc nhiên cấp |
| --- | --- | --- |
| `LOG_INGEST` | Đẩy log vào đúng index/tenant | Query, export, delete |
| `LOG_READ_STANDARD` | Truy vấn log mức standard trong scope | Restricted data |
| `LOG_READ_RESTRICTED` | Truy vấn tập restricted được duyệt | Bulk export hoặc admin |
| `LOG_EXPORT_STANDARD` | Xuất standard logs theo giới hạn | Export restricted |
| `LOG_EXPORT_RESTRICTED` | Xuất restricted theo policy riêng | Xóa hoặc thay retention |
| `LOG_MANAGE_PIPELINE` | Thay parser, collector, destination theo quy trình | Đọc raw log mặc định |
| `LOG_MANAGE_RETENTION` | Quản trị lifecycle/retention được phê duyệt | Xóa vô điều kiện |
| `LOG_DELETE` | Delete/quarantine khi có authorization và bằng chứng | Xóa audit truy cập của chính mình |
| `LOG_MANAGE_ACCESS` | Cấp/thu hồi grants có scope | Tự động đọc mọi dữ liệu |
| `LOG_AUDIT_READ` | Xem access audit | Sửa/xóa audit events |

Đây là tên do bài học định nghĩa, **không phải tên permissions có sẵn** của mọi log backend.

Sự khác nhau quan trọng:
- **READ khác EXPORT**: tìm vài log events qua dashboard có rủi ro khác với tạo file ZIP/CSV chứa toàn bộ lịch sử.
- **INGEST khác READ**: collector cần ghi dữ liệu, không cần tải các events cũ.
- **CONFIGURE khác DATA ACCESS**: người chỉnh pipeline không tự động là người được xem dữ liệu restricted.
- **DELETE khác MANAGE RETENTION**: giữ dữ liệu theo chính sách khác việc xóa thủ công một tập records.
- **AUDIT READ khác APPLICATION LOG READ**: audit về việc ai xem log thường cần được bảo vệ riêng.

**Cảnh báo về quyền gián tiếp:** Một admin có thể đổi collector destination, tạo API token hoặc sửa policy để lấy raw logs. Chỉ tách role trên giấy không ngăn được hành động đó nếu thiếu change approval, immutable audit hoặc kiểm soát privilege escalation.

### 4.1. Ma trận role mẫu

| Vai trò | Read | Ingest | Export | Admin |
| --- | --- | --- | --- | --- |
| Application developer | Staging và production logs đã lọc thuộc service cần hỗ trợ, theo policy | Không | Không mặc định | Không |
| Production on-call | `STANDARD/INTERNAL` của team và environment phụ trách | Không | Cần quyền riêng | Không |
| Security analyst | Audit/restricted datasets theo phê duyệt | Không | Có kiểm toán/phê duyệt | Không mặc định |
| Collector service identity | Không | Chỉ đúng destination | Không | Không |
| Pipeline operator | Có thể chỉ metadata về pipeline | Qua service identity nếu cần | Không | Chỉnh cấu hình có review |
| Retention administrator | Không mặc định | Không | Không mặc định | Retention có phạm vi |
| Break-glass responder | Dataset/incident/time window cụ thể | Không mặc định | Theo phê duyệt riêng | Chỉ quyền xử lý sự cố |

Một on-call xử lý `orders-api` thường không cần thấy payment audit logs của nhóm khác. Tổ chức có thể có nhiều role hơn hoặc ít hơn; điều cần bảo đảm là **effective permissions có thể kiểm chứng**.

## 5. RBAC và ABAC

### 5.1. RBAC: role gắn với permissions

**Role-Based Access Control** gắn quyền cho nhóm/vai trò, sau đó xác thực user/service account và đánh giá membership:

```text
identity: alice
groups:   orders-oncall
role:     prod-orders-log-reader
grant:    LOG_READ_STANDARD
scope:    environment=prod AND service=orders
```

Ưu điểm: dễ quản lý theo nhóm, dễ review grants. Rủi ro: role creep, nhân sự chuyển team vẫn giữ quyền cũ, một role `ALL_PROD_VIEWER` cấp quá rộng, role name nghe có vẻ hẹp nhưng thực tế được gộp nhiều quyền.

Role cần được xem cùng **tài nguyên**: `READ_STANDARD` toàn cluster vẫn rộng hơn `READ_STANDARD` trong một service và khung thời gian cụ thể.

### 5.2. ABAC: attribute của người, tài nguyên và hoàn cảnh

**Attribute-Based Access Control** có thể xét:
- Subject: team, employment status, MFA, managed device, on-call rotation, approved incident.
- Resource: environment, service, tenant, classification, region, dataset owner.
- Action: read, ingest, export, delete, manage access.
- Context: purpose, requested time window, temporary elevation, source identity.

Một policy khái niệm:

```text
ALLOW READ
  IF subject.active
 AND subject.team == resource.owner_team
 AND subject.permissions CONTAINS "LOG_READ_STANDARD"
 AND resource.environment == "prod"
 AND resource.classification == "STANDARD"
 AND context.authentication_strength >= required_strength

DENY OTHERWISE
```

Đây là **pseudocode**, không phải cú pháp cụ thể của IAM, OPA hay backend logging. Với RESTRICTED, policy có thể cần incident reference, phê duyệt và TTL; không sửa rule trên bằng `OR true` để xử lý nhanh một sự cố.

### 5.3. Enforcement phải nằm ở trusted boundary

Một API chỉ gắn `service=orders` vào truy vấn ở browser là không đủ. Người dùng có thể sửa request bằng Developer Tools, gọi backend trực tiếp, thay index alias, wildcard hoặc export endpoint.

Cần:
1. Xác thực subject/session/token tại backend hoặc trusted gateway.
2. Kiểm tra action và dataset/tenant scope **trước mỗi query/export**.
3. Thực thi row/document/field restrictions tại tầng không thể bị client bỏ qua.
4. Giới hạn time range, records, bytes, rate, concurrency khi phù hợp.
5. Audit decision/outcome, kể cả DENY, mà không chép raw log data vào audit.
6. Kiểm tra saved queries, share links, raw document API, download endpoint và service-to-service queries có đi cùng policy không.

Nếu sản phẩm không cung cấp field-level security đáng tin, có thể **tách restricted log sang index/tenant riêng** rồi dùng ACL phù hợp thay vì tuyên bố client-side masking là đủ.

## 6. Ví dụ Java 17: mô phỏng quyền đọc và xuất log

Chương trình dưới đây **chạy độc lập trên JDK 17**, dùng `java.util.logging` (JUL), mô phỏng cấp quyền trong một process. Nó cố ý không có backend thật: chỉ minh họa cách **READ khác EXPORT**, **INGEST không ngầm là READ**, và **CONFIGURE không ngầm là người được xem raw log**.

Các identity và record ID đều là dữ liệu giả do mã tạo. Trong ứng dụng thật, principal phải được tạo từ kết quả xác thực tin cậy, classification phải đến từ catalog/storage được kiểm soát, và policy phải được enforce ở mọi đường truy vấn.

Tạo file `ProductionLogAccessDemo.java`:

```java
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ProductionLogAccessDemo {
    private enum Classification { STANDARD, RESTRICTED }
    private enum Action { READ, EXPORT }
    private enum Permission {
        READ_STANDARD, READ_RESTRICTED,
        EXPORT_STANDARD, EXPORT_RESTRICTED,
        INGEST, CONFIGURE
    }

    private record Principal(
            String id, Set<Permission> grants) {}

    private record LogEntry(
            String id, Classification classification) {}

    private static boolean permitted(
            Principal principal, LogEntry entry, Action action) {
        Permission read =
                entry.classification() == Classification.RESTRICTED
                ? Permission.READ_RESTRICTED
                : Permission.READ_STANDARD;

        if (!principal.grants().contains(read)) {
            return false;
        }

        if (action == Action.READ) {
            return true;
        }

        Permission export =
                entry.classification() == Classification.RESTRICTED
                ? Permission.EXPORT_RESTRICTED
                : Permission.EXPORT_STANDARD;

        // Export cần CẢ quyền read và quyền export.
        return principal.grants().contains(export);
    }

    private static void check(
            Logger audit, Principal principal,
            LogEntry entry, Action action) {
        boolean allowed = permitted(principal, entry, action);
        audit.info("actor=" + principal.id()
                + " action=" + action
                + " record=" + entry.id()
                + " class=" + entry.classification()
                + " decision=" + (allowed ? "ALLOW" : "DENY"));

        // Chỉ in quyết định; không in nội dung raw log.
        System.out.println("RESULT actor=" + principal.id()
                + " action=" + action
                + " status=" + (allowed ? "ALLOWED" : "DENIED"));
    }

    public static void main(String[] args) {
        Logger audit = Logger.getLogger("lesson.production.log.access");
        audit.setLevel(Level.INFO);
        audit.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println("AUDIT " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        audit.addHandler(output);

        try {
            LogEntry standard = new LogEntry(
                    "evt-1", Classification.STANDARD);
            LogEntry restricted = new LogEntry(
                    "evt-2", Classification.RESTRICTED);

            Principal oncall = new Principal(
                    "oncall", Set.of(Permission.READ_STANDARD));
            Principal auditor = new Principal(
                    "security-auditor",
                    Set.of(Permission.READ_STANDARD,
                            Permission.READ_RESTRICTED));
            Principal collector = new Principal(
                    "collector", Set.of(Permission.INGEST));
            Principal configAdmin = new Principal(
                    "config-admin", Set.of(Permission.CONFIGURE));

            check(audit, oncall, standard, Action.READ);
            check(audit, oncall, restricted, Action.READ);
            check(audit, auditor, restricted, Action.READ);
            check(audit, auditor, restricted, Action.EXPORT);
            check(audit, collector, standard, Action.READ);
            check(audit, configAdmin, restricted, Action.READ);
        } finally {
            audit.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ProductionLogAccessDemo.java
java ProductionLogAccessDemo
```

**Stdout chính xác** trong JVM mới không có thành phần khác can thiệp vào logger:

```text
AUDIT actor=oncall action=READ record=evt-1 class=STANDARD decision=ALLOW
RESULT actor=oncall action=READ status=ALLOWED
AUDIT actor=oncall action=READ record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=oncall action=READ status=DENIED
AUDIT actor=security-auditor action=READ record=evt-2 class=RESTRICTED decision=ALLOW
RESULT actor=security-auditor action=READ status=ALLOWED
AUDIT actor=security-auditor action=EXPORT record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=security-auditor action=EXPORT status=DENIED
AUDIT actor=collector action=READ record=evt-1 class=STANDARD decision=DENY
RESULT actor=collector action=READ status=DENIED
AUDIT actor=config-admin action=READ record=evt-2 class=RESTRICTED decision=DENY
RESULT actor=config-admin action=READ status=DENIED
```

**Giải thích:** on-call đọc được standard nhưng không đọc restricted; security auditor đọc restricted song không có `EXPORT_RESTRICTED` nên không được xuất; collector có `INGEST` không có quyền READ; config admin có `CONFIGURE` không tự trở thành data reader.

Handler JUL tự in `AUDIT` qua stdout, còn `setUseParentHandlers(false)` tránh root ConsoleHandler ghi thêm bản khác. Những event này không chứa raw log body. Trong production, access audit nên có timestamp, verified actor, source, resource scope, incident ID và lưu ở sink được bảo vệ.

**Giới hạn cố ý:** Chương trình chỉ là mô hình trong RAM, không xác thực danh tính, không có tenant/service/time/approval, không có expiry, không lưu audit bền vững, không quản lý session hoặc authorization caching. Đặc biệt, `LOG_INGEST` ở demo là tên quyền chưa được implement cho action INGEST; nó chỉ chứng minh quyền đó **không cấp READ**. Không dùng mã này như một IAM/authorization solution hoàn chỉnh.

## 7. Kubernetes RBAC: quyền `pods/log`

Ở Kubernetes, `kubectl logs` thường truy cập Kubernetes API subresource **`pods/log`**. Quyền `get` trên subresource này là một phần quan trọng của quyền xem logs trong một namespace. Quyền này **khác** quyền truy vấn hệ thống log tập trung.

Ví dụ YAML **chỉ minh họa** một namespace Role và RoleBinding:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: application-log-reader
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: application-log-readers
  namespace: production
subjects:
  - kind: Group
    name: production-oncall-log-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: application-log-reader
  apiGroup: rbac.authorization.k8s.io
```

Ý nghĩa và giới hạn:
- `Role` có hiệu lực trong namespace `production`, không tự tạo quyền cluster-wide.
- `RoleBinding` gắn role với group; việc người dùng thật thuộc group đó **phụ thuộc IdP/authentication setup**.
- `get pods/log` trong ví dụ có thể xem logs của **mọi Pod trong namespace**, không phân biệt team hay classification. Nếu namespace trộn ứng dụng nhạy cảm và ít nhạy cảm, cần cấu trúc namespace/ACL khác hoặc backend log có service-scoped authorization.
- Grant này không cho `pods/exec` hay `secrets/get`, nhưng một user có những quyền mạnh khác **có thể tìm đường tiếp cận dữ liệu khác**, dù bị chặn `pods/log`.
- Đọc logs qua Kubernetes API không cấp quyền đọc index/snapshot của hệ thống log tập trung; ngược lại, quyền backend viewer cũng không tự cấp quyền `kubectl logs`.
- Kubernetes logs chịu giới hạn rotation, pod restart và lưu trữ node; RBAC không biến `kubectl logs` thành archive.

Có thể kiểm tra quyền của context đang dùng:

```bash
kubectl auth can-i get pods/log -n production
kubectl auth can-i list pods -n production
kubectl logs pod/orders-api-abc -n production -c app --tail=50
```

Tên Pod/container là giả. `kubectl auth can-i` xác nhận một authorization question tại thời điểm gọi; nó **không chứng minh toàn bộ đường truy cập logs đã an toàn**.

### 7.1. Kiểm tra các quyền hạ tầng gián tiếp

Đừng chỉ xem `pods/log`:
- `pods/exec` có thể cho phép chạy lệnh trong container.
- Quyền sửa Pod/Deployment hoặc tạo privileged workload có thể dẫn đến truy cập file/volume/credentials.
- Node access, hostPath, SSH, kubelet/node filesystem có thể cho xem container log files.
- Quyền lấy Secret, cloud workload identity hoặc token của collector có thể mở đường vào backend.
- Quyền thay collector config có thể redirect log sang một destination khác.
- Quyền sửa audit policy/retention hoặc xóa logs có thể che dấu hành vi.

Kubernetes API audit (nếu được bật/cấu hình) có thể ghi thao tác gọi `pods/log`; central log backend lại cần audit riêng về search/export/delete ở chính backend đó.

## 8. Central logging: quyền trong search, API, index và dashboard

Hệ thống log tập trung thường có:
- **Authentication:** SSO/OIDC/SAML/LDAP hoặc hệ thống tương đương, MFA và session policy.
- **Authorization:** role/index/dataset/tenant permissions, trong một số sản phẩm có document-/field-level controls.
- **Ingest API:** token service dùng để ghi dữ liệu.
- **Search API:** truy vấn logs bằng identity của caller.
- **Export/snapshot:** tạo file, object hoặc bản sao dữ liệu.
- **Administration:** đổi retention, parser, role, alert/routing và policy.
- **Access audit:** ghi ai tìm kiếm, xuất, sửa quyền hoặc xóa dữ liệu.

Không phải mọi sản phẩm có cùng capability hoặc cùng tên quyền. Ví dụ `viewer` ở hai nền tảng khác nhau có thể khác nhau về raw API, exports và saved queries. **Phải xác nhận quyền thực tế và phiên bản đang chạy**.

### 8.1. Đường bypass thường bị quên

Một policy đúng không chỉ chặn trên dashboard. Kiểm tra:
- Direct API request thay vì UI.
- Truy vấn wildcard index/tenant hoặc alias.
- Raw document endpoint truy xuất theo ID.
- Saved query, dashboard panel hoặc alert chạy bằng quyền owner/service account.
- Shared URL, embed, snapshot và export job.
- API token được phát trước khi đổi role.
- Batch query, aggregation, suggestions/autocomplete, preview fields.
- Export sang object storage rồi đọc trực tiếp qua cloud IAM.
- Cache còn dữ liệu cũ sau khi revoke.

Nếu field-level redaction chỉ diễn ra trong UI, dữ liệu raw có thể vẫn có ở API/export. Phân quyền **phải cưỡng chế ở backend hoặc trusted gateway**, và khi không thể bảo đảm field-level enforcement thì tách restricted data ra dataset/index có ACL riêng.

### 8.2. Collector không nên có quyền viewer

Collector nên có identity riêng và `write-only` đến đúng destination. Không cấp một admin token cho cả collector và dashboard chỉ để đơn giản hóa cấu hình. Cần:
- Scope theo dataset, namespace, service/tenant khi hỗ trợ.
- Secret store/workload identity, rotation, hạn dùng và theo dõi sử dụng.
- Không hardcode key trong repository, container image hoặc command line được log.
- Quota/rate limit chống spam ingest.
- Xác thực nguồn để một collector không giả mạo audit event của tenant khác.
- Không cấp read, export, delete, role-admin nếu không có yêu cầu riêng rõ ràng.

Ngay cả quyền ingest-only vẫn có rủi ro **data poisoning** (ghi giả log) và gây tăng phí ingest; least privilege chỉ giảm phạm vi thiệt hại.

## 9. Read và export: quản trị bản sao dữ liệu

**Được search một nhóm log không đồng nghĩa được download hàng triệu records**. Khi export:
- Dữ liệu rời khỏi cơ chế query/retention của backend.
- CSV/ZIP có thể lưu trên máy cá nhân, gửi email hoặc đính kèm ticket.
- Shared link hoặc signed URL có thể dùng được sau khi người tạo đổi role.
- Bản xuất có thể chứa fields đã bị ẩn ở UI nếu export pipeline khác.
- Snapshot/backup có thể bị đọc qua storage IAM độc lập.

Một workflow export restricted nên có permission riêng, scope/time range, lý do, approval khi chính sách yêu cầu, limit về records/bytes, nơi lưu được kiểm soát, TTL/retention của bản xuất và **audit thực tế** (ai, lúc nào, dữ liệu nào, trạng thái thành công/thất bại).

Tách hai event:
- `EXPORT_AUTHORIZED`: hệ thống đã cho phép thao tác.
- `EXPORT_COMPLETED`: export thành công, có dữ liệu và đích nhận theo contract.

Không ghi `EXPORT_COMPLETED` thành công chỉ vì permission check trả ALLOW; storage/network có thể lỗi.

### 9.1. Archive, backup và quyền decrypt

Dữ liệu log đã được chuyển tới object storage, snapshot hoặc backup vẫn cần IAM/ACL riêng. Quyền đọc object + quyền giải mã bằng key liên quan có thể tạo ra một đường đọc khác với UI. Một admin backup có thể sao chép toàn bộ dữ liệu dù không được cấp backend `LOG_READ_RESTRICTED`.

Cần review:
- Ai có quyền list/get/export archive objects?
- Ai có quyền decrypt khóa?
- Có thể copy snapshot sang account/region khác không?
- Retention và legal hold áp dụng thế nào?
- Khi người dùng bị revoke, các bản xuất/signed URLs còn tồn tại và sử dụng được không?

Đừng cho rằng xóa một log index là đã xóa mọi bản sao hoặc việc thu hồi role xóa được các file ZIP đã tải.

## 10. Phân quyền theo time, team, tenant và incident

Một scope có ích thường là tổ hợp:

```text
subject  = team:orders-oncall
action   = READ
dataset  = prod-application-logs
service  = orders-api
tier     = STANDARD
window   = incident-related, bounded
purpose  = production-incident-investigation
```

Nếu nhiều tenants dùng chung một backend, tenant ID cần được **gắn từ nguồn metadata tin cậy** và enforced server-side. Không tin một query parameter hay log field do client tự khai để quyết định tenant scope.

**Không để request ID làm quyền truy cập.** Một request ID hữu ích cho tìm kiếm nhưng không phải credential hoặc bằng chứng quyền. Khi cần giới hạn một incident, kết hợp identity, grant và dataset scope; ID chỉ là bộ lọc phụ.

Quyền tạm thời/JIT (just in time) giúp giảm role tồn tại quá lâu. Khi hết hạn, cần xem session, token cache, saved dashboards và export đã tạo; một policy hết hạn trên giấy chưa chắc vô hiệu hóa ngay các token cũ.

## 11. Break-glass: truy cập khẩn cấp mà vẫn kiểm toán

**Break-glass** nghĩa là một đường nâng quyền cho tình huống nghiêm trọng, có kiểm soát, không phải shared root password.

Một quy trình tham khảo:
1. Người trực nêu incident ID, lý do cần restricted log, service/dataset và time window.
2. Xác thực mạnh; phê duyệt theo mức rủi ro. Khi yêu cầu ứng cứu cực khẩn, policy có thể cho nâng quyền trước nhưng **bắt buộc báo động/hậu kiểm**.
3. Cấp quyền **đúng action** (thường là READ) và đúng scope; không mặc định cho EXPORT/DELETE.
4. Grant có expiry (thời hạn do chính sách quy định), không giữ quyền vĩnh viễn.
5. Access audit ghi actor, scope, incident, approver, grant change và mọi query/export liên quan.
6. Tự động thu hồi; kiểm tra session/token/link còn dùng được hay không.
7. Review sau sự cố: quyền có bị dùng quá phạm vi, có lộ dữ liệu, có thể giảm nhu cầu truy cập restricted logs bằng schema tốt hơn không?

Không copy raw secret trong ticket, Slack/email hoặc ảnh chụp màn hình không được kiểm soát chỉ vì đang xử lý outage.

**Tách nhiệm vụ:** người cấp quyền, người quản trị retention/delete và người xem audit không nên tự do xóa/chỉnh bằng chứng của chính mình. Một hệ thống có thể dùng policy-as-code, approval cho thay đổi nguy hiểm, audit store riêng và alert khi grant thay đổi bất thường.

## 12. Access audit: kiểm toán việc truy cập log

**Audit of log access** khác **application log**. Mục tiêu là trả lời **ai đã thử xem, xem thành công, export, chia sẻ, xóa hoặc thay quyền**, và kết quả ra sao.

Ví dụ event JSON giả lập:

```json
{
  "event": "production_log_access",
  "occurred_at": "2026-11-10T04:00:00Z",
  "actor_id": "staff-123",
  "action": "EXPORT_REQUESTED",
  "dataset": "orders-prod-restricted",
  "decision": "DENY",
  "incident_id": "inc-42",
  "auth_method": "SSO_MFA",
  "request_id": "req-911"
}
```

Đây là **dữ liệu ví dụ**. Một access audit thực tế có thể thêm:
- Verified identity và loại principal (USER/SERVICE).
- Source/network info phù hợp chính sách.
- Resource scope, classification, time range.
- Approval/elevation ID và lý do.
- Decision và **outcome sau thao tác** (success/error/cancel).
- Số bản ghi/bytes export khi đo được thực.
- Thời gian UTC, event ID, correlation ID.
- Policy version hoặc rule ID hỗ trợ điều tra.

**Không ghi raw query chứa PII, raw log body, bearer token hoặc API key vào access audit**. Query template, phạm vi, request ID hoặc reference an toàn thường đủ; nếu dùng hash/fingerprint, đánh giá khả năng suy đoán nội dung.

Audit nên được bảo vệ chống sửa/xóa bởi người bị kiểm toán, có quyền đọc riêng và retention theo policy. Một dòng `logger.info` gửi vào chính backend do admin có thể xóa **không bảo đảm audit bất biến hay bền vững**; sự kiện quan trọng có thể cần protected append-only storage, policy engine logs, outbox hoặc giải pháp được quản lý phù hợp.

### 12.1. Security alert về quyền đọc log

Theo dõi những tín hiệu:
- Tạo API token mới với scope rộng hoặc privileged role grant.
- Đọc restricted logs không liên quan incident/purpose.
- Bulk export tăng bất thường.
- Nhiều lần DENY hoặc tìm kiếm wildcard datasets.
- Đọc logs từ thiết bị/vùng truy cập không được phép theo policy.
- Sửa masking pipeline, retention hoặc audit policy.
- Credential của collector bất ngờ gọi Search API.
- Truy cập qua break-glass không được hậu kiểm hoặc quá thời hạn.

**Alert không được gửi lại nguyên dữ liệu nhạy cảm** trong email/chat. Dùng event code, actor ID an toàn, scope, mức độ và link tới hệ thống có xác thực.

## 13. Java logging và dữ liệu nhạy cảm

Trước khi phân quyền backend, Java application phải tạo log có **data minimization**.

Ví dụ không an toàn:

```java
// Mảnh code phản diện; logger và request có trong ứng dụng.
logger.debug("request={}", request);
logger.error("Failed to call {}", fullUrlWithToken);
```

Đây không phải code chạy độc lập. `request.toString()` hoặc serializer có thể đưa password, token, Cookie và body vào event; URL có thể chứa API key ở query. Parameterized logging `{}` **không tự che dữ liệu**.

Thay bằng event schema có các trường cần thiết:

```java
// Mảnh tích hợp SLF4J; các giá trị đã được validate/allowlist.
logger.info("event=order_completed service={} requestId={} result={}",
        "orders-api", safeRequestId, "SUCCESS");
```

Cần review:
- Exception `getMessage()`/cause/suppressed, stack traces có URL/SQL credential.
- MDC/ThreadContext chứa dữ liệu truyền giữa threads.
- Structured key-value logging với raw request object.
- HTTP request/response payload logging, access logs, SQL parameter logging.
- Console file, collector, dashboard, notification và archive.

Redaction ở encoder/collector là lớp bổ sung nhưng **không thay thế việc loại secret ngay tại call site**. Khi phát hiện credential đã vào production logs, phải xem như security incident: ngăn ghi tiếp, xác định các sink/bản sao, revoke/rotate theo policy, kiểm soát truy cập và điều tra.

## 14. Kiểm thử phân quyền: phải có DENY

Chỉ kiểm tra “viewer đọc được” là chưa đủ. Bộ test cần kiểm tra hành vi **bị từ chối** và đường truy cập gián tiếp.

| Tình huống | Hành động | Kỳ vọng |
| --- | --- | --- |
| Orders on-call | Search orders STANDARD ở prod | ALLOW theo scope |
| Orders on-call | Search payments RESTRICTED | DENY |
| Orders on-call | Export toàn bộ raw prod logs | DENY nếu chưa grant |
| Collector | Ingest vào index được phép | ALLOW |
| Collector | Search/export index đó | DENY |
| Config admin | Sửa parser theo policy | Có thể ALLOW với approval |
| Config admin | Search RESTRICTED logs | DENY nếu không có read grant |
| Security auditor | Read dataset được duyệt | ALLOW có audit |
| Security auditor | Bulk export chưa phê duyệt | DENY |
| User đã bị revoke | Search bằng session/token cũ | DENY theo policy và TTL đã thiết kế |
| Viewer gọi API trực tiếp | Bỏ filter của UI | DENY ngoài scope |
| Viewer dùng wildcard index | Search tenants khác | DENY |
| K8s on-call được cấp namespace A | `get pods/log` ở namespace A | ALLOW |
| Cùng on-call | `get pods/log` ở namespace B | DENY |
| Backend viewer không có K8s grant | `kubectl logs` | DENY |
| Người không có object IAM | Read archive/snapshot | DENY |
| Break-glass hết hạn | Read restricted dataset | DENY |
| Không có export permission | Gọi raw export API | DENY và có access audit |
| Share link | Người ngoài scope mở | DENY hoặc chỉ nội dung policy cho phép |

### 14.1. Test end-to-end

1. Tạo tài khoản **không có quyền**, on-call và restricted-reader trong môi trường test/staging.
2. Tạo dữ liệu log giả cho hai classifications; sử dụng **canary giả**, không dùng credential thật.
3. Truy vấn từ UI, Search API, raw document endpoint, saved query, dashboard, export và archive.
4. Thử sửa URL, index alias, tenant filter, query wildcards và API arguments để vượt scope.
5. Thử cấp quyền tạm/JIT rồi revoke; kiểm tra session, token, cache và shared link.
6. Test `kubectl auth can-i` và các quyền node/workload trong phạm vi có phép.
7. Test Search/Export outcome, action limits, field-level masking, quotas và rate limiting.
8. Xác nhận audit record từ policy boundary chứa actor/action/scope/decision/outcome, không chứa raw log.
9. Kiểm tra alert/channel nhận notification không có secret.
10. Review effective permissions, role drift và thay đổi policy-as-code qua pull request.

Nếu chỉ kiểm tra UI, đường backend API hoặc snapshot vẫn có thể bypass. Nếu chỉ kiểm tra `kubectl auth can-i`, quyền cloud IAM hoặc collector vẫn có thể cho đường khác tới cùng dữ liệu.

## 15. Xử lý cấp, dùng, thu hồi quyền trong vận hành

Một yêu cầu truy cập logs production nên nêu:
- **Ai** cần quyền? Identity cá nhân hay workload?
- **Tại sao?** Incident, duty, audit/compliance mục đích nào?
- **Ở đâu?** Environment, service, tenant, dataset/classification nào?
- **Làm gì?** Read, query, export, ingest, delete hay configure?
- **Bao lâu?** Temporary grant, session TTL và retention của bản xuất?
- **Ai duyệt và ai theo dõi?** Data owner, service owner, security/on-call theo policy.

Cấp quyền qua IdP/IAM/JIT thay vì chia sẻ admin token. Review định kỳ quyền không dùng, nhân sự đổi nhóm, collector ngừng hoạt động và quyền tồn tại quá lâu.

Khi người dùng báo “không thấy log”, **đừng ngay lập tức cấp admin**. Kiểm tra:
- Đã xác thực đúng identity/IdP group chưa?
- Đang xem đúng workspace, tenant, environment và time window không?
- Policy scope có cho phép service/dataset đó không?
- Dữ liệu có được emit, collector có ingest thành công, backend có retention không?
- UI query có dùng quyền viewer hay service owner?
- Session/cached claims có cần refresh sau grant không?
- Record bị ẩn field hay đang ở archive khác?

Khi phát hiện tài khoản log viewer bị xâm nhập:
1. Revoke/disable tokens và sessions.
2. Kiểm tra query/export/share/grant logs, phạm vi đã bị truy cập.
3. Đánh giá raw data và credentials có thể bị lộ.
4. Revoke/rotate credential thật nếu cần.
5. Kiểm soát các bản export/downstream, phối hợp security/privacy.
6. Cập nhật MFA, scopes, token TTL, alert và review grants.

## 16. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mọi developer có quyền xem mọi prod log | Lộ thông tin nhiều team/tenant | Team/service-scoped read |
| Một admin key dùng cho collector và dashboard | Collector có thể đọc/xóa/export | Service identity ingest-only |
| Chỉ ẩn Export ở frontend | API vẫn có thể export | Backend enforce từng action |
| Filter tenant chỉ ở UI | Có thể sửa request | Server-side tenant scoping |
| Admin config mặc nhiên đọc raw restricted data | Vi phạm separation of duties | Tách grants và kiểm soát indirect paths |
| Cấp `pods/log` rộng trong namespace hỗn hợp | Xem logs workloads không thuộc team | Thiết kế namespace/role hoặc central ACL |
| Chỉ review Kubernetes RBAC | Bỏ qua backend, node, archive | Threat model toàn pipeline |
| Không audit searches/exports | Không truy vết lộ dữ liệu | Protected access audit |
| Dùng một shared break-glass password | Không biết ai đã truy cập | Personal identity, MFA, expiry, hậu kiểm |
| Share raw log trong ticket | Nhân bản dữ liệu nhạy cảm | Reference an toàn và restricted storage |
| Mask trong dashboard, raw index mở | Dữ liệu vẫn bị truy cập qua API | Redact tại nguồn, storage/index ACL |
| Giữ snapshot/export sau revoke không kiểm soát | Quyền không thực sự hết | File/link lifecycle và cloud IAM |
| Xóa log truy cập để “dọn sạch” | Mất chứng cứ | Retention/quarantine và phê duyệt |
| Tin mọi dòng INFO là công khai | Log có thể là audit/PII | Phân loại theo nội dung/mục đích |
| Quên quyền sửa collector | Có thể redirect dữ liệu | Change control và audit cấu hình |
| Không test trường hợp DENY | Policy bypass không bị phát hiện | Negative tests và policy regression |

## 17. Bài tập

**Câu 1.** Collector cần gửi log vào `orders-prod`. Nên cấp role ADMIN để tránh lỗi quyền không?

**Không.** Cấp `LOG_INGEST` với đúng destination, không cấp search/export/delete/role administration. Kiểm thử quyền DENY cho các hành động không liên quan.

**Câu 2.** Developer có `get pods/log` ở namespace production có cả orders và payments. Có chắc họ chỉ xem được orders không?

**Không.** Quyền namespace-level không tự giới hạn theo team. Cần xem exact Role/RoleBinding, chia namespaces khi thích hợp hoặc bảo vệ truy vấn ở central backend theo service.

**Câu 3.** Người dùng đã được quyền READ restricted. Có nên mặc nhiên cho export 60 ngày raw logs?

**Không.** Export là action khác, cần permission, scope, giới hạn, audit, approval và lifecycle riêng.

**Câu 4.** Pipeline admin bị chặn `LOG_READ_RESTRICTED`. Có thể nói chắc không thể lấy restricted log?

**Chưa.** Người đó có thể có quyền sửa collector destination, tạo token hoặc đọc snapshot qua hạ tầng khác. Phải kiểm soát privilege escalation và indirect access.

**Câu 5.** Một nhân viên bị remove group nhưng vẫn có API token và file ZIP đã export. Quá trình thu hồi đã hoàn tất chưa?

**Chưa chắc.** Cần kiểm tra token/session validity, cache, shared links và bản xuất dữ liệu còn tồn tại, xử lý theo chính sách.

**Câu 6.** Tại sao security auditor trong demo được READ RESTRICTED nhưng EXPORT RESTRICTED bị DENY?

**Vì** quyền export là grant riêng. Hàm `permitted` yêu cầu cả quyền đọc tương ứng và `EXPORT_RESTRICTED`; auditor chỉ có quyền đọc.

**Câu 7.** Một API cho phép EXPORT nhưng storage timeout, có nên ghi `EXPORT_COMPLETED result=SUCCESS` không?

**Không.** Authorization ALLOW và kết quả thực thi là hai event khác nhau. Chỉ ghi thành công sau khi có xác nhận phù hợp.

## 18. Checklist production

1. Phân loại log/dataset/field theo rủi ro; loại password, token và PII không cần thiết **trước khi logger được gọi**.
2. Tách permission ingest, read, export, delete, configure, manage-access, retention và audit-read.
3. Cấp quyền theo service/team/environment/tenant và mục đích, có TTL khi phù hợp; deny by default.
4. Xác thực qua identity đáng tin; MFA/JIT/break-glass và incident approval theo policy.
5. Enforce quyền ở backend/API/storage, không chỉ giấu buttons hoặc lọc dữ liệu tại frontend.
6. Kiểm tra Kubernetes `pods/log`, `pods/exec`, node filesystem, workload identity, collector và cloud storage IAM.
7. Collector dùng credential ingest-only, giới hạn destination, rotate và theo dõi.
8. Exports/snapshots có quyền riêng, giới hạn dữ liệu, quyền lưu file, TTL và audit outcome.
9. Access audit ghi actor/action/resource/time/decision/outcome vào kho có bảo vệ độc lập.
10. Review role grants, unused accounts, session/token cache, privilege escalation và policy drift.
11. Kiểm thử positive **và negative**, direct APIs, wildcards, dashboard links, saved queries và archive.
12. Có quy trình revoke/incident response khi viewer/token bị xâm nhập hoặc logs chứa secret.
13. Có cảnh báo khi bulk export, privilege elevation, nhiều DENY, policy change hoặc collector credential dùng sai mục đích.
14. Không coi retention của backend là retention của mọi backup/export; quản trị các bản sao theo vòng đời.
15. Khi on-call không xem được log, kiểm tra đúng identity/scope/query và ingest trước khi cấp quyền rộng.

**Kết luận:** Phân quyền production log là một bài toán **dữ liệu + danh tính + hành động + phạm vi + thời hạn + kiểm toán**, không chỉ là “xem được log hay không”. Trong hệ thống Java, giảm dữ liệu nhạy cảm ngay tại nguồn; trong hạ tầng, tách ingest khỏi read, read khỏi export và cấu hình khỏi quyền xem raw dữ liệu; kiểm soát Kubernetes, backend, snapshot và notification như một chuỗi thống nhất. Chính sách quyền tối thiểu chỉ đáng tin khi đã được enforce và kiểm thử cả những trường hợp phải **DENY**.