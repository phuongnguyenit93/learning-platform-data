# Audit thay đổi ACL và truy vết quyền được cấp

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Triển khai ACL. Bài này hướng dẫn xây dựng cơ chế **ghi dấu mọi thay đổi quyền trên từng đối tượng** và **giải thích một quyết định GRANT/DENY có nguồn từ ACE nào, SID nào, ACL trực tiếp hay ACL cha**. Trọng tâm là phân biệt audit cấu hình ACL với audit kiểm tra quyền tại runtime; thiết kế sự kiện bất biến, transaction/outbox, truy vết lịch sử và kiểm thử. Các đoạn tích hợp tham chiếu Spring Security ACL 6.x/7.x, Spring Boot Servlet và Java 17+. Không đồng nhất audit logger mặc định với một hệ thống lịch sử thay đổi bảo mật đầy đủ.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Phân biệt ba khái niệm **ACL mutation audit**, **authorization decision audit**, **permission provenance** (nguồn hình thành quyền).
2. Giải thích `acl_entry.audit_success`, `audit_failure`, `AuditableAcl.updateAuditing(...)` và `AuditLogger.logIfNeeded(...)` — đặc biệt là **chúng không tự ghi lịch sử ai thay đổi ACE**.
3. Thiết kế schema sự kiện ghi lại `actor`, `resource type/id`, `tenant`, thay đổi `before → after`, lý do, thời điểm, revision, correlation ID và outcome.
4. Đặt mutation ACL và ghi audit/outbox trong transaction phù hợp để không có “quyền đã đổi nhưng không có nhật ký”, hoặc ngược lại.
5. Diễn giải quyền được cấp theo `ObjectIdentity`, danh sách `Sid`, `Permission`, ACE, `parentAcl`/`entriesInheriting` và chính sách kết hợp khác.
6. Phân biệt **quyền hiện tại** với **quyền tại thời điểm lịch sử**, nhất là khi role membership, ACL cha, trạng thái tenant và dữ liệu domain đã thay đổi.
7. Viết code và kiểm thử một luồng cấp/thu hồi quyền, đọc lại từ `AclService`, xác nhận event audit đúng, và kiểm tra lỗi rollback.
8. Vận hành logging không lộ token/PII, có RBAC khi truy cập log, retention, giám sát biến động quyền và khả năng chống sửa/xóa trái phép.

## 2. Bài toán: “Vì sao Bob đọc được Document 42?”

Một ngày, đội bảo mật nhận câu hỏi:

> “10:15 sáng thứ Năm, Bob mở được Document 42 của tenant alpha. Ai cấp quyền cho Bob, lúc nào, quyền trực tiếp hay thừa hưởng từ Folder, và quyền đó có hợp lệ theo chính sách?”

Chỉ truy vấn ACL **hiện tại** có thể thấy:

~~~text
Document(42):
  ACL id=901
  parentAcl = Folder(9)
  entriesInheriting = true
  local entries: [không có ACE READ cho Bob]

Folder(9):
  ACE: GrantedAuthoritySid("ROLE_REVIEWER") + READ = GRANT

Bob at request time:
  principal = bob
  authorities = [ROLE_REVIEWER, ...]
~~~

Từ dữ liệu đó có thể giải thích **quyền hiệu lực hiện tại** của Bob nhận từ ACL Folder qua `ROLE_REVIEWER`, nếu không có ACE phù hợp khác được ưu tiên và các điều kiện authorization còn lại không veto. Nhưng trả lời **ai thêm ACE vào Folder và khi nào** cần một lịch sử thay đổi độc lập. Trả lời **Bob có thuộc ROLE_REVIEWER lúc 10:15 không** cũng cần bằng chứng về identity/role ở thời điểm đó. Một ACL snapshot tại 16:00 không tự chứng minh quyết định tại 10:15.

Vì vậy phải thiết kế **hai sổ sự kiện** cùng mô hình truy vết:

~~~text
1) ACL CHANGE AUDIT:
   admin carol -> INSERT ACE (ROLE_REVIEWER, READ, GRANT)
   resource Folder(9), revision 17 -> 18, reason=CASE-208

2) ACCESS/DECISION AUDIT:
   Bob -> READ Document(42) at 10:15
   decision GRANT, evaluated on ACL Document->Folder,
   matched SID ROLE_REVIEWER, ACE id=375, policyVersion=...

3) IDENTITY / POLICY CONTEXT:
   at 10:15 Bob was ROLE_REVIEWER in tenant alpha;
   Document(42) belonged to alpha; request filters and state rules passed.
~~~

Không ghi đủ cả ba lớp thì chỉ có thể kết luận đến mức **bằng chứng thực sự cho phép**, không tự điền “chắc Carol đã cấp” hay “chắc Bob đã có role từ trước”.

## 3. Phân biệt hai loại audit mà Spring ACL hỗ trợ khác nhau

| Khái niệm | Sự kiện cần ghi | Cơ chế / giới hạn |
| --- | --- | --- |
| **Mutation audit** | INSERT/UPDATE/DELETE ACE; thay owner/parent/inherit; tạo/xóa ACL | **Ứng dụng phải tự tổ chức** quanh `MutableAclService`/DB; không có lịch sử thay đổi đầy đủ tự phát sinh chỉ vì dùng ACL module |
| **Decision audit** | Kiểm tra READ/WRITE được GRANT hoặc DENY lúc runtime | Có `AuditLogger` và cờ audit trên ACE; cần tích hợp observability nếu muốn lưu ở audit store |
| **Provenance/explain** | Quyền GRANT do SID, ACE, ACL nào, có kế thừa từ cha không | Phải diễn giải dựa trên cùng policy/strategy và dữ liệu snapshot; `Acl.getEntries()` đơn thuần không trả quyền kế thừa |
| **Authentication audit** | Ai đăng nhập, token/credential type, role/tenant snapshot | Thuộc authentication/identity layer, không do `MutableAclService` tự ghi |
| **Business audit** | Ai move Document giữa Folder/tenant, ai đổi classification | Thuộc domain workflow; cần correlation với ACL mutation |

**Nguyên tắc:** `audit_success` và `audit_failure` **không đồng nghĩa** “bật auditing cho mọi thay đổi ACL”. Chúng là flags cho việc ghi **kết quả kiểm tra quyền dựa trên ACE**. Một lệnh `aclService.updateAcl(acl)` không tự thêm audit-event về actor, before/after, reason và request ID vào bảng lịch sử do ứng dụng định nghĩa.

## 4. Những API và cột thực sự có trong Spring Security ACL

### 4.1. Bốn bảng liên quan

Spring Security JDBC ACL thường dùng:

- `acl_class`: type đối tượng được bảo vệ.
- `acl_sid`: principal SID hoặc granted-authority SID.
- `acl_object_identity`: object ID, owner SID, parent ACL, `entries_inheriting`.
- `acl_entry`: mỗi ACE; `sid`, `mask`, `granting`, `ace_order`, `audit_success`, `audit_failure`.

Khối sau chỉ là **lược đồ khái niệm**, không phải migration hoàn chỉnh cho một DB cụ thể:

~~~sql
acl_object_identity (
  id,
  object_id_class,
  object_id_identity,
  parent_object,
  owner_sid,
  entries_inheriting
);

acl_entry (
  id,
  acl_object_identity,
  ace_order,
  sid,
  mask,
  granting,
  audit_success,
  audit_failure
);
~~~

Các bảng này là **trạng thái quyền hiện tại**, không phải event sourcing/history. Khi `updateAcl` sửa `acl_entry`, dữ liệu trước đó có thể bị thay thế/xóa. Nếu muốn trả lời “quyền cũ là gì”, phải có snapshot/diff hoặc audit trail riêng.

### 4.2. API mutation và cờ audit

~~~java
// Trích đoạn trong @Service đã được cấp quyền quản lý ACL.
ObjectIdentity oid =
        new ObjectIdentityImpl("com.acme.domain.Document", documentId);
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

