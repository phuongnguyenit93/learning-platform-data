# Authentication log: ghi nhận, tương quan và điều tra sự kiện xác thực trong IAM

Lúc 08:12, một nhân viên đăng nhập thành công vào hệ thống SSO. Ba phút sau, hệ thống tài chính nhận một request qua API mang access token còn hợp lệ. Đến 08:20, HRIS công bố nhân viên đó đã kết thúc quan hệ lao động có hiệu lực từ 08:00. Trong lúc điều tra, đội bảo mật nhìn thấy dòng log “Login successful” nhưng không biết **tài khoản nào, phương thức xác thực nào, thiết bị nào, IdP nào, phiên nào, ứng dụng nào và liệu yêu cầu API có thực sự thuộc về phiên vừa đăng nhập hay không**.

Đây là vấn đề của **authentication logging**: ghi lại sự kiện xác thực để có thể **truy vết danh tính và bối cảnh**, phát hiện hành vi đáng ngờ, hỗ trợ ứng cứu và đối soát vòng đời quyền. Một log xác thực hữu ích không chỉ là câu “đăng nhập thành công/thất bại”; nó cần **đủ ngữ nghĩa, đúng chủ thể, nguồn đáng tin, thời điểm chính xác, định danh có thể tương quan và bảo vệ dữ liệu nhạy cảm**.

Bài thuộc chương **Identity logging**, chủ đề trực tiếp **Authentication log**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi mô-đun là quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi thay đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Xác định **sự kiện nào là authentication event**, phân biệt với authorization, provisioning, session và risk event.
- Thiết kế **schema authentication log** cho IdP, SAML/OIDC SSO, MFA, passkey/WebAuthn, certificate/mTLS, PAM và workload identities.
- Tương quan đúng **Person/Engagement, account, issuer, tenant, device, session, request và ứng dụng** mà không chỉ dựa email/IP.
- Ghi log đủ để phân tích **Joiner–Mover–Leaver, password spraying, credential stuffing, MFA fatigue, bất thường thiết bị và token/session reuse**.
- Bảo vệ **password, OTP, token, cookie, private key, danh tính và dữ liệu cá nhân**, đồng thời bảo đảm integrity, access control và retention.
- Xây dựng pipeline **thu thập → chuẩn hóa → tương quan → phát hiện → điều tra → đối soát** và kiểm soát chất lượng bằng KPI, test và checklist.

## 1. Authentication log là gì?

**Authentication log** là bản ghi có cấu trúc về **một hoạt động xác thực hoặc bước trong luồng xác thực**, do một thành phần có thẩm quyền quan sát và tạo ra. Nó có thể ghi:

- Một principal **bắt đầu** yêu cầu xác thực.
- Hệ thống **kiểm chứng** mật khẩu, chứng chỉ, authenticator hoặc assertion.
- Hệ thống **yêu cầu hoặc hoàn tất MFA/step-up**.
- IdP **phát hành kết quả xác thực** cho ứng dụng trong luồng SSO.
- Yêu cầu bị **từ chối, khóa, bị gián đoạn hoặc hết thời gian**.
- Một session/token được **tạo, gia hạn, thu hồi hoặc dùng lại** (những sự kiện này thường thuộc *session/token logs* liên quan, không đồng nhất với login).

Một event trả lời câu hỏi:

> **Chủ thể nào đã thực hiện bước xác thực nào, với thành phần nào, tại thời điểm nào, dùng phương thức và ngữ cảnh nào, kết quả gì, và có bằng chứng nào liên kết tới các bước tiếp theo?**

### 1.1. Vì sao cần log có cấu trúc?

~~~text
LOG KÉM:
    "User login failed"

LOG CÓ THỂ ĐIỀU TRA:
    eventType       = AUTHENTICATION_FAILED
    eventTime       = 2026-12-01T08:12:03+07:00
    issuerId        = idp-corporate
    tenantId        = tenant-a
    accountRef      = acct-01042
    subjectRef      = person-1042 (nếu mapping đủ tin cậy)
    flowId          = flow-771
    authMethod      = PASSWORD
    reasonCategory  = INVALID_CREDENTIAL
    sourceNetwork   = nguồn đã được phân loại/giới hạn
    requestId       = req-8801
    outcome         = DENIED
~~~

Không nhất thiết hệ thống nào cũng biết mọi trường ngay tại thời điểm phát log. **Điều không quan sát được phải ghi UNKNOWN hoặc để trống theo schema**, không tự dựng `personId` hoặc thiết bị từ một IP.

### 1.2. Authentication log phục vụ những mục đích nào?

| Mục đích | Câu hỏi chính | Ví dụ bằng chứng |
| --- | --- | --- |
| **Security monitoring** | Có đăng nhập bất thường hoặc tấn công đang xảy ra không? | Fail bursts, suspicious source, MFA deny. |
| **Incident response** | Ai/đường nào có thể đã bị chiếm? | Auth flow, account, session, device, risk events. |
| **IAM lifecycle** | Người Joiner/Mover/Leaver còn đăng nhập được không? | Auth events trước/sau effectiveAt. |
| **Access governance** | Có tài khoản, IdP hoặc ứng dụng ngoài kiểm soát không? | Local login bypass SSO, unknown principal. |
| **Operational troubleshooting** | Vì sao login thất bại? | Protocol result, provider error, policy deny. |
| **Audit/attestation** | Có bằng chứng kiểm soát đã vận hành không? | Immutable-ish event chain, policy version, timestamps. |
| **Threat hunting** | Các sự kiện tưởng rời rạc có cùng tác nhân/chiến dịch không? | Correlation theo source, time, account cohort. |

## 2. Phân biệt authentication, authorization, session và provisioning

Đây là bốn nhóm sự kiện dễ bị gộp nhầm:

| Nhóm | Câu hỏi | Ví dụ | Kết luận không nên suy |
| --- | --- | --- | --- |
| **Authentication** | Principal có chứng minh được danh tính không? | Password/MFA/passkey/certificate verified. | Đã được phép đọc tài nguyên cụ thể. |
| **Authorization** | Chủ thể có quyền làm hành động này trên tài nguyên này không? | API trả DENY vì thiếu role Finance. | Người dùng chưa xác thực thành công. |
| **Session/token** | Có credential phiên hoặc access token đang được chấp nhận không? | SESSION_CREATED, TOKEN_REFRESHED. | Đã có sự kiện người dùng nhập mật khẩu mới. |
| **Provisioning/JML** | Tài khoản/quyền đã được tạo, thay đổi hoặc thu hồi chưa? | SCIM PATCH `active=false`, group removed. | Tất cả phiên ứng dụng đã mất hiệu lực. |

### 2.1. Một phiên đăng nhập có thể chứa nhiều log

~~~mermaid
flowchart TD
    A["User truy cập ứng dụng"] --> B["App yêu cầu sign-in"]
    B --> C["IdP: AUTH_FLOW_STARTED"]
    C --> D["Primary authenticator verified"]
    D --> E["MFA challenge / WebAuthn"]
    E --> F["MFA verified hoặc denied"]
    F --> G["AUTHENTICATION_SUCCEEDED"]
    G --> H["OIDC/SAML assertion/token issued"]
    H --> I["App validates response"]
    I --> J["Application session created"]
    J --> K["API: AUTHORIZATION decision"]
    K --> L["Resource action + audit"]
~~~

**AUTHENTICATION_SUCCEEDED** của IdP **khác** `APPLICATION_SESSION_CREATED` và **khác** `RESOURCE_ACCESS_ALLOWED`. Cần dùng correlation IDs hoặc liên kết phù hợp để nối chuỗi, không đổi nhãn tất cả thành “login”.

### 2.2. Login thành công không có nghĩa truy cập thành công

Một người có thể xác thực thành công nhưng bị RBAC từ chối vì thiếu role. Ngược lại, API có thể nhận token đã phát từ trước và không có một lần login mới ở thời điểm request. Điều tra “ai truy cập tài nguyên?” cần nối **authentication evidence + session/token lineage + authorization/resource logs**.

### 2.3. Authentication failure không đồng nghĩa tấn công

Sai mật khẩu có thể do người dùng gõ nhầm, credential cũ trong ứng dụng, đồng hồ thiết bị lệch, IdP outage, MFA không khả dụng, Conditional Access, khóa account hoặc tấn công. Phải phân loại **reason** và kết hợp ngữ cảnh, không gắn mọi `FAILED` thành `ATTACK`.

## 3. Những nguồn authentication log phổ biến

| Nguồn | Sự kiện điển hình | Điểm giới hạn |
| --- | --- | --- |
| **IdP/Directory** | Password verification, MFA, policy challenge/deny, account lock, sign-in. | Có thể không thấy app-local sessions. |
| **OIDC/OAuth authorization server** | Authorization request, authentication, token issuance, refresh, revoke. | Token event không đồng nghĩa có tương tác người dùng mới. |
| **SAML IdP** | Authn request, assertion issued, federation errors. | Assertion issued không chứng minh SP đã chấp nhận. |
| **Relying Party/Service Provider** | Federation response verified/failed, local login, app session creation. | Không thấy toàn bộ quá trình xác thực trong IdP. |
| **MFA/Authenticator provider** | Challenge sent, approved/denied, factor enrollment/use. | “Push delivered” không phải “factor verified”. |
| **PAM/PIM** | Privileged authentication, vault checkout, elevation, session start. | Có thể có đường quản trị trực tiếp ngoài PAM. |
| **VPN/ZTNA/Reverse proxy** | Device/user auth, certificate verification, denied connections. | Không tự chứng minh authorization tại API cuối. |
| **OS/Directory services** | Kerberos, LDAP bind, local login, SSH, RDP. | Thuật ngữ và event IDs tùy nền tảng. |
| **API gateway/resource server** | Token validated/invalid, client certificate auth, denied token. | Một request có token hợp lệ không phải user vừa login. |
| **Cloud workload identity/STS** | Role assumption, service principal auth, token exchange. | Chủ thể máy khác Person, không có MFA như người dùng. |
| **Application-local authentication** | Local password/session, fallback admin sign-in. | Có thể bypass IdP/SSO nếu không giám sát riêng. |

### 3.1. Không để nguồn duy nhất tạo điểm mù

Trong môi trường SSO, một ứng dụng có thể hỗ trợ **local admin fallback**. IdP sign-in logs không có event nào, nhưng local admin vẫn vào được ứng dụng. Vì vậy, phải duy trì inventory **authentication paths**: đường bình thường, break-glass, LDAP/legacy, API/service principal và các đường dự phòng.

### 3.2. Phân quyền theo nguồn

Một authentication event có thể đến từ hệ thống bên thứ ba; mọi assertion như `username`, `sourceIp`, `deviceName` phải được đánh giá **độ tin cậy và khả năng giả mạo** theo nguồn. Log của reverse proxy tin cậy khác hẳn chuỗi `X-Forwarded-For` do client gửi từ Internet nếu proxy chưa làm sạch headers.

## 4. Phân loại loại sự kiện xác thực

Không nên dồn mọi hoạt động vào `LOGIN_SUCCESS` hoặc `LOGIN_FAILURE`.

| Event category | Event type minh họa | Ý nghĩa |
| --- | --- | --- |
| **Flow lifecycle** | AUTH_FLOW_STARTED, AUTH_FLOW_ABORTED, AUTH_FLOW_TIMED_OUT. | Dòng xác thực bắt đầu, dừng hoặc hết hạn. |
| **Primary credential** | PRIMARY_AUTH_VERIFIED, PRIMARY_AUTH_FAILED. | Bằng chứng yếu tố đầu được kiểm. |
| **MFA** | MFA_CHALLENGE_ISSUED, MFA_VERIFIED, MFA_DENIED, MFA_EXPIRED. | Phân biệt gửi yêu cầu với xác nhận. |
| **Passwordless** | PASSKEY_ASSERTION_VERIFIED, AUTHENTICATOR_ERROR. | Verify một authenticator response. |
| **Certificate** | CLIENT_CERT_VERIFIED, CLIENT_CERT_REJECTED. | Xác thực dựa certificate/PKI. |
| **Federation** | ASSERTION_ACCEPTED, ASSERTION_REJECTED, FEDERATION_ERROR. | IdP/SP hoặc OP/RP nhận/xử lý kết quả. |
| **Final authentication** | AUTHENTICATION_SUCCEEDED, AUTHENTICATION_FAILED. | Kết quả cuối theo policy của issuer/ứng dụng. |
| **Policy enforcement** | CONDITIONAL_ACCESS_DENIED, STEP_UP_REQUIRED. | Từ chối do posture/risk/assurance. |
| **Account defense** | ACCOUNT_LOCKED, RISK_CHALLENGE_TRIGGERED. | Kiểm soát chống thử credential/rủi ro. |
| **Session** | SESSION_CREATED, SESSION_REVOKED, SESSION_EXPIRED. | Liên kết, nhưng không phải mọi event là login. |
| **Token** | TOKEN_ISSUED, REFRESH_REUSED, TOKEN_REVOKED. | Sự kiện cấp, dùng lại hoặc thu hồi token. |
| **Recovery** | PASSWORD_RESET_COMPLETED, FACTOR_RESET_COMPLETED. | Thay đổi yếu tố xác thực; cần giám sát đặc biệt. |
| **Emergency** | BREAK_GLASS_AUTHENTICATED, EMERGENCY_SESSION_STARTED. | Đường khẩn với yêu cầu hậu kiểm riêng. |

**Tên event trên là taxonomy minh họa**, không phải enum chuẩn bắt buộc của OAuth, SAML, WebAuthn hay mọi SIEM. Một hệ thống thực cần tài liệu hóa mapping từ event gốc sang schema chuẩn hóa mà không xóa raw event có ích.

### 4.1. Quy trình có nhiều bước không được tính nhiều lần như nhiều login

Một authentication flow có thể tạo các event `PRIMARY_AUTH_VERIFIED`, `MFA_VERIFIED` và `AUTHENTICATION_SUCCEEDED`. Báo cáo số lần login thành công nên đếm **final successful flow** theo khóa duy nhất, không cộng cả ba event.

