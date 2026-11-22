# Cấu trúc Response, Assertion và Subject trong SAML2

> **Module:** Spring Security – federation · **Chủ đề cha:** Mô hình SAML2. Bài học giải thích cách đọc ba lớp XML cốt lõi của SAML 2.0 Web Browser SSO, cách chúng liên kết với nhau và cách một Service Provider (SP) xác minh trước khi chấp nhận đăng nhập.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **`<samlp:Response>`**, **`<saml:Assertion>`** và **`<saml:Subject>`** theo trách nhiệm, vị trí và dữ liệu chúng mang.
2. Đọc các thuộc tính `ID`, `Version`, `IssueInstant`, `Destination`, `InResponseTo`, `Issuer`, `Status`; đối chiếu chúng với yêu cầu đăng nhập và cấu hình SP.
3. Hiểu ý nghĩa của `NameID`, `SubjectConfirmation`, `SubjectConfirmationData`, `Conditions`, `AudienceRestriction`, `AuthnStatement` và `AttributeStatement`.
4. Theo dõi một ví dụ XML hoàn chỉnh về mặt cấu trúc, xác định **ai phát hành**, **ai là chủ thể**, **phát hành cho SP nào**, **trả lời yêu cầu nào** và **đến thời điểm nào còn được chấp nhận**.
5. Giải thích vì sao **giải mã Base64 hay đọc XML không chứng minh tính xác thực**, và nêu được những kiểm tra mà SP phải thực hiện trước khi tạo phiên.
6. Nhận ra cách Spring Security SAML2 chuyển một response đã xác minh thành `Saml2Authentication` và `Saml2AuthenticatedPrincipal`.

## 1. Bức tranh tổng thể: ba lớp, ba trách nhiệm

Trong SAML 2.0 Web Browser SSO, **Identity Provider (IdP)**, còn gọi *Asserting Party*, xác thực người dùng; **Service Provider (SP)**, còn gọi *Relying Party*, nhận và kiểm tra thông điệp SAML để quyết định có tạo phiên ứng dụng hay không.

Hãy nhìn cấu trúc khái niệm sau:

~~~text
HTTP POST đến Assertion Consumer Service (ACS)
└── form field SAMLResponse = Base64(XML)
    └── <samlp:Response>              (vỏ thông điệp ở tầng protocol)
        ├── <saml:Issuer>             (bên phát hành response)
        ├── <ds:Signature>?           (nếu ký ở tầng Response)
        ├── <samlp:Status>            (kết quả xử lý yêu cầu)
        └── <saml:Assertion>          (một khẳng định SAML)
            ├── <saml:Issuer>         (bên phát hành assertion)
            ├── <ds:Signature>?       (nếu ký ở tầng Assertion)
            ├── <saml:Subject>        (chủ thể của khẳng định)
            │   ├── <saml:NameID>     (định danh chủ thể)
            │   └── <saml:SubjectConfirmation>
            │       └── <saml:SubjectConfirmationData>
            ├── <saml:Conditions>     (điều kiện được phép sử dụng)
            │   └── <saml:AudienceRestriction>
            ├── <saml:AuthnStatement> (sự kiện/ngữ cảnh xác thực)
            └── <saml:AttributeStatement> (thuộc tính người dùng)
~~~

Dấu `?` tại Signature có nghĩa **vị trí chữ ký tùy hồ sơ và cấu hình**, không có nghĩa mọi response không ký đều được chấp nhận. Ở một thiết lập Web SSO thông thường, SP phải yêu cầu **bằng chứng chữ ký hợp lệ theo profile/chính sách tin cậy**: ký Response và/hoặc ký các Assertion theo quy tắc thích hợp. Một tài liệu XML minh họa không có chữ ký thật **không đủ** để đăng nhập.

Một cách ghi nhớ:

| Thành phần | Trả lời câu hỏi | Không nên dùng để kết luận |
| --- | --- | --- |
| **Response** | “IdP trả về thông điệp nào cho SP, đối với request nào và kết quả xử lý ra sao?” | Chưa đủ để kết luận có người dùng đã đăng nhập khi chưa kiểm tra assertion. |
| **Assertion** | “IdP khẳng định sự thật gì về một chủ thể, trong phạm vi và thời hạn nào?” | Không chứng minh mọi claim là quyền của ứng dụng. |
| **Subject** | “Assertion nói về ai và bên trình assertion phải đáp ứng điều kiện nào để được chấp nhận?” | Không phải một mật khẩu; `NameID` không tự chứng minh quyền truy cập. |

**Phân biệt giao thức và vận chuyển:** chuỗi `SAMLResponse` trong form HTTP là tên **tham số binding**, thường chứa XML đã được Base64 hóa. Nó khác phần tử XML `<samlp:Response>`. Base64 là mã hóa biểu diễn dữ liệu, **không phải mã hóa bảo mật và không phải chữ ký**.

## 2. Namespace và tên phần tử

SAML2 tách **protocol** khỏi **assertion** bằng hai XML namespace:

| Prefix thường dùng | Namespace URI | Ví dụ |
| --- | --- | --- |
| `samlp` | `urn:oasis:names:tc:SAML:2.0:protocol` | `Response`, `Status`, `AuthnRequest` |
| `saml` | `urn:oasis:names:tc:SAML:2.0:assertion` | `Assertion`, `Subject`, `NameID`, `Conditions` |
| `ds` | `http://www.w3.org/2000/09/xmldsig#` | `Signature` và cấu trúc XML Digital Signature |

**Prefix có thể đổi:** `<p:Response xmlns:p="urn:oasis:names:tc:SAML:2.0:protocol">` và `<samlp:Response ...>` cùng chỉ tới một element theo XML namespace. Trình phân tích phải dựa vào **namespace URI + local name**, không dựa vào chuỗi prefix trong XML. SAML Core quy định tên và thứ tự các phần tử, không phải mọi XML tự đặt tên “Assertion” đều hợp lệ.

## 3. Lớp ngoài cùng: `<samlp:Response>`

