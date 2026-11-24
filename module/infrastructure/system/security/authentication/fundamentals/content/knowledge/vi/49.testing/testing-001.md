# Authentication functional test

> **Chương:** Testing  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Xác minh các luồng xác thực hoạt động đúng theo yêu cầu nghiệp vụ và chính sách bảo mật, từ credential đầu vào đến session/token, liên kết danh tính, thu hồi và khôi phục tài khoản.

## 1. Authentication functional test là gì?

**Authentication functional test (kiểm thử chức năng xác thực)** xác minh hệ thống thực hiện đúng các hành vi đã được đặc tả khi một người dùng, ứng dụng hoặc workload chứng minh danh tính. Kiểm thử tập trung vào đầu vào, trạng thái, kết quả, lỗi, chuyển tiếp giữa các bước và tác động quan sát được ở ranh giới hệ thống.

Ví dụ, khi người dùng nhập đúng password và hoàn tất MFA, ứng dụng phải xác định đúng principal, tạo session mới, phát cookie theo cấu hình và cho phép truy cập trang được bảo vệ. Nếu password đúng nhưng MFA chưa hoàn tất, hệ thống chỉ được giữ challenge state giới hạn. Nếu session đã bị revoke, request tiếp theo phải bị từ chối trên mọi node phục vụ ứng dụng.

Authentication functional test không chỉ kiểm tra nút Login có chuyển trang hay endpoint trả HTTP 200. Một bài test cần xác minh đúng principal, authentication context, session/token, thời hạn, quyền, trạng thái factor, audit event và hành vi khi dependency lỗi.

Module SECURITY_AUTHENTICATION_FUNDAMENTALS học các nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, federation, phishing defense và account recovery. Vì vậy, kiểm thử phải nhìn toàn bộ vòng đời và trust boundary, không chỉ một màn hình đăng nhập.

### Kết quả học tập

Sau bài này, người học có thể:

- Chuyển yêu cầu authentication thành test condition và test case có thể kiểm chứng.
- Phân biệt kiểm thử authentication với authorization.
- Thiết kế positive, negative, boundary, state-transition và integration test.
- Kiểm thử password, MFA, passkey, certificate, API key, token, session và federation.
- Xác minh expiry, replay protection, rotation, revocation và account recovery.
- Quản lý test identity, secret và dữ liệu cá nhân an toàn.
- Chọn unit, component, contract, integration và end-to-end test phù hợp.
- Đọc kết quả, xử lý flaky test và liên kết bằng chứng với yêu cầu.

## 2. Xác định phạm vi kiểm thử

Trước khi viết test, xác định hệ thống đang chịu trách nhiệm xác thực phần nào và phần nào thuộc IdP hoặc nhà cung cấp bên ngoài.

### Các thành phần có thể nằm trong phạm vi

| Thành phần | Hành vi cần xác minh |
|---|---|
| Login UI/API | Nhận request, validate input, hiển thị kết quả |
| Credential store | Tra cứu credential verifier và trạng thái |
| Authentication service | Xác minh password, key, certificate hoặc assertion |
| MFA service | Tạo, gửi, xác minh và kết thúc challenge |
| Passkey/WebAuthn handler | Xác minh challenge, origin, RP ID và signature |
| Token issuer/verifier | Phát hành, kiểm tra và từ chối token |
| Session manager | Tạo, rotate, expire và revoke session |
| Federation/OIDC client | Chuyển hướng, callback, state, nonce và token exchange |
| Recovery service | Reset password, factor và recovery code |
| Audit/monitoring | Ghi sự kiện và metric theo hợp đồng |
| Gateway/proxy | Chuyển tiếp credential và trust context đúng cách |

### Xác định trust boundary

Một test plan cần mô tả ai được tin và bằng chứng nào được xác minh:

- Browser/client gửi dữ liệu chưa đáng tin.
- Backend xác minh credential và xác định principal.
- IdP chỉ được tin khi issuer, signature, audience và protocol được xác minh.
- Gateway chỉ được tin khi backend có thể xác minh gateway identity và đường kết nối.
- Directory/group service có authority đối với các thuộc tính cụ thể, theo freshness policy.
- Session store/token verifier quyết định trạng thái credential theo hợp đồng.
- Authorization layer kiểm tra quyền trên resource và tenant sau authentication.

Test không nên mock xuyên qua chính trust boundary đang cần xác minh. Nếu mục tiêu là kiểm tra OIDC callback, mock toàn bộ callback verifier sẽ làm test mất giá trị.

## 3. Từ yêu cầu đến test case

Mỗi test case nên bắt nguồn từ yêu cầu, threat hoặc hợp đồng giao tiếp. Một yêu cầu mơ hồ như “login an toàn” cần được phân rã thành các điều kiện có thể kiểm tra.

### Ví dụ phân rã

Yêu cầu: “User chỉ có session đầy đủ sau khi hoàn tất mọi yếu tố bắt buộc.”

Các điều kiện:

1. Password đúng nhưng MFA còn pending thì không truy cập protected resource.
2. MFA thành công thì session mới được tạo.
3. Session ID trước authentication không được giữ lại sau login.
4. MFA challenge hết hạn thì không thể hoàn tất bằng challenge cũ.
5. Một challenge đã dùng không thể được dùng lại nếu policy yêu cầu one-time use.
6. Audit event phản ánh authentication method và kết quả cuối.

### Traceability

Liên kết mỗi test với:

- Requirement ID hoặc policy ID.
- Authentication method và flow.
- Preconditions/test identity.
- Input và hành động.
- Expected result.
- Security invariant cần giữ.
- Bằng chứng quan sát được.
- Owner và trạng thái test.

Traceability giúp biết một thay đổi về password policy, token lifetime hoặc recovery flow cần chạy lại những nhóm test nào.

## 4. Test model: positive, negative, boundary và state

Một bộ test chức năng cần nhiều góc nhìn.

| Loại test | Mục đích | Ví dụ |
|---|---|---|
| Positive | Xác minh luồng hợp lệ | Password đúng và MFA thành công |
| Negative | Xác minh input/trạng thái không hợp lệ bị từ chối | Token sai chữ ký |
| Boundary | Kiểm tra biên thời gian, độ dài và giới hạn | Token tại thời điểm exp |
| State transition | Kiểm tra chuyển trạng thái đúng | Challenge pending sang verified |
| Integration | Kiểm tra tương tác giữa thành phần | Backend với IdP/session store |
| Contract | Kiểm tra giao kèo API/protocol | OIDC callback và token response |
| Regression | Bảo đảm thay đổi không phá hành vi đã có | Logout vẫn revoke session sau release |
| Recovery | Kiểm tra đường khôi phục sau sự cố | Reset password và thu hồi session cũ |

### Test theo state machine

Authentication flow thường có trạng thái rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> Anonymous
    Anonymous --> CredentialPending: Submit credential
    CredentialPending --> Rejected: Invalid credential
    CredentialPending --> ChallengePending: Credential valid, MFA required
    CredentialPending --> Authenticated: No additional challenge
    ChallengePending --> Authenticated: Challenge verified
    ChallengePending --> Rejected: Failed or expired
    Authenticated --> SessionExpired: Timeout
    Authenticated --> SessionRevoked: Logout or revoke
    SessionExpired --> Anonymous
    SessionRevoked --> Anonymous
    Rejected --> Anonymous
~~~

Test cần xác minh cả transition hợp lệ lẫn transition bị cấm. Ví dụ, không được chuyển từ ChallengePending sang Authenticated khi challenge đã hết hạn hoặc thuộc một session khác.

## 5. Test data và test identity

Test identity phải đại diện cho các trường hợp nghiệp vụ nhưng không sử dụng tài khoản thật hoặc credential production.

### Bộ principal tối thiểu

- User active có password.
- User yêu cầu MFA.
- User có passkey.
- User có nhiều factor và recovery code.
- User disabled/suspended.
- User thuộc hai tenant với role khác nhau.
- User không có membership trong tenant đang thử.
- Privileged user có step-up requirement.
- Service/workload principal.
- Principal liên kết với IdP ngoài.

### Quản lý test credential

- Tạo credential riêng cho môi trường test.
- Không sao chép password, TOTP seed, private key hoặc token production.
- Lưu secret test trong secret manager hoặc fixture an toàn.
- Cấp quyền tối thiểu cho test identity.
- Có thời hạn và quy trình rotate/revoke sau test.
- Không ghi secret vào source control, test report hoặc CI log.
- Reset state giữa các test để kết quả có thể lặp lại.

### Tính cô lập

Một test không nên phụ thuộc vào trạng thái do test trước để lại. Dùng fixture setup/teardown, namespace riêng, tenant riêng hoặc data factory. Nếu test cần state dùng chung, phải khai báo rõ và tránh chạy song song gây race.

## 6. Kiểm thử password authentication

Password flow cần kiểm tra input validation, credential verification, policy và trạng thái tài khoản.

### Positive cases

- Identifier và password hợp lệ.
- Password có ký tự Unicode, khoảng trắng hoặc ký tự đặc biệt theo policy.
- Password manager paste hoạt động.
- Password mới sau reset có thể đăng nhập.
- Login thành công tạo session mới và principal đúng.

### Negative cases

- Password sai.
- Account không tồn tại.
- Account disabled, suspended hoặc chưa được kích hoạt.
- Password đã bị revoke/reset.
- Password vượt giới hạn input hoặc payload không đúng schema.
- Request thiếu CSRF token nếu flow yêu cầu.
- Rate limit được kích hoạt.

### Boundary và policy

- Minimum/maximum length theo policy.
- Unicode normalization nhất quán theo hợp đồng.
- Không cắt ngắn password âm thầm.
- Password mới nằm trong blocklist bị từ chối.
- Password reuse policy được áp dụng nếu có.
- Password verifier được nâng cấp khi policy/library thay đổi theo cơ chế migration.

Test không nên khẳng định một hash cụ thể bằng cách đọc database production. Có thể kiểm tra bằng unit/component test rằng password verifier dùng thư viện và cấu hình được phê duyệt, đồng thời kiểm tra hành vi xác minh đúng/sai qua interface.

### Ví dụ test case

| ID | Điều kiện | Kết quả mong đợi |
|---|---|---|
| PWD-01 | Active user, password đúng | Credential được xác minh |
| PWD-02 | Password sai | Login bị từ chối, không có full session |
| PWD-03 | Account không tồn tại | Public response không tiết lộ account state |
| PWD-04 | Account suspended | Không tạo session |
| PWD-05 | Password mới không đạt policy | Reset/change bị từ chối |
| PWD-06 | Password hợp lệ có Unicode | Kết quả nhất quán theo policy |
| PWD-07 | Login vượt rate limit | Request bị giới hạn |

## 7. Kiểm thử MFA và challenge

MFA cần được kiểm thử như một state machine riêng, gắn với login attempt và principal.

### TOTP

- Mã hợp lệ trong time step được chấp nhận.
- Mã sai, hết hạn hoặc sai format bị từ chối.
- Mã đã dùng không được replay nếu policy yêu cầu.
- Clock skew nằm trong tolerance được xử lý đúng.
- Clock skew vượt tolerance bị từ chối có kiểm soát.
- Rate limit áp dụng riêng cho verify/resend.

### Push MFA

- Challenge được gửi tới factor đã đăng ký.
- Approve đúng challenge hoàn tất bước xác minh.
- Deny, timeout hoặc cancel không tạo full session.
- Challenge cũ hoặc challenge của attempt khác bị từ chối.
- Push resend có cooldown và giới hạn.
- Nhiều challenge không được âm thầm thay thế nhau.

### Recovery code

- Code hợp lệ, chưa dùng được chấp nhận.
- Code đã dùng hoặc sai bị từ chối.
- Code chỉ dùng một lần theo policy.
- Khi bộ code được rotate, code cũ mất hiệu lực.
- Không ghi raw code vào log.

### Step-up

- Action nhạy cảm yêu cầu mức xác thực bổ sung.
- Challenge ràng buộc với session, action và resource.
- Challenge cũ không thể phê duyệt action mới.
- Khi step-up thất bại, quyền hiện tại không được nâng lên.

## 8. Kiểm thử passkey và WebAuthn

Passkey test cần xác minh cả browser ceremony và server-side verification. Dùng test authenticator hoặc browser automation được hỗ trợ; không giả lập chữ ký tùy tiện rồi bỏ qua verifier thật trong integration test.

### Registration

- Server tạo challenge mới, đủ ngẫu nhiên và gắn với ceremony.
- Browser nhận đúng RP ID và origin context.
- User verification/presence được yêu cầu theo policy.
- Server kiểm tra challenge, origin, RP ID hash, attestation policy nếu có, credential ID và public key.
- Credential được gắn với đúng principal.
- Credential đã tồn tại hoặc bị revoke được xử lý theo policy.

### Authentication assertion

- Assertion hợp lệ được chấp nhận.
- Challenge sai, hết hạn hoặc đã dùng bị từ chối.
- Origin hoặc RP ID không khớp bị từ chối.
- Chữ ký sai hoặc credential không thuộc principal bị từ chối.
- User verification không đạt yêu cầu bị từ chối.
- Counter/backup eligibility signals được xử lý theo semantics của authenticator và policy, không áp đặt giả định không phù hợp với passkey synced.

### Lifecycle

- User có thể xem và thu hồi passkey theo quyền.
- Thu hồi credential làm assertion tiếp theo thất bại.
- Thêm passkey mới yêu cầu proof/step-up theo policy.
- Account recovery không tự động khôi phục passkey đã bị revoke.

## 9. Kiểm thử token authentication

Token test cần kiểm tra token được phát hành đúng mục đích và verifier áp dụng đầy đủ các điều kiện.

### JWT validation

- Chữ ký đúng với key được tin cậy.
- Thuật toán nằm trong allowlist.
- Issuer khớp cấu hình.
- Audience/resource khớp API.
- exp, nbf và các claim thời gian được xử lý đúng.
- Token thiếu claim bắt buộc bị từ chối.
- Token bị sửa payload hoặc signature bị từ chối.
- Key rotation không làm verifier tin key không xác minh.
- Token có scope/permission phù hợp với API contract.

### Opaque token/introspection

- Active token được xử lý đúng.
- Inactive/revoked token bị từ chối.
- Introspection timeout không fail-open.
- Cache không giữ trạng thái active quá TTL policy.
- Client authentication tới introspection endpoint được xác minh.

### Access token và ID token

- Access token có audience của resource server.
- ID token được dùng để xác minh đăng nhập cho relying party theo OIDC.
- ID token không được chấp nhận thay access token để gọi API.
- Client không thể tự chọn issuer hoặc key URL tùy ý từ token header.

### Replay và token binding

- Token bị revoke không thể tiếp tục sử dụng sau propagation deadline.
- Sender-constrained token được kiểm tra proof theo profile hỗ trợ.
- DPoP/mTLS-bound token được test theo giao thức và thư viện tương ứng.
- Không giả định bearer token tự chống replay.

## 10. Kiểm thử session lifecycle

Session là credential có vòng đời riêng, kể cả khi login ban đầu dùng passkey hoặc OIDC.

Các test quan trọng:

- Session mới được tạo sau authentication success.
- Session ID được rotate sau login và step-up.
- Session ID cũ bị vô hiệu hóa.
- Cookie có Secure, HttpOnly, SameSite và scope phù hợp.
- Idle timeout và absolute timeout được thực thi.
- Request nền không kéo dài session vô hạn ngoài policy.
- Logout invalidate session phía server.
- Admin/account recovery có thể revoke session theo policy.
- Session bị revoke không được chấp nhận ở mọi app node.
- Session của tenant này không truy cập được dữ liệu tenant khác.

### Kiểm thử concurrency

Test đồng thời nhiều request dùng cùng session trong lúc logout/revoke. Kết quả phải phù hợp với consistency contract: sau thời điểm revoke có hiệu lực, request mới không được tiếp tục sử dụng session. Nếu có propagation delay, cần đo và giới hạn theo policy.

## 11. Kiểm thử OpenID Connect và federation

Federated login cần kiểm thử protocol boundary, không chỉ mock một user profile.

### Authorization request/callback

- state được tạo, gắn với browser session và kiểm tra khi callback.
- nonce được tạo và xác minh trong ID token.
- Redirect URI khớp chính xác cấu hình đã đăng ký.
- Authorization code chỉ dùng một lần và có thời hạn.
- PKCE verifier khớp challenge theo flow.
- Issuer, audience, signature, exp và required claims được xác minh.
- Callback không hợp lệ không tạo session.
- Account linking dùng issuer + subject ổn định, không tự hợp nhất chỉ dựa email.

### Federation lifecycle

- IdP metadata/JWKS update được xử lý an toàn.
- Key rotation có overlap và verifier không tin key không xác thực.
- IdP unavailable trả lỗi tạm thời, không báo password sai.
- Logout cục bộ và IdP logout được phân biệt.
- Consent/grant revoke có hiệu lực theo contract.
- Một issuer không được phép không thể tạo principal trong ứng dụng.

## 12. Kiểm thử certificate và workload authentication

Với mTLS/client certificate:

- Certificate chain được xác minh tới trust anchor đúng.
- Hostname/SAN, validity, EKU và key usage được kiểm tra.
- Certificate hết hạn hoặc chưa có hiệu lực bị từ chối.
- Certificate bị revoke được xử lý theo cơ chế triển khai.
- Certificate từ CA không được tin cậy bị từ chối.
- Client không thể giả mạo identity header sau TLS termination.
- Workload chỉ được nhận scope/audience đã cấp.
- Rotation certificate không tạo khoảng thời gian mà certificate không xác minh vẫn được chấp nhận.

Với service identity, test cả danh tính workload và quyền API. mTLS xác thực peer ở tầng kết nối; nó không tự cấp mọi permission nghiệp vụ.

## 13. Kiểm thử API key và request signing

API key:

- Key hợp lệ, active và đúng scope được chấp nhận.
- Key sai, hết hạn, revoked hoặc thuộc application khác bị từ chối.
- Key không được nhận qua query string nếu contract quy định header.
- Rotation tạo key mới và revoke key cũ đúng thời hạn.
- Secret không xuất hiện trong log, trace hoặc error response.

Request signing:

- Chữ ký hợp lệ cho method/path/body được chấp nhận.
- Sửa method, path, body hoặc signed header làm chữ ký thất bại.
- Timestamp ngoài freshness window bị từ chối.
- Nonce đã dùng bị từ chối hoặc xử lý idempotent theo contract.
- Canonicalization nhất quán giữa client, proxy và server.
- Hai request đồng thời dùng cùng nonce không thể cùng vượt qua one-time check.

## 14. Kiểm thử account recovery

Recovery là một authentication flow khác và thường có assurance thấp hơn login bình thường nếu thiết kế kém.

Test các trường hợp:

- Recovery request không tiết lộ account existence.
- Token reset ngẫu nhiên, một lần và hết hạn đúng.
- Token sai, hết hạn hoặc đã dùng bị từ chối.
- Token chỉ cho phép hành động reset đã định nghĩa, không cấp full session.
- Recovery method change yêu cầu xác minh/step-up.
- Helpdesk recovery yêu cầu proofing và approval theo policy.
- Sau recovery, session/refresh token/factor đáng ngờ được xử lý theo policy.
- Notification được gửi tới kênh đã xác minh.
- Recovery code và token không xuất hiện trong log.
- Rate limit ngăn spam reset và OTP.

## 15. Kiểm thử authorization boundary sau authentication

Functional test xác thực cần xác nhận principal được truyền đúng sang authorization layer, nhưng phải giữ hai kết quả riêng.

- Credential hợp lệ không tự cấp quyền Admin.
- Role claim do client gửi bị bỏ qua.
- Principal chỉ có quyền trong tenant được gán.
- Resource ownership được kiểm tra ở server.
- Role mapping dùng issuer/subject/group identifier đã xác minh.
- Step-up context đáp ứng action cụ thể và còn hiệu lực.
- User bị suspend không truy cập được resource sau khi session bị revoke.
- Service identity không thể giả làm user hoặc tenant khác.

Một test có thể xác thực thành công rồi nhận 403 vì thiếu quyền. Đó là kết quả authentication đúng và authorization denial đúng; không đánh dấu test login thất bại.

## 16. Boundary, clock và replay test

Thời gian và replay thường gây lỗi không ổn định nếu chỉ kiểm tra happy path.

### Clock boundary

- Token ngay trước, tại và sau exp.
- Token trước và sau nbf.
- Certificate trước notBefore và sau notAfter.
- TOTP trong và ngoài step window.
- Session ở idle/absolute timeout boundary.
- Clock skew trong tolerance và vượt tolerance.
- Wall clock rollback/jump không làm timeout duration chạy ngược.

### Replay boundary

- Authorization code đã dùng không thể đổi lần hai.
- OIDC state/nonce sai không tạo session.
- TOTP code đã dùng bị từ chối theo policy.
- Signed request nonce bị claim một lần trên cluster.
- Request retry với idempotency key không tạo giao dịch lặp.
- Refresh token rotation reuse kích hoạt policy thu hồi.

Test clock nên dùng fake clock hoặc test harness cô lập; không chỉnh giờ máy production. Test replay phải bao gồm request đồng thời để phát hiện race condition trong nonce store.

## 17. Kiểm thử error contract và privacy

Kiểm tra response và telemetry như một phần của functional contract:

- Account không tồn tại và password sai không tiết lộ account state.
- 401, 403, 429 và 5xx được dùng đúng ngữ nghĩa.
- Dependency outage không bị báo thành invalid password.
- Response không chứa stack trace, SQL detail hoặc internal hostname.
- Password, OTP, recovery code, raw token, cookie và private key không xuất hiện trong log.
- Metric labels không chứa email, IP, user ID hoặc request ID.
- Audit event có event ID, timestamp, method, outcome và reason group cần thiết.
- Truy cập audit detail bị giới hạn và được ghi nhận.
- Retention/deletion policy được áp dụng.

## 18. Chọn test level và mức độ tích hợp

Không cần gọi mọi dependency thật trong từng test. Chọn test level theo rủi ro của hành vi cần xác minh.

| Test level | Phạm vi | Phù hợp với |
|---|---|---|
| Unit | Hàm/logic nhỏ | Policy mapping, claim validation helper, state transition |
| Component | Một service với dependency test double | Password policy, session manager, challenge service |
| Contract | API/protocol boundary | OIDC metadata, token response, error schema |
| Integration | Nhiều thành phần thật trong môi trường test | DB, session store, JWKS, directory, MFA adapter |
| End-to-end | Browser/API qua hệ thống gần production | Login, MFA, callback, logout, recovery |
| Compatibility | Browser/device/library/version khác nhau | WebAuthn, cookie, federation interoperability |

### Dùng mock có chủ đích

Mock phù hợp để mô phỏng timeout, lỗi provider hiếm gặp hoặc kiểm tra logic cục bộ. Nhưng cần integration test xác minh chữ ký, TLS, WebAuthn, OIDC callback và revoke propagation bằng implementation thật hoặc test provider đáng tin.

Nếu mock token verifier trong mọi test, suite có thể xanh trong khi production chấp nhận sai audience. Nếu gọi IdP thật trong mọi unit test, suite sẽ chậm và flaky. Phân tầng test giúp cân bằng.

## 19. Tự động hóa và CI

Một pipeline test authentication có thể gồm:

1. Unit/component test cho policy và state transition.
2. Contract test cho API, token claim và federation metadata.
3. Integration test với DB, session store, test IdP và test MFA provider.
4. Browser/API end-to-end test cho luồng quan trọng.
5. Negative test cho credential sai, expiry, revoke và replay.
6. Secret scan cho source, test fixture và report.
7. Regression suite cho bug đã từng xảy ra.

### Quản lý test secret

- Secret test được inject từ secret manager/CI protected variable.
- Không in env var hoặc request header ra console.
- Dùng test tenant và issuer riêng.
- Token/certificate test có lifetime ngắn.
- Rotate/revoke sau job hoặc theo lịch.
- Không cho pull request không tin cậy truy cập secret của pipeline protected.

### Flaky test

Các nguyên nhân thường gặp:

- Test phụ thuộc thời gian thực và chạy sát exp.
- Clock giữa runner và test IdP lệch.
- Race trong session/nonce store.
- Rate limit state dùng chung giữa test.
- Email/SMS/MFA delivery bất đồng bộ.
- Callback URL hoặc browser state không được cô lập.
- Test cleanup không hoàn tất.

Dùng fake clock, unique test identity, isolated namespace, polling có deadline và event correlation. Không retry vô hạn để che flaky test.

## 20. Độ tin cậy, concurrency và failure mode

Authentication functional test cần bao gồm các điều kiện vận hành có thể thay đổi kết quả:

- IdP timeout hoặc unavailable.
- JWKS endpoint không refresh được.
- Directory/group lookup timeout.
- Session store read/write failure.
- KMS/HSM signing/decryption unavailable.
- MFA delivery chậm hoặc không tới.
- Network retry và duplicate callback.
- Multi-region revoke propagation delay.
- Clock skew hoặc host resume.
- Browser đóng giữa challenge.

Kỳ vọng chính là hệ thống fail theo policy an toàn, có thể phục hồi và không cấp quyền ngoài ý muốn. Test cũng cần xác minh người dùng hợp lệ có đường thử lại hoặc hỗ trợ phù hợp khi dependency hồi phục.

## 21. Ví dụ test scenario tổng hợp

**Bối cảnh:** Cổng nhân viên dùng OIDC với IdP doanh nghiệp, MFA bắt buộc cho admin và session cookie server-side.

### Scenario: đăng nhập admin thành công

1. Tạo test principal có role Admin trong test tenant.
2. Mở browser context sạch và truy cập protected route.
3. Bắt đầu OIDC Authorization Code Flow với state, nonce và PKCE.
4. Xác thực ở test IdP và hoàn tất MFA.
5. Callback về đúng redirect URI.
6. Backend xác minh state, code, PKCE, ID token, issuer, audience và nonce.
7. Backend tạo session ID mới và cookie theo policy.
8. Truy cập protected route thành công với principal đúng.
9. Audit ghi method, outcome và request reference không có token.

### Scenario: MFA chưa hoàn tất

1. Bắt đầu cùng flow nhưng không approve MFA.
2. Thử truy cập protected route bằng challenge state.
3. Hệ thống từ chối vì chưa có full session.
4. Challenge hết hạn; callback hoặc response cũ không thể hoàn tất login.
5. Metric ghi một attempt và challenge outcome riêng.

### Scenario: revoke trong lúc đang đăng nhập

1. Tạo session và xác nhận request được chấp nhận.
2. Admin/incident workflow revoke session.
3. Gửi request đồng thời qua nhiều app node.
4. Sau propagation deadline, mọi node từ chối session cũ.
5. Refresh token/grant liên quan bị xử lý theo policy.
6. Audit ghi actor, thời điểm và phạm vi revoke.

## 22. Mẫu test case

Ví dụ JSON minh họa một test case có thể lưu trong test management system:

~~~json
{
  "test_id": "AUTH-OIDC-014",
  "requirement": "OIDC callback must validate state and nonce",
  "level": "integration",
  "preconditions": [
    "test user is active",
    "test IdP is configured",
    "browser session has a pending authorization request"
  ],
  "steps": [
    "start authorization code flow",
    "receive callback with mismatched state",
    "observe callback result and session store"
  ],
  "expected": {
    "http_or_ui_result": "authentication rejected",
    "session_created": false,
    "audit_reason": "OIDC_STATE_MISMATCH",
    "secret_logged": false
  },
  "cleanup": [
    "expire test authorization transaction",
    "clear isolated browser context"
  ]
}
~~~

Test case thật cần dùng schema của tổ chức, gắn link requirement và lưu bằng chứng ở nơi được kiểm soát. Không đưa token hoặc password thật vào JSON test artifact.

## 23. Ma trận kiểm thử authentication

| Nhóm | Positive | Negative/boundary | Integration |
|---|---|---|---|
| Password | Credential đúng | Sai, expired, disabled, rate limit | Credential store/verifier |
| MFA/TOTP | Code hợp lệ | Sai, reused, clock skew | Challenge store/provider |
| Push MFA | Approve đúng request | Deny, timeout, stale challenge | Push adapter |
| Passkey | Assertion hợp lệ | Origin, RP ID, challenge, signature sai | Browser/authenticator/server |
| Certificate | Chain hợp lệ | Expired, revoked, wrong SAN/EKU | TLS/mTLS verifier |
| API key | Key active đúng scope | Wrong, revoked, expired | Gateway/key registry |
| JWT | Signature/claims hợp lệ | Issuer/audience/exp/nbf sai | JWKS/token verifier |
| OIDC | Code flow hoàn tất | State/nonce/PKCE mismatch | Test IdP/callback |
| Session | Cookie hợp lệ | Fixation, timeout, revoke | Session store/multi-node |
| Recovery | Reset hợp lệ | Token reused/expired | Email/notification/recovery |
| Authorization boundary | Role/resource đúng | Cross-tenant, client role spoof | Policy/service layer |
| Error/privacy | Error contract đúng | Enumeration/log leakage | Gateway/log/metrics |

Không cần mọi hàng có cùng số test. Ưu tiên theo rủi ro, mức sử dụng, thay đổi gần đây và hậu quả khi sai.

## 24. Tiêu chí hoàn tất một test run

Một test run có thể được xem là hoàn tất khi:

- Test suite chạy trên build và cấu hình được xác định.
- Tất cả test quan trọng có kết quả pass/fail/blocked rõ.
- Failure được phân loại: product defect, environment issue, test defect hoặc flaky.
- Test evidence không chứa secret hoặc dữ liệu production.
- Regression liên quan đã chạy lại sau khi sửa lỗi.
- Known limitation và test chưa chạy được ghi nhận.
- Test report gắn commit/build, environment, test data version và thời điểm.
- Không đánh dấu pass nếu test bị skip hoặc assertion không thực sự kiểm tra hành vi.

Một suite xanh chỉ chứng minh các điều kiện đã được test trong môi trường đó. Nó không chứng minh mọi threat đã được loại bỏ hoặc hệ thống đã qua security review.

## 25. Checklist authentication functional test

- [ ] Test scope và trust boundary được xác định.
- [ ] Yêu cầu có ID và được liên kết với test case.
- [ ] Test identity/credential riêng cho môi trường test.
- [ ] Positive, negative, boundary và state-transition cases được bao phủ.
- [ ] Password policy và credential verification được kiểm tra.
- [ ] MFA, TOTP, push, recovery code và step-up được kiểm tra.
- [ ] Passkey registration/assertion và lifecycle được kiểm tra.
- [ ] JWT/opaque token, issuer, audience, expiry và revocation được kiểm tra.
- [ ] OIDC state, nonce, PKCE, redirect URI và code reuse được kiểm tra.
- [ ] Certificate chain, validity, mTLS và workload identity được kiểm tra.
- [ ] API key, request signature, nonce và replay được kiểm tra.
- [ ] Session rotation, cookie attributes, timeout và logout được kiểm tra.
- [ ] Account recovery và factor replacement được kiểm tra.
- [ ] Authentication được phân biệt với authorization.
- [ ] Tenant isolation và resource ownership được kiểm tra ở server.
- [ ] Clock skew, concurrency, retry và dependency outage được kiểm tra.
- [ ] Error response, account enumeration và privacy được kiểm tra.
- [ ] Log, metric, trace và test artifact không chứa secret.
- [ ] Test có isolation, cleanup, deadline và không flaky không kiểm soát.
- [ ] Kết quả có traceability, evidence, owner và limitation rõ ràng.

## Ghi nhớ

Authentication functional test cần xác minh toàn bộ hành vi từ credential đến trạng thái xác thực có thể sử dụng: challenge, token/session, factor lifecycle, federation, revoke và recovery. Một test thành công phải chứng minh đúng principal, đúng trạng thái và đúng giới hạn quyền; không chỉ kiểm tra response code hoặc giao diện.

Hãy kết hợp positive, negative, boundary, state, integration và end-to-end test; giữ test identity/secret riêng; mô phỏng thời gian và lỗi dependency có kiểm soát; xác minh replay, rotation và revoke trên nhiều node. Tách authentication khỏi authorization, bảo vệ test data và lưu bằng chứng đủ để truy vết mà không làm lộ credential.
