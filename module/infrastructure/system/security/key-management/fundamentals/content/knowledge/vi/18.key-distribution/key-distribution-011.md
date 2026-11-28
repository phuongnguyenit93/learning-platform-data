# Kiểm tra recipient

> **Chương:** Key distribution  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Recipient là ai và vì sao phải kiểm tra trước khi cấp khóa?

Trong **key distribution**, **recipient** là **chủ thể dự định nhận quyền sử dụng hoặc nhận vật liệu khóa**: một dịch vụ, thiết bị, người dùng, hệ thống đối tác, HSM partition hoặc tổ chức có trách nhiệm quản lý khóa. Recipient có thể nhận **khóa đã được wrap/encrypt**, một **key handle/grant trong KMS**, một secret tạm thời thông qua giao thức xác thực hoặc chỉ được cấp quyền gọi một số thao tác mật mã. Recipient **không nhất thiết nhận raw secret key**.

**Kiểm tra recipient (recipient verification)** là quá trình xác minh rằng **đúng chủ thể, đúng danh tính, đúng khóa công khai/đích tin cậy, đúng phạm vi được phép và đúng thời điểm** được nhận hoặc sử dụng khóa. Nó phải diễn ra **trước khi** tạo grant, wrap DEK cho public key của đích, phân phối PSK, trao quyền `Decrypt/Unwrap/Sign`, hoặc gửi key material qua một kênh truyền.

**Ví dụ:** dịch vụ Billing cần gửi một DEK đã wrap để đối tác xử lý dữ liệu hóa đơn. Một attacker gửi public key của mình và tự khai là `partner-payments`. Nếu Billing chỉ kiểm tra khóa có dạng RSA 3072-bit hợp lệ rồi mã hóa DEK cho khóa đó, dữ liệu sẽ đi vào tay attacker. **Public key hợp lệ về mặt mật mã không đồng nghĩa thuộc về recipient hợp lệ hoặc đã được ủy quyền.**

Kiểm tra recipient phải trả lời ít nhất **năm câu hỏi**:

1. **WHO:** danh tính nào đang nhận? Người, workload, device, organization hay HSM partition nào?
2. **WHICH KEY:** public key/certificate, key ID/version hoặc endpoint nào thực sự thuộc về danh tính đó?
3. **WHY:** danh tính đó có được phép nhận **loại khóa, dữ liệu, tenant, purpose và thời hạn** này không?
4. **HOW:** key được phân phối qua **kênh và cryptographic mechanism** đã được phê duyệt không?
5. **WHEN/PROOF:** chứng cứ danh tính, key binding, authorization và trạng thái recipient có còn hiệu lực tại lúc phát hành không?

**Thông điệp chính:** *Xác minh recipient là kiểm soát kết hợp giữa identity, trust, authorization và key lifecycle*, không phải một lệnh “validate public key” đơn lẻ.

### Mục tiêu học tập

Sau bài này, bạn sẽ phân biệt **authentication**, **authorization**, **key-to-identity binding** và **proof of possession (PoP)**; kiểm tra certificate chain/SAN/EKU/key usage và trạng thái thu hồi; chọn cơ chế phân phối DEK/KEK/PSK hoặc quyền KMS thích hợp; chống **public-key substitution, MITM, cross-tenant, replay và TOCTOU**; ghi audit và xử lý recipient rotation/revocation. Bài có ví dụ **Java 17** và tình huống vận hành nhiều tenant.

## 2. Bốn kiểm soát phải đồng thời đúng

| Kiểm soát | Câu hỏi | Điều kiện cần | Lỗi nếu bỏ qua |
| --- | --- | --- | --- |
| **Authentication** | Đây thật sự là ai? | mTLS, danh tính workload đã xác minh, PKI, identity provider, thiết bị được attested... | Attacker mạo danh recipient |
| **Key-to-identity binding** | Key/endpoint này thuộc ai? | Certificate/SAN, registry đáng tin, fingerprint/key ID đã ghim theo quy trình, HSM attestation khi cần | Khóa công khai bị tráo |
| **Authorization** | Chủ thể ấy có được nhận khóa này không? | Key owner policy, IAM, tenant/resource/purpose scope, approval | Recipient thật nhưng không có quyền |
| **Freshness & suitability** | Quyết định còn hợp lệ không? | Expiry, revocation, algorithm/key usage, key version, replay/rotation checks | Dùng chứng thư, quyền hoặc key cũ |

**Không được suy ra authorization từ authentication.** Một chứng thư mTLS hợp lệ cho `service-reports` chỉ chứng minh danh tính theo PKI được tin; nó **không tự cấp quyền** lấy DEK của `tenant-payments`.

### 2.1. Recipient identity không đồng nghĩa địa chỉ mạng

Địa chỉ IP, hostname, URL hay queue topic chỉ là **đích định tuyến**. Một hostname có thể bị cấu hình sai DNS, proxy hoặc service discovery; nó không thay thế **xác thực endpoint**. Với TLS, client cần kiểm tra hostname/expected service identity qua **cơ chế chuẩn của TLS stack**, trust anchor và certificate chain; không tắt verification chỉ vì request đang trong VPC/private network.

### 2.2. Recipient có thể nhận một *capability* chứ không nhận key bytes

Khi KMS cho workload quyền **`Unwrap` trên một KEK** hoặc một **grant giới hạn**, recipient nhận **khả năng thực hiện operation** theo IAM/KMS policy, không nhất thiết nhận raw KEK. Khi HSM ký số theo yêu cầu, bên được ủy quyền nhận **signature output**, không nhận private signing key.

Vì vậy, cần xác định rõ **vật được phân phối**: raw secret, wrapped secret, private-key import blob, public key, key reference, KMS grant, token tạm thời hay kết quả key agreement. Mỗi loại có rủi ro và tiêu chí xác minh khác nhau.

## 3. Mô hình đe dọa khi chọn sai recipient

| Kiểu tấn công/sai sót | Kịch bản | Tác động |
| --- | --- | --- |
| **Public-key substitution** | Attacker thay public key trong registry hoặc request | DEK được wrap cho private key của attacker |
| **MITM** | Client không xác thực peer trong TLS/(EC)DH | Attacker chặn/đổi khóa hoặc secret trong phiên |
| **Wrong tenant / cross-tenant** | Workload tenant A được cấp wrapped DEK của tenant B | Lộ dữ liệu xuyên tenant |
| **Confused deputy** | Service được phép dùng KMS phục vụ caller chưa được ủy quyền | KMS trở thành `Unwrap`/decrypt oracle |
| **Stale certificate** | Recipient cert bị thu hồi, hết hạn hoặc thay key | Trao secret cho đích không còn tin cậy |
| **Replay** | Gửi lại grant/token/wrapped secret trước đó | Tái kích hoạt quyền hoặc cấp khóa hết hiệu lực |
| **Downgrade** | Bên gửi fallback sang thuật toán/kênh yếu | Tăng khả năng giải mã, sửa hoặc tráo dữ liệu |
| **TOCTOU** | Recipient hợp lệ lúc duyệt nhưng bị offboard trước lúc gửi | Phân phối sau khi quyền đã bị thu hồi |
| **Key misuse** | Dùng signing public key cho key transport trái policy | Sai key usage, rủi ro liên giao thức |
| **Wrong HSM partition** | Gửi wrapped key tới partition/slot khác | Key đến sai miền tin cậy hoặc không restore được |
| **Compromised recipient** | Chủ thể đích hợp lệ nhưng host bị chiếm | Secret vẫn có thể bị lấy sau khi nhận |

### 3.1. Sơ đồ public-key substitution

~~~mermaid
sequenceDiagram
    participant App as Sender / Data service
    participant Attacker as Attacker
    participant Registry as Trusted recipient registry
    participant Recipient as Legitimate recipient
    Attacker->>App: "Tôi là Recipient B; đây là public key của tôi"
    Note over App,Attacker: Nếu tin key từ request, DEK có thể bị wrap cho attacker
    App->>Registry: Tra cứu B + tenant + purpose + approved key version
    Registry-->>App: B identity + certified key + status + policy revision
    App->>Recipient: Xác thực endpoint / PoP theo protocol khi cần
    App->>App: So khớp recipient identity, key binding, authorization, freshness
    App-->>Attacker: Từ chối key không khớp registry
    App->>Recipient: Gửi wrapped DEK dưới key đã được xác minh
~~~

**Điểm quyết định:** bên gửi **không lấy public key của đối tượng cần cấp khóa từ chính thông điệp không đáng tin rồi mặc định đó là key của người nhận**. Dùng trust chain/registry/key binding độc lập, có policy và revision.

## 4. Quy trình xác minh recipient trước khi phân phối

Một quy trình **fail closed** có thể có các bước:

1. **Phân loại key:** đây là DEK, KEK, PSK, session secret hay private signing key? Có được phép export/wrap không?
2. **Xác thực requester:** ai yêu cầu chia sẻ hoặc cấp grant? Có quyền với dữ liệu/tenant không?
3. **Giải quyết recipient từ nguồn tin cậy:** recipient ID, tenant, organization, workload identity, environment và purpose.
4. **Xác thực binding:** certificate/public key, key handle, HSM partition hoặc account principal thuộc recipient được phê duyệt.
5. **Kiểm tra suitability:** algorithm, độ mạnh, key usage/EKU, chain, expiry, revocation, proof of possession khi cần.
6. **Authorize việc phân phối:** đúng `keyId/version`, recipient, purpose, data classification, thời hạn và approval/quorum của key owner.
7. **Kiểm tra lại trước khi thực thi:** eligibility, key state, policy revision và credential/recipient version chưa thay.
8. **Wrap/cấp quyền:** thực hiện bằng KMS/HSM hoặc giao thức đã được phê duyệt; không export raw KEK ngoài policy.
9. **Binding và delivery:** gắn recipient/context/operation ID vào envelope, gửi qua authenticated channel.
10. **Ghi receipt và audit:** ai yêu cầu, ai nhận, key version nào, decision/policy nào, thời gian và kết quả thực.