Response là thông điệp protocol do IdP trả cho SP. Cấu trúc điển hình:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-4ac"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/partner"
    InResponseTo="_req-48f">
    <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>
    <!-- Nếu ký Response, ds:Signature nằm theo thứ tự XML hợp lệ tại đây -->
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
    <!-- Assertion hoặc EncryptedAssertion nằm sau Status -->
</samlp:Response>
~~~

Đây là **đoạn cấu trúc minh họa**, không phải một Response được ký hoặc sử dụng để đăng nhập.

### 3.1. Ý nghĩa từng trường

| Trường | Ý nghĩa | Điểm SP phải đối chiếu |
| --- | --- | --- |
| `ID` | Định danh riêng của **Response** (theo quy định về ID của SAML). | Nhận diện response, chống lặp/replay khi thích hợp; phân biệt với ID của Assertion và AuthnRequest. |
| `Version="2.0"` | Phiên bản giao thức SAML. | Phải phù hợp trình xử lý SAML 2.0. |
| `IssueInstant` | Thời điểm IdP phát hành **Response**. | Kiểm tra chính sách thời gian/lệch đồng hồ; không nhầm với thời điểm user xác thực. |
| `Destination` | Địa chỉ dự kiến **nhận thông điệp Response**. | Thường phải khớp chính xác địa chỉ ACS dự kiến của SP theo binding/cấu hình. |
| `InResponseTo` | ID của **AuthnRequest** mà Response này trả lời. | Với SP-initiated SSO, phải tương ứng một request do SP phát hành và còn hợp lệ. |
| `<saml:Issuer>` | Bên phát hành Response (thường là entity ID của IdP). | Phải khớp IdP/registration được cấu hình, không tin issuer do request tự chọn. |
| `<samlp:Status>` | Kết quả xử lý yêu cầu SAML. | Cần trạng thái phù hợp, thường là `Success`, trước khi chấp nhận kết quả xác thực. |
| `<saml:Assertion>` | Một hoặc nhiều assertion chứa khẳng định. | Phải xác minh tính toàn vẹn, điều kiện và subject trên assertion thật sự được sử dụng. |
| `<saml:EncryptedAssertion>` | Assertion ở dạng được mã hóa (nếu dùng). | Giải mã bằng khóa của SP và tiếp tục kiểm tra chữ ký/điều kiện đúng trình tự. |

`ID` của Response **khác** `InResponseTo`: ví dụ `_resp-4ac` là ID thông điệp mới, còn `_req-48f` trỏ về ID của yêu cầu trước đó. Không được kiểm tra bằng cách so sánh hai ID này với nhau.

### 3.2. `Status`: kết quả protocol, không phải quyền truy cập

~~~xml
<samlp:Status
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Responder">
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:AuthnFailed"/>
    </samlp:StatusCode>
    <samlp:StatusMessage>Authentication failed</samlp:StatusMessage>
</samlp:Status>
~~~

Response có thể mang lỗi như `Responder`, `AuthnFailed`, `Requester` hoặc các status khác theo SAML. Một response báo lỗi có thể **không có assertion xác thực thành công**. `StatusMessage` là mô tả tùy chọn và phải được coi là dữ liệu bên ngoài khi hiển thị/log; không nên để lỗi chi tiết của IdP làm lộ thông tin nhạy cảm.

`Success` chỉ nói yêu cầu protocol được xử lý thành công, **chưa thay thế việc xác minh chữ ký, subject, Conditions hoặc quyền ứng dụng**.

## 4. Lớp khẳng định: `<saml:Assertion>`

Một Assertion là tập hợp các lời khẳng định từ một issuer về một subject. Với Web Browser SSO, assertion xác thực thường chứa:

~~~text
Assertion
├── ID, Version, IssueInstant
├── Issuer
├── Signature (nếu ký assertion)
├── Subject
├── Conditions
├── AuthnStatement
│   ├── AuthnInstant
│   ├── SessionIndex (tùy chọn)
│   └── AuthnContext
└── AttributeStatement (nếu có)
    └── Attribute / AttributeValue
~~~

### 4.1. Ba loại statement thông dụng

- **`AuthnStatement`**: IdP khẳng định **người dùng đã xác thực**, với `AuthnInstant`, `AuthnContext` và có thể `SessionIndex` hoặc `SessionNotOnOrAfter`. Đây là lõi của câu chuyện SSO.
- **`AttributeStatement`**: IdP khẳng định **thuộc tính** của subject (email, mã phòng ban, nhóm…). Mỗi `Attribute` có thể có **nhiều `AttributeValue`**; không mặc định một giá trị là duy nhất.
- **`AuthzDecisionStatement`**: SAML Core có mô hình lời khẳng định về quyết định ủy quyền, nhưng không nên ngầm coi đó là chính sách phân quyền của mọi ứng dụng. Ứng dụng phải xác định rõ nguồn quyền và hợp đồng tin cậy nếu có dùng.

Trong luồng SAML2 Login của Spring Security, ứng dụng thường dựa vào assertion được xác minh để tạo principal, sau đó thực hiện **authorization riêng** ở tầng ứng dụng. Một thuộc tính `department=finance` hoặc `group=admin` không tự biến thành quyền `APP_PAYMENT_APPROVE`.

### 4.2. `Issuer` ở Response và Assertion

Một thông điệp có thể có `Issuer` ở **hai lớp**: issuer của Response và issuer của từng Assertion. Trong cấu hình Web SSO thông thường, cả hai phải phù hợp các quan hệ tin cậy với IdP. Không được chỉ kiểm tra issuer ngoài rồi mặc nhiên tin assertion bất kỳ ở trong.

Đối với ký số cũng vậy: **chữ ký ở Response** bảo vệ một phạm vi XML; **chữ ký ở Assertion** bảo vệ một phạm vi khác. Cần biết chính xác phần tử nào được ký và phần tử nào được chương trình tiêu thụ, để phòng các biến thể tấn công XML Signature Wrapping.

### 4.3. `Conditions` không phải `SubjectConfirmationData`

~~~xml
<saml:Conditions
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    NotBefore="2030-05-01T09:59:00Z"
    NotOnOrAfter="2030-05-01T10:05:00Z">
    <saml:AudienceRestriction>
        <saml:Audience>
            https://sp.example.org/saml2/service-provider-metadata/partner
        </saml:Audience>
    </saml:AudienceRestriction>
