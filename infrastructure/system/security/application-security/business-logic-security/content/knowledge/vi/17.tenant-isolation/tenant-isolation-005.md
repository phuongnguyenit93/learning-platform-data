# Tenant administrator boundary — Ranh giới quyền của quản trị viên tenant

## 1. Quản trị một tenant không đồng nghĩa quản trị toàn hệ thống

Trong ứng dụng nhiều tenant, quản trị viên tenant thường được giao những quyền mạnh: mời thành viên, phân công vai trò, cấu hình tích hợp và quản lý dữ liệu của tổ chức mình. Những quyền đó cần thiết cho vận hành, nhưng không được mặc nhiên vượt sang tenant khác hoặc mặt phẳng quản trị nền tảng.

**Tenant administrator boundary** là tập giới hạn xác định quản trị viên tenant được quản lý chủ thể nào, tài nguyên nào, hành động nào và cấu hình nào, kể cả khi họ có thể cấp quyền cho người khác.

Một bất biến cốt lõi là:

```text
Quyền quản trị tenant T không tự tạo quyền trên tenant U,
không tự tạo quyền nền tảng và không được tắt các bảo vệ bắt buộc.
```

Ranh giới này không chỉ nằm ở câu SQL có `tenant_id`. Nó còn nằm ở quyền sửa role, nguồn danh tính, cấu hình SSO, công cụ hỗ trợ, background job và các tùy chọn có thể thay đổi quy trình nghiệp vụ.

Ví dụ, một quản trị viên chỉ có dữ liệu tenant A nhưng được phép sửa một role template dùng chung toàn hệ thống vẫn có thể ảnh hưởng tenant B. Một quản trị viên không có quyền duyệt chi nhưng được tự đổi danh tính của người duyệt cũng có thể đạt quyền đó qua đường gián tiếp.

Bài học này giải thích cách xác định trần thẩm quyền, kiểm tra quyền theo đối tượng và bảo vệ các đường quản trị có thể phá tenant isolation.

## 2. Phân biệt những miền thẩm quyền

Không nên gom mọi tài khoản có tên “admin” vào cùng một nhánh bỏ qua kiểm tra.

| Chủ thể hoặc vai trò | Phạm vi điển hình | Không mặc nhiên được làm |
| --- | --- | --- |
| Quản trị viên tenant | Thành viên, role và cấu hình được cho phép trong tenant | Sửa tenant khác, cấp quyền nền tảng hoặc tắt audit bắt buộc |
| Người phê duyệt nghiệp vụ | Hồ sơ và bước phê duyệt trong phạm vi được giao | Quản lý toàn bộ danh tính hoặc tự thay chính sách bảo vệ |
| Auditor của tenant | Bằng chứng và kết luận kiểm tra được phép | Chỉnh giao dịch để xóa phát hiện |
| Nhân viên hỗ trợ nền tảng | Những thao tác được cấp theo yêu cầu hỗ trợ cụ thể | Tự động có quyền đọc và sửa mọi dữ liệu khách hàng |
| Quản trị an ninh nền tảng | Những chính sách và chức năng quản trị được giao | Mặc nhiên thay thế mọi thẩm quyền nghiệp vụ |
| Service account | Loại command hoặc tích hợp đã được giới hạn | Dùng quyền kỹ thuật để thực hiện mọi yêu cầu do tenant gửi |

Tên role không quyết định phạm vi. Role `ADMIN` của tenant A phải được diễn giải trong namespace và scope tương ứng, không được xử lý như một quyền quản trị nền tảng vì trùng tên.

### 2.1. Không nhất thiết có một role cao nhất bao trùm mọi thứ

Quản trị danh tính, quản lý role, duyệt khoản chi, kiểm toán và vận hành hạ tầng là những trách nhiệm có thể cần tách biệt. Một thứ bậc duy nhất kiểu `USER < TENANT_ADMIN < PLATFORM_ADMIN` không diễn đạt đủ các ranh giới này.

Nếu cần quyền khẩn cấp, đó phải là một cơ chế có phạm vi, thời hạn và kiểm soát riêng. Không dùng nó làm ngữ nghĩa mặc định cho mọi endpoint có tham số `admin=true`.

## 3. Định nghĩa trần thẩm quyền của tenant

Một quản trị viên tenant có thể được phép quản lý một phần chính sách cục bộ, nhưng chính sách cục bộ không được tự mở rộng quyền nền tảng.

Có thể hình dung ba lớp:

```text
Lớp bảo vệ bắt buộc của nền tảng
  → khung quyền quản trị được giao cho tenant
    → cấu hình, role và assignment cục bộ hợp lệ
```

Ví dụ trần thẩm quyền:

| Nội dung | Tenant có thể được cấu hình | Giới hạn bắt buộc |
| --- | --- | --- |
| Vai trò thành viên | Gán những role cục bộ được phép | Không tạo hoặc gán permission nền tảng |
| Hạn mức nghiệp vụ | Chọn mức trong khoảng được giao | Không vượt trần hoặc bỏ bất biến số tiền |
| Quy trình phê duyệt | Chọn nhóm người duyệt theo mô hình được hỗ trợ | Không tắt điều kiện độc lập bắt buộc |
| Tích hợp | Quản lý tích hợp của tenant | Không lấy credential dùng chung hoặc truy cập hạ tầng ngoài phạm vi |
| Cấu hình dữ liệu | Những trường cho phép trong tenant | Không đổi quyền sở hữu sang tenant khác bằng một bản vá dữ liệu |
| Audit | Đọc dữ liệu được phép, có thể đặt thêm yêu cầu cục bộ | Không xóa audit bắt buộc hoặc tắt ghi nhận của nền tảng |

Trần này phải do server thực thi. Không để một JSON cấu hình do tenant sửa có thể đặt `skipApproval`, `disableMandatoryAudit` hoặc `allowCrossTenantAccess` rồi được code dùng trực tiếp như quyền hợp lệ.

### 3.1. Kiểm tra quyền hiệu lực, không chỉ tên role

Một role cục bộ có thể nhận permission từ role khác. Nếu chỉ cấm gán role có tên nền tảng, tenant admin có thể tạo role mới nhận kế thừa từ role bị cấm.

Khi tạo, sửa hoặc gán role, cần xem quyền hiệu lực sau thay đổi có còn nằm trong khung quản trị được giao hay không. Các permission hoặc role hệ thống được bảo vệ phải có ranh giới rõ ràng, không chỉ một quy ước đặt tên.

## 4. Mô hình đe dọa: coi quản trị viên tenant là một chủ thể có giới hạn

Đối với tenant isolation, không giả định quản trị viên luôn dùng đúng giao diện hoặc chỉ gọi API theo luồng được thiết kế.

Họ có thể:

- Thay tenant ID, member ID hoặc role ID trong request.
- Gửi thêm các trường mà giao diện không hiển thị.
- Dùng API import, batch, webhook hoặc tác vụ nền.
- Tạo role tổng hợp, đổi group mapping hoặc cấu hình nguồn danh tính.
- Phát lại yêu cầu quản trị cũ sau khi quyền đã bị thu hồi.
- Cố dùng một service account có phạm vi rộng làm trung gian.

Trong mô hình cơ bản, tenant admin không có toàn quyền trên cơ sở dữ liệu nền tảng, khóa ký và hệ thống triển khai. Nếu họ có các quyền đó, ranh giới ứng dụng phải được đánh giá lại theo mô hình đặc quyền tương ứng.

### 4.1. Quyền gián tiếp cũng là quyền thực tế

Nếu một người không có quyền đọc tài liệu nhưng được tự cấp role đọc, khả năng đọc là một quyền gián tiếp của họ. Nếu được thay cấu hình danh tính để đăng nhập thành người có quyền duyệt, quyền duyệt có thể bị tiếp cận qua đường quản trị danh tính.

Vì vậy, không tuyên bố “tenant admin không thể làm X” chỉ vì role hiện tại không liệt kê action X. Phải xem toàn bộ chuỗi có thể dùng để đạt action đó.

Nếu cần bảo vệ một nhóm người duyệt hoặc dữ liệu đặc biệt ngay cả trước tenant admin, quyền quản lý danh tính, khôi phục tài khoản, phân công role và cấu hình nguồn xác thực của nhóm đó cũng phải có cơ chế độc lập phù hợp.

## 5. Xác định tenant đang thao tác từ ngữ cảnh đã kiểm tra

Một tài khoản có thể thuộc nhiều tenant. Việc chọn tenant qua URL hoặc header không nhất thiết là sai; sai là tin lựa chọn đó mà không kiểm tra quan hệ và quyền.

Quy trình phù hợp:

1. Xác thực danh tính người gọi.
2. Đọc tenant được yêu cầu từ đường vào được thiết kế.
3. Kiểm tra membership, phạm vi và quyền quản trị hiện tại của danh tính trên tenant đó.
4. Tạo ngữ cảnh tenant đã được xác minh cho action.
5. Dùng cùng ngữ cảnh đó cho mọi truy vấn, cập nhật, audit và command phát sinh.

```text
TenantAdministrationContext = {
    authenticated_subject,
    active_tenant,
    membership_reference,
    authorization_revision,
    delegated_administration_scope,
    original_actor_if_any
}
```

Không cho body ghi đè tenant sau khi ngữ cảnh đã được xác định. Nếu URL, command và đối tượng tham chiếu mâu thuẫn, phải từ chối hoặc xử lý theo hợp đồng rõ ràng, không âm thầm chọn giá trị thuận lợi.

Thiếu tenant không nên rơi về “toàn hệ thống”. Một endpoint quản trị tenant không được trở thành endpoint toàn cục khi tham số rỗng hoặc header bị bỏ.

### 5.1. Role phải được kiểm tra trong đúng membership

Một người có role admin ở A và thành viên thường ở B không được dùng role A khi chuyển active tenant sang B.

Cache và bộ tính quyền cần giữ quan hệ giữa chủ thể, tenant, membership và revision. Cache chỉ theo user ID hoặc chuỗi `ADMIN` dễ tạo nhầm lẫn phạm vi.

