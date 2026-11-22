# Phân biệt xác minh chữ ký Response với xác minh Assertion được sử dụng trong SAML 2.0

> **Chủ đề:** Spring Security – federation · **Nhóm:** Kiểm chứng SAML2. Bài học này tập trung vào câu hỏi rất dễ bị hiểu sai: **SP đã xác minh chữ ký trên `samlp:Response` thì có chắc `saml:Assertion` mà ứng dụng dùng để đăng nhập cũng được bảo vệ không?** Câu trả lời phụ thuộc vào **chữ ký bao phủ đúng node nào**, **Assertion nào thật sự được chọn làm principal/attributes**, **trust của khóa**, và **các kiểm tra SAML còn lại**.

## 1. Mục tiêu và kết luận cần nhớ

Sau bài này, có thể:

1. Chỉ ra vị trí và phạm vi bảo vệ của chữ ký XML ở **Response** so với ở **Assertion**.
2. Phân biệt **xác minh chữ ký thành công** với **xác minh chính Assertion dùng để cấp phiên và quyền**.
3. Hiểu hai mô hình hợp lệ theo Web Browser SSO HTTP-POST: **Response được ký** hoặc **mọi Assertion được sử dụng đều được ký** theo profile/chính sách.
4. Nhận diện lỗi **XML Signature Wrapping**, duplicate ID, chọn sai element và việc tin nhầm dữ liệu không nằm trong vùng chữ ký.
5. Hiểu pipeline của Spring Security SAML2/OpenSAML và điểm cần chú ý khi tùy biến converter/validator.
6. Thiết kế các bài test cho Response-only signature, Assertion-only signature, both-signed, multi-assertion, encrypted assertion và các thông điệp độc hại.
7. Không nhầm chữ ký/metadata/issuer với các validation riêng như Audience, Recipient, Destination, Expiry, InResponseTo và Replay.

**Phân biệt ngắn gọn:**

- **Response signature**: bảo vệ **Response XML được ký** và nội dung bên trong mà phép tham chiếu chữ ký thực sự bao phủ, bao gồm Assertion lồng trong signed Response.
- **Assertion signature**: bảo vệ **một Assertion XML cụ thể** mà tham chiếu chữ ký hướng đến; không mặc nhiên ký cả Response bên ngoài.
- **Used Assertion validation**: ứng dụng chỉ được sử dụng principal/attributes từ **Assertion đã được xác thực, nằm trong phạm vi được ký tin cậy và qua mọi điều kiện SAML bắt buộc**.
- **Signature validation ≠ SAML validation ≠ authorization**. Chữ ký đúng không biến một Assertion sai audience, quá hạn hoặc sai request thành bằng chứng đăng nhập hợp lệ.

## 2. Những thành phần có mặt trong SAML Web Browser SSO

Một bản tin `SAMLResponse` từ Identity Provider (IdP) thường được browser gửi qua HTTP POST đến Assertion Consumer Service (ACS) của Service Provider (SP). Chú ý tên XML namespaces: `samlp` thuộc SAML protocol; `saml` thuộc SAML assertion; `ds` thuộc XML Digital Signature (XMLDSig).

| Thành phần | Vai trò | Câu hỏi kiểm chứng |
|---|---|---|
| `samlp:Response` | Phong bì giao thức, ID, Issuer, Destination, InResponseTo, Status, Assertions | Response đúng IdP, ACS, pending request và profile chưa? |
| `saml:Assertion` | Chủ thể, NameID, authentication statement, Conditions, attributes | Assertion nào thực sự được dùng? Nó hợp lệ và được bảo vệ chưa? |
| `ds:Signature` dưới Response | Chữ ký XML cho phạm vi Response | Reference trỏ đúng Response và bao phủ nội dung được dùng chưa? |
| `ds:Signature` dưới Assertion | Chữ ký XML cho một Assertion | Reference trỏ đúng Assertion đó chưa? |
| `ds:SignedInfo/Reference` | Liên kết hash/digest tới đối tượng được ký | URI, transforms, canonicalization và digest hợp lệ chưa? |
| `RelyingPartyRegistration` | Cấu hình trust và endpoint SP ↔ IdP trong Spring Security | Verification certificate có thuộc đúng IdP không? |
| `Saml2AuthenticatedPrincipal` | Principal tạo sau xác thực | NameID/attributes lấy từ Assertion nào và sau kiểm chứng nào? |

Không nên coi `<ds:Signature>` chỉ là một nhãn nằm đâu đó trong XML. XMLDSig phải kiểm **chính xác phần tử được tham chiếu** cùng các transforms, digest, SignatureValue, key/trust. Hơn nữa, người dùng thực tế được xác định từ Assertion mà converter dùng, **không phải một chuỗi `NameID` bất kỳ trong XML**.

### Ví dụ luồng cơ bản

~~~text
User + Browser
      |
      | POST SAMLResponse (base64 XML)
      v
Spring Security /login/saml2/sso/{registrationId}
      |
      | 1. Giải mã và parse XML an toàn
      | 2. Resolve đúng RelyingPartyRegistration / IdP
      | 3. Kiểm chữ ký Response nếu hiện diện
      | 4. Giải mã EncryptedAssertion nếu có
      | 5. Kiểm chữ ký Assertion, trust, chính sách
      | 6. Kiểm Issuer, Destination, Audience,
      |    SubjectConfirmation, thời hạn, request state
      | 7. Chọn/chuyển Assertion đã được xác thực thành
      |    principal + attributes + authorities
      v
Authentication / SecurityContext / Session
~~~

Sơ đồ mô tả **các yêu cầu logic**. Thứ tự thực hiện cụ thể có thể thay đổi giữa Spring Security 6 và 7, đặc biệt thứ tự response validation so với assertion validation. Điều bắt buộc là **không tạo phiên hay cấp quyền từ dữ liệu chưa được xác minh**.

## 3. Chữ ký trên Response bảo vệ phần nào?

### 3.1. Mô hình Response-signed, Assertion unsigned

Ví dụ XML **rút gọn để đọc cấu trúc**, thiếu nhiều thành phần bắt buộc, chữ ký và các giá trị digest thật, **không phải SAMLResponse chạy được**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response_01"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <ds:Signature>
    <ds:SignedInfo>
      <ds:Reference URI="#_response_01">
        <!-- Transforms, DigestMethod, DigestValue... -->
      </ds:Reference>
    </ds:SignedInfo>
    <!-- SignatureValue và thông tin khóa theo profile -->
  </ds:Signature>
  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assertion_01">
    <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
    <saml:Subject>
      <saml:NameID>alice</saml:NameID>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Ở ví dụ, `ds:Signature` là con của Response và `ds:Reference URI="#_response_01"` trỏ tới Response. Khi signature validator:

- Giải ID đúng, kiểm digest của **đúng Response element** sau các transforms.
- Kiểm `SignatureValue` với public verification key thuộc **IdP được SP tin cậy**.
- Xác nhận Response mà nghiệp vụ dùng **chính là Response đã được ký**.
- Bảo đảm Assertion được dùng **nằm trong phạm vi Response được ký**, không phải node từ chỗ khác được chèn, thay hoặc lấy nhầm.

...thì chữ ký Response hợp lệ **có thể** bảo vệ assertion lồng bên trong, dù assertion đó không chứa `ds:Signature` riêng. Với Web Browser SSO HTTP-POST, đây là một hình thức bảo vệ có thể phù hợp chuẩn và với Spring Security mặc định khi các điều kiện khác hợp lệ.

**Điểm cần nói chính xác:** Chữ ký Response **không chỉ ký một danh sách thuộc tính Response**. Nó có thể bảo vệ cả cấu trúc XML con qua canonicalization/digest. Nhưng phải kiểm **Reference và phép biến đổi** thực tế; việc nhìn thấy chữ ký đặt trong Response không đủ bảo đảm mọi node được ứng dụng xử lý đều được bảo vệ.

### 3.2. Điều Response signature không tự làm

- **Không mã hóa Assertion:** browser có thể đọc NameID và Attribute nếu Assertion là plaintext.
- **Không bảo đảm đúng SP:** vẫn kiểm `AudienceRestriction` và recipient.
- **Không bảo đảm mới:** vẫn kiểm `NotBefore/NotOnOrAfter`, replay và thời hạn subject confirmation.
- **Không bảo đảm đúng phiên:** trong SP-initiated SSO cần kiểm `InResponseTo` và pending AuthnRequest phù hợp; IdP-initiated có chính sách riêng.
- **Không bảo đảm user có quyền:** `role=admin` chỉ là một thuộc tính/claim cần ánh xạ theo chính sách.
- **Không thay IdP trust:** một response ký bằng private key của bên không nằm trong trust registration không được chấp nhận.
- **Không cho phép dùng Assertion nằm ngoài signed subtree:** đây là lỗi cốt lõi dẫn tới XML Signature Wrapping.

**Ví dụ:** IdP ký Response có assertion cho `alice` và Audience là `https://another-sp.example.org`. Chữ ký vẫn đúng về mặt mật mã, nhưng SP hiện tại phải **từ chối** vì Audience không dành cho nó.

## 4. Chữ ký trên Assertion bảo vệ phần nào?

### 4.1. Mô hình Assertion-signed, Response unsigned

Ví dụ XML rút gọn:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_response_02"
    Destination="https://sp.example.org/login/saml2/sso/corporate">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>...</samlp:Status>
  <saml:Assertion ID="_assertion_02">
    <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
    <ds:Signature>
      <ds:SignedInfo>
        <ds:Reference URI="#_assertion_02">
          <!-- Transforms và digest... -->
        </ds:Reference>
      </ds:SignedInfo>
      <!-- SignatureValue... -->
    </ds:Signature>
    <saml:Subject>
      <saml:NameID>alice</saml:NameID>
    </saml:Subject>
    <saml:Conditions>...</saml:Conditions>
    <saml:AuthnStatement>...</saml:AuthnStatement>
    <saml:AttributeStatement>...</saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Chữ ký Assertion gắn với `_assertion_02`, chỉ bảo vệ **Assertion đó theo XMLDSig transforms**. Nó **không tự ký** các trường nằm ngoài Assertion ở Response, như `Response.Destination` hoặc `Response.InResponseTo`. Đây là lý do SP vẫn có trách nhiệm kiểm đúng profile của Response, ACS và ngữ cảnh request, ngay cả khi Assertion signature hợp lệ.

Cần kiểm:

1. Reference `URI="#_assertion_02"` giải ra **chính Assertion mà SP sẽ dùng**.
2. Signature/digest hợp lệ và ký bằng khóa của **IdP đã được cấu hình tin cậy**.
3. Assertion thật sự thuộc Response nhận ở ACS hợp lệ; không có một Assertion chưa ký khác bị parser/chuyển đổi chọn.
4. Các trường `Issuer, Subject, SubjectConfirmationData, AudienceRestriction, Conditions, AuthnStatement` hợp lệ.
5. Nếu có nhiều Assertions, **không dùng chữ ký Assertion A để tin Assertion B**.

### 4.2. Vì sao chữ ký Assertion không bao trùm Response?

Giả sử response có:

~~~text
Response (unsigned)
  ├── Destination / InResponseTo / Status
  └── Assertion ID=A1 (signed)
       ├── Subject NameID=alice
       ├── Conditions Audience=sp-1
       └── Attribute groups=report-readers
~~~

Chữ ký ở Assertion bảo đảm nội dung Assertion A1 không bị sửa mà vẫn qua kiểm tra, nhưng **không bảo vệ trực tiếp** các trường Response ở phía ngoài. SP phải dùng **validator của giao thức** để quyết định Response được gửi tới đúng ACS, liên hệ đúng request và issuer, status phù hợp. Không được bỏ qua Response validation chỉ vì ID/Subject/Attributes có chữ ký riêng.

Với hệ thống dùng nhiều Assertion, mỗi Assertion thực sự dùng để xác thực hoặc lấy attributes đều phải được **bảo vệ theo chính sách đáng tin**. Không đủ khi chỉ có một Assertion ký hợp lệ nhưng converter lại lấy role từ một Assertion khác không được bảo vệ.

## 5. Bốn câu hỏi bắt buộc về một chữ ký

Một bước signature validation đầy đủ phải trả lời **bốn câu**:

1. **Ai ký?** Chữ ký phải kiểm bằng verification credential của **IdP được SP cho phép**, lấy từ metadata/trust cấu hình đáng tin. Không lấy khóa bất kỳ từ `ds:KeyInfo` trong payload rồi xem như trusted.
2. **Ký gì?** `ds:Reference URI`, transforms, canonicalization và digest xác định **node/phạm vi XML thực sự được ký**. Reference không được trỏ sang một Assertion khác với Assertion được sử dụng.
3. **Có nguyên vẹn không?** Digest và `SignatureValue` có hợp lệ theo thuật toán được chấp nhận không? Bất kỳ thay đổi trong vùng được ký phải làm kiểm tra thất bại.
4. **Dữ liệu nào được dùng?** Sau xác minh, parser và business converter có dùng **chính node đã được chữ ký bảo vệ** không? Nếu lấy một node mới/từ vùng ngoài signed content, bảo đảm chữ ký không còn ý nghĩa.

Bảng phân biệt kết quả:

| Phát hiện | Đánh giá | Hành động đúng |
|---|---|---|
| Có `ds:Signature` nhưng verify thất bại | Không đáng tin | Từ chối |
| Verify thành công bằng certificate do payload tự khai nhưng SP chưa tin | Thiếu trust | Từ chối |
| Verify thành công nhưng Reference trỏ một Response **khác** | Không bảo vệ node cần dùng | Từ chối |
| Verify thành công trên Assertion A, nhưng converter lấy NameID từ Assertion B chưa được bảo vệ | Assertion được dùng không đáng tin | Từ chối |
| Verify thành công trên Response được dùng, Assertion là con thuộc signed subtree | Có bảo vệ integrity cho Assertion đó | Tiếp tục kiểm điều kiện SAML |
| Verify thành công trên Assertion được dùng, Response không ký | Assertion được bảo vệ | Tiếp tục kiểm Response conditions và correlation |
| Verify đúng, nhưng Assertion hết hạn hoặc sai Audience | Không thỏa SAML policy | Từ chối |
| Verify đúng, conditions đúng, nhưng user không có quyền | Authentication có thể hợp lệ; authorization thất bại | Trả 403/từ chối tài nguyên hạn chế |

**Tóm tắt:** Valid signature là điều kiện cần cho phần XML bảo vệ bằng chữ ký, nhưng **chưa đủ** để tạo Authentication cho một người dùng.

## 6. SAML XML Signature Wrapping: chữ ký đúng, Assertion sử dụng sai

### 6.1. Ý tưởng của lớp tấn công

**XML Signature Wrapping (XSW)** xảy ra khi một phần XML được ký hợp lệ vẫn tồn tại, nhưng kẻ tấn công sắp xếp/chèn thêm phần tử để:

- Thư viện XML signature kiểm **một Response/Assertion đã ký**.
- Logic ứng dụng lại đọc **một Response/Assertion khác** (chưa được ký hoặc nằm ngoài signed content).
- Ứng dụng vô tình tin NameID/role từ node không được chữ ký bảo vệ.

Đây là **lỗi gắn sai kết quả kiểm chứng với dữ liệu được sử dụng**. Không cần phá thuật toán chữ ký hay biết private key IdP.

Một ví dụ khái niệm:

~~~text
XML envelope không đáng tin
  ├── Original Assertion ID=A1, chữ ký hợp lệ cho A1
  │    NameID=alice
  └── Injected Assertion ID=A2, chưa ký hoặc sai vị trí
       NameID=admin

Signature library:  "Chữ ký Assertion A1 hợp lệ"
Business converter: "Lấy NameID từ Assertion A2"
Kết quả sai:        "Đăng nhập admin"
~~~

Đây là **minh họa nguy cơ**, không phải một SAML document hợp lệ cụ thể. Schema validation, signature reference enforcement và logic chọn node đúng phải khiến cấu trúc giả như vậy **bị từ chối**.

### 6.2. Vì sao chọn bằng `getElementsByTagName` dễ nguy hiểm?

Đoạn mã DOM minh họa **anti-pattern**, tuyệt đối không dùng làm trình kiểm SAML:

~~~java
// SAI: chọn tùy tiện phần tử theo tên, không bảo đảm nó được ký.
var assertions = document.getElementsByTagName("saml:Assertion");
var selected = assertions.item(assertions.getLength() - 1);
// Không được lấy NameID hoặc roles từ selected để tạo Authentication.
~~~

Các sai lầm ở đây gồm:

- Lấy phần tử theo literal prefix, trong XML prefix có thể đổi mà namespace vẫn giống.
- Có nhiều Assert​ions ở những vị trí bất thường hoặc duplicate ID, thư viện signature và ứng dụng có thể chọn khác nhau.
- Chọn phần tử theo vị trí thay vì **schema + signature coverage + profile**.
- Không chứng minh selected node thuộc Response hợp lệ đã được ký hoặc là chính Assertion đã được ký.

**Biện pháp bảo vệ:**

1. Dùng **parser/schema SAML và validator OpenSAML đã được kiểm nghiệm**, không tự ráp XPath/regex để quyết định danh tính.
2. Cấu hình XML parser an toàn: không cho DTD/external entity tùy tiện, giới hạn kích thước/tài nguyên và cấu trúc schema.
3. Reject **duplicate XML ID**, Reference bất thường, nhiều root/Assertion ngoài schema, transforms/thuật toán không cho phép.
4. Kiểm chính xác **resolved signed element** bằng identity của node/ID hợp lệ, không chỉ so text hoặc display name.
5. Chọn principal và attributes **từ chính Assertion đã qua signature/trust/conditions**.
6. Không thay các validation mặc định bằng converter tìm thẻ `NameID`/`Attribute` trong DOM toàn tài liệu.

OWASP đặc biệt lưu ý Signature Wrapping và yêu cầu xác minh **exact Assertion used for authentication** được bao phủ bởi verified signature.

## 7. Trường hợp nhiều Assertions trong một Response

Một `samlp:Response` có thể chứa nhiều assertion theo các profile/đặc tả phù hợp, hoặc các phần tử `EncryptedAssertion` cần giải mã trước. Với Spring Security SAML2, **không được suy diễn rằng chỉ cần một Assertion bất kỳ có chữ ký**.

### 7.1. Chính sách mặc định được Spring Security mô tả

Tài liệu Spring Security SAML 2.0 Login Overview mô tả các điều kiện:

- Nếu Response có chữ ký nhưng **không hợp lệ**, authentication thất bại.
- Nếu một Assertion có chữ ký nhưng **không hợp lệ**, authentication thất bại.
- Nếu **cả Response và các Assertions đều không có chữ ký**, authentication thất bại.
- Theo chính sách mặc định được tài liệu mô tả, **Response phải có chữ ký hợp lệ hoặc tất cả Assertions phải có chữ ký hợp lệ**.
- Provider kiểm từng Assertion trước khi xác thực thành công; principal/attributes mặc định được tạo từ **Assertion đầu tiên** sau xử lý.

Như vậy có ba tầng tách biệt:

| Tầng | Chỉ dấu | Kiểm soát |
|---|---|---|
| Mật mã | Signed Response / Signed Assertions | Những node nào đã được ký, khóa ký có tin cậy không |
| SAML semantic | Issuer, Destination, Audience, Conditions, SubjectConfirmation | Assertion và Response có được phép dùng không |
| Chuyển đổi Principal | First Assertion / custom converter | Dữ liệu nào được dùng tạo NameID, Attributes và GrantedAuthority |

Nếu bạn tùy biến converter để lấy Assertion thứ hai hoặc ghép thuộc tính từ nhiều Assertion, phải **giữ và áp dụng validation đầy đủ cho tất cả Assertions được dùng**. Không được sửa pipeline sao cho chỉ validate Assertion A rồi dùng Assertion B chưa được bảo vệ.

