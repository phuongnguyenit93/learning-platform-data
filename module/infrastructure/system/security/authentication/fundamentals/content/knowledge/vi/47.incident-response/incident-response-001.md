# Authentication incident — Quy trình ứng phó sự cố xác thực danh tính

> **Chương:** Incident response  
> **Chủ đề:** Authentication incident  
> **Phạm vi:** Security Authentication Fundamentals — chuẩn bị, phát hiện, phân loại, điều tra, containment, eradication, recovery và rút kinh nghiệm khi xảy ra sự cố liên quan đến danh tính, credential, MFA, passkey, token, session, federation và service identity.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện và phân loại sự cố authentication, identity và account compromise.
2. Kích hoạt incident response dựa trên evidence, impact, confidence và phạm vi ảnh hưởng.
3. Phân công incident commander, technical lead, security analyst, communications lead và evidence owner.
4. Thu thập, bảo toàn và tương quan bằng chứng mà không làm lộ thêm credential hoặc dữ liệu cá nhân.
5. Điều tra password spraying, credential stuffing, account takeover, MFA fatigue, token/session abuse và service credential compromise.
6. Chọn containment có phạm vi phù hợp: revoke session/token, disable credential, block source, step-up hoặc giới hạn chức năng.
7. Xử lý compromise của signing key, identity provider, federation trust và recovery channel.
8. Phục hồi dịch vụ theo thứ tự an toàn, xác minh lại trust và theo dõi dấu hiệu tái xâm nhập.
9. Phân biệt incident bảo mật với outage hoặc lỗi cấu hình của identity dependency.
10. Viết timeline, incident report, lessons learned và action item có owner.

## 1. Authentication incident là gì?

**Authentication incident** là sự kiện hoặc chuỗi sự kiện cho thấy quá trình xác thực danh tính, credential, token, session hoặc trust relationship có thể đã bị xâm phạm, bị lạm dụng hoặc không còn hoạt động theo policy. Sự cố có thể ảnh hưởng một account, một service principal, nhiều tenant hoặc toàn bộ identity platform.

Ví dụ:

- Attacker sử dụng password bị lộ để đăng nhập vào account;
- Password spraying hoặc credential stuffing dẫn tới một hay nhiều login thành công;
- Người dùng bị spam MFA push và vô tình approve;
- Refresh token bị đánh cắp và tái sử dụng sau rotation;
- Session cookie bị đánh cắp hoặc tiếp tục hoạt động sau revoke;
- Private signing key bị lộ, cho phép tạo token giả;
- OAuth client secret hoặc service API key bị công khai;
- Federation trust bị thay đổi hoặc assertion được chấp nhận sai;
- Recovery flow bị lạm dụng để chiếm account;
- Identity provider hoặc MFA provider outage khiến hệ thống không thể xác minh credential;
- Cấu hình sai khiến token không được kiểm tra audience, issuer hoặc chữ ký đúng cách.

Không phải mọi login failure đều là incident. Một lần nhập sai password thường là hoạt động bình thường; một đợt failure có pattern, có login success bất thường hoặc thay đổi factor ngay sau đó có thể là dấu hiệu account takeover.

### Sự cố bảo mật và sự cố availability

| Loại | Mục tiêu ứng phó | Ví dụ |
| --- | --- | --- |
| Security incident | Ngăn truy cập trái phép, bảo toàn evidence, xác định impact | Credential theft, token replay, signing-key compromise |
| Service incident | Khôi phục chức năng xác thực đúng policy | IdP outage, database unavailable, MFA provider timeout |
| Mixed incident | Đồng thời xử lý compromise và availability | Attacker làm quá tải token endpoint, hoặc outage che giấu credential abuse |

Một outage có thể tạo ra nhiều login failure mà không phải tấn công. Ngược lại, attacker có thể lợi dụng outage để thực hiện hành động trong degraded mode. Phải điều tra cả hai chiều.

## 2. Nguyên tắc ứng phó

Incident response authentication cần bảo vệ cả tính bảo mật và khả năng khôi phục của hệ thống.

### Nguyên tắc cốt lõi

- **Xác minh trước khi kết luận:** phân biệt tín hiệu, giả thuyết và evidence đã xác nhận.
- **Giới hạn phạm vi:** containment đúng account, credential, client, tenant hoặc service bị ảnh hưởng.
- **Bảo toàn bằng chứng:** ghi timeline, request ID, token reference và log đã redaction trước khi thay đổi trạng thái nếu tình huống cho phép.
- **Thu hồi trust khi cần:** credential bị compromise phải bị revoke; không giữ lại chỉ để tránh gián đoạn.
- **Không hạ tiêu chuẩn xác thực:** outage không phải lý do bỏ qua signature, issuer, audience, MFA hoặc authorization.
- **Ưu tiên hành động có thể đảo ngược:** dùng step-up, revoke session có phạm vi nhỏ hoặc tạm giới hạn action trước khi khóa rộng, nếu rủi ro cho phép.
- **Một nguồn điều phối:** incident commander thống nhất ưu tiên và quyết định ảnh hưởng nhiều nhóm.
- **Giao tiếp rõ:** thông báo sự kiện, tác động, hướng dẫn và cập nhật theo kênh được phê duyệt.
- **Kiểm tra sau containment:** xác minh attacker không còn session, token, credential phụ hoặc persistence.

### Không phá hủy evidence

Không xóa account, log, device record hoặc credential metadata một cách vội vàng nếu có thể bảo toàn evidence trước. Khi nguy cơ đang diễn ra, containment có thể cần ưu tiên hơn; ghi lại hành động, thời điểm và lý do để phục vụ điều tra sau đó.

### Không thu thập bí mật để điều tra

