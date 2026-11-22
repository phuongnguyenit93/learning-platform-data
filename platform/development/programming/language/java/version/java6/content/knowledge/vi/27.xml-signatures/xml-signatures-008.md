# Secure validation và giới hạn tham chiếu ngoài trong XML Digital Signature API

## 1. Vì sao cần secure validation và URI policy?

XML Digital Signature (XMLDSig, JSR 105) cho phép ký/xác minh nội dung XML hoặc dữ liệu được tham chiếu bằng `Reference URI`. API Java hiện hành nằm ở module `java.xml.crypto`, nổi bật là `XMLSignatureFactory`, `XMLSignature`, `Reference`, `DOMSignContext`, `DOMValidateContext` và `URIDereferencer`.

Thử hình dung hệ thống nhận một invoice XML đã ký. Bên gửi có thể đính:

~~~xml
<ds:Reference URI="#invoice-7"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  ...
</ds:Reference>
~~~

Đây chỉ là snippet minh họa, không phải một chữ ký hoàn chỉnh. Ý nghĩa hợp lệ: dữ liệu được bảo vệ nằm tại phần tử có ID được công nhận là `invoice-7`. Nhưng nếu một document không đáng tin được phép chọn `URI="https://..."` hoặc `URI="file:///..."`, bộ xác minh có nguy cơ truy cập URL hoặc tài nguyên cục bộ không mong muốn. Ngay cả khi URI chỉ là fragment `#other`, nó cũng có thể chỉ đến **phần tử khác với dữ liệu nghiệp vụ ứng dụng đang đọc**.

Một verifier an toàn cần **nhiều lớp độc lập**:

1. **Harden XML parser** trước khi DOM được tạo: chặn DTD/external entities, giới hạn bytes/depth/time.
2. **Bật secure validation** để JDK XMLDSig áp giới hạn algorithms, transforms, references và các kiểu URI rủi ro.
3. **Whitelisted reference policy** theo đúng message type: ví dụ chỉ cho phép `#invoice-7`, một reference, SHA-256 và RSA-SHA256.
4. **URIDereferencer hạn chế**: chặn mọi tham chiếu ngoài policy ngay ở bước truy cập dữ liệu.
5. **ID uniqueness và XML structure checks**: không cho XML Signature Wrapping hoặc ký một node trong khi ứng dụng dùng node khác.
6. **Trusted public key selection**: không coi `KeyInfo` trong XML chưa tin là chứng minh danh tính.
7. **Core validation và business authorization**: yêu cầu cả digest và SignatureValue hợp lệ trước khi xử lý dữ liệu đã ký.

> **Secure validation không tự làm mọi tài liệu XML trở nên an toàn.** Nó là lớp giới hạn do provider quản lý; exact URI allowlist và trust/business policy là trách nhiệm của ứng dụng.

Bài học tập trung vào **Java 17+**, không sử dụng các thuật toán ký cũ như MD5/SHA-1. Chương trình đầy đủ ở mục 8 đã biên dịch bằng `javac --release 17` trên JDK 24 và kiểm chứng toàn bộ stdout.

## 2. Bản chất của XMLDSig Reference và secure processing

Trong XMLDSig, phần `SignedInfo` chứa một hoặc nhiều `Reference`. Mỗi Reference khai báo URI, transforms, digest algorithm và DigestValue; ngoài ra, SignedInfo còn khai báo canonicalization algorithm và signature method. Bên nhận cần:

~~~text
Untrusted XML bytes
    |
    v
Hardened namespace-aware DOM parser
    |
    v
Check structure / IDs / expected Reference URIs
    |
    v
DOMValidateContext(trustedPublicKey, approved Signature)
    |
    +--> secureValidation = Boolean.TRUE
    +--> register trusted ID
    +--> restricted URIDereferencer
    |
    v
unmarshalXMLSignature
    |
    v
Check exact algorithm/transform/reference profile
    |
    v
XMLSignature.validate(context)
    |
    +--> Reference digest comparison
    +--> SignatureValue verification
    |
    v
Only consume the exact business element covered by the signature
~~~

**Sự khác nhau giữa hai phép kiểm:**

- `SignatureValue.validate(context)` xác minh chữ ký mật mã trên dạng chuẩn hóa của `SignedInfo`.
- `Reference.validate(context)` xác minh digest của dữ liệu Reference sau khi resolve và áp transforms.
- `XMLSignature.validate(context)` xác minh **core validation** bao gồm chữ ký và các references liên quan.

Nếu attacker sửa amount từ 125 thành 999 nhưng không sửa SignedInfo/SignatureValue, có thể nhận:

~~~text
Signed amount edit validates: false
Signed amount digest validates: false
SignatureValue remains valid: true
~~~

Đó là lý do **không được chỉ gọi `getSignatureValue().validate`** rồi xem toàn bộ payload hợp lệ. Cũng không được dùng những trường nằm ngoài signed references như thể chúng đã được xác thực.

### 2.1. Vai trò các API còn được hỗ trợ

