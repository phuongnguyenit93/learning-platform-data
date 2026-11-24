# Leaver flow — Thu hồi quyền truy cập khi người dùng rời tổ chức

> **Chương:** Account lifecycle  
> **Chủ đề:** Leaver flow  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào quy trình offboarding khi nhân viên, nhà thầu hoặc người dùng thuộc một tổ chức rời đi: xác định sự kiện có thẩm quyền, vô hiệu hóa account, thu hồi phiên và credential, lan truyền thay đổi tới hệ thống liên kết, bảo toàn dữ liệu cần thiết và kiểm chứng rằng quyền truy cập đã chấm dứt.

## 1. Leaver flow là gì?

**Leaver flow** là quy trình quản lý danh tính và quyền truy cập khi một người không còn đủ điều kiện sử dụng tài nguyên của tổ chức. Sự kiện có thể là nhân viên nghỉ việc, nhà thầu kết thúc hợp đồng, sinh viên tốt nghiệp, đối tác ngừng hợp tác hoặc người dùng bị chấm dứt quyền truy cập theo quyết định có thẩm quyền.

Ví dụ, An là nhân viên có account trong hệ thống Identity Provider (IdP), email, VPN, nền tảng mã nguồn, cloud console và công cụ quản lý dự án. Khi ngày làm việc cuối cùng đến, tổ chức cần ngăn An đăng nhập mới, thu hồi session và token đang hoạt động, gỡ membership/role, xử lý thiết bị và credential, đồng thời chuyển giao quyền sở hữu tài nguyên công việc. Nếu chỉ disable account trong thư mục chính nhưng access token, API key hoặc session ở ứng dụng khác vẫn còn hiệu lực, An có thể tiếp tục truy cập qua những đường đó.

Leaver flow là một phần của **account lifecycle**. Nó cần phối hợp HR/contract management, IAM, IdP, ứng dụng SaaS, hạ tầng, quản lý thiết bị, chủ sở hữu dữ liệu và bộ phận xử lý sự cố.

**Mục tiêu bảo mật:** sau thời điểm hiệu lực đã được phê duyệt, mọi đường xác thực và ủy quyền thuộc phạm vi cần thu hồi phải bị chặn trong thời hạn đã định; các tài nguyên cần lưu giữ hoặc chuyển giao vẫn được xử lý theo policy và có audit.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt leaver flow với user-initiated account closure, suspension và chuyển bộ phận.
2. Xác định nguồn sự kiện offboarding có thẩm quyền và thời điểm hiệu lực.
3. Lập inventory account, credential, session, token, group, device và workload identity liên quan.
4. Thiết kế trình tự disable, revoke, deprovision và xác minh kết quả.
5. Hiểu giới hạn thu hồi của JWT, refresh token, session cache và federation.
6. Xử lý SCIM, event propagation, retry, idempotency và race condition.
7. Bảo toàn dữ liệu, audit, legal hold và chuyển giao tài nguyên mà không duy trì quyền đăng nhập của người rời đi.
8. Xây dựng kiểm thử chứng minh mọi đường truy cập đã bị vô hiệu hóa theo SLA.

## 2. Leaver khác suspension, transfer và account deletion

Không phải mọi thay đổi nhân sự đều có cùng hành động.

| Sự kiện | Ý nghĩa | Xử lý danh tính thường gặp |
| --- | --- | --- |
| **Leaver** | Người dùng rời tổ chức hoặc hết quan hệ được cấp quyền | Disable sign-in, revoke access và deprovision theo phạm vi. |
| **Suspension** | Tạm dừng quyền trong khi quan hệ có thể vẫn tồn tại | Tạm khóa, giữ dữ liệu và credential record theo policy; có thể khôi phục sau phê duyệt. |
| **Transfer** | Chuyển nhóm, đơn vị, vai trò hoặc tenant | Gỡ quyền cũ, cấp quyền mới sau kiểm tra; không mặc định là leaver toàn tổ chức. |
| **Leave of absence** | Nghỉ phép hoặc nghỉ dài hạn | Áp dụng policy riêng, có thể giảm quyền hoặc tạm khóa tùy rủi ro. |
| **Account deletion** | Xóa hoặc ẩn danh dữ liệu account theo policy | Thường là bước riêng sau retention, legal hold và kiểm tra phụ thuộc. |
| **Rehire** | Người đã rời quay lại | Xác minh lại quan hệ và cấp quyền theo quy trình mới; không mặc định mở lại mọi credential cũ. |

Leaver flow không nên bị rút gọn thành “xóa user row”. Account có thể là khóa tham chiếu trong audit, tài liệu, giao dịch và quan hệ ownership. Xóa vật lý quá sớm có thể phá vỡ audit hoặc khiến hệ thống mất khả năng xác định ai đã thực hiện hành động.

