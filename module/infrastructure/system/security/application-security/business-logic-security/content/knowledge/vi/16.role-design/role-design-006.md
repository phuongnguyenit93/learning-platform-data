# Role removal policy — Chính sách gỡ và thu hồi vai trò

## 1. Gỡ role là làm mất một nguồn thẩm quyền

**Role removal policy** xác định khi nào phải gỡ một vai trò, ai được thực hiện, nguồn cấp nào bị thu hồi, thời điểm có hiệu lực và cách hệ thống ngăn quyền cũ tiếp tục được sử dụng.

Xóa một dòng khỏi bảng gán role chưa chắc làm người dùng mất quyền ngay. Quyền có thể còn trong token, session, cache, group, role kế thừa, grant trực tiếp hoặc công việc đã được đưa vào hàng đợi.

Bài thuộc chương **Role Design** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Trọng tâm là thu hồi quyền mà vẫn bảo vệ business invariants, quyền theo đối tượng, state machine, transaction, idempotency và bằng chứng kiểm toán.

Ví dụ xuyên suốt: An có role `PURCHASE_REVIEWER` tại project P1. Khi An chuyển nhiệm vụ, binding B1 phải được thu hồi. Hệ thống cần trả lời được:

- Có đang gỡ đúng binding B1, đúng người, đúng tenant/project không?
- An còn một đường cấp quyền approve khác tại P1 không?
- Token và session cũ được xử lý thế nào?
- Nếu An đang phê duyệt một đơn, thao tác đó được phép hoàn tất đến mốc nào?
- Các quyết định trước đây và công việc đã lên lịch có còn hiệu lực không?
- Bằng chứng nào xác nhận việc thu hồi đã thực sự được thực thi?

Mục tiêu không chỉ là cập nhật màn hình quản trị. Mục tiêu là thay đổi thẩm quyền hiệu lực theo một hợp đồng có thể kiểm chứng.

## 2. Phân biệt các thao tác thường cùng bị gọi là “xóa role”

| Thao tác | Đối tượng thay đổi | Điều không tự xảy ra |
| --- | --- | --- |
| Thu hồi một role binding | Quan hệ cấp role cho một principal trong một scope | Không tự thu hồi mọi grant khác của principal |
| Xóa người khỏi group | Một nguồn membership | Không tự xóa binding trực tiếp hoặc group khác |
| Gỡ permission khỏi role definition | Capability của các holder dùng definition đó | Không nhất thiết tác động tới version definition khác hoặc grant trực tiếp |
| Retire một role definition | Khả năng tiếp tục cấp/sử dụng một role theo policy vòng đời | Không tự hoàn tất fan-out hoặc thu hồi token ở mọi nơi |
| Khóa principal hoặc tenant membership | Quyền tham gia hệ thống/phạm vi | Không tự hoàn tác tác dụng nghiệp vụ đã commit |
| Logout hoặc vô hiệu session | Một hoặc nhiều phiên | Không mặc nhiên vô hiệu mọi credential ở ứng dụng khác |
| Thu hồi token | Credential hoặc authorization grant liên quan | Không tự xác định toàn bộ quyền object hiện tại |

Phải ghi rõ thao tác đang làm. API `removeRole(userId, roleName)` sẽ mơ hồ nếu cùng người có role đó từ nhiều nguồn và nhiều project.

Một API thu hồi binding nên nhận ID ổn định của binding và xác minh tenant, principal, scope từ dữ liệu server. Nếu nghiệp vụ yêu cầu “ngừng mọi khả năng approve của An tại P1”, đó là yêu cầu rộng hơn: cần xác định và xử lý mọi đường cấp phù hợp, hoặc áp dụng một lệnh cấm/khóa có semantics rõ.

### 2.1. Thu hồi nguồn không đồng nghĩa thu hồi capability hiệu lực

An có thể nhận approve qua:

```text
B1: role reviewer được cấp trực tiếp tại P1
B2: group FinanceReviewers được bind role tại P1
G3: grant approve trực tiếp trên một đơn cụ thể
```

Thu hồi B1 chỉ làm B1 không còn đóng góp quyền. B2 hoặc G3 có thể vẫn cho phép cùng action. Hệ thống không được báo “đã mất mọi quyền approve” nếu mới xử lý một nguồn.

Điều này không có nghĩa B2/G3 phải luôn bị xóa cùng B1. Nó có nghĩa mục tiêu thu hồi và kết quả quyền hiệu lực phải được phân biệt để tránh xử lý quá ít hoặc quá rộng.

## 3. Định nghĩa chính sách trước khi triển khai

### 3.1. Khi nào cần gỡ role?

