# Kiểm chứng tương thích MTOM giữa máy chủ và máy khách

**MTOM (Message Transmission Optimization Mechanism)** giúp dịch vụ SOAP truyền dữ liệu nhị phân như PDF, ảnh hoặc hồ sơ đính kèm mà không bắt buộc mã hóa toàn bộ dữ liệu thành chuỗi Base64 bên trong XML. Nhưng chỉ cần bật một cờ `mtomEnabled=true` ở máy khách **không chứng minh** máy chủ đọc được tệp, không chứng minh client khác hiểu phản hồi và cũng không chứng minh dữ liệu nhị phân được bảo vệ theo chính sách bảo mật.

Tình huống điển hình: một dịch vụ `UploadDocument` dùng SOAP contract-first. Máy khách Java gửi PDF 15 MiB, server Spring Web Services (Spring-WS) nhận đúng yêu cầu XML nhưng tệp bị rỗng hoặc báo thiếu `cid`. Ở một chiều khác, server trả tài liệu bằng MTOM và client .NET chỉ đọc phần SOAP XML mà không tái dựng attachment. Các trường hợp này phải được kiểm chứng bằng **hợp đồng XSD/WSDL, cấu hình JAXB/SOAP, thông điệp MIME trên dây và kiểm tra dữ liệu đầu-cuối**, chứ không chỉ bằng test gọi Java method.

Bài thuộc chương **Tệp đính kèm** của module **SPRING_WEB_SERVICES**: phát triển dịch vụ SOAP theo hướng **contract-first** với XSD/WSDL, JAXB/OXM, endpoint và SOAP client, đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích để tích hợp hệ thống doanh nghiệp ổn định. Mục tiêu của bài là xây được **bộ tiêu chí và quy trình kiểm chứng MTOM hai chiều**, phân biệt lỗi contract, marshalling, MIME packaging, transport và bảo mật.

## 1. “Tương thích MTOM” nghĩa là gì?

Một tích hợp MTOM được coi là đạt khi **cả phía gửi lẫn phía nhận** thống nhất ít nhất năm điều:

| Góc độ | Điều phải thống nhất | Phép kiểm chứng |
| --- | --- | --- |
| **Contract** | Global element, QName, `xs:base64Binary`, content type và SOAP binding | XSD/WSDL, JAXB types, schema validation |
| **Biểu diễn SOAP** | SOAP 1.1 hay 1.2; XOP/MTOM được hỗ trợ | Envelope namespace, root MIME part và Content-Type |
| **MIME packaging** | `multipart/related`, boundary, `Content-ID`, `xop:Include href` | Bắt thông điệp HTTP test và phân tích MIME |
| **Tính toàn vẹn dữ liệu** | Bytes nhận **bằng** bytes gốc, không thiếu/trùng/hỏng | Kích thước, SHA-256 và nội dung file đã tái dựng |
| **Vận hành/bảo mật** | Giới hạn kích thước, stream lifetime, TLS/mTLS, WS-Security, xử lý lỗi | Negative tests, load tests, policy tests |

Với operation trả file, phải kiểm chứng **server → client**; với operation nhận file, kiểm chứng **client → server**; với dịch vụ vừa nhận vừa trả, thực hiện **cả hai chiều**. Một test chỉ xác nhận `UploadDocumentResponse.status=OK` không đủ: server có thể ghi tệp hỏng nhưng vẫn trả kết quả thành công.

### Điều kiện chấp nhận tối thiểu

Một giao dịch thành công nên đáp ứng:

1. Máy nhận chọn được SOAP endpoint và hiểu payload root QName đúng XSD.
2. Nếu hợp đồng **bắt buộc MTOM**, HTTP message thực sự có định dạng XOP/MIME được thỏa thuận, không chỉ Base64 inline.
3. Mọi `xop:Include href="cid:..."` tham chiếu được tới **đúng MIME part**, không có CID thiếu hoặc nhập nhằng.
4. XML Infoset sau tái dựng biểu diễn đúng giá trị `xs:base64Binary`, không làm thay đổi nội dung binary.
5. Tệp nhận có **cùng byte length và SHA-256** với tệp nguồn.
6. SOAP Fault, TLS/mTLS, xác minh chữ ký và giới hạn tài nguyên hoạt động ngay cả khi request bị hỏng/cố tình lạm dụng.

Không nên đánh đồng “số attachment bằng 1” với “đúng tệp”: có thể có một MIME part nhưng sai `Content-ID`, sai bytes hoặc không được phần tử SOAP Body tham chiếu.

## 2. MTOM, XOP, Base64 inline và SOAP with Attachments khác nhau thế nào?

Khi XSD định nghĩa:

~~~xml
<xs:element name="content" type="xs:base64Binary"/>
~~~

Giá trị logic của `content` là **một dãy byte**. XML thông thường thể hiện nó bằng Base64:

~~~xml
<doc:content xmlns:doc="urn:example:documents:v1">
    JVBERi0xLjQKLi4u
</doc:content>
~~~

Base64 thường tăng kích thước phần dữ liệu so với bytes gốc khoảng **4/3**, chưa kể XML framing; cách này đơn giản nhưng tốn băng thông/bộ nhớ khi file lớn.

Với **MTOM**, SOAP implementation có thể chọn đưa bytes sang một **MIME part nhị phân**, rồi chèn tham chiếu `xop:Include` trong biểu diễn SOAP XML:

~~~xml
<doc:content xmlns:doc="urn:example:documents:v1"
             xmlns:xop="http://www.w3.org/2004/08/xop/include">
    <xop:Include href="cid:file-01@example.org"/>
</doc:content>
~~~

Receiver phải tìm MIME part có `Content-ID: <file-01@example.org>`, lấy bytes và tái dựng giá trị XML Infoset tương đương `xs:base64Binary`. **`xop:Include` là chi tiết truyền tải của gói XOP**, không phải một element business tùy ý mà bạn nên thêm vào XSD application.

| Cơ chế | Biểu diễn | Dùng khi nào | Điểm quan trọng |
| --- | --- | --- | --- |
| **Inline Base64** | Text Base64 trực tiếp trong XML | Payload nhỏ, đối tác không dùng MTOM | Không có MIME part bên ngoài |
| **MTOM + XOP** | `xop:Include` tham chiếu MIME part khi tối ưu | Dữ liệu `xs:base64Binary`, hai bên hỗ trợ | Giữ nghĩa của XML Infoset; có thể có fallback inline |
| **SOAP with Attachments (SwA)** | SOAP root MIME part và attachment parts | Hợp đồng/đối tác dùng mô hình SwA | Không đồng nghĩa XOP; quan hệ tới Body có thể theo cơ chế khác |
| **swaRef** | Giá trị tham chiếu tới MIME attachment theo WS-I profile | Hợp đồng khai báo kiểu `swaRef` | Không đánh đồng với MTOM optimization cho `base64Binary` |
| **HTTP multipart/form-data** | Multipart upload của web form | REST/web upload | **Không** phải MTOM SOAP binding |

### MTOM không luôn phát sinh MIME part

Bật `Jaxb2Marshaller.setMtomEnabled(true)` cho phép JAXB dùng cơ chế XOP/MTOM, nhưng **không cam kết mọi field nhị phân, mọi kích thước đều được externalize**. Implementation có thể quyết định giữ bytes inline, chẳng hạn khi dữ liệu nhỏ hoặc attachment context chưa được áp dụng. Để khẳng định **wire optimization xảy ra**, test phải thấy `multipart/related`, `application/xop+xml` và tham chiếu CID hợp lệ.

### XML Infoset và hiệu ứng tối ưu

~~~mermaid
flowchart LR
    A["Java DataHandler / byte[]"] --> B["JAXB XML Infoset<br/>base64Binary"]
    B --> C{"MTOM/XOP có áp dụng?"}
    C -->|Không| I["SOAP XML<br/>Base64 inline"]
    C -->|Có| X["MIME multipart/related<br/>SOAP root + binary part"]
    X --> D["Receiver tái dựng Infoset"]
    I --> D
    D --> E["JAXB / application<br/>bytes gốc"]
~~~

Tiêu chuẩn MTOM/XOP đòi hỏi **nội dung logic được bảo toàn** sau quá trình đóng gói và giải đóng gói. Kiểm tra raw XML string của một gói XOP như thể nó là XML business độc lập có thể gây nhầm lẫn; phải kiểm tra **MIME package + SOAP envelope được tái dựng**.

## 3. Gói MTOM trên dây trông như thế nào?

Ví dụ minh họa **SOAP 1.2** gửi `UploadDocumentRequest` qua HTTP, các giá trị `boundary` và `Content-ID` chỉ mang tính minh họa:

~~~http
POST /soap/documents HTTP/1.1
Host: api.example.org
Content-Type: multipart/related; boundary="batch_42"; type="application/xop+xml"; start="<root-42@example.org>"; start-info="application/soap+xml"
MIME-Version: 1.0

