# Ghi nhận consent version

Một người dùng kết nối ứng dụng **Sales Report** với hệ thống đơn hàng vào tháng 9. Màn hình lúc đó ghi: “Cho phép ứng dụng xem đơn hàng”, tương ứng quyền **orders:read**. Tháng 11, sản phẩm bổ sung quyền **orders:export**, thay đổi câu chữ thành “Xem và xuất dữ liệu đơn hàng” rồi vẫn lưu duy nhất **consented=true** trong database. Khi có khiếu nại “Tôi đã đồng ý xuất dữ liệu từ bao giờ?”, hệ thống không trả lời được: người dùng đã thấy văn bản nào, quyền nào, thuộc client/tenant nào và chính sách đang ở phiên bản nào?

Đó là lý do cần **ghi nhận consent version**. Không chỉ lưu “người dùng đã bấm Cho phép”, Authorization Server hoặc hệ thống quản lý ủy quyền cần biết **quyết định đó gắn với chính xác nội dung và phạm vi quyền nào tại thời điểm ra quyết định**. Khi nội dung, quyền, mục đích, tenant hoặc chính sách thay đổi, phiên bản được ghi lại giúp hệ thống xác định **grant cũ còn phù hợp, cần thu hẹp, cần cấp lại hay cần yêu cầu consent mới**.

**Nguyên tắc cốt lõi:** lưu **quyết định chấp thuận/từ chối cùng một phiên bản nội dung được trình bày bất biến và snapshot quyền thực sự được xem xét**, gắn đúng chủ thể, OAuth client, resource, tenant, thời điểm và trạng thái grant. Consent version là dữ liệu nghiệp vụ/audit của hệ thống; **OAuth 2.0 không định nghĩa một claim tiêu chuẩn bắt buộc tên consent_version trong mọi access token**.

Bài học thuộc chương **Consent** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối việc phiên bản hóa consent với mô hình tin cậy và vòng đời token: JWT/opaque access token, refresh token, OAuth 2.0/OpenID Connect (OIDC), issuer, scope, audience, cấp phát, xác minh, thu hồi và ngăn credential bị lạm dụng hoặc phát lại.

Sau bài học, bạn có thể phân loại các loại version cần lưu, thiết kế consent record/event, ràng buộc phiên bản với màn hình và giao dịch OAuth, đánh giá thay đổi nào cần hỏi lại, triển khai kiểm soát đồng thời và kiểm thử toàn bộ vòng đời từ **Approve → Grant → Issue token → Revoke/Re-consent**.

## 1. Ghi nhận consent version giải quyết vấn đề gì?

Consent trong một luồng OAuth thường là **quyết định cho phép một client được thực hiện những quyền đã được mô tả**, khi loại flow và policy yêu cầu. **Version** trả lời thêm câu hỏi: “Quyết định ấy được đưa ra **trên nội dung và tập quyền nào**?”

Ba câu hỏi phải được trả lời tách bạch:

| Câu hỏi | Ví dụ | Dữ liệu chứng minh |
|---|---|---|
| **Ai đã quyết định?** | user-42 trong tenant-A | Subject/actor đáng tin, phương thức/quyền ra quyết định |
| **Quyết định điều gì?** | Cho Sales Report đọc đơn hàng, không cho xuất dữ liệu | Client, resource, scope và snapshot điều khoản được trình bày |
| **Theo phiên bản và trạng thái nào?** | Consent screen v2, policy v5, grant revision 3 | Version identifiers, nội dung bất biến hoặc tham chiếu bền vững, timestamps và sự kiện thay đổi |

Nếu chỉ có:

~~~json
{
  "userId": "user-42",
  "clientId": "sales-report",
  "consented": true
}
~~~

thì không biết quyền được đồng ý, phiên bản nội dung, tenant, thời điểm, người quyết định có thẩm quyền hay không, hoặc consent đã bị thu hồi chưa. Một boolean như vậy dễ dẫn tới lỗi **quyền mới vô tình kế thừa sự đồng ý cũ**.

**Ghi nhận version không phải để tự động hợp pháp hóa quyền truy cập.** Việc lưu một consent record đẹp vẫn không thay thế kiểm tra grant tại AS và authorization theo tài nguyên ở Resource Server.

## 2. Consent, grant, token và phiên bản không phải cùng một đối tượng

Trong một hệ thống có Authorization Server (AS), các lớp liên quan có vòng đời khác nhau:

| Đối tượng | Ý nghĩa | Vì sao cần phân biệt version? |
|---|---|---|
| **Consent presentation** | Nội dung người ra quyết định thực sự được hiển thị | Có thể chỉnh câu chữ, ngôn ngữ, tên ứng dụng và mô tả quyền |
| **Consent decision event** | Hành động Approve/Deny hoặc quyết định từ một nguồn có thẩm quyền | Một sự kiện lịch sử cần lưu nguyên ngữ cảnh |
| **Authorization grant** | Cơ sở ủy quyền AS chấp nhận để cấp token | Có thể bị giới hạn, thay thế, mở rộng, hết hạn hoặc thu hồi |
| **Grant revision** | Lần thay đổi trạng thái/quyền của grant | Giúp kiểm soát cập nhật đồng thời và truy vết quyền thực tế |
| **Access token** | Credential gọi Resource Server với audience/scope/thời hạn được cấp | Có thể còn hạn dù grant đã thay đổi nếu không có kiểm tra trạng thái |
| **Refresh token** | Credential xin access token mới tại token endpoint khi được phép | Cần kiểm grant còn hiệu lực, client binding và revocation |

Ví dụ **presentation version 2** không có nghĩa “access token đời 2”. Khi AS thay đổi văn bản consent, access token cũ **không tự thay đổi**; khi AS thu hồi grant, **presentation version vẫn cần giữ lịch sử** để chứng minh trước đó người dùng đã xem nội dung nào.

Tương tự, một **grant revision** tăng vì thu hồi, thay đổi scope hoặc ghi nhận quyết định mới **không đồng nghĩa mỗi lần AS refresh access token đều phải hiện màn hình consent**. Re-consent phụ thuộc **chính sách cấp quyền**, không chỉ con số revision.

## 3. Nên phiên bản hóa những thứ gì?

Một trường duy nhất **consent_version=3** thường không đủ vì nhiều thứ thay đổi độc lập. Nên làm rõ **version của đối tượng nào**:

| Loại version | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Presentation/content version** | Người dùng đã nhìn thấy mô tả chính xác nào? | consent-screen-v3 |
| **Scope catalog version** | Scope **orders:read** được diễn giải/thực thi ra sao tại thời điểm đó? | scope-catalog-v4 |
| **Grant revision** | Quyền và trạng thái grant đã thay đổi bao nhiêu lần? | revision=7 |
| **Authorization policy version** | Chính sách AS dùng để xác định quyền tối đa là bản nào? | authz-policy-v12 |
| **Client registration version** | Tên, publisher, redirect, các quyền được phép của client tại thời điểm đó? | client-reg-v5 |
| **Localized content version** | Bản tiếng Việt/Anh được hiển thị thực tế là bản nào? | vi-VN-v3 / en-US-v3 |
| **Terms/privacy document version** | Điều khoản hay thông báo quyền riêng tư nào được trình bày nếu có? | notice-2026-11 |