int index = acl.getEntries() == null ? 0 : acl.getEntries().size();
acl.insertAce(index, BasePermission.READ,
              new PrincipalSid("bob"), true);

if (acl instanceof AuditableAcl auditableAcl) {
    auditableAcl.updateAuditing(index, true, true);
}

mutableAclService.updateAcl(acl);
~~~

Imports chính: `ObjectIdentityImpl`, `BasePermission`, `PrincipalSid`, `MutableAcl`, `AuditableAcl`, `MutableAclService`, `ObjectIdentity` từ packages `org.springframework.security.acls.domain` và `org.springframework.security.acls.model`.

Ý nghĩa:
1. `insertAce` tạo ACE trong mutable ACL; `true` là GRANT, không phải bật auditing.
2. `updateAuditing(index, auditSuccess, auditFailure)` đặt cờ audit của **ACE tại index** (API `AuditableAcl`).
3. `updateAcl` lưu mutation vào ACL persistence.
4. `AuditLogger` có thể được gọi khi đánh giá permission phù hợp, tùy cờ audit của ACE, strategy, administrativeMode và đường gọi.
5. Cả bốn bước **chưa ghi** “Carol đã thay đổi ACL lúc 10:15 vì CASE-208”. Cần thiết kế mutation audit riêng.

**Không lưu index của ACE như một định danh bất biến.** `ace_order` có thể đổi khi insert/delete/reorder. Khi làm audit, nên ghi `ACE database ID` nếu đã persist và/hoặc stable tuple (SID, mask, granting, object, sequence/revision), cùng snapshot before/after; đừng lưu mỗi index rồi hi vọng tra lại đúng ACE sau này.

### 4.3. AuditLogger và ConsoleAuditLogger

~~~java
// Mã cấu hình minh họa cho Spring Security ACL.
@Bean
PermissionGrantingStrategy permissionGrantingStrategy() {
    return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger());
}
~~~

`DefaultPermissionGrantingStrategy` dùng `AuditLogger.logIfNeeded(boolean granted, AccessControlEntry ace)` khi đánh giá quyền và khi cờ audit liên quan yêu cầu ghi. `ConsoleAuditLogger` là implementation đơn giản in thông tin ra console. Nó **không phải** hệ thống lưu sự kiện bất biến, không có correlation ID chuẩn và không bảo đảm truy vấn lịch sử nhiều năm.

Để có sự kiện truy cập chuyên nghiệp, có thể cung cấp một `AuditLogger` riêng:

~~~java
// Trích đoạn: sink là interface do ứng dụng triển khai.
final class StructuredAclAuditLogger implements AuditLogger {
    private final DecisionAuditSink sink;

    StructuredAclAuditLogger(DecisionAuditSink sink) {
        this.sink = sink;
    }

    @Override
    public void logIfNeeded(boolean granted, AccessControlEntry ace) {
        if (!(ace instanceof AuditableAccessControlEntry auditable)) {
            return;
        }
        if ((granted && !auditable.isAuditSuccess())
                || (!granted && !auditable.isAuditFailure())) {
            return;
        }
        sink.offer(ace.getAcl().getObjectIdentity(),
                ace.getSid(), ace.getPermission(), granted);
    }
}
~~~

Đây là snippet **không độc lập**, thiếu các interface ứng dụng `DecisionAuditSink` và cấu hình bean. Log hook có **ACE quyết định và granted**, nhưng **không tự cung cấp** actor đang gọi, request ID, tenant, danh sách mọi SID được xét, snapshot role hoặc đầy đủ kết quả kiểm tra policy khác. Nếu cần dữ liệu đó, hãy tạo `AuthorizationDecisionEvent` ở service/security boundary nơi có đủ context và liên kết trace ID an toàn. Tránh tự gọi code I/O chậm/ngoại hệ thống từ logger trên đường nóng của authorization; dùng non-blocking sink có backpressure, sampling chính sách và cơ chế chống mất sự kiện nếu đó là yêu cầu tuân thủ.

**Lưu ý:** `administrativeMode=true` trong `Acl.isGranted(..., administrativeMode)` có ý nghĩa đặc biệt: theo Javadoc, kiểm tra ở chế độ hành chính không thực hiện auditing. Không dùng administrativeMode để “tắt log cho nhanh” trên đường truy cập thông thường.

## 5. Mutation audit cần ghi những trường nào?

Một event nên thể hiện **ai đã yêu cầu**, **quyền gì đã thay đổi**, **đối tượng nào chịu tác động**, **thành công hay thất bại**, và **bằng chứng liên kết giao dịch**.

| Trường đề xuất | Mục đích |
| --- | --- |
| `eventId` | ID duy nhất, dùng chống ghi trùng và đối chiếu |
| `occurredAt` | Thời điểm UTC từ clock đáng tin |
| `actorId` | Stable principal ID/service identity, không chỉ username hiển thị |
| `actorType` | USER / SERVICE / SYSTEM; nếu “on behalf of”, lưu requester riêng |
| `tenantId` | Biên dữ liệu, không do client khai một cách trực tiếp |
| `objectType` + `objectId` | `ObjectIdentity` trọn vẹn; ID riêng lẻ dễ collision giữa các loại resource |
| `action` | ACL_CREATED, ACE_GRANTED, ACE_DENIED, ACE_REMOVED, ACE_PERMISSION_CHANGED, ACL_OWNER_CHANGED, PARENT_CHANGED, INHERITANCE_CHANGED, ACL_DELETED |
| `sidType` + `sidValue` | PRINCIPAL hay AUTHORITY; ví dụ Bob khác ROLE_REVIEWER |
| `permissionMask` + `permissionName` | Quyền theo `BasePermission` hoặc custom Permission |
| `before` / `after` | Snapshot/diff chuẩn hóa, không suy luận từ ACL hiện tại |
| `aclRevisionBefore/After` | Revision monotonic theo object, kiểm tra event loss/race |
| `reasonCode` / `ticketId` | Lý do phê duyệt hoặc case ID đã được kiểm soát |
| `correlationId` / `requestId` | Nối HTTP request, trace, domain event và policy decision |
| `outcome` | SUCCESS / REJECTED / FAILED; nêu rõ event nào là committed fact |
| `policyVersion` | Phiên bản policy/ACL evaluator nếu cần tái hiện lịch sử |
| `source` | API, batch job, migration hoặc console admin |
| `integrityMetadata` | Sequence/hash/signature/retention policy nếu có yêu cầu tamper evidence |

**Phân biệt sự kiện yêu cầu và sự kiện thay đổi đã commit.** “Admin nhấn Save” không có nghĩa DB đã commit. Nếu cần audit cả **thử thay đổi thất bại**, ghi một security-event riêng, không để nó trộn với bảng committed mutation. Sự kiện chính thức “ACE_GRANTED” chỉ xác nhận sau khi thay đổi ACL đã commit theo contract.

### 5.1. Vì sao lưu cả before và after?

Giả sử ACE `ROLE_REVIEWER WRITE = DENY` bị đổi thành `GRANT`, cùng SID/mask. Event “UPDATE ACE” không nói đủ liệu quyền đã mở hay thu hẹp. Cần:

~~~json
{
  "action": "ACE_UPDATED",
  "objectType": "Document",
  "objectId": "42",
  "sidType": "AUTHORITY",
  "sidValue": "ROLE_REVIEWER",
  "before": {"mask": 2, "granting": false},
  "after":  {"mask": 2, "granting": true},
  "reason": "APPROVAL-314"
}
~~~

Số `2` ở đây là mask WRITE thường dùng của `BasePermission.WRITE` trong Spring ACL; với custom permissions phải dùng mapping thực tế của ứng dụng. Đối với thay parent hoặc inheritance, cần snapshot cả ObjectIdentity của cha cũ/mới và `entriesInheriting` trước/sau; không chỉ ACE.

### 5.2. Snapshot hay diff?