| API | Cách dùng | Biện pháp an toàn |
| --- | --- | --- |
| `XMLSignatureFactory.getInstance("DOM")` | Tạo/unmarshal chữ ký trong DOM | Dùng provider hỗ trợ profile đã kiểm thử |
| `DOMValidateContext` | Context cho public key, signature node, ID, URI resolver | Một context mới cho một validation |
| `setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE)` | Yêu cầu secure mode | Đặt trước khi unmarshal/validate |
| `DOMCryptoContext.setIdAttributeNS` | Đăng ký đúng thuộc tính ID cho Element đã chọn | Không để ID trùng/mơ hồ |
| `XMLSignatureFactory.getURIDereferencer()` | Lấy resolver mặc định | Chỉ delegate khi URI đã được phép |
| `DOMValidateContext.setURIDereferencer` | Override resolution policy | Reject mọi URI ngoài exact allowlist |
| `Reference.getURI` | Xem target URI | Kiểm tra chính xác string theo protocol |
| `Reference.getTransforms` | Các transform được áp trước digest | Whitelist đủ cả số lượng và algorithm |
| `SignedInfo.getSignatureMethod` | Chữ ký trên SignedInfo | Ví dụ `SignatureMethod.RSA_SHA256` |
| `Reference.getDigestMethod` | Hash dữ liệu Reference | Ví dụ `DigestMethod.SHA256` |
| `XMLSignature.validate` | Core validation | Require true mới xử lý dữ liệu |

Java SE `java.xml.crypto` cung cấp các package `javax.xml.crypto`, `javax.xml.crypto.dsig`, `javax.xml.crypto.dsig.dom` và các phần liên quan. XML parser DOM nằm ở `java.xml`. Các API vẫn có hiệu lực trên Java 17+.

## 3. Secure validation mode: mặc định và override

Trong Java XMLDSig:

~~~java
DOMValidateContext ctx =
        new DOMValidateContext(trustedKey, signatureElement);
ctx.setProperty(
        "org.jcp.xml.dsig.secureValidation",
        Boolean.TRUE);
~~~

Đây là snippet, với `trustedKey` là `PublicKey` lấy từ trust policy của ứng dụng và `signatureElement` là DOM Element đã được schema/path kiểm tra.

Tài liệu Oracle Java SE 26 cho biết secure validation **được bật mặc định** trong JDK hiện hành. Có hai nguồn cấu hình liên quan:

- Context property `org.jcp.xml.dsig.secureValidation` là `Boolean` đặt qua `setProperty`.
- Java system property `org.jcp.xml.dsig.secureValidation` có **độ ưu tiên cao hơn** context property. Nếu JVM được cấu hình tắt mode, việc đặt context TRUE không bảo đảm override được.
- Security property `jdk.xml.dsig.secureValidationPolicy` điều khiển policy của JDK implementation, ví dụ giới hạn references/transforms/algorithms. Đây không phải URI allowlist của một message type.

**Đừng tắt mode để chấp nhận chữ ký cũ dùng crypto yếu hoặc biến đổi nguy hiểm.** Thay vào đó, sửa giao thức và cấu hình ký giữa các bên.

Ví dụ fail-closed nếu JVM override không phải giá trị true:

~~~java
String override = System.getProperty(
        "org.jcp.xml.dsig.secureValidation");
if (override != null && !"true".equalsIgnoreCase(override)) {
    throw new SecurityException(
            "JVM override disables secure validation");
}
~~~

Đây là một kiểm tra bổ sung trong demo. Nó không thay thế audit provider/security properties; nó giúp tránh một cấu hình JVM được biết là tắt secure validation.

### 3.1. Hạn chế mặc định do Oracle JDK mô tả

| Mục | Hạn chế trong tài liệu Oracle Java SE 26 | Lưu ý |
| --- | --- | --- |
| XSLT transform | Không cho phép | Tránh transform có thể gây DoS/khả năng truy cập tài nguyên |
| Số `Reference` trong `SignedInfo` hoặc `Manifest` | Không quá **30** | Profile chỉ cần một vẫn nên chỉ cho **một** |
| Số transforms cho một Reference | Không quá **5** | Không đồng nghĩa mọi transform dưới ngưỡng đều an toàn |
| MD5/SHA-1 signatures và MD5 MAC | Từ chối các cấu hình bị chính sách cấm | Dùng thuật toán hiện hành |
| Duplicate `Reference` IDs | Hạn chế các ID trùng | Chưa thay kiểm tra business-element IDs |
| Reference URI `http`, `https`, `file` | Bị cấm | Chưa bao phủ relative/custom schemes hoặc fragment sai |
| RetrievalMethod → RetrievalMethod | Không cho chain như vậy | KeyInfo vẫn cần trust policy |
| RSA/DSA keys dưới 1024 bits | Từ chối | 1024 bits **không phải mức khuyến nghị** cho khóa mới |
| EC keys dưới 224 bits | Từ chối | Chọn độ mạnh theo security policy |

Những con số là **giới hạn mặc định của JDK policy theo tài liệu được trích**, có thể thay đổi theo bản JDK, provider hoặc `java.security`. Không dùng chúng như lời bảo đảm mọi JDK/provider đều triển khai giống nhau.

**Nguyên tắc:** Provider limit là *ceiling bảo vệ chung*; application policy thường cần **nghiêm ngặt hơn**. Nếu invoice schema chỉ có một Reference, chấp nhận 29 References bổ sung vì “vẫn dưới 30” là sai.

### 3.2. Vì sao system property precedence quan trọng?

Nếu chạy ứng dụng với:

~~~sh
java -Dorg.jcp.xml.dsig.secureValidation=false SecureXmlSignatureDemo
~~~

JDK có thể áp override **false**, bất kể code đã gọi `context.setProperty(..., Boolean.TRUE)`. Demo chủ động ném `SecurityException` khi thấy override như vậy, nên không lặng lẽ chuyển sang verify không an toàn.

Trong production, deployment pipeline nên kiểm tra JVM flags, security properties và provider thực tế. Các module mới hoặc bản JDK mới phải chạy regression tests cho signature profile; đừng dựa chỉ vào kết quả pass của một chương trình đơn giản trên máy lập trình.

## 4. Những kiểu Reference URI phải phân biệt

