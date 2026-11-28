# Federation (Liên kết danh tính) trong Identity Assurance

## 1. Vì sao hệ thống cần Federation?

Một nền tảng SaaS phục vụ hàng trăm doanh nghiệp thường không muốn phát hành một mật khẩu riêng cho từng nhân viên khách hàng. Thay vào đó, khách hàng đăng nhập bằng hệ thống định danh doanh nghiệp đang sử dụng; nhà cung cấp SaaS nhận một thông điệp xác thực từ hệ thống đó rồi tạo phiên truy cập trong ứng dụng của mình. Cách tiếp cận này hỗ trợ **Single Sign-On (SSO)** và giảm chi phí quản lý nhiều tài khoản đăng nhập, nhưng đồng thời tạo ra **mối quan hệ tin cậy xuyên tổ chức** cần được thiết kế và kiểm chứng.

**Identity federation (liên kết danh tính)** là việc một hệ thống hoặc tổ chức **dựa vào thông tin về danh tính, sự kiện xác thực hoặc các thuộc tính đã được một bên khác xác nhận**, dựa trên thỏa thuận tin cậy và giao thức đã được thiết lập. Trong bối cảnh người dùng, bên cung cấp xác thực thường gọi là **Identity Provider (IdP)**; ứng dụng tiếp nhận và dựa vào kết quả gọi là **Relying Party (RP)** hoặc **Service Provider (SP)** tùy giao thức.

Ví dụ: nhân viên kế toán thuộc doanh nghiệp A đăng nhập vào ứng dụng Invoice SaaS bằng IdP của doanh nghiệp A. SaaS không trực tiếp kiểm tra mật khẩu của nhân viên; nó phải **xác minh assertion/token có nguồn gốc từ IdP đã được tin cậy, dành đúng cho ứng dụng, còn hiệu lực và gắn với đúng giao dịch đăng nhập**.

Federation giải quyết nhiều vấn đề:

- Tái sử dụng cơ chế xác thực và vòng đời nhân sự tại tổ chức sở hữu danh tính.
- Cho phép đối tác hoặc khách hàng đăng nhập bằng IdP của chính họ, tránh phát hành quá nhiều thông tin xác thực cục bộ.
- Tập trung một số chính sách xác thực như MFA, điều kiện thiết bị hoặc quản lý rủi ro tại IdP.
- Có thể giảm ma sát đăng nhập và hỗ trợ mở rộng mô hình B2B/B2E.
- Cung cấp một cách **truyền có kiểm soát các thuộc tính danh tính** giữa các miền tin cậy.

Nhưng Federation **không tự bảo đảm ứng dụng an toàn**: token hợp lệ vẫn có thể được chấp nhận sai audience, gán nhầm tenant, liên kết nhầm tài khoản, chuyển tiếp sai quyền hoặc tồn tại phiên ứng dụng quá lâu sau khi IdP đã khóa người dùng.

Trong chương **Identity assurance** của module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật từ rủi ro, yêu cầu và controls đến kiểm thử, audit, phát hiện và khắc phục. Với Federation, câu hỏi cốt lõi không chỉ là **“SSO đăng nhập được không?”** mà là **“mối quan hệ tin cậy có đúng, assertions có được kiểm tra đầy đủ, tài khoản có được gắn đúng chủ thể và đúng tenant, và các điều kiện đó được chứng minh ở bản triển khai thực tế thế nào?”**

## 2. Những khái niệm phải phân biệt

| Thuật ngữ | Nghĩa trong Federation | Lưu ý |
| --- | --- | --- |
| **Identity Provider (IdP)** | Bên xác thực danh tính hoặc phát hành thông tin về chủ thể theo quan hệ tin cậy. | IdP có thể là hệ thống doanh nghiệp, cloud identity hoặc identity broker. |
| **Relying Party (RP)** | Ứng dụng dựa vào kết quả của IdP để tạo phiên hoặc quyết định một phần về định danh. | RP vẫn phải kiểm soát quyền trên dữ liệu của mình. |
| **Service Provider (SP)** | Thuật ngữ thường gặp trong SAML cho hệ thống sử dụng assertion. | Trong bài, SP và RP có thể đều chỉ ứng dụng Invoice SaaS theo ngữ cảnh. |
| **Federation assertion / token** | Thông tin xác thực/thuộc tính chủ thể do bên phát hành cung cấp theo giao thức. | Phải kiểm tra issuer, người nhận, thời hạn, bảo vệ toàn vẹn, giao dịch liên quan. |
| **Trust relationship** | Thỏa thuận và cấu hình nói rõ ai được tin, tin điều gì, cho client/tenant nào và thời hạn nào. | Tin một IdP không có nghĩa tin mọi claim và mọi đối tượng của IdP. |
| **Authentication session** | Phiên xác thực tại IdP hoặc phiên cục bộ tại RP. | Hai phiên có thể có vòng đời và cơ chế hủy riêng. |
| **Claim / attribute** | Thuộc tính về chủ thể, sự kiện xác thực hoặc ngữ cảnh. | Email, group, tenant hay MFA claim không tự trở thành quyền ứng dụng. |
| **Subject identifier** | Định danh chủ thể trong phạm vi do issuer xác định. | Thường phải kết hợp với issuer và ngữ cảnh tenant khi gắn tài khoản. |
| **Provisioning / deprovisioning** | Tạo, cập nhật và vô hiệu hóa tài khoản hoặc quyền. | Không mặc nhiên diễn ra khi đăng nhập Federation thành công/thất bại. |
| **Identity broker** | Trung gian nối nhiều IdP và RP, có thể biến đổi hoặc phát hành lại assertions. | Tăng linh hoạt nhưng tạo thêm ranh giới tin cậy và điểm lỗi. |

### Federation, SSO, authentication và authorization

- **Federation** nói về **tin cậy thông tin danh tính giữa các miền**.
- **SSO** nói về **trải nghiệm sử dụng một lần xác thực cho nhiều ứng dụng/phiên theo thiết kế**.
- **Authentication** trả lời “chủ thể nào đã được xác thực theo cơ chế nào?”.
- **Authorization** trả lời “chủ thể ấy được làm gì trên tài nguyên nào, dưới những điều kiện nào?”.

Một ứng dụng có thể hỗ trợ SSO bằng session nội bộ mà không có quan hệ Federation với doanh nghiệp khác. Ngược lại, hỗ trợ Federation không bảo đảm người dùng sẽ không phải xác thực lại; RP có thể yêu cầu xác thực mới cho thao tác nhạy cảm.

**OAuth 2.0 chủ yếu là framework ủy quyền**, không phải tự nó là giao thức xác thực danh tính người dùng. **OpenID Connect (OIDC)** xây lớp xác thực danh tính trên OAuth 2.0; **SAML 2.0** cung cấp cơ chế trao đổi assertions, thường dùng cho đăng nhập enterprise. Không dùng access token được cấp cho một API như bằng chứng đăng nhập dành cho RP nếu thiết kế/giao thức không cho phép.

## 3. Các bên tham gia và ranh giới tin cậy

Giả sử nhân viên thuộc doanh nghiệp A dùng Invoice SaaS thông qua IdP của A:

~~~mermaid
flowchart LR
    U["Người dùng / Trình duyệt"] --> RP["Invoice SaaS / Relying Party"]
    U <-->|"Redirect và xác thực"| IDP["Enterprise Identity Provider A"]
    RP <-->|"Trust metadata, token/assertion verification"| IDP
    RP --> IAM[("Local account + tenant + roles")]
    RP --> DATA[("Invoice data / tenant A")]
    RP --> AUD[("Audit / Assurance evidence")]
    B["Tenant B / IdP B"] -. "Trust riêng biệt" .-> RP
~~~

**Ranh giới cần xem xét:**

1. **B1 – Trình duyệt ↔ RP:** redirect URL, cookie, state, callback và session local đều có thể bị thao túng hoặc sử dụng sai.
2. **B2 – RP ↔ IdP:** RP nhận assertion/token từ một miền tin cậy khác và phải xác nhận nguồn phát hành, thông điệp và phạm vi dự kiến.
3. **B3 – IdP ↔ người dùng:** IdP xác thực theo chính sách riêng; RP không thể chỉ nhìn token có chữ ký để biết chính xác người dùng đã qua MFA hoặc identity proofing nào nếu không có thuộc tính và thỏa thuận đáng tin.
4. **B4 – RP ↔ tài khoản cục bộ:** email, subject và group được ánh xạ sang một principal trong SaaS. Sai liên kết có thể dẫn tới **account takeover** hoặc truy cập sai tenant.
5. **B5 – RP ↔ dữ liệu/nghiệp vụ:** đăng nhập thành công không thay thế kiểm soát quyền đọc/sửa/xuất dữ liệu trên từng đối tượng.
6. **B6 – Metadata/keys/configuration:** thay đổi key, issuer, endpoint hoặc trust relationship có thể làm hệ thống chấp nhận sai thông điệp hoặc gián đoạn toàn bộ người dùng.

Nếu ứng dụng sử dụng **identity broker**, phải phân tích thêm mối tin cậy **IdP gốc → broker → RP**. RP có thể chỉ thấy issuer của broker; cần biết broker cam kết điều gì về IdP nguồn, độ tin cậy thuộc tính và quy tắc ánh xạ tenant.

## 4. Tài sản, threat scenario và mục tiêu bảo mật

Một threat model Federation nên xác định trước khi chọn giao thức:

| Tài sản | Hậu quả nếu sai | Security objective |
| --- | --- | --- |
| **Federation configuration** | Tin nhầm IdP, sai redirect hoặc sai audience. | Chỉ nguồn được duyệt mới được phát hành thông tin cho đúng RP/tenant. |
| **Signing keys / certificates** | Assertion/token giả hoặc mất khả năng xác minh. | Khóa được bảo vệ, xoay vòng và xác nhận đúng nguồn. |
| **Subject-account binding** | Người A bị gắn vào tài khoản B. | Mỗi phiên nhận đúng danh tính nội bộ, không dựa vào thuộc tính dễ thay đổi. |
| **Tenant binding** | Đăng nhập tenant A nhưng vào dữ liệu tenant B. | Ngữ cảnh tenant được kiểm chứng từ trust và quyền nội bộ. |
| **Authentication assurance** | Chấp nhận phiên xác thực yếu cho thao tác nguy hiểm. | Phương pháp, độ mới xác thực và mức assurance đạt requirement đã duyệt. |
| **Roles/claims** | Claim bị lạm dụng để thành admin. | Mapping quyền có allowlist, owner và kiểm tra trong ứng dụng. |
| **RP session / cookies** | Session bị chiếm hoặc tồn tại sau thu hồi quyền. | Vòng đời phiên, cookie và reauthentication có cơ chế phù hợp. |
| **Audit trail** | Không xác định được ai đăng nhập, tenant nào và vì sao được cấp quyền. | Sự kiện có nguồn, request/correlation, outcome và log được bảo vệ. |
| **Availability của IdP** | Khách hàng không đăng nhập được khi phụ thuộc gián đoạn. | Xác định failure behavior, khả năng ứng cứu và SLA theo risk. |

### Từ kịch bản đến yêu cầu có thể kiểm thử

**Kịch bản:** một token do IdP A phát hành cho ứng dụng khác được RP Invoice SaaS chấp nhận vì chỉ kiểm tra chữ ký mà bỏ qua audience.

**Yêu cầu:** “RP phải xác minh token/assertion được phát hành cho đúng client/SP đã đăng ký, đúng issuer, còn hiệu lực và liên kết với phiên đăng nhập hợp lệ theo giao thức được triển khai.”

**Controls:** cấu hình issuer và client cố định, thư viện giao thức được duy trì, kiểm tra audience/recipient/destination, transaction binding, test token bị sửa/thay và log từ chối.

**Evidence:** trust registry, cấu hình client/service provider, test negative cases, kết quả trên release được đánh giá, log đã làm sạch dữ liệu và danh sách ngoại lệ.

## 5. Hai mô hình Federation thường gặp: OIDC và SAML

| Tiêu chí | OIDC | SAML 2.0 |
| --- | --- | --- |
| Kiểu thông điệp chính | ID Token (thường là JWT), authorization code và các artifacts theo flow. | SAML assertion trong SAML Response. |
| Bên phát hành | OpenID Provider (OP), là IdP theo ngữ cảnh OIDC. | SAML Identity Provider. |
| Bên sử dụng | Relying Party/client. | Service Provider. |
| Dữ liệu định danh | Subject và claims phù hợp scope/giao thức. | NameID và các attribute được thỏa thuận. |
| Khám phá/cấu hình | OIDC discovery metadata và key set từ nguồn tin cậy khi dùng. | SAML metadata hoặc cấu hình endpoints/certificates tin cậy. |
| Bảo vệ thông điệp | Xác minh chữ ký/điều kiện token; mã hóa nếu profile đòi hỏi. | Xác minh chữ ký assertion/response theo profile; mã hóa assertion khi cần. |
| Liên hệ giao dịch | state, PKCE, nonce theo flow và các điều kiện hợp đồng giao thức. | AuthnRequest ID, InResponseTo và RelayState theo binding/flow. |
| Nguy cơ thường gặp | Audience/issuer confusion, login CSRF, token substitution, redirect sai. | Chữ ký XML kiểm sai, assertion replay, recipient/audience sai, metadata không đáng tin. |
| Đặc trưng triển khai | Thường thuận tiện với ứng dụng web/mobile/API hiện đại. | Phổ biến trong tích hợp SSO enterprise lâu năm. |

**Không có giao thức nào tự động an toàn hơn trong mọi trường hợp.** Thư viện, profile, cấu hình IdP/RP, kiểm tra assertion/token, quản lý danh tính và khả năng audit quyết định mức bảo vệ thực tế.

### OIDC vs OAuth 2.0

Một **access token** thường được dùng để gọi protected resource/API theo audience và scope/permission của tài nguyên đó. **ID Token** cung cấp thông tin về sự kiện xác thực người dùng cho OIDC client. Không nên dùng ID Token như bearer credential chung cho API, hoặc dùng access token dành cho một API khác để tự suy danh tính đăng nhập vào RP.

Trong kiến trúc API, **resource server** cần kiểm tra access token theo thiết kế riêng, bao gồm issuer, audience, thời hạn và scope/quyền. Kiểm chứng ID Token ở bước login và access token ở bước gọi API là **hai claim assurance khác nhau**.

## 6. Một luồng OIDC Authorization Code với PKCE

Luồng được khuyến nghị rộng rãi cho nhiều trường hợp đăng nhập trình duyệt hiện đại là **Authorization Code Flow** cùng các biện pháp bảo vệ hiện hành như **PKCE**, giao tiếp TLS, kiểm tra issuer và redirect URI.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant RP as SaaS / RP
    participant IDP as IdP / OP
    U->>RP: Mở trang đăng nhập
    RP-->>U: Redirect tới IdP với state, challenge và request
    U->>IDP: Authentication request
    IDP->>U: Xác thực theo chính sách
    IDP-->>U: Redirect tới RP callback với authorization code và state
    U->>RP: Callback
    RP->>RP: Kiểm tra state và login transaction
    RP->>IDP: Đổi code tại token endpoint với code_verifier và client auth nếu áp dụng
    IDP-->>RP: ID Token và tokens theo flow
    RP->>RP: Kiểm tra issuer, signature, audience, lifetime, nonce/claims nếu áp dụng
    RP->>RP: Gắn tài khoản, tenant, quyền; tạo session cục bộ
    RP-->>U: Cookie phiên được bảo vệ
~~~

Sơ đồ là luồng khái quát, không mô tả tất cả profile hay các ràng buộc chi tiết của từng SDK.

### state, PKCE, nonce khác nhau ở đâu?

| Thành phần | Chức năng chính | Sai lầm thường gặp |
| --- | --- | --- |
| **state** | Liên kết response/callback với giao dịch do client khởi tạo, hỗ trợ chống login CSRF và bảo vệ ngữ cảnh chuyển hướng. | Không kiểm tra state, chấp nhận lại state hoặc dùng dữ liệu không ràng buộc phiên. |
| **PKCE** | Ràng buộc authorization code với code_verifier do client giữ, giảm rủi ro mã code bị đánh cắp và đổi trái phép. | Chỉ kiểm tra có tham số challenge mà bỏ qua flow/verifier thực tế. |
| **nonce** | Ràng buộc ID Token với yêu cầu xác thực trong các trường hợp/profile tương ứng; hỗ trợ chống replay/substitution. | Gửi nonce nhưng không đối chiếu, hoặc áp một yêu cầu nonce không đúng profile mà không hiểu flow. |
| **Exact redirect URI** | Giới hạn nơi IdP trả code/response. | Cho wildcard hoặc open redirect tạo khả năng chuyển code tới đích khác. |
| **Issuer / audience** | Xác định đúng bên phát hành và bên nhận. | Chỉ kiểm tra token có chữ ký hợp lệ, không kiểm tra token dành cho ứng dụng nào. |

Với OIDC, **nonce cần được xử lý theo flow và yêu cầu profile**. Trong các flow có ID Token ở front channel, nonce đặc biệt quan trọng; nếu client gửi nonce, phải xác minh giá trị tương ứng trong ID Token. Nhiều triển khai code flow cũng dùng nonce để tăng bảo vệ. Không nên diễn đạt “chỉ cần nonce là đủ chống CSRF”; state, transaction binding, redirect và các biện pháp khác vẫn có vai trò riêng.

### Những kiểm tra quan trọng đối với ID Token

RP cần sử dụng thư viện OIDC đáng tin và kiểm tra theo profile áp dụng, thường gồm:

1. **Nguồn và chữ ký:** thuật toán được phép, khóa của issuer được tin cậy, chữ ký hợp lệ; không tin tùy tiện URL khóa nằm trong token.
2. **Issuer (iss):** trùng định danh của IdP đã đăng ký cho login transaction, không chỉ có định dạng URL “trông giống” IdP.
3. **Audience (aud):** dành cho OIDC client/RP phù hợp; xét azp và trường hợp nhiều audience theo quy tắc OIDC nếu liên quan.
4. **Thời gian:** exp và các điều kiện thời gian khác theo protocol/SDK, có xử lý clock skew giới hạn và có lý do.
5. **Subject (sub):** có giá trị hợp lệ, sử dụng theo phạm vi issuer; không tự thay bằng email.
6. **Nonce, auth_time, acr/amr và các claims khác:** kiểm tra khi đã yêu cầu hoặc khi chính sách cần, với **ý nghĩa đã thỏa thuận**.
7. **Giao dịch và client:** response được ràng buộc với quá trình login đúng tenant/client/redirect và không bị lặp sai.

**Một token có chữ ký hợp lệ chưa đủ để tin** nếu issuer, audience, session hoặc tenant sai. Không tự động nhận thuật toán dựa vào header không kiểm soát, không chấp nhận kiểu ký không được cho phép, và không tải JWKS từ một endpoint tùy ý do attacker chỉ ra trong token.

## 7. SAML 2.0 Federation: những gì SP phải kiểm tra

Với SAML, SP gửi hoặc nhận luồng đăng nhập theo binding/profile đã thỏa thuận và xử lý **SAML Response/Assertion**. Dữ liệu thường được trao đổi qua trình duyệt; SP phải chống lại việc assertion hợp lệ cho một mục tiêu khác bị chuyển sang phiên của mình.

### Nhóm kiểm tra cơ bản

