# Federation metadata: cấu hình quan hệ tin cậy giữa các hệ thống IAM

**Federation metadata** là tập thông tin có cấu trúc giúp các bên tham gia **liên kết danh tính (identity federation)** xác định **đối tác là ai, các endpoint giao thức ở đâu, sử dụng những khóa/chứng thư công khai nào và hỗ trợ cơ chế giao tiếp nào**. Với **SAML 2.0**, metadata thường được trao đổi dưới dạng XML chứa định danh thực thể, vai trò IdP/SP, endpoint và chứng thư công khai. Với **OpenID Connect (OIDC)**, thông tin cấu hình của nhà cung cấp thường được xuất bản qua **discovery document** dạng JSON, kết hợp với **JSON Web Key Set (JWKS)** cho các khóa công khai.

Trong một hệ thống **Identity and Access Management (IAM)**, metadata giúp ứng dụng nhận kết quả xác thực từ **Identity Provider (IdP)** một cách có kiểm soát. Tuy nhiên, metadata **không tự chứng minh danh tính của mọi người dùng**, **không thay thế việc xác thực chữ ký/thông điệp thực tế**, **không tự tạo tài khoản** và **không cấp quyền nghiệp vụ**. Nó là một phần của **thiết lập và duy trì ranh giới tin cậy**, cần được xác minh nguồn, cập nhật an toàn và giám sát khi thay đổi.

Bài thuộc chương **Federation** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Khi quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, tổ chức có thể dùng **IdP/SSO** để xác thực, **SCIM/API** để đồng bộ tài khoản và **RBAC/ABAC** để phân quyền. Federation metadata giúp các ứng dụng trao đổi kết quả đăng nhập đúng đối tác; còn việc cập nhật vai trò, thu hồi người dùng, tài khoản dịch vụ và giảm **quyền truy cập tồn dư** vẫn cần các kiểm soát vòng đời và kiểm toán riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **federation metadata** là gì, được dùng ở thời điểm nào và khác những dữ liệu người dùng nào.
2. Phân biệt **IdP/SP metadata của SAML** với **OIDC discovery document, JWKS và client registration**.
3. Nhận diện các trường quan trọng: **entityID, issuer, SSO/ACS endpoint, signing/encryption key, redirect URI, audience** và thuật toán được phép.
4. Mô tả cách thiết lập quan hệ tin cậy ban đầu thay vì nhận metadata tùy ý từ một URL chưa kiểm chứng.
5. Hiểu việc **xoay vòng khóa/chứng thư (key/certificate rollover)**, thời hạn metadata, caching và kiểm tra thay đổi.
6. Phân tích hậu quả khi metadata sai, lỗi thời, bị thay thế hoặc có endpoint/khóa của kẻ tấn công.
7. Thiết kế kiểm tra vận hành, bằng chứng kiểm toán và các bước ứng phó khi thay đổi IdP, SP hoặc ứng dụng.
8. Liên hệ federation metadata với **SSO, MFA, SCIM, RBAC/ABAC, service account** và biến cố **Joiner–Mover–Leaver**.

## 2. Metadata xác lập những gì, và không xác lập những gì?

Một liên kết SSO có ít nhất hai câu hỏi khác nhau:

- **Thiết lập tin cậy:** “Ứng dụng đang hợp tác với IdP nào, endpoint và khóa nào được chấp nhận?”
- **Thực thi đăng nhập:** “Thông điệp xác thực của phiên này có thực sự do IdP đã tin cậy phát hành, dành cho đúng ứng dụng, còn hiệu lực và thuộc đúng giao dịch hay không?”

Federation metadata hỗ trợ câu hỏi thứ nhất. Việc kiểm tra **SAML assertion** hoặc **OIDC ID token**, điều kiện thời gian, đối tượng nhận và trạng thái phiên xử lý câu hỏi thứ hai.

| Thành phần | Dữ liệu hoặc trách nhiệm | Không tự bảo đảm |
|---|---|---|
| **Federation metadata** | Định danh đối tác, endpoint, khóa công khai, cơ chế giao thức | Người dùng đã đăng nhập hợp lệ |
| **Identity proofing** | Cơ sở xác minh người dùng là ai | Có tài khoản và quyền trong mọi ứng dụng |
| **Authentication** | Người dùng/chủ thể chứng minh quyền kiểm soát authenticator | Có quyền đọc mọi dữ liệu |
| **Federation / SSO message** | Kết quả xác thực hoặc claim truyền tới ứng dụng theo giao thức | Tài khoản cục bộ đã provision |
| **SCIM / provisioning** | Tạo, cập nhật, vô hiệu hóa user/group nếu đích hỗ trợ | Mọi phiên/token đã phát hành bị thu hồi |
| **RBAC / ABAC** | Chính sách hành động, tài nguyên, trạng thái và ngữ cảnh | Khóa/chứng thư metadata được xác minh |
| **Audit / reconciliation** | Theo dõi cấu hình, thay đổi, quyền hiệu dụng | Tự động khắc phục sai lệch không có quy trình |

**Ví dụ:** Một ứng dụng nhận được ID token có chữ ký khớp một khóa trong JWKS. Điều đó **chưa đủ** nếu ứng dụng không kiểm tra `iss`, `aud`, thời gian, nonce khi áp dụng và các điều kiện giao thức khác. Tương tự, có SAML metadata của đúng đối tác không có nghĩa ứng dụng được quyền chấp nhận bất kỳ assertion XML nào gửi đến endpoint của mình.

## 3. Các vai trò trong liên kết danh tính

### 3.1. SAML: Identity Provider và Service Provider

- **Identity Provider (IdP):** Xác thực người dùng và phát hành SAML assertion theo quan hệ tin cậy.
- **Service Provider (SP):** Ứng dụng tiêu thụ SAML Response/Assertion và quyết định tạo phiên.
- **IdP metadata:** Mô tả IdP, khóa/chứng thư công khai dùng cho mục đích tương ứng, SSO endpoint, binding và các khả năng hỗ trợ.
- **SP metadata:** Mô tả SP, entityID, Assertion Consumer Service (**ACS**) endpoint, và khi cần có khóa/chứng thư để IdP kiểm tra chữ ký yêu cầu hoặc mã hóa assertion.

**Hai bên phải cấu hình chấp nhận nhau** theo chính sách. Việc SP tự nhập một URL IdP không tạo quan hệ tin cậy an toàn nếu URL và metadata chưa được xác nhận từ nguồn có thẩm quyền.

### 3.2. OIDC: OpenID Provider và Relying Party

- **OpenID Provider (OP):** IdP hỗ trợ OIDC, phát hành ID token và các thông tin liên quan.
- **Relying Party (RP) / OIDC client:** Ứng dụng yêu cầu đăng nhập và kiểm chứng ID token.
- **Discovery metadata:** Mô tả `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri` và các khả năng giao thức.
- **JWKS:** Tập khóa công khai được xuất bản để các bên tiêu thụ kiểm chứng chữ ký/token theo chính sách.
- **Client registration:** Client ID, redirect URI, cách xác thực client và các điều kiện sử dụng được đăng ký với OP. **Discovery document không tự đăng ký một ứng dụng làm client được tin cậy.**

