# Ứng phó sự cố mất tin cậy đối tác, lộ khóa và thu hồi phiên diện rộng

**Sự cố federation không kết thúc khi đổi mật khẩu hoặc thay chứng chỉ.** Nếu một Identity Provider (IdP), OpenID Provider (OP), SAML signing certificate, OAuth signing key, service keytab hoặc quan hệ tin cậy với đối tác bị xâm phạm, các phiên đã hình thành có thể tiếp tục dùng được; JWT có thể vẫn được Resource Server chấp nhận; metadata/JWKS cache có thể giữ khóa cũ; các ứng dụng downstream có thể không nhận được tín hiệu logout. Hậu quả có thể là **đăng nhập giả mạo, chiếm tài khoản, truy cập xuyên tenant và duy trì quyền sau khi tổ chức đã ngừng tin đối tác**.

**Nguyên tắc ứng phó:** trước tiên **cô lập nguồn trust bị ảnh hưởng tại tất cả điểm quyết định**, sau đó **thu hồi HTTP sessions, refresh tokens, access tokens, SAML/OIDC sessions và các credentials phụ thuộc theo đúng loại**, đồng thời **bảo toàn chứng cứ** và **thay khóa qua kênh đã kiểm chứng độc lập**. Không coi việc thay key trên IdP là đủ, không coi SAML Single Logout/OIDC back-channel logout là “global kill switch” tuyệt đối, và không mở lại issuer chỉ vì JWKS mới tải được.

Bài thuộc **Spring Security – federation → Triển khai và vận hành**, tập trung incident response đối với OIDC/OAuth2, SAML2, Kerberos/SPNEGO và quan hệ đối tác đa tenant. Có sơ đồ trust graph, bảng phân loại compromise, quy trình containment–eradication–recovery, cách tổ chức Spring Security/Spring Session, Java 17 runnable mô phỏng trust epoch và thu hồi phiên, ma trận kiểm thử, checklist diễn tập và liên kết chuẩn chính thức.

> **Phạm vi:** Đây là hướng dẫn bảo vệ hệ thống do bạn có quyền vận hành. Thay đổi trust, thu hồi hàng loạt hoặc điều chỉnh khóa trong thực tế phải theo quyền vận hành/incident commander và change control của tổ chức; bài sử dụng tên miền, tài khoản và khóa giả lập.

## 1. Mục tiêu học tập

Sau bài này, kỹ sư có thể:

1. Phân biệt **mất tin cậy đối tác** với **lộ signing key**, **lộ SP private key**, **lộ client secret** và **lộ keytab**.
2. Định vị phạm vi tác động theo **issuer/entityID, đăng ký IdP, client ID, key ID, tenant, service và ứng dụng downstream**.
3. Thiết kế **quarantine/fail-closed** tại ingress login, SAML Response consumer, JWT Resource Servers và session authorization.
4. Giải thích vì sao **key rotation ≠ token/session revocation**.
5. Phân biệt logout cục bộ, OIDC back-channel logout, SAML SLO, OAuth token revocation/introspection và application-enforced invalidation.
6. Thu hồi hàng loạt Spring HTTP sessions trên nhiều nodes mà không dựa vào một `SessionRegistryImpl` cục bộ.
7. Thiết kế **trust epoch / reauthentication generation** để chặn các session lọt khỏi index.
8. Tránh lỗi cross-tenant khi một issuer phục vụ nhiều tổ chức hoặc một tenant tin nhiều IdPs.
9. Xây runbook, RACI, metrics, quyết định mở lại và kiểm thử fail-closed.
10. Viết demo Java 17 độc lập chứng minh policy quarantine, revocation, stale epoch và cách ly tenant.

## 2. Những khái niệm phải tách bạch

| Khái niệm | Có nghĩa là | Không tự bảo đảm |
| --- | --- | --- |
| **IdP/OP trust** | RP/app chấp nhận chứng cứ do một issuer/IdP phát theo registration đã phê duyệt | Người dùng có quyền tenant |
| **Issuer** | ID của token issuer/AS, ví dụ `https://id.partner.test` | Signing key đang an toàn |
| **SAML entityID** | ID của asserting party/service trong SAML | Cert trong metadata chưa bị lộ |
| **JWK / signing certificate** | Public key xác minh chữ ký | Private key chưa bị đánh cắp |
| **Trust anchor / registration** | Bộ metadata, khóa, issuer, audience, binding, chính sách cho một nguồn | Session cũ đã hết |
| **HTTP session** | Phiên cục bộ của ứng dụng web | Token OAuth ở API đã mất hiệu lực |
| **OIDC OP session** | Phiên của user tại OP, có thể liên kết `sid` | Mọi RP session đã bị hủy |
| **SAML SLO** | Giao thức logout giữa các SP/IdP hỗ trợ | Các SP offline hoặc không tham gia cũng logout |
| **OAuth access token** | Credential dành cho Resource Server | Thu hồi ngay nếu đã phát dưới dạng self-contained JWT |
| **OAuth refresh token** | Cho phép xin access token mới | Việc thu hồi nó tự hủy mọi access token đã phát |
| **Kerberos ticket** | Bằng chứng truy cập service theo KDC/service key | Logout Spring session sẽ phá hủy TGT ở OS |
| **Trust epoch** | Phiên bản policy tin cậy do app quản lý | Thay cho kiểm chữ ký ban đầu |

**Không gộp** `sub`, email, `kid`, SAML NameID hoặc group name làm khóa toàn hệ. Identity phải giữ source namespace (OIDC `iss+sub`; SAML IdP entityID + stable NameID/attribute theo contract; Kerberos verified realm/principal).

## 3. Sơ đồ rủi ro lan truyền

~~~text
                     Partner IdP / OP / SAML
                      private signing key (?)
                               |
                    issuer metadata / JWKS
                               |
      +------------------------+-------------------------+
      |                        |                         |
  Portal RP             Billing API                 HR SAML SP
  Spring session        JWT Resource Server         SAML session
      |                        |                         |
  OAuth refresh         JWT access tokens           Downstream app
      |                        |                         |
      +------------------------+-------------------------+
                               |
                       Tenant A / Tenant B
                               |
                     Domain authorization
~~~

Nếu signing key của Partner bị lộ, attacker có thể tạo chữ ký trông hợp lệ đối với những consumers vẫn tin khóa đó. **Tải lại metadata hoặc logout một portal không cắt được tất cả các đường**. Cần inventory các **verifiers**, sessions, token consumers, keys, caches và downstream services.

**Đường kiểm soát ưu tiên:** cắt đường cấp *quyền truy cập mới và tiếp diễn* tại các điểm ứng dụng tự kiểm soát; nếu downstream của bên thứ ba không có khả năng quản trị, phối hợp và ghi nhận residual risk.

## 4. Phân loại sự cố trước khi chọn biện pháp

| Tình huống | Ranh giới bị phá | Phạm vi đầu tiên cần xét |
| --- | --- | --- |
| **Đối tác mất tin cậy** (hợp đồng chấm dứt, IdP takeover, metadata supply-chain) | Trust relationship, issuer/IdP registration | Mọi login/verification và account links từ đối tác đó |
| **OIDC/OAuth signing private key lộ** | Chữ ký ID Token/JWT access token | Mọi consumers đang tin key; cả token cũ và mới có thể không phân biệt được |
| **SAML IdP signing private key lộ** | Chữ ký Response/Assertion/LogoutRequest | Tất cả RPs tin cert/key đó, kể cả assertions có `IssueInstant` giả |
| **SAML SP signing private key lộ** | Danh tính RP đối với IdP và các protocol messages | Các IdPs tin SP signing key đó |
| **SAML SP decryption key lộ** | Confidentiality của encrypted Assertions | Assertions bị thu thập có thể lộ; phải xét dữ liệu trong quá khứ |
| **OAuth client secret/private key lộ** | Client authentication với AS | Token issuance/grants, client_credentials, refresh token exposure |
| **Spring session store / cookie key lộ** | Local sessions, server-side session hijack/forgery tùy design | Tất cả users/apps dùng chung secret/store |
| **Kerberos HTTP service keytab lộ** | Service credential/SPN | Ticket decryption/service impersonation và các SPNs dùng chung account |
| **TLS private key hoặc truststore bị thay** | Channel identity/transport integrity | Endpoints/phạm vi dựa trên TLS key hoặc trust config |

**Lộ public signing certificate không phải lộ private key**: public key được công khai để verifiers xác minh. Phải phân biệt *public metadata bị xem* với *private key bị chiếm*, *private key nghi bị chiếm* và *IdP phát token sai*.

## 5. Mức độ nghiêm trọng: điều gì làm tăng priority?

Đánh giá theo business impact và thực tế kỹ thuật, không chỉ tên thuật toán:

- **Reach:** signing key dùng cho bao nhiêu tenants, applications, RPs, APIs, environments?
- **Trust:** có claims admin hoặc quyền tài chính/PII được ký bằng key này không?
- **Token validity:** JWT có lifetime dài, refresh token rotation và introspection không?
- **Session lifetime:** long-lived HTTP session, remember-me, downstream sessions?
- **Evidence:** đã thấy token giả/mass login, key xuất hiện ngoài vault, metadata thay đổi trái phép?
- **Control:** có kill switch central hay phải cập nhật từng microservice?
- **External exposure:** keys/metadata đã chia sẻ cho third-party verifiers?
- **Service availability:** tắt partner làm gián đoạn workflow nào; có đường break-glass tách biệt không?
- **Regulatory/customer impact:** dữ liệu cá nhân, ngành quản lý đặc biệt, notification obligations?
- **Cross-tenant:** cùng issuer phục vụ cả tenants không bị ảnh hưởng và tenants đã bị xâm nhập?