- **Diff** gọn và dễ tìm hành động: “thêm quyền READ cho Bob”.
- **Snapshot đầy đủ** sau mỗi N phiên bản giúp tái dựng lịch sử và khắc phục event thiếu.
- Có thể lưu cả event diff chuẩn và snapshot theo chu kỳ.
- Nếu sự kiện dùng để làm bằng chứng tuân thủ, schema phải có version và chính sách retention/immutability. Tránh log raw Authentication/token/secret hay toàn bộ document content.
- Với parent inheritance, muốn giải thích quyền lịch sử phải giữ hoặc tái dựng **cả ACL ancestor path và identity/role membership** tương ứng.

## 6. Chỉ ghi mutation audit ở nơi có quyền sửa ACL

Một hệ thống thường có đường đi:

~~~text
PATCH /api/documents/42/acl/grants
    |
    +-- xác thực admin, principal/tenant
    +-- @PreAuthorize("hasAuthority('acl:manage')")
    +-- domain policy: admin có quyền sửa ACL của Document 42?
    +-- kiểm tra recipient SID/permission có hợp lệ?
    +-- transaction:
            read ACL with lock / optimistic version
            calculate before
            insertAce/updateAce/deleteAce/...
            updateAcl
            persist audit_outbox / audit_change
            commit atomically
    +-- response success after commit
~~~

Không đặt audit event ở UI rồi tin client gửi “after”. Cơ sở ghi lịch sử phải nằm phía server, dùng snapshot trước/sau của ACL đã kiểm tra. Các API sửa quyền không được dựa vào việc người dùng có `READ` trên Document rồi tự suy ra có quyền sửa ACL.

### 6.1. Authorization sửa ACL và mutation audit là hai việc riêng

Spring ACL có `AclAuthorizationStrategy` để kiểm soát một số thao tác mutation trên `MutableAcl`. Ví dụ `AclAuthorizationStrategyImpl` có thể yêu cầu quyền admin/owner theo loại thay đổi; đó là kiểm tra nội bộ, không thay cho policy nghiệp vụ:

- Alice có thể là owner của Document nhưng **không** được chuyển quyền ra tenant khác.
- Một admin của tenant A không được sửa ACL ObjectIdentity của tenant B.
- Người có quyền chia sẻ READ không nhất thiết được cấp WRITE/DELETE/ADMINISTRATION cho người khác.
- Thao tác thay `entriesInheriting` hoặc `parentAcl` có thể lan quyền xuống hàng nghìn descendants; cần quyền quản trị riêng, reason code và audit tác động.

Lưu ý: không dùng `ROLE_ACL_ADMIN` làm role mặc định của tất cả request “để updateAcl không lỗi”. Đây là cách tạo lỗ hổng leo thang quyền.

### 6.2. Ghi audit trong cùng transaction

Nếu domain, ACL và audit outbox cùng database hoặc chia sẻ một transaction resource thực sự, dùng `@Transactional` ở application service gọi qua Spring proxy. Khi transaction rollback, cả thay đổi ACL lẫn outbox “đã commit” đều không còn. Sau commit, một worker có thể chuyển event từ outbox sang hệ thống audit append-only, với idempotency theo `eventId`.

**Không đảm bảo atomicity chỉ bằng cách đặt `@Transactional`** nếu:
- ACL JDBC dùng DataSource/transaction manager khác DB audit.
- Gửi Kafka/HTTP audit service giữa transaction rồi sau đó rollback.
- Spring method bị self-invocation bỏ qua transaction proxy.
- ACL mutation chạy `@Async` trên thread khác (transaction context của caller không tự truyền).
- Audit event được ghi sau commit nhưng process chết trước khi gửi.

Nếu cần chống mất sự kiện, transactional outbox đáng tin hơn gọi network trực tiếp rồi hy vọng “cả hai cùng thành công”.

## 7. SQL audit outbox: một thiết kế thực tế

Dùng migration do ứng dụng quản lý (ví dụ PostgreSQL, kiểu dữ liệu tùy DB):

~~~sql
-- MẪU thiết kế, cần thêm constraints/partition/RLS theo hệ thống thật.
CREATE TABLE acl_audit_outbox (
    event_id        UUID PRIMARY KEY,
    tenant_id       VARCHAR(120) NOT NULL,
    object_type     VARCHAR(240) NOT NULL,
    object_id       VARCHAR(120) NOT NULL,
    acl_revision    BIGINT NOT NULL,
    actor_id        VARCHAR(160) NOT NULL,
    action          VARCHAR(80) NOT NULL,
    event_payload   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ NULL,
    publish_attempt INT NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, object_type, object_id, acl_revision)
);
~~~

**Giải thích:**

- `event_id` hỗ trợ publisher retry và consumer de-duplicate.
- `tenant_id + object_type + object_id + acl_revision` giúp kiểm tra thứ tự per-object; cần đảm bảo revision được cấp **atomically**.
- `event_payload` có before/after và correlationId; không chứa secrets.
- `published_at` chỉ đánh dấu outbox đã được giao tới downstream theo contract, **không** có nghĩa audit downstream luôn xử lý đúng nếu ack/commit sai.
- `publish_attempt` giúp giám sát lỗi.
- `UNIQUE(...)` là ví dụ nếu **mỗi revision chỉ có một event tổng hợp**. Nếu một mutation tạo nhiều events, dùng `event_sequence` hoặc một event chứa nhiều diffs; không giữ unique constraint như trên rồi khiến insert thứ hai bị lỗi.

SQL ở đây là DDL minh họa; nếu dùng MySQL/H2 cần đổi kiểu `UUID`/`JSONB`/`TIMESTAMPTZ` phù hợp. Ngoài outbox, cần một **audit ledger/history** append-only riêng để truy vấn lâu dài, không chỉ xóa event ngay khi publisher hoàn tất.

### 7.1. Mẫu payload

~~~json
{
  "eventId": "d9bc3cb0-68ae-4a96-a344-d3067d1cda31",
  "schemaVersion": 1,
  "actor": {"kind": "USER", "id": "carol-17"},
  "resource": {
    "tenantId": "tenant-alpha",
    "type": "com.acme.domain.Document",
    "id": "42"
  },
  "action": "ACE_GRANTED",
  "revision": {"before": 7, "after": 8},
  "changes": [{
    "sidType": "PRINCIPAL",
    "sid": "bob-23",
    "permission": "READ",
    "mask": 1,
    "before": null,
    "after": {"granting": true, "auditSuccess": true, "auditFailure": true}
  }],
  "reasonCode": "TICKET-814",
  "correlationId": "req-54bb",
  "occurredAt": "2026-11-05T06:00:00Z"
}
~~~

Các ID, thời điểm và người trong payload là **dữ liệu ví dụ**, không phải sự kiện của một hệ thống có thật. `mask:1` tương ứng READ thông dụng; nếu ứng dụng dùng custom `Permission`, ghi rõ mapping.

## 8. Spring service: cấp quyền và ghi sự kiện trong một boundary

Đây là **mã trích đoạn tích hợp** cho project đã có ACL persistence, audit repository/outbox, transaction manager và tenant policy. Không phải chương trình standalone vì `AclChangeOutbox`, `AclChangeOutboxRepository`, `AclRevisionRepository`, `ScopePolicy`, `StableIdentity` là các interface/kiểu do ứng dụng phải tự định nghĩa.

~~~java
@Service
public class DocumentAclCommandService {
    private final MutableAclService aclService;
    private final ScopePolicy scopePolicy;
    private final AclRevisionRepository revisions;
    private final AclChangeOutboxRepository outbox;
    private final StableIdentity identity;

    public DocumentAclCommandService(
            MutableAclService aclService, ScopePolicy scopePolicy,
            AclRevisionRepository revisions,
            AclChangeOutboxRepository outbox, StableIdentity identity) {
        this.aclService = aclService;
        this.scopePolicy = scopePolicy;
        this.revisions = revisions;
        this.outbox = outbox;
        this.identity = identity;
    }