### 7.2. Ma trận đa Assertion

Giả sử Response chứa A1 và A2:

| Response | A1 | A2 | Kết quả với chính sách mặc định đã mô tả |
|---|---|---|---|
| Signed hợp lệ | Không ký | Không ký | Có thể qua yêu cầu chữ ký nếu cả A1 và A2 nằm trong signed Response, rồi kiểm mọi SAML conditions |
| Không ký | Signed hợp lệ | Signed hợp lệ | Có thể qua yêu cầu chữ ký, rồi kiểm mọi SAML conditions |
| Không ký | Signed hợp lệ | Không ký | **Từ chối**: không phải tất cả Assertions có chữ ký |
| Signed hợp lệ | Signed hợp lệ | Không ký | Có thể qua yêu cầu chữ ký; mọi chữ ký có mặt phải hợp lệ và mọi Assertion phải qua validation |
| Signed hợp lệ | Signed **sai** | Không ký | **Từ chối**: không được bỏ qua signature hỏng của A1 |
| Không ký | Không ký | Signed hợp lệ | **Từ chối**: một Assertion ký không đủ bảo vệ A1 |
| Signed hợp lệ | Không ký, sai Audience | Không ký | **Từ chối** vì semantic validation, dù signed Response bảo vệ integrity |
| Signed hợp lệ | Hợp lệ | Hợp lệ | Có thể thành công; converter mặc định dùng principal/attributes của **A1** |

"**Có thể**" nghĩa là **chỉ xét yêu cầu chữ ký**; còn bắt buộc qua đầy đủ issuer, audience, recipient, timing, subject, replay, request correlation và cấu hình IdP. Nếu profile/partner yêu cầu **chữ ký Assertion riêng**, một signed Response có thể chưa đáp ứng hợp đồng đó.

### 7.3. Assertion nào "được sử dụng" và rủi ro mapping role?

Trong Spring Security mặc định được tài liệu mô tả, provider sau khi kiểm các assertions sẽ lấy **`NameID` và `AttributeStatement` của assertion đầu** để tạo `Saml2AuthenticatedPrincipal`. Đây là chi tiết triển khai/version, **không phải quy tắc chung rằng mọi SAML SP đều chọn assertion đầu**.

Khi thêm custom `ResponseAuthenticationConverter` hoặc tự ghép group claims, xác định minh bạch:

- Assertion nào cung cấp **principal ID**?
- Assertion nào cung cấp **attributes**?
- Nếu ghép nhiều assertions, tất cả có cùng issuer/subject/tenant và được xác thực cùng chính sách không?
- Có hành vi bất thường khi thiếu/đổi thứ tự assertions không?
- Bất kỳ assertion nào bị lỗi chữ ký, expired hoặc sai audience có làm toàn bộ authentication fail không?
- Mapping `role=ADMIN` dựa trên claim thuộc Assertion được ký và thuộc trust realm được chấp nhận không?

**Sai lầm nghiêm trọng:** chỉ kiểm `Response.getAssertions().get(0)` nhưng mapper lại dùng `get(1)` cho quyền, hoặc dùng XPath trên toàn XML sau khi validator đã kiểm chữ ký một node khác.

## 8. Hai tình huống có chữ ký và Assertion mã hóa

### 8.1. Response ký bao phủ EncryptedAssertion

~~~text
Signed(Response ID=R1)
  └── EncryptedAssertion [ciphertext gửi cho SP]
         └── (sau giải mã) Assertion không có chữ ký riêng
~~~

Khi XML Signature bảo vệ đúng **Response có ciphertext**, SP có thể kiểm signature bên ngoài trước, sau đó dùng private decryption key giải mã. Bảo vệ chữ ký của Response vẫn có ý nghĩa đối với encrypted assertion được bao phủ bởi nó. Cần tiếp tục kiểm issuer/audience/subject/conditions của plaintext.

**Tính bảo mật nội dung:** encryption giúp browser không đọc được NameID/attributes, nhưng **không tự chứng minh IdP đã phát hành**. Nếu Response không ký và Assertion bên trong cũng không ký, chỉ giải mã thành công không đủ để xác thực.

### 8.2. Assertion ký rồi mã hóa

~~~text
Response (unsigned hoặc signed tùy cấu hình)
  └── EncryptedAssertion
        └── Decrypt...
               └── Signed(Assertion ID=A1)
                      ├── NameID
                      ├── Conditions
                      └── Attributes
~~~

SP không thể kiểm chữ ký Assertion đang bị mã hóa cho tới khi đã **giải mã**. Sau giải mã phải kiểm chữ ký trên Assertion thực sự được dùng rồi kiểm SAML semantic. Nếu Response ngoài có chữ ký, xác minh chữ ký của Response theo cấu trúc/phần bao phủ thích hợp trước khi xử lý.

Spring Security/OpenSAML tách bộ giải mã:

- **Response elements decrypter:** giải mã `EncryptedAssertion` ở cấp Response.
- **Assertion elements decrypter:** giải mã `EncryptedID`/`EncryptedAttribute` nằm bên trong Assertion.

Lý do là việc **giải mã nội dung bên trong một Assertion đã ký trước khi xác minh chữ ký Assertion** có thể làm thay đổi XML được ký, gây signature verification failure. Cần tuân theo pipeline của provider; không tự chuyển thứ tự decryption/signature validation.

### 8.3. Bảng so sánh ba mục tiêu

| Thủ tục | Câu hỏi được trả lời | Không thể thay thế |
|---|---|---|
| Verify Response XMLDSig | Signed Response đúng nguồn, nguyên vẹn và bao phủ đúng node? | Assert​ion condition check và authorization |
| Verify Assertion XMLDSig | Assertion cụ thể được IdP ký có nguyên vẹn? | Response/request validation ngoài Assertion |
| Decrypt EncryptedAssertion | SP có private key đọc được nội dung? | Signature trust/issuer/audience, anti-replay |
| Validate Assertion | Subject, Audience, Recipient, time và conditions có hợp lệ? | Bảo đảm chữ ký/crypto integrity |
| Convert to Authentication | Chọn NameID, Attribute và authorities | Các validation trước đó |
| Application authorization | Principal được phép làm gì? | Xác thực danh tính tại IdP |

## 9. Spring Security SAML2: xử lý thực tế

### 9.1. Các thành phần cần biết

Một ứng dụng Servlet Spring Security làm SAML Service Provider thường có:

- `HttpSecurity.saml2Login()`: bật luồng SAML2 login.
- `Saml2WebSsoAuthenticationFilter`: nhận `SAMLResponse` ở ACS.
- `Saml2AuthenticationTokenConverter`: chuyển HTTP request thành `Saml2AuthenticationToken` và resolve registration.
- `RelyingPartyRegistrationRepository`: đăng ký SP, IdP, issuer, ACS, verification credentials và decryption credentials.
- `OpenSaml5AuthenticationProvider` trong nhánh tài liệu dùng OpenSAML 5: xác minh chữ ký, giải mã, validate Response/Assertions và tạo Authentication.
- `Saml2AuthenticatedPrincipal` / `Saml2Authentication`: principal và authorities được đưa vào SecurityContext sau thành công.

Tài liệu Spring Security mô tả pipeline (rút gọn):

1. Parse Response từ HTTP binding.
2. Nếu có Response signature thì **kiểm chữ ký**; chữ ký sai thì fail.
3. Giải mã `EncryptedAssertion`; lỗi thì fail.
4. Kiểm các điều kiện Response, như issuer/destination và tương quan request theo validator.
5. Kiểm chữ ký **từng Assertion**; chữ ký có nhưng sai thì fail. Nếu không có Response signature và không phải tất cả Assertions đều ký thì fail.
6. Giải mã phần tử trong Assertion khi phù hợp.
7. Kiểm assertion expiration, subject, audience, confirmations và conditions.
8. Chọn/convert principal và attributes từ assertions đã được chấp nhận, rồi tạo Authentication.

**Lưu ý phiên bản:** Spring Security 6.x và 7.x có thể khác **thứ tự** response validation và assertion validation; tài liệu migration Spring Security 7 đã đề cập việc chuyển response validation về sau assertion validation. Quy tắc không thay đổi là **chữ ký và semantic của chính dữ liệu dùng tạo principal phải được xác thực trước khi đăng nhập**. Kiểm đúng tài liệu của version đang chạy khi mở rộng provider.

### 9.2. Chứng thư xác minh IdP từ đâu?

SP phải có trusted verification certificate của IdP trong `RelyingPartyRegistration`, có thể nạp từ IdP metadata đáng tin:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: "https://idp.example.org/metadata"
~~~

Đây là **ví dụ cấu hình**, URL phải trỏ metadata IdP thực được kiểm nguồn; IdP cũng phải đăng ký SP entityID/ACS. Nếu cấu hình thủ công, cần entityID, SSO URL/binding và `verification.credentials` hợp lệ. **Không** xem cert được nhúng trong SAML Response do browser gửi là certificate đáng tin chỉ vì cấu trúc XML có `KeyInfo`.

Đối với signing/encryption:

- **IdP signing private key** do IdP giữ; SP có **IdP verification public cert** để verify Response/Assertion.
- **SP decryption private key** do SP giữ; IdP có **SP encryption public cert** để mã hóa Assertion cho SP.
- **SP signing private key** (khi ký AuthnRequest/LogoutRequest) do SP giữ; IdP có public cert tương ứng để verify request.

Những cặp khóa có thể khác nhau. Đừng dùng public cert phục vụ encryption làm verification trust tự động, hoặc chấp nhận IdP khác chỉ vì có cùng email domain.

### 9.3. Java 17+ ứng dụng Spring Boot Servlet tối thiểu

Đây là **class Spring Boot đầy đủ ở mức ứng dụng**, dùng khi project đã có Spring MVC, Spring Security, SAML2 SP dependency cùng version. Không chạy bằng `javac` thuần vì cần Spring classpath và IdP thật.

Tệp `src/main/java/com/example/sso/SamlVerificationApplication.java`:

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
public class SamlVerificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SamlVerificationApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML verification demo";
    }

    @GetMapping("/private")
    String privateResource() {
        return "Authenticated";
    }
}
~~~

Để chạy project Maven có wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Sau khi Spring Boot khởi động và metadata/registration IdP hợp lệ, `GET /` trả HTTP body `SAML verification demo`. `GET /private` đòi hỏi đăng nhập; chỉ trả `Authenticated` sau khi SAML Response và assertions được xác thực. Không thể ấn định stdout và redirect URL thực tế nếu chưa có IdP thật.

**Phụ thuộc cần có:** `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-security-saml2-service-provider`; version lấy từ Boot BOM/nhánh phù hợp. Với OpenSAML/Maven repository, thực hiện theo Spring Security dependency guide tương ứng. Luồng SAML2 login này dành cho **Servlet**, không phải `ServerHttpSecurity` WebFlux.

### 9.4. Cần làm gì khi tùy biến converter/validator?

Spring Security cho phép tùy biến provider, response validator, assertion validator và response authentication converter. **Đừng thay bằng validator hời hợt chỉ kiểm chữ ký một nơi**.

Khi can thiệp:

- Ưu tiên **mở rộng validator mặc định** để thêm rule, tránh thay thế toàn bộ mà bỏ issuer/destination/audience/subject confirmation.
- Giữ signature validation cùng với trust IdP và signed-node coverage của dữ liệu đang dùng.
- Nếu custom converter chọn Assertion khác hoặc ghép attributes, phải test multi-assertion/unsigned assertion và mapping authorization.
- Nếu custom decrypter xử lý EncryptedAssertion, vẫn kiểm chữ ký và conditions của plaintext đúng thứ tự; không coi giải mã là authentication.
- Nếu nhiều IdP registrations, không chọn một trusted cert tùy ý khớp chữ ký mà bỏ issuer/entityID/ACS.
- Nếu đổi thời gian cho phép clock skew, giữ cửa sổ ngắn và chính sách replay phù hợp; đừng nới mãi để tránh lỗi.
- Không dùng `Response.getAssertions().stream().findFirst()` như bằng chứng bảo mật khi đang đứng **trước** bước xác minh.
- Không tắt `SignatureValidator` hay bỏ `AudienceRestriction` để một sample của IdP "đăng nhập được".

**Có thể phát sinh điểm lỗi thiết kế:** Spring Security mặc định có bộ validation cho các trường cần thiết trong profile, nhưng một **custom provider/converter** viết sai có thể phá liên kết chữ ký → Assertion → Authentication. Phải test bằng Response đa Assertions và các trường hợp sai chữ ký.

## 10. Ma trận xác minh chữ ký và dữ liệu thực tế được sử dụng

Bảng này dùng để suy luận **trong một SP dùng Web Browser SSO HTTP-POST**. "Qua chữ ký" chưa đồng nghĩa đăng nhập thành công.