### 3.3. Federation metadata và service account

Trong các hệ thống máy đến máy, metadata của một **authorization server** hoặc thông tin tin cậy của một **workload identity provider** có thể giúp ứng dụng kiểm tra token và endpoint. Dù vậy, không nên coi đây là luồng SSO người dùng: workload phải có **ID, owner kỹ thuật, policy audience/scope, quản lý khóa/credential và vòng đời riêng**.

## 4. So sánh SAML metadata và OIDC discovery

| Tiêu chí | **SAML 2.0 metadata** | **OIDC discovery / JWKS** |
|---|---|---|
| Định dạng | XML | JSON cho discovery; JSON cho JWKS |
| Định danh nhà phát hành | `entityID` của IdP | `issuer` (`iss` trong ID token phải khớp) |
| Định danh ứng dụng | SP `entityID` | `client_id` / audience được đăng ký |
| Điểm đến đăng nhập | `SingleSignOnService` kèm Binding | `authorization_endpoint` |
| Điểm nhận kết quả | `AssertionConsumerService` của SP | `redirect_uri` đã đăng ký cho client |
| Trao đổi token | SAML Response/Assertion và các binding | Authorization code/token endpoint theo flow |
| Khóa công khai | `KeyDescriptor` và chứng thư/khóa tương ứng | `jwks_uri` dẫn đến JWKS; khóa có `kid`, `kty`, v.v. |
| Thuật toán/khả năng | Phụ thuộc metadata/profile và cấu hình tin cậy | `id_token_signing_alg_values_supported` và các trường hỗ trợ |
| Tải/cập nhật | Có thể trao file, URL metadata, aggregate hoặc cấu hình theo nền tảng | Thường tải discovery document và JWKS qua HTTPS từ issuer tin cậy |
| Session/logout | Các endpoint hỗ trợ và cấu hình ứng dụng | Các endpoint/logout feature tùy hỗ trợ |
| Khả năng cấp quyền ứng dụng | Không phải nhiệm vụ của metadata | Không phải nhiệm vụ của discovery/JWKS |

Cả hai đều cần **khởi tạo tin cậy an toàn**, kiểm tra endpoint/khóa, xử lý thay đổi và kiểm chứng thông điệp xác thực. Không nên chọn giao thức chỉ vì một bên cung cấp URL metadata: phải xác nhận yêu cầu ứng dụng, bảo đảm giao thức và khả năng vận hành.

## 5. Cấu trúc một SAML IdP metadata

SAML metadata mô tả một thực thể bằng `EntityDescriptor`. Một IdP thường có `IDPSSODescriptor` và có thể liệt kê một hoặc nhiều endpoint SSO, bindings cùng khóa dùng cho các tác vụ cụ thể.

### 5.1. Ví dụ XML minh họa

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<EntityDescriptor
    xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    entityID="https://login.example.test/saml/idp"
    validUntil="2026-12-31T23:59:59Z">

  <IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>
            BASE64_PUBLIC_CERTIFICATE_PLACEHOLDER
          </ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </KeyDescriptor>

    <NameIDFormat>
      urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
    </NameIDFormat>

    <SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.test/saml/sso"/>
  </IDPSSODescriptor>
</EntityDescriptor>
~~~

**Chỉ là ví dụ để đọc cấu trúc:** Chứng thư `BASE64_PUBLIC_CERTIFICATE_PLACEHOLDER` không hợp lệ và XML không chứa chữ ký metadata; **không thể dùng làm cấu hình thực tế**. Trong hệ thống thật, phải xác minh nguồn/chuỗi tin cậy theo cách thiết kế, thuật toán, khóa, phiên bản và các điều kiện giao thức.

### 5.2. Diễn giải từng thành phần

| Trường hoặc phần tử | Ý nghĩa | Lỗi thường gặp |
|---|---|---|
| `entityID` | Định danh logic của thực thể SAML | Nhầm với địa chỉ endpoint, thay định danh khi đổi host |
| `IDPSSODescriptor` | Công bố vai trò/các khả năng IdP SSO | Đọc nhầm SP metadata là IdP metadata |
| `protocolSupportEnumeration` | Giao thức được công bố | Chấp nhận giao thức không được phép |
| `KeyDescriptor use="signing"` | Chỉ khóa dùng trong tác vụ ký phù hợp | Dùng nhầm khóa mã hóa để kiểm chữ ký |
| `ds:X509Certificate` | Dữ liệu chứng thư/khóa công khai trong metadata | Coi sự hiện diện của chứng thư là bằng chứng nguồn tin cậy |
| `SingleSignOnService` | Endpoint cùng binding nhận yêu cầu SSO | Gửi nhầm binding hoặc endpoint không kiểm chứng |
| `NameIDFormat` | Định dạng định danh subject được hỗ trợ | Dùng email thay định danh ổn định một cách tùy tiện |
| `validUntil` | Giới hạn thời gian hợp lệ của metadata khi được khai báo | Tiếp tục dùng dữ liệu hết hiệu lực vô thời hạn |
| `cacheDuration` (nếu có) | Gợi ý về caching metadata theo cơ chế áp dụng | Coi gợi ý cache là bảo đảm khóa chưa bị thu hồi |

**Quan trọng:** `entityID` là một **định danh**; mặc dù thường có hình thức URI, không nên tự giả định nó là endpoint có thể mở để đăng nhập. Endpoint phải đọc từ phần tử tương ứng và kiểm tra trong cấu hình tin cậy.

## 6. Cấu trúc SAML SP metadata và ACS

Trong SAML, SP cũng có metadata để IdP biết ứng dụng nhận SAML Response ở đâu và, khi có yêu cầu, dùng khóa gì để kiểm tra AuthnRequest hoặc mã hóa assertion.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<EntityDescriptor
    xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://app.example.test/saml/sp">

  <SPSSODescriptor
      AuthnRequestsSigned="true"
      WantAssertionsSigned="true"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">

    <AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://app.example.test/saml/acs"/>
  </SPSSODescriptor>
</EntityDescriptor>
~~~

Đây là **ví dụ cấu trúc rút gọn**, không phải metadata hoàn chỉnh để triển khai thực tế. `AuthnRequestsSigned="true"` tuyên bố SP dự định ký yêu cầu trong cấu hình này, nhưng ví dụ **chưa cung cấp KeyDescriptor** để IdP kiểm chứng chữ ký. Một tích hợp thật phải đáp ứng yêu cầu khóa và policy hai bên.

### 6.1. Những điều SP phải tự kiểm tra