Incident responder không cần yêu cầu người dùng gửi password, OTP, recovery code hoặc token. Dùng event ID, session reference, credential reference, device context và log đã được bảo vệ.

## 3. Phạm vi và taxonomy sự cố

Phân loại theo loại credential, giai đoạn authentication và tài sản bị ảnh hưởng giúp chọn playbook chính xác.

| Nhóm sự cố | Dấu hiệu thường gặp | Tài sản có thể bị ảnh hưởng |
| --- | --- | --- |
| Password compromise | Login lạ, credential stuffing, password spraying | User account, session, dữ liệu người dùng |
| MFA compromise | Push fatigue, OTP phishing, factor replacement | Account, recovery path, assurance |
| Passkey/authenticator issue | Credential enrollment bất thường, authenticator bị mất | Public-key credential, account |
| Token compromise | Access/refresh token theft, replay, wrong audience | API, resource server, delegated access |
| Session compromise | Cookie theft, session fixation, session reuse | Web/mobile session, account actions |
| Signing-key compromise | Ký token/assertion trái phép | Nhiều client/API/tenant |
| Client/service credential | API key, client secret, private key bị lộ | Workload, database, SaaS integration |
| Federation compromise | IdP/SP trust, redirect URI, SAML/OIDC validation | Federated accounts, enterprise apps |
| Account recovery abuse | Recovery link/code bị lạm dụng | Account ownership, credential enrollment |
| Identity platform outage | Login/token/introspection/session lỗi diện rộng | Availability, business operations |
| Privileged identity abuse | Admin account hoặc break-glass bị dùng bất thường | IAM policy, tenant, signing configuration |

### Phân loại theo impact

- **Identity:** một người dùng, một nhóm, service account hay privileged principal?
- **Scope:** một application, một tenant, nhiều tenant hay toàn bộ issuer?
- **Privilege:** quyền đọc thông thường, dữ liệu nhạy cảm, admin hay signing authority?
- **Outcome:** chỉ có attempt, đã xác thực, đã tạo session, đã thực hiện sensitive action hay đã thay đổi trust?
- **Duration:** đang diễn ra, đã chấm dứt hay chưa rõ?
- **Confidence:** nghi ngờ, có bằng chứng mạnh hay đã xác nhận?

## 4. Severity và tiêu chí kích hoạt incident

Severity giúp xác định tốc độ phản ứng, nguồn lực và mức escalation. Severity cần xét impact và confidence; không nên chỉ dựa trên số lượng event.

| Mức | Tiêu chí tham khảo | Ví dụ |
| --- | --- | --- |
| Critical | Compromise trust root hoặc nhiều principal đặc quyền; phạm vi rộng; attacker có thể phát hành credential/token trái phép | Signing key compromise, IdP admin takeover |
| High | Account/service có quyền đáng kể bị chiếm hoặc token/session abuse có evidence | Refresh token reuse kèm sensitive action |
| Medium | Hành vi đáng ngờ có phạm vi giới hạn, chưa thấy impact nghiêm trọng | MFA fatigue trên một số account |
| Low | Tín hiệu đơn lẻ hoặc bất thường chưa xác nhận | Một login từ source mới, vài lần password failure |
| Informational | Sự kiện thay đổi có phê duyệt hoặc trạng thái cần theo dõi | Rotation theo lịch, credential sắp hết hạn |

### Kích hoạt incident khi

- Có login thành công sau chuỗi credential attack và context bất thường;
- Refresh token reuse hoặc session reuse được xác nhận;
- MFA factor, email recovery hoặc passkey bị thay đổi trái phép;
- Signing key, client secret hoặc service credential bị lộ;
- Có bằng chứng token/assertion giả được chấp nhận;
- Privileged identity thực hiện hành động không được phê duyệt;
- Nhiều tenant hoặc service cùng bị ảnh hưởng;
- Identity provider có dấu hiệu compromise, không chỉ outage;
- Recovery flow tạo quyền truy cập cho người không đúng chủ thể.

### Phân biệt confidence với severity

Một tín hiệu có confidence thấp nhưng impact tiềm tàng lớn vẫn cần triage nhanh; không nhất thiết phải công bố Critical ngay. Ngược lại, một sự kiện có confidence cao nhưng impact thấp có thể được xử lý theo playbook phạm vi nhỏ.

## 5. Vai trò và điều phối incident

Khi sự cố lớn, nhiều nhóm có thể cùng xử lý. Vai trò rõ ràng giúp tránh hành động mâu thuẫn hoặc bỏ sót quyết định.

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander (IC) | Điều phối, đặt ưu tiên, phê duyệt quyết định containment lớn và theo dõi tiến độ |
| Security incident lead | Dẫn dắt phân tích threat, phạm vi compromise và containment |
| Identity/IAM technical lead | Hiểu issuer, credential, token, session, federation và policy |
| Platform/SRE lead | Điều tra availability, dependency, capacity và phục hồi |
| Application owner | Xác định business impact và xác minh chức năng sau phục hồi |
| Evidence custodian | Thu thập, bảo toàn, kiểm soát truy cập và chain of custody |
| Communications lead | Chuẩn bị thông báo nội bộ/khách hàng theo phê duyệt |
| Legal/privacy/compliance | Đánh giá nghĩa vụ thông báo và xử lý dữ liệu |
| Scribe | Ghi timeline, quyết định, owner, evidence và action item |

Một người có thể đảm nhiệm nhiều vai trò trong sự cố nhỏ. Với incident Critical/High, cần có IC và người ghi nhận quyết định rõ ràng.

### Quy tắc điều phối