--batch_42
Content-Type: application/xop+xml; charset=UTF-8; type="application/soap+xml"
Content-Transfer-Encoding: 8bit
Content-ID: <root-42@example.org>

<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:doc="urn:example:documents:v1"
              xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <env:Body>
    <doc:UploadDocumentRequest>
      <doc:documentId>DOC-123</doc:documentId>
      <doc:filename>contract.pdf</doc:filename>
      <doc:content>
        <xop:Include href="cid:file-42@example.org"/>
      </doc:content>
    </doc:UploadDocumentRequest>
  </env:Body>
</env:Envelope>

--batch_42
Content-Type: application/pdf
Content-Transfer-Encoding: binary
Content-ID: <file-42@example.org>

[NHỊ PHÂN PDF THẬT: không phải chuỗi ký tự này]
--batch_42--
~~~

**Đây là sơ đồ MIME đọc bằng mắt, không phải fixture byte-for-byte hợp lệ**: một gói thực phải dùng CRLF, ranh giới MIME và dữ liệu nhị phân nguyên vẹn theo tiêu chuẩn. Không bao giờ chèn literal `[NHỊ PHÂN...]` vào file test rồi khẳng định kiểm chứng dữ liệu.

### Những trường cần quan sát

| Trường | Giá trị/mục đích |
| --- | --- |
| Outer `Content-Type` | `multipart/related`, `type="application/xop+xml"`, `boundary` |
| `start` | Content-ID của **root SOAP part** khi dùng tham số này |
| `start-info` | Thông tin binding SOAP; với SOAP 1.2 MTOM theo W3C là `application/soap+xml` |
| Root MIME part | `Content-Type: application/xop+xml` và tham số `type` cho SOAP media type |
| SOAP Envelope | Namespace SOAP 1.1/1.2 đúng binding |
| `xop:Include href` | `cid:...` trỏ đúng MIME part |
| Binary MIME part | `Content-ID`, `Content-Type` và bytes nhị phân |
| Closing boundary | Kết thúc package đúng syntax |

Một MIME parser phải kiểm tra boundary, Content-ID, Content-Type và tái dựng tham chiếu. Tự lấy substring giữa hai dấu gạch ngang bằng regex không an toàn: nội dung file có thể chứa ký tự tùy ý, không phải văn bản.

### SOAP 1.1 và SOAP 1.2

W3C MTOM Recommendation mô tả rõ cơ chế SOAP 1.2; các triển khai SOAP 1.1 có thể sử dụng profile/binding MTOM tương thích theo chính sách hai phía. Khi kiểm thử:

- **SOAP 1.1:** Envelope namespace `http://schemas.xmlsoap.org/soap/envelope/`, media type SOAP gốc thường liên quan `text/xml` và SOAPAction transport.
- **SOAP 1.2:** Envelope namespace `http://www.w3.org/2003/05/soap-envelope`, media type SOAP `application/soap+xml`; action theo binding/media type.
- **XOP:** namespace `http://www.w3.org/2004/08/xop/include` không phụ thuộc prefix.

Đừng chỉ đổi `start-info` mà giữ Envelope sai version. Client SOAP 1.1 và server SOAP 1.2 có thể gặp `VersionMismatch` dù cả hai đều hỗ trợ MTOM.

## 4. Hợp đồng XSD: binary thuộc Body, không phải MIME tự do

Một thiết kế contract-first nên mô tả **giá trị nhị phân trong XSD**. Ví dụ schema tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:doc="urn:example:documents:v1"
           targetNamespace="urn:example:documents:v1"
           elementFormDefault="qualified">

  <xs:element name="UploadDocumentRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="filename" type="xs:string"/>
        <xs:element name="content" type="xs:base64Binary"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="UploadDocumentResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="sha256" type="xs:string"/>
        <xs:element name="acceptedBytes" type="xs:long"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Với `xs:base64Binary`, **giá trị XSD vẫn là bytes** ngay cả khi SOAP stack truyền bằng XOP. XSD không cần định nghĩa `xop:Include` làm child của `content`. Nếu phía đối tác yêu cầu `application/pdf`, nên công bố content type ở hợp đồng/policy. Một tùy chọn là annotation XML MIME do chuẩn JAXB hỗ trợ:

~~~xml
<!-- Trích đoạn: cần xmlns:xmime và schema import/local catalog hợp lệ. -->
<xs:element name="content" type="xs:base64Binary"
            xmime:expectedContentTypes="application/pdf"/>
~~~

Ở schema chứa annotation, namespace `xmime` có thể là `http://www.w3.org/2005/05/xmlmime`. Nếu compiler XSD cần import, hãy dùng schema/catalog **đóng gói nội bộ đáng tin cậy**, không fetch URL ngoài trong lúc nhận SOAP request. Những toolchains khác nhau có thể ánh xạ annotation này khác nhau; **phải kiểm tra Java classes thật sau codegen**.

### Bên gửi/bên nhận cần nhất quán những gì?

| Hợp đồng | Ví dụ | Kiểm tra |
| --- | --- | --- |
| Root request QName | `{urn:example:documents:v1}UploadDocumentRequest` | Spring-WS `@PayloadRoot` và client JAXB |
| Binary element QName | `{urn:example:documents:v1}content` | Đúng namespace/local name |
| XSD type | `xs:base64Binary` | Giá trị có semantics byte array |
| Optional/null | `minOccurs` và `nillable` đúng | Thiếu/rỗng/nil khác nhau |
| Media type | `application/pdf` nếu được công bố | MIME part và payload thật khớp |
| Response contract | `UploadDocumentResponse` có checksum/số byte | Client đối chiếu kết quả |
| WS-Policy | Có thể có MTOM assertion | Bắt buộc hay tùy chọn phải rõ |

**Không coi `filename="contract.pdf"` là chứng minh đó là PDF**. Tên file và MIME Content-Type đều là metadata có thể bị giả mạo. Server phải kiểm tra loại nội dung theo policy, giới hạn kích thước và quét tệp nếu nghiệp vụ yêu cầu.

## 5. WS-Policy: MTOM bắt buộc hay tùy chọn?

Hai hệ thống nói “hỗ trợ MTOM” chưa chắc giống nhau:

- **Optional:** server nhận cả inline Base64 và optimized MIME packages.
- **Required:** client phải gửi XOP/MTOM, và response được tối ưu như policy mô tả.
- **Có điều kiện:** một số operations/port/binding hoặc kích thước tệp chỉ chấp nhận MTOM.

Một WS-Policy assertion theo MTOM Serialization Policy:

~~~xml
<wsoma:MTOM
    xmlns:wsoma="http://www.w3.org/2007/08/soap12-mtom-policy"/>
~~~

Đây là **assertion rút gọn**, không phải WSDL/WS-Policy document hoàn chỉnh. Với assertion có `wsp:Optional="true"`, client phải hiểu policy alternatives theo chuẩn và xác định binding/port đang chọn. Không chỉ thấy chuỗi `MTOM` trong WSDL rồi suy ra mọi request/response bắt buộc có attachment; đồng thời **WSDL XSD `base64Binary` không tự quy định optimization phải bật**.

Theo policy, một client có thể gửi một request với MIME MTOM để thương lượng/biểu thị khả năng nhận optimized response; test chính xác cần xem policy của đối tác và behavior trên từng port, SOAP version.

## 6. JAXB/OXM: DataHandler, byte[] và @XmlMimeType

Trong Java, JAXB có thể ánh xạ binary field thành `byte[]`, `DataHandler` hoặc kiểu khác tùy binding và media type. Với file lớn, `DataHandler` thường hữu ích vì có thể truy cập qua stream, nhưng **không mặc định bảo đảm streaming đầu-cuối**: SAAJ, JAXB provider, HTTP sender hoặc logging có thể đệm dữ liệu trong RAM.

Ví dụ Java class minh họa tương đương ý tưởng JAXB từ `UploadDocumentRequest`:

~~~java
import jakarta.activation.DataHandler;
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlMimeType;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(
    name = "UploadDocumentRequest",
    namespace = "urn:example:documents:v1")
@XmlAccessorType(XmlAccessType.FIELD)
public class UploadDocumentRequest {
    private static final String NS = "urn:example:documents:v1";

    @XmlElement(namespace = NS, required = true)
    private String documentId;

    @XmlElement(namespace = NS, required = true)
    private String filename;

    @XmlElement(namespace = NS, required = true)
    @XmlMimeType("application/pdf")
    private DataHandler content;

    public String getDocumentId() { return documentId; }
    public void setDocumentId(String v) { documentId = v; }
    public String getFilename() { return filename; }
    public void setFilename(String v) { filename = v; }
    public DataHandler getContent() { return content; }
    public void setContent(DataHandler v) { content = v; }
}
~~~

