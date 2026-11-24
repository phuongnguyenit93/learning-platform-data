# Di trú identity provider trong quản lý vòng đời danh tính (IAM)

> **Chương:** IAM migration  
> **Chủ đề:** Di trú identity provider  
> **Phạm vi:** Quản lý vòng đời danh tính theo mô hình Joiner–Mover–Leaver (JML), liên kết IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và thu hồi quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích phạm vi của **di trú Identity Provider (IdP)**, phân biệt thay tầng xác thực/SSO với đổi identity source, directory và hệ thống quản trị quyền IAM/IGA.
2. Lập danh sách ứng dụng, giao thức, chính sách và đối tượng cần chuyển; nhận diện các phụ thuộc SAML, OpenID Connect (OIDC), OAuth, MFA, session, certificate và provisioning.
3. Thiết kế liên kết tài khoản cũ–mới dựa trên danh tính chuẩn và bằng chứng có thẩm quyền, tránh tạo tài khoản trùng hoặc chiếm quyền do ghép nhầm email.
4. Di chuyển trust và cấu hình ứng dụng có kiểm soát, xử lý khác biệt về issuer, subject, SAML NameID, signing key, callback URL và token.
5. Bảo toàn JML, quyền RBAC/ABAC, tài khoản phi con người và khả năng thu hồi khi thay IdP.
6. Chuẩn bị shadow/pilot, cutover, rollback, giám sát và tiêu chí nghiệm thu dựa trên trạng thái **truy cập thực tế**.

**Tình huống xuyên suốt:** Doanh nghiệp chuyển từ IdP-A sang IdP-B, giữ nguyên phần lớn nhân sự và ứng dụng. Nhân viên vẫn có email cũ nhưng ứng dụng có thể nhận **issuer + subject mới**, người dùng cần đăng ký lại MFA, còn một số ứng dụng đã có quyền cục bộ. Làm sao chuyển đăng nhập mà vẫn xác định đúng người, đúng quyền và chặn kịp thời người đã nghỉ việc?

## 2. IdP là gì và di trú IdP thay đổi điều gì?

**Identity Provider** xác thực chủ thể, áp chính sách đăng nhập và phát hành bằng chứng đăng nhập hoặc token cho ứng dụng. Với liên kết danh tính doanh nghiệp, IdP thường tham gia SSO qua SAML hoặc OIDC, MFA, conditional access, federation và quản trị phiên.

| Thành phần | Vai trò chính | Điều cần phân biệt khi di trú |
|---|---|---|
| **Identity source** | Nguồn có thẩm quyền về trạng thái người, ngày bắt đầu/nghỉ, phòng ban, nhà thầu | Thay IdP không tự đổi nguồn HRIS |
| **Directory** | Lưu account, group, thuộc tính; có thể tham gia xác thực | Thay IdP có thể giữ nguyên directory hoặc đổi kèm |
| **IdP** | Kiểm tra danh tính, MFA, chính sách đăng nhập, phát hành assertion/token | Đổi issuer, trust, login flow, session, method MFA |
| **IAM/IGA** | Tạo/liên kết account, điều phối JML, RBAC/ABAC, phê duyệt và access review | Quyết định quyền phải giữ tính liên tục qua hai IdP |
| **Ứng dụng/SP/RP** | Tin cậy IdP, nhận diện user và thực thi quyền cục bộ | Có thể gắn user bằng subject/NameID hoặc account ID riêng |
| **Provisioning connector** | Tạo/sửa/vô hiệu hóa account và nhóm qua SCIM/API | Đăng nhập qua IdP mới không đồng nghĩa account đích đã được liên kết đúng |

Các dạng dự án thường gặp:

- Thay nhà cung cấp IdP hoặc hợp nhất hai tenant sau sáp nhập.
- Chuyển ứng dụng từ xác thực độc lập sang SSO tập trung.
- Thay federation broker, đổi issuer hoặc trust giữa IdP và ứng dụng.
- Tách workforce và customer/partner identity thành các tầng phù hợp.
- Đổi hệ thống directory đứng sau IdP, đồng thời chuyển chính sách MFA/conditional access.
- Chuyển từ giao thức legacy sang OIDC/SAML đã được ứng dụng hỗ trợ, có lộ trình loại bỏ phụ thuộc cũ.

**Quan trọng:** OAuth 2.0 chủ yếu là khung **ủy quyền**; một access token không tự động là bằng chứng đăng nhập dùng để xây dựng session người dùng. Với đăng nhập OIDC, ứng dụng phải kiểm tra ID token và các thuộc tính liên quan theo đúng flow. SAML dùng assertion với quy tắc xác thực và điều kiện riêng. Việc đánh đồng các token là lỗi thiết kế nghiêm trọng.

### 2.1. Luồng trước và sau khi thay IdP

~~~mermaid
flowchart LR
    HR["HRIS / nguồn nhà thầu"] --> IAM["IAM / IGA: JML, RBAC, ABAC"]
    IAM --> DIR["Directory / identity registry"]
    DIR --> IDPA["IdP-A: cũ"]
    DIR --> IDPB["IdP-B: mới"]
    IDPA -. "Trust cũ trong giai đoạn chuyển đổi" .-> APP["Ứng dụng SaaS / nội bộ"]
    IDPB --> APP
    IAM --> PROV["SCIM / API provisioning"]
    PROV --> APP
    APP --> AUDIT["Audit / đối soát quyền và đăng nhập"]
    IDPA --> AUDIT
    IDPB --> AUDIT
~~~

Sơ đồ minh họa hai luồng độc lập:

- **Authentication/federation:** IdP xác thực, phát hành SAML assertion hoặc OIDC token để ứng dụng biết ai đăng nhập.
- **Provisioning/lifecycle:** IAM/IGA và connector quyết định account, role, group và trạng thái hoạt động trong ứng dụng đích.

Nếu ứng dụng hỗ trợ SSO nhưng không hỗ trợ tự thu hồi quyền, việc đổi login URL chưa giải quyết được stale access hoặc orphan account.

## 3. Những bất biến phải giữ trong suốt dự án

Trước khi chạy công cụ, nhóm bảo mật, IAM, hạ tầng và chủ ứng dụng cần thống nhất các điều kiện sau:

| Bất biến | Bằng chứng nghiệm thu |
|---|---|
| **Một chủ thể, một identity chuẩn** | Old subject và new subject đã được liên kết tới cùng canonical person ID |
| **Không ghép sai người** | Matching mơ hồ bị cách ly, không tự động hợp nhất qua email/tên |
| **Không nâng quyền ngoài phê duyệt** | Vai trò/entitlement sau di trú phù hợp chính sách và ngoại lệ được duyệt |
| **Leaver bị chặn đúng hạn** | Kiểm thử cả IdP cũ, IdP mới, refresh token, session và account ứng dụng |
| **Mover mất quyền không còn hợp lệ** | Phát hiện group, direct grant, delegated admin và đặc quyền tồn dư |
| **Không mất MFA và kiểm soát rủi ro đăng nhập** | Có kế hoạch đăng ký/xác minh MFA, điều kiện truy cập và xử lý recovery |
| **Không mất khả năng điều tra** | Mỗi liên kết và thay đổi có owner, thời điểm, correlation ID và kết quả |
| **Có thể tạm dừng/chuyển lại có kiểm soát** | Đã thử rollback, xác nhận ảnh hưởng đến phiên và JML phát sinh |

**Đăng nhập thành công không phải tiêu chí duy nhất.** Người dùng vẫn có thể đăng nhập được trong khi account ứng dụng thuộc người khác, còn quyền cũ hoặc không bị thu hồi khi đã nghỉ việc.