## 6. Kiểm tra cùng tenant trên toàn bộ đồ thị đối tượng

Một thao tác gán role có ít nhất ba đối tượng cần ràng buộc:

```text
actor membership → tenant đang quản trị
target membership → cùng tenant
target role       → catalog được phép của tenant
```

Không đủ để kiểm tra người gọi là admin A rồi tìm target member hoặc role bằng một ID toàn cục không có điều kiện tenant.

Ví dụ một truy vấn đối tượng nên có hợp đồng:

```java
memberships.findByTenantAndId(activeTenantId, membershipId);
roles.findLocalRoleByTenantAndId(activeTenantId, roleId);
```

Tên method không tự bảo đảm an toàn; SQL và mọi đường gọi phải thực sự giữ điều kiện tương ứng.

### 6.1. Ràng buộc tham chiếu ghép

Schema minh họa sau chỉ tập trung vào việc assignment không liên kết nhầm membership và role khác tenant:

```sql
CREATE TABLE tenant_membership (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    subject_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, subject_id)
);

CREATE TABLE tenant_role (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    role_code VARCHAR(128) NOT NULL,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE tenant_role_assignment (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    membership_id UUID NOT NULL,
    role_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES tenant_membership (tenant_id, id),
    FOREIGN KEY (tenant_id, role_id)
        REFERENCES tenant_role (tenant_id, id)
);
```

Các ràng buộc trạng thái, thời hạn, chống assignment trùng và lịch sử cần bổ sung theo mô hình cụ thể. Đoạn schema không phải toàn bộ thiết kế quản lý quyền.

Khóa ngoại ghép bảo vệ quan hệ dữ liệu cùng tenant. Nó không chứng minh người gọi được gán role, role nằm dưới trần quyền hay thay đổi không vi phạm phân tách nhiệm vụ.

### 6.2. Join cũng phải giữ tenant

```sql
SELECT a.id, m.subject_id, r.role_code
FROM tenant_role_assignment a
JOIN tenant_membership m
  ON m.tenant_id = a.tenant_id
 AND m.id = a.membership_id
JOIN tenant_role r
  ON r.tenant_id = a.tenant_id
 AND r.id = a.role_id
WHERE a.tenant_id = :activeTenantId;
```

Đây là ví dụ join theo quyền sở hữu, chưa phải toàn bộ quyết định cấp quyền. Các dấu `:` biểu diễn tham số bind của lớp truy cập dữ liệu.

## 7. API quản trị phải giới hạn cả hành động lẫn trường được sửa

Một endpoint có thể nhận:

```http
POST /tenants/tenant-a/members/member-123/role-assignments
Authorization: Bearer <access-token>
Idempotency-Key: 6a7277d4-e0ac-40cb-a5f4-322bc19d306f
Content-Type: application/json

{
  "roleId": "role-456",
  "expectedAuthorizationRevision": 28,
  "reason": "Phân công xử lý hồ sơ của đơn vị"
}
```

Server tự xác định tenant từ ngữ cảnh đã kiểm tra, người cấp từ danh tính và phạm vi được phép từ policy. Một `roleId` đúng cú pháp vẫn phải được tra trong catalog và khung quyền hợp lệ.

Không map trực tiếp body vào entity có các trường như:

```text
tenant_id
is_platform_admin
global_permissions
identity_provider_owner
mandatory_audit_enabled
```

DTO chỉ chứa các trường thuộc hợp đồng action. Có thể từ chối các trường nhạy cảm không được hỗ trợ để phát hiện request sai, nhưng chỉ bỏ qua trường lạ không thay thế kiểm tra quyền trên những trường hợp lệ.

### 7.1. Tách hành động đổi nội dung và đổi quyền sở hữu

Quyền sửa hồ sơ không bao gồm chuyển hồ sơ sang tenant khác, đổi chủ sở hữu bảo mật hoặc sửa ACL. Chuyển tenant là quy trình đặc biệt vì có thể ảnh hưởng dữ liệu liên quan, lịch sử, tài nguyên và nghĩa vụ nghiệp vụ.

Tương tự, quyền đổi tên role không tự bao gồm sửa hierarchy hoặc permission của role đó.

## 8. Ví dụ Java: gán role dưới trần quản trị tenant

### 8.1. Giả định

Ví dụ dùng Spring transaction và cơ sở dữ liệu chung cho trạng thái quản trị cục bộ, membership, role, assignment, audit và outbox.

- Context tenant được tạo sau xác thực và kiểm tra lựa chọn tenant, không do body tự tạo.
- Mọi thay đổi quyền cục bộ liên quan khóa bản ghi đầu trạng thái an ninh của tenant theo cùng giao thức.
- Role resolver tính quyền hiệu lực đầy đủ, gồm hierarchy và nguồn cần thiết.
- Những thay đổi đặc biệt có thể cần phê duyệt độc lập gắn với kế hoạch cụ thể.
- Ví dụ không tạo transaction nguyên tử với IAM hoặc dịch vụ ngoài.

### 8.2. Service minh họa

Các repository, policy và kiểu dữ liệu cần được triển khai. Constructor injection được lược bỏ; đoạn mã thể hiện thiết kế chứ không phải ứng dụng độc lập.