Không phải lúc nào cũng cần **mọi trường** trong bảng. Yêu cầu thực tế phụ thuộc sản phẩm, quy trình ủy quyền, audit, hợp đồng và nghĩa vụ liên quan. Nhưng nếu thông tin **ảnh hưởng đến ý nghĩa quyết định cấp quyền**, phải có cách chứng minh phiên bản hoặc snapshot phù hợp.

**Đừng gộp consent OAuth với consent theo pháp luật dữ liệu cá nhân.** Một OAuth consent screen version có thể giúp audit quyết định ủy quyền API; nó **không tự chứng minh** sự đồng ý hợp lệ cho mọi mục đích xử lý dữ liệu, quảng cáo hoặc điều khoản pháp lý. Nếu hệ thống cần quản lý các loại đồng ý ấy, phải có mô hình, mục đích và yêu cầu chứng cứ riêng.

### Version number, hash và snapshot có vai trò khác nhau

- **Version number** giúp nhận diện và so sánh bản phát hành theo quy tắc quản trị.
- **Content hash** giúp nhận biết bytes/tài liệu đã thay đổi so với snapshot được lưu.
- **Immutable snapshot** hoặc tham chiếu đến nội dung bất biến cho phép đọc lại đúng những gì đã được trình bày.

Hash **không tự chứng minh** rằng đúng người đã nhìn thấy tài liệu hoặc đã bấm Approve. Muốn có chuỗi chứng cứ đáng tin còn cần **transaction binding, audit, quyền quản trị nội dung và tính toàn vẹn lưu trữ**.

## 4. Minh họa lịch sử version: không nâng quyền bằng consent cũ

Giả sử Sales Report phát triển qua ba giai đoạn:

| Thời điểm | Phiên bản consent presentation | Quyền mô tả/được xin | Hệ quả |
|---|---|---|---|
| 01/09 | **v1** | orders:read | Người dùng chỉ có thể chấp thuận quyền đọc |
| 01/10 | **v2** | orders:read, mô tả chi tiết dữ liệu đọc | Có thể là thay đổi câu chữ; cần đánh giá materiality |
| 01/11 | **v3** | orders:read + orders:export | Thêm năng lực xuất; không được tự coi người dùng v1 đã cho phép |

Tình huống:

~~~text
User: user-42, Tenant: tenant-A
Approval trước đây:
  presentation_version = v1
  approved_scopes      = [orders:read]
  resource             = orders-api

Authorization request mới:
  requested_scopes     = [orders:read, orders:export]
~~~

Hệ thống **không được** chỉ thấy user có một record **APPROVED** rồi cấp cả hai scope. AS cần đánh giá:

1. Client có quyền **xin orders:export** theo client registration không?
2. User/tenant có quyền được cho phép xuất đơn hàng không?
3. Grant hiện tại có bao gồm orders:export không? **Không**.
4. Chính sách có cần hiển thị và chấp thuận phiên bản **v3** hoặc một quyết định cấp quyền mới không?
5. Nếu user từ chối quyền bổ sung, quyền đọc đã được cấp trước đó **còn hợp lệ không** theo policy?

**Consent v1 không tự mở rộng thành consent v3.** Ngược lại, chỉnh một lỗi chính tả không ảnh hưởng ý nghĩa quyền có thể không cần buộc toàn bộ người dùng xác nhận lại — quyết định này thuộc **chính sách có kiểm soát**, không phải phép so sánh version number máy móc.

## 5. Consent version phải gắn với giao dịch OAuth cụ thể

Trong Authorization Code + PKCE Flow, consent diễn ra ở **authorization endpoint**, trước khi client đổi authorization code tại token endpoint.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Consent/Grant Store
    participant RS as Resource Server
    C->>AS: Authorization request + state + PKCE challenge
    AS->>AS: Xác thực user, kiểm client/scope/resource
    AS->>DB: Load presentation version đang được phép
    DB-->>AS: v3 + immutable content digest
    AS->>U: Hiển thị chính v3 với quyền được xin
    U->>AS: Approve/Deny cho transaction này
    AS->>DB: Atomic check version, actor, policy và grant
    DB-->>AS: Decision event + grant revision nếu approve
    alt Approve hợp lệ
        AS-->>C: Authorization code + state
        C->>AS: POST token endpoint, code + PKCE verifier
        AS->>AS: Kiểm code/grant/client/redirect và giới hạn quyền
        AS-->>C: Access token đúng audience/scope
        C->>RS: Bearer access token
        RS->>RS: Validate token và quyền tài nguyên
    else Deny
        AS-->>C: access_denied tại redirect hợp lệ
    end
~~~

Điều cần lưu **theo đúng authorization transaction**:

~~~text
transaction_id        = tx-901
expected_issuer       = https://auth.example.org
client_id             = sales-report
subject_ref           = user-42
tenant_ref            = tenant-A
redirect_uri          = https://app.example.org/oauth/callback
requested_resource    = orders-api
requested_scopes      = orders:read orders:export
presentation_version  = consent-screen-v3
presentation_digest   = sha256:<content-hash>
presentation_locale   = vi-VN
pkce_challenge_ref    = <bound-to-authorization-code>
status                = WAITING_FOR_DECISION
~~~

Những giá trị chỉ để minh họa, không phải schema OAuth. **state** của OAuth client, **PKCE** và **consent transaction ID** giải quyết những ranh giới khác nhau: client kiểm response thuộc phiên mình; AS kiểm chứng cứ đổi code; AS lưu quyết định chấp thuận đúng nội dung/giao dịch.

**Đừng lấy một consent_version do browser tự gửi rồi tin nó là phiên bản đã hiển thị.** AS cần lưu nó ở trạng thái server-side hoặc một payload được bảo vệ toàn vẹn, gắn với phiên giao dịch đã xác thực.

## 6. Chứng minh nội dung đã hiển thị: snapshot và digest

Một phiên bản consent có thể có nhiều ngôn ngữ, phiên bản giao diện hoặc cách trình bày phù hợp accessibility. Khi mục tiêu là trả lời “người dùng đã thấy gì?”, lưu **chỉ tên tài liệu hiện hành** có thể không đủ.

### Ví dụ bản phát hành bất biến

~~~json
{
  "presentation_id": "sales-report-orders-consent",
  "version": "3.0.0",
  "locale": "vi-VN",
  "title": "Kết nối Sales Report",
  "requested_permissions": [
    {
      "resource": "orders-api",
      "scope": "orders:read",
      "display_text": "Xem danh sách đơn hàng"
    },
    {
      "resource": "orders-api",
      "scope": "orders:export",
      "display_text": "Xuất dữ liệu đơn hàng"
    }
  ],
  "content_sha256": "<digest-of-canonical-published-content>",
  "published_at": "2026-11-23T09:00:00Z",
  "status": "PUBLISHED"
}
~~~

**Đây là cấu trúc nội bộ minh họa**, không phải JSON response OAuth tiêu chuẩn. Hash là placeholder, không phải một giá trị SHA-256 thật.

Quy trình phù hợp:

1. Nội dung consent được duyệt và **publish thành một revision bất biến**.
2. Tạo bytes để tính hash theo **quy tắc canonicalization cố định**; không băm JSON xuất ra không ổn định về thứ tự field/encoding rồi cho rằng sẽ luôn đối chiếu được.
3. Lưu hash cùng **snapshot hoặc tham chiếu nội dung bất biến** và locale.
4. Khi render consent cho transaction, AS ghi lại **revision cụ thể được lấy và đưa vào màn hình**.
5. Khi người dùng quyết định, AS so revision/transaction với record tin cậy, không dựa vào version người dùng sửa ở form.
6. Các bản v4, v5 **được tạo mới**; không sửa nội dung v3 mà giữ nguyên nhãn v3.

### Vì sao hash một mình chưa đủ?

Nếu nội dung v3 bị sửa trực tiếp trong database và hash cũng bị sửa bởi cùng một người có đặc quyền, việc đối chiếu sẽ vẫn “đúng”. Cần **quyền publish tách biệt, audit, append-only/immutable storage**, và khi có threat model cao hơn, có thể dùng **chữ ký số hoặc lưu bằng chứng trong kho độc lập**. Hash chứng minh nhất quán giữa bytes và digest được tin, **không tự chứng minh hành động con người**.

### Ngôn ngữ và phiên bản

Nếu bản **vi-VN v3** và **en-US v3** diễn giải quyền khác nhau, một trường version=3 không nói đủ. Có thể dùng khóa tổng hợp **presentation_id + version + locale + digest**, cùng quy trình kiểm bản dịch. Thay đổi bản dịch làm thay đổi ý nghĩa quyền cần được đánh giá như một thay đổi nội dung, không tự động coi là chỉnh sửa vô hại.

## 7. Thiết kế consent decision event bất biến

**Decision event** là bằng chứng rằng một quyết định đã xảy ra. Nên tách **lịch sử sự kiện** khỏi **trạng thái grant hiện tại**.

Ví dụ sự kiện Approve:

~~~json
{
  "event_id": "consent-event-219",
  "transaction_ref": "tx-901",
  "event_type": "APPROVED",
  "decision_source": "RESOURCE_OWNER",
  "actor_ref": "user-42",
  "subject_ref": "user-42",
  "tenant_ref": "tenant-A",
  "issuer_ref": "auth-main",
  "client_id": "sales-report",
  "resource": "orders-api",
  "requested_scopes": ["orders:read", "orders:export"],
  "approved_scopes": ["orders:read", "orders:export"],
  "presentation_id": "sales-report-orders-consent",
  "presentation_version": "3.0.0",
  "presentation_locale": "vi-VN",
  "presentation_digest": "<content-sha256>",
  "authorization_policy_version": "policy-12",
  "decided_at": "2026-11-23T09:03:22Z",
  "recorded_at": "2026-11-23T09:03:23Z",
  "result": "COMMITTED"
}
~~~

Cần hiểu:

- **actor_ref**: ai thực sự thực hiện quyết định, ví dụ user hoặc quản trị viên.
- **subject_ref**: chủ thể có dữ liệu/quyền được ủy quyền; có thể khác actor trong admin consent.
- **decision_source**: Resource Owner, admin, chính sách tổ chức, hoặc cơ chế có thẩm quyền khác. **Không giả mạo** một policy grant thành “người dùng đã bấm đồng ý”.
- **requested_scopes**: quyền client xin.
- **approved_scopes**: phạm vi được cho phép thật sự, không tự sao chép requested_scopes.
- **presentation_version/digest**: nội dung đã được hiển thị và làm căn cứ cho quyết định.
- **decided_at vs recorded_at**: khi quyết định xảy ra và khi hệ thống ghi nhận. Đồng hồ và độ tin cậy của nguồn phải được xác định.

**Event type APPROVED không đồng nghĩa grant tồn tại mãi mãi**. Một sự kiện REVOKED hoặc chính sách thay đổi có thể làm trạng thái hiện tại chuyển sang không được phép; lịch sử APPROVED vẫn có ý nghĩa để giải thích quá khứ.

### Không ghi access token vào event

Sự kiện consent nên lưu **grant_ref, request_id, client_id, scopes và version** với bảo vệ dữ liệu thích hợp, không lưu **raw authorization code, PKCE code_verifier, access token, refresh token, ID token, private key**. Những credential này có vòng đời riêng và có thể bị khai thác nếu xuất hiện trong kho audit.

## 8. Một grant có thể có nhiều version và nhiều sự kiện

Giả sử user-42 chấp thuận quyền đọc v1, sau đó mở rộng v3 rồi thu hồi:

~~~text
T1: APPROVED v1 -> grant revision 1
    scopes = [orders:read]
    status = ACTIVE

T2: APPROVED v3 -> grant revision 2
    scopes = [orders:read, orders:export]
    status = ACTIVE

T3: REVOKED    -> grant revision 3
    scopes = [] theo mô hình current-state
    status = REVOKED
~~~

**Presentation version** và **grant revision** tăng theo **hai quy tắc khác nhau**. Nếu grant được thu hồi mà không có UI consent mới, **grant revision tăng**, nhưng không có lý do bịa một **presentation version mới**. Nếu UI thay đổi câu chữ song grant hiện tại vẫn hợp lệ, **presentation version tăng** mà grant có thể không thay đổi.

Một mô hình:

| Thành phần | Nội dung nên lưu | Cách cập nhật |
|---|---|---|
| **Consent presentation registry** | Bản nội dung/locale/version đã publish, digest, lifecycle | Tạo revision mới; không sửa bản đã publish |
| **Consent decision events** | APPROVED/DENIED/REVOKED và ngữ cảnh bất biến | **Append-only** theo retention/audit policy |
| **Current grant** | Phạm vi quyền hiệu lực, trạng thái, revision, thời hạn | Cập nhật có kiểm soát tranh chấp |
| **Token lineage** | Những token/grants được cấp và liên hệ nội bộ | Dùng để thu hồi hoặc đánh giá ảnh hưởng theo chính sách |

**Deny một request mở rộng scope không nhất thiết thu hồi grant chỉ đọc đã có.** Hệ thống phải định nghĩa rõ liệu Deny chỉ từ chối **request hiện tại** hay có ý nghĩa “disconnect app”, để tránh xóa quyền ngoài ý định hoặc lén giữ quyền sau khi người dùng chọn thu hồi.

## 9. Quy tắc re-consent: khi version mới cần quyết định mới?

Không nên viết:

~~~text
if currentPresentationVersion != recordedPresentationVersion:
    forceConsentForEveryone()
~~~

Quy tắc trên có thể gây phiền toái khi chỉ sửa dấu câu, nhưng vẫn có thể bỏ sót thay đổi nghiêm trọng nếu scope catalog bị sửa mà version của màn hình không tăng. **Re-consent là quyết định policy dựa trên thay đổi có ý nghĩa**, không phải phép so sánh số phiên bản duy nhất.

### Ma trận đánh giá thay đổi