**Khi chưa chắc private key đã bị đánh cắp nhưng có bằng chứng đáng tin**, cần áp mức containment theo blast radius và risk appetite; không chờ forensic kết luận tuyệt đối rồi mới chặn forgery khả dĩ.

## 6. Các vai trò trong war room

| Vai trò | Chịu trách nhiệm chính |
| --- | --- |
| **Incident Commander (IC)** | Ưu tiên, phạm vi, quyết định chặn/mở lại, nhật ký thời gian |
| **IAM/IdP owner** | Issuer/SAML metadata, keys, user/session revocation phía IdP |
| **Spring app owner** | Login filters, client registration, HTTP sessions, local access |
| **API / Resource Server owner** | JWT/opaque access-token rejection, cache, revocation guard |
| **Platform/SRE** | Secret store, service mesh, Redis/JDBC sessions, rollout, monitoring |
| **Security/forensics** | IOC, evidence chain-of-custody, log retention, scope, threat validation |
| **Customer/partner liaison** | Kênh xác minh độc lập, cập nhật trạng thái, hỗ trợ chuyển đổi |
| **Privacy/legal/compliance** | Đánh giá notification và nghĩa vụ báo cáo theo pháp luật/hợp đồng |
| **Business continuity owner** | Break-glass workflows, critical business availability |

**Không để một tenant admin tự khôi phục trust của chính IdP đang bị điều tra** nếu hành động đó bỏ qua security owner approval. Quyền cấu hình identity trust phải tách khỏi quyền business thông thường.

## 7. Chuỗi hành động tổng quát

~~~text
DETECT / VERIFY SIGNAL
         |
         v
DECLARE INCIDENT + preserve evidence
         |
         v
INVENTORY affected trust and consumers
         |
         v
QUARANTINE / fail closed (login + APIs + sessions)
         |
         v
REVOKE local sessions, refresh grants, tokens, delegated credentials
         |
         v
ERADICATE compromise, rotate keys via verified independent channel
         |
         v
ATTEST new issuer/IdP metadata, credentials, trusted mappings
         |
         v
RE-ENABLE selected flows with trust epoch increase
         |
         v
FORCE re-authentication + monitor + post-incident review
~~~

Đây là thứ tự khái niệm; **containment, evidence preservation và credential revocation có thể diễn ra song song** dưới sự điều phối IC. Điều cấm là mở lại trust dựa trên key/metadata mới xuất hiện từ **chính kênh đang bị chiếm** mà chưa có xác minh độc lập.

## 8. Tín hiệu xác định “mất tin cậy đối tác”

Một số dấu hiệu:
- IdP/OP gửi thông báo private signing key compromise.
- JWK set xuất hiện key mới không đi qua phê duyệt, hoặc thumbprint bất thường.
- SAML metadata trỏ signing certificate lạ, redirect tới endpoint không phê duyệt.
- Issuer/entityID vẫn đúng nhưng login claims/roles/subjects tăng đột ngột.
- Dữ liệu cho thấy account có verified issuer Partner nhưng truy cập tenant không có membership.
- Token JWT có `iat`/`jti` không phù hợp telemetry của AS; chữ ký vẫn verify.
- Chứng nhận partner trust đã hết hiệu lực hoặc yêu cầu hợp đồng ngừng dùng nguồn identity.
- Partner có sự cố DNS/metadata server compromise, hoặc user provisioning bị lạm dụng.

**Nguồn sự thật** là incident evidence + kênh liên lạc xác minh ngoài băng (out-of-band) và danh sách registration đã được duyệt. **Đừng coi “signature valid” là bằng chứng issuer chưa bị chiếm** nếu signer key chính là thứ nghi lộ.

## 9. Containment đầu tiên: deny trust, không chỉ xóa key

Trên từng consumer cần thực hiện:
1. Đặt trusted issuer/IdP registration vào trạng thái **QUARANTINED** trong control-plane đã xác thực.
2. Từ chối **new OIDC logins**, OAuth authorization callback, SAML Response từ profile đó.
3. Từ chối API Bearer JWT thuộc issuer/credential bị ảnh hưởng **trước hoặc cùng lúc với decoder**, kể cả các tokens ký hợp lệ.
4. Nếu có opaque access token, từ chối profile bị quarantine ngay cả khi introspection trả `active=true`.
5. Chặn session cũ có source registration/issuer bị quarantine bằng **per-request trust guard**; không chỉ xóa known sessions.
6. Tắt JIT provisioning/automatic account linking và group-role mapping từ source đó.
7. Gỡ/quarantine certificates/keys bị nghi compromised tại **mọi verifiers** hoặc áp policy deny có hiệu lực tức thì khi chưa thể rollout key stores.
8. Chặn ingestion event/log out-of-band chưa được authenticate, không cho partner tự gửi tín hiệu “incident đã xong”.
9. Bảo toàn audit logs, key version IDs, configuration snapshots theo quy trình forensic.
10. Duy trì break-glass admin login từ **nguồn độc lập**, ràng buộc MFA và theo dõi riêng.

**Xóa một JWK khỏi JWKS endpoint chưa chắc các Resource Servers ngừng tin ngay**: nhiều consumers cache JWK; một số có key pinning. Vì vậy cần control-plane deny/epoch tại các consumer và bằng chứng từ từng deployment.

## 10. SAML: khi IdP signing private key bị lộ

Một SAML Assertion được ký bằng private key bị đánh cắp có thể có **Issuer, NameID, group, Conditions và IssueInstant do attacker lựa chọn**. Các RPs còn tin certificate cũ có thể accept. Không xem timestamp là cách chắc chắn để biết assertion được phát trước hay sau compromise.

**Runbook SAML:**
1. Lập danh sách `RelyingPartyRegistration` và SPs đang trust cert đó.
2. Disable/quarantine asserting party registration; block new responses và phiên hiện có theo app policy.
3. Bảo toàn SAML Response identifiers/metadata fingerprints ở dạng không lộ attributes/PII.
4. Partner tạo **signing key mới trong môi trường được xác minh là sạch**; xác nhận ownership/kênh riêng.
5. Truyền public certificate/thumbprint mới qua approved metadata change process.
6. Kiểm expected IdP entityID, signed metadata trust, ACS/Destination, Audience, cert binding và algorithms.
7. Phân biệt overlap rotation bình thường với **compromise**: **không duy trì old compromised cert trusted** chỉ vì muốn giảm downtime.
8. Reload/rollout RelyingPartyRegistrationRepository/validators tới mọi SPs và kiểm old cert bị reject.
9. Revoke application sessions được tạo từ compromised asserting party, ép login lại sau trust restored.
10. Test SAML login, NameID namespace, group mapping, tenant isolation, replay/in-response correlation và SLO behavior.

**Lưu ý:** signed LogoutRequest bằng compromised IdP key cũng không còn trust. Không dùng một LogoutRequest lạ làm thẩm quyền thu hồi phiên vượt namespace nếu key đã nghi lộ; thực hiện revocation qua admin control-plane độc lập.

## 11. SAML: khi private key của Service Provider bị lộ

Cần phân biệt loại key:

- **SP signing key:** có thể dùng ký AuthnRequest/LogoutRequest, chứng minh client/SP identity với IdP nếu policy của IdP yêu cầu.
- **SP decryption key:** có thể giải mã EncryptedAssertion; lộ key đe dọa confidentiality của assertions đã bị thu thập.
- **Cùng một key dùng cả hai:** blast radius tăng, cần đánh giá cả authentication và confidentiality.
- **SAML IdP signing cert:** public trust key của đối tác, là role khác.

**Hành động:** lập danh sách IdPs tin SP signing cert hoặc dùng SP encryption cert; yêu cầu rotate/disable key qua kênh độc lập, cập nhật SP metadata và IdP registrations, ngừng sử dụng key lộ, kiểm test interoperability, phân loại lịch sử assertions có thể bị giải mã. Đừng chỉ đổi certificate hiển thị ở UI trong khi private key lộ vẫn hoạt động trên một node hoặc trong backup dùng được.

## 12. OIDC/OAuth: khi OP/Authorization Server signing key lộ

**Đối với ID Tokens:** RP có thể chấp nhận danh tính giả nếu còn tin signing key, kể cả `iss` và `aud` trông hợp lệ. Phải quarantine issuer/client registration, invalidate local sessions và refresh trust metadata.

**Đối với JWT access tokens:** Resource Server tự verify chữ ký. Nếu private signing key lộ, việc thay JWK tại AS **không tự bảo đảm mọi tokens trước đó bị từ chối ngay**; các Resource Servers có thể giữ old key trong cache, và key có thể vẫn được nhiều APIs trust.

**Ưu tiên:**
1. Chặn issuer/key tại **tất cả Resource Servers** bằng trusted deny policy.
2. Tăng trust epoch/cutoff cho sessions, tokens/grants theo source.
3. Rotate signing keys trong HSM/KMS/AS đã được xác minh độc lập.
4. Xác nhận metadata/JWKS new key qua một kênh không lệ thuộc hạ tầng bị chiếm.
5. Purge/invalidate stale decoder caches hoặc restart/rollout theo thiết kế.
6. Thử token ký bằng old compromised key phải **fail** ở mọi API.
7. Thử new token từ restored issuer đúng audience, alg, `iss`, `exp/nbf` và tenant policy.
8. Không dùng token `kid` chưa verify để tự download JWKS tùy ý.
9. Revoke refresh grants và sessions, force reauthentication theo blast radius.
10. Audit long-lived offline grants và machine clients cần rotation riêng.

