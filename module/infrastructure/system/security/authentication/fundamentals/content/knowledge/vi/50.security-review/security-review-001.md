# Authentication threat review — Đánh giá mối đe dọa cho hệ thống xác thực

> **Chương:** Security review  
> **Chủ đề:** Authentication threat review  
> **Phạm vi:** Security Authentication Fundamentals — phương pháp đánh giá có hệ thống các mối đe dọa đối với credential, password, MFA, passkey, certificate, token, session, federation, account recovery và service identity; xác định trust boundary, abuse case, rủi ro, kiểm soát và bằng chứng kiểm thử.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định phạm vi, tài sản, chủ thể, entry point và trust boundary của authentication system.
2. Mô hình hóa luồng đăng nhập, token issuance, session, federation và recovery.
3. Phân tích threat bằng STRIDE, abuse case và attacker goal mà không phụ thuộc máy móc vào một framework.
4. Đánh giá rủi ro theo likelihood, impact, exposure, privilege và confidence.
5. Nhận diện rủi ro trong password, MFA, passkey, certificate, API key, token và session.
6. Đánh giá trust relationship giữa browser, mobile app, identity provider, resource server và workload.
7. Chọn preventive, detective và recovery control phù hợp với threat scenario.
8. Chuyển threat thành security requirement, test case và evidence có thể kiểm tra.
9. Ghi nhận residual risk, exception, owner và điều kiện chấp nhận rủi ro.
10. Thực hiện threat review trước release và sau thay đổi quan trọng của authentication architecture.

## 1. Authentication threat review là gì?

**Authentication threat review** là hoạt động phân tích có cấu trúc nhằm xác định cách một attacker, người dùng nội bộ hoặc thành phần bị compromise có thể làm sai lệch quá trình xác thực danh tính, chiếm credential, giả mạo principal, chiếm session hoặc lợi dụng trust relationship.

Review không chỉ hỏi “có MFA không?” hoặc “token có ký không?”. Nó cần xác định:

- Hệ thống đang bảo vệ tài sản nào?
- Ai có thể tương tác với từng thành phần?
- Dữ liệu hoặc quyết định nào đi qua trust boundary?
- Attacker có thể giả mạo, sửa, replay, đánh cắp hoặc làm gián đoạn điều gì?
- Kiểm soát nào ngăn, phát hiện hoặc giới hạn từng kịch bản?
- Có bằng chứng nào cho thấy kiểm soát hoạt động?
- Rủi ro còn lại có được owner có thẩm quyền chấp nhận không?

### Mục tiêu của review

- Phát hiện thiết kế yếu trước khi triển khai;
- Đánh giá thay đổi kiến trúc hoặc tích hợp identity provider;
- Xác định các đường bypass authentication và recovery;
- Kiểm tra credential lifecycle và session lifecycle;
- Đánh giá blast radius khi key, token hoặc IdP bị compromise;
- Tạo backlog remediation có mức ưu tiên;
- Cung cấp evidence cho security approval và release decision.

Threat review không thay thế penetration test, code review, privacy review, compliance assessment hoặc operational readiness. Nó định hướng các hoạt động đó bằng cách chỉ ra tài sản, trust boundary và attack path cần kiểm chứng.

## 2. Khi nào cần thực hiện threat review?

Review nên được thực hiện khi thiết kế mới, khi có thay đổi ảnh hưởng trust hoặc khi xuất hiện threat/evidence mới.

### Trước khi xây dựng

- Tạo login hoặc registration flow mới;
- Thêm passwordless, passkey hoặc MFA;
- Tích hợp OIDC, SAML hoặc external identity provider;
- Thiết kế token format, signing key hoặc session architecture;
- Thêm service-to-service authentication;
- Xây dựng account recovery hoặc account linking.

### Trước khi thay đổi production

- Thay issuer, audience, redirect URI hoặc signing algorithm;
- Thay đổi token lifetime, refresh rotation hoặc session policy;
- Thêm claim, scope, role hoặc tenant mapping;
- Chuyển từ JWT sang opaque token hoặc ngược lại;
- Thay KMS/HSM, certificate authority hoặc secret manager;
- Thay MFA provider, passkey enrollment hoặc recovery channel;
- Thêm browser/mobile deep link hoặc embedded login;
- Thay đổi fail-open/degraded mode hoặc cache policy.

### Sau sự kiện

- Credential compromise hoặc account takeover;
- Authentication bypass hoặc authorization confusion;
- Token/session replay;
- Federation misconfiguration;
- Identity provider outage có ảnh hưởng đến trust decision;
- Thay đổi threat landscape hoặc xuất hiện kỹ thuật tấn công mới.

Mức review có thể khác nhau theo quy mô thay đổi. Thay text trên trang login có thể cần kiểm tra hẹp; thay signing key hoặc trust federation cần review sâu và xác minh toàn bộ verifier.

## 3. Xác định scope và context

Review phải có ranh giới rõ ràng để tránh bỏ sót thành phần hoặc mở rộng không cần thiết.

### Thông tin scope

- Ứng dụng, service và environment;
- User population, tenant và client type;
- Authentication methods được hỗ trợ;
- Identity provider và external federation;
- Token/session model;
- Credential enrollment, rotation, revoke và recovery;
- Resource server và protected action;
- Browser, mobile, API và workload entry point;
- Region, cloud account và dependency;
- Các hệ thống logging, monitoring và incident response.

