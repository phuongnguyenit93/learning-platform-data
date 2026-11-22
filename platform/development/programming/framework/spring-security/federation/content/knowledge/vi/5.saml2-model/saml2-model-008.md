# Chữ ký ở Response, Assertion và phân biệt với assertion được mã hóa trong SAML 2.0

> **Chủ đề:** Spring Security – federation · **Nhóm:** Mô hình SAML2. Bài học giải thích chính xác **chữ ký XML ở `samlp:Response`**, **chữ ký ở `saml:Assertion`**, **`saml:EncryptedAssertion`**, quan hệ ký–mã hóa và cách Service Provider (SP) kiểm tra trước khi cho người dùng đăng nhập.

## 1. Vấn đề cần hiểu

Khi Identity Provider (**IdP**, còn gọi là Asserting Party) hoàn tất đăng nhập, trình duyệt người dùng chuyển một `SAMLResponse` về Assertion Consumer Service (**ACS**) của ứng dụng **Service Provider (SP)**. Thông tin có thể bao gồm:

- **`samlp:Response`:** phong bì giao thức chứa `ID`, `InResponseTo`, `Destination`, `Issuer`, `Status` và một hay nhiều assertion.
- **`saml:Assertion`:** khẳng định do IdP phát hành về người dùng, thời điểm, điều kiện sử dụng, đối tượng nhận (audience), phương pháp xác thực, thuộc tính/nhóm.
- **`ds:Signature`:** chữ ký XML (XML Digital Signature/XMLDSig) để kiểm nguồn phát hành tin cậy và **tính toàn vẹn** của **đúng phần XML được ký**.
- **`saml:EncryptedAssertion`:** một assertion đã được mã hóa theo XML Encryption (XMLEnc), thường để bảo vệ thông tin người dùng khỏi người cầm thông điệp trung gian, bao gồm trình duyệt.
- **Metadata và credential:** danh sách khóa/chứng thư tin cậy cho kiểm chữ ký IdP và khóa giải mã thuộc SP.

Mọi dữ liệu trong browser POST phải được coi là **không đáng tin trước khi kiểm chứng**. HTTPS chỉ bảo vệ các kết nối truyền tải; chính trình duyệt vẫn mang payload nên có thể sửa tham số `SAMLResponse`. Chỉ Base64-decode XML rồi lấy `NameID` hoặc `Role` là **không phải xác thực SAML**.

**Luận điểm trung tâm:**
- **Ký** trả lời: "Thông điệp/phần XML này có được bên giữ khóa ký đáng tin phát hành và còn nguyên vẹn không?"
- **Mã hóa** trả lời: "Ai có thể đọc nội dung được mã hóa?"
- **Kiểm điều kiện SAML** trả lời: "Assertion đã được xác thực này có được phép dùng **ở SP này, cho request/phiên này, tại thời điểm này** không?"
- Không một bước nào có thể thay thế toàn bộ các bước còn lại.

## 2. Cấu trúc XML và vị trí chữ ký

SAML 2.0 dùng XML namespaces: `samlp` cho protocol, `saml` cho assertion, `ds` cho XML Signature và `xenc` cho XML Encryption. Tên prefix chỉ là cách viết; validator phải làm việc với namespace/schema thực, không so chuỗi theo prefix.

### 2.1. Chữ ký ở Response

Minh họa **lược giản**, **không phải SAML Response hợp lệ để chạy thật**: `...` thay cho trường, ký số và dữ liệu định danh đầy đủ.

~~~xml
<samlp:Response ID="_resp001"
                Destination="https://sp.example.org/login/saml2/sso/corp"
                InResponseTo="_request001"
                xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <saml:Issuer>https://idp.example.org</saml:Issuer>

  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_resp001">
        <!-- Transforms/DigestMethod/DigestValue không hiển thị -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue, KeyInfo tùy profile không hiển thị -->
  </ds:Signature>

  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assert001">
    <!-- Subject, Conditions, AuthnStatement, AttributeStatement -->
  </saml:Assertion>
</samlp:Response>
~~~

Ở đây `ds:Signature` là **con trực tiếp của Response**, `ds:Reference URI="#_resp001"` trỏ đến Response. Với Reference, transforms và chữ ký được **xác minh đúng**, chữ ký bảo vệ vùng XML của Response được ký, bao gồm assertion lồng bên trong; không bắt buộc assertion có chữ ký riêng nếu profile/chính sách SP cho phép ký Response.

**Điều không được suy ra:**
- Thấy thẻ `ds:Signature` ở Response **không chứng minh** chữ ký hợp lệ.
- Chữ ký chỉ có ý nghĩa khi đã đối chiếu khóa ký với **IdP tin cậy trong đăng ký SP** và ràng buộc Reference với đúng Response được xử lý.
- Nếu lập trình viên tự tìm một `Assertion` khác ở ngoài phần XML được bảo vệ, chữ ký Response đúng vẫn có thể bị lợi dụng bằng **XML Signature Wrapping**.
- Chữ ký Response **không tự giữ bí mật** `NameID`, email hay group; browser có thể Base64-decode và đọc assertion dạng plaintext.

### 2.2. Chữ ký ở Assertion

Minh họa lược giản:

~~~xml
<samlp:Response ID="_resp002"
                Destination="https://sp.example.org/login/saml2/sso/corp"
                xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <saml:Issuer>https://idp.example.org</saml:Issuer>

  <saml:Assertion ID="_assert002">
    <saml:Issuer>https://idp.example.org</saml:Issuer>
    <ds:Signature>
      <ds:SignedInfo>
        <ds:Reference URI="#_assert002">
          <!-- Transforms, digest ... -->
        </ds:Reference>
      </ds:SignedInfo>
      <!-- SignatureValue ... -->
    </ds:Signature>
    <saml:Subject>...</saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Ở đây chữ ký nằm **bên trong Assertion** và Reference trỏ tới `_assert002`. Nó bảo vệ nội dung assertion theo biến đổi/canonicalization áp dụng. **Phần vỏ Response không được ký bởi chữ ký Assertion**. Vì thế SP vẫn phải kiểm `Destination`, `InResponseTo`, issuer/registration, ACS và ngữ cảnh request theo quy tắc protocol; không tự tin các trường Response chỉ vì nội dung assertion có chữ ký hợp lệ.

Nếu một Response chứa **nhiều assertion**, không thể lấy chữ ký của một assertion để mặc nhiên tin assertion khác. Với Spring Security SAML2 mặc định được tài liệu mô tả: **Response được ký hợp lệ hoặc toàn bộ assertion cần có chữ ký hợp lệ**; một chữ ký bất hợp lệ ở assertion là lỗi, ngay cả khi có phần khác đã ký.

### 2.3. Cả Response và Assertion được ký

IdP cũng có thể:

~~~text
Response [ds:Signature -> Response.ID]
└── Assertion [ds:Signature -> Assertion.ID]
    └── Subject / Conditions / AuthnStatement / Attributes
~~~

Hai chữ ký bảo vệ **hai phạm vi XML khác nhau**. SP phải kiểm các chữ ký mà nó yêu cầu và không bỏ qua một chữ ký có mặt nhưng **không hợp lệ**. Cấu hình "ký cả hai" có thể phục vụ hợp đồng federation, yêu cầu đối tác hoặc kiểm soát cụ thể, nhưng không biến assertion hết hạn thành hợp lệ hay thay thế kiểm audience/recipient.

**Chú ý về chính sách:** Tùy binding/profile, metadata và chính sách SP/IdP, một bên có thể yêu cầu "sign Response", "sign Assertion" hoặc "both". Với **SAML Web Browser SSO HTTP-POST**, errata OASIS làm rõ **Response hoặc các Assertion trong Response phải được ký**; chính sách của một đối tác cụ thể có thể chặt hơn. Không áp dụng máy móc quy tắc đó cho mọi profile/binding SAML.

## 3. Chữ ký XML thực sự kiểm tra điều gì?

Một `ds:Signature` không phải một chuỗi chữ ký gắn kèm tùy ý. XMLDSig có:

1. **`ds:SignedInfo`** gồm `CanonicalizationMethod`, `SignatureMethod` và một hay nhiều `Reference`.
2. **`ds:Reference URI="#ID"`** xác định **phần XML được bảo vệ**. `Transforms` và `DigestMethod/DigestValue` mô tả cách chuẩn hóa/hash nội dung được tham chiếu.
3. **`ds:SignatureValue`** là giá trị chữ ký cho `SignedInfo` đã canonicalize.
4. **`ds:KeyInfo`** (nếu có) gợi ý khóa/chứng thư; **không được tự tin khóa do payload không đáng tin cung cấp**.

Quy trình kiểm đúng: dùng parser XML an toàn; giải tham chiếu ID/transform theo quy tắc thư viện được kiểm nghiệm; kiểm digest và signature; **chọn khóa xác minh từ bộ IdP verification credentials đã được SP tin cậy**; ràng buộc kết quả kiểm với **đúng node Assertion/Response mà nghiệp vụ đọc**.

Chữ ký số thường dùng private key của **IdP**; SP có **public key/chứng thư X.509 của IdP** để xác minh. Chứng thư dùng trong SAML metadata thường là cách phân phối và quản trị trust theo federation, không mặc định dựa vào kiểm tra tên miền/CA của TLS. Quản lý thay khóa và IdP metadata quan trọng hơn việc đơn thuần nhìn thấy một `X509Certificate` trong `KeyInfo` do browser gửi.

Hãy phân biệt các kiểm tra sau:

| Kiểm tra | Giải quyết vấn đề gì? | Không thay thế được |
|---|---|---|
| XML Signature + trusted IdP key | Nguồn phát hành và tính toàn vẹn của vùng XML ký | Time, audience, recipient, state/replay |
| Issuer/registration trust | Xác thực liên kết đúng IdP đã đăng ký | Signature validation |
| AudienceRestriction | Assertion dành cho SP/entityID này | Recipient/ACS và thời hạn |
| Recipient/Destination | Assertion/Response được trả về endpoint phù hợp | Thời hạn và request correlation |
| InResponseTo + session/request context | Phản hồi thuộc yêu cầu đăng nhập đang chờ, khi SP-initiated | Chữ ký và chống replay tổng thể |
| NotBefore/NotOnOrAfter | Assertion chỉ hợp lệ trong cửa sổ thời gian | Signature và session lifecycle |
| SubjectConfirmationData | Subject có thể được SP chấp nhận với ràng buộc nhận/chứng thực | Các điều kiện khác |
| Replay detection | ID/response/assertion/ticket không bị tái sử dụng trái phép | Xác minh ký số |
| Mã hóa assertion | Bảo mật nội dung đối với bên không có decryption key | Xác thực bên gửi |