| Trường hợp | Response signature | Used Assertion signature | Kết luận |
|---|---|---|---|
| A | Hợp lệ, bao phủ used Assertion | Không có | **Có thể qua yêu cầu chữ ký**; tiếp tục validate Assertion conditions |
| B | Không có | Hợp lệ trên chính used Assertion | **Có thể qua yêu cầu chữ ký** nếu tất cả Assertions cần có chữ ký hợp lệ |
| C | Hợp lệ, bao phủ used Assertion | Hợp lệ | Có thể qua yêu cầu chữ ký; kiểm cả hai chữ ký có mặt |
| D | Không có | Không có | **Từ chối**: không có bảo vệ chữ ký |
| E | Có nhưng **invalid** | Hợp lệ | **Từ chối**: không bỏ qua chữ ký Response hỏng |
| F | Hợp lệ | Có nhưng **invalid** | **Từ chối** theo pipeline Spring Security mô tả |
| G | Hợp lệ cho Response khác / Reference sai | Không có | **Từ chối**: chữ ký không bảo vệ used Response/Assertion |
| H | Không có | Hợp lệ cho Assertion A, nhưng converter dùng Assertion B chưa ký | **Từ chối**: used Assertion không được bảo vệ |
| I | Hợp lệ cho Response bao phủ A1+A2 | A1 và A2 đều không ký | Có thể qua yêu cầu chữ ký, nhưng cả hai cần semantic validation |
| J | Không có | A1 ký, A2 không ký | **Từ chối** theo chính sách mặc định mô tả |
| K | Hợp lệ cho Response | Used Assertion expired/sai Audience | **Từ chối**: semantic sai |
| L | Hợp lệ cho Response chứa ciphertext | Assertion giải mã được, không ký | Có thể qua yêu cầu chữ ký nếu đúng signed ciphertext và đủ policy |
| M | Không có | Assertion được ký **bên trong ciphertext** | Có thể qua yêu cầu chữ ký sau khi giải mã và verify, vẫn phải kiểm mọi điều kiện |
| N | Không có | Assertion giải mã được nhưng không ký | **Từ chối**: encryption không phải authentication |
| O | Hợp lệ bằng cert của IdP **không tin cậy** | Không có | **Từ chối**: thiếu trust |
| P | Hợp lệ và đúng node | Hợp lệ, nhưng role không được map | Authentication có thể thành công, nhưng **không cấp quyền** ngoài policy |

Bất kỳ cấu hình federation nào cũng có thể yêu cầu mạnh hơn policy mặc định, chẳng hạn **bắt buộc Assertion signature** dù Response đã ký. Khi đó Response-only signed phải bị từ chối **theo hợp đồng đối tác**, không điều chỉnh tùy hứng.

## 11. Kiểm Conditions, Subject và request sau chữ ký

Sau khi đã biết dữ liệu nào được bảo vệ bằng chữ ký và signer có tin cậy, SP còn phải kiểm:

| Kiểm tra | Nguồn | Ví dụ lỗi phải từ chối |
|---|---|---|
| **Issuer** | Response/Assertion | Assertion từ IdP khác tenant được đăng ký |
| **AudienceRestriction** | `saml:Conditions` | Assertion dành cho SP B nhưng dùng đăng nhập SP A |
| **Destination** | Response | URL đích không đúng ACS của registration |
| **Recipient** | `SubjectConfirmationData` | Bearer assertion gửi đến ACS khác |
| **InResponseTo** | Response + bearer subject confirmation, pending AuthnRequest | Response thuộc request/session khác |
| **NotBefore** | Conditions | Assertion chưa đến thời điểm sử dụng |
| **NotOnOrAfter** | Conditions + SubjectConfirmationData | Assertion đã hết thời hạn |
| **AuthnStatement** | Assertion | Chưa có phương thức/ngữ cảnh xác thực phù hợp policy |
| **Status** | Response | IdP trả lỗi nhưng app vẫn tạo phiên |
| **Replay** | Assertion/Response IDs, policy | Một bearer assertion đã tiêu thụ được gửi lại |
| **Principal mapping** | Subject/NameID | ID từ issuer khác bị liên kết nhầm tài khoản |
| **Authorization** | Mapping roles/group và rule business | User đã xác thực nhưng không được sửa dữ liệu |

**Giải thích:** Khi Response ký, assertion trong signed subtree được bảo vệ về integrity. Điều đó **không có nghĩa** `AudienceRestriction` hoặc thời hạn tự đúng. Chúng có thể là dữ liệu do **IdP thật** ký nhưng dành cho SP khác, bị expired hoặc không phù hợp request; SP phải từ chối.

### Phân biệt ký và mã hóa

- **Chữ ký Response/Assertion**: integrity và authenticated origin cho XML được ký.
- **EncryptedAssertion**: confidentiality cho assertion, thường IdP mã hóa bằng public encryption cert của SP.
- **TLS/HTTPS**: bảo vệ giao tiếp vận chuyển browser–SP/IdP; browser vẫn là bên chuyển payload, không phải issuer đáng tin.

Một `EncryptedAssertion` không ký và không nằm trong signed Response **không thể** trở thành assertion tin cậy chỉ vì SP giải mã được. Ngược lại, một Response ký nhưng Assertion plaintext có thể đọc được; chữ ký **không giấu** NameID/email/groups.

## 12. Bài thực hành Java 17 độc lập: xác nhận phạm vi được bảo vệ

Bài này diễn đạt **business policy sau khi có kết quả kiểm chữ ký từ thư viện bảo mật chuyên dụng**. Nó **không thực hiện XML Signature, không parse SAML, không thay thế OpenSAML**. Mục tiêu là luyện tư duy "chữ ký hợp lệ nhưng Assertion được sử dụng có thực sự nằm trong vùng tin cậy?".

Tệp `SignedAssertionPolicyDemo.java`:

~~~java
public class SignedAssertionPolicyDemo {

    static String decide(
            boolean responseSignaturePresent,
            boolean responseSignatureValid,
            boolean responseCoversUsedAssertion,
            boolean assertionSignaturePresent,
            boolean assertionSignatureValid,
            boolean sameAssertionNode,
            boolean assertionConditionsValid) {

        if (responseSignaturePresent && !responseSignatureValid) {
            return "REJECT: bad response signature";
        }
        if (assertionSignaturePresent && !assertionSignatureValid) {
            return "REJECT: bad assertion signature";
        }

        boolean protectedByResponse =
                responseSignaturePresent
                && responseSignatureValid
                && responseCoversUsedAssertion;

        boolean protectedByAssertion =
                assertionSignaturePresent
                && assertionSignatureValid
                && sameAssertionNode;

        if (!protectedByResponse && !protectedByAssertion) {
            return "REJECT: used assertion unsigned";
        }
        if (!assertionConditionsValid) {
            return "REJECT: assertion conditions";
        }
        return "ACCEPT: protected and valid";
    }