### In-scope và out-of-scope

Ghi rõ:

- Thành phần được review trực tiếp;
- Dependency được xem như external trust;
- Thành phần chỉ được đánh giá qua interface;
- Threat được loại khỏi scope và lý do;
- Giả định cần owner xác nhận;
- Phiên bản kiến trúc hoặc deployment đang được đánh giá.

Không được coi một dependency là an toàn chỉ vì nó nằm ngoài scope. Nếu identity provider, email service hoặc KMS nằm ngoài quyền kiểm soát, vẫn phải đánh giá trust assumption, failure mode và contract của dependency đó.

### Context của module

Authentication system cần bảo vệ danh tính từ credential ban đầu tới session và khôi phục tài khoản. Vì vậy, scope không dừng ở màn hình login: enrollment, MFA reset, token refresh, federation, service identity và recovery đều có thể là đường chiếm quyền.

## 4. Inventory tài sản cần bảo vệ

Tài sản là thứ attacker muốn lấy, sửa, giả mạo hoặc làm gián đoạn. Nếu không có inventory, threat review dễ tập trung vào component mà bỏ sót dữ liệu hoặc quyền có giá trị.

| Nhóm tài sản | Ví dụ | Hậu quả khi bị compromise |
| --- | --- | --- |
| Identity record | Subject ID, tenant membership, verified attributes | Mạo danh hoặc liên kết sai danh tính |
| Password credential | Password verifier/hash, reset state | Account takeover, offline cracking |
| MFA factor | TOTP seed, push binding, recovery code | Bypass yếu tố bổ sung |
| Passkey credential | Public key, credential ID, authenticator binding | Đăng nhập giả hoặc mất khả năng xác minh |
| Private key | Signing key, mTLS key, client key | Giả mạo token/certificate |
| API/client secret | API key, OAuth client secret | Truy cập service trái phép |
| Token | Authorization code, access/refresh/ID token | Delegated access, replay |
| Session | Session identifier, server-side session state | Chiếm phiên người dùng |
| Trust metadata | Issuer, JWKS, redirect URI, federation metadata | Chấp nhận sai identity provider hoặc token |
| Policy | MFA requirement, scope mapping, recovery policy | Bypass kiểm soát hoặc cấp quyền sai |
| Audit evidence | Login event, admin event, revoke record | Mất khả năng phát hiện/điều tra |
| Availability | IdP, token endpoint, session store, KMS | Người dùng/service không thể xác thực |

### Phân loại tài sản

Với mỗi tài sản, ghi:

- Owner và authoritative source;
- Confidentiality, integrity và availability requirement;
- Sensitivity/classification;
- Retention và backup;
- Principal/service có quyền truy cập;
- Cách revoke, rotate hoặc restore;
- Hậu quả nếu bị mất, lộ hoặc sửa.

### Không chỉ bảo vệ bí mật

Authentication phụ thuộc mạnh vào integrity và availability. Một public key không cần giữ bí mật nhưng nếu attacker thay JWKS hoặc trust metadata, verifier có thể chấp nhận token giả. Một session store không chứa private key nhưng nếu mất availability, người dùng có thể không thể logout hoặc revoke session.

## 5. Actors và attacker capability

Không phải attacker nào cũng có cùng quyền hoặc cùng khả năng.

### Actors

- Người dùng hợp lệ;
- Người dùng nội bộ có quyền thấp;
- Tenant administrator;
- Identity platform operator;
- Application/service owner;
- External attacker chưa xác thực;
- Attacker đã có một credential hợp lệ;
- Attacker kiểm soát thiết bị hoặc browser;
- Attacker kiểm soát một workload/service;
- External identity provider hoặc vendor;
- Malware, malicious browser extension hoặc compromised dependency.

### Attacker capability

Xác định attacker có thể:

- Gửi request tùy ý tới public endpoint;
- Đăng ký account hoặc client;
- Kiểm soát email/phone hoặc thiết bị của nạn nhân;
- Có password bị lộ từ breach khác;
- Đọc log, browser history hoặc mobile backup;
- Đăng ký custom URL scheme hoặc app giả;
- Có quyền trong một tenant nhưng không có quyền toàn hệ thống;
- Đọc secret từ CI/CD hoặc workload;
- Truy cập một service nội bộ;
- Chiếm admin account hoặc KMS permission;
- Gây network partition, outage hoặc retry storm.

### Phân biệt giả định và bằng chứng

Không ghi “attacker không thể truy cập network nội bộ” nếu chưa có network control chứng minh. Không giả định mobile app giữ client secret an toàn chỉ vì binary được obfuscate. Mỗi giả định cần owner, bằng chứng hoặc risk nếu giả định sai.

## 6. Trust boundary và data-flow diagram

Trust boundary là ranh giới nơi dữ liệu hoặc quyết định đi qua một miền có mức tin cậy, quyền kiểm soát hoặc chủ sở hữu khác.

### Các boundary thường gặp

- Browser/mobile app ↔ backend;
- Internet ↔ API gateway;
- Application ↔ identity provider;
- Identity provider ↔ external federation;
- Authorization server ↔ resource server;
- Service ↔ service;
- Workload ↔ KMS/secret manager;
- User ↔ recovery channel;
- Application ↔ logging/analytics provider;
- Region ↔ region hoặc tenant ↔ tenant.

### Sơ đồ khái niệm

