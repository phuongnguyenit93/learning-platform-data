# Rà soát quyền truy cập, dữ liệu chia sẻ và cấu hình đối tác định kỳ

> **Chủ đề:** Spring Security – federation. **Nhóm:** Triển khai và vận hành. Bài Knowledge độc lập này hướng dẫn thiết kế, thực hiện và kiểm chứng **đợt rà soát định kỳ** với các hệ thống đăng nhập liên kết: OpenID Connect (OIDC)/OAuth 2.0, SAML 2.0, CAS và kết nối thư mục/SCIM khi có sử dụng. Ba câu hỏi phải được trả lời **bằng bằng chứng thực tế** là: **Ai còn truy cập được cái gì? Dữ liệu nhận dạng nào đang được trao đổi với ai, cho mục đích gì? Mỗi cấu hình đối tác/khóa/callback hiện có đúng hợp đồng tin cậy và còn an toàn không?** Trọng tâm là vận hành **Spring Security Servlet, Java 17+**, chính sách least privilege, giảm thiểu dữ liệu, JML (joiner–mover–leaver), quản lý thay đổi và kiểm toán. Các chu kỳ/số ngày trong ví dụ là **policy minh họa**, không phải thời hạn pháp lý hay mặc định của Spring.

## 1. Kết quả học tập

Sau bài, người học có thể:

1. Lập **federation inventory** với owner, IdP/OP, RP/SP, application, tenant, registrationId, issuer/entityID, metadata URL, audience, ACS/redirect URI, key/cert, scopes/attributes, provisioning/deprovisioning và nhật ký thay đổi.
2. Phân biệt **xác thực liên kết** (user là ai) với **ủy quyền nghiệp vụ** (user có thể làm gì), và xác định các lớp quyền: account tại IdP, nhóm thư mục, claims/tokens, authority mapping, phân quyền ứng dụng, quyền resource/tenant, API clients và session.
3. Thiết lập review cadence dựa trên rủi ro (privileged, dữ liệu nhạy cảm, đối tác mới, không hoạt động lâu) và **trigger ngay khi có sự kiện quan trọng** (leaver, compromise, key leak, thay đổi issuer/callback hoặc tăng dữ liệu chia sẻ).
4. So sánh **actual effective access** với **approved desired access**, tìm orphan accounts, stale group grants, role creep, SoD conflicts, shared identities, contractor hết hạn và service account có quyền không dùng.
5. Rà soát **attribute release** của SAML/OIDC, scopes/consent, UserInfo, profile/group values, SCIM mappings và retention; kiểm tra purpose, legal/contract basis, minimization, visibility/receiver và thông báo cho chủ thể khi phù hợp.
6. Kiểm tra partner trust configuration: signed SAML metadata, IdP certificates, `validUntil`/`cacheDuration`, OIDC discovery `issuer`/`jwks_uri`, allowed redirect URIs, logout endpoints, algorithms, SP signing/decryption credentials, TLS/PKIX, secret expiry và trust anchor.
7. Triển khai quy trình **người yêu cầu – người duyệt độc lập – người thực thi – người xác minh**, có bằng chứng snapshot/diff/approval/closure, không cho owner tự chứng nhận quyền đặc quyền của chính mình.
8. Viết kiểm thử Spring Security nhằm chứng minh runtime issuer/audience/role/tenant enforcement còn hiệu lực sau thay đổi; không biến bảng review thành cơ chế authorization.
9. Chạy được demo Java 17 độc lập để phân loại partner drift và quyền cần rà soát/thu hồi bằng dữ liệu tổng hợp, đầu ra xác định.
10. Lập dashboard, ticket/runbook, negative test matrix và tiêu chí nghiệm thu/đóng kỳ rà soát.

**Nguyên tắc:** “Tài khoản vẫn đăng nhập được” **không chứng minh** quyền hợp lệ, và “chứng thư chưa hết hạn” **không chứng minh** đối tác còn đáng tin. Review phải dựa vào inventory có owner, desired policy, effective configuration, runtime evidence, phạm vi chia sẻ dữ liệu và kết quả xử lý sai lệch.

## 2. Bối cảnh và ranh giới liên kết

Giả sử một doanh nghiệp vận hành cổng `https://portal.example.org` với:

| Đối tác/nguồn | Giao thức | Hệ nhận | Đối tượng/dữ liệu | Owner |
| --- | --- | --- | --- | --- |
| IdP nhân sự North | OIDC Authorization Code | Web app `registrationId=north-oidc` | `sub`, `name`, `email`, một số role app đã duyệt | IAM + HR + app |
| Đối tác South | SAML2 Web Browser SSO | SP `registrationId=south-saml` | Stable NameID, department, approved group claims | Đối tác + IAM + app |
| CAS của intranet | CAS protocol | CAS service/filter | CAS subject/service attributes tối thiểu | IAM vận hành nội bộ |
| Thư mục doanh nghiệp | LDAP/AD/SCIM | Provisioning/authorization store | account status, manager, group membership | Directory/HR |
| API trao đổi dữ liệu | OAuth2 Resource Server | API với issuer/audience riêng | Access scopes, tenant, resource grants | API owner + Security |

Đây là **mô hình học tập**, không phải thông tin về đối tác thật. Trong production, mỗi endpoint, owner, certificate, purpose và tenant phải đến từ inventory được xác thực. Không tạo review report chứa raw production SAMLResponse, ID Token, LDAP exports có mật khẩu hoặc danh sách nhân sự đầy đủ chỉ vì mục đích audit.

### 2.1. Sơ đồ quyền và dữ liệu

```text
     HR / Partner HR              IAM / Directory / SCIM
       employment                  accounts / groups
          |                             |
          +----------+------------------+
                     |
              Identity Provider
           OIDC OP / SAML IdP / CAS
                     |
           signed assertion / tokens
           limited identity attributes
                     |
                     v
           Spring Security RP / SP
        verified issuer + stable subject
                     |
           local account resolution
                     |
           approved role/tenant policy
                     |
             protected resource
                     |
          audit + session/token lifecycle
```

Bốn hệ có thể **không đồng bộ lập tức**: HR vô hiệu một nhân sự, directory đã disable account nhưng OAuth access token/JWT cũ còn hạn hoặc Spring HttpSession vẫn hoạt động; IdP đã bỏ một group nhưng application DB còn direct grant; key N2 đã publish nhưng một pod vẫn trust N1. Do đó review **phải reconcile theo nhiều nguồn**, không chỉ export danh sách IdP.

## 3. Ba sổ kiểm soát phải được đối chiếu

### 3.1. Sổ A — Quyền truy cập (Access & entitlement inventory)

| Trường | Cần lưu gì? | Bằng chứng |
| --- | --- | --- |
| `partnerId/registrationId` | Đối tác và integration cố định | App config/inventory |
| `issuer/entityID` | Trusted issuer; không lấy từ user query | OIDC discovery/SAML metadata approved |
| `internalAccountId` | ID nội bộ giả danh hóa cho audit | Account store |
| `federatedKey` | `(issuer, sub)` OIDC hoặc stable SAML identifier có issuer | Trusted claims và account mapping |
| `tenantId/resource` | Phạm vi được cấp quyền | Authorization DB/policy |
| `effectiveRole/permission` | Quyền **thật** tính từ group/direct/ABAC | Authorization engine + grants |
| `sourceOfGrant` | HR, group, SCIM, manual exception, break-glass | Grant provenance |
| `grantOwner/approver` | Người có thẩm quyền duyệt, khác owner đặc quyền nếu SoD | Ticket/approval |
| `createdAt/lastUsedAt/lastReviewedAt` | Tuổi quyền và độ hoạt động | Audited access records |
| `employment/contractStatus` | Active/leave/expired theo authoritative source | HR/partner feed |
| `expiry/reviewDue` | Thời hạn grant và kỳ review | Policy |
| `session/revocation state` | Phiên/token nào còn khả dụng sau revoke | Spring Session/IdP API |

Phân biệt **IdP group membership**, **Spring `GrantedAuthority`**, **database resource grants** và **token scope**. Chúng có thể là bốn tập khác nhau. Một user không nằm trong group `APP_ADMIN` tại IdP vẫn có thể đang giữ direct admin grant trong database; review mỗi group riêng sẽ bỏ sót.

### 3.2. Sổ B — Luồng dữ liệu chia sẻ (Claim/attribute release register)

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| `origin` | North OIDC OP | Nguồn thông tin |
| `recipient` | RP portal, API báo cáo | Đích nhận thực tế |
| `protocol/transport` | OIDC ID Token/UserInfo, SAML assertion, SCIM | Khác vòng đời và bảo vệ |
| `claim/attribute` | `sub`, `email`, `groups`, `employeeId` | Biết dữ liệu nào được chia sẻ |
| `purpose` | Login, liên hệ, policy tenant | Có cơ sở phục vụ mục đích |
| `required/optional` | `sub` bắt buộc; `name` optional | Data minimization |
| `classification` | Public/internal/PII/sensitive | Quyền truy cập/retention |
| `authorizedOwner` | Privacy + app owner | Người chịu trách nhiệm |
| `transform/mapping` | IdP group ID→APP_READER | Chống role escalation |
| `storage/retention` | Chỉ session, DB, logs, backup | Tránh nhân bản dữ liệu |
| `consent/notice/agreement` | Trust agreement/purpose/notice theo bối cảnh | Kiểm điều khoản sử dụng |
| `lastApprovedAt` | Ngày duyệt phát hành | Drift detection |

**OIDC `scope` không đồng nghĩa SAML `AttributeStatement`.** `openid` xác lập OIDC flow, `profile`/`email` xin các claim chuẩn ở OP; `groups` thường là custom claim tùy IdP. OAuth2 access token `scope` là quyền đối với API và **không mặc nhiên là nhóm tổ chức** hay role được RP phép sử dụng. Cần mapping có owner và issuer/tenant binding.

### 3.3. Sổ C — Cấu hình đối tác (Trust & integration register)

| Mục | OIDC/OAuth2 | SAML2 | CAS/SCIM khác |
| --- | --- | --- | --- |
| Identity/provider | `issuer-uri`, `authorization_uri` | `IdP EntityID`, SSO/SLO | CAS base URL, SCIM base URL |
| RP/client identifier | `client_id` | `SP EntityID` | CAS `service` |
| Callback | Exact `redirect_uri` | Exact ACS/Recipient/Destination | CAS callback/service |
| Key trust | JWKS URI, algorithms, `kid` | Signing KeyDescriptors, metadata signer, SP keys | TLS/service credentials |
| Credential lifecycle | Client secret/private key/KMS | Signing/decryption private keys | SCIM bearer/service secret |
| Data sharing | Scopes, ID Token/UserInfo, API consent | Released attributes, NameID, groups | CAS attributes, SCIM schema |
| Validity | JWKS/cache/secret expiry | `validUntil`/`cacheDuration`, cert rollover | TLS/cert/token expiry |
| Logout/revoke | OIDC logout/token revocation/session | SAML SLO/SessionIndex | CAS SLO, SCIM deactivate |
| Owner/change | IdP+RP+Security | IdP+SP+Security | Directory/partner service |
| Allowed network | HTTPS/PKIX/hostname/egress | HTTPS/metadata fetch/ACS | mTLS/firewall/rate limit |