| Reference URI | Diễn giải điển hình | Ví dụ policy `#invoice-7` |
| --- | --- | --- |
| `#invoice-7` | Same-document fragment tới ID được đăng ký | **Allow** |
| `#other` | Same-document fragment tới ID khác | Reject |
| `""` | Same-document root theo XMLDSig processing rules | Reject |
| `https://example.invalid/doc.xml` | External HTTPS | Reject |
| `http://...` | External HTTP | Reject |
| `file:///private/config` | File URI | Reject |
| `../invoice.xml` | Relative URI, có thể resolve theo base URI | Reject |
| `invoice.xml#section` | Relative resource kèm fragment | Reject |
| `data:...` hoặc scheme riêng | Embedded/custom data source | Reject |
| XPointer fragment khác profile | Same-document target theo expression khác | Reject |

Cách lọc sai:

~~~java
if (!uri.startsWith("http")) {
    allow(); // Sai: file:, relative URI, #other... đều lọt.
}
~~~

Đây là **anti-pattern**, hàm `allow()` chỉ là placeholder minh họa hành vi sai, không phải snippet runnable.

Cách đúng khi contract chỉ cho một fragment:

~~~java
private static final String EXPECTED_URI = "#invoice-7";

if (!EXPECTED_URI.equals(reference.getURI())) {
    throw new SecurityException(
            "Reference URI outside allowlist");
}
~~~

So exact string giúp loại cả relative URL, absolute URL, fragment lạ và empty URI. Nếu profile khác thực sự cần external detached data, hãy thiết kế một resolver từ **trusted object store** với ID/authorization/size/timeout allowlist, không cho arbitrary fetch URL.

### 4.1. Không dùng mỗi kiểm tra scheme

Cấm `http/https/file` là hữu ích nhưng chưa đủ nếu provider hỗ trợ relative URI hoặc custom scheme. Ví dụ `../private.xml` không có scheme text nhưng có thể trỏ đến file tùy base URI; `#other` cùng document nhưng có thể dẫn tới node không đúng invoice. Vì vậy policy nên khai báo **tập URI chính xác**, không đoán rằng URI không có dấu hai chấm là an toàn.

### 4.2. Empty URI và enveloped signature

`Reference URI=""` có semantics khác `#invoice-7`: thường bao trùm document root theo processing model. Nếu `Signature` nằm bên trong vùng XML được ký, cần `Transform.ENVELOPED` phù hợp để tránh ký chính signature đang được tạo. Demo đặt chữ ký **cạnh** invoice dưới root, còn signed reference chỉ trỏ tới invoice, nên không cần enveloped transform.

Không thay `#invoice-7` bằng `""` mà giữ nguyên chính sách chọn business node; phạm vi ký thay đổi hoàn toàn.

### 4.3. Chỉ external URI thôi chưa phải rủi ro duy nhất

XML Signature Wrapping có thể dùng **same-document** IDs bị trùng hoặc relocated signed nodes. Validator có thể xác minh một node, còn service đọc node khác. Ngay cả URL allowlist rất chặt cũng không thay việc kiểm tra root, namespace, parent path và ID uniqueness.

## 5. URIDereferencer: lớp chặn tại thời điểm truy cập dữ liệu

Interface hiện hành `javax.xml.crypto.URIDereferencer` có method:

~~~java
Data dereference(
        URIReference reference,
        XMLCryptoContext context)
        throws URIReferenceException;
~~~

Đây là chữ ký API mô tả, không phải class bạn tự định nghĩa. Trong Java DSig:

~~~java
URIDereferencer original =
        factory.getURIDereferencer();

ctx.setURIDereferencer((reference, context) -> {
    if (!"#invoice-7".equals(reference.getURI())) {
        throw new URIReferenceException(
                "External or unknown reference denied");
    }
    return original.dereference(reference, context);
});
~~~

Khi reference là `#invoice-7`, resolver mặc định có thể dùng ID được context đăng ký để lấy cùng-document data. Với URI khác, resolver tùy biến ném exception **trước khi truy cập mạng hoặc filesystem**.

Để tránh rủi ro, code nên có **hai lớp**:

1. Đọc cấu trúc DOM và kiểm Reference URI trước khi unmarshal.
2. Khi verify, cài dereferencer từ chối mọi URI ngoài allowlist, rồi kiểm lại `Reference.getURI()` sau unmarshal.

Điều đó làm rõ trust boundary ngay cả khi sau này có developer thêm một code path gọi `validate`.

### 5.1. `KeyInfo` có thể chứa RetrievalMethod riêng

`KeyInfo` có thể chứa `KeyValue`, `X509Data`, `KeyName` hay `RetrievalMethod`. Một reference đến certificate/key cũng có thể tạo bề mặt external fetch nếu ứng dụng dùng key selector cho phép lấy tùy ý.

Không mặc nhiên xem public key do chính XML đưa vào là trusted. Hãy chọn key từ trusted mapping/keystore/PKIX trust chain theo tenant/partner; chỉ xem `KeyInfo` là hint trong phạm vi đã được kiểm soát.

### 5.2. Nếu business bắt buộc ký detached binary resource

Thay vì để input dẫn trực tiếp tới `https://host/path` hoặc `file:///...`:

- Resolve **resource ID** theo database/object store của server.
- Chỉ cho ID thuộc tenant/partner hiện tại.
- Giới hạn bytes, content type, timeouts và số đối tượng.
- Không follow redirects tùy ý hay truy cập metadata endpoints.
- Đảm bảo binary bytes được hash là chính dữ liệu business dùng.
- Tách trust của key references khỏi resource references.
- Log audit/reference ID không chứa secrets.

