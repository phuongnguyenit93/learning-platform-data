# DOMSignContext và DOMValidateContext: ký và xác minh chữ ký XML an toàn (Java 17+)

## 1. Bối cảnh: chữ ký số XML không chỉ là một chuỗi Base64

Một ứng dụng Java nhận hóa đơn, tài liệu kinh doanh, phiếu giao dịch hoặc thông điệp XML có thể cần bảo đảm **nội dung được ký chưa bị chỉnh sửa** và **người ký sử dụng khóa được bên nhận tin cậy**. Java SE cung cấp **XML Digital Signature API (JSR 105)** trong module `java.xml.crypto`, với các interface chính trong package `javax.xml.crypto.dsig`.

Khi XML được biểu diễn bằng **DOM (Document Object Model)**, hai lớp có vai trò đặc biệt:

- **`javax.xml.crypto.dsig.dom.DOMSignContext`**: chỉ dẫn quá trình **tạo chữ ký**, gồm khóa dùng để ký và vị trí chèn phần tử `<Signature>` vào cây DOM.
- **`javax.xml.crypto.dsig.dom.DOMValidateContext`**: chỉ dẫn quá trình **đọc và xác minh chữ ký**, gồm khóa/`KeySelector` tin cậy và **nút chữ ký cần kiểm tra** trong cây DOM.

Cả hai kế thừa **`javax.xml.crypto.dom.DOMCryptoContext`** để chia sẻ các cơ chế namespace prefix, ID mapping, base URI, properties, `KeySelector` và `URIDereferencer`. Chúng **không** phải `DocumentBuilder`, **không** tự tạo khóa, và **không** phải chữ ký số. Chữ ký thực được tạo/đọc qua **`XMLSignatureFactory`** và `XMLSignature`.

**Hai câu hỏi cốt lõi:**

1. Khi ký: “Dùng khóa nào? Chèn `<Signature>` vào đâu? Tham chiếu chính xác phần tử nào được bảo vệ?”
2. Khi xác minh: “Đọc `<Signature>` nào? Dùng **khóa được tin cậy từ bên ngoài** nào? Digest của **đúng dữ liệu nghiệp vụ** có khớp không?”

Một phép `signature.validate(context) == true` là **core cryptographic validation**, **không tự suy ra** bên ký đã được cấp quyền thực hiện giao dịch hoặc application đang sử dụng đúng phần tử đã được ký. Phải kiểm tra **trust policy** và chống **XML Signature Wrapping (XSW)**.

### Phân biệt package hiện hành

| Tên | Thuộc module | Vai trò |
| --- | --- | --- |
| `XMLSignatureFactory` | `java.xml.crypto` | Tạo/đọc XML Signature theo mechanism, thường `"DOM"` |
| `XMLSignature` | `java.xml.crypto` | Chứa SignedInfo, SignatureValue, KeyInfo; `sign`/`validate` |
| `SignedInfo` | `java.xml.crypto` | Thông tin tham chiếu, canonicalization và signature method |
| `Reference` | `java.xml.crypto` | Xác định dữ liệu được digest qua URI, transforms |
| `DOMSignContext` | `java.xml.crypto` | Khóa ký + vị trí chèn chữ ký DOM |
| `DOMValidateContext` | `java.xml.crypto` | Khóa xác minh + nút chữ ký DOM |
| `DOMCryptoContext` | `java.xml.crypto` | ID mappings, prefix, URI dereferencer, properties |
| `DocumentBuilderFactory` | `java.xml` | Parse XML thành DOM một cách bảo mật |
| `TransformerFactory` | `java.xml` | Serialize DOM sang bytes nếu cần |

**Tên `javax.xml.crypto.*` vẫn là API Java SE hiện hành trong Java 17+ và Java SE 25**. Không đổi các class này sang một package `jakarta.*` theo suy đoán, không phụ thuộc ví dụ SHA-1 hoặc API lỗi thời. XML Signature là **chữ ký số**, không phải encryption: nội dung XML được ký **không tự trở thành bí mật**.

## 2. Dòng xử lý từ ký đến xác minh

~~~text
          BÊN KÝ                                      BÊN NHẬN
     Document (DOM)                                  bytes XML
          |                                              |
    kiểm tra schema/ID                              parser chống XXE
          |                                              |
   XMLSignatureFactory("DOM")                         Document (DOM)
          |                                              |
    SignedInfo + Reference                       tìm Signature đúng namespace
          |                                              |
     DOMSignContext                              DOMValidateContext
    (PrivateKey, parent)                          (trusted PublicKey, Signature node)
          |                                        + đăng ký đúng ID
    signContext.setIdAttributeNS                         |
          |                                  factory.unmarshalXMLSignature(ctx)
    xmlSignature.sign(ctx)                                |
          |                                       signature.validate(ctx)
    chèn <ds:Signature>                                   |
          |                                   kiểm tra SignatureValue và References
     serialize XML                                       |
          |                                 xác nhận data đúng node, trust, business rules
          v                                              v
       KÝ XONG                                     CHẤP NHẬN / TỪ CHỐI
~~~

**Ký và xác minh là hai context khác nhau.** Trong ví dụ:
- `DOMSignContext` nhận **`PrivateKey` và phần tử DOM parent**, rồi `sign` tạo ra `<Signature>` dưới parent.
- `DOMValidateContext` nhận **`PublicKey` và phần tử `<Signature>`**, sau đó factory **unmarshal** chữ ký và xác minh nó.
- `Reference` dùng URI `#inv-0001` trỏ đến phần tử `Invoice Id="inv-0001"`, **không** trỏ tới bất kỳ phần tử nào chỉ có tên na ná “Invoice”.
- `Transform.ENVELOPED` loại chính phần tử chữ ký đang chèn vào dữ liệu khi tính digest, tránh việc chữ ký tự ký chính nó.

### Ba cấu trúc XML Signature

| Dạng | Vị trí chữ ký | Ví dụ và lưu ý |
| --- | --- | --- |
| **Enveloped** | `<Signature>` nằm **bên trong dữ liệu được ký** | Ví dụ hóa đơn root chứa chữ ký, thường cần `Transform.ENVELOPED` |
| **Enveloping** | Chữ ký chứa dữ liệu được ký, thường trong `<Object>` | Dữ liệu có thể nằm dưới `<Signature>`, cần kiểm tra đúng Reference |
| **Detached** | Chữ ký tách khỏi dữ liệu được ký | Reference có thể trỏ file/URI/đối tượng ngoài; cần chống SSRF, allowlist/cấm external dereference |

Lựa chọn **dạng** chữ ký không do tên `DOMSignContext` quyết định mà do **cây DOM, vị trí chèn và các `Reference`/transforms**. Ví dụ bên dưới dùng **enveloped XML Signature** với URI nội bộ cùng document, tránh mọi external Reference.

## 3. `DOMSignContext` — đúng vị trí chèn và đúng khóa ký

### Constructors đang được hỗ trợ

`DOMSignContext` có các constructors chính:

~~~java
DOMSignContext sign1 = new DOMSignContext(privateKey, parentNode);
DOMSignContext sign2 = new DOMSignContext(
        privateKey, parentNode, nextSiblingNode);

// Nếu dùng KeySelector để chọn khóa ký:
DOMSignContext sign3 = new DOMSignContext(keySelector, parentNode);
DOMSignContext sign4 = new DOMSignContext(
        keySelector, parentNode, nextSiblingNode);
~~~

**Đây là đoạn API minh họa, không phải file Java độc lập**: các biến `privateKey`, `parentNode`, `nextSiblingNode`, `keySelector` phải được tạo hợp lệ trước. Hai overload nhận `Key` thích hợp khi application đã biết chính xác private key cần ký; overload nhận `KeySelector` cho trường hợp lựa chọn khóa được quản lý theo policy khác.

