# Xác minh chữ ký metadata SAML 2.0 bằng khóa tin cậy được cấp qua kênh độc lập

## 1. Mục tiêu và tình huống thực tế

Trong liên kết đăng nhập SAML 2.0, **Service Provider (SP)** là ứng dụng sử dụng kết quả đăng nhập, còn **Identity Provider (IdP)** là hệ thống xác thực và phát hành SAML Assertion. Trước khi hai bên trao đổi AuthnRequest và SAML Response, SP thường tải **metadata** của IdP để biết:

- **IdP Entity ID**: định danh của nhà phát hành.
- **SingleSignOnService**: URL và binding mà SP sẽ gửi yêu cầu đăng nhập đến.
- **KeyDescriptor**: thông tin khóa/certificate IdP công bố để các đối tác xác minh chữ ký SAML Response/Assertion hoặc mã hóa dữ liệu.
- Các chính sách hoặc khả năng khác: `WantAuthnRequestsSigned`, NameID format, Single Logout, `validUntil` và `cacheDuration` nếu được công bố.

Metadata là một phần **cấu hình bảo mật của liên kết**. Nếu ai đó thay được nội dung metadata trước khi SP tin nó, họ có thể thay IdP SSO endpoint hoặc khóa xác minh assertion. SP khi đó có nguy cơ chuyển người dùng sang IdP giả hoặc tin một assertion được ký bởi khóa của kẻ tấn công.

Đề bài này tập trung vào **xác minh chữ ký XML của chính metadata SAML 2.0** bằng **khóa tin cậy đã được cung cấp và kiểm chứng qua một kênh độc lập với metadata đang tải**.

**Nguyên tắc cốt lõi:** một chữ ký XML có giá trị mật mã chỉ chứng minh rằng tài liệu được ký bằng một khóa nhất định. Để chấp nhận metadata, SP còn phải biết **khóa đó thuộc về nhà phát hành metadata được phép tin cậy**. Nếu khóa được chọn chỉ vì nó nằm trong chính tài liệu chưa được xác minh, kiểm tra có thể bị lừa.

Kết quả học tập: phân biệt metadata-signing key với assertion-signing key, biết quy trình thiết lập trust anchor, hiểu phạm vi của XML Signature, biết cách cấu hình Spring Security thích hợp và xử lý cập nhật/thu hồi khóa an toàn.

## 2. Metadata SAML 2.0 là gì và chữ ký nằm ở đâu?

Tài liệu metadata SAML sử dụng namespace `urn:oasis:names:tc:SAML:2.0:metadata`, thường có một trong hai dạng:

- **`<md:EntityDescriptor>`**: mô tả một SAML entity như một IdP hoặc một SP; có `entityID`.
- **`<md:EntitiesDescriptor>`**: tập hợp nhiều `EntityDescriptor` và có thể lồng các nhóm, thường gặp ở federation operator hoặc metadata aggregator.

SAML metadata có thể chứa chữ ký theo chuẩn **XML Digital Signature (XMLDSig)** ở phần tử `<ds:Signature>`. Chữ ký có thể bảo vệ `EntityDescriptor` riêng lẻ hoặc một `EntitiesDescriptor` chứa nhiều entity. Nội dung dưới một phần tử **đã được ký hợp lệ** được bảo vệ theo phạm vi tham chiếu thực tế của chữ ký.

Ví dụ bản đồ khái niệm:

```text
md:EntitiesDescriptor (ID="_federation", validUntil="...")
  ds:Signature
    ds:SignedInfo
      ds:Reference URI="#_federation"
      ds:DigestMethod
      ds:SignatureMethod
    ds:SignatureValue
    ds:KeyInfo                  <- thông tin gợi ý khóa, chưa tự đáng tin
  md:EntityDescriptor (entityID="https://idp-a.example.test/saml")
    md:IDPSSODescriptor
      md:KeyDescriptor          <- khóa dùng cho SAML message, khác chức năng
      md:SingleSignOnService
  md:EntityDescriptor (entityID="https://idp-b.example.test/saml")
    ...
```

Sơ đồ là **mô tả quan hệ**, không phải XML hoàn chỉnh. Nếu kiểm tra chữ ký của root `EntitiesDescriptor` đúng theo hồ sơ SAML, các entity con nằm trong phạm vi được ký có thể thừa hưởng bảo đảm toàn vẹn từ root. Nhưng SP vẫn cần kiểm tra **entity nào được phép**, `entityID` nào mong đợi, vai trò IdP nào cần sử dụng, thời hạn và cấu hình trust.

### 2.1. Ba vị trí dễ bị nhầm là “khóa tin cậy”

| Vị trí/đối tượng | Chức năng | Có tự trở thành trust anchor không? |
| --- | --- | --- |
| `ds:KeyInfo` trong `ds:Signature` của metadata | Có thể chứa hoặc gợi ý public key/certificate của **người ký metadata** | **Không**; cần kiểm chứng khóa qua trust policy độc lập |
| `md:KeyDescriptor` trong `IDPSSODescriptor` | Công bố khóa của IdP cho **ký SAML message/assertion** hoặc mã hóa | **Chỉ được tin sau khi nguồn metadata đã được xác thực** |
| Khóa/certificate đã cấp qua kênh độc lập | Cơ sở để SP nhận diện **người ký metadata được phép** | **Có thể làm trust anchor** nếu đã kiểm chứng và gắn với đúng đối tác |

Cùng một tổ chức có thể dùng một certificate cho nhiều vai trò, nhưng không được **mặc định** như vậy. Việc metadata được aggregator ký bằng khóa của federation operator không có nghĩa IdP bên trong dùng chính khóa aggregator để ký SAML Assertion.

### 2.2. Metadata chữ ký khác SAML Response chữ ký

Đây là **hai thời điểm và hai đối tượng khác nhau**:

1. **Lúc nhập/refresh metadata:** kiểm tra chữ ký của tài liệu XML metadata bằng **metadata trust anchor đã có từ trước**. Chỉ sau đó mới sử dụng thông tin IdP bên trong.
2. **Lúc người dùng đăng nhập:** kiểm tra chữ ký của SAML Response/Assertion bằng **khóa của IdP đã xác thực qua trust configuration/metadata**; đồng thời kiểm tra issuer, audience, thời gian, destination, recipient và các điều kiện khác.

SP có thể xác minh SAML Response rất chặt nhưng vẫn bị lộ nếu nó đã **nạp sai khóa xác minh response từ metadata giả**.

## 3. Vì sao phải cấp khóa qua kênh độc lập?

Giả sử SP tải metadata từ `https://login.example.test/saml/metadata`. Nếu chỉ làm:

```text
1. Tải metadata XML.
2. Đọc ds:KeyInfo/X509Certificate trong XML vừa tải.
3. Dùng chính certificate đó kiểm tra ds:Signature của XML.
4. Nếu valid thì tin toàn bộ metadata.
```

