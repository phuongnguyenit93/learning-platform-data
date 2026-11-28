# Giới hạn kích thước, bộ đệm, tệp tạm và vòng đời luồng dữ liệu

Với **Spring Web Services (Spring-WS)**, việc gửi SOAP request/response nhỏ bằng XML khá đơn giản. Nhưng một dịch vụ tích hợp chứng từ PDF, ảnh, bản vẽ, biên nhận hoặc hồ sơ doanh nghiệp thường phải xử lý **SOAP attachments** có kích thước hàng chục MiB, đôi khi có nhiều tệp trên một request. Trong tình huống đó, tính đúng đắn của JAXB/XSD/WSDL mới chỉ là một phần: backend còn phải bảo vệ **heap, bộ đệm, ổ đĩa tạm, file descriptors, kết nối, thời gian xử lý và dữ liệu nhạy cảm**.

Bài thuộc chương **Tệp đính kèm** trong module `SPRING_WEB_SERVICES`, đặt trong bối cảnh **contract-first**: XSD/WSDL quy định cấu trúc request/response; JAXB/OXM ánh xạ XML; endpoint và `WebServiceTemplate` giao tiếp SOAP; `MimeMessage`/`Attachment` cung cấp truy cập tệp nhị phân. Các lớp SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích giúp quy trình upload/download an toàn, ổn định khi tích hợp hệ thống doanh nghiệp.

**Thông điệp chính:** *giới hạn HTTP không thay thế kiểm tra kích thước attachment thật; bộ đệm 64 KiB ở endpoint không chứng minh toàn pipeline streaming; tệp tạm không tự bảo đảm cleanup sau crash; và `InputStream` thuộc attachment không được giữ ngoài vòng đời SOAP exchange.*

Ví dụ dùng Java 17+, Spring-WS 4.1.x, Jakarta JAXB. Các quota chỉ **minh họa**, không phải mặc định của Spring Boot hay Spring-WS. Mã có phụ thuộc ứng dụng được chú thích rõ. Với các đảm bảo của message factory, luôn kiểm tra phiên bản/provider thực tế trước production.

## Mục tiêu học tập

1. Phân biệt SOAP Body, SwA, MIME multipart, MTOM/XOP, `xs:base64Binary` và `DataHandler`.
2. Thiết lập giới hạn **HTTP entity, XML payload, số MIME parts, kích thước từng part, tổng bytes, dung lượng tạm và concurrency**.
3. Hiểu `getSize() == -1`, `Content-Length` không tin cậy tuyệt đối và vì sao phải đếm byte thật.
4. So sánh `SaajSoapMessageFactory` với `AxiomSoapMessageFactory` và các knobs cache.
5. Quản lý `InputStream`, `InputStreamSource`, `DataHandler` và tệp nguồn gửi đi theo đúng ownership.
6. Viết bộ đọc có **bounded buffering, try-with-resources, checksum, tệp staging và cleanup**.
7. Xử lý lỗi file quá lớn, disconnect, timeout, ổ tạm đầy, partial upload và quét file.
8. Phân biệt tệp tạm của thư viện, staging của ứng dụng và object đã lưu bền vững.
9. Kiểm thử memory/disk/concurrency, SOAP Fault, XML security, WS-Security, transport và tương thích client.

## 1. Tình huống UploadDocument có tệp PDF

Đối tác gửi thao tác `UploadDocument` qua SOAP. Body chứa metadata, còn tệp PDF nằm trong một MIME part:

~~~xml
<doc:UploadDocumentRequest xmlns:doc="urn:example:documents:v1">
  <doc:requestId>REQ-2026-001</doc:requestId>
  <doc:documentId>DOC-42</doc:documentId>
  <doc:contentId>invoice-42@example.test</doc:contentId>
  <doc:declaredSize>15728640</doc:declaredSize>
  <doc:sha256>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</doc:sha256>
</doc:UploadDocumentRequest>
~~~

Đây là **Body metadata theo một hợp đồng SwA minh họa**; `contentId` ánh xạ tới MIME `Content-ID` theo quy tắc ứng dụng. Nó **không phải** XML chuẩn cho mọi MTOM service. Nếu dùng MTOM/XOP, Body có thể chứa phần tử `xs:base64Binary` với `xop:Include href="cid:..."` và JAXB mapping khác.

Giả sử PDF đúng **15 MiB**; `declaredSize` do client tự khai báo chỉ là chỉ dấu. Backend vẫn phải kiểm tra kích thước **thực** của stream. Một client có thể truyền `Content-Length` sai, không gửi Content-Length (chunked), hoặc bị ngắt kết nối khi đang chuyển file.

### 1.1. Dòng đời và các nơi phát sinh chi phí

~~~mermaid
flowchart TD
    A["SOAP client + binary source"] --> B["TLS / gateway / HTTP connector"]
    B --> C["MIME parser + SOAP message factory"]
    C --> D["Endpoint: XSD / metadata / authorization"]
    D --> E["Bounded stream copy"]
    E --> F["Application staging file"]
    F --> G["Hash + type scan + malware policy"]
    G --> H["Durable object/quarantine storage"]
    H --> I["DB status + SOAP response"]
    E -. "Too large / IOException" .-> X["Close + delete app temp"]
    G -. "Rejected" .-> X
~~~

Nếu parser đã nạp toàn bộ attachment lên heap **trước** khi endpoint copy bằng buffer 64 KiB, endpoint vẫn có thể là nguồn tăng heap đáng kể. Cần đo mọi lớp, không chỉ `Files.copy`.

### 1.2. Bốn số đo không tương đương

| Khái niệm | Nội dung | Ranh giới |
| --- | --- | --- |
| HTTP wire bytes | Headers, SOAP Envelope, MIME boundaries, file parts | Gateway/transport |
| XML payload bytes | XML được parse, có thể chứa base64 text | XML parser/XSD |
| Attachment decoded bytes | Bytes thật từ `Attachment.getInputStream()` | Application quota |
| Durable object bytes | Bytes đã lưu sau xử lý/transform/scan | Storage/quota |

Base64 trong SOAP XML thường tăng kích thước trên dây xấp xỉ **4/3** so với binary thô (chưa cộng XML overhead). SwA hoặc MTOM/XOP có thể tránh overhead này trên wire, nhưng **không hứa zero-copy end-to-end**.

## 2. MIME multipart, SwA và MTOM/XOP

Một thông điệp SwA thường có `multipart/related`: root MIME part chứa SOAP Envelope, các part khác chứa binary:

~~~text
HTTP Content-Type: multipart/related; boundary="b-001"; ...

--b-001
Content-Type: text/xml; charset=UTF-8
Content-ID: <root@example.test>

<soap:Envelope>... metadata ...</soap:Envelope>

--b-001
Content-Type: application/pdf
Content-ID: <invoice-42@example.test>

<binary PDF bytes>
--b-001--
~~~

Đây là **sơ đồ**, không phải MIME stream hoàn chỉnh: CRLF, transfer encoding, root start parameter và `Content-Type` phụ thuộc SOAP version phải do thư viện định dạng. SOAP 1.1 và SOAP 1.2 có root-part media types khác nhau.

### 2.1. SwA thủ công vs MTOM

| Tiêu chí | SwA attachment riêng | MTOM/XOP |
| --- | --- | --- |
| Body XML | Có thể tự chứa tham chiếu `Content-ID` theo profile | Chứa binary value logic `xs:base64Binary` |
| Binary part | MIME attachment riêng | XOP package MIME part được tham chiếu bởi `xop:Include` |
| WSDL/XSD | Cần mô tả MIME attachment contract/profile | XML Infoset tương ứng schema base64Binary |
| Java API | `MimeMessage.getAttachments()`, `addAttachment(...)` | `Jaxb2Marshaller`/JAXB `DataHandler` hoặc `byte[]` |
| Tối ưu memory | Phụ thuộc provider và code | Phụ thuộc mapping, serializer, provider |
| Có limit file tự động? | **Không** | **Không** |

Dùng `Jaxb2Marshaller.setMtomEnabled(true)` giúp OXM hỗ trợ MTOM. Nhưng chỉ bật flag **không chứng minh** binary đang được gửi thành MIME part hoặc payload lớn sẽ không bị materialize thành `byte[]`. Kiểm tra Content-Type multipart, `xop:Include`, MIME part và peak heap trên đường truyền thực tế.

### 2.2. Contract-first XSD minh họa

~~~xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:d="urn:example:documents:v1"
    targetNamespace="urn:example:documents:v1"
    elementFormDefault="qualified">
  <xs:element name="UploadDocumentRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="xs:string"/>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="contentId" type="xs:string"/>
        <xs:element name="declaredSize" type="xs:nonNegativeInteger"/>
        <xs:element name="sha256" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
  <xs:element name="UploadDocumentResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="documentId" type="xs:string"/>
        <xs:element name="state" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Đây là **XSD Body** cho ví dụ SwA, **không tự ràng buộc MIME parts**. `maxLength` của `contentId` hoặc `sha256` không giới hạn PDF. Cần WSDL/SOAP MIME binding hoặc profile thỏa thuận với đối tác, cộng với size/security policy runtime. Với MTOM, một hợp đồng khác có thể dùng `<xs:element name="documentBytes" type="xs:base64Binary"/>`; hai hợp đồng phải được phân biệt rõ.

