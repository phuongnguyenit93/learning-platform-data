# Service-to-service auth

> **Chương:** Case study  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Tình huống:** Thiết kế xác thực giữa Order Service, Inventory Service và Payment Service trong một nền tảng thương mại điện tử.

## 1. Bối cảnh

Một nền tảng thương mại điện tử tách chức năng thành nhiều service. Order Service tiếp nhận đơn hàng, Inventory Service kiểm tra và giữ hàng, Payment Service tạo yêu cầu thanh toán. Các service chạy ở nhiều instance, có thể được triển khai ở nhiều region và giao tiếp qua network nội bộ.

Khi khách hàng đặt hàng, Order Service cần gọi Inventory Service để giữ hàng và gọi Payment Service để khởi tạo thanh toán. Hai service đích phải biết request đến từ workload nào, request có được gửi qua kênh tin cậy không và workload đó có được phép thực hiện hành động cụ thể hay không.

Một thiết kế ban đầu dùng chung một API key trong biến môi trường của cả ba service. Cách làm này đơn giản nhưng tạo ra một vùng tin cậy quá rộng: nếu một container bị chiếm hoặc log vô tình làm lộ key, attacker có thể giả làm nhiều service. Key không cho biết caller cụ thể, không có audience rõ ràng, khó giới hạn scope và việc thu hồi có thể ảnh hưởng toàn bộ hệ thống.

Nhóm kỹ thuật quyết định chuyển sang workload identity, access token ngắn hạn có audience và scope cụ thể, cùng mTLS giữa các service. Hệ thống cũng cần phân biệt service identity với danh tính người dùng để tránh biến một request hợp lệ từ Order Service thành quyền truy cập không giới hạn thay mặt khách hàng.

Đây là case study thiết kế, triển khai và kiểm thử service-to-service authentication trong module SECURITY_AUTHENTICATION_FUNDAMENTALS. Mục tiêu là mô hình hóa ranh giới tin cậy, xác minh credential, giới hạn quyền, phòng chống replay và chuẩn bị vòng đời thu hồi.

### Kết quả học tập

Sau case study, người học có thể:

- Xác định workload principal và trust boundary trong kiến trúc nhiều service.
- Chọn cơ chế cấp và xác minh workload credential.
- Kết hợp OAuth 2.0 Client Credentials với mTLS hoặc client authentication mạnh.
- Ràng buộc token với issuer, audience, scope và thời hạn.
- Phân biệt service identity với user delegation.
- Thiết kế least privilege và authorization ở service đích.
- Xử lý rotation, revocation, outage và replay.
- Xây test matrix, observability và kế hoạch rollout có kiểm soát.

## 2. Kiến trúc hiện tại và vấn đề

Luồng nghiệp vụ hiện tại:

1. Browser gửi yêu cầu đặt hàng tới API Gateway.
2. Gateway xác thực người dùng và chuyển request tới Order Service.
3. Order Service gọi Inventory Service để giữ hàng.
4. Order Service gọi Payment Service để tạo payment intent.
5. Các service trả kết quả về Order Service, sau đó Order Service phản hồi cho gateway.

### Sơ đồ hệ thống

~~~mermaid
flowchart LR
    U["Customer browser"] --> G["API Gateway"]
    G --> O["Order Service"]
    O --> I["Inventory Service"]
    O --> P["Payment Service"]
    I --> DBI[("Inventory DB")]
    P --> DBP[("Payment DB")]
    O --> DBO[("Order DB")]
~~~

### Các vấn đề của API key dùng chung

- Không xác định được service nào thực sự gọi khi mọi workload dùng cùng một secret.
- Một key bị lộ có thể mở đường truy cập tới nhiều API.
- Khó giới hạn key theo audience, action hoặc thời hạn.
- Rotation đòi hỏi phối hợp nhiều workload và dễ để key cũ tồn tại lâu.
- Không có bằng chứng mật mã gắn request với workload cụ thể nếu key chỉ được gửi như bearer secret.
- Key có thể bị copy vào image, build log, environment dump hoặc ticket.
- Service đích có thể nhầm authentication thành authorization và cho phép mọi caller có key thực hiện hành động rộng.

API key không phải lúc nào cũng sai. Nó có thể phù hợp với một số API integration có scope hẹp, vòng đời rõ và cơ chế bảo vệ tốt. Nhưng một secret dùng chung cho nhiều workload nội bộ không tạo ra danh tính riêng và không đáp ứng yêu cầu cô lập của kiến trúc này.

## 3. Yêu cầu bảo mật và nghiệp vụ

Nhóm thống nhất các yêu cầu trước khi chọn công nghệ.

### Yêu cầu xác thực

- Mỗi workload có một principal riêng, ví dụ order-service, inventory-service và payment-service.
- Service đích xác minh danh tính caller từ credential do issuer được tin cậy cấp.
- Credential có lifetime ngắn và được cấp tự động cho workload hợp lệ.
- Token chỉ dùng được cho đúng audience và API.
- Kênh kết nối được bảo vệ bằng TLS; mTLS được dùng khi cần xác minh peer ở tầng transport.
- Không có shared static secret giữa các service.

### Yêu cầu authorization

- Order Service được gọi endpoint giữ hàng của Inventory Service.
- Order Service được tạo payment intent trong Payment Service.
- Order Service không được đọc dữ liệu thẻ hoặc gọi endpoint hoàn tiền quản trị.
- Inventory Service không được tạo payment.
- Payment Service không được giả làm Order Service để gọi API quản trị đơn hàng.
- Mỗi service tự kiểm tra quyền và trạng thái nghiệp vụ tại ranh giới của mình.