Đây là một profile khác với bài demo. Không nới `URIDereferencer` đến mức “URI nào Java cũng đọc được”.

## 6. Strict schema, ID registration và chống wrapping

Một attribute tên literal `Id` không tự trở thành XML-typed ID trong mọi DOM parser. Khi dùng `Reference URI="#invoice-7"`:

~~~java
ctx.setIdAttributeNS(invoiceElement, null, "Id");
~~~

`invoiceElement` phải là DOM `Element` mà ứng dụng đã kiểm tra: đúng namespace, đúng vị trí trong document, đúng ID, không trùng với node khác.

Một policy ví dụ:

| Thành phần | Giá trị bắt buộc |
| --- | --- |
| Root | `{urn:demo:invoice}envelope` |
| Signed business element | Chính xác một `{urn:demo:invoice}invoice`, direct child |
| ID | `Id="invoice-7"` không trùng |
| Signature element | Chính xác một `{http://www.w3.org/2000/09/xmldsig#}Signature`, direct child |
| Reference URI | Chính xác `#invoice-7` |
| Reference count | Chính xác **1** |
| Digest | `DigestMethod.SHA256` |
| SignatureMethod | `SignatureMethod.RSA_SHA256` |
| C14N | `CanonicalizationMethod.EXCLUSIVE` |
| Reference transforms | Chính xác một exclusive C14N |
| Public key | Đã được trust mapping chọn trước validation |
| XML parser | Namespace aware, DTD/external entities disabled |

Nếu thấy thêm một invoice cùng namespace, signature ở vị trí khác hoặc `Id` trùng, từ chối. Đây là guard **dành cho schema demo**; production phải kiểm tra mọi ID-typed attributes theo vocabulary (kể cả `xml:id`/namespaced IDs khi được hỗ trợ), signed target và canonicalization profile.

Lưu ý: Secure validation của JDK có thể kiểm duplicate reference IDs theo policy, nhưng điều đó **không thay kiểm tra toàn bộ custom business IDs**.

## 7. Harden DOM parser trước khi verify

SecureValidation của XMLDSig chạy **sau khi XML bytes đã được parse thành DOM**. Nếu XML parser đã xử lý DTD, external entities hoặc XML bomb ở bước trước, cài secureValidation quá muộn để ngăn side effects đó.

Một cấu hình dùng APIs hiện hành:

~~~java
DocumentBuilderFactory f =
        DocumentBuilderFactory.newInstance();
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

Đây là snippet Java17+ với `DocumentBuilderFactory` và `XMLConstants` imports. Tùy parser provider, một vài feature URIs có thể không được hỗ trợ; đối với security settings bắt buộc, **fail closed**, không catch exception rồi parse bằng cấu hình mặc định.

Bổ sung giới hạn input byte size, entity count/depth, processing deadline và XML structure complexity. Nếu cần serialize/transform XML, cũng cấu hình `TransformerFactory` với secure processing và `ACCESS_EXTERNAL_DTD/ACCESS_EXTERNAL_STYLESHEET` restrictions.

**Namespace URI bản thân chỉ là identifier**, không tự kích hoạt fetch URL. Bề mặt network/file nằm ở external entities, XMLDSig References, RetrievalMethod, XSLT, XML schema imports hoặc cơ chế resolver tương ứng.

## 8. Chương trình Java 17+ độc lập: secure validation và URI allowlist

Mã `SecureXmlSignatureDemo.java` là chương trình đầy đủ, không cần database, file key hay kết nối ngoài:

- Tạo RSA keypair 3072-bit **chỉ cho demo**.
- Ký `invoice Id="invoice-7"` với SHA-256, RSA-SHA256 và exclusive C14N.
- Tạo `DOMSignContext` khi ký và `DOMValidateContext` khi xác minh.
- Bật `secureValidation` và chặn JVM override false.
- Chọn trusted public key do caller cung cấp (không tin `KeyInfo` từ XML).
- Bảo đảm Reference URI chính xác trước unmarshal và tại `URIDereferencer`.
- Serialize XML thành bytes rồi parse lại trước verify để kiểm ID registration.
- Sửa trường signed/unsigned, thử URI HTTP/file/fragment sai, duplicate ID và wrong public key.

### 8.1. Source đầy đủ: `SecureXmlSignatureDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.util.List;
import javax.xml.XMLConstants;
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
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

public final class SecureXmlSignatureDemo {
    static final String NS = "urn:demo:invoice";
    static final String ID = "invoice-7";
    static final String EXPECTED_URI = "#" + ID;

    static DocumentBuilderFactory parser() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature("http://apache.org/xml/features/disallow-doctype-decl",
                true);
        f.setFeature("http://xml.org/sax/features/external-general-entities",
                false);
        f.setFeature("http://xml.org/sax/features/external-parameter-entities",
                false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return f;
    }