- Mọi hành động ảnh hưởng nhiều tenant/service phải được ghi và điều phối qua IC;
- Owner của hệ thống xác nhận tác động kỹ thuật trước khi thay đổi cấu hình lớn;
- Security lead xác nhận threat scope và containment;
- Communications không tự suy đoán nguyên nhân hoặc phạm vi;
- Escalate khi chưa có owner, evidence bị mất hoặc containment thất bại.

## 6. Chuẩn bị trước sự cố

Ứng phó hiệu quả bắt đầu từ trước khi incident xảy ra.

### Những thứ cần chuẩn bị

- Inventory issuer, client, resource server, credential và owner;
- Sơ đồ trust boundary và dependency;
- Runbook cho từng loại credential/token/session;
- Cơ chế revoke session, refresh token, API key, certificate và signing key;
- Break-glass account được bảo vệ và kiểm tra định kỳ;
- Kênh liên lạc ngoài identity provider chính;
- Quy trình truy cập log/evidence có audit;
- Synthetic account/test tenant có quyền giới hạn;
- Quy trình failover và degraded mode;
- Danh sách bên thứ ba và escalation contact;
- Mẫu incident timeline và report;
- Diễn tập tabletop và technical exercise.

### Readiness của containment

Trước sự cố phải biết:

- Có thể revoke token theo subject, session hoặc token family không?
- Có thể disable client hoặc issuer mà không làm sập mọi ứng dụng không?
- Có thể rotate signing key và cập nhật verifier/JWKS trong thời gian nào?
- Có thể buộc reauthentication hoặc step-up cho nhóm bị ảnh hưởng không?
- Có thể tạm dừng recovery hoặc enrollment không?
- Có thể phân biệt outage của MFA provider với MFA abuse không?

Không chờ đến lúc compromise mới tìm hiểu cách thu hồi credential.

## 7. Vòng đời incident response

Một quy trình tổng quát có thể chia thành các giai đoạn: prepare, detect, analyze, contain, eradicate, recover và learn. Trong thực tế, các giai đoạn có thể lặp lại khi xuất hiện evidence mới.

`````````mermaid
flowchart TD
    A["Prepare: inventory, runbook, access"] --> B["Detect: alert, report, anomaly"]
    B --> C["Analyze: validate evidence and scope"]
    C --> D{"Incident confirmed?"}
    D -- "No" --> E["Close as benign/configuration issue; retain notes"]
    D -- "Yes" --> F["Contain: limit attacker access"]
    F --> G["Eradicate: remove persistence and root cause"]
    G --> H["Recover: restore trusted authentication"]
    H --> I["Monitor: detect recurrence"]
    I --> J["Learn: post-incident review and actions"]
    J --> A
`````````

### Detect

Nhận alert, báo cáo user, threat intelligence hoặc tín hiệu từ bên thứ ba. Ghi thời điểm nhận, nguồn và incident ID.

### Analyze

Xác minh event, phân loại outcome, dựng timeline, xác định principal/resource, kiểm tra success sau failure và đánh giá mức độ compromise.

### Contain

Ngăn attacker tiếp tục dùng credential/session/token hoặc thay đổi trust. Chọn containment có phạm vi nhỏ nhất đáp ứng rủi ro.

### Eradicate

Loại bỏ credential bị lộ, persistence, malicious client, redirect URI, factor lạ, key trái phép hoặc cấu hình yếu.

### Recover

Khôi phục dịch vụ và cấp lại credential theo quy trình tin cậy; xác minh token, session, policy và monitoring.

### Learn

Rút kinh nghiệm về root cause, detection gap, response latency, communication và thay đổi kiểm soát.

## 8. Triage ban đầu và thu thập evidence

Triage cần trả lời: điều gì xảy ra, chủ thể nào, tài sản nào, từ khi nào, còn diễn ra không và evidence nào xác nhận?

### Thông tin cần ghi

- Incident ID, alert ID và detection rule/version;
- Event time và ingest time;
- Subject/client/tenant reference;
- Authentication method và credential type;
- Source/device/network reference đã xử lý;
- Login success/failure, MFA outcome, token issuance/use;
- Session/token/credential reference;
- Request/correlation ID;
- Resource/action được truy cập;
- Deployment, key rotation, policy change hoặc outage gần thời điểm đó;
- Người thu thập, nguồn log và thời điểm export.

### Nguồn evidence

- Identity provider authentication/audit log;
- API gateway và resource server log;
- Token issuance/introspection event;
- Session store audit;
- MFA/passkey provider event;
- Credential enrollment/revocation history;
- KMS/HSM signing audit;
- Secret manager access log;
- Device/session risk signal;
- WAF/network/DNS telemetry;
- Change management và deployment record.

### Không thu thập

- Password hoặc password hash để gửi qua chat;
- OTP, TOTP seed, recovery code;
- Raw access/refresh/ID token;
- Session cookie hoặc Authorization header;
- Private key/client secret;
- Toàn bộ PII không liên quan.

Ưu tiên reference và evidence đã redaction. Nếu cần bảo toàn artifact nhạy cảm cho điều tra, lưu trong kho evidence có kiểm soát truy cập, mã hóa, audit và retention phù hợp.

## 9. Timeline và chain of custody

Timeline giúp liên kết các sự kiện từ nhiều hệ thống; chain of custody giúp chứng minh evidence không bị thay đổi hoặc truy cập trái phép.

### Timeline

Ghi:

- Thời điểm phát hiện và kích hoạt incident;
- Lần credential failure đầu tiên;
- Login/token/session success đầu tiên đáng ngờ;
- MFA/recovery/factor change;
- Sensitive action hoặc dữ liệu bị truy cập;
- Thời điểm containment;
- Revoke/disable/rotation;
- Thời điểm attacker activity dừng;
- Recovery và xác minh.

