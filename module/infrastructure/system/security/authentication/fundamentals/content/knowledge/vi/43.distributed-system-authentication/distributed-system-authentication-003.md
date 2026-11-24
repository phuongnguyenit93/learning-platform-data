# Token propagation — Truyền ngữ cảnh xác thực an toàn giữa các dịch vụ

Một người dùng đăng nhập vào ứng dụng thương mại điện tử rồi yêu cầu xem đơn hàng. API gateway chuyển request tới order service; order service cần gọi inventory service và payment service để tổng hợp dữ liệu. Các dịch vụ phía sau phải biết request bắt nguồn từ người dùng nào, dịch vụ nào đang gọi trực tiếp và quyền nào được phép sử dụng. Nếu mọi service chỉ chuyển tiếp nguyên bearer token nhận từ trình duyệt, token có thể bị gửi tới sai audience, lộ qua log hoặc mang quyền rộng hơn mức service tiếp theo cần. Nếu gateway chỉ truyền header X-User-ID do client gửi, attacker có thể tự nhận là người khác.

**Token propagation (truyền token)** là cách chuyển tiếp hoặc trao đổi thông tin xác thực/ủy quyền qua các ranh giới dịch vụ trong một hệ thống phân tán. Mục tiêu là giữ đúng ngữ cảnh của request — chủ thể người dùng, workload gọi trực tiếp, tenant, audience, scope và mục đích — để mỗi dịch vụ xác minh được caller và tự áp dụng authorization policy. Token propagation cần được thiết kế theo trust boundary và semantics của token; việc chuyển một chuỗi token qua nhiều hop không tự động làm các dịch vụ phía sau được phép tin hoặc sử dụng token đó.

Bài học thuộc chương **Authentication trong distributed system** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối token propagation với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập; đồng thời thiết kế luồng truyền danh tính và quyền giữa các dịch vụ sao cho có thể kiểm chứng, giới hạn phạm vi và thu hồi.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích token propagation trong kiến trúc nhiều dịch vụ và phân biệt nó với trace/context propagation.
- Phân biệt token forwarding, token exchange, on-behalf-of delegation và service-to-service authentication.
- Xác định subject, actor, client/workload, audience, scope, tenant và mục đích của token.
- Quyết định khi nào có thể forward access token và khi nào cần đổi token cho downstream service.
- Thiết kế token exchange để giới hạn audience và scope theo từng hop.
- Giữ rõ danh tính người dùng và danh tính workload đang hành động thay mặt người dùng.
- Bảo vệ trust boundary giữa client, gateway, service mesh, microservice, message broker và resource server.
- Truyền ngữ cảnh xác thực qua HTTP/gRPC và luồng bất đồng bộ mà không đưa bearer token vào log/queue không cần thiết.
- Xử lý token expiry, refresh, revocation, retry, cache và lỗi authorization server.
- Phòng chống confused deputy, token substitution, audience confusion, replay và privilege escalation.
- Viết tiêu chí kiểm thử cho từng hop, delegation chain, tenant isolation và thu hồi quyền.

## 2. Token propagation giải quyết vấn đề gì?

Trong ứng dụng đơn khối, một request có thể đi qua nhiều module trong cùng một tiến trình. Trong distributed system, request thường đi qua gateway, backend, worker, API nội bộ và hệ thống dữ liệu. Mỗi dịch vụ có thể nằm trong trust boundary khác nhau, dùng runtime/credential khác nhau và có quyền riêng.

Token propagation cần giữ được ba câu trả lời:

1. **Ai là chủ thể (subject)?** Người dùng hoặc workload mà hành động được thực hiện thay mặt.
2. **Ai đang gọi trực tiếp (actor/caller)?** Service, client hoặc workload gửi request tới hop hiện tại.
3. **Request được phép làm gì ở đâu?** Audience/resource, scope, tenant, action và các điều kiện authorization.

Nếu chỉ giữ subject mà bỏ actor, hệ thống khó điều tra service nào đã gọi downstream. Nếu chỉ giữ actor service mà bỏ user context, downstream có thể không áp dụng được quyền của người dùng. Nếu giữ cả hai nhưng không giới hạn audience/scope, token có thể trở thành quyền truy cập quá rộng.

### 2.1. Token propagation không phải trace propagation

Trace ID, span ID, correlation ID và W3C Trace Context giúp liên kết log/trace giữa các service. Chúng không chứng minh danh tính, không cấp quyền và không được dùng thay token. Attacker có thể tự gửi một traceparent hoặc correlation ID bất kỳ.