- `parentNode` là **DOM node chứa chữ ký được tạo**, không phải nút `<Signature>` đã tồn tại trước.
- Khi **không** chỉ định `nextSiblingNode`, `<Signature>` được thêm làm **child cuối** của parent.
- Khi chỉ định `nextSiblingNode`, chữ ký được chèn **ngay trước nút sibling đó** dưới cùng parent.
- Có thể dùng `setParent(Node)`, `getParent()`, `setNextSibling(Node)`, `getNextSibling()` theo API để điều chỉnh cấu hình trước khi ký.
- `privateKey` thuộc một `KeyPair`/keystore/KMS được bảo vệ ở phía signer. **Không** đưa private key vào XML.
- `DOMSignContext` **không tự lựa chọn đoạn tài liệu cần bảo vệ**. Phạm vi dữ liệu được ký thực tế nằm trong `SignedInfo/Reference URI` và các Transforms.

Một cách ký trên root:

~~~java
Element root = document.getDocumentElement();
DOMSignContext signContext = new DOMSignContext(privateKey, root);
signature.sign(signContext);
~~~

Đây là đoạn trong method, cần `document`, `privateKey`, `signature` đã được chuẩn bị. Kết quả là chữ ký DOM được thêm **bên trong root**, nhưng **chỉ những phần mà Reference trỏ đến mới được kiểm tra digest**. Nếu Reference chỉ ký một `<Payload>` nhỏ, các phần tử khác ngoài Payload có thể không được bảo vệ dù `<Signature>` được chèn dưới root.

### Namespace prefix cho chữ ký

`DOMCryptoContext.setDefaultNamespacePrefix("ds")` cho phép provider dùng prefix `ds` khi sinh các phần tử XMLDSig:

~~~java
DOMSignContext ctx = new DOMSignContext(privateKey, root);
ctx.setDefaultNamespacePrefix("ds");
signature.sign(ctx);
~~~

**Prefix `ds` chỉ là cách biểu diễn**, namespace URI chuẩn của XML Signature là **`http://www.w3.org/2000/09/xmldsig#`**. Phía validate phải tìm phần tử bằng URI + local name, ví dụ `getElementsByTagNameNS(XMLSignature.XMLNS, "Signature")`, **không** chỉ dùng `getElementsByTagName("ds:Signature")` vì prefix có thể thay đổi.

Bên cạnh prefix của `<Signature>`, **prefix/namespace bindings của phần tử dữ liệu được ký phải ổn định trước khi ký**. Trong demo, root `<inv:Invoice>` đã được khai báo:

~~~java
Element root = doc.createElementNS("urn:demo:invoice", "inv:Invoice");
root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
        "xmlns:inv", "urn:demo:invoice");
root.setAttribute("Id", "inv-0001");
~~~

Đoạn này là **minh họa trong method**. Khai báo `xmlns:inv` trước khi ký giúp tránh trường hợp serializer tự bổ sung namespace declaration **sau khi digest đã được tạo**, làm representation cần canonicalization thay đổi. Với canonicalization inclusive, một thay đổi namespace context có thể làm digest khác dù text visible không đổi.

**Lưu ý thực tế đã kiểm thử:** phiên bản ban đầu của ví dụ khi chưa khai báo namespace binding rõ ràng đã cho `SignatureValue=true` nhưng `Reference=false` sau serialize→parse. Sau khi khai báo namespace ổn định **trước `signature.sign`**, cả hai đều `true`. Đây là một bài học quan trọng về canonicalization, không phải lý do để tắt kiểm tra digest.

### Không tái sử dụng `DOMSignContext` bừa bãi

Javadoc Java 25 cảnh báo mỗi instance có thể giữ trạng thái gắn với một cấu trúc chữ ký cụ thể. Nếu dùng **một `DOMSignContext` cho hai `XMLSignature` khác nhau**, hành vi có thể khó dự đoán. Nên **tạo context riêng cho mỗi operation** với parent, khóa và ID mapping rõ ràng; không chia sẻ context mutable giữa các threads.

## 4. `DOMValidateContext` — nút chữ ký, khóa xác minh và trust boundary

### Constructors

~~~java
DOMValidateContext validate1 =
        new DOMValidateContext(trustedPublicKey, signatureNode);

DOMValidateContext validate2 =
        new DOMValidateContext(keySelector, signatureNode);
~~~

**Đây là đoạn minh họa**, cần `trustedPublicKey`/`signatureNode`/`keySelector` hợp lệ. Hai overload mang ý nghĩa:

- `Key validatingKey`: khóa đã biết để kiểm chứng chữ ký, ví dụ public key lấy từ **truststore/pinned key** hoặc được chứng thực theo chính sách doanh nghiệp.
- `KeySelector`: callback chọn khóa dựa trên `KeyInfo`/metadata và policy. Nếu XML mang `KeyInfo`, **không có nghĩa public key trong đó tự động đáng tin**.
- `signatureNode` phải là **nút `<Signature>` cần xác minh** trong DOM; **không** truyền root invoice hay `Document` thay cho signature node.
- `setNode(Node)`/`getNode()` cho phép quản lý nút validation. Tránh thay node giữa unmarshal/validate hoặc reuse context qua chữ ký khác.

Thực tế:

~~~java
NodeList signatures =
        document.getElementsByTagNameNS(XMLSignature.XMLNS, "Signature");
if (signatures.getLength() != 1) {
    throw new SecurityException("Expected exactly one Signature");
}
DOMValidateContext ctx =
        new DOMValidateContext(trustedPublicKey, signatures.item(0));

XMLSignatureFactory factory = XMLSignatureFactory.getInstance("DOM");
XMLSignature signature = factory.unmarshalXMLSignature(ctx);
boolean valid = signature.validate(ctx);
~~~

Đây là **mã minh họa trong method** cần imports từ DOM/XMLDSig và variable đã tồn tại. Đối với một ứng dụng chỉ chấp nhận một chữ ký, hãy **từ chối 0 hoặc nhiều hơn 1 `Signature`**; không âm thầm chọn `item(0)` khi attacker có thể đưa thêm chữ ký hoặc cây phụ. Ứng dụng khác có thể chấp nhận nhiều signatures, nhưng phải có policy rõ “ai ký cái gì” cho **từng** signature.

### Không coi boolean `validate` là toàn bộ business authorization

Giả sử chữ ký hợp lệ trên `<Payload Id="p1">` nhưng ứng dụng thực hiện nghiệp vụ bằng một `<Payload Id="p2">` chưa ký. Core validation của signature trên `p1` có thể **true** mà business logic đọc `p2` là sai. Đây là cơ chế phổ biến của **signature wrapping / signed-element confusion**.

Cần kiểm tra:
1. Có đúng signature đang được hệ thống tin cậy chấp nhận?
2. `Reference URI` có phải đúng định danh payload cần xử lý?
3. Định danh ID có **duy nhất** trong phạm vi document theo schema/policy?
4. Payload được ứng dụng **sử dụng** có phải chính DOM element được reference và digest bảo vệ?
5. Khóa/định danh người ký có nằm trong trust policy đúng tenant/role/issuer/audience?
6. Namespace, schema, vị trí payload, amount/currency, XML structure có hợp business contract?
7. Nếu có nhiều References hoặc Manifest, policy có quy định rõ tất cả dữ liệu cần validate không?

**Chống XSW không chỉ bằng `setIdAttributeNS`**; ID registration là một bước của reference resolution. Bạn còn phải ràng buộc đúng node được ký với node dữ liệu mà code tiêu thụ.

## 5. `DOMCryptoContext` và `setIdAttributeNS`: một chi tiết dễ khiến ví dụ sai

Trong DOM, một attribute tên `Id` **không tự động trở thành XML ID** chỉ vì tên là “Id”. Nếu không có DTD/schema hoặc bước đánh dấu ID phù hợp, `getElementById("inv-0001")` có thể trả null. Một same-document `Reference URI="#inv-0001"` có thể thất bại khi resolver không tìm được phần tử đích.

Cả `DOMSignContext` và `DOMValidateContext` kế thừa:

~~~java
void setIdAttributeNS(
        Element element, String namespaceURI, String localName);
~~~

Ví dụ trên **phần tử hóa đơn đã được chọn và kiểm tra**:

~~~java
DOMSignContext signCtx = new DOMSignContext(privateKey, invoice);
signCtx.setIdAttributeNS(invoice, null, "Id");
signature.sign(signCtx);