</saml:Conditions>
~~~

- `NotBefore`: assertion **chưa được dùng trước thời điểm này**, tùy chính sách chấp nhận độ lệch đồng hồ.
- `NotOnOrAfter`: tại hoặc sau mốc này, assertion **không còn hợp lệ để chấp nhận**; không hiểu mốc này là “còn hợp lệ trong đúng giây hết hạn”.
- `AudienceRestriction`: chỉ định **thực thể được phép tiêu thụ assertion**; thường là **SP entity ID**, không nhất thiết bằng địa chỉ ACS.
- Có thể có điều kiện khác như `OneTimeUse`, `ProxyRestriction`. Việc hỗ trợ thực thi điều kiện phụ thuộc thư viện/profile/chính sách; nếu một điều kiện chưa được xử lý an toàn, không tự ý bỏ qua.
- Phải kiểm tra **cả Conditions lẫn SubjectConfirmationData** khi tương ứng; hợp lệ ở một nơi **không** bù cho một nơi khác sai.

## 5. Lớp chủ thể: `<saml:Subject>`

`Subject` nằm **bên trong một Assertion**, mô tả ai là đối tượng của những lời khẳng định. Thường có hai phần quan trọng:

~~~xml
<saml:Subject
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
        partner-user-073
    </saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            InResponseTo="_req-48f"
            NotOnOrAfter="2030-05-01T10:05:00Z"
            Recipient="https://sp.example.org/login/saml2/sso/partner"/>
    </saml:SubjectConfirmation>
</saml:Subject>
~~~

### 5.1. `NameID`: cách định danh người được khẳng định

`NameID` có nội dung văn bản và có thể mang `Format`, `NameQualifier`, `SPNameQualifier`, `SPProvidedID` tùy thiết lập. Một số định dạng thường gặp:

| NameID Format | Ý nghĩa | Cách hiểu đúng |
| --- | --- | --- |
| `unspecified` | IdP và SP dùng quy ước riêng. | Phải đọc hợp đồng IdP–SP để biết chuỗi này đại diện gì. |
| `emailAddress` | Định danh dạng địa chỉ email. | Email có thể thay đổi/tái sử dụng; tránh ghép tài khoản chỉ từ email. |
| `persistent` | Định danh được IdP cấp có tính bền vững trong ngữ cảnh liên kết. | Phù hợp cho liên kết tài khoản nếu chính sách IdP xác nhận độ ổn định và phạm vi. |
| `transient` | Định danh tạm thời, không phải khóa lâu dài. | Không dùng để nối một user qua nhiều lần đăng nhập nếu IdP không bảo đảm ổn định. |

**NameID không mặc nhiên là username/email/local user ID.** Với nhiều IdP, cùng một chuỗi `NameID` có thể chỉ những người khác nhau; việc liên kết tài khoản nên xác định theo **issuer/entity ID + NameID và ngữ cảnh format/qualifier** theo hợp đồng, có thể thêm tenant/registration. Một `NameID` rỗng/không mong đợi hoặc sai format cần được xử lý theo chính sách thay vì đoán.

`NameID` cũng có thể được mã hóa thành `EncryptedID`. Khi đó SP phải giải mã bằng khóa phù hợp **sau khi đã bảo toàn các ràng buộc chữ ký/định dạng**, không coi plaintext giải mã được là chứng cứ tin cậy nếu chưa xác minh toàn bộ assertion.

### 5.2. `SubjectConfirmation`: chứng minh assertion được trình đúng cách

`SubjectConfirmation` chỉ định **phương thức xác nhận subject**. Trong SAML2 Web Browser SSO, phương thức thường là:

~~~text
urn:oasis:names:tc:SAML:2.0:cm:bearer
~~~

**Bearer** ở đây không có nghĩa “ai cầm XML là đã được phép dùng mọi nơi”. SP phải xác minh assertion là hợp lệ, được phát hành cho SP, vẫn còn thời hạn, người đang trình response qua binding đúng ràng buộc và không bị replay.

`SubjectConfirmationData` thường chứa:

- **`Recipient`**: nơi assertion có thể được trình để chấp nhận, thường **ACS endpoint** của SP.
- **`InResponseTo`**: liên kết với `AuthnRequest` đã được SP tạo, đặc biệt trong SP-initiated SSO.
- **`NotOnOrAfter`**: thời hạn chấp nhận **subject confirmation**, thường ngắn; khác với `SessionNotOnOrAfter` của phiên IdP.
- **`NotBefore` hoặc `Address`** nếu xuất hiện theo phương thức/profile: cần hiểu quy tắc tương ứng; không áp đặt rằng mọi hệ thống đều gửi các trường này.

Một Assertion có thể chứa nhiều `SubjectConfirmation`. Bộ xác minh cần xử lý theo profile và bảo đảm một **phương thức/nhánh confirmation thích hợp** thực sự hợp lệ; không nên đọc phần tử đầu tiên tùy tiện rồi kết luận.

### 5.3. Bốn giá trị dễ nhầm

| Thuộc tính/phần tử | Đối tượng ràng buộc | Giá trị trong ví dụ |
| --- | --- | --- |
| `Response.Destination` | **URL ACS nhận Response** | `https://sp.example.org/login/saml2/sso/partner` |
| `SubjectConfirmationData.Recipient` | **URL nơi được trình bearer assertion** | `https://sp.example.org/login/saml2/sso/partner` |
| `Conditions.AudienceRestriction.Audience` | **SP entity ID**, định danh thực thể được phép dùng assertion | `https://sp.example.org/saml2/service-provider-metadata/partner` |
| `InResponseTo` (Response/SubjectConfirmationData) | **ID AuthnRequest đang được trả lời** | `_req-48f` |

Tùy cấu hình, **Destination và Recipient thường trùng ACS**, trong khi **Audience là entity ID**, thường là một URL khác. Không lấy URL của IdP thay cho Audience. `InResponseTo` là **ID**, không phải URL.

## 6. Ví dụ XML đầy đủ để đọc theo đường đi

Giả sử SP có:

- **SP entity ID**: `https://sp.example.org/saml2/service-provider-metadata/partner`.
- **ACS**: `https://sp.example.org/login/saml2/sso/partner`.
- **IdP entity ID**: `https://idp.partner.example.org/saml`.
- **AuthnRequest ID** vừa gửi: `_req-48f`.
- **User**: `partner-user-073`.

Ví dụ **cố ý không chứa chữ ký số**, giá trị ngày/tháng và ID chỉ để học cấu trúc. **Dù XML well-formed, SP bảo mật phải từ chối dùng bản minh họa này để xác thực**; muốn một SAML Response hợp lệ thực tế cần IdP được cấu hình và các chữ ký/binding/điều kiện đáp ứng đúng profile.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-4ac"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/partner"
    InResponseTo="_req-48f">

    <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>

    <!-- Minh hoa: bo qua ds:Signature thuc te. KHONG DUNG de dang nhap. -->

    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>

    <saml:Assertion
        ID="_assert-9d1"
        Version="2.0"
        IssueInstant="2030-05-01T10:00:00Z">

        <saml:Issuer>https://idp.partner.example.org/saml</saml:Issuer>

        <!-- Neu ky Assertion, ds:Signature nam tai vi tri dung theo schema. -->

        <saml:Subject>
            <saml:NameID
                Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
                partner-user-073
            </saml:NameID>
            <saml:SubjectConfirmation
                Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData
                    InResponseTo="_req-48f"
                    Recipient="https://sp.example.org/login/saml2/sso/partner"
                    NotOnOrAfter="2030-05-01T10:05:00Z"/>
            </saml:SubjectConfirmation>
        </saml:Subject>

        <saml:Conditions
            NotBefore="2030-05-01T09:59:00Z"
            NotOnOrAfter="2030-05-01T10:05:00Z">
            <saml:AudienceRestriction>
                <saml:Audience>https://sp.example.org/saml2/service-provider-metadata/partner</saml:Audience>
            </saml:AudienceRestriction>
        </saml:Conditions>

        <saml:AuthnStatement
            AuthnInstant="2030-05-01T09:58:30Z"
            SessionIndex="_idp-session-28"
            SessionNotOnOrAfter="2030-05-01T18:00:00Z">
            <saml:AuthnContext>
                <saml:AuthnContextClassRef>
                    urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
                </saml:AuthnContextClassRef>
            </saml:AuthnContext>
        </saml:AuthnStatement>

        <saml:AttributeStatement>
            <saml:Attribute Name="department">
                <saml:AttributeValue>engineering</saml:AttributeValue>
            </saml:Attribute>
            <saml:Attribute Name="groups">
                <saml:AttributeValue>partner-readers</saml:AttributeValue>
                <saml:AttributeValue>partner-auditors</saml:AttributeValue>
            </saml:Attribute>
        </saml:AttributeStatement>
    </saml:Assertion>
</samlp:Response>
~~~

### 6.1. Đọc ví dụ theo chuỗi câu hỏi

**(a) Ai phát hành?** Hai `Issuer` minh họa cùng entity ID `https://idp.partner.example.org/saml`. SP vẫn phải đối chiếu với IdP được tin cậy và **xác minh chữ ký**; nhìn chuỗi text chưa đủ.

**(b) Thông điệp thuộc request nào?** `Response.InResponseTo` và `SubjectConfirmationData.InResponseTo` đều là `_req-48f`. SP cần còn lưu trạng thái của AuthnRequest phù hợp; một ID hợp lệ về định dạng nhưng không có request tương ứng là tình huống đáng từ chối trong SP-initiated flow.

**(c) Trả về đâu?** `Response.Destination` và `Recipient` trỏ ACS của SP. Nếu response được POST đến ACS khác hoặc có URL trái cấu hình, đây là dấu hiệu ràng buộc đích thất bại.

**(d) Dành cho SP nào?** `Audience` là SP entity ID. Đây là kiểm tra chống dùng một assertion được cấp cho ứng dụng X đem đăng nhập ứng dụng Y.

**(e) Ai là subject?** `NameID=partner-user-073` với format `persistent`. Đây là tên định danh mà IdP khẳng định, không tự là username/quyền nội bộ. SP cần liên kết với tài khoản local bằng khóa và quy trình phù hợp.

**(f) Hợp lệ đến khi nào?** Hai mốc `Conditions.NotOnOrAfter` và `SubjectConfirmationData.NotOnOrAfter` đều là `10:05:00Z` trong ví dụ; cả hai phải qua kiểm tra riêng. `SessionNotOnOrAfter=18:00:00Z` là thời hạn ngữ cảnh phiên IdP được báo cáo, **không nới thời hạn chấp nhận assertion**.

**(g) Xác thực khi nào?** `AuthnInstant=09:58:30Z` có thể trước `IssueInstant=10:00:00Z`: IdP xác thực người dùng trước rồi mới phát assertion (có thể dựa trên phiên SSO). Hai thời điểm có ý nghĩa khác nhau.

**(h) Thuộc tính nào được khai báo?** `groups` có **hai giá trị**. Không lấy `partner-readers` làm quyền nội bộ nếu chưa có mapping đáng tin. Một SP có thể cho phép đăng nhập nhưng từ chối gọi API nghiệp vụ khi không có quyền.

## 7. Vòng đời thông điệp: từ AuthnRequest tới phiên SP

~~~text
Người dùng          SP (Spring Security)              IdP
    |                        |                          |
    |-- GET /private ------->|                          |
    |<-- redirect AuthnRequest -------------------------|
    |----------------- gửi AuthnRequest ---------------->|
    |                        |            kiểm tra phiên/đăng nhập
    |<------------- trang/HTML POST chứa SAMLResponse --|
    |-- POST SAMLResponse -->| ACS                      |
    |                        |-- parse + verify sig     |
    |                        |-- validate Status/Issuer |
    |                        |-- validate assertion     |
    |                        |-- validate Subject       |
    |                        |-- map principal/roles    |
    |<--- cookie phiên SP ---|                          |
    |-- GET /private ------->| authorize tại SP         |
~~~