Tương tự, header như X-User-ID, X-Roles hoặc X-Tenant-ID không đáng tin nếu được nhận trực tiếp từ client. Chỉ sử dụng identity context được tạo bởi thành phần tin cậy, được xác thực trên kênh nội bộ và/hoặc có chữ ký, đồng thời vẫn kiểm tra authorization ở resource server.

### 2.2. Token không phải toàn bộ authentication context

Một token có thể mang claims về subject, audience, scope, thời hạn và client. Những dữ liệu khác như phương thức MFA, độ mới xác thực, thiết bị, transaction risk hoặc session state có thể nằm ở token khác hay hệ thống server-side. Không tự suy ra rằng một token hợp lệ có nghĩa mọi thao tác nhạy cảm đều được phép.

## 3. Phân biệt subject, actor và workload identity

Trong một chuỗi gọi service, nhiều principal có thể cùng liên quan tới một hành động:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Subject | Chủ thể mà hành động hướng tới hoặc được thực hiện thay mặt | Người dùng Alice |
| Actor | Principal thực hiện hành động thay cho subject ở hop hiện tại | Order service |
| Client | Ứng dụng xin token hoặc gọi authorization server | Web app hoặc backend client |
| Workload identity | Danh tính của service/tiến trình đang chạy | spiffe://prod.example/ns/shop/sa/orders |
| Audience/resource | Resource server dự kiến chấp nhận token | Payment API |
| Tenant | Phạm vi tổ chức/dữ liệu | Tenant của Alice |
| Delegation | Quyền cho actor hành động thay mặt subject trong phạm vi xác định | Order service được phép tạo payment intent thay Alice |

### 3.1. Giữ cả user context và service context

Ví dụ: Alice yêu cầu tạo đơn hàng. Order service nhận request đã xác thực từ gateway, rồi gọi payment service. Payment cần biết:

- Người dùng Alice là subject của thao tác.
- Order service là workload actor trực tiếp.
- Token dành cho payment API.
- Scope chỉ cho phép tạo/ủy quyền payment intent.
- Tenant và order reference phù hợp.

Payment cũng phải xác thực workload order service, ví dụ bằng mTLS, workload identity hoặc client authentication. Một user token hợp lệ không thay thế việc xác thực service gọi nó; ngược lại, mTLS xác thực order service không tự chứng minh Alice có quyền thanh toán đơn hàng.

### 3.2. Delegation và impersonation

- **Delegation:** service được phép thực hiện một tập hành động giới hạn thay mặt user; actor và subject được phân biệt.
- **Impersonation:** service hành động như thể chính nó là user; nếu hệ thống hỗ trợ, phải có policy, audit và phạm vi rất chặt.

Không âm thầm biến workload identity thành user identity. Audit cần thể hiện ai khởi tạo hành động, service nào thực hiện và quyền nào đã được sử dụng.

## 4. Những mẫu token propagation thường gặp

Không có một mẫu duy nhất phù hợp mọi kiến trúc. Chọn mẫu theo audience, trust boundary, delegation và khả năng của identity provider.

| Mẫu | Cách hoạt động | Khi phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| Forward original access token | Service A chuyển token nhận được tới service B | Token được phát hành rõ ràng cho B hoặc một resource set bao gồm B | Sai audience, scope quá rộng, token lộ qua nhiều hop |
| Token exchange | A đổi token đầu vào lấy token mới dành cho B | Downstream cần audience/scope khác hoặc cần actor context | Trust policy của issuer, subject/actor mapping, exchange scope |
| On-behalf-of (OBO) | Backend xin token để gọi downstream thay mặt user | API cần giữ user delegation qua nhiều service | Phụ thuộc provider/profile; phải giữ actor chain và consent/policy |
| Workload-only authentication | A gọi B bằng identity riêng của A | Tác vụ nền/service operation không cần user delegation | Không được suy ra user permission từ quyền service |
| Signed identity assertion | Gateway/IdP phát assertion nội bộ có chữ ký | Hệ thống có trust boundary nội bộ được xác định | Key distribution, audience, expiry, replay và header spoofing |

### 4.1. Forward original token

Forward token là cách đơn giản nhất: service A nhận access token rồi chuyển nguyên token đó cho service B. Chỉ dùng khi token thực sự được cấp cho B hoặc resource set bao gồm B, B tin issuer đó và scope phù hợp. B vẫn phải tự xác minh token.