    static Document newDocument() throws Exception {
        Document doc = parser().newDocumentBuilder().newDocument();
        Element root = doc.createElementNS(NS, "i:envelope");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
                "xmlns:i", NS);
        doc.appendChild(root);
        Element invoice = doc.createElementNS(NS, "i:invoice");
        invoice.setAttribute("Id", ID);
        Element amount = doc.createElementNS(NS, "i:amount");
        amount.setTextContent("125");
        invoice.appendChild(amount);
        root.appendChild(invoice);
        Element note = doc.createElementNS(NS, "i:note");
        note.setTextContent("original");
        root.appendChild(note);
        return doc;
    }

    static byte[] bytes(Document doc) throws Exception {
        TransformerFactory f = TransformerFactory.newInstance();
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer t = f.newTransformer();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        t.transform(new DOMSource(doc), new StreamResult(out));
        return out.toByteArray();
    }

    static Document parse(byte[] xml) throws Exception {
        return parser().newDocumentBuilder().parse(
                new ByteArrayInputStream(xml));
    }

    static Element oneDirect(Document doc, String namespace, String local) {
        NodeList list = doc.getElementsByTagNameNS(namespace, local);
        if (list.getLength() != 1) {
            throw new SecurityException("Expected exactly one " + local);
        }
        Element result = (Element) list.item(0);
        if (result.getParentNode() != doc.getDocumentElement()) {
            throw new SecurityException("Unexpected location: " + local);
        }
        return result;
    }

    static Element preflight(Document doc) {
        Element root = doc.getDocumentElement();
        if (!NS.equals(root.getNamespaceURI())
                || !"envelope".equals(root.getLocalName())) {
            throw new SecurityException("Unexpected document root");
        }
        Element invoice = oneDirect(doc, NS, "invoice");
        if (!ID.equals(invoice.getAttribute("Id"))) {
            throw new SecurityException("Unexpected business Id");
        }
        int ids = 0;
        NodeList all = doc.getElementsByTagName("*");
        for (int i = 0; i < all.getLength(); i++) {
            Element element = (Element) all.item(i);
            if (ID.equals(element.getAttribute("Id"))) {
                ids++;
                if (element != invoice) {
                    throw new SecurityException("Duplicate business Id");
                }
            }
        }
        if (ids != 1) {
            throw new SecurityException("Business Id is not unique");
        }
        Element sig = oneDirect(doc, XMLSignature.XMLNS, "Signature");
        NodeList refs = sig.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Reference");
        if (refs.getLength() != 1
                || !EXPECTED_URI.equals(
                        ((Element) refs.item(0)).getAttribute("URI"))) {
            throw new SecurityException("Reference URI outside allowlist");
        }
        return invoice;
    }

    static void sign(Document doc, KeyPair keyPair) throws Exception {
        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        Element invoice = oneDirect(doc, NS, "invoice");
        Reference ref = f.newReference(
                EXPECTED_URI,
                f.newDigestMethod(DigestMethod.SHA256, null),
                List.of(f.newTransform(CanonicalizationMethod.EXCLUSIVE,
                        (TransformParameterSpec) null)),
                null, null);
        SignedInfo si = f.newSignedInfo(
                f.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                f.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(ref));
        DOMSignContext ctx = new DOMSignContext(
                keyPair.getPrivate(), doc.getDocumentElement());
        ctx.setDefaultNamespacePrefix("ds");
        ctx.setIdAttributeNS(invoice, null, "Id");
        f.newXMLSignature(si, null).sign(ctx);
    }

    record Result(boolean core, boolean signatureValue,
                  boolean digest, boolean secureRequested) {}

    static Result verify(Document doc, PublicKey trustedKey)
            throws Exception {
        String override =
                System.getProperty("org.jcp.xml.dsig.secureValidation");
        if (override != null && !"true".equalsIgnoreCase(override)) {
            throw new SecurityException(
                    "JVM override disables secure validation");
        }
        Element invoice = preflight(doc);
        Element sigElement =
                oneDirect(doc, XMLSignature.XMLNS, "Signature");
        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        DOMValidateContext ctx = new DOMValidateContext(
                trustedKey, sigElement);
        ctx.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        ctx.setIdAttributeNS(invoice, null, "Id");
        URIDereferencer original = f.getURIDereferencer();
        ctx.setURIDereferencer((reference, context) -> {
            if (!EXPECTED_URI.equals(reference.getURI())) {
                throw new URIReferenceException(
                        "External or unknown reference denied");
            }
            return original.dereference(reference, context);
        });
        XMLSignature signature = f.unmarshalXMLSignature(ctx);
        List<Reference> refs = signature.getSignedInfo().getReferences();
        if (refs.size() != 1
                || !EXPECTED_URI.equals(refs.get(0).getURI())
                || !DigestMethod.SHA256.equals(
                        refs.get(0).getDigestMethod().getAlgorithm())
                || !SignatureMethod.RSA_SHA256.equals(
                        signature.getSignedInfo().getSignatureMethod()
                                .getAlgorithm())
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                        signature.getSignedInfo()
                                .getCanonicalizationMethod()
                                .getAlgorithm())
                || refs.get(0).getTransforms().size() != 1
                || !CanonicalizationMethod.EXCLUSIVE.equals(
                        ((Transform) refs.get(0).getTransforms().get(0))
                                .getAlgorithm())) {
            throw new SecurityException("Unexpected signature profile");
        }
        boolean core = signature.validate(ctx);
        boolean value = signature.getSignatureValue().validate(ctx);
        boolean digest = refs.get(0).validate(ctx);
        return new Result(core, value, digest,
                Boolean.TRUE.equals(ctx.getProperty(
                        "org.jcp.xml.dsig.secureValidation")));
    }

    static boolean blocked(byte[] signed, PublicKey key, String uri)
            throws Exception {
        Document doc = parse(signed);
        Element ref = (Element) doc.getElementsByTagNameNS(
                XMLSignature.XMLNS, "Reference").item(0);
        ref.setAttribute("URI", uri);
        try {
            verify(doc, key);
            return false;
        } catch (SecurityException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair keys = generator.generateKeyPair();
        Document document = newDocument();
        sign(document, keys);
        byte[] signed = bytes(document);

        Result valid = verify(parse(signed), keys.getPublic());
        System.out.println("Secure validation explicitly requested: "
                + valid.secureRequested());
        System.out.println("Local reference validates: " + valid.core());

        Document changedNote = parse(signed);
        oneDirect(changedNote, NS, "note").setTextContent("different");
        System.out.println("Unsigned note edit validates: "
                + verify(changedNote, keys.getPublic()).core());

        Document changedAmount = parse(signed);
        Element amount = (Element) oneDirect(
                changedAmount, NS, "invoice")
                .getElementsByTagNameNS(NS, "amount").item(0);
        amount.setTextContent("999");
        Result bad = verify(changedAmount, keys.getPublic());
        System.out.println("Signed amount edit validates: " + bad.core());
        System.out.println("Signed amount digest validates: " + bad.digest());
        System.out.println("SignatureValue remains valid: "
                + bad.signatureValue());

        System.out.println("HTTP URI blocked before dereference: "
                + blocked(signed, keys.getPublic(),
                        "https://example.invalid/remote.xml"));
        System.out.println("File URI blocked before dereference: "
                + blocked(signed, keys.getPublic(), "file:///private/data"));
        System.out.println("Wrong local URI blocked: "
                + blocked(signed, keys.getPublic(), "#other"));

        Document duplicate = parse(signed);
        Element other = duplicate.createElementNS(NS, "i:other");
        other.setAttribute("Id", ID);
        duplicate.getDocumentElement().appendChild(other);
        try {
            verify(duplicate, keys.getPublic());
            throw new AssertionError("Duplicate ID not rejected");
        } catch (SecurityException expected) {
            System.out.println("Duplicate Id blocked: true");
        }

        KeyPair otherKeys = generator.generateKeyPair();
        System.out.println("Untrusted key validates: "
                + verify(parse(signed), otherKeys.getPublic()).core());
        System.out.println("Demo used no network access: true");
    }
}
~~~

