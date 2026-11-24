# Retention token metadata

> **Chương:** Compliance  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Quản lý vòng đời token bảo mật trong xác thực và phân quyền; phân biệt JWT, opaque token, access token, refresh token và OAuth 2.0/OIDC; kiểm soát claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **retention token metadata** và phân biệt thời hạn token với thời hạn lưu metadata liên quan.
2. Xác định metadata cần lưu cho vận hành, thu hồi, chống replay, audit và chứng minh tuân thủ.
3. Phân loại dữ liệu nhạy cảm, dữ liệu định danh và dữ liệu kỹ thuật để áp dụng thời hạn lưu tương ứng.
4. Thiết kế retention policy theo mục đích, vòng đời token, mức độ rủi ro và yêu cầu pháp lý/hợp đồng áp dụng.
5. Quản lý metadata của JWT, opaque access token, refresh token family, token revocation và token exchange.
6. Kiểm thử TTL, xóa dữ liệu, backup, legal hold, quyền truy cập, pseudonymization và khả năng truy vết mà không lưu token thô.

## 1. Retention token metadata là gì?

**Token metadata** là dữ liệu mô tả token hoặc sự kiện liên quan đến token, được dùng để quản lý vòng đời, xác minh trạng thái, điều tra sự cố và chứng minh quyết định bảo mật. **Retention** là thời gian và cách thức dữ liệu đó được giữ, lưu trữ, archive, xóa hoặc ẩn danh sau khi mục đích sử dụng kết thúc.

Ví dụ, một Authorization Server phát hành refresh token cho ứng dụng. Hệ thống có thể cần giữ metadata để biết token thuộc client nào, subject nào, được cấp lúc nào, hết hạn khi nào, đã bị thu hồi chưa và token nào là token kế tiếp trong cùng family. Những thông tin này giúp phát hiện reuse hoặc xử lý revoke. Tuy nhiên, hệ thống không cần lưu raw refresh token trong log để đạt được mục đích đó.

Cần phân biệt ba vòng đời:

- **Token lifetime:** thời gian credential được phép dùng, ví dụ access token hết hạn sau một khoảng thời gian ngắn.
- **Metadata retention:** thời gian giữ bản ghi mô tả token để xác minh trạng thái, hỗ trợ revoke, điều tra và audit.
- **Audit retention:** thời gian giữ bằng chứng về sự kiện bảo mật, quyết định cấp quyền, thu hồi hoặc truy cập dữ liệu.

Ba khoảng thời gian có thể khác nhau. Token hết hạn không có nghĩa metadata phải bị xóa ngay lập tức; ngược lại, nhu cầu audit không phải lý do để giữ raw token vô thời hạn.

~~~mermaid
flowchart LR
    A["Token được phát hành"] --> B["Token đang hoạt động<br/>metadata cần cho validation/revoke"]
    B --> C["Token hết hạn hoặc bị thu hồi"]
    C --> D["Metadata chuyển sang<br/>retention hậu hiệu lực"]
    D --> E["Hết mục đích lưu giữ"]
    E --> F["Xóa / aggregate / anonymize"]
    G["Audit event"] --> H["Retention riêng theo<br/>mục đích và nghĩa vụ"]
~~~

**Nguyên tắc:** Chỉ lưu metadata cần thiết cho một mục đích được xác định, trong thời gian cần thiết, với quyền truy cập và cơ chế xóa phù hợp. Không biến token store, log hoặc backup thành kho lưu trữ bearer credential.

## 2. Phân biệt token, metadata và audit event

| Nhóm | Ví dụ | Mục đích | Rủi ro |
|---|---|---|---|
| Raw credential | JWT access token, opaque token, refresh token, client assertion | Chứng minh quyền truy cập | Người lấy được có thể sử dụng credential |
| Token metadata | token ID/hash, issuer, client ID, subject reference, audience, scope, issued_at, expires_at, status | Quản lý trạng thái và vòng đời | Có thể tiết lộ danh tính, quyền hoặc quan hệ hệ thống |
| Authorization context | tenant, actor, grant, consent reference, resource | Diễn giải phạm vi quyền | Có thể tiết lộ dữ liệu cá nhân và quan hệ tenant |
| Audit event | token issued, exchanged, revoked, introspection denied | Điều tra và chứng minh hành động | Có thể tạo hồ sơ hoạt động dài hạn |
| Operational telemetry | số lượng token, latency, lỗi validation | Giám sát sức khỏe hệ thống | Cardinality cao hoặc label định danh gây rò rỉ |

Raw credential phải được bảo vệ theo yêu cầu nghiêm ngặt hơn metadata. Nếu cần lưu opaque token để server xác minh về sau, nên lưu dạng hash hoặc verifier phù hợp thay vì giá trị token có thể dùng trực tiếp. Với refresh token rotation, cần thiết kế kho token chuyên biệt có mã hóa, phân quyền và cơ chế so sánh an toàn.

