# Consent record

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt consent record, OAuth authorization grant, access token và hồ sơ chứng minh cơ sở xử lý dữ liệu.
- Xác định thông tin cần lưu để chứng minh ai đã đồng ý, đồng ý với nội dung nào, cho client nào, vào thời điểm và trong phạm vi nào.
- Thiết kế vòng đời consent có cấp, cập nhật, hết hạn, rút lại và lưu vết thay đổi.
- Liên kết consent với scope, resource, purpose, tenant và token issuance mà không biến access token thành kho lưu bằng chứng pháp lý.
- Kiểm thử việc cấp token, thay đổi scope, rút consent, đồng bộ trạng thái và truy xuất audit evidence.

## 1. Consent record là gì?

**Consent record** là bản ghi có cấu trúc lưu bằng chứng về một quyết định đồng ý, từ chối hoặc rút lại sự đồng ý của một chủ thể. Trong hệ thống dùng OAuth 2.0/OIDC, bản ghi này có thể giúp authorization server chứng minh một client đã được cấp quyền trong phạm vi cụ thể, đồng thời giúp hệ thống xác định consent còn hiệu lực hay đã bị thay đổi.

Ví dụ, một người dùng kết nối ứng dụng quản lý chi tiêu với tài khoản ngân hàng. Ứng dụng yêu cầu đọc số dư và lịch sử giao dịch. Consent record cần giúp trả lời:

- Ai đã đưa ra quyết định?
- Họ đang hành động với tư cách cá nhân hay đại diện cho một tổ chức?
- Client nào nhận quyền?
- Dữ liệu hoặc resource nào được truy cập?
- Mục đích và phạm vi quyền đã được giải thích ra sao?
- Người dùng đã đồng ý vào lúc nào, qua giao diện/phiên bản thông báo nào?
- Consent hiện còn hiệu lực, đã hết hạn hay đã bị rút lại?

Consent record là bằng chứng và trạng thái quản trị. Nó không phải access token, không phải refresh token và cũng không tự nó thực thi quyền truy cập. Resource server vẫn phải xác minh token, audience, scope và policy ở mỗi request.

## 2. Phân biệt consent, authorization và authentication

Ba khái niệm này thường xuất hiện trong cùng một luồng nhưng có ý nghĩa khác nhau:

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang đăng nhập? | Identity Provider xác thực user-42 |
| Consent | Chủ thể đã đồng ý điều gì, với ai và theo thông tin nào? | User-42 đồng ý cho finance-app đọc số dư |
| Authorization | Request hiện tại có được phép thực hiện hành động này không? | Token hợp lệ có scope balance.read và đúng audience |

Một user đăng nhập thành công không có nghĩa họ đã đồng ý chia sẻ dữ liệu với mọi client. Ngược lại, có consent record cũng không có nghĩa mọi request sau đó đều được phép: token có thể hết hạn, bị thu hồi, sai audience, scope không đủ hoặc quyền đã thay đổi.

OAuth 2.0 mô tả authorization grant và scope. Scope biểu diễn phạm vi quyền được cấp trong giao thức, nhưng **một chuỗi scope trong access token không phải bằng chứng đầy đủ về consent**. Muốn chứng minh nội dung đã trình bày và quyết định của người dùng, hệ thống cần lưu consent evidence riêng theo policy của mình.

### Consent không phải lúc nào cũng là cơ sở xử lý dữ liệu

Trong các quy định về bảo vệ dữ liệu cá nhân, consent có thể là một cơ sở pháp lý để xử lý dữ liệu, nhưng không phải cơ sở duy nhất. Tùy tình huống, tổ chức có thể dựa vào hợp đồng, nghĩa vụ pháp lý, lợi ích hợp pháp hoặc cơ sở khác được quy định. Không được ép người dùng bấm đồng ý nếu hoạt động xử lý thực tế dựa trên một cơ sở khác, hoặc coi việc cấp OAuth scope là tự động chứng minh mọi yêu cầu pháp lý về consent đã được đáp ứng.

Với machine-to-machine/client credentials, quyền thường được quản trị viên hoặc chủ sở hữu hệ thống cấu hình theo hợp đồng và policy. Không nên giả định luôn có một người dùng cuối thực hiện consent tương tác. Hãy ghi rõ loại quyết định, người/role phê duyệt và căn cứ áp dụng.

## 3. Consent record cần chứa những gì?

