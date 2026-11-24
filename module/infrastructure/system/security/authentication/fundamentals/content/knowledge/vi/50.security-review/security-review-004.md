# Configuration review — Rà soát cấu hình bảo mật cho hệ thống xác thực

Một nhóm triển khai identity provider mới và bật đăng nhập bằng OIDC cho ứng dụng nội bộ. Cấu hình ban đầu dùng redirect URI wildcard, refresh token có thời hạn dài, cookie thiếu SameSite, MFA chỉ bắt buộc cho một nhóm admin nhỏ và service account có quyền đọc toàn bộ secret trong production. Các thiết lập này được sao chép qua nhiều môi trường. Sau một lần thay đổi, một ứng dụng staging bắt đầu nhận token production và một endpoint cũ vẫn chấp nhận session đã logout.

**Configuration review** là quá trình kiểm tra có hệ thống các thiết lập của thành phần xác thực và các thành phần phụ thuộc để xác định cấu hình sai, quyền quá rộng, trust boundary không rõ, cơ chế bảo vệ bị tắt hoặc hành vi không phù hợp với threat model. Review cần xem cấu hình thực tế đang chạy, nguồn cấu hình, cách triển khai, ngoại lệ, quyền thay đổi và bằng chứng kiểm thử.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học rà soát cấu hình của identity provider, password, MFA, passkey, OAuth/OIDC, token, session, cookie, API authentication, certificate, workload identity, secret manager và audit. Người học biết xây dựng baseline, phân loại rủi ro, kiểm tra drift giữa môi trường, đánh giá thay đổi, tự động hóa kiểm thử và lập kế hoạch khắc phục. Mục tiêu là bảo đảm cấu hình đang chạy thực thi đúng chính sách xác thực, giảm cơ hội phishing, replay, session theft, privilege abuse và account takeover.

## 1. Configuration review giải quyết vấn đề gì?

Một hệ thống có thể sử dụng thuật toán mạnh nhưng vẫn dễ bị tấn công do cấu hình sai. Ví dụ:

- OIDC client chấp nhận redirect URI wildcard hoặc open redirect.
- Native app nhúng client secret vào binary và không dùng PKCE.
- Refresh token sống quá lâu, không rotation hoặc không có reuse detection.
- Cookie session thiếu Secure, HttpOnly hoặc SameSite phù hợp.
- MFA không được yêu cầu cho thao tác nhạy cảm hoặc recovery flow yếu hơn login.
- Passkey registration không yêu cầu user verification theo policy.
- API chấp nhận token có audience hoặc issuer không đúng.
- Certificate validation bỏ qua hostname, expiry hoặc chain validation.
- Workload identity có thể xin token production từ môi trường staging.
- Secret manager policy cấp quyền đọc toàn bộ namespace.
- Audit log ghi raw token hoặc không có retention/integrity.

Configuration review tìm các sai lệch giữa **ý định bảo mật**, **cấu hình được phê duyệt** và **cấu hình thực tế**. Nó không chỉ là kiểm tra file YAML hay màn hình admin; cần xem cả runtime behavior, default của framework, quyền cloud/platform, reverse proxy và downstream resource server.

### 1.1. Các câu hỏi review

1. Thành phần nào đang xác thực user, client hoặc workload?
2. Principal được xác minh bằng yếu tố nào và trust anchor nào?
3. Redirect, issuer, audience, origin, RP ID và certificate identity có bị giới hạn chính xác không?
4. Token/session có lifetime, rotation, revocation và binding phù hợp không?
5. Quyền đọc secret, quản lý key và thay đổi policy có theo least privilege không?
6. Dev, staging và production có tách biệt identity, key, endpoint và data không?
7. Thay đổi cấu hình được ai phê duyệt, triển khai và kiểm tra?
8. Có bằng chứng runtime chứng minh cấu hình hoạt động như mong muốn không?
9. Ngoại lệ có owner, scope, expiry và kế hoạch loại bỏ không?
10. Nếu cấu hình sai, blast radius và rollback path là gì?

## 2. Phạm vi và ranh giới của review

Review cần bắt đầu từ luồng xác thực end-to-end thay vì kiểm tra từng sản phẩm riêng lẻ.

~~~mermaid
flowchart LR
    U[User / workload] --> C[Client app]
    C --> I[Identity provider]
    I --> T[Token endpoint]
    T --> G[API gateway]
    G --> R[Resource server]
    C --> S[Session / cookie]
    R --> K[KMS / secret manager]
    I --> A[Audit / monitoring]
    T --> A
    G --> A
    R --> A
~~~

### 2.1. Thành phần cần xem xét