## 3. Nguồn sự kiện và quyền quyết định

Leaver flow phải bắt đầu từ **nguồn dữ liệu có thẩm quyền**. Với nhân viên, nguồn thường là HR Information System (HRIS) hoặc quy trình nhân sự được phê duyệt. Với nhà thầu, có thể là hệ thống quản lý hợp đồng hoặc sponsor có thẩm quyền. Với sinh viên/đối tác, nguồn có thể là hệ thống quản lý quan hệ tương ứng.

Một sự kiện nên có:
- định danh người dùng ổn định, ví dụ employee/contractor ID nội bộ;
- loại sự kiện và trạng thái quan hệ;
- thời điểm hiệu lực (effective time);
- thời điểm sự kiện được ghi nhận;
- phạm vi tổ chức/tenant;
- actor hoặc hệ thống phát hành;
- mã yêu cầu/approval reference;
- lý do và phân loại khẩn cấp theo policy.

Không định danh người cần offboard chỉ bằng email hoặc display name. Email có thể đổi, được tái cấp hoặc trùng; dùng khóa ổn định để ánh xạ tới account và các identity liên kết.

### Xác minh nguồn và chống sự kiện giả

Không cho phép một email tự do hoặc request từ client tự kích hoạt offboarding. Event cần xác thực nguồn, kiểm tra quyền phát hành, schema/version, correlation ID và chống replay. Các thay đổi đặc biệt nhạy cảm như chấm dứt khẩn cấp hoặc giữ nguyên quyền trong thời gian chuyển tiếp cần approval theo policy.

### Thời điểm hiệu lực

Phân biệt:
- **Scheduled leaver:** đã biết trước, có thời điểm hiệu lực tương lai.
- **Immediate leaver:** cần chấm dứt truy cập ngay khi được phê duyệt.
- **Delayed/partial offboarding:** một số quyền được giữ tạm thời theo quyết định rõ ràng, ví dụ account chỉ đọc cho bàn giao; phải có owner, scope và expiry.

Không suy ra thời điểm offboarding từ lúc event được gửi nếu HR/contract source cung cấp effective time riêng. Đồng hồ, timezone và xử lý sự kiện đến muộn phải được quy định.

## 4. Inventory danh tính trước khi thu hồi

Một người có thể có nhiều account và credential ngoài account chính. Trước khi kết thúc quyền truy cập, hệ thống cần biết những danh tính và tài nguyên nào thuộc phạm vi.

Inventory có thể gồm:

- account trong directory/IdP chính và các IdP liên kết;
- account local trong ứng dụng SaaS hoặc hệ thống legacy;
- federation identity theo issuer + subject;
- session cookie, server-side session và session version;
- access token, refresh token, token family và API token;
- passkey/WebAuthn credential, security key, OTP seed và recovery code;
- client certificate, device certificate, SSH key và signing key;
- group, role, tenant membership, delegated permission và privileged role;
- thiết bị được quản lý, device certificate và remembered-device record;
- service account, workload identity, automation token và secret mà người đó sở hữu/quản lý;
- quyền sở hữu repository, cloud project, mailbox, lịch, ticket, tài liệu và dữ liệu;
- quyền truy cập vật lý hoặc hệ thống ngoài IAM nếu thuộc phạm vi.

### Liên kết account an toàn

Dùng immutable subject/employee ID và mapping đã quản trị để tìm account. Không tự động thu hồi account khác chỉ vì email giống nhau. Với account liên kết OIDC/SAML, lưu issuer + subject hoặc định danh federation đã xác minh để truy tìm chính xác.

Inventory có thể không đầy đủ nếu tổ chức không có central IAM. Khi đó cần quy trình discovery theo ứng dụng, owner attestation và đối soát định kỳ; không tuyên bố “all access revoked” nếu còn hệ thống ngoài phạm vi chưa được xác minh.

## 5. Thứ tự offboarding và mục tiêu của từng bước

Một trình tự tổng quát:

1. Xác minh sự kiện, người dùng, phạm vi và effective time.
2. Tạo offboarding operation có ID duy nhất và ghi audit.
3. Ngăn đăng nhập mới bằng cách disable account/IdP principal hoặc áp dụng trạng thái chặn tương đương.
4. Thu hồi session đang hoạt động, refresh token và token family.
5. Gỡ group, role, tenant membership, privileged grant và delegated access.
6. Thu hồi credential cá nhân, certificate, SSH key và remembered-device binding theo policy.
7. Thu hồi hoặc rotate secret/workload credential mà người rời đi có quyền sở hữu hoặc biết.
8. Deprovision ứng dụng downstream qua SCIM/API/event hoặc workflow quản trị.
9. Xử lý thiết bị, quyền vật lý, mailbox và tài nguyên công việc.
10. Xác minh kết quả ở các hệ thống, xử lý lỗi và theo dõi retry.
11. Lưu audit, bằng chứng hoàn tất và các ngoại lệ được phê duyệt.

