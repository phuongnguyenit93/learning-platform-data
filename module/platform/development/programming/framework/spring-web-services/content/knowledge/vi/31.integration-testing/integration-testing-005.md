# Trao đổi MTOM và xác nhận toàn vẹn dữ liệu nhị phân

## 1. Bài toán: SOAP gửi file lớn mà không phải biến toàn bộ thành Base64

Một hệ thống quản lý hồ sơ dùng SOAP để nhận tài liệu từ đối tác. Request chứa metadata như mã hồ sơ, tên file, loại tài liệu và một file PDF 18 MB. Contract-first XSD mô tả file bằng `xs:base64Binary`, JAXB sinh model Java, Spring-WS nhận request qua HTTP.

Nếu serialize toàn bộ bytes thành Base64 nằm trực tiếp trong SOAP Body, dung lượng biểu diễn tăng xấp xỉ một phần ba, đồng thời XML parser/JAXB có thể phải giữ chuỗi lớn trong bộ nhớ. MTOM (Message Transmission Optimization Mechanism) cùng XOP (XML-binary Optimized Packaging) cho phép đóng gói phần binary thành MIME part riêng và thay nội dung Base64 trong XML bằng `xop:Include` tham chiếu theo Content-ID.

Tuy nhiên, “nhìn thấy MIME attachment” chưa chứng minh server đã nhận đủ file hoặc file nhận được giống file gửi. Một kiểm thử tích hợp đúng phải kiểm tra cả **SOAP contract, MIME packaging, bytes thực nhận và tính toàn vẹn**.

Bài học thuộc chương **Kiểm thử tích hợp** của module `SPRING_WEB_SERVICES`, tập trung vào dịch vụ SOAP contract-first với XSD/WSDL, JAXB, Spring-WS endpoint/client, XML security và kiểm thử tương thích.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Base64 inline, SOAP with Attachments và MTOM/XOP.
2. Đọc một XOP package gồm SOAP XML root part và binary MIME parts.
3. Thiết kế XSD `xs:base64Binary` với `xmime:expectedContentTypes`.
4. Ánh xạ binary data sang `DataHandler`/`byte[]` trong JAXB và hiểu vai trò `@XmlMimeType`.
5. Cấu hình Spring-WS client/server để trao đổi MTOM theo đúng message factory, marshaller và SOAP version.
6. Viết test round-trip kiểm tra length, SHA-256, content type và metadata.
7. Kiểm tra attachment thiếu, Content-ID sai, trùng CID, MIME type sai, nội dung bị cắt và payload vượt giới hạn.
8. Phân biệt integrity của bytes, XML Signature/WS-Security, TLS và checksum nghiệp vụ.
9. Đánh giá streaming, memory/disk caching, kích thước tối ưu hóa và interoperability với SOAP stacks khác nền tảng.

## 2. Phân biệt Base64 inline, SwA và MTOM/XOP

### 2.1. Base64 inline trong SOAP Body

Với cách truyền thông thường, XSD `xs:base64Binary` được marshal thành nội dung Base64:

```xml
<doc:UploadDocumentRequest
    xmlns:doc="urn:example:documents:v1">
    <doc:documentId>DOC-100</doc:documentId>
    <doc:fileName>contract.pdf</doc:fileName>
    <doc:contentType>application/pdf</doc:contentType>
    <doc:content>JVBERi0xLjQKJc...</doc:content>
</doc:UploadDocumentRequest>
```

Ưu điểm là message chỉ có XML; schema validation và JAXB mapping đơn giản. Nhược điểm:

- Base64 có thêm khoảng một phần ba ký tự so với dữ liệu nhị phân gốc, chưa tính whitespace/markup.
- DOM, String và JAXB object có thể giữ nhiều bản sao dữ liệu.
- Log payload có thể làm lộ toàn bộ file và tiêu tốn dung lượng.
- Với file lớn, CPU/memory pressure tăng đáng kể.

### 2.2. SOAP with Attachments (SwA)

SwA đóng gói SOAP root document và attachment thành MIME `multipart/related`. Body XML có thể tham chiếu attachment bằng Content-ID hoặc cơ chế profile liên quan. Attachment tồn tại như MIME part độc lập với nội dung SOAP Body.

SwA và MTOM không đồng nhất. MTOM dùng quy ước XOP để biểu diễn một XML Infoset tương đương với nội dung Base64 trong SOAP payload, giúp các stack SOAP hiểu được dữ liệu binary như một phần của XML contract.

### 2.3. MTOM/XOP

Với MTOM, XML element có content `xs:base64Binary` được tối ưu bằng cách thay phần text Base64 bằng `xop:Include`:

```xml
<doc:UploadDocumentRequest
    xmlns:doc="urn:example:documents:v1"
    xmlns:xop="http://www.w3.org/2004/08/xop/include">
    <doc:documentId>DOC-100</doc:documentId>
    <doc:fileName>contract.pdf</doc:fileName>
    <doc:contentType>application/pdf</doc:contentType>
    <doc:content>
        <xop:Include href="cid:part-100@example.org"/>
    </doc:content>
</doc:UploadDocumentRequest>
```

MIME package có root part chứa XOP XML và một part khác chứa bytes:

```text
Content-Type: multipart/related;
  type="application/xop+xml";
  start="<root@example.org>";
  start-info="application/soap+xml";
  boundary="----soap-boundary"

------soap-boundary
Content-Type: application/xop+xml; charset=UTF-8;
  type="application/soap+xml"
Content-Transfer-Encoding: 8bit
Content-ID: <root@example.org>

... SOAP Envelope với xop:Include ...

------soap-boundary
Content-Type: application/pdf
Content-Transfer-Encoding: binary
Content-ID: <part-100@example.org>

[các octets gốc của contract.pdf]

------soap-boundary--
```

Đây là sơ đồ MIME minh họa. Boundary, Content-ID, thứ tự part, header parameters và SOAP version thực tế được message stack tạo; không hard-code boundary hoặc trông chờ attachment luôn đứng sau root part.

Trong ví dụ package phía trên, `start-info="application/soap+xml"` minh họa SOAP 1.2. Với SOAP 1.1, root XOP part thường khai báo type/start-info tương ứng `text/xml`; không copy Content-Type của SOAP 1.2 sang SOAP 1.1.

### 2.4. Mối quan hệ giữa XOP package và XML Infoset

XOP package là một cách serialize tối ưu của XML Infoset. Khi diễn giải lại, `xop:Include` được thay bằng nội dung Base64 tương ứng của MIME part. Vì vậy client/server vẫn nhìn thấy cùng contract XML ở mức khái niệm.

Một số hệ quả:

- XOP chỉ tối ưu element content tương ứng binary Base64; không tối ưu tùy tiện attribute hoặc văn bản thường.
- Nội dung cần tối ưu phải ở dạng lexical canonical của `xs:base64Binary` theo quy tắc XOP.
- `xop:Include/@href` trỏ đến part theo URI, thường có dạng `cid:...`.
- Content-ID trong `xop:Include` và MIME `Content-ID` phải khớp theo quy tắc URI/Content-ID của package.
- XOP không đổi XSD type của field từ `base64Binary` thành một URL nghiệp vụ.

### 2.5. So sánh nhanh

