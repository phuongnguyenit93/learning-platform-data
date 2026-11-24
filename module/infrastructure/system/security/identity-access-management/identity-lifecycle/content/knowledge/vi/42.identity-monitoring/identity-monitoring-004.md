# Login anomaly trong IAM: phát hiện đăng nhập bất thường theo ngữ cảnh danh tính

> **Chương:** Identity monitoring  
> **Bài:** Login anomaly  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Bối cảnh:** Theo dõi quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, cấp tài khoản/quyền đến rà soát và thu hồi. Kết nối tín hiệu từ **IdP, SSO, MFA, SCIM, RBAC/ABAC, tài khoản dịch vụ, session/token và audit** nhằm giảm quyền truy cập tồn dư.

## 1. Login anomaly là gì?

Một nhân viên thường đăng nhập vào cổng nội bộ từ một máy đã được quản lý trong giờ làm việc. Hôm nay hệ thống nhận một lần đăng nhập thành công từ client chưa từng ghi nhận, sau nhiều lần MFA bị từ chối. Đây có thể là **một đăng nhập bất thường (login anomaly)**. Nhưng cũng có thể là nhân viên đang đi công tác, đổi thiết bị hoặc dùng VPN doanh nghiệp.

**Login anomaly** là **sự kiện hoặc mẫu hành vi đăng nhập khác đáng kể so với quy luật dự kiến của một danh tính, nhóm người dùng, ứng dụng hoặc môi trường**, được xác định dựa trên các tín hiệu, baseline và ngữ cảnh rủi ro đã được định nghĩa.

Điều quan trọng: **bất thường không đồng nghĩa đã bị tấn công**. Một hệ thống tốt phải phát hiện để **xác minh và phản ứng phù hợp**, không gắn nhãn một người dùng là kẻ tấn công chỉ vì IP khác hoặc giờ hoạt động thay đổi.

Trong IAM, login anomaly giúp trả lời:

- Ai hoặc account nào đang cố truy cập hệ thống?
- Sự kiện diễn ra qua IdP, application SSO, local login hay một loại token/client authentication khác?
- Thành công, thất bại hay bị chặn vì rủi ro/policy?
- Tín hiệu nào khác với lịch sử hoặc chính sách dự kiến?
- Account đang ở giai đoạn Joiner, Mover, Leaver hay đã retired?
- Phiên/token/role nào có thể bị sử dụng sau khi authentication thành công?
- Tài nguyên nào nhạy cảm, ai có trách nhiệm triage và evidence gì cần lưu?
- Khi nào cần step-up MFA, block, session revoke hoặc incident response?

### 1.1. Ví dụ minh họa

~~~text
09:00  User U đăng nhập thành công trên managed laptop thường dùng
09:02  Nhiều lần MFA challenge bị từ chối với user U
09:03  Đăng nhập thành công từ device/browser mới
09:05  User U yêu cầu export báo cáo tài chính

Đánh giá:
  MFA denial burst + new device + sensitive action
  Có thể cần step-up/triage, không tự kết luận account takeover
~~~

Các mốc và identity U ở trên là **dữ liệu giả lập**, không đại diện sự kiện thực.

### 1.2. Mục tiêu bài học

Sau bài này, người đọc có thể:

1. Phân biệt login anomaly với failed login, policy violation, attack indicator và confirmed account compromise.
2. Xác định log fields, nguồn dữ liệu và trust boundary cho detection.
3. Xây baseline cho người dùng, nhóm, ứng dụng, thiết bị, địa lý và vòng đời.
4. Đánh giá tín hiệu impossible travel, unfamiliar device, MFA fatigue, password spray, credential stuffing và session/token misuse theo đúng giới hạn.
5. Thiết kế risk scoring, correlation, suppression, tuning và xử lý false positives.
6. Liên kết IdP/SSO/OIDC/SAML, PAM, RBAC/ABAC với JML và quyền nhạy cảm.
7. Xây playbook điều tra, containment, recovery và evidence/audit.
8. Thử nghiệm detection bằng tập dữ liệu an toàn, đánh giá false positive/false negative và cải tiến liên tục.

## 2. Phân biệt anomaly, indicator, incident và risk

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Authentication event** | Một lần thử xác thực được hệ thống ghi nhận | Login failed vì password sai |
| **Login anomaly** | Sự kiện/mẫu khác baseline | Login lúc giờ chưa từng thấy |
| **Threat indicator** | Tín hiệu có thể gắn với hành vi tấn công | Nhiều account bị thử từ một IP |
| **Policy violation** | Hành vi trái quy tắc đã ban hành | Login vào admin console khi account đã disabled |
| **Detection alert** | Kết quả rule/model cần xử lý | High-risk sign-in |
| **Investigation case** | Tập bằng chứng được analyst triage | Case có IP, MFA, device và resource access |
| **Security incident** | Sự cố đã/đang có khả năng ảnh hưởng an toàn cần ứng phó | Account compromise được xác nhận |
| **False positive** | Detection đánh dấu đáng nghi nhưng hành vi hợp lệ | Người dùng đổi điện thoại có approval |
| **False negative** | Hành vi xấu không bị phát hiện | Token hợp lệ bị lạm dụng không có login mới |

Một login anomaly thường là **tín hiệu đầu vào**, không phải kết luận cuối cùng. Để khẳng định account takeover cần xem thêm sessions, token issuance, entitlement change, privileged actions, owner verification và evidence.

### 2.1. Một login thất bại chưa phải bất thường

Người dùng gõ sai password một lần có thể bình thường. Hàng nghìn lần thất bại trên nhiều users trong cửa sổ ngắn có thể đáng chú ý. Baseline, thresholds, account sensitivity và source context quyết định.

### 2.2. Thành công cũng cần giám sát

Một attacker đã có credential hợp lệ có thể tạo ra một login **thành công** không gây nhiều thất bại trước đó. Chỉ theo dõi password failure rate sẽ bỏ sót unknown device, unusual protocol, stolen session hoặc access sau Leaver.

### 2.3. Không phải mọi bất thường đều liên quan đăng nhập

Một OAuth access token cũ được sử dụng để truy cập API dù không xuất hiện sign-in event mới. Đây có thể là **token/session anomaly** hoặc **authorization anomaly**, liên quan identity monitoring nhưng không nên gán sai là “new login from IP”.

## 3. Kiến trúc giám sát Login anomaly

~~~mermaid
flowchart TD
    HR[HRIS / JML / Identity Registry] --> CTX[Trusted Identity Context]
    IDP[IdP Authentication + MFA Logs] --> BUS[Event Ingestion]
    RP[SSO RP / Application Login] --> BUS
    PAM[PAM / Privileged Login] --> BUS
    TOK[OAuth Token / Session Logs] --> BUS
    BUS --> NORM[Normalize + Validate + Deduplicate]
    NORM --> DET[Rules / Baselines / Risk Scoring]
    CTX --> DET
    DEVICE[Device / Network / Threat Context] --> DET
    DET --> DEC{Risk / Confidence / Policy}
    DEC -- Low --> AUDIT[Audit + Feedback]
    DEC -- Medium --> STEP[Step-up / Reverify]
    DEC -- High --> SOC[Analyst Triage / Containment]
    STEP --> AUDIT
    SOC --> AUDIT
    AUDIT --> TUNE[Review False Positives and Drift]
    TUNE --> DET
~~~

Các thành phần có chức năng riêng:

- **Nguồn đăng nhập:** IdP, local auth, SAML/OIDC relying parties, PAM.
- **Nguồn định danh:** HRIS, identity governance, account status, manager/team, lifecycleVersion, service registry.
- **Nguồn thiết bị/mạng:** endpoint management, known-device bindings, VPN, proxy, network risk.
- **Phát hiện:** quy tắc logic, correlation, thống kê hoặc anomaly model.
- **Phản ứng:** kiểm tra lại, MFA step-up, revoke session, block account, điều tra.
- **Audit:** evidence, quyết định và hiệu quả sau xử lý.

### 3.1. Control plane và data plane

IdP có thể deny login mới, nhưng một ứng dụng vẫn chấp nhận local session hoặc access token còn hạn. Monitoring phải phân biệt:

1. **Identity control plane:** account active/disabled, roles, policies.
2. **Authentication plane:** signin outcome, MFA, token issuance.
3. **Application/data plane:** API access, resource actions, session usage.

Một rule “login after Leaver” có thể không phát hiện quyền tồn dư dùng qua **phiên đã tạo trước khi Leaver**. Cần theo dõi cả data-plane access khi rủi ro yêu cầu.

### 3.2. Near-real-time và batch

- **Near-real-time detection:** phù hợp MFA bombing, credential stuffing, privileged login bất thường.
- **Batch analytics:** phù hợp dormant accounts, baseline dài hạn, low-frequency abuse, recertification.
- **Periodic reconciliation:** đối chiếu inventory/role/account states với nguồn JML.

Không có chế độ nào thay tất cả. Rule near-real-time có thể không có đủ context tại thời điểm đầu; hỗ trợ enrichment và cập nhật case khi evidence tới trễ.

## 4. Dữ liệu tối thiểu cho một Sign-in event

Một bản ghi cần đủ để liên kết request với **principal, kết quả xác thực, ngữ cảnh và evidence** nhưng không làm lộ credentials.

| Nhóm | Trường tiêu biểu |
|---|---|
| Event | eventId, eventType, emittedAt, ingestedAt, schemaVersion |
| Identity | principalId, principalType, tenantId, identitySource |
| Application | appId, relyingPartyId, targetResource, authenticationProtocol |
| Result | outcome, failureReason, policyDecision, errorCategory |
| Source | sourceIp, networkType, trustedProxyContext |
| Device | trustedDeviceId, deviceManaged, deviceCompliant, clientType |
| Geographic | derivedCountry/region, confidence, geoDbVersion |
| Authentication | authMethod, amr/acr khi có, MFA outcome, authenticationTime |
| Session | sessionReference, tokenType, tokenIssuer, audience, tokenGrantType |
| Risk | detectorId, detectorVersion, features, score, confidence |
| Lifecycle | identityStatus, lifecycleVersion, effectiveAt, riskTier |
| Correlation | requestId, correlationId, relatedEventIds, alertId |
| Audit | evidenceRef, responseAction, reviewer, policyVersion |

Không phải mọi provider có đủ tất cả trường. Thiếu thiết bị tin cậy, issuer hoặc user mapping phải được ghi là **UNKNOWN**, không tự gán SAFE.

### 4.1. Không log secret

Không lưu password, one-time passcode, private key, raw OAuth bearer token, refresh token, session cookie, authorization header hoặc full ID token chứa PII trong hệ thống detection. Dùng opaque references hoặc token metadata đã được xác minh từ nguồn phù hợp.

### 4.2. Stable identity thay username

Email và displayName có thể đổi hoặc tái sử dụng. Kết nối login events với **immutable principal ID + tenant + issuer/source**. Với SSO, issuer+subject thường giúp phân biệt tài khoản ngoài giữa nhiều IdP.

