# Trust relationship trong Federation: thiết lập và quản trị quan hệ tin cậy giữa các miền danh tính

Một nhân viên có thể dùng tài khoản doanh nghiệp để đăng nhập vào nhiều ứng dụng SaaS mà không cần tạo và quản lý mật khẩu riêng tại từng ứng dụng. Một đối tác cũng có thể đăng nhập cổng cộng tác bằng danh tính do chính tổ chức đối tác quản lý. Điều này hoạt động nhờ **federation (liên kết danh tính)**: ứng dụng hoặc một miền danh tính chấp nhận thông tin xác thực do **bên phát hành được tin cậy** cung cấp, sau khi kiểm tra đúng giao thức và chính sách.

Nền tảng của federation là **trust relationship – quan hệ tin cậy**. Đây không phải lời khẳng định chung rằng “hai hệ thống tin nhau”, mà là **một thỏa thuận kỹ thuật và quản trị có giới hạn**: bên nào được phát hành thông tin, phát hành cho ai, loại thông tin gì, được xác minh bằng khóa/metadata nào, giới hạn thời gian và những điều kiện nào khiến thông tin không còn được chấp nhận.

Bài học thuộc chương **Federation** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi đổi vai trò hoặc chấm dứt quan hệ. Bài này liên kết quan hệ tin cậy với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và việc giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Giải thích quan hệ tin cậy trong federation và phân biệt **tin nguồn xác thực** với **cho phép truy cập tài nguyên**.
- Nhận diện vai trò IdP/SP trong SAML và OpenID Provider/Relying Party trong OpenID Connect.
- Liệt kê các thông số cần xác minh để thiết lập trust trong **SAML 2.0** và **OIDC**.
- Phân tích rủi ro khi tin sai issuer, audience, chữ ký, endpoint, ánh xạ chủ thể hoặc thuộc tính.
- Thiết kế quy trình tạo, thay đổi, rà soát, xoay khóa và chấm dứt trust gắn với vòng đời JML.
- Xây dựng bằng chứng kiểm toán và kiểm tra quyền truy cập thực tế sau sự kiện thu hồi trust hoặc Leaver.

## 1. Trust relationship là gì?

Trong federation, một bên tin cậy một bên khác **trong phạm vi đã cấu hình**, chẳng hạn tin rằng IdP của doanh nghiệp có thể xác thực nhân viên và phát hành một assertion hoặc ID token mà ứng dụng được phép kiểm tra.

Quan hệ tin cậy thường phải trả lời rõ:

1. **Trustor (bên tin cậy)** là hệ thống nào? Ví dụ ứng dụng SaaS.
2. **Trusted party (bên được tin cậy)** là ai? Ví dụ IdP của doanh nghiệp.
3. **Bằng chứng được chấp nhận** là gì? SAML assertion đã ký hoặc OIDC ID token hợp lệ.
4. **Bằng chứng dành cho ai?** Audience, client ID, entity ID và endpoint phải được ràng buộc đúng.
5. **Khóa và metadata nào có hiệu lực?** Danh sách khóa công khai, chứng chỉ ký, thuật toán được cho phép và nguồn cấu hình tin cậy.
6. **Danh tính nào được ánh xạ?** Issuer kết hợp subject identifier nào đại diện đúng tài khoản nội bộ?
7. **Điều gì được phép sau xác thực?** Điều kiện provisioning, role, thuộc tính, trạng thái tài khoản và chính sách truy cập tại ứng dụng.
8. **Khi nào trust kết thúc?** Thay đổi hợp đồng, phát hiện xâm nhập, đóng tenant, xoay khóa hoặc chấm dứt tích hợp.

**Trust relationship không có nghĩa mọi tuyên bố của bên phát hành đều đủ để cấp mọi quyền.** Ứng dụng có thể chấp nhận rằng người dùng đã xác thực tại IdP nhưng vẫn từ chối truy cập nếu người đó không có tài khoản hợp lệ, không thuộc nhóm được phép, bị Leaver hoặc không đáp ứng yêu cầu bảo mật.

### 1.1. Trust có giới hạn, không mặc nhiên bắc cầu

Giả sử ứng dụng A tin IdP B; IdP B lại sử dụng xác thực từ IdP C. Không thể tự suy rằng A trực tiếp tin mọi assertion của C. A phải xác minh **bằng chứng do bên phát hành đã được cấu hình** cung cấp và hiểu các tuyên bố về nguồn, phương thức xác thực hoặc mức bảo đảm theo hợp đồng đã thống nhất.

Trong mô hình nhiều tầng hoặc broker, hệ thống trung gian có thể chịu trách nhiệm phát hành token mới và ánh xạ danh tính. Cần có ranh giới trách nhiệm rõ ràng; **trust không tự lan truyền vô hạn qua chuỗi hệ thống**.

## 2. Federation khác SSO, provisioning và authorization như thế nào?

Các khái niệm liên quan nhưng không thay thế nhau:

| Khái niệm | Mục đích chính | Câu hỏi tiêu biểu |
| --- | --- | --- |
| **Federation** | Chấp nhận thông tin xác thực hoặc thuộc tính danh tính từ miền tin cậy khác. | Ứng dụng có thể tin IdP nào, với điều kiện nào? |
| **SSO – Single Sign-On** | Cho phép người dùng đăng nhập nhiều ứng dụng mà không phải xác thực lại ở từng ứng dụng, theo thiết kế phiên. | Người dùng có phải nhập credential riêng cho từng ứng dụng không? |
| **Authentication** | Kiểm chứng quyền kiểm soát danh tính được khai báo. | Ai đã được xác thực và qua phương thức nào? |
| **Provisioning / SCIM** | Tạo, liên kết, cập nhật, vô hiệu hóa tài khoản và nhóm. | Tài khoản ở ứng dụng đích có tồn tại và đúng trạng thái không? |
| **Authorization – RBAC/ABAC** | Quyết định hành động và tài nguyên được phép. | Danh tính này được xem hoặc sửa dữ liệu nào? |
| **Identity lifecycle – JML** | Quản trị sự kiện gia nhập, chuyển vai trò và rời tổ chức. | Khi quan hệ làm việc đổi, tài khoản và quyền phải thay đổi thế nào? |

Ví dụ, ứng dụng dùng SAML SSO có thể tin IdP nhưng **không tự động nhận sự kiện nhân viên đã nghỉ** nếu chỉ xác thực lại khi người dùng truy cập. SCIM hoặc một API deprovision riêng có thể giúp ứng dụng nhận thay đổi tài khoản trước lần đăng nhập tiếp theo. Ngược lại, SCIM tạo tài khoản không tự thiết lập trust SAML/OIDC hoặc chứng minh người dùng đã xác thực.