Chuẩn hóa thời gian UTC và lưu cả event time lẫn ingest time. Ghi nhận clock skew nếu nguồn log không đồng bộ.

### Chain of custody

Với evidence quan trọng:

1. Ghi nguồn và cách thu thập;
2. Ghi người thu thập, thời điểm và incident ID;
3. Giữ bản gốc ở nơi chỉ đọc nếu có thể;
4. Tính hash integrity cho file export;
5. Ghi mọi lần truy cập/chuyển giao;
6. Giới hạn quyền xem và export;
7. Ghi redaction hoặc transformation đã thực hiện;
8. Áp dụng retention/legal hold theo policy.

Không chỉnh sửa trực tiếp bản evidence gốc để làm sạch PII. Tạo bản làm việc đã redaction và giữ liên kết tới artifact gốc trong kho được kiểm soát.

## 10. Đánh giá blast radius

Blast radius là phạm vi account, credential, application, tenant, resource và dữ liệu có thể bị ảnh hưởng.

### Câu hỏi

- Credential bị compromise thuộc user, service, admin hay issuer?
- Credential có được dùng chung giữa nhiều app/environment không?
- Token có audience/scope nào?
- Session hoặc token family nào được tạo từ login đó?
- Có refresh token hoặc credential phụ nào được phát hành?
- Account có thể thay email, MFA, recovery hoặc liên kết danh tính không?
- Có sensitive action sau authentication không?
- Có client/tenant khác dùng chung signing key hoặc trust configuration?
- Có backup/replica/log chứa credential bị lộ?

### Phân loại phạm vi

| Mức | Phạm vi | Hướng xử lý |
| --- | --- | --- |
| Single principal | Một user/service identity | Revoke credential/session liên quan, kiểm tra action |
| Client/application | Một OAuth client hoặc ứng dụng | Disable/rotate client credential, kiểm tra audience |
| Tenant | Nhiều principal trong một tenant | Containment tenant, rà soát policy và admin |
| Issuer/platform | Nhiều client/resource server | Incident cấp nền tảng, đánh giá key/trust |
| Cross-organization | Federation/vendor/partner | Phối hợp bên liên quan và đánh giá trust boundary |

Không kết luận blast radius chỉ từ số alert. Một signing key có thể ảnh hưởng rất rộng dù chỉ có một event; một đợt brute force có thể tạo hàng nghìn failure nhưng chưa có account nào bị chiếm.

## 11. Containment: giới hạn quyền truy cập của attacker

Containment nhằm ngăn attacker tiếp tục sử dụng credential, token, session hoặc trust relationship. Chọn biện pháp dựa trên evidence và blast radius.

### Các biện pháp containment

- Revoke session hoặc session family;
- Revoke refresh token và authorization grant;
- Disable hoặc rotate password/API key/client secret;
- Revoke certificate hoặc workload credential;
- Force reauthentication hoặc step-up cho nhóm principal bị ảnh hưởng;
- Tạm dừng password reset, MFA enrollment hoặc account linking nếu flow bị lạm dụng;
- Disable OAuth client hoặc federation connection bị compromise;
- Block source/campaign ở gateway/WAF khi evidence đủ;
- Giới hạn scope, audience hoặc sensitive operation;
- Tạm dừng token issuance nếu signing trust không còn an toàn.

### Chọn phạm vi nhỏ nhất có hiệu quả

Nếu một account bị compromise, revoke session và credential của account đó có thể đủ. Nếu signing key bị compromise, chỉ khóa một user là không đủ; cần xử lý toàn bộ token có thể được ký bởi key đó và mọi verifier tin issuer.

### Containment có thể gây tác động

Revoke session hàng loạt, disable IdP hoặc rotate signing key có thể làm nhiều người dùng mất quyền truy cập. Trước khi thực hiện, IC cần biết:

- Phạm vi người dùng/service bị ảnh hưởng;
- Có thể rollback an toàn không;
- Credential cũ có còn an toàn không;
- Các verifier có nhận được revoke/key update không;
- Có break-glass path được phê duyệt không;
- Có cần thông báo khách hàng hoặc owner ứng dụng không.

Nếu credential đã bị compromise, không rollback về credential đó chỉ để giảm downtime.

## 12. Eradication: loại bỏ nguyên nhân và persistence

Sau containment, cần loại bỏ nguyên nhân để attacker không thể quay lại bằng credential hoặc đường truy cập khác.

### Kiểm tra persistence

- Account phụ hoặc admin account mới;
- Passkey/security key lạ;
- MFA phone, authenticator hoặc recovery email mới;
- OAuth client, refresh token hoặc grant mới;
- Session chưa revoke;
- API key, SSH key, certificate hoặc workload identity mới;
- Redirect URI, federation trust hoặc IdP configuration bị thay;
- Role/group/permission được thêm;
- Email forwarding rule hoặc mailbox compromise liên quan recovery;
- Automation secret hoặc CI/CD variable bị thay;
- Logging/alert suppression bị tắt.

### Loại bỏ

- Xóa/revoke credential trái phép;
- Thu hồi session, token family và grant;
- Khôi phục policy, redirect URI, trust configuration;
- Xoay secret bị lộ và cập nhật consumer;
- Re-enroll factor bằng quy trình xác minh mạnh;
- Patch root cause như XSS, phishing flow, secret exposure hoặc access policy yếu;
- Kiểm tra mọi replica/cache đã nhận trạng thái mới;
- Xác minh không còn token/credential cũ được chấp nhận.

Không chỉ xóa artifact nhìn thấy đầu tiên. Tìm nguyên nhân ban đầu và mọi credential có thể bị lộ cùng thời điểm.

## 13. Recovery: khôi phục dịch vụ và danh tính đáng tin

