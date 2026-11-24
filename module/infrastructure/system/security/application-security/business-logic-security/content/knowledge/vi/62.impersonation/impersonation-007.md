# Impersonation audit

## 1. Audit impersonation cần trả lời điều gì?

Impersonation là cơ chế cho phép một người đã được xác thực thao tác trong ngữ cảnh của người dùng khác. Ví dụ, nhân viên hỗ trợ mở một phiên để tái hiện lỗi mà khách hàng gặp. **Impersonation audit** là dấu vết có cấu trúc giúp giải thích ai đã khởi tạo phiên, đang hành động thay ai, được phép làm gì, và mỗi thao tác thực sự tạo ra kết quả nào.

Trong bảo mật logic nghiệp vụ, chỉ biết “tài khoản khách hàng đã đổi địa chỉ nhận hàng” là chưa đủ. Cần biết thay đổi đó do khách hàng tự thực hiện hay do nhân viên hỗ trợ thực hiện trong một phiên impersonation. Nếu gán toàn bộ hành động cho khách hàng, hệ thống có thể che khuất việc sửa giá, vượt bước phê duyệt, đọc dữ liệu sai phạm vi hoặc gửi lại yêu cầu gây tác động trùng.

Một dấu vết đủ dùng phải trả lời được các câu hỏi:

- **Ai thao tác thật?** Danh tính đã được xác thực của nhân viên hoặc dịch vụ chịu trách nhiệm.
- **Hành động thay ai?** Người dùng được chọn làm ngữ cảnh hiệu lực.
- **Vì sao và dựa trên quyền nào?** Mục đích, yêu cầu hỗ trợ, chính sách, phạm vi được cấp và thông tin phê duyệt nếu quy trình yêu cầu.
- **Trên đối tượng nào?** Tenant, loại tài nguyên, mã tài nguyên và hành động nghiệp vụ.
- **Đã xảy ra điều gì?** Bị từ chối, được chấp nhận xử lý, đã commit, bị rollback hay còn chờ xử lý bất đồng bộ.
- **Có bằng chứng nào liên kết các bước?** Phiên impersonation, quyết định phân quyền, thao tác nghiệp vụ và giao dịch tương ứng.

Audit phục vụ điều tra và kiểm chứng các quy tắc nghiệp vụ. Nó phải đi cùng cơ chế kiểm soát quyền và transaction; việc ghi log không tự ngăn được hành vi vượt quyền.

## 2. Mô hình danh tính: giữ riêng người thao tác và người bị impersonate

### 2.1. Các danh tính cần phân biệt

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Actor | Người thao tác thật, đã qua xác thực | Nhân viên hỗ trợ `support-42` |
| Effective subject | Người dùng có ngữ cảnh đang được sử dụng | Khách hàng `customer-891` |
| Execution principal | Thành phần kỹ thuật thực thi thao tác | API hỗ trợ hoặc worker xử lý lệnh |
| Approver | Người phê duyệt yêu cầu nếu có | Trưởng nhóm `lead-12` |
| Target resource | Đối tượng nghiệp vụ chịu tác động | Đơn hàng `order-581` |

Một phiên đăng nhập thông thường có actor trùng effective subject. Trong phiên impersonation, hai giá trị khác nhau và phải cùng xuất hiện trong ngữ cảnh bảo mật lẫn dấu vết audit.

Execution principal không thay thế actor. Khi một worker xử lý yêu cầu do nhân viên khởi tạo, cần giữ cả danh tính nhân viên và danh tính worker. Tương tự, không được điền approver bằng actor chỉ để đủ trường dữ liệu.

### 2.2. Không lấy danh tính audit từ đầu vào do client quyết định

Một request như sau không chứng minh được người thao tác thật:

~~~http
POST /orders/order-581/change-delivery-address
X-Actor-Id: support-42
X-Impersonated-User: customer-891
Content-Type: application/json

{
  "newAddressId": "address-204"
}
~~~

Các header trên có thể bị người gọi tự sửa. Actor phải đến từ thông tin xác thực đã được server kiểm chứng. Effective subject và phạm vi impersonation phải được tra cứu hoặc xác minh từ phiên do server quản lý, rồi ràng buộc với actor, tenant và trạng thái hiện tại của phiên.

Trong hệ thống có gateway truyền ngữ cảnh danh tính, cần xác thực gateway, kiểm tra tính toàn vẹn ngữ cảnh và ngăn client đi vòng qua gateway hoặc tự chèn header nội bộ. Một giá trị có tên “internal” không tự trở thành dữ liệu đáng tin.

Không chuyển ngữ cảnh impersonation thành một phiên đăng nhập khách hàng thông thường làm mất actor gốc. Có thể thiết kế credential riêng cho impersonation, nhưng credential đó phải giữ được quan hệ actor–subject và không mở rộng quyền sang luồng đăng nhập thông thường.

### 2.3. Quyền hiệu lực không phải phép cộng quyền

Một quy tắc minh họa:

~~~text
Cho phép hành động khi đồng thời thỏa:
  actor được phép hỗ trợ tenant này;
  phiên impersonation đang ACTIVE và còn hạn;
  actor, subject và tenant khớp ràng buộc của phiên;
  hành động thuộc scope đã cấp cho phiên;
  subject có quyền với đối tượng theo chính sách của thao tác;
  trạng thái đối tượng cho phép hành động;
  không vi phạm quy tắc nghiệp vụ cấm trong impersonation.
~~~

Không lấy quyền quản trị của actor cộng với quyền của subject để tạo một “siêu người dùng”. Với thao tác hỗ trợ đặc biệt không thuộc quyền của subject, nên có capability hoặc luồng quản trị riêng, chính sách rõ ràng và audit tương ứng; không ngầm cho phép chỉ vì đang impersonate.

Ví dụ, hỗ trợ có thể được xem trạng thái đơn hàng nhưng bị cấm đổi tài khoản nhận tiền, chỉnh giá đã chốt hoặc tự phê duyệt yêu cầu hoàn tiền. Audit cần lưu kết quả kiểm tra và mã lý do như `IMPERSONATION_SCOPE_DENIED`, thay vì một dòng “access denied” khó giải thích.