Các trigger thường gặp là thay đổi nhiệm vụ, chuyển project/tenant, kết thúc ủy quyền, hết thời hạn, principal bị vô hiệu, rà soát phát hiện cấp thừa hoặc phát hiện sự cố cần ngăn truy cập.

Phân biệt thu hồi thông thường và thu hồi khẩn cấp. Trường hợp thông thường có thể cần chuyển giao công việc; trường hợp khẩn cấp có thể cần chặn trước rồi xử lý backlog. Không để quy tắc chuyển giao vô tình buộc phải giữ quyền nhạy cảm của một tài khoản đang bị nghi ngờ.

Rà soát và thu hồi quyền không còn cần thiết giúp tránh quyền tích lũy vượt nhiệm vụ hiện tại. Đây là một phần của kiểm soát quyền tối thiểu và privilege creep được OWASP đề cập. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 3.2. Một policy cần trả lời những gì?

| Nội dung | Quyết định cần có |
| --- | --- |
| Mục tiêu | Thu hồi một nguồn, một capability trong scope hay khóa toàn principal? |
| Thẩm quyền | Ai được gỡ binding nào, trong phạm vi nào, có được gỡ role của chính mình không? |
| Thời điểm hiệu lực | Tính từ commit tại nguồn, lúc điểm thực thi quan sát thay đổi hay một mốc khác? |
| Yêu cầu đang chạy | Kiểm tra tại lúc chấp nhận, tại điểm ghi hay cả trước tác dụng bên ngoài? |
| Credential và cache | Cần vô hiệu gì, kiểm tra độ mới bằng cơ chế nào? |
| Công việc tồn đọng | Reassign, hủy, tạm dừng hay tiếp tục bằng quyền service được định nghĩa riêng? |
| Quyết định lịch sử | Giữ sự thật đã xảy ra; có cần vô hiệu quyền sử dụng kết quả chưa thực thi không? |
| Bằng chứng | Actor, binding, lý do, version, thời điểm và trạng thái lan truyền nào được lưu? |
| Lỗi hạ tầng | Khi không xác minh được độ mới, action nào phải dừng? |

### 3.3. Mẫu invariant cho ví dụ

```text
Sau khi B1 được thu hồi tại nguồn có thẩm quyền,
B1 không được đóng góp grant cho quyết định mới
ngoài cửa sổ độ trễ đã được policy cho phép.

Với đường ghi nhạy cảm dùng cơ chế tuần tự hóa ở phần sau:
không có transaction nghiệp vụ dựa vào B1 cũ
commit sau transaction thu hồi B1 đã commit.

Thu hồi B1 không sửa lại lịch sử quyết định đã commit.

Retry cùng thao tác thu hồi không hồi sinh binding,
không tạo thêm lần thay đổi thẩm quyền và không đổi mốc gốc.
```

Invariant thứ hai chỉ áp dụng cho các operation thực sự tham gia giao thức chung. Nó không mặc nhiên bao phủ service bên ngoài, đường đọc dùng cache hoặc một tác dụng đã được chấp nhận trước đó và đang chờ giao.

## 4. Xác định mốc hiệu lực và cam kết độ trễ

### 4.1. Không dùng một nhãn “thành công” cho mọi giai đoạn

Có ít nhất ba mốc:

1. **Đã nhận yêu cầu:** hệ thống nhận lệnh thu hồi nhưng có thể chưa ghi thay đổi tại nguồn.
2. **Đã ghi tại nguồn:** binding chuyển trạng thái và version quyền được commit bền vững.
3. **Đã đáp ứng cam kết thực thi:** những đường truy cập thuộc hợp đồng đã chặn quyền cũ hoặc đã được xác nhận ở version phù hợp.

Nếu API chỉ đưa việc thu hồi vào hàng đợi, phản hồi phải thể hiện còn chờ xử lý. Nếu API xác nhận nguồn đã cập nhật, không mô tả rộng thành mọi token và mọi node đã biết nếu chưa có cơ chế chứng minh điều đó.

### 4.2. Hai loại cam kết phổ biến

- **Có giới hạn độ trễ:** quyền cũ có thể còn được dùng trong cửa sổ tối đa đã định nghĩa, sau đó điểm thực thi phải có dữ liệu đủ mới hoặc không được tiếp tục cho phép.
- **Tuần tự hóa với đường ghi nhạy cảm:** thu hồi và action dùng cùng hàng rào kiểm soát; thứ tự commit tạo ranh giới rõ như invariant ở phần trên.

Đối với cam kết có giới hạn, một TTL đơn lẻ chưa đủ chứng minh thời gian toàn hệ thống. Cần tính các tầng token, cache, replica, phân phối event và cách xử lý khi node bị cô lập. Node vẫn cho phép bằng dữ liệu cũ vô hạn thì không có giới hạn thu hồi thực sự.