### Yêu cầu vận hành

- Có thể rotate và revoke workload credential mà không cần rebuild toàn bộ image.
- Có audit và metric theo workload principal.
- Có runbook khi token issuer, certificate authority hoặc KMS/HSM gặp sự cố.
- Có kiểm thử multi-instance, multi-region và cache propagation.
- Không ghi private key, client secret hoặc raw bearer token vào log.

## 4. Xác định workload identity

**Workload identity** là danh tính được cấp cho một ứng dụng hoặc workload đang chạy, chẳng hạn service, job, container, VM hoặc function. Nó trả lời câu hỏi: workload nào đang giao tiếp?

Ví dụ:

| Workload | Principal minh họa | Trách nhiệm |
|---|---|---|
| Order Service | spiffe://shop.example/ns/prod/sa/order | Điều phối đơn hàng |
| Inventory Service | spiffe://shop.example/ns/prod/sa/inventory | Giữ và giải phóng hàng |
| Payment Service | spiffe://shop.example/ns/prod/sa/payment | Tạo và quản lý payment intent |
| Fulfillment Worker | spiffe://shop.example/ns/prod/sa/fulfillment | Xử lý giao hàng |

Principal cần ổn định theo workload identity contract, không dựa vào hostname, IP hoặc tên pod có thể thay đổi sau mỗi lần deploy.

### Nguồn cấp danh tính

Có thể dùng:

- Cloud workload identity của nhà cung cấp cloud.
- Kubernetes service account được liên kết với identity provider.
- SPIFFE/SPIRE và SPIFFE Verifiable Identity Document (SVID).
- Certificate do internal CA cấp cho workload.
- OAuth 2.0 authorization server cấp access token sau khi xác minh workload.

Chọn một nguồn có authority rõ ràng, quy trình enrollment, owner, rotation và revocation. Không cho workload tự khai báo tên principal trong header rồi tin giá trị đó.

## 5. Chọn mô hình xác thực

Có nhiều cách xác thực service-to-service. Không có một lựa chọn duy nhất phù hợp với mọi môi trường.

| Cơ chế | Cung cấp điều gì | Điểm cần lưu ý |
|---|---|---|
| OAuth 2.0 Client Credentials | Access token đại diện cho client/workload | Cần client authentication an toàn, audience và scope |
| private_key_jwt | Client chứng minh quyền sở hữu private key với authorization server | Key custody, assertion lifetime, jti/replay protection |
| mTLS client authentication | Client xác thực bằng certificate trong TLS handshake | CA trust, SAN mapping, rotation và revocation |
| SPIFFE/SPIRE SVID | Workload identity có thể xác minh qua certificate hoặc JWT SVID | Trust domain, attestation và bundle rotation |
| Cloud workload identity | Danh tính workload gắn với hạ tầng cloud | Cần cấu hình trust policy và audience đúng |
| Static API key | Shared secret để nhận diện caller theo key | Rotation, leakage, scope và attribution khó hơn |

### Quyết định cho case study

Nhóm chọn:

1. Workload identity từ nền tảng triển khai làm nguồn xác định principal.
2. OAuth 2.0 Client Credentials để xin access token cho API cụ thể.
3. Client authentication bằng mTLS hoặc private_key_jwt tùy khả năng của authorization server.
4. TLS/mTLS cho kết nối giữa service.
5. Resource server xác minh token và tự thực hiện authorization.

Trong môi trường đã có service mesh với SPIFFE identity và mTLS được quản lý tốt, workload SVID có thể là cơ sở xác thực peer. OAuth access token vẫn hữu ích khi cần scope, audience và authorization context ở tầng API. Không cần thêm nhiều lớp credential nếu chúng không tạo thêm kiểm soát có ý nghĩa.

## 6. Kiến trúc mục tiêu

Authorization Server cấp access token cho Order Service sau khi xác minh workload credential. Order Service gọi Inventory và Payment với token dành riêng cho từng audience. Mỗi resource server kiểm tra token và quyền.

~~~mermaid
flowchart TD
    W["Order Service workload"] -->|Workload identity| A["Identity / Authorization Server"]
    A -->|Short-lived token: aud=inventory-api| OI["Order Service"]
    OI -->|mTLS + inventory token| I["Inventory API"]
    A -->|Short-lived token: aud=payment-api| OP["Order Service"]
    OP -->|mTLS + payment token| P["Payment API"]
    I -->|Verify identity, token, scope| DI["Inventory policy"]
    P -->|Verify identity, token, scope| DP["Payment policy"]
    DI --> RI["Hold inventory"]
    DP --> RP["Create payment intent"]
~~~

Sơ đồ mô tả khái niệm. Trong triển khai thực tế, token acquisition thường diễn ra qua một token client/library hoặc sidecar; service không nhất thiết gọi authorization server ở mọi request. Token cache phải tôn trọng expiry, audience và rotation policy.

### Trust boundary

- Workload runtime: nơi workload được attestation và credential được cấp.
- Authorization Server: nơi xác minh client và phát token.
- Network/TLS boundary: nơi xác minh peer và bảo vệ dữ liệu trên đường truyền.
- Resource Server: nơi xác minh token và quyết định quyền.
- Business data boundary: nơi kiểm tra tenant, resource ownership và trạng thái nghiệp vụ.

