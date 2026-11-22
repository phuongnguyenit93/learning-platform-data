# XMLSignatureFactory, SignedInfo và Reference trong chữ ký XML Java

**XML Digital Signature (XMLDSig)** là cơ chế tạo chữ ký số được biểu diễn bằng XML. API chuẩn Java được định nghĩa trong **JSR 105**, nằm ở module `java.xml.crypto`, đặc biệt là package `javax.xml.crypto.dsig`. API này được hỗ trợ từ Java 6 và **vẫn áp dụng trên Java 17+ cũng như Java SE hiện hành**. Phần quan trọng nhất khi học XMLDSig là hiểu đúng ba interface:

- **`XMLSignatureFactory`:** factory tạo ra `DigestMethod`, `Transform`, `Reference`, `CanonicalizationMethod`, `SignatureMethod`, `SignedInfo` và `XMLSignature`; nó còn đọc cấu trúc chữ ký trong tài liệu bằng `unmarshalXMLSignature(...)`.
- **`SignedInfo`:** phần XML **được ký bằng khóa riêng** sau canonicalization. Nó chứa thuật toán canonicalization, thuật toán ký và danh sách một hoặc nhiều `Reference`.
- **`Reference`:** chỉ ra dữ liệu nào được bảo vệ qua `URI`, dữ liệu trải qua những `Transform` nào, dùng `DigestMethod` nào và có `DigestValue` bao nhiêu.

**Phân biệt hai phép kiểm tra:** `SignatureValue` xác minh chữ ký mật mã của **canonicalized SignedInfo**, còn `Reference.validate(...)` kiểm tra digest của **dữ liệu thật được URI trỏ tới**. Nếu XML nghiệp vụ bị sửa nhưng SignedInfo không đổi, phép kiểm tra `SignatureValue` có thể **true** trong khi digest Reference **false**, dẫn đến `XMLSignature.validate(...)` **false**.

Bài này thuộc nhóm **Chữ ký XML**. Chỉ sử dụng kiến thức còn phù hợp với JDK hiện hành: **SHA-256 digest, RSA-SHA256 signature, RSA 3072-bit để minh họa, Exclusive XML Canonicalization, same-document Reference, cấu hình XML parser chống XXE và XMLDSig secure validation**. Không dùng các mẫu SHA-1/MD5 legacy làm lựa chọn khuyến nghị cho hệ thống mới.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Tạo factory kiểu DOM bằng `XMLSignatureFactory.getInstance("DOM")`.
2. Xây một `Reference` với `URI="#purchase-1"`, `DigestMethod.SHA256` và các transforms đúng ngữ nghĩa.
3. Xây `SignedInfo` bằng `CanonicalizationMethod.EXCLUSIVE`, `SignatureMethod.RSA_SHA256` và danh sách references.
4. Tạo `XMLSignature` rồi ký bằng `DOMSignContext` và khóa riêng.
5. Parse lại XML, tạo `DOMValidateContext`, đăng ký ID và xác minh bằng trusted public key.
6. So sánh `XMLSignature.validate`, `SignatureValue.validate` và `Reference.validate`.
7. Phân biệt canonicalization của SignedInfo và canonicalization transform của dữ liệu Reference.
8. Giới hạn `Reference URI` với `URIDereferencer` để tránh đọc file/HTTP không được phép.
9. Hiểu vì sao `KeyInfo` trong XML không phải một trust anchor.
10. Phát hiện duplicate IDs, signature wrapping, nhầm namespace hoặc xử lý business element chưa được ký.
11. Tránh kết quả kiểm tra bị cache khi XML đã bị sửa và tránh parser XXE/DTD.
12. Biên dịch/chạy chương trình Java 17+ đầy đủ với các negative tests đã được kiểm chứng trên JDK 24.

## 2. Sơ đồ cấu trúc XMLDSig

Một chữ ký enveloped (chữ ký nằm trong tài liệu chứa dữ liệu được ký) có cấu trúc ý tưởng:

```xml
<p:Purchase xmlns:p="urn:example:purchase" Id="purchase-1">
  <p:Amount>100</p:Amount>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="URI_EXCLUSIVE_C14N"/>
      <ds:SignatureMethod Algorithm="URI_RSA_SHA256"/>
      <ds:Reference URI="#purchase-1">
        <ds:Transforms>
          <ds:Transform Algorithm="URI_ENVELOPED_TRANSFORM"/>
          <ds:Transform Algorithm="URI_EXCLUSIVE_C14N"/>
        </ds:Transforms>
        <ds:DigestMethod Algorithm="URI_SHA256_DIGEST"/>
        <ds:DigestValue>BASE64_DIGEST</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>BASE64_SIGNATURE</ds:SignatureValue>
  </ds:Signature>
</p:Purchase>
```

**Đây chỉ là sơ đồ**, không phải XMLDSig hợp lệ để copy vào hệ thống: các chuỗi `URI_*`, `BASE64_*` là tên minh họa. Chương trình ở mục 8 sẽ dùng **constants thực** của Java và tự tạo SignatureValue đúng.

Mối quan hệ:

```text
XMLSignature
├── SignedInfo                         <- Được ký số
│   ├── CanonicalizationMethod          <- C14N của SignedInfo
│   ├── SignatureMethod                 <- RSA-SHA256
│   └── Reference[1..n]                 <- Các đối tượng cần bảo vệ
│       ├── URI                         <- #purchase-1
│       ├── Transforms                   <- enveloped, exclusive C14N
│       ├── DigestMethod                 <- SHA-256
│       └── DigestValue                  <- hash của data sau transforms
├── SignatureValue                       <- chữ ký trên SignedInfo
└── KeyInfo (tùy chọn)                   <- gợi ý khóa, KHÔNG tự chứng minh trust
```

Một Reference có thể trỏ vào document hiện tại bằng fragment, vào toàn bộ document hoặc tới resource khác; **ứng dụng phải quyết định trước loại target nào được phép**, không để XML không đáng tin tự chọn bừa.

### 2.1. Cách tạo chữ ký theo từng lớp