```java
@Service
public class TenantRoleAdministrationService {
    private final TenantSecurityStateRepository securityStates;
    private final TenantMembershipRepository memberships;
    private final TenantRoleRepository roles;
    private final TenantAuthorizationSnapshotLoader snapshots;
    private final TenantRoleGrantPlanner grantPlanner;
    private final TenantAdministrationPolicy administration;
    private final TenantAuthorityCeiling ceiling;
    private final SeparationOfDutiesPolicy separation;
    private final AdministrationChangeApproval approvals;
    private final IdempotencyRepository idempotency;
    private final SecurityAuditRepository audits;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public TenantRoleGrantReceipt assignRole(
            VerifiedActor actor,
            VerifiedTenantContext tenantContext,
            AssignTenantRoleCommand command) {

        actor.requireAuthenticated();
        tenantContext.requireBoundTo(actor);
        command.validateSyntaxAndLimits();

        TenantId tenantId = tenantContext.tenantId();
        TenantSecurityHead head = securityStates.lockForUpdate(tenantId);

        TenantMembership operator = memberships.requireActive(
                tenantId, actor.canonicalSubjectId());
        administration.requireRoleAssignmentAuthority(
                actor, operator, head);

        TenantMembership target = memberships.findByTenantAndId(
                tenantId, command.targetMembershipId())
            .orElseThrow(TenantMemberNotFoundException::new);

        CommandScope keyScope = new CommandScope(
                tenantId, target.id(), actor.canonicalSubjectId(),
                "ASSIGN_TENANT_ROLE", command.idempotencyKey());
        String fingerprint = fingerprints.forTenantRoleGrant(command);

        var previous = idempotency.find(keyScope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        if (head.revision() != command.expectedAuthorizationRevision()) {
            throw new StaleTenantAuthorizationException();
        }

        TenantRole role = roles.findLocalRoleByTenantAndId(
                tenantId, command.roleId())
            .orElseThrow(TenantRoleNotFoundException::new);

        TenantAuthorizationSnapshot before = snapshots.loadComplete(
                tenantId, head.revision());
        before.requireValidAndComplete();

        TenantRoleGrantPlan plan = grantPlanner.propose(
                actor, target, role, command, before);
        plan.requireNewAssignment();
        plan.requireOnlyTenantScopedChanges(tenantId);

        ceiling.requireEffectiveCapabilitiesWithinTenantEnvelope(
                actor, operator, target, plan);
        separation.requireAllowed(actor, target, plan);
        approvals.requireSatisfiedWhenNeeded(
                actor, command.approvalReference(),
                plan.digest(), head.revision());

        grantPlanner.apply(plan);

        long newRevision = Math.addExact(head.revision(), 1);
        int changed = securityStates.advanceRevision(
                tenantId, head.revision(), newRevision);
        if (changed != 1) {
            throw new ConcurrentTenantSecurityChangeException();
        }

        audits.appendTenantRoleAssigned(
                actor, tenantContext, plan, newRevision);
        outbox.appendTenantAuthorizationChanged(
                UUID.randomUUID(), tenantId, target.id(), newRevision);

        TenantRoleGrantReceipt receipt = new TenantRoleGrantReceipt(
                tenantId, plan.assignmentId(), target.id(), newRevision);
        idempotency.insert(keyScope, fingerprint, receipt);
        return receipt;
    }
}
```

Các dependency `final` phải được khởi tạo qua constructor. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý để annotation có hiệu lực, và các repository phải tham gia đúng transaction manager.

Tên `VerifiedTenantContext` không tự tạo bảo đảm bảo mật. Đường xây dựng context và cách truyền nó giữa các lớp phải được bảo vệ; không deserialize trực tiếp kiểu đó từ JSON rồi bỏ kiểm tra.

`requireActive()` phải dùng dữ liệu và thời gian phù hợp theo hợp đồng kiểm tra quyền, không chỉ tin role trong một token cũ. Nếu role hoặc membership đến từ nguồn ngoài có độ trễ, giới hạn nhất quán đó phải được xác định rõ.

`ceiling` cần xem các năng lực thực sự được mở sau thay đổi. `separation` bảo vệ những tổ hợp hoặc trường hợp tự cấp quyền bị cấm. Nếu cần phê duyệt, người yêu cầu không được tự đáp ứng điều kiện độc lập bằng cùng một danh tính.

### 8.3. Idempotency có phạm vi tenant

Ví dụ dùng phạm vi gồm tenant, membership đích, chủ thể quản trị, action và key. Cùng chuỗi key ở tenant khác không được trả nhầm receipt hoặc tái sử dụng kế hoạch của tenant trước.

Kiểm tra quyền hiện tại xảy ra trước khi trả receipt cũ. Key không phải thông tin xác thực. Replay trả lại kết quả của thay đổi đã commit, không tạo một assignment mới hoặc diễn giải lại role theo một kế hoạch khác.

## 9. Quản trị membership không phải quản trị danh tính toàn cục

