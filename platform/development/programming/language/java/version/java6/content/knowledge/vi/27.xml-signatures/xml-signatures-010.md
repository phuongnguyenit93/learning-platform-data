# Kiểm thử chữ ký XML: sửa đổi nội dung, sai khóa và tham chiếu không mong muốn (Java 17+)

## 1. Vì sao “XMLSignature.validate() trả true” vẫn có thể chưa đủ?

Trong hệ thống trao đổi hóa đơn điện tử, hợp đồng, thông điệp nghiệp vụ hoặc chứng từ XML, chữ ký số giúp kiểm tra **tính toàn vẹn của những dữ liệu được tham chiếu** và tính hợp lệ của chữ ký trên phần `SignedInfo`. Tuy nhiên, một thông điệp có thể **được ký hợp lệ về mặt toán học nhưng lại không bảo vệ đúng phần tử nghiệp vụ mà ứng dụng định dùng**. Đây là lý do kiểm thử XML Signature không thể chỉ có một “happy path” và một lời gọi `signature.validate(context)`.

Ba nhóm kiểm thử trọng tâm:

1. **Sửa đổi nội dung đã ký:** thay số tiền hoặc mã đơn hàng nhưng giữ nguyên chữ ký. Kỳ vọng phần digest của `Reference` không khớp, nên core validation thất bại. Riêng `SignatureValue` vẫn có thể **true** vì `SignedInfo` chưa bị sửa.
2. **Sai khóa xác minh:** dùng public key khác với public key tương ứng private key đã ký. Kỳ vọng `SignatureValue` thất bại; phần `Reference` có thể vẫn true vì nội dung XML chưa đổi. Đừng nhầm đây với “tệp không nguyên vẹn” — đó là hai điều kiện khác.
3. **Tham chiếu không mong muốn:** XML có chữ ký RSA-SHA256 **hoàn toàn hợp lệ** nhưng `Reference URI` chỉ tới `<Memo>` thay vì `<Invoice>`, hoặc có thêm một `Reference` không được giao thức chấp nhận. Kỳ vọng **core có thể true**, nhưng **business verification phải reject** trước khi sử dụng dữ liệu.

Các kịch bản đi kèm:
- **External Reference URI** như `https://example.invalid/untrusted`: từ chối **trước dereference**, không mở network/file chỉ để thử xem signature có hợp lệ.
- **Duplicate ID / signature wrapping:** từ chối khi có nhiều nodes có thể khớp với ID nghiệp vụ, hoặc dữ liệu ứng dụng sử dụng không phải dữ liệu đã được ký.
- **DTD/XXE:** chặn từ **giai đoạn DOM parser**, vì `DOMValidateContext` không phải lớp bảo vệ XML parser đã chạy trước đó.
- **XMLSignature/Reference cache:** nếu cần thử dữ liệu sửa đổi, dùng **DOM mới và DOMValidateContext mới**, không thay DOM rồi gọi lại trên `XMLSignature` đã cache kết quả.

Trong Java SE hiện hành, các API còn được hỗ trợ thuộc **`java.xml.crypto`** và **`java.xml`**. Ví dụ sử dụng Java **17+**, `javax.xml.crypto.dsig.XMLSignature`, `XMLSignatureFactory`, `DOMSignContext` và `DOMValidateContext`. `javax.xml.crypto.*` là package đúng trong Java SE 25, không cần một thư viện XMLDSig legacy.

## 2. Mô hình kiểm thử: ba lớp điều kiện phải cùng đúng

~~~text
          XML nhận được (bytes)
                   |
             DOM parser an toàn
                   |
               Cấu trúc XML?
                   |
              Định danh ID?
                   |
              1 Signature?
                   |
        DOMValidateContext(trustedKey, Signature)
                   |
          XMLSignatureFactory.unmarshal
                   |
          kiểm tra signed policy
          Reference URI / số Reference /
          thuật toán / transforms
                   |
            Chỉ URI được phép
                   |
            Core XMLDSig validate
              /             \
    SignatureValue        Reference digest(s)
       đúng?                  đúng?
              \             /
                cả hai đúng?
                   |
          Key trust / authorization
                   |
       đúng signed business element?
                   |
             ACCEPT / REJECT
~~~

Một đơn vị kết quả nên phân biệt rõ:

| Trạng thái | Ý nghĩa | Chấp nhận nghiệp vụ? |
| --- | --- | --- |
| `SignatureValue=true` | Chữ ký trên canonicalized `SignedInfo` xác minh được với public key đang dùng | **Chưa đủ** |
| `Reference=true` | Digest của dữ liệu `Reference` sau transforms khớp | **Chưa đủ** |
| `core=true` | XML Signature core validation đúng, gồm SignatureValue và các References | **Chưa đủ** |
| `core=true, policy=false` | Chữ ký toán học đúng nhưng ký sai phần tử, sai tập References hoặc key identity không hợp quy định | **Không** |
| `evaluated=false` | Validator cố ý **không chạy crypto/dereference** vì URI, thuật toán hoặc cấu trúc không được phép | **Không** |
| `accepted=true` | Core hợp lệ **và** chính sách ứng dụng xác nhận khóa tin cậy, đúng signed target, cấu trúc, IDs, số References, thuật toán | **Có**, nếu các điều kiện nghiệp vụ khác cũng đúng |

**Không đánh đồng “chưa kiểm tra” với “đã kiểm tra và sai”.** Trong ví dụ chạy ở phần 6, `Verdict.evaluated` tách riêng hai trạng thái. Trường hợp URI external bị từ chối trước cryptographic validation trả `evaluated=false`; nó không gửi một request mạng và cũng không kết luận giá trị digest external.

### Vì sao `SignatureValue` và `Reference` độc lập?

`SignedInfo` chứa danh sách `Reference URI` và các digest đã được tính. `SignatureValue` là chữ ký khóa riêng trên canonicalized `SignedInfo`. Do đó:

~~~text
Invoice gốc: amount = 125.50
Reference digest trên #invoice-42 -> D1
SignedInfo chứa D1
PrivateKey ký SignedInfo -> SignatureValue S

Attacker sửa amount = 999.99, không sửa SignedInfo/S:
    SignatureValue S vẫn khớp SignedInfo -> true
    Reference digest thực tế D2 != D1 -> false
    XMLSignature.validate(...) -> false
~~~

Ngược lại, dùng public key khác vẫn có thể đọc và hash XML thành D1, nên `Reference=true`, nhưng public key đó không xác minh được chữ ký S, nên `SignatureValue=false`.

**Một lỗi nghiêm trọng** là chỉ gọi:

~~~java
boolean ok = signature.getSignatureValue().validate(context);
~~~

rồi xem đây là “nội dung XML còn nguyên vẹn”. Method này **chỉ** kiểm tra `SignatureValue`. Để xác nhận XMLDSig core, gọi **`signature.validate(context)`** với context đã cấu hình; nếu cần diagnostics, kiểm tra thêm từng `Reference.validate(context)` nhưng **không** dùng chúng riêng lẻ thay core+policy.

## 3. Test matrix tối thiểu cho XML Signature

| Mã test | Đầu vào/thay đổi | SignatureValue | Reference(s) | Core | Kỳ vọng policy |
| --- | --- | --- | --- | --- | --- |
| T0 | XML nguyên bản, trusted key, đúng URI | true | true | true | **ACCEPT** |
| T1 | Sửa giá trị `Amount` của invoice đã ký | true | false | false | REJECT |
| T2 | Dùng public key khác | false | true | false | REJECT |
| T3 | Ký hợp lệ `#memo-7` thay cho `#invoice-42` | true | true | true | **REJECT** |
| T4 | Ký cả `#invoice-42` và `#memo-7` nhưng contract chỉ cho 1 Reference | true | true | true | **REJECT** |
| T5 | Thay URI thành `https://example.invalid/untrusted` | Không chạy | Không chạy | Không chạy | **REJECT trước dereference** |
| T6 | Thêm node có `Id="invoice-42"` trùng | Không chạy | Không chạy | Không chạy | **REJECT cấu trúc** |
| T7 | XML có DTD/external entity | Không parse thành DOM | Không chạy | Không chạy | **REJECT parser** |

