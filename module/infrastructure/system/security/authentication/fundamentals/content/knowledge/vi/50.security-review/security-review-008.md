# Security sign-off

> **Chương:** Security review  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Đưa ra quyết định phê duyệt bảo mật có căn cứ cho một hệ thống hoặc thay đổi liên quan đến xác thực danh tính, dựa trên phạm vi, threat model, bằng chứng kiểm thử, cấu hình vận hành và rủi ro còn lại.

## 1. Security sign-off là gì?

**Security sign-off** là quyết định được ghi nhận bởi người hoặc nhóm có thẩm quyền rằng một hệ thống, tính năng hoặc thay đổi đã được xem xét theo các tiêu chí bảo mật đã thống nhất và có thể chuyển sang giai đoạn tiếp theo trong những điều kiện được nêu rõ. Sign-off cần dựa trên bằng chứng có thể kiểm tra, phạm vi cụ thể, findings, residual risk và trách nhiệm của các owner.

Trong hệ thống xác thực, sign-off có thể áp dụng khi ra mắt login flow mới, chuyển từ password sang passkey, tích hợp OpenID Connect, thay signing key, triển khai mTLS cho workload, thay đổi session policy hoặc đưa quy trình account recovery vào sử dụng.

Ví dụ, một ứng dụng chuẩn bị dùng IdP doanh nghiệp. Nhóm phát triển đã triển khai OIDC Authorization Code Flow với PKCE, session cookie, MFA và logout. Security sign-off xem xét liệu callback có xác minh state/nonce/issuer/audience, session có rotate sau login, token có được bảo vệ, role có được kiểm tra ở backend, recovery có an toàn và đội vận hành có thể revoke access khi xảy ra compromise hay không. Một bản demo login thành công chưa đủ để kết luận hệ thống sẵn sàng.

Security sign-off không phải lời bảo đảm rằng hệ thống không có lỗ hổng. Nó là quyết định có giới hạn theo phạm vi, thời điểm, phiên bản, môi trường và bằng chứng đã xem xét. Khi kiến trúc, threat, dependency hoặc cấu hình thay đổi đáng kể, sign-off cũ có thể không còn phù hợp.

### Kết quả học tập

Sau bài này, người học có thể:

- Xác định phạm vi, owner và thẩm quyền của security sign-off.
- Xây dựng tiêu chí phê duyệt dựa trên threat model và trust boundary.
- Đánh giá bằng chứng cho password, MFA, passkey, certificate, token, session và federation.
- Kiểm tra authorization boundary, recovery, logging, privacy và vận hành.
- Phân loại finding theo mức độ, khả năng khai thác và tác động.
- Đánh giá residual risk và quản lý security exception.
- Đưa ra quyết định approve, conditional approval hoặc reject.
- Ghi nhận quyết định, điều kiện, người chịu trách nhiệm và thời hạn review.

## 2. Mục đích và phạm vi của sign-off

Trước khi review, cần xác định chính xác đối tượng được phê duyệt. “Đã review authentication” là phạm vi quá rộng và không thể kiểm chứng.

### Phạm vi cần ghi rõ

- Hệ thống, service, ứng dụng hoặc tính năng.
- Môi trường: development, staging, production hoặc tenant cụ thể.
- Phiên bản build, commit, release hoặc configuration baseline.
- Authentication flow được xem xét.
- Loại principal: end user, administrator, partner, service hoặc workload.
- Credential và factor được hỗ trợ.
- IdP, directory, gateway, session store, KMS/HSM và dependency liên quan.
- Dữ liệu và resource được bảo vệ.
- Region, tenant, client và relying party nằm trong phạm vi.
- Những phần không được review và lý do loại trừ.

### Ví dụ phạm vi

Một sign-off có thể phê duyệt:

> Web portal phiên bản 4.2 trong production, dùng OIDC Authorization Code Flow với PKCE từ IdP doanh nghiệp, session cookie server-side, MFA bắt buộc cho privileged action, và quyền truy cập được kiểm tra theo tenant ở backend.

Phạm vi đó không tự động phê duyệt mobile client, API key của workload, quy trình helpdesk recovery hoặc một IdP khác. Nếu các thành phần này có thể tạo hoặc duy trì access vào cùng dữ liệu, cần đưa chúng vào review hoặc ghi rõ residual risk và dependency.

## 3. Ai chịu trách nhiệm?

Security sign-off là quyết định có trách nhiệm, không phải checkbox của một cá nhân không có quyền.