~~~mermaid
flowchart TD
    Req[Distribution request + requester identity] --> P[Validate requester / tenant / data scope]
    P -->|Deny| X[Reject + audit]
    P -->|Allow| R[Resolve recipient in trusted registry]
    R --> ID[Authenticate identity + public key/cert binding]
    ID -->|Fail| X
    ID -->|Pass| S[Check expiry, revocation, key usage, key version]
    S -->|Fail| X
    S -->|Pass| A[Authorize recipient, purpose, classification, policy]
    A -->|Deny| X
    A -->|Allow| J[Revalidate before issuance; request binding]
    J -->|Stale| X
    J -->|Valid| K[KMS/HSM wrap / scoped grant / AKE]
    K --> D[Authenticated delivery + correlation ID]
    D --> Audit[Audit receipt + lifecycle tracking]
~~~

### 4.1. Thứ tự không chỉ là thủ tục hành chính

Nếu **KMS `Unwrap` hoặc export raw DEK xảy ra trước authorization**, secret đã đi ra vùng bảo vệ. Việc trả HTTP 403 sau đó **không thu hồi** được các byte đã lộ. Vì vậy, các bước xác thực/ủy quyền phải đến **trước side effect mật mã nhạy cảm**.

### 4.2. Không coi registry là bất khả xâm phạm

Recipient registry cần quyền ghi tách vai, versioned change, approval, audit và kiểm tra chống **key substitution**. Nếu attacker có quyền thay registry từ public key của đối tác sang key của mình, quá trình lookup có thể “thành công” nhưng vẫn phân phối sai đích. Bảo vệ registry/key enrollment là một phần của bảo vệ key distribution.

## 5. Các loại recipient và phương pháp kiểm tra tương ứng

| Recipient | Đối tượng phân phối thường gặp | Kiểm tra cần thiết |
| --- | --- | --- |
| **Workload nội bộ** | KMS grant, DEK/PSK được wrap, secret theo phiên | Workload identity, mTLS, tenant/purpose IAM, deployment/environment |
| **Đối tác bên ngoài** | Wrapped DEK, public-key-encrypted message | Tổ chức/contract, certificate chain, public-key binding, key use, expiry |
| **Thiết bị IoT** | Per-device PSK, key-agreement identity | Device enrollment, unique ID, credential/attestation, firmware posture theo risk |
| **Người dùng cuối** | Encrypted file key, recovery capability | AuthN mạnh, quyền file/record, account recovery policy, thiết bị đích |
| **HSM partition / KMS tenant** | Wrapped key object, imported key, backup | Partition ID, ownership, attestation/approved transfer, operator/quorum |
| **Microservice API** | Token/grant hoặc keying material của phiên | Service identity, audience, mTLS/SPIFFE khi dùng, least privilege |
| **CA / signing service** | Private-key handle hoặc sign capability | Trust domain, certificate issuance authority, key usage, HSM policy |
| **Backup/DR environment** | Bản wrapped key, khả năng restore | DR role, environment/region, recovery quorum, encryption context |

### 5.1. Phân phối *public key* và *secret key* có mục tiêu khác nhau

Public key về nguyên tắc **không cần bí mật**, nhưng cần **xác thực nguồn và key-to-identity binding**. Nếu attacker tráo public key người nhận, họ có thể đọc bí mật mà sender mã hóa. Nếu attacker tráo public verification key, họ có thể khiến ứng dụng chấp nhận chữ ký giả.

Secret key/DEK/PSK cần bảo mật khi truyền và giới hạn số recipient; càng nhiều bên có raw key, phạm vi cần tin cậy và thu hồi càng phức tạp. **Không gửi private signing key cho verifier**: verifier chỉ cần public key/chứng thư đúng trust.

### 5.2. Một recipient có nhiều version khóa

Recipient có thể dùng `recipient-encryption-key/v3` và đồng thời giữ `v2` để decrypt dữ liệu cũ. Khi gửi key mới, dùng **version được phê duyệt cho nhận mới**, không mặc định chọn alias `current` thiếu kiểm tra state. Payload cũ cần tham chiếu version chính xác hoặc định dạng cho phép định tuyến an toàn.

## 6. Kiểm tra certificate và identity binding bằng PKI

Nếu recipient đưa ra **X.509 certificate**, các bước validation thường bao gồm:

1. **Trust anchor:** certificate chain dẫn tới CA/trust anchor đã được cấu hình theo chính sách, không lấy root CA do recipient gửi và tin ngay.
2. **Path validation:** chữ ký các chứng thư, basic constraints, key usage của CA, name constraints, chính sách và thuật toán theo triển khai.
3. **Validity:** `notBefore`/`notAfter` phù hợp với thời điểm xác minh; xử lý clock skew đã được xác định.
4. **Subject Alternative Name (SAN):** đúng identity được mong đợi (DNS/IP/URI/SPIFFE ID...), không chỉ certificate có chữ “Trusted” hay CN tùy ý.
5. **Extended Key Usage (EKU) và Key Usage:** certificate được phép cho **mục đích sử dụng cụ thể**; key transport, TLS client/server auth, code signing là mục đích khác nhau.
6. **Revocation:** CRL/OCSP hoặc cơ chế status được chính sách yêu cầu; không cho cert bị thu hồi dùng chỉ vì chưa hết hạn.
7. **Public key strength và thuật toán:** RSA/ECDSA/Ed25519/X25519 theo profile, curve/key size/parameters đủ an toàn.
8. **Recipient authorization:** tenant, service, dữ liệu và operation được phép — **bước này không do certificate path validator tự làm**.

### 6.1. Chain hợp lệ không đồng nghĩa recipient đúng

CA có thể phát hành nhiều chứng thư cho nhiều đối tác. Một certificate chain hợp lệ cho `partner-B` không cho phép dùng nó để wrap DEK của `partner-A`. Phải kiểm tra **SAN/subject mapping tới recipient ID trong trusted registry**, sau đó kiểm tra **quyền trên dữ liệu/tenant**.

### 6.2. Certificate dành cho TLS khác certificate dành cho key transport

Chứng thư mTLS được dùng để **xác thực đầu cuối kênh truyền**. Chứng thư dùng RSA public key để **wrap DEK** phải có key usage/algorithm phù hợp với **key encipherment** và chính sách của hệ thống. **Đừng tự động tái sử dụng một private key cho TLS authentication, ký số và key transport** nếu profile không cho phép: key separation làm giảm rủi ro cross-protocol misuse.

EKU bắt buộc tùy certificate profile; không mặc định mọi chứng thư RSA đều có EKU “key wrapping”. Nếu một profile chuyên dùng yêu cầu OID EKU cụ thể, phải **định nghĩa rõ trong policy**, validate nó và quản lý việc phát hành.

### 6.3. SAN và SPIFFE ID

Một workload có thể được nhận dạng bằng **URI SAN** như `spiffe://prod.example/ns/billing/sa/exporter` khi tổ chức có trust domain và cơ chế quản lý workload identity tương ứng. Giá trị này chỉ đáng tin khi chứng thư được xác thực bởi **trust domain đúng** và mapping sang quyền key distribution được phê duyệt.

Không coi chuỗi `spiffe://...` tự khai trong request JSON là bằng chứng danh tính, và không “khớp substring” kiểu bất kỳ URI nào chứa `billing` đều hợp lệ.

### 6.4. Revocation và dữ liệu status không sẵn sàng

Certificate có thể bị thu hồi trước `notAfter`. Chính sách phải xác định **cách lấy/kiểm tra CRL/OCSP, cache TTL, lỗi mạng, soft-fail/hard-fail theo mức rủi ro**. Đối với việc cấp DEK có phạm vi rộng, thường không nên bỏ qua dữ liệu revocation chỉ để giữ availability.

Một demo dùng `setRevocationEnabled(false)` **chưa phải xác minh recipient hoàn chỉnh**. Production phải có thiết kế trạng thái thu hồi và cập nhật trust anchor/issuer.

## 7. Proof of possession (PoP): recipient có thật sự kiểm soát khóa?

**Proof of possession** là bằng chứng recipient có khả năng sử dụng **private key tương ứng** với public key đã đăng ký, hoặc kiểm soát key handle/capability theo giao thức được thiết kế. PoP có ích khi enrollment hoặc khi sender muốn tránh phân phối bí mật cho một public key bị đăng ký sai mà recipient không thể dùng.

### 7.1. Ví dụ challenge–response

1. Server xác định **recipient ID và public key đã được registry/PKI xác thực**.
2. Server tạo **challenge ngẫu nhiên bằng CSPRNG**, có nonce, expiry, request ID và domain separation.
3. Recipient ký challenge bằng **private key dùng cho chứng minh danh tính** hoặc thực hiện cơ chế PoP do giao thức quy định.
4. Server xác minh proof bằng **public key được tin**, kiểm tra challenge chưa được dùng, thời hạn và identity/tenant tương ứng.
5. Nếu đạt, server tiếp tục authorization và phân phối khóa đúng mechanism.

**Không tự tái sử dụng cùng một key cho cả signing PoP và RSA-OAEP unwrap** nếu policy không cho phép. Một thiết kế có thể sử dụng **khóa xác thực riêng** và **khóa mã hóa recipient riêng**, với bản ghi enrollment/trust binding liên kết cả hai khóa.

### 7.2. Điều PoP chứng minh — và không chứng minh

| PoP có thể hỗ trợ | PoP **không tự chứng minh** |
| --- | --- |
| Bên tham gia có thể dùng private key/credential tương ứng | Người đó có quyền đọc dữ liệu của tenant khác |
| Enrollment không chỉ dựa vào public key đã upload | Private key nằm trong HSM hoặc không bị sao chép |
| Challenge được trả lời trong một phiên xác thực | Host không bị malware/attacker kiểm soát |
| Người nhận có thể unwrap một test object theo giao thức | Certificate chain, key usage và revocation đã hợp lệ |

**Chỉ chứng minh key control không chứng minh đúng người.** Nếu một attacker tự tạo key pair và ký được challenge do mình yêu cầu, PoP thành công nhưng **key chưa chắc được gắn với recipient hợp lệ**.

### 7.3. Khi PoP được bao hàm bởi giao thức