### 4.3. Client IP có thể không phải IP thực tế

Ứng dụng sau proxy/CDN phải chọn client address theo **trusted proxy chain**. Không tin header X-Forwarded-For do client tùy ý gửi; nếu sai, attacker có thể thao túng geo/risk score.

### 4.4. Thời gian phải so sánh đúng

Dùng timestamp offset-aware/UTC cho processing; phân biệt:

- eventTime: lúc sign-in xảy ra.
- ingestedAt: khi pipeline nhận.
- authTime: thời điểm người dùng được xác thực theo IdP.
- receivedAt: thời điểm RP nhận response.
- effectiveAt: thời điểm JML policy có hiệu lực.

Clock drift, delayed ingestion và retries có thể khiến sự kiện đến không theo thứ tự.

### 4.5. Event completeness là một thuộc tính kiểm soát

Một dashboard không có suspicious logins có thể chỉ phản ánh source chưa phát events. Theo dõi ingest lag, heartbeat, missing event rate, schema failures và source-to-sink reconciliation.

## 5. Các loại Login anomaly theo tín hiệu

| Dạng | Điều bất thường | Cách có thể sai |
|---|---|---|
| **Unfamiliar location** | Vị trí IP khác thói quen | VPN, CGNAT, IP geo sai |
| **Impossible travel** | Hai sign-ins quá gần về thời gian nhưng địa lý xa | Cloud proxy, mobile switching, inaccurate location |
| **New device/browser** | Thiết bị/client chưa có lịch sử | Thiết bị mới, xóa cookies, privacy browser |
| **Unusual time** | Sign-in ngoài baseline làm việc | Ca đêm, on-call, travel |
| **Password spray** | Nhiều accounts có password failures từ một nguồn | Proxy công ty chung |
| **Credential stuffing** | Tỷ lệ thử credentials tự động cao | Traffic do security test cho phép |
| **MFA fatigue / push bombing** | Nhiều challenges/denials rồi một approval | User thao tác nhầm/notification issue |
| **Protocol anomaly** | Legacy auth hoặc flow không thường dùng | Migration/tool compatibility |
| **New app/resource** | Client truy cập app nhạy cảm chưa từng dùng | Job mới, quyền mới hợp lệ |
| **Privileged sign-in anomaly** | Admin đăng nhập khác điều kiện cho phép | Emergency/JIT window được duyệt |
| **Dormant identity reactivated** | Account lâu không dùng bất ngờ login | Quay lại dự án có approval |
| **Post-Leaver sign-in** | Login attempt sau cutoff | Sync delay, stale credential, local login |
| **Session/token anomaly** | Token được dùng không có auth context phù hợp | Token refresh, legitimate SSO, log coverage |
| **Service credential anomaly** | Workload identity dùng từ runtime khác | Deployment migration được duyệt |

### 5.1. Signal đơn lẻ vs phối hợp

Một IP lạ có thể low confidence. IP lạ **kèm** MFA denials, new device, OAuth consent bất thường và lần export dữ liệu đầu tiên có thể nâng độ ưu tiên điều tra. Correlation cần thời gian, principal ID và user/asset context đáng tin.

### 5.2. Tách anomaly score và risk impact

Một hành vi cực kỳ hiếm trên account chỉ có quyền đọc tài liệu công khai có impact khác với hành vi ít hiếm hơn trên cloud organization-admin. Risk-based decision cần xét **likelihood/confidence** và **business impact** riêng.

### 5.3. Unknown không mặc định malicious hoặc safe

Nếu device telemetry trống, không tự coi thiết bị là unmanaged hoặc compliant. Có thể đánh giá mức assurance thấp hơn và yêu cầu step-up tùy chính sách, nhưng phải ghi rõ sự thiếu dữ liệu.

## 6. Impossible travel: cách hiểu và những giới hạn

**Impossible travel** thường được tính khi hai sign-ins cùng principal được định vị từ IP ở hai địa điểm cách xa mà khoảng thời gian giữa chúng không đủ để di chuyển vật lý theo giả định.

### 6.1. Mô hình đánh giá đơn giản

~~~text
User U:
  Sign-in A: 09:00, IP geo gần Tokyo
  Sign-in B: 09:20, IP geo gần Singapore

Tín hiệu:
  Khoảng cách lớn so với khoảng thời gian
  Nhưng cả hai vị trí là IP-derived, có sai số

Cần kiểm tra:
  Cloud proxy / VPN / corporate egress?
  Location confidence và IP classification?
  Hai sign-ins là interactive hay token refresh?
  Thời gian được ghi nhận ở cùng time basis?
  Có device/session continuity hay MFA anomaly?
~~~

Các vị trí chỉ minh họa; **IP geolocation không chứng minh chính xác người dùng đang ở địa điểm đó**.

### 6.2. Công thức trực giác

Với khoảng cách địa lý ước lượng d giữa hai IP locations và khoảng thời gian Δt:

\[
v_{\mathrm{ước\ tính}} = \frac{d}{\Delta t}
\]

Một v quá lớn có thể là detection signal. Nhưng d/Δt chỉ có ý nghĩa khi hai điểm đại diện đáng tin cho vị trí người; với cloud egress, VPN hoặc proxy toàn cầu, công thức có thể tạo nhiều false positives.

### 6.3. Loại nguồn gây nhiễu

- VPN tunnel qua trung tâm ở quốc gia khác.
- Corporate ZTNA/SASE egress đổi vị trí.
- Carrier NAT và mobile network.
- IP blocks geolocation chưa cập nhật.
- Cloud-hosted login agent hoặc automation.
- Sign-in không tương tác, refresh token hoặc federated redirect bị ghi là login mới.
- Shared IP, time skew hoặc duplicated events.

### 6.4. Không xử lý bằng “khóa account ngay lập tức” một cách máy móc

Cần risk policy. Với user thường, có thể yêu cầu step-up và triage. Với privileged account cộng các tín hiệu mạnh, có thể tạm chặn phiên/token theo quy trình sự cố. Luôn có phương án cho legitimate travel/on-call để tránh gây outage hoặc ngăn quyền truy cập khẩn cấp.

### 6.5. Từ geographic alert tới investigation

Kết hợp device continuity, passkey/credential details không nhạy cảm, MFA events, sign-in source, privileged grants, access to sensitive resources và user verification qua kênh đáng tin. Không hỏi người dùng gửi password hoặc mã OTP để chứng minh danh tính.

## 7. Phát hiện password spray và credential stuffing

Hai kiểu tấn công có thể cùng tạo authentication failures nhưng có mẫu hành vi khác.

### 7.1. Password spray

Password spray thường là thử **một hoặc vài mật khẩu phổ biến trên nhiều accounts**, nhằm tránh ngưỡng khóa từng user.

Một detection ở mức khái niệm:

~~~text
Trong cửa sổ T:
  nhiều distinct principals có password failures
  từ một nguồn hoặc tập nguồn có liên hệ
  với tỷ lệ thành công thấp
  và hành vi không phù hợp expected automation

Tăng risk nếu:
  target gồm admin hoặc dormant accounts
  xuất hiện ngay sau một đợt password reset
  có một account success sau nhiều failures cùng chiến dịch
~~~

### 7.2. Credential stuffing

Credential stuffing thường tự động thử nhiều cặp username/password bị lộ. Một source có thể phân tán qua nhiều IP và user-agents; chỉ rate-limit theo một IP không đủ.

Tín hiệu bổ trợ: distributed attempts, low success ratio, many accounts, unusual client fingerprints, recent credential compromise evidence nếu có nguồn hợp pháp và tin cậy.

### 7.3. Account lockout có thể trở thành DoS

Nếu khóa mỗi user sau vài failures từ Internet, attacker có thể cố tình khóa hàng loạt accounts. Thay vì chỉ dùng hard lockout, cân nhắc adaptive rate limits, risk-based challenges, bot controls, passwordless/passkeys và escalation theo policy.

### 7.4. Không gọi mọi burst là attack

Một misconfigured application retry dùng password cũ có thể tạo nhiều failures. Detection cần phân loại service accounts vs human, client app, failure reason và approved security tests để tránh gây outage.

### 7.5. Password spray sau Leaver

Một Leaver account đã disabled vẫn bị thử login có thể cho thấy attackers quét credentials cũ, nhưng không chứng minh identity có thể truy cập được. Đánh giá thêm nếu local SaaS login vẫn tồn tại hoặc access token cũ tiếp tục được chấp nhận.

## 8. MFA anomaly, fatigue và step-up abuse

MFA tăng assurance nhưng cũng tạo tín hiệu bảo mật hữu ích khi có mẫu challenges bất thường.

### 8.1. Những mẫu nên chú ý

| Tín hiệu | Diễn giải có thể | Kiểm tra thêm |
|---|---|---|
| Nhiều MFA prompts trong thời gian ngắn | Push bombing hoặc retry lỗi | User context, client/request IDs |
| Nhiều denials rồi một approval | Có thể fatigue/social engineering | Device/session và actor verification |
| Đổi MFA method ngay trước privileged sign-in | Có thể enrollment takeover | Approval, recovery process |
| MFA bypass theo exception | Có thể cấu hình sai | Policy, reason, expiry |
| Không thấy MFA ở admin login | Auth path không qua expected step-up | amr/acr/policy decision |
| Đăng nhập với authentication method mới | Có thể user migration hợp lệ | Device enrollment, owner |
| Nhiều failed recovery attempts | Nguy cơ recovery abuse | Recovery policy/actor |

### 8.2. MFA prompt count không đủ

Một user làm mới nhiều browser tabs hoặc có kết nối lỗi cũng có thể nhận nhiều prompts. Phải correlation theo challenge ID, authentication request, RP và successful/denied outcome.

### 8.3. Không yêu cầu user đọc OTP trong triage

SOC/helpdesk không nên yêu cầu user gửi OTP, backup codes, password hay approve một push mới chỉ để “xác nhận bất thường”. Dùng kênh xác minh danh tính ngoài luồng, không hướng dẫn hành vi làm suy yếu MFA.

### 8.4. Step-up không tự nâng quyền

MFA step-up xác minh assurance, không tự tạo RBAC role. Sau login đáng nghi, resource server vẫn phải kiểm tra action, resource, tenant, session freshness và entitlement validity.

## 9. New device, browser và client protocol

### 9.1. Device ID không phải danh tính bất biến tuyệt đối

Cookies bị xóa, trình duyệt đổi profile, thiết bị reset hoặc phiên remote desktop có thể làm detector thấy “new device”. Phải phân biệt device registered/managed/compliant với browser fingerprint phỏng đoán.

### 9.2. Những tín hiệu đáng tin hơn

- Device binding do tổ chức quản lý, attestation nếu có.
- MDM/EDR compliance được xác nhận.
- Certificate/passkey registration events.
- Device posture và access decision ở ZTNA.
- Trạng thái approved device enrollment trong identity lifecycle.

Không phải mọi browser có các signals này. Thiếu thiết bị quản lý không tự chứng minh attacker.

### 9.3. Legacy authentication và protocol downgrade