`Content-Type: application/pdf` và tên `.pdf` là **dữ liệu do client khai báo**, không chứng minh file thật là PDF. Dùng content sniffing an toàn, hash, scanner và whitelist types theo nghiệp vụ; không chạy executable hoặc parser không tin cậy trên file chưa qua chính sách.

## 3. Bảo vệ bằng giới hạn ở từng lớp

Không có một setter duy nhất trên `@Endpoint` hoặc `WebServiceTemplate` đủ để giới hạn mọi khía cạnh của SOAP attachment:

| Lớp | Ví dụ limit | Lý do |
| --- | --- | --- |
| Gateway/WAF | Max HTTP request entity, rate limit, timeout | Chặn sớm trước JVM |
| HTTP connector | Request size, header limit, read timeouts | Chống giữ connection lâu |
| MIME decoder | Số part, MIME headers, nesting | Chống hàng nghìn parts |
| XML parser | Payload bytes, độ sâu, entity/DTD | XML DoS/XXE |
| SOAP endpoint | Attachment count, mỗi part size | Bảo vệ use case |
| Mỗi stream | Đếm decoded bytes thực tế | Không tin declared size |
| Tổng request | Tổng decoded bytes qua tất cả parts | Tránh N files gần trần |
| Memory | Bounded buffers và max in-flight requests | Tránh OOM |
| Temp disk | Quota theo request/tenant/global | Tránh đầy disk và inode |
| Durable storage | Max object size, lifecycle, retention | Ngăn chiếm chỗ dài hạn |
| Outbound response | Max attachments, thời gian ghi | Không gây download DoS |

**Ví dụ policy (không phải cấu hình Spring Boot thật):**

~~~yaml
uploadPolicy:
  httpEntityLimitBytes: 29360128       # 28 MiB
  soapXmlLimitBytes: 262144            # 256 KiB
  attachmentCountLimit: 2
  singleAttachmentLimitBytes: 20971520 # 20 MiB
  totalDecodedLimitBytes: 25165824     # 24 MiB
  maxConcurrentRequests: 20
  copyBufferBytes: 65536               # 64 KiB
  tempGlobalQuotaBytes: 536870912      # 512 MiB
~~~

Các con số phải **được áp thật** ở gateway/provider/Java, đo theo SLA và điều chỉnh đủ headroom cho MIME overhead. Một policy minh họa không tự bật limit. Không giả định `spring.servlet.multipart.max-file-size` luôn áp cho SOAP `multipart/related`: nhiều Servlet multipart handlers chủ yếu áp cho `multipart/form-data`, còn SOAP có đường MIME parser riêng.

### 3.1. Cần phân biệt byte units

- 1 KiB = 1024 bytes, 1 MiB = 1048576 bytes.
- 20 MiB tương ứng `20L * 1024 * 1024`, không phải 20.000 bytes.
- 20 MiB binary thành base64 trong Body cần gần 26,7 MiB ký tự trước XML overhead.
- `maxConcurrentRequests × copyBufferBytes` chỉ là **buffer Java của phần copy**, chưa cộng parser, JAXB, transport buffers, threads và caches.
- Nếu 20 uploads có thể spool mỗi request tối đa 20 MiB, disk staging có thể cần ít nhất khoảng 400 MiB **chỉ cho data chính**, chưa tính MIME cache của provider và crash leftovers.

### 3.2. Không tin Content-Length hoặc declaredSize là đủ

`Content-Length` có thể không có khi HTTP chunked, bị thay đổi khi proxy/decompression, hoặc là size của **multipart entity** chứ không phải từng file. `declaredSize` do client khai báo có thể sai. Spring-WS `Attachment.getSize()` trả **`-1` nếu không xác định được kích thước**. Cả ba đều chỉ giúp **reject sớm**; vẫn phải giới hạn bằng đếm số bytes thật từ `InputStream`.

Nếu hệ thống giải nén ZIP/gzip, cần giới hạn cả **compressed** và **decompressed** bytes, entry count, nesting depth, extraction path để chống zip bombs. Việc chặn HTTP 28 MiB không ngăn một file ZIP nhỏ bung ra nhiều GiB.

## 4. RAM và buffering trong message factory

### 4.1. SAAJ/DOM

`SaajSoapMessageFactory` dựa trên SAAJ/DOM; SOAP XML message tree được giữ trong memory. Các MIME part cũng có thể đi qua memory/temporary storage tùy Jakarta SAAJ implementation. **Không nên tuyên bố** mọi provider SAAJ luôn chứa nguyên mọi attachment trong một `byte[]`, nhưng cần đo heap vì DOM/XML, JAXB, logging và buffer có thể chồng lên nhau.

~~~text
TCP/TLS → HTTP parser → MIME headers/parts
                    → SOAP DOM hoặc StAX cursor
                    → JAXB / DataHandler / byte arrays
                    → application buffer / temp staging
~~~

Một pipeline có thể tạo nhiều bản sao dữ liệu ở những bước này, nhưng **không nhất thiết bước nào cũng copy**. Muốn biết memory thực tế phải đo bằng profiler và integration test với đúng provider/message factory.

### 4.2. Tránh readAllBytes() trên dữ liệu không giới hạn

~~~java
// SAI: không limit, không đóng stream và có thể OOM.
byte[] whole = attachment.getInputStream().readAllBytes();
saveToDatabase(whole);
~~~

Ngay cả dùng `try-with-resources` để đóng stream, `readAllBytes()` vẫn có thể tạo `byte[]` lớn không kiểm soát. Chỉ dùng array cho tài liệu **rất nhỏ đã bị giới hạn chặt**, còn tệp lớn dùng copy stream có limit và staging.

### 4.3. Nguồn dữ liệu dùng chung

| Resource | Đặc tính | Dùng khi |
| --- | --- | --- |
| `ByteArrayResource` | Giữ bytes trên heap, mở stream mới mỗi lần | File nhỏ |
| `FileSystemResource` | Có thể mở stream mới từ tệp mỗi lần | Tệp nguồn tồn tại đến hết send |
| `InputStreamResource` | Thường single-use stream | **Không phù hợp** khi serializer cần mở nhiều lần |
| `InputStreamSource` tùy biến | Phải trả stream mới trên mỗi `getInputStream()` | Nguồn replayable, ownership rõ |
| `jakarta.activation.DataHandler` | DataSource abstraction cho MIME/JAXB | SwA/MTOM; phụ thuộc implementation |

Theo `MimeMessage.addAttachment(contentId, InputStreamSource, contentType)`, underlying MIME provider **có thể gọi `getInputStream()` nhiều lần**. Vì vậy truyền một `InputStreamResource` đang trỏ tới single-use stream có nguy cơ đọc thiếu dữ liệu ở lần serialize thứ hai.

## 5. Axiom caching và trade-off streaming

`AxiomSoapMessageFactory` dựa trên AXIOM/StAX, có các cấu hình API chính:

| Setter | Default ở Spring-WS 4.1.x | Nghĩa |
| --- | --- | --- |
| `setPayloadCaching(boolean)` | `true` | Cho phép đọc lại SOAP Body |
| `setAttachmentCaching(boolean)` | `false` | Cache attachment lớn xuống disk |
| `setAttachmentCacheThreshold(int)` | 4096 bytes | Ngưỡng chuyển attachment cache sang disk |
| `setAttachmentCacheDir(File)` | `java.io.tmpdir` | Chọn thư mục MIME attachment cache |

**Hai loại caching độc lập.** Attachment caching xuống đĩa giúp giảm chi phí memory nhưng không tự giới hạn số bytes. `attachmentCacheThreshold=65536` nghĩa là **spool khi lớn hơn 64 KiB** (nếu attachmentCaching bật), **không có nghĩa từ chối tệp >64 KiB**.

### 5.1. Ví dụ tạo AxiomSoapMessageFactory

~~~java
import java.io.File;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.axiom.AxiomSoapMessageFactory;

@Configuration(proxyBeanMethods = false)
class SoapMessageFactoryConfig {
    @Bean
    AxiomSoapMessageFactory messageFactory() {
        AxiomSoapMessageFactory factory =
            new AxiomSoapMessageFactory();
        factory.setPayloadCaching(true);
        factory.setAttachmentCaching(true);
        factory.setAttachmentCacheThreshold(64 * 1024);
        factory.setAttachmentCacheDir(
            new File("/var/lib/soap/attachment-cache"));
        return factory;
    }
}
~~~

Directory ví dụ phải **tồn tại, writable, permissions hạn chế và được monitor**. Dependency AXIOM cần phù hợp Spring-WS/runtime. Với Spring Boot, tránh khai báo trùng bean messageFactory mà không hiểu auto-configuration. Provider/serializer có thể chọn cách tối ưu khác nhau, nên kiểm throughput, memory, disk bằng test thực.

### 5.2. Tắt payloadCaching có thể phá luồng validation

~~~java
factory.setPayloadCaching(false);
~~~