Recovery không đơn thuần là bật lại endpoint. Hệ thống phải trở lại trạng thái có thể xác minh danh tính và quyền với trust material đã được kiểm tra.

### Recovery checklist

1. Root cause đã được xử lý hoặc đã có biện pháp giảm thiểu được phê duyệt;
2. Credential/secret/key bị compromise đã được revoke/rotate;
3. Issuer, audience, signing algorithm và JWKS được xác minh;
4. Session/token/recovery state được đồng bộ;
5. Resource server và client đã nhận cấu hình mới;
6. MFA/passkey/recovery factor của principal bị ảnh hưởng đã được xác minh;
7. Synthetic login/token/validation transaction thành công;
8. Security control và alert pipeline hoạt động;
9. Traffic được mở lại theo từng giai đoạn;
10. Theo dõi recurrence và rollback trigger.

### Phục hồi theo giai đoạn

- Canary một client/tenant hoặc một nhóm user;
- Xác minh login và token issuance;
- Xác minh token validation tại resource server;
- Xác minh revoke và session behavior;
- Mở rộng theo batch;
- Theo dõi failure rate, latency và security alert;
- Chỉ kết thúc incident khi có bằng chứng ổn định.

### Khôi phục account người dùng

Khi account bị takeover:

- Xác minh người yêu cầu bằng recovery policy độc lập;
- Revoke session/token và factor attacker đã thêm;
- Đặt lại credential qua kênh tin cậy;
- Re-enroll MFA/passkey nếu cần;
- Kiểm tra email/phone/recovery channel;
- Thông báo hoạt động quan trọng và cung cấp hướng dẫn bảo vệ account;
- Rà soát action/data access trong khoảng thời gian compromise.

Không gửi password tạm, OTP hoặc recovery code qua kênh không an toàn. Không dùng chính email/phone đang bị nghi compromise làm bằng chứng duy nhất.

## 14. Playbook: password spraying và credential stuffing

### Dấu hiệu

- Failure tăng trên nhiều subject;
- Một source/campaign thử nhiều account;
- Failure mỗi account thấp nhưng unique subject cao;
- Traffic phân tán nhiều IP với pattern giống nhau;
- Một số login success xuất hiện sau chuỗi failure;
- Account vừa đăng nhập thành công có device/session mới.

### Điều tra

1. Kiểm tra reason code để tách invalid credential khỏi dependency error;
2. Xác định unique subject, source, client, ASN và user-agent pattern;
3. Tìm login success sau failure;
4. Kiểm tra MFA completion và session creation;
5. Xác định sensitive action sau login;
6. So sánh với baseline, maintenance và provider health.

### Containment

- Rate limit theo account, source, client và campaign;
- Chặn nguồn có confidence cao theo thời gian giới hạn;
- Buộc step-up với account có risk;
- Revoke session của account đã xác nhận bị takeover;
- Reset credential hoặc force password change theo policy;
- Không khóa hàng loạt account chỉ vì cùng IP/NAT;
- Bảo vệ recovery endpoint để attacker không chuyển sang abuse reset flow.

### Recovery và follow-up

- Theo dõi success sau containment;
- Kiểm tra password reuse và breach exposure;
- Rà soát rate-limit thresholds và bot controls;
- Cải thiện telemetry cho distributed source/campaign;
- Thông báo người dùng bị ảnh hưởng theo policy.

## 15. Playbook: account takeover và MFA fatigue

### Dấu hiệu

- Login success từ source/device bất thường;
- Nhiều MFA challenge bị deny/timeout rồi một challenge được approve;
- Factor, email hoặc phone vừa bị thay;
- Recovery flow hoàn tất ngay trước login;
- Session mới thực hiện thao tác nhạy cảm;
- User báo không tự thực hiện login hoặc approve.

### Điều tra

- Xác định login transaction, method và assurance;
- Kiểm tra challenge ID và thời điểm approve;
- Xác định thiết bị/source gửi challenge;
- Kiểm tra factor enrollment/recovery changes;
- Liệt kê session, refresh token và token family;
- Rà soát action, data access và account linking sau login;
- Kiểm tra mailbox/device compromise có thể hỗ trợ attacker.

### Containment

- Revoke tất cả session/token liên quan;
- Tạm dừng factor/recovery change mới nếu đang bị abuse;
- Buộc reauthentication qua factor tin cậy;
- Xóa factor lạ sau khi xác minh chủ tài khoản;
- Giới hạn sensitive action và yêu cầu step-up;
- Cảnh báo người dùng qua kênh độc lập;
- Escalate nếu account có quyền admin hoặc truy cập dữ liệu nhạy cảm.

### Recovery

- Xác minh account owner bằng quy trình độc lập;
- Re-enroll passkey/MFA;
- Kiểm tra recovery email/phone và thiết bị tin cậy;
- Rotate password/credential khi có nguy cơ lộ;
- Revoke session cũ và refresh token family;
- Theo dõi account sau khôi phục.

Không yêu cầu người dùng approve thêm push để chứng minh danh tính trong lúc nghi MFA fatigue. Dùng quy trình xác minh thay thế đã được phê duyệt.

## 16. Playbook: token, session và signing-key compromise

### Token/session theft

**Dấu hiệu:** token được dùng từ context bất thường, refresh token reuse, session tiếp tục hoạt động sau revoke hoặc sensitive action không phù hợp.

**Hành động:**

1. Xác định token type, issuer, audience, scope, subject và token family reference;
2. Xác định resource server đã chấp nhận token nào;
3. Revoke refresh token family, session và grant liên quan;
4. Nếu access token JWT không thể revoke tức thời, dùng denylist/version hoặc giới hạn resource theo policy;
5. Rotate credential nguồn nếu token bị lấy từ client secret/password;
6. Kiểm tra endpoint/log/storage có thể làm lộ token;
7. Xác minh token cũ bị từ chối hoặc hết hạn theo SLA.