Một account thường dùng OIDC với MFA nhưng đột ngột đăng nhập qua legacy protocol không hỗ trợ controls mong đợi có thể là anomaly. Kiểm tra vendor/app protocol, migration exceptions và chính sách block. Không gắn “legacy” thành lỗi nếu hệ thống không hỗ trợ cơ chế khác và có ngoại lệ hợp lệ, nhưng vẫn đánh giá risk.

### 9.4. Passwordless và passkeys

Nếu đăng nhập sử dụng passkey đúng origin/device binding theo hợp đồng, một số kiểu phishing risk được giảm; tuy nhiên session theft, token replay, recovery abuse và sai authorization vẫn cần phát hiện. Không coi passwordless là lý do bỏ giám sát session/token.

## 10. Thiết lập baseline hành vi có ý nghĩa

Baseline là mô hình điều gì được xem là bình thường hoặc dự kiến trong ngữ cảnh một principal, nhóm hay ứng dụng. Không có baseline đáng tin, nhiều detector chỉ tạo ra cảnh báo “lần đầu nhìn thấy” mà không biết hành vi đó có rủi ro hay không.

### 10.1. Các mức baseline

| Baseline | Dùng khi | Giới hạn |
|---|---|---|
| **Per-principal** | User có lịch sử ổn định | Cold start của Joiner |
| **Per-peer group** | Nhân viên cùng role, ca trực, ứng dụng | Có thể chuẩn hóa sai hành vi đặc quyền |
| **Per-application** | App có luồng login khác nhau | Một app có nhiều nhóm user khác biệt |
| **Per-tenant** | SaaS multi-tenant có policies riêng | Một tenant có thể rất không đồng nhất |
| **Per-device** | Thiết bị được quản lý và có identity ổn định | Device rotation và reset |
| **Per-workload** | CI/job/service principal xác thực tự động | Deployment migration/rollouts |
| **Per-season/time** | Ca trực, payroll closing, chiến dịch | Có thể học nhầm hành vi tấn công lặp |

### 10.2. Cold start của Joiner

Nhân viên Joiner chưa có lịch sử. Nếu detector mặc định mọi login đầu tiên là high risk, đội vận hành sẽ bị alert flood. Có thể dùng baseline theo nhóm, thông tin enroll/approved device, startDate, department và authentication method; ghi rõ confidence thấp vì dữ liệu lịch sử chưa đủ.

### 10.3. Baseline sau Mover

Một nhân viên đổi sang trực đêm có thể bắt đầu login lúc 22:00. Những đợt Mover hợp lệ cần được dùng làm context để điều chỉnh expected schedule. Tuy vậy, **không cho phép behavior bất thường tự biến thành “normal”** chỉ vì lặp vài lần; cần policy và trusted business event.

### 10.4. Baseline không phải allowlist vĩnh viễn

Một trusted network hoặc managed device vẫn có thể bị compromised. Account có lịch sử đăng nhập từ IP A không đồng nghĩa mọi request từ A luôn an toàn. Biện pháp allowlist/suppression phải có scope, owner, expiry và review.

### 10.5. History window và data quality

Window quá ngắn bỏ sót hành vi theo mùa, window quá dài khiến role/công việc cũ ảnh hưởng hiện tại. Cần xác định retention và drift strategy; không tự định nghĩa “30 ngày là đủ” cho mọi doanh nghiệp. Đánh giá missing logs, timezone, unusual shifts và retention policy.

### 10.6. Không tạo baseline từ dữ liệu đã có compromise

Nếu một account bị kẻ xấu dùng trong nhiều ngày và toàn bộ hoạt động ấy được coi là bình thường, model có thể giảm khả năng phát hiện. Feedback từ incident response nên gắn nhãn/suppress dữ liệu độc hại khi retraining theo quy trình có audit.

## 11. Risk scoring: từ tín hiệu đến quyết định

Một điểm anomaly chỉ cho biết độ khác biệt theo một mô hình. Quyết định có block/step-up không còn phụ thuộc **độ tin cậy bằng chứng, trạng thái account, entitlement, dữ liệu nhạy cảm và policy**.

### 11.1. Ví dụ chấm điểm minh họa

~~~text
Feature                              Points minh họa
Known corporate VPN egress          -10
Unfamiliar device                   +15
Rare country IP                     +15
MFA denial burst                    +25
New privileged app                  +20
Leaver identity after cutoff        +50
Verified managed/compliant device   -10

RiskScore = clamp(0, 100, sum(feature points))
~~~

**Trọng số chỉ để học cách kết hợp**, không phải ngưỡng production hoặc công thức được kiểm chứng. Một rule Leaver có thể dùng hard policy deny độc lập với score; không nên cho điểm âm từ VPN hợp lệ làm “xóa” vi phạm account đã disabled.

### 11.2. Tách ba khía cạnh

1. **Anomaly magnitude:** hành vi hiếm đến đâu so với baseline?
2. **Evidence confidence:** dữ liệu và mapping có đáng tin không?
3. **Business risk/impact:** nếu identity bị chiếm, hậu quả ra sao?

Một mô hình có thể tạo score 90 vì sai IP geolocation nhưng confidence thấp. Một cloud-admin account có score thấp hơn nhưng một verified privileged policy violation vẫn cần ưu tiên.

### 11.3. Risk-based response policy

| Tình huống | Hướng phản ứng khả dĩ |
|---|---|
| Ít tín hiệu, confidence thấp | Log + bổ sung telemetry, không làm gián đoạn |
| Unfamiliar device, user bình thường | Step-up hoặc kiểm tra device theo policy |
| Nhiều MFA denials + success + action nhạy cảm | Triage ưu tiên cao, xem session/token |
| Disabled Leaver account có successful local login | Chặn/revoke và điều tra residual access |
| Privileged login từ unapproved runtime | Block hoặc JIT/re-auth theo policy |
| Suspected account takeover có evidence mạnh | Incident response, containment theo runbook |

Response phải cân nhắc khả năng self-service recovery và tác động vận hành. Không tự khóa hàng nghìn người dùng khi một detection rule mới chưa được thử nghiệm.

### 11.4. Rule deterministic và statistical anomaly

- **Policy rule:** “Account retired nhưng login success” có thể là vi phạm rõ nếu identity mapping, cutoff và event outcome đáng tin.
- **Statistical rule:** “User thường login 09:00, nay 02:00” chỉ là sai khác baseline; cần enrichment.
- **Correlated rule:** “MFA denials + new device + privileged role action” có tín hiệu mạnh hơn.

Không dùng một risk score trừu tượng thay việc đánh giá rule nào có hiệu lực chắc chắn.

### 11.5. Explainability là điều kiện vận hành

Một alert nên ghi rõ lý do như “new device + MFA denial burst + production-admin scope”, detector version, eventRefs và baseline reference. Nếu analyst không thể giải thích vì sao score tăng, rất khó kiểm tra false positives và mức rủi ro.

### 11.6. Tránh cộng điểm các tín hiệu trùng nhau

Unfamiliar country và impossible travel có thể đều dựa trên cùng IP geo sai. Nếu coi hai feature độc lập và cộng trọn điểm, detector có thể thổi rủi ro. Cần correlation, feature dependencies và confidence handling.

## 12. Correlation theo principal, thời gian và hành vi sau đăng nhập

Một cuộc tấn công có thể xuất hiện qua nhiều event sources:

~~~mermaid
sequenceDiagram
    participant Auth as IdP / MFA
    participant Risk as Detection Engine
    participant RP as Business Application
    participant IAM as IAM / JML Registry
    participant SOC as SOC / Response
    Auth->>Risk: Sign-in failed bursts + MFA denials
    IAM->>Risk: Principal status, role, current entitlements
    Auth->>Risk: Successful login, new device
    RP->>Risk: Sensitive action requested
    Risk->>Risk: Correlate events and confidence
    Risk->>SOC: Risk case with evidence references
    SOC->>RP: Verify resource action and session
    SOC->>Auth: Revoke/step-up via approved playbook
    SOC->>Risk: Case disposition and feedback
~~~

### 12.1. Join events đúng khóa

Tối thiểu có thể dùng **tenant + issuer/identitySource + immutable principalId**. Bổ sung authentication request ID, app/client ID, device reference và correlation ID đáng tin để nối events. Email chỉ nên là thuộc tính tra cứu.

### 12.2. Correlation windows

Một detector có thể quan sát burst MFA trong vài phút và resource action trong một cửa sổ tiếp theo. Chọn window dựa trên SLA/behavior của ứng dụng, kiểm tra event lateness và không gắn nhầm hai phiên không liên quan chỉ vì user ID giống nhau.

### 12.3. Sự kiện đến muộn

Nếu token issuance log ingest sau resource access log, không suy ngược rằng token xuất hiện sau request. Sử dụng eventTime có độ tin cậy, source sequence và ingestionLag; với evidence không đầy đủ, cho phép case update/reassessment.

### 12.4. Session binding

Hai requests cùng principal không chắc cùng một phiên. Nếu công cụ cho phép, gắn session reference được bảo vệ, token issuance reference hoặc auth correlation; **không lưu raw bearer token** chỉ để so khớp.

### 12.5. Theo dõi hành vi sau successful login

Một sign-in có vẻ bình thường nhưng ngay sau đó tạo OAuth app consent bất thường, tải nhiều dữ liệu hoặc đổi MFA methods có thể nâng rủi ro. Điều tra theo **chuỗi hoạt động**, không chỉ một màn hình login history.

## 13. IdP, SSO, OIDC/SAML và login anomaly

### 13.1. Một người, nhiều nơi phát sign-in logs

- **IdP:** user authentication, MFA, risk-based policy, token issuance.
- **Relying Party (RP):** nhận OIDC/SAML response, tạo local session, mapping role.
- **Application local login:** có thể tồn tại ngoài IdP.
- **PAM/JIT:** privileged activation/authentication.
- **Cloud console/API:** federated sign-in, role assumption, token exchange.

Không mặc định một IdP sign-in event đồng nghĩa ứng dụng RP đã cấp session thành công, cũng không mặc định RP có cùng issuer, tenant hoặc user ID.

### 13.2. OIDC ID token khác access token

- **ID token:** xác nhận authentication tới OIDC client/RP trong luồng phù hợp.
- **Access token:** được resource server dùng cho authorization theo audience/scope/profile.
- **Refresh token:** có thể xin token mới khi hợp lệ.
- **Session cookie:** ứng dụng có thể duy trì local session.

Một refresh hoặc API access không nhất thiết tạo **interactive login mới**. Detectors nên phân loại eventType và token flow để tránh báo “login from new country” sai khi token được đổi bởi backend hoặc proxy.

### 13.3. SAML/OIDC account mapping

Nếu RP dùng email chưa xác minh để link account thay vì trusted issuer+subject, detector có thể gộp hai identities hoặc bỏ sót một account takeover path. Identity matching phải theo contract federation và namespace đúng.

### 13.4. Policy về MFA và step-up