| Thay đổi | Hướng xử lý đề xuất | Lý do |
|---|---|---|
| Sửa lỗi chính tả, không đổi ý nghĩa quyền | Có thể không bắt buộc re-consent | Không thay phạm vi ủy quyền |
| Thay mô tả để làm rõ quyền đã có | Đánh giá materiality và policy | Không tự kết luận là tăng quyền |
| Thêm **orders:export** | Thường phải có quyết định ủy quyền mới phù hợp | Mở rộng khả năng sử dụng dữ liệu |
| Đổi từ đọc sang ghi/xóa | Cần policy/consent chặt hơn, có thể step-up | Rủi ro cao hơn |
| Thêm Resource Server hoặc audience mới | Đánh giá grant/resource riêng, có thể hỏi lại | Quyền đến nơi nhận mới |
| Thay client/publisher được cấp quyền | Không chuyển consent cũ sang client khác | Trust identity khác |
| Đổi tenant/account | Kiểm lại đúng chủ thể và thẩm quyền | Consent không mặc định xuyên tenant |
| Policy siết điều kiện hoặc cấm quyền cũ | Phải áp dụng siết quyền/thu hồi theo policy; không đợi user đồng ý | Không được fail open |
| Grant hết hạn/bị thu hồi | Không sử dụng lại; yêu cầu flow hợp lệ mới nếu cho phép | Quyết định cũ không còn hiệu lực |
| Bản dịch thay đổi nghĩa câu chữ | Đánh giá như thay đổi content có ý nghĩa | Người dùng có thể hiểu quyền khác đi |

### Hai chiều cần phân biệt

- **Khi quyền mở rộng:** phải đánh giá liệu cần xin quyết định mới từ đúng chủ thể có thẩm quyền.
- **Khi quyền bị siết lại:** AS/RS phải thực thi chính sách chặt hơn, **không cần đợi user chấp thuận việc cấm quyền mới**.

Một client không được tự đưa **consent_version=latest** vào token request để vượt yêu cầu re-consent. Quyết định thuộc AS/policy và phải liên kết được với **grant thực**.

## 10. OIDC prompt=consent và offline_access liên quan ra sao?

Trong OpenID Connect, **prompt=consent** là tham số authorization request yêu cầu OpenID Provider thực hiện giao diện consent theo quy tắc profile. Nó **không phải mã phiên bản của consent** và cũng không tự động mở rộng quyền.

Ví dụ:

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fapp.example.org%2Fcallback&scope=openid%20orders%3Aread&state=<random-state>&code_challenge=<S256-challenge>&code_challenge_method=S256&prompt=consent HTTP/1.1
Host: auth.example.org
~~~

Nếu AS quyết định người dùng phải xem phiên bản nội dung mới, có thể bắt đầu flow tương ứng và ràng buộc **presentation version** vào transaction. Nhưng **prompt=consent** không chứng minh người dùng đã thực sự chấp thuận, và không phải phép ghi consent record của client.

Với **offline_access**, OIDC có các quy tắc về consent và điều kiện cấp refresh token. Hệ thống có thể cần mô tả rõ **khả năng duy trì truy cập khi người dùng không hiện diện**. Tuy nhiên:

- Xin **offline_access** không bảo đảm AS cấp refresh token.
- Refresh token có thể hết hạn, bị thu hồi, rotation hoặc sender-constrained theo chính sách.
- Version mới làm thay đổi quyền offline có thể cần quyết định lại.
- Một consent record cho quyền **orders:read** không tự cho phép access lâu dài hoặc audience bất kỳ.

**ID token OIDC** dùng để client kiểm chứng đăng nhập; nó không phải access token của Resource Server và cũng không phải chứng cứ chuẩn có chứa đầy đủ lịch sử consent version.

## 11. Consent version có nên nhúng trong access token không?

**Không mặc định.** OAuth 2.0 không yêu cầu access token có claim **consent_version**. Nếu hệ thống tự bổ sung claim nội bộ, cần thỏa thuận rõ ý nghĩa, issuer, audience và cách Resource Server sử dụng.

Ví dụ JWT access token **minh họa nội bộ**:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "sales-report",
  "scope": "orders:read",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "at-example-104",
  "grant_ref": "grant-example-017",
  "grant_revision": 2
}
~~~

Đây chỉ là claims JSON, **không phải JWT có chữ ký**. **grant_ref** và **grant_revision** là claims riêng của một hệ thống giả định, không phải những trường mặc định của OAuth 2.0. Nếu dùng profile JWT access token theo **RFC 9068**, phải tuân thủ yêu cầu profile về chữ ký, header và claims.

### Lợi ích và giới hạn

| Cách thiết kế | Ưu điểm | Giới hạn/rủi ro |
|---|---|---|
| **Version chỉ lưu ở AS/consent store** | Ít dữ liệu lộ trong token, đơn giản hợp đồng API | RS khó biết ngay grant revision hiện hành nếu không hỏi trạng thái |
| **Thêm grant revision vào token** | Có thể hỗ trợ đối chiếu trạng thái nếu RS có nguồn policy/grant version | JWT tự chứa mang revision cũ cho tới exp, trừ khi RS kiểm trạng thái |
| **Opaque token + introspection** | AS có thể trả trạng thái active và metadata được cho phép | Cache introspection có thể khiến revoke có độ trễ |
| **RS luôn kiểm current policy/grant state khi cần** | Có thể thực thi thu hồi nhanh và quyền hiện hành | Tăng độ phức tạp và phụ thuộc vào nguồn trạng thái |

**Ký claim consent_version không làm consent trở nên hiện hành.** Một JWT có chữ ký đúng vẫn có thể thể hiện trạng thái lúc token phát hành. Muốn từ chối ngay khi grant revision thay đổi, RS phải có **nguồn current state/epoch hoặc denylist** và chính sách kiểm tương ứng.

Không nhúng toàn bộ nội dung consent, tên tài khoản, email, thông tin audit hoặc refresh token vào JWT chỉ để truy vết; JWT JWS thông thường có payload **đọc được**, không được coi là mã hóa.

## 12. Refresh token và việc đổi version sau khi cấp grant

Một client có thể nhận refresh token sau khi user consent theo flow/chính sách. Sau đó, AS phát hành **presentation v4** và tăng quyền trong phạm vi yêu cầu.

Khi client gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token>&client_id=sales-report
~~~

AS không được hiểu “refresh token còn hạn” là quyền xin mọi scope của presentation v4. Cần kiểm:

1. Refresh token gắn với **đúng client/grant**, còn hiệu lực và chưa bị revoke.
2. Grant hiện hành có còn được phép theo **subject, tenant, policy, resource** không.
3. Scope yêu cầu/được cấp **không vượt phạm vi grant đã chấp thuận**.
4. Nếu policy yêu cầu **re-consent vì thay đổi material**, AS không tự cấp quyền mới qua refresh.
5. Nếu refresh token rotation được dùng, xử lý **single-use/reuse detection** và trạng thái atomically.

### Khi nào cho refresh quyền cũ?

Tùy policy:

- **Giữ quyền cũ** nếu nó vẫn được phép và thay đổi presentation mới không ảnh hưởng grant đã cấp.
- **Thu hẹp quyền** nếu policy giảm quyền và grant còn có phần hợp lệ, theo hợp đồng.
- **Từ chối refresh, yêu cầu ủy quyền lại** nếu grant cần consent mới hoặc bị revoke.

Không có quy tắc “cứ tăng consent version là refresh token tự mất hiệu lực” áp dụng cho mọi AS. Nhưng **không bao giờ được tự nâng quyền** chỉ vì client có refresh token hợp lệ.

**Thu hồi refresh token/grant không tự vô hiệu ngay mọi JWT access token cũ** tại Resource Server chỉ xác minh signature và exp. Cần token revocation/epoch/denylist hoặc thiết kế TTL phù hợp nếu yêu cầu phản ứng sớm.