## 4. Khảo sát: không bỏ sót ứng dụng và đường xác thực

### 4.1. Lập inventory ứng dụng

Mỗi ứng dụng cần mô tả:

- Chủ hệ thống và người phê duyệt thay đổi.
- Giao thức: SAML 2.0, OIDC, OAuth, WS-Federation, LDAP/RADIUS, local authentication, social federation hoặc cơ chế riêng.
- Endpoint/metadata: SAML entityID, ACS URL, Single Logout URL; OIDC issuer, discovery URL, authorization/token/JWKS endpoint, redirect URI, logout URI.
- Khóa nhận diện người dùng: SAML NameID, OIDC issuer + sub, email, UPN, immutable ID hay internal user ID.
- Cách liên kết account hiện hữu: pre-link bằng API, thuộc tính bất biến, JIT provisioning, SCIM externalId, mapping thủ công.
- Quyền: app-local role, group claim, SCIM group, direct grant, admin role, token/credential riêng.
- MFA, conditional access, device posture, session lifetime và yêu cầu phục hồi tài khoản.
- Chế độ hỗ trợ hai IdP, chuyển metadata, rotate signing key và phương án khôi phục.
- Mức độ quan trọng, thời gian bảo trì, đường truy cập người dùng và khả năng test.

Ví dụ:

| Ứng dụng | SSO và nhận diện | Provisioning | Rủi ro nổi bật |
|---|---|---|---|
| HR portal | SAML, NameID persistent | SCIM user/group | NameID mới tạo user thứ hai |
| CRM SaaS | OIDC, issuer + sub | SCIM + direct role | Đăng nhập được nhưng giữ quyền trực tiếp cũ |
| Git/CI | OIDC, tổ chức/tenant claim | API/SCIM | OAuth app và bot token vẫn tồn tại |
| VPN | SAML hoặc RADIUS | Group/policy | MFA, session hoặc thiết bị không tương thích |
| Ứng dụng nội bộ cũ | LDAP hoặc local login | Script định kỳ | Không dùng IdP mới; vẫn cần kiểm soát leaver |
| PAM / Admin console | SSO + xác thực nâng cao | Workflow đặc quyền | Chính sách MFA và tài khoản break-glass |

Không suy luận rằng **mọi** ứng dụng đều đi qua IdP cũ. Ứng dụng LDAP hoặc local login có thể tiếp tục tạo đường truy cập độc lập.

### 4.2. Lập inventory identity và phương thức xác thực

Phải tách các nhóm: nhân viên, nhà thầu, tài khoản đối tác B2B, khách/guest, người có nhiều affiliation, quản trị viên, tài khoản break-glass, tài khoản dịch vụ và workload identity.

Đồng thời kiểm tra:

1. **Chính sách MFA:** yếu tố bắt buộc, phương thức chống phishing, trường hợp không có thiết bị, recovery, step-up và user chưa đăng ký.
2. **Ứng dụng tự phục vụ:** reset password, đổi tên, self-service group, báo mất thiết bị, đăng nhập lần đầu.
3. **Các đường kết nối:** browser, mobile/native app, VPN, CLI, desktop, API, service-to-service, ứng dụng offline.
4. **Token và session:** thời hạn, phạm vi, cache, logout, thu hồi refresh token, sự kiện đồng bộ trạng thái.
5. **Phụ thuộc federation bên ngoài:** IdP đối tác, social login, cross-tenant B2B, trust ký chứng thư và domain discovery.
6. **Tài nguyên đang dùng:** group claim, role claim, thiết bị đã đăng ký, quyền local, API key và delegated permissions.

### 4.3. Chụp baseline trước khi sửa trust

Cần biết tại thời điểm chuẩn:

- Số lượng user, group, service principal/workload identity đang active.
- Số app liên kết IdP, thành công/thất bại đăng nhập theo app và cohort.
- Quyền kỳ vọng và quyền thực tế, đặc biệt privileged role và direct grant.
- Số trường hợp orphan, duplicate và mapping chưa xác minh.
- Độ trễ của JML, SCIM, deprovisioning, đồng bộ trạng thái.
- MFA enrollment, tỷ lệ ứng dụng hỗ trợ logout/session revocation, danh sách token/secret cần chuyển.

Baseline giúp phân biệt **lỗi có sẵn** với drift phát sinh do di trú.

## 5. Danh tính chuẩn và account linking an toàn

Đây thường là phần quan trọng nhất: người dùng có thể không đổi email nhưng định danh federation có thể thay.

### 5.1. Các khóa không có cùng phạm vi

| Định danh | Chủ thể sở hữu và phạm vi | Nguy cơ khi di trú |
|---|---|---|
| **Canonical person ID** | Identity registry/IAM, biểu diễn chủ thể thực ổn định | Phải giữ liên tục, không tái sử dụng |
| **Directory object ID** | Đối tượng tại directory/tenant riêng | Có thể đổi khi chuyển tenant/directory |
| **OIDC issuer + sub** | Cặp định danh chủ thể trong issuer | Nếu issuer/sub đổi, app có thể tạo account mới |
| **SAML NameID + ngữ cảnh issuer** | Giá trị chủ thể trong assertion và quan hệ trust | Format hoặc giá trị mới có thể làm mất liên kết |
| **SCIM id** | ID tài nguyên do service provider cấp | Không tự bằng object ID trong IdP |
| **SCIM externalId** | Khóa liên kết do client quản lý | Phải xác minh cách ứng dụng dùng và giữ ổn định |
| **Email/UPN** | Địa chỉ liên hệ/tên đăng nhập | Có thể đổi, bị tái sử dụng hoặc trùng giữa tổ chức |
| **Internal application user ID** | Khóa dữ liệu và quyền trong ứng dụng | Cần ưu tiên giữ nguyên, tránh làm mất lịch sử |

**OIDC sub** chỉ có ý nghĩa trong phạm vi issuer. Hơn nữa, nhà cung cấp có thể dùng subject **public** hoặc **pairwise** tùy cấu hình client/sector, vì vậy cùng người ở hai client chưa chắc có cùng sub. Không biến sub thành canonical person ID dùng xuyên mọi IdP.

**SAML NameID** có thể dùng format persistent, transient hoặc emailAddress tùy ứng dụng; NameID transient không phải khóa bền vững để map user. Với SAML, issuer, format, yêu cầu app và account linking phải được ghi rõ.

### 5.2. Mapping được xác minh, có thể kiểm toán

Ví dụ minh họa một người được liên kết qua IdP-A và IdP-B:

~~~yaml
canonicalPersonId: person-00672
personType: employee
lifecycleState: active
federatedIdentities:
  - idp: idp-a
    protocol: oidc
    issuer: https://login-old.example.org/
    subject: subject-old-682
  - idp: idp-b
    protocol: oidc
    issuer: https://login-new.example.org/
    subject: subject-new-912
applicationLinks:
  - app: crm
    appUserId: crm-user-421
mappingEvidence:
  reference: verified-hr-person-link
  approvedBy: identity-steward
  version: 6
~~~

Đây là **dữ liệu mô phỏng**, không phải schema của nhà cung cấp hay địa chỉ triển khai thật.

Quy trình matching:

1. Xác định canonical person ID từ nguồn có thẩm quyền về chủ thể, không tin email tự khai.
2. Tạo bảng old issuer/subject ↔ canonical ID ↔ new issuer/subject có bằng chứng kiểm tra.
3. Xác minh account ứng dụng nào tương ứng với canonical ID; dùng chức năng linking do ứng dụng hỗ trợ.
4. Đưa trường hợp nhiều–một, một–nhiều hoặc thiếu bằng chứng vào **quarantine**, tạm ngừng tự động hợp nhất/cấp quyền.
5. Lưu người phê duyệt, mapping version, thời gian hiệu lực, nguyên nhân sửa và audit trước/sau.
6. Giữ mapping cũ theo retention policy để đối soát và rollback; không công khai bảng này rộng rãi.

**Link** là liên kết hai account đã xác minh của cùng một chủ thể. **Merge** là gộp hồ sơ từng được coi là hai chủ thể, có thể ảnh hưởng dữ liệu, lịch sử phê duyệt và quyền. Merge cần quy trình kiểm soát riêng.

### 5.3. Tại sao không tự ghép bằng email?

Một email cũ có thể được cấp lại cho nhân viên mới; guest từ hai tổ chức có thể cùng một địa chỉ ở các context khác nhau; nhà thầu chuyển thành nhân viên có identity lifecycle khác; tên miền mới có thể tạo collision. Nếu ứng dụng tự link dựa vào email không được xác minh, người dùng có nguy cơ đăng nhập vào account và dữ liệu của người khác.

Ví dụ sai: IdP-B phát email claim “lan@example.org”, ứng dụng tìm account cũ cùng email rồi tự hợp nhất, bất kể issuer hay proof. Cách an toàn là **pre-link** theo mapping có thẩm quyền, hoặc dùng cơ chế linking do ứng dụng hỗ trợ với xác minh quyền sở hữu cả hai bên và phê duyệt phù hợp.

## 6. Di trú OIDC và OAuth: trust, token và đăng nhập

### 6.1. Những giá trị phải so khớp

Với mỗi OIDC relying party (RP), kiểm tra:

| Thành phần | Ý nghĩa | Kiểm tra khi đổi IdP |
|---|---|---|
| **Issuer (iss)** | Bên phát hành ID token | Chính xác với issuer được cấu hình tin cậy |
| **Subject (sub)** | Chủ thể theo issuer | Liên kết account qua canonical ID; không tự dùng email |
| **Audience (aud)** | Client/ứng dụng được nhận token | Token cho ứng dụng khác phải bị từ chối |
| **Client ID/secret** | Định danh, bí mật hoặc credential client | Tạo/cấp phát theo quy trình bảo mật và rotate |
| **Redirect URI** | Đích callback được đăng ký | Khớp chính xác URI đã phê duyệt |
| **JWKS/signing keys** | Khóa xác minh chữ ký token | Cache/rotate và kiểm tra chữ ký đúng |
| **Nonce, state, PKCE** | Ràng buộc request/response, chống replay/CSRF và interception | Thử flow tương ứng, dùng PKCE khi thích hợp |
| **Scopes/claims** | Thông tin và quyền yêu cầu | Chỉ yêu cầu và sử dụng claim cần thiết |
| **Logout/session** | Kết thúc phiên tại RP/IdP | Chứng minh phiên, refresh token được xử lý theo khả năng sản phẩm |

Phần lớn RP có thể dùng metadata discovery để lấy endpoint và JWKS. Dù vậy, **không** được tin bất cứ issuer hay JWKS URL nào chỉ vì nhận được từ một token chưa xác thực. Ứng dụng phải xác minh issuer, audience, signature, expiration, nonce (khi áp dụng), các điều kiện giao thức và chính sách tin cậy.

**ID token** dùng cho xác thực OIDC. **Access token** dùng để gọi resource server trong phạm vi được cấp. Ứng dụng không được coi access token phát cho API khác là ID token hay bỏ kiểm tra chữ ký và audience.

### 6.2. Thay signing key không giống đổi issuer/subject

Có ít nhất ba loại thay đổi độc lập:

- **Rotate key:** Có thể giữ nguyên issuer và subject, chỉ thay chứng thư/khóa ký; cần cấu hình chấp nhận các khóa hợp lệ trong giai đoạn luân chuyển.
- **Đổi issuer/client:** Trust và audience thay, có thể cần app reconfiguration hoặc tạo client mới.
- **Đổi subject:** Thay khóa người dùng; cần mapping và account linking, dù email vẫn giữ.

Kiểm thử riêng từng loại sẽ dễ xác định nguyên nhân hơn chuyển mọi thứ cùng lúc.

### 6.3. Native/mobile và máy dùng CLI

Browser app, mobile app và CLI có thể sử dụng các OAuth flow khác nhau. Kiểm tra ứng dụng native có dùng authorization code + PKCE, registered redirect URI, deep link/loopback và session refresh. Một client cũ chỉ hoạt động với grant lỗi thời có thể cần nâng cấp ứng dụng trước khi đổi IdP. Không nới lỏng token validation để che lỗi tương thích.

## 7. Di trú SAML: federation metadata và account binding

Với mỗi Service Provider (SP), phải kiểm tra:

- **IdP entityID / issuer:** SP có tin đúng IdP mới không?
- **SAML SSO URL, SLO URL:** Đường đăng nhập/đăng xuất và binding hỗ trợ.
- **X.509 certificate:** Chứng chỉ dùng xác minh chữ ký và kế hoạch chuyển đổi; cần phân biệt chứng chỉ ký với TLS endpoint.
- **SP entityID / audience:** Assertion phải gửi đúng SP.
- **Assertion Consumer Service (ACS):** Recipient/Destination và URL nhận assertion phải hợp lệ.
- **NameID format/value:** Ứng dụng liên kết người dùng bằng khóa nào?
- **Attribute statements/group claims:** Đúng schema, giới hạn kích thước claim và chính sách vai trò.
- **Response/Assertion signature, Conditions:** InResponseTo (với SP-initiated), time validity, audience restriction và replay protection.
- **AuthnContext / session handling:** Cách SP yêu cầu mức xác thực và xử lý logout.

Các trường như email hoặc group có thể dùng để hiển thị/phân quyền, nhưng không đương nhiên là định danh bền vững. Trước cutover, xác minh SP có hỗ trợ **hai trust song song**, thay cấu hình bằng metadata mới hay chỉ có một IdP tại một thời điểm. Kịch bản một trust duy nhất cần cửa sổ và kế hoạch rollback rõ hơn.

### Ví dụ lỗi

SP cũ lưu user dưới NameID “A-219”. IdP-B phát NameID “B-410” cho cùng người. SP tạo hồ sơ mới rỗng, trong khi hồ sơ cũ vẫn giữ dữ liệu và quyền. Mở SSO mà chưa pre-link sẽ che lỗi: người dùng đăng nhập được nhưng mất dữ liệu, hoặc admin cấp lại quyền sai.

Giải pháp là xác minh capability của SP: immutable app ID, API linking, custom attribute có kiểm soát, nhà cung cấp hỗ trợ migration, hoặc bước chuyển đổi hồ sơ được phê duyệt. Không tự sửa ID trong cơ sở dữ liệu ứng dụng nếu sản phẩm không hỗ trợ.

## 8. Chính sách xác thực, MFA và phục hồi tài khoản

### 8.1. MFA không tự chuyển cùng account

Mỗi IdP có cách lưu đăng ký authenticator, passkey/FIDO2, phương thức recovery, device trust và chính sách rủi ro riêng. Không mặc định sao chép hash mật khẩu, private key hay trạng thái MFA sang IdP khác. Trong nhiều kịch bản, người dùng phải đăng ký lại MFA hoặc passkey bằng quy trình nhà cung cấp hỗ trợ.

Thiết kế cần bao gồm:

1. Chính sách MFA theo vai trò, rủi ro, ứng dụng, thiết bị và vị trí.
2. Quy trình **proofing/recovery** cho người không truy cập được thiết bị cũ hoặc chưa đăng ký.
3. Phương thức chống phishing cho quản trị viên và hệ thống nhạy cảm khi có hỗ trợ.
4. Step-up authentication cho hành động rủi ro và quản lý session.
5. Giới hạn helpdesk reset: xác minh danh tính qua kênh có thẩm quyền, lưu audit và áp hạn chế quyền tạm thời.
6. Tài khoản break-glass được kiểm soát, độc lập khi federation gặp sự cố, có giám sát và diễn tập.

Không nên tạm tắt MFA diện rộng để đạt tỷ lệ đăng nhập cao trong ngày cutover; phải có ngoại lệ rất hẹp, được duyệt, có thời hạn và nhật ký.

### 8.2. Session, token và logout

Đổi IdP **không nhất thiết làm mất ngay mọi phiên đã có** tại SP hoặc resource server. Cookie ứng dụng, access token, refresh token, API key và session bên thứ ba có vòng đời độc lập.

Khi user bị leaver hoặc xảy ra sự cố bảo mật, cần kế hoạch theo từng đích:

- Disable account tại nguồn đăng nhập còn hoạt động.
- Thu hồi refresh token/phiên theo cơ chế IdP và ứng dụng hỗ trợ.
- Thu hồi hoặc làm hết hiệu lực API token, personal access token và local credential liên quan.
- Giảm session lifetime hoặc buộc reauthentication ở app nhạy cảm theo rủi ro và khả năng hệ thống.
- Dùng reconciliation và nhật ký đích để xác minh thực tế, vì “gửi lệnh revoke” chưa chứng minh đã mất truy cập.

Một số token tự chứa đã phát hành có thể tiếp tục hợp lệ tới khi hết hạn nếu resource server không có cơ chế thu hồi phù hợp; thiết kế SLA thu hồi phải phản ánh giới hạn này.

## 9. Bảo toàn Joiner–Mover–Leaver khi thay IdP

Identity source có thẩm quyền xác nhận JML; IdP thực hiện một phần chính sách xác thực. Hệ thống IAM/IGA và ứng dụng vẫn chịu trách nhiệm về account và quyền.

| Sự kiện | Trạng thái kỳ vọng | Kiểm thử xuyên hai IdP |
|---|---|---|
| **Joiner** | Xác minh chủ thể, tạo/link account, kích hoạt đúng ngày, cấp quyền tối thiểu | Không tạo user/app account kép; MFA có thể đăng ký an toàn |
| **Mover** | Cập nhật department/manager/role; cấp mới và thu hồi quyền cũ; SoD | Group/claim mới đúng, direct grant và delegated role cũ được rà soát |
| **Leaver** | Chặn đường đăng nhập, thu hồi session/token, account app và quyền | Không còn đăng nhập qua IdP-A khi đã chuyển IdP-B; revoke trong SLA |
| **Rejoiner** | Xác minh danh tính lại, quyết định link hay tạo lại theo chính sách | Không tự khôi phục quyền cũ không còn lý do |
| **Contractor/guest hết hạn** | Dựa vào hệ nguồn nhà thầu/đối tác có thẩm quyền | Không phụ thuộc hoàn toàn vào HRIS nhân viên |

### 9.1. Joiner và JIT provisioning

Một số ứng dụng tự tạo user ở lần SSO đầu tiên (**just-in-time provisioning**). Khi di trú IdP, cơ chế này có thể tạo hồ sơ thứ hai nếu subject/NameID đổi.

Cần kiểm tra user hiện hữu đã được pre-link trước khi cho JIT chạy; hoặc tạm chặn auto-create với trường hợp mapping không chắc chắn. Không cho auto-create trên email claim chưa được xác minh.

### 9.2. Mover và quyền dựa trên claim

Nếu ứng dụng map role từ SAML group claim/OIDC claim, thay tên group hoặc format claim có thể giữ sai quyền cũ hoặc làm mất quyền cần thiết. Chuẩn hóa **ý nghĩa role** theo policy IAM/IGA, xác định writer và phê duyệt chuyển đổi mapping. Kiểm tra cả user thuộc nhóm lồng và quyền cấp trực tiếp.

### 9.3. Leaver và truy cập tồn dư

Leaver có thể vẫn dùng:

- Phiên SSO cũ đã phát;
- Local login trong ứng dụng;
- Token API, SSH key, personal access token;
- Tài khoản tại SP chưa bị deprovision;
- IdP-A còn được SP chấp nhận trong giai đoạn coexistence;
- Guest account hoặc quyền delegated ở tenant khác.

Vì vậy, **disable user ở IdP-B chưa đủ**. Kiểm thử ngược với IdP-A và các đường truy cập phụ trong cửa sổ chuyển đổi; chỉ đóng trust cũ khi chắc chắn tất cả phụ thuộc đã được xử lý.

Không coi user “biến mất khỏi batch sync” là leaver chắc chắn. Phải có dữ liệu nguồn đáng tin, guardrail cho bulk disable và xác minh các thay đổi bất thường.

## 10. Provisioning, SCIM và trạng thái account tại ứng dụng

### 10.1. Phân biệt SSO với account lifecycle

Ứng dụng có thể xác thực qua IdP-B nhưng account tại SP vẫn do SCIM client cũ tạo ra, hoặc được quản lý thủ công. Cần xác định:

- Ai là chủ thể quản lý SCIM user/group?
- Khóa **SCIM id** của SP có được giữ không?
- **externalId** có được dùng nhất quán giữa hai bên không?
- Quyền local và app API nào không qua SCIM?
- Cơ chế deactivation, soft delete, restore, xử lý user bị xóa/khóa thế nào?
- Retry, rate limit và event ordering có tạo account trùng hoặc hồi sinh quyền không?

### 10.2. Quy tắc triển khai an toàn

1. Đọc và đối soát account hiện có ở SP trước khi đổi SCIM writer.
2. Duy trì mapping canonical ID ↔ SCIM id ↔ IdP-A/IdP-B.
3. Quy định một writer có thẩm quyền cho thuộc tính và entitlement ở từng giai đoạn.
4. Thử dry-run trên nhóm nhỏ; kiểm tra kết quả tạo/sửa/vô hiệu hóa/quản lý group.
5. Idempotency: gửi lại event cùng ID không tạo user hoặc cấp quyền lặp.
6. Trạng thái source **không khả dụng** phải khác với source **đã xác nhận leaver**.
7. Reconcile quyền trực tiếp và role cục bộ không nằm trong SCIM, có owner xử lý.
8. Sau cutover, thu hồi credential/quyền của SCIM client cũ theo kế hoạch.

**Ví dụ:** Sau khi đổi IdP, ứng dụng CRM vẫn có account cũ gắn cùng internal CRM user ID. Connector SCIM mới phải **link tới account đó**, không tạo account theo email rồi để account cũ mồ côi. Kiểm tra direct role vẫn hợp lệ trước và sau link.

## 11. RBAC, ABAC, conditional access và SoD

**RBAC** quyết định quyền theo vai trò; **ABAC** dùng thuộc tính như department, employmentType, location hoặc thuộc tính của tài nguyên. IdP còn có conditional access quyết định việc được đăng nhập trong điều kiện cụ thể.

Các lớp này không hoàn toàn thay thế nhau:

| Kiểm soát | Nơi thường thực thi | Tình huống migration |
|---|---|---|
| Role/nhóm tổ chức | IAM/IGA, directory, ứng dụng | Tên group mới không tự bảo đảm quyền tương đương |
| Chính sách ABAC | Policy engine, ứng dụng, IdP hoặc gateway | Claim/attribute không nhất quán khiến quyết định sai |
| MFA/conditional access | IdP | Quy tắc cho device, rủi ro, admin có thể khác sản phẩm |
| SoD | IGA hoặc workflow cấp quyền | Nhân viên không được đồng thời giữ các quyền xung đột |
| App-local/admin role | Ứng dụng/PAM | SSO chuyển xong vẫn có direct grant hoặc service token cũ |

Ví dụ: quyền “duyệt thanh toán” cấp qua role FIN_APPROVER ở ứng dụng. IdP-A phát claim group “Finance/Approver”, IdP-B phát “FIN_APPR”. Chỉ đổi group claim mà không cập nhật app role mapping có thể khiến người đúng mất quyền; nếu giữ default admin role tạm thời sẽ tạo rủi ro vượt quyền. Giải pháp là ánh xạ vai trò có phê duyệt và test trên actual entitlement.

Các ngoại lệ chuyển đổi cần owner, lý do, thời hạn, phạm vi và người duyệt. Không để quyền tạm thời tồn tại vô thời hạn sau go-live.

## 12. Tài khoản phi con người và danh tính bên thứ ba

### 12.1. Service account, workload identity và automation

Không phải danh tính nào cũng đi qua luồng SSO tương tác của nhân viên. Nhiều workload dùng OAuth client credentials, service principal, certificate, federated workload identity, secret, managed identity hoặc API key.

Với mỗi service integration:

- Liệt kê client ID, issuer, audience, scope/role, endpoint và tài nguyên đang tin cậy.
- Xác định owner chịu trách nhiệm và mối liên hệ với nhân viên (nếu có).
- Tạo credential/trust phía IdP mới theo cơ chế chính thức; đưa bí mật vào vault, giới hạn quyền.
- Kiểm tra quyền của workload tại resource server và lưu dấu vết hoạt động.
- Lên lịch rotate/revoke credential, certificate và token cũ sau khi xác nhận đích.
- Kiểm thử tình huống owner nghỉ việc: chuyển ownership, không làm đứt job hoặc để service account vô chủ.

Không tự xem OAuth access token của workload là “user SSO”. Một ứng dụng server-to-server cần kế hoạch chuyển trust, client authentication và permission riêng.

### 12.2. Partner, guest và B2B federation

Identity khách/đối tác có thể được xác thực từ **home IdP** bên ngoài, còn quyền được thực thi trong tenant ứng dụng của doanh nghiệp. Di trú cần biết ai có thẩm quyền quản lý guest lifecycle, trust liên tenant, kiểm tra email/domain và thời hạn truy cập. Đảm bảo đối tác không bị ghép vào user nội bộ do trùng email, và quyền external vẫn được review/expire đúng hạn.

## 13. Các chiến lược di trú IdP

| Chiến lược | Cách triển khai | Phù hợp | Rủi ro cần xử lý |
|---|---|---|---|
| **Phased per application** | Chuyển từng ứng dụng sang IdP-B, giữ app khác ở IdP-A | Nhiều ứng dụng có owner khác nhau | User gặp hai phương thức đăng nhập; cần kiểm soát JML xuyên hai nơi |
| **Phased per cohort** | Chuyển theo đơn vị hoặc nhóm người dùng | Ứng dụng hỗ trợ routing/account linking theo cohort | Phân tuyến nhầm user; group/app chung giữa cohort |
| **Dual federation** | Ứng dụng hỗ trợ đồng thời hai trust trong thời gian giới hạn | SP/RP hỗ trợ rõ ràng, đã test | Hai account/subject cùng tồn tại; leaver có thể đi qua trust cũ |
| **Federation bridge/broker** | Một broker duy trì mặt giao tiếp cho app trong khi thay upstream IdP | Giảm thay đổi cho ứng dụng khó nâng cấp | Tăng phụ thuộc broker, vẫn phải kiểm thử claim/subject và policy |
| **Big-bang cutover** | Đổi toàn bộ trust trong một cửa sổ | Hệ nhỏ, phụ thuộc ít, rehearsal kỹ | Sự cố SSO diện rộng, rollback phức tạp |
| **Application rebuild/link** | Tạo trust/client mới, liên kết account hiện hữu | Đổi tenant/issuer bắt buộc | Sai mapping và không thể giữ app user ID |

Không có chiến lược tối ưu cho mọi hệ thống. Chọn dựa trên khả năng ứng dụng hỗ trợ multi-IdP, tính ổn định subject, mức phụ thuộc, khối lượng người dùng, SLA, hỗ trợ rollback và mức độ chấp nhận gián đoạn.

Ưu tiên **shadow evaluation** của mapping/claim/policy và **pilot có đại diện** trước khi chuyển production quy mô lớn. Shadow là so sánh kết quả dự kiến, không nên trở thành writer thứ hai ngoài kiểm soát.

## 14. Quy trình triển khai từng giai đoạn

### Giai đoạn A — Discover và thiết kế

1. Xác nhận phạm vi IdP, directory, nguồn HR, ứng dụng, tenant, guest, admin và workload identity.
2. Thu thập hợp đồng trust/protocol, danh sách callback, claim, certificate, token lifetime và group/role mapping.
3. Chụp baseline đăng nhập, JML, actual entitlements, orphan/duplicate, MFA enrollment, thông tin recovery.
4. Thiết kế canonical identity mapping, workflow xử lý account mơ hồ, retention/audit và phân quyền xem bảng mapping.
5. Xác định người phê duyệt go/no-go, điều kiện rollback, lịch bảo trì và kênh thông báo người dùng.

### Giai đoạn B — Xây dựng môi trường đích

1. Cấu hình IdP-B, domain, federation, logging, MFA, policy, break-glass và phân quyền admin tối thiểu.
2. Tạo client/SP integration trên môi trường kiểm thử; cấu hình issuer, audience, redirect URI, ACS, signing key và certificate hợp lệ.
3. Chuyển các chính sách đăng nhập, group/role/claim; ghi rõ khác biệt về khả năng sản phẩm.
4. Liên kết account đã xác minh; xử lý JIT/SCIM và chặn merge tự động mơ hồ.
5. Chuẩn bị phương án đăng ký MFA/phục hồi cho user và chuyển workload credential.
6. Thiết lập monitoring, truy vết, cảnh báo, guardrail và kênh hỗ trợ.

### Giai đoạn C — Shadow, dry-run và pilot

- So sánh kết quả claim/role/mapping IdP-A và IdP-B trên cùng tập chủ thể.
- Thử ít nhất các cohort: user thường, admin, người đổi tên, joiner tương lai, mover, leaver, nhà thầu, guest, người không có thiết bị MFA, người dùng mobile/VPN và owner service account.
- Kiểm tra cả kết quả **đăng nhập thành công**, **đăng nhập bị từ chối đúng lý do** và **thu hồi quyền**.
- Thử flow lỗi: token không đúng issuer/audience, hết hạn, chữ ký không hợp lệ, request lặp, SAML replay, subject chưa được link, SCIM lỗi, signer/certificate rotate.
- Ghi và xử lý các exception trước khi mở rộng.

### Giai đoạn D — Cutover theo cohort/ứng dụng