## 3. Những bên tham gia quan hệ tin cậy

### 3.1. Trong SAML 2.0

- **Identity Provider (IdP):** xác thực chủ thể và phát hành SAML assertion về sự kiện xác thực/thuộc tính.
- **Service Provider (SP):** ứng dụng cần đăng nhập, tiếp nhận và kiểm tra SAML response/assertion.
- **SAML metadata:** mô tả entity ID, endpoint, khóa/chứng chỉ và khả năng giao thức để các bên cấu hình trust.
- **Assertion Consumer Service (ACS):** endpoint của SP tiếp nhận SAML response.

Một SP phải biết rõ **IdP nào được chấp nhận**, phản hồi có dành cho SP và ACS chính xác không, chữ ký có hợp lệ không, thời hạn và ràng buộc yêu cầu có phù hợp không.

### 3.2. Trong OpenID Connect (OIDC)

- **OpenID Provider (OP):** hệ thống xác thực và phát hành ID token; thường là một IdP.
- **Relying Party (RP):** ứng dụng sử dụng thông tin xác thực OIDC.
- **Issuer:** định danh duy nhất cho OP trong ngữ cảnh liên kết; RP cần cấu hình issuer được phép.
- **Discovery document và JWKS:** metadata và tập khóa công khai dùng cho cấu hình và kiểm tra chữ ký, **chỉ được tin sau khi nguồn issuer đã được cấu hình/đánh giá**.
- **Client ID, redirect URI và audience:** ràng buộc một phiên đăng nhập với đúng ứng dụng nhận kết quả.

OIDC được xây dựng trên OAuth 2.0 nhưng có mục tiêu xác thực danh tính người dùng. **ID token dùng để xác thực tại RP không được đối xử như access token để gọi API**; API cần kiểm tra access token theo yêu cầu của resource server, issuer, audience, scope và chính sách riêng.

### 3.3. Bên sở hữu quan hệ ngoài giao thức

Ngoài IdP/SP hoặc OP/RP, doanh nghiệp cần có **owner kỹ thuật**, **owner nghiệp vụ**, đơn vị quản lý đối tác và bên chịu trách nhiệm hợp đồng/bảo mật. Một tích hợp vẫn chạy được về mặt giao thức nhưng **không còn owner hợp lệ** là quan hệ tin cậy cần được rà soát, không phải mặc nhiên duy trì.

## 4. Một luồng đăng nhập federated SSO

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as SaaS / RP hoặc SP
    participant IDP as IdP / OP
    participant IAM as IAM / policy / directory
    U->>RP: Yêu cầu vào ứng dụng
    RP->>IDP: Yêu cầu đăng nhập theo trust đã cấu hình
    IDP->>IAM: Kiểm tra danh tính, trạng thái, MFA và chính sách
    IAM-->>IDP: Kết quả xác thực/chính sách
    IDP-->>RP: SAML response hoặc OIDC flow/result
    RP->>RP: Kiểm issuer, chữ ký, audience, thời hạn và request binding
    RP->>RP: Ánh xạ tài khoản, kiểm entitlement và quyền ứng dụng
    RP-->>U: Tạo phiên ứng dụng hoặc từ chối
~~~

Sơ đồ mô tả logic tổng quan, **không phải từng thông điệp HTTP thực tế**. Với OIDC Authorization Code Flow, RP nhận authorization code qua trình duyệt rồi đổi code tại token endpoint, thường dùng PKCE; ID token không nhất thiết được gửi trực tiếp từ OP tới RP trên cùng đường trình duyệt như một SAML response.

**Điểm quyết định:** ở bước xác minh, ứng dụng không nên chỉ hỏi “chữ ký có hợp lệ không?” mà còn phải kiểm **token do đúng issuer được tin cậy phát hành, dành cho đúng ứng dụng, còn thời hạn và liên kết với yêu cầu đăng nhập hợp lệ**.

## 5. Thiết lập trust trong SAML: cần kiểm tra gì?

### 5.1. Các thông số cốt lõi

| Thông số | Vai trò trong trust | Sai sót thường gặp |
| --- | --- | --- |
| **IdP Entity ID / Issuer** | Xác định đúng IdP phát hành. | Chấp nhận assertion của issuer khác vì dùng chung tên miền hoặc cấu hình quá rộng. |
| **SP Entity ID / Audience** | Ràng buộc assertion dành cho SP cụ thể. | Assertion phát cho ứng dụng A được ứng dụng B chấp nhận. |
| **ACS URL / Recipient / Destination** | Xác minh điểm nhận phản hồi. | Cấu hình endpoint không chặt hoặc cho phép redirect không được phê duyệt. |
| **IdP signing certificate/key** | Kiểm tra chữ ký theo bộ khóa được tin cậy. | Không xác minh chữ ký hoặc chấp nhận khóa từ nguồn không kiểm soát. |
| **Signature requirements** | Quy định phần nào của response/assertion bắt buộc được ký. | Chỉ kiểm chữ ký trên một phần không đúng đối tượng được sử dụng, dẫn tới nguy cơ signature wrapping. |
| **Conditions / NotBefore / NotOnOrAfter** | Hạn chế thời gian assertion có hiệu lực. | Chấp nhận assertion cũ, không kiểm giới hạn thời gian hoặc lệch đồng hồ quá rộng. |
| **InResponseTo / request correlation** | Liên kết phản hồi với yêu cầu SP phát ra khi luồng yêu cầu điều đó. | Chấp nhận phản hồi không có quan hệ với phiên đăng nhập hợp lệ. |
| **SubjectConfirmationData** | Ràng buộc chủ thể, recipient, thời hạn và thông số bearer confirmation. | Chỉ đọc NameID nhưng bỏ qua điều kiện subject confirmation. |
| **NameID và thuộc tính** | Liên kết người dùng liên miền. | Dùng email làm khóa duy nhất hoặc ánh xạ sang tài khoản khác. |
| **Allowed bindings / endpoints** | Chỉ chấp nhận cách truyền và endpoint hợp lệ. | Mở endpoint thừa hoặc đổi cấu hình không qua phê duyệt. |

Ví dụ cấu hình ở mức khái niệm (không phải metadata SAML chuẩn đầy đủ):

~~~yaml
federationType: SAML2
spEntityId: "https://portal.example.test/saml/sp"
idpEntityId: "https://login.partner.example.test/saml/idp"
acsUrl: "https://portal.example.test/saml/acs"
requireSignedAssertions: true
validateAudience: true
validateRecipientAndDestination: true
enforceAssertionTimeConditions: true
allowedSigningKeysRef: "trust-store://partner-idp/signing-keys"
accountMapping: "issuer-plus-persistent-subject"
~~~