**Giới hạn của bảng:** kết quả true/false phía SignatureValue/Reference là **kỳ vọng của chương trình kiểm thử cụ thể** bên dưới, trong đó chỉ thay đúng một điều kiện mỗi lần và dùng một signature đã được sinh hợp lệ. Không có quy tắc rằng *mọi* tài liệu bị sửa đều cho SignatureValue true: nếu sửa luôn `SignedInfo` hoặc `SignatureValue`, SignatureValue sẽ thất bại; nếu sửa phần **không thuộc Reference**, core có thể vẫn true mà business policy phải xem xét.

T3 và T4 đặc biệt quan trọng: việc ký nhầm phần tử có thể xảy ra do cấu hình sai, mapping nhầm ID, một XML từ nguồn không tin cậy, hoặc signature-wrapping/payload-confusion. Ứng dụng không được cho phép bản ghi invoice chỉ vì **có một chữ ký hợp lệ ở nơi nào đó trong XML**.

## 4. Thiết kế tài liệu test có ranh giới rõ ràng

Ví dụ có một root `Envelope` chứa hai phần tử:

~~~xml
<d:Envelope xmlns:d="urn:demo:documents">
  <d:Invoice Id="invoice-42">
    <d:Amount>125.50</d:Amount>
  </d:Invoice>
  <d:Memo Id="memo-7">Unrelated note</d:Memo>
  <!-- XML Signature được chèn làm child thứ ba của Envelope -->
</d:Envelope>
~~~

Đây là **sơ đồ cấu trúc trước khi ký**, không phải output XML đầy đủ. Chương trình chạy:
- Đăng ký hai attributes `Id` trong context bằng `setIdAttributeNS(element, null, "Id")`.
- Tạo `Reference URI="#invoice-42"` cho trường hợp đúng; tạo `#memo-7` hoặc hai References cho negative tests.
- Tạo chữ ký dưới `Envelope`, **bên ngoài `Invoice`** và `Memo`. Vì `Signature` không nằm trong nội dung của phần tử `Invoice` được tham chiếu, trường hợp này **không cần `Transform.ENVELOPED`**.
- Dùng **SHA-256** cho digest và **RSA-SHA256** cho chữ ký, canonicalization inclusive.
- Khai báo namespace prefix `d` **trước khi ký**, tránh việc serializer bổ sung namespace context sau khi tạo digest.
- Sau ký, serialize sang bytes và **parse DOM mới** trước khi validate. Đây là điểm quan trọng để phát hiện lỗi canonicalization/namespace thường bị bỏ qua trong unit test chỉ làm việc với cùng một DOM.

**Đây là một chữ ký same-document đặt ngoài signed element**, không phải ví dụ enveloped signature trên chính Invoice. Nếu chữ ký được chèn **bên trong** phần tử tham chiếu (enveloped signature), cần cân nhắc `Transform.ENVELOPED` để loại chữ ký ra khỏi dữ liệu trước khi tính digest. Không tự sao chép transform của ví dụ này sang mọi sơ đồ XMLDSig.

### Ai là chủ sở hữu trust?

Trong test, `KeyPairGenerator` sinh một cặp RSA key; private key chỉ dùng ở `DOMSignContext`. Khi verify, caller truyền `signer.getPublic()` hoặc một public key cố ý sai; **không có `KeyInfo` trong XML**. Cách này làm rõ nguyên tắc: ứng dụng **không tin public key tùy ý do XML tự cung cấp**.

Trong production, trusted key thường đến từ keystore/truststore, PKIX certificate path hoặc hệ thống KMS/PKI đã xác minh identity/role. Điều kiện `SignatureValue=true` với bất kỳ public key nào người gửi tự đưa vào không đủ để xác thực người ký.

## 5. Các API và invariants hiện hành cần kiểm tra

### `DOMSignContext` và `DOMValidateContext`

~~~java
DOMSignContext signing =
        new DOMSignContext(privateKey, envelopeElement);
signing.setIdAttributeNS(invoiceElement, null, "Id");
xmlSignature.sign(signing);

// Bên nhận phải tạo context MỚI sau khi parse:
DOMValidateContext verification =
        new DOMValidateContext(trustedPublicKey, signatureElement);
