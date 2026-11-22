# XXE, XML mở rộng thực thể và sử dụng bộ phân tích an toàn

**Module:** Spring Security – federation  
**Chủ đề cha:** Gia cố an toàn  
**Công nghệ:** SAML 2.0, Spring Security 6.x, OpenSAML, Spring Boot 3.x, Java 17+, JAXP.

## 1. Vì sao XML là một điểm tấn công của federation?

Trong SAML 2.0, ứng dụng Service Provider (SP) nhận **SAMLResponse** qua browser, kiểm tra **Assertion**, chữ ký và trust của Identity Provider (IdP). SP còn đọc **IdP metadata** để tìm EntityID, KeyDescriptor, signing certificates và endpoints. Nhiều ứng dụng Spring cũng parse XML từ SOAP/IAM connector, file import, XML Schema và XSLT.

Một XML parser có thể hỗ trợ **Document Type Definition (DTD)**, internal/external entities hoặc tự mở external URLs. Nếu dữ liệu XML do attacker/đối tác gửi được parse mà không hạn chế, rủi ro gồm:

- **XXE (XML External Entity)**: đọc file local hoặc URL nội bộ mà client không trực tiếp truy cập được.
- **SSRF**: XML khiến ứng dụng backend gửi HTTP request đến endpoint private, loopback, cloud metadata hoặc service khác.
- **Entity expansion denial of service**: entity tự lặp/nested khiến text sau mở rộng lớn hơn input rất nhiều; tốn CPU và RAM.
- **External XSD/XSLT/XInclude**: tải tài nguyên bên ngoài dù không khai báo external entity theo kiểu DTD.
- **Metadata URL SSRF**: ứng dụng chủ động tải metadata từ URL không tin cậy trước khi parse; đây là đường SSRF **khác** XML entity.
- **Parser differential và XML Signature Wrapping (XSW)**: parser và logic signature/element selection có thể hiểu XML khác nhau; bảo mật SAML không chỉ là chống XXE.

**Nguyên tắc bắt buộc:** Chặn nguy cơ XML ở **bước parse đầu tiên**, trước khi lấy user/attributes và trước cả lúc kiểm tra chữ ký SAML. Chữ ký tốt không tự làm một parser dễ bị XXE trở nên an toàn, vì parser phải xử lý XML để có đối tượng cho signature validator.

~~~text
Browser / IdP / Partner / Metadata feed
                |
                v
HTTP body / Base64 decode / inflate (strict byte limits)
                |
                v
SECURE XML PARSER (reject DTD, external resources, XInclude)
                |
                v
SAML Protocol/Signature Validation
  Issuer, signing key, Audience, Destination, Recipient,
  InResponseTo, Conditions, SubjectConfirmation, replay
                |
                v
Approved local user mapping + tenant/resource authorization
~~~

Một XML được parser chấp nhận **không phải** một SAMLResponse đã authenticated. Một Assertion có chữ ký hợp lệ **không tự có mọi quyền nghiệp vụ**. Hai ranh giới này phải được test riêng.

## 2. DTD, internal entity và external entity

### Internal entity

XML hỗ trợ định nghĩa tên thay thế trong DTD:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Hello [
  <!ENTITY team "Security Team">
]>
<Hello>Hi, &team;!</Hello>
~~~

Nếu DTD được phép, parser có thể mở rộng &team; thành text. SAMLResponse và SAML metadata thông thường **không cần DTD**, nên lựa chọn an toàn nhất là **từ chối mọi DOCTYPE**, không cố phân biệt DTD có vẻ vô hại.

### External general entity

~~~xml
<!DOCTYPE Document [
  <!ENTITY outside SYSTEM "file:///nonexistent/xxe-demo.txt">
]>
<Document>&outside;</Document>
~~~

Đây là ví dụ kiểm thử chỉ dùng **file không tồn tại**, không đọc tài liệu thật. Nếu parser giải external entity, nó có thể truy cập file:// hoặc network protocol. Dữ liệu bị mở có thể vô tình chui vào response, audit, logs, exceptions hoặc downstream services.

### External DTD

~~~xml
<!DOCTYPE Document SYSTEM
  "https://example.invalid/untrusted.dtd">
<Document>Example</Document>
~~~

Một parser bật external DTD loading có thể phát network request **chỉ vì gặp DOCTYPE SYSTEM**, dù body không tham chiếu entity cụ thể.

### Parameter entities

DTD có cả **parameter entities**; chúng có thể tạo đường dẫn resolution ngoài external general entity. Vì vậy một cấu hình chỉ tắt external-general-entities mà quên external-parameter-entities và nonvalidating/load-external-dtd là chưa đủ.

### Entity expansion

~~~xml
<!DOCTYPE a [
  <!ENTITY x "ha">
  <!ENTITY y "&x;&x;&x;&x;">
  <!ENTITY z "&y;&y;&y;&y;">
]>
<a>&z;</a>
~~~

Đây là mẫu nhỏ giải thích hiện tượng, **không phải payload tấn công lớn**. Khi các entities lồng nhau nhiều cấp, text sau expansion có thể lớn vượt xa kích thước XML gốc; **không cần truy cập file hay HTTP** để gây DoS.

## 3. Rủi ro theo từng API XML

| API/cơ chế | Điểm cần bảo vệ | Biện pháp |
| --- | --- | --- |
| **DocumentBuilderFactory (DOM)** | DTD, external entities, XInclude, tree RAM | disallow-doctype-decl; FSP; external-access properties; XInclude false; byte/depth limits |
| **SAXParserFactory/XMLReader** | DTD + external references | disallow DOCTYPE; disable general/parameter entities + external DTD; resolver throw |
| **XMLInputFactory (StAX)** | DTD, external entities, token streaming | SUPPORT_DTD=false; IS_SUPPORTING_EXTERNAL_ENTITIES=false; XMLResolver throw; DTD event policy |
| **SchemaFactory/Validator** | schemaLocation/import/include | ACCESS_EXTERNAL_SCHEMA="", ACCESS_EXTERNAL_DTD="", trusted XSD |
| **TransformerFactory/XSLT** | xsl:import/include, document() | ACCESS_EXTERNAL_STYLESHEET="", ACCESS_EXTERNAL_DTD="", trusted stylesheet |
| **XPath** | implicit parser khi nhận InputSource | Parse bằng hardened DOM trước; evaluate trên Document |
| **JAXB/Unmarshaller** | parser được tạo bên trong | cung cấp hardened StAX/SAX reader; kiểm DTD rejection |
| **OpenSAML ParserPool** | SAMLResponse, metadata, XMLDSig DOM | Secure XML Processing Requirements theo version |
| **Metadata HTTP fetch** | URL/redirect/private IP | URL allowlist, egress, DNS/IP/redirect/timeouts trước XML parse |
| **XInclude** | xi:include href tới file/URL | setXIncludeAware(false); kiểm tra policy |
| **XMLDSig** | signed vs unsigned node selection | ID uniqueness, signature/trust validation đúng node |

**Không thể chỉ bật một switch trên Spring SecurityFilterChain rồi coi mọi XML parsing an toàn.** Mỗi library và entry point có parser riêng; cần kiểm kê cả controller tùy biến, file import, metadata resolver và schema/XSLT processors.

## 4. Chính sách parser: reject DTD và fail closed

Đối với XML của federation, ưu tiên:

1. **Từ chối DOCTYPE declaration** ngay tại parser.
2. **FEATURE_SECURE_PROCESSING=true** trên factories có hỗ trợ.
3. **Chặn external general entities, external parameter entities và load-external-dtd**.
4. **ACCESS_EXTERNAL_DTD=""**, **ACCESS_EXTERNAL_SCHEMA=""**, **ACCESS_EXTERNAL_STYLESHEET=""** tại đúng factory/API.
5. **XInclude=false**.
6. Gắn **EntityResolver/XMLResolver** từ chối external references, không cho fallback sang default.
7. Khi parser không hỗ trợ một required setting, **fail closed**: không xử lý XML untrusted bằng factory “hạ cấp”.
8. Chỉ parse **InputStream do app sở hữu**, có giới hạn bytes và timeout; không truyền user-controlled URI vào parse(String).
9. Cài **resource limits** về số entity, depth, attributes, size sau Base64/inflate và mức concurrency.
10. Chỉ dùng schema/XSLT/catalog **đáng tin** do app quản lý nếu thật sự cần.

| Sai lầm | Vì sao không an toàn? |
| --- | --- |
| Chỉ gọi setExpandEntityReferences(false) | Có thể vẫn còn external resolution/DTD; flag không là giải pháp toàn diện |
| setValidating(false) | Không tự tắt DTD/external entity loading |
| Chỉ bật FEATURE_SECURE_PROCESSING | Behavior/default phụ thuộc provider/JDK; đặt external-access restrictions rõ |
| Chỉ set ACCESS_EXTERNAL_DTD="" | Chưa chặn XInclude, XSLT, external schema và XML bombs không dùng DTD |
| Regex bỏ từ khóa DOCTYPE | Không phải XML parser chuẩn; dễ parser differential/encoding bypass |
| Chặn HTTP egress nhưng không chặn DTD | file:// hoặc internal entity expansion còn rủi ro |
| Tin XML vì “đã có HTTPS” | TLS bảo vệ đường truyền, không bảo đảm nội dung XML an toàn |
| Tin XML vì “có chữ ký” | Parser có thể bị tấn công trước signature verification |
| Dùng XML schema validation mặc định | XSD có thể tải import/include từ URL ngoài |
| Chấp nhận exceptions khi setFeature rồi chạy tiếp | Insecure fallback với untrusted input |

## 5. DOM an toàn với DocumentBuilderFactory trong Java 17

JDK 17 có **DocumentBuilderFactory.newDefaultNSInstance()**, chọn JDK built-in namespace-aware DOM factory. Các features dưới đây chủ đích cho JDK built-in parser (Xerces derivative):

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.SAXException;

DocumentBuilderFactory factory =
    DocumentBuilderFactory.newDefaultNSInstance();

factory.setNamespaceAware(true);
factory.setXIncludeAware(false);
factory.setExpandEntityReferences(false);
factory.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);
factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setFeature(
    "http://xml.org/sax/features/external-general-entities",
    false);
factory.setFeature(
    "http://xml.org/sax/features/external-parameter-entities",
    false);
factory.setFeature(
    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
    false);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

DocumentBuilder builder = factory.newDocumentBuilder();
builder.setEntityResolver((publicId, systemId) -> {
    throw new SAXException("External reference forbidden");
});

// inputStream phải được app mở/giới hạn/đóng.
org.w3c.dom.Document document = builder.parse(inputStream);
~~~

**Đây là fragment**, inputStream chưa được khai báo. Trong code thật, mở stream bằng try-with-resources, áp size/timeout bounds trước khi parse và sanitize lỗi XML.

**Feature URI disallow-doctype-decl** là Xerces-specific; JDK built-in parser hiểu nó. Một provider do container/app server inject có thể xử lý khác. Nếu không hỗ trợ, thay provider hoặc cung cấp equivalent hardened policy đã kiểm chứng; không catch ParserConfigurationException để bỏ qua.

### Vì sao EntityResolver không nên trả null?

~~~java
builder.setEntityResolver((publicId, systemId) -> null);
~~~

**Null thường có nghĩa để parser resolve theo cơ chế mặc định**, không phải deny. Với untrusted XML không cần DTD, resolver tốt nên **throw SAXException**. Resolver chỉ là lớp bổ sung; **disallow DOCTYPE** vẫn là tuyến phòng vệ chính.

### parse(String URI) là một đường SSRF riêng

~~~java
// Rủi ro nếu userProvidedUri không đáng tin:
builder.parse(userProvidedUri);
~~~

External-access restrictions cho DTD không có nghĩa ứng dụng bị ngăn mở **initial XML source URI**. Nếu nguồn là HTTP/metadata, ứng dụng tự áp URL allowlist, DNS/IP/redirect controls và egress policy rồi chuyển InputStream đã giới hạn cho parser.

## 6. Bài thực hành Java 17 chạy độc lập

Chương trình dưới đây **biên dịch bằng JDK 17 thuần**, không cần Spring/IdP/network/file secret. Nó chứng minh **DOCTYPE bị chặn kể cả khi chứa internal entity, external file, external HTTP hoặc không có entity**.

**Tệp: XmlParserHardeningDemo.java**

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public final class XmlParserHardeningDemo {

    static DocumentBuilder safeBuilder() throws Exception {
        DocumentBuilderFactory f =
            DocumentBuilderFactory.newDefaultNSInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        f.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        f.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder b = f.newDocumentBuilder();
        b.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("No external resolution");
        });
        b.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException e)
                    throws SAXException {
                throw e;
            }

            @Override
            public void fatalError(SAXParseException e)
                    throws SAXException {
                throw e;
            }
        });
        return b;
    }

    static String check(String xml) {
        try {
            safeBuilder().parse(
                new InputSource(new StringReader(xml)));
            return "ACCEPTED";
        } catch (Exception ex) {
            // Demo fail closed; production phân biệt
            // invalid XML (4xx) với lỗi parser config (5xx).
            return "BLOCKED";
        }
    }

    public static void main(String[] args) throws Exception {
        String valid =
            "<Response><Name>Alice</Name></Response>";
        Document doc = safeBuilder().parse(
            new InputSource(new StringReader(valid)));

        System.out.println("validRoot=" +
            doc.getDocumentElement().getTagName());
        System.out.println("validName=" +
            doc.getElementsByTagName("Name").item(0)
                .getTextContent());

        String internal =
            "<!DOCTYPE Response [<!ENTITY e 'TEXT'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String externalFile =
            "<!DOCTYPE Response [<!ENTITY e SYSTEM " +
            "'file:///nonexistent/xxe-demo.txt'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String externalHttp =
            "<!DOCTYPE Response [<!ENTITY e SYSTEM " +
            "'https://example.invalid/blocked'>]>" +
            "<Response><Name>&e;</Name></Response>";

        String emptyDoctype =
            "<!DOCTYPE Response>" +
            "<Response><Name>Alice</Name></Response>";

        System.out.println(
            "internalEntity=" + check(internal));
        System.out.println(
            "externalFile=" + check(externalFile));
        System.out.println(
            "externalHttp=" + check(externalHttp));
        System.out.println(
            "emptyDoctype=" + check(emptyDoctype));
    }
}
~~~

Chạy:

~~~bash
javac XmlParserHardeningDemo.java
java XmlParserHardeningDemo
~~~

**Stdout dự kiến chính xác với JDK 17 built-in parser:**

~~~text
validRoot=Response
validName=Alice
internalEntity=BLOCKED
externalFile=BLOCKED
externalHttp=BLOCKED
emptyDoctype=BLOCKED
~~~

**Lưu ý:**

- File/HTTP URLs trong bài chỉ là dummy, không được truy cập nếu parser chặn DOCTYPE.
- Demo chỉ kiểm tra **XML parser hardening**, không có SAML XML Signature.
- Class dùng JDK default parser; provider/version khác cần kiểm thử tương ứng.
- check() gom lỗi để minh họa fail-closed; trong production phải ghi metric/lỗi config riêng và không hiển thị raw input/secrets.
- Chương trình không mô phỏng large XML/CPU DoS; cần separate load/limits tests.
- Nếu muốn kiểm tra không có outbound I/O thực, dùng một mock HTTP server của integration test và assert **zero requests**.

## 7. SAX Parser: dùng XMLReader đã hardened

SAX xử lý XML qua events, dùng ít RAM hơn DOM trong nhiều trường hợp nhưng **không tự ngăn XXE**:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;
import org.xml.sax.SAXException;
import org.xml.sax.helpers.DefaultHandler;

SAXParserFactory f =
    SAXParserFactory.newDefaultInstance();
f.setNamespaceAware(true);
f.setFeature(
    "http://apache.org/xml/features/disallow-doctype-decl",
    true);
f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
f.setFeature(
    "http://xml.org/sax/features/external-general-entities",
    false);
f.setFeature(
    "http://xml.org/sax/features/external-parameter-entities",
    false);
f.setFeature(
    "http://apache.org/xml/features/nonvalidating/load-external-dtd",
    false);

XMLReader reader = f.newSAXParser().getXMLReader();
reader.setEntityResolver((publicId, systemId) -> {
    throw new SAXException("No external entities");
});
reader.setContentHandler(new DefaultHandler());
reader.parse(new InputSource(inputStream));
~~~

Đây là fragment. **reader.parse** bảo đảm sử dụng resolver đã cấu hình; một số wrapper SAXParser.parse(source, DefaultHandler) có thể gán lại resolver/handler. Xác minh provider và đặt ACCESS_EXTERNAL_DTD property bằng API hợp lệ nếu cần; đừng coi DOM setAttribute là API của SAXParserFactory.

Không gom toàn bộ SAX characters() vào một String không giới hạn rồi làm mất lợi ích streaming. Giới hạn tổng bytes, depth, text size và number of events.

## 8. StAX: tắt DTD/external entities, kiểm tra DTD event

StAX không dùng FEATURE_SECURE_PROCESSING như DOM/SAX. Cấu hình:

~~~java
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

XMLInputFactory f =
    XMLInputFactory.newDefaultFactory();
f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
f.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External resource forbidden");
});

XMLStreamReader reader =
    f.createXMLStreamReader(inputStream);

try {
    while (reader.hasNext()) {
        int event = reader.next();
        if (event == XMLStreamConstants.DTD) {
            throw new XMLStreamException("DOCTYPE not allowed");
        }
        // Business events: hạn chế depth/text/count.
    }
} finally {
    reader.close();
}
~~~

**SUPPORT_DTD=false không có nghĩa mọi provider luôn throw khi thấy DOCTYPE.** Nó có thể bỏ qua xử lý DTD nhưng vẫn phát sự kiện DTD. Nếu policy yêu cầu reject syntax, explicit DTD check là cần thiết. Đóng inputStream ngoài finally/try-with-resources riêng; reader.close không mặc định đóng stream.

## 9. XSD SchemaFactory và Validator

XSD cũng có external imports/includes/schemaLocation. Với **schema do app quản lý**, cấm external references:

~~~java
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import javax.xml.transform.stream.StreamSource;

SchemaFactory sf =
    SchemaFactory.newDefaultInstance();
sf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
sf.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema = sf.newSchema(
    new StreamSource(trustedSchemaStream));
Validator validator = schema.newValidator();
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

validator.validate(new StreamSource(untrustedXmlStream));
~~~

Đây là fragment; streams được app mở/đóng và hạn chế bytes. Nếu dùng LSResourceResolver, chú ý **Validator không mặc nhiên kế thừa factory resolver**; thiết lập và test trên mỗi validator theo API. Trả null từ resolver thường có nghĩa default resolution. Khi XML chưa tin được đưa bằng StreamSource, bộ xử lý có thể tự tạo parser; cân nhắc dùng hardened DOMSource/SAXSource đã kiểm soát parse.

**Không để input XML chỉ định XSD trên một URL public rồi tự động tải.** Quản lý trusted XSD version/catalog, validate protocol/namespace, chặn xsd:import tới resources ngoài allowlist.

## 10. XSLT TransformerFactory

XSLT có thể đọc resources bằng xsl:import, xsl:include hoặc **document()**, tách biệt XXE qua DTD. Chỉ biên dịch **trusted stylesheet**:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamSource;

TransformerFactory tf =
    TransformerFactory.newDefaultInstance();
tf.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING, true);
tf.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
tf.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");

Transformer transformer = tf.newTransformer(
    new StreamSource(trustedStylesheetStream));
transformer.transform(hardenedDomOrSaxSource, outputResult);
~~~

Fragment yêu cầu inputs/output được tạo ở app. Restrictions không biến **untrusted XSLT** thành sandbox an toàn; expressions phức tạp vẫn có thể gây DoS. Với identity transform, tránh pass untrusted StreamSource khi chưa áp parser safety phù hợp.

## 11. JAXB và XPath

**JAXB:** Trong Java 17, JAXB không còn được bundle trong JDK. Spring Boot 3 thường dùng jakarta.xml.bind với dependencies riêng. Đừng mặc định unmarshaller.unmarshal(InputStream) dùng hardened parser.

~~~java
XMLInputFactory f = XMLInputFactory.newDefaultFactory();
f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
f.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
f.setXMLResolver((p, s, b, n) -> {
    throw new XMLStreamException("External URL forbidden");
});
XMLStreamReader r = f.createXMLStreamReader(untrustedStream);
try {
    Object value = unmarshaller.unmarshal(r);
} finally {
    r.close();
}
~~~

Đây là fragment với unmarshaller khai báo ngoài. Nếu contract cấm DOCTYPE, cần reader/DTD-event policy đủ mạnh **trước hoặc trong lúc JAXB consume**; chỉ SUPPORT_DTD=false chưa chứng minh DOCTYPE syntax bị từ chối.

**XPath:** Tránh evaluate(expression, InputSource) với XML không tin, vì XPath API có thể parse nguồn ngầm. Parse trước thành Document an toàn, sau đó evaluate:

~~~java
org.w3c.dom.Document doc =
    secureBuilder.parse(inputStream);
javax.xml.xpath.XPath xpath =
    javax.xml.xpath.XPathFactory
        .newDefaultInstance().newXPath();
String name = xpath.evaluate("/root/name", doc);
~~~

Trong SAML/XMLDSig, không chọn Assertion chỉ theo local-name() hoặc first element; phải chọn đúng signed element, namespace và ID đã được kiểm chứng. XPath Injection cũng là vấn đề riêng nếu expression nhận từ user.

## 12. Spring Security SAML2, Saml2WebSsoAuthenticationFilter và OpenSAML

Trong Spring Security 6.x, module **spring-security-saml2-service-provider** triển khai SAML 2.0 dựa trên **OpenSAML**. **Saml2WebSsoAuthenticationFilter** nhận callback SSO; các thành phần authentication provider dùng OpenSAML để parse và validate Response/Assertion rồi tạo Saml2Authentication theo trusted **RelyingPartyRegistration**.

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **snippet** yêu cầu imports và repository cấu hình. Mục đích là dùng **framework authentication pipeline**, không tự parse SAMLResponse bằng DOM trong controller rồi lấy NameID từ XML chưa kiểm chứng.

### OpenSAML ParserPool

OpenSAML có cơ chế parser pool và **Secure XML Processing Requirements**. Nếu tự xây hoặc thay **BasicParserPool**, bảo đảm phù hợp version:

- expandEntityReferences=false;
- FEATURE_SECURE_PROCESSING=true;
- disallow-doctype-decl=true;
- XInclude không được phép truy xuất ngoài;
- coalescing và ignoreComments phải phù hợp với OpenSAML DOM/signature expectations;
- không bật external entity processing để “sửa lỗi XML signature”.

**Spring Security 6.5** có khả năng chọn các thành phần OpenSAML 4/5 theo dependency version. OpenSAML 4 và 5 có khác package/API; không copy cấu hình parser từ **Spring Security SAML Extension/OpenSAML 2** sang phiên bản mới như thể giống hệt nhau.

Đọc docs của **đúng version** rồi tích hợp kiểm thử: XXE external resolution phải bị chặn, nhưng XMLDSig canonicalization/signature validation vẫn đúng.

### XXE khác XML Signature Wrapping (XSW)

~~~text
SAML Response
    +-- Assertion A: signed, subject=alice
    +-- Assertion B: unsigned, subject=administrator
~~~

Nếu signature validator xác minh **A** nhưng code chọn **B** để lập principal, đây là **XML Signature Wrapping/ID-selection error**, không phải XXE. Cần kiểm tra signed reference đúng element, XML IDs duy nhất, signature trust, issuer/audience/conditions, và **dùng chính validated object**; đừng parse lại rồi lấy Assertion bất kỳ.

**Hai lớp độc lập:** Parser chặn DTD không xác minh SAML signature. Một SAML signature hợp lệ cũng không tự vô hiệu hóa external entity resolution nếu parser đã chạy trước verify.

## 13. Metadata fetch và trust của IdP

IdP metadata có thể được tải qua URL do admin cấu hình. Nếu một UI cho nhập URL tùy ý, server có thể gửi request đến loopback/private IP hoặc bị redirect đến endpoint nội bộ **trước khi XML parser được gọi**. Đây là metadata URL SSRF.

Chính sách tối thiểu:

1. Metadata source chỉ được tạo bởi trusted admin/partner onboarding.
2. HTTPS URL allowlist; TLS certificate/hostname verification; giới hạn redirect.
3. DNS/IP checks và egress deny cho loopback, link-local, private zones ngoài policy; chống DNS rebinding theo threat model.
4. HTTP timeouts, Content-Length/body/decompressed size limits và concurrency quota.
5. XML parser hardened khi nhận InputStream.
6. Kiểm tra IdP EntityID, KeyDescriptor, signing certificates, endpoints/roles đúng contract.
7. Metadata signature/trusted signing certificate hoặc transport provenance đúng chính sách; không tự tin một key mới chỉ vì metadata hiện tại phát nó.
8. validUntil/cacheDuration/refresh/last-known-good trong thời hạn trust hợp lệ, audit thay đổi IdP key/issuer.
9. Không log raw metadata/signing data/PII nhạy cảm.
10. Không cho user đăng nhập tự chỉ định arbitrary IdP metadata endpoint.

**ACCESS_EXTERNAL_DTD="" không bảo vệ bước tải initial metadata URL** vì đây là request do app HTTP client chủ động tạo.

## 14. Resource limits cho XML dù không dùng DTD

Một XML không có DOCTYPE vẫn có thể gồm cực nhiều nodes, depth lớn, attributes, Base64 text hoặc XSD/XPath/XSLT cực tốn CPU. Java JAXP có **JDK-specific processing limits**:

| Property | Loại giới hạn |
| --- | --- |
| **jdk.xml.entityExpansionLimit** | Số entity expansions |
| **jdk.xml.totalEntitySizeLimit** | Tổng entity size |
| **jdk.xml.maxGeneralEntitySizeLimit** | Kích thước general entity |
| **jdk.xml.maxParameterEntitySizeLimit** | Kích thước parameter entity |
| **jdk.xml.elementAttributeLimit** | Số attributes |
| **jdk.xml.maxElementDepth** | Độ sâu XML |
| **jdk.xml.maxOccurLimit** | Số lần lặp trong schema |
| **jdk.xml.xpathExprGrpLimit** | Số expression groups |
| **jdk.xml.xpathTotalOpLimit** | Tổng XPath operations |

Một ví dụ riêng cho JDK built-in DOM:

~~~java
factory.setAttribute("jdk.xml.entityExpansionLimit", "1000");
factory.setAttribute("jdk.xml.totalEntitySizeLimit", "100000");
factory.setAttribute("jdk.xml.maxElementDepth", "100");
~~~

**Các số chỉ để minh họa**, cần calibrate với payload hợp lệ. Đây là implementation properties, không portable cho mọi parser; nếu unsupported, không âm thầm bỏ qua. Nếu protocol cấm DTD, reject DOCTYPE vẫn là biện pháp nền tảng.

**Kiểm soát nhiều tầng:**

- Request size limit ở reverse proxy/Servlet container (kể cả chunked).
- Base64-decoded SAMLResponse limit, decompression/inflation limit.
- Streaming body bounds trước khi load toàn bộ byte[].
- Parser depth/attribute/text/entity limits, CPU timeout/concurrency.
- Metadata maximum descriptors/certificate count; XML validation/XPath/XSLT complexity.
- Audit parser errors và outbound attempts đã làm sạch, không lưu raw SAML Assertion/NameID/token.

Chặn external URL không ngăn CPU DoS; chặn DTD cũng không ngăn document quá lớn. **Không đợi OutOfMemoryError rồi catch để khắc phục**.

## 15. Spring Boot 3 XML data endpoint: không phá SAML filter

Nếu SP có một XML import API riêng bên cạnh SAML callback, controller phải dùng parser đã harden. Đừng parse SAMLResponse bằng controller custom rồi coi đó là login.

**src/main/java/com/example/xml/SafeXmlParser.java**

~~~java
package com.example.xml;

import java.io.ByteArrayInputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;

public final class SafeXmlParser {

    private static final int MAX_BYTES = 262_144;

    public Document parse(byte[] body) throws Exception {
        if (body == null || body.length == 0
                || body.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "XML body size forbidden");
        }

        DocumentBuilderFactory f =
            DocumentBuilderFactory.newDefaultNSInstance();
        f.setNamespaceAware(true);
        f.setXIncludeAware(false);
        f.setExpandEntityReferences(false);
        f.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        f.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        f.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        f.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        DocumentBuilder builder = f.newDocumentBuilder();
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("No external XML references");
        });
        return builder.parse(new ByteArrayInputStream(body));
    }
}
~~~

**src/main/java/com/example/xml/XmlInspectController.java**

~~~java
package com.example.xml;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/xml")
public class XmlInspectController {

    private final SafeXmlParser parser = new SafeXmlParser();

    @PostMapping(
        path = "/inspect",
        consumes = MediaType.APPLICATION_XML_VALUE)
    public Map<String, String> inspect(@RequestBody byte[] body)
            throws Exception {
        var doc = parser.parse(body);
        return Map.of(
            "root", doc.getDocumentElement().getTagName());
    }
}
~~~

**Không phải ứng dụng hoàn chỉnh**: project còn cần Boot main class, dependencies và một **SecurityFilterChain** xác thực/kiểm quyền cho /api/xml/inspect. Giới hạn 262,144 bytes được kiểm tra **sau** khi HTTP body đã thành byte[], nên còn cần **reverse proxy/container request-size limits trước khi body vào RAM**. Lỗi XML invalid trả 400 đã sanitize, lỗi parser config trả 5xx an toàn; không trả raw XML. Đối với SAML metadata lớn phải có limit khác theo policy.

## 16. Bộ kiểm thử âm cho federation XXE

Dùng local/staging đã được phép kiểm thử, mock HTTP server và đường dẫn file giả. Không thử exfiltrate file thật hoặc scan private network production.

| # | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| 1 | XML đơn giản không DOCTYPE | Parse được, nhưng chưa là SAML authenticated |
| 2 | Internal DTD/entity | Reject DOCTYPE |
| 3 | External general entity file:///nonexistent/... | Reject; không đọc file |
| 4 | External HTTP entity tới mock URL | Reject; mock request count = 0 |
| 5 | External parameter entity | Reject trước resolution |
| 6 | External DTD SYSTEM URL | Không có outbound request |
| 7 | DOCTYPE rỗng | Reject do chính sách cấm DTD |
| 8 | Nested entity expansion (“Billion Laughs” mẫu nhỏ) | Reject trước expansion |
| 9 | XInclude href=file:///... | Không mở file |
| 10 | schemaLocation tới remote URL | Không fetch XSD |
| 11 | xsd:import/include external | ACCESS_EXTERNAL_SCHEMA chặn |
| 12 | xsl:import/include external | ACCESS_EXTERNAL_STYLESHEET chặn |
| 13 | XSLT document() external | Không load external document |
| 14 | StAX SUPPORT_DTD=false nhưng gặp DOCTYPE | DTD event bị phát hiện/reject theo contract |
| 15 | SAX resolver null fallback | Test phát hiện nguy cơ resolution |
| 16 | Parser provider không support security feature | Fail closed, không fallback defaults |
| 17 | App parse(userControlledURI) | Reject initial URL không tin cậy |
| 18 | Metadata URL localhost/private IP | HTTP client policy chặn trước parse |
| 19 | Metadata redirect sang private IP | Chặn theo mỗi hop/egress policy |
| 20 | XML lớn sau Base64 decode | Reject decoded body limit |
| 21 | Compressed payload phình quá mức | Reject inflate limit |
| 22 | XML sâu hàng nghìn levels | Depth/resource limit reject |
| 23 | Element có quá nhiều attributes | Attribute limit reject |
| 24 | Invalid encoding/malformed XML | Không parse; lỗi 4xx an toàn |
| 25 | Namespace giả giống SAML tag | Không qua SAML trust validation |
| 26 | Duplicate XML ID/signature wrapping | Reject hoặc dùng đúng signed element |
| 27 | XML được parser accept nhưng SAML chưa ký | Authentication fail |
| 28 | SAML signed nhưng Audience/Issuer sai | Authentication fail |
| 29 | IdP metadata đã hết hạn | Không tự tin metadata expired |
| 30 | IdP metadata signing key đổi trái policy | Trust check fail |
| 31 | XML import endpoint chưa authenticated | SecurityFilterChain deny trước parsing |
| 32 | JAXB khác XMLInputFactory policy | Test đúng provider/Unmarshaller |
| 33 | Parser logs raw SAMLResponse/NameID | Redact |
| 34 | Multi-request XML DoS | Quota/timeout giữ hệ thống ổn định |
| 35 | Third-party JAXP parser override | Features vẫn enforced hoặc fail closed |

### Test bằng mock server

1. Tạo mock HTTP server nội bộ test và request counter.
2. Gửi XML có external reference trỏ tới mock endpoint vào **đúng ứng dụng/route đang parse**.
3. Assert parser reject và mock server **nhận 0 requests**.
4. Assert lỗi không chứa raw XML, file path nhạy cảm hoặc credentials.
5. Lặp lại với DOM, SAX, StAX, XSD, XSLT/JAXB và OpenSAML metadata paths mà ứng dụng thực sự dùng.
6. Với identity flow, test thêm issuer/signature/audience/conditions và signed-element selection.
7. Khi thay JDK, parser provider hoặc OpenSAML, chạy lại regression suite.

**Không mock một Authentication luôn-success rồi kết luận đã test SAML security**. Test parser XXE và test signature/trust là hai bài kiểm thử độc lập.

## 17. Troubleshooting nhanh

| Dấu hiệu | Nguyên nhân có thể | Xử lý |
| --- | --- | --- |
| DOCTYPE bị parser reject | Chính sách XML an toàn hoạt động | Không bật DTD chỉ để parse được |
| ParserConfigurationException | Provider không hỗ trợ feature | Fail closed; đổi parser/provider |
| XML vẫn tải external DTD | Chưa disallow-doctype/load-external-dtd/resolver | Kiểm tra factory/reader, throw resolver |
| XInclude vẫn mở file | setXIncludeAware chưa tắt | Tắt và kiểm thử |
| StAX không throw DOCTYPE | SUPPORT_DTD=false chỉ tắt processing | Reject DTD event theo contract |
| XSD validator tự tải URL | ACCESS_EXTERNAL_SCHEMA chưa set | Trusted schema/catalog |
| XSLT gọi document() URL | ACCESS_EXTERNAL_STYLESHEET chưa set | Trusted stylesheet + deny |
| XPath code bỏ qua DOM parser an toàn | evaluate(InputSource) parse ngầm | Evaluate trên hardened Document |
| DOM chặn XXE nhưng metadata vẫn SSRF | Initial HTTP URL untrusted | Safe fetch/egress allowlist |
| App OOM với XML không DTD | Thiếu input/depth/concurrency limits | Hard resource quotas |
| OpenSAML signature fail sau custom ParserPool | Coalescing/comments/canonicalization đổi | Theo Secure XML Processing Requirements |
| SAML ký Assertion A nhưng app dùng B | XML Signature Wrapping | Validate ID/ref, use signed object |
| XML parse thành công nhưng authentication fail | Issuer/audience/signature/trust sai | Debug SAML policy, không bỏ parser hardening |
| Log chứa XML và secrets | Error handler/APM body logging | Redact và không phản chiếu input |

Thứ tự xử lý: xác định nguồn XML → limit bytes → xác định parser thật → DTD/external settings → XInclude/XSD/XSLT → initial metadata fetch → test outbound zero → SAML trust → local authorization. Không chữa lỗi bằng cách tắt FEATURE_SECURE_PROCESSING hoặc cho phép arbitrary file/HTTP resolution.

## 18. Checklist production

- [ ] Kiểm kê mọi XML entry point: SAMLResponse, metadata, XML import, SOAP, XSD/XSLT/JAXB.
- [ ] **Reject DOCTYPE** với XML federation không yêu cầu DTD.
- [ ] DOM/SAX: FSP=true; general/parameter entities false; external DTD false; external access denied.
- [ ] StAX: SUPPORT_DTD=false; external entities false; XMLResolver deny; reject DTD event khi contract cấm DOCTYPE.
- [ ] XInclude disabled; không có file/HTTP resolution từ untrusted input.
- [ ] SchemaFactory/Validator deny external DTD/SCHEMA và dùng trusted XSD.
- [ ] TransformerFactory deny external DTD/STYLESHEET; không chạy XSLT chưa tin.
- [ ] JAXB nhận hardened reader, XPath chỉ evaluate trên hardened DOM.
- [ ] Parser không support required setting → **fail closed**, không fallback.
- [ ] Không dùng parse(String URI) với user input; metadata fetch cần URL/DNS/redirect/egress policy.
- [ ] Giới hạn HTTP body, Base64/DEFLATE decoded bytes, depth, attributes, CPU/time/concurrency.
- [ ] Mock HTTP test xác nhận XXE payload không phát request mạng.
- [ ] OpenSAML ParserPool theo đúng version và Secure XML Processing Requirements.
- [ ] XMLDSig xác minh đúng signed element/ID, reject signature wrapping/duplicate IDs.
- [ ] SAML trust: Issuer, trusted certificate, Audience, Destination/Recipient, Conditions, InResponseTo, replay.
- [ ] Metadata EntityID, signing key, validUntil/cacheDuration và refresh policy được kiểm chứng.
- [ ] XML API endpoints đều được xác thực/phân quyền, không phản chiếu XML raw.
- [ ] Errors/logs/APM không lộ SAML Assertion, NameID, private keys hoặc file contents.
- [ ] JDK/OpenSAML/Spring Security/XML providers được patch; regression tests chạy sau nâng cấp.
- [ ] Local account/tenant/resource authorization vẫn áp dụng sau khi SAML được xác thực.

**Kết luận:** Trong SAML federation, **XML parsing là bề mặt tấn công trước khi có bằng chứng xác thực**. Với XML không cần DTD, hãy **reject DOCTYPE**, chặn external resources qua mọi parser/validator/transformer, giới hạn tài nguyên và **fail closed** nếu một setting không hoạt động. Sau đó mới xác thực XMLDSig/SAML protocol và áp quyền ứng dụng; không lấy kết quả parser sạch làm bằng chứng người dùng hợp lệ.

## 19. Tài liệu tham khảo

- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): DOM, SAX, StAX, XSD, XSLT, XPath, JAXB và fail-closed.
- [Oracle JDK 17 JAXP Security Guide](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html): FEATURE_SECURE_PROCESSING, ACCESS_EXTERNAL_*, JDK resource limits.
- [Java 17 DocumentBuilderFactory API](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html): parser features, XInclude, entity expansion.
- [Spring Security 6.5 OpenSAML Support](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html): OpenSAML 4/5 integration.
- [Spring Security 6.5 SAML2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): SAML authentication pipeline.
- [OpenSAML Secure XML Processing Requirements](https://shibboleth.atlassian.net/wiki/spaces/OSAML/pages/1828356995/Secure+XML+Processing+Requirements): parser security, comments/coalescing và XMLDSig.
- [Spring Blog – SAML XML Parser Security](https://spring.io/blog/2018/03/01/spring-security-saml-and-this-week-s-saml-vulnerability/): unsafe ParserPool configurations.
- [CWE-611 XXE](https://cwe.mitre.org/data/definitions/611.html): XML External Entity Reference.
- [CWE-776 XML Entity Expansion](https://cwe.mitre.org/data/definitions/776.html): Recursive Entity References in DTDs.