1. Công bố cửa sổ, xác minh backup cấu hình, snapshot mapping, tài khoản khẩn cấp và người trực xử lý.
2. Khóa/migrate writer theo kế hoạch; xác nhận HR/JML tiếp tục là nguồn điều khiển trạng thái.
3. Chuyển metadata/trust, routing, DNS hoặc endpoint cấu hình **theo ứng dụng**, xác nhận ký và handshake.
4. Kiểm thử trực tiếp: login/logout/MFA, account linking, policy, role, JML, quyền ứng dụng, thiết bị và API.
5. Replay event delta có idempotency và thứ tự hiệu lực; không để event cũ mở lại account leaver.
6. Theo dõi đăng nhập, provisioning, quyền và incident; quyết định mở rộng cohort hoặc pause.

### Giai đoạn E — Stabilize và retire

- Đối soát desired/actual access và xử lý orphan, duplicate, direct grant hoặc token tồn dư.
- Kiểm tra mọi ứng dụng trong phạm vi đã loại bỏ trust/credential IdP-A khi thích hợp.
- Thu hồi SCIM connector, secret, certificate, OAuth client và quyền quản trị IdP-A không còn cần.
- Giữ bằng chứng audit và mapping theo retention policy.
- Chỉ decommission IdP-A khi owner các ứng dụng xác nhận không còn phụ thuộc và rollback window đã được xử lý.

## 15. Thiết kế xử lý account linking và event JML

Một luồng an toàn cần kiểm tra **nguồn, mapping, version và policy hiện hành** trước khi phát sinh quyền:

~~~text
onIdentityEvent(event):
    requireTrustedAuthoritativeSource(event)
    if alreadyProcessed(event.eventId):
        return NO_OP

    person = resolveCanonicalPersonWithVerifiedEvidence(event)
    if person is ambiguous:
        quarantine(event)
        notifyIdentitySteward()
        return NEED_REVIEW

    if event.version < latestAcceptedVersion(person):
        return STALE_EVENT

    newSubject = resolveVerifiedIdpBSubject(person)
    oldSubject = lookupIdpASubject(person)
    appAccounts = lookupVerifiedAppLinks(person)

    desired = calculateCurrentJmlAndAccessPolicy(
        person, event.effectiveTime, approvedExceptions
    )

    if looksLikeUnexpectedMassDisableOrGrant(desired):
        holdForApproval(event)
        return HOLD

    updateOnlyAuthorizedIdpAndProvisioningWriters(
        person, newSubject, appAccounts, desired
    )
    reconcileSessionsTokensAndAppEntitlements(person, desired)
    audit(event.eventId, oldSubject, newSubject, desired)
~~~

Đây là **pseudocode**, không phải triển khai production. Hệ thống thật cần chống race condition, xác thực event, transaction/outbox hoặc queue phù hợp, xử lý thất bại từng phần, retry/backoff, versioning và kiểm tra quyền của service account chạy connector.

**Đừng phụ thuộc vào trình tự nhận event.** Ví dụ, sự kiện mover phát sớm nhưng tới muộn không được ghi đè leaver đã có hiệu lực. Với sự kiện nhân sự bị sửa hồi tố, thực thi trạng thái kỳ vọng mới nhất phải theo luật nghiệp vụ và audit.

## 16. Cutover, session và kế hoạch rollback

### 16.1. Điều kiện chuyển tiếp (go/no-go)

Cần đạt các điều kiện được đo trước:

- Mapping coverage đủ theo phạm vi, không có liên kết mơ hồ tự động cấp quyền.
- Ứng dụng trọng yếu đã test SAML/OIDC, MFA, SCIM, JML, app-local role và actual access.
- Người dùng quan trọng đã có phương án recovery/MFA; admin và break-glass đã diễn tập.
- Sự khác biệt giữa issuer/subject, session/token, signing key đã được giải quyết hoặc có biện pháp được duyệt.
- Có dashboard, on-call, ngưỡng rollback, liên lạc nội bộ, bằng chứng kiểm thử và owner phê duyệt.
- Đã thử khả năng khôi phục trust/config và xử lý JML phát sinh giữa hai thời điểm.

### 16.2. Các sự cố kích hoạt tạm dừng

Có thể quy định pause khi:

- Account linking sai người hoặc xuất hiện duplicate được cấp quyền.
- SSO thất bại tăng bất thường ở ứng dụng quan trọng.
- MFA policy vô tình bị hạ hoặc admin bị khóa ngoài không có đường khẩn cấp.
- User đã nghỉ vẫn đăng nhập được qua IdP-A hoặc IdP-B.
- Access drift, direct grant hoặc role đặc quyền tăng bất thường.
- Connector tạo/xóa hàng loạt do source thiếu dữ liệu hoặc SCIM sai mapping.

Ngưỡng cụ thể dựa trên baseline và rủi ro của tổ chức; không lấy con số minh họa làm tiêu chuẩn cố định.

### 16.3. Rollback có điều kiện

Đổi cấu hình application trust trở về IdP-A **không đủ** nếu đã tạo account/role/phiên mới hoặc có JML sau cutover.

1. Pause các writer liên quan; giữ log, snapshot, mapping version và event backlog.
2. Xác định các joiner/mover/leaver, account link và quyền phát sinh kể từ mốc chuyển.
3. Chọn lại IdP/trust và provisioning writer có thẩm quyền; xác định phương pháp khôi phục session/MFA phù hợp.
4. Áp **trạng thái nhân sự và quyền hiện hành** khi replay; không phục hồi quyền của leaver chỉ vì snapshot cũ còn active.
5. Kiểm thử login qua trust được khôi phục, revoke/logout, quyền ứng dụng, group, local account và workload token.
6. Ghi incident, nguyên nhân, khắc phục và quyết định có thử cutover tiếp.

Một số thay đổi như revoke credential, đổi signing key, xóa tài khoản ứng dụng hay chuyển profile tenant có thể không đảo ngược hoàn toàn. Cần làm rõ giới hạn trong runbook và lựa chọn thao tác có thể phục hồi trong pilot.

## 17. Kiểm toán, đối soát và các chỉ số vận hành

### 17.1. Audit trail xuyên hệ thống

Mỗi sự kiện đáng kể nên truy được:

| Dữ liệu audit | Mục đích |
|---|---|
| Correlation ID / event ID | Nối HR source → IAM → IdP → SP/SCIM |
| Canonical person ID | Gắn hành động với đúng chủ thể |
| Old issuer/subject và new issuer/subject | Giải thích chuyển đổi định danh federation |
| Application account ID / entitlement | Đối chiếu đúng account và quyền thực tế |
| Rule/policy version, before/after | Xác định logic và tác động |
| Actor/approver và ticket/exception | Truy vết trách nhiệm và lý do thay đổi |
| Timestamp, target, outcome/retry | Điều tra độ trễ, lỗi hoặc sai thứ tự |

Không ghi raw access token, refresh token, private key, password hoặc dữ liệu HR nhạy cảm không cần thiết vào log. Bảng liên kết định danh cần phân quyền, mã hóa, retention và cơ chế kiểm toán truy cập.

### 17.2. Desired state và actual state

**Desired state:** chủ thể nào được hoạt động, role nào hợp lệ theo HR/contractor source, IAM/IGA policy và exception được duyệt.  
**Actual state:** ai đang đăng nhập được tại từng IdP, token/phiên nào còn hiệu lực, account/role nào thực sự tồn tại tại SP và resource server.

Đối soát cần chỉ ra:

- User đã chuyển nhưng SP vẫn tin IdP-A và cho phép đăng nhập.
- IdP-B có user mới nhưng app account cũ chưa link, dẫn tới duplicate.
- Group claim đã đổi nhưng app-local role không được thu hồi.
- SCIM disable thành công nhưng session/API key vẫn hợp lệ.
- Service account hoặc guest không có owner/expiry.
- Một IdP hoặc một directory khác vẫn là đường truy cập ngoài phạm vi kiểm thử.