MFA events ở IdP nên được correlate với đúng RP request/assurance. User login có MFA không có nghĩa mọi action cần MFA đều được phép: resource-side RBAC/ABAC vẫn cần kiểm tra. Nếu RP không thấy tín hiệu assurance kỳ vọng, đánh dấu context gap hoặc policy violation theo khả năng log.

### 13.5. Session fixation và session reuse

Một RP giữ anonymous session ID qua authentication có nguy cơ session fixation. Đây có thể được phát hiện thông qua session lifecycle audit hoặc regression test, không chỉ IP-based login anomaly. Kiểm tra old-ID không còn truy cập authenticated principal.

### 13.6. SSO logout và các phiên RP

User bị disable tại IdP sau Leaver nhưng RP session còn hạn có thể tiếp tục truy cập theo cách ứng dụng triển khai. Monitoring cần cả sign-in attempts **và** data-plane authorization/session activity sau cutoff.

## 14. Joiner–Mover–Leaver: anomaly phải hiểu trạng thái vòng đời

### 14.1. Joiner: first login có thể hoàn toàn hợp lệ

Một nhân viên mới chưa có lịch sử thiết bị và IP. Đừng đánh dấu mọi first login nguy hiểm. Dùng HRIS startDate, employee onboarding status, approved enrollment event, device registration và expected application list làm context đáng tin.

Một detection hữu ích hơn là **login thành công vào production app trước ngày active theo policy**, không phải “new login”.

### 14.2. Mover: hành vi mới phải so với quyền mới

Nhân viên chuyển team từ Finance sang Operations có thể bắt đầu dùng app mới và đổi lịch làm việc. Update baseline hợp lý nhưng đồng thời kiểm tra:

- Quyền Finance đã được revoke đúng effectiveAt?
- Có successful access vào tài nguyên Finance sau Mover không?
- Group/role mapping có stale?
- Có privileged role mới chưa có approval?
- Session/token cũ còn cho quyền cũ không?

Một login hiếm vào Finance sau Mover có thể quan trọng hơn login hiếm vào Ops app đã được duyệt.

### 14.3. Leaver: phân loại trước và sau cutoff

~~~text
HRIS Leaver effectiveAt: 2026-11-23T10:00:00Z

09:59 successful login:
  Có thể hợp lệ về mặt cutoff; kiểm tra policy khác

10:01 failed login tại IdP:
  Có thể chứng minh IdP block hiệu quả

10:02 successful local SaaS login:
  Có thể là residual access nếu đúng user/app và policy

10:03 API call với old token:
  Không nhất thiết có interactive login mới,
  nhưng cần kiểm tra effective authorization
~~~

Ví dụ timeline giả lập để phân biệt các loại evidence. **Không tự gọi một failed login là compromise**; điều đáng lo có thể là successful access qua đường khác.

### 14.4. Guest và contractor

Guest identities có thể có effectiveAt theo hợp đồng/sponsor, không nằm trong HRIS như nhân viên. Dùng nguồn có thẩm quyền tương ứng, review sponsor, contract end, resource scope và guest local sessions.

### 14.5. Leaver owner của service identity

Kỹ sư quản lý một workload nghỉ không đồng nghĩa workload phải ngừng. Monitoring nên phát hiện **human owner còn vault/admin access** hoặc orphan service principal, đồng thời tránh tự block production job hợp lệ chỉ vì owner đã Leaver.

### 14.6. Role/entitlement làm tăng impact

Một user thuộc cloud-admin hoặc finance-approver có blast radius lớn hơn viewer. Correlate login anomaly với effective RBAC/ABAC grants hiện tại và policy version, không dùng cached group list cũ khiến đánh giá sai.

## 15. Privileged logins, PAM và break-glass

### 15.1. Những event quan trọng

- Admin sign-in ngoài approved JIT activation window.
- Privileged role assumed lần đầu, từ device/runtime chưa được duyệt.
- Break-glass/emergency account dùng bất ngờ.
- Admin login không đạt expected MFA/assurance.
- Privileged session active sau role expiration.
- Service account dùng human interactive login bất thường.
- Permission elevation ngay sau sign-in high risk.

### 15.2. Break-glass có baseline khác account thường

Emergency account hiếm khi được dùng. Điều đó không có nghĩa mọi use là attack: có thể là sự cố vận hành. Nhưng cần alert ưu tiên cao, approval/incident reference, dual control khi policy yêu cầu, time-bounded session và hậu kiểm.

### 15.3. JIT/PAM không thay event monitoring

Một privilege activation hợp lệ có thể bị sử dụng sai sau đó. Giám sát role assumption, privileged action, session recording/metadata khi phù hợp, và authorization decisions tại resource. Không lưu raw credential vào audit chỉ để tiện điều tra.

### 15.4. Tỷ lệ false positive phải tương xứng tác động

Một false positive chặn break-glass giữa outage có thể gây hậu quả nghiêm trọng. Thiết kế escalation path, human override có kiểm soát và audit, đồng thời không miễn kiểm tra hoàn toàn các accounts khẩn cấp.

## 16. Non-human accounts và service/workload login anomaly

Các **non-human identities** như service principals, integration accounts, CI/CD bots và managed identities có mô hình xác thực khác người dùng. Detector phải phân loại principalType.

### 16.1. Những tín hiệu NHI đáng chú ý

| Tín hiệu | Rủi ro khả dĩ | Kiểm tra |
|---|---|---|
| Client credentials từ runtime lạ | Secret bị dùng ngoài ứng dụng | Allowed workload/host/network |
| STS token issuance ngoài deployment window | Job/trust bị lạm dụng | Issuer/subject/audience |
| Service principal gọi app khác thường | Lateral movement/role creep | Resource audience và grants |
| Service key cũ vẫn dùng sau rotation | Credential tồn dư | Key ID/status và timeline |
| Token issuance sau service retirement | Trust chưa thu hồi | Registry, policy, STS logs |
| CI identity từ repo/branch không duyệt | Federation trust quá rộng | Trusted subject claims |
| Interactive login bằng technical user | Sai identity use hoặc credential abuse | Vendor capability, exception |
| API key dùng chéo tenant | Tenant isolation failure | Principal/tenant/resource check |

### 16.2. Không áp impossible travel cho mọi service

M2M token được cấp tại cloud regions hoặc egress IP khác nhau có thể là vận hành bình thường. Baseline NHI nên dựa trên **workload identity, deployment region, namespace, trusted issuer/subject, client grant, expected audience/resource và schedule** hơn là lịch trình di chuyển của người.

### 16.3. Credential rotation và owner

Khi old key vẫn được dùng ngoài overlap window, tạo alert nhưng xác minh ứng dụng đang phụ thuộc key đó hay có compromise. Rotation credential không tự thu hồi role; còn phải review grants của principal.

### 16.4. SCIM connector đặc quyền

Một SCIM provisioning connector có thể disable users hoặc thêm group, nên login/token anomaly của connector cần severity theo privileged action. Đồng thời phân biệt migration hợp lệ với secret dùng từ location khác.

### 16.5. Service Leaver

Khi service retired, monitoring có thể flag any new token issuance, active credential use hoặc resource access sau effectiveAt. Đây có thể là bằng chứng residual non-human access; cần target readback và đối chiếu dependency trước khi chấm dứt.

## 17. Session, token và authorization sau login

Một successful login không phải điểm kết thúc. Attacker có thể:

- Dùng session cookie được chiếm thay vì login mới.
- Dùng access token đã phát trước khi tài khoản bị disable.
- Thêm một OAuth consent hoặc refresh token.
- Tạo API key/long-lived credential từ quyền hiện có.
- Tận dụng direct resource ACL ngoài nhóm IdP.
- Gửi data-plane requests từ một workload đã được tin.

### 17.1. Tách ba câu hỏi

1. **Authentication:** principal nào được xác thực ở lần nào?
2. **Session/token:** bằng chứng nào còn dùng được và có lifetime gì?
3. **Authorization:** action/resource nào vẫn được chấp nhận theo policy hiện tại?

Một detection chỉ đếm sign-ins sẽ không trả lời đầy đủ hai câu cuối.

### 17.2. Token audience và issuer

Resource API cần validate token theo profile, gồm issuer, audience, signature/introspection, lifetime và authorization context. Token được phát hợp lệ không tự cho phép mọi resource/tenant.

### 17.3. Post-revoke monitoring

Sau khi Leaver hoặc grant REVOKE, cần theo dõi target access outcome. Một denied request có thể cho thấy một kiểm soát hoạt động, còn một permitted sensitive action sau cutoff cần investigation. Nhưng không suy toàn hệ thống đã an toàn từ một endpoint trả 403.

### 17.4. Session revoke chưa chắc tức thời

IdP session, RP session, OAuth refresh/access token, PAM activation và local API key có vòng đời khác nhau. Nếu provider không hỗ trợ revoke tức thời của token đã phát, ghi risk window và biện pháp giảm rủi ro theo policy.

## 18. Điều chỉnh alert và xử lý false positives

Nếu phát quá nhiều alerts không có giá trị, analyst sẽ bỏ qua tín hiệu quan trọng hoặc tự động hóa phản ứng gây gián đoạn.

### 18.1. Các nguồn nhiễu thường gặp

- Approved travel và changing time zones.
- New laptop/enrollment.
- VPN/SASE cloud egress.
- Shift workers, on-call, emergency response.
- Scheduled batch logins và machine clients.
- Password rotation làm client retries.
- Synthetic probes, authorized penetration tests.
- Duplicated/out-of-order sign-in events.
- IdP vs RP log duplication.
- Thiếu trusted identity mapping.

### 18.2. Tuning không nên chỉ xóa rule

Có thể:

1. Thêm context về approved travel, registered device, JML và work schedule.
2. Chuẩn hóa loại sign-in (interactive vs non-interactive).
3. Dedup cùng request ID.
4. Thay threshold theo risk tier và peer group.
5. Kết hợp nhiều independent signals thay single-IP anomaly.
6. Suppress được phê duyệt theo scope và expiry.
7. Phân biệt report-only vs enforce mode để thử rule.
8. Lưu analyst disposition/feedback và kiểm tra chất lượng model.

### 18.3. False positive vs false negative là trade-off

Tăng sensitivity có thể bắt nhiều tình huống hơn nhưng tăng false positives. Giảm alert volume bằng threshold quá cao có thể bỏ sót compromise. Đo theo use case/risk tier, không tối ưu một metric chung cho mọi hệ.

### 18.4. Fairness và privacy

Nhân viên làm ca đêm, remote, ở quốc gia khác hoặc thường dùng công nghệ hỗ trợ có thể bị gắn nhãn bất thường nhiều hơn. Tránh biến tín hiệu hành vi thành đánh giá nhân phẩm, hiệu suất hay đặc điểm nhạy cảm; giới hạn use case vào bảo mật, quyền truy cập và policy đã thông báo.

### 18.5. Feedback loop có kiểm toán

Khi analyst đánh dấu BENIGN_TRAVEL hoặc CONFIRMED_COMPROMISE, lưu reason/evidence, người quyết định, detector version và hiệu lực suppression. Không để feedback thiếu thẩm quyền tự sửa policy hoặc cho một account vào allowlist vĩnh viễn.