Kẻ tấn công có thể tạo một cặp khóa mới, thay endpoint/KeyDescriptor trong metadata, **tự ký metadata bằng khóa mới** và đưa public key mới vào `ds:KeyInfo`. Chữ ký sẽ khớp **khóa do chính kẻ tấn công chọn**. Kết quả `signatureValid=true` trong bước 3 không chứng minh metadata đó thuộc đối tác thật.

Đây là **lỗi thiết lập niềm tin vòng tròn**: dùng nội dung chưa tin để quyết định ai đáng tin, rồi dùng người ấy để xác minh chính nội dung đó.

Luồng đúng:

```text
                   KÊNH ĐỘC LẬP ĐÃ XÁC THỰC
IdP / Federation operator --------------------> Người quản trị SP
             Certificate hoặc public key        |
             + danh tính đối tác                 | duyệt và lưu trust anchor
             + fingerprint SHA-256               v
                                                SP Trust Store
                                                     |
                                                     | khóa đã được tin cậy
                                                     v
NGUỒN METADATA                                XML Signature Verifier
https://.../metadata ------------------------> kiểm tra chữ ký
                                                     |
                                             PASS + policy checks
                                                     |
                                                     v
                                        Metadata được phép sử dụng
                                         Entity ID, SSO URL, keys
                                                     |
                                                     v
                                        Cấu hình SAML đăng nhập
```

**“Kênh độc lập”** không nhất thiết là một mạng vật lý thứ hai. Nó là **chuỗi cấp phát và xác thực tin cậy riêng**, không được điều khiển bằng nội dung metadata chưa xác minh. Ví dụ:

- Quản trị viên IdP công bố **fingerprint SHA-256 của certificate** qua cổng quản trị đã đăng nhập và được bảo vệ; đội SP đối chiếu với certificate nhận được qua một cơ chế phân phối khác.
- Certificate metadata-signer được đưa vào repository cấu hình có kiểm soát thay đổi/code review hoặc kho certificate/secret của tổ chức, sau khi đã xác minh người cấp.
- Trong quan hệ federation có operator được tổ chức tin cậy, SP nhận certificate của **operator** qua quy trình onboarding chính thức; metadata tổng hợp của operator được xác minh theo certificate ấy.
- Đối tác trao đổi certificate qua quy trình bảo mật có xác minh danh tính người liên hệ và xác nhận fingerprint trên một kênh đã biết trước.

**Chỉ nhận một certificate qua cùng email/link chưa được xác minh rồi so với fingerprint cũng xuất hiện cùng email/link đó chưa tạo được kênh độc lập.** Nếu kẻ tấn công thay được cả certificate lẫn fingerprint trên cùng nguồn, phép so sánh trở nên vô nghĩa.

## 4. Khóa nào thực sự phải được pin/trust?

Trong mô hình kiểm tra chữ ký metadata, SP có thể dùng:

1. **Pinned signing certificate/public key**: một hoặc nhiều khóa công khai đã được phê duyệt cho metadata của đúng IdP/operator.
2. **Trust anchor PKIX được giới hạn**: một hoặc một số CA/chain/certificate đã được phê duyệt theo chính sách, kèm kiểm tra danh tính đối tác, usage, thời hạn/thu hồi khi áp dụng.
3. **Trust của federation operator**: SP tin người ký metadata tổng hợp; chỉ nhận các entity được operator ký trong phạm vi federation đã thỏa thuận.

Lựa chọn nào cũng phải trả lời:

- **Ai** có quyền ký metadata này?
- **Khóa nào** được phép dùng?
- **Với scope nào**: một IdP cụ thể, nhóm entity, tenant, federation hay môi trường?
- **Đến khi nào**: thời gian hiệu lực của trust anchor và metadata?
- **Ai** được thêm/xóa khóa và kiểm toán quyết định đó?

**Không tự động coi toàn bộ CA trust store dùng cho HTTPS của JVM là danh sách đối tác được phép ký metadata.** Trust cho TLS server identity và trust cho việc ký tài liệu metadata có mục đích khác nhau; nếu dùng PKIX cho metadata thì phải có policy ràng buộc signer và danh tính đối tác, thay vì chấp nhận bất cứ certificate công khai hợp lệ nào.

### 4.1. Fingerprint SHA-256 là gì?

Certificate X.509 thường được lưu dưới PEM hoặc DER. Fingerprint là **hash của certificate**; ví dụ kiểm tra bằng OpenSSL:

```bash
openssl x509 -in metadata-signer.pem -noout -fingerprint -sha256
```

Lệnh chỉ **tính fingerprint** từ file đã có, **không tự chứng minh certificate là đáng tin**. Người quản trị phải so sánh kết quả với fingerprint đã nhận từ **nguồn đã xác thực độc lập**. Nếu đổi certificate nhưng giữ nguyên public key, fingerprint certificate cũng có thể đổi; cần ghi rõ đang pin **certificate** hay **public key** để xử lý rotation đúng.

Không dùng MD5/SHA-1 fingerprint như cơ sở kiểm tra mới. Fingerprint cần được kiểm tra nguyên giá trị, và thao tác phê duyệt phải gắn với đúng IdP hoặc federation operator.

## 5. Quy trình xác minh metadata trước khi đưa vào sử dụng

Hãy tách rõ **giai đoạn cấp trust anchor** và **giai đoạn tải/kiểm tra metadata**.

### Giai đoạn A — Bootstrap trust

1. Xác minh danh tính tổ chức/nhà cung cấp và vai trò của người quản trị đang cấp khóa.
2. Nhận certificate/public key metadata signer qua quy trình đã phê duyệt.
3. Đối chiếu fingerprint SHA-256 bằng kênh kiểm chứng độc lập.
4. Lưu khóa ở nơi chỉ đội/hệ thống được phép có quyền thay đổi, ví dụ trust store hoặc cấu hình triển khai được quản trị.
5. Ràng buộc trust anchor với **đúng nhà phát hành/metadata source, môi trường và danh sách entity được cho phép**.
6. Ghi owner, thời hạn, cách refresh và quy trình rotation/rollback; kiểm tra rằng SP có thể lấy khóa ấy khi khởi động.

### Giai đoạn B — Nhập metadata đã ký

