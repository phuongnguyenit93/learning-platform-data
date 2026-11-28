# Assertion signature — chữ ký số của SAML assertion

Trong SAML SSO, Service Provider (SP) nhận assertion do Identity Provider (IdP) phát hành để xác định người dùng. Assertion thường đi qua trình duyệt trước khi tới SP. Vì vậy, SP không thể tin một thông điệp chỉ vì nó có cấu trúc XML đúng hoặc có trường `Issuer` mang tên IdP quen thuộc.

**Assertion signature** là chữ ký số gắn với assertion. IdP ký bằng khóa riêng; SP xác minh bằng khóa công khai đã được tin cậy cho IdP đó. Việc xác minh phải trả lời được cả hai câu hỏi: nội dung được bảo vệ có bị thay đổi không, và khóa ký có thực sự thuộc đối tác được phép xác thực người dùng cho ứng dụng này không?

Sau bài học, người học cần phân biệt được chữ ký assertion với chữ ký response, đọc được các thành phần chính của XML Signature, và giải thích vì sao chữ ký hợp lệ chưa đủ để tạo phiên đăng nhập.

## 1. Chữ ký giải quyết vấn đề gì trong IAM?

Giả sử cổng nhân sự `HR Portal` dùng SSO của doanh nghiệp. IdP gửi assertion cho biết người dùng có mã nhân viên `EMP-1042`, phòng ban `Finance` và nhóm `payroll-reader`.

Nếu ứng dụng nhận nguyên văn những thuộc tính do trình duyệt gửi rồi cấp quyền, một người dùng có thể thử thay mã nhân viên hoặc đổi nhóm thành `payroll-admin`. Chữ ký cho phép SP phát hiện thay đổi trong dữ liệu được ký, thay vì tin lời khai của trình duyệt.

Tuy nhiên, cần tách các thuộc tính bảo mật sau:

| Cơ chế | Câu hỏi chính được giải quyết | Giới hạn cần nhớ |
|---|---|---|
| Chữ ký assertion | Assertion có được ký bằng khóa được chấp nhận và còn toàn vẹn không? | Không che giấu nội dung assertion |
| Mã hóa assertion | Bên nào có thể đọc nội dung assertion? | Không tự thay thế việc xác minh người phát hành |
| HTTPS | Kênh truyền giữa hai đầu kết nối có được bảo vệ không? | Không tự xác thực nội dung SAML đã đi qua trình duyệt |
| Kiểm tra điều kiện SAML | Assertion này có dùng được cho SP, thời điểm và yêu cầu hiện tại không? | Phải đi cùng kiểm tra chữ ký và nguồn tin cậy |
| Chính sách phân quyền của SP | Người dùng được phép làm gì trong ứng dụng? | Không suy ra toàn bộ quyền chỉ từ việc đăng nhập thành công |

Trong ví dụ trên, assertion được ký hợp lệ có thể cung cấp đầu vào cho RBAC hoặc ABAC. SP vẫn phải quyết định nhóm nào được ánh xạ thành quyền nào, áp dụng nguyên tắc ít quyền nhất và kiểm tra trạng thái tài khoản theo chính sách của mình.

## 2. XML Signature bảo vệ assertion như thế nào?