```text
[Reference URI] → [Dereference dữ liệu XML]
      → [Transforms] → [DigestMethod] → [DigestValue]
                                             |
                                             v
[CanonicalizationMethod] + [SignatureMethod] + [References]
                                             |
                                             v
                                         SignedInfo
                                             |
                                             v
                                   Canonicalize SignedInfo
                                             |
                                             v
                              KÝ với PRIVATE KEY → SignatureValue
```

Để xác minh, hệ thống tính lại digests từ dữ liệu thực tế và kiểm tra chữ ký SignedInfo bằng public key tin cậy; chỉ một phép so digest hoặc chỉ một phép verify RSA **không đủ**.

## 3. XMLSignatureFactory: lựa chọn provider và tạo thành phần

`XMLSignatureFactory` là abstract factory theo mô hình Java Cryptography Architecture (JCA). API hỗ trợ cơ chế XML `"DOM"`:

```java
XMLSignatureFactory factory =
        XMLSignatureFactory.getInstance("DOM");
```

Mảnh code có import `javax.xml.crypto.dsig.XMLSignatureFactory`. Java XML Digital Signature provider mặc định của JDK hỗ trợ DOM; ứng dụng có thể có provider khác và cần kiểm thử thuật toán/interop.

Các method chính:

| Factory method | Kết quả | Công dụng |
| --- | --- | --- |
| `getInstance("DOM")` | `XMLSignatureFactory` | Factory phù hợp với DOM XML signatures. |
| `newDigestMethod(...)` | `DigestMethod` | Thuật toán băm của mỗi Reference. |
| `newTransform(...)` | `Transform` | Biến đổi data trước digest. |
| `newCanonicalizationMethod(...)` | `CanonicalizationMethod` | C14N của SignedInfo. |
| `newSignatureMethod(...)` | `SignatureMethod` | Thuật toán ký SignedInfo. |
| `newReference(...)` | `Reference` | URI, transforms, digest và metadata optional. |
| `newSignedInfo(...)` | `SignedInfo` | C14N, SignatureMethod và các References. |
| `newXMLSignature(...)` | `XMLSignature` | Object sẽ được ký bằng `sign`. |
| `unmarshalXMLSignature(...)` | `XMLSignature` | Đọc cấu trúc Signature XML vào API model; **chưa verify**. |

Ví dụ chuẩn bị thuật toán:

```java
DigestMethod digest =
        factory.newDigestMethod(DigestMethod.SHA256, null);

SignatureMethod signatureMethod =
        factory.newSignatureMethod(SignatureMethod.RSA_SHA256, null);
```

Cả hai là mảnh code trong method xử lý checked exceptions. Không tự tạo implementation của `SignedInfo` hay `Reference` bằng tên class `com.sun.org.apache...`: đó là API nội bộ của provider, không phải contract Java application ổn định.

### 3.1. Package và type cần phân biệt

- `javax.xml.crypto.dsig.XMLSignatureFactory` tạo cấu trúc chữ ký.
- `javax.xml.crypto.dsig.SignedInfo` biểu diễn phần được ký.
- `javax.xml.crypto.dsig.Reference` biểu diễn tài nguyên được digest.
- `javax.xml.crypto.dsig.XMLSignature` có `sign` và `validate`.
- `javax.xml.crypto.dsig.dom.DOMSignContext` xác định khóa ký/vị trí chèn Signature.
- `javax.xml.crypto.dsig.dom.DOMValidateContext` xác định khóa xác minh/vị trí Signature.
- `javax.xml.crypto.URIDereferencer` định nghĩa cách lấy data từ Reference URI.
- `javax.xml.crypto.dsig.keyinfo.KeyInfo` là metadata khóa tùy chọn, không thay thế trust policy.

Đừng nhầm `java.security.Signature` primitive cấp thấp với `javax.xml.crypto.dsig.XMLSignature`. Chữ ký XML không đơn giản là `Signature.sign(rawXmlString)`; XMLDSig cần URI dereferencing, transforms, C14N, SignedInfo và Reference digests.

## 4. SignedInfo: nội dung thực sự được ký

`SignedInfo` chứa ba thành phần bắt buộc: `CanonicalizationMethod`, `SignatureMethod` và danh sách **ít nhất một `Reference`**. Một ví dụ:

```java
SignedInfo signedInfo = factory.newSignedInfo(
        factory.newCanonicalizationMethod(
                CanonicalizationMethod.EXCLUSIVE,
                (C14NMethodParameterSpec) null),
        factory.newSignatureMethod(
                SignatureMethod.RSA_SHA256, null),
        List.of(reference));
```

Đây là mảnh code cần import các interfaces/spec classes và biến `reference` đã tạo. `SignedInfo.getReferences()` trả một danh sách không thể thay đổi qua list view, còn `getSignatureMethod()` và `getCanonicalizationMethod()` giúp đọc lại thuật toán khi kiểm tra policy.

**SignatureValue ký canonicalized SignedInfo, không trực tiếp ký raw XML bytes.** Dữ liệu nghiệp vụ được bảo vệ bởi **`Reference.DigestValue` nằm bên trong SignedInfo**. Nếu XML bị sửa, Reference digest fail; nếu SignedInfo bị sửa, SignatureValue fail.

### 4.1. Core validation khác SignatureValue validation

```java
boolean coreValid = xmlSignature.validate(validation);
boolean signedInfoOk =
        xmlSignature.getSignatureValue().validate(validation);
```

Trong đó:

- `signedInfoOk` chỉ kiểm tra chữ ký mật mã của `SignedInfo`.
- `coreValid` kiểm tra core XMLDSig rules, bao gồm chữ ký và digest của các References.

Nếu một `Amount` đã bị thay từ `100` thành `999` trong khi Signature giữ nguyên:

```text
SignatureValue.validate() = true
Reference.validate()      = false
XMLSignature.validate()   = false
```

Đây là kết quả thực đã kiểm chứng trong ví dụ Java 17+ của bài. Nó cho thấy chỉ kiểm tra khóa/chữ ký trên `SignedInfo` không đủ để xác minh data.

### 4.2. Không chấp nhận SignedInfo bất kỳ