verification.setIdAttributeNS(invoiceElement, null, "Id");
verification.setProperty(
        "org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
XMLSignature parsed = factory.unmarshalXMLSignature(verification);
boolean core = parsed.validate(verification);
~~~

Đây là **đoạn minh họa trong method** với `privateKey`, `envelopeElement`, `invoiceElement`, `signatureElement`, `xmlSignature` và `factory` đã khởi tạo, import các class tương ứng. Không thể chạy độc lập. Khi ký, context trỏ parent để thêm chữ ký; khi verify, context trỏ **chính nút Signature**.

`setIdAttributeNS` giúp same-document `Reference URI="#..."` tìm đúng element. Trong DOM, một attribute tên `Id` không tự động trở thành ID chỉ vì tên của nó; context cần ánh xạ rõ. Điều đó **không thay thế** kiểm tra ID **duy nhất**, element location hoặc XML schema: một attacker có thể đưa thêm attribute/nút cùng tên khiến code chọn sai phần tử.

### `XMLSignature.validate` có cache

Javadoc Java SE 25 ghi:
- `XMLSignature.validate(context)` chỉ tính core validation **ở lần gọi đầu** trên đối tượng đó; các lần sau trả về **kết quả cache**.
- `XMLSignature.SignatureValue.validate(context)` cũng cache.
- `Reference.validate(context)` chỉ tính digest validation lần đầu, sau đó trả kết quả cache.

**Vì vậy các negative tests phải parse lại bytes** hoặc tạo DOM/`DOMValidateContext`/unmarshalled `XMLSignature` mới cho mỗi case. Không viết:

~~~java
boolean first = signature.validate(context);
amountElement.setTextContent("999.99");
boolean second = signature.validate(context); // Có thể trả kết quả cached!
~~~

Đây là **anti-pattern được chú thích**, không phải kiểm thử đáng tin. Ở ví dụ runnable, mỗi trường hợp lấy `parse(goodBytes)` để có một cây DOM mới, hoặc sinh một signed fixture mới từ đầu. Mỗi test case độc lập.

### `Reference URI`, số lượng và algorithm policy

Một profile invoice có thể yêu cầu **chính xác một Reference**:

~~~java
List<? extends Reference> refs = signature.getSignedInfo().getReferences();
if (refs.size() != 1
        || !"#invoice-42".equals(refs.get(0).getURI())) {
    throw new SecurityException("Unexpected Reference");
}
~~~

Đoạn minh họa trong method, các objects đã có. **Không** coi “ít nhất một Reference trỏ đúng invoice” là đủ nếu profile không cho phép extra references; một chữ ký có thêm Reference tới dữ liệu không cần thiết vẫn core-valid nhưng cấu trúc không đúng giao thức. Với profile yêu cầu nhiều References, định nghĩa **allowlist chính xác theo URI/algorithm/transforms/target** thay vì áp rule một Reference cho mọi hệ thống.

Lựa chọn kiểm thử **không mở URI external**. Trước khi gọi `signature.validate(context)` hay `ref.validate(context)`, phải giới hạn references theo trust policy. Dữ liệu ngoài document cần allowlist/bounded resolver riêng nếu thật sự bắt buộc; không dùng `URIDereferencer` tải `file:`/`http:`/`https:` tùy ý.

## 6. Chương trình Java 17+ chạy được: bộ negative tests đầy đủ

Tạo file **`XmlSignatureAdversarialTests.java`**. Chỉ cần JDK 17+, không cần Maven, Bouncy Castle, internet, file chứng thư hay database. Mã sử dụng Java `record`, `DOM`, `javax.xml.crypto.dsig`, `JAXP` và RSA từ JDK.

**Các nguyên tắc trong mã:**
- `secureBuilder()` cấm DTD/external entities và bật namespace awareness.
- `sign(...)` ký các URI do **bộ test** chỉ định.
- `serialize(...)` và `parse(...)` mô phỏng bytes được chuyển giữa signer và verifier.
- `checkStructure(...)` yêu cầu đúng root, đúng số node, đúng thứ tự, ID duy nhất theo profile nhỏ.
- `verify(...)` unmarshal dưới secureValidation và **chỉ cryptographically evaluate** URI nội bộ **`#invoice-42`** hoặc **`#memo-7`** đã được fixture biết trước; bất kỳ URI khác đều trả `evaluated=false`, **không dereference**.
- **Business policy nghiêm ngặt hơn:** chỉ chấp nhận **chính xác một `Reference URI="#invoice-42"`**.
- `main` chạy 8 kịch bản với các fixtures độc lập: đúng, tamper, wrong key, wrong target, extra ref, external URI, duplicate ID, DOCTYPE.

**Chỉ dùng `#memo-7` trong test-only cryptographic evaluation** để *chứng minh core=true nhưng nghiệp vụ sai*. Production không nên giữ một “allowlist rộng để test” rồi vô tình chấp nhận `Memo`; acceptance ở cuối chỉ cho `Invoice`.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.crypto.dsig.CanonicalizationMethod;
import javax.xml.crypto.dsig.DigestMethod;
import javax.xml.crypto.dsig.Reference;
import javax.xml.crypto.dsig.SignatureMethod;
import javax.xml.crypto.dsig.SignedInfo;
import javax.xml.crypto.dsig.XMLSignature;
import javax.xml.crypto.dsig.XMLSignatureFactory;
import javax.xml.crypto.dsig.dom.DOMSignContext;
import javax.xml.crypto.dsig.dom.DOMValidateContext;
import javax.xml.crypto.dsig.spec.C14NMethodParameterSpec;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class XmlSignatureAdversarialTests {
    private static final String NS = "urn:demo:documents";
    private static final String INVOICE_ID = "invoice-42";
    private static final String MEMO_ID = "memo-7";

    record Verdict(
            boolean evaluated, boolean core,
            boolean signatureValue, boolean references,
            boolean accepted) {
        static Verdict rejectedBeforeCrypto() {
            return new Verdict(false, false, false, false, false);
        }
    }

    static DocumentBuilder secureBuilder() throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newDefaultNSInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override public void fatalError(SAXParseException error)
                    throws SAXException {
                throw error;
            }
        });
        return builder;
    }

    static Document createDocument() throws Exception {
        Document doc = secureBuilder().newDocument();
        Element root = doc.createElementNS(NS, "d:Envelope");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:d", NS);
        doc.appendChild(root);

        Element invoice = doc.createElementNS(NS, "d:Invoice");
        invoice.setAttribute("Id", INVOICE_ID);
        Element amount = doc.createElementNS(NS, "d:Amount");
        amount.setTextContent("125.50");
        invoice.appendChild(amount);
        root.appendChild(invoice);

        Element memo = doc.createElementNS(NS, "d:Memo");
        memo.setAttribute("Id", MEMO_ID);
        memo.setTextContent("Unrelated note");
        root.appendChild(memo);
        return doc;
    }

    static void sign(Document doc, KeyPair signer, String... referenceUris)
            throws Exception {
        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        List<Reference> refs = new ArrayList<>();
        for (String uri : referenceUris) {
            refs.add(f.newReference(uri,
                    f.newDigestMethod(DigestMethod.SHA256, null),
                    null, null, null));
        }
        SignedInfo info = f.newSignedInfo(
                f.newCanonicalizationMethod(CanonicalizationMethod.INCLUSIVE,
                        (C14NMethodParameterSpec) null),
                f.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                refs);
        XMLSignature signature = f.newXMLSignature(info, null);

        Element root = doc.getDocumentElement();
        Element invoice = (Element) doc.getElementsByTagNameNS(NS, "Invoice").item(0);
        Element memo = (Element) doc.getElementsByTagNameNS(NS, "Memo").item(0);
        DOMSignContext context = new DOMSignContext(signer.getPrivate(), root);
        context.setIdAttributeNS(invoice, null, "Id");
        context.setIdAttributeNS(memo, null, "Id");
        context.setDefaultNamespacePrefix("ds");
        signature.sign(context);
    }

    static byte[] serialize(Document doc) throws Exception {
        TransformerFactory f = TransformerFactory.newDefaultInstance();
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        Transformer t = f.newTransformer();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        t.transform(new DOMSource(doc), new StreamResult(bytes));
        return bytes.toByteArray();
    }

    static Document parse(byte[] bytes) throws Exception {
        return secureBuilder().parse(new ByteArrayInputStream(bytes));
    }

    static Element only(Document d, String namespace, String localName) {
        NodeList nodes = d.getElementsByTagNameNS(namespace, localName);
        if (nodes.getLength() != 1) {
            throw new SecurityException("Expected exactly one " + localName);
        }
        return (Element) nodes.item(0);
    }

    static void checkStructure(Document doc, Element invoice, Element memo,
                               Element signature) {
        Element root = doc.getDocumentElement();
        if (!NS.equals(root.getNamespaceURI())
                || !"Envelope".equals(root.getLocalName())
                || invoice.getParentNode() != root
                || memo.getParentNode() != root
                || signature.getParentNode() != root
                || !INVOICE_ID.equals(invoice.getAttribute("Id"))
                || !MEMO_ID.equals(memo.getAttribute("Id"))
                || root.getElementsByTagNameNS(NS, "Amount").getLength() != 1) {
            throw new SecurityException("Unexpected document structure");
        }
        int invoiceIds = 0, memoIds = 0;
        NodeList elements = doc.getElementsByTagName("*");
        for (int i = 0; i < elements.getLength(); i++) {
            Element e = (Element) elements.item(i);
            if (INVOICE_ID.equals(e.getAttribute("Id"))) invoiceIds++;
            if (MEMO_ID.equals(e.getAttribute("Id"))) memoIds++;
        }
        if (invoiceIds != 1 || memoIds != 1) {
            throw new SecurityException("Duplicate or missing Id");
        }
        // Strict profile: exactly three root element children in this order.
        Element first = null, second = null, third = null;
        int count = 0;
        for (Node n = root.getFirstChild(); n != null; n = n.getNextSibling()) {
            if (n.getNodeType() == Node.ELEMENT_NODE) {
                if (++count == 1) first = (Element) n;
                if (count == 2) second = (Element) n;
                if (count == 3) third = (Element) n;
            } else if (n.getNodeType() == Node.TEXT_NODE
                    && !n.getTextContent().isBlank()) {
                throw new SecurityException("Unexpected root text");
            }
        }
        if (count != 3 || first != invoice || second != memo
                || third != signature) {
            throw new SecurityException("Unexpected root children");
        }
    }

    static Verdict verify(Document doc, PublicKey trustedKey) throws Exception {
        Element invoice = only(doc, NS, "Invoice");
        Element memo = only(doc, NS, "Memo");
        Element signatureNode = only(doc, XMLSignature.XMLNS, "Signature");
        checkStructure(doc, invoice, memo, signatureNode);

        DOMValidateContext context = new DOMValidateContext(trustedKey, signatureNode);
        context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        context.setIdAttributeNS(invoice, null, "Id");
        context.setIdAttributeNS(memo, null, "Id");

        XMLSignatureFactory f = XMLSignatureFactory.getInstance("DOM");
        XMLSignature signature = f.unmarshalXMLSignature(context);
        SignedInfo info = signature.getSignedInfo();
        List<Reference> references = new ArrayList<>();
        for (Object item : info.getReferences()) {
            references.add((Reference) item);
        }

        if (!SignatureMethod.RSA_SHA256.equals(
                    info.getSignatureMethod().getAlgorithm())
                || !CanonicalizationMethod.INCLUSIVE.equals(
                    info.getCanonicalizationMethod().getAlgorithm())
                || references.isEmpty()) {
            return Verdict.rejectedBeforeCrypto();
        }

        // A test-only allowlist: safely evaluate signatures on either local
        // element; business policy BELOW accepts only invoice-42.
        for (Reference ref : references) {
            String uri = ref.getURI();
            if ((!("#" + INVOICE_ID).equals(uri)
                    && !("#" + MEMO_ID).equals(uri))
                    || !DigestMethod.SHA256.equals(
                            ref.getDigestMethod().getAlgorithm())
                    || !ref.getTransforms().isEmpty()) {
                // Never dereference an unfamiliar/file/HTTP URI.
                return Verdict.rejectedBeforeCrypto();
            }
        }

        boolean core = signature.validate(context);
        boolean value = signature.getSignatureValue().validate(context);
        boolean allDigests = true;
        for (Reference ref : references) {
            allDigests &= ref.validate(context);
        }
        boolean exactInvoiceOnly = references.size() == 1
                && ("#" + INVOICE_ID).equals(references.get(0).getURI());

        return new Verdict(true, core, value, allDigests,
                core && value && allDigests && exactInvoiceOnly);
    }

    static byte[] signed(KeyPair signer, String... uris) throws Exception {
        Document d = createDocument();
        sign(d, signer, uris);
        return serialize(d);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072);
        KeyPair signer = generator.generateKeyPair();
        byte[] good = signed(signer, "#" + INVOICE_ID);

        Verdict valid = verify(parse(good), signer.getPublic());
        System.out.println("baseline core: " + valid.core());
        System.out.println("baseline accepted: " + valid.accepted());

        Document tampered = parse(good);
        only(tampered, NS, "Amount").setTextContent("999.99");
        Verdict changed = verify(tampered, signer.getPublic());
        System.out.println("tampered SignatureValue: " + changed.signatureValue());
        System.out.println("tampered Reference: " + changed.references());
        System.out.println("tampered accepted: " + changed.accepted());

        PublicKey other = generator.generateKeyPair().getPublic();
        Verdict wrong = verify(parse(good), other);
        System.out.println("wrong key SignatureValue: " + wrong.signatureValue());
        System.out.println("wrong key Reference: " + wrong.references());
        System.out.println("wrong key accepted: " + wrong.accepted());

        Verdict wrongTarget = verify(
                parse(signed(signer, "#" + MEMO_ID)), signer.getPublic());
        System.out.println("wrong target core: " + wrongTarget.core());
        System.out.println("wrong target accepted: " + wrongTarget.accepted());

        Verdict extraRef = verify(parse(signed(signer,
                "#" + INVOICE_ID, "#" + MEMO_ID)), signer.getPublic());
        System.out.println("extra reference core: " + extraRef.core());
        System.out.println("extra reference accepted: " + extraRef.accepted());

        Document external = parse(good);
        Element ref = only(external, XMLSignature.XMLNS, "Reference");
        ref.setAttribute("URI", "https://example.invalid/untrusted");
        Verdict externalResult = verify(external, signer.getPublic());
        System.out.println("external URI skipped crypto: "
                + !externalResult.evaluated());
        System.out.println("external URI accepted: " + externalResult.accepted());

        Document duplicate = parse(good);
        Element added = duplicate.createElementNS(NS, "d:Extra");
        added.setAttribute("Id", INVOICE_ID);
        duplicate.getDocumentElement().appendChild(added);
        boolean duplicateRejected = false;
        try {
            verify(duplicate, signer.getPublic());
        } catch (SecurityException e) {
            duplicateRejected = true;
        }
        System.out.println("duplicate Id rejected: " + duplicateRejected);

        String dangerous = "<!DOCTYPE Envelope [<!ENTITY xxe SYSTEM "
                + "\"file:///blocked.txt\">]><Envelope>&xxe;</Envelope>";
        boolean dtdRejected = false;
        try {
            parse(dangerous.getBytes(StandardCharsets.UTF_8));
        } catch (SAXException e) {
            dtdRejected = true;
        }
        System.out.println("DOCTYPE rejected: " + dtdRejected);
    }
}
~~~

