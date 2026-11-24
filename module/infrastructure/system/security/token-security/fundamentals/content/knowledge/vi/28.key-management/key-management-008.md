# Key revocation

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **key revocation** trong quản lý token: vô hiệu khả năng **dùng khóa để ký/mã hóa/xác thực** và/hoặc rút **niềm tin của verifier** đối với khóa bị thu hồi.
- Phân biệt **key rotation có kế hoạch**, **disable signing key**, **revoke verification trust**, **token revocation** và **certificate revocation**; không dùng những thuật ngữ này thay nhau.
- Phân tích tác động khi **HMAC secret HS256**, **private signing key RSA/ECDSA/EdDSA**, **client authentication key**, **mTLS certificate key**, **DPoP key** hoặc key mã hóa bị xâm phạm.
- Mô tả cách **JWKS**, metadata issuer, **kid**, JWK thumbprint, key status và các cache ở Resource Server (RS) ảnh hưởng đến khả năng từ chối JWT.
- Thiết kế quy trình khẩn cấp: phát hiện → cô lập → ngừng ký → rút trust → thay khóa → ngăn token giả → kiểm chứng tại từng RS → điều tra và phục hồi.
- Hiểu giới hạn của **RFC 7009 token revocation**, **RFC 7662 introspection**, **CRL/OCSP** và các API **DisableKey/DeleteKey** của HSM/KMS đối với key revocation.
- Thiết lập kiểm soát **admin authentication, dual control, key registry, event propagation, fail-closed, rollback an toàn, audit và SLO**.
- Xây dựng negative tests, Java/Spring pseudocode, sơ đồ Mermaid và checklist cho hệ thống OAuth 2.0/OIDC thực tế.

## 1. Key revocation là gì?

Trong OAuth 2.0/OIDC, Authorization Server (AS) có thể ký **JWT access token**, **OIDC ID token** hoặc các JWT assertions bằng một **signing key**. Resource Server hoặc Relying Party (RP) xác minh chữ ký bằng khóa tương ứng.

**Key revocation** là quyết định và hành động quản trị nhằm **chấm dứt quyền sử dụng hoặc quyền tin cậy đối với một khóa** khi khóa không còn hợp lệ về chính sách, bị nghi lộ, bị sử dụng sai hoặc phải rút khỏi hệ thống.

Với signing key bất đối xứng, cần tách hai việc:

1. **Ngừng ký mới (stop signing):** AS/HSM/KMS không còn dùng private key K-old để tạo chữ ký JWT.
2. **Ngừng xác minh/tin cậy (remove verification trust):** các RS/RP không còn chấp nhận chữ ký gắn với K-old, kể cả với token chưa hết hạn, nếu chính sách incident yêu cầu.

Ví dụ:

~~~text
10:00  AS ký JWT T bằng private key K-old.
10:05  Security admin disable K-old ở KMS.
10:06  Attacker vẫn có bản private K-old đã bị lộ.
10:07  Orders RS còn cache public K-old từ JWKS.
10:08  Attacker tự ký JWT giả bằng K-old.
10:09  Orders RS có thể nhận JWT giả nếu vẫn tin K-old.
~~~

**DisableKey tại KMS không thu hồi public verification key đã được RS lưu trong cache.** Một triển khai chỉ ngừng ký ở AS chưa chắc ngăn token giả.

### Key revocation không nhất thiết nói về một token cụ thể

Nếu một JWT T bị lộ nhưng private signing key vẫn an toàn, thường cần xử lý **token revocation/denylist**, không nhất thiết phải rút khóa ký của cả issuer.

Ngược lại, nếu **private signing key** bị lộ, kẻ tấn công có thể tạo nhiều JWT giả với **jti, sub, scope, exp** tự chọn trong giới hạn được parser chấp nhận. Chặn riêng jti của T không đủ; phải xử lý **trust anchor** là key.

## 2. Trust boundary của signing key

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Yêu cầu Sign sau kiểm grant/scope"| HSM["HSM/KMS: private signing key"]
    HSM -->|"Signature"| AS
    AS -->|"Signed JWT"| C["OAuth Client"]
    C -->|"Bearer JWT"| RS["Orders Resource Server"]
    JWKS["JWKS tin cậy: public verification key"] -->|"Public key, kid"| RS
    RS --> AUTH["Verify signature và kiểm iss/aud/exp/scope"]
    ADM["Security Admin"] -->|"Disable signing"| HSM
    ADM -->|"Revoke verification trust"| REG["Key trust registry / policy"]
    REG -->|"Trusted revocation state"| RS
~~~

Bảng phân chia trách nhiệm:

| Thành phần | Điều nó kiểm soát | Điều không được mặc định |
| --- | --- | --- |
| **AS Token Service** | Quyết định phát token, chọn active signing key và claims. | Một key có thể ký mọi token type/issuer không giới hạn. |
| **HSM/KMS** | Lưu key, thực thi Sign/Disable theo IAM và key policy. | Disable Sign tự sửa mọi JWKS/verifier cache. |
| **JWKS Publisher** | Phân phối **public verification keys** theo issuer. | Gỡ key khỏi JWKS khiến RS offline lập tức quên key. |
| **RS/RP** | Chỉ tin keys thuộc issuer/profile hợp lệ, verify chữ ký và claims. | Token đúng chữ ký vẫn luôn được phép truy cập. |
| **Key/Incident Administrator** | Phê duyệt, thực thi rút khóa và theo dõi propagation. | Có thể yêu cầu mọi RS chấp nhận trạng thái mới mà không cần bằng chứng. |
| **OAuth Client** | Gửi token đến intended resource. | Biết kid hoặc public key là có quyền phát token. |

**Ranh giới quan trọng:** một JWT self-contained có chữ ký được RS verify **offline**. AS không tham gia ở mỗi request. Vì vậy AS không có một “công tắc từ xa” tự động thu hồi toàn bộ JWT tại RS nếu RS chưa thiết kế cơ chế cập nhật trust/state.

## 3. Rotation, revocation và destruction khác nhau thế nào?

| Thao tác | Hành vi | Khi nào dùng | Tác động với JWT cũ |
| --- | --- | --- | --- |
| **Rotate bình thường** | Sinh K-new, ngừng ký K-old, tiếp tục giữ public K-old đến lúc token cũ hết hạn. | Lịch thay khóa, cải tiến thuật toán, giới hạn tuổi khóa. | JWT cũ có thể tiếp tục hợp lệ theo exp/policy. |
| **Disable Sign** | Ngăn AS/KMS dùng private K-old để ký token mới. | Dừng sử dụng hoặc bước containment ban đầu. | JWT cũ vẫn có thể được RS verify bằng public K-old. |
| **Revoke verification trust** | RS/RP từ chối chữ ký bằng K-old theo trạng thái/registry đáng tin. | Key bị compromise, sử dụng sai, thay đổi policy bắt buộc. | Có thể vô hiệu hàng loạt JWT **trước exp**. |
| **Revoke token/grant** | Chặn token cụ thể hoặc các token/issuance theo grant. | Token theft, RT reuse, account compromise. | Phụ thuộc denylist/introspection và RS cache. |
| **Destroy private key** | Xóa key material/capability theo quy trình. | Sau lifecycle/retention hoặc sự cố phù hợp. | Không xóa các bản đã bị attacker copy hoặc public key ở RS. |
| **Revoke certificate** | CA/tổ chức đánh dấu certificate không còn được tin qua CRL/OCSP/policy. | mTLS/TLS/PKI dựa trên X.509. | Chỉ có tác dụng nếu verifier thực sự kiểm chain/revocation theo profile. |

### Routine rotation và emergency revocation

Trong **rotation có kế hoạch**, giữ K-old trong verify-only state giúp token hợp pháp tiếp tục hoạt động. Khi K-old **đã bị lộ private component**, giữ trust để tránh downtime có thể cho attacker forge JWT.

~~~text
Routine:
    K-new = ACTIVE_SIGNING
    K-old = VERIFY_ONLY -> RETIRED sau token TTL

Compromise:
    K-old = SIGN_DISABLED + TRUST_REVOKED
    K-new = ACTIVE_SIGNING nếu đã an toàn và RS sẵn sàng
    RS không được tiếp tục verify bằng K-old
~~~

Không mặc định rằng key revocation luôn phải vô hiệu toàn bộ session, grant hoặc refresh token. Ngược lại, **chặn chữ ký cũ không chặn attacker tiếp tục xin token mới** nếu credential/grant gốc cũng bị lộ. Scope incident cần được phân tích riêng.

## 4. Khi nào một key cần bị revoke?

Các tình huống phổ biến:

- **Private signing key** bị công bố trong repository, backup, container image, log, ticket hoặc kênh đối tác.
- **HMAC secret HS256** bị rò từ AS hoặc một RS có quyền verify.
- HSM/KMS **Sign permission** bị chiếm dụng hoặc signer bị lạm dụng để ký claims ngoài policy.
- Thay đổi **trusted issuer/key ownership**, key được cấp sai purpose hoặc thuật toán không còn được chấp nhận.
- Phát hiện key tạo từ **RNG yếu/seed cố định**, key size quá thấp hoặc lỗi nonce ECDSA có nguy cơ lộ private key.
- Key của **OAuth client** dùng private_key_jwt bị mất quyền kiểm soát; có thể cần revoke client authentication key.
- **mTLS certificate/key** của một workload bị lộ; cần xử lý cả trust certificate và token ràng certificate.
- **DPoP key** của client bị lấy cắp; access tokens ràng với key có thể phải bị thu hồi.
- Key bị dùng trái phép dù **raw private key chưa được xác định đã thoát ra ngoài**.

### Phân loại bằng chứng và phạm vi