Một người dùng có thể thuộc A và B. Quản trị viên A thường được phép thay membership của người đó trong A, không được vì thế:

- Xóa tài khoản toàn cục của người dùng.
- Thu hồi membership trong B.
- Thay email đăng nhập hoặc credential toàn cục theo một đường không được cấp.
- Đặt lại yếu tố xác thực để chiếm một danh tính có quyền ở nơi khác.

Cần tách rõ thao tác “loại khỏi tenant A” và “xóa danh tính khỏi nền tảng”. Nếu có một chức năng quản lý danh tính đặc biệt, nó phải có miền thẩm quyền và bằng chứng riêng.

### 9.1. Lời mời và liên kết tài khoản

Lời mời vào tenant cần ràng buộc tenant, vai trò hoặc phạm vi được phép, hạn dùng và chủ thể nhận theo giao thức của hệ thống.

Không để sửa tenant ID trong lời mời làm thay đổi nơi được tham gia. Không dùng một địa chỉ email do bên gửi tự khai để liên kết ngay với tài khoản có sẵn mà thiếu bước chứng minh quyền kiểm soát hoặc điều kiện liên kết cần thiết.

Việc mời một người vào A không chuyển người đó từ B sang A. Đây là một membership mới, không phải sửa quyền sở hữu của một danh tính toàn cục.

## 10. SSO, group mapping và quyền gián tiếp

Quản trị nguồn danh tính có thể mạnh hơn việc sửa một role trực tiếp. Nếu tenant admin kiểm soát nhà cung cấp danh tính, mapping nhóm hoặc cơ chế khôi phục, họ có thể ảnh hưởng ai được hệ thống coi là người có quyền.

Những ràng buộc quan trọng gồm:

- Cấu hình nguồn danh tính phải gắn với đúng tenant và bên phát hành được chấp nhận.
- Claim về nhóm hoặc role phải được ánh xạ vào khung quyền cục bộ được cho phép.
- Không cho một claim như `platform_admin` từ nguồn của tenant tự tạo quyền nền tảng.
- Không tự coi email trùng chuỗi là đủ để chuyển quyền kiểm soát một danh tính đã tồn tại.
- Thay đổi issuer, mapping hoặc cơ chế khôi phục cần được đánh giá theo tác động đến quyền hiệu lực.

### 10.1. Ranh giới đặc biệt với người duyệt được bảo vệ

Giả sử tổ chức yêu cầu tenant admin không được tự trở thành người duyệt chi. Chỉ chặn endpoint tự gán role là chưa đủ nếu họ vẫn được:

```text
đổi nguồn xác thực của người duyệt
đặt lại credential hoặc MFA của người duyệt
liên kết tài khoản mình với danh tính người duyệt
thêm mình vào nhóm ngoài được mapping thành người duyệt
```

Cần đặt các đường đó dưới cơ chế quản trị phù hợp với yêu cầu độc lập. Nếu vẫn chủ động giao tenant admin toàn bộ quyền kiểm soát danh tính của nhóm người duyệt, phải thừa nhận quyền gián tiếp tương ứng; không mô tả một giới hạn chỉ tồn tại trên giao diện phân role như một bảo đảm mạnh hơn.

## 11. Cấu hình tenant cũng là một bề mặt cấp quyền

### 11.1. Policy nghiệp vụ

Các trường như hạn mức duyệt, số người duyệt hoặc quyền bỏ qua một bước có thể thay đổi trực tiếp khả năng thực hiện giao dịch.

Server cần xác định trường nào tenant được sửa, phạm vi giá trị nào hợp lệ và thay đổi nào cần phê duyệt độc lập. Không chỉ kiểm tra JSON đúng schema rồi áp dụng toàn bộ như chính sách có thẩm quyền.

Ví dụ, tenant được chọn hạn mức trong một khoảng không có nghĩa được đặt một giá trị cực lớn để vô hiệu hóa bước kiểm soát bắt buộc. Số tiền và giá giao dịch cũng phải dựa trên dữ liệu được server quản lý theo hợp đồng nghiệp vụ.

### 11.2. Webhook và tích hợp

Quyền cấu hình webhook không phải quyền yêu cầu server gửi request tùy ý đến mọi địa chỉ hoặc dùng mọi credential của nền tảng.

Cần giới hạn loại tích hợp, credential theo tenant, dữ liệu được gửi, đích được phép theo chính sách và quyền truy cập mạng của bộ thực thi. Không để một cấu hình hợp lệ ở UI biến service có đặc quyền thành trung gian truy cập ngoài phạm vi tenant.

Callback phải được xác thực và liên kết với integration cùng đối tượng đã đăng ký. Không lấy `tenantId` trong payload làm bằng chứng duy nhất để chọn dữ liệu cần cập nhật.

### 11.3. Audit, quota và tài nguyên chung

Tenant admin không được tắt ghi nhận bắt buộc chỉ vì có quyền sửa cấu hình tenant. Tương tự, quyền tạo export hoặc background job vẫn chịu quota và giới hạn công suất để một tenant không chiếm toàn bộ tài nguyên chung.

Các giới hạn này cần áp dụng ở đường thực thi và hàng đợi liên quan, không chỉ ở số lượng nút hoặc lựa chọn trên giao diện.

