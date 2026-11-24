# Service identity propagation

## 1. Service identity propagation là gì?

**Service identity propagation (truyền tải danh tính giữa các dịch vụ)** là cách một hệ thống giữ được ngữ cảnh về chủ thể và quyền hạn khi request đi qua nhiều service. Khi Service A gọi Service B, rồi B gọi tiếp Service C, mỗi service cần biết workload nào đang gọi, request đang hành động thay ai nếu có người dùng cuối, và quyền đó được giới hạn tới tài nguyên nào.

Ví dụ: nhân viên đăng nhập vào cổng thanh toán, cổng gọi Order Service, Order Service gọi Risk Service và Payment Service. Payment Service cần xác minh request đến từ workload Order Service đáng tin, đồng thời có thể cần biết giao dịch được khởi tạo bởi người dùng nào và trong tenant nào. Nếu chỉ biết request đến từ một service account dùng chung, hệ thống có thể mất ngữ cảnh người dùng. Nếu chuyển tiếp nguyên bearer token của người dùng qua mọi service, token có thể bị dùng sai audience hoặc lộ sang một trust boundary khác.

Service identity propagation không đơn giản là thêm header `X-User-Id` vào request. Danh tính phải được xác thực bằng cơ chế tin cậy, ràng buộc với đúng request hoặc token, và được từng service kiểm tra trước khi quyết định authorization.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, chủ đề này kết nối authentication, workload identity, OAuth token, session, federation và authorization boundary. Mỗi hop trong kiến trúc cần có danh tính rõ, quyền tối thiểu và bằng chứng có thể kiểm tra.

## 2. Những danh tính cần phân biệt

Trong một request liên dịch vụ, có thể tồn tại nhiều chủ thể khác nhau:

| Danh tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **End-user identity / subject** | Người dùng hoặc principal mà hành động nghiệp vụ đại diện. | Nhân viên tạo yêu cầu thanh toán. |
| **Workload identity** | Danh tính của process, service, pod hoặc workload đang thực thi request. | Order Service chạy trong Kubernetes. |
| **Client identity** | Ứng dụng hoặc OAuth client khởi tạo luồng lấy token. | Backend web portal đã đăng ký với IdP. |
| **Actor identity** | Chủ thể trung gian thực sự thực hiện hành động thay cho subject. | Order Service gọi Payment Service theo ủy quyền. |
| **Tenant identity** | Phạm vi tổ chức mà request và tài nguyên thuộc về. | Tenant của doanh nghiệp đang thanh toán. |
| **Resource identity** | Dịch vụ hoặc tài nguyên mà token/quyền được cấp để truy cập. | Payment API hoặc một payment record cụ thể. |

Một service có thể vừa là actor vừa là workload. Người dùng là subject, còn workload service là actor thực hiện lời gọi kỹ thuật. Không nên gộp các vai trò này thành một trường `userId` duy nhất.

### 2.1. Subject và actor

**Subject** trả lời câu hỏi “hành động này đại diện cho ai?”. **Actor** trả lời “thành phần nào đang thực hiện hành động?”. Trong một chuỗi delegation, actor có thể thay đổi qua từng hop trong khi subject vẫn là người dùng ban đầu.

Ví dụ:

- Subject: `user-42`.
- Actor đầu tiên: `web-portal`.
- Actor tiếp theo: `order-service`.
- Resource server: `payment-service`.

Payment Service có thể cần cả subject và actor để kiểm tra quyền nghiệp vụ và chính sách workload. Nếu chỉ tin subject, nó có thể bỏ qua việc caller là một service không được phép gọi endpoint. Nếu chỉ tin actor, nó có thể không phân biệt hành động nào đang được thực hiện thay mặt người dùng nào.

## 3. Authentication, propagation và authorization

Ba hoạt động này giải quyết các câu hỏi khác nhau:

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Caller là ai và bằng chứng có hợp lệ không? | Payment Service xác minh workload certificate hoặc access token. |
| **Identity propagation** | Ngữ cảnh subject/actor/tenant được truyền qua các hop ra sao? | Order Service đổi token để gọi Payment API thay mặt user. |
| **Authorization** | Caller được phép làm gì trên resource này? | Payment Service kiểm tra scope, tenant, ownership và transaction state. |