    @Transactional
    @PreAuthorize("hasAuthority('acl:manage')")
    public void grantRead(long documentId, String recipientId,
                          String reason, String correlationId) {
        String actorId = identity.requireAuthenticatedActorId();
        String tenantId = identity.requireTrustedTenantId();

        // Phải kiểm tra cả object, actor, recipient, tenant và quyền grant.
        scopePolicy.requireCanGrantRead(
                actorId, tenantId, documentId, recipientId);

        ObjectIdentity oid =
                new ObjectIdentityImpl(
                        "com.acme.domain.Document", documentId);
        MutableAcl acl = (MutableAcl) aclService.readAclById(oid);

        // Khóa/version cần được cấp theo cùng resource và transaction.
        long nextRevision = revisions.lockAndNext(
                tenantId, oid.getType(), String.valueOf(documentId));

        // Chống trùng ACE: repository/policy phải phát hiện case đã grant.
        if (hasExplicitGrant(acl, new PrincipalSid(recipientId),
                             BasePermission.READ)) {
            throw new IllegalStateException("Grant already exists");
        }

        int index = acl.getEntries() == null
                ? 0 : acl.getEntries().size();
        Sid recipient = new PrincipalSid(recipientId);
        acl.insertAce(index, BasePermission.READ, recipient, true);

        if (acl instanceof AuditableAcl auditable) {
            auditable.updateAuditing(index, true, true);
        }
        aclService.updateAcl(acl);

        // Audit event là dữ liệu server tạo, cùng transaction với ACL.
        outbox.save(AclChangeOutbox.grantRead(
                tenantId, oid, actorId, recipientId,
                nextRevision, reason, correlationId));
    }

    private boolean hasExplicitGrant(
            Acl acl, Sid sid, Permission permission) {
        List<AccessControlEntry> entries = acl.getEntries();
        if (entries == null) return false;
        return entries.stream().anyMatch(e ->
                e.getSid().equals(sid)
                && e.getPermission().getMask() == permission.getMask()
                && e.isGranting());
    }
}
~~~

**Imports cần có** khi tích hợp: `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.security.access.prepost.PreAuthorize`, `org.springframework.security.acls.model.*`, `org.springframework.security.acls.domain.*` và `java.util.List`. Các helper/repository nêu trong code là contract ứng dụng, phải được triển khai, không phải lớp của Spring Security.

### 8.1. Vì sao phải lưu snapshot/diff before và after?

Mã minh họa `AclChangeOutbox.grantRead(...)` cố tình là factory ứng dụng. Implementation thực phải lấy snapshot trước mutation (hoặc đầy đủ tuple thay đổi), ghi **mask, granting, audit flags, sid type/value, parent/inheritance/owner nếu thay đổi**. Đặc biệt:
- Đừng tạo event chỉ từ request payload, vì ACL có thể bị dịch vụ chuẩn hóa/đổi thứ tự.
- Nếu `updateAcl` đổi ACE database ID, ghi ID sau persist nếu cần và có thể tra lại.
- Với `deleteAce`, phải snapshot ACE bị xóa **trước khi xóa**.
- Với `updateAce`, lưu cả permission/mask cũ và mới.
- Với `setParent`, lưu ObjectIdentity cha cũ/mới và kiểm tra tenant/cycle.

**Ghi chú về hasExplicitGrant:** Hàm trên chỉ giúp tìm **ACE trực tiếp** đã cấp đúng mask cho SID, không phát hiện quyền đang được kế thừa. Nó không thay cho `Acl.isGranted(...)` để đánh giá quyền hiệu lực. Khi idempotency yêu cầu “grant đã tồn tại ở local”, logic này có thể hữu ích, nhưng mọi policy cần kiểm tra cả grant trái dấu và duplicate SID/mask để tránh kết quả bất ngờ.

### 8.2. Revision và concurrency

`MutableAclService`/schema mặc định không cung cấp một **revision lịch sử per-object** đáp ứng tự động mọi yêu cầu audit. Bạn phải tạo bảng/version riêng hoặc dùng optimistic lock trên domain/ACL metadata theo kiến trúc. `lockAndNext(...)` là **API ứng dụng giả định**, cần triển khai bằng row lock, compare-and-swap hoặc serialization phù hợp trong transaction.

Không cấp revision bằng `SELECT MAX(revision)+1` mà không khóa/unique constraint: hai request đồng thời có thể cùng nhận số 8. Nếu outbox insert trùng revision rồi rollback, retry phải tuân thủ idempotency và không tạo grant kép.

### 8.3. Audit event thành công và sự kiện thử thất bại

Khi `@PreAuthorize` chặn một lời gọi grant trước thân method, không có mutation và cũng không có committed event ở outbox do service. Nếu cần theo dõi hành vi quản trị trái phép, đặt **attempt audit** ở security layer:

~~~text
ACL_CHANGE_REJECTED:
  actorId, resource, requestedAction, reasonCode, timestamp, requestId
  outcome=REJECTED
  detail=NOT_AUTHORIZED
~~~

Event này không được ngụ ý quyền đã được thay đổi. Vì một transaction rollback sẽ xóa cả audit outbox transaction đó, sự kiện “thử thất bại” có thể cần đường ghi độc lập, an toàn, hạn chế dữ liệu nhạy cảm và chịu được service lỗi. Đừng để audit lỗi gây mở quyền hoặc che mất lỗi authorization thực.

## 9. Truy vết nguồn quyền GRANT: nhiều dữ liệu hơn một boolean

`Acl.isGranted(List<Permission>, List<Sid>, boolean)` là **oracle quyết định quyền ACL** (trong phạm vi implementation và security context được cấu hình). Một boolean GRANT/DENY chưa nói:
- Đến từ `PrincipalSid("bob")` hay `GrantedAuthoritySid("ROLE_REVIEWER")`?
- Match ACE trực tiếp của Document hay ACE cha ở Folder?
- ACE có mask READ hay composite/custom mask?
- Quyết định bị hạn chế bởi tenant/feature flag/business state hay chưa?
- Có `NotFoundException` vì thiếu ACE hay một ACE DENY rõ ràng?
- Decision có đang dựa trên ACL cache stale hay không?

### 9.1. Đừng dùng getEntries để tự quyết định quyền

Theo Javadoc `Acl.getEntries()`, danh sách đó là ACE **thuộc ACL hiện tại**, không tự gộp ACE từ ACL cha. Một ACL có thể được tải chỉ cho một tập `Sid`; `isSidLoaded(...)` cần được xét khi công cụ explain/debug yêu cầu dữ liệu đầy đủ. API khuyến cáo dùng `isGranted(...)` để ra quyết định, không suy diễn “thấy ACE nào trước thì grant”.

Để có **permission provenance**:
1. Tạo một `decisionId` và ghi context về actor, tenant, resource, permission, timestamp, policy version, SID list theo đúng thứ tự.
2. Dùng policy/`Acl.isGranted` thật để tính outcome.
3. Ghi/thu một trace giải thích **candidate ACE đã được kiểm tra** và nguồn ACL/parent, tránh thuật toán song song có thể lệch strategy.
4. Nếu phải duyệt ACL tree để giải thích, bảo đảm cùng snapshot/transaction hoặc ghi rõ kết quả chỉ là **best-effort current explanation**.
5. Đính kèm revision ACL và identity membership version nếu có để tái dựng sau này.

Một `AuditLogger.logIfNeeded(granted, ace)` cho bạn ACE liên quan đến logging, nhưng **không bảo đảm** một narrative đầy đủ của mọi rule/role đã được xét. Nếu cần exact trace cho hệ thống nhạy cảm, instrument `PermissionGrantingStrategy`/authorization layer hoặc xây decision engine có trace, rồi kiểm thử sự tương đương.

### 9.2. Biểu đồ nguồn quyền

~~~text
Auth Bob:
  PrincipalSid("bob")
  GrantedAuthoritySid("ROLE_REVIEWER")
  ...
           |
           v