| Vai trò | Trách nhiệm |
|---|---|
| Product/system owner | Chịu trách nhiệm về mục đích, phạm vi và quyết định phát hành |
| Engineering owner | Cung cấp kiến trúc, cấu hình, implementation và bằng chứng kỹ thuật |
| Security reviewer | Đánh giá threat, control, findings và residual risk |
| Identity/IAM owner | Xác nhận IdP, credential lifecycle, federation và access governance |
| Operations/SRE | Xác nhận monitoring, incident response, recovery và vận hành |
| Privacy/data owner | Xác nhận dữ liệu cá nhân, logging, retention và mục đích xử lý |
| Risk owner/approver | Chấp nhận residual risk trong thẩm quyền được giao |
| Incident commander/on-call owner | Xác nhận khả năng phát hiện, khoanh vùng và ứng cứu |

Một người có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ, nhưng cần tránh để người triển khai tự phê duyệt mọi rủi ro của chính thay đổi đó mà không có review độc lập phù hợp.

### Quyền phê duyệt

- Người review có thể đưa ra khuyến nghị kỹ thuật.
- Risk owner có thẩm quyền chấp nhận rủi ro còn lại.
- Product/system owner quyết định phát hành theo governance của tổ chức.
- Finding vượt thẩm quyền phải được chuyển lên cấp có quyền quyết định.
- Không dùng sự im lặng hoặc việc ticket đã đóng làm bằng chứng chấp thuận.

## 4. Security sign-off trong vòng đời phát triển

Sign-off thường là một checkpoint trước release hoặc trước khi thay đổi trust boundary. Nó cần được chuẩn bị từ sớm để findings có thể được xử lý trước thời điểm phát hành.

~~~mermaid
flowchart TD
    A["Define scope and owners"] --> B["Architecture and threat review"]
    B --> C["Implement security controls"]
    C --> D["Collect test and operational evidence"]
    D --> E["Review findings and residual risk"]
    E --> F{"Decision"}
    F -->|Approve| G["Release within approved scope"]
    F -->|Conditional| H["Track conditions and deadlines"]
    H --> I["Verify conditions"]
    I --> F
    F -->|Reject| J["Fix and resubmit"]
    G --> K["Monitor and re-review on change"]
    J --> B
~~~

Sign-off không thay thế secure design review, code review, penetration test, privacy review hoặc production readiness review. Nó tổng hợp kết quả liên quan và xác nhận các điều kiện bắt buộc đã được đáp ứng hoặc có người đủ thẩm quyền chấp nhận rủi ro còn lại.

## 5. Chuẩn bị evidence package

Review hiệu quả cần evidence package có thể truy xuất tới đúng phiên bản được đánh giá.

### Tài liệu và bằng chứng thường cần

- System context diagram và data flow.
- Trust boundary và danh sách principal.
- Threat model và abuse cases.
- Authentication/authorization sequence diagram.
- Credential, token, session và recovery design.
- IdP/federation configuration có loại bỏ secret.
- Cookie, TLS, CORS, redirect URI và gateway policy.
- Test plan, test report, test data version và kết quả regression.
- Security test hoặc penetration test findings nếu thuộc phạm vi.
- Dependency inventory và owner.
- Logging, monitoring, alert và audit design.
- Incident response, containment, revoke và recovery runbook.
- Privacy assessment, data inventory và retention policy.
- Change record, build/commit và configuration version.

### Evidence phải có thể kiểm chứng

Mỗi bằng chứng nên nêu:

- Tên và mục đích.
- Hệ thống/phiên bản/môi trường.
- Người hoặc công cụ tạo.
- Thời điểm tạo.
- Kết quả và giới hạn.
- Liên kết tới requirement hoặc finding.

Ảnh chụp màn hình login thành công chỉ chứng minh một trường hợp giao diện. Nó không chứng minh chữ ký token được xác minh, session bị revoke trên nhiều node hay account recovery không thể bị lạm dụng. Dùng test report, cấu hình đã review, log mẫu đã redacted và kiểm tra độc lập cho các control tương ứng.

### Bảo vệ evidence

- Không đính kèm password, OTP, recovery code, access token, refresh token, session cookie hoặc private key.
- Redact dữ liệu cá nhân không cần thiết.
- Giữ bản gốc và checksum khi yêu cầu evidence integrity.
- Lưu ở hệ thống có access control và audit.
- Không dùng production secret trong test report.

## 6. Threat model và trust boundary

Sign-off cần xác nhận threat model phản ánh kiến trúc thực tế, không chỉ một sơ đồ login đơn giản.

### Câu hỏi threat model