## 3. Những bất biến audit phải duy trì

Bất biến là điều kiện phải đúng trên mọi đường thực thi, bao gồm retry, lỗi giữa chừng và xử lý bất đồng bộ.

| Bất biến | Ý nghĩa đối với thiết kế |
| --- | --- |
| Mỗi thao tác impersonation truy về được actor thật | Không ghi subject vào trường actor chỉ vì giao diện đang hiển thị tài khoản khách hàng |
| Phiên và thao tác cùng tenant hợp lệ | Không dựa riêng vào tenant do request gửi lên |
| Mỗi thay đổi đã commit có bằng chứng audit bền vững | Ghi bản ghi audit/outbox trong cùng transaction với thay đổi nghiệp vụ |
| Không báo thành công trước khi giao dịch hoàn tất | Phân biệt `REQUESTED`, `COMMITTED`, `ROLLED_BACK` và trạng thái của tác vụ bất đồng bộ |
| Retry không tạo tác động nghiệp vụ trùng | Ràng buộc khóa idempotency, payload và kết quả với đúng ngữ cảnh được phép |
| Thay đổi scope, hết hạn và thu hồi có thể giải thích | Ghi sự kiện vòng đời và quyết định thực thi chính sách |
| Audit không trở thành kênh rò dữ liệu | Không lưu credential, nội dung nhạy cảm hoặc toàn bộ payload một cách mặc định |

Ví dụ, một yêu cầu hoàn tiền đã commit nhưng không có dấu vết ai thực hiện là vi phạm bất biến audit. Một sự kiện “refund succeeded” được gửi trước commit, sau đó giao dịch bị rollback, cũng làm mất độ tin cậy của bằng chứng.

Audit không thay thế các bất biến của đơn hàng hay thanh toán: không hoàn vượt số tiền còn lại, không tự phê duyệt, không sửa đơn đã khóa, không thao tác trên đơn của tenant khác. Cần kiểm tra các điều kiện này tại nơi quyết định thay đổi dữ liệu.

## 4. Theo dõi toàn bộ vòng đời phiên impersonation

### 4.1. Trạng thái phiên và sự kiện audit là hai khái niệm khác nhau

Một mô hình minh họa cho hệ thống có phê duyệt:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: Đủ điều kiện phê duyệt
    REQUESTED --> REJECTED: Từ chối
    REQUESTED --> CANCELLED: Hủy yêu cầu
    REQUESTED --> EXPIRED: Hết hạn yêu cầu
    APPROVED --> ACTIVE: Xác thực tăng cường và kích hoạt
    APPROVED --> CANCELLED: Hủy trước kích hoạt
    APPROVED --> REVOKED: Thu hồi quyền đã cấp
    APPROVED --> EXPIRED: Quá hạn kích hoạt
    ACTIVE --> ENDED: Chủ động kết thúc
    ACTIVE --> EXPIRED: Hết hạn phiên
    ACTIVE --> REVOKED: Thu hồi
~~~

Không phải sản phẩm nào cũng cần phê duyệt thủ công. Có thể cấp quyền theo chính sách tự động, nhưng vẫn cần ghi chính sách nào cho phép, scope nào được cấp, thời hạn và các ràng buộc liên quan. Không tạo một “người phê duyệt” giả cho quyết định tự động.

Trạng thái hết hạn có thể được suy ra từ thời gian server ngay cả khi tác vụ nền chưa ghi sự kiện `EXPIRED`. Kiểm tra quyền không được tiếp tục chấp nhận phiên chỉ vì cột trạng thái chưa kịp cập nhật.

### 4.2. Các sự kiện nên có

| Sự kiện | Nội dung cần giải thích |
| --- | --- |
| `impersonation.requested` | Actor, subject, tenant, mục đích, ticket và scope yêu cầu |
| `impersonation.approved` hoặc `impersonation.rejected` | Người hoặc chính sách quyết định, scope cấp thực tế, lý do và thời hạn |
| `impersonation.started` | Phiên nào được kích hoạt, actor nào, thời điểm và phương thức xác thực tăng cường nếu có |
| `impersonation.action.allowed` | Quyết định cho phép tại một thời điểm; chưa khẳng định giao dịch đã commit |
| `impersonation.action.denied` | Hành động bị chặn, đối tượng và mã lý do phù hợp |
| Sự kiện nghiệp vụ như `order.delivery_address.changed` | Kết quả thay đổi đã commit và liên kết đến phiên, actor, quyết định quyền |
| `impersonation.ended`, `impersonation.expired`, `impersonation.revoked` | Phiên kết thúc thế nào, ai chủ động kết thúc/thu hồi nếu có |

Nếu cho phép đổi subject hoặc mở rộng scope, nên tạo phiên mới hoặc thực hiện một chuyển trạng thái được cấp quyền và audit rõ ràng. Không sửa âm thầm các ràng buộc cũ, vì thao tác trước và sau khi sửa sẽ khó phân biệt.

### 4.3. Xử lý thu hồi khi có yêu cầu đang chạy

Cần định nghĩa rõ mốc có hiệu lực của thu hồi. Ví dụ:

- Nếu thao tác nghiệp vụ và thao tác thu hồi cùng khóa bản ghi phiên, bên nào lấy khóa trước sẽ xác lập thứ tự. Giao dịch nghiệp vụ đã lấy khóa và kiểm tra hợp lệ có thể commit trước khi việc thu hồi hoàn tất.
- Nếu chính sách yêu cầu một mốc kiểm tra sát commit, phải có cơ chế transaction, khóa hoặc fencing tương ứng để tránh khoảng hở giữa “kiểm tra” và “sử dụng quyền”.
- Một quyết định đã kiểm tra quyền từ trước không được dùng để mở đầu một thao tác mới sau khi thu hồi đã có hiệu lực.