## 12. Background job, batch, export và lưu trữ

### 12.1. Ngữ cảnh tenant phải theo công việc đến cuối

Một job nên tham chiếu command hoặc đối tượng bền vững đã được nhận hợp lệ, cùng tenant nguồn và thông tin quy trách nhiệm cần thiết.

Worker không được chạy một truy vấn toàn cục chỉ vì dùng service account mạnh. Nó phải kiểm tra job, đối tượng đích và tenant khớp nhau theo nguồn đáng tin cậy.

Thiếu tenant trong message không nên được hiểu là chạy cho mọi tenant. Công việc toàn nền tảng phải dùng một loại command và thẩm quyền riêng.

### 12.2. Batch phải kiểm tra mọi phần tử

Một request có thể chứa membership hoặc resource ID thuộc nhiều tenant. Kiểm tra phần tử đầu tiên không cấp quyền cho phần còn lại.

Cần định nghĩa batch nguyên tử toàn bộ hay có kết quả từng phần, nhưng mỗi phần tử vẫn phải thỏa quyền theo tenant và bất biến tương ứng. Một phần tử trái phép không được âm thầm xử lý bằng credential của worker.

### 12.3. Export và object storage

Tên file, đường dẫn hoặc prefix tenant không tự là bằng chứng quyền sở hữu. Server phải xác định đối tượng lưu trữ nào thuộc export nào và ai được tải nó.

Nếu dùng URL tải có thời hạn, chỉ phát hành sau kiểm tra quyền và ràng buộc đúng đối tượng, phạm vi, hành động và hạn dùng theo cơ chế được chọn. Không cho tenant A chọn một object key của B rồi dùng dịch vụ ký để tạo đường tải.

## 13. Nhân viên hỗ trợ và chức năng thao tác thay

Hỗ trợ khách hàng đôi khi cần xem hoặc thao tác trong tenant. Đây là một đường riêng, không phải lý do để mọi endpoint tự bỏ qua tenant khi caller có một role nền tảng.

Một grant hỗ trợ có thể cần chỉ rõ:

```text
tenant đích
action được phép
đối tượng hoặc miền dữ liệu
thời hạn
lý do và tham chiếu yêu cầu hỗ trợ
cơ chế phê duyệt nếu cần
danh tính người thực sự thao tác
```

Nếu có chức năng thao tác thay người dùng, audit cần giữ cả actor gốc và danh tính hiệu lực. Không thay hoàn toàn actor gốc bằng người dùng đích rồi mất dấu ai đã thực hiện.

Hành động hỗ trợ cũng không tự đáp ứng điều kiện hai người độc lập hoặc phê duyệt nghiệp vụ. Nếu người hỗ trợ có thể tạo và duyệt thay hai tài khoản, cần có giới hạn hoặc kiểm soát phù hợp với chính sách độc lập.

Tenant admin không được tự phát hành grant hỗ trợ nền tảng hoặc đổi một request tenant thành request quản trị toàn cục bằng một header.

## 14. Concurrency, thu hồi và cache

### 14.1. Cấp role rồi sửa role để vượt trần

Một role có thể hợp lệ lúc gán nhưng sau đó được thêm permission nhạy cảm. Nếu chỉ kiểm tra trần khi gán, mọi thành viên đang giữ role có thể được mở quyền ngoài khung cho phép.

Vì vậy cần kiểm tra mọi thay đổi làm đổi quyền hiệu lực: permission, hierarchy, membership, group mapping, phạm vi hoặc cơ chế ủy nhiệm. Thay một nguồn nền có thể tác động nhiều người gián tiếp.

### 14.2. Hai thay đổi quản trị chạy đồng thời

Ví dụ một transaction duyệt kế hoạch gán role trong lúc transaction khác đổi hierarchy hoặc thu hẹp khung quản trị của tenant.

Cần một giao thức giữ snapshot, version hoặc khóa phù hợp. Ví dụ service ở trên dùng bản ghi đầu trạng thái an ninh tenant; các đường thay đổi liên quan phải cùng tuân thủ thì kiểm tra mới có ý nghĩa.

Một approval reference gắn với kế hoạch cũ không được dùng sau khi nội dung role hoặc revision đã khác. Phải đánh giá lại thay vì chỉ xác nhận mã phê duyệt có tồn tại.

### 14.3. Cache và token không được trộn tenant

Khóa cache cần bao gồm những thành phần quyết định phạm vi như chủ thể, tenant, membership, action hoặc revision theo mô hình. Cùng user hoặc cùng tên role không đủ.

Thu hồi membership ở A không tự sửa token đã phát hành, và không có nghĩa thu hồi membership ở B. Cần hợp đồng thu hồi phù hợp với cách service dùng token và nguồn quyền hiện tại.

Nếu một command đã được nhận hợp lệ trước thu hồi có hợp đồng tiếp tục riêng, phải phân biệt nó với một request mới dùng quyền cũ. Không tự thực hiện lại nghiệp vụ vì bối cảnh đăng nhập đã thay đổi.