### Signing-key compromise

Signing key compromise là sự cố trust cấp cao vì attacker có thể tạo token/assertion giả được verifier tin cậy.

**Hành động khẩn cấp:**

1. Kích hoạt Critical incident và xác định key ID, algorithm, issuer, verifier và token population;
2. Dừng signing bằng key bị compromise;
3. Tạo key pair mới trong KMS/HSM theo quy trình kiểm soát;
4. Publish public key mới và cập nhật issuer/verifier;
5. Block key cũ theo khả năng của verifier; không chỉ chờ token hết hạn nếu attacker có thể tiếp tục ký;
6. Force refresh JWKS/trust cache và kiểm tra node/region còn stale;
7. Revoke session/token có thể bị ảnh hưởng;
8. Điều tra quyền truy cập KMS/HSM và nguồn export/key operation;
9. Tìm token/assertion bất thường được phát hành trong thời gian compromise;
10. Xác minh mọi verifier từ chối token mới ký bằng key cũ.

### Lưu ý

- Public key cũ có thể cần giữ để verify token hợp lệ trong rotation bình thường; khi private key bị compromise, quyết định giữ/bỏ key phải theo incident policy.
- Không export private key sang file hoặc kênh chat để xử lý khẩn cấp.
- Không chỉ đổi key ở issuer; verifier, gateway, cache và regional replica đều phải cập nhật.
- Theo dõi token được ký bằng key mới và sự kiện unknown kid sau rotation.

## 17. Playbook: OAuth client, federation và service credential compromise

### OAuth client secret/API key

- Xác định client ID, owner, audience, scope và consumer;
- Kiểm tra credential đã lộ ở source, CI, log hoặc secret manager;
- Tạo credential mới hoặc client registration thay thế;
- Rollout tới mọi consumer;
- Revoke secret cũ và kiểm tra provider từ chối;
- Revoke grant/token/session liên quan nếu cần;
- Giảm scope và tách credential theo environment.

### Federation trust compromise

- Xác định issuer, SP/client, metadata version và signing certificate;
- Kiểm tra redirect URI, audience, recipient, state, nonce và assertion ID;
- Disable trust relationship bị compromise nếu cần;
- Thay signing certificate/key theo quy trình;
- Xác minh metadata và trust bundle tại mọi consumer;
- Kiểm tra account linking và provisioning phát sinh trong thời gian incident.

### Workload/service identity

- Xác định workload, namespace, node, service account và trust policy;
- Kiểm tra credential type: API key, client secret, mTLS certificate, workload token;
- Revoke/rotate credential và cập nhật consumer;
- Tạm dừng workload hoặc giới hạn network khi cần;
- Kiểm tra secret manager read, KMS signing và service-to-service access;
- Tìm lateral movement sang service khác;
- Xác minh credential cũ không còn được chấp nhận.

## 18. Playbook: identity provider outage hoặc cấu hình sai

Không phải outage nào cũng là security incident, nhưng cần đánh giá liệu lỗi có làm suy yếu quyết định xác thực.

### Dấu hiệu outage

- Token endpoint timeout hoặc 5xx tăng;
- JWKS/discovery không truy cập được;
- MFA provider chậm hoặc không gửi challenge;
- Session store/database unavailable;
- KMS/HSM signing failure;
- Clock drift hoặc TLS/DNS lỗi;
- Nhiều client/region cùng bị ảnh hưởng sau deployment.

### Phân biệt với compromise

- Kiểm tra deployment/configuration gần nhất;
- Đối chiếu provider health và network telemetry;
- Xác định token/signature/issuer có bị chấp nhận sai không;
- Kiểm tra admin change và signing operation bất thường;
- Tìm login/token success từ principal không mong đợi;
- Xem có trust policy bị nới lỏng hoặc fail-open ngoài dự kiến không.

### Ứng phó

- Kích hoạt service incident hoặc mixed incident theo evidence;
- Áp dụng degraded mode đã phê duyệt;
- Local JWT validation chỉ tiếp tục nếu key cache còn tin cậy và token hợp lệ;
- Opaque token introspection cache miss không được coi là active;
- Không bỏ qua signature, issuer, audience hoặc MFA policy;
- Giới hạn retry storm và load shedding;
- Phục hồi dependency theo thứ tự;
- Sau phục hồi, kiểm tra token/session được chấp nhận trong outage window.

## 19. Giao tiếp, thông báo và phối hợp bên ngoài

Incident authentication có thể ảnh hưởng quyền truy cập, dữ liệu cá nhân và hoạt động kinh doanh. Thông báo phải chính xác, có kiểm soát và không tiết lộ thông tin giúp attacker.

### Đối tượng

- Người dùng bị ảnh hưởng;
- Application/service owner;
- IAM/security/platform teams;
- Customer support;
- Ban lãnh đạo và incident management;
- Legal/privacy/compliance;
- Identity provider, cloud provider hoặc vendor liên quan;
- Cơ quan/đối tác theo nghĩa vụ áp dụng.

### Nội dung thông báo

- Điều gì đã biết và chưa biết;
- Phạm vi ảnh hưởng đã xác nhận;
- Thời điểm và trạng thái hiện tại;
- Hành động người dùng cần thực hiện;
- Kênh hỗ trợ chính thức;
- Thời điểm cập nhật tiếp theo;
- Hướng dẫn không chia sẻ password, OTP hoặc recovery code.