### 4.2. Không có final event không mặc nhiên là thất bại

Một luồng có `AUTH_FLOW_STARTED` nhưng không có terminal event có thể là user đóng tab, mất mạng, provider lỗi, telemetry thiếu hoặc hoạt động đáng ngờ. Sau cửa sổ chờ hợp lý, đặt trạng thái **UNKNOWN/ABANDONED/INCOMPLETE** theo policy, không tự ghi `INVALID_PASSWORD`.

## 5. Schema tối thiểu của một Authentication event

Một log xác thực tốt cần **nhận diện sự kiện, định vị thời gian, nguồn, chủ thể, phương thức, kết quả, bối cảnh, trace**.

| Nhóm trường | Trường ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| **Event identity** | `eventId`, `eventType`, `schemaVersion`. | Chống đếm trùng và kiểm version. |
| **Time** | `eventTime`, `observedAt`, `ingestedAt`. | Phân biệt sự kiện diễn ra và lúc nhận. |
| **Source** | `sourceSystem`, `issuerId`, `tenantId`. | Namespace, trust và ownership. |
| **Principal** | `subjectId`, `accountId`, `principalType`. | Xác định ai/đối tượng máy nào. |
| **Identity mapping** | `personId`, `engagementId` hoặc `workloadId`. | Tương quan JML và owner, khi nguồn đủ tin. |
| **Authentication** | `authMethod`, `factors`, `authStrength`. | Phương thức/bảo đảm thực sự đạt. |
| **Outcome** | `outcome`, `reasonCategory`, `providerCode`. | Phân biệt thành công/từ chối/lỗi. |
| **Flow/session** | `authFlowId`, `requestId`, `sessionRef`. | Ghép bước và truy vết phiên. |
| **Application** | `clientId`, `relyingPartyId`, `resourceId`. | Xác định hệ thống nhận kết quả. |
| **Network** | `sourceIp` hoặc network reference, `userAgentCategory`. | Phân tích rủi ro, có giới hạn tin cậy. |
| **Device** | `deviceId`, `deviceEvidenceRef`, `postureState`. | Gắn ngữ cảnh endpoint đúng nguồn. |
| **Risk/policy** | `riskLevel`, `policyId`, `policyVersion`. | Vì sao challenge/deny. |
| **Assurance** | `correlationConfidence`, `sourceIntegrityRef`. | Đánh giá độ tin cậy kết luận. |

Không phải mọi event đều cần lưu **địa chỉ IP đầy đủ, user-agent nguyên văn hoặc tọa độ chính xác**; chọn thuộc tính tối thiểu phù hợp mục đích, bảo mật và quy định. Khi phục vụ điều tra, có thể lưu các trường nhạy cảm ở **kho phân quyền sâu** và chỉ dùng bản đã giảm chi tiết ở dashboard.

### 5.1. Ví dụ JSON minh họa: login hoàn tất

~~~json
{
  "schemaVersion": "auth-event-v1",
  "eventId": "evt-auth-20261201-00042",
  "eventType": "AUTHENTICATION_SUCCEEDED",
  "eventTime": "2026-12-01T08:12:09+07:00",
  "ingestedAt": "2026-12-01T08:12:11+07:00",
  "sourceSystem": "corporate-idp",
  "issuerId": "https://idp.example.invalid/tenant-a",
  "tenantId": "tenant-a",
  "principalType": "HUMAN",
  "accountId": "acct-01042",
  "subjectId": "sub-idp-1042",
  "personId": "person-1042",
  "engagementId": "EMP-5812",
  "identityMappingConfidence": "AUTHORITATIVE",
  "authFlowId": "flow-00771",
  "requestId": "req-8801",
  "clientId": "finance-portal",
  "authMethods": ["PASSWORD", "WEBAUTHN"],
  "authStrength": "POLICY_REQUIRED_FACTORS_MET",
  "outcome": "SUCCESS",
  "riskLevel": "LOW",
  "policyId": "workforce-signin-policy",
  "policyVersion": "v7",
  "deviceId": "device-ref-101",
  "deviceEvidenceRef": "mdm-posture-881",
  "sessionRef": "sess-ref-00912",
  "sourceIpClass": "CORPORATE_EGRESS",
  "traceId": "trace-idp-8801"
}
~~~

**Ví dụ hoàn toàn giả định**; tên trường không phải chuẩn thống nhất của mọi IdP. Domain `example.invalid` chỉ là địa chỉ minh họa, không phải dịch vụ thật. Những ID chỉ là reference, không phải token hoặc tài khoản của người thực.

### 5.2. Ví dụ JSON: thất bại không chứa bí mật

~~~json
{
  "schemaVersion": "auth-event-v1",
  "eventId": "evt-auth-20261201-00043",
  "eventType": "AUTHENTICATION_FAILED",
  "eventTime": "2026-12-01T08:12:14+07:00",
  "sourceSystem": "corporate-idp",
  "tenantId": "tenant-a",
  "principalType": "HUMAN",
  "accountRef": "acct-pseudonym-9f1",
  "authFlowId": "flow-00772",
  "authMethod": "PASSWORD",
  "outcome": "DENIED",
  "reasonCategory": "INVALID_CREDENTIAL_OR_UNKNOWN_ACCOUNT",
  "sourceNetworkRef": "network-class-447",
  "policyVersion": "v7",
  "traceId": "trace-idp-8802"
}
~~~

Trong nhiều trường hợp **không nên xác nhận cho client biết tài khoản có tồn tại hay không**, tránh user enumeration. Log nội bộ có thể có phân loại chi tiết hơn khi cần và được bảo vệ, nhưng **không chứa password được gửi**, kể cả password sai.

## 6. Identity correlation: Subject, Account, Person và Engagement

Để trả lời câu hỏi IAM, phải tách:

~~~text
Person
  └── Engagement E1 (Employee)
        ├── IdP account A
        ├── Application local account B
        └── Privileged account C

Person có thể có Engagement E2 mới khi rehire.
Device D có identity riêng; session S gắn vào account/issuer.
Workload W có principal khác với human accounts.
~~~

### 6.1. Khóa nối an toàn

| Khóa | Dùng để | Lưu ý |
| --- | --- | --- |
| **Person ID** | Xác định con người qua nhiều account nếu mapping đã được xác minh. | Không tự suy từ display name/email. |
| **Engagement ID** | Xác định quan hệ lao động/hợp đồng theo JML. | Rehire có thể tạo Engagement mới. |
| **Issuer + Subject** | OIDC principal trong namespace cụ thể. | `sub` không có ý nghĩa toàn cục nếu thiếu `iss`. |
| **Directory object ID/SID** | Identity trong directory scope. | Namespace và lifecycle riêng từng directory. |
| **Account ID** | Tài khoản local/PAM/SaaS. | Một Person có nhiều account. |
| **Session reference** | Một phiên hoặc session family cụ thể. | Không lưu raw cookie/session secret. |
| **Device ID + issuer/tenant** | Thiết bị/attestation context. | Có thể re-enroll hoặc reassign. |
| **Workload/Service principal ID** | Chủ thể máy, owner/team. | Không tự gắn vào Person chỉ vì creator. |

### 6.2. Vì sao email, IP và hostname không đủ?

Email có thể đổi hoặc tái cấp; IP có NAT/VPN/shared proxy; hostname có thể trùng và spoof; account admin phụ có thể thuộc cùng Person. Tương quan dựa vào **nguồn có thẩm quyền, immutable/stable ID, tenant và thời điểm hiệu lực**, có ghi mức tin cậy.

### 6.3. Tương quan không chắc chắn

Khi một local account không map chắc về Person, đặt:

~~~text
identityCorrelation = UNRESOLVED
accountRef          = local-admin-42
ownerStatus         = UNKNOWN
triageOwner         = application-security
~~~

Không tự gán log đó cho người đang giữ email trông giống tên account. **UNKNOWN là tín hiệu quản trị**, không phải dữ liệu được phép bị bỏ qua.

## 7. Thời gian trong log: eventTime, observedAt, ingestedAt

Một log có ít nhất ba mốc thời gian có thể khác nhau:

| Trường | Ý nghĩa | Rủi ro khi trộn |
| --- | --- | --- |
| **eventTime** | Lúc sự kiện thực sự diễn ra theo đồng hồ nguồn. | Clock skew của nguồn. |
| **observedAt** | Lúc sensor/gateway quan sát sự kiện. | Buffer hoặc delay tại nguồn. |
| **ingestedAt** | Lúc collector/SIEM nhận bản ghi. | Pipeline/network delay. |

### 7.1. Ví dụ log đến muộn

~~~text
08:00  HRIS: Leaver effectiveAt.
08:05  IdP: Authentication attempt after Leaver.
08:10  SIEM nhận log IdP 08:05.
08:15  SIEM mới nhận event HRIS 08:00.
~~~

Nếu dashboard sắp theo `ingestedAt`, nó có thể hiển thị login trước Leaver, dù **effectiveAt của Leaver sớm hơn**. Khi điều tra JML, dùng **event time/effective time từ nguồn có thẩm quyền**, cộng ghi chú độ trễ ingest, không chỉ dựa vào thứ tự xuất hiện trên SIEM.

### 7.2. Timezone và UTC

Nên dùng timestamp có timezone/offset rõ, ví dụ `2026-12-01T08:12:00+07:00` hoặc UTC tương đương, đồng bộ đồng hồ nguồn và cảnh báo clock drift. Không áp đặt mọi sản phẩm phải hiển thị giờ địa phương; **quy tắc chuẩn hóa phải nhất quán và tái dựng được**.

### 7.3. Thứ tự sự kiện phân tán

Một flow OIDC/SAML có nhiều server, queue và retry. Không thể suy thứ tự chính xác chỉ từ timestamp lệch vài mili giây. Khi cần, dùng `flowId`, `requestId`, `sequence`, `sourceVersion`, causal references và điều kiện nghiệp vụ để tái dựng. Đối với event đến muộn, có thể cập nhật **finding** có version mà không xóa sự kiện gốc.

## 8. Kết quả và lý do thất bại cần nhất quán

### 8.1. Mô hình outcome

~~~text
SUCCESS       = bước hoặc flow được xác nhận thành công.
DENIED        = yêu cầu bị từ chối theo credential/policy.
CHALLENGED    = cần thêm bước, chưa có kết quả cuối.
CANCELLED     = actor/app chủ động hủy khi quan sát được.
TIMED_OUT     = flow/challenge hết thời gian.
ERROR         = lỗi kỹ thuật/hạ tầng/giao thức.
INDETERMINATE = chưa đủ dữ liệu kết luận.
~~~

**Chọn outcome theo đúng event granularity.** `MFA_CHALLENGE_ISSUED` có thể mang `CHALLENGED`, còn cùng auth flow về sau có `AUTHENTICATION_SUCCEEDED`. Không tính đó là mâu thuẫn.

### 8.2. Reason taxonomy

| Reason category | Ví dụ cụ thể | Nên làm gì? |
| --- | --- | --- |
| **INVALID_CREDENTIAL** | Password, passkey assertion hoặc certificate không hợp lệ. | Phân tích nguồn, số lần, account cohort. |
| **ACCOUNT_DISABLED/EXPIRED** | Leaver, contractor end date, disabled account. | Kiểm JML effectiveAt và đường local bypass. |
| **ACCOUNT_LOCKED** | Lock theo policy sau nhiều lần thử. | Kiểm brute force và ảnh hưởng người dùng. |
| **MFA_NOT_COMPLETED** | Push bị từ chối/hết hạn hoặc user không xác nhận. | Không đồng nhất với mật khẩu sai. |
| **DEVICE_NONCOMPLIANT** | MDM/EDR posture không đạt. | Xem freshness và policy, remediation. |
| **CONDITIONAL_ACCESS_DENIED** | Context/risk/tenant không đủ. | Kiểm policy version, exception. |
| **FEDERATION_VALIDATION_FAILED** | OIDC/SAML issuer/audience/signature mismatch. | Điều tra cấu hình/trust hoặc sự kiện đáng ngờ. |
| **TOKEN_EXPIRED/REVOKED** | API không chấp nhận bearer/session. | Đối chiếu token/session, không gọi là login sai password. |
| **PROVIDER_UNAVAILABLE** | IdP, MFA, directory bị outage. | Alert SRE/Identity Ops, tránh false positive tấn công. |
| **CLIENT_ABORTED** | App ngừng flow hoặc không nhận callback. | Chẩn đoán UX và event flow, không suy intent. |
| **UNKNOWN** | Không rõ nguyên nhân vì thiếu evidence. | Ghi data-quality gap và triage. |

### 8.3. Giữ provider code nhưng chuẩn hóa an toàn

Nên giữ `rawProviderCode` hoặc reference có kiểm soát để support debug, đồng thời ánh xạ `reasonCategory` dùng chung. Không để thông điệp thô chứa password, HTTP Authorization header, token hoặc dữ liệu riêng tư được chuyển thẳng tới SIEM.

## 9. MFA logging: challenge, factor và assurance

Một luồng MFA có thể có:

~~~text
AUTH_FLOW_STARTED
  -> PRIMARY_AUTH_VERIFIED
  -> MFA_CHALLENGE_ISSUED
  -> MFA_CHALLENGE_DELIVERED (nếu provider có bằng chứng)
  -> MFA_RESPONSE_VERIFIED hoặc MFA_DENIED/EXPIRED
  -> AUTHENTICATION_SUCCEEDED hoặc FAILED
~~~

**MFA challenge sent != MFA verified != login succeeded.**

### 9.1. Những trường nên ghi