RFC 7009 cũng nêu khả năng có propagation delay giữa các server khi token bị thu hồi. Việc thu hồi role nội bộ cần hợp đồng riêng, không tự có bảo đảm toàn cục chỉ vì có endpoint revoke token. [RFC 7009: OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1).

### 4.3. Request đến trước chưa chắc được thực thi trước

Một request phê duyệt đến API trước yêu cầu thu hồi nhưng còn chờ khóa không nên được cho qua chỉ nhờ timestamp đến sớm, trừ khi policy thực sự định nghĩa như vậy và có cơ chế bảo vệ tương ứng.

Trong mô hình transaction của bài, thứ tự được quyết định bằng khóa tại nguồn quyền và commit, không dựa vào thời gian client tự khai hoặc thứ tự gói tin tới load balancer.

## 5. Token, session và cache giữ lại quyền như thế nào?

### 5.1. Credential hợp lệ chưa chắc chứa quyền hiện tại

Một access token có chữ ký hợp lệ có thể chứa snapshot role tại lúc phát hành. Resource server chỉ xác minh chữ ký và hạn token sẽ không tự biết binding đã bị thu hồi sau đó.

Đổi role trong database không sửa được byte của token đang nằm ở client. Cần cơ chế kiểm tra hiệu lực hoặc độ mới phù hợp, đồng thời xác định có chấm dứt session, chặn refresh hay thu hồi cả credential liên quan không.

| Cơ chế | Tác dụng | Giới hạn cần thiết kế |
| --- | --- | --- |
| Vô hiệu session server-side | Chặn phiên đã được quản lý tại server đó | Không tự bao phủ mọi access token hoặc ứng dụng khác |
| Thu hồi refresh token/grant | Ngăn tiếp tục dùng nguồn refresh đã bị thu hồi | Xử lý access token liên quan tùy cơ chế/cascade; không giả định mọi resource server tự biết |
| Access token ngắn hạn | Giảm thời gian tồn tại của snapshot cũ nếu kiểm tra expiry đúng | Không phải thu hồi tức thì trước expiry |
| Introspection | Hỏi trạng thái token từ authorization server | Cache có thể cũ; token active không tự chứng minh mọi role/object permission hiện tại |
| Denylist hoặc version/epoch check | Phát hiện credential/snapshot không còn được chấp nhận | Mọi đường liên quan phải kiểm tra nguồn đủ mới |
| Event invalidation | Làm cache biết có thay đổi sớm hơn | Có thể trễ/mất/trùng/lệch thứ tự; cần phục hồi và đối soát |