Trình tự thực tế có thể song song hóa, nhưng phải giữ các bất biến: account không được tiếp tục đăng nhập mới sau effective time; session/token cũ phải bị vô hiệu trong SLA; tài nguyên không bị xóa trước khi ownership/retention được xử lý; ngoại lệ có owner và expiry.

~~~mermaid
flowchart TD
    A["Authoritative leaver event"] --> B["Validate identity, scope, approval, effective time"]
    B --> C["Create offboarding operation + audit"]
    C --> D["Disable sign-in at IdP / primary directory"]
    D --> E["Revoke sessions and refresh-token families"]
    E --> F["Remove roles, groups, memberships and grants"]
    F --> G["Revoke credentials, keys and certificates"]
    G --> H["Deprovision downstream apps and devices"]
    H --> I["Transfer ownership / preserve required data"]
    I --> J["Verify every system and retry failures"]
    J --> K["Close with evidence and approved exceptions"]
~~~

## 6. Disable account: chặn đăng nhập mới

Disable account hoặc đặt trạng thái inactive là bước quan trọng để ngăn lần xác thực mới. Tuy nhiên, semantics phụ thuộc từng hệ thống:
- IdP có thể từ chối authentication mới nhưng session cũ vẫn còn.
- Ứng dụng local có thể cache trạng thái account.
- Một số API chỉ kiểm tra chữ ký JWT mà không gọi IdP.
- Service account hoặc API key có thể không phụ thuộc account tương tác.
- Account liên kết có thể tồn tại ở tenant/IdP khác.

Do đó, disable tại directory chính là một lớp kiểm soát, không phải bằng chứng hoàn tất toàn bộ offboarding.

### Không dùng đổi password làm biện pháp duy nhất

Đổi password không tự thu hồi passkey, OTP, client certificate, API key, refresh token hoặc session đã phát hành. Leaver flow cần xử lý từng loại credential và quyền liên quan. Với account dùng password, có thể đặt credential unusable hoặc rotate theo policy, nhưng vẫn phải revoke các đường truy cập khác.

### Account state và audit

Nên giữ trạng thái như ACTIVE, SUSPENDED, DISABLED hoặc DEPROVISIONED theo lifecycle model. Ghi actor, thời điểm, lý do, nguồn event và operation ID. Không xóa account record chỉ để ngăn login; verifier cần nhận biết trạng thái disabled và từ chối.

## 7. Thu hồi session và cookie

Sau khi account bị disable, các session đã tạo trước đó có thể vẫn active. Cần:
- revoke từng server-side session hoặc tăng account/session revocation epoch;
- invalidate cache trên mọi instance/region;
- thu hồi remembered-device/session binding theo policy;
- xử lý session ở các ứng dụng downstream;
- kiểm tra account status hoặc version gần điểm authorization/commit với hành động nhạy cảm.

Xóa cookie từ browser của người rời đi thường không thể bảo đảm vì tổ chức có thể không còn kiểm soát thiết bị hoặc browser đang offline. Điều quyết định là server từ chối session ID cũ. Với session store phân tán, xác định SLA propagation và cách xử lý khi cache invalidation bị lỗi.

## 8. Access Token, Refresh Token và giới hạn revocation

Các loại token có hành vi khác nhau:

| Credential/token | Cách xử lý khi offboarding |
| --- | --- |
| Opaque Access Token | Gọi revocation/introspection theo cơ chế authorization server; kiểm tra resource server policy. |
| JWT Access Token tự xác minh | Có thể còn hợp lệ tới exp nếu API không kiểm tra denylist, version hoặc introspection. Dùng TTL phù hợp và cơ chế revoke cho API nhạy cảm. |
| Refresh Token | Revoke token hoặc token family; ngăn cấp Access Token mới. |
| API key/personal access token | Liệt kê theo owner, revoke và kiểm tra secret được dùng ở automation nào. |
| ID Token | Không phải token API; xử lý local session được tạo từ authentication và logout/revocation liên quan. |
| SAML assertion/authorization code | Thường ngắn hạn và one-time; đảm bảo replay cache/expiry, không nhầm với session dài hạn. |

Không tuyên bố mọi JWT đã bị thu hồi tức thời nếu resource server chỉ xác minh chữ ký và exp. Có thể giảm cửa sổ bằng access token ngắn hạn, introspection, account/session version, denylist hoặc sender-constrained tokens tùy kiến trúc.