`````````mermaid
flowchart LR
    U["User / attacker"] --> B["Browser or mobile app"]
    B -->|HTTPS, credential, callback| G["API gateway"]
    G --> I["Identity provider"]
    I -->|Token / assertion| R["Resource server"]
    R --> D["Protected data"]
    I --> K["KMS / HSM"]
    I --> S["Session and credential store"]
    I --> M["MFA / passkey provider"]
    I --> A["Audit and detection pipeline"]
    F["External IdP"] -->|Federation assertion| I
`````````

Sơ đồ phải được thay bằng kiến trúc thực tế trong review chính thức. Với mỗi data flow, ghi:

- Sender và receiver;
- Protocol và endpoint;
- Data/credential đi qua;
- Authentication của channel;
- Integrity/confidentiality protection;
- Validation ở receiver;
- Replay/expiry semantics;
- Logging/cache behavior;
- Failure mode và fallback.

### Trust boundary không chỉ là network

Hai service cùng VPC vẫn có thể có owner, privilege và dữ liệu khác nhau. Một browser cùng origin với app vẫn có thể bị ảnh hưởng bởi XSS hoặc third-party script. Một token do IdP tin cậy phát hành vẫn không hợp lệ cho mọi API nếu audience không khớp.

## 7. Phương pháp threat identification

Không có một framework duy nhất bao phủ mọi vấn đề. Kết hợp threat category, abuse case và attacker journey để giảm blind spot.

### STRIDE

| Category | Câu hỏi | Authentication example |
| --- | --- | --- |
| Spoofing | Attacker giả mạo ai hoặc thành phần nào? | Giả IdP, user, workload hoặc certificate |
| Tampering | Dữ liệu/quyết định nào có thể bị sửa? | Sửa claim, redirect URI, MFA policy |
| Repudiation | Có thể phủ nhận hành động không? | Audit thiếu actor, timestamp hoặc integrity |
| Information disclosure | Bí mật/dữ liệu nào có thể bị lộ? | Token, password, TOTP seed, PII |
| Denial of service | Thành phần nào có thể bị làm gián đoạn? | Login endpoint, MFA provider, KMS |
| Elevation of privilege | Có thể tăng quyền bằng cách nào? | Bypass MFA, scope confusion, session fixation |

### Abuse case

Viết threat dưới dạng:

> Khi [điều kiện/điểm vào], attacker có thể [hành động], khiến [tài sản hoặc security property] bị ảnh hưởng, vì [điểm yếu/giả định]. Kiểm soát hiện tại là [control], bằng chứng là [evidence].

Ví dụ:

> Khi một mobile app nhận OAuth callback qua custom scheme, app giả có thể đăng ký cùng scheme và nhận authorization code, khiến transaction có nguy cơ bị chiếm nếu client không dùng PKCE hoặc không kiểm tra state.

### Attacker journey

Xem toàn bộ chuỗi:

1. Initial access: phishing, password breach, malware hoặc secret exposure;
2. Credential acquisition: lấy password, token, session hoặc key;
3. Authentication: vượt login/MFA/recovery;
4. Persistence: thêm factor, OAuth grant, API key hoặc session;
5. Privilege: tăng scope/role hoặc chuyển tenant;
6. Action: đọc dữ liệu, thay đổi account hoặc gọi service;
7. Evasion: xóa log, dùng IP phân tán hoặc lạm dụng degraded mode.

Một kiểm soát có thể bảo vệ một bước nhưng attacker chuyển sang recovery hoặc service credential. Review phải tìm đường thay thế.

## 8. Threat matrix cho authentication lifecycle

| Giai đoạn | Threat tiêu biểu | Security property bị ảnh hưởng |
| --- | --- | --- |
| Registration/enrollment | Account pre-hijacking, factor enrollment fraud | Identity binding |
| Password login | Brute force, spraying, stuffing, phishing | Authentication assurance |
| MFA | Push fatigue, OTP relay, SIM swap | Factor independence/phishing resistance |
| Passkey | Challenge replay, origin/RP ID confusion, fallback bypass | Origin binding, proof of possession |
| Certificate | Private key theft, weak issuance, revocation gap | Key possession, issuer trust |
| Federation | Issuer confusion, redirect manipulation, assertion replay | Trust, audience, transaction binding |
| Token issuance | Client impersonation, grant theft, overbroad scope | Client identity, least privilege |
| Token validation | Algorithm confusion, wrong issuer/audience, key confusion | Integrity and recipient binding |
| Session | Fixation, theft, replay, weak logout | Session integrity and revocation |
| Recovery | Email takeover, recovery token replay, support fraud | Account ownership |
| Service auth | Secret reuse, workload spoofing, certificate abuse | Workload identity |
| Administration | MFA disable, policy downgrade, key replacement | Control-plane integrity |

Với mỗi hàng, ghi threat scenario cụ thể theo kiến trúc. Không dùng bảng này như checklist đánh dấu “có/không” mà không có evidence.

## 9. Password và credential threat review

### Threat cần xem xét

- Password guessing và brute force;
- Password spraying;
- Credential stuffing;
- Phishing và adversary-in-the-middle;
- Password reset abuse;
- Offline cracking sau database exfiltration;
- Password reuse trong môi trường nội bộ;
- Credential bị lộ qua log, URL, crash report hoặc support;
- Account enumeration;
- Password change/session invalidation sai.

### Câu hỏi review