**Ví dụ:** Assertion được ký hợp lệ nhưng `Audience` là một SP khác thì **không được dùng** để đăng nhập SP hiện tại. Assertion hợp lệ nhưng `NotOnOrAfter` đã qua cũng bị từ chối. Một assertion chứa `role=admin` chỉ nên ánh xạ thành quyền nếu được ký/bao phủ đáng tin và chính sách phân quyền cho phép.

## 4. EncryptedAssertion là gì? Khác chữ ký ở đâu?

Thay vì đặt `<saml:Assertion> ... </saml:Assertion>` có thể đọc được trong XML, IdP có thể tạo:

~~~xml
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                xmlns:xenc="http://www.w3.org/2001/04/xmlenc#"
                ID="_resp003">
  <saml:Issuer>https://idp.example.org</saml:Issuer>
  <saml:EncryptedAssertion>
    <xenc:EncryptedData Type="http://www.w3.org/2001/04/xmlenc#Element">
      <xenc:EncryptionMethod Algorithm="..."/>
      <xenc:CipherData>
        <xenc:CipherValue>BASE64_CIPHERTEXT_PLACEHOLDER</xenc:CipherValue>
      </xenc:CipherData>
    </xenc:EncryptedData>
    <!-- EncryptedKey/KeyInfo có thể được đặt tại vị trí thích hợp -->
  </saml:EncryptedAssertion>
</samlp:Response>
~~~

Đây là **khung minh họa, không phải XML Encryption hợp lệ hoàn chỉnh**. Chuẩn mã hóa dùng thuật toán đối xứng cho nội dung và thường bảo vệ khóa nội dung bằng khóa công khai của SP (hybrid encryption). Chỉ SP có **private key giải mã** đúng mới đọc assertion được. `EncryptedKey` có thể xuất hiện trong cấu trúc XML Encryption theo cách mà bộ thư viện quản lý; không suy luận vị trí cố định hay tự phân tích chuỗi Base64 để thay thư viện.

### 4.1. Mỗi cơ chế đảm nhiệm một mục đích

| Khía cạnh | Chữ ký Response | Chữ ký Assertion | EncryptedAssertion |
|---|---|---|---|
| Vị trí | `ds:Signature` thuộc Response | `ds:Signature` thuộc Assertion | `saml:EncryptedAssertion` thay cho assertion rõ |
| Mục đích chính | Bảo vệ Response và nội dung mà chữ ký bao phủ | Bảo vệ assertion cụ thể | Giữ bí mật assertion |
| Bên tạo | IdP ký bằng khóa ký | IdP ký bằng khóa ký | IdP mã hóa cho SP bằng khóa/certificate giải mã SP |
| Bên kiểm/xử lý | SP dùng verification credential IdP | SP dùng verification credential IdP | SP dùng decryption private key |
| Người có SAML POST đọc NameID? | **Có thể**, nếu assertion plaintext | **Có thể**, nếu assertion plaintext | Thường **không**, nếu mã hóa đúng và khóa bí mật an toàn |
| Có bảo vệ khỏi sửa/tạo assertion giả? | Có, **nếu chữ ký hợp lệ và bao phủ đúng assertion** | Có, **cho assertion được ký đúng** | **Không đủ**, chỉ từ đặc tính bí mật; vẫn cần tính toàn vẹn/xác thực và policy |
| Có thay thế kiểm audience/time? | Không | Không | Không |

**Giải thích quan trọng:** "Đã mã hóa" không đồng nghĩa "đã ký". Một kẻ tấn công có thể có **public certificate của SP** (thường được công bố trong metadata) và về nguyên lý tạo ciphertext gửi tới SP; hệ thống **không được coi khả năng giải mã là bằng chứng IdP đã phát hành**. Ngay cả khi dùng authenticated encryption để chống sửa ciphertext, yêu cầu **xác thực issuer/federation** và các điều kiện SAML vẫn tồn tại.

Tương tự, "đã ký" không đồng nghĩa "đã mã hóa": chữ ký không giấu email, thuộc tính nhân sự, mã định danh hoặc group của người dùng trong browser POST. HTTPS là cần thiết nhưng khác với **mã hóa end-to-end assertion tới SP** vì browser là một điểm trung gian trong HTTP-POST binding.

### 4.2. Ký và mã hóa có thể kết hợp

Bốn mô hình hay gặp:

| Mô hình | Sơ đồ | Cách SP hiểu |
|---|---|---|
| A. Response ký; Assertion rõ không ký | `Signed(Response[Plain Assertion])` | Chữ ký Response bảo vệ assertion nằm trong Response ký |
| B. Response không ký; Assertion rõ được ký | `Response[Signed(Assertion)]` | Kiểm từng assertion, sau đó quy tắc Response/request |
| C. Response ký; Assertion đã mã hóa | `Signed(Response[EncryptedAssertion])` | Kiểm chữ ký ngoài rồi giải mã; ciphertext nằm trong Response ký |
| D. Assertion được ký **rồi** mã hóa | `Response[Encrypt(Signed(Assertion))]` | Giải mã trước để thấy chữ ký assertion, sau đó xác minh chữ ký bên trong |