Trong **SP-initiated SSO**, SP khởi tạo `AuthnRequest` và ghi lại ID/registration để đối chiếu response. Với **IdP-initiated/unsolicited SSO**, có thể không tồn tại `AuthnRequest` tương ứng; hỗ trợ hay từ chối cách này là lựa chọn chính sách/profile của SP và thư viện. Không tự nới kiểm tra `InResponseTo` của SP-initiated để “fix” lỗi tích hợp.

### SAML Binding: lớp HTTP không phải lớp XML

- **HTTP-Redirect Binding** thường dùng chuyển `AuthnRequest` từ SP tới IdP qua URL; cơ chế biểu diễn/ký request có quy tắc riêng.
- **HTTP-POST Binding** thường dùng trả `Response` từ IdP đến ACS bằng form có field `SAMLResponse` chứa **Base64 của XML**.
- **`RelayState`** là dữ liệu trạng thái được chuyển qua binding, **không phải** phần tử `Assertion` và không phải bằng chứng danh tính. Cần liên kết với request phù hợp, tránh biến `RelayState` thành URL redirect tùy ý.
- Sau khi POST thành công, **SP tạo phiên của chính mình**; XML assertion và cookie phiên SP không phải một.

Bản tin bị Base64 hóa **không che giấu nội dung**, nhất là nếu log form value. Không ghi raw SAMLResponse, assertions hoặc NameID nhạy cảm ra log production; dùng HTTPS và chính sách lưu dữ liệu phù hợp.

## 8. Các mốc thời gian và ID dễ hiểu sai

| Giá trị | Phát sinh ở đâu | Dùng để làm gì |
| --- | --- | --- |
| `AuthnRequest.ID` | SP khi yêu cầu login | Khóa liên kết request-response. |
| `Response.ID` | IdP khi phát response | Định danh thông điệp trả về, phục vụ kiểm soát replay/correlation. |
| `Assertion.ID` | IdP khi phát assertion | Định danh khẳng định; lưu vết/chống replay theo profile. |
| `Response.InResponseTo` | IdP sao từ request | Cho biết response trả lời yêu cầu SP nào. |
| `SubjectConfirmationData.InResponseTo` | IdP trong bearer assertion | Gắn quyền trình assertion với yêu cầu SP cụ thể. |
| `Response.IssueInstant` | IdP khi phát response | Thời điểm tạo response. |
| `Assertion.IssueInstant` | IdP khi phát assertion | Thời điểm tạo assertion (có thể không trùng response). |
| `AuthnStatement.AuthnInstant` | IdP ghi nhận lúc user xác thực | Có thể cũ hơn IssueInstant do tái sử dụng phiên SSO. |
| `Conditions.NotOnOrAfter` | IdP cho assertion | Hạn sử dụng assertion theo Conditions. |
| `SubjectConfirmationData.NotOnOrAfter` | IdP cho bearer confirmation | Hạn được trình assertion theo phương thức confirmation. |
| `AuthnStatement.SessionNotOnOrAfter` | IdP nếu gửi | Giới hạn thời gian phiên xác thực được báo cáo; không phải TTL cho mọi ứng dụng. |
| `AuthnStatement.SessionIndex` | IdP nếu gửi | Định danh/handle phiên IdP, hữu ích trong một số luồng SAML Single Logout. |

Ba ID đầu **không cần bằng nhau**; mỗi cái có vai trò riêng. `InResponseTo` thường trỏ tới **AuthnRequest.ID**, không trỏ tới Response.ID hoặc Assertion.ID. Trong môi trường nhiều IdP/tenant, cần bảo toàn mapping **AuthnRequest ↔ registration/IdP ↔ ACS** để chống gửi response vào ngữ cảnh khác.

Nếu SP chấp nhận Assertion đã hết `NotOnOrAfter` chỉ vì `SessionNotOnOrAfter` còn dài, SP đã **đọc sai đối tượng thời gian**. Một assertion hợp lệ lúc đăng nhập không mặc nhiên làm tất cả phiên ứng dụng bị giới hạn chính xác bởi cùng mốc thời gian; cần chính sách phiên riêng.

## 9. Kiểm tra bảo mật khi SP nhận `Response`

**Không tự viết bộ xác minh SAML bằng việc parse XML thủ công rồi so sánh vài chuỗi.** SP cần thư viện SAML2 đã được kiểm định, metadata/khóa tin cậy đúng và chính sách tương ứng. Trình tự có thể khác giữa phiên bản thư viện, nhưng về mặt bảo mật phải đảm bảo đủ các điều kiện sau:

1. **Chọn đúng registration:** Xác định RP–IdP pair được tin cậy; IdP issuer, binding, ACS, entity ID và credentials phải khớp cấu hình.
2. **Parse XML an toàn:** Chống XXE/entity expansion, giới hạn kích thước, độ sâu; tránh xử lý một payload có nhiều phần tử trùng/đánh lừa parser.
3. **Kiểm tra chữ ký trên đúng đối tượng:** Xác minh XML Digital Signature với certificate/key được tin qua metadata/cấu hình, kiểm tra tham chiếu ID được ký; tránh **XML Signature Wrapping**, nơi chương trình đọc một Assertion không phải Assertion đã được ký.
4. **Xử lý mã hóa có kiểm soát:** Nếu `EncryptedAssertion`/`EncryptedID`/`EncryptedAttribute` xuất hiện, giải mã bằng khóa SP hợp lệ mà vẫn bảo toàn yêu cầu xác minh.
5. **Kiểm tra tầng Response:** `Status` phù hợp; issuer, `Destination`, `InResponseTo`, version, time và binding theo profile/registration.
6. **Kiểm tra tầng Assertion:** issuer, chữ ký và phạm vi được ký, `Conditions`, `AudienceRestriction`, các condition khác bắt buộc và số lượng/vị trí Assertion theo chính sách.
7. **Kiểm tra tầng Subject:** `NameID` đúng format/thỏa thuận, phương thức `bearer` phù hợp, `SubjectConfirmationData.Recipient` trùng ACS, `InResponseTo` đúng request, thời hạn còn hiệu lực.
8. **Ngăn replay:** Một assertion/response được chấp nhận không nên được dùng lại để tạo phiên không giới hạn; duy trì cache ID/nonces/request state khi profile yêu cầu và phù hợp lifetime.
9. **Chỉ khi xác minh thành công:** Tạo `Authentication`/principal, liên kết tài khoản local và thực thi authorization ở ứng dụng. Một claim `group=admin` bên IdP không có nghĩa đương nhiên là `ROLE_ADMIN` trong SP.
10. **Không lỏng hóa policy khi lỗi:** Chênh lệch giờ, metadata cũ, ACS sai hoặc IdP chưa ký đúng cần sửa cấu hình/đồng bộ theo profile, **không bỏ chữ ký/audience/recipient check**.

