# Chọn quyền truy cập trong chiến lược Java Logging

## 1. Vì sao quyền truy cập log phải được thiết kế ngay từ đầu?

Log của một ứng dụng Java có thể chứa nhiều thông tin hơn một dòng báo lỗi: đường dẫn API, IP, dấu vết xác thực, mã đơn hàng, request ID, trace ID, tên host, stack trace, cấu hình runtime và các field vô tình mang dữ liệu người dùng. Nếu một tài khoản có thể đọc mọi log, nó có thể xem dữ liệu không thuộc nhiệm vụ của mình. Nếu một service ghi log cũng có quyền xóa hoặc đổi retention, một sự cố bảo mật có thể làm mất luôn dấu vết điều tra.

**Chọn quyền truy cập** là xác định rõ: **ai** được **thực hiện hành động gì** với **loại log nào**, trong **phạm vi service/tenant/môi trường nào**, trong **bao lâu**, và **ai có thể kiểm toán lại** hành vi đó.

Sơ đồ minh họa:

~~~text
payment-service               log collector                 central log store
     |                            |                               |
     | emit stdout                | ingest/forward                | index/retain
     v                            v                               v
 APP_LOG_WRITER             COLLECTOR_WRITER               PROTECTED LOG DATA
                                                                   |
                             +-------------------------------------+----------------+
                             |                                     |                |
                        ONCALL_READER                         SECURITY_AUDITOR   CONFIG_ADMIN
                       operational only                      sensitive by scope  manage pipeline
                       own service/env                       approved cases      not implicit read
~~~

Một role tổng quát tên admin không nên được xem là lời giải. **Least privilege** (quyền tối thiểu), **separation of duties** (phân tách nhiệm vụ) và **deny by default** (từ chối mặc định) là ba nguyên tắc nền tảng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các quyền EMIT, INGEST, READ, SEARCH, EXPORT, CONFIGURE, DELETE, GRANT và AUDIT_ACCESS.
2. Thiết kế RBAC cùng ABAC để giới hạn quyền theo role, tenant, service, environment, classification và time window.
3. Giải thích vì sao JUL/Logback/Log4j 2 tự thân không quản lý quyền đọc log trong hệ thống tập trung.
4. Áp dụng quyền file Linux/POSIX, Windows ACL, quyền Kubernetes Pod logs và log backend IAM.
5. Biết cách dùng human identity, workload identity, SSO/MFA, JIT access và break-glass.
6. Viết Java 17 độc lập để kiểm thử deny-by-default, cách ly tenant và giới hạn security logs.
7. Bảo vệ quyền export, retention, archives, backups, privacy và audit logs.
8. Xây test matrix cho những đường truy cập dễ bị bỏ sót: API, UI, raw file, dashboard, export, Kubernetes và cold storage.

## 2. Đầu tiên phải xác định tài nguyên và hành động

"Log" không phải một khối dữ liệu đồng nhất. Có thể có:

- stdout/stderr của JVM hoặc Pod.
- File application.log, security.log và rotated archives.
- Log stream/index/dataset của backend/SIEM.
- Trace/correlation context chứa trong structured log.
- Raw payload, stack trace, HTTP metadata và các field nhạy cảm.
- Audit trail ghi nhận chính hành vi xem/xuất/thay đổi log.
- Disk spool tại collector, backup và bản export CSV/JSON.
- Cấu hình route, filter, log level, redaction, retention và alert.

Tương tự, người dùng có thể cần làm nhiều việc khác nhau:

| Hành động | Ý nghĩa | Điểm cần giới hạn |
| --- | --- | --- |
| EMIT | App tạo logging event | Nguồn, schema và thông tin nhạy cảm |
| INGEST | Agent/backend nhận ghi event | Stream/namespace đích, không mặc định có READ |
| READ | Xem một event hoặc tập kết quả | Service, tenant, environment, category |
| SEARCH | Query/filter logs | Cùng authorization với dữ liệu thực |
| REVEAL_SENSITIVE | Xem field raw đã được mask | Permission riêng, lý do, audit |
| EXPORT | Download/copy log ra ngoài backend | Phạm vi, số lượng, destination, retention |
| CONFIGURE | Đổi pipeline, filter, redaction, retention | Change review, audit, phân tách với READ |
| DELETE | Xóa index/file/archive | Chỉ qua chính sách lifecycle/approval |
| GRANT | Cấp hoặc mở rộng quyền | Identity admin có kiểm soát |
| AUDIT_ACCESS | Xem các quyết định truy cập log | Không mở cho mọi log reader |

**Quyền ghi không đồng nghĩa quyền đọc. Quyền đọc không đồng nghĩa quyền export. Quyền cấu hình không tự động bao gồm quyền xem raw security logs.**

Một service account chỉ dùng để ingest không nên được cấp search hoặc delete vì "tiện debug". Một SRE được xem operational logs không tự được xem audit trail của việc truy cập tài khoản khách hàng.

## 3. Phân loại dữ liệu trước khi định nghĩa role

Một policy chỉ nói "ai có thể đọc logs" sẽ quá thô nếu datasets có độ nhạy khác nhau.

| Loại log | Nội dung minh họa | Vai trò cần cân nhắc |
| --- | --- | --- |
| Operational | Startup, duration, error code, health | On-call/SRE của service |
| Business/application | Trạng thái xử lý đơn hàng, correlation ID | Nhóm có nhiệm vụ theo tenant/service |
| Security | Authentication failures, policy decisions | Security responders/auditors được cấp |
| Audit | Đổi quyền, xuất dữ liệu, hành động quản trị | Bộ phận kiểm toán hoặc người được ủy quyền |
| Debug/trace chi tiết | Stack trace, query params, object fields | Chỉ khi thật cần, ngắn hạn, có redaction |
| Collector internal | Retry, queue full, transport errors | Logging platform operators |