Metadata vẫn có thể là dữ liệu nhạy cảm. Ví dụ subject, client ID, tenant ID, audience hoặc scope có thể tiết lộ người dùng thuộc tổ chức nào, ứng dụng nào đang hoạt động hoặc họ có quyền gì. Vì vậy, không mặc định rằng metadata là dữ liệu công khai.

## 3. Những metadata thường cần quản lý

Tùy kiến trúc, một bản ghi token metadata có thể gồm:

| Field | Ý nghĩa | Lưu ý |
|---|---|---|
| token_reference | ID nội bộ hoặc hash định danh token | Không dùng raw token làm khóa tra cứu |
| token_type | access_token, refresh_token hoặc loại khác | Phân biệt loại token và mục đích |
| token_format | jwt hoặc opaque | Chọn quy trình kiểm tra trạng thái phù hợp |
| issuer | Authorization Server phát hành | Ưu tiên issuer alias khi log |
| client_id | OAuth client được xác thực | Có thể ánh xạ sang client alias |
| subject_reference | Chủ thể được token đại diện | Pseudonymize nếu có thể |
| audience/resource | Resource server được phép nhận | Chỉ giữ identifier cần thiết |
| scope/permissions | Quyền được cấp | Tránh lưu toàn bộ claims không cần thiết |
| issued_at | Thời điểm phát hành | Hỗ trợ vòng đời và điều tra |
| expires_at | Thời điểm hết hạn | Dùng để tính thời điểm dọn dẹp |
| status | active, revoked, expired, consumed | Phải có semantics nhất quán |
| revoked_at | Thời điểm thu hồi | Chỉ có khi token bị thu hồi |
| revoke_reason | Lý do chuẩn hóa | Không ghi raw exception/request |
| parent/family reference | Liên kết refresh token rotation | Không lưu credential cha/con thô |
| actor/client context | Service hoặc actor liên quan | Cần phân biệt subject và actor |
| created_at/updated_at | Thời điểm cập nhật metadata | Đồng bộ clock và timezone |
| policy_version | Phiên bản policy cấp token | Hữu ích khi điều tra quyết định cũ |

Không phải hệ thống nào cũng cần tất cả các field. Với JWT tự xác minh offline, resource server có thể không lưu từng token. Với opaque token, Authorization Server thường phải quản lý trạng thái token và introspection metadata. Với refresh token, server thường cần trạng thái, family, reuse detection và quan hệ rotation.

### Tránh schema lưu quá mức

Không sao chép toàn bộ JWT payload vào một cột JSON chỉ để tiện debug. Claims có thể chứa email, tên, nhóm, tenant, quyền, thông tin định danh hoặc dữ liệu riêng tư. Hãy xác định field cụ thể phục vụ validation, revoke hoặc audit và chỉ lưu những field đó.

Nếu cần giữ snapshot policy để tái dựng quyết định cấp token, hãy lưu policy version hoặc một bản ghi quyết định đã giảm dữ liệu, không mặc định lưu toàn bộ token/claims.

## 4. Retention theo loại token

### 4.1. JWT access token

JWT thường có thời hạn trong claim **exp**. Resource server có thể xác minh chữ ký và claims mà không cần tra cứu trạng thái từng token. Do đó:

- Không cần lưu raw JWT trong database chỉ để xác minh chữ ký.
- Có thể lưu metadata cấp token ở Authorization Server nếu cần audit hoặc revoke.
- Nếu dùng denylist theo **jti**, chỉ giữ entry đủ lâu để token không còn được chấp nhận.
- Nếu dùng token version hoặc session state, thời gian lưu phải đáp ứng mục tiêu thu hồi.
- Metadata về signing key/kid và issuer có vòng đời riêng với token.

JWT hết hạn theo exp nhưng log về sự kiện phát hành/thu hồi có thể được giữ lâu hơn theo retention policy riêng. Không kéo dài exp của token chỉ để đáp ứng audit.

### 4.2. Opaque access token

Opaque token thường tham chiếu đến trạng thái được lưu ở Authorization Server hoặc token store. Metadata có thể cần tồn tại trong khi token active và thêm một khoảng hậu hiệu lực để:

- Xác định token đã bị revoke hay hết hạn.
- Phục vụ introspection trong thời gian hệ thống có thể còn nhận request cũ.
- Phát hiện token bị dùng lại sau revoke.
- Hỗ trợ audit và đối soát sự cố.

Khi hết thời hạn cần thiết, token record có thể được xóa hoặc chuyển sang dữ liệu tổng hợp không định danh. Không giữ bản ghi active vô thời hạn chỉ vì chưa có job cleanup.

### 4.3. Refresh token

