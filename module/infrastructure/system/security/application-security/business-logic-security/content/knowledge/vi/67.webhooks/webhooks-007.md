# Webhook subscription audit

## 1. Subscription là một quyền nhận dữ liệu có vòng đời

Một webhook subscription là cấu hình cho phép gửi một nhóm sự kiện đến một nơi nhận, trong một phạm vi dữ liệu nhất định. Đăng ký sự kiện hóa đơn cho một cửa hàng có nghĩa là cấp một luồng truy cập dữ liệu ra ngoài hệ thống. Subscription vì vậy cần được quản lý như một quyền truy cập, không chỉ như một URL.

**Webhook subscription audit** gồm hai công việc:

- Ghi lại ai tạo, sửa, xác minh, phê duyệt, kích hoạt, tạm dừng hoặc thu hồi subscription; thay đổi nào thực sự được commit.
- Rà soát subscription đang tồn tại để xác định chúng còn đúng chủ thể, phạm vi, nơi nhận và quy trình phê duyệt hay không.

Trong bảo mật logic nghiệp vụ, audit giúp bảo vệ các bất biến trước hành vi bỏ qua phê duyệt, sửa sai đối tượng, mở rộng quyền, khai thác cạnh tranh và gửi yêu cầu trùng. Audit không thay thế việc chặn hành động sai ngay tại API.

Sau bài học, bạn có thể thiết kế lịch sử thay đổi gắn với transaction, truy ngược một delivery đến cấu hình đã cấp quyền gửi, và xây dựng các ca kiểm thử tấn công logic.

### Tình huống xuyên suốt

Nền tảng bán hàng phục vụ nhiều doanh nghiệp; mỗi doanh nghiệp là một tenant. Tenant “t-acme” có hai cửa hàng “shop-01” và “shop-02”. Ứng dụng kế toán “integration-acc” chỉ được nhận sự kiện “invoice.paid” của “shop-01” tại địa chỉ:

~~~text
https://receiver.example/hooks/invoices
~~~

Nhân viên được tạo đề xuất tích hợp; người có thẩm quyền phải phê duyệt trước khi dữ liệu hóa đơn được gửi. Kẻ lạm dụng có thể đổi URL, thay bộ lọc cửa hàng thành toàn tenant, gọi thẳng API kích hoạt, dùng bằng chứng xác minh cũ hoặc phát lại job sau khi bị thu hồi quyền.

**Chữ ký webhook hợp lệ không chứng minh việc gửi dữ liệu là đúng quyền.** Chữ ký giúp xác minh thông điệp được ký bằng khóa tương ứng. Quyết định ai được nhận hóa đơn vẫn thuộc logic nghiệp vụ.

## 2. Ba loại bằng chứng cần phân biệt

| Loại dữ liệu | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Lịch sử quản lý subscription | Ai thay đổi quyền nhận dữ liệu? Thay đổi có thành công không? | Người đổi phạm vi, revision trước/sau, approval |
| Lịch sử delivery | Sự kiện nào được thử gửi, bằng cấu hình nào, đến đâu? | Delivery ID, event ID, endpoint revision, kết quả |
| Kết quả rà soát | Cấu hình đang có còn phù hợp với quyền và policy hiện tại không? | Grant đã thu hồi, approval không còn khớp |

Access log HTTP thường không đủ để dựng lại phạm vi dữ liệu trước/sau, căn cứ phê duyệt và quyết định quyền. Delivery trả mã 200 không chứng minh bên nhận có quyền nhận dữ liệu.

Ngược lại, audit record có kết quả COMMITTED chứng minh một thay đổi đã được lưu; nó không chứng minh bên nhận xử lý thành công. Timeout cũng không chứng minh dữ liệu chưa đến nơi nhận. Cần liên kết bằng chứng bằng các ID ổn định.

Một mô hình subscription phục vụ bài học có các trường sau:

| Trường | Ý nghĩa bảo mật |
| --- | --- |
| tenant_id, subscription_id | Ranh giới dữ liệu và đối tượng cần kiểm tra quyền |
| integration_id, grant_id | Chủ thể tích hợp và quyền duy trì luồng dữ liệu |
| created_by | Người tạo, không nhất thiết là chủ thể giữ quyền dài hạn |
| event_types, resource_scope, payload_profile | Loại sự kiện, đối tượng và nhóm trường được xuất |
| endpoint_id, endpoint_revision | Nơi nhận cụ thể đã được xác minh |
| state, revision, authorization_epoch | Trạng thái, phiên bản cấu hình và thế hệ quyền |
| verification_id, approval_id | Bằng chứng xác minh và phê duyệt |
| signing_key_id | Tham chiếu khóa, không phải giá trị bí mật |
| created_at, updated_at, revoked_at | Các mốc thời gian do máy chủ ghi nhận |

Đây là mô hình minh họa, không phải schema bắt buộc của một nhà cung cấp webhook. Hệ thống có thể dùng ít trường hơn nhưng phải mô tả rõ khi nào quyền và bằng chứng hết hiệu lực.

## 3. Bất biến cần kiểm toán

### 3.1. Tenant, đối tượng và quyền xuất dữ liệu

Với subscription s và sự kiện e:

~~~text
s.tenant_id = e.tenant_id
s.integration_id thuộc s.tenant_id
grant của integration còn hiệu lực
s.event_types là tập con của loại sự kiện được grant cho phép
s.resource_scope là tập con của phạm vi đối tượng được grant cho phép
payload chỉ chứa các trường được payload_profile cho phép
~~~

Quyền xem hóa đơn trên màn hình không tự động bao hàm quyền xuất hóa đơn liên tục sang hệ thống khác. Cần kiểm tra riêng quyền quản lý webhook và quyền cấp luồng dữ liệu, trên đúng tenant, integration, cửa hàng và loại sự kiện.

Người thực hiện request phải có quyền làm hành động đó. Quyền duy trì subscription có thể thuộc integration hoặc service account, không nhất thiết phụ thuộc vĩnh viễn vào người đã bấm tạo. Khi người tạo nghỉ việc, subscription cá nhân có thể bị đình chỉ; subscription của doanh nghiệp có thể tiếp tục nếu grant và chủ thể chịu trách nhiệm vẫn hợp lệ. Quy tắc này phải được công bố, không suy từ trường created_by.

Nguyên tắc kiểm tra quyền trên mọi request và trên đúng đối tượng được trình bày trong [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Với webhook, cần áp dụng cho cả cấu hình, xem audit, xem delivery, gửi thử và replay.

### 3.2. Trạng thái và bằng chứng phê duyệt

~~~text
ACTIVE(s, r)
  => endpoint revision đã được xác minh
  AND approval khớp cấu hình bảo mật của revision r
  AND grant hiện tại còn hợp lệ
  AND các điều kiện policy còn được đáp ứng

Thay đổi cấu hình bảo mật
  => không tái sử dụng bằng chứng cũ khi bằng chứng không còn phù hợp

REVOKED(s)
  => không cấp phép lần gửi mới sau điểm thu hồi có hiệu lực
~~~

Approval nên ràng buộc với một config_digest: dấu băm của biểu diễn chuẩn hóa các trường ảnh hưởng quyền, chẳng hạn tenant, integration, endpoint, tập sự kiện, phạm vi và payload profile. Tập hợp phải được sắp xếp ổn định trước khi băm. Không đưa secret vào dấu băm dùng trong audit.

Đổi URL hoặc mở rộng scope làm approval cũ không còn đủ. Đổi tên hiển thị có thể không cần phê duyệt lại. Có thể tách revision toàn bản ghi với digest cấu hình bảo mật để không vô hiệu hóa bằng chứng vì thay đổi không liên quan.

### 3.3. Transaction, cạnh tranh và yêu cầu trùng

- Mỗi thay đổi thành công có audit record tương ứng được lưu bền vững cùng transaction dữ liệu, hoặc bằng một cơ chế tương đương được mô tả rõ.
- Request bị từ chối không để lại thay đổi subscription, quota hay job gửi thử dở dang.
- Cùng một command và idempotency key chỉ tạo một hiệu ứng nghiệp vụ chuẩn.
- Hai request dựa trên cùng revision cũ không được âm thầm ghi đè nhau.
- Hai request tạo subscription không được cùng chiếm một suất quota cuối cùng.

Log chỉ giúp biết một bất biến đã bị vi phạm. Chính service, transaction và cơ chế cấp phép gửi phải thực thi bất biến đó.

## 4. Kiểm toán theo state machine

Ví dụ sau dùng chính sách dừng gửi khi sửa cấu hình nhạy cảm:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_VERIFICATION: Yêu cầu xác minh
    PENDING_VERIFICATION --> PENDING_APPROVAL: Xác minh endpoint
    PENDING_APPROVAL --> ACTIVE: Duyệt đúng cấu hình
    ACTIVE --> PAUSED: Tạm dừng
    PAUSED --> ACTIVE: Kiểm tra lại điều kiện
    ACTIVE --> PENDING_VERIFICATION: Đổi endpoint và dừng gửi
    ACTIVE --> PENDING_APPROVAL: Đổi scope và dừng gửi
    ACTIVE --> REVOKED: Thu hồi
    PAUSED --> REVOKED: Thu hồi
    PENDING_APPROVAL --> REVOKED: Hủy đề xuất
    PENDING_VERIFICATION --> REVOKED: Hủy đề xuất
    DRAFT --> REVOKED: Hủy bản nháp
    REVOKED --> [*]
~~~

Sản phẩm cần chuyển đổi không gián đoạn có thể giữ revision cũ hoạt động và tạo đề xuất revision mới riêng. Revision cũ phải giữ nguyên quyền; revision mới chỉ nhận quyền sau khi hoàn tất điều kiện. Không sửa cấu hình đang chạy rồi giữ nguyên một cờ approved của lần duyệt trước.

| Thao tác | Điều kiện kiểm tra | Bằng chứng lưu |
| --- | --- | --- |
| Tạo | Quyền trên tenant/integration, grant và quota | Actor, cấu hình đề xuất đã che secret |
| Xác minh | Challenge đúng endpoint revision, còn hạn, chưa dùng | Verification ID, revision, kết quả |
| Phê duyệt | Người duyệt có thẩm quyền với toàn bộ phạm vi | Approval ID, config digest, policy/grant version |
| Kích hoạt | Bằng chứng còn hiệu lực, không có thay đổi xen ngang | Revision và quyết định quyền |
| Đổi URL/scope | Quyền sửa, expected revision, quy trình duyệt lại | Diff an toàn và bằng chứng bị vô hiệu hóa |
| Xoay khóa | Quyền chuyên biệt, khóa mới sẵn sàng | Key ID cũ/mới, thời hạn chuyển tiếp |
| Tạm dừng/thu hồi | Quyền trên subscription, lý do phù hợp | Mốc hiệu lực, authorization epoch |
| Replay | Quyền phát lại, phạm vi và nơi nhận còn hợp lệ | Batch ID, khoảng sự kiện, lý do |

Nếu policy yêu cầu hai người độc lập, máy chủ phải kiểm tra người duyệt khác người đề xuất. Tính lại thẩm quyền khi duyệt; không tin danh sách vai trò được chụp từ lúc tạo đề xuất.

Không bind toàn bộ entity từ request để client có thể tự gán state, approved_by, verified_at, tenant_id hoặc signing_key_id. Mỗi command chỉ nhận các trường được phép sửa. Với giao diện quản trị xác thực bằng cookie, các command thay đổi subscription cũng cần kiểm soát CSRF phù hợp.

## 5. Xác minh endpoint không phải phê duyệt xuất dữ liệu

Một challenge thành công chỉ chứng minh mức kiểm soát kỹ thuật đối với endpoint tại thời điểm xác minh. Nó không chứng minh người nhận được phép nhận hóa đơn, hay người xác minh có quyền phê duyệt.

Challenge nên gắn với bộ:

~~~text
tenant_id + subscription_id + endpoint_revision + nonce + expires_at
~~~

Challenge dùng một lần, có hạn, chỉ mang dữ liệu tổng hợp. Không gửi hóa đơn thật để thử kết nối. Không chấp nhận client tự gửi verified=true; kết quả phải đi qua kênh xác minh có kiểm tra challenge.

Đổi host, port, đường dẫn hoặc thành phần định tuyến có ý nghĩa phải tạo endpoint revision mới theo hợp đồng sản phẩm. Không chuẩn hóa đường dẫn/query theo cách làm thay đổi ngữ nghĩa rồi xem hai URL khác nhau là một. Ví dụ của bài không cho credential trong URL; bí mật xác thực bổ sung được lưu riêng trong kho secret.

API verify, test và replay đều khiến máy chủ gọi ra ngoài. Chúng phải dùng chung kiểm soát egress với delivery. Có quyền sửa subscription không có nghĩa là được phép biến máy chủ thành công cụ gọi mạng nội bộ.

[OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) đề cập kiểm soát ở lớp ứng dụng và mạng, nguy cơ redirect, cùng việc gắn kết nối với IP đã kiểm tra. Thiết kế minh họa dùng HTTPS, xét IPv4/IPv6, chặn loopback, mạng nội bộ, link-local và metadata; không tự theo redirect. Kiểm soát áp dụng cho cả retry và địa chỉ dự phòng, đồng thời giữ đúng hostname khi xác minh TLS.

DNS an toàn lúc đăng ký không chứng minh đích đến an toàn lúc gửi. Audit lưu phiên bản policy egress và kết quả quyết định, nhưng rà soát định kỳ không thay thế kiểm soát tại điểm kết nối.

Giới hạn số lần xác minh, gửi thử và replay theo tenant, integration và chủ thể. Kiểm tra quota tạo subscription phải nguyên tử: count rồi insert bằng hai transaction độc lập có thể bị vượt bằng request song song. Gửi thử bằng dữ liệu tổng hợp vẫn là hành động cần audit.

## 6. Audit record: đủ để dựng lại quyết định

Dùng schema có phiên bản, mã hành động ổn định và danh sách trường được phép ghi. Tránh serialize toàn bộ request hoặc entity.

| Nhóm trường | Ví dụ | Nguồn |
| --- | --- | --- |
| Record | audit_id, schema_version, occurred_at | Máy chủ sinh |
| Chủ thể | actor_type, actor_id, effective_subject_id | Ngữ cảnh xác thực/ủy quyền đã kiểm chứng |
| Đối tượng | tenant_id, subscription_id, integration_id | Đối tượng được truy xuất trong tenant hợp lệ |
| Quyết định | action, outcome, reason_code | Kết quả xử lý thực tế |
| Phiên bản | before_revision, after_revision, authorization_epoch | Trạng thái trong transaction |
| Diff | changed_fields, before_summary, after_summary | Projection an toàn |
| Bằng chứng | approval_id, verification_id, policy_version, grant_version | Nguồn đã kiểm chứng |
| Liên kết | request_id, command_id, trace_id, outbox_id | Hệ thống sinh hoặc chuẩn hóa |

Ví dụ đổi phạm vi từ một sang hai cửa hàng, chưa duyệt phạm vi mới:

~~~json
{
  "schema_version": 1,
  "audit_id": "aud-2041",
  "occurred_at": "2026-11-22T03:15:04Z",
  "tenant_id": "t-acme",
  "subscription_id": "sub-17",
  "integration_id": "integration-acc",
  "actor_type": "HUMAN",
  "actor_id": "user-42",
  "action": "SUBSCRIPTION_SCOPE_CHANGE_REQUESTED",
  "outcome": "COMMITTED",
  "reason_code": "REAPPROVAL_REQUIRED",
  "before_revision": 7,
  "after_revision": 8,
  "authorization_epoch": 4,
  "changed_fields": ["resource_scope", "state"],
  "before_summary": {
    "shops": ["shop-01"],
    "state": "ACTIVE"
  },
  "after_summary": {
    "shops": ["shop-01", "shop-02"],
    "state": "PENDING_APPROVAL"
  },
  "config_digest": "sha256:example-redacted",
  "invalidated_approval_id": "apr-91",
  "policy_version": "policy-12",
  "grant_version": 5,
  "request_id": "req-901",
  "command_id": "cmd-660"
}
~~~

COMMITTED ở đây có nghĩa đề xuất và trạng thái chờ duyệt đã được lưu, không phải phạm vi mới đã được cấp quyền gửi. Theo mô hình dừng gửi của bài, rời ACTIVE đồng thời tăng authorization_epoch để vô hiệu hóa quyền gửi cũ.

Request thiếu quyền dùng outcome DENIED cùng reason code an toàn; không tạo record COMMITTED. Không đưa tên tenant hay cấu hình mà caller không được xem vào phản hồi hoặc màn hình audit.

Không lấy actor_id, approved_by hoặc tenant_id do client khai báo làm sự thật kiểm toán. Thao tác quản trị thay mặt khách hàng phải giữ cả actor thực, chủ thể được đại diện và tham chiếu lý do đã kiểm soát. Job tự động dùng service identity, tên job và run ID cụ thể, tránh ghi mọi thứ dưới một actor chung tên “system”.

### Tránh tạo thêm một kho rò rỉ dữ liệu

OWASP khuyến nghị log ghi đủ thời gian, nơi phát sinh, chủ thể và hành động; tránh ghi trực tiếp access token, khóa và dữ liệu nhạy cảm. Audit webhook nên dùng projection đã kiểm soát và quyền đọc riêng. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Không ghi signing secret, authorization header, cookie, challenge token hay toàn bộ payload hóa đơn. Với endpoint, lưu ID, revision và mô tả đã che thông tin. Bản cấu hình chính xác phục vụ điều tra có thể nằm trong kho lịch sử được bảo vệ chặt hơn. Digest không khôi phục được URL đã mất; cần thiết kế cả việc lưu và truy cập cấu hình lịch sử.

Giới hạn chiều dài lý do, User-Agent và request ID; dùng log có cấu trúc và encoding an toàn để ký tự xuống dòng không tạo record giả. IP nguồn phải được xác định qua proxy tin cậy, không từ header tùy ý. IP và dữ liệu nhận diện cũng cần quyền đọc, thời hạn lưu phù hợp.

## 7. Transaction cho cấu hình, audit và outbox

Sửa cấu hình xong mới gọi dịch vụ log từ xa có thể làm mất bằng chứng khi gọi log lỗi. Ghi “thành công” trước commit lại tạo lịch sử cho thay đổi sau đó bị rollback.

Mô hình minh họa đặt các bước sau trong cùng transaction cơ sở dữ liệu:

~~~text
BEGIN
  kiểm tra quyền hiện tại và kiểm soát revision liên quan
  giữ chỗ idempotency key, kiểm tra fingerprint
  cập nhật subscription và quota/trạng thái liên quan
  INSERT subscription_audit với outcome COMMITTED
  INSERT outbox_event liên kết audit_id và revision
  lưu kết quả idempotency của command
COMMIT
~~~

Outbox relay chuyển record sang kho giám sát sau commit. Relay có thể gửi trùng, nên nơi nhận khử trùng bằng audit_id hoặc outbox_id. Khi relay ngừng, dữ liệu local vẫn còn để chuyển tiếp.

Trong mô hình này, lỗi ghi audit bắt buộc trong transaction làm rollback command thay đổi quyền. Gián đoạn kho giám sát từ xa không nhất thiết chặn command nếu audit và outbox đã được lưu bền vững. Không buộc mọi request đợi một dịch vụ log ngoài database.

Request DENIED, conflict hoặc rollback cần kênh security event độc lập, vì audit row nằm trong transaction bị rollback cũng mất. Kênh này phải có giám sát mất log và chống spam. Không biến thao tác bị từ chối thành thành công vì log lỗi. Nếu timeout khiến kết quả commit chưa rõ, tra lại command_id trước khi kết luận hoặc làm lại bằng command mới.

### Mã giả Java: đổi endpoint

Đây là mã giả tầng ứng dụng để minh họa thứ tự kiểm soát, không phải chương trình có thể biên dịch trực tiếp:

~~~java
ChangeResult changeEndpoint(AuthContext auth, ChangeEndpoint cmd) {
    TrustedActor actor = authentication.requireActor(auth);
    TenantId tenant = authorization.requireTenantContext(actor);
    EndpointProposal proposal = endpointPolicy.validateSyntax(cmd.endpoint());
    // Chưa gọi HTTP/DNS bên ngoài trong transaction cấu hình.

    return unitOfWork.inTransaction(() -> {
        Subscription current = subscriptions.lockByTenantAndId(
            tenant, cmd.subscriptionId());

        PolicySnapshot policy = authorization.lockAndRequireChange(
            actor, current); // Kiểm tra cả grant duy trì integration.

        String fingerprint = fingerprints.ofCanonicalCommand(
            tenant, actor.id(), cmd.subscriptionId(), "CHANGE_ENDPOINT",
            proposal, cmd.expectedRevision());

        IdempotencyClaim claim = commands.claimOrRead(
            tenant, actor.id(), "CHANGE_ENDPOINT", cmd.idempotencyKey(),
            fingerprint); // Unique constraint; xử lý request cạnh tranh.
        claim.requireSameFingerprint();

        if (claim.completed()) {
            return claim.storedResult(); // Đã kiểm tra quyền hiện tại.
        }

        current.requireRevision(cmd.expectedRevision());
        current.requireNotRevoked();
        SafeSnapshot before = auditProjection.of(current);

        current.proposeEndpoint(proposal); // Endpoint revision mới.
        current.invalidateVerificationAndApproval();
        current.moveToPendingVerification();
        current.incrementRevisionAndAuthorizationEpoch();
        subscriptions.save(current);

        AuditRecord record = audit.committedChange(
            actor, policy, claim.commandId(), before,
            auditProjection.of(current));
        auditRepository.insert(record);
        outboxRepository.insertForAudit(record);

        ChangeResult result = ChangeResult.from(current, record.id());
        commands.complete(claim, result);
        return result;
    });
}
~~~

Hợp đồng lockAndRequireChange phải có thật: các đường cập nhật grant và subscription dùng cùng chiến lược khóa hoặc kiểm tra phiên bản, tránh khoảng hở kiểm tra quyền rồi grant bị thu hồi trước commit. Thứ tự lấy khóa phải nhất quán để hạn chế deadlock. Nếu policy nằm ở dịch vụ ngoài, cần giao thức phiên bản, lease hoặc thu hồi rõ ràng; một lần gọi kiểm tra quyền từ xa không tạo transaction nguyên tử với database local.

Xác minh endpoint qua mạng diễn ra bất đồng bộ, ngoài transaction giữ khóa. Khi kết quả quay lại, command xác minh khóa lại đối tượng và kiểm tra endpoint revision, nonce, hạn dùng. Kết quả endpoint cũ không được kích hoạt cấu hình mới.

Thao tác kho secret cũng không tự rollback theo database. Khi xoay khóa, có thể chuẩn bị key reference bất biến trước, commit cấu hình tham chiếu cùng audit, rồi dọn khóa chưa dùng nếu thất bại. Cần quy trình riêng cho kích hoạt và hủy khóa.

## 8. Idempotency và cạnh tranh

Namespace idempotency key cần rõ, ví dụ:

~~~text
(tenant_id, actor_id, operation, idempotency_key)
~~~

Unique constraint đảm bảo hai request đồng thời không cùng sở hữu một key. Fingerprint gồm đối tượng đích, các trường có ý nghĩa và expected revision. Cùng key nhưng đổi URL hoặc scope phải bị từ chối, không nhận kết quả cũ cho nội dung mới.

Khi trả kết quả đã lưu, vẫn xác thực và kiểm tra quyền đọc hiện tại để không tiết lộ cấu hình sau khi caller mất quyền. Kết quả idempotency trong ví dụ không chứa secret.

| Tình huống | Hiệu ứng mong muốn | Dấu vết |
| --- | --- | --- |
| Cùng key, cùng nội dung, gửi đồng thời | Một commit; request kia nhận kết quả chung hoặc trạng thái đang xử lý | Một audit thay đổi, liên kết retry |
| Cùng key, khác nội dung | Conflict, không đổi thêm | Record từ chối an toàn |
| Hai key, cùng expected revision | Chỉ một thay đổi từ revision đó thành công | Một commit, một revision conflict |
| Hai request tranh suất quota cuối | Chỉ một request giữ được suất | Audit tạo và quota denied |
| Retry sau khi key hết thời hạn | Theo hợp đồng API đã công bố | Uniqueness nghiệp vụ vẫn bảo vệ khi cần |

API có thể dùng 409 cho conflict hoặc 412 khi điều kiện If-Match thất bại, tùy hợp đồng. Không được thực hiện một phần thay đổi rồi mới trả lỗi.

Idempotency không ngăn người có quyền tạo nhiều subscription với nhiều key khác nhau. Nếu đăng ký trùng cùng integration, endpoint và scope không có ý nghĩa, cần ràng buộc uniqueness nghiệp vụ riêng. Hạn mức phải bao phủ cả subscription, proposal chờ, challenge và replay.

Có thể ghi nhiều attempt retry để điều tra, nhưng chỉ một record thay đổi cấu hình đã commit. Không phát thêm “subscription created” mỗi lần đọc lại kết quả idempotency.

## 9. Từ audit đến delivery và thu hồi

Nếu queue chỉ lưu subscription_id rồi worker lấy URL hiện tại, sự kiện cũ có thể bị chuyển sang nơi nhận chưa từng được cấp quyền đối với sự kiện đó.

Job trong ví dụ tham chiếu:

~~~text
delivery_id, event_id, event_tenant_id
subscription_id, subscription_revision, authorization_epoch
endpoint_id, endpoint_revision, payload_profile_version
routing_decision_id hoặc origin_command_id
~~~

Metadata không chứa signing secret. Cấu hình lịch sử phải đủ để dựng đúng payload và đích gửi, nhưng bản lịch sử không tự cho phép tiếp tục gửi khi quyền hiện tại đã bị thu hồi.

Trước khi cấp phép mỗi attempt, kiểm tra subscription còn ACTIVE, grant còn hiệu lực, tenant/scope phù hợp, authorization_epoch chưa bị thay thế và endpoint revision còn được phép. Thu hẹp quyền không được đợi queue cũ chạy hết. Job hết quyền được đánh dấu CANCELLED_AUTHORIZATION_CHANGED, liên kết audit record gây vô hiệu hóa.

### Race giữa kiểm tra và gửi

Worker có thể đọc ACTIVE, sau đó subscription bị thu hồi, rồi mới gửi HTTP. Một phép đọc trạng thái đơn lẻ không giải quyết race. Cần định nghĩa điểm tuần tự hóa giữa **cấp phép gửi** và **thu hồi**.

Một thiết kế dùng coordinator hoặc khóa chung theo subscription để tuần tự hóa việc cấp send permit và thu hồi. Permit gắn epoch, có hạn ngắn, chỉ dùng một attempt và được worker thực thi theo giao thức xác định. Worker không tự cấp permit mới khi coordinator không truy cập được.

Permit được cấp trước điểm thu hồi có thể đang thực thi. Chính sách cần xác định cách đợi hết, hủy hoặc báo cáo attempt đó. Không thể thu hồi byte đã đi ra mạng.

Cam kết mặc định của ví dụ là “không cấp phép lần gửi mới sau điểm thu hồi có hiệu lực”, đồng thời báo cáo attempt đã được cấp phép trước đó còn đang chạy. Nếu API hứa khi thu hồi trả về thì không còn attempt đang gửi, cần cơ chế drain phối hợp và xử lý worker treo; đổi một cột trạng thái không đủ.

### Replay là một lần cấp quyền mới

Biết event_id không đủ để phát lại. Phải kiểm tra quyền replay, tenant sự kiện, phạm vi, khoảng thời gian, endpoint và grant hiện tại. Dữ liệu trước ngày subscription được kích hoạt cần chính sách cho phép backfill riêng, không tự được cấp theo quyền nhận sự kiện mới.

Replay có batch ID, lý do, quota và idempotency riêng. Giữ event ID nghiệp vụ và tạo metadata delivery/attempt theo hợp đồng tích hợp để bên nhận khử trùng đúng. Không dùng chức năng gửi thử làm đường tắt phát lại payload thật.

GitHub khuyến nghị đăng ký những sự kiện cần thiết, dùng webhook secret, HTTPS và xác minh chứng chỉ. Những kiểm soát kênh gửi này hữu ích, nhưng ứng dụng vẫn phải quản lý quyền và vòng đời subscription. [GitHub: Best practices for using webhooks](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks).

## 10. Rà soát subscription đang tồn tại

Endpoint trả 200 vẫn có thể đang nhận dữ liệu vượt quyền. Rà soát cần đối chiếu trạng thái thực với nguồn quyền và bằng chứng được chấp nhận.

Mỗi run nên có audit_run_id, thời điểm snapshot, phiên bản policy và phạm vi tenant. Dùng snapshot nhất quán hoặc checkpoint rõ để phân biệt sai lệch thật với dữ liệu thay đổi giữa lúc quét.

1. Liệt kê subscription cùng integration, grant, endpoint revision và bằng chứng.
2. Tính entitlement hiện tại từ nguồn quyền chính thức, gồm cả scope và payload profile.
3. Đối chiếu cấu hình ACTIVE với verification, approval và config digest.
4. Đối chiếu chuỗi revision với audit; tìm thay đổi qua admin API, script hoặc migration thiếu lịch sử.
5. Kiểm tra job/delivery quanh lần đổi URL, thu hẹp quyền và thu hồi.
6. Tạo finding có bằng chứng, mức độ, chủ thể xử lý và cách khắc phục.
7. Trước khi khắc phục, đọc lại quyền và revision để tránh sửa theo snapshot đã cũ.

| Finding | Bằng chứng | Hướng xử lý |
| --- | --- | --- |
| ORPHANED_INTEGRATION | Integration bị xóa hoặc grant bị thu hồi | Dừng cấp phép gửi theo policy, rà soát delivery |
| SCOPE_EXCEEDS_GRANT | Sự kiện, cửa hàng hoặc trường dữ liệu vượt entitlement | Thu hẹp/đình chỉ bằng command có audit |
| APPROVAL_STALE | Digest cấu hình không khớp approval | Duyệt lại, chặn kích hoạt sai quy trình |
| ENDPOINT_PROOF_STALE | Verification sai revision hoặc hết hiệu lực theo policy | Xác minh lại bằng challenge tổng hợp |
| REVISION_HISTORY_GAP | Trạng thái hiện tại không khớp chuỗi chuyển revision | Điều tra nguồn cập nhật và độ đầy đủ audit |
| DELIVERY_AFTER_REVOCATION | Permit mới được cấp sau điểm thu hồi | Điều tra race, cache quyền, đường replay |
| STALE_UNUSED_SUBSCRIPTION | Không có hoạt động trong khoảng policy quy định | Yêu cầu chủ thể chịu trách nhiệm xác nhận |

Không có delivery gần đây không chứng minh subscription không còn cần: sự kiện có thể hiếm. Endpoint timeout không chứng minh chủ sở hữu mất quyền. Lỗi đọc dịch vụ quyền tạo trạng thái chưa xác định; việc chặn gửi hoặc retry phải theo policy, không tự kết luận mọi subscription đều trái phép.

Chỉ tự động đình chỉ khi điều kiện và quyền khắc phục đủ rõ. Job audit có quyền tối thiểu, không tự gọi hàng loạt URL đã thu thập. Nếu kiểm tra kết nối, dùng egress được bảo vệ và hạn mức như delivery. Hành động khắc phục của job là command riêng với service identity và audit riêng.

### Truy vấn tìm approval không khớp

Giả sử dùng PostgreSQL; subscription có security_config_digest, approval có approved_config_digest, trạng thái và expires_at. ID approval là duy nhất trong tenant:

~~~sql
SELECT s.tenant_id,
       s.id AS subscription_id,
       s.revision,
       s.approval_id
FROM webhook_subscription s
LEFT JOIN webhook_approval a
       ON a.tenant_id = s.tenant_id
      AND a.id = s.approval_id
      AND a.subscription_id = s.id
WHERE s.state = 'ACTIVE'
  AND (
       a.id IS NULL
       OR a.status IS DISTINCT FROM 'APPROVED'
       OR a.approved_config_digest
             IS DISTINCT FROM s.security_config_digest
       OR (a.expires_at IS NOT NULL AND a.expires_at <= CURRENT_TIMESTAMP)
  );
~~~

Truy vấn chỉ tìm ứng viên trong schema minh họa. Nó chưa đánh giá thẩm quyền người duyệt, grant version, endpoint proof và thay đổi policy. Bổ sung các kiểm tra đó khi kết luận finding, tốt nhất theo cùng mốc snapshot. Không lấy danh sách kết quả rồi tự tắt hàng loạt subscription.

Không dùng updated_at bằng timestamp audit mới nhất làm bằng chứng lịch sử đầy đủ. Đồng hồ, transaction cạnh tranh và độ trễ chuyển log có thể làm kết quả sai. Liên kết theo revision, command ID và audit ID được ghi cùng transaction đáng tin hơn.

## 11. Bảo vệ chính lịch sử kiểm toán

Người sửa subscription không nên có khả năng xóa lịch sử thay đổi của mình. Tách quyền ghi audit khỏi quyền sửa/xóa, cấp quyền tối thiểu cho tài khoản ứng dụng và có thể chuyển bản sao sang kho với ranh giới quản trị độc lập.

Append-only ở tầng service không ngăn được tài khoản database/hạ tầng có đặc quyền. Lưu trữ bất biến, retention lock hoặc checkpoint độc lập có thể tăng khả năng phát hiện và chống sửa. Chuỗi hash chỉ hữu ích khi điểm neo và khóa không nằm hoàn toàn trong cùng quyền kiểm soát với dữ liệu bị sửa; nó không tạo tính chống chối bỏ tuyệt đối.

Quy định thời hạn lưu audit, cấu hình lịch sử, metadata delivery, backup và export theo nhu cầu điều tra và chính sách dữ liệu. Không mặc định lưu vĩnh viễn toàn bộ payload. Đồng bộ thời gian, lưu UTC và dùng revision để không phụ thuộc hoàn toàn vào timestamp khi sắp thứ tự.

API xem/export audit phải kiểm tra tenant, đối tượng và vai trò chuyên biệt. Quyền sửa webhook không mặc nhiên cho quyền tải toàn bộ lịch sử doanh nghiệp. Các lần xem, xuất hoặc thay đổi chính sách audit cũng cần dấu vết; file export cần hạn truy cập và không làm lộ secret.

Theo dõi độ trễ outbox/ingest, record lỗi schema, mất log và sức khỏe pipeline. Không có audit event có thể là không có thay đổi, nhưng cũng có thể pipeline đã dừng; cần tín hiệu sức khỏe riêng để phân biệt.

## 12. Kiểm thử tình huống tấn công logic

Mỗi ca cần kiểm tra cả phản hồi API, trạng thái dữ liệu, audit và side effect. Nhận 403 là chưa đủ nếu phía sau vẫn có job gửi dữ liệu.

| Tình huống | Cách thử trong môi trường kiểm thử | Kết quả cần khẳng định |
| --- | --- | --- |
| Sửa sai tenant | Tài khoản A gọi subscription của B | Không sửa, không gửi thử, không lộ thông tin B |
| Mass assignment | Gửi thêm state=ACTIVE, approved_by, tenant_id | Không gán trường đặc quyền, không kích hoạt ngầm |
| Bỏ qua phê duyệt | Gọi activate trước approval | Không có send permit; có lý do từ chối |
| Tự duyệt trái policy | Người đề xuất tự phê duyệt | Từ chối ở máy chủ, trạng thái không đổi |
| Đổi URL sau duyệt | Duyệt revision 7, đổi endpoint ở revision 8 | Approval cũ không cho phép gửi đến URL mới |
| Challenge cũ | Hoàn tất challenge của endpoint revision trước | Không xác minh cấu hình hiện tại |
| Mở rộng bằng bộ lọc | Bỏ filter, dùng wildcard hoặc tập cửa hàng lớn hơn | Kiểm tra quyền theo ngữ nghĩa, không ngầm thành toàn tenant |
| Retry/tranh quota | Gửi song song cùng và khác idempotency key | Một hiệu ứng cho retry, không vượt quota |
| Ghi đè cạnh tranh | Hai cập nhật cùng expected revision | Một commit; diff và revision audit đúng |
| Audit insert lỗi | Gây lỗi ghi audit trong transaction | Cấu hình, outbox và kết quả command cùng rollback |
| Kho log ngoài ngừng | Dừng relay sau commit local | Audit/outbox còn; gửi lại không tạo record trùng |
| Race thu hồi/gửi | Chặn worker tại bước permit rồi thu hồi | Không có permit mới sau điểm hiệu lực |
| Job epoch cũ | Đưa job cũ vào queue sau đổi quyền | Job bị hủy, không tự lấy URL hiện tại để gửi |
| Replay vượt quyền | Chọn tenant khác hoặc dữ liệu lịch sử chưa được cấp | Không tạo batch xuất dữ liệu trái phép |
| SSRF qua test/retry | Dùng endpoint nội bộ hoặc redirect trong lab | Egress chặn verify, test, retry và replay |
| Secret trong audit | Đặt canary ở secret/header rồi chạy command | Canary không xuất hiện trong log, diff, lỗi hoặc export |
| Log injection | Đặt CR/LF trong lý do/tên | Một record có cấu trúc, không có dòng giả |
| Đọc audit sai tenant | Gọi list/get/export bằng tenant khác | Không đọc được lịch sử và cấu hình được bảo vệ |

Với ca cạnh tranh, dùng barrier/latch điều khiển thứ tự thay vì chỉ thêm sleep rồi hy vọng race xảy ra. Quan sát số transaction commit, audit record thay đổi, outbox event và send permit. Thử cả trường hợp response bị mất nhưng transaction đã commit.

Các ca mạng dùng endpoint và dữ liệu do nhóm kiểm thử kiểm soát. Không cần payload thật hay hạ tầng bên thứ ba để chứng minh bất biến.

## 13. Điều tra một subscription đáng ngờ

Giả sử sub-17 mở rộng từ một cửa hàng sang toàn tenant rồi yêu cầu replay lịch sử. Chuỗi điều tra nên trả lời:

1. Actor thực nào gửi command, có đại diện ai và được xác thực thế nào?
2. Revision/digest nào được đề xuất, approval nào đã chấp nhận và có dùng bằng chứng cũ không?
3. Grant/policy nào có hiệu lực khi commit? Quyền hiện tại có cho tiếp tục gửi không?
4. Routing decision, replay batch, send permit và delivery attempt nào liên quan?
5. Event, khoảng thời gian, nhóm đối tượng và payload profile nào có khả năng đã ra ngoài?
6. Command thu hồi/đình chỉ nào đã ngăn gửi tiếp? Queue và attempt đang chạy được xử lý thế nào?

Không lấy số response 200 làm toàn bộ phạm vi dữ liệu có thể đã rò rỉ. Giữ nguyên lịch sử cũ, ghi thêm finding và hành động khắc phục; không sửa audit để làm sạch kết quả.

Xoay signing secret có thể cần khi secret bị lộ, nhưng không thu hồi dữ liệu đã gửi và không sửa lỗi cấp quyền tenant/cửa hàng. Khắc phục phải nhắm đúng nguyên nhân: authorization, chuyển trạng thái, ràng buộc approval, race hoặc đường thực thi bỏ qua kiểm soát.

## 14. Tiêu chí hoàn thành thiết kế

- Với subscription ACTIVE, chỉ ra được grant, endpoint proof, approval và cấu hình cụ thể đang cho phép gửi.
- Với thay đổi nhạy cảm, chỉ ra được actor thực, revision trước/sau, quyết định quyền và audit đã commit cùng dữ liệu.
- Với delivery, truy ngược được event, tenant, revision, endpoint và căn cứ cấp phép attempt.
- Khi đổi URL, thu hẹp scope hoặc thu hồi, mô tả rõ số phận job đã xếp hàng và attempt đang chạy.
- Khi request trùng, cạnh tranh hoặc pipeline log lỗi, dữ liệu nghiệp vụ và lịch sử giữ đúng bất biến đã công bố.
- Audit, delivery và export không làm lộ secret hoặc dữ liệu khác tenant.
- Job rà soát tạo finding có bằng chứng và khắc phục qua command được kiểm soát.