Từng nguồn có thể cần **field classification** chứ không chỉ dataset classification. Một operational log tưởng vô hại có thể chứa access token do code vô tình log toàn bộ Authorization header. Vì vậy **không ghi secret là ưu tiên đầu**, sau đó mới tính ACL, encryption và masking.

Một index có cả trường bình thường lẫn nhạy cảm có thể cần field-level security hoặc tách datasets. Nếu backend không hỗ trợ field restriction đáng tin, việc ẩn cột ở dashboard không chặn được API trả raw data.

### Data minimization

OWASP khuyến nghị bảo vệ thông tin log trong lưu trữ và truy cập, đồng thời hạn chế dữ liệu không cần ghi. Trong Java, không log password, session cookie, access token, private key hoặc raw request body chỉ để phục vụ debugging. Dùng mã lỗi, event type, ID an toàn và correlation đã được kiểm soát.

Nếu không ghi dữ liệu nhạy cảm ngay từ đầu, rủi ro của mọi người đọc log, mọi archive và mọi bản sao export đều giảm.

## 4. RBAC: tách vai trò theo nhiệm vụ

**Role-Based Access Control (RBAC)** gán một tập hành động cho role. Ma trận dưới đây là mẫu chính sách, không phải tên role có sẵn trong Logback hay Kubernetes.

| Vai trò | Ingest | Đọc operational | Đọc security | Export | Config | Delete |
| --- | --- | --- | --- | --- | --- | --- |
| APP_LOG_WRITER | Chỉ log của ứng dụng | Không | Không | Không | Không | Không |
| COLLECTOR_WRITER | Đúng stream được cấp | Không | Không | Không | Không | Không |
| ONCALL_READER | Không | Đúng service/env | Không mặc định | Chỉ nếu có grant riêng | Không | Không |
| SECURITY_AUDITOR | Không | Nếu cần theo case | Theo phạm vi được duyệt | Theo approval | Không | Không |
| LOG_CONFIG_ADMIN | Không mặc định | Không mặc định | Không mặc định | Không | Theo change control | Không mặc định |
| RETENTION_OPERATOR | Không | Không mặc định | Không mặc định | Không | Chỉ lifecycle policy | Theo approval |
| BREAK_GLASS_RESPONDER | Theo incident | Khi cần, trong TTL | Nếu phê duyệt | Hạn chế | Hạn chế | Không mặc định |

Đây là mô hình đề xuất để thảo luận. Khi thực thi, phải chuyển sang permission/action names và resource scopes của backend thực tế. Một role được đặt tên khéo nhưng được gắn wildcard resource vẫn có thể nguy hiểm.

### Không suy ra quyền từ tên chức danh

Một người tên "operator" hoặc nằm trong nhóm "admin" ở một công cụ có thể chỉ cần chỉnh collection pipeline. Nếu muốn đọc security logs, phải có quyền riêng, lý do và audit. Phân tách chức năng giúp giới hạn tác động khi credential bị đánh cắp.

## 5. ABAC: scope mới quyết định dữ liệu nào được xem

**Attribute-Based Access Control (ABAC)** bổ sung thuộc tính của identity, tài nguyên, action và bối cảnh.

- **Subject:** danh tính xác thực, group, đội, tenant grants, trạng thái MFA, session validity.
- **Resource:** dataset, service, namespace, environment, tenant_id, sensitivity.
- **Action:** read/search/reveal/export/configure/delete.
- **Context:** incident ID, JIT permission, thời hạn, môi trường truy cập và chính sách bảo mật.

Pseudo-policy:

~~~text
ALLOW READ(event)
  IF authenticated(subject)
 AND hasRole(subject, ONCALL_READER)
 AND event.service in subject.allowedServices
 AND event.environment in subject.allowedEnvironments
 AND event.tenant in subject.allowedTenants
 AND event.classification == OPERATIONAL
 AND requestedFields subsetOf subject.allowedFields

OTHERWISE DENY
~~~

Đây là cách mô tả hợp đồng, **không phải cú pháp IAM chạy trực tiếp**.

Một user có LOG_READER không nên nhìn được mọi tenant; một developer có quyền staging không mặc nhiên thấy prod. Trong hệ thống multi-tenant, tenant được lấy từ **authenticated principal và resource metadata do server kiểm soát**, không chỉ từ tham số tenant_id mà người gọi có thể thay.

### Deny by default và fail closed

Nếu thiếu principal/role, hết TTL, thiếu tenant hoặc classification không hợp lệ, mặc định **DENY** hoặc quarantine theo policy. Đừng viết điều kiện cho phép khi role null.

~~~java
// Anti-pattern, snippet không độc lập và nguy hiểm:
boolean allowed = role == null || role.equals("LOG_READER");
~~~

Mất thông tin xác thực không được biến thành được cấp quyền. API nên phân biệt chưa đăng nhập và không đủ quyền theo security framework, đồng thời không trả raw log ở body lỗi.

## 6. Java 17 hoàn chỉnh: thử quyết định truy cập

Chương trình sau chỉ dùng JDK 17, không cần Maven, Spring, IAM backend hay thư viện ngoài. Nó mô phỏng một log viewer phải kiểm tra **role và tenant trước khi hiển thị**.

Chính sách trong ví dụ:

- LOG_READER đọc operational logs cùng tenant.
- SECURITY_AUDITOR đọc security và operational logs cùng tenant.
- LOG_INGEST có quyền gửi/ghi log theo contract khác, **không có quyền đọc**.
- LOG_CONFIG_ADMIN chỉ quản lý cấu hình, **không có quyền đọc** nếu chưa được cấp.
- Không có đường truy cập tenant khác.
- Mọi lần thử đọc tạo một dòng audit; chỉ ALLOW tạo dòng VIEW.