Refresh Token đặc biệt quan trọng: nếu còn active, nó có thể tiếp tục cấp Access Token sau khi người dùng rời tổ chức. Token family rotation/reuse detection và revocation phải được thực hiện ở authorization server có thẩm quyền.

## 9. Credential cá nhân: passkey, MFA và certificate

Leaver flow cần vô hiệu các credential gắn với người dùng hoặc thiết bị của họ theo đúng registry.

### Passkey/WebAuthn

- Disable/revoke credential record hoặc gỡ credential khỏi account theo policy.
- Giữ metadata cần thiết cho audit, không lưu private key.
- Kiểm tra discoverable credential và passkey đồng bộ theo mô hình quản lý của RP; revoke server-side binding để assertion mới không còn được chấp nhận.
- Nếu credential được dùng ở nhiều account/service, xác định phạm vi thu hồi và thông báo owner.

### OTP và recovery code

- Vô hiệu OTP seed hoặc authenticator binding.
- Revoke recovery codes và backup methods.
- Không chỉ xóa app trên thiết bị; server-side verifier phải từ chối mã/seed cũ.
- Thu hồi phone/email recovery channel nếu đó là tài nguyên tổ chức được quản lý và policy yêu cầu.

### Client/device certificate

- Thu hồi certificate tại CA hoặc registry theo quy trình.
- Cập nhật CRL/OCSP hoặc trạng thái revocation mà verifier sử dụng.
- Gỡ mapping certificate tới account/device/workload.
- Xử lý private key trên thiết bị do tổ chức quản lý bằng MDM/wipe khi được phép.
- Không dựa vào expiry tự nhiên nếu cần chặn ngay.

### SSH và signing keys

- Gỡ public key khỏi authorized key inventory hoặc hệ thống quản lý truy cập.
- Thu hồi certificate/SSH CA principal nếu dùng certificate-based SSH.
- Rotate signing key/shared secret mà người rời đi biết hoặc kiểm soát.
- Kiểm tra key đã được copy vào CI/CD, laptop khác, repository secret hoặc vault policy.

## 10. Gỡ group, role và delegated access

Một account disabled vẫn có thể để lại quyền hoặc grant trong các hệ thống không kiểm tra trạng thái IdP mỗi request.

Cần rà soát:
- group membership trực tiếp và membership kế thừa;
- role assignment ở tenant, project, subscription và application;
- admin/privileged role và quyền elevation;
- OAuth consent/delegated grants;
- shared mailbox, calendar, file share và service ownership;
- VPN/network access, database grants và cloud IAM;
- external collaboration, guest account và partner organization;
- break-glass hoặc emergency access assignment.

Role mapping phải được kiểm tra ở cả IdP và resource application. Xóa group ở IdP không đảm bảo app đã cập nhật nếu SCIM/event sync lỗi hoặc app cache group claims trong session/token cũ.

### Least privilege và quyền tạm thời

Nếu cần giữ một quyền chỉ đọc cho bàn giao, tạo grant riêng có scope, owner, approval và expiry. Không giữ nguyên account cá nhân của leaver active chỉ để người khác tiếp tục dùng. Không chia sẻ password hoặc passkey của người đã rời đi.

## 11. SCIM và deprovisioning downstream

SCIM có thể giúp đồng bộ lifecycle từ identity system tới SaaS/app. Trong SCIM 2.0, user có thể được vô hiệu hóa bằng cách cập nhật thuộc tính `active` thành false; cách xử lý xóa resource và semantics cụ thể phụ thuộc service provider và hợp đồng tích hợp.

Một flow downstream:
1. Provisioning service nhận leaver event đã xác thực.
2. Ánh xạ immutable subject sang SCIM user ID ở ứng dụng đích.
3. Gửi PATCH/deactivation theo schema và capability đã cấu hình.
4. Xác minh response và trạng thái resource sau cập nhật nếu cần.
5. Ghi kết quả theo từng app; retry lỗi tạm thời.
6. Alert khi ứng dụng không hỗ trợ deprovision tự động hoặc không phản hồi.

Không giả định mọi SaaS hỗ trợ SCIM đầy đủ. Một số ứng dụng cần API riêng, ticket hoặc thao tác admin. Inventory phải ghi rõ owner và cách xác minh.

### Retry và idempotency

Deprovision event có thể gửi nhiều lần. Consumer cần idempotent: nhận lại cùng operation không tạo trạng thái sai hoặc kích hoạt hành động phụ lặp. Dùng event ID/version, lưu kết quả theo target application và retry có backoff. Không bỏ qua lỗi vĩnh viễn; chuyển dead-letter/exception queue và tạo công việc remediation.

## 12. Race condition và cửa sổ truy cập còn sót