Một chữ ký có thể hợp lệ cho dữ liệu không quan trọng, chẳng hạn header hoặc logo, trong khi phần `Purchase.Amount` chưa được bảo vệ. Vì vậy, ứng dụng phải xác định:

- Số Reference nào **bắt buộc** theo giao thức?
- URI nào tương ứng với đúng business object?
- Digest và Signature algorithm nào được chấp thuận?
- Transform nào được phép và thứ tự nào hợp lý?
- Element được tham chiếu có đúng namespace, vị trí và ID?
- Có signed subtree nằm ngoài nơi business code đang đọc không?

**Cryptographic validity và business binding là hai điều kiện bổ sung, không thay thế nhau.**

## 5. Reference: URI, Transforms, DigestMethod và DigestValue

`Reference` bảo vệ một mục dữ liệu được xác định bởi URI. Với target ở document hiện tại:

```java
Reference reference = factory.newReference(
        "#purchase-1",
        factory.newDigestMethod(DigestMethod.SHA256, null),
        List.of(
                factory.newTransform(
                        Transform.ENVELOPED, (TransformParameterSpec) null),
                factory.newTransform(
                        CanonicalizationMethod.EXCLUSIVE,
                        (TransformParameterSpec) null)),
        null, null);
```

Mảnh code này dùng overload năm tham số: `URI`, `DigestMethod`, `List<Transform>`, `type` optional, `id` optional. **Hai tham số `null` cuối không phải target ID**: target được chỉ ra bởi `URI="#purchase-1"`. `Reference.getId()` nếu có là thuộc tính `Id` của chính element Reference.

### 5.1. Ý nghĩa của URI

| URI | Đối tượng được biểu diễn | Quy tắc cần xét |
| --- | --- | --- |
| `""` | Same-document toàn bộ XML theo quy tắc XMLDSig. | Chữ ký enveloped cần tránh tự digest chính Signature. |
| `"#purchase-1"` | Same-document element có ID `purchase-1`. | Đăng ký đúng typed ID, chỉ một target hợp lệ. |
| `"data.xml"` | Relative resource theo base URI. | Không được tự tìm file theo input untrusted. |
| `"file:///..."` | External filesystem resource. | Cần deny khi không có policy đặc biệt. |
| `"https://..."` | External network resource. | Tránh SSRF/remote content substitution. |

Trong bài, policy là **chỉ chấp nhận đúng `"#purchase-1"`**, không mở remote URI. Cách này không bao phủ mọi XMLDSig use case, nhưng giúp bản ký Purchase có ý nghĩa rõ ràng.

### 5.2. DigestValue không phải SignatureValue

- `DigestMethod` băm **Referenced Data** sau Transforms; `DigestValue` là kết quả hash được lưu.
- `SignatureMethod` dùng private key ký **canonicalized SignedInfo**, vốn chứa một hoặc nhiều DigestValue.
- Một Reference có thể digest đúng dù chữ ký SignedInfo sai (ví dụ dùng public key của người khác).
- Một SignatureValue có thể đúng dù Reference digest sai (data bị thay đổi sau khi ký).

`Reference.getDigestValue()` trả digest đã lưu; `Reference.getCalculatedDigestValue()` có thể trả digest vừa tính sau validation. Kết quả là `byte[]` và có thể là `null` nếu operation chưa thực hiện. Chỉ dùng hai giá trị để **debug**, không tự thay `Reference.validate(...)` bằng phép so hash đơn giản.

### 5.3. Transforms thực hiện theo thứ tự

Ví dụ dùng:

1. `Transform.ENVELOPED`: bỏ element `<Signature>` khỏi dữ liệu đang được ký, vì Signature nằm **bên trong** Purchase.
2. `CanonicalizationMethod.EXCLUSIVE` như một Reference transform: canonicalize dữ liệu còn lại để đưa vào SHA-256 digest.

Nếu đảo thứ tự hoặc chọn transform khác, dữ liệu digest có thể khác. Một chữ ký có thể fail dù các element quan trọng nhìn bằng mắt vẫn đúng nếu có thay đổi về whitespace, namespace context hoặc XML serialization.

**C14N của Reference** và **C14N của SignedInfo** là hai bước riêng:

| Thuộc tính | Áp dụng cho | Kết quả |
| --- | --- | --- |
| `Reference.Transform` C14N | Target XML data | Byte input cho DigestMethod. |
| `SignedInfo.CanonicalizationMethod` | SignedInfo XML structure | Byte input cho SignatureMethod. |

Đừng thay XMLDSig bằng `MessageDigest.getInstance("SHA-256").digest(xml.getBytes(...))`: cách đó bỏ qua URI, transforms, canonicalization và chữ ký SignedInfo.

## 6. Canonicalization và ba dạng XML Signature

XML có nhiều cách serialize có thể tạo cùng một cấu trúc: thuộc tính thay thứ tự, namespace declarations, quote styles hoặc representation của các character entities. **XML Canonicalization (C14N)** quy định cách chuyển một node-set/XML structure về dạng chuẩn trước phép băm hoặc ký.

Trong demo dùng `CanonicalizationMethod.EXCLUSIVE` cho SignedInfo và một transform exclusive C14N cho Reference. Exclusive C14N hữu ích với XML subtree và các ngữ cảnh namespace, nhưng **không biến mọi thay đổi dữ liệu thành tương đương**. Sửa `Amount` từ `100` sang `999` vẫn bắt buộc làm digest fail.

Ba kiểu chữ ký thường gặp:

| Kiểu | Chữ ký ở đâu? | Điều cần nhớ |
| --- | --- | --- |
| **Enveloped** | Signature nằm trong data document. | Dùng enveloped transform khi ký vùng chứa Signature. |
| **Enveloping** | Data nằm trong Signature, thường trong `XMLObject`. | Cần nhận diện đúng data object được ký. |
| **Detached** | Signature nằm ngoài dữ liệu tham chiếu. | Cần dereferencing an toàn và content identity binding. |

Một ứng dụng có thể có nhiều References trong SignedInfo, ví dụ ký XML cùng attachment. Phải kiểm tra **mọi Reference bắt buộc**, không chỉ Reference đầu tiên trả true.