Một record hữu ích cần đủ thông tin để chứng minh quyết định và tái dựng phạm vi quyền tại thời điểm cấp. Schema cụ thể phụ thuộc hệ thống; OAuth 2.0 và OIDC không định nghĩa một cấu trúc consent record phổ quát.

| Nhóm dữ liệu | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Định danh | consent_id, grant_id | Tra cứu record và liên kết authorization grant |
| Chủ thể | subject, subject_type | Xác định người dùng hoặc principal được đại diện |
| Người ra quyết định | actor, actor_role | Ghi nhận người dùng hoặc quản trị viên đã thực hiện quyết định |
| Tenant | tenant_id | Phân tách consent theo tổ chức/khách hàng |
| Client | client_id, client_name/version | Xác định ứng dụng nhận quyền |
| Resource | resource/audience | Xác định API hoặc nhóm dữ liệu được truy cập |
| Quyền | scopes, authorization_details | Ghi rõ quyền được cấp ở mức cần thiết |
| Mục đích | purpose, data_categories | Ghi lại mục đích và nhóm dữ liệu được giải thích |
| Thông báo | notice_id, notice_version, locale | Xác định nội dung người dùng được trình bày |
| Bằng chứng | decision, captured_at, capture_method | Ghi quyết định, thời gian và cách thu nhận |
| Trạng thái | status, expires_at, withdrawn_at | Quản lý vòng đời consent |
| Nguồn | source, policy_version | Biết hệ thống/luồng và policy đã áp dụng |

Ví dụ record minh họa:

~~~json
{
  "consent_id": "consent-7f21",
  "grant_id": "grant-91a2",
  "subject": {
    "type": "user",
    "id": "user-42"
  },
  "actor": {
    "type": "user",
    "id": "user-42",
    "role": "account-holder"
  },
  "tenant_id": "tenant-a",
  "client": {
    "client_id": "finance-app",
    "display_name": "Finance App"
  },
  "resources": ["accounts-api"],
  "scopes": ["balance.read", "transactions.read"],
  "purpose": "personal-finance-dashboard",
  "data_categories": ["account-balance", "transaction-history"],
  "notice": {
    "notice_id": "bank-data-sharing",
    "version": "3.2",
    "locale": "vi-VN",
    "content_hash": "sha256:example-digest"
  },
  "decision": "GRANTED",
  "capture_method": "authenticated-web-consent",
  "captured_at": "2026-11-23T10:30:00Z",
  "status": "ACTIVE",
  "expires_at": "2027-11-23T10:30:00Z",
  "withdrawn_at": null,
  "policy_version": "consent-policy-5"
}
~~~

Các giá trị trong ví dụ là dữ liệu giả. Schema trên là thiết kế ứng dụng minh họa, không phải schema bắt buộc của OAuth/OIDC. Không lưu raw access token, refresh token, mật khẩu hoặc dữ liệu cá nhân không cần thiết trong consent record. Nếu cần lưu bản thông báo chính xác, tham chiếu tới bản nội dung đã version hóa và bảo vệ tính toàn vẹn; một content hash đơn lẻ không chứng minh người dùng thực sự đã nhìn thấy nội dung đó.

## 4. Ghi nhận bằng chứng consent có thể kiểm chứng

### 4.1 Lưu nội dung đã trình bày

Consent record cần liên kết tới phiên bản thông báo mà người dùng đã được trình bày. Phiên bản đó nên bao gồm:

- Tên client và bên nhận dữ liệu.
- Mục đích xử lý được diễn đạt rõ.
- Nhóm dữ liệu hoặc resource được yêu cầu.
- Scope/permission cụ thể và hệ quả thực tế.
- Thời hạn hoặc điều kiện hết hiệu lực nếu có.
- Cách rút lại consent và ảnh hưởng của việc rút lại.
- Ngôn ngữ và phiên bản giao diện/thông báo.

Nếu wording thay đổi đáng kể, không được chỉ cập nhật text tại cùng một version rồi mất khả năng tái dựng nội dung cũ. Giữ các phiên bản thông báo bất biến hoặc lưu bản snapshot được kiểm soát truy cập.

### 4.2 Ghi nhận hành động rõ ràng

Lưu hành động mà người dùng thực hiện: grant, deny, withdraw hoặc update. Không suy diễn consent chỉ từ việc người dùng tiếp tục dùng dịch vụ, không phản hồi hoặc đóng cửa sổ. Với checkbox hay nút đồng ý, giao diện phải thể hiện rõ hành động và phạm vi; không chọn sẵn tùy tiện nếu policy yêu cầu hành động chủ động.