Không forward token chỉ vì “nó đang có sẵn trong request”. Nếu token có audience là API gateway hoặc service A, service B phải từ chối token đó. Một chữ ký JWT hợp lệ không làm token trở thành credential dùng chung cho mọi API.

### 4.2. Token exchange

Token exchange cho phép một client/workload gửi token hiện có tới authorization server và xin một token mới với resource/audience/scope phù hợp. Token mới có thể giữ subject, thể hiện actor/delegation theo profile và có thời hạn ngắn hơn.

Token exchange phù hợp khi:

- Token gốc dành cho service A, nhưng A cần gọi service B.
- B cần scope hẹp hơn token gốc.
- Cần thể hiện A là actor đang hành động thay mặt user.
- Cần tách token external khỏi token nội bộ.
- Cần đổi từ identity của workload sang token cho resource cụ thể.

### 4.3. On-behalf-of

OBO là mẫu backend xin token downstream thay mặt user dựa trên token đầu vào và danh tính client/backend. Một số identity platform triển khai OBO theo profile riêng; về nguyên lý, backend phải được phép delegate, token đầu vào phải hợp lệ, resource/audience đích phải rõ và token đầu ra chỉ chứa quyền cần thiết.

Không giả định mọi OAuth provider đều hỗ trợ OBO theo cùng cách. Kiểm tra giao thức, claims, actor semantics, consent và policy của issuer thực tế.

## 5. Audience và scope theo từng hop

Audience cho biết resource server nào được phép chấp nhận token. Scope/permission mô tả quyền được cấp. Khi request đi qua nhiều service, mỗi hop cần token phù hợp với resource đích.

Ví dụ:

| Hop | Caller | Token audience | Quyền |
| --- | --- | --- | --- |
| Browser → API gateway | Web client | Orders API | orders.read |
| Gateway → Order service | Gateway/workload + user context | Order service | orders.read hoặc orders.create |
| Order service → Payment | Order service acting for user | Payment API | payment.intent.create |
| Order service → Inventory | Order service | Inventory API | inventory.reserve |

Tên scope chỉ là ví dụ. Mỗi hệ thống phải định nghĩa scope/permission theo tài nguyên và hành động thật.

### 5.1. Downscoping

Downscoping là giảm quyền của token đầu ra so với token đầu vào:

- Audience chỉ là service đích.
- Scope chỉ gồm thao tác cần thiết.
- Thời hạn ngắn hơn.
- Tenant/resource bị giới hạn nếu authorization server hỗ trợ.
- Actor chain được giữ theo policy.

Không trao cho payment service toàn bộ quyền orders.*, inventory.* hoặc quyền quản trị chỉ vì order service có các quyền đó.

### 5.2. Không nhầm audience với scope

Audience trả lời “token dành cho resource server nào?” Scope trả lời “token được phép làm hành động nào?”. Token đúng audience nhưng scope quá rộng vẫn nguy hiểm; token scope hẹp nhưng sai audience cũng phải bị từ chối.

### 5.3. Kiểm tra tại resource server

Service B phải tự kiểm tra:

- Issuer và trust configuration.
- Chữ ký/algorithm/key phù hợp.
- Audience của chính B.
- Expiry và not-before.
- Scope/permission cần cho action.
- Subject/actor/client mapping.
- Tenant và resource ownership.
- Sender constraint nếu token được ràng buộc với key/certificate.

Gateway xác minh trước không có nghĩa service phía sau được bỏ qua validation, trừ khi kiến trúc dùng một trust mechanism nội bộ được thiết kế và bảo vệ rõ ràng.

## 6. OAuth 2.0 Token Exchange và delegation

OAuth 2.0 Token Exchange (RFC 8693) định nghĩa cách client trình một subject token và có thể cả actor token để xin security token khác. Authorization server quyết định có chấp nhận exchange không và token mới được cấp cho audience/resource, scope và loại token nào.

Các khái niệm thường gặp:

- subject_token: token đại diện cho subject mà client muốn hành động thay mặt.
- actor_token: token đại diện cho actor/client đang thực hiện delegation, nếu flow/profile sử dụng.
- requested_token_type: loại token đầu ra mong muốn.
- audience hoặc resource: resource đích.
- scope: quyền được yêu cầu.
- act claim: có thể thể hiện actor trong token đầu ra theo semantics của RFC/profile.