Theo tài liệu chính thức, `payloadCaching=false` cho SOAP Body chỉ **đọc được một lần**. Những thành phần đọc Body trước endpoint như `PayloadRootAnnotationMethodEndpointMapping`, `PayloadValidatingInterceptor` và `PayloadLoggingInterceptor` không hoạt động theo cùng flow vì chúng tiêu thụ stream. Nếu thực sự cần single-pass processing, hãy chọn endpoint mapping không đọc Body (chẳng hạn dựa SOAPAction) và thiết kế validation/logging phù hợp. **Không giảm RAM bằng cách vô tình bỏ validation.**

### 5.3. Temp cache của thư viện khác staging do ứng dụng tạo

| Loại tệp | Owner | Cleanup |
| --- | --- | --- |
| AXIOM attachment cache | MIME/message factory/provider | Theo lifecycle provider, monitor orphan |
| HTTP/container temp | Transport/Servlet | Theo container contract/config |
| Application staging temp | **Ứng dụng** | `try/finally`, delete nếu không promote |
| Persisted business object | Storage/ứng dụng | Retention, quota, GC |
| Outbound source file | Ứng dụng phía client | Giữ tồn tại đến khi transport hoàn tất |

**Không dọn toàn bộ `java.io.tmpdir`** ở cuối một SOAP request: có file từ các requests khác và thư viện khác. Cũng không khẳng định temp cache nhà cung cấp sẽ được dọn chắc chắn khi process crash; cần monitoring, ownership, retention và cơ chế dọn orphan theo policy.
## 6. InputStream: ai mở, ai đóng và thời điểm nào?

Spring-WS API:

~~~text
org.springframework.ws.mime.MimeMessage
  getAttachments()                                      Iterator<Attachment>
  getAttachment(String contentId)                        Attachment hoặc null
  addAttachment(String contentId, File file)
  addAttachment(String contentId, InputStreamSource src, String type)
  addAttachment(String contentId, DataHandler handler)

org.springframework.ws.mime.Attachment
  getContentId()                                         String
  getContentType()                                       String
  getSize()                                              long (có thể -1)
  getInputStream()                                       InputStream
  getDataHandler()                                       jakarta.activation.DataHandler
~~~

Theo Javadoc Spring-WS, **người gọi `Attachment.getInputStream()` có trách nhiệm đóng stream**. Sử dụng `try-with-resources` ở vị trí đọc:

~~~java
try (InputStream in = attachment.getInputStream()) {
    // Read/copy một cách có giới hạn khi SOAP message còn hợp lệ.
}
~~~

Không trả `InputStream` từ endpoint rồi gửi sang `@Async` worker; khi response đã được phát, message factory, HTTP connection hoặc temp cache có thể giải phóng nội dung. Nếu cần xử lý bất đồng bộ, **trước khi trả acknowledgement** phải lưu payload vào một nơi bền vững có policy rõ, rồi truyền cho worker một **immutable reference**, không truyền stream mở.

### 6.1. Bảng ownership

| Resource | Chủ sở hữu | Mốc phải đóng hoặc giữ |
| --- | --- | --- |
| InputStream trả từ `Attachment.getInputStream()` | **Code gọi phương thức** | Đóng ngay trong cùng xử lý bằng try-with-resources |
| `MimeMessage` / `SoapMessage` / `MessageContext` | Spring-WS/message factory | Một SOAP exchange; không giữ sau khi request kết thúc |
| HTTP connection do `WebServiceTemplate` quản lý | Transport/template | Framework xử lý đóng/hoàn trả pool theo lifecycle |
| Local Java `byte[]`/buffer 64 KiB | Application | Không cache mỗi request lâu dài; GC sau khi xong |
| Application `Files.createTempFile` | **Application** | Delete khi fail, promote hoặc retain có chủ đích |
| Axiom temp MIME cache | Provider | Dựa vào lifecycle provider; monitor orphan files |
| Source file dùng `addAttachment(...)` outbound | Application/client | **Phải tồn tại cho tới khi serialization/send kết thúc** |
| Object store/quarantine file | Storage/application | Theo retention, ACL và trạng thái workflow |

Một nguồn `InputStreamSource` phải mở **stream mới mỗi lần `getInputStream()` được gọi**; không bọc một `InputStream` đã tiêu thụ rồi trả về mãi. Ngược lại, nếu bạn **đã nhận** một stream qua `Attachment.getInputStream()`, hãy đóng nó sau xử lý thay vì giả định HTTP container sẽ làm hộ.

### 6.2. Đọc một lần hay đọc nhiều lần?

Provider có thể cache để hỗ trợ đọc lại, nhưng không nên thiết kế nghiệp vụ bắt buộc đọc ba lần cùng một source mà API không cam kết replayability. Quy trình gọn:

~~~text
MIME attachment stream
   ↓ một lượt duy nhất, có giới hạn
Application staging file + SHA-256
   ↓ mở lại từ staged file (resource do ứng dụng sở hữu)
Scanner / file signature validation
   ↓ nếu hợp lệ
Promote to durable store / quarantine
~~~

Cách này tập trung rủi ro I/O vào một lớp, có thể enforce byte cap chính xác và truy dấu mỗi file bằng checksum mà không giữ cả tệp trên heap.

### 6.3. Điểm nguy hiểm của stream single-use

Đừng truyền một `InputStreamResource` từ luồng đã mở vào `MimeMessage.addAttachment(String, InputStreamSource, String)` rồi trông chờ serialization đọc nhiều lần thành công. Javadoc Spring-WS nói rõ provider **có thể gọi `getInputStream()` nhiều lần**.

- `FileSystemResource` thường phù hợp hơn khi tệp đã tồn tại và owner giữ nó tới cuối send.
- `ByteArrayResource` tạo fresh stream nhưng giữ toàn bộ bytes trong RAM; chỉ dùng cho tệp nhỏ đã giới hạn.
- Custom `InputStreamSource` phải chủ động cung cấp nguồn replayable và quy định lifecycle.
- `DataHandler` chỉ là abstraction; một DataSource custom có thể vẫn single-use nếu hiện thực sai.

## 7. Bộ copy có giới hạn: không phụ thuộc getSize

Dưới đây là hàm Java có thể dùng trong một ingestion service. Nó không đọc toàn bộ tệp thành mảng, chỉ dùng một buffer và dừng khi số bytes thực vượt ngưỡng.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;

public final class BoundedAttachmentCopy {
    private BoundedAttachmentCopy() {}

    public static long copy(
            InputStream source,
            OutputStream target,
            long maxBytes,
            MessageDigest digest) throws IOException {

        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be nonnegative");
        }

        byte[] buffer = new byte[64 * 1024];
        long total = 0;
        int read;

        while ((read = source.read(buffer)) != -1) {
            if (read == 0) {
                // Với buffer length > 0, không chấp nhận provider
                // liên tục trả zero bytes khiến CPU spin vô hạn.
                throw new IOException("Input stream made no progress");
            }
            // Tránh overflow của total + read.
            if (read > maxBytes - total) {
                throw new AttachmentTooLargeException(
                    "Attachment exceeds allowed size");
            }

            target.write(buffer, 0, read);
            digest.update(buffer, 0, read);
            total += read;
        }

        return total;
    }

    public static final class AttachmentTooLargeException
            extends IOException {
        public AttachmentTooLargeException(String message) {
            super(message);
        }
    }
}
~~~

Hàm này **không tự đóng** `source` và `target`, vì quyền sở hữu luồng được giao cho người gọi. `IOException` ở giữa vòng lặp không khiến file tạm tự xóa; wrapper gọi `copy` phải có `try-with-resources` và `finally`.

Kiểm tra `read > maxBytes - total` tránh tràn số khi cộng. Vì `total` luôn không âm và không vượt `maxBytes`, phép trừ hợp lệ. Dừng **ngay khi phát hiện vượt trần**, không tiếp tục ghi thêm bytes vào staging; dù đã đọc một chunk 64 KiB cuối, bytes được ghi tối đa vẫn đúng giới hạn.

### 7.1. Vì sao không chỉ `InputStream.transferTo`?

~~~java
// Không có built-in maxBytes: nếu source vô hạn hoặc rất lớn,
// việc copy này có thể đầy đĩa trước khi endpoint phát hiện lỗi.
try (InputStream in = attachment.getInputStream();
     OutputStream out = Files.newOutputStream(staging)) {
    in.transferTo(out);
}
~~~

`transferTo` hữu ích với nguồn tin cậy hoặc khi đã có một wrapper bounded thực sự. Nhưng trong SOAP attachment nhận từ bên ngoài, phải enforce quota trên **byte stream thực**; không dùng `getSize()` như điều kiện duy nhất rồi gọi `transferTo` vô giới hạn.

### 7.2. Giới hạn tổng nhiều attachments

Nếu operation chấp nhận hai file, không chỉ kiểm từng file `<= 20 MiB` mà còn kiểm **tổng `<= 24 MiB`**. Theo dõi `long remainingTotal`, và với mỗi file áp:

~~~java
long limitForThisPart = Math.min(
    maxSingleAttachmentBytes, remainingTotalBytes);

long copied = BoundedAttachmentCopy.copy(
    input, output, limitForThisPart, sha256);