Trong thư mục có file `XmlSignatureAdversarialTests.java`, chạy:

~~~bash
javac --release 17 XmlSignatureAdversarialTests.java
java XmlSignatureAdversarialTests
~~~

**Stdout chính xác**, đã biên dịch và thực thi trên **OpenJDK 24.0.2** với target Java 17:

~~~text
baseline core: true
baseline accepted: true
tampered SignatureValue: true
tampered Reference: false
tampered accepted: false
wrong key SignatureValue: false
wrong key Reference: true
wrong key accepted: false
wrong target core: true
wrong target accepted: false
extra reference core: true
extra reference accepted: false
external URI skipped crypto: true
external URI accepted: false
duplicate Id rejected: true
DOCTYPE rejected: true
~~~

### Tại sao chương trình không cần `Transform.ENVELOPED`?

Trong `createDocument()`, `Invoice` và `Memo` là các child của `Envelope`, còn `<Signature>` được `DOMSignContext(signer.getPrivate(), root)` thêm như **child khác** của Envelope. `Reference="#invoice-42"` chỉ digest **Invoice**, không chứa chính Signature, nên không có self-reference cycle. Nếu đổi kiến trúc để Signature nằm **trong Invoice được ký**, cần thiết kế lại Reference/transforms và test canonicalization, không dùng nguyên mã.

### Tại sao khai báo namespace trước khi ký?

`root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:d", NS)` đặt binding cho prefix `d` trước `signature.sign`. Khi serialize→parse, namespace context ổn định; digest trên signed node không bị thay bởi việc output writer tự bổ sung prefix declaration sau khi ký. Với các giao thức XML Signature khác (inclusive/exclusive C14N), phải theo canonicalization profile chính thức và kiểm thử interoperability.

### Tại sao có `Verdict.evaluated`?

Với URI ngoài allowlist, code **không gọi** `signature.validate(context)` hoặc `Reference.validate(context)`. Nó trả về `rejectedBeforeCrypto` có `evaluated=false`. Điều này tránh một validator tự dereference `file:`/`http:` chỉ để chẩn đoán. Các cờ core/reference false trong trường hợp ấy là **giá trị phản hồi fail closed**, **không phải một phép digest thực sự đã thất bại**.

### Tại sao test-only allowlist bao gồm `#memo-7`?

Chính sách ứng dụng cuối chỉ cho phép invoice. Nhưng để tạo một **test phản ví dụ** “chữ ký hợp lệ trên Memo”, test-only verifier kiểm tra cryptography với hai **same-document IDs được kiểm soát**. Kết quả `wrong target core: true` chứng minh rằng các điều kiện mật mã không đủ. Cờ `accepted` vẫn false vì URI không phải invoice.

**Không chạy phép test này với các URI ngoài whitelist.** Nếu một môi trường yêu cầu ký nhiều loại XML payloads hợp lệ, định nghĩa profile cho mỗi loại riêng và xác định chính xác dữ liệu nào được phép xử lý.

## 7. Phân tích từng negative test

### T0: baseline — khi nào thật sự được ACCEPT?

Fixture good tạo bằng private key tương ứng trusted public key. Cả `SignatureValue` và digest của `Reference="#invoice-42"` hợp lệ, root/namespace/IDs đúng schema nhỏ. Kết quả:

~~~text
baseline core: true
baseline accepted: true
~~~

Điều này chỉ chứng minh điều kiện **XML cryptographic + application policy trong demo**. Ứng dụng thật còn có certificate chain/role, authorization, anti-replay, thời điểm hiệu lực, amount business rules, tenant boundary, và có thể nhiều profile XMLDSig khác nhau. Trong demo, người ký/khóa được sinh trong cùng process để test deterministic outcome, không phải triển khai PKI.

### T1: sửa nội dung đã ký

Test tạo một **DOM mới** từ bytes good:

~~~java
Document changed = parse(good);
only(changed, NS, "Amount").setTextContent("999.99");
Verdict result = verify(changed, signer.getPublic());
~~~