- Attacker có thể kiểm soát browser, thiết bị, network hoặc email recovery ở mức nào?
- Credential nào có thể bị phishing, replay, stuffing hoặc đánh cắp?
- Ai có thể phát hành token, ký assertion hoặc thay đổi IdP configuration?
- Gateway/proxy nào có quyền thêm identity header?
- Session/token có thể bị dùng lại ở application hoặc tenant khác không?
- Có đường recovery hoặc helpdesk bypass MFA không?
- Workload có thể giả mạo principal hoặc audience không?
- Signing key, KMS/HSM và directory được bảo vệ ra sao?
- Khi một dependency bị compromise, trust nào khác bị ảnh hưởng?
- Hệ thống phát hiện và giới hạn credential abuse bằng cách nào?

### Threats cần cân nhắc

- Phishing và credential theft.
- Credential stuffing, password spraying và brute force.
- MFA fatigue và factor replacement abuse.
- Passkey/recovery abuse và thiết bị bị chiếm.
- Token theft, replay, substitution và audience confusion.
- Session fixation, hijacking, CSRF và XSS.
- OIDC state/nonce/redirect URI lỗi.
- Certificate/private key compromise.
- API key leakage và workload impersonation.
- Clock skew làm token/certificate hết hạn sai.
- Account enumeration và privacy leakage.
- Privilege escalation qua group/role mapping.
- IdP, federation partner hoặc signing key compromise.

### Tiêu chí sign-off

- Threat model có owner và ngày review.
- Trust boundary được thể hiện cho browser, gateway, backend, IdP, directory và resource server.
- Data flow bao gồm credential, token, session và recovery.
- Các threat có control, test hoặc lý do chấp nhận rủi ro.
- Dependency và assumption được ghi rõ.
- Thay đổi kiến trúc có quy trình cập nhật threat model.

## 7. Credential và password controls

Nếu password được hỗ trợ, sign-off cần xác nhận cả xác minh lẫn vòng đời credential.

### Kiểm tra

- Password được truyền qua TLS.
- Password verifier dùng password hashing scheme chuyên dụng với salt riêng và tham số phù hợp.
- Không lưu password dạng rõ hoặc mã hóa có thể giải mã để thay thế password hashing.
- Không log password hoặc request body nhạy cảm.
- Password policy hỗ trợ password manager, paste và độ dài phù hợp.
- Có kiểm tra password phổ biến/bị lộ theo policy.
- Rate limit chống brute force, stuffing và spraying.
- Phản hồi công khai giảm account enumeration.
- Password reset token có entropy, one-time use và expiry.
- Thay password sau compromise có xử lý session/token liên quan.

### Evidence

- Cấu hình/thư viện password verifier đã review.
- Test case password đúng/sai, account không tồn tại và policy boundary.
- Test rate limit và enumeration.
- Log sample đã xác nhận không có password.
- Recovery flow test và session revocation result.

Không yêu cầu đưa password thật hoặc password hash của người dùng vào evidence package.

## 8. MFA, passkey và phishing resistance

MFA policy phải gắn với loại tài khoản và hành động được bảo vệ. “Có MFA” không đủ để sign-off nếu phương thức dễ bị phishing hoặc recovery có thể bypass.

### MFA

- Challenge được ràng buộc với principal, session và login attempt.
- Challenge có expiry, retry limit và one-time semantics theo policy.
- Password đúng nhưng MFA chưa hoàn tất không tạo full session.
- Push có context/number matching khi phù hợp và chống fatigue.
- TOTP có rate limit và cửa sổ clock skew giới hạn.
- Recovery code một lần, không log và có cơ chế rotate.
- Factor add/remove yêu cầu proof/step-up và tạo audit event.

### Passkey/WebAuthn

- Server challenge đủ ngẫu nhiên và được kiểm tra.
- Origin và RP ID được xác minh.
- Chữ ký, credential ID và user verification được kiểm tra theo policy.
- Private key không được gửi lên server.
- Credential lifecycle, revoke và lost-device recovery có quy trình.
- Synced passkey và security key được đánh giá theo assurance phù hợp.

### Phishing resistance

- Ưu tiên phishing-resistant authenticator cho privileged user và hành động rủi ro cao khi khả thi.
- Không xem SMS/TOTP là tương đương passkey/security key về khả năng chống phishing.
- Login page, redirect và recovery channel không tạo đường phishing phụ.
- Test xác minh authenticator không chấp nhận origin/RP ID giả.

### Evidence

- MFA policy matrix theo user class/action.
- Passkey registration/assertion test.
- MFA challenge expiry/replay/rate-limit test.
- Factor enrollment/removal audit.
- Recovery test và quy trình xử lý mất thiết bị.

## 9. Certificate, API key và workload identity

Với certificate hoặc credential máy-máy, sign-off cần xác minh cả danh tính peer lẫn scope được cấp.

### Certificate/mTLS