- Password có được gửi qua TLS không?
- Password được hash bằng password hashing function phù hợp, salt riêng và cost được benchmark?
- Có giới hạn request theo account/source/client và bảo vệ phân tán?
- Error response có làm lộ account existence?
- Password reset token có entropy, expiry, purpose binding và single-use?
- Password change có xác minh reauthentication phù hợp?
- Session/token cũ có bị xử lý theo policy sau reset?
- Có kiểm tra password phổ biến/breached khi enrollment?
- Log/APM có loại bỏ request body và password field?

### Evidence

- Cấu hình password hashing và test benchmark;
- Rate-limit rule và test fixture;
- Recovery flow diagram;
- Log redaction test;
- Account enumeration test;
- Session revoke test sau password reset.

## 10. MFA và factor threat review

MFA tăng assurance khi các yếu tố độc lập và được xác minh đúng. Việc hiển thị màn hình OTP không tự chứng minh MFA được triển khai an toàn.

### Threat

- OTP phishing hoặc relay;
- SIM swap/number porting;
- Push bombing/MFA fatigue;
- TOTP seed theft;
- Recovery code leakage;
- Factor replacement sau account takeover;
- MFA enrollment không yêu cầu reauthentication;
- Step-up chỉ được kiểm tra ở UI;
- Backup factor yếu hơn factor chính.

### Câu hỏi review

- Factor được binding với đúng subject và transaction?
- Challenge có expiry, attempt limit và replay protection?
- Push approval có context/number matching khi cần?
- Enrollment/recovery factor có yêu cầu assurance phù hợp?
- Factor removal có thông báo và audit?
- Có giới hạn resend và chống abuse?
- Step-up được enforce ở server/resource?
- Recovery không tạo đường bypass MFA?

### Evidence

- MFA enrollment/removal sequence;
- Challenge lifecycle và replay tests;
- Step-up authorization tests;
- Recovery factor policy;
- Push fatigue detection rule;
- Audit event cho factor changes.

## 11. Passkey và WebAuthn threat review

Passkey/WebAuthn có khả năng chống phishing tốt nhờ ràng buộc origin/RP ID và chữ ký public-key, nhưng triển khai sai vẫn tạo rủi ro.

### Threat

- Challenge reuse hoặc challenge không gắn transaction;
- Origin/RP ID validation yếu;
- Credential ID không được binding với đúng account;
- User verification requirement bị bỏ qua;
- Attestation được tin quá mức hoặc xử lý sai;
- Registration ceremony không yêu cầu reauthentication;
- Account recovery/fallback yếu hơn passkey;
- Credential bị xóa hoặc thay đổi mà không có audit.

### Câu hỏi review

- Challenge có ngẫu nhiên, TTL ngắn và consume một lần?
- Server xác minh origin, RP ID hash, signature, credential và user presence/verification đúng policy?
- Credential được gắn với subject qua transaction đã xác thực?
- User verification có bắt buộc cho thao tác nhạy cảm?
- Attestation có được yêu cầu thực sự và policy có phù hợp?
- Có rate limit cho assertion failure và registration?
- Có cách revoke credential và phục hồi khi mất thiết bị?
- Fallback không làm suy yếu phishing resistance?

### Evidence

- WebAuthn registration/authentication flow;
- Test invalid origin/RP ID/challenge;
- Replay test;
- Credential enrollment audit;
- Recovery and fallback review.

## 12. Certificate, API key và workload credential

Service identity có thể dùng mTLS, certificate, API key, OAuth client secret hoặc workload identity. Mỗi loại có lifecycle và failure mode riêng.

### Threat

- Private key bị export hoặc lộ trong image/repository;
- API key dùng chung giữa môi trường;
- Certificate issuance không xác minh workload;
- Revocation không được verifier kiểm tra;
- Credential cũ tiếp tục hoạt động sau rotation;
- Service account có scope quá rộng;
- Workload identity token bị replay từ node khác;
- Secret manager permission quá rộng.

### Câu hỏi review

- Credential có owner, inventory, expiry và rotation policy?
- Private key có được tạo/lưu trong HSM/Keystore khi phù hợp?
- mTLS kiểm tra chain, SAN, EKU, validity và revocation theo policy?
- API key có scope, rate limit, monitoring và revoke?
- Workload identity có ràng buộc namespace/service account/audience?
- Credential được tách theo environment và consumer?
- Rotation có overlap, cutover, rollback và revoke?
- Secret manager access được audit?

## 13. Federation và OIDC/SAML threat review

Federation chuyển một phần quyết định danh tính sang issuer khác. Trust phải được xác định rõ theo issuer, key, audience, recipient, client và protocol.

### Threat

- Issuer confusion hoặc mix-up attack;
- Redirect URI open redirect;
- State/nonce thiếu hoặc không kiểm tra;
- Authorization code interception/replay;
- PKCE không dùng hoặc verifier bị lộ;
- ID token bị dùng như access token;
- SAML signature wrapping hoặc assertion replay;
- Audience/recipient/destination không được kiểm tra;
- Federation metadata/key bị thay trái phép;
- Account linking dựa vào email không đủ tin cậy.

### Câu hỏi review

- Native app dùng external user-agent và Authorization Code + PKCE?
- Redirect URI khớp chính xác?
- State và nonce được binding với transaction và consume một lần?
- Issuer, audience, signature, exp/nbf và algorithm được xác minh?
- SAML parser chống XXE và signature wrapping?
- Assertion ID replay được ngăn?
- Federation key rotation có overlap và revoke plan?
- Account linking yêu cầu xác minh danh tính hai phía?

