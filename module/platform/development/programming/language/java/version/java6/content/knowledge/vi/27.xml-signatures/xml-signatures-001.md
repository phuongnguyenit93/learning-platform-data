# XML Digital Signature API và tính toàn vẹn dữ liệu XML

## 1. Chữ ký số XML giải quyết bài toán gì?

Giả sử một dịch vụ nhận tài liệu XML về giao dịch thanh toán. Tài liệu chứa `payment` với `Id="pay-42"`, số tiền `100` và một chữ ký số. Dịch vụ nhận cần biết **những bytes/dữ liệu logic được bảo vệ đã bị thay đổi kể từ khi chủ thể giữ khóa riêng ký hay chưa**, đồng thời kiểm tra chữ ký với **khóa công khai đáng tin cậy theo chính sách của ứng dụng**.

Java SE cung cấp **XML Digital Signature API** (thường gọi là *JSR 105*) qua module `java.xml.crypto` và các package:

- `javax.xml.crypto.dsig`: tạo và xác minh chữ ký XML, với `XMLSignatureFactory`, `XMLSignature`, `SignedInfo`, `Reference`, `DigestMethod`, `SignatureMethod`, `CanonicalizationMethod`.
- `javax.xml.crypto.dsig.dom`: tích hợp DOM bằng `DOMSignContext` và `DOMValidateContext`.
- `javax.xml.crypto.dsig.spec`: các parameter specs cho transform/canonicalization.
- `javax.xml.crypto.dsig.keyinfo`: biểu diễn `KeyInfo`, `KeyValue`, `X509Data`, `KeyName`; **không mặc nhiên xác lập độ tin cậy của một khóa**.
- `javax.xml.crypto`: các abstraction như `URIDereferencer`, `URIReferenceException`, `KeySelector`.
- `org.w3c.dom` và `javax.xml.parsers` (module `java.xml`): biểu diễn/đọc XML theo DOM.

Các API này **vẫn hiện hành**, có trên Java 17+ và các phiên bản Java SE mới. Không cần những thư viện Java XMLDSig cũ đã bị thay thế để học phần lõi; ứng dụng thực tế có thể sử dụng provider/library khác nếu đáp ứng chính sách bảo mật và chuẩn tương thích.

Mục tiêu của chữ ký số XML:

1. **Integrity:** thay đổi dữ liệu nằm trong phạm vi được ký làm `Reference` digest verification thất bại.
2. **Authentication đối với một khóa:** `SignatureValue` chỉ hợp lệ với public key tương ứng. **Danh tính bên ngoài** chỉ được tin khi ứng dụng đã xác lập trust anchor và policy kiểm chứng khóa/chứng thư.
3. **Ràng buộc phạm vi ký:** các `Reference URI` xác định phần nào được bảo vệ. Không ký toàn document thì những phần ngoài references có thể thay đổi mà chữ ký **vẫn hợp lệ**.
4. **Không cung cấp confidentiality:** XML có chữ ký vẫn là dữ liệu **đọc được**, không được mã hóa.
5. **Không tự ngăn replay:** kẻ nhận lại một tài liệu đã ký đúng có thể gửi lại nó. Nếu cần chống replay, hãy ký cả request ID, nonce/timestamp, phạm vi quyền và kiểm tra deduplication/expiration ở lớp ứng dụng.

> Cốt lõi bảo mật: **chữ ký có giá trị về mật mã chưa chứng minh rằng ứng dụng đang dùng đúng node XML đã được ký**, hoặc rằng khóa ký thuộc về một đối tác đáng tin. Phải kiểm tra cả cryptography, key trust, reference target và business semantics.

## 2. Cấu trúc XML Signature theo W3C

Một chữ ký XML dùng namespace `http://www.w3.org/2000/09/xmldsig#`, thường có prefix `ds` nhưng prefix **không phải danh tính**: namespace URI và local name mới quyết định phần tử.

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="#pay-42">
      <ds:Transforms>
        <ds:Transform Algorithm="..."/>
      </ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
</ds:Signature>
~~~

Đây là **sơ đồ cấu trúc**, không phải XML Signature hợp lệ để xác minh: các Algorithm URIs, digest/signature values và key material được thay bằng dấu ba chấm.

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `Signature` | Container toàn bộ chữ ký XML |
| `SignedInfo` | Dữ liệu được ký về mặt mật mã: canonicalization method, signature algorithm, các references/digests |
| `CanonicalizationMethod` | Chuẩn hóa XML của `SignedInfo` trước khi tạo/xác minh `SignatureValue` |
| `SignatureMethod` | Thuật toán chữ ký bất đối xứng hoặc MAC theo profile |
| `Reference URI` | Xác định tài nguyên hoặc XML node-set cần bảo vệ |
| `Transforms` | Các biến đổi có thứ tự trước khi tính digest (ví dụ canonicalization) |
| `DigestMethod` | Thuật toán hash của nội dung reference |
| `DigestValue` | Hash đã tính của nội dung reference sau transforms |
| `SignatureValue` | Chữ ký mật mã trên dạng chuẩn hóa của `SignedInfo` |
| `KeyInfo` | *Tùy chọn*: gợi ý khóa/chứng thư/KeyName; **không phải trusted source mặc định** |
| `Object` | *Tùy chọn*: dữ liệu gói bên trong signature (enveloping case) |

### 2.1. Hai phép xác minh khác nhau

Khi nhận một XML Signature, quá trình **core validation** cần ít nhất hai lớp:

~~~text
                         XML Signature
                                |
                +---------------+---------------+
                |                               |
                v                               v
       SignedInfo / SignatureValue        Reference(s) / DigestValue
                |                               |
      Canonicalize SignedInfo           Resolve reference URI
                |                               |
      Verify cryptographic signature     Apply allowed transforms
       with trusted public key                   |
                                                v
                                         Digest referenced data
                                                |
                                         Compare DigestValue
                |                               |
                +---------------+---------------+
                                |
                                v
                        Core validation true
~~~

Một trường hợp dễ hiểu: **đổi số tiền trong phần XML đã ký**, nhưng không thay `SignedInfo` và `SignatureValue`, có thể cho:

~~~text
SignatureValue validation: true
Reference digest validation: false
Core XMLSignature.validate: false
~~~

Lý do: chữ ký trên `SignedInfo` **chưa bị thay đổi**; nhưng dữ liệu do `Reference` trỏ tới đã khác, nên digest mismatch. Code chỉ gọi `getSignatureValue().validate(context)` là **không đủ** để xác nhận tính toàn vẹn dữ liệu XML!

Một trường hợp khác: giữ nguyên dữ liệu được ký nhưng thay public key kiểm tra bằng khóa không tương ứng. Khi đó Reference digest vẫn có thể đúng, trong khi SignatureValue validation và core validation thất bại.

### 2.2. SHA-256 là hash, RSA-SHA256 là signature algorithm

Hai thành phần có mục đích khác nhau:

~~~java
DigestMethod.SHA256
SignatureMethod.RSA_SHA256
~~~

- `DigestMethod.SHA256` tính hash SHA-256 của dữ liệu **mỗi Reference** sau transforms.
- `SignatureMethod.RSA_SHA256` xác minh/tạo **chữ ký RSA trên SignedInfo** với SHA-256 theo thuật toán quy định.
- `CanonicalizationMethod.EXCLUSIVE` là canonicalization algorithm, **không phải thuật toán băm** hoặc chữ ký.

Không nhầm SHA-256 với khả năng **xác thực chủ thể**. Bất kỳ ai đều tính được một digest SHA-256 mới; chỉ chủ sở hữu khóa riêng hợp lệ mới tạo chữ ký RSA tương ứng trên SignedInfo. Trong ứng dụng production, khóa ký phải được quản lý an toàn, và public key kiểm tra phải đến từ trust policy.

## 3. Ba bố trí chữ ký: enveloped, enveloping, detached

Thuật ngữ của W3C phân biệt vị trí dữ liệu được ký so với `Signature`:

| Bố trí | Quan hệ giữa chữ ký và dữ liệu | Hệ quả |
| --- | --- | --- |
| **Enveloped** | `Signature` nằm **bên trong** phần XML được ký | Thường cần `Transform.ENVELOPED` để loại chính signature khỏi digest |
| **Enveloping** | Dữ liệu được gói trong `ds:Object` **bên trong** `Signature` | Reference thường trỏ tới `Object` theo ID |
| **Detached** | `Signature` nằm ngoài phần XML được ký, có thể ở tài liệu khác hoặc là sibling | Không cần enveloped transform nếu signature không nằm trong referenced subtree |

Ví dụ enveloped:

~~~xml
<order xmlns="urn:example:orders" Id="ord-9">
  <amount>100</amount>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    ...
  </ds:Signature>