Không hứa rằng “bấm thu hồi sẽ hủy mọi tác động đang chạy” nếu hệ thống chỉ kiểm tra trạng thái phiên ở đầu request. Audit nên cho thấy thứ tự quyết định, commit và thu hồi để có thể đánh giá đúng hành vi.

## 5. Thiết kế bản ghi audit có thể truy vết

### 5.1. Các trường dữ liệu quan trọng

| Nhóm | Trường minh họa | Mục đích |
| --- | --- | --- |
| Định danh sự kiện | `event_id`, `event_type`, `schema_version` | Khử trùng khi chuyển phát, phân loại và đọc được schema cũ |
| Thời gian | `occurred_at`, `recorded_at`, `ingested_at` | Phân biệt lúc xảy ra theo nguồn, lúc ghi bền vững và lúc kho tập trung nhận |
| Nguồn | `source_service`, `execution_principal_id` | Biết thành phần nào phát sinh và thực thi |
| Danh tính | `actor_id`, `effective_subject_id`, `tenant_id` | Giữ trách nhiệm của người thao tác thật và phạm vi dữ liệu |
| Phiên | `impersonation_session_id`, `session_version` | Liên kết vòng đời, scope và phiên bản quyền tại thời điểm xét |
| Căn cứ | `purpose_code`, `ticket_ref`, `approval_ref` nếu có | Giải thích lý do và quyết định cấp quyền |
| Phân quyền | `policy_version`, `authorization_decision_id`, `reason_code` | Tái dựng căn cứ cho phép hoặc từ chối |
| Nghiệp vụ | `action`, `resource_type`, `resource_id`, `resource_version` | Xác định đối tượng và phiên bản chịu tác động |
| Liên kết | `request_id`, `trace_id`, `operation_id`, `causation_id` | Nối request, nghiệp vụ nhiều bước và sự kiện phát sinh |
| Kết quả | `outcome`, `changed_fields`, `error_code` khi thích hợp | Phân biệt quyết định quyền, thay đổi đã commit và lỗi |

Đây là mô hình tham khảo, không phải yêu cầu lưu mọi trường ở mọi sự kiện. Chẳng hạn, sự kiện yêu cầu bị từ chối trước khi tìm được phiên không có một `impersonation_session_id` hợp lệ. Giá trị actor không xác định phải được thể hiện trung thực, không lấy ID tự khai từ request để điền vào trường danh tính đã xác thực.

`request_id` và `trace_id` hỗ trợ liên kết kỹ thuật, nhưng không thay thế danh tính hay khóa nghiệp vụ. Trace có thể bị sampling hoặc thiếu một đoạn. Một header trace do client gửi cũng không được coi là bằng chứng quyền hạn.

### 5.2. Ví dụ sự kiện cho thay đổi đã commit

~~~json
{
  "schema_version": 1,
  "event_id": "evt-8e3f",
  "event_type": "order.delivery_address.changed",
  "occurred_at": "2026-11-22T03:10:15.120Z",
  "recorded_at": "2026-11-22T03:10:15.125Z",
  "source_service": "order-service",
  "execution_principal_id": "svc-order-api",
  "actor_id": "support-42",
  "effective_subject_id": "customer-891",
  "tenant_id": "tenant-a",
  "impersonation_session_id": "imp-73",
  "session_version": 3,
  "purpose_code": "RESOLVE_DELIVERY_ISSUE",
  "ticket_ref": "SUP-1042",
  "approval_ref": "approval-25",
  "policy_version": "support-policy-18",
  "authorization_decision_id": "decision-77",
  "action": "ORDER_CHANGE_DELIVERY_ADDRESS",
  "resource_type": "order",
  "resource_id": "order-581",
  "resource_version": 8,
  "operation_id": "op-902",
  "request_id": "req-501",
  "trace_id": "trace-101",
  "causation_id": "command-204",
  "outcome": "COMMITTED",
  "changed_fields": ["delivery_address_id"],
  "change_ref": "change-603"
}
~~~

Trong ví dụ, bản ghi được chèn cùng transaction với thay đổi đơn hàng. Giá trị `COMMITTED` chỉ được quan sát qua luồng đọc các transaction đã commit; nếu transaction rollback, cả thay đổi và bản ghi này đều không tồn tại.

Thời gian ghi bên trong transaction không nhất thiết là thời gian commit chính xác. Không tự gán `committed_at` từ đồng hồ ứng dụng trước khi commit rồi diễn giải nó như thời điểm commit của cơ sở dữ liệu.

`changed_fields` giúp biết loại dữ liệu đã thay đổi. `change_ref` có thể trỏ đến lịch sử thay đổi được kiểm soát quyền riêng. Việc khôi phục giá trị cũ cần mô hình lưu trữ thích hợp; chỉ lưu hash của giá trị không cho phép phục hồi nội dung và cũng không mặc nhiên ẩn được dữ liệu có miền giá trị nhỏ.

### 5.3. Hạn chế dữ liệu nhạy cảm

Không ghi trực tiếp vào audit:

- Password, access token, refresh token, cookie phiên, mã OTP hoặc khóa ký.
- Toàn bộ header, request/response body hoặc thông tin thanh toán.
- Địa chỉ, giấy tờ, nội dung trao đổi riêng tư nếu mục đích audit không đòi hỏi.
- Lý do hỗ trợ dạng văn bản tự do không được giới hạn và xử lý.

Ưu tiên ID tham chiếu, tên trường thay đổi, mã lý do có danh mục và giá trị đã được giảm chi tiết. Nếu cần lưu giá trị trước/sau để điều tra, tách vùng dữ liệu được bảo vệ với quyền đọc và thời hạn lưu phù hợp.

Thông tin mạng như IP, thiết bị hoặc user agent chỉ là ngữ cảnh phụ. IP sau proxy phải được xử lý theo chuỗi proxy đáng tin; không dùng một header tùy ý làm bằng chứng chắc chắn về nguồn truy cập.