**Không nhầm certificate chain HTTPS với chứng thư XML Signature SAML**: ký SAML Response/Assertion dùng trusted IdP SAML signing credentials; TLS chứng minh máy chủ đường truyền. Metadata có `ds:Signature` cần metadata-signing trust anchor riêng khi hợp đồng yêu cầu.

## 4. Chọn chu kỳ rà soát: định kỳ cộng event-driven

Bảng sau là **lịch mẫu** để minh họa kỹ thuật; tổ chức phải đặt chính sách dựa vào pháp luật, rủi ro, hợp đồng và kiểm soát nội bộ:

| Đối tượng | Chu kỳ tham khảo | Trigger tức thời |
| --- | --- | --- |
| Privileged production access / break-glass | 90 ngày hoặc ngắn hơn theo risk | Leaver, incident, SoD conflict, privileged grant mới |
| Standard employee access | 180 ngày | Transfer, contractor expiration, source disabled |
| Federation partner config/trust | 90 ngày và trước mọi key rollover | Metadata/key/issuer/ACS/redirect URI thay đổi |
| Attribute release/privacy register | 90–180 ngày tùy PII/risk | Claim/scope mới, thay đổi mục đích/recipient, data incident |
| Client secrets, SP signing/decryption certs | Alert trước expiry 90/60/30 ngày | Lost key, rollover, cert distrust, invalid metadata |
| Service accounts/API clients | 90 ngày hoặc theo sensitivity | Key leak, scope change, unused credential, owner left |
| CI/canary trust/authorization regression | Mỗi deployment liên quan | Spring Security upgrade, IdP migration, policy update |
| Partner contract/owner/contact | Ít nhất theo review cycle | Hết hợp đồng, chuyển vendor, ownership gap |

**Kỳ rà soát không phải TTL của authorization**. Nếu HR phát sự kiện leaver hôm nay, không đợi 90 ngày mới khóa quyền. Event-driven revocation là luồng vận hành **gần thời gian thực theo SLA**, kết hợp session/token invalidation và action-time authorization.

### 4.1. Lý do có nhiều đồng hồ

```text
T_access_grant_review      Khi quyền cần người duyệt xác nhận lại
T_partner_configuration    Khi metadata/callback/client config cần owner xem lại
T_key_expiry               Khi certificate/secret kết thúc vòng đời kỹ thuật
T_jwt_exp                  Khi JWT đã phát hết hạn
T_http_session_expiry      Khi phiên app tự hết hạn hoặc bị revoke
T_contract_end             Khi đối tác không còn được phép sử dụng
T_employment_end           Khi người dùng không còn quyền theo HR

Không đồng nhất các mốc này.
```

Một quyền có thể “approved until next quarter” nhưng token đã cấp hôm nay mang `scope` trong vài phút/giờ; một session trong Spring Session Redis có thể sống qua một lần đổi nhóm nếu ứng dụng không kiểm lại authorization. Review phải nêu rõ **nguồn sự thật** và **cơ chế thực thi thu hồi**.

### 4.2. Trigger khi cấu hình đối tác thay đổi

- IdP thay `issuer`/EntityID, domain/hostname, OIDC `jwks_uri`, SAML metadata URL hoặc endpoint; cần review trust boundary.
- New SAML signing key public xuất hiện hoặc old key bị gỡ, metadata signature/cert thay, `validUntil` sắp hết.
- OAuth2 client thêm `redirect_uri` mới, đổi `grant_type`, `response_type`, `scope`, client auth method hoặc audience.
- SP ACS/EntityID/decryption cert thay; IdP SSO/SLO endpoints thay; CAS service path đổi.
- SCIM provisioning credentials/field mappings thay hoặc delta tăng users/groups bất thường.
- Đối tác đổi sub-processor/processor/receiver, khu vực xử lý hoặc mục đích dữ liệu; cân nhắc privacy/legal review.
- IdP khóa bất ngờ không được duyệt; ưu tiên quarantine/incident thay vì tự động trust mọi key trong response.
- App chuyển Spring Security/OpenSAML/Nimbus/cert libs phiên bản; chạy regression security tests.
- Partner bị compromise, mTLS/TLS PKIX fail hoặc metadata signature verification fail; security incident, không chỉ ticket review định kỳ.

## 5. Governance: RACI và phân tách nhiệm vụ

Review hiệu quả cần có owner rõ ràng:

| Vai trò | Trách nhiệm | Không nên tự làm |
| --- | --- | --- |
| Business/application owner | Xác nhận quyền theo nhu cầu nghiệp vụ; approve least privilege | Duyệt quyền admin của chính mình |
| IAM/federation engineer | Chụp cấu hình, phân tích diff, triển khai role/metadata updates | Tự approve exception không có owner |
| HR/partner identity owner | Chứng thực trạng thái nhân sự/hợp đồng, nguồn nhóm | Sửa business authorization không có review |
| Security/IAM governance | Kiểm SoD, rủi ro đối tác, key trust, exception duration | Tạo quyền production không có approvals |
| Privacy/data protection owner | Xác định purpose, data minimization, retention, onward disclosure | Mặc định thu thập mọi claim “để dự phòng” |
| Partner contact/IdP admin | Cung cấp metadata, claims contract, rotation schedule, attestation | Quyết định đơn phương quyền RP tenant |
| Implementer/operator | Thực hiện revoke/update có ticket, ghi evidence | Tự xóa audit log sau thay đổi |
| Independent verifier/auditor | So desired/actual, test negative cases, chốt closure | Chỉ tin comment “đã fix” mà không readback |

RACI cần ít nhất **Responsible**, **Accountable**, **Consulted**, **Informed** cho mỗi hệ đối tác. Những quyền high-risk yêu cầu **dual control** hoặc người duyệt độc lập theo policy. Reviewer vắng mặt/đối tác không phản hồi → **quyền chưa được duyệt**, không tự đánh dấu “approved by silence” nếu chính sách không cho phép.

### 5.1. Quyết định review phải có trạng thái thực

```text
DISCOVERED
  -> NEEDS_OWNER
  -> PENDING_REVIEW
  -> APPROVED or REVOKE_REQUESTED or ESCALATED
  -> IMPLEMENTED
  -> VERIFIED
  -> CLOSED_WITH_EVIDENCE
```

Không ghi `CLOSED` khi mới bấm `APPROVED` nhưng cấu hình thực chưa thay. Với revoke, cần xác nhận **effective grant** đã biến mất và session/token lifecycle được xử lý. Với dữ liệu dư thừa, cần xác nhận IdP ngừng phát field, RP ngừng lưu/log và downstream recipients không còn dùng.

## 6. Rà soát quyền: desired vs observed vs effective

### 6.1. Vì sao export IdP groups là chưa đủ?

Ứng dụng có thể có nhiều quyền chồng lớp:

```text
HR status (employed/contracted/terminated)
     |
directory group membership
     |
IdP mapping -> SAML groups / OIDC custom claim
     |
Spring GrantedAuthorities / method security
     |
local DB direct grants / tenant-specific ACL
     |
resource-level ABAC and break-glass
     |
actual authorization at request time
```

Một leaver bị disable IdP nhưng vẫn tồn tại **local service token**, legacy role in DB hoặc active HttpSession. Ngược lại một user có group nhưng app không map group đó thành authority, nên không có effective permission. Review cả **configuration** và **decision**.

### 6.2. Reconciliation thực tế

1. Lấy **desired access** từ approved request/HR/partner contract và business owner decisions.
2. Lấy **observed grants** từ directory groups, IdP app assignments, SAML/OIDC mapping config, Spring authorities store, local DB, SCIM, API client grants và privileged break-glass entries.
3. Tính **effective access** theo authorization policy đang chạy: role inheritance, deny overrides, ABAC theo tenant/resource/owner, delegated group memberships, temporary exceptions.
4. So desired/effective theo subject **stable immutable ID**, issuer, tenant và resource: `EXTRA` (chưa duyệt), `MISSING` (đã duyệt nhưng chưa có), `STALE` (review quá hạn), `ORPHAN` (không còn HR/partner owner), `SOD_CONFLICT`.
5. Quyết định: keep, reduce, revoke, reapprove with expiry, fix provisioning, escalate security.
6. Thực thi trong **đúng authoritative layer** (IdP group, app permission DB, SCIM directory, service account credentials); không “xóa ở dashboard” mà source auto-provision lại hôm sau.
7. Kiểm convergence giữa IdP, local DB, Spring Session, downstream API tokens và cache theo SLA.
8. Ghi bằng chứng diff trước/sau và negative authorization test thực tế (không chỉ trạng thái ticket).

### 6.3. Chỉ dùng identifier có phạm vi nguồn

- Với OIDC, `sub` chỉ ổn định trong phạm vi `iss`. Khóa federation an toàn thường là **`(iss, sub)`**, rồi ánh xạ tới internal account ID.
- Với SAML, **stable persistent NameID** hoặc identifier có đảm bảo tương ứng cần xét Format/NameQualifier/SPNameQualifier và IdP EntityID; transient NameID không phải khóa dài hạn.
- `email`/`preferred_username`/`name` có thể đổi, được tái sử dụng hoặc trùng giữa các IdPs. `email_verified` còn phụ thuộc claim source/trust policy, không tự cho phép auto-link.
- Một user có nhiều identities từ hai IdPs chỉ được liên kết qua **approved account linking process** và auditable evidence.
- Partner tenant không nên suy từ email domain; quy định tenant từ registration + local authoritative membership.

### 6.4. Những dạng quyền dễ bị bỏ sót