Đây là class **minh họa cách binding**, không phải cam kết mọi phiên bản XJC tự sinh đúng cấu trúc này. Trong dự án contract-first, ưu tiên **generated classes từ XSD**, kiểm tra `ObjectFactory`/`@XmlRootElement`/`@XmlMimeType` và cấu hình binding file cho codegen nếu cần. **Không chỉnh tay class generated** rồi để lần build kế tiếp ghi đè.

### DataHandler không thay thế validation

`DataHandler` chứa một nguồn dữ liệu và MIME type; khi tạo từ file:

~~~java
import jakarta.activation.DataHandler;
import jakarta.activation.FileDataSource;
import java.io.File;

File pdf = new File("/secure-test-fixtures/contract.pdf");
DataHandler binary = new DataHandler(new FileDataSource(pdf));

UploadDocumentRequest request = new UploadDocumentRequest();
request.setDocumentId("DOC-123");
request.setFilename("contract.pdf");
request.setContent(binary);
~~~

Đường dẫn ở trên chỉ là **fixture tượng trưng**, không phải file đã tồn tại trên workspace. Với triển khai thực tế, nguồn file phải được kiểm soát, không lấy path từ SOAP request mà không chuẩn hóa/kiểm tra. Dữ liệu `DataHandler` có thể được đọc **khi marshal**, nên đừng đóng, xóa hoặc thay file nguồn trước khi gửi xong message.

### Javax hay Jakarta?

Với Spring-WS thế hệ Jakarta/Spring Framework 6, thường dùng `jakarta.xml.bind.*` và `jakarta.activation.DataHandler`. Trong dự án Spring-WS/Java EE cũ, code có thể dùng `javax.xml.bind.*`/`javax.activation.*`. **Không trộn JAXB runtime và generated annotations giữa hai thế hệ**; lỗi tương thích kiểu có thể xảy ra trước khi MTOM serialization.

## 7. Cấu hình phía máy khách Spring-WS

Một SOAP client dùng `WebServiceTemplate` có ba thành phần khác nhau:

~~~mermaid
flowchart LR
    A["UploadDocumentRequest<br/>DataHandler"] --> B["Jaxb2Marshaller<br/>setMtomEnabled(true)"]
    B --> C["SaajSoapMessageFactory<br/>SOAP 1.1/1.2"]
    C --> D["WebServiceTemplate"]
    D --> E["HTTP MessageSender<br/>HTTPS, timeouts, mTLS"]
    E --> F["Spring-WS server"]
~~~

Ví dụ cấu hình **SOAP 1.2** với JAXB package minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;
import org.springframework.ws.transport.http.HttpUrlConnectionMessageSender;

@Configuration
public class DocumentsSoapClientConfig {

    @Bean
    public Jaxb2Marshaller documentsMtomOxm() {
        Jaxb2Marshaller oxm = new Jaxb2Marshaller();
        oxm.setContextPath("org.example.documents.v1");
        oxm.setMtomEnabled(true);
        return oxm;
    }

    @Bean
    public SaajSoapMessageFactory documentsSoapFactory() {
        SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
        factory.setSoapVersion(SoapVersion.SOAP_12);
        return factory;
    }

    @Bean
    public WebServiceTemplate documentsTemplate(
            SaajSoapMessageFactory documentsSoapFactory,
            Jaxb2Marshaller documentsMtomOxm) {

        WebServiceTemplate template =
                new WebServiceTemplate(documentsSoapFactory);
        template.setMarshaller(documentsMtomOxm);
        template.setUnmarshaller(documentsMtomOxm);
        template.setMessageSender(new HttpUrlConnectionMessageSender());
        template.setDefaultUri("https://partner.example.org/soap/documents");
        return template;
    }
}
~~~

**Điều kiện:** JAXB context path đúng package generated, SAAJ/Jakarta Activation runtime tương thích và SOAP endpoint hỗ trợ SOAP 1.2. `HttpUrlConnectionMessageSender` minh họa sender cơ bản; production cần cấu hình TLS trust, mTLS nếu yêu cầu, timeout, connection management và proxy phù hợp. Đừng hardcode credentials, keys hoặc tệp thật vào source.

### 7.1. Gửi request

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;

public class DocumentsClient {
    private final WebServiceTemplate template;

    public DocumentsClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object upload(UploadDocumentRequest request) {
        return template.marshalSendAndReceive(request);
    }
}
~~~

Nếu JAXB generated model không có `@XmlRootElement` mà sử dụng `JAXBElement<T>`, hãy truyền root element từ `ObjectFactory`. Một response có thể được unmarshal thành class trực tiếp hoặc `JAXBElement<?>`; kiểm tra type thực tế trước khi ép kiểu. Thêm SOAPAction/WS-Addressing headers nếu WSDL yêu cầu; chúng **không thay thế** cấu hình MTOM.

**Bật MTOM ở client chưa bảo đảm server dùng nó:** phải kiểm tra HTTP request thực. Nếu máy khách chỉ gửi inline Base64, cần xem JAXB binding, MTOM context và kích thước dữ liệu, không sửa ngẫu nhiên XSD để tự thêm `xop:Include`.

## 8. Cấu hình phía máy chủ Spring-WS

Server cần đồng bộ **SOAP message factory**, **endpoint/JAXB binding**, **XSD schema**, **transport** và **security policy**. Trong cấu hình hiện đại:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@EnableWs
@Configuration
public class DocumentsServerConfig {

    @Bean
    public SaajSoapMessageFactory messageFactory() {
        SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
        factory.setSoapVersion(SoapVersion.SOAP_12);
        return factory;
    }

    @Bean
    public Jaxb2Marshaller documentMarshaller() {
        Jaxb2Marshaller oxm = new Jaxb2Marshaller();
        oxm.setContextPath("org.example.documents.v1");
        oxm.setMtomEnabled(true);
        return oxm;
    }
}
~~~

**Cảnh báo cấu hình quan trọng:** Bean `Jaxb2Marshaller` trên server **không tự bảo đảm** mọi `@Endpoint` method dùng chính bean đó. Spring-WS có các **argument resolvers/return value handlers** cho JAXB và một processor riêng `MarshallingPayloadMethodProcessor`; nếu endpoint adapter chọn một JAXB processor mặc định khác, `mtomEnabled=true` của bean tùy chỉnh có thể không được dùng ở đường marshal/unmarshal.

Trong ứng dụng có `@EnableWs`, có thể sử dụng `WsConfigurer` để cung cấp một `MarshallingPayloadMethodProcessor` gắn OXM:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.endpoint.adapter.method.MarshallingPayloadMethodProcessor;
import org.springframework.ws.server.endpoint.adapter.method.MethodArgumentResolver;
import org.springframework.ws.server.endpoint.adapter.method.MethodReturnValueHandler;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class DocumentEndpointOxmConfig implements WsConfigurer {
    private final MarshallingPayloadMethodProcessor processor;

    public DocumentEndpointOxmConfig(Jaxb2Marshaller documentMarshaller) {
        processor = new MarshallingPayloadMethodProcessor(documentMarshaller);
    }

    @Override
    public void addArgumentResolvers(List<MethodArgumentResolver> resolvers) {
        resolvers.add(processor);
    }

    @Override
    public void addReturnValueHandlers(
            List<MethodReturnValueHandler> handlers) {
        handlers.add(processor);
    }
}
~~~

Đây là **cấu hình tích hợp minh họa**, không cam kết processor tùy chỉnh được chọn trước mọi **built-in JAXB resolver**: thứ tự resolver/handler trong `DefaultMethodEndpointAdapter` cần được **kiểm chứng ở runtime** và nếu cần, tùy biến danh sách/ưu tiên qua cấu hình Spring-WS tương ứng. Đây chính là một test tương thích quan trọng: **server có thật sự tạo MIME/XOP response và unmarshal XOP request bằng OXM đã bật MTOM không?**

### 8.1. Endpoint nhận nội dung nhị phân

~~~java
import java.io.InputStream;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class DocumentEndpoint {
    private static final String NS = "urn:example:documents:v1";
    private final DocumentStorageService storage;

    public DocumentEndpoint(DocumentStorageService storage) {
        this.storage = storage;
    }

    @PayloadRoot(namespace = NS, localPart = "UploadDocumentRequest")
    @ResponsePayload
    public UploadDocumentResponse upload(
            @RequestPayload UploadDocumentRequest request) throws Exception {

        if (request.getContent() == null) {
            throw new InvalidDocumentException("Thiếu content");
        }
        // Service tự áp giới hạn size, loại file, checksum,
        // quyền truy cập và quản lý nguồn stream.
        try (InputStream input = request.getContent().getInputStream()) {
            StoredDocument stored = storage.putValidated(
                    request.getDocumentId(),
                    request.getFilename(), input);

            UploadDocumentResponse reply = new UploadDocumentResponse();
            reply.setDocumentId(stored.id());
            reply.setSha256(stored.sha256());
            reply.setAcceptedBytes(stored.bytes());
            return reply;
        }
    }
}
~~~