| Trường | Ý nghĩa | Không lưu |
| --- | --- | --- |
| **factorType** | WebAuthn, TOTP, push, SMS, hardware token... | Mã TOTP/SMS/OTP. |
| **factorRef** | ID tham chiếu đã giả danh/ẩn thông tin. | Seed/secret hoặc public PII không cần thiết. |
| **challengeId/flowId** | Tương quan challenge với response. | Secret của challenge/session. |
| **challengeIssuedAt/respondedAt** | Độ trễ, timeout, spam pattern. | Raw payload nhạy cảm. |
| **outcome** | APPROVED, DENIED, EXPIRED, CANCELLED. | Giả “thành công” chỉ vì push gửi được. |
| **authStrength/assurance** | Mức yêu cầu đã đạt theo policy. | Khẳng định phishing-resistant nếu factor không đáp ứng. |
| **risk/context** | Thiết bị lạ, impossible travel signal, policy challenge. | Geolocation chính xác không cần thiết. |

### 9.2. MFA fatigue / push bombing

Một người dùng nhận nhiều push liên tiếp có thể bấm Approve nhầm hoặc do bị gây áp lực. Dấu hiệu điều tra gồm:

- Số challenge/push tăng bất thường tới cùng account/factor.
- Chuỗi nhiều **DENIED/EXPIRED** rồi một **APPROVED**.
- Nguồn network/device thay đổi, time window ngắn.
- Sau lần Approved có hành động nhạy cảm, enrollment factor mới hoặc đổi session.

**Một lần approve không tự chứng minh user thật đã chủ động phê duyệt.** Cần tương quan device/risk, token issuance, resource actions và phản hồi người dùng qua quy trình ứng cứu phù hợp.

## 10. Passkeys/WebAuthn và phishing-resistant authentication logs

Với WebAuthn, server gửi challenge và xác minh assertion từ authenticator. Authentication log nên ghi **kết quả xác minh giao thức** và bối cảnh chính sách, không ghi raw authenticator data nhạy cảm khi không cần.

### 10.1. Trường hữu ích

- `authenticatorCredentialRef` hoặc credential ID được quản lý/giảm chi tiết.
- `rpId`/relying party namespace được xác minh.
- `challengeFlowRef` và freshness.
- `userVerificationResult` khi được kiểm theo policy.
- `signatureVerificationResult`, credential status.
- `authenticatorClass` hoặc assurance level nếu được chính sách hỗ trợ.
- `failureReason` như invalid signature, challenge mismatch hoặc credential revoked.

**Không coi mọi “passwordless” là cùng mức đảm bảo.** Ví dụ, cách dùng passkey, user verification và tính chống phishing phụ thuộc quy trình và policy được kiểm cụ thể.

### 10.2. Attestation không đồng nghĩa toàn bộ device posture

WebAuthn authenticator attestation, nếu được dùng, nói về thuộc tính hoặc nguồn authenticator trong phạm vi chứng thực; **không tự xác nhận OS của laptop đang compliant**. Nếu policy cần device trust, phải tương quan với UEM/MDM/EDR hoặc bằng chứng nền tảng tương ứng.

## 11. Certificate, Kerberos, LDAP, SSH và xác thực không qua trình duyệt

Không phải mọi authentication event đều bắt nguồn từ HTML login form.

| Phương thức/nguồn | Log đáng lưu | Sai lầm thường gặp |
| --- | --- | --- |
| **mTLS/X.509** | Client identity, issuer, cert ref, validation/revocation result, target. | Log raw private key hoặc coi certificate valid là authorization. |
| **Kerberos** | Ticket request/validation result, principal, service, domain/realm, reason. | Coi ticket issuance là mọi resource access đã được duyệt. |
| **LDAP bind** | Bind identity, auth method, source/target, result, error code. | Log bind password hoặc DN đầy đủ vượt nhu cầu. |
| **SSH** | Principal/key ref, source, host, authentication result, session ref. | Chỉ log username, bỏ key/host/owner mapping. |
| **RDP/OS local login** | Logon type, account, host, result, session/logoff. | Không phân biệt interactive và service logons. |
| **Cloud STS/assume-role** | Service/workload principal, trust, role, session duration, outcome. | Coi role assumption là human MFA login. |

### 11.1. Machine authentication có thể diễn ra liên tục

Một dịch vụ có thể dùng mTLS để xác thực hàng nghìn kết nối mỗi phút. Không nên đếm mọi handshake như một người đăng nhập. Phân tích theo **principal type, credential type, workload owner, service identity, baseline** và phân biệt event kết nối với event token/session issuance.

### 11.2. Certificate còn hạn không chứng minh hợp lệ

Trong log certificate validation, nên phân biệt **chain trusted, EKU phù hợp, NotBefore/NotAfter, revocation status, hostname/SAN hoặc principal binding** theo cơ chế được dùng. Một handshake TLS thành công không chứng minh chủ thể có quyền thao tác nghiệp vụ.

## 12. SSO federation: liên kết log IdP và ứng dụng

Một flow SSO đi qua nhiều hệ thống; điều tra cần theo dõi **issuer → RP/SP → app session → API**.

### 12.1. OIDC

Những mốc điển hình:

~~~text
RP sends authorization request
IdP begins auth flow
User authenticates / MFA checks
OP issues authorization response/code
RP exchanges code (nếu flow có token exchange)
RP validates ID token + issuer/audience/nonce...
RP creates local session
Resource server validates access token for API
~~~

**Không log raw authorization code, access token, refresh token hoặc ID token** vào dashboard, trace hay ticket. Thay vào đó ghi **flow ID, token issuance reference/jti nếu an toàn, issuer/audience, clientId, timestamp, validation outcome**.

### 12.2. SAML

Theo dõi:

- AuthnRequest reference và SP/IdP metadata phiên bản nếu cần.
- Assertion issuance/validation outcome.
- Issuer, Audience, Recipient/Destination và điều kiện thời gian dưới dạng metadata.
- Chữ ký/certificate verification result.
- NameID/subject mapping reference (không public raw PII không cần).
- SP session creation và SSO logout/SLO khi dùng.

**IdP assertion issued ≠ SP session created**. Nếu SP từ chối assertion do audience mismatch, phải có event ở SP; chỉ nhìn log IdP success sẽ bỏ sót lỗi login.

### 12.3. Tương quan không cần lưu secret

Có thể dùng `authFlowId`, `requestId`, `traceId`, `stateRef`, `assertionRef` hoặc `providerEventId` với chính sách ẩn dữ liệu. **Không ghi raw OAuth `state`/`nonce` nếu chúng được dùng trong cơ chế bảo vệ luồng và mang tính bí mật/binding**; sử dụng ID tham chiếu không tiết lộ giá trị.

### 12.4. Session sau SSO là một lớp riêng

Một user được IdP xác thực thành công lúc 09:00; ứng dụng tạo cookie session tới 17:00. Lúc 13:00, IdP account bị disabled. Nếu SP không có session revocation, cookie ở ứng dụng có thể còn hoạt động. Vì vậy, authentication log cần liên kết với **IdP disable event, SP session lifecycle, API authorization và revocation verification**.

## 13. Tương quan Authentication log với Session management

Log xác thực thường mở đầu một chuỗi truy cập, nhưng **phiên sống lâu hơn một lần xác thực**. Một user có thể giữ session qua nhiều request, token refresh hoặc ứng dụng.

### 13.1. Các sự kiện của phiên nên liên kết

| Event | Mốc cần lưu | Ý nghĩa |
| --- | --- | --- |
| **AUTHENTICATION_SUCCEEDED** | `authenticatedAt`, auth flow, method/assurance. | Người dùng đã qua xác thực theo policy. |
| **SESSION_CREATED** | `sessionRef`, `createdAt`, `absoluteExpiresAt`. | Ứng dụng thiết lập phiên. |
| **SESSION_USED** | Thời gian, app/resource, source context. | Có yêu cầu sử dụng session. |
| **SESSION_STEP_UP** | Factor, assurance, outcome, thời gian. | Bổ sung mức bảo đảm cho thao tác. |
| **TOKEN_REFRESHED** | FamilyRef, tokenRef, time, policy result. | Cấp token mới, **không phải login mới**. |
| **SESSION_REVOKED** | Reason, requestedAt, effectiveAt, actor/system. | Có yêu cầu hoặc hành vi thu hồi. |
| **SESSION_EXPIRED** | IDLE/ABSOLUTE/token reason, time. | Deadline đã tới hoặc phiên bị đánh dấu hết. |
| **RESOURCE_ACCESS_DENIED** | PEP, app/action, session/token reference. | Bằng chứng quyền không được thực thi ở đích. |

### 13.2. Absolute timeout và ý nghĩa log

Giả sử session có absolute deadline 17:00:

~~~text
09:00  AUTHENTICATION_SUCCEEDED
09:00  SESSION_CREATED (absoluteExpiresAt=17:00)
16:59  RESOURCE_ACCESS_ALLOWED
17:00  SESSION_EXPIRED_ABSOLUTE
17:01  RESOURCE_ACCESS_DENIED (session-ref matching)
~~~

Một sự kiện `SESSION_EXPIRED_ABSOLUTE` trong store **chưa chứng minh** mọi API đã từ chối token liên quan. Cần **PEP denial** hoặc bằng chứng giới hạn vòng đời token theo phạm vi bảo đảm của hệ thống.

### 13.3. Một người có nhiều phiên

Logout một browser có thể chỉ thu hồi một session, trong khi IdP SSO cookie, mobile refresh family và app session khác vẫn sống. Khi người dùng yêu cầu **logout all**, Security incident hoặc Leaver:

- Tương quan tất cả `sessionRef/tokenFamilyRef` thuộc đúng principal/tenant.
- Theo dõi lệnh và kết quả thu hồi riêng từng provider.
- Phát hiện phiên còn thực thi được sau deadline/sự kiện.
- Không log raw token trong quá trình truy vết.

### 13.4. Phân biệt đăng nhập mới và silent SSO

Một RP redirect sang IdP rồi nhận callback thành công không nhất thiết có một lần người dùng vừa nhập mật khẩu. Cần các trường `authenticationTime`, `sessionCreationTime` và phương thức xác thực thực tế, nếu nguồn cung cấp. Đừng tính mọi SSO redirect/callback thành “MFA vừa được người dùng thực hiện”.

## 14. Authentication log trong Joiner–Mover–Leaver

Khi kết hợp **HRIS, IAM/IGA, IdP, SSO, SCIM và ứng dụng**, authentication logs trở thành công cụ xác minh **quyền truy cập thực tế theo vòng đời**, không chỉ chỉ số đăng nhập.

### 14.1. Joiner: bắt đầu quá sớm hoặc chưa được cấp đúng quyền

Ví dụ nhân viên có `startDate` ngày 01/12 nhưng pre-provision account ngày 28/11:

| Tình huống | Cần quan sát | Kết luận |
| --- | --- | --- |
| Login preboarding vào portal giới hạn. | Auth event, app, purpose, policy, effectiveAt. | Có thể hợp lệ nếu policy cho. |
| Login thành công vào ứng dụng production trước Start date. | Auth, app session, resource action, role và identity mapping. | Cần kiểm eligibility; không tự coi hợp lệ. |
| Login bị từ chối do chưa ACTIVE. | ACCOUNT_NOT_YET_ACTIVE, clientId, policy version. | Có thể là kiểm soát đúng, không hẳn sự cố. |
| Login thất bại hàng loạt sau ngày bắt đầu. | Account status, IdP/SCIM sync, errors. | Có thể là lỗi provisioning/HRIS. |

**Pre-provisioned ≠ Active/Authorized**. Authentication success nếu có cũng không thay policy về thời điểm bắt đầu quan hệ.

### 14.2. Mover: đăng nhập với quyền và thuộc tính cũ

Một nhân viên chuyển SRE sang Finance lúc 13:00:

~~~text
13:00 HRIS Mover effectiveAt
13:01 IGA revoke SRE role, grant Finance role
13:02 IdP logs authentication success with current account
13:03 App API receives cached token with old SRE claim
13:04 App allows production-admin action (unexpected)
~~~

**Authentication success không phải vấn đề tự thân**, vì nhân viên vẫn được làm việc. Rủi ro là **authorization/privileged action sau khi role cũ đáng ra phải mất**. Nối log auth với token issuance, claim version, IdP group change, app-local role và PEP decision.

### 14.3. Leaver: login attempt sau termination

Một trong những rule giá trị cao:

~~~text
IF subject.engagementState == TERMINATED at eventTime
AND event is authentication attempt/success
THEN correlate identity + application + access path
     verify whether account/session remains usable
     prioritize by risk and observed effective access
~~~

**Không phải mọi attempt là vi phạm đã thành công**. Một lần đăng nhập bị từ chối sau Leaver có thể chứng minh kiểm soát đã chặn đúng. Ngược lại, **LOGIN_SUCCESS sau Leaver** hoặc app session/API action được cho phép cần điều tra khẩn theo severity, dữ liệu nguồn và policy.

### 14.4. Các lớp xác minh Leaver

| Nguồn | Cần kiểm | Kết luận không thể rút ra từ log đơn lẻ |
| --- | --- | --- |
| **HRIS** | EffectiveAt, employee/contractor, Person–Engagement. | Session đã bị thu hồi. |
| **IdP** | Sign-in disabled, auth attempt/success sau end. | App-local login luôn bị chặn. |
| **SCIM** | User `active=false`, group membership updates. | Cookie/API key đã chết. |
| **Application SP** | Local login/session, token-based auth. | Chỉ vì IdP khóa nên app đã từ chối. |
| **PAM** | Privileged account/session/use. | Quyền admin không còn qua direct path khác. |
| **API gateway** | Credential usage, access attempts, allow/deny. | Mọi nguồn dữ liệu khác cũng đã đồng bộ. |

### 14.5. Rehire và Engagement mới

Một Person tái tuyển có thể dùng cùng email/UPN, nhưng **Engagement mới** không tự gia hạn phiên cũ hay phê duyệt quyền cũ. Tương quan `personId` giúp nối lịch sử khi có thẩm quyền; `engagementId` giúp phân biệt **lần làm việc E1 và E2**. Đừng quy một auth event của E1 cho E2 chỉ vì email giống nhau.

### 14.6. Contractor, partner và guest identities