Khi nhận SAML Response/Assertion, SP thường cần kiểm tra các yếu tố phù hợp với profile:

- **Issuer** đúng IdP đã được tin cậy.
- **Chữ ký** ở đúng phần tử được yêu cầu, do khóa được chấp nhận phát hành; chống XML signature wrapping bằng thư viện an toàn.
- **AudienceRestriction** hướng tới đúng SP.
- **Recipient/Destination** và ACS đúng endpoint được phép.
- **Thời gian** như `NotBefore`, `NotOnOrAfter` với dung sai đồng hồ hợp lý.
- **InResponseTo** liên kết với AuthnRequest khi áp dụng; chặn replay.
- **Subject / NameID** được ánh xạ tới identity/account đúng, không tự gộp người theo tên/email.

Chỉ có URL ACS đúng hoặc chứng thư hiện diện trong metadata **không đủ** để bảo đảm assertion hợp lệ.

## 7. OIDC Provider Configuration: discovery metadata

Trong OIDC, ứng dụng có thể truy vấn tài liệu cấu hình do OP công bố. Ví dụ với issuer `https://idp.example.test`, một vị trí discovery thường dùng là:

~~~text
https://idp.example.test/.well-known/openid-configuration
~~~

Với issuer có đường dẫn hoặc các trường hợp khác, cách hình thành địa chỉ discovery phải tuân theo đặc tả và cấu hình thực tế, không tự nối chuỗi tùy tiện.

### 7.1. Ví dụ discovery JSON

~~~json
{
  "issuer": "https://idp.example.test",
  "authorization_endpoint": "https://idp.example.test/oauth2/authorize",
  "token_endpoint": "https://idp.example.test/oauth2/token",
  "jwks_uri": "https://idp.example.test/.well-known/jwks.json",
  "userinfo_endpoint": "https://idp.example.test/oidc/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

Đây là **ví dụ có endpoint giả `example.test`**, không đại diện nhà cung cấp thật. Các trường phải phản ánh khả năng và policy thực tế; một số endpoint hoặc tính năng có thể không được cung cấp.

### 7.2. Các trường quan trọng

| Trường | Vai trò | Kiểm tra thiết kế |
|---|---|---|
| `issuer` | Định danh nhà phát hành OP | Phải đúng với issuer đã tin cậy và `iss` của ID token |
| `authorization_endpoint` | Endpoint khởi tạo đăng nhập/ủy quyền | HTTPS, URL thuộc cấu hình được chấp nhận |
| `token_endpoint` | Đổi authorization code lấy token, các grant phù hợp | Bảo vệ kết nối và client authentication đúng |
| `jwks_uri` | Vị trí công bố bộ khóa công khai | Nguồn đáng tin, chính sách fetch/cache/rotation |
| `response_types_supported` | Kiểu response OP hỗ trợ | Chỉ chọn flow được ứng dụng cho phép |
| `id_token_signing_alg_values_supported` | Thuật toán ký ID token OP công bố | Chỉ chấp nhận giao của khả năng và allowlist bảo mật |
| `subject_types_supported` | Mô hình định danh subject được công bố | Ánh xạ subject ổn định theo chính sách |
| `userinfo_endpoint` | Điểm lấy claim bổ sung khi được sử dụng | Kiểm tra token/scope và ràng buộc subject |
| `end_session_endpoint` (tùy chọn) | Endpoint phục vụ logout nếu có | Không suy ra thu hồi mọi phiên và token |
| `token_endpoint_auth_methods_supported` | Các phương thức client authentication hỗ trợ | Chọn phương thức đã đăng ký và phù hợp khả năng client |

**Discovery không có nghĩa tất cả các phương thức được liệt kê đều an toàn cho ứng dụng.** Client cần cấu hình **allowlist các flow/thuật toán, redirect URI, kiểu client và policy** riêng. Metadata giúp khám phá khả năng của OP; **không tự cho phép downgrade** hoặc bỏ qua giới hạn bảo mật của ứng dụng.

### 7.3. Cẩn trọng với issuer và multi-tenant

Một dịch vụ IdP có thể có nhiều tenant hoặc issuer. Chỉ giống tên miền hoặc thuộc cùng thương hiệu **không đồng nghĩa cùng ranh giới tin cậy**. Ứng dụng cần xác định chính xác issuer nào được phép dùng, cách ánh xạ tenant và subject, trường hợp đăng nhập đối tác nào có thẩm quyền.

Không tin ID token của một issuer khác chỉ vì chữ ký dùng một khóa xuất hiện trên một endpoint cùng nhà cung cấp; việc kiểm tra **issuer, audience, subject, nonce và giao dịch** vẫn bắt buộc theo giao thức.

## 8. JWKS và quản lý khóa công khai

**JSON Web Key Set (JWKS)** là cấu trúc chứa một hoặc nhiều **JSON Web Key (JWK)**. OP có thể xuất bản khóa công khai tại `jwks_uri`; ứng dụng dùng khóa phù hợp để kiểm chứng chữ ký của ID token hoặc token được thiết kế cho việc này.

### 8.1. Ví dụ JWKS rút gọn

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-2026-b",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS_PLACEHOLDER",
      "e": "AQAB"
    }
  ]
}
~~~

**Ví dụ không phải bộ khóa hoạt động**, vì `n` là chuỗi minh họa. Với JWK thật, các trường khóa phải đúng cấu trúc và giá trị mật mã tương ứng; chỉ dữ liệu **khóa công khai** nên được xuất bản ở endpoint JWKS công khai. **Không xuất khóa riêng**, symmetric secret hay credential quản trị trong JWKS công khai.

### 8.2. Vai trò của các trường

- `kty`: Kiểu khóa, ví dụ RSA hoặc EC theo cấu hình.
- `kid`: Định danh giúp lựa chọn khóa ứng viên; **không tự chứng minh tin cậy**.
- `use`: Mục đích sử dụng, ví dụ `sig` cho chữ ký khi được khai báo.
- `alg`: Thuật toán liên quan nếu được khai báo; **không thay thế allowlist** tại client.
- Các tham số khóa công khai như `n`/`e` với RSA dùng cho kiểm chứng chữ ký.

**Cách kiểm chứng đúng:** Ứng dụng chỉ tải khóa từ **JWKS thuộc OP đã tin cậy**, chọn khóa phù hợp, kiểm chứng thuật toán/chữ ký, kiểm tra claim cần thiết rồi mới chấp nhận kết quả. Không lấy một `jku` hoặc URL khóa tùy ý do token chưa được tin cậy cung cấp và tự động tải làm nguồn xác minh.

### 8.3. Metadata không phải nơi lưu private key

- **Signing private key** thuộc bên phát hành và phải được bảo vệ theo quy trình quản lý khóa.
- **Signing public key/certificate** có thể xuất hiện trong metadata hoặc JWKS để đối tác kiểm chứng.
- **TLS certificate** bảo vệ kết nối HTTPS, có vòng đời và cách xác minh khác với khóa ký SAML/JWT.
- **Encryption key** có mục đích khác signing key; phải phân biệt vai trò và hướng sử dụng.