Giá trị trên là **cấu hình minh họa**, không có khóa/chứng chỉ thật và không thay thế yêu cầu cụ thể của một thư viện hay nhà cung cấp SAML. Tính bảo mật phụ thuộc cách thư viện thực sự xác minh assertion/response, tính toàn vẹn metadata, thuật toán và giao thức đã được đánh giá.

### 5.2. Chứng chỉ ký và chứng chỉ mã hóa

**Chữ ký** giúp SP kiểm tra tính xác thực và toàn vẹn dữ liệu theo khóa công khai đã tin cậy. **Mã hóa assertion** có thể bảo vệ nội dung khỏi người không có private key giải mã, khi triển khai cần thiết. Hai chức năng khác nhau:

- Mã hóa không thay thế kiểm tra chữ ký, issuer, audience hoặc thời gian.
- Chữ ký hợp lệ không đảm bảo assertion được bảo mật khi đi qua nơi có thể đọc dữ liệu.
- Việc trust một chứng chỉ không phải lúc nào dựa trên hệ thống CA công khai: nhiều federation SAML **pin khóa/chứng chỉ ký qua metadata hoặc cấu hình đã phê duyệt**.
- Khi thay khóa, SP cần biết khóa nào còn được phép kiểm và trong khoảng thời gian nào, tránh ngắt dịch vụ hoặc kéo dài trust với khóa đã bị lộ.

## 6. Thiết lập trust trong OIDC: issuer, client và token validation

Một RP cần đăng ký với OP và biết các endpoint, định danh, khóa và chính sách được phép. **OIDC Discovery** hỗ trợ đọc metadata nhưng **không có nghĩa mọi URL discovery đều đáng tin**.