Không phải mọi token exchange đều phải có actor token hoặc claim act; cách biểu diễn phụ thuộc policy và profile. Authorization server phải kiểm tra client có được phép exchange subject token đó, được phép hành động thay mặt subject và được phép xin audience/scope đích hay không.

### 6.1. Luồng token exchange khái niệm

~~~mermaid
sequenceDiagram
    participant U as User
    participant G as API Gateway
    participant A as Order Service
    participant AS as Authorization Server
    participant B as Payment Service
    U->>G: Request + token cho Orders API
    G->>G: Xác minh token, session và policy
    G->>A: Request + context/token dành cho Order
    A->>AS: Token exchange: subject + actor, audience=Payment
    AS->>AS: Kiểm tra delegation, audience, scope
    AS-->>A: Access token mới dành cho Payment
    A->>B: Request + token mới; xác thực workload A
    B->>B: Validate token và authorization
    B-->>A: Kết quả
    A-->>G: Kết quả đơn hàng
    G-->>U: Response
~~~

### 6.2. Trust policy của token exchange

Authorization server không nên exchange bất kỳ token nào mà client đưa vào. Cần ràng buộc:

- Issuer và loại subject token được chấp nhận.
- Client/workload được phép yêu cầu exchange.
- Subject có quyền liên quan tới resource/action không.
- Actor được phép delegate cho subject trong phạm vi nào.
- Audience/resource và scope có nằm trong allowlist không.
- Tenant/environment có khớp không.
- Token đầu ra có expiry, confirmation/key binding và claims phù hợp không.

Không cho client tự khai subject/actor bằng form field rồi coi đó là delegation. Subject và actor phải được suy ra từ token đã xác minh hoặc identity authority đáng tin.

## 7. Ranh giới tin cậy giữa gateway và microservice

Gateway thường là điểm đầu tiên xác minh token từ người dùng, nhưng gateway không nên biến mọi claim thành header tùy ý rồi để backend tin mà không có bảo vệ.

### 7.1. Header identity nội bộ

Nếu kiến trúc dùng header nội bộ như X-Authenticated-Subject, X-Authenticated-Tenant hoặc X-Actor-Service:

- Gateway phải xóa header cùng tên do client gửi trước khi thêm giá trị của nó.
- Backend chỉ nhận traffic từ gateway/proxy được xác thực, ví dụ mTLS và network policy.
- Header phải được tạo từ token/identity đã xác minh.
- Cần integrity protection hoặc signed assertion nếu header đi qua nhiều hop/ranh giới không hoàn toàn tin cậy.
- Backend không được cho phép client truy cập trực tiếp bỏ qua gateway nếu backend dựa vào gateway assertion.
- Mỗi service vẫn áp dụng authorization theo resource/action.

Header không có chữ ký trên một mạng nội bộ rộng không tự nhiên trở nên đáng tin. “Internal network” không phải ranh giới xác thực đủ mạnh.

### 7.2. Signed internal assertion

Một gateway có thể phát assertion ngắn hạn cho service nội bộ, gồm issuer, audience cụ thể, subject, actor, tenant, scope, issued-at và expiry. Backend xác minh chữ ký bằng key/trust bundle đã cấu hình, kiểm tra audience và thời gian, rồi áp dụng policy. Assertion cần key rotation, revocation strategy và chống replay phù hợp.

Không tái sử dụng một assertion dành cho service A ở service B nếu audience không cho phép. Không ký assertion chứa quyền mà gateway không có thẩm quyền cấp.

### 7.3. Service mesh

Service mesh có thể cung cấp mTLS giữa sidecar/proxy và workload identity cho caller. Mesh giúp xác thực workload ở tầng transport, nhưng không tự thay thế user authorization. Nếu service cần user context, cần token/delegation riêng và xác minh claims. Không coi mTLS identity của order service là bằng chứng Alice được phép thanh toán.

## 8. Truyền token qua HTTP và gRPC

Với HTTP, access token thường được gửi trong Authorization: Bearer ... tới resource server đúng audience. Với gRPC, metadata có thể mang credential theo quy ước của framework, nhưng vẫn cần TLS/mTLS, validation và redaction.

### Nguyên tắc

- Chỉ gửi token tới host/service đúng audience.
- Không đưa access/refresh token vào URL query, path, fragment hoặc redirect parameter.
- Không gửi token qua HTTP không mã hóa.
- Không forward toàn bộ inbound headers một cách mù quáng.
- Chỉ chuyển tiếp header cần thiết; xóa client-supplied identity headers.
- Không log Authorization, cookie, token exchange request/response hoặc DPoP proof nhạy cảm.
- Dùng TLS/mTLS giữa các service; kiểm tra certificate/hostname/workload identity.
- Giữ timeout và retry policy phù hợp với expiry của token.
- Không cache token vượt expiry hoặc chia sẻ token giữa tenant/client không tương ứng.