Refresh token thường có rủi ro cao hơn access token vì có thể xin access token mới. Với rotating refresh token:

- Mỗi lần sử dụng thành công có thể phát hành token kế tiếp và vô hiệu hóa token trước.
- Metadata phải theo dõi family/chain, trạng thái consumed/revoked và thời điểm sử dụng.
- Reuse của token cũ có thể là tín hiệu credential bị đánh cắp.
- Dữ liệu family cần giữ đủ để phát hiện reuse trong phạm vi lifetime và policy của family.
- Khi family bị revoke, các token thành viên cần không còn được chấp nhận theo semantics của Authorization Server.

Không lưu raw refresh token trong log, audit event hoặc analytics. Nếu cần xác minh token nhận được, dùng hash/verifier phù hợp với thiết kế và bảo vệ kho dữ liệu.

### 4.4. ID token và session metadata

ID token OIDC chủ yếu phục vụ client OIDC và thông tin xác thực đăng nhập. Không dùng ID token thay access token cho API. Session metadata, nonce, authentication time và session reference có thể cần retention riêng để hỗ trợ logout, session management hoặc audit. Không sao chép toàn bộ ID token vào log.

## 5. Xác định retention theo mục đích

Không nên đặt một thời hạn duy nhất cho mọi metadata. Trước tiên phải xác định mục đích lưu.

| Mục đích | Metadata cần thiết | Điều kiện kết thúc |
|---|---|---|
| Xác minh token đang active | Token reference, status, exp, revoke state | Token không còn được chấp nhận và hết cửa sổ cần kiểm tra |
| Revocation | Token reference/jti hoặc session/family reference, status | Token không còn hiệu lực và không cần denylist |
| Refresh token reuse detection | Family reference, token generation, consumed/revoked state, timestamps | Hết lifetime và cửa sổ phát hiện reuse theo policy |
| Audit cấp token | Issuer/client/subject reference, time, grant, outcome | Hết thời hạn audit được phê duyệt |
| Điều tra sự cố | Reason code, trace/request reference, token metadata tối thiểu | Hết thời hạn điều tra/security retention |
| Metrics vận hành | Counter, latency, outcome theo label ít giá trị | Theo chu kỳ metrics/monitoring |
| Báo cáo compliance | Dữ liệu tổng hợp, policy version, bằng chứng kiểm soát | Theo yêu cầu pháp lý/hợp đồng và mục đích báo cáo |

Retention phải xuất phát từ mục đích, nghĩa vụ pháp lý/hợp đồng áp dụng và rủi ro. Không tự gán một số ngày chung cho mọi tổ chức. Các thời hạn phải được chủ sở hữu dữ liệu, security, privacy/legal và vận hành phê duyệt theo bối cảnh thực tế.

### Một cách lập retention schedule

Với mỗi loại dữ liệu, ghi:

1. **Data owner:** ai chịu trách nhiệm?
2. **Purpose:** dữ liệu được giữ để làm gì?
3. **Data fields:** chính xác field nào được lưu?
4. **Start event:** đồng hồ retention bắt đầu từ lúc phát hành, hết hạn, thu hồi hay đóng sự cố?
5. **Retention period:** thời hạn đã được phê duyệt.
6. **Storage locations:** database chính, replica, cache, log, SIEM, backup, data lake.
7. **Access roles:** ai được đọc, export hoặc xóa?
8. **Deletion method:** hard delete, purge, cryptographic erase hoặc aggregation.
9. **Exceptions:** legal hold, incident hold hoặc nghĩa vụ lưu trữ bắt buộc.
10. **Evidence:** log job cleanup, kết quả kiểm tra và audit trail.

## 6. Ví dụ retention schedule

Bảng dưới đây là mẫu cấu trúc để tổ chức điền thời hạn theo policy của mình; các giá trị thời hạn không được suy ra từ ví dụ này.

| Dữ liệu | Mốc bắt đầu | Thời hạn được phê duyệt | Sau thời hạn |
|---|---|---|---|
| Active opaque access token metadata | issued_at | Theo exp và cửa sổ revoke/introspection | Purge hoặc archive tối thiểu |
| JWT denylist entry | revoked_at | Tới khi token không còn được chấp nhận | Xóa entry |
| Refresh token family metadata | family created/revoked | Theo family lifetime và reuse detection policy | Purge/aggregate |
| Token issuance audit | event timestamp | Theo audit schedule | Archive hoặc xóa |
| Security incident evidence | incident closure hoặc mốc policy | Theo incident/legal schedule | Legal review, archive hoặc xóa |
| Subject pseudonym mapping | mapping created | Theo mục đích correlation | Xóa mapping/key theo policy |
| Metrics aggregate | observation window | Theo monitoring schedule | Downsample hoặc xóa |
| Backup chứa token metadata | backup creation | Theo backup lifecycle | Expire backup hoặc cryptographic erase |