Khách/đối tác có thể đăng nhập qua federation, external IdP hoặc local guest. Những dữ liệu cần đánh giá gồm **sponsor, tenant, issuer, contract expiry, invitedAt, consent/trust, last successful auth**, trong phạm vi hệ thống có. Log nên báo **ownerless/expired guest activity**, đồng thời tránh tự suy Person nội bộ từ account ngoài.

## 15. Privileged authentication và emergency/break-glass

Đăng nhập vào PAM, tài khoản admin hoặc emergency access có mức rủi ro khác với portal nhân viên bình thường.

### 15.1. Những sự kiện cần ưu tiên

- Admin/privileged account login success/failure.
- Step-up và **phishing-resistant MFA** theo policy.
- Privileged role activation/eligibility.
- Vault checkout/credential access.
- Break-glass account authentication khi IdP/PAM bình thường không khả dụng.
- Privileged session start/end và những action có tác động lớn.
- Local admin login không qua SSO.
- Password reset/MFA factor reset cho tài khoản đặc quyền.
- Sign-in của privileged account **sau Mover/Leaver**.

### 15.2. Break-glass không nên mù log

Nếu cơ chế khẩn được thiết kế để hoạt động khi IdP chính lỗi, cần một đường ghi dấu độc lập đủ tin cậy: **incidentId, named actor/checkout, activationAt, scope, session reference, alert, action trail, review owner và hậu kiểm**. Một số thành phần có thể offline; phải lưu/đẩy log khi phục hồi và ghi rõ khoảng trống evidence.

**Không dùng tài khoản khẩn để bỏ việc giám sát xác thực.** Nếu không thể gắn shared emergency account với cá nhân do thiết kế, đây là **attribution gap** cần kiểm soát bù và đánh giá rủi ro.

### 15.3. SoD và log phê duyệt

Log đăng nhập approver không chứng minh một request đã được phê duyệt hợp lệ. Cần nối:

~~~text
approver authenticated
  -> actor identity + current authority checked
  -> approval decision with request version
  -> provisioning/elevation executed
  -> target privilege verified
  -> privileged actions audited
~~~

Một người có user account và admin account vẫn là **cùng Person** khi kiểm self-approval theo policy. Tương quan bằng canonical identity chứ không lấy hai account IDs khác nhau làm bằng chứng độc lập.

## 16. Workload identities, service principals và machine authentication

Không phải mọi xác thực có con người ở đầu bên kia. Một pipeline CI/CD, microservice, scheduler hoặc cloud agent có thể dùng:

- OAuth 2.0 `client_credentials`.
- Workload federation/token exchange.
- mTLS/X.509 client certificates.
- Managed identity/cloud role assumption.
- SSH keys, database service authentication.
- Kubernetes service accounts/platform-issued tokens.

### 16.1. Trường cần thay đổi theo principal type

| Human | Workload |
| --- | --- |
| `personId`, `engagementId`, `accountId`. | `workloadId`, `servicePrincipalId`, `ownerTeam`. |
| MFA/passkey/password method. | Certificate, token exchange, client credential, federated assertion. |
| Device/user sign-in context. | Host/node/namespace/runner context khi có. |
| Joiner/Mover/Leaver status. | Deploy/rotate/decommission state, owner transfer. |
| Human session and user authorization. | Service token lifetime, scope, API authorization. |

### 16.2. Không gọi machine token issuance là “nhân viên login”

Một workload có thể tạo hàng nghìn token trong ca. Đếm chúng vào KPI login người dùng gây nhiễu. Cần phân tích **principalType=WORKLOAD**, workload owner, expected cadence, issuer, audience, scope và trust domain riêng.

### 16.3. Credential và vòng đời owner

Khi một kỹ sư Leaver, job có thể vẫn cần hoạt động hợp lệ. **Không giữ account người nghỉ để job chạy tiếp**; chuyển sang workload identity có ownerTeam, secret rotation và least privilege. Authentication logs giúp phát hiện **PAT/service token còn dùng từ tài khoản cá nhân đã Leaver**.

### 16.4. Phát hiện bất thường workload

Những tín hiệu gợi ý:

- Service principal lần đầu truy cập tenant/resource nhạy cảm ngoài baseline.
- Client certificate cũ vẫn được chấp nhận sau revoke.
- Token audience/scope mới không thuộc deployment được duyệt.
- Workload chạy từ môi trường/runner lạ hoặc host bị đánh giá high-risk.
- Một service account có owner đã rời tổ chức mà không chuyển trách nhiệm.

**Không tự coi một thay đổi workload là tấn công** nếu đó là rollout/scale hợp lệ. Tương quan change/deployment context và owner trước khi kết luận.

## 17. Device trust và network context trong log

Authentication log có thể mang **deviceId, MDM compliance, EDR risk, certificateRef, IP, user-agent, VPN/ZTNA context**. Những trường này hữu ích nhưng không tương đương.

| Tín hiệu | Có thể giúp | Không nên suy |
| --- | --- | --- |
| **Source IP/ASN** | Phân tích nguồn mạng, thay đổi vị trí tương đối. | IP là ID thiết bị hoặc vị trí chính xác của con người. |
| **User-Agent** | Nhận biết client loại nào, thay đổi bất thường. | User-agent không thể giả. |
| **Device ID** | Liên kết bản ghi thiết bị nếu nguồn đáng tin. | Client tự khai ID đã xác thực. |
| **MDM compliance** | Posture theo một policy và snapshot. | Không thể có malware hoặc chưa bị mất. |
| **EDR risk** | Tín hiệu bất thường runtime. | Không có alert = chắc chắn an toàn. |
| **mTLS certificate** | Bằng chứng kiểm soát private key được tin. | Người dùng hiện tại được phép hành động. |
| **Geo-IP** | Ước lượng khu vực nguồn mạng. | Vị trí thực tế, đặc biệt khi dùng VPN/proxy. |

### 17.1. Phân biệt nguồn IP gốc và proxy

Nếu hệ thống sau proxy nhận `X-Forwarded-For`, cần xác định proxy nào được tin và có làm sạch header từ client không. Một attacker có thể gửi header giả nếu ứng dụng tin nó trực tiếp; log/source analytics khi đó không còn đáng tin.

### 17.2. Risk thay đổi giữa session

Thiết bị compliant lúc login nhưng EDR báo HIGH_RISK sau 30 phút. Authentication log lúc đầu **không đổi thành false**; nó vẫn phản ánh xác thực đã xảy ra. Cần thêm **device-risk event, session risk change, authorization/resource deny/revoke**, nối bằng session/device reference.

## 18. Detection use cases: từ tín hiệu tới điều tra

Authentication logs là dữ liệu nền tảng cho phát hiện rủi ro, nhưng một **detection rule** cần định nghĩa rõ:

- Tập nguồn và loại principal trong scope.
- Điều kiện, cửa sổ thời gian và threshold có căn cứ.
- Mẫu số/baseline hợp lệ cho nhóm người dùng hoặc workload.
- Những tình huống gây false positives.
- Cách tăng độ tin cậy bằng MFA, session, endpoint, JML và resource evidence.
- Severity, owner, hành động ứng cứu và tiêu chí đóng.

### 18.1. Password spraying

**Password spraying** thường thử một hoặc vài mật khẩu phổ biến trên nhiều account nhằm tránh ngưỡng khóa trên từng account. Dấu hiệu gợi ý:

~~~text
time window = W (ví dụ do đội Detection Engineering cấu hình)
source cluster có nhiều INVALID_CREDENTIAL events
distinct target accounts cao
attempts per target thấp hoặc tăng phân tán
optional: một số account được AUTHENTICATION_SUCCEEDED sau các lần thử
~~~

Không gắn cứng một ngưỡng chung như “10 lỗi = tấn công”. Nhiều người sau password rotation hoặc một proxy egress dùng chung có thể tạo mẫu tương tự. Tương quan **source, target diversity, device, auth methods, risk và user reports**.

### 18.2. Credential stuffing

Credential stuffing là việc thử **các cặp username/password** bị lộ hoặc thu thập ở nơi khác trên dịch vụ đăng nhập. Tín hiệu có thể gồm:

- Nhiều request lỗi trên nhiều account, với phân bố nguồn đa dạng.
- Tỷ lệ success nhỏ nhưng đáng chú ý trong tập attempts lớn.
- User-agent/device fingerprint bất thường (không xem là bằng chứng đơn lẻ).
- Tài khoản bị tấn công có hành động thay mật khẩu/factor hoặc truy cập dữ liệu lạ ngay sau đó.

Tách với password spraying theo **mô hình phân bố attempts, identities, nguồn và kết quả**, không chỉ dựa một trường reason.

### 18.3. Brute-force một tài khoản

Nhiều `INVALID_CREDENTIAL` liên tiếp cho cùng account, có thể qua một hoặc nhiều IP. Cần đánh giá **account lockout, rate limit, MFA challenge, compromised password signals** và khả năng người dùng bị ảnh hưởng. Tránh phản xạ khóa rộng khiến attacker gây **denial of service** cho người dùng hợp lệ.

### 18.4. MFA fatigue / unexpected approval

Chuỗi MFA push DENIED/EXPIRED lặp lại rồi một APPROVED, tiếp theo là login từ thiết bị lạ, có thể cần điều tra. Các yếu tố **number matching, device binding, contextual approval** khi có có thể tăng bảo đảm nhưng không thay bằng chứng người dùng xác nhận.

### 18.5. Impossible travel và anomalous location

Hai login cách xa về Geo-IP trong thời gian ngắn có thể tạo impossible-travel alert. Tuy nhiên, VPN, corporate proxies, mobile roaming, NAT hoặc Geo-IP sai có thể khiến cảnh báo giả. **Không sử dụng geolocation từ IP như bằng chứng chính xác về vị trí vật lý**; kết hợp device/session/network context và user verification.

### 18.6. New device/new authenticator

Một login từ thiết bị chưa thấy hoặc factor mới được đăng ký ngay trước hành động đặc quyền có thể là dấu hiệu rủi ro. Nhưng Joiner, đổi điện thoại hay thay laptop cũng là lý do hợp lệ. Nối với **device enrollment, factor reset approval, asset assignment và JML**.

### 18.7. Token/session misuse

Các tín hiệu:

- Refresh token replay/reuse bị phát hiện bởi issuer.
- Token invalid issuer/audience hoặc session đã revoked vẫn được API chấp nhận.
- Cùng session reference xuất hiện ở hai môi trường client bất tương thích với mô hình session binding.
- Access token được dùng sau Leaver hoặc device LOST.
- Privileged session ngoài JIT/absolute deadline.

Một số tín hiệu này thuộc **token/session logs**, không thể rút ra từ login logs một mình.

### 18.8. Federation trust failures

Nhiều sự kiện `INVALID_SIGNATURE`, `AUDIENCE_MISMATCH` hoặc `UNKNOWN_ISSUER` có thể do cấu hình rotation certificate lỗi hoặc hoạt động đáng ngờ. Cần xem **change window, metadata version, affected SP count và source distribution**; không mặc định mọi SAML/OIDC error là tấn công.

## 19. Ví dụ correlation rule phòng thủ

### 19.1. Quy tắc minh họa Leaver authentication success

~~~text
for each auth event e where:
    e.eventType == AUTHENTICATION_SUCCEEDED
    e.principalType == HUMAN

    identity = correlateToAuthoritativeEngagement(e)
    if identity is unresolved:
        reportIdentityMappingGap(e)
        continue

    if identity.terminationEffectiveAt != null
       and e.eventTime >= identity.terminationEffectiveAt:

        risk = evaluate(
            applicationSensitivity(e.clientId),
            privilegedAccount(e.accountId),
            deviceTrust(e.deviceId),
            subsequentResourceAccess(e.sessionRef),
            knownTerminationPropagationWindow()
        )
        openAlertWithEvidenceAndOwner(e, identity, risk)
~~~

**Đây là giả mã cho SIEM/correlation pipeline**, không phải chương trình chạy trực tiếp. Trong môi trường thật, cần xử lý **event đến muộn, uncertainty trong identity correlation, timestamp skew, app-local users và ngoại lệ được phê duyệt**. Không tự gắn nhãn “lạm dụng đã thành công” khi mới có auth event mà chưa có resource evidence.

### 19.2. Pseudocode phát hiện bất thường MFA

~~~text
for each human account over configured time window:
    challenges = verifiedSourceMfaEvents(account)
    if repeatedDeniedOrExpired(challenges)
       and followedByApproval(challenges):

        correlate:
            authenticated session
            client/device changes
            privileged actions and factor resets
            user-reported suspicious prompts

        prioritize by effective access and asset criticality
        createAlertWithoutStoringRawOtpOrToken()
~~~

### 19.3. Không để detection phụ thuộc một trường tự khai

Nếu một rule dựa toàn bộ vào IP do client gửi trong header không xác thực, attacker có thể làm sai correlation. Dùng **trusted edge/network metadata** hoặc đánh dấu provenance của dữ liệu. Dù source logs đa dạng, luôn biết trường nào là **provider-observed** và trường nào **user-supplied**.

## 20. Thu thập logs: kiến trúc pipeline

~~~mermaid
flowchart TD
    IDP["IdP / Directory / MFA"] --> COL["Collectors / Authenticated ingestion"]
    SSO["OIDC / SAML RPs / SPs"] --> COL
    PAM["PAM / Break-glass"] --> COL
    APP["Applications / APIs / VPN"] --> COL
    M2M["Workload identity / Cloud STS"] --> COL
    COL --> RAW["Protected source events<br/>immutable references"]
    COL --> NORM["Schema validation<br/>normalization + redaction"]
    NORM --> ENR["Identity/JML mapping<br/>device + session + resource context"]
    ENR --> SIEM["SIEM / detection<br/>correlation + alert"]
    SIEM --> IR["Triage / IR / IAM Operations"]
    ENR --> AUD["Auditable query store<br/>retention + controlled access"]
    IR --> FIX["Revoke / containment<br/>readback + verify"]
    FIX --> SIEM