## 19. Ví dụ log đăng nhập và alert có cấu trúc

Một hệ thống monitoring nên phân biệt **raw event**, **normalized event** và **detector output**. Dưới đây là schema giả lập để minh họa; mỗi IdP/vendor có API và trường khác nhau.

### 19.1. Normalized sign-in event

~~~json
{
  "eventId": "signin-evt-2841",
  "schemaVersion": "1.0",
  "eventType": "INTERACTIVE_SIGN_IN",
  "eventTime": "2026-11-23T02:15:10Z",
  "ingestedAt": "2026-11-23T02:15:12Z",
  "identity": {
    "principalId": "employee-1042",
    "principalType": "HUMAN",
    "identitySource": "corporate-idp",
    "tenantId": "tenant-a",
    "lifecycleStatus": "ACTIVE",
    "lifecycleVersion": 107
  },
  "application": {
    "appId": "finance-portal",
    "protocol": "OIDC",
    "authRequestRef": "auth-request-472"
  },
  "authentication": {
    "outcome": "SUCCESS",
    "method": "PASSWORD_PLUS_MFA",
    "mfaResult": "APPROVED",
    "assurance": "provider-defined"
  },
  "network": {
    "clientIp": "203.0.113.42",
    "networkClassification": "UNCLASSIFIED",
    "geoRegion": "illustrative-region",
    "geoConfidence": "LOW"
  },
  "device": {
    "trustedDeviceRef": "device-new-8",
    "managed": "UNKNOWN",
    "knownForPrincipal": false
  },
  "correlationId": "auth-flow-2841"
}
~~~

IP **203.0.113.42** thuộc dải địa chỉ dành cho ví dụ; không đại diện người dùng thật. Không thể dùng một event này để khẳng định account takeover.

### 19.2. Alert tương ứng

~~~json
{
  "alertId": "alert-login-2841",
  "detectorId": "correlated-login-risk-v3",
  "detectorVersion": "3.4.0",
  "principalRef": "employee-1042",
  "tenantId": "tenant-a",
  "riskTier": "HIGH",
  "riskScore": 72,
  "confidence": "MEDIUM",
  "status": "PENDING_TRIAGE",
  "signals": [
    {"code": "UNFAMILIAR_DEVICE", "eventRef": "signin-evt-2841"},
    {"code": "MFA_DENIAL_BURST", "eventRef": "mfa-window-010"},
    {"code": "SENSITIVE_APP", "eventRef": "app-catalog-finance"}
  ],
  "policy": {
    "id": "signin-risk-policy",
    "version": "7"
  },
  "recommendedAction": "STEP_UP_AND_ANALYST_REVIEW",
  "evidenceRefs": ["evidence/login-case-2841"],
  "createdAt": "2026-11-23T02:15:13Z",
  "correlationId": "auth-flow-2841"
}
~~~

Score 72 và action chỉ là **giá trị minh họa**. Production phải có policy owner, calibration, threshold tests và khả năng xử lý trường hợp gián đoạn thiết bị hoặc xác thực hợp lệ.

### 19.3. Kết quả triage được ghi riêng

~~~json
{
  "caseId": "login-case-2841",
  "alertId": "alert-login-2841",
  "triageOutcome": "BENIGN_APPROVED_DEVICE_MIGRATION",
  "reviewerRole": "SOC_ANALYST",
  "decisionTime": "2026-11-23T02:25:00Z",
  "verificationMethod": "TRUSTED_OUT_OF_BAND",
  "incidentRequired": false,
  "controlChanges": [],
  "notesRef": "case-notes/2841"
}
~~~

Không đưa password, MFA OTP, raw session cookie hoặc full personal documents vào notes. Triage outcome không tự thêm permanent allowlist.

### 19.4. Audit provenance

Một event trông giống JSON đúng schema chưa chắc đáng tin. Pipeline phải xác thực producer, chống duplicate/replay ở mức nguồn, xác minh mapping principal/tenant và giữ metadata về source/ingestion. Nếu có field do client tự khai, cần đánh dấu untrusted.

## 20. Chính sách phát hiện và phản ứng minh họa

### 20.1. Policy YAML giả lập

~~~yaml
loginAnomalyPolicy:
  policyId: signin-risk-policy
  version: "7"
  scope:
    principalTypes: [HUMAN, PRIVILEGED_HUMAN]
    targetApplications: [finance-portal, admin-console]
  dataQuality:
    requireTrustedPrincipalMapping: true
    missingDeviceState: UNKNOWN
    rejectUntrustedForwardedIp: true
  detectors:
    - id: mfa-denial-burst
      signal: MANY_MFA_DENIALS_SAME_PRINCIPAL
      correlateWithinSeconds: 300
    - id: unfamiliar-device-with-sensitive-app
      signals: [UNFAMILIAR_DEVICE, SENSITIVE_APP]
      correlateWithinSeconds: 600
    - id: post-leaver-interactive-success
      signal: LOGIN_SUCCESS_AFTER_LIFECYCLE_CUTOFF
      deterministicPolicyCheck: true
  response:
    low: AUDIT
    medium: STEP_UP_MFA
    high: ANALYST_TRIAGE_AND_CONTAINMENT
  controls:
    suppressionRequiresOwnerAndExpiry: true
    evidenceWithoutRawTokens: true
    doNotAutomaticallyBlockEmergencyAccounts: true
~~~

Đây là **policy học tập**, không phải schema được IdP hoặc SIEM cụ thể hỗ trợ. Những số giây và cách ánh xạ risk bands cần hiệu chỉnh theo use case và dữ liệu thực; không triển khai copy/paste vào production.

### 20.2. Tách rules theo loại principal

HUMAN dùng device familiarity, MFA, work pattern. NHI cần workload proof, issuer, subject, audience, runtime và key issuance. Một YAML rule kiểu “IP quốc gia lạ” không nên áp như nhau cho browser user và CI/CD service principal.

### 20.3. Enforce và report-only

Khi thêm rule mới, có thể chạy trong report-only để đo false positives, baseline và trải nghiệm người dùng. Chuyển sang enforce sau khi đã xác minh detection quality, exception path và owner; với dấu hiệu compromise chắc chắn/vi phạm policy nghiêm trọng, phải dùng kiểm soát hiện hành thích hợp thay vì chờ model.

### 20.4. Policy version và audit

Mỗi alert nên chỉ ra ruleVersion, policyVersion, feature data quality và response. Khi rule đổi, giữ lịch sử để diễn giải vì sao cùng một event có outcome khác ở hai thời điểm.

## 21. Pseudocode: correlate và đánh giá Login anomaly

### 21.1. Luồng phát hiện ở mức thiết kế

~~~text
function evaluateLoginEvent(rawEvent):
    event = trustedIngestion.validateAndNormalize(rawEvent)

    if event is INVALID:
        quarantineWithReason(rawEvent.reference)
        return NO_DECISION

    principal = trustedIdentityCatalog.find(
        event.issuer,
        event.tenant,
        event.immutablePrincipalId
    )

    if principal is UNKNOWN:
        emitIdentityMappingGap(event)
        return NEEDS_ENRICHMENT

    if event.eventId already processed:
        recordDeduplication(event.reference)
        return ALREADY_PROCESSED

    if event.type is NON_INTERACTIVE_WORKLOAD:
        return evaluateWorkloadSignals(event, principal)

    baseline = getVersionedBaseline(principal, event.appId)
    device = getTrustedDeviceContext(event.deviceRef)
    recentMfa = correlateMfaByAuthenticatedRequest(event)
    sensitiveActions = correlateAppEventsByTrustedSession(event)

    signals = detectIndependentSignals(
        event, baseline, device, recentMfa, sensitiveActions
    )

    lifecycleViolation = evaluateLifecyclePolicy(
        principal.status,
        principal.effectiveAt,
        principal.sourceVersion,
        event.eventTime,
        event.outcome
    )

    if lifecycleViolation is VERIFIED:
        emitHighPriorityCaseWithEvidence(event, signals)
        return POLICY_ESCALATION

    score = calibratedRiskScore(signals, principal.riskTier)
    confidence = assessSignalQuality(signals, event.dataQuality)

    action = policy.chooseResponse(score, confidence, principal)

    recordDecisionWithoutSecrets(
        event.reference, signals, score, confidence, action
    )
    return action
~~~

Pseudocode không thể tự đảm bảo exactly-once processing, quality của identity mapping hoặc orchestration với IdP. Sản phẩm thật cần concurrency guards, retry handling, durable outbox, versioning và approval cho sensitive remediation.

### 21.2. Khi event thiếu dữ liệu

Nếu IP bị thiếu hoặc device state UNKNOWN, detector có thể tạo signal DATA_GAP và giảm confidence. Không suy unknown country = foreign attacker hoặc unknown device = untrusted device một cách tuyệt đối.

### 21.3. Sự kiện sign-in bị denied

Một denied login sau Leaver là chứng cứ có yêu cầu truy cập nhưng có thể là dấu hiệu control đang hoạt động. Không gắn là successful residual access; lưu cả policyDecision và observedOutcome.

### 21.4. Rủi ro xử lý out-of-order

Nếu event Leaver version=109 được xử lý trước một event Mover version=108 đến muộn, không cho phép login context bị “khôi phục” về ACTIVE. Dùng authoritative current lifecycle state và version guard.

### 21.5. Correlation phải tôn trọng tenant

Không gộp identity cùng email giữa hai tenants thành một principal, cũng không tính một IP shared NAT là attacker duy nhất. Dùng namespace và evidence relationship đúng.

## 22. Java: một bộ đánh giá tín hiệu tối giản

Mẫu này minh họa cách phân biệt **risk features** với **kết luận triage**. Nó không phải hệ thống nhận diện compromise hoàn chỉnh và không thực hiện block network.

~~~java
import java.time.Instant;
import java.util.Objects;

record SignInObservation(
        String principalId,
        String tenantId,
        Instant occurredAt,
        boolean loginSucceeded,
        boolean unfamiliarDevice,
        boolean mfaDenialBurst,
        boolean sensitiveApp,
        boolean lifecycleInactiveAtEvent
) {}

record LoginRiskResult(
        int score,
        String tier,
        boolean deterministicLifecycleViolation
) {}

final class LoginRiskEvaluator {

    static LoginRiskResult evaluate(SignInObservation event) {
        Objects.requireNonNull(event, "event");
        Objects.requireNonNull(event.principalId(), "principalId");
        Objects.requireNonNull(event.tenantId(), "tenantId");
        Objects.requireNonNull(event.occurredAt(), "occurredAt");

        if (!event.loginSucceeded()) {
            return new LoginRiskResult(0, "EVALUATE_FAILURE_PATTERN", false);
        }

        // Weights are illustrative, not production-calibrated.
        int score = 0;

        if (event.unfamiliarDevice()) score += 15;
        if (event.mfaDenialBurst()) score += 25;
        if (event.sensitiveApp()) score += 20;

        if (event.lifecycleInactiveAtEvent()) {
            // A policy violation must not be erased by a low score.
            return new LoginRiskResult(100, "POLICY_ESCALATION", true);
        }

        score = Math.min(100, score);
        String tier = score >= 60 ? "HIGH"
                : score >= 30 ? "MEDIUM" : "LOW";

        return new LoginRiskResult(score, tier, false);
    }
}
~~~