Có thể kết hợp **C + D**: ký assertion, mã hóa assertion đã ký, rồi ký Response bên ngoài. Điều này dẫn tới **hai chữ ký ở hai tầng khác nhau** và hai thao tác xác minh tương ứng.

Chữ ký Response có thể bao phủ **ciphertext** của `EncryptedAssertion` mà không cần nhìn thấy plaintext. Chữ ký Assertion nằm **bên trong ciphertext** nếu chính assertion được ký trước khi mã hóa.

### 4.3. Thứ tự sign/encrypt và verify/decrypt

Nếu IdP thực hiện:

~~~text
1. Tạo Assertion rõ
2. Ký Assertion: Signed(Assertion)
3. Mã hóa Assertion đã ký: Encrypt(Signed(Assertion))
4. Đưa EncryptedAssertion vào Response
5. (Tùy cấu hình) ký Response bao ngoài
~~~

thì SP phải thực hiện theo thứ tự logic **ngược**:

~~~text
1. Nếu Response có chữ ký, xác minh chữ ký Response hợp lệ
2. Giải mã EncryptedAssertion bằng private key SP
3. Xác minh chữ ký Assertion vừa giải mã (nếu có)
4. Kiểm issuer, audience, subject confirmation, thời hạn, replay
5. Chỉ sau cùng tạo phiên đăng nhập và cấp quyền
~~~

Trong thư viện, thứ tự chính xác của các phép kiểm cùng lớp có thể được tối ưu nhưng **không được dùng thông tin chưa xác minh để quyết định quyền**. Cần gắn bước giải mã với kiểm tính toàn vẹn/xác thực phù hợp: errata OASIS cảnh báo về **malleability của một số chế độ mã hóa CBC** và khuyến nghị xác thực toàn vẹn ciphertext **trước khi xử lý**. Với `EncryptedAssertion` dùng mã hóa CBC, OASIS Web Browser SSO errata nói Response **SHOULD** được ký để bảo vệ ciphertext. Thuật toán authenticated encryption hiện đại cần tương thích IdP/SP và chính sách mật mã; không tự chọn algorithm không được thư viện hỗ trợ.

**Trường hợp mã hóa thành phần bên trong một Assertion đã ký:** Nếu mã hóa một `NameID` hay `Attribute` trước rồi ký Assertion, cần **kiểm chữ ký assertion trước khi giải mã phần tử** để không làm đổi nội dung XML đã được ký. Đây là lý do một số thư viện tách decrypter của Response và của Assertion.

## 5. Tại sao Response đã ký vẫn cần kiểm Assertion?

Có hai ý khác nhau:

1. **Kiểm chữ ký:** Với profile và bộ xác minh đúng, chữ ký Response bảo vệ nội dung assertion **nằm trong Response được ký**, nên assertion đó không nhất thiết có chữ ký riêng. Theo tài liệu Spring Security SAML2 Login, mặc định **Response hoặc tất cả Assertions phải được ký**, và chữ ký có mặt nhưng sai sẽ bị từ chối.
2. **Kiểm điều kiện của Assertion:** Chữ ký Response chỉ đảm bảo dữ liệu không bị đổi và đến từ signer đáng tin; nó **không** đảm bảo assertion chưa hết hạn, dành đúng SP hoặc đủ quyền. Chính các điều kiện ấy phải được đọc và kiểm **sau khi bảo đảm tính toàn vẹn**.

Cùng một cách, chữ ký Assertion không miễn trách nhiệm kiểm thông tin yêu cầu/callback nằm ở Response. Nếu IdP không ký Response, các trường ngoài Assertion không tự được bảo vệ bởi chữ ký Assertion; SP phải thực hiện validation đúng profile với thông tin đã tin cậy về endpoint/registration/request.

**Ví dụ phản chứng:** Một Response ký hợp lệ chứa assertion đúng chữ ký nhưng có `NotOnOrAfter` trong quá khứ. Chữ ký hợp lệ **và** nội dung đã được bảo vệ chính xác; kết quả vẫn là **đăng nhập thất bại vì expired**.

## 6. Trust, certificate và các khóa phải đặt đúng phía

Trong giao tiếp SAML ký + mã hóa, có thể có **ba** cặp khóa khác nhau:

| Công việc | Ai giữ private key? | Ai cần public certificate/key? |
|---|---|---|
| IdP **ký Response/Assertion** | **IdP** | **SP** để xác minh |
| IdP **mã hóa Assertion gửi SP** | **SP** giữ private key giải mã | **IdP** lấy public certificate của SP để mã hóa |
| SP **ký AuthnRequest/LogoutRequest** nếu cần | **SP** | **IdP** để xác minh yêu cầu từ SP |

Đừng nhầm **IdP verification certificate** với **SP decryption certificate**: cả hai có thể là X.509, nhưng chủ sở hữu, vai trò và khóa private khác nhau. Một tổ chức đôi khi tái sử dụng keypair, nhưng tốt hơn nên quản trị theo mục đích, quyền truy cập, hạn dùng, rotation và yêu cầu đối tác.

**Metadata SAML** thường giúp phân phối thông tin `entityID`, endpoint, binding và `KeyDescriptor use="signing"/"encryption"`. Tuy nhiên:
- Chỉ tin metadata nhận từ kênh/quy trình đáng tin, không tự nạp một metadata URL không xác minh do request chỉ đến.
- Cấu hình verification credential có thể chứa nhiều cert đồng thời trong giai đoạn **rotation**; vẫn phải gắn với đúng IdP/issuer.
- Không để SP decryption private key trong Git, log, image công khai hoặc thư mục web; cấp quyền file tối thiểu/secret storage được quản lý.
- Có thể cần overlap cert cũ/mới trong rollout. Lỗi "certificate mismatch" phải được chẩn đoán có kiểm soát; **không tắt signature validation** để làm login chạy.