### 8.1. Inbound token và outbound token

Đặt tên/biến riêng cho token inbound và outbound trong code để tránh vô tình forward nhầm:

- Inbound token: token mà service nhận từ caller, có audience của service hiện tại.
- Outbound token: token được exchange/cấp cho downstream resource.
- Workload credential: certificate hoặc client credential dùng để xác thực service với authorization server/resource server.

Không ghi các token này vào exception message hoặc debug output.

### 8.2. gRPC metadata

Metadata của gRPC có thể chứa bearer token hoặc identity context. Cần áp dụng cùng nguyên tắc như HTTP: audience đúng, channel bảo mật, không log secret, không chuyển metadata không tin cậy sang downstream. Interceptor có thể tập trung validation và token exchange nhưng không được bỏ qua authorization tại service xử lý nghiệp vụ.

## 9. Token propagation trong hệ thống bất đồng bộ

Queue, event bus và background worker có vòng đời khác request HTTP. Message có thể nằm trong broker nhiều phút/giờ, được retry, dead-letter hoặc xử lý sau khi user session/token hết hạn. Đưa access token người dùng vào message thường tạo rủi ro lớn:

- Token có thể hết hạn trước khi consumer xử lý.
- Broker, dead-letter queue, replay tool và log có thể lưu token lâu hơn dự kiến.
- Message có thể bị phát lại hoặc chuyển sang consumer khác.
- Quyền của user có thể đã thay đổi sau khi message được tạo.
- Consumer có thể vô tình dùng token của user cho hành động ngoài mục đích ban đầu.

### 9.1. Message envelope

Một event có thể mang identity context tối thiểu, không mang bearer token:

~~~json
{
  "event_id": "evt_...",
  "event_type": "ORDER_SUBMITTED",
  "occurred_at": "2026-11-22T06:00:00Z",
  "subject_ref": "user-ref-...",
  "actor_workload": "orders-service",
  "tenant_ref": "tenant-ref-...",
  "purpose": "fulfill-order",
  "authorization_ref": "decision-ref-...",
  "correlation_id": "corr-..."
}
~~~

Đây là ví dụ cấu trúc minh họa. subject_ref, tenant_ref và authorization_ref phải là reference không có quyền bearer. Message cần được broker ACL bảo vệ, xác thực producer, integrity protection khi cần và kiểm tra schema/version.

### 9.2. Quyết định authorization tại enqueue hay consume

Thiết kế phải trả lời quyền được kiểm tra ở thời điểm nào:

- **Authorize at enqueue:** API kiểm tra user có quyền gửi lệnh; event được xem là lệnh đã được chấp thuận trong phạm vi rõ ràng. Consumer xác minh producer/message và chỉ thực hiện đúng action đã được authorize.
- **Authorize at consume:** Consumer hoặc policy service đánh giá lại quyền khi xử lý. Cần có danh tính subject/actor đáng tin và dữ liệu đủ để kiểm tra; không dựa vào access token đã hết hạn nằm trong queue.
- **Pre-authorized task capability:** hệ thống cấp capability/token riêng cho một task, audience hẹp, action cụ thể, thời hạn và số lần sử dụng giới hạn; consumer xác minh và consume theo policy.

Không tự động coi message hợp lệ là bằng chứng user vẫn có quyền hiện tại. Với hành động nhạy cảm hoặc có độ trễ dài, thường cần xác định rõ semantics nếu user bị disable hoặc quyền bị thu hồi trước khi consumer chạy.

### 9.3. Producer và consumer identity

Consumer cần xác thực broker và producer/event source theo cơ chế của nền tảng. Workload identity của consumer chứng minh worker nào đang xử lý; nó không chứng minh event được phát bởi service hợp lệ nếu broker ACL/signature/schema không được kiểm tra. Giữ audit về subject gốc, producer, consumer và policy decision.

## 10. Token expiry, refresh và cache

Token propagation tạo thêm các vấn đề vòng đời:

- Token inbound có thể sắp hết hạn khi service nhận request.
- Outbound token có thể hết hạn trước khi downstream xử lý.
- Nhiều request đồng thời có thể cùng yêu cầu token exchange.
- Cache token có thể bị dùng nhầm giữa audience, scope, tenant hoặc subject.
- Authorization server có thể tạm thời không khả dụng.