Đoạn code là **mẫu endpoint**: `DocumentStorageService`, `StoredDocument`, `InvalidDocumentException` và generated response phải được triển khai trong dự án. File validation, security và response Fault resolver chưa được cung cấp. Nếu payload JAXB field là `byte[]` thay vì `DataHandler`, phương thức nhận stream cần được điều chỉnh theo binding.

**Không đọc toàn bộ input stream thành `byte[]` vô hạn**; hãy áp giới hạn byte đọc, timeout, content-type policy và checksum trong service. Nhận multipart không đồng nghĩa bỏ qua xử lý an toàn đối với dữ liệu đính kèm.

## 9. Kiểm chứng payload và MIME ở server bằng MimeMessage

Spring-WS cung cấp `org.springframework.ws.mime.MimeMessage` và `org.springframework.ws.mime.Attachment`. `SoapMessage` mở rộng hỗ trợ MIME, nên trong một `MessageContext` thích hợp có thể:

~~~java
import java.util.Iterator;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.mime.Attachment;
import org.springframework.ws.mime.MimeMessage;

public void inspectRequestAttachments(MessageContext context) {
    if (!(context.getRequest() instanceof MimeMessage mime)) {
        throw new IllegalStateException("Cần MIME-capable message");
    }

    boolean xop = mime.isXopPackage();
    Iterator<Attachment> parts = mime.getAttachments();
    while (parts.hasNext()) {
        Attachment part = parts.next();
        String contentId = part.getContentId();
        String contentType = part.getContentType();
        long size = part.getSize(); // Có thể -1 nếu không xác định.
        // Dùng cho kiểm tra/metrics đã lọc; không log bytes/tokens.
    }

    // Quan sát xop và các parts theo contract,
    // không dùng riêng boolean này để xác thực payload.
}
~~~

`getAttachment(contentId)` cho phép tra phần đính kèm theo CID và có thể trả `null` nếu không tồn tại; `getInputStream()` trên `Attachment` phải được **đóng sau khi dùng**. Chú ý:

- `MimeMessage.isXopPackage()` xác định thông điệp có phải gói XOP không theo implementation.
- `getAttachments()` liệt kê MIME parts mà SOAP stack cung cấp, **không mặc định bằng số phần tử binary trong XSD**.
- CID của root SOAP part và CID của binary attachment là **hai loại đối tượng khác nhau**.
- `getSize()` có thể bằng `-1` nếu provider không biết size; không bỏ kiểm tra quota chỉ vì size chưa rõ.
- Khi handler đọc attachment stream để tính checksum, nó có thể tiêu thụ nguồn dữ liệu; hãy kiểm tra streaming/caching semantics trước khi đọc nhiều lần.

### MIME attachment được thêm thủ công khác MTOM tối ưu tự động

Spring-WS `MimeMessage.addAttachment(...)` cho phép đính kèm một MIME part:

~~~java
import org.springframework.core.io.ByteArrayResource;
import org.springframework.ws.mime.MimeMessage;

MimeMessage mime = (MimeMessage) soapMessage;
mime.addAttachment(
        "manual-attachment@example.org",
        new ByteArrayResource(new byte[] {1, 2, 3}),
        "application/octet-stream");
~~~

**Nhưng chỉ gọi `addAttachment` chưa chứng minh tạo MTOM package hợp đồng.** Để có XOP optimization của một phần tử `xs:base64Binary`, SOAP root phải chứa `xop:Include` với đúng CID và MIME package phải có định dạng XOP phù hợp. Một attachment không được tham chiếu có thể là **SwA/manual attachment**, không phải phần tối ưu của `content`.

## 10. Thiết kế kiểm thử ba lớp

Để kết luận hai bên tương thích, nên có ít nhất ba lớp test:

| Lớp | Công cụ gợi ý | Chứng minh được | **Chưa** chứng minh được |
| --- | --- | --- | --- |
| **JAXB/OXM test** | JAXB marshaller/unmarshaller, Spring OXM test | Java ↔ XML theo XSD, annotations, bytes roundtrip | MIME HTTP wire format, TLS, proxy |
| **SOAP message test** | `MockWebServiceClient` (server), `MockWebServiceServer` (client), SAAJ/MimeMessage assertions | SOAP Body/Header, attachment model, response/Fault | HTTP multipart thực sự sau sender/proxy |
| **Wire-level integration** | Embedded HTTP(S) endpoint, test server, staging đối tác, MIME parser | Content-Type, boundary/CID, wire bytes, SOAP versions, TLS/mTLS | Không tự đại diện cho mọi runtime của đối tác nếu chỉ test một provider |

**Không đánh đồng mock transport với transport thật.** `MockWebServiceServer` có thể kiểm thử request message mà `WebServiceTemplate` tạo, nhưng thường **không mở một HTTP connection thật** để xác minh headers, chunked encoding, multipart boundaries hoặc proxy behavior. Muốn chứng minh MTOM tương thích trên dây, bắt buộc có ít nhất một test HTTP(S) ở cấp message thật.

### Thứ tự ưu tiên test

~~~mermaid
flowchart TD
    A["XSD/WSDL và JAXB bindings"] --> B["Local OXM roundtrip"]
    B --> C["Spring-WS message-level test"]
    C --> D["HTTP multipart/XOP test"]
    D --> E["Bilateral integration test<br/>Java ↔ server thật"]
    E --> F["Cross-platform test<br/>.NET / ESB / khác"]
    F --> G["Load + security + negative tests"]
~~~

Không bỏ qua lớp đầu khi debug lớp sau: nếu XSD root QName sai hoặc JAXB generated classes không hiểu `DataHandler`, chỉnh MIME boundary ở HTTP server sẽ không giải quyết nguyên nhân.

## 11. Bộ dữ liệu kiểm thử và phép đối chiếu bytes

Để kiểm chứng MTOM có ý nghĩa, hãy chọn **ít nhất hai kích thước dữ liệu** và nhiều dạng nội dung:

| Fixture | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Rỗng** | `0 B`, nếu XSD cho phép | Phân biệt empty với absent/nil |
| **Rất nhỏ** | `1 B`, `16 B`, `1 KiB` | Kiểm tra fallback Base64/threshold |
| **Qua ngưỡng tối ưu** | `256 KiB`, `1 MiB` | Kích hoạt XOP trên provider thường gặp, nhưng phải quan sát thực |
| **Lớn** | `20 MiB`, `100 MiB` theo quota môi trường | Memory, timeout, streaming, backpressure |
| **Binary có byte tùy ý** | `0x00`, `0xFF`, CR/LF, chuỗi chứa boundary-like bytes | Không bị xử lý như text, không cắt file |
| **Đúng loại PDF/PNG** | File fixture đã biết định dạng | Kiểm tra content type và business content validation |
| **Không đúng loại** | File ngẫu nhiên nhưng báo `application/pdf` | Server không tin MIME header |
| **Gửi lặp** | Cùng documentId, bytes khác nhau | Quy tắc ghi đè/idempotency/authorization |

**Dữ liệu ngẫu nhiên nhị phân cố định seed** thường tốt hơn file chỉ toàn `0x00`: nó dễ phát hiện cắt/đảo bytes hoặc lỗi encode/decode. Chọn fixture **không chứa bí mật**, có thể sinh lại và được CI lưu trữ theo chính sách.

### 11.1. So SHA-256 thay vì so chuỗi Base64

Trên client trước khi gửi:

~~~java
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.HexFormat;

static String sha256(InputStream in) throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[8192];
    for (int count; (count = in.read(buffer)) != -1; ) {
        if (count > 0) {
            digest.update(buffer, 0, count);
        }
    }
    return HexFormat.of().formatHex(digest.digest());
}
~~~

`HexFormat` yêu cầu Java 17+. Helper này **không đóng input**; bên gọi cần dùng `try-with-resources`. Trong test, tính hash nguồn từ một input stream, upload từ một stream **độc lập**, rồi tính hash trên bytes server đã lưu. Không đọc hết một stream có thể chỉ mở một lần để tính checksum trước khi gửi, sau đó hy vọng sender vẫn còn bytes.

Một test thành công có thể assert:

~~~text
sourceBytes == serverStoredBytes
SHA256(source) == SHA256(serverStoredFile)
response.acceptedBytes == sourceBytes
response.sha256 == SHA256(source)
~~~

Điều này kiểm chứng **giá trị dữ liệu cuối-cuối**. Tuy nhiên, nó vẫn **chưa chứng minh MTOM được dùng trên dây**; phải kết hợp MIME assertions ở phần 12–14.

### 11.2. Khi file lớn, không lưu cả blob trong test assertions