1. Tải metadata từ **nguồn đã định trước** qua HTTPS hợp lệ; áp dụng timeout, giới hạn kích thước và chính sách redirect.
2. Parse XML an toàn, chặn DTD/external entity (XXE), XInclude, external references và các transform nguy hiểm; dùng thư viện SAML/XMLDSig đã được bảo trì.
3. Xác định **phần tử `EntityDescriptor` hoặc `EntitiesDescriptor` được ký**, vị trí `ds:Signature`, `ID` và `ds:Reference`.
4. Lấy **verification key từ trust store bên ngoài**, không lấy quyết định trust từ `ds:KeyInfo` hoặc `md:KeyDescriptor` của tài liệu chưa kiểm tra.
5. Kiểm tra chữ ký XMLDSig: SignedInfo, thuật toán và canonicalization được phép, reference/digest, chữ ký mật mã và **đúng phạm vi nội dung được bảo vệ**. Từ chối chữ ký không hợp lệ hoặc chưa đủ điều kiện trust.
6. Kiểm tra **entityID và role dự kiến**, nhà phát hành ký có quyền công bố entity ấy, các phần tử mục tiêu thực sự nằm trong vùng đã xác minh.
7. Kiểm tra `validUntil`, `cacheDuration`, phiên bản/trạng thái theo chính sách; ngăn dữ liệu quá hạn hoặc bị thu hồi.
8. **Chỉ sau khi vượt qua các bước trên**, mới lấy SSO/SLO endpoints, signing/encryption certificates và thuộc tính IdP để cập nhật `RelyingPartyRegistration`.
9. Lưu audit về signer, fingerprint trust anchor, entityID, thời gian, kết quả và lý do lỗi. Không ghi khóa bí mật hoặc toàn bộ metadata chứa nội dung nhạy cảm không cần thiết.

### Giai đoạn C — Refresh định kỳ

Mỗi lần tải metadata mới cần kiểm tra lại như lần đầu. Một metadata đã ký hợp lệ hôm qua **không khiến phiên bản tải hôm nay mặc nhiên đáng tin**. Nếu metadata mới có khóa IdP mới, nó chỉ được sử dụng sau khi metadata mới được kiểm tra bằng trust anchor hợp lệ.

**Chính sách fail closed:** không nhập và kích hoạt metadata chưa xác minh. Nếu refresh thất bại, có thể tiếp tục dùng bản metadata **trước đó đã được xác minh và còn hiệu lực** nếu chính sách vận hành cho phép. Không vô hạn dùng dữ liệu đã quá hạn hay tự chuyển sang bỏ signature validation để duy trì đăng nhập.

## 6. Những trường XMLDSig cần hiểu

| Thành phần | Vai trò | Sai lầm cần tránh |
| --- | --- | --- |
| `ds:Signature` | Chữ ký XML gắn với phần tử metadata | Chỉ tìm một tag tên Signature rồi coi toàn XML đã ký |
| `ds:SignedInfo` | Thuật toán, canonicalization và danh sách reference | Tin SignedInfo trước khi xác thực bằng trust key |
| `ds:Reference URI="#..."` | Chỉ phần tử XML được bảo vệ | Chấp nhận reference trỏ sai phần tử hoặc XML không được dùng |
| `ds:DigestMethod` / `DigestValue` | Hash của nội dung đã transform | Dùng SHA-1 cũ hoặc bỏ kiểm tra digest |
| `ds:SignatureMethod` / `SignatureValue` | Chữ ký mật mã trên SignedInfo | Ký bởi khóa lạ nhưng lại tin vì chữ ký hợp lệ với khóa lạ đó |
| `ds:CanonicalizationMethod` | Chuẩn hóa XML trước khi kiểm tra | Tự so sánh text XML thay cho canonicalization chuẩn |
| `ds:Transforms` | Biến đổi đầu vào của reference | Cho phép transform tùy ý truy cập mạng/thực thi XSLT |
| `ds:KeyInfo` | Gợi ý khóa/chứng thư của người ký | Lấy KeyInfo trong metadata chưa tin làm trust anchor |
| `md:EntityDescriptor/@ID` | ID của phần tử dùng trong XML reference | Nhầm `ID` với `entityID` hoặc xử lý duplicate ID thiếu an toàn |
| `md:EntityDescriptor/@entityID` | Danh tính logic của entity | Coi entityID là bằng chứng chữ ký/trust |

**SAML Metadata Signature Profile** yêu cầu dạng enveloped signature cho các phần tử metadata được ký; phần tử được ký phải có định danh `ID`, và reference chỉ đến chính ID đó, chẳng hạn `URI="#_metadata_001"`. Không giả định một `Reference URI=""` tổng quát cho toàn document là phù hợp với **SAML metadata profile**. Phạm vi ký của `EntitiesDescriptor` cũng khác với ký riêng một `EntityDescriptor` con.

### 6.1. Chống XML Signature Wrapping

Một dạng tấn công là để XML chứa:

- Một phần tử **đã ký hợp lệ** nhưng không phải phần tử mà chương trình sử dụng.
- Một phần tử **khác chưa được ký** với tên/ID/cấu trúc dễ khiến bộ xử lý lấy nhầm.
- `ds:Reference` trỏ đến ID không tương ứng phần tử được đưa vào cấu hình, hoặc ID bị trùng/không đăng ký kiểu ID đúng.

Nếu ứng dụng chỉ gọi `getElementsByTagName(...)` và lấy phần tử đầu tiên, nó có thể dùng **nội dung khác với nội dung đã được xác minh**.

Cách phòng ngừa:

1. Dùng parser XML an toàn và thư viện xử lý SAML metadata/XMLEnc/XMLDSig chuyên dụng.
2. Ràng buộc reference đến **phần tử metadata dự kiến**; kiểm tra đường đi, vị trí, ID duy nhất và cây XML dùng để lấy dữ liệu.
3. Chỉ trích xuất entity/khóa/endpoint từ **DOM hoặc đối tượng thực sự đã được xác minh**, không parse lại một bản khác.
4. Giới hạn thuật toán, reference URI, transform, kích thước và số lượng phần tử.
5. Với metadata tổng hợp, xác nhận entity cần dùng nằm trong **phạm vi chữ ký của aggregator đã tin**, không chỉ nằm trong cùng file.

**Chữ ký hợp lệ trên “một phần” không chứng minh toàn bộ cấu hình trong file là đáng tin.** Đây là vấn đề xác minh *cái gì đã được ký* chứ không chỉ *ai đã ký*.

## 7. Phân biệt chữ ký metadata, TLS và chữ ký assertion

| Kiểm soát | Bảo vệ điều gì | Không thay thế được |
| --- | --- | --- |
| **HTTPS/TLS** khi tải metadata | Xác thực endpoint TLS theo trust TLS và bảo vệ kênh trong khi truyền | Không tự bảo đảm metadata được ký bởi đúng metadata signer/federation operator theo chính sách |
| **XMLDSig của metadata** + trust anchor độc lập | Toàn vẹn, xuất xứ của **nội dung metadata được ký** | Không tự xác thực người dùng, không thay thế kiểm tra hết hạn/đối tác được phép |
| **Chữ ký SAML Response/Assertion** | Xác minh thông điệp đăng nhập do IdP tin cậy ký | Không chứng minh metadata ban đầu lấy từ đúng nguồn nếu quá trình bootstrap sai |
| **Kiểm tra Entity ID, Audience, Recipient, thời gian** | Đảm bảo response đúng issuer, đúng SP, đúng yêu cầu và còn hiệu lực | Không thay thế xác thực chữ ký |
| **Authorization của ứng dụng** | Quyết định user có quyền trên chức năng/tài nguyên không | Không sửa được lỗi tin metadata/IdP giả |