Dùng sự kiện có cấu trúc, giới hạn độ dài chuỗi và escape đúng lúc hiển thị. Ticket hoặc user agent chứa ký tự xuống dòng không được biến thành các dòng log giả; dữ liệu hiển thị trong trang xem audit cũng cần được mã hóa theo ngữ cảnh để tránh chèn nội dung.

## 6. Liên kết audit với transaction nghiệp vụ

### 6.1. Lỗi thường gặp của cách ghi log trực tiếp

~~~text
1. Cập nhật đơn hàng.
2. Commit transaction.
3. Gửi audit qua HTTP sang hệ thống log.
4. Tiến trình bị dừng trước khi bước 3 hoàn tất.
~~~

Kết quả: đơn hàng đã thay đổi nhưng dấu vết audit bị thiếu.

Đảo thứ tự cũng có vấn đề:

~~~text
1. Gửi sự kiện "đổi địa chỉ thành công".
2. Cập nhật đơn hàng.
3. Transaction gặp lỗi và rollback.
~~~

Kết quả: audit khẳng định một thay đổi chưa từng được commit. Đổi HTTP sang message broker không tự giải quyết khoảng hở giữa hai lần ghi vào hai hệ thống độc lập.

### 6.2. Ghi nhận bền vững bằng transaction và outbox

Với thay đổi trong một cơ sở dữ liệu, có thể ghi bản ghi audit hoặc audit outbox cùng transaction với dữ liệu nghiệp vụ:

~~~mermaid
sequenceDiagram
    participant A as Actor hỗ trợ
    participant API as API nghiệp vụ
    participant DB as Database
    participant R as Outbox relay
    participant L as Kho audit

    A->>API: Lệnh trong phiên impersonation
    API->>API: Xác thực actor và giới hạn request
    API->>DB: BEGIN, khóa và đọc phiên
    API->>DB: Kiểm tra phiên, tenant, quyền, trạng thái đối tượng
    API->>DB: Thay đổi nghiệp vụ
    API->>DB: Ghi idempotency và audit outbox
    API->>DB: COMMIT
    DB-->>API: Đã commit
    API-->>A: Kết quả nghiệp vụ
    R->>DB: Đọc outbox đã commit
    R->>L: Chuyển sự kiện cùng event_id
    L-->>R: Xác nhận đã nhận bền vững
    R->>DB: Đánh dấu đã chuyển
~~~

Nếu chèn audit/outbox thất bại, transaction nghiệp vụ phải rollback. Kho audit tập trung tạm thời không khả dụng vẫn có thể được xử lý bằng retry của relay, miễn là outbox bền vững còn hoạt động và chưa vượt chính sách về dung lượng, độ trễ hoặc thời hạn lưu.

Relay thường có thể chuyển lại một sự kiện sau lỗi. Kho nhận cần khử trùng theo `event_id`, trong một phạm vi ID được định nghĩa rõ. Không tuyên bố toàn hệ thống “exactly once” chỉ vì mỗi hàng outbox có một ID duy nhất.

Một sự kiện nhiều lần chuyển phát và một nghiệp vụ bị thực hiện nhiều lần là hai vấn đề khác nhau. Khử trùng `event_id` xử lý bản sao chuyển phát; idempotency và ràng buộc dữ liệu bảo vệ tác động nghiệp vụ.

### 6.3. Pseudocode Java: thay đổi địa chỉ trong phiên hỗ trợ

Đoạn dưới là mã giả về thứ tự xử lý, không gắn với API của một framework cụ thể. Giả định phiên, đơn hàng, lịch sử thay đổi, bảng idempotency và outbox dùng chung cơ sở dữ liệu và transaction. Quy tắc trong ví dụ chỉ cho phép đổi địa chỉ của đơn thuộc subject khi đơn còn ở trạng thái cho phép.

~~~java
ChangeResult changeDeliveryAddress(
        AuthenticatedPrincipal authenticatedActor,
        SessionId sessionId,
        ChangeAddressCommand command,
        IdempotencyKey idempotencyKey) {

    ValidatedInput input = validateCommand(command, idempotencyKey);

    // transaction() chỉ trả kết quả thành công sau khi commit hoàn tất.
    return database.transaction(tx -> {
        ImpersonationSession session = sessions.lockForUpdate(tx, sessionId);

        SecurityContext context = policy.requireActiveContext(
                authenticatedActor,
                session,
                input.tenantId(),
                clock.instant());

        AuthorizationDecision decision = policy.requireAllowedAction(
                context,
                "ORDER_CHANGE_DELIVERY_ADDRESS");

        // Claim dựa trên unique constraint; cùng key nhưng khác fingerprint
        // bị từ chối. Việc chờ transaction cạnh tranh phải được xử lý rõ.
        IdempotencyClaim claim = idempotency.claimOrLoad(
                tx,
                context.stableIdentity(),
                idempotencyKey,
                fingerprint(input));

        if (claim.isCompleted()) {
            // Kiểm tra quyền hiện tại trước khi trả kết quả đã lưu.
            policy.requireCanReadStoredResult(tx, context, claim);
            audit.appendReplayAccess(tx, context, decision, claim);
            return claim.storedResult();
        }

        Order order = orders.lockForUpdate(
                tx, context.tenantId(), input.orderId());

        policy.requireSubjectOwnsOrder(context, order);
        order.requireDeliveryAddressCanChange();

        DeliveryAddress address = addresses.requireUsableBy(
                tx, context.tenantId(),
                context.effectiveSubjectId(), input.newAddressId());

        Change change = order.changeDeliveryAddress(address);
        orders.save(tx, order);
        changeHistory.appendMinimized(tx, change, context);

        ChangeResult result = ChangeResult.from(order);

        auditOutbox.append(tx, AuditEvent.businessCommitted(
                context, decision, order, change.reference()));

        idempotency.complete(tx, claim, result);
        return result;
    });
}
~~~

Các điều kiện cần giữ khi triển khai:

1. Actor được lấy từ principal đã xác thực. Session ID từ client chỉ là một tham chiếu để server kiểm chứng.
2. Scope, subject, tenant và trạng thái phiên đều được kiểm tra ở server. Địa chỉ mới cũng phải thuộc phạm vi được phép, không chỉ đơn hàng.
3. Quyền đọc kết quả idempotency phải được kiểm tra trước khi trả lại kết quả cũ. Nếu phiên bị thu hồi, không trả dữ liệu đã cache chỉ vì key tồn tại.
4. Kiểm tra trạng thái và thay đổi đối tượng phải được bảo vệ trước cạnh tranh bằng khóa, version hoặc cơ chế tương đương.
5. Claim idempotency có unique constraint và cùng transaction với tác động nghiệp vụ. Trình tự khóa phải thống nhất giữa các luồng để hạn chế deadlock.
6. Actor–subject được tạo một lần thành ngữ cảnh đáng tin và truyền đến nơi ghi audit. Không đọc chúng lại từ payload của lệnh.

Nếu phiên nằm ở một dịch vụ khác, không thể giả định việc đọc phiên qua HTTP tham gia transaction của đơn hàng. Khi đó cần một thiết kế rõ về hiệu lực quyền và thu hồi, chẳng hạn quyền ngắn hạn có phiên bản, kiểm tra quyền tập trung hoặc fencing phù hợp. Chỉ thêm annotation transaction trong một service không biến nhiều dịch vụ thành một giao dịch nguyên tử.

### 6.4. Ghi nhận từ chối và rollback

Sự kiện `action.denied` hoặc `action.failed` ghi trong transaction bị rollback cũng sẽ biến mất. Cần một đường ghi độc lập cho các kết quả này, ví dụ sau khi transaction đã kết thúc hoặc qua kênh sự kiện bảo mật có độ bền phù hợp.

Phân biệt hai yêu cầu:

- Với thay đổi nghiệp vụ nhạy cảm, nếu không thể tạo bằng chứng bền vững cùng thay đổi, không cho phép commit.
- Với yêu cầu đã bị từ chối, lỗi ghi audit không được làm nó trở thành được phép. Cần giữ kết quả từ chối và báo tình trạng mất khả năng ghi nhận qua cơ chế giám sát.

Không giả định mọi lần gọi đều sẽ có sự kiện lỗi: tiến trình có thể dừng đột ngột. Với quy trình cần chứng minh cả yêu cầu đầu vào, có thể ghi bền vững một sự kiện `REQUESTED` trước khi xử lý và đối chiếu các yêu cầu chưa có kết quả. Bản ghi còn treo chỉ cho biết chưa xác định được kết quả, không đủ căn cứ để kết luận thành công hay thất bại.

## 7. Idempotency, retry và xử lý bất đồng bộ

### 7.1. Một nghiệp vụ, nhiều lần gửi request

Giả sử nhân viên nhấn nút đổi địa chỉ, nhận timeout rồi gửi lại cùng lệnh. Có thể giao dịch đầu đã commit nhưng response bị mất. Nếu lần hai dùng cùng khóa idempotency và cùng fingerprint, server trả kết quả đã lưu sau khi kiểm tra quyền truy cập hiện tại, thay vì lặp lại tác động nghiệp vụ.

Phạm vi idempotency cần được quy định tường minh. Trong ví dụ trên, có thể dùng:

~~~text
tenant_id
+ actor_id
+ effective_subject_id
+ impersonation_session_id
+ operation_type
+ idempotency_key
~~~

Fingerprint phải được tính từ các trường nghiệp vụ đã chuẩn hóa, gồm đối tượng đích và nội dung lệnh có ý nghĩa. Cùng key nhưng thay địa chỉ hoặc đổi đơn hàng phải bị từ chối, không tái sử dụng một kết quả không tương ứng.

Đưa session vào khóa giúp cách ly các phiên, nhưng không ngăn một nghiệp vụ bị tạo lại từ phiên mới. Với nghiệp vụ như hoàn tiền, vẫn cần operation ID ổn định, unique constraint theo nghiệp vụ và bất biến về số tiền. Thời hạn giữ bản ghi idempotency cũng phải phù hợp với khoảng thời gian retry được chấp nhận; hết hạn cache không đồng nghĩa được phép bỏ qua ràng buộc nghiệp vụ.

Trong audit, có thể phân biệt:

| Tình huống | Cách ghi nhận |
| --- | --- |
| Lần đầu tạo thay đổi | Một sự kiện nghiệp vụ đã commit, gắn `operation_id` |
| Gửi lại cùng key và cùng lệnh | Sự kiện truy cập kết quả/replay nếu chính sách yêu cầu, liên kết đến operation cũ |
| Cùng key nhưng khác lệnh | Sự kiện xung đột idempotency hoặc từ chối, không tạo tác động mới |
| Relay chuyển lại cùng sự kiện | Kho nhận khử trùng theo `event_id` |
| Lệnh mới nhưng gây vi phạm bất biến | Từ chối theo quy tắc nghiệp vụ, dù key khác |

Một operation có thể có nhiều lần gửi request hợp lệ. Mỗi attempt có request ID riêng; các lần chuyển phát của cùng một sự kiện giữ nguyên event ID. Không tạo thêm một sự kiện “nghiệp vụ đã thực hiện” cho mỗi lần replay kết quả.

### 7.2. Truyền ngữ cảnh sang worker

Message cho worker cần mang hoặc tham chiếu được các thông tin đã được server xác lập:

- Actor gốc, effective subject và tenant.
- Phiên impersonation, phiên bản quyền và phạm vi liên quan.
- Operation ID, causation ID và tham chiếu quyết định phân quyền.
- Căn cứ nghiệp vụ đã chấp nhận, thời hạn thực thi hoặc điều kiện cần kiểm tra lại.

Message phải đi qua kênh được xác thực, có quyền publish phù hợp và kiểm tra schema. Không coi một JSON từ nguồn bất kỳ là ngữ cảnh tin cậy chỉ vì có trường `actor_id`.

Khi worker xử lý, cần phân biệt hai kiểu công việc:

1. **Tiếp tục một operation đã được chấp nhận bền vững.** Ví dụ, một yêu cầu hoàn tiền hợp lệ đã được ghi vào hàng đợi lệnh trong transaction. Việc phiên hỗ trợ kết thúc sau đó không nhất thiết hủy cam kết đã được chấp nhận; điều này phụ thuộc chính sách nghiệp vụ và cơ chế hủy.
2. **Mở đầu hành động mới dựa trên quyền hiện tại.** Worker phải xét lại quyền theo chính sách, thời hạn và trạng thái thu hồi, thay vì dùng quyền cũ vô thời hạn.

Cả hai kiểu đều phải giữ actor gốc và ghi execution principal của worker. Không thay actor bằng `system` chỉ vì tác động cuối được thực hiện ngoài HTTP request.

### 7.3. Tác động qua hệ thống bên ngoài

Outbox trong cơ sở dữ liệu nội bộ không làm một lời gọi hoàn tiền tới nhà cung cấp bên ngoài trở nên nguyên tử với transaction nội bộ. Với luồng này, cần trạng thái operation, khóa idempotency được nhà cung cấp hỗ trợ nếu có, quy trình đối chiếu và cách xử lý kết quả chưa xác định.

Ví dụ:

~~~text
refund.requested     -> Lệnh nội bộ được chấp nhận bền vững
refund.dispatched    -> Đã thử gửi tới hệ thống thanh toán
refund.confirmed     -> Có xác nhận đủ tin cậy rằng hoàn tiền thành công
refund.failed        -> Có bằng chứng thất bại theo chính sách
refund.unknown       -> Chưa xác định được kết quả, cần đối chiếu
~~~

HTTP timeout chỉ cho biết bên gọi chưa nhận được kết quả đúng hạn. Không tự suy ra rằng hoàn tiền thất bại rồi gửi một lệnh mới không có cơ chế chống trùng.

## 8. Bảo vệ tính toàn vẹn và quyền truy cập audit

### 8.1. Append-only và phân tách quyền

Một thiết kế có thể áp dụng:

- Ứng dụng có quyền tạo sự kiện qua API hoặc đường ghi chuyên biệt; không có quyền sửa, xóa tùy ý lịch sử.
- Nhân viên hỗ trợ không được tự xóa dấu vết phiên mình đã dùng.
- Người xem audit phải có quyền phù hợp với tenant và mục đích sử dụng.
- Quyền đọc dữ liệu nhạy cảm, xuất báo cáo và quản lý chính sách lưu trữ được phân tách khi cần.
- Các thao tác truy vấn nhạy cảm, xuất dữ liệu và thay đổi quyền quản trị audit cũng được ghi nhận.

Cần xét cả khả năng sửa/xóa outbox trước khi relay chuyển sự kiện. Có thể dùng phân quyền bảng, thủ tục ghi được giới hạn, lưu trữ riêng và giám sát thao tác bất thường. Chính sách cho relay đánh dấu “đã gửi” không nên trở thành quyền sửa nội dung sự kiện.

Append-only là một thuộc tính phải được thực thi ở lớp lưu trữ và vận hành, không chỉ là quy ước trong code. Tài khoản quản trị cơ sở dữ liệu hoặc hệ điều hành có thể có khả năng vượt qua giới hạn thông thường; cần giảm quyền, giám sát và phân tách trách nhiệm phù hợp với mô hình đe dọa.

### 8.2. Phát hiện sửa đổi và giới hạn của hash

Hash từng sự kiện có thể hỗ trợ kiểm tra tính toàn vẹn, nhưng người sửa được cả dữ liệu và hash vẫn có thể tính lại hash. Chuỗi hash cũng chưa đủ chống người có thể viết lại toàn bộ chuỗi hoặc xóa phần cuối.

Nếu cần bằng chứng mạnh hơn, có thể kết hợp chữ ký hoặc MAC được quản lý khóa độc lập, checkpoint được neo sang nơi có quyền quản trị tách biệt, và cơ chế lưu trữ chống sửa/xóa phù hợp. Cần bảo vệ khóa, xác định dữ liệu chuẩn hóa để ký và quản lý vòng đời khóa.

Các cơ chế này giúp phát hiện một số kiểu can thiệp trong một mô hình đe dọa cụ thể. Chúng không tự chứng minh rằng nội dung do ứng dụng phát ra là sự thật nếu chính ứng dụng hoặc danh tính người dùng đã bị chiếm quyền.

### 8.3. Lưu trữ, thời gian và khả năng tìm kiếm

- Xác định thời hạn lưu theo nhu cầu điều tra, vận hành và các yêu cầu áp dụng; không mặc định lưu vô hạn.
- Đồng bộ đồng hồ hệ thống và ghi rõ múi giờ, thường bằng UTC. Không dùng timestamp làm tiêu chí duy nhất để kết luận thứ tự tuyệt đối giữa nhiều dịch vụ.
- Dùng causation ID, sequence theo phiên/operation hoặc version đối tượng để hỗ trợ dựng thứ tự. Không giả định một ID tăng dần luôn phản ánh chính xác thứ tự commit.
- Theo dõi schema version, quyền truy vấn, backup và khả năng khôi phục kho audit.
- Cân nhắc index theo tenant, actor, subject, session, resource và operation để tìm được bằng chứng khi có sự cố.

Nếu có chính sách che hoặc xóa dữ liệu nhận dạng, cần thiết kế cách thực hiện mà vẫn giữ liên kết điều tra cần thiết trong phạm vi được phép. Không rải dữ liệu cá nhân dạng thô vào nhiều bản sao rồi kỳ vọng chỉ xóa một chỗ.

## 9. Giám sát và đối chiếu để phát hiện lỗ hổng logic

### 9.1. Những tín hiệu đáng quan tâm