Các actor và event được hardcode để stdout xác định. Trong ứng dụng thật, identities và tenant grants phải xuất phát từ authentication/IdP đáng tin.

**Tệp: LogAccessDecisionDemo.java**

~~~java
import java.util.Objects;
import java.util.Set;

public final class LogAccessDecisionDemo {
    enum Role {
        LOG_INGEST,
        LOG_READER,
        SECURITY_AUDITOR,
        LOG_CONFIG_ADMIN
    }

    enum Category {
        OPERATIONAL,
        SECURITY
    }

    record Actor(String subject, String tenant, Set<Role> roles) {
        Actor {
            Objects.requireNonNull(subject);
            Objects.requireNonNull(tenant);
            roles = Set.copyOf(Objects.requireNonNull(roles));
        }
    }

    record LogEvent(
            String id,
            String tenant,
            Category category,
            String safeSummary) {

        LogEvent {
            Objects.requireNonNull(id);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(category);
            Objects.requireNonNull(safeSummary);
        }
    }

    static boolean canRead(Actor actor, LogEvent event) {
        if (!actor.tenant().equals(event.tenant())) {
            return false;
        }
        return switch (event.category()) {
            case OPERATIONAL ->
                actor.roles().contains(Role.LOG_READER)
                || actor.roles().contains(Role.SECURITY_AUDITOR);
            case SECURITY ->
                actor.roles().contains(Role.SECURITY_AUDITOR);
        };
    }

    static int attemptRead(Actor actor, LogEvent event) {
        boolean allowed = canRead(actor, event);

        // Audit quyết định; không sao chép raw event payload.
        System.out.println(
                "AUDIT subject=" + actor.subject()
                + " log=" + event.id()
                + " decision=" + (allowed ? "ALLOW" : "DENY"));

        if (allowed) {
            System.out.println(
                    "VIEW log=" + event.id()
                    + " summary=" + event.safeSummary());
        }
        return allowed ? 1 : 0;
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", "tenant-a", Set.of(Role.LOG_READER));
        Actor sara = new Actor(
                "sara", "tenant-a", Set.of(Role.SECURITY_AUDITOR));
        Actor service = new Actor(
                "svc-payments", "tenant-a", Set.of(Role.LOG_INGEST));
        Actor ops = new Actor(
                "ops", "tenant-a", Set.of(Role.LOG_CONFIG_ADMIN));

        LogEvent operational = new LogEvent(
                "evt-1", "tenant-a",
                Category.OPERATIONAL, "payment_started");
        LogEvent security = new LogEvent(
                "evt-2", "tenant-a",
                Category.SECURITY, "login_failed_count_1");
        LogEvent otherTenant = new LogEvent(
                "evt-3", "tenant-b",
                Category.OPERATIONAL, "shipment_created");

        int allowed = 0;
        allowed += attemptRead(alice, operational);
        allowed += attemptRead(alice, security);
        allowed += attemptRead(alice, otherTenant);
        allowed += attemptRead(sara, security);
        allowed += attemptRead(service, operational);
        allowed += attemptRead(ops, operational);

        System.out.println(
                "SUMMARY allowed=" + allowed
                + " denied=" + (6 - allowed));
    }
}
~~~

**Biên dịch và chạy với JDK 17 trở lên:**

~~~bash
javac -encoding UTF-8 LogAccessDecisionDemo.java
java LogAccessDecisionDemo
~~~

**Stdout chính xác:**

~~~text
AUDIT subject=alice log=evt-1 decision=ALLOW
VIEW log=evt-1 summary=payment_started
AUDIT subject=alice log=evt-2 decision=DENY
AUDIT subject=alice log=evt-3 decision=DENY
AUDIT subject=sara log=evt-2 decision=ALLOW
VIEW log=evt-2 summary=login_failed_count_1
AUDIT subject=svc-payments log=evt-1 decision=DENY
AUDIT subject=ops log=evt-1 decision=DENY
SUMMARY allowed=2 denied=4
~~~

### Phân tích kết quả

1. Alice có LOG_READER tenant-a nên đọc được operational log evt-1.
2. Alice không có SECURITY_AUDITOR nên không đọc security log evt-2 dù cùng tenant.
3. Alice không được xem evt-3 ở tenant-b, bất kể category là OPERATIONAL.
4. Sara có SECURITY_AUDITOR tenant-a, đọc được security log evt-2.
5. Service svc-payments chỉ có role ingest, nên READ bị từ chối.
6. Ops có role quản trị cấu hình nhưng không mặc nhiên được READ.
7. Có hai lần ALLOW, bốn lần DENY. Chỉ ALLOW mới in VIEW.
8. Không dùng clock, thread, network nên output không phụ thuộc scheduling.

### Giới hạn của demo

Đây chỉ là **mô hình authorization** với identities được tạo bởi code, không có authentication, JWT validation, session management, database hay backend log thực. Trong production phải kiểm tra principal ở server, xác minh tenant của event, enforce scope cho mọi API, bảo vệ audit sink và tránh in raw nội dung nhạy cảm vào audit.

- Set.copyOf bảo vệ record role set khỏi sửa tại chỗ; không thay thế cấp/thu hồi role qua IdP.
- Hàm canRead chỉ quản lý READ. EXPORT, DELETE, CONFIGURE và GRANT phải có phương thức/policy riêng.
- Không lấy actor.tenant hoặc event.tenant từ query/header client chưa được xác thực.
- Không dùng correlation ID hoặc event ID làm credential.
- Audit in ra stdout chỉ để quan sát trong demo; log audit của hệ thống thật cần sink độc lập có quyền đọc/xóa được kiểm soát.
- Nếu actor ID hoặc event ID nhận từ input bên ngoài, cần validate/escape trước khi đưa vào text log để tránh log injection.
- Một boolean check trong Java không ngăn người dùng truy vấn thẳng backend bằng token quá rộng; hạn chế service credentials và IAM ở backend.