### 17.3. KPI

| Chỉ số | Cách hiểu |
|---|---|
| **Verified mapping coverage** | Số user trong phạm vi có mapping xác minh / tổng user |
| **Account duplicate rate** | Số identity có nhiều account ngoài chủ đích / tổng identity |
| **SSO success/failure rate** | Theo ứng dụng, cohort, giao thức, browser/device, loại lỗi |
| **MFA enrollment/recovery success** | Mức độ hoàn tất phương thức xác thực và tự phục hồi |
| **Provisioning success/latency** | Tỷ lệ và độ trễ user/group create/update/disable |
| **Leaver revocation latency** | Từ effective time tới khi các đường truy cập trong phạm vi bị thu hồi |
| **Entitlement drift** | Quyền thực tế khác quyền đã phê duyệt |
| **Orphan account / credential count** | Account và credential không còn owner hợp lệ |
| **Session/token revocation coverage** | Các hệ có khả năng và đã kiểm chứng việc thu hồi |
| **Unresolved exceptions** | Số mapping, ứng dụng hoặc quyền đang chờ owner giải quyết |

Một KPI độc lập không mô tả đầy đủ thành công. Tỷ lệ SSO 99% vẫn có thể che một app quan trọng đang cấp quyền sai người.

## 18. Case study: chuyển IdP-A sang IdP-B cho 1.200 nhân viên

Giả sử doanh nghiệp có **1.200 nhân viên**, **90 nhà thầu**, **40 ứng dụng**. IdP-A làm SSO, HRIS là nguồn trạng thái nhân sự, IAM/IGA chạy JML và phần lớn ứng dụng có provisioning qua SCIM/API.

### Bước 1 — Khảo sát

Nhóm xác định 24 ứng dụng dùng SAML, 12 dùng OIDC, 4 ứng dụng cũ dùng LDAP hoặc local login. Hai ứng dụng SAML liên kết user theo NameID persistent, ba ứng dụng OIDC dùng issuer + sub và nhiều ứng dụng có direct grant. Một số quản trị viên dùng token CLI và phương thức MFA chuyên biệt.

Nhóm không coi bốn ứng dụng ngoài SSO là “đã xong” sau khi thay IdP: chúng phải tiếp tục được điều phối leaver qua kênh riêng.

### Bước 2 — Liên kết định danh

Canonical person ID được giữ từ identity registry. Bảng mapping xác minh old issuer/subject và new issuer/subject. Ví dụ minh họa:

- 1.185 nhân viên có mapping tự động từ nguồn đã xác minh.
- 12 hồ sơ cần rà soát vì đổi tên hoặc nguồn dữ liệu không nhất quán.
- 3 hồ sơ mơ hồ được cách ly, chưa liên kết hoặc cho phép tự động tạo account.

Các con số chỉ dùng cho bài tập tình huống; không phải benchmark hay ngưỡng mục tiêu thực tế. Sau khi được owner xác minh, account tại các ứng dụng được pre-link theo capability của từng SP.

### Bước 3 — Thử JML và giao thức

- **Joiner:** Nhân viên mới có ngày bắt đầu tương lai được chuẩn bị account nhưng chỉ kích hoạt theo chính sách; đăng ký MFA qua quy trình xác minh an toàn.
- **Mover:** Nhân viên chuyển từ Kế toán sang Mua hàng, role mới được cấp đúng phê duyệt; role Kế toán cũ và direct grant được đối soát và thu hồi.
- **Leaver:** Nhà thầu hết hạn bị chặn trên IdP-B, IdP-A còn tồn tại trong coexistence và các ứng dụng/API liên quan; token/phiên được xử lý theo SLA từng hệ.
- **SSO:** Một ứng dụng OIDC từng dùng sub làm user key xuất hiện duplicate trong pilot. Nhóm pre-link vào internal app user ID trước khi mở rộng.
- **MFA:** Nhóm có người dùng không thể dùng thiết bị cũ, vì vậy cần quy trình recovery đã được bảo mật phê duyệt.
- **Automation:** Bot kết nối CRM được chuyển client/trust và rotate credential, xác nhận job chạy dưới quyền tối thiểu.

### Bước 4 — Cutover và nghiệm thu

Mỗi cohort chỉ được chuyển khi đăng nhập, mapping, entitlement, JML và audit đều đạt tiêu chí. Sau chuyển đổi, nhóm chạy reconciliation tìm access drift, chốt owner xử lý ngoại lệ, gỡ trust/connector IdP-A theo kế hoạch và giữ dữ liệu phục vụ điều tra.

**Bài học:** Di trú IdP là thay một quan hệ tin cậy xuyên nhiều ứng dụng. Thành công là giữ **đúng chủ thể, đúng chính sách xác thực, đúng quyền và đúng vòng đời**, chứ không chỉ thay trang đăng nhập.

## 19. Bộ kiểm thử nghiệm thu

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | Người dùng giữ email, đổi OIDC issuer/sub | Vào đúng internal app account; không tạo duplicate |
| T02 | Hai identity cùng email hoặc email tái sử dụng | Không tự merge; quarantine để xác minh |
| T03 | SAML NameID/issuer đổi | SP liên kết account đúng, không mất lịch sử/quyền |
| T04 | OIDC token sai issuer/audience hoặc chữ ký | RP từ chối |
| T05 | OIDC auth flow hợp lệ với state/nonce/PKCE áp dụng | Đăng nhập thành công, chống replay/code injection |
| T06 | SAML assertion hết hạn, sai recipient/audience hoặc replay | SP từ chối và audit |
| T07 | Rotate certificate/JWKS | Ứng dụng hoạt động với trust hợp lệ, loại khóa cũ đúng lộ trình |
| T08 | User chưa đăng ký MFA ở IdP-B | Có enrollment/recovery an toàn, không bypass trái chính sách |
| T09 | Admin gặp lỗi IdP/federation | Break-glass hoạt động và được giám sát |
| T10 | Joiner có effective date trong tương lai | Account/SSO/quyền hoạt động đúng thời điểm |
| T11 | Mover đổi phòng ban và group claim | Cấp đúng role mới, thu hồi quyền cũ, tuân SoD |
| T12 | Leaver trong coexistence | Không đăng nhập qua IdP-A/B và thu hồi quyền/token trong SLA |
| T13 | SP có direct grant, local login và API key | Reconciliation phát hiện và xử lý quyền tồn dư |
| T14 | SCIM event lặp/đến sai thứ tự | Không tạo duplicate hoặc hồi sinh user |
| T15 | Nguồn HRIS xuất batch rỗng do lỗi | Không bulk deprovision, có cảnh báo và kiểm tra |
| T16 | Guest/contractor hết hạn | Quyền hết hạn theo nguồn có thẩm quyền, không lẫn nội bộ |
| T17 | Workload identity chuyển client/issuer | Token nhận đúng audience/quyền, credential cũ được xử lý |
| T18 | Rollback sau sự kiện JML mới | Trạng thái hiện hành được áp dụng, leaver không được mở lại |
| T19 | Thiết bị/mobile/VPN sau cutover | Flow login/logout/MFA hoạt động theo policy và app hỗ trợ |
| T20 | Một app không hỗ trợ dual trust | Chuyển theo runbook, đã diễn tập phục hồi và xác định giới hạn |

**Gợi ý nghiệm thu:** ghi kết quả theo application, cohort, môi trường, thời điểm, người kiểm tra, expected/actual result, log ID, owner và ngoại lệ còn mở. Không chỉ đánh dấu “PASS” bằng một tài khoản thử duy nhất.

