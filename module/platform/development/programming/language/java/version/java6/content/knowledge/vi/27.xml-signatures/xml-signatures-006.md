# Enveloped, enveloping và detached signature

## 1. Cùng là XML Digital Signature, nhưng ký dữ liệu ở đâu?

**XML Digital Signature (XMLDSig)** là định dạng chữ ký số thể hiện bằng XML. Nó cho phép kiểm tra dữ liệu được tham chiếu có thay đổi hay không và liệu chữ ký mật mã có được tạo bởi private key tương ứng với public key xác minh. **Để kết luận ai đã ký và người đó có quyền làm gì, ứng dụng còn phải kiểm tra danh tính/trust/ủy quyền của public key**. XMLDSig **không mã hóa nội dung**; dữ liệu đã ký thường vẫn đọc được.

Có ba bố cục thường gặp:

- **Enveloped signature**: phần tử `ds:Signature` được đặt **bên trong** phần XML mà nó ký.
- **Enveloping signature**: phần XML được ký được đặt **bên trong `ds:Object`**, còn `ds:Object` nằm trong `ds:Signature`.
- **Detached signature**: `ds:Signature` nằm **ngoài** phần dữ liệu nó ký. Dữ liệu có thể là một phần tử **anh em trong cùng document** hoặc **tệp/bytes bên ngoài**.

Đó là phân loại **về quan hệ giữa chữ ký và nội dung**, không phải ba thuật toán mật mã. Cả ba đều có thể sử dụng `DigestMethod.SHA256`, `SignatureMethod.RSA_SHA256` và các canonicalization/transforms phù hợp.

### Mục tiêu

Sau bài học, bạn có thể nhận diện đúng ba bố cục; hiểu `Reference` và phạm vi dữ liệu được bảo vệ; tạo/kiểm tra chữ ký XML bằng API JSR 105 trong Java 17+; dùng SHA-256 thay cho SHA-1 cũ; đăng ký ID attribute; khóa URI dereferencing nguy hiểm; hiểu XML Signature Wrapping; kiểm thử thay đổi dữ liệu được ký và dữ liệu **không được ký**; phân biệt core cryptographic validation với PKI trust, schema validation và business authorization.

## 2. API Java SE hiện hành, nguồn gốc Java 6

JSR 105 (Java XML Digital Signature API) xuất hiện từ **Java 6** và vẫn là API hiện hành trong **module `java.xml.crypto` của Java SE 26**. Ví dụ trong bài này dùng **Java 17+** và đã được biên dịch/chạy với `javac --release 17`.

| Thành phần | Vai trò |
| --- | --- |
| `XMLSignatureFactory.getInstance("DOM")` | Factory tạo/unmarshal XMLDSig theo DOM mechanism |
| `Reference` | URI chỉ tới data, transforms và digest của data |
| `DigestMethod` | Thuật toán băm cho dữ liệu mỗi Reference |
| `SignedInfo` | Chứa CanonicalizationMethod, SignatureMethod và các References |
| `SignatureMethod` | Thuật toán ký lên canonicalized SignedInfo |
| `CanonicalizationMethod` | Chuẩn hóa biểu diễn XML của SignedInfo |
| `Transform` | Xử lý nội dung Referenced data trước khi hash |
| `XMLSignature` | `sign` hoặc `validate` |
| `XMLObject` | Dữ liệu bên trong Signature của bố cục enveloping |
| `DOMStructure` | Bọc DOM Node cho nội dung XMLObject |
| `DOMSignContext` | Private key, vị trí Signature, đăng ký ID/resolver |
| `DOMValidateContext` | Trusted public key, Signature Node, ID/resolver, security policy |
| `URIDereferencer` | Quyết định dữ liệu lấy từ Reference URI |
| `OctetStreamData` | Input bytes cho external detached reference |
| `KeyInfo` | Metadata gợi ý vị trí key/certificate, **không tự chứng minh trust** |

Package của chữ ký là `javax.xml.crypto.dsig`, không phải `java.security.Signature` trực tiếp (dù JSR 105 dùng JCA engines bên dưới). API có thể làm việc với XML hoặc binary referenced data.

**Đúng lịch sử, vẫn dạy hiện hành:** `SignatureMethod.RSA_SHA256` có trong JDK 17+ (constant Javadoc từ Java 11), còn cú pháp Java text blocks và `List.of` là tính năng Java mới hơn Java 6. Vì vậy **không** khẳng định code chạy nguyên xi trên JDK 6; kiến thức XMLDSig bắt đầu từ Java 6 nhưng ứng dụng hiện đại nên build/run theo JDK đang được hỗ trợ.

## 3. Cấu trúc chung của một chữ ký XML

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="...">
      <ds:Transforms>...</ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <!-- ds:KeyInfo (tùy chọn) -->
  <!-- ds:Object (tùy chọn) -->
</ds:Signature>
~~~

Đây chỉ là **sơ đồ cấu trúc**, có dấu `...` minh họa, không phải chữ ký có thể validate. Namespace `http://www.w3.org/2000/09/xmldsig#` là định danh chính; prefix `ds` chỉ là alias.

### 3.1. Hai bước mật mã bắt buộc

**Digest verification:** với mỗi `Reference`, resolver xác định data được tham chiếu; áp dụng transforms theo thứ tự; băm bằng `DigestMethod`; so với `DigestValue`.

**Signature verification:** canonicalize `SignedInfo` theo `CanonicalizationMethod` rồi dùng `SignatureMethod` và public key đã tin cậy để kiểm tra `SignatureValue`.

`XMLSignature.validate(context)` thực hiện **core validation** hai mặt trên. Một Boolean `true` **không** có nghĩa tất cả nodes XML được bảo vệ hay mọi business rule đều đúng. Ứng dụng phải xác định chính xác **node/bytes nào được ký** và chỉ đọc dữ liệu nghiệp vụ **từ đối tượng đó** sau khi verify.

### 3.2. DigestMethod khác SignatureMethod

| Khái niệm | Ví dụ hiện đại | Chức năng |
| --- | --- | --- |
| `DigestMethod.SHA256` | SHA-256 | Hash nội dung mà Reference trỏ tới |
| `SignatureMethod.RSA_SHA256` | RSA/SHA-256 | Ký canonicalized SignedInfo bằng private key |
| `CanonicalizationMethod.EXCLUSIVE` | Exclusive XML Canonicalization | Chuẩn hóa SignedInfo trước ký |
| `Transform.ENVELOPED` | Enveloped transform | Loại chính Signature khỏi dữ liệu được hash |
| `CanonicalizationMethod.EXCLUSIVE` dạng Reference Transform | Exclusive C14N | Chuẩn hóa node-set XML được tham chiếu |

**Canonicalization không phải encryption.** Nó biến biểu diễn XML thành một dạng chuẩn theo thuật toán, không làm nội dung trở nên bí mật.

## 4. Enveloped: chữ ký ở trong phần tử được ký

~~~xml
<Invoice Id="invoice-42">
  <Amount>900</Amount>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <!-- SignedInfo/SignatureValue -->
  </ds:Signature>
</Invoice>
~~~

Đây là sơ đồ minh họa. `Invoice` là đối tượng được ký, còn `ds:Signature` nằm bên trong nó. Để tránh chữ ký bị bao gồm trong chính digest mà nó đang tính, Reference thường cần **`Transform.ENVELOPED`**.

### 4.1. Reference cho enveloped

~~~java
Reference reference = factory.newReference(
    "#invoice-42",
    factory.newDigestMethod(DigestMethod.SHA256, null),
    List.of(
        factory.newTransform(Transform.ENVELOPED,
            (TransformParameterSpec) null),
        factory.newTransform(CanonicalizationMethod.EXCLUSIVE,
            (TransformParameterSpec) null)),
    null, null);
~~~

Đây là **đoạn trích**, không phải file độc lập; `factory` là `XMLSignatureFactory`. Thứ tự transforms quan trọng: loại chữ ký trước, canonicalize sau. Một lựa chọn khác là `URI=""` để tham chiếu toàn document, nhưng fragment `#id` giúp application ràng buộc rõ đối tượng nghiệp vụ nếu ID được đăng ký/kiểm tra đúng.

### 4.2. Id trong DOM không tự được nhận là XML ID

~~~java
DOMSignContext ctx = new DOMSignContext(privateKey, invoice);
ctx.setIdAttributeNS(invoice, null, "Id");
~~~

Cần gắn attribute `Id` đúng element và đúng namespace vào signing context. Khi verify, `DOMValidateContext` cũng cần biết đúng ID ấy nếu parser/provider chưa tự xác định được kiểu ID. Dùng literal `Id` không có nghĩa DOM tự đảm bảo unique.

### 4.3. Ý nghĩa của tamper

Nếu ký `<Amount>900</Amount>` rồi sửa thành `901` thì Reference digest của Invoice phải fail. Nếu chỉ ký một subtree nhỏ, các phần XML khác không nằm trong Reference có thể bị sửa mà core validation vẫn true. **Luôn quyết định phạm vi ký dựa trên business contract**, không dựa vào việc mắt thấy Signature nằm trong file.

## 5. Enveloping: data nằm bên trong ds:Object của Signature

~~~xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:Reference URI="#object-42">...</ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
  <ds:Object Id="object-42">
    <Message>Signed in ds:Object</Message>
  </ds:Object>
</ds:Signature>
~~~

Đây là minh họa hình dạng, chưa có chữ ký hợp lệ. Phần `Message` được bọc bởi `ds:Object`, và `Reference` chỉ tới **Object có ID cụ thể**. Không sử dụng `Transform.ENVELOPED` trong Reference tới Object vì Signature không nằm **bên trong Object**.

### 5.1. XMLObject trong Java

~~~java
XMLObject object = factory.newXMLObject(
    List.of(new DOMStructure(payloadElement)),
    "object-42", null, null);
Reference reference = factory.newReference(
    "#object-42",
    factory.newDigestMethod(DigestMethod.SHA256, null),
    List.of(factory.newTransform(CanonicalizationMethod.EXCLUSIVE,
        (TransformParameterSpec) null)),
    null, null);
XMLSignature signature = factory.newXMLSignature(
    signedInfo, null, List.of(object), "sig-42", null);
~~~

Đây là **đoạn trích** với các biến `factory`, `payloadElement` và `signedInfo` đã được khởi tạo. Trong code runnable ở mục 9, XMLObject có `Id="object-42"` và chứa `Message`, còn Signature là root document.

### 5.2. Đừng nhầm Object với toàn bộ nội dung nghiệp vụ

`ds:Object` có thể chứa XML, arbitrary data hoặc cấu trúc như `Manifest`. **Core validation** không tự cho phép ứng dụng giả định mọi thứ bên trong Signature đều là payload đã ký nếu Reference trỏ tới một đối tượng khác. Đặc biệt, Manifest references có quy tắc validation riêng; trong JDK, property `org.jcp.xml.dsig.validateManifests` ảnh hưởng việc kiểm tra chúng, mặc định false. Ví dụ của bài **không dùng Manifest**.

Enveloping thường thuận tiện khi muốn phân phối một **gói XML Signature mang chính payload**. Với dữ liệu lớn, DOM XMLObject có thể tốn heap; detached external có thể phù hợp hơn nếu kèm thiết kế storage/resolver an toàn.

## 6. Detached: chữ ký nằm ngoài dữ liệu được ký

### 6.1. Same-document detached: hai phần tử anh em

~~~xml
<Bundle>
  <Payload Id="payload-42">important</Payload>
  <UnsignedNote>original</UnsignedNote>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:Reference URI="#payload-42">...</ds:Reference>
    </ds:SignedInfo>
  </ds:Signature>
</Bundle>
~~~

`Payload` và `ds:Signature` là **sibling elements** trong `Bundle`. Theo W3C, đây **vẫn là detached**, dù XML chỉ có một file. Data được Reference bảo vệ là **Payload**, không phải toàn bộ Bundle.

Khi ký đúng Payload:

- Sửa `Payload` → verify **false**.
- Sửa `UnsignedNote` → verify **vẫn true**, vì note **ngoài phạm vi được ký**.
- Không cần `Transform.ENVELOPED`, vì Signature không nằm trong Payload.
- Ứng dụng **không được dựa vào UnsignedNote làm dữ liệu đã được phê duyệt**; nếu quan trọng, phải đưa note vào phạm vi ký hoặc có cơ chế xác thực khác.

### 6.2. External detached: signature và dữ liệu tách riêng

~~~text
Data riêng:      invoice=42;amount=900
Signature XML:   <ds:Signature><ds:SignedInfo><ds:Reference
                   URI="urn:lesson:payload:42"/> ...</ds:SignedInfo>...</ds:Signature>
~~~

Đây là **sơ đồ text**, không phải XML signature hoàn chỉnh. Signature nằm trong một tài liệu riêng; `Reference URI` trỏ tới data có thể là **binary bytes**, XML file hoặc một content object của storage.

Một chữ ký external detached đúng sẽ fail nếu bytes nhận được khi verify không còn đúng bytes đã được hash khi sign. Với dữ liệu ngoài dạng **octet stream**, thay đổi một byte, newline hoặc encoding có thể thay digest. Nếu muốn canonicalize external XML thay vì ký exact bytes, cần quy định transforms/c14n chung cho cả hai bên.

### 6.3. Không để URI tự dẫn tới mạng và file tùy ý

`Reference URI` nằm trong XML có thể do người khác cung cấp. Nếu cho library tự tải `http://`, `https://` hoặc `file://`, application có thể bị SSRF, đọc private files, đọc cloud metadata hoặc tiêu tốn băng thông.

Trong Java hiện đại, dùng `URIDereferencer` có **allowlist URI** và nội dung do **nguồn đáng tin/được ủy quyền** cung cấp. Ví dụ runnable mục 10 chỉ cho `urn:lesson:payload:42` và trả `OctetStreamData` từ mảng bytes an toàn; không tạo network request.

## 7. Ký và verify phải nối với phạm vi dữ liệu nghiệp vụ

### 7.1. Luồng tạo chữ ký

~~~text
Chọn đúng business element / byte content
       |
       v
Tạo Reference URI + Transforms + DigestMethod
       |
       v
Hash từng Reference -> DigestValue
       |
       v
Tạo SignedInfo (C14N, SignatureMethod, references)
       |
       v
Ký SignedInfo bằng trusted PrivateKey
       |
       v
Gắn ds:Signature vào vị trí phù hợp bố cục
~~~

`XMLSignatureFactory.newXMLSignature` chỉ xây dựng cấu trúc; `XMLSignature.sign(DOMSignContext)` mới thực sự tính digest, SignatureValue và chèn XML vào DOM. `DOMSignContext` có private key, parent node, ID registry và tùy chọn URI resolver.

### 7.2. Luồng xác minh

~~~text
Parse XML có khóa DTD/XXE, size/depth limits
       |
       v
Chọn đúng ds:Signature ở vị trí được chấp nhận
       |
       v
Tạo DOMValidateContext(trusted PublicKey, Signature Node)
       |
       v
Bật secureValidation, đăng ký ID, URI allowlist
       |
       v
Unmarshal, kiểm tra Reference URI/count/transforms/algorithms
       |
       v
XMLSignature.validate(context)
       |
       +-- SignatureValue check trên SignedInfo
       |
       +-- Digest checks của từng Reference
       |
       v
Chỉ dùng đúng business node/bytes đã được xác minh
       |
       v
Thực hiện thêm kiểm tra PKI trust, authorization, schema
~~~

**Một boolean `validate()==true` không có nghĩa một node XML tùy ý khác cũng đã được ký.** Ví dụ hệ thống ký `<Invoice Id="original">` nhưng sau đó đọc `//Invoice` khác chưa ký có thể bị **XML Signature Wrapping**.

### 7.3. Khóa tin cậy: public key không phải chỉ lấy từ KeyInfo

Hai chương trình mẫu sinh RSA `KeyPair` tạm và verify bằng `keys.getPublic()` từ **nguồn độc lập**, tức chính fixture. Chúng **không cung cấp PKI production**. Thực tế phải:

- Lấy public key/certificate theo trust store, PKIX path validation, issuer, expiration, revocation/status, key usage và policy.
- Kiểm tra signer đó có **quyền ký loại tài liệu/nghiệp vụ** tương ứng.
- Giữ private key trong KeyStore/HSM/key management system, không hardcode hoặc log.
- Xử lý key rotation, audit, timestamp, long-term verification.
- Không coi một `KeyInfo` do attacker đính kèm là bằng chứng chứng thư hoặc signer trusted: bất cứ ai cũng có thể tự sinh key và tạo một chữ ký crypto hợp lệ với chính key của họ.

### 7.4. Cả XML schema lẫn signature đều cần

Một XML hợp chữ ký số có thể vẫn chứa amount âm, customer ID sai, hoặc thông tin không được phép; cần XSD/domain validation và authorization. Ngược lại XML hợp XSD không chứng minh nội dung không bị sửa. Signature không cung cấp confidentiality; nếu cần bí mật dùng TLS/encryption theo thiết kế.

## 8. Thuật toán còn phù hợp và secure validation

Ví dụ sử dụng:

- `DigestMethod.SHA256` — hash Reference.
- `SignatureMethod.RSA_SHA256` — ký canonicalized SignedInfo.
- RSA **3072 bits** — key sinh tạm cho fixture.
- `CanonicalizationMethod.EXCLUSIVE`.
- Enveloped reference: `Transform.ENVELOPED` rồi exclusive canonicalization.
- Enveloping và detached sibling: exclusive canonicalization, **không** cần enveloped transform.

Không dùng `RSA_SHA1`, `DSA_SHA1`, MD5/SHA-1 signatures cho ứng dụng mới. Các thuật toán ECDSA-SHA256, RSA-PSS hoặc EdDSA có thể phù hợp với môi trường/hạ tầng hiện đại nếu **JDK/nhà cung cấp và đối tác** hỗ trợ cùng chuẩn, không lựa chọn chỉ dựa vào sở thích.

### 8.1. C14N không làm mọi thay đổi XML vô hại

Exclusive C14N chuẩn hóa theo quy tắc, nhưng thay đổi text nodes, significant whitespace, namespace scope, transform order, ID typing hoặc bytes bên ngoài vẫn có thể phá chữ ký. Không parse-serialize XML đã ký rồi mong byte-identical. Nếu muốn xác nhận **XML semantic equality** cần chính sách canonicalization phù hợp, đặc biệt với namespace và detached external payload.

### 8.2. Secure validation của JDK

`DOMValidateContext` hỗ trợ:

~~~java
ctx.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
~~~

Trong JDK hiện đại, secure validation **mặc định bật**. Oracle Java SE 26 mô tả các hạn chế mặc định đối với XMLDSig verification:

- Cấm XSLT transforms trong chữ ký.
- Giới hạn số `Reference` và transforms.
- Cấm MD5/SHA-1 signature và MAC MD5.
- Chống duplicate Reference IDs và retrieval-method loops.
- Không cho external `http/https/file` Reference URIs.
- Kiểm soát độ dài khóa tối thiểu, phụ thuộc `jdk.xml.dsig.secureValidationPolicy`.
- Những policy chi tiết có thể thay đổi theo JDK version; ngoài ra JDK 26 có cập nhật liên quan XPath transform policies.

**System property** `org.jcp.xml.dsig.secureValidation` nếu có sẽ **ưu tiên per-context property**. Vì vậy production cần kiểm tra JVM configuration; không giải quyết incompatibility bằng cách vô hiệu hóa secure validation.

Một **XSLT transform bên trong ds:Reference** (bị chính sách hạn chế) khác với một chương trình Java dùng XSLT ngoài quy trình chữ ký để chuyển đổi XML ở bước độc lập. Không nới lỏng policy chữ ký để dùng XSLT cho mục đích khác.

## 9. Java 17+ runnable: ba kiểu XMLDSig, verify và tamper tests

File `XmlSignatureShapesDemo.java` được biên dịch và chạy thành công trên OpenJDK 24 với target Java 17. Nó tạo các tài liệu DOM nội bộ, sign RSA-SHA256, verify với `DOMValidateContext`, ràng buộc đúng `Reference URI` và kiểm tra sửa dữ liệu sau khi ký.

- **Enveloped:** Signature bên trong `Invoice Id="invoice-42"`, reference có enveloped transform.
- **Enveloping:** Signature root chứa `ds:Object Id="object-42"` và `Message`.
- **Detached sibling:** Signature và `Payload Id="payload-42"` nằm cùng `Bundle`; `UnsignedNote` không nằm trong reference.
- Khi sửa signed data, verify trả false; khi sửa riêng unsigned sibling, verify vẫn true.

**Giới hạn:** demo dùng DOM và private key tạm, không có KeyStore/PKI/certificate; không phải hệ thống chống XML Signature Wrapping đầy đủ. XML parser trong demo tạo document mới, không đọc file không tin cậy.

### 9.1. File XmlSignatureShapesDemo.java

~~~java
import java.security.*;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.crypto.dom.DOMStructure;
import javax.xml.crypto.dsig.*;
import javax.xml.crypto.dsig.dom.*;
import javax.xml.crypto.dsig.spec.*;
import javax.xml.parsers.*;
import org.w3c.dom.*;

public final class XmlSignatureShapesDemo {
    private static final XMLSignatureFactory FAC = XMLSignatureFactory.getInstance("DOM");
    private static final String DATA_ID = "invoice-42";
    private static final String OBJECT_ID = "object-42";
    private static final String DETACHED_ID = "payload-42";

    private static Document newDoc() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        f.setFeature("http://xml.org/sax/features/external-general-entities", false);
        f.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return f.newDocumentBuilder().newDocument();
    }

    private static Element element(Document doc, String tag, String text) {
        Element el = doc.createElement(tag);
        if (text != null) el.setTextContent(text);
        return el;
    }

    private static Reference ref(String uri, List<Transform> transforms)
            throws Exception {
        return FAC.newReference(uri,
                FAC.newDigestMethod(DigestMethod.SHA256, null),
                transforms, null, null);
    }

    private static Transform transform(String algorithm) throws Exception {
        return FAC.newTransform(algorithm, (TransformParameterSpec) null);
    }

    private static SignedInfo info(Reference reference) throws Exception {
        return FAC.newSignedInfo(
                FAC.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                FAC.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(reference));
    }

    private static Element oneSignature(Document doc) {
        NodeList signatures = doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1)
            throw new IllegalArgumentException("Expected exactly one Signature");
        return (Element) signatures.item(0);
    }

    private static boolean verify(Document doc, PublicKey trustedKey,
                                  String expectedReference, Element signedElement)
            throws Exception {
        DOMValidateContext ctx = new DOMValidateContext(trustedKey, oneSignature(doc));
        ctx.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        if (signedElement != null)
            ctx.setIdAttributeNS(signedElement, null, "Id");
        XMLSignature signature = FAC.unmarshalXMLSignature(ctx);
        List<?> refs = signature.getSignedInfo().getReferences();
        if (refs.size() != 1) return false;
        Reference actual = (Reference) refs.get(0);
        if (!expectedReference.equals(actual.getURI())) return false;
        return signature.validate(ctx);
    }

    private static Document enveloped(KeyPair keys) throws Exception {
        Document doc = newDoc();
        Element invoice = element(doc, "Invoice", null);
        invoice.setAttribute("Id", DATA_ID);
        invoice.appendChild(element(doc, "Amount", "900"));
        doc.appendChild(invoice);

        Reference reference = ref("#" + DATA_ID,
                List.of(transform(Transform.ENVELOPED),
                        transform(CanonicalizationMethod.EXCLUSIVE)));
        XMLSignature signature = FAC.newXMLSignature(info(reference), null);
        DOMSignContext context = new DOMSignContext(keys.getPrivate(), invoice);
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(invoice, null, "Id");
        signature.sign(context);
        return doc;
    }

    private static Document enveloping(KeyPair keys) throws Exception {
        Document doc = newDoc();
        Element payload = element(doc, "Message", "Signed in ds:Object");
        XMLObject object = FAC.newXMLObject(
                List.of(new DOMStructure(payload)), OBJECT_ID, null, null);
        Reference reference = ref("#" + OBJECT_ID,
                List.of(transform(CanonicalizationMethod.EXCLUSIVE)));
        XMLSignature signature = FAC.newXMLSignature(
                info(reference), null, List.of(object), "sig-42", null);
        DOMSignContext context = new DOMSignContext(keys.getPrivate(), doc);
        context.setDefaultNamespacePrefix("ds");
        signature.sign(context);
        return doc;
    }

    private static Document detachedSibling(KeyPair keys) throws Exception {
        Document doc = newDoc();
        Element bundle = element(doc, "Bundle", null);
        doc.appendChild(bundle);
        Element payload = element(doc, "Payload", "important");
        payload.setAttribute("Id", DETACHED_ID);
        bundle.appendChild(payload);
        bundle.appendChild(element(doc, "UnsignedNote", "original"));

        Reference reference = ref("#" + DETACHED_ID,
                List.of(transform(CanonicalizationMethod.EXCLUSIVE)));
        XMLSignature signature = FAC.newXMLSignature(info(reference), null);
        DOMSignContext context = new DOMSignContext(keys.getPrivate(), bundle);
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(payload, null, "Id");
        signature.sign(context);
        return doc;
    }

    private static void check(boolean condition, String what) {
        if (!condition) throw new AssertionError(what);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair keys = generator.generateKeyPair();

        Document env = enveloped(keys);
        Element invoice = env.getDocumentElement();
        check(invoice.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature")
                .getLength() == 1, "Signature not nested under Invoice");
        check(verify(env, keys.getPublic(), "#" + DATA_ID, invoice), "enveloped");
        System.out.println("enveloped-valid=true");
        ((Element) invoice.getElementsByTagName("Amount").item(0))
                .setTextContent("901");
        check(!verify(env, keys.getPublic(), "#" + DATA_ID, invoice),
                "enveloped mutation should fail");
        System.out.println("enveloped-tamper-detected=true");

        Document objDoc = enveloping(keys);
        Element signatureRoot = objDoc.getDocumentElement();
        check(XMLSignature.XMLNS.equals(signatureRoot.getNamespaceURI()),
                "Expected ds:Signature document root");
        check(signatureRoot.getElementsByTagNameNS(XMLSignature.XMLNS, "Object")
                .getLength() == 1, "Object not nested under signature");
        check(verify(objDoc, keys.getPublic(), "#" + OBJECT_ID, null),
                "enveloping");
        System.out.println("enveloping-valid=true");
        ((Element) objDoc.getElementsByTagName("Message").item(0))
                .setTextContent("changed");
        check(!verify(objDoc, keys.getPublic(), "#" + OBJECT_ID, null),
                "enveloping mutation should fail");
        System.out.println("enveloping-tamper-detected=true");

        Document detDoc = detachedSibling(keys);
        Element bundle = detDoc.getDocumentElement();
        Element payload = (Element) bundle.getElementsByTagName("Payload").item(0);
        check(bundle.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature")
                .getLength() == 1, "missing sibling signature");
        check(verify(detDoc, keys.getPublic(), "#" + DETACHED_ID, payload),
                "detached sibling");
        System.out.println("detached-sibling-valid=true");
        ((Element) bundle.getElementsByTagName("UnsignedNote").item(0))
                .setTextContent("different");
        check(verify(detDoc, keys.getPublic(), "#" + DETACHED_ID, payload),
                "unsigned sibling should not be covered");
        System.out.println("unsigned-sibling-can-change=true");
        payload.setTextContent("tampered");
        check(!verify(detDoc, keys.getPublic(), "#" + DETACHED_ID, payload),
                "detached payload mutation should fail");
        System.out.println("detached-payload-tamper-detected=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Biên dịch/chạy và stdout đã kiểm chứng

~~~bash
javac -encoding UTF-8 --release 17 XmlSignatureShapesDemo.java
java XmlSignatureShapesDemo
~~~

Stdout **chính xác**, chạy thành công trên OpenJDK 24 với `--release 17`:

~~~text
enveloped-valid=true
enveloped-tamper-detected=true
enveloping-valid=true
enveloping-tamper-detected=true
detached-sibling-valid=true
unsigned-sibling-can-change=true
detached-payload-tamper-detected=true
tests=PASS
~~~

Giải thích:

- Enveloped và enveloping đều `valid=true` với dữ liệu không đổi và `tamper-detected=true` sau thay đổi phần **đã ký**.
- Detached sibling `valid=true` khi Signature và Payload là **sibling** (không phải signature bên trong Payload).
- `unsigned-sibling-can-change=true` là **điểm bảo mật quan trọng**: thay metadata nằm ngoài Reference thì chữ ký vẫn hợp lệ.
- `detached-payload-tamper-detected=true` xác nhận chính Payload được Reference trỏ tới được bảo vệ.
- `tests=PASS` chỉ chứng minh implementation/provider JDK trong môi trường test cho những fixtures cụ thể, **không** khẳng định hệ thống có PKI/trust hoặc anti-wrapping đầy đủ.

## 10. Java 17+ runnable: external detached và URIDereferencer giới hạn

`XmlExternalDetachedDemo.java` là ví dụ độc lập thứ hai. Chữ ký nằm **trong một DOM document chỉ chứa Signature**, còn dữ liệu là **bytes được cung cấp riêng**.

- URI logic cố định: `urn:lesson:payload:42`.
- `URIDereferencer` clone bytes, từ chối URI khác và trả `OctetStreamData`.
- Không tự tải HTTP, HTTPS hay file.
- Dữ liệu gốc verify true; thay amount từ 900 thành 901 verify false.
- Test URI không nằm trong allowlist bị `URIReferenceException`.

### 10.1. File XmlExternalDetachedDemo.java

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.xml.crypto.*;
import javax.xml.crypto.dsig.*;
import javax.xml.crypto.dsig.dom.*;
import javax.xml.crypto.dsig.spec.*;
import javax.xml.parsers.*;
import org.w3c.dom.*;

public final class XmlExternalDetachedDemo {
    private static final String SAFE_URI = "urn:lesson:payload:42";
    private static final XMLSignatureFactory FAC =
            XMLSignatureFactory.getInstance("DOM");

    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    static Document blankDocument() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        return f.newDocumentBuilder().newDocument();
    }

    static URIDereferencer exactBytes(byte[] content) {
        byte[] immutableCopy = content.clone();
        return (uriReference, context) -> {
            if (!SAFE_URI.equals(uriReference.getURI())) {
                throw new URIReferenceException("URI not on the explicit allowlist");
            }
            return new OctetStreamData(
                    new ByteArrayInputStream(immutableCopy),
                    SAFE_URI, "application/octet-stream");
        };
    }

    static Document sign(byte[] content, PrivateKey key) throws Exception {
        Document doc = blankDocument();
        Reference ref = FAC.newReference(SAFE_URI,
                FAC.newDigestMethod(DigestMethod.SHA256, null));
        SignedInfo info = FAC.newSignedInfo(
                FAC.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                FAC.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(ref));
        XMLSignature signature = FAC.newXMLSignature(info, null);
        DOMSignContext ctx = new DOMSignContext(key, doc);
        ctx.setDefaultNamespacePrefix("ds");
        ctx.setURIDereferencer(exactBytes(content));
        signature.sign(ctx);
        return doc;
    }

    static boolean verify(Document doc, byte[] content, PublicKey trustedKey)
            throws Exception {
        NodeList signatures = doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1)
            throw new IllegalArgumentException("Expected exactly one signature");
        DOMValidateContext ctx = new DOMValidateContext(
                trustedKey, signatures.item(0));
        ctx.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        ctx.setURIDereferencer(exactBytes(content));
        XMLSignature signature = FAC.unmarshalXMLSignature(ctx);
        List<?> references = signature.getSignedInfo().getReferences();
        check(references.size() == 1, "unexpected Reference count");
        check(SAFE_URI.equals(((Reference) references.get(0)).getURI()),
                "wrong signed reference URI");
        return signature.validate(ctx);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(3072);
        KeyPair keys = g.generateKeyPair();

        byte[] original = "invoice=42;amount=900".getBytes(
                StandardCharsets.UTF_8);
        Document signatureOnly = sign(original, keys.getPrivate());
        check(signatureOnly.getDocumentElement().getLocalName()
                .equals("Signature"), "signature should be separate");
        check(verify(signatureOnly, original, keys.getPublic()), "original");
        System.out.println("external-detached-valid=true");

        byte[] changed = "invoice=42;amount=901".getBytes(
                StandardCharsets.UTF_8);
        check(!verify(signatureOnly, changed, keys.getPublic()),
                "changed bytes must invalidate reference");
        System.out.println("changed-payload-invalid=true");

        try {
            exactBytes(original).dereference(
                    new URIReference() {
                        @Override public String getURI() {
                            return "https://forbidden.example/file.xml";
                        }
                        @Override public String getType() { return null; }
                    }, null);
            throw new AssertionError("Non-allowlisted URI accepted");
        } catch (URIReferenceException expected) {
            System.out.println("unlisted-uri-rejected=true");
        }
        System.out.println("tests=PASS");
    }
}
~~~

### 10.2. Biên dịch/chạy và stdout đã kiểm chứng

~~~bash
javac -encoding UTF-8 --release 17 XmlExternalDetachedDemo.java
java XmlExternalDetachedDemo
~~~

Stdout **chính xác** trên OpenJDK 24 với `--release 17`:

~~~text
external-detached-valid=true
changed-payload-invalid=true
unlisted-uri-rejected=true
tests=PASS
~~~

Giải thích:

- `external-detached-valid=true`: XML Signature tham chiếu dữ liệu ngoài qua URI logic, resolver trả đúng bytes, cả digest và SignedInfo đúng.
- `changed-payload-invalid=true`: một thay đổi trong exact bytes làm hash mismatch, dù Signature XML không đổi.
- `unlisted-uri-rejected=true`: resolver **không** chấp nhận URL HTTPS do người khác chỉ định.
- `tests=PASS`: hai phép verify và kiểm tra URI allowlist đã đúng trên fixture.

**Không suy rộng:** demo dùng `byte[]` trong bộ nhớ và khóa RSA tự sinh, không phải storage service hay PKI production. Với file lớn, resolver có thể đọc từ stream đã được ủy quyền và giới hạn bytes; còn `blankDocument()` chỉ tạo document rỗng, **không dùng để parse XML untrusted**. Nguồn content phải được khóa theo URI/version và tránh TOCTOU khi dữ liệu đổi sau verify.

## 11. XML Signature Wrapping: verify đúng chữ ký nhưng đọc sai dữ liệu

Giả sử XML có hai phần giống tên:

~~~xml
<Envelope>
  <SignedInvoice Id="original">
    <Amount>100</Amount>
  </SignedInvoice>
  <Invoice>
    <Amount>9999</Amount>
  </Invoice>
  <!-- Chữ ký hợp lệ chỉ trỏ tới #original -->
</Envelope>
~~~

Đây chỉ là XML minh họa, **chưa có SignatureValue thật**. Nếu code crypto verify `#original`, nhưng xử lý thanh toán bằng XPath `//Invoice` hoặc element đầu/element cuối không được verify, attacker có thể đạt `validate()==true` trong khi business dùng data **chưa ký**.

Để tránh:

1. Hạn chế document schema/root/namespaces và nơi Signature được phép xuất hiện.
2. Kiểm tra **số lượng Signature** như business contract yêu cầu; không tự lấy signature đầu tiên khi có nhiều signatures.
3. Kiểm tra **số lượng và URI của References** đúng expected payload IDs.
4. Đăng ký ID đúng element/namespace và **kiểm tra ID duy nhất**; tránh trùng `Id` và những alias mơ hồ.
5. Dùng **chính xác Element/bytes đã xác minh** cho business processing; không tìm lại theo tag name rộng.
6. Allowlist thuật toán/canonicalization/transforms, không tin mọi transform chain được đưa từ bên ngoài.
7. Xác minh trusted public key/certificate path và signer authorization.
8. Không coi unsigned sibling fields là authenticated.
9. Xem xét Manifest/KeyInfo/Reference interactions đúng policy và giới hạn URI dereferencing.
10. Viết adversarial tests cho duplicate IDs, signature wrapping, nested signatures, Unicode/namespace confusion.

Code runnable kiểm tra số Signature = 1, expected Reference URI và đăng ký IDs cho ví dụ đơn giản. **Đó chưa phải verifier production hoàn chỉnh** vì chưa implement đầy đủ schema/path policy, duplicate-ID scanning hoặc PKIX trust.

## 12. Quy trình bảo mật XML đầu vào

Nếu bạn nhận XML Signature từ người khác, bước **parse DOM** phải được cấu hình phòng XXE và resource exhaustion **trước khi JSR 105 unmarshal**:

~~~java
DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
factory.setNamespaceAware(true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setFeature(
    "http://xml.org/sax/features/external-general-entities", false);
factory.setFeature(
    "http://xml.org/sax/features/external-parameter-entities", false);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Đây là **đoạn trích** của factory configuration, không phải toàn bộ parser. Khi tạo `DocumentBuilder` để parse InputStream, phải đóng input; với untrusted XML, nếu provider không hỗ trợ cài đặt bắt buộc, **fail closed** chứ không nuốt lỗi và parse tiếp. Ngoài ra còn cần giới hạn **tổng bytes, depth, text, entity expansion, timeout, concurrent requests**.

Không tự cho phép giải quyết external URI chỉ vì Signature XML có Reference URL. Với detached, dùng resolver có scope riêng; không lấy URI như một URL tải được trực tiếp từ client.

## 13. Chẩn đoán lỗi chữ ký và giới hạn cache validation

`XMLSignature.validate(context)` có thể trả `false` hoặc ném `XMLSignatureException` cho lỗi xử lý. Có thể kiểm tra:

~~~java
boolean signatureValueOk =
    xmlSignature.getSignatureValue().validate(validateContext);

for (Object item : xmlSignature.getSignedInfo().getReferences()) {
    Reference ref = (Reference) item;
    boolean digestOk = ref.validate(validateContext);
    System.out.println("uri=" + ref.getURI()
        + " digestOk=" + digestOk);
}
~~~

**Đoạn trích** cần `xmlSignature` đã được unmarshal và `validateContext` đã có key/IDs/resolver. Chú ý Javadoc: `XMLSignature.validate` và `Reference.validate` **cache kết quả của lần kiểm tra đầu tiên** trên đối tượng; vì vậy **không** sửa DOM rồi gọi lại cùng XMLSignature instance/context để mong kiểm chứng thay đổi. Mỗi test tamper nên **unmarshal lại** với context mới, như hai chương trình đã làm.

Các lỗi cần phân loại:

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `#Id` không resolve | DOM chưa nhận attribute kiểu ID | `setIdAttributeNS` đúng element/namespace |
| Enveloped verify fail | Thiếu ENVELOPED transform hoặc dữ liệu bị sửa | Chọn transforms đúng thứ tự |
| Enveloping verify fail | `XMLObject Id` và Reference mismatch | Kiểm tra object được tham chiếu |
| Detached sibling note đổi mà vẫn true | Note ngoài phạm vi ký | Bảo vệ/không dùng trường unsigned |
| Detached external digest fail | Bytes/encoding/version thay đổi | Ràng buộc đúng bytes và storage version |
| Verify true với key của attacker | Sai key trust, tự chấp nhận KeyInfo | PKIX/trust store/authorization |
| SHA-1 signature bị từ chối | Secure validation policy | Chuyển sang thuật toán còn an toàn |
| Duplicate IDs | Signature wrapping risk | Reject theo schema/policy |
| `XMLSignatureException` | URI/transform/provider/key issues | Inspect cause chain và policy |
| DTD/XXE | Parser chưa khóa external refs | Fail closed, secure parsing |
| Heap tăng | DOM/materialization/external byte arrays | Giới hạn input/memory và benchmark |

## 14. Chọn bố cục theo nghiệp vụ

| Yêu cầu | Cân nhắc |
| --- | --- |
| XML tài liệu phải tự chứa chữ ký bên trong | Enveloped |
| Muốn truyền một gói XML Signature chứa chính payload | Enveloping với `ds:Object` |
| Payload và Signature là sibling trong một envelope | Detached same-document |
| Muốn ký file/bytes không đưa vào Signature XML | Detached external |
| Chỉ một số fields cần bảo vệ | Bắt buộc khai báo scope/Reference rõ ràng; không dùng unsigned fields cho quyết định an ninh |
| Ký nhiều XML nodes | Nhiều References và policy validation rõ; xem giới hạn secure validation |
| Dữ liệu rất lớn | Có thể tách detached external, giới hạn resolver buffers; DOM XMLDSig vẫn có overhead |
| Cần xác định người ký | PKIX/trust store + certificate/authorization, không chỉ KeyInfo |
| Nội dung cần bí mật | TLS/encryption riêng; XML Signature không mã hóa |

### 14.1. Detached không đồng nghĩa ký “tất cả”

Detached thường chỉ ký đúng resource được Reference chỉ đến. Nếu envelope chứa `Payload` cùng `AmountOverride` hoặc `UnsignedNote`, application phải **không** dùng dữ liệu chưa ký làm nguồn sự thật. Khi cần bảo vệ toàn bundle, ký đúng root/bộ References hoặc chuyển bố cục theo contract.

### 14.2. Không dùng raw output XML serialization làm thước đo

XML canonicalization và transforms có thể thay đổi cách serialize namespace prefixes, attribute order hoặc whitespace; so sánh raw XML byte-for-byte dễ thất bại dù XML có cùng ý nghĩa. Với detached external binary octets, ngược lại, **exact bytes** mới là điều digest bảo vệ nếu không có XML transforms.

## 15. Integration tests cần thực hiện trên sản phẩm thực

| Trường hợp | Kết quả cần xác minh |
| --- | --- |
| Enveloped không sửa | Verify true, đúng Signature position |
| Enveloped đổi signed amount | Verify false |
| Enveloped thiếu ENVELOPED transform | Fail hoặc không đáp ứng signature contract |
| Enveloping Object Id đúng | Verify true |
| Enveloping sửa Object | Verify false |
| Detached sibling đúng URI | Verify true |
| Detached sửa unsigned sibling | Verify vẫn true; app **không tin** trường này |
| Detached sửa Payload | Verify false |
| External detached bytes nguyên bản | Verify true |
| External detached đổi 1 byte | Verify false |
| Unknown URI, file/http/https | Bị chặn, không SSRF/file read |
| Public key sai | Signature false |
| KeyInfo giả | Không tự coi signer trusted |
| Duplicate IDs/Signature | Reject anti-wrapping policy |
| Reference trỏ node không đúng business object | Reject |
| Malformed XML/DOCTYPE/XXE | Parser từ chối |
| Unsupported/legacy algorithms | Reject theo policy |
| Too many references/transforms | SecureValidation/quotas chặn |
| XML lớn | Memory, CPU, concurrent quotas hợp SLA |
| JDK/provider upgrade | Policy và interoperability verified |
| Business authorization | Chỉ signer phù hợp được chấp nhận |

## 16. Tự đánh giá và bài tập

**1.** Enveloped và enveloping khác nhau thế nào?

**Đáp án:** Enveloped có Signature nằm trong phần XML được ký; enveloping có data nằm trong `ds:Object` thuộc Signature.

**2.** Detached có luôn là chữ ký trong file khác không?

**Đáp án:** Không. Signature và Payload là sibling trong cùng XML vẫn là detached.

**3.** Enveloped phải loại gì trước khi hash?

**Đáp án:** Phần tử Signature đang nằm trong nội dung được ký, bằng `Transform.ENVELOPED` hoặc kỹ thuật transform thích hợp.

**4.** Tại sao phải đăng ký attribute Id trong DOM?

**Đáp án:** Chuỗi tên `Id` không tự biến nó thành XML ID có thể resolve bằng `#fragment`. Cần typing/registration và đảm bảo uniqueness.

**5.** Nếu sửa `UnsignedNote` trong detached sibling, chữ ký có fail không?

**Đáp án:** Không nếu Reference chỉ ký Payload. Điều này cảnh báo mọi unsigned data đều có thể bị thay đổi.

**6.** `DigestMethod` có phải RSA signing method?

**Đáp án:** Không. Digest SHA-256 hash Reference; SignatureMethod RSA-SHA256 ký SignedInfo.

**7.** Verify true có chứng minh signer được doanh nghiệp tin cậy?

**Đáp án:** Không. Cần PKI/trust/authorization ngoài core signature verification.

**8.** Tại sao không tự mở `Reference URI="file:///..."`?

**Đáp án:** File/network dereferencing từ chữ ký không tin cậy có thể gây SSRF/local-file access; dùng allowlist URIDereferencer.

**9.** SHA-1 signatures có phù hợp hệ thống mới không?

**Đáp án:** Không. Chọn thuật toán được hỗ trợ và an toàn theo policy, như RSA-SHA256; JDK secure validation có hạn chế SHA-1 signatures.

**10.** XML Signature Wrapping là gì?

**Đáp án:** Verify dữ liệu A có ký nhưng business layer dùng dữ liệu B chưa ký; cần ràng buộc đúng business node.

**11.** XML signature có che nội dung không?

**Đáp án:** Không, muốn confidentiality phải dùng encryption/TLS riêng.

**12.** Vì sao không validate nhiều lần trên cùng XMLSignature instance sau khi đổi DOM?

**Đáp án:** JSR 105 có caching kết quả validation; cần unmarshal context mới cho kiểm thử tamper.

### Bài tập mở rộng

1. Chạy `XmlSignatureShapesDemo` và giải thích từng dòng `tests=PASS`.
2. Thay `Amount` rồi kiểm tra Reference digest bị sai.
3. Bỏ `Transform.ENVELOPED` trong một test riêng để tìm hiểu điều kiện enveloped signature.
4. Đổi `XMLObject Id` nhưng giữ Reference cũ, kiểm tra lỗi.
5. Tạo hai `Payload` có cùng `Id` để kiểm tra wrapping/duplicate-ID policy.
6. Thêm trường unsigned quan trọng vào Bundle, kiểm tra nó có thể bị sửa mà verify vẫn true.
7. Đổi verify public key sang key khác và xác nhận fail.
8. Thử external detached data có newline/encoding khác và phân tích digest.
9. Viết allowlist resolver đọc file từ thư mục được phép, có path/size/time constraints.
10. Bổ sung certificate validation/trust store cho signer thật.
11. Kiểm thử qua hai JDK/providers và chính sách security khác nhau.
12. Thiết kế verifier trả đúng **verified payload Element** thay vì boolean thuần.
13. Thử lớn hơn 100 MB với detached external streaming và đo heap/GC.
14. Định nghĩa signed business data vs unsigned metadata trong contract XML.
15. Thiết kế pipeline lưu chữ ký + timestamp/audit + revision/immutability.

## 17. Tài liệu hiện hành

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html).
- [Oracle Java SE 26 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html).
- [Oracle Java SE 26 — XMLSignature](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html).
- [Oracle Java SE 26 — SignedInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignedInfo.html).
- [Oracle Java SE 26 — Reference](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html).
- [Oracle Java SE 26 — XMLObject](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLObject.html).
- [Oracle Java SE 26 — DigestMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/DigestMethod.html).
- [Oracle Java SE 26 — SignatureMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html).
- [Oracle Java SE 26 — Transform](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Transform.html).
- [Oracle Java SE 26 — CanonicalizationMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/CanonicalizationMethod.html).
- [Oracle Java SE 26 — DOMSignContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html).
- [Oracle Java SE 26 — DOMValidateContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html).
- [Oracle Java SE 26 — URIDereferencer](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/URIDereferencer.html).
- [Oracle Java SE 26 — OctetStreamData](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/OctetStreamData.html).
- [Oracle Java SE 26 — KeyInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/keyinfo/KeyInfo.html).
- [Oracle Java SE 26 — java.xml.crypto module](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/module-summary.html).
- [Oracle Java SE 17 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html).
- [W3C — XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core/).
- [W3C — XML Signature Best Practices](https://www.w3.org/TR/xmldsig-bestpractices/).
- [OWASP — XML External Entity Prevention](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html).

**Ghi nhớ:** Enveloped = **Signature nằm trong nội dung được ký**; enveloping = **nội dung nằm trong ds:Object của Signature**; detached = **Signature nằm ngoài nội dung được ký**, kể cả cùng document là sibling. Hãy xác minh **Reference URI, transforms, digests, SignatureValue, public key trust và chính business element**, không tự coi toàn bộ XML được bảo vệ chỉ vì có một chữ ký hợp lệ. Với external detached phải kiểm soát URI dereferencing; với Java hiện đại dùng thuật toán và secure-validation policy còn an toàn, không dùng lại SHA-1 signature chỉ vì nó có trong Javadoc lịch sử.