Các boolean **phải được tạo từ detector và authoritative context đã xác thực**; không nhận flags tùy ý từ frontend. Giá trị HIGH không chứng minh attacker: sự kiện phải tiếp tục qua policy/analyst response. Trong production, cần treatment cho UNKNOWN, confidence, duplicate features, rule versions, device trust, token type, action risk và privacy.

### 22.1. Tại sao không lưu IP trong mã Java này?

Mục tiêu code là minh họa việc tổng hợp signals. IP, issuer và device metadata nên được chuẩn hóa ở lớp ingestion và kiểm tra ở detector chuyên biệt; không cho một chuỗi IP chưa được xác thực quyết định cuối cùng.

### 22.2. Tại sao failed login cho score 0?

Đoạn code chủ ý **không chấm điểm failed login đơn lẻ**; nó trả về chỉ dẫn EVALUATE_FAILURE_PATTERN để hệ thống password spray/MFA denial đánh giá theo cửa sổ. Trong hệ thống thật, failed events cần được lưu, correlate và phát hiện thích hợp; không phải bỏ qua.

### 22.3. Không dùng boolean lifecycleInactiveAtEvent do client tự gửi

Giá trị này cần được tính theo status và effectiveAt có thẩm quyền, policy version và eventTime đã xác minh. Nếu chỉ nhận một field do request bên ngoài cung cấp, attacker có thể sửa để giảm rủi ro.

## 23. SQL: phát hiện các mẫu đăng nhập bất thường

Ví dụ PostgreSQL read model dùng bảng normalized_signins có một hàng/event, gồm event_time, principal_id, tenant_id, client_ip, outcome, app_id, is_interactive và is_privileged. Cú pháp minh họa cần điều chỉnh theo schema/retention của hệ thống thật.

### 23.1. Nhiều account thất bại từ một IP trong cửa sổ

~~~sql
SELECT
    tenant_id,
    client_ip,
    COUNT(*) AS failed_attempts,
    COUNT(DISTINCT principal_id) AS distinct_principals
FROM normalized_signins
WHERE event_time >= :windowStart
  AND event_time < :windowEnd
  AND outcome = 'FAILURE'
  AND is_interactive = TRUE
  AND tenant_id = :authorizedTenantId
GROUP BY tenant_id, client_ip
HAVING COUNT(DISTINCT principal_id) >= :minDistinctUsers
ORDER BY distinct_principals DESC;
~~~

Đây là **candidate password spray signal**, không chứng minh brute force thành công hoặc một actor duy nhất vì IP có thể là NAT/proxy. Với distributed attacks cần correlate thêm nhiều nguồn.

### 23.2. Successful privileged sign-ins từ client mới

Giả định bảng có feature known_device đã được tính từ data source đáng tin:

~~~sql
SELECT
    principal_id,
    app_id,
    event_time,
    correlation_id,
    detector_version
FROM normalized_signins
WHERE outcome = 'SUCCESS'
  AND is_privileged = TRUE
  AND known_device = FALSE
  AND event_time >= :windowStart
  AND event_time < :windowEnd
  AND tenant_id = :authorizedTenantId
ORDER BY event_time DESC;
~~~

Không suy known_device = FALSE từ NULL/UNKNOWN; thiếu telemetry cần logic riêng.

### 23.3. Sign-in sau Leaver cutoff

Giả định bảng authoritative_identity_lifecycle có current event-sourced projection đầy đủ theo principal và tenant:

~~~sql
SELECT
    s.principal_id,
    s.app_id,
    s.event_time,
    s.outcome,
    l.effective_at,
    l.status,
    s.correlation_id
FROM normalized_signins s
JOIN authoritative_identity_lifecycle l
  ON s.principal_id = l.principal_id
 AND s.tenant_id = l.tenant_id
WHERE l.status = 'LEAVER'
  AND s.event_time >= l.effective_at
  AND s.event_time >= :windowStart
  AND s.event_time < :windowEnd
  AND s.tenant_id = :authorizedTenantId;
~~~

Truy vấn này là **candidate review**: projection current status có thể không đủ để tái hiện lifecycle **as-of** một event lịch sử; production nên join với hiệu lực theo thời gian, sourceVersion/validity intervals và mapping đáng tin. Phân biệt SUCCESS và FAILURE trước khi kết luận residual access.

### 23.4. Tránh nhầm số attempts và số người

COUNT(*) đếm events, COUNT(DISTINCT principal_id) đếm principals trong scope. Một user 100 lần thử từ proxy dùng chung khác với 100 users một lần thử; dashboard cần hiển thị cả hai.

### 23.5. Không phải mọi sự kiện là interactive login

Token refresh/STS issuance có thể có IP cloud khác. Không dùng chung query impossible travel của human browser nếu không lọc eventType và authentication context chính xác.

## 24. Playbook triage: từ alert tới evidence

### 24.1. Tiếp nhận alert

Analyst thu thập alert ID, principal ID, app, risk tier, eventTime, detector version, tín hiệu, source confidence và case history. Xác minh event đến từ nguồn tin cậy, tránh điều tra dựa vào field giả.

### 24.2. Kiểm tra identity và JML

- Identity là employee, contractor, guest hay workload?
- Status/effectiveAt/current role trong HRIS/IAM là gì?
- Có approval cho travel, Mover, JIT, emergency access không?
- Owner và contact cập nhật?
- Có access request/role grant mới trước anomaly?
- Account có lịch sử compromise hoặc alerts liên quan?

### 24.3. Xem authentication detail

- Thành công/thất bại/bị block?
- Interactive, legacy, token refresh hay service client auth?
- MFA challenge/denial/approval và assurance?
- Thiết bị registered/managed/unknown?
- IP classification, proxy/VPN, geo confidence?
- RP/IdP correlation và token issuance?

### 24.4. Kiểm tra hoạt động sau xác thực

- Có admin role activation hoặc permission change?
- Có export/download, login vào app mới hoặc API access bất thường?
- Session/token nào còn active, có revoke được không?
- Có consent grant, new credential hoặc secondary access tạo mới?
- Có hành vi tương tự trên identities khác cùng nguồn không?

### 24.5. Xác minh người dùng bằng kênh đáng tin

Nếu cần hỏi người dùng, sử dụng kênh nội bộ đã được xác minh; không phản hồi vào email/chat khả nghi trong event và không yêu cầu password/OTP/approve push như bằng chứng. Giới hạn thông tin chia sẻ và bảo vệ quyền riêng tư.

### 24.6. Phân loại kết quả

| Disposition | Ý nghĩa | Hành động |
|---|---|---|
| BENIGN_EXPECTED | Hành vi hợp lệ, có context | Đóng case với evidence, tuning có scope |
| BENIGN_ENVIRONMENT_CHANGE | VPN/device/migration hợp lệ | Điều chỉnh baseline sau approval |
| SUSPICIOUS_UNCONFIRMED | Tín hiệu mạnh nhưng thiếu chứng cứ kết luận | Step-up/containment theo rủi ro, tiếp tục điều tra |
| CONFIRMED_POLICY_VIOLATION | Trái control có thẩm quyền | Khắc phục, audit finding nếu phù hợp |
| CONFIRMED_COMPROMISE | Có evidence chiếm quyền | Incident response |
| DATA_INSUFFICIENT | Logs/mapping thiếu | Khắc phục telemetry, giữ dấu vết |
| FALSE_ALERT_RULE_ERROR | Detector hoặc schema sai | Fix rule và regression test |

### 24.7. Đảm bảo analyst không tự xóa bằng chứng

Case disposition phải có actor, timestamp, evidenceRef, policy version, reason, triage result. Việc false positive không có nghĩa xóa raw event lịch sử hoặc xóa tất cả future alerts của user.

## 25. Incident response và containment theo mức rủi ro

Khi anomaly đi kèm bằng chứng compromise hoặc quyền critical còn usable, có thể phải xử lý ngay, không chờ đợt access review tiếp theo.

### 25.1. Các bước khả dĩ

1. Xác minh scope của event, principal/tenant và tài nguyên.
2. Xác định user sessions, OAuth clients, API keys, privileged roles liên quan.
3. Áp chính sách containment phù hợp: block login, revoke sessions/refresh tokens, disable grants/credentials.
4. Xử lý access tokens đã phát theo khả năng resource server và SLA.
5. Reset/rotate compromised credentials theo quy trình được phê duyệt.
6. Giám sát secondary identities, OAuth consent, service principals và sharing.
7. Thu thập/bảo toàn audit logs, request correlation, owner decisions.
8. Phục hồi identity và quyền hợp lệ có kiểm chứng.
9. Theo dõi repeated anomalies, xác minh effective closure.
10. Feedback detector, document root cause, xử lý finding nếu có control deficiency.

### 25.2. Không cứ alert là phải disable user

Block một account quan trọng hoặc SCIM connector có thể gây outage. Quyết định dựa severity, confidence, có evidence compromise hay không, quyền hiện có và escalation path. Có thể dùng step-up/re-auth cho medium risk; với verified high-risk compromise thì containment có thể cần ngay theo policy.

### 25.3. Token revoke không đồng nghĩa mọi data-plane request bị chặn

Một số self-contained access tokens vẫn có thể được resource server chấp nhận đến expiration nếu không có online revocation/entitlement check. Ghi residual window và dùng compensating controls khi cần; không báo “all access revoked” chỉ từ IdP disable.

### 25.4. Recovery có SoD và audit

Khi mở lại account sau false positive/incident, không tự cấp mọi role cũ mà không kiểm tra business need, JML effective status và entitlement validity. Ghi owner approval, mốc restore, allowed sessions và target readback.

### 25.5. Liên kết với identity audit finding

Nếu phát hiện root cause là không terminate RP sessions sau Leaver hoặc SCIM group mapping thiếu, có thể phát sinh audit finding có criteria–condition–cause–risk–corrective action. Incident response xử lý cấp bách; audit CAPA giải quyết nguyên nhân dài hạn.

## 26. Case study: Finance Portal xuất hiện login anomaly sau MFA denials

### 26.1. Bối cảnh

Một tổ chức có HRIS, IdP, Finance Portal qua OIDC, MFA, EDR/MDM và SIEM. Nhân viên U thuộc nhóm finance.viewer, được giao một số report; những hành động export tài liệu nhạy cảm cần policy bổ sung.

Một buổi sáng hệ thống ghi nhiều MFA challenges bị từ chối, sau đó có successful login trên browser mới. Analyst phải phân biệt **người dùng mới đổi thiết bị** với **credential đã bị lộ hoặc bị social-engineering**.

### 26.2. Timeline giả lập