Một số giao thức như **mTLS với certificate-bound identities** hoặc **authenticated key establishment** đã có cơ chế xác thực bằng private key và freshness tích hợp. Không tự thêm challenge bespoke nếu chỉ làm trùng lặp không cần thiết và tăng lỗi. Chọn **protocol chuẩn, library được kiểm tra và expected peer identity**; dùng PoP riêng trong key enrollment/ceremony nếu chính sách yêu cầu.

## 8. Authorization: recipient có quyền nhận *đúng khóa đó* không?

Một recipient có identity thật và public key hợp lệ vẫn có thể **không được phép** nhận DEK của record cụ thể. Recipient authorization cần gắn ít nhất:

| Thuộc tính policy | Ví dụ |
| --- | --- |
| `recipientId` | `partner-acquirer-07` |
| `recipientType` | `PARTNER_WORKLOAD` |
| `tenantScope` | `production/tenant-42` |
| `dataClassification` | `CONFIDENTIAL_PAYMENTS` |
| `purpose` | `SETTLEMENT_EXPORT` |
| `keyClass` | `DEK`, không phải root KEK |
| `allowedOperations` | `RECEIVE_WRAPPED_DEK` hoặc `KMS_UNWRAP` |
| `recipientKeyId/version` | `partner-07-encryption/v3` |
| `issuer/trustDomain` | Trust domain hoặc CA được phê duyệt |
| `validFrom/until` | Thời hạn quan hệ và quyền nhận |
| `policyRevision/approvalRef` | Thay đổi được phê duyệt, audit được |

### 8.1. RACI: ai ra quyết định?

| Vai trò | Trách nhiệm |
| --- | --- |
| **Data owner** | Quyết định dữ liệu có được chia sẻ, tenant/purpose/retention |
| **Key owner** | Xác định key class, recipient scope, cryptoperiod, wrapping/export policy |
| **Security/PKI** | Trust anchors, certificate profiles, identity binding, revocation |
| **Key custodian / KMS operator** | Cấu hình IAM/key grants, HSM controls, thực thi workflow được duyệt |
| **Distribution service** | AuthN/AuthZ, check recipient, bind request, wrap/deliver, audit |
| **Recipient admin** | Quản lý private key/endpoint, rotation, bảo mật môi trường nhận |
| **Auditor** | Kiểm tra evidence và sai lệch; không mặc nhiên có quyền `Decrypt` |

**Không cấp quyền raw KEK hoặc `DeleteKey` chỉ vì một recipient được phép đọc vài ciphertext.** Sử dụng **least privilege, scope theo tenant/service/operation/time**; với phân phối root key, key export hoặc trust-root change, có thể yêu cầu **quorum approval** theo risk tier.

### 8.2. Cross-tenant authorization

Nếu shared KMS KEK dùng cho nhiều tenant, principal có quyền `Unwrap` trên KEK đó **không có nghĩa** được unwrap bản ghi mọi tenant. Resource authorization của application và encryption context/tenant-binding của KMS nếu có phải kết hợp chặt, tránh **confused deputy**.

### 8.3. Vòng đời quyền độc lập với vòng đời khóa

Recipient có thể hết hợp đồng hôm nay dù KEK còn active ba tháng. **Recipient authorization expiry/revocation** phải được kiểm tra riêng với **key cryptoperiod**. Ngược lại, recipient được phép vẫn không được yêu cầu dùng key đã revoke hoặc vượt `newUseUntil` cho việc phân phối mới.

## 9. Kênh và cơ chế phân phối khóa đúng recipient

**Không nên thiết kế phân phối bằng cách “gửi secret qua HTTPS là xong”.** HTTPS xác thực và bảo vệ kênh theo cấu hình đúng, nhưng việc secret có cần rời KMS/HSM không, recipient nào được phép, key được wrap thế nào và dữ liệu tồn tại sau khi nhận vẫn phải được quyết định.

| Phương án | Khi phù hợp | Xác minh recipient và giới hạn |
| --- | --- | --- |
| **KMS grant/permission** | Workload dùng key qua API, không cần raw KEK | Principal IAM, tenant/condition, key ID/version, grant lifetime, audit |
| **KMS/HSM wrap DEK** | Gửi DEK đã bọc cho hệ thống được ủy quyền | Recipient key binding hoặc provider context, wrap mechanism, key version |
| **HPKE (RFC 9180)** | Hybrid public-key encryption theo suite đã chuẩn hóa | Public key recipient phải được xác thực/authorize, context/info binding, library chuẩn |
| **CMS EnvelopedData / JWE** | Trao key/content theo format chuẩn với PKI/web ecosystem | Certificate/JWK trust, alg allowlist, `kid`/recipient binding, replay defense |
| **Authenticated TLS/mTLS** | Truyền secret đã được cấp phát giữa endpoint có trust | Chain + expected identity, E2E boundary, authz và secret lifecycle |
| **Authenticated (EC)DH/handshake** | Hai peer thiết lập session secret | Peer authentication, chống MITM, HKDF/key schedule, transcript binding |
| **HSM-to-HSM secure transfer** | Di chuyển/backup key object theo policy | Partition/recipient HSM identity, wrapped transfer, operator approval, evidence |
| **PSK provisioning** | Thiết bị/đối tác theo giao thức đã đánh giá | Per-device identity, secure enrollment, unique key, rotate/revoke |

### 9.1. Đừng wrap KEK gốc như một DEK thông thường

Một **KEK cấp cao** bảo vệ nhiều DEK có blast radius rộng. Nếu policy yêu cầu KEK non-extractable, **không export raw KEK chỉ vì có một recipient được cấp quyền đọc dữ liệu**. Khi có nhu cầu liên môi trường, cân nhắc **KMS grant, secure HSM import/transfer, rewrap hoặc cấp một DEK phạm vi hẹp** thay vì phát tán root key.

### 9.2. Public-key encryption không thay trust

RSA-OAEP, HPKE hoặc JWE có thể mã hóa dữ liệu cho public key recipient, nhưng nếu public key là của attacker, chính thuật toán tốt sẽ **giúp attacker nhận secret một cách an toàn**. Kết nối cryptography với **PKI/registry, chứng cứ quyền và exact recipient key version** là bắt buộc.

### 9.3. Không tự thiết kế key agreement

Với ECDH/X25519, hai bên có thể tính shared secret nhưng nếu **public key trao đổi không được xác thực**, attacker có thể thực hiện MITM. Dùng **TLS 1.3 hoặc một AKE protocol được đánh giá**, key schedule/KDF chuẩn với context separation; không dùng raw ECDH secret trực tiếp làm AES key theo cách tùy tiện.

## 10. Gắn recipient vào envelope và chống replay

Khi phân phối **wrapped DEK** hoặc grant, một envelope có thể chứa:

~~~json
{
  "formatVersion": 2,
  "operationId": "dist-20261128-0012",
  "issuer": "payments-key-distributor",
  "recipientId": "partner-acquirer-07",
  "recipientKeyId": "partner-07-encryption",
  "recipientKeyVersion": "v3",
  "recipientKeyFingerprint": "<verified-public-key-digest>",
  "tenantScope": "production/tenant-42",
  "purpose": "SETTLEMENT_EXPORT",
  "dataKeyRef": "invoice-batch-2026-11-28/dek-01",
  "wrappingAlgorithm": "APPROVED_HPKE_SUITE_OR_KMS_BLOB",
  "wrappedDek": "<base64-of-wrapped-dek>",
  "issuedAt": "2026-11-28T03:00:00Z",
  "expiresAt": "2026-11-28T03:10:00Z",
  "policyRevision": 17,
  "evidenceRef": "recipient-approval-1093"
}
~~~

**Dữ liệu là schema minh họa**, không phải JWE/HPKE/KMS API tiêu chuẩn. Placeholder không phải ciphertext hợp lệ. Trường `recipientKeyFingerprint` là digest của **public key được phê duyệt**, không phải fingerprint được tạo bằng cách xuất raw private key/KEK.

### 10.1. Metadata phải được bảo vệ khỏi sửa/tráo

Nếu attacker sửa `recipientId`, `tenantScope`, `purpose` hoặc `keyVersion` trong header nhưng wrapped DEK vẫn được chấp nhận, có thể dẫn đến **confusion hoặc phân phối sai quyền**.

Cần **cryptographically bind** ngữ cảnh vào message qua AEAD AAD, HPKE `info`/AAD phù hợp, protocol transcript/recipient headers được bảo vệ hoặc **KMS encryption context** theo semantics provider. **Không giả định AES-KW cơ bản có AAD**; khi wrapping mechanism không hỗ trợ bind ngữ cảnh, phải dùng **trusted container/authorization** và các biện pháp integrity cấp protocol để tránh tráo header.

### 10.2. Exact version, không chỉ alias

Recipient public key và sender KEK có thể xoay vòng. Mỗi envelope/receipt phải chỉ rõ **key identity/version chính xác** hoặc chứa blob cho provider định tuyến đáng tin. Alias `current` có thể đổi sau khi phê duyệt; đó không phải bằng chứng material cụ thể đã được sử dụng.

### 10.3. Replay protection và expiry

Một wrapped DEK được phát đúng cho recipient hôm qua **không tự trở thành vô hại hôm nay**. Tùy mô hình threat:

- Dùng `operationId` hoặc `messageId` duy nhất.
- Có `issuedAt`, `expiresAt`, expected audience/purpose.
- Nếu một lần dùng, lưu **single-use/consumption state** với giao dịch đủ tin cậy.
- Giới hạn quyền KMS/grants theo TTL/scope và revoke khi không còn cần.
- Tránh nhận lại envelope sau khi recipient bị offboard hoặc key bị revoke.

**TTL ở header chỉ có tác dụng nếu recipient/protocol thực sự kiểm tra và enforce**, không làm ciphertext không thể giải mã sau giờ hết hạn nếu private key/DEK đã được lấy. **Revocation không xóa bản sao secret mà recipient đã nhận.**

## 11. Identity, key và authorization có thể thay đổi trong khi gửi

**TOCTOU (time-of-check to time-of-use)** xảy ra khi hệ thống đã duyệt recipient dưới một trạng thái nhưng **trước lúc thực thi**, certificate/key version, IAM, tenant ownership hoặc đối tác đã bị thu hồi/thay đổi.

Một thao tác phân phối an toàn cần:

1. Gắn approval với **request digest**, recipient ID, exact key/version, tenant, data classification, action, policy revision và expiry.
2. Trước KMS `Wrap` hoặc cấp grant, **revalidate** recipient status, key suitability, trust và permission.
3. Tránh tin cache lâu hơn giới hạn revocation/rotation chấp nhận được.
4. Dùng **compare-and-swap/conditional issuance** hoặc transaction cho trạng thái recipient/grant nếu hạ tầng cho phép.
5. Sau khi cấp, lưu evidence và đối chiếu **actual provider response** với request.

### 11.1. Ví dụ race

Lúc 10:00, recipient `partner-07` còn hợp đồng, dùng key `v3`. Lúc 10:02, key `v3` bị revoke do sự cố. Lúc 10:03, worker xử lý request phê duyệt từ 10:00. Nếu không kiểm tra lại, DEK có thể được wrap cho key đã compromise.

**Biện pháp:** kiểm tra tại điểm thực thi, phát hành permit ngắn hạn gắn policy revision và key version, có cơ chế invalidate state khi revoke.

### 11.2. Không tồn tại transaction chung mặc định giữa registry, KMS và mạng

Grant có thể được KMS tạo thành công nhưng response timeout; recipient có thể nhận wrapped DEK trong khi audit service lỗi. Sử dụng **idempotency/operation ID, reconciliation và audit receipt**, không retry mù quáng hoặc tạo raw secret copy để “bảo đảm gửi lại”.

## 12. Java 17: xác minh certificate binding trước khi wrap khóa

Ví dụ sau **chỉ minh họa lớp kiểm tra recipient certificate cho mục đích RSA key transport**. Nó xác nhận **đường chứng thư PKIX, public key RSA đủ mạnh, key usage cho key encipherment, URI SAN đúng identity** và EKU nếu profile yêu cầu.

**Quan trọng:** ví dụ **không gọi KMS, không phân phối DEK và cố ý tắt revocation để có thể chạy offline**. Không được dùng nguyên xi cho production; cần **CRL/OCSP/PKIXRevocationChecker** hoặc cơ chế status/trust của tổ chức, cấp chứng thư đúng profile, trust anchor được quản trị và **authorization riêng** đối với tenant/DEK. Mã không tự tải chứng thư từ nguồn không tin cậy hay tạo trust anchor từ certificate của recipient.

~~~java
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class RecipientCertificateCheck {
    private static final int SAN_URI = 6;
    // X.509 KeyUsage bit #2 = keyEncipherment, dành cho profile RSA wrap này.
    private static final int KEY_ENCIPHERMENT_BIT = 2;

    // intermediates theo thứ tự leaf -> issuer -> ... (không gồm root).
    static void validateForRsaKeyTransport(
            X509Certificate recipientLeaf,
            List<X509Certificate> intermediates,
            X509Certificate configuredTrustRoot,
            String expectedRecipientUri,
            String requiredEkuOid,
            Instant now) throws Exception {
        Objects.requireNonNull(recipientLeaf);
        Objects.requireNonNull(intermediates);
        Objects.requireNonNull(configuredTrustRoot);
        Objects.requireNonNull(now);
        if (expectedRecipientUri == null || expectedRecipientUri.isBlank()) {
            throw new IllegalArgumentException("Missing trusted recipient ID");
        }

        recipientLeaf.checkValidity(Date.from(now));
        if (!(recipientLeaf.getPublicKey() instanceof RSAPublicKey rsa)
                || rsa.getModulus().bitLength() < 3072) {
            throw new SecurityException("Unsupported recipient RSA key");
        }

        boolean[] usage = recipientLeaf.getKeyUsage();
        if (usage == null || usage.length <= KEY_ENCIPHERMENT_BIT
                || !usage[KEY_ENCIPHERMENT_BIT]) {
            throw new SecurityException("Key encipherment not permitted");
        }

        boolean matchingSan = false;
        Collection<List<?>> names =
                recipientLeaf.getSubjectAlternativeNames();
        if (names != null) {
            for (List<?> san : names) {
                if (san.size() >= 2
                        && san.get(0) instanceof Integer type
                        && type == SAN_URI
                        && expectedRecipientUri.equals(san.get(1))) {
                    matchingSan = true;
                }
            }
        }
        if (!matchingSan) {
            throw new SecurityException("Recipient URI SAN mismatch");
        }

        if (requiredEkuOid != null) {
            List<String> ekus = recipientLeaf.getExtendedKeyUsage();
            if (ekus == null || !ekus.contains(requiredEkuOid)) {
                throw new SecurityException("Recipient EKU mismatch");
            }
        }

        List<X509Certificate> pathCerts = new ArrayList<>();
        pathCerts.add(recipientLeaf);
        pathCerts.addAll(intermediates);
        CertificateFactory factory =
                CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(pathCerts);
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(configuredTrustRoot, null)));
        params.setDate(Date.from(now));

        // OFFLINE DEMO ONLY. Production phải có revocation policy
        // và kiểm tra CRL/OCSP hoặc cơ chế tương ứng.
        params.setRevocationEnabled(false);
        CertPathValidator.getInstance("PKIX").validate(path, params);
    }

    // Caller tiếp tục kiểm tra recipient ID đã xác thực,
    // tenant/resource authorization, key version, approval và state.
}
~~~

### 12.1. Những lưu ý khi áp dụng mã

- **`configuredTrustRoot`** phải do operator/PKI được ủy quyền cấu hình trước, không nhận tùy ý từ người gửi request.
- **`expectedRecipientUri`** phải đến từ **trusted recipient registry/authorization decision**, không từ trường client có thể tự đổi.
- **`keyEncipherment`** phù hợp với profile RSA key transport trong ví dụ; certificate dùng EC agreement, mTLS hoặc chữ ký cần **các checks khác**.
- **`requiredEkuOid`** phải là EKU được chính sách phát hành certificate xác định. Nếu profile bắt buộc EKU mà caller truyền `null`, policy gate ở tầng ngoài phải chặn.
- **Đúng key đã được kiểm tra:** public key dùng để wrap DEK phải chính là public key trong certificate/registry đã xác minh (hoặc có binding được phê duyệt tới key đó). Không được validate certificate A rồi lấy public key B từ payload client để mã hóa.
- **`setRevocationEnabled(false)`** là **giới hạn nghiêm trọng**: dùng để giải thích PKIX offline, **không phải cấu hình an toàn chung**.
- Code không tự xác thực possession, không đánh giá HSM/non-extractability, không có authorization cho DEK và không bảo vệ chống tất cả cross-protocol issues.
- Trong một hệ thống mTLS/HTTPS thông thường, ưu tiên **TLS stack chuẩn với endpoint identity verification**, không tự xây một phần certificate checker rồi vô tình bỏ hostname/revocation.

**Đây là lớp kiểm tra kỹ thuật**, chưa phải phép quyết định đầy đủ “recipient được nhận khóa nào”. Xác minh chứng thư hợp lệ vẫn phải **liên kết với chính sách phát khóa** và trạng thái recipient tại lúc wrap.

## 13. Java 17: bind DEK vào đúng recipient bằng RSA-OAEP

Mã sau minh họa **key transport với RSA-OAEP** và một recipient record **đã được trusted registry/authorization service xác minh**. Nó không thay thế mTLS/PKIX và không có KMS thật:

- Sender **không nhận public key tùy ý từ client**, mà lấy key từ `RecipientBinding` được xác nhận ở tầng tin cậy.
- Trước khi wrap, sender kiểm tra **identity đã xác minh, tenant, recipient status, scope, thời hạn và key version**.
- Dùng RSA-OAEP với **SHA-256 cho cả OAEP digest và MGF1**, đồng thời đưa **recipient ID, tenant, version và domain separator** vào OAEP label.
- Receiver phải giải mã bằng private key tương ứng và đúng **context**, nếu sửa context thì decryption sẽ thất bại.
- Cả hai phía dùng **KeyPair RSA riêng cho mục đích key transport**; ví dụ không dùng nó để ký approval hay xác thực TLS.