### 9.1. Phân biệt ký số và mã hóa

| Tính năng | Giải quyết điều gì? | Không giải quyết điều gì? |
| --- | --- | --- |
| XML Digital Signature (`ds:Signature`) | Xác minh nguồn ký và tính toàn vẹn **phần tử XML được ký** qua khóa tin cậy. | Không giữ bí mật dữ liệu; không tự chứng minh đối tượng ngoài phạm vi ký hợp lệ. |
| XML Encryption (`EncryptedAssertion`/`EncryptedID`) | Giữ bí mật nội dung đối với bên nắm khóa giải mã. | Không mặc nhiên chứng minh người phát hành và tính toàn vẹn của assertion theo profile. |
| HTTPS | Bảo vệ kênh vận chuyển giữa browser và endpoint. | Không thay chữ ký SAML trong mô hình response được chuyển qua browser. |
| Base64 trong HTTP-POST | Biểu diễn XML thành chuỗi có thể đưa vào form. | Không mã hóa bảo mật, không xác thực nguồn, không chống replay. |

Một response có thể có **Signature ở Response**, **Signature ở từng Assertion**, cả hai, hoặc kết hợp mã hóa. Không áp quy tắc “phải ký cả hai” cho mọi IdP nếu profile/metadata cho phép một phương án cụ thể; nhưng luôn bảo đảm rằng **toàn bộ assertion dùng để xác thực được bảo vệ bằng chữ ký hợp lệ** theo chính sách. Theo mô hình kiểm tra của Spring Security, thiếu cả chữ ký Response và chữ ký các Assertion là không thể chấp nhận.

### 9.2. Multiple assertions và XML Signature Wrapping

SAML Response có thể chứa nhiều Assertion; các phần tử được ký và các phần tử ứng dụng **đọc** phải là cùng nội dung được xác minh. Nếu hệ thống chỉ tìm `//Assertion[1]/Subject/NameID` bằng XPath tự viết, kẻ tấn công có thể tìm cách đưa một assertion không được bảo vệ vào vị trí đó trong khi signature vẫn khớp một assertion khác. Đây là kiểu rủi ro **XML Signature Wrapping**.

Cách phòng thủ là dùng bộ xác minh SAML chuyên dụng, tuân thủ quy tắc ID uniqueness, signature references và chính sách selection assertion; không xây một parser thứ hai để rút claim sau khi thư viện đã xác thực một đối tượng khác.

## 10. Spring Security SAML2 xử lý Response ra sao?

Với Spring Security Servlet/SAML2 Login, ứng dụng đóng vai **SP/Relying Party**. Các thành phần tiêu biểu:

| Thành phần Spring Security | Vai trò |
| --- | --- |
| `RelyingPartyRegistration` | Cấu hình quan hệ SP–IdP: entity IDs, ACS, metadata, credentials và bindings. |
| `Saml2WebSsoAuthenticationRequestFilter` | Tạo/đưa `AuthnRequest` tới IdP khi khởi tạo đăng nhập. |
| `Saml2WebSsoAuthenticationFilter` | Nhận `SAMLResponse` qua ACS, đưa tới authentication provider. |
| `Saml2AuthenticationToken` | Dữ liệu đầu vào authentication chứa SAML response và registration liên quan. |
| OpenSAML authentication provider | Parse, xác minh chữ ký, giải mã và xác nhận các điều kiện SAML theo version/configuration. |
| `Saml2AuthenticatedPrincipal` | Principal ứng dụng nhận sau xác thực, gồm name/attributes và thông tin registration. |
| `Saml2Authentication` | Kết quả authentication được đặt vào security context; sau đó mới thực thi authorization. |

Tên/phiên bản cụ thể của OpenSAML provider thay đổi theo Spring Security release; ứng dụng thường cấu hình bằng `saml2Login` thay vì tự tạo provider. Mẫu dưới đây nhắm **Java 17 và Spring Boot 3.3.x / Spring Security 6.x**.

### 10.1. Ví dụ ứng dụng SP tối giản

Cấu trúc dự án:

~~~text
saml-structure-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/samlstructure/
    │   ├── SamlStructureApplication.java
    │   ├── SecurityConfig.java
    │   └── PrincipalController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-structure-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // OpenSAML có các artifact do hệ sinh thái Shibboleth phát hành.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Dùng phiên bản Spring Boot/Gradle phù hợp môi trường; repository Shibboleth được dùng theo hướng dẫn dependency của Spring Security. Không cần tự parse XML bằng `DocumentBuilder` để thực hiện đăng nhập.

`src/main/java/com/example/samlstructure/SamlStructureApplication.java`:

~~~java
package com.example.samlstructure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlStructureApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlStructureApplication.class, args);
    }
}
~~~

`src/main/java/com/example/samlstructure/SecurityConfig.java`:

~~~java
package com.example.samlstructure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

`saml2Login` bật xử lý login SAML2; `saml2Metadata` hỗ trợ xuất SP metadata cho đối tác cấu hình. Rule `authenticated()` chỉ yêu cầu đăng nhập; endpoint nghiệp vụ thật cần kiểm tra quyền/tenant ở service. Giữ bảo vệ CSRF và các bộ lọc mặc định; không tắt toàn bộ xác minh chỉ để làm một IdP test đăng nhập thành công.

`src/main/java/com/example/samlstructure/PrincipalController.java`:

~~~java
package com.example.samlstructure;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrincipalController {

    @GetMapping("/")
    public String home() {
        return "Visit /me to start SAML 2.0 login";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameId", principal.getName());
        result.put("registrationId",
            principal.getRelyingPartyRegistrationId());
        result.put("department", principal.getFirstAttribute("department"));
        result.put("sessionIndexes", principal.getSessionIndexes());
        return result;
    }
}
~~~

Sau khi bộ xử lý xác thực thành công, `principal.getName()` thường phản ánh **NameID** của assertion được Spring Security chọn; `getFirstAttribute("department")` lấy giá trị đầu tiên của Attribute trong ví dụ. `getSessionIndexes()` có thể rỗng tùy assertion/IdP. **Không lấy `nameId` hoặc `department` làm quyền quản trị**. Dữ liệu in ra trong demo chỉ để học; giới hạn hoặc bỏ endpoint debug khi triển khai sản xuất.

### 10.2. Cấu hình IdP metadata

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}
~~~

`SAML_IDP_METADATA_URI` là URL metadata **thật** của IdP đối tác mà SP đã quyết định tin. Metadata thường mô tả entity ID, endpoints, certificates và bindings; SP phải được IdP đăng ký đúng entity ID, ACS URL, yêu cầu ký và các chính sách. URL ở phần XML học tập (ví dụ `sp.example.org`) không đại diện cho một IdP có thể đăng nhập ngay.

Endpoint hay gặp trong cấu hình mặc định:

~~~text
Bắt đầu SP-initiated SSO:  GET /saml2/authenticate/partner
ACS nhận SAMLResponse:      POST /login/saml2/sso/partner
Xuất metadata SP:           GET /saml2/metadata/partner
~~~

Khi triển khai thật, cấu hình reverse proxy, `{baseUrl}`, HTTPS và certificate/metadata phải khớp URL công khai của SP. Bản thân ứng dụng demo **không tạo IdP** và không tự phát hành chữ ký SAML.

### 10.3. Chạy demo và hiểu kết quả

Nếu máy đã có Gradle phù hợp hoặc dự án có Gradle Wrapper hợp lệ:

~~~bash
gradle bootRun
~~~

Với IdP thật đã cấu hình và môi trường network/metadata hoạt động:

1. Mở `http://localhost:8080/`, nhận chuỗi hướng dẫn công khai.
2. Mở `http://localhost:8080/me` khi chưa đăng nhập; Spring Security khởi tạo SAML2 login với IdP đã đăng ký.
3. IdP xác thực người dùng và gửi SAMLResponse qua HTTP-POST về ACS. Spring Security/OpenSAML xác minh response và assertion.
4. Sau xác thực hợp lệ, `/me` hiển thị JSON có `nameId`, `registrationId`, `department`, `sessionIndexes`. Các giá trị này **phụ thuộc IdP**, không có output JSON cố định.
5. Nếu không cấu hình metadata/certificate/ACS đúng, ứng dụng có thể không khởi động hoặc login thất bại. Lỗi không thể sửa bằng cách copy XML chưa ký ở mục 6 vào POST.

**Chỉ kiểm thử cấu trúc với XML ở mục 6** bằng mắt hoặc công cụ hiển thị XML cục bộ. **Không** POST ví dụ chưa ký như một SAMLResponse “hợp lệ” và không tuyên bố nó đã được xác thực.

### 10.4. Ranh giới giữa validation và authorization trong Spring

Spring Security biến SAML Response thành principal **sau khi** bước xác minh hoàn tất. Nhưng việc IdP khẳng định `NameID=partner-user-073` chỉ trả lời ai đã được IdP xác thực; SP mới quyết định:

- Người này có được liên kết với local account nào và thuộc partner/tenant nào?
- Local account có đang active hay bị chặn?
- Người này có `APP_ORDER_READ` hay quyền nào khác?
- Request có nhằm vào đúng tài nguyên của partner được phép hay không?

Một thiết kế an toàn có thể dùng khóa liên kết **(IdP entity ID, NameID + format/qualifiers theo hợp đồng)** để tra cứu tài khoản. Không gán `ROLE_ADMIN` vì Attribute tên `groups` chứa chữ `admin`. Phần phân quyền nên có lớp riêng được test độc lập với việc parse SAML.

## 11. Các lỗi thường gặp khi đọc Response, Assertion và Subject

| Lỗi hiểu/triển khai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`SAMLResponse` là XML đã mã hóa nên có thể tin.” | Base64 chỉ biến đổi biểu diễn chuỗi. | Giải mã qua thư viện SAML và xác minh chữ ký/điều kiện. |
| Chỉ nhìn `Status=Success` rồi cho login. | Status chỉ là trạng thái xử lý protocol. | Kiểm tra Assertion, Subject, điều kiện và signature. |
| So sánh `Response.ID` với `InResponseTo`. | Hai ID có vai trò khác nhau. | `InResponseTo` phải đối chiếu với `AuthnRequest.ID`. |
| Xem `Destination`, `Recipient` và `Audience` là cùng một URL. | Hai giá trị đầu thường là ACS; Audience là SP entity ID. | Ràng buộc từng giá trị với nguồn cấu hình riêng. |
| Dùng `AuthnInstant` để suy ra hạn Assertion. | Thời điểm xác thực không phải expiration của bearer assertion. | Kiểm tra `Conditions` và `SubjectConfirmationData`. |
| Coi `SessionNotOnOrAfter` là hạn dùng assertion. | Đây là thông tin phiên IdP. | Tách session lifetime khỏi thời hạn chấp nhận assertion. |
| Chấp nhận `NameID=email` làm khóa local user bất biến. | Email đổi/tái sử dụng; identifier phụ thuộc format và IdP. | Thiết kế identity link theo issuer/nameID/qualifier. |
| Tự tìm XPath “Assertion đầu tiên” trước xác minh chữ ký. | Có thể tiêu thụ assertion không phải đối tượng được ký. | Dùng OpenSAML/Spring Security, chống signature wrapping. |
| Tin certificate chỉ vì nằm trong `ds:KeyInfo`. | Kẻ gửi có thể tự nhúng khóa của chính mình. | Anchor trust vào metadata/certificate đáng tin cậy đã cấu hình. |
| Cho phép replay trong thời hạn 5 phút không giới hạn. | Time validity không tự tạo one-time-use. | Correlation request, cache IDs/replay theo profile/chính sách. |
| Bỏ qua nhiều `AttributeValue` của một attribute. | SAML cho phép giá trị nhiều phần tử. | Dùng danh sách và quy tắc mapping phù hợp. |
| Lấy external group làm quyền local ngay. | IdP có thẩm quyền về identity/claim theo hợp đồng, không mặc nhiên về quyền nghiệp vụ. | Mapping least privilege và kiểm tra ownership/tenant. |
| Vô hiệu kiểm tra issuer/recipient khi reverse proxy sai. | Che lỗi cấu hình thành rủi ro xác thực sai đối tượng. | Sửa base URL, ACS, metadata và forwarded headers. |
| Bỏ qua `EncryptedAssertion` do không đọc được XML thường. | Assertion có thể được mã hóa, cần khóa giải mã của SP. | Khai báo decryption credentials, dùng provider SAML chuẩn. |