**TLS** vẫn phải sử dụng cho ACS, IdP SSO endpoint, metadata fetch và luồng trao đổi khóa. Chữ ký SAML không thay thế HTTPS, cũng như HTTPS không làm thay công việc xác minh SAML.

## 7. Spring Security/OpenSAML xử lý Response và Assertion như thế nào?

Trong ứng dụng **Spring MVC/Servlet** dùng `spring-security-saml2-service-provider`, Spring Security làm **SAML SP**. Tài liệu Spring Security mô tả luồng:

1. HTTP POST đến ACS với tham số `SAMLResponse` được filter `Saml2WebSsoAuthenticationFilter` tiếp nhận.
2. `Saml2AuthenticationTokenConverter` tạo authentication token và resolve `RelyingPartyRegistration` của IdP được cấu hình.
3. `OpenSaml5AuthenticationProvider` (trong nhánh tài liệu dùng OpenSAML 5) giải mã serialization/XML và **kiểm chữ ký Response** nếu có; sai thì fail.
4. Provider **giải mã các `EncryptedAssertion`**; lỗi giải mã thì fail.
5. Kiểm các giá trị thuộc Response như `Issuer`, `Destination`.
6. **Kiểm chữ ký từng Assertion**: chữ ký hiện diện nhưng sai thì fail; nếu cả Response và mọi Assertion đều không có chữ ký thì fail. Response ký hoặc **mọi** assertion ký là điều kiện mặc định được mô tả.
7. Giải mã các phần tử có thể mã hóa **bên trong Assertion**, như `EncryptedID` hoặc `EncryptedAttribute`, tại giai đoạn phù hợp để không phá chữ ký assertion.
8. Kiểm hạn dùng, `SubjectConfirmation`, `AudienceRestriction` và các validation liên quan.
9. Sau các bước thành công mới tạo `Saml2AuthenticatedPrincipal` và `Saml2Authentication`, đặt vào security context.

Đây là **khái quát của pipeline mặc định trong tài liệu**, không thay thế kiểm tra cấu hình phiên bản đang dùng. Việc tùy biến response/assertion validator, decrypter, resolver hoặc AuthenticationManager có thể thay đổi cách bảo vệ; tuyệt đối không bỏ các kiểm tra bắt buộc.

Tài liệu cũng tách hai điểm mở rộng giải mã: `setResponseElementsDecrypter` để xử lý phần tử ở cấp Response (bao gồm EncryptedAssertion) và `setAssertionElementsDecrypter` để xử lý phần tử trong Assertion, vì **giải mã thành phần bên trong một Assertion đã ký quá sớm** có thể làm chữ ký không còn hợp lệ. Không thay thế ngẫu nhiên thứ tự của hai decrypter khi customize.

## 8. Ví dụ Spring Boot 3/4 và Spring Security tương ứng

### 8.1. Dependency và ứng dụng Java

Ứng dụng **Servlet** cần ít nhất web, security và SAML2 SP module (phiên bản do Spring Boot BOM quản lý). Đoạn Maven dependency dưới đây **không phải pom.xml hoàn chỉnh**; đưa vào phần `<dependencies>` của một project Spring Boot đã được cấu hình Java 17+ và dependency management:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Một số phiên bản OpenSAML từng yêu cầu repository riêng theo hướng dẫn Spring Security/BOM. Dùng dependency versions và Maven repositories **được tài liệu nhánh dự án yêu cầu**, không trộn Spring Security 6 và 7 theo đoán.