- Trust anchor và certificate chain đúng.
- Hostname/SAN, validity, EKU và key usage được kiểm tra.
- Revocation và rotation có quy trình.
- Private key được bảo vệ bằng KMS/HSM hoặc secret store phù hợp.
- TLS termination/proxy không cho phép client giả mạo identity header.
- Backend xác minh nguồn identity header qua trusted connection.

### API key/client secret

- Key có owner, scope, environment và expiry/review.
- Secret không nằm trong source, URL, log hoặc client-side bundle.
- Rotation có overlap được kiểm soát và revoke key cũ có xác minh.
- Rate limit và audit gắn với key/application reference.
- Key compromise có runbook và khả năng xác định consumer.

### Workload identity

- Workload có identity riêng, không dùng shared human account.
- Token/certificate có audience và lifetime phù hợp.
- Service chỉ nhận quyền cần thiết.
- Credential được cấp qua trust path xác minh được.
- Offboarding/redeployment thu hồi identity cũ.
- Network segmentation và service authorization bổ sung cho authentication.

## 10. Token, federation và OpenID Connect

Sign-off phải xác minh token được dùng đúng mục đích và federation trust được cấu hình chặt.

### Token validation

- Signature và algorithm được xác minh theo allowlist.
- Issuer, audience, expiry và required claims được kiểm tra.
- nbf/iat và clock tolerance có semantics rõ.
- Key rotation không làm verifier tin key chưa xác minh.
- Token không chứa dữ liệu nhạy cảm không cần thiết.
- Access token và ID token được phân biệt đúng.
- Refresh token rotation/reuse detection/revocation được kiểm thử.
- Bearer token exposure và replay risk được đánh giá.

### OIDC/federation

- Authorization Code Flow và PKCE được dùng theo client profile.
- state, nonce và redirect URI được kiểm tra.
- Authorization code có lifetime ngắn và one-time use.
- Issuer được allowlist; discovery/JWKS không lấy từ URL tùy ý do client điều khiển.
- Account linking dựa trên issuer + subject ổn định.
- Email không tự động là bằng chứng để hợp nhất hai identity.
- Logout tại RP và IdP được phân biệt.
- Federation metadata/key rotation và partner outage có xử lý.

### Evidence

- OIDC integration test và negative callback test.
- JWT validation test với issuer/audience/signature/time sai.
- JWKS rotation test.
- Token revoke/refresh reuse test.
- Federation configuration review.

## 11. Session lifecycle và browser security

Session là bearer credential và có thể tiếp tục truy cập sau khi credential ban đầu đã bị đổi.

### Kiểm tra

- Session ID đủ ngẫu nhiên và không chứa dữ liệu đoán được.
- Session ID rotate sau login và step-up.
- Session cũ bị invalidate phía server.
- Cookie có Secure, HttpOnly, SameSite và scope phù hợp.
- Không đưa session ID vào URL hoặc log.
- Idle timeout và absolute timeout được áp dụng.
- Logout revoke session phía server.
- Password reset, account compromise và admin disable có xử lý revoke.
- CSRF/login CSRF, XSS, clickjacking và open redirect được đánh giá.
- Session revocation propagation được kiểm tra trên mọi node/region.

### Evidence

- Cookie/configuration review.
- Session fixation và logout test.
- Multi-node revoke propagation test.
- Browser security headers/CSP review.
- Session timeout and reauthentication test.

## 12. Account recovery và identity lifecycle

Recovery thường là đường có assurance thấp hơn login chính. Một thiết kế login tốt vẫn có thể bị vô hiệu nếu helpdesk hoặc recovery link dễ bị lạm dụng.

### Kiểm tra

- Recovery proof phù hợp mức rủi ro và loại tài khoản.
- Public response không tiết lộ account existence.
- Recovery token một lần, có expiry và scope hẹp.
- Token không tự tạo full session nếu policy yêu cầu đăng nhập lại.
- Recovery method change yêu cầu step-up/approval phù hợp.
- Helpdesk không reset MFA chỉ dựa trên thông tin dễ đoán.
- Notification tới kênh đã xác minh.
- Session, refresh token và factor đáng ngờ bị revoke.
- Joiner/mover/leaver và offboarding cập nhật principal, group và credential.
- Identity linking/unlinking có xác minh và audit.

### Evidence

- Recovery positive/negative test.
- Helpdesk procedure và training record.
- Account lifecycle workflow.
- Factor replacement/revocation audit sample.
- Session/token invalidation test sau recovery.

## 13. Authorization boundary sau authentication

Authentication xác minh principal; authorization quyết định principal được làm gì. Sign-off cần xác nhận hai lớp không bị nhập làm một.