| Thành phần | Cấu hình trọng yếu |
| --- | --- |
| Identity provider | Password policy, MFA, passkey, recovery, session, federation |
| OAuth/OIDC client | Client type, redirect URI, PKCE, grant, scope, token policy |
| Authorization server | Issuer, signing key, audience, token lifetime, refresh rotation |
| Browser/web app | Cookie, CSRF, CORS, origin, CSP, referrer và cache policy |
| Mobile app | External user-agent, callback URI, App Links/Universal Links, secure storage |
| API gateway/resource server | Issuer/audience validation, scope, authorization, rate limit |
| PKI/mTLS | Trust store, SAN, EKU, expiry, revocation, key protection |
| Workload identity | Issuer, subject, audience, attestation, service account scope |
| Secret manager/KMS | Authentication, policy, key boundary, rotation, audit |
| Logging/SIEM | Event coverage, redaction, retention, integrity và alert |
| Platform/network | TLS, proxy headers, DNS, egress, service mesh và environment isolation |
| CI/CD/IaC | State source, approval, secret injection, drift và deployment identity |

### 2.2. Những gì configuration review không thay thế

- Penetration test kiểm tra khả năng khai thác thực tế trong phạm vi được phép.
- Code review kiểm tra logic và implementation.
- Threat modeling xác định tài sản, attacker capability và trust boundary.
- Compliance audit đánh giá yêu cầu theo chuẩn/pháp lý cụ thể.
- Operational readiness review đánh giá khả năng vận hành, backup và incident response.

Configuration review có thể phát hiện vấn đề cần các hoạt động trên xác minh. Không kết luận “an toàn” chỉ vì các checkbox cấu hình đều bật.

## 3. Chuẩn bị: inventory, owner và nguồn cấu hình chuẩn

Trước khi kiểm tra, lập inventory để biết mình đang review cái gì.

### 3.1. Configuration inventory

Mỗi thành phần nên có:

- Tên service, owner và technical contact.
- Environment, tenant, region và deployment ID.
- Component/version, framework và identity provider.
- Principal/client/workload liên quan.
- Endpoint, issuer, audience, redirect URI và trust domain.
- Config source: IaC, Git, config service, admin console hoặc runtime secret.
- Policy version, last change và approver.
- Data classification và privilege level.
- Dependency tới KMS, secret manager, PKI, gateway và logging.

### 3.2. Source of truth

Chọn nguồn cấu hình được phê duyệt cho từng loại thiết lập:

- Infrastructure as Code cho network, cloud resource và service policy.
- Version-controlled configuration cho app và gateway.
- Identity provider configuration export/API với quyền truy cập hạn chế.
- Policy-as-code cho authorization và workload identity.
- Secret manager cho secret value, version và access policy.
- Certificate management/PKI cho issuance và trust configuration.

Không coi một file trong Git là nguồn chuẩn nếu runtime cho phép admin console override. Ghi rõ precedence giữa environment variable, config file, remote config, database, feature flag và admin UI.

### 3.3. Baseline theo môi trường

Dev, staging và production có thể dùng cùng pattern nhưng cần tách:

- Client ID và redirect URI.
- Issuer/tenant và signing key.
- Certificate và trust bundle.
- Workload identity subject/audience.
- Secret path và KMS key.
- Cookie domain và allowed origin.
- API endpoint, scope và data boundary.
- CI/CD deployment identity.

Không cho staging token hoặc credential được chấp nhận tại production. Không dùng signing key production trong môi trường test chỉ để giảm công sức cấu hình.

## 4. Phân loại cấu hình theo mức độ rủi ro

Không phải mọi setting có cùng tác động. Có thể phân loại:

| Mức | Ví dụ | Cách review |
| --- | --- | --- |
| Critical | Signing key, issuer trust, redirect URI, admin role, recovery override | Dual review, test bắt buộc, audit và rollback plan |
| High | MFA policy, token lifetime, session revocation, certificate trust | Owner + security review, evidence runtime |
| Medium | Rate limit, cookie lifetime, logging coverage, cache TTL | Review theo change và test định kỳ |
| Low | Metadata/label, non-sensitive display setting | Owner review và config validation |

Rủi ro phụ thuộc context. Một cookie setting có thể là critical nếu nó bảo vệ admin session; một scope có thể là high nếu truy cập dữ liệu nhạy cảm. Ghi rationale và impact, không chỉ dựa tên field.

## 5. Review identity provider và account policy

### 5.1. Issuer và tenant boundary

- Issuer URL phải chính xác và ổn định.
- Client chỉ tin issuer đã đăng ký; không lấy issuer từ input tùy ý.
- Tách tenant và environment; không dùng nhầm test tenant cho production.
- Kiểm tra signing key/JWKS trust và key rotation.
- Xác minh discovery metadata được lấy từ endpoint tin cậy.
- Không chấp nhận issuer gần giống hoặc host do attacker kiểm soát.

### 5.2. Account lifecycle

- Kiểm tra provisioning/deprovisioning và đồng bộ group/role.
- Tài khoản rời tổ chức phải disable và revoke session/credential theo SLA.
- Account dormant cần policy riêng.
- Shared account cần hạn chế, owner rõ và audit từng actor nếu còn tồn tại.
- Privileged account phải tách khỏi account thường khi policy yêu cầu.
- Role/group mapping phải allowlist claim và source tin cậy.
- Không tự động cấp role từ email domain hoặc claim do client kiểm soát.