| Cách truyền | Binary nằm ở đâu? | XML Body | Khi phù hợp |
| --- | --- | --- | --- |
| Base64 inline | Text Base64 trong XML | Có đầy đủ Base64 | File nhỏ, tương thích đơn giản |
| SwA | MIME attachment riêng | Có thể tham chiếu attachment theo profile | Hệ thống legacy dùng SOAP with Attachments |
| MTOM/XOP | MIME part riêng, được `xop:Include` tham chiếu | XML Infoset tương đương Base64 | Contract `base64Binary`, payload nhị phân lớn |

Không chọn MTOM chỉ vì file có đuôi PDF. Quyết định phụ thuộc kích thước, SOAP stack, contract và mức hỗ trợ của đối tác.

## 3. Contract-first XSD cho binary content

### 3.1. Khai báo `xs:base64Binary`

Một schema mẫu cho upload tài liệu:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:doc="urn:example:documents:v1"
    xmlns:xmime="http://www.w3.org/2005/05/xmlmime"
    targetNamespace="urn:example:documents:v1"
    elementFormDefault="qualified">

    <xs:import
        namespace="http://www.w3.org/2005/05/xmlmime"
        schemaLocation="http://www.w3.org/2005/05/xmlmime"/>

    <xs:element name="UploadDocumentRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="documentId" type="xs:string"/>
                <xs:element name="fileName" type="xs:string"/>
                <xs:element name="content"
                            xmime:expectedContentTypes="application/pdf">
                    <xs:complexType>
                        <xs:simpleContent>
                            <xs:extension base="xs:base64Binary">
                                <xs:attribute
                                    ref="xmime:contentType"
                                    use="optional"/>
                            </xs:extension>
                        </xs:simpleContent>
                    </xs:complexType>
                </xs:element>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

</xs:schema>
```

Schema ví dụ dùng `xmime:contentType` để mô tả media type thực tế. Trong dự án, pin XSD XML MIME tại nguồn đã được quản lý/review; tránh để build hoặc production phụ thuộc một URL ngoài không kiểm soát.

### 3.2. xmime:expectedContentTypes

Để JAXB/XJC biết binary field có MIME type dự kiến, schema có thể khai báo annotation:

```xml
<xs:element name="content"
            type="xs:base64Binary"
            xmime:expectedContentTypes="application/pdf"/>
```

Namespace XML MIME thường dùng là `http://www.w3.org/2005/05/xmlmime`.

Phân biệt:

- `xmime:expectedContentTypes`: gợi ý media type mong đợi cho binding/tooling.
- `xmime:contentType`: mô tả content type của binary value cụ thể khi dùng theo schema pattern phù hợp.
- MIME part `Content-Type`: header thực tế của attachment trong package.

Ba nơi này phải thống nhất theo hợp đồng. Không tin `Content-Type` client gửi như một bằng chứng file thực sự là PDF; kiểm tra nội dung file bằng parser/scanner phù hợp.

### 3.3. Binding được sinh có thể phụ thuộc expected media type

JAXB binding có thể ánh xạ `xs:base64Binary` sang:

- `byte[]` khi xử lý như dữ liệu nhị phân trực tiếp.
- `DataHandler` khi dùng media type linh hoạt hoặc attachment-friendly binding.
- `Image`/`Source` với một số media type cụ thể và binding tương ứng.

Kiểu Java thực tế phụ thuộc XSD annotation, XJC binding customization và JAXB implementation/toolchain. Không đoán từ field name; đọc generated source và verify runtime.

### 3.4. Ví dụ XSD với MIME type không cố định

Nếu service nhận nhiều loại file, có thể cho phép một tập MIME type dự kiến hoặc wildcard theo contract:

```xml
<xs:element name="content"
            type="xs:base64Binary"
            xmime:expectedContentTypes="application/pdf, image/jpeg, image/png"/>
```

Trong trường hợp media type chưa cố định, JAXB thường có thể bind sang `DataHandler`; ứng dụng cần kiểm tra `DataHandler.getContentType()` và nội dung thực tế. Contract nên quy định rõ danh sách media type được chấp nhận, kích thước tối đa và xử lý các type không biết.

### 3.5. Đừng biến Content-ID thành định danh file nghiệp vụ

Content-ID chỉ là định danh part bên trong MIME package. Nó không phải document ID, tên file, checksum, quyền truy cập hay URL tải file dài hạn. Dùng `documentId` hoặc business request ID trong payload; dùng CID chỉ để liên kết `xop:Include` với MIME part tương ứng.

## 4. JAXB mapping: DataHandler, byte[] và annotation

### 4.1. Mapping sang `DataHandler`

Với file có thể lớn, `DataHandler` thường thuận tiện vì làm việc với `DataSource`/stream thay vì buộc business API chỉ nhận một mảng bytes đã materialize.

Ví dụ JAXB model:

```java
import jakarta.activation.DataHandler;
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlMimeType;
import jakarta.xml.bind.annotation.XmlType;

@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "DocumentContentType")
public class DocumentContent {

    @XmlMimeType("application/pdf")
    private DataHandler content;

    public DataHandler getContent() {
        return content;
    }

    public void setContent(DataHandler content) {
        this.content = content;
    }
}
```

Ví dụ Jakarta JAXB 3/4. Nếu dự án dùng JAXB 2.x, annotation và activation dependencies thuộc namespace `javax.*`; không trộn `javax.xml.bind` với `jakarta.xml.bind` hoặc `javax.activation` với `jakarta.activation` trong cùng binding runtime.

### 4.2. Tạo DataHandler từ file

```java
import jakarta.activation.DataHandler;
import jakarta.activation.FileDataSource;
import java.nio.file.Path;

Path file = Path.of("fixtures/contract.pdf");
DataHandler handler =
    new DataHandler(new FileDataSource(file.toFile()));

DocumentContent document = new DocumentContent();
document.setContent(handler);
```

`FileDataSource` cung cấp bytes khi marshaller đọc stream. Không mở file rồi đọc toàn bộ vào `byte[]` chỉ để tạo `DataHandler`; làm vậy có thể triệt tiêu lợi ích streaming.

### 4.3. Mapping sang `byte[]`

```java
import jakarta.xml.bind.annotation.XmlMimeType;

public class SmallImage {

    @XmlMimeType("image/png")
    private byte[] content;

    public byte[] getContent() {
        return content;
    }

    public void setContent(byte[] content) {
        this.content = content;
    }
}
```

`byte[]` dễ assert trong unit test, nhưng JAXB/application giữ toàn bộ dữ liệu trong heap. Với payload vài chục MB hoặc nhiều request song song, cần tính tổng heap, số bản sao và concurrency.

### 4.4. XmlInlineBinaryData

JAXB có annotation `@XmlInlineBinaryData` để yêu cầu dữ liệu binary được inline thay vì tối ưu bằng attachment trong các trường hợp binding hỗ trợ MTOM. Khi áp dụng, phải hiểu annotation có thể làm thay đổi cách marshalling field đó; đừng gắn annotation này vào mọi binary field một cách máy móc.

### 4.5. DataHandler không tự chứng minh integrity

`DataHandler` là abstraction cho data source/content handler. Nó không tự tính SHA-256, xác minh kích thước theo metadata, đảm bảo file không bị thay đổi giữa lúc scan và lúc lưu, chống virus hoặc xác nhận file type thực.

Integrity cần được kiểm tra ở application boundary bằng digest/length hoặc chữ ký theo contract. Security và business validation là các bước riêng.