Một endpoint có HTTPS hợp lệ **chưa đủ chứng minh tổ chức đó là IdP mà ứng dụng đã được phép tin cậy**. HTTPS bảo vệ kết nối tới endpoint được truy cập; **định danh và khóa liên kết federation vẫn cần được xác minh với cấu hình tin cậy đã phê duyệt**.

## 9. Federation metadata được sử dụng trong luồng đăng nhập ở đâu?

Metadata thường được nạp/cấu hình **trước khi người dùng đăng nhập** và được cập nhật trong vận hành. Khi có phiên đăng nhập, ứng dụng áp thông tin đã tin cậy để gửi yêu cầu và kiểm chứng kết quả.

~~~mermaid
sequenceDiagram
    autonumber
    actor Admin as IAM / quản trị tích hợp
    participant RP as Ứng dụng RP / SP
    participant OP as IdP / OP
    actor User as Người dùng

    Admin->>RP: Phê duyệt đối tác, issuer/entityID và policy
    RP->>OP: Tải metadata / discovery / JWKS qua kênh được phép
    OP-->>RP: Endpoint, khóa công khai, khả năng giao thức
    RP->>RP: Xác thực nguồn, ràng buộc tin cậy và cấu hình
    User->>RP: Yêu cầu truy cập
    RP->>OP: Yêu cầu xác thực theo giao thức
    OP->>User: Xác thực/MFA khi cần
    User-->>OP: Hoàn tất phương thức được yêu cầu
    OP-->>RP: Kết quả federation
    RP->>RP: Kiểm chữ ký, issuer, audience,\nrequest correlation và thời gian
    RP->>RP: Ánh xạ identity và kiểm tra trạng thái
    RP-->>User: Phiên ứng dụng nếu hợp lệ
~~~

**Giới hạn sơ đồ:** Các trao đổi thực tế có thể đi qua trình duyệt, redirect, POST binding, token endpoint hoặc front-channel; sơ đồ gom các bước để làm rõ mối liên hệ **metadata trước phiên** và **kiểm tra thông điệp trong phiên**.

### Metadata không tự quyết định quyền truy cập nghiệp vụ

Ứng dụng có thể xác thực người dùng qua OIDC/SAML thành công nhưng vẫn phải:

1. Xác định đúng identity/account theo mapping đã phê duyệt.
2. Kiểm tra có account ứng dụng hay cần provisioning hợp lệ không.
3. Tính và thực thi **RBAC/ABAC** dựa trên vai trò, dự án, trạng thái JML, môi trường và tài nguyên.
4. Chặn quyền không còn căn cứ, kể cả khi phiên SSO hoặc ID token vẫn đúng về mặt mật mã.

## 10. Thiết lập tin cậy ban đầu (trust bootstrap)

Bước nguy hiểm nhất có thể là **quyết định tin metadata nào**. Nếu kẻ tấn công thay URL metadata bằng endpoint và khóa của họ, ứng dụng có thể bị dẫn tới một nhà phát hành giả mạo, mặc dù việc kiểm chữ ký đối với **khóa giả mạo đó** vẫn trả về “hợp lệ”.

### 10.1. Quy trình onboarding một đối tác federation

1. **Định danh đối tác:** Xác nhận tổ chức, tenant, SP/IdP và mục đích tích hợp qua nguồn nghiệp vụ có thẩm quyền.
2. **Phê duyệt ranh giới tin cậy:** Xác định `entityID` hoặc `issuer`, endpoint được phép và chính sách mức bảo đảm.
3. **Nhận metadata qua nguồn xác nhận:** URL/file/aggregate được đối chiếu độc lập với thông tin đã phê duyệt, không chỉ dựa email tự khai.
4. **Kiểm tra tính toàn vẹn và nguồn phát hành:** Xác minh chữ ký metadata khi sử dụng signed metadata, chuỗi tin cậy và chứng thư/khóa ký metadata theo cơ chế được thiết kế; với discovery, kiểm tra kết nối và tính khớp issuer/endpoint theo quan hệ đã định.
5. **Chọn giao thức và thuật toán:** Chỉ bật các binding, flow, phương thức ký/mã hóa, thuật toán, redirect/ACS phù hợp chính sách.
6. **Đăng ký client/SP:** Xác định chính xác client ID, redirect URI, ACS, audience, chữ ký AuthnRequest nếu có và cách kiểm tra kết quả.
7. **Chạy kiểm tra tích hợp:** Xác thực thành công, từ chối token/assertion sai issuer/audience/khóa, kiểm tra expiry và logout theo phạm vi.
8. **Lưu cấu hình và owner:** Ghi đối tác, nguồn metadata, phiên bản, khóa/chứng thư đã chấp nhận, người phê duyệt và kế hoạch cập nhật.

**Chú ý:** Signed SAML metadata chỉ có ý nghĩa nếu chữ ký được kiểm tra bằng **khóa ký metadata đã được tin cậy từ trước**. Không được dùng chính chứng thư được nhúng trong tài liệu chưa tin cậy làm bằng chứng duy nhất để tin chữ ký đó; đây là lỗi **tự xác nhận nguồn**.

### 10.2. Metadata công khai không đồng nghĩa có thể tự động tin

Một địa chỉ `https://.../.well-known/openid-configuration` có thể đọc được công khai để phục vụ khám phá cấu hình. Việc tải thành công không cho phép ứng dụng tự động tin mọi issuer được trả về. Trong mô hình có dynamic federation, cần chính sách và cơ chế thiết lập tin cậy rõ ràng; **không biến input do người dùng gửi thành URL tải metadata hoặc JWKS không được kiểm soát**.

## 11. Kiểm soát an toàn khi tải và phân tích metadata