## 13. Thiết kế lưu trữ: presentation registry, decision log và current grant

Một cách tổ chức dễ kiểm soát là tách thành ba nhóm dữ liệu, thay vì dồn toàn bộ vào một bảng **user_consented**.

### 13.1. Registry của nội dung đã publish

~~~sql
-- PostgreSQL minh họa; chưa bao gồm mọi chính sách access control.
CREATE TABLE consent_presentations (
    presentation_id      TEXT NOT NULL,
    version              TEXT NOT NULL,
    locale               TEXT NOT NULL,
    canonical_content    TEXT NOT NULL,
    content_sha256       TEXT NOT NULL,
    scope_catalog_version TEXT NOT NULL,
    published_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (presentation_id, version, locale)
);
~~~

**Quy tắc thiết kế:** bản đã publish cần **bất biến theo nghiệp vụ**; tạo hàng mới khi nội dung thay đổi. Việc lưu digest phải đi cùng cơ chế bảo vệ update/delete từ bên không được phép. Không coi PRIMARY KEY tự bảo đảm tính bất biến vì người có quyền UPDATE vẫn có thể sửa nội dung cùng khóa.

### 13.2. Decision events để audit

~~~sql
CREATE TABLE consent_decision_events (
    event_id              TEXT PRIMARY KEY,
    transaction_ref       TEXT NOT NULL UNIQUE,
    grant_ref             TEXT,
    event_type            TEXT NOT NULL,
    actor_ref             TEXT NOT NULL,
    subject_ref           TEXT NOT NULL,
    tenant_ref            TEXT,
    client_id             TEXT NOT NULL,
    resource_ref          TEXT NOT NULL,
    requested_scopes_json JSONB NOT NULL,
    approved_scopes_json  JSONB NOT NULL,
    presentation_id       TEXT,
    presentation_version  TEXT,
    presentation_locale   TEXT,
    presentation_digest   TEXT,
    policy_version        TEXT NOT NULL,
    decided_at            TIMESTAMPTZ NOT NULL,
    recorded_at           TIMESTAMPTZ NOT NULL
);
~~~

Đây là một **thiết kế minh họa**, không phải schema chuẩn; các trường nullable, ràng buộc khóa ngoại, event type, bảng identity và retention phải được thiết kế kỹ cho thực tế. **UNIQUE transaction_ref** trong ví dụ có nghĩa **một quyết định cuối cùng trên một transaction**; với hệ thống cần nhiều events trung gian, hãy dùng **decision transaction ID** riêng hoặc mô hình sự kiện phù hợp, không cố nhét mọi sự kiện trung gian vào UNIQUE này.

**DENIED** nên có sự kiện riêng với tập **approved scopes rỗng**, không được tạo một grant APPROVED từ request bị từ chối. Sự kiện **REVOKED** có thể liên kết một grant đã có, với transaction/command độc lập.

### 13.3. Current grant để kiểm tra quyền

~~~sql
CREATE TABLE current_oauth_grants (
    grant_ref             TEXT PRIMARY KEY,
    subject_ref           TEXT NOT NULL,
    tenant_ref            TEXT,
    client_id             TEXT NOT NULL,
    resource_ref          TEXT NOT NULL,
    approved_scopes_json  JSONB NOT NULL,
    status                TEXT NOT NULL,
    revision              BIGINT NOT NULL DEFAULT 1,
    last_decision_event_id TEXT NOT NULL,
    expires_at            TIMESTAMPTZ,
    revoked_at            TIMESTAMPTZ
);
~~~

Trong triển khai thật, nên có **CHECK constraints/foreign keys**, index theo client/subject/tenant, chính sách encryption/ACL phù hợp và thiết kế chống trùng grant. Các trường định danh người dùng có thể là dữ liệu cá nhân cần quản lý vòng đời riêng.

**Tách hai mục đích:** khi vận hành, AS thường đọc **current_oauth_grants** để quyết định cấp token; khi audit, đối chiếu **consent_decision_events** và **consent_presentations** để giải thích grant đã đến từ quyết định nào, với nội dung gì.

## 14. Atomicity: không để màn hình v2 được duyệt thành quyền v3

Một race condition nguy hiểm:

~~~text
10:00:00  User mở consent screen v2, quyền [orders:read]
10:00:02  Deployment publish v3, quyền [orders:read, orders:export]
10:00:04  User bấm Approve trên tab v2
10:00:05  AS lấy "latest scopes" từ v3 rồi ghi grant có orders:export
~~~

Đây là **consent version confusion**: người dùng chưa nhìn thấy và chưa chấp thuận quyền xuất.

Để phòng tránh:

1. Tại lúc render, AS **cố định presentation version và requested/eligible scope snapshot** của transaction.
2. Khi nhận Approve, AS lấy **transaction server-side**, kiểm nó chưa hết hạn/chưa hoàn tất, session/actor khớp.
3. AS tính lại policy bắt buộc để bảo đảm **không cấp quyền bị cấm**.
4. **Không bao giờ tăng tập quyền được cấp so với quyền đã hiển thị và có quyết định hợp lệ**.
5. Nếu thay đổi làm nội dung không còn phù hợp, **hủy/restart transaction** hoặc yêu cầu hiển thị phiên bản mới.
6. Ghi decision event và current grant **trong một transaction có tính nhất quán**.
7. Mọi request Approve/Deny lặp lại hoặc cạnh tranh phải nhận một kết quả cuối cùng phù hợp policy.

~~~mermaid
flowchart TD
    A["User gửi Approve cho transaction T"] --> B["AS load + khóa transaction T"]
    B --> C{"T còn hạn, chưa hoàn tất, đúng actor?"}
    C -->|Không| X["Reject, không cấp grant"]
    C -->|Có| D["Load presentation version được pin ở T"]
    D --> E{"Content digest, tenant, client, resource khớp?"}
    E -->|Không| X
    E -->|Có| F["Đánh giá current authorization policy"]
    F --> G{"Policy còn cho phép phạm vi đã hiển thị?"}
    G -->|Không| R["Yêu cầu quyết định mới hoặc Deny"]
    G -->|Có| H["Atomic commit decision event + grant revision"]
    H --> I["Phát code/grant theo scope đã được chấp thuận"]
~~~

Nếu policy mới **siết** quyền, AS có thể từ chối hoặc chỉ cấp phần hợp lệ theo hợp đồng; không được âm thầm dùng bản mới để tăng quyền.

### Không chỉ dùng optimistic revision trong frontend

Một form có trường **version=3** do browser gửi chưa đủ. Khi khách hàng sửa thành 99, AS phải bỏ qua giá trị không đáng tin hoặc đối chiếu chính xác với snapshot server-side. **CSRF token, session binding, chống clickjacking và one-time transaction** vẫn cần để bảo vệ thao tác phê duyệt.

## 15. Java: kiểm version và ghi quyết định theo transaction

Ví dụ Java dưới đây là **pseudocode kiểu Java/Spring** cho tầng quản lý consent. Các lớp **TransactionRepository, GrantRepository, DecisionEventRepository, PolicyEngine** mang tính minh họa, **không phải thư viện OAuth hoàn chỉnh**.