Đây là đoạn nằm **bên trong main** của ví dụ đầy đủ. `Amount` nằm trong `Invoice` đã được digest; không sửa `SignedInfo` hoặc `SignatureValue`. Kết quả:

~~~text
tampered SignatureValue: true
tampered Reference: false
tampered accepted: false
~~~

Nếu chỉ xem SignatureValue, bạn sẽ bỏ sót nội dung invoice đã thay đổi. Nếu sửa metadata **ngoài** Reference, digest có thể vẫn true: điều đó không phải parser bug mà phản ánh chính xác phạm vi chữ ký. Vì thế ứng dụng phải biết dữ liệu nào là authoritative và ký đủ các trường cần thiết.

### T2: khóa khác

Test tạo một RSA keypair khác:

~~~java
PublicKey wrongKey = generator.generateKeyPair().getPublic();
Verdict result = verify(parse(good), wrongKey);
~~~

Kết quả:

~~~text
wrong key SignatureValue: false
wrong key Reference: true
wrong key accepted: false
~~~

Nội dung XML vẫn nguyên nên Reference digest khớp; nhưng RSA verification trên SignedInfo với public key sai thất bại. **Đừng diễn giải “Reference=true” là người gửi được xác thực**. Nếu app chấp nhận một `KeyValue` tự khai báo trong untrusted `KeyInfo`, attacker có thể dùng keypair của họ và tạo chữ ký toán học hợp lệ; trust phải đến từ nguồn độc lập và đúng business role.

### T3: chữ ký hợp lệ nhưng tham chiếu nhầm Memo

Test sinh **một chữ ký thật** với cùng private key tin cậy, nhưng Reference trỏ `#memo-7`:

~~~java
byte[] wrongTarget = signed(signer, "#memo-7");
Verdict result = verify(parse(wrongTarget), signer.getPublic());
~~~

Kết quả:

~~~text
wrong target core: true
wrong target accepted: false
~~~

Đây là bằng chứng rõ ràng: **XMLDSig core validation đúng không đồng nghĩa phần tử Invoice cần xử lý đã được ký**. `Memo` không phải `Invoice`; business profile đã yêu cầu chính xác `#invoice-42`. Một ứng dụng chỉ kiểm tra core=true rồi đọc `Invoice` có thể xử lý dữ liệu chưa được bảo vệ bởi chữ ký.

**Câu hỏi QA:** sau khi verify, code của bạn có sử dụng *chính node được kiểm tra* hay lại dùng một XPath/DOM query rộng tới một node khác? Đây là nguồn lỗi signature wrapping/signed-element substitution.

### T4: nhiều References hơn hợp đồng cho phép

Fixture signed với **hai References** tới cả Invoice và Memo:

~~~java
byte[] tooMany = signed(signer, "#invoice-42", "#memo-7");
Verdict result = verify(parse(tooMany), signer.getPublic());
~~~

Kết quả:

~~~text
extra reference core: true
extra reference accepted: false
~~~

Không có gì sai về mật mã: cả hai References có digest đúng và SignedInfo được ký bằng private key hợp lệ. Nhưng **profile của demo chỉ cho một Reference**, nên extra reference khiến tài liệu sai policy.

**Không** khẳng định “nhiều References là độc hại trong mọi chuẩn”: XMLDSig cho phép nhiều References. Bài học là **policy phải biết số lượng/tập tham chiếu chính xác**. Ở một giao thức khác, 2 References có thể được yêu cầu; test nên chấp nhận đúng tập mà giao thức quy định và từ chối tập thiếu/thừa/khác target.

### T5: URI bên ngoài — từ chối trước khi mạng/file được chạm

Trong test, chúng ta **thay attribute của Reference trên một DOM mới**, không yêu cầu ký hợp lệ một tài nguyên remote:

~~~java
Document external = parse(good);
Element ref = only(external, XMLSignature.XMLNS, "Reference");
ref.setAttribute("URI", "https://example.invalid/untrusted");
Verdict result = verify(external, signer.getPublic());
~~~

`verify` unmarshal cấu trúc để xem URI, rồi thấy URI ngoài allowlist nội bộ. Nó trả về `evaluated=false` **trước khi gọi bất kỳ validate/dereference nào**:

~~~text
external URI skipped crypto: true
external URI accepted: false
~~~

**Không phát sinh HTTP request và không đọc file ngoài.** Lưu ý XML Signature secure validation của JDK có thêm các restrictions với file/HTTP URI; nhưng không nên chỉ trông chờ implementation mặc định nếu ứng dụng có profile chỉ cho same-document IDs. Ứng dụng phải từ chối ở tầng policy; nếu có detached Reference hợp lệ, dùng `URIDereferencer` đã kiểm soát, allowlist trusted resources, quota bytes/time và audit.

### T6: ID trùng hoặc phần tử được thêm vào

Test thêm một phần tử khác mang `Id="invoice-42"`:

~~~java
Document duplicate = parse(good);
Element extra = duplicate.createElementNS(NS, "d:Extra");
extra.setAttribute("Id", "invoice-42");
duplicate.getDocumentElement().appendChild(extra);
~~~

`checkStructure` phát hiện duplicate/extra node, ném `SecurityException` **trước khi chạy core validation**:

~~~text
duplicate Id rejected: true
~~~

Hành vi này giúp giảm rủi ro **ID ambiguity**, nhưng **không phải bộ chống XML Signature Wrapping hoàn chỉnh**. Một giao thức phức tạp có thể có IDs thuộc namespace khác (`xml:id`, `wsu:Id`), schema ID types, nested wrapper elements hoặc nhiều chữ ký. Tất cả phải được xử lý theo profile, và ứng dụng phải bind **đúng signed element** tới dữ liệu nghiệp vụ.

### T7: DTD/XXE

Parser của demo cấm DTD bằng `DocumentBuilderFactory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)` và hạn chế external access. Khi nhận một payload chứa external entity:

~~~xml
<!DOCTYPE Envelope [
  <!ENTITY xxe SYSTEM "file:///blocked.txt">
]>
<Envelope>&xxe;</Envelope>
~~~

JAXP parser từ chối trước khi XMLDSig verification được chạy:

~~~text
DOCTYPE rejected: true
~~~

**Không nhầm** `DOMValidateContext` với bảo vệ `DocumentBuilderFactory`. Parser unsafe có thể đã gây I/O tới file/network trước khi bạn tạo validation context. Điều kiện fail closed ở parser là một lớp riêng, không thay core XMLDSig validation.

## 8. Signature wrapping: nơi crypto đúng nhưng dữ liệu nghiệp vụ sai

XML Signature Wrapping (XSW) có nhiều biến thể, thường dựa vào **sự khác biệt giữa phần tử chữ ký bảo vệ và phần tử application xử lý**.

Ví dụ khái niệm:

~~~xml
<Envelope>
  <Invoice Id="old-invoice"><Amount>125.50</Amount></Invoice>
  <Signature>
    <!-- Reference URI="#old-invoice", chữ ký hợp lệ trên old-invoice -->
  </Signature>
  <Invoice Id="new-invoice"><Amount>999.99</Amount></Invoice>
</Envelope>
~~~

Đây là **minh họa**, không phải chữ ký XML thực đã ký. Một validator thấy Reference `#old-invoice` và chữ ký hợp lệ. Nhưng nếu business handler lấy **Invoice cuối** hoặc dùng XPath quá rộng, nó có thể xử lý `999.99` dù số tiền ấy chưa nằm trong dữ liệu được ký.

Cách phòng vệ theo tầng:

1. **Chọn root/namespaces/schema chính xác**, giới hạn số lượng các elements cùng vai trò.
2. **Không chọn Signature “đầu tiên” tùy ý** nếu tài liệu có thể có nhiều chữ ký; kiểm tra đúng số lượng và vị trí theo profile.
3. **Duy nhất ID** trong toàn document theo các loại ID được cho phép; khi đăng ký `setIdAttributeNS`, dùng element đã được kiểm tra.
4. **Exact Reference whitelist** về URI, số lượng, algorithm, transforms; từ chối missing/extra/unexpected references.
5. **Bind signed data tới domain data:** lấy dữ liệu từ **đúng DOM Element** đã được Reference bảo vệ, không tự động chọn node khác.
6. **Pin trusted key/PKI policy** từ bên ngoài XML; kiểm tra signer identity/role/tenant.
7. **Không mutate DOM sau unmarshal/validate**; tách parse, check policy, verify và extract business fields trong một scope rõ.
8. **Hạn chế URI dereferencing**: chỉ same-document nếu profile không yêu cầu resource ngoài.
9. **Chặn DTD/XXE, giới hạn file size/depth, transform count, Reference count và thời gian xử lý**.
10. **Kiểm tra ứng dụng ở integration layer**: một chữ ký ký đúng Memo nhưng không ký Invoice phải bị từ chối trước khi tạo payment/order, dù `core=true`.

Một test suite **không có case “core=true nhưng application reject” là chưa đủ** để chứng minh XML Signature được ràng buộc vào dữ liệu nghiệp vụ đúng.

## 9. Các loại lỗi và ý nghĩa chẩn đoán

| Hiện tượng | Phần sai hoặc hành vi | Phản ứng đúng |
| --- | --- | --- |
| `SignatureValue=false`, `Reference=true` | Khóa xác minh sai, SignedInfo/SignatureValue bị thay, algorithm mismatch | REJECT, kiểm tra trust/algorithm |
| `SignatureValue=true`, `Reference=false` | Dữ liệu signed payload, namespace hoặc canonicalized digest thay đổi | REJECT, kiểm tra chính xác signed node |
| `core=true`, Reference trỏ Memo | Chữ ký tốt nhưng sai business target | REJECT bằng exact URI policy |
| `core=true`, quá nhiều References | SignedInfo hợp lệ nhưng sai XML profile | REJECT theo số References cho phép |
| External URI | Có nguy cơ file/network I/O, SSRF/data substitution | Reject trước dereference, không fetch |
| Duplicate ID | Ambiguity/XSW risk | Reject cấu trúc, không tự chọn first match |
| Nhiều `Signature` | Có thể chọn chữ ký hợp lệ không liên quan payload | Reject hoặc áp multi-signature protocol |
| XML DTD/XXE | Tấn công trước bước XMLDSig | Harden DOM parser trước parse |
| `XMLSignatureException` khi validate | Resolver/algorithm/transform/provider error | Fail closed, không coi là thành công |
| `MarshalException` khi unmarshal | XMLDSig cấu trúc không hợp lệ hoặc policy restrictions | Fail closed |
| `SecurityException` từ structure policy | Document không đúng layout/ID | Reject trước nghiệp vụ |
| Core true với attacker KeyInfo | Key tự khai báo chưa được tin | PKIX/truststore/pinned-key policy |
| Core true nhưng replay | Thông điệp cũ vẫn có chữ ký đúng | Nonce/timestamp/sequence/idempotency business policy |

**Có ba loại trạng thái khác nhau** cần thể hiện trong log/metrics: *crypto PASS*, *crypto FAIL*, và *crypto NOT_EVALUATED due to policy*. Không ghi “digest invalid” cho một URI mà validator đã chủ động từ chối trước dereferencing, vì điều đó đánh mất nguyên nhân thực tế.

### Khi một Reference có cached result

`Reference.validate(context)` theo Javadoc cache kết quả lần đầu. Không dùng một đối tượng `Reference` hoặc `XMLSignature` đã validate rồi sửa DOM và validate lại để “test tampering”, vì bạn có thể nhìn lại cached true/false cũ. Mỗi test cần **fixture bytes riêng, parse riêng, context riêng, unmarshal riêng**. Đây cũng là lý do phải kiểm thử serialize→parse, không chỉ DOM tại chỗ.

## 10. Bảo mật parser và secure XMLDSig validation là hai lớp độc lập

### DOM parser

~~~java
DocumentBuilderFactory factory =
        DocumentBuilderFactory.newDefaultNSInstance();
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl", true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
DocumentBuilder builder = factory.newDocumentBuilder();
~~~

Đây là snippet minh họa trong method, cần imports và checked exceptions. Với XML không tin cậy, còn phải đặt maximum payload size, parser/JAXP processing limits, deadline và resource ownership cho InputStream. Không catch lỗi cấu hình security property rồi silently parse với defaults yếu hơn; provider không hỗ trợ essential setting thì **fail closed**.

### XMLDSig secure validation

~~~java
DOMValidateContext context =
        new DOMValidateContext(trustedPublicKey, signatureNode);
context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
~~~

JDK bật secure validation theo mặc định trong provider hiện đại. Policy này hạn chế một số thuật toán yếu, external URIs, transformations và document constructs nguy hiểm. **Không tắt secureValidation** chỉ để chữ ký SHA-1/unknown transform cũ “chạy được”, đặc biệt với dữ liệu đối tác không tin cậy.

**Quan trọng về precedence:** theo Java SE 25 API documentation, **system property** `org.jcp.xml.dsig.secureValidation` có thể được ưu tiên so với giá trị context property. Hãy kiểm soát JVM startup options/`java.security` policy và test runtime configuration; `setProperty(..., true)` không phải giải pháp chống mọi cấu hình JVM bất cẩn.

### Thuật toán và KeyInfo

Test dùng `SignatureMethod.RSA_SHA256`, `DigestMethod.SHA256` và RSA 3072-bit, là những lựa chọn hiện hành để demo. Trong production chọn thuật toán và key lengths theo profile, tiêu chuẩn ngành và lifetime policy, có key rotation/certificate revocation. Một XMLDSig `KeyInfo` có thể mang `KeyValue` hoặc `X509Data` nhưng **không tự xác thực trust chain**.

Đối với phần ký test, private key do test tạo trong RAM, không nhúng vào XML. Đối với nhận dữ liệu thật, `DOMValidateContext` cần key/`KeySelector` chọn từ trust anchors/PKI bên ngoài, kiểm tra authorization. XML signature bảo vệ integrity/authenticity theo public key, **không mã hóa XML** và **không tự chống replay**.

## 11. Mở rộng test suite cho production

### Test sửa nội dung (mutation testing)

Đừng chỉ thay một con số. Cần test cả:
- Sửa text của phần tử đã ký, thay ký tự Unicode, dấu, số thập phân và newline.
- Đổi attribute có ý nghĩa trong signed subtree.
- Đổi prefix/namespace binding, sau đó kiểm tra canonicalization và chính sách XML namespace chính xác.
- Chèn/xóa/move child element bên trong signed target.
- Đổi thứ tự các trường có ý nghĩa theo schema.
- Sửa `SignedInfo`/`SignatureMethod`/`DigestValue`/`SignatureValue` trực tiếp.
- Thêm unsigned elements ở ngoài signed Reference và xác nhận application **không sử dụng** chúng như signed data.
- Sửa một trường ngoài Reference; core có thể vẫn true, và **chính sách ứng dụng phải quyết định** trường ấy có được phép ảnh hưởng tới kết quả nghiệp vụ không.

Không phải mọi thay đổi bytes XML đều phải invalidate chữ ký: canonicalization có thể bỏ qua khác biệt mang tính trình bày theo profile, nhưng **cấu trúc/nội dung signed Reference sau C14N** phải khớp. Định nghĩa invariant theo signed semantic data, không chỉ so raw byte strings.

### Test sai khóa

Ngoài public key từ KeyPair khác, kiểm thử:
- Certificate chain không tới trust anchor cho phép.
- Certificate hết hạn/bị thu hồi theo policy hoặc key usage sai.
- Issuer/subject không có role được ký loại document đó.
- Key cùng loại RSA nhưng ID/signer mapping sai.
- Algorithm mismatch/weak digest hoặc key size không đạt policy.
- Rotation: old key có được chấp nhận trong cửa sổ migration được phê duyệt không.
- Trusted key được lấy từ config/keystore thay vì KeyInfo attacker cung cấp.