## 5. Cấu hình MTOM trong Spring-WS

### 5.1. Bật MTOM ở JAXB marshaller

Spring Framework class `Jaxb2Marshaller` có thuộc tính `mtomEnabled`; mặc định là `false`. Một cấu hình Java-based minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class SoapBinaryConfiguration {

    @Bean
    public Jaxb2Marshaller documentMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setPackagesToScan(
            "com.example.documents.schema"
        );
        marshaller.setMtomEnabled(true);
        return marshaller;
    }
}
```

Đoạn cấu hình nạp generated JAXB model trong package. Trong dự án thực tế, cấu hình package/context path, schema resources, adapters và validation theo contract đang triển khai.

### 5.2. Dùng marshaller ở SOAP client

```java
import org.springframework.context.annotation.Bean;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Bean
public SaajSoapMessageFactory soapMessageFactory() {
    return new SaajSoapMessageFactory();
}

@Bean
public WebServiceTemplate documentWebServiceTemplate(
        SaajSoapMessageFactory soapMessageFactory,
        Jaxb2Marshaller documentMarshaller) {

    WebServiceTemplate template =
        new WebServiceTemplate(soapMessageFactory);
    template.setMarshaller(documentMarshaller);
    template.setUnmarshaller(documentMarshaller);
    template.setDefaultUri(
        "https://partner.example.org/ws/documents"
    );
    return template;
}
```

Endpoint URL là ví dụ minh họa. Ứng dụng thực phải cấu hình TLS, timeouts, connection pooling, authentication, WSDL binding và endpoint theo môi trường.

### 5.3. Server endpoint dùng JAXB payload

```java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class DocumentEndpoint {

    private final DocumentService documentService;

    public DocumentEndpoint(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PayloadRoot(
        namespace = "urn:example:documents:v1",
        localPart = "UploadDocumentRequest"
    )
    @ResponsePayload
    public UploadDocumentResponse upload(
            @RequestPayload UploadDocumentRequest request) {
        return documentService.store(request);
    }
}
```

`DocumentService` cần xử lý stream/attachment, giới hạn kích thước và kiểm tra digest trước khi commit. Không nên để endpoint tự đọc toàn bộ bytes vào heap rồi mới gọi service nếu file lớn.

### 5.4. SAAJ và AXIOM là message factory, không phải một toggle MTOM duy nhất

Spring-WS cung cấp các SOAP message factory chính:

| Factory | Mô hình | Cân nhắc với file lớn |
| --- | --- | --- |
| `SaajSoapMessageFactory` | SAAJ/DOM; message có thể được giữ trong memory | Dễ tích hợp SAAJ attachment APIs, nhưng kiểm tra memory behavior |
| `AxiomSoapMessageFactory` | AXIOM/StAX; pull-based XML processing | Có thể phù hợp payload lớn/streaming hơn nếu đường đi của ứng dụng giữ streaming |

Không thể kết luận toàn hệ thống streaming chỉ vì dùng AXIOM. Endpoint, JAXB mapping, interceptor, validation, logging và business layer đều có thể materialize bytes hoặc SOAP Body.

### 5.5. Attachment API trên SoapMessage

`SoapMessage` kế thừa MIME message abstraction. Với SAAJ implementation, `SaajSoapMessage` có các thao tác như `addAttachment(contentId, DataHandler)`, `getAttachment(contentId)`, `getAttachments()` và `convertToXopPackage()`.

API SOAP message-level phù hợp khi cần thao tác attachment thủ công. Khi dùng JAXB/MTOM end-to-end, nên ưu tiên marshalling integration để model và MIME package được kết nối tự động. Tránh vừa tự tạo attachment vừa bật JAXB MTOM trên cùng field nếu không có một thiết kế rõ ràng; rất dễ tạo duplicate parts hoặc CID không khớp.

### 5.6. WSDL/XSD và capability của partner

XSD có thể khai báo `base64Binary`/XML MIME annotations, nhưng không phải mọi SOAP client đều tự bật MTOM. Hai bên cần đồng thuận:

- Có chấp nhận MTOM/XOP không?
- Dùng SOAP 1.1 hay SOAP 1.2?
- MIME content type/profile và attachment media types nào?
- Kích thước tối đa và threshold tối ưu hóa?
- Có fallback Base64 inline không?
- WS-Security ký/mã hóa binary part theo profile nào?

Một client không hỗ trợ MTOM có thể cần nhận Base64 inline; một số client có thể từ chối `multipart/related` dù XSD payload đúng. Phải test với stack thật của đối tác.

## 6. Thiết kế kiểm tra tính toàn vẹn dữ liệu nhị phân

### 6.1. Ba phép kiểm tra cơ bản

Ít nhất hãy xác nhận:

1. **Length:** số bytes nhận được bằng số bytes đã gửi.
2. **Digest:** SHA-256 của bytes nhận bằng digest của file gốc.
3. **Content metadata:** document ID, media type và tên file/metadata khớp request contract.

Length một mình không đủ: hai file khác nhau có thể có cùng độ dài. Content-Type một mình không đủ: client có thể khai báo `application/pdf` cho bất kỳ bytes nào.

### 6.2. Tính SHA-256 khi đọc stream

Có thể copy stream trong khi tính digest mà không giữ toàn bộ file trong heap:

```java
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public record BinaryDigest(long length, String sha256) {}

public final class BinaryIntegrity {

    private BinaryIntegrity() {}

    public static BinaryDigest digest(InputStream input)
            throws IOException {
        final MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 is unavailable", ex
            );
        }

        byte[] buffer = new byte[64 * 1024];
        long total = 0;
        int read;

        while ((read = input.read(buffer)) != -1) {
            digest.update(buffer, 0, read);
            total = Math.addExact(total, read);
        }

        return new BinaryDigest(
            total,
            HexFormat.of().formatHex(digest.digest())
        );
    }
}
```

Hàm tiêu thụ stream từ vị trí hiện tại tới EOF. Caller phải quản lý lifecycle/close stream bằng try-with-resources; nếu cần digest rồi đọc lại file, mở một stream mới hoặc lưu file vào staging storage.

### 6.3. Hash trước khi gửi và sau khi nhận

```text
Fixture file bytes
   |
   +--> SHA-256(source), length(source)
   |
   v
JAXB DataHandler / MTOM marshal
   |
   v
multipart/related over HTTP
   |
   v
SOAP message factory + XOP reconstruction
   |
   v
DataHandler at server endpoint
   |
   +--> SHA-256(received), length(received)
   |
   v