| Nhóm | Câu hỏi security assurance |
| --- | --- |
| **Trust metadata** | IdP entityID, endpoints, chứng chỉ và profile có đến từ nguồn đã được xác minh, đúng tenant/partner? |
| **Signature** | Chữ ký của Response/Assertion có được xác minh theo yêu cầu cấu hình, dùng đúng khóa đã tin cậy và đúng phần nội dung được sử dụng? |
| **Issuer** | Assertion đến từ IdP được phép phát hành cho SP/tenant này? |
| **AudienceRestriction** | Assertion dành đúng cho SP? |
| **Recipient/Destination** | Response/assertion được gửi tới đúng Assertion Consumer Service/endpoint được đăng ký? |
| **Time Conditions** | NotBefore, NotOnOrAfter và các giới hạn thời gian khác hợp lệ với clock skew được kiểm soát? |
| **InResponseTo** | Với luồng SP-initiated, response gắn với yêu cầu xác thực đang chờ có đúng ID không? |
| **SubjectConfirmation** | Các điều kiện người nhận, giao dịch, thời gian và confirmation method có phù hợp? |
| **Replay protection** | Assertion ID hoặc bằng chứng giao dịch đã sử dụng có bị chấp nhận lặp không? |
| **Subject/attributes** | NameID và attributes có được ánh xạ đến identity/tenant đúng theo hợp đồng? |

### Hai lỗi đặc biệt cần cảnh giác

**XML Signature Wrapping:** nếu ứng dụng xác minh chữ ký cho một phần XML nhưng sau đó lại đọc dữ liệu chủ thể hoặc quyền từ một phần khác chưa được ký, attacker có thể lợi dụng sự không khớp. Cần dùng thư viện SAML đã được duy trì, giới hạn parser và xác định **chính phần nội dung được xác minh** là phần sử dụng để tạo principal.

**Replay/unsolicited assertion:** một assertion được sử dụng lại hoặc gửi tới SP khi không gắn với giao dịch dự kiến có thể dẫn tới đăng nhập sai phiên. Đối với IdP-initiated SSO, cách kiểm soát giao dịch khác SP-initiated vì không có AuthnRequest tương ứng; phải đánh giá riêng profile và các biện pháp bù như anti-replay, recipient/audience, điều kiện session và hạn chế luồng.

### Mã hóa không thay cho xác minh

SAML assertion có thể được mã hóa để giảm lộ thuộc tính qua đường truyền hoặc trung gian, tùy cấu hình. **Một assertion được mã hóa nhưng không có nguồn gốc và đối tượng nhận được xác minh đúng vẫn có thể gây rủi ro.** Kiểm tra chữ ký, audience, thời gian và giao dịch không thể bỏ qua chỉ vì có mã hóa.

## 8. Trust configuration và quản lý vòng đời metadata/khóa

Federation là **mối tin cậy được cấu hình**, không phải niềm tin vào bất cứ endpoint có HTTPS.

Một trust record tốt nên chỉ rõ:

- **Partner/tenant:** tổ chức nào và hệ thống nào thuộc phạm vi.
- **Issuer/entityID:** định danh IdP được phê duyệt, cách bảo đảm đúng nguồn.
- **Client ID / SP entityID:** đối tượng nhận và các endpoint callback/ACS cố định.
- **Allowed algorithms/profiles:** chỉ những phương thức đã được phê duyệt và thư viện hỗ trợ an toàn.
- **JWKS/certificates:** nguồn metadata/keys được tin cậy, cách kiểm soát xoay vòng và chấm dứt tin cậy.
- **Claims/attribute contract:** những thuộc tính bắt buộc, ý nghĩa, nguồn và mức tin cậy.
- **Tenant/account binding:** quy tắc gán người và ứng dụng, chống nhầm tenant.
- **Authentication requirements:** MFA, phương pháp, độ mới và tín hiệu assurance khi cần.
- **Provisioning/deprovisioning:** ai duy trì trạng thái người dùng, quyền, session và dữ liệu sau nghỉ việc.
- **Incident/revocation contacts:** đầu mối xử lý key compromise, IdP outage, sai claims hoặc account takeover.
- **Change/review/expiry:** người phê duyệt, phiên bản trust và trigger đánh giá lại.

### Xoay vòng khóa đúng cách

IdP có thể thay signing key theo lịch. RP cần lấy key từ **metadata endpoint đã tin cậy**, kiểm soát caching và refresh theo SDK, đồng thời xử lý thời gian chuyển tiếp key cũ/mới theo thỏa thuận. Nếu khóa không biết xuất hiện trong token, có thể refresh keyset từ **nguồn cố định đã đăng ký**, không đọc URL tùy ý từ header token hoặc tự bỏ kiểm tra chữ ký.

**Giới hạn availability và security:** khi IdP đổi key không thông báo, đăng nhập có thể thất bại. Không được “tạm cho qua chữ ký” để khôi phục dịch vụ; phải có quy trình sự cố trust, phối hợp IdP và khôi phục cấu hình đúng.

### Chấm dứt mối tin cậy

Khi hợp đồng kết thúc hoặc phát hiện compromise: vô hiệu hóa issuer/client liên quan, xử lý tài khoản liên kết, session, provisioning, quyền API và token còn hiệu lực theo cơ chế thực tế. **Xóa cấu hình trên trang quản trị** không tự chứng minh mọi session hoặc bản sao quyền đã mất hiệu lực.

## 9. Subject identity, account linking và nguy cơ nhầm người

Đây là một trong những rủi ro nghiệp vụ quan trọng nhất của Federation B2B. Một RP có thể xác minh token hoàn toàn đúng về mặt mật mã, nhưng **gắn nó vào sai tài khoản cục bộ**.

### Vì sao không nên dùng email làm khóa danh tính duy nhất?

Email có thể đổi khi nhân viên đổi tên, tổ chức đổi miền hoặc khi địa chỉ được tái cấp cho người khác. Nhiều nguồn phát hành có thể đưa cùng một giá trị email; mức xác minh email và quyền sở hữu địa chỉ có thể khác nhau.

Nếu SaaS tự động đăng nhập vào tài khoản cũ chỉ vì email trong token khớp email đã lưu, một IdP mới hoặc người dùng khác có thể được **liên kết nhầm**, dẫn tới chiếm quyền truy cập.

### Khóa liên kết thực tế

Trong nhiều thiết kế OIDC, một **federated subject key** có thể dựa vào:

**Tenant/internal trust context + trusted issuer + stable subject ID.**

Tuy nhiên:

- **Tenant context phải được xác minh độc lập** theo cấu hình trust và giao dịch đăng nhập, không lấy trực tiếp từ form/header không đáng tin.
- **Issuer và subject** phải lấy từ ID Token đã xác minh, không từ thông điệp chưa được kiểm chứng.
- Một issuer có thể phục vụ **nhiều tenant**; không mặc nhiên một issuer bằng đúng một khách hàng.
- Trong một số hệ thống, subject là **pairwise identifier** khác nhau giữa các client; cần thỏa thuận về khả năng giữ ổn định khi thay client/app.
- Nếu cần đổi IdP hoặc liên kết lại tài khoản, phải dùng **account recovery/linking workflow có xác minh và phê duyệt thích hợp**, không tự nối bằng email.

### Quy trình liên kết tài khoản an toàn

1. RP xác định tenant đã lựa chọn bằng **login transaction có kiểm soát**, đã ràng buộc state và trust configuration.
2. Kiểm tra assertion/token từ IdP được **tenant đó phê duyệt**.
3. Sử dụng định danh chủ thể ổn định để tìm federated identity mapping đã đăng ký.
4. Nếu lần đầu, tạo hoặc mời liên kết tài khoản theo **quy tắc provisioning/approval** và kiểm tra vai trò.
5. Nếu có xung đột email, subject hoặc tài khoản cũ, **không tự hợp nhất**; chuyển quy trình xác minh quyền sở hữu.
6. Ghi audit người/nguồn đã liên kết, phạm vi tenant và quyết định; kiểm thử khi đổi email, đổi IdP, tái cấp tài khoản.

**Một domain email doanh nghiệp được xác nhận không đủ để chứng minh mọi người dùng mang domain đó có quyền truy cập mọi dữ liệu của doanh nghiệp.** Domain có thể hỗ trợ xác định tổ chức trong một số luồng, nhưng membership, quyền và account linking phải có cơ sở riêng.

## 10. Multi-tenant Federation: ranh giới giữa các khách hàng

Một SaaS có nhiều khách hàng, mỗi khách hàng có IdP riêng hoặc cùng dùng một nền tảng IdP đa tổ chức. Các lựa chọn thiết kế thường gặp:

| Cách tổ chức | Lợi ích | Rủi ro cần xét |
| --- | --- | --- |
| **Một cấu hình IdP cho từng tenant** | Đơn giản hóa ownership và giới hạn nguồn tin cậy. | Cấu hình drift giữa các tenant; onboarding sai issuer/keys. |
| **Một issuer nền tảng phục vụ nhiều tenant** | Dễ tích hợp với nhà cung cấp định danh phổ biến. | Issuer không tự chứng minh chủ thể thuộc đúng tenant; cần claim và binding phù hợp. |
| **Identity broker trung gian** | RP dùng một cơ chế liên kết với nhiều IdP. | Broker trở thành nguồn identity assertion và điểm rủi ro tập trung; source IdP mapping phải minh bạch. |
| **Hỗ trợ cả SAML và OIDC** | Phù hợp nhiều khách hàng. | Chính sách và bằng chứng của hai đường dễ không nhất quán; có thể tạo fallback yếu. |

### Một cuộc tấn công nhầm tenant

Khách hàng A và B có cùng địa chỉ email tại hai IdP (hoặc một địa chỉ từng được tái cấp). RP dùng email để tìm tài khoản thay vì **issuer + sub + tenant binding**. Người ở B có thể bị liên kết vào tài khoản của A dù token được IdP B ký hợp lệ.