## 7. Java logging API không tự giải quyết IAM

JUL, SLF4J/Logback, Log4j 2 và Spring Boot logging chủ yếu quyết định **có tạo event hay không, level/filter, format và đích ghi**.

| Thành phần | Điều nó kiểm soát | Điều không được suy ra |
| --- | --- | --- |
| JUL Logger/Handler | Level, filter, FileHandler, ConsoleHandler | Phân quyền đọc mọi bản sao log |
| Logback FileAppender | File path, encoder, rolling behavior | Quyền truy cập dashboard/central SIEM |
| Log4j 2 Appender | Destination, filters, layouts, async | Tenant isolation của API query |
| Spring Boot logging | Bootstrapping backend, config file/console | Log storage IAM |
| OS filesystem ACL | Ai đọc/ghi được file trên host | Quyền query hot index/archives khác |
| Kubernetes RBAC | Quyền API như Pod logs/namespace | Field-level redaction/tenant filtering |
| Central log backend IAM | Search/export/index privileges theo sản phẩm | Ngăn ứng dụng log secret trước ingest |

Với Java 17, java.util.logging.FileHandler ghi file theo khả năng của process ở filesystem. Nó không cung cấp sẵn role SECURITY_AUDITOR cho người đọc file. Khi file được ship lên collector/backend, quyền ở backend là một lớp authorization khác.

### Log ingestion phải được bảo vệ riêng

Một service account có quyền INGEST chỉ nên ghi vào stream/dataset đúng scope và không mặc định có search/delete. Nếu bị đánh cắp, token ingest có thể được dùng để spam/giả event; cần xác thực nguồn, rate limit/quota, schema validation và alert. Quyền ghi hẹp không giải quyết mọi rủi ro nhưng giảm tác động.

## 8. Quyền file và thư mục trên Linux/POSIX

Nếu Java ghi file cục bộ, phải giới hạn quyền của **thư mục, file, archives và quá trình rotation**.

Một trạng thái mong muốn:

~~~text
/var/log/myapp/                   owner=appsvc group=logreaders mode=0750
/var/log/myapp/application.log    owner=appsvc group=logreaders mode=0640
~~~

- Directory 0750: owner có rwx, group có r-x, other không có quyền. Group cần execute/traverse để mở file.
- File 0640: owner được rw, group được r, other không có quyền.
- Agent cần tail file có thể thuộc group hoặc dùng ACL thích hợp; không nhất thiết chạy root.
- Các parent directories cũng phải cho phép traversal theo policy.
- umask, default ACL, FileHandler/appender creation mode và logrotate có thể đổi mode sau restart.
- Khi rotating, file mới và archive cần được kiểm tra quyền, không chỉ file active.
- Trên Windows, dùng NTFS ACL và service identities; chmod kiểu POSIX không phải công cụ phân quyền chung.

Lệnh **chỉ đọc metadata** trên Linux:

~~~bash
namei -l /var/log/myapp/application.log
stat -c '%U %G %a %n' /var/log/myapp /var/log/myapp/application.log
getfacl /var/log/myapp/application.log
~~~

Các lệnh phụ thuộc môi trường; getfacl có thể cần package riêng.

### 0640 không đồng nghĩa append-only

Một chủ sở hữu có quyền ghi file có thể sửa nội dung; người có quyền ghi thư mục có thể rename/xóa file theo semantics POSIX. Root hoặc người có quyền hạ tầng cao có thể vượt ACL thông thường. Vì vậy 0640 chỉ là **access control cơ bản**, không phải bảo đảm tamper-evident.

Nếu yêu cầu chống ứng dụng bị xâm nhập xóa bằng chứng, ưu tiên ghi sang backend chỉ cấp quyền ingest cho app, có immutable/tamper-evident retention khi cần. Nếu dùng hash chain, phải bảo vệ baseline/keys độc lập; hash trong cùng file mà attacker được sửa cả file không tự chứng minh integrity.

### Không lưu log trong web root

File log không nên nằm trong thư mục phục vụ static assets hoặc có URL public. Một endpoint download file do user điều khiển path có thể tạo path traversal. Nếu cần log viewer, phải authenticate, authorize, audit, redaction và chỉ lấy từ nguồn/truy vấn đã giới hạn.

## 9. Kubernetes: quyền đọc Pod log qua pods/log

Trong Kubernetes, log Pod được truy cập qua API subresource **pods/log**. RBAC cho phép cấp động tác get đối với subresource này trong một namespace.

**Ví dụ Role/RoleBinding chỉ cấp get pods/log trong namespace payments:**

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payments-pod-log-reader
  namespace: payments
rules:
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payments-pod-log-readers
  namespace: payments
subjects:
  - kind: Group
    name: sre-payments
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: payments-pod-log-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Group sre-payments phải được identity provider xác thực và ánh xạ thực tế; YAML không tạo group. Chỉ áp dụng vào cluster/namespace được phép và có change review.

**Hiểu đúng giới hạn:**

- Rule trên cấp get đối với pods/log; không cấp secrets, pods/exec, pods/delete hoặc cluster-admin.
- Nếu cần liệt kê Pod names trước khi xem log, có thể phải cấp thêm get/list pods sau khi xem xét. Không tự cấp wildcard chỉ để kubectl logs thuận tiện.
- Namespace RoleBinding không tự cho quyền ở namespace khác. Tuy vậy một người có thể đồng thời có nhiều Role/ClusterRoleBinding, nên kiểm tra **tổng quyền**.
- Kubernetes RBAC kiểm soát API request theo Pod/namespace, **không lọc từng dòng hoặc từng field nhạy cảm trong Pod log**.
- Nếu một Pod xử lý nhiều tenant, cấp quyền pods/log có thể làm lộ log của tất cả tenant trong Pod. Người dùng theo tenant nên truy vấn backend có scope/field filtering thực sự, không xem raw Pod log.
- Một người có quyền pods/exec, hostPath/node access hay token ở central log backend có thể đọc log theo đường khác. Phải kiểm soát toàn bộ đường.
- Node/runtime log rotation và collector retention là chuyện khác với quyền API.