RFC 7662 nêu rõ cache kết quả introspection tạo đánh đổi giữa tải hệ thống và cửa sổ sử dụng thông tin token đã cũ; kết quả có `exp` không được cache vượt mốc đó. Đây vẫn không thay thế kiểm tra quyền nghiệp vụ hiện tại. [RFC 7662: Security Considerations](https://www.rfc-editor.org/rfc/rfc7662.html#section-4).

### 5.2. Epoch trong token chỉ hữu ích khi được đối chiếu

Giả sử principal có `authz_epoch = 7`, sau thu hồi tăng thành 8. Token hoặc cache ghi epoch 7 chỉ bị phát hiện cũ nếu điểm thực thi so với epoch hiện tại theo cơ chế đủ tin cậy.

Đặt thêm claim `authz_epoch` nhưng không kiểm tra, hoặc so với một bản epoch cũ không có giới hạn độ mới, không tạo ra khả năng thu hồi tức thì.

Epoch nên tăng đơn điệu trong phạm vi đã chọn, ví dụ principal–tenant. Không reset epoch về 0 khi xóa rồi tạo lại tài khoản, và không tái sử dụng một principal ID khiến credential cũ có thể khớp lại một thế hệ mới.

### 5.3. Xử lý event trùng và lệch thứ tự

Một event thu hồi ở epoch 8 có thể đến sau event cấp mới ở epoch 9. Không áp dụng event cũ bằng cách ghi đè projection mới hoặc làm binding cũ sống lại.

Có thể dùng epoch như tín hiệu vô hiệu cache rồi đọc lại snapshot quyền hiện tại. Nếu projection áp dụng delta, nó phải có thứ tự/version và cơ chế phát hiện khoảng trống. Chỉ nhận epoch lớn nhất rồi bỏ mọi delta cũ có thể làm mất một thay đổi thu hồi chưa từng được áp dụng.

Event và cache hỗ trợ phân phối; nguồn có thẩm quyền, tombstone và giao thức độ mới mới xác định quyền nào còn dùng được.

## 6. Mô hình dữ liệu thu hồi có version và dấu vết

### 6.1. Giữ binding bị thu hồi thay vì tái sử dụng nó

Một binding có thể đi từ `ACTIVE` sang `REVOKED`. Nếu sau này cần cấp lại cùng role/scope, tạo binding mới với ID mới và bằng chứng cấp mới, không xóa `revoked_at` của B1 để hồi sinh nó.

Cách đó phân biệt được hai lần cấp, chống event cũ tác động nhầm lần cấp mới và giữ khả năng giải thích quyết định lịch sử.

### 6.2. Schema PostgreSQL phần lõi

```sql
CREATE TABLE principal_authz_guard (
    tenant_id     uuid NOT NULL,
    principal_id  uuid NOT NULL,
    epoch         bigint NOT NULL DEFAULT 0 CHECK (epoch >= 0),
    PRIMARY KEY (tenant_id, principal_id)
);

CREATE TABLE role_binding (
    tenant_id          uuid NOT NULL,
    id                 uuid NOT NULL,
    principal_id       uuid NOT NULL,
    role_code          varchar(128) NOT NULL,
    scope_json         jsonb NOT NULL,
    constraints_json   jsonb NOT NULL,
    state              varchar(16) NOT NULL,
    binding_version    bigint NOT NULL DEFAULT 0,
    valid_from         timestamptz NOT NULL,
    valid_until        timestamptz,
    revoked_at         timestamptz,
    revoked_by         uuid,
    revocation_reason  varchar(128),
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, principal_id)
        REFERENCES principal_authz_guard (tenant_id, principal_id),
    CHECK (state IN ('ACTIVE', 'REVOKED')),
    CHECK (binding_version >= 0),
    CHECK (valid_until IS NULL OR valid_until > valid_from),
    CHECK (
        (state = 'ACTIVE' AND revoked_at IS NULL AND revoked_by IS NULL)
        OR
        (state = 'REVOKED' AND revoked_at IS NOT NULL AND revoked_by IS NOT NULL)
    )
);
```

Đây là phần lõi minh họa cho binding trực tiếp trong một database; role catalog, audit, outbox và kho idempotency là thành phần bổ sung của hệ thống.

`ACTIVE` vẫn phải được kiểm tra thời gian hiệu lực. Một binding qua `valid_until` không được dùng chỉ vì job chưa đổi trạng thái. Bảng guard phải tồn tại theo vòng đời principal và không được âm thầm tạo lại với epoch ban đầu khi thiếu dữ liệu kiểm soát.

Giới hạn quyền ghi để tài khoản ứng dụng không tùy ý xóa tombstone, đổi principal/scope của binding đã chốt hoặc sửa lịch sử thu hồi. Các constraint chỉ hỗ trợ hình dạng dữ liệu; chúng không tự xác minh người gọi có quyền gỡ binding.

## 7. Tuần tự hóa thu hồi với thao tác nghiệp vụ nhạy cảm

### 7.1. Một hàng rào quyền dùng chung

Trong mô hình minh họa, mỗi principal–tenant có một hàng guard. Quy tắc:

1. Action nhạy cảm lấy **shared lock** trên guard trước khi đọc quyền hiện tại và giữ khóa đến khi transaction nghiệp vụ kết thúc.
2. Thu hồi binding lấy **exclusive lock** trên cùng guard, sửa binding, tăng epoch, ghi audit/outbox rồi commit.
3. Mọi thay đổi quyền nội bộ thuộc bảo đảm này phải tuân cùng giao thức. Đường nghiệp vụ đọc quyền từ nguồn có thẩm quyền sau khi giành khóa.

Với PostgreSQL, có thể dùng:

```sql
-- Đường thực thi nghiệp vụ, giữ khóa đến cuối transaction.
SELECT epoch
FROM principal_authz_guard
WHERE tenant_id = :tenant_id
  AND principal_id = :principal_id
FOR SHARE;

-- Đường thu hồi, cần khóa xung đột với đường thực thi.
SELECT epoch
FROM principal_authz_guard
WHERE tenant_id = :tenant_id
  AND principal_id = :principal_id
FOR UPDATE;
```

`FOR SHARE` xung đột với cập nhật/khóa độc quyền liên quan ở đây; không thay bằng `FOR KEY SHARE` rồi giả định nó chặn mọi cập nhật epoch. PostgreSQL mô tả rõ các mode row lock và quan hệ xung đột. [PostgreSQL: Row-Level Locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

Ví dụ giả định `READ COMMITTED`, đọc binding/quyền ở statement sau khi đã lấy guard, dùng nguồn primary và giữ khóa qua commit. Với isolation khác cần xử lý snapshot/serialization và retry toàn operation phù hợp.

### 7.2. Hai thứ tự hợp lệ

| Thứ tự | Kết quả |
| --- | --- |
| Action giữ shared lock trước | Thu hồi phải chờ. Action có thể commit theo quyền trước thu hồi; sau đó transaction thu hồi mới commit |
| Thu hồi giữ exclusive lock trước | Action phải chờ. Sau khi thu hồi commit, action đọc quyền mới; B1 không còn được dùng làm nguồn cho phép |

Vì shared lock được giữ đến commit, một action đã đọc quyền cũ không thể commit sau transaction thu hồi theo giao thức này: transaction thu hồi chưa lấy được exclusive lock khi action còn đang chạy.

Nếu còn B2 hợp lệ cấp cùng capability, action có thể được phép nhờ B2. Hàng rào không biến việc gỡ B1 thành lệnh cấm mọi đường cấp khác.

### 7.3. Phạm vi bảo đảm và chi phí

Transaction phải ngắn, không giữ guard trong khi chờ người dùng hoặc HTTP từ xa. Thu hồi có thể phải chờ action đang chạy; lock timeout là lỗi/chưa hoàn tất, không được báo đã thu hồi bền vững khi transaction chưa commit.

Với thay đổi ảnh hưởng nhiều principal như retire role hoặc sửa group chung, chỉ bump một guard không đủ. Cần hàng rào role/group thích hợp, khóa các phạm vi liên quan theo thứ tự thống nhất hoặc cơ chế tương đương. Fan-out còn đang chạy không được mô tả như đã thu hồi ở tất cả holder.

Nếu một quyết định dùng nhiều guard, hệ thống cần thứ tự khóa xác định và mode mạnh nhất cho cùng một khóa để tránh deadlock. Không tự trộn giao thức khác nhau giữa đường thu hồi, gán lại và đường thực thi.

## 8. Khung Java cho thao tác thu hồi binding

Ví dụ sau dùng `TransactionTemplate` của Spring. Các dependency và kiểu kết quả là hợp đồng minh họa, chưa phải chương trình hoàn chỉnh có thể chép chạy ngay.

```java
public RevocationReceipt revokeRoleBinding(
        RevokeBindingCommand cmd, TrustedActor operator) {

    return transactions.execute(tx -> {
        // Shared cho operator, exclusive cho target; cùng ID thì dùng exclusive.
        // Helper lấy các guard theo thứ tự xác định và giữ đến cuối transaction.
        guards.lockForRoleRemoval(
            operator.tenantId(), operator.principalId(), cmd.targetPrincipalId());

        RoleBinding binding = bindings.findByTenantPrincipalAndId(
            operator.tenantId(), cmd.targetPrincipalId(), cmd.bindingId());

        managementPolicy.requireCanRevoke(operator, binding);

        IdempotencyClaim claim = idempotency.claim(
            operator.tenantId(), operator.principalId(), "REVOKE_ROLE_BINDING",
            cmd.idempotencyKey(), fingerprints.revokeBinding(cmd));

        if (claim.isCompleted()) {
            return claim.originalReceipt();
        }

        if (binding.isRevoked()) {
            RevocationReceipt original = revocations.receiptFor(binding.id());
            idempotency.complete(claim, original);
            return original;
        }

        binding.requireExpectedVersion(cmd.expectedBindingVersion());
        removalRules.requireAllowed(operator, binding);

        Instant revokedAt = databaseClock.currentInstant();
        int changed = bindings.revokeIfActive(
            binding, operator.principalId(), revokedAt, cmd.reasonCode());

        if (changed != 1) {
            throw new ConcurrentRoleBindingChangeException();
        }

        long newEpoch = guards.incrementEpoch(
            binding.tenantId(), binding.principalId());

        RevocationReceipt receipt = revocations.appendSourceRevoked(
            binding, operator, newEpoch, revokedAt, cmd.reasonCode());

        outbox.appendRoleBindingRevoked(receipt);
        idempotency.complete(claim, receipt);
        return receipt;
    });
}
```

Các điều kiện bắt buộc phía sau ví dụ:

- `TrustedActor` đến từ xác thực đã kiểm chứng. Target principal, binding và scope được đối chiếu với dữ liệu server trong tenant có thẩm quyền; client không được chọn tenant khác bằng cách sửa body.
- `lockForRoleRemoval` giữ operator guard để các quyền quản trị nội bộ liên quan cũng có thể được kiểm tra nhất quán, đồng thời giữ target guard để ngăn action dựa trên quyền cũ. Tất cả writer trong bảo đảm này phải dùng cùng giao thức.
- `managementPolicy` kiểm tra đúng quyền thu hồi trên binding/scope cụ thể, không chỉ `isAdmin`. Replay ở API này yêu cầu thẩm quyền quản trị hiện tại theo policy đã chọn.
- Fingerprint gồm binding, target, version kỳ vọng và nội dung nghiệp vụ như lý do theo hợp đồng. Cùng key nhưng khác nội dung bị từ chối.
- Nếu binding đã bị thu hồi, kết quả gốc được tra trong đúng tenant/principal đã xác minh. Thao tác lặp không tăng epoch hoặc thay mốc thu hồi gốc chỉ để phục vụ retry.
- `revokeIfActive` kiểm tra tenant, ID, principal, state và binding version, tăng binding version một lần và phải thay đổi đúng một hàng.
- Binding, epoch, audit/receipt, outbox và kết quả idempotency cùng transaction. Lỗi ghi bất kỳ bước nào làm rollback toàn bộ; chỉ trả thành công sau khi transaction hoàn tất.
- Receipt xác nhận **nguồn binding đã bị thu hồi** và epoch mới. Nó không tự khẳng định mọi capability hiệu lực đã mất hoặc mọi kênh bất đồng bộ đã cập nhật.

Mô hình này không tự tạo transaction với identity provider bên ngoài. Nếu quyền operator/target còn đến từ nguồn ngoài, cần xác định độ mới và giao thức đồng bộ của nguồn đó; không chỉ dựa vào việc đã giữ một guard nội bộ.

## 9. Công việc đang chờ, quyết định cũ và tác dụng bên ngoài

### 9.1. Yêu cầu đang đợi reviewer

Gỡ reviewer có thể làm một vòng không còn người đủ điều kiện. Quy trình cần reassign, tạm dừng hoặc kết thúc theo policy. Không tự đưa requester vào làm reviewer để “tránh kẹt”.

Việc reassign là action riêng có quyền và audit. Nó không xóa maker history, không đổi nội dung đã xem và không hồi sinh quyết định cũ dưới danh tính reviewer mới.

### 9.2. Quyết định đã commit là sự thật lịch sử

Nếu An duyệt hợp lệ trước khi binding bị thu hồi, đừng sửa audit thành “An chưa từng có quyền” hoặc xóa decision để phù hợp trạng thái hiện tại.

Tuy nhiên, **hiệu lực tiếp tục sử dụng kết quả** có thể phụ thuộc policy:

- Cho phép giữ kết quả đã được chấp nhận trước khi thu hồi.
- Yêu cầu xét duyệt lại những kết quả chưa được thực thi.
- Vô hiệu có chọn lọc nếu thu hồi do phát hiện tài khoản bị chiếm hoặc quyết định có vấn đề.

Nếu vô hiệu, ghi action và lý do mới, liên kết quyết định gốc, cập nhật trạng thái/projection hiệu lực. Không làm mất sự thật rằng quyết định đã từng được hệ thống chấp nhận.

### 9.3. Job và outbox đã được commit trước đó

Một action commit trước thu hồi có thể đã tạo outbox phát hành đơn. Message được gửi sau thu hồi không tự vi phạm bảo đảm thứ tự commit ở phần trước; bảo đảm đó nói về transaction chấp nhận action tại nguồn.

Phải chọn rõ: ý định đã chấp nhận được tiếp tục bằng thẩm quyền service được giới hạn, hay phải kiểm tra lại trước tác dụng cuối. Nếu kiểm tra lại, nơi thực thi phải có nguồn quyền/hiệu lực đủ mới và cách hủy/bù trừ phù hợp.

Không biến một message chứa `requested_by = An` thành bằng chứng quyền còn hiệu lực. Cũng không bỏ qua một callback xác nhận tác dụng thật đã xảy ra chỉ vì role của An vừa bị gỡ; cần ghi nhận và đối soát sự thật đó.

### 9.4. Không hoàn tác được mọi thứ bằng thu hồi role

File đã tải, email đã gửi, đơn đã phát hành hoặc tác dụng ở hệ thống khác không tự biến mất khi role bị gỡ. Dừng quyền tương lai, hủy tác vụ còn chờ và bù trừ tác dụng đã xảy ra là các việc khác nhau.

Các bước bù trừ cần state machine, quyền và idempotency riêng. Retry lệnh hủy/thu hồi tài nguyên không được cộng trả tài nguyên hoặc tạo tác dụng bù trừ nhiều lần.

## 10. Trường hợp biên và quản trị vòng đời

### 10.1. Thu hồi quản trị viên cuối cùng

Một tenant có thể cần bảo đảm còn đường quản trị/phục hồi hợp lệ. Nếu có invariant “không mất người quản trị cuối”, phép `count(admins) > 1` ngoài transaction là chưa đủ: hai thao tác đồng thời có thể cùng thấy còn hai rồi gỡ hết.

Cần tuần tự hóa trên guard quản trị chung của tenant hoặc cơ chế isolation/constraint phù hợp, và xử lý retry. Đồng thời phải có quy trình độc lập cho tình huống tài khoản cuối cùng bị xâm nhập; không biến quy tắc duy trì khả năng quản trị thành lý do bắt buộc giữ một tài khoản nguy hiểm hoạt động.

### 10.2. Group hoặc đồng bộ có thể cấp lại quyền

Gỡ binding trực tiếp nhưng giữ một mapping group tự động có thể khiến role xuất hiện lại ở lượt đồng bộ kế tiếp. Cần xác định hệ thống nào là nguồn quản lý assignment và sửa đúng nguồn hoặc đặt suppression/deny theo policy rõ ràng.

Đối soát membership lồng nhau, role kế thừa, assignment theo chức danh và grant ủy quyền. Không chỉ kiểm tra đúng một bảng mà màn hình quản trị đang dùng.

### 10.3. Retire role definition

Ngừng cấp mới, thu hồi binding hiện tại và ngừng chấp nhận role version cũ là ba việc cần phối hợp. Xóa definition trước có thể làm mất khả năng giải thích audit hoặc khiến evaluator rơi vào nhánh xử lý thiếu cấu hình không an toàn.

Giữ định danh/version lịch sử theo chính sách lưu trữ, chặn cấp mới ở trạng thái thích hợp và migration/thu hồi holder có theo dõi. Definition không tìm thấy không được mặc định cho phép.

### 10.4. Regrant là lần cấp mới

An được giao lại nhiệm vụ sau này có binding B2 mới. Event thu hồi B1 đến trễ không được thu hồi nhầm B2 chỉ vì cùng role code. Ngược lại, event cấp B2 không được xóa tombstone của B1.

Mọi event phải có đúng aggregate ID, version/epoch và semantics đủ để consumer không nhầm hai vòng đời cấp quyền.

## 11. Giám sát và bằng chứng thu hồi

Audit của thao tác gỡ role nên có operator, target principal, tenant, binding ID, role definition/version, scope, lý do, trạng thái trước/sau, epoch mới, thời điểm ghi nhận và command/correlation ID.

Đường nghiệp vụ nhạy cảm nên ghi binding/epoch đã dùng để ra quyết định. Nhờ đó có thể đối chiếu action commit trước hay sau mốc thu hồi theo dữ liệu transaction, thay vì chỉ so hai timestamp từ máy khác nhau.

Những chỉ số hữu ích:

| Chỉ số | Điều cần xác minh |
| --- | --- |
| Thời gian từ yêu cầu tới commit nguồn | Có chờ khóa hoặc lỗi xử lý làm thu hồi chưa hoàn tất không? |
| Tuổi event thu hồi chưa giao | Outbox/relay có backlog không? |
| Epoch tại điểm thực thi so với nguồn | Kênh nào đang dựa vào dữ liệu quá cũ? |
| Action bị chặn do quyền cũ | Có token/client/job tiếp tục thử sau khi thu hồi không? |
| Binding/role được cấp lại bất thường | Có mapping đồng bộ hoặc đường nâng quyền chưa được xử lý không? |
| Công việc còn gán cho người mất quyền | Quy trình có cần reassign hoặc tạm dừng không? |

Một trạng thái “đã xác minh thực thi” cần dựa trên tập kênh và bằng chứng cụ thể. Không thể khẳng định mọi node đã áp dụng chỉ vì đã publish một event hoặc vì một consumer báo nhận thành công.

Không ghi token nguyên văn, bí mật hoặc thông tin scope nhạy cảm vào log mà người không có quyền đọc được. Quyền đọc audit và quyền thực hiện thu hồi cũng phải theo phạm vi tenant/đối tượng.

## 12. Các tình huống kiểm thử cần thiết

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Thu hồi binding đang hoạt động | Binding đổi state, epoch tăng và audit/outbox commit cùng nhau |
| Retry cùng key sau khi response bị mất | Trả kết quả gốc, không tăng epoch hoặc tạo thu hồi mới |
| Cùng key nhưng đổi target/binding/lý do theo fingerprint | Từ chối xung đột |
| Gọi lại với key mới cho binding đã revoked | Không hồi sinh hoặc thay mốc thu hồi gốc |
| Operator không có quyền trên scope hoặc tenant | Không thay đổi nguồn quyền, không lộ dữ liệu binding ngoài phạm vi |
| Gỡ B1 nhưng B2 vẫn cấp cùng capability | Kết quả phản ánh còn nguồn hợp lệ; không báo mất mọi quyền |
| Binding đã hết thời hạn nhưng chưa có job dọn dẹp | Không còn đóng góp quyền chỉ vì state còn ACTIVE |
| Token cũ còn chữ ký/hạn hợp lệ | Bị xử lý đúng cơ chế độ mới/thu hồi đã cam kết |
| Kết quả introspection hoặc cache cũ | Không vượt giới hạn stale mà policy cho phép |
| Event thu hồi bị trễ, trùng hoặc lệch thứ tự | Không hồi sinh nguồn cũ, không mất delta mà không phục hồi |
| Node mất kết nối nguồn quyền | Sau giới hạn đã định nghĩa, không tiếp tục action nhạy cảm bằng dữ liệu cũ vô hạn |
| Action giữ shared guard trước thu hồi | Thu hồi chờ; nếu action commit thì commit đó đứng trước commit thu hồi |
| Thu hồi giữ exclusive guard trước action | Action đọc quyền mới sau khi chờ, không dùng B1 cũ |
| Lỗi sau update binding, trước epoch/audit/outbox | Rollback toàn bộ |
| Lock timeout hoặc deadlock khi thu hồi | Không báo đã commit; retry phải đọc và kiểm tra lại từ đầu |
| Hai người gỡ hai admin cuối đồng thời | Không phá invariant phục hồi nếu policy có yêu cầu đó |
| Group sync hoặc role kế thừa còn đường cấp | Được phát hiện và xử lý theo đúng mục tiêu thu hồi |
| Job được enqueue trước thu hồi, chạy sau thu hồi | Đúng policy tiếp tục/kiểm tra lại/hủy đã định nghĩa |
| Quyết định hợp lệ đã commit trước thu hồi | Lịch sử không bị viết lại; hiệu lực sử dụng xử lý bằng action riêng nếu cần |
| Cấp B2 mới rồi nhận event thu hồi B1 cũ | Không tác động nhầm vòng đời binding mới |
| Xóa/tạo lại principal hoặc guard | Không reset epoch hoặc tái dùng danh tính làm credential cũ có hiệu lực lại |

Với kiểm thử concurrency, dùng kết nối và transaction thật, chủ động giữ/nhả guard để tạo cả hai thứ tự. Quan sát trạng thái đã commit bằng kết nối khác, không chỉ xác nhận một hàm `removeRole()` đã được gọi.

Với propagation, mô phỏng consumer dừng, cache còn dữ liệu, event lệch thứ tự và node mất nguồn quyền. Đo hành vi trên từng đường đọc/ghi thuộc hợp đồng, không suy ra bảo đảm hệ thống từ một API quản trị trả thành công.

Các khung mã và schema trong bài là minh họa thiết kế; chúng chưa được chạy như một ứng dụng hoàn chỉnh.

## 13. Bài tập áp dụng

Một người có reviewer trực tiếp ở P1, reviewer qua group ở P2 và grant tạm thời trên một đơn P1. Người đó còn access token, session web, job xuất báo cáo và một lệnh phát hành đã nằm trong outbox. Bộ phận quản trị yêu cầu “ngừng mọi khả năng phê duyệt ở P1 ngay khi việc thu hồi được xác nhận”.

Hãy thiết kế:

1. Mục tiêu này khác việc gỡ một role binding cụ thể ở điểm nào? Những đường cấp nào phải kiểm tra?
2. “Ngay khi xác nhận” là mốc nào, và những điểm thực thi nào thực sự tham gia bảo đảm đó?
3. Dùng nguồn quyền, guard/version hoặc cơ chế nào để request đang chạy không vượt ranh giới đã cam kết?
4. Token, session, cache và group sync được xử lý ra sao mà không gỡ thừa quyền hợp lệ ở P2?
5. Job, outbox và quyết định cũ được tiếp tục, kiểm tra lại hay vô hiệu theo policy nào?
6. Cách ghi audit, idempotency và tombstone nào giúp retry hoặc event đến muộn không cấp lại quyền?
7. Kiểm thử nào chứng minh hành vi khi nguồn quyền hoặc kênh phân phối bị lỗi?

Một chính sách gỡ role đầy đủ phải xác định đúng nguồn thẩm quyền, đúng phạm vi và đúng ranh giới hiệu lực. Việc thu hồi chỉ đáng tin khi các điểm thực thi không còn sử dụng nguồn quyền cũ ngoài hợp đồng đã cam kết, trong khi lịch sử quyết định và tác dụng nghiệp vụ vẫn được giữ chính xác.