## 7. DOMSignContext, DOMValidateContext và ID registration

Phía ký cần private key và vị trí chèn chữ ký:

```java
DOMSignContext signContext =
        new DOMSignContext(privateKey, purchaseRoot);
signContext.setIdAttributeNS(purchaseRoot, null, "Id");
signature.sign(signContext);
```

Phía kiểm tra cần public key từ nguồn tin cậy và vị trí chữ ký:

```java
DOMValidateContext valContext =
        new DOMValidateContext(trustedPublicKey, signatureNode);
valContext.setIdAttributeNS(purchaseRoot, null, "Id");
valContext.setProperty(
        "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
XMLSignature parsed =
        factory.unmarshalXMLSignature(valContext);
boolean valid = parsed.validate(valContext);
```

Đây là các mảnh code: `privateKey`, `purchaseRoot`, `signature`, `trustedPublicKey`, `signatureNode` và `factory` do ứng dụng cung cấp.

### 7.1. Vì sao phải register ID?

Một DOM attribute có tên `Id` **không nhất thiết tự được coi là XML ID** nếu parser không validate schema/DTD. Khi `Reference URI="#purchase-1"`, provider cần xác định đúng node mang ID. `setIdAttributeNS` đăng ký attribute tương ứng trên DOMCryptoContext mà XMLDSig dùng; sai element hoặc nhầm namespace có thể khiến reference không resolve hoặc trỏ sai.

### 7.2. DOM data chưa chắc được bảo vệ nếu chỉ tìm theo tên

`getElementsByTagNameNS(...,"Purchase")` có thể trả nhiều element; một XML bị tấn công wrapping có thể chứa Purchase ký thật ở nhánh này và Purchase giả ở nhánh khác. Sau khi validate, không dùng “Purchase đầu tiên” hay một XPath không ràng buộc để xử lý nghiệp vụ.

**Phải dùng chính target element đã xác minh và bảo đảm ID/namespace/vị trí/cấu trúc đúng policy.**

## 8. Chương trình Java 17+ chạy độc lập: ký và xác minh đầy đủ

Ví dụ dưới đây không cần database, Maven/Gradle hoặc tải network. Nó tạo RSA keypair **tạm để học API**, ký XML `Purchase`, serialize, parse lại, rồi thực hiện kiểm thử:

- Chữ ký nguyên vẹn hợp lệ.
- Chữ ký trên SignedInfo và digest của Reference đều hợp lệ.
- Sửa `Amount` làm core validation false, nhưng chữ ký SignedInfo vẫn true.
- Public key sai làm core false dù data digest vẫn đúng.
- Duplicate `Id` bị policy reject trước validation.
- XML có DOCTYPE bị secure DOM parser reject.

Nó cố tình **không nhúng `KeyInfo`**: ứng dụng xác minh dùng trusted public key có sẵn, vì tin KeyInfo của input XML mà không kiểm tra identity là nguy hiểm.

### 8.1. File `XmlSignaturePartsDemo.java`

