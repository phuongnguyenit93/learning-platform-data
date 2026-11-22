# Chữ ký XML: Canonicalization, transform và tác động lên dữ liệu được ký

## Mục tiêu bài học

**XML Digital Signature (XMLDSig)** dùng chữ ký số để bảo vệ nội dung được tham chiếu trong hoặc ngoài một tài liệu XML. Nó không chỉ ký trực tiếp chuỗi XML gốc. XML có thể khác thứ tự thuộc tính, cách dùng dấu nháy hoặc ký pháp phần tử rỗng mà vẫn có cùng biểu diễn ngữ nghĩa ở mức XML. Ngược lại, một thao tác “format cho đẹp” có thể thêm whitespace text nodes và khiến chữ ký mất hiệu lực. **Canonicalization (C14N)** và **transforms** là các bước kỹ thuật quyết định những bytes nào được băm và ký.

Bài tập trung vào ba vấn đề:

1. `Reference URI` chỉ ra **đúng dữ liệu nào** nằm trong phạm vi bảo vệ.
2. `Reference Transforms` (ví dụ `enveloped-signature`, exclusive C14N) xử lý nguồn **theo thứ tự** trước khi tính `DigestValue`.
3. `SignedInfo/CanonicalizationMethod` chuẩn hóa **chính SignedInfo** trước khi tạo và kiểm tra `SignatureValue`, **không đồng nghĩa** canonicalize mọi Reference.

Kết thúc bài, bạn có thể:

- Phân biệt một **Reference digest** với **cryptographic SignatureValue**, kiểm tra cả hai khi verify.
- So sánh inclusive C14N, Canonical XML 1.1 và exclusive C14N, với/không comments.
- Hiểu tại sao đổi attribute order có thể không ảnh hưởng digest, còn signed text/attribute value/whitespace node/order of child elements có thể làm digest sai.
- Giải thích `Transform.ENVELOPED` khi `Signature` nằm trong XML nó ký, và ý nghĩa thứ tự transforms.
- Phân biệt biến đổi **dữ liệu đã ký** với thay đổi ở phần **ngoài** phạm vi của `Reference URI`.
- Biết C14N không tự làm Unicode NFC/NFD normalization, không validate business schema và không bảo vệ unsigned elements.
- Sử dụng Java SE 17+ API `javax.xml.crypto.dsig` trong module `java.xml.crypto` để ký/verify bằng **SHA-256 + RSA-SHA256**.
- Hiểu XMLDSig secure validation trong JDK 17+ và vì sao không dùng SHA-1, không nhận arbitrary external Reference/transform, không vô hiệu hóa security để cho chữ ký cũ qua.
- Phòng lỗi **XML signature wrapping / wrong-node selection** bằng expected Reference URI, unique IDs, trust policy và lựa chọn đúng node sau verify.
- Chạy chương trình Java 17+ độc lập có **25 phép kiểm tra tự động** đã chạy thực tế trên OpenJDK 24.

**Special Note:** Chỉ áp dụng tri thức còn hiệu lực theo Java SE 26, W3C XML Signature 1.1 và JDK 17+; không dùng các cách làm đã legacy hoặc thuật toán chữ ký yếu. Mã chính được biên dịch với `javac --release 17`, không yêu cầu database, mạng hay thư viện ngoài JDK.

## 1. Cấu trúc XML Signature và ý nghĩa từng thành phần

Một cấu trúc khái quát:

```xml
<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:SignedInfo>
    <ds:CanonicalizationMethod Algorithm="..."/>
    <ds:SignatureMethod Algorithm="..."/>
    <ds:Reference URI="#pay-001">
      <ds:Transforms>
        <ds:Transform Algorithm="..."/>
        <ds:Transform Algorithm="..."/>
      </ds:Transforms>
      <ds:DigestMethod Algorithm="..."/>
      <ds:DigestValue>...</ds:DigestValue>
    </ds:Reference>
  </ds:SignedInfo>
  <ds:SignatureValue>...</ds:SignatureValue>
</ds:Signature>
```

Đây là **sơ đồ minh họa**, không phải chữ ký có thể xác minh. Dấu `...` là placeholder trong ví dụ XML, không dùng để tạo một document production.

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `Signature` | Element chứa SignedInfo, SignatureValue, optional KeyInfo | Có thể nằm trong, ngoài hoặc bao lấy dữ liệu được ký |
| `SignedInfo` | Mô tả Reference(s), digest(s), thuật toán ký và canonicalization | Chính bytes canonicalized của SignedInfo được ký mật mã |
| `CanonicalizationMethod` | Thuật toán C14N cho SignedInfo | Không tự động làm C14N cho dữ liệu Reference |
| `SignatureMethod` | Thuật toán chữ ký, ví dụ `RSA_SHA256` | Không nhầm với DigestMethod |
| `Reference URI` | Xác định nguồn phải băm | Không phải cứ có Signature thì toàn bộ XML được bảo vệ |
| `Transforms` | Chuỗi biến đổi nguồn được tham chiếu | Thứ tự transforms quan trọng |
| `DigestMethod` | Hash kết quả biến đổi, ví dụ `SHA256` | Không cần private key để tính digest |
| `DigestValue` | Base64 của digest, là một phần SignedInfo | Được bảo vệ gián tiếp bởi SignatureValue |
| `SignatureValue` | Chữ ký trên SignedInfo sau canonicalization | Có thể hợp lệ dù Reference digest sai |
| `KeyInfo` | Optional dữ liệu giúp tìm khóa/chứng chỉ | **Không tự quyết định khóa đáng tin** |

### Hai pipeline không được nhầm lẫn

```text
Reference URI="#pay-001"
      |
      v
DEREFERENCE data object
      |
      v
Transform 1: enveloped-signature (bỏ Signature tự chứa)
      |
      v
Transform 2: Exclusive C14N (node-set -> canonical octets)
      |
      v
Digest SHA-256 -> DigestValue ---------+
                                        |
                                        v
SignedInfo [algorithms, URI, transforms, DigestValue]
      |
      v
SignedInfo CanonicalizationMethod: Exclusive C14N
      |
      v
SignatureMethod: RSA-SHA256 + private key
      |
      v
SignatureValue
```

Khi kiểm tra XML đã nhận, verifier phải **(a)** xác minh chữ ký của `SignedInfo` bằng khóa công khai **tin cậy**, và **(b)** dereference/recompute digest cho **tất cả References** cần được bảo vệ. `XMLSignature.validate(context)` thực hiện core validation. Ứng dụng vẫn cần bước trust, authorization, business data binding và anti-replay.

## 2. Canonicalization là gì và không là gì?

Canonicalization tạo cách serialize **nhất quán hơn** của một XML node-set để ký hoặc băm. Ví dụ XML source:

```xml
<item b="2" a="1"></item>
```

và:

```xml
<item a='1' b='2'/>
```

có thể trở thành cùng canonical representation, nếu parsing/namespace context và thuật toán giống nhau. C14N sắp xếp thuộc tính, chuẩn hóa cách biểu diễn empty elements, escaped character data và namespace declarations theo quy tắc cụ thể. Do đó **raw-byte khác** không nhất thiết là **Reference digest khác**.

Tuy nhiên:

- **C14N không phải XML Schema validator.** Nó không xác minh Amount có dương, invoice hợp lệ hay user có quyền.
- **C14N không phải Unicode Normalizer.** `é` dạng `U+00E9` và dạng `e` + `U+0301` có thể trông như nhau nhưng không được C14N tự chuyển thành một Unicode normalization form.
- **C14N không trim tùy ý whitespace text nodes.** Chèn `"\n    "` vào signed subtree có thể làm sai digest.
- **C14N không sắp xếp child elements** theo business key. Đổi thứ tự con có thể làm chữ ký sai.
- **C14N không bỏ qua mọi comments**. With-comments/without-comments algorithms và Reference dereferencing quyết định.
- **C14N không xử lý toàn bộ XML theo ý muốn người dùng**; nó xử lý đúng node-set và algorithm được khai báo.
- **C14N không biến XMLDSig thành bảo đảm danh tính**. Key trust và đối tượng ký vẫn do app quyết định.

### Attribute order và attribute value khác nhau

XML attribute order thường không có ý nghĩa với parsed XML data model, nên C14N sắp xếp để tránh khác biệt ký pháp. Ngược lại, `role="payer"` thành `role="payee"` là **đổi dữ liệu** — digest thay đổi và core validation thất bại.

### Empty tag

Ký pháp `<empty/>` và `<empty></empty>` tạo cùng empty element theo XML, nên canonicalization có thể loại khác biệt lexical đó. Nhưng thêm `<child/>` mới vào signed subtree là **thêm node**, không phải biến thể lexical, nên phải làm digest khác.

### Whitespace không phải lúc nào cũng “trang trí”

Whitespace giữa child elements có thể là text nodes trong DOM. Một pretty printer thêm indentation trước `<Amount>` sau khi đã ký sẽ tạo các bytes khác khi canonicalize, ngay cả khi người nhìn thấy dữ liệu kinh doanh vẫn giống. Không tự format lại signed XML mà chưa kiểm tra quy trình ký/xác minh.

## 3. Inclusive C14N, C14N 1.1 và Exclusive C14N

Java SE 26 có các constants trong `CanonicalizationMethod`:

```java
CanonicalizationMethod.INCLUSIVE;
CanonicalizationMethod.INCLUSIVE_WITH_COMMENTS;
CanonicalizationMethod.INCLUSIVE_11;
CanonicalizationMethod.INCLUSIVE_11_WITH_COMMENTS;
CanonicalizationMethod.EXCLUSIVE;
CanonicalizationMethod.EXCLUSIVE_WITH_COMMENTS;
```

Đây là **tên API constants**, không phải một Java program độc lập. Chúng là các algorithm URIs; không thay bằng chuỗi tự đặt như `"exclusive"`.

### Inclusive C14N 1.0

Inclusive Canonical XML có thể mang theo **namespace context từ ancestors** khi canonicalize một subtree. Nếu chuyển một phần tử được ký từ container A sang B có namespace declarations khác, canonical octets có thể thay đổi. Đó là vấn đề interoperability nếu signed XML fragment đi qua nhiều SOAP/Envelope contexts.

### Canonical XML 1.1

W3C XML Signature 1.1 khuyến nghị **Canonical XML 1.1** khi chọn inclusive canonicalization, nhằm xử lý một số vấn đề context (ví dụ liên quan `xml:id`/`xml:base` theo chuẩn). Chọn đúng profile mà signer/verifier đã thỏa thuận, không đổi thuật toán của chữ ký đã tạo.

### Exclusive C14N

Exclusive Canonical XML hạn chế ảnh hưởng của **unused ancestor namespace declarations**. Với:

```xml
<Envelope xmlns:unused="urn:outside">
  <p:Payment xmlns:p="urn:example:payments" Id="pay-001">
    <p:Amount>1000</p:Amount>
  </p:Payment>
</Envelope>
```

nếu `Reference` dùng exclusive C14N cho Payment và prefix `unused` không được dùng, thêm/sửa `xmlns:unused` ở ancestor có thể **không ảnh hưởng digest**. Demo kiểm thử trường hợp này.

**Không hiểu sai:** Exclusive C14N không xóa các namespaces thật sự dùng để đặt tên elements/attributes. Nếu XML format chứa QName trong **attribute values hoặc text**, application có thể cần khai báo danh sách prefixes phải giữ bằng `ExcC14NParameterSpec` (inclusive namespace prefix list) theo profile. Thuật toán không tự hiểu giá trị business đó.

### With-comments và without-comments

Variants without-comments loại comment nodes thuộc phạm vi của chúng; with-comments có thể giữ comments và làm thay đổi digest nếu comment đổi. Tuy nhiên khi `Reference URI` là bare-name fragment `#id`, **bước dereference** cũng quyết định node-set và có quy tắc riêng liên quan comments. Vì vậy không đủ để chỉ nhìn `WITH_COMMENTS` rồi hứa mọi comment trong file đều được ký.

Trong **fixture cụ thể** của bài, `#pay-001` + enveloped + exclusive without-comments cho kết quả thêm comment trong Payment **không phá core validation**. Điều đó không được suy rộng thành “comment luôn vô hại”.

## 4. CanonicalizationMethod trong SignedInfo khác Reference Transform

### 4.1. Chuẩn hóa SignedInfo

```xml
<ds:SignedInfo>
  <ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
  <ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
  ...
</ds:SignedInfo>
```

`SignedInfo/CanonicalizationMethod` tạo **canonicalized SignedInfo bytes** cho thuật toán ký số. Nó **không** tự biến XML của mọi Reference thành exclusive canonical XML.

### 4.2. C14N là một transform riêng của Reference

```xml
<ds:Reference URI="#pay-001">
  <ds:Transforms>
    <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
    <ds:Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
  </ds:Transforms>
  <ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
  <ds:DigestValue>...</ds:DigestValue>
</ds:Reference>
```

Ở đây C14N cuối của `Transforms` canonicalize **dữ liệu đã được dereference và lọc bằng enveloped-signature transform**, rồi `DigestMethod` tính SHA-256.

W3C khuyến nghị khai báo tường minh transform chuyển node-set sang canonical octets khi ký, thay vì dựa vào quy tắc ngầm. Nó giúp các bên hiểu cùng pipeline, đặc biệt khi node-set và octet-stream được xử lý khác nhau.

### 4.3. Thứ tự transforms có ý nghĩa

```text
Reference URI
    -> dereference XML node-set
    -> enveloped-signature transform
    -> exclusive canonicalization transform
    -> SHA-256 digest
```

Đừng tự hoán đổi thứ tự cho “đơn giản”: transform trước có thể đổi kiểu dữ liệu hoặc loại nodes mà transform sau sẽ xử lý. Chỉ dùng transformations do giao thức cho phép, không chấp nhận XPath/XSLT scripts tùy ý từ dữ liệu không tin cậy.

## 5. Transform.ENVELOPED: vì sao cần nó?

Với **enveloped signature**, `ds:Signature` nằm **bên trong XML được ký**:

```xml
<p:Payment xmlns:p="urn:example:payments" Id="pay-001">
  <p:Amount>1000</p:Amount>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    ...
  </ds:Signature>
</p:Payment>
```

Nếu đưa chính `ds:SignatureValue` vào dữ liệu tính Reference digest, sẽ có vòng phụ thuộc: phải có SignatureValue mới biết digest, nhưng lại cần digest để tạo SignatureValue.

**`Transform.ENVELOPED`** loại chữ ký tương ứng ra khỏi tập dữ liệu được băm theo thuật toán chuẩn. Nó không phải phép tìm kiếm/xóa mọi element có tên `Signature` trên document, mà có semantics riêng trong XMLDSig.

Trong Java:

```java
Transform enveloped = factory.newTransform(
        Transform.ENVELOPED, (TransformParameterSpec) null);
Transform exclusive = factory.newTransform(
        CanonicalizationMethod.EXCLUSIVE, (TransformParameterSpec) null);
```

Đây là snippet cần biến `factory` kiểu `XMLSignatureFactory` và imports `TransformParameterSpec`, `CanonicalizationMethod`. Demo đầy đủ ở mục 10 tạo một `Reference` với `List.of(enveloped, exclusive)` đúng thứ tự.

### Chỉ những gì được ký mới được bảo vệ

W3C nhấn mạnh rằng transformations có thể **loại nội dung**. Nếu chữ ký ký Payment nhưng không ký Audit, Audit có thể đổi mà signature vẫn hợp lệ. Đây là giới hạn phạm vi thiết kế, không phải sự thất bại của RSA. Vì vậy phải thiết kế Reference URI/Transforms để bảo vệ **mọi field mà nghiệp vụ sẽ tin dùng**.

## 6. Reference URI: phạm vi chữ ký nằm ở đâu?

Các Reference thường gặp:

| URI | Diễn giải | Lưu ý |
| --- | --- | --- |
| `"#pay-001"` | Same-document ID reference tới element có ID tương ứng | Phải đăng ký và xác minh ID uniqueness |
| `""` | Same-document reference tới toàn XML document theo profile XMLDSig | Thường cần enveloped transform nếu Signature nằm bên trong |
| Một local/detached object URI | Đối tượng bên ngoài Signature, tùy resolver | Không cho URI dereferencing không kiểm soát |
| `http:`, `https:`, `file:` | External resource schemes | JDK XMLDSig secure-validation policy mặc định hạn chế/cấm, không mở tùy tiện |

`Reference URI="#pay-001"` không ký toàn bộ `Envelope`, mà ký data object được chọn theo ID và biến đổi bởi transforms. Nếu sửa một sibling element nằm ngoài Payment, Reference có thể vẫn hợp lệ.

### ID trong DOM là một thuộc tính có type

Một XML attribute có tên `Id` chưa chắc được DOM biết là **ID attribute** nếu không có XML Schema/DTD type information. Java DOM XMLDSig contexts hỗ trợ:

```java
signContext.setIdAttributeNS(payload, null, "Id");
validateContext.setIdAttributeNS(payload, null, "Id");
```

Đây là **snippets tích hợp**, cần contexts và `payload` đúng. Không tự quét mọi attributes tên Id rồi chọn phần tử đầu tiên. Khi nhận XML từ ngoài, cần kiểm tra **unique ID trên document**, loại node/đường dẫn đúng theo profile, không có namespace ambiguity và ký đúng phần tử mà business xử lý.

### Một chữ ký có thể chứa nhiều Reference

`SignedInfo` có thể chứa nhiều References. `XMLSignature.validate` cần core validation toàn bộ chữ ký; không thể chỉ validate Reference đầu tiên rồi tự kết luận mọi dữ liệu đều đúng. Ứng dụng nên kiểm soát danh sách References, số lượng, expected URIs và transforms trước khi dùng bất kỳ field nhạy cảm nào.

## 7. Khi SignatureValue đúng nhưng Reference sai

Đây là tình huống dễ gây lỗi nhất:

```text
SignedInfo + SignatureValue đều nguyên vẹn
        |
        +-- SignatureValue.validate() == true
        |
        +-- Signed Amount bị sửa 1000 -> 1001
                |
                +-- Reference.validate() == false
                |
                +-- XMLSignature.validate() == false
```

Bởi `SignatureValue` ký **SignedInfo**, không trực tiếp ký text Amount. Khi SignedInfo chưa bị sửa, chữ ký mật mã có thể vẫn đúng; nhưng digest của Reference được tính lại từ XML đã bị sửa sẽ khác `DigestValue` đã được ký.

Ngược lại, nếu chỉ sửa Base64 `SignatureValue`, Reference data có thể vẫn đúng, nên `Reference.validate()` true trong khi `SignatureValue.validate()` false và core false.

| Sự cố | SignatureValue check | Reference digest check | Core |
| --- | --- | --- | --- |
| XML gốc không đổi | true | true | true |
| Sửa signed Amount text | **true** có thể xảy ra | **false** | false |
| Sửa signed attribute | **true** có thể xảy ra | **false** | false |
| Sửa SignatureValue mà data giữ nguyên | **false** | **true** | false |
| Sửa SignedInfo/algorithm/URI | Thường false hoặc validation error | Phụ thuộc mục bị sửa | Không được chấp nhận |
| Sửa dữ liệu nằm ngoài Reference | Có thể true | Có thể true | Có thể true |

**Không dùng riêng `sig.getSignatureValue().validate(context)` để chấp nhận business data.** Dùng `sig.validate(context)` và bảo đảm các References được phép chính là các objects mà ứng dụng sẽ tiêu thụ.

## 8. Thay đổi nào giữ chữ ký, thay đổi nào làm hỏng?

Bảng dưới được kiểm thử với **profile cố định**: `Reference URI="#pay-001"`; transforms `ENVELOPED` rồi `EXCLUSIVE without-comments`; `SignedInfo` cũng dùng EXCLUSIVE; digest SHA-256, chữ ký RSA-SHA256, public key được cung cấp từ code.

| Sau khi ký | Kết quả demo | Giải thích |
| --- | --- | --- |
| Bỏ và đặt lại cùng attribute `role="payer"` | **Core vẫn true** | Attribute value/canonical representation không đổi |
| Thêm XML comment trong Payment | **Core vẫn true** | Comment không tham gia digest trong pipeline cụ thể |
| Thêm unused `xmlns:unused` ở ancestor Envelope | **Core vẫn true** | Exclusive C14N hạn chế ancestor namespace không dùng |
| Đổi text của `Audit` sibling ngoài Payment | **Core vẫn true** | Audit không nằm trong Reference |
| Đổi `Amount` từ 1000 thành 1001 | **Core false, Reference false** | Signed content đã đổi |
| Đổi `role="payer"` sang `role="payee"` | **Core false** | Signed attribute value đã đổi |
| Thêm whitespace node `"\n    "` trong Payment | **Core false** | Whitespace text node là một phần nội dung XML được ký |
| Thêm child `p:Extra` vào Payment | **Core false** | Signed subtree có node mới |
| Thêm một Payment sibling **không nằm trong Reference** | **Core vẫn true** | Chữ ký bảo vệ Payment ID pay-001, không phải mọi Payment |
| Đổi Base64 `SignatureValue` | **Core false, crypto false, Reference true** | Chỉ chữ ký mật mã bị sửa |

Các kết quả trên **không** hứa rằng mọi XML Signature với thuật toán khác có cùng tính chất. Đặc biệt comments, ancestor namespace context, XML Schema default attributes và external References cần xét theo profile riêng.

### Canonicalization không cho phép đảo thứ tự child elements

C14N có thể ổn định attribute order, nhưng không tự reorder children theo ID. Nếu hoán đổi `<Amount>` và `<Currency>` trong signed Payment, node sequence đổi và canonical bytes thường khác.

### Pretty print có thể là sửa dữ liệu

Một serializer thêm indentation vào signed subtree có thể tạo character nodes mới. C14N không phân biệt “người xem nghĩ chỉ là khoảng trắng”. Không tự thêm newline/indentation **sau khi ký** nếu chưa đảm bảo quá trình giữ đúng canonical data.

### Unicode trông giống nhau vẫn có thể khác

Nếu đổi string từ ký tự composed sang decomposed dù chữ hiển thị giống, C14N không tự gọi `java.text.Normalizer`. Nếu ứng dụng cần Unicode normalization, xác định policy **trước khi ký** và tránh normalizing signed bytes tùy ý sau đó.

## 9. Java XML Digital Signature API hiện hành và thuật toán

Java hiện đại cung cấp JSR 105 trong module `java.xml.crypto` (vẫn được Oracle Java SE 26 mô tả):

```text
javax.xml.crypto.dsig
javax.xml.crypto.dsig.dom
javax.xml.crypto.dsig.spec
javax.xml.crypto.dsig.keyinfo
javax.xml.crypto.dom
```

| Java type | Vai trò |
| --- | --- |
| `XMLSignatureFactory` | Tạo Reference, transforms, SignedInfo, signature object |
| `Reference` | URI/transforms/digest data |
| `CanonicalizationMethod` | C14N algorithm URIs |
| `Transform` | Enveloped, base64, XPath/XSLT identifiers và C14N transforms |
| `DigestMethod` | SHA-256 digest identifier |
| `SignatureMethod` | RSA-SHA256 signature identifier |
| `SignedInfo` | Phần metadata và DigestValues được ký |
| `XMLSignature` | `sign`, `validate`, `SignatureValue` |
| `DOMSignContext` | Private key, vị trí chèn Signature, ID registration |
| `DOMValidateContext` | Public key, vị trí Signature, ID registration, security properties |

### Không dùng thuật toán SHA-1 cho XML Signature mới

JDK 17 đã bật **XML Signature secure validation mode theo mặc định** và vô hiệu hóa SHA-1 based XML signatures theo secure-validation policy. SHA-1 không còn là lựa chọn chữ ký số an toàn cho ứng dụng mới. Demo dùng:

```java
fac.newDigestMethod(DigestMethod.SHA256, null);
fac.newSignatureMethod(SignatureMethod.RSA_SHA256, null);
```

Đây là snippets cần `fac` có kiểu `XMLSignatureFactory`. Khóa RSA 2048-bit của demo chỉ phục vụ bài học; hệ thống thật phải có policy độ dài khóa, vòng đời key/certificate và algorithm agility.

### XMLDSig secure validation

```java
DOMValidateContext context =
        new DOMValidateContext(trustedPublicKey, signatureElement);
context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
```

Đây là snippet có public key được cung cấp từ **nguồn tin cậy ngoài tài liệu**, không đọc tin cậy từ một KeyInfo bất kỳ. Trên JDK 17+, secureValidation mặc định đã bật, nhưng đặt true trong context làm rõ ý định. Oracle lưu ý **system property** cùng tên có thể **ưu tiên hơn** context setting; cần kiểm tra cấu hình production.

Secure mode mặc định áp dụng những hạn chế như:

- Chặn XSLT transforms trong validation policy.
- Giới hạn số Reference và transforms để giảm nguy cơ DoS.
- Cấm các thuật toán chữ ký yếu như SHA-1/MD5 theo policy hiện hành.
- Hạn chế URI schemes như `http`, `https` và `file`.
- Hạn chế khóa quá ngắn, duplicate IDs và reference loops.

Cấu hình chính xác phụ thuộc JDK/security provider và `jdk.xml.dsig.secureValidationPolicy`. **Không tắt secure validation chỉ để một chữ ký dùng thuật toán cũ “pass”.** Giải quyết bằng nâng chuẩn chữ ký hoặc interop policy được kiểm soát.

## 10. Ví dụ hoàn chỉnh Java 17+: ký, thay đổi và xác minh

### Mục đích kiểm thử

Fixture tạo `Envelope` chứa `Payment Id="pay-001"` và một `Audit` sibling. `Signature` nằm **bên trong Payment** (enveloped), dùng `Reference URI="#pay-001"`. Program:

- Sinh RSA keypair **trong RAM**, không dùng keystore/Internet.
- Ký với RSA-SHA256, SHA-256 digest.
- Canonicalize `SignedInfo` bằng `CanonicalizationMethod.EXCLUSIVE`.
- Dùng hai Reference transforms đúng thứ tự: `ENVELOPED` → `EXCLUSIVE`.
- Register `Id` bằng `DOMSignContext.setIdAttributeNS` và `DOMValidateContext.setIdAttributeNS`.
- Verify core, SignatureValue và Reference digest độc lập.
- Thử thay đổi lexical/context, nội dung signed/unsigned và tamper SignatureValue.
- Thêm một Payment **unsigned** phía trước Payment được ký để minh họa việc chọn nhầm element.

Không cần bất kỳ external library hoặc database nào. DOM được **tạo trong memory**, không parse input không tin cậy; phần bảo mật khi parse file XML thật được tách riêng ở mục 13.

### File `XmlSignatureC14nDemo.java`

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
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

public final class XmlSignatureC14nDemo {
    private static final String ENV_NS = "urn:example:envelope";
    private static final String PAY_NS = "urn:example:payments";
    private static final String PAY_ID = "pay-001";

    private record SignedDocument(Document doc, Element root, Element payload,
                                  Element amount, Element audit) {}

    private record Result(boolean coreValid, boolean signatureValueValid,
                          boolean referenceDigestValid, String uri,
                          String canonicalization, String signatureAlgorithm,
                          String digestAlgorithm, List<String> transforms) {}

    private static SignedDocument makeSigned(KeyPair keypair) throws Exception {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        Document doc = dbf.newDocumentBuilder().newDocument();
        Element root = doc.createElementNS(ENV_NS, "e:Envelope");
        root.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:e", ENV_NS);
        doc.appendChild(root);

        Element payload = doc.createElementNS(PAY_NS, "p:Payment");
        payload.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI, "xmlns:p", PAY_NS);
        payload.setAttribute("Id", PAY_ID);
        payload.setIdAttribute("Id", true);
        payload.setAttribute("role", "payer");
        root.appendChild(payload);

        Element amount = doc.createElementNS(PAY_NS, "p:Amount");
        amount.setAttribute("currency", "VND");
        amount.setTextContent("1000");
        payload.appendChild(amount);
        Element note = doc.createElementNS(PAY_NS, "p:Note");
        note.setTextContent("Xin chào & hẹn gặp 🌏");
        payload.appendChild(note);

        Element audit = doc.createElementNS(ENV_NS, "e:Audit");
        audit.setTextContent("unsigned-audit");
        root.appendChild(audit);

        XMLSignatureFactory fac = XMLSignatureFactory.getInstance("DOM");
        Transform enveloped = fac.newTransform(
                Transform.ENVELOPED, (TransformParameterSpec) null);
        Transform exclusive = fac.newTransform(
                CanonicalizationMethod.EXCLUSIVE, (TransformParameterSpec) null);
        Reference ref = fac.newReference("#" + PAY_ID,
                fac.newDigestMethod(DigestMethod.SHA256, null),
                List.of(enveloped, exclusive), null, "ref-payment");
        SignedInfo signedInfo = fac.newSignedInfo(
                fac.newCanonicalizationMethod(
                        CanonicalizationMethod.EXCLUSIVE,
                        (C14NMethodParameterSpec) null),
                fac.newSignatureMethod(SignatureMethod.RSA_SHA256, null),
                List.of(ref));
        XMLSignature sig = fac.newXMLSignature(signedInfo, null);
        DOMSignContext context = new DOMSignContext(keypair.getPrivate(), payload);
        context.setDefaultNamespacePrefix("ds");
        context.setIdAttributeNS(payload, null, "Id");
        sig.sign(context);
        return new SignedDocument(doc, root, payload, amount, audit);
    }

    private static Result verify(SignedDocument signed, KeyPair keypair)
            throws Exception {
        Element signatureElement = (Element) signed.payload()
                .getElementsByTagNameNS(XMLSignature.XMLNS, "Signature").item(0);
        if (signatureElement == null) {
            throw new IllegalStateException("Missing ds:Signature element");
        }
        DOMValidateContext context = new DOMValidateContext(
                keypair.getPublic(), signatureElement);
        context.setProperty("org.jcp.xml.dsig.secureValidation", Boolean.TRUE);
        context.setIdAttributeNS(signed.payload(), null, "Id");
        XMLSignatureFactory fac = XMLSignatureFactory.getInstance("DOM");
        XMLSignature sig = fac.unmarshalXMLSignature(context);
        boolean core = sig.validate(context);
        boolean sigValue = sig.getSignatureValue().validate(context);
        Reference ref = (Reference) sig.getSignedInfo().getReferences().get(0);
        boolean refValue = ref.validate(context);
        List<String> transforms = ref.getTransforms().stream()
                .map(t -> ((Transform) t).getAlgorithm()).toList();
        return new Result(core, sigValue, refValue, ref.getURI(),
                sig.getSignedInfo().getCanonicalizationMethod().getAlgorithm(),
                sig.getSignedInfo().getSignatureMethod().getAlgorithm(),
                ref.getDigestMethod().getAlgorithm(), transforms);
    }

    private static SignedDocument fresh(KeyPair keypair) throws Exception {
        return makeSigned(keypair);
    }

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keypair = generator.generateKeyPair();

        SignedDocument original = fresh(keypair);
        Result baseline = verify(original, keypair);
        check("baselineCoreValid", baseline.coreValid());
        check("baselineSignatureValueValid", baseline.signatureValueValid());
        check("baselineReferenceDigestValid", baseline.referenceDigestValid());
        check("referenceOnlyPayment", ("#" + PAY_ID).equals(baseline.uri()));
        check("signedInfoExclusiveC14n",
                CanonicalizationMethod.EXCLUSIVE.equals(baseline.canonicalization()));
        check("signatureRsaSha256",
                SignatureMethod.RSA_SHA256.equals(baseline.signatureAlgorithm()));
        check("referenceSha256",
                DigestMethod.SHA256.equals(baseline.digestAlgorithm()));
        check("referenceEnvelopedThenExclusive",
                baseline.transforms().equals(List.of(
                    Transform.ENVELOPED, CanonicalizationMethod.EXCLUSIVE)));

        SignedDocument sameAttr = fresh(keypair);
        sameAttr.payload().removeAttribute("role");
        sameAttr.payload().setAttribute("role", "payer");
        check("attributeOrderOrReinsertPreserves",
                verify(sameAttr, keypair).coreValid());

        SignedDocument comment = fresh(keypair);
        comment.payload().insertBefore(
                comment.doc().createComment("informational comment"),
                comment.amount());
        check("commentIgnoredByThisReference",
                verify(comment, keypair).coreValid());

        SignedDocument namespace = fresh(keypair);
        namespace.root().setAttributeNS(
                XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
                "xmlns:unused", "urn:example:unused");
        check("unusedAncestorNamespaceIgnored",
                verify(namespace, keypair).coreValid());

        SignedDocument sibling = fresh(keypair);
        sibling.audit().setTextContent("updated-unsigned-audit");
        check("unsignedSiblingCanChange",
                verify(sibling, keypair).coreValid());

        SignedDocument changedText = fresh(keypair);
        changedText.amount().setTextContent("1001");
        Result textResult = verify(changedText, keypair);
        check("signedTextChangeInvalidatesCore",
                !textResult.coreValid());
        check("signedTextChangeFailsReferenceDigest",
                !textResult.referenceDigestValid());
        check("signedTextChangeKeepsSignatureValue",
                textResult.signatureValueValid());

        SignedDocument changedAttribute = fresh(keypair);
        changedAttribute.payload().setAttribute("role", "payee");
        check("signedAttributeValueChangeInvalidates",
                !verify(changedAttribute, keypair).coreValid());

        SignedDocument whitespace = fresh(keypair);
        whitespace.payload().insertBefore(
                whitespace.doc().createTextNode("\n    "),
                whitespace.amount());
        check("signedWhitespaceNodeChangesDigest",
                !verify(whitespace, keypair).coreValid());

        SignedDocument newElement = fresh(keypair);
        Element extra = newElement.doc().createElementNS(PAY_NS, "p:Extra");
        extra.setTextContent("new data");
        newElement.payload().appendChild(extra);
        check("newSignedDescendantInvalidates",
                !verify(newElement, keypair).coreValid());

        SignedDocument wrapping = fresh(keypair);
        Element decoy = wrapping.doc().createElementNS(PAY_NS, "p:Payment");
        decoy.setAttributeNS(XMLConstants.XMLNS_ATTRIBUTE_NS_URI,
                "xmlns:p", PAY_NS);
        decoy.setAttribute("Id", "pay-decoy");
        decoy.setIdAttribute("Id", true);
        Element decoyAmount = wrapping.doc().createElementNS(PAY_NS, "p:Amount");
        decoyAmount.setTextContent("999999");
        decoy.appendChild(decoyAmount);
        wrapping.root().insertBefore(decoy, wrapping.payload());
        check("unsignedDecoyDoesNotBreakCore",
                verify(wrapping, keypair).coreValid());
        check("naiveFirstElementIsDecoy",
                wrapping.root().getElementsByTagNameNS(
                    PAY_NS, "Payment").item(0) == decoy);
        check("signedTargetIsExplicitId",
                wrapping.doc().getElementById(PAY_ID) == wrapping.payload());
        check("signedTargetValueNotDecoy",
                "1000".equals(wrapping.amount().getTextContent())
                && "999999".equals(decoyAmount.getTextContent()));

        SignedDocument changedSignature = fresh(keypair);
        Element dsSignature = (Element) changedSignature.payload()
                .getElementsByTagNameNS(XMLSignature.XMLNS, "Signature").item(0);
        Element dsSignatureValue = (Element) dsSignature
                .getElementsByTagNameNS(XMLSignature.XMLNS, "SignatureValue").item(0);
        String oldValue = dsSignatureValue.getTextContent();
        dsSignatureValue.setTextContent(
                (oldValue.startsWith("A") ? "B" : "A") + oldValue.substring(1));
        Result altered = verify(changedSignature, keypair);
        check("signatureValueTamperInvalidatesCore", !altered.coreValid());
        check("signatureValueTamperFailsCrypto", !altered.signatureValueValid());
        check("signatureValueTamperKeepsReferenceDigest",
                altered.referenceDigestValid());
    }
}
```

### Biên dịch và chạy

Tạo một file `XmlSignatureC14nDemo.java` chứa toàn bộ code trên, sau đó:

```bash
javac --release 17 XmlSignatureC14nDemo.java
java XmlSignatureC14nDemo
```

Các modules `java.xml.crypto`, `java.xml` và `java.base` đã thuộc JDK; không cần Maven, JAR, DB hoặc network. Nếu dùng `module-info.java`, khai báo `requires java.xml.crypto;` và `requires java.xml;`. Đầu ra không in key bytes vì khóa RSA được sinh ngẫu nhiên; các assertions kiểm tra kết quả một cách ổn định.

### Stdout chính xác (OpenJDK 24)

```text
baselineCoreValid=true
baselineSignatureValueValid=true
baselineReferenceDigestValid=true
referenceOnlyPayment=true
signedInfoExclusiveC14n=true
signatureRsaSha256=true
referenceSha256=true
referenceEnvelopedThenExclusive=true
attributeOrderOrReinsertPreserves=true
commentIgnoredByThisReference=true
unusedAncestorNamespaceIgnored=true
unsignedSiblingCanChange=true
signedTextChangeInvalidatesCore=true
signedTextChangeFailsReferenceDigest=true
signedTextChangeKeepsSignatureValue=true
signedAttributeValueChangeInvalidates=true
signedWhitespaceNodeChangesDigest=true
newSignedDescendantInvalidates=true
unsignedDecoyDoesNotBreakCore=true
naiveFirstElementIsDecoy=true
signedTargetIsExplicitId=true
signedTargetValueNotDecoy=true
signatureValueTamperInvalidatesCore=true
signatureValueTamperFailsCrypto=true
signatureValueTamperKeepsReferenceDigest=true
```

**25/25 assertions PASS.** `check` ném `AssertionError` khi có điều kiện sai; các dòng `=true` không được in vô điều kiện. Mã đã được **biên dịch bằng `javac --release 17` và chạy thực tế trên Windows OpenJDK 24**, fixture tạm đã được dọn sạch.

### Nhóm kết quả đáng chú ý

| Nhóm | Những assertions | Điều chứng minh |
| --- | --- | --- |
| Baseline | `baselineCoreValid`, `baselineSignatureValueValid`, `baselineReferenceDigestValid` | Full signature và digest hợp lệ trước khi sửa |
| Đúng phạm vi | `referenceOnlyPayment` | URI trỏ Payment ID pay-001, không ký toàn Envelope |
| Thuật toán | `signedInfoExclusiveC14n`, `signatureRsaSha256`, `referenceSha256`, `referenceEnvelopedThenExclusive` | Hai nơi canonicalize và transforms đúng thứ tự |
| Attribute/comment | `attributeOrderOrReinsertPreserves`, `commentIgnoredByThisReference` | Các thay đổi không đổi canonical bytes trong profile này |
| Namespace ancestor | `unusedAncestorNamespaceIgnored` | Exclusive C14N không bị unused prefix ancestor tác động |
| Unsigned sibling | `unsignedSiblingCanChange` | Audit không được ký |
| Signed content bị sửa | `signedTextChangeInvalidatesCore`, `signedTextChangeFailsReferenceDigest`, `signedTextChangeKeepsSignatureValue` | Reference digest sai, SignatureValue trên SignedInfo còn đúng |
| Signed attribute/whitespace/child | `signedAttributeValueChangeInvalidates`, `signedWhitespaceNodeChangesDigest`, `newSignedDescendantInvalidates` | Các thay đổi thuộc signed subtree làm core fail |
| Decoy / selection | `unsignedDecoyDoesNotBreakCore`, `naiveFirstElementIsDecoy`, `signedTargetIsExplicitId`, `signedTargetValueNotDecoy` | Một Payment chưa ký đứng trước có thể được app chọn nhầm |
| SignatureValue bị sửa | `signatureValueTamperInvalidatesCore`, `signatureValueTamperFailsCrypto`, `signatureValueTamperKeepsReferenceDigest` | Crypto sai, Reference digest vẫn đúng |

## 11. XML signature wrapping: khi verify đúng nhưng ứng dụng đọc nhầm

Mô hình:

```xml
<Envelope>
  <Payment Id="pay-decoy">
    <Amount>999999</Amount>
  </Payment>
  <Payment Id="pay-001">
    <Amount>1000</Amount>
    <Signature>...ký Payment pay-001...</Signature>
  </Payment>
</Envelope>
```

XML trên chỉ là **mô hình minh họa**, không phải một file chữ ký thực. Reference trỏ `#pay-001`, nên `Payment` thứ hai được ký. Sau đó ai đó thêm Payment khác ở đầu Envelope — ngoài phạm vi Reference. Một application **vẫn có thể verify thành công** đối tượng `pay-001`, nhưng lại dùng:

```java
Element first = (Element) doc.getElementsByTagName("Payment").item(0);
```

để đọc business Amount. Đó là **unsigned decoy**. Lỗi không nằm ở RSA, mà ở chỗ application **tin dữ liệu khác dữ liệu đã verify**.

### Phòng vệ thực tế

- Quy định profile xác định **đúng element QName và vị trí** được phép ký.
- Check **Reference URI** có giá trị mong đợi và nằm trong allowlist, không chỉ “có một chữ ký hợp lệ nào đó”.
- Đảm bảo **unique ID** và không chấp nhận trùng ID hoặc mơ hồ namespace.
- Đăng ký/resolve ID theo đúng schema; không dùng `getElementsByTagName(...).item(0)` để thay node được ký.
- Dùng **chính DOM element được kiểm chứng** làm đầu vào business; không lựa chọn lại trên một bản XML khác.
- Giới hạn số lượng các element ký, transforms, refs, và các phần tử cạnh tranh trong schema.
- Xác minh public key/chứng chỉ là của **principal đáng tin và có quyền**; không dùng public key attacker tự cung cấp rồi suy ra đã trusted.
- Có chống replay, kiểm tra audience, transaction ID, timestamp, nonce và tình trạng nghiệp vụ nếu profile yêu cầu.

### Decoy khác duplicate ID

Fixture có **hai ID khác nhau** (`pay-decoy` và `pay-001`) nên minh họa **sai selection logic**, không cần duplicate ID. Những kiểu signature wrapping khác có thể khai thác duplicate IDs, namespace/schema ambiguity hoặc transform selection. JDK secureValidation hạn chế một số trường hợp, **nhưng không thay quy tắc xử lý signed node đúng của application**.

## 12. Trust, authorization và giới hạn của chữ ký hợp lệ

Chữ ký mật mã chỉ bảo đảm rằng **dữ liệu đã được chọn bởi Reference và transforms** không thay đổi so với lúc ký bằng khóa tương ứng, **nếu bạn đã xác lập trust của khóa**. Nó không tự cho biết:

- Chủ thể giữ khóa có được phép chuyển tiền hay không.
- Certificate/key có còn hợp lệ, bị thu hồi hoặc bị thay thế không.
- Thông điệp có đã được chấp nhận trước đó hay chưa (replay).
- XML còn đúng schema/business rules hay không.
- Application có đang sử dụng một element **nằm ngoài scope** chữ ký hay không.
- Tài liệu đã được parse/normalize theo đúng profile được thỏa thuận chưa.

Trong demo, verifier nhận `keypair.getPublic()` từ biến nội bộ. Điều đó **tránh phụ thuộc KeyInfo trong XML**, nhưng **không có nghĩa bài này đã triển khai PKI/certificate trust chain**. Production phải có trust store, policy xác minh danh tính và quyền phù hợp hệ thống.

## 13. Parser security và tác động lên canonicalization

Fixture dùng `DocumentBuilderFactory.newDocumentBuilder().newDocument()` tạo DOM trong memory; nó **không phải** phần xử lý XML không đáng tin từ bên ngoài. Nếu nhận signed XML qua file/network, phải có một parser được harden.

Một đoạn **snippet cấu hình** (không phải chương trình độc lập):

```java
DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
dbf.setNamespaceAware(true);
dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
dbf.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
dbf.setXIncludeAware(false);
dbf.setExpandEntityReferences(false);
```

Các feature strings như `disallow-doctype-decl` có thể phụ thuộc provider; nếu một hardening property bắt buộc không được hỗ trợ, **fail closed** hoặc chọn provider được kiểm chứng. Cần thêm giới hạn bytes, depth, entity expansions, node count, memory, timeouts và HTTP/request limits theo threat model.

**Hai lớp bảo mật khác nhau:** `DocumentBuilderFactory` bảo vệ XML parsing/XXE; `DOMValidateContext` và XMLDSig secure validation bảo vệ Reference dereferencing/algorithms/transforms. Cần **cả hai**, cùng với kiểm tra ID, business binding và trust.

### Parser configuration có thể ảnh hưởng chữ ký

DTD/default attributes, entity expansion, whitespace handling và namespace-aware settings có thể làm parsed DOM khác nhau. Nếu phía ký và phía verify có parse profiles khác, canonicalized node-set có thể khác và digest bị sai. Đừng dùng XML parser thông số không rõ rồi tự sửa/normalize document sau khi ký.

## 14. Vận hành: serialize, migrate và kiểm thử với provider thật

### Đừng pretty-print sau ký rồi kỳ vọng mọi chữ ký vẫn đúng

Một serializer có thể không làm đổi nghĩa khi sắp xếp attributes nhưng lại tạo whitespace nodes trong signed subtree. W3C C14N không có nhiệm vụ loại hết những text nodes này. Khi cần log/hiển thị XML, tạo **bản sao dùng để xem**, đừng coi nó tương đương file cần verify.

### Đừng đổi thuật toán của chữ ký đã ký

Thay `CanonicalizationMethod`, `Reference URI`, `Transforms`, `DigestMethod` hoặc `SignatureMethod` trong `SignedInfo` là **thay đổi chính SignedInfo đã được ký**. Không sửa để “match verifier” rồi mong chữ ký cũ còn giá trị; cần tạo chữ ký mới theo profile được phép.

### Detached binary khác XML node-set

Nếu Reference trỏ raw octets/PDF/ảnh, canonical XML không tự áp dụng. Chỉ các transforms đã được chỉ định (hoặc quy tắc chuẩn xử lý input type theo XMLDSig) quyết định bytes được hash. Không mặc định signed binary file sẽ bỏ qua whitespace hay normalize Unicode.

### Trình tự validate khi có nhiều References

Ứng dụng nhận phải định nghĩa expected references, expected types/locations, algorithms và URI policy. Sau đó dùng core validation, kiểm tra toàn bộ signed data objects, rồi mới đưa dữ liệu nghiệp vụ ra workflow. Nếu chỉ một Reference sai, không tự bỏ qua vì các References khác vẫn đúng.

## 15. Những lỗi thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Hash trực tiếp `xmlString.getBytes()` rồi gọi là XMLDSig | Bỏ qua Reference XML canonicalization semantics | Dùng đúng JSR 105/XMLDSig profile |
| Đồng nhất SignedInfo C14N với Reference C14N | Không biết nguồn octets được băm | Tách hai pipeline |
| Quên enveloped transform | Có thể tự tham chiếu Signature | Dùng `Transform.ENVELOPED` cho enveloped profile |
| Đổi thứ tự Reference transforms | Thay dữ liệu đầu vào digest | Giữ algorithm order chuẩn |
| Chỉ `SignatureValue.validate` | Bỏ qua Reference digest mismatch | `XMLSignature.validate` và expected References |
| Coi every XML sibling đều ký | Lạm dụng phạm vi chữ ký | Enforce expected Reference URIs |
| Chọn node đầu tiên có tên Payment | Có thể chọn unsigned decoy | Lấy đúng verified node |
| Tin KeyInfo do XML cung cấp | Attacker có thể tự ký | Key trust/PKI policy |
| Disable secureValidation để dùng SHA1 | Gỡ security restrictions | Dùng modern algorithms/migration |
| Cho arbitrary remote URI dereference | SSRF / local file read | Restrict URI schemes/resolvers |
| Chấp nhận bất kỳ XPath/XSLT transform | Có thể lọc dữ liệu ký hoặc DoS | Allowlist transforms |
| Nghĩ comments luôn được ký | Profile without-comments có thể loại | Xét URI+algorithm+input node-set |
| Nghĩ C14N trim tất cả whitespace | Pretty print có thể phá digest | Preserve signed subtree |
| Nghĩ C14N normalize Unicode | NFC/NFD vẫn khác bytes | Định nghĩa normalization trước ký |
| Đổi namespace URI hoặc prefixes tùy ý | Có thể đổi canonical representation | Test profile, không chỉnh signed data |
| Xác định ID bằng chuỗi Id tùy ý | Ambiguous resolution/wrapping | Register ID và enforce uniqueness |
| Dùng parser XML không harden | XXE, entity expansion, DoS | Secure parser cùng XMLDSig mode |
| Nêu chỉ có SHA256 là đủ security | Bỏ qua trust/key/authorization | Dùng full protocol security policy |
| So sánh Base64 SignatureValue từ các lần chạy fixture | RSA keys được tạo mới | Assert cryptographic validity |
| Chỉ test XML tự tạo, không test driver/provider | Có thể khác C14N/URI behavior | Integration test với JDK/provider mục tiêu |

## 16. Ma trận kiểm thử tích hợp

| Test | Điều cần xác nhận |
| --- | --- |
| Chữ ký gốc | Core, SignatureValue, mọi Reference đều true |
| Attribute value đổi | Digest/core false |
| Attribute order/quote lexical đổi | Canonicalization ổn định nếu XML semantics giống |
| Empty element notation đổi | Không tự coi là child mới |
| Text value đổi | Digest/core false |
| Whitespace text node mới trong signed subtree | Digest/core false theo profile |
| XML comment thêm | Kiểm tra theo with/without comments + URI semantics |
| Unused ancestor namespace | Exclusive C14N có thể không đổi digest |
| Used prefix/URI đổi | Không được đổi signed QName một cách tùy tiện |
| Di chuyển signed subtree | Inclusive/exclusive behavior đúng protocol |
| Unicode NFC/NFD | Không mặc định C14N normalize |
| Signed child element reorder | Digest fail nếu node order đổi |
| Unsigned sibling đổi | Không coi sibling là trusted data |
| Wrong-node decoy | Application chỉ xử lý đúng signed element |
| Duplicate IDs | Fail closed theo schema/uniqueness policy |
| SignatureValue tamper | Crypto/core false |
| DigestValue/SignedInfo tamper | Core false |
| Nhiều References, một Reference sai | Core false |
| KeyInfo chứa khóa lạ | Không tự coi khóa đáng tin |
| Weak SHA1/XML signature | Secure validation từ chối theo policy |
| External file/HTTP URI | Restriction/allowlist hoạt động, không mở file/network |
| XML DTD/XXE | Parser hardening hoạt động |
| Replay payload hợp lệ | Application replay policy từ chối |
| Certificate expired/untrusted | Trust policy từ chối |
| JDK/provider upgrade | Interop tests vẫn pass |

**Đừng assert tuyệt đối bytes SignatureValue từ mỗi lần sinh khóa mới**. Các kiểm tra có giá trị là scope, cryptographic validity, Reference digests, ID resolution, key trust và business rules.

## 17. Bài tập thực hành

**Bài 1 — Hai pipeline:** Vẽ đường từ `Reference URI` đến `DigestValue` và đường từ `SignedInfo` qua C14N đến `SignatureValue`. Giải thích vì sao hai đường độc lập nhưng liên kết qua SignedInfo.

**Bài 2 — Sai digest:** Đổi `Amount` từ 1000 thành 1001; kiểm tra riêng Reference và SignatureValue. Quan sát Reference false nhưng SignatureValue có thể true.

**Bài 3 — Sai SignatureValue:** Sửa một ký tự `SignatureValue` mà giữ Payment nguyên; quan sát crypto false, Reference true.

**Bài 4 — Comment:** Thêm comment trong Payment. Giải thích vì sao với profile trong demo nó không làm core fail, và vì sao không thể suy rộng thành quy tắc comments chung.

**Bài 5 — Namespace:** Thêm `xmlns:unused` vào Envelope. Với Exclusive C14N, assert core true trong case này; thử tạo **chữ ký mới** với Inclusive C14N để so behavior, không sửa algorithm metadata trong chữ ký đang tồn tại.

**Bài 6 — Whitespace:** Chèn một text node `"\n"` vào Payment. Nếu document vẫn well-formed, vì sao digest vẫn có thể fail?

**Bài 7 — Unsigned sibling:** Đổi Audit, rồi suy nghĩ xem protocol có cần ký cả Audit không. Nếu cần, phải thêm Reference/đổi scope và tạo chữ ký mới.

**Bài 8 — Wrapping:** Thêm Payment chưa ký phía trước, kiểm tra verifier còn true với `#pay-001`. Sửa business logic để dùng đúng element đã resolve theo signed ID, không chọn element đầu tiên.

**Bài 9 — Unicode:** Dùng tên chứa `é` dạng composed và decomposed; so kết quả canonicalization. Không tự chuẩn hóa sau khi ký mà không thống nhất policy hai phía.

**Bài 10 — Security:** Tạo test harness kiểm tra secureValidation không bị tắt, không cho arbitrary file/http URI và không chấp nhận KeyInfo chỉ vì nó chứa một public key. Thực hiện trong môi trường isolated, không truy xuất tài nguyên nhạy cảm.

## 18. Câu hỏi tự kiểm tra

**1. `CanonicalizationMethod` trong SignedInfo dùng để canonicalize cái gì?** Chính SignedInfo, trước khi ký/verify SignatureValue.

**2. Reference transforms chạy lúc nào?** Sau dereference, trước DigestMethod.

**3. Vì sao enveloped-signature transform quan trọng?** Nó tránh đưa Signature nằm trong signed data vào digest tạo vòng phụ thuộc.

**4. Chỉ có `SignatureValue.validate() == true` là đủ chưa?** Chưa. Phải kiểm tra Reference digests và đúng object.

**5. C14N có thể bỏ qua đổi thứ tự attributes không?** Có trong phạm vi XML semantics và algorithm tương ứng; không bỏ qua đổi attribute value.

**6. Thêm whitespace trong signed subtree có an toàn không?** Không nên giả định. Whitespace text node có thể làm digest sai.

**7. Inclusive và exclusive C14N khác gì?** Khác cách xử lý inherited/ancestor namespace context, đặc biệt unused namespaces.

**8. C14N có normalize Unicode NFC/NFD không?** Không.

**9. Comments có luôn được ký không?** Không. Phụ thuộc URI node selection và with/without-comments algorithm.

**10. Reference URI="#id" có ký mọi elements cùng local name không?** Không. Nó chọn dữ liệu theo ID resolution và transforms.

**11. Vì sao phải kiểm tra ID uniqueness?** Để tránh ambiguity/wrapping, không dùng một ID mapping sai.

**12. Signature valid có bảo đảm người ký có quyền không?** Không. Key trust và authorization là bước riêng.

**13. SHA-1 XML signatures có nên dùng cho ứng dụng mới không?** Không; secure policy JDK 17+ đã hạn chế/vô hiệu hóa chúng theo mặc định.

**14. XMLDSig secureValidation có tự chữa lỗi chọn nhầm Payment không?** Không. Business code phải dùng đúng signed node.

**15. Kết quả nào trong demo cho thấy dữ liệu ngoài scope có thể đổi?** `unsignedSiblingCanChange` và `unsignedDecoyDoesNotBreakCore`.

**16. Nếu dữ liệu XML chỉ thay đổi biểu diễn lexical, chữ ký luôn còn đúng?** Không hứa mọi thay đổi; phải xét parsed node-set, transform algorithm, namespaces và whitespace.

**17. Chữ ký khác gì hash dữ liệu?** Hash không có private key trust; SignatureValue ký SignedInfo và các DigestValues được tham chiếu.

**18. Có nên so sánh SignatureValue Base64 giữa hai lần chạy demo?** Không, khóa mới được sinh ngẫu nhiên; hãy kiểm tra core verification.

## Nguồn chính thức còn hiệu lực

- [Oracle Java SE 26 — XML Digital Signature API Overview and Tutorial](https://docs.oracle.com/en/java/javase/26/security/java-xml-digital-signature-api-overview-and-tutorial.html): JSR 105, DOM sign/validate, SignedInfo/Reference pipelines và secure validation.
- [Oracle Java SE 26 — CanonicalizationMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/CanonicalizationMethod.html): Inclusive/Exclusive C14N và with/without comments.
- [Oracle Java SE 26 — Transform](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Transform.html): ENVELOPED và transform APIs.
- [Oracle Java SE 26 — XMLSignature](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignature.html): sign, validate, SignatureValue.
- [Oracle Java SE 26 — XMLSignatureFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/XMLSignatureFactory.html): tạo Reference, SignedInfo, Transform và signature.
- [Oracle Java SE 26 — Reference](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/Reference.html): URI, digest, transforms và Reference validation.
- [Oracle Java SE 26 — DOMSignContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMSignContext.html): private key, vị trí chèn signature và ID registration.
- [Oracle Java SE 26 — DOMValidateContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/dom/DOMValidateContext.html): public key, signature node và secure validation.
- [Oracle Java SE 26 — DigestMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/DigestMethod.html): SHA-256.
- [Oracle Java SE 26 — SignatureMethod](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml.crypto/javax/xml/crypto/dsig/SignatureMethod.html): RSA-SHA256.
- [Oracle JDK 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html): secure XMLDSig validation enabled by default, SHA-1 restriction.
- [W3C — XML Signature Syntax and Processing Version 1.1](https://www.w3.org/TR/xmldsig-core/): Reference transforms, canonicalization, SignedInfo, comments, security and signed-data scope.
- [W3C — Exclusive XML Canonicalization](https://www.w3.org/TR/xml-exc-c14n/): ancestor namespaces và exclusive C14N.
- [W3C — Canonical XML 1.1](https://www.w3.org/TR/xml-c14n11/): inclusive C14N context rules.
- [Oracle Java SE 26 — JAXP Security Guide](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html): secure XML parsing và external resource restrictions.

**Ghi nhớ:** Một `Reference URI` xác định **dữ liệu được bảo vệ**; các transforms chạy **theo thứ tự** để tạo octets tính `DigestValue`. Riêng `SignedInfo/CanonicalizationMethod` xử lý **SignedInfo**, sau đó `SignatureMethod` tạo `SignatureValue`. C14N ổn định một số khác biệt lexical nhưng **không xóa mọi whitespace, không chuẩn hóa Unicode và không tự tin cậy dữ liệu ngoài Reference**. Hãy verify **cả crypto và mọi Reference**, dùng khóa công khai có trust, đăng ký/kiểm tra ID an toàn và xử lý **chính node đã được ký**, không chọn một element khác chỉ vì cùng tên.