### 5.3. Account lockout và anti-abuse

- Rate limit theo account, source, device và client.
- Chống brute force, password spraying và credential stuffing.
- Lockout không được tạo điều kiện DoS account bằng cách cố ý nhập sai.
- Có progressive delay, risk-based challenge hoặc bot defense.
- Thông báo lỗi không tiết lộ account có tồn tại hay không.
- Support unlock phải có identity verification và audit.

## 6. Password và password reset configuration

### 6.1. Password verifier

- Lưu password bằng password hashing function chuyên dụng như Argon2id, scrypt hoặc bcrypt với salt riêng.
- Chọn cost parameter theo khả năng vận hành và threat model.
- Không dùng SHA-256 đơn thuần hoặc encryption có thể giải ngược để lưu password.
- Pepper nếu dùng phải được bảo vệ riêng trong KMS/secret manager.
- Có quy trình nâng cost và rehash khi người dùng đăng nhập.
- Không log password hoặc request body chứa password.

### 6.2. Password policy

- Độ dài tối thiểu và maximum length phải phù hợp; tránh cắt ngắn âm thầm.
- Chặn password phổ biến, đã bị lộ và biến thể dễ đoán.
- Cho phép password manager và paste.
- Không ép thay password định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu cụ thể.
- Kiểm tra encoding, Unicode normalization và password comparison nhất quán.
- Thông báo lỗi không tiết lộ account enumeration.

### 6.3. Reset và recovery

- Reset token có entropy cao, one-time và TTL ngắn.
- Token được lưu dạng hash hoặc reference an toàn phía server.
- Link reset dùng HTTPS, host allowlist và không nhận redirect tùy ý.
- Reset thành công phải xử lý session/token theo policy.
- Recovery contact change có notification và delay/step-up khi rủi ro cao.
- Không dùng câu hỏi bảo mật yếu làm factor duy nhất.
- Support-assisted reset phải có identity proofing và audit.

### 6.4. Checklist password

| Kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Password hashing | Algorithm/cost/salt policy được xác nhận |
| Breached password screening | Service/rule và fail behavior được tài liệu hóa |
| Rate limit | Test account/source burst và distributed pattern |
| Enumeration resistance | Response body/status/timing không phân biệt account |
| Reset token | TTL, one-time, secure storage và invalidation test |
| Password change | Session/recovery policy và audit event |
| Logging | Canary password không xuất hiện trong log/trace |

## 7. MFA, passkey và authentication assurance

### 7.1. MFA policy

- Xác định account/role/action nào bắt buộc MFA.
- Privileged action cần step-up phù hợp với risk.
- Không xem hai yếu tố cùng một thiết bị/nguồn là độc lập mặc định.
- Có giới hạn số lần OTP/push challenge.
- Chống push fatigue và yêu cầu user context rõ ràng.
- Factor enrollment/removal yêu cầu xác thực hiện tại hoặc recovery mạnh.
- Recovery code one-time, lưu an toàn và audit khi dùng.
- Factor reset bởi support cần approval và identity proofing.

### 7.2. Passkey/WebAuthn

- RP ID và allowed origin được cấu hình chính xác.
- Challenge ngẫu nhiên, có expiry và gắn với transaction.
- Server xác minh clientData origin, RP ID hash, challenge và signature.
- User verification requirement phù hợp policy.
- Credential ID được gắn đúng account và có lifecycle.
- Attestation policy được chọn có chủ đích; không yêu cầu attestation không cần thiết.
- Backup/sync eligibility được xử lý theo threat model.
- Credential removal, rename và recovery được audit.

Không suy ra passkey an toàn chỉ vì UI hiển thị “biometric”. Cần xác minh WebAuthn protocol và cấu hình RP/origin ở server.

### 7.3. Authentication assurance

Định nghĩa assurance theo hành động và rủi ro:

- Login thông thường có thể chấp nhận session hiện tại nếu còn hợp lệ.
- Đổi recovery contact cần reauthentication.
- Thêm factor hoặc passkey cần xác thực mạnh và thông báo.
- Export dữ liệu nhạy cảm hoặc thay đổi payment có thể yêu cầu step-up.
- Privileged configuration change có thể cần phishing-resistant factor và dual approval.

Assurance phải dựa vào phương thức và ngữ cảnh đã xác minh, không chỉ một claim tự khai từ client.

## 8. OAuth 2.0 và OpenID Connect configuration

### 8.1. Client type và grant

- Native app và browser-based public client dùng Authorization Code + PKCE.
- Confidential client giữ secret/key ở server-side secure storage.
- Không dùng implicit flow cho ứng dụng mới.
- Không dùng Resource Owner Password Credentials grant cho thiết kế mới.
- Chỉ bật grant cần thiết cho client.
- Client credentials chỉ dùng cho machine-to-machine với workload identity/credential phù hợp.
- Dùng sender-constrained token khi risk và platform hỗ trợ.