Một workload được xác thực thành công ở TLS layer chưa tự động có quyền trên mọi endpoint. Tương tự, token hợp lệ không chứng minh request có dữ liệu nghiệp vụ hợp lệ.

## 7. Token contract cho từng service

Token phải được phát hành cho resource cụ thể. Không dùng một token audience rộng cho mọi API chỉ để giảm số lần lấy token.

### Ví dụ token claims

Token minh họa cho Order Service gọi Inventory API:

~~~json
{
  "iss": "https://identity.shop.example",
  "sub": "spiffe://shop.example/ns/prod/sa/order",
  "aud": "inventory-api",
  "iat": 1795341600,
  "nbf": 1795341600,
  "exp": 1795341900,
  "jti": "tok-7f31",
  "scope": "inventory.hold inventory.release",
  "client_id": "order-service"
}
~~~

Các giá trị là ví dụ. Profile token thực tế phải tuân theo authorization server và API contract. Nếu dùng JWT access token, resource server phải xác minh chữ ký và claim; không tin payload chỉ vì có thể decode.

### Audience

- Token cho Inventory API có audience inventory-api.
- Token cho Payment API có audience payment-api.
- Inventory API từ chối token chỉ dành cho Payment API.
- Không dùng audience wildcard nếu không có threat model và kiểm soát chặt.

### Scope

Scope nên thể hiện hành động cần thiết:

- inventory.hold
- inventory.release
- payment.intent.create

Không cấp scope payment.refund hoặc payment.admin cho Order Service nếu nghiệp vụ không cần. Resource server vẫn kiểm tra trạng thái đơn hàng và giới hạn giao dịch sau khi scope hợp lệ.

### Lifetime và claims

- Access token có lifetime ngắn theo threat model.
- Không đưa password, private key hoặc dữ liệu cá nhân không cần thiết vào token.
- sub xác định workload principal theo contract.
- iss và aud phải được xác minh chính xác.
- exp, nbf và iat phải được kiểm tra với clock tolerance nhỏ, có kiểm soát.
- jti có thể hỗ trợ correlation/revocation/replay controls, nhưng tự nó không ngăn replay nếu server không duy trì trạng thái hoặc có sender constraint.

## 8. Luồng cấp token bằng Client Credentials

Order Service cần token cho Inventory API.

1. Workload được runtime xác minh và nhận credential riêng.
2. Token client kết nối authorization server qua TLS/mTLS.
3. Client chứng minh danh tính bằng mTLS hoặc private_key_jwt.
4. Authorization server kiểm tra client, trạng thái, scope được cấp và audience.
5. Authorization server phát access token ngắn hạn.
6. Token client cache token theo issuer, client, audience và scope.
7. Khi token sắp hết hạn, client lấy token mới theo policy.
8. Khi credential bị revoke hoặc client bị disable, authorization server từ chối lần cấp token tiếp theo.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant AS as Authorization Server
    participant I as Inventory API
    O->>AS: Client authentication + token request
    AS->>AS: Verify workload identity and allowed scope
    AS-->>O: Access token aud=inventory-api
    O->>I: Request + Bearer token over TLS/mTLS
    I->>I: Verify signature, iss, aud, exp, scope
    I->>I: Check inventory policy and order context
    I-->>O: Hold result
~~~

### Không có user context trong Client Credentials

Client Credentials đại diện cho workload, không đại diện cho người dùng cuối. Nếu request được khởi tạo bởi khách hàng, service có thể ghi nhận actor và correlation trong business context, nhưng không được giả vờ rằng access token Client Credentials là user token.

Nếu Payment API cần biết người dùng nào đã khởi tạo thao tác, phải dùng cơ chế delegation/on-behalf-of được thiết kế riêng, hoặc chuyển thông tin actor có chữ ký và provenance được xác minh. Không tin header X-User-Id do caller tự gửi.

## 9. Khi nào dùng private_key_jwt và khi nào dùng mTLS?

### private_key_jwt

Client tạo JWT assertion và ký bằng private key để chứng minh danh tính với token endpoint. Authorization server xác minh chữ ký bằng public key đã đăng ký.

Các kiểm soát:

- Assertion có issuer/subject/audience đúng theo profile.
- Thời hạn assertion ngắn.
- jti duy nhất và replay cache nếu profile yêu cầu.
- Key được bảo vệ trong KMS/HSM hoặc workload keystore phù hợp.
- Rotation có overlap và quy trình thu hồi.
- Không ghi assertion hoặc private key vào log.

### mTLS

Client trình certificate trong TLS handshake. Server xác minh chain và ánh xạ certificate identity sang workload principal. Nếu dùng OAuth mTLS client authentication hoặc certificate-bound access token, tuân thủ profile tương ứng.

Các kiểm soát:

- CA/trust bundle chỉ gồm issuer được phép.
- SAN/URI identity được kiểm tra chính xác.
- Certificate có EKU/key usage phù hợp.
- Validity và revocation được kiểm tra theo policy.
- Private key không rời khỏi môi trường bảo vệ.
- Proxy/gateway không làm mất hoặc giả mạo client identity.

### Quyết định thực tế

Chọn theo hạ tầng và threat model. mTLS xác thực peer ở tầng kết nối và có thể bảo vệ token khỏi bị dùng từ một client không sở hữu certificate nếu token được ràng buộc đúng cách. private_key_jwt chứng minh client với token endpoint nhưng access token trả về vẫn có thể là bearer token nếu không có sender constraint. Hai cơ chế có thể bổ sung nhau, nhưng phải tính chi phí vận hành certificate và key.