## 14. Token và authorization threat review

Token là bằng chứng hoặc quyền truy cập được truyền giữa thành phần. Cần đánh giá cả nội dung, issuer, recipient, lifetime, storage và replay.

### Threat

- Token theft qua browser storage, mobile backup hoặc log;
- Wrong issuer/audience;
- Algorithm confusion hoặc none acceptance;
- Unknown kid và key lookup tùy ý;
- Scope/claim over-provisioning;
- Token replay;
- Refresh token reuse;
- ID/access token confusion;
- Token lifetime quá dài;
- Revocation không lan truyền;
- DPoP/mTLS sender constraint bị bỏ qua.

### Câu hỏi review

- Verifier có allowlist algorithm và issuer?
- Signature, audience, expiry, not-before và token type được kiểm tra?
- JWKS được lấy từ issuer tin cậy, không theo URL tùy ý trong token?
- Scope/audience theo resource và least privilege?
- Access/refresh token được lưu và gửi đúng nơi?
- Refresh rotation có reuse detection?
- Token có lifetime và revocation policy theo risk?
- Sensitive claim có được tối thiểu hóa?
- Error/log không echo token?

## 15. Session và browser/mobile threat review

Session thường là credential có thời hạn dài hơn request. Nếu session bị chiếm, attacker có thể bỏ qua login và MFA cho tới khi session hết hiệu lực hoặc bị revoke.

### Threat

- Session fixation;
- Cookie theft/XSS;
- CSRF và login CSRF;
- Weak cookie attributes;
- Session ID trong URL;
- Session không rotate sau login/step-up;
- Logout chỉ xóa client cookie nhưng không revoke server state;
- Idle/absolute timeout không phù hợp;
- Cross-device session không có visibility/revoke;
- Mobile token lưu plain storage;
- Deep link callback bị app khác chiếm;
- Notification hoặc clipboard làm lộ token.

### Câu hỏi review

- Session ID có entropy cao và được rotate sau authentication/privilege change?
- Cookie có Secure, HttpOnly, SameSite phù hợp?
- CSRF protection được áp dụng cho state-changing action?
- XSS và third-party script được kiểm soát?
- Logout/password reset/recovery có revoke session theo policy?
- Session có idle/absolute timeout và device visibility?
- Mobile token có platform-protected storage?
- Deep link/OAuth callback có PKCE/state và exact URI?

## 16. Account recovery và account linking threat review

Recovery thường là đường thay thế khi người dùng mất credential. Nếu recovery yếu hơn login, attacker sẽ nhắm vào recovery.

### Threat

- Email mailbox compromise;
- SIM swap hoặc phone number recycling;
- Recovery code theft/replay;
- Helpdesk social engineering;
- Support agent privilege abuse;
- Account enumeration;
- Recovery token leakage qua logs/referrer;
- Factor reset không yêu cầu assurance;
- Account linking nhầm subject/tenant;
- Recovery sau compromise không revoke session cũ.

### Câu hỏi review

- Recovery proof có độc lập với credential đang bị nghi compromise?
- Token có entropy, purpose binding, TTL và single-use?
- GET/prefetch không thực hiện side effect nhạy cảm?
- Support workflow có dual control và audit?
- Người dùng nhận notification qua kênh tin cậy?
- Recovery có delay/step-up cho thay đổi rủi ro cao?
- Session/token/factor attacker được revoke?
- Account linking xác minh issuer/subject, không chỉ email?

## 17. Threat review cho administrative và control plane

Control plane có thể thay đổi cách toàn bộ hệ thống tin cậy danh tính.

### Thành phần quan trọng

- Identity provider admin console;
- OAuth client registration;
- Redirect URI allowlist;
- Issuer and federation metadata;
- Signing key/JWKS configuration;
- MFA policy và recovery policy;
- Role/group mapping;
- KMS/HSM access policy;
- Secret manager permission;
- Audit, detection và suppression rule.

### Threat

- Admin account takeover;
- Unauthorized client registration;
- Redirect URI bị thêm host attacker;
- Signing key bị thay hoặc export;
- MFA policy bị downgrade;
- Logging/alert bị tắt;
- Break-glass account bị lạm dụng;
- Tenant boundary bị thay đổi.

### Kiểm soát

- Phishing-resistant MFA cho admin;
- Privileged access management và just-in-time access;
- Dual approval cho thay đổi trust root/key;
- Immutable/audited change log;
- Separation of duties;
- Break-glass credential được bảo vệ, kiểm tra và rotate sau sử dụng;
- Alert cho thay đổi ngoài change window;
- Rollback plan và test trước khi áp dụng rộng.

## 18. Risk assessment và ưu tiên remediation

Không phải threat nào cũng có cùng xác suất hoặc hậu quả. Risk assessment cần minh bạch cách xếp hạng và tránh tạo cảm giác chính xác giả bằng một con số duy nhất.

### Các yếu tố

- **Likelihood:** khả năng attacker thực hiện được;
- **Impact:** hậu quả với confidentiality, integrity, availability, safety và business;
- **Exposure:** endpoint public, internal, partner-only hay privileged;
- **Privilege:** quyền của principal/credential bị ảnh hưởng;
- **Exploitability:** kỹ năng, chi phí và điều kiện cần;
- **Detectability:** khả năng phát hiện trước khi thiệt hại;
- **Blast radius:** số account, tenant, API hoặc service có thể bị ảnh hưởng;
- **Confidence:** chất lượng evidence và giả định.