| Sự kiện | Khả năng attacker | Biện pháp chính |
| --- | --- | --- |
| Một **Bearer AT** bị copy | Replay token còn hạn; không nhất thiết ký JWT mới. | Revoke AT/grant theo phạm vi, không mặc định revoke signing key. |
| **AS private key** bị copy | Ký JWT giả tùy ý trong phạm vi thuật toán/trust được RS chấp nhận. | Emergency revoke signing/verification trust, rotate key và điều tra. |
| **RS public key** bị công bố | Public key vốn có thể công khai, không tự cung cấp signing ability. | Không revoke chỉ vì public key bị đọc; kiểm thêm nếu có dấu hiệu key spoofing. |
| **HS256 secret** ở RS bị lộ | Forge HMAC JWT cho nơi cùng tin secret. | Revoke/rotate shared secret tại mọi verifier liên quan. |
| Chỉ **KMS Sign IAM role** bị lạm dụng | Có thể yêu cầu ký nhưng chưa chắc đã xuất private bytes. | Chặn caller, điều tra issued signatures, xem xét thay key nếu không cô lập được rủi ro. |
| **Client private_key_jwt key** bị lộ | Giả mạo OAuth client authentication với AS. | Revoke client key/trust, credential recovery và xử lý AT/grant liên đới. |
| **CA/mTLS client key** bị lộ | Có thể giả mạo certificate holder theo trust/profile. | PKI/certificate revocation và token binding controls. |
| **JWE decryption key** bị lộ | Giải mã ciphertext có thể đã lưu/copy. | Rotate/revoke decryption capability, đánh giá confidentiality impact. |

**Không phải mọi “key” đều là signing key của AS**. Cần xác định key purpose, nơi lưu, issuer/client và hệ thống nào đang tin hoặc dùng key đó.

## 5. Key revocation ảnh hưởng đến các loại token

| Loại credential | Có liên hệ với key nào? | Cần kiểm gì khi revoke? |
| --- | --- | --- |
| **JWT access token** | Signing key AS, có thể cả sender-binding key. | RS có còn tin signing key? AT còn hạn? Có state/denylist/DPoP? |
| **Opaque access token** | Thường là reference token, không cần JWT signature để RS đọc. | AS introspection/lookup và issuance vẫn hoạt động; key revocation có thể ảnh hưởng AS/client auth nhưng không tự làm opaque AT inactive. |
| **Refresh token** | Thường do AS quản lý, có thể opaque hoặc định dạng được bảo vệ riêng. | Signing-key revoke không tự revoke RT family/grant; phải đóng issuance path nếu rủi ro. |
| **OIDC ID token** | OP signing key; RP giữ public verifier keys. | RP còn chấp nhận ID token cũ? Ứng dụng đã tạo session riêng chưa? |
| **Client assertion private_key_jwt** | Client private key; AS giữ public key hoặc JWKS. | AS ngừng chấp nhận key của client, xử lý replay/credential rotation. |
| **mTLS-bound AT** | Token gắn client certificate thumbprint. | Kiểm mTLS certificate/trust và binding, revoke AT nếu key bị lộ. |
| **DPoP-bound AT** | Token gắn public key thumbprint của DPoP key. | Nếu DPoP private key bị lộ, thu hồi AT ràng key và dùng key mới. |
| **JWE token** | Key agreement/encryption/decryption key. | Key bị lộ có thể ảnh hưởng confidentiality; signing trust là quyết định riêng. |

### Một nguyên tắc dễ bỏ sót

Nếu **AS signing private key** bị lộ, revoke trust của key đó giúp RS từ chối JWT giả. Nhưng nếu **refresh token** hoặc **client secret** cũng bị lộ, attacker vẫn có thể yêu cầu AS phát JWT mới bằng K-new nếu issuance path chưa bị chặn.

**Key revocation và token/grant revocation là hai control bổ trợ, không tự bao hàm nhau.**

## 6. Vì sao chỉ xóa key khỏi JWKS chưa đủ?

**JSON Web Key Set (JWKS)** theo RFC 7517 là cơ chế biểu diễn/distribution keys. Nó **không phải giao thức đồng bộ revocation tức thời** cho mọi RS.

Một issuer có:

~~~text
issuer = https://identity.example.test
jwks_uri = https://identity.example.test/.well-known/jwks.json
kid = as-ps256-2026-10
~~~

Khi AS gỡ public key K-old khỏi JWKS, các RS có thể:

- Giữ **JWKS cache TTL** còn dài.
- Chỉ refresh khi gặp unknown kid; JWT của K-old vẫn có **kid đã biết** nên không kích hoạt refresh.
- Bị outage không liên lạc được JWKS endpoint.
- Dùng local public key được provision ở deployment, không fetch JWKS mỗi request.
- Có instance/gateway mới khởi động bằng snapshot key set cũ.
- Từng cấu hình key trust trực tiếp ở code/environment thay vì JWKS.

~~~mermaid
sequenceDiagram
    participant IR as Incident Admin
    participant AS as AS/JWKS
    participant RS1 as Orders RS - cache cũ
    participant RS2 as Payments RS - cache mới
    participant X as Attacker có K-old

    RS1->>AS: Lấy JWKS có public K-old
    AS-->>RS1: Cache K-old
    IR->>AS: Disable private K-old, remove khỏi JWKS
    AS->>AS: JWKS chỉ còn K-new
    RS2->>AS: Refresh JWKS
    AS-->>RS2: Không còn K-old
    X->>RS1: JWT giả ký K-old
    Note over RS1: Còn cache K-old nếu chưa áp revoke state
    RS1-->>X: Có nguy cơ chấp nhận nếu validate chỉ chữ ký/claims
    X->>RS2: JWT giả ký K-old
    RS2-->>X: Từ chối: K-old không tin
~~~

Để có **emergency revocation**, nên có một cơ chế trạng thái đáng tin như **denylist key identifiers/fingerprints, trust epoch, policy/config deployment, push event, JWKS cache invalidation** hoặc phối hợp. Chọn cách tùy topology và SLO.

### Public key vẫn công khai sau revocation

Revocation không “xóa public key khỏi Internet”. Public key từng nằm trong JWKS có thể được lưu trong logs/caches. Điều cần bảo đảm là **verifier ngừng xem nó là nguồn xác minh đáng tin** cho mục đích token hiện tại.

## 7. Key identity: kid chưa đủ cho trạng thái thu hồi

**kid** là một key identifier trong JOSE, thường nằm trong JWS protected header. Nó hữu ích cho key selection nhưng:

- Do chính token mang tới, nên **không tự là bằng chứng tin cậy**.
- Có thể trùng giữa các issuer.
- Có thể bị dùng lại nhầm khi key material thay đổi.
- Không buộc một JWK phải có kid duy nhất toàn cầu.
- Có thể chứa dữ liệu độc hại nếu dùng làm filesystem path, SQL hoặc URL không an toàn.

Một revocation record nên ràng:

~~~text
issuer_id
key_fingerprint / trusted public JWK thumbprint
kid trong phạm vi issuer
key_type, algorithm, key_use / purpose
environment hoặc trust domain
revocation_generation
effective_at, reason, incident_id
~~~

### Fingerprint/JWK thumbprint

**RFC 7638** định nghĩa cách tính **JWK Thumbprint** cho một JWK theo các thành phần canonical được quy định. Thumbprint giúp xác định public key material ổn định hơn việc chỉ đọc kid, khi dùng đúng chuẩn.

Với một key có thể được đăng ký dưới nhiều kid, incident responder cần chặn **mọi alias và mọi đường phát/verify** gắn với cùng key material.

**Không lấy thumbprint do client tự khai làm bằng chứng issuer.** Phải tính/tra từ **trusted key registry hoặc trusted JWKS**, có issuer binding và key purpose.

### Tránh hủy nhầm key

Nếu issuer A và issuer B có cùng kid=key-1, một thao tác revoke không được vô hiệu issuer B chỉ vì so mỗi kid.

Ngược lại, nếu attacker đăng ký lại **cùng private/public key material** dưới kid mới, hệ thống cũng không được coi đó là một key sạch. Cần phân biệt **identity của key material** và **nhãn kid**.

## 8. Mô hình trạng thái khóa: ký và xác minh là hai trục

Một enum đơn giản **ACTIVE/REVOKED** thường không thể biểu diễn đầy đủ trạng thái của signing key. Với JWT/JWS nên tách:

- **Signing capability:** AS/KMS có được phép tạo chữ ký mới bằng K-old không?
- **Verification trust:** RS/RP có được phép chấp nhận chữ ký gắn với K-old không?

| Signing capability | Verification trust | Tình huống |
| --- | --- | --- |
| **DISABLED** | **NOT_YET_TRUSTED** | Key vừa tạo, chưa được đưa vào sử dụng. |
| **ENABLED** | **TRUSTED** | Key ký JWT mới và RS được phép verify. |
| **DISABLED** | **TRUSTED** | Rotation bình thường: ngừng ký cũ, token cũ còn được verify. |
| **DISABLED** | **REVOKED** | Key compromise: chặn ký và rút trust khẩn cấp. |
| **ENABLED** | **REVOKED** | Cấu hình mâu thuẫn: signer còn ký token mà RS phải từ chối. |

~~~mermaid
flowchart TD
    A["PREPARED / chưa ký"] --> B["ACTIVE_SIGNING + TRUSTED_VERIFY"]
    B --> C["SIGN_DISABLED + TRUSTED_VERIFY"]
    C --> D["RETIRED / trust removed after normal TTL"]
    B --> E["EMERGENCY: SIGN_DISABLED + TRUST_REVOKED"]
    C --> E
    E --> F["REPLACED BY CLEAN KEY"]
    E --> G["DESTROY / FORENSIC RETENTION theo policy"]
~~~

**Không tự chuyển key material đã bị compromise trở lại ACTIVE để sửa outage.** Khôi phục dịch vụ bằng key mới, credential/grant mới nếu cần và quy trình tin cậy được kiểm soát.