**Cảnh báo:** đây là minh họa **một nguyên lý**, không phải giao thức phân phối production. Trong thực tế, ưu tiên **HPKE/CMS/JWE, KMS/HSM hoặc protocol đã được đánh giá** cùng authenticated delivery và replay protection. RSA-OAEP **bảo vệ bí mật DEK cho recipient**, **không tự xác thực danh tính của sender** và không chứng minh receiver được phép đọc dữ liệu nghiệp vụ.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.time.Instant;
import java.util.Arrays;
import java.util.Objects;
import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class VerifiedRecipientDeliveryDemo {
    private static final SecureRandom RNG = new SecureRandom();

    // Binding phải đến từ registry + identity + authorization đã kiểm tra.
    record RecipientBinding(
            String recipientId,
            String tenant,
            String publicKeyVersion,
            PublicKey wrappingPublicKey,
            Instant permissionExpiresAt,
            boolean identityVerified,
            boolean allowedToReceiveDek) {}

    record Delivery(
            String recipientId,
            String tenant,
            String wrappingKeyVersion,
            byte[] wrappedDek) {
        Delivery {
            wrappedDek = Objects.requireNonNull(wrappedDek).clone();
        }
        @Override public byte[] wrappedDek() {
            return wrappedDek.clone();
        }
    }

    static void writeField(DataOutputStream out, String value)
            throws Exception {
        byte[] data = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(data.length);
        out.write(data);
    }

    static byte[] recipientContext(
            String recipientId, String tenant, String version)
            throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        writeField(out, "KEY-DISTRIBUTION/DEK-TRANSPORT/V1");
        writeField(out, recipientId);
        writeField(out, tenant);
        writeField(out, version);
        out.flush();
        return buffer.toByteArray();
    }

    static Cipher oaep(
            int mode, Key key, byte[] context) throws Exception {
        OAEPParameterSpec spec = new OAEPParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                new PSource.PSpecified(context));
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        cipher.init(mode, key, spec);
        return cipher;
    }

    static Delivery issue(
            RecipientBinding verifiedRecipient,
            String requestedRecipientId,
            String requestedTenant,
            byte[] rawDek,
            Instant now) throws Exception {
        Objects.requireNonNull(verifiedRecipient);
        Objects.requireNonNull(rawDek);
        Objects.requireNonNull(now);
        if (!verifiedRecipient.identityVerified()
                || !verifiedRecipient.allowedToReceiveDek()
                || !verifiedRecipient.recipientId()
                        .equals(requestedRecipientId)
                || !verifiedRecipient.tenant().equals(requestedTenant)
                || verifiedRecipient.publicKeyVersion() == null
                || verifiedRecipient.publicKeyVersion().isBlank()
                || verifiedRecipient.wrappingPublicKey() == null
                || !(verifiedRecipient.wrappingPublicKey()
                        instanceof RSAPublicKey rsa)
                || rsa.getModulus().bitLength() < 3072
                || verifiedRecipient.permissionExpiresAt() == null
                || !now.isBefore(
                        verifiedRecipient.permissionExpiresAt())
                || rawDek.length != 32) {
            throw new SecurityException("Recipient policy denied");
        }

        byte[] label = recipientContext(
                requestedRecipientId, requestedTenant,
                verifiedRecipient.publicKeyVersion());
        byte[] wrapped = oaep(
                Cipher.ENCRYPT_MODE,
                verifiedRecipient.wrappingPublicKey(),
                label).doFinal(rawDek);
        return new Delivery(
                requestedRecipientId, requestedTenant,
                verifiedRecipient.publicKeyVersion(), wrapped);
    }

    // Phía nhận: key riêng thuộc recipient, không trao private key cho sender.
    static byte[] receive(
            Delivery delivery,
            Key recipientPrivateKey,
            String trustedRecipientId,
            String trustedTenant,
            String expectedKeyVersion) throws Exception {
        Objects.requireNonNull(delivery);
        if (!delivery.recipientId().equals(trustedRecipientId)
                || !delivery.tenant().equals(trustedTenant)
                || !delivery.wrappingKeyVersion().equals(expectedKeyVersion)) {
            throw new SecurityException("Recipient context mismatch");
        }
        byte[] label = recipientContext(
                trustedRecipientId, trustedTenant, expectedKeyVersion);
        return oaep(Cipher.DECRYPT_MODE, recipientPrivateKey, label)
                .doFinal(delivery.wrappedDek());
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: recipient tạo keypair; production key có thể ở HSM.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, RNG);
        KeyPair recipientKeys = generator.generateKeyPair();

        Instant now = Instant.parse("2026-11-28T03:00:00Z");
        RecipientBinding fromTrustedRegistry = new RecipientBinding(
                "partner-07", "tenant-42", "v3",
                recipientKeys.getPublic(), now.plusSeconds(600),
                true, true);

        byte[] dek = new byte[32];
        RNG.nextBytes(dek);
        byte[] recovered = null;
        try {
            Delivery delivery = issue(
                    fromTrustedRegistry, "partner-07",
                    "tenant-42", dek, now);
            recovered = receive(
                    delivery, recipientKeys.getPrivate(),
                    "partner-07", "tenant-42", "v3");
            if (!Arrays.equals(dek, recovered)) {
                throw new AssertionError("DEK recovery mismatch");
            }

            // Recipient/tenant metadata bị tráo, giữ nguyên blob RSA.
            Delivery wrongTenant = new Delivery(
                    delivery.recipientId(), "tenant-99",
                    delivery.wrappingKeyVersion(),
                    delivery.wrappedDek());
            boolean blocked = false;
            try {
                receive(wrongTenant, recipientKeys.getPrivate(),
                        "partner-07", "tenant-99", "v3");
            } catch (BadPaddingException expected) {
                blocked = true; // OAEP label không khớp.
            }
            if (!blocked) {
                throw new AssertionError("Wrong recipient context accepted");
            }

            // Sender từ chối cấp DEK cho recipient ID không được duyệt.
            boolean denied = false;
            try {
                issue(fromTrustedRegistry, "attacker-recipient",
                        "tenant-42", dek, now);
            } catch (SecurityException expected) {
                denied = true;
            }
            if (!denied) {
                throw new AssertionError("Untrusted recipient accepted");
            }
            System.out.println("Recipient binding demo: PASS");
        } finally {
            Arrays.fill(dek, (byte) 0);
            if (recovered != null) {
                Arrays.fill(recovered, (byte) 0);
            }
        }
    }
}
~~~

### 13.1. Vì sao ví dụ gắn ngữ cảnh vào OAEP label?

OAEP có tham số **label** được xác minh khi giải mã. Việc tạo label bằng **length-prefixed fields và domain separator** giúp receiver phát hiện một envelope bị gắn sai recipient/tenant/version khi đúng context được kiểm tra. Điều này bổ sung cho chính sách **nhận đúng public key từ registry**.

**OAEP label không phải chữ ký của sender**, không bảo vệ trước kẻ có thể tự tạo một ciphertext mới bằng public key recipient và không thay thế authenticated transport hoặc application authorization. Không mọi vendor/KMS API đều hỗ trợ tùy biến OAEP label; phải kiểm tra interoperability và chuẩn định dạng trước khi dùng.

### 13.2. Những gì code *chưa* bảo đảm

- `identityVerified` và `allowedToReceiveDek` **chỉ là kết quả đáng tin giả lập**, không được nhận nguyên giá trị `true` do client gửi.
- `wrappingPublicKey` trong binding phải **là key đã được PKIX/registry xác minh**, không được đánh tráo thành một public key client gửi sau khi quyết định đã được duyệt. Kiểm tra RSA 3072-bit trong demo chỉ là kiểm tra độ mạnh tối thiểu, không thay certificate validation.
- Mã không kiểm tra PKIX, revocation, PoP, issuer, key usage, trust domain, KMS IAM, approval hay root-KEK export policy; các phần đó nằm trong **policy/PKI/KMS workflow**.
- `permissionExpiresAt` được kiểm tra khi gửi, nhưng không thể **xóa DEK** khỏi thiết bị sau khi đã nhận. Không có replay store/one-time envelope.
- Private key RSA demo được sinh trong JVM, **không phải non-extractable HSM key**.
- Mã dùng `RSA/ECB/OAEPPadding` như tên transformation JCA; “ECB” ở đây thuộc cách đặt tên provider cho RSA, **không phải khuyến nghị AES-ECB**.
- Việc fill mảng `dek` là **best effort**, không bảo đảm mọi bản sao trong JVM/provider được xóa. Production nên hạn chế thời gian tồn tại raw DEK.
- Một bản phân phối production nên dùng **format/protocol chuẩn hóa**, key version/issuer/authenticated sender, rate limit, audit và chính sách xử lý lỗi thống nhất.

## 14. Recipient trong KMS/HSM và envelope encryption

Trong **envelope encryption**, DEK mã hóa dữ liệu bằng AEAD, KEK bảo vệ DEK; recipient có thể được cấp **wrapped DEK hoặc khả năng unwrap**. Việc lựa chọn phụ thuộc vào **ranh giới tin cậy của recipient** và quyền KMS.

~~~mermaid
sequenceDiagram
    participant Requester as Caller / business workflow
    participant Sender as Data service
    participant Registry as Recipient registry + policy
    participant KMS as KMS/HSM giữ KEK
    participant Recipient as Verified recipient
    Requester->>Sender: Xin chia sẻ dữ liệu/DEK
    Sender->>Registry: AuthZ caller, tenant, recipient, purpose
    Registry-->>Sender: Approved identity + public key/version + constraints
    Sender->>Recipient: Authenticated handshake / PoP nếu cần
    Recipient-->>Sender: Identity/capability proof
    Sender->>Registry: Revalidate before distribution
    Registry-->>Sender: Fresh permission + policy revision
    Sender->>KMS: Wrap scoped DEK / issue limited grant
    KMS-->>Sender: Wrapped blob / grant reference
    Sender->>Recipient: Authenticated delivery + bound metadata
    Sender->>Registry: Audit exact key, recipient, scope, outcome
~~~

### 14.1. Phân phối DEK không đồng nghĩa phân phối KEK

Nếu dữ liệu thuộc tenant A và đối tác chỉ cần giải mã một batch, **không trao raw KEK của toàn bộ tenant**. Có thể cấp **DEK giới hạn cho batch đã được wrap cho key recipient** hoặc dùng một capability được giới hạn; phương án cụ thể phụ thuộc kiến trúc và chính sách chia sẻ.

### 14.2. KMS `Unwrap` không tự quyết định record nào thuộc recipient

Một service có thể được KMS cấp quyền `Unwrap` nhưng vẫn phải tuân theo **data owner authorization, tenant binding, classification và purpose**. Nếu service chấp nhận wrapped DEK của caller rồi unwrap vô điều kiện, nó trở thành **confused deputy**.

### 14.3. Encryption context/AAD

Nếu KMS hỗ trợ **encryption context**, dùng context đáng tin để ràng buộc `tenantId`, `purpose`, resource hoặc recipient theo semantics provider. Nếu DEK được wrap bằng AES-KW cơ bản **không có AAD**, phải dùng container/protocol có integrity và authorization để bảo vệ metadata ngữ cảnh.

**Data AAD** của ciphertext AES-GCM là lớp riêng. AAD ở lớp dữ liệu không thay thế authenticated recipient identity khi cấp DEK.

### 14.4. HSM partition và recipient custody

Khi recipient là HSM partition ở một hệ thống khác, cần xác minh **partition identity, target HSM provenance, import/transfer support, exportability và quyền của operator**. Một key được bảo vệ trong HSM nguồn nhưng được import qua một host có raw key **không tương đương HSM-to-HSM secure transfer**.

## 15. mTLS, workload identity và service-to-service distribution

Khi recipient là microservice, **mTLS** thường hữu ích để xác thực hai đầu mối. Nhưng một kết nối mTLS thành công vẫn cần **mapping identity → authorization**:

1. TLS stack kiểm tra trust anchor/certificate chain, validity, key usage và identity theo profile.
2. Ứng dụng lấy **peer identity đã được xác thực** từ TLS/security context đáng tin, không lấy từ header tự khai.
3. Policy engine kiểm tra **recipient service, tenant, audience, purpose, operation và key type**.
4. Nếu phân phối key reference/grant, credential được scope cho workload cụ thể, thời hạn ngắn, key version rõ.
5. Audit liên kết mTLS identity, distribution request, key ID/version và KMS result.