```java
import java.io.StringReader;
import java.io.StringWriter;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.util.List;

import javax.xml.XMLConstants;
import javax.xml.crypto.Data;
import javax.xml.crypto.URIReference;
import javax.xml.crypto.URIReferenceException;
import javax.xml.crypto.URIDereferencer;
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
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

public final class XmlSignaturePartsDemo {
    private static final String NS = "urn:example:purchase";
    private static final String ID = "purchase-1";
    private static final String REF_URI = "#" + ID;

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    private static DocumentBuilderFactory safeDomFactory() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        return f;
    }

    private static Document createPurchase() throws Exception {
        Document doc = safeDomFactory().newDocumentBuilder().newDocument();
        Element root = doc.createElementNS(NS, "p:Purchase");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:p", NS);
        root.setAttribute("Id", ID);
        doc.appendChild(root);
        Element amount = doc.createElementNS(NS, "p:Amount");
        amount.setTextContent("100");
        root.appendChild(amount);
        Element title = doc.createElementNS(NS, "p:Title");
        title.setTextContent("Đơn hàng Việt Nam 😀");
        root.appendChild(title);
        return doc;
    }

    private static URIDereferencer onlyExpectedReference(XMLSignatureFactory factory) {
        URIDereferencer delegate = factory.getURIDereferencer();
        return (reference, context) -> {
            if (!REF_URI.equals(reference.getURI())) {
                throw new URIReferenceException(
                        "Only expected same-document URI is allowed");
            }
            return delegate.dereference(reference, context);
        };
    }

    private static void sign(Document doc, KeyPair keys) throws Exception {
        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        Reference reference = f.newReference(
                REF_URI,
                f.newDigestMethod(DigestMethod.SHA256, null),
                List.of(
                    f.newTransform(Transform.ENVELOPED,
                                   (TransformParameterSpec) null),
                    f.newTransform(CanonicalizationMethod.EXCLUSIVE,
                                   (TransformParameterSpec) null)),
                null,
                null);
        SignedInfo info = f.newSignedInfo(
                f.newCanonicalizationMethod(CanonicalizationMethod.EXCLUSIVE,
                                             (C14NMethodParameterSpec) null),
                f.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(reference));
        XMLSignature signature = f.newXMLSignature(info, null);
        Element root = doc.getDocumentElement();
        DOMSignContext context = new DOMSignContext(keys.getPrivate(), root);
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(root, null, "Id");
        context.setURIDereferencer(onlyExpectedReference(f));
        signature.sign(context);
    }

    private static String xml(Document doc) throws Exception {
        TransformerFactory f = TransformerFactory.newInstance();
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        var transformer = f.newTransformer();
        transformer.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
        transformer.setOutputProperty(OutputKeys.INDENT, "no");
        StringWriter out = new StringWriter();
        transformer.transform(new DOMSource(doc), new StreamResult(out));
        return out.toString();
    }

    private static Document parse(String source) throws Exception {
        return safeDomFactory().newDocumentBuilder().parse(
                new InputSource(new StringReader(source)));
    }

    private static void requireUniqueTarget(Document doc, Element root,
                                            Node signatureNode) {
        if (!NS.equals(root.getNamespaceURI())
                || !"Purchase".equals(root.getLocalName())
                || !ID.equals(root.getAttribute("Id"))
                || signatureNode.getParentNode() != root) {
            throw new SecurityException("Unexpected signed-data structure");
        }
        NodeList all = doc.getElementsByTagName("*");
        int matches = 0;
        for (int i = 0; i < all.getLength(); i++) {
            Element e = (Element) all.item(i);
            if (ID.equals(e.getAttribute("Id"))) matches++;
        }
        if (matches != 1) {
            throw new SecurityException("Duplicate or missing target Id");
        }
    }

    record Result(boolean core, boolean signatureValue, boolean reference) {}

    private static Result verify(Document doc, PublicKey trustedPublicKey)
            throws Exception {
        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        NodeList signatures =
                doc.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature");
        if (signatures.getLength() != 1) {
            throw new SecurityException("Expected one Signature");
        }
        Node signatureNode = signatures.item(0);
        Element root = doc.getDocumentElement();
        requireUniqueTarget(doc, root, signatureNode);

        DOMValidateContext context =
                new DOMValidateContext(trustedPublicKey, signatureNode);
        context.setIdAttributeNS(root, null, "Id");
        context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        context.setURIDereferencer(onlyExpectedReference(f));
        XMLSignature signature = f.unmarshalXMLSignature(context);
        SignedInfo info = signature.getSignedInfo();
        if (!SignatureMethod.RSA_SHA256.equals(
                    info.getSignatureMethod().getAlgorithm())
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                    info.getCanonicalizationMethod().getAlgorithm())
                || info.getReferences().size() != 1) {
            throw new SecurityException("Unexpected SignedInfo policy");
        }
        Reference reference = (Reference) info.getReferences().get(0);
        if (!REF_URI.equals(reference.getURI())
                || !DigestMethod.SHA256.equals(
                    reference.getDigestMethod().getAlgorithm())
                || reference.getTransforms().size() != 2
                || !Transform.ENVELOPED.equals(
                    reference.getTransforms().get(0).getAlgorithm())
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                    reference.getTransforms().get(1).getAlgorithm())) {
            throw new SecurityException("Unexpected Reference policy");
        }
        boolean valid = signature.validate(context);
        boolean signatureValue =
                signature.getSignatureValue().validate(context);
        boolean referenceValid = reference.validate(context);
        return new Result(valid, signatureValue, referenceValid);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(3072);
        KeyPair trusted = rsa.generateKeyPair();

        Document document = createPurchase();
        sign(document, trusted);
        String signedXml = xml(document);

        Result valid = verify(parse(signedXml), trusted.getPublic());
        check("signedDocumentValid", valid.core());
        check("signatureValueValid", valid.signatureValue());
        check("referenceDigestValid", valid.reference());

        Document tampered = parse(signedXml);
        ((Element) tampered.getElementsByTagNameNS(NS, "Amount").item(0))
                .setTextContent("999");
        Result altered = verify(tampered, trusted.getPublic());
        check("changedAmountRejected", !altered.core());
        check("changedAmountSignatureValueStillValid",
                altered.signatureValue());
        check("changedAmountReferenceDigestInvalid", !altered.reference());

        KeyPair unknown = rsa.generateKeyPair();
        Result wrongKey = verify(parse(signedXml), unknown.getPublic());
        check("untrustedKeyRejected", !wrongKey.core());
        check("untrustedKeyReferenceDigestStillValid",
                wrongKey.reference());

        Document wrapping = parse(signedXml);
        Element duplicate = wrapping.createElementNS(NS, "p:Purchase");
        duplicate.setAttribute("Id", ID);
        wrapping.getDocumentElement().appendChild(duplicate);
        try {
            verify(wrapping, trusted.getPublic());
            throw new AssertionError("Duplicate target Id should be rejected");
        } catch (SecurityException expected) {
            System.out.println("duplicateId=REJECTED");
        }

        try {
            parse("<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///no-file'>]>"
                    + "<x>&e;</x>");
            throw new AssertionError("DOCTYPE should be rejected");
        } catch (SAXException expected) {
            System.out.println("doctype=REJECTED");
        }
    }
}
```

### 8.2. Biên dịch và chạy

Tạo tệp UTF-8 đúng tên `XmlSignaturePartsDemo.java` rồi chạy:

```bash
javac --release 17 -encoding UTF-8 XmlSignaturePartsDemo.java
java XmlSignaturePartsDemo
```

Đây là chương trình **chạy độc lập với JDK 17+**. `java.xml.crypto` là module chuẩn, không cần external JAR. Keypair được sinh ngẫu nhiên mỗi lượt chạy, vì vậy không in ra base64 của `SignatureValue` làm expected output.

### 8.3. Stdout chính xác đã kiểm chứng trên JDK 24

```text
signedDocumentValid=PASS
signatureValueValid=PASS
referenceDigestValid=PASS
changedAmountRejected=PASS
changedAmountSignatureValueStillValid=PASS
changedAmountReferenceDigestInvalid=PASS
untrustedKeyRejected=PASS
untrustedKeyReferenceDigestStillValid=PASS
duplicateId=REJECTED
doctype=REJECTED
```

**10 dòng stdout.** Đã biên dịch bằng `javac --release 17` và chạy thành công trên **OpenJDK 24.0.2**. Trong lần kiểm thử đã thực hiện, DOM parser còn ghi thông báo lỗi DOCTYPE bị cấm ra **stderr** khi negative test; thông báo này không phải một phần của 10 dòng stdout và có thể thay đổi tùy parser/JDK.

### 8.4. Vì sao các kiểm tra đều có ý nghĩa?