### 8.2. Biên dịch và output đã kiểm thử

Lưu file `SecureXmlSignatureDemo.java`, chạy:

~~~sh
javac --release 17 SecureXmlSignatureDemo.java
java SecureXmlSignatureDemo
~~~

Chỉ cần JDK17+ với `java.xml.crypto` và `java.xml`; không cần database, Maven/Gradle, key file hoặc network. Chương trình đã biên dịch bằng `javac --release 17` trên JDK24 và chạy thành công. **Stdout chính xác gồm 12 dòng:**

~~~text
Secure validation explicitly requested: true
Local reference validates: true
Unsigned note edit validates: true
Signed amount edit validates: false
Signed amount digest validates: false
SignatureValue remains valid: true
HTTP URI blocked before dereference: true
File URI blocked before dereference: true
Wrong local URI blocked: true
Duplicate Id blocked: true
Untrusted key validates: false
Demo used no network access: true
~~~

**Giới hạn kiểm thử:** Các URI HTTP/file bị từ chối ở `preflight`, nên không có network/file IO xảy ra. Đây là mục tiêu của security policy; không tuyên bố đã thử HTTP thực hoặc file thực. RSA keys được tạo tạm, **không có certificate/trust chain thật**.

### 8.3. Giải thích kết quả theo threat model

- **Local reference validates = true:** cùng-document ID được đăng ký đúng, signed invoice nguyên vẹn, public key phù hợp.
- **Unsigned note edit = true:** note nằm ngoài Reference; XMLDSig không bảo vệ trường này. Đừng dùng note để xác thực amount, currency hoặc quyền hạn nếu chưa được ký.
- **Signed amount edit = false:** thay amount làm Reference digest mismatch.
- **SignatureValue remains valid = true:** SignedInfo vẫn chưa đổi; do đó chỉ kiểm SignatureValue sẽ sai.
- **HTTP/file URI blocked = true:** exact allowlist chặn URLs ngoài trước resolver, không fetch bất kỳ tài nguyên nào.
- **Wrong local URI blocked = true:** ngay cả một fragment trong document cũng không được chấp nhận nếu ngoài business profile.
- **Duplicate Id blocked = true:** application path/ID guard từ chối một biến thể wrapping.
- **Untrusted key validates = false:** public key khác signer khiến signature verification thất bại.
- **Secure validation explicitly requested = true:** kiểm tra context property đã được đặt; đây **không phải** một phép đo toàn bộ runtime security property, do đó cần audit system overrides và JDK provider.

### 8.4. Vì sao program cần preflight trước unmarshal?

XMLDSig unmarshal/validate có thể xử lý Reference/transforms. Kiểm cấu trúc XML trước tiên giúp bảo đảm chỉ đúng một chữ ký, một reference và đúng URI, giảm nguy cơ input lạ gây công việc không cần thiết.

Trong code, `preflight` còn kiểm root namespace, invoice path và ID uniqueness. Đó là **schema-specific guard**, không phải giải pháp hoàn chỉnh cho mọi chuẩn WS-Security/XAdES có nhiều ID attribute types. Production phải mở rộng theo schema thực tế mà không bỏ các invariant cần thiết.

## 9. Production design: thêm giới hạn ở những lớp nào?

### 9.1. Network/API boundary

Trước XML parsing:

- Giới hạn request body size, timeouts, concurrent parse operations và content type.
- Xác định expected tenant/message type và nguồn trusted keys.
- Không cho XML chưa xác minh ảnh hưởng tới URL, file path hoặc object-store key.
- Từ chối dữ liệu lớn bất thường thay vì cố parse toàn bộ rồi kiểm size sau.

### 9.2. XML parsing boundary

Bật namespace-aware DOM, tắt DTD/external entities, kiểm parser features và giới hạn entity expansion/depth. Không coi secure XMLDSig mode là một XML parser firewall.

### 9.3. Signature policy boundary

Áp `secureValidation` và whitelist:

- Chính xác message format, `ds:Signature` placement/cardinality.
- URI set và số lượng references.
- Digest/signature/C14N algorithm URIs.
- Transform sequences và optional parameters.
- Trusted verification key và role của signer.
- ID uniqueness và ràng buộc reference target với đúng business node.

### 9.4. URI/resource boundary

Đối với same-document messages, chỉ cho expected ID fragments và không bao giờ fetch external. Nếu detached data là cần thiết, resolver phải được viết riêng dựa trên trusted data store cùng max size, timeouts, authorization và audit; không fallback sang arbitrary URL.

### 9.5. Business boundary

Sau core validation:

- Xác nhận mọi trường có ảnh hưởng tới giao dịch đều **nằm trong signed scope**.
- Kiểm schema, value ranges, currency, tenant, receiver/payee và authorization.
- Kiểm signed nonce/request ID/timestamp và idempotency state để chặn replay.
- Dùng business object được xây từ **chính validated Element**, không chọn một node khác sau verification.

## 10. Một số tình huống sai nguy hiểm

### 10.1. Chỉ chặn `http`

~~~java
boolean allowed = !uri.startsWith("http");
~~~

Đây là anti-pattern: `file:`, relative URL, custom schemes hoặc `#other` đều lọt. Hãy allowlist exact.

### 10.2. Chỉ tin mặc định “max 30 references”

Nếu protocol chỉ cần một Reference, hai References vẫn là input bất thường dù tổng thấp hơn 30. Giới hạn của JDK giảm DoS, **không thay validation nghiệp vụ**.

### 10.3. Cho mọi XPath/XSLT transforms

Transforms ảnh hưởng trực tiếp đến dữ liệu thực sự được digest. Nếu cho attacker lựa chọn transform chain tùy ý, họ có thể thay đổi selection/content hoặc gây tiêu hao tài nguyên. Pin sequence của profile; secure mode cấm XSLT trong JDK policy được tài liệu hóa.

### 10.4. Tin `KeyInfo` do XML cung cấp

Attacker có thể tạo cặp khóa, ký tài liệu và đính public key vào `KeyInfo`. Cryptographic verification với key đó không chứng minh signer đã được cấp quyền. Chọn trusted key từ config/KeyStore/PKIX mapping trước verify.

### 10.5. Không kiểm tra ID trùng

Một chữ ký có thể hợp lệ trên node A trong khi business code đọc node B. Đảm bảo reference target là **đúng Element** được dùng, kiểm unique IDs và expected parent path.

### 10.6. Dùng cùng mutable DOMValidateContext cho nhiều signatures

JDK JavaDoc cảnh báo context và signature object có state riêng; đừng reuse một context cho nhiều signature structures hoặc sửa DOM sau khi unmarshal mà vẫn dùng kết quả cũ. Tạo context cho từng request và hoàn tất verification trước processing.

### 10.7. Hạ `secureValidation` để XML legacy chạy

Không nên tắt mode hoặc nới security property toàn JVM để ký cũ dùng thuật toán yếu được chấp nhận. Nâng cấp protocol với đối tác, hoặc cách ly legacy integration qua security review/allowlist riêng, không phá verifier chung.

## 11. Test matrix cần có

| Tình huống | Kết quả mong đợi |
| --- | --- |
| `#invoice-7` + trusted key + nguyên vẹn | Core true |
| Sửa signed amount | Core false, digest false |
| Sửa unsigned note | Có thể core true; business không tin trường unsigned |
| Wrong public key | SignatureValue/core false |
| Reference `https://...` | Reject **trước fetch** |
| Reference `http://...` | Reject |
| Reference `file:///...` | Reject **trước file read** |
| Reference `../x.xml` | Reject relative URI |
| Reference `#other` | Reject wrong fragment |
| Reference `""` | Reject khi profile chỉ cho `#invoice-7` |
| Thêm Reference thứ hai | Reject |
| Đổi DigestMethod khỏi SHA-256 | Reject |
| Đổi SignatureMethod khỏi RSA-SHA256 | Reject |
| Thêm transform ngoài profile | Reject |
| XSLT transform | JDK secure policy reject |
| Dùng chữ ký MD5/SHA-1 thuộc policy cấm | Reject |
| Duplicate `Id="invoice-7"` | Reject structural preflight |
| Di chuyển signed node vào wrapper | Reject path |
| Đổi namespace root | Reject |
| Thêm `ds:Signature` thứ hai | Reject |
| Parser chứa DTD/XXE | Reject parser security policy |
| Input cực lớn | Reject size/depth/time limit |
| JVM system property false | Demo fail closed |
| Cùng valid request gửi lại | Reject/return stored result theo idempotency policy |
| Certificate không thuộc trusted partner | Trust layer reject |
| Provider/JDK nâng cấp | Security regression tests pass |

Các tests nên chạy trong sandbox/CI với provider thật. Không thử SSRF bằng cách truy cập metadata hoặc file bí mật trên production; policy nên chặn URI ngay trước I/O.

## 12. Chẩn đoán lỗi và logging an toàn

| Kết quả | Cách hiểu |
| --- | --- |
| `XMLSignature.validate()==false` | Có thể digest hoặc SignatureValue sai |
| `Reference.validate()==false` | Dữ liệu referenced hoặc transform digest không khớp |
| `SignatureValue.validate()==false` | Chữ ký trên SignedInfo sai hoặc trusted key không tương ứng |
| `SecurityException` từ preflight | Structure/URI/ID/profile không được phép |
| `URIReferenceException` | Dereferencer không giải tham chiếu được/bị policy chặn |
| `MarshalException` | Unmarshal XML Signature không hợp lệ hoặc bị secure policy ngăn |
| `XMLSignatureException` | Lỗi crypto/transforms/validation |
| `SAXException` | XML parser từ chối input, DTD hoặc malformed XML |
| `ParserConfigurationException` | Parser provider thiếu security configuration cần thiết |