assert source == received
```

Khi digest không khớp, không lưu tài liệu thành bản chính thức. Ghi trạng thái lỗi có correlation ID, đóng/deallocate attachment resources và áp retention phù hợp cho staging file.

### 6.4. Không dùng hash tự tính từ Content-ID

CID chỉ trỏ đến MIME part. Nó không chứa digest và cũng không đảm bảo attachment tương ứng đúng với document ID. Nếu contract cần checksum, khai báo digest field riêng, ví dụ SHA-256 hex hoặc Base64 binary digest, và định nghĩa chính xác:

- Thuật toán (ví dụ SHA-256).
- Digest áp dụng lên đúng octets nào (bytes gốc sau khi giải mã MIME transfer encoding, trước khi unzip/decompress).
- Representation (hex lowercase hay Base64).
- Có canonicalization/transform nào không.
- Metadata digest có nằm trong WS-Security signed SOAP Body hay không.

### 6.5. Digest không thay thế digital signature

Nếu cả digest và file đi qua cùng một kênh mà attacker có thể sửa cả hai, so sánh digest không chứng minh nguồn gửi. Cần xác thực sender và bảo vệ integrity trên metadata digest bằng WS-Security/XML Signature, chữ ký detached hoặc một kênh trusted phù hợp.

TLS bảo vệ channel/hop trong lúc truyền; nó không thay thế application-level digest khi file được lưu, xử lý hoặc chuyển tiếp sau khi kết nối kết thúc.

## 7. Test MTOM ở nhiều tầng

Một test dùng JAXB object không chứng minh MIME package đúng; một test thấy `multipart/related` cũng không chứng minh bytes được tái tạo chính xác. Chia kiểm thử theo tầng.

### 7.1. Unit test digest implementation

Kiểm tra hàm SHA-256 với một fixture deterministic:

```java
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BinaryIntegrityTest {

    @Test
    void calculatesExpectedLengthAndSha256() throws Exception {
        byte[] bytes = "MTOM-integrity-fixture"
            .getBytes(StandardCharsets.UTF_8);

        BinaryDigest result = BinaryIntegrity.digest(
            new ByteArrayInputStream(bytes)
        );

        assertEquals(bytes.length, result.length());
        assertEquals(
            "e5ede7dea72468478a5fb0b09e289ccba8cfd9ecb1f668be4413bedb1490f617",
            result.sha256()
        );
    }
}
```

Expected digest phía trên được tính từ chính chuỗi UTF-8 `MTOM-integrity-fixture`. Không tạo expected digest bằng cách gọi chính hàm đang test; như vậy test sẽ lặp cùng lỗi implementation.

### 7.2. Test JAXB marshal/unmarshal với DataHandler

Tạo binary fixture và `DataHandler`, marshal/unmarshal bằng `Jaxb2Marshaller` đã bật MTOM. Test cần xác nhận:

- JAXB context nhận đúng class/property.
- Content type giữ đúng giá trị dự kiến.
- `DataHandler` có thể mở stream sau unmarshal.
- Bytes đọc ra có length và SHA-256 giống fixture.
- Không tự giả định JAXB object round-trip đồng nghĩa package được gửi qua HTTP.

Ví dụ kiểm tra DataHandler sau khi đã unmarshal:

```java
try (InputStream received =
        unmarshalled.getContent().getInputStream()) {
    BinaryDigest actual = BinaryIntegrity.digest(received);
    assertEquals(expectedLength, actual.length());
    assertEquals(expectedSha256, actual.sha256());
}
```

### 7.3. Kiểm tra SOAP MIME package thực tế

Với test sender/receiver thật hoặc transport capture, xác minh:

1. Top-level `Content-Type` là `multipart/related` khi message được tối ưu MTOM.
2. `type`/`start-info` parameters phù hợp SOAP 1.1/1.2 và MTOM profile.
3. Root part có media type XOP/XML tương ứng.
4. SOAP XML có `xop:Include` đúng namespace.
5. `href="cid:..."` tham chiếu đến một MIME Content-ID tồn tại.
6. Attachment `Content-Type` tương ứng file metadata/contract.
7. Attachment body bytes có length/digest đúng.

Đừng assert boundary hoặc Content-ID cụ thể do runtime tự sinh. Assert quan hệ tham chiếu và cấu trúc theo MIME parser, không regex toàn bộ raw HTTP body.

### 7.4. Kiểm tra response từ server

Phía server nên ghi kết quả của processing pipeline:

```text
received documentId
received media type
received byte length
computed SHA-256
virus/content scan result
persisted object identifier
response status
```

Endpoint chỉ trả trạng thái thành công sau khi đã đọc đủ stream, xác nhận digest/length, kiểm tra nội dung và hoàn thành bước lưu bền vững theo transaction policy.

### 7.5. Test round-trip với HTTP server đang chạy

`MockWebServiceServer` phù hợp để test client marshalling/request matcher, nhưng nó không chứng minh multipart bytes qua socket/container thật. Với integration test:

- Khởi động Spring-WS server trên HTTP port test (hoặc môi trường container dành riêng).
- Nạp cùng SOAP message factory, JAXB marshaller và endpoint configuration như deployment.
- Dùng `WebServiceTemplate` thật gửi fixture binary qua HTTP.
- Server đọc attachment và ghi kết quả digest/length vào test probe hoặc test persistence.
- Client assert response SOAP payload và server assert digest/length.
- Dừng server/transport resources sau test.

Nếu hệ thống dùng proxy, API gateway hoặc TLS termination, cần thêm deployment-like test để xác minh intermediary không làm thay đổi MIME package.

### 7.6. Ví dụ endpoint/service kiểm tra integrity

Một service có thể đọc stream một lần, tính digest rồi đưa nội dung vào staging storage:

```java
import jakarta.activation.DataHandler;
import java.io.InputStream;