## 15. Phòng vệ ở cơ sở dữ liệu và hạ tầng

Điều kiện tenant ở ứng dụng có thể được bổ sung bằng ràng buộc dữ liệu, phân quyền tài khoản cơ sở dữ liệu hoặc cơ chế lọc theo hàng nếu nền tảng hỗ trợ.

Những lớp này cần được thiết kế đúng với connection pool, transaction và đường quản trị. Một session cơ sở dữ liệu giữ ngữ cảnh tenant từ request trước có thể làm request sau chạy sai phạm vi nếu không được thiết lập và làm sạch theo giao thức phù hợp.

Không để tenant admin tự đặt ngữ cảnh bảo mật của kết nối bằng câu SQL tùy ý. Cũng cần hiểu những tài khoản đặc quyền hoặc đường quản trị có thể không chịu cùng bộ lọc như tài khoản ứng dụng.

Tenant isolation ở tầng dữ liệu không thay thế kiểm tra action và trần quản trị. Một quản trị viên chỉ sửa dữ liệu A vẫn có thể phá quy tắc phê duyệt của A nếu được phép sửa những trường bảo vệ không đúng thẩm quyền.

Ngược lại, policy ứng dụng đúng cũng không ngăn được một tài khoản cơ sở dữ liệu toàn cục bị trao trực tiếp cho quản trị viên tenant. Ranh giới cần được giữ trên toàn bộ đường truy cập, gồm công cụ hỗ trợ và vận hành.

## 16. Audit và dấu hiệu vượt ranh giới

Audit của một thay đổi quản trị nên cho biết:

- Actor thật, chủ thể chuẩn hóa và actor hiệu lực nếu có thao tác thay.
- Tenant đang thao tác và tenant sở hữu các đối tượng liên quan.
- Action, target membership, role hoặc cấu hình được thay đổi.
- Revision trước và sau, kế hoạch hoặc tập permission hiệu lực chịu tác động.
- Approval reference, lý do và kết quả kiểm tra trần thẩm quyền nếu cần.
- Command ID và idempotency reference để liên kết retry.

Không ghi access token, link lời mời có bí mật, credential SSO hoặc secret webhook nguyên văn. Tên tenant, tên role và lý do do người dùng nhập phải được xử lý an toàn khi hiển thị trong công cụ audit.

| Tín hiệu | Điều cần điều tra |
| --- | --- |
| Admin A liên tục dùng ID đối tượng của B | Có thể dò ID hoặc có lỗi xây dựng tenant context |
| Tạo role nhận permission hệ thống được bảo vệ | Có thể đang thử nâng quyền qua hierarchy |
| Thay SSO hoặc mapping trước khi gán quyền nhạy cảm | Cần xem tác động gián tiếp đến danh tính và phân tách nhiệm vụ |
| Request thiếu tenant nhưng chạm dữ liệu rộng | Có thể tồn tại đường mặc định toàn cục |
| Worker xử lý job khác tenant của command gốc | Có thể mất ràng buộc ở ranh giới queue |
| Cache trả receipt hoặc dữ liệu của tenant khác | Có thể khóa cache thiếu phạm vi |
| Tắt audit hoặc tăng hạn mức ngoài khung | Cấu hình cục bộ có thể đang vượt trần quản trị |
| Dùng quyền hỗ trợ ngoài tenant hoặc thời hạn được cấp | Ranh giới công cụ hỗ trợ có thể bị phá |

Kết quả bị từ chối không nên tiết lộ quá mức việc đối tượng tenant khác có tồn tại. Chọn chính sách phản hồi nhất quán; mã HTTP tự nó không thay thế việc không truy cập hoặc thay đổi dữ liệu trái phép.

## 17. Kiểm thử ranh giới quản trị tenant

### 17.1. Kiểm thử đối tượng và trường dữ liệu

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Admin A gọi URL quản trị B | Không dùng được role A trong B |
| URL tenant A nhưng member ID thuộc B | Không đọc hoặc sửa membership B |
| Membership thuộc A nhưng role ID thuộc B | Không tạo assignment khác tenant |
| Hai tenant đều có role code `ADMIN` | Không nhầm thành một quyền toàn cục |
| Body thêm `isPlatformAdmin`, `tenantId` hoặc permission nền tảng | Không làm thay đổi quyền ngoài hợp đồng |
| Request bỏ tenant hoặc gửi tenant rỗng | Không rơi về quyền toàn hệ thống |
| Người dùng thuộc cả A và B, chỉ quản trị A | Chuyển active tenant không mang quyền quản trị sang B |
| Xóa thành viên khỏi A | Không xóa danh tính toàn cục hoặc membership B |

### 17.2. Kiểm thử các đường nâng quyền gián tiếp