### 10.1. Cache key đúng

Nếu cache outbound token, key phải phân biệt tối thiểu các yếu tố ảnh hưởng quyền:

- Issuer/authorization server.
- Client/workload identity.
- Subject/delegation context nếu token đại diện user.
- Audience/resource.
- Scope/permission.
- Tenant hoặc security boundary.
- Sender-constrained key/certificate binding nếu áp dụng.

Không cache theo mỗi client ID nếu token còn phụ thuộc user, tenant, audience hoặc scope. Không chia sẻ token giữa hai user chỉ vì cùng service gọi một API.

### 10.2. Token refresh tại đúng boundary

Service không nên dùng refresh token của người dùng như một bí mật chung cho toàn bộ microservice. Refresh token thường thuộc client/session được cấp và cần được lưu, rotation, revoke theo policy. Downstream service nên nhận access token phù hợp hoặc token exchange result, không nhận refresh token gốc.

### 10.3. Authorization server outage

Nếu không thể exchange token:

- Không tự phát token nội bộ hoặc bỏ qua audience/scope.
- Retry có backoff và giới hạn.
- Dùng cache token còn hạn nếu cache key và policy còn hợp lệ.
- Fail closed cho hành động nhạy cảm nếu không thể xác minh quyền.
- Có thể trả lỗi tạm thời/503 theo contract.
- Không lưu token inbound vào queue để “dùng lại sau” nếu token có thể hết hạn hoặc quyền thay đổi.

## 11. Revocation và thay đổi quyền giữa các hop

Token đầu ra có thể tiếp tục tồn tại sau khi user bị disable, session bị revoke hoặc workload bị compromise. Hệ thống cần xác định:

- Token nào bị revoke: inbound session, refresh family, outbound token, workload credential hay tất cả.
- Resource server có kiểm tra introspection/denylist/session epoch không.
- Access JWT có thể còn hợp lệ tới expiry không.
- Delegation grant còn hiệu lực không.
- Message/task đang chờ có cần hủy hoặc đánh giá lại không.

Token exchange không loại bỏ nhu cầu revocation. Nó tạo thêm token có vòng đời riêng; cần theo dõi quan hệ giữa token đầu vào, token đầu ra, grant và actor.

### 11.1. Delegation grant

Nếu service A được phép gọi service B thay mặt user, grant đó cần giới hạn theo client, subject, audience, scope và thời hạn. Khi user revoke consent, bị disable hoặc policy thay đổi, authorization server cần ngừng exchange mới; resource server cần có cơ chế xử lý token đã cấp.

### 11.2. User logout

Logout khỏi web app có thể revoke session/refresh token tại identity provider, nhưng token đã được exchange cho downstream có thể còn hiệu lực tới expiry nếu resource server không kiểm tra trạng thái. Với thao tác nhạy cảm, cân nhắc session reference, token introspection hoặc revocation epoch để rút ngắn cửa sổ.

## 12. Các kiểu tấn công và lỗi thiết kế

| Mối đe dọa | Cách xảy ra | Biện pháp phòng chống |
| --- | --- | --- |
| Token leakage | Token bị ghi vào log, trace, URL, queue hoặc crash dump | Redaction, secret scanning, TLS, không đưa token vào URL/message |
| Audience confusion | Service B chấp nhận token dành cho service A | Kiểm tra aud tại từng resource server; exchange cho audience mới |
| Scope amplification | Token downstream có quyền rộng hơn action cần thiết | Downscoping và authorization theo resource/action |
| Confused deputy | Service có quyền rộng hành động thay caller không đủ quyền | Giữ subject/actor, delegation policy và caller authorization |
| Header spoofing | Client tự gửi X-User-ID/X-Roles | Strip inbound headers; signed assertion hoặc token đã xác minh |
| Token substitution | Token hợp lệ của tenant/client khác được đưa vào request | Kiểm tra issuer, audience, client, subject và tenant binding |
| Replay | Token/proof/message cũ được phát lại | TTL, nonce/jti khi phù hợp, idempotency, one-time consume |
| Cross-tenant propagation | Context user/tenant bị dùng lẫn giữa request | Cache key và policy tenant-aware; kiểm thử isolation |
| Delegation chain loss | Actor trung gian bị bỏ mất, audit chỉ thấy subject | Giữ actor/delegation context theo profile |
| Over-trusting gateway | Backend bỏ qua validation và nhận traffic trực tiếp | mTLS, network policy, signed assertion và backend authorization |
| Async privilege drift | User mất quyền nhưng event cũ vẫn chạy với quyền service rộng | Quy định authorize-at-enqueue/consume, task capability và cancel policy |
| Token cache mix-up | Cache trả token sai user/audience/scope | Cache key đầy đủ, TTL và partition theo security context |