**Nhóm rủi ro:** giả mạo/liên kết sai danh tính, vượt quyền theo tenant và khả năng lộ dữ liệu. Controls cần có: registry trust riêng, khóa identity ổn định, account linking có kiểm chứng, authorization theo tenant/object và test negative cross-tenant.

### Một kiểm tra nhỏ không bao phủ toàn bộ hệ thống

Khi user tenant A đăng nhập, RP có thể thiết lập tenant A chính xác nhưng **worker xuất hóa đơn** lại đọc dữ liệu bằng service account rộng và chỉ dựa vào tenantId trong queue message. Token login đúng không chứng minh job/export đúng quyền. Cần kiểm tra **login identity → principal → authorization → job → storage** như một chuỗi.

## 11. Claims, roles và phân quyền: ranh giới giữa IdP và RP

IdP có thể gửi các attributes như name, email, group, department, roles hoặc thông tin MFA. Nhưng **nguồn phát hành một claim không tự tạo quyền tại ứng dụng**.

### Quy tắc mapping an toàn

- Định nghĩa **allowlist claims** và ý nghĩa được thỏa thuận với từng IdP/tenant.
- Ràng buộc claim với issuer, client, tenant và thời gian; không nhận giá trị nhóm hoặc role từ IdP không được phép cấp quyền đó.
- Tránh biến bất kỳ giá trị role có chữ “admin” thành quyền admin nội bộ mà không có mapping được duyệt.
- Áp dụng **least privilege**, mặc định từ chối quyền ngoài hợp đồng.
- Với quyền nhạy cảm, kết hợp quy trình phê duyệt, SoD, JIT/PAM hoặc kiểm tra tại RP nếu cần.
- Ghi lịch sử thay đổi claim mapping và kiểm thử cả các giá trị bất thường/missing claim.
- Kiểm tra object-level authorization và data ownership tại chính RP cho từng thao tác.

### Ví dụ

IdP của khách hàng gửi group **Finance**. RP ánh xạ Finance thành **InvoiceReader**; không tự động cấp **RefundApprover**, vì quyền phê duyệt hoàn tiền liên quan quy trình tách nhiệm vụ nội bộ của ứng dụng.

Nếu IdP đổi tên group hoặc người dùng không còn trong group, RP cần có **quy tắc cập nhật quyền**. Không được giữ quyền cũ vô thời hạn chỉ vì session trước đó chứa claim cũ, trừ khi có kiểm soát và thời hạn phù hợp với chính sách.

## 12. Identity assurance: IAL, AAL, FAL không đồng nghĩa

Trong các mô hình assurance được sử dụng rộng rãi, có thể phân biệt ba chiều:

| Khái niệm | Câu hỏi chính | Ví dụ cần biết |
| --- | --- | --- |
| **Identity Assurance Level (IAL)** | Mức tin cậy về việc danh tính thực được thiết lập/chứng minh ra sao? | Đã có identity proofing, kiểm tra hồ sơ hay chỉ tự khai? |
| **Authenticator Assurance Level (AAL)** | Mức tin cậy của cơ chế xác thực đang dùng? | Phương pháp, nhiều yếu tố, khả năng chống phishing và cách bảo vệ authenticator. |
| **Federation Assurance Level (FAL)** | Mức bảo đảm của cách truyền thông tin xác thực/assertion giữa các miền tin cậy? | Bảo vệ assertion, ràng buộc bên nhận, cách xử lý bí mật và các yêu cầu profile tương ứng. |

Đây là các **khía cạnh phân biệt**, không phải một số “độ an toàn đăng nhập” duy nhất. Tên và mức cụ thể được định nghĩa bởi bộ tiêu chuẩn áp dụng, chẳng hạn họ NIST SP 800-63; khi đưa vào một chương trình tuân thủ phải đối chiếu **phiên bản và tiêu chí hiện hành thực sự áp dụng**.

### Một token có chữ ký không chứng minh người dùng đã MFA

Chữ ký xác nhận token đến từ bên giữ khóa tương ứng, trong điều kiện trust được xác minh. Nó **không tự chứng minh**:

- IdP có xác minh danh tính thực bằng quy trình proofing phù hợp.
- Người dùng vừa thực hiện MFA trong giao dịch hiện tại.
- MFA dùng cơ chế có khả năng chống phishing theo yêu cầu nghiệp vụ.
- Claims nhóm/tenant đã được cập nhật kịp thời.
- Quyền cục bộ tại RP phù hợp với công việc và dữ liệu.

Nếu RP cần một mức xác thực cho thao tác nguy hiểm, phải có **hợp đồng IdP/RP** nêu tín hiệu tin cậy và cách diễn giải, ví dụ **acr**, **amr** hoặc **auth_time** trong OIDC khi có, hay thông tin authentication context tương ứng trong SAML.

**acr/amr có ý nghĩa phụ thuộc hợp đồng và IdP.** Không được suy ra từ một chuỗi như “mfa” rằng mọi tiêu chí assurance của tổ chức đã được đáp ứng. Cần kiểm tra chính sách IdP, cách phát sinh claim và kết quả thử nghiệm cụ thể.

## 13. Fresh authentication, step-up và phiên cục bộ

Đối với một số hành động rủi ro cao như đổi tài khoản nhận tiền, cấp quyền admin hoặc tải dữ liệu nhạy cảm hàng loạt, ứng dụng có thể yêu cầu **reauthentication hoặc step-up authentication**.

### Tách ba trạng thái

1. **IdP session:** IdP còn nhận biết người dùng đã đăng nhập và có thể cấp assertion/token mới.
2. **RP local session:** ứng dụng SaaS duy trì cookie/phiên riêng và quyết định khi nào phải xác thực lại.
3. **Authorization state:** người dùng còn quyền trên tenant, đối tượng và thao tác cụ thể hay không.

Một người bị vô hiệu hóa ở IdP **không nhất thiết lập tức bị đăng xuất khỏi RP** nếu RP vẫn chấp nhận session cũ. Một người được xác thực lại cũng không tự có quyền mới tại RP.

### Security requirements phù hợp

- Cookie phiên được bảo vệ (ví dụ Secure, HttpOnly và SameSite phù hợp kiến trúc), được rotate ở thời điểm cần và không lưu bí mật trong nơi dễ đọc.
- Giới hạn phiên tuyệt đối/nhàn rỗi theo rủi ro, chống session fixation và CSRF cho các thao tác state-changing theo thiết kế.
- Step-up cho hành động nhạy cảm, có cơ chế **kiểm tra thời điểm và phương pháp xác thực** chứ không chỉ có mặt claim.
- Thu hồi quyền và session theo sự kiện JML/sự cố trong giới hạn được quy định.
- Kế hoạch xử lý IdP outage, session đang mở và quyền đặc quyền.

### Single Logout (SLO) có giới hạn

OIDC và SAML có các cơ chế logout khác nhau; khả năng đăng xuất xuyên các ứng dụng phụ thuộc flow, phiên bản thư viện, IdP và các client đã tích hợp. **Đăng xuất tại IdP không đảm bảo mọi RP session đã kết thúc ngay**. Một chương trình assurance cần thử logout, deprovisioning và session revocation đầu cuối, ghi rõ phần không hỗ trợ.

## 14. JIT provisioning, SCIM và vòng đời Joiner–Mover–Leaver

Federation hỗ trợ xác thực, còn **quản lý vòng đời tài khoản** cần một quy trình riêng. Các hình thức phổ biến:

| Cơ chế | Mục đích | Rủi ro |
| --- | --- | --- |
| **Just-in-Time (JIT) provisioning** | Tạo tài khoản cục bộ khi đăng nhập hợp lệ lần đầu theo chính sách. | Tự tạo user cho mọi assertion hợp lệ, cấp role mặc định quá rộng hoặc liên kết bằng email. |
| **SCIM / provisioning API** | Đồng bộ danh tính, nhóm, trạng thái và thuộc tính qua API/protocol provisioning. | Sync lỗi, xóa nhầm, quyền cũ tồn tại khi mất kết nối. |
| **Manual approval / invitation** | Quyết định trước ai được phép vào RP hoặc tenant. | Quy trình chậm, người được mời có thể dùng IdP khác nếu binding sai. |
| **Event-driven deprovisioning** | Thu hồi quyền theo sự kiện nhân sự/tài khoản. | Phiên/token còn sống hoặc service khác không nhận được sự kiện. |

### Kịch bản JML

**Joiner:** nhân viên mới được cấp account tại IdP; RP chỉ tạo/liên kết tài khoản nếu tenant, subject và yêu cầu onboarding hợp lệ; role mặc định tối thiểu.

**Mover:** nhân viên chuyển từ kế toán sang chăm sóc khách hàng; quyền cũ cần được cập nhật ở IdP, provisioning và RP, kể cả session/cache.

**Leaver:** nhân viên nghỉ việc; IdP bị vô hiệu hóa và provisioning gửi deactivation, nhưng RP còn session và quyền export. Cần có tiêu chí **time to deprovision** và phép kiểm tra hiệu lực trên các luồng thực tế.

### Đừng dùng “không đăng nhập được” làm bằng chứng đã xóa quyền

Một IdP chặn người dùng có thể ngăn phiên mới nhưng không xử lý **access token còn sống**, API keys, sessions của RP, tài khoản cục bộ khác hoặc quyền của service account. Hồ sơ deprovision cần xác định tất cả đường quyền nằm trong scope.

## 15. Threat modeling cho Federation

Federation mở thêm bề mặt tấn công. Dùng STRIDE hoặc phương pháp tương đương để tìm kịch bản theo các trust boundaries:

| Nhóm | Kịch bản | Control cần kiểm chứng |
| --- | --- | --- |
| **Spoofing** | Assertion/token từ IdP không được duyệt nhưng RP vẫn tin; subject bị gắn sai. | Kiểm tra issuer/signature, trust registry, account binding và negative tests. |
| **Tampering** | Token/claims bị sửa hoặc metadata bị thay trái phép. | Bảo vệ chữ ký/toàn vẹn, metadata provenance, review thay đổi, chống XML signature misuse. |
| **Repudiation** | Không liên kết được login từ issuer tới local account và hành động nhạy cảm. | Audit chain gồm issuer, federated subject reference, principal nội bộ, outcome, correlation. |
| **Information Disclosure** | User thuộc tenant A vào dữ liệu B; token nhạy cảm bị ghi log hoặc chuyển sai endpoint. | Tenant/object authorization, log minimization, callback/redirect restrictions. |
| **Denial of Service** | IdP outage hoặc key rotation sai khiến mọi người không đăng nhập được. | Dependency monitoring, runbook, rotation testing, phù hợp continuity objective. |
| **Elevation of Privilege** | Claim group từ IdP tự thành PlatformAdmin, hoặc account linking ghi đè tài khoản cũ. | Allowlisted mapping, phê duyệt quyền nhạy cảm, test role/SoD và binding. |

Các nhãn là **gợi ý phân loại**, không có giá trị thay risk assessment. Một kịch bản có thể mang nhiều nhãn và phải đánh giá likelihood/impact, controls hiện hành, evidence và residual risk theo phương pháp được tổ chức chọn.

### Các lỗi thường thấy khi cấu hình

- Chỉ kiểm tra chữ ký mà bỏ issuer, audience, lifetime hoặc giao dịch login.
- Dùng cấu hình “common” hoặc multi-tenant issuer mà không xác minh tenant thực sự được tin cậy.
- Cho redirect URI quá rộng hoặc có open redirect.
- Nhận vai trò admin trực tiếp từ claim không có mapping đã phê duyệt.
- Ghép tài khoản bằng email mà không xác minh ownership và subject binding.
- Không kiểm tra replay, login CSRF, IdP-initiated unsolicited flows.
- Không xử lý trường hợp key/cert bị thu hồi hoặc đổi IdP.
- Lưu ID Token/access token/refresh token trong log hoặc URL.
- Cho rằng IdP logout/deactivation sẽ tự hết hạn mọi session RP.
- Coi MFA tại IdP là bằng chứng mặc định cho mọi hành động RP.

## 16. Ví dụ cấu hình an toàn trong Java/Spring Security

Với một ứng dụng Java/Spring, thường nên **dùng thư viện OIDC/SAML được duy trì**, thay vì tự xác minh JWT, parse XML hoặc xây callback login từ đầu. Tuy nhiên, việc sử dụng SDK không loại bỏ yêu cầu cấu hình đúng và kiểm thử.

### 16.1. Cấu hình đăng nhập OIDC ở lớp web

Ví dụ Spring Security theo phong cách cấu hình Java hiện đại, giả định **ClientRegistration** và provider metadata đã được thiết lập riêng:

~~~java
@Configuration
@EnableWebSecurity
public class FederatedLoginSecurity {
    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/login/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        // Không tắt CSRF, session fixation protection hoặc
        // token validation để "sửa nhanh" vấn đề SSO.
        return http.build();
    }
}
~~~

Đây chỉ là **khung cấu hình**; cần imports, dependency, cấu hình OIDC client/issuer, logout, session, approval và authorization logic đúng với phiên bản framework sử dụng. Chính ví dụ này **chưa thể hiện quy tắc phân quyền tenant và claim mapping**. Ngoài ra phải bảo đảm callback endpoints thật sự đi theo config của OAuth2 Login, không tự permit những endpoint nghiệp vụ nhạy cảm.

### 16.2. Gắn federated identity vào tài khoản cục bộ

Pseudocode Java sau minh họa **một quyết định account binding** sau khi ID Token đã được SDK xác minh, không phải API có thể dùng nguyên bản:

~~~java
record FederatedKey(String tenantId, String issuer, String subject) {}

LocalAccount resolveLocalAccount(
        VerifiedOidcIdentity identity,
        VerifiedLoginContext loginContext) {

    String tenantId = loginContext.tenantId();
    String issuer = identity.issuer();
    String subject = identity.subject();

    if (!trustRegistry.isIssuerAllowedForTenant(tenantId, issuer)) {
        throw new AccessDeniedException("Untrusted federation");
    }
    if (!trustRegistry.isClientAllowedForTenant(
            tenantId, loginContext.clientRegistrationId())) {
        throw new AccessDeniedException("Wrong federation client");
    }

    FederatedKey key = new FederatedKey(tenantId, issuer, subject);
    return localAccountRepository.findByFederatedKey(key)
            .orElseThrow(() -> new AccessDeniedException(
                    "Federated account is not linked"));
}
~~~

**VerifiedOidcIdentity** và **VerifiedLoginContext** là kiểu minh họa, chỉ được hình thành sau khi xác minh giao thức và login transaction. Giá trị tenant trong context phải gắn với **state/flow được bảo vệ** và cấu hình trust, không lấy tùy ý từ query parameter. Đoạn này cố ý **không tự liên kết bằng email** và không tự cấp role: onboarding/JIT và authorization thuộc các quy trình được phê duyệt riêng.

### Cần kiểm thử gì quanh framework?

Thư viện có thể xác minh token theo chuẩn, nhưng ứng dụng vẫn cần test:

- Từ chối issuer không thuộc tenant, ID Token sai audience hoặc không đủ điều kiện thời gian.
- State sai, giao dịch login bị lặp và callback khác cấu hình.
- Tạo session đúng local account và tenant; không nhập nhằng user cùng email khác issuer.
- Claim thiếu/thay đổi và việc role mapping chỉ cấp quyền đã được duyệt.
- Quyền của người dùng khi logout, thay IdP, deprovision và refresh session.
- Đường quản trị/batch/export không bypass authorization dù người dùng đã SSO.

## 17. Case study: B2B Invoice SaaS liên kết nhiều IdP

### 17.1. Phạm vi

Invoice SaaS hỗ trợ hai khách hàng:

- **Tenant A:** doanh nghiệp A, IdP A, người dùng có nhóm Finance và Viewer.
- **Tenant B:** doanh nghiệp B, IdP B, có nhân viên và tài khoản nhà thầu.

SaaS hỗ trợ OIDC, lưu user nội bộ và ánh xạ danh tính thông qua trust registry. Một email đã được sử dụng ở cả hai miền vì nhân sự từng chuyển công ty.

**Security objective:** người dùng phải đăng nhập theo đúng trust của tenant, liên kết với đúng local account, chỉ nhận role được phép và không thể đọc hóa đơn của tenant khác.

### 17.2. Các câu hỏi của nhóm assurance

1. Khi user chọn tenant A, IdP B có thể gửi token tới cùng callback và được chấp nhận không?
2. Một token hợp lệ cho client B có thể đăng nhập client A do cùng khóa issuer không?
3. Hai user cùng email nhưng khác issuer/sub có bị nối nhầm không?
4. Một IdP gửi group Admin trái hợp đồng có khiến RP cấp BillingAdmin không?
5. Sau khi IdP thu hồi quyền nhóm hoặc vô hiệu hóa user, local RP session tồn tại bao lâu?
6. Một job export có dùng tenant đã xác minh hay chỉ tin giá trị từ message?

### 17.3. Phát hiện giả định

Team kiểm thử tìm được hai sai lệch:

- **FED-01 – Email auto-link:** SaaS tự liên kết user theo email trước khi xét issuer và stable subject.
- **FED-02 – Role escalation:** claim group “Administrators” từ IdP bất kỳ được ánh xạ thẳng thành TenantAdmin.

Hai phát hiện có thể khiến RP gắn sai tài khoản hoặc cấp quyền quá mức mặc dù OIDC token được ký đúng. Đây là **lỗi trust/account mapping tại RP**, không nhất thiết là lỗi chữ ký.

### 17.4. Biện pháp khắc phục

**FED-01:** thay ánh xạ email bằng liên kết có ràng buộc tenant + issuer + subject, thêm migration có kiểm tra đối với tài khoản cũ và quy trình linking khi đổi IdP. Không tự hợp nhất dựa vào email.

**FED-02:** dùng bảng claim-to-role mapping có allowlist theo từng tenant/issuer, quyền mặc định tối thiểu; role admin cần quyết định hợp lệ theo chính sách. Thêm kiểm tra SoD và negative tests.

Đồng thời, cập nhật audit trail: phiên đăng nhập có issuer và federated subject reference tối thiểu, tenant, tài khoản nội bộ, mapping rule version và kết quả, **không lưu token thô**.

### 17.5. Test matrix sau sửa

| ID | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| **FED-TEST-01** | User A dùng IdP A và client/tenant đúng. | Đăng nhập vào đúng local account với quyền được duyệt. |
| **FED-TEST-02** | Token IdP B được đưa vào giao dịch tenant A. | Không tạo phiên tenant A; từ chối theo policy. |
| **FED-TEST-03** | Token hợp lệ nhưng audience thuộc client khác. | Không chấp nhận. |
| **FED-TEST-04** | User A và B cùng email nhưng khác issuer/sub. | Không tự liên kết thành cùng account. |
| **FED-TEST-05** | IdP tự gửi claim admin ngoài contract. | Không cấp quyền admin. |
| **FED-TEST-06** | User có quyền tenant A đọc hóa đơn tenant B. | Bị từ chối trên API và đường export trong phạm vi. |
| **FED-TEST-07** | User bị deprovision ở IdP khi đang có session RP. | Quyền/phiên thay đổi theo yêu cầu đã định và được đo thời gian. |
| **FED-TEST-08** | Signing key thay theo lịch được phê duyệt. | Token khóa mới hợp lệ được chấp nhận; khóa sai/ngoài trust bị từ chối. |
| **FED-TEST-09** | state bị thay hoặc callback bị replay. | Không ghép nhầm giao dịch hay tạo phiên trái phép. |
| **FED-TEST-10** | IdP tạm gián đoạn. | RP xử lý theo runbook được duyệt; không bỏ xác minh assertion. |
| **FED-TEST-11** | Logout từ IdP hoặc RP, kiểm tra session còn tồn tại. | Trạng thái thực phù hợp cam kết SLO/session; giới hạn được ghi. |
| **FED-TEST-12** | User đổi email hoặc tổ chức đổi IdP. | Chỉ liên kết lại theo workflow đủ điều kiện; không tự chiếm account. |