### Kiểm tra

- Principal được lấy từ credential đã xác minh, không từ user ID do client tự gửi.
- Role/group mapping dùng issuer, subject và identifier nguồn ổn định.
- Tenant và resource scope được kiểm tra ở backend.
- Default deny áp dụng cho quyền không được cấp.
- Role claim từ browser/header không thể tự nâng quyền.
- Service identity không thể giả làm user hoặc tenant khác.
- Step-up context gắn với action và resource cụ thể.
- Separation of duties được kiểm tra cho workflow nhạy cảm.
- Admin role có approval, review, expiry hoặc just-in-time elevation khi phù hợp.

### Evidence

- Authorization test matrix theo role/tenant/resource.
- Negative cross-tenant test.
- Role mapping configuration và approval.
- Privileged access review.
- Audit event cho role/permission changes.

Một login thành công và request trả 403 có thể là kết quả đúng nếu principal thiếu permission. Không coi mọi 403 là lỗi authentication.

## 14. Error handling, logging và privacy

Sign-off cần xác nhận hệ thống vừa điều tra được sự cố vừa hạn chế dữ liệu bị lộ.

### Error response

- 401, 403, 429 và 5xx dùng đúng semantics.
- Login/recovery response giảm account enumeration.
- Dependency timeout không bị báo thành password sai.
- Không trả stack trace, SQL detail, hostname hoặc file path nội bộ.
- Retry có backoff và deadline.

### Logging và monitoring

- Không log password, OTP, recovery code, raw token, cookie, authorization code hoặc private key.
- Metric labels có cardinality hữu hạn và không chứa PII/secret.
- Audit event ghi principal reference, actor, method, outcome và timestamp cần thiết.
- Log access có role, MFA, audit và retention.
- Alert có owner, severity, runbook và ngưỡng đã kiểm thử.
- Có tín hiệu cho credential stuffing, MFA fatigue, token replay và recovery abuse.

### Privacy

- Dữ liệu được thu thập có purpose và owner.
- Pseudonymization được áp dụng khi cần correlation.
- Retention/deletion được định nghĩa theo loại log.
- Không gửi authentication data tới analytics/advertising ngoài mục đích được phép.
- Dashboard mặc định hiển thị dữ liệu tổng hợp.

## 15. Secure configuration và dependency review

Một số lỗi không nằm trong code login mà nằm ở cấu hình và dependency.

### Cấu hình cần xem xét

- HTTPS/TLS và HSTS theo deployment model.
- CORS allowlist và credential mode.
- Redirect URI và allowed return URL.
- Cookie domain/path/attributes.
- Trusted proxy và header forwarding.
- CSP và third-party script trên trang login.
- NTP/time source và clock tolerance.
- Rate limit, bot protection và lockout policy.
- Token lifetime, key rotation và cache TTL.
- Session store access, encryption và availability.
- KMS/HSM access policy và signing key custody.
- IdP tenant, app registration, scopes và consent policy.

### Dependency

Với mỗi dependency, xác định owner, data exchanged, authentication method, failure mode, version, update process và trust assumption. Không phê duyệt một integration chỉ dựa vào tên nhà cung cấp hoặc chứng nhận chung; cần xem cách dịch vụ được cấu hình và sử dụng trong hệ thống cụ thể.

## 16. Security testing evidence

Test report phải gắn với đúng build/configuration và chứng minh các invariant quan trọng.

### Nhóm test tối thiểu theo phạm vi

- Happy path và negative path cho từng authentication method.
- Credential expiry, revoke, rotation và replay.
- Session fixation, cookie, timeout, logout và multi-node revocation.
- MFA challenge, factor enrollment/removal và recovery.
- OIDC state/nonce/PKCE/issuer/audience/redirect URI.
- Certificate validity, trust chain và mTLS identity.
- API key scope, rotation và secret exposure.
- Account enumeration, rate limit và error contract.
- Cross-tenant authorization và role spoofing.
- Dependency outage, clock skew và retry behavior.
- Logging/metric/trace secret scan và privacy checks.

### Đọc kết quả đúng cách

- Test pass chứng minh hành vi cụ thể trong điều kiện cụ thể.
- Test skipped không được tính là pass.
- Flaky test cần phân loại và điều tra, không retry vô hạn.
- Test không chạy được do dependency phải được ghi là blocked.
- Penetration test có phạm vi và giới hạn; không thay thế mọi functional test.
- Không kết luận an toàn chỉ từ coverage percentage.

## 17. Findings và severity

Mỗi finding cần mô tả vấn đề, điều kiện khai thác, tác động và biện pháp khắc phục.

### Finding record