Trong hệ thống phân tán, sự kiện offboarding không tới mọi service cùng lúc. Các tình huống:
- người dùng đăng nhập mới giữa lúc HR event được tạo và IdP disable;
- session đã xác minh trước khi account bị disable nhưng request commit sau đó;
- JWT còn hạn ở API không introspect;
- SCIM event tới chậm hoặc bị mất;
- cache role/membership chưa invalidated;
- worker đang chạy với token/secret của leaver.

Các biện pháp:
- xác định effective time và deadline propagation theo mức rủi ro;
- disable primary sign-in sớm theo policy;
- dùng event version và outbox để không mất event sau commit;
- retry và reconcile theo inventory;
- kiểm tra account/session version gần điểm commit cho hành động nhạy cảm;
- giảm TTL của credential có cửa sổ thu hồi hạn chế;
- ưu tiên revoke đồng bộ cho privileged account hoặc sự cố khẩn cấp;
- theo dõi mọi target chưa xác nhận hoàn tất.

~~~text
T0: HRIS ghi leaver event với effectiveAt
T1: IAM nhận và xác thực event
T2: Primary IdP disable account
T3: Session/token revoke được phát hành
T4: SaaS A nhận SCIM deactivation
T5: SaaS B timeout, còn quyền cũ
T6: Retry/reconciliation phát hiện SaaS B chưa deprovision
T7: Owner xử lý ngoại lệ và xác minh trạng thái
~~~

Không đánh đồng “event đã phát” với “mọi hệ thống đã thu hồi”. Cần có trạng thái per-target như PENDING, SUCCEEDED, RETRYING, FAILED hoặc MANUAL_REVIEW.

## 13. Privileged user và leaver khẩn cấp

Account quản trị, cloud operator, security engineer hoặc người có quyền truy cập dữ liệu nhạy cảm cần quy trình ưu tiên. Nếu có nguy cơ insider threat hoặc credential compromise, tổ chức có thể cần thu hồi ngay khi quyết định được phê duyệt.

Ưu tiên:
- disable interactive login ở IdP/directory;
- revoke privileged sessions và refresh token;
- thu hồi elevation/PIM grants, VPN và remote access;
- revoke admin API key, SSH/certificate và cloud role;
- rotate shared secret mà người đó biết;
- khóa/thu hồi device certificate và xử lý thiết bị theo policy;
- theo dõi hoạt động sau effective time;
- bảo toàn audit và evidence theo incident/legal process.

Không dùng một tài khoản cá nhân của leaver làm break-glass. Emergency access phải là danh tính riêng, có owner, kiểm soát độc lập, MFA và audit.

## 14. Service account, workload identity và secret ownership

Nhân viên có thể tạo hoặc quản lý credential được dùng bởi automation. Offboarding cá nhân không nên làm production workload ngừng hoạt động, nhưng cũng không được để secret mà người đó biết tiếp tục mở đường truy cập.

Rà soát:
- service account do người đó tạo hoặc sở hữu;
- API key/personal access token được nhúng trong CI/CD;
- cloud access key và workload federation;
- SSH deploy key, signing key và package registry token;
- database credential, webhook secret và integration secret;
- vault policy, secret rotation ownership và approval group;
- scheduled job, bot và automation dùng credential cá nhân.

Không tự động xóa service account chỉ vì creator đã rời đi. Chuyển ownership sang team/service owner có thẩm quyền, xác minh dependency, rotate secret khi người rời đi có thể biết/kiểm soát, rồi kiểm thử workload. Tránh chuyển nguyên password cá nhân hoặc private key sang người khác.

## 15. Thiết bị, tài sản và quyền truy cập vật lý

IAM offboarding thường cần phối hợp với endpoint/device management và physical security:
- thu hồi device certificate và MDM enrollment khi phù hợp;
- khóa hoặc wipe thiết bị thuộc tổ chức theo policy, legal hold và khả năng quản trị;
- thu hồi VPN profile, Wi-Fi certificate và remote access;
- thu hồi badge, thẻ ra vào, khóa vật lý hoặc quyền phòng lab;
- xử lý thiết bị cá nhân (BYOD) theo thỏa thuận và giới hạn pháp lý;
- thu hồi SIM/phone number do tổ chức quản lý nếu dùng cho MFA;
- kiểm tra bản sao dữ liệu và credential trong backup/endpoint.

Không giả định wipe thiết bị cá nhân luôn được phép. Cần phân biệt thiết bị công ty, BYOD và thiết bị dùng chung; hành động phải có căn cứ, owner và audit.

## 16. Chuyển giao tài nguyên và bảo toàn dữ liệu