Không công bố IP, detection threshold, cách thức containment chi tiết hoặc evidence nhạy cảm ra kênh công khai. Mọi thông báo ra ngoài cần người có thẩm quyền phê duyệt.

### Phối hợp vendor

Khi incident liên quan IdP/MFA/cloud vendor:

- Dùng escalation contact đã chuẩn bị;
- Cung cấp timestamp, request ID, tenant/client reference và symptom đã redaction;
- Không gửi raw token, password hoặc private key;
- Yêu cầu xác nhận phạm vi và timeline từ vendor;
- Ghi lại response và quyết định phụ thuộc vendor.

## 20. Kết thúc incident và post-incident review

Không đóng incident chỉ vì alert đã im lặng. Cần có evidence rằng attacker không còn truy cập và hệ thống đã trở lại trạng thái tin cậy.

### Tiêu chí đóng

- Containment hoàn tất và được xác minh;
- Credential/token/session/trust bị compromise đã được revoke hoặc thay thế;
- Persistence đã được kiểm tra;
- Recovery hoàn tất và service health ổn định;
- Monitoring/alert pipeline hoạt động;
- Các owner xác nhận ứng dụng phụ thuộc hoạt động;
- Residual risk và exception được ghi nhận;
- Communications và nghĩa vụ thông báo được xử lý;
- Action item có owner và deadline.

### Post-incident review

Đánh giá:

- Root cause và contributing factors;
- Detection nào phát hiện đầu tiên, detection nào bị thiếu;
- Thời gian từ compromise tới detection/containment/recovery;
- Evidence nào không có hoặc đến muộn;
- Containment có quá rộng hoặc quá hẹp không;
- Degraded mode có tạo rủi ro không;
- Communication có chính xác và kịp thời không;
- Credential lifecycle, access control hoặc policy nào cần thay;
- Test/runbook nào cần bổ sung.

### Action item tốt

Mỗi action item cần:

- Mô tả thay đổi cụ thể;
- Owner;
- Priority;
- Deadline;
- Dependency;
- Cách xác minh hoàn thành;
- Liên kết tới incident/evidence;
- Trạng thái theo dõi.

Tránh kết luận chung như “tăng cường bảo mật”. Hãy nêu kiểm soát cụ thể, ví dụ “bật refresh token reuse detection cho tất cả confidential clients và cảnh báo trong vòng một phút”.

## 21. Mẫu incident record

Mẫu sau là khung tham khảo để ghi nhận incident. Chỉ lưu reference và evidence đã được phép; không điền password, token hoặc secret.

`````````yaml
incident:
  id: IR-2026-0042
  title: Suspected account takeover
  category: authentication
  severity: high
  confidence: medium
  status: investigating
  detected_at: "2026-11-22T07:10:00Z"
  commander: identity-incident-commander
  technical_owner: iam-oncall
scope:
  tenant_ref: tenant-17
  subject_ref: sub-hmac-31a9
  client_id: web-portal
  session_refs:
    - sess-ref-01
evidence:
  alert_ids:
    - alert-2026-0142
  request_ids:
    - req-7d11
  sources:
    - idp-audit
    - api-gateway
    - session-store-audit
timeline:
  - at: "2026-11-22T07:10:00Z"
    event: detection
    note: "Unusual login sequence detected"
  - at: "2026-11-22T07:18:00Z"
    event: containment
    note: "Related sessions revoked"
decisions:
  - action: revoke_session_family
    approved_by: incident-commander
    reason: suspected_session_compromise
    result: completed
recovery:
  credential_reset: pending
  factor_review: pending
  monitoring_window: 24h
`````````

Ví dụ là dữ liệu giả lập. Trong hệ thống thật, incident record cần access control, audit, retention và liên kết evidence được bảo vệ.

## 22. Bộ kiểm thử và diễn tập chấp nhận