public StoredDocument store(UploadDocumentRequest request)
        throws Exception {

    DataHandler handler = request.getContent();
    if (handler == null) {
        throw new InvalidDocumentException("Missing attachment");
    }

    String contentType = handler.getContentType();
    validateAllowedMediaType(contentType);

    try (InputStream input = handler.getInputStream()) {
        StagedBlob staged = stagingStore.copyAndDigest(input);

        if (staged.length() > MAX_DOCUMENT_BYTES) {
            stagingStore.delete(staged.id());
            throw new DocumentTooLargeException();
        }

        verifyExpectedLength(request, staged.length());
        verifyExpectedDigest(request, staged.sha256());
        contentScanner.scan(staged.id(), contentType);

        return documentRepository.commit(
            request.getDocumentId(),
            staged,
            contentType
        );
    }
}
```

Các service/exception/storage methods là application abstractions minh họa. Trong thực tế cần xác định rollback/cleanup khi checksum mismatch, scanner fail hoặc database commit thất bại. Không tạo trạng thái “uploaded” trước khi bytes được xác nhận và lưu bền vững.

### 7.7. Đừng đọc stream hai lần mà không rewind

`DataHandler.getInputStream()` thường cung cấp stream mới từ DataSource, nhưng không nên dựa vào điều đó với mọi custom DataSource. Nếu scanner, digest và storage đều cần đọc bytes:

- Copy stream vào staging object một lần và tính digest trong lúc copy.
- Cho scanner đọc staging object đã ghi.
- Chỉ commit/reference object sau khi scan pass.
- Xóa staging object nếu bất kỳ bước nào thất bại.

Với file quá lớn để staging trên disk, thiết kế streaming pipeline có backpressure và giới hạn bytes rõ.

## 8. Negative tests và interoperability

### 8.1. Attachment bị thiếu

Tạo XOP root part có `xop:Include href="cid:missing@example.org"` nhưng không có MIME part tương ứng. Kỳ vọng message/package bị reject ở tầng MIME/XOP processing hoặc attachment resolution. Không gọi business service và không tạo document record.

### 8.2. Content-ID sai hoặc không khớp

Root part trỏ tới `cid:part-a@example.org`, MIME part lại có Content-ID `part-b@example.org`. Kỳ vọng resolver không được trả nhầm attachment khác; lỗi phải được log theo correlation ID, không ghi raw binary.

### 8.3. Duplicate Content-ID

Một package có nhiều MIME parts cùng Content-ID. Kết quả phải là reject theo parser/package rules; không để implementation chọn ngẫu nhiên một part. Test với đúng MIME parser/provider của production vì behavior duplicate identifiers có thể khác.

### 8.4. Attachment bị cắt hoặc lỗi stream

Gửi MIME part ngắn hơn độ dài đã khai báo/được mong đợi hoặc làm input stream ném IOException giữa chừng. Kỳ vọng:

- Không commit document.
- Digest/length không được coi là pass.
- Temporary files/streams được đóng và cleanup.
- SOAP Fault/transport error được phân loại phù hợp.
- Client không retry một side-effect command mù nếu outcome chưa xác định.

### 8.5. MIME type sai

Client khai `application/pdf` nhưng gửi bytes PNG, ZIP hoặc nội dung tùy ý. Server không được chỉ dựa `Content-Type` header để nhận diện. Kiểm tra file signature/parser thực tế, allowlist type và scanner policy.

### 8.6. Binary data rỗng

Một attachment 0 byte có hợp lệ hay không phải do business contract quy định. Test riêng:

- Element absent.
- `xsi:nil`.
- Empty Base64/binary part 0 bytes.
- Attachment part tồn tại nhưng rỗng.

Không tự coi bốn trạng thái này là tương đương.

### 8.7. Payload vượt quota

Test kích thước:

- Ngay dưới giới hạn.
- Bằng giới hạn.
- Vượt giới hạn một byte.
- Nhiều attachment cùng request khiến tổng package vượt giới hạn.
- MIME headers/parts quá nhiều dù mỗi attachment nhỏ.

Giới hạn ở reverse proxy, servlet/container, SOAP parser, attachment cache, application stream và storage phải tương thích nhau. Nếu proxy giới hạn thấp hơn app, server có thể không nhận được SOAP Fault để trả về.

### 8.8. MIME part không được tham chiếu

Package có attachment thừa không xuất hiện trong `xop:Include`. Theo policy/profile, reject hoặc bỏ qua có kiểm soát; không tự lưu mọi part vào business storage chỉ vì nó có trong multipart. Giới hạn tổng số part và tổng bytes để tránh resource exhaustion.

### 8.9. Content-ID injection và URI handling

Không dùng CID làm filesystem path hoặc truy cập URL tự do. CID chỉ là identifier trong package. Không mở network connection hoặc truy cập file dựa vào giá trị `href` tùy ý; XOP resolver phải giới hạn phạm vi theo các MIME parts của package.

### 8.10. Interoperability với SOAP stack khác nền tảng

Kiểm thử ít nhất hai chiều:

| Bên gửi | Bên nhận | Điều cần xác minh |
| --- | --- | --- |
| Spring-WS/JAXB | .NET/WCF hoặc stack đối tác | XOP package, media type, CID, SOAP version, content bytes |
| .NET/WCF hoặc stack đối tác | Spring-WS/JAXB | JAXB DataHandler, CID resolution, content type, digest |
| Spring-WS/SAAJ | Spring-WS/AXIOM | MIME serialization, attachment streaming/cache |
| MTOM enabled | Client chỉ hiểu inline Base64 | Negotiated/fallback behavior, không giả định tự tương thích |

Đừng chỉ test Spring client gọi Spring server dùng cùng runtime; cùng implementation có thể cùng chia sẻ một assumption sai và vẫn pass.

## 9. WS-Security, signature và attachment integrity

MTOM tối ưu cách serialize binary content. Nó không tự xác thực người gửi, không mã hóa file và không bảo vệ nội dung khỏi sửa đổi sau khi được lưu.

### 9.1. Phân biệt các lớp bảo vệ

| Cơ chế | Bảo vệ | Không tự bảo đảm |
| --- | --- | --- |
| TLS | Confidentiality/integrity của hop mạng và xác thực server (mTLS có thể xác thực client) | File vẫn nguyên vẹn sau khi được lưu/forward; business sender identity xuyên mọi intermediary |
| WS-Security XML Signature | Integrity/authenticity của các SOAP parts/attachments được ký theo profile/transform phù hợp | Mọi part MIME hoặc metadata đều được ký nếu không nằm trong signed references |
| WS-Security Encryption | Confidentiality của SOAP parts/attachments được mã hóa theo profile phù hợp | Authorization file type, malware scanning, retention |
| SHA-256 field | So sánh digest của bytes theo contract | Nguồn gốc đáng tin nếu digest cũng bị thay đổi |
| Antivirus/content inspection | Phát hiện nội dung độc hại theo scanner | Binary transport không bị thay đổi |
| MTOM/XOP | Đóng gói binary hiệu quả, giữ XML Infoset tương đương | Checksum, signature, authentication |

### 9.2. XML Signature với XOP cần profile tương thích

XOP package có root XML part và các MIME parts. Một XML Signature trên SOAP Infoset không mặc nhiên bảo vệ mọi chi tiết packaging, ví dụ việc đổi thứ tự các MIME parts không được tham chiếu hoặc thay metadata ngoài signed infoset. Khi ký nội dung attachment, hai bên cần thống nhất WS-Security Attachment Profile/transform và test interoperability.

Không tự giả định việc bật `Wss4jSecurityInterceptor` sẽ ký mọi attachment theo đúng profile mà đối tác yêu cầu. Kiểm tra cấu hình signed parts, attachment transforms, thuật toán digest/signature và behavior với client stack thực.

### 9.3. Digest phải được bảo vệ

Nếu SOAP Body chứa:

```xml
<doc:sha256>...</doc:sha256>
```

thì field digest cần nằm trong phần SOAP được bảo vệ theo security profile. Nếu một attacker sửa được cả attachment và digest, so sánh vẫn pass. Có thể dùng XML Signature trên Body chứa digest, chữ ký detached hoặc chữ ký số được thỏa thuận để ràng buộc digest với sender identity.

### 9.4. Không tin MIME metadata do client khai

Các thông tin sau có thể bị giả mạo:

- Content-Type.
- File name.
- Extension `.pdf`, `.png`, `.docx`.
- Claimed file size.
- Digest nếu không được bảo vệ.
- Content-ID nếu request package không được xác minh.

Server cần:

1. Enforce max bytes trong lúc stream, không chỉ tin Content-Length.
2. Validate MIME type theo allowlist và inspect magic bytes/parser thực tế.
3. Scan malware theo policy và cách ly file đáng ngờ.
4. Chuẩn hóa/sanitize file name khi lưu; không dùng làm đường dẫn filesystem.
5. Lưu digest/length thực đo và liên kết với document ID.
6. Chỉ publish file sau khi bước scan/validation thành công.

### 9.5. XXE, ZIP bombs và file parser

MTOM không làm XML hoặc binary trở nên an toàn tự động:

- XML parser phải chặn external entities/DTD theo security policy của ứng dụng.
- ZIP/DOCX/JAR hoặc file nén cần giới hạn expansion ratio, số entries và tổng expanded bytes.
- PDF/image parser cần timeout, sandbox/quarantine nếu threat model yêu cầu.
- Không mở file đính kèm theo URL/path do client cung cấp.
- Có quota cho số MIME parts và số attachment trên mỗi request.

## 10. Streaming, caching và quản lý tài nguyên

### 10.1. SAAJ có thể giữ toàn bộ SOAP message trong memory

SAAJ dựa trên DOM. Khi dùng `SaajSoapMessageFactory`, message có thể được lưu trong memory; file lớn và concurrency cao có thể tạo áp lực heap đáng kể.

Nếu cần payload lớn, xem xét `AxiomSoapMessageFactory`/AXIOM StAX và attachment caching. AXIOM có các lựa chọn như `payloadCaching` và `attachmentCaching`; cấu hình cụ thể phụ thuộc use case và Spring-WS version.

### 10.2. Payload caching false có side effect

`AxiomSoapMessageFactory` có thể đọc SOAP Body trực tiếp từ input stream khi `payloadCaching=false`. Điều này có thể làm payload chỉ đọc được một lần. Nếu endpoint mapping, `PayloadValidatingInterceptor`, logging interceptor hoặc custom preprocessing tiêu thụ stream trước endpoint, các bước sau có thể không còn đọc được payload.

Trước khi bật:

- Xác định endpoint mapping có đọc payload hay không.
- Kiểm tra interceptor nào đọc/log/validate payload.
- Không chạy nhiều consumers trên cùng one-shot stream.
- Test request/response thực qua tất cả interceptors.

### 10.3. Attachment caching ra disk

AXIOM có thể cache attachment lớn ra disk qua `attachmentCaching`; `attachmentCacheDir` có thể chỉ định thư mục cache. Nếu dùng:

- Chọn thư mục riêng, quyền filesystem chặt và dung lượng quota.
- Không dùng thư mục public/webroot.
- Xóa tệp tạm khi message xử lý xong hoặc thất bại.
- Có cleanup job cho crash/orphan files.
- Theo dõi disk pressure và I/O latency.
- Bảo vệ dữ liệu nhạy cảm tại rest (filesystem permissions/encryption theo policy).

`attachmentCacheThreshold` điều khiển ngưỡng kích thước attachment được cache ra disk; Spring-WS 4.1.4 mặc định là 4 KB khi attachment caching được bật. Giá trị phù hợp phụ thuộc disk throughput, heap budget và phân bố kích thước file.

### 10.4. Tính ngân sách memory

Ví dụ 20 request đồng thời, mỗi file 25 MB:

| Cách xử lý | Rủi ro |
| --- | --- |
| Base64 String + DOM + byte[] + copy service | Nhiều bản sao, heap có thể vượt xa 500 MB |
| DataHandler + streaming + disk staging | Giảm heap nhưng tăng disk I/O và lifecycle complexity |
| Axiom streaming nhưng interceptor cache payload | Có thể lại materialize dữ liệu |
| Async queue lưu file staging | Tăng durability/decoupling nhưng cần quản lý retry, cleanup, duplicate |

Đây là ví dụ định tính, không phải hệ số memory cố định. Đo heap, allocation, GC pauses và throughput bằng file size/concurrency gần production.

### 10.5. Backpressure và cancellation

Một client ngắt kết nối khi đang upload không nên để server tiếp tục đọc/lưu vô hạn nếu transport báo cancellation. Hệ thống cần:

- Timeout đọc stream và request deadline.
- Hủy staging operation khi request bị cancel nếu có thể.
- Giới hạn concurrency theo kích thước file.
- Không mở tất cả file streams một lúc.
- Đóng stream/attachment/resource trong mọi nhánh exception.
- Trả trạng thái business rõ ràng nếu file đã được lưu nhưng response bị mất.

### 10.6. Retry upload và idempotency

Client timeout không chứng minh server chưa lưu file. Retry có thể tạo bản ghi/file trùng. Dùng `documentId`/upload idempotency key ổn định và server-side dedup:

```text
Upload request key: tenant-42/DOC-100/version-3
Expected digest: 8d...
Received digest: 8d...

