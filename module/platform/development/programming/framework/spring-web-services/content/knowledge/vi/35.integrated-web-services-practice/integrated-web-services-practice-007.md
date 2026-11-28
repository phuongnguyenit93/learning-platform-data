# Trao đổi tệp đính kèm bằng MTOM và kiểm tra giới hạn dữ liệu

> **Chương:** Thực hành tổng hợp  
> **Công nghệ:** Spring Web Services (Spring-WS), SOAP contract-first, XSD/WSDL, JAXB, MTOM/XOP  
> **Bài thực hành:** Tạo dịch vụ SOAP nhận một tệp nhị phân, kiểm soát kích thước thực tế và tính toàn vẹn trước khi lưu.

## 1. Bối cảnh và kết quả cần đạt

Một hệ thống doanh nghiệp cần nhận tài liệu từ đối tác qua SOAP: đối tác gửi mã giao dịch, tên tệp, số byte dự kiến, mã băm SHA-256 và nội dung PDF/ảnh/tệp nhị phân. Đưa toàn bộ tệp vào một phần tử XML dưới dạng Base64 khiến thông điệp tăng kích thước khoảng 33% chỉ riêng phần mã hóa, làm phát sinh thêm chi phí cấp phát bộ nhớ và xử lý XML. **MTOM (Message Transmission Optimization Mechanism)** cho phép giữ giao diện SOAP/XML nhưng đóng gói dữ liệu nhị phân thành phần MIME riêng.

Sau bài này, bạn có thể:

1. Thiết kế contract XSD cho một thao tác `UploadDocument` theo hướng contract-first và sinh kiểu JAXB thích hợp với MTOM.
2. Phân biệt phần tử `xs:base64Binary`, `DataHandler`, `xop:Include`, `Content-ID` và phần MIME nhị phân.
3. Cấu hình Spring-WS để cả endpoint lẫn SOAP client thực sự marshal/unmarshal bằng MTOM.
4. Áp dụng giới hạn ở **cổng HTTP**, **lớp giải mã SOAP** và **dữ liệu thực đọc được**; kiểm tra tổng byte và SHA-256 trước khi công nhận thành công.
5. Kiểm thử đường truyền, các trường hợp vượt giới hạn, sai metadata, lỗi SOAP Fault và bảo vệ tài nguyên khi nhiều yêu cầu đến đồng thời.

**Quy ước thực hành:** mỗi tệp tối đa **5 MiB = 5.242.880 byte**; toàn bộ HTTP request tối đa **8 MiB** (bao gồm SOAP envelope, MIME headers và các phần nhị phân). Các con số chỉ là chính sách ví dụ, phải đo tải thực tế và điều chỉnh đồng bộ khi triển khai.

## 2. MTOM đóng gói tệp như thế nào?

Một trường `xs:base64Binary` trong XSD diễn tả **giá trị logic** là chuỗi byte. Với SOAP thông thường, giá trị này được đặt trong XML dưới dạng Base64. Với MTOM/XOP, biểu diễn truyền trên mạng có thể được tối ưu:

```text
                      HTTP POST /ws
                           |
              Content-Type: multipart/related
                           |
              +------------+-------------+
              |                          |
       MIME root part              MIME binary part
       application/xop+xml         application/octet-stream
              |                          |
        SOAP Envelope                Byte gốc
              |                          ^
      <xop:Include                  Content-ID:
       href="cid:file-1"/> --------- file-1
```

Ví dụ rút gọn của **SOAP 1.1 + MTOM** (đã lược bỏ các header không liên quan, boundary chỉ là minh họa):

```http
POST /ws HTTP/1.1
Content-Type: multipart/related; boundary="b1"; type="application/xop+xml"; start-info="text/xml"

--b1
Content-Type: application/xop+xml; charset=UTF-8; type="text/xml"
Content-ID: <soap-root@example.test>

<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:d="urn:example:documents:v1"
               xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <soap:Body>
    <d:UploadDocumentRequest>
      <d:documentId>doc-42</d:documentId>
      <d:fileName>report.pdf</d:fileName>
      <d:declaredSize>4</d:declaredSize>
      <d:sha256>...</d:sha256>
      <d:content><xop:Include href="cid:file-1@example.test"/></d:content>
    </d:UploadDocumentRequest>
  </soap:Body>
</soap:Envelope>

--b1
Content-Type: application/octet-stream
Content-ID: <file-1@example.test>
Content-Transfer-Encoding: binary

%PDF
--b1--
```