**Không tái sử dụng private key production trong unit tests**. Dùng keypair tạm hoặc fixture test keys với mô tả rõ; PKI/OCSP/CRL network integration tests phải có môi trường được kiểm soát, không phụ thuộc vào mạng ngoài vô hạn.

### Test URI/số lượng/transform không mong muốn

- `Reference URI="#invoice-42"` một lần: đúng theo profile demo.
- `Reference URI="#memo-7"`: core true vẫn reject.
- Hai References, một trỏ Invoice một trỏ Memo: core true vẫn reject.
- `Reference URI=""`: cùng document/root, **không tương đương** Invoice; reject nếu policy đòi exact ID.
- `Reference URI="file:///..."`: reject trước dereference.
- `Reference URI="https://..."`: reject trước dereference, không gây SSRF.
- `Reference URI="#missing"`: không có ID mapping/target, fail closed.
- `Reference URI="#invoice-42"` nhưng ID trùng ở hai phần tử: reject.
- `Reference URI` dùng dạng xpointer/XML fragment khác profile: reject nếu không được định nghĩa.
- Thêm `Transform` XPath/XSLT hoặc algorithm chưa allowlist: reject.
- Digest method SHA-1 hoặc signature method yếu bị policy hiện hành chặn: không bật lại legacy để test “thành công”.
- `SignedInfo` có quá nhiều References/transforms: fail theo resource policy và limits.
- Nhiều `Signature` hợp lệ trên những targets khác nhau: chọn theo giao thức hoặc reject, không dùng first match.
- Payload signer identity/tenant khác yêu cầu: reject dù core valid.

Khi test external URI, **không cần thực sự gọi một endpoint**. Mục tiêu là chứng minh verifier **không bước vào đường dereference**. Có thể cài một test `URIDereferencer` ném exception/counter nếu được gọi với unexpected URI, hoặc đơn giản chặn trước `validate` như ví dụ. Đừng tạo test khiến worker CI vô tình đọc private file hoặc gửi HTTP tới môi trường thật.

### Test structural wrapping

Kiểm thử thêm:
- Chèn một `Invoice` khác, có hoặc không có ID.
- Đưa Invoice đã ký sang một wrapper mới và chèn Invoice chưa ký ở vị trí business parser thường đọc.
- Duplicate `Id` với cùng namespace hoặc dạng ID khác (`xml:id`, profile-specific IDs).
- Đổi prefix nhưng giữ URI; parser phải namespace-aware.
- Chèn chữ ký thứ hai trong một subtree.
- Đổi thứ tự Signature so với elements khi profile cấm.
- Làm cho app dùng unsigned amount bằng XPath quá rộng.
- Dùng schema version khác nhưng local names giống.
- Thử DTD/XXE/oversized XML, element depth và số attributes quá mức.

**Nội dung của signed Reference phải là nguồn dữ liệu nghiệp vụ cuối cùng.** Đừng validate một node rồi đọc nội dung từ một node tìm thấy bằng query khác mà không kiểm tra identity.

## 12. Kết nối unit tests với integration tests

Unit test trong chương trình đã kiểm tra behavior thực của JDK XMLDSig, không phải một fake `XMLSignature` trả boolean giả. Nhưng nó vẫn chỉ là một fixture synthetic với keypair trong RAM. Hệ thống thực cần kiểm thử thêm:

| Layer | Test nên có | Mục đích |
| --- | --- | --- |
| DOM parsing | XXE/DTD, entity limits, bytes/depth quotas | Không để parser truy cập ngoại vi |
| Signature structure | Count/position/namespaces/IDs | Chống mơ hồ và XSW |
| XMLDSig | SHA-256/RSA, C14N, Reference digest | Phát hiện tampering và wrong key |
| Reference policy | Exact URIs, number, transforms, algorithms | Không validate nhầm tài liệu |
| PKI/trust | Cert path, issuer, role, validity/revocation | Người ký được chấp nhận |
| Business binding | Amount/order/customer lấy từ signed node | Không đọc unsigned payload |
| Replay protection | Message ID, nonce, timestamp | Không xử lý lại chữ ký cũ |
| Interoperability | Files ký bởi partner/JDK khác | C14N/namespace consistency |
| Resilience | Oversized XML, expensive transforms, timeouts | Không bị DoS/timeout vô hạn |
| Logging | Error type, ref policy decision, sanitized IDs | Điều tra được mà không rò rỉ dữ liệu |

**Một test xanh sau serialize→parse trong cùng JVM không đủ chứng minh interoperability** với hệ thống ký khác: C14N algorithms, comments, namespace attributes, certificate containers, transform types, canonicalization versions và profile XMLDSig có thể khác. Cần known-answer fixtures liên nhà cung cấp, test key/cert riêng, expected accept/reject matrix và security regression tests khi nâng JDK.

### Test isolation

- Mỗi test dùng một `Document`/`DOMValidateContext` mới.
- Không mutate document đang được kiểm tra đồng thời ở thread khác.
- Không share `XMLSignature` instance giữa tests để tránh validation cache.
- Không mở external URI cho test negative.
- Không in private key, raw invoice PII, cert secret hoặc file nội bộ ra stdout/log.
- Không phụ thuộc default provider nếu production dùng provider khác; kiểm tra JDK, XMLSignatureFactory, namespace/algorithm support.
- Assert **cả phần cryptographic và policy result**, không chỉ `true/false` chung.

## 13. Quy trình kiểm chứng trước khi chấp nhận chứng từ XML

~~~text
1. Nhận bytes, authenticated transport và quota.
2. Parse XML bằng DOM factory đã hạn chế DTD/XXE.
3. Kiểm tra root namespace/schema và ID uniqueness.
4. Xác định đúng 1 Signature theo vị trí/profile.
5. Lấy trusted public key từ policy ngoài XML.
6. Tạo DOMValidateContext(trustedKey, signatureNode).
7. Bật XMLDSig secure validation (và kiểm soát JVM policy).
8. Đăng ký đúng ID trên đúng signed element.
9. Unmarshal XMLSignature.
10. Kiểm tra chính xác:
    - SignatureMethod + DigestMethod + CanonicalizationMethod
    - Number of References
    - Exact expected Reference URI(s)
    - Allowed transforms, tuyệt đối không tùy ý HTTP/file.
11. Chỉ sau khi reference policy qua: core signature.validate(ctx).
12. Nếu core false: reject; dùng SignatureValue/Reference diagnostics
    trên context mới và policy-allowed URIs nếu cần.
13. Nếu core true: bind đúng signed element tới domain object.
14. Kiểm tra signer authorization, tenant, amount/schema, anti-replay.
15. Chỉ khi tất cả điều kiện đúng mới thực hiện nghiệp vụ.
~~~

Với những giao thức dùng **nhiều chữ ký**, **nhiều References**, **detached signatures** hoặc **multiple-signature thresholds**, cần tạo profile riêng cho phép đúng mô hình ấy. Không dùng rule “một Reference duy nhất” của demo làm chuẩn chung cho mọi loại XML.

### Đừng tách validation và business read thành hai lần chọn node không liên quan

Sau khi validate invoice `#invoice-42`, hãy đảm bảo application dùng **cùng element Invoice đã đăng ký ID và bị digest bảo vệ**, không gọi một API khác để tìm “Invoice gần nhất” hoặc “Invoice cuối” mà không kiểm tra object identity. Nếu cần chuyển sang DTO, extract value **từ node đã xác nhận signed**, làm validate business constraints rồi persist. Không để một untrusted part của XML điều khiển destination tenant, account ID hoặc amount khi part ấy không được ký.

## 14. Những anti-patterns thường gặp