Ví dụ kiểm tra current identity:

~~~bash
kubectl auth can-i get pods/log -n payments
kubectl auth can-i get secrets -n payments
kubectl auth can-i create pods/exec -n payments
~~~

Kết quả có thể là yes/no theo tất cả grants đang có, không chỉ Role trên. Không dùng impersonation không được ủy quyền.

### Service account của log collector

Nếu agent chạy DaemonSet và đọc host log files, nó có thể cần node mount/permissions nhạy cảm. Tránh cấp cluster-admin mặc định, đánh giá hostPath, pod security, file ACL, namespace và runtime identity. Collector cần quyền đọc log ở node và quyền ingest ở backend; **không mặc định cần quyền xóa/sửa hoặc search backend**.

## 10. IAM của log backend/SIEM

Khi log được tập trung, backend là nơi cần enforce read/search/export thực. Một policy mẫu:

~~~text
payments-ingester service:
  ALLOW ingest -> payments-prod-operational
  DENY search/export/delete/configure

payments-oncall:
  ALLOW search/read -> payments-prod-operational (redacted)
  DENY security-raw, other-tenant datasets, delete
  EXPORT only with additional grant

security-incident-reader:
  ALLOW read designated security datasets
        within approved case/tenant/time window
  DENY changing retention

logging-platform-operator:
  ALLOW manage pipeline, schema, routing
  DENY raw sensitive read unless separately granted

retention-operator:
  ALLOW policy-governed lifecycle tasks
  DENY ad-hoc purge without approvals
~~~

Đây là pseudo-policy, không phải syntax IAM của một vendor. Khi triển khai, dùng action names, resource patterns và conditions thực sự được sản phẩm hỗ trợ.

### Những câu hỏi bắt buộc

- Backend có resource/index ACL hay chỉ một tài khoản admin toàn cục?
- Có document-level/row-level security cho multi-tenant không?
- Có field-level access hoặc mask dữ liệu tại server không?
- Search API và bulk export API có áp cùng policy không?
- Saved dashboard/alert chạy dưới identity của ai? Có cache kết quả người khác xem được không?
- Cold archive, object storage và bản backup có dùng ACL khác?
- Token ingest có bị cấp nhầm quyền delete hoặc read không?
- Có quyền thay retention/tắt ingest qua một API riêng không?
- Có quản lý TTL/token rotation và logs của chính các quyền này không?

Một dashboard ẩn cột nhạy cảm không đủ nếu người dùng có thể gọi API backend trực tiếp. Cần security boundary ở server/backend và service credential đủ hẹp để ngay cả khi API bị khai thác cũng giảm thiệt hại.

## 11. Quyền export khác quyền read

Export làm xuất hiện một bản sao mới: CSV, JSON, object storage, email attachment hoặc hệ thống phân tích. Bản sao có thể không còn chịu retention/ACL gốc.

Trước khi cấp EXPORT cần:

1. Có permission riêng ngoài READ.
2. Xác định scope tenant, service, environment, classification và thời gian.
3. Kiểm soát field masking/redaction trong **đường export**, không chỉ UI.
4. Có size/rate limit và cảnh báo bulk export bất thường.
5. Có destination được phê duyệt, encryption và ACL cho file xuất.
6. Có TTL và quy trình xóa bản export khi hết mục đích.
7. Ghi audit ai xuất, lúc nào, phạm vi nào, bao nhiêu records/bytes và lý do.
8. Với dữ liệu nhạy cảm, có thể yêu cầu approval/MFA/incident ID.
9. Cần đánh giá cả saved reports, scheduled exports và email notifications.

Một người đọc được 10 dòng operational log không tự cần quyền tải cả tháng security logs. Tương tự, việc có nút Download trong UI không chứng minh quyền đã được kiểm tra tại API.

## 12. Xác thực danh tính: người và máy phải tách

### Human access

- SSO/IdP với danh tính riêng, không dùng shared admin account.
- MFA khi xem dữ liệu nhạy cảm hoặc nâng quyền.
- Group-based grants nhưng kèm scope và expiry/JIT.
- Quyền theo ca trực/incident có thời hạn.
- Revoke khi người dùng đổi team, nghỉ việc hoặc không còn on-call.
- Audit các phiên đọc/export và thay đổi permission.
- Review grants định kỳ để tránh privilege creep.

### Service/workload identity

- Mỗi app/collector có identity hoặc token chuyên dụng.
- Ingest token chỉ cần ghi vào stream được cấp, không cần query/delete.
- Không lưu token trong code, log payload hoặc image.
- Dùng workload identity/secret manager, rotate và short TTL khi có thể.
- Transport dùng TLS, kiểm tra chứng chỉ và hostname.
- Khi mất quyền ingest, tạo error metric/alert qua kênh độc lập; không log raw credentials.
- Không dùng một token cho mọi môi trường nếu có thể tách.

Một API client đưa request_id, correlation_id hoặc trace_id vào request **không chứng minh identity**. Đừng dùng các ID đó làm access token.

## 13. Break-glass cho điều tra khẩn cấp

Trong incident nghiêm trọng, người trực có thể cần đọc dữ liệu nhạy cảm vượt quyền thường ngày. Break-glass nên là **quyền tạm thời có kiểm soát**, không phải superadmin vĩnh viễn.