### 8.2. Redirect URI

- Exact-match redirect URI theo client registration.
- Không dùng wildcard host/path rộng.
- Không cho redirect tới domain do user/client tùy ý chỉ định.
- Kiểm tra scheme, host, port, path và query theo profile.
- Native app ưu tiên claimed HTTPS App Links/Universal Links khi phù hợp; custom scheme phải được PKCE bảo vệ.
- Không dùng open redirect làm callback.
- Tách redirect URI dev/staging/prod.

### 8.3. PKCE, state và nonce

- Bắt buộc PKCE S256 cho native/public clients.
- State ngẫu nhiên, gắn transaction, one-time và expiry.
- OIDC nonce được tạo và xác minh trong ID token.
- Không dùng lại state/nonce giữa các transaction.
- Callback phải được ràng buộc với đúng client, issuer và transaction.
- Xử lý error callback có state và không render error text như HTML tin cậy.

### 8.4. Issuer, audience và token claims

- API chỉ chấp nhận issuer đã cấu hình.
- Audience phải đúng resource server.
- Kiểm tra signature, allowed algorithm, key ID, expiry và not-before.
- Validate authorized party/client khi profile yêu cầu.
- Kiểm tra scope/role/tenant mapping server-side.
- Không tin token từ issuer khác chỉ vì chữ ký hợp lệ.
- Không chấp nhận alg=none hoặc algorithm downgrade.
- Không lấy key URL tùy ý từ token header.

### 8.5. Scope và consent

- Scope tối thiểu theo use case.
- Tách read/write/admin scope.
- Consent và delegated grant có owner, client và thời hạn/review.
- Không tự động cấp quyền rộng từ default scope.
- Review offline_access/refresh token scope.
- Revoke grant khi client không còn cần hoặc bị compromise.

## 9. Token lifetime, refresh rotation và revocation

### 9.1. Access token

- Lifetime theo sensitivity và khả năng revocation.
- Audience cụ thể; không dùng một token cho nhiều resource không liên quan.
- Scope tối thiểu.
- Signing key và JWKS rotation có overlap hợp lý.
- Resource server validate issuer/audience/signature/expiry.
- Không log raw JWT hoặc opaque token.

### 9.2. Refresh token

- Lưu ở client/server theo secure storage phù hợp.
- Rotation và reuse detection nếu authorization server hỗ trợ.
- Token family có reference để revoke và audit.
- TTL, absolute lifetime và inactivity timeout được xác định.
- Logout/password reset/credential compromise có policy revoke rõ.
- Xử lý concurrency/retry để không gắn nhầm reuse hợp lệ với theft.

### 9.3. Revocation propagation

Review toàn bộ đường đi:

1. Identity provider đánh dấu principal/session/token family bị revoke.
2. Authorization server ngừng refresh hoặc exchange.
3. Introspection/cache cập nhật.
4. Gateway/resource server nhận deny hoặc kiểm tra state.
5. Downstream session/token được invalidate.
6. Mobile/web client xóa local credential.

Nếu JWT được xác minh offline, revoke tại IdP có thể không làm token mất hiệu lực ngay. Cần lifetime ngắn, denylist, introspection, subject version hoặc gateway policy theo risk. Ghi SLA propagation và test thực tế.

## 10. Session và browser cookie configuration

### 10.1. Session lifecycle

- Session ID đủ entropy và rotate sau login/step-up/privilege change.
- Idle timeout và absolute timeout theo sensitivity.
- Revoke server-side khi logout, recovery hoặc compromise.
- Giới hạn concurrent session theo policy.
- Device binding nếu có threat model và UX phù hợp.
- Không đặt session ID trong URL.
- Không dùng session fixation-prone flow.
- Reauthentication trước action nhạy cảm.

### 10.2. Cookie flags

Với cookie chứa session:

- `Secure`: chỉ gửi qua HTTPS.
- `HttpOnly`: JavaScript không đọc được cookie.
- `SameSite`: chọn Lax/Strict/None theo luồng; None yêu cầu Secure.
- `Path` và `Domain`: scope hẹp nhất có thể.
- Prefix `__Host-` nếu phù hợp: Secure, Path=/ và không có Domain.
- Max-Age/Expires: phù hợp session lifecycle.

Cookie flags không thay CSRF protection hoặc XSS prevention. Review callback/cross-site POST và embedded flow để chọn SameSite đúng.

### 10.3. CSRF, CORS và origin

- CSRF token hoặc cơ chế chống CSRF phù hợp cho cookie-authenticated state change.
- CORS allowlist origin chính xác; không reflect arbitrary Origin.
- Không kết hợp wildcard origin với credentials.
- Kiểm tra `Origin`/`Referer` theo policy khi phù hợp.
- Không coi CORS là authorization; server vẫn kiểm tra user và resource.
- CSP, frame policy và referrer policy hỗ trợ giảm bề mặt tấn công.

## 11. API authentication và authorization configuration