remainingTotalBytes -= copied;
~~~

Cần cập nhật `remainingTotalBytes` **chỉ sau khi file đã được đọc đầy đủ và chấp nhận**, nếu lỗi phải xóa staged part. Với nhiều files, việc commit/trả response có thể là **all-or-nothing** hoặc partial acceptance theo WSDL; chọn rõ chính sách và không để một file hoàn tất “lọt” ra durable store khi cả batch phải rollback.

### 7.3. Đếm attachment trước khi mở stream

Trong operation cho phép **đúng một** MIME attachment:

~~~java
import java.util.Iterator;
import org.springframework.ws.mime.Attachment;
import org.springframework.ws.soap.SoapMessage;

public static Attachment requireSingleAttachment(SoapMessage soap) {
    Iterator<Attachment> parts = soap.getAttachments();

    if (!parts.hasNext()) {
        throw new IllegalArgumentException("Missing attachment");
    }

    Attachment attachment = parts.next();
    if (parts.hasNext()) {
        throw new IllegalArgumentException("Too many attachments");
    }

    return attachment;
}
~~~

Kiểm một attachment có thể chỉ được thực hiện **sau khi parser đã tạo danh sách MIME parts**. Vì vậy vẫn cần MIME parser/gateway limit để ngăn một request chứa hàng nghìn parts làm hao tài nguyên trước khi endpoint tới dòng này.

`Attachment.getContentId()` có thể có dạng có hoặc không có dấu ngoặc góc tùy provider. Nếu Body tham chiếu `cid:...`, cần xử lý quy tắc **RFC 2392** (URL-encoding) và kiểm duplicate IDs, namespace, type; đừng so bừa chuỗi mà không normalize/validate hoặc cho phép client chọn đường dẫn file từ Content-ID.

## 8. Xây staging file an toàn trong endpoint

Một thiết kế bền vững thường đặt phần copy/scan ở **application ingestion service**, còn `@Endpoint` nhận JAXB metadata và lấy stream từ `SoapMessage`. Bên dưới là khung xử lý minh họa có kiểm soát lifecycle:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import org.springframework.ws.mime.Attachment;

public final class AttachmentStager {

    private final Path privateStagingDirectory;
    private final long maxBytes;

    public AttachmentStager(
            Path privateStagingDirectory, long maxBytes) {
        this.privateStagingDirectory = privateStagingDirectory;
        this.maxBytes = maxBytes;
    }

    public StagedFile stage(Attachment part)
            throws IOException, NoSuchAlgorithmException {

        long sizeHint = part.getSize();
        if (sizeHint >= 0 && sizeHint > maxBytes) {
            throw new BoundedAttachmentCopy.AttachmentTooLargeException(
                "Attachment exceeds allowed size");
        }

        // Directory phải được provision/permission sẵn.
        Path temp = Files.createTempFile(
            privateStagingDirectory, "soap-", ".partial");
        boolean retained = false;

        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long size;

            try (InputStream in = part.getInputStream();
                 OutputStream out = Files.newOutputStream(temp)) {
                size = BoundedAttachmentCopy.copy(
                    in, out, maxBytes, digest);
            }

            String sha256 = java.util.HexFormat.of()
                .formatHex(digest.digest());

            StagedFile result = new StagedFile(
                temp, size, sha256);

            // Chuyển quyền sở hữu file sang caller; caller bắt
            // buộc cleanup/promote khi hoàn tất hoặc thất bại.
            retained = true;
            return result;
        }
        finally {
            if (!retained) {
                Files.deleteIfExists(temp);
            }
        }
    }

    public record StagedFile(
        Path path, long sizeBytes, String sha256) {}
}
~~~

`stage` làm nhiệm vụ lưu **tạm**, chưa hứa file hợp lệ về nội dung, không làm AV scan và chưa commit nghiệp vụ. Caller nhận `StagedFile` là **chủ sở hữu file mới**; phải dọn trong `finally` khi nghiệp vụ bị từ chối hoặc di chuyển sang kho bền vững.

Đoạn code không quy định permissions cho `privateStagingDirectory`. Trong production, provision directory riêng với user dịch vụ, umask/ACL hạn chế, quota, không dùng đường dẫn từ caller và không cho executable chạy tại vùng staging. Không tự tin vào tên file do client gửi; `Files.createTempFile` dùng tên ngẫu nhiên để tránh collision, path traversal và file overwrite.

### 8.1. Endpoint façade gọi staging service

~~~java
import java.nio.file.Files;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.SoapMessage;

@Endpoint
public final class UploadDocumentEndpoint {

    private final AttachmentStager stager;
    private final DocumentIngestionUseCase useCase;

    public UploadDocumentEndpoint(
            AttachmentStager stager,
            DocumentIngestionUseCase useCase) {
        this.stager = stager;
        this.useCase = useCase;
    }

    @PayloadRoot(
        namespace = "urn:example:documents:v1",
        localPart = "UploadDocumentRequest")
    @ResponsePayload
    public UploadDocumentResponse upload(
            @RequestPayload UploadDocumentRequest request,
            MessageContext context) throws Exception {

        // WS-Security/authorization cần hoàn tất theo policy.
        SoapMessage soap = (SoapMessage) context.getRequest();
        Attachment part = requireSingleAttachment(soap);

        // Cần kiểm Content-ID, type, declaredSize, policy
        // và duplicate detection theo contract thực tế.
        AttachmentStager.StagedFile staged =
            stager.stage(part);

        try {
            return useCase.acceptStagedDocument(
                request, staged);
        }
        finally {
            // Contract: useCase đã copy dữ liệu sang kho durable
            // hoặc đã từ chối, KHÔNG giữ path staging sau return.
            Files.deleteIfExists(staged.path());
        }
    }
}
~~~

Đây là **sơ đồ Java có application types giả định**: `UploadDocumentRequest`/`Response` do JAXB/XJC sinh, `DocumentIngestionUseCase` do dự án tự viết, `requireSingleAttachment` lấy từ helper mục 7.3 (cần static import hoặc gọi đúng class). Hợp đồng của ví dụ là **useCase xử lý hoàn tất đồng bộ và không giữ quyền sở hữu file staging**; vì vậy endpoint dọn file trong `finally`, kể cả thành công. Nếu useCase chỉ enqueue job, phải thay bằng **durable quarantine/ownership transfer** và thay mốc phản hồi; không được giữ path đã bị xóa.

Nếu muốn `move` staging vào vùng durable trên cùng filesystem, cần trạng thái `promoted` rõ và chỉ dọn source còn tồn tại. Không thiết kế kiểu “useCase có thể giữ file tùy ý” mà không có protocol ownership. Một lỗi dọn file sau khi use case đã commit có thể biến phản hồi thành lỗi dù tài liệu vẫn tồn tại; phải có idempotency/query status và logging cleanup thất bại thay vì suy diễn rollback.

### 8.2. Đúng thời điểm quét và công bố trạng thái

Với file nhạy cảm hoặc có nguy cơ malware:

1. Check WS-Security/TLS/authz + Body XSD/metadata theo policy.
2. Copy bounded sang vùng staging riêng/quarantine.
3. Validate checksum/định dạng/declared size; quét malware theo chính sách.
4. Nếu scan đồng bộ: chỉ promote file **sau khi đã qua scan**; rồi cập nhật metadata DB.
5. Nếu scan bất đồng bộ: durable quarantine/job phải được lưu **trước** khi trả `PENDING_SCAN`; không trả `AVAILABLE` khi chưa scan.
6. Chỉ cho download từ storage và với trạng thái/authorization phù hợp.

`sha256` giúp kiểm integrity nếu hash từ nguồn tin cậy và so đúng giá trị, **không tự xác thực danh tính client** và **không chứng minh file không chứa malware**. Nếu client tự gửi hash, cùng một attacker có thể tính hash cho file độc hại; cần WS-Security/authentication và file scanning độc lập.

## 9. Vòng đời tệp tạm: thất bại, crash và durable commit

### 9.1. Những mốc không được nhập làm một

~~~text
M1 HTTP receiver bắt đầu nhận multipart
  ↓
M2 MIME parser tạo Attachment
  ↓
M3 Application copy vào staging file xong
  ↓
M4 Checksum/type/AV policy hoàn tất
  ↓
M5 Durable object/quarantine storage xác nhận lưu
  ↓
M6 Database lưu trạng thái nghiệp vụ + idempotency
  ↓
M7 SOAP response đã viết/sent
  ↓
M8 Client đã nhận response
~~~

- **M3** không có nghĩa file đã lưu bền vững, vì staging có thể nằm trên ephemeral disk.
- **M5** không có nghĩa transaction database tự commit.
- **M6** không chứng minh SOAP response đã đến client.
- **M7** không chứng minh đối tác đã nhận/trong trường hợp network reset.
- **M8** thường không có xác nhận tuyệt đối từ phía server nếu không có protocol acknowledgement riêng.

Nếu response thất lạc sau khi storage/DB đã commit, client retry `UploadDocument` với **cùng business requestId** theo contract; server xử lý idempotently. Không tạo thêm document/version chỉ vì lần trước timeout.

### 9.2. Cleanup khi xử lý hoàn tất hoặc lỗi