| Cách làm sai | Vì sao nguy hiểm | Phương án đúng |
| --- | --- | --- |
| Chỉ kiểm tra `SignatureValue.validate` | Không kiểm tra digest payload | `signature.validate` + Reference diagnostics + policy |
| Core=true ⇒ document được chấp nhận | Có thể ký nhầm Memo/unsigned data | Exact target URI và business binding |
| Tin public key từ KeyInfo tự khai báo | Attacker tự tạo keypair/chữ ký | Truststore/pinned key/PKIX ngoài XML |
| Chỉ chọn `Signature[0]` không kiểm count | Chữ ký khác có thể được chèn thêm | Enforce count/placement/profile |
| Chỉ so localName, bỏ namespace | Tag khác schema trông giống nhau | URI + localName |
| Bỏ qua ID duplicate | Signature wrapping ambiguity | Schema/ID uniqueness validation |
| `setIdAttributeNS` trên first element có Id trùng | Có thể map sai signed target | Chỉ đăng ký element đã kiểm tra đúng |
| Accept nếu *một* Reference hợp lệ | Extra/missing Reference có thể bị bỏ qua | Exact expected set và core của toàn SignedInfo |
| Accept URI `""` thay `#invoice-42` | Ký root khác ký đúng invoice | Exact URI policy |
| Validate remote URI để “kiểm thử” | SSRF/file disclosure/DoS | Block trước dereference |
| Reuse XMLSignature sau DOM mutation | Cached validate results | Parse/unmarshal/context mới |
| Bật insecure XML parser | XXE xảy ra trước XMLDSig | Harden DocumentBuilderFactory |
| Tắt secureValidation để chấp nhận SHA-1 | Nới bề mặt tấn công và weak cryptography | SHA-256, profile hiện hành |
| Nới transforms tùy ý | XPath/XSLT DoS/canonicalization confusion | Allowlist transforms/algorithms |
| Bỏ qua certificate role/chain | Crypto true với khóa không được cấp quyền | Authorization/PKI policy |
| Xem XML Signature là mã hóa | Payload vẫn đọc được | Encryption/transport security riêng |
| Xem chữ ký tự chống replay | Thông điệp cũ vẫn valid | ID/nonce/timestamp state |
| Chỉ test valid path | Không chứng minh thất bại đúng | Mutation, wrong key, wrong reference tests |
| So XML bytes sau C14N mù quáng | XML presentation khác không luôn thay digest | Profile-based C14N tests |
| Log raw XML/URI/KeyInfo | Lộ PII hoặc secrets | Sanitized diagnostics/metrics |

## 15. Câu hỏi tự kiểm tra

1. **Vì sao `SignatureValue=true` không đủ?** Vì nó chỉ chứng minh SignedInfo được ký, chưa kiểm digest của payload.
2. **Sửa `Amount` đã ký thường làm phần nào fail?** Reference digest, kéo core về false.
3. **Dùng sai public key làm phần nào fail?** SignatureValue, còn Reference digest có thể vẫn true.
4. **Ký `Memo` bằng trusted private key có thể cho core=true không?** Có.
5. **Vì sao ký Memo vẫn bị reject?** Policy cần chữ ký trên chính Invoice.
6. **Có thể có nhiều References mà core=true không?** Có; profile ứng dụng quyết định cho phép hay không.
7. **Tại sao cần `Verdict.evaluated`?** Tách “không chạy crypto vì policy” khỏi “đã chạy và sai”.
8. **Tham chiếu external có nên được dereference chỉ để kiểm thử không?** Không, phải chặn trước.
9. **`DOMSignContext` nhận parent nào?** Nút DOM nơi chữ ký được thêm vào.
10. **`DOMValidateContext` nhận node nào?** Chính nút `<Signature>`.
11. **`setIdAttributeNS` có tự bảo đảm ID duy nhất không?** Không; app phải kiểm tra.
12. **Sau mutate DOM có nên gọi lại `signature.validate` trên cùng object không?** Không, API cache kết quả.
13. **Tại sao test phải serialize→parse?** Để bắt lỗi namespace/canonicalization/interoperability và có DOM độc lập.
14. **Khi Signature nằm ngoài Invoice, có cần enveloped transform không?** Không cho Reference chỉ ký Invoice không chứa Signature.
15. **Khi chữ ký nằm trong signed element thì sao?** Thường cần enveloped transform theo profile.
16. **Tại sao không tin KeyValue trong `KeyInfo`?** Sender có thể tự cung cấp public key của họ.
17. **XMLDSig có tự chặn XML parser XXE không?** Không, parser phải cấu hình trước.
18. **Property `org.jcp.xml.dsig.secureValidation` có cần kiểm soát ở JVM level không?** Có.
19. **URI `""` và `#invoice-42` có giống nhau không?** Không.
20. **Thay prefix XML nhưng giữ namespace URI có luôn an toàn cho C14N không?** Không được mặc định; kiểm tra canonicalization profile/serialization.
21. **Nếu XML có hai Invoice, code chọn Invoice đầu có đủ không?** Không; phải theo schema và signed identity.
22. **XML Signature có mã hóa invoice không?** Không.
23. **XML Signature có ngăn replay không?** Không tự động.
24. **Khi gặp unsupported transform, validator nên làm gì?** Fail closed, không disable policy mù quáng.
25. **Nếu app chỉ cần ký một Invoice, điều kiện cuối cùng là gì?** Trusted key, core valid, exact one Reference tới đúng Invoice, đúng schema/business binding.
26. **Tại sao test wrong-target core=true là quan trọng?** Nó bắt lớp lỗi business signer-target confusion mà kiểm tra crypto riêng không phát hiện.
27. **Khi external reference được thiết kế hợp lệ, cần gì?** Controlled dereferencer, allowlist nguồn/bytes, size/time quotas và trust policy.
28. **Một unit test ký bằng cùng JDK đã chứng minh interoperability chưa?** Chưa; cần partner fixtures và profile tests.
29. **Khi digest fail nhưng SignatureValue true, có được sửa digest để chấp nhận không?** Không; phải reject và điều tra tampering/canonicalization.
30. **Khi signing key đã hợp lệ nhưng signer không thuộc tenant hiện tại?** Reject theo authorization policy.

## 16. Tham khảo chính thức còn áp dụng

- [Java SE 25 — XMLSignature](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): `validate`, core rules và **cached validation result**.
- [Java SE 25 — XMLSignature.SignatureValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.SignatureValue.html): signature-value verification riêng và cache.
- [Java SE 25 — Reference](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, DigestMethod, transforms, `validate` và cached digest result.
- [Java SE 25 — SignedInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignedInfo.html): danh sách References và signature/canonicalization algorithms.
- [Java SE 25 — DOMSignContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html): signing key, parent và placement của Signature.
- [Java SE 25 — DOMValidateContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): trusted key, signature node và secureValidation property.
- [Java SE 25 — DOMCryptoContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dom/DOMCryptoContext.html): `setIdAttributeNS`, ID mapping và `URIDereferencer`.
- [Java SE 25 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): sinh/unmarshal XML signatures và provider selection.
- [Oracle Java SE 25 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/25/security/java-xml-digital-signature-api-overview-and-tutorial.html): XMLDSig components, secure validation và thực hành signature.
- [Oracle Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): parser FSP, DTD/external access, resource limits.
- [W3C — XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): core validation, SignedInfo, Reference, URI và transforms.
- [W3C — Canonical XML 1.1](https://www.w3.org/TR/xml-c14n11/): canonicalization của XML.
- [OWASP — XML Signature Wrapping](https://owasp.org/www-community/attacks/XML_Signature_Wrapping): mô hình signed-node substitution và kiểm tra target binding.

**Ghi nhớ:** Muốn kiểm thử XML Signature đúng, phải xác minh **ba chuyện tách biệt**: dữ liệu được ký có bị sửa không (`Reference`), chữ ký được tạo bởi khóa tương ứng không (`SignatureValue`), và chữ ký có bảo vệ **đúng dữ liệu được ứng dụng sử dụng** hay không (URI/ID/schema/trust/business policy). **Core validation true có thể cùng tồn tại với việc ký nhầm Memo hoặc một Reference thừa**; đó chính là lý do bộ kiểm thử cần negative cases trên **tampering, wrong key và unexpected references**, cùng các chốt fail-closed trước network dereference và chống signature wrapping.