Một token hợp lệ chỉ chứng minh issuer đã phát hành token với các claim nhất định. Nó không tự chứng minh request được phép thực hiện mọi thao tác. Resource service phải xác minh token và áp dụng authorization tại chính ranh giới của mình.

Tương tự, trace ID, request ID hoặc header ghi tên người dùng không phải bằng chứng authentication. Chúng hữu ích cho observability nhưng không được dùng thay token hoặc workload identity đã xác minh.

## 4. Các mô hình truyền danh tính phổ biến

Không có một mô hình duy nhất phù hợp với mọi kiến trúc. Cần chọn mô hình theo việc service đích cần biết workload, người dùng cuối hay cả hai.

| Mô hình | Ngữ cảnh được truyền | Khi phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Service identity only** | Danh tính workload gọi service đích. | Background job hoặc tác vụ service-owned không đại diện cho một người dùng cụ thể. | Service account dùng chung có quyền quá rộng. |
| **Delegated user token** | Danh tính và quyền người dùng được ủy quyền tới API đích. | Service gọi API thay mặt người dùng trong phạm vi được cấp. | Token có audience/scope rộng hoặc bị relay sang service khác. |
| **Token exchange / on-behalf-of** | Token mới cho resource/audience kế tiếp, có thể giữ subject và ghi nhận actor. | Chuỗi microservice cần quyền riêng cho từng API. | Sai subject/actor, token exchange không giới hạn hoặc delegation chain không được kiểm tra. |
| **Trusted identity context** | Assertion hoặc context nội bộ có chữ ký/bảo vệ toàn vẹn. | Hệ thống nội bộ có trust broker và giao thức context rõ ràng. | Header giả mạo nếu gateway không xóa và tái tạo context. |
| **Workload-to-workload identity** | Danh tính workload được chứng minh bằng certificate hoặc token ngắn hạn. | Service-to-service không cần end-user context. | Certificate/key bị đánh cắp hoặc trust domain quá rộng. |

### 4.1. Service identity only

Nếu một scheduled job tổng hợp số liệu hệ thống, không có người dùng cụ thể đứng sau, nó có thể gọi Analytics Service bằng workload identity riêng. Service đích kiểm tra client/workload, audience, scope và policy.

Không nên gán một user giả như `admin` cho mọi tác vụ máy. Làm vậy khiến audit sai lệch và tạo quyền người dùng không cần thiết cho workload.

### 4.2. Delegated user identity

Nếu một người dùng yêu cầu xem dữ liệu đơn hàng của chính họ, downstream service có thể cần subject để kiểm tra ownership. Token cần biểu diễn đúng user context và chỉ cho phép resource đích thực hiện các thao tác đã được ủy quyền.

Không nên dùng một service credential mạnh để bỏ qua authorization của người dùng. Việc service có quyền đọc toàn bộ database không có nghĩa mọi request từ người dùng đều được phép đọc mọi record.

### 4.3. Token exchange và on-behalf-of

Khi Service A nhận token dành cho A nhưng cần gọi Service B, A có thể dùng cơ chế token exchange hoặc flow on-behalf-of do IdP hỗ trợ để nhận token mới dành cho B. Token mới có thể giữ subject ban đầu, giới hạn audience và scope cho API đích, đồng thời thể hiện actor theo profile được sử dụng.

Token exchange giúp tránh chuyển một bearer token có audience dành cho API A sang API B. Tuy nhiên, exchange chỉ an toàn khi authorization server kiểm tra caller, subject token, actor token nếu có, resource/audience yêu cầu, scope và policy delegation.

## 5. Workload identity cho service-to-service

Workload identity là danh tính được gán cho một workload đang chạy, không phụ thuộc vào việc có nhân viên đăng nhập tương tác hay không. Nó có thể được cấp bởi cloud IAM, Kubernetes workload identity, SPIFFE/SPIRE hoặc một hệ thống certificate nội bộ.