- ID và title.
- Component, version và environment.
- Evidence/reference.
- Preconditions và attack path.
- Affected principal/data/trust boundary.
- Likelihood và impact.
- Severity theo rubric của tổ chức.
- Recommended remediation.
- Owner và due date.
- Retest result.

### Ví dụ nhóm severity

| Mức | Ví dụ trong authentication |
|---|---|
| Critical | Attacker có thể giả mạo issuer/signing key và truy cập diện rộng |
| High | Session/token bị chiếm có thể truy cập dữ liệu nhạy cảm; MFA có thể bị bypass |
| Medium | Rate limit hoặc recovery control yếu trong điều kiện khai thác cụ thể |
| Low | Thiếu audit detail hoặc cấu hình hardening có tác động hạn chế |
| Informational | Cải tiến quan sát hoặc tài liệu, chưa chứng minh được exploit |

Rubric thực tế phải theo chính sách tổ chức và context tài sản. Không hạ severity chỉ vì việc sửa khó hoặc release sắp tới.

### Retest

Finding chỉ được đóng khi có bằng chứng fix đã triển khai trong phiên bản/phạm vi liên quan và test xác nhận attack path không còn hoạt động. Một commit sửa code nhưng chưa deploy hoặc chưa kiểm tra cấu hình production chưa đủ để đóng finding vận hành.

## 18. Residual risk và security exception

Không phải mọi rủi ro đều có thể được loại bỏ trước release. Rủi ro còn lại cần được mô tả và chấp nhận bởi người có thẩm quyền.

### Nội dung residual risk

- Threat và attack path còn tồn tại.
- Asset/principal/data bị ảnh hưởng.
- Khả năng và tác động dự kiến.
- Control hiện có và giới hạn.
- Lý do chưa khắc phục.
- Phương án giảm thiểu tạm thời.
- Owner chịu trách nhiệm.
- Risk approver có thẩm quyền.
- Expiry/review date.
- Trigger bắt buộc xem xét lại.

### Security exception

Exception phải có phạm vi hẹp, thời hạn, owner và điều kiện kết thúc. Không tạo exception vô thời hạn hoặc áp dụng cho toàn bộ module chỉ vì một integration chưa hoàn tất.

Các trigger xem xét lại:

- Thay đổi authentication method hoặc IdP.
- Thay signing key, certificate hoặc token lifetime.
- Thay đổi tenant model, role mapping hoặc recovery.
- Tăng mức nhạy cảm của dữ liệu.
- Xuất hiện exploit mới hoặc incident liên quan.
- Hết hạn exception.
- Control bù không còn hiệu lực.

Risk acceptance không biến một control thiếu thành control đã đạt. Báo cáo cần giữ nguyên finding và thể hiện rõ ai đã chấp nhận rủi ro.

## 19. Quyết định approve, conditional approval hoặc reject

Quyết định nên dùng các trạng thái có ý nghĩa rõ.

| Quyết định | Khi nào dùng | Điều kiện |
|---|---|---|
| Approve | Tiêu chí bắt buộc đạt, evidence đủ, residual risk trong ngưỡng | Phạm vi và version được ghi rõ |
| Conditional approval | Còn điều kiện có thể kiểm soát trước hoặc sau release theo policy | Owner, deadline, compensating control và release gate cụ thể |
| Reject / No-go | Có rủi ro không chấp nhận, evidence thiếu trọng yếu hoặc control cốt lõi thất bại | Sửa, retest và trình lại |
| Deferred | Chưa đủ thông tin để ra quyết định | Ghi rõ evidence còn thiếu và ngày xem xét lại |

### Không dùng conditional approval mơ hồ

Một điều kiện như “bổ sung security sau” không thể kiểm chứng. Viết rõ:

- Điều gì phải hoàn tất?
- Ai chịu trách nhiệm?
- Hạn chót?
- Có được release trước khi hoàn tất không?
- Compensating control nào đang bảo vệ?
- Ai xác minh và đóng điều kiện?

Nếu thiếu một control cốt lõi như xác minh issuer/signature, revoke session sau account takeover hoặc bảo vệ signing key, không nên biến nó thành điều kiện hậu release nếu không có biện pháp thay thế đủ mạnh và người có thẩm quyền chấp nhận rõ ràng.

## 20. Go/no-go checklist cho authentication

### Danh tính và credential

- [ ] Principal được định danh ổn định và có nguồn xác minh.
- [ ] Credential được lưu, truyền và xác minh an toàn.
- [ ] Password verifier và policy đáp ứng yêu cầu.
- [ ] MFA/passkey/certificate được kiểm tra theo assurance cần thiết.
- [ ] Factor enrollment, removal và recovery được bảo vệ.
- [ ] Credential expiry, rotation và revocation có hiệu lực.