// Phía nhận, sau khi parse và xác định đúng Invoice:
DOMValidateContext valCtx =
        new DOMValidateContext(trustedPublicKey, signatureElement);
valCtx.setIdAttributeNS(invoice, null, "Id");
XMLSignature verified =
        XMLSignatureFactory.getInstance("DOM").unmarshalXMLSignature(valCtx);
boolean ok = verified.validate(valCtx);
~~~

Đây là **đoạn minh họa trong method**, không phải file runnable độc lập; nó giả định có các đối tượng và import hợp lệ, tránh việc đăng ký một ID lấy tùy ý từ XML chưa kiểm tra.

**Các bẫy phải tránh:**

- `namespaceURI=null` chỉ đúng nếu attribute `Id` **không thuộc namespace**. Với `xml:id` hoặc attribute trong namespace riêng, phải dùng namespace URI và localName phù hợp.
- `setIdAttributeNS` đăng ký ánh xạ ID trong **context**, không thay việc rà soát **ID trùng** hoặc xác minh cấu trúc XML.
- `Reference URI="#inv-0001"` không tương đương `Reference URI=""`: URI rỗng thường đại diện root/document toàn bộ theo XML Signature rules, còn `#inv-0001` trỏ một element được ID-map.
- `setBaseURI` giúp xử lý relative URI trong trường hợp cần, nhưng không biến external URIs thành an toàn. Với bài này chỉ dùng same-document URI; bỏ external resolution.
- Không thay nội dung DOM sau ký rồi kỳ vọng `Reference` vẫn hợp lệ. Nếu cần sửa invoice, phải ký lại với private key được cấp quyền.
- Sau `XMLSignatureFactory.unmarshalXMLSignature(ctx)`, **không sửa DOM dưới chân đối tượng XMLSignature đã unmarshal rồi dùng lại nó**: Javadoc `DOMValidateContext` nói behavior undefined khi underlying tree bị caller mutate sau khi đã tạo `XMLSignature`. Muốn kiểm tra bản sửa, **parse lại / tạo context + XMLSignature mới**.

## 6. `SignedInfo`, `Reference` và canonicalization không thuộc trách nhiệm riêng của context

Một tài liệu XMLDSig enveloped có thể có cấu trúc khái quát:

~~~xml
<inv:Invoice xmlns:inv="urn:demo:invoice" Id="inv-0001">
  <inv:Amount>125.50</inv:Amount>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignedInfo>
      <ds:CanonicalizationMethod Algorithm="..."/>
      <ds:SignatureMethod Algorithm="..."/>
      <ds:Reference URI="#inv-0001">
        <ds:Transforms>
          <ds:Transform Algorithm="...enveloped-signature"/>
        </ds:Transforms>
        <ds:DigestMethod Algorithm="...sha256"/>
        <ds:DigestValue>...</ds:DigestValue>
      </ds:Reference>
    </ds:SignedInfo>
    <ds:SignatureValue>...</ds:SignatureValue>
    <ds:KeyInfo>...</ds:KeyInfo>
  </ds:Signature>
</inv:Invoice>
~~~

Đây là **sơ đồ XML lược giản**, các dấu `...` là chú thích cho cấu trúc, **không** phải tài liệu XML đã ký hợp lệ. Chương trình chạy phần sau tạo bytes chữ ký thật.

- **`Reference`** trỏ dữ liệu `#inv-0001`, thực hiện transforms và digest SHA-256.
- **`SignedInfo`** chứa Reference, signature algorithm và canonicalization method.
- **`SignatureValue`** là chữ ký điện tử trên canonicalized SignedInfo, ở đây RSA-SHA256.
- **`KeyInfo`** có thể mang KeyValue/certificate metadata để giúp tìm khóa, nhưng thông tin từ XML chưa được chứng thực và **không tự cấp trust**.

### Canonicalization (C14N)

XML tương đương về mặt hiển thị có thể khác ở namespace bindings, khoảng trắng, attribute order hoặc encoding khi serialize. Canonicalization chuẩn hóa một representation cho tác vụ băm/ký. **Không** đồng nghĩa bạn có thể thay đổi tùy ý whitespace hoặc di chuyển các nodes sau ký mà chữ ký vẫn đúng: các bytes sau C14N vẫn phải khớp.

Trong ví dụ, `CanonicalizationMethod.INCLUSIVE` được sử dụng để minh họa nguyên tắc namespace declaration phải ổn định trước khi ký. Với giao thức thực tế, chọn **canonicalization algorithm đúng profile** (inclusive/exclusive, comments/no-comments) và xác nhận interoperablity giữa các implementations; không chuyển algorithm sau khi đã ký.

### Tại sao cần `Transform.ENVELOPED`?

Chữ ký được thêm vào **chính phần tử invoice** mà Reference bảo vệ. Nếu digest của invoice bao gồm cả `<Signature>` đang được tạo, việc ký sẽ tạo quan hệ vòng tròn. **Enveloped-signature transform** bỏ phần tử chữ ký cần thiết khỏi dữ liệu Reference trước khi tính digest.

~~~java
Reference reference = factory.newReference(
        "#inv-0001",
        factory.newDigestMethod(DigestMethod.SHA256, null),
        List.of(factory.newTransform(
                Transform.ENVELOPED, (TransformParameterSpec) null)),
        null, null);
~~~

Đây là đoạn Java 17 trong method, `factory` là `XMLSignatureFactory`; cần imports `List`/`TransformParameterSpec`. Với **detached signature** hoặc chữ ký trên một element không chứa Signature, transform này có thể không cần. Đừng thêm một chuỗi transforms tùy ý vì mỗi transform làm thay đổi dữ liệu được digest và làm tăng bề mặt tấn công.

### Thuật toán hiện hành

Ví dụ dùng **RSA với SHA-256** và **digest SHA-256**:

~~~java
SignatureMethod.RSA_SHA256
DigestMethod.SHA256
CanonicalizationMethod.INCLUSIVE
Transform.ENVELOPED
~~~

Tất cả đều là các constant có trong Java 17+. Không dùng `SHA1` cho hệ thống mới: JDK 17+ đã bật secure validation mặc định và hạn chế các thuật toán ký/digest yếu. Chọn key size/algorithm theo security policy, profile ngành, HSM/KMS và tương thích đối tác; ví dụ sinh một RSA key pair **3072 bit** tạm để kiểm thử, **không** lưu private key vào file XML.

## 7. Chương trình Java 17+ hoàn chỉnh: ký, serialize, parse lại, validate và chống sai lệch

Ví dụ **`DomXmlSignatureDemo.java`** dưới đây độc lập, chỉ cần JDK 17+ và không dùng database/network/library ngoài. Nó mô phỏng một invoice thuộc namespace `urn:demo:invoice`, tạo RSA key pair, ký invoice, serialize sang XML bytes rồi parse **với DOM parser an toàn** trước khi validate.

Để phân biệt rõ các bước, chương trình:
1. Tạo DOM `Invoice Id="inv-0001"` với namespace declaration **có trước chữ ký**.
2. Tạo `XMLSignatureFactory.getInstance("DOM")`, `Reference URI="#inv-0001"`, enveloped transform, SHA-256 digest, RSA-SHA256 SignedInfo.
3. Chèn chữ ký bằng `DOMSignContext(keys.getPrivate(), root)`; đăng ký `Id` trên sign context.
4. Serialize sang bytes bằng JAXP Transformer có external access restrictions.
5. Parse lại XML để mô phỏng bên nhận, tìm **đúng một** `Signature` và validate bằng **public key được truyền vào bởi caller** (không lấy khóa từ KeyInfo).
6. `DOMValidateContext.setIdAttributeNS(...)` tạo mapping cho same-document reference và bật `secureValidation=true` rõ ràng.
7. Kiểm tra **core / SignatureValue / Reference** riêng.
8. Sửa `Amount` rồi parse/xác minh lại với **context mới**; kiểm tra `SignatureValue` vẫn hợp lệ nhưng `Reference` thất bại.
9. Thử một public key khác: core validation thất bại.
10. Thử một element khác trùng `Id`: demo từ chối trước validation.
11. Thử input có `DOCTYPE`/external entity: secure DOM parser từ chối.