</order>
~~~

Đây là snippet cấu trúc. Nếu Reference trỏ tới root `order` mà signature nằm trong root, cần loại signature khỏi material được hash để không có vòng phụ thuộc chữ ký vào chính mình. Với Java DSig, đó là:

~~~java
fac.newTransform(Transform.ENVELOPED,
        (TransformParameterSpec) null)
~~~

Còn bài demo chính sẽ có:

~~~xml
<p:envelope xmlns:p="urn:demo:payment">
  <p:payment Id="pay-42">
    <p:amount>100</p:amount>
  </p:payment>
  <p:note>original</p:note>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    ...
  </ds:Signature>
</p:envelope>
~~~

Đây là **sơ đồ**, không phải chữ ký valid vì rút gọn Signature. `Signature` nằm cạnh `payment`, không nằm trong `payment`. Reference `#pay-42` chỉ ký `payment`: đây là **same-document detached signature** đối với phần dữ liệu được ký. Vì thế demo dùng exclusive C14N transform mà **không cần enveloped-signature transform**.

**Không coi `URI=""` và `URI="#pay-42"` là tương đương.** Theo W3C, `URI=""` biểu diễn tham chiếu same-document tới document root theo processing model (có thể cần enveloped transform nếu chữ ký nằm trong tài liệu); `#pay-42` nhắm tới đối tượng có ID được resolve hợp lệ.

## 4. Lược đồ thao tác ký và xác minh trong Java

Đường ký:

~~~text
Private key (đáng tin ở phía signer)
        |
        v
XMLSignatureFactory.getInstance("DOM")
        |
        +--> Reference("#pay-42", SHA256, allowed transforms)
        |
        +--> SignedInfo(exclusive C14N, RSA_SHA256, reference)
        |
        +--> DOMSignContext(privateKey, insertionNode)
        |          |
        |          +--> setIdAttributeNS(payment, null, "Id")
        |
        +--> XMLSignature.sign(context)
                   |
                   v
             DOM chứa ds:Signature
~~~

Đường xác minh:

~~~text
XML bytes
   |
   v
Hardened namespace-aware DOM parser
   |
   v
Validate expected root/schema/path/ID uniqueness
   |
   v
Select exactly expected ds:Signature
   |
   v
DOMValidateContext(TRUSTED PUBLIC KEY, Signature element)
   |
   +--> secureValidation = true
   +--> register trusted Id
   +--> whitelist reference URI / dereferencer
   |
   v
Unmarshal XMLSignature
   |
   v
Validate allowed SignatureMethod/DigestMethod/Transforms/URI
   |
   v
XMLSignature.validate(context)
   |
   v
Only then consume the exact validated business node
~~~

**Thứ tự rất quan trọng**: Không chọn tùy ý node `//payment` và đưa thẳng vào business logic trước khi xác minh rằng nó chính là node **được Reference bảo vệ**. Một validation true trên một phần tử khác, còn ứng dụng dùng phần tử do attacker chèn, là lỗi **XML Signature Wrapping (XSW)**.

## 5. Tạo khóa ký an toàn: demo và production khác nhau

Để bài tập chạy độc lập, dùng Java Security API hiện hành:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(3072);
KeyPair pair = generator.generateKeyPair();
~~~

Đây là snippet tạo **cặp khóa dùng để minh họa**, không phải key management production. RSA 3072-bit với RSA-SHA256 là một lựa chọn hiện đại phù hợp cho ví dụ. Profile thực tế có thể dùng ECDSA-SHA256, RSA-PSS hoặc thuật toán được bộ tiêu chuẩn áp dụng cho hệ thống quy định; **khả năng hỗ trợ phụ thuộc JDK/provider và liên thông đối tác**.

Trong production:

- Không tạo khóa ký mới cho mỗi request: chữ ký sẽ khó được xác minh dài hạn nếu không lưu và quản lý định danh khóa.
- Giữ private key trong **KeyStore, KMS, HSM hoặc cơ chế quản lý bí mật được phê duyệt**, thay vì nhúng trong source.
- Phân quyền ký, rotation, audit và backup theo yêu cầu vận hành.
- Dùng khóa có kích thước/thuật toán được security policy cho phép. Không chọn MD5/SHA-1 hoặc các thuật toán chữ ký yếu chỉ vì ví dụ trên internet cũ.
- Phân biệt **khóa ký** với **khóa kiểm tra**: bên nhận cần một nguồn public key đáng tin (cấu hình, keystore, certificate trust) độc lập với nội dung chưa xác minh.

### 5.1. Không tự tin bất kỳ `KeyInfo` nào được gửi cùng XML

`KeyInfo` có thể chứa `KeyValue`, `X509Data`, `KeyName` hoặc retrieval hint. Kẻ tấn công cũng có thể tự tạo key pair, ký tài liệu tùy ý bằng private key của họ và gắn public key của họ trong `KeyInfo`. **Một chữ ký xác minh hợp lệ bằng chính key do attacker gửi không chứng minh tài liệu được ký bởi đối tác đáng tin.**

Nếu dùng X.509:

- Xây dựng/kiểm tra trust chain tới trust anchor đã cấu hình.
- Xác minh hiệu lực theo thời gian, key usage, algorithm policy, tên/định danh và ràng buộc đối tác.
- Đánh giá revocation theo chính sách hệ thống (CRL/OCSP khi phù hợp).
- Không tải chứng thư/key URL tùy ý từ XML qua mạng nếu không có policy kiểm soát.
- Gắn public key/certificate đã tin với tenant, merchant, role hoặc đối tác cụ thể.

Demo truyền **public key đã có sẵn ở phía ứng dụng** vào `DOMValidateContext`. Không có `KeyInfo` trong XML; nhờ vậy, ví dụ không tạo cảm giác sai rằng trust tự xuất hiện chỉ nhờ nội dung chữ ký.

## 6. Canonicalization: tại sao XML cần bước chuẩn hóa?

Hai XML serialized forms có thể biểu đạt nội dung tương đương dưới một số khía cạnh nhưng có khác biệt về cách viết: thứ tự attributes, prefix, escape syntax, newline handling hoặc namespace declaration. Chữ ký mật mã hoạt động trên **octets**, nên XMLDSig dùng **Canonical XML (C14N)** để biến node-set XML thành chuỗi bytes xác định theo một thuật toán cụ thể.

Các thuật toán cần phân biệt:

- **Canonicalization của `SignedInfo`**: định nghĩa cách tạo bytes để ký/xác minh `SignatureValue`.
- **Reference transforms**: chuỗi biến đổi nội dung được ký trước khi hash; canonicalization có thể xuất hiện ở đây.
- **Enveloped-signature transform**: loại bản thân `Signature` khỏi nội dung được hash nếu signature là descendant của signed subtree.
- **Digest method**: hash bytes sau transforms.

Demo dùng:

~~~java
fac.newCanonicalizationMethod(
        CanonicalizationMethod.EXCLUSIVE,
        (C14NMethodParameterSpec) null)
~~~

cho `SignedInfo` và:

~~~java
fac.newTransform(
        CanonicalizationMethod.EXCLUSIVE,
        (TransformParameterSpec) null)
~~~

trong `Reference`. Chuỗi XML algorithm URI của exclusive C14N là `http://www.w3.org/2001/10/xml-exc-c14n#`.

**Không suy diễn rằng mọi thay đổi về whitespace đều vô hại**. Whitespace bên trong text nodes và whitespace giữa các elements có thể được DOM bảo tồn và trở thành dữ liệu được ký. Sau khi ký, pretty-print thêm indentation vào signed subtree có thể tạo text nodes mới → digest mismatch.

### 6.1. Exclusive C14N không giải quyết mọi khác biệt XML

Exclusive C14N thường hữu ích khi ký một subtree có thể được đặt trong nhiều namespace contexts, vì hạn chế một số namespace declarations không liên quan. Tuy nhiên nó **không bảo đảm** hai documents dùng prefix khác nhau, có text khác nhau hoặc cấu trúc khác nhau sẽ cho cùng digest. Canonicalization không phải XML Schema validation và không tự phân biệt business fields hợp lệ.

Cần chọn thuật toán C14N theo protocol đối tác; không tự đổi từ inclusive sang exclusive sau khi ký. Signature có thuật toán/chế độ canonicalization trong `SignedInfo`, nhưng **bên nhận vẫn cần whitelist chính sách** thay vì tự chấp nhận mọi algorithm do tài liệu không tin cậy yêu cầu.

## 7. Reference URI: phần nào đã được ký?