Mẫu ownership **ứng dụng giữ staging**:

~~~java
AttachmentStager.StagedFile staged = stager.stage(part);
try {
    validateDeclaredSizeAndHash(request, staged);
    scanOrQuarantineAccordingToPolicy(staged);
    durableStorage.storeFromPath(staged.path());
    return saveMetadataAndBuildReceipt(request, staged);
}
finally {
    Files.deleteIfExists(staged.path());
}
~~~

Các method `validateDeclaredSizeAndHash`, `scanOrQuarantineAccordingToPolicy`, `durableStorage.storeFromPath` và `saveMetadataAndBuildReceipt` là **pseudocode application**, không phải API Spring-WS. Phải thiết kế error mapping nếu `deleteIfExists` thất bại; đừng che mất nguyên nhân chính của một failure bằng cleanup exception. Có thể log/metric file cleanup error và để job dọn orphan xử lý.

### 9.3. Atomic move không tạo giao dịch xuyên DB/object store

Nếu staging và durable directory cùng filesystem, `Files.move(..., ATOMIC_MOVE)` có thể hỗ trợ move atomic ở cấp filesystem khi provider hỗ trợ. Tuy nhiên:

- `ATOMIC_MOVE` có thể không được hỗ trợ; có thể ném `AtomicMoveNotSupportedException`.
- Atomic move không phải tương đương fsync/durability trước power loss.
- Atomic move không tự bảo đảm transaction metadata database.
- Object store `PUT` và database commit thường thuộc hai hệ thống khác nhau.

Để phối hợp, dùng state machine như `STAGED → SCANNING → AVAILABLE / REJECTED`, durable job/outbox và reconciliation/compensation. Không trả `AVAILABLE` trước khi độ bền và kiểm tra đã đạt điều kiện công bố. Với bản thân staging chỉ dùng khi đang xử lý đồng bộ, vùng temp có thể được xóa khi request hoàn tất; với job async cần **kho bền vững riêng**, không dùng temp directory làm queue.

### 9.4. Lỗi process crash không chạy finally

`finally` xử lý luồng control-flow bình thường/exception trong process, **không chạy khi `kill -9`, machine mất điện hoặc container bị hủy cưỡng bức**. Vì thế nếu do ứng dụng tạo tệp tạm, cần thêm:

- Quota/permissions của staging directory.
- Job dọn orphan theo **age + ownership + trạng thái** đã ghi; không xóa tệp của request khác đang hoạt động.
- TTL cho `STAGED`/`PENDING_SCAN`, reconciliation với DB/object store.
- Giới hạn disk/inodes và alert trên tốc độ tăng orphan files.
- Không lưu plaintext secret nếu không cần; cân nhắc encrypt-at-rest cho dữ liệu nhạy cảm.

Không dùng việc dọn theo timestamp đơn thuần khi request rất lâu hoặc đang bị treo; phối hợp heartbeat/state hoặc lease hợp lý.
## 10. SOAP client: gửi attachment không giữ cả file trong RAM

Ở phía `WebServiceTemplate`, có thể tạo SOAP Body bằng callback và thêm MIME part bằng `MimeMessage.addAttachment`.

### 10.1. FileSystemResource và Content-Type tường minh

~~~java
import java.nio.file.Path;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;

import org.springframework.core.io.FileSystemResource;
import org.springframework.xml.transform.StringSource;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.SoapMessage;

public final class DocumentSoapClient {
    private final WebServiceTemplate template;
    private final String uri;

    public DocumentSoapClient(WebServiceTemplate template, String uri) {
        this.template = template;
        this.uri = uri;
    }

    public Boolean send(
            Path sourcePath, String bodyXml, String contentId) {

        return template.sendAndReceive(
            uri,
            request -> {
                if (!(request instanceof SoapMessage soap)) {
                    throw new IllegalStateException("SOAP required");
                }

                Transformer tr = TransformerFactory
                    .newInstance().newTransformer();

                tr.transform(
                    new StringSource(bodyXml),
                    soap.getPayloadResult());

                soap.addAttachment(
                    contentId,
                    new FileSystemResource(sourcePath),
                    "application/pdf");
            },
            response -> {
                // Với response thực: parse QName, XSD, SOAP Fault
                // và dữ liệu nghiệp vụ theo contract.
                return Boolean.TRUE;
            });
    }
}
~~~

Ví dụ trên sử dụng overload `WebServiceTemplate.sendAndReceive(String uri, WebServiceMessageCallback, WebServiceMessageExtractor<T>)`. `bodyXml` được giả định là XML payload **đã được ứng dụng tạo theo XSD**, không được ghép từ chuỗi người dùng chưa escape/validate. Client production nên marshal JAXB object hoặc dùng XML writer an toàn để tránh XML injection.

**Lợi ích của `FileSystemResource`:** nó cung cấp một nguồn có thể mở stream mới khi MIME serializer cần; ứng dụng **không** phải gọi `Files.readAllBytes(sourcePath)` để biến file thành `ByteArrayResource`. Tuy nhiên, không hứa đường truyền zero-copy: serializer, SAAJ/Axiom và HTTP client có thể cache hoặc buffer ở các tầng khác.

### 10.2. Giữ tệp nguồn tới khi send hoàn thành

~~~java
Path tempSource = Files.createTempFile(
    privateOutboundDir, "soap-out-", ".pdf");

try {
    prepareValidatedPdf(tempSource);
    client.send(tempSource, safeBodyXml, contentId);
}
finally {
    Files.deleteIfExists(tempSource);
}
~~~

`prepareValidatedPdf` là application code giả định. Pattern này hợp lý với **sendAndReceive đồng bộ**: đợi method kết thúc hoặc ném exception rồi mới dọn tệp nguồn do ứng dụng tạo. Nếu client thực hiện **async send/queue** hoặc trả về trước khi serialization/transport xong, tệp nguồn phải **tồn tại và được sở hữu** đến mốc hoàn tất thực tế — không delete ngay khi enqueue.

Tương tự inbound, nếu `deleteIfExists` fail cần log/alert và orphan cleanup; trong code production nên giữ nguyên nguyên nhân lỗi chính khi cleanup cũng ném exception.

### 10.3. Vì sao không chỉ gọi addAttachment(File)?

`MimeMessage.addAttachment(String, File)` có API thật, nhưng Spring-WS Javadoc lưu ý **content type được suy từ tên file**. Nếu tên file tạm là `upload-123.tmp`, provider có thể suy sai type. Vì thế với tệp staging hoặc file tên không mô tả nội dung, dùng `addAttachment(String, InputStreamSource, String)` và **chỉ rõ Content-Type**. Dù type được chỉ định, server vẫn phải kiểm tra binary content; header do client gửi không đủ tin cậy.

### 10.4. HTTP streaming cũng phụ thuộc sender

Cùng một `WebServiceTemplate` có thể đi qua các HTTP senders khác nhau. Một sender có thể cần tính Content-Length trước khi gửi, buffer body hoặc dùng chunked transfer. Pooling và compression/transfer semantics phụ thuộc HTTP client. Hãy **kiểm tra byte stream thực tế và memory allocation** dưới load; đừng kết luận “FileSystemResource ⇒ HTTP streaming hoàn toàn” khi chưa đo.

Khi SOAP client được dùng bởi nhiều threads, file source và callback của từng invocation cần tách riêng; không lưu mutable `currentAttachment` hoặc `currentInputStream` vào field singleton.

## 11. JAXB/MTOM và DataHandler

Nếu hợp đồng sử dụng MTOM/XOP thay vì SwA thủ công, một payload có thể mang:

~~~xml
<doc:UploadMtomRequest
    xmlns:doc="urn:example:documents:v1"
    xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <doc:documentId>DOC-42</doc:documentId>
  <doc:documentBytes>
    <xop:Include href="cid:doc42@example.test"/>
  </doc:documentBytes>
</doc:UploadMtomRequest>
~~~

Đây là **XOP-serialized representation** của một giá trị XML binary theo contract, không nhất thiết là XML Body có thể validate như một document XSD tách rời khỏi XOP processing. `cid:doc42@example.test` tham chiếu một MIME part cùng thông điệp; xử lý RFC 2392 URL encoding và Content-ID theo provider. Đừng tự dựng XOP package bằng nối chuỗi; nên dùng Jakarta JAXB/Spring-WS khi có thể.

### 11.1. MTOM configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Bean
Jaxb2Marshaller documentMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.documents.contract.v1");
    marshaller.setMtomEnabled(true);
    return marshaller;
}
~~~

`Jaxb2Marshaller.setMtomEnabled(true)` là API Spring Framework OXM; mặc định **false**. Điều kiện sử dụng còn phụ thuộc SOAP message factory hỗ trợ MIME/XOP, JAXB classes, WS-I interoperability profile và test thực tế. Không tự suy rằng mọi `byte[]` sẽ được tách thành MIME part.

### 11.2. DataHandler, byte[] và memory

Một mapping JAXB minh họa khi XSD `xs:base64Binary` được ánh xạ phù hợp:

~~~java
import jakarta.activation.DataHandler;
import jakarta.xml.bind.annotation.XmlMimeType;