- `signedDocumentValid`: ký và xác minh đầy đủ trên một DOM được parse lại.
- `signatureValueValid`: RSA-SHA256 xác minh SignedInfo bằng trusted public key.
- `referenceDigestValid`: SHA-256 của Reference URI `#purchase-1` khớp digest lưu trong chữ ký.
- `changedAmountRejected`: đổi Amount từ 100 sang 999 làm core validation thất bại.
- `changedAmountSignatureValueStillValid`: SignedInfo không bị đổi nên chữ ký SignedInfo vẫn đúng, dù data đã bị sửa.
- `changedAmountReferenceDigestInvalid`: Reference digest không còn khớp với Purchase đã bị sửa.
- `untrustedKeyRejected`: public key của cặp RSA khác không thể xác minh SignatureValue.
- `untrustedKeyReferenceDigestStillValid`: dữ liệu XML không đổi nên Reference digest vẫn đúng dù key sai.
- `duplicateId=REJECTED`: policy kiểm tra ID duy nhất từ chối XML có hai nodes cùng `Id="purchase-1"`.
- `doctype=REJECTED`: parser từ chối DOCTYPE trước khi phép xác minh chữ ký có cơ hội chạy.

Chương trình dùng một purchase schema nhỏ. `requireUniqueTarget` chỉ kiểm tra attribute `Id` không namespace; **không được coi là giải pháp tổng quát** cho mọi `xml:id`, `wsu:Id`, namespace/phần tử hoặc profile XMLDSig/WS-Security phức tạp.

## 9. Tại sao không reuse validation sau khi XML bị sửa?

`XMLSignature.validate(...)` và `Reference.validate(...)` có thể **cache kết quả lần đầu**. Javadoc cũng nêu hành vi không được bảo đảm nếu caller thay đổi DOM chứa XMLSignature sau khi unmarshal.

Cách test đúng là:

- Giữ signed XML ban đầu.
- Với mỗi test, **parse thành Document mới**.
- Tạo `DOMValidateContext` riêng cho mỗi Document/Signature.
- Unmarshal XMLSignature riêng rồi validate.
- Không sửa DOM rồi gọi validate lần nữa trên cùng object để hy vọng implementation tự kiểm tra lại.

Demo thực hiện đúng cách này cho nhánh tamper, wrong key và duplicate ID.

### 9.1. Sự khác nhau giữa signed object và XML bytes hiển thị

XMLDSig ký **canonicalized structures theo profile** chứ không ký một đoạn source string bất kỳ. Nếu serializer thêm indentation vào subtree được ký, bytes canonicalized có thể thay đổi; ngược lại một số thay đổi lexical có thể không làm cấu trúc canonical khác. Nên serialize ổn định, không thay content/namespace context ngoài kỳ vọng, và có interoperability tests giữa các implementations.

## 10. URIDereferencer: chỉ cho phép đúng tài nguyên cần ký

Nếu Reference URI là `https://internal-service/...` hoặc `file:///...` mà ứng dụng dùng default dereferencer không kiểm soát, attacker có thể gây SSRF/truy cập file hoặc thay đổi nội dung được băm. Trong XML nhập từ bên ngoài, một chính sách an toàn là **allowlist rõ ràng**.

Demo dùng:

```java
private static URIDereferencer onlyExpectedReference(
        XMLSignatureFactory factory) {
    URIDereferencer delegate = factory.getURIDereferencer();
    return (reference, context) -> {
        if (!"#purchase-1".equals(reference.getURI())) {
            throw new URIReferenceException(
                    "Only expected same-document URI is allowed");
        }
        return delegate.dereference(reference, context);
    };
}
```

Khi URI đúng, resolver của provider mới được phép xử lý same-document fragment đã đăng ký. Mọi URI khác đều bị từ chối, **không có code HTTP/file fetch tự viết**.

Không dùng `URI.create(reference.getURI()).toURL().openStream()` trong custom resolver lấy input chưa tin cậy. `secureValidation` của JDK có các hạn chế bổ sung với HTTP/file và transforms, nhưng không thay thế business allowlist hoặc network egress policy.

### 10.1. XML Signature Wrapping và identity binding

Một chữ ký mật mã hợp lệ có thể bảo vệ `Purchase` A, trong khi business code đọc `Purchase` B chưa được ký. Vì vậy:

- Kiểm tra root element, namespace URI và vị trí.
- Kiểm tra đúng một Signature trong profile đơn giản.
- Kiểm tra target ID duy nhất theo schema.
- Kiểm tra URI từ SignedInfo trỏ đúng expected target.
- Kiểm tra số Reference và algorithms/transforms theo allowlist.
- **Xử lý chính DOM node đã được xác minh**, không chọn element khác sau validate.
- Với nhiều namespaces/ID schemes, mở rộng kiểm tra duplicate ID thay vì tin scanner chỉ nhìn attribute `Id`.

Crypto pass **không phải** là toàn bộ kiểm tra business policy.

## 11. KeyInfo và trust: chữ ký đúng chưa chắc signer đáng tin

`KeyInfo` là thành phần optional để biểu diễn thông tin về khóa: `KeyName`, `KeyValue`, `X509Data`, `RetrievalMethod` và các cấu trúc khác. Nhưng một attacker có thể tự tạo cặp khóa, ký XML giả mạo và nhúng public key của chính họ vào `KeyInfo`.

Nếu verifier cứ nhận mọi key trong XML làm đáng tin, `SignatureValue.validate` có thể đúng về toán học nhưng **không xác nhận đúng chủ thể**.

Hướng thực tế:

- Lấy trusted public key từ application configuration/keystore hoặc pinning có quản lý.
- Nếu dùng certificate: validate chain, validity, revocation theo policy, key usage/EKU, identity/tenant binding.
- Có key rotation/compromise handling và audit.
- Không nhúng private key vào XML hoặc logs.
- Nếu cần `KeySelector`, nó phải chọn key gắn với trust policy thay vì chỉ lấy public key đầu tiên.

Trong demo, `DOMValidateContext(trustedPublicKey, signatureNode)` không dựa vào `KeyInfo` từ input. Private key sinh ra chỉ phục vụ bài test, không phải giải pháp lưu trữ khóa production.

## 12. XMLDSig secure validation và parser security

JDK hiện hành bật `org.jcp.xml.dsig.secureValidation` theo mặc định trong `DOMValidateContext`; demo còn đặt `Boolean.TRUE` rõ ràng. Oracle Security Guide nêu các hạn chế như: loại bỏ một số XSLT transforms, giới hạn số References/transforms, từ chối các chữ ký/thuật toán yếu, chặn URI scheme HTTP/HTTPS/file và áp giới hạn key sizes/ID uniqueness theo **`jdk.xml.dsig.secureValidationPolicy`**.