SAML metadata spec **không yêu cầu mọi metadata đều bắt buộc phải có XML Signature trong mọi mô hình trao đổi**: có các trường hợp truyền trực tiếp qua kênh đáng tin và phương thức xác thực nguồn độc lập. Tuy nhiên, **nếu chính sách tích hợp yêu cầu “signed metadata với khóa out-of-band”**, SP phải **từ chối metadata không có chữ ký được tin cậy**, dù HTTPS vẫn hoạt động.

Không trộn hai lựa chọn thành “HTTPS luôn đủ, khỏi cần chữ ký” hoặc “chữ ký XML luôn đủ, khỏi cần bảo vệ đường tải”. Đó là hai lớp bảo vệ có phạm vi riêng.

## 8. Spring Security: sử dụng metadata signer credential đúng mục đích

### 8.1. Cơ chế cần nắm

Các bản Spring Security hiện đại có `RelyingPartyRegistration` để mô tả SP–IdP, và có API **`AssertingPartyMetadataRepository`** hỗ trợ việc quản lý metadata phía IdP. Tài liệu Spring Security công bố hỗ trợ xác minh chữ ký metadata qua **`OpenSaml5AssertingPartyMetadataRepository`** khi cung cấp danh sách `Saml2X509Credential` dùng cho metadata verification.

Điểm đặc biệt cần nhớ từ tài liệu Spring Security:

> Với `OpenSaml5AssertingPartyMetadataRepository`, nếu **không** cung cấp verification credentials, component **không thực hiện metadata signature validation**.

Vì vậy, viết `RelyingPartyRegistrations.fromMetadataLocation(...)` để nạp metadata hoặc chỉ khai `assertingparty.metadata-uri` trong YAML **không tự chứng minh** đã áp dụng chính sách xác minh **chữ ký metadata bằng trust anchor độc lập**. Một thư viện có thể giúp phân tích metadata mà không nhất thiết có đủ tín nhiệm để nhận nó.

**Phân biệt hai bộ credential trong ứng dụng:**

- **Metadata-verification credential:** SP dùng để xác minh **metadata document** mà nó tải hoặc refresh; được provision từ nguồn độc lập.
- **Asserting-party verification credential:** SP dùng để xác minh **SAML Response/Assertion** khi người dùng đăng nhập; thường là khóa IdP được công bố trong metadata đã tin cậy.

Certificate cho metadata signer và certificate ký assertion có thể khác nhau. Không cấu hình nhầm metadata signer vào nơi chỉ kiểm tra SAML response, rồi tưởng XML metadata đã được xác minh.

### 8.2. Mẫu cấu hình verificationCredentials

Đoạn sau mô tả **cách gọi API được Spring Security tài liệu hóa**. Nó được đặt **bên trong một lớp cấu hình Spring phù hợp**, với biến `trustedMetadataSignerCertificate` là `X509Certificate` đã đọc từ **trust store được cấp và xác minh ngoài luồng tải metadata**:

```java
// Trích đoạn trong ứng dụng dùng phiên bản Spring Security có API này.
// trustedMetadataSignerCertificate: java.security.cert.X509Certificate
Saml2X509Credential metadataVerificationCredential =
    Saml2X509Credential.verification(trustedMetadataSignerCertificate);

AssertingPartyMetadataRepository metadataRepository =
    OpenSaml5AssertingPartyMetadataRepository
        .withMetadataLocation("https://idp.example.test/saml/metadata")
        .verificationCredentials(credentials ->
            credentials.add(metadataVerificationCredential))
        .build();
```

Đoạn này **không phải file Java độc lập**; cần import các class Spring Security tương ứng và dependency SAML Service Provider/OpenSAML tương thích. API `OpenSaml5AssertingPartyMetadataRepository` và kiểu cấu hình có thể chưa có trong phiên bản Spring Security cũ. Trước khi áp dụng, đối chiếu **đúng Javadoc/phiên bản** của dự án.

Phần quan trọng trong bài là **nguồn** của `trustedMetadataSignerCertificate`: phải do SP **đã tin trước** khi tải XML. Nếu hàm đọc certificate này lại lấy từ `ds:KeyInfo` của metadata cùng URL, cấu hình sẽ làm mất ý nghĩa của out-of-band trust.

`metadataRepository` là kho metadata phía IdP. Ứng dụng còn cần ghép nó vào quy trình cung cấp `RelyingPartyRegistration`, đặt SP Entity ID, ACS, credentials SP và security filter chain SAML. Tạo metadata repository một mình **không tự động hoàn tất tích hợp đăng nhập**.

### 8.3. Mẫu Spring Boot application.yml mô tả location

Ví dụ cấu hình một registration SAML:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:prod:sp"
            assertingparty:
              metadata-uri: "https://idp.example.test/saml/metadata"
```

YAML chỉ minh họa **metadata source và SP entityId**. Nó **không chứng minh** metadata signature verification đã được bật bằng trust anchor độc lập. Để đáp ứng chính sách của bài, cần triển khai repository/metadata resolver có xác minh chữ ký theo phiên bản Spring Security đang dùng hoặc nhập bản metadata đã được kiểm tra bằng pipeline có kiểm soát.

Khi thiết lập custom repository, phải bảo đảm ứng dụng sử dụng **đúng repository đã xác minh**, không để một đường tải metadata khác lặng lẽ bỏ qua kiểm tra.

### 8.4. Nếu dùng phiên bản không hỗ trợ API trên

Khi dự án dùng Spring Security/Spring Boot khác phiên bản tài liệu:

1. Đọc Javadoc và cấu trúc provider/metadata resolver của **phiên bản thực tế**.
2. Cấu hình OpenSAML MetadataResolver với **SignatureValidationFilter** và `SignatureTrustEngine` có trust credentials được cung cấp độc lập, hoặc kiểm tra signed metadata trước bằng một pipeline đã kiểm soát.
3. Chỉ cung cấp XML/object đã qua xác minh cho builder/repository của Spring Security.
4. Nếu dùng metadata cục bộ, phải có quy trình quản trị **nguồn và refresh nội dung cục bộ**; việc nằm trên classpath không tự chứng minh XML đã ký hợp lệ.
5. Bảo đảm tất cả lần cập nhật/refresh vẫn đi qua validation như lần import đầu.
6. Không kế thừa cấu hình từ **Spring Security SAML Extension đời cũ** (ví dụ `ExtendedMetadataDelegate`) mà chưa kiểm tra sự khác biệt với Spring Security SAML 2.0 Service Provider hiện đại.

**Không tự viết parser SAML/XMLDSig mới** chỉ để có một dòng “signature valid”. Thư viện SAML được bảo trì xử lý nhiều chi tiết giao thức như ID/reference, signing profile, canonicalization và trust engine mà một ví dụ ngắn rất dễ bỏ sót.

## 9. Java 17 độc lập: chữ ký đúng, bị sửa và người ký không tin cậy

Ví dụ dưới đây dùng **XML Digital Signature API có sẵn trong JDK 17** để minh họa ba kết quả:

- Metadata được ký bằng **private key của người ký đã được tin**, và bên xác minh có **public key đã cấp trước** ⇒ PASS.
- Metadata sau khi ký bị sửa `entityID` ⇒ FAIL.
- Một người khác tự ký metadata bằng private key riêng nhưng SP vẫn xác minh bằng public key đã tin ⇒ FAIL.

Để thể hiện đúng ý tưởng SAML metadata profile, chữ ký dùng **enveloped transform** và **Reference `#_entity001` trỏ vào thuộc tính `ID`** của phần tử metadata. Code đặt `ds:Signature` trước role descriptor.