### 12.1. Phòng chống confused deputy

Một service có thể có quyền gọi nhiều API. Nếu service nhận một request từ user rồi dùng quyền riêng của mình để thực hiện mọi thao tác, nó có thể trở thành confused deputy. Cần:

- Xác thực workload caller và subject user riêng.
- Kiểm tra user có quyền khởi tạo hành động không.
- Dùng token exchange/downscoping hoặc policy decision cho downstream.
- Không cho client chọn subject tùy ý.
- Ghi audit subject, actor, action, resource và tenant.
- Giới hạn service role theo nhiệm vụ thực tế.

## 13. Ví dụ thực tế: order service gọi payment và inventory

Alice đăng nhập bằng passkey vào ứng dụng. Client nhận access token dành cho Orders API. Alice tạo đơn hàng; order service cần giữ quyền người dùng nhưng chỉ gọi đúng hai dịch vụ downstream.

### Luồng an toàn

1. Client gửi token tới Orders API qua TLS.
2. Gateway/resource server kiểm tra issuer, audience, expiry, scope, session/risk policy.
3. Gateway chuyển request tới order service qua mTLS hoặc workload identity; inbound identity headers do client gửi đã bị loại bỏ.
4. Order service xác minh user context và workload identity của gateway.
5. Order service yêu cầu authorization server exchange token cho Payment API với scope payment.intent.create, giữ subject Alice và actor order service theo profile.
6. Order service xác thực workload với payment service qua mTLS; gửi outbound token chỉ tới Payment API.
7. Payment xác minh issuer, audience, expiry, actor/subject, tenant và scope; kiểm tra Alice có quyền với order/payment intent.
8. Order service thực hiện exchange riêng cho Inventory API với scope inventory.reserve.
9. Mỗi service ghi audit subject, actor, action, resource và correlation ID; không ghi token.
10. Response quay về client; token downstream không được trả cho browser.

### Vì sao không dùng một token cho mọi hop?

Orders, Payment và Inventory là resource server khác nhau. Token dành cho Orders không tự động được Payment/Inventory chấp nhận. Token exchange tạo credential phù hợp cho từng audience và scope; service identity xác thực caller ở tầng workload. Cách này giới hạn tác động nếu một token downstream bị lộ.

## 14. Pseudocode: exchange token cho downstream

Ví dụ khái niệm theo mẫu token exchange. API thực tế phụ thuộc authorization server và profile OBO:

~~~ts
async function callPaymentAsUser(inboundToken, order, workloadIdentity) {
  const userContext = await validateInboundToken(inboundToken, {
    expectedAudience: "orders-api"
  });
  if (!userContext.valid) throw new AuthenticationError();

  const decision = await authorizeOrderAction({
    subject: userContext.subject,
    tenant: userContext.tenant,
    action: "payment.intent.create",
    resource: order.id
  });
  if (!decision.allowed) throw new AuthorizationError();

  const outboundToken = await authorizationServer.exchange({
    subjectToken: inboundToken,
    actorIdentity: workloadIdentity,
    audience: "payment-api",
    scope: ["payment.intent.create"],
    tenant: userContext.tenant
  });

  return paymentClient.createIntent({
    order,
    accessToken: outboundToken,
    clientCertificate: workloadIdentity.certificate
  });
}
~~~

Đây là pseudocode, không phải endpoint OAuth cụ thể. Trong triển khai:

- Xác minh inbound token dành cho service hiện tại.
- Xác minh workload identity của order service bằng mTLS/managed identity/federation.
- Authorization server phải kiểm tra client được phép exchange subject token đó.
- Không tin tenant/subject do request body tự khai; lấy từ context đã xác minh và policy.
- Outbound token chỉ dành cho Payment API và có scope tối thiểu.
- Payment vẫn tự xác minh token, workload caller và authorization.
- Không log token hoặc trả outbound token cho browser.
- Cache token phải phân biệt subject, actor, audience, scope và tenant.