| Rủi ro | Tình huống | Kiểm soát |
|---|---|---|
| **Thay nguồn metadata** | Kẻ tấn công trỏ ứng dụng tới IdP giả | Pin nguồn/issuer/entityID đã duyệt; quản lý thay đổi |
| **SSRF** | Backend tải URL metadata do người dùng cung cấp tới mạng nội bộ | Allowlist nguồn, chặn IP/endpoint nội bộ không phù hợp, kiểm soát redirect |
| **XML parser attack** | SAML XML có external entity hoặc cấu trúc gây quá tải | Parser an toàn, tắt XXE/DTD không cần, giới hạn kích thước/độ sâu |
| **Sai chữ ký metadata** | Tài liệu bị sửa trên đường đi hoặc nguồn không đáng tin | Kiểm chứng chữ ký với trust anchor đã cấu hình khi áp dụng |
| **Thuật toán yếu/downgrade** | Metadata hoặc token đề xuất thuật toán không được phép | Allowlist thuật toán theo chính sách, không tin `alg` tùy ý |
| **Key confusion** | Dùng nhầm signing, encryption hoặc TLS key | Phân biệt vai trò và usage của khóa |
| **Cache lỗi thời** | Đối tác đã đổi khóa, ứng dụng vẫn dùng metadata cũ | Refresh có giám sát, kiểm tra TTL/validity, cảnh báo trước expiry |
| **Tenant/issuer confusion** | Token từ tenant khác cùng tên miền được chấp nhận | Kiểm issuer exact, audience, subject, policy tenant |
| **Endpoint injection** | Redirect/ACS đổi sang host ngoài mong đợi | Đăng ký chính xác, so sánh và phê duyệt thay đổi endpoint |
| **Metadata quá lớn/phức tạp** | XML/JWKS có nhiều khóa hoặc phần tử bất thường | Giới hạn dung lượng, số khóa, thời gian xử lý và cấu trúc |
| **Rò rỉ cấu hình nhạy cảm** | Private key/client secret nằm trong tài liệu chia sẻ | Chỉ công bố khóa công khai, bí mật ở secret manager |
| **Tự động tin khóa từ token** | Token mang URL JWKS giả | Không tự tải URL khóa từ input chưa tin cậy |

**Tải qua HTTPS là cần thiết đối với nhiều cách triển khai, nhưng không thay thế kiểm tra danh tính đối tác và chính sách.** Với metadata phân phối qua file hoặc aggregate, cần xác thực nguồn và tính toàn vẹn bằng cơ chế phù hợp.

### 11.1. Lỗi xử lý XML đáng chú ý

SAML dùng XML, nên parser cần được cấu hình tránh **XML External Entity (XXE)**, entity expansion và các rủi ro xử lý tài liệu không tin cậy. Thư viện xác minh SAML còn phải chống **XML signature wrapping** khi kiểm chữ ký trên Response/Assertion.

**Không tự tìm một phần tử XML có chữ ký hợp lệ rồi tin nội dung ở phần tử khác**. Phải bảo đảm dữ liệu dùng cho quyết định identity là chính xác nội dung được bảo vệ bởi chữ ký theo profile.

## 12. Thay đổi khóa và chứng thư: key/certificate rollover

IdP và SP phải thay khóa vì hết hạn, thay thuật toán, nâng cấp hạ tầng hoặc nghi ngờ lộ private key. Nếu bên phát hành đổi khóa nhưng bên tiêu thụ chưa cập nhật trust, đăng nhập có thể ngừng hoạt động. Nếu ứng dụng tiếp tục tin khóa bị thu hồi quá lâu, hệ thống có thể gặp rủi ro an ninh.

### 12.1. Rollover có kế hoạch

Một quy trình minh họa khi **IdP thay signing key**:

1. **Chuẩn bị:** Xác định owner hai bên, danh sách RP/SP phụ thuộc, lịch thay đổi và cách rollback.
2. **Công bố trước:** Khi giao thức/nền tảng hỗ trợ, công bố khóa công khai mới bên cạnh khóa cũ trong metadata/JWKS để bên nhận cập nhật trước.
3. **Đối soát:** Kiểm tra các RP/SP đã tải và tin khóa mới, không chỉ kiểm tra metadata từ phía IdP.
4. **Chuyển ký:** IdP bắt đầu phát hành assertion/token bằng khóa mới khi thời điểm đã được thống nhất.
5. **Quan sát:** Theo dõi lỗi kiểm chữ ký, issuer, audience, mã lỗi và kết quả đăng nhập.
6. **Gỡ khóa cũ:** Sau khi xác nhận không còn nhu cầu hợp lệ theo thời hạn token, cache và chính sách, loại khóa cũ khỏi các nguồn tin cậy tương ứng.
7. **Lưu bằng chứng:** Ghi change ID, người duyệt, thời gian, phiên bản metadata, kết quả kiểm thử và sự cố.

~~~mermaid
flowchart LR
    A["Chỉ khóa A<br/>đang được tin"] --> B["Công bố khóa A + B<br/>và chuẩn bị cache"]
    B --> C["RP/SP nhận khóa B<br/>và xác minh"]
    C --> D["IdP ký bằng khóa B<br/>theo lịch"]
    D --> E["Giám sát token/assertion<br/>và quyền truy cập"]
    E --> F["Gỡ khóa A<br/>khi đủ điều kiện"]
~~~

**Không tự áp dụng một khoảng thời gian cố định** cho mọi nơi: phải xét thời hạn token, cache metadata, đặc điểm SAML/OIDC, yêu cầu dịch vụ và nguy cơ an ninh.

### 12.2. Thay khóa khẩn cấp do nghi ngờ lộ

Nếu khóa ký bị lộ, kế hoạch thông thường “chờ cho mọi token cũ hết hạn” có thể không phù hợp. Cần xử lý theo **incident response**, đánh giá tác động, gỡ khóa bị lộ ở các bên tiêu thụ và áp cơ chế thu hồi/chặn truy cập được hỗ trợ.

Phải phân biệt:

- **Thay khóa ký:** Tác động tới khả năng kiểm chứng token/assertion.
- **Đổi TLS certificate:** Tác động tới HTTPS và xác minh endpoint, không nhất thiết đổi khóa ký federation.
- **Đổi khóa mã hóa assertion:** Tác động tới khả năng giải mã nội dung.
- **Thay client secret:** Tác động tới client authentication, không tương đương thay JWKS signing key.

### 12.3. JWKS cache và `kid`

Một ID token mới có thể chứa header `kid` của khóa B. Nếu RP cache JWKS chỉ có khóa A, RP không kiểm được token. Cần thiết kế refresh/rollover hợp lý; khi gặp khóa chưa biết, chỉ thử cập nhật từ **JWKS đã tin cậy** theo giới hạn tần suất/caching, không tùy tiện mở URL do token cung cấp.

**Không phải `kid` tự xác nhận khóa.** Nó là gợi ý chọn ứng viên; kiểm chứng cuối vẫn phụ thuộc nguồn JWKS đã tin, thuật toán được phép và chữ ký hợp lệ.

## 13. Thời hạn và caching: dữ liệu cũ nguy hiểm thế nào?

Metadata có thể được hệ thống tải lại theo lịch, theo hiệu lực được công bố hoặc theo thao tác quản trị. Tùy sản phẩm và cách phân phối:

- SAML metadata có thể chứa **`validUntil`** và **`cacheDuration`**; cần áp ngữ nghĩa đúng theo chuẩn và chính sách. Metadata hết hạn cần được phát hiện và xử lý, không mặc định tin vô hạn.
- OIDC discovery/JWKS thường được tải qua HTTP(S), có thể có header caching. Ứng dụng cần tôn trọng chính sách và kiểm soát refresh phù hợp, tránh dùng khóa cũ quá lâu.
- Metadata trong bộ nhớ hoặc cấu hình tĩnh có thể vẫn tồn tại khi nguồn đã thay. Cần quy trình đồng bộ và xác minh sau thay đổi.
- Nếu nguồn metadata tạm thời không khả dụng, giải pháp dự phòng phải cân bằng **sẵn sàng** với **mức rủi ro của việc sử dụng cấu hình cũ**; không có quy tắc “cứ tiếp tục tin mọi khóa mãi mãi”.
- Với thay đổi do sự cố bảo mật, có thể cần **vô hiệu hóa khóa cũ ngay**, vượt qua cache thông thường theo cơ chế kiểm soát thích hợp.

Một bảng theo dõi có thể chứa:

| Trường kiểm soát | Ý nghĩa |
|---|---|
| `partnerId` / tenant | Đối tác và ranh giới tin cậy |
| `sourceUri` / source type | Nơi metadata được nhận theo cấu hình |
| `entityID` / `issuer` | Định danh phải khớp |
| `lastVerifiedAt` | Lần gần nhất xác minh nguồn và nội dung |
| `lastRefreshedAt` | Lần gần nhất cập nhật runtime |
| `validUntil` / cache policy | Mốc cần làm mới khi áp dụng |
| `activeSigningKeyIds` | Khóa công khai còn được chấp nhận |
| `changeReference` | Phê duyệt cho thay đổi |
| `owner` | Người/nhóm chịu trách nhiệm theo dõi |

## 14. Sự cố thường gặp do metadata sai hoặc không đồng bộ

| Triệu chứng | Khả năng nguyên nhân | Điều cần kiểm tra |
|---|---|---|
| Mọi đăng nhập SAML thất bại sau khi IdP đổi chứng thư | SP chưa nhận khóa ký mới | Metadata, KeyDescriptor, lịch rollover và chữ ký |
| `Invalid issuer` | Issuer/entityID thực tế khác cấu hình | Đối chiếu issuer chính xác, tenant và source |
| `Audience mismatch` | Token/assertion dành cho ứng dụng khác | Client ID / SP entityID và cấu hình bên phát hành |
| `Invalid signature` | Khóa cũ, thuật toán không hỗ trợ hoặc token bị thay | Nguồn khóa đã tin, rotation, chữ ký thực tế |
| `Unknown kid` | JWKS cache chưa có khóa ký mới | Refresh từ `jwks_uri` đã tin, policy cache |
| SAML Response đến sai endpoint | ACS/Binding không khớp | SP metadata và cấu hình IdP |
| OIDC redirect báo lỗi | Redirect URI khác đăng ký | Client registration, callback và reverse proxy |
| Đăng nhập IdP được nhưng ứng dụng báo user không tồn tại | SCIM/JIT provisioning hoặc mapping lỗi | Account đích, `(iss, sub)` hoặc NameID và trạng thái |
| Login đúng nhưng bị từ chối quyền | RBAC/ABAC, nhóm hay thuộc tính chưa cập nhật | Authorization riêng, entitlement và JML |
| Chỉ một tenant bị lỗi | Tenant-specific metadata/issuer chưa đúng | Không mặc định tin mọi tenant cùng host |
| Đổi TLS cert nhưng vẫn báo lỗi token | Khóa TLS và khóa ký token khác nhau | Tách hai vòng đời khóa |
| User Leaver vẫn dùng được API | Phiên/token hoặc credential không bị thu hồi | Deprovisioning và kiểm chứng truy cập thực tế |

**Không sửa lỗi bằng cách tắt kiểm chứng chữ ký, issuer, audience hoặc cho phép thuật toán tùy ý.** Cách đó có thể khôi phục đăng nhập bề ngoài nhưng phá vỡ ranh giới tin cậy. Cần truy nguyên cấu hình, khóa, endpoint, thời gian và dữ liệu phiên.

## 15. Federation metadata trong vòng đời Joiner–Mover–Leaver

### 15.1. Joiner: metadata làm SSO hoạt động, không tự cấp tài khoản

Ví dụ nhân viên mới Lan đã qua identity proofing, HR cho phép gia nhập và IAM tạo account IdP. Ứng dụng CRM đã có quan hệ federation với IdP qua metadata. Khi Lan đăng nhập, CRM kiểm chứng kết quả OIDC/SAML từ đúng issuer/entityID.

Tuy nhiên, để Lan sử dụng CRM còn cần:

1. Account CRM được tạo/liên kết qua **SCIM/API** hoặc JIT provisioning được cho phép.
2. Quyền vai trò theo bộ phận, phạm vi dữ liệu và chính sách.
3. Kết quả xác thực đáp ứng yêu cầu MFA/conditional access.
4. Trạng thái và mốc Joiner cho phép truy cập.

Có metadata đúng **chưa có nghĩa Lan đã có account CRM hay role hợp lệ**.

### 15.2. Mover: định danh SSO có thể giữ nguyên, quyền phải đổi

Lan chuyển từ Sales sang Finance. Issuer IdP, metadata SAML/OIDC và subject ID thường **không cần đổi** chỉ vì người dùng chuyển bộ phận. Nhưng quyền ứng dụng cần được tính lại theo RBAC/ABAC, thu hồi phần Sales không còn căn cứ và áp các yêu cầu xác thực/step-up phù hợp vai trò mới.

Một token hoặc phiên cũ có thể mang claim vai trò trước khi thay đổi; phải đánh giá thời hạn token, cache của ứng dụng và cơ chế cập nhật quyền.

### 15.3. Leaver: metadata vẫn hoạt động cho tổ chức, account người rời đi phải bị thu hồi

Khi contractor hết hợp đồng, không nên “xóa IdP metadata” để thu hồi một người dùng: thao tác này có thể làm hỏng SSO của **toàn bộ đối tác hoặc nhiều người dùng khác**.

Thay vào đó, quy trình Leaver cần:

- Xác định chính xác identity, engagement, ứng dụng và account đích.
- Vô hiệu hóa/thu hồi quyền qua IdP, SCIM/API, role và quyền trực tiếp.
- Xử lý local session, refresh/access token, personal token và API key theo khả năng hệ thống.
- Kiểm chứng quyền thực tế đã hết hiệu lực tại target, ghi bằng chứng và theo dõi lỗi một phần.

Nếu một quan hệ federation **của cả đối tác** chấm dứt, đó là biến cố quản trị trust riêng: cần kiểm kê ứng dụng, thu hồi quyền người dùng liên quan, xử lý khóa, endpoint và hợp đồng theo quy trình phê duyệt; không đồng nhất với Leaver của một cá nhân.

### 15.4. Rejoiner và thay IdP

Khi cá nhân quay lại tổ chức hoặc đối tác chuyển sang IdP mới, không tự ghép hai subject chỉ từ email giống nhau. Với OIDC, subject thường được ánh xạ bằng **cặp `(issuer, sub)`**; thay issuer có thể đòi hỏi quy trình **account linking/migration được xác minh**. Với SAML, cần quan tâm định danh NameID và policy ánh xạ tương ứng.