- Chọn auth mechanism theo client: OAuth access token, mTLS, signed request hoặc workload identity.
- Validate issuer, audience, expiry, signature và key rotation.
- Enforce scope/role/tenant/object authorization ở resource server.
- Không tin client-supplied user ID, role hoặc tenant header.
- Rate limit login, token endpoint và API nhạy cảm.
- Phân biệt `401` authentication failure với `403` authorization denial theo semantics.
- Không để health/debug endpoint tiết lộ token/config.
- Dùng request signing hoặc sender-constrained token khi cần chống replay.
- Idempotency key và replay window phải được định nghĩa cho operation có side effect.
- Không ghi `Authorization` header hoặc raw credential trong access log.

### 11.1. Multi-tenant boundary

Tenant phải được lấy từ claim/identity đã xác minh và đối chiếu với resource ownership. Không cho client tự gửi tenant ID rồi dùng trực tiếp làm authorization context. Review cache key, database row-level policy và background job để tránh cross-tenant mix-up.

## 12. Certificate, mTLS và key management

### 12.1. Certificate validation

- Validate chain tới trust anchor đã cấu hình.
- Kiểm tra validity period và clock.
- Kiểm tra SAN/hostname hoặc URI identity đúng service.
- Kiểm tra EKU/key usage phù hợp.
- Có policy revocation/OCSP/CRL hoặc short-lived certificate.
- Không bỏ qua validation khi gặp self-signed hoặc lỗi chain.
- Trust store chỉ chứa CA cần thiết; review CA addition/removal.

### 12.2. mTLS

- Client certificate được map tới workload identity cụ thể.
- Không dùng subject DN chung cho nhiều workload nếu cần accountability.
- Gateway truyền identity downstream qua channel tin cậy; không tin header client tự gửi.
- Certificate rotation có overlap và kiểm tra consumer.
- Revocation propagation tới service mesh/gateway được đo và test.

### 12.3. Private key

- Ưu tiên KMS/HSM hoặc hardware-backed storage.
- Không nhúng private key trong image, source hoặc log.
- Tách quyền key admin, signer và auditor.
- Rotation, backup và recovery có approval.
- Audit sign/decrypt operation và key policy change.

## 13. Workload identity và service authentication

- Tách identity theo service, namespace, environment và workload.
- Audience/subject/issuer trong federation trust policy phải exact.
- Token có TTL ngắn và scope tối thiểu.
- Không dùng service account mặc định nếu không cần.
- Kubernetes projected token có audience/expiry phù hợp.
- RBAC tính cả quyền tạo pod, exec, sửa service account và đọc secret.
- CI/CD federation giới hạn repository, branch, workflow và environment.
- mTLS/SPIFFE identity được map đúng trust domain.
- Workload termination phải revoke credential/lease theo SLA.
- Không dùng shared static secret làm bootstrap dài hạn nếu có thể dùng platform identity.

## 14. Secret manager và credential storage

- Workload xác thực trước khi đọc secret.
- Policy ràng buộc principal, path, action, version và environment.
- Không cấp wildcard rộng.
- Envelope encryption dùng DEK/KEK và KMS/HSM phù hợp.
- Secret value không nằm trong source, image, build artifact hoặc command line.
- Runtime injection và cache có TTL/version.
- Rotation có overlap, consumer adoption và revoke cũ.
- Dynamic credential có lease/revocation nếu upstream hỗ trợ.
- Audit read/write/rotate/revoke nhưng không log plaintext.
- Backup và key recovery được kiểm thử.

## 15. Logging, monitoring và audit configuration

- Event schema có actor, subject, action, resource, outcome và time.
- Ghi authentication, factor, token, session, recovery, key và policy lifecycle.
- Producer được xác thực; client không tự khai actor.
- Không log password, OTP, recovery code, token, cookie hoặc private key.
- Có event_time và observed_time, request/trace/session reference.
- Audit store append-only/tamper-evident theo risk.
- Tách quyền producer, storage admin, key admin, retention admin và auditor.
- Có alert cho policy change, admin action, factor reset, token reuse và secret read anomaly.
- Kiểm tra event loss, ingestion lag và schema drift.
- Retention, privacy và export access được định nghĩa.

## 16. TLS, proxy và network boundary

- TLS version/cipher policy theo baseline hiện hành của tổ chức.
- Certificate hostname validation được bật ở client.
- Không tắt TLS verification trong production.
- Reverse proxy chỉ tin forwarded headers từ proxy được cấu hình.
- Redirect/issuer host không bị ảnh hưởng bởi Host header không tin cậy.
- Admin endpoint giới hạn network và identity.
- Egress của IdP, token service và secret manager được kiểm soát.
- DNS và service discovery không cho attacker redirect trust endpoint.
- Service-to-service channel dùng mTLS/workload identity khi phù hợp.
- Network segmentation không thay authentication/authorization.

## 17. Configuration as Code và change management

### 17.1. Review thay đổi

Mỗi thay đổi security-sensitive nên có:

- Owner và mục đích.
- Threat/risk rationale.
- Config diff và policy version.
- Environment và blast radius.
- Peer/security approval theo mức rủi ro.
- Automated test và runtime validation.
- Rollback plan và rollback trigger.
- Deployment identity và audit event.

Không triển khai thay đổi redirect URI, issuer trust, signing key, MFA policy hoặc admin role qua thao tác console không có audit/change record.

### 17.2. IaC và policy-as-code

Lưu cấu hình không nhạy cảm trong version control, review diff và kiểm tra bằng linter/policy engine. Secret value nằm trong secret manager. Pipeline cần identity riêng và quyền theo environment; không để pull request từ fork đọc production secret.

### 17.3. Drift detection

Drift là khác biệt giữa cấu hình được phê duyệt và cấu hình thực tế. Phát hiện drift bằng:

- Periodic export/snapshot từ runtime.
- So sánh với desired state.
- Audit event cho admin/config change.
- Cloud configuration monitor.
- Policy evaluation trong CI/CD.
- Reconciliation sau deployment.

Không tự động ghi đè mọi drift. Có thể là emergency change hợp lệ hoặc một dấu hiệu compromise. Triage, bảo toàn evidence, xác định owner và phê duyệt trước khi sửa.

### 17.4. Ngoại lệ

Mỗi exception cần:

- Lý do và rủi ro được chấp nhận.
- Principal/component/environment cụ thể.
- Compensating control.
- Owner và approver.
- Expiry/review date.
- Cách đo và kế hoạch loại bỏ.

Không dùng exception vô thời hạn để che một cấu hình không đạt baseline.

## 18. Ví dụ cấu hình và kiểm tra tự động

Ví dụ YAML minh họa policy mong muốn cho một OAuth client public. Đây là cấu trúc khái niệm, không phải schema của một IdP cụ thể:

~~~yaml
client:
  id: mobile-app-prod
  type: public
  environment: production
  grants:
    - authorization_code
  require_pkce: true
  pkce_method: S256
  redirect_uris:
    - https://login.example.com/mobile/callback
  scopes:
    - openid
    - profile
  refresh_token:
    rotation: enabled
    reuse_detection: enabled
    absolute_lifetime: policy_defined
  client_secret:
    embedded: false
~~~

Không đặt secret thật hoặc token vào file cấu hình. Giá trị như lifetime phải được xác định theo risk, platform capability và policy thực tế; ví dụ không áp một thời lượng chung cho mọi hệ thống.

### 18.1. Java: validate configuration lúc khởi động

~~~java
public record OAuthClientSettings(
    String issuer,
    String clientId,
    boolean publicClient,
    boolean pkceRequired,
    String pkceMethod,
    List<URI> redirectUris,
    Set<String> allowedAudiences
) {}

public final class OAuthSettingsValidator {
    public void validate(OAuthClientSettings settings) {
        requireHttps(settings.issuer());

        if (settings.publicClient() && !settings.pkceRequired()) {
            throw new IllegalStateException(
                "Public client must require PKCE"
            );
        }

        if (settings.publicClient()
                && !"S256".equals(settings.pkceMethod())) {
            throw new IllegalStateException(
                "Public client must use PKCE S256"
            );
        }

        if (settings.redirectUris().isEmpty()) {
            throw new IllegalStateException(
                "At least one exact redirect URI is required"
            );
        }

        settings.redirectUris().forEach(this::validateExactRedirectUri);
    }

    private void requireHttps(String value) {
        URI uri = URI.create(value);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null) {
            throw new IllegalStateException("Issuer must be HTTPS");
        }
    }

    private void validateExactRedirectUri(URI uri) {
        if (uri.getHost() == null || uri.getFragment() != null
                || uri.getUserInfo() != null) {
            throw new IllegalStateException("Invalid redirect URI");
        }
    }
}
~~~

Đây là ví dụ minh họa. Production cần validate allowlist chính xác, scheme theo loại client, host/path/port, duplicate URI, query policy và issuer metadata; không chỉ kiểm tra URI có HTTPS. Với native custom scheme, áp dụng profile riêng và PKCE. Dùng thư viện URI chuẩn, không so sánh URL bằng substring.

### 18.2. Policy test minh họa

~~~java
@Test
void publicClientMustUsePkceS256() {
    OAuthClientSettings settings = new OAuthClientSettings(
        "https://id.example.com",
        "mobile-app-prod",
        true,
        true,
        "S256",
        List.of(URI.create(
            "https://login.example.com/mobile/callback"
        )),
        Set.of("api.example.com")
    );

    assertDoesNotThrow(() -> validator.validate(settings));
}

@Test
void publicClientWithoutPkceIsRejected() {
    OAuthClientSettings settings = validSettings()
        .withPkceRequired(false);

    assertThrows(
        IllegalStateException.class,
        () -> validator.validate(settings)
    );
}
~~~

Đoạn test giả định helper/builder để minh họa; điều quan trọng là kiểm thử cả cấu hình hợp lệ và cấu hình phải bị từ chối. Nên bổ sung test cho wildcard redirect, wrong issuer, wrong audience, missing cookie flags, insecure TLS, broad secret policy và missing audit.