**Các test phải chạy trong môi trường được phép**, sử dụng danh tính/dữ liệu giả khi có thể. Kết quả production cần được xác nhận bằng cấu hình, phiên bản, telemetry và kiểm tra an toàn phù hợp; không cố tình phát hành token giả vào hệ thống thật nếu không được cho phép.

## 18. Federation trust register và mẫu cấu hình evidence

Để audit, tổ chức cần biết **ai đang tin ai, trong phạm vi nào và vì sao**. Một bảng trust registry có thể gồm:

| Mục | Nội dung cần ghi |
| --- | --- |
| **trust_id / owner** | Liên kết ổn định với tenant/partner và người chịu trách nhiệm. |
| **protocol + flow/profile** | OIDC Code + PKCE, SAML SP-initiated hoặc profile khác đã duyệt. |
| **issuer/entityID và client/SP** | Nguồn phát hành, đối tượng nhận, endpoints và key source được xác minh. |
| **claims/assurance contract** | Subject, các thuộc tính được phép, MFA/reauthentication context nếu cần. |
| **account binding và role mapping** | Cách liên kết tài khoản và cấp quyền, phiên bản luật. |
| **sessions/provisioning** | Deprovisioning, logout, refresh và trách nhiệm bên nào. |
| **validation/monitoring evidence** | Test run, config diff, alert và thời kỳ được kiểm tra. |
| **exceptions/incidents** | Các sai lệch, quyết định, hạn xử lý và retest. |

### YAML mẫu minh họa, không chứa thông tin xác thực thật

~~~yaml
trust_id: FED-INVOICE-TENANT-A-001
tenant_id: tenant-a
partner_name: Example Enterprise A
protocol: OIDC
profile: authorization_code_with_pkce
relying_party:
  client_registration: invoice-tenant-a
  redirect_uri: "https://invoice.example.invalid/login/oauth2/code/tenant-a"
identity_provider:
  trusted_issuer: "https://idp-a.example.invalid"
  metadata_source: "https://idp-a.example.invalid/.well-known/openid-configuration"
  key_source_policy: "Only verified discovery metadata for trusted issuer"
token_requirements:
  validate:
    - issuer
    - signature_and_allowed_algorithm
    - audience_and_authorized_party_when_applicable
    - expiration_and_time_conditions
    - login_transaction_state
    - nonce_if_used_or_required_by_profile
identity_binding:
  local_key:
    - verified_tenant_id
    - verified_issuer
    - verified_subject
  auto_link_by_email: false
  jit_provisioning: invitation_and_owner_approval
authorization:
  role_mapping_source: approved-tenant-a-map
  default_access: deny_except_explicitly_granted
  object_tenant_enforcement: application_resource_layer
assurance_contract:
  high_risk_actions_require_fresh_authentication: true
  method_and_freshness_mapping: approved-idp-contract
session_and_lifecycle:
  deprovisioning: event_sync_and_local_session_control
  logout: verify_actual_supported_flows
control_owner_role: Federation Control Owner
risk_owner_role: Identity and Access Risk Owner
evidence:
  - "restricted://federation/trust-registry/example"
  - "restricted://federation/tests/oidc-negative-cases"
  - "restricted://federation/reviews/account-binding"
known_gaps:
  - "Legacy SAML portal assessed in separate scope"
review_triggers:
  - issuer_or_signing_key_policy_change
  - claims_or_role_mapping_change
  - new_tenant_or_account_linking_flow
  - security_incident_or_deprovisioning_failure
~~~

Mọi domain, ID, đường dẫn, owner role và kết quả là **giả định học tập**. Domain **example.invalid** cố ý không đại diện cho dịch vụ thực. Mẫu này là **hồ sơ governance/evidence**, không phải tệp cấu hình Spring có thể dùng trực tiếp. Trong hệ thống thật phải kiểm chứng giá trị của mọi endpoint, metadata, client và yêu cầu protocol theo phiên bản đã triển khai.

## 19. Evidence cần có để khẳng định Federation được kiểm soát

Một chương trình assurance cần tách **design effectiveness** và **operating effectiveness**:

- **Design effectiveness:** nếu Federation hoạt động đúng như kiến trúc, có giải quyết kịch bản rủi ro và yêu cầu đã nêu không? Có cơ chế xác minh issuer/client/subject, hạn token, session, role và tenant hay không?
- **Operating effectiveness:** những controls đó có **được áp thực tế** trên tenant, IdP, clients, thời kỳ và phiên bản cần đánh giá không? Có evidence khi lỗi, key rotation, deprovisioning hay thay đổi policy không?

### Claim – Argument – Evidence (CAE)

**Claim:** “Trong các tenant và luồng OIDC thuộc phạm vi, Invoice SaaS chỉ tạo phiên từ assertions của IdP được phê duyệt cho đúng client/tenant; liên kết tới đúng local account và áp dụng phân quyền theo đối tượng.”

**Argument:** “Trust registry giới hạn issuer/client, OIDC library xác minh protocol, login context được bảo vệ, account binding dùng trusted identity key, role mapping theo allowlist, API enforcement và negative tests được thực hiện.”

**Evidence:** registry có phê duyệt, config/metadata ở runtime, kết quả protocol validation, test federation chéo tenant, account-linking tests, ma trận quyền, log đăng nhập đã che dữ liệu, release/deploy evidence, các ngoại lệ và kết quả retest.

### Ma trận control → test → evidence

| Requirement/control | Test cần thực hiện | Evidence phù hợp |
| --- | --- | --- |
| **FED-TRUST-01:** chỉ trust IdP được duyệt. | Đưa issuer không hợp lệ, tenant sai, metadata thay ngoài quy trình. | Trust registry, config diff, negative test, audit thay đổi. |
| **FED-TOKEN-02:** validate token/assertion. | Sai chữ ký, audience, issuer, hết hạn, replay, sai transaction. | SDK/config version, integration test, log từ chối. |
| **FED-LINK-03:** account linking đúng người. | Subject/email collision, rehire, đổi IdP, account chưa link. | Mapping design, test cases, audit liên kết và approval. |
| **FED-AUTHZ-04:** quyền theo tenant/object. | Truy cập dữ liệu tenant khác, claim admin giả, export/batch. | Access matrix, API/worker tests, policy audit. |
| **FED-ASSURANCE-05:** điều kiện xác thực phù hợp rủi ro. | Không có MFA khi bắt buộc, auth quá cũ, step-up. | IdP contract, kết quả test xác thực và claim mapping. |
| **FED-SESSION-06:** phiên/thu hồi có kiểm soát. | Logout, session expiry, deprovision/role revoke khi session mở. | Session test, JML events, đo thời gian mất quyền. |
| **FED-KEY-07:** quản lý vòng đời trust/keys. | Key rotation, unknown key, cert hết hạn, IdP outage. | Metadata review, test rotation, incident runbook. |
| **FED-LOG-08:** audit và monitoring. | Login success/denied, mapping denied, trust change và mất log. | Event contract, log samples, monitoring health, alert test. |

### Thế nào là bằng chứng yếu?

**Screenshot nút “SSO Enabled”** chỉ cho biết một phần cấu hình tại thời điểm chụp. Nó không chứng minh token được kiểm tra issuer/audience, role mapping đúng, user không còn quyền sau khi nghỉ, hay đường SAML khác có an toàn tương đương.

**Một login thành công** chứng minh đường happy path chạy được; để đánh giá bảo mật phải có **negative tests và lỗi giả lập**. Một token sai chữ ký bị từ chối chưa đủ chứng minh token **đúng chữ ký nhưng sai audience** cũng bị từ chối.

**Báo cáo từ IdP** có thể hữu ích nhưng RP cần tự kiểm tra trách nhiệm của mình, đặc biệt session, local account binding và authorization trên dữ liệu.

## 20. Quality, coverage, provenance và thời kỳ đánh giá

Evidence Federation có thể nhanh lỗi thời khi khách hàng đổi IdP, client hoặc role mapping. Vì vậy cần các tiêu chí:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Coverage** | Có bao nhiêu tenant/IdP, clients, protocol profiles, đường login và tài khoản đặc quyền trong phạm vi? |
| **Relevance** | Evidence kiểm tra đúng claim về issuer, binding, session hoặc quyền hay chỉ cho thấy login thành công? |
| **Freshness** | Kết quả có đúng release, thư viện, metadata, key và trust registry đang chạy? |
| **Completeness** | Population có bỏ sót local account, IdP khác, broker, đường SAML cũ hoặc tài khoản break-glass? |
| **Provenance** | Ai/công cụ nào tạo test report, nguồn cấu hình và log gốc ở đâu, timestamp thế nào? |
| **Integrity** | Hiện vật có được bảo vệ khỏi sửa/xóa trái phép, có dấu vết truy cập và phiên bản? |
| **Repeatability** | Có token synthetic, test setup, expected/observed và cách tái tạo an toàn? |
| **Confidentiality** | Evidence có loại bỏ access token, session cookie, key hay PII không cần thiết? |
| **Limits** | Các đường ngoài scope, vấn đề chưa test, lỗi parser hoặc thiếu log có được nêu? |

### Point-in-time và period-of-time

Một lần kiểm tra issuer/client tại thời điểm audit có thể chứng minh trạng thái cấu hình **tại mốc đó**, không tự chứng minh **trong cả quý** mọi lần đổi metadata đều được phê duyệt. Nếu muốn kết luận về quá trình, cần history của trust changes, key rotation, deprovisioning, log monitoring và hồ sơ exception trong kỳ.

