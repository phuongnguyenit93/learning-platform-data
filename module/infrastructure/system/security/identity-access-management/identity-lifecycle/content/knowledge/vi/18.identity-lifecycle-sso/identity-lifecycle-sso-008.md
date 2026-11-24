# SSO error: nhận diện, chẩn đoán và xử lý lỗi đăng nhập một lần trong vòng đời danh tính

Nhân viên đã được tạo tài khoản tại Identity Provider (**IdP**), nhưng khi mở ứng dụng nghiệp vụ lại thấy thông báo *“Single Sign-On failed”*. Một trường hợp khác, IdP báo đăng nhập thành công, song ứng dụng vẫn trả về **403 Forbidden**. Có khi nhân viên đổi phòng ban và đột ngột mất quyền truy cập; cũng có khi người đã nghỉ việc vẫn vào được ứng dụng nhờ phiên cũ. Những hiện tượng này thường được người dùng gọi chung là **SSO error**, nhưng nguyên nhân thực tế có thể nằm ở các giai đoạn rất khác nhau.

**SSO error** là cách gọi tổng quát cho lỗi hoặc kết quả không mong muốn trên đường đăng nhập một lần (*Single Sign-On*). Việc phân loại chính xác cần phân biệt **xác thực tại IdP**, **trao đổi bằng chứng qua SAML/OIDC**, **liên kết tài khoản tại ứng dụng**, **cấp phát tài khoản**, **phân quyền** và **quản lý phiên**.

Bài học thuộc chương **SSO**, mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun bao quát quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi thay đổi vai trò. Nội dung liên hệ các thành phần **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán**, với mục tiêu không chỉ giúp người dùng đăng nhập được mà còn **ngăn truy cập trái phép hoặc quyền truy cập tồn dư**.

Sau bài học, người học có thể:

- Phân biệt lỗi **authentication**, **federation protocol**, **account provisioning**, **authorization**, **session** và **availability** trên luồng SSO.
- Đọc những tín hiệu chính trong SAML 2.0 và OpenID Connect (OIDC) mà không làm lộ assertion, token, cookie hoặc credential.
- Thiết kế quy trình kiểm tra **issuer, audience, chữ ký, endpoint, state/nonce, thời gian, tài khoản và quyền** đúng trình tự.
- Giải thích tại sao Joiner, Mover hoặc Leaver có thể tạo ra lỗi SSO hợp lệ, hoặc tạo ra tình trạng nguy hiểm khi phiên cũ vẫn truy cập được.
- Xây dựng runbook hỗ trợ người dùng, xử lý sự cố, đối soát trạng thái và lưu bằng chứng kiểm toán.

## 1. SSO hoạt động thế nào trước khi xảy ra lỗi?

**Single Sign-On** cho phép người dùng tận dụng phiên xác thực tại một hệ thống danh tính để đăng nhập vào nhiều ứng dụng tích hợp. Trong mô hình doanh nghiệp, **IdP** xác thực người dùng, còn **ứng dụng** sử dụng thông tin từ IdP để xác định tài khoản cục bộ và quyết định quyền.

Các vai trò điển hình:

| Thành phần | Vai trò | Điều cần nhớ khi có lỗi |
| --- | --- | --- |
| **HRIS / nguồn danh tính** | Xác nhận nhân viên, loại quan hệ, ngày bắt đầu/kết thúc, bộ phận và quản lý. | Sai dữ liệu nguồn có thể khiến IAM chuẩn bị/kích hoạt/thu hồi tài khoản sai. |
| **IAM/IGA** | Liên kết danh tính, điều phối Joiner–Mover–Leaver, quy tắc cấp quyền và phê duyệt. | Hồ sơ đã tạo không đồng nghĩa ứng dụng đã có đúng tài khoản/quyền. |
| **IdP** | Xác thực, MFA, chính sách điều kiện truy cập, phát hành thông tin đăng nhập liên thông. | Đăng nhập IdP thành công không chứng minh ứng dụng đã cho phép truy cập. |
| **SP / RP** | Ứng dụng nhận bằng chứng danh tính; trong SAML là **Service Provider**, OIDC là **Relying Party**. | Phải xác minh giao thức, ánh xạ chủ thể và quyền tại ứng dụng. |
| **SCIM / provisioning connector** | Tạo, cập nhật, vô hiệu hóa User/Group ở ứng dụng hỗ trợ. | SCIM có thể lỗi độc lập với việc IdP phát hành assertion/token đúng. |
| **Authorization engine** | Kiểm tra RBAC/ABAC, nhóm, entitlement, scope và tài nguyên. | HTTP 403 thường là lớp quyền, không phải lúc nào là lỗi mật khẩu. |
| **Session/token services** | Quản lý phiên IdP, phiên ứng dụng và token liên quan. | Một phiên cũ có thể còn hiệu lực sau thay đổi quyền nếu ứng dụng chưa kiểm tra lại. |

### 1.1. Luồng logic

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant APP as Ứng dụng SP/RP
    participant IDP as IdP / OP
    participant IAM as IAM / HRIS / policy
    U->>APP: Mở ứng dụng
    APP-->>U: Bắt đầu luồng SAML/OIDC
    U->>IDP: Yêu cầu xác thực
    IDP->>IAM: Kiểm tra trạng thái, chính sách, MFA
    IAM-->>IDP: Điều kiện và kết quả phù hợp
    IDP-->>APP: Kết quả federation theo giao thức
    APP->>APP: Xác minh issuer, chữ ký, audience, request binding
    APP->>APP: Liên kết account và kiểm tra RBAC/ABAC
    APP-->>U: Tạo phiên / hiển thị lỗi / từ chối quyền
~~~

Sơ đồ thể hiện **các bước logic**, không phải toàn bộ HTTP messages. Với **OIDC Authorization Code Flow**, trình duyệt thường nhận authorization code qua redirect và RP đổi code tại token endpoint; **không phải** IdP luôn gửi ID token trực tiếp qua front channel như một SAML response.

Chỉ cần một bước thất bại, người dùng có thể thấy *“SSO error”*. Vì vậy, chẩn đoán nên bắt đầu bằng câu hỏi: **lỗi xuất hiện ở bước nào và bên nào là bên đã từ chối?**

## 2. Phân loại SSO error theo vị trí lỗi