Target Document 42, permission READ
  ACL(Document 42)
  - local READ for Bob?          none
  - entriesInheriting?           true
  - parentAcl?                   Folder 9
           |
           v
  ACL(Folder 9)
  - ROLE_REVIEWER READ           GRANT
           |
           v
  ACL outcome                    GRANT
           |
           v
  Additional policy:
  - same tenant?                 true
  - account active?              true
           |
           v
  FINAL outcome                  GRANT
~~~

**Cẩn trọng:** Sơ đồ minh họa một đường thuận lợi với ít ACE; không được dùng nó như specification đầy đủ khi có nhiều `Sid`/permission/ACE trái dấu. `DefaultPermissionGrantingStrategy` xét danh sách permission và SID theo thứ tự quan trọng; custom matcher có thể đổi cách so mask. Vì thế **trace thực tế phải ghi rõ algorithm/version** và không tự tuyên bố DENY bất kỳ đâu luôn thắng hay ACE ở con luôn thắng trong mọi tổ hợp SID.

### 9.3. Inheritance và vì sao quyền có thể lan rộng

`Acl.getParentAcl()` biểu diễn quan hệ cha, còn `Acl.isEntriesInheriting()` quyết định liệu ACE của cha có được tham khảo khi cần hay không. Nếu Document inherits Folder, một thay đổi ACE ở Folder có thể thay đổi quyền của nhiều Documents mà không ghi riêng ACE ở từng con.

Một audit mutation chỉ có:

~~~text
ACL_CHANGED Folder 9: ROLE_REVIEWER READ = GRANT
~~~

không đủ để liệt kê ngay **mọi** Document bị ảnh hưởng. Nếu compliance yêu cầu “blast radius”, cần truy vấn descendants (theo ACL hierarchy và domain scope), tính effective rights trên các trường hợp liên quan và lưu **impact summary** hoặc job đánh giá. Đừng phát một event “cấp READ cho tất cả Document” khi chưa chứng minh chính sách/structure tương ứng.

### 9.4. Missing ACE không phải DENY ACE

`Acl.isGranted(...)` với `DefaultPermissionGrantingStrategy` có thể ném `NotFoundException` khi không có ACE phù hợp trong đường lookup; đó là trạng thái **không tìm thấy quyết định**, khác với ACE có `granting=false`. Trong hệ thống fail closed, cả hai cuối cùng đều không cho người dùng truy cập, nhưng logs nên phân biệt:

~~~text
DENY_EXPLICIT: matched ACE granting=false
DENY_NO_MATCH: no applicable ACE; strategy raised NotFoundException
DENY_TENANT:  ACL might grant, but required tenant policy denies
DENY_AUTHENTICATION: identity not authenticated
~~~

Phân biệt lý do giúp điều tra provisioning thiếu ACL, thay đổi role, lỗi caching và hành vi tấn công. Không tiết lộ chi tiết này nguyên vẹn cho client không có quyền, vì có thể làm lộ sự tồn tại/owner/tenant của object.

## 10. Trace lịch sử: quyền lúc 10:15 khác quyền lúc 16:00

Nếu chỉ lưu ACL snapshot hiện tại, một hệ thống có thể **không tái dựng** quyết định trong quá khứ vì:

- ACE đã bị xóa/sửa (cần mutation history).
- Parent ACL hoặc `entriesInheriting` đã đổi (cần hierarchy history).
- User đã bị gỡ `ROLE_REVIEWER` (cần authority membership snapshot/sự kiện).
- Tenant của Document hoặc user đã đổi (cần lịch sử domain identity).
- Custom permission matcher/policy deployment đã nâng phiên bản (cần code/policy version).
- Cache stale ở một instance khiến decision lúc đó dùng snapshot khác DB hiện tại (cần cache revision/decision facts).
- Token lúc đó có authority claim cũ dù identity directory hiện tại đã đổi (cần trusted claims snapshot và quy tắc revocation).

### 10.1. Sự kiện decision nên chứa gì?

Một structured decision event có thể ghi:

~~~json
{
  "decisionId": "dec-9acd",
  "occurredAt": "2026-11-05T03:15:00Z",
  "actorId": "bob-23",
  "tenantId": "tenant-alpha",
  "resource": {"type": "Document", "id": "42"},
  "action": "READ",
  "result": "GRANT",
  "policyVersion": "authz-2026-11-01",
  "aclRevision": 18,
  "matchedAce": {
    "sourceType": "Folder",
    "sourceId": "9",
    "sidType": "AUTHORITY",
    "sid": "ROLE_REVIEWER",
    "permissionMask": 1,
    "granting": true
  },
  "inheritancePath": ["Document:42", "Folder:9"],
  "correlationId": "req-54bb"
}
~~~

Đây là **ví dụ schema custom**, Spring không tự phát đúng object JSON này. Để khẳng định chính xác `matchedAce` và `inheritancePath`, phải instrument decision engine trên cùng snapshot, không tự đoán sau từ `AclService.readAclById(...)` tại thời điểm khác.

### 10.2. Cần giữ gì để điều tra đủ tin cậy?

- Mutation event ledger có thứ tự, revision, before/after, reason.
- Decision events chọn lọc theo rủi ro: mọi DENY nhạy cảm, GRANT cho tài nguyên tối mật, thao tác admin, và sampling nếu lưu lượng rất lớn (cân nhắc nghĩa vụ pháp lý).
- Định danh phiên bản policy/role membership ở thời điểm quyết định, hoặc signed claims tối thiểu được redacted.
- Thông tin liên kết transaction/trace/request ID, trạng thái delivery, deadline và alert.
- Bằng chứng integrity/retention và RBAC dành cho investigator; audit admin cũng phải được audit.

Nếu thiếu dữ liệu, báo cáo nên ghi **“không thể xác minh chính xác lý do quyền lịch sử vì thiếu snapshot X”**, thay vì gán lỗi cho người hoặc tự suy diễn chính sách đã hoạt động.

## 11. Chương trình Java 17 độc lập: mutation log và giải thích nguồn quyền

Chương trình sau **không dùng Spring**. Nó mô phỏng một SID, một permission, ưu tiên ACE local trước và fallback lên parent khi `inherits=true`. Nó cho thấy quyền từ Folder có thể ảnh hưởng Document, local DENY thay đổi kết quả, mutation log ghi who/what/before/after, và cắt inheritance thay đổi quyền hiệu lực.