Quy trình minh họa:

1. Xác thực nhân sự với MFA.
2. Gắn incident/ticket ID và mục đích.
3. Chọn dataset, tenant, environment, time range thật cần thiết.
4. Cấp quyền JIT với TTL ngắn và tự động thu hồi.
5. Cảnh báo khi quyền khẩn cấp được bật.
6. Audit READ, SEARCH, EXPORT, CONFIGURE, DENY trong thời gian đó.
7. Kiểm tra lại sau incident và xác nhận grants đã hết.
8. Quản lý bản export/copy theo retention và privacy.

Nếu cơ chế break-glass phụ thuộc hoàn toàn vào IdP/network có thể hỏng trong chính incident, phải có phương án khôi phục đã được phê duyệt và kiểm thử trước.

## 14. Audit mọi thao tác đặc quyền trên log

Người đọc log cũng cần được ghi nhận truy cập, nhất là khi xem security logs, export, sửa permission hoặc giảm retention.

**Ví dụ structured access audit:**

~~~json
{
  "event_type": "LOG_ACCESS_DECISION",
  "subject_id": "alice",
  "action": "READ",
  "resource_kind": "log_dataset",
  "resource_id": "payments-prod-operational",
  "requested_tenant_scope": "tenant-b",
  "decision": "DENY",
  "reason_code": "SCOPE_MISMATCH",
  "request_id": "audit-request-42"
}
~~~

Đây là schema gợi ý, không phải định dạng mặc định của JUL/Spring/SIEM.

**Nên ghi:** authenticated subject, action, resource, approved/requested scope, decision, reason code an toàn, timestamp, session/request ID, policy version và incident ID nếu có.

**Không nên ghi:** raw log mà user vừa xem, tokens/cookies, full unredacted query, password hoặc payload export. Audit không nên tự tạo thêm một bản sao nhạy cảm.

**Bảo vệ audit sink:** người có quyền xem operational log hoặc chỉnh cấu hình thông thường không nên dễ dàng xóa audit của chính hoạt động đó. Có thể cần storage/retention tách biệt hoặc immutable controls. Nếu dùng hash/tamper-evident mechanism, baseline/keys phải được bảo vệ độc lập.

### Vì sao chỉ ghi DENY là chưa đủ?

Một actor có quyền READ có thể lạm dụng để query hàng triệu records. Ghi cả các lần ALLOW và khối lượng truy xuất giúp phát hiện bất thường. Access logs của viewer cũng cần quản lý retention và privacy, không giữ vô hạn.

## 15. Java web/API viewer: enforce ở server, không ở nút bấm

Một kiến trúc log viewer:

~~~text
Browser
   |
   v
Identity provider -> authenticated principal
   |
   v
API Gateway / Spring Security
   |
   v
Policy check (action + role + scopes)
   |
   v
Query backend with enforced dataset/tenant filter
   |
   v
Mask fields / limit pagination
   |
   v
Response + independent access audit
~~~

Ẩn nút Export trên frontend không thay thế việc kiểm tra quyền tại POST /logs/export. Đọc danh sách tenant có từ authenticated principal/policy service; không tin tham số tenant do client nhập.

Pseudo-example:

~~~text
principal:
  subject=alice
  roles=[LOG_READER]
  allowed_tenants=[tenant-a]
  environments=[staging]

request:
  GET /logs?tenant=tenant-b&env=prod

policy:
  DENY
  never trust query params as authorization grants
  do not return log content in error response
  audit decision and safe reason code
~~~

Trong Spring Security, một annotation kiểm tra hasAuthority có thể là lớp đầu, nhưng dữ liệu được fetch từ repository/search backend vẫn phải enforce tenant/environment/dataset scope. Nếu backend query token có wildcard access, chỉ một bug ở API có thể làm lộ log khác tenant; dùng defense in depth.

## 16. Phạm vi theo tenant, môi trường và thời gian

Quyền READ nên có boundaries:

| Phạm vi | Ví dụ | Sai lầm cần tránh |
| --- | --- | --- |
| Tenant | tenant-a only | Tin tenant_id do client tự gửi |
| Service | payments only | Cho xem mọi cluster index |
| Environment | staging/prod tách biệt | Dev role mặc nhiên đọc prod |
| Classification | operational/security | Dùng một index raw chung không mask |
| Time range | Incident window | Query toàn lịch sử không cần thiết |
| Fields | status và error_code | Export raw payload vì UI chỉ ẩn cột |
| Data volume | Page/query limit | Bulk download không rate limit |
| Session | Quyền JIT 30 phút | Không thu hồi khi incident kết thúc |

Nếu một Pod xử lý nhiều tenant và ghi chung stdout, Kubernetes pods/log RBAC không cung cấp field-level tenant filtering. User theo tenant nên truy cập backend/API có isolation thật, hoặc hệ thống nên tách datasets/workloads phù hợp.

Lưu ý dữ liệu có thể được lưu trong backup, cold archive hoặc disk spool lâu hơn dashboard. Quyền ở hot index không tự kiểm soát các nơi đó.

## 17. Quyền xóa log, chỉnh retention và integrity

Tách tối thiểu:

- WRITE/INGEST để thêm event.
- READ/SEARCH để truy vấn.
- EXPORT để tạo bản sao.
- CONFIGURE để đổi route/schema/redaction/retention.
- DELETE để xóa dữ liệu.
- GRANT để cấp quyền.
- AUDIT_ACCESS để xem access decisions.

Một config admin có thể thay retention từ 90 ngày xuống 1 ngày và dẫn đến xóa lượng lớn log mà không trực tiếp gọi DELETE. Vì vậy CONFIGURE cũng là quyền nhạy cảm, cần review/approval và audit.