1. Tạo role mới nhận kế thừa từ role hoặc permission nền tảng được bảo vệ.
2. Gán một role hợp lệ rồi sửa role để thêm năng lực vượt trần.
3. Tự cấp role nghiệp vụ nhạy cảm hoặc tự đáp ứng điều kiện phê duyệt thay đổi khi chính sách cấm.
4. Đổi group mapping thành một năng lực nhạy cảm ngoài khung cho phép.
5. Thay SSO, liên kết tài khoản hoặc khôi phục danh tính để tiếp cận người duyệt được bảo vệ.
6. Sửa cấu hình để tắt audit, bỏ bước duyệt hoặc vượt hạn mức bắt buộc.
7. Dùng webhook hoặc tích hợp để yêu cầu service truy cập ngoài phạm vi được cấp.
8. Dùng tên role, header hoặc claim của nguồn tenant để yêu cầu quyền nền tảng.

Mỗi test cần có kỳ vọng theo mô hình thẩm quyền thực sự. Nếu đã chủ động trao tenant admin khả năng kiểm soát toàn bộ nguồn danh tính của một nhóm, không viết test chỉ kiểm tra endpoint role rồi kết luận nhóm đó được bảo vệ độc lập trước admin.

### 17.3. Kiểm thử worker, batch và dữ liệu đầu ra

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Batch gồm ID của A và B | Mỗi phần tử được kiểm tra, không dựa vào phần tử đầu |
| Job của A tham chiếu đối tượng B | Không thực thi trên B bằng quyền rộng của worker |
| Message thiếu tenant | Không được hiểu là lệnh chạy toàn nền tảng |
| Callback giả tenant trong payload | Không đổi phạm vi integration đã xác thực |
| Admin A yêu cầu ký URL cho object B | Không phát hành đường tải ngoài quyền |
| Cùng key idempotency dùng ở hai tenant | Không lẫn receipt hoặc kế hoạch giữa hai phạm vi |
| Export hoặc tìm kiếm | Không lộ dữ liệu, số lượng hoặc trường ngoài phạm vi theo hợp đồng |
| Quyền hỗ trợ hết hạn hoặc sai tenant | Không được tiếp tục thao tác mới bằng grant đó |

### 17.4. Kiểm thử concurrency và commit

Dùng transaction độc lập với barrier hoặc latch để điều khiển lịch, không dựa vào `sleep`.

```text
A. T1 chuẩn bị gán role, T2 đổi permission của role.
   Kết quả: commit không dùng một kế hoạch cũ để cấp năng lực vượt trần.

B. T1 gán quyền, T2 thu hồi quyền quản trị của người cấp.
   Kết quả: tuân theo điểm cấp quyền và giao thức đồng bộ đã định nghĩa,
   không dùng một snapshot ngoài hợp đồng nhất quán.

C. T1 sửa hierarchy, T2 thay group mapping cùng làm mở quyền gián tiếp.
   Kết quả: các bất biến về khung tenant và phân tách không bị bỏ qua.
```

Chèn lỗi ở bước ghi audit hoặc outbox bắt buộc để chứng minh assignment, revision và receipt không commit nửa vời. Mất response sau commit phải được phục hồi bằng cùng key mà không tạo thay đổi mới.

Kiểm tra thêm connection pool khi hai request của A và B dùng lại kết nối, cùng các công cụ import hoặc quản trị không đi qua controller chính. Mock repository không chứng minh được ràng buộc khóa ngoại, hành vi transaction và ngữ cảnh kết nối thực tế.

### 17.5. Kiểm tra bất biến xuyên tenant

Với một thao tác chỉ được cấp cho tenant A, đối chiếu trước và sau để chứng minh dữ liệu và quyền của tenant B không bị thay đổi bởi thao tác đó trong phạm vi các nguồn mà test kiểm soát.

Ngoài trạng thái chính, cần kiểm tra assignment, membership, cấu hình, outbox, job và file xuất. Một response từ chối không đủ nếu hệ thống đã tạo một tác vụ nền trái phép trước khi trả lỗi.

## 18. Bài tập thiết kế

Thiết kế quyền quản trị cho ứng dụng nhiều tenant có membership dùng chung danh tính toàn cục, role cục bộ, SSO theo tenant, tích hợp webhook và workflow phê duyệt khoản chi.

Hãy mô tả:

1. Tenant admin được quản lý những action và trường cấu hình nào, và trần nào không được sửa?
2. Tenant đang thao tác được xác định và kiểm tra ra sao khi một người thuộc nhiều tenant?
3. Những khóa ghép hoặc truy vấn nào bảo đảm membership, role và assignment cùng tenant?
4. Quyền tự cấp role, sửa hierarchy và đổi group mapping được giới hạn theo năng lực hiệu lực thế nào?
5. Nếu cần bảo vệ người duyệt trước tenant admin, những đường quản trị danh tính nào cũng phải tách riêng?
6. Worker, callback, export và URL tải giữ tenant context như thế nào?
7. Quyền hỗ trợ nền tảng được cấp ra sao và audit có giữ actor thật khi thao tác thay không?
8. Những test nào chứng minh một thao tác quản trị A không tạo thay đổi hoặc công việc nền ngoài phạm vi A?

Một thiết kế đạt yêu cầu phải giới hạn được cả quyền trực tiếp lẫn những con đường gián tiếp mà quản trị viên tenant có thể dùng, đồng thời giữ nguyên các bất biến nghiệp vụ và ranh giới của nền tảng tại mọi điểm thực thi.