Lưu toàn bộ thành `AclAuditDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AclAuditDemo {
    record Key(String sid, String permission) {}

    record Event(long revision, String actor, String resource,
                 String sid, String permission,
                 String before, String after) {}

    static final List<Event> HISTORY = new ArrayList<>();

    static final class Node {
        final String name;
        final Node parent;
        final Map<Key, Boolean> local = new LinkedHashMap<>();
        boolean inherits;
        long revision = 0;

        Node(String name, Node parent, boolean inherits) {
            this.name = name;
            this.parent = parent;
            this.inherits = inherits;
        }

        void change(String actor, String sid, String permission,
                    Boolean granting) {
            Key key = new Key(sid, permission);
            Boolean before = local.get(key);

            if (granting == null) {
                local.remove(key);
            } else {
                local.put(key, granting);
            }
            revision++;

            HISTORY.add(new Event(revision, actor, name, sid, permission,
                    describe(before), describe(granting)));
        }
    }

    static String describe(Boolean value) {
        if (value == null) return "UNSET";
        return value ? "GRANT" : "DENY";
    }

    static String explain(Node node, String sid, String permission) {
        List<String> path = new ArrayList<>();
        Node current = node;
        while (current != null) {
            path.add(current.name);
            Boolean vote = current.local.get(new Key(sid, permission));
            if (vote != null) {
                return describe(vote) + " via " + current.name
                        + " path=" + String.join(">", path);
            }
            if (!current.inherits) break;
            current = current.parent;
        }
        // Missing decision: mô hình này trả NO_ACE, không gán GRANT.
        return "NO_ACE path=" + String.join(">", path);
    }

    public static void main(String[] args) {
        Node folder = new Node("Folder", null, false);
        Node document = new Node("Document", folder, true);

        folder.change("carol", "bob", "READ", true);
        System.out.println("initial=" +
                explain(document, "bob", "READ"));

        document.change("alice", "bob", "READ", false);
        System.out.println("local-deny=" +
                explain(document, "bob", "READ"));

        document.change("alice", "bob", "READ", null);
        System.out.println("after-revoke-local=" +
                explain(document, "bob", "READ"));

        document.inherits = false;
        System.out.println("inheritance-off=" +
                explain(document, "bob", "READ"));

        System.out.println("events=" + HISTORY.size());
        for (Event event : HISTORY) {
            System.out.println(event.resource() + "#" + event.revision()
                    + ":" + event.actor() + ":"
                    + event.before() + "->" + event.after());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AclAuditDemo.java
java AclAuditDemo
~~~

**stdout chính xác:**

~~~text
initial=GRANT via Folder path=Document>Folder
local-deny=DENY via Document path=Document
after-revoke-local=GRANT via Folder path=Document>Folder
inheritance-off=NO_ACE path=Document
events=3
Folder#1:carol:UNSET->GRANT
Document#1:alice:UNSET->DENY
Document#2:alice:DENY->UNSET
~~~

Giải thích:
- Carol cấp READ tại Folder, Document ban đầu thừa hưởng.
- Alice thêm DENY trực tiếp ở Document nên quyết định local cho Bob/READ thay đổi.
- Khi xóa local DENY, quyền READ từ Folder xuất hiện trở lại. **Xóa một deny không tương đương tự cấp grant trực tiếp**, nhưng có thể mở quyền hiệu lực do inheritance.
- Tắt `inherits` chặn fallback, tạo kết quả `NO_ACE` (Spring ACL có thể ném `NotFoundException`). Demo cố ý không thêm event cho thao tác tắt inheritance, để minh họa **lỗ hổng audit** nếu chỉ log thay đổi ACE mà bỏ sót metadata ACL. Hệ thống thật phải có event `INHERITANCE_CHANGED`.
- Mỗi resource có revision riêng (Folder#1, Document#1,#2); nếu muốn một thứ tự toàn cục, cần sequence/global event ID khác.
- Đây là code mô phỏng, không tái tạo toàn bộ `DefaultPermissionGrantingStrategy` đa SID/mask và không phải transaction manager.

## 12. Kiểm thử đúng ở ba tầng

### 12.1. Unit test mutation diff

Với service xây `AclChangeEvent`, unit test nên kiểm:
- Tạo ACE READ GRANT mới: before UNSET, after GRANT, event actor/resource/SID/mask đúng.
- Đổi ACE từ DENY sang GRANT: before DENY, after GRANT; không phát “ACE_CREATED” sai.
- Xóa local DENY: event ghi DENY → UNSET, không tự phát grant explicit.
- Sửa `audit_success`/`audit_failure`: event ghi thay đổi audit flags.
- Đổi owner ACL: record oldOwner/newOwner.
- Thay `parentAcl`: record oldParent/newParent và kiểm tra biên tenant.
- Đổi `entriesInheriting`: record old/new và đánh giá possible blast radius.
- Lỗi validation/authorization: không có committed mutation event.
- Lỗi repository: không đánh dấu outbox published khi chưa được commit.

Một unit test dùng mock `MutableAclService` có thể kiểm tra trình tự `read → insertAce → updateAcl → save(outbox)`, nhưng **không chứng minh** JDBC và outbox cùng rollback. Cần integration test.

### 12.2. Integration test: transaction và reload

Trong test Spring Boot có DB thử nghiệm và ACL schema:
1. Cấp quyền admin đã xác minh và gọi service qua **Spring proxy**.
2. Đọc bản ghi ACL hiện tại bằng `AclService.readAclById(...)` và read outbox/ledger trong transaction mới.
3. Assert ACE READ cho đúng SID, audit flags đúng, một event before/after đúng revision.
4. Inject lỗi `outbox.save` sau `aclService.updateAcl`; assert sau rollback không có ACE mới và không có committed event. Chỉ valid nếu JDBC ACL và outbox thực sự chung transaction.
5. Inject lỗi `aclService.updateAcl`; assert event không được ghi như thành công.
6. Retry cùng eventId/idempotency key; consumer không tạo trùng ledger.
7. Thực thi hai thao tác grant/revoke song song, assert monotonic revision/unique constraint và final state.
8. Kiểm chứng sau restart/reload/cache evict, không chỉ trên cùng Java object mutable.
9. Kiểm tra owner/tenant wrong, forbidden actor, disallowed recipient và quyền vượt phạm vi đều không thay đổi ACL.
10. Chạy test với DB dialect/transaction manager gần production; `@SpringBootTest @Transactional` rollback cuối test có thể che lỗi commit thật.

### 12.3. Authorization decision test

Test trực tiếp `Acl.isGranted(...)` với `List<Permission>` và `List<Sid>` có thứ tự xác định. Dùng các case:

| ACL setup | Kết quả và nguồn cần giải thích |
| --- | --- |
| Document local Bob READ GRANT | GRANT từ Document |
| Document không có ACE, inherits=true; Folder Bob READ GRANT | GRANT từ Folder |
| Document Bob READ DENY, Folder Bob READ GRANT | Với một SID+READ: DENY local |
| Document inherits=false; Folder grant | Không nhận parent, thiếu local ACE có thể là NotFound |
| Parent ACE bị revoke | Child đang dựa trên parent grant mất nguồn quyền |
| Bob có cả PrincipalSid và ROLE_REVIEWER SID | Kết quả tùy thứ tự SID, ACE/mask; phải test implementation |
| ACE audit_success=true | `AuditLogger` có thể được gọi ở grant phù hợp |
| ACE audit_failure=true | `AuditLogger` có thể được gọi ở deny phù hợp |
| `administrativeMode=true` | Theo contract không audit quyết định hành chính |
| Child/parent loaded subset SID | Phải xác minh `isSidLoaded`/reload trước khi kết luận |
| ACL no-match và deny explicit | Phân biệt `NotFoundException` và false |

Bổ sung test `hasPermission` qua `@PreAuthorize`/`AclPermissionEvaluator` và HTTP `MockMvc` nếu entrypoint public. Tránh unit test tự gọi evaluator rồi kết luận method-security proxy đang hoạt động.

### 12.4. AuditLogger test riêng

Để test logger:
- Dùng implementation `AuditLogger` fake ghi nhận các lần gọi `logIfNeeded(granted, ace)`.
- Tạo `AclImpl` với `DefaultPermissionGrantingStrategy(fakeLogger)` và ACE có audit flags phù hợp.
- Assert callback xảy ra khi `Acl.isGranted` đánh giá đúng ACE với administrativeMode=false.
- Assert không có callback ở đường không phù hợp audit flags hoặc administrativeMode=true.
- **Không đồng nhất** callback audit decision với event mutation; test `MutableAclService.updateAcl` và outbox riêng.

## 13. Truy vết từ dữ liệu lịch sử: một phép điều tra có kiểm chứng

Giả sử nhân viên bảo mật điều tra quyền của Bob tại thời điểm T.

### Bước 1 — Xác định request/decision

Tìm theo `decisionId` hoặc `correlationId` thay vì chỉ tìm tên người và giờ. Xác nhận request thật đã đi qua auth filter/method-security proxy, target ObjectIdentity và loại permission.

### Bước 2 — Xác định actor, authorities và tenant ở T

Từ trusted authentication log/claims snapshot: Bob là ai (stable ID), authorities nào đang hiệu lực, account status/tenant gì. Không lấy role hiện tại thay role tại T.

### Bước 3 — Tái dựng ACL tại T

Từ mutation ledger/snapshots:
- ObjectIdentity của Document.
- Local ACE list với `ace_order`, SID, mask, granting và audit flags.
- Parent chain, `entriesInheriting` từng tầng.
- Các mutation trước/sau thời điểm T, revision theo object và parent.
- ACL cache/state đã được serve ở request đó, nếu có metadata.

### Bước 4 — Đối chiếu với decision engine/policy lúc T

Dùng same-version strategy/mask matcher và thứ tự danh sách SID/permission đã log; so với recorded final decision. Không tự viết “quy tắc gần giống” rồi nhận là kết quả chính xác. Nếu không có environment/policy version, nêu rõ kết luận chỉ best effort.

### Bước 5 — Tìm grant origin

Ví dụ:

~~~text
Result: GRANT READ for Document 42
Observed origin:
  ACE #375 at Folder(9), ROLE_REVIEWER, READ, granting=true
  Inheritance path: Document(42) -> Folder(9)
  Change event that introduced ACE: EVT-8821
  Actor: carol-17; reason TICKET-814
  ACL revision: Folder(9)#18
  Bob membership evidence: ROLE_REVIEWER at T
  Additional required policies: tenant/active checks PASS
Confidence: high only if event, decision, identity snapshots align
~~~

Nếu không có `decisionId` hoặc không có lịch sử role, đừng khẳng định “Bob chắc chắn được cấp vào T”; hãy tách evidence observed và assumption.

### Bước 6 — Xác minh hậu quả và đóng điều tra

Kiểm tra tài liệu nhạy cảm khác chịu inheritance từ Folder, event revoke sau đó, active sessions, downloads/exfiltration dấu hiệu, audit integrity và remediation. Đừng biến mọi audit log GRANT thành bằng chứng dữ liệu thực sự đã được tải: authorization GRANT có thể xảy ra rồi controller/DB lỗi trước khi trả dữ liệu. Muốn biết dữ liệu đã được truy xuất, cần access/business/HTTP outcome log riêng.

## 14. Vận hành: integrity, retention, quyền đọc log và cảnh báo

### 14.1. Chống sửa/xóa lịch sử

Bảng audit cùng quyền ghi với business admin chưa chắc đủ tin cậy nếu chính admin có thể `DELETE FROM audit_events`. Những biện pháp có giá trị:
- Append-only IAM/DB permission (không cấp UPDATE/DELETE cho application role).
- Chuyển event sau commit tới hệ thống lưu trữ tách quyền quản trị; immutable/WORM retention khi có yêu cầu tuân thủ.
- ID, revision và hash chain/signature để phát hiện xóa/sửa **khi triển khai đúng khóa và anchor độc lập**.
- Monitoring publication gaps, duplicate event IDs, out-of-order sequence, offset lag, clock skew và sync failures.
- Audit truy cập **chính audit log** và giới hạn investigator theo tenant/need-to-know.

Không khẳng định hash chain nội bộ cùng một DB là “không thể sửa”: kẻ có quyền thay đổi cả records và hashes có thể viết lại chuỗi. Cần anchor/secret key/ledger độc lập nếu yêu cầu tamper evidence mạnh.

### 14.2. Không lộ dữ liệu nhạy cảm

Nên log: stable actor ID, resource type/ID, tenant ID đã được xác minh, SID type/value đã được bảo vệ theo chính sách, permission mask/action, revision, reason code, correlation ID.

Không log:
- Raw Authorization/Bearer header, password, refresh/access token.
- `Authentication#getCredentials()`, toàn bộ principal details.
- Nội dung Document, ACL secrets hoặc thông điệp policy nội bộ vượt nhu cầu kiểm toán.
- PII quá mức chỉ vì muốn giúp debug; áp redaction/field-level encryption khi cần.