Khi hệ thống cần integrity mạnh, cân nhắc append-only ingestion, immutable/WORM archive hoặc tamper-evident logs, kiểm soát keys/manifest và việc hủy dữ liệu theo policy. Chỉ dùng chmod 0444 hay hash file không đủ để chống một attacker có quyền root hoặc quyền sửa baseline.

## 18. Quy trình chọn quyền cho dự án Java

### Bước 1: Kiểm kê

Liệt kê app services, log categories, stdout/files, collectors, indexes, archives, backups, exports và owner của từng nguồn.

### Bước 2: Phân loại

Đánh giá privacy/security/audit levels. Loại bỏ secrets và dữ liệu không cần thiết ngay ở code/encoder; define redaction và retention.

### Bước 3: Xây roles

Tách writer, collector writer, operational reader, security auditor, config admin, retention operator và break-glass. Không gộp READ + EXPORT + DELETE theo một role "admin" mặc định.

### Bước 4: Gắn scopes

Service, namespace, tenant, env, classification, time, fields. Xác định policy được enforce tại nơi nào.

### Bước 5: Áp identity

Human qua IdP/SSO/MFA; machines qua workload/service identity và token hẹp. Bật time-bound access khi thích hợp.

### Bước 6: Enforce ở mọi đường

OS files, Kubernetes API, backend query API, dashboards, scheduled exports, archives, backups và spool.

### Bước 7: Audit và test

Ghi privileged actions và thay đổi grants. Test cả positive/negative cases, cross-tenant, expired grants, API bypass, raw files và bulk export. Review quyền định kỳ.

## 19. Ma trận kiểm thử chính sách

| Test | Identity/Action | Kỳ vọng |
| --- | --- | --- |
| Operational log cùng tenant | Alice LOG_READER tenant-a READ evt-1 | ALLOW |
| Security log cùng tenant | Alice READ evt-2 | DENY |
| Operational tenant khác | Alice READ tenant-b evt-3 | DENY |
| Security auditor đúng tenant | Sara READ evt-2 | ALLOW |
| Service chỉ ingest muốn đọc | svc-payments READ evt-1 | DENY |
| Config admin muốn đọc | ops READ evt-1 | DENY |
| Chưa xác thực | Anonymous READ | DENY |
| Missing role/tenant scope | Unknown principal READ | DENY |
| Đã hết thời gian JIT | Expired grant READ | DENY |
| Reader gọi export | Alice EXPORT | DENY trừ khi có grant riêng |
| Dev đọc prod | Staging-only user READ prod | DENY |
| Reader đổi retention | ONCALL_READER CONFIGURE | DENY |
| Service xóa log | APP_LOG_WRITER DELETE | DENY |
| Export API bỏ UI | No EXPORT grant invokes API | DENY |
| Header tenant giả | Caller khai tenant-b | Không mở grant |
| Kubernetes Pod logs | Role get pods/log đúng namespace | ALLOW theo RBAC |
| Kubernetes secret | Role chỉ pods/log | Không được grant bởi Role đó |
| Bulk query qua backend | Unauthorized dataset | DENY |
| Cold archive | No archive grant | DENY |
| Break-glass hết TTL | Expired role | DENY |
| Authorized export | EXPORT grant, đúng scope, destination | ALLOW và audit |

**Kiểm thử denied:** không có raw content trong response, status hợp lý, audit được ghi, không lộ stack trace hoặc chi tiết tenant khác. **Kiểm thử allowed:** dữ liệu trả về chỉ gồm tenant/service/fields đúng và giới hạn truy vấn.

Với Java policy, có thể viết JUnit 5 parameterized tests cho tổ hợp role × category × tenant. Sau đó cần integration tests với real auth middleware và log backend; một unit test canRead không thể phát hiện API token backend đang có quyền wildcard.

## 20. Các lỗi thường gặp

1. **Ai vận hành server cũng được xem mọi log.** On-call cần quyền điều tra nhưng không mặc nhiên cần raw PII/security logs mọi tenant.
2. **Writer cũng là reader.** Ingest credential bị lộ có thể vừa giả event vừa đọc dữ liệu nếu cấp dư.
3. **Admin cấu hình đồng nghĩa admin dữ liệu.** Tách roles và audit change policy.
4. **Chỉ ẩn nút Export.** API export vẫn phải authorize.
5. **Chỉ dùng chmod 0640.** Còn parent directories, rotation, root, backend, archive.
6. **Tenant client truyền được tin trực tiếp.** Phải derive từ principal và trusted metadata.
7. **Dùng Kubernetes RBAC như field filter.** pods/log là subresource, không lọc field/tenant.
8. **Bảo mật hot index nhưng bỏ quên archive/backup.** Cold storage có thể là đường bypass.
9. **Access audit in toàn bộ raw query/result.** Tạo bản sao sensitive không cần thiết.
10. **Shared admin account.** Không có attribution rõ, khó revoke từng người.
11. **Quyền JIT không hết hạn.** Có thể trở thành privileged access vĩnh viễn.
12. **Token dài hạn commit vào repo/log.** Có thể bị lộ rồi dùng truy vấn backend.
13. **Mã hóa là đủ.** Encryption không thay thế authorization/scope/audit.
14. **Test tất cả bằng admin token.** Không kiểm được least privilege và deny cases.
15. **Sửa retention không được audit.** Có thể xóa bằng chứng gián tiếp.
16. **Break-glass chưa từng thử.** Khi incident có thể không hoạt động hoặc không thu hồi được.