**Lưu ý:** Một bản ghi token bị revoke có thể cần được giữ trong denylist đến khi exp của token qua đi. Nếu xóa entry quá sớm, resource server có thể chấp nhận lại token còn hạn. Ngược lại, giữ denylist mãi mãi tạo dữ liệu không cần thiết và tăng chi phí.

## 7. Thiết kế TTL và cleanup cho metadata

Metadata có thể được lưu ở relational database, key-value store, cache hoặc token service chuyên dụng. Cần phân biệt TTL logic với việc dữ liệu vật lý thực sự bị xóa.

### TTL logic

Một record có thể có:

- **expires_at:** thời điểm token hết hiệu lực.
- **purge_after:** thời điểm sớm nhất được phép xóa metadata theo policy.
- **revoked_at:** thời điểm thu hồi.
- **status:** trạng thái hiện tại.

Ví dụ quy tắc:

~~~text
if token is active:
    keep metadata while token may be accepted

if token is revoked:
    keep revocation evidence until token can no longer be accepted
    and the required security window has passed

if retention deadline has passed:
    purge or aggregate metadata
    unless a documented hold applies
~~~

### SQL minh họa

~~~sql
CREATE TABLE token_metadata (
    token_ref_hash   VARCHAR(128) PRIMARY KEY,
    issuer_alias     VARCHAR(80) NOT NULL,
    client_alias     VARCHAR(100),
    subject_ref      VARCHAR(128),
    audience_alias   VARCHAR(100),
    token_type       VARCHAR(32) NOT NULL,
    token_status     VARCHAR(24) NOT NULL,
    issued_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at       TIMESTAMP WITH TIME ZONE,
    purge_after      TIMESTAMP WITH TIME ZONE NOT NULL,
    policy_version   VARCHAR(40) NOT NULL
);
~~~

Bảng trên chỉ là ví dụ metadata tối thiểu. token_ref_hash phải được tạo từ token reference bằng cơ chế phù hợp; không lưu raw token trong primary key. Các alias và subject_ref cần được pseudonymize/allowlist theo policy. Tránh lưu scope hoặc claims nhạy cảm nếu không có nhu cầu cụ thể.

Job cleanup có thể chạy định kỳ:

~~~sql
DELETE FROM token_metadata
WHERE purge_after < CURRENT_TIMESTAMP
  AND token_status IN ('expired', 'revoked', 'consumed');
~~~

Đây chỉ là ví dụ đơn giản. Production cần xử lý batch size, index, lock contention, transaction duration, partitioning, replica lag, audit evidence và legal hold. Nếu bảng có foreign key hoặc token family relationship, cần xóa theo thứ tự hoặc chính sách cascade đã được kiểm tra. Không xóa record đang bị hold.

### TTL của cache khác retention database

Cache token/introspection có thể cần TTL ngắn để giảm độ trễ. TTL cache không thay thế retention policy của database/audit. Khi revoke, phải có cách invalidate cache hoặc giới hạn độ trễ stale theo yêu cầu bảo mật.

## 8. Revocation và thời gian giữ metadata

OAuth 2.0 Token Revocation (RFC 7009) cho phép client yêu cầu thu hồi token qua revocation endpoint. Token status và cách resource server nhận biết revoke phụ thuộc loại token và kiến trúc.

### JWT self-contained

Nếu resource server xác minh JWT offline, việc Authorization Server revoke một token không tự động làm mọi resource server biết token đã bị thu hồi. Một số thiết kế dùng:

- Token lifetime ngắn.
- Denylist theo jti hoặc token reference.
- Token introspection thay vì chỉ xác minh offline.
- Session/token version check.
- Key rotation trong tình huống compromise ở phạm vi phù hợp.

Nếu dùng denylist, metadata phải được giữ đủ đến khi JWT không còn có thể được chấp nhận. Ví dụ token đã revoke nhưng còn thời hạn hợp lệ; xóa denylist trước exp có thể khiến token được chấp nhận lại ở resource server có cache hoặc không có state khác.

### Opaque token

Opaque token thường có trạng thái tập trung. Introspection (RFC 7662) có thể trả về active=false sau revoke, nhưng cache ở resource server có thể làm chậm hiệu lực. Retention phải tính cả introspection cache TTL, retry, replica và thời gian propagation.

### Refresh token family

Khi refresh token reuse được phát hiện, server có thể revoke token family hoặc session theo policy. Metadata family cần tồn tại đủ lâu để phân biệt token cũ bị replay với token không còn liên quan. Không xóa lịch sử generation ngay khi token mới được phát hành nếu reuse detection còn phụ thuộc lịch sử đó.

## 9. Metadata và chống replay

Metadata có thể hỗ trợ phát hiện replay nhưng không tự ngăn replay. Một số cơ chế:

- **jti:** JWT ID duy nhất, có thể dùng để tra cứu hoặc phát hiện token lặp theo profile.
- **Refresh token family:** phát hiện refresh token cũ được dùng lại.
- **Nonce/replay cache:** lưu nonce hoặc request identifier trong cửa sổ ngắn nếu giao thức yêu cầu.
- **DPoP proof metadata:** theo dõi proof identifier/jti và thời điểm để phát hiện proof bị phát lại theo profile.
- **mTLS certificate binding:** kiểm tra token gắn với chứng chỉ client; không chỉ lưu thumbprint mà bỏ qua xác minh chứng chỉ thực tế.

### Lưu replay metadata trong bao lâu?

Retention của replay cache thường gắn với **cửa sổ chấp nhận replay** của giao thức và clock skew. Nếu xóa nonce/jti quá sớm, một proof/token có thể được chấp nhận lại trong thời gian còn hợp lệ. Nếu giữ quá lâu, cache tăng không cần thiết.

Cần xác định:

- Proof/token có lifetime bao lâu?
- Clock skew được phép bao nhiêu?
- Request có thể retry hợp lệ không?
- Replay detection có cần phân biệt retry idempotent?
- Các node có dùng chung replay store hoặc đồng bộ state không?
- Khi store không khả dụng, hệ thống fail closed hay áp dụng chế độ dự phòng nào?

Không dùng raw access token làm replay key. Dùng identifier hoặc hash phù hợp, có TTL và namespace theo issuer/client/protocol.

## 10. Pseudonymization và minimization metadata

Một số trường như subject, tenant hoặc client ID có thể được biến đổi để giảm khả năng nhận diện trực tiếp.

### Pseudonymization

Có thể tạo subject reference bằng HMAC-SHA-256:

~~~text
subject_ref = HMAC-SHA-256(
    dedicated_key,
    purpose + environment + issuer + tenant + subject
)
~~~

Điều này cho phép correlation trong phạm vi được thiết kế mà không ghi raw subject. Khóa HMAC phải được quản lý riêng, có version, rotation và quyền truy cập tối thiểu. Pseudonymization không phải anonymization; subject_ref vẫn có thể liên kết các hoạt động và phải được bảo vệ.

### Minimization theo field

| Field | Cách giảm dữ liệu |
|---|---|
| issuer | Alias từ allowlist |
| client_id | Client alias hoặc client class |
| subject | HMAC reference hoặc subject category |
| tenant_id | Tenant alias/pseudonymous reference |
| audience | Resource alias |
| scope | Chỉ lưu scope cần thiết hoặc scope summary |
| jti | Hash/reference nếu cần correlation |
| timestamps | Precision phù hợp mục đích |
| IP address | Rút gọn/pseudonymize nếu không cần IP đầy đủ |
| user-agent | Chỉ lưu loại/phiên bản cần thiết nếu đủ |

Không pseudonymize theo cách phá hỏng mục đích bảo mật. Ví dụ, nếu cần revoke token theo jti, server phải có một identifier ổn định có thể so sánh; có thể lưu hash/reference được tính nhất quán. Cần kiểm tra khả năng collision và rotation key ảnh hưởng đến lookup.

## 11. Audit retention và operational retention

Không nên dùng một stream duy nhất cho mọi nhu cầu.

### Operational log

Mục đích là vận hành và troubleshooting:

- Lỗi token validation, introspection, token exchange.
- Thời gian phản hồi, outcome, reason code.
- Issuer/client alias, subject reference theo policy.
- Trace ID, service, deployment version.

Operational log thường cần schema tối giản và retention ngắn hơn audit nếu không có nghĩa vụ khác.

### Security audit

Mục đích là tái dựng hành động bảo mật:

- Ai/actor nào yêu cầu cấp hoặc revoke token?
- Client nào được xác thực?
- Token type, grant type, audience và scope được cấp?
- Quyết định policy nào được áp dụng?
- Sự kiện nào dẫn tới revoke, reuse detection hoặc access denied?
- Ai đã xem/export metadata nhạy cảm?

Audit record cần tính toàn vẹn, kiểm soát quyền, đồng bộ thời gian và retention theo policy được phê duyệt.

### Compliance evidence

Bằng chứng tuân thủ có thể là policy version, cấu hình retention, kết quả cleanup, access review và kiểm thử định kỳ. Không cần giữ raw token để chứng minh đã áp dụng retention policy. Có thể lưu bằng chứng đã giảm dữ liệu, hash manifest hoặc báo cáo tổng hợp theo yêu cầu.

## 12. Legal hold, incident hold và ngoại lệ retention

Trong một số tình huống, dữ liệu đáng lẽ hết hạn có thể phải giữ lại để điều tra sự cố, xử lý tranh chấp hoặc đáp ứng nghĩa vụ pháp lý/hợp đồng. Đây là ngoại lệ có kiểm soát, không phải lý do để tắt cleanup toàn hệ thống.