| Tín hiệu | Rủi ro cần xem xét |
| --- | --- |
| Actor mở nhiều phiên cho nhiều khách hàng trong thời gian ngắn | Lạm dụng chức năng hỗ trợ hoặc dò dữ liệu |
| Nhiều lần đổi tenant, đổi resource ID rồi bị từ chối | Thử vượt quyền theo đối tượng |
| Thao tác tài chính bị cấm lặp lại trong phiên hỗ trợ | Tìm đường sửa tiền, giá hoặc người nhận |
| Phiên thiếu ticket hợp lệ hoặc dùng một lý do cho nhiều mục đích | Cơ chế kiểm soát mục đích đang yếu |
| Thao tác mới được cho phép sau mốc thu hồi có hiệu lực | Kiểm tra phiên hoặc cache quyền có vấn đề |
| Bản ghi thay đổi nhạy cảm không nối được đến audit/operation | Có đường ghi đi vòng kiểm soát hoặc mất dữ liệu |
| Outbox tăng lâu, sự kiện lỗi schema hoặc mất liên tục | Kho audit đang không nhận đủ bằng chứng |

Ngưỡng cảnh báo phụ thuộc mô hình sử dụng thực tế. Cần tránh kết luận nhân viên lạm dụng chỉ từ một tín hiệu đơn lẻ; nên liên kết với ticket, lịch làm việc, chính sách và lịch sử sự kiện.

### 9.2. Đối chiếu thay đổi nghiệp vụ với audit

Một truy vấn minh họa, giả định có lịch sử thay đổi nghiệp vụ độc lập và bảng audit chuẩn hóa:

~~~sql
SELECT
    c.tenant_id,
    c.change_id,
    c.operation_id,
    c.order_id,
    c.actor_id
FROM order_change_history c
LEFT JOIN audit_event a
    ON  a.tenant_id = c.tenant_id
    AND a.operation_id = c.operation_id
    AND a.change_id = c.change_id
    AND a.event_type = 'order.delivery_address.changed'
    AND a.outcome = 'COMMITTED'
WHERE c.execution_mode = 'IMPERSONATION'
  AND a.event_id IS NULL;
~~~

Bảng chuẩn hóa có thể lấy `change_id` từ `change_ref` trong envelope ở ví dụ trước. Tên bảng, cột và cách lưu thực tế tùy hệ thống.

Nếu truy vấn kho audit tập trung, phải tính đến độ trễ chuyển phát và chỉ đối chiếu các thay đổi đã qua cửa sổ độ trễ được chấp nhận. Một dòng chưa xuất hiện ngay sau commit chưa đủ để kết luận bị mất vĩnh viễn.

Lịch sử thay đổi dùng để đối chiếu cần bao phủ các đường ghi liên quan, kể cả quản trị và tác vụ nền. Nếu cả lịch sử và audit đều chỉ được tạo bởi một đoạn code mà đường ghi khác có thể bỏ qua, việc đối chiếu hai bảng đó không chứng minh mọi thay đổi đã được theo dõi.

### 9.3. Một trình tự điều tra thực tế

Khi khách hàng báo địa chỉ đơn hàng bị đổi ngoài ý muốn:

1. Xác định đúng tenant, order ID và các version liên quan.
2. Tìm operation/change và sự kiện nghiệp vụ đã commit; ghi nhận trường nào đổi.
3. Truy theo session đến actor thật, mục đích, ticket, approval và scope đã cấp.
4. Kiểm tra quyết định quyền, chính sách tại thời điểm thực hiện và trạng thái đơn hàng.
5. So sánh thứ tự với sự kiện hết hạn hoặc thu hồi; kiểm tra request retry và công việc nền.
6. Đối chiếu bản ghi nguồn, outbox và kho tập trung để phát hiện thiếu, trùng hoặc chậm chuyển phát.
7. Bảo toàn bằng chứng cần thiết và xử lý theo quy trình của tổ chức.

Không chỉ tìm bằng effective subject rồi kết luận khách hàng tự thay đổi. Không sửa lại lịch sử cũ để “làm sạch” kết quả điều tra; nếu cần đính chính, ghi một sự kiện mới liên kết với bằng chứng gốc.

## 10. Kiểm thử các tình huống tấn công logic

Kiểm thử cần quan sát cả kết quả API, dữ liệu nghiệp vụ và bằng chứng audit bền vững. Một response đúng nhưng dữ liệu thay đổi sai, hoặc dữ liệu đúng nhưng mất actor, vẫn là lỗi.

| Tình huống | Kỳ vọng về nghiệp vụ | Kỳ vọng về audit |
| --- | --- | --- |
| Client tự đặt actor/subject header | Không thể thay đổi danh tính đáng tin | Actor phản ánh principal đã xác thực; giá trị tự khai không trở thành actor |
| Actor A dùng session được cấp cho actor B | Từ chối | Có mã lý do ràng buộc phiên không hợp lệ, không rò thông tin vượt quyền |
| Đổi order ID sang đơn của khách hàng khác | Từ chối theo quyền đối tượng | Ghi được lần thử và tenant/context đã xác minh |
| Chọn địa chỉ của subject khác | Không đổi địa chỉ đơn hàng | Ghi từ chối ở bước kiểm tra đối tượng địa chỉ |
| Gửi tenant khác trong request | Không truy cập hay thay đổi dữ liệu tenant đó | Phân biệt tenant đã xác thực và dữ liệu khai báo nếu cần lưu |
| Phiên ACTIVE trong bảng nhưng đã quá expires_at | Từ chối thao tác mới | Lý do hết hạn đúng, không phụ thuộc tác vụ nền |
| Thu hồi và thao tác chạy đồng thời | Kết quả tuân theo thứ tự hiệu lực đã định nghĩa | Có đủ version/causation để giải thích thứ tự |
| Hai request đồng thời cùng key, cùng payload | Tối đa một tác động nghiệp vụ | Một sự kiện tác động; các attempt/replay liên kết operation |
| Cùng key nhưng khác payload hoặc resource | Từ chối xung đột | Không ghi thêm một kết quả thành công sai đối tượng |
| Retry sau khi phiên bị thu hồi | Không mở quyền hoặc lộ kết quả cũ trái phép | Kết quả từ chối/replay phản ánh kiểm tra quyền hiện tại |
| Chèn outbox thất bại | Thay đổi nghiệp vụ rollback | Không có sự kiện thành công đã commit |
| Tiến trình dừng sau commit trước khi trả response | Tác động vẫn được ghi nhận; retry an toàn | Outbox và kết quả idempotency còn bền vững |
| Relay bị dừng sau khi kho nhận đã lưu | Có thể chuyển lại cùng event | Khử trùng theo event ID, không mất sự kiện |
| Transaction rollback sau một bước kiểm tra | Không có thay đổi đã commit | Không tồn tại sự kiện nghiệp vụ thành công; lỗi/từ chối được ghi độc lập nếu ghi được |
| Worker tiếp tục sau khi phiên kết thúc | Theo chính sách của operation đã nhận hoặc hành động mới | Giữ actor gốc, subject và execution principal của worker |
| Actor thử tự phê duyệt hoặc sửa giá bị cấm | Bất biến nghiệp vụ được giữ | Lý do từ chối cụ thể, không chỉ ghi “logged in” |
| Ticket chứa xuống dòng hoặc nội dung HTML | Không giả mạo log hay chạy nội dung trong trang audit | Dữ liệu có cấu trúc, giới hạn và hiển thị an toàn |
| Nhân viên hỗ trợ thử xóa/xuất audit trái quyền | Từ chối theo quyền đọc/ghi | Có dấu vết thao tác quản trị/tra cứu theo chính sách |