~~~

### 20.1. Các bước

1. **Source onboarding:** lập danh mục IdP, MFA, SP, local auth, PAM và cloud principal được giám sát.
2. **Authenticated transport:** dùng kênh phù hợp, phân quyền producer, chống spoof dữ liệu giữa tenants.
3. **Validation:** schema, event ID, timestamp, source ID, outcome; không bỏ qua error events.
4. **Redaction:** loại secrets/raw headers/PII thừa trước khi nhân bản log.
5. **Normalization:** ánh xạ taxonomy chung mà vẫn giữ reference đến source event.
6. **Enrichment:** nối JML/owner/device/role/app, có timestamp và sourceVersion.
7. **Detection/correlation:** tạo findings với rule version, evidence và uncertainty.
8. **Retention/audit:** bảo vệ integrity, access policy, thời hạn, deletion và truy cập phục vụ kiểm toán.
9. **Incident/feedback loop:** kết quả điều tra dùng để cải tiến rule, mapping và chất lượng nguồn.

### 20.2. Raw và normalized data không được làm mất ngữ nghĩa

Hai provider có thể dùng `success` với ý nghĩa khác nhau: một hệ thống báo **password verified**, hệ khác báo **full flow completed**. Normalize cả hai thành `AUTHENTICATION_SUCCEEDED` sẽ tạo false assurance. Cần lưu `eventStage`, `sourceOutcome` hoặc taxonomy đủ chi tiết, và bản gốc đã bảo vệ khi cần điều tra.

### 20.3. Chống giả sự kiện từ producer

Khi ingestion API chấp nhận log từ nhiều ứng dụng, cần xác thực **log producer identity**, ràng buộc tenant/source và tránh để một service ghi event `IdP_AUTH_SUCCESS` thay cho IdP thật. Log record có chữ ký hoặc transport integrity, source-to-schema permissions và provenance giúp tăng khả năng tin cậy.

## 21. At-least-once delivery, deduplication và event ordering

Pipeline log thường ưu tiên **không mất sự kiện**; vì vậy một event có thể được gửi lại.

### 21.1. Không đếm retry như login mới

Giả sử IdP phát `eventId=E-100`, collector nhận hai lần do retry. Nếu không deduplicate, dashboard có thể đếm **hai lần AUTH_SUCCESS**.

~~~text
deduplication key = sourceSystem + tenantId + providerEventId
if providerEventId absent:
    use a documented fallback with collision/false-dedup risk noted
~~~

Không giả định tất cả vendor luôn có eventId duy nhất; fallback nên rõ phạm vi thời gian và không vô tình gộp hai lần đăng nhập thực.

### 21.2. Event đến muộn

Một MFA_APPROVED có thể đến trước MFA_CHALLENGE_ISSUED do queue và độ trễ. Correlation cần có **windowing, event-time semantics, watermark/late-event policy hoặc cơ chế cập nhật finding**. Không tự đảo nghĩa outcome chỉ vì ingest order lạ.

### 21.3. Khi nguồn tắt hoặc mất log

Nếu IdP outage, SIEM không có login failures không có nghĩa “không ai cố đăng nhập”. Cần phát hiện:

- Producer heartbeat/health và last event time.
- Expected event volume so với traffic/auth activity.
- Connector lag, API polling errors hoặc rate limits.
- Mất trang khi phân trang, thay schema/version.
- Gaps trong một tenant hoặc một nhóm ứng dụng.

**Silence from source không phải bằng chứng absence of attacks**. Ghi tình trạng telemetry degraded/unknown và thông báo tới owner.

## 22. Không ghi thông tin xác thực bí mật vào log

Authentication logging phải bảo đảm **sự kiện có thể điều tra** nhưng không biến log thành nơi tập trung credentials để kẻ tấn công khai thác.

### 22.1. Những dữ liệu tuyệt đối không nên đưa nguyên văn vào log thông thường

- Password đúng hoặc sai, mật khẩu mới/cũ và câu trả lời bảo mật.
- TOTP seed, OTP/SMS code, recovery code hoặc push approval secret.
- Access token, refresh token, ID token, raw session cookie, bearer header.
- OAuth authorization code, `client_secret`, API key/PAT, private key.
- Full SAML assertion, OIDC token response hoặc WebAuthn private credential.
- Raw HTTP `Authorization` hoặc headers chứa credential, kể cả khi login thất bại.
- Recovery links, reset tokens, magic links hoặc email verification tokens.

### 22.2. Log thay thế bằng dữ liệu gì?

| Không ghi | Nên ghi |
| --- | --- |
| Raw access token | Token issuance/reference ID, hash có thiết kế bảo mật phù hợp hoặc `jti` an toàn, issuer/audience/expiry. |
| Raw cookie | Session reference, lifecycle state, createdAt, revocation reason. |
| Password value | Credential verification outcome, reason category. |
| OTP/magic-link content | Challenge/flow reference, factor type và outcome. |
| Private key | Certificate/key metadata reference, fingerprint theo chính sách bảo mật. |
| Full user profile | Stable subject/account reference và attributes tối thiểu được phép. |
| Full sensitive HTTP request | Endpoint/action/response outcome và request trace ID sau redaction. |

**Hash không tự làm một chuỗi trở nên vô hại.** Nếu hash trực tiếp một token có entropy thấp, một địa chỉ email hoặc một secret mà nơi khác có thể quan sát, có thể gây nguy cơ tương quan/ngược tìm kiếm. Việc dùng hashing/HMAC/tokenization phải có threat model, quản lý khóa và chính sách truy cập riêng.

### 22.3. Cẩn thận khi log lỗi

Một exception trong authentication middleware có thể vô tình log toàn bộ request body, headers, query string hoặc callback URL. Trước khi đưa error stack/context vào SIEM, phải:

1. Chỉ định trường cần được log theo **allowlist**.
2. Redact hoặc loại bỏ các trường có khả năng là secret.
3. Xử lý trường lồng nhau, query parameters, exception cause và serialized objects.
4. Kiểm mã nguồn/framework tự động log request/response khi DEBUG.
5. Thử các trường hợp thất bại chứa secret để xác minh log không lộ.

**Chỉ ẩn thông điệp hiển thị cho user là chưa đủ**; secret có thể lọt qua metrics, traces, reverse proxy hoặc audit sink.

## 23. Bảo vệ thông tin cá nhân, retention và quyền xem

Authentication logs có thể tiết lộ **thói quen làm việc, thiết bị, nguồn kết nối, tình trạng account, yếu tố MFA và hoạt động truy cập tài nguyên**. Đây là dữ liệu có rủi ro quyền riêng tư, ngay cả khi không chứa password.

### 23.1. Nguyên tắc quản trị

| Nguyên tắc | Áp dụng vào Authentication logging |
| --- | --- |
| **Purpose limitation** | Dùng cho bảo mật, IAM audit và vận hành đã xác định; không tùy tiện dùng mục đích khác. |
| **Data minimization** | Chỉ giữ trường cần cho phát hiện và truy vết. |
| **Role-based access** | SOC, Identity Ops, Application Owner, Audit có phạm vi xem khác nhau. |
| **Tenant/subject isolation** | Người dùng một tenant không xem log của tenant khác. |
| **Encryption** | Bảo vệ transport và storage, quản lý key access. |
| **Retention/deletion** | Thời hạn theo mục đích, risk tier, policy và nghĩa vụ áp dụng. |
| **Access auditing** | Ghi lại việc truy vấn/export nhạy cảm và thay đổi cấu hình logging. |
| **Integrity preservation** | Phát hiện hành vi sửa/xóa hoặc khoảng trống log. |
| **Controlled sharing** | Dùng pseudonymization/redaction và approval khi export. |

### 23.2. Không có một thời gian lưu giữ universal

Tùy pháp luật, tiêu chuẩn, loại hệ thống và mục đích, tổ chức có thể cần retention khác nhau. Không nên viết “mọi authentication logs phải giữ 90 ngày/1 năm/7 năm” như một quy tắc chung. Hãy xác định:

- **Thời gian truy vấn nhanh (hot)** cho detection/incident.
- **Thời gian lưu dài (cold)** nếu cần điều tra hoặc audit.
- **Legal hold/incident preservation** theo quy trình được phép.
- **Xóa/ẩn danh sau hết mục đích**, kể cả backups và data lake khi thuộc phạm vi.
- **Access logs của chính hệ thống SIEM** để hạn chế lạm dụng dữ liệu.

### 23.3. Geolocation và device fingerprint

Không cần lưu vị trí GPS chính xác của mọi nhân viên chỉ để phát hiện anomalous login. Geo-IP có thể đủ với độ chính xác hạn chế và cần ghi uncertainty. Device fingerprinting có thể mang rủi ro privacy; chỉ dùng tín hiệu có mục đích, hợp pháp và được bảo vệ theo policy.

### 23.4. Phân tầng truy cập báo cáo

- **Executive dashboard:** tỷ lệ, xu hướng, rủi ro tổng hợp, không hiển thị PII chi tiết.
- **Application owner:** sự kiện liên quan app và chủ thể do họ quản lý.
- **Identity/SOC:** có thể drill down theo nhiệm vụ điều tra và quyền được cấp.
- **Internal audit:** đọc bằng chứng cần thiết, không có quyền tự sửa raw logs.
- **Data subject/service owner requests:** xử lý qua quy trình riêng, không cung cấp log ngoài quyền được phép.

## 24. Integrity, tamper detection và chain of custody

Authentication log có giá trị kiểm toán nếu tổ chức có thể chứng minh **event đến từ đâu, không bị sửa trái phép và việc trích xuất/di chuyển có kiểm soát**.

### 24.1. Các biện pháp thường dùng

- **Write-once/append-only controls** hoặc storage có khóa sửa/xóa phù hợp khi cần.
- **Producer authentication** và transport integrity.
- **Separation of duties:** admin ứng dụng không được tự xóa log điều tra của mình.
- **Restricted administrative actions** với audit độc lập cho SIEM/storage.
- **Cryptographic integrity**: hashing/chain/signature khi threat model yêu cầu.
- **Time synchronization** và source/ingest timestamps.
- **Access history** cho search, export, retention override và deletion.
- **Backups/replication** được bảo vệ và kiểm thử khôi phục.
- **Gap detection** khi collector hoặc nguồn ngừng phát log.

### 24.2. Hash chain minh họa

~~~text
eventHash[i] = HASH(
    canonicalEvent[i]
    || eventHash[i-1]
    || sourceIdentity
)
~~~

Một hash chain có thể giúp **phát hiện sửa, xóa hoặc thay thứ tự bản ghi trong chuỗi đã neo tin cậy**, nhưng không tự chứng minh:

- Event gốc do hệ thống nói thật.
- Không có event nào bị bỏ qua trước khi đưa vào chain.
- Timestamp của nguồn chính xác.
- Kẻ kiểm soát cả storage lẫn trust anchor không thể tạo chain mới.

Để bảo đảm mạnh hơn, cần **trusted anchoring, chữ ký/key management, independent copies, kiểm chứng completeness và governance**, tùy yêu cầu.

### 24.3. Chain of custody trong điều tra

Khi log trở thành bằng chứng sự cố, ghi:

1. Nguồn, người/tác vụ thu thập, thời gian và truy vấn.
2. Phạm vi dữ liệu, filter và time window.
3. Kiểm tra integrity/digest tại thời điểm xuất nếu áp dụng.
4. Kho lưu trữ, quyền truy cập và những lần chuyển giao.
5. Sự kiện bổ sung/chỉnh sửa cách diễn giải (không xóa bản gốc).

**Hồ sơ điều tra có thể thay đổi kết luận khi có bằng chứng mới**, nhưng không nên âm thầm thay đổi authentication event gốc để khớp giả thuyết.

## 25. Tính đầy đủ của dữ liệu: inventory nguồn và coverage

Không thể tuyên bố “không có đăng nhập trái phép” nếu nhiều ứng dụng không gửi logs hoặc chỉ gửi event thành công.

### 25.1. Kiểm coverage đa chiều

| Chiều | Câu hỏi |
| --- | --- |
| **Applications** | Mọi ứng dụng thuộc scope có đăng nhập local/SSO được giám sát không? |
| **Identity providers** | Có nhiều IdP, external federation hoặc tenant chưa tích hợp không? |
| **Principal types** | Human, privileged, guest và workload có được tách không? |
| **Event outcomes** | Success, failure, challenge, timeout, provider error và token events có đủ không? |
| **Device/network** | Có những nguồn không cung cấp device context hoặc IP đáng tin không? |
| **Time coverage** | Event collector có hoạt động 24/7 và phát hiện log gaps không? |
| **Authentication paths** | Break-glass, local admin, SSH/RDP/VPN/legacy có bị bỏ sót không? |
| **Lifecycle identity mapping** | Bao nhiêu event ghép được Person/Engagement hoặc owner workload? |
| **Retention** | Dữ liệu còn truy vấn được trong khoảng điều tra cần thiết không? |

### 25.2. “Không có event” có nhiều nghĩa

~~~text
NO_EVENTS_DUE_TO_NO_AUTH_ACTIVITY
NO_EVENTS_DUE_TO_SOURCE_OUTAGE
NO_EVENTS_DUE_TO_COLLECTOR_FAILURE
NO_EVENTS_DUE_TO_FILTER_DROPPED
NO_EVENTS_DUE_TO_RETENTION_EXPIRED
UNKNOWN
~~~

Chỉ trường hợp đầu tiên có thể liên quan **không phát sinh hoạt động**; những trường hợp khác là **data quality/telemetry risk**, không phải bằng chứng an toàn.

### 25.3. Source inventory gợi ý

~~~yaml
# Metadata minh họa, không phải cấu hình SIEM sản phẩm cụ thể.
sourceId: corporate-idp-tenant-a
systemOwner: identity-operations
principalTypes: [HUMAN, SERVICE]
eventTypes:
  - AUTHENTICATION_SUCCEEDED
  - AUTHENTICATION_FAILED
  - MFA_CHALLENGE_ISSUED
  - MFA_VERIFIED