If same key + same digest:
  return existing result

If same key + different digest:
  reject conflict; do not silently overwrite
```

Quy tắc này là business contract. Không dùng Content-ID làm idempotency key.

## 11. Observability và vận hành

### 11.1. Metrics đề xuất

```text
soap_mtom_requests_total{operation,outcome}
soap_mtom_attachments_total{operation}
soap_mtom_bytes_received_total{operation}
soap_mtom_digest_mismatch_total{operation}
soap_mtom_attachment_rejected_total{reason}
soap_mtom_processing_seconds{operation}
soap_mtom_staging_bytes{storage}
soap_mtom_cleanup_failures_total
```

Không dùng Content-ID, file name, document ID, tenant ID hoặc raw digest làm metric labels vì cardinality và thông tin nhạy cảm. Dùng aggregate labels có giới hạn.

### 11.2. Structured log không chứa bytes

```text
event=SOAP_MTM_UPLOAD
operation=UploadDocument
requestId=req-100
documentId=DOC-100
soapVersion=1.2
receivedBytes=18874368
receivedSha256=8d... (redacted/truncated by policy)
declaredContentType=application/pdf
detectedContentType=application/pdf
validation=PASS
scan=PASS
outcome=STORED
durationMs=...
```

Raw digest có thể được xem là metadata có liên quan file; chỉ log theo policy, thường có thể lưu digest đầy đủ ở audit record kiểm soát truy cập, còn application logs chỉ hiển thị prefix hoặc correlation reference.

Không log nguyên MIME multipart body, raw Base64, attachment bytes, SOAP Security header hoặc full file names có PII.

### 11.3. Alert vận hành

Theo dõi:

- Tỷ lệ digest mismatch tăng.
- Attachment resolution failures.
- File vượt quota/negative tests bị kích hoạt bất thường.
- Disk cache/staging storage gần đầy.
- Cleanup job thất bại/orphan attachment tăng.
- P95/P99 upload latency và SOAP timeout.
- GC pauses/heap pressure khi tải file lớn.
- Virus scanner timeout/failure.
- Partner interoperability failures sau khi nâng SOAP stack.

## 12. Troubleshooting MTOM

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| JAXB marshal Base64 inline thay vì MTOM | `mtomEnabled` chưa bật hoặc field binding không tối ưu được | `Jaxb2Marshaller`, `@XmlMimeType`, generated model |
| `DataHandler` bị bind như type không hỗ trợ | Activation/JAXB namespace mismatch hoặc context thiếu model | `jakarta.activation` vs `javax.activation`, runtime dependency |
| XOP Include xuất hiện nhưng part không có | Attachment marshalling/package writer lỗi hoặc message bị cắt | Capture raw multipart, CID mapping, SAAJ/Axiom |
| Server không resolve CID | `href` và Content-ID mismatch | MIME parser, normalized CID, package capture |
| SAAJ message ngốn heap | DOM giữ message/attachment trong memory | Heap dump, file size, concurrency, staging |
| AXIOM payload rỗng khi interceptor chạy sau | `payloadCaching=false`, stream đã bị đọc | Endpoint mapping/interceptor ordering |
| Attachment cache chiếm disk | Cleanup lỗi, crash/orphan files, quota thiếu | Cache directory, temp file lifecycle, cleanup metrics |
| Digest mismatch | Truncation, wrong CID, transform/encoding mismatch hoặc file khác | Compare raw bytes, length, MIME decode, SHA-256 |
| Content-Type không khớp | Client khai metadata sai hoặc provider mapping không giữ media type | XSD XML MIME annotation, `DataHandler.getContentType()`, MIME headers |
| Partner .NET không đọc được file | MTOM policy/version/binding mismatch | Interop capture, SOAP version, WSDL/profile, attachment part |
| Test nhỏ pass, file lớn fail | Size limits, threshold, memory/disk, timeouts | Proxy/container limits, heap, cache, stream timeout |
| SOAP body valid nhưng file invalid | XSD chỉ xác nhận cấu trúc/Base64 type, không xác nhận file semantics | Magic bytes, file parser, antivirus/content scan |
| Signature verify fail khi bật MTOM | Attachment transform/signed parts không đồng bộ | WS-Security attachment profile, canonicalization, WSS4J config |
| Retry tạo file trùng | Client timeout sau khi server commit, thiếu idempotency | Upload key, digest persistence, status lookup |
| HTTP 413/connection reset không có SOAP Fault | Proxy/container reject trước SOAP message factory | Reverse proxy, servlet limits, request size config |

### 12.1. Trình tự điều tra

```text
1. Client marshaller có bật MTOM và model binding đúng không?
2. Request có thực sự là multipart/related không?
3. Root part là XOP XML với đúng SOAP version/type không?
4. Mỗi xop:Include CID có một MIME part tương ứng không?
5. SOAP message factory có reconstruct attachment được không?
6. DataHandler/stream có mở và đọc hết được không?
7. Received length và SHA-256 có khớp source không?
8. Content type/file scan/schema/security có pass không?
9. Server commit có idempotent và cleanup đúng không?
```

Không vội tắt validation/security khi chưa xác định tầng đầu tiên lỗi.

## 13. Bài thực hành có đáp án

### Bài 1. MTOM có thay đổi XSD type không?

XSD field content là xs:base64Binary. Khi gửi MTOM, wire XML có xop:Include.

**Đáp án:** Không. XOP là cách serialize tối ưu của XML Infoset. Ở mức khái niệm, phần tử vẫn biểu diễn nội dung Base64 tương đương theo contract; MIME part mang octets tương ứng.

### Bài 2. MTOM và SOAP with Attachments có giống nhau?

**Đáp án:** Không. Cả hai có thể dùng MIME multipart, nhưng MTOM dùng XOP để thay nội dung Base64 trong XML Infoset bằng xop:Include, giữ semantics XML của base64Binary. SwA dùng attachment theo profile/cơ chế khác.

### Bài 3. Vì sao Base64 inline làm message lớn?

**Đáp án:** Base64 biểu diễn 3 bytes thành 4 ký tự, tăng xấp xỉ 33% trước overhead XML. Parser/JAXB/String/DOM còn có thể tạo thêm bản sao trong memory.

### Bài 4. xop:Include tham chiếu attachment bằng gì?

**Đáp án:** Thuộc tính href, thường dạng URI cid:..., trỏ tới Content-ID của MIME part tương ứng. CID không phải document ID hoặc checksum.

### Bài 5. xmime:expectedContentTypes có phải Content-Type thực tế?

**Đáp án:** Không. Đây là schema annotation về MIME type dự kiến cho binding/tooling. MIME part vẫn có header Content-Type thực tế; ứng dụng phải xác minh type theo contract và nội dung.

### Bài 6. JAXB dùng type Java nào cho binary?

**Đáp án:** Tùy binding/schema/runtime. Có thể là byte[], DataHandler, Image, Source hoặc type khác theo MIME annotation/customization. Đọc generated source và test runtime.

### Bài 7. DataHandler có tự bật MTOM?

**Đáp án:** Không. DataHandler là data abstraction; Jaxb2Marshaller.setMtomEnabled(true) mới bật MTOM processing trong Spring OXM marshaller. Còn cần message factory/transport hỗ trợ.

### Bài 8. mtomEnabled mặc định là gì?

**Đáp án:** Spring Framework Jaxb2Marshaller mặc định là false. Cần bật rõ ràng trong cấu hình và xác minh MIME package.

### Bài 9. Vì sao chọn DataHandler cho file lớn?

**Đáp án:** Nó làm việc qua DataSource/InputStream, cho phép xử lý dạng stream tùy implementation. byte[] buộc giữ toàn bộ file trong memory và có thể tăng heap pressure.

### Bài 10. Content-Type là application/pdf có chứng minh file PDF?

**Đáp án:** Không. Đây là metadata do sender khai. Server cần kiểm tra magic bytes/parser thực tế và scan theo policy.

### Bài 11. Attachment Content-ID có thể làm storage key không?

**Đáp án:** Không nên. CID chỉ định danh MIME part trong package và có thể thay đổi mỗi lần gửi. Dùng business document ID/idempotency key ổn định.

### Bài 12. Kiểm tra length có đủ xác nhận integrity?

**Đáp án:** Không. Hai file khác nhau có thể có cùng chiều dài. So sánh SHA-256 của source bytes với received bytes, đồng thời xác minh metadata.

### Bài 13. Digest field có cần ký không?

**Đáp án:** Nếu digest được dùng làm bằng chứng integrity/nguồn gốc, cần bảo vệ digest bằng WS-Security/XML Signature hoặc cơ chế chữ ký trusted. Nếu attacker sửa được cả file và digest thì so sánh vẫn pass.

### Bài 14. TLS có thay SHA-256 application-level không?

**Đáp án:** Không. TLS bảo vệ dữ liệu trên channel/hop trong lúc truyền; application digest giúp kiểm tra file sau parse, lưu trữ hoặc chuyển tiếp, theo contract.

### Bài 15. Vì sao test MTOM cần HTTP server thật?

**Đáp án:** JAXB unit test chỉ kiểm tra binding. Mock client có thể test marshaller/request expectation, nhưng không chứng minh MIME multipart qua socket, servlet/container, proxy, TLS hoặc partner stack. Cần integration test thật.

### Bài 16. Có nên assert MIME boundary và CID literal?

**Đáp án:** Không. Runtime thường tự sinh chúng. Assert multipart/related, root part, xop:Include href có part tương ứng, bytes và metadata. Không phụ thuộc giá trị ngẫu nhiên.

### Bài 17. Attachment thiếu nhưng xop:Include vẫn có

**Đáp án:** Reject ở MIME/XOP attachment resolution, không gọi business service và không commit record. Log correlation ID, không log bytes.

### Bài 18. Vì sao AXIOM payloadCaching=false có thể làm test fail?

**Đáp án:** Payload có thể chỉ đọc được một lần. Endpoint mapping/interceptor/logging/validation có thể tiêu thụ stream trước endpoint. Phải kiểm tra thứ tự và tránh nhiều consumers đọc cùng one-shot stream.

### Bài 19. SAAJ và AXIOM khác gì với payload lớn?

**Đáp án:** SAAJ dựa DOM và có thể giữ message trong memory. AXIOM dựa StAX/pull processing, có thể phù hợp streaming/caching hơn, nhưng toàn pipeline vẫn có thể materialize bytes.

### Bài 20. Client timeout upload có nghĩa server chưa lưu file?

**Đáp án:** Không. Server có thể đã nhận và commit file rồi nhưng response bị mất. Cần idempotency key, digest và status lookup; không retry mù tạo bản ghi trùng.

### Bài 21. Vì sao không dùng filename làm file system path?

**Đáp án:** Filename do client cung cấp có thể chứa path traversal, ký tự điều khiển hoặc tên trùng. Sanitize và tạo server-side storage key riêng.

### Bài 22. MIME attachment có thể là ZIP bomb?

**Đáp án:** Có. Giới hạn bytes truyền, expanded bytes/ratio, số entries và thời gian parser; scan/sandbox theo threat model.

### Bài 23. WS-Security ký SOAP Body có chắc attachment đã được ký?

**Đáp án:** Không. Cần cấu hình/kiểm tra attachment transforms và signed references theo profile mà hai SOAP stack hỗ trợ. Không mặc định mọi MIME part được bảo vệ.

### Bài 24. Khi nào có thể dùng Base64 inline thay MTOM?

**Đáp án:** File nhỏ, client/partner không hỗ trợ MTOM hoặc contract/profile yêu cầu inline. Quyết định dựa kích thước, memory budget, interop và SLA; không có ngưỡng chung đúng cho mọi stack.

## 14. Checklist nghiệm thu production

| Nhóm | Câu hỏi kiểm tra |
| --- | --- |
| Contract | XSD có xs:base64Binary và XML MIME annotations phù hợp? |
| SOAP version | SOAP 1.1/1.2 và WSDL binding đã thống nhất? |
| MTOM enablement | JAXB marshaller đã bật mtomEnabled ở client/server cần thiết? |
| JAXB mapping | Model sinh là DataHandler/byte[] hay custom binding; đã đọc generated source? |
| Message factory | SAAJ/AXIOM/provider hỗ trợ attachment; version dependency đồng nhất? |
| MIME package | Multipart root part, type/start-info, Content-ID và attachment parts đúng profile? |
| XOP | xop:Include QName/href và MIME part mapping được kiểm tra? |
| Partner compatibility | Đã test gửi/nhận với SOAP stack đối tác, không chỉ stack cùng hãng? |
| Binary integrity | Received length và SHA-256 so khớp source bytes? |
| Digest contract | Thuật toán, representation và byte scope được định nghĩa? |
| Signature | Nếu cần, digest/header/body/attachment được ký theo WS-Security profile? |
| Encryption | Attachment có cần encryption at rest/in transit hoặc XML Encryption không? |
| Content-Type | Allowlist + file signature/parser validation; không chỉ tin header? |
| Size quotas | Max attachment bytes, total package bytes, part count và concurrency? |
| Parser security | XXE/DTD và XML parser limits được cấu hình? |
| File security | Malware scan, archive expansion limits, parser timeout/sandbox? |
| Streaming | Không materialize nhiều bản sao vô ý; có backpressure/timeout? |
| Temp storage | Disk cache/staging quota, permissions, cleanup và encryption? |
| Retry | Document ID/idempotency key và duplicate handling rõ? |
| Transaction | Không publish/commit document trước digest/scan/validation pass? |
| Logging | Không log raw multipart, Base64, file bytes, secrets hoặc PII? |
| Metrics | Bytes, digest mismatch, failed attachments, staging usage và latency? |
| Negative tests | Missing CID, duplicate CID, truncation, wrong type, over-quota đã test? |
| Fault handling | Fault/transport outcome và client retry semantics được xác định? |
| Operations | Runbook, cleanup, disk alerts, scanner failures, rollback và reprocess? |

### 14.1. Mẫu test matrix tối thiểu

```text
Happy path:
  small binary / large binary
  PDF / PNG / supported media types
  MTOM request / MTOM response
  DataHandler / byte[] binding where applicable