SAML sử dụng XML Signature. Hai việc mật mã khác nhau cần được phân biệt: kiểm tra digest của dữ liệu được tham chiếu và kiểm tra chữ ký trên `SignedInfo`. Một trong hai thất bại thì không thể coi chữ ký là hợp lệ. Đây là hai phần của core validation trong [W3C XML Signature, mục 3.2](https://www.w3.org/TR/xmldsig-core1/#sec-CoreValidation).

Các thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| `Assertion/@ID` | Định danh assertion trong tài liệu |
| `ds:Reference/@URI` | Chỉ ra đối tượng được bảo vệ, thường là `#` cộng ID assertion |
| `ds:Transforms` | Quy định các phép biến đổi trước khi tính digest |
| `ds:DigestMethod` và `ds:DigestValue` | Thuật toán băm và kết quả băm của dữ liệu sau biến đổi |
| `ds:CanonicalizationMethod` | Quy định chuẩn hóa `SignedInfo` trước khi ký/xác minh |
| `ds:SignatureMethod` | Thuật toán chữ ký |
| `ds:SignatureValue` | Giá trị chữ ký số |
| `ds:KeyInfo` | Thông tin hỗ trợ nhận diện khóa; không tự tạo ra sự tin cậy |

Có thể hình dung luồng tạo chữ ký như sau:

```text
Assertion có ID
    -> áp dụng transforms cho Reference
    -> tính digest
    -> đưa Reference và digest vào SignedInfo
    -> canonicalize SignedInfo
    -> ký bằng khóa riêng của IdP
```

SP kiểm tra lại các quan hệ này bằng thư viện xác minh. Digest đơn thuần không chứng minh ai phát hành dữ liệu: người sửa XML cũng có thể tự tính digest mới. Chữ ký bảo vệ `SignedInfo`, trong đó có digest và tham chiếu, mới ràng buộc các thông tin ấy với khóa ký.

Canonicalization (C14N) là chuẩn hóa theo thuật toán XML đã chọn. Không nên hiểu nó là “xóa mọi khoảng trắng”. Tự pretty-print, đổi namespace hoặc chuyển XML sang đối tượng khác rồi dựng lại trước khi xác minh có thể làm thay đổi dữ liệu cần kiểm tra.

## 3. Đọc một assertion có chữ ký

Ví dụ sau là XML minh họa đã rút gọn. Các chuỗi `DEMO_...` không phải digest/chữ ký Base64 thực; thời gian là dữ liệu ví dụ cố định. Không dùng thông điệp này làm token đăng nhập hoặc làm mẫu cấu hình sản xuất.

```xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="_assertion_demo_1042"
    Version="2.0"
    IssueInstant="2030-04-08T08:00:00Z">
  <saml:Issuer>https://idp.example.com/entity</saml:Issuer>

  <ds:Signature>
    <ds:SignedInfo>
      <ds:CanonicalizationMethod
          Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
      <ds:SignatureMethod
          Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
      <ds:Reference URI="#_assertion_demo_1042">
        <ds:Transforms>
          <ds:Transform
              Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
          <ds:Transform
              Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
        </ds:Transforms>
        <ds:DigestMethod
            Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
        <ds:DigestValue>DEMO_DIGEST</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>DEMO_SIGNATURE</ds:SignatureValue>
  </ds:Signature>

  <saml:Subject>
    <saml:NameID>EMP-1042</saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          Recipient="https://hr.example.com/saml/acs"
          InResponseTo="_request_demo_17"
          NotOnOrAfter="2030-04-08T08:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>

  <saml:Conditions
      NotBefore="2030-04-08T07:59:30Z"
      NotOnOrAfter="2030-04-08T08:05:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://hr.example.com/entity</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>

  <saml:AttributeStatement>
    <saml:Attribute Name="employeeGroup">
      <saml:AttributeValue>payroll-reader</saml:AttributeValue>
    </saml:Attribute>
  </saml:AttributeStatement>
</saml:Assertion>
```

Điểm đầu tiên cần đọc là cặp `ID="_assertion_demo_1042"` và `Reference URI="#_assertion_demo_1042"`. SP phải xác nhận tham chiếu trỏ duy nhất tới đúng assertion đang được xử lý.

Đây là dạng **enveloped signature**: chữ ký nằm bên trong phần tử được ký. Transform `enveloped-signature` loại chính phần tử chữ ký đang xét khỏi dữ liệu tính digest, tránh việc chữ ký phải chứa digest của chính nó. Các ràng buộc chữ ký SAML được quy định trong [SAML Core 2.0, mục 5](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf).

Nếu đổi `employeeGroup` trong assertion này, một bộ xác minh đúng phải phát hiện digest không còn khớp. Nếu thông điệp bổ sung một assertion khác bên ngoài đối tượng được ký, SP không được mặc nhiên xem assertion bổ sung ấy là đáng tin.

## 4. Assertion signature và response signature có phạm vi khác nhau

`samlp:Response` là thông điệp giao thức có thể chứa assertion; chữ ký trên response và chữ ký trên assertion không cùng đối tượng tham chiếu.

| Vị trí chữ ký | Phạm vi khi tham chiếu và transforms đúng | Điều SP phải phân biệt |
|---|---|---|
| Ký assertion | Assertion được tham chiếu | Không bảo vệ các thuộc tính nằm ở response bên ngoài |
| Ký response | Response được tham chiếu, gồm nội dung con được bao phủ | Không thể kết luận bằng việc chỉ thấy một phần tử `Signature` |
| Ký cả hai | Hai đối tượng được kiểm tra theo từng chữ ký | Mỗi chữ ký phải được xử lý theo yêu cầu profile và chính sách |
| Không ký | Không có bảo vệ chữ ký XML ở hai cấp này | Không đáp ứng chính sách yêu cầu assertion được ký của ví dụ |

Không dùng quy tắc chung “có bất kỳ một chữ ký là đủ” cho mọi tích hợp. Riêng Web Browser SSO dùng HTTP-POST để chuyển response, SAML Profiles 2.0 mục 4.1.4.5 yêu cầu các assertion chứa bên trong phải được ký. Mục 4.1.4.3 cũng yêu cầu xác minh các chữ ký hiện diện. Cần phân biệt yêu cầu profile với chế độ tương thích riêng của một sản phẩm. [Nguồn: OASIS SAML Profiles 2.0](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf).

Ví dụ, dù assertion đã ký, trường `Destination` ở response bên ngoài không trở thành dữ liệu có chữ ký assertion bảo vệ. SP vẫn phải kiểm tra thông điệp bao ngoài theo profile và chính sách tích hợp, đồng thời xác minh các ràng buộc trong assertion.

## 5. Khóa xác minh đến từ quan hệ tin cậy

Một chữ ký có thể hoàn toàn đúng về toán học nhưng do kẻ tấn công tạo bằng khóa riêng của họ. Nếu SP lấy chứng thư bất kỳ đính kèm trong `KeyInfo` rồi coi đó là nguồn tin cậy, người gửi đã tự chọn cả thông điệp lẫn khóa được dùng để xác minh mình.

Trong mô hình của bài học, quản trị viên cấu hình trước quan hệ tin cậy giữa HR Portal và IdP doanh nghiệp. Khóa xác minh được nạp từ cấu hình đã phê duyệt hoặc metadata được xác thực bằng cơ chế tin cậy độc lập. `KeyInfo`, nếu được dùng để chọn khóa, chỉ được chọn trong tập khóa đã cho phép.

SAML metadata có `KeyDescriptor` mô tả khóa của một entity; thuộc tính `use` có thể nêu mục đích `signing` hoặc `encryption`. Metadata phải được xác thực trước khi khóa trong đó được dùng làm căn cứ tin cậy. [Nguồn: OASIS SAML Metadata 2.0, mục 2.4.1.1 và 4](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf).

Ba trường hợp cần nhận diện khi vận hành:

- **Nhiều tenant:** khóa được chấp nhận cho tenant A không tự trở thành khóa hợp lệ cho tenant B.
- **Nhiều mục đích khóa:** chứng thư HTTPS của IdP không mặc nhiên là chứng thư ký SAML của IdP.
- **Thông tin chưa xác minh:** `Issuer` đọc từ XML có thể hỗ trợ tra cứu cấu hình đối tác, nhưng chỉ là gợi ý chưa tin cậy cho đến khi kiểm tra thành công bằng cấu hình đó.

`saml:Issuer` là định danh bên phát hành assertion, khác với trường issuer của chứng thư X.509 vốn mô tả bên cấp chứng thư. Một chứng thư có tên tổ chức quen thuộc cũng không tự cấp quyền phát hành danh tính cho mọi ứng dụng.

## 6. Tránh XML Signature Wrapping: dùng đúng đối tượng đã được xác minh

**XML Signature Wrapping (XSW)** khai thác sự khác biệt giữa đối tượng bộ xác minh kiểm tra và đối tượng ứng dụng lấy dữ liệu. Kẻ tấn công có thể giữ nguyên một assertion đã ký, nhưng bố trí thêm XML để ứng dụng đọc một assertion khác.

Ví dụ khái niệm sau mô tả luồng xử lý sai, không phải một payload SAML hợp lệ:

```text
Tài liệu nhận vào
├── Assertion A: dữ liệu người dùng bình thường, chữ ký hợp lệ
└── Assertion B: dữ liệu giả, không được ký

Mã xác minh: tìm thấy chữ ký của A -> trả về true
Mã đăng nhập: lấy NameID/role từ B -> cấp phiên hoặc quyền sai
```

Vấn đề không phải thuật toán ký bị phá. Vấn đề là giá trị `true` không ràng buộc với đối tượng mà ứng dụng sử dụng sau đó.

Thiết kế SP cần từ chối ID trùng hoặc tham chiếu mơ hồ, kiểm soát cấu trúc XML, và chỉ lấy danh tính/thuộc tính từ assertion đã được xác minh. Không tìm `NameID` hoặc `Attribute` tùy ý trên toàn cây XML sau khi kiểm tra một chữ ký khác. OWASP mô tả nhóm lỗi này và yêu cầu kiểm tra schema bằng bản tin cậy, xác minh khóa và xử lý XML đúng cách trong [SAML Security Cheat Sheet, phần Validate Signatures](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html#validate-signatures).

Một chính sách minh họa cho HR Portal là chỉ nhận đúng một assertion dùng để đăng nhập. Nếu tích hợp cần nhiều assertion, phải định nghĩa riêng cách chọn và xác minh từng assertion được tiêu thụ; không tùy tiện lấy phần tử đầu tiên hoặc cuối cùng.

## 7. Từ XML đầu vào đến phiên đăng nhập

Luồng dưới đây là thiết kế minh họa cho HR Portal sử dụng SP-initiated SSO và yêu cầu assertion có chữ ký. Các hàm là mã giả, không phải API Java hoặc cấu hình của một framework cụ thể.

```text
handleSamlPost(encodedResponse, loginContext):
    partner = configuredPartnerFor(loginContext)

    document = boundedSecureParse(encodedResponse)
    requireExpectedSamlStructure(document)
    requireUniqueIds(document)

    assertion = requireSingleLoginAssertion(document)
    requireSignatureOn(assertion)

    verifiedAssertion = verifyAndBindAssertion(
        assertion,
        trustedSigningKeys = partner.approvedSigningKeys,
        allowedAlgorithms = partner.algorithmPolicy,
        allowedReferences = sameAssertionOnly
    )

    verifyOtherRequiredOrPresentSignatures(document, partner)
    validateResponseForCurrentFlow(document, loginContext, partner)
    validateAssertionForCurrentFlow(verifiedAssertion, loginContext, partner)

    requireAllowedSubjectAndAttributes(verifiedAssertion, partner)
    atomicallyRejectReplayAndRecordUse(
        issuer = verifiedAssertion.issuer,
        assertionId = verifiedAssertion.id,
        retention = acceptedAssertionLifetimeIncludingClockTolerance
    )

    principal = mapVerifiedIdentity(verifiedAssertion, partner)
    return createApplicationSession(principal)
```

Các hàm xác minh phải kiểm soát tham chiếu và transforms, không tự tải dữ liệu hay khóa từ URL do thông điệp đưa vào. Parser cần giới hạn tài nguyên, vô hiệu hóa DTD/external entities và không tải schema tùy ý. Khi dùng schema validation, tránh cơ chế làm thay đổi cây XML đang được xác minh. [W3C XML Signature Best Practices](https://www.w3.org/TR/xmldsig-bestpractices/) phân tích các rủi ro xử lý tham chiếu, transforms và thay đổi DOM này.

Sau khi chữ ký hợp lệ, SP vẫn cần đối chiếu:

- **Issuer:** đúng IdP được phép cho ứng dụng và tenant hiện tại.
- **AudienceRestriction:** cho phép SP hiện tại sử dụng assertion.
- **Recipient/Destination:** phù hợp endpoint ACS và thông điệp của luồng đang xử lý.
- **Thời gian:** các điều kiện hiệu lực và thời hạn bearer confirmation đều được chấp nhận; độ lệch đồng hồ phải hữu hạn và được cấu hình rõ.
- **InResponseTo:** tương ứng yêu cầu đăng nhập đang chờ trong SP-initiated SSO.
- **Replay:** assertion chưa được dùng trong cửa sổ chấp nhận.
- **Ngữ cảnh xác thực và danh tính:** đáp ứng mức xác thực yêu cầu, có ánh xạ người dùng hợp lệ và thuộc tính phù hợp hợp đồng tích hợp.

Đối với IdP-initiated SSO, không có cùng quan hệ với một AuthnRequest đang chờ. Nếu sản phẩm hỗ trợ luồng đó, phải bật bằng chính sách riêng; không “sửa” lỗi `InResponseTo` của SP-initiated SSO bằng cách tắt kiểm tra tương quan toàn hệ thống.

Replay cache cần được chia sẻ hoặc bảo đảm nhất quán giữa các instance của SP. Kiểm tra rồi ghi bằng hai thao tác độc lập có thể cho hai yêu cầu đồng thời cùng vượt qua. Khóa cache nên gắn assertion ID với bên phát hành, và thời gian giữ phải bao phủ cửa sổ thực tế SP còn chấp nhận assertion, kể cả dung sai đồng hồ.

## 8. Chính sách thuật toán và vòng đời khóa

SP cần có danh sách thuật toán được chấp nhận, gồm thuật toán chữ ký, digest, canonicalization và transforms. Không chấp nhận mọi thuật toán chỉ vì thư viện có thể xử lý. Ví dụ XML của bài dùng RSA-SHA256 cùng SHA-256; lựa chọn thực tế còn phải phù hợp chính sách mật mã và khả năng của hai bên.

Các thao tác vận hành sau là ví dụ chính sách cho HR Portal:

1. Ghi nhận các khóa ký được phê duyệt cho từng đối tác, người phê duyệt và thời điểm áp dụng.
2. Khi đổi khóa theo kế hoạch, đưa khóa mới vào tập tin cậy trước khi IdP bắt đầu ký bằng khóa mới.
3. Kiểm tra đăng nhập qua mọi instance SP trong giai đoạn chấp nhận khóa cũ và mới.
4. Ngừng chấp nhận khóa cũ sau khi hết cửa sổ chuyển đổi đã định, có tính tới thời hạn assertion và độ trễ phân phối cấu hình.
5. Nếu nghi lộ khóa, dùng quy trình sự cố để thu hồi sự tin cậy; không tiếp tục giai đoạn chồng lấn thông thường chỉ để giữ đăng nhập hoạt động.

Vòng đời chứng thư, hiệu lực metadata và thời hạn assertion là các đồng hồ khác nhau. Không suy luận “chứng thư còn hạn nên assertion còn dùng được” hoặc “assertion hết hạn nên khóa ký phải thay”. Khi sự cố ảnh hưởng danh tính, còn phải đánh giá các phiên ứng dụng đã tạo trước đó; thay khóa không tự đăng xuất mọi phiên.

## 9. Tình huống kiểm chứng và chẩn đoán

Bảng sau là các tình huống học tập cho chính sách HR Portal đã mô tả, không phải báo cáo đã chạy kiểm thử trên một sản phẩm cụ thể.

| Tình huống | Kết quả mong đợi | Lý do |
|---|---|---|
| Assertion được ký bằng khóa IdP đã phê duyệt, mọi điều kiện đều đúng | Có thể tiếp tục ánh xạ danh tính | Đã vượt kiểm tra thông điệp, chưa có nghĩa là có mọi quyền |
| Đổi `employeeGroup` sau khi ký | Từ chối | Dữ liệu được tham chiếu không còn khớp digest |
| Tự ký bằng khóa người gửi rồi đính kèm chứng thư | Từ chối | Khóa không thuộc quan hệ tin cậy |
| Xóa chữ ký assertion nhưng giữ một chữ ký response | Từ chối theo chính sách ví dụ | Không còn đáp ứng yêu cầu ký assertion |
| Chữ ký đúng nhưng audience là ứng dụng khác | Từ chối | Assertion không dành cho HR Portal |
| Chữ ký đúng nhưng assertion hết hiệu lực | Từ chối | Chữ ký không gia hạn điều kiện sử dụng |
| Gửi lại assertion đã dùng | Từ chối | Phát hiện replay |
| Thêm assertion giả để bộ đọc thuộc tính chọn nhầm | Từ chối | Không khớp cấu trúc và đối tượng đã xác minh |
| Khóa mới đã được phê duyệt trong giai đoạn chuyển đổi | Chấp nhận nếu mọi kiểm tra khác đạt | Tập tin cậy cho phép khóa mới |
| Không lấy được cấu hình khóa tin cậy | Không tạo phiên mới từ thông điệp chưa xác minh | Không có căn cứ xác thực người phát hành |

Khi đăng nhập thất bại, cần phân biệt `UNTRUSTED_SIGNING_KEY`, `SIGNATURE_INVALID`, `SIGNED_OBJECT_MISMATCH`, `ASSERTION_EXPIRED`, `AUDIENCE_MISMATCH` và `REPLAY_DETECTED`. Những mã này là ví dụ do ứng dụng định nghĩa; thông báo thực tế tùy sản phẩm.

Log nên ghi mã tương quan, đối tác, dấu nhận diện khóa phù hợp và nhóm lỗi. Tránh ghi nguyên assertion, thuộc tính cá nhân hoặc dữ liệu đăng nhập nhạy cảm. Lỗi chữ ký xuất hiện sau khi đổi khóa cần được đối chiếu tập khóa đang triển khai trên từng instance, thay vì tắt xác minh để khôi phục tạm thời.

## 10. Tự kiểm tra hiểu biết

**Chữ ký đúng nhưng `Audience` sai thì có đăng nhập được không?** Không. Toàn vẹn mật mã và điều kiện sử dụng là hai kiểm tra khác nhau.

**Vì sao không tin chứng thư trong `KeyInfo` ngay lập tức?** Vì đó là dữ liệu đi cùng thông điệp do bên gửi cung cấp. Nó phải được đối chiếu với quan hệ tin cậy đã thiết lập.

**Vì sao vẫn có XSW khi thư viện báo chữ ký hợp lệ?** Vì ứng dụng có thể lấy danh tính từ đối tượng khác với đối tượng mà thư viện đã xác minh.

**Assertion có chữ ký có ngăn người dùng đọc thuộc tính không?** Không. Muốn bảo mật nội dung cần cơ chế thích hợp như mã hóa assertion và bảo vệ kênh truyền.

**Khi nào SP được tạo phiên?** Sau khi đã xác minh đúng đối tượng bằng khóa được tin cậy, chấp nhận mọi điều kiện của luồng SAML, ngăn replay và ánh xạ danh tính theo chính sách ứng dụng. Quyền truy cập từng tài nguyên tiếp tục chịu kiểm soát của SP.