Tệp `src/main/java/com/example/sso/SamlSecurityApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SamlSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP demo";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }
}
~~~

Code có import và cấu trúc Java hợp lệ với Spring Security Servlet DSL phù hợp; tuy nhiên **không chạy bằng `javac` đơn độc** vì phụ thuộc Spring Boot/Security và IdP. Trong dự án Maven có Maven Wrapper, sau khi cấu hình credential và SP với IdP, chạy:

~~~bash
./mvnw spring-boot:run
~~~

`GET /` trả nội dung HTTP `SAML SP demo` (khi server khởi động thành công). `GET /private` yêu cầu đăng nhập SAML và, nếu IdP xác thực/Response được chấp nhận, trả `Authenticated`. Không giả định console stdout, URL chuyển hướng hoặc người dùng thực khi chưa có IdP chạy.

### 8.2. Cấu hình ký và giải mã là **hai loại credential khác nhau**

Ví dụ `src/main/resources/application.yml` (**đường dẫn minh họa**; dùng cert/key thật đã cấu hình bên IdP, không copy private key vào repo):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://sp.example.org/saml2/service-provider-metadata/corporate"
            acs:
              location: "https://sp.example.org/login/saml2/sso/corporate"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml-sp-decrypt-key.pem"
                  certificate-location: "file:/run/secrets/saml-sp-decrypt-cert.pem"
            assertingparty:
              entity-id: "https://idp.example.org/entity"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "file:/etc/saml/idp-signing.crt"
~~~

**Lưu ý phiên bản thuộc tính:** Tên cấu hình và chỗ khai báo ACS/service-provider tùy Spring Boot version. Trước khi sử dụng nguyên dạng, đối chiếu `Saml2RelyingPartyProperties` của Spring Boot đang chạy; cách ít rủi ro khi IdP có metadata đáng tin là dùng `assertingparty.metadata-uri` và bổ sung `decryption.credentials`. Các giá trị URL, entityID và đường dẫn ở trên chỉ minh họa; nếu IdP/SP metadata hoặc callback ngoài proxy khác nhau, login sẽ fail.

Các nhánh có ý nghĩa:

- **`assertingparty.verification.credentials`:** public cert của **IdP** cho kiểm chữ ký Response/Assertion nhận vào.
- **`decryption.credentials`:** SP private key + SP cert cho giải mã `EncryptedAssertion` nhận vào.
- **`signing.credentials`** (nếu cấu hình): SP private key + cert dùng **ký AuthnRequest/logout** gửi đi. Đây không phải chứng thư kiểm Response từ IdP.
- **`assertingparty.metadata-uri`** (nếu sử dụng): tải và đăng ký entityID, endpoint, signing cert… từ metadata IdP đáng tin.
- **`entity-id` và ACS URL** phải trùng thiết lập phía IdP; sau reverse proxy cần xử lý scheme/host từ trusted proxy đúng cách.

Nếu không có SP decryption private key, một Response hợp lệ có `EncryptedAssertion` có thể vẫn **không đăng nhập được** vì không giải mã. Nếu decryption key đúng nhưng chưa cấu hình IdP verification cert, **không được chấp nhận** assertion như thể ciphertext là nguồn tin cậy.

**Không tùy tiện bỏ xác minh chữ ký** trong `OpenSamlAuthenticationProvider` hay thay converter bằng parser lấy XML trực tiếp. Spring Security/OpenSAML đã xử lý canonicalization, signature validation, assertion conditions và các điểm mở rộng cần thiết; cấu hình sai trust hay validator tùy biến gây lỗi bảo mật khó thấy.

## 9. Tương tác metadata: IdP và SP phải thống nhất những gì?

Để triển khai thành công, hai bên cần thống nhất **những trường khác nhau**:

1. **IdP entityID/Issuer:** SP chấp nhận đúng bên phát hành.
2. **IdP signing certificate:** SP dùng verify signature. Thêm chứng thư mới đúng quy trình rollover.
3. **SP entityID/Audience:** Assertion dành đúng SP này; không chọn theo hostname ngẫu nhiên.
4. **ACS URL/binding:** HTTP-POST nhận SAMLResponse, khớp recipient/destination.
5. **Yêu cầu vị trí chữ ký:** response signed, assertion signed, hoặc cả hai theo profile/chính sách đối tác.
6. **Yêu cầu mã hóa:** plaintext hay encrypted assertion; thuật toán/crypto policy tương thích; **SP decryption cert** được cung cấp cho IdP.
7. **SP signing cert:** nếu IdP bắt buộc ký AuthnRequest hoặc LogoutRequest.
8. **Clock skew, request correlation, replay:** giới hạn chấp nhận; thời gian trên hai hệ thống đồng bộ.
9. **NameID/claims/groups:** thuộc tính nào cần, mục đích sử dụng và cách map authority.

**Ví dụ đối tác nói "ứng dụng của anh phải gửi cert"**: cần hỏi đó là **SP signing certificate** cho AuthnRequest hay **SP encryption certificate** để IdP mã hóa assertion; cũng có thể họ cần cả hai. Công dụng khác nhau dù có thể cùng tệp cert trong cấu hình mẫu.

## 10. Các tổ hợp và kết quả kỳ vọng khi kiểm chứng

| # | Response ký? | Assertion ký? | Assertion mã hóa? | Kỳ vọng có điều kiện |
|---|---|---|---|---|
| 1 | Có, hợp lệ | Không | Không | Có thể được chấp nhận nếu mọi điều kiện SAML, profile và policy SP hợp lệ |
| 2 | Không | Có, hợp lệ ở **mọi** assertion | Không | Có thể được chấp nhận nếu mọi điều kiện SAML và policy hợp lệ |
| 3 | Có, hợp lệ | Có, hợp lệ | Không | Có thể được chấp nhận khi các điều kiện còn lại hợp lệ |
| 4 | Không | Không | Không | **Từ chối** trong SAML Browser SSO HTTP-POST/Spring Security mặc định |
| 5 | Có nhưng chữ ký sai | Có hợp lệ | Không | **Từ chối**: chữ ký có mặt nhưng sai không thể bỏ qua |
| 6 | Có hợp lệ | Có nhưng chữ ký sai | Không | **Từ chối** theo pipeline Spring Security được mô tả |
| 7 | Có hợp lệ | Không | Có | Giải mã được và ký Response bảo vệ đúng ciphertext, rồi kiểm mọi điều kiện mới có thể chấp nhận |
| 8 | Không | Có **bên trong ciphertext**, hợp lệ | Có | Chỉ có thể chấp nhận sau giải mã, kiểm chữ ký và policy; lưu ý bảo vệ ciphertext/integrity trước giải mã theo thuật toán và profile |
| 9 | Không | Không | Có | **Không chấp nhận chỉ vì giải mã thành công**; thiếu bằng chứng phát hành đáng tin |
| 10 | Có hợp lệ | Không | Có nhưng private key sai | **Từ chối** do không giải mã được |
| 11 | Có hợp lệ | Có hợp lệ | Không nhưng expired / sai Audience | **Từ chối** dù ký đúng |
| 12 | Có hợp lệ | Có hợp lệ | Không nhưng IdP key chưa được SP tin cậy | **Từ chối** vì thất bại trust verification |

Các hàng nói "**có thể chấp nhận**" luôn giả định issuer, destination/recipient, InResponseTo, signature references, status, subject confirmation, conditions, replay, TLS/registration đều hợp lệ. Đây là **ma trận ý nghĩa bảo mật**, không phải công cụ để nới điều kiện của profile hoặc một IdP cụ thể.

### Hai tình huống dễ nhầm

**Tình huống A — Response signed, Assertion unsigned, login vẫn đúng chuẩn:** SP có thể chấp nhận nếu chữ ký Response bao phủ đúng assertion, thuật toán/cert tin cậy, IdP và toàn bộ điều kiện đúng. Không nên tự báo lỗi "thiếu signature bên trong assertion" nếu contract của hệ thống cho phép ký Response.

**Tình huống B — Assertion encrypted, login thất bại dù "có certificate":** IdP có thể đang dùng **SP public certificate phiên bản mới** trong khi SP còn **private key cũ**, hoặc dùng một cặp encryption key khác với cặp signing; phải kiểm đúng keypair và metadata, không thay bằng IdP signing certificate.

## 11. Xử lý sự cố có hệ thống

| Triệu chứng | Nguyên nhân khả dĩ | Bước xác minh |
|---|---|---|
| `Signature validation failed` | IdP cert sai/hết vòng đời, key rollover, signature/digest bị thay, signature Reference không khớp | Kiểm trust metadata, issuer, cert fingerprints đúng môi trường, thuật toán và XML signature library |
| Có Response signature nhưng validator báo thiếu chữ ký bảo vệ assertion | Chữ ký không bao phủ assertion được dùng, cấu hình yêu cầu ký Assertion hoặc có nhiều assertion unsigned | Kiểm chính sách SP, số assertion, đúng signed node và Reference |
| `EncryptedAssertion` không giải mã | SP key sai, key location/permissions, thuật toán không hỗ trợ, cert IdP dùng để encrypt không trùng key | Đối chiếu cặp private key–public cert, kiểm permission và thuật toán |
| Giải mã thành công nhưng đăng nhập fail | Chữ ký Assertion sai, issuer/audience/time/subject confirmation lỗi, replay | Xem lỗi validation theo bước, không bỏ security check |
| Có NameID đúng nhưng vẫn 401/403 | Authentication chưa tạo, thiếu authority mapping hoặc policy application | Phân biệt authentication failure và authorization failure |
| Intermittent fail quanh lúc rotation | Nhiều nút sử dụng cert/key version khác nhau; metadata cache chưa đồng bộ | Kế hoạch overlap keys, rollout và log fingerprint/version |
| Thời gian bất thường | NTP lệch, NotBefore/NotOnOrAfter, InResponseTo cache bị xóa | Đồng bộ clock, kiểm request store và allowed clock skew tối thiểu |
| ACS URL sai sau reverse proxy | App thấy HTTP/local hostname nhưng IdP dùng HTTPS external URL | Trusted forwarded headers, entityID/ACS, Recipient/Destination |
| Login khi request cũ bị phát lại | Replay cache/correlation yếu hoặc session xử lý thiếu | Bật kiểm request context và assertion/replay ID theo profile |
| Security parser chọn nhầm Assertion | XML Signature Wrapping, duplicate ID hoặc parser lấy thẻ bằng tên | Dùng OpenSAML validator hardened và verify đúng node được sử dụng |

**Tránh xử lý sự cố bằng cách:** bỏ signature validation, bật trust tất cả `KeyInfo`, đặt clock skew quá lớn, cho phép mọi Destination/Audience, dump đầy đủ SAML assertion/PII vào log sản xuất, hoặc lưu private key trong ứng dụng public.

## 12. Kiểm thử tích hợp và bài tập đọc thông điệp

### 12.1. Kịch bản kiểm thử có ý nghĩa

Lấy test IdP đúng tenant và môi trường thử nghiệm, phát các trường hợp:

- **Response signed only**: assertion plaintext không ký; SP theo cấu hình chấp nhận chữ ký Response nếu hợp lệ.
- **Assertion signed only**: Response ngoài không ký; validator phải kiểm đúng assertion ký, các protocol/subject conditions.
- **Both signed**: sửa một ký tự của Response hoặc Assertion sau khi IdP phát; validator phải từ chối.
- **Encrypted + Response signed**: cấu hình SP decryption key hợp lệ → parse được; sai key/không có key → fail.
- **Signed then encrypted assertion**: giải mã, kiểm chữ ký bên trong rồi kiểm conditions; thay digest/chữ ký → fail.
- **Encrypted but unsigned**: không xem khả năng giải mã là chứng cứ xác thực.
- **Expiration & audience**: chữ ký vẫn hợp lệ nhưng expired/sai audience/recipient → fail.
- **Replay & wrong request**: gửi lại một Response hoặc `InResponseTo` không khớp request pending → từ chối khi quy tắc profile yêu cầu.
- **Key rollover**: IdP dùng cert mới, SP đã được cấp trust đúng theo quy trình; nếu chưa, fail an toàn.
- **XML Signature Wrapping**: response chứa cấu trúc trùng ID hoặc assertion không được chữ ký bảo vệ → fail, không dùng thẻ mà parser tùy tiện lấy.

Test nên bắt đầu bằng SAML response do **test IdP thật** hoặc SAML test harness phát ra. Không chỉnh XML rồi hy vọng signature vẫn đúng; đây là lý do phải có negative test tự xác nhận kỳ vọng **FAIL**. Không nên tự xây trình xác minh XML signature bằng XPath tự viết.

### 12.2. Bài tập tự kiểm tra

**Bài 1:** Một assertion được mã hóa, không có chữ ký Response/Assertion. SP giải mã đúng tên người dùng. Có được tạo phiên không?

**Đáp án:** Không. Giải mã chứng minh SP có private key tương ứng, không chứng minh assertion được ký bởi IdP đáng tin hay đầy đủ điều kiện xác thực.

**Bài 2:** Response ký hợp lệ, Assertion bên trong không ký. Có mặc định là "sai chuẩn"?

**Đáp án:** Không. Trong HTTP-POST Web Browser SSO, chuẩn/errata và provider có thể chấp nhận chữ ký Response bao phủ assertion; chính sách SP/đối tác có thể yêu cầu thêm chữ ký Assertion.

**Bài 3:** Assertion có `ds:Signature` hợp lệ nhưng `AudienceRestriction` là ứng dụng khác. Kết quả?

**Đáp án:** Từ chối. Integrity đúng không đồng nghĩa assertion được phép dùng tại SP này.

**Bài 4:** IdP ký Assertion rồi mã hóa toàn bộ Assertion. SP phải xác minh chữ ký bên trong trước khi giải mã?

**Đáp án:** Không thể: chữ ký nằm bên trong ciphertext, phải giải mã rồi xác minh chữ ký. Nếu Response ngoài cũng được ký, kiểm chữ ký ngoài trước theo quy trình xác minh phù hợp.

**Bài 5:** IdP đã đưa SP certificate vào metadata để mã hóa assertion; SP có cần private key?

**Đáp án:** Có. IdP dùng public key/certificate của SP để mã hóa; SP dùng private key tương ứng để giải mã.

**Bài 6:** Khi nào khác biệt Response signature/Assertion signature trở nên nghiêm trọng?

**Đáp án:** Khi có nhiều assertions, thông tin ở Response ngoài assertion, XML signature wrapping, policy yêu cầu tầng ký cụ thể, và khi ký–mã hóa kết hợp phải tuân thủ thứ tự verification/decryption.

## 13. Checklist thực hành trước khi đưa SAML SSO vào production

1. Xác nhận **SP/IdP role**, HTTP-POST/Artifact binding, entityID, ACS URL, issuer và profile áp dụng.
2. Chốt văn bản integration về **sign Response, sign Assertion hoặc cả hai**; không suy đoán chỉ từ một sample base64.
3. Cấu hình **IdP verification credential** từ metadata đáng tin; không lấy key từ request chưa xác thực.
4. Nếu cần **EncryptedAssertion**, cung cấp **SP public encryption cert** cho IdP và giữ **SP decryption private key** an toàn. Thống nhất thuật toán.
5. Nếu cần **signed AuthnRequest**, dùng **SP signing key** riêng đúng vai trò; đừng nhầm với decryption credential.
6. Xác minh response/assertion signature đúng vùng dữ liệu; hardened XML parser và chống wrapping/replay.
7. Kiểm `Status`, `Issuer`, `Destination`, `InResponseTo`, `AudienceRestriction`, `SubjectConfirmationData`, `NotBefore`/`NotOnOrAfter` và ngữ cảnh pending request.
8. Mapping `NameID`/attributes/roles có kiểm soát; đừng cấp vai trò admin chỉ vì XML có một chuỗi role.
9. Kiểm đủ **positive/negative tests**, key rotation, clock drift, lỗi callback sau proxy, logout/session.
10. Log lỗi kỹ thuật theo mã/sự kiện mà không log full assertion, ticket, private key, thuộc tính nhạy cảm; cảnh báo lúc chứng thư/key sắp hết vòng đời.

## 14. Tài liệu chuẩn và tài liệu Spring Security

- **OASIS SAML 2.0 Errata 05** (phần ký Response/Assertion, ký+mã hóa, integrity): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html
- **OASIS SAML Core** (Assertions and Protocols): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **Spring Security – SAML2 Login Overview** (pipeline signature → decrypt → assertion validation): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- **Spring Security – Authenticating SAML2 Responses** (custom validators/decrypters): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- **Spring Boot – SAML2 Relying Party Properties**: https://docs.spring.io/spring-boot/reference/security/saml2.html
- **OWASP SAML Security Cheat Sheet** (signature wrapping, trust, assertions): https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Nhớ:** *Response signed* bảo vệ vùng Response đúng chữ ký; *Assertion signed* bảo vệ assertion riêng; *EncryptedAssertion* giấu nội dung cho SP. Để đăng nhập an toàn, cần **bảo vệ và xác minh đúng nội dung mà ứng dụng sử dụng**, **kiểm điều kiện SAML**, quản lý khóa tin cậy và session. Mọi ví dụ cấu hình phải được đối chiếu với version Spring Boot/Spring Security thực tế.