**Giới hạn quan trọng:** tài liệu XML trong chương trình chỉ đủ minh họa XMLDSig và vị trí ký, **chưa phải IdP metadata hoàn chỉnh theo SAML schema** (không có SingleSignOnService, certificate/role đầy đủ, validUntil). Nó cũng **không** cung cấp validation schema, chính sách trusted entity, duplicate-ID/wrapping trên XML tùy ý hoặc SAML Response authentication. **Không dùng `verify` từ ví dụ làm bộ nhập metadata production.**

Tệp `MetadataSignatureDemo.java`:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.Transform;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.crypto.dsig.spec.TransformParameterSpec;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

public class MetadataSignatureDemo {
    private static final String MD_NS =
        "urn:oasis:names:tc:SAML:2.0:metadata";
    private static final XMLSignatureFactory XML_SIG =
        XMLSignatureFactory.getInstance("DOM");

    static Document newMetadata() throws Exception {
        DocumentBuilderFactory builder =
            DocumentBuilderFactory.newInstance();
        builder.setNamespaceAware(true);
        builder.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        builder.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true);
        builder.setXIncludeAware(false);
        builder.setExpandEntityReferences(false);

        Document doc = builder.newDocumentBuilder().newDocument();
        Element entity = doc.createElementNS(
            MD_NS, "md:EntityDescriptor");
        entity.setAttribute("ID", "_entity001");
        entity.setIdAttribute("ID", true);
        entity.setAttribute(
            "entityID", "https://idp.example.test/saml/issuer");
        doc.appendChild(entity);