`Reference URI="#pay-42"` nghĩa là dereferencer tìm **một đối tượng có ID được công nhận là `pay-42`** trong tài liệu. Trong DOM chưa có XML Schema validation, thuộc tính literal `Id="pay-42"` **không tự động được DOM xem là kiểu ID**.

Trên Java DSig DOM API, application có thể đăng ký:

~~~java
signContext.setIdAttributeNS(payment, null, "Id");
validateContext.setIdAttributeNS(payment, null, "Id");
~~~

Hai dòng trên là **snippets ở hai context khác nhau**; `payment` là `Element` đã được chọn và kiểm tra, `Id` là thuộc tính không namespace. Khi parser sử dụng schema đã xác định ID attribute một cách đáng tin, cơ chế có thể khác; nhưng **không dựa vào một tên chuỗi `Id` bất kỳ** rồi để implementation tìm node đầu tiên trùng tên.

### 7.1. Vì sao trùng ID là nguy hiểm?

Giả sử attacker chèn:

~~~xml
<envelope>
  <payment Id="pay-42"><amount>999</amount></payment>
  <wrapper>
    <payment Id="pay-42"><amount>100</amount></payment>
  </wrapper>
  <Signature>...</Signature>
</envelope>
~~~

Đây là **sơ đồ tấn công**, không phải XMLDSig đầy đủ. Một validator có thể dereference `#pay-42` tới một node, trong khi business code dùng node `payment` khác. Nếu policy không kiểm tra cấu trúc/ID, chữ ký có thể được xác nhận cho **một phần dữ liệu không phải phần đang được xử lý**.

Để giảm nguy cơ XSW:

1. Chỉ chấp nhận **root element, namespace và schema/path** đã được định nghĩa cho message type.
2. Chỉ có **một** business element được phép ở vị trí mong đợi.
3. ID của Reference phải **duy nhất** theo các quy tắc ID của toàn bộ vocabulary; kiểm tra duplicate IDs kể cả ID attributes có namespace nếu schema cho phép.
4. **Đăng ký đúng node** làm ID trong `DOMValidateContext`.
5. Whitelist `Reference URI`, số lượng references, algorithms và transforms.
6. Chọn đúng một `ds:Signature` tại vị trí policy cho phép; không lấy signature đầu tiên tùy ý từ `getElementsByTagNameNS` mà không kiểm tra.
7. Chỉ tiêu thụ **đúng node đã được kiểm chứng** và dữ liệu đã được validate; không reparse hoặc chọn một node khác sau khi xác minh mà chưa liên kết nó với reference.
8. Nếu protocol cho phép nhiều signatures/references, quy tắc chọn signature và signed material phải minh bạch, có tests chống wrapping tương ứng.

Demo kiểm tra đúng **một** `payment` direct child của root, đúng một `Signature` direct child, đúng một thuộc tính `Id` literal trùng `pay-42` trong DOM, rồi đăng ký chính node ấy làm ID. Đây là guard **giới hạn theo schema demo**, không thay cho XML Schema validation hoặc XSW defense tổng quát cho nhiều ID attribute vocabularies như `xml:id`, `wsu:Id`.

### 7.2. External references và SSRF

W3C XMLDSig cho phép Reference trỏ tới dữ liệu external hoặc same-document. Nhưng một XML nhận từ bên ngoài có thể chứa:

~~~xml
<ds:Reference URI="https://example.invalid/private-resource.xml"/>
~~~

Nếu ứng dụng/driver dereference tùy ý, có nguy cơ **SSRF, đọc file nội bộ, tải tài nguyên lớn, tấn công redirect** và nondeterministic validation.

Demo **chỉ cho phép chính xác** `#pay-42` và dùng `URIDereferencer` để từ chối URI khác:

~~~java
var delegate = factory.getURIDereferencer();
context.setURIDereferencer((reference, cryptoContext) -> {
    if (!"#pay-42".equals(reference.getURI())) {
        throw new URIReferenceException(
                "URI outside trusted local ID");
    }
    return delegate.dereference(reference, cryptoContext);
});
~~~

Đây là snippet từ method xác minh; đặt policy *trước* khi unmarshal/validate. Đồng thời kiểm tra `Reference.getURI()` sau unmarshal. Trong production, **không tự động nới policy** sang URL từ `KeyInfo`/Reference do XML khai báo nếu không có nhu cầu nghiệp vụ và cơ chế fetch được sandbox/allowlist.

## 8. Secure validation của Java XML Digital Signature

Oracle Java SE hiện hành có **XML Signature secure validation mode**; tài liệu Java SE 26 mô tả chế độ này **được bật mặc định**. Demo vẫn đặt tường minh:

~~~java
context.setProperty(
        "org.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
~~~

Các policy có thể giới hạn những cấu trúc rủi ro như:

- Cấm một số XSLT transforms.
- Giới hạn số lượng `Reference` và số transforms.
- Cấm những thuật toán bị xem là yếu (ví dụ một số MD5-based algorithms).
- Không cho một số external reference URI schemes như `http`, `https`, `file`.
- Kiểm soát duplicate references/IDs ở những trường hợp được provider nhận diện.
- Giới hạn kích thước khóa tối thiểu hoặc các cấu hình crypto yếu.

Các con số giới hạn và chính sách cụ thể **phụ thuộc JDK, security properties và provider**. Với Oracle/OpenJDK có property `jdk.xml.dsig.secureValidationPolicy` điều chỉnh một số hạn chế. **Không vô hiệu hóa secure validation để một tài liệu cũ, yếu được chấp nhận**, nhất là trên input không tin cậy.

Chế độ này **không đủ để giải quyết trust policy, XSW, business-level replay/authorization, XML Schema validation hay XML parser XXE**. Nó là **một lớp** trong defense-in-depth.

## 9. DOM parser phải an toàn trước khi kiểm tra signature

Khi nhận XML bytes từ bên ngoài, cần parse thành DOM để dùng DOM-based XMLSignatureFactory. **Parser chạy trước khi chữ ký được xác minh**, do đó attacker có thể tấn công ở bước parse qua DTD, external entities, entity expansion hoặc oversized input.

Mẫu tạo parser bảo thủ:

~~~java
DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
f.setNamespaceAware(true);
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true);
f.setFeature(
        "http://xml.org/sax/features/external-general-entities",
        false);
f.setFeature(
        "http://xml.org/sax/features/external-parameter-entities",
        false);
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Đây là snippet; cần import `javax.xml.XMLConstants` và `javax.xml.parsers.DocumentBuilderFactory`. Các feature URIs của parser implementation có thể không được mọi provider hỗ trợ. Nếu security-critical setting không được hỗ trợ, **fail closed** thay vì âm thầm tiếp tục parse dữ liệu không tin cậy.

Ngoài các flags:

- **Giới hạn kích thước input** trước parse, ví dụ MB phù hợp nghiệp vụ.
- Giới hạn element depth, số attributes, số references/transforms và dung lượng canonicalization.
- Đặt timeout/cancellation cho luồng đọc từ network.
- Không log toàn bộ signed XML khi chứa secrets/PII.
- Validate message type/schema/required business elements, đặc biệt namespace và vị trí các signed nodes.
- Đối với XMLDSig từ đối tác, kiểm tra thuật toán, key trust, chính sách certificate và replay/expiry ngay cả khi core validation true.

### 9.1. DOM không đồng nghĩa streaming end-to-end

DOM phải giữ cấu trúc document trong memory; một chữ ký XML có nhiều references/transforms có thể tốn CPU/bộ nhớ. StAX phù hợp xử lý event stream, nhưng **API DOM`XMLSignatureFactory` không trở thành streaming chỉ vì input ban đầu là InputStream**. Với XML lớn và yêu cầu ký streaming, cần đánh giá kỹ implementation/library/protocol, giới hạn resource và kiểm thử tương thích.

## 10. Chương trình Java 17+ độc lập: ký một payment và phát hiện sửa dữ liệu

### 10.1. Mục tiêu và phạm vi an toàn

Chương trình `XmlSignatureIntegrityDemo.java`:

1. Tạo DOM namespace-aware với root `{urn:demo:payment}envelope`.
2. Thêm phần tử `payment Id="pay-42"` chứa `amount=100`, và một `note` **không nằm trong phạm vi được ký**.
3. Tạo RSA key pair 3072-bit **chỉ cho demo**.
4. Tạo `Reference URI="#pay-42"` với SHA-256 và exclusive C14N.
5. Tạo `SignedInfo` dùng exclusive C14N và RSA-SHA256.
6. Dùng `DOMSignContext(privateKey, root)` để thêm `ds:Signature` bên cạnh `payment`.
7. Serialize XML ra bytes và parse lại bằng parser an toàn, xác minh với **public key do code tin cậy cấp**.
8. Thay ghi chú unsigned và kiểm tra signature vẫn đúng, minh họa phạm vi ký.
9. Sửa `amount` trong signed payment, kiểm tra core validation false và reference digest false, nhưng SignatureValue vẫn true.
10. Xác minh với một public key không đúng, kết quả false.
11. Tạo duplicate `Id` và external URI, xác nhận guard policy chặn trước khi consumer dùng dữ liệu.
12. In chính xác algorithms và ID để người học hiểu cấu hình.