Với race condition, nên dùng kiểm thử tích hợp có điểm đồng bộ rõ để điều khiển thứ tự khóa và commit. Chạy hai request “gần cùng lúc” mà không kiểm soát lịch thực thi có thể bỏ sót khoảng hở.

Với tính nguyên tử, chèn lỗi tại các ranh giới: trước thay đổi, sau thay đổi nhưng trước outbox, sau outbox nhưng trước commit, và sau commit nhưng trước response. Kiểm tra dữ liệu đã commit từ một kết nối/transaction độc lập để tránh chỉ nhìn thấy trạng thái tạm thời của chính test.

Với bảo mật dữ liệu, kiểm tra nội dung audit thực tế thay vì chỉ kiểm tra tên event. Một logger ghi nguyên request body vẫn có thể làm lộ token dù business event đã được giảm dữ liệu.

## 11. Ví dụ xuyên suốt: nhân viên hỗ trợ đổi địa chỉ giao hàng

Giả sử chính sách cho phép hỗ trợ đổi địa chỉ trước khi đơn chuyển sang khâu xử lý giao hàng, nhưng cấm sửa giá, thay chủ đơn và tự phê duyệt hoàn tiền.

Một luồng hợp lệ:

1. `support-42` tạo yêu cầu cho `customer-891` trong `tenant-a`, gắn ticket `SUP-1042`.
2. Hệ thống cấp scope xem đơn và đổi địa chỉ trong thời hạn quy định; nếu quy trình yêu cầu, `lead-12` phê duyệt.
3. Server kích hoạt `imp-73`, lưu actor, subject, tenant, scope và thời hạn.
4. Nhân viên gửi lệnh đổi địa chỉ của `order-581`, kèm khóa idempotency.
5. Server xác minh phiên, quyền trên đơn, quyền dùng địa chỉ đích và trạng thái đơn trong cơ chế transaction thích hợp.
6. Đơn, lịch sử thay đổi, kết quả idempotency và audit outbox cùng commit.
7. Relay chuyển sự kiện; khi xem lịch sử, người có quyền thấy thay đổi do `support-42` thực hiện thay `customer-891`.
8. Nhân viên kết thúc phiên. Các yêu cầu mới trong phiên đó bị từ chối.

Những nhánh tấn công cần bị chặn:

- Thay ID đơn bằng đơn của một khách hàng khác, dù cùng tenant.
- Dùng cùng phiên nhưng gọi endpoint sửa giá trực tiếp.
- Gửi lại lệnh với khóa khác để gây thêm tác động mà quy tắc nghiệp vụ không cho phép.
- Tiếp tục dùng credential impersonation sau khi phiên bị thu hồi.
- Lợi dụng đường gọi worker để bỏ qua scope hoặc mất dấu actor.

Khi khách hàng hỏi “ai đã đổi địa chỉ của tôi?”, bằng chứng cần chỉ ra người thao tác thật, phiên hỗ trợ, căn cứ cấp quyền và thay đổi đã commit. Không trả lời bằng dòng log chỉ ghi tên khách hàng.

## 12. Tiêu chí hoàn thành một thiết kế impersonation audit

Một thiết kế có thể được đánh giá qua các câu hỏi sau:

- Mỗi thay đổi truy được đồng thời actor thật, effective subject, tenant và phiên impersonation không?
- Phân quyền theo đối tượng, trạng thái nghiệp vụ và scope có được kiểm tra ở server không?
- Audit có phân biệt quyết định cho phép với thay đổi đã commit không?
- Thay đổi nghiệp vụ và bằng chứng bền vững có cùng transaction hoặc một thiết kế nhất quán được giải thích rõ không?
- Thu hồi, hết hạn, retry và xử lý bất đồng bộ có ngữ nghĩa cụ thể không?
- Kho audit có chống sửa/xóa trong mô hình quyền đã chọn, kiểm soát đọc và giảm dữ liệu nhạy cảm không?
- Có phát hiện được sự kiện thiếu, chuyển phát trùng, độ trễ quá mức và đường ghi đi vòng không?
- Các tình huống vượt quyền, thao tác trùng và lỗi giữa chừng đã có cách kiểm chứng không?

Giá trị của impersonation audit nằm ở khả năng gắn một tác động nghiệp vụ với đúng người thao tác thật và bằng chứng đáng tin về quyền, thời điểm và kết quả. Dấu vết đó chỉ hữu ích khi được thiết kế cùng state machine, quyền theo đối tượng, transaction và idempotency của nghiệp vụ.