        Element role = doc.createElementNS(
            MD_NS, "md:IDPSSODescriptor");
        role.setAttribute("protocolSupportEnumeration",
            "urn:oasis:names:tc:SAML:2.0:protocol");
        entity.appendChild(role);
        return doc;
    }

    static void sign(Document doc, PrivateKey key) throws Exception {
        Reference reference = XML_SIG.newReference(
            "#_entity001",
            XML_SIG.newDigestMethod(DigestMethod.SHA256, null),
            List.of(
                XML_SIG.newTransform(
                    Transform.ENVELOPED, (TransformParameterSpec) null),
                XML_SIG.newTransform(
                    CanonicalizationMethod.EXCLUSIVE,
                    (TransformParameterSpec) null)
            ), null, null);

        SignedInfo signedInfo = XML_SIG.newSignedInfo(
            XML_SIG.newCanonicalizationMethod(
                CanonicalizationMethod.EXCLUSIVE,
                (C14NMethodParameterSpec) null),
            XML_SIG.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
            List.of(reference));

        Element entity = doc.getDocumentElement();
        DOMSignContext context = new DOMSignContext(
            key, entity, entity.getFirstChild());
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(entity, null, "ID");
        XML_SIG.newXMLSignature(signedInfo, null).sign(context);
    }

    static boolean verify(Document doc, PublicKey trustedKey)
            throws Exception {
        Element entity = doc.getDocumentElement();
        Node first = entity.getFirstChild();
        if (!(first instanceof Element signatureNode)
                || !XMLSignature.XMLNS.equals(
                    signatureNode.getNamespaceURI())
                || !"Signature".equals(
                    signatureNode.getLocalName())) {
            return false;
        }

        DOMValidateContext context =
            new DOMValidateContext(trustedKey, signatureNode);
        context.setIdAttributeNS(entity, null, "ID");
        context.setProperty(
            "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);

        XMLSignature signature =
            XML_SIG.unmarshalXMLSignature(context);
        if (signature.getSignedInfo().getReferences().size() != 1) {
            return false;
        }
        Reference reference = (Reference)
            signature.getSignedInfo().getReferences().get(0);
        if (!("#" + entity.getAttribute("ID"))
                .equals(reference.getURI())) {
            return false;
        }
        return signature.validate(context);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair approvedSigner = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        Document original = newMetadata();
        sign(original, approvedSigner.getPrivate());
        System.out.println("trusted=" +
            verify(original, approvedSigner.getPublic()));

        original.getDocumentElement().setAttribute(
            "entityID", "https://evil.example.test/idp");
        System.out.println("tampered=" +
            verify(original, approvedSigner.getPublic()));

        Document forged = newMetadata();
        sign(forged, attacker.getPrivate());
        System.out.println("otherSigner=" +
            verify(forged, approvedSigner.getPublic()));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac MetadataSignatureDemo.java
java MetadataSignatureDemo
```

Stdout chính xác:

```text
trusted=true
tampered=false
otherSigner=false
```

**Giải thích:**

- `KeyPairGenerator` tạo hai cặp RSA 2048-bit cho mục đích học. Trong production, SP **không tự tạo khóa tin cậy mỗi lần chạy**: public key/certificate của metadata signer phải được provision và xác nhận từ **nguồn ngoài metadata**.
- `sign` dùng private key của signer để tạo `ds:Signature`; `verify` dùng **một public key được truyền vào** từ phía verifier. Trong demo public key này đóng vai trust anchor giả định.
- `Reference="#_entity001"` và registration ID thuộc tính `ID` cho thấy XMLDSig ký đúng phần tử. `DigestMethod.SHA256` và `SignatureMethod.RSA_SHA256` tránh dùng SHA-1 cũ trong ví dụ.
- Khi sửa `entityID` trong XML đã ký, digest không khớp ⇒ `tampered=false`.
- Khi một đối tượng khác tự tạo cặp khóa để ký, chữ ký có thể hợp lệ **với khóa của họ**, nhưng không xác minh được bằng public key mà SP đã tin ⇒ `otherSigner=false`.
- Demo cố ý **không** thêm `KeyInfo`: điều này giúp minh họa rằng khóa xác minh do bên nhận chọn trước, không phải do tài liệu tự cung cấp.
- `secureValidation` là một cơ chế hạn chế XMLDSig, nhưng **không thay thế** schema SAML, trust policy, certificate lifecycle, giới hạn kích thước, kiểm tra wrapping/duplicate ID và entity allowlist khi xử lý XML từ Internet.

Mô hình thực tế dùng X.509 certificate đã provision và hệ thống OpenSAML trust engine; JDK demo chỉ minh họa logic chữ ký ở lớp thấp.

## 10. Xác minh một tập metadata nhiều IdP

Có trường hợp SP tải **aggregated metadata** từ một federation operator thay vì nhận từng file riêng của từng IdP.

```text
Federation operator
    |
    | ký md:EntitiesDescriptor bằng metadata signing key OP
    v
  md:EntitiesDescriptor
      md:EntityDescriptor IdP A (KeyDescriptor A)
      md:EntityDescriptor IdP B (KeyDescriptor B)
      md:EntityDescriptor IdP C (KeyDescriptor C)
    |
    v
SP xác minh chữ ký root bằng OP key đã cấp out-of-band
    |
    v
SP chỉ cho phép những entity ID/role đã được phê duyệt
```

Điều này không có nghĩa SP phải pin riêng metadata signing certificate cho từng IdP bên trong tập nếu nó đã có **quan hệ trust rõ ràng với aggregator** cho phạm vi ấy. Nhưng SP phải biết operator được phép công bố những entity nào, và phải giới hạn trust tương ứng. Một chữ ký operator hợp lệ **không tự cấp quyền** cho mọi entity bất kỳ được thêm vào metadata nếu ứng dụng chỉ muốn liên kết với một danh sách IdP cụ thể.

Khi metadata có chữ ký ở nhiều cấp:

- Xác minh chữ ký ở **cấp thực sự bảo vệ entity được dùng**.
- Không nhầm một `EntityDescriptor` con unsigned với toàn bộ file unsigned khi nó được nằm trong `EntitiesDescriptor` gốc đã được ký và tin cậy.
- Không dùng entity **ngoài** subtree/đối tượng đã ký.
- Không tự lấy cert của IdP C rồi cho rằng C có quyền ký lại metadata tổng hợp dành cho A/B.

**Quy tắc:** xác minh *người ký*, *phạm vi ký*, *entity được phép* và *thời gian hiệu lực*, đủ cả bốn.

## 11. Phân biệt hai hoạt động certificate rotation

### 11.1. Xoay khóa ký assertion của IdP

IdP cần thay certificate dùng để ký SAML Response/Assertion. IdP cập nhật `KeyDescriptor use="signing"` trong metadata. Nếu metadata được **ký bằng metadata signer đã tin cậy**, SP có thể xác minh metadata mới rồi cập nhật tập certificate ký assertion theo chính sách.

Luồng:

```text
Metadata signer cũ đã tin
   |
   v
Metadata mới được ký hợp lệ
   |
   +-- assertion signing cert hiện tại
   +-- assertion signing cert kế tiếp
   |
   v
SP xác minh metadata -> chấp nhận overlap cert IdP theo chính sách
```

Certificate ký assertion mới **không tự động trở thành metadata signing trust anchor** nếu chính sách không cho phép. Nó chỉ trở thành credential được tin để xác minh assertion sau quá trình nhập metadata hợp lệ.

### 11.2. Xoay khóa ký metadata

Đây là thay đổi ở **trust anchor bảo vệ metadata**. Nếu publisher đổi metadata signer từ khóa A sang B, chỉ công bố khóa B trong metadata mới đã được ký bằng B sẽ gây ra bài toán khởi tạo niềm tin vòng tròn.

Quy trình đúng:

1. Đối tác thông báo thay đổi qua quy trình quản trị đã xác thực.
2. SP nhận certificate/public key B và fingerprint SHA-256 từ **kênh độc lập**, kiểm tra owner và hiệu lực.
3. SP bổ sung B vào trust anchor theo kế hoạch chuyển tiếp; có thể đồng thời tin A và B **trong khoảng giao nhau được duyệt**.
4. Publisher phát metadata ký bằng B; SP xác minh được bằng B và kiểm tra entity/validUntil bình thường.
5. Theo dõi việc refresh của mọi SP và đối tác; sau thời điểm chuyển đổi, xóa A khỏi trust store và ghi audit.
6. Không bật chế độ “accept any signer” khi gặp lỗi rotation.

Nếu metadata ký bằng A công bố một certificate B trong `KeyDescriptor`, điều đó **không mặc nhiên** cấp cho B quyền ký metadata trong tương lai: `KeyDescriptor` thường công bố các khóa liên quan giao thức SAML của entity. Quyền ký metadata B phải được quy định rõ trong chính sách trust và quy trình cấp phát.

### 11.3. Kịch bản mất khóa hoặc nghi bị lộ

Nếu private key của metadata signer bị đánh cắp, việc tài liệu mới còn có “signature valid” với khóa cũ **không bảo đảm dữ liệu đáng tin**. SP phải:

- Thu hồi trust anchor theo hướng dẫn ứng cứu và cập nhật các bên liên quan.
- Kiểm tra/audit metadata đã nhập trong khoảng nghi ngờ, xác định endpoint hoặc certificate bị thay thế.
- Phục hồi từ bản đã xác minh/hợp đồng đúng và provision khóa mới qua kênh độc lập.
- Kiểm tra session/token, IdP assertion key và các hệ thống downstream nếu trust đã bị thao túng.

Không coi chữ ký đúng là bằng chứng tuyệt đối sau khi khóa signer bị lộ.

## 12. Thời hạn metadata và refresh an toàn

SAML metadata hỗ trợ:

- **`validUntil`**: mốc metadata hết hạn; có thể xuất hiện ở `EntityDescriptor` hoặc `EntitiesDescriptor`.
- **`cacheDuration`**: gợi ý giới hạn thời gian cache; không đồng nghĩa “ký còn hợp lệ mãi”.
- **Chữ ký**: bảo vệ nội dung metadata, nhưng một file cũ đã ký đúng vẫn có thể **quá hạn hoặc bị thay thế**.

Ví dụ: một file metadata có `validUntil=2026-11-01T00:00:00Z` và chữ ký hợp lệ. Nếu kiểm tra vào ngày 2026-11-07 thì **không được coi file đó là metadata hiện hành hợp lệ** chỉ vì `SignatureValue` vẫn đúng.

Trong production, mỗi lần refresh nên ghi:

```text
metadata_source
expected_entity_id
signer_fingerprint_sha256
signature_validation_result
document_valid_until
last_successful_refresh
next_refresh_due
last_refresh_error
active_metadata_version
```

Bản lưu/cached phải là **bản đã xác minh**. Khi tải mới thất bại:

- Không kích hoạt bất kỳ dữ liệu chưa xác minh nào.
- Có thể giữ bản trước **nếu còn hiệu lực và đúng policy**.
- Cảnh báo trước `validUntil`, đủ sớm để đối tác khắc phục.
- Không mặc định “last known good” đồng nghĩa được dùng mãi sau hết hạn.
- Đặt giới hạn thời gian, retry/backoff và không để lỗi tải metadata gây ra vòng lặp DOS.

### 12.1. HTTPS và redirect trong refresh

Ngay cả với metadata có chữ ký, vẫn nên dùng HTTPS, hostname đã đăng ký, timeout, giới hạn redirect và nội dung tải. Không cho metadata loader tự đi theo URL tùy ý từ query request hay XML có external reference, tránh SSRF và dữ liệu quá tải. Dùng XML parser chặn external entities và schema fetch từ nguồn không tin.

## 13. Các tình huống tấn công và lỗi cấu hình

| Tình huống | Lỗi/khả năng xảy ra | Kết quả đúng |
| --- | --- | --- |
| Metadata bị sửa SSO URL sau khi ký | Digest hoặc signature không khớp | Từ chối metadata mới |
| Metadata được kẻ lạ tự ký | Signature valid với khóa lạ nhưng signer không thuộc trust store | Từ chối |
| `KeyInfo` tự chứa certificate lạ | Ứng dụng nhận KeyInfo làm trust anchor | Từ chối; luôn dùng trust anchor độc lập |
| Metadata không có signature | Chính sách yêu cầu signed metadata | Từ chối dù tải qua HTTPS |
| Metadata có signature nhưng sai signer | Khóa khác danh sách được phép | Từ chối |
| Metadata có chữ ký hợp lệ nhưng `entityID` sai | Cấu hình IdP khác đối tác được duyệt | Từ chối hoặc chỉ xử lý entity được phép |
| Ký `EntityDescriptor` A, dùng endpoint trong B unsigned | Phạm vi signed content bị nhầm | Từ chối B, không dùng nội dung ngoài vùng signed |
| Trùng ID hoặc wrapping | Bộ xử lý có thể lấy XML khác nội dung ký | Từ chối cấu trúc không hợp lệ; kiểm tra reference và element thực dùng |
| Metadata hết `validUntil` | Chữ ký vẫn đúng trên file cũ | Từ chối theo chính sách hết hạn |
| Xoay assertion certificate | Metadata mới signed và tin cậy | Có thể cập nhật assertion verification keys theo policy |
| Xoay metadata signing key | Khóa mới chưa được out-of-band approval | Không tự tin key mới; yêu cầu onboarding/rotation |
| Metadata signer bị thu hồi | Khóa cũ có thể tạo chữ ký hợp lệ mật mã | Thu hồi trust và ứng cứu |
| TLS certificate hợp lệ, XML tự ký | TLS chỉ xác thực kênh, không xác lập metadata signing policy | Từ chối nếu chữ ký không đến từ metadata signer đáng tin |
| Cấu hình `verificationCredentials` bị bỏ trống | Repository documented không validate metadata signature | Test/deployment policy phải phát hiện và từ chối |
| Metadata aggregation | Root signed, IDP entity con nằm trong signed subtree | Kiểm tra root signer, phạm vi, entity allowlist |
| Malicious external Reference | XMLEnc/XMLDSig đi tải dữ liệu ngoài | Chặn external URI/transform theo secure processing |

**Cần phân biệt hai kết quả QA:** “XML Signature cryptographically valid” và “metadata trusted and safe to activate” là hai điều kiện khác nhau. Cả hai phải đạt.

## 14. Ma trận kiểm thử một bộ nhập metadata

Có thể xây integration tests với IdP giả lập và metadata thử nghiệm có chữ ký được tạo bởi cặp khóa test riêng:

| Test case | Cấu hình/đầu vào | Kỳ vọng |
| --- | --- | --- |
| Signer chuẩn | Metadata ký bởi key A đã pin, entity và thời hạn hợp lệ | PASS, cho phép nhập |
| Payload sửa | Đổi SSO Location sau ký | FAIL |
| Signer khác | Metadata ký bởi key B không thuộc trust | FAIL |
| Self-signed KeyInfo | Kẻ tấn công nhúng cert B trong KeyInfo rồi ký bằng B | FAIL dù tự kiểm bằng B là valid |
| Thiếu chữ ký | XML IdP hợp lệ về mặt schema nhưng không signed | FAIL khi policy yêu cầu signed |
| Sai entityID | Signed metadata hợp lệ nhưng entity không thuộc allowlist | FAIL |
| Sai scope ký | Signature bảo vệ A nhưng importer chọn dữ liệu B | FAIL |
| Duplicate IDs | Hai element cùng ID tham chiếu | FAIL |
| Signature wrapping | Element chưa ký được dùng làm cấu hình | FAIL |
| XML chứa DTD/XXE | Parser bị yêu cầu tải external entity | FAIL, không có outbound fetch |
| Reference URL ngoài | `ds:Reference` tới HTTPS khác | FAIL theo local-only reference policy |
| Metadata đã hết hạn | Chữ ký đúng nhưng `validUntil` đã qua | FAIL |
| Metadata sắp hết hạn | Chữ ký đúng, còn hạn rất ngắn | Nhập hoặc cảnh báo theo freshness policy |
| Refresh lỗi tạm thời | Nguồn không truy cập, bản cũ còn hiệu lực | Chỉ dùng bản cũ đã xác minh nếu policy cho phép, phát cảnh báo |
| Metadata B được ký qua key rotation approved | A/B cùng được pin trong thời gian chuyển tiếp | PASS với B theo kế hoạch |
| B ký trước khi approval | B chưa được cấp out-of-band | FAIL |
| Key A đã revocation | Metadata vẫn ký được bằng A | FAIL sau khi A bị loại trust |
| Rollover assertion cert | Metadata mới ký bởi signer tin cậy, KeyDescriptor chứa key mới | Nhập key assertion mới theo policy |
| Aggregate root signed | Entity mong muốn nằm trong subtree root signed | PASS khi scope/allowlist/expiry đúng |
| Aggregate root signer lạ | XML nhiều IdP nhưng signer chưa trusted | FAIL |
| Hai IdP | Key metadata signer A và B khác nhau | Không chấp nhận B bằng trust policy A |

Điều quan trọng là kiểm thử **từ lúc tải metadata đến khi kích hoạt config thực tế**. Một unit test chỉ gọi API `signature.validate()` trên XML đã chọn sẵn có thể bỏ qua lỗi “chọn nhầm element đã ký”.

## 15. Checklist vận hành khi cấu hình SAML2 metadata

- [ ] Biết ai là metadata publisher/signer của từng IdP hoặc federation operator.
- [ ] Có certificate/public key metadata signer và fingerprint SHA-256 được đối chiếu qua kênh độc lập.
- [ ] Trust anchor nằm trong cấu hình được quản trị; không học khóa tự động từ `ds:KeyInfo` hoặc `KeyDescriptor` của XML chưa kiểm tra.
- [ ] Chính sách dùng pinned key hay PKIX được viết rõ; signer được giới hạn theo đối tác/môi trường.
- [ ] Bộ nhập **bắt buộc validate metadata signature** khi policy yêu cầu signed metadata.
- [ ] Không coi `RelyingPartyRegistrations.fromMetadataLocation` hoặc `metadata-uri` đơn lẻ là bằng chứng metadata signature đã được kiểm tra.
- [ ] Đã xác minh code Spring Security dùng đúng metadata repository/resolver có trust credentials.
- [ ] XML được parse an toàn, không tải DTD/external URI tùy ý và dùng thư viện XMLDSig/OpenSAML hỗ trợ profile SAML.
- [ ] Chữ ký bảo vệ đúng `EntityDescriptor` hoặc `EntitiesDescriptor` và entity cần dùng nằm trong phạm vi signed.
- [ ] Đã kiểm tra entityID, role IdP, key usage, endpoints, `validUntil`, `cacheDuration` và policy thay đổi cấu hình.
- [ ] Certificate ký metadata và certificate ký assertion được quản lý theo **mục đích riêng**.
- [ ] Có rotation keys, overlap có giới hạn, thu hồi khóa cũ và kế hoạch ứng cứu khi private key bị lộ.
- [ ] Refresh không kích hoạt metadata thiếu/invalid signature; cache last-known-good có thời hạn và alert.
- [ ] Test metadata bị sửa, key tự ký, wrapping, expiry và cross-IdP confusion đã chạy.
- [ ] Hệ thống nghiệp vụ vẫn kiểm tra ánh xạ user và quyền trên tài nguyên sau khi SAML login hợp lệ.

## 16. Câu hỏi tự kiểm tra

**1. Metadata có `ds:Signature` và `ds:KeyInfo` chứa certificate. Chỉ cần dùng certificate đó xác minh để kết luận đáng tin không?**

Không. Chữ ký có thể đúng với certificate do attacker tự cung cấp. Trust anchor phải được kiểm chứng **độc lập**, có binding với nhà phát hành được phép.

**2. Khóa trong `md:KeyDescriptor use="signing"` dùng để làm gì?**

Thường để công bố khóa verify chữ ký **SAML Response/Assertion** của IdP. Nó không mặc nhiên là khóa cấp phép ký **metadata**. Nó chỉ được tin sau khi metadata được xác minh qua trust policy thích hợp.

**3. Metadata được tải qua HTTPS đã xác thực, có thể bỏ signature validation không?**

Phụ thuộc chính sách và mô hình trust. SAML metadata spec có mô hình phân phối đáng tin không nhất thiết signed. **Nhưng bài này yêu cầu signed metadata với out-of-band key**, nên HTTPS không thay thế kiểm tra chữ ký được yêu cầu.

**4. Một XML có signature hợp lệ nhưng `entityID` không thuộc IdP được đăng ký, có nhập không?**

Không. Ngoài chữ ký, cần kiểm tra signer có quyền công bố **entity** cụ thể và entity có nằm trong danh sách được phép.

**5. Vì sao cần kiểm tra `ds:Reference URI="#ID"` và vị trí phần tử?**

Vì signature có thể bảo vệ một element **khác** element mà chương trình sử dụng, dẫn đến XML Signature Wrapping. Kiểm tra đúng signed subtree và dữ liệu trích xuất.

**6. Vì sao khóa metadata signer phải xoay khác khóa ký assertion?**

Hai khóa bảo vệ **hai đối tượng và hai thời điểm**. Metadata signer key thay đổi phải được out-of-band approval; assertion key có thể đổi qua metadata **đã ký đáng tin**.

**7. Spring Security tự validate chữ ký metadata khi chỉ khai `metadata-uri`?**

Không được suy luận vậy. Tài liệu `OpenSaml5AssertingPartyMetadataRepository` nêu rõ nếu không cung cấp verification credentials, component **không** thực hiện signature validation. Cần cấu hình cơ chế tin cậy theo đúng phiên bản dùng.

**8. Chữ ký metadata hợp lệ nhưng `validUntil` đã quá hạn có chấp nhận không?**

Không theo chính sách freshness chuẩn: signature chứng minh nội dung chưa bị sửa, không chứng minh tài liệu vẫn còn hiệu lực tại thời điểm hiện tại.

**9. Nếu IdP đổi signing key cho SAML Response, SP có thể tự nhận key mới từ metadata không?**

Có thể khi metadata **mới** được kiểm tra bằng metadata signer trust anchor và policy cho phép key rollover. Không dùng KeyDescriptor mới từ metadata chưa xác thực.

**10. Test quan trọng nhất để phát hiện sai trust bootstrap là gì?**

Tạo metadata ký bằng **khóa attacker** có nhúng certificate attacker trong KeyInfo, đảm bảo hệ thống **từ chối** dù chữ ký tự kiểm bằng khóa đó có thể hợp lệ. Điều này chứng minh verifier sử dụng trust key đã được provision độc lập.

## 17. Tài liệu kỹ thuật để đối chiếu

- Spring Security, **SAML 2.0 Metadata – Verifying Metadata Signatures**; tài liệu hóa `OpenSaml5AssertingPartyMetadataRepository` và `verificationCredentials`: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **SAML 2.0 Login Overview**; cấu trúc `RelyingPartyRegistration` và các credential phía SP/IdP: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS, **Metadata for SAML V2.0**, đặc biệt mục 2, 3 (Signature Processing), 4 (Publication/Resolution): https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- W3C, **XML Signature Best Practices**, nhất là thiết lập trust key, reference scope, external URI và wrapping: https://www.w3.org/TR/xmldsig-bestpractices/
- OWASP, **SAML Security Cheat Sheet**, signature trust, static trusted keys và XML Signature Wrapping: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet
- OpenSAML, **SignatureValidationFilter** và trust engine cho metadata: https://javadoc.io/static/org.opensaml/opensaml-saml-impl/4.0.1/org/opensaml/saml/metadata/resolver/filter/impl/SignatureValidationFilter.html

**Ghi nhớ:** chỉ có `ds:Signature` và `SignatureValue` hợp lệ **chưa đủ**. Bên nhận cần **metadata signer trust anchor được cấp qua kênh độc lập**, xác minh đúng **phần metadata được ký**, đối chiếu signer/entity/time/policy rồi **mới** cho phép sử dụng endpoint và khóa IdP bên trong metadata.