### 15.1. “Ở trong cùng VPC” không phải identity

Private network, VPC, Kubernetes namespace hay source IP **không đảm bảo danh tính mật mã**. DNS/route/service mesh config có thể thay. Cần xác định **TLS endpoint identity**, IAM/workload identity và quyền trên resource/tenant; network isolation là một lớp phòng thủ phụ.

### 15.2. Forward proxy và TLS termination

Nếu TLS kết thúc tại gateway/proxy, backend cần một cách **đáng tin để nhận verified client identity** từ proxy: kết nối nội bộ được bảo vệ, cấu hình xóa header mạo danh, chính sách trust boundary, hoặc cơ chế identity propagation được đánh giá. **Không chấp nhận `X-Recipient-Id` từ Internet chỉ vì proxy cũng đặt header cùng tên.**

### 15.3. Không buộc key distribution phụ thuộc một trường tên khó ổn định

Workload identity có thể là URI SAN, service account, namespace và trust domain; instance ID, pod IP hay hostname có thể thay khi autoscale. Mapping cần phân biệt **identity dài hạn của workload** với **ephemeral instance** và bảo đảm rollout/rotation không vô tình cấp DEK cho workload sai.

## 16. Enrollment, rotation, offboarding: lifecycle của recipient

Recipient cũng có **vòng đời riêng**, không chỉ key material:

~~~mermaid
flowchart TD
    Request[Recipient enrollment request] --> Verify[Identity proofing + key binding]
    Verify --> Policy[Authorize tenant/purpose/key type]
    Policy --> Active[Recipient ACTIVE with exact key version]
    Active --> Rotate[Rotate recipient public key/cert]
    Rotate --> Overlap[Controlled overlap for old envelopes]
    Overlap --> Active
    Active --> Suspended[Suspend / revoke recipient permission]
    Suspended --> Assess[Audit grants, cached secrets, issued envelopes]
    Assess --> Retire[Offboard / expire / destroy per policy]
~~~

### 16.1. Enrollment và key registration

Khi recipient đăng ký public key, yêu cầu **identity proofing**, chứng từ/approval theo risk tier, certificate validation, PoP khi cần, key usage và pinning/registry update audit. **Không cho phép tự thay public key bằng API `PUT /recipient/key` không có authorization mạnh** rồi tiếp tục phát DEK tới key mới.

### 16.2. Recipient public key rotation

Đổi từ `recipient-key/v2` sang `v3` đòi hỏi:

- Xác minh **v3 thuộc cùng recipient hợp lệ** và được phê duyệt cho phân phối mới.
- Công bố `v3` qua registry/channel đáng tin, không chỉ email chứa PEM.
- Chuyển primary cho **new distribution**, nhưng còn hỗ trợ mở envelope cũ bằng `v2` nếu chính sách cho phép.
- Theo dõi **key references trong các envelope đã phát**, retention và khả năng rollback có kiểm soát.
- Thu hồi/revoke `v2` nếu lộ; không dùng overlap trong trường hợp compromise.

### 16.3. Offboarding recipient

Khi đối tác hết hợp đồng:

1. Ngừng cấp grant/wrapped DEK mới cho recipient.
2. Revoke KMS IAM/grants, tokens, certificate/trust binding khi phù hợp.
3. Xác minh **các bản sao secret đã phát hoặc cache** mà recipient vẫn có thể giữ.
4. Đánh giá DEK/KEK và dữ liệu cần **rotate/re-encrypt** để giảm quyền truy cập tương lai.
5. Bảo vệ các bản backup và nghĩa vụ retention, báo cáo sự cố/termination theo hợp đồng.

**Revocation không tự thu hồi secret đã được recipient nhận dạng rõ**. Nếu họ có DEK và ciphertext cũ, họ có thể còn khả năng giải mã dữ liệu tương ứng, bất kể IAM của sender đã chặn.

## 17. Multi-recipient distribution: nhiều bên nhận cùng dữ liệu

Một tài liệu được chia sẻ cho ba tổ chức có thể được mã hóa **một lần bằng DEK**, rồi DEK được wrap **riêng cho từng recipient public key**. Thiết kế có thể gồm:

~~~text
              AEAD_Encrypt(DEK, document)
                       |
                   Ciphertext
                       |
        +--------------+---------------+
        |              |               |
 Wrap DEK cho A   Wrap DEK cho B   Wrap DEK cho C
  public key A     public key B      public key C
        |              |               |
  Wrapped DEK A    Wrapped DEK B     Wrapped DEK C
~~~

### 17.1. Điều gì phải kiểm tra cho từng recipient?

**Mỗi recipient phải được kiểm tra riêng**: danh tính, key version, key usage, policy scope, expiry và trust status. Một recipient hợp lệ không cho phép nhân bản wrapped DEK cho mọi tên có trong danh sách người nhận. Nên dùng **domain/context binding** để mỗi encrypted key entry gắn với đúng intended recipient.

### 17.2. Bổ sung recipient mới

Nếu DEK không bị lộ và policy cho phép, hệ thống có thể wrap **cùng DEK** cho recipient mới mà không mã hóa lại dữ liệu. Nhưng việc này **mở rộng số bên có thể giải mã toàn bộ ciphertext dưới DEK**, nên phải có data owner approval, audit và hiểu rõ blast radius.

### 17.3. Loại bỏ recipient

Xóa wrapped DEK của recipient A trong database **không làm A mất khả năng đọc bản sao cũ đã tải về**. Nếu cần chặn việc đọc dữ liệu **trong tương lai**, hãy cân nhắc **DEK mới, re-encrypt**, tách tài liệu thành phiên bản mới và ngừng phát ciphertext mới cho A. Dữ liệu A đã sở hữu trước đó không thể bị xóa từ xa chỉ nhờ mật mã.

### 17.4. Tránh dùng một PSK chung cho nhiều recipient

PSK chung cho nhiều hệ thống gây khó khăn khi một recipient bị lộ/thu hồi; mọi recipient khác có thể phải đổi khóa. Với thiết bị/đối tác, ưu tiên **secret/key riêng theo recipient** hoặc giao thức authenticated key establishment phù hợp, trừ khi thiết kế nhóm/multicast có cơ chế quản lý thành viên riêng đã được đánh giá.

## 18. Attestation và tình trạng an toàn của recipient

Trong một số môi trường, chỉ xác nhận “đúng danh tính” chưa đủ. Chính sách có thể yêu cầu recipient giữ private key trong **TPM, HSM, secure enclave hoặc trusted execution environment**.

**Remote attestation** có thể hỗ trợ đánh giá cấu hình/hardware boundary và trạng thái đo lường theo mô hình thiết bị, nhưng phải biết:

- Attestation evidence gắn với **thiết bị/instance hoặc key nào**?
- Root of trust, verifier, freshness/nonce và measurement policy có đáng tin không?
- Report có chứng minh private key nhận DEK **không xuất được** không, hay chỉ chứng minh image/firmware?
- Có bind giữa **attested key, recipient identity và public encryption key** không?
- Tại lúc phân phối, attestation còn mới và không thuộc bản bị revoke không?

**Attestation không tự trao quyền truy cập dữ liệu** và không bảo vệ sau khi recipient hợp lệ cố tình copy plaintext ra ngoài. Nó là **tín hiệu assurance** bổ sung; identity, authorization và protocol binding vẫn cần thiết.

### 18.1. Đừng lạm dụng soft assumptions

Một virtual HSM có thể là hardware-backed partition hoặc software token trên VM. Thấy API PKCS#11 hoạt động **không chứng minh** recipient đang giữ private key trong hardware security boundary. Cần evidence từ provider/thiết bị và chính sách xác minh phù hợp.

### 18.2. Khi không có attestation

Không tự khai `recipientAttested=true` chỉ vì ứng dụng gửi một certificate hợp lệ. Nếu risk tier không yêu cầu attestation, có thể ghi **`NOT_REQUIRED`**; nếu yêu cầu mà không có bằng chứng, phải **deny** hoặc dùng quy trình exception được phê duyệt.

## 19. Audit và bằng chứng quyết định recipient

Đối với một distribution request quan trọng, audit tối thiểu nên trả lời:

| Nhóm bằng chứng | Thuộc tính nên có |
| --- | --- |
| **Ý định** | `requestId`, key ID/version/class, purpose, tenant/data scope |
| **Requester** | Authenticated principal, quyền trên dữ liệu, approval reference |
| **Recipient** | ID/trust domain, type, verified public key fingerprint/version |
| **PKI/identity** | Issuer/trust profile, cert serial/fingerprint, validation status/expiry |
| **Authorization** | Policy revision, role constraints, decision, approver/quorum khi cần |
| **Issuance** | KMS/HSM operation ID, wrapping mechanism, grant scope và TTL |
| **Delivery** | Channel type, recipient endpoint identity, receipt/ack, retry/reconcile state |
| **Lifecycle** | Recipient/key rotation, revoke/offboarding, dependent envelopes |
| **Kết quả** | Success/deny, error class, timestamp/clock source, audit integrity |

### Event JSON minh họa

~~~json
{
  "eventType": "KEY_DISTRIBUTION_ISSUED",
  "requestId": "dist-20261128-0012",
  "requesterPrincipal": "billing-exporter",
  "recipientId": "partner-acquirer-07",
  "recipientTrustDomain": "partner-registry-approved",
  "recipientKeyId": "partner-07-encryption",
  "recipientKeyVersion": "v3",
  "recipientKeyFingerprint": "sha256:<public-key-digest>",
  "recipientVerification": "PKIX_AND_POLICY_VERIFIED",
  "keyClass": "DEK",
  "tenantScope": "production/tenant-42",
  "purpose": "SETTLEMENT_EXPORT",
  "wrappingMechanism": "RSA-OAEP-SHA256",
  "senderKeyRef": "data-dek-batch-08",
  "policyRevision": 17,
  "recipientApprovalRef": "recipient-approval-1093",
  "kmsOperationRef": "kms-wrap-9032",
  "deliveryState": "DELIVERED",
  "recordedAt": "2026-11-28T03:00:00Z"
}
~~~