## 12. Bài luyện tập: phân tích và đối chiếu một Response

Dùng XML minh họa ở mục 6. Không cần IdP thật để làm các câu hỏi **đọc cấu trúc**; muốn kiểm thử Spring Security chấp nhận đăng nhập, phải có payload thật được ký và môi trường tích hợp đúng.

### Bài A — Đọc các quan hệ

1. Xác định **hai issuer** và nơi chúng xuất hiện.
2. Xác định **ID của Response**, **ID của Assertion** và **ID của AuthnRequest được trả lời**.
3. Chỉ ra ba giá trị **Destination**, **Recipient**, **Audience** và giải thích vì sao Audience khác URL ACS.
4. Xác định **NameID**, **NameID Format**, **bearer confirmation method** và thời hạn bearer.
5. Tìm **AuthnInstant**, **IssueInstant**, **SessionNotOnOrAfter**; giải thích tại sao không thể thay thế lẫn nhau.
6. Kể tên **hai giá trị** của Attribute `groups` và nêu vì sao đây không tự là permission SP.

### Bài B — Tình huống sửa một trường

| Biến thể so với một Response đã được ký hợp lệ | Điều cần xảy ra tại SP |
| --- | --- |
| `Recipient` trỏ sang ACS khác. | Từ chối vì bearer confirmation không dành cho ACS hiện tại. |
| `Audience` là entity ID của SP khác. | Từ chối assertion vì không dành cho SP này. |
| `InResponseTo` trỏ ID request không tồn tại ở SP-initiated flow. | Từ chối do correlation thất bại. |
| `Conditions.NotOnOrAfter` đã qua. | Từ chối assertion đã hết hạn. |
| `NameID` thay đổi sau khi response được ký. | Chữ ký/phạm vi bảo vệ không còn hợp lệ; từ chối. |
| `Status` báo `AuthnFailed`. | Không tạo phiên đăng nhập thành công. |
| Một response đã được chấp nhận được gửi lại. | Bị chặn theo replay/request-state policy; không tạo phiên tùy ý. |
| Có `groups=admin` nhưng local user không có quyền. | Có thể xác thực thành công, nhưng endpoint quản trị phải trả 403. |

### Bài C — Tự trả lời ngắn

**Câu 1.** “Assertion có `Conditions` còn hạn, vậy `SubjectConfirmationData.NotOnOrAfter` đã hết hạn có được login không?”  
**Đáp án:** Không. Các kiểm tra áp dụng phải **đồng thời** hợp lệ; hạn `Conditions` không gia hạn bearer confirmation.

**Câu 2.** “Có thể xác minh chữ ký bằng khóa bất kỳ được nhúng sẵn trong XML không?”  
**Đáp án:** Không. Khóa ký phải nối được tới **trust anchor/metadata IdP** được SP cấu hình; XML do đối tác gửi không tự quyết định ai đáng tin.

**Câu 3.** “Một tên `<saml:Subject>` có đủ chứng minh người đó được vào trang quản trị không?”  
**Đáp án:** Không. Subject là định danh trong assertion; quyền local do SP quyết định sau khi liên kết tài khoản và kiểm tra chính sách.

**Câu 4.** “Tại sao `AuthnInstant` có thể sớm hơn `Response.IssueInstant`?”  
**Đáp án:** IdP có thể đã xác thực user trước đó và dùng lại phiên SSO để phát Response mới.

**Câu 5.** “Vì sao `Assertion.ID`, `Response.ID` và `AuthnRequest.ID` phải phân biệt?”  
**Đáp án:** Ba ID định danh **ba đối tượng khác nhau**. `InResponseTo` là quan hệ trả lời về **request ID**, còn assertion/response ID phục vụ định danh và kiểm soát riêng.

## 13. Ghi nhớ và checklist trước khi chấp nhận SAML2 Login

- **Response** là vỏ protocol: issuer, destination, request correlation, status.
- **Assertion** mang khẳng định của IdP: subject, các điều kiện, sự kiện xác thực và thuộc tính.
- **Subject** chỉ người được khẳng định: NameID và phương thức/điều kiện trình assertion.
- **Recipient/Destination là đích ACS**, còn **Audience là SP entity ID**; `InResponseTo` trỏ AuthnRequest.
- **Conditions**, **SubjectConfirmationData** và **AuthnStatement** mô tả các loại thời gian khác nhau.
- **Chữ ký XML + khóa tin cậy + điều kiện profile + chống replay** là các cổng bảo mật bắt buộc trước khi tạo principal.
- **Spring Security/OpenSAML** thực hiện xác minh protocol; **ứng dụng** tiếp tục liên kết local account và phân quyền nghiệp vụ.
- XML minh họa chưa ký **chỉ để học**: nó không thể chứng minh một login thật đã được xác thực.

### Tài liệu tham khảo

- [OASIS — Assertions and Protocols for SAML V2.0 (SAML Core)](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) — cấu trúc Response, Assertion, Subject, Conditions, statements.
- [OASIS — Profiles for SAML V2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — quy tắc Web Browser SSO, bearer subject confirmation, bindings/correlation.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — các filter và thành phần RP.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) — xác minh response/assertion và principal.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — cấu hình metadata của SP/IdP.