| Trường hợp | Cách diễn tập | Kết quả kỳ vọng |
| --- | --- | --- |
| Alert intake | Phát một authentication alert test | Tạo incident record với ID và owner |
| Severity triage | Cung cấp evidence ở nhiều mức impact | Severity/confidence được phân loại riêng |
| Role assignment | Kích hoạt incident High | Có IC, security lead, technical owner và scribe |
| Evidence collection | Thu thập event từ IdP/gateway/session store | Có nguồn, timestamp, request ID và access control |
| Secret redaction | Gửi test token/password marker vào log path | Không xuất hiện trong ticket, chat hoặc alert |
| Timeline | Gửi event từ nhiều service có clock offset | Timeline ghi UTC, event time và ingest time |
| Chain of custody | Export evidence file | Có hash, collector, timestamp và access log |
| Blast radius | Mô phỏng một user compromise | Chỉ principal/resource liên quan được xác định |
| Password spraying | Phát event trên nhiều subject | Phát hiện campaign và không khóa nhầm toàn tenant |
| Credential stuffing | Mô phỏng login success sau chuỗi failure | Kiểm tra session và action tiếp theo |
| MFA fatigue | Nhiều deny/timeout rồi approve | Alert và playbook yêu cầu xác minh factor |
| Passkey enrollment abuse | Thêm credential lạ sau login risk | Phát hiện enrollment và hỗ trợ revoke |
| Account takeover | Login lạ rồi thay recovery factor | Revoke session/token và xác minh owner |
| Refresh token reuse | Dùng token family đã rotate | Revoke family theo policy và audit |
| Session theft | Dùng session từ context bất thường | Session bị giới hạn/revoke sau triage |
| Signing key compromise | Mô phỏng key bị đánh dấu compromised | Dừng signing, rotate key, cập nhật verifier |
| JWKS stale cache | Giữ verifier dùng key set cũ | Xác định node stale và xác minh key bị block |
| OAuth client secret leak | Đánh dấu secret test bị lộ | Rotate client credential và kiểm tra consumer |
| Service API key leak | Dùng key đã revoke | Provider/verifier từ chối credential cũ |
| mTLS certificate revoke | Dùng certificate đã revoke | Handshake/identity bị từ chối theo policy |
| Federation trust change | Thay metadata/redirect URI ngoài change | Alert và kiểm tra issuer/client trust |
| Recovery abuse | Dùng recovery token đã consume | Từ chối replay, không thay credential |
| IdP outage | Chặn token endpoint | Degraded mode đúng policy, không fail-open |
| MFA provider outage | Làm provider timeout diện rộng | Service incident được phân biệt với MFA abuse |
| Session store outage | Làm store unavailable | Không tạo session giả hoặc bỏ qua kiểm tra |
| Break-glass | Dùng emergency account trong exercise | Có approval, MFA, audit và revoke/rotation sau dùng |
| Containment scope | Revoke một subject trong tenant lớn | Không làm gián đoạn principal ngoài phạm vi |
| Containment rollback | Thử khôi phục sau false positive | Có rollback được phê duyệt và audit |
| Eradication | Tìm factor/client/session phụ | Persistence được phát hiện và xử lý |
| Recovery canary | Khôi phục một client/tenant | Login, token, validation và revoke đều đúng |
| Recovery monitoring | Theo dõi sau phục hồi | Không tái xuất hiện dấu hiệu compromise |
| Communications | Soạn thông báo mô phỏng | Nội dung chính xác, được phê duyệt, không lộ secret |
| Vendor escalation | Gửi evidence đã redaction | Vendor nhận đủ context mà không có credential thô |
| Post-incident review | Kết thúc tabletop | Có root cause, owner và action item đo được |
| RTO/RPO | Diễn tập failover/restore | Đạt mục tiêu và kiểm tra state revoke/one-time |
| Alert pipeline loss | Dừng collector trong exercise | Telemetry gap được phát hiện |
| Incident record | Hoàn tất mẫu record | Có timeline, evidence, decision và recovery state |

Diễn tập cần có cả tình huống benign, attack và outage. Mục tiêu không phải chỉ chứng minh người trực biết chạy lệnh, mà còn xác nhận containment không làm mất evidence, không hạ tiêu chuẩn xác thực và không gây ảnh hưởng ngoài phạm vi.

## 23. Checklist ứng phó Authentication incident

- **Detection:** Alert hoặc báo cáo có nguồn, timestamp, event ID và owner?
- **Classification:** Security incident, service incident hay mixed incident?
- **Severity:** Impact, confidence, scope và privilege được đánh giá?
- **Command:** Có incident commander, technical lead, evidence owner và scribe?
- **Evidence:** Log, request ID, session/token reference được bảo toàn và có chain of custody?
- **Privacy:** Không thu thập hoặc chia sẻ password, OTP, token, cookie, private key?
- **Timeline:** Event time, ingest time, clock skew và quyết định được ghi?
- **Blast radius:** User, service, client, tenant, issuer, audience và resource được xác định?
- **Containment:** Session/token/credential/trust bị thu hồi đúng phạm vi?
- **Persistence:** Factor, OAuth grant, client, role, redirect URI và recovery channel lạ đã được kiểm tra?
- **Eradication:** Root cause và credential phụ đã được loại bỏ?
- **Recovery:** Issuer, key, JWKS, session, policy và application được xác minh?
- **Availability:** Degraded mode, retry và failover không bỏ qua authentication?
- **Communications:** Người dùng, owner và vendor nhận thông tin đã được phê duyệt?
- **Monitoring:** Có theo dõi recurrence sau containment/recovery?
- **Closure:** Residual risk, notification và action item được ghi?
- **Learning:** Runbook, alert, test và control được cập nhật?

### Câu hỏi tự kiểm tra

1. Vì sao authentication incident không đồng nghĩa với login failure?
2. Khi nào cần phân loại mixed incident thay vì chỉ security hoặc service incident?
3. Severity khác confidence như thế nào?
4. Vì sao incident commander và evidence custodian cần trách nhiệm riêng?
5. Những trường nào cần có trong timeline và chain of custody?
6. Làm thế nào xác định blast radius khi signing key bị compromise?
7. Vì sao containment không nên chỉ xóa account đầu tiên bị phát hiện?
8. Khi nào nên revoke session/token và khi nào cần rotate signing key?
9. Tại sao không được rollback về credential đã bị compromise?
10. Vì sao outage của identity provider không cho phép bỏ qua signature hoặc audience validation?
11. Những persistence path nào cần kiểm tra sau account takeover?
12. Tiêu chí nào chứng minh incident đã đủ điều kiện đóng?

## Kết luận

**Authentication incident response là quy trình khôi phục trust: xác định điều gì bị xâm phạm, giới hạn quyền của attacker, loại bỏ persistence và xác minh lại danh tính trước khi khôi phục dịch vụ.** Đội ứng phó cần phân loại đúng security incident và outage, phân công vai trò, bảo toàn evidence, dựng timeline và đánh giá blast radius theo principal, credential, token, session, issuer và resource. Containment phải revoke đúng credential/session/grant; signing-key hoặc federation compromise cần xử lý ở phạm vi trust platform. Recovery cần xác minh key, policy, session, factor và mọi verifier trước khi mở lại traffic. Incident chỉ kết thúc khi persistence đã được kiểm tra, service ổn định, người bị ảnh hưởng được hướng dẫn phù hợp và action item có owner. Diễn tập, audit và post-incident review giúp rút ngắn thời gian phát hiện/phản ứng mà vẫn giữ nguyên tiêu chuẩn xác thực và bảo vệ dữ liệu cá nhân.