## 10. Xác minh ở Resource Server

Inventory API và Payment API không được tin request chỉ vì nó đến từ network nội bộ. Mọi request phải qua xác minh ở service đích.

### Kiểm tra token

- Chỉ chấp nhận issuer được cấu hình.
- Xác minh chữ ký bằng key tin cậy và thuật toán allowlist.
- Kiểm tra audience đúng API hiện tại.
- Kiểm tra exp, nbf và clock tolerance.
- Kiểm tra scope/permission cần thiết.
- Kiểm tra client/workload identity theo contract.
- Kiểm tra token bị revoke hoặc key bị từ chối nếu kiến trúc hỗ trợ.
- Từ chối token malformed hoặc claim thiếu.

### Kiểm tra transport

- TLS được bật và certificate chain hợp lệ.
- Với mTLS, peer certificate được ánh xạ sang principal đã đăng ký.
- Không tin forwarded certificate/header từ nguồn không đáng tin.
- Nếu TLS terminate ở gateway, backend chỉ tin identity context được gateway xác thực và chuyển qua kênh riêng có bảo vệ.

### Kiểm tra nghiệp vụ

Inventory API cần xác minh:

- Scope inventory.hold.
- Order reference tồn tại và thuộc tenant đúng.
- Số lượng giữ không vượt giới hạn.
- Trạng thái order cho phép giữ hàng.
- Idempotency key gắn với thao tác phù hợp.

Payment API cần xác minh:

- Scope payment.intent.create.
- Order hợp lệ và chưa bị hủy.
- Amount/currency lấy từ dữ liệu server đáng tin, không chỉ từ body do caller gửi.
- Idempotency và trạng thái payment được kiểm tra.
- Caller không thể gọi refund/admin endpoint bằng token create intent.

Authentication chỉ xác định caller; authorization và business validation quyết định hành động.

## 11. Service identity khác user identity

Một lỗi thiết kế phổ biến là chuyển user identifier từ gateway thành header rồi xem nó như danh tính đã xác thực.

### Hai loại principal

| Loại | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Workload principal | Service nào đang gọi? | order-service |
| User principal | Người dùng nào khởi tạo hoặc được đại diện? | customer-482 |

Order Service có thể được xác thực là order-service nhưng request được khởi tạo bởi customer-482. Hai thông tin có provenance và quyền khác nhau.

### Không tin header tự khai báo

Header như X-User, X-Role hoặc X-Tenant do client gửi có thể bị giả mạo nếu gateway không xóa và tái tạo từ nguồn đã xác minh. Backend cần:

- Chặn client tự gửi identity header đặc quyền.
- Gateway xóa header do client cung cấp trước khi thêm context tin cậy.
- Backend chỉ chấp nhận context từ gateway qua mTLS hoặc cơ chế xác minh tương đương.
- Gắn context với request/correlation và giữ provenance.
- Authorization service vẫn kiểm tra user permission và resource ownership.

## 12. Delegation và on-behalf-of

Nếu Payment Service cần biết user nào đã khởi tạo thanh toán, có hai hướng phổ biến:

1. Order Service gửi một user-delegated token được authorization server cấp cho đúng audience và scope.
2. Một cơ chế token exchange/on-behalf-of đổi token đầu vào thành token dành cho Payment API theo policy.

Không nên nhét user ID vào workload token rồi coi đó là delegation. Cần token hoặc assertion thể hiện rõ subject user, actor workload, audience, scope và chain of delegation theo profile đã chọn.

### Ví dụ ngữ nghĩa

- Subject: customer-482, người dùng được đại diện.
- Actor/client: order-service, workload thực hiện lời gọi.
- Audience: payment-api.
- Scope: payment.intent.create.
- Context: order reference và transaction context đã được xác minh.

Payment API kiểm tra cả quyền của user lẫn quyền của workload và policy giao dịch. User có quyền mua hàng không có nghĩa Order Service được phép gọi mọi API của Payment.

### Khi không cần delegation

Nếu nghiệp vụ chỉ cần service thực hiện một tác vụ nội bộ theo quyền của workload, Client Credentials là đủ. Không chuyển user token xuyên nhiều service chỉ vì thuận tiện; điều đó mở rộng phạm vi token và làm khó kiểm soát audience.

## 13. Threat model cho service-to-service auth

Threat model phải xét cả credential, transport, token, runtime và business authorization.

| Threat | Tác động | Control |
|---|---|---|
| Shared API key bị lộ | Giả mạo nhiều service | Workload identity riêng, revoke/rotate riêng |
| Token theft | Bearer token bị dùng lại | TLS, lifetime ngắn, sender constraint khi phù hợp |
| Token replay | Request bị gửi lại | Idempotency, nonce/request ID, replay detection |
| Audience confusion | Token của API A dùng ở API B | Audience validation bắt buộc |
| Scope overgrant | Service có quyền quá rộng | Least privilege, scope review |
| Workload impersonation | Pod/service giả làm workload khác | Runtime attestation, mTLS, identity binding |
| Header spoofing | Giả mạo user/role/tenant | Strip untrusted headers, trusted channel |
| SSRF to metadata/token endpoint | Lấy workload credential | Metadata endpoint protection, egress control |
| Private key extraction | Giả mạo client | KMS/HSM, workload isolation, key rotation |
| Compromised service | Lateral movement | Segmentation, per-service identity, narrow audience |
| Stale JWKS/cache | Key bị revoke vẫn được tin | Cache TTL, invalidation, emergency deny |
| Clock skew | Token bị chấp nhận sai thời điểm | Time sync, bounded leeway |
| Confused deputy | Service dùng quyền của mình sai mục đích | Audience/scope, delegation semantics, resource checks |

### Blast radius

Nếu Order Service bị chiếm, attacker có thể sử dụng quyền của Order Service. Mục tiêu là giới hạn thiệt hại ở inventory hold và payment intent trong phạm vi cần thiết, không cho phép đọc card data, refund hoặc quản trị Payment.

Một workload identity riêng cho mỗi service giúp revoke một principal mà không buộc thu hồi credential của mọi workload khác.

## 14. Token theft, replay và idempotency

Access token bearer có thể được sử dụng bởi bất kỳ bên nào sở hữu token. Vì vậy:

- Chỉ truyền token qua TLS.
- Không đặt token trong URL, query string hoặc log.
- Dùng lifetime ngắn theo risk.
- Không chia sẻ token giữa các audience.
- Cache token an toàn theo client/audience/scope.
- Hạn chế nơi token có thể xuất hiện trong crash dump hoặc tracing.

### Chống replay ở tầng nghiệp vụ

Với lệnh tạo payment intent hoặc giữ hàng, retry do network có thể gửi cùng thao tác nhiều lần. API nên dùng idempotency key hoặc business request ID:

~~~http
POST /v1/payment-intents
Authorization: Bearer <access-token>
Idempotency-Key: order-2026-00482-payment
Content-Type: application/json
~~~

Server lưu trạng thái idempotency theo principal, endpoint và request semantics. Một request lặp lại với cùng key và cùng nội dung có thể trả kết quả trước đó; cùng key nhưng nội dung khác phải bị từ chối.

Idempotency không xác thực caller và không thay thế token. Nó kiểm soát việc thực hiện lặp hành động nghiệp vụ.

### Nonce và request signing

Nếu protocol ký từng request, timestamp và nonce có thể giới hạn freshness/replay. Nonce store phải có thao tác claim nguyên tử trên cluster. Chỉ kiểm tra timestamp không đủ để bảo đảm request chỉ được dùng một lần.

## 15. Key, certificate và token lifecycle

Credential workload cần vòng đời được tự động hóa và quan sát được.

### Issuance

- Workload được xác minh từ runtime hoặc orchestrator.
- Identity provider cấp credential ngắn hạn.
- Owner và trust domain được xác định.
- Scope/audience được cấp theo policy.

### Rotation

- Tạo key/certificate mới trong vùng bảo vệ.
- Cập nhật public key/trust bundle hoặc workload credential.
- Cho phép overlap ngắn theo kế hoạch để tránh outage.
- Xác minh consumer đã chuyển sang credential mới.
- Thu hồi credential cũ.
- Theo dõi request dùng credential cũ sau deadline.

### Revocation

- Disable workload principal hoặc client.
- Revoke certificate/token/grant theo loại credential.
- Cập nhật deny policy ở verifier/gateway.
- Invalidate cache và xác nhận mọi region.
- Điều tra request đã thực hiện trong khoảng credential có thể bị lộ.

### Failure mode

Nếu authorization server không khả dụng, workload có thể tiếp tục dùng token đã phát hành đến expiry theo policy, nhưng không được tự tạo credential hoặc bỏ xác minh. Nếu token hết hạn mà không thể refresh, request cần fail theo policy an toàn và phát metric/alert.

## 16. Quản lý secret và private key

Private key của workload không nên được đặt trong source code, image hoặc file cấu hình dùng chung.

Các lựa chọn:

- KMS/HSM để ký hoặc giải mã mà không xuất private key.
- Workload identity federation để tránh long-lived client secret.
- Secret manager có access policy theo workload principal.
- Memory-backed credential delivery nếu nền tảng hỗ trợ.
- File permission và rotation nếu buộc phải dùng file key trong môi trường giới hạn.

### Những nơi cần kiểm tra

- Source repository và commit history.
- Container image layer.
- Build log và CI artifact.
- Environment variable dump.
- Crash dump và heap dump.
- Application log và distributed trace.
- Ticket/chat/document.
- Backup và snapshot.
- Local developer workstation.

Nếu key bị lộ, xóa file khỏi branch mới không làm key cũ an toàn. Phải revoke/rotate và đánh giá lịch sử truy cập.

## 17. Network boundary và service mesh

Network nội bộ không đồng nghĩa với network đáng tin. Một workload bị compromise có thể gửi request tới nhiều service nếu network policy quá rộng.

### Kiểm soát

- TLS cho mọi hop có dữ liệu xác thực hoặc nghiệp vụ nhạy cảm.
- mTLS giữa workload khi phù hợp.
- Network policy chỉ cho phép route cần thiết.
- Service mesh identity được xác minh ở proxy và application boundary theo thiết kế.
- Gateway không chuyển identity header do client tự gửi.
- Egress control hạn chế SSRF tới metadata endpoint hoặc token service không cần thiết.
- DNS/service discovery không phải bằng chứng identity.

### Service mesh không thay authorization

mTLS trong mesh có thể xác minh peer workload và mã hóa kết nối. Nhưng một certificate hợp lệ không tự chứng minh service được phép gọi endpoint refund. API vẫn cần kiểm tra audience/scope hoặc policy tương đương.

Nếu proxy terminate mTLS và gửi identity header tới application, backend phải chỉ tin header qua channel được bảo vệ từ proxy đã xác minh. Nếu client có thể kết nối trực tiếp vào backend, phải có kiểm soát ngăn bypass proxy.

## 18. Authorization policy tại service đích

Mỗi resource server thực thi policy cục bộ hoặc gọi policy engine tin cậy. Không dựa vào việc gateway đã kiểm tra một lần rồi bỏ qua ở service đích.

### Policy minh họa

| Caller | Resource | Action | Kết quả |
|---|---|---|---|
| order-service | inventory reservation | inventory.hold | Allow |
| order-service | inventory reservation | inventory.release | Allow theo order state |
| order-service | payment intent | payment.intent.create | Allow |
| order-service | card data | payment.card.read | Deny |
| inventory-service | payment intent | payment.intent.create | Deny |
| payment-service | order administration | order.admin.update | Deny |
| unknown workload | bất kỳ API protected | bất kỳ action | Deny |

### Business invariant

Ngay cả khi token có scope payment.intent.create, Payment API vẫn phải xác minh amount/currency/order state từ dữ liệu đáng tin. Caller không thể tự gửi amount thấp trong token context rồi yêu cầu charge amount khác trong body.

Policy cần kiểm tra:

- Workload principal.
- Audience và scope.
- User delegation nếu có.
- Tenant/resource ownership.
- Trạng thái nghiệp vụ.
- Idempotency và transaction limit.
- Risk/step-up requirement nếu action nhạy cảm.

## 19. Triển khai tham khảo

Ví dụ dưới đây là pseudocode, minh họa thứ tự xử lý. Không phải cấu hình có thể copy trực tiếp cho mọi framework.

### Token acquisition ở Order Service

~~~text
function getAccessToken(audience, scopes):
    cacheKey = (workloadPrincipal, audience, sorted(scopes))
    token = tokenCache.get(cacheKey)

    if token exists and token.expiresAt > now + refreshSkew:
        return token

    clientProof = workloadCredential.createClientProof(
        audience = authorizationServer,
        shortLifetime = true
    )

    response = authorizationServer.requestClientCredentials(
        clientAuthentication = clientProof,
        audience = audience,
        scopes = scopes
    )

    validateTokenResponse(response)
    tokenCache.store(cacheKey, response.accessToken, response.expiresAt)
    return response.accessToken
~~~

### Request tới Inventory API

~~~text
token = getAccessToken(
    audience = "inventory-api",
    scopes = ["inventory.hold"]
)

response = httpClient.post(
    url = inventoryService + "/v1/reservations",
    headers = {
        "Authorization": "Bearer " + token,
        "Idempotency-Key": orderReservationKey
    },
    body = reservationRequest,
    tls = verifiedTlsConfiguration
)
~~~

Token client cần xử lý timeout, retry và concurrent refresh an toàn. Không để nhiều thread cùng refresh token gây request storm. Không log token khi HTTP client ném exception.

### Middleware ở Inventory API

~~~text
function handleRequest(request):
    peer = verifyTlsPeerIfRequired(request.tlsSession)
    token = extractBearerToken(request)

    claims = verifyAccessToken(
        token,
        trustedIssuers = configuredIssuers,
        expectedAudience = "inventory-api",
        allowedAlgorithms = configuredAlgorithms,
        clockTolerance = boundedTolerance
    )

    requireScope(claims, "inventory.hold")
    requireWorkloadIdentity(claims.subject, "order-service")
    requireTenantAndOrderOwnership(request.body)
    requireValidOrderState(request.body.orderId)

    return createReservationIdempotently(request)
~~~

Thứ tự minh họa không thay thế threat review. Thư viện xác minh token phải được kiểm chứng; middleware cần xử lý exception theo fail-closed policy và không đưa claims nhạy cảm vào response.

## 20. Xử lý lỗi và tính sẵn sàng

Service-to-service auth cần xử lý lỗi có chủ đích vì một lỗi token có thể lan truyền thành outage của cả chuỗi request.

| Lỗi | Hành vi mong đợi |
|---|---|
| Token endpoint timeout | Retry có backoff/deadline; không tự bỏ auth |
| Client credential bị revoke | Không cấp token mới; alert owner |
| Access token hết hạn | Refresh theo policy; request cũ không được tự gia hạn quyền |
| Issuer/audience sai | Từ chối request và ghi reason code |
| JWKS refresh failure | Chỉ dùng key cache đã xác minh trong giới hạn policy |
| mTLS certificate hết hạn | Handshake thất bại; rotation/runbook xử lý |
| Revocation propagation chậm | Đánh dấu containment chưa toàn cục và theo dõi verifier |
| Session/user context thiếu | Không suy đoán danh tính người dùng |
| Resource server không khả dụng | Trả lỗi dependency phù hợp, không cấp quyền thay thế |
| Clock skew vượt tolerance | Từ chối theo policy, cảnh báo time service |

### Retry

- Dùng deadline tổng cho chuỗi request.
- Exponential backoff và jitter cho token acquisition.
- Không retry vô hạn lỗi 4xx do credential/policy.
- Với request nghiệp vụ, dùng idempotency key.
- Circuit breaker không được bỏ qua authentication.
- Không log bearer token hoặc client assertion trong error report.

### Availability và fail-safe

Nếu token issuer mất kết nối, token đã phát hành có thể tiếp tục được chấp nhận đến expiry theo policy và cache semantics. Khi token hết hạn, service phải từ chối nếu không thể xác minh credential mới. Không kéo dài token lifetime vô hạn để che outage.

## 21. Logging, audit và monitoring

Mỗi service cần quan sát được workload identity và quyết định authorization mà không ghi secret.

### Audit event nên có

- Timestamp UTC.
- Event ID và correlation ID.
- Caller principal reference.
- Target service/API.
- Audience và scope đã được kiểm tra ở mức cần thiết.
- Authentication outcome và authorization outcome.
- Reason group an toàn.
- Region/node/service version.
- Idempotency reference nếu cần điều tra.

Không ghi raw access token, private key, client assertion, certificate private material hoặc toàn bộ request body có dữ liệu nhạy cảm.

### Metric gợi ý

- Token issuance success/failure theo client class.
- Token endpoint latency và error rate.
- Service request auth success/denial.
- Invalid issuer/audience/signature count.
- mTLS handshake failure.
- Token expiry/refresh rate.
- Revocation propagation time.
- Request replay/idempotency conflict count.
- Workload principal chưa được nhận diện.

Metric label phải hữu hạn. Không đưa token ID, request ID hoặc workload instance ID thay đổi liên tục thành label có cardinality cao.

### Alert

- Workload principal mới hoặc không được phép xuất hiện.
- Token issuance tăng bất thường.
- Một client yêu cầu scope ngoài baseline.
- Nhiều audience mismatch.
- Certificate sắp hết hạn hoặc bị revoke nhưng vẫn có request.
- Request dùng credential cũ sau rotation deadline.
- Token endpoint hoặc JWKS refresh lỗi kéo dài.
- Một workload gọi API ngoài graph giao tiếp đã phê duyệt.

## 22. Kế hoạch rollout

Chuyển từ shared API key sang workload identity cần có giai đoạn chuyển đổi và kiểm chứng.

### Giai đoạn 1: Inventory

- Liệt kê service caller, API đích và luồng dữ liệu.
- Xác định key dùng chung ở đâu và ai sở hữu.
- Phân loại endpoint theo độ nhạy cảm.
- Xác định dependency, owner và traffic baseline.

### Giai đoạn 2: Identity foundation

- Thiết lập workload identity provider/attestation.
- Đăng ký principal cho từng workload.
- Thiết lập authorization server và client authentication.
- Cấu hình audience, scope và token lifetime.
- Thiết lập CA/trust bundle nếu dùng mTLS.

### Giai đoạn 3: Shadow validation

- Cấp token mới cho test/staging workload.
- Xác minh token và policy ở chế độ quan sát nếu kiến trúc hỗ trợ.
- So sánh quyết định mới với allowlist/traffic hợp lệ hiện tại.
- Phát hiện service chưa được đăng ký hoặc scope thiếu.
- Không log token trong shadow telemetry.

### Giai đoạn 4: Enforce theo service

- Bật enforcement ở một service đích trước.
- Chuyển một nhóm caller nhỏ.
- Kiểm tra deny, latency, dependency và rollback.
- Mở rộng từng service/region sau khi đạt tiêu chí.
- Giữ đường rollback có thời hạn và không duy trì shared key vô hạn.

### Giai đoạn 5: Revoke shared key

- Xác minh mọi caller đã chuyển.
- Thu hồi key cũ.
- Kiểm tra request dùng key cũ bị từ chối.
- Tìm key trong source, image, CI artifact và secret store.
- Ghi nhận hoàn tất và đóng exception chuyển đổi.

## 23. Test matrix

Kiểm thử trong môi trường được phép với workload principal, key, certificate và token giả lập.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Order Service có identity hợp lệ | Authorization Server cấp token đúng client |
| Client authentication sai | Không cấp token |
| Workload principal không được đăng ký | Bị từ chối |
| Token đúng issuer, audience, scope | Request được xét tiếp ở policy |
| Token có audience Payment gửi tới Inventory | Inventory từ chối |
| Token thiếu scope inventory.hold | 403/deny theo API contract |
| Token hết hạn | Bị từ chối |
| Token chưa đến nbf | Bị từ chối |
| Token chữ ký sai | Bị từ chối |
| Thuật toán không allowlist | Bị từ chối |
| Issuer không được tin cậy | Bị từ chối |
| Token bị sửa payload | Signature validation thất bại |
| Client assertion hết hạn hoặc replay | Token endpoint từ chối |
| mTLS certificate sai SAN/CA | Handshake hoặc identity mapping thất bại |
| Certificate bị revoke | Verifier áp dụng revoke policy |
| Private key bị rotate | Workload mới hoạt động; key cũ bị thu hồi đúng hạn |
| Token issuer unavailable | Không fail-open; retry/backoff và alert |
| JWKS cache stale | Áp dụng freshness policy, không tin key mới không xác minh |
| Token bị dùng từ workload khác khi sender constraint bật | Proof/peer mismatch bị từ chối |
| X-User-Id giả từ client | Gateway xóa hoặc backend bỏ qua |
| Order Service gọi payment.refund | Authorization từ chối |
| Inventory Service gọi payment intent | Authorization từ chối |
| Tenant/resource không khớp | Request bị từ chối |
| Request payment lặp cùng idempotency key | Không tạo payment intent trùng |
| Cùng nonce được gửi đồng thời | Chỉ một request claim nonce nếu protocol yêu cầu one-time |
| Shared API key cũ sau cutover | Bị từ chối |
| Một region chưa nhận revoke | Rollout/containment chưa được xác nhận hoàn tất |
| Token xuất hiện trong log/trace | Secret scan phát hiện; pipeline phải fail |
| Workload bị redeploy | Identity mới được cấp theo attestation, không dùng shared secret |

## 24. Tình huống sự cố: Order Service bị compromise

Giả sử attacker chiếm được một container Order Service. Attacker có thể truy cập process memory, token cache hoặc gọi API bằng workload identity của container.

### Phạm vi có thể bị ảnh hưởng

- Token cho inventory.hold.
- Token cho payment.intent.create.
- Order data và request context mà service có quyền đọc.
- User-delegated token nếu service được phép exchange.
- Workload identity credential hoặc quyền truy cập metadata endpoint.

### Containment

1. Cô lập workload instance hoặc deployment bị compromise.
2. Disable/revoke workload principal theo incident policy.
3. Revoke token/grant và ngăn token issuance mới.
4. Thu hồi hoặc rotate certificate/private key liên quan.
5. Xác minh Inventory và Payment từ chối token/identity cũ ở mọi region.
6. Kiểm tra request và payment intent đã tạo trong khoảng sự cố.
7. Review workload role, scope, audience và delegation grant.
8. Điều tra metadata endpoint, secret manager và runtime attestation.
9. Triển khai lại từ image/config đã xác minh với identity mới.
10. Theo dõi principal cũ và request bất thường sau containment.

### Vì sao per-workload identity quan trọng?

Nếu mọi service dùng chung một API key, việc thu hồi key có thể làm dừng toàn bộ tích hợp và vẫn không cho biết service nào bị chiếm. Với identity riêng, nhóm có thể cô lập Order Service, giữ Inventory và Payment hoạt động trong phạm vi an toàn, đồng thời kiểm tra chính xác quyền đã cấp.

## 25. Mẫu policy và token request

Ví dụ JSON minh họa policy cấp quyền. Đây là cấu hình khái niệm, cần chuyển sang schema và policy engine thực tế.

~~~json
{
  "client": "order-service",
  "workload_principal": "spiffe://shop.example/ns/prod/sa/order",
  "allowed_grants": ["client_credentials"],
  "resources": {
    "inventory-api": ["inventory.hold", "inventory.release"],
    "payment-api": ["payment.intent.create"]
  },
  "token_policy": {
    "max_lifetime_seconds": 300,
    "require_authenticated_client": true,
    "require_audience": true
  },
  "owner": "commerce-platform"
}
~~~

Policy này không cấp payment.refund hoặc payment.admin. Thay đổi scope phải qua review và approval, có audit và test.

### Token request minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.shop.example
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.hold&audience=inventory-api
~~~

Client authentication được thực hiện theo profile đã chọn, chẳng hạn mTLS hoặc private_key_jwt. Không gửi client secret trong query string và không ghi request body có assertion/secret vào log.

## 26. Checklist thiết kế service-to-service auth

- [ ] Mỗi workload có principal riêng và owner.
- [ ] Workload identity được cấp từ nguồn có attestation/trust rõ.
- [ ] Không dùng shared static API key giữa nhiều service.
- [ ] Client authentication dùng mTLS, private_key_jwt hoặc cơ chế mạnh phù hợp.
- [ ] Access token có audience, scope và lifetime cụ thể.
- [ ] Resource server xác minh issuer, signature, audience, thời hạn và scope.
- [ ] TLS được bật; mTLS được dùng theo trust model.
- [ ] Identity header từ client không được tin trực tiếp.
- [ ] Service identity được phân biệt với user identity.
- [ ] Delegation/on-behalf-of có token semantics và audience riêng.
- [ ] Authorization và business validation được thực hiện tại service đích.
- [ ] Idempotency/replay control phù hợp với hành động nghiệp vụ.
- [ ] Key/certificate/token có issuance, rotation và revocation.
- [ ] Secret/private key được bảo vệ và không xuất hiện trong log.
- [ ] Cache/JWKS/revocation propagation được kiểm tra.
- [ ] Network policy giới hạn route và egress.
- [ ] Monitoring có principal, audience, scope và reason group cần thiết.
- [ ] Incident runbook có thể cô lập một workload mà không làm mất kiểm soát toàn hệ thống.
- [ ] Test bao gồm negative, replay, concurrency, expiry, revoke và multi-region.
- [ ] Shared key cũ được thu hồi sau cutover và có xác minh.

## Ghi nhớ

Service-to-service authentication phải trả lời chính xác workload nào đang gọi và credential đó có được issuer tin cậy cấp hay không. OAuth Client Credentials, workload identity, mTLS hoặc private_key_jwt có thể kết hợp để tạo danh tính riêng, token ngắn hạn gắn audience/scope và kênh truyền được xác minh.

Authentication không tự cấp quyền nghiệp vụ. Service đích vẫn phải kiểm tra scope, resource, tenant, trạng thái và idempotency. Phân biệt workload principal với user principal; chỉ dùng delegation khi có nhu cầu và cơ chế được xác minh. Identity riêng, least privilege, rotation/revocation và kiểm thử trên mọi node giúp giới hạn blast radius khi một workload bị compromise.