### 4.3 Ghi thời gian và nguồn gốc

Ghi timestamp theo UTC, đồng bộ đồng hồ hệ thống và lưu nguồn phát sinh sự kiện. Có thể lưu request/session reference hoặc audit correlation ID để điều tra, nhưng không lưu toàn bộ request có chứa token hay bí mật.

### 4.4 Bảo vệ tính toàn vẹn

Consent evidence có thể cần chống sửa đổi trái phép. Các biện pháp thường dùng:

- Phân quyền ghi/sửa record theo service identity.
- Dùng append-only event log hoặc audit store có kiểm soát.
- Lưu version và correlation ID để nối các sự kiện grant/update/withdraw.
- Theo dõi ai đã truy cập hoặc thay đổi metadata quản trị.
- Dùng chữ ký, MAC hoặc cơ chế tamper-evident khi mô hình đe dọa yêu cầu.

Không nhất thiết mọi trường dữ liệu đều phải bất biến tuyệt đối. Có thể cập nhật trạng thái hiện tại trong bảng projection, đồng thời giữ event history chỉ-ghi-thêm để truy vết quyết định.

## 5. Vòng đời consent

Consent không phải trạng thái vĩnh viễn. Hệ thống nên mô hình hóa các chuyển đổi rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> ACTIVE: Người có thẩm quyền đồng ý
    PENDING --> DENIED: Từ chối
    ACTIVE --> UPDATED: Thay đổi phạm vi/thông báo
    UPDATED --> ACTIVE: Chấp nhận phiên bản mới
    ACTIVE --> WITHDRAWN: Rút consent
    ACTIVE --> EXPIRED: Hết thời hạn
    DENIED --> PENDING: Yêu cầu mới
    WITHDRAWN --> PENDING: Xin cấp lại
    EXPIRED --> PENDING: Xin cấp lại
~~~

Trạng thái có thể được thiết kế khác tùy domain. Ví dụ, thay đổi consent có thể tạo record mới và liên kết supersedes_consent_id thay vì cập nhật record cũ. Cách tiếp cận event/version giúp giữ lịch sử rõ ràng.

### Grant

Khi chủ thể đồng ý, server lưu bằng chứng, tạo hoặc cập nhật authorization grant, rồi mới cấp token trong phạm vi được phép. Giao dịch giữa consent store và token issuance cần có cơ chế nhất quán: nếu lưu consent thành công nhưng token issuance thất bại, record vẫn phải phản ánh trạng thái hợp lệ; nếu consent chưa được lưu bền vững thì không nên cấp quyền dựa trên một quyết định chưa được ghi nhận.

### Update

Nếu client xin thêm scope, resource hoặc mục đích mới, hệ thống phải đánh giá lại consent. Không tự động mở rộng grant cũ chỉ vì user đã đồng ý một scope khác trước đó. Có thể yêu cầu consent mới cho phần quyền bổ sung và giữ nguyên phần grant còn hiệu lực.

### Withdraw

Khi người dùng rút consent, lưu sự kiện withdraw với thời gian, actor và phạm vi. Cập nhật authorization grant, revoke refresh token/session liên quan và ngăn phát hành token mới dựa trên consent đã rút. Với access token đang còn hiệu lực, cần có cơ chế revoke/introspection/denylist hoặc policy TTL để giới hạn thời gian tiếp tục truy cập.

Việc rút consent không tự động quyết định mọi dữ liệu đã xử lý trước đó phải bị xóa ngay trong mọi trường hợp. Nghĩa vụ tiếp tục lưu, xóa hoặc hạn chế dữ liệu phụ thuộc cơ sở xử lý, nghĩa vụ pháp lý và quy định áp dụng. Hệ thống cần tách **withdraw consent**, **revoke authorization grant** và **data deletion request** thành các hành động liên quan nhưng không đồng nhất.

### Expire

Khi consent hết hạn, không cấp token mới dựa trên record đó. Xử lý token đã cấp trước thời điểm hết hạn theo policy rõ ràng; không giả định token tự hết hạn cùng consent nếu token có exp dài hơn. Nên đặt token TTL phù hợp với thời hạn grant và có kiểm tra trạng thái nếu cần hiệu lực revoke nhanh.

## 6. Liên kết consent với OAuth 2.0/OIDC

### 6.1 Consent trước token issuance

Một authorization server có thể dùng luồng:

1. Xác thực resource owner.
2. Xác định client và redirect URI đã đăng ký.
3. Đánh giá scope/resource được yêu cầu.
4. Tìm consent/grant hiện có, kiểm tra chủ thể, client, tenant, mục đích và trạng thái.
5. Nếu cần, trình bày màn hình consent và lưu quyết định mới.
6. Tạo authorization code hoặc grant phù hợp.
7. Phát hành access token với audience/scope được phép.

Authorization server không được coi tham số scope do client gửi lên là bằng chứng người dùng đã đồng ý. Client chỉ yêu cầu phạm vi; server quyết định có cấp hay không dựa trên policy và consent/authorization tương ứng.

### 6.2 Scope và resource

Scope nên có ý nghĩa rõ, ví dụ balance.read hoặc payments.initiate. Tránh scope quá rộng như all nếu không có ranh giới quyền cụ thể. Khi cần quyền chi tiết theo tài nguyên, OAuth 2.0 Rich Authorization Requests (RFC 9396) định nghĩa tham số authorization_details để biểu diễn yêu cầu quyền có cấu trúc. Điều này có thể giúp hệ thống liên kết consent với resource/action cụ thể, nhưng vẫn không cung cấp một schema consent record chung.

Ví dụ yêu cầu quyền có cấu trúc (rút gọn):

~~~json
{
  "type": "account_information",
  "actions": ["read"],
  "locations": ["accounts-api"],
  "identifier": "account-123"
}
~~~

Consent store có thể tham chiếu đến các authorization details đã được chấp thuận. Khi token được cấp, resource server vẫn cần xác minh token và enforce quyền tương ứng.

### 6.3 Token không phải consent receipt

Access token có thể chứa scope, audience, subject, client và một số claim ứng dụng. Không nên nhồi toàn bộ nội dung consent, bản thông báo, IP, lịch sử thao tác hoặc PII vào JWT. Token có thể được gửi qua nhiều dịch vụ và có thể xuất hiện trong log nếu hệ thống cấu hình sai.

Nếu cần truy xuất consent, token có thể mang một grant ID hoặc consent reference opaque theo policy. Resource server không nên tự tin vào một consent ID chưa được kiểm tra trạng thái; authorization server hoặc policy service cần xác nhận grant còn hiệu lực khi yêu cầu mức cập nhật cao.

## 7. Rút lại consent và đồng bộ revoke

Một sự kiện withdraw cần lan truyền tới các thành phần thực thi quyền:

~~~text
User withdraw
      |
      v
Consent service ----> Consent event/audit log
      |
      +----> Authorization grant disabled
      |
      +----> Refresh token/session revoked
      |
      +----> Access token status / denylist updated
      |
      +----> Resource server / gateway cache invalidated
~~~

Thiết kế event nên có:

- Event ID duy nhất để consumer xử lý idempotent.
- Consent ID, grant ID và phiên bản trạng thái.
- Actor, timestamp và phạm vi bị thay đổi.
- Loại sự kiện: granted, updated, withdrawn, expired.
- Correlation ID để theo dõi quá trình phân phối.

Consumer phải xử lý sự kiện trùng lặp và đến sai thứ tự. Ví dụ, event withdrawn phiên bản 5 không được bị event active cũ phiên bản 4 ghi đè. Dùng version/sequence và quy tắc monotonic để trạng thái thu hồi không bị đảo ngược bởi message cũ.

Đo thời gian từ lúc withdraw được ghi nhận tới khi mọi resource server từ chối token liên quan. Nếu token JWT được xác minh hoàn toàn stateless, hệ thống cần chấp nhận rõ cửa sổ còn hiệu lực tới exp hoặc bổ sung cơ chế trạng thái.

## 8. Quyền riêng tư, lưu trữ và retention

Consent record là dữ liệu có thể gắn với cá nhân. Chỉ lưu những trường cần thiết để chứng minh và thực thi quyết định. Tránh sao chép toàn bộ profile, dữ liệu giao dịch hoặc nội dung token vào audit record.

Các nguyên tắc thiết kế:

- **Data minimization:** lưu subject reference thay vì sao chép thông tin định danh dư thừa.
- **Purpose limitation:** dùng record cho mục đích quản lý consent, kiểm toán và thực thi quyền đã công bố.
- **Access control:** chỉ service/role được phép mới đọc hoặc thay đổi record.
- **Retention:** xác định thời hạn lưu theo mục đích, nghĩa vụ và policy áp dụng.
- **Deletion/anonymization:** xử lý dữ liệu hết hạn theo yêu cầu hợp lệ, nhưng bảo toàn phần audit bắt buộc nếu có cơ sở phù hợp.
- **Encryption:** bảo vệ dữ liệu nhạy cảm khi lưu và truyền; quản lý key riêng.
- **Audit:** ghi lại truy cập và thay đổi đối với consent evidence.