deliveryMode: API_POLLING
schemaVersion: auth-event-v1
expectedHeartbeat: true
sourceTimeZone: UTC
lastDataQualityReview: "2026-12-01"
evidenceHandlingPolicy: identity-audit-v3
~~~

Nếu một nguồn **không hỗ trợ MFA logs**, không tự thêm `MFA_VERIFIED` vào danh sách chỉ để dashboard đầy đủ. Ghi capability gap và biện pháp thay thế đã được đánh giá.

## 26. Error handling và observability của chính pipeline logs

### 26.1. Các lỗi cần cảnh báo

| Tình huống | Tác động | Phản ứng |
| --- | --- | --- |
| **IdP API rate limit** | Log đến muộn hoặc bị bỏ trang. | Backoff, cursor/checkpoint, gap detection. |
| **Collector mất credential** | Không còn lấy dữ liệu. | Owner alert, service credential rotation, health check. |
| **Schema thay đổi** | Event parser drop trường outcome. | Schema version monitoring và quarantine invalid records. |
| **Clock lệch** | Sai thứ tự JML/attack timeline. | Time skew alert, nguồn giờ tin cậy. |
| **Duplicate delivery** | Đếm phình login failures/successes. | Deduplication key có provenance. |
| **Partial outage** | Một tenant không còn logs. | Tenant-level heartbeat/volume detection. |
| **Sensitive field leakage** | Token/PII nằm trong log. | Containment, access limitation, deletion/rotation theo incident process. |
| **Search index lỗi** | SIEM truy vấn thiếu nhưng raw store còn. | Phân biệt ingest success và query availability. |
| **Retention job sai** | Log bị xóa trước policy. | Audit retention controls, restore khi được phép. |
| **Alert engine lỗi** | Có log nhưng không tạo cảnh báo. | Synthetic detections, test rule execution. |

### 26.2. Không để logging làm sập authentication flow

Việc ghi log đồng bộ có thể tăng latency hoặc ảnh hưởng availability. Tuy nhiên, với tác vụ đặc biệt nhạy cảm, **không có khả năng audit bắt buộc** có thể là lý do policy chọn deny hoặc queue an toàn. Cần kiến trúc theo **risk tier**, không một lựa chọn fail-open/fail-closed áp cứng toàn bộ.

Điều quan trọng là **không tự động bỏ qua yêu cầu audit của hành động đặc quyền vì hệ thống log đang lỗi**, và không tuyên bố event đã được lưu chỉ vì code gọi hàm gửi log.

### 26.3. Pipeline monitoring riêng

Nên đo:

- Producer/source availability.
- Transport/ingest delay theo percentile.
- Parse/normalization failure rate.
- Event loss/gap rate dựa nguồn có thể đối soát.
- Duplication rate và false deduplication risk.
- Schema contract test status.
- Sensitive field detection incidents.
- Query/index freshness.
- Retention compliance và access audit.

## 27. Threat model: kẻ tấn công khai thác hoặc né Authentication logging

| Mối đe dọa | Cách thể hiện | Kiểm soát nên xem xét |
| --- | --- | --- |
| **Log tampering/deletion** | Kẻ có admin quyền xóa dấu đăng nhập. | Restricted writes, integrity, independent storage, SoD. |
| **Producer spoofing** | App tự gửi AUTH_SUCCESS giả của IdP. | Authenticated log source, source ID binding. |
| **Missing local path** | Tấn công qua local admin không hiện trong IdP. | Auth-path inventory, app-local logs. |
| **Credential leakage through logs** | Raw token/password bị in trong error trace. | Allowlist logging, redaction, sensitive-field tests. |
| **PII exfiltration from SIEM** | Lạm dụng quyền search/export theo nhân viên. | Least privilege, audit access, masking, retention. |
| **Event flooding** | Gửi lượng lớn log rác làm che alert. | Rate control, prioritization, protected pipeline, sampling policy. |
| **Clock/event ordering manipulation** | Kết luận sai thứ tự hoạt động. | Trusted time, provenance, correlation theo causal IDs. |
| **Tenant crossover** | Log bị gắn sai tenant/người. | Namespace validation và identity source version. |
| **False device context** | Client giả user-agent/IP/header. | Trusted edge data, device proof. |
| **Attacker controls account+MFA** | Login success nhìn “bình thường”. | Risk/behavior/resource telemetry và incident response. |
| **Retention abuse** | Xóa evidence trước khi audit. | Policy-governed deletion và legal-hold workflow. |
| **Telemetry blind spot** | Outage tạo khoảng trống event. | Source heartbeat, backups và exception. |

**Mục tiêu không phải log càng nhiều càng tốt**, mà log **đúng, đủ, đáng tin, truy vết được và giới hạn rủi ro dữ liệu**.

## 28. Runbook điều tra authentication bất thường

### Bước 1 – Xác định finding và phạm vi

Lấy **detectionId/ruleVersion, event IDs, tenant/issuer, time window, affected accounts, principalType và severity**. Kiểm liệu source vẫn hoạt động và dữ liệu có hoàn chỉnh không.

### Bước 2 – Xác minh identity mapping

Đối chiếu **accountId → issuer/subject → Person/Engagement hoặc workload/ownerTeam** từ nguồn có thẩm quyền. Nếu mapping mơ hồ, ghi **UNRESOLVED**; không tự kết luận một cá nhân cụ thể đã thực hiện hành động.

### Bước 3 – Dựng timeline

~~~text
HRIS/IGA lifecycle event
  -> authentication attempt / challenge / final outcome
  -> IdP or SP token/session issuance
  -> resource/API authorization
  -> privilege or account changes
  -> response/revocation and verification
~~~

Dùng **eventTime, effectiveAt, observedAt, ingestedAt**, timezone và correlation references để phân biệt chuyện xảy ra với chuyện được phát hiện.

### Bước 4 – Phân loại nguyên nhân

Xem khả năng:

- Người dùng nhầm mật khẩu hoặc mất MFA device.
- Conditional Access/MDM/EDR policy thay đổi.
- IdP/provider/network outage.
- Legacy client dùng credential cũ.
- Password spraying/credential stuffing.
- Session/token reuse hoặc account takeover.
- Leaver/expired contractor còn đường local.
- Workload credential hoặc automation sai chủ thể.

### Bước 5 – Ưu tiên theo quyền thực tế

Một auth success vào app có dữ liệu nhạy cảm cần ưu tiên cao hơn nhiều login failures bị chặn, nếu ngữ cảnh rủi ro tương đương. Kiểm **PAM activation, role/permission, export/download, factor reset, device risk, token/session ongoing**.

### Bước 6 – Giảm thiểu có thẩm quyền

Theo quy trình Security/IAM có thể:

- Thu hồi session/token family và khóa credential nghi bị lộ.
- Yêu cầu factor reset/re-enrollment có xác minh.
- Hạn chế Conditional Access hoặc device risk.
- Tạm chặn app-local/privileged access và kiểm direct grants.
- Chuyển incident response khi có dấu hiệu xâm nhập.

Không tự thay đổi role, tắt MFA hoặc khóa hàng loạt người dùng chỉ dựa một alert chưa được xác minh.

### Bước 7 – Kiểm chứng khắc phục

Đối soát **IdP, SP, PAM, API gateway/resource**, bảo đảm đường trái policy bị từ chối. `ACCOUNT_DISABLED` hoặc `SCIM_PATCH_204` không tự chứng minh session cũ đã hết quyền.

### Bước 8 – Đóng và học từ sự cố

Ghi root cause, affected scope, evidence gaps, điều chỉnh detection rule, owner và deadline khắc phục. Nếu kết luận false positive, lưu bối cảnh chính đáng để cải tiến rule mà không bỏ luôn kiểm soát.

## 29. Thiết kế báo cáo Authentication logging

Nên có hai lớp báo cáo:

### 29.1. Executive summary

Tập trung:

- Scope các IdP/apps/tenants và principal types được quan sát.
- Xu hướng success/denied/error theo thời gian có denominator.
- Critical findings: privileged, Leaver, emergency, token replay.
- Telemetry gaps, ownerless accounts, local auth paths không kiểm soát.
- Trạng thái incident/remediation và rủi ro chưa được xác minh.

### 29.2. Operational detail

Lọc/tương quan theo:

| Bộ lọc | Mục đích |
| --- | --- |
| **Time range/asOf** | Dựng timeline nhất quán. |
| **Tenant/issuer/source** | Tránh nhầm namespace. |
| **Principal type** | Tách human/workload/guest/privileged. |
| **Event type/outcome/reason** | Chẩn đoán đúng giai đoạn thất bại. |
| **Client/application** | Xác định nơi đăng nhập và SP. |
| **Auth method/factor** | Đánh giá assurance/MFA và policy. |
| **Account/Person/Engagement** | Liên kết JML. |
| **Device/session/token reference** | Truy vết session và risk. |
| **Risk/detection IDs** | Điều tra findings và kết quả ứng cứu. |
| **Source freshness/coverage** | Không hiểu log thiếu là không có hoạt động. |

### 29.3. Một báo cáo không được làm lộ bí mật

Bảng xuất CSV/XLSX cần bảo vệ dữ liệu nhạy cảm và **formula injection** từ các trường có thể do client kiểm soát, ví dụ user-agent, username hoặc error text chứa chuỗi bắt đầu bằng `=`, `+`, `-`, `@`. Dùng export có kiểm kiểu dữ liệu/escaping phù hợp, thay vì để spreadsheet tự thực thi công thức từ log.

Không đính kèm raw JWT, session cookie, MFA OTP hoặc full SAML assertions để người đọc “đối chiếu nhanh”.

## 30. Case study 1 – Password spraying bị che bởi IP dùng chung

**Bối cảnh giả định:** một tổ chức phát hiện hàng trăm lần xác thực mật khẩu thất bại trong 15 phút. Tất cả request có vẻ xuất phát từ cùng một IP egress của VPN công ty, trong khi người dùng vừa phải thay mật khẩu sau một đợt rotation.

### 30.1. Bằng chứng ban đầu

| Quan sát | Có thể cho thấy | Chưa chứng minh |
| --- | --- | --- |
| Nhiều `INVALID_CREDENTIAL`. | Hệ thống đang nhận nhiều thử mật khẩu không đúng. | Tất cả do attacker thực hiện. |
| Nhiều account đích. | Dạng phân tán có thể phù hợp spraying. | Chắc chắn cùng một tác nhân. |
| Một IP egress. | Nhiều request đi qua một điểm mạng. | Một thiết bị duy nhất. |
| Vừa có password rotation. | Có thể gây credential cũ trong ứng dụng/automation. | Mọi failure đều là lỗi vận hành. |
| Một account cuối cùng thành công. | Có một authentication success cần phân tích. | Thành công đó thuộc cùng nguồn thử hoặc user bị chiếm. |

### 30.2. Quy trình điều tra

1. Tách events theo **principalType, clientId, authMethod, outcome, account cohort**.
2. Kiểm nguồn IP từ gateway **trusted proxy metadata**, không tin user-supplied headers.
3. Đối chiếu thiết bị/agent, application và request rates; xem có legacy clients dùng credential cũ.
4. Nối final `AUTHENTICATION_SUCCEEDED` với flow, MFA, device/session và resource actions.
5. Kiểm account lockout, user reports và telemetry nguồn khác.
6. Nếu còn nghi vấn, giảm thiểu theo incident process; tránh khóa toàn doanh nghiệp bằng một rule thiếu ngữ cảnh.

### 30.3. Kết luận minh họa

Giả sử phần lớn failures đến từ các desktop clients chưa cập nhật mật khẩu, nhưng vẫn có một nhóm attempts từ nguồn Internet chưa xác định đi vào cùng cổng reverse proxy. **Không gộp hai nhóm thành một nguyên nhân duy nhất**. Báo cáo nên phân loại **operational login failures** và **suspected spraying** với từng tập bằng chứng, confidence và owner riêng.

### 30.4. Bài học

Detection dựa vào `failedCount` và một IP đơn lẻ dễ tạo false positives/false negatives. **Độ đa dạng account, nguồn đáng tin, flow outcomes và bối cảnh thay đổi hệ thống** giúp giải thích đúng.

## 31. Case study 2 – IdP success nhưng người Leaver còn phiên SaaS

**Bối cảnh giả định:** nhân viên Mai kết thúc hợp đồng lúc 11:00. IdP đã chặn sign-in mới, SCIM User `active=false` ở SaaS nhưng phiên ứng dụng tạo từ 09:00 vẫn dùng được tới 12:00.

### 31.1. Dòng thời gian

| Mốc giả định | Sự kiện | Cần hiểu gì? |
| --- | --- | --- |
| **09:00** | IdP `AUTHENTICATION_SUCCEEDED`. | Mai đăng nhập khi engagement còn ACTIVE. |
| **09:01** | SaaS `SESSION_CREATED`. | Có local session ở SaaS. |
| **11:00** | HRIS Leaver effectiveAt. | Tư cách truy cập đã thay đổi. |
| **11:02** | IdP `ACCOUNT_DISABLED`. | Chặn đăng nhập mới qua IdP. |
| **11:03** | SCIM PATCH success. | Provider nhận cập nhật; không tự chứng minh session bị hủy. |
| **11:10** | SaaS API `RESOURCE_ACCESS_ALLOWED` bằng session cũ. | **Confirmed residual access** nếu không hợp lệ theo policy. |
| **11:14** | App owner revoke local session. | Lệnh thu hồi, chưa nhất thiết verified. |
| **11:16** | SaaS API kiểm tra lại và trả DENY. | Bằng chứng giới hạn thực tế đã được xử lý. |

### 31.2. Sự thật quan trọng

Nếu chỉ nhìn IdP authentication logs sau 11:00, hệ thống có thể thấy **không có login success mới** và kết luận sai “Leaver không còn truy cập”. Nhưng quyền API đã hoạt động qua **local session**, không cần login mới.

### 31.3. Quyết định đúng