Các giá trị chỉ minh họa. `PKIX_AND_POLICY_VERIFIED` phải dựa trên **chứng cứ validation và quyết định thật**; không điền nhãn thành công nếu chưa kiểm tra revocation/identity theo policy. `senderKeyRef` trong ví dụ là **tham chiếu DEK**, không phải bí mật.

### 19.1. Audit an toàn không chứa key material

**Không log** private key, raw DEK/KEK/PSK, unwrapped secret, plaintext, PIN, bearer token, challenge secret hoặc dữ liệu nhạy cảm của đối tác. Public-key fingerprint, tenant ID và recipient metadata vẫn có thể là **thông tin nhạy cảm về cấu trúc/tần suất giao dịch**: phân quyền đọc, retention và redaction phù hợp.

### 19.2. Integrity của evidence

Một field `status=VERIFIED` có thể bị sửa nếu attacker có quyền ghi audit/inventory. Dùng **protected append-only log, signed events/hash-chain với trust anchor phù hợp, kiểm tra provider audit độc lập và quyền sửa tách vai**. SHA-256 digest của một bản ghi **không tự bất biến** nếu attacker sửa được cả record và digest.

### 19.3. Vết thời gian và cryptoperiod

Nên tách `requestedAt`, `validatedAt`, `issuedAt`, `deliveredAt` và `acknowledgedAt` (nếu có). Phân phối có thể được **chấp thuận** trước khi recipient key bị revoke nhưng **thực thi** sau đó; chỉ audit thời điểm approve sẽ che giấu TOCTOU. Mốc thời gian theo UTC/nguồn clock đáng tin, liên kết request/provider operation ID.

## 20. Idempotency, retry và delivery failure

Một distribution service có thể phát hành một wrapped DEK/grant thành công nhưng **network response bị mất**. Retry sai có thể cấp nhiều grants, phát lại secret hết hạn hoặc khiến audit nói “FAIL” dù recipient đã nhận.

### 20.1. State machine gợi ý

~~~text
RECEIVED
  -> AUTHENTICATED
  -> RECIPIENT_VERIFIED
  -> AUTHORIZED
  -> WRAPPED_OR_GRANTED
  -> DELIVERY_ATTEMPTED
  -> DELIVERED / ACKNOWLEDGED
  -> CLOSED

Từ bất kỳ bước nào:
  DENIED / EXPIRED / REVOKED / NEEDS_RECONCILIATION
~~~

Không coi `DELIVERED` đồng nghĩa recipient đã sử dụng secret đúng mục đích hoặc đã xóa bản sao tạm thời. `ACKNOWLEDGED` chỉ là một bằng chứng giao thức hoặc nghiệp vụ tùy thiết kế.

### 20.2. Những bất biến khi retry

- `requestId` ổn định và request payload được **canonicalize/hash**, chống thay recipient hay key version.
- Trước retry, kiểm tra **recipient vẫn active**, grant chưa revoke và policy revision còn hợp lệ.
- Khi KMS API hỗ trợ **idempotency token**, sử dụng theo semantics thật; nếu không, query operation state trước khi tạo thêm grant.
- Không gửi raw DEK vào queue/dead-letter queue chỉ để “đảm bảo không mất message”.
- Không thay recipient key version một cách im lặng giữa các lần retry; nếu registry đổi key, **re-authorize và bind lại request**.
- Không trả plaintext/wrapped key cho caller không có quyền xem kết quả.

### 20.3. Recipient không phản hồi

Một client offline có thể không nhận envelope trong thời hạn; đừng giữ quyền raw secret vô hạn. Có thể cho **expiry, retry limit, queued encrypted blob với recipient binding, revocation check trước resend** và chính sách archival. Không dùng recipient certificate đã hết hạn để gửi lại chỉ vì job được tạo từ tuần trước.

## 21. Tình huống thực tế: phân phối DEK cho đối tác thanh toán

Giả sử một SaaS có nhiều tenant chia sẻ một tập dữ liệu hóa đơn với đối tác `Acquirer-07` để đối soát. Mỗi batch được mã hóa bằng **DEK AES-256**, DEK được bảo vệ trong KMS/HSM và chỉ nên được phát cho đối tác đúng hợp đồng.

### Giai đoạn A — Enrollment recipient

Nhóm Partner Operations xác thực tổ chức, **recipient owner và đầu mối liên lạc**. Security kiểm tra certificate chain, URI SAN, algorithm/key usage, issuer/trust profile và bằng chứng PoP khi yêu cầu. Một **trusted registry** ghi `recipientId`, public encryption key/version, tenant scope, purpose, expiry và approval reference.

**Không nhận PEM mới từ email** rồi thay registry trực tiếp nếu không có quy trình xác minh danh tính/ký duyệt độc lập; đây là đường public-key substitution quen thuộc.

### Giai đoạn B — Yêu cầu xuất dữ liệu

Billing requester tạo batch cho `tenant-42`. Data owner phê duyệt mục đích `SETTLEMENT_EXPORT`; Key owner xác nhận **chỉ DEK của batch**, không phải root KEK, được phân phối. Policy engine kiểm tra partner đang Active, được phép nhận đúng tenant/classification và key version recipient phù hợp.

### Giai đoạn C — Wrap và gửi

Service mã hóa payload bằng AEAD với nonce/AAD; DEK được wrap cho public key recipient đã xác minh hoặc qua cơ chế chuẩn được phê duyệt. Envelope mang recipient ID/key version, batch/resource ID, purpose, policy revision và thời gian; metadata nhạy cảm được bảo vệ toàn vẹn. Dữ liệu được gửi qua **authenticated TLS/mTLS**.

### Giai đoạn D — Phát hiện thao tác tráo khóa

Một attacker chiếm tài khoản support, gửi yêu cầu thay `Acquirer-07` public key bằng khóa của họ. Nếu hệ thống chỉ kiểm tra định dạng public key, DEK có thể bị mã hóa cho attacker. Với quy trình đúng, key update yêu cầu **identity proofing lại, approved signer, key binding, PoP, review độc lập và audit**, nên request bị từ chối hoặc treo chờ xác minh.

### Giai đoạn E — Rotation và offboarding

Đối tác đổi encryption key từ `v3` sang `v4`. New batch chỉ dùng `v4` sau khi validation; envelope cũ vẫn tham chiếu `v3` theo retention. Khi hợp đồng kết thúc, SaaS **ngừng gửi mới, thu hồi KMS grants, key registry binding**, đánh giá DEK đã chia sẻ và chuẩn bị re-encrypt dữ liệu tương lai nếu cần.

**Không thể bảo đảm đối tác mất khả năng đọc một batch đã được trao DEK trước đó** chỉ bằng xóa quyền KMS của sender. Phải có data sharing/retention agreement và thiết kế key scope/cryptoperiod ngay từ đầu.

## 22. Sự cố bảo mật: phản ứng khác nhau theo loại compromise

| Sự cố | Điều phải phân loại | Phản ứng chính |
| --- | --- | --- |
| **Recipient private key bị lộ** | Những wrapped DEK/envelopes nào đã được gửi cho key đó? | Revoke key binding/grants, ngừng phát, đánh giá DEK mới/re-encrypt và ciphertext cũ |
| **Recipient endpoint bị chiếm** | Plaintext/DEK/cached secrets đã được đọc chưa? | Cô lập endpoint, thu hồi credentials, đánh giá dữ liệu |
| **Public key registry bị sửa** | Key nào đã bị tráo, từ thời điểm nào, những DEK nào bị wrap sai? | Đóng enrollment, khôi phục binding, rà audit, thông báo/rotate |
| **Certificate revocation chưa lan** | Những sender vẫn dùng certificate/key cũ? | Cập nhật trust/cache, block at issuance, negative test |
| **KMS unwrap principal bị chiếm** | Raw DEK nào được trả về qua API? | Revoke principal, kiểm tra log, thay DEK/re-encrypt khi cần |
| **Raw KEK bị lộ** | Attacker có wrapped DEK, backups, ciphertext nào? | Thay KEK, đánh giá DEK cũ/copy của attacker, không chỉ rewrap |
| **Wrong tenant distribution** | Recipient có nhận secret/ciphertext tenant khác? | Containment, đánh giá phạm vi, rotate DEK và thông báo theo quy trình |
| **Replay grant/token** | Quyền có được dùng lại ngoài TTL/scope? | Invalidate grants, replay store, protocol binding và audit |

### 22.1. Giới hạn của revoke sau khi đã cấp raw secret

Một recipient đã nhận **raw DEK** và bản ciphertext có thể giữ bản sao của cả hai. Hủy certificate, đổi key alias, revoke IAM hoặc xóa envelope ở phía gửi **không thể xóa byte đã có trong tay recipient**. Nếu cần hạn chế truy cập tương lai, tạo **DEK mới và ciphertext mới**, không gửi cho recipient đã bị thu hồi, rồi bảo vệ các bản snapshot/backup theo retention.

### 22.2. Không “rewrap là xong” khi recipient key bị lộ