Account của người rời đi có thể sở hữu tài nguyên cần tiếp tục hoạt động:
- repository, pull request và package;
- cloud project, subscription và infrastructure;
- mailbox, lịch và tài liệu;
- ticket, incident, dashboard và alert;
- database/schema, secret vault và service integration;
- hợp đồng, hồ sơ và dữ liệu khách hàng.

Trước khi xóa hoặc archive account, xác định owner mới và chuyển giao theo policy. Chuyển ownership không đồng nghĩa chia sẻ credential cá nhân. Ví dụ, mailbox có thể được delegate hoặc archive; người thay thế không nên đăng nhập bằng password của người cũ.

### Retention và legal hold

Phân biệt dữ liệu nghiệp vụ cần lưu, dữ liệu audit cần bảo toàn, credential cần revoke và dữ liệu cá nhân cần xóa theo retention policy. Legal hold có thể yêu cầu bảo toàn một số dữ liệu; nó không phải lý do duy trì quyền đăng nhập của leaver. Giới hạn quyền truy cập dữ liệu được giữ lại cho người có thẩm quyền.

## 17. Rehire và account recovery sau offboarding

Nếu người đã rời quay lại, không nên tự động kích hoạt mọi credential cũ. Cần:
1. Nhận sự kiện rehire từ nguồn có thẩm quyền.
2. Xác minh danh tính và quan hệ mới.
3. Xác định account cũ có thể được tái sử dụng theo policy hay phải tạo account mới.
4. Kiểm tra email/username có thể đã được tái cấp hoặc thay đổi.
5. Cấp lại credential và thiết bị theo quy trình enrollment.
6. Xác minh lại membership, tenant, role và manager.
7. Không khôi phục session, refresh token hoặc credential đã revoke.
8. Ghi audit về liên kết giữa hồ sơ cũ và mới.

Account recovery không được dùng để bỏ qua offboarding. Người dùng cần chứng minh quyền kiểm soát danh tính theo policy trước khi được cấp credential mới.

## 18. Privacy, phân tách nhiệm vụ và thông báo

Leaver event chứa thông tin nhân sự nhạy cảm. Chỉ chia sẻ dữ liệu cần thiết cho từng hệ thống:
- IAM cần định danh, effective time, scope và approval reference;
- app owner cần account/resource cần deprovision;
- endpoint team cần device inventory;
- legal/compliance cần dữ liệu theo phạm vi có thẩm quyền.

Không gửi lý do nghỉ việc hoặc thông tin cá nhân nhạy cảm tới mọi ứng dụng nếu chúng chỉ cần trạng thái active/inactive.

Phân tách nhiệm vụ:
- HR/contract owner xác nhận quan hệ và effective time;
- IAM thực hiện identity disable/revoke;
- application owner xử lý quyền đặc thù;
- data owner tiếp nhận tài nguyên;
- security/audit kiểm tra ngoại lệ và bằng chứng hoàn tất.

Với trường hợp nhạy cảm, thông báo cho người quản lý và người rời đi theo thời điểm được phê duyệt. Không để thông báo sớm làm ảnh hưởng quy trình an toàn, nhưng cũng không giữ thông tin bí mật ngoài nhu cầu hợp pháp.

## 19. Audit và bằng chứng hoàn tất

Một leaver workflow nên có operation ID duy nhất và kết quả cho từng hệ thống đích.

Audit có thể ghi:
- subject/employee ID nội bộ;
- nguồn event và event ID/version;
- effective time và received time;
- actor/approval reference;
- account/tenant/service đã xử lý;
- thời điểm disable, session revoke, token revoke và deprovision;
- credential/device reference đã thu hồi;
- kết quả từng target và retry count;
- resource ownership transfer;
- ngoại lệ được phê duyệt, owner và expiry;
- verification evidence và người xác nhận.

Không ghi password, raw token, private key, recovery code hoặc secret. Bảo vệ audit bằng quyền truy cập tối thiểu, integrity control và retention phù hợp.

### Completion không phải một boolean mơ hồ

Có thể định nghĩa:
- **Identity disabled:** IdP/primary account từ chối login mới.
- **Sessions revoked:** session hiện hành bị từ chối.
- **Credentials revoked:** credential thuộc phạm vi bị vô hiệu.
- **Entitlements removed:** role/group/grant đã gỡ.
- **Downstream deprovisioned:** mọi app target đã xác nhận hoặc có exception.
- **Assets transferred/preserved:** ownership và retention đã xử lý.
- **Verified complete:** mọi yêu cầu bắt buộc hoàn tất hoặc ngoại lệ có approval, owner, scope và expiry.

Nếu một SaaS không phản hồi, workflow không nên ghi “fully complete” nếu chưa có bằng chứng hoặc ngoại lệ được phê duyệt.

## 20. Pseudocode điều phối leaver event

Ví dụ Java minh họa:

~~~java
OffboardingResult processLeaverEvent(VerifiedLeaverEvent event) {
    eventVerifier.requireTrustedSource(event);
    eventVerifier.requireValidSchemaAndSignature(event);
    eventVerifier.requireFreshOrKnownDuplicate(event);

    PersonRecord person =
        personRepository.requireByImmutableSubject(event.subjectId());

    OffboardingOperation operation =
        operationStore.createOrGetIdempotently(
            event.eventId(), person.id(), event.effectiveAt());

    if (operation.isCompleted()) {
        return operation.savedResult();
    }

    // Chặn đăng nhập mới trước khi xử lý các target downstream.
    identityService.disableInteractiveSignIn(
        person.id(), operation.id());

    sessionService.revokeAllSessions(person.id(), operation.id());
    tokenService.revokeRefreshTokenFamilies(person.id(), operation.id());

    entitlementService.removeOrganizationGrants(
        person.id(), operation.id());

    credentialService.revokeUserCredentials(
        person.id(), operation.id());

    // Mỗi target có trạng thái riêng, retry được và có audit.
    for (ApplicationTarget target : inventory.targetsFor(person.id())) {
        targetDeprovisioner.enqueueIdempotently(
            target, person.id(), operation.id());
    }

    assetService.createOwnershipTransferTasks(person.id(), operation.id());
    return operationStore.summarizeCurrentStatus(operation.id());
}
~~~

Đây là pseudocode khái niệm. Production cần:
- kiểm tra event signature/transport identity và approval;
- phân biệt scheduled event với immediate event;
- không thực hiện các bước trước effective time nếu policy không cho phép;
- dùng transaction/outbox để không mất công việc sau khi disable account;
- xử lý từng target độc lập, có retry/backoff/dead-letter;
- bảo đảm thao tác revoke/deprovision idempotent;
- không chạy một vòng lặp đồng bộ không giới hạn trên request path;
- kiểm tra account và target inventory trước khi đánh dấu complete;
- có rollback/compensation được định nghĩa cho event sai hoặc bị hủy, không tự kích hoạt lại credential đã revoke.

## 21. Kiểm thử leaver flow

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Leaver event hợp lệ, effective time hiện tại | Tạo operation và disable account theo policy. |
| Event thiếu immutable subject ID | Từ chối hoặc chuyển manual review; không suy từ email. |
| Event signature/source không tin cậy | Từ chối và audit. |
| Event replay cùng ID | Xử lý idempotently, không tạo side effect sai. |
| Scheduled leaver trong tương lai | Lập lịch đúng effective time, không disable sớm ngoài policy. |
| Immediate leaver | Ưu tiên disable sign-in và revoke theo SLA khẩn cấp. |
| Account tồn tại ở nhiều IdP/tenant | Inventory và xử lý đúng phạm vi đã phê duyệt. |
| Email trùng nhưng immutable subject khác | Không thu hồi nhầm account. |
| Session cookie cũ được replay sau revoke | Tất cả verifier liên quan từ chối. |
| JWT còn hạn sau leaver | API áp dụng TTL/introspection/version policy đã định; rủi ro được ghi nhận. |
| Refresh Token còn active | Token family bị revoke; không cấp Access Token mới. |
| Passkey assertion sau credential revoke | RP từ chối credential. |
| OTP/recovery code cũ | Verifier từ chối. |
| Client certificate bị thu hồi | Verifier nhận trạng thái revoke theo SLA. |
| SSH key/API key cá nhân | Bị gỡ/revoke khỏi inventory tương ứng. |
| Group/role được kế thừa | Quyền hiệu lực được gỡ, không chỉ membership trực tiếp. |
| SCIM target timeout | Target ở trạng thái retry/failed, không bị đánh dấu complete. |
| SCIM event gửi lặp | Deprovision idempotent. |
| Cache invalidation bị mất | Nguồn trạng thái authoritative vẫn chặn session theo SLA. |
| Request đang chạy trong lúc revoke | Hành động nhạy cảm kiểm tra trạng thái gần commit. |
| Service account do leaver sở hữu | Chuyển owner và rotate secret theo dependency; workload được kiểm thử. |
| Thiết bị BYOD | Chỉ thực hiện wipe/retire theo policy và quyền đã xác minh. |
| Repository/mailbox cần bàn giao | Ownership được chuyển, audit và dữ liệu được bảo toàn. |
| Legal hold đang hiệu lực | Giữ dữ liệu cần thiết nhưng account login vẫn bị chặn. |
| Rehire | Cấp lại credential theo flow mới; session/token cũ không được khôi phục. |
| Downstream app ngoài inventory | Không tuyên bố hoàn tất cho đến khi discovery/owner xác minh. |
| Retry sau partial failure | Tiếp tục từ target chưa hoàn tất, không lặp side effect đã commit. |
| Audit review | Có event, actor, target, thời gian, trạng thái và exception; không có secret. |