- Ghi cửa sổ truy cập tồn dư 11:00–11:16 theo evidence được quan sát.
- Kiểm các action/dữ liệu được truy cập từ 11:00 tới lúc chặn.
- Đánh giá các SaaS app-local sessions/token khác trong scope.
- Cải thiện event-driven session revocation, không dựa chỉ vào SCIM User state.
- Lưu remediation/verifiedAt và findings để đo SLA, không xóa lịch sử.

### 31.4. Bài học

**Authentication logs là điểm khởi đầu cho điều tra, không phải bằng chứng đủ để khẳng định mọi quyền thực tế đã mất.** Cần kết hợp lifecycle, session, provisioning và resource access.

## 32. Case study 3 – MFA fatigue dẫn tới privileged session

**Bối cảnh giả định:** một nhân viên nhận nhiều push MFA mà họ không chủ động yêu cầu. Trong 20 phút, log có 12 challenges bị từ chối/hết hạn, sau đó một challenge APPROVED và một session thành công truy cập PAM.

### 32.1. Chuỗi sự kiện giả định

~~~text
14:00-14:18  12 x MFA_DENIED/MFA_EXPIRED
14:19        MFA_VERIFIED for flow-8801
14:19        AUTHENTICATION_SUCCEEDED
14:20        PAM_SESSION_STARTED
14:21        PRIVILEGED_ROLE_ACTIVATED
14:24        Production IAM policy change requested
~~~

### 32.2. Điều tra phải phân biệt

| Câu hỏi | Bằng chứng |
| --- | --- |
| User đã tự đăng nhập hay bị spam push? | User verification qua quy trình được phép, auth flow, source/device. |
| Factor approve có thật không? | MFA provider verified event, assurance và account binding. |
| Login dùng client/device lạ? | Trusted device/MDM/EDR/risk evidence. |
| Quyền admin có được phê duyệt hợp lệ? | PAM approval, JIT policy, SoD và current authority. |
| Đã có hành động gây hại? | Resource/API audit, config changes, session trace. |
| Có yếu tố bị chiếm hoặc thêm factor trái phép? | Factor enrollment/reset history. |

### 32.3. Phản ứng gợi ý

Nếu có dấu hiệu session compromise, phối hợp IAM/Security để **revoke sessions/token families, bảo vệ tài khoản, xác minh factor và kiểm tác động các thay đổi đặc quyền**, theo incident policy. Không đơn thuần gán kết quả “MFA PASS” rồi bỏ qua chuỗi challenge bất thường.

### 32.4. Bài học

Một `AUTHENTICATION_SUCCEEDED` phản ánh **provider đã chấp nhận luồng**; khi có bất thường trước/sau đó, cần đánh giá tính chính đáng của hoạt động chứ không coi success là kết luận cuối.

## 33. Case study 4 – Workload credential của người đã nghỉ vẫn được dùng

**Bối cảnh giả định:** một batch job sử dụng PAT tạo bởi kỹ sư Bình. Bình Leaver ngày 01/12 nhưng script vẫn chạy, gọi API mỗi đêm. IdP không thấy login người dùng mới, nên dashboard chỉ dựa login human không cảnh báo.

### 33.1. Dấu vết đúng cần nối

~~~text
HRIS Leaver: Person Bình, effectiveAt
    -> IAM account + PAT inventory
    -> tokenRef / principal owner metadata
    -> nightly API authentication/authorization events
    -> resource actions
    -> secret rotation / workload migration
    -> actual denial of old token
~~~

### 33.2. Sai lầm cần tránh

- Chỉ đếm đăng nhập interactive và bỏ API key/PAT.
- Gắn service job là “Bình đăng nhập mỗi đêm” dù **không có user interaction**.
- Giữ account Bình ACTIVE để tránh batch job ngừng.
- Thu hồi PAT mà không thiết kế workload identity thay thế, khiến job quan trọng bị gián đoạn không có kế hoạch.
- Ghi raw PAT vào log/ticket để chứng minh “đã dùng token nào”.

### 33.3. Xử lý và cải tiến

Chuyển job sang **service/workload principal có ownerTeam**, cấp scope tối thiểu, rotate/revoke PAT cũ, kiểm API từ chối credential đã thu hồi và bổ sung detection cho **credential use after owner termination**. Tách **workload login/event** khỏi human interactive log nhưng giữ liên kết owner.

### 33.4. Bài học

**Không có login mới không đồng nghĩa không có truy cập**. Authentication logging trong IAM phải bao phủ cả service identities và API credentials, với mô hình trách nhiệm và vòng đời khác con người.

## 34. Case study 5 – Authentication log bị thiếu do provider outage

**Bối cảnh giả định:** SIEM dashboard không ghi nhận lần đăng nhập thất bại nào trong hai giờ, trùng lúc IdP API collector bị lỗi 429 và một số events bị chậm.

### 34.1. Kết luận sai

> “Không còn password spraying vì số login thất bại về 0.”

### 34.2. Kết luận có căn cứ

“Từ 02:00–04:00, nguồn IdP authentication telemetry **degraded** do collector rate limit. Không thể kết luận không có attempts. Cần khôi phục checkpoint/cursor, đối soát event counts với nguồn, đánh giá data loss và dùng các nguồn VPN/proxy/app logs thay thế trong phạm vi đáng tin.”

### 34.3. Bài học

**Data availability và event absence phải được phân biệt.** Nếu pipeline không phát hiện source outage, một dashboard ít cảnh báo có thể mang lại cảm giác an toàn sai.

## 35. KPI cho Authentication logging

| KPI | Cách tính/định nghĩa gợi ý | Lưu ý diễn giải |
| --- | --- | --- |
| **Authentication source coverage** | Nguồn login trong scope đã gửi logs ÷ toàn bộ nguồn bắt buộc. | Phải có inventory độc lập. |
| **Event coverage by principal type** | Human/guest/admin/workload được giám sát ÷ tổng population trong scope. | Không gộp máy với người. |
| **Final flow completion** | Auth flows có terminal outcome ÷ flows bắt đầu có đủ thời gian kết thúc. | Tránh coi in-progress/late event là failure. |
| **Authentication success rate** | Final successful flows ÷ final completed flows trong scope. | Không cộng MFA steps như login mới. |
| **Failure/deny rate** | Final denies ÷ final completed flows trong scope. | Cao có thể do outage, policy đúng hoặc tấn công. |
| **MFA evidence coverage** | High-risk logins có factor verification evidence ÷ login cần MFA. | Challenge sent không tính verified. |
| **Privileged auth monitoring coverage** | Đường privileged auth đã onboard ÷ tổng đường theo inventory. | Bỏ local admin tạo điểm mù. |
| **Leaver authentication anomalies** | Login/auth success sau termination effectiveAt được xác minh. | Cần Person–Engagement mapping và timestamp. |
| **Post-Leaver effective access** | Resource access được phép sau termination trái policy. | Không suy từ auth log đơn lẻ. |
| **Identity correlation coverage** | Events map được principal đáng tin ÷ events cần mapping. | UNKNOWN phải báo riêng. |
| **Log ingestion latency p50/p95** | `ingestedAt - eventTime` khi clock đáng tin. | Nêu clock skew và sample population. |
| **Source outage/gap duration** | Tổng thời gian nguồn không có dữ liệu tin cậy. | Không nhầm với không có hoạt động. |
| **Duplicate event rate** | Bản ghi duplicate có thể nhận diện ÷ raw records. | Cần cân bằng dedup và giữ audit. |
| **Detection time to triage** | Alert created → owner acknowledged. | Đánh giá năng lực phản ứng. |
| **False-positive rate** | Findings được điều tra là không đúng ÷ findings đủ kết luận. | Không tính UNKNOWN thành false positive. |
| **Log secret leakage incidents** | Các trường hợp lộ credential qua pipeline. | Mức rủi ro nghiêm trọng dù số nhỏ. |
| **Retention/access compliance** | Dataset và truy cập đáp ứng policy ÷ dataset kiểm được. | Cần scope và evidence. |
| **Effective revocation verification** | Đường quyền cần revoke có evidence bị từ chối ÷ đường bắt buộc. | Provider ACK không thay readback. |

### 35.1. KPI không được gộp các mẫu số khác nhau

Một người login 1 lần nhưng dùng 10 access tokens, 15 API requests và 2 MFA challenges. Nếu cộng lại thành 28 “authentication attempts”, tỷ lệ sẽ vô nghĩa. Nên dùng đơn vị rõ:

~~~text
Auth flow      = một quá trình xác thực có ID riêng.
Auth step      = một bước password/MFA/WebAuthn trong flow.
Session        = một trạng thái phiên ứng dụng/IdP.
Token event    = một lần token issued/refresh/revoked.
Resource call  = một request API có authorization decision.
Person/account = chủ thể/định danh liên kết trong namespace.
~~~

### 35.2. Dashboard giả định

~~~text
IDENTITY AUTHENTICATION LOGGING – EXAMPLE
As-of: 2026-12-01 10:00 +07:00
Scope: Workforce IdP tenant-a + 8 applications + PAM

Known authentication paths in scope: 25
Integrated sources: 23
Source coverage: 23 / 25 = 92%

Final auth flows observed: 12,000
  SUCCESS: 10,800
  DENIED:   1,050
  ERROR:      150

Auth success rate: 10,800 / 12,000 = 90%

Unresolved subject mapping among observed final flows: 180
Source gaps: 2 (local admin path + external partner gateway)
High-risk auth findings open: 7
Post-Leaver resource access confirmed: 1

Priority actions:
  - Onboard the two missing authentication paths.
  - Investigate the confirmed post-Leaver access.
  - Resolve identity mapping gaps by authoritative sources.
  - Validate privileged/MFA and session enforcement coverage.
~~~

**Số liệu hoàn toàn giả định**. `12,000` là số final flows **đã quan sát được trong phạm vi nguồn tích hợp**, không phải mọi login của doanh nghiệp. Source coverage 92% không chứng minh 92% từng kiểu event hay request được thu thập.

## 36. Kiểm thử Authentication logging end-to-end

### 36.1. Mục tiêu

Kiểm không chỉ “log file có dòng” mà là:

1. **Nguồn xác thực thực sự tạo event đúng giai đoạn và outcome.**
2. **Collector nhận đủ, không lọt secrets.**
3. **Normalization giữ đúng ngữ nghĩa và không đếm trùng.**
4. **Correlation nối đúng subject/tenant/session.**
5. **Detection chạy và cảnh báo đến owner.**
6. **Audit/retrieval và retention hoạt động theo policy.**

### 36.2. Ma trận test gợi ý

| ID | Kịch bản trong môi trường được phép | Expected |
| --- | --- | --- |
| **LOG-01** | User hợp lệ đăng nhập thành công. | Một final success event, có issuer, subject, flow. |
| **LOG-02** | Password sai. | Auth failure reason đúng, **không log password**. |
| **LOG-03** | MFA challenge gửi nhưng user không approve. | Challenge issued + timeout/deny, không có final success giả. |
| **LOG-04** | MFA verified rồi final auth success. | Các bước gắn cùng flow, không đếm thành nhiều login. |
| **LOG-05** | WebAuthn/passkey assertion thất bại. | Method/reason log đúng, không lưu secret. |
| **LOG-06** | Device noncompliant bị Conditional Access deny. | Deny reason/policy/deviceRef, không ghi sai invalid password. |
| **LOG-07** | OIDC RP từ chối ID token do audience mismatch. | IdP/RP outcomes riêng, lỗi federation trace được. |
| **LOG-08** | SAML SP từ chối assertion vì signature. | Source/issuer/SP log và reason đúng, không log raw assertion. |
| **LOG-09** | Local app admin sign-in ngoài SSO. | Có nguồn log riêng, không mất vì IdP không thấy. |
| **LOG-10** | Break-glass dùng trong diễn tập được duyệt. | Actor/incident/session/alert/review references đầy đủ. |
| **LOG-11** | Workload dùng client credentials. | PrincipalType=WORKLOAD, ownerTeam, không tính human login. |
| **LOG-12** | Mover còn token role cũ. | Auth success và authorization denial/use tách đúng, link JML. |
| **LOG-13** | Leaver attempt bị từ chối. | Chặn đúng, có source effectiveAt/correlation. |
| **LOG-14** | Leaver local session được API cho phép. | Detection nối JML+session+PEP, không chỉ IdP. |
| **LOG-15** | Một provider event gửi trùng vì retry. | Dedup để báo cáo, giữ source audit reference. |
| **LOG-16** | Event đến muộn hoặc lệch ingest order. | Timeline dùng event/effective time, có late-event handling. |
| **LOG-17** | MDM/source log thiếu một tenant. | Coverage gap/heartbeat cảnh báo, không ghi 0 attacks. |
| **LOG-18** | Collector bị 429 hoặc credential expired. | Error/lag monitor và retry/checkpoint an toàn. |
| **LOG-19** | Client gửi `X-Forwarded-For` giả. | Không coi raw header là verified source IP. |
| **LOG-20** | HTTP request chứa raw Authorization header khi auth fail. | Token/header không xuất hiện trong log, trace hoặc export. |
| **LOG-21** | Source cố giả tenant/source ID khác. | Ingestion từ chối hoặc cách ly bởi source binding. |
| **LOG-22** | Người dùng được xem dashboard executive. | Chỉ thấy summary/đúng tenant; không lộ PII chi tiết. |
| **LOG-23** | SOC export log sau khi được cấp quyền. | Có audit export, redaction và retention đúng. |
| **LOG-24** | Collector/SIEM admin thử xóa event mà thiếu quyền. | Access deny và audit tamper attempt. |
| **LOG-25** | Một authentication source outage. | Alert source gap đúng; detection report có giới hạn. |
| **LOG-26** | Login success, resource API denied do thiếu role. | Không ghi nhầm thành authentication failure. |
| **LOG-27** | Refresh token sau login. | Token event, không thêm final human login. |
| **LOG-28** | Session hết absolute timeout nhưng API vẫn nhận token. | Authentication/session/resource logs giúp phát hiện violation. |
| **LOG-29** | Rehire cùng email nhưng Engagement mới. | Không gắn session cũ sang E2. |
| **LOG-30** | User-agent/error text bắt đầu bằng công thức khi export CSV. | Không thực thi formula injection trong bảng tính. |