Một hold cần có:

- Người/phòng ban có thẩm quyền phê duyệt.
- Mục đích và phạm vi dữ liệu cụ thể.
- Thời điểm bắt đầu và người chịu trách nhiệm.
- Các hệ thống/bản sao bị ảnh hưởng.
- Quyền truy cập hạn chế và audit việc đọc/export.
- Ngày review lại và điều kiện giải phóng hold.
- Quy trình xóa sau khi hold kết thúc nếu không còn mục đích khác.

Không tự suy đoán rằng mọi dữ liệu token phải được giữ vì có thể phát sinh tranh chấp. Quyết định legal hold phải theo quy trình pháp lý/privacy của tổ chức và phạm vi nghĩa vụ thực tế.

## 13. Xóa dữ liệu, backup và bản sao

Một lệnh DELETE trong database chính không có nghĩa dữ liệu đã biến mất khỏi mọi nơi. Metadata có thể tồn tại trong:

- Read replica hoặc replica chậm.
- Cache, search index và materialized view.
- Log aggregation/SIEM.
- Data lake, warehouse và export file.
- Backup, snapshot, archive.
- Crash dump, support bundle hoặc file tạm.
- Replication stream và dead-letter queue.

### Thiết kế deletion workflow

1. Xác định token metadata record và mọi bản sao theo data inventory.
2. Kiểm tra legal/incident hold.
3. Xóa hoặc ẩn danh ở nguồn chính theo policy.
4. Invalidate cache và xóa search index/derived data.
5. Đảm bảo bản sao backup hết hạn theo lịch hoặc dùng cryptographic erase nếu kiến trúc hỗ trợ.
6. Ghi deletion event không chứa raw token/PII.
7. Xác minh bằng kiểm tra có giới hạn quyền, không tái tạo dữ liệu đã xóa.
8. Giữ bằng chứng deletion theo retention của compliance evidence.

Nếu backup không hỗ trợ xóa từng record, policy cần nêu rõ thời hạn backup, hạn chế restore, quy trình reapply deletion tombstones sau restore và cách ngăn dữ liệu đã hết retention quay lại môi trường production.

### Cryptographic erase

Nếu dữ liệu được mã hóa bằng data encryption key riêng cho tenant hoặc nhóm dữ liệu, hủy khóa có thể làm dữ liệu không thể giải mã. Cách này chỉ có ý nghĩa nếu mọi bản sao ciphertext đều phụ thuộc khóa đó và không còn bản sao plaintext/key ở nơi khác. Không coi cryptographic erase là bảo đảm tự động nếu kiến trúc key management chưa được kiểm chứng.

## 14. Ví dụ Java quản lý purge deadline

Một hàm tính purge deadline cần dựa trên retention policy được cấu hình, không hardcode một thời hạn dùng chung cho mọi token:

~~~java
import java.time.Instant;
import java.time.Duration;

public record TokenRetentionPolicy(
        Duration postExpiryWindow,
        Duration auditRetention
) {
    public Instant purgeAfter(Instant tokenExpiry) {
        return tokenExpiry.plus(postExpiryWindow);
    }
}
~~~

Ví dụ này chỉ minh họa tính toán. Policy thực tế phải phân biệt metadata vận hành, denylist, refresh family và audit event. Với token bị revoke, thời điểm purge có thể phải dựa trên max(exp, revoked_at + security_window) cùng retention được phê duyệt.

Không để service tự chọn retention dựa trên dữ liệu client gửi. Cấu hình policy phải có version, owner và audit thay đổi. Cần xử lý timestamp theo UTC và đồng bộ clock để tránh purge trước hạn.

### Quy tắc tổng quát minh họa

~~~text
purge_after =
    max(
        token_expiry,
        revoked_at + required_revocation_window,
        family_reuse_detection_until
    )
    + approved_metadata_retention
~~~

Đây là mô hình minh họa, không phải công thức áp dụng cho mọi hệ thống. Chỉ giữ các mốc có liên quan đến loại record; không cộng các khoảng thời gian tùy tiện nếu policy đã định nghĩa một deadline tuyệt đối.

## 15. Kiểm thử retention policy

Retention cần được kiểm thử như một chức năng bảo mật và compliance, không chỉ là job dọn database.