## 21. Troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Người đúng role không xem được log | Scope tenant/service/env sai | Auth principal và policy grants |
| User thấy log tenant khác | Filter chỉ ở UI | Backend query/API authorization |
| Writer có thể xóa index | Wildcard token | Service IAM actions/resources |
| Export lộ field đã mask | Mask chỉ ở frontend | Server/export path and field security |
| Pod logs được đọc nhưng SIEM bị deny | Kubernetes RBAC khác backend IAM | Hai identity/permission planes |
| RoleBinding không hoạt động | Group IdP chưa map, namespace sai | Kubernetes authn và roleRef |
| File mới không cho agent đọc | Umask/default ACL/logrotate | Owner/group/mode và parent dirs |
| Audit log bị xóa cùng operational log | Cùng delete rights | Tách storage/retention/admin |
| Dev đọc được prod | Env grants wildcard | Rà soát role inheritance |
| JIT role còn mãi | Missing TTL/revocation | Identity lifecycle |
| Dashboard share lộ data | Saved query chạy bằng admin | Run-as identity, cache, API |
| Log viewer trả 500 kèm raw stack trace | Error handling sai | Safe error response và access audit |

Quy trình điều tra: xác định identity → action → resource/scope → policy version → backend grant → raw file/API bypass → access audit → sửa quyền tối thiểu → test lại.

## 22. Bài tập thực hành

**Bài 1 – Tách READ và EXPORT.** Thêm enum Action với READ/EXPORT/DELETE/CONFIGURE vào demo. Chỉ grant EXPORT khi có permission riêng. Viết expected ALLOW/DENY và audit.

**Bài 2 – Kiểm soát environment.** Thêm environment vào Actor/LogEvent. User tenant-a chỉ có quyền staging không được xem prod, kể cả query khai tenant hợp lệ.

**Bài 3 – Linux ACL.** Trong sandbox, tạo thư mục 0750 và file 0640, kiểm tra owner, reader group, user không có group. Thử rotation và xác nhận quyền file mới. Không thay thư mục production.

**Bài 4 – Kubernetes RBAC.** Áp Role/RoleBinding mẫu trong cluster test có group đã map. Kiểm tra get pods/log đúng namespace và không grant secrets hoặc exec qua role đó.

**Bài 5 – Export policy.** Thiết kế endpoint export có permission riêng, field redaction, byte limit, TTL cho file xuất và audit. Thử gọi API trực tiếp không qua nút UI.

**Bài 6 – Break-glass.** Cấp quyền security read tạm 30 phút trong test policy engine; gắn incident ID, MFA, alert, log read/deny và tự thu hồi sau TTL.

**Bài 7 – Multi-tenant.** Tạo log records của tenant-a và tenant-b trong cùng dataset. Dùng two test identities, bảo đảm query backend thực trả chỉ dữ liệu được cấp, không chỉ lọc ở frontend.

**Bài 8 – Access audit.** Ghi một access event cho READ/EXPORT/DENY, không copy raw log message vào audit. Test identity có quyền READ operational không xóa được audit trail.

**Bài 9 – Inventory đường đọc.** Liệt kê cùng một event ở stdout, Pod logs, node file, collector spool, SIEM, backup, dashboard, export. Đảm bảo unauthorized actor không đi đường vòng được.

## 23. Checklist triển khai

- [ ] Có inventory sources, files, streams, archives, backups và exports.
- [ ] Mỗi dataset có owner/classification/retention.
- [ ] Có quy tắc loại trừ password/token/secret ngay tại nguồn.
- [ ] Role APP_LOG_WRITER/COLLECTOR_WRITER không mặc định có READ.
- [ ] READ/SEARCH, EXPORT, CONFIGURE, DELETE, GRANT tách nhau.
- [ ] Tenant/service/environment scope được enforce ở server/backend.
- [ ] Có field masking hoặc tách dataset khi backend không hỗ trợ field-level security.
- [ ] SSO/MFA cho người, workload identity riêng cho máy.
- [ ] JIT/break-glass có TTL, approval, alert và revoke.
- [ ] File permissions, rotated archives và parent directories được kiểm tra.
- [ ] Quyền Kubernetes pods/log, exec, secrets được rà soát độc lập.
- [ ] Backend IAM áp cho cả UI, API, saved query, export và cold storage.
- [ ] Privileged READ/EXPORT/CONFIGURE/DELETE/GRANT có access audit.
- [ ] Access audit có retention/ACL riêng và bảo vệ integrity phù hợp.
- [ ] Test cả positive, denied, cross-tenant, expired grant, API bypass.
- [ ] Review grants và token rotation định kỳ, xóa quyền không còn cần.

## 24. Tổng kết

**Chọn quyền truy cập là một phần của thiết kế chiến lược Java Logging.** Hãy tách quyền phát sinh/ingest, đọc/search, xem dữ liệu nhạy cảm, export, cấu hình, xóa và cấp quyền. Dùng RBAC để phân vai, ABAC để giới hạn tenant/service/môi trường/field/thời gian. **Mặc định từ chối** khi chưa đủ bằng chứng được cấp.

Logger API và appender chỉ là một lớp; quyền phải được kiểm soát qua file OS/ACL, Kubernetes Pod logs, collector, SIEM/log backend và API/export/archive. Không để quyền đọc production log mở rộng theo sự tiện lợi, không dùng ID tương quan làm thông tin xác thực và không tự coi mã hóa dữ liệu thay thế authorization.

Để log có giá trị điều tra, hãy tránh ghi secret từ đầu, bảo vệ integrity của audit, cấp quyền khẩn cấp có thời hạn, giám sát mọi truy cập nhạy cảm và kiểm thử tất cả những đường có thể xem hoặc mang log ra ngoài hệ thống.

### Tài liệu tham khảo

- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Kubernetes RBAC Authorization: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes RBAC Good Practices: https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- Kubernetes kubectl logs: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Oracle Java 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java 17 PosixFilePermissions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- NIST SP 800-92 Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 Manual: https://logging.apache.org/log4j/2.x/manual/
- Spring Security Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