**Lưu ý:** đoạn kiểm tra ID trùng của demo chỉ đếm đúng attribute không namespace tên `Id` mang giá trị `inv-0001`; **không phải bộ lọc XSW hoàn chỉnh cho XML tùy ý**. Production cần xác định tất cả các dạng ID/schema/namespace được cho phép, cấu trúc/business node và trust policy chặt hơn. Keys được tạo ngay trong `main` chỉ để test, không đại diện quy trình PKI thực.

Tạo file đầy đủ:

~~~java
import java.io.*;
import java.security.*;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.crypto.dsig.*;
import javax.xml.crypto.dsig.dom.*;
import javax.xml.crypto.dsig.keyinfo.*;
import javax.xml.crypto.dsig.spec.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import org.w3c.dom.*;
import org.xml.sax.*;
import org.xml.sax.helpers.*;

public final class DomXmlSignatureDemo {
    private static final String NS = "urn:demo:invoice";
    private static final String ID = "inv-0001";

    static DocumentBuilder secureBuilder() throws Exception {
        DocumentBuilderFactory f = DocumentBuilderFactory.newDefaultNSInstance();
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        DocumentBuilder builder = f.newDocumentBuilder();
        builder.setErrorHandler(new DefaultHandler() {
            @Override public void fatalError(SAXParseException e) throws SAXException {
                throw e;
            }
        });
        return builder;
    }

    static Document newInvoice() throws Exception {
        Document doc = secureBuilder().newDocument();
        Element root = doc.createElementNS(NS, "inv:Invoice");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:inv", NS);
        root.setAttribute("Id", ID);
        doc.appendChild(root);
        Element amount = doc.createElementNS(NS, "inv:Amount");
        amount.setTextContent("125.50");
        root.appendChild(amount);
        return doc;
    }