| Test case | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Token còn active | expires_at ở tương lai | Metadata không bị purge |
| Token vừa hết hạn | Chưa qua purge_after | Metadata còn theo policy |
| Token expired quá hạn lưu | purge_after đã qua | Record được purge/aggregate |
| Token revoked còn trong thời hạn có thể bị replay | Denylist/revoke metadata còn cần thiết | Không xóa sớm |
| JWT jti denylist | Token còn exp | Entry vẫn chặn token |
| Refresh family có token cũ consumed | Còn reuse detection window | Family metadata được giữ |
| Refresh family hết retention | Không còn hold | Metadata được xóa theo policy |
| Legal hold active | purge_after đã qua | Record được giữ đúng phạm vi hold |
| Legal hold released | Không còn mục đích lưu | Record được đưa vào cleanup |
| Backup restore | Có deletion tombstone | Dữ liệu hết retention không quay lại active store |
| Cache stale | Token đã revoke | Cache invalidated trong SLA |
| Replica lag | Record đã purge ở primary | Không tạo bản sao active ngoài policy |
| Subject pseudonym rotation | Key version mới | Lookup/correlation theo policy, không fallback raw subject |
| Access review | User không có quyền | Không đọc/export metadata nhạy cảm |
| Log redaction | Phát hành/revoke token | Không có raw token, secret hoặc Authorization header |
| Job lỗi giữa batch | Cleanup dừng giữa chừng | Retry idempotent, không bỏ sót record |
| Clock skew | Thời gian node lệch trong giới hạn | Không purge trước deadline |
| Duplicate events | Event revoke/expire gửi lặp | Metadata status nhất quán, không lỗi side effect |

### Test deletion có thể chứng minh điều gì?

- Record không còn trong store đang hoạt động.
- Cache/index được invalidated.
- Backup tuân thủ lịch expire hoặc quy trình restore không phục hồi dữ liệu đã xóa.
- Event deletion không chứa credential.
- Legal hold không bị cleanup bỏ qua.
- Job có thể chạy lại an toàn sau lỗi.
- Báo cáo số record đã xóa/giữ lại có thể đối soát mà không lộ nội dung record.

Không chỉ test số lượng record. Cần test một số record đại diện qua các lớp storage, nhưng tránh xuất raw subject/token vào báo cáo kiểm thử.

## 16. Monitoring và bằng chứng vận hành

Các metric hữu ích:

- Số metadata record theo trạng thái và loại token.
- Số record quá purge_after nhưng chưa được xử lý.
- Tuổi lớn nhất của record expired/revoked còn trong active store.
- Số refresh token reuse detection event.
- Số revoke request và thời gian propagation.
- Cleanup job success/failure, batch duration và retry.
- Số record đang nằm trong legal/incident hold.
- Cache invalidation latency.
- Số lần restore phát hiện deletion tombstone cần áp dụng.

Không đưa raw subject, token ID hoặc client ID có cardinality cao vào metric labels. Dùng nhóm token type, issuer alias, outcome, environment và reason code có tập giá trị giới hạn.

### Báo cáo compliance

Một báo cáo có thể thể hiện:

- Retention policy version và ngày phê duyệt.
- Các loại metadata nằm trong phạm vi.
- Tỷ lệ cleanup job thành công.
- Số record quá hạn đang chờ xử lý.
- Các ngoại lệ hold và owner.
- Kết quả access review và deletion test.
- Vấn đề tồn đọng và thời hạn khắc phục.

Báo cáo không cần chứa raw token hoặc danh sách subject. Khi cần kiểm tra record cụ thể, dùng quy trình truy cập có audit.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng token exp làm retention của mọi dữ liệu | Audit bị xóa quá sớm hoặc metadata bị giữ quá lâu | Schedule riêng cho token, metadata và audit |
| Lưu raw JWT/refresh token trong log | Credential bị lộ qua SIEM hoặc backup | Allowlist metadata, redaction trước log sink |
| Xóa denylist ngay khi revoke | JWT còn hạn có thể được chấp nhận lại | Giữ entry tới khi token không còn được chấp nhận |
| Giữ refresh family vô thời hạn | Tăng dữ liệu và rủi ro riêng tư | Purge sau lifetime và reuse detection window |
| Chỉ xóa database chính | Metadata còn trong cache, backup, SIEM | Deletion inventory và workflow nhiều lớp |
| Cleanup không xét legal hold | Mất bằng chứng phải giữ | Hold registry và kiểm tra trước purge |
| Dùng raw subject làm partition/metric label | Rò rỉ và cardinality cao | Pseudonymization/alias và aggregate |
| Không version retention policy | Khó giải thích vì sao record được giữ/xóa | Gắn policy version và audit thay đổi |
| Clock lệch giữa node | Xóa sớm hoặc giữ quá hạn | UTC, NTP và safety margin |
| Cleanup job không idempotent | Xóa sót hoặc side effect khi retry | Batch transaction và idempotent design |
| Restore backup không áp deletion tombstone | Dữ liệu đã xóa xuất hiện lại | Reapply deletion policy sau restore |
| Legal hold không có expiry/review | Ngoại lệ trở thành lưu trữ vô thời hạn | Owner, review date và release workflow |

## 18. Tình huống thực tế