| Thời gian (UTC+07:00) | Nguồn | Event | Nhận xét |
|---|---|---|---|
| 09:00 | IdP | Login success trên managed laptop quen thuộc | Baseline bình thường |
| 09:02 | MFA | 4 push challenges bị từ chối | Có signal MFA fatigue |
| 09:03 | IdP | Login success trên client chưa từng ghi nhận | Cần xem device/source |
| 09:03 | Identity registry | User U đang ACTIVE | Không vi phạm Leaver |
| 09:04 | RP | New local session được tạo | Phải kiểm auth/session binding |
| 09:05 | Finance Portal | Request export sensitive report | Resource impact tăng |
| 09:06 | SIEM | Correlated login alert HIGH | Case, chưa phải compromise đã xác nhận |
| 09:07 | SOC | Step-up/temporary containment theo policy | Giảm rủi ro |
| 09:12 | User verification | User phủ nhận phiên mới qua kênh nội bộ tin cậy | Evidence đáng chú ý |
| 09:15 | Incident workflow | Nghi compromise, revoke sessions/credential | Theo runbook |
| 09:25 | Resource API | Quyền export qua phiên nghi vấn bị deny | Bằng chứng containment cụ thể |

Tất cả mốc đều phục vụ giảng dạy, không phải event thực hoặc xác nhận phương pháp xử lý nào là chuẩn bắt buộc.

### 26.3. Tại sao signal cần được kết hợp?

- Một browser mới: có thể hợp lệ.
- Một vài MFA denials: có thể lỗi người dùng.
- Successful sign-in ngay sau burst: tăng nghi ngờ.
- Sensitive export request: tăng impact.
- User phủ nhận activity qua kênh tin cậy: tăng confidence.
- Target deny sau revoke: giúp xác minh containment tại endpoint được kiểm tra.

Không được bỏ qua khả năng thiếu logs hoặc session đã được tạo từ flow khác; cần đối chiếu authentication request IDs và sessions.

### 26.4. Một kịch bản khác: false positive do thiết bị mới

Nếu user đã đăng ký thiết bị mới qua MDM và support ticket được phê duyệt, browser mới và MFA retries có thể là migration hợp lệ. Analyst có thể đóng BENIGN_ENVIRONMENT_CHANGE sau xác minh, **không tự tạo permanent allowlist** cho mọi sign-in tương lai.

### 26.5. Liên hệ Mover và quyền hiện hành

Nếu user vừa chuyển team, detector phải kiểm tra finance.export có còn hợp lệ không. Successful login trên thiết bị quen thuộc cũng có thể dẫn tới **residual authorization** nếu role cũ chưa gỡ; đó là vấn đề khác với login anomaly thuần túy.

### 26.6. Liên hệ Leaver

Nếu chính user đã Leaver trước 09:00, successful login mới sẽ là tín hiệu nghiêm trọng hơn, nhưng cần kiểm tra identity ID, target app, login type và effectiveAt. Một API request dùng old token có thể không tạo sign-in event mới, nên không chỉ dựa IdP dashboard.

### 26.7. Kết thúc case thế nào?

- Có disposition và evidence rõ, không chỉ “alert closed”.
- Nếu confirmed compromise, có incident response, affected sessions/tokens và action history.
- Đã verify quyền cần chặn tại các target thuộc scope.
- Các telemetry gaps được ghi nhận; không giả định 100% coverage.
- Tuning dựa vào root cause, không làm rule quá lỏng để tránh alert.

## 27. Đo chất lượng detector và vận hành

Đội monitoring cần biết không chỉ bao nhiêu alerts được tạo mà detector có **bắt đúng, ưu tiên đúng và giảm rủi ro thật không**.

### 27.1. Các chỉ số quan trọng

| Chỉ số | Ý nghĩa | Giới hạn |
|---|---|---|
| Alerts per 1,000 sign-ins | Mức tải alert so với volume | Không chứng minh chất lượng |
| True positive rate / recall | Tỷ lệ tình huống có nhãn xấu được phát hiện | Nhãn ground truth thường không đầy đủ |
| Precision | Phần alerts thực sự có giá trị/đúng theo bộ nhãn | Phụ thuộc triage consistency |
| False positive rate | Tỷ lệ benign events bị gắn cờ | Cần mẫu benign có nhãn |
| False negative analysis | Những sự cố bị miss | Cần incident retrospectives |
| Mean time to detect (MTTD) | Thời gian từ event đến phát hiện | Đồng hồ/source coverage phải đúng |
| Mean time to triage | Thời gian analyst xác định disposition | Không tương đương resolution |
| Mean time to contain | Thời gian tới containment có evidence | Không đồng nghĩa root cause resolved |
| Alert fatigue | Backlog và lượng noisy cases | Không chỉ số raw alerts |
| Source coverage | Bao nhiêu apps/protocols có logs | Thiếu source tạo điểm mù |
| Pipeline lag | Event ingestion và enrichment latency | Event có thể tới muộn |
| Suppression aging | Rule exceptions quá hạn | Silent blind spots |
| Post-Leaver success count | Các successful auth trái cutoff | Cần identity mapping/effectiveAt |
| Critical principal anomaly rate | Risk tier cao có signal | Thiếu denominator có thể gây hiểu sai |
| Model/data drift | Baseline thay đổi theo thời gian | Không suy mọi drift là attack |

### 27.2. Precision và recall

Với các events/cases **đã có nhãn đáng tin**, công thức thường dùng:

~~~text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
FPR       = FP / (FP + TN)
~~~

TP, FP, FN, TN phải có định nghĩa và population. Nếu chưa có nhãn cho các tình huống bỏ sót, không được công bố recall chính xác chỉ từ alerts đã được triage.

### 27.3. Cẩn trọng với baseline labels

Một case BENIGN do user xác minh có thể là nhãn tốt hơn việc mặc định mọi alert không thành incident là false positive. Một incident được phát hiện qua nguồn khác có thể giúp tìm false negatives. Tài liệu audit cần giữ phương pháp gán nhãn.

### 27.4. Time-to-detect không giống time-to-ingest

Một event lúc 09:00, pipeline nhận lúc 09:04, alert lúc 09:06, analyst triage lúc 09:15:

~~~text
Ingestion lag: 4 phút
Detection latency từ event: 6 phút
Triage latency từ alert: 9 phút
~~~

Ví dụ nhấn mạnh sự khác biệt. Mục tiêu thời gian phải do policy/SLO quyết định theo risk tier; không tự bịa một ngưỡng chung.

### 27.5. Backtesting và policy tuning

Khi thay threshold hoặc thêm detector, có thể chạy lại trên tập lịch sử đã khử nhạy cảm để xem precision/recall, impact theo user groups và incidents. Không để dữ liệu tương lai rò vào baseline khi đánh giá theo thời gian.

### 27.6. Không tối ưu theo số cảnh báo giảm

Alerts giảm có thể vì detector được cải tiến **hoặc** vì IdP log source bị mất. Theo dõi ingestion coverage và synthetic safe test events trước khi tuyên bố chất lượng tốt hơn.

## 28. Ma trận kiểm thử Login anomaly

| Bài kiểm thử | Kết quả mong đợi |
|---|---|
| User login quen thuộc từ managed device | Low risk nếu không có tín hiệu khác |
| User mới Joiner trên thiết bị được cấp | Cold-start context, không auto high risk |
| Unfamiliar browser nhưng approved enrollment | Triage/context giải thích được |
| VPN đổi geo trong thời gian ngắn | Không tự kết luận impossible physical travel |
| Hai IP geo xa, khác confidence | Risk phụ thuộc quality/correlation |
| Shared corporate NAT có nhiều failures | Không mặc định một attacker |
| Một IP thử nhiều accounts | Password spray candidate alert |
| Distributed credential stuffing | Correlate vượt single-IP rule |
| Một lần sai password của user | Không tự incident |
| MFA denial burst không có success | Điều tra fatigue/DoS theo policy |
| MFA denial burst rồi success | Tăng risk, correlation đúng request |
| MDM compliant device nhưng user không nhận hoạt động | Không auto dismiss vì managed |
| Admin login ngoài JIT window | Alert/policy response theo privileged risk |
| Break-glass dùng trong incident hợp lệ | Alert + approval verification, không tự outage |
| Retired identity interactive sign-in success | Escalate, kiểm cutoff và target mapping |
| Leaver login failed do blocked | Không ghi là successful residual access |
| Old access token dùng sau Leaver | Token/access monitoring, không nhầm new login |
| Local SaaS session active sau IdP disable | Data-plane residual access alert |
| Mover dùng app mới đã được cấp | Baseline/context được cập nhật |
| Mover còn dùng Finance role cũ | Authorization residual finding |
| Service token từ approved new deployment | Xác minh migration trước khi block |
| Service token issuance sau retirement | High-priority NHI anomaly |
| CI workload đổi repo/branch không duyệt | Trust subject violation |
| Technical user dùng interactive login | Review vendor exception/principal type |
| Token refresh được ghi là sign-in | Không gây impossible-travel human alert sai |
| OIDC callback duplicated logs | Dedup request ID/issuer |
| SAML external subject giống email internal | Mapping namespace không gộp sai |
| Client gửi fake X-Forwarded-For | Chỉ dùng trusted proxy chain |
| Event đến muộn/out-of-order | Correlation theo eventTime/version, update case |
| Geo field UNKNOWN | Confidence thấp, không tự malicious |
| Thiếu device ID | UNKNOWN, không ép managed=false |
| Rule mới chạy report-only | Không block, vẫn log outcomes |
| Suppression hết hạn | Phát lại signal và alert nếu đủ điều kiện |
| Feedback CONFIRMED_COMPROMISE | Không dùng như benign baseline |
| Analyst đóng BENIGN_TRAVEL | Có evidence và expiry scope nếu suppress |
| Cross-tenant correlation | Không join hai identities sai |
| IdP log pipeline down | Có source health alert |
| Alert có raw token trong payload | Test fail, remediation bảo mật dữ liệu |
| API resource deny sau revoke | Evidence theo đúng scope |
| API khác vẫn cho quyền cũ | Không báo full verified closure |
| SOC triage dùng kênh không tin cậy | Chặn quy trình/phát hiện rủi ro xác minh |
| Detector score cao do feature trùng | Cần dependency/correlation adjustment |
| Dashboard không có ground truth | Không công bố precision/recall sai |
| Synthetic test account | Không tác động production trái phép |

### 28.1. Test rule và test pipeline

Một detector có thể logic đúng nhưng không nhận logs từ ứng dụng. Test cần hai lớp: **detection semantics** và **end-to-end producer→ingestion→alert→response→audit**.

### 28.2. Test false positives cùng negative cases

Dùng scenarios hợp lệ: approved travel, on-call, new device, password reset, SSO migration, multi-region workload. Đồng thời test cases rủi ro thật giả lập: post-Leaver login success, MFA denial burst + new session, privileged access không approval.

### 28.3. Test bằng principal an toàn