| Loại | Vì sao nguy hiểm | Cách kiểm |
| --- | --- | --- |
| Break-glass admin | Quyền đặc biệt sống lâu sau incident | Owner, expiry, use logs, independent approval |
| Contractor/guest | Contract end không cập nhật IdP group kịp | External HR/contract status + expiry |
| Shared accounts | Không quy trách nhiệm cá nhân | Đánh dấu exception, loại bỏ hoặc kiểm soát chặt |
| API service principals | Không phải user tương tác, không xuất hiện trong HR export | Client registration, scopes, owner, key history |
| Nested AD groups | Membership gián tiếp cấp quyền quá rộng | Effective transitive memberships |
| Local DB direct grants | IdP group removal không thu hồi | Reconcile app grants với IdP/HR |
| Old JWTs or Spring sessions | Quyền cũ tiếp tục trong window | Token TTL, introspection, session invalidation |
| Dormant accounts | Ít login không đồng nghĩa không còn cấp quyền | Last used + approved business owner |
| Cross-tenant role mapping | Group `Admins` ở IdP A bị map vào B | Issuer-specific allowlist, tenant check |
| Shadow OIDC clients | Client app cũ vẫn xin access scopes | Inventory OP registrations, owner, client secret rotation |

**Thứ tự ưu tiên:** Quyền không còn cơ sở/đối tượng đã nghỉ việc → **thu hồi theo incident/offboarding SLA ngay**; quyền privileged review quá hạn → hạn chế hoặc escalation theo risk; quyền standard mới dùng nhưng chưa được phê duyệt → điều tra source; quyền cần mở rộng → không cấp trước khi owner approve.

## 7. JML, SCIM và thu hồi phiên: review không đợi tới kỳ sau

### 7.1. Nguồn và hành động JML

**Joiner:** Xác nhận HR/partner source, tạo danh tính với stable subject, chỉ cấp entitlement tối thiểu, identity verification policy; không tự cấp admin do mail domain.

**Mover:** Đổi bộ phận/tenant/vai trò phải **remove old grants** trước hoặc đồng thời thêm grant mới; kiểm SoD. Một người chuyển Finance→Sales không nên giữ quyền chi tiền chỉ vì role ở token cũ.

**Leaver:** Disable identity/SCIM `active=false` hoặc provider-specific action theo contract, revoke local grants, sessions, refresh tokens/service credentials theo phạm vi, xác minh downstream access. **Tắt IdP account chưa tự tắt JWT đã phát** hoặc HttpSession của RP.

### 7.2. SCIM cần coi là provisioning chứ không là authorization engine

RFC 7643/7644 định nghĩa SCIM schema/protocol; SCIM `PATCH`/`PUT`/`DELETE` hoặc `active=false` là lifecycle operations, nhưng tác động chính xác phụ thuộc schema/IdP và connector contract. Khi một nhóm bị xóa trên IdP:

1. Chứng minh SCIM event đến target, authenticate bằng service credential đúng scope.
2. Chứng minh target xử lý idempotent, mapping group đúng tenant, không mất sự kiện do outage.
3. Xác nhận local grant đã bị gỡ trong effective policy.
4. Xác nhận sessions/tokens cũ bị hạn chế theo TTL, revocation hook hoặc action-time permission check.
5. Test rollback/duplicate/out-of-order events; có retry, dead-letter alert và reconciliation batch.
6. Không log toàn bộ SCIM User resource chứa PII khi báo audit; dùng IDs và schema-safe summaries.

SCIM `active=false` **không** có nghĩa mọi API JWT bị revoked theo RFC. Nếu cần near-real-time deny, API phải kiểm authoritative account/entitlement status hoặc token introspection/revocation mechanism đã thiết kế.

### 7.3. Logout ≠ toàn bộ thu hồi

| Tầng | Tác động khi logout | Review cần kiểm |
| --- | --- | --- |
| Spring HttpSession | Local session invalidation/cookie clearing | Session store, multi-pod, session indices |
| OIDC OP session | RP-initiated/back-channel logout tùy provider | Liên kết `sid`/`sub`, validate Logout Token |
| SAML IdP session | SAML SLO nếu được dùng và thành công | SessionIndex và multi-SP coverage |
| OAuth refresh token | Có thể revoke tại AS qua RFC 7009 nếu hỗ trợ | Revocation endpoint/client scope/owner |
| OAuth access token JWT | Có thể còn valid tới `exp` nếu offline verification | TTL/denylists/authoritative checks |
| Opaque access token | Resource server introspection `active` theo RFC 7662 | Caching/latency/availability policy |
| CAS TGC/TGT | CAS global login lifecycle | Local app session có invalidated không |
| App business grants | Không tự thay khi logout | DB/AuthorizationManager state and cache |

**Không chờ token expiry khi có incident khóa bị lộ/cấp quyền nguy hiểm** nếu còn biện pháp deny cấp bách. Hãy thiết kế refresh/access token TTLs, session revocation, authorization epoch và audit phù hợp mức độ rủi ro.

## 8. Dữ liệu chia sẻ: kiểm soát purpose và tối thiểu hóa

### 8.1. Bản đồ OIDC scopes/claims

| Claim/Scope | Ý nghĩa | Review nên hỏi |
| --- | --- | --- |
| `openid` | OIDC authentication flow | Ứng dụng cần ID Token cho login? |
| `sub` + `iss` | Federated subject identity | Có dùng thay email làm stable key không? |
| `profile` | Có thể yêu cầu nhiều profile claims | Có cần toàn bộ hay chỉ `name`? |
| `email`/`email_verified` | Email contact/verification claim | Có cần lưu? Người nhận nào sử dụng? |
| `address`/`phone` | PII có thể nhạy theo ngữ cảnh | Có thực sự cần trong SSO? |
| `groups` | Custom claims, không phải scope chuẩn OIDC Core | Có giới hạn số lượng/namespace/issuer? |
| `roles`/`entitlements` | Provider-specific authorization claims | Có mapping allowlist sang APP_*? |
| `acr`/`amr`/`auth_time` | Authentication strength/context | App kiểm risk level nào, không lạm dụng? |
| API `scope` (ví dụ `reports.read`) | Quyền resource cho access token | Có đúng API/audience, read vs write? |
| `offline_access` | Có thể cho refresh token theo policy OP | RP có cần truy cập lâu dài không? |

OIDC `profile` theo tiêu chuẩn có thể xin nhiều loại thông tin cá nhân; **đừng mặc định xin tất cả scopes**. `email_verified=true` chỉ có ý nghĩa trong IdP/claim trust contract; không tự đồng nhất email của hai issuers. Nếu chỉ cần tên hiển thị, ưu tiên claim tối thiểu thay vì thu đủ birthdate, phone, address.

**Rà soát cả nơi lưu:** ID Token thường chứa claims và có thể nằm trong session/security context; UserInfo response, SCIM User resource, logs, data lake, backups và telemetry có thể nhân bản PII. Không chỉ kiểm “IdP gửi field gì”, phải kiểm “RP/processor downstream giữ bao lâu và ai đọc”.

### 8.2. SAML Attribute Release

Ví dụ minh họa:

```xml
<saml:AttributeStatement
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Attribute Name="displayName">
    <saml:AttributeValue>Nguyễn Minh An</saml:AttributeValue>
  </saml:Attribute>
  <saml:Attribute Name="groups">
    <saml:AttributeValue>app-report-readers</saml:AttributeValue>
  </saml:Attribute>
</saml:AttributeStatement>
```

Đây là **fragment AttributeStatement không có chữ ký và không phải SAMLResponse xác thực được**. Dữ liệu có vẻ hợp lý không chứng minh IdP đã ký hoặc assertion đúng Issuer/Audience/Recipient/NotOnOrAfter.

Bài review hỏi:

1. `NameID` Format là persistent/transient/email, có đủ ổn định không?
2. Nhóm `groups` được phát từ directory nào, có nested groups/guest membership ngoài hợp đồng không?
3. Có gửi dư `memberOf` hàng trăm group khiến SAMLResponse to, gây 413/DoS/session bloat?
4. Chỉ các group values được IdP approved và RP allowlist có thể map thành app rights; không map tên `Admins` của mọi IdP thành `ROLE_ADMIN`.
5. Có gửi personal IDs/employee salary/birthdate hay thuộc tính không cần thiết không?
6. Data có bị encrypt khi trust/privacy agreement yêu cầu? **XML encryption không thay signature validation**.
7. Privacy/retention có áp cho raw XML/SAMLResponse debugging backups không?
8. Thay release policy **tại IdP trước khi ký**; không tự cắt signed XML trên RP.
9. Khi giảm claims, test chức năng hợp lệ và quyền còn chính xác; đừng remove attribute cần cho identity key/correlation.
10. Metadata `RequestedAttribute` có thể mô tả request nhưng không tự bảo đảm IdP chỉ phát những attributes đó; phải đo assertion verified thực.

### 8.3. Data minimization không phải xóa dữ liệu bừa bãi

Một field không còn sử dụng có thể vẫn thuộc retention hold hợp pháp hoặc nguồn HR; không tự purge dữ liệu không có quyền. Quy trình:

- Phân loại theo mục đích, trust agreement, retention schedule, legal holds và downstream dependencies.
- Dừng **thu thập/truyền mới** không cần thiết bằng IdP release policy/client scopes.
- Dừng mapping/storage/logging không cần thiết tại RP.
- Thực hiện lịch xóa/anonymize ở đúng systems theo policy và hợp đồng.
- Xác nhận downstream recipients/sub-processors và backups được xử lý theo nghĩa vụ.
- Test không có fail-open khi claim bị bỏ: app có thể deny/handle optional value thay vì cấp default admin.
- Lưu bằng chứng chỉ gồm schema/claim names, purpose/owner, count/byte sizes và approved diffs; không cần raw PII.

## 9. Trust Agreement và kiểm soát đối tác

Một kết nối SSO an toàn cần cả cấu hình kỹ thuật và văn bản/thỏa thuận vận hành. Các mục nên ghi:

1. Legal entity/contact, owner escalation (business, security, privacy, IdP technical).
2. Danh sách RP/client được phép, audience/entityID, tenant, ACS/redirect URIs, allowed origins/domains.
3. Protocol/profile/bindings: OIDC Authorization Code + PKCE, SAML2 signed assertion, CAS service ticket.
4. Key/metadata authority: URL/hosting, metadata signer trust, JWKS key source, certificate rollover schedule và emergency revocation.
5. Authentication assurance/step-up (MFA, `acr`, `amr`) nếu dựa vào đó cho sensitive operations.
6. Attribute schema, purposes, allowed data receivers, retention, onward disclosure, incident/breach process.
7. Account identity key/subject stability, account linking policy, JML/SCIM deprovision SLA.
8. Delegated authorization: ai được cấp nhóm, group→permission mapping, least privilege và SoD.
9. Session/logout/token lifetime và xử lý incident khi user bị disable.
10. Monitoring, evidence exchange, downtime/outage contact, test environment/key material.
11. Change management: trước khi đổi issuer, ACS, redirect URI, signing key, data release phải thông báo/approve.
12. Offboarding: gỡ keys/client registration, disable app assignment, revoke secrets, destroy data theo nghĩa vụ, kiểm access thật.

**Không dùng “đối tác đã ký hợp đồng” làm lý do tin mọi URL/KeyInfo/JWKS mà browser gợi ý**. Runtime phải verify exact issuer/audience/recipient/signature và authoritative local tenant permissions.

## 10. OIDC/OAuth2 partner configuration: checklist chuyên sâu

### 10.1. Các điểm phải so actual với approved baseline

| Mục | Baseline an toàn | Sai lệch cần ticket |
| --- | --- | --- |
| `issuer-uri` | Exact HTTPS issuer đã được phê duyệt | New hostname/issuer không có owner |
| OIDC discovery | OP metadata được tải/kiểm qua trusted HTTPS | Wrong JWKS/token endpoints, SSRF redirects |
| `client-id` | Client riêng đúng RP/tenant | Shared client across unrelated RPs |
| `client-secret` hoặc private key | Secret store/KMS, rotation, least privilege | Hardcoded file/Git, expired/unused owner |
| `redirect-uri` | Exact HTTPS registered URL | Wildcard, HTTP public, open redirect |
| `authorization-grant-type` | Authorization Code, PKCE theo policy | Legacy implicit/password grant không được duyệt |
| `scope` | Minimal `openid`, optional profile/email | `offline_access`/broad API scopes dư |
| `response_type`/mode | Phù hợp đã kiểm | Unexpected form_post/cookie failures |
| PKCE `code_challenge_method` | S256 nếu hỗ trợ/được yêu cầu | Missing verifier or downgrade |
| ID Token validators | iss, aud, exp, nonce, signature/kid | alg none, wrong OP key |
| API access token validators | issuer, audience, exp/nbf, scopes/resource policy | Dùng ID Token thay API access token |
| JWKS cache/key rotation | Trusted issuer-bound keys, overlap | Unknown kid accepted or stale trust |
| Logout/token revoke | Registered endpoints and supported policy | Long-lived token/session còn sau offboarding |
| HTTP client/egress | TLS/PKIX/host allowlist/timeouts | trustAll, SSRF, outbound to private IP |

RFC 9700 (OAuth 2.0 Security Best Current Practice, 2025) là nguồn review thiết kế: strict redirect, chống mix-up, PKCE, tránh những flows kém an toàn. Đánh giá tương thích từng OP/Spring Security release; không gán một cấu hình sample là mặc định chung.

### 10.2. Ví dụ Spring Boot 3.x OIDC cấu hình tối thiểu

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner-north:
            provider: north-op
            client-id: "portal-north"
            client-secret: "SET_FROM_SECRET_MANAGER"
            authorization-grant-type: authorization_code
            scope: openid,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          north-op:
            issuer-uri: "https://idp-north.example.org/issuer"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Lưu ý:** YAML là **fragment**, không phải app chạy được nếu thiếu IdP thật, secret mount, Spring Boot OAuth2 client dependencies và login/security config. Giá trị `SET_FROM_SECRET_MANAGER` là ký hiệu để nhắc chính sách; **không dùng chuỗi đó làm secret thực**. Với IdP dùng cross-site `response_mode=form_post`, `SameSite=Lax` có thể không gửi cookie cần cho callback, phải review cookie policy độc lập.

Một review diff điển hình:

```diff
  registration.partner-north.scope = [openid, email]
+ registration.partner-north.scope += offline_access
+ redirect_uris += https://temporary-debug.example.net/callback
```

Cả hai thay đổi mới đòi owner/purpose/security review. Không chấp nhận debug URL chưa kiểm soát vì nó có thể nhận authorization code. **Tắt/chặn client registration không còn owner**, không để “temporary” secrets/redirects vĩnh viễn.

### 10.3. API Resource Server không tự được bảo vệ chỉ bằng OAuth login

Một web app dùng `oauth2Login()` có local session, nhưng resource API dùng JWT Bearer token cần validation riêng. Spring Security Resource Server có thể kiểm issuer/expiry và audience theo cấu hình. Ví dụ Boot 3.5 (chỉ áp cho API dùng đúng issuer/audience):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp-north.example.org/issuer"
          audiences: "https://api.example.org/reports"
```

**Không dùng một `issuer-uri` duy nhất** nếu resource server tin nhiều issuers mà chưa có custom resolver/validators trust-specific. Với multi-tenant, phải ràng buộc issuer, audience, tenant, scope/resource và local policy; không chỉ tìm một JWT có chữ ký hợp lệ. Không suy ý `aud` giống OAuth client_id ở mọi API.

## 11. SAML2 partner configuration: metadata và khóa

### 11.1. Rà soát các trường giao thức

| Mục | Kiểm định kỳ | Vì sao |
| --- | --- | --- |
| Spring `registrationId` | Map tới đúng IdP và tenant | Không lẫn các đối tác |
| IdP `EntityID` / `Issuer` | Exact approved value | Ngăn SAML tenant confusion |
| SP `EntityID` | Expected `AudienceRestriction` | Ngăn assertion cho RP khác |
| ACS `/login/saml2/sso/{registrationId}` | Exact HTTPS public URL | `Destination`/Recipient đúng |
| `SingleSignOnService` | Allowed endpoint/binding | Không tự chuyển tới host lạ |
| `SingleLogoutService` | Key/binding và session flow | SLO không thiếu bảo vệ |
| IdP `KeyDescriptor use=signing` | Trusted public verification certs | Verify XML Signature đúng |
| SP signing credential | Private key ở SP, public cert IdP biết | AuthnRequest/LogoutRequest signing |
| SP decryption credential | Private key ở SP, public cert IdP biết | EncryptedAssertion |
| Metadata signature | Verification trust anchor nếu yêu cầu | Không nhận fake metadata |
| `validUntil` | Hard validity theo spec/consumer policy | Không dùng metadata expired |
| `cacheDuration` | Refresh scheduling hint | Không nhầm cache TTL với validity |
| NameID/attributes | Stable subject, minimal release | Privacy/identity mapping |
| Clock and replay | NotBefore/NotOnOrAfter, InResponseTo | Không chấp nhận assertion cũ |

**Điểm đặc biệt:** `cacheDuration` của SAML metadata là gợi ý khi nên refresh; `validUntil` là hạn hiệu lực metadata. Một caching repository có TTL không mặc nhiên enforce `validUntil` nếu ứng dụng tự build không kiểm. Kiểm đúng Spring Security/OpenSAML version và metadata resolver trust policy.

### 11.2. Cần kiểm ba khóa khác nhau

```text
IDP signing key:
    IdP private -> signs SAML Response/Assertion
    SP public  -> verifies signed node

SP signing key:
    SP private -> signs AuthnRequest/LogoutRequest
    IdP public -> verifies request

SP decryption key:
    IdP uses SP public certificate to encrypt Assertion
    SP uses matching private key to decrypt
```

Và thêm **metadata-signing key** (nếu metadata có chữ ký XML), **TLS certificate** cho HTTPS. Chúng không tự đồng nhất. Một IdP dùng certificate ký SAML khác TLS cert là bình thường. Cần inventory fingerprint public SHA-256, usage, owner, validity, rotation ticket; private key chỉ trong KMS/keystore/secret store.

### 11.3. Key rollover chuẩn

```text
T0   IdP signs with N1; metadata lists N1.
T1   IdP publishes signed/trusted metadata with N1 + N2.
T2   SP verifies & activates trusted [N1,N2].
T3   IdP switches signer to N2.
T4   SP accepts N2, may accept in-flight N1 in approved overlap.
T5   IdP metadata retires N1; SP refreshes to [N2].
T6   Negative test: N1 signature REJECTED on every pod.
```

Nếu N1 bị compromise, không chờ lịch overlap để thuận tiện; xử lý emergency revoke theo incident. Metadata signed/trusted mới có key N2 chưa chắc **được phép** tự activate nếu change approval policy yêu cầu. **Không lấy key từ raw SAML `KeyInfo` của Response chưa verify rồi cho vào trusted set**.

### 11.4. Spring Security SAML2 metadata

Spring Security liên kết `RelyingPartyRegistration` với AP/IdP metadata, ACS, SP EntityID và certificates. Với các release hỗ trợ, `http.saml2Metadata(...)` publish SP metadata. Một lần gọi `RelyingPartyRegistrations.fromMetadataLocation(...)` để build rồi lưu `InMemoryRelyingPartyRegistrationRepository` **không có nghĩa IdP metadata được tự làm mới mãi mãi**. Nếu cần refresh, dùng repository/resolver/caching strategy được hỗ trợ, kiểm expiry/signature/TLS, atomic publication và multi-pod consistency.

Một review phải thử **signed SAMLResponse** hợp lệ với key mới và chứng minh old key bị reject sau retirement, đồng thời kiểm issuer, audience, destination, recipient, time, InResponseTo và replay. Metadata HTTP 200, cert chưa hết hạn hoặc browser login 302 không đủ.

## 12. CAS, Kerberos và các đường identity ngoài OAuth/SAML

Nếu kết nối CAS/LDAP/AD/SPNEGO cũng có trong federation estate, review riêng:

- **CAS:** registered `service` public HTTPS URI, CAS ticket-validation endpoint/TLS, allowed proxy tickets (nếu có), CAS attribute release, service owners, CAS logout behavior. Ticket `ST` là one-use bearer artifact, không log.
- **Kerberos/SPNEGO:** expected `HTTP/public-host@REALM` SPN, service keytab/KVNO/etype, ownership, delegation scope, key rotation, trusted reverse proxy/pre-auth. HTTP 401 Negotiate challenge có thể bình thường, không phải quyền còn hợp lệ.
- **LDAP/AD:** service bind accounts, read permissions, TLS StartTLS/LDAPS certificate, group nesting, lock/disable flags, stale user cache, account control, privileged directory groups.
- **SCIM:** client credentials/scopes, target base URL/tenant binding, mapping `active`, group assignment/revocation, retry/dead letter, provisioning freshness.
- **Vendor portal admin:** tài khoản quản trị IdP dành cho tích hợp, API token quản lý metadata/client registrations, emergency owner và MFA; đây thường là quyền rất cao nhưng không xuất hiện trong app business users.

Đừng ép các loại service credentials vào danh sách “user SSO”; chúng cần phân loại riêng và owner/risk-based expiry.

## 13. Chuẩn hóa mẫu bảng rà soát và bằng chứng

### 13.1. Ví dụ dòng quyền đã che danh tính

| reviewId | partner | subjectRef | tenant | effectiveEntitlement | lastReviewed | decision | owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RV-101 | north-oidc | usr-17 (pseudonym) | north | APP_REPORT_READ | 2026-05-01 | REVIEW_DUE | Reports owner |
| RV-102 | north-oidc | usr-18 (pseudonym) | north | APP_ADMIN | 2026-10-20 | KEEP_APPROVED | Security owner |
| RV-103 | north-oidc | usr-19 (pseudonym) | north | APP_ADMIN | 2026-11-01 | REVOKE_NOW | IAM owner |
| RV-104 | south-saml | usr-33 (pseudonym) | south | APP_ADMIN | 2026-07-01 | REVIEW_DUE | South manager |
| RV-105 | south-saml | usr-34 (pseudonym) | south | APP_REPORT_READ | 2026-10-01 | REVOKE_NOW | South owner |

Dữ liệu giả lập, không phải người thật. `REVIEW_DUE` không đồng nghĩa phải revoke ngay nếu user còn active và policy cho phép temporary restricted access; cần reviewer quyết định theo risk. `REVOKE_NOW` đối với leaver/unauthorized grant là emergency action với thực thi và xác minh riêng.

### 13.2. Ví dụ dòng claim release register

```json
{
  "partnerId": "north-oidc",
  "source": "https://idp-north.example.org/issuer",
  "recipient": "portal.example.org",
  "field": "email",
  "purpose": "user notification after login",
  "classification": "personal-data",
  "required": false,
  "approved": true,
  "storage": "short-lived-profile-cache",
  "retentionPolicyId": "RET-PORTAL-PROFILE",
  "approvedByRole": "privacy-owner",
  "observedFrom": "schema-only-staging-assertion"
}
```

Không gắn giá trị email thật vào audit config. Khi một field mới như `phone_number` xuất hiện dù không nằm trong register, đánh dấu `DATA_DRIFT`, dừng log/lưu nếu có thể, gửi tới privacy/app owner, kiểm downstream recipients và cập nhật IdP release policy.

### 13.3. Ví dụ approved vs actual config diff

```diff
partner: north-oidc
  issuer: https://idp-north.example.org/issuer
  redirect_uris:
    - https://portal.example.org/login/oauth2/code/north-oidc
+   - https://diagnostic.example.net/callback
  scopes:
    - openid
    - email
+   - offline_access

partner: south-saml
  idpEntityId: https://idp-south.example.org/saml
  trustedSigningCerts:
    - S1
+   - S2
  spAcs: https://portal.example.org/login/saml2/sso/south-saml
```

**Mọi dòng thêm không tự xấu:** S2 có thể là rollover có phê duyệt; `offline_access` có thể cần cho API use case thật. Nhưng review phải chứng minh owner/purpose, trust, expiry và test. Dòng callback diagnostic là **rủi ro cao** vì có thể nhận OAuth code; phải xác minh endpoint/custodian và loại bỏ nếu không được duyệt.

## 14. Thiết kế quy trình review 8 bước

### Bước 1 — Scope và snapshot

- Chọn cutoff UTC/date; khóa danh sách partners/tenants/apps/IdPs theo inventory.
- Lấy current config từ **nguồn đang chạy** (OP client registry, Spring configs effective, SAML metadata resolved, IdP group mappings, SCIM target, DB grants).
- Lưu dấu thời gian, config revision/generation, SHA-256 của **public certificate**, reviewer role, hệ thống phát evidence.
- Không export private keys, client secrets, raw tokens, SAMLResponse hay người dùng không liên quan; giảm dữ liệu từ đầu.
- Kiểm completeness: đối tác không có owner được đánh dấu **NEEDS_OWNER**, không bỏ khỏi scope.

### Bước 2 — Thu thập desired baseline

- Approved client registration IDs, exact HTTPS redirect URIs/ACS/SP EntityIDs, issuer/trust anchors.
- Approved data fields/scopes/purpose/recipient/retention.
- Approved entitlement policies, service accounts, high-risk exceptions, SoD matrix.
- Reviewed JML source status, contractor end date, group owners, token/session TTL policy.
- Mọi thay đổi baseline cần ticket/version/approver; không để live config tự trở thành baseline.

### Bước 3 — Reconcile và tính risk

- So current vs baseline; flag unknown issuer, callback, new cert, endpoint, unexpected scope/attribute, old key still trusted.
- So effective access vs approved grants; flag leaver, privileged stale, orphan, unused/broad API client.
- Phân loại: **P0 incident** (key compromise, leaked secrets, unapproved privileged grant), **P1 high** (unexpected callback/issuer, missing metadata signature theo contract), **P2 normal** (review overdue, excess optional claim), theo risk scale của tổ chức.
- Không gộp mọi anomaly thành “P0” khiến vận hành mất phân biệt ưu tiên.

### Bước 4 — Reviewer quyết định

- Business owner xác nhận access need và tenant/resource.
- Security owner xác nhận trust key/algorithm/SoD/risk/expiry.
- Privacy owner xác nhận data purpose/scope/retention và disclosure.
- Partner IdP owner xác nhận issuer/metadata/key rotation, SSO/SLO/config change.
- Quyền privileged của reviewer cần independent approval; không chấp nhận tự duyệt.

### Bước 5 — Đề xuất change và impact

- Nếu thu hồi quyền: identify authoritative source + token/session ramifications.
- Nếu giảm claims: IdP release policy + RP mapping/null handling/downstream impact.
- Nếu đổi callback/cert: test plan, staged rollover, rollback conditions không reintroduce compromised key.
- Nếu tăng quyền: privilege justification, duration, separation of duties and action-time authorization.
- Có canary/staging signed fixtures và acceptance criteria; không ghi “cứ redeploy” như một phép kiểm.

### Bước 6 — Triển khai có kiểm soát

- Thực hiện GitOps/config store/OP/IdP portal/SCIM updates bằng tài khoản có quyền, theo approved change ticket.
- Secrets được rotate trong KMS/secret manager, không dán vào dashboard/tickets.
- Deploy theo tenant/registration, có monitoring; không nhầm reload config với actual Spring repository refresh trên từng pod.
- Emergency compromise: ưu tiên isolate/revoke, không đợi lịch deploy bình thường.

### Bước 7 — Readback, regression và negative validation

- Đọc actual effective grants/certs/claims sau thay đổi, so snapshot version/fingerprint.
- Test signed SAML fixtures/key rollover, OIDC state/PKCE/JWT validators và API audience/tenant.
- Test user **không được cấp** vẫn bị 403/401; test user hợp lệ vẫn 200 tài nguyên đúng.
- Test logout/token/session invalidation nếu quyền bị thu hồi, kể cả multi-pod/Redis.
- Kiểm data fields thực tế ID Token/UserInfo/SAML/SCIM không còn phát dư, không bị log/backup sau thời hạn policy.
- Mỗi lỗi có owner/ticket/fix deadline. **Không đóng review khi readback chưa chứng minh**.

### Bước 8 — Evidence & closure

- Lưu review scope, inputs/config fingerprints, date, reviewer decisions, implementer, verification, exceptions (expiry, risk owner), audit IDs.
- Tạo báo cáo số liệu tổng hợp: partners reviewed, grants reviewed, overdue, revoked, data drifts, key drifts, exception aging.
- Ký xác nhận độc lập hoặc workflow approvals theo policy.
- Báo remaining open issues rõ ràng thay vì ép thành 100% pass.
- Đặt nextReviewAt và event-driven triggers; kiểm lịch automation/alerts có owner.
- Lưu/truy cập evidence theo retention và privacy policy, tuyệt đối không lưu bearer artifacts chỉ để chứng minh login.

## 15. Spring Security: review policy phải đi tới runtime enforcement

### 15.1. Authentication không cấp quyền resource

Cấu hình đơn giản (fragment trong Spring Boot 3.x/Security 6.x):

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationWebSecurity {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Cảnh báo quan trọng:** `authenticated()` không kiểm tenant/permission. Khi dùng cả OIDC + SAML trong cùng app phải có `ClientRegistrationRepository` và `RelyingPartyRegistrationRepository` thật, login page/entry points và CSRF/cookie policy phù hợp. Code trên không phải app độc lập. Không cấp admin vì có authority `ROLE_USER` hoặc `groups` raw chưa được allowlist.

### 15.2. Method security kiểm quyền ở thời điểm thực thi

Mẫu minh họa tách role/tenant policy khỏi SSO login:

```java
package com.example.federation;

import org.springframework.security.core.Authentication;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final PartnerAccessPolicy access;

    public ReportService(PartnerAccessPolicy access) {
        this.access = access;
    }

    @PreAuthorize("@partnerAccessPolicy.mayRead(authentication, #tenantId)")
    public String summary(String tenantId) {
        return "Aggregate reports for " + tenantId;
    }
}

@Service("partnerAccessPolicy")
class PartnerAccessPolicy {

    boolean mayRead(Authentication authentication, String tenantId) {
        // Example only; replace with real authoritative
        // issuer-scoped account and tenant membership lookup.
        return authentication != null
            && authentication.isAuthenticated()
            && tenantId != null
            && !tenantId.isBlank()
            && false; // Fail closed until real policy is connected.
    }
}
```

**Chủ ý fail closed:** `return ... && false` làm mọi request bị deny; mục tiêu là tránh mẫu “dummy policy trả true” bị sao chép sang production. Khi triển khai thật, dùng authenticated issuer+stable subject→internal account mapping, kiểm account status/tenant ACL/grants from authoritative store **mỗi lần cần** hoặc cache có invalidation/version phù hợp. `@PreAuthorize` cần `@EnableMethodSecurity` và bean Spring managed (không tự gọi method trực tiếp trên object mới không qua proxy). Không mặc định dùng `authentication.getName()` nếu đó chỉ là email có thể đổi/trùng.

**Điểm QA:** Sau khi business owner thu hồi quyền `reports.read`, dù OIDC ID Token/HttpSession vẫn mang group cũ, gọi `/reports/tenant-north` phải trả deny theo effective resource policy/credential invalidation strategy đã thiết kế. Một spreadsheet báo “REVOKED” nhưng endpoint vẫn 200 là **QA FAIL**.

### 15.3. Gắn source vào role mapping

Khi convert OIDC/SAML claims thành Spring authorities, map theo bảng allowlist:

```text
issuerId        providerValue                appAuthority       tenant
north-oidc      group:report-reader-north    APP_REPORT_READ    north
south-saml      urn:south:group:finance-r     APP_REPORT_READ    south

UNMAPPED group / unknown issuer / wrong tenant -> NO PRIVILEGE
```

Không chuyển trực tiếp một claim `groups=["admin"]` từ mọi IdP thành `ROLE_ADMIN`. Quyền API scopes cũng phải gắn với **audience/resource**; `SCOPE_reports.read` không tự cho phép truy cập dữ liệu tenant khác.

## 16. Java 17 độc lập: bộ phân loại drift/review định kỳ

Chương trình sau dùng **JDK 17 thuần**, không Spring, không database, không secrets. Nó lấy **fixture giả lập đã xác minh**, kiểm partner metadata/trust/config, claim allowlist và access grants theo một ngày cố định. Kết quả chỉ là **candidate findings để con người/automation có thẩm quyền xử lý**, không tự revoke hoặc tạo grant. Nó không verify SAML/XML signatures, ID Token/JWT, TLS, HR source hay SCIM API thật.

### 16.1. File `FederationReviewDemo.java`

```java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class FederationReviewDemo {

    private static final LocalDate AS_OF =
        LocalDate.parse("2026-11-07");

    // All intervals are EXAMPLE company policy,
    // not a Spring default or statutory requirement.
    private static final int PARTNER_REVIEW_DAYS = 90;
    private static final int PRIVILEGED_REVIEW_DAYS = 90;
    private static final int STANDARD_REVIEW_DAYS = 180;
    private static final int CERT_ALERT_DAYS = 90;

    record Partner(
        String id,
        LocalDate lastReviewed,
        LocalDate keyExpires,
        boolean metadataTrusted,
        boolean callbackHttps,
        Set<String> approvedClaims,
        Set<String> observedClaims
    ) { }

    record Grant(
        String partnerId,
        String subjectRef,
        String entitlement,
        boolean privileged,
        boolean sourceActive,
        boolean grantActive,
        boolean approved,
        LocalDate lastReviewed
    ) { }

    static String partnerReview(Partner p) {
        Set<String> flags = new TreeSet<>();

        if (!p.metadataTrusted()) {
            flags.add("METADATA_UNTRUSTED");
        }
        if (!p.callbackHttps()) {
            flags.add("INSECURE_CALLBACK");
        }
        if (!p.approvedClaims().containsAll(p.observedClaims())) {
            flags.add("EXCESS_CLAIMS");
        }
        if (p.lastReviewed() == null ||
            !p.lastReviewed().plusDays(PARTNER_REVIEW_DAYS)
                .isAfter(AS_OF)) {
            flags.add("REVIEW_DUE");
        }
        if (p.keyExpires() == null ||
            !p.keyExpires().isAfter(AS_OF)) {
            flags.add("KEY_EXPIRED");
        }
        else if (ChronoUnit.DAYS.between(
                AS_OF, p.keyExpires()) <= CERT_ALERT_DAYS) {
            flags.add("KEY_EXPIRING");
        }

        return flags.isEmpty()
            ? "CURRENT"
            : String.join(",", flags);
    }

    static String grantReview(Grant g) {
        if (!g.grantActive()) return "NO_ACTIVE_GRANT";

        // Source status and approval take precedence over due dates.
        if (!g.sourceActive()) {
            return "REVOKE_NOW_SOURCE_DISABLED";
        }
        if (!g.approved()) {
            return "REVOKE_NOW_UNAPPROVED";
        }

        long days = g.privileged()
            ? PRIVILEGED_REVIEW_DAYS
            : STANDARD_REVIEW_DAYS;

        if (g.lastReviewed() == null ||
            !g.lastReviewed().plusDays(days).isAfter(AS_OF)) {
            return "REVIEW_DUE";
        }

        return "CURRENT";
    }

    public static void main(String[] args) {
        Partner north = new Partner(
            "north-oidc",
            LocalDate.parse("2026-10-01"),
            LocalDate.parse("2027-01-15"),
            true,
            true,
            Set.of("sub", "name", "email"),
            Set.of("sub", "name", "email", "phone"));

        Partner south = new Partner(
            "south-saml",
            LocalDate.parse("2026-06-01"),
            LocalDate.parse("2027-05-01"),
            false,
            false,
            Set.of("NameID", "groups"),
            Set.of("NameID", "groups"));

        List<Grant> grants = List.of(
            new Grant("north-oidc", "usr-17",
                "APP_REPORT_READ", false, true, true, true,
                LocalDate.parse("2026-05-01")),
            new Grant("north-oidc", "usr-18",
                "APP_ADMIN", true, true, true, true,
                LocalDate.parse("2026-10-20")),
            new Grant("north-oidc", "usr-19",
                "APP_ADMIN", true, false, true, true,
                LocalDate.parse("2026-11-01")),
            new Grant("south-saml", "usr-33",
                "APP_ADMIN", true, true, true, true,
                LocalDate.parse("2026-07-01")),
            new Grant("south-saml", "usr-34",
                "APP_REPORT_READ", false, true, true, false,
                LocalDate.parse("2026-10-01")));

        System.out.println("north=" + partnerReview(north));
        System.out.println("south=" + partnerReview(south));

        long findings = 0;
        for (Grant g : grants) {
            String result = grantReview(g);
            System.out.println(
                "grant:" + g.subjectRef() + "=" + result);

            if (!"CURRENT".equals(result)
                    && !"NO_ACTIVE_GRANT".equals(result)) {
                findings++;
            }
        }
        System.out.println("openAccessItems=" + findings);
    }
}
```

Lệnh chạy:

```bash
javac --release 17 FederationReviewDemo.java
java FederationReviewDemo
```

Stdout xác định:

```text
north=EXCESS_CLAIMS,KEY_EXPIRING
south=INSECURE_CALLBACK,METADATA_UNTRUSTED,REVIEW_DUE
grant:usr-17=REVIEW_DUE
grant:usr-18=CURRENT
grant:usr-19=REVOKE_NOW_SOURCE_DISABLED
grant:usr-33=REVIEW_DUE
grant:usr-34=REVOKE_NOW_UNAPPROVED
openAccessItems=4
```

### 16.2. Tại sao kết quả như vậy?

- `north` có observed `phone` không thuộc approved claim set → `EXCESS_CLAIMS`; key expiry 2027-01-15 còn trong 90 ngày từ AS_OF → `KEY_EXPIRING`. North last review 2026-10-01 chưa quá 90 ngày, HTTPS/certificate trust flags tốt theo giả lập.
- `south` metadataTrusted=false, callbackHttps=false → `METADATA_UNTRUSTED` và `INSECURE_CALLBACK`; last review 2026-06-01 đã quá 90 ngày → `REVIEW_DUE`. Những flags này là test fixtures chứ không có đối tác thực nào bị phát hiện.
- `usr-17` standard review từ 2026-05-01 → 180 ngày đã qua, review due.
- `usr-18` privileged reviewed 2026-10-20 → còn hạn.
- `usr-19` source account disabled nhưng app grant vẫn active → `REVOKE_NOW_SOURCE_DISABLED`, ưu tiên hơn review date.
- `usr-33` privileged review 2026-07-01 → quá 90 ngày.
- `usr-34` source active nhưng grant chưa có approval → `REVOKE_NOW_UNAPPROVED`, không đợi kỳ review.
- `openAccessItems=4` đếm 2 review overdue + 2 revoke candidates. Nó **không** đếm partner issues vào access findings.

### 16.3. Những điều demo không chứng minh

- `metadataTrusted=true` chỉ là **fixture boolean**; production cần validate metadata signature/TLS trust và exact issuer/registration, không nhận boolean từ browser.
- `callbackHttps=true` không kiểm hostname/redirect URI allowlist; cần đối chiếu exact URI/cert.
- `observedClaims` chỉ là tên fields, không chứng minh nội dung/tính hợp lệ/chữ ký. Production lấy schema metadata có kiểm soát và pseudonymized observations sau validation.
- `sourceActive` phải từ HR/partner directory **đáng tin**, không từ raw user claim.
- `approved=true` phải gắn grant ID, approver, timestamp, expiry và SoD proof; không phải request boolean.
- Không kết nối IdP, Redis, SCIM, Spring Session, token revocation, SAML/ID token verification hay database. Không dùng output `CURRENT` làm API authorization decision.
- `LocalDate.plusDays` cho ngưỡng “due on or before AS_OF”; production có timezone/UTC cutoffs, holiday policies và fixed-time scheduling rõ ràng.
- Đây là report classifier, **không tự thu hồi quyền**. Thực thi revoke phải qua authoritative system và readback như mục 14.
- Java 17 code dùng `record`, `Set.of`, `TreeSet` và `ChronoUnit`; không cần library ngoài JDK.

## 17. Dashboard và cơ chế cảnh báo review

### 17.1. Chỉ số vận hành đề xuất

```text
federation_partner_review_due_total{riskTier}
federation_partner_owner_missing_total{}
federation_metadata_signature_failures_total{registration}
federation_metadata_validity_seconds{registration}
federation_cert_expiry_days{registration,purpose}
federation_key_rotation_lag_seconds{registration}
federation_unapproved_redirect_uri_total{partner}
federation_excess_claims_total{partner}
federation_claim_release_change_total{partner}
federation_access_review_due_total{riskTier,tenant}
federation_unapproved_privileged_grants_total{tenant}
federation_orphan_accounts_total{partner}
federation_jml_revoke_latency_seconds{source}
federation_session_revoke_failures_total{app}
federation_config_diff_total{severity}
federation_review_closure_percent{reviewCycle}
```

Tên metrics là **đề xuất**, không phải Spring/Micrometer built-in. Tránh labels gồm email, `sub`, NameID, access token, group values hoặc arbitrary issuer URLs (high cardinality/PII). `registration` và `tenant` phải là tập known bounded IDs; các giá trị tự nhập không được biến thành label.

### 17.2. Phân biệt count và effectiveness

**Chỉ số đẹp nhưng vô nghĩa:** 100% rows có reviewer comment “approved”. Có thể các quyền đã revoke chưa bị gỡ, expired cert chưa rotate hoặc claims vẫn phát dư.

**Chỉ số có giá trị:** P95 time-to-revoke từ authoritative offboarding đến effective deny tại API; phần trăm privileged grants có independent approval; số sessions sống sau revoke trong test; phần trăm partner metadata resolved đúng trust generation trên **mọi pods**; số unapproved claims **observed after validation** và đã gỡ tại IdP; số key cũ còn được chấp nhận sau retirement.

Dashboard không thay evidence/ticket hay security test. Với high-severity events, dùng alert ngay thay vì đợi dashboard review theo quý.

## 18. Ma trận kiểm thử trước khi chốt kỳ review

| Kiểm thử | Dữ liệu/động tác | Kết quả đúng |
| --- | --- | --- |
| **Privileged grant overdue** | Last reviewed 91 ngày, policy 90 | Review due |
| **Standard grant at boundary** | Last reviewed đúng 180 ngày | Review due theo policy inclusive |
| **No review history** | Null lastReviewedAt | Flag review due |
| **Leaver still has grant** | HR disabled, app grant active | Emergency revoke candidate |
| **Partner contractor expired** | Contract ended, local account active | Revoke/escalate; không chờ quý |
| **Orphan role** | Group missing owner/approval | Needs owner, risk decision |
| **SoD conflict** | Approver = privileged grant owner | Independent approval required |
| **Shared/break-glass account** | No owner or no expiry | Escalate, time-bound exception |
| **Nested AD group** | Indirect APP_ADMIN grant | Effective access includes it |
| **Direct DB grant** | IdP group removed, local role still exists | Flag stale privilege |
| **SCIM active=false** | User disabled via SCIM | Target inactive, grants/session policy effective |
| **SCIM event lost** | Queue outage, target unchanged | Alert/retry/reconciliation |
| **SCIM duplicate/out-of-order** | Repeated PATCH or old change arrives later | Idempotent/version policy |
| **Existing JWT after revoke** | JWT still within exp | API action-time deny or bounded risk window |
| **Spring HttpSession after revoke** | Session Redis still exists | Session invalidate/authoritative access deny |
| **Unknown issuer same email** | IdP B email matches IdP A | No auto-link/tenant grant |
| **Unapproved OIDC scope** | `offline_access` newly granted | Flag data/access drift |
| **Unapproved claim** | `phone` appears in UserInfo | DATA_DRIFT, stop unnecessary release |
| **Remove optional claim** | IdP stops `name` | No null dereference / privilege fallback |
| **Group claim explosion** | Thousands of groups from IdP | Enforce size/allowlist, no role escalation |
| **OIDC wrong `iss`** | Valid JWT from different issuer | Reject |
| **OIDC wrong `aud`** | API token for other service | Reject |
| **OIDC unknown `kid`** | Untrusted JWK key | Reject, trusted refresh only |
| **OIDC weak/none algorithm** | `alg=none` or unapproved | Reject |
| **OIDC redirect URI added** | New external callback | Change approval, quarantine if unauthorized |
| **OIDC authorization code replay** | Reuse code in staging | Reject; no state/PKCE bypass |
| **SAML issuer mismatch** | Signed Response from wrong registration | Reject |
| **SAML audience mismatch** | Assertion to other SP entityID | Reject |
| **SAML recipient/destination wrong** | ACS not registered | Reject |
| **SAML unknown signing cert** | Key not trusted | Reject |
| **SAML metadata signature invalid** | Tampered candidate metadata | Reject candidate |
| **SAML metadata expired** | At/past validUntil | No trust based on expired metadata |
| **SAML N1→N1+N2→N2** | Valid signed fixtures in stages | New key PASS after staged trust; old FAIL after retire |
| **Cross-tenant SAML** | Response from tenant A to B | Reject, no group/identity merge |
| **SP decryption key rotate** | IdP encrypts to new SP cert | All pods decrypt, old retired when safe |
| **CAS wrong service** | ST for other service URL | CAS validation reject |
| **CAS ST reuse** | Ticket validated twice | Second reject |
| **SPNEGO unknown SPN** | Ticket for wrong host | GSS reject |
| **Partner cert expired** | Cert near/past expiry | Alert, safe rollover/deny per policy |
| **Unapproved metadata redirect** | Fetch URL redirects to private IP | SSRF/egress reject |
| **Partner absent owner** | Contact departed organization | Escalate/disable risky integration |
| **App authorization negative** | Revoked user access resource | 403/401 (policy), never 200 |
| **App authorization positive** | Approved user reads allowed tenant | 200 correct resource |
| **Audit redaction** | Export review evidence | No bearer code, SAMLResponse, secrets, raw PII |
| **Multi-pod drift** | One pod holds old signing set | Fail rollout/converge, quarantine old trust |
| **Configuration revert** | Rollback to old metadata/client | Must not reintroduce revoked key/callback |
| **Review approval evidence** | Reviewer marks keep/revoke | Ticket owner/approval/readback/closure present |

**Tách fixture:** Muốn test SAML wrong audience nhưng signature hợp lệ, ký lại SAML fixture **sau khi** tạo wrong audience bằng IdP test. Nếu sửa XML sau khi ký thì chỉ test signature invalid, không test audience validator. Không dùng raw production assertions/tokens trong automated tests.

## 19. Tình huống thực tế và cách xử lý

### 19.1. Quyền admin còn sau khi nhân viên nghỉ

**Triệu chứng:** HR đã ghi leaver, IdP account disabled, nhưng user có active session/JWT và local APP_ADMIN grant.

**Runbook:**

1. Xác nhận authoritative HR status/termination time và grant ownership (không dựa tin đồn).
2. Kích hoạt emergency revoke theo SLA: xóa local grants, disable service principals gắn cá nhân (nếu có), revoke refresh tokens/sessions theo các cơ chế hỗ trợ.
3. Kiểm Spring Session Redis/JDBC, Resource Server token TTL/authoritative permission check và every-tenant resource.
4. Test negative với staging account đã disabled hoặc security-approved controlled test, tránh chiếm đoạt tài khoản thật.
5. Điều tra vì sao SCIM/group sync không gỡ grant, thiết kế reconciliation và alert.
6. Đóng incident khi **actual access DENIED**, không chỉ “IdP disabled”.

### 19.2. OP tự thêm `offline_access` cho client

1. So client registration `scopes` actual với approved register; có owner/purpose cụ thể cho refresh token không?
2. Kiểm OP consent/token issuance policy, client auth method và secret storage.
3. Nếu không cần, remove scope ở client/OP và xử lý refresh tokens đã cấp theo policy.
4. Kiểm ID Token/UserInfo và API access tokens không phát thêm PII/scopes ngoài mục đích.
5. Regression test web login & API, không bật implicit/password grant.
6. Lưu diff, approval và outcome; không log refresh token.

### 19.3. SAML metadata xuất hiện signing key S2 lạ

1. Xác định đây là planned rotation hay unexpected; kiểm source metadata HTTPS, metadata signature trust anchor, expected entityID và hard validity.
2. Không tự add S2 vào mọi registrations/tenants. Đề nghị partner owner xác nhận certificate fingerprint public qua kênh đã phê duyệt.
3. Nếu hợp lệ, stage N1+S2 overlap (đúng cặp key theo partner); test signed fixture key mới và issuer/audience/recipient.
4. Sau cutover, retire old key và test old-key signature rejected trên mọi pods.
5. Nếu nghi compromise, quarantine/revoke/incident; không tiếp tục tin old key vì “còn validity”.
6. Đảm bảo SAML SP decryption/signing key của mình không bị nhầm với IdP signing cert.

### 19.4. App nhận quá nhiều group/PII từ IdP

1. Ghi count và schema fields (không raw values/NameID) sau signed verification.
2. So mục đích với release register; nhóm không liên quan app và custom claims không có owner phải flag.
3. Yêu cầu IdP giảm release/filtered group claims; xem backend entitlement lookup nếu nhiều nhóm.
4. RP bỏ mapping/storage không cần; session/cache/log retention theo policy.
5. Test user legitimate vẫn login và quyền đúng; unknown group không tự thành admin.
6. Cập nhật trust agreement/contract/data map nếu thay đổi purpose hoặc recipient hợp lệ.

### 19.5. Đối tác không trả lời yêu cầu review

1. Chứng minh contact/owner/last attestation; tạo ticket `NEEDS_OWNER` với hạn xử lý.
2. Kiểm key expiry, metadata validity, actual auth volume và data sensitivity; phân loại risk.
3. Với high-risk/expired contract, áp policy tạm hạn chế hoặc suspend theo phê duyệt khẩn cấp; không tự xóa mọi user account nếu có nghĩa vụ kinh doanh/retention.
4. Escalate Security/Legal/Business owner; không đánh dấu approved by silence.
5. Test sau khi hạn chế: đúng tenant và hợp đồng, không làm hỏng đối tác khác.
6. Khi partner xác nhận lại, cần review đầy đủ config/claims/grants trước khi khôi phục.

### 19.6. Spring Security upgrade làm đổi authority mapping

1. Chụp version Spring/Boot/OpenSAML, các converter `GrantedAuthoritiesMapper` và custom policy.
2. Dùng signed OIDC/SAML staging assertions, kiểm issuer-scoped claim→application authority mapping.
3. So access decisions trước/sau với golden cases per tenant; chỉ approved grants được allow.
4. Negative tests: unknown group, wrong issuer, email trùng, disabled user, stale session, admin SoD conflict.
5. Nếu group names chệch, **không** map toàn bộ values thành `ROLE_ADMIN` để làm tests xanh.
6. Rollback version chỉ khi không tái đưa vulnerability/key đã thu hồi, có security owner review.

## 20. Cách làm audit mà không lộ dữ liệu

### 20.1. Evidence đủ dùng

```text
reviewCycleId
snapshotAtUtc
partnerId/registrationId (approved local ID)
ownerRole/reviewerRole/approverRole
configVersion/hash (not raw private key)
issuerEntityId (approved canonical string)
publicSigningCertFingerprintSha256
keyPurpose/validity
redirectUriOrAcsCategory (or exact approved config under ACL)
approvedScope/attributeName schema only
numberOfEffectiveGrantsByRisk
pseudonymousGrantRef
decision + reason category
changeTicketId / implementation timestamp
verification result (negative/positive tests)
exceptionExpiresAt / escalationOwner
nextReviewAt
```

Không thu thập trong review export:

```text
Raw SAMLResponse / RelayState / NameID values
OIDC authorization code / ID token / access/refresh tokens
CAS service ticket / TGT / TGC / PGT
Kerberos Negotiate header / keytab
JSESSIONID / SESSION cookies / CSRF token
SP or IdP private signing/decryption keys
Client secrets / SCIM bearer tokens
User passwords, full LDAP dump, unrelated HR details
```

Public certificate fingerprint SHA-256 có thể lưu và so bản cũ/mới, nhưng certificate/key details phải dùng đúng ownership context; không biến fingerprint thành đại diện cho sự phê duyệt. Dữ liệu về reviewer và pseudonymous subject cũng có thể là personal data; áp ACL/retention cho chính evidence store.

### 20.2. Bằng chứng không phải screenshot duy nhất

Một screenshot IdP admin console nói "role removed" **không chứng minh** runtime Spring Resource Server đã deny. Một YAML diff nói "scope removed" **không chứng minh** OP đã ngừng cấp refresh token hoặc RP đã xóa stored token. Gắn:

- **Change evidence**: ticket/config diff signed by automation/owner.
- **Readback evidence**: actual source, config generation, session/token state.
- **Runtime evidence**: success/fail login and negative business resource tests.
- **Privacy evidence**: claim schemas/counters, logging/retention check.
- **Closure evidence**: independent verifier, residual risk/exception expiry.

Không bắt buộc lưu raw assertion để chứng minh metadata signing; có thể dùng test fixtures độc lập và signed validation outcome với certificate fingerprint.

## 21. Bài tập kiểm tra và đáp án

**Câu 1.** Một user bị disable ở IdP nhưng còn JWT hợp lệ 30 phút và local DB role. Review có thể chờ quý sau không?

**Đáp án:** Không. JML leaver là event-driven; cần xử lý authoritative revoke/local role, session/refresh token và JWT risk window, test deny theo SLA.

**Câu 2.** Một đối tác đăng nhập SAML thành công. Có chứng minh SP đủ an toàn không?

**Đáp án:** Chưa. Cần signature/issuer/audience/recipient/time, key trust đúng, tenant permissions, dữ liệu phát hành tối thiểu và governance.

**Câu 3.** OIDC `email_verified=true` có cho phép tự link user từ issuer A với cùng email issuer B?

**Đáp án:** Không. Identity key nên issuer+subject; cross-issuer account linking cần kiểm chứng và phê duyệt riêng.

**Câu 4.** `scope=openid email profile offline_access` có luôn phù hợp cho một web chỉ cần login và tên hiển thị không?

**Đáp án:** Không. Chỉ xin scopes/claims cần cho purpose; `offline_access` tạo thêm lifecycle/risk nếu cấp refresh tokens.

**Câu 5.** `SAML metadata cacheDuration` đã qua nhưng `validUntil` còn ngày mai. Có bắt buộc khóa ngay mọi login?

**Đáp án:** Không tự động. `cacheDuration` là thời điểm refresh; hard validity `validUntil` khác. Last-known-good fallback chỉ trong policy/trust window đã duyệt.

**Câu 6.** IdP đưa SAML signing cert mới vào metadata, có thể tự tin chỉ vì XML chứa cert đó?

**Đáp án:** Không. Metadata must be trusted/verified theo trust anchor và approval policy, key usage/issuer đúng; không tự học key từ raw Response.

**Câu 7.** Xóa group của user tại directory đủ để revoke mọi Spring session chứ?

**Đáp án:** Không mặc nhiên. Cached GrantedAuthorities/HttpSession/JWT đã cấp có thể còn; cần session invalidation và action-time authorization/caching plan.

**Câu 8.** App giữ nhiều SAML group names “để sau này có thể dùng” nhưng không có purpose/owner. Nên làm gì?

**Đáp án:** Flag release drift, xác nhận business/Privacy, giảm attribute release/storage/retention, kiểm không ảnh hưởng principal và least privilege.

**Câu 9.** Hai IdPs có nhóm `Admins`, có thể map cả hai sang `ROLE_ADMIN` không?

**Đáp án:** Không nếu chưa có approved issuer/tenant-specific mapping. Raw group names không độc lập chứng minh entitlement.

**Câu 10.** Grant privileged được reviewer tự approve và đóng ticket. Có đạt SoD không?

**Đáp án:** Thường không. Cần independent approval theo chính sách, chính xác nguồn HR/business và audit.

**Câu 11.** Đối tác thay Redirect URI sang trang debug HTTP tạm thời, có thể tạm chấp nhận vài giờ không?

**Đáp án:** Không mặc định. Authorization code có thể rò; exact HTTPS redirect URIs, allowed host/owner/security review và canary cần trước khi thay.

**Câu 12.** Review sheet báo “revoke complete” nhưng user vẫn đọc API data. Kết quả QA?

**Đáp án:** FAIL. Chỉ chốt sau khi effective deny được kiểm (token/session/resource/tenant), điều tra source auto-provision, caches và authorization.

**Câu 13.** SCIM `active=false` có đảm bảo IdP tự thu hồi mọi JWT đã phát không?

**Đáp án:** Không. SCIM là provisioning protocol; JWT/token lifecycle thuộc OAuth AS/RP/resource enforcement.

**Câu 14.** Khi thấy cert sắp hết hạn 90 ngày, đây có tự động là security incident không?

**Đáp án:** Không phải luôn. Nó là planned renewal alert; nếu cert bị lộ, expired, hoặc untrusted/invalid, escalation có thể cao hơn. Cần đánh giá role, exposure và rotation window.

**Câu 15.** Bằng chứng audit có cần chứa SAMLResponse đầy đủ để chứng minh IdP đã gửi group nào không?

**Đáp án:** Không. Có thể dùng sanitized schema/counts + verified fixture/results và limited-access signed test logs, không chứa raw PII.

## 22. Checklist nghiệm thu trước production và theo kỳ

- [ ] Inventory không bỏ sót đối tác IdP/OP, SP/RP, CAS, SCIM, API client và user/group/service identities.
- [ ] Mỗi partner có business owner, IAM owner, security/privacy contact, technical point of contact và contract expiry.
- [ ] Expected issuer/entityID, registrationId, audience/SP EntityID, ACS/redirect URI, SSO/SLO endpoints được pin và so với actual.
- [ ] TLS/PKIX/hostname checks, metadata signature verification policy, JWKS trusted keys và key usage được duy trì.
- [ ] SAML `validUntil`/`cacheDuration` được hiểu đúng, metadata refresh/repository convergence có test.
- [ ] IdP/SP signing/decryption cert lifecycle và secret rotation có owner, 90/60/30-day alert theo risk.
- [ ] Unknown signing key, untrusted metadata, wrong issuer/audience/recipient và expired assertions/tokens bị reject.
- [ ] OIDC client grant type, PKCE, scopes, redirect URI và client authentication được review theo RFC 9700.
- [ ] API access tokens có issuer/audience/scope/resource enforcement, không dùng ID Token thay access token.
- [ ] Dữ liệu chia sẻ có purpose, approved names, receiver, classification, retention và downstream propagation register.
- [ ] Custom `groups`/`roles` được map theo issuer/tenant allowlist, không cấp admin từ raw claims.
- [ ] SAML AttributeStatement/NameID và OIDC profile/email claims được tối thiểu hóa, loại bỏ unused PII và log leaks.
- [ ] Federation identity key dùng issuer+stable subject hoặc approved SAML equivalent; không auto-link bằng email trùng.
- [ ] Effective grants gồm IdP groups, local direct grants, DB ACL, API clients, break-glass và nested memberships.
- [ ] JML nguồn HR/contract authoritative, leaver/mover triggers gây revoke theo SLA ngay, không chờ kỳ audit.
- [ ] SCIM events và actual app grants được reconciliation, retries/dead letter/caching có tests.
- [ ] Local sessions/JWTs/refresh tokens có revocation/TTL/authoritative check phù hợp risk.
- [ ] Review có separate approver/implementer/verifier, especially privileged SoD.
- [ ] Reviewer quyết định giữ/giảm/thu hồi/exception với lý do, owner, expiry; không approve by silence.
- [ ] Configuration diff và unexpected claims/redirects/keys tạo ticket đúng severity.
- [ ] Thay đổi chỉ qua controlled deployment/IdP portal/secret store, có rollback không reintroduce compromised key.
- [ ] Mọi pods/regions của Spring Security dùng phiên bản trust/role mapping mong muốn; không stale key caches.
- [ ] Negative tests: revoked user cannot access tenant/resource; unknown issuer and group claims cannot escalate.
- [ ] Positive tests: approved user login và truy cập đúng resource không bị ảnh hưởng do giảm claims/rotate key.
- [ ] Audit artifacts được giả danh hóa và hạn chế quyền; không chứa raw tokens, cookies, SAMLResponse, private keys.
- [ ] Dashboard đo review overdue, stale privilege, drift, key expiry, SCIM revoke latency, runtime verification.
- [ ] Open findings có owner và deadline; review chưa đóng nếu readback hoặc test FAIL.
- [ ] Next review date và event-driven alerts hoạt động, lịch được theo dõi không bị quên khi owner thay.
- [ ] Tài liệu SOP/runbook cập nhật theo Spring Security/IdP major version, với signed staging fixtures và privacy safeguards.
- [ ] Mọi change sensitive có documented approver/rollback criteria/incident contact và evidence lưu theo retention.
- [ ] Đã phân biệt “SSO login works” với “effective access correct”, “data sharing lawful/minimal” và “partner trust still approved”.

**Kết luận:** Rà soát liên kết SSO phải là một **chu trình liên tục**: kiểm quyền hiệu lực, dữ liệu nhận/gửi theo mục đích và trust config của từng đối tác; chuyển mọi sai lệch thành hành động có chủ sở hữu, xác minh bằng readback và runtime negative tests, rồi lưu bằng chứng tối thiểu. Spring Security giúp enforce authentication/authorization nhưng không tự làm access certification, privacy review, hợp đồng đối tác hay key approval. Một chu kỳ review chỉ hoàn tất khi **đúng người còn đúng quyền, những người không còn được phép đã thực sự bị từ chối, dữ liệu không cần thiết ngừng được trao đổi và mọi issuer/callback/certificate tiếp tục được xác minh bằng trust policy đúng**.

## 23. Tài liệu chính thức và chuẩn tham chiếu

1. [NIST SP 800-63C-4 – Federation and Assertions (final, 2025)](https://csrc.nist.gov/pubs/sp/800/63/c/4/final): federation trust, RP/IdP, user identifier kết hợp issuer + subject, privacy và assertion protection.
2. [NIST SP 800-63-4 – Digital Identity Guidelines (2025)](https://csrc.nist.gov/pubs/sp/800/63/4/final): authentication/federation risk management framework.
3. [Spring Security – OAuth2 Client/Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/): client registrations, authorization and callback endpoints.
4. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): RelyingPartyRegistration, asserting party metadata and credentials.
5. [Spring Security – SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): parsing/publishing metadata và trust/refresh options.
6. [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): AuthorizationManager, request/method-level decisions.
7. [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/audience validation, JWK trust.
8. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext/HttpSession lifecycle.
9. [RFC 9700 – OAuth2 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): current best practice, redirect URI, PKCE và token flow safety.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `sub`/`iss`, scopes/claims, UserInfo, `email_verified` và ID Token validation.
11. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata, endpoints, JWKS URI.
12. [OASIS SAML2 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, validUntil/cacheDuration.
13. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertion, AudienceRestriction, SubjectConfirmation.
14. [OASIS SAML2 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): SAML Web SSO transport/binding.
15. [RFC 7643 – SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643): SCIM users/groups/active attributes.
16. [RFC 7644 – SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644): provisioning operations, PATCH, GET, DELETE.
17. [RFC 7009 – OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation endpoint.
18. [RFC 7662 – OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token active state.
19. [RFC 7591 – OAuth2 Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591): client metadata, redirect_uris và grant types.
20. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, per-request authorization.
21. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle/revocation.
22. [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): issuer/audience/signature/metadata trust.
23. [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): audit redaction và secret-safe logging.
24. [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): client secret/private key lifecycle.