### Tình huống A — JWT đã hết hạn nhưng audit cần được giữ

Một access token JWT có exp đã qua. Resource server không còn chấp nhận token. Tuy nhiên, audit event cho biết token đã được cấp cho client nào, audience nào và bị revoke hay không vẫn cần thiết cho điều tra trong thời hạn đã phê duyệt.

**Phân tích:** Token lifetime đã kết thúc, nhưng audit retention có mục đích riêng. Giữ event tối thiểu đã pseudonymize, không giữ raw JWT.

### Tình huống B — Denylist bị xóa quá sớm

Một JWT bị revoke khi còn thời hạn. Cleanup job xóa denylist entry ngay sau khi revoke. Resource server xác minh offline và không có trạng thái khác, nên token vẫn có thể được chấp nhận.

**Phân tích:** Denylist metadata phải tồn tại đủ lâu để token không còn hợp lệ theo tất cả verifier. Cleanup cần căn cứ exp, clock skew và cache/policy propagation.

### Tình huống C — Refresh token reuse sau rotation

Refresh token v1 đã được dùng để phát v2. Kẻ tấn công gửi lại v1 trong thời gian family còn được theo dõi. Nếu metadata v1 đã bị xóa ngay sau khi phát v2, Authorization Server có thể không nhận ra reuse.

**Phân tích:** Giữ generation/state của family trong reuse detection window. Không giữ raw refresh token; dùng reference/hash và trạng thái consumed/revoked.

### Tình huống D — Backup restore làm dữ liệu quay lại

Một metadata record đã bị xóa khỏi database chính nhưng còn trong snapshot. Khi restore môi trường, record xuất hiện lại và được coi là active.

**Phân tích:** Backup restore phải áp dụng deletion tombstone hoặc cleanup policy trước khi mở hệ thống cho traffic. Không để record đã hết retention trở lại luồng xác thực.

### Tình huống E — Điều tra yêu cầu raw subject

Đội security muốn tìm subject thật sau khi phát hiện token bị lạm dụng. Log vận hành chỉ có subject_ref.

**Phân tích:** Nếu cần mapping, dùng quy trình break-glass/authorized lookup có lý do, phê duyệt, audit và giới hạn dữ liệu. Không mặc định bật raw subject logging trên toàn bộ production để tiện điều tra.

## 19. Checklist retention token metadata trước production

- Đã phân biệt token lifetime, metadata retention và audit retention chưa?
- Có inventory cho JWT, opaque token, access token, refresh token, token family, denylist và introspection metadata?
- Mỗi field có purpose, owner, sensitivity và retention deadline rõ ràng?
- Có tránh lưu raw token, refresh token, Authorization header, secret và private key không?
- Subject/client/tenant có được pseudonymize hoặc alias khi có thể không?
- Denylist và replay metadata có được giữ đủ lâu để token/proof không thể được chấp nhận lại?
- Refresh token family có đủ metadata để phát hiện reuse trong cửa sổ policy?
- Cleanup job có idempotent, batch-safe, quan sát được và kiểm tra legal hold không?
- Cache, replica, SIEM, data lake và backup có nằm trong deletion inventory không?
- Restore có áp dụng deletion tombstone trước khi đưa dữ liệu vào sử dụng?
- Có access control, encryption, audit search/export và review quyền đọc metadata?
- Có test clock skew, job retry, cache invalidation, revoke propagation và backup restore?
- Retention schedule đã được security/privacy/legal/data owner phê duyệt theo nghĩa vụ áp dụng chưa?
- Có bằng chứng thực thi retention mà không cần giữ raw credential?

## 20. Tổng kết

**Retention token metadata** là việc quản lý thời gian lưu giữ dữ liệu mô tả token và các sự kiện liên quan để phục vụ xác minh trạng thái, thu hồi, chống replay, điều tra và audit. Nó phải được thiết kế riêng theo loại token và mục đích lưu.

JWT, opaque access token, refresh token, denylist entry, token family, introspection cache và audit event có vòng đời khác nhau. Metadata phục vụ revoke hoặc replay detection phải còn tồn tại đủ lâu để token không thể được chấp nhận lại; audit record có thể cần retention riêng. Khi hết mục đích, dữ liệu phải được xóa, aggregate hoặc anonymize theo policy, bao gồm cả cache, replica, archive và backup.

Trong hệ thống OAuth 2.0/OIDC, không lưu raw access token, refresh token, client secret hoặc private key trong log để đáp ứng compliance. Hãy ưu tiên token reference/hash, issuer/client alias, subject reference được pseudonymize, policy version và reason code. **Một retention policy tốt vừa giữ đủ bằng chứng và trạng thái cần thiết cho bảo mật, vừa giới hạn thời gian tồn tại của dữ liệu định danh và credential trong toàn bộ hệ thống.**