Đổi issuer/entityID cũng có thể ảnh hưởng tới **trust configuration**, không phải chỉ thay một URL trong metadata.

## 16. Liên hệ MFA, RBAC/ABAC và dữ liệu danh tính trong assertion

### 16.1. Metadata không tự bảo đảm MFA

Metadata có thể nêu thông tin khả năng giao thức, nhưng không có nghĩa **mọi lần đăng nhập** đều đã thực hiện MFA mạnh. Với một số tích hợp, assertion/token có thể chứa claim về phương thức hoặc mức xác thực (ví dụ `acr`, `amr` trong OIDC) nếu IdP hỗ trợ, nhưng RP phải **hiểu rõ ngữ nghĩa, mức tin cậy và policy đã thống nhất**.

Không nên gán “MFA đã đạt” chỉ vì người dùng đến từ một IdP đáng tin. Nếu ứng dụng nhạy cảm yêu cầu step-up, phải kiểm tra kết quả xác thực thực tế và độ mới thích hợp.

### 16.2. Claim/attribute không tự tạo chính sách phân quyền

Ví dụ một SAML assertion hoặc OIDC token mang `department=Finance`. Ứng dụng cần xác định:

- Nguồn thuộc tính có thẩm quyền và có đủ tin cậy cho quyết định này không?
- Giá trị thuộc tính có còn mới và đúng engagement không?
- Role trong RBAC có được cấp từ quy trình được duyệt hay chỉ suy ra một claim?
- ABAC có kiểm tra tài nguyên, hành động, site/project và thời hạn?
- Có nguy cơ tin một email hoặc nhóm do bên ngoài tự khai để cấp quyền nội bộ quá rộng không?

**Metadata xác định đối tác**, còn **attribute mapping và authorization policy** phải được thiết kế riêng, có owner và được đối soát khi thay đổi vai trò.

### 16.3. Giảm chia sẻ thuộc tính nhạy cảm

Federation giúp tránh ứng dụng phải nhận mật khẩu người dùng; tuy nhiên, không nên vì thế gửi toàn bộ hồ sơ HR, số giấy tờ hay thông tin sinh trắc qua assertion/token. Chỉ truyền **claim cần thiết, được phép và có thời hạn phù hợp**, với kiểm soát logging và quyền riêng tư.

## 17. Quản trị federation với nhà thầu và đối tác

Một đối tác cung cấp tài khoản cho chuyên gia ngoài và muốn họ đăng nhập vào cổng dự án. Thiết kế cần ít nhất hai lớp trách nhiệm:

**Lớp federation (trust):**

- Đối tác/tenant/issuer/entityID nào được tin?
- Metadata đến từ nguồn nào và cách xác minh?
- Key/algorithm/endpoint nào được chấp nhận?
- Đối tác chịu trách nhiệm xác thực và bảo vệ tài khoản ở mức nào?
- Cách báo thay đổi khóa, issuer, outage và sự cố là gì?

**Lớp lifecycle & access (IAM):**

- Ai là nhà thầu cụ thể, sponsor nội bộ nào chịu trách nhiệm?
- Hợp đồng/dự án còn hiệu lực tới ngày nào?
- Account/entitlement nào trong hệ thống nhận được phép sử dụng?
- Ai rà soát khi nhà thầu đổi nhiệm vụ hoặc rời dự án?
- Khi IdP đối tác không phản hồi, hệ thống nhận có thể **chặn truy cập tại chính ứng dụng** theo chính sách không?

Một assertion đăng nhập hợp lệ từ IdP đối tác **không được tự cấp quyền truy cập mọi tài nguyên**. Tổ chức nhận cần một lớp kiểm soát truy cập và thời hạn độc lập với trạng thái đăng nhập của đối tác.

## 18. Bài tập thực hành: thay signing key của IdP

**Bối cảnh:** Công ty sử dụng một IdP cho nhiều ứng dụng SAML và OIDC. Đội IAM chuẩn bị thay khóa ký ở IdP. Sau thời điểm chuyển, một số ứng dụng OIDC báo `unknown kid`, một SP SAML báo `signature validation failed`, nhưng các ứng dụng khác vẫn đăng nhập bình thường.

### 18.1. Phân tích

- Các ứng dụng OIDC có thể đang cache **JWKS cũ** hoặc nhận token `kid` mới khi chưa tải khóa mới.
- SP SAML có thể chưa nạp metadata có **signing certificate mới**.
- Không thể kết luận IdP bị lỗi chỉ vì một số ứng dụng thất bại; mỗi ứng dụng có cache/trust configuration khác nhau.
- Không được sửa bằng cách tắt chữ ký hoặc bỏ qua `kid`/issuer/audience.
- Cần kiểm tra việc công bố khóa, thời điểm chuyển ký, tình trạng cập nhật metadata/JWKS và khả năng rollback được duyệt.

### 18.2. Hướng xử lý

1. Xác minh sự kiện thay khóa đã được phê duyệt và khóa mới thuộc IdP đáng tin.
2. Kiểm tra metadata SAML/JWKS tại nguồn chính thức, trạng thái cache ở từng ứng dụng.
3. Rà soát khóa đang được tin và thuật toán được phép, không nạp khóa từ nguồn không xác minh.
4. Cập nhật những ứng dụng chưa nhận khóa mới theo quy trình, kiểm tra lại chữ ký và giao dịch thực.
5. Theo dõi lỗi và ảnh hưởng dịch vụ; xử lý các ứng dụng không hỗ trợ nhiều khóa trong giai đoạn rollover bằng kế hoạch riêng.
6. Chỉ loại khóa cũ khi đáp ứng điều kiện về token/assertion còn hợp lệ, cache và chính sách.
7. Ghi chứng cứ: thay đổi nào, đối tác nào, thời điểm, khóa trước/sau, kết quả kiểm tra và người phê duyệt.

### 18.3. Điều kiện hoàn tất

- Các ứng dụng bắt buộc kiểm chứng được kết quả do khóa mới phát hành.
- Không ứng dụng nào âm thầm bỏ qua điều kiện issuer/audience/chữ ký.
- Những target lỗi được xử lý hoặc theo dõi ngoại lệ có owner và thời hạn.
- Kế hoạch loại khóa cũ và hậu kiểm được thực hiện đúng chính sách.

## 19. Tình huống: đổi URL issuer và account mapping

**Bối cảnh:** Một IdP chuyển từ `https://idp-old.example.test` sang `https://idp-new.example.test`. Tên người dùng/email được giữ nguyên, nhưng `issuer` trong ID token thay đổi. Đội ứng dụng đề nghị chỉ sửa `jwks_uri` và tiếp tục ánh xạ người dùng theo email.

**Vì sao chưa đủ?**