## 19. Quy trình configuration review

Một vòng review có thể thực hiện theo các bước:

1. **Scope:** xác định service, environment, data, identity và owner.
2. **Collect:** lấy desired config, effective runtime config, version và audit history.
3. **Threat model:** xác định credential, trust boundary, attacker path và blast radius.
4. **Baseline:** áp tiêu chuẩn nội bộ và profile theo loại client/service.
5. **Inspect:** kiểm tra cấu hình, quyền, key, token, session, network và logging.
6. **Test:** xác minh runtime behavior bằng test an toàn, negative test và policy simulation.
7. **Rate:** phân loại finding theo severity, exploitability và impact.
8. **Remediate:** gán owner, deadline, change plan và rollback.
9. **Verify:** kiểm tra effective config sau deploy và bằng chứng runtime.
10. **Record:** lưu report, exception, approval và next review date.

### 19.1. Evidence cần lưu

- Config snapshot và version/hash.
- Environment, service, owner và deployment ID.
- Policy evaluation output.
- Test result, request ID và sanitized response.
- Admin/audit event của thay đổi.
- Finding, severity, risk rationale và exception.
- Remediation owner, due date và verification evidence.

Không lưu secret value trong report. Redact endpoint parameter, credential, private key và PII trước khi export.

## 20. Findings, severity và remediation

| Severity | Ví dụ | Kỳ vọng xử lý |
| --- | --- | --- |
| Critical | Production issuer trust sai, redirect tới domain attacker, signing key lộ, cross-environment token accepted | Contain ngay, change khẩn cấp và xác minh toàn bộ downstream |
| High | MFA bypass cho privileged action, refresh token không rotation, secret policy quá rộng | Ưu tiên sửa, có owner/deadline và compensating control |
| Medium | Cookie scope rộng, audit thiếu một số lifecycle event, token lifetime dài hơn policy | Kế hoạch sửa theo risk và kiểm thử |
| Low | Metadata/label chưa chuẩn, warning không ảnh hưởng trust boundary | Đưa vào backlog có owner |

Mỗi finding cần:

- Mô tả cấu hình hiện tại và expected state.
- Asset/principal/environment bị ảnh hưởng.
- Attack path cụ thể.
- Impact và likelihood.
- Evidence/reference, không chứa secret.
- Remediation và rollback.
- Owner, due date, approver.
- Retest criteria và trạng thái.

Không đánh giá severity chỉ bằng tên setting. Một redirect URI sai trên client production có thể Critical; cùng lỗi trên sandbox cô lập có thể thấp hơn nếu không có trust hoặc data path tới production.

## 21. Những lỗi review thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Chỉ review file Git | Bỏ sót runtime override/admin console | So sánh desired và effective config |
| Dùng một baseline cho mọi client | Native, web và service có threat model khác nhau | Profile theo client/principal type |
| Chỉ kiểm tra setting bật/tắt | Không xác minh behavior | Negative test và runtime evidence |
| Bỏ qua default framework | Default có thể yếu hoặc thay đổi theo version | Pin version và kiểm tra effective default |
| Không tách environment | Staging credential/token đi vào production | Issuer/client/key/secret riêng |
| Wildcard redirect/origin | Mở đường token/code leakage | Exact allowlist và test |
| Token lifetime quá dài | Tăng cửa sổ lạm dụng sau theft | Lifetime theo risk và revocation capability |
| Reset password được coi là revoke session | Session/token cũ tiếp tục hoạt động | Test end-to-end revocation |
| Bỏ qua recovery flow | Attacker bypass MFA qua support/recovery | Review assurance ngang login |
| Không review workload identity | Service account có quyền production quá rộng | Exact subject/audience và least privilege |
| Chỉ kiểm tra TLS ở edge | Downstream connection có thể không validate | End-to-end certificate validation |
| Logging không được kiểm thử | Token/OTP lọt vào SIEM | Canary secret và redaction test |
| Ngoại lệ không expiry | Temporary bypass trở thành vĩnh viễn | Owner, compensating control và expiry |
| Drift tự động overwrite | Xóa evidence của compromise hoặc emergency change | Triage drift trước remediation |
| Không kiểm tra rollback | Change gây lockout/outage | Canary, rollback trigger và recovery test |
| Không lưu policy version | Không tái dựng quyết định trước sự cố | Versioned policy và audit reference |

## 22. Ma trận kiểm thử configuration review

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Public OAuth client không bật PKCE | Policy test fail |
| PKCE dùng plain thay vì S256 | Policy test fail theo baseline |
| Redirect URI có wildcard host/path | Review phát hiện và từ chối |
| Redirect URI trỏ staging từ production client | Environment boundary test fail |
| Issuer không nằm trong allowlist | Token bị từ chối |
| Audience sai | Resource server từ chối |
| Token hết hạn hoặc signature sai | Authentication validation từ chối |
| Refresh token cũ bị reuse theo rotation policy | Token family bị revoke/cảnh báo |
| Session logout vẫn truy cập API | Revocation test fail |
| Cookie session thiếu Secure/HttpOnly | Configuration test fail |
| Cookie SameSite không phù hợp flow | CSRF/callback integration test phát hiện |
| CORS phản chiếu arbitrary Origin với credentials | Security test fail |
| API tin role/tenant header từ client | Authorization test fail |
| Password log canary xuất hiện | Redaction test fail |
| Recovery token dùng lại hoặc hết TTL | Server từ chối |
| Factor enrollment không step-up | Policy test fail |
| WebAuthn origin/RP ID sai | Server từ chối assertion |
| Certificate hostname/SAN sai | TLS client từ chối |
| Workload staging xin production audience | Federation trust test fail |
| Service account đọc secret ngoài path | Authorization test fail |
| KMS key policy cho principal quá rộng | Policy review fail |
| Audit event không có actor/outcome | Schema validation fail |
| Audit store không nhận event | Completeness alert và degraded-mode policy |
| Runtime config drift khỏi approved state | Drift detection tạo finding |
| Emergency exception không có expiry | Governance test fail |
| Deployment identity có quyền admin toàn tổ chức | CI/CD least-privilege test fail |
| Rollback cấu hình không khôi phục service | Release gate fail |

## 23. Tình huống thực hành

Một ứng dụng web và mobile dùng chung identity provider. Review phát hiện:

- Web client cho phép redirect URI wildcard.
- Mobile client có client secret trong binary và dùng custom URI scheme không có PKCE.
- Access token dùng chung audience cho ba API; refresh token có lifetime dài và không rotation.
- Cookie session thiếu SameSite và Domain scope đặt ở domain cha.
- API gateway xác minh chữ ký nhưng không kiểm tra audience.
- Staging workload dùng cùng service account với production và đọc được secret production.
- Admin console cho phép reset MFA mà không yêu cầu step-up.
- Log gateway ghi Authorization header khi request lỗi.

**Yêu cầu:** lập kế hoạch review và remediation theo ưu tiên.

**Hướng phân tích:**

1. Critical: chặn cross-environment access; tách workload identity/service account và secret path; sửa audience validation; loại raw Authorization header khỏi log và xử lý log đã lưu theo incident policy.
2. High: thu hẹp redirect URI exact-match; chuyển native app sang Authorization Code + PKCE S256, loại client secret khỏi binary; thêm step-up cho MFA reset.
3. High/Medium: bật refresh token rotation/reuse detection và xác định lifetime theo risk; tách audience theo API.
4. Medium/High: đặt cookie Secure, HttpOnly, SameSite phù hợp; scope Domain/Path hẹp nhất và kiểm thử CSRF.
5. Tách client ID, issuer, key, redirect URI và secret theo environment.
6. Tạo policy-as-code, automated negative tests và drift detection.
7. Triển khai theo canary, đo login/token/API success, chuẩn bị rollback và kiểm tra revocation propagation.
8. Lưu finding, owner, approval, exception expiry và evidence retest.

## 24. Câu hỏi tự kiểm tra

1. **Configuration review là gì?** Kiểm tra desired/effective configuration của hệ thống xác thực so với threat model và baseline.
2. **Vì sao review file Git chưa đủ?** Runtime có thể bị override qua environment, admin console, database hoặc remote config.
3. **Vì sao redirect URI phải exact-match?** Ngăn authorization code/token bị gửi tới endpoint ngoài ý muốn.
4. **Native public client cần gì?** Authorization Code Flow với PKCE S256 và không nhúng client secret.
5. **Reset password có revoke mọi session không?** Không; cần policy và kiểm thử revocation cho session/token/downstream.
6. **Vì sao recovery cần được review như login?** Recovery yếu có thể bypass MFA và trao account cho attacker.
7. **Audience validation bảo vệ điều gì?** Ngăn token dành cho resource khác được chấp nhận tại API hiện tại.
8. **Workload identity policy cần giới hạn gì?** Issuer, subject, audience, environment, scope và resource.
9. **Drift có nên tự động overwrite không?** Không trước khi triage; drift có thể là emergency change hoặc dấu hiệu compromise.
10. **Một finding tốt cần những gì?** Expected/current state, attack path, impact, evidence, owner, remediation, rollback và retest.

**Ghi nhớ:** Configuration review phải so sánh cấu hình được phê duyệt với cấu hình thực tế và kiểm chứng bằng hành vi runtime. Rà soát trust boundary, issuer/audience, redirect URI, PKCE, MFA/recovery, token/session, cookie, API authorization, certificate, workload identity, secret storage và audit. Ưu tiên theo blast radius, dùng policy-as-code và negative test, kiểm soát ngoại lệ/drift, rồi xác minh remediation sau triển khai. Cấu hình an toàn chỉ có ý nghĩa khi được thực thi nhất quán ở mọi môi trường và mọi downstream.