~~~java
@Transactional
public ConsentResult approve(
        String transactionId,
        AuthenticatedActor actor
) {
    // Lock bản ghi server-side; không tin scope/version từ browser.
    ConsentTransaction tx =
            transactionRepository.findByIdForUpdate(transactionId);

    if (tx == null || tx.isExpired() || tx.isCompleted()) {
        throw new InvalidConsentTransaction();
    }
    if (!tx.mayBeDecidedBy(actor)) {
        throw new ForbiddenConsentDecision();
    }

    PublishedPresentation presentation =
            presentationRepository.findImmutableVersion(
                    tx.presentationId(),
                    tx.presentationVersion(),
                    tx.locale()
            );
    if (presentation == null ||
            !presentation.digest().equals(tx.presentationDigest())) {
        throw new StaleConsentPresentation();
    }

    ClientRegistration client = clientRegistry.requireActive(tx.clientId());
    PolicyDecision current = policyEngine.evaluate(
            actor, client, tx.tenant(), tx.resource()
    );

    // Đảm bảo không cấp scope chưa từng được hiển thị.
    Set<String> approved = intersect(
            tx.scopesActuallyShownToActor(),
            current.eligibleScopes()
    );
    if (approved.isEmpty() || current.requiresNewPresentation()) {
        throw new ConsentMustRestart();
    }

    ConsentDecisionEvent event = decisionEvents.appendApproved(
            tx, actor, approved, current.policyVersion()
    );
    OAuthGrant grant = grantRepository.upsertWithRevision(
            tx.subject(), tx.tenant(), client.id(),
            tx.resource(), approved, event.id()
    );
    tx.completeExactlyOnce(event.id());

    return new ConsentResult(grant.id(), grant.revision());
}
~~~

**Những điểm phải làm thật trong sản phẩm:**

- Annotation **@Transactional** chỉ có tác dụng đúng khi repository, transaction manager, isolation và lock được cấu hình phù hợp. Với AS đa instance, không dùng mutex in-memory làm nguồn chống race duy nhất.
- **intersect** là minh họa giới hạn quyền, **không tự cho phép partial approval** nếu UI và policy yêu cầu người dùng chấp thuận toàn bộ tập quyền một cách rõ ràng. Khi cần quyết định mới, nên dừng và hiển thị lại.
- **scopesActuallyShownToActor()** phải đến từ transaction tin cậy, không từ tham số browser.
- **upsertWithRevision** phải định nghĩa rõ cộng dồn, thay thế, thu hẹp hay tạo grant mới; không gộp scope của grant cũ mà không kiểm policy/consent.
- **Grant/token issuance** ở bước sau còn phải kiểm client, authorization code, PKCE, redirect URI, issuer và các điều kiện OAuth khác.

### Optimistic concurrency ở current grant

Ví dụ điều kiện cập nhật revision:

~~~sql
UPDATE current_oauth_grants
SET approved_scopes_json = :new_scopes_json,
    revision = revision + 1,
    last_decision_event_id = :new_event_id
WHERE grant_ref = :grant_ref
  AND revision = :expected_revision
  AND status = 'ACTIVE';
~~~

Chỉ khi số hàng cập nhật bằng **1** thì bản cập nhật tranh chấp được chấp nhận. Phải thực hiện trong một transaction cùng event/điều kiện đi kèm; không tạo decision event “COMMITTED” nếu grant update đã thất bại mà không có cơ chế event-sourcing được thiết kế rõ.

## 16. Multi-tenant và admin consent version

Trong hệ thống doanh nghiệp, một quản trị viên có thể chấp thuận ứng dụng **cho tổ chức**. Khi đó:

~~~text
actor_ref         = admin-7
decision_source   = TENANT_ADMIN
subject_ref       = tenant-A (hoặc tenant-level permission owner)
tenant_ref        = tenant-A
client_id         = sales-report
approved_scopes   = orders:read
presentation_v    = tenant-consent-v2
~~~

Đây là **mô hình minh họa**. Tùy nền tảng, subject/actor/resource owner có thể được biểu diễn khác. Điểm quan trọng:

- **Actor** là người hoặc workload thực sự thực hiện quyết định.
- **Decision source** cho biết quyền phê duyệt của actor đến từ user/admin/policy nào.
- **Tenant boundary** phải được gắn với quyết định.
- **Presentation version** phải phù hợp với quyền được trình bày cho **admin consent**, không giả vờ đó là consent cá nhân của từng user.

Nếu admin chỉ có quyền ở tenant-A, không được dùng record của họ để tạo quyền ở tenant-B. Khi admin mất quyền hoặc tổ chức cập nhật chính sách, hệ thống cần quyết định trạng thái grant theo quy tắc, không dựa vào một **approved=true** cũ.

**Admin consent không tự biến application permission thành user-delegated permission.** Với Client Credentials grant, quyền thuộc client/service principal theo registration/policy; access token không nhất thiết đại diện một end user. Resource Server vẫn phải kiểm tenant, audience, scope và quyền nghiệp vụ.

## 17. Audit, privacy và retention của consent version

Versioning giúp audit, nhưng nó cũng tạo dữ liệu liên hệ **ai đã làm gì, lúc nào, với ứng dụng nào**. Cần thiết kế quyền truy cập và retention tương xứng.

### Nên lưu theo nhu cầu

- **Decision ID / transaction ID / grant_ref** không chứa token thật.
- **Actor/subject reference** do hệ thống tin cậy xác minh, cùng tenant khi cần.
- **Client identity** và metadata đăng ký được phép công bố tại thời điểm đó.
- **Requested/approved scope, resource và policy version**.
- **Presentation ID, version, locale, digest**; liên kết tới snapshot bất biến.
- **Decision type** APPROVE/DENY/REVOKE, timestamp, tình trạng commit.
- **Reason code** chuẩn hóa và điều kiện ủy quyền quan trọng theo chính sách audit.

### Không nên lưu theo thói quen

~~~text
Authorization: Bearer <access-token>
refresh_token=<refresh-token>
id_token=<id-token>
authorization_code=<code>
code_verifier=<pkce-verifier>
client_secret=<secret>
session_cookie=<cookie>
raw JWT / raw token endpoint request and response
~~~

Không lấy raw token làm primary key/correlation ID của event. Với JWT JWS, payload thường **đọc được**; lưu cả JWT có thể làm lộ claims không cần. **Refresh token** có thể duy trì truy cập trong thời gian dài, đặc biệt nguy hiểm khi xuất hiện trong log hay audit kho chung.

### Retention và quyền xóa

Tùy mục đích audit, nghĩa vụ pháp lý và loại dịch vụ, dữ liệu có thể cần được giữ trong thời hạn nhất định rồi được xóa, rút gọn hoặc pseudonymize theo quy trình. **Immutable audit** ở tầng ứng dụng không có nghĩa “giữ mọi định danh người dùng mãi mãi, không cho bất kỳ biện pháp bảo vệ riêng tư nào”.

Phân quyền tách biệt người có thể **publish nội dung**, **đọc audit**, **quản lý grant**, **thu hồi token**. Theo dõi truy cập audit và mọi sửa đổi hệ thống quản trị. Nếu cần chứng cứ chống sửa đổi ở mức cao, dùng giải pháp lưu vết độc lập và chính sách vận hành rõ, thay vì chỉ dựa vào một hash.

## 18. Consent phishing và version confusion