Chỉ dùng test identity, fake IP ranges, môi trường được phép và lịch test có owner. Không cố tạo hàng nghìn password attempts vào production để “kiểm tra password spray” khi chưa được phê duyệt.

## 29. Hiểu lầm thường gặp

**“Login ở quốc gia lạ là chắc chắn attacker.”** Geo theo IP có thể phản ánh VPN/proxy.

**“Impossible travel luôn là bằng chứng vật lý.”** IP egress và geolocation không đo vị trí chính xác của người.

**“Một login failure là brute-force attack.”** Cần pattern và context.

**“Chỉ login thất bại mới nguy hiểm.”** Stolen credential có thể login success.

**“MFA bật là không thể account takeover.”** MFA fatigue, recovery abuse, token/session misuse vẫn cần quản lý.

**“Trusted device nghĩa là phiên nào cũng an toàn.”** Device có thể bị compromise; policy còn phụ thuộc actor/action.

**“Client ID là secret, cứ thấy client ID khác là tấn công.”** Client ID thường là định danh, cần hiểu flow và trust.

**“SSO success chứng minh SaaS role đúng.”** Authentication không thay authorization.

**“Chặn IdP là mọi RP session hết ngay.”** Không mặc định, cần session/token controls riêng.

**“Không có login sau Leaver nghĩa là không còn access.”** Old token hoặc local session có thể còn.

**“Service account đi từ hai vùng cloud là impossible travel.”** Máy không có lịch di chuyển vật lý như người.

**“Role admin thì mọi alert đều phải auto block.”** Cần policy, confidence và emergency access path.

**“Alert score 90 chứng minh compromise.”** Score là output model, không phải bằng chứng định danh attacker.

**“Tăng threshold để giảm alerts là tối ưu.”** Có thể bỏ sót incidents.

**“Một IP là một người.”** NAT, proxy và dịch vụ shared egress làm kết luận sai.

**“Không thấy anomaly có nghĩa an toàn.”** Có thể thiếu logs hoặc detector coverage.

**“Bất thường là lỗi của người dùng.”** Detection nhằm bảo vệ access, không đánh giá cá nhân.

**“Cứ yêu cầu user đọc OTP để xác minh.”** Là hành vi suy yếu MFA và không nên sử dụng.

**“Một HTTP 403 sau revoke là tất cả quyền đã hết.”** Chỉ chứng minh outcome ở một endpoint/scope.

**“Đã đóng alert thì không cần giữ evidence.”** Audit/incident review cần history và retention theo policy.

## 30. Bài tập tự đánh giá

### A. Impossible travel do corporate VPN

Hai sign-ins từ IP geolocation cách nhau hàng nghìn km trong 15 phút, nhưng người dùng đang ở cùng managed laptop và VPN egress vừa chuyển.

**Phân tích:** Đây có thể là false positive. Kiểm tra trusted device continuity, VPN/network classification, confidence IP geo và các hành vi khác trước khi khẳng định compromise.

### B. MFA fatigue rồi login thành công

Một user nhận nhiều push notifications, phần lớn bị từ chối, sau đó có approval từ client mới.

**Phân tích:** Correlation theo auth request, MFA details và resource activity; triage bằng kênh tin cậy. Có thể cần containment nếu evidence mạnh, không gắn nhãn tấn công chỉ từ count.

### C. Leaver vẫn truy cập SaaS

HRIS Leaver effectiveAt 17:00, IdP chặn sign-in mới, nhưng Finance SaaS session vẫn cho export lúc 17:20.

**Phân tích:** Đây là residual application session/authorization path. Điều tra target, revoke session theo policy và xem deprovisioning control deficiency; login anomaly ở IdP đơn lẻ không phát hiện đầy đủ.

### D. Mover bắt đầu sử dụng ứng dụng mới

Nhân viên chuyển bộ phận, lần đầu login vào Ops dashboard với device quen thuộc và entitlement được duyệt.

**Phân tích:** New app là anomaly có thể hợp lệ; dùng trusted Mover event. Đồng thời kiểm tra Finance role cũ đã được gỡ.

### E. CI token từ vùng cloud mới

Một managed build runner chuyển region theo kế hoạch migration, token issuance logs thấy IP lạ.

**Phân tích:** Dùng workload principal baseline, issuer/subject/audience, CI repository/branch/environment và approval deployment; không áp human impossible-travel.

### F. Production-admin đăng nhập từ browser mới

Có một alert high risk, nhưng đang diễn ra incident production và privileged activation được PAM phê duyệt.

**Phân tích:** Kiểm tra JIT/incident reference, strong authentication và session scope. Cần audit kỹ, tránh auto block phá quy trình khẩn cấp nếu policy không cho phép.

### G. Dashboard đột nhiên có 0 alerts

Cùng ngày đó pipeline OIDC sign-in logs bị mất kết nối.

**Phân tích:** Không kết luận security posture đã tốt hơn. Giám sát source heartbeat, ingestion lag, dropped events và recovery/backfill.

### H. Token refresh làm giả cảm giác login mới

OAuth client dùng refresh token qua backend ở region khác; analytics coi là interactive login và cảnh báo geolocation.

**Phân tích:** Tách grantType/token flow khỏi interactive sign-in; bổ sung RP/AS correlation trước khi tạo impossible-travel detection.

### I. Alert false positive được suppress vô hạn

Một admin đi công tác một lần, analyst allowlist vĩnh viễn mọi login của account đó.

**Phân tích:** Quá rộng. Chỉ suppress signal cụ thể trong thời gian có approval, theo dõi expiry và vẫn phát hiện những tín hiệu khác.

## 31. Checklist triển khai Login anomaly monitoring

1. **Identity scope:** nhân viên, contractor, guest và workload có phân loại?
2. **Sources:** IdP, local login, RP, PAM, token, application audit đầy đủ?
3. **Producer trust:** event sources được xác thực, không tin client spoofing?
4. **Schema:** eventType, outcome, eventTime, principal và tenant rõ?
5. **Mapping:** immutable ID + issuer/source, không gộp theo email?
6. **Time:** event vs ingest vs lifecycle effectiveAt được phân biệt?
7. **Data quality:** missing logs, unknown geo/device có trạng thái riêng?
8. **Proxy:** client IP lấy từ trusted chain?
9. **Geo:** có IP geolocation confidence và VPN/SASE enrichment?
10. **Impossible travel:** lọc interactive human sign-ins và duplicates?
11. **Password spray:** có multi-account correlation ngoài per-user lockouts?
12. **Credential stuffing:** có xem distributed patterns, không chỉ một IP?
13. **MFA:** denial/approval/enrollment/recovery events được correlate?
14. **Device:** registered/compliant khác fingerprint phỏng đoán?
15. **Protocols:** legacy login, OIDC/SAML và token refresh phân biệt?
16. **Baseline:** per-user/peer/app/tenant và cold start có kế hoạch?
17. **Seasonality:** ca trực, migration, approved travel được xem xét?
18. **Baseline poisoning:** compromised history không bị học thành normal?
19. **Signals:** ít nhất đánh giá confidence và feature dependencies?
20. **Impact:** app/resource sensitivity và effective privileges được tính?
21. **Role:** RBAC/ABAC, SoD, PAM/JIT và access approvals hiện hành?
22. **Joiner:** login đầu tiên không auto high; pre-start access được kiểm?
23. **Mover:** quyền cũ/role cache/session residual được giám sát?
24. **Leaver:** login success sau cutoff phân biệt denial và token reuse?
25. **Guest:** sponsor/contract expiry và local sessions có coverage?
26. **NHI:** client credentials, STS, trust, key rotation và runtime baseline?
27. **Service Leaver:** issuance/use sau retirement có alert?
28. **Sessions:** IdP/RP/OAuth tokens/data-plane access được theo dõi?
29. **Privileged:** break-glass và admin access có rules riêng?
30. **Scoring:** calibrated thresholds, deterministic policy checks và confidence?
31. **Response:** low/medium/high có policy, owner, recovery path?
32. **Triage:** có case disposition, evidenceRefs và user verification an toàn?
33. **No secrets:** logs không có passwords, OTP, raw cookies hoặc tokens?
34. **Privacy:** retention, access control, purpose limitation theo policy?
35. **SIEM health:** heartbeat, latency, missing data và schema failures?
36. **Correlation:** request/session refs không lộ bearer secret?
37. **Feedback:** analyst labels có audit, suppression có expiry?
38. **False positive:** đo theo use case và peer group?
39. **False negative:** review incidents bị detector bỏ sót?
40. **Tests:** benign travel và suspicious patterns cùng được kiểm?
41. **Drift:** monitor thay đổi baseline, rule/version và model performance?
42. **JML coverage:** source-to-target reconciliation phù hợp risk tier?
43. **Containment:** revoke và target readback có bằng chứng?
44. **Incident:** có escalation ngay khi verified compromise?
45. **Reporting:** metrics có cohort, time basis, denominator và confidence?
46. **Governance:** owner và review cadence cho mọi rule, exception, policy?

## 32. Tổng kết

**Login anomaly** là một sự kiện hoặc chuỗi đăng nhập **khác baseline/kỳ vọng**, được phát hiện qua IP/geo, thiết bị, thời gian, giao thức, MFA, auth failures và ngữ cảnh nghiệp vụ. Một anomaly có thể là đăng nhập hợp lệ, lỗi cấu hình, telemetry thiếu hoặc dấu hiệu compromise; **không nên đánh đồng bất thường với tấn công đã xác nhận**.

Một chương trình Identity monitoring tốt phải:

- **Thu thập chuẩn hóa:** IdP, SSO/RP, local auth, PAM, OAuth token và resource logs.
- **Liên kết đúng danh tính:** immutable principal, issuer, tenant, session/auth context.
- **Hiểu JML:** Joiner first login, Mover role changes, Leaver cutoff và residual access.
- **Phân biệt con người với workload:** behavioral geo/MFA không áp máy móc cho service principals.
- **Đánh giá nhiều tín hiệu:** baseline, device/network trust, MFA, sensitivity, confidence.
- **Triage minh bạch:** giải thích risk, xác minh bằng kênh tin cậy, lưu disposition/evidence.
- **Phản ứng tương xứng:** step-up, deny, session/token revoke, risk-based incident response.
- **Đo chất lượng:** coverage, precision/recall có nhãn, false positives, detection latency và pipeline health.
- **Kiểm chứng hiệu lực:** không coi IdP disable là bằng chứng mọi token, app session và local grants đã hết.

Trong IAM theo **Joiner–Mover–Leaver**, mục đích cuối của login-anomaly monitoring không chỉ là phát hiện sự kiện lạ mà là **bảo vệ đúng danh tính, quyền, tài nguyên và thời điểm**, ngăn người không còn có căn cứ truy cập tiếp tục sử dụng **quyền truy cập tồn dư**.

**Ghi nhớ:** **Một login lạ là lý do để đặt câu hỏi; một quyết định bảo mật đáng tin cần tín hiệu có nguồn gốc rõ ràng, ngữ cảnh quyền hiện hành, khả năng xác minh và phản ứng có kiểm toán.**