### 36.3. Kiểm quality bằng bất biến

~~~text
finalAuthFlows = finalSuccess + finalDenied + finalError + otherTerminal
completedFlowCount <= distinctStartedFlowCount + documentedImportedFlows
noRawSecretsFoundInApprovedLogFields
eventId is unique within declared source/tenant namespace
eventTime and ingestedAt are present and parseable
issuer + subject is correctly namespaced for OIDC
noHumanMfaClaimForMachineClientCredentials
sourceHealthGap cannot be treated as zero authentication activity
Leaver review uses termination effectiveAt, not only ingestion order
~~~

Đây là **data invariants minh họa**. Một hệ thống có thể thiếu `FLOW_STARTED` do sampling/retention; khi đó phải ghi exception thay vì bỏ qua bất biến hoặc tự tạo final events.

### 36.4. Test fixtures và cleanup

Dùng account/test tenant, device, workload, certificate và user giả có owner. Không thử mật khẩu thật của người khác, không tổ chức password spraying trên production để kiểm SIEM. Có thể **inject synthetic events có đánh dấu rõ** hoặc chạy negative login tests có ủy quyền trong staging. Test cleanup credentials/sessions và xóa dữ liệu giả theo policy.

## 37. Operating model: ai sở hữu Authentication logs?

Một nguồn auth log có thể do Identity Ops quản lý, nhưng nhiều nhóm phải cùng bảo đảm ý nghĩa và sử dụng đúng.

| Vai trò | Trách nhiệm |
| --- | --- |
| **IAM/IdP owner** | Định nghĩa event semantics từ IdP, account/JML mapping và log nguồn. |
| **Application/SP owner** | Cung cấp local/federation login, session và authorization references. |
| **MFA/Endpoint owner** | Factor, device posture, telemetry availability và trust provenance. |
| **PAM/Privileged access owner** | Privileged logins, elevation, break-glass và session evidence. |
| **Workload/cloud owner** | Service principal, issuer, credential lifecycle và ownerTeam. |
| **SOC/Detection Engineering** | Use cases, correlation rules, triage, incident evidence. |
| **SIEM/Data Engineering** | Ingestion, normalization, schema, dedup, retention, completeness. |
| **HR/JML owner** | Person/Engagement effectiveAt và trạng thái có thẩm quyền. |
| **Risk/Compliance/Privacy** | Retention, lawful purpose, hạn chế quyền xem, dữ liệu nhạy cảm. |
| **Internal Audit** | Kiểm tính đầy đủ, integrity và evidence control không sửa thay dữ liệu gốc. |

### 37.1. Thiết lập hợp đồng nguồn (logging contract)

Mỗi nguồn nên có:

- `sourceId`, namespace/tenant và owner.
- Những **event types** cung cấp, ý nghĩa thành công/thất bại.
- **Schema version**, mapping/transform rules và raw provenance.
- Trường bắt buộc, chính sách secrets/PII và cách redaction.
- Timestamp semantics, timezone và độ trễ chấp nhận.
- Delivery semantics, checkpoint/dedup key và replay behavior.
- Retention/availability và quy trình change notification.
- Cách thử nguồn: synthetic auth events, health checks, alert tests.

### 37.2. Thay đổi IdP hoặc ứng dụng là thay đổi logging

Khi nâng phiên bản IdP, đổi MFA provider, kết nối SSO, migrate LDAP, sửa chính sách login hoặc thay role catalog, phải đánh giá **event types/fields có đổi không**. Một trường `loginOutcome` đổi từ `SUCCESS` thành `COMPLETED` mà parser chưa cập nhật có thể tạo khoảng trống giám sát.

### 37.3. Điều tra không được sửa log nguồn

SOC/IAM có thể thêm **case notes, normalized correction, identity mapping updates hoặc updated findings**, nhưng phải giữ **source event và lineage**. Chỉnh kết luận sau khi có bằng chứng mới là hợp lệ; ghi đè log cũ hoặc xóa dấu vết sai lệch là không phù hợp.

## 38. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| **“Login success” = user có quyền truy cập mọi dữ liệu** | Bỏ authorization/SoD. | Nối auth với PEP/resource logs. |
| **“Không có login” = không có truy cập** | Bỏ session/token/API key cũ. | Ghép session/token/resource evidence. |
| **Mọi MFA step đều được tính một login** | Tỷ lệ success/failure sai. | Đếm final auth flow có key duy nhất. |
| **Push sent = MFA verified** | Assurance bị khai cao hơn thực tế. | Tách challenge issued/delivered/verified. |
| **Mọi failure đều là brute force** | Nhiều false positives và khóa nhầm user. | Reason taxonomy và bối cảnh vận hành. |
| **Chỉ thu IdP logs** | Bỏ app-local admin, break-glass, workload. | Inventory mọi auth paths. |
| **Dùng email/IP làm identity key** | Nhầm Person, device, tenant hoặc rehire. | Issuer+subject, stable IDs và mapping đáng tin. |
| **Quên sourceVersion/effectiveAt của HRIS** | Sai kết luận trước/sau Leaver. | Event time và authoritative history. |
| **Đếm retry là login mới** | Metrics/detection phình. | Dedup theo source namespace + providerEventId. |
| **Gộp password verified với final auth success** | MFA-bypass giả hoặc đo lường sai. | Event granularity rõ. |
| **Tin X-Forwarded-For từ client** | Sai nguồn IP, risk analysis bị điều khiển. | Trusted edge metadata. |
| **Log raw request khi lỗi** | Lộ password/token/OTP trong SIEM. | Allowlist fields và redaction tests. |
| **Giữ tất cả dữ liệu vô thời hạn** | Rủi ro privacy/chi phí/vi phạm policy. | Retention theo mục đích, deletion controls. |
| **Admin ứng dụng có thể xóa audit** | Dấu vết có thể bị che. | SoD, append-only/immutable controls, audit integrity. |
| **Source outage làm dashboard giảm alert** | False assurance khi không có telemetry. | Source heartbeat, lag/gap detection. |
| **SCIM 204 = không còn session** | Quyền tồn dư sau Leaver. | Resource/session verification. |
| **IdP login success = SAML/OIDC SP đã login** | Bỏ federation validation errors. | Correlate IdP and SP acceptance. |
| **Thấy event MFA approved là không thể bị chiếm** | Bỏ MFA fatigue/social engineering. | Kết hợp context và incident evidence. |
| **Gộp workload login với human login** | Dashboard nhiễu, phát hiện sai. | PrincipalType và workload baseline. |
| **Báo 100% coverage từ những nguồn đã onboard** | Bỏ nguồn chưa tích hợp khỏi mẫu số. | Inventory độc lập và unknown paths. |
| **Export raw log sang CSV không kiểm giá trị** | PII exposure hoặc formula injection. | Safe export, type control, masking. |
| **Xóa raw event khi đổi normalization** | Mất khả năng tái điều tra. | Event lineage và versioned corrections. |

## 39. Checklist triển khai Authentication logging

### 39.1. Phạm vi và ngữ nghĩa

1. Đã có **inventory đầy đủ các đường xác thực**: IdP, SP/RP, local apps, PAM, VPN, OS, workload và emergency chưa?
2. Mỗi nguồn có **owner, issuer/tenant namespace, event types và hợp đồng schema** không?
3. Có phân biệt **authentication, authorization, session/token, provisioning và resource access** không?
4. Có tách **flow started, primary verified, MFA challenge/verified, final success/failure** không?
5. Có tách **human, guest, privileged, service/workload** trong principalType không?
6. Các mã `reasonCategory` có phân biệt **invalid credential, account disabled, MFA, conditional access, federation error, provider outage** không?
7. Có ghi **policy version, provider outcome, source event ID và audit references** khi cần không?
8. Các event không có kết quả cuối có được xử lý **UNKNOWN/ABANDONED/TIMED_OUT** đúng semantics không?

### 39.2. Danh tính và tương quan

9. Có liên kết **issuer+subject/accountId** với Person/Engagement từ nguồn đáng tin thay vì chỉ email không?
10. Mover/Rehire có giữ **lịch sử Engagement**, tránh dùng role/sessions cũ sai ngữ cảnh không?
11. Device ID, IP, user agent và Geo-IP có được ghi **provenance/uncertainty**, không giả thành ID chắc chắn không?
12. Auth flow có `authFlowId/requestId/traceId` để nối IdP, MFA, RP/SP và session không?
13. OIDC/SAML có log **assertion/token validation outcome** mà không lộ raw assertion/token không?
14. Có nối được **session/token family ↔ API/PEP authorization** để đánh giá quyền thực tế không?
15. Workload identity có **service principal/ownerTeam, issuer, scope và credential reference** riêng không?
16. Các local/unknown accounts không mapping được có được ghi **UNRESOLVED và owner xử lý** không?

### 39.3. Joiner–Mover–Leaver, đặc quyền và phát hiện

17. Có phát hiện **login success trước Start date hoặc sau End date** theo policy và authoritative effectiveAt không?
18. Có kiểm **Mover role/token claims cũ** với authorization thực tế, không chỉ auth success không?
19. Có đối chiếu Leaver với **IdP disable, SCIM, app-local session, PAM và API keys** không?
20. Các hoạt động **break-glass/privileged sign-in** có alert, named actor hoặc attribution gap và hậu kiểm không?
21. Có các use cases như **password spraying, credential stuffing, MFA fatigue, impossible travel, token replay, unknown issuer** không?
22. Rules có **false-positive conditions, owner, severity, version, triage actions và kiểm thử** không?
23. Có phân biệt **failed attempts đã bị chặn** với **confirmed effective unauthorized access** không?
24. Có kiểm credential của **workload còn dùng sau khi owner Leaver**, theo owner/policy không?

### 39.4. Dữ liệu nhạy cảm và kiểm toán

25. Có chặn log **password, OTP, raw JWT, refresh token, cookie, authorization code, private key, PAT, secret** không?
26. Exceptions/errors/traces có dùng **allowlist redaction** và test khi thất bại không?
27. Có bảo vệ **transport, ingestion producer identity, storage, search/export và tenant isolation** không?
28. Retention/backup/deletion/legal hold có tuân theo mục đích và nghĩa vụ áp dụng không?
29. Log có **integrity controls, audit access và SoD** giữa người dùng đặc quyền với người quản lý evidence không?
30. Export CSV/XLSX có bảo vệ **formula injection/PII**, không cho user strings chạy như công thức không?
31. Khi có incident, có **evidence lineage và chain of custody** phù hợp không?

### 39.5. Pipeline và đo lường

32. Có tách `eventTime, observedAt, ingestedAt` và kiểm clock skew/timezone không?
33. Có xử lý **duplicates, retries, out-of-order và late events** mà không gộp sai nhiều auth flows không?
34. Có monitor **producer heartbeat, rate limits, cursor/checkpoint, parse errors và nguồn thiếu dữ liệu** không?
35. Có các metrics **source coverage từ inventory độc lập, final-flow counts, MFA evidence, identity mapping, ingestion delay, privileged coverage** không?
36. Có **test IdP/RP/SP/SCIM/PAM/Workload/Local** để bảo đảm đủ log theo scope không?
37. Có đo **auth success vs API resource allow** tách biệt để không suy sai về quyền không?
38. Có thực hiện **controlled synthetic tests** cho alert rules và xác minh incident route không?
39. Có khai báo những **unverifiable authentication paths hoặc source outages** trong dashboard không?
40. Trước phát hành, owner có xác nhận **policy, schema, mẫu số, phạm vi, dữ liệu và giới hạn kết luận** chưa?

## 40. Kết luận: Authentication log là bằng chứng xác thực, không phải toàn bộ câu chuyện quyền truy cập

Một hệ thống Identity logging hữu ích phải giữ được chuỗi:

~~~text
AUTHORITATIVE IDENTITY CONTEXT
    Person/Engagement hoặc Workload + Owner + Tenant
                         ↓
AUTHENTICATION EVIDENCE
    Source + Flow + Method/MFA + Outcome + Time
                         ↓
FEDERATION / SESSION / TOKEN LINEAGE
    IdP/SSO → RP/SP → Session → Token family
                         ↓
AUTHORIZATION AND EFFECTIVE ACCESS
    Role + Resource + Action + API/PEP decision
                         ↓
RISK DETECTION AND JML RECONCILIATION
    Joiner–Mover–Leaver + Device + PAM + Credential
                         ↓
INTEGRITY, RETENTION, PRIVACY AND RESPONSE
    Protected evidence + Owner + Alert + Verification
~~~

**Ghi nhớ:** **Authentication log ghi bằng chứng về hoạt động xác thực và các bước của nó, không tự chứng minh chủ thể đã được phép thực hiện mọi hành động hoặc mọi phiên đã bị thu hồi**. Hãy phân biệt **authentication success/failure, MFA challenge, federation acceptance, session/token lifecycle, provisioning và resource authorization**; liên kết chúng bằng **issuer/tenant, stable subject IDs, Person/Engagement hoặc workload owner, flow/session references và thời gian có nguồn gốc rõ**. Để bảo vệ mô hình **Joiner–Mover–Leaver**, log phải giúp phát hiện **đăng nhập ngoài hiệu lực quan hệ, quyền cũ còn dùng, hoạt động tài khoản đặc quyền, token/service credential tồn dư**. Hệ thống ghi log đáng tin cần **coverage đầy đủ, schema đúng, chống đếm trùng, phát hiện nguồn gián đoạn, không lộ bí mật, có integrity/retention và kiểm chứng tác động ở ứng dụng/API đích**. Khi đó logging không chỉ phục vụ báo cáo mà còn giúp **phát hiện, điều tra và đóng vòng khắc phục quyền truy cập thực tế**.