### Ma trận tham khảo

| Likelihood / Impact | Low | Medium | High | Critical |
| --- | --- | --- | --- | --- |
| Rare | Low | Low | Medium | High |
| Unlikely | Low | Medium | High | High |
| Possible | Medium | Medium | High | Critical |
| Likely | Medium | High | Critical | Critical |
| Almost certain | High | High | Critical | Critical |

Đây là ma trận định hướng. Tổ chức cần định nghĩa tiêu chí cụ thể, risk appetite và cách xử lý uncertainty.

### Ưu tiên remediation

- Fix trước các trust-root compromise và authentication bypass;
- Ưu tiên privileged/service identity có blast radius lớn;
- Xử lý đường recovery yếu có thể bypass MFA;
- Giảm token/session lifetime hoặc scope khi phù hợp;
- Tăng detection cho threat chưa thể loại bỏ ngay;
- Ghi rõ compensating control và expiry cho exception.

### Không chỉ dựa vào điểm số

Một threat có likelihood thấp nhưng cho phép attacker ký token giả cho mọi API có thể vẫn cần ưu tiên cao. Một issue có điểm trung bình nhưng đã có evidence exploitation phải được escalation.

## 19. Control mapping: prevent, detect, respond

Mỗi threat scenario nên có nhiều lớp kiểm soát.

| Threat | Prevent | Detect | Respond |
| --- | --- | --- | --- |
| Password stuffing | Rate limit, breached password screening, MFA/passkey | Failure campaign, success after failures | Revoke session, reset credential, notify |
| MFA fatigue | Number matching/context, prompt limit | Deny/timeout burst | Revoke sessions, verify factor, re-enroll |
| Passkey callback abuse | Origin/RP ID, challenge binding | Assertion failure/replay alert | Revoke credential, investigate device |
| Token replay | Short lifetime, sender constraint, one-time semantics | jti/nonce reuse | Revoke token family/session |
| Session theft | Secure cookie, XSS/CSRF controls, rotation | Concurrent/context anomaly | Revoke session and reauthenticate |
| Signing key compromise | HSM, least privilege, key isolation | KMS audit and signing anomaly | Stop signing, rotate, block old key |
| Federation confusion | Exact issuer/audience/redirect checks | State/nonce/assertion mismatch | Disable trust/client, rotate metadata/key |
| Recovery abuse | Independent proof, single-use token, delay | Recovery anomaly and factor change | Freeze risky change, verify owner, revoke |
| Service secret leak | Secret manager, workload identity, rotation | Secret access and source anomaly | Revoke/rotate, contain workload |
| IdP outage | HA, cache, DR and dependency isolation | SLI/SLO and dependency alert | Degraded mode under explicit policy |

Không coi việc có control trên giấy là bằng chứng. Cần test hoặc artifact chứng minh control được thực thi ở đúng boundary.

## 20. Security requirement và verification evidence

Threat review có giá trị khi kết quả được chuyển thành yêu cầu kiểm chứng được.

### Viết requirement tốt

Requirement nên mô tả:

- Hành vi bắt buộc;
- Thành phần chịu trách nhiệm;
- Điều kiện áp dụng;
- Failure behavior;
- Evidence hoặc test để xác minh.

Ví dụ:

`````````text
REQ-AUTH-014:
Resource server MUST reject an access token when its audience
does not identify that resource server.

Verification:
Submit a correctly signed token with a different audience.
Expected: request is rejected and no protected action occurs.
`````````

### Evidence gợi ý

- Data-flow/trust-boundary diagram;
- Protocol configuration và issuer/client registration;
- Threat scenario/risk register;
- Unit/integration/security test;
- Penetration test finding;
- Log redaction proof;
- Key lifecycle/rotation evidence;
- Recovery tabletop result;
- Access review và approval record;
- Monitoring alert và incident runbook;
- Deployment/change record.

### Requirement traceability

Mỗi threat cần liên kết:

Threat ID → Risk → Security requirement → Control → Test → Evidence → Owner

Nếu một threat không có control, ghi rõ treatment decision. Nếu có control nhưng không có test/evidence, trạng thái là chưa được xác minh.

## 21. Quy trình thực hiện review

Một review có thể theo các bước sau:

1. **Kickoff:** xác định owner, mục tiêu, scope, environment và deadline;
2. **Collect:** thu thập architecture, protocol flow, asset inventory và dependency;
3. **Model:** vẽ data flow, trust boundary và principal;
4. **Identify:** viết threat/abuse case theo lifecycle và attacker journey;
5. **Assess:** đánh giá likelihood, impact, exposure, confidence và blast radius;
6. **Map:** liên kết preventive, detective và response control;
7. **Verify:** kiểm tra test/evidence, ghi gap và assumption;
8. **Decide:** remediation, compensating control hoặc risk acceptance;
9. **Track:** gán owner, priority, due date và verification;
10. **Revisit:** review lại sau thay đổi hoặc khi threat intelligence/incident mới xuất hiện.

### Người tham gia

- Security architect hoặc reviewer;
- Identity/IAM engineer;
- Application/resource owner;
- Platform/SRE;
- Privacy/data owner khi có sensitive claim;
- Operations/incident response;
- Product/business risk owner.