### Token, session và federation

- [ ] Issuer, audience, signature, algorithm và thời hạn được xác minh.
- [ ] OIDC state, nonce, PKCE và redirect URI được kiểm tra.
- [ ] Access token và ID token được dùng đúng mục đích.
- [ ] Session ID rotate sau login/step-up.
- [ ] Cookie attributes, timeout, logout và revoke được kiểm tra.
- [ ] Multi-node/cache propagation có bằng chứng.

### Authorization và trust boundary

- [ ] Role/permission không lấy từ client input không tin cậy.
- [ ] Tenant/resource ownership được kiểm tra ở backend.
- [ ] Default deny và least privilege được áp dụng.
- [ ] Privileged action có step-up/approval phù hợp.
- [ ] Gateway/proxy header và service identity có trust boundary rõ.

### Vận hành và privacy

- [ ] Logging không chứa credential hoặc secret.
- [ ] Monitoring/alert có owner và runbook.
- [ ] Incident containment và recovery đã được diễn tập hoặc kiểm tra.
- [ ] Dependency outage không fail-open.
- [ ] Time synchronization và key rotation có giám sát.
- [ ] Data minimization, retention và log access được phê duyệt.

### Governance

- [ ] Scope, build/configuration và evidence package được ghi nhận.
- [ ] Findings có severity, owner, due date và retest.
- [ ] Residual risk có approver và expiry.
- [ ] Conditional approval có release gate cụ thể.
- [ ] Có trigger và lịch review lại sau thay đổi.

## 21. Tình huống thực hành: sign-off cho cổng nhân viên

**Bối cảnh:** Một doanh nghiệp chuẩn bị đưa portal nhân viên vào production. Portal dùng OIDC với IdP doanh nghiệp, passkey cho nhóm quản trị, MFA cho hành động nhạy cảm và session cookie server-side. Portal xử lý dữ liệu nhân sự và cho phép một số thao tác quản trị.

### Evidence được yêu cầu

1. Architecture diagram cho browser, portal backend, IdP, directory, session store và HR API.
2. Threat model bao gồm phishing, token theft, session hijacking, recovery abuse và privileged account compromise.
3. OIDC integration tests cho state, nonce, PKCE, issuer, audience, signature và redirect URI.
4. Passkey tests cho origin, RP ID, challenge và user verification.
5. Session tests cho rotation, cookie attributes, timeout, logout và multi-node revoke.
6. Authorization tests cho tenant isolation, role mapping và privileged action.
7. Recovery tests cho lost device, factor replacement và helpdesk process.
8. Logging/privacy review và secret scan.
9. Incident runbook cho account takeover, IdP compromise và signing key rotation.
10. Production configuration baseline và dependency owner.

### Finding trong review

Review phát hiện session cookie được rotate ở browser nhưng session ID cũ chưa bị invalidate tại một node cache. Đây là đường session fixation/hijacking có tác động cao hơn một vấn đề giao diện.

### Quyết định

- Không approve release cho đến khi session revoke được xác minh trên mọi node.
- Engineering owner sửa cache invalidation và thêm integration test.
- Security reviewer retest với session cũ qua từng region.
- Operations owner xác nhận dashboard phát hiện revoke propagation failure.
- Khi evidence đạt, approver ghi quyết định cùng build/configuration cụ thể.

Ví dụ này cho thấy sign-off dựa trên control có thể kiểm chứng và điều kiện phát hành, không dựa trên việc nhóm đã hoàn thành một danh sách tài liệu.

## 22. Mẫu security sign-off record

Ví dụ JSON minh họa record quyết định. Dữ liệu thực tế cần tuân theo hệ thống governance của tổ chức.

~~~json
{
  "review_id": "SEC-REV-2026-042",
  "system": "employee-portal",
  "scope": {
    "environment": "production",
    "release": "4.2.0",
    "flows": ["oidc-login", "passkey-step-up", "session-cookie", "account-recovery"]
  },
  "reviewers": {
    "engineering_owner": "portal-engineering",
    "security_reviewer": "application-security",
    "risk_approver": "system-risk-owner"
  },
  "evidence": [
    "architecture-v4.2",
    "threat-model-v3",
    "oidc-test-report-118",
    "session-revocation-test-24",
    "privacy-review-19"
  ],
  "findings": {
    "open_critical": 0,
    "open_high": 0,
    "open_medium": 1,
    "open_low": 2
  },
  "decision": "conditional_approval",
  "conditions": [
    {
      "id": "COND-01",
      "requirement": "Complete log retention configuration review",
      "owner": "operations",
      "due_date": "2026-12-05",
      "release_gate": false
    }
  ],
  "residual_risk_owner": "system-risk-owner",
  "review_again_on": ["identity-provider-change", "session-policy-change", "new-critical-finding"]
}
~~~