Một workload identity tốt cần:

- Có định danh ổn định trong trust domain, ví dụ service, namespace, environment và workload.
- Được cấp bằng cơ chế xác minh workload, không dựa trên tên tự khai trong request.
- Có credential ngắn hạn hoặc cơ chế rotation tự động.
- Chỉ được cấp quyền gọi đúng service/resource cần thiết.
- Có owner kỹ thuật và quy trình thu hồi khi workload bị xóa hoặc xâm nhập.
- Được ghi nhận trong audit để truy vết service caller.

### 5.1. Certificate và mTLS

Với mutual TLS (mTLS), cả client và server xác thực certificate trong quá trình thiết lập TLS. Server có thể dùng certificate client để xác định workload caller, sau đó ánh xạ identity đã xác minh sang policy.

mTLS bảo vệ kênh và chứng minh possession của private key tương ứng với certificate. Nó không tự quyết định caller được phép gọi API nào. Service vẫn cần authorization dựa trên identity, endpoint, resource và policy.

Không nên chấp nhận mọi certificate do một CA rộng phát hành. Trust configuration cần giới hạn CA, trust domain, SAN/URI identity, thời hạn, mục đích sử dụng và trạng thái thu hồi theo kiến trúc PKI.

### 5.2. SPIFFE và workload identity

Trong môi trường hỗ trợ SPIFFE, workload có thể nhận một SPIFFE ID và SVID để chứng minh danh tính trong trust domain. SPIFFE ID thường thể hiện một workload identity theo namespace/path đã được tổ chức quy định.

Service đích cần xác minh SVID theo trust bundle và policy, sau đó ánh xạ SPIFFE ID sang quyền cụ thể. Không coi mọi workload trong cùng cluster hoặc cùng trust domain đều được quyền gọi mọi service.

### 5.3. Tránh static shared secret

Một API key tĩnh được chia sẻ giữa nhiều service làm mất khả năng phân biệt caller và khó thu hồi có mục tiêu. Nếu một workload bị xâm nhập, attacker có thể dùng cùng key để giả danh các service khác.

Ưu tiên workload identity có credential ngắn hạn, cấp phát tự động và rotation. Nếu phải dùng secret, mỗi workload cần secret riêng, scope hẹp, lưu trong secret manager, có owner, rotation và quy trình revoke.

## 6. OAuth access token và audience

OAuth access token được phát hành để resource server cụ thể chấp nhận theo policy. Claim `aud` hoặc cơ chế audience tương đương giúp giới hạn token cho đúng resource/API.

Ví dụ:

- Token A: `aud = orders-api`, scope `orders.read`.
- Token B: `aud = payments-api`, scope `payments.create`.

Không nên gửi Token A tới Payments API chỉ vì hai API cùng thuộc một hệ thống. Payments API phải từ chối token không dành cho nó, kể cả chữ ký token hợp lệ.

Với JWT access token, resource server cần xác minh chữ ký, issuer, audience, thời hạn, token type và claim theo profile đã thỏa thuận. Với opaque token, resource server có thể dùng introspection hoặc cơ chế kiểm tra trạng thái tương đương.

Không dùng OIDC ID Token làm access token cho API. ID Token mang thông tin xác thực dành cho client; access token mang quyền truy cập resource theo OAuth.

## 7. Token exchange và actor chain

OAuth 2.0 Token Exchange (RFC 8693) định nghĩa cách client đổi một security token lấy token khác theo yêu cầu resource, audience hoặc phạm vi. Cơ chế này hữu ích khi một chuỗi service cần token riêng cho từng downstream API.

Một luồng khái niệm:

1. Web Portal xác thực người dùng và nhận token phù hợp cho API đầu tiên.
2. Order Service xác minh token và workload caller.
3. Order Service yêu cầu authorization server đổi subject token sang token dành cho Payment API.
4. Authorization server kiểm tra quyền delegation, caller, resource/audience yêu cầu, scope và policy.
5. Order Service gọi Payment API bằng token mới.
6. Payment API xác minh token, subject, actor và quyền trên giao dịch cụ thể.