**Giới hạn:** Chương trình không đọc network, không dùng chứng thư X.509, không thực thi hệ thống thanh toán, không chứng minh certificate chain. Chỉ minh họa cryptographic integrity, signed scope và một **schema-specific validation policy**.

### 10.2. Source đầy đủ `XmlSignatureIntegrityDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.crypto.URIReferenceException;
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
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

public final class XmlSignatureIntegrityDemo {
    private static final String NS = "urn:demo:payment";
    private static final String ID = "pay-42";
    private static final String URI = "#" + ID;

    private static DocumentBuilderFactory safeParserFactory()
            throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature(
                "http://xml.org/sax/features/external-general-entities",
                false);
        f.setFeature(
                "http://xml.org/sax/features/external-parameter-entities",
                false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return f;
    }

    private static Document newDocument() throws Exception {
        Document doc =
                safeParserFactory().newDocumentBuilder().newDocument();
        Element root = doc.createElementNS(NS, "p:envelope");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
                "xmlns:p", NS);
        doc.appendChild(root);

        Element payment = doc.createElementNS(NS, "p:payment");
        payment.setAttribute("Id", ID);
        Element amount = doc.createElementNS(NS, "p:amount");
        amount.setTextContent("100");
        payment.appendChild(amount);
        root.appendChild(payment);

        Element note = doc.createElementNS(NS, "p:note");
        note.setTextContent("original");
        root.appendChild(note);
        return doc;
    }

    private static byte[] serialize(Document doc) throws Exception {
        TransformerFactory factory = TransformerFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer t = factory.newTransformer();
        t.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no");
        t.setOutputProperty(OutputKeys.INDENT, "no");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        t.transform(new DOMSource(doc), new StreamResult(output));
        return output.toByteArray();
    }

    private static Document parse(byte[] bytes) throws Exception {
        return safeParserFactory().newDocumentBuilder().parse(
                new ByteArrayInputStream(bytes));
    }

    private static Element requiredOne(Document doc, String localName) {
        NodeList nodes = doc.getElementsByTagNameNS(NS, localName);
        if (nodes.getLength() != 1) {
            throw new SecurityException(
                    "Expected exactly one " + localName);
        }
        Element element = (Element) nodes.item(0);
        if (element.getParentNode() != doc.getDocumentElement()) {
            throw new SecurityException(
                    localName + " must be a root child");
        }
        return element;
    }

    private static Element requiredSignature(Document doc) {
        NodeList signatures = doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1) {
            throw new SecurityException(
                    "Expected exactly one Signature");
        }
        Element signature = (Element) signatures.item(0);
        if (signature.getParentNode() != doc.getDocumentElement()) {
            throw new SecurityException(
                    "Signature must be a root child");
        }
        return signature;
    }

    private static Element trustedPayment(Document doc) {
        Element payment = requiredOne(doc, "payment");
        if (!ID.equals(payment.getAttribute("Id"))) {
            throw new SecurityException("Unexpected payment Id");
        }

        int count = 0;
        NodeList elements = doc.getElementsByTagName("*");
        for (int i = 0; i < elements.getLength(); i++) {
            Element element = (Element) elements.item(i);
            if (element.hasAttribute("Id")
                    && ID.equals(element.getAttribute("Id"))) {
                count++;
                if (element != payment) {
                    throw new SecurityException(
                            "Duplicate payment Id");
                }
            }
        }
        if (count != 1) {
            throw new SecurityException(
                    "Payment Id is not unique");
        }
        return payment;
    }

    private static void sign(Document doc, KeyPair pair)
            throws Exception {
        XMLSignatureFactory f =
                XMLSignatureFactory.getInstance("DOM");
        Element payment = trustedPayment(doc);

        Reference reference = f.newReference(
                URI,
                f.newDigestMethod(DigestMethod.SHA256, null),
                List.of(f.newTransform(
                        CanonicalizationMethod.EXCLUSIVE,
                        (TransformParameterSpec) null)),
                null, null);

        SignedInfo signed = f.newSignedInfo(
                f.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                f.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(reference));

        DOMSignContext context = new DOMSignContext(
                pair.getPrivate(), doc.getDocumentElement());
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(payment, null, "Id");
        f.newXMLSignature(signed, null).sign(context);
    }

    record Verification(boolean core, boolean signatureValue,
                        boolean referenceDigest) {}

    private static Verification verify(
            Document doc, PublicKey trustedKey)
            throws Exception {
        if (!NS.equals(doc.getDocumentElement().getNamespaceURI())
                || !"envelope".equals(
                        doc.getDocumentElement().getLocalName())) {
            throw new SecurityException("Unexpected root element");
        }

        Element payment = trustedPayment(doc);
        Element signatureNode = requiredSignature(doc);
        XMLSignatureFactory f =
                XMLSignatureFactory.getInstance("DOM");

        DOMValidateContext context = new DOMValidateContext(
                trustedKey, signatureNode);
        context.setProperty(
                "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        context.setIdAttributeNS(payment, null, "Id");

        var delegate = f.getURIDereferencer();
        context.setURIDereferencer((ref, cryptoContext) -> {
            if (!URI.equals(ref.getURI())) {
                throw new URIReferenceException(
                        "URI outside trusted local ID");
            }
            return delegate.dereference(ref, cryptoContext);
        });

        XMLSignature sig = f.unmarshalXMLSignature(context);
        List<?> references = sig.getSignedInfo().getReferences();
        if (references.size() != 1) {
            throw new SecurityException(
                    "Unexpected reference count");
        }

        Reference reference = (Reference) references.get(0);
        if (!URI.equals(reference.getURI())) {
            throw new SecurityException(
                    "External or unexpected URI");
        }
        if (!DigestMethod.SHA256.equals(
                    reference.getDigestMethod().getAlgorithm())
                || !SignatureMethod.RSA_SHA256.equals(
                    sig.getSignedInfo().getSignatureMethod()
                            .getAlgorithm())
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                    sig.getSignedInfo().getCanonicalizationMethod()
                            .getAlgorithm())
                || reference.getTransforms().size() != 1
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                    ((Transform) reference.getTransforms().get(0))
                            .getAlgorithm())) {
            throw new SecurityException(
                    "Unexpected XML signature policy");
        }

        boolean core = sig.validate(context);
        boolean signatureValue =
                sig.getSignatureValue().validate(context);
        boolean digest = reference.validate(context);
        return new Verification(core, signatureValue, digest);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair pair = generator.generateKeyPair();

        Document unsigned = newDocument();
        sign(unsigned, pair);
        byte[] signedBytes = serialize(unsigned);

        Verification original =
                verify(parse(signedBytes), pair.getPublic());
        System.out.println("Signed document validates: "
                + original.core());

        Document unsignedEdit = parse(signedBytes);
        requiredOne(unsignedEdit, "note").setTextContent("changed");
        System.out.println("Unsigned note changed, validates: "
                + verify(unsignedEdit, pair.getPublic()).core());

        Document signedEdit = parse(signedBytes);
        Element amount = (Element) requiredOne(
                signedEdit, "payment").getElementsByTagNameNS(
                NS, "amount").item(0);
        amount.setTextContent("999");
        Verification changed =
                verify(signedEdit, pair.getPublic());
        System.out.println("Signed amount changed, validates: "
                + changed.core());
        System.out.println("Signed amount digest validates: "
                + changed.referenceDigest());
        System.out.println(
                "SignatureValue still validates on payload edit: "
                + changed.signatureValue());

        KeyPair another = generator.generateKeyPair();
        System.out.println("Wrong trusted public key validates: "
                + verify(parse(signedBytes), another.getPublic()).core());

        Document duplicate = parse(signedBytes);
        Element extra =
                duplicate.createElementNS(NS, "p:other");
        extra.setAttribute("Id", ID);
        duplicate.getDocumentElement().appendChild(extra);
        try {
            verify(duplicate, pair.getPublic());
            throw new AssertionError(
                    "Duplicate Id should be rejected");
        } catch (SecurityException expected) {
            System.out.println("Duplicate Id rejected: true");
        }

        Document differentReference = parse(signedBytes);
        Node referenceNode =
                differentReference.getElementsByTagNameNS(
                        XMLSignature.XMLNS, "Reference").item(0);
        ((Element) referenceNode).setAttribute(
                "URI", "https://example.invalid/external.xml");
        try {
            verify(differentReference, pair.getPublic());
            throw new AssertionError(
                    "External URI should be rejected");
        } catch (SecurityException expected) {
            System.out.println("External URI rejected: true");
        }

        System.out.println("Referenced element Id: " + ID);
        System.out.println(
                "Digest algorithm: " + DigestMethod.SHA256);
        System.out.println(
                "Signature algorithm: " + SignatureMethod.RSA_SHA256);
        System.out.println(
                "Demo keys only; no certificate trust claim: true");
    }
}
~~~