## 22. Bài tập tình huống

Một kỹ sư rời công ty vào cuối ngày. HRIS gửi event sau thời điểm hiệu lực 20 phút. IdP đã disable account, nhưng một số API chỉ kiểm tra JWT có hạn 8 giờ. Một SaaS không nhận SCIM event do lỗi mạng. Kỹ sư là owner của repository, cloud project và CI/CD secret. Account record bị xóa ngay sau khi IdP disable nên đội vận hành không còn mapping để truy tìm token và resource.

**Yêu cầu phân tích:**

1. Những điểm nào trong leaver flow đang tạo cửa sổ truy cập còn sót?
2. Làm sao thiết kế event/effective time và SLA propagation?
3. JWT còn hạn và refresh token phải được xử lý ra sao?
4. Làm sao retry SCIM mà không deprovision trùng hoặc bỏ sót?
5. Những secret/workload credential nào cần inventory và rotate?
6. Làm sao chuyển ownership repository/cloud/CI mà không chia sẻ credential cá nhân?
7. Vì sao không nên xóa account record ngay sau disable?
8. Tiêu chí nào cho phép workflow báo hoàn tất?

**Hướng phân tích:** HRIS event cần xác thực nguồn, immutable subject, event ID và effective time; phát hiện event đến trễ và kích hoạt urgent remediation theo policy. Disable IdP chặn login mới nhưng không tự vô hiệu JWT tự xác minh; dùng TTL/introspection/version/denylist phù hợp và revoke refresh token family. SCIM target cần retry, dead-letter và manual owner; trạng thái từng app được giữ. Inventory key, deploy token, cloud role, vault secret và service account; chuyển owner, rotate secret mà leaver biết và test workload. Giữ account/audit mapping theo retention, không xóa vật lý trước khi xử lý phụ thuộc. Chỉ báo complete khi mọi target bắt buộc đã xác minh hoặc ngoại lệ có phê duyệt, owner và expiry.

## 23. Checklist review

- [ ] Leaver event đến từ nguồn có thẩm quyền, được xác thực và có approval phù hợp.
- [ ] Định danh dùng immutable subject/employee ID, không chỉ email.
- [ ] Effective time, timezone, urgency và scope được xác định rõ.
- [ ] Inventory bao gồm account, IdP, session, token, credential, role, device và workload identity.
- [ ] Primary sign-in bị disable theo SLA.
- [ ] Session và refresh token family được revoke.
- [ ] JWT/resource server revocation limitation được xử lý rõ.
- [ ] Passkey, OTP, recovery code, certificate, SSH key và API token được rà soát.
- [ ] Group, role, delegated grant và tenant membership được gỡ.
- [ ] SCIM/API downstream có per-target status, retry, idempotency và dead-letter.
- [ ] Cache/replica và request đang chạy có policy race/consistency.
- [ ] Service account/workload secret được chuyển owner và rotate khi cần.
- [ ] Thiết bị công ty, BYOD và quyền vật lý được xử lý đúng policy.
- [ ] Resource ownership được chuyển giao trước archive/deletion.
- [ ] Legal hold và retention được tôn trọng; dữ liệu giữ lại không duy trì login.
- [ ] Rehire không khôi phục credential/session đã revoke một cách mù quáng.
- [ ] Audit ghi event, actor, target, kết quả và exception mà không lưu secret.
- [ ] “Completed” yêu cầu bằng chứng từng target hoặc exception được phê duyệt.
- [ ] Có test event replay, delayed event, partial failure, token TTL, race và retry.

## 24. Ghi nhớ

**Leaver flow là quy trình thu hồi toàn bộ quyền truy cập gắn với một quan hệ đã kết thúc, không chỉ disable một account trong directory.** Cần bắt đầu từ sự kiện có thẩm quyền và định danh ổn định, chặn đăng nhập mới, revoke session/token/credential, gỡ quyền, deprovision ứng dụng downstream, xử lý thiết bị và workload secret, rồi xác minh từng hệ thống. Dữ liệu và tài nguyên được giữ hoặc chuyển giao theo retention/legal policy; account record không bị xóa trước khi audit và dependency được xử lý.

Khi review, hãy hỏi: **Ai có quyền phát hành leaver event và effective time là khi nào? Có tìm được mọi account/credential/token của người đó không? JWT và refresh token còn đường sử dụng nào? SCIM hoặc cache lỗi thì ai theo dõi và retry? Service account và secret có owner mới chưa? Tài nguyên được bàn giao ra sao? Có bằng chứng cho thấy mọi target bắt buộc đã từ chối truy cập không?**