Theo GDPR, khi consent là cơ sở xử lý, tổ chức cần có khả năng chứng minh consent đã được đưa ra; người dùng có quyền rút lại và việc rút lại phải dễ như việc đưa ra consent. GDPR cũng quy định nguyên tắc accountability và các yêu cầu liên quan đến lưu trữ/xóa dữ liệu. Việc áp dụng cụ thể phụ thuộc vai trò controller/processor, loại dữ liệu và cơ sở pháp lý của từng hoạt động.

Không dùng một khoảng retention mặc định cho mọi consent record. Xác định thời hạn theo quy định áp dụng, mục đích chứng minh, thời hiệu khiếu nại và policy nội bộ đã được phê duyệt. Khi cần xóa dữ liệu chủ thể, đánh giá cả consent store, audit store, backup và bản sao downstream.

## 9. Ví dụ kiểm thử consent record

### 9.1 Test cấp consent

Scenario:

1. User A đã xác thực và có membership ở Tenant A.
2. Client finance-app yêu cầu balance.read cho accounts-api.
3. Authorization server trình bày notice version 3.2.
4. User chọn đồng ý.
5. Consent record được lưu với subject, tenant, client, resource, scope, purpose, notice version và timestamp.
6. Authorization server cấp grant/token trong đúng phạm vi.

Assertions:

- Record có trạng thái ACTIVE và decision GRANTED.
- Client/resource/scope trùng với nội dung được chấp thuận.
- Không có scope hoặc resource ngoài yêu cầu được tự động thêm.
- Token có audience đúng và scope không vượt grant.
- Audit event chứa consent ID và correlation ID, không chứa raw token.

### 9.2 Test scope escalation

User đã đồng ý balance.read. Client gửi yêu cầu mới transactions.read hoặc payments.initiate. Hệ thống không được âm thầm mở rộng grant cũ. Cần trình bày và lưu quyết định mới theo policy; nếu user từ chối, token không được chứa scope bổ sung.

### 9.3 Test withdraw

Sau khi consent ACTIVE:

- User rút consent.
- Consent record tạo trạng thái/sự kiện WITHDRAWN.
- Grant bị disable; refresh token/session liên quan bị revoke.
- Token issuance tiếp theo dựa trên grant đó bị từ chối.
- Resource server từ chối access token cũ theo cơ chế revoke đã công bố.
- Event consumer xử lý lại cùng event không làm trạng thái sai.

### 9.4 Test multi-tenant và actor

User A không thể rút consent thuộc Tenant B chỉ bằng cách sửa consent ID. Quản trị viên tenant chỉ được thay đổi consent trong phạm vi role được giao. Nếu admin cấp consent thay mặt tổ chức, record phải ghi actor và vai trò đại diện; không ghi nhầm admin thành subject cá nhân đã đồng ý.

### 9.5 Test version và audit

- Thông báo version 3.2 vẫn truy xuất được sau khi version 3.3 được phát hành.
- Record mới tham chiếu đúng locale và notice version.
- Sửa nội dung thông báo không làm thay đổi bằng chứng của consent cũ.
- Actor không có quyền không thể sửa decision/timestamp.
- Event cũ không ghi đè trạng thái mới hơn.
- Retention job không xóa record còn thuộc thời hạn lưu đã xác định.

## 10. Mô hình Java minh họa

Đoạn code dưới đây mô tả kiểm tra một consent trước khi cấp grant. Đây là logic domain minh họa, không phải thư viện OAuth server hoàn chỉnh.

~~~java
import java.time.Instant;
import java.util.Set;

record ConsentRecord(
        String consentId,
        String subjectId,
        String tenantId,
        String clientId,
        Set<String> scopes,
        Set<String> resources,
        String purpose,
        String noticeVersion,
        String status,
        Instant expiresAt) {}

record TokenRequest(
        String subjectId,
        String tenantId,
        String clientId,
        Set<String> requestedScopes,
        Set<String> requestedResources,
        String purpose) {}