Với file 100 MiB, tránh `readAllBytes()` hai phía hoặc lưu hai bản sao trong RAM chỉ để so bằng `Arrays.equals(...)`. Dùng streaming SHA-256 và đếm byte có giới hạn. Nếu mục tiêu là đo **đỉnh bộ nhớ**, test phải đo thực tế ở client, server, servlet container, message factory và HTTP sender.

## 12. Test phía máy khách bằng MockWebServiceServer

`MockWebServiceServer` kiểm tra `WebServiceTemplate` phía client, cho phép định nghĩa `RequestMatcher` tùy chỉnh. Với SOAP message đã marshal, ta có thể xác minh nó hỗ trợ MIME/XOP và chứa attachment:

~~~java
import java.net.URI;
import java.util.Iterator;
import org.junit.jupiter.api.Assertions;
import org.springframework.ws.mime.Attachment;
import org.springframework.ws.mime.MimeMessage;
import org.springframework.ws.test.client.MockWebServiceServer;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import org.springframework.xml.transform.StringSource;

MockWebServiceServer mock =
        MockWebServiceServer.createServer(webServiceTemplate);

mock.expect((URI uri, org.springframework.ws.WebServiceMessage request) -> {
    Assertions.assertInstanceOf(MimeMessage.class, request);
    MimeMessage mime = (MimeMessage) request;

    // Chỉ nên kỳ vọng true với fixture đủ lớn
    // và MTOM thực sự được bật/được provider sử dụng.
    Assertions.assertTrue(mime.isXopPackage());

    Iterator<Attachment> attachments = mime.getAttachments();
    Assertions.assertTrue(attachments.hasNext());
    Attachment first = attachments.next();
    Assertions.assertNotNull(first.getContentId());
    Assertions.assertEquals("application/pdf", first.getContentType());

    // Đọc InputStream để hash bytes trong fixture, nếu provider
    // cho phép và không làm tiêu thụ nguồn trước khi request hoàn tất.
}).andRespond(withPayload(new StringSource(
        "<d:UploadDocumentResponse xmlns:d='urn:example:documents:v1'>" +
        "<d:documentId>DOC-123</d:documentId>" +
        "<d:sha256>fixture-sha256</d:sha256>" +
        "<d:acceptedBytes>262144</d:acceptedBytes>" +
        "</d:UploadDocumentResponse>")));

// Gọi webServiceTemplate.marshalSendAndReceive(...) với
// UploadDocumentRequest fixture đã có content hợp lệ.
// Sau đó assert response và gọi mock.verify().
~~~

Đây là **khung JUnit 5**, không phải tệp test độc lập: cần khai báo `webServiceTemplate`, fixture JAXB request, thực hiện lời gọi client, assert response và giải quyết XML root/JAXB binding theo project. Header `Content-Type` của một MIME part có thể chứa tham số; nếu đối tác/provider bổ sung charset hoặc khác cách chuẩn hóa media type, test nên parse media type thay vì so literal string không cần thiết.

**Giới hạn quan trọng:** `MockWebServiceServer` kiểm tra **đối tượng SOAP/MIME** trong client pipeline nhưng **không chứng minh HTTP sender thực sự phát đúng multipart bytes**. Vì vậy phải có wire-level test ở phần 14.

### 12.1. Test khách nhận phản hồi MTOM

Một client hoàn chỉnh còn phải đọc được response do server gửi có XOP attachment. Dùng:

1. Fixture response chứa `UploadDocumentResponse` hoặc `DownloadDocumentResponse` với binary `xs:base64Binary`.
2. HTTP(S) test server phát **multipart/related XOP** thật, có root SOAP part và binary part.
3. Client `WebServiceTemplate` đọc và unmarshal thành JAXB `DataHandler`/`byte[]`.
4. Client tính checksum, kiểm tra metadata, giải phóng nguồn stream.
5. Lặp lại với SOAP Fault để xác nhận client không cố unmarshal Fault thành binary success DTO.

Một `withPayload(...)` mock response chỉ chèn XML Body, **không đủ** chứng minh client giải được MIME part thật. Nếu framework test có khả năng tạo response MIME riêng, cần đảm bảo fixture có đầy đủ XOP packaging; nếu không, dùng HTTP test server.

## 13. Test phía máy chủ bằng MockWebServiceClient

`MockWebServiceClient` chạy request qua Spring-WS endpoint và các thành phần được đăng ký trong test `ApplicationContext`. Với bài MTOM, test nên xác nhận:

- Bean `@Endpoint` thực sự được dispatch theo QName payload.
- `@RequestPayload`/custom marshaller nhận đúng bytes nhị phân.
- `MessageContext.getRequest()` biểu diễn MIME/XOP đúng khi có gói request được cung cấp.
- Service lưu tệp đúng checksum/size và chỉ chạy khi XSD/authorization/security đạt.
- Server trả đúng JAXB response và SOAP Fault cho các lỗi.

Một cách kiểm thử là dùng `RequestCreator` tùy chỉnh để dựng request SOAP có MIME attachments theo provider mà server sử dụng. **Nhưng lưu ý:** tự gọi `MimeMessage.addAttachment(...)` mà không tạo `xop:Include` tham chiếu tương ứng có thể chỉ kiểm thử **SwA/manual attachment**, chưa phải MTOM.

### 13.1. Khi cần kiểm chứng thật, gửi multipart HTTP qua servlet

Để tránh tự tạo một “MTOM request giả”, có thể chạy server Spring-WS trong **embedded servlet container** và đưa vào một gói XOP MIME được tạo bằng SOAP client khác hoặc fixture chuẩn. Kiểm tra:

~~~text
HTTP multipart/related request
    ↓
MessageDispatcherServlet + SaajSoapMessageFactory
    ↓
SOAP root Envelope + xop:Include
    ↓
Attachment CID được resolve
    ↓
JAXB @RequestPayload / MessageContext
    ↓
DocumentStorageService
    ↓
Server-stored SHA-256 == source SHA-256
~~~

Test này bao phủ cả **MIME parsing → JAXB conversion → endpoint behavior** và giúp phát hiện lỗi mà `MockWebServiceClient` thuần payload không bộc lộ, chẳng hạn Content-ID syntax sai, boundary sai hoặc SOAP version/Content-Type không phù hợp.

### 13.2. Test chiều download

Nếu server trả binary:

~~~xml
<doc:DownloadDocumentResponse
    xmlns:doc="urn:example:documents:v1">
    <doc:documentId>DOC-123</doc:documentId>
    <doc:content>
        <!-- Giá trị logic xs:base64Binary; có thể truyền bằng XOP. -->
    </doc:content>
</doc:DownloadDocumentResponse>
~~~

Hãy tạo endpoint trả JAXB object có `DataHandler`/`byte[]`, cấu hình đúng **return value processor dùng OXM MTOM-enabled**, rồi **bắt raw HTTP response** để xác nhận server thực sự xuất `multipart/related`. Chỉ kiểm tra Java response trong controller hoặc XML Body sau khi framework đã tái dựng Infoset là chưa đủ.

## 14. Wire-level test: bắt và kiểm tra MIME/HTTP thật

Đây là bước **quyết định** khi mục tiêu là “kiểm chứng tương thích MTOM giữa máy chủ và máy khách”.

### 14.1. Quy trình thiết lập

1. **Khởi chạy test server HTTP(S)** có SOAP endpoint và message factory thực tế; nếu cần, đặt reverse proxy như production.
2. Dùng **client thật**: `WebServiceTemplate` + SAAJ + OXM MTOM-enabled + HTTP sender.
3. Gửi một file fixture đủ lớn (ví dụ 256 KiB và 20 MiB), có SHA-256 đã biết.
4. Capture request **ở test HTTP boundary** với cơ chế cho phép đọc body nhưng không làm mất dữ liệu, hoặc sử dụng network trace/test proxy an toàn. Không cần vô hiệu hóa TLS trên production để capture.
5. Parse `Content-Type` của HTTP envelope, `boundary`, `start`, `start-info` và toàn bộ MIME parts.
6. Tìm root SOAP part, parse XML namespace-aware, định vị `xop:Include` trong `doc:content`.
7. Resolve `href="cid:..."` tới binary part theo `Content-ID`, so bytes/hash và content type.
8. Kiểm tra server đã lưu đúng bytes, SOAP response, và làm ngược với operation download.

### 14.2. Những assertions cụ thể

| Assertion | Ý nghĩa |
| --- | --- |
| HTTP method/URI đúng | Không POST vào URL `.wsdl` hay port sai |
| Outer Content-Type là `multipart/related` | Có đóng gói MIME |
| `type="application/xop+xml"` | Package được công bố theo XOP |
| `start` (nếu có) trỏ root MIME part | Chọn SOAP Envelope đúng |
| Root `application/xop+xml`, đúng SOAP media type | XOP root sử dụng binding hợp đồng |
| SOAP Envelope namespace đúng | Không trộn SOAP 1.1/1.2 |
| `xop:Include` đúng QName | Không dùng prefix string như tiêu chí |
| `href` có định dạng CID hợp lệ | Tham chiếu đến MIME attachment |
| CID resolve **đúng một** binary part | Không thiếu và không nhập nhằng |
| Binary Content-Type hợp đồng | Thể hiện `application/pdf` nếu bắt buộc |
| Binary SHA-256 và byte count đúng | Không mất/cắt/biến đổi dữ liệu |
| Boundary kết thúc hợp lệ | MIME parser đọc hết package |
| Response/Fault hợp SOAP version | Không mất khả năng xử lý lỗi |

**Không assert boundary, Content-ID hoặc prefix phải có đúng một giá trị cố định** do provider sinh. Một lần chạy có thể tạo UUID/CID khác lần trước. Hãy assert tính **tự nhất quán** của references, loại media và bytes.

### 14.3. Content-ID và cid URI không hoàn toàn cùng chuỗi ký tự

Ví dụ:

~~~http
Content-ID: <file-42@example.org>
~~~

SOAP root:

~~~xml
<xop:Include
    xmlns:xop="http://www.w3.org/2004/08/xop/include"
    href="cid:file-42@example.org"/>
~~~

Trong MIME header, Content-ID thường có dấu ngoặc nhọn góc `<...>`. Trong URI `cid:`, định danh không chứa nguyên văn cặp ngoặc này. Khi so sánh, dùng **parser chuẩn cho MIME/CID URI** để xử lý escape/chuẩn hóa theo RFC; không làm `replace("<", "")` trên toàn chuỗi HTTP rồi coi là parser đầy đủ.

### 14.4. Tại sao phải kiểm tra response độc lập?

Một server có thể **đọc** MTOM request nhưng trả response **inline Base64** vì output JAXB processor không có MIME context. Ngược lại, client có thể **gửi** MTOM nhưng không đọc được server-optimized response. Do đó test gồm:

~~~text
Client → Server: UploadDocumentRequest (MTOM request)
Server → Client: UploadDocumentResponse (SOAP success/fault)

Client → Server: DownloadDocumentRequest (SOAP request)
Server → Client: DownloadDocumentResponse (MTOM response)
~~~

Chỉ khi hai chiều đều được kiểm tra thì mới có cơ sở kết luận client và server hỗ trợ MTOM trong toàn bộ hợp đồng có upload/download.

## 15. Ma trận tương thích theo provider và SOAP binding

| Máy khách | Máy chủ | Binding/cấu hình | Cần chứng minh |
| --- | --- | --- | --- |
| Spring-WS + JAXB | Spring-WS + JAXB | SOAP 1.1, MTOM optional | Có thể đọc inline và optimized; dữ liệu giống nhau |
| Spring-WS + JAXB | Spring-WS + JAXB | SOAP 1.2, MTOM required | Request và response được đóng gói XOP đúng policy |
| Spring-WS + JAXB | .NET/WCF hoặc stack .NET tương ứng | Port MTOM được công bố | Chọn đúng port/binding, nhận DataHandler/bytes |
| .NET/WCF | Spring-WS server | SOAP 1.1/1.2 thỏa thuận | Server unmarshal CID, lưu đúng bytes |
| ESB/Java stack khác | Spring-WS server | XOP/MIME qua proxy | Không bị gateway xóa/sửa Content-Type/boundary |
| Spring-WS client | ESB/server khác | MTOM optional + threshold riêng | Test cả inline Base64 và multipart |
| Spring-WS client | Server không hỗ trợ MTOM | Không có policy tương thích | Fault/HTTP error có kiểm soát; không tự “chữa” bằng sửa XSD |

**Không mặc định .NET/WCF hay ESB hỗ trợ mọi MTOM profile giống Spring-WS.** Tên option cấu hình, ngưỡng attachment optimization, SOAP version và WS-Policy có thể khác nhau giữa các stack và phiên bản. Hãy trao đổi một **wire-level fixture chuẩn** và yêu cầu mỗi phía test đọc/ghi.

### Những thông tin nên bàn giao cho đối tác

- WSDL/XSD đã công bố, imports và namespace/version.
- SOAP 1.1/1.2 binding, endpoint URL, SOAPAction/WS-Addressing nếu dùng.
- MTOM **required/optional**, kích thước file tối đa, các loại MIME cho phép.
- Ví dụ HTTP multipart request/response **đã ẩn dữ liệu thật**.
- Quy tắc Content-ID/CID, attachment mapping và expected root element.
- SHA-256/byte count của vài fixtures không nhạy cảm.
- TLS/mTLS, certificate/WS-Security policy, signed parts/attachments.
- SOAP Fault codes và xử lý request không hợp lệ.

## 16. Negative tests: gói MIME hỏng phải bị từ chối

| Tình huống lỗi | Thay đổi trong request | Kỳ vọng |
| --- | --- | --- |
| **Thiếu MIME part** | `xop:Include href` trỏ CID không có part | Từ chối/parse error, không lưu file |
| **CID trùng** | Hai parts cùng Content-ID được tham chiếu | Không chọn ngẫu nhiên; từ chối hoặc xử lý theo parser/security policy |
| **CID khác chữ hoa/escape** | Thay format URI/Content-ID | Tuân CID URI semantics; test parser thật |
| **Thiếu root part** | `start` chỉ tới CID không tồn tại | Không xử lý như SOAP request hợp lệ |
| **Boundary sai** | Closing boundary thiếu hoặc không khớp | Parser báo lỗi, không ghi dữ liệu dở |
| **Content-Type sai** | Multipart nhưng `type` không phải XOP | Từ chối theo policy hoặc fallback rõ ràng |
| **SOAP version sai** | Root SOAP 1.2 với binding SOAP 1.1 | VersionMismatch/transport error thích hợp |
| **XOP namespace sai** | Thay `http://www.w3.org/2004/08/xop/include` | Không nhận như XOP hợp lệ |
| **`href` không phải cid URI** | `href="https://attacker.example/file"` | Không fetch URL tùy ý; từ chối |
| **Binary bị cắt** | Giảm bytes MIME part | Checksum/size sai, không báo thành công |
| **Media type giả** | `application/pdf` nhưng bytes không phải PDF | Content validation từ chối |
| **Quá kích thước** | Attachment vượt giới hạn | Fail bounded, không OOM hoặc ghi vô hạn |
| **Quá nhiều parts** | Hàng nghìn attachments không được tham chiếu | Quota/part-count limits, không cạn resources |
| **Compression bomb/zip bomb** | Dữ liệu nén nở rất lớn | Giới hạn nội dung sau giải nén nếu có giải nén |
| **XML DTD/XXE** | DTD trong root SOAP/XOP | XML parser bị harden, không mở external entities |
| **Signature sai** | Sửa XML hoặc binary attachment được bảo vệ | WS-Security/attachment policy từ chối |
| **Unsigned attachment** | Body ký đúng nhưng binary không được ký theo policy | Bị từ chối nếu hợp đồng yêu cầu bảo vệ attachment |
| **Một stream bị đọc lại** | DataSource chỉ cho mở một lần | Test behavior rõ; không mất bytes âm thầm |
| **Null/absent/nil** | Bỏ `content` hoặc gửi `xsi:nil` | XSD/schema validation và business rules quyết định |

Một **SOAP Fault không phải kết quả duy nhất có thể xảy ra**. Với MIME hỏng ở tầng HTTP/parser trước SOAP processing, server có thể trả HTTP 4xx/5xx không chứa SOAP Fault. Test nên khẳng định **không có side effect và giới hạn tài nguyên được tôn trọng**, sau đó kiểm tra dạng lỗi theo contract/stack.

### Không test lỗi bằng cách sửa duy nhất một chuỗi Base64

Trong MTOM, bytes có thể nằm ngoài SOAP XML. Chỉ thay phần text `doc:content` không chạm đến MIME binary part. Để test lỗi đúng:

1. Có fixture **multipart byte stream** thật.
2. Sửa riêng **Content-ID** hoặc `xop:Include href`.
3. Sửa riêng **binary MIME bytes** nhưng giữ envelope hợp lệ.
4. Gửi qua servlet và quan sát parser/security response.
5. Assert không có persisted bytes, hoặc transaction rollback/outbox policy phù hợp.

## 17. Giới hạn bộ nhớ, streaming và lifecycle của tệp

MTOM giảm overhead Base64 trên dây, nhưng **không mặc định** giữ bộ nhớ thấp:

- SAAJ thường tạo/cất giữ cấu trúc SOAP trong memory theo DOM; MIME provider có thể có chiến lược buffering.
- JAXB generated `byte[]` có thể buộc tạo toàn bộ binary array trong Java heap.
- `DataHandler` cho phép stream source, nhưng HTTP sender, interceptor logging, retries hoặc checksum có thể đọc nhiều lần.
- Một pipeline có WS-Security signing/encryption có thể buffer toàn bộ/những phần message cần ký/mã hóa.
- Reverse proxy và servlet container có thể spool request body ra disk theo cấu hình, không nhất thiết giữ streaming end-to-end.

| Vấn đề | Cách kiểm soát |
| --- | --- |
| Memory spike/OOM | Test file lớn, quan sát heap, tránh `readAllBytes()` vô hạn |
| Disk spool quá tải | Chọn thư mục tạm an toàn, quota, cleanup và monitoring |
| File nguồn bị xóa sớm | Giữ DataHandler/FileDataSource sống tới khi marshal/send xong |
| Temporary files rò rỉ | Đóng streams, giải phóng message/attachments, cleanup sau Fault |
| HTTP timeout | Connect/response/lease timeout theo SLA, overall deadline |
| Retry sau timeout | Idempotency key và reconciliation, không tự gửi lại không giới hạn |
| Nhiều concurrent uploads | Bulkhead, pool limits, rate limits, bounded queues |
| Attachment count lớn | Giới hạn số MIME parts và chỉ chấp nhận những parts hợp contract |

### MTOM nhanh hơn bao nhiêu?

MTOM thường giúp giảm overhead Base64, nhưng **không có một tỷ lệ tăng tốc cố định**. Với file nhỏ, overhead multipart/boundaries có thể khiến message không nhỏ hơn; với file lớn, lợi ích tùy provider, compression, TLS, storage I/O và proxy. Hãy đo:

~~~text
payloadBytes
httpEntityBytes
uploadElapsedMs p50 / p95 / p99
serverHeapPeakMiB
clientHeapPeakMiB
diskSpoolMiB
bytesPersisted / checksumStatus
~~~

Không chỉ so `Content-Length` của request MTOM và XML inline mà bỏ qua throughput, streaming, server memory và độ ổn định khi có concurrent uploads.

## 18. MTOM và WS-Security: bảo vệ XML không tự bảo vệ mọi bytes

MTOM/XOP là **cơ chế tối ưu biểu diễn**, không phải mã hóa hoặc ký số. Một SOAP message có `wsse:Security` không tự bảo đảm mọi attachment binary được ký:

| Cơ chế | Bảo vệ gì? | Điều cần xác minh |
| --- | --- | --- |
| TLS/mTLS | Kênh transport và peer identity theo config | Chứng chỉ, hostname, trust, client auth |
| WS-Security XML Signature | Các XML parts được chỉ định trong signature references | Bao phủ **đúng** Body/Header application tiêu thụ |
| WS-Security attachment protection/profile | Những MIME attachment parts được policy bảo vệ | Binary thực sự được ký/mã hóa, ref/digest đúng |
| MTOM/XOP | Cách truyền dữ liệu nhị phân | Không có ý nghĩa security riêng |
| Business authorization | Caller được upload/download tài liệu nào | Principal đã xác minh, quyền theo document/tenant |

### 18.1. Ký SOAP Body có bao gồm attachment?

Điều này **phụ thuộc security policy, cách ký và cách chuyển đổi XOP/XML**. Không được suy luận “Body đã ký” ⇒ “bytes MIME attachment chắc chắn được bảo vệ” nếu chưa kiểm tra rằng phần bytes tương ứng được đưa vào signature verification đúng tiêu chuẩn/profile và **không có signature wrapping**. Một số chính sách yêu cầu **attachment-specific transforms/references** và kiểm tra riêng binary parts.

Hãy kiểm tra:

1. Tất cả những phần **Body và attachments** bắt buộc có mặt trong signed/encrypted scope.
2. Các references/CIDs có được ràng buộc đúng phần dữ liệu đang được đọc không.
3. Khi sửa **một byte** trong attachment ở fixture, receiver có từ chối message theo policy không.
4. Có thể gửi attachment không được ký trong khi Body vẫn hợp lệ không? Nếu policy cấm, test phải thất bại.
5. Chữ ký còn hợp lệ khi qua proxy/transformer hoặc SOAP stack khác không.
6. Timestamp/replay protection vẫn hoạt động khi request có file lớn.

### 18.2. Thứ tự bảo mật và kiểm tra tài liệu

~~~mermaid
flowchart TD
    A["MTOM HTTP multipart request"] --> B["Transport/TLS + limits"]
    B --> C["MIME + XML parse an toàn"]
    C --> D["WS-Security verify/decrypt<br/>đúng parts theo policy"]
    D --> E["JAXB/XSD + MIME validation"]
    E --> F["Principal/authorization"]
    F --> G["File type/size/checksum/AV scan"]
    G --> H["Transaction/store + audit"]
    H --> I["SOAP response / Fault<br/>outbound security"]
~~~

Đây là **thứ tự trách nhiệm về an toàn**, không phải cam kết callback ordering bất biến của mọi Spring-WS/WSS4J version. MIME/XML parsing tối thiểu phải xảy ra trước verification, nên hardening parser và quota **phải có từ trước**. Không chuyển file vào nơi lưu trữ công khai hoặc phát side effects trước khi các kiểm tra cần thiết đạt.

### 18.3. Những lỗi an toàn thường bị bỏ sót

- **Path traversal:** dùng `filename` trực tiếp tạo đường dẫn file trên server.
- **Content-type spoofing:** tin `application/pdf` mà không kiểm tra nội dung.
- **XML External Entity:** XML parser mở external entities trong SOAP root.
- **Unbounded memory/disk usage:** gửi hàng chục GB hoặc nhiều MIME parts.
- **Zip/Decompression bombs:** tệp nén mở rộng không có quota.
- **Logging secrets:** log raw binary, toàn SOAP Header WS-Security hoặc PDF chứa PII.
- **SSRF/RFI:** fetch `href` như URL ngoài thay vì xử lý CID theo MIME/XOP policy.

Xử lý attachment không chỉ là sửa JAXB model; nó là ranh giới **nhận dữ liệu bên ngoài** và phải áp dụng những chính sách file-upload an toàn.

## 19. Chẩn đoán lỗi MTOM theo triệu chứng

| Triệu chứng | Nghi ngờ | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| `415 Unsupported Media Type` | Server không hỗ trợ `multipart/related` hoặc SOAP version sai | HTTP Content-Type, SOAP binding |
| `VersionMismatch` | SOAP 1.1/1.2 Envelope sai | Message factory/namespace |
| XML có `xop:Include` nhưng JAXB content null | CID thiếu, MIME container không được truyền tới unmarshaller | `href`, `Content-ID`, OXM processor |
| Client bật MTOM nhưng request vẫn inline | Dữ liệu nhỏ, binding hoặc MIME context không tham gia | Kích thước fixture, `setMtomEnabled`, wire capture |
| MIME có part nhưng không thấy XOP optimization | Chỉ thêm attachment thủ công, SOAP Body không tham chiếu | `MimeMessage.addAttachment` vs `xop:Include` |
| Client đọc 0 bytes | DataHandler stream đã đóng/nguồn đã tiêu thụ | Source lifecycle, logging/interceptor |
| Server ghi file sai byte count | Binary bị cắt, kích thước bị giới hạn hoặc encoding sai | So SHA-256 từng chặng |
| Server đọc được request nhưng client không đọc response | Outbound OXM không dùng MTOM-enabled processor | Response Content-Type/root MIME và JAXB |
| `ClassCastException` giữa JAXB classes | `JAXBElement`/root binding, Javax vs Jakarta | ObjectFactory/generated types |
| `SAAJ provider not found` | Thiếu SAAJ implementation/API | Dependency graph/runtime classpath |
| `PKIX/SSLHandshakeException` | Truststore, hostname hoặc mTLS sai | TLS logs/cert chain, không tắt verify |
| HTTP 502 HTML | Proxy/gateway chặn MIME size/type | Gateway logs/body-size policies |
| Signature invalid | Binary được sửa hoặc signed part không đúng | WS-Security scope, attachment policy |
| Valid Body signature nhưng attachment bị đổi vẫn chấp nhận | Attachment chưa được bảo vệ đúng yêu cầu | Signature refs/attachment validation |
| OutOfMemoryError trên file lớn | Buffering, `byte[]` hoặc logging toàn payload | Heap profile, stream/spool config |
| XML schema validator báo lỗi với `xop:Include` | Validate **serialized XOP XML** như business XML | Validate Infoset đã tái dựng, đúng pipeline |
| Content type `application/pdf` nhưng file hỏng | MIME metadata giả hoặc bytes sai | File magic/validation và SHA-256 |
| Test MockWebServiceServer pass, production fail | Mock không kiểm HTTP wire/proxy | Embedded HTTPS MIME test |

### Lưu đồ xử lý sự cố

~~~mermaid
flowchart TD
    A["Upload/download SOAP lỗi"] --> B{"HTTP(S) transport thành công?"}
    B -->|Không| C["TLS/mTLS, proxy, timeout, request size"]
    B -->|Có| D{"SOAP version và multipart Content-Type đúng?"}
    D -->|Không| E["WSDL binding, SAAJ factory, MIME headers"]
    D -->|Có| F{"XOP root và CID references hợp lệ?"}
    F -->|Không| G["Boundary/start/Content-ID/xop:Include"]
    F -->|Có| H{"JAXB/Server MIME context nhận binary?"}
    H -->|Không| I["Jaxb2Marshaller, processor, DataHandler"]
    H -->|Có| J{"SHA-256/bytes khớp?"}
    J -->|Không| K["Nguồn stream, truncation, charset, storage"]
    J -->|Có| L{"Security và authorization đạt?"}
    L -->|Không| M["Signature/attachment policy, trust, access"]
    L -->|Có| N["Kiểm response/Fault và chiều ngược lại"]
~~~

Lưu đồ chỉ là **thứ tự chẩn đoán**, không phải thứ tự xác minh security thực tế của service. Khi request chưa đáng tin, không cần trả cho client từng chi tiết nội bộ về attachment parser hoặc certificate trust.

## 20. Bài thực hành tự đánh giá

### Bài 1 — Chứng minh optimization trên dây

Tạo một `UploadDocumentRequest` mang file nhị phân 1 MiB, bật MTOM trên client và server. Dùng HTTP test server capture request, tìm `multipart/related`, root `application/xop+xml`, `xop:Include href="cid:..."` và binary MIME part. Tính SHA-256 trước khi gửi và sau khi server lưu.

### Bài 2 — Inline Base64 so với MTOM

Gửi cùng file 16 B và 1 MiB với MTOM enabled/disabled. Đối chiếu `HTTP entity bytes`, Content-Type, thời gian và heap; giải thích vì sao MTOM enabled không bắt buộc tạo MIME part với file nhỏ.

### Bài 3 — Test response MTOM

Xây `DownloadDocumentResponse` chứa `xs:base64Binary`. Xác minh endpoint sử dụng **output marshaller/return-value handler có MTOM enabled**, bắt raw HTTP response, sau đó dùng client JAXB khác đọc và so checksum. Giải thích tại sao test chỉ assert DTO trả về chưa đủ.

### Bài 4 — JAXB DataHandler và nguồn stream

Dùng `DataHandler` từ `FileDataSource`, gửi file và sau đó thử đóng/xóa file nguồn trước bước marshal. Quan sát lỗi; thiết kế lifecycle đúng, không lưu tất cả bytes trong RAM.

### Bài 5 — CID missing/duplicate

Tạo fixture MIME có `xop:Include` trỏ tới CID không tồn tại, rồi fixture có duplicate Content-ID. Dùng HTTP integration test xác nhận server không ghi file và trả lỗi đúng tầng.

### Bài 6 — SOAP 1.1/1.2

Cấu hình hai binding riêng. Kiểm tra Envelope namespace, root media type và SOAPAction/action; thử gửi SOAP 1.1 MTOM request đến endpoint chỉ nhận SOAP 1.2 và phân loại lỗi.

### Bài 7 — WS-Security attachment protection

Ký message/attachments theo policy có kiểm soát. Sửa một byte trong binary MIME part nhưng giữ SOAP Body không đổi. Xác nhận receiver từ chối nếu chính sách yêu cầu bảo vệ attachment; giải thích vì sao “Body XML signature valid” chưa đủ.

### Bài 8 — Cross-platform interoperability

Cho Spring-WS client gửi file tới .NET/WCF hoặc ESB test endpoint, sau đó đổi vai trò: client khác gửi tới Spring-WS server. Assert cùng bytes, đúng QName và MIME packaging. Đối chiếu config MTOM optional/required của mỗi stack.

### Bài 9 — Tải đồng thời

Gửi 50 uploads song song với kích thước 20 MiB theo quota phòng thử nghiệm. Theo dõi peak heap, spool disk, connection pool, p95 latency và tỷ lệ checksum success. Nếu có OOM, điều tra buffers/byte[]/logging trước khi kết luận MTOM không hiệu quả.

### Bài 10 — Threat modeling file upload

Đối tác gửi `filename="../../config.yml"`, `Content-Type=application/pdf` nhưng bytes là tệp thực thi, attachment nặng hơn giới hạn, và `xop:Include` trỏ URI HTTP. Thiết kế lớp kiểm soát filename, content validation, CID-only resolver, quotas, authorization và cách trả SOAP Fault an toàn.

## 21. Checklist kiểm chứng tương thích MTOM

| Nhóm | Điều kiện chấp nhận |
| --- | --- |
| **Contract-first** | WSDL/XSD toàn vẹn, root QName đúng; binary là `xs:base64Binary` và media type theo policy |
| **MTOM policy** | Required/optional, giới hạn kích thước và behavior fallback được công bố |
| **SOAP version** | SOAP 1.1/1.2, Content-Type, Envelope namespace và binding thống nhất |
| **JAXB/OXM** | `Jaxb2Marshaller#setMtomEnabled(true)`; DataHandler/byte[] mapping phù hợp; Javax/Jakarta nhất quán |
| **Server adapter** | Endpoint dùng đúng resolver/return handler cho MTOM; không chỉ khai báo một bean chưa được dùng |
| **Client** | WebServiceTemplate, SAAJ factory, sender, SOAPAction/WS-A và TLS cấu hình đúng |
| **MIME wire** | `multipart/related`, `application/xop+xml`, root CID và boundary hợp lệ |
| **CID linkage** | Mỗi `xop:Include` resolve đúng binary part, không missing/ambiguous |
| **Data integrity** | Byte count và SHA-256 nguồn/server/client khớp |
| **Hai chiều** | Test upload và download (nếu contract hỗ trợ), cả success lẫn SOAP Fault |
| **Cross-platform** | Ít nhất một client/server khác stack khi có đối tác .NET/ESB |
| **Streaming/resources** | Quotas, memory/disk peak, cleanup, stream lifetime, timeout/concurrency |
| **Security** | TLS/mTLS, WS-Security đúng signed parts/attachments, authorization và file validation |
| **Negative tests** | Missing CID, bad boundary, oversized attachment, wrong type, invalid signature, invalid SOAP version |
| **Quan sát** | Log/metrics có lọc, không dump raw binary/token/PII, có correlation ID |

## 22. Tài liệu tham khảo và chuẩn chính thức

- [Spring Web Services Reference 4.1.4 — MTOM](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): mục `5.2.7 MTOM` và các API SOAP/message factory.
- [Spring Web Services — MimeMessage API](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/mime/MimeMessage.html): `addAttachment`, `getAttachment(s)`, `isXopPackage`, `convertToXopPackage`.
- [Spring Framework — Jaxb2Marshaller](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html): `setMtomEnabled` và overloads dùng MIME container.
- [Spring Framework — MimeMarshaller và MimeUnmarshaller](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/oxm/mime/MimeMarshaller.html): vai trò của MIME container khi marshal/unmarshal.
- [Jakarta XML Binding — XmlMimeType](https://jakarta.ee/specifications/xml-binding/4.0/apidocs/jakarta.xml.bind/jakarta/xml/bind/annotation/xmlmimetype): metadata MIME type của JAXB property.
- [W3C — SOAP Message Transmission Optimization Mechanism](https://www.w3.org/TR/soap12-mtom/): cơ chế tối ưu và HTTP MIME package.
- [W3C — XML-binary Optimized Packaging](https://www.w3.org/TR/xop10/): `xop:Include` và quy tắc XOP packages.
- [W3C — MTOM Serialization Policy Assertion 1.1](https://www.w3.org/TR/soap12-mtom-policy/): cách công bố MTOM required/optional.

**Kết luận:** **Kiểm chứng tương thích MTOM** là chứng minh **XML Infoset đúng hợp đồng, MIME/XOP packaging hợp lệ và dữ liệu nhị phân nguyên vẹn ở cả hai phía**. Trong **SPRING_WEB_SERVICES**, cần phối hợp `Jaxb2Marshaller`, SAAJ/`MimeMessage`, endpoint/client adapters và HTTP sender, nhưng **bật `mtomEnabled` không tự chứng minh wire-level optimization**. Một bộ test đáng tin gồm OXM/JAXB, SOAP message, HTTP multipart thật, checksum/byte-count end-to-end, request/response hai chiều, negative tests và kiểm thử WS-Security/TLS/giới hạn tài nguyên. Khi các phép kiểm này đạt trên đúng WSDL binding và SOAP version của đối tác, MTOM mới thực sự là một cách truyền tệp ổn định, tương thích và an toàn thay vì một cờ cấu hình.