// Field trong một JAXB request type được cấu hình theo XSD:
@XmlMimeType("application/pdf")
private DataHandler documentBytes;
~~~

Đây là **fragment class**, không phải class hoàn chỉnh; XJC có thể sinh `byte[]` hoặc `DataHandler` tùy XSD annotation/binding. `@XmlMimeType` nói về MIME type mong muốn; tự nó không đặt byte cap hoặc quyền truy cập.

Nếu ánh xạ sang `byte[]`, unmarshalling có thể materialize toàn bộ file trên heap. `DataHandler` cho phép abstraction nguồn dữ liệu, nhưng một custom `DataSource` vẫn có thể đọc toàn bộ file; **dùng DataHandler không tự cam kết streaming**. Kiểm tra provider, binding, lifecycle và memory profile.

Đặc biệt, với WSS4J WS-Security bảo vệ attachment, kiểm tra handler/crypto và profile hợp lệ; raw `DataHandler` chưa được xác thực chỉ vì nó có mặt trong payload.

### 11.3. Hợp đồng hóa kích thước và kiểu dữ liệu

Với contract-first:

- XSD mô tả trường metadata như `documentId`, `mediaType`, `sha256`, `declaredSize` và binary field nếu dùng MTOM.
- WSDL binding/profile mô tả cách gửi attachment/MTOM, SOAP 1.1/1.2 và các chính sách bắt buộc nếu có.
- **Giới hạn bytes** cần được viết rõ trong tài liệu giao diện và enforce **ở runtime**, vì XSD `maxLength` của một chuỗi không đủ bảo vệ MIME stream.
- Client và server cùng thử file nhỏ, đúng trần, vượt trần và Content-ID không hợp lệ để phát hiện chênh lệch serialization.

## 12. SOAP Fault và lỗi tài nguyên phải xử lý khác nhau

### 12.1. Không phải lỗi nào cũng sinh SOAP Fault

| Lỗi | Xảy ra ở đâu? | Client có thể thấy |
| --- | --- | --- |
| HTTP request vượt trần gateway | Trước Spring-WS | HTTP 413 hoặc transport error; **có thể không có SOAP Fault** |
| TLS handshake/client cert sai | Trước SOAP Envelope | TLS/connection error |
| MIME boundary hoặc Content-ID không hợp lệ | MIME parser/message factory | Parse error, SOAP fault hoặc HTTP error theo stack |
| XML Body không hợp XSD | Endpoint interceptor | SOAP Client/Sender fault nếu route được |
| File stream vượt byte cap ở endpoint | Ingestion service | Custom validation fault nếu có resolver và response còn tạo được |
| Temp disk đầy/quota global | I/O/staging | Server/Receiver fault hoặc transport failure |
| Malicious content/virus | Scanner/application policy | Rejection/async status theo contract |
| Tệp source outbound biến mất | SOAP client I/O | Client-side exception, có thể không gửi đủ request |
| DB commit nhưng response mất | Hậu xử lý | Timeout; **kết quả nghiệp vụ chưa biết** |
| Process kill khi copy file | Hệ điều hành | Đứt kết nối, orphan temp có thể còn |