Integrity:
  exact length
  exact SHA-256
  wrong digest
  truncated stream

Package:
  valid XOP href/CID
  missing CID
  duplicate Content-ID
  extra unreferenced part
  malformed multipart boundary

Security/limits:
  wrong MIME type
  over-size attachment
  too many parts
  malicious archive
  invalid signature / unsigned required part

Interoperability:
  Spring -> partner stack
  partner stack -> Spring
  SOAP 1.1/1.2 as contracted
```

## 15. Tổng kết

MTOM/XOP là cơ chế tối ưu truyền binary content trong SOAP:

- XSD contract vẫn dùng `xs:base64Binary`; XOP thay lexical Base64 trong XML bằng `xop:Include` và MIME part riêng.
- `xmime:expectedContentTypes` và `xmime:contentType` hỗ trợ mô tả MIME data; chúng không tự xác nhận nội dung file.
- JAXB có thể bind binary thành `DataHandler` hoặc `byte[]`; `DataHandler`/stream thích hợp khi cần tránh materialize file lớn, còn `byte[]` dễ dùng nhưng tốn heap.
- Spring Framework `Jaxb2Marshaller` mặc định không bật MTOM; cấu hình `setMtomEnabled(true)` và kiểm tra message factory/transport hai đầu.
- SAAJ/DOM và AXIOM/StAX có memory/streaming trade-offs; interceptor, validation, logging và business code vẫn có thể đọc hết payload vào memory.
- MIME package cần kiểm tra root part, Content-ID, XOP href và attachment bytes; không phụ thuộc boundary/CID ngẫu nhiên.
- Integrity cần length + SHA-256 trên bytes thực, và digest phải được bảo vệ nếu dùng làm bằng chứng nguồn gốc.
- TLS, WS-Security signature/encryption, digest, malware scanning và MTOM giải quyết những vấn đề khác nhau.
- Production cần quotas, parser security, staging cleanup, idempotency, metrics, interop tests và retry policy.

### Mô hình tư duy

```text
XSD / WSDL contract
  xs:base64Binary + XML MIME metadata
            |
            v