- `issuer` là một thành phần của **ranh giới tin cậy**. Nếu thay issuer, ứng dụng phải xác nhận danh tính thực thể mới và chính sách liên kết.
- Cặp `(iss, sub)` được dùng để nhận diện subject trong OIDC; cùng email chưa chắc là cùng identity.
- Chuyển `jwks_uri` mà không kiểm issuer/endpoint có thể dẫn đến dùng sai khóa và sai tenant.
- Người dùng có thể còn account, role và phiên cũ. Cần đối soát migration để tránh tạo trùng hoặc cấp quyền cho nhầm người.

**Thiết kế phù hợp hơn:** Quy trình thay đổi trust có phê duyệt, kiểm tra metadata và khóa mới; lập bản đồ subject ID được xác minh, xử lý phiên/token cũ, test role và hệ thống đích, lưu bằng chứng và có phương án rollback. Không tin issuer mới tự động chỉ vì cùng tên hiển thị doanh nghiệp.

## 20. Kiểm toán và giám sát federation metadata

Một bản ghi quản trị federation nên giúp trả lời:

1. Tổ chức, tenant và ứng dụng nào đang tin đối tác?
2. `entityID` hoặc `issuer` nào được chấp nhận; nguồn metadata ở đâu?
3. Ai duyệt thiết lập ban đầu và các lần thay đổi khóa/endpoint?
4. Signing key/certificate/algorithm nào đang được chấp nhận? Có khóa cũ chờ loại không?
5. Metadata được tải, xác minh và áp vào runtime khi nào?
6. Có chênh lệch giữa metadata nguồn với cấu hình runtime không?
7. Có lỗi signature, issuer, audience, redirect/ACS và JWKS cache không?
8. Nếu đối tác ngừng hoạt động hoặc kết thúc hợp đồng, còn account/phiên/quyền nào tồn dư?

### Các chỉ số vận hành

| Chỉ số | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| **Metadata freshness** | Độ mới của cấu hình đã được xác minh | Không chỉ dựa vào lần tải thành công |
| **Metadata validation failure** | Số lần chữ ký/nguồn/issuer không đạt | Phân biệt lỗi mạng và sai cấu hình với dấu hiệu tấn công |
| **Key rollover readiness** | Tỷ lệ RP/SP sẵn sàng nhận khóa mới | Readback cấu hình và test xác thực quan trọng |
| **Unknown kid/signature failures** | Sự cố chọn khóa/kiểm chứng | Không tự hạ chính sách để “fix” |
| **Endpoint drift** | Endpoint runtime khác nguồn đã duyệt | Có thể do thay đổi proxy, vendor hoặc cấu hình sai |
| **Federation login success** | Thành công đăng nhập theo đối tác/ứng dụng | Không đồng nhất với cấp quyền ứng dụng |
| **Provisioning mismatch** | Xác thực được nhưng thiếu account/role ở đích | Liên hệ SCIM/JIT và mapping |
| **Residual access after trust change** | Quyền/phiên/tài khoản tồn dư sau thay IdP hoặc kết thúc quan hệ | Cần đối soát ứng dụng và JML |
| **Unowned federation connection** | Kết nối không còn owner phụ trách | Rủi ro metadata lỗi thời và chứng thư hết hạn |

Bảo vệ nhật ký và báo cáo: **không ghi private key, client secret, access token nguyên văn, mật khẩu hoặc dữ liệu cá nhân vượt mục đích**. Ghi dấu vết thay đổi cấu hình và kết quả xác minh, kèm quyền truy cập phù hợp.

## 21. Checklist thiết kế và vận hành federation metadata

- [ ] **Ranh giới tin cậy:** Đối tác, tenant, ứng dụng, owner và mục đích tích hợp đã được xác nhận?
- [ ] **Định danh:** `entityID` (SAML) hoặc `issuer` (OIDC) được cấu hình chính xác, không suy từ tên miền gần giống?
- [ ] **Nguồn:** URL/file metadata và kênh nhận được xác minh độc lập, có phê duyệt?
- [ ] **Tính toàn vẹn:** Signed metadata (nếu áp dụng) được kiểm bằng khóa đã tin từ trước; không tự xác nhận nguồn?
- [ ] **Endpoint:** SSO/ACS, authorization/token/redirect đã được đăng ký chính xác và giới hạn?
- [ ] **Khóa:** Signing/encryption/TLS được phân biệt; không xuất bản private key hoặc secret?
- [ ] **Thuật toán:** Allowlist theo chính sách, không tin `alg` tùy ý và không chấp nhận downgrade?
- [ ] **Giao thức:** SAML assertion hoặc OIDC ID token được kiểm chữ ký, issuer/audience, thời gian và transaction correlation?
- [ ] **JWKS:** Chỉ tải từ OP đã tin cậy, kiểm soát `kid`, caching, refresh và rollover?
- [ ] **Parser:** XML/JSON được phân tích an toàn, giới hạn kích thước, không XXE/SSRF?
- [ ] **Thời hạn:** Có kế hoạch cho `validUntil`, caching, key rollover và trường hợp khẩn cấp?
- [ ] **Client/SP:** Có cấu hình registration, audience và callback riêng; discovery không tự cho phép client mới?
- [ ] **Subject mapping:** Có định danh ổn định, không liên kết tài khoản chỉ theo email, đặc biệt khi thay issuer?
- [ ] **MFA:** Mức xác thực và step-up được xác minh theo chính sách, không suy từ metadata?
- [ ] **Quyền:** RBAC/ABAC, SCIM/API và session/token được quản trị độc lập với trust metadata?
- [ ] **JML:** Joiner được cấp đúng tài khoản; Mover thu hồi quyền cũ; Leaver được chặn đường truy cập cần thiết?
- [ ] **Đối tác/contractor:** Có sponsor, thời hạn, kiểm tra quyền tại hệ thống nhận và kế hoạch khi đối tác kết thúc?
- [ ] **Service account:** Federation/workload trust có owner, audience/scope và vòng đời credential riêng?
- [ ] **Readback & audit:** Đã kiểm tra runtime thực tế, lưu nguồn, phiên bản, thay đổi, lỗi và owner?
- [ ] **Hậu kiểm:** Có cảnh báo chứng thư sắp hết hạn, metadata drift, lỗi login và quyền tồn dư?

**Ghi nhớ:** **Federation metadata là bản mô tả quan hệ tin cậy, không phải giấy phép truy cập**. SAML metadata và OIDC discovery/JWKS giúp định danh đúng đối tác, endpoint và khóa công khai để các hệ thống kiểm chứng kết quả xác thực. Một kiến trúc IAM an toàn phải **xác minh nguồn metadata, ràng buộc issuer/entityID, kiểm chữ ký/token, quản lý rollover và theo dõi thay đổi**, đồng thời vận hành **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và Joiner–Mover–Leaver** để thu hồi đúng quyền, tránh quyền truy cập tồn dư.