**Không chỉ dựa vào `iat > incidentTime`:** kẻ có signing key có thể giả `iat`. Cutoff chỉ đủ khi khóa/timing và claims provenance đáng tin; khi key lộ, cần deny theo **key/issuer epoch** hoặc token validation state do server kiểm soát.

## 13. OAuth client secret hoặc client private key bị lộ

Một compromised client credential khác với OP token-signing key. Tấn công có thể gồm impersonate OAuth client, dùng `client_credentials`, redeem grants hoặc refresh tokens **nếu attacker còn có các yếu tố cần thiết**.

Runbook:
- Disable/quarantine client registration hoặc client auth key.
- Revoke client secret/private key/certificate bị lộ tại AS.
- Rotate client credentials ở secret manager, tất cả pods và workload identities; không commit vào config/Git.
- Revoke/rotate affected refresh grants; rà soát access tokens và service-to-service clients.
- Đánh giá redirect URI/consent/DPoP/mTLS bindings nếu áp dụng.
- Kiểm client authentications bất thường và API logs.
- Cập nhật secret theo least-privilege và hạn chế blast radius giữa tenants.
- Duy trì break-glass token issuance khác client, có MFA/admin approval.
- Kiểm पुराने credentials bị từ chối, mới thành công; không gửi tokens/keys vào incident chat.

**Đừng dùng lại client secret giữa môi trường, tenants hoặc nhiều đối tác**. Nếu key chung, scope phải mở rộng đến mọi integrations đã chia sẻ.

## 14. Kerberos HTTP keytab lộ: trường hợp liên quan federation

**Keytab** chứa keys của service principal, ví dụ `HTTP/portal.corp.test@CORP.TEST`. Lộ keytab có thể cho phép giải mã service tickets hoặc giả mạo service trong những điều kiện nhất định. Không đồng nhất với lộ **user password** hay OIDC issuer signing key.

Cần:
1. Xác định service account và **mọi SPNs** cùng dùng secret.
2. Disable/chặn affected services khi cần; rotate service account keys/KVNO có điều phối với KDC/AD.
3. Triển khai keytab mới tới toàn bộ nodes, xử lý overlap ticket lifetime có security policy.
4. Test old/new service tickets theo KVNO và đúng enctypes.
5. Chặn reuse keytab cũ trong containers/images/CI logs; kiểm secrets exposure.
6. Xóa hoặc cô lập app sessions có thể được tạo nhờ service bị mạo danh.
7. Đảm bảo không tự cấp quyền từ raw `REMOTE_USER`/header do proxy không tin kiểm soát.
8. Ghi nhận cross-realm referrals/SPN aliases và các services bị ảnh hưởng.

**Kerberos logout của ứng dụng không tự xóa OS TGT**, và reset service keytab không tự thu hồi mọi Spring sessions. Phải bảo vệ cả service trust và local authorization.

## 15. Thu hồi diện rộng: thứ tự kiểm soát quan trọng

Khi incident xảy ra, phân biệt:

1. **Stop accepting**: ngăn tạo/duy trì truy cập từ source compromise.
2. **Invalidate HTTP sessions**: cookie session của portal/RP không còn quyền.
3. **Revoke refresh tokens/grants**: ngăn xin access tokens mới.
4. **Invalidate/deny access tokens**: API không tiếp tục nhận tokens đã phát.
5. **Stop downstream delegation / service credentials**.
6. **Trigger logout signals** khi IdP/SP còn trust và protocol hoạt động.
7. **Apply account and tenant emergency denies** tại domain/object authorization.
8. **Force reauthentication** sau khi trust được khôi phục.
9. **Verify propagation** trên tất cả services/nodes, không chỉ UI.
10. **Maintain incident hold** cho các identities/tenants nghi ngờ abuse dù issuer đã phục hồi.

**Chú ý:** thứ tự logic là chặn trước, nhưng không cần chờ hoàn tất số lượng lớn session deletion mới áp deny; per-request quarantine guard giúp giảm khoảng hở.

## 16. Các loại session/token phải có hành động riêng

| Credential/phiên | Nơi quản lý | Hành động khả dụng | Hạn chế |
| --- | --- | --- | --- |
| Spring `HttpSession` | App/Spring Session | Invalidate/delete hoặc deny bằng epoch | Multi-node store, request đang chạy |
| `SecurityContext` | Spring request/session | Clear current context, deny next requests | Thread/request khác có thể vẫn đang chạy |
| OIDC RP session | Mỗi RP | Local invalidation hoặc validated back-channel logout | Không tự bao phủ toàn bộ RPs |
| OIDC OP session | OP | OP logout/session revoke | Không đảm bảo RPs offline cập nhật ngay |
| OAuth refresh token | AS | RFC 7009 revocation, revoke grant | Không tự chắc chắn access JWT cũ mất |
| OAuth opaque access token | AS/introspection | Revoke và introspection `active=false` | Caches và RS authorization policy |
| OAuth JWT access token | RS/AS | Deny issuer/key/epoch, denylist, lifetime | Offline validation không có central revocation mặc định |
| SAML SP local session | Mỗi SP | Local invalidation, SLO nếu được hỗ trợ | SLO không chắc đến mọi app |
| SAML IdP session | IdP | IdP-side session revoke | SP chưa nhận SLO vẫn có local session |
| Kerberos OS TGT/service ticket | KDC/client/acceptor | KDC/account/key rotation, ticket lifetime | Không phải cùng namespace HTTP session |
| Mobile/app offline token | Client/server | Revoke/deny next online use, device policy | Thiết bị offline không thể bị “xóa tức thì” từ xa |

**Từ “thu hồi ngay” chỉ nên dùng khi có bằng chứng request đến Resource Server đã bị từ chối**, không chỉ vì đã gửi lệnh revoke tới IdP.

## 17. OAuth token revocation (RFC 7009): nên hiểu chính xác

RFC 7009 định nghĩa **token revocation endpoint**. OAuth client có thể yêu cầu AS thu hồi token; AS invalidates token đó và có thể thu hồi các tokens liên quan cùng grant theo policy.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: as.example.test
Authorization: Basic <CLIENT_AUTH_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_EXAMPLE&token_type_hint=refresh_token
~~~

Đây là **pseudo-request không chạy được**, placeholder chỉ mô tả hình thức; không lưu real client credentials trong bài test/log.

**Các giới hạn:**
- Revocation endpoint thuộc AS **nếu AS hỗ trợ**, app/RP không tự giả lập endpoint rồi nghĩ tất cả APIs đã nhận.
- Revoke refresh token thường ngăn future token issuance, nhưng **self-contained access JWT đã phát** có thể vẫn verify tới `exp` nếu RS chưa có revocation awareness.
- Access token revocation có thể có propagation delay phụ thuộc AS/RS caches.
- Có thể cần revoke **grant family**/rotating refresh token chain, không chỉ một token string.
- Không đưa raw tokens vào audit logs; dùng token fingerprints/hash nếu chính sách cho phép.
- Trong issuer compromise, introspection từ một AS bị chiếm không nên là **nguồn quyết định tin cậy duy nhất**; emergency deny tại RS vẫn cần.

**Kết luận:** RFC 7009 là cơ chế quản lý token tại AS, **không thay thế centralized emergency authorization deny** ở nhiều ứng dụng.

## 18. Opaque token introspection (RFC 7662)

Với opaque tokens, Resource Server thường gọi introspection endpoint để biết token có `active=true/false`, scope, issuer/client metadata theo AS contract.

Ví dụ token đã thu hồi:

~~~json
{
  "active": false
}
~~~

Điều cần test:
- Resource Server từ chối inactive token.
- Access token introspection cache có TTL ngắn/purge được; incident disable không bị giữ trong cache.
- Với **AS/issuer bị compromise**, một phản hồi `active=true` không được vượt qua **local issuer QUARANTINED policy**.
- Introspection client credentials được bảo vệ; endpoint TLS/AS identity đúng.
- Không coi introspection success là local tenant authorization.
- Nếu AS outage, fail-closed với operations cần mức trust đó; không fallback accept token tự do.

**Giới hạn:** introspection khả dụng không tự thu hồi Spring browser session hoặc SAML SP session.

## 19. JWT stateless cần một lớp emergency deny có trạng thái

Một JWT access token có thể được xác minh offline ở mỗi Resource Server. **Không có “xóa JWT khỏi browser” như một biện pháp server-side có hiệu lực toàn cục**. Nếu ký bằng khóa bị lộ, mọi JWT còn được các verifiers tin có thể bị giả mạo.

Cách bảo vệ:
- Denylist **issuer/registration/key version** tại Resource Servers.
- Mã hóa policy dưới dạng trust status + epoch/generation được phân phối có integrity.
- Với token được phát sau recovery, verify signer/key qua registration mới.
- Với sessions/tokens chưa có epoch claims, deny theo source/key/tenant binding hoặc risk classification.
- Với key không lộ nhưng cần revoke từng JWT, có thể dùng server-side `jti` denylist với TTL tới `exp` nếu token/JTI đáng tin và hệ thống bảo đảm fan-out.
- Với compromised signer, **`jti` và `iat` do attacker ký không phải chìa khóa allowlisted trust**; chỉ dùng chúng như secondary controls, không làm “ngoại lệ nhận token”.
- Dùng short-lived access tokens, sender-constrained tokens (mTLS/DPoP khi phù hợp), introspection nếu yêu cầu immediate revocation.
- Xác nhận mỗi RS kiểm issuer, audience, time, token purpose, tenant và emergency policy.