### Version hóa revocation

Một record nội bộ có thể chứa:

~~~json
{
  "issuer": "https://identity.example.test",
  "key_id": "as-ps256-2026-10",
  "public_key_thumbprint": "EXAMPLE_TRUSTED_FINGERPRINT",
  "purpose": "oauth-access-token-signing",
  "signing_state": "DISABLED",
  "verification_state": "REVOKED",
  "generation": 19,
  "incident_id": "INC-EXAMPLE-874"
}
~~~

Đây **không phải định dạng JWK chuẩn**, chỉ là ví dụ cho registry quản trị. Fingerprint phải được tính từ trusted public key, không lấy nguyên từ input chưa được xác thực.

Generation/version phải **monotonic**: event generation=18 đến muộn không được ghi đè state revoked generation=19. Refresh JWKS từ một cache cũ cũng không được làm key hồi sinh.

## 9. Playbook ứng phó key compromise

~~~mermaid
flowchart TD
    D["Phát hiện nghi lộ private signing key"] --> I["Tạo incident ID, giữ evidence an toàn"]
    I --> S["Xác định issuer, purpose, fingerprint và RS coverage"]
    S --> P{"Admin có quyền và approval?"}
    P -->|Không| E["Escalate và containment theo quyền sẵn có"]
    P -->|Có| X["Disable Sign, cô lập signer/caller"]
    X --> R["Commit TRUST_REVOKED trong authoritative registry"]
    R --> K["Sinh/activate key sạch sau kiểm issuance policy"]
    K --> V["Push revoke config, update trusted JWKS và cache"]
    V --> T["Kiểm từng RS từ chối K-old"]
    T --> Q{"Tất cả targets đạt SLO?"}
    Q -->|Không| C["Emergency block, escalate, retry propagation"]
    C --> T
    Q -->|Có| Z["Khôi phục hợp lệ, audit, postmortem"]
~~~

### Triage

Ghi nhận:

1. **Issuer/trust domain:** key của AS/OP, OAuth client, CA hay DPoP device?
2. **Key identity:** kid, JWK thumbprint, alg/kty, key handle và version.
3. **Evidence:** key bị copy, IAM Sign bị lạm dụng hay chỉ một AT bị đánh cắp?
4. **Phạm vi:** JWT token types, RS/RP, tenant, clients và token TTL.
5. **Thời gian:** lúc nghi compromise, last-good-signing, JWKS cache TTL.
6. **Kiểm soát:** ai có quyền disable Sign, revoke Verify và phê duyệt mở rộng.
7. **SLO:** bao lâu AS phải ngừng ký và RS phải từ chối chữ ký cũ?
8. **Forensics:** signing logs, client grants, API operations và bản sao key/backup có thể liên quan.

Không copy private key vào ticket/chat. Giữ bằng chứng theo phân quyền bằng **key handle, fingerprint, file provenance và audit record**.

### Containment

- Disable KMS Sign hoặc thu hồi IAM role/caller bị chiếm.
- Nếu key bytes có thể bị lộ, rút **verification trust**, không chỉ disable signer.
- Ngăn đăng ký lại chính key material dưới kid khác.
- Cô lập hệ thống phát hành token sai scope/audience.
- Nếu RT/client credential cũng bị đánh cắp, xử lý grant/issuance path riêng.
- Theo dõi token đã bị dùng và đánh giá dữ liệu bị truy cập trái phép.

### Recovery

Sinh key mới từ môi trường sạch; đăng ký issuer, purpose, alg, kid; công bố public key qua trusted JWKS; kiểm RS readiness, negative tests và quyền Sign; phát hành token mới theo grant/policy an toàn; không tái kích hoạt compromised K-old.

## 10. Race giữa revoke và token issuance

Trong hệ thống phân tán, có thể xảy ra:

~~~text
A: signer kiểm K-old đang ACTIVE.
B: admin commit SIGN_DISABLED + TRUST_REVOKED.
A: dùng trạng thái cũ và hoàn thành chữ ký K-old.
C: RS chưa nhận event vẫn verify K-old.
~~~

Nên có **generation fencing** hoặc cơ chế nhất quán tương đương:

~~~text
TOKEN ISSUANCE:
    check grant/client/resource policy
    select allowed signing key for issuer/purpose
    check current key generation/active state
    sign only with authorized KMS Sign capability
    confirm issuance state according to concurrency contract

KEY REVOKE:
    disable signing capability
    commit trusted revocation state + generation
    write audit + durable propagation event
    trigger verifier trust removal

RESOURCE SERVER:
    verify signature under issuer-specific key trust
    reject keys locally marked REVOKED
    validate aud/type/exp/scope/permission
~~~

Một kiểm tra ACTIVE đơn lẻ trước khi đưa job vào queue ký **không đủ** nếu queue chạy sau revocation. KMS disable và signer state gating phải phối hợp.

### Race với JWKS fetch

~~~text
T1: RS đang fetch JWKS cũ chứa K-old.
T2: RS nhận event TRUST_REVOKED(K-old, generation=42).
T3: Response JWKS cũ đến sau và chứa K-old.
~~~

**RS không được cài lại K-old thành TRUSTED** nếu local revocation generation mới hơn. Trạng thái revoked phải được giữ qua restart hoặc đồng bộ từ nguồn authoritative trước khi chấp nhận token thuộc trust domain nhạy cảm.

## 11. Phát tán revocation đến nhiều Resource Servers

Khi AS rút một signing key, các điểm thực thi có thể gồm:

- Resource Server xác minh JWT offline.
- API Gateway, BFF, authentication sidecar hoặc service mesh policy.
- Relying Party xác minh OIDC ID token nếu key dùng chung.
- Offline job, edge node hoặc batch consumer giữ JWKS snapshot.
- Key trust registry cho OAuth client private_key_jwt nếu bị revoke client key.
- Hạ tầng xác minh mTLS/certificate nếu sự cố liên quan PKI.

### Pull qua JWKS

RS có thể fetch JWKS theo HTTP caching. Cách này thường hợp lý cho rotation có kế hoạch, nhưng **không bảo đảm hiệu lực thu hồi tức thì** khi key bị lộ.

### Push qua kênh điều khiển đáng tin

~~~text
Authoritative Key Revocation Registry
    |
    | authenticated event / durable outbox
    v
Message Broker / Policy Distribution
    |
    +--> Orders RS / auth library
    +--> Payments RS
    +--> API Gateway / edge
    +--> OIDC RP (nếu bị ảnh hưởng)
    +--> Offline workers (snapshot/reconciliation)
~~~

Nếu dùng một local key denylist, nên khóa theo **issuer + trusted public key fingerprint + purpose**, không chỉ kid tự khai từ JWT.

~~~text
if keyTrustRegistry.isRevoked(
    trustedIssuer,
    verifiedKeyFingerprint,
    expectedTokenPurpose
):
    REJECT_TOKEN
~~~

Việc xác định **verifiedKeyFingerprint** phải dựa trên key material từ trusted issuer registry, không chỉ từ header do attacker gửi.

### Khi RS offline

RS không nhận được event trong lúc offline cần **replay, snapshot hoặc reconciliation** trước khi dùng state stale. Nếu một instance có nguy cơ còn nhận K-old bị compromise, có thể cần tạm ngừng traffic nhạy cảm theo containment policy. Đừng tự dùng stale trust vô hạn chỉ để giữ availability.

## 12. Event ordering, idempotency và cache consistency

Một broker có thể giao message nhiều lần hoặc sai thứ tự. Revocation consumer phải **monotonic và idempotent**.

Event nội bộ minh họa:

~~~json
{
  "event_id": "evt-example-432",
  "incident_id": "INC-EXAMPLE-874",
  "issuer": "https://identity.example.test",
  "key_id": "as-ps256-2026-10",
  "public_key_thumbprint": "EXAMPLE_KEY_THUMBPRINT",
  "purpose": "oauth-access-token-signing",
  "verification_state": "REVOKED",
  "generation": 42,
  "effective_at": "2026-11-23T00:00:00Z"
}
~~~

**Không phải schema RFC 7517/7009.** Event không nên mang private key hoặc HMAC secret.

Consumer pseudocode:

~~~text
function applyRevocationEvent(event):
    authenticateEventSource(event)
    verifyIssuerPurposeAndSchema(event)

    key = trustedRegistry.resolveFingerprint(
        issuer=event.issuer,
        keyId=event.key_id
    )

    if key.fingerprint != event.public_key_thumbprint:
        REJECT_AND_ALERT()

    local = localRevocationState(key)

    if local.generation >= event.generation:
        ACK_DUPLICATE_OR_STALE()
        return

    atomically:
        persistRevokedState(key, event.generation)
        invalidateAffectedJwksAndJwtCaches(key)
        blockAliasesWithSameKeyMaterial(key)

    ACK_APPLIED_GENERATION(event.generation)
~~~

**Broker delivery ACK khác applied-generation ACK**: message được giao không chứng minh RS đã thay đổi validator.

### Không khôi phục key bị revoke từ cache

- JWKS cache cũ không được ghi đè deny state mới.
- Cần lưu revoked fingerprints/generation qua restart.
- Một policy bundle version thấp hơn không được hạ trạng thái từ REVOKED về TRUSTED.
- Nếu phải đổi registry/tin cậy trở lại trong tình huống đặc biệt, cần quy trình change approval mới; với key compromise nên cấp key material **mới**, không mở lại K-old.
- Có periodic reconciliation và cảnh báo queue lag, missed events, stale instances.

## 13. API quản trị key revocation là giao diện riêng

**OAuth RFC 7009** định nghĩa client request để thu hồi token, **không** định nghĩa admin endpoint chuẩn để revoke signing key của AS. Ví dụ dưới đây là API nội bộ giả định:

~~~http
POST /admin/security/key-revocations HTTP/1.1
Host: admin.identity.example.test
Authorization: Bearer EXAMPLE_ADMIN_ACCESS_TOKEN
Content-Type: application/json
Idempotency-Key: inc-example-874-kold

{
  "incident_id": "INC-EXAMPLE-874",
  "issuer": "https://identity.example.test",
  "purpose": "oauth-access-token-signing",
  "key_id": "as-ps256-2026-10",
  "public_key_thumbprint": "EXAMPLE_KEY_THUMBPRINT",
  "requested_actions": [
    "DISABLE_SIGN",
    "REVOKE_VERIFICATION_TRUST"
  ],
  "reason_code": "SUSPECTED_PRIVATE_KEY_EXPOSURE"
}
~~~

Request phải đi qua HTTPS, admin authentication mạnh và kiểm issuer/target/approval phía server. Idempotency key không phải bằng chứng authorization.

### Operation accepted không phải enforced

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /admin/security/key-revocations/op-example-25

{
  "operation_id": "op-example-25",
  "status": "PROPAGATING",
  "signing_disabled": true,
  "trust_revocation_committed": true,
  "required_verifiers": 5,
  "confirmed_verifiers": 2
}
~~~

**Chỉ đặt signing_disabled=true khi KMS/signing policy thật sự đã chặn Sign.** HTTP 202 không chứng minh toàn bộ RS đã áp trusted revocation state.

### Lỗi cần phân biệt

| Tình trạng | Hành vi đúng |
| --- | --- |
| Admin chưa xác thực | 401, không tiết lộ thông tin nhạy cảm. |
| Admin thiếu issuer/tenant/action permission | 403, không revoke. |
| Thiếu dual approval khi policy yêu cầu | Không thực thi bulk key revoke. |
| Cùng idempotency key nhưng payload khác | 409/conflict. |
| Key đã revoked | Idempotent response, không tự re-enable. |
| KMS DisableKey thất bại | Không báo ngừng ký thành công. |
| Commit authoritative registry thất bại | Không báo trust revoke committed. |
| Propagation mới đạt một số RS | PROPAGATING/PARTIALLY_ENFORCED. |
| RS còn nhận chữ ký K-old | Alert và containment, không báo ENFORCED. |

Một admin operation có thể cần thực hiện **hai bước quản trị khác nhau**: disable signing key và revoke verifier trust. Từng bước cần evidence riêng.

## 14. Quyền hạn admin và lưu bằng chứng

Key revocation có thể khiến hàng loạt người dùng hợp pháp mất quyền truy cập trước thời hạn token. Management plane phải có bảo vệ tương xứng.

- RBAC/ABAC theo issuer, environment, tenant, key purpose và operation type.
- **MFA/step-up**, JIT elevation hoặc break-glass có giám sát theo risk policy.
- **Dual control** cho key rotation/revoke diện rộng và tác động production lớn.
- Tách quyền **Generate, Activate, Sign, Disable, Revoke Trust, Destroy**.
- Không tin UI đã ẩn lựa chọn issuer khác; backend phải kiểm.
- Bảo vệ CSRF nếu admin console dùng cookie và không để endpoint có side effects qua GET.
- Ràng idempotency key với actor/target/payload, dùng transaction/unique constraints.
- Giới hạn metadata admin đọc để ngăn key/tenant enumeration.
- Audit có retention và chống sửa/xóa.

Audit record gợi ý:

~~~text
incident_id / operation_id
actor_id / approver_id
issuer / environment / purpose
key_handle / kid / trusted fingerprint
previous_signing_state / previous_verification_state
new_signing_state / new_verification_state
generation / effective_at / committed_at
affected_verifier_set / applied_generation_ack
reason_code / change_reference / result / exceptions
~~~

**Không ghi private key, HMAC secret, full raw token hoặc thông tin xác thực admin vào audit/logs.** Fingerprint vẫn có thể là identifier nhạy cảm về vận hành, nên giới hạn quyền đọc.

### Idempotent không có nghĩa hủy bỏ incident record

Lặp cùng request với idempotency key hợp lệ phải trả cùng operation hoặc trạng thái đúng, không tạo nhiều quyết định mới. Nếu caller đổi target hoặc requested_actions nhưng dùng lại key cũ, phải báo conflict. Revoke key đã compromise phải **monotonic**; việc mở lại bằng retry là sai.

## 15. Thu hồi HS256 shared secret

Với **HS256**, AS và các Resource Server dùng cùng một bí mật K để tạo và xác minh HMAC. Vì vậy **bất kỳ RS nào biết K cũng có thể tạo tag hợp lệ**, không chỉ verify.

~~~mermaid
flowchart LR
    AS["AS giữ secret K"] -->|"HS256 JWT"| C["OAuth Client"]
    C --> O["Orders giữ K"]
    C --> P["Payments giữ K"]
    X["Attacker lấy K từ Orders"] -.->|"Forge HS256 JWT"| P
~~~

Khi secret bị lộ:

1. Disable việc ký token mới bằng K-old ở AS.
2. Ngừng tin K-old ở **mọi RS** còn giữ cùng secret, bao gồm gateway/replica.
3. Sinh K-new bằng CSPRNG/KMS, đủ entropy theo JWA và security policy.
4. Phân phối K-new qua secret manager, không qua Git/log/URL.
5. Kiểm cả cache/process memory/config snapshots và các alias của K-old.
6. Điều tra khả năng forged token, quyền truy cập và dữ liệu đã bị tác động.
7. Cấp token mới, khắc phục điểm rò rỉ, đo enforcement SLO.

**JWK kty=oct chứa trường k là symmetric secret; tuyệt đối không công bố nó trong JWKS public.** Nếu nhiều verifier thuộc các trust domains khác nhau, cân nhắc asymmetric signing.

Một secret có thể được đăng ký dưới nhiều kid; key revocation phải bao phủ **cùng key material** chứ không chỉ một nhãn kid.

## 16. Thu hồi private signing key RSA/ECDSA/EdDSA

Trong asymmetric signing, AS giữ private key còn RS chỉ cần public key. **Public key xuất hiện trong JWKS là bình thường**, không tự chứng minh signing key bị lộ.

Nếu private K-old bị đánh cắp:

- Attacker có thể ký JWT giả cho các RS còn tin public K-old.
- Attacker có thể tự tạo **jti** mới: denylist token IDs đã thấy chưa đủ.
- Attacker có thể tự đặt **iat** trước thời điểm phát hiện compromise, nên không thể nhận diện token thật chỉ bằng iat.
- Attacker có thể tạo scope/subject/audience giả theo những điều kiện parser/verifier còn chấp nhận.

Cần **ngừng Sign và rút trust**, đồng thời ngăn tái đăng ký cùng key material với kid khác.

Một **authoritative issuance ledger** độc lập có thể giúp xác định token AS đã phát, nhưng phải có integrity, lifecycle và online verification phù hợp. Không dùng claims được ký bởi key compromised làm bằng chứng duy nhất về tính hợp pháp.

### Sai lầm thường gặp

~~~text
if jwt.iat < incidentDetectedAt:
    accept token signed with compromised K-old
~~~

Sai vì attacker có K-old cũng có thể ký token với iat giả. Chính sách key trust phải kiểm fingerprint/trạng thái **độc lập với nội dung JWT**.

## 17. Thu hồi khóa xác thực OAuth client: private_key_jwt

Trong **private_key_jwt**:

- OAuth client giữ private key để ký **client assertion**.
- AS giữ public verification key/JWKS của client để kiểm client authentication.
- Khi client private key bị lộ, attacker có thể giả client tại token endpoint.

**Không nhất thiết cần revoke signing key của chính AS.** Cần xử lý client-authentication key/registration:

1. Xác định client_id, trusted public key fingerprint, key registration và issuer.
2. Chặn AS chấp nhận assertion ký bằng K-old.
3. Client tạo K-new, cập nhật registration/JWKS bằng kênh xác thực.
4. Kiểm client assertions cũ bị từ chối; assertions mới kiểm iss/sub/aud/exp/jti theo profile.
5. Rà soát AT/grants đã được cấp trong thời gian compromise; revoke/deny khi cần.
6. Kiểm scope/resource của client, key custody, token endpoint logs và replay protection.
7. Không giữ public K-old trong trusted client keys vô hạn.

**Client assertion dành cho AS token endpoint, không phải access token cho RS.** Key revocation của client không tự khiến tất cả AT đã cấp trở nên inactive; đó là quyết định token/grant revocation riêng.

## 18. mTLS certificate, DPoP key và X.509 revocation

### mTLS client certificate key

Một OAuth client có thể dùng mTLS để xác thực với AS. Một access token có thể được ràng với client certificate thumbprint theo profile RFC 8705.

Nếu private key của certificate bị lộ:

1. Thu hồi/loại certificate khỏi trusted client-authentication policy.
2. Phát certificate và private key mới trong môi trường sạch.
3. Kiểm AS không tiếp tục xác thực client bằng certificate cũ.
4. Kiểm RS xác minh mTLS sender-binding cho AT đã phát.
5. Revoke AT/grant liên quan theo threat model; token còn ràng thumbprint cũ không tự chuyển sang certificate mới.
6. Kiểm PKI, CA policy, certificate stores và caches.

**Certificate revocation và JWT signing-key revocation không phải một thao tác duy nhất.** Có thể cần cả certificate-status validation lẫn resource-token lifecycle.

### CRL/OCSP chỉ có hiệu lực trong PKI validation

**CRL (Certificate Revocation List)** và **OCSP (Online Certificate Status Protocol)** thuộc hệ sinh thái **X.509 PKI**. Chúng chỉ giúp từ chối certificate bị revoke khi verifier thực sự làm chain/status validation theo policy.

Một RSA public key được công bố dưới dạng **raw JWK** không tự có CRL/OCSP. Nếu RS chỉ sử dụng trusted JWKS, cần cơ chế quản lý key trust/JWKS riêng; không mặc định OCSP sẽ rút mọi signing JWK.

### DPoP client key

DPoP proof do client ký cho **request hiện tại**; access token có thể mang confirmation key thumbprint.

Nếu DPoP private key bị lộ, attacker có cả token và key có thể tạo proof hợp lệ. Cần:

- Revoke các access tokens ràng với key bị lộ, theo khả năng AS và registry.
- Sinh DPoP key mới; cấp token mới với thumbprint mới.
- RS tiếp tục kiểm signature proof, **htm, htu, iat, jti, replay/nonce và key binding** theo RFC 9449.
- Bảo vệ client runtime/storage, hạn chế scopes và giám sát replay.

**DPoP key của client không phải AS signing key.** Không revoke toàn bộ AS JWT signing keys chỉ vì một thiết bị mất DPoP key.

## 19. Opaque token, refresh token và OIDC sessions

### Opaque access token

Với opaque AT được RS introspect tại AS, trạng thái active được quản lý theo token/grant. Việc AS revoke một **JWT signing private key** không tự làm mọi opaque AT active=false nếu không có liên kết chính sách.

Nếu opaque token nội bộ có MAC/encryption bằng key khác, revoke key đó có thể làm AS không thể giải mã/lookup; cần hiểu định dạng triển khai thực, không suy từ chữ “opaque”.

### Refresh token

Refresh token thường dùng tại AS token endpoint, không dùng làm AT tại RS. **Key revocation không tự khóa RT family**. Nếu attacker có cả RT, client secret hoặc session, họ có thể tiếp tục xin AT mới ký bằng K-new nếu grant/issuance còn mở.

Phải xử lý **RT family, grant, account session và client credentials** theo phạm vi incident.

### OIDC ID token

Nếu key K-old còn ký ID tokens, các RP cần biết key đã revoked. Nhưng một RP đã tạo session cookie/server-side session riêng không tự logout chỉ vì JWKS đổi.

Có thể cần OIDC logout/session termination theo hợp đồng và reauthentication. **Key revocation không tự là logout toàn bộ ứng dụng**.

### RFC 7009 và RFC 7662 không thay key trust control

- **RFC 7009:** token revocation endpoint, không chuẩn hóa admin API revoke signing key.
- **RFC 7662:** introspection endpoint có active field, không đồng nghĩa RS verify JWT offline đã cập nhật key status.
- **RFC 7517:** biểu diễn JWK/JWKS, không quy định revocation propagation SLO.
- **RFC 8414:** metadata AS, có thể chỉ ra jwks_uri đáng tin; metadata không tự ép RS refresh tức thì.

Kết hợp controls theo token type/trust boundary, không đòi một endpoint xử lý tất cả.

## 20. Chữ ký có thể đúng về toán nhưng key không còn tin cậy

Khi private K-old lộ, kiểm signature bằng public K-old vẫn có thể trả true. Nhưng policy RS đã rút trust:

~~~text
VerifySignature(K-old.public, jwt) == true
TrustedKey(K-old, issuer, purpose) == false

Result = REJECT
~~~

Các điều kiện nhận JWT:

~~~text
ALLOW only if:
    expected issuer/trust domain is configured
    AND selected key belongs to trusted issuer/purpose
    AND selected key material is not revoked
    AND alg and key type are permitted
    AND JWS signature valid
    AND token type/profile is supported
    AND audience, exp, nbf, scope are valid
    AND principal/tenant/resource authorization allows
    AND applicable sender proof and token state checks pass
~~~

**Không đọc scope từ unverified JWT rồi cấp quyền**. Cũng không fallback sang alg=none, HS256 bất ngờ hoặc untrusted jku chỉ để tiếp tục chấp nhận token sau khi K-old bị chặn.

## 21. Cache TTL, issuer trust và SLO revocation

Một key revoke có thể lan qua:

~~~text
Incident decision
  -> KMS/HSM Disable Sign
  -> authoritative key trust registry
  -> JWKS publisher
  -> API Gateway key cache
  -> Resource Server JWT decoder cache
  -> OIDC RP / offline workers
  -> verification probes and applied-version evidence
~~~

Thời gian phản ánh revoke phụ thuộc **control plane, message delivery, local caches và policy của từng RS**.

### Các mốc quan sát

~~~text
T_detect: security team phát hiện.
T_sign_disabled: signer không còn dùng K-old.
T_trust_committed: authoritative registry ghi REVOKED.
T_rs_applied: verifier áp generation mới.
T_verified: RS từ chối chữ ký K-old trong test được phép.
~~~

Định nghĩa riêng:

- **Signing cutoff SLO:** commit quyết định đến lúc Sign bằng K-old bị chặn.
- **Verification trust SLO:** trust revoke commit đến lúc toàn bộ RS bắt buộc từ chối K-old.
- **Coverage SLO:** tỷ lệ/độ trễ cập nhật của tất cả gateway, RS replicas và RP cần thiết.
- **Containment SLO:** lúc phát hiện đến thời điểm khả năng forge/replay trong phạm vi đã được kiểm soát.

Đây là **SLO vận hành**, không phải con số mặc định của JOSE/RFC 7517.

### Không đánh đồng partial và complete

~~~text
KMS: K-old disabled
Orders RS: applied generation 42
Payments RS: applied generation 42
Analytics RS: offline, chưa applied
OIDC RP: vẫn cache K-old
~~~

Nếu Analytics/RP thuộc tập targets bắt buộc, chưa thể kết luận ENFORCED toàn hệ thống. Có thể cần emergency ingress block, tạm dừng endpoint nhạy cảm hoặc biện pháp containment được duyệt.

**Không dùng JWKS response cũ để làm key đã revoke hồi sinh trong local trust set.**

## 22. Java: lưu trạng thái key revocation theo generation

Ví dụ Java sau minh họa một **in-memory index** cho khóa đã bị revoke. Nó **không** thay authoritative registry, signature verifier, durable store hoặc event authentication của production.

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public final class KeyRevocationIndex {

    public record KeyIdentity(
            String issuer,
            String publicKeyThumbprint,
            String purpose) {

        public KeyIdentity {
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(publicKeyThumbprint);
            Objects.requireNonNull(purpose);
        }
    }

    // Chỉ nhận key đã được xác định từ trusted registry.
    private final Map<KeyIdentity, Long> revokedGenerations =
            new ConcurrentHashMap<>();

    public void applyVerifiedRevocation(
            KeyIdentity identity,
            long generation) {

        if (generation <= 0) {
            throw new IllegalArgumentException("Invalid generation");
        }

        revokedGenerations.merge(
                Objects.requireNonNull(identity),
                generation,
                Math::max
        );
    }

    public boolean isRevoked(KeyIdentity identity) {
        return revokedGenerations.containsKey(identity);
    }

    public long lastRevocationGeneration(KeyIdentity identity) {
        return revokedGenerations.getOrDefault(identity, 0L);
    }
}
~~~

### Bài học từ ví dụ

- **KeyIdentity** gồm issuer, public-key fingerprint và purpose, không chỉ kid.
- **merge(..., Math.max)** giúp không giảm generation nếu event cũ đến muộn.
- Không có nhánh **unrevoke**: key material đã compromised nên không được tự tin lại.
- Hash map ở process memory sẽ mất khi restart, nên **không đủ cho production**.
- Tên method applyVerifiedRevocation giả định **caller đã xác thực event và đối chiếu fingerprint từ trusted registry**; method không tự xác thực event.
- Nếu dùng registry phân tán, cần durable state, authenticated transport, exact issuer scoping, startup reconciliation và monitoring.
- Các bộ nhớ cache JWT/JWK riêng của thư viện phải thực sự **tham chiếu index ở validation path** hoặc được invalidate đúng cách; chỉ tạo index này mà không gắn vào decoder không có tác dụng.

### Không dùng kid chưa được xác thực làm key identity

Sai:

~~~text
identity = KeyIdentity(
    issuer = token.payload.iss,
    thumbprint = token.header.kid,
    purpose = "access-token"
)
~~~

Cả iss và kid từ token **chưa được tin trước khi verify**; kid không phải thumbprint. Đúng hơn là chọn **trusted issuer/key material** từ policy, tính/truy vấn thumbprint từ trusted key registry, kiểm key revocation, sau đó xác minh JWS và semantic claims theo profile.

## 23. Gắn key revocation vào JWT verification path

Một thuật toán validation khái niệm:

~~~text
function verifyJwtAccessToken(rawJwt, request):
    expectedIssuer = routeConfiguredTrustedIssuer(request)
    profile = configuredAccessTokenProfile(request)
    allowedAlgs = profile.allowedSignatureAlgorithms

    header = strictParseProtectedHeader(rawJwt)
    requireAllowedAlg(header.alg, allowedAlgs)
    requireKnownSafeHeaderParameters(header)

    trustedKey = trustedJwkRegistry.resolve(
        issuer = expectedIssuer,
        purpose = "oauth-access-token-signing",
        kid = header.kid,
        algorithm = header.alg
    )
    if trustedKey absent:
        DENY_401()

    keyIdentity = trustedKey.issuerAndPublicFingerprint()
    if revocationRegistry.isRevoked(keyIdentity):
        DENY_401()

    verifiedJwt = joseLibrary.verifySignature(
        rawJwt, trustedKey, profile
    )
    if invalid:
        DENY_401()

    requireIssuer(verifiedJwt.iss, expectedIssuer)
    requireAudience(verifiedJwt.aud, expectedResourceAudience)
    requireTokenType(verifiedJwt, profile)
    requireValidExpirationAndNotBefore(verifiedJwt)
    requireSupportedPrincipalAndGrantedScopes(verifiedJwt)

    if accessTokenRevocationIsRequired:
        requireTokenNotRevoked(verifiedJwt)

    if senderConstrained:
        requireValidProofForThisRequest(request, verifiedJwt)

    requireBusinessPermission(verifiedJwt, request.resource)
    return AUTHENTICATED_CONTEXT
~~~

**Đây là pseudocode**, không phải một JWT library mới tự triển khai. JOSE parsing, signature verification, certificate validation và canonicalization nên do thư viện uy tín xử lý.

### Trusted key selection

- **Không fetch jku/x5u** theo URL do JWT tự khai nếu không được trust profile cho phép.
- **Không biến kid thành path/SQL query** không an toàn.
- **Không cho token tự chọn issuer** rồi gửi key lookup đến host bất kỳ.
- **Không chấp nhận alg=none** hoặc HS256 thay RS256 khi key/profile không cho phép.
- **Không dùng public key của issuer B** chỉ vì kid trùng issuer A.
- **Không lẫn ID token và access token** dù cùng signing key.
- **Không bỏ audience, scope và resource policy** chỉ vì signature đúng.

### Nếu thư viện chỉ cung cấp post-verification callback

Có thể dùng một validator sau signature để kiểm revoked key **nếu thư viện đã chọn key từ issuer registry tin cậy và có thể cung cấp chính xác key identity đã dùng**.

Chỉ đọc **jwt.header.kid** sau verify là chưa đủ trong hệ thống cho phép alias/trùng key material. Với yêu cầu bảo vệ key compromise, nên tích hợp ở **trusted JWK selector/decoder** hoặc metadata đi kèm về fingerprint **của verification key thực sự**, không gán thumbprint từ header.

## 24. Spring Security: cấu hình crypto không tự giải quyết key revocation

Một Resource Server dùng Spring Security có thể cấu hình JWT decoder theo JWKS tin cậy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        return NimbusJwtDecoder
                .withJwkSetUri(
                    "https://identity.example.test/.well-known/jwks.json"
                )
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();
    }
}
~~~

**Đây chỉ là cấu hình minh họa thuật toán/JWKS**, chưa phải cấu hình production đầy đủ. Trong hệ thống thật cần:

- Gắn **issuer, audience, exp/nbf, token type** validators theo profile.
- Gắn scope, principal, business permission và revocation policy.
- **Áp key revocation tại trusted key selection/verification boundary** hoặc validator có danh tính chính xác của verification key đã dùng.
- Cấu hình HTTP timeouts, TLS, JWKS caching/refresh và fail-closed.
- Đảm bảo revoked public key **không được tự nhận trở lại** khi refresh JWKS stale.
- Có distributed key trust state hoặc policy deployment riêng nếu cần revocation nhanh hơn JWKS TTL.
- Tách HTTP Bearer token validation với mTLS/DPoP sender proof.
- Thử trên phiên bản Spring/Nimbus thực tế vì API xây dựng decoder, key selection và caching có thể thay đổi.

### Điều gì xảy ra nếu chỉ cập nhật JWKS?

Nếu JWKS endpoint đã gỡ K-old nhưng local Nimbus/JWKSource vẫn cache key cũ theo cache policy, một JWT cũ có chữ ký đúng có thể tiếp tục được verify. Vì vậy **không dựa duy nhất vào thao tác HTTP publish** để xác nhận key revocation đã có hiệu lực ở mọi instance.

### Khi registry trạng thái bị lỗi

Không bật một nhánh fallback như:

~~~text
if revocationRegistryUnavailable:
    acceptAnyJwtWithValidSignature()
~~~

với trust domain cần key revocation khẩn cấp. Tùy risk policy, có thể fail closed, tạm dừng endpoint nhạy cảm hoặc dùng một **trusted snapshot** còn trong freshness SLO. Không mặc định stale trust được phép kéo dài vô hạn.

## 25. API Gateway và service mesh: header spoofing sau key revoke

Một số kiến trúc cho gateway kiểm JWT, rồi gửi principal metadata cho backend.

~~~mermaid
flowchart LR
    C["Client Bearer JWT"] --> G["API Gateway JWT verification"]
    POL["Trusted key revocation policy"] --> G
    G -->|"Authenticated internal context"| O["Orders Service"]
    G -->|"Authenticated internal context"| P["Payments Service"]
~~~

Đúng khi:

1. Gateway được cấu hình **trusted issuer JWKS và key revoke state**.
2. Client Internet không thể bypass gateway để vào backend.
3. Gateway xóa/ghi đè các headers do client tự gán như X-Authenticated-Subject hoặc X-Token-Valid.
4. Gateway→backend được xác thực và bảo vệ; backend biết context từ đúng gateway.
5. Backend vẫn kiểm **tenant/resource permissions** theo dữ liệu đáng tin.
6. Gateway có bằng chứng đã áp **revocation generation** cho key K-old.

Sai:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
X-Token-Valid: true
X-Token-Key-Revoked: false
X-Authenticated-Subject: admin
~~~

Client có thể tự gửi các headers này; **chúng không thay JWT verification**. Nếu gateway kiểm token nhưng hậu trường cho phép bypass, backend cần cơ chế kiểm riêng hoặc chặn mọi path không tin cậy.

### Logical Resource Server

Nếu gateway là logical RS của nhiều backend, audience và authorization rules cần có hợp đồng rõ. Một token ký hợp lệ cho Orders không tự được Payments nhận chỉ vì gateway chung tin signing key đó.

## 26. Tình huống vận hành thực tế

### Case A — Rotation bình thường

AS đổi từ K-old sang K-new theo lịch. K-old vẫn an toàn và còn JWT hợp lệ chưa hết hạn.

**Đúng:** prepublish public K-new, xác minh RS readiness, chuyển ký mới sang K-new, giữ K-old ở trạng thái **SIGN_DISABLED + VERIFY_TRUSTED** đến khi token cuối cùng hết hạn theo policy; sau đó mới retire.

**Sai:** coi rotation là compromise và xóa K-old public key ngay mà không có kế hoạch tác động tới user.

### Case B — Private RSA key xuất hiện trong CI artifact

Một pipeline xuất private K-old vào artifact có thể tải công khai. Orders/Payments verify JWT offline.

**Đúng:** giữ evidence an toàn, disable Sign, rút public K-old khỏi **toàn bộ trusted verifier set**, sinh K-new sạch, kiểm từng RS/replica và điều tra forged JWT. **Không chỉ** nhìn KMS DisableKey success vì attacker có thể đã copy private key.

### Case C — HS256 secret bị lấy từ Reports

AS, Reports và Orders dùng chung K. Reports bị xâm phạm và K lộ.

**Đúng:** revoke/rotate **cùng secret ở mọi verifier** trong trust domain, cấp lại token, kiểm scope/audience, điều tra credential leakage và cân nhắc chuyển sang ký bất đối xứng. Chỉ đổi secret ở AS trong khi Orders còn tin K-old là sai.

### Case D — private_key_jwt client key bị lộ

Client nightly-worker bị mất private key, nhưng AS signing key vẫn an toàn.

**Đúng:** AS thu hồi **client verification key**, client đăng ký key mới, kiểm token endpoint từ chối assertions K-old và đánh giá các AT đã phát. Không cần revoke AS signing key nếu không có bằng chứng AS bị compromise.

### Case E — Replica giữ JWKS stale

Orders replica A đã áp TRUST_REVOKED(K-old), replica B vẫn cache public K-old. Load balancer có thể đưa forged JWT tới B.

**Đúng:** đo required coverage từng replica, cô lập B nếu quá SLO, invalidate JWKS cache, ưu tiên revoked state trước fetch stale, chạy probes có kiểm soát. Một thử nghiệm A trả 401 **không chứng minh** cả service đã an toàn.

### Case F — KMS Sign permission bị lạm dụng

Attacker chiếm quyền gọi Sign nhưng chưa rõ private bytes đã bị export. Key có thể non-exportable mà vẫn bị dùng để ký token quyền cao.

**Đúng:** khóa caller/IAM, điều tra signing audit, đánh giá issuance ledger và risk; có thể phải rút trust K-old nếu không thể bảo đảm token nào được ký hợp pháp. Non-exportable không phải miễn nhiễm signing-oracle abuse.

### Case G — DPoP device key bị lộ

Access token ràng DPoP thumbprint, attacker có private DPoP key của device nhưng không có AS signing key.

**Đúng:** revoke AT/grant ràng key cũ, cấp DPoP key mới và token mới, kiểm sender proof và replay protection. Không revoke toàn bộ AS signing keys vì một device bị lộ.

### Case H — Dùng kid mới cho đúng key material cũ

K-old bị revoked dưới kid=key-1; một job đăng ký lại chính public/private K-old dưới kid=key-2.

**Đúng:** trust registry từ chối đăng ký lại **revoked fingerprint/key material**. Chặn theo một nhãn kid là không đủ.

### Case I — AS ký claims sai nhưng key vẫn an toàn

AS có bug cấp payments:approve cho client chỉ được payments:read.

**Đúng:** sửa issuance policy, ngăn token mới, revoke token/grant đã overgrant, RS kiểm permission. **Không tự kết luận signing key compromised** chỉ vì JWT đã ký chứa claims sai.

## 27. Phân biệt kết quả revocation và lỗi vận hành

| Quan sát | Kết luận được phép | Hành động tiếp theo |
| --- | --- | --- |
| **KMS DisableKey trả success** | Ngừng dùng key theo KMS policy. | Kiểm RS còn tin public key hay không. |
| **JWKS không còn K-old** | Publisher đã thay key set. | Kiểm cache, replicas, offline consumers. |
| **Một RS trả 401** | RS đó từ chối một request. | Kiểm mọi verifier bắt buộc. |
| **JWT ký K-old vẫn verify toán học** | Signature khớp public key. | Trust policy vẫn phải reject revoked key. |
| **K-old VERIFY_ONLY** | Rotation bình thường nếu key an toàn. | Retire sau TTL. |
| **Private key lộ nhưng RS còn tin** | Có nguy cơ forged JWT. | Emergency trust removal. |
| **HMAC secret lộ ở RS** | Mọi nơi dùng chung secret có nguy cơ. | Rotate/revoke toàn trust domain. |
| **Client auth key lộ** | AS có nguy cơ nhận client assertion giả. | Revoke client key và xử lý AT/grant liên quan. |
| **mTLS cert revoked, AT còn hạn** | Certificate và AT lifecycle tách biệt. | Kiểm mTLS proof và token binding; revoke AT nếu cần. |
| **DPoP key rotated** | Client có key mới. | AT ràng key cũ vẫn cần xử lý riêng. |
| **JWKS timeout** | Không refresh được trust metadata. | Fail closed hoặc fresh trusted snapshot theo policy. |
| **Broker delivery ACK** | Message đã được giao. | Đợi applied-generation/enforcement evidence. |
| **Event generation cũ tới muộn** | Có out-of-order delivery. | Bỏ qua stale event, giữ revoked state. |
| **JWKS stale fetch tới sau revoke** | Có cache race. | Không re-trust K-old. |
| **RT vẫn refresh được sau key revoke** | Key revocation không tự đóng grant. | Xử lý RT/client credential nếu compromised. |
| **OIDC RP session vẫn sống** | Session riêng chưa bị terminate. | Logout/session controls khi scope incident yêu cầu. |
| **Admin revoke sai issuer** | Key identity/authorization policy lỗi. | Dừng side effects, audit và sửa theo approval. |

### Tránh false confidence

Không kết luận toàn hệ thống đã chặn K-old chỉ dựa vào một trong các tín hiệu sau:

- Admin console hiện chữ Success.
- Database có verification_state=REVOKED.
- KMS trả HTTP 200.
- Public K-old bị gỡ khỏi JWKS.
- Một RS trả 401.
- Broker báo publish thành công.
- Token không còn xuất hiện trên dashboard metrics.

Cần chứng minh **signing cutoff**, **trusted key removal tại mọi verifier bắt buộc** và việc kiểm JWT type/audience/permission vẫn hoạt động.

## 28. Negative tests và fault-injection cho key revocation

Các test nên được chạy trên **key và JWT thử nghiệm được phép**, không sao chép private key production sang một môi trường lạ.

| Trường hợp | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| **Routine rotate** | K-old ngừng ký, chưa compromise, AT cũ còn hạn. | RS vẫn verify token cũ theo policy verify-only. |
| **Old key Signing disabled** | AS gọi Sign bằng K-old. | Sign bị từ chối, không mint JWT mới. |
| **Private K-old compromised** | AS đã revoke trust K-old. | RS từ chối mọi JWT ký K-old thuộc scope. |
| **JWT cũ chưa hết hạn** | JWT K-old có exp tương lai. | Vẫn từ chối nếu key trust revoked. |
| **Tampered JWT** | Sửa một byte payload, giữ signature. | Verify thất bại. |
| **Forged JWT với jti mới** | Dùng K-old compromised ký token jti ngẫu nhiên. | RS từ chối do revoked key, không cần biết jti trước. |
| **Forged JWT iat trong quá khứ** | K-old ký claims iat trước lúc phát hiện incident. | Không bypass key revoke. |
| **K-old under new kid** | Đăng ký cùng key material với kid mới. | Registry chặn theo trusted fingerprint. |
| **Duplicate kid trong issuer** | Hai keys cùng kid gây mơ hồ. | Key registry/decoder từ chối hoặc giải quyết theo policy an toàn. |
| **Same kid across issuers** | Issuer A/B cùng kid. | Không chọn public key sai issuer. |
| **Wrong issuer** | JWT có signature hợp lệ với key issuer B. | RS tin issuer A từ chối. |
| **Wrong audience** | AT Orders gửi Payments. | Payments từ chối dù key trusted. |
| **Wrong token type** | ID token đúng chữ ký đưa đến API. | RS từ chối type/profile. |
| **Expired token** | JWT exp đã qua. | Từ chối dù key chưa revoked. |
| **Missing scope** | Token chỉ read gọi approve. | Từ chối authorization. |
| **Cross-tenant access** | Token đúng nhưng resource tenant sai. | Từ chối theo policy tài nguyên. |
| **Untrusted jku** | Header chỉ tới JWKS attacker. | RS không fetch/tin URL đó. |
| **Unknown kid** | Header kid không có trong trusted issuer keys. | Từ chối hoặc refresh trusted JWKS giới hạn, không fail-open. |
| **kid path traversal** | Header chứa chuỗi thao túng đường dẫn. | Không đọc file/cấu hình ngoài trust registry. |
| **alg=none** | JWT unsigned. | API cần signed AT từ chối. |
| **HS/RS confusion** | Dùng RSA public bytes để tạo HS256 tag. | RS256 verifier từ chối. |
| **Wrong key type** | JWK oct dùng cho PS256. | Từ chối algorithm/key-type mismatch. |
| **Expired X.509 certificate** | mTLS cert không còn hạn. | Client auth/RS proof từ chối theo PKI policy. |
| **Revoked X.509 certificate** | Cert trong CRL/OCSP theo profile. | Verifier có revocation checking từ chối. |
| **Raw JWK không có CRL** | JWT verify raw public JWK. | Hệ thống không giả định OCSP xử lý key revoke. |
| **HS256 secret compromised** | Một RS lộ K-old. | Mọi RS liên quan ngừng verify K-old. |
| **Client private_key_jwt key revoked** | Attacker dùng assertion ký K-old. | AS từ chối client authentication. |
| **Client key mới** | Client gửi assertion bằng K-new đúng registration. | AS xác thực theo profile và grant policy. |
| **Client key revoke, AT còn hạn** | AT đã phát trước đó. | Kiểm token/grant revocation riêng; không giả định tự inactive. |
| **DPoP key compromised** | Request dùng AT cũ với key đã revoked theo policy. | RS/AS chặn bound token theo cơ chế được thiết kế. |
| **DPoP proof sai key** | Proof không khớp cnf. | Từ chối sender binding. |
| **RT còn usable sau key revoke** | Cùng user có RT/grant active. | Test phơi bày scope khác; không mặc định key revoke khóa RT. |
| **Opaque AT active=true** | AS signing JWT key bị revoked. | Không tự kết luận opaque AT inactive; áp contract token/grant. |
| **KMS Sign unauthorized** | RS hoặc attacker gọi Sign. | Bị IAM/policy từ chối, audit. |
| **KMS disabled but signing cache stale** | Worker cố Sign với K-old. | Sign fail hoặc issuance bị chặn theo generation fencing. |
| **KMS Sign API abuse** | Caller hợp lệ gửi payload ngoài scope. | Issuance/signing policy từ chối. |
| **JWKS cache stale** | RS cache public K-old sau emergency revoke. | Key revocation state thắng cache, JWT K-old bị từ chối. |
| **Stale fetch after revocation** | JWKS cũ về sau event REVOKED. | Không chuyển key trở lại TRUSTED. |
| **Out-of-order events** | Generation 41 đến sau 42. | RS giữ generation 42 và REVOKED. |
| **Duplicate revocation event** | Broker giao lại event. | Consumer idempotent, không side effects mới. |
| **Missing event** | Một RS bị offline trong lúc publish. | Replay/snapshot/reconciliation, không báo ENFORCED sớm. |
| **New replica bootstrap** | Instance mới tải stale JWKS snapshot. | Đọc trusted revocation state trước traffic nhạy cảm. |
| **Partial propagation** | 3/4 RS đã apply. | Operation báo PARTIALLY_ENFORCED. |
| **Fake applied ACK** | Broker delivered, validator chưa đổi. | Không coi là enforcement ACK. |
| **Revocation registry timeout** | RS không lấy state mới. | Fail closed hoặc trusted fresh snapshot theo risk policy. |
| **JWKS outage** | Remote trusted JWKS không phản hồi. | Không tải key từ URL do token đề xuất; dùng policy an toàn. |
| **Rollback to compromised K-old** | K-new rollout lỗi, operator chọn K-old. | Quy trình chặn tái kích hoạt key compromised. |
| **Backup restore K-old** | DR khôi phục bản key đã revoked. | Bị phát hiện/chặn, không cấp lại Sign/trust. |
| **Secret/private key in logs** | Audit/CI xuất key material. | DLP/secret scanning phát hiện; xử lý incident. |
| **Cross-environment trust** | JWT staging được trình ở production. | Production RS từ chối issuer/key/trust domain sai. |
| **Key revoke wrong tenant** | Admin chỉ có quyền tenant-blue, target tenant-green. | Backend từ chối, không mutate state. |
| **Admin thiếu approval** | Bulk key revoke có blast radius lớn. | Không thực hiện khi thiếu control bắt buộc. |
| **Same idempotency key, new payload** | Retry key cũ với target khác. | 409 conflict, không revoke nhầm. |
| **Repeated same request** | Retry đúng operation. | Kết quả idempotent, không undo state. |
| **Admin operation committed but KMS failed** | Registry revoked nhưng Sign chưa disable. | Báo trạng thái partial/error, escalate. |
| **JWT profile under shared key** | K-old ký cả AT/ID token. | RS và RP thuộc affected coverage được xử lý. |
| **Gateway bypass** | Caller đi thẳng vào backend. | Không bỏ qua required authentication/trust control. |
| **Header spoofing** | Client tự gửi X-Token-Valid=true. | Backend không tin untrusted header. |

### Bộ test tối thiểu cho emergency revoke

~~~text
A. AS/KMS: Sign with K-old -> DENY.
B. Orders RS: signed JWT K-old, exp future -> DENY.
C. Payments RS: signed JWT K-old, exp future -> DENY.
D. Unknown/new kid pointing at same K-old material -> DENY.
E. Stale JWKS response / out-of-order event -> keep REVOKED.
F. K-new trusted JWT correct aud/scope -> normal authz checks.
G. K-new trusted JWT wrong aud/scope -> DENY.
H. All mandatory verifier targets reported applied generation.
~~~

**Một token thử ký K-old phải được tạo trong môi trường kiểm thử có kiểm soát hoặc từ fixture được ủy quyền.** Không phổ biến raw compromised private key để chạy probes trên production.

## 29. Checklist triển khai và vận hành key revocation

1. **Purpose:** Đã phân biệt AS signing, client signing, HMAC, mTLS, DPoP, JWE keys?
2. **Issuer:** Key thuộc issuer, environment, tenant hoặc trust domain nào?
3. **Identity:** Có trusted public-key fingerprint, kid aliases, alg/kty/use và key handle?
4. **Incident:** Có bằng chứng, incident ID, severity và time window?
5. **Scope:** Đã xác định mọi RS/RP/gateway/replica đang tin key?
6. **Signing capability:** KMS/AS đã ngừng Sign bằng K-old?
7. **Verification trust:** Mọi required verifier đã rút trust K-old?
8. **Routine rotation:** Có phân biệt VERIFY_ONLY hợp lệ với compromised key?
9. **JWT offline:** Có cơ chế trạng thái/deny/trust refresh ngoài expiry khi cần?
10. **JWKS:** Đã thay public key set qua trusted issuer metadata?
11. **Cache:** JWKS/JWT decoder caches có thể bị invalidate và không resurrect key?
12. **Fingerprint:** Revocation không chỉ dựa vào chuỗi kid do token khai?
13. **Multi-issuer:** Không trộn key sets hoặc thu hồi nhầm issuer vì kid trùng?
14. **Alg policy:** Không chấp nhận alg=none hoặc HS256/RS256 confusion?
15. **Token validation:** Vẫn kiểm iss, aud, typ, exp, scope, principal và permission?
16. **HMAC:** Khi secret lộ, có xử lý mọi RS cùng giữ secret?
17. **Client auth:** private_key_jwt/mTLS key bị lộ có chặn token endpoint?
18. **DPoP:** Có xử lý AT ràng với key bị lộ và proof verification?
19. **Opaque/RT:** Có đánh giá token/grant revocation riêng, không suy tự inactive?
20. **OIDC:** Có xử lý ID token trust và RP/OP sessions theo scope?
21. **Trust state:** Hai trục Sign và Verify có version/generation riêng hoặc nhất quán?
22. **Events:** Outbox, event authentication, idempotency, ordering và reconciliation?
23. **Offline RS:** Bootstrap từ trusted snapshot trước khi phục vụ traffic nhạy cảm?
24. **SLO:** Đã đo signing cutoff, verification enforcement và coverage lag?
25. **Fail-closed:** RS không bypass khi registry/JWKS unavailable?
26. **KMS permissions:** Admin/Signer/Verifier/Incident responder có least privilege?
27. **Approval:** Key revoke diện rộng có MFA/JIT/dual control theo policy?
28. **Audit:** Có immutable incident, actor, target, key fingerprint, applied evidence?
29. **Key material:** Không log private key/HMAC secret hoặc raw JWT/RT?
30. **Recovery:** K-new sinh từ môi trường sạch, có public JWKS và RS readiness?
31. **No resurrection:** Không rollback/restore/register lại compromised K-old?
32. **Negative tests:** Đã kiểm forged jti/iat, stale caches, alias kid, AS/RS race và offline replicas?
33. **Partial failure:** Không báo ENFORCED nếu thiếu một required verifier?
34. **Postmortem:** Đã cập nhật runbook, trust policies, token TTL, KMS IAM và test coverage?

## 30. Bài tập vận dụng: quyết định revoke đúng đối tượng

### Bài tập 1 — JWT bị lộ, signing key không lộ

Một access token JWT cho Orders xuất hiện trong log. KMS audit không ghi nhận key export, issuer không có dấu hiệu signer compromise. Token còn hạn 20 phút.

**Câu hỏi:** Có cần emergency key revocation không?

**Phân tích:** Trọng tâm trước mắt là **revoke token hoặc grant liên quan**, bảo vệ log/credential, kiểm Orders RS thực hiện deny/introspection theo SLO. Thu hồi signing key của toàn issuer có thể tạo downtime diện rộng mà không cần thiết nếu không có bằng chứng key bị lộ. Nếu điều tra mới phát hiện private key cũng bị lộ, phải mở rộng sang key revocation.

### Bài tập 2 — KMS Sign disabled nhưng forged JWT vẫn được nhận

AS đã disable K-old ở KMS và công bố public K-new. JWT giả ký K-old còn được một RS trả HTTP 200.

**Câu hỏi:** Thiếu control gì?

**Phân tích:** RS chưa **rút verification trust với K-old**. Cần trusted revocation policy/cache invalidation trên mọi verifier, kiểm local key aliases/replicas, xác nhận K-old không tự được trust lại sau refresh.

### Bài tập 3 — Thu hồi key của OAuth client

AS sử dụng PS256 để ký AT. Client cron-worker xác thực bằng private_key_jwt. Private key cron-worker bị lộ, nhưng private key AS vẫn trong HSM an toàn.

**Câu hỏi:** Thu hồi key nào và token nào?

**Phân tích:** AS phải ngừng tin **public verification key của cron-worker** cho client authentication, rotate client credential, chặn issuance mới bằng key cũ. Các AT/grants đã cấp trong incident window cần rà soát và revoke tùy risk; không tự revoke signing key PS256 của AS.

### Bài tập 4 — Same kid, different issuers

Issuer A và issuer B đều có kid=key-1. Admin muốn revoke key Issuer A vì private key đã lộ.

**Câu hỏi:** Chặn theo kid=key-1 toàn hệ thống có đúng không?

**Phân tích:** Không. Key trust identity phải gồm **issuer và trusted public-key fingerprint** (và purpose/environment khi thích hợp). Chặn mọi key-1 trên issuer B có thể gây outage không liên quan; đồng thời chỉ chặn A/key-1 có thể bỏ sót alias khác cùng compromised key material.

### Bài tập 5 — JWKS cache và outage

Orders RS offline lúc event revoke xảy ra, sau đó khởi động lại với public JWKS snapshot chứa K-old.

**Câu hỏi:** Cho phép phục vụ ngay có an toàn không?

**Phân tích:** Không mặc định. Nếu SLO key revocation yêu cầu trạng thái mới, RS phải load **trusted revocation snapshot/replay** hoặc fail closed trong phạm vi bị ảnh hưởng trước khi nhận JWT. Việc dùng stale JWKS vô thời hạn có thể làm compromised key sống lại.

### Sơ đồ quyết định tổng hợp

~~~mermaid
flowchart TD
    A["Credential/token/key có dấu hiệu compromise"] --> B{"Signing/MAC key material bị lộ hoặc Sign authority bị lạm dụng?"}
    B -->|Không rõ/không| T["Xem token/grant/session revocation và tiếp tục điều tra"]
    B -->|Có| K{"Key thuộc trust domain nào?"}
    K -->|AS private signing key| AS["Disable AS Sign + revoke verifier trust"]
    K -->|HS256 shared secret| HS["Rotate secret tại AS và mọi verifier"]
    K -->|OAuth client auth key| CL["AS ngừng tin client key + chặn issuance"]
    K -->|DPoP hoặc mTLS key| CN["Revoke bound AT / client certificate trust theo profile"]
    AS --> V["Phát tán policy, kiểm từng RS/RP"]
    HS --> V
    CL --> V
    CN --> V
    T --> V
    V --> R["Audit, enforce SLO, recovery bằng credential sạch"]
~~~

## Kết luận

**Key revocation trong token security không chỉ là xóa một public key khỏi JWKS hoặc disable private key trong KMS.** Nó là quy trình quản trị toàn bộ **quyền ký và quyền tin cậy để xác minh** tại từng thành phần trong hệ thống OAuth 2.0/OIDC.

- **Routine rotation** có thể cho phép key cũ ở trạng thái verify-only đến khi JWT hợp lệ hết hạn.
- **Key compromise** thường đòi **ngừng Sign và rút verification trust khẩn cấp**; nếu private key đã lộ, attacker có thể tạo JWT giả với jti/iat tùy ý.
- **HS256 secret** phải được thu hồi ở mọi verifier cùng biết secret; còn **asymmetric public key** có thể công khai nhưng không được tiếp tục là trust anchor khi private component bị lộ.
- **OAuth client private_key_jwt, mTLS và DPoP keys** có trust boundary khác AS signing key; thu hồi đúng đối tượng và xử lý AT/grant liên đới khi cần.
- **JWKS caching, static keys, offline replicas, event ordering và issuer/kid aliases** quyết định độ trễ thực tế của việc rút trust.
- **RFC 7009 token revocation, RFC 7662 introspection và CRL/OCSP cho X.509** không tự thay một cơ chế key revocation được thiết kế riêng.
- Key revocation cần **MFA/approval, state generation monotonic, idempotent operations, fail-closed, audit, negative tests và coverage SLO**.

Nguyên tắc kết thúc incident là: **chỉ tuyên bố thu hồi khóa thành công khi nguồn ký đã bị kiểm soát và mọi verifier bắt buộc thực sự từ chối key bị thu hồi**, đồng thời các credential/grant khác còn có khả năng cấp token mới đã được xử lý theo phạm vi sự cố.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8037 — CFRG Elliptic Curve EdDSA for JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8705 — Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)](https://www.rfc-editor.org/rfc/rfc6960)
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)









