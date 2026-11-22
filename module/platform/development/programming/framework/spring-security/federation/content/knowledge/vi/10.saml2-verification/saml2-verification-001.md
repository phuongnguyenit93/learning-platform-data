# Giải mã thông điệp vận chuyển và phân tích XML bằng thư viện chuyên dụng trong SAML2

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **giải mã lớp vận chuyển** (URL encoding, Base64 và DEFLATE), **phân tích XML** (parse/unmarshal), **giải mã mật mã** (`EncryptedAssertion`) và **xác minh chữ ký**; biết mỗi thao tác bảo vệ điều gì.
2. Mô tả chính xác cách `SAMLRequest`/`SAMLResponse` đi qua **HTTP-Redirect Binding** và **HTTP-POST Binding**, với thứ tự giải mã thích hợp từng loại.
3. Sử dụng **Spring Security SAML2 + OpenSAML** để tiếp nhận, unmarshal và kiểm chứng response thay vì tự đọc `NameID` bằng regex/DOM rồi tạo phiên.
4. Hiểu vai trò `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter`, `RelyingPartyRegistration`, provider OpenSAML và `Saml2Authentication`.
5. Thực hành Java 17+ với Base64 POST và raw DEFLATE Redirect để thấy encoding hoạt động thế nào, nhưng không nhầm demo transport với hệ thống xác thực.
6. Áp dụng parser hardening chống **XXE**, giới hạn tài nguyên chống XML bombs/zip bombs, phòng vệ **XML Signature Wrapping**, xác minh issuer/audience/destination/conditions và bảo vệ dữ liệu nhạy cảm.

## 1. Bản chất của SAML2 message processing

**SAML 2.0** sử dụng XML để biểu diễn protocol messages như `AuthnRequest`, `Response` và assertions về một người dùng. **Binding** mô tả cách những message ấy đi trên đường truyền (ví dụ HTTP Redirect hoặc HTTP POST). Một thông điệp “được chuyển đi thành công” chỉ nói rằng bên nhận có bytes để xử lý, **không** chứng minh được người dùng đã xác thực.

Trong mô hình Web Browser SSO:

- **Service Provider (SP) / Relying Party (RP):** ứng dụng Spring Boot nhận SAMLResponse tại Assertion Consumer Service (ACS), kiểm chứng và tạo phiên nếu đủ điều kiện.
- **Identity Provider (IdP) / Asserting Party (AP):** xác thực người dùng, phát Response/Assertion, ký bằng private signing key của IdP và có thể mã hóa assertion cho SP.
- **Browser:** đi theo redirect hoặc submit HTML form. Browser là **kênh vận chuyển không đáng tin cậy**, không phải nơi xác minh danh tính.
- **OpenSAML:** thư viện phân tích/biểu diễn/kiểm chứng đối tượng SAML. Spring Security xây một lớp tích hợp an toàn quanh những chức năng đó.
- **RelyingPartyRegistration:** danh tính IdP/SP, certificate và endpoint đã được thiết lập tin cậy trước khi nhận response.

### 1.1. Phân tách các bước để không tạo lỗ hổng

| Bước | Thao tác | Đầu ra | Điều **chưa** được bảo đảm |
| --- | --- | --- | --- |
| HTTP transport | Servlet đọc form/query parameter | Chuỗi `SAMLResponse` hoặc `SAMLRequest` | Chưa chắc input hợp lệ |
| Transport decode | URL decode / Base64 / Inflate theo đúng binding | Bytes XML | Không xác thực chữ ký/nguồn phát hành |
| XML parsing | Parser an toàn đọc namespace và element | Cấu trúc XML | Không biết IdP có đáng tin |
| SAML unmarshalling | OpenSAML chuyển XML sang `Response`, `Assertion`, `Issuer`... | Domain objects | Chưa đánh giá điều kiện giao thức |
| Cryptographic processing | Chữ ký, trusted cert, giải mã encrypted elements khi cần | Dữ liệu có thể kiểm chứng | Chưa đủ nếu audience/recipient/expiry sai |
| SAML validation | Issuer, destination, audience, timestamp, `InResponseTo`, subject confirmation... | Assertion hợp lệ với SP và giao dịch | Không tự cấp toàn bộ quyền nghiệp vụ |
| Spring authentication | Tạo principal/authorities/`SecurityContext` | Phiên đăng nhập ứng dụng | Authorization từng tài nguyên vẫn riêng |

**Ba khác biệt cần nhớ:**

- **Base64 ≠ encryption:** ai có chuỗi Base64 đều có thể khôi phục bytes.
- **Parse XML thành công ≠ verify SAML:** message có thể là XML hợp lệ nhưng tự ký, hết hạn hoặc dành cho ứng dụng khác.
- **Decrypt thành công ≠ signature verified:** mã hóa bảo mật nội dung, chữ ký và điều kiện SAML kiểm tính tin cậy của kết quả.

## 2. Toàn cảnh luồng SP-initiated SAML2

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant SP as Spring Security SP
    participant IdP as IdP
    User->>Browser: Mở /reports
    Browser->>SP: GET /reports (anonymous)
    SP-->>Browser: Redirect tới AuthnRequest
    Browser->>SP: GET /saml2/authenticate/company
    SP->>SP: Sinh AuthnRequest, ID và RelayState
    SP-->>Browser: Redirect SAMLRequest encoded tới IdP
    Browser->>IdP: GET /sso?SAMLRequest=...
    IdP->>IdP: Decode/parse AuthnRequest; verify chữ ký nếu cần
    IdP->>User: Login hoặc dùng SSO session
    User->>IdP: Xác thực
    IdP->>IdP: Tạo và ký SAMLResponse/Assertion
    IdP-->>Browser: Form SAMLResponse Base64
    Browser->>SP: POST /login/saml2/sso/company
    SP->>SP: Decode, OpenSAML parse/unmarshal
    SP->>SP: Verify/decrypt/validate issuer, audience, state, time
    alt Hợp lệ
        SP->>SP: Tạo Saml2Authentication và session
        SP-->>Browser: Redirect tới /reports
    else Không hợp lệ
        SP-->>Browser: Authentication failure
    end
```

Luồng phổ biến sử dụng **Redirect cho AuthnRequest** và **POST cho SAMLResponse**. Hai binding không phải lúc nào cũng cố định như vậy; hãy đối chiếu metadata và thỏa thuận của IdP/SP. Mọi response qua browser đều là input bên ngoài cho SP.

## 3. So sánh HTTP-POST, HTTP-Redirect và Artifact

| Binding | Cách mang message | Bước khôi phục dữ liệu | Thường dùng |
| --- | --- | --- | --- |
| **HTTP-POST** | HTML form có `SAMLResponse` hoặc `SAMLRequest` chứa Base64-encoded XML | HTTP form decode → Base64 decode → XML parse | Response từ IdP tới ACS của SP |
| **HTTP-Redirect** | Query URL có `SAMLRequest`/`SAMLResponse` dạng raw DEFLATE → Base64 → URL-encode | URL decode → Base64 decode → raw DEFLATE inflate → XML parse | AuthnRequest từ SP tới IdP |
| **HTTP-Artifact** | Browser chỉ mang một artifact/reference; message được truy xuất bằng back-channel đã thỏa thuận | Artifact resolution protocol và kiểm trust | Một số triển khai cần front-channel nhỏ |
| **SOAP/back-channel** | SOAP XML server-to-server | SOAP/SAML protocol processing | Artifact resolution hoặc các flow phụ |

Đừng áp dụng một đoạn mã “giải mã SAML” chung cho mọi binding. Nếu HTTP-POST message vốn là Base64 XML mà lại đem `Inflater` chạy lên, kết quả thường là lỗi dữ liệu nén. Nếu HTTP-Redirect raw DEFLATE mà chỉ Base64 decode rồi coi output là XML, parser sẽ thấy bytes nén không phải XML.

### 3.1. Chữ ký ở hai binding khác nhau

- Với **POST binding**, chữ ký thường là **XML Signature** trong `Response`/`Assertion`, kiểm theo XML Signature và policy trust.
- Với **Redirect binding**, chữ ký có thể ở tham số `SigAlg`/`Signature` của query; chữ ký được tính trên đúng chuỗi các query parameters **đã URL-encode** theo thứ tự ràng buộc. Vì vậy XML đã giải nén **có thể không chứa** `<ds:Signature>` dù Redirect request được ký.
- Đừng giải mã URL, ghép query tùy tiện rồi kiểm chữ ký, vì có thể làm biến đổi bytes được ký.
- Không được tin certificate nằm trong message mà không đối chiếu với trust configuration đã thẩm định.

**Transport encoding không tạo bảo mật.** Chính chữ ký/trust và các điều kiện SAML mới cho phép SP chấp nhận định danh.

## 4. HTTP-POST Binding: từ form field đến XML

Ví dụ IdP gửi HTML form:

```html
<!-- Dữ liệu rút gọn; không phải SAMLResponse có thể đăng nhập -->
<form method="post" action="https://portal.example.org/login/saml2/sso/company">
  <input type="hidden" name="SAMLResponse" value="BASE64_ENCODED_XML" />
  <input type="hidden" name="RelayState" value="OPAQUE_STATE" />
  <button type="submit">Continue</button>
</form>
```

Khi browser submit:

```http
POST /login/saml2/sso/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_ENCODED_XML&RelayState=OPAQUE_STATE
```

Quy trình đọc:

1. Servlet container xử lý HTTP body đúng content type và cung cấp parameter `SAMLResponse`; đừng decode form-urlencoded hai lần.
2. Base64 decoder phục hồi bytes XML. **POST binding thông thường không cần DEFLATE.**
3. Parser XML được cấu hình an toàn đọc document và namespace; OpenSAML unmarshaller xây `Response` và các kiểu SAML liên quan.
4. Provider kiểm chữ ký theo IdP verification certificate, giải mã `EncryptedAssertion` nếu xuất hiện, rồi kiểm issuer, destination, audience, time conditions và request correlation.
5. Chỉ khi tất cả kiểm tra cần thiết thành công mới tạo `Saml2Authentication`.

### 4.1. Thận trọng với dấu `+` và URL encoding

Base64 alphabet có `+`, `/` và ký tự padding `=`. Trong `application/x-www-form-urlencoded`, dấu `+` có thể bị coi là khoảng trắng nếu form encoding bị xử lý sai. Không nên:

- Tự đọc raw POST body rồi `replace("+", " ")`.
- Gọi `URLDecoder.decode` lần hai trên giá trị parameter vốn đã được container giải form encoding.
- Ghi thông điệp Base64 ra log để sao chép vào một tool rồi tin rằng bytes không bị biến đổi.
- Cố lấy Base64 “đẹp” bằng cách xóa tất cả ký tự lạ và vẫn tiếp tục xác thực.

Hãy dùng binding handling đã được kiểm thử của Spring Security/OpenSAML. Nếu có lỗi transport, kiểm raw HTTP capture **trong môi trường kiểm soát và che dữ liệu nhạy cảm**.

### 4.2. Đã có XML nhưng chưa có user tin cậy

Sau Base64 decode có thể thấy `<samlp:Response>` và `<saml:Assertion>`, nhưng cũng có thể có `<saml:EncryptedAssertion>`. XML parser thấy **EncryptedAssertion node** không có nghĩa đọc được `NameID` bên trong. Cần SP private decryption key phù hợp, do IdP mã hóa bằng SP public encryption certificate.

XML chữ ký hợp lệ nhưng sai `AudienceRestriction` cũng phải bị từ chối. XML với `NameID=admin` hoàn toàn có thể do một bên không đáng tin tự tạo. Không dùng parser để cấp quyền.

## 5. HTTP-Redirect Binding: URL decode, Base64, raw DEFLATE

Đây là ví dụ khi SP gửi `AuthnRequest` cho IdP qua HTTP Redirect:

```http
HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=ENCODED&RelayState=OPAQUE
```

Thứ tự gửi:

```text
AuthnRequest XML
    -> UTF-8 bytes
    -> raw DEFLATE compress
    -> Base64 encode
    -> URL encode
    -> Query parameter SAMLRequest
```

Thứ tự nhận:

```text
SAMLRequest query (URL decode đúng một lần)
    -> Base64 decode
    -> raw DEFLATE inflate
    -> XML bytes
    -> Parser XML + SAML unmarshaller
    -> Binding signature + protocol validation theo vai trò
```

**Raw DEFLATE** khác GZIP và zlib wrapper. Trong Java, khi thử raw DEFLATE dùng `Inflater(true)`. Bản production phải ưu tiên HTTP-Redirect decoder của thư viện vì ngoài giải nén còn có chữ ký `SigAlg`/`Signature`, raw query encoding và các giới hạn tài nguyên.

### 5.1. Chống “compression bombs”

Một input nén cực nhỏ có thể phình ra XML rất lớn. Phải kiểm:

- Độ dài URL/query nhận được; Base64 string length và bytes nén.
- **Kích thước output sau inflate**, không chỉ bytes nén.
- Timeout/CPU và limits của servlet container/decoder/parser.
- Kết thúc stream và dữ liệu nén có hợp lệ không; không chấp nhận dữ liệu chưa kiểm.
- Độ sâu XML, số node/attributes và entity expansion.

Không dùng “Inflate hết rồi mới kiểm `String.length`” nếu có nguy cơ cạn bộ nhớ trước khi kiểm.

### 5.2. Đường ký của Redirect binding

Khi có `SigAlg` và `Signature`, chữ ký bảo vệ thông điệp theo SAML HTTP-Redirect binding. Một triển khai tự ý URL-decode, reorder parameters, encode lại theo charset khác rồi ký/verify có thể sai ngay cả khi XML vẫn đọc được.

Vì thế: **đối với xác thực thật, luôn giao cả decoding/binding signature cho OpenSAML và Spring Security theo vai trò**, không chỉ chạy `Base64.getDecoder()` + `Inflater` rồi giả định chữ ký hợp lệ.

## 6. Ví dụ Java 17 chạy được: POST Base64 và XML parser an toàn cho demo

Mục đích: thấy rõ “đọc được XML” **không bằng** “đăng nhập hợp lệ”. Đoạn này dùng JDK 17, một XML mẫu tự tạo trong bộ nhớ, Base64 decode và JAXP parser có cấu hình chống XXE. Nó **không có XML Signature validation, decryption, SAML profile checks hoặc trust configuration** và **tuyệt đối không dùng làm ACS/login handler**.

**Tệp `PostTransportDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;

public final class PostTransportDemo {
    private static final int MAX_XML_BYTES = 16 * 1024;

    public static void main(String[] args) throws Exception {
        String xml = """
                <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                                ID="_demo" Version="2.0"/>
                """;
        String formParameter = Base64.getEncoder()
                .encodeToString(xml.getBytes(StandardCharsets.UTF_8));
        byte[] bytes = Base64.getDecoder().decode(formParameter);

        if (bytes.length > MAX_XML_BYTES) {
            throw new IllegalArgumentException("XML too large");
        }

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        Document document = factory.newDocumentBuilder()
                .parse(new ByteArrayInputStream(bytes));
        System.out.println("Root local name: "
                + document.getDocumentElement().getLocalName());
        System.out.println("Trusted authentication: false");
    }
}
```

Lệnh:

```bash
javac PostTransportDemo.java
java PostTransportDemo
```

Stdout chính xác:

```text
Root local name: Response
Trusted authentication: false
```

**Lý giải:**

- `Base64` và `DocumentBuilderFactory` thuộc JDK chuẩn, không cần Spring/OpenSAML cho bài tập transport.
- `newDefaultInstance()` chọn parser JDK có hỗ trợ Java 17; `namespaceAware` để phân biệt local name/namespace.
- `disallow-doctype-decl` giúp từ chối DTD; `FEATURE_SECURE_PROCESSING` và external-access restrictions làm giảm tấn công XXE/resource. Nếu một security setting thiết yếu không hỗ trợ, code **ném lỗi** và không lặng lẽ xử lý tiếp.
- `MAX_XML_BYTES` là một **ngưỡng lab** để tránh input lớn; sản phẩm thật phải giới hạn request size và parser resources **trước** khi cấp phát/decode.
- `Response` chỉ là local name. Parser chưa xác minh đúng SAML namespace, không kiểm chữ ký hoặc token đã dành cho đúng SP.
- **Không sửa dòng `Trusted authentication: false` thành true** dựa trên kết quả parser. Authentication phải qua thư viện SAML có kiểm đầy đủ.

### 6.1. Vì sao DOM/JAXP không thay OpenSAML?

XML parser chung chỉ hiểu cấu trúc tài liệu. SAML yêu cầu XML Signature validation trên **đúng node được ký**, canonicalization, trust X.509, issuer, audience, recipient, `InResponseTo`, điều kiện bearer subject và thời gian. DOM/XML syntax không tự biết các điều kiện đó.

Một cách làm sai:

```java
// Anti-pattern; KHÔNG dùng làm kiểm chứng SAML.
String xmlText = new String(
        java.util.Base64.getDecoder().decode(samlResponseParam),
        java.nio.charset.StandardCharsets.UTF_8);
if (xmlText.contains("admin")) {
    // Không được tự tạo Authentication/ROLE_ADMIN.
}
```

Kẻ tấn công có thể đưa chuỗi “admin” vào XML tùy ý; có thể có namespace prefix khác, node giả hoặc assertion không được ký. **Chỉ tin principal sau khi SAML validation hoàn chỉnh**.

## 7. Ví dụ Java 17 chạy được: round-trip raw DEFLATE cho Redirect

Đoạn sau nén một XML mẫu bằng **raw DEFLATE**, Base64 và giải ngược lại để minh họa. Không tính `SigAlg`/`Signature`, không tạo một AuthnRequest đúng chuẩn để gửi IdP; chỉ quan sát encoding trong lab.

**Tệp `RedirectTransportDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public final class RedirectTransportDemo {
    private static final int MAX_INFLATED_BYTES = 16 * 1024;

    public static void main(String[] args) throws Exception {
        String xml = "<samlp:AuthnRequest "
                + "xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\" "
                + "ID=\"_demo\" Version=\"2.0\"/>";

        byte[] compressed;
        try (ByteArrayOutputStream sink = new ByteArrayOutputStream()) {
            Deflater deflater =
                    new Deflater(Deflater.DEFAULT_COMPRESSION, true);
            try (DeflaterOutputStream out =
                    new DeflaterOutputStream(sink, deflater)) {
                out.write(xml.getBytes(StandardCharsets.UTF_8));
            } finally {
                deflater.end();
            }
            compressed = sink.toByteArray();
        }

        String base64 = Base64.getEncoder().encodeToString(compressed);
        byte[] restored;
        Inflater inflater = new Inflater(true);
        try (InflaterInputStream input = new InflaterInputStream(
                new ByteArrayInputStream(
                        Base64.getDecoder().decode(base64)), inflater);
             ByteArrayOutputStream sink = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (sink.size() + n > MAX_INFLATED_BYTES) {
                    throw new IllegalArgumentException("Inflated XML too large");
                }
                sink.write(buffer, 0, n);
            }
            restored = sink.toByteArray();
        } finally {
            inflater.end();
        }

        String result = new String(restored, StandardCharsets.UTF_8);
        System.out.println("Round trip matches: " + xml.equals(result));
        System.out.println("Trusted authentication: false");
    }
}
```

Lệnh:

```bash
javac RedirectTransportDemo.java
java RedirectTransportDemo
```

Stdout chính xác:

```text
Round trip matches: true
Trusted authentication: false
```

Ở HTTP Redirect thật còn có **URL-encoding vào query string**: khi nhận, container/binding processor phải URL-decode đúng một lần trước Base64. Đoạn demo cố ý bỏ bước HTTP URL vì input được tạo trong bộ nhớ. Không sử dụng bản demo để kiểm chữ ký Redirect; đó là chức năng của binding handler chuyên dụng.

### 7.1. Vì sao không nên tự dùng đoạn demo trong production?

- Không phân tích `RelayState`, `SigAlg` và `Signature`.
- Không kiểm bytes được ký đúng theo HTTP-Redirect binding.
- Không biết SP/IdP entity ID, destination, service registration hay SAML message schema.
- Không có XML parser/SAML unmarshaller và SAML signature/conditions validator.
- Chỉ chặn kích thước **sau** một số bước cấp phát bộ nhớ; production cần tầng giới hạn HTTP/URL/Base64 sớm hơn.
- Không nên chấp nhận URL/metadata/issuer theo input tùy ý từ browser.

**Dùng JDK demo để học; dùng OpenSAML/Spring Security để xác thực.**

## 8. OpenSAML đọc XML thành mô hình đối tượng SAML

OpenSAML xử lý nhiều kiểu domain:

| XML / khái niệm | Kiểu/ý nghĩa trong SAML |
| --- | --- |
| `<samlp:Response>` | Vỏ protocol response, status, issuer, destination, ID, InResponseTo |
| `<saml:Assertion>` | Nội dung assertion về một subject, authentication/attributes/conditions |
| `<saml:Issuer>` | Bên phát hành request/response/assertion |
| `<saml:Subject>` và `<saml:NameID>` | Định danh chủ thể, không nhất thiết là email |
| `<saml:Conditions>` | Thời gian hiệu lực và giới hạn sử dụng |
| `<saml:AudienceRestriction>` | SP nào được phép nhận assertion |
| `<saml:SubjectConfirmation>` | Điều kiện xác nhận chủ thể/recipient/InResponseTo |
| `<saml:AuthnStatement>` | Thời điểm/phương thức xác thực theo profile |
| `<saml:AttributeStatement>` | Claims/attributes được IdP phát hành |
| `<saml:EncryptedAssertion>` | Assertion được mã hóa, cần private key SP |
| `<ds:Signature>` | XML Signature cần kiểm bằng trust material đúng issuer |

**Unmarshaller** chuyển XML DOM elements sang các `XMLObject` SAML có cấu trúc/namespace đúng. **Validator** và provider xác định có tin được những object này hay không. Đừng dùng `Unmarshaller` đơn độc để login: một object SAML có đủ field về mặt cấu trúc chưa chắc có chữ ký tin cậy.

### 8.1. Vì sao phân tích bằng regex/string search nguy hiểm?

XML cho phép đổi namespace prefix; chuỗi `<saml:NameID>` và `<x:NameID>` có thể cùng namespace. Ngược lại hai prefix giống nhau nhưng namespace khác cũng có thể là dữ liệu khác. Ngoài ra còn có:

- Namespace spoofing và các node trùng tên.
- `EncryptedAssertion` chưa giải mã.
- XML Signature Wrapping, duplicate IDs hoặc chữ ký bảo vệ **node A** trong khi code lấy user ở **node B**.
- XML entities/DTD dẫn tới XXE, SSRF hoặc tiêu thụ tài nguyên.
- Response có nhiều assertions, signature ở Response hoặc từng Assertion tùy profile.
- Message sai audience, thời hạn, destination hoặc request correlation.

Đọc được văn bản `NameID` chỉ là đọc một **claim**; trước khi tin, phải bảo đảm claim thuộc **đối tượng SAML được bảo vệ và hợp lệ**.

### 8.2. XML Signature Wrapping (XSW)

Signature có thể dùng ID reference đến một assertion. Kẻ tấn công có thể chèn một assertion khác ngoài phần được ký; một parser/validator tự viết có thể kiểm một node có chữ ký nhưng lấy identity từ node không ký. Biện pháp:

1. Sử dụng thư viện SAML được duy trì, có handling ID uniqueness và signature references.
2. Kiểm đúng **node đã được ký**/bảo vệ, không chọn assertion theo vị trí DOM tùy ý.
3. Certificate dùng verify phải đến từ **IdP metadata/registration được thẩm định**, không tự tin mọi `KeyInfo` trong message.
4. Cấu hình signed-response/signed-assertion policy phù hợp; không bỏ kiểm XML Signature vì “decode được”.
5. Cập nhật Spring Security/OpenSAML và thử negative cases khi IdP thay đổi profile.

### 8.3. XML External Entity (XXE)

XML là đầu vào không tin cậy. Parser sai có thể đọc file nội bộ hoặc thực hiện network request qua external entity. Các lớp phòng vệ:

- Từ chối `DOCTYPE`/DTD khi không cần.
- Tắt external general/parameter entities, external DTD loading và XInclude.
- Kiểm soát external schema/stylesheets resource access.
- Dùng `FEATURE_SECURE_PROCESSING` và các parser resource limits tương ứng.
- **Fail closed** nếu parser không hỗ trợ cờ security cần thiết; không tiếp tục bằng parser mặc định không được thẩm định.
- Không thêm “XML pretty-print debug parser” không cứng hóa bên cạnh OpenSAML.

Đừng sửa XXE bằng regex xóa chuỗi `<!DOCTYPE>`, vì parser còn xử lý nhiều cấu trúc/encoding và có thể tìm cách vòng qua.

## 9. Spring Security: các thành phần trong inbound SAMLResponse

Trong Servlet application sử dụng `spring-security-saml2-service-provider`, luồng phổ biến:

```text
Browser POST /login/saml2/sso/company
  -> Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationTokenConverter
       + HttpServletRequest
       + RelyingPartyRegistration(company)
       -> Saml2AuthenticationToken
  -> AuthenticationManager
  -> OpenSAML authentication provider
       -> Deserialize/unmarshal Response
       -> Verify signatures with trusted IdP certificate
       -> Decrypt encrypted elements using SP private key
       -> Validate issuer, destination, audience, conditions, state
       -> Create Saml2AuthenticatedPrincipal/authorities
  -> Saml2Authentication
  -> SecurityContext and app session (if accepted)
```

Lớp `Saml2AuthenticationTokenConverter` lấy response từ request và gắn đúng registration để provider biết **tin ai, nhận cho entity ID nào, giải mã bằng khóa nào**. Nó không nên là nơi business code tự kết luận login thành công chỉ vì parameter có tồn tại.

**Chú ý phiên bản:** Spring Security 6.x có provider triển khai OpenSAML với tên version-specific (ví dụ `OpenSaml4AuthenticationProvider` hoặc `OpenSaml5AuthenticationProvider` tùy dependency/version); tài liệu Spring Security hiện hành mô tả `OpenSaml5AuthenticationProvider`. Khi cấu hình extension, hãy tra API **chính xác version dự án đang dùng**, không copy class từ một release khác. Ý nghĩa chung về decode/unmarshal/verify/decrypt/validate vẫn như nhau.

### 9.1. Tầm quan trọng của `RelyingPartyRegistration`

Mỗi RP registration cung cấp:

- `registrationId` – định danh cấu hình local (ví dụ `company`).
- SP `entityId`, ACS URL – assertion phải được phát cho SP và endpoint này.
- IdP `entityId/issuer`, SSO URL/metadata – nguồn SAML được tin.
- **IdP verification certificates** – public signing cert dùng verify response/assertion.
- **SP decryption credentials** – private key SP khi IdP phát EncryptedAssertion.
- **SP signing credentials** – private key SP nếu phải ký AuthnRequest.

Nếu chọn sai registration trong hệ đa IdP, dễ dẫn tới issuer/certificate mismatch. Không tự “thử tất cả các cert của mọi IdP cho đến khi một cert hợp lệ” nếu làm mất ranh giới tenant/trust.

### 9.2. Trình tự cryptographic validation

Một provider SAML đã được cấu hình đúng cần xác minh Response Signature (nếu có), giải mã EncryptedAssertion khi cần, đối chiếu Response Issuer/Destination, kiểm Assertion signatures, xử lý encrypted elements và các điều kiện như AudienceRestriction, bearer SubjectConfirmation, thời hạn. Thứ tự chi tiết của từng bước có thể khác theo phiên bản và vị trí chữ ký/encryption.

**Không tự reorder** “giải mã mọi XML, sửa DOM, rồi tính lại signature” vì XML canonicalization và signature references có thể thay đổi. Nếu response chỉ ký outer Response khác với assertion có chữ ký riêng, thời điểm giải mã các encrypted elements cũng quan trọng.

### 9.3. Khi nào tạo `Saml2Authentication`?

Chỉ sau khi SAML provider kết luận hợp lệ, Spring Security mới đưa principal/authorities vào `Authentication` và lưu trong `SecurityContext`/session theo cách đăng nhập web. `NameID` thường là nguồn cho `Authentication#getName()`; một số hệ thống ánh xạ principal khác theo policy.

**Quyền truy cập** vẫn thuộc ứng dụng: đăng nhập từ IdP không tự cấp `ROLE_ADMIN`. Nếu user đã authenticated nhưng thiếu quyền tài nguyên, ứng dụng có thể trả 403 mà không liên quan transport XML.

## 10. Ví dụ Spring Boot 3 / Spring Security 6: không tự viết ACS parser

Ví dụ Java 17+ dưới đây là cấu hình trong một **dự án Spring Boot Servlet**. Nó cần IdP thật, metadata/entity IDs/ACS đúng, trusted cert X.509 hợp lệ. Không thể dùng `javac` đơn lẻ vì có Spring dependencies; các domain `example.org` chỉ dùng minh họa.

### 10.1. Gradle dependencies

Tệp `build.gradle` đã áp dụng Spring Boot plugin và dependency management; phần dependencies cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Dùng Spring Security/OpenSAML được BOM/repositories của version dự án hỗ trợ. Đừng tự kéo OpenSAML version không tương thích chỉ vì một bài viết cũ dùng class khác.

### 10.2. Cấu hình registration thủ công bằng YAML

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/company"
            acs:
              location: "https://portal.example.org/login/saml2/sso/company"
            assertingparty:
              entity-id: "https://idp.example.org/saml"
              verification:
                credentials:
                  - certificate-location: "classpath:idp-signing.crt"
              singlesignon:
                url: "https://idp.example.org/sso"
                sign-request: false
```

Giải thích:

- `company` là tên registration local, dùng trong `/saml2/authenticate/company` và ACS `/login/saml2/sso/company`.
- `entity-id` tại cấp registration là SP entity ID; IdP phải đăng ký và chỉ phát assertions cho đúng audience.
- `acs.location` phải khớp URL HTTPS bên ngoài mà browser có thể POST và IdP công nhận. Reverse proxy không được tự tạo sai host/scheme.
- `assertingparty.entity-id` là issuer IdP được trust; khác entity ID của SP.
- `verification.credentials` là **public signing certificate của IdP đã xác minh nguồn**; không lấy từ response tự khai báo.
- `sign-request: false` chỉ đúng nếu IdP cho phép request không ký. Nếu bắt buộc signed AuthnRequest, phải thêm SP signing private key/cert và dùng `true`.
- Nếu nhận `EncryptedAssertion`, cần bổ sung `decryption.credentials` của SP để OpenSAML giải mã khi xác thực.

**YAML không thể khởi chạy đầy đủ nếu thiếu `idp-signing.crt` thật** và đăng ký IdP đúng. Đây là ví dụ code/config, không phải một sản phẩm SSO đã được deploy.

### 10.3. SecurityFilterChain Java 17+

Tệp `src/main/java/com/example/saml/SamlSecurityConfiguration.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated()
                )
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
```

Với `saml2Login()`, Spring Security đã cung cấp filters cho outbound `AuthnRequest` và inbound SAMLResponse tại ACS. **Không cần tự viết HTTP controller nhận POST rồi Base64 decode, parse XML và tự cấp session.**

Anti-pattern:

```java
// Không sử dụng cách này để xác thực SAML2.
@PostMapping("/login/saml2/sso/company")
void accept(String samlResponse) {
    // Base64 decode -> lấy NameID -> tự đánh dấu authenticated: SAI.
}
```

Trường hợp muốn **tùy chỉnh** cách validate/nhận response, phải sử dụng extension points của `Saml2LoginConfigurer`/provider đang dùng; giữ mặc định chữ ký, issuer, audience, recipient, time và request correlation. Không tạo một “ngõ tắt” authentication ngoài Spring Security.

### 10.4. Lớp khởi động và controller

Tệp `src/main/java/com/example/saml/SamlDemoApplication.java`:

```java
package com.example.saml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/saml/ReportController.java`:

```java
package com.example.saml;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/")
    String home() {
        return "Public";
    }

    @GetMapping("/reports")
    String reports(Authentication authentication) {
        return "Authenticated as " + authentication.getName();
    }
}
```

Nếu IdP thật gửi assertion hợp lệ có NameID `employee-42` và ứng dụng chấp nhận, HTTP response của `GET /reports` có thể là:

```text
Authenticated as employee-42
```

Đây là kết quả **có điều kiện** theo NameID thực tế, không phải stdout của `javac`. Người học phải cấu hình IdP/ACS/cert đúng và đi hết browser SSO mới nhìn thấy kết quả.

## 11. Xác minh chữ ký và mã hóa không thể bỏ qua

### 11.1. Signature trust

IdP ký Response/Assertion bằng **private signing key của IdP**. SP dùng **public signing certificate IdP đã tin** trong registration để xác minh. Nếu Response chứa `<KeyInfo>` hoặc certificate tự đính kèm, certificate ấy **không tự thành trusted key**. Một attacker có thể tự ký response với khóa của chính mình và đính cert tương ứng.

Chữ ký hợp lệ với một cert **chưa đủ** nếu issuer, audience, recipient, time conditions hoặc request correlation sai.

### 11.2. XML Signature Wrapping

SAML XML có thể chứa nhiều phần tử; XML Signature có thể bảo vệ một assertion theo ID. Nếu ứng dụng tự chọn một `NameID` khác ngoài node đã được verify, attacker có thể lạm dụng **XML Signature Wrapping**. Vì vậy cần dùng đúng dữ liệu đã được provider xác nhận, không tự parse toàn bộ document rồi tra node theo vị trí.

### 11.3. Decryption credentials

IdP có thể dùng public encryption certificate của SP để mã hóa `EncryptedAssertion`. SP giải mã bằng **private decryption key của SP** trong `RelyingPartyRegistration`. Đây là phép toán mật mã thật, **không phải Base64 decode**.

Nếu IdP đổi SP encryption certificate trong quá trình rotation, SP có thể cần giữ private key cũ/mới trong giai đoạn giao thoa theo thư viện và chính sách. Không gỡ bỏ signature verification để “giải mã cho được”.

### 11.4. Chữ ký và XML encoding

XML Signature nhạy với canonicalization/Reference URI/ID mapping. Không pretty-print/re-serialize/modification một signed element rồi mong chữ ký vẫn hợp lệ. Binding handler và provider sẽ làm việc trên cấu trúc/bằng chứng theo chuẩn; phần debug chỉ nên quan sát dữ liệu đã khử nhạy cảm.

## 12. Những kiểm tra SAML cần thực hiện sau parsing

| Điều kiện | Mục đích |
| --- | --- |
| **Issuer** | Response/Assertion đến từ IdP đã được đăng ký |
| **Destination/Recipient** | Browser POST tới ACS đúng thỏa thuận, assertion dành cho endpoint hợp lệ |
| **AudienceRestriction** | Assertion dành cho đúng SP entity ID, không phải SP khác |
| **InResponseTo** | Trong SP-initiated flow, response liên kết AuthnRequest của SP; ngăn mix-up/login CSRF |
| **NotBefore / NotOnOrAfter** | Assertion chưa đến hạn/đã hết hạn phải bị từ chối |
| **SubjectConfirmation** | Kiểm điều kiện bearer confirmation/recipient/time/request ID |
| **Signature placement** | Đối tượng được tin phải thực sự được chữ ký hợp lệ bảo vệ |
| **Replay/state** | Không chấp nhận lại response/assertion ngoài chính sách |
| **SAML status** | IdP báo authentication failure thì không tạo session thành công |
| **Principal mapping** | Ánh xạ subject/attributes đã xác thực sang tài khoản và quyền nội bộ theo tenant |

Bất kỳ bước nào thất bại thì **không cấp authentication thành công**. Không làm “rút gọn validation” để cho demo chạy khi sai URL/certificate.

## 13. Những rủi ro bảo mật đặc biệt của XML và transport

1. **XXE/SSRF:** parser DTD/external entity không được khóa có thể truy cập tài nguyên nội bộ; dùng security parser settings và fail closed.
2. **XML bomb:** entity expansion, node depth, DOM allocations có thể làm cạn memory; đặt giới hạn HTTP/input/parser.
3. **DEFLATE bomb:** Redirect payload nhỏ phình thành XML lớn; giới hạn output trước khi tích trữ quá nhiều dữ liệu.
4. **XML Signature Wrapping:** kiểm đúng signed node, không nhầm assertion hợp lệ với assertion giả.
5. **Chứng thư giả:** không dùng `KeyInfo` từ XML để mở rộng danh sách IdP tin cậy.
6. **Replay:** kiểm request ID/state/time và profile; một SAMLResponse đã dùng không phải “vé đăng nhập mãi mãi”.
7. **IdP mix-up:** với nhiều registrations, issuer/certificate/ACS phải thuộc đúng IdP/tenant được chọn.
8. **URL/form double-decoding:** đừng tự decode `+`/`%xx` thêm lần nữa rồi parse dữ liệu đã bị biến đổi.
9. **Lộ dữ liệu trong log:** XML assertions có thể chứa email, NameID, groups, identifiers và chữ ký; không log raw payload/URL query.
10. **Cross-site POST cookie:** Browser POST ACS từ domain IdP có thể mất session cookie vì `SameSite`; kiểm cookie/HTTPS và request correlation thay vì bỏ `InResponseTo`.
11. **Reverse proxy:** hostname/scheme thay đổi có thể gây `Destination`/`Recipient` mismatch, dù transport decode đúng.
12. **Không tự cấp quyền:** sau authentication vẫn cần permission checks, không cấp `ROLE_ADMIN` từ mọi SAML attributes.

## 14. Kiểm thử và chẩn đoán theo từng lớp

| Triệu chứng | Lớp lỗi thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Illegal base64 character` | POST/form encoding hoặc transport | Đảm bảo form value không bị double URL decode; kiểm ký tự `+`/`/`/`=` |
| `DataFormatException` | Redirect DEFLATE | Kiểm đúng raw DEFLATE, không đưa GZIP/zlib hoặc POST XML vào Inflate |
| `Content is not allowed in prolog` | XML parse | Thường chưa decode đúng, bytes không phải XML, charset/parameter sai |
| Root XML không phải `samlp:Response` | Unmarshal/type | Dùng nhầm SAMLRequest/endpoint, namespace khác hoặc payload giả |
| `DOCTYPE is disallowed` | Parser hardening | Parser từ chối DTD đúng như chính sách; không cho phép chỉ để vượt lỗi |
| OOM / CPU cao | Inflate, XML parse | Đặt size limit, depth/entity limits, timeout và resource budgets |
| `InvalidSignature` | Cryptographic validation | Kiểm IdP signing cert đã tin, metadata và key rollover |
| Không thấy `NameID` | Unmarshal/decryption | Assertion có thể encrypted; kiểm decryption credentials |
| `DecryptionException` | EncryptedAssertion | SP private key không khớp cert IdP dùng, algorithm/rotation không phù hợp |
| `Issuer mismatch` | SAML trust | Sai registration/IdP, hoặc response từ issuer lạ |
| `Audience/Recipient mismatch` | SAML conditions | SP entity ID/ACS sai, proxy đổi URL public |
| `InResponseTo mismatch` | Session/request state | Cookie SameSite, session repo, LB, wrong transaction |
| SAML thành công nhưng 403 | Authorization | Principal thiếu role/permission; không phải lỗi Base64/parser |
| Redirect loop sau ACS | Session persistence | Kiểm SecurityContext, session cookie/domain/proxy/filter chains |

### 14.1. Quy trình debug hợp lý

1. Xem HTTP method, endpoint, content type và trường `SAMLResponse`/`SAMLRequest` có đúng binding không.
2. Kiểm transport decoding (Base64/Inflate) đúng loại binding, không áp chung một routine.
3. Xác minh XML parser nhận đúng root QName/namespace qua công cụ được kiểm soát; không log raw SAML tại production.
4. Kiểm registration, issuer, IdP cert, SP decryption key và metadata.
5. Kiểm signature, audience, destination, conditions, request correlation và clock.
6. Kiểm session/cookie và authorization **chỉ sau khi authentication thành công**.

Không bỏ signature validator hoặc `InResponseTo` để chữa lỗi tạm thời. Nếu thư viện báo lỗi bảo mật, phải tìm đúng nguyên nhân trong trust, binding và policy.

## 15. Kiểm thử thực hành

**Transport-only tests:**

- POST Base64 hợp lệ → bytes XML mẫu khớp.
- POST Base64 hỏng/khổng lồ → lỗi trước parse.
- Redirect raw DEFLATE → phục hồi đúng bytes của fixture.
- GZIP bytes đưa vào raw Inflater → bị từ chối; không tự đoán định dạng.
- XML có DOCTYPE/external entity → parser cứng hóa từ chối.
- XML có namespace sai/root giả → unmarshaller không coi đó là SAML Response phù hợp.
- Dữ liệu nén nhỏ phình vượt giới hạn → từ chối.

**Security validation tests:**

- Response từ IdP có chữ ký/certificate đáng tin + conditions đúng → authentication có thể thành công.
- Response XML tự ký → phải bị từ chối, dù decode/parse hoàn hảo.
- Response hợp lệ về chữ ký nhưng audience/recipient khác SP → bị từ chối.
- Response expired hoặc replay → bị từ chối.
- Có assertion giả/unsigned bên cạnh assertion đã ký → không lấy user từ node giả.
- EncryptedAssertion không có đúng SP private key → fail decryption, không tạo phiên.
- Đã login nhưng thiếu role → 403 authorization.

Lệnh build Spring Boot (trong dự án có Gradle Wrapper):

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew compileJava
./gradlew test
```

Trên Windows có thể dùng `.\gradlew.bat`. Các lệnh chỉ kiểm code/build/tests đã cấu hình; đăng nhập end-to-end vẫn cần IdP thật và browser. Hai ví dụ Java 17 độc lập ở mục 6–7 có `javac`/`java` và stdout xác định riêng.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao Base64 decode thành công chưa chứng minh người dùng đã đăng nhập?**

Base64 chỉ đổi biểu diễn bytes; XML có thể đến từ attacker hoặc dành cho SP khác. Phải verify chữ ký/trust và các SAML conditions rồi mới tạo Authentication.

**2. HTTP-POST và HTTP-Redirect giải mã khác nhau thế nào?**

POST thường chứa XML Base64 trong form field. Redirect thường dùng query parameter được URL-encode, Base64 và raw DEFLATE, nên phía nhận phải URL-decode, Base64-decode rồi inflate trước parse.

**3. Vì sao chữ ký của Redirect AuthnRequest có thể không có `<ds:Signature>` trong XML?**

Vì binding có thể ký trực tiếp các URL-encoded query parameters `SAMLRequest`, `RelayState` và `SigAlg`, mang chữ ký ở tham số `Signature`.

**4. Tại sao không dùng `contains("admin")` trên XML sau decode?**

Chuỗi không chứng minh danh tính, không kiểm signature, namespace, signed node, audience, thời hạn. Có thể dẫn tới authentication bypass và XML Signature Wrapping.

**5. Vai trò OpenSAML khác JAXP DOM thế nào?**

JAXP hiểu XML; OpenSAML hiểu cấu trúc/kiểu đối tượng SAML và cùng Spring Security thực hiện signature/decryption/validation theo profile. Một DOM parse không tạo trust.

**6. `EncryptedAssertion` có thể đọc bằng Base64 decoder không?**

Không. Base64 có thể khôi phục XML mang EncryptedAssertion, nhưng nội dung mã hóa cần SP private decryption key và thuật toán phù hợp, sau đó vẫn kiểm chứng SAML.

**7. `Saml2AuthenticationTokenConverter` có phải bộ quyết định user đã đăng nhập không?**

Không. Converter tạo request token từ HTTP response và registration. Provider với OpenSAML xác minh rồi mới có `Saml2Authentication` hợp lệ.

**8. Tại sao không trust certificate từ `KeyInfo` trong một SAMLResponse chưa xác minh?**

Kẻ tấn công có thể tự tạo key, ký response giả và nhúng public cert của mình. SP phải dùng certificate IdP đã đăng ký/xác thực qua kênh tin cậy.

**9. Chữ ký đúng nhưng `AudienceRestriction` là một SP khác thì xử lý sao?**

Từ chối. Chữ ký không làm assertion dành cho mọi ứng dụng; phải khớp SP entity ID và ACS/recipient theo profile.

**10. Hai ví dụ `PostTransportDemo`/`RedirectTransportDemo` có thể dùng làm SSO production không?**

Không. Chúng chỉ minh họa encoding/decoding và parsing an toàn ở mức lab. Không có signature/trust/issuer/audience/time/replay/authorization validation.

## Ghi nhớ

**SAML2 có nhiều lớp xử lý không thể bỏ qua:**

**HTTP binding → transport decoding → XML parser an toàn → OpenSAML unmarshal → trusted signature verification và decryption nếu cần → SAML conditions validation → Spring Security Authentication → application authorization.**

- **POST:** form-urlencoded + Base64 của XML; thường không Inflate.
- **Redirect:** URL-encoding + Base64 + raw DEFLATE; chữ ký có thể ở query binding, không nằm trong XML.
- **XML parse ≠ authentication:** chỉ chấp nhận principal từ assertion đúng nguồn, đúng signed target, đúng SP, đúng thời gian và request correlation.
- **Dùng Spring Security/OpenSAML** thay vì tự viết ACS parser/regex.
- **Giới hạn tài nguyên và khóa XML parser**, che dữ liệu trong log, luôn fail closed nếu bước bảo mật không đạt.

### Tài liệu tham khảo

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [OASIS – SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html)
- [OWASP – XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)