| Nhóm lỗi | Biểu hiện thường gặp | Hệ thống ưu tiên kiểm tra |
| --- | --- | --- |
| **Danh tính/Joiner chưa sẵn sàng** | Tài khoản chưa tồn tại, chưa tới ngày bắt đầu hoặc chưa được kích hoạt. | HRIS, IAM/IGA, IdP và lịch kích hoạt. |
| **Authentication/MFA** | Sai credential, thiếu phương thức MFA, account locked, risk policy denied. | Log xác thực và chính sách IdP. |
| **Federation/trust configuration** | Issuer, audience, redirect URI/ACS, chữ ký, chứng chỉ hoặc metadata không khớp. | Cấu hình IdP và SP/RP, lịch thay đổi trust. |
| **Protocol/request validation** | State/nonce sai, authorization code hết hạn, response không phù hợp request. | RP/SP, thư viện OIDC/SAML, correlation ID. |
| **Provisioning/account mapping** | IdP xác thực thành công nhưng ứng dụng không có User hợp lệ hoặc liên kết sai. | SCIM connector, mapping ID và trạng thái tài khoản đích. |
| **Authorization** | Người dùng vào được nhưng gặp 403, không thấy dữ liệu hoặc bị “not assigned”. | RBAC/ABAC, nhóm, claim và owner ứng dụng. |
| **Session/cookie/browser** | Redirect loop, phiên IdP còn nhưng phiên ứng dụng lỗi, cookie không lưu được. | Trình duyệt, reverse proxy, session store và cấu hình cookie. |
| **Availability/integration** | Timeout, 5xx, endpoint lỗi, không đổi được authorization code. | IdP, RP/SP, DNS/TLS, network và tình trạng dịch vụ. |
| **Leaver/revocation** | Đăng nhập bị từ chối sau nghỉ việc, hoặc nguy hiểm hơn là vẫn truy cập bằng phiên cũ. | HRIS, IdP, ứng dụng cục bộ, token/session và SCIM. |

**Không nên chữa mọi lỗi bằng cách reset mật khẩu hoặc tắt MFA.** Nếu lỗi do thiếu quyền ứng dụng, reset credential không giải quyết nguyên nhân; nếu lỗi do audience/chữ ký, bỏ qua kiểm tra có thể biến một cấu hình lỗi thành lỗ hổng bảo mật.

### 2.1. Những thông báo giống nhau nhưng ý nghĩa khác

- **“Invalid credentials”**: thường liên quan credential hoặc xác thực ở nơi trả lỗi, nhưng cũng có thể được ứng dụng dùng như thông báo chung.
- **“Access denied”**: có thể do chính sách IdP, người dùng từ chối consent, tài khoản ứng dụng bị khóa hoặc quyền tài nguyên bị từ chối.
- **“User not found”**: có thể là IdP không biết danh tính, hoặc ứng dụng đã nhận token hợp lệ nhưng không ánh xạ được tài khoản đích.
- **“SAML response invalid”**: cần xem kiểm issuer, chữ ký, recipient, audience, subject confirmation và thời gian; không tự giả định chỉ do chứng chỉ hết hạn.
- **“Invalid grant”**: thường xuất hiện ở OAuth token endpoint với các tình huống như code không hợp lệ/hết hạn/đã sử dụng hoặc PKCE không đúng, tùy ngữ cảnh.
- **“Too many redirects”**: có thể do session, cookie, cấu hình URL hoặc ứng dụng lặp yêu cầu xác thực; không tự quy kết là IdP sập.

Thông báo hiển thị cho người dùng nên **ngắn gọn, không tiết lộ thông tin nhạy cảm**; log kỹ thuật bảo vệ tốt mới chứa mã lỗi, phiên liên quan và chi tiết cần thiết.

## 3. SSO error trong SAML 2.0

Ở SAML, **IdP** phát hành **SAML assertion/response** để **SP** xác minh. Một chứng chỉ ký đúng nhưng đối tượng, thời gian hoặc điểm nhận sai vẫn phải dẫn tới từ chối.

### 3.1. Những trường và ràng buộc quan trọng

| Thành phần SAML | Cần kiểm tra | Lỗi thường thấy |
| --- | --- | --- |
| **IdP Entity ID / Issuer** | Assertion/response do đúng IdP đã thiết lập trust phát hành. | Tin nhầm issuer hoặc tenant. |
| **SP Entity ID / AudienceRestriction** | Assertion dành cho đúng SP. | Cấu hình audience ở hai phía khác nhau. |
| **ACS / Destination / Recipient** | Response được chuyển đến endpoint đích hợp lệ, phù hợp subject confirmation. | Sai ACS URL sau đổi domain/reverse proxy. |
| **Signature và signing key** | Kiểm chữ ký trên đúng đối tượng theo cấu hình và profile. | Xoay cert chưa đồng bộ, khóa không thuộc trust, sai quy tắc chữ ký. |
| **NotBefore / NotOnOrAfter** | Assertion và điều kiện subject confirmation còn hiệu lực. | Lệch đồng hồ hoặc assertion hết hạn. |
| **InResponseTo** | Liên kết assertion/response với AuthnRequest khi yêu cầu. | Yêu cầu đã hết phiên, response bị lặp hoặc không khớp. |
| **NameID / Attributes** | Liên kết đúng người/tài khoản, hiểu đúng format và nguồn thuộc tính. | Email đổi, NameID không ổn định, mapping sai. |
| **Status / Substatus** | Biết IdP đã từ chối yêu cầu hay SP không kiểm chứng được phản hồi. | Nhầm lỗi xác thực IdP với lỗi validation tại SP. |