**Đừng tắt secureValidation để ép chữ ký legacy pass.** Nếu liên thông với đối tác có thuật toán cũ, cần xem giao thức, rủi ro và migration policy; không lấy cấu hình yếu làm mặc định.

### 12.1. Parser XML phải an toàn trước khi verify

JDK XMLDSig không tự giải quyết mọi rủi ro XXE xảy ra **khi parse XML ban đầu**. Demo dùng `DocumentBuilderFactory`:

```java
DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
f.setNamespaceAware(true);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);
```

`disallow-doctype-decl` hoạt động trên JDK parser đã kiểm thử, **không phải một feature đảm bảo cho mọi DOM parser provider**. Nếu parser không hỗ trợ các bảo vệ bắt buộc, hãy fail closed thay vì silently ignore. Bổ sung input size, depth, entity expansion và time limits theo threat model.

### 12.2. Hạn chế serialization/transform

Ví dụ dùng `TransformerFactory` với `FEATURE_SECURE_PROCESSING` và `ACCESS_EXTERNAL_STYLESHEET=""` để không mở stylesheet ngoài, đồng thời không indent XML đã ký. Việc parse/serialize/validate qua nhiều providers cần integration tests với Unicode, namespace, prefix và whitespace. Không dùng XSLT do XML untrusted yêu cầu nếu không có chính sách chặt.

### 12.3. Những thuật toán cần dùng hiện nay

| Vị trí | Lựa chọn trong bài | Ghi nhớ |
| --- | --- | --- |
| `Reference.DigestMethod` | `DigestMethod.SHA256` | Hash của dữ liệu sau transforms. |
| `SignedInfo.SignatureMethod` | `SignatureMethod.RSA_SHA256` | Ký canonicalized SignedInfo. |
| `SignedInfo.CanonicalizationMethod` | `CanonicalizationMethod.EXCLUSIVE` | C14N SignedInfo. |
| `Reference.Transforms` | `Transform.ENVELOPED` + Exclusive C14N | Phù hợp chữ ký enveloped trên root. |
| Khóa demo | RSA 3072-bit | Sinh ngẫu nhiên để test; production cần keystore/HSM. |

Tránh MD5 và SHA1 signature legacy khi tạo giao thức mới. Các tiêu chuẩn liên thông hoặc compliance có thể yêu cầu thuật toán/profile khác; chỉ dùng thuật toán provider thực sự hỗ trợ và đã được security review.

## 13. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Chỉ kiểm tra SignatureValue | Bỏ qua digest data thực tế. | `XMLSignature.validate` và kiểm tra references. |
| Chỉ kiểm tra digest Reference | Không chứng minh signer có khóa tin cậy. | Kiểm tra SignedInfo signature và key trust. |
| Dùng raw XML bytes để hash thay vì XMLDSig transforms | Sai canonicalization/data model. | Dùng XMLSignatureFactory. |
| Nhầm `Reference.Id` với target XML ID | Hai khái niệm khác nhau. | Reference URI chỉ target Id. |
| Không register ID | Same-document URI không resolve đúng. | `setIdAttributeNS`. |
| Cho trùng ID | Có nguy cơ XML Signature Wrapping. | Kiểm tra ID uniqueness theo schema. |
| Chấp nhận mọi Reference URI | Có thể mở file/network, ký sai content. | Strict URIDereferencer. |
| Dựa vào tên prefix `ds` | XML prefix có thể khác. | Match namespace URI + localName. |
| Dựa vào KeyInfo tự khai | Key không tự đáng tin. | Trust store/pinning/certificate policy. |
| Bỏ qua Signature position và business binding | Có thể validate node khác node đang xử lý. | Validate đúng node và dùng chính nó. |
| Xóa/đổi XML Signature nhưng giữ old context | Validation cache/undefined state. | Parse lại, context mới. |
| Dùng SHA-1/MD5 mới | Không phù hợp security policy hiện hành. | SHA-256+ và thuật toán được duyệt. |
| Tắt secure validation | Mở các constructs nguy hiểm. | Giữ mode an toàn. |
| Dùng DOM parser mặc định cho XML untrusted | Có thể XXE/DTD. | Secure XML parser. |
| Đổi indentation sau ký | Whitespace có thể ảnh hưởng digest. | Serialize có kiểm soát. |
| Đoán expected base64 SignatureValue | Keypair ngẫu nhiên, chữ ký có thể khác. | Kiểm tra booleans/signature semantics. |
| Cho rằng core valid nghĩa identity hợp lệ | Crypto không tự xác thực certificate/trust. | Kiểm tra business signer policy. |

## 14. Checklist triển khai production

- [ ] Có profile rõ ràng cho XML data, namespace, target IDs và vị trí Signature?
- [ ] Chỉ cho thuật toán digest/signature/canonicalization/transforms được duyệt?
- [ ] Reference URIs chỉ trỏ resources cần thiết, không cho file/HTTP tùy ý?
- [ ] ID attributes được đăng ký đúng qua `setIdAttributeNS`?
- [ ] Có kiểm tra ID uniqueness theo mọi schema/namespace được hỗ trợ?
- [ ] Có chặn signature wrapping và business node mismatch?
- [ ] Có kiểm tra đúng số lượng `Reference`, tên thuật toán và thứ tự transforms?
- [ ] Có dùng trusted public key độc lập với input XML?
- [ ] Có certificate chain/identity/rotation policy nếu dùng X.509?
- [ ] DOM parser có namespace-aware, chặn DTD/XXE và có limits?
- [ ] Có bật secure validation và không tắt để nhận SHA1 cũ?
- [ ] Có gọi `XMLSignature.validate`, không chỉ `SignatureValue.validate`?
- [ ] Với nhiều references, có kiểm tra từng reference bắt buộc?
- [ ] Có dùng đúng DOM node đã ký, không parse nguồn mới để lấy data chưa xác minh?
- [ ] Mỗi lần verify có DOM/context riêng và không tái sử dụng kết quả bị cache?
- [ ] Không log private key, raw XML có PII hoặc Signature internals không cần thiết?
- [ ] Có tests cho tamper, wrong key, duplicate IDs, DOCTYPE, external URI, algorithm downgrade?
- [ ] Có interoperability tests với đối tác/JDK/provider đang triển khai?