## 20. Checklist bàn giao trước và sau go-live

### Trước cutover

- [ ] Có inventory app/trust, nguồn identity, account liên kết, group/role và owner đầy đủ.
- [ ] Mapping canonical ID ↔ old/new subject/NameID đã xác minh; ca mơ hồ được cách ly.
- [ ] OIDC issuer/audience/redirect/JWKS và SAML entityID/ACS/certificate/NameID đã test.
- [ ] MFA, policy đăng nhập, recovery, admin break-glass và thiết bị đã có phương án.
- [ ] IAM/IGA, JML, SCIM/API writer, role/group claims và direct grants được đối chiếu.
- [ ] Service account, workload token, guest federation và ứng dụng legacy có owner.
- [ ] Có snapshot trust/mapping, audit, dashboard, no-go thresholds, rollback rehearsal.
- [ ] Có người duyệt nghiệp vụ, an ninh, IAM và owner các ứng dụng quan trọng.

### Sau cutover

- [ ] Đăng nhập hợp lệ và từ chối sai người đều được thử ở các ứng dụng trọng yếu.
- [ ] Account, entitlement và session thực tế đã đối soát với desired state.
- [ ] Joiner, Mover, Leaver và nhà thầu được xác minh hoạt động xuyên các hệ.
- [ ] Duplicate, orphan, quyền trực tiếp, token cũ và ngoại lệ có owner/hạn xử lý.
- [ ] Đã xác minh điều kiện dừng IdP-A, thu hồi trust/secret/credential cũ đúng kế hoạch.
- [ ] Mapping và audit được bảo vệ, lưu giữ theo chính sách; lessons learned được ghi nhận.

## 21. Sai lầm thường gặp

**Chỉ thay login URL:** không xử lý issuer, subject và account linking; app tạo user mới hoặc mất dữ liệu. Cần kiểm chứng khóa nhận diện tại từng SP/RP.

**Tin email làm khóa định danh duy nhất:** tạo nguy cơ chiếm tài khoản khi email bị đổi/tái sử dụng. Dùng mapping có xác minh và cơ chế liên kết được hỗ trợ.

**Bật JIT provisioning trước khi pre-link:** một người có hai app account và quyền sai. Cần quarantine ca chưa khớp và hạn chế auto-create.

**Chuyển MFA bằng cách tắt bắt buộc:** tạo cửa sổ truy cập yếu. Dùng enrollment/recovery có bảo vệ và ngoại lệ ngắn hạn có phê duyệt nếu thực sự cần.

**Xóa IdP-A trước khi kiểm tra đường truy cập:** ứng dụng legacy, service principal, session/token hoặc trust đối tác có thể bị bỏ sót. Inventory và retire theo điều kiện xác nhận thực tế.

**Coi IdP disable là đủ cho leaver:** các phiên, token và app-local account có thể tồn tại. Kiểm tra revoke và reconciliation tại đích.

**Để hai SCIM writer cùng sửa một account:** tạo đảo trạng thái, cấp/thu hồi quyền liên tục. Quy định authority và thứ tự event.

**Rollback mù về snapshot cũ:** vô tình cấp lại quyền đã bị thu hồi hợp lệ. Khôi phục dựa trên trạng thái JML hiện hành và kiểm thử tất cả đường truy cập.

## 22. Câu hỏi tự kiểm tra

1. Thay IdP nhưng không thay HRIS có nghĩa là nguồn nào vẫn có thẩm quyền xác nhận leaver?
2. Vì sao issuer + sub quan trọng hơn email khi liên kết tài khoản OIDC? Khi nào sub còn phụ thuộc client?
3. SAML NameID thay đổi có thể làm ứng dụng nhận diện người dùng khác như thế nào?
4. Tại sao đổi signing key chưa chắc là di trú account, nhưng đổi issuer/subject thường đòi hỏi mapping?
5. Một ứng dụng cho đăng nhập SSO thành công nhưng vẫn giữ direct admin role cũ: phải xử lý gì?
6. Nếu IdP-A còn được một ứng dụng chấp nhận trong coexistence, điều gì cần kiểm thử khi nhân viên nghỉ việc?
7. Vì sao không thể mặc định sao chép trạng thái MFA hoặc passkey sang IdP mới?
8. Nếu rollback sau một sự kiện mover và leaver, làm sao tránh phát lại quyền cũ?
9. Quy trình bảo vệ service account và workload OAuth khác gì với người dùng tương tác?
10. Những KPI nào kết hợp lại mới đủ chứng minh cuộc di trú đạt yêu cầu?

**Gợi ý trả lời:** phân biệt nguồn danh tính và IdP; ghi rõ phạm vi của từng khóa; kiểm tra actual entitlement bên cạnh authentication; dựa vào mapping đã xác minh, policy JML hiện hành, audit và recovery được thử nghiệm.

## 23. Thuật ngữ và nguồn tham khảo

| Thuật ngữ | Diễn giải |
|---|---|
| **IdP / SP / RP** | Nhà cung cấp danh tính / SAML Service Provider / OIDC Relying Party |
| **SAML** | Giao thức liên hợp danh tính bằng assertion XML |
| **OIDC** | Lớp xác thực danh tính xây trên OAuth 2.0 |
| **OAuth 2.0** | Khung ủy quyền truy cập tài nguyên |
| **Issuer / subject / audience** | Bên phát hành / chủ thể / bên nhận token |
| **JWKS** | Tập khóa công khai JSON dùng phục vụ xác minh chữ ký |
| **NameID** | Giá trị định danh chủ thể trong SAML |
| **ACS / redirect URI** | Endpoint nhận SAML assertion / callback OIDC |
| **MFA / FIDO2 / passkey** | Xác thực nhiều yếu tố / phương thức xác thực bằng khóa công khai |
| **SCIM / JIT** | Giao thức provisioning / tạo user khi đăng nhập lần đầu |
| **JML** | Joiner–Mover–Leaver, vào–chuyển–rời tổ chức |
| **RBAC / ABAC / SoD** | Kiểm soát theo vai trò / thuộc tính / phân tách nhiệm vụ |
| **Coexistence / cutover / rollback** | Đồng tồn tại / chuyển chính thức / khôi phục có kiểm soát |

Tài liệu nền tảng nên tra cứu khi triển khai:

- **OpenID Connect Core 1.0**, Discovery và các tài liệu liên quan đến issuer, subject, ID token, signing keys, client registration.
- **OAuth 2.0 Authorization Framework (RFC 6749)**, **PKCE (RFC 7636)** và tài liệu thực hành bảo mật OAuth hiện hành.
- **SAML 2.0 Core, Bindings và Metadata** của OASIS.
- **SCIM Core Schema (RFC 7643)** và **SCIM Protocol (RFC 7644)**.
- **NIST SP 800-63** và tài liệu chính thức của nhà cung cấp IdP/SP về assurance, MFA, recovery, account linking, federation, SCIM, session/token revocation.
- Tài liệu vận hành của từng ứng dụng đang dùng: có hỗ trợ dual trust, pre-link, subject migration, JIT behavior, signing certificate rotation và backup/restore không.

**Điểm kiểm tra cuối cùng:** Sau khi thay IdP, mỗi người vẫn phải được nhận diện là cùng một chủ thể đã xác minh; chính sách xác thực được thực thi; chỉ quyền hợp lệ còn tồn tại; các sự kiện Joiner–Mover–Leaver vẫn hoạt động; và mọi thay đổi đều có bằng chứng để đối soát, điều tra và khôi phục.