Trong mô hình token exchange, `sub` thường biểu diễn subject, còn claim actor như `act` có thể thể hiện actor hiện tại theo profile. Cấu trúc chính xác phụ thuộc chuẩn và authorization server; không tự suy diễn ý nghĩa claim ngoài profile đã thống nhất.

### 7.1. Token exchange không phải quyền nâng cấp

Token exchange không được dùng để biến một token ít quyền thành token mạnh hơn chỉ vì service trung gian yêu cầu. Authorization server phải kiểm tra policy delegation và không phát hành quyền vượt quá quyền subject được phép ủy quyền, quyền actor có thể thực hiện và policy resource.

Token mới thường cần scope được thu hẹp, audience cụ thể và thời hạn phù hợp. Nếu yêu cầu không hợp lệ, server phải từ chối thay vì tự động phát token mặc định rộng.

### 7.2. Chọn token exchange thay vì relay token

Relay nguyên bearer token có thể phù hợp trong một số kiến trúc đơn giản nếu audience, scope, trust boundary và resource server được thiết kế cho việc đó. Tuy nhiên, khi token ban đầu dành cho service A, việc chuyển tiếp sang B dễ gây confused deputy hoặc token leakage.

Token exchange hữu ích khi:

- Downstream API có audience riêng.
- Mỗi service cần scope khác nhau.
- Cần ghi nhận actor chain hoặc delegation.
- Cần giảm quyền khi đi sâu vào hệ thống.
- Cần tách quyền workload khỏi quyền người dùng.

Không exchange token một cách mù quáng ở mọi hop. Mỗi lần exchange làm tăng độ phức tạp và phụ thuộc authorization server; chỉ dùng khi nó giải quyết rõ ranh giới tin cậy hoặc policy.

## 8. Không tin identity header do client tự gửi

Các header như `X-User-Id`, `X-Role`, `X-Tenant-Id`, `X-Authenticated-User` hoặc `X-Forwarded-User` có thể bị client giả mạo nếu service tin trực tiếp.

Nếu kiến trúc sử dụng identity header nội bộ:

1. Edge/gateway phải xóa header identity do client gửi từ bên ngoài.
2. Gateway xác minh token hoặc certificate theo policy.
3. Gateway tạo lại identity context từ dữ liệu đã xác minh.
4. Kênh gateway-to-service phải được bảo vệ, ví dụ mTLS hoặc network identity riêng.
5. Service đích chỉ tin context đến từ gateway được xác thực và đúng trust domain.
6. Context phải có integrity protection hoặc ràng buộc với kênh tin cậy, có thời hạn và chống replay phù hợp.

Một header chỉ là dữ liệu văn bản. TLS giữa các service bảo vệ kênh nhưng không tự làm cho header do bất kỳ upstream nào gửi trở thành đáng tin. Cần xác thực caller và giới hạn service nào có quyền tạo context.

Không cho phép service trung gian tùy ý thay `sub`, `tenant` hoặc `roles` trong identity context. Thay đổi subject/actor phải được authorization server hoặc trust broker có thẩm quyền xác nhận.

## 9. Propagation qua nhiều service

Mỗi service trong chuỗi cần xác định:

- Caller trực tiếp là workload nào?
- Subject ban đầu là ai, nếu request có user context?
- Actor hiện tại là service nào?
- Token dành cho resource nào?
- Scope và quyền có được thu hẹp đúng mức không?
- Tenant/resource ID có được kiểm tra với dữ liệu đích không?
- Request có thuộc delegation chain còn hợp lệ không?