Không đưa `IOException.getMessage()` hoặc file path staging/hostname vào public SOAP Fault. Với lỗi business đã phân loại, có thể trả application detail như `ATTACHMENT_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `CHECKSUM_MISMATCH`, `MALWARE_REJECTED`; tên mã là **ví dụ**, phải đưa vào WSDL/XSD/error catalog.

### 12.2. Phân biệt lỗi phía gửi và phía nhận

- **SOAP 1.1 Client / SOAP 1.2 Sender:** payload/attachment vượt policy được công bố, sai Content-ID, checksum không khớp, loại file không hỗ trợ.
- **SOAP 1.1 Server / SOAP 1.2 Receiver:** storage unavailable, tệp tạm không ghi được, scanner service down, lỗi cấu hình.
- **Transport failure:** request có thể bị chặn **trước khi message parse**, không phải lúc nào cũng có Envelope Fault.
- **Unknown after commit:** client timeout không đồng nghĩa file chưa lưu. Cần `requestId` idempotent + operation tra cứu trạng thái.

### 12.3. Không echo dữ liệu nhạy cảm

Một Fault public có thể mang:

~~~xml
<doc:UploadFault xmlns:doc="urn:example:documents:v1">
  <doc:code>ATTACHMENT_TOO_LARGE</doc:code>
  <doc:message>Tệp vượt giới hạn cho phép</doc:message>
  <doc:correlationId>corr-001</doc:correlationId>
</doc:UploadFault>
~~~

Đoạn này là **fault detail ứng dụng minh họa**, phải có schema và WSDL fault binding nếu client cần typed fault. Không nhúng toàn bộ filename/path, stack trace, file hash bí mật, dữ liệu PDF, SQL hoặc raw parser diagnostics. Không trả `ACCEPTED` khi staging/metadata durable chưa đạt mốc cam kết.

## 13. Bảo mật: MIME, XML, WS-Security và lưu trữ

### 13.1. Xác thực trước xử lý tốn tài nguyên khi có thể

TLS/mTLS bảo vệ kênh và có thể xác minh đối tác; WS-Security/WSS4J có thể xác minh signature, token, timestamp, mã hóa. Nhưng một chữ ký hợp lệ **không chứng minh file không chứa malware**. XSD hợp lệ cũng **không** chứng minh caller có quyền gửi tài liệu cho `documentId`.

Đừng để client không xác thực upload hàng GiB vào disk rồi mới kiểm quyền. Có thể pre-auth ở gateway và giới hạn HTTP body trước parser, sau đó kiểm WS-Security/authorization theo thứ tự phù hợp. Với security cần đọc attachment để kiểm chữ ký, tránh xem file là **trusted** trước khi toàn bộ verification thành công.

### 13.2. Các bề mặt tấn công

| Bề mặt | Nguy cơ | Phòng vệ |
| --- | --- | --- |
| XML parser | XXE, entity expansion, deep nesting | Disable external entities/DTD theo provider, depth/size cap |
| MIME parser | Nhiều part, header dài, nested multipart | Part count/header/total size limits |
| Content-ID | Duplicate/sai `cid:`, header confusion | Validate uniqueness, normalize RFC 2392 |
| Filename | `../` traversal, path tuyệt đối, Unicode lạ | Không dùng tên caller làm filesystem path |
| Content-Type | File giả mạo định dạng | Magic bytes, parser sandbox, whitelist |
| ZIP/archive | Zip bomb, zip slip, symlinks | Decoded size/depth/entry count/path checks |
| Temp directory | Symlink/race, plaintext PII, disk full | Private directory, random file, quotas, encryption |
| WS-Security signature | Unsigned attachment/mismatched node | Coverage đúng profile, signed parts/canonicalization |
| Client certificate | Chứng chỉ hết hạn/không tin cậy | Truststore, rotation, hostname validation |
| Antivirus/scanner | Quá tải, timeout, false negative | Quarantine, bounded concurrency, scan status |
| Download response | Data exfiltration, huge outbound stream | Authz, bounded send/timeout, logging |

### 13.3. WS-Security và attachment coverage

Với message security, cần xác minh chính xác:

- Chữ ký bảo vệ **SOAP Body**, addressing/security headers và **attachment** theo profile được công bố.
- Phần MIME mà application xử lý chính là phần đã được xác thực, không để **content-ID duplicate** hoặc node mismatch gây confusion.
- Bật timestamp/replay policy khi cần; không chỉ kiểm có `wsse:Security`.
- Không log raw MIME parts, UsernameToken, private key hoặc tài liệu nhạy cảm.
- Các partner Java/.NET có thể khác nhau trong MTOM + WS-Security attachment support, phải test wire interoperability.

Spring-WS `Wss4jSecurityInterceptor` có extension `setAttachmentCallbackHandler(...)` hỗ trợ xử lý attachment security trong các phiên bản có tính năng; cấu hình thực tế phụ thuộc WS-Security profile và WSS4J, không thể coi một setter là bật tất cả chữ ký/encryption. Phải chứng minh bằng test signature tamper và rejected attachments.

### 13.4. Bảo mật tệp staging

- Chọn directory **ngoài web root** và ngoài nơi có thể thực thi file.
- Dùng tên ngẫu nhiên/`Files.createTempFile`; không ghép `getFilename()` của client.
- Giới hạn quyền đọc/ghi ở service account, không chia sẻ volume rộng cho ứng dụng khác.
- Ghi trạng thái/owner của file nếu quy trình có thể kéo dài.
- Tách các tệp chưa scan khỏi tài liệu sẵn sàng download.
- Có retention/cleanup và encryption-at-rest khi threat model cần.
- Không cho các lớp downstream đọc từ path của file tạm không thuộc sở hữu của chúng.

## 14. Kiểm thử giới hạn, vòng đời và fault injection

### 14.1. Ma trận kiểm thử

| Kịch bản | Kỳ vọng | Tài nguyên cần kiểm |
| --- | --- | --- |
| Attachment nhỏ 1 KiB | Nhận thành công | Hash, size, file nội dung |
| Attachment đúng `maxBytes` | Chấp nhận nếu policy dùng `<=` | Không vượt trần |
| Attachment `maxBytes + 1` | Từ chối | Temp bị dọn |
| `getSize()=-1`, stream nhỏ | Vẫn nhận đúng bytes | Không bỏ qua limit |
| `getSize()=-1`, stream quá lớn | Dừng khi vượt trần | Disk không nhận bytes vượt cap |
| declaredSize nhỏ hơn thực tế | Reject mismatch | Không lưu durable thành công |
| declaredSize lớn hơn thực tế | Reject mismatch | Phát hiện truncation |
| Thiếu attachment | Validation fault | Không tạo business entity |
| Có 3 parts khi chỉ cho 2 | Reject | MIME parser/part count |
| Duplicate Content-ID | Reject theo contract | Không dùng nhầm part |
| MIME Content-Type giả | Reject/scan | Không tin file extension |
| File ZIP nhỏ nhưng giải nén rất lớn | Reject | Decoded size/depth |
| XML sâu/XXE | Reject trước business | XML parser safety |
| Tràn temp quota/disk full | Fail có kiểm soát | Không giữ partial file |
| `InputStream.read()` ném IOException | Cleanup | Stream đóng, temp dọn |
| Client disconnect giữa upload | Fail/truncation | Không trả AVAILABLE |
| Scanner timeout | PENDING_SCAN hoặc reject theo policy | Bounded concurrency |
| Crash process khi đang copy | Orphan cleanup hoạt động | Disk sau restart |
| 20 uploads đồng thời | Không OOM, không lẫn files | Heap, FD, disk, queues |
| SOAP request vượt gateway limit | HTTP rejection | Không cần fault SOAP |
| MTOM/XOP từ Java/.NET | Unmarshal đúng content | Wire MIME, XML Infoset |
| WS-Security attachment bị sửa | Signature verification fail | Không tạo durable object |
| SOAP response mất sau commit | Retry idempotent | Không tạo object trùng |
| Outbound source file bị xóa sớm | Test phát hiện I/O failure | Lifecycle file source |

### 14.2. Unit test với stream không biết size

Có thể viết một `Attachment` mock có `getSize() = -1` và `getInputStream()` trả stream sinh dữ liệu dài hơn trần. Gọi `AttachmentStager.stage` và kiểm:

~~~java
// Pseudocode JUnit/Mockito:
when(part.getSize()).thenReturn(-1L);
when(part.getInputStream())
    .thenReturn(new ByteArrayInputStream(
        new byte[1024 * 1024 + 1]));

// maxBytes của stager là 1 MiB.
assertThrows(
    BoundedAttachmentCopy.AttachmentTooLargeException.class,
    () -> stager.stage(part));

// Assert thư mục staging không còn file ứng dụng mới.
assertEquals(0L, countApplicationStagingFiles());
~~~

Khung test cần `part`/`stager`/`countApplicationStagingFiles` là fixtures thật; ví dụ cấp mảng nhỏ để test đơn giản, không khuyến khích dựng mảng hàng GiB nhằm kiểm limit. Bổ sung spy/`FilterInputStream` để xác minh `close()` được gọi ngay cả khi fail.

### 14.3. Integration test dùng provider thật

`MockWebServiceClient` phù hợp để kiểm endpoint/Body/Fault qua Spring-WS dispatcher khi test request creator biết thêm MIME attachment. `MockWebServiceServer` phù hợp ở phía SOAP client. Tuy nhiên, chỉ mock method `Attachment.getInputStream()` **không đo** heap/disk của MIME parser.

Một bộ test production cần:

1. Gửi multipart SOAP **qua HTTP thật** với SAAJ/Axiom provider đang dùng.
2. Đo peak heap/GC, temp directory, file descriptors và request latency.
3. Vary `Content-Length`, chunked transfer, MIME boundaries, header size và part counts.
4. Gửi chính xác limit, limit+1, unknown size, nhiều parts và request bị cắt ngang.
5. Kill process giữa upload, restart và kiểm orphan cleanup/reconciliation.
6. Giả lập disk full, read IOException, scanner unavailable, timeout.
7. Dùng SOAP 1.1 và SOAP 1.2 theo WSDL; thử đối tác Java/.NET với MTOM.
8. Xác minh **không có file AVAILABLE** nếu nội dung chưa được quét hoặc commit.
9. Kiểm WS-Security tampering đối với MIME attachment, không chỉ SOAP Body.
10. Gửi concurrent uploads và quan sát queue/backpressure/resource usage thực tế.

### 14.4. Xác minh message factory trước khi kết luận

Cùng một test chạy với `SaajSoapMessageFactory` và `AxiomSoapMessageFactory` có thể tạo bộ nhớ/disk profile khác nhau. Khi bật `payloadCaching=false`, test phải kiểm endpoint mapping/validation có còn hoạt động, không chỉ đo thời gian nhanh hơn. Khi bật attachment caching, test directory phải có quyền ghi, dung lượng đủ và cleanup theo provider.

Không tạo bài test chỉ assert `setAttachmentCacheThreshold(65536)` được gọi rồi tuyên bố có giới hạn attachment 64 KiB; **đó là caching threshold, không phải hard limit**.
## 15. Giám sát tài nguyên và vận hành

Khi triển khai thực tế, **sự ổn định của SOAP attachment processing không thể được đánh giá chỉ bằng tỷ lệ HTTP 200**. Một service có thể trả response thành công nhưng disk temp tăng dần, GC pause lớn và số file descriptors không được giải phóng.

### 15.1. Những metric quan trọng

| Metric | Mục đích | Lưu ý |
| --- | --- | --- |
| `upload_attempts_total` theo operation/result | Phân biệt success, validation reject, transport fail | Không gắn raw filename/user ID làm label |
| `attachment_decoded_bytes` histogram | Hiểu phân phối kích thước file thật | Đếm bytes thực, không chỉ declared size |
| `http_wire_bytes` histogram | Đo MIME/transfer overhead | Có thể khác decoded bytes |
| `inflight_uploads` / queue depth | Bảo vệ concurrency | Giới hạn tổng số requests đang copy |
| `heap_used`, GC pause, allocation rate | Phát hiện buffer/DOM/JAXB pressure | Quan sát peak load |
| `temp_bytes_used` / `temp_file_count` | Phát hiện orphan/disks full | Phân biệt application staging và provider cache |
| `temp_inode_usage` | Tránh lỗi khi nhiều file nhỏ | Disk còn bytes chưa đủ |
| `open_file_descriptors` | Phát hiện stream leak | Nguy cơ `Too many open files` |
| `stream_copy_duration` | Hiểu chi phí upload/storage | Tránh log từng 64 KiB gây overhead |
| `scan_queue_depth` / scan failures | Ngăn backlog không giới hạn | PENDING_SCAN vs AVAILABLE |
| `attachment_rejection_reason` | Theo dõi oversized/type/hash | Chỉ dùng mã lý do được whitelist |
| `post_commit_timeout` / idempotency retries | Phân biệt client timeout với duplicate attempts | Không suy commit từ HTTP response |

**Không log file bytes**, raw XML chứa token hoặc tên file nhạy cảm ở mức debug toàn cục. Dùng correlation ID vô hại và access-controlled tracing/structured logs, che dữ liệu nhận dạng và giữ retention phù hợp.

### 15.2. Capacity planning ngắn

Một phương pháp tính sơ bộ:

~~~text
C = số uploads đồng thời tối đa
L = max bytes staging trên một upload
B = buffer Java cho một stream
P = số MIME/provider copies hoặc cache độc lập (đo thực tế)

Application buffer budget ~ C * B
Worst-case staging footprint ~ C * L + retained files + overhead
Heap thực tế              = app buffers + SOAP/JAXB/XML/transport/GC ...
Temp disk thực tế         = app staging + provider cache + orphan files ...
~~~

Không thay số `P` bằng một hằng số do suy đoán. Đo peak concurrent requests theo message factory, kiểu attachment, TLS/WS-Security và response pattern. Nếu quota toàn hệ thống thấp hơn tổng limit per-request tiềm năng, cần semaphore/bulkhead/backpressure để giới hạn in-flight bytes, không chỉ giới hạn request count.

### 15.3. Recovery khi thiếu tài nguyên

- **Temp disk gần đầy:** dừng nhận thêm upload trước khi đến 100%, trả lỗi/tạm từ chối có kiểm soát.
- **Disk đầy trong lúc copy:** đóng streams, xóa file partial nếu có thể, ghi metric sự cố và không trả success.
- **Process restart:** rà soát staging có owner/state/TTL; không xóa file của một workflow còn hiệu lực.
- **Scanner chậm:** giới hạn queue, công bố `PENDING_SCAN` chỉ khi job được lưu bền vững.
- **Outbound backpressure:** hạn chế đồng thời, timeout/chunking theo sender; không tích tụ tệp nguồn vô hạn.
- **Peak heap tăng:** xem lại SAAJ vs Axiom, payload caching, base64 arrays, logging, MTOM provider và concurrency.
- **SOAP response thất lạc:** tra cứu trạng thái theo business requestId; retry idempotently.

## 16. Những lỗi thiết kế thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách làm tốt hơn |
| --- | --- | --- |
| Tin `Content-Length` là đủ | Có thể thiếu/chunked, không bằng decoded size | Count bytes thật trong stream |
| Tin `Attachment.getSize()==-1` là tệp rỗng | Không biết size | Vẫn bounded copy |
| Chỉ đặt `max-file-size` của form multipart | Có thể không áp SOAP multipart/related | Enforce đúng HTTP/MIME path |
| Dùng `readAllBytes()` cho file người dùng | Memory spike/OOM | Bounded buffer + staging |
| Dùng Axiom `attachmentCacheThreshold` như upload limit | Threshold chỉ chuyển cache RAM→disk | Hard limit độc lập |
| Tắt `payloadCaching` mà vẫn dùng PayloadRoot mapping | Payload bị consume một lần | Thiết kế mapping/validator compatible |
| Không đóng `Attachment.getInputStream()` | File descriptor/stream leak | try-with-resources |
| Dùng `InputStreamResource` cho attachment gửi lại nhiều lần | Stream single-use có thể cạn | FileSystemResource/replayable source |
| Xóa file source ngay sau khi enqueue send async | Serializer không còn file để đọc | Giữ file qua send completion |
| Để file staging trong web root | Tệp chưa scan có thể bị tải/xử lý | Private/quarantine directory |
| Dùng tên file caller làm path | Path traversal/collision | Random temp name + safe metadata |
| Quét file bằng một service không có timeout | Upload threads bị giữ lâu | Bounded scanner/async durable job |
| Trả `AVAILABLE` ngay khi copy xong staging | Chưa scan/chưa durable | State machine rõ |
| Coi temp move là DB transaction | Hai hệ thống không atomic | Durable workflow/reconciliation |
| Tin SHA-256 tự chứng minh tệp an toàn | Hash không phải malware scan | Type/content scan + provenance |
| Không cleanup sau lỗi/timeout | Disk đầy, inode leak | finally + orphan reaper |
| Dọn toàn bộ temp dir chung ở cuối request | Xóa file request khác | Cleanup theo ownership |
| Giả định `finally` chạy sau power loss | Orphan còn trên disk | Startup reconciliation/TTL |
| Tin MIME Content-Type/extension | Dễ giả mạo | Magic bytes + scanner |
| Nhận attachment mà không verify WS-Security coverage | Nội dung có thể bị thay đổi | Xác minh đúng parts/Body |
| Chỉ test endpoint bằng attachment mock | Không đo parser/HTTP memory | Wire integration test + load |
| Coi SOAP Fault luôn xảy ra khi quá size | Gateway có thể trả HTTP 413 trước SOAP | Hỗ trợ transport errors |
| Retry upload bằng requestId mới sau timeout | Có thể tạo duplicate object | Idempotent retry + status query |

## 17. Quy trình thiết kế và checklist

~~~mermaid
flowchart TD
    A["Xác định payload SwA hay MTOM/XOP"] --> B["XSD/WSDL và kích thước tối đa"]
    B --> C["Limits: gateway / HTTP / MIME / XML"]
    C --> D["MessageFactory + cache policy"]
    D --> E["Endpoint authz + Attachment count/type"]
    E --> F["Bounded stream → private staging"]
    F --> G["Hash, declared size, content/AV check"]
    G --> H{"Đã hợp lệ và durable?"}
    H -- "Không" --> I["Cleanup + Fault hoặc durable PENDING_SCAN"]
    H -- "Có" --> J["Persist state / idempotency"]
    J --> K["SOAP response, metrics và reconciliation"]
~~~

### Checklist trước production

1. **Hợp đồng:** sử dụng SwA hay MTOM? QName Body, Content-ID, MIME type và WSDL binding có thống nhất với client Java/.NET không?
2. **Gateway:** HTTP entity size, header size, timeout, rate limit và chunked behavior đã cấu hình chưa?
3. **Parser:** XML size/depth/DTD, MIME part count/headers và không mở external entities?
4. **Attachment:** giới hạn single-part và tổng decoded bytes được enforce ngay khi đọc stream, kể cả `getSize()=-1`?
5. **Memory:** message factory SAAJ/Axiom, JAXB `byte[]`/`DataHandler` và logging có được đo dưới tải không?
6. **Axiom:** `attachmentCaching`, `attachmentCacheDir`, threshold và `payloadCaching` có phù hợp endpoint mapping/validation?
7. **Ownership:** ai đóng InputStream, ai xóa staging, ai giữ outbound source cho đến khi gửi xong?
8. **Temp security:** thư mục staging riêng, quota, permissions, TTL, disk/inode monitoring, không dùng filename caller?
9. **Validation:** declaredSize, checksum, signature/magic bytes, malware scan và authorization có rõ mốc trước khi AVAILABLE?
10. **Durability:** storage object và DB metadata có workflow/recovery khi một bên thành công, bên kia thất bại?
11. **Response:** SOAP Fault vs HTTP transport errors, retry theo business requestId và query status có được mô tả?
12. **Security:** TLS/mTLS, WS-Security signature coverage cho attachment, encryption, XXE, ZIP bomb và redaction?
13. **Client:** FileSystemResource/replayable stream, file source lifetime, timeout và SOAP version đúng?
14. **Testing:** file đúng limit/vượt limit, unknown size, disk full, scanner outage, kill process, concurrent load, Java/.NET interoperability?

### Bài tập tự kiểm tra

1. Vì sao giới hạn `Content-Length=25 MiB` không thay thế `maxSingleAttachmentBytes=20 MiB`?
2. Phân biệt `setAttachmentCacheThreshold(65536)` và kiểm file size tối đa 64 KiB.
3. Với `AxiomSoapMessageFactory.setPayloadCaching(false)`, điều gì có thể xảy ra với `PayloadValidatingInterceptor`?
4. Một attachment có `getSize()=-1` và stream chứa 30 MiB; thiết kế phải xử lý thế nào nếu limit là 20 MiB?
5. `Attachment.getInputStream()` có cần đóng không? Nếu copy ném lỗi khi đang đọc thì ai chịu trách nhiệm?
6. Vì sao `FileSystemResource` phù hợp hơn `InputStreamResource` khi MIME serializer có thể mở stream nhiều lần?
7. Một file PDF được nhận vào `/tmp` và endpoint trả `AVAILABLE` trước khi scanner chạy. Rủi ro gì?
8. Tại sao `Files.createTempFile` và `finally` vẫn chưa đủ để thu hồi tất cả files sau crash?
9. SOAP Fault bị mất sau khi file và metadata đã commit. Client nên dùng cơ chế nào để tránh upload trùng?
10. Vì sao mã `Content-Type: application/pdf` không chứng minh byte stream là PDF an toàn?
11. Hãy thiết kế test phát hiện leak stream và thư mục temp sau 100 requests bị ngắt giữa chừng.
12. Với MTOM DataHandler, tại sao không được kết luận serializer luôn streaming mà không đo memory thực tế?
13. Nêu các lớp bảo mật riêng của XSD validation, WS-Security và malware scanner.
14. Khi một upload batch có hai files và file thứ hai sai checksum, service cần quyết định gì để bảo đảm all-or-nothing hoặc partial acceptance?

## Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — SAAJ/AXIOM message factories, payload streaming, attachments và SOAP client/server.
- [Spring-WS API — MimeMessage](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/mime/MimeMessage.html) — `addAttachment`, `getAttachments`, `InputStreamSource` và XOP.
- [Spring-WS API — Attachment](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/mime/Attachment.html) — `getSize()`, `getInputStream()`, `DataHandler` và trách nhiệm đóng stream.
- [Spring-WS API — AxiomSoapMessageFactory](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/axiom/AxiomSoapMessageFactory.html) — `payloadCaching`, `attachmentCaching`, threshold, cache directory.
- [Spring-WS API — WebServiceTemplate](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/client/core/WebServiceTemplate.html) — gửi/nhận bằng callback và extractor.
- [Spring Framework OXM — Jaxb2Marshaller](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html) — `setMtomEnabled(boolean)` và JAXB binding.
- [Spring Framework — InputStreamResource](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/io/InputStreamResource.html) — nguồn stream single-use và lựa chọn resource khác.
- [W3C — SOAP Message Transmission Optimization Mechanism](https://www.w3.org/TR/soap12-mtom/) — MTOM/XOP relationship.
- [RFC 2392 — Content-ID and Message-ID URLs](https://www.rfc-editor.org/rfc/rfc2392) — `cid:` URL và MIME `Content-ID`.

**Ghi nhớ:** **SOAP attachment là bài toán tài nguyên và vòng đời, không chỉ là một element XML hay MIME part.** Giới hạn HTTP/MIME/XML ở cửa vào, **đếm bytes thật** dù `getSize()=-1`, dùng buffer nhỏ và staging riêng, quản lý owner của `InputStream`/file nguồn, phân biệt Axiom cache threshold với hard upload limit, dọn temp có cả cơ chế sau crash, và chỉ trả trạng thái thành công theo mốc durable/scan được hợp đồng xác nhận. Kiểm thử cả SOAP Fault, transport timeout, MTOM/SwA, WS-Security và tải đồng thời trước khi tích hợp đối tác.