`ConsoleAuditLogger` có thể in thông tin ACE ra console; nếu production logs được nhiều bên đọc hoặc có forwarding ra bên ngoài, nên dùng structured sink đã kiểm soát thay vì console debug mặc định.

### 14.3. Chọn mức độ audit theo rủi ro

| Trường hợp | Mức audit khuyến nghị |
| --- | --- |
| Thêm/xóa admin/WRITE/DELETE ACE | Event mutation **bắt buộc**, reason/approval, alert khi bất thường |
| Reparent, bật inheritance trên subtree | Audit metadata, impact analysis và cảnh báo quyền lan rộng |
| Đổi owner của ACL | Audit old/new owner và quyền actor thực hiện |
| READ trên tài nguyên nhạy cảm | Decision GRANT và business access outcome theo policy |
| DENY liên tục do tenant/ACL | Security monitoring chống enumeration/probing |
| Hàng triệu lần READ public không nhạy cảm | Cân nhắc sampling/aggregation, nhưng không làm mất event bắt buộc |
| ACL/outbox publisher thất bại | Error alerts, retry/dead letter, kiểm tra gap |
| Truy vấn audit history | Audit riêng người tra cứu, mục đích và export |

Retention phải theo luật/hợp đồng/dữ liệu nhạy cảm áp dụng cho tổ chức; không chọn con số tùy tiện. Nếu cần xóa dữ liệu cá nhân mà vẫn giữ sự kiện bảo mật tối thiểu, thiết kế pseudonymization/key separation và chính sách pháp lý phù hợp.

## 15. Lỗi phổ biến và cách sửa

### Lỗi 1 — Chỉ bật audit_success/audit_failure là có lịch sử ai thay ACL

Sai. Hai cờ nằm trên ACE, dùng cho **auditing quyết định**. Lịch sử mutations cần transactionally written events hoặc database CDC có đủ context actor/before/after; CDC thuần có thể không biết lý do/người yêu cầu.

### Lỗi 2 — Dùng ConsoleAuditLogger làm audit ledger

`ConsoleAuditLogger` in log cơ bản, không bảo đảm immutable, retention, correlation, re-delivery, quyền truy cập, schema version. Dùng structured durable audit store/outbox khi cần điều tra.

### Lỗi 3 — Log “grant READ” nhưng không log SID type

`PrincipalSid("REVIEWER")` khác `GrantedAuthoritySid("REVIEWER")`. Bỏ SID type có thể nhầm quyền cấp cho một người với quyền cấp cho cả nhóm. Ghi đầy đủ type/value/permission mask.

### Lỗi 4 — Chỉ lưu object ID

Document 42 và Invoice 42 có thể cùng ID. Luôn ghi ObjectIdentity gồm **type + ID** và tenant scope tin cậy.

### Lỗi 5 — Chỉ log hiện trạng sau update

Không có before sẽ không biết DENY→GRANT, grant→deny, owner change hay parent change đã xảy ra. Lưu diff/snapshot và revision.

### Lỗi 6 — Bỏ qua thay đổi parent/inheritance

Quyền có thể lan xuống cả subtree mà không phát sinh ACE tại child. Audit phải bao phủ `setParent`/`setEntriesInheriting`/ACL delete và blast radius.

### Lỗi 7 — Bỏ qua thay đổi role membership

Bob được ROLE_REVIEWER ở t1, dù ACE được tạo ở t0. Quyền hiệu lực có thể xuất hiện mà **không đổi ACL**. Audit identity/role policy và correlation với ACL decision.

### Lỗi 8 — Dùng getEntries() làm permission oracle

`getEntries()` không liệt kê inherited ACE; ACL có thể được tải thiếu SIDs. Dùng `Acl.isGranted(...)`/real policy để quyết định; explain/provenance cần cùng snapshot và algorithm.

### Lỗi 9 — Cho rằng DENY ACE và không thấy ACE là một

`NotFoundException` khác kết quả false do explicit DENY. Cùng fail closed nhưng phải log distinct reason để xử lý provisioning/cache lỗi.

### Lỗi 10 — Gửi sự kiện audit ra network trong transaction rồi rollback

Audit stream có thể ghi “grant committed” dù DB rollback. Dùng outbox cùng DB transaction, publish sau commit với idempotency; phân biệt attempt và committed mutation.

### Lỗi 11 — Chỉ @Transactional mà hai DataSource không chung transaction

Không bảo đảm ACL DB, outbox DB và domain DB rollback cùng nhau. Tính atomic phải được chứng minh bằng integration test fail injection, không chỉ bởi annotation.

### Lỗi 12 — Không có revision/lock khi hai admin sửa cùng ACL