~~~mermaid
sequenceDiagram
    participant U as User
    participant W as Web Portal
    participant O as Order Service
    participant Z as Authorization Server
    participant P as Payment API
    U->>W: Yêu cầu tạo thanh toán
    W->>O: Token dành cho Orders API
    O->>O: Xác minh user context và workload caller
    O->>Z: Token exchange: subject token + audience Payments
    Z->>Z: Kiểm tra delegation, actor, scope và policy
    Z-->>O: Access token dành cho Payments API
    O->>P: Request + token mới
    P->>P: Xác minh issuer, audience, actor, subject và scope
    P->>P: Kiểm tra tenant, ownership và transaction policy
    P-->>O: Kết quả
    O-->>W: Kết quả nghiệp vụ
    W-->>U: Phản hồi
~~~

Nếu Order Service gọi thêm Inventory Service, nó cần xác định Inventory có cần biết user subject hay chỉ cần workload identity của Order Service. Không truyền toàn bộ claim và quyền người dùng tới mọi service chỉ vì dữ liệu đang có sẵn.

## 10. Propagation trong message queue và tác vụ bất đồng bộ

Không phải mọi lời gọi đều diễn ra đồng bộ qua HTTP. Một service có thể gửi message vào queue và worker xử lý sau vài giây hoặc vài giờ.

Message có thể cần giữ:

- Event ID và correlation ID.
- Principal/subject ID ở dạng định danh nội bộ nếu cần truy vết nghiệp vụ.
- Tenant ID đã được xác minh.
- Workload producer identity hoặc nguồn phát message được broker xác thực.
- Actor/service đã khởi tạo hành động.
- Resource/action và policy context tối thiểu cần thiết.
- Thời điểm tạo, thời hạn hoặc version của quyền nếu policy yêu cầu.

Không nên đặt bearer access token, refresh token, password hoặc session cookie vào message body để worker dùng lại lâu dài. Token có thể hết hạn, bị lộ qua queue retention hoặc được replay bởi consumer khác.

Có hai mô hình phổ biến:

1. **Service-owned job:** worker chạy bằng workload identity riêng, chỉ thực hiện nhiệm vụ hệ thống đã được cấp. Message giữ subject reference để audit, nhưng worker không giả danh người dùng.
2. **Delegated user action:** nếu worker cần tiếp tục hành động thay mặt user, hệ thống phải có cơ chế delegation/job authorization rõ ràng, token ngắn hạn hoặc capability có scope, expiry, audience và one-time/idempotent semantics phù hợp.

Worker cần xác minh producer/message integrity, tenant, event schema và authorization ở thời điểm xử lý. Không mặc định quyền tại thời điểm enqueue vẫn còn hiệu lực khi job chạy; với hành động nhạy cảm, cần kiểm tra lại trạng thái account, grant và resource.

## 11. Giới hạn quyền và ngăn confused deputy

**Confused deputy** xảy ra khi một service có quyền rộng bị lừa sử dụng quyền của chính nó để thực hiện hành động mà caller không được phép. Ví dụ, Report Service có thể đọc mọi tenant, nhưng người dùng chỉ được xem báo cáo tenant của mình. Nếu service nhận `tenantId` từ request mà không kiểm tra subject và quyền, attacker có thể yêu cầu service đọc tenant khác.

Biện pháp:

- Kiểm tra quyền của workload caller và quyền delegated subject riêng biệt.
- Ràng buộc tenant/resource với danh tính đã xác minh, không chỉ lấy từ request body.
- Giới hạn audience và scope cho từng downstream API.
- Không dùng service credential quyền rộng để bỏ qua authorization nghiệp vụ.
- Kiểm tra ownership và trạng thái resource tại service đích.
- Tránh cho caller tự chọn subject hoặc actor tùy ý.
- Dùng policy explicit cho delegation và ghi audit chain.

Một service có thể có quyền kỹ thuật đọc dữ liệu để thực thi nghiệp vụ, nhưng phải giới hạn dữ liệu mà nó đọc dựa trên context và policy của request.

## 12. Authorization tại mỗi trust boundary

Mỗi service nhận request cần thực hiện kiểm tra tối thiểu:

1. Xác thực kênh/caller workload.
2. Xác minh access token hoặc assertion theo issuer và profile đã cấu hình.
3. Kiểm tra audience dành cho chính service/resource.
4. Kiểm tra expiry, not-before, token type và trạng thái thu hồi nếu có.
5. Kiểm tra subject, actor, tenant và delegation chain.
6. Kiểm tra scope/role/permission phù hợp với endpoint.
7. Kiểm tra ownership, relationship và trạng thái tài nguyên.
8. Áp dụng policy bổ sung như step-up, transaction limit hoặc separation of duties.

Không dựa vào network location như bằng chứng duy nhất. Một service nằm trong private subnet hoặc cùng cluster vẫn có thể bị xâm nhập; zero-trust principle yêu cầu xác thực và authorization tại ranh giới phù hợp.

### 12.1. Tenant isolation

Tenant ID cần được ràng buộc với principal và resource. Nếu token chứa tenant claim, service vẫn phải kiểm tra resource thuộc tenant đó. Không tin `tenantId` do client gửi hoặc header chưa được xác minh.

Nếu workload được phép xử lý nhiều tenant, scope cần giới hạn rõ và audit phải ghi tenant thực tế của từng hành động. Không dùng một service identity đa tenant có quyền toàn cục nếu workload có thể được chia thành identity hẹp hơn.

## 13. Token binding và bảo vệ kênh

Bearer token có thể được sử dụng bởi bất kỳ ai sở hữu token trong thời hạn hiệu lực. Nếu token bị log, lộ qua proxy hoặc lấy từ memory, attacker có thể replay.

Các biện pháp giảm rủi ro:

- Dùng TLS cho mọi hop; xác thực server và bảo vệ certificate chain.
- Dùng mTLS khi cần xác thực workload hai chiều và binding với client certificate.
- Cân nhắc sender-constrained token như mTLS-bound token hoặc DPoP theo khả năng của authorization server/resource server.
- Giữ access token ngắn hạn và audience hẹp.
- Không log token hoặc đặt token trong URL.
- Bảo vệ secret/key bằng KMS, HSM hoặc secret manager.
- Rotation và revoke credential khi workload bị xâm nhập hoặc ngừng hoạt động.

mTLS bảo vệ kênh và có thể ràng buộc token với certificate theo profile hỗ trợ; chỉ bật TLS không tự làm bearer token trở thành sender-constrained. DPoP cũng cần verifier kiểm tra proof và binding đúng chuẩn, không chỉ nhìn thấy header DPoP là tin.

## 14. Token claims và identity context

Một access token JWT minh họa có thể chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "payments-api",
  "azp": "order-service-client",
  "scope": "payments.create",
  "tenant_id": "tenant-a",
  "act": {
    "sub": "spiffe://example.test/ns/prod/sa/order-service"
  },
  "iat": 1795341600,
  "exp": 1795341900
}
~~~

Đây là ví dụ khái niệm; claim và cấu trúc actor phụ thuộc token profile, issuer và thỏa thuận giữa các service. Không tự thêm claim `act` hoặc `tenant_id` rồi mặc định mọi resource server hiểu cùng ngữ nghĩa.

Các trường thường cần quan tâm:

- `iss`: issuer phát hành token.
- `sub`: subject theo định nghĩa của issuer/profile.
- `aud`: resource server hoặc audience được phép nhận token.
- `scope`/roles: quyền được cấp theo profile.
- `act`: actor context nếu profile hỗ trợ.
- `azp` hoặc client identifier: client được ủy quyền theo profile.
- `iat`, `nbf`, `exp`: thời điểm phát hành, bắt đầu hiệu lực và hết hạn.
- `cnf`: confirmation/binding claim nếu token được ràng buộc với key/certificate.
- Tenant/resource claims: chỉ dùng khi được issuer xác minh và policy định nghĩa rõ.

Không lấy `email`, `name` hoặc display name làm principal key ổn định. Với federation, cần dùng định danh issuer/subject theo quy tắc liên kết tài khoản đã xác minh.

## 15. Audit và observability qua chuỗi service

Để điều tra một hành động, hệ thống cần nối được các log mà không biến trace metadata thành bằng chứng danh tính.

Nên ghi:

- Request ID/correlation ID và trace ID.
- Caller workload identity đã xác minh.
- Subject/tenant nếu policy và quyền riêng tư cho phép.
- Actor chain hoặc delegation reference.
- Audience, scope và token/client reference ở dạng không nhạy cảm.
- Resource/action và authorization decision.
- Thời điểm, service version và kết quả downstream.

Không ghi access token, refresh token, session cookie, private key hoặc secret. Nếu cần tham chiếu token, dùng token ID/JTI hoặc hash đã được thiết kế phù hợp, không ghi bearer value.

Trace context như `traceparent` giúp nối request qua service nhưng có thể do caller bên ngoài cung cấp. Gateway có thể tạo hoặc kiểm tra trace context theo policy; không dùng trace ID để suy ra user identity hoặc quyền.

## 16. Ví dụ pseudocode xác minh propagation context

Đoạn mã khái niệm ở resource service:

~~~ts
async function authorizePaymentRequest(request) {
  const workload = await authenticateWorkload(request.tlsPeer);
  const token = await verifyAccessToken(request.authorizationHeader, {
    expectedIssuer: "https://identity.example.test",
    expectedAudience: "payments-api"
  });

  const subject = token.subject;
  const actor = token.actor;
  const tenantId = token.tenantId;

  if (!subject || !actor || !tenantId) {
    throw new UnauthorizedError();
  }

  if (!policy.isAllowedActor(workload, actor)) {
    throw new ForbiddenError();
  }

  if (!token.scopes.includes("payments.create")) {
    throw new ForbiddenError();
  }

  const payment = await payments.load(request.paymentId);
  if (payment.tenantId !== tenantId) {
    throw new ForbiddenError();
  }

  await policy.assertCanCreatePayment({
    subject,
    actor,
    tenantId,
    payment
  });

  return payments.createAuthorized(request, payment);
}
~~~

Đây là pseudocode, không phải verifier production. `verifyAccessToken` phải kiểm tra chữ ký hoặc introspection, issuer, audience, expiry, not-before, token type và binding theo profile. `authenticateWorkload` phải xác minh mTLS/SVID hoặc cơ chế workload identity đã chọn. Không tin các trường subject, actor, tenantId nếu chúng chỉ được lấy từ header do client tự gửi.

## 17. Ví dụ: Order Service gọi Payment Service thay mặt nhân viên

Một nhân viên trong tenant A tạo yêu cầu thanh toán:

1. Người dùng đăng nhập bằng passkey vào Web Portal.
2. Web Portal nhận token phù hợp với Orders API và gửi request tạo order.
3. Order Service xác minh token, workload caller, subject, tenant và quyền tạo order.
4. Order Service cần gọi Payment Service; nó yêu cầu authorization server token exchange với subject token đã xác minh, actor identity của Order Service, audience `payments-api` và scope `payments.create`.
5. Authorization server kiểm tra policy delegation, client/workload, subject, tenant, audience và scope. Nếu hợp lệ, nó cấp token ngắn hạn cho Payments API.
6. Order Service gọi Payment Service qua mTLS và gửi token mới.
7. Payment Service xác minh issuer, audience, token binding, actor và subject; sau đó kiểm tra tenant, ownership, trạng thái giao dịch, hạn mức và quyền phê duyệt.
8. Payment Service ghi audit event thể hiện subject là nhân viên, actor là Order Service và resource là giao dịch thuộc tenant A.
9. Kết quả quay lại Order Service và Web Portal.