### Đếm coverage đúng mẫu số

Một báo cáo “10/10 tenants có SSO PASS” không hợp lệ nếu có thêm tenant thứ 11 đang dùng local login hoặc một khách hàng có **hai IdP và fallback SAML** không được thống kê. Cần đối chiếu population từ tenant registry, IdP connections, client registrations và luồng truy cập thực tế.

## 21. Incident response cho Federation

Các sự cố liên quan Federation thường có **blast radius** lớn vì một IdP hoặc broker phục vụ nhiều ứng dụng.

### Kịch bản 1: Signing key nghi bị lộ

Rủi ro là bên khác có thể tạo assertion/token được RP chấp nhận nếu có đủ điều kiện. Cần phối hợp IdP và RP:

1. Xác minh phạm vi key, issuer, clients và thời gian có khả năng bị lộ.
2. Hạn chế/thu hồi trust vào key bị nghi ngờ theo runbook có thẩm quyền.
3. Xoay vòng key và metadata từ nguồn đáng tin, kiểm tra chấp nhận khóa mới và từ chối khóa không hợp lệ.
4. Đánh giá sessions/tokens đã được cấp, khả năng cần vô hiệu hóa phiên, log và điều tra tác động.
5. Kiểm thử các RP liên quan, lưu evidence và xác định residual risk.

Không dùng cách **tắt kiểm tra chữ ký hoặc bỏ issuer validation** như biện pháp duy trì dịch vụ.

### Kịch bản 2: IdP ngừng hoạt động

Tác động có thể là người dùng không tạo được phiên mới, trong khi các RP sessions hiện hữu vẫn hoạt động. Tùy phân loại nghiệp vụ, tổ chức cần xác định:

- Tiêu chí chấp nhận rủi ro mất đăng nhập mới.
- Chế độ hoạt động các phiên đang mở, giới hạn thời gian/đặc quyền.
- Break-glass có kiểm soát để duy trì chức năng thiết yếu nếu được phê duyệt.
- Quy trình thông báo, hỗ trợ khách hàng và kiểm tra lại trust khi IdP phục hồi.

**Không tự động fallback sang password yếu hoặc IdP khác** nếu chưa có thiết kế kiểm soát và được phê duyệt; fallback là một đường xác thực độc lập phải có threat model và evidence riêng.

### Kịch bản 3: Gán sai local account hoặc sai tenant

Ưu tiên chặn/thu hồi quyền nhầm, bảo toàn audit events, xác định phiên/dữ liệu đã tiếp cận, đánh giá tác động khách hàng và sửa mapping root cause. Sửa email hiển thị không đủ; cần xử lý **binding records, active sessions, cached permissions và các đường API/export**.

## 22. Trách nhiệm và RACI trong chương trình Federation

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Federation control owner / IAM owner** | Định nghĩa trust policy, cấu hình IdP/RP, vòng đời metadata/keys, tiêu chí review và evidence. |
| **RP application owner** | Account binding, session, role mapping, authorization theo tenant/object, triển khai và kiểm thử. |
| **Customer/partner IdP owner** | Quản trị danh tính, xác thực, các attributes theo hợp đồng, thay đổi khóa và phản hồi sự cố IdP. |
| **Data/business owner** | Xác định dữ liệu, quyền, tác động nếu gán sai tenant hoặc account. |
| **Security architect / threat modeling lead** | Review trust boundaries, giao thức, profile và kịch bản rủi ro. |
| **Security assurance / assessor** | Kiểm tra thiết kế/vận hành, coverage, evidence quality và sai lệch. |
| **Risk owner** | Quyết định xử lý hoặc chấp nhận residual risk trong thẩm quyền. |
| **Operations / incident response** | Giám sát, xử lý login outage, account abuse, compromise và khôi phục theo runbook. |
| **Legal/privacy/compliance** | Xác định yêu cầu với dữ liệu cá nhân, đối tác, log, hợp đồng và thông báo khi áp dụng. |

### RACI ví dụ

**R** = thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = thông báo.

| Hoạt động | Federation owner | RP owner | Partner IdP owner | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Duyệt trust contract và issuer/client | **A/R** | C | C | C | I |
| Kiểm tra subject-account/tenant binding | C | **A/R** | C | C | I |
| Định nghĩa claim/role mapping và object authz | C | **A/R** | C | C | I |
| Quản lý vòng đời signing keys phía IdP | C | I | **A/R** | C | I |
| Kiểm thử độc lập và kết luận evidence | C | C | C | **A/R** | I |
| Chấp nhận residual risk thuộc thẩm quyền | C | C | C | C | **A/R** |

RACI là minh họa cho một hợp đồng B2B. Đơn vị sở hữu IdP của khách hàng có thể không nằm trong RACI nội bộ của nhà cung cấp SaaS; khi đó phải **ghi rõ ranh giới trách nhiệm theo hợp đồng và đầu mối liên hệ**, thay vì giả định nhà cung cấp SaaS có thể tự sửa IdP của khách hàng.

## 23. Continuous Federation Assurance trong SDLC

Federation trust không chỉ được kiểm tra một lần tại thời điểm onboarding. Các nguồn thay đổi liên tục gồm thư viện SDK, IdP metadata, key rotation, khách hàng mới, role mapping, session policy và quy trình provisioning.

~~~mermaid
flowchart TD
    A["Inventory partners / trust / data flows"] --> B["Security requirements + risk scenarios"]
    B --> C["Protocol, identity binding và authorization controls"]
    C --> D["CI tests + config / trust verification"]
    D --> E["Production telemetry + evidence"]
    E --> F{"Claim đạt trong phạm vi?"}
    F -- "Không" --> G["Finding / incident / remediation"]
    G --> H["Retest + residual risk review"]
    H --> C
    F -- "Có" --> I["Time-scoped assurance conclusion"]
    I --> J["New IdP / key / claim / tenant / SDK change"]
    J --> B
~~~

### Quy trình theo thời điểm

| Giai đoạn | Hoạt động | Bằng chứng |
| --- | --- | --- |
| **Thiết kế** | Xác định actor, trust, flow, data, requirements, MFA/step-up và provisioning. | Threat model, trust registry draft, claim contract. |
| **Onboarding IdP** | Xác minh partner, issuer, client, endpoints, certificates, account linking. | Approval, metadata validation, negative tests. |
| **Phát triển** | Dùng SDK được duy trì; kiểm tra identity mapping và authorization. | Code review, regression tests, dependency evidence. |
| **CI/CD** | Kiểm thử protocol/role mapping, cấm thay đổi trust ngoài quy trình. | Test runs, config diff, review và deploy ID. |
| **Vận hành** | Giám sát login outcomes, key errors, callback errors, deprovision/session drift. | Security events, dashboards, alert tests, JML reconciliation. |
| **Audit/review** | Đối chiếu population, negative tests, kết quả thay đổi/ngoại lệ. | Evidence pack, findings, retest, conclusion có phạm vi. |
| **Incident** | Khóa/thu hồi trust bị ảnh hưởng, điều tra account binding, xử lý sessions. | Incident timeline, evidence protected, risk decisions. |

### Trigger đánh giá lại không nên bỏ qua

- IdP issuer/entityID hoặc nguồn metadata thay đổi.
- Signing key/certificate rotation, expiration, nghi compromise.
- Client ID, redirect URI, ACS endpoint hoặc protocol profile thay đổi.
- Thêm tenant, broker hoặc đường login local/fallback.
- Thay group/role claim mapping, subject identifiers, account linking.
- Thay yêu cầu MFA/step-up, timeouts, sessions hoặc deprovisioning.
- Vulnerability của SDK, thư viện JWT/XML, hoặc trust policy mới.
- Phát hiện access cross-tenant, account takeover, login CSRF hoặc token replay.
- Bằng chứng kiểm thử cũ không còn phản ánh release/production.

### Chỉ số theo dõi

| Chỉ số | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Trusted connections inventory coverage** | Tỷ lệ issuer/client/tenant connections được quản trị và có owner. | Inventory thiếu sẽ tạo tỷ lệ 100% giả. |
| **Trust config drift** | Các thay đổi issuer/key/redirect/claims ngoài quy trình. | Không có alert nếu collector không quan sát được. |
| **Protocol negative test coverage** | Bao nhiêu flow/tenant/client đã được test sai issuer/audience/state/replay. | Happy path PASS không thay negative tests. |
| **Account linking exceptions** | Số collisions, manual approvals, account recovery bất thường. | Một trường hợp có tác động lớn hơn số lượng thống kê. |
| **Deprovision propagation time** | Thời gian từ trigger đến quyền/phiên thật sự bị vô hiệu theo yêu cầu. | IdP disable event không tự là mốc RP hết quyền. |
| **Key rotation success / failure** | Khả năng thay khóa không bỏ validation và không gây outage vượt mục tiêu. | Rotation test cần xét client và phiên bản thật. |
| **Federated login denial / anomalous rate** | Hỗ trợ phát hiện sai config hoặc tấn công. | Nhiều denial có thể do lỗi IdP; cần triage và context. |
| **Open findings / expired exceptions** | Theo dõi các đường trust chưa đủ bằng chứng hoặc quá hạn. | Acceptance không đồng nghĩa control hiệu quả. |

## 24. Ngoại lệ, bằng chứng thiếu và residual risk

Một khách hàng có thể dùng IdP cũ chưa hỗ trợ flow hoặc thuộc tính cần thiết. RP có thể chưa có SLO hoàn chỉnh, hoặc chưa thể nhận deprovisioning event. Những khoảng trống này phải được **ghi nhận và quyết định minh bạch**.

Hồ sơ ngoại lệ cần ghi:

1. **Trust/tenant/client ID** và security requirement chưa đạt.
2. **Threat scenario**, dữ liệu/người dùng trong phạm vi và hậu quả dự kiến.
3. **Current controls** đang hoạt động với bằng chứng phù hợp.
4. **Giới hạn kỹ thuật**, ví dụ chưa có logout callback hoặc không nhận tín hiệu độ mới MFA.
5. **Compensating controls** nếu có và bằng chứng chúng giảm rủi ro ra sao.
6. **Owner khắc phục, deadline, target state, kế hoạch test lại**.
7. **Risk owner hoặc người có thẩm quyền** quyết định với scope, expiry và review triggers.

**Current residual risk** là rủi ro còn lại với các controls đã hoạt động; **target residual risk** là mức dự kiến sau kế hoạch chưa được kiểm chứng. Một lời hứa “quý sau sẽ nâng cấp IdP” không làm current risk giảm.

Không phải yêu cầu pháp lý/hợp đồng nào cũng có thể được miễn trừ chỉ bằng chữ ký nội bộ. Khi nghĩa vụ bên thứ ba hoặc dữ liệu nhạy cảm được đề cập, phải tham vấn chủ thể có thẩm quyền.

## 25. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “SSO đăng nhập được nghĩa là Federation an toàn.” | Happy path không chứng minh token validation, linking, tenant isolation và lifecycle. |
| “Token có chữ ký là đủ.” | Cần issuer, audience, thời gian, binding và đúng người nhận/giao dịch. |
| “OAuth 2.0 tự là đăng nhập người dùng.” | OAuth 2.0 chủ yếu giải quyết ủy quyền; OIDC bổ sung layer xác thực. |
| “ID Token có thể gửi tới API như access token.” | API phải dùng credential/token đúng audience và purpose theo thiết kế. |
| “Email là ID duy nhất ổn định.” | Email đổi hoặc được tái cấp; linking cần issuer/sub và trust context đúng. |
| “Issuer xác thực đủ để biết tenant.” | Một issuer có thể phục vụ nhiều tenant; phải kiểm tra tenant binding. |
| “IdP gửi admin thì SaaS phải cho admin.” | RP cần mapping được duyệt và authorization trên tài nguyên. |
| “IdP có MFA nên mọi thao tác của RP đều đạt assurance cao.” | Cần kiểm tra phương pháp, thời điểm, ngữ nghĩa claims và step-up khi cần. |
| “Đăng xuất IdP nghĩa là mọi phiên đã biến mất.” | RP session và vòng đời thu hồi có thể độc lập, phải kiểm tra end-to-end. |
| “Deprovisioning tại IdP là đủ.” | Local sessions, API keys, user mapping và quyền ở RP cần được xét. |
| “Metadata qua HTTPS nào cũng đáng tin.” | Nguồn metadata/keys phải được đăng ký và kiểm soát trust. |
| “Khi IdP lỗi, bỏ verify signature để người dùng vẫn đăng nhập.” | Đây là hạ control nghiêm trọng; cần runbook khả dụng được phê duyệt. |
| “Mọi token sai phải luôn có cùng một lỗi.” | Response có thể khác theo protocol, nhưng không tiết lộ thông tin nhạy cảm hoặc chấp nhận sai. |
| “Screenshot SSO enabled đủ làm evidence.” | Cần test, cấu hình thực, population, phiên bản, time period và giới hạn. |
| “Cấu hình đúng hôm nay chứng minh cả quý đều đúng.” | Cần change history, monitoring và evidence theo thời kỳ. |

## 26. Checklist thực hành đánh giá Federation

1. **Scope:** mọi tenant/IdP, client/SP, broker, protocol flow và local fallback đã được kiểm kê?
2. **Trust:** mỗi issuer/entityID và metadata/keys có nguồn, owner, approval và expiry rõ?
3. **Binding:** login transaction gắn đúng client/tenant; subject mapping không dựa email đơn thuần?
4. **Protocol:** chữ ký, issuer, audience, thời gian, callback/recipient, state, PKCE, nonce/InResponseTo/replay được kiểm tra theo flow?
5. **Claims:** các attributes/MFA signals có hợp đồng ý nghĩa, nguồn đáng tin và allowlist?
6. **Authorization:** role mapping có least privilege, có test object/tenant, SoD và export/batch?
7. **Sessions:** cookie, fixation, lifetime, step-up, logout, deprovision và token/session revocation được kiểm chứng?
8. **Lifecycle:** JIT/SCIM/manual invitation và JML có owner, xử lý lỗi đồng bộ và audit?
9. **Incident/availability:** key compromise, rotation, IdP outage và account takeover có runbook diễn tập?
10. **Audit:** security events có source, trust/tenant, principal, result, correlation mà không chứa token/secret?
11. **Evidence:** có tests cả negative cases, nguồn, release, phạm vi, thời kỳ và giới hạn?
12. **Governance:** findings, evidence gaps, ngoại lệ, remediation, retest và residual risk có quyết định có thẩm quyền?

## 27. Bài tập và gợi ý giải

### Bài tập A — Token hợp lệ nhưng sai audience

Một ID Token có chữ ký hợp lệ của IdP A nhưng aud dành cho ứng dụng CRM. Invoice SaaS nhận và tạo phiên vì nó chỉ kiểm tra chữ ký.

**Gợi ý:** Đây là lỗi **token audience validation / token substitution**. RP phải từ chối nếu audience không dành cho OIDC client đã đăng ký; xem issuer, transaction binding, expiry và các claim khác. Evidence gồm negative test với token sai audience, cấu hình validator và log từ chối.

### Bài tập B — Hai nhân viên có cùng email

Nhân viên cũ của A chuyển sang B và sau đó dùng IdP B với email trùng tài khoản SaaS cũ. RP tự login vào tài khoản thuộc tenant A.

**Gợi ý:** Lỗi **account linking dựa vào email** và tenant binding. Cần khóa federation từ issuer/subject tin cậy cùng tenant context, quy trình chuyển/đổi IdP có approval và kiểm tra quyền cũ; điều tra dữ liệu đã truy cập và thu hồi session sai.

### Bài tập C — IdP phát claim role “admin”

Khách hàng B cấu hình một custom claim admin, còn RP ánh xạ mọi admin thành PlatformAdmin.

**Gợi ý:** Không tin claim như quyền tuyệt đối. Phải ràng buộc theo IdP/tenant, contract và mapping được duyệt; hạn chế quyền quản trị nền tảng riêng với tenant admin; kiểm thử claim giả, thiếu và giá trị mới.

### Bài tập D — MFA có ở IdP nhưng giao dịch nguy hiểm không step-up

Người dùng đã xác thực nhiều giờ trước. SaaS cho đổi tài khoản nhận tiền dựa trên session còn sống và claim cho biết người đó từng sử dụng MFA.

**Gợi ý:** Phải xác định requirement về **độ mới và phương pháp xác thực cho hành động**; có thể yêu cầu reauthentication/step-up, kiểm tra auth_time và tín hiệu assurance có nghĩa đã thỏa thuận. Không suy ra MFA vẫn đủ mới chỉ vì session còn hoạt động.

### Bài tập E — Khóa ký mới làm đăng nhập thất bại

IdP thay signing key. RP không lấy được metadata mới nên đội vận hành đề nghị bỏ kiểm tra chữ ký 24 giờ.

**Gợi ý:** Không bỏ validation. Dùng incident runbook, nguồn JWKS/metadata tin cậy, chính sách xoay vòng phù hợp; kiểm tra key mới và loại khóa cũ theo thỏa thuận, theo dõi availability và bảo vệ trust.

### Bài tập F — Disable tại IdP nhưng RP session còn sống

Nhân viên nghỉ việc bị khóa ở IdP, nhưng vẫn truy cập Invoice SaaS bằng cookie đã nhận trước đó.

**Gợi ý:** IdP deactivation không tự xóa session RP. Cần thiết kế JML/deprovision, local session expiration/revocation, chính sách revalidation và negative tests với phiên cũ; đo thời gian mất quyền ở từng đường.

### Bài tập G — SAML assertion được dùng lại

Một ứng dụng SAML nhận lại assertion trước đó và tạo phiên mới, dù assertion không gắn với AuthnRequest hiện tại.

**Gợi ý:** Cần kiểm tra expiry, InResponseTo theo flow, SubjectConfirmation, recipient/audience, replay cache và xử lý IdP-initiated flow nếu được cho phép. Không chỉ kiểm tra chữ ký rồi tái dùng assertion.

### Bài tập H — Dashboard báo 100% SSO đạt

Nhóm kiểm thử 12 kết nối OIDC, tất cả đều login thành công. Sau đó phát hiện một cổng SAML legacy và một local admin login không nằm trong danh sách.

**Gợi ý:** Population không đầy đủ và tests chỉ kiểm tra happy path; kết luận phải giới hạn scope. Cần kiểm kê tất cả flows, đánh giá SAML/local fallback, negative cases và các điểm liên kết/ủy quyền thực tế.

## Kết luận

**Federation** giúp các hệ thống tin cậy kết quả xác thực và thuộc tính danh tính giữa các miền, nhưng đồng thời tạo ra rủi ro ở **trust configuration, token/assertion validation, subject-account linking, tenant binding, claims, authorization, phiên đăng nhập và vòng đời tài khoản**. OIDC/SAML cung cấp cơ chế trao đổi và kiểm chứng; tính an toàn phụ thuộc cách chúng được cấu hình và cách RP sử dụng thông tin đã xác minh. Trong **SECURITY_SECURITY_ASSURANCE**, chỉ có cơ sở kết luận một Federation control hiệu quả khi **claim gắn với phạm vi cụ thể, có negative tests, cấu hình hiện hành, audit trail, evidence chất lượng, owner, xử lý ngoại lệ, retest và đánh giá residual risk liên tục**. Cần chứng minh **đúng danh tính, đúng nguồn tin cậy, đúng tenant, đúng quyền và đúng thời điểm**, không chỉ chứng minh rằng người dùng đăng nhập SSO thành công.