Một dạng lạm dụng là **consent phishing**: kẻ tấn công dùng OAuth client của họ, dụ nạn nhân vào Authorization Server thật và chấp thuận quyền của client ấy. **Phiên bản hóa không tự ngăn phishing**, nhưng giúp hệ thống xác định:

- Nạn nhân đã nhìn thấy **tên client và publisher** nào?
- Scope/resource nào đã được hiển thị?
- Bản tiếng Việt/Anh nào đã được dùng?
- Có sự thay đổi client registration hay mô tả quyền ngay trước khi phê duyệt không?
- Consent được ghi nhận từ account/tenant nào và policy ra sao?

### Các sai lệch cần phòng tránh

| Sai lệch | Rủi ro | Cách bảo vệ |
|---|---|---|
| UI hiện v2 nhưng server ghi nhận v3 | Người dùng bị gán quyền chưa thấy | Pin version/digest và scope snapshot vào transaction |
| Client đổi tên/logo sau khi user duyệt | Audit hiện metadata mới và làm sai lịch sử | Lưu hoặc tham chiếu metadata đăng ký tại thời điểm quyết định |
| Scope catalog đổi nghĩa mà không cập nhật quy trình | Quyền cũ bị diễn giải rộng hơn | Version catalog/policy, đánh giá tác động tới grant cũ |
| App thay tenant giữa lúc hiển thị và ghi nhận | Quyết định bị áp dụng sang tenant khác | Tenant/subject/client binding server-side |
| Người dùng bấm Deny nhưng API vẫn có token mới | Consent thất bại nhưng grant/token được mở | Atomic state, kiểm token issuance và negative tests |
| Sự kiện replay/duplicate approve | Ghi nhiều grant hoặc quyền mâu thuẫn | Idempotent transaction processing và concurrency control |
| Dùng prompt=consent để tự nâng scope | Grant vượt thẩm quyền | AS kiểm scope/resource/policy độc lập với request params |

**Nhiều giá trị trong authorization request và consent form đều do client/browser gửi, nên chưa thể được tin để xác định “đã chấp thuận gì”.** AS phải lấy ý nghĩa quyết định từ trạng thái, registry và policy tin cậy.

## 19. Khi cần điều tra hoặc phản ứng sự cố

Ví dụ hệ thống phát hiện Sales Report đã nhận access token có **orders:export**, nhưng user chỉ có sự kiện APPROVED phiên bản v1 với **orders:read**.

Quy trình xử lý:

1. **Xác định grant và token lineage:** client, subject, tenant, resource, token issuance timeline; không công khai raw token.
2. **Đối chiếu version:** presentation v1/v3, content digest, scope catalog/policy version và decision events.
3. **Xác định điểm phát sinh mở quyền:** AS tính sai eligible scope, refresh nâng quyền, admin consent khác, lỗi migration, hay token validation sai?
4. **Ngăn tác động tiếp diễn:** siết policy, chặn grant/token mới, thu hồi refresh token hoặc grant liên quan.
5. **Xử lý access token đang còn hạn:** áp dụng cơ chế revoke/denylist/epoch/introspection phù hợp; không giả định xóa consent record sẽ làm JWT cũ mất hiệu lực.
6. **Kiểm Resource Server:** xem có hành động xuất dữ liệu thật hay không, quyền API có được kiểm sau token validation không.
7. **Sửa dữ liệu và chứng cứ đúng cách:** thêm correction event nếu audit sai; tránh âm thầm sửa lịch sử v1 thành v3.
8. **Chạy regression tests:** permission escalation, stale version, replay, cache và concurrency.

**Không đánh tráo hai loại sự cố:** sai consent version thường là vấn đề **grant/policy/audit integrity**; nó không tự chứng minh private signing key của AS đã bị lộ. Nếu có bằng chứng khóa issuer bị xâm phạm, phải xử lý theo kế hoạch thu hồi niềm tin riêng.

## 20. Ma trận kiểm thử ghi nhận consent version

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| **S01** | User xem v1, Approve đúng client/scope/resource | Event tham chiếu v1/digest/locale; grant đúng quyền |
| **S02** | User xem v3 mới và chủ động Approve quyền mở rộng | Event mới ghi v3; grant revision tăng nếu policy cho phép |
| **S03** | User Deny một request mới | Event DENIED đúng version; không cấp token cho request đó |
| **S04** | Revoke grant đã Approve | Ghi REVOKED, current grant không còn hiệu lực theo policy; lịch sử APPROVED vẫn tra cứu được |
| **S05** | Chỉ sửa văn bản không material và policy cho reuse grant | Không tự nâng scope; quyết định reuse được audit theo policy |
| **F01** | UI render v2, server ghi v3 do đọc latest lúc submit | Phải bị chặn; không cấp scope chưa hiển thị |
| **F02** | Browser sửa presentation_version trong form | Không tin dữ liệu sửa; đối chiếu server-side transaction |
| **F03** | Browser sửa approved_scope từ read thành export | Không cấp scope chưa được hiển thị/cho phép |
| **F04** | Client A dùng consent record của client B | Từ chối |
| **F05** | User A/tenant-A gắn record sang user B/tenant-B | Từ chối |
| **F06** | Content snapshot bị sửa mà version không đổi | Phát hiện digest mismatch/integrity failure; không coi là bản cũ hợp lệ |
| **F07** | Một locale đổi nghĩa nhưng giữ version/digest cũ | Phát hiện quy trình publish sai, không áp dụng im lặng |
| **F08** | Grant v1 orders:read, request mới xin orders:export | Không tự tăng quyền từ grant cũ |
| **F09** | Policy mới cấm scope cũ | AS/RS siết quyền đúng policy, không đợi user Approve quyền bị cấm |
| **F10** | Authorization transaction hết hạn mới bấm Approve | Từ chối, không tạo grant mới |
| **F11** | Hai tab cùng Approve một transaction | Một decision cuối cùng nhất quán |
| **F12** | Approve và Deny cạnh tranh cùng transaction | Không ghi hai kết quả mâu thuẫn/không phát token trái policy |
| **F13** | Transaction commit event thành công nhưng grant update lỗi | Không báo COMMITTED sai trạng thái hoặc áp dụng cơ chế nhất quán đã thiết kế |
| **F14** | Current grant revision bị thay trước khi update | Conditional update thất bại; không overwrite revision mới |
| **F15** | Client gửi refresh token cũ xin scope mới | Không cấp vượt approved grant |
| **F16** | Consent bị revoke, refresh token còn lưu ở client | Token endpoint từ chối theo revoke/client policy |
| **F17** | JWT access token cũ sau khi revoke grant | RS làm đúng revocation/TTL policy; không mặc định claim cũ cập nhật |
| **F18** | Access token có đúng scope nhưng sai audience | RS từ chối |
| **F19** | Access token đúng audience/scope nhưng resource tenant khác | RS từ chối theo object-level policy |
| **F20** | ID token hoặc refresh token được gửi làm Bearer tới API | RS từ chối sai loại credential |
| **F21** | Admin tenant-A duyệt cho tenant-B | AS từ chối thiếu thẩm quyền |
| **F22** | OIDC prompt=consent được gửi nhưng user chưa chấp thuận | Không coi tham số request là decision event APPROVED |
| **F23** | App đổi metadata/tên sau lần approve cũ | Audit vẫn khôi phục được metadata/presentation lịch sử |
| **F24** | APM/log/tracing bật debug khi bấm Approve/token exchange | Không có raw code/verifier/access/refresh token, session cookie |
| **F25** | Consent snapshot mất hoặc digest không xác minh được | Không bịa nội dung cũ; báo thiếu chứng cứ/áp policy |
| **F26** | Hai AS nodes cùng cập nhật một grant | Revision/transaction control ngăn mất sự kiện hoặc nâng quyền trái phép |
| **F27** | Quyết định DENY mới nhưng grant cũ đang ACTIVE | Hành vi đúng policy, không tự suy Deny = revoke tất cả token |
| **F28** | Permission được quản trị viên cấp qua policy | Event chỉ rõ decision_source; không gán giả là user approve |