SAML có các trạng thái tổng quát như \`Success\`, \`Requester\`, \`Responder\` và một số mã con phục vụ nguyên nhân cụ thể. **Không phải mọi lỗi kiểm chữ ký hoặc audience đều có status code SAML từ IdP**: SP có thể tự từ chối response đã nhận và chỉ ghi lỗi trong log của mình.

### 3.2. Một trường hợp xoay chứng chỉ ký

**Tình huống:** IdP thay khóa ký nhưng một SP vẫn dùng certificate cũ.

1. Người dùng xác thực ở IdP thành công.
2. IdP phát SAML response được ký bằng khóa mới.
3. SP không tìm được khóa phù hợp trong trust store và từ chối response.
4. Người dùng thấy SSO error dù mật khẩu và MFA hoàn toàn hợp lệ.

Cách xử lý là kiểm **thay đổi metadata, signing key được phép, lịch rollover và trạng thái ở từng SP**, không phải tắt xác minh chữ ký để người dùng vào được. Nếu thay khóa do lộ bí mật, có thể phải **ngừng tin khóa cũ ngay theo kế hoạch ứng cứu**, không kéo dài chấp nhận vì tương thích.

### 3.3. NameID và tài khoản đích

SP có thể kiểm SAML response hợp lệ nhưng không tìm thấy user tương ứng. Ví dụ HRIS đổi họ tên hoặc email của nhân viên trong giai đoạn Mover; nếu SP ánh xạ bằng email, ứng dụng có thể coi đây là người mới.

Nên dùng **định danh bền vững gắn với issuer**, có bảng liên kết tài khoản được quản trị. Không nên tự nối người dùng mới với tài khoản cũ chỉ vì trùng displayName; cần xử lý ambiguity và kiểm chứng đúng chủ thể.

## 4. SSO error trong OpenID Connect (OIDC)

OIDC cho phép **Relying Party (RP)** xác thực người dùng thông qua **OpenID Provider (OP)**. Trong luồng Authorization Code, RP gửi yêu cầu authorization, nhận code, đổi lấy token và xác minh **ID token**.

### 4.1. Nhóm lỗi theo endpoint

| Giai đoạn | Lỗi/tín hiệu thường gặp | Cách tiếp cận |
| --- | --- | --- |
| **Authorization endpoint** | \`invalid_request\`, \`unauthorized_client\`, \`access_denied\`, \`invalid_scope\`, \`server_error\`, \`temporarily_unavailable\`. | Xem tham số request, client, policy, sự cố IdP và ngữ cảnh người dùng. |
| **OIDC authentication interaction** | \`login_required\`, \`interaction_required\`, \`consent_required\`, \`account_selection_required\` trong tình huống tương ứng, nhất là yêu cầu không tương tác. | Hiểu rằng yêu cầu xác thực tương tác có thể cần thực hiện lại, không nhất thiết là credential sai. |
| **Token endpoint** | \`invalid_grant\`, \`invalid_client\`, \`invalid_request\` và những lỗi OAuth hợp lệ khác. | Kiểm authorization code, PKCE, client authentication, redirect URI và thời hạn. |
| **ID token validation tại RP** | Issuer, audience, signature, \`nonce\`, thời gian hoặc thuật toán không hợp lệ. | Xem chi tiết validation nội bộ; không mặc định OP trả OAuth error tương ứng. |
| **Sau xác thực** | Không tìm thấy local account, role/claim không phù hợp, tài khoản bị disabled. | Điều tra provisioning/authorization, không sửa giao thức nếu token hợp lệ. |

**Các chuỗi lỗi trên là ví dụ theo ngữ cảnh OIDC/OAuth, không phải mã thông báo chung của mọi IdP.** Một số sản phẩm hiển thị mã riêng hoặc che thông tin vì lý do bảo mật. Chẳng hạn “redirect URI mismatch” thường là **mô tả chẩn đoán của provider**, không phải lúc nào là mã lỗi chuẩn riêng tên \`invalid_redirect_uri\`.

### 4.2. Những kiểm tra bắt buộc không được bỏ qua

| Thuộc tính/cơ chế | Cần bảo đảm |
| --- | --- |
| **Issuer \`iss\`** | ID token được phát hành bởi đúng OP đã cấu hình. |
| **Audience \`aud\`** | Token dành cho đúng RP/client; xét thêm \`azp\` theo trường hợp cần. |
| **Signature và \`alg\`** | Dùng thuật toán được cho phép và khóa của issuer tin cậy; không tùy tiện lấy khóa từ tham số token. |
| **\`exp\`, \`iat\`, các mốc thời gian liên quan** | Token còn hiệu lực, đồng hồ và clock skew ở mức hợp lý. |
| **\`state\`** | Callback liên kết với đúng phiên authorization đang mở, phòng CSRF/tráo luồng. |
| **\`nonce\`** | Khi được sử dụng/yêu cầu, phải khớp nonce gắn với request ban đầu. |
| **Authorization Code** | Đúng client, redirect URI, một lần sử dụng, chưa hết hạn. |
| **PKCE** | \`code_verifier\` khớp \`code_challenge\` của luồng đã khởi tạo. |
| **Redirect URI** | Khớp URI đăng ký với OP theo quy tắc giao thức/provider; tránh redirect mở. |
| **Subject \`sub\`** | Ánh xạ người dùng từ **\`iss\` + \`sub\`**, không chỉ email. |

Ví dụ tình huống:

~~~text
RP khởi tạo đăng nhập OIDC:
    state = tham chiếu phiên giao dịch
    nonce = tham chiếu xác thực ID token
    PKCE = challenge ràng buộc với code verifier

RP nhận callback:
    Nếu state không khớp -> từ chối và điều tra phiên/cookie
    Nếu code không đổi được -> xem token endpoint và tương quan request
    Nếu ID token không đạt validation -> từ chối, không "bỏ qua tạm"
    Nếu token hợp lệ nhưng local account bị khóa -> từ chối theo vòng đời IAM
    Nếu account hợp lệ nhưng thiếu quyền -> xử lý authorization
~~~

Đây là **giả mã chẩn đoán**, không phải mã thực thi giao thức. Nên dùng thư viện OIDC được duy trì và cấu hình validation chuẩn thay vì tự xây bộ xác thực token.

### 4.3. Phân biệt ID token và access token

- **ID token** xác thực sự kiện người dùng đăng nhập đối với RP nhận token; không dùng nó thay access token khi gọi API.
- **Access token** dành cho resource server/API, phải có audience, scope/quyền và cơ chế validation phù hợp tại API đó.
- **Refresh token** có thể giúp xin access token mới mà không cần nhập lại credential; phải quản lý thu hồi theo chính sách.

Nếu ứng dụng đưa ID token cho API có audience khác, API phải từ chối. Đó có thể là **hành vi bảo mật đúng**, không nên “sửa” bằng cách bỏ kiểm audience.

## 5. Lỗi liên quan cookie, session và redirect

SSO thường có ít nhất hai lớp trạng thái:

1. **Phiên IdP**: chứng minh người dùng đã xác thực tại IdP.
2. **Phiên ứng dụng SP/RP**: cho phép người dùng sử dụng ứng dụng sau khi nhận và xác minh federation response.

Hai phiên có thể có thời hạn và cơ chế hủy khác nhau. Trường hợp IdP còn phiên nhưng ứng dụng mất cookie phiên có thể tạo **vòng lặp redirect**, dù IdP vẫn hoạt động.

### 5.1. Những nguồn gây lỗi phổ biến

| Tình huống | Biểu hiện | Kiểm tra an toàn |
| --- | --- | --- |
| **Cookie ứng dụng không được lưu/gửi lại** | Liên tục chuyển đến IdP và quay lại ứng dụng. | Thuộc tính \`Secure\`, \`HttpOnly\`, \`SameSite\`, domain/path, HTTPS và luồng redirect phù hợp. |
| **Reverse proxy ghi sai scheme/host** | Callback quay về địa chỉ nội bộ hoặc sai HTTPS/host. | Cấu hình public URL, header được tin cậy và allowlist redirect/ACS. |
| **Session store lỗi** | Đăng nhập xong bị coi là chưa có phiên. | Tính sẵn sàng, timeout, phân phối session giữa các instance. |
| **Clock skew** | Token/assertion bị cho là chưa có hiệu lực hoặc đã hết hạn. | Đồng bộ đồng hồ, kiểm thời gian thực và mức lệch cho phép. |
| **State/correlation không tồn tại** | Callback OIDC/SAML bị từ chối, có thể do phiên mất hoặc request đã hết hạn. | Log phiên ở mức metadata, không tắt state/InResponseTo validation. |
| **Trình duyệt hoặc chính sách chặn cookie** | Luồng phụ thuộc cookie không hoạt động trong một bối cảnh nhất định. | Tái hiện trên cấu hình được hỗ trợ, kiểm third-party context và thiết kế luồng. |
| **Cache/phiên cũ sau thay đổi quyền** | Người dùng vẫn xem dữ liệu cũ hoặc chưa thấy quyền mới. | Đánh giá hiệu lực token, cache RBAC/ABAC và khả năng hủy session. |

**Không dùng “cho phép tất cả redirect URI” hoặc “tắt SameSite/Secure vô điều kiện” để chữa lỗi.** Cần cấu hình cookie và URL đúng mô hình bảo mật của ứng dụng, đặc biệt khi có callback qua nhiều miền.

### 5.2. Phân biệt logout tại IdP và logout tại ứng dụng

Người dùng đăng xuất khỏi ứng dụng có thể chỉ hủy **phiên tại ứng dụng**. Ngược lại, đóng phiên IdP không nhất thiết hủy mọi phiên cục bộ của tất cả SP/RP. Tùy sản phẩm, có thể dùng các cơ chế logout/front-channel/back-channel khác nhau; phải kiểm tra khả năng, điều kiện và giới hạn của từng tích hợp.

Trong sự kiện **Leaver**, không nên dùng một lần logout thủ công làm bằng chứng toàn bộ quyền đã bị thu hồi.

## 6. Lỗi provisioning, JIT và liên kết tài khoản: IdP đúng nhưng ứng dụng sai

Một ứng dụng có thể sử dụng **Just-in-Time (JIT) provisioning** khi người dùng đăng nhập lần đầu, hoặc sử dụng **SCIM** để nhận danh tính/nhóm chủ động từ IAM/IdP.

### 6.1. Những trường hợp thường bị nhầm là SSO error

| Tình huống | Dấu hiệu | Nguồn nên kiểm |
| --- | --- | --- |
| **Joiner chưa được cấp tài khoản ứng dụng** | IdP báo login success nhưng SP/RP báo user not found. | SCIM queue, mapping stable ID, lịch kích hoạt và trạng thái account đích. |
| **JIT bị từ chối** | Token/assertion hợp lệ nhưng không có quyền tạo user mới. | Chính sách JIT, thuộc tính bắt buộc và nguồn định danh. |
| **SCIM create/update thất bại** | Người dùng có tài khoản IdP nhưng ứng dụng còn thiếu hoặc stale. | Response từ service provider, retry, \`id\`/\`externalId\`, schema. |
| **Một người có hai local accounts** | Đăng nhập vào tài khoản không có dữ liệu/quyền mong đợi. | Mapping issuer + stable subject và lịch sử đổi email/rehire. |
| **Ứng dụng đã disable user** | IdP xác thực đúng, ứng dụng từ chối phiên. | Local account state và nguyên nhân lifecycle; không tự bật lại. |
| **Nhóm/role không đồng bộ** | Đăng nhập được nhưng báo not assigned hoặc 403. | SCIM group membership, claim mapping, RBAC/ABAC. |

**SCIM không phải giao thức SSO.** Đặt \`active=true\` tại một SCIM User chưa chứng minh người dùng đã xác thực, và đặt \`active=false\` chưa mặc nhiên hủy mọi phiên/token hoặc PAT của ứng dụng.

### 6.2. Định danh ổn định là điều kiện quan trọng

Đối với OIDC, RP thường cần ràng buộc từ cặp **issuer (\`iss\`) + subject (\`sub\`)** tới local user. Với SAML, SP có thể dùng NameID bền vững và issuer theo hợp đồng liên kết. Khi đối chiếu SCIM, cần phân biệt:

- \`id\`: ID tài nguyên User do **SCIM service provider** cấp.
- \`externalId\`: giá trị tham chiếu do client cấp trong ngữ cảnh tích hợp.
- \`userName\` và email: thuộc tính có thể đổi theo chính sách, không bảo đảm là khóa chung bền vững.

Không tự ghép hai tài khoản bằng email chỉ vì chúng đang có cùng tên hiển thị. Nếu user bị rehire hoặc được chuyển từ Contractor sang Employee, cần **xác minh đúng người và đúng engagement mới**, không tự khôi phục quyền từ account cũ.

## 7. SSO error do authorization: 401 khác 403 như thế nào?

Sau khi ứng dụng xác thực được người dùng, **authorization** còn quyết định tài nguyên và hành động được phép.

| Quan sát | Cách hiểu thường gặp | Lưu ý |
| --- | --- | --- |
| **401 Unauthorized** từ API | Thiếu hoặc không chấp nhận được thông tin xác thực tại API. | Phụ thuộc API; không thể suy ra chính xác nguyên nhân chỉ từ HTTP status. |
| **403 Forbidden** từ API/ứng dụng | Hệ thống hiểu yêu cầu nhưng từ chối theo quyền/chính sách. | Có thể do RBAC, ABAC, resource scope, user disabled hoặc policy khác. |
| **SSO success + “app not assigned”** | Đã xác thực, chưa được phê duyệt quyền vào ứng dụng. | Kiểm assignment, nhóm, role và điều kiện ứng dụng. |
| **Chỉ một chức năng bị cấm** | Role/scope của chức năng hoặc tài nguyên chưa đủ. | Điều tra authorization tại endpoint liên quan, không reset mật khẩu. |
| **Bị từ chối sau Mover** | Có thể là quyền cũ đã bị thu hồi đúng chính sách. | Đối chiếu HRIS, effectiveAt, phê duyệt và quyền mong đợi. |

### 7.1. RBAC

**Role-Based Access Control (RBAC)** cấp quyền theo role. Ví dụ nhân viên kế toán được gán \`finance-reader\`, không có quyền \`finance-admin\`. Nếu ứng dụng từ chối thao tác quản trị, có thể đó là **quyết định đúng** dù SSO hoàn toàn thành công.

### 7.2. ABAC

**Attribute-Based Access Control (ABAC)** xét thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh:

~~~text
ALLOW if
    subject.lifecycleState == "ACTIVE"
    AND subject.departmentId == resource.ownerDepartment
    AND action == "read"
    AND resource.classification <= subject.approvedClearance
~~~

Giả mã chỉ minh họa. Nếu HRIS cập nhật phòng ban mà ứng dụng còn dùng claim/thuộc tính cũ, người dùng có thể bị từ chối quyền mới hoặc giữ quyền cũ. Cần kiểm dữ liệu **có hiệu lực** và **độ tươi của policy input**, không chỉ ID token có chữ ký đúng.

### 7.3. Không giải quyết lỗi bằng cấp quyền vượt nhu cầu

Khi nhân viên báo “vào được nhưng không mở được dữ liệu”, đội hỗ trợ không nên cho vào nhóm admin để thử. Thay vào đó cần xác định:

1. Tài khoản đúng chủ thể và còn quan hệ làm việc hợp lệ không?
2. Quyền được phê duyệt là gì, có thời hạn hoặc SoD không?
3. Tài nguyên có phân loại và ownership nào?
4. Quy tắc RBAC/ABAC nào đưa ra quyết định từ chối?
5. Ứng dụng đã nhận cập nhật quyền mới và xóa quyền cũ chưa?

## 8. SSO error theo vòng đời Joiner–Mover–Leaver

### 8.1. Joiner: tài khoản chưa đến ngày kích hoạt

**Ví dụ:** HRIS xác nhận nhân viên mới bắt đầu làm việc ngày 01/12, còn IAM chuẩn bị IdP account và SCIM User ngày 25/11. Ngày 27/11, người đó mở ứng dụng và bị từ chối.

Đây có thể là **hành vi hợp lệ**, không phải sự cố cần bỏ kiểm soát. Cần kiểm:

- \`startDate\` và \`activationAt\` theo múi giờ/chính sách doanh nghiệp.
- Hồ sơ đã identity proofing, phê duyệt và đủ điều kiện chưa.
- Tài khoản IdP đang ở trạng thái chờ hay bị khóa vì rủi ro.
- SCIM có tạo account sớm nhưng để \`active=false\` theo chính sách không.
- Có phạm vi **preboarding** riêng được phê duyệt hay không.

**Không bật quyền sản xuất chỉ để sửa “SSO error” trước Start date.** Nếu nhu cầu preboarding hợp lệ, phải tạo luồng và quyền được giới hạn rõ.

### 8.2. Mover: đổi phòng ban, manager và quyền

Khi nhân viên đổi vai trò, **subject ID** và credential có thể giữ nguyên trong khi **group/role/entitlement** phải thay. Một lỗi thường gặp:

1. HRIS đã thay \`departmentId\`.
2. IGA tính role mới đúng nhưng connector SCIM lỗi.
3. IdP đăng nhập thành công.
4. Ứng dụng chưa có nhóm mới, trả 403.

Cách xử lý là kiểm pipeline cập nhật thuộc tính và quyền, không thay mật khẩu. Đồng thời phải kiểm **quyền cũ được thu hồi**: việc khôi phục đăng nhập cho Mover không được làm người dùng tích lũy cả quyền phòng ban cũ và mới.

Nếu thay **manager**, SSO có thể vẫn hoạt động bình thường nhưng tuyến phê duyệt thay đổi; không gộp lỗi approval vào lỗi xác thực. Những yêu cầu đang chờ cần được xử lý theo chính sách chuyển giao.

### 8.3. Leaver: từ chối đăng nhập là đúng, nhưng phiên cũ có thể còn

Khi quan hệ lao động chấm dứt, HRIS/nguồn hợp đồng phát sự kiện Leaver. IdP có thể khóa tài khoản và ứng dụng nhận \`active=false\` qua SCIM. Nếu Leaver cố đăng nhập lại và bị từ chối, **đó thường là kết quả mong muốn**.

Rủi ro đáng chú ý là người đã nghỉ **vẫn truy cập được** nhờ:

- Phiên ứng dụng còn sống, không kiểm lại trạng thái tài khoản.
- Token còn hiệu lực hoặc refresh token chưa được thu hồi.
- Local account không đồng bộ với IdP.
- PAT, API key, chứng chỉ hoặc credential thuộc dịch vụ nằm ngoài SSO.
- Nhóm/quyền tại ứng dụng chưa được xóa dù nguồn nhân sự đã kết thúc.

Phải phân biệt **“chặn đăng nhập SSO mới”** với **“không còn đường truy cập thực tế”**. Việc xử lý Leaver chỉ có bằng chứng đầy đủ khi các hệ thống nằm trong phạm vi đã được đối soát hoặc có ngoại lệ rõ chủ sở hữu.

### 8.4. Rehire và chuyển loại quan hệ

Khi Employee được tuyển trở lại hoặc Contractor trở thành Employee, hệ thống cần xác minh liên kết Person/engagement. Không được tự phục hồi tất cả phiên, credential, vai trò hoặc trust cũ chỉ vì email trùng. Lỗi SSO do account đã terminated có thể cần **tạo hoặc liên kết quan hệ hiện tại** và cấp quyền mới theo chính sách, không phải bật lại tài khoản cũ vô điều kiện.

## 9. Runbook chẩn đoán SSO error an toàn

Một runbook tốt giúp xác định nguyên nhân mà **không cần yêu cầu người dùng gửi mật khẩu, ảnh token hay SAML assertion thô**.

### Bước 1. Ghi nhận triệu chứng và phạm vi

Xác định ứng dụng nào, môi trường/tenant nào, thời điểm theo múi giờ, đối tượng bị ảnh hưởng, loại thiết bị/trình duyệt, URL công khai đang dùng và **request/correlation ID** nếu có.

Hỏi bằng ngôn ngữ người dùng:

- Lỗi xảy ra **trước khi nhập credential**, sau bước MFA, khi quay về ứng dụng hay khi mở một chức năng?
- Chỉ một người hay nhiều người bị ảnh hưởng?
- Có thay đổi vị trí, ngày bắt đầu, hợp đồng, ứng dụng hoặc chính sách gần thời điểm lỗi không?

Không yêu cầu người dùng cung cấp mã OTP, password, authorization code, cookie hoặc token.

### Bước 2. Kiểm nguồn và xác minh trạng thái danh tính

Tra ID người dùng ổn định từ nguồn có thẩm quyền và đối chiếu:

- Người dùng thuộc giai đoạn **Joiner, Mover, Leaver** nào?
- Start date/end date và trạng thái có hiệu lực là gì?
- IdP account có tồn tại, có bị khóa hợp lệ hoặc yêu cầu MFA chưa hoàn tất không?
- Có sự kiện nghi chiếm tài khoản, rủi ro thiết bị hoặc policy mới không?

Nếu đây là Leaver đã terminated, **không được mở lại tài khoản chỉ vì xuất hiện ticket SSO**.

### Bước 3. Xác định lớp lỗi thực tế

| Câu hỏi | Nếu câu trả lời là… | Hướng tiếp theo |
| --- | --- | --- |
| IdP có ghi nhận sign-in request không? | **Không** | Kiểm redirect, DNS/TLS, URL, reverse proxy, cấu hình SP/RP. |
| IdP xác thực thành công chưa? | **Chưa** | Xem MFA, lockout, credential, Conditional Access và lifecycle state. |
| Federation response/token có được phát hành không? | **Chưa** | Xem lỗi IdP/OP, client, consent, policy và request. |
| SP/RP có chấp nhận response/token không? | **Không** | Kiểm SAML/OIDC validation, state/nonce, issuer, audience, signature, thời gian. |
| Đã ánh xạ tới đúng local account chưa? | **Chưa** | Xem JIT/SCIM và stable subject mapping. |
| Account được xác thực nhưng bị từ chối quyền? | **Có** | Kiểm RBAC/ABAC, group, app assignment, hiệu lực JML. |
| Đăng nhập xong lặp lại hoặc mất phiên? | **Có** | Kiểm cookie, session store, public URL, logout và token expiry. |

### Bước 4. Đối chiếu log theo một giao dịch

Nối log từ **IdP → SP/RP → IGA/provisioning → ứng dụng/API** bằng request ID, correlation ID, session reference an toàn hoặc mốc thời gian. Không nên dựa vào một email hoặc IP duy nhất vì chúng có thể thay đổi hoặc đại diện nhiều người.

Phân biệt:

- **occurredAt**: sự kiện thực sự xảy ra.
- **ingestedAt**: hệ thống thu log nhận sự kiện.
- **effectiveAt**: thay đổi JML có hiệu lực theo nghiệp vụ.
- **verifiedAt**: thời điểm trạng thái ứng dụng được kiểm chứng.

### Bước 5. Đánh giá thay đổi gần nhất

Xem cấu hình federation, signing key/JWKS, cert SAML, redirect URI/ACS, miền công khai, chính sách MFA, phiên bản ứng dụng và connector SCIM vừa đổi hay không. Chỉ đọc đúng nguồn vận hành được phân quyền; phân biệt lỗi do triển khai với sự kiện đáng ngờ.

### Bước 6. Sửa tại đúng lớp và kiểm thử

Ví dụ:

- Nếu thiếu SCIM account, sửa provisioning/mapping rồi kiểm tra trạng thái đích.
- Nếu token bị từ chối vì audience sai, sửa **cấu hình client/ứng dụng**, không tắt audience validation.
- Nếu account bị khóa do Leaver, giữ nguyên và trả lời rõ quy trình có thẩm quyền.
- Nếu MFA chưa đăng ký vì Joiner, xử lý enrollment qua kênh xác minh.
- Nếu RBAC từ chối đúng, chỉ cấp quyền khi có phê duyệt phù hợp.

Kiểm thử **dương tính** (đúng người, đúng ứng dụng, đúng quyền) và **âm tính** (issuer sai, account disabled, quyền không hợp lệ, token sai phải bị từ chối) theo quy trình được ủy quyền.

### Bước 7. Xác minh và đóng sự cố

Đối soát IdP, tài khoản ứng dụng, nhóm/role, session và các API liên quan. Lưu sự kiện nguồn, thay đổi đã thực hiện, người phê duyệt, kết quả và ngoại lệ chưa xử lý. Không đánh dấu khắc phục xong chỉ từ một HTTP 200 hoặc một lần thử đăng nhập thành công của người dùng nếu còn rủi ro quyền cũ.

## 10. Ví dụ kỹ thuật: chuẩn hóa sự kiện SSO để điều tra

Các hệ thống khác nhau đặt mã lỗi khác nhau. Một lớp **normalized authentication event** giúp phân tích mà không phụ thuộc riêng sản phẩm.

~~~json
{
  "eventId": "auth-evt-20261123-008",
  "traceId": "sso-trace-5281",
  "occurredAt": "2026-11-23T02:10:00Z",
  "tenantId": "corp-primary",
  "applicationId": "expense-portal",
  "subjectId": "person-1042",
  "protocol": "OIDC",
  "stage": "LOCAL_AUTHORIZATION",
  "result": "DENIED",
  "reasonCode": "APPLICATION_ROLE_MISSING",
  "issuerId": "corp-idp",
  "accountLifecycleState": "ACTIVE",
  "provisioningRequestId": "scim-req-6102",
  "policyVersion": "expense-access-v6"
}
~~~

Đây là **schema minh họa với ID giả**, không phải kết quả thực từ một hệ thống. Log có thể cho biết tài khoản đã xác thực ở IdP nhưng bị từ chối tại authorization của ứng dụng; do đó helpdesk nên kiểm nhóm/quyền thay vì reset mật khẩu.

### Giả mã phân tuyến lỗi

~~~text
diagnoseSsoFailure(traceId):
    context = joinAuthorizedLogsByTraceId(traceId)
    subject = resolveByStableSubjectId(context.subjectId)

    if context.hasSecurityIncidentIndicators:
        escalateToSecurityRunbook(context)
        return

    if subject.lifecycleState == "TERMINATED":
        confirmAccessIsDeniedAcrossRelevantTargets(subject)
        return "EXPECTED_LEAVER_DENIAL"

    if context.idpAuthentication != "SUCCESS":
        return investigateIdpAuthenticationAndMfa(context)

    if context.federationValidation != "SUCCESS":
        return investigateSamlOrOidcValidation(context)

    if context.localAccountMapping != "SUCCESS":
        return investigateProvisioningAndSubjectLink(context)

    if context.authorization != "ALLOWED":
        return investigateApprovedRolesAttributesAndResources(context)

    if context.applicationSession != "CREATED":
        return investigateSessionCookieAndProxy(context)

    return verifyTargetStateAndEscalateIfUnresolved(context)
~~~

Giả mã có mục đích **phân loại hỗ trợ vận hành**; các trường hợp thật có thể có nhiều lớp lỗi đồng thời. Không nên dùng script này để tự cấp quyền hoặc tự vô hiệu hóa kiểm tra an ninh.

## 11. Những cách “sửa lỗi” không an toàn

| Cách làm sai | Vì sao nguy hiểm | Cách xử lý đúng |
| --- | --- | --- |
| **Tắt xác minh chữ ký SAML/JWT** | Có thể chấp nhận bằng chứng giả mạo. | Xác định và sửa trust/metadata/khóa ký đúng. |
| **Bỏ kiểm issuer hoặc audience** | Token/assertion của bên khác hoặc ứng dụng khác có thể được chấp nhận. | So khớp issuer, audience và client/SP ID theo cấu hình. |
| **Bỏ \`state\`, \`nonce\` hoặc InResponseTo validation** | Tăng nguy cơ CSRF, replay và tráo luồng đăng nhập. | Sửa session/correlation và callback, không tắt ràng buộc giao thức. |
| **Chấp nhận mọi redirect URI/ACS** | Có thể chuyển phản hồi đăng nhập tới điểm không được phép. | Dùng danh sách endpoint đã đăng ký, so khớp chặt. |
| **Bật local password không MFA để chữa lỗi SSO** | Tạo đường xác thực yếu ngoài kiểm soát tập trung. | Xử lý nguyên nhân SSO và cơ chế dự phòng có phê duyệt. |
| **Gán người dùng vào nhóm admin để thử** | Mở quyền vượt nhu cầu, có thể tạo SoD conflict. | Xem policy và chỉ cấp entitlement được duyệt. |
| **Kích hoạt lại account Leaver** | Khôi phục quyền cho người hết quan hệ hợp lệ. | Đối chiếu HRIS và quy trình rehire có xác minh. |
| **Ghép local user bằng email hiển thị** | Gắn nhầm danh tính, đặc biệt khi đổi tên/tái tuyển dụng. | Issuer + stable subject, mapping được kiểm chứng. |
| **Gửi raw SAML response/ID token cho bên thứ ba** | Lộ thông tin cá nhân, credential hoặc dữ liệu phiên. | Dùng correlation ID, metadata đã che và kênh hỗ trợ bảo mật. |
| **Tăng TTL token/phiên vô hạn** | Tăng cửa sổ truy cập tồn dư khi Mover/Leaver. | Sửa clock/session design và chính sách thời hạn phù hợp. |

**Nguyên tắc vận hành:** một lỗi SSO có thể chính là **kiểm soát bảo mật đang hoạt động đúng**. Phải điều tra trước khi cho phép vượt qua nó.

## 12. Case study: nhân viên chuyển bộ phận, SSO thành công nhưng 403

**Bối cảnh:** nhân viên Bình chuyển từ bộ phận Bán hàng sang Tài chính, hiệu lực **08:00 ngày 01/12**. HRIS phát sự kiện Mover; IAM tính Bình cần role \`finance-reader\` và không còn \`sales-editor\`. IdP sử dụng OIDC SSO với ứng dụng báo cáo.

| Thời điểm giả định | Sự kiện | Điều cần kiểm chứng |
| --- | --- | --- |
| **30/11 15:00** | HRIS xác nhận Mover hiệu lực 01/12 08:00. | Ghi đúng ID chủ thể và effectiveAt. |
| **01/12 08:00** | IGA đổi entitlement mong đợi. | Quyền \`sales-editor\` phải được rà soát/thu hồi. |
| **01/12 08:01** | Connector SCIM cập nhật \`department\` thành công nhưng cập nhật group thất bại. | Trạng thái thuộc tính và group có thể lệch nhau. |
| **01/12 08:05** | Bình đăng nhập qua OIDC, ID token hợp lệ. | Authentication/federation thành công. |
| **01/12 08:06** | Ứng dụng trả 403 ở chức năng Tài chính. | Kiểm role/group tại ứng dụng, không reset mật khẩu. |
| **01/12 08:10** | IAM retry cập nhật group, provider phản hồi thành công. | Chưa kết luận quyền đã áp dụng nếu chưa đọc lại. |
| **01/12 08:12** | Đối soát xác nhận có \`finance-reader\`, không còn \`sales-editor\`. | Kết quả phù hợp quyền mong đợi. |

### Cách điều tra

1. Liên kết SSO trace của Bình tới **đúng \`subjectId\`**, không chỉ \`email\`.
2. Xác minh OIDC \`iss\`, \`aud\`, chữ ký và phiên IdP đều hợp lệ.
3. Kiểm local account và role trong ứng dụng; đọc log connector SCIM.
4. Tính lại **quyền mong đợi** từ HRIS/IGA theo thời điểm có hiệu lực.
5. Sửa kết nối cấp phát hoặc phê duyệt còn thiếu; xác minh role tại ứng dụng.
6. Kiểm tra cả **quyền cũ phải thu hồi**, không chỉ quyền mới cần được cấp.

**Bài học:** “SSO error” có thể là **provisioning/authorization mismatch**. Sửa đúng nguyên nhân vừa giúp người dùng làm việc, vừa tránh **privilege creep**.

## 13. Case study: Leaver bị khóa IdP nhưng còn phiên ứng dụng

**Bối cảnh:** Hà nghỉ việc lúc 17:00 ngày 30/11. HRIS phát sự kiện Leaver và IdP khóa tài khoản đúng hạn. Hệ thống CRM sử dụng SAML SSO nhưng còn phiên ứng dụng riêng; một token/API key khác cũng được phát hành độc lập.

1. Từ 17:00, **đăng nhập SAML mới bị từ chối** ở IdP là kết quả đúng.
2. Một phiên CRM đã tạo từ trước có thể vẫn truy cập được nếu CRM chưa hủy session hoặc kiểm trạng thái hiện hành.
3. SCIM \`active=false\` có thể giúp khóa tài khoản CRM, nhưng phải kiểm provider xử lý phiên thế nào; **không mặc định** thao tác này thu hồi mọi API key.
4. IAM cần rà soát tài khoản cục bộ, nhóm, ủy quyền, PAT, refresh token, các phiên và quyền quản trị phụ.
5. Đối soát sau thu hồi: CRM/API đã từ chối các đường truy cập còn tồn tại chưa? Nếu chưa, phải có ngoại lệ có owner và biện pháp hạn chế phù hợp.

**Bài học:** một hệ thống có thể **báo SSO hoạt động đúng và vẫn còn lỗ hổng Leaver**. Đội IAM phải kiểm **quyền thực tế tại tài nguyên**, không chỉ màn hình đăng nhập.

## 14. Tài khoản dịch vụ, workload và lỗi bị nhầm là SSO

Các workload như batch job, ứng dụng backend, CI/CD pipeline hoặc service account thường **không sử dụng luồng SSO tương tác giống nhân viên**. Chúng có thể dùng OAuth client credentials, workload identity federation, chứng chỉ, API key hoặc credential dịch vụ.

| Triệu chứng | Khác SSO tương tác ở điểm nào? | Cách kiểm tra |
| --- | --- | --- |
| Job nhận \`invalid_client\` | Client authentication tại token endpoint thất bại, không phải người dùng nhập sai mật khẩu. | Client ID, secret/cert/issuer, trust và thời hạn. |
| API trả 401 sau xoay credential | Token hoặc client credential của workload có thể không hợp lệ. | Audience/scope, credential version, secret distribution. |
| Pipeline mất quyền sau nhân viên nghỉ | Service account có owner là Leaver hoặc job dùng PAT cá nhân. | Chuyển ownership, thay PAT bằng workload principal hợp lệ. |
| Batch job bị từ chối 403 | Principal được xác thực nhưng role/scope không đủ. | RBAC/ABAC của workload và tài nguyên. |

**Không bật tài khoản nhân viên đã nghỉ để chữa lỗi pipeline.** Cần xác định principal kỹ thuật, owner hợp lệ, scope, thời hạn credential và thay thế theo quy trình. Khi xử lý, tránh ghi client secret, API key hoặc access token vào ticket/log.

## 15. Quan sát, kiểm toán và bảo vệ dữ liệu khi điều tra SSO

Một log SSO hữu ích phải giúp trả lời: **ai yêu cầu**, **hệ thống nào xác thực**, **vì sao bị từ chối**, **phiên/quyền nào thực tế được tạo** và **trạng thái JML lúc đó là gì**.

### 15.1. Bộ trường nên lưu

| Trường | Giá trị điều tra |
| --- | --- |
| \`eventId\`, \`traceId\`, \`requestId\` | Nối các bước của một giao dịch SSO. |
| \`subjectId\`, \`accountId\`, \`tenantId\` | Liên kết đúng chủ thể, tài khoản và miền; hạn chế nhầm email. |
| \`applicationId\`, \`protocol\`, \`stage\` | Xác định SP/RP và vị trí lỗi. |
| \`issuerId\`, \`audience/clientId\` | Kiểm nguồn phát hành và bên nhận token/assertion. |
| \`result\`, \`reasonCode\`, \`policyVersion\` | Phân biệt xác thực, federation, account mapping và quyền. |
| \`jmlEventId\`, \`lifecycleState\`, \`effectiveAt\` | Kiểm các sự kiện Joiner–Mover–Leaver liên quan. |
| \`provisioningRequestId\`, \`targetAccountId\` | Kiểm connector và trạng thái ứng dụng đích. |
| \`occurredAt\`, \`ingestedAt\`, \`verifiedAt\` | Dựng thời gian sự kiện và độ trễ xử lý. |
| \`actorId\`, \`changeRef\`, \`exceptionId\` | Ai thay cấu hình/role, bằng chứng phê duyệt và lỗi còn mở. |

### 15.2. Không biến debug thành nơi lộ bí mật

Không ghi các giá trị sau vào log, chat, ảnh chụp màn hình không che hoặc ticket hỗ trợ:

- Mật khẩu, OTP, recovery code, passkey private key.
- Toàn bộ SAML response/assertion có thể chứa dữ liệu cá nhân hoặc thông tin có thể dùng lại.
- Authorization code, ID token, access token, refresh token, session cookie và client secret.
- Dữ liệu hồ sơ nhân sự không cần thiết cho quyết định hỗ trợ.

Có thể lưu **credential/token ID, issuer, key ID, subject reference, error code, policy ID, thời điểm và request correlation** theo cơ chế bảo vệ. Bằng chứng cần phân quyền truy cập, mã hóa, hạn lưu và kiểm soát sửa/xóa trái phép. Với nhà cung cấp hỗ trợ cần xem trace, hãy ưu tiên **metadata đã che** hoặc kênh trao đổi dữ liệu chuyên dụng được phê duyệt.

### 15.3. Theo dõi phạm vi quan sát

Một sự kiện sign-in thành công ở IdP **không chứng minh** người dùng đã truy cập được API. Một request SCIM thành công **không chứng minh** mọi phiên/token đã bị thu hồi. Ngược lại, không có log ứng dụng **không chứng minh** không có truy cập nếu connector log bị thiếu hoặc trễ.

Do đó báo cáo điều tra phải ghi **nguồn đã kiểm, nguồn còn thiếu, phạm vi hệ thống, độ trễ và kết quả xác minh thực tế**.

## 16. Chỉ số đánh giá độ tin cậy SSO và JML

| Chỉ số | Cách đo gợi ý | Ý nghĩa |
| --- | --- | --- |
| **Tỷ lệ đăng nhập SSO hoàn tất** | Giao dịch đáp ứng authentication, federation, session theo phạm vi ÷ tổng giao dịch hợp lệ. | Hiệu quả đăng nhập thực tế, không chỉ IdP success. |
| **Tỷ lệ lỗi phân theo giai đoạn** | Authentication, SAML/OIDC validation, account mapping, authorization, session, availability. | Biết nhóm nguyên nhân cần ưu tiên cải thiện. |
| **Thời gian chẩn đoán SSO** | Từ lúc nhận sự cố đến khi xác định lớp lỗi có bằng chứng. | Hiệu quả correlation và runbook. |
| **Tỷ lệ Joiner có tài khoản đích sẵn sàng đúng hạn** | Joiner đủ điều kiện có account/role đã xác minh ÷ Joiner trong phạm vi. | Giảm lỗi “IdP thành công nhưng app chưa có user”. |
| **Độ trễ đồng bộ Mover** | Từ thời điểm có hiệu lực đến khi role/attribute thực tế tại đích đúng. | Phát hiện quyền cũ còn tồn dư hoặc thiếu quyền mới. |
| **Leaver còn phiên hoặc tài khoản truy cập được** | Những đường truy cập đã xác minh còn hoạt động sau thời điểm phải thu hồi. | Đánh giá rủi ro offboarding. |
| **Tỷ lệ ứng dụng kiểm tra validation SAML/OIDC** | SP/RP đã kiểm issuer, audience, chữ ký, thời gian, request binding ÷ ứng dụng thuộc phạm vi. | Ngăn sửa lỗi bằng cách nới lỏng bảo mật. |
| **Tỷ lệ sự cố có chuỗi log xuyên hệ thống** | Incident có IdP, SP/RP, provisioning, authorization và kết quả đích liên quan ÷ tổng incident cần điều tra. | Khả năng truy vết. |
| **Số lỗi sau thay đổi cấu hình trust** | Sự cố liên quan key rollover, redirect URI, metadata, endpoint hoặc cert. | Nâng chất lượng change management. |
| **Số ngoại lệ chưa được xác minh** | Lỗi SCIM, local account, session hoặc quyền vẫn chưa có bằng chứng cuối. | Ngăn kết thúc ticket sớm. |

Cần công bố mẫu số, phạm vi ứng dụng/tenant và các đường xác thực nằm ngoài IdP. **Không đồng nhất một mã lỗi HTTP với kết luận nguyên nhân** khi chưa có dữ liệu theo lớp.

## 17. Checklist vận hành SSO error

1. Có phân biệt lỗi **authentication**, **federation protocol**, **provisioning**, **authorization**, **session** và **availability** không?
2. Đã xác định chính xác **IdP/OP, SP/RP, tenant, ứng dụng và giai đoạn lỗi** bằng correlation ID chưa?
3. Với SAML, có kiểm đúng **issuer, chữ ký, audience, ACS/recipient, subject confirmation, InResponseTo và thời gian** không?
4. Với OIDC, có kiểm **\`iss\`, \`aud\`, chữ ký/JWKS, state, nonce, PKCE, redirect URI và token lifetime** theo luồng không?
5. Khi có redirect loop, đã kiểm **cookie, session store, reverse proxy và public URL** mà không tắt kiểm soát bảo mật chưa?
6. Khi IdP thành công nhưng ứng dụng báo lỗi, đã kiểm **JIT/SCIM, ID liên kết tài khoản, \`active\` và role** chưa?
7. Có phân biệt **lỗi đăng nhập** với quyết định **RBAC/ABAC từ chối đúng chính sách** không?
8. Joiner có được kích hoạt đúng thời điểm sau xác minh, không tự mở tài khoản trước Start date không?
9. Mover có nhận đúng thuộc tính mới **và thu hồi quyền cũ**, không chỉ sửa nhóm cho hết 403 không?
10. Leaver có bị chặn tại **IdP, ứng dụng cục bộ, phiên/token và API credential** theo phạm vi không?
11. Đã xem tác động tới **service account/workload** và tránh bật lại tài khoản của nhân viên đã nghỉ để chữa lỗi tích hợp chưa?
12. Việc khắc phục có giữ nguyên **signature, issuer, audience, MFA, state/nonce, PKCE và authorization checks** không?
13. Có kiểm thử cả trường hợp hợp lệ và trường hợp phải bị từ chối sau sửa lỗi không?
14. Audit có liên kết nguồn JML, SSO trace, thay đổi cấu hình/quyền, trạng thái ứng dụng và ngoại lệ mà **không ghi token/secret** không?

**Ghi nhớ:** **SSO error là triệu chứng trên luồng đăng nhập liên thông, không phải một nguyên nhân duy nhất**. Phải xác định đúng lớp lỗi: **IdP xác thực**, **SAML/OIDC kiểm bằng chứng**, **SCIM/JIT liên kết tài khoản**, **RBAC/ABAC kiểm quyền** hay **phiên/token và hạ tầng**. Trong quản lý **Joiner–Mover–Leaver**, từ chối một tài khoản chưa kích hoạt hoặc đã nghỉ có thể là kiểm soát đúng; ngược lại, đăng nhập SSO thành công không chứng minh không còn quyền tồn dư. Quy trình tốt vừa khắc phục sự cố đúng lớp, vừa **giữ nguyên các kiểm tra bảo mật**, đối soát trạng thái hệ thống đích và lưu bằng chứng kiểm toán đáng tin cậy.