### 10.3. Biên dịch/chạy

Lưu source thành file `XmlSignatureIntegrityDemo.java` khớp tên public class. Tại thư mục chứa file:

~~~sh
javac --release 17 XmlSignatureIntegrityDemo.java
java XmlSignatureIntegrityDemo
~~~

Chỉ dùng Java SE APIs hiện hành (module `java.xml.crypto` và `java.xml`). Không cần Maven/Gradle, database hay cert file. KeyPair được tạo tạm ở runtime chỉ cho kiểm thử.

**Stdout chính xác**, đã biên dịch bằng `javac --release 17` trên JDK 24 và chạy thành công:

~~~text
Signed document validates: true
Unsigned note changed, validates: true
Signed amount changed, validates: false
Signed amount digest validates: false
SignatureValue still validates on payload edit: true
Wrong trusted public key validates: false
Duplicate Id rejected: true
External URI rejected: true
Referenced element Id: pay-42
Digest algorithm: http://www.w3.org/2001/04/xmlenc#sha256
Signature algorithm: http://www.w3.org/2001/04/xmldsig-more#rsa-sha256
Demo keys only; no certificate trust claim: true
~~~

Các dòng là kết quả của **program tự chạy**, không phụ thuộc dữ liệu ngẫu nhiên của cặp RSA ở dạng text. Chữ ký tạo ra ở mỗi lần chạy có bytes khác nhau, nhưng những điều kiện true/false mong đợi vẫn nhất quán nếu provider đáp ứng các thuật toán.

### 10.4. Giải thích vì sao `note` đổi mà signature vẫn true

Reference chỉ bảo vệ `<p:payment Id="pay-42">...</p:payment>`. `<p:note>` là sibling nằm **ngoài reference**. Khi thay text note từ `original` thành `changed`:

- XML document thay đổi.
- Nhưng **canonicalized bytes của referenced payment** không đổi.
- `Reference DigestValue` vẫn đúng.
- `SignedInfo` và `SignatureValue` không đổi.
- `XMLSignature.validate(...)` trả true.

Đó **không phải lỗi** của XMLDSig: phạm vi ký được thiết kế rõ ràng. Nhưng **sẽ là lỗi bảo mật ứng dụng** nếu service tin rằng mọi thông tin trong document (bao gồm note, deadline, payer account, destination) đều được xác thực chỉ vì một Reference hợp lệ.

**Quy tắc:** mọi trường nghiệp vụ ảnh hưởng đến quyết định phải **nằm trong signed references**, hoặc có cơ chế bảo vệ khác được xác minh; đừng đưa dữ liệu unsigned vào authorization/payment calculation.

### 10.5. Giải thích vì sao `amount` đổi làm core validation false

Sau khi thay số tiền `100` thành `999` trong đúng signed payment:

- Ref URI `#pay-42` vẫn trỏ tới payment.
- Canonicalization của payment cho bytes khác.
- SHA-256 digest khác `DigestValue` đã ký.
- Reference validation false.
- `SignatureValue` trên `SignedInfo` vẫn đúng, vì `SignedInfo` chưa đổi.
- Core validation (`XMLSignature.validate`) false.

Điểm này chứng minh **không thể chỉ kiểm tra SignatureValue** mà phải dùng core validation và bảo đảm reference đúng.

### 10.6. Giải thích `Wrong trusted public key validates: false`

Demo tạo cặp RSA thứ hai, dùng public key mới để xác minh chữ ký tạo bằng private key thứ nhất. Vì khóa không tương ứng, SignatureValue verification thất bại. Điều đó minh họa lý do khóa kiểm tra phải xuất phát từ **trusted source**.

Tuy nhiên, kết quả false với key ngẫu nhiên **không thay cho certificate path validation**. Demo không phát hành và không xác minh chứng thư X.509 thật.

### 10.7. Vì sao duplicate ID/external URI bị từ chối?

- Demo thêm một element khác có cùng literal `Id="pay-42"`. Hàm `trustedPayment` thấy có duplicate và ném `SecurityException`. Guard chặn ngay cả trước khi làm phép so digest.
- Demo sửa `Reference URI` thành external HTTPS URL. Hàm `verify` kiểm tra reference URI có đúng `#pay-42` hay không và từ chối. Chính sách `URIDereferencer` cũng ngăn dereferencing ngoài scope nếu bị gọi trong validation.
- Chúng không phải ví dụ khai thác XSW hoàn chỉnh; chúng minh họa kiểm tra **input shape và reference policy**.

### 10.8. Vì sao serializing rồi parse lại?

Ký và verify trên cùng một DOM object có thể che lấp một số lỗi về canonicalization hoặc ID setup. Chương trình gọi `serialize(Document)` rồi `parse(byte[])` trước khi verify để mô phỏng boundary gửi/nhận và đòi hỏi bên nhận **đăng ký lại ID** bằng `DOMValidateContext.setIdAttributeNS`.

Không dùng `transformer.setOutputProperty(OutputKeys.INDENT,"yes")` trên vùng được ký sau khi tạo signature nếu nó làm thêm whitespace nodes. JavaDoc không bảo đảm mọi dạng pretty-print giữ nguyên signed digest.

## 11. Mẫu ký/verifying trong hệ thống thực

### 11.1. Bên ký

~~~text
Validate outgoing data/schema
        |
        v
Build stable namespace-aware DOM
        |
        v
Resolve exact business element and unique ID
        |
        v
Obtain authorized private key from keystore/HSM/KMS
        |
        v
Construct expected references + canonicalization + algorithms
        |
        v
DOMSignContext + XMLSignature.sign(...)
        |
        v
Serialize without changing signed content
        |
        v
Deliver XML + key identifier/certificate profile as required
~~~

Tránh phát chữ ký nếu dữ liệu đầu vào chưa qua validation hoặc chứa các fields cần thiết chưa thuộc reference. Đảm bảo ký đúng **tenant, operation, amount, destination, request ID, expiry** theo message contract. Nếu gửi nhiều references, kiểm thử rằng **tất cả** đúng phạm vi và không có reference ngoài whitelist.

### 11.2. Bên nhận

~~~text
Receive bounded-size XML bytes
        |
        v
Parse with XXE-disabled, namespace-aware DOM
        |
        v
Check expected root/message type/schema and signature placement
        |
        v
Resolve expected business element(s), unique ID(s)
        |
        v
Select trusted verification key for sender/tenant/role
        |
        v
DOMValidateContext(...), secureValidation=true
        |
        v
Restrict references, transforms, algorithms, dereferencer
        |
        v
XMLSignature.validate(context)
        |
        v
Verify business fields are from the same protected node(s)
        |
        v
Check expiry, nonce/request ID, duplicate/replay, authorization
        |
        v
Execute business operation idempotently
~~~

**Fail closed** nếu reference không khớp expected target, có nhiều signatures/IDs không thuộc profile, bị lệch namespace hoặc chứng thư không còn đáng tin. Không “thử lần lượt vài signature cho đến khi có một signature true” rồi dùng bất kỳ payment node nào ứng dụng tìm được.

### 11.3. Nhiều reference hoặc nhiều chữ ký

W3C XMLDSig cho phép nhiều References trong SignedInfo và nhiều chữ ký trong document. Nếu protocol thật dùng nhiều refs, policy nên khai báo **tập Reference URI chính xác** cùng vai trò mỗi phần được ký. Mỗi Reference cần được kiểm tra digest, và policy phải ràng buộc đúng phần dữ liệu mà code xử lý.

Demo cố ý chỉ chấp nhận **một** reference `#pay-42` và **một** chữ ký để đơn giản hóa invariant. Không áp cứng policy này cho SOAP/WS-Security hoặc tài liệu nhiều chữ ký nếu đó là protocol hợp lệ; thay bằng chính sách schema/profile tương ứng và tests.

## 12. XML Signature Wrapping: chữ ký đúng vẫn có thể bị lạm dụng

Một pattern XSW kinh điển:

1. Attacker giữ nguyên một subtree đã được ký hợp lệ để validator vẫn thấy digest đúng.
2. Attacker chèn hoặc di chuyển một subtree mới có dữ liệu ác ý ở vị trí business code sẽ đọc.
3. Validator xác minh subtree cũ; business code lại lấy subtree mới (ví dụ `document.getElementsByTagName("payment").item(0)`).
4. Hệ thống thực hiện nghiệp vụ trên **dữ liệu chưa hề được ký**.

Giảm nguy cơ bằng:

- Strict XML schema với vị trí, số lượng phần tử và namespaces.
- ID uniqueness (cả custom IDs, namespaced IDs, typed IDs), không chấp nhận duplicate hoặc ambiguous matches.
- Explicit reference resolution và whitelist algorithm/transform/URI.
- Binding đối tượng business cuối cùng với **đúng DOM Element đã được reference bảo vệ**.
- Không để XSLT/XPath transforms tùy ý từ input không tin cậy thay đổi selection context.
- Không tin message type/authorization ngoài signed scope.
- Unit/integration tests với duplicate IDs, reordered wrappers, nested nodes, altered namespace, unsigned overrides và multiple signatures.

**Lưu ý:** Demo `trustedPayment` kiểm tra literal `Id`, vị trí direct-child và số `payment` trong namespace riêng. Đó là guard tốt **cho schema minh họa**, nhưng chưa kiểm hết mọi ID types/prefixes/foreign protocols. Để triển khai chống XSW thật, cần policy chính thức theo XML schema cụ thể, validated ID-typed attributes, protocol reference rules và library/parser có security track record.

## 13. KeyInfo và certificate: ví dụ về trách nhiệm ứng dụng

Java XMLDSig có `KeyInfoFactory` và các interface liên quan:

~~~java
KeyInfoFactory keyInfoFactory = factory.getKeyInfoFactory();
~~~

Đây là snippet với `XMLSignatureFactory factory`. `KeyInfo` có thể chứa:

- `KeyValue`: public key dưới dạng cấu trúc XMLDSig.
- `X509Data`: certificate, issuer/serial hoặc các cấu trúc X.509 liên quan.
- `KeyName`: tên khóa do protocol quy định.
- `RetrievalMethod`: reference tới dữ liệu khóa khác.

Không có cái nào tự bảo đảm **trust**. Một `KeyValueKeySelector` kiểu tutorial có thể lấy public key từ document và dùng nó cho cryptographic verification, nhưng **bên nhận vẫn phải xác minh public key/chứng thư đó được phép ký message**.

Trong hệ thống thật, client onboarding có thể cung cấp trusted certificate fingerprint/public key theo đối tác, hoặc sử dụng PKIX trust chain và constraints. Hãy kiểm tra signer identity, key usage, certificate policy, expiration/revocation theo yêu cầu. Chỉ chấp nhận `KeyInfo` như **hint** để tìm key trong tập trusted keys, không để XML quyết định toàn bộ trust anchor.

## 14. Không đồng nhất chữ ký với mã hóa và authorization

Ba khái niệm:

| Bảo vệ | Câu hỏi trả lời | XMLDSig tự cung cấp? |
| --- | --- | --- |
| **Integrity** | Phần dữ liệu được ký có bị sửa không? | Có, khi core validation đúng |
| **Authentication của khóa** | Dữ liệu do private key tương ứng ký? | Có về mặt mật mã; key-to-identity cần trust policy |
| **Confidentiality** | Người không có quyền có đọc được XML không? | **Không**; cần TLS/XML Encryption hoặc bảo vệ lưu trữ |
| **Authorization** | Người ký có được phép yêu cầu giao dịch này không? | **Không**; cần policy/role/tenant checks |
| **Replay protection** | Message này đã được dùng trước đó chưa? | **Không**; cần nonce/idempotency key/timestamp có ràng buộc trong signed scope |
| **Semantic validation** | Amount, currency, recipient, schema đúng không? | **Không**; cần schema/business validation |

Chữ ký hợp lệ không xác nhận rằng một giao dịch 100 USD là được phép. Nó chỉ xác nhận dữ liệu được ký phù hợp với public key và reference rules. Không thay thế authentication/authorization của ứng dụng.

## 15. Một số vấn đề thường khiến verify bất ngờ thất bại

### 15.1. Thay đổi whitespace trong signed subtree

XML:

~~~xml
<p:payment xmlns:p="urn:demo:payment" Id="pay-42">
  <p:amount>100</p:amount>
</p:payment>
~~~

Thêm/bớt indent/newlines có thể thay đổi text nodes và canonicalized bytes. Đừng dùng một formatter tự động trên signed XML trước verify, cũng đừng tự ý normalize whitespace của text nội dung.

### 15.2. Sửa namespace prefix hoặc declarations

Canonicalization xử lý namespace bindings theo thuật toán cụ thể. Đổi lexical prefix có thể thay canonicalized bytes dù namespace URIs giống nhau về nghĩa ứng dụng. Exclusive C14N hạn chế một số ảnh hưởng của ancestor context nhưng **không** bảo đảm mọi prefix rewrite an toàn sau ký.

### 15.3. Không đăng ký ID ở phía validate

DOM parser không tự biết literal `Id` là type ID. `#pay-42` có thể không resolve được, dẫn tới `URIReferenceException` hoặc validation error. Bên nhận cần parse/schema/ID registration đúng; đừng “sửa” bằng cách cho phép dereference mọi URI không kiểm soát.

### 15.4. Quên enveloped transform khi signature nằm trong vùng ký

Nếu signature là descendant của node được ký, canonicalization/digest cần tránh hash cả signature mới. Dùng `Transform.ENVELOPED` theo profile. Demo không dùng vì signature nằm **ngoài `payment`**.

### 15.5. Thay `SignatureMethod` mà không cập nhật key/profile

RSA key không thể tự dùng với ECDSA signature algorithm; algorithm mismatch hoặc unsupported provider gây `XMLSignatureException`/`MarshalException`/`NoSuchAlgorithmException` theo phase. Whitelist thuật toán và kiểm thử liên thông với đối tác.

### 15.6. Chỉ xác minh SignatureValue

`SignatureValue.validate(context)==true` không chứng minh mọi Reference digest đã đúng. Luôn gọi **`XMLSignature.validate(context)`** và bảo đảm signed material được nghiệp vụ sử dụng.

### 15.7. Chỉ chấp nhận KeyInfo trong tài liệu làm trusted key

Attacker có thể ký bằng khóa riêng của họ và gửi public key tương ứng. Crypto verification true **không** đồng nghĩa identity/trust true. Pin keys hoặc xác minh trust chain.

### 15.8. Nhầm XML Signature với XML Schema validation

Schema validation có thể xác nhận field types/structure; signature validation chứng minh integrity/authentication đối với references. Cần cả hai khi message contract yêu cầu.

### 15.9. Phụ thuộc external URI từ XML

Có nguy cơ SSRF/file access và kết quả không ổn định. Với business document same-document, khóa chính xác refs thành `#knownId` và dùng restrictive dereferencer; với external refs hợp lệ trong protocol, thực thi fetch trong sandbox/allowlist với giới hạn và trust riêng.

## 16. Chẩn đoán thất bại mà không tiết lộ secrets

Nếu `XMLSignature.validate(context)` trả false, có thể kiểm tra riêng `SignatureValue` và từng `Reference` để xác định failure ở signature key/algorithm hay digest/transforms/data.

Ví dụ snippet:

~~~java
boolean core = signature.validate(context);
boolean crypto = signature.getSignatureValue().validate(context);

for (Object item : signature.getSignedInfo().getReferences()) {
    Reference ref = (Reference) item;
    boolean validDigest = ref.validate(context);
    System.out.println(
            ref.getURI() + " digest=" + validDigest);
}
~~~

Đây là **snippet**, với `signature` đã được unmarshal và `context` đã được cấu hình an toàn. **Không gọi validation trên input chưa bị giới hạn** vì dereferencing/transforms có thể tốn tài nguyên; áp policy trước.

Thông tin log hữu ích:

~~~text
operation/message_type
tenant_or_partner_id (không chứa secrets)
signature_id / trusted_key_id
reference_uri_allowlist_decision
digest_algorithm
signature_algorithm
canonicalization_algorithm
core_valid
signature_value_valid
reference_digest_valid
schema_path_valid
id_uniqueness_valid
trust_policy_valid
elapsed_ms
reason_category
~~~

Đây là schema telemetry minh họa. Không log private key, raw payment XML, token nhạy cảm hoặc toàn bộ certificate chain vào logs mặc định. Khi có `XMLSignatureException` hoặc `MarshalException`, log safe failure category, correlation ID và cause chain đã redacted.

### 16.1. `false` khác `exception`

- `validate()==false`: việc kiểm tra core signature/digest không thành công theo dữ liệu và khóa/algorithms đã được parse, và không có exception làm dừng thao tác.
- `XMLSignatureException`: có vấn đề trong quá trình validate/dereference/crypto.
- `MarshalException`: không thể unmarshal cấu trúc chữ ký đúng profile/provider.
- `URIReferenceException`: reference resolution bị lỗi hoặc bị policy từ chối.
- `ParserConfigurationException`/`SAXException`/`IOException`: lỗi tạo parser hoặc đọc XML trước signature validation.

**Không** catch mọi exception rồi coi như “valid=false và dùng tạm dữ liệu nếu không quan trọng”. Business XML nhận từ nguồn không tin cậy phải **fail closed** khi parser/validation/trust policy không đạt.

## 17. Performance và memory

DOM-based Java XMLDSig làm việc trên cây DOM, nên:

- Memory thường tăng theo **document size + DOM overhead + canonicalization buffers**.
- Mỗi `Reference` có thể dẫn tới thêm dereferencing/transforms và hashing.
- Reference URI external/complex XSLT/XPath có thể làm chi phí lớn bất thường.
- Signature verification RSA/ECDSA thường nhỏ hơn chi phí parse/canonicalize với XML lớn, nhưng cần đo theo workload.
- Việc parse lại XML sau signature có thể tăng cost, đổi lại cho phép test đường đi persistence/transport thực tế; production có thể giữ DOM an toàn và verify trong cùng process nếu contract phù hợp.

Các biện pháp:

1. Đặt hard limit trên XML bytes, element depth, attributes count, references count, transforms count và canonicalization work.
2. Giữ secureValidation bật.
3. Dùng input stream/size-limited reader để chặn tải quá mức **trước parse**.
4. Không deserialize DOM thành model ứng dụng trước validation.
5. Không lấy untrusted Reference URI để network-fetch vô giới hạn.
6. Reuse configured key material/trust policy một cách an toàn, không cache mutable `DOMValidateContext` dùng chung nhiều threads.
7. Benchmark trên JDK/provider thực tế, đặc biệt với XML nhiều MB và nhiều references.
8. Không tăng giới hạn chỉ để chấp nhận một tài liệu vô lý do đối tác gửi; điều tra và sửa protocol nếu cần.

## 18. Ma trận kiểm thử cho XMLDSig

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Valid signature | Đúng public key và signed payload | Core validation true |
| Signed field edited | `amount=100` thành `999` | Ref digest false; core false |
| Unsigned field edited | Sửa `note` ngoài reference | Có thể core true; app không được tin note nếu ảnh hưởng nghiệp vụ |
| Wrong public key | Khóa khác với signer | SignatureValue/core false |
| Duplicate literal ID | Hai elements `Id="pay-42"` | Schema/profile guard từ chối |
| Wrapped signed node | Signed node chuyển wrapper, unsigned node ở expected path | Schema/path/reference policy từ chối |
| Reference URI changed | `#pay-42` đổi thành HTTPS/file URI | External URI policy từ chối |
| Missing target ID | Không có target ID hợp lệ | Fail closed |
| ID in another namespace | `xml:id`/`wsu:Id` trong protocol có hỗ trợ | Xử lý theo explicit schema/ID policy, không đoán |
| Multiple Signatures | Nhiều `ds:Signature` trong input | Chọn theo trusted profile hoặc reject |
| Extra references | Reference ngoài expected set | Policy reject |
| Weak algorithms | SHA-1/MD5/unsupported method | Security policy reject |
| Unknown transform | XSLT/XPath hoặc transform phức tạp ngoài profile | Reject, không chạy tùy ý |
| Enveloped mode | Signature nằm trong signed root | Enveloped transform áp dụng đúng |
| Detached same-document | Signature sibling signed element | Reference URI chính xác |
| Pretty-print after sign | Thêm text whitespace vào signed subtree | Có thể digest mismatch |
| Reparse after serialization | DOM signer → bytes → DOM validator | ID registration và C14N ổn định |
| KeyInfo from attacker | Public key chỉ có trong XML | Không tự nâng thành trusted key |
| Certificate expired/revoked | X509Data có certificate không đạt policy | Rejected ở trust layer |
| Replay identical document | Cùng valid signature được gửi lại | Idempotency/nonce checker chặn |
| Unsigned authorization field | Role/tenant nằm ngoài refs | App từ chối dùng unsigned field |
| Oversized XML/DTD | XML bomb/XXE | Parser/security limits chặn |
| Multi-tenant key mismatch | Merchant A signature dùng key của B | Trust/key identity policy từ chối |
| Java 17 build | JDK17+ APIs | `javac --release 17` PASS |

Các test về key trust, XSW, certificate revocation và full protocol phải chạy trong môi trường kiểm thử phù hợp; demo chỉ kiểm một số guards và cryptographic correctness cơ bản.

## 19. Bài tập thực hành có hướng dẫn

### 19.1. Bài tập A: thêm một trường quan trọng vào payment

Thêm:

~~~xml
<p:currency>USD</p:currency>
~~~

**vào trong** `p:payment` trước khi ký. Sau khi ký xong, đổi `USD` thành `EUR` và xác minh thất bại. Lý do: field currency thuộc signed subtree, hash thay đổi.

Ngược lại, nếu currency là sibling unsigned của payment, core validation có thể vẫn true khi currency đổi. Đó là bug trong thiết kế message contract nếu quyết định số tiền phải dựa trên currency này.

### 19.2. Bài tập B: thay scope ký

Nếu nghiệp vụ yêu cầu bảo vệ cả `payment` và `note`, hãy thiết kế protocol:

- Ký toàn root bằng `URI=""` và enveloped transform, **hoặc**
- Dùng hai references với expected IDs (mỗi ID duy nhất, registration rõ ràng) và kiểm tra đủ references khi validate.

Không chỉ đổi `#pay-42` thành `""` trong demo mà giữ nguyên validation policy; cả signing logic, transforms và expected references đều phải cùng được cập nhật. Khi thay signed scope, unit tests về unsigned changes cũng phải thay.

### 19.3. Bài tập C: đổi khóa kiểm tra

Tạo KeyPair thứ hai và dùng public key mới để validate chữ ký thứ nhất. Kỳ vọng:

~~~text
Wrong trusted public key validates: false
~~~

Giải thích vì sao attacker có thể đưa chính public key của họ vào `KeyInfo` để tạo chữ ký đúng về kỹ thuật, nhưng vẫn không được hệ thống tin.

### 19.4. Bài tập D: bảo vệ chống signature wrapping

Thử chèn thêm một element có `Id="pay-42"` vào document. Kỳ vọng demo từ chối duplicate ID. Nâng cấp guard theo protocol bạn chọn:

- Xác định expected root path/namespace và cardinality.
- Chỉ cho những ID attributes được schema phê duyệt.
- Kiểm tra tất cả ID-typed attributes và uniqueness.
- Ràng buộc reference target với đúng business object.
- Thử nhiều payload wrapping/namespace-rebinding/multiple signatures trong test fixture.

Không coi guard theo đúng một literal `Id` như một thư viện XSW đầy đủ.

### 19.5. Bài tập E: chẩn đoán hai loại validation failure

Lần 1: sửa signed payload, giữ nguyên public key. Kỳ vọng:

~~~text
Signed amount digest validates: false
SignatureValue still validates on payload edit: true
~~~

Lần 2: giữ original payload nhưng đổi trusted public key. Kỳ vọng core false do SignatureValue. Hai case minh họa sự khác nhau giữa hash nội dung và chữ ký mật mã trên SignedInfo.

## 20. Những sai lầm thường gặp và cách khắc phục

| Sai lầm | Vì sao nguy hiểm | Hướng đúng |
| --- | --- | --- |
| Chỉ `getSignatureValue().validate` | Có thể bỏ qua Reference digest mismatch | Dùng `XMLSignature.validate` |
| Tin `KeyInfo.KeyValue` như identity | Attacker tự ký bằng key của họ | Trusted public key/PKIX policy độc lập |
| Chỉ tìm node theo localName | Có thể lấy node không cùng namespace | So QName + path/schema |
| Lấy `payment` đầu tiên bất kỳ | Signature wrapping | Ràng buộc đúng signed target |
| Không kiểm tra ID uniqueness | Ambiguous URI resolution | Unique typed IDs, schema validation |
| Không `setIdAttributeNS` | Reference không resolve/resolve sai | Đăng ký đúng ID đã validate |
| Dùng `Reference URI=""` khi chỉ muốn một node | Phạm vi ký không như ý định | Chọn URI theo protocol |
| Cho phép URI bất kỳ | SSRF/file access và untrusted references | URI allowlist/restrictive dereferencer |
| Tắt secureValidation | Mở thêm unsafe algorithms/transforms/DoS | Giữ bật và pin algorithms |
| Dùng SHA-1/MD5 vì tutorial cũ | Yếu và dễ fail security policy | SHA-256 và signature algorithm hiện hành |
| Nhầm DigestMethod với SignatureMethod | Hash không chứng minh key ownership | Phân biệt digest và digital signature |
| Quên enveloped transform | Signature hash chính nó | Cấu hình đúng reference layout |
| Pretty print sau sign | Có thể thay text nodes/digest | Giữ signed subtree ổn định |
| Nghĩ exclusive C14N bảo toàn mọi semantic changes | Không đúng | Canonicalization không thay schema validation |
| Cho phép XSLT transform bất kỳ | Performance/security/selection risk | Restrict transforms theo profile |
| Parse với DTD/external entities | XXE/DoS trước khi verify | Harden DOM parser |
| Chỉ dựa vào coreValid=true | Unsigned fields vẫn có thể thay | Check signed scope và business data |
| Không chống replay | Valid XML gửi nhiều lần | Signed nonce/request ID + dedupe |
| Tự tạo key mới mỗi request | Mất quản lý signer identity | Keystore/HSM/KMS + rotation |
| Không kiểm tra certificate trust | Key có thể không thuộc đối tác | PKIX/pinning/issuer policy |
| Bỏ qua namespace trong XML Signature | Select nhầm `Signature` giả | `XMLSignature.XMLNS` + local name |
| Tưởng XMLDSig mã hóa XML | Lộ nội dung nhạy cảm | TLS/storage encryption/XML Encryption khi cần |
| Dùng DOM cho XML vô hạn | Memory/CPU DoS | Size/depth/reference limits |
| Mượn `DOMValidateContext` cho nhiều threads | Mutable state/cached validation | Tạo context theo mỗi validation operation |
| Không xem Reference algorithms | Attacker dùng profile ngoài policy | Pin digest/signature/C14N/transforms |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** XML Digital Signature API nằm ở package nào của Java?

**Trả lời:** Chủ yếu `javax.xml.crypto.dsig`, với DOM integration tại `javax.xml.crypto.dsig.dom`, key info tại `javax.xml.crypto.dsig.keyinfo`. Java SE module là `java.xml.crypto`.

**Câu 2.** `Reference` và `SignatureValue` khác nhau thế nào?

**Trả lời:** Reference xác định dữ liệu, transforms và digest. SignatureValue là chữ ký mật mã trên SignedInfo. Core validation kiểm tra cả signature value và các reference digests.

**Câu 3.** Vì sao thay số tiền trong payment khiến core validation false nhưng SignatureValue validation vẫn true?

**Trả lời:** SignedInfo không đổi nên chữ ký trên SignedInfo còn đúng; dữ liệu payment đã đổi nên hash/reference digest mismatch.

**Câu 4.** `KeyInfo` chứa public key có chứng minh đối tác đáng tin không?

**Trả lời:** Không. Trust anchor/certificate/key identity phải được xác lập qua policy độc lập.

**Câu 5.** `URI="#pay-42"` có tự tìm mọi element chứa `Id="pay-42"` không?

**Trả lời:** Không được dựa vào điều đó. DOM phải biết thuộc tính nào là kiểu ID; dùng schema đáng tin hoặc `setIdAttributeNS` trên đúng Element đã được kiểm tra.

**Câu 6.** Vì sao cần kiểm tra duplicate ID?

**Trả lời:** Để tránh URI tham chiếu trở nên ambiguous, và giảm nguy cơ signature wrapping khi validator/business code chọn những nodes khác nhau.

**Câu 7.** Enveloped signature cần transform gì thường gặp?

**Trả lời:** `Transform.ENVELOPED` để loại chính Signature khỏi phần data được hash khi Signature nằm trong signed subtree. Same-document detached signature sibling có thể không cần transform đó.

**Câu 8.** SHA-256 và RSA-SHA256 có cùng chức năng không?

**Trả lời:** Không. `DigestMethod.SHA256` hash reference content; `SignatureMethod.RSA_SHA256` ký/xác minh SignedInfo với khóa RSA và SHA-256.

**Câu 9.** `CanonicalizationMethod.EXCLUSIVE` dùng để làm gì?

**Trả lời:** Chuẩn hóa XML thành octets theo exclusive C14N policy, nhằm tạo cách tính digest/signature nhất quán. Không thay thế XML Schema validation hoặc ngăn mọi prefix/whitespace change.

**Câu 10.** Thay `note` ngoài signed subtree mà chữ ký vẫn true có là lỗi của XMLDSig không?

**Trả lời:** Không. Chữ ký chỉ bảo vệ references đã định nghĩa. Nhưng có thể là lỗi thiết kế nghiệp vụ nếu ứng dụng tin note dù không ký nó.

**Câu 11.** `secureValidation=true` có thay thế chống XSW và certificate trust không?

**Trả lời:** Không. Nó hạn chế một số nguy cơ XMLDSig parser/algorithm/transform. Vẫn cần schema/path/ID guards và trusted key/certificate validation.

**Câu 12.** Vì sao không tự dereference external URLs từ XML?

**Trả lời:** Có nguy cơ SSRF/file access/DoS và validation phụ thuộc network. Chỉ cho references được protocol phê duyệt, dùng allowlist và restrictive dereferencer.

**Câu 13.** Chữ ký hợp lệ có ngăn replay không?

**Trả lời:** Không. Bên nhận cần check signed timestamp/nonce/request ID và lưu trạng thái dedupe/idempotency theo policy.

**Câu 14.** Khi nào `XMLSignature.validate` trả false, khi nào throw exception?

**Trả lời:** False khi core checks không khớp; exception khi parse/unmarshal, dereference, algorithms/provider hoặc crypto processing gặp lỗi. Cả hai đều phải được xử lý fail closed đối với message không tin cậy.

**Câu 15.** Vì sao demo parse lại XML sau serialization?

**Trả lời:** Để kiểm tra đường đi gửi/nhận qua bytes và nhắc rằng bên nhận phải đăng ký lại ID/trust policy; không chỉ verify trong cùng DOM signer.

**Câu 16.** Một signature xác nhận quyền chuyển tiền 100 USD không?

**Trả lời:** Nó xác nhận dữ liệu được ký không đổi và hợp lệ với public key; quyền chuyển tiền còn phụ thuộc signer identity, authorization, số dư, giới hạn giao dịch, tenant và business rules.

**Câu 17.** Dùng một signature hợp lệ trên một node rồi business code đọc node khác có nguy cơ gì?

**Trả lời:** XML Signature Wrapping. Phải ràng buộc signed reference target với chính business DOM element được xử lý.

**Câu 18.** XMLDSig có mã hóa dữ liệu không?

**Trả lời:** Không. XML digital signature hỗ trợ integrity/authentication của signed content; bảo mật nội dung cần lớp encryption riêng.

**Ghi nhớ:** XML Digital Signature API Java 17+ dùng `XMLSignatureFactory`, `Reference`, `SignedInfo`, `DOMSignContext` và `DOMValidateContext` để ký/xác minh XML. Chọn thuật toán hiện hành như SHA-256/RSA-SHA256, cấu hình canonicalization đúng layout, đăng ký ID thật, giữ secureValidation bật, chặn external references và **xác minh đủ cả SignatureValue lẫn mọi Reference digest**. Sau core validation, phải kiểm tra key trust, schema/path, signed scope, chống wrapping/replay và business authorization. Một chữ ký đúng **chỉ có giá trị trên dữ liệu thật sự nằm trong references** — không phải giấy thông hành cho mọi node trong XML.

### Tài liệu chính thức và tiêu chuẩn

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html): JSR 105, signing/validation, secure validation mode, examples.
- [Oracle Java SE 26 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): tạo SignedInfo/Reference/Signature.
- [Oracle Java SE 26 — XMLSignature](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): sign/validate/core validation.
- [Oracle Java SE 26 — DOMSignContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html): ký bằng DOM, đăng ký Id.
- [Oracle Java SE 26 — DOMValidateContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): xác minh, key selection/ID/validation context.
- [Oracle Java SE 26 — Reference](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, transforms, DigestMethod/DigestValue, reference.validate.
- [Oracle Java SE 26 — SignatureMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html): RSA_SHA256 và các algorithms.
- [Oracle Java SE 26 — CanonicalizationMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/CanonicalizationMethod.html): C14N.
- [W3C — XML Signature Syntax and Processing Version 1.1](https://www.w3.org/TR/xmldsig-core/): chuẩn cấu trúc và processing, Reference/SignatureValue, security considerations.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): DOM/JAXP hardening.