`xop:Include` trỏ đến một MIME part qua `cid:`. Bên nhận khôi phục giá trị nhị phân logic của phần tử XML bằng nội dung part đó. Trên dây, MTOM dùng `multipart/related` với `application/xop+xml`; với SOAP 1.1, `start-info` thường là `text/xml`, còn SOAP 1.2 dùng `application/soap+xml`.

**Phân biệt quan trọng:**

| Cách gửi | Nội dung của SOAP Body | Tệp truyền đi | Điều cần nhớ |
|---|---|---|---|
| Base64 nhúng XML | Văn bản Base64 | Nằm trong phần XML | Phình khoảng 4/3 kích thước byte, chưa tính XML |
| MTOM/XOP | Tham chiếu `xop:Include` | MIME part nhị phân | Có thể giảm chi phí mã hóa và sao chép dữ liệu |
| SwA (SOAP with Attachments) thông thường | Có thể tham chiếu `cid:` theo quy ước riêng | MIME part | Không đồng nghĩa với cơ chế tối ưu giá trị `xs:base64Binary` của MTOM |

MTOM **không tự bảo đảm** truyền theo luồng hoàn toàn, tiết kiệm RAM tuyệt đối hoặc từ chối thông điệp quá lớn. Bộ phân tích MIME/SOAP và các thư viện có thể đệm dữ liệu trước khi endpoint nhận `DataHandler`; việc giới hạn request vẫn bắt buộc.

## 3. Thiết kế contract-first: XSD và WSDL

Hợp đồng định nghĩa kiểu dữ liệu trước, sau đó sinh mã JAXB từ XSD và công bố WSDL. Ví dụ `src/main/resources/xsd/documents.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:documents:v1"
           xmlns:xmime="http://www.w3.org/2005/05/xmlmime"
           targetNamespace="urn:example:documents:v1"
           elementFormDefault="qualified">

  <xs:element name="UploadDocumentRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="fileName" type="xs:string"/>
        <xs:element name="declaredSize" type="xs:long"/>
        <xs:element name="sha256" type="xs:string"/>
        <xs:element name="content" type="xs:base64Binary"
                    xmime:expectedContentTypes="application/octet-stream"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="UploadDocumentResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="receiptId" type="xs:string"/>
        <xs:element name="actualSize" type="xs:long"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

`xmime:expectedContentTypes` gợi ý cho công cụ JAXB/XJC ánh xạ phần tử nhị phân thành `jakarta.activation.DataHandler` thay vì buộc ứng dụng giữ `byte[]` toàn bộ tệp. Kiểm tra mã được sinh: trường `content` cần truy cập được qua `DataHandler` hoặc binding tương đương hỗ trợ MTOM. Nếu XJC sinh `byte[]`, hãy kiểm tra phiên bản plugin, binding XJC và khai báo `xmime` trước khi triển khai; không giả định mọi công cụ đều sinh kiểu giống nhau.

Một lớp JAXB minh họa biểu diễn phần nội dung (thường **được sinh từ XSD**, không duy trì bản viết tay song song):

```java
import jakarta.activation.DataHandler;
import jakarta.xml.bind.annotation.XmlMimeType;