## 15. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token dành cho service A được gửi tới service B | B từ chối nếu audience không bao gồm B |
| Token đầu vào hợp lệ và exchange được phép | Issuer cấp token mới đúng audience/scope đã duyệt |
| Client không có quyền exchange subject token | Authorization server từ chối |
| Client tự khai subject khác | Bị từ chối; subject lấy từ token đã xác minh |
| Outbound token có scope rộng hơn policy | Không cấp hoặc resource server từ chối |
| Workload caller không hợp lệ | Service đích từ chối dù user token hợp lệ |
| Workload hợp lệ nhưng user thiếu quyền | Authorization từ chối |
| Client gửi X-User-ID giả | Gateway strip/ignore; backend dùng identity đã xác minh |
| Gateway assertion sai audience/hết hạn | Backend từ chối |
| Backend bị gọi trực tiếp bỏ qua gateway | mTLS/network/auth policy ngăn truy cập hoặc backend tự xác minh token |
| Token bị log trong tracing | Redaction/secret scan phát hiện; không có raw token trong telemetry |
| Token cache giữa hai user | Cache key tách biệt; không trả token của user này cho user kia |
| Token cache giữa hai tenant | Tenant isolation được giữ |
| User logout sau token exchange | Downstream revoke/TTL/introspection policy hoạt động theo SLA |
| User bị disable khi message đang chờ | Consumer xử lý theo authorize-at-enqueue/consume policy đã định nghĩa |
| Message bị phát lại | Event ID/idempotency/one-time capability ngăn side effect trùng |
| Authorization server tạm lỗi | Không bỏ qua validation hoặc tự cấp token; retry/fail theo policy |
| Token inbound gần hết hạn | Exchange từ chối hoặc áp dụng policy; không phát token downstream không có căn cứ |
| OBO chain qua nhiều service | Subject và actor được giữ đúng, audit xác định được từng hop |
| Service A gọi Payment và Inventory | Mỗi downstream nhận token đúng audience và scope riêng |
| JWT có chữ ký hợp lệ nhưng sai issuer/algorithm | Từ chối |
| Trace ID do client tự gửi | Chỉ dùng correlation; không được coi là identity hoặc authorization |

### Chỉ số vận hành

Theo dõi số token exchange theo client/audience, exchange denial theo reason code, token audience mismatch, scope escalation attempt, token cache hit/miss, authorization server latency/error, token expiry khi downstream xử lý, delegation chain depth, cross-tenant denial và số token bị phát hiện trong log/queue. Không đưa token hoặc PII thô vào metric label.

## 16. Bài tập tự kiểm tra

Một nền tảng SaaS có API gateway, order service, billing service và reporting worker. Người dùng có thể xem đơn hàng, thanh toán và xuất báo cáo. Các service dùng mTLS trong service mesh; access token người dùng do IdP phát hành.

Hãy:

1. Vẽ chuỗi request và xác định subject, actor, workload identity, audience và scope ở từng hop.
2. Quyết định khi nào forward original token, khi nào dùng token exchange/OBO và khi nào chỉ dùng workload identity.
3. Thiết kế token exchange từ Orders API sang Billing API với scope hẹp.
4. Giải thích vì sao mTLS không thay thế user authorization.
5. Thiết kế message envelope cho reporting worker mà không lưu bearer token trong queue.
6. Xác định cách xử lý khi user logout hoặc mất quyền trước lúc worker chạy.
7. Thiết kế token cache key và cách tránh trộn tenant/user.
8. Viết test case cho audience confusion, header spoofing, confused deputy, token leakage và async replay.

**Gợi ý đánh giá:** lời giải tốt phải giữ rõ subject và actor, xác minh workload ở từng trust boundary, dùng audience/scope hẹp, exchange token khi downstream cần resource context khác, xử lý async không phụ thuộc bearer token dài hạn và ghi audit không chứa secret.

---

**Ghi nhớ:** token propagation giữ ngữ cảnh xác thực/ủy quyền khi request đi qua nhiều service. Trước mỗi hop, hãy xác định **subject, actor, workload identity, audience, scope và tenant**. Chỉ forward token khi resource đích được phép nhận token đó; nếu audience hoặc quyền cần thay đổi, dùng token exchange/OBO để cấp token mới có phạm vi hẹp. Xác thực workload riêng bằng mTLS/managed identity, không tin identity header tự khai, không đưa bearer token vào URL/log/queue và vẫn kiểm tra authorization tại resource server. Truyền token đúng cách giúp giữ delegation; nó không biến một token hợp lệ thành quyền truy cập toàn hệ thống.