**Fail closed** với tất cả security policy failures. Log type/stage, correlation ID, algorithm identifiers, Reference URI classification và error code, nhưng không log private keys, raw XML chứa PII, thông tin tài khoản hoặc dữ liệu internal file/URL.

Không parse lại XML thành một DOM khác sau validation rồi chọn node bằng `getElementsByTagName(...).item(0)` mà không bảo đảm business data vẫn chính là signed target.

## 13. Câu hỏi tự kiểm tra

**1.** Secure validation có tự chặn mọi URI ngoài không?

**Trả lời:** Không bảo đảm. JDK policy chặn một số schemes, nhưng application vẫn cần exact URI allowlist và restricted dereferencer.

**2.** Tại sao `#other` cũng bị từ chối dù cùng document?

**Trả lời:** Vì nó không phải business element `#invoice-7` theo profile. Same-document không đồng nghĩa signed target hợp lệ.

**3.** Context `Boolean.TRUE` có thắng JVM system property false không?

**Trả lời:** Không. Oracle JDK documentation nêu system property cùng tên có ưu tiên cao hơn context property.

**4.** `jdk.xml.dsig.secureValidationPolicy` dùng để làm gì?

**Trả lời:** Tinh chỉnh một số giới hạn secure XMLDSig do JDK provider áp; không thay exact message-level allowlist.

**5.** Vì sao không coi ngưỡng max 30 references là business policy?

**Trả lời:** Nó là ngưỡng chống tài nguyên quá mức. Một invoice chỉ có một reference phải reject bất kỳ reference thứ hai.

**6.** `URIDereferencer` nên nhận URI nào?

**Trả lời:** Chỉ URI đã nằm trong trusted profile, ví dụ `#invoice-7`; sau đó có thể delegate tới resolver mặc định đối với ID đã đăng ký đúng.

**7.** Tại sao `file:///...` phải bị chặn trước khi validate?

**Trả lời:** Để tránh truy cập tài nguyên local không nằm trong chính sách; không cần đọc file thật mới biết URI không được phép.

**8.** `Id="invoice-7"` có tự được DOM hiểu là type ID không?

**Trả lời:** Không luôn. Dùng schema ID-typing tin cậy hoặc `DOMValidateContext.setIdAttributeNS` cho đúng Element.

**9.** Chỉ `SignatureValue.validate()==true` là đủ chưa?

**Trả lời:** Chưa. Reference digest có thể false nếu signed payload đã thay đổi; phải dùng `XMLSignature.validate`.

**10.** Secure validation có chống XML Signature Wrapping hoàn toàn không?

**Trả lời:** Không. Cần ID uniqueness, schema/path/cardinality và gắn business object với đúng signed node.

**11.** Có cần bảo vệ XML parser riêng không?

**Trả lời:** Có. DTD/XXE/size attacks xảy ra khi parse XML, trước bước XMLDSig secure validation.

**12.** Có thể tin public key trong untrusted `KeyInfo` không?

**Trả lời:** Không. Cần trusted key selection/certificate validation từ nguồn ngoài XML.

**13.** Nếu detached binary reference là yêu cầu thật thì sao?

**Trả lời:** Viết controlled resource resolver với trusted IDs, authorization, size/timeouts và restricted fetch policy; không dùng unrestricted URL.

**14.** Chữ ký hợp lệ có ngăn message replay không?

**Trả lời:** Không. Cần signed request ID/nonce/timestamp và idempotency/replay checks.

**15.** Tại sao demo sửa note mà chữ ký vẫn true?

**Trả lời:** Note nằm ngoài signed Reference; đó là tính đúng của phạm vi ký, nhưng business không được dùng unsigned note như dữ liệu đã xác thực.

**16.** Vì sao demo không phát HTTP request để kiểm external URI?

**Trả lời:** Vì chính sách chặn trước khi dereference; đó là hành vi mong muốn.

**17.** Vì sao cần so exact algorithm URI?

**Trả lời:** Vì XMLDSig dùng identifiers là algorithm URIs; provider hỗ trợ algorithm không có nghĩa nó phù hợp profile của ứng dụng.

**18.** Khi thay JDK/provider có cần test lại không?

**Trả lời:** Có. Secure policies, supported algorithms và error timing có thể khác; chạy integration/security regression.

**Ghi nhớ:** Dùng `DOMValidateContext` với `secureValidation=Boolean.TRUE`, kiểm JVM override, restrict `Reference URI` bằng exact allowlist, đặt `URIDereferencer` chống external I/O, chỉ đăng ký đúng ID của signed element, harden DOM parser, pin transforms/algorithms và dùng trusted public key. **Chỉ core-validating dữ liệu đã nằm đúng signed scope mới được sử dụng cho nghiệp vụ.**

### Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html): secure validation defaults, limits và system property precedence.
- [Oracle Java SE 26 — DOMValidateContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): property, context state, ID.
- [Oracle Java SE 26 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): factory/unmarshal/dereferencer.
- [Oracle Java SE 26 — URIDereferencer](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/URIDereferencer.html): custom URI resolution.
- [Oracle Java SE 26 — Reference](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): digest, URI, transforms.
- [Oracle Java SE 27 — Security Developer's Guide](https://docs.oracle.com/en/java/javase/27/security/index.html): hiện hành tháng 11/2026.
- [W3C — XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core/): canonicalization, URI processing, signed references.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): JAXP parser hardening.