Nếu Order Service dùng một client credential có quyền tạo mọi khoản thanh toán, nó có thể trở thành confused deputy. Authorization server và Payment Service cần giới hạn delegation theo user context và policy nghiệp vụ.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ truyền `X-User-Id` | Caller có thể giả mạo subject. | Dùng token/assertion đã xác minh hoặc trusted identity context có integrity. |
| Relay cùng bearer token qua mọi API | Token có thể bị dùng sai audience hoặc lộ ở nhiều trust boundary. | Dùng token audience-specific hoặc token exchange khi phù hợp. |
| Chỉ kiểm tra user subject, bỏ qua workload actor | Service lạ có thể giả danh một luồng hợp lệ. | Xác thực workload và kiểm tra actor/delegation. |
| Chỉ kiểm tra service identity, bỏ qua user context | Service quyền rộng có thể truy cập dữ liệu thay người dùng không đủ quyền. | Kiểm tra cả workload permission và delegated subject authorization. |
| Token audience quá rộng | Một token bị lộ có thể truy cập nhiều API. | Audience hẹp, scope tối thiểu và TTL ngắn. |
| Tin mọi service trong private network | Workload bị xâm nhập có thể gọi ngang hàng. | mTLS/workload identity và authorization tại từng boundary. |
| Chấp nhận tenant ID từ request body | Cross-tenant data access. | Ràng buộc tenant với token/identity đã xác minh và resource. |
| Dùng ID Token để gọi API | Sai loại token và audience. | Dùng access token dành cho resource server. |
| Gửi bearer token vào queue | Token bị lưu lâu, replay hoặc lộ qua consumer. | Dùng workload identity và job delegation/capability có scope, expiry. |
| Không kiểm tra token exchange policy | Service trung gian có thể nâng quyền. | Authorization server kiểm tra actor, subject, audience và quyền delegation. |
| Tin identity header từ upstream bất kỳ | Header giả mạo vượt trust boundary. | Gateway xóa header ngoài, xác minh caller và tạo context mới. |
| Ghi token vào trace/log | Bí mật truy cập bị lộ qua observability. | Redact secret, dùng token reference và audit metadata. |
| Không thu hồi workload credential cũ | Service đã ngừng vẫn có thể gọi API. | Lifecycle, rotation và revocation của workload identity. |
| Không re-check quyền ở worker bất đồng bộ | Job chạy bằng quyền đã hết hoặc đã bị thu hồi. | Kiểm tra lại policy/resource khi thực thi job nhạy cảm. |

## 19. Checklist thiết kế service identity propagation

Trước khi đưa chuỗi service vào production, hãy kiểm tra:

1. Mỗi service có workload identity riêng, owner và trust domain rõ ràng không?
2. Có phân biệt subject, actor, client, workload, tenant và resource không?
3. Service đích xác minh caller bằng token, mTLS/SVID hoặc assertion được tin cậy không?
4. Token có đúng issuer, audience, token type, thời hạn và binding không?
5. Có dùng access token thay cho ID Token khi gọi resource API không?
6. Nếu cần user context, delegation có được cấp theo policy và scope tối thiểu không?
7. Token exchange/OBO có kiểm tra actor, subject, audience, tenant và không nâng quyền không?
8. Mỗi downstream API có audience/scope riêng khi cần không?
9. Identity header do client gửi có bị xóa ở edge và tái tạo từ context đã xác minh không?
10. Service đích có tự kiểm tra tenant, ownership, role, scope và trạng thái resource không?
11. Queue/worker có tránh lưu bearer token lâu dài và có kiểm tra lại quyền khi thực thi không?
12. Credential workload có ngắn hạn, rotation, revoke và secret storage phù hợp không?
13. Có chống replay, confused deputy, cross-tenant access và token leakage không?
14. Audit có nối được actor chain với request/resource nhưng không ghi secret/token không?
15. Có kiểm thử token sai audience, actor không hợp lệ, tenant mismatch, revoked workload, expired token, forged header và retry không?

**Kết luận:** Service identity propagation giữ được danh tính workload, subject người dùng và actor trung gian khi request đi qua nhiều dịch vụ. Thiết kế an toàn phải xác thực từng caller, phân biệt subject với actor, giới hạn token theo audience/scope, dùng delegation hoặc token exchange có policy khi cần, và thực hiện authorization tại mỗi resource boundary. Không coi header, trace context hay private network là bằng chứng danh tính. Với tác vụ bất đồng bộ, chỉ truyền ngữ cảnh tối thiểu và kiểm tra lại quyền khi worker thực thi.