    public static void main(String[] args) {
        System.out.println(decide(
                true, true, true, false, false, false, true));
        System.out.println(decide(
                false, false, false, true, true, true, true));
        System.out.println(decide(
                true, true, false, false, false, false, true));
        System.out.println(decide(
                false, false, false, true, true, false, true));
        System.out.println(decide(
                true, true, true, false, false, false, false));
        System.out.println(decide(
                true, false, true, true, true, true, true));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac SignedAssertionPolicyDemo.java
java SignedAssertionPolicyDemo
~~~

**Stdout chính xác:**

~~~text
ACCEPT: protected and valid
ACCEPT: protected and valid
REJECT: used assertion unsigned
REJECT: used assertion unsigned
REJECT: assertion conditions
REJECT: bad response signature
~~~

Giải thích:

1. Response chữ ký hợp lệ và bao phủ used Assertion; Assertion không có chữ ký riêng → điều kiện chữ ký đạt.
2. Response không ký, Assertion ký hợp lệ và là chính node được dùng → điều kiện chữ ký đạt.
3. Response ký hợp lệ nhưng **không bao phủ** used Assertion → bị từ chối.
4. Chữ ký Assertion hợp lệ nhưng thuộc **node khác** → used Assertion vẫn chưa được bảo vệ.
5. Chữ ký/coverage đúng nhưng conditions invalid → bị từ chối.
6. Response signature có mặt nhưng invalid → từ chối dù Assertion signature có mặt và hợp lệ.

**Giới hạn bài tập:** hàm `decide` giả định boolean từ một bộ validator **đã kiểm mật mã + trust**; nó không kiểm multi-assertion, ID duplicate, XML schema, issuer, response destination, request correlation, replay hoặc nhóm quyền. Một SP sản xuất phải dùng OpenSAML/Spring Security để thực hiện các kiểm tra ấy, không biến mẫu boolean thành middleware nhận SAML XML.

## 13. Kiểm thử SAML với chữ ký thật và các response độc hại

### 13.1. Positive test

1. **Response-only signed:** Response signature hợp lệ bao phủ Assertion không ký; SP theo policy chấp nhận sau khi conditions đúng.
2. **Assertion-only signed:** Response không ký, Assertion được dùng ký hợp lệ; SP chấp nhận khi mọi assertions cần thiết đều được ký và conditions đúng.
3. **Both-signed:** Response và Assertion có chữ ký hợp lệ; SP xử lý bình thường.
4. **Multi-assertion, Response-signed:** Response ký bao phủ A1/A2; provider kiểm conditions từng Assertion và converter dùng đúng principal theo policy.
5. **Multi-assertion, Assertion-signed:** mọi Assertions có chữ ký hợp lệ và điều kiện đúng.
6. **Encrypted Assertion trong signed Response:** provider xác minh chữ ký bao phủ ciphertext, giải mã và kiểm conditions.
7. **Signed Assertion rồi encrypt:** giải mã để lấy Assertion, kiểm signature của chính Assertion đó.
8. **Key rotation:** IdP ký bằng cert mới đã có trong trusted credentials của SP, không chấp nhận cert ngoài allowlist.

### 13.2. Negative test

| Trường hợp thử | Kết quả phải đạt |
|---|---|
| Thay một ký tự NameID/role trong Response đã ký | Signature/digest verification thất bại |
| Thay một ký tự trong signed Assertion | Signature verification thất bại |
| Chữ ký đặt ở Response nhưng Reference sai ID hoặc ngoài node được dùng | Từ chối |
| XML có duplicate ID, cấu trúc wrap hoặc Assertion ngoài signed subtree | Từ chối |
| Chữ ký hợp lệ cho A1 nhưng app cố lấy NameID A2 unsigned | Từ chối |
| Response không ký, A1 ký hợp lệ, A2 không ký | Từ chối theo default policy |
| Response signature invalid nhưng Assertion signature valid | Từ chối chữ ký hỏng |
| Response signature valid nhưng Assertion signature invalid | Từ chối chữ ký hỏng |
| Response/Assertion không ký, chỉ có EncryptedAssertion | Không chấp nhận chỉ vì decrypt được |
| XML Signature dùng cert từ KeyInfo chưa đăng ký trust | Từ chối |
| Chữ ký đúng nhưng Audience khác SP entityID | Từ chối |
| Chữ ký đúng nhưng Recipient/Destination khác ACS | Từ chối |
| Chữ ký đúng nhưng InResponseTo không khớp pending request | Từ chối |
| Chữ ký đúng nhưng expired/NotBefore không hợp lệ | Từ chối |
| Chữ ký đúng nhưng replay assertion ID đã dùng | Từ chối |
| Chữ ký đúng, user thiếu role business | Không cấp quyền truy cập tài nguyên hạn chế |
| Converter tùy biến chọn Assertion không được xác minh | Test fail và phải sửa converter/pipeline |

### 13.3. Cách xây test an toàn và có ý nghĩa

Dùng test IdP, OpenSAML fixture hoặc SAML test harness phát hành **Response đã được ký bằng test keys**, không giả định rằng thay XML rồi chữ ký vẫn đúng. Đối với negative test về **business converter chọn sai node**, cần một fixture có **chữ ký đúng cho một node** nhưng dữ liệu không tin cậy ở node khác; validator phải từ chối do schema/coverage, không vì "không parse được" tình cờ.

Khi test multi-assertion, kiểm cả:
- Authentication principal NameID thực sự được lấy từ Assertion nào.
- Group/role attributes có bị ghép từ Assertion khác không.
- Tất cả assertions đều được kiểm signature/trust/conditions phù hợp.
- Chỉ cần một signature sai có dẫn đến fail như policy yêu cầu không.
- Có sự khác nhau giữa bản Spring Security 6.x và 7.x khi custom converter/validator không.

Không log trọn `SAMLResponse` thật, raw assertions chứa PII, private keys, cookie hoặc mã phiên vào hệ thống public. Cần log sự kiện và fingerprint/correlation ID phù hợp đã hạn chế nhạy cảm.

## 14. Sự cố thường gặp và cách phân tích

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm |
|---|---|---|
| `Signature validation failed` | Cert IdP sai, key rollover, XML biến đổi, digest/signer không hợp lệ | So metadata IdP, verification credentials, ID/Reference, signature algorithm |
| Có chữ ký Response nhưng SP báo thiếu bảo vệ Assertion | Response không ký đúng node/Reference, custom converter dùng Assertion ngoài signed subtree hoặc partner yêu cầu Assertion signature | Xác minh signed node và actual used Assertion, contract IdP |
| Chữ ký Assertion hợp lệ nhưng login bị từ chối | Response fields sai, request correlation/recipient/audience/expiry sai | Tách signature test khỏi semantic validation |
| XML có hai Assertions, một ký, một không | Default policy yêu cầu Response signed hoặc tất cả Assertions signed | Kiểm cả response signature và mọi assertion |
| Login ra user không mong muốn | Converter chọn nhầm Assertion/NameID, account linking theo email | So chính xác principal được lấy từ validated assertion nào |
| Role tăng quyền bất thường | Attribute từ Assertion chưa xác thực hoặc mapper ghép sai source | Kiểm claims mapping, issuer, tenant, converter |
| Signature Wrapping hoặc duplicate ID | XML parser + signature verifier chọn khác node business dùng | Reject duplicate ID/schema invalid; dùng hardened OpenSAML |
| EncryptedAssertion giải mã được nhưng signature không qua | SP decryption key khác verification trust; signing cert không phù hợp | Kiểm đúng vai trò khóa, chuỗi trust và thứ tự decryption |
| Response signed valid, Assertion expired | Chữ ký đúng nhưng semantic điều kiện sai | Kiểm `NotOnOrAfter`, NTP, SubjectConfirmation |
| SSO qua proxy lỗi Destination | Host/scheme public khác internal ACS | Sửa trusted forwarded headers, entityID/ACS |
| Nhiều phiên bản app xử lý khác nhau | Spring Security 6/7 hoặc custom provider/validator khác | So locked dependencies, migration docs, integration tests |

**Hướng chẩn đoán:** xác minh đúng issuer/registration → kiểm Response signature/trust/Reference → giải mã nếu có → kiểm từng Assertion signature và đúng node → kiểm SAML conditions → principal conversion → authorization. Đừng bỏ signature validation hoặc Audience check để vá lỗi cấu hình.

## 15. Checklist review bảo mật cho một PR/SAML integration

- [ ] `RelyingPartyRegistration` trỏ đúng IdP metadata/issuer/cert đáng tin.
- [ ] Không đọc user/roles bằng regex/XML DOM tùy tiện từ chưa validated `SAMLResponse`.
- [ ] Đã kiểm **Response signature nếu có** và đúng Response được dùng.
- [ ] Đã kiểm **Assertion signature nếu có** và chính Assertion được dùng.
- [ ] Nếu Response không ký, **mọi Assertions cần thiết** có chữ ký đáng tin; không chấp nhận một Assertion unsigned khác.
- [ ] Reject signature có mặt nhưng invalid, dù chữ ký tầng khác valid.
- [ ] Signed node/Reference/ID phải chính xác; reject duplicate IDs/signature wrapping.
- [ ] XML parser hardened, schema đúng và thuật toán ký/hash nằm trong allowlist.
- [ ] Với EncryptedAssertion, có decryption credentials đúng vai trò và tiếp tục kiểm chữ ký/conditions.
- [ ] Response issuer/destination/status và Assertion audience/subject/time/confirmation được validate.
- [ ] Có request correlation với `InResponseTo` khi SP-initiated; có chính sách rõ cho unsolicited IdP-initiated.
- [ ] Có replay protection phù hợp profile/deployment.
- [ ] Principal/attributes chỉ từ **validated used Assertion**; không ghép roles chưa chứng thực.
- [ ] Test multi-assertion, sign Response-only, Assertion-only, both, wrong-key, wrong-Reference và signature-wrapping.
- [ ] Test quyền user thấp, user không có quyền, tenant khác và expired Assertion.
- [ ] Không tắt validator mặc định khi custom converter/decrypter; kiểm version Spring Security thực tế.

## 16. Câu hỏi tự kiểm tra

1. **Response ký hợp lệ, Assertion bên trong không ký, SP có thể chấp nhận không?** Có thể, nếu chữ ký Response **bao phủ đúng Assertion được dùng**, cert IdP được tin cậy, policy/profile cho phép, và mọi điều kiện SAML đều hợp lệ.
2. **Assertion ký hợp lệ, Response ngoài không ký, có được bỏ Destination/InResponseTo không?** Không. Phải kiểm Response/request context theo profile, dù Assertion bảo vệ các trường nằm bên trong nó.
3. **Response có A1 ký hợp lệ và A2 unsigned, Response không ký; dùng A1 có đủ không?** Theo pipeline mặc định Spring Security mô tả, **không**: hoặc Response phải ký hoặc **tất cả Assertions** phải ký.
4. **Một signature hợp lệ có bảo vệ mọi Assertion trong tài liệu không?** Không. Phải xem Reference, transforms, signed subtree và used node.
5. **Signature wrapping là gì?** Kiểm chữ ký của node A nhưng ứng dụng lại sử dụng node B không nằm trong vùng được ký.
6. **Tại sao signature đúng vẫn có thể bị từ chối?** Audience, issuer, recipient, destination, time, request state, replay hoặc chính sách quyền có thể không hợp lệ.
7. **Mã hóa Assertion có thay chữ ký không?** Không; giải mã là confidentiality, vẫn cần xác minh issuer/signature/conditions.
8. **Spring Security mặc định tạo principal từ Assertion nào?** Tài liệu overview của pipeline được mô tả lấy NameID/AttributeStatement từ **Assertion đầu tiên sau validation**. Custom converter hoặc version khác phải kiểm lại.
9. **Có nên dùng `getElementsByTagName("Assertion")` để lấy principal?** Không. Phải gắn logic với đúng validated and signed node qua thư viện SAML đã kiểm nghiệm.
10. **Khi IdP đổi signing cert mà SP không tin cert mới thì xử lý sao?** Cập nhật verification credentials/metadata trust và rollout có kiểm soát; không tắt signature validation.

## 17. Tài liệu chính thức

- Spring Security – SAML 2.0 Login Overview (pipeline, Response-or-all-Assertions signature policy, principal conversion): https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Authenticating SAML2 Responses (provider, validator, decrypter, converters): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Migration to 7 (response validation order): https://docs.spring.io/spring-security/reference/migration-7/saml2.html
- OWASP SAML Security Cheat Sheet (signature wrapping, exact signed assertion, XML validation): https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OASIS SAML 2.0 Core (Assertions, Protocols, Signatures): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles (Web Browser SSO, signature requirements): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Approved Errata (signature coverage/Response signature conditions): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html

**Cốt lõi để nhớ:** Chữ ký trên Response hợp lệ có thể bảo vệ Assertion lồng bên trong; chữ ký trên Assertion chỉ bảo vệ chính Assertion đó. **Dữ liệu quyết định NameID/attributes/role phải đến từ Assertion thực sự được chữ ký tin cậy bao phủ**, rồi còn phải qua đầy đủ **SAML conditions** và **application authorization**. Không lấy kết luận "signature valid" làm bằng chứng độc lập rằng mọi phần tử trong XML đều đáng tin.