Event có thể sai thứ tự; một bản ghi ACL có thể bị last-write-wins. Dùng lock/optimistic version và unique event revision, test concurrent updates.

### Lỗi 13 — Đọc ACL hiện tại để giải thích access tháng trước

Role, parent, SID và ACE đã thay đổi; hậu kiểm hiện tại không chứng minh lịch sử. Cần decision snapshot + event history + policy version.

### Lỗi 14 — Log mọi principal details/token

Audit log có thể trở thành một kho bí mật dễ bị truy cập. Chỉ lưu thông tin cần thiết, redaction, bảo vệ theo tenant, mã hóa và retention đúng mục đích.

### Lỗi 15 — Không audit truy cập hệ thống audit

Một người có quyền xem hoặc export audit log có thể biết lịch sử tài nguyên nhạy cảm. Áp RBAC/ABAC, MFA cho điều tra nhạy cảm và audit hành động export/search.

### Lỗi 16 — Coi GRANT nghĩa là đã tải dữ liệu

Authorization GRANT là **quyết định quyền**, chưa chứng minh HTTP trả 200 hoặc byte dữ liệu được download. Nối với business event/response status/object storage access log khi điều tra truy cập thực tế.

## 16. Bảng QA trước khi phát hành

| Ca | Điều cần chứng minh |
| --- | --- |
| Cấp READ ACE trực tiếp | ACL và committed event cùng tồn tại sau commit |
| Xóa hoặc đảo ACE | Before/after đúng, không mất lịch sử cũ |
| Thay parent/inherit | Event bao phủ metadata, kiểm tra quyền lan xuống |
| Đổi ACL owner | Old/new owner, actor, reason được ghi |
| ACL write lỗi trước commit | Không có committed event hoặc quyền bị đổi một phần |
| Outbox insert lỗi | ACL mutation rollback nếu chung transaction |
| Publisher retry | Consumer dedupe theo eventId, không duplicate ledger |
| Hai mutation song song | Revision không trùng/out-of-order theo object |
| Actor không có quyền quản trị | ACL không đổi; attempt audit nếu yêu cầu |
| Recipient thuộc tenant khác | Deny; không thay ACL hay lộ user khác |
| Inherited READ | Trace chỉ rõ parent source, inheritance path |
| Local DENY trên child | Trace đúng quyết định với SID/permission thử nghiệm |
| Multiple SIDs/permissions | Trace khớp `DefaultPermissionGrantingStrategy`, không dùng quy tắc suy diễn |
| All ACE absent | Phân biệt NotFound vs DENY explicit |
| Audit flags off / administrativeMode | Không khẳng định có callback quyết định nếu không được cấu hình |
| Role đổi nhưng ACL không đổi | Historical decision khác current decision được giải thích đúng |
| Multi-instance cache | ACL revision/caches sau revoke nhất quán theo SLA |
| Audit export/search | RBAC, tenant scoping và audit truy cập audit store |
| Retention / integrity | Phát hiện tampering/gaps theo thiết kế đã chọn |

### Bài tập 1 — “Ai cấp READ cho Bob?”

ACL Document 42 không có local ACE, còn Folder 9 có `ROLE_REVIEWER READ = GRANT`. Bob hiện mang ROLE_REVIEWER. Chỉ nhìn bảng hiện tại có thể biết ai đã cấp quyền không?

**Đáp án:** Không. Có thể giải thích khả năng quyền hiệu lực hiện tại được kế thừa từ ACE của Folder, nhưng không biết **ai/bao giờ** tạo ACE nếu không có mutation audit. Muốn chứng minh lịch sử cần membership, policy/ACL revision và decision log tại thời điểm quan tâm.

### Bài tập 2 — Tắt inheritance có cần audit?

Document 42 vẫn tham chiếu parent Folder 9 nhưng `entriesInheriting` đổi true→false. Không có ACE nào bị xóa. Có cần event không?

**Đáp án:** Có. Quyền hiệu lực có thể thay đổi lớn; event nên ghi actor, old/new inheritance, parent, object, revision và reason. Đây là mutation policy dù bảng `acl_entry` không đổi.

### Bài tập 3 — Xóa local DENY có phải là cấp quyền không?

Document có local READ DENY cho Bob, Folder có READ GRANT cho ROLE_REVIEWER, Bob thuộc role này. Admin xóa local DENY. Điều gì xảy ra?

**Đáp án:** Có thể mở READ hiệu lực thông qua fallback đến Folder theo kết hợp SID/strategy cụ thể. Mutation event là **ACE_REMOVED** với before DENY→after UNSET, không tự ghi sai là “cấp ACE local READ”.

### Bài tập 4 — Vì sao cần transactional outbox?

ACL `updateAcl` thành công ở DB, nhưng gọi remote audit service thất bại. Nếu trả thành công và bỏ log, hệ thống mất dấu. Nếu remote log trước rồi local DB rollback, lại có event giả. Giải pháp?

**Đáp án:** Ghi outbox và ACL mutation trong cùng DB transaction phù hợp; publisher sau commit chuyển đến durable audit store với event ID/idempotency, retry và monitoring. Nếu hai DB khác transaction cần thiết kế compensation/consistency riêng.

### Bài tập 5 — Vì sao decision log không chứng minh download thành công?

AuditLogger ghi GRANT READ, sau đó controller ném 500. Điều tra viên có thể kết luận Bob đã lấy toàn bộ nội dung không?

**Đáp án:** Không. GRANT chỉ là kết quả kiểm tra authorization; phải đối chiếu với HTTP response, business access/outbox/object storage log để xác minh dữ liệu đã được trả hay chưa.

## 17. Tóm tắt

Audit ACL đầy đủ cần **ba lớp dữ liệu có liên hệ**:

1. **Mutation history**: ai thay đổi ACE/owner/parent/inheritance, trước và sau, trên ObjectIdentity nào, lý do gì, revision và trạng thái commit.
2. **Authorization decision audit**: ai yêu cầu quyền gì, policy/ACL version nào được xét, kết quả GRANT/DENY/NO_MATCH, tương quan với HTTP/business outcomes.
3. **Permission provenance**: nếu quyền được cấp, nguồn là SID/ACE/ACL cụ thể nào; có đến từ parent hay role membership không; khi điều tra quá khứ cần snapshot của identity, ACL và chính sách **lúc đó**.

Các cờ `audit_success`/`audit_failure` và `ConsoleAuditLogger` hỗ trợ logging quyết định quyền, **không thay** cơ chế audit mutations có transaction, retention, integrity và explainability. Dùng `Acl.isGranted` làm cơ sở quyết định; mọi tiện ích giải thích phải thống nhất với strategy/snapshot, không suy diễn từ một danh sách ACE cục bộ.

**Nguyên tắc cuối:** *Một thay đổi quyền chỉ được coi là “đã xảy ra” khi commit; một quyền chỉ được coi là “đã được cấp” khi decision engine đã cho phép trong đúng bối cảnh và thời điểm; một kết luận điều tra chỉ đáng tin khi có bằng chứng cho cả hai.*

## Tài liệu chính thức

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): mô hình bảng ACL, `AclService`, `MutableAclService`, `DefaultPermissionGrantingStrategy` và wiring `AuditLogger`.
- [DefaultPermissionGrantingStrategy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): thứ tự Permission/SID, auditing và `NotFoundException`.
- [AuditLogger Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AuditLogger.html): `logIfNeeded(granted, ace)`.
- [ConsoleAuditLogger Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/ConsoleAuditLogger.html): audit logger đơn giản cho ACE.
- [AuditableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AuditableAcl.html): `updateAuditing(aceIndex,auditSuccess,auditFailure)`.
- [Acl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `getEntries`, `isSidLoaded`, `isGranted`, parent/inheritance.
- [AccessControlEntry Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AccessControlEntry.html): SID, Permission, grant/deny, ACE ID.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): create/update/delete ACL; bản thân API không phải mutation event store.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy/transaction boundary, lý do cần kiểm chứng cùng transaction resource.