## 15. Bài tập thực hành

**Bài A — Reference URI:** đổi `"#purchase-1"` thành `""` trong sandbox và sửa URI policy; phân tích phạm vi data được digest thay đổi thế nào.

**Bài B — SignedInfo khác Reference:** sửa `Amount` sau khi ký, xác minh kết quả `SignatureValue.validate=true` nhưng `Reference.validate=false`.

**Bài C — Wrong key:** giữ XML nguyên, dùng public key từ một cặp RSA khác; vì sao reference digest vẫn có thể đúng?

**Bài D — Two references:** ký hai elements có ID khác nhau, kiểm tra ứng dụng chỉ chấp nhận nếu cả hai nằm trong SignedInfo và hợp lệ.

**Bài E — Duplicate ID:** chèn hai elements cùng ID. Nâng hàm kiểm tra để bao phủ namespace-specific IDs như `xml:id`/`wsu:Id` nếu schema của bạn hỗ trợ.

**Bài F — Namespace confusion:** tạo `Purchase` cùng local name nhưng namespace khác; chính sách phải từ chối nếu namespace không đúng.

**Bài G — Canonicalization:** thay đổi cách serialize một tài liệu mà không đổi data, quan sát dấu hiệu digest pass/fail; giải thích vì sao C14N không biến `100` thành `999`.

**Bài H — Reference URI policy:** thử một URI `https://untrusted.invalid/a` và bảo đảm dereferencer chặn trước khi có network request.

**Bài I — Secure validation:** thử profile SHA1/MD5 từ một test fixture an toàn và xác minh JDK policy từ chối, không tắt chế độ an toàn để làm test pass.

**Bài J — Keys và trust:** thay keypair sinh trong RAM bằng public key lấy từ trust store/certificate được kiểm tra, không tin KeyInfo tự khai.

**Bài K — Replay/cached validation:** thử sửa DOM sau khi validate, so với parse lại và validate context mới; không dùng kết quả cached làm khẳng định bảo mật.

**Bài L — Profile nghiệp vụ:** thiết kế các quy tắc ID/signature location/reference count/algorithms dành riêng cho hóa đơn hoặc tài liệu doanh nghiệp.

## 16. Câu hỏi tự kiểm tra

**1. XMLSignatureFactory là gì?** — Factory của XMLDSig tạo Reference, SignedInfo, XMLSignature và unmarshal chữ ký XML.

**2. SignedInfo chứa gì?** — CanonicalizationMethod, SignatureMethod và danh sách một hoặc nhiều Reference.

**3. Reference.DigestValue bảo vệ nội dung nào?** — Dữ liệu được URI trỏ tới sau khi chạy Transforms theo thứ tự.

**4. SignatureValue ký gì?** — Canonicalized SignedInfo, không phải raw bytes của toàn bộ XML document theo cách ứng dụng tự chọn.

**5. Vì sao SignatureValue đúng mà XMLSignature.validate sai?** — Referenced data có thể đã bị sửa; Reference digest fail.

**6. Reference URI="#purchase-1" có nghĩa gì?** — Same-document reference đến element với ID đã đăng ký là purchase-1.

**7. Reference.getId() có phải target ID không?** — Không. Nó là optional Id của chính Reference element.

**8. Vì sao cần Transform.ENVELOPED?** — Chữ ký nằm trong data; transform loại chữ ký khỏi data trước khi digest để tránh self-reference.

**9. C14N của SignedInfo và C14N của Reference có giống mục tiêu?** — Không. Một dành cho bytes ký SignedInfo, một dành cho bytes băm dữ liệu.

**10. Có nên tin KeyInfo.KeyValue tự khai trong XML?** — Không. Cần xác minh trust/key identity độc lập.

**11. XMLSignature.validate() true có tự ngăn mọi signature wrapping?** — Không. Phải kiểm tra target structure, ID uniqueness và business node binding.

**12. DOMValidateContext có nên reuse sau khi DOM bị sửa?** — Không. Kết quả có thể cached; tạo parse/context mới.

**13. Secure validation thay thế parser XXE protection không?** — Không. Cần cả JAXP parser settings và XMLDSig policy.

**14. Demo có kiểm thử với database hay external URL không?** — Không. Chỉ chạy trong JDK, có same-document reference và các negative tests.

## 17. Nguồn tài liệu chính thức còn hiệu lực

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html): cấu trúc XMLDSig, ký/xác minh và secure-validation policy.
- [XMLSignatureFactory — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): factory và các phương thức `newReference`, `newSignedInfo`.
- [SignedInfo — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignedInfo.html): C14N, SignatureMethod, getReferences.
- [Reference — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, transforms, DigestValue và calculated digest.
- [XMLSignature — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): sign, validate và cache behavior.
- [DOMSignContext — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html): private key và vị trí chèn Signature.
- [DOMValidateContext — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): validating key, secureValidation và ID registration.
- [URIDereferencer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/URIDereferencer.html): tùy chỉnh xử lý Reference URI.
- [DigestMethod — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/DigestMethod.html): SHA-256.
- [SignatureMethod — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html): RSA-SHA256.
- [JAXP Security Guide — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): xử lý XML không tin cậy và hạn chế external access.
- [XMLDSig package — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml.crypto/javax/xml/crypto/dsig/package-summary.html): xác nhận API tương thích Java 17.

**Ghi nhớ:** `XMLSignatureFactory` tạo `SignedInfo` và `Reference`. `SignedInfo` là phần được ký số, còn `Reference` định danh đúng dữ liệu cần bảo vệ bằng digest. Muốn tin XML trong ứng dụng thật phải đồng thời **verify SignatureValue và Reference digest**, tin đúng signer public key, khóa external URIs/XXE, kiểm tra ID/namespace/target business element, và không dùng kết quả validation cached sau khi sửa DOM.