// Nằm trong kiểu JAXB của UploadDocumentRequest:
@XmlMimeType("application/octet-stream")
protected DataHandler content;
```

Với Spring Boot/Spring-WS có cấu hình SOAP servlet tại `/ws/*`, ví dụ công bố WSDL từ XSD:

```java
@Bean(name = "documents")
DefaultWsdl11Definition documentsWsdl(XsdSchema documentsSchema) {
    DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
    wsdl.setPortTypeName("DocumentsPort");
    wsdl.setLocationUri("/ws");
    wsdl.setTargetNamespace("urn:example:documents:v1");
    wsdl.setSchema(documentsSchema);
    return wsdl;
}

@Bean
XsdSchema documentsSchema() {
    return new SimpleXsdSchema(
        new ClassPathResource("xsd/documents.xsd"));
}
```

Các lớp trên lần lượt thuộc `org.springframework.ws.wsdl.wsdl11`, `org.springframework.xml.xsd` và `org.springframework.core.io`. Sau khi đăng ký `MessageDispatcherServlet`, ví dụ endpoint công bố WSDL là `/ws/documents.wsdl`. Phần xây dựng ứng dụng dùng Spring-WS hỗ trợ **Jakarta JAXB/Activation** (thông thường Spring-WS 4+/5+); dự án cũ dựa trên `javax.*` phải dùng bộ thư viện tương thích, không trộn hai namespace.

**Ranh giới hợp đồng và chính sách:** XSD xác định tên phần tử, thứ tự, kiểu và giá trị logic của binary; nó không tự giới hạn byte của một MIME part. Quy tắc `5 MiB`, loại tệp được phép, thời gian xử lý và số request đồng thời phải được thực thi ở tầng ứng dụng/hạ tầng. WSDL cũng không tự ép mọi client gửi MTOM: cần xác nhận hỗ trợ MTOM giữa hai bên, hoặc công bố chính sách WS-Policy phù hợp nếu giao thức tích hợp yêu cầu.

## 4. Cấu hình Spring-WS đúng cho MTOM

Các thành phần chính là `spring-ws-core`, JAXB runtime, Jakarta Activation và SAAJ tương thích. Với ứng dụng Spring Boot có thể bắt đầu từ `spring-boot-starter-web-services` và cấu hình JAXB/XJC ở bước build; version theo BOM của dự án.

**Điểm dễ bỏ sót:** `@EnableWs` đăng ký xử lý JAXB mặc định, nhưng bộ xử lý mặc định **không đảm bảo đọc attachment MTOM**. Tài liệu Spring-WS cảnh báo `DataHandler` có thể nhận luồng rỗng khi endpoint dùng JAXB mặc định. Phải đăng ký `MarshallingPayloadMethodProcessor` dùng `Jaxb2Marshaller(mtomEnabled=true)` và đặt trước các processor mặc định.

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.endpoint.adapter.method.MarshallingPayloadMethodProcessor;
import org.springframework.ws.server.endpoint.adapter.method.MethodArgumentResolver;
import org.springframework.ws.server.endpoint.adapter.method.MethodReturnValueHandler;

@Configuration
@EnableWs
public class MtomWsConfig implements WsConfigurer {

    @Bean
    public Jaxb2Marshaller mtomMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.documents.jaxb");
        marshaller.setMtomEnabled(true);
        return marshaller;
    }

    @Override
    public void addArgumentResolvers(
            List<MethodArgumentResolver> argumentResolvers) {
        argumentResolvers.add(0,
            new MarshallingPayloadMethodProcessor(mtomMarshaller()));
    }

    @Override
    public void addReturnValueHandlers(
            List<MethodReturnValueHandler> returnValueHandlers) {
        returnValueHandlers.add(0,
            new MarshallingPayloadMethodProcessor(mtomMarshaller()));
    }
}
```

`com.example.documents.jaxb` là package JAXB được sinh từ XSD, chứa cả `ObjectFactory`. Nếu XJC tạo một phần tử toàn cục dùng **named complex type**, lớp kiểu có thể chỉ mang `@XmlType` mà không có `@XmlRootElement`. Khi đó khai báo tham số endpoint bằng `JAXBElement<UploadDocumentRequest>` (rồi lấy `.getValue()`) để processor MTOM nhận đúng kiểu. Contract XSD ở mục 3 dùng **anonymous complex type** cho phần tử gốc để thuận tiện với ví dụ endpoint bên dưới.

Cấu hình cùng một `marshaller` cho cả bên gửi và bên nhận; bật MTOM ở client không thay thế bước cấu hình processor của server. Bài thực hành dùng một yêu cầu chứa **một binary element**; nếu hợp đồng có nhiều phần đính kèm, phải kiểm soát từng phần và tổng dung lượng.

## 5. Xây dựng endpoint nhận tệp

Endpoint nhận đối tượng JAXB từ SOAP Body, sau đó chuyển `DataHandler` cho lớp lưu trữ có kiểm soát. Các class `UploadDocumentRequest` và `UploadDocumentResponse` trong ví dụ là mã sinh theo XSD.

```java
import java.io.IOException;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class DocumentEndpoint {
    private static final String NS = "urn:example:documents:v1";
    private final BoundedDocumentStore store;

    public DocumentEndpoint(BoundedDocumentStore store) {
        this.store = store;
    }

    @PayloadRoot(namespace = NS, localPart = "UploadDocumentRequest")
    @ResponsePayload
    public UploadDocumentResponse upload(
            @RequestPayload UploadDocumentRequest request)
            throws IOException {

        BoundedDocumentStore.Receipt saved = store.save(
            request.getDocumentId(),
            request.getFileName(),
            request.getDeclaredSize(),
            request.getSha256(),
            request.getContent()
        );

        UploadDocumentResponse response = new UploadDocumentResponse();
        response.setDocumentId(request.getDocumentId());
        response.setReceiptId(saved.receiptId());
        response.setActualSize(saved.actualSize());
        return response;
    }
}
```

Một số điều cần nhớ:

- Chỉ trả `UploadDocumentResponse` sau khi tệp đã được đọc đủ, xác thực thành công và chuyển sang vùng lưu trữ chính thức.
- Không gọi `getInputStream().readAllBytes()`, không biến tệp thành `byte[]` và không ghi nội dung nhị phân vào log. Các thao tác đó dễ làm tăng bộ nhớ theo kích thước tệp.
- Không dùng `fileName` phía client làm đường dẫn lưu tệp. Đây chỉ là metadata; đường dẫn thực do server tự sinh.
- XSD là nơi xác thực **cấu trúc**; endpoint/service là nơi xác thực **quy tắc nghiệp vụ** và nội dung thực.

## 6. Đo byte thực tế, xác thực SHA-256 và lưu an toàn

Trong ví dụ sau, `BoundedDocumentStore` là một Spring `@Service`, sử dụng Java 17+. Thư mục lưu trữ được cấu hình bằng `app.upload-dir`; phải tạo trước hoặc cấp quyền ghi cho tiến trình. Tệp tạm và tệp hoàn tất cùng nằm trên một filesystem để ưu tiên `ATOMIC_MOVE`.

```java
import jakarta.activation.DataHandler;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class BoundedDocumentStore {
    public static final long MAX_FILE_BYTES = 5L * 1024 * 1024;
    private final Path uploadDir;

    public BoundedDocumentStore(
            @Value("${app.upload-dir}") String configuredDir)
            throws IOException {
        uploadDir = Path.of(configuredDir).toAbsolutePath().normalize();
        Files.createDirectories(uploadDir);
    }

    public record Receipt(String receiptId, long actualSize) {}

    public Receipt save(
            String documentId,
            String fileName,
            long declaredSize,
            String expectedSha256,
            DataHandler content) throws IOException {

        if (documentId == null ||
            !documentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new UploadRejectedException("documentId không hợp lệ");
        }
        // Ví dụ chỉ nhận tên tệp ASCII an toàn để đơn giản hóa chính sách.
        if (fileName == null ||
            !fileName.matches("[A-Za-z0-9._-]{1,128}") ||
            fileName.equals(".") || fileName.equals("..")) {
            throw new UploadRejectedException("fileName không hợp lệ");
        }
        if (declaredSize < 0 || declaredSize > MAX_FILE_BYTES) {
            throw new UploadRejectedException("declaredSize vượt giới hạn");
        }
        if (expectedSha256 == null ||
            !expectedSha256.matches("[0-9a-fA-F]{64}")) {
            throw new UploadRejectedException("sha256 không hợp lệ");
        }
        if (content == null) {
            throw new UploadRejectedException("Thiếu nội dung tệp");
        }

        Path partial = Files.createTempFile(uploadDir, "upload-", ".part");
        boolean committed = false;

        try {
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException("SHA-256 không khả dụng", e);
            }

            long actualSize = 0;
            try (InputStream in = content.getInputStream();
                 OutputStream out = Files.newOutputStream(partial)) {
                byte[] chunk = new byte[8192];
                int read;
                while ((read = in.read(chunk)) != -1) {
                    if (read == 0) {
                        continue;
                    }
                    // Dạng trừ tránh tràn số khi cộng với dữ liệu lớn.
                    if (read > MAX_FILE_BYTES - actualSize) {
                        throw new UploadRejectedException(
                            "Nội dung thực vượt 5 MiB");
                    }
                    out.write(chunk, 0, read);
                    digest.update(chunk, 0, read);
                    actualSize += read;
                }
            }

            if (actualSize != declaredSize) {
                throw new UploadRejectedException(
                    "Kích thước thực khác declaredSize");
            }
            String actualSha256 = HexFormat.of()
                .formatHex(digest.digest());
            if (!actualSha256.equalsIgnoreCase(expectedSha256)) {
                throw new UploadRejectedException(
                    "SHA-256 của tệp không khớp");
            }

            String receiptId = UUID.randomUUID().toString();
            Path destination = uploadDir.resolve(receiptId + ".bin");
            try {
                Files.move(partial, destination,
                    StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(partial, destination);
            }

            committed = true;
            return new Receipt(receiptId, actualSize);
        } finally {
            // Nếu lỗi hoặc tệp bị từ chối, xóa nội dung chưa hoàn tất.
            if (!committed) {
                Files.deleteIfExists(partial);
            }
        }
    }
}
```

Ví dụ này bảo vệ khỏi tệp vượt ngưỡng **ngay cả khi `declaredSize` và `Content-Length` bị khai gian**. Với mọi yêu cầu không hợp lệ, tệp `.part` được xóa và không tạo `receiptId` thành công. Nếu kiểm tra hash không khớp, không được coi yêu cầu là upload thành công dù đủ số byte.

**Giới hạn của ví dụ:** lớp lưu trữ chưa giải quyết idempotency theo `documentId`, xác minh chữ ký số, quét malware, xác định định dạng từ magic bytes, quota theo người dùng, thời gian giữ tệp hoặc giao dịch giữa metadata DB và file store. Trong sản phẩm thực, các yêu cầu này cần bổ sung và không dùng tên tệp gửi lên để tin rằng nội dung thực sự là PDF/ảnh.

### Trả SOAP Fault thay vì công bố chi tiết nội bộ

Các lỗi do người gửi gây ra (kích thước, hash, tên tệp không hợp lệ) phù hợp với SOAP 1.1 `Client` / SOAP 1.2 `Sender` fault. Có thể ánh xạ exception bằng Spring-WS:

```java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Tệp đính kèm không hợp lệ")
public class UploadRejectedException extends RuntimeException {
    public UploadRejectedException(String detail) {
        super(detail);
    }
}
```

Đăng ký `SoapFaultAnnotationExceptionResolver` làm bean để annotation được xử lý:

```java
@Bean
SoapFaultAnnotationExceptionResolver soapFaultResolver() {
    return new SoapFaultAnnotationExceptionResolver();
}
```

Import resolver từ `org.springframework.ws.soap.server.endpoint`. Khi cần trả mã lỗi chi tiết, có thể bổ sung `fault detail` theo contract, nhưng phải tránh để lộ đường dẫn thật, stack trace và dữ liệu nhạy cảm. Lỗi I/O khi lưu tệp là lỗi phía server và cần được xử lý/log an toàn riêng.

## 7. Viết SOAP client gửi tệp MTOM

Client cũng dùng `Jaxb2Marshaller` bật MTOM, tạo `DataHandler` trỏ tới tệp trên đĩa và gọi `WebServiceTemplate`. Hãy sử dụng chính package JAXB sinh từ **cùng contract XSD** để bảo đảm tên phần tử và namespace nhất quán.

```java
@Bean
WebServiceTemplate documentTemplate(Jaxb2Marshaller mtomMarshaller) {
    WebServiceTemplate template = new WebServiceTemplate();
    template.setMarshaller(mtomMarshaller);
    template.setUnmarshaller(mtomMarshaller);
    return template;
}
```

Ví dụ phương thức gửi tệp (các import chính: `jakarta.activation.DataHandler`, `jakarta.activation.FileDataSource`, `java.nio.file.*`, `java.security.*`, `java.util.*`, `org.springframework.ws.client.core.WebServiceTemplate`):

```java
public UploadDocumentResponse upload(
        WebServiceTemplate template, String serviceUrl, Path file)
        throws IOException {

    if (!Files.isRegularFile(file)) {
        throw new IllegalArgumentException("Tệp không tồn tại");
    }
    long length = Files.size(file);
    if (length > BoundedDocumentStore.MAX_FILE_BYTES) {
        throw new IllegalArgumentException("Tệp vượt 5 MiB");
    }

    UploadDocumentRequest request = new UploadDocumentRequest();
    request.setDocumentId(UUID.randomUUID().toString());
    request.setFileName(file.getFileName().toString());
    request.setDeclaredSize(length);
    request.setSha256(sha256(file));

    // Giữ Content-Type nhất quán với contract xmime.
    DataHandler handler = new DataHandler(
        new FileDataSource(file.toFile()) {
            @Override
            public String getContentType() {
                return "application/octet-stream";
            }
        });
    request.setContent(handler);

    Object result = template.marshalSendAndReceive(serviceUrl, request);
    return (UploadDocumentResponse) result;
}

private String sha256(Path path) throws IOException {
    MessageDigest digest;
    try {
        digest = MessageDigest.getInstance("SHA-256");
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException(e);
    }
    try (InputStream in =
             new DigestInputStream(Files.newInputStream(path), digest)) {
        in.transferTo(OutputStream.nullOutputStream());
    }
    return HexFormat.of().formatHex(digest.digest());
}
```

Đây là đoạn minh họa trong một lớp client Java 17+ với các import tiêu chuẩn tương ứng (`InputStream`, `OutputStream`, `DigestInputStream`, `HexFormat`, `UUID`, `Files`, `Path`). Nếu JAXB sinh root dưới dạng `JAXBElement<T>`, hãy bọc request bằng `ObjectFactory` và lấy `getValue()` từ response sau khi gọi `marshalSendAndReceive`. Khi dùng file lớn, cần bảo đảm file không bị chỉnh sửa giữa lần đọc tính SHA-256 và lần gửi; một lựa chọn là chụp bản tạm bất biến trước hai thao tác.

`DataHandler` không có nghĩa là toàn bộ pipeline luôn streaming. SOAP stack có thể tạo MIME part trong RAM hoặc disk; phải đo mức dùng bộ nhớ thực tế và đặt ngưỡng ở HTTP ingress trước khi xử lý.

## 8. Giới hạn dữ liệu ở ba lớp khác nhau

Một giới hạn ở endpoint là **quá muộn** để ngăn trường hợp parser đã nạp request cực lớn. Sử dụng phòng thủ nhiều lớp:

| Lớp | Chính sách ví dụ | Mục đích |
|---|---|---|
| Reverse proxy/API gateway | `client_max_body_size 8m` hoặc giới hạn request-body tương ứng | Chặn **tổng byte HTTP** trước SOAP servlet; chặn cả request không có `Content-Length` đáng tin |
| Spring-WS message factory | `maxMessageSize` nếu phiên bản hỗ trợ; giữ giới hạn phù hợp với request hợp lệ | Hạn chế lượng dữ liệu message factory chấp nhận trong quá trình giải mã SOAP |
| Endpoint/store | `MAX_FILE_BYTES = 5 * 1024 * 1024`, đếm byte thực, so sánh SHA-256 | Chặn **nội dung nhị phân** vượt mức; ngăn metadata sai và tệp dở dang |

Ví dụ NGINX ở route của dịch vụ:

```nginx
location /ws/ {
    client_max_body_size 8m;
    proxy_pass http://127.0.0.1:8080;
}
```

Giới hạn HTTP tính **tổng request**: nếu tệp tối đa 5 MiB, cần dành chỗ cho các MIME headers và SOAP envelope. Ngược lại, không được suy ra tệp hợp lệ chỉ vì request dưới 8 MiB. Không dùng `spring.servlet.multipart.max-file-size` như một biện pháp duy nhất: thuộc tính đó nhắm đến cơ chế upload `multipart/form-data` của Spring MVC, còn SOAP MTOM sử dụng `multipart/related` qua message factory của Spring-WS.

**Lưu ý phiên bản và an toàn bộ nhớ:** thông báo bảo mật Spring ngày **19/11/2026** (`CVE-2026-59349`) nêu rằng một số phiên bản Spring-WS cũ không giới hạn kích thước thông điệp trước khi parse, có nguy cơ tiêu tốn bộ nhớ. Các bản sửa áp dụng ngưỡng mặc định **10 MB** ở message factory và cho phép cấu hình `maxMessageSize`; ngưỡng mặc định này khác với hạn mức tệp nghiệp vụ của bài. Hãy dùng bản vá tương ứng với nhánh đang triển khai và cấu hình thông số theo tài liệu đúng version. Không bỏ giới hạn ở proxy ngay cả khi đã có bản vá.

Cần xem xét thêm:

- **Số yêu cầu đồng thời, timeout, tốc độ upload và quota đĩa:** 100 request cùng ghi tệp 5 MiB có thể tạm chiếm khoảng 500 MiB đĩa, chưa kể bộ đệm ở SOAP stack. Dùng rate limit, connection timeout, số worker có giới hạn và giám sát thư mục tạm.
- **Tổng số phần MIME, header MIME và phần dư:** nếu hợp đồng cho phép nhiều binary element, giới hạn từng phần, tổng phần và số attachment. Cấu hình gateway/parser để không tiếp nhận vô hạn MIME part không tham chiếu.
- **XML và thông tin đầu vào:** giới hạn XML depth/entity expansion, tắt external entity/DTD khi không cần, validate XSD, không tin `Content-Type`, `fileName`, `Content-ID` và `declaredSize` như dữ liệu đã xác minh.
- **An toàn kênh tích hợp:** TLS, xác thực/mTLS hoặc WS-Security theo hợp đồng; xác minh chữ ký và chứng chỉ ở lớp phù hợp. SHA-256 trong body kiểm tra tính toàn vẹn so với giá trị do **cùng người gửi cung cấp**; bản thân nó không xác thực danh tính và không thay chữ ký số.
- **Không giải nén ngay khi upload:** tệp nén có thể nhỏ trên mạng nhưng nở cực lớn. Nếu xử lý archive, phải có quota riêng cho kích thước sau giải nén và số lượng entry.

### Khi nào bắt buộc kiểm tra có MTOM trên dây?

`mtomEnabled=true` cho phép marshaller tối ưu các giá trị nhị phân phù hợp; nó không chứng minh từng request luôn mang `multipart/related`. Nếu hợp đồng **bắt buộc dùng MTOM**, hãy xác nhận `Content-Type` ở lớp HTTP, kiểm tra dạng XOP package trong message factory/interceptor tương thích, và kiểm tra tham chiếu `cid:` thực sự khớp MIME part. Không kiểm tra bằng cách chỉ nhìn dữ liệu `DataHandler`, vì binary có thể được gửi Base64 inline rồi được JAXB chuyển thành cùng một kiểu logic.

## 9. Kịch bản kiểm thử tích hợp

Chuẩn bị client SOAP có MTOM (Spring-WS `WebServiceTemplate`, SoapUI hoặc công cụ tương đương). Với các trường hợp thành công, ngoài SOAP response còn phải kiểm tra **byte đã lưu**, **kích thước**, **digest** và **wire format**.

| Tình huống | Dữ liệu gửi | Kỳ vọng |
|---|---|---|
| Tệp rỗng | 0 byte, SHA-256 của rỗng, `declaredSize=0` | Chấp nhận nếu chính sách cho phép tệp rỗng; bản lưu có 0 byte |
| Tệp nhỏ | 4 byte, metadata và SHA đúng | SOAP response có `receiptId`, bản lưu giống từng byte |
| Sát giới hạn | 5.242.880 byte | Thành công nếu tổng request vẫn dưới ngưỡng HTTP |
| Vượt đúng 1 byte | 5.242.881 byte, khai đúng | SOAP `Client` fault ở tầng nghiệp vụ, không có file hoàn tất |
| Khai báo thấp hơn thực tế | 5 MiB + 1 byte nhưng `declaredSize=1` | Phát hiện khi đọc luồng, từ chối và dọn `.part` |
| Khai báo cao hơn thực tế | 1 KiB thực, khai 2 KiB | Từ chối sau khi đọc, không tạo receipt |
| Sai SHA-256 | 1 KiB, chuỗi hex hợp lệ nhưng khác digest | Từ chối; dữ liệu tạm bị xóa |
| Không hợp lệ về tên tệp | `../a.pdf`, `..\a.pdf` hoặc đường dẫn tuyệt đối | SOAP `Client` fault, không được ghi ngoài upload-dir |
| Thiếu tệp | XML thiếu `content` hoặc MIME CID bị mất | Lỗi schema/MIME/SOAP; không được tạo receipt |
| Chỉ bật MTOM ở client | Client tối ưu XOP, server dùng JAXB processor mặc định | Bài kiểm thử phải phát hiện lỗi attachment rỗng; sửa cấu hình server |
| Gửi Base64 inline | Cùng giá trị byte nhưng không có MIME part | Xử lý theo chính sách tích hợp; nếu yêu cầu MTOM bắt buộc thì từ chối |
| HTTP request vượt 8 MiB | MIME hoặc XML tổng lớn | Gateway trả giới hạn request (thường HTTP 413) trước khi gọi endpoint |
| Hai request đồng thời | Hai tệp hợp lệ, `documentId` khác nhau | Không trộn nội dung; hai receipt riêng, không giữ tệp tạm thừa |
| Mất kết nối giữa lúc upload | Stream bị ngắt đột ngột | Không xác nhận thành công; không lưu bản hoàn tất |

Cách kiểm tra **thực sự là MTOM**:

1. Dùng client gửi một tệp có nội dung đã biết và capture HTTP request trong môi trường test với dữ liệu giả.
2. Kiểm tra `Content-Type: multipart/related` cùng `type="application/xop+xml"`.
3. Trong root XML, kiểm tra `xop:Include href="cid:..."`; trong các MIME part, tìm `Content-ID` tương ứng và `Content-Type: application/octet-stream`.
4. Đọc file server lưu và tính SHA-256 độc lập. So sánh với digest gửi trong request và byte của file client.
5. Tắt `setMtomEnabled(true)` để thấy sự khác biệt trên wire; không dùng kết quả round-trip thành công làm bằng chứng duy nhất rằng MTOM đã hoạt động.

Trong kiểm thử tự động, tách **kiểm thử service** (byte, hash, validation) khỏi **kiểm thử truyền tải thật** (HTTP multipart MIME/XOP), vì một số mock của Spring-WS bỏ qua bước tuần tự hóa thực tế.

## 10. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| `DataHandler` tồn tại nhưng `InputStream` rỗng | Default JAXB processor của `@EnableWs` chạy trước processor MTOM | Đăng ký `MarshallingPayloadMethodProcessor` bật MTOM ở vị trí ưu tiên |
| Phần tử `content` thành `byte[]` | JAXB/XJC không nhận `xmime:expectedContentTypes` hoặc binding không đúng | Kiểm tra XSD, plugin sinh class và `DataHandler` mapping |
| WSDL đúng nhưng client vẫn gửi Base64 | Client chưa bật MTOM, hoặc thư viện không tối ưu dữ liệu được cung cấp | Kiểm tra marshaller phía client và capture request |
| HTTP 413 dù tệp nhỏ hơn 5 MiB | Tổng SOAP/MIME vượt `8m`, hoặc giới hạn ở gateway khác nhỏ hơn | Đo byte toàn request và chỉnh các ngưỡng có chủ đích |
| `Content-ID` không khớp | Tham chiếu `cid:` hỏng/khác biệt do tool tạo MIME | Kiểm tra nguyên văn MIME parts và serializer |
| SOAP Fault không rõ lý do | Lỗi ở parser, schema, business validation hay disk I/O | Theo dõi log có request ID, loại lỗi và số byte; không log file nhị phân |
| Đĩa đầy hoặc nhiều `.part` | Không dọn dữ liệu tạm, lưu tạm sai filesystem, quota/timeout yếu | Dọn trong `finally`, job quét tệp mồ côi, giám sát quota |

## 11. Tiêu chí hoàn thành bài thực hành

Bài được coi là đạt khi bạn có một SOAP service contract-first với XSD/WSDL ổn định; JAXB sinh kiểu thích hợp cho binary; server/client dùng MTOM đúng cách; bản ghi trên dây thể hiện MIME/XOP; bản lưu trùng tuyệt đối với file gốc và chỉ công nhận sau khi xác minh số byte + SHA-256. Yêu cầu vượt ngưỡng phải bị chặn đúng lớp, không để tệp hoàn tất; thử ngắt upload không làm tồn tại bản lưu dở dang. Cuối cùng, ngưỡng tại gateway, message factory, service, disk quota và concurrency phải nhất quán trong triển khai.

### Tài liệu tham khảo

- [Spring Web Services Reference — MTOM](https://docs.spring.io/spring-ws/docs/current/reference/html/#_mtom): cấu hình `Jaxb2Marshaller`, `MarshallingPayloadMethodProcessor` và vấn đề JAXB processor mặc định.
- [Spring Framework — `Jaxb2Marshaller`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html): `setMtomEnabled` và JAXB mapping.
- [W3C — SOAP Message Transmission Optimization Mechanism](https://www.w3.org/TR/soap12-mtom/): định dạng MTOM/XOP; [SOAP 1.1 Binding for MTOM](https://www.w3.org/submissions/soap11mtom10/).
- [W3C — XML-binary Optimized Packaging](https://www.w3.org/TR/xop10/): `xop:Include`, MIME part và tham chiếu CID.
- [Spring Security Advisory — CVE-2026-59349 (19/11/2026)](https://spring.io/security/cve-2026-59349/): giới hạn kích thước thông điệp trước khi phân tích SOAP và các nhánh đã được vá.