JAXB model (DataHandler / byte[])
            |
            v
Jaxb2Marshaller (MTOM enabled)
            |
            v
SOAP message factory + MIME package writer
            |
            v
multipart/related
  root SOAP/XOP XML + binary MIME parts
            |
            v
HTTP/TLS + WS-Security profile
            |
            v
SOAP message factory + XOP reconstruction
            |
            v
DataHandler/InputStream at endpoint
            |
            +--> length + SHA-256 + content validation
            |
            +--> malware scan + staging + commit
```

**Nguyên tắc thực hành:** MTOM làm cho binary content được truyền hiệu quả hơn; chỉ kiểm thử bytes sau khi reconstruct, digest, metadata và business/storage outcome mới chứng minh dữ liệu đã đến đúng và an toàn.

### Tài liệu tham khảo

- [Spring Web Services 4.1.4 — Reference Documentation, MTOM](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/).
- [Spring-WS 4.1.4 — SaajSoapMessage API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/saaj/SaajSoapMessage.html).
- [Spring-WS 4.1.4 — AxiomSoapMessageFactory API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessageFactory.html).
- [Spring Framework 6.2 — Jaxb2Marshaller API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html).
- [Jakarta XML Binding 4.0 Specification, Appendix G — Enhanced Binary Data Handling](https://jakarta.ee/specifications/xml-binding/4.0/jakarta-xml-binding-spec-4.0).
- [W3C — XML-binary Optimized Packaging (XOP)](https://www.w3.org/TR/xop10/).
- [W3C — SOAP Message Transmission Optimization Mechanism (MTOM)](https://www.w3.org/TR/soap12-mtom/).
- [W3C — SOAP 1.2 Part 1: Messaging Framework](https://www.w3.org/TR/soap12-part1/).
- [OASIS — Web Services Security](https://www.oasis-open.org/committees/tc_home.php?wg_abbrev=wss).