**Không cứu sự cố bằng cách đổi key duy nhất rồi để old key trong trust store vô thời hạn**.

## 20. Spring Security SessionRegistry: hữu ích nhưng không tự là giải pháp cluster

Spring Security hỗ trợ session management, `SessionRegistry`/`SessionInformation` và concurrent session control. Tuy nhiên:

- `SessionRegistryImpl` lưu thông tin trong memory của một JVM nếu dùng mặc định, không nên coi là view đầy đủ trên nhiều pods.
- `expireNow()` trên `SessionInformation` giúp đánh dấu session expired trong luồng Spring concurrency; **không đồng nghĩa xóa ngay HTTP session trong mọi store hoặc hủy HTTP requests đang thực thi**.
- Một session được tạo qua custom filters có thể không có trong registry nếu không tích hợp.
- Invalidation từ người dùng tại `/logout` chỉ xử lý session hiện tại, không phải mass revocation.
- `SecurityContextHolder.clearContext()` chỉ dọn context của thread hiện tại; không thu hồi sessions của mọi người dùng.
- Token Bearer trên stateless API không dùng cùng HTTP session registry.
- Việc dùng Spring Session chia sẻ store giúp định danh/deletion, nhưng cần thiết kế indexes cho source/tenant.

**Quyết định kiểm soát:** có một **quarantine guard đọc trust policy trên mọi request nhạy cảm** và một **job thu hồi sessions theo indexed inventory**; cả hai bổ sung cho nhau.

## 21. Spring Session: tìm và hủy phiên nhiều nodes

Spring Session định nghĩa `SessionRepository<S extends Session>` với `deleteById(sessionId)` và `FindByIndexNameSessionRepository<S>` có `findByPrincipalName(name)` (nếu implementation/index hỗ trợ).

**Mảnh code dự án, không phải Java standalone:**

~~~java
import java.util.Map;
import org.springframework.session.Session;
import org.springframework.session.FindByIndexNameSessionRepository;

class PrincipalSessionRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> repository;

    PrincipalSessionRevoker(
        FindByIndexNameSessionRepository<S> repository) {
        this.repository = repository;
    }

    int revokeByPrincipal(String principalName) {
        Map<String, S> sessions =
            repository.findByPrincipalName(principalName);
        sessions.keySet().forEach(repository::deleteById);
        return sessions.size();
    }
}
~~~

**Giới hạn nghiêm trọng của ví dụ:**
- Đây là **best-effort per-principal deletion**. Không tự có phương thức “xóa mọi session theo issuer” và không cung cấp atomic snapshot toàn cụm.
- Principal index mặc định có thể chỉ là username; **không đủ để phân biệt hai issuers cùng username**. Phải lưu namespace trusted source + subject qua **index riêng hoặc session inventory đáng tin**.
- Repository implementation cần hỗ trợ index chính xác; `findByPrincipalName` có thể rỗng nếu index chưa được populate.
- Delete-by-id không ngăn race: một session khác có thể được tạo cùng lúc; **quarantine/epoch guard** chặn lại.
- HTTP requests đã bắt đầu có thể còn chạy; critical operations cần policy check gần lúc commit.
- Session store có thể partitioned/cached; verify delete propagation ở toàn bộ nodes.
- Không biến tên principal lấy từ attacker token chưa verify thành batch revocation target.

**Không chạy batch xóa production tự động chỉ dựa vào một login error hoặc OIDC Logout Token chưa được verify.** Cần IC approval, scope exact và audit trail.

## 22. Session inventory riêng cho federation

Nếu cần thu hồi theo issuer/tenant/key compromise, nên có server-side index:

~~~text
federation_session_inventory(
  app_id,
  local_session_id_hash,
  storage_session_id_reference,  // encrypted/protected internal pointer
  source_protocol,              // oidc, saml, kerberos, ldap...
  trusted_registration_id,
  verified_issuer_or_entity_id,
  verified_subject_id,
  tenant_id,
  local_account_id,
  auth_method,
  trust_epoch_at_login,
  created_at,
  last_seen_at,
  expires_at,
  revoked_at,
  policy_version
)
~~~

**Không lưu session ID dạng dễ bị đọc/giả mạo trong analytics/logs.** Storage key phục vụ revoke phải có access control; external audit dùng hash/opaque correlation. Index được tạo **sau authentication thành công**, chỉ từ verified identity context; không lấy nguồn từ request `iss`/`tenant` chưa xác minh.

**Fan-out revocation:** chọn inventory theo trusted registration/issuer và tenant scope đã duyệt; delete sessions + set persistent revoked flag + bump epoch. Dùng idempotent batches, pagination, retries giới hạn, checkpoint, reconciliation và metrics.

**Compromise của một issuer chung cho nhiều tenants** đòi hỏi xem **tất cả** tenants sử dụng issuer/key đó, không chỉ tenant báo sự cố.

## 23. Trust epoch / generation guard: lớp phòng vệ chống missed sessions

Tạo version **tăng đơn điệu** cho một trust profile. Mỗi lần quarantine/restore/key-change, tăng epoch; session mới chỉ được phát sau verification dưới epoch hiện tại. Khi request đến, so session epoch với **current authoritative epoch**.

~~~text
TrustProfile:
  id = partner-oidc
  status = QUARANTINED / ACTIVE
  epoch = 12

Existing HttpSession:
  source = partner-oidc
  epoch_at_login = 11

Request:
  if status != ACTIVE -> DENY
  else if session_epoch != current_epoch -> DENY_REAUTH_REQUIRED
  else if session revoked -> DENY
  else check local account/tenant/permissions
~~~

Ưu điểm:
- Chặn sessions không nằm trong batch deletion vì index không hoàn chỉnh.
- Chặn races tạo session ngay trước quarantine nếu epoch tăng.
- Có thể áp cho cookies/session stores, authenticated API grants và delegated app sessions nếu nguồn được link đúng.

**Giới hạn:** epoch guard chỉ hữu dụng khi **mọi điểm enforcement có thể đọc policy mới kịp thời**. Caches với TTL dài hoặc fail-open làm khoảng hở. Trong incident, dùng fail-closed cho issuer đang bị nghi lộ và đo **maximum propagation delay**.

**Một session cookie không mang source registration đáng tin** sẽ khó revoke có chọn lọc; nên thiết kế inventory ngay từ trước incident.

## 24. Mảnh Spring request guard cho suspended provider

Ý tưởng project-level trong ứng dụng Spring Servlet: kiểm issuer của **Authentication đã được provider xác minh**, không từ headers/claims chưa verify; định danh source nên được lưu trong local authentication/session claims được bảo vệ.

~~~java
// PSEUDOCODE gắn trong OncePerRequestFilter đã đăng ký
// CHỈ là mẫu policy guard, không phải class compile độc lập.
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()
        && !(auth instanceof AnonymousAuthenticationToken)) {
    VerifiedFederationContext ctx =
        trustedContextResolver.resolve(auth); // app-owned; verified
    TrustPolicy policy =
        trustPolicyStore.current(ctx.registrationId());
    if (!policy.active()
            || ctx.loginEpoch() != policy.epoch()) {
        SecurityContextHolder.clearContext();
        response.sendError(401, "Reauthentication required");
        return;
    }
}
filterChain.doFilter(request, response);
~~~

**Cần làm thêm trong production:** đảm bảo `VerifiedFederationContext` không phải HTTP header, source identity được bind tới session, API Bearer tokens không bị bypass, policy store HA/atomic versioning, session store deletion, CSRF/error response và exception handling đúng. Filter riêng không bảo vệ operations đã được xử lý trước trong pipeline; kiểm vị trí Spring SecurityFilterChain. Nếu app sử dụng WebFlux, dùng reactive equivalent.

**Không tin token đã ký bằng compromised key để lấy claims rồi làm ngoại lệ trust epoch**. Khi issuer/quarantine, policy phải chặn trước mọi privileged acceptance.

## 25. OIDC Back-Channel Logout: bảo đảm và giới hạn

OpenID Connect Back-Channel Logout 1.0 cho phép OP gửi **Logout Token** đến RP qua server-to-server endpoint. Token cần được verify: signature, `iss`, `aud`, `iat/exp`, logout `events` claim, có `sub` hoặc `sid`, và **không có `nonce`**. Khi `sid` có mặt, nhắm phiên tương ứng; khi có `sub` không `sid`, phạm vi thường là các phiên của subject tại RP theo issuer/client.

**Spring Security Servlet docs** mô tả cấu hình:

~~~java
// Fragment trong Spring Security OAuth2/OIDC Client application.
// Yêu cầu oauth2Login; cấu hình logout token validation đúng release.
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

Trong Spring docs, endpoint mặc định thường là `/logout/connect/back-channel/{registrationId}`; OIDC logout handler/session registry cần wiring đúng. **Spring Session thường dùng cookie `SESSION`, trong khi handler mặc định có thể trông đợi `JSESSIONID`**, nên phải cấu hình cookie name/registry tương thích và test thật.