Không đưa password, token, key, raw user identifier hoặc dữ liệu cá nhân không cần thiết vào sign-off record. Evidence reference nên trỏ tới kho tài liệu được kiểm soát quyền.

## 23. Kiểm thử quy trình sign-off

Sign-off process cũng cần được kiểm tra để tránh phê duyệt nhầm phiên bản, bỏ sót finding hoặc chấp nhận rủi ro không đúng thẩm quyền.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Scope không ghi release/build | Không thể approve |
| Evidence thuộc build cũ | Phải cập nhật hoặc đánh giá tác động |
| Threat model thiếu trust boundary quan trọng | Review bị block hoặc ghi rõ gap |
| Test critical flow bị skip | Không tính là pass |
| Open critical finding | No-go theo policy |
| Open high finding không có risk acceptance hợp lệ | No-go |
| Conditional approval thiếu owner/deadline | Không hợp lệ |
| Risk approver không đủ thẩm quyền | Chuyển cấp phê duyệt |
| Finding đã fix nhưng chưa retest | Chưa được đóng |
| Release config khác config đã review | Cần đánh giá lại |
| IdP/signing key thay đổi sau sign-off | Kích hoạt re-review |
| Exception hết hạn | Yêu cầu review/renewal có phê duyệt |
| Evidence chứa secret | Từ chối lưu và xử lý theo incident/data policy |
| Sign-off record bị sửa | Có version history/audit |
| Không có owner cho monitoring/runbook | Điều kiện vận hành chưa đạt |

## 24. Khi nào phải review lại?

Sign-off không phải phê duyệt vĩnh viễn. Cần review lại khi có thay đổi làm biến đổi threat, trust hoặc control:

- Thêm hoặc thay IdP, federation partner hay authentication method.
- Thay đổi password/MFA/passkey/recovery policy.
- Thay issuer, signing key, certificate authority hoặc token validation.
- Thay session lifetime, cookie, logout hoặc revocation architecture.
- Thay gateway, reverse proxy, trusted header hoặc network boundary.
- Thay role mapping, tenant model hoặc quyền privileged.
- Thêm dữ liệu nhạy cảm hoặc mở rộng audience.
- Thay đổi dependency quan trọng hoặc chuyển cloud/region.
- Xuất hiện incident, exploit hoặc finding nghiêm trọng.
- Hết hạn residual risk/exception.

Thay đổi nhỏ không nhất thiết cần lặp toàn bộ review. Dùng impact analysis để xác định phần nào cần retest và ai có thẩm quyền chấp thuận.

## 25. Checklist hoàn tất security sign-off

- [ ] Scope, build, environment và authentication flow được xác định.
- [ ] Owner, reviewer và approver có trách nhiệm rõ.
- [ ] Architecture/data flow và trust boundary được cập nhật.
- [ ] Threat model bao phủ credential theft, phishing, replay và recovery abuse.
- [ ] Password, MFA, passkey, certificate và workload credential được review theo phạm vi.
- [ ] Token, OIDC/federation, session và revocation được kiểm tra.
- [ ] Authorization boundary, role mapping và tenant isolation được kiểm tra.
- [ ] Recovery, helpdesk và factor replacement được đánh giá.
- [ ] Error handling, logging, monitoring và privacy được review.
- [ ] Dependency, secure configuration và key management có owner.
- [ ] Test evidence gắn đúng build/configuration và không chứa secret.
- [ ] Findings có severity, remediation, owner, deadline và retest.
- [ ] Residual risk được ghi nhận và chấp nhận đúng thẩm quyền.
- [ ] Conditional approval có điều kiện, release gate và deadline cụ thể.
- [ ] Incident containment, recovery và operational runbook sẵn sàng.
- [ ] Decision record có version, approver, scope và review trigger.

## Ghi nhớ

Security sign-off là quyết định có phạm vi và thời hạn, dựa trên evidence về threat model, credential, MFA/passkey, certificate, token, session, federation, recovery, authorization, privacy và vận hành. Một login thành công hoặc một test suite xanh không tự chứng minh toàn bộ hệ thống đã an toàn.

Hãy ghi rõ findings, residual risk, owner và thẩm quyền chấp nhận; dùng approve, conditional approval hoặc reject với điều kiện kiểm chứng được. Sign-off phải gắn với đúng build/configuration và được xem xét lại khi trust boundary, IdP, credential, session, recovery hoặc threat thay đổi.