    static void sign(Document doc, KeyPair keys) throws Exception {
        XMLSignatureFactory fac = XMLSignatureFactory.getInstance("DOM");
        Reference reference = fac.newReference("#" + ID,
                fac.newDigestMethod(DigestMethod.SHA256, null),
                List.of(fac.newTransform(Transform.ENVELOPED, (TransformParameterSpec)null)),
                null, null);
        SignedInfo signedInfo = fac.newSignedInfo(
                fac.newCanonicalizationMethod(CanonicalizationMethod.INCLUSIVE,
                        (C14NMethodParameterSpec)null),
                fac.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(reference));
        KeyInfoFactory kf = fac.getKeyInfoFactory();
        KeyInfo info = kf.newKeyInfo(List.of(kf.newKeyValue(keys.getPublic())));
        XMLSignature signature = fac.newXMLSignature(signedInfo, info);
        Element root = doc.getDocumentElement();
        DOMSignContext context = new DOMSignContext(keys.getPrivate(), root);
        context.setIdAttributeNS(root, null, "Id");
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

    record Check(boolean core, boolean signatureValue, boolean reference) {}

    static Check validate(Document doc, PublicKey trustedKey) throws Exception {
        Element root = doc.getDocumentElement();
        if (!NS.equals(root.getNamespaceURI())
                || !"Invoice".equals(root.getLocalName())
                || !ID.equals(root.getAttribute("Id"))) {
            throw new SecurityException("Unexpected signed payload");
        }
        int n = 0;
        NodeList all = doc.getElementsByTagName("*");
        for(int i=0;i<all.getLength();i++){
            if(ID.equals(((Element)all.item(i)).getAttribute("Id")))n++;
        }
        if(n!=1)throw new SecurityException("Duplicate Id");
        NodeList signatures = doc.getElementsByTagNameNS(XMLSignature.XMLNS,"Signature");
        if(signatures.getLength()!=1)throw new SecurityException("Expected one Signature");
        DOMValidateContext context = new DOMValidateContext(trustedKey,signatures.item(0));
        context.setIdAttributeNS(root,null,"Id");
        context.setProperty("org.jcp.xml.dsig.secureValidation",Boolean.TRUE);
        XMLSignatureFactory fac = XMLSignatureFactory.getInstance("DOM");
        XMLSignature signature = fac.unmarshalXMLSignature(context);
        if(signature.getSignedInfo().getReferences().size()!=1){
            throw new SecurityException("Unexpected references");
        }
        Reference reference=(Reference) signature.getSignedInfo().getReferences().get(0);
        if(!("#"+ID).equals(reference.getURI())) {
            throw new SecurityException("Unexpected URI");
        }
        boolean core=signature.validate(context);
        return new Check(core,signature.getSignatureValue().validate(context),
                reference.validate(context));
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen=KeyPairGenerator.getInstance("RSA");
        gen.initialize(3072);
        KeyPair pair=gen.generateKeyPair();
        Document original=newInvoice();
        sign(original,pair);
        byte[] data=serialize(original);
        Document received=parse(data);
        Check valid=validate(received,pair.getPublic());
        System.out.println("Signature elements: "+
                received.getElementsByTagNameNS(XMLSignature.XMLNS,"Signature").getLength());
        System.out.println("Valid core: "+valid.core());
        System.out.println("Valid SignatureValue: "+valid.signatureValue());
        System.out.println("Valid Reference: "+valid.reference());
        Document changed=parse(data);
        changed.getElementsByTagNameNS(NS,"Amount").item(0).setTextContent("999.99");
        Check tampered=validate(changed,pair.getPublic());
        System.out.println("Tampered core: "+tampered.core());
        System.out.println("Tampered SignatureValue: "+tampered.signatureValue());
        System.out.println("Tampered Reference: "+tampered.reference());
        Check wrongKey=validate(parse(data),gen.generateKeyPair().getPublic());
        System.out.println("Wrong key core: "+wrongKey.core());
        Document duplicate=parse(data);
        Element extra=duplicate.createElementNS(NS,"inv:Other");
        extra.setAttribute("Id",ID);
        duplicate.getDocumentElement().appendChild(extra);
        boolean duplicateRejected=false;
        try {validate(duplicate,pair.getPublic());}
        catch(SecurityException e){duplicateRejected=true;}
        System.out.println("Duplicate Id rejected: "+duplicateRejected);
        String malicious="<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "
                +"\"file:///blocked.txt\">]><Invoice>&xxe;</Invoice>";
        boolean dtdRejected=false;
        try {parse(malicious.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
        catch(SAXException e){dtdRejected=true;}
        System.out.println("DOCTYPE rejected: "+dtdRejected);
    }
}
~~~

Biên dịch và chạy với JDK **17 hoặc mới hơn**, ở thư mục có file `DomXmlSignatureDemo.java`:

~~~bash
javac --release 17 DomXmlSignatureDemo.java
java DomXmlSignatureDemo
~~~

**Stdout chính xác** đã kiểm chứng trên **OpenJDK 24.0.2** khi compile bằng `javac --release 17`:

~~~text
Signature elements: 1
Valid core: true
Valid SignatureValue: true
Valid Reference: true
Tampered core: false
Tampered SignatureValue: true
Tampered Reference: false
Wrong key core: false
Duplicate Id rejected: true
DOCTYPE rejected: true
~~~

### Đọc output theo đúng semantics

1. `Signature elements: 1`: ứng dụng tìm **đúng một** `Signature` trong namespace XML Signature. **Không** tìm theo prefix literal `ds`.
2. `Valid core: true`: chữ ký hợp lệ theo core rules; được kiểm tra trên DOM **đã serialize rồi parse lại**, không chỉ trên DOM trong bộ nhớ ngay sau `sign()`.
3. `Valid SignatureValue: true`: RSA-SHA256 verification trên `SignedInfo` hợp lệ với public key đúng.
4. `Valid Reference: true`: digest SHA-256 trên dữ liệu được tham chiếu `#inv-0001`, sau enveloped transform/canonicalization, đúng.
5. `Tampered core: false`: sửa `Amount` làm nội dung invoice không còn đúng bản đã được ký.
6. `Tampered SignatureValue: true` nhưng `Tampered Reference: false`: `SignedInfo` và bản thân `SignatureValue` không bị đổi; **chính dữ liệu của Reference đã bị sửa**, nên digest fail. Nếu bạn chỉ gọi `getSignatureValue().validate(...)`, có thể bỏ sót việc dữ liệu XML bị chỉnh sửa.
7. `Wrong key core: false`: public key khác không thể xác minh RSA signature hợp lệ của signer trong ví dụ.
8. `Duplicate Id rejected: true`: application policy từ chối ngay khi phát hiện phần tử khác có `Id="inv-0001"`. Đây là điều kiện chống ambiguity, không phải toàn bộ các kiểm tra XSW production.
9. `DOCTYPE rejected: true`: DocumentBuilder được cấu hình từ chối DTD trước khi external entity có thể được xử lý theo đường parser demo.

**Cần chú ý một việc:** demo nhúng `KeyInfo` với `KeyValue` vào XML để cho thấy XMLDSig có thể chứa metadata public key, **nhưng `validate` dùng `trustedKey` được caller truyền vào**, hoàn toàn không chọn khóa từ `KeyInfo`. Nhờ vậy, thay public key trong XML không tự khiến signer mới được tin tưởng. Trong hệ thống thật, pinned key/truststore phải được quản lý bên ngoài XML, và key rotation, revocation, role policy phải có quy trình.

### Tại sao ví dụ sinh key pair động?

Vì mục đích của file là chứng minh hoạt động của `DOMSignContext`/`DOMValidateContext` mà không cần PKI, HSM hoặc certificate thật. Với production:
- Private key lấy từ protected keystore, HSM hoặc KMS theo quy định; không nhúng trong code, log hay XML.
- Public key/certificate chain phải được xác minh từ trust anchor, gắn đúng signer identity/role, certificate policy và thời điểm ký.
- Application phải phân biệt “chữ ký math đúng” với “khóa/certificate được phép ký hóa đơn này”.
- Không để người gửi tự quyết định một khóa mới bằng `KeyInfo` rồi mặc định chấp nhận.

## 8. Vì sao `DOMValidateContext` phải chỉ tới đúng `Signature`?

Khi XML chứa nhiều chữ ký hoặc nhiều tài liệu con, method:

~~~java
NodeList list = doc.getElementsByTagNameNS(
        XMLSignature.XMLNS, "Signature");
DOMValidateContext ctx = new DOMValidateContext(
        trustedPublicKey, list.item(0));
~~~

là **chưa đủ an toàn** nếu không biết `list.getLength()`, vị trí và dữ liệu được ký. Một attacker có thể đưa chữ ký hợp lệ nhưng **không liên quan đến payload mà application dùng**. Ví dụ code demo đã từ chối nếu không có đúng một `Signature`, và ràng buộc Reference URI `#inv-0001`.

Với XML phức tạp hơn, hãy chọn **Signature theo cấu trúc/giao thức**, không chỉ theo thứ tự NodeList toàn document. Có thể xác minh nhiều signatures hợp lệ rồi áp business policy để quyết định ai được ký phần nào; trong trường hợp đó, mỗi chữ ký dùng **một context và XMLSignature mới**.

### `SignatureValue` khác `Reference`

Trong XML Signature core validation có hai phần:

- **Signature validation:** tính toán/chứng thực `SignatureValue` trên canonicalized SignedInfo, bằng public key đã chọn.
- **Reference validation:** dereference từng `Reference URI`, áp transforms, tính digest và so với `DigestValue` đã được ký.

**Core validation phải thỏa cả hai**. Một kết quả `signature.getSignatureValue().validate(ctx) == true` **không chứng minh XML payload không bị sửa**. Ví dụ tampering trên Amount đã cho trường hợp Reference false nhưng SignatureValue true.

Nếu core fail, hãy kiểm tra riêng các components cho **diagnostics**; đừng dùng một component riêng lẻ làm điều kiện chấp nhận. `Reference.validate` có thể **cache kết quả** trong một `XMLSignature` instance; khi tài liệu thay đổi, hãy parse lại/tạo signature và context mới trước khi validate, như Javadoc và ví dụ yêu cầu.

## 9. Quản lý tin cậy khóa: `KeyInfo`, `KeySelector` và `DOMValidateContext`

### `DOMValidateContext(Key, Node)`

Khi caller đã biết chính xác khóa phải dùng, đây là phương án ít mơ hồ:

~~~java
PublicKey trustedKey = trustedKeyStore.getPublicKeyFor(issuerId);
DOMValidateContext ctx = new DOMValidateContext(trustedKey, signatureNode);
~~~

**Đây là pseudocode minh họa tích hợp**, vì `trustedKeyStore.getPublicKeyFor` không phải method JDK chuẩn; trong ứng dụng thật, có keystore/PKIX/certificate service được xác thực và mapping issuer→key được quản lý bên ngoài XML. Việc truyền một `PublicKey` đúng giúp crypto verification nhưng chưa chứng minh certificate chưa bị thu hồi hoặc đã được cấp quyền cho đối tượng nghiệp vụ.

### `DOMValidateContext(KeySelector, Node)`

Khi XML có `KeyInfo` và ứng dụng có policy để chọn khóa:

~~~java
DOMValidateContext ctx =
        new DOMValidateContext(policyKeySelector, signatureNode);
~~~

`KeySelector` nhận ngữ cảnh gồm `KeyInfo`, purpose, algorithm và `XMLCryptoContext`, sau đó trả `KeySelectorResult`. Nó **không tự cung cấp trust policy**: application cần map certificate/KeyName/issuer sang trust anchors, kiểm tra algorithm, key usage, validity, signer authorization và revocation nếu nghiệp vụ yêu cầu.

**Không nên** viết selector mặc định “lấy KeyValue đầu tiên từ XML, trả về và coi là đã xác thực danh tính” nếu XML do bên ngoài cung cấp. Kẻ tấn công có thể tự tạo key pair, ký XML của chính họ, nhúng public key vào `KeyInfo` rồi vượt qua điều kiện toán học `validate == true` mà không hề là người ký được ủy quyền.

### Nếu XML mang X.509 certificate

`KeyInfo` có thể chứa `X509Data`/`X509Certificate`, nhưng:
- Phải kiểm tra certificate chain qua **trust anchors** được quản lý.
- Kiểm tra thời hạn certificate tại thời điểm hợp lệ theo quy trình nghiệp vụ, revocation/CRL/OCSP khi policy đòi.
- Kiểm tra key usage/extended key usage, subject/issuer/role và ràng buộc signer với document.
- XMLDSig JDK không phải một dịch vụ PKI “tự xác minh tất cả điều kiện trust” chỉ vì bạn dùng `DOMValidateContext`.
- Với chữ ký có timestamp/long-term validation, cần profile tiêu chuẩn riêng và retention/evidence strategy.

## 10. Signature wrapping, ID trùng và Reference URI

Một kiểu tấn công tổng quát:

~~~xml
<Envelope>
  <Payload Id="old">Giá trị cũ được ký</Payload>
  <Signature><!-- Reference URI="#old", chữ ký hợp lệ --></Signature>
  <Payload Id="new">Giá trị độc hại mà app lại đọc</Payload>
</Envelope>
~~~

Đây là **sơ đồ không đủ cấu trúc XMLDSig để chạy**, dùng minh họa. Nếu code chỉ xác minh Signature cho `old` nhưng khi thanh toán lại dùng payload `new`, ứng dụng có thể bị **signature wrapping / payload substitution**, dù một Reference hợp lệ về mặt mật mã.

**Phòng vệ theo lớp:**

1. Giới hạn **hình dạng document**/root namespace và số lượng signature đúng profile.
2. Ràng buộc `Reference URI` phải là **same-document, exact ID** mà business protocol cho phép, không nhận reference arbitrary.
3. Xác nhận **ID duy nhất** theo tất cả attribute ID được schema/protocol cho phép; tránh XML có nhiều candidates cho cùng một URI.
4. `DOMValidateContext.setIdAttributeNS` chỉ đăng ký **đúng element đã được application kiểm tra**, không chọn first match vô điều kiện.
5. Sau core validation, application đọc **chính element đã được chứng minh thuộc signed Reference**. Không chuyển sang một element khác chỉ vì cùng localName, XPath rộng hay vị trí “first child”.
6. Đối với nhiều References, định nghĩa expected set, digest methods, transforms và phạm vi tin cậy; từ chối extra/missing references nếu protocol không cho phép.
7. Kiểm tra signer trust/authorization ngoài XML, tránh embedded KeyInfo tự tạo trust.
8. Giới hạn parser complexity, reference count, transform count, URI access và external resources.
9. Nếu XPath/XSLT transforms được phép trong giao thức, cần threat model riêng; tránh nới secureValidation chỉ để “chạy được”.

**Đừng chỉ dựa vào việc Java XMLDSig secure validation có kiểm tra ID uniqueness**; JDK policy có hạn chế theo provider nhưng application vẫn phải kiểm tra business payload structure, đúng node và các loại ID mà parser chấp nhận.

### External URI và `URIDereferencer`

`DOMCryptoContext.setURIDereferencer(URIDereferencer)` cho phép tùy biến cách resolve các `Reference` (URI nội bộ hoặc external). Nhưng với XML không tin cậy, một resolver cho phép `file:`, `http:`, `https:` có thể tạo **XXE-like file disclosure, SSRF hoặc data substitution**.

Trong bài/demo chỉ dùng `URI="#inv-0001"`, được context map qua `setIdAttributeNS`. Không cần network hay file URI. JDK `org.jcp.xml.dsig.secureValidation` mặc định áp các restrictions, trong đó có hạn chế URI external scheme theo security policy. Không nới policy và không tự viết một resolver tải URL tùy ý từ XML.

Nếu nghiệp vụ bắt buộc detached signatures trỏ tài nguyên ngoài, phải có **allowlist và mapping explicit** giữa URI và **trusted local bytes**; hạn chế size/timeout, kiểm tra digest/identity, không tự động mở đường dẫn do sender điều khiển.

## 11. Secure validation và XML parser security là hai tầng khác nhau

### Tầng 1: parse XML trước khi xác minh

`DOMValidateContext` nhận một **DOM node đã tồn tại**. Nếu DOM được tạo từ untrusted XML bằng parser mở DTD/external entities, một tấn công XXE có thể xảy ra **trước khi** bạn tạo `DOMValidateContext`. Vì vậy code demo tạo parser an toàn:

~~~java
DocumentBuilderFactory f = DocumentBuilderFactory.newDefaultNSInstance();
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
f.setXIncludeAware(false);
f.setExpandEntityReferences(false);

DocumentBuilder builder = f.newDocumentBuilder();
Document document = builder.parse(inputStream);
~~~

Đây là snippet trong method với `inputStream` được owner cấp/đóng riêng. Security settings phụ thuộc provider; nếu một essential setting không hỗ trợ, **fail closed** thay vì parse untrusted XML theo cấu hình yếu. Còn cần giới hạn bytes, depth, entity expansion, attributes, thời gian parse và quyền truy cập file/network.

**Không lấy một DOMSource do driver/parser khác tạo sẵn rồi nghĩ cấu hình DocumentBuilder mới ở đây có tác dụng hồi tố.** Mọi processor parse/transform nên được cấu hình ở chính nơi nó hoạt động.

### Tầng 2: validate XML digital signature

JDK 17+ bật **XML Signature secure validation mode** mặc định trong JDK implementation. Trong demo, ta đặt rõ:

~~~java
ctx.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
~~~

Chế độ này giúp hạn chế một số constructs nguy hiểm, chẳng hạn XSLT transforms, số Reference/transforms quá mức, weak algorithms, external URI schemes, small keys và các dạng ID ambiguity theo security policy. Cấu hình policy chi tiết thuộc `jdk.xml.dsig.secureValidationPolicy` ở `java.security`; quy tắc cụ thể có thể thay đổi theo JDK version/vendor.

**Lưu ý system property:** `org.jcp.xml.dsig.secureValidation` cũng có thể được đặt ở JVM level; theo Javadoc, giá trị system property **được ưu tiên hơn** giá trị đặt trên context. Nếu system property bị cấu hình thành `false`, `ctx.setProperty(..., Boolean.TRUE)` không bảo đảm override lại. Đối với production, kiểm soát JVM startup/security properties và kiểm thử policy thực tế; **không** bật/tắt chế độ này dựa vào input người dùng.

**Không tắt secureValidation** bằng `Boolean.FALSE` chỉ để chấp nhận SHA-1 hoặc XML signatures không phù hợp policy, trừ khi có một ngoại lệ tương thích cũ được đánh giá bảo mật chặt và tách biệt. Với bài Java hiện đại, ưu tiên SHA-256 và key lengths phù hợp.

### Không mặc định chữ ký là “an toàn tuyệt đối”

Chữ ký hợp lệ:
- Không mã hóa dữ liệu.
- Không tự ngăn việc replay thông điệp cũ.
- Không chứng minh người ký có quyền của tài khoản hiện tại.
- Không tự validate XML schema/business constraints.
- Không tự đảm bảo dữ liệu **ngoài** References được bảo vệ.
- Không bảo đảm một embedded certificate được trusted.
- Không thay thế authorization, anti-replay nonce/timestamp, audience/tenant binding và key rotation.

**Ứng dụng phải xử lý những thuộc tính này ngoài `DOMValidateContext`**.

## 12. Ký dữ liệu từ file/HTTP: thứ tự vận hành production

Đối với XML do application **tạo để ký**:

1. Xây DOM với namespace declarations/ID attributes ổn định theo schema, validate domain data.
2. Chọn đúng **khóa riêng** qua key management subsystem; không đưa khóa vào logs.
3. Chọn `XMLSignatureFactory("DOM")`, SignedInfo/References và algorithms đúng profile.
4. Tạo một `DOMSignContext(privateKey, parent)`, đăng ký ID cho signed target, chọn signature placement.
5. Gọi `signature.sign(context)`.
6. Serialize XML qua Transformer/output với security settings và encoding chính xác.
7. Không sửa signed nodes hoặc namespace context sau khi ký.
8. Gửi XML qua kênh transport có authentication/integrity theo yêu cầu, lưu audit/correlation IDs mà không lộ private key.

Đối với XML nhận để **xác minh**:

1. Xác thực nguồn truyền thông/tenant sơ bộ và áp byte limits.
2. Parse XML với namespace-aware DOM parser đã khóa DTD/XXE và có resource limits.
3. Rà soát root, namespaces, allowed schema, số signatures và ID uniqueness.
4. Từ signer/issuer policy, lấy **public key được tin cậy độc lập** hoặc `KeySelector` có trust validation.
5. Chọn đúng `<Signature>`, tạo **`DOMValidateContext(trustedKey, signatureNode)`** mới.
6. Đăng ký đúng ID element và đặt secureValidation theo policy.
7. Unmarshal bằng `XMLSignatureFactory.getInstance("DOM")`.
8. Kiểm tra exact `Reference URI`, các transforms/algorithms được phép, signed target và binding với dữ liệu ứng dụng.
9. Gọi `signature.validate(ctx)`; nếu false, phân tích `SignatureValue` và từng `Reference`, **không tiếp tục nghiệp vụ**.
10. Nếu core valid, tiếp tục trust/authorization/replay/domain policy, chỉ sử dụng dữ liệu **đã được chứng minh là signed**.
11. Dọn streams và DOM references theo scope; không reuse mutable contexts across requests.

**Phân biệt việc chọn DOM:** một tài liệu XML khổng lồ có thể khiến DOM chiếm nhiều RAM. API XML Signature DOM yêu cầu cây DOM để canonicalize/xử lý các references; nếu kích thước untrusted input lớn, đặt giới hạn file/payload trước parse. Không ngầm coi StAX streaming là được áp dụng ở bước DOMValidateContext khi cơ chế factory đang là DOM.

## 13. Trục trặc thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `unmarshalXMLSignature` lỗi | Node không phải XML Signature hợp lệ, wrong namespace, malformed constructs | Tìm signature bằng XMLSignature.XMLNS và profile structure |
| `DOMValidateContext` nhận root invoice | Truyền sai node (phải là Signature) | Chọn đúng `<Signature>` node |
| `getElementById("inv-0001") == null` | Attribute `Id` chưa được đăng ký ID | `setIdAttributeNS` trên đúng element ở cả ký và validate |
| `Reference URI="#..."` resolve thất bại | ID sai/trùng/không map, URI không hợp policy | Kiểm tra exact URI, schema, ID mapping |
| `SignatureValue=true`, `Reference=false` | XML data/namespace/digest thay đổi sau khi ký | Kiểm tra canonicalization/namespace declarations, tampering |
| `SignatureValue=false`, `Reference=true` | Public key sai hoặc SignedInfo/SignatureValue bị sửa | Kiểm tra trusted key, signature method và KeyInfo policy |
| Core valid nhưng business data không đúng | App đọc **khác signed element** | Chống signature wrapping, bind signed node to domain |
| Core valid với khóa attacker tự đưa | KeyInfo bị tự tin cậy | Truststore/pinned key/PKIX validation ngoài XML |
| Sau serialize→parse thì ref fail | Serializer thêm namespace binding hoặc đổi signed content | Khai báo namespaces/IDs ổn định trước sign, test roundtrip |
| Parser gọi ra external URL/file | DTD/XXE chưa bị khóa ở parser | Harden DocumentBuilderFactory trước parse |
| `secureValidation` bị tắt dù setProperty TRUE | JVM system property override | Kiểm soát JVM properties và runtime policy |
| SHA-1 signature bị từ chối | Weak algorithms bị hạn chế ở JDK hiện hành | Di chuyển sang algorithm/profile hiện hành |
| XSLT transform bị từ chối | Secure validation policy hạn chế XSLT | Không tắt policy mù quáng; xem lại profile |
| XML có nhiều signatures | Chọn item(0) sai hoặc attacker chèn thêm | Enforce expected number/placement/refs |
| `XMLSignature` đổi hành vi sau mutate DOM | Javadoc cảnh báo undefined khi tree đổi sau unmarshal | Parse lại, tạo context + unmarshalled signature mới |
| `Reference.validate` sau lần đầu không tính lại | Reference có cached validation result | Không reuse object sau DOM mutation |
| Performance/OOM | Input rất lớn, DOM/transform complexity | Giới hạn size, depth, refs/transforms, deadline |

### Diagnostics có kiểm soát

Khi `signature.validate(ctx)` trả false, có thể dùng:

~~~java
boolean sigValueOk = signature.getSignatureValue().validate(ctx);
for (Reference ref : signature.getSignedInfo().getReferences()) {
    boolean digestOk = ref.validate(ctx);
    System.out.println("Reference " + ref.getURI() + ": " + digestOk);
}
~~~

Đây là **mã minh họa trong method**, chỉ dùng cho **diagnostics** với context và signature mới, các references đã được policy allowlist và logger đã sanitize. Trong production, không ghi raw XML/payload/certificate/private-key/URI chứa secret vào log. Với URI do attacker cung cấp, không được chạy dereference ngoài policy chỉ để có thêm diagnostics.

**Hai loại “false” có nguyên nhân khác nhau**: signature value false thường liên quan SignedInfo/key/signature, reference false liên quan dữ liệu đã ký/digest/transforms/resolution. Nếu API ném `XMLSignatureException` thay vì trả false (ví dụ unsupported transform, resolver error), xử lý như **validation failure**, không coi là một chữ ký thiếu trường có thể bỏ qua.

## 14. Kiểm thử cho `DOMSignContext` và `DOMValidateContext`

### Unit tests / deterministic tests

| Tình huống | Kỳ vọng |
| --- | --- |
| Sign invoice chuẩn, SHA-256/RSA-3072 | Tạo đúng một Signature |
| Parse lại XML sau ký | Core, SignatureValue, Reference đều true |
| Đổi `Amount` sau ký | Core=false, Reference=false |
| Đổi text `SignedInfo` hoặc SignatureValue | Core=false hoặc exception theo cấu trúc |
| Dùng public key khác | Core=false |
| Missing Signature | Fail closed |
| Có nhiều Signature | Fail closed nếu profile chỉ cho 1 |
| Missing ID mapping | Reference unresolved, validation không thành công |
| Duplicate `Id` | App từ chối theo ID uniqueness policy |
| Reference trỏ một ID khác | App từ chối dù có một chữ ký hợp lệ ở nơi khác |
| XML DTD/external entity | Parser từ chối, không đọc file/SSRF |
| External Reference URI | Secure validation/policy từ chối |
| SHA-1 / MD5 / small key | Bị policy secure validation chặn theo JDK |
| Namespace prefix đổi nhưng URI đúng | Xử lý theo namespace-aware XML (không dựa prefix literal) |
| Namespace binding thay đổi sau ký | Có thể làm digest fail; test các serializers |
| Whitespace formatting sau ký | Chỉ chấp nhận nếu canonical bytes vẫn khớp |
| Reuse DOMValidateContext cho signature khác | **Không thực hiện**, tạo instance riêng |
| XML có unsigned payload khác | Application không lấy nhầm dữ liệu ngoài signed Reference |
| KeyInfo chứa attacker public key | Không cấp trust nếu không được truststore/PKIX xác minh |
| Certificate expired/revoked/wrong role | Reject theo PKI/business policy |
| Replay signed invoice cũ | Reject theo nonce/sequence/time policy nếu ứng dụng yêu cầu |
| Huge XML / too many References | Resource quotas và secureValidation áp dụng |
| Invalid/malformed XML | Parser fail, không chạy vào nghiệp vụ |

### Tích hợp cross-provider và interoperability

JDK `XMLSignatureFactory.getInstance("DOM")` dùng JCA provider framework; cùng ký hiệu algorithm URI nhưng khi trao đổi với đối tác có thể xuất hiện differences ở canonicalization, namespace propagation, DTD handling hoặc supported transforms. Cần:
- Kiểm thử JDK/crypto provider phiên bản dùng production, đối tác bên ngoài và canonicalization algorithm theo profile.
- Dùng test fixtures đã ký bởi **khóa kiểm thử** độc lập, không gửi/commit private key thật.
- Kiểm tra XML output sau serialize→parse→validate, không chỉ gọi validate trên một DOM vừa sign.
- Test chứng thư nhiều CA, key rotation, trust revocation và xác nhận role/issuer.
- Kiểm tra XML signature có algorithm được hỗ trợ nhưng bị policy không cho phép (algorithm agility).
- Tránh chia sẻ `XMLSignatureFactory` instance giữa nhiều threads nếu provider không bảo đảm thread safety của non-static methods; tạo scope riêng hoặc synchronization theo docs.
- Đặt validation deadline/size quotas, tránh một XML nhiều reference hoặc transform gây tốn tài nguyên.

**Test trong chương trình phần 7 chỉ xác minh bằng key pair tạm cùng tiến trình**; không chứng minh một doanh nghiệp đã thiết lập trust anchors, PKIX path validation hoặc anti-replay policy.

## 15. Những nhầm lẫn phổ biến

| Nhận định sai | Thực tế |
| --- | --- |
| “DOMSignContext là chữ ký số.” | Nó là **ngữ cảnh cung cấp khóa và vị trí DOM** cho XMLSignature |
| “DOMValidateContext tự xác thực người ký.” | Nó cung cấp key/selector và signature node; **trust do ứng dụng quản lý** |
| “`DOMSignContext(privateKey, root)` là ký mọi thứ trong file.” | Phạm vi ký do References/Transforms quyết định |
| “`DOMValidateContext(publicKey, root)` là đúng.” | Tham số node phải là **Signature element** |
| “Public key nhúng trong KeyInfo chắc chắn đáng tin.” | Attacker cũng có thể tự nhúng public key |
| “Reference URI trỏ bằng tên tag.” | URI nội bộ dùng ID mapping, `setIdAttributeNS` rất quan trọng |
| “Attribute `Id` mặc nhiên là ID.” | Phải được DOM/parser/context đăng ký theo schema/ID policy |
| “Cho phép ID trùng nhưng chỉ lấy phần tử đầu.” | Có thể tạo signed-element ambiguity/XSW |
| “Chữ ký core valid tức app đang dùng đúng payload.” | Phải bind signed Reference tới business element |
| “SignatureValue=true nghĩa là nội dung XML không bị sửa.” | Reference digest có thể false |
| “Canonicalization cho phép tùy tiện đổi namespace sau ký.” | Namespace context có thể đổi digest |
| “Serializer thay namespace prefix không ảnh hưởng trong mọi profile.” | Không được bảo đảm; test C14N và XML representation |
| “Enveloped transform là cơ chế chống XXE.” | Nó loại chữ ký khỏi dữ liệu để digest; **không** chống XXE |
| “Secure XMLDSig validation tự bảo vệ XML parser trước đó.” | Parser cần security config độc lập |
| “Tắt secureValidation cho tương thích luôn an toàn.” | Có thể bật lại weak algorithms/external URIs |
| “RSA-SHA256 cung cấp encryption.” | Signature bảo vệ integrity/authentication, không giấu XML |
| “Một DOMValidateContext dùng cho mọi signatures được.” | Javadoc cảnh báo instance state không portable khi reuse |
| “Sau unmarshal có thể mutate tree rồi validate tiếp.” | Undefined behavior, có caching; parse/unmarshal lại |
| “Đúng schema là đã có quyền ký.” | Authorization/issuer/tenant/role là policy ngoài schema |
| “Một chữ ký hợp lệ ngăn replay.” | Cần nonce/timestamp/sequence và validation ngoài chữ ký |
| “DOM signature tự streaming ở tệp rất lớn.” | DOM-based implementation cần DOM tree, cần quotas |

## 16. Câu hỏi tự kiểm tra

1. **`DOMSignContext` là gì?** Ngữ cảnh DOM cho quá trình tạo chữ ký, chứa signing key/KeySelector và vị trí chèn.
2. **`DOMValidateContext` là gì?** Ngữ cảnh DOM cho việc unmarshal/validate chữ ký, chứa verification key/KeySelector và nút Signature.
3. **Hai class kế thừa lớp nào?** `DOMCryptoContext`.
4. **`DOMSignContext(key, parent)` thêm chữ ký ở đâu?** Mặc định làm child cuối của parent.
5. **Muốn chèn trước một sibling?** Dùng overload có `nextSibling` hoặc `setNextSibling`.
6. **Khi validate, Node nên là root hay Signature?** Nút `<Signature>`.
7. **API tạo/đọc XMLSignature theo cơ chế DOM?** `XMLSignatureFactory.getInstance("DOM")`.
8. **Phương thức tạo chữ ký cuối cùng?** `signature.sign(signContext)`.
9. **Phương thức unmarshal chữ ký?** `factory.unmarshalXMLSignature(validateContext)`.
10. **Phương thức core validation?** `signature.validate(validateContext)`.
11. **Kết quả SignatureValue=true, Reference=false là gì?** SignedInfo được xác minh, nhưng dữ liệu tham chiếu/digest không khớp.
12. **Vì sao không tin khóa từ KeyInfo vô điều kiện?** XML từ sender có thể chứa public key của attacker.
13. **`setIdAttributeNS` làm gì?** Đăng ký attribute ID cho đúng DOM element vào context.
14. **URI `#inv-0001` bảo vệ gì?** Dữ liệu đúng element có ID đã đăng ký `inv-0001`, qua transforms.
15. **`Transform.ENVELOPED` dùng khi nào?** Khi chữ ký nằm trong chính nội dung được ký, để không digest nó.
16. **Vì sao namespace phải ổn định trước sign?** C14N/digest có thể thay đổi sau serializer thêm declarations.
17. **SHA-1 có nên dùng cho chữ ký XML mới?** Không; JDK hiện đại chặn/hạn chế yếu tố này trong secure validation.
18. **`DOMValidateContext` có tự chặn XXE từ parser không?** Không, DOM parser phải được cấu hình trước khi parse.
19. **`org.jcp.xml.dsig.secureValidation` là gì?** Property JDK hạn chế các constructs/algorithms nguy hiểm khi XMLDSig validation.
20. **System property có thể override context property?** Có, theo Javadoc; cần kiểm soát runtime config.
21. **Chữ ký XML có ngăn replay không?** Không tự động; cần nonce/sequence/time business policy.
22. **Vì sao không reuse context khi validate chữ ký khác?** State gắn với signature và Javadoc cảnh báo hành vi khó dự đoán.
23. **Khi phát hiện ID trùng, nên làm gì?** Reject document hoặc làm theo schema chặt, không chọn first match.
24. **Core validation true đã đủ authorize thanh toán?** Chưa; cần trust/role, business constraints, signed-element binding.
25. **Sau sửa DOM, có nên gọi validate lại trên cùng object?** Không; parse mới, context và unmarshal mới.
26. **Ví dụ sử dụng private key ở đâu?** Chỉ tại `DOMSignContext` bên ký; bên nhận dùng public key được tin cậy.
27. **Tại sao demo serialize→parse?** Để kiểm thử canonicalization/namespace bindings và dữ liệu thật như bên nhận.
28. **Vì sao không dùng XPath rộng để lấy “Amount đầu tiên” sau validate?** Có thể lấy phần tử không nằm trong signed Reference và bị XSW.
29. **Nếu cần detached external reference, phải bổ sung gì?** Allowlist/controlled dereferencer, size/time/resource limits, trust.
30. **Các API XML Signature còn hiện hành nằm ở đâu?** Module `java.xml.crypto`, package `javax.xml.crypto.dsig` và `javax.xml.crypto.dsig.dom`.

## 17. Tham khảo chính thức và hiện hành

- [Java SE 25 — DOMSignContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html): signing key/KeySelector constructors, parent/nextSibling, context lifecycle.
- [Java SE 25 — DOMValidateContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): validation key/KeySelector, Signature node, secureValidation mặc định, cảnh báo reuse/mutate.
- [Java SE 25 — DOMCryptoContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dom/DOMCryptoContext.html): `setIdAttributeNS`, prefix, properties, base URI và URIDereferencer.
- [Java SE 25 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): DOM mechanism, newSignedInfo/newReference/newXMLSignature, unmarshal.
- [Java SE 25 — XMLSignature](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): `sign`, `validate`, `SignatureValue`.
- [Java SE 25 — Reference](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, transforms, digest validation và cached validation result.
- [Java SE 25 — KeySelector](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml.crypto/javax/xml/crypto/KeySelector.html): chọn khóa theo KeyInfo/policy.
- [Java SE 25 — DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): namespace-aware DOM parsing và XXE hardening.
- [Oracle Java SE 25 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/25/security/java-xml-digital-signature-api-overview-and-tutorial.html): XML signature forms, DOMSignContext/DOMValidateContext, secure validation policy, ví dụ ký và kiểm tra.
- [Oracle Java SE 25 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html): FSP, external DTD/schema/stylesheet access và resource limits.
- [W3C — XML Signature Syntax and Processing 1.1](https://www.w3.org/TR/xmldsig-core1/): chuẩn Reference URI, SignedInfo, Transforms, SignatureValue, KeyInfo.
- [W3C — Canonical XML 1.1](https://www.w3.org/TR/xml-c14n11/): canonicalization và các tình huống namespace/attribute normalization.

**Ghi nhớ:** `DOMSignContext` xác định **khóa ký và vị trí chèn** chữ ký trong DOM; `DOMValidateContext` xác định **khóa tin cậy và nút chữ ký cần kiểm tra**. Cả hai không thay việc chọn `Reference URI` đúng, đăng ký unique ID, canonicalize ổn định, kiểm tra **core = SignatureValue + References**, cấu hình DOM parser chống XXE và ràng buộc **đúng signed element** với dữ liệu nghiệp vụ. Với XML không tin cậy, chữ ký hợp lệ theo toán học chỉ là một lớp trong hệ thống xác thực, toàn vẹn và phân quyền.