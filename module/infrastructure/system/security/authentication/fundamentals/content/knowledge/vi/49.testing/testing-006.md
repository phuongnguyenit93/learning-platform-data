# Recovery test — Kiểm thử quy trình khôi phục tài khoản an toàn
 
> **Chương:** Testing  
> **Chủ đề:** Recovery test

**Recovery test** là hoạt động kiểm chứng rằng quy trình khôi phục tài khoản hoạt động đúng trong cả tình huống bình thường lẫn tình huống lỗi, đồng thời không tạo ra đường vòng để attacker chiếm quyền. Một recovery flow thường gồm nhận yêu cầu, xác định account, kiểm tra điều kiện, xác minh danh tính, approval nếu cần, phát recovery artifact, tiêu thụ artifact, thiết lập lại credential, thu hồi phiên cũ và thông báo cho chủ tài khoản. Mỗi bước đều có thể gây lỗi bảo mật hoặc làm người dùng bị khóa ngoài tài khoản.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, recovery gắn trực tiếp với password, MFA, passkey, certificate, token, session, identity linking, tenant context và account lifecycle. Kiểm thử phải xác minh rằng recovery chứng minh đúng quyền kiểm soát danh tính, ràng buộc giao dịch với đúng subject và purpose, chống replay/race, giữ assurance phù hợp, cập nhật mọi credential/session liên quan và tạo audit evidence có thể điều tra.

Một recovery flow được coi là thành công về mặt chức năng khi người dùng hợp lệ lấy lại quyền truy cập. Nhưng chỉ được coi là an toàn khi attacker không thể dùng email enumeration, social engineering, token replay, helpdesk bypass, tenant confusion hoặc lỗi đồng bộ để chiếm tài khoản hay giữ session cũ.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Mô hình hóa recovery flow và các trust boundary từ yêu cầu đến hoàn tất.
2. Xác định security invariant cho identity proofing, approval, recovery token và credential replacement.
3. Thiết kế test case positive, negative, boundary, abuse và failure injection.
4. Kiểm tra token/code có entropy, TTL, purpose binding, subject binding và one-time consumption.
5. Phát hiện replay, brute force, enumeration, race condition và concurrent recovery.
6. Kiểm thử recovery cho password, MFA, passkey, certificate và federated identity.
7. Xác minh session, refresh token, API key và credential cũ được xử lý đúng sau recovery.
8. Kiểm tra helpdesk, administrator-assisted recovery, approval và break-glass.
9. Đánh giá tenant isolation, account linking, notification và audit.
10. Xây dựng test automation, staging fixtures, chaos scenarios và production acceptance checklist.

## 2. Recovery flow và phạm vi kiểm thử

Recovery là một chuỗi giao dịch bảo mật, không phải một endpoint duy nhất. Mỗi bước có input, output, authority, expiry và state transition riêng.

~~~mermaid
flowchart TD
    A["Người dùng yêu cầu recovery"] --> B["Resolve account và áp dụng abuse controls"]
    B --> C["Identity proofing / factor verification"]
    C --> D{"Đạt policy?"}
    D -->|"Không"| E["Từ chối an toàn + audit"]
    D -->|"Có"| F["Approval / cooldown nếu cần"]
    F --> G["Phát recovery transaction/token"]
    G --> H["Người dùng tiêu thụ token một lần"]
    H --> I["Thiết lập credential/factor mới"]
    I --> J["Thu hồi credential/session cũ theo policy"]
    J --> K["Notification + audit + monitoring"]
~~~

### 2.1. Các thành phần cần kiểm thử

- Recovery request API và UI;
- Account lookup và identifier normalization;
- Identity proofing và verification factor;
- Email/SMS/push notification provider;
- Recovery token/code issuer và verifier;
- Approval/helpdesk console;
- Credential enrollment service;
- Session/token revocation service;
- Tenant membership và identity mapping;
- Audit log, event bus và monitoring;
- Rate limit, bot defense và abuse detection.

### 2.2. Xác định ranh giới

Test plan cần biết thành phần nào là nguồn authoritative cho:
- Account identity và trạng thái;
- Recovery eligibility;
- Approval decision;
- Recovery transaction state;
- Credential registry;
- Session/token family;
- Tenant membership;
- Notification delivery;
- Audit evidence.

Không coi UI hiển thị “Recovery complete” là bằng chứng backend đã thu hồi session hoặc cập nhật credential.

## 3. Threat model cho account recovery

Attacker thường nhắm vào recovery vì đây là con đường thay thế khi không có credential chính.

| Threat | Mục tiêu | Test cần chứng minh |
| --- | --- | --- |
| Account enumeration | Tìm account tồn tại | Public response không tiết lộ account state |
| Recovery token theft | Chiếm token từ mailbox/device/log | Token không lộ, có TTL và purpose binding |
| Token replay | Dùng lại token đã tiêu thụ | Chỉ một lần thành công |
| Brute force | Đoán recovery code | Rate limit và entropy đủ mạnh |
| SIM swap/mailbox takeover | Chiếm kênh recovery | Kênh không được xem là proof duy nhất khi risk cao |
| Helpdesk social engineering | Thuyết phục support reset account | Proofing, approval, dual control và audit |
| Recovery race | Hai request cùng consume token | Atomic state transition |
| Factor enrollment hijack | Thêm authenticator của attacker | Reauthentication/approval và notification |
| Session persistence | Giữ session attacker sau reset | Revocation theo policy |
| Tenant confusion | Khôi phục nhầm account/tenant | Subject + tenant binding |
| Identity linking abuse | Gắn IdP của attacker vào account nạn nhân | Xác minh quyền kiểm soát cả hai identity |
| Notification suppression | Chủ tài khoản không biết recovery lạ | Delivery/retry và audit |
| Insider misuse | Support/admin dùng quyền quá mức | Least privilege, purpose, approval và review |

### 3.1. Abuse case phải có trong test plan

Không chỉ kiểm thử “quên password thành công”. Cần mô phỏng người không sở hữu account, người có session cũ, attacker kiểm soát một recovery channel, support agent thiếu quyền, và hai request cạnh tranh cùng một transaction.

### 3.2. Phân loại impact

Recovery cho user thông thường, admin, workload identity và account có dữ liệu nhạy cảm cần mức assurance khác nhau. Test phải chứng minh policy đúng với từng class, không chỉ kiểm tra một flow chung.

## 4. Security invariant của recovery

Các invariant là điều kiện luôn phải đúng bất kể UI, provider hoặc thứ tự request.

1. Recovery transaction gắn với đúng principal/account.
2. Transaction gắn purpose cụ thể, ví dụ password reset hoặc factor replacement.
3. Token/code chỉ có hiệu lực trong TTL và chỉ tiêu thụ một lần.
4. Recovery không tự nâng assurance vượt quá proof đã thực hiện.
5. Không thể thay đổi recovery channel bằng chính channel đang được thay mà không có kiểm tra độc lập.
6. Credential mới chỉ được đăng ký sau khi proofing và approval đạt policy.
7. Credential bị mất/compromise được revoke theo policy.
8. Session/token cũ được xử lý theo chính sách đã công bố.
9. Tenant membership và resource authorization được kiểm tra lại.
10. Mọi state transition quan trọng có audit event.
11. Public response không tạo account enumeration ngoài discoverability policy.
12. Một lỗi notification không làm transaction trở thành hợp lệ hoặc làm lộ secret.
13. Retry không làm token dùng nhiều lần hoặc thực hiện side effect lặp.
14. Helpdesk/admin không thể bỏ qua proofing ngoài quy trình được phê duyệt.

## 5. Test fixture và môi trường

Recovery test có thể gây khóa account, revoke session hoặc thay credential. Vì vậy, dùng dữ liệu và provider sandbox riêng.

### 5.1. Fixture tối thiểu

| Fixture | Mục đích |
| --- | --- |
| Account active có password | Password reset happy path |
| Account có passkey và backup key | Phục hồi authenticator |
| Account có TOTP/recovery codes | MFA recovery |
| Account có certificate | Certificate replacement |
| Account bị suspended/disabled | Eligibility và policy |
| Account không tồn tại | Enumeration |
| Account thuộc nhiều tenant | Tenant isolation |
| Admin account | High-assurance recovery |
| Workload identity | Machine credential rotation |
| Helpdesk agent theo role | Authorization và approval |
| Session/token family đang hoạt động | Revocation verification |
| Mail/SMS sandbox inbox | Kiểm tra notification |
| Fake clock/test clock | TTL, expiry và boundary |
| Audit/event collector | Kiểm tra evidence |

### 5.2. Tách môi trường

- Chỉ dùng account giả lập;
- Dùng email/SMS sink hoặc provider sandbox;
- Không gửi recovery message tới người dùng thật;
- Không dùng password, OTP, token hoặc private key production;
- Không thử brute force trên production;
- Không dùng dữ liệu cá nhân thật trong fixture;
- Có thể reset trạng thái test giữa các case;
- Ghi rõ test run ID và cleanup owner.

### 5.3. Test clock

Dùng clock abstraction để kiểm thử trước, đúng và sau expiry mà không cần chờ thật. Đồng hồ giả phải áp dụng nhất quán cho issuer và verifier; vẫn cần integration test với clock skew thực tế.

## 6. Kiểm thử recovery request

### 6.1. Happy path

1. Gửi recovery request với identifier hợp lệ.
2. Xác nhận response contract.
3. Kiểm tra transaction được tạo cho đúng account.
4. Xác nhận notification được enqueue.
5. Kiểm tra transaction có TTL, purpose và trạng thái pending.
6. Tiếp tục flow bằng proof phù hợp.

### 6.2. Invalid và edge cases

- Identifier sai định dạng;
- Identifier không tồn tại;
- Account chưa verify;
- Account disabled/suspended;
- Account không đủ điều kiện recovery;
- Request trùng lặp;
- Request từ source bị throttle;
- Account có nhiều identity/alias;
- Identifier khác chữ hoa/thường hoặc Unicode normalization;
- Phone number có định dạng quốc tế khác nhau.

### 6.3. Account enumeration

So sánh status, body, response schema, redirect và timing giữa account tồn tại/không tồn tại. Public response cần nhất quán theo privacy policy. Không yêu cầu gửi email thật để chứng minh response giống nhau; kiểm tra queue side effect trong test harness.

## 7. Kiểm thử identity proofing

Identity proofing xác định người yêu cầu có đủ bằng chứng để khôi phục account hay không. Cần phân biệt proofing với việc chỉ kiểm tra một kênh liên hệ.

### 7.1. Factor verification

Test các tình huống:
- Password hiện tại còn dùng được;
- Backup passkey/security key;
- TOTP hợp lệ/không hợp lệ;
- Recovery code hợp lệ/đã dùng;
- Email hoặc SMS verification;
- Certificate hoặc smart card;
- IdP assertion/federated proof;
- Helpdesk identity proofing.

### 7.2. Độc lập giữa proof và destination

Nếu người dùng đổi email rồi dùng email mới để xác minh chính việc đổi email đó, flow có thể tự chứng minh bằng dữ liệu do attacker kiểm soát. Test phải đảm bảo recovery destination mới không trở thành bằng chứng duy nhất cho quyền sở hữu account cũ.

### 7.3. Assurance mapping

Mỗi proofing method cần mapping vào policy:
- Factor đã đăng ký trước hay mới cung cấp;
- Có chống phishing không;
- Có ràng buộc với thiết bị/kênh không;
- Có thể bị relay hoặc SIM swap không;
- Có cần approval/cooldown không;
- Action nào được phép sau proof.

Không gán mức assurance cao hơn chỉ vì một factor có tên “MFA” hoặc “verified”.

## 8. Kiểm thử recovery token và code

Recovery artifact có thể là link token, numeric code, recovery code hoặc transaction handle. Nó phải được bảo vệ như credential.

### 8.1. Thuộc tính bắt buộc

- Entropy đủ cao với loại artifact;
- Sinh bằng cryptographically secure random generator;
- Subject/account binding;
- Purpose binding;
- TTL;
- One-time consumption;
- Server-side state hoặc verifier phù hợp;
- Không ghi secret vào log/analytics;
- Không đặt token vào referrer hoặc third-party resource request;
- Có thể revoke khi transaction bị hủy hoặc account state thay đổi.

### 8.2. Token storage

Nếu token có thể dùng trực tiếp, cân nhắc chỉ lưu verifier/hash phía server. So sánh constant-time khi phù hợp. Không lưu raw token trong database/log nếu không cần. Recovery URL cần tránh bị thu thập bởi analytics, proxy log, browser history hoặc referrer header.

### 8.3. Purpose binding

Token reset password không được dùng để thêm passkey, thay email hoặc liên kết IdP. Nếu một transaction cho phép nhiều bước, từng step cần state và authorization riêng.

### 8.4. TTL boundary

Test:
- Token còn hạn một khoảng an toàn;
- Token đúng tại ranh giới expiry;
- Token vừa hết hạn;
- Token hết hạn do transaction bị cancel;
- Token bị revoke sau khi account suspended;
- Token bị thay thế bởi transaction mới.

Không chỉ kiểm tra token có trường exp; verifier phải thực sự enforce expiry theo clock policy.

## 9. Kiểm thử one-time use và replay

One-time use phải được bảo đảm ở server bằng state transition nguyên tử.

### 9.1. Test cơ bản

- Tiêu thụ token lần đầu: thành công;
- Tiêu thụ lần thứ hai: từ chối;
- Dùng token ở purpose khác: từ chối;
- Dùng token với account khác: từ chối;
- Dùng token đã revoke: từ chối;
- Dùng token trong transaction đã hoàn tất: từ chối;
- Dùng token từ client/session không thỏa binding: từ chối nếu policy yêu cầu.

### 9.2. Replay qua endpoint khác

Nếu cùng token có thể gửi tới endpoint password reset và endpoint enroll MFA, test phải chứng minh chỉ endpoint/purpose đã định mới chấp nhận.

### 9.3. Atomic consumption

Hai request đồng thời có thể cùng đọc token ở trạng thái pending. Verifier phải thực hiện compare-and-set hoặc transaction tương đương để chỉ một request chuyển trạng thái pending sang consumed. Kiểm thử bằng concurrency test, không chỉ gửi hai request tuần tự.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant S as Recovery store
    A->>S: Consume transaction T
    B->>S: Consume transaction T
    S-->>A: Atomic transition pending -> consumed
    S-->>B: State already consumed
~~~

## 10. Kiểm thử rate limit và brute-force resistance

Recovery code thường có entropy thấp hơn token dài, nên cần giới hạn thử.

Kiểm tra:
- Giới hạn theo transaction/token reference;
- Giới hạn theo account pseudonym;
- Giới hạn theo source/network/client;
- Progressive delay hoặc challenge;
- Không cho attacker khóa account nạn nhân chỉ bằng request recovery;
- Không reset counter chỉ bằng cách tạo transaction mới;
- Không cho nhiều endpoint có counter độc lập để vượt ngưỡng;
- Alert khi có pattern thử nhiều code;
- Thử từ nhiều IP nhưng cùng transaction/account.

Rate limit không được tiết lộ account existence. Nếu request bị throttle, response cần theo contract privacy và không để header tiết lộ trạng thái account.

## 11. Kiểm thử password reset

Password reset thay đổi một credential có quyền xác thực trực tiếp.

### 11.1. Positive path

- Recovery proof đạt policy;
- Token đúng subject/purpose;
- Password mới đạt length/quality policy;
- Password verifier được cập nhật an toàn;
- Session/token cũ được xử lý đúng;
- Thông báo được gửi tới kênh đã xác minh;
- Audit ghi actor, reason và transaction reference.

### 11.2. Negative path

- Password mới trùng hoặc thuộc breached-password list theo policy;
- Token sai/hết hạn/đã dùng;
- Account bị disable giữa chừng;
- Proofing không đạt;
- Password update bị race với một recovery khác;
- Database update thành công nhưng session revocation thất bại;
- Notification provider lỗi;
- Client retry sau timeout.

### 11.3. Không log password

Test log redaction cả application log, reverse proxy, APM, exception, audit và support tooling. Password không được xuất hiện trong request dump hoặc test report.

## 12. Kiểm thử MFA recovery

MFA recovery có thể ảnh hưởng trực tiếp đến mức bảo đảm của account.

### 12.1. TOTP

- TOTP hợp lệ trong time step;
- Code sai;
- Code hết cửa sổ;
- Code đã dùng lại nếu verifier áp dụng replay prevention;
- Clock skew trong giới hạn;
- Clock skew vượt giới hạn;
- Secret rotation;
- Xóa authenticator cũ sau khi thay.

### 12.2. Recovery code

- Code hợp lệ và one-time;
- Code đã consume;
- Code bị revoke;
- Code sai nhiều lần;
- Code thuộc account khác;
- Bộ code được rotate;
- Không tiết lộ số lượng code còn lại trước proof phù hợp.

### 12.3. Push MFA

- User deny;
- User timeout;
- Push provider outage;
- Repeated prompt;
- Number matching mismatch;
- Approval từ device không phù hợp;
- Challenge không gắn login transaction.

Không xem push timeout là proof thành công. Test phải xác minh một push cũ không thể approve một transaction mới.

## 13. Kiểm thử passkey/WebAuthn recovery

### 13.1. Thêm passkey mới

Recovery flow có thể cho phép người dùng thêm passkey sau khi proofing. Test:
- Reauthentication/step-up theo policy;
- Challenge mới và TTL;
- Origin và RP ID chính xác;
- User verification khi cần;
- Credential ID/public key được lưu đúng account;
- Không thêm credential nếu transaction đã hết hạn;
- Không thể thêm passkey cho tenant/account khác;
- Notification và audit được tạo.

### 13.2. Credential cũ

Nếu thiết bị bị mất hoặc compromise:
- Revoke credential ID ở RP;
- Kiểm tra assertion từ credential cũ bị từ chối;
- Kiểm tra session/token liên quan theo policy;
- Không giả định RP có thể xóa private key trên thiết bị từ xa;
- Xử lý synced passkey ở account hệ sinh thái theo quy trình riêng.

### 13.3. Attestation và device policy

Nếu tổ chức yêu cầu authenticator được quản lý, test attestation trust policy, metadata và privacy behavior. Không dùng attestation như bằng chứng identity proofing của con người.

## 14. Kiểm thử certificate và workload credential recovery

### 14.1. Client certificate

- Certificate mới được cấp đúng principal;
- SAN/EKU/key usage đúng policy;
- Chain tới trust anchor;
- Certificate cũ bị revoke;
- Certificate hết hạn bị từ chối;
- Private key không bị export nếu policy yêu cầu;
- Mapping certificate sang account không bị nhầm.

### 14.2. Workload identity

- Workload được cấp credential mới qua control plane;
- Credential cũ hết hạn/revoke;
- Service không dùng shared static secret làm bypass;
- Audience và scope đúng service đích;
- mTLS peer identity đúng workload;
- Rotation overlap có thời hạn;
- Outage của identity control plane không khiến verifier chấp nhận certificate không tin cậy.

### 14.3. Không làm đứt workload khác

Trong môi trường staging, kiểm tra rotation của một workload không ảnh hưởng service identity khác. Certificate chung hoặc key dùng chung cần được phát hiện vì tăng blast radius.

## 15. Kiểm thử session và token sau recovery

Recovery thành công không đảm bảo attacker đã mất quyền nếu session cũ vẫn còn hiệu lực.

### 15.1. Session inventory

Tạo test fixtures với:
- Browser session;
- Mobile session;
- Refresh token family;
- Remembered device;
- API key;
- Personal access token;
- Federated session;
- Workload credential nếu recovery liên quan service.

### 15.2. Revocation policy

Tùy loại recovery:
- Password reset có thể revoke tất cả session hoặc session không tin cậy;
- MFA factor removal có thể revoke session có risk;
- Passkey compromise cần revoke credential và session liên quan;
- Email/phone change cần step-up và thông báo;
- Account takeover recovery thường cần revoke toàn bộ session/token family;
- Workload key rotation cần thu hồi credential cũ.

Policy phải được định nghĩa trước. Test không giả định mọi recovery đều có cùng hành vi.

### 15.3. Race và propagation

Kiểm tra:
- Session store nhận revoke;
- API gateway và backend cập nhật cache;
- Refresh token rotation từ chối token cũ;
- Event bus không mất revoke event;
- In-flight request xử lý theo policy;
- Logout/revocation được áp dụng trên nhiều region.

## 16. Kiểm thử approval và helpdesk recovery

Human-assisted recovery có nguy cơ social engineering và insider misuse.

### 16.1. Role-based authorization

- Agent không có quyền không thể khởi tạo recovery;
- Agent không thể tự approve yêu cầu của chính mình;
- Tenant support chỉ thao tác tenant được cấp;
- Admin cấp cao cần dual control theo policy;
- Approval hết hạn không được dùng;
- Agent rời tổ chức bị revoke quyền;
- Support action phải có case/purpose.

### 16.2. Separation of duties

Test requester, verifier và approver là các vai trò tách biệt khi policy yêu cầu. Không cho cùng một người thực hiện toàn bộ flow có rủi ro cao.

### 16.3. Audit và notification

Ghi agent ID, approver ID, case ID, subject reference, tenant, purpose, timestamp và quyết định. Notification tới chủ account qua kênh đã xác minh. Không đưa recovery token hoặc bí mật vào ticket.

### 16.4. Không tin thông tin công khai

Test helpdesk từ chối yêu cầu chỉ dựa trên tên, ngày sinh, chức danh, email công khai hoặc thông tin có thể tìm trên mạng. Proofing phải theo quy trình được phê duyệt.

## 17. Kiểm thử tenant isolation và identity linking

### 17.1. Multi-tenant account

- Recovery request cho tenant A không được đổi credential của principal khác ở tenant B;
- Membership revoked không được phục hồi tự động;
- Tenant suspended không được bỏ qua policy;
- Support tenant A không thể reset account thuộc tenant B;
- Tenant ID do client gửi không thay thế server-side mapping.

### 17.2. Identity linking

- Không link IdP chỉ vì email trùng;
- Xác minh quyền kiểm soát identity hiện có và identity mới;
- Token/assertion phải đúng issuer, audience, nonce và thời hạn;
- Một external subject đã link account khác thì flow phải xử lý an toàn;
- Unlink IdP không được làm mất mọi recovery method nếu policy cần dự phòng;
- Audit ghi actor và cả hai identity reference.

### 17.3. Account merge

Account merge là thao tác nhạy cảm. Test quyền trên cả hai account, resource ownership, tenant membership, credential migration, session revocation và khả năng rollback. Không gộp account tự động dựa vào email giống nhau.

## 18. Notification, privacy và account enumeration

### 18.1. Public response

Account tồn tại/không tồn tại nên có response contract nhất quán nếu privacy policy yêu cầu. So sánh:
- HTTP status;
- Body/schema;
- Headers;
- Redirect;
- Timing distribution;
- CAPTCHA/rate limit behavior.

### 18.2. Notification delivery

- Recovery request hợp lệ enqueue đúng một notification;
- Retry không gửi vô hạn;
- Provider outage được retry có giới hạn;
- Không gửi tới địa chỉ do attacker vừa thay mà chưa xác minh;
- Không chứa token trong analytics/log;
- Người dùng có thể báo recovery không do mình khởi tạo;
- Notification không tiết lộ dữ liệu nhạy cảm qua subject/preview.

### 18.3. Privacy và retention

Recovery event có thể chứa identifier, source, device và proofing context. Chỉ lưu dữ liệu cần thiết, hạn chế truy cập và retention. Test quyền truy cập support/analyst và audit khi mở evidence.

## 19. Fault injection và resilience testing

Recovery phụ thuộc nhiều dịch vụ. Cần kiểm thử partial failure để không tạo state nửa vời.

| Thành phần lỗi | Hành vi cần xác minh |
| --- | --- |
| Email/SMS provider outage | Transaction không tự hoàn tất; retry có giới hạn; public response vẫn an toàn |
| Recovery store timeout | Không consume token một phần hoặc tạo session sai |
| Database failover | State transition nhất quán, không nhân đôi credential |
| Audit pipeline outage | Action nhạy cảm xử lý theo policy; không âm thầm mất evidence |
| Session store outage | Không bỏ qua session validation |
| Token revocation outage | Degraded mode hoặc fail closed theo risk |
| IdP outage | Chỉ dùng alternate issuer đã trust hoặc từ chối |
| Clock skew | Expiry và one-time policy vẫn nhất quán |
| Queue redelivery | Notification/job không gây side effect lặp |
| Region partition | Một transaction chỉ được consume theo consistency policy |
| Approval service outage | Không tự động coi approval là granted |
| Rate limiter outage | Fallback limit hoặc fail closed cho flow nhạy cảm |
| Credential registry outage | Không enroll credential khi không thể xác minh account state |

### 19.1. Partial commit

Ví dụ password verifier đã cập nhật nhưng session revoke thất bại. Hệ thống cần transaction/outbox/reconciliation để đưa các bước liên quan về trạng thái nhất quán. Test phải xác minh retry không làm password reset nhiều lần hoặc để credential cũ tiếp tục hoạt động ngoài policy.

### 19.2. Compensation

Một số bước không thể rollback hoàn toàn, như email đã gửi hoặc credential đã được tạo. Thiết kế compensating action: revoke credential mới, cancel transaction, notify owner và yêu cầu điều tra.

## 20. Concurrency, race condition và idempotency

Các request đồng thời thường xuất hiện khi người dùng double-click, client retry hoặc attacker gửi token song song.

Test:
- Hai request consume cùng token;
- Hai password reset cùng account;
- Hai helpdesk agent approve cùng case;
- Factor enrollment đồng thời với factor removal;
- Recovery và account suspension cùng lúc;
- Recovery và session revoke cùng lúc;
- Event revoke tới trước/sau session creation;
- Retry sau khi client timeout nhưng server đã commit.

Dùng idempotency key và state machine có transition nguyên tử. Không dựa vào frontend disable button để bảo vệ one-time operation.

## 21. Test automation và phân lớp kiểm thử

Một recovery test suite nên có nhiều tầng:

| Tầng test | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Unit | Token verifier, state machine, policy function | Boundary, purpose, TTL và state transition |
| Component | Recovery service + database/queue fake | Persistence, idempotency và rollback |
| Integration | IdP, email/SMS sandbox, session service | Trust, token, notification và revocation |
| End-to-end | Browser/mobile flow | UX, accessibility và complete journey |
| Security negative | Replay, tampering, wrong subject/purpose | Bypass resistance |
| Concurrency | Parallel consume/approve/update | Atomicity và race |
| Resilience/chaos | Timeout, outage, partition, redelivery | Failure safety |
| Regression | Known vulnerability scenarios | Ngăn tái xuất hiện lỗi |

### 21.1. Deterministic test

Dùng fake clock, seeded test data, isolated namespace và deterministic provider stub. Không dựa vào sleep dài hoặc provider Internet thật cho unit test.

### 21.2. Property-based test

Có thể tạo nhiều combination của:
- Token state;
- Account state;
- Purpose;
- Subject;
- Expiry;
- Retry count;
- Tenant;
- Concurrent requests.

Property quan trọng: không có input nào làm transaction đã consumed chuyển lại thành pending hoặc cho phép subject khác sử dụng artifact.

### 21.3. Contract test

Kiểm tra API schema, status semantics, event schema, notification contract và error mapping giữa recovery service, IdP, gateway, helpdesk và session service.

## 22. Pseudocode recovery transaction an toàn

~~~text
complete_recovery(token, requested_change, request_context):
    transaction = load_recovery_transaction(token_reference(token))
    require transaction exists
    require transaction.status == PENDING
    require now < transaction.expires_at
    require transaction.purpose == requested_change.purpose

    account = load_account(transaction.subject_id)
    require account exists
    require account.status permits recovery

    verify_token_secret(token, transaction.token_verifier)
    verify_subject_binding(transaction, account)
    verify_proofing_and_approval(transaction)
    enforce_recovery_risk_policy(account, request_context)

    atomically:
        require transaction.status == PENDING
        transaction.status = CONSUMED
        apply_credential_change(account, requested_change)
        record_recovery_audit(account, transaction, requested_change)
        enqueue_session_revocation(account, transaction.policy)
        enqueue_owner_notification(account, transaction)

    return recovery_completed_without_disclosing_secrets()
~~~

Đây là pseudocode khái niệm. Triển khai thực tế cần transaction boundary, outbox, idempotency, concurrency control, secure token comparison, password KDF, WebAuthn/PKI library đã kiểm chứng và xử lý partial failure. Không tự triển khai thuật toán mật mã.

## 23. Test case matrix tổng hợp

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| REC-001 | Account hợp lệ yêu cầu recovery | Tạo transaction pending và notification |
| REC-002 | Identifier không tồn tại | Public response không phân biệt |
| REC-003 | Account suspended | Không hoàn tất recovery ngoài policy |
| REC-004 | Proof hợp lệ | Cho phép bước tiếp theo |
| REC-005 | Proof sai | Từ chối và audit |
| REC-006 | Proof từ channel mới chưa xác minh | Không đủ điều kiện một mình |
| REC-007 | Token đúng subject/purpose | Chấp nhận nếu còn hạn |
| REC-008 | Token sai subject | Từ chối |
| REC-009 | Token sai purpose | Từ chối |
| REC-010 | Token hết hạn | Từ chối |
| REC-011 | Token đã revoke | Từ chối |
| REC-012 | Token replay | Chỉ lần đầu được consume |
| REC-013 | Hai request consume đồng thời | Chỉ một thành công |
| REC-014 | Brute force recovery code | Rate limit/challenge |
| REC-015 | Password reset hợp lệ | Verifier đổi, audit và revoke theo policy |
| REC-016 | Password reset sau khi account bị disable | Từ chối |
| REC-017 | Recovery code đã dùng | Từ chối |
| REC-018 | TOTP ngoài time window | Từ chối |
| REC-019 | MFA push cũ được approve | Không hoàn tất transaction mới |
| REC-020 | Thêm passkey sau recovery | RP/origin/challenge/UV đúng policy |
| REC-021 | Assertion từ origin khác | Từ chối |
| REC-022 | Certificate không trusted | Từ chối |
| REC-023 | Workload credential rotation | Credential mới hoạt động, credential cũ bị xử lý |
| REC-024 | Session cũ sau account takeover recovery | Revoke theo policy |
| REC-025 | Refresh token cũ được reuse | Từ chối/alert |
| REC-026 | Helpdesk agent thiếu role | DENY |
| REC-027 | Requester tự approve | DENY nếu separation required |
| REC-028 | Approval hết hạn | Từ chối |
| REC-029 | Support sai tenant | DENY |
| REC-030 | Identity link theo email trùng | Không tự động link |
| REC-031 | Email provider outage | Không tạo trạng thái hoàn tất giả |
| REC-032 | Audit store outage | Hành động nhạy cảm theo fail policy |
| REC-033 | Session revoke service outage | Outbox/retry hoặc degraded policy |
| REC-034 | Queue redelivery | Không gửi side effect vô hạn |
| REC-035 | Client retry sau timeout | Idempotent result |
| REC-036 | Account suspension race | Không hoàn tất nếu policy không cho phép |
| REC-037 | Tenant membership revoke | Không khôi phục quyền membership |
| REC-038 | Recovery notification | Gửi tới channel đã xác minh |
| REC-039 | Log inspection | Không có password/token/OTP |
| REC-040 | Recovery complete | Credential/session/audit state nhất quán |

## 24. Đo chất lượng recovery

Ngoài việc test pass/fail, cần đo chất lượng và tác động vận hành.

| Metric | Ý nghĩa |
| --- | --- |
| Recovery completion rate | Tỷ lệ flow hợp lệ hoàn tất |
| Recovery abandonment | Người dùng bỏ dở ở bước nào |
| Proofing failure rate | Tỷ lệ proof không đạt |
| Recovery latency | Thời gian từ request tới hoàn tất |
| Token replay rejection | Số lần replay bị chặn |
| Recovery abuse rate | Tỷ lệ request bị đánh dấu abuse |
| False rejection rate | Người hợp lệ bị từ chối nhầm |
| Session revocation latency | Thời gian revoke lan tới service |
| Notification delivery rate | Tỷ lệ notification được provider xác nhận |
| Helpdesk override rate | Tỷ lệ recovery cần human override |
| Cross-tenant deny count | Số attempt truy cập sai tenant bị chặn |
| Audit completeness | Tỷ lệ recovery transaction có đủ evidence |

Không tối ưu completion rate bằng cách làm proofing yếu đi. Cần cân bằng user recovery, account security và support cost.

## 25. Những lỗi kiểm thử thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ test happy path | Bỏ sót replay/race/bypass | Negative, abuse và concurrency suite |
| Test token tuần tự בלבד | Không phát hiện double consume | Parallel race test |
| Chỉ test UI | API có thể bypass | API/component/integration tests |
| Dùng provider thật | Test flaky và gửi tin thật | Sandbox/stub |
| Không kiểm tra session cũ | Attacker vẫn giữ quyền | Session/token inventory test |
| Không test tenant | Cross-tenant recovery | Subject + tenant binding tests |
| Không test notification | Owner không biết recovery lạ | Delivery/retry/privacy test |
| Log raw token để debug | Recovery secret bị lộ | Redaction assertion |
| Dựa vào frontend disable | Request song song vẫn consume | Server-side atomic state |
| Không test outage | Partial state không nhất quán | Fault injection và compensation |
| Test account production | Rủi ro khóa/đổi credential thật | Isolated staging fixtures |
| Không cleanup fixture | Test sau phụ thuộc trạng thái cũ | Reset và cleanup owner |
| Không test clock boundary | Token expiry sai | Fake clock + boundary integration |
| Không review disposition | Không học từ lỗi | Test report và incident mapping |

## 26. Checklist production acceptance

1. **Flow model:** Recovery state machine và trust boundary được tài liệu hóa?
2. **Eligibility:** Account state và recovery policy được kiểm tra server-side?
3. **Proofing:** Factor và identity proofing đáp ứng assurance của action?
4. **Subject binding:** Recovery transaction gắn đúng principal/account?
5. **Purpose binding:** Token chỉ dùng cho đúng mục đích?
6. **Entropy:** Token/code có entropy phù hợp và được sinh an toàn?
7. **TTL:** Expiry được enforce ở issuer và verifier?
8. **One-time:** Atomic consume và replay rejection hoạt động?
9. **Abuse:** Rate limit đa chiều và không tạo lockout DoS?
10. **Enumeration:** Public response không lộ account state?
11. **Credential update:** Password/passkey/MFA/certificate được thay đổi đúng?
12. **Revocation:** Credential/session/token cũ được xử lý theo policy?
13. **Tenant:** Membership và resource authorization được kiểm tra lại?
14. **Helpdesk:** RBAC, purpose, approval, separation of duties và audit?
15. **Notification:** Gửi tới channel đã xác minh, retry idempotent và không lộ secret?
16. **Privacy:** Log, APM, ticket và analytics đã redacted?
17. **Resilience:** Outage/partial commit/retry/queue redelivery được xử lý?
18. **Concurrency:** Parallel consume/approve/change không vượt state machine?
19. **Observability:** Có metric abuse, completion, revocation latency và audit completeness?
20. **Test evidence:** Có test report, fixture cleanup và owner sign-off?

## 27. Bài tập tình huống

Một nền tảng học tập cho phép người dùng reset password bằng link gửi email. Recovery token có TTL 24 giờ và được lưu raw trong database. Endpoint chỉ kiểm tra token đúng, không kiểm tra purpose hoặc account state. Sau khi đổi password, session trên thiết bị cũ vẫn hoạt động. Helpdesk có thể thêm passkey mới nếu người gọi cung cấp tên và email. Một số tenant có policy yêu cầu phishing-resistant MFA cho giảng viên và admin.

**Yêu cầu:**

1. Xác định ít nhất **mười lỗ hổng** trong recovery flow.
2. Thiết kế lại token với entropy, verifier storage, TTL, subject/purpose binding và one-time consumption.
3. Viết test cho replay, concurrent consume, account suspension và token purpose mismatch.
4. Xác định credential/session/token nào phải revoke sau password reset và passkey replacement.
5. Thiết kế helpdesk proofing, approval và tenant-scoped authorization.
6. Đảm bảo recovery không hạ assurance của admin/giảng viên xuống email-only.
7. Viết test cho notification, enumeration, log redaction và provider outage.
8. Đề xuất metric để theo dõi completion, abuse, false rejection và revocation latency.

**Gợi ý đối chiếu:** Token cần verifier, TTL ngắn, subject/purpose binding và atomic one-time use; password reset cần xử lý session cũ; helpdesk cần proofing và separation of duties; tenant policy quyết định assurance; audit và notification phải bảo vệ secret.

## 28. Ghi nhớ

- **Recovery test** kiểm chứng cả chức năng khôi phục và khả năng chống chiếm tài khoản qua đường recovery.
- Recovery là stateful security transaction gồm proofing, approval, artifact, credential change, revocation, notification và audit.
- Token/code cần entropy, TTL, subject binding, purpose binding, one-time consumption và replay protection.
- Concurrency test phải chứng minh chỉ một request tiêu thụ transaction; frontend không thể bảo vệ state machine.
- Password, MFA, passkey và certificate recovery có policy và failure mode riêng.
- Recovery thành công cần xử lý session, refresh token, API key và credential cũ theo risk.
- Helpdesk/admin cần least privilege, purpose, approval, separation of duties và audit.
- Tenant membership và identity linking phải được xác minh; không tự gộp account theo email.
- Fault injection, queue retry, partial commit và provider outage cần được kiểm thử.
- Test fixture phải cô lập; không dùng credential hoặc dữ liệu người dùng production.
- Quality metrics cần đo completion, abuse, false rejection, latency và revocation propagation.

Recovery an toàn khi **người sở hữu hợp lệ có thể khôi phục quyền truy cập bằng bằng chứng phù hợp, còn mọi token, credential, session và thao tác hỗ trợ đều bị ràng buộc với đúng account, purpose, thời hạn và policy**.