**Đánh giá test phải nhìn vào trạng thái thật**: presentation digest, decision event, current grant, token đã cấp và kết quả tại Resource Server. HTTP 200/400 chưa đủ; một request lỗi vẫn có thể đã commit grant sai hoặc phát token trước khi rollback.

### Test minh họa: phiên bản đổi trong lúc form đang mở

~~~text
Given:
  Transaction T pin presentation v2, scopes=[orders:read]
  Người dùng đang xem v2.
  Hệ thống publish v3, thêm orders:export.

When:
  Người dùng bấm Approve trên form v2.

Then:
  Quyền được cấp không chứa orders:export chỉ vì latest=v3.
  Event ghi đúng v2 và digest của v2 nếu quyết định còn hợp lệ.
  Nếu policy yêu cầu v3, T bị từ chối/restart để hiển thị v3.
  Không có token nào được phát cho quyền chưa được cho phép.
~~~

## 21. Checklist triển khai consent version

1. **Khái niệm:** Đã phân biệt presentation version, grant revision, policy version và scope catalog version?
2. **Snapshot:** Mỗi quyết định có thể khôi phục nội dung/locale/scope/resource đã thực sự trình bày?
3. **Immutability:** Content đã publish có revision riêng, không chỉnh cùng version?
4. **Digest:** Có quy tắc canonicalization, kiểm digest và bảo vệ quyền sửa/xóa bản snapshot?
5. **Actor/subject:** Ghi đúng người quyết định và chủ thể được cấp quyền; phân biệt user/admin/policy?
6. **Client/tenant:** Consent được ràng buộc đúng OAuth client, account/tenant và resource?
7. **Transaction binding:** AS pin presentation/scope khi hiển thị, không tin version/scopes từ browser?
8. **Policy:** Có quy tắc materiality/re-consent rõ khi tăng quyền, đổi tài nguyên hoặc đổi mục đích?
9. **Deny:** Từ chối request mới được phân biệt với revoke grant đang tồn tại?
10. **Grant:** Current grant có version/revision, state ACTIVE/EXPIRED/REVOKED và phạm vi hiệu lực?
11. **Concurrency:** Approve/Deny, publish nội dung, cập nhật grant và đổi code chịu transaction/locking phù hợp?
12. **Token endpoint:** Không cấp scope/audience vượt grant khi đổi code hoặc refresh token?
13. **Token validation:** RS kiểm issuer, audience, thời hạn, token type, scope và object-level authorization?
14. **Revocation:** Có chính sách xử lý refresh token, access token JWT/opaque và cache sau revoke?
15. **OIDC:** Không nhầm prompt=consent/offline_access với approval version hoặc refresh token bất biến?
16. **Multi-tenant:** Admin consent không lan sang tenant khác hay biến service permission thành user delegation?
17. **Audit:** Có decision event đủ chứng cứ, dấu thời gian, policy version và correlation ID an toàn?
18. **Privacy:** Retention, quyền xem, xóa/pseudonymize được thiết kế mà không thu thập credential thô?
19. **Security:** Consent screen có CSRF/clickjacking protection, trusted client metadata và anti-phishing UX?
20. **Regression:** Có tests stale version, scope escalation, tampering, double submit, replay, revoke, token leakage và RS enforcement?

## 22. Câu hỏi tự đánh giá

**1. Vì sao chỉ lưu consented=true là không đủ?** Vì không biết user chấp thuận quyền nào, qua màn hình phiên bản nào, dành cho client/tenant/resource nào và vào thời điểm nào.

**2. Consent presentation version có phải access token version không?** Không. Presentation version mô tả nội dung đã hiển thị; token có vòng đời và các claims riêng.

**3. Thay một lỗi chính tả từ v2 lên v3 có bắt buộc mọi user consent lại không?** Không mặc định. Cần policy phân loại thay đổi có ảnh hưởng quyền hay không.

**4. Nếu v3 thêm orders:export, grant v1 orders:read có tự tăng quyền không?** Không. AS phải áp dụng chính sách chấp thuận/cấp quyền mới phù hợp.

**5. Hash nội dung consent có tự chứng minh user đã xem và đồng ý không?** Không. Hash chỉ giúp xác minh nội dung; còn cần actor, session/transaction binding, sự kiện quyết định và bảo vệ nguồn lưu.

**6. Tại sao lưu locale?** Bởi bản dịch và câu chữ có thể khác; cần biết người ra quyết định thực sự được hiển thị nội dung theo ngôn ngữ nào.

**7. Khi người dùng Deny một yêu cầu mở rộng quyền, có phải mọi grant cũ đều tự bị revoke?** Không. Deny request mới và revoke kết nối cũ là hai hành động cần quy định ngữ nghĩa riêng.

**8. Grant revision tăng khi revoke có buộc phải tạo consent presentation version mới?** Không. Quyền/trạng thái grant thay đổi không đồng nghĩa màn hình consent đã thay đổi.

**9. Có nên đặt consent_version trong mọi JWT access token không?** Không bắt buộc theo OAuth. Nếu có claim nội bộ, RS vẫn phải kiểm current state khi cần thu hồi sớm.

**10. Vì sao refresh token không tự cho phép xin scope của presentation mới?** Vì refresh token gắn với grant đã được cấp và phải được AS kiểm; version mới không tự mở rộng quyền.

**11. Consent record admin tenant-A có dùng cho tenant-B được không?** Không nếu người ra quyết định không có thẩm quyền với tenant-B; record phải ràng buộc tenant.

**12. Bài test quan trọng nhất cho version confusion là gì?** Hiển thị v2, publish v3 trong lúc form mở, rồi Approve v2: hệ thống không được cấp bất kỳ quyền mới chỉ có ở v3.

**Ghi nhớ:** **Ghi nhận consent version là bảo toàn ý nghĩa của quyết định cấp quyền theo thời gian.** Để làm được, hệ thống cần **nội dung đã publish bất biến, version/locale/digest, snapshot phạm vi quyền được hiển thị, decision events và current grant có revision**, tất cả ràng buộc đúng **actor, subject, client, tenant, resource và authorization transaction**. Khi scope, policy hoặc nội dung thay đổi, AS phải đánh giá việc **reuse, re-consent, thu hẹp hoặc revoke** chứ không tự tăng quyền. Access token và refresh token vẫn tuân thủ vòng đời riêng; **Resource Server luôn phải kiểm issuer, audience, scope, thời hạn và quyền tài nguyên**, kể cả khi consent version được ghi nhận đầy đủ.