Nếu attacker lấy private encryption key của recipient và những wrapped DEK cũ, họ vẫn có thể unwrap bản cũ. Wrap lại DEK đó cho public key recipient mới **không làm attacker mất DEK cũ**. Đánh giá **DEK mới + re-encrypt** và sự cố dữ liệu đã thu thập; không tuyên bố phục hồi bí mật quá mức.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tin public key do caller tự upload là key của recipient đã duyệt | Public-key substitution | Trusted PKI/registry, binding và enrollment approval |
| Chỉ validate certificate chain, không kiểm tra SAN/identity | Gửi cho recipient khác nhưng cùng CA | Exact expected identity matching |
| Không kiểm tra EKU/key usage | Dùng key sai purpose/protocol | Certificate profile, allowlisted algorithm/usage |
| Tắt TLS hostname verification | MITM | TLS stack xác thực expected peer |
| Coi mTLS = quyền đọc mọi tenant | Confused deputy và cross-tenant | Separate resource authorization và KMS policy |
| Không kiểm tra CRL/OCSP/status | Chấp nhận key đã revoke | Revocation policy và failure mode theo risk |
| Dùng cert hết hạn vì cache vẫn giữ | Phát DEK cho key stale | Revalidate gần issuance, TTL cache |
| Chỉ proof of possession, bỏ kiểm tra danh tính | Attacker tự ký challenge và pass | PoP + verified identity binding + authz |
| Tái dùng signing key làm wrapping key trái policy | Cross-protocol misuse | Key separation và purpose-bound profile |
| Gửi raw KEK khi recipient chỉ cần DEK | Blast radius nghiêm trọng | Scoped wrapped DEK/KMS grant |
| Gửi secret bằng email/chat/log | Khả năng phát tán vô hạn | Authenticated protected distribution channel |
| Chỉ lưu alias `current` | Sai key version khi rotation | Exact key ID/version và provider reference |
| Không bind tenant/purpose/recipient vào envelope | Tráo context hoặc cấp nhầm quyền | AEAD context, standard authenticated format |
| Dùng AES-KW rồi tuyên bố tự có recipient AAD | Sai giả định về binding | Protocol metadata integrity + policy checks |
| Chỉ dùng expiration trong JSON header | Recipient vẫn decrypt sau expiry | Enforce TTL/grants và thừa nhận giới hạn secret đã phát |
| Retry sau timeout mà không reconcile | Cấp grant trùng hoặc phát sai key | Idempotency, operation tracking, revalidation |
| Một account quản lý registry, approve và cấp grant | Không có independent control | SoD/quorum khi cần, audit độc lập |
| Tự gán `attested=true` khi chưa kiểm chứng | Sai boundary assurance | Evidence chain và policy verifier |
| HSM key non-exportable nên bỏ app authorization | API misuse | Least privilege, transaction authorization, monitoring |
| Rewrap DEK cho recipient mới sau khi key cũ lộ | Attacker vẫn có bản DEK cũ | Đánh giá re-encrypt dữ liệu bằng DEK mới |
| Chỉ log success/fail không có recipient key version | Không điều tra được distribution sai | Key binding, policy revision, evidence/receipt |
| Lưu raw DEK trong audit để “chứng minh đã gửi” | Tạo lỗ hổng lộ secret mới | Log references/status, không log key material |
| Chờ quorum chặn mọi thao tác khẩn cấp | Attacker tiếp tục nhận secret | Break-glass containment có phạm vi hẹp và hậu kiểm |

## 24. Checklist triển khai recipient verification

- [ ] Đã xác định recipient là **người, workload, device, partner hay KMS/HSM partition**, và đối tượng được cấp là key material hay capability?
- [ ] Đã threat-model **MITM, public-key substitution, cross-tenant, API misuse, replay và TOCTOU**?
- [ ] Recipient ID đến từ **trusted registry/identity provider**, không tự lấy từ untrusted request?
- [ ] Có phân biệt **authentication, key-to-identity binding, PoP và authorization**?
- [ ] Public key/cert được xác minh **đúng trust anchor, chain, SAN/URI/DNS, key usage/EKU, validity và revocation**?
- [ ] Algorithm, key size/curve, protocol và `recipientKeyVersion` được allowlist theo profile?
- [ ] Nếu cần PoP, challenge có nonce CSPRNG, TTL, domain/request binding và chống replay?
- [ ] Không dùng PoP thay cho **identity proofing hoặc quyền trên tenant/data**?
- [ ] Thay recipient key/certificate có **enrollment approval, registry versioning, audit và review**?
- [ ] Trước phát hành có kiểm tra **requester identity, data owner policy, key owner rules, tenant/resource và purpose**?
- [ ] Có revalidate recipient state, authorization và key version **gần lúc wrap/cấp grant**?
- [ ] Chỉ gửi **wrapped DEK hoặc scoped KMS grant** khi có thể; không xuất raw KEK trái policy?
- [ ] Wrapped envelope dùng **approved mechanism/standard format** và bind recipient/tenant/purpose/key version?
- [ ] Encryption context/AAD được lấy từ metadata đáng tin và được kiểm tra lúc nhận/unwrap?
- [ ] Transport dùng authenticated TLS/mTLS hoặc protocol tương đương, **không tắt identity verification**?
- [ ] Recipient private key được giữ trong vùng bảo vệ phù hợp, attestation được kiểm tra nếu policy yêu cầu?
- [ ] Multi-recipient distribution có **approval riêng từng recipient**, không phát PSK/KEK chung tùy tiện?
- [ ] Có TTL/grant scope, replay defense, idempotency và kiểm soát resend khi recipient offline?
- [ ] Không ghi raw DEK/KEK/PSK, PIN, bearer token hoặc plaintext vào log/queue/trace?
- [ ] Audit liên kết **requester, recipient, key ID/version, key fingerprint, policy revision, provider operation và result**?
- [ ] Khi recipient offboard hoặc key compromise, có **revoke/containment, cache invalidation và đánh giá DEK đã phát**?
- [ ] Có negative tests **wrong SAN, wrong tenant, expired cert, revoked key, changed public key, replay, wrong policy revision và direct bypass**?
- [ ] Đã đánh giá **cryptoperiod, rotation, envelope dependencies, backup/retention và key inventory** xuyên suốt?
- [ ] Có runbook khi một recipient từng nhận raw DEK và **revocation không thể xóa secret đã có**?

## 25. Câu hỏi tự kiểm tra

**1. Recipient verification có chỉ là kiểm tra certificate hợp lệ không?**  
Không. Cần xác thực danh tính, xác minh key-to-identity binding, quyền nhận đúng key/data/tenant, thời hạn/trạng thái và kênh/cơ chế phân phối.

**2. Tại sao một public key RSA hợp lệ vẫn có thể nguy hiểm?**  
Nó có thể thuộc attacker hoặc recipient không có quyền. Nếu sender wrap DEK cho key sai, mật mã hoạt động đúng nhưng secret đến sai người.

**3. PKIX path validation thành công có cấp quyền đọc dữ liệu cho recipient không?**  
Không. Nó là một phần của xác thực chứng thư/trust; authorization theo tenant, purpose, key class và resource phải được kiểm tra riêng.

**4. PoP chứng minh điều gì?**  
Một chủ thể có khả năng dùng key/credential tương ứng với proof, theo giao thức. Nó không tự chứng minh đúng danh tính tổ chức, được ủy quyền hoặc key nằm trong HSM.

**5. Vì sao không thể chỉ dựa vào hostname/IP của recipient?**  
DNS, route, proxy và IP có thể thay hoặc bị cấu hình sai. Cần authenticated peer identity, certificate validation và mapping tới quyền đúng.

**6. Khi nào nên dùng KMS grant thay vì gửi raw KEK?**  
Khi recipient chỉ cần dùng một operation hợp lệ trên key trong KMS; grant scope/TTL và IAM giúp tránh phát tán vật liệu KEK gốc.

**7. AES-KW có tự bind tenant hoặc recipient ID không?**  
Không theo dạng cơ bản. Cần protocol/header integrity, trusted context/authorization hoặc wrapping mechanism hỗ trợ AAD theo thiết kế.

**8. Nếu recipient cert bị revoke sau khi approval nhưng trước lúc wrap, làm gì?**  
Phải revalidate gần lúc thực thi, từ chối phát hành và yêu cầu xử lý key rotation/approval mới. Không dùng approval cũ như giấy phép vĩnh viễn.

**9. Vì sao không nên dùng cùng private key cho PoP signing và DEK unwrap?**  
Key usage khác nhau và có thể tạo cross-protocol misuse; ưu tiên key separation và profile/giao thức đã được phê duyệt.

**10. Một recipient đã nhận DEK bị offboard. Revoke KMS có làm họ quên DEK không?**  
Không. Nếu họ còn DEK và ciphertext, họ có thể tiếp tục giải mã bản đã có. Cần thiết kế phạm vi DEK, rotation/re-encrypt dữ liệu tương lai và nghĩa vụ bảo mật/retention.

**11. Vì sao cần exact recipient key version thay vì `current`?**  
Alias có thể đổi trong rotation, làm approval và thực tế wrap lệch nhau; envelope cũ còn cần key version cụ thể để unwrap đúng.

**12. Khi có nhiều recipient cùng nhận một DEK, loại bỏ một recipient có dễ không?**  
Không. Họ có thể đã giữ DEK và ciphertext. Ngừng phát mới, đánh giá key scope và cân nhắc DEK mới/re-encrypt cho dữ liệu về sau.

**13. Recipient key trong HSM không xuất được có làm mọi request an toàn không?**  
Không. Một principal bị chiếm có thể gọi API hợp lệ để unwrap/decrypt, hoặc host có thể nhận plaintext/DEK trong bộ nhớ theo thiết kế. Cần IAM, operation authorization và audit.

**14. Tại sao OAEP label hoặc AAD không thay authenticated sender và replay protection?**  
Chúng bảo vệ context ở lớp mật mã tương ứng, nhưng không tự xác minh ai tạo message hay ngăn phát lại ciphertext hợp lệ. Cần identity/protocol authentication và replay state phù hợp.

**15. Trong sự cố private key recipient bị lộ, chỉ đổi public key mới và rewrap DEK có đủ không?**  
Không mặc nhiên. Attacker có thể giữ private key cũ và wrapped DEK cũ; cần đánh giá DEK mới/re-encrypt và dữ liệu đã bị đọc.

## Ghi nhớ

**Kiểm tra recipient là bước bắt buộc trước khi phân phối khóa hoặc cấp khả năng sử dụng khóa.** Một recipient an toàn phải được xác minh về **danh tính, quyền trên dữ liệu, public-key/certificate-to-identity binding, key usage/algorithm, trạng thái thu hồi, thời hạn và ngữ cảnh nhận**. Certificate chain hợp lệ, PoP thành công hay mTLS kết nối được **không tự bảo đảm authorization**. Trong thực tế, cần kết hợp **trusted registry/PKI, IAM, key owner/data owner approvals, KMS/HSM, authenticated distribution protocol, exact key versions, context binding, chống replay và audit**; kiểm tra lại gần lúc thực thi để tránh TOCTOU. Đồng thời, quản lý **enrollment, rotation, offboarding, cryptoperiod, DEK/KEK, envelope encryption, PSK, key agreement, backup và incident response**. Một bí mật được mã hóa hoàn hảo nhưng gửi cho **người nhận sai** vẫn là một sự cố lộ khóa.