Review không nên chỉ do người thiết kế hệ thống tự đánh giá. Cần một reviewer có thể chất vấn assumption và kiểm tra evidence độc lập.

## 22. Risk acceptance và exception

Không phải mọi risk đều có thể được loại bỏ ngay. Tuy nhiên, exception cần minh bạch, có người chịu trách nhiệm và có thời hạn.

### Nội dung exception

- Threat ID và mô tả;
- Risk rating và rationale;
- Tài sản/tenant/flow bị ảnh hưởng;
- Lý do chưa remediation;
- Compensating control;
- Residual risk;
- Owner có thẩm quyền;
- Ngày chấp nhận và expiry;
- Điều kiện đóng exception;
- Trigger review sớm khi có incident hoặc thay đổi.

### Không chấp nhận rủi ro mơ hồ

Các ghi chú như “chấp nhận tạm”, “sẽ sửa sau” hoặc “không có khả năng bị khai thác” không đủ. Cần xác định người chấp nhận, phạm vi, thời hạn và evidence hỗ trợ.

### Trigger hết hiệu lực

Exception cần review lại khi:

- Hết expiry;
- Thêm tenant/client/resource;
- Thay đổi token lifetime hoặc privilege;
- Xuất hiện exploit/incident mới;
- Compensating control không còn hoạt động;
- Owner hoặc business purpose thay đổi.

## 23. Tình huống review: thêm passkey và federation cho ứng dụng doanh nghiệp

Một ứng dụng web/mobile bổ sung passkey và đăng nhập qua enterprise OIDC. Hệ thống vẫn giữ password fallback, hỗ trợ magic link recovery và phát hành JWT access token cho nhiều API.

### Architecture cần làm rõ

- Browser/mobile external user-agent;
- Passkey registration/authentication endpoints;
- OIDC authorization server;
- Redirect URI và app links;
- Password fallback;
- Recovery service/email provider;
- Token issuer/JWKS/KMS;
- Resource server và API gateway;
- Session store và mobile secure storage;
- Audit/monitoring pipeline.

### Threat scenarios

1. Attacker dùng password bị lộ để đi qua fallback yếu;
2. Magic link bị email scanner consume hoặc bị lộ qua log;
3. OAuth callback bị custom scheme hijack;
4. State/nonce không binding với login transaction;
5. Passkey challenge không consume một lần;
6. App nhận assertion có origin/RP ID sai;
7. JWT audience rộng khiến token dùng ở API khác;
8. Recovery factor mới được thêm sau account takeover;
9. Refresh token bị replay sau rotation;
10. Admin thay redirect URI hoặc signing key không có approval.

### Controls và evidence

| Threat | Control | Evidence cần có |
| --- | --- | --- |
| Password fallback abuse | Rate limit, breached password screening, MFA/step-up | Attack simulation và rate-limit test |
| Magic link replay | Opaque single-use token, atomic consume, no GET side effect | Parallel replay test và email scanner test |
| Callback hijack | Verified HTTPS link, PKCE S256, state | Wrong scheme/state/verifier test |
| Passkey replay | Challenge TTL, origin/RP ID validation, consume once | Replayed assertion test |
| Token audience confusion | Audience-specific token và strict validation | Wrong audience integration test |
| Recovery takeover | Independent proof, factor-change notification | Recovery tabletop và audit |
| Refresh reuse | Rotation family và reuse detection | Reuse test và revoke evidence |
| Admin trust change | Dual approval, privileged MFA, immutable audit | Change audit và alert test |

### Kết quả review

Review kết thúc khi mỗi threat có risk rating, control owner, test/evidence và treatment decision. Các issue chưa xử lý được ghi exception có expiry và compensating control; không đánh dấu pass chỉ vì flow chạy thành công.

## 24. Bộ kiểm thử chấp nhận cho Authentication threat review

| Trường hợp | Cách kiểm tra | Kết quả kỳ vọng |
| --- | --- | --- |
| Scope completeness | Đối chiếu user/client/service/flow | Không bỏ sót enrollment, recovery và admin |
| Asset inventory | Kiểm tra credential/token/key/session inventory | Có owner, classification và lifecycle |
| Trust boundary | Review data-flow diagram | Mọi cross-boundary flow có sender, receiver và validation |
| Attacker capability | Thử các giả định về public/internal access | Giả định có evidence hoặc risk |
| Password attack | Mô phỏng brute force/spraying/stuffing | Detection/prevention được xác minh |
| Password storage | Kiểm tra verifier configuration | Password không plaintext/fast hash đơn lẻ |
| Account enumeration | So sánh response/timing | Không lộ account state không cần thiết |
| MFA enrollment | Thử thêm factor khi session yếu | Yêu cầu assurance phù hợp |
| MFA replay | Dùng lại challenge/OTP theo protocol | Bị từ chối |
| MFA fatigue | Tạo nhiều push challenge | Rate limit/detection hoạt động |
| Passkey origin | Gửi assertion từ origin sai | Server từ chối |
| Passkey RP ID | Gửi RP ID hash sai | Server từ chối |
| Passkey challenge | Reuse challenge | Server từ chối |
| Passkey fallback | Bỏ qua passkey qua password/recovery | Fallback giữ assurance policy |
| Certificate trust | Dùng cert sai SAN/EKU/issuer | Service identity bị từ chối |
| API key rotation | Dùng key cũ sau revoke | Provider từ chối |
| OAuth redirect | Dùng redirect URI không đăng ký | Authorization server từ chối |
| OIDC state | Callback state không khớp | Client từ chối |
| OIDC nonce | ID token nonce sai | Client từ chối |
| PKCE | Dùng verifier không khớp | Token endpoint từ chối |
| SAML replay | Gửi assertion ID đã dùng | SP từ chối |
| SAML signature | Sửa attribute sau ký | Signature validation thất bại |
| JWT signature | Sửa payload hoặc dùng algorithm không allowlist | Resource server từ chối |
| JWT audience | Dùng token cho resource khác | Resource server từ chối |
| JWT issuer | Dùng token từ issuer ngoài trust | Resource server từ chối |
| JWKS lookup | Token trỏ key URL không tin cậy | Verifier không fetch URL tùy ý |
| Token replay | Dùng lại proof/token theo replay policy | Bị phát hiện hoặc giới hạn |
| Refresh reuse | Dùng refresh token đã rotate | Token family bị xử lý theo policy |
| Session fixation | Giữ session ID trước login | Session ID được rotate |
| Logout/revoke | Dùng lại session sau logout | Server từ chối |
| Recovery abuse | Dùng recovery token cũ/đã consume | Bị từ chối |
| Account linking | Link subject/issuer khác không có proof | Không tự động liên kết |
| Tenant isolation | Thay tenant claim/reference | Cross-tenant access bị từ chối |
| Admin control plane | Thay redirect URI/signing key | Approval/audit/alert hoạt động |
| Logging | Gửi marker secret qua request | Marker không xuất hiện trong log/trace |
| Risk register | Kiểm tra threat record | Có owner, rating, control và treatment |
| Exception expiry | Đến ngày hết hạn exception | Review/escalation được kích hoạt |
| Evidence traceability | Chọn một threat và truy tới test | Có link threat → control → test → evidence |

Kiểm thử phải dựa trên threat scenario cụ thể của kiến trúc. Kết quả “HTTP 401” hoặc “unit test pass” không đủ nếu chưa chứng minh request không tạo session, token, side effect hoặc privilege ngoài ý muốn.

## 25. Checklist Authentication threat review

- **Scope:** Đã xác định application, user, tenant, client, environment và dependency?
- **Assets:** Credential, factor, key, token, session, policy, trust metadata và audit evidence có owner?
- **Actors:** Attacker capability, insider, compromised device/workload và external IdP đã được mô hình hóa?
- **Trust boundary:** Browser, mobile, gateway, IdP, resource server, KMS, recovery và logging flow đã được vẽ?
- **Lifecycle:** Registration, login, MFA, token, session, recovery, service identity và admin path đều được review?
- **Threat identification:** Có STRIDE, abuse case và attacker journey?
- **Risk:** Likelihood, impact, exposure, privilege, confidence và blast radius được ghi?
- **Controls:** Có preventive, detective và response control cho từng threat?
- **Protocol:** Issuer, audience, redirect, state, nonce, PKCE, signature, expiry và replay được kiểm tra?
- **Credential:** Enrollment, storage, rotation, revoke và recovery có policy?
- **Session:** Fixation, theft, CSRF, timeout, logout và revocation được đánh giá?
- **Privacy:** Sensitive claim, token, log, cache và retention được tối thiểu hóa?
- **Availability:** Dependency outage và degraded mode không bypass authentication?
- **Evidence:** Mỗi control có test, config hoặc artifact xác minh?
- **Ownership:** Threat/control/remediation có owner và due date?
- **Exception:** Residual risk có approver, rationale, compensating control và expiry?
- **Re-review:** Có trigger khi architecture, threat hoặc incident thay đổi?

### Câu hỏi tự kiểm tra

1. Vì sao authentication threat review phải bao gồm recovery và enrollment?
2. Trust boundary khác network boundary như thế nào?
3. STRIDE giúp phát hiện những nhóm threat nào trong identity system?
4. Vì sao cần mô hình hóa attacker đã có một credential hợp lệ?
5. Làm thế nào phân biệt control trên tài liệu với control đã được xác minh?
6. Vì sao signing-key compromise có blast radius lớn hơn một password bị lộ?
7. Tại sao passkey fallback và recovery cần được review cùng flow chính?
8. Một risk score thấp có thể bị override trong trường hợp nào?
9. Evidence nào chứng minh resource server kiểm tra audience?
10. Risk acceptance cần những trường nào và khi nào phải hết hiệu lực?

## Kết luận

**Authentication threat review là cách kiểm tra có hệ thống xem attacker có thể giả mạo danh tính, chiếm credential, lạm dụng token/session hoặc thay đổi trust bằng con đường nào.** Review bắt đầu từ scope, asset, actor và trust boundary; tiếp tục bằng threat scenario theo toàn bộ lifecycle; rồi đánh giá likelihood, impact, exposure, privilege và blast radius. Mỗi threat cần được nối với preventive, detective và response control, cùng security requirement và test evidence. Password, MFA, passkey, certificate, federation, token, session, recovery và administrative control plane đều phải được xem xét như các đường có thể cấp hoặc duy trì quyền truy cập. Kết quả review chỉ có giá trị khi risk owner, remediation, exception và expiry được ghi rõ, và các kiểm soát quan trọng được xác minh bằng test hoặc evidence thực tế.