final class ConsentPolicy {
    boolean permits(
            ConsentRecord consent,
            TokenRequest request,
            Instant now) {
        if (consent == null || !"ACTIVE".equals(consent.status())) {
            return false;
        }
        if (consent.expiresAt() != null
                && !now.isBefore(consent.expiresAt())) {
            return false;
        }
        if (!consent.subjectId().equals(request.subjectId())
                || !consent.tenantId().equals(request.tenantId())
                || !consent.clientId().equals(request.clientId())) {
            return false;
        }
        if (!consent.purpose().equals(request.purpose())) {
            return false;
        }
        return consent.scopes().containsAll(request.requestedScopes())
                && consent.resources().containsAll(
                        request.requestedResources());
    }
}
~~~

Trong ứng dụng thật, phải xác minh principal và tenant context trước khi tạo TokenRequest; không nhận các trường này như dữ liệu tự khai từ client. Cần xử lý concurrency giữa consent withdrawal và token issuance bằng transaction, version check hoặc cơ chế đồng bộ phù hợp. Nếu consent bị rút đồng thời với request cấp token, hệ thống phải có quy tắc nhất quán xác định request nào được phép hoàn tất.

## 11. Những sai lầm thường gặp

1. **Coi scope là consent evidence:** scope cho biết quyền trong token, không lưu được nội dung thông báo hay hành động người dùng đã thực hiện.
2. **Chỉ lưu boolean consented=true:** không biết ai đồng ý, với client nào, scope nào, notice version nào và lúc nào.
3. **Không lưu phiên bản thông báo:** không thể tái dựng nội dung được trình bày tại thời điểm cấp.
4. **Cho phép scope tăng tự động:** client có thể nhận thêm quyền mà người dùng chưa chấp thuận.
5. **Rút consent nhưng không revoke grant/token:** request cũ vẫn có thể truy cập trong khi hệ thống hiển thị consent đã rút.
6. **Dùng chung consent giữa tenant:** quyền của một tổ chức bị áp dụng nhầm cho tổ chức khác.
7. **Ghi admin thành subject:** không phân biệt người đại diện phê duyệt và người/chủ thể được xử lý dữ liệu.
8. **Lưu raw token trong audit record:** biến consent store thành nơi chứa credential nhạy cảm.
9. **Xóa record ngay khi withdraw:** có thể làm mất bằng chứng cần thiết; phải áp dụng retention và data protection policy phù hợp.
10. **Cho event cũ ghi đè event mới:** trạng thái ACTIVE có thể xuất hiện trở lại sau WITHDRAWN.

## 12. Checklist triển khai

- [ ] Định nghĩa consent record và phân biệt với OAuth grant, access token, refresh token.
- [ ] Ghi subject, actor, tenant, client, resource, scope, purpose và quyết định.
- [ ] Lưu notice ID/version/locale và bản nội dung có thể truy xuất.
- [ ] Ghi timestamp UTC, capture method và correlation ID.
- [ ] Không lưu raw token, secret hoặc PII không cần thiết.
- [ ] Có state transition rõ cho grant, deny, update, withdraw và expire.
- [ ] Scope/resource/purpose tăng thêm cần đánh giá consent mới theo policy.
- [ ] Withdraw làm grant và token liên quan mất hiệu lực theo SLA đã xác định.
- [ ] Event consumer xử lý idempotent và không cho event cũ ghi đè trạng thái mới.
- [ ] Tenant và actor authorization được kiểm tra khi đọc, sửa hoặc rút consent.
- [ ] Có retention, access control, encryption và audit cho consent evidence.
- [ ] Test cấp, từ chối, cập nhật, rút lại, hết hạn, scope escalation và concurrency.

## Ghi nhớ

**Consent record phải chứng minh một quyết định cụ thể trong một phạm vi cụ thể.** Hãy lưu ai quyết định, cho client nào, trên resource/scope/purpose nào, theo phiên bản thông báo nào và vào thời điểm nào. Liên kết record với authorization grant để kiểm soát token issuance, nhưng giữ bằng chứng consent ở kho riêng. Khi consent thay đổi hoặc bị rút, cập nhật grant, refresh/session, trạng thái access token và cache; đồng thời giữ audit history theo retention policy phù hợp.

### Tài liệu tham khảo

- IETF RFC 6749 — The OAuth 2.0 Authorization Framework, authorization grants và scope: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 9396 — OAuth 2.0 Rich Authorization Requests (RAR): https://www.rfc-editor.org/rfc/rfc9396
- Regulation (EU) 2016/679 (GDPR), đặc biệt Articles 5, 7 và 17: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- European Data Protection Board — Guidelines 05/2020 on consent under Regulation 2016/679: https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052020-consent-under-regulation-2016679_en