| Thành phần | Điều cần xác nhận |
| --- | --- |
| **Issuer (\`iss\`)** | Khớp chính xác với issuer được cấu hình và ngữ cảnh OP tin cậy. |
| **Audience (\`aud\`)** | ID token dành cho đúng RP/client; kiểm \`azp\` khi ngữ cảnh token yêu cầu. |
| **Signature / \`alg\` / JWKS** | Chỉ dùng thuật toán được cho phép, khóa lấy từ issuer đã tin cậy; không tin \`alg\` hoặc URL khóa do token tự chỉ định một cách tùy tiện. |
| **\`exp\`, \`iat\` và điều kiện thời gian** | Token nằm trong khoảng hợp lệ, clock skew có giới hạn phù hợp. |
| **\`nonce\` (khi được sử dụng/yêu cầu)** | Liên kết ID token với yêu cầu xác thực để giảm nguy cơ replay/token substitution. |
| **\`state\`** | Liên kết phản hồi authorization với phiên giao dịch, phòng CSRF và các dạng trộn luồng. |
| **Authorization Code + PKCE** | Bảo vệ việc đổi authorization code, đặc biệt với public client; nên áp dụng theo mô hình OAuth/OIDC hiện đại. |
| **Redirect URI** | Danh sách URI được đăng ký và so khớp chặt; không mở redirect tùy ý. |
| **\`sub\`** | Định danh chủ thể theo issuer; có thể là public hoặc pairwise subject tùy cấu hình. |
| **Authentication context / \`acr\`, \`amr\`** | Chỉ dùng khi OP công bố và RP hiểu đúng ý nghĩa mức bảo đảm/phương thức xác thực. |

Ví dụ cấu hình ứng dụng ở mức khái niệm:

~~~json
{
  "protocol": "OIDC",
  "trustedIssuer": "https://idp.partner.example.test",
  "clientId": "workforce-portal-rp",
  "allowedRedirectUris": [
    "https://portal.example.test/oidc/callback"
  ],
  "responseType": "code",
  "requirePkce": true,
  "allowedIdTokenAlgorithms": ["RS256"],
  "jwksSource": "trusted-issuer-discovery",
  "subjectMapping": "iss-plus-sub",
  "authorizationPolicy": "local-role-and-account-state"
}
~~~

Đây là **ví dụ thiết kế**, không phải bộ tham số đủ để triển khai OIDC hay khuyến cáo mọi hệ thống đều phải dùng RS256. Thuật toán, client authentication, token handling và endpoint phải theo tiêu chuẩn bảo mật hiện hành và khả năng hệ thống.

### 6.1. Những lỗi token validation nguy hiểm

1. **Chỉ kiểm chữ ký mà bỏ qua issuer:** một token hợp lệ từ OP không được tin cậy có thể được chấp nhận nhầm.
2. **Không kiểm audience:** ID token của ứng dụng A bị ứng dụng B chấp nhận.
3. **Tin thuật toán/đường lấy khóa từ input không kiểm soát:** có thể dùng khóa hoặc cơ chế xác minh không được phê duyệt.
4. **Không kiểm thời hạn và nonce/state phù hợp:** tăng nguy cơ replay hoặc tráo đổi phản hồi.
5. **Dùng email để quyết định tài khoản:** email có thể đổi/tái sử dụng và claim \`email_verified\` có ý nghĩa phụ thuộc issuer.
6. **Dùng ID token làm access token:** token xác thực dành cho RP bị trình tới API không có audience/scope phù hợp.
7. **Tin claims đặc quyền mà không có hợp đồng:** giá trị \`admin=true\` hoặc \`groups\` từ nguồn không đủ thẩm quyền dẫn đến nâng quyền.

Không được cố sửa các lỗi này bằng cách tự viết bộ kiểm tra JWT/SAML thiếu hiểu biết về giao thức. Nên sử dụng thư viện/bộ SDK đã được duy trì, cấu hình validation nghiêm ngặt và có thử nghiệm bảo mật phù hợp.

## 7. Thiết lập và quản trị trust qua metadata, khóa và endpoint

Quan hệ tin cậy không phải cấu hình làm một lần rồi bỏ quên. Mỗi trust phải có **chủ sở hữu, phạm vi, phiên bản, thay đổi có phê duyệt và kế hoạch chấm dứt**.

### 7.1. Danh mục trust

| Trường quản trị | Nội dung |
| --- | --- |
| \`trustId\` | ID duy nhất cho quan hệ tin cậy. |
| \`protocol\` | SAML2, OIDC hoặc cơ chế đã được phê duyệt khác. |
| \`trustedIssuer/entityId\` | Miền danh tính được phép phát hành. |
| \`consumerId\` | SP/RP/ứng dụng nhận bằng chứng. |
| \`businessOwner\`, \`technicalOwner\` | Người/nhóm chịu trách nhiệm nghiệp vụ và kỹ thuật. |
| \`purpose\`, \`contractRef\` | Mục đích kết nối và căn cứ quan hệ với bên ngoài. |
| \`metadataSource\`, \`signingKeysRef\` | Nguồn metadata và khóa/chứng chỉ đang được tin cậy. |
| \`allowedEndpoints\`, \`allowedAlgorithms\` | Danh sách endpoint/thuật toán đã phê duyệt. |
| \`subjectMappingPolicy\` | Quy tắc liên kết chủ thể liên miền với tài khoản nội bộ. |
| \`claimPolicy\`, \`accessPolicy\` | Thuộc tính nào được chấp nhận và quyền nào có thể phát sinh. |
| \`reviewAt\`, \`expiresAt\` (nếu có) | Lịch rà soát hoặc kết thúc quan hệ. |
| \`state\`, \`lastVerifiedAt\` | Trạng thái trust và lần kiểm tra gần nhất. |

Không để **metadata URL hoặc JWKS URL thay đổi tùy ý** mà không kiểm soát. Hệ thống cần biết điểm lấy metadata thuộc issuer đã phê duyệt, dùng TLS và phương pháp xác thực nguồn thích hợp, theo dõi thay đổi khóa/endpoint và tránh đưa URL do người dùng cung cấp vào cơ chế tải metadata nhạy cảm.

### 7.2. Vòng đời trust

~~~mermaid
stateDiagram-v2
    [*] --> PROPOSED: Yêu cầu tích hợp
    PROPOSED --> REVIEWED: Đánh giá bên tin cậy và phạm vi
    REVIEWED --> ACTIVE: Phê duyệt + cấu hình + kiểm thử
    ACTIVE --> CHANGING: Xoay khóa / đổi endpoint / claim policy
    CHANGING --> ACTIVE: Kiểm thử và xác minh hoàn tất
    ACTIVE --> SUSPENDED: Sự cố / mất thẩm quyền / rủi ro cao
    SUSPENDED --> ACTIVE: Xác minh + phê duyệt khôi phục
    ACTIVE --> TERMINATED: Hết hợp đồng / ngừng tích hợp
    SUSPENDED --> TERMINATED: Chấm dứt trust
    TERMINATED --> [*]
~~~

Các trạng thái là **mô hình nội bộ minh họa**. Một sản phẩm có thể hỗ trợ disable trust ngay hoặc chỉ hỗ trợ xóa cấu hình. Khi chấm dứt, phải xác định rõ ảnh hưởng tới **phiên đã tạo, token còn hiệu lực, tài khoản ứng dụng và API credential**.

### 7.3. Xoay khóa an toàn

Khi IdP/OP thay khóa ký:

1. Nguồn có thẩm quyền thông báo hoặc cung cấp metadata/JWKS mới bằng kênh được tin cậy.
2. Bên nhận tải và xác minh tập khóa/metadata theo chính sách, không tự chấp nhận một issuer mới.
3. Tùy giao thức và khả năng provider, có thể cho phép **giai đoạn chồng lấn khóa cũ và mới** được kiểm soát để không làm gián đoạn đăng nhập.
4. Kiểm tra chữ ký từ khóa mới và phản ứng khi gặp khóa không được phê duyệt.
5. Sau thời gian chuyển đổi hợp lệ, loại khóa cũ khỏi danh sách được tin cậy.
6. Nếu **khóa bị lộ**, xử lý như sự cố an ninh: có thể cần thu hồi khẩn, vô hiệu token/assertion liên quan và tránh tiếp tục tin khóa cũ vì mục tiêu tương thích.

**JWKS cache hoặc metadata cache** có thể khiến một số RP/SP tiếp tục dùng khóa cũ. Cần theo dõi thời gian làm mới, sự nhất quán giữa vùng triển khai và khả năng ứng cứu khi khóa bị lộ; không chỉ sửa cấu hình ở một nút.

## 8. Ánh xạ danh tính qua các miền tin cậy

Giả sử tổ chức A có nhân viên An, ứng dụng tại tổ chức B chấp nhận IdP A. Ứng dụng B phải xác định tài khoản nội bộ nào tương ứng **đúng người An**.

### 8.1. Khóa định danh ổn định

Một cách liên kết OIDC thường dựa trên **cặp \`iss\` + \`sub\`**. Trong SAML, sử dụng NameID bền vững hoặc định danh đã được thỏa thuận theo hợp đồng tích hợp, cộng với issuer/entity ID. Không dùng **họ tên** hoặc **email** làm khóa duy nhất:

- Email có thể đổi do tên, tên miền hoặc tái tuyển dụng.
- Một địa chỉ email có thể được tái cấp cho người khác theo thời gian.
- OIDC \`sub\` có thể là **pairwise subject** khác nhau giữa các RP, theo cấu hình provider.
- SAML NameID có thể thay đổi tùy format, NameID policy và cách IdP phát hành.

Ví dụ mapping nội bộ:

~~~json
{
  "trustId": "partner-a-to-portal-b",
  "externalIssuer": "https://idp.partner.example.test",
  "externalSubject": "opaque-user-id-0073",
  "localSubjectId": "external-person-2081",
  "localAccountId": "portal-user-891",
  "mappingStatus": "VERIFIED",
  "verifiedAt": "2026-11-20T09:30:00Z"
}
~~~

Mã định danh trên chỉ là ví dụ; giá trị \`externalSubject\` không cần tiết lộ thông tin người dùng. Nếu mapping mơ hồ hoặc xảy ra thay đổi issuer/subject, **không tự ghép tài khoản bằng email** mà phải dùng quy trình xác minh và phê duyệt liên kết.

### 8.2. Just-in-Time (JIT) provisioning và SCIM

Một ứng dụng có thể tạo tài khoản khi người dùng **đăng nhập federated lần đầu (JIT)** hoặc được cấp phát từ trước bằng **SCIM**. Hai cơ chế có khác biệt quan trọng:

| JIT provisioning | SCIM / lifecycle provisioning |
| --- | --- |
| Tạo/liên kết tài khoản khi có lần đăng nhập hợp lệ. | Có thể tạo/cập nhật/vô hiệu hóa tài khoản chủ động, trước khi người dùng đăng nhập. |
| Thuận tiện khi số người dùng thay đổi hoặc ít đăng nhập. | Hữu ích khi cần chuẩn bị quyền, quản lý nhóm và offboarding đúng hạn. |
| Nếu chỉ dựa vào đăng nhập, ứng dụng khó biết Leaver **trước lần đăng nhập tiếp theo**. | Có thể truyền \`active=false\` và cập nhật thuộc tính/nhóm theo khả năng provider. |
| Có nguy cơ tạo nhầm tài khoản nếu mapping claim không chặt. | Có nguy cơ tạo trùng nếu \`externalId\`, \`id\` và ID nội bộ không được đối chiếu đúng. |

**SCIM trust là quan hệ tích hợp cấp phát tài khoản**, có credential, endpoint, quyền và owner riêng; nó không tự thiết lập hoặc thay thế trust xác thực SAML/OIDC. Ngược lại, có thể đã ngừng trust đăng nhập nhưng tài khoản ở ứng dụng vẫn hoạt động nếu chưa thực hiện deprovision.

## 9. Trust relationship và authorization: không tin claims quá mức

Một IdP có thể phát hành claim về department, job title, group hoặc mức xác thực. **Bên nhận phải quyết định có dùng claim nào, với ý nghĩa và thẩm quyền gì**.

### 9.1. RBAC

Với **Role-Based Access Control (RBAC)**, ứng dụng có thể ánh xạ một số group hoặc role claims đã được thỏa thuận sang vai trò nội bộ:

~~~text
External IdP assertion:
  issuer = IdP đối tác đã tin cậy
  subject = mã chủ thể ổn định
  group = partner-readers
           |
           v
Local policy mapping đã phê duyệt
           |
           v
Ứng dụng cấp role: portal-read-only
~~~

Không nên cho phép IdP đối tác tự tuyên bố \`admin=true\` để nhận quyền quản trị trừ khi **chính sách quản trị đặc quyền** và hợp đồng thẩm quyền đã xác nhận rõ điều đó. Dùng **allowlist** các giá trị có ý nghĩa, gắn phiên bản chính sách và từ chối mặc định những claim ngoài thỏa thuận.

### 9.2. ABAC

Với **Attribute-Based Access Control (ABAC)**, có thể đánh giá đồng thời thuộc tính được tin cậy, tài nguyên và ngữ cảnh:

~~~text
ALLOW if
    federationTrust.state == "ACTIVE"
    AND subject.localAccountState == "ACTIVE"
    AND subject.partnerAccessApproved == true
    AND request.action == "read"
    AND resource.partnerId == subject.partnerId
    AND resource.classification <= subject.approvedScope
~~~

Đây là **giả mã mô hình**. \`partnerAccessApproved\` phải có nguồn phê duyệt đáng tin cậy; không nên suy ra chỉ từ một claim tự khai hoặc email của người dùng. Với phân quyền dữ liệu nhạy cảm, cần kiểm soát tính mới của thuộc tính và xử lý khi token hoặc bộ nhớ đệm giữ claim cũ.

### 9.3. Xác thực mạnh chưa đủ để cấp quyền

Một đối tác đăng nhập bằng passkey/MFA tại IdP của họ có thể đã được xác thực an toàn, nhưng tổ chức tiếp nhận vẫn cần đánh giá:

- Quan hệ đối tác hoặc hợp đồng có còn hiệu lực không?
- Chủ thể có được sponsor/owner nội bộ phê duyệt không?
- Tài khoản ứng dụng hiện có đang ACTIVE hay đã bị khóa?
- Phạm vi dữ liệu, môi trường và thời hạn truy cập có đúng không?
- Có yêu cầu step-up, điều kiện thiết bị hoặc hạn chế phiên bổ sung không?

**Trust identity ≠ trust every authorization claim**. Phân biệt này ngăn việc đưa toàn bộ quyết định truy cập ra ngoài ranh giới quản trị.

## 10. Trust relationship xuyên Joiner–Mover–Leaver

### 10.1. Joiner: thiết lập quyền dựa trên nguồn đã tin cậy

Khi nhân viên hoặc đối tác mới tham gia:

1. Nguồn có thẩm quyền xác nhận người/quan hệ và thời điểm bắt đầu.
2. IAM liên kết subject ID ổn định với issuer/subject federation thích hợp.
3. Xác định ứng dụng có cần tài khoản tạo trước qua SCIM hay tạo JIT khi đăng nhập.
4. Chỉ cấp role/entitlement theo quyền đã được duyệt và giới hạn thời gian.
5. Kiểm tra IdP có áp dụng phương thức xác thực phù hợp, MFA và các điều kiện cần thiết không.
6. Kiểm tra trust configuration không cho tài khoản ở issuer khác hoặc audience khác truy cập.
7. Ghi lại chứng cứ nguồn, mapping, phê duyệt và kết quả tài khoản/quyền thực tế.

### 10.2. Mover: thuộc tính và phạm vi quyền thay đổi

Khi nhân viên đổi bộ phận, manager, vai trò hoặc chuyển dự án, **issuer/subject có thể giữ nguyên** trong khi quyền và thuộc tính thay đổi. IAM cần:

- Cập nhật các thuộc tính được phát hành hoặc dùng nội bộ theo nguồn có thẩm quyền.
- Tính lại RBAC/ABAC; thu hồi quyền cũ không còn phù hợp.
- Đồng bộ SCIM/API và nhóm trong ứng dụng nếu có.
- Kiểm tra claim trong token/phiên cũ có thể còn hiệu lực đến khi hết hạn.
- Rà soát quyền ngoại lệ, tài khoản admin, các ủy quyền và dịch vụ do người đó quản lý.

Không nên hiểu đổi manager là phải tạo trust mới; ngược lại, không được bỏ qua quyền tồn dư chỉ vì trust SSO vẫn hoạt động bình thường.

### 10.3. Leaver: thu hồi quyền của một chủ thể khác với thu hồi trust của cả IdP

Khi **một nhân viên của tổ chức đối tác nghỉ việc**, thường cần **thu hồi khả năng truy cập của riêng chủ thể**, không phải xóa trust giữa hai tổ chức nếu những người khác còn cần sử dụng.

| Phạm vi thay đổi | Biện pháp phù hợp | Điều cần xác minh |
| --- | --- | --- |
| **Một người rời đối tác** | Khóa tại IdP nguồn; vô hiệu hóa tài khoản/role ứng dụng đích qua SCIM/API hoặc quy trình chủ động, thu hồi phiên/token. | Tài khoản ứng dụng không còn truy cập được; không còn quyền cục bộ, PAT hoặc session tồn dư. |
| **Một người chuyển vai trò** | Đồng bộ thuộc tính, nhóm và entitlement, xử lý quyền cũ. | Quyền thực tế khớp vai trò mới, không tích lũy quyền. |
| **Một ứng dụng ngừng tích hợp** | Tắt/xóa trust của ứng dụng đó; thu hồi client secret, signing trust, token, quyền và tài khoản liên quan. | Ứng dụng không còn chấp nhận assertion/token của tích hợp cũ. |
| **Toàn bộ quan hệ với đối tác chấm dứt** | Thu hồi trust issuer/entity, API cấp phát, tài khoản đối tác, quyền, credential và phiên liên quan. | Không còn đường federation hoặc API ngoài ý muốn, có kiểm soát dữ liệu cần lưu. |
| **IdP đối tác bị xâm nhập** | Áp dụng kế hoạch cô lập trust, khóa/giới hạn truy cập, xoay khóa và điều tra token/assertion đáng ngờ. | Các RP/SP và cache thực thi thay đổi, ghi nhận giới hạn token còn hiệu lực. |

**Vô hiệu hóa IdP user không tự đảm bảo mọi ứng dụng đã xóa phiên cục bộ.** Tương tự, xóa trust có thể ngăn *đăng nhập mới* nhưng chưa thu hồi được **session cookie, access token, PAT hoặc API key** đã phát hành. Cần đánh giá từng đường truy cập theo tính năng của hệ thống.

## 11. Trust giữa các tổ chức: trách nhiệm hai phía

Trong federation B2B, một bên có thể quản lý mật khẩu/MFA và xác minh nhân sự, bên kia quản lý dữ liệu, quyền và điều kiện sử dụng. Cần xác định rõ trong thỏa thuận vận hành:

| Câu hỏi | Bên chịu trách nhiệm cần được chỉ rõ |
| --- | --- |
| Ai xác minh người dùng mới và duy trì trạng thái làm việc? | Nguồn nhân sự/IdP của đối tác hoặc mô hình được chấp thuận. |
| Ai yêu cầu MFA và ở mức nào? | IdP phát hành cùng các yêu cầu mà SP/RP kiểm tra/áp dụng được. |
| Ai được quyền bật quyền ở ứng dụng đích? | Owner nghiệp vụ và chính sách truy cập tại bên nhận. |
| Ai thông báo Leaver/Mover và trong thời hạn nào? | Quy trình JML hai bên, không chỉ kỳ vọng “đối tác tự xử lý”. |
| Ai xử lý sự cố IdP, key bị lộ và token sai? | Đầu mối kỹ thuật/CSIRT hai bên, kênh liên lạc khẩn và quyền cô lập trust. |
| Ai xoay signing key/chứng chỉ và kiểm tra metadata? | Owner IdP/OP và SP/RP, cùng kế hoạch thay đổi. |
| Ai có thể xem log xác thực hoặc dữ liệu người dùng? | Phân quyền, căn cứ, thời hạn lưu và yêu cầu bảo vệ dữ liệu. |
| Khi hợp đồng kết thúc, ai xóa/giữ dữ liệu và tài khoản? | Owner ứng dụng/dữ liệu, IAM và tuân thủ theo chính sách. |

Nếu không có thỏa thuận về **thông báo Leaver và xử lý tài khoản đích**, một đối tác có thể đã khóa người dùng ở IdP của họ nhưng ứng dụng doanh nghiệp vẫn giữ tài khoản local hoạt động hoặc token cũ.

## 12. Các lỗi cấu hình trust thường gặp

| Sai sót | Hậu quả có thể xảy ra | Biện pháp phòng vệ |
| --- | --- | --- |
| **Tin issuer quá rộng** | Token/assertion từ nguồn ngoài danh sách được phép có thể được chấp nhận. | Allowlist issuer/entity ID theo từng trust và tenant. |
| **Không kiểm audience** | Token dành cho ứng dụng A được dùng ở B. | Validation audience/client ID hoặc SP entity ID nghiêm ngặt. |
| **Bỏ qua chữ ký hoặc kiểm sai đối tượng** | Assertion/token bị giả mạo hoặc bị tráo nội dung. | Thư viện chuẩn, kiểm đúng cấu trúc/chữ ký, test signature wrapping cho SAML khi phù hợp. |
| **Tin JWK/URL khóa do token tự cung cấp** | Hệ thống lấy khóa từ nguồn do kẻ tấn công kiểm soát. | Giới hạn khóa theo issuer đã tin cậy và metadata có kiểm soát. |
| **Không kiểm thời hạn/replay** | Assertion hoặc token cũ được dùng lại ngoài chính sách. | Kiểm exp, NotBefore, NotOnOrAfter, nonce, InResponseTo, state theo giao thức. |
| **Redirect/ACS quá rộng** | Phản hồi đăng nhập bị chuyển sai nơi hoặc luồng bị trộn. | Danh sách endpoint được phê duyệt và so khớp chặt. |
| **Ánh xạ bằng email** | Tài khoản bị gắn nhầm khi email đổi/tái sử dụng. | Issuer + subject bền vững, xác minh mapping và lịch sử. |
| **Tin claim \`admin\` từ nguồn ngoài** | Nâng quyền dù bên phát hành không có thẩm quyền quyết định quyền nội bộ. | Chính sách role/claim mapping cụ thể và phê duyệt đặc quyền. |
| **Không rà soát khóa cũ** | Khóa đã lộ hoặc đã hết dùng vẫn được chấp nhận. | Vòng đời signing keys/JWKS và xử lý compromise. |
| **Chỉ khóa SSO, bỏ qua session và SCIM** | Leaver còn tài khoản/quyền tại ứng dụng đích. | Deprovision đa hệ thống, thu hồi phiên/token, đối soát. |
| **Trust không có owner** | Không ai chịu trách nhiệm khi đổi metadata, đối tác nghỉ hợp đồng hoặc xảy ra sự cố. | Trust inventory, owner, rà soát và lịch kết thúc. |
| **Dùng ID token thay access token** | API tiếp nhận sai loại token và áp dụng audience/scope không đúng. | Phân tách validation theo loại token, RP và resource server. |

**Cấu hình trust an toàn không chỉ là một checkbox “Enable SSO”.** Nó là tập ràng buộc định danh, mật mã, endpoint, phiên, thuộc tính, vòng đời và trách nhiệm có thể kiểm chứng.

## 13. Tình huống thực tế: đối tác chuyển nhân sự nhưng ứng dụng vẫn chấp nhận phiên cũ

**Bối cảnh:** doanh nghiệp B cung cấp cổng theo dõi dự án cho nhân viên của đối tác A. Cổng dùng OIDC SSO từ IdP A, còn tài khoản và quyền dự án được quản lý tại B. Nhân viên Mai của A chuyển khỏi dự án ngày 01/12 và không còn được phép xem dữ liệu dự án tại B.

| Mốc giả định | Bằng chứng | Kết luận |
| --- | --- | --- |
| **30/11** | A thông báo Mover, quyền dự án của Mai hết hiệu lực 01/12. | B có căn cứ lên lịch thu hồi quyền. |
| **01/12 08:00** | A cập nhật nhóm/vai trò; Mai vẫn là Employee tại A. | Không nhất thiết khóa IdP của Mai vì người đó còn làm việc. |
| **01/12 08:02** | B nhận cập nhật SCIM/API hoặc xử lý yêu cầu deprovision quyền. | Đã có lệnh thay đổi, chưa đủ kết luận app đã áp dụng. |
| **01/12 08:05** | Cổng B vẫn ghi một phiên ứng dụng dùng claim nhóm cũ. | Có khả năng quyền hoặc phiên tồn dư. |
| **01/12 08:10** | Owner B vô hiệu quyền dự án và thu hồi phiên liên quan; xác minh tại API. | Có bằng chứng thực thi kiểm soát ở bên nhận. |
| **01/12 08:15** | Đối soát tài khoản/role ở B và kiểm tra lịch sử đăng nhập. | Xác minh trạng thái cuối, xác định khoảng truy cập tiềm năng. |

### Phân tích

1. **Trust OIDC với IdP A vẫn hợp lệ** cho những nhân viên khác của đối tác và cả Mai nếu Mai còn được truy cập ứng dụng khác.
2. **Quan hệ dự án của Mai mới là yếu tố phải thu hồi**; chính sách authorization của cổng B phải ngăn Mai xem dữ liệu dự án đã kết thúc.
3. **Claim nhóm trong ID token/phiên cũ** có thể không phản ánh thay đổi HRIS tức thời. Ứng dụng cần có cơ chế cập nhật quyền hiện tại, phiên phù hợp hoặc thu hồi session theo khả năng.
4. Nếu B chỉ dựa vào nhóm cũ trong token lâu hạn, một Mover có thể để lại **privilege creep** dù quá trình federation vẫn xác thực đúng người.
5. Cần truy vết từ sự kiện HRIS A → chính sách đối tác → lệnh đồng bộ → thay đổi role tại B → kiểm chứng API/phiên, với trách nhiệm rõ giữa hai tổ chức.

### Nếu toàn bộ đối tác chấm dứt hợp tác?

Khi hợp đồng với A kết thúc, B không chỉ thu hồi từng role; phải kiểm kê và chấm dứt **trust với issuer A**, client/metadata/khóa liên quan, đường SCIM provisioning, tài khoản và quyền của đối tác, phiên/token còn hoạt động cùng dữ liệu cần giữ theo hợp đồng/quy định. Dữ liệu nghiệp vụ cần lưu **không phải lý do để giữ đường SSO của đối tác hoạt động**.

## 14. Quy trình thay đổi hoặc ngừng một trust relationship

Một thay đổi quan hệ tin cậy cần được kiểm soát như thay đổi an ninh quan trọng:

1. **Khởi tạo:** ghi mục đích thay đổi, phạm vi ứng dụng/tenant, owner, lý do nghiệp vụ và mức độ rủi ro.
2. **Đánh giá:** đối chiếu danh mục trust, user/ứng dụng bị ảnh hưởng, credential, endpoints, claims, quyền và phụ thuộc với workload.
3. **Phê duyệt:** Security, Identity Governance và owner ứng dụng/đối tác thông qua theo chính sách.
4. **Chuẩn bị:** kiểm tra thay đổi metadata, chứng chỉ/JWKS, redirect/ACS, mapping chủ thể và phương án phục hồi an toàn.
5. **Thực thi:** cập nhật từng SP/RP và IdP/OP trong phạm vi, kiểm soát thay đổi song song nếu có nhiều vùng/tenant.
6. **Kiểm thử dương tính:** người dùng hợp lệ từ issuer đúng đăng nhập được và chỉ có quyền theo chính sách.
7. **Kiểm thử âm tính:** token/assertion từ issuer, audience, endpoint, khóa, trạng thái hoặc thời hạn không được phép phải bị từ chối; dùng môi trường và quy trình kiểm thử được ủy quyền.
8. **Xử lý phiên/token:** đánh giá dữ liệu được lưu ở phiên và token đã phát hành; thu hồi khi có cơ chế hỗ trợ, ghi nhận giới hạn còn hiệu lực.
9. **Đối soát:** tài khoản/nhóm/role tại ứng dụng và quyền thực tế ở API phù hợp trạng thái mong đợi.
10. **Bàn giao vận hành:** cập nhật inventory, tài liệu tích hợp, owner, runbook ứng cứu và lịch rà soát.

### 14.1. Xử lý sự cố mất trust

Nếu nghi khóa ký IdP bị lộ hoặc bên phát hành bị xâm nhập, phải ưu tiên **hạn chế khả năng chấp nhận bằng chứng giả**. Tùy rủi ro có thể tạm ngừng federation, thu hẹp issuer/key được chấp nhận, yêu cầu xác thực tăng cường, thu hồi phiên/token và kiểm tra hành động đã diễn ra trong thời gian nghi vấn.

Quy trình cần ghi rõ **thời điểm phát hiện**, các SP/RP đã nhận thay đổi, key/metadata bị ảnh hưởng và các phiên/token có thể còn sống. Không đánh dấu sự cố đã hết chỉ vì thay một chứng chỉ ở IdP; bên nhận có thể vẫn cache khóa cũ hoặc có phiên ứng dụng độc lập.

## 15. Truy vết và kiểm toán quan hệ tin cậy

Federation làm việc qua nhiều miền, nên log của một bên hiếm khi đủ để dựng toàn bộ sự kiện. Cần đối chiếu **nguồn phát hành**, **bên tiêu thụ**, **quyết định quyền** và **trạng thái tại ứng dụng**.

### 15.1. Trường dữ liệu nên lưu

| Trường/bằng chứng | Giá trị kiểm toán |
| --- | --- |
| **\`trustId\`, \`protocol\`, \`configVersion\`** | Biết trust nào được sử dụng và cấu hình lúc sự kiện xảy ra. |
| **Issuer/entity ID và consumer ID** | Chứng minh nguồn và đích nằm trong phạm vi được phê duyệt. |
| **External subject và local subject mapping** | Truy vết đúng chủ thể mà không phụ thuộc email. |
| **Event/correlation/request ID** | Liên kết IdP, gateway, RP/SP và hệ thống quyền. |
| **Authentication outcome và policy version** | Phân biệt đăng nhập thành công, MFA chưa hoàn tất và bị từ chối. |
| **Signing key ID / metadata version** | Xác định khóa dùng để xác minh và thay đổi trust. |
| **Audience / application ID** | Biết token/assertion dành cho ứng dụng nào. |
| **Account/entitlement state** | Kết quả authorization và provisioning liên quan. |
| **Occurred/effective/verified at** | Phân biệt thời điểm phát hành, hiệu lực nghiệp vụ và xác nhận ở đích. |
| **Exception/owner/evidence reference** | Theo dõi sự cố, hệ thống chưa đồng bộ và người xử lý. |

**Không lưu SAML assertion nguyên vẹn, ID/access token, mã xác thực, private key, client secret hay cookie phiên vào log vận hành** chỉ để thuận tiện điều tra. Có thể ghi ID sự kiện, claim tối thiểu hoặc metadata không nhạy cảm theo chính sách. Với dữ liệu định danh liên tổ chức, cần kiểm soát quyền riêng tư, thời hạn lưu và mục đích truy xuất.

### 15.2. Phân biệt “đã xác thực” với “đã được cấp quyền”

Một log của IdP có thể chứng minh một yêu cầu xác thực được xử lý; **không chứng minh** ứng dụng đã cấp quyền thành công hoặc người dùng đã truy cập dữ liệu. Để giải trình một thao tác, cần kết hợp:

1. IdP/OP phát hành assertion hoặc token đúng trust.
2. RP/SP xác minh giao thức và ánh xạ tài khoản.
3. Ứng dụng đánh giá trạng thái, RBAC/ABAC và entitlement.
4. Tài nguyên/API ghi nhận hành động được cho phép hoặc từ chối.
5. Khi có Mover/Leaver, kết quả thu hồi quyền/phiên được xác minh theo phạm vi.

Không thấy log cũng không đủ kết luận không có hoạt động nếu một bên thiếu telemetry hoặc bị chậm đồng bộ.

## 16. Chỉ số đánh giá chất lượng trust

| Chỉ số | Cách đo gợi ý | Rủi ro phát hiện |
| --- | --- | --- |
| **Tỷ lệ trust có owner và mục đích hợp lệ** | Trust đang hoạt động có owner, ứng dụng, căn cứ và kỳ rà soát ÷ tổng trust. | Quan hệ không còn được quản trị. |
| **Tỷ lệ trust đúng cấu hình kiểm tra** | Tích hợp đáp ứng issuer, audience, chữ ký, endpoint và validation thời gian ÷ tích hợp được kiểm tra. | Chấp nhận bằng chứng ngoài phạm vi. |
| **Tỷ lệ tài khoản federated có mapping ổn định** | Tài khoản liên kết bằng subject đáng tin cậy, không dựa duy nhất email ÷ tài khoản liên kết. | Gắn nhầm danh tính. |
| **Thời gian cập nhật signing key/metadata** | Từ thay đổi có thẩm quyền đến khi toàn bộ SP/RP thuộc phạm vi xác nhận. | Khóa cũ còn được tin quá hạn hoặc gián đoạn dịch vụ. |
| **Thời gian thu hồi khi Leaver/Mover** | Từ mốc hiệu lực đến khi quyền và tài khoản đích được xác minh đúng. | Quyền truy cập tồn dư. |
| **Phiên/token còn hiệu lực sau chấm dứt trust** | Số trường hợp được xác minh còn dùng được theo phạm vi kiểm tra. | Trust bị đóng nhưng đường truy cập vẫn còn. |
| **Tỷ lệ ứng dụng có đối soát JML** | App federated có kiểm tra account/entitlement thực tế ÷ tổng app phải xử lý. | SSO hoạt động nhưng provisioning sai. |
| **Tỷ lệ sự kiện có audit trail xuyên miền** | Sự kiện liên kết được nguồn, ứng dụng, quyết định và kết quả ÷ tổng sự kiện trong phạm vi. | Không đủ bằng chứng điều tra. |
| **Số trust quá hạn rà soát hoặc không còn hợp đồng** | Quan hệ ACTIVE nhưng owner/contract/review đã hết hiệu lực. | Duy trì tin cậy khi không còn nhu cầu. |

Không đặt ngưỡng chung cho mọi tổ chức. Chỉ số nên phân theo độ nhạy ứng dụng, loại đối tác, tenant, giao thức và mức độ bao phủ của log. Báo cáo “mọi trust đều an toàn” chỉ có giá trị khi phương pháp và phạm vi kiểm tra được công bố rõ.

## 17. Checklist triển khai và vận hành

1. Đã xác định **trustor, trusted issuer, SP/RP, mục đích, owner và phạm vi ứng dụng/tenant** chưa?
2. Có phân biệt rõ **federation trust**, **SSO session**, **SCIM provisioning** và **authorization** không?
3. Với SAML, có kiểm **issuer, entity ID, audience, ACS/recipient, chữ ký, thời hạn, subject confirmation và request binding** theo giao thức không?
4. Với OIDC, có kiểm đúng **\`iss\`, \`aud\`, chữ ký/JWKS, thời hạn, state/nonce, redirect URI và PKCE** theo luồng được sử dụng không?
5. Metadata, JWKS, signing certificates và thuật toán có được lấy từ **nguồn đã tin cậy**, kiểm soát thay đổi và xoay khóa an toàn không?
6. Có ngăn trust chấp nhận issuer/token của tenant khác, claim đặc quyền không được ủy quyền và mapping tài khoản chỉ dựa vào email không?
7. Có liên kết **issuer + stable subject** hoặc định danh SAML bền vững với đúng chủ thể/tài khoản và xử lý đổi tên, tái tuyển dụng không?
8. Role, group, ABAC claim từ nguồn ngoài có được **đánh giá và ánh xạ theo chính sách nội bộ** thay vì cấp quyền mặc định không?
9. **Joiner** có tài khoản đúng người, đúng thời điểm; **Mover** có thu hồi quyền cũ; **Leaver** có thu hồi phiên, token, tài khoản local và API key theo phạm vi không?
10. SCIM/API deprovision có kết quả được xác minh tại ứng dụng, thay vì chỉ dựa vào IdP login log không?
11. Khi một đối tác ngừng hợp tác, có quy trình chấm dứt trust và xử lý tài khoản, khóa, phiên, entitlement và dữ liệu còn giữ hợp lệ không?
12. Có runbook xử lý signing key bị lộ, metadata sai, clock skew, token replay và sự cố federation chéo tổ chức không?
13. Có thể truy vết từ sự kiện JML tới issuer, RP/SP, mapping, quyết định quyền và hành động ở hệ thống đích mà không ghi raw token/assertion/secret không?
14. Trust inventory, kỳ rà soát, owner kỹ thuật/nghiệp vụ và cảnh báo trust mồ côi có được vận hành thường xuyên không?

**Ghi nhớ:** **Trust relationship trong Federation là sự tin cậy có điều kiện, có phạm vi và có thể thu hồi giữa những bên phát hành và tiêu thụ bằng chứng danh tính.** Một ứng dụng phải kiểm tra **đúng issuer, đúng chữ ký/khóa, đúng audience/endpoint, đúng thời hạn và đúng chủ thể**, rồi áp dụng **authorization riêng** trước khi cấp quyền. Quản trị trust phải đi cùng **Joiner–Mover–Leaver**, đồng bộ tài khoản qua SCIM/API khi phù hợp, xoay khóa, thu hồi phiên/token và đối soát hệ thống đích. Chỉ như vậy federation mới hỗ trợ SSO thuận tiện mà không tạo thêm quyền truy cập tồn dư hoặc vùng tin cậy vượt quá kiểm soát.