**Giới hạn sự cố:**
- Back-channel logout chỉ hoạt động cho RPs đã đăng ký, reachable và xử lý event.
- RP phải kiểm Logout Token trước khi invalidate sessions.
- Nếu OP signing key bị lộ, một Logout Token được ký bằng khóa đó không còn là bằng chứng độc lập đáng tin. **Emergency admin revocation phải đi qua control-plane riêng**, không chờ một Logout Token “hợp lệ”.
- Token có `sid`/`sub` từ issuer A **không được xóa sessions issuer B** chỉ vì string user trùng.
- OP logout không đảm bảo downstream access JWT và refresh tokens ở mọi API bị hủy.
- Sự cố cần mass revocation phải thực hiện **nội bộ RP và API**, kết hợp OP signals chỉ khi trust đã được đánh giá.

## 26. SAML Single Logout: có ích nhưng không phải emergency guarantee

Spring Security SAML2 hỗ trợ **RP-initiated** và **AP/IdP-initiated SLO** khi cả hai phía cấu hình. Một SLO hợp lệ có thể giúp đóng session cục bộ.

**Nhưng SLO không thể được xem là thu hồi toàn cục chắc chắn:**
- SP/IdP phải hỗ trợ và có endpoints/trust configuration đúng.
- Browser redirects, timeouts, partners offline làm partial logout.
- Session của downstream app dùng protocol khác không mặc định nằm trong SLO.
- Một LogoutRequest được ký bởi **key nghi compromised** có thể không đáng tin; không dùng nó làm authorized remote admin action.
- Key rotation/metadata cache có thể khiến LogoutRequest/Response bị reject.
- Logout SP session không làm access JWT ở API hết hạn.
- User có thể có nhiều thiết bị, browsers và local sessions; cần inventory riêng.

**Trong sự cố lộ SAML IdP key, ưu tiên quarantine và local session revocation qua app-owned control-plane**, không chờ hoàn thành SLO. Giữ SLO như cơ chế hỗ trợ khi trust còn đúng hoặc đã phục hồi.

## 27. Shared security events và continuous access evaluation

Một số hệ thống hỗ trợ **Security Event Tokens (SET)** và **Continuous Access Evaluation Profile (CAEP)** như `session-revoked`, `token-claims-change` hoặc `credential-change`. Chúng có thể giúp giảm thời gian truyền tín hiệu sự cố giữa identity provider và relying parties nếu ecosystem hỗ trợ.

**Điều kiện thiết kế:**
- Xác minh event sender/issuer, audience, event type và event signature theo contract.
- Chặn replay/duplicate (event IDs/nonce/timing theo spec).
- Ràng buộc subject identity với issuer namespace và tenant.
- Kết hợp với issuer local quarantine, không tin sender bị chiếm.
- Có retry/idempotency và audit acknowledgments.
- Đánh giá cả event-delivery outages.
- Đừng giả CAEP/SET là hỗ trợ mặc định của mọi IdP hoặc Spring application.

**Không thay thế** revocation logic và policy enforcement của backend bằng một event bus không có xác thực.

## 28. Chia nhỏ blast radius theo tenant mà không bỏ sót key chung

Trong B2B SaaS, cùng một issuer có thể được nhiều tenants tin:

~~~text
partner-issuer -> tenants North, South, West
shared-signing-key -> ID Tokens of partner-issuer
North -> partner-issuer + corp-issuer
South -> partner-issuer only
West -> partner-issuer + saml-enterprise
~~~

Nếu **private signing key chung** của partner-issuer bị lộ, cả North, South, West có thể bị ảnh hưởng, ngay cả khi incident bắt đầu từ South. Cần quarantine **theo trust/credential blast radius**, không theo một `tenantId` do request chứa.

Nếu chỉ **trust agreement** của tenant South bị chấm dứt nhưng signing key của OP không bị chiếm, có thể tắt mapping `South → partner-issuer` mà vẫn cho North/West nếu security owners xác nhận.

**Local authorization:** ngay cả khi issuer vẫn trusted cho một tenant, user phải có **active membership** và object-level permissions. Không tự map user từ issuer B sang account issuer A dựa email/sub giống nhau.

## 29. Metadata, JWKS và certificate caches trong khẩn cấp

Các thành phần có thể cache:
- OIDC Discovery document, `jwks_uri` và signing keys theo `kid`.
- Spring/Nimbus `JwtDecoder` key sets, underlying network cache.
- SAML `RelyingPartyRegistrationRepository`, IdP signing certificates.
- Gateway/service mesh auth policy.
- JWT validation libraries trong workers/mobile backends.
- Spring Session and local SecurityContext.
- OAuth access token introspection responses.
- Partner metadata endpoints/CDN/DNS.

**Cần kiểm từng điểm:** key cũ có còn trusted không? Cache TTL bao lâu? Có rollout/restart/purge được không? Policy deny được enforce trước key verification hay sau? Nếu key lộ, phải ngăn mọi đường còn có thể accept compromised signatures.

**Cẩn thận với “first key that verifies”**: không thử toàn bộ issuers rồi nhận chữ ký của bất kỳ issuer nào; bind đúng source registration, expected issuer/entityID, audience và tenant.

## 30. Thay signing key an toàn và “proof of control” độc lập

Quy trình khôi phục sau compromise:

1. IdP/OP owner xác nhận nguồn xâm nhập đã được cô lập; quay vòng signer trong vault/HSM **sạch**.
2. Security owner xác thực người có thẩm quyền qua kênh **độc lập** với metadata/DNS/email account đang nghi compromise.
3. Công bố public key/certificate mới qua trust change process đã phê duyệt.
4. Ghi fingerprint, key identifier, algorithm, owner, thời gian, impacted clients.
5. Đối chiếu issuer/entityID, service endpoints, keys, metadata và expected recipient/audience.
6. Reconfigure RPs, Resource Servers, gateways và downstream services.
7. **Không giữ compromised old key trong overlap**; nếu cần downtime để bảo đảm loại bỏ trust thì chấp nhận theo quyết định IC.
8. Test old-key forged/synthetic tokens **đều bị từ chối** trước khi phục hồi.
9. Test new-key tokens có provenance đáng tin qua login flow chuẩn và policy mới.
10. Chỉ khi verification trên **tất cả** consumers đạt yêu cầu mới chuyển trạng thái READY→ACTIVE.
11. Tăng trust epoch; tất cả phiên cũ phải reauthenticate, không tự gia hạn.
12. Giám sát changes và có quy trình rollback an toàn không đưa compromised key trở lại.

**Nếu không thể chứng minh signing key mới được tạo trong môi trường sạch, chưa đủ điều kiện restore trust.**

## 31. Local account và authorization sau khi phục hồi

Việc IdP mới đã an toàn không tự khôi phục accounts/roles:

- Kiểm **(verified issuer, subject)** với OIDC, **(verified IdP entityID, stable identifier)** với SAML.
- Nếu partner đổi issuer/entityID, đó có thể là **namespace mới**; migration/linking cần authoritative proof, không auto-link bằng email.
- Tắt JIT provisioning trong quarantine, review các accounts tạo ra trong incident window.
- Review group→GrantedAuthority mappings, privileged grants, tenant memberships, SCIM changes và admin role assignments.
- Kiểm các resource object đã bị sửa bởi sessions/tokens đáng ngờ.
- Revoke OAuth consent/grants có thể đã bị abuse.
- Bắt buộc step-up/MFA/re-enrollment theo severity và tenant policy.
- Không cấp `ROLE_ADMIN` chỉ vì claim đã được signer mới xác minh.
- Kiểm local user disable và offboarding.
- Rebuild subject-to-local-account map nếu phát hiện identity collision.

**Mục đích của recovery không chỉ là login lại được**, mà là **trạng thái quyền vẫn đúng** sau compromise.

## 32. Java 17 runnable: quarantine, mass revocation và trust epoch

Ví dụ dưới đây **chạy bằng JDK 17 thuần**, mô phỏng control-plane policy và sessions của hai nguồn federation. Nó không đọc JWT, không xác minh SAML signature, không gọi Redis, không xóa session trong Spring thực. Dữ liệu `provider`/`tenant` là **trusted context sau verification**, không phải values lấy từ untrusted HTTP request.

Bài toán mô phỏng:
- Có `partner-oidc` phục vụ South và `corp-saml` phục vụ North.
- Quarantine partner chặn ngay yêu cầu; Corp không bị ảnh hưởng.
- Batch revoke các partner sessions đã biết.
- Khôi phục partner với epoch tăng, **session cũ bị stale dù index bỏ sót**.
- Session mới sau reauthentication được nhận nếu tenant đúng.
- Unknown provider hoặc no session bị từ chối.

Tạo file **FederationIncidentGateDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class FederationIncidentGateDemo {

    enum TrustState { ACTIVE, QUARANTINED }

    record Policy(TrustState state, long epoch) {}

    record LoginSession(
            String id, String provider, String tenant,
            long loginEpoch, boolean revoked) {}

    private final Map<String, Policy> policies = new HashMap<>();
    private final Map<String, LoginSession> sessions = new HashMap<>();

    FederationIncidentGateDemo() {
        policies.put("partner-oidc", new Policy(TrustState.ACTIVE, 4));
        policies.put("corp-saml", new Policy(TrustState.ACTIVE, 9));
        sessions.put("partner-old", new LoginSession(
                "partner-old", "partner-oidc", "south", 4, false));
        sessions.put("corp-old", new LoginSession(
                "corp-old", "corp-saml", "north", 9, false));
    }

    String check(String sessionId, String requestedTenant) {
        LoginSession session = sessions.get(sessionId);
        if (session == null) {
            return "DENY_NO_SESSION";
        }
        Policy policy = policies.get(session.provider());
        if (policy == null) {
            return "DENY_UNKNOWN_PROVIDER";
        }
        if (policy.state() != TrustState.ACTIVE) {
            return "DENY_PROVIDER_QUARANTINED";
        }
        if (session.revoked()) {
            return "DENY_SESSION_REVOKED";
        }
        if (session.loginEpoch() != policy.epoch()) {
            return "DENY_STALE_TRUST_EPOCH";
        }
        if (!session.tenant().equals(requestedTenant)) {
            return "DENY_TENANT";
        }
        return "ALLOW " + session.id();
    }

    void quarantine(String provider) {
        Policy current = policies.get(provider);
        if (current == null) {
            throw new IllegalArgumentException("Unknown provider");
        }
        policies.put(provider, new Policy(
                TrustState.QUARANTINED, current.epoch() + 1));
    }

    int revokeKnownSessions(String provider) {
        int revoked = 0;
        for (Map.Entry<String, LoginSession> entry : sessions.entrySet()) {
            LoginSession s = entry.getValue();
            if (s.provider().equals(provider) && !s.revoked()) {
                entry.setValue(new LoginSession(
                        s.id(), s.provider(), s.tenant(),
                        s.loginEpoch(), true));
                revoked++;
            }
        }
        return revoked;
    }

    void restoreAfterIndependentAttestation(String provider) {
        Policy current = policies.get(provider);
        if (current == null || current.state() != TrustState.QUARANTINED) {
            throw new IllegalStateException("Not quarantined");
        }
        // Trong production, security approvals + rotated keys
        // phải được xác minh TRƯỚC khi gọi hàm này.
        policies.put(provider, new Policy(
                TrustState.ACTIVE, current.epoch()));
    }

    void addSessionFromVerifiedReauthentication(
            String id, String provider, String tenant) {
        Policy policy = policies.get(provider);
        if (policy == null || policy.state() != TrustState.ACTIVE) {
            throw new IllegalStateException("Provider not active");
        }
        sessions.put(id, new LoginSession(
                id, provider, tenant, policy.epoch(), false));
    }

    public static void main(String[] args) {
        FederationIncidentGateDemo gate = new FederationIncidentGateDemo();

        System.out.println("Partner before: "
                + gate.check("partner-old", "south"));
        System.out.println("Corp before: "
                + gate.check("corp-old", "north"));

        gate.quarantine("partner-oidc");
        System.out.println("Partner quarantined: "
                + gate.check("partner-old", "south"));
        System.out.println("Corp unaffected: "
                + gate.check("corp-old", "north"));

        System.out.println("Revoked known partner sessions: "
                + gate.revokeKnownSessions("partner-oidc"));

        // Mô phỏng một phiên cũ nằm ngoài inventory đã revoke.
        gate.sessions.put("missed-edge", new LoginSession(
                "missed-edge", "partner-oidc", "south", 4, false));
        gate.restoreAfterIndependentAttestation("partner-oidc");

        System.out.println("Known old partner: "
                + gate.check("partner-old", "south"));
        System.out.println("Missed stale session: "
                + gate.check("missed-edge", "south"));

        gate.addSessionFromVerifiedReauthentication(
                "partner-new", "partner-oidc", "south");
        System.out.println("New verified partner: "
                + gate.check("partner-new", "south"));
        System.out.println("Wrong tenant: "
                + gate.check("partner-new", "north"));
        System.out.println("No session: "
                + gate.check("unknown", "south"));

        gate.sessions.put("unknown-provider", new LoginSession(
                "unknown-provider", "rogue-oidc", "south", 1, false));
        System.out.println("Unknown provider: "
                + gate.check("unknown-provider", "south"));
    }
}
~~~

Chạy:

~~~bash
javac FederationIncidentGateDemo.java
java FederationIncidentGateDemo
~~~

**Stdout chính xác:**

~~~text
Partner before: ALLOW partner-old
Corp before: ALLOW corp-old
Partner quarantined: DENY_PROVIDER_QUARANTINED
Corp unaffected: ALLOW corp-old
Revoked known partner sessions: 1
Known old partner: DENY_SESSION_REVOKED
Missed stale session: DENY_STALE_TRUST_EPOCH
New verified partner: ALLOW partner-new
Wrong tenant: DENY_TENANT
No session: DENY_NO_SESSION
Unknown provider: DENY_UNKNOWN_PROVIDER
~~~

**Giới hạn rất quan trọng:** demo dùng HashMap của một JVM, không có cryptography, không chứa trusted distributed policy store, không xóa Redis/DB sessions hoặc JWTs thật; không cho phép handler user gọi `quarantine`/`restore` như endpoint công khai. Đây là bài về **authorization safety invariants sau khi có evidence đáng tin**; thực tế phải enforce trust epoch ở mọi request cùng với Spring authentication, MFA/privileged authorization và audit.

## 33. Tại sao demo có cả session deletion lẫn epoch guard?

Giả sử batch inventory revocation bỏ sót một session vì:
- User logout/relogin đúng thời điểm job đang quét.
- Index chưa populate cho custom SAML/OIDC filter.
- Redis replica lag hoặc node offlined.
- Session ID bị thay/rotate.
- Worker/API Gateway có cache riêng.
- Một phiên không còn mapped vào principal index nhưng vẫn có SecurityContext.

**Session deletion** giải phóng credential và giảm lưu lượng request. **Epoch guard** buộc bất kỳ session đến từ policy epoch cũ đều phải reauthenticate. **Quarantine** giúp chặn ngay cả trước khi revocation batch hoàn thành.

Trong môi trường phân tán phải kiểm **atomic epoch update + propagation**, out-of-order events và khả năng fail closed khi policy store unavailable. Không cho old node “đọc lại epoch cũ” rồi accept token đến từ key lộ.

## 34. Race conditions và kiểm soát nhất quán

| Race | Nguy cơ | Bảo vệ |
| --- | --- | --- |
| User login đúng lúc issuer bị quarantine | Session mới với trust cũ | Epoch CAS / active check trước persist |
| Batch xóa session vừa user login lại | Xóa nhầm session mới | Target bằng source+epoch+time, idempotency |
| JWT validator key cache chưa refresh | Tiếp tục nhận signer lộ | Emergency deny policy trước privileged access |
| Logout Token đến muộn sau restore | Xóa session mới sai scope | Validate issuer/client/sid/sub + event semantics |
| Quarantine event và restore event đến đảo thứ tự | Old ACTIVE đè QUARANTINED | Version monotonic, compare-and-set, signed control-plane |
| Một API request đã qua check, commit sau quarantine | Side effect vẫn xảy ra | Re-check near transaction/critical operation, idempotency |
| Regional policy cache stale | Một region accept trong khi region khác deny | Propagation SLO/health, deny-on-staleness |
| IdP key rotate mà SP còn old cert | Forged assertion vẫn được accept | Explicit key removal + verification |
| Concurrent admin actions | Mở lại trước khi incident closure | Approval workflow/state machine |
| Session inventory thiếu custom principals | Incomplete revocation | Independent epoch guard + reconciliation |

**Không thể hoàn tác mọi operation đã hoàn tất trước khi policy thay đổi**. Incident response còn cần fraud review, containment của dữ liệu đã bị xuất và công cụ rollback business transactions theo policy.

## 35. Forensics: giữ bằng chứng trước/sau containment

**Không trì hoãn chặn nguy hiểm chỉ để thu thập thêm logs**, nhưng cần lưu có kiểm soát:
- Timeline incident events, first seen, notifications, key version/serial/thumbprints.
- Versioned issuer/IdP metadata, JWKS fingerprints, RelyingPartyRegistration/ClientRegistration configs.
- Security config changes, deploys, signer rotations, feature flag changes.
- Authentication decisions theo issuer/client/tenant, failure codes, IP/device/session fingerprints đã pseudonymized.
- JWT `kid/iss/aud/jti` metadata được ghi ở dạng redacted/hashed phù hợp; raw signed tokens chỉ được giữ trong forensic vault nếu pháp lý/security owner cho phép.
- SAML Response/Assertion IDs, issuer/audience/Recipient, signing cert fingerprint; bảo vệ NameID/PII.
- Spring Session inventory snapshot, revoked count, failure/retry counts.
- Refresh token grant records và OAuth client activity.
- HSM/KMS audit operations và secret access logs.
- SCIM provisioning, account linking, role changes, privileged operations.
- Network/CDN/proxy logs phục vụ truy dấu.
- Timestamp UTC với clock synchronization.
- Evidence owner, integrity hash, retention và chain of custody.

**Không chia sẻ** private keys, SAML Assertions, access/refresh tokens, session cookies hoặc HAR chứa credentials trong chat/công cụ ticket thông thường.

## 36. Theo dõi hiệu lực containment

Metrics do tổ chức tự triển khai, không phải Spring Security mặc định phát tất cả:

| Metric | Mục đích |
| --- | --- |
| `federation_trust_quarantined_profiles` | Profiles đang bị khóa |
| `federation_trust_epoch_version` | Epoch/version trên từng region |
| `federation_login_blocked_total` | New login từ source bị quarantine |
| `federation_api_token_rejected_total` | JWT/opaque tokens bị từ chối do incident |
| `federation_sessions_revoked_total` | Batch sessions xóa/đánh dấu revoke |
| `federation_session_epoch_denied_total` | Sessions lọt index nhưng bị epoch chặn |
| `federation_logout_event_invalid_total` | Back-channel/SLO/SET không hợp lệ |
| `federation_jwks_stale_instances` | Verifiers còn old compromised keys |
| `federation_partner_restore_approvals` | Hồ sơ phê duyệt mở lại |
| `federation_token_introspection_failures` | Phụ thuộc AS/introspection |
| `federation_cross_tenant_denials_total` | Nguy cơ lateral movement |
| `federation_reauthentication_success_total` | Sessions mới sau restore |
| `federation_revocation_propagation_seconds` | Thời gian lan truyền deny toàn cụm |

**Không đưa raw subject, email, user identifiers hoặc token/JWK values vào metric labels**; dùng allowlisted registration IDs, environment, region và reason enum. Logs phải có correlation ID và audit access controls.

**Cần đo:** ngay sau quarantine, bao nhiêu requests vẫn thành công từ affected source? Khi câu trả lời khác 0 ngoài approved exceptions, containment chưa đủ.

## 37. Giao tiếp với đối tác và khách hàng

Một thông báo cần cân bằng tính chính xác với bảo mật:

1. Nêu loại sự cố đã xác nhận/đang nghi vấn, thời điểm UTC và phạm vi dự kiến.
2. Nêu các dịch vụ login/access bị tạm khóa và lý do security.
3. Không nêu private signing key, raw JWT, logout token hoặc tài khoản nghi bị lợi dụng.
4. Cung cấp đường hỗ trợ xác thực độc lập, không chỉ email từ IdP đang bị compromise.
5. Phân biệt **restored login availability** với **confirmed compromise eradication**.
6. Thông báo yêu cầu reauthentication, password reset/MFA enrollment nếu policy áp.
7. Cập nhật thời điểm và nội dung theo thực tế, không hứa thời gian chắc chắn.
8. Phối hợp legal/privacy về báo cáo bắt buộc theo hợp đồng/pháp luật thực tế.
9. Ghi rõ phía nào chịu trách nhiệm revoke downstream tokens/sessions.
10. Có kịch bản cho khách hàng bị gián đoạn critical workflows, bảo vệ break-glass.

**Không chia sẻ danh sách users bị ảnh hưởng rộng hơn nhu cầu xử lý**. Incident updates phục vụ vận hành phải có mức phân quyền phù hợp.

## 38. Điều kiện mở lại đối tác / issuer

Đừng mở trust chỉ vì một trang login đã chạy. Checklist có bằng chứng:

- [ ] Source compromise đã được cô lập và root cause ít nhất đủ để kiểm soát tái phát.
- [ ] Security/partner ownership được xác minh ngoài băng.
- [ ] Key/signing certificate mới được tạo, lưu trong HSM/KMS/secret store đáng tin.
- [ ] Issuer/entityID, endpoints, audience/client IDs, cert fingerprints đã được independently verified.
- [ ] Old compromised key/cert bị từ chối tại mọi RPs/Resource Servers/gateways.
- [ ] Trust policy epoch tăng và được phân phối đến mọi regions/nodes.
- [ ] Old sessions từ affected source bị deny, kể cả session index bỏ sót.
- [ ] Refresh grants và API access token policy đã được xử lý theo blast radius.
- [ ] SAML/OIDC login mới pass full protocol verification + anti-replay.
- [ ] Local account, group mapping, SCIM JIT/provisioning, tenant membership được rà soát.
- [ ] Downstream partners/RPs xác nhận đã cập nhật trust.
- [ ] Canary traffic cho affected tenant và các unaffected tenants pass.
- [ ] Fail-closed khi policy store/JWKS/introspection outages.
- [ ] Break-glass, audit logs, metrics và alert hoạt động.
- [ ] Incident Commander và security owner ký duyệt restore.
- [ ] Có phương án re-quarantine ngay nếu xuất hiện signal xấu.

**Bằng chứng restore phải là một tập test và approvals**, không phải “JWT signature verify được bằng key mới” đơn lẻ.

## 39. Ma trận kiểm thử sự cố — trust và key compromise

| # | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| 01 | OIDC issuer Partner ACTIVE, ID Token đúng | Login qua policy bình thường |
| 02 | Quarantine Partner, vẫn gửi ID Token ký đúng | Login bị chặn |
| 03 | Quarantine Partner, vẫn gửi OAuth callback code | Không tạo session |
| 04 | Quarantine Partner, SAML Response ký đúng bằng key cũ | Không accept |
| 05 | Forged token ký bằng compromised key, cùng `iss` | Reject tại verifier |
| 06 | Forged token có `iat` trước incident | Không dùng iat để bypass |
| 07 | JWKS cache còn compromised old key | Emergency deny vẫn chặn |
| 08 | Client metadata URI đổi trái phép | Không auto-trust |
| 09 | New signer do partner tự gửi qua kênh compromised | Pending approval, không active |
| 10 | New signer được independently verified | Có thể restore sau full QA |
| 11 | Old compromised signing key được thêm lại overlap | QA fail |
| 12 | SAML Assertion sai Audience/Recipient dù key mới | Reject |
| 13 | SAML IdP entityID không khớp expected | Reject |
| 14 | SAML Response replay sau restore | Reject |
| 15 | JWT mới aud sai Resource Server | Reject |
| 16 | JWT `kid` chọn key không thuộc issuer | Reject |
| 17 | Resource Server dùng `jku` từ unverified JWT | Security QA fail |
| 18 | Client secret cũ sau rotate | AS từ chối |
| 19 | Refresh token cũ sau grant revoke | Không xin access token mới |
| 20 | Keytab service cũ sau rotation | Không dùng làm acceptor hợp lệ |

## 40. Ma trận kiểm thử — session, token và logout

| # | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| 21 | Spring session Partner đang active trước quarantine | Request kế tiếp bị deny |
| 22 | Session Corp không cùng blast radius | Vẫn hoạt động đúng policy |
| 23 | Batch revocation bỏ sót session Partner | Epoch guard vẫn deny |
| 24 | User tạo session đúng thời điểm quarantine | Không persist thành phiên trusted |
| 25 | App session đã logout nhưng JWT access token còn hạn | API deny theo incident policy |
| 26 | Revoke refresh token nhưng cached JWT còn hạn | JWT vẫn phải bị RS emergency deny |
| 27 | OAuth opaque token introspection `active=false` | Deny |
| 28 | Issuer compromised trả introspection `active=true` | Local quarantine override, deny |
| 29 | OIDC Back-Channel Logout Token hợp lệ trong trusted state | Logout đúng issuer/client/sid |
| 30 | OIDC Logout Token sai issuer/signature/audience | Reject, không xóa sessions khác |
| 31 | OIDC Logout Token bị ký bởi compromised key khi quarantine | Không dùng như nguồn admin trust |
| 32 | SAML IdP-initiated SLO khi issuer trusted | Áp policy và protocol checks |
| 33 | SAML SLO không tới SP offline | Local emergency deny vẫn có hiệu lực |
| 34 | SessionRegistry chỉ giữ one-pod sessions | Distributed test phát hiện thiếu |
| 35 | Spring Session principal index trùng username ở hai IdPs | Không cross-issuer revoke |
| 36 | Two revocation jobs chạy đồng thời | Idempotent, không revive session |
| 37 | Revocation event đến đảo thứ tự | Higher monotonic version thắng |
| 38 | Trust store unavailable trong incident | Fail closed theo risk policy |
| 39 | JWT AS outage và token có chữ ký compromised | Không fallback accept |
| 40 | Browser session revoked nhưng HTTP request đã chạy | Critical operation recheck gần commit |
| 41 | Same user có sessions nhiều thiết bị | Thu hồi theo scope được duyệt |
| 42 | Tenant North bị revoke, South unaffected source | Không xóa vô cớ nếu chỉ tenant-scope |
| 43 | Shared signing key của issuer dùng nhiều tenants | Chặn mọi tenant thuộc key blast radius |
| 44 | Reauthentication sau restore với epoch mới | New session pass theo policy |
| 45 | Old partner session sau restore | Deny, không tái sử dụng |
| 46 | Local account disabled sau IdP compromise | Deny kể cả new token |
| 47 | Forged group admin trong otherwise valid token | Local role mapping/tenant policy deny |
| 48 | Multi-region cache stale issuer ACTIVE | Test phát hiện breach propagation SLA |
| 49 | Kerberos service account rotated nhưng old keytab còn pod | Node fail, quarantine/rotation kiểm soát |
| 50 | Security evidence endpoint bị lộ raw tokens | QA fail và incident logging fix |

## 41. Runbook theo giai đoạn vận hành

### A. Kích hoạt ngay sau phát hiện

1. Mở incident, xác định IC, mức ưu tiên, UTC timeline và kênh liên lạc độc lập.
2. Xác minh initial signals, lấy trust profile/credential fingerprints có kiểm soát.
3. Lập list affected clients, SPs, RPs, Resource Servers, tenants và session stores.
4. Áp **QUARANTINED** ở tất cả enforcement points; kiểm new logins và tokens bị reject.
5. Bảo vệ emergency admin access khỏi cùng issuer bị lộ.
6. Bảo toàn evidence và stop privileged operations nếu risk yêu cầu.

### B. Containment + revocation

1. Tăng trust epoch và phân phối policy có integrity.
2. Disable new federation exchanges/JIT provisioning.
3. Scan/index và delete/revoke Spring sessions theo trusted source/tenant scope.
4. Revoke refresh grants/client credentials ở AS; liên hệ AS owner.
5. Áp emergency deny cho JWT/opaque tokens ở mọi RS.
6. Notify/downstream partners cập nhật trust; không giả logout tự propagate.
7. Chặn delegated services, rotate service keys theo blast radius.
8. Ghi counts, missed sessions và propagation time.

### C. Eradication và recovery

1. Xác nhận root cause đủ để ngăn key lại bị lấy.
2. Rotate signing/enc keys trong environment sạch, bảo đảm independent attestation.
3. Cập nhật trusted metadata/JWKS/certs, client registrations, SPNs/keytabs liên quan.
4. Remove old compromised trust mọi nơi, purge stale caches.
5. Review accounts, group mappings, privileged grants, SCIM events.
6. Chạy full negative test + canary.
7. Mở issuer theo staged approval; ép reauthentication phiên cũ.
8. Monitor 401/403/login anomalies và unknown-key attempts.

### D. Hậu sự cố

1. Đối chiếu incident timeline và forensic evidence.
2. Xác nhận không có successful access từ compromised source sau quarantine threshold.
3. Đóng gaps trong inventory/index và central policy propagation.
4. Cải thiện token lifetime/revocation support và key isolation.
5. Diễn tập lại multi-region/token/session cases.
6. Cập nhật customer/partner notice và legal obligations.
7. Lưu decisions/approvals, postmortem, follow-up owners và deadlines.

## 42. Tabletop exercises: những câu hỏi phải trả lời được

**Tình huống 1 — Lộ SAML IdP key trong partner, 12 RPs đang trust.**  
Ai có thể disable trust từ trung tâm? Các RPs tự quản có cách nhận emergency notice không? Tất cả keys cũ bị xóa trước khi restore? Một SP đang offline liệu vẫn nhận assertion lộ key khi online lại không?

**Tình huống 2 — OIDC signer bị lộ, 6 APIs dùng JWT offline.**  
Có allowlist issuer per API và kill switch tách từ JWKS không? JWT có lifetime bao lâu? API nào còn key cache cũ? Làm sao chứng minh không access sau quarantine?

**Tình huống 3 — Partner phục vụ ba tenants; chỉ một tenant báo compromise.**  
Key chung hay trust relationship riêng? Chặn theo key blast radius hay tenant mapping? Ai approve giữ tenants còn lại? User có cùng email ở hai issuers có bị link sai?

**Tình huống 4 — Redis Spring Session outage giữa batch mass logout.**  
Policy store khác Redis có fail closed không? Nếu các app chỉ xóa sessions khi Redis trở lại, các API stateless còn accept JWT không? Có reconciliation và retry không?

**Tình huống 5 — Logout Token của OP ký bằng compromised signer.**  
App có nên nhận event này để xóa sessions tất cả users? Không; một event từ compromised signer không là independent admin proof. Hệ thống phải có control-plane revoke riêng.

**Tình huống 6 — Partner đã rotate cert và xin restore gấp.**  
Có independent ownership attestation không? Old signer đã reject tại mọi RPs chưa? Sessions cũ bị deny bằng epoch? Role mapping/tenant isolation tests đã pass chưa?

**Tình huống 7 — OAuth client secret lộ nhưng signer key vẫn an toàn.**  
Có thể giới hạn scope vào client credentials/grants mà không block toàn issuer nếu evidence hỗ trợ. Tuy nhiên phải bảo đảm client secret không dùng chung nhiều integrations.

**Tình huống 8 — Operator cần break-glass khi tất cả partner logins bị tắt.**  
Break-glass phải dùng independent factor/source và audit tăng cường, không “bật tạm accept any issuer”.

## 43. Những anti-pattern tuyệt đối tránh

1. **“Đổi JWKS là hết sự cố”:** JWT và caches vẫn có thể tin key cũ.
2. **“Xóa session ở web portal là thu hồi API tokens”:** khác credential namespaces.
3. **“Một OIDC/SAML logout sẽ logout mọi đối tác”:** protocol/participant support không đầy đủ.
4. **“Claim iat cho biết token được phát trước lúc lộ key”:** signer attacker có thể giả iat.
5. **“Issuer hợp lệ nên token chắc an toàn”:** issuer private key đã lộ.
6. **“Dùng mọi JWK tìm key verify được”:** phải đúng issuer/key binding.
7. **“Phát signal logout từ IdP compromised là admin proof”:** cần control-plane độc lập.
8. **“SessionRegistryImpl có đủ mọi pod”:** mặc định local memory.
9. **“Xóa theo principal name email đủ chính xác”:** identity collision xuyên issuers.
10. **“Tạm bỏ chữ ký SAML/ID Token khi partner bị lỗi”:** biến outage thành authentication bypass.
11. **“Giữ compromised cert thêm một tháng để overlap”:** tiếp tục cho forge.
12. **“Tắt signing key cũng thu hồi SP decryption compromise”:** confidentiality scope khác.
13. **“Tự đăng ký new issuer từ token claims”:** attacker-controlled trust enrollment.
14. **“Chiến dịch xóa sessions không có epoch guard”:** có race/missed index.
15. **“Mọi access là an toàn ngay khi dashboard hiển thị 0 active sessions”:** các requests đang chạy/RS caches có thể chưa chặn.
16. **“Mở lại ngay khi test login thành công”:** thiếu identity mapping, tenant, revocation, canary, approvals.

## 44. Checklist sẵn sàng trước khi sự cố xảy ra

- [ ] Trusted issuer/IdP registry có owner, environment, source protocol và tenant mapping.
- [ ] Inventory tất cả signing/enc/client/TLS/keytab secrets và nơi dùng.
- [ ] Rotation owners, KMS/HSM access và out-of-band partner contacts đã kiểm.
- [ ] Có quarantine switch độc lập từ remote issuer metadata/JWKS.
- [ ] Resource Servers có policy deny cho compromised issuer/key dù JWT signature đúng.
- [ ] Opaque token introspection cache TTL và fail-closed behavior đã được test.
- [ ] Refresh token/grant revocation APIs có owner và playbook.
- [ ] Spring Session store/index đủ truy vết local sessions theo verified source.
- [ ] Có monotonic trust epoch/revocation version, enforced trên critical requests.
- [ ] Có khả năng delete sessions theo scope chính xác và reconcile đa node.
- [ ] OIDC back-channel logout được kiểm signature/issuer/audience/sid/sub/replay khi dùng.
- [ ] SAML SLO được coi là best-effort và có local revocation fallback.
- [ ] Không tự trust dynamic issuer/certificate từ unverified input.
- [ ] JWT access tokens ngắn hạn hoặc có emergency deny phù hợp latency SLA.
- [ ] Session/identity link theo issuer+subject hoặc verified SAML namespace.
- [ ] Roles/tenant/object authorization không suy ra từ provider login đơn thuần.
- [ ] IdP-initiated SAML và JIT provisioning có kill switch tách biệt.
- [ ] Secret leak/metadata tamper/signing key compromise đều có test cases.
- [ ] Có break-glass identity provider độc lập, phê duyệt và audit.
- [ ] Policy propagation monitoring bao phủ mọi regions/nodes/partners.
- [ ] Có forensic evidence retention và redaction/custody policy.
- [ ] Có customer/partner communication và legal escalation path.
- [ ] Có điều kiện re-enable bằng security approvals + signed canary results.
- [ ] Đã diễn tập ít nhất tình huống JWT signer lộ và SAML IdP signing key lộ.

## 45. Kết luận và công thức nhớ

Ứng phó sự cố federation là **bài toán thu hồi *niềm tin* trước khi thu hồi từng loại *credential***. Một lộ signing key có thể khiến token/assertion giả mạo vẫn được verifier chấp nhận; một HTTP session có thể tồn tại ngay cả khi IdP đã disable; một JWT đã phát không nhất thiết biến mất khi refresh token bị revoke. Để containment đáng tin, cần:

**Verified incident → scoped trust quarantine → per-request emergency deny + trust epoch → revoke sessions/grants/tokens → independent key replacement → verify every consumer → forced reauthentication → tenant authorization → staged restore.**

Trong Spring Security, kết hợp **client/RP registration trust controls**, **JWT Resource Server issuer/key/audience policy**, **Spring Session indexed invalidation**, **OIDC Back-Channel Logout/SAML SLO khi phù hợp** và **application-owned domain authorization**. **Không có một API logout duy nhất bảo đảm chặn toàn bộ OAuth, SAML, Kerberos và các local sessions**. Kiểm bằng negative tests và telemetry của từng consumer, không chỉ dashboard IdP.

### Tài liệu chính thức để triển khai và rà soát

- NIST SP 800-61 Rev. 3 (April 2025) — Incident Response Recommendations and Considerations for Cybersecurity Risk Management: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- NIST SP 800-57 Part 1 — Key Management Recommendations: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- Spring Security — Session Management and concurrent sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Session — API, SessionRepository and FindByIndexNameSessionRepository: https://docs.spring.io/spring-session/reference/api.html
- Spring Security — OIDC Logout, RP-initiated and Back-Channel Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — SAML2 Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security — OAuth2 Resource Server JWT validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8417 — Security Event Token: https://www.rfc-editor.org/rfc/rfc8417
- OpenID Continuous Access Evaluation Profile 1.0: https://openid.net/specs/openid-caep-1_0.html
- OpenID Connect Core — ID Token validation/issuer/audience: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS SAML 2.0 Core/Profiles/Metadata: https://www.oasis-open.org/standard/saml/
- RFC 4120 — Kerberos V5: https://www.rfc-editor.org/rfc/rfc4120
