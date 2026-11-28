# Loại nội dung, tên tệp và kiểm tra dữ liệu nhận được

## 1. Vấn đề: tên `invoice.pdf` chưa chứng minh đây là PDF

Một dịch vụ SOAP của doanh nghiệp tiếp nhận chứng từ từ các đối tác. Client gửi request `UploadDocumentRequest` cùng một tệp đính kèm và khai báo:

~~~text
Content-ID: <invoice-1001@example.test>
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

Nhìn vào ba thông tin này, server có thể cho rằng tệp là PDF tên `invoice.pdf`. Nhưng cả **loại nội dung (Content-Type)** và **tên tệp do bên gửi cung cấp** đều là metadata có thể giả mạo. Một client khác có thể gửi các header giống hệt nhưng phần dữ liệu thực tế là file thực thi, ZIP chứa dữ liệu độc hại, PDF hỏng hoặc tệp khổng lồ.

Ở phía Spring Web Services (**Spring-WS**), yêu cầu SOAP hợp lệ về XSD cũng **không tự xác nhận** các bytes MIME attachment là tệp đúng định dạng, an toàn hoặc có kích thước cho phép.

Trong chương **Tệp đính kèm** của module `SPRING_WEB_SERVICES`, bài học này tập trung vào cách đọc và kiểm tra **Content-Type, tên tệp và dữ liệu thực nhận** trong SOAP attachments, đồng thời kết nối kiến thức với XSD/WSDL contract-first, JAXB, SOAP endpoint/client, SOAP Fault, XML security, WS-Security và kiểm thử tương thích.

Kết quả cần đạt:

1. Nhận diện sự khác nhau giữa SOAP Body, MIME parts, MTOM/XOP và HTTP multipart form.
2. Hiểu `Content-ID` dùng làm gì, `Content-Type` cho biết điều gì và vì sao **filename** thường không phải thuộc tính bắt buộc của attachment.
3. Biết cách lấy attachment trong Spring-WS bằng `MimeMessage` và `Attachment`.
4. Xây dựng pipeline kiểm tra metadata, giới hạn bytes, nhận diện định dạng thực tế, xác minh XSD và nghiệp vụ.
5. Ngăn path traversal, SSRF, tệp độc hại, ZIP bomb, rò rỉ dữ liệu và lạm dụng dung lượng.
6. Phân loại lỗi thành SOAP Fault hoặc transport failure phù hợp hợp đồng và kiểm thử được bằng Java lẫn client bên ngoài.

**Nguyên tắc xuyên suốt:** metadata của tệp chỉ là **lời khai của client**; an toàn đòi hỏi kiểm tra **dữ liệu nhận được**, chính sách tiếp nhận và quyền thao tác.

## 2. Một SOAP request có attachment gồm những phần nào?

Với SOAP có tệp đính kèm, HTTP request có thể được truyền dưới dạng **MIME `multipart/related`**. Một MIME part chứa SOAP Envelope, các part còn lại chứa dữ liệu nhị phân hoặc nội dung khác.

~~~mermaid
flowchart TD
    H["HTTP POST multipart/related"] --> R["Root MIME part: SOAP Envelope"]
    H --> A["Attachment MIME part A"]
    H --> B["Attachment MIME part B"]
    R --> X["SOAP Header + SOAP Body"]
    X --> C["cid: tham chiếu tới attachment"]
    C -.-> A
    A --> M["Content-ID, Content-Type, headers"]
    M --> D["Bytes thực nhận"]
~~~

Ví dụ **minh họa cấu trúc**, không phải bản tin được tạo bởi một thư viện cụ thể:

~~~http
POST /ws/documents HTTP/1.1
Host: api.example.test
MIME-Version: 1.0
Content-Type: multipart/related; boundary="b-123"; type="text/xml"; start="<root@example.test>"
~~~

~~~text
--b-123
Content-Type: text/xml; charset=UTF-8
Content-ID: <root@example.test>

<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>...</soap:Body>
</soap:Envelope>
--b-123
Content-Type: application/pdf
Content-ID: <invoice-1001@example.test>
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: binary

[các bytes của file PDF]
--b-123--
~~~

Chú ý: ví dụ thể hiện SOAP 1.1 với MIME packaging minh họa. Khi dùng **MTOM/XOP** với SOAP 1.2 hoặc SOAP 1.1, các giá trị của outer/inner `Content-Type`, `type`, `start-info` và `application/xop+xml` khác theo binding. **Không dùng ví dụ này làm khuôn HTTP header cứng cho mọi MTOM client.**

### 2.1. Phân biệt ba Content-Type

| Nơi xuất hiện | Ví dụ | Nó mô tả gì? |
| --- | --- | --- |
| Header HTTP toàn request | `multipart/related; boundary=...` | Cách đóng gói nhiều MIME parts |
| MIME root part | `text/xml` hoặc `application/xop+xml` với tham số thích hợp | Phần SOAP message chính |
| MIME attachment part | `application/pdf`, `image/png`, `application/octet-stream` | Loại nội dung **được khai báo** cho tệp |

Nếu lập trình viên chỉ đọc `Content-Type` của HTTP request và thấy `multipart/related`, điều đó **không** cho biết tệp đính kèm là PDF, ảnh hay loại khác. Muốn biết phần đính kèm được khai báo là gì, phải đọc metadata **của chính MIME part ấy**.

### 2.2. SOAP attachments không phải `multipart/form-data`

`multipart/form-data` thường dùng cho form upload HTTP/REST và Spring MVC `MultipartFile`. SOAP attachments/MTOM thường dùng `multipart/related` cùng SOAP Envelope.

Do đó:

- Không mặc định `@RequestParam MultipartFile` trong Spring MVC nhận được một SOAP attachment.
- Không tự bóc raw MIME body bằng chuỗi `split("--boundary")`: boundary, binary bytes và encoding có quy tắc MIME riêng.
- Không cho rằng việc dùng `@RequestPayload` chỉ nhận JAXB DTO đã đủ để xử lý an toàn mọi attachment.
- Hãy để **SOAP message factory/MIME API** xử lý đóng gói và truy cập part, đồng thời giới hạn tài nguyên ngay từ tầng nhận request.

## 3. MTOM/XOP, SwA và base64 inline khác nhau như thế nào?

Cùng một dữ liệu nhị phân có thể được đưa vào SOAP theo nhiều cách:

| Cách truyền | Dữ liệu nằm ở đâu? | Tác động tới xử lý |
| --- | --- | --- |
| Inline `xs:base64Binary` | Text base64 ngay trong SOAP Body | XML lớn hơn; JAXB có thể ánh xạ thành `byte[]` |
| SOAP with Attachments (SwA) | MIME part riêng, SOAP XML có cơ chế tham chiếu nếu contract quy định | Cần đọc/đối chiếu attachment và tham chiếu |
| MTOM/XOP | MIME part riêng với biểu diễn `xop:Include href="cid:..."` trong root XOP message | Dữ liệu nhị phân được tối ưu hóa, logic XML vẫn gắn với phần tử schema |

MTOM là **cơ chế tối ưu truyền tải** XML-binary; nó không tự xác nhận file hợp lệ hay thay đổi quy tắc phân quyền. Một XSD `xs:base64Binary` có thể tương thích về mặt dữ liệu XML với cả biểu diễn inline base64 và MTOM tùy binding/framework.

### 3.1. Ví dụ XOP tham chiếu bytes

~~~xml
<doc:DocumentContent
    xmlns:doc="urn:example:documents:v1">
    <doc:data>
        <xop:Include
            xmlns:xop="http://www.w3.org/2004/08/xop/include"
            href="cid:invoice-1001@example.test"/>
    </doc:data>
</doc:DocumentContent>
~~~

Đây là **fragment minh họa**, không phải XML ứng dụng dùng để bypass một XML schema: trong một message MTOM/XOP chuẩn, dạng tối ưu khi truyền được processor khôi phục về nội dung kiểu base64Binary trong XML infoset. Client/server phải có **MTOM-aware processing**.

`href="cid:invoice-1001@example.test"` tham chiếu MIME part có `Content-ID` tương ứng; nó **không** phải URL HTTP để server đi tải từ mạng.

### 3.2. Điều gì không được suy từ MTOM?

- Có MTOM không có nghĩa attachment là virus-free.
- Một `DataHandler` hay `byte[]` được JAXB tạo không chứng minh file đúng `Content-Type`.
- Dữ liệu truyền được thành công qua SOAP không có nghĩa xử lý nghiệp vụ thành công.
- XSD validation của SOAP payload không mặc nhiên quét bytes attachment hay kiểm tra kích thước từng part.
- WS-Security ký SOAP Body không có nghĩa mọi attachment part đã được ký; phải xác định chính sách chữ ký cho attachments.

## 4. Ba thông tin khác nhau: `Content-ID`, `Content-Type` và filename

### 4.1. `Content-ID`: định danh một MIME part

~~~text
Content-ID: <invoice-1001@example.test>
~~~

Đây là MIME content identifier dùng để tham chiếu tới part, ví dụ từ `cid:invoice-1001@example.test` trong XOP.

Không xem `Content-ID` là:

- Tên file cần lưu trên đĩa.
- Đường dẫn tuyệt đối hoặc URL public.
- Hash kiểm tra tính toàn vẹn.
- Danh tính của người gửi.
- Idempotency key đã được xác thực.

Framework có thể biểu diễn content ID có hoặc không có dấu ngoặc nhọn `<...>` tùy API. Khi đối chiếu, dùng **quy tắc chuẩn hóa phù hợp MIME/cid của stack đang dùng**, không tự tách/ghép chuỗi một cách tùy tiện dẫn đến chọn nhầm part.

### 4.2. `Content-Type`: lời khai về media type

~~~text
Content-Type: application/pdf
~~~

`Content-Type` giúp hệ thống chọn policy xử lý, nhưng **không có cơ chế bảo đảm bytes thật đúng loại**. Giá trị có thể có tham số:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: application/pdf; name="statement.pdf"
Content-Type: image/png
~~~

Vì thế:

1. Xác định media type chính một cách có cấu trúc, chuẩn hóa ASCII/case theo parser thích hợp.
2. Chỉ chấp nhận **allowlist** những loại mà nghiệp vụ thực sự hỗ trợ.
3. Phân biệt media type được khai báo và định dạng **được nhận diện từ bytes**.
4. Dùng decoder/parser định dạng an toàn hoặc dịch vụ quét theo chính sách.
5. Không dựa vào giá trị `application/octet-stream` để tự động cho phép mọi nội dung không rõ loại.

### 4.3. Tên tệp: metadata tùy chọn, không đồng nhất với Content-ID

Một MIME part **có thể** mang:

~~~text
Content-Disposition: attachment; filename="invoice-1001.pdf"
~~~

hoặc một tham số `name` trong `Content-Type` theo hệ thống tích hợp. Nhưng **không có bảo đảm mọi SwA/MTOM attachment phải có filename**, hoặc tên file luôn được API attachment cấp cao cung cấp.

Trong Spring-WS, abstraction `org.springframework.ws.mime.Attachment` chủ yếu cho biết **content ID, media type, size và dữ liệu stream**; **đừng giả định có `attachment.getOriginalFilename()` hay `attachment.getFileName()` giống Spring MVC `MultipartFile`**.

Hai thiết kế có thể dùng:

- **Tên tệp trong SOAP payload hợp đồng**: một trường như `originalFileName` trong XSD để client công bố rõ, rồi validate theo chính sách.
- **Tên tệp trong MIME headers**: nếu đối tác thực sự cung cấp `Content-Disposition` và SOAP implementation cho phép truy xuất, đọc qua API MIME/SAAJ cụ thể của phiên bản sau khi parse đúng header.

Nếu cả SOAP payload và MIME header có filename, cần định nghĩa **nguồn nào là chuẩn** và hành vi khi chúng mâu thuẫn. **Không tự coi một trong hai là đáng tin chỉ vì nó được đặt trong SOAP.**

### 4.4. Một bảng kiểm tra metadata

| Metadata | Có thể giả mạo? | Có thể thiếu? | Dùng vào việc gì? |
| --- | --- | --- | --- |
| `Content-ID` | Có | Tùy packaging/contract | Liên kết payload với MIME part |
| `Content-Type` | Có | Có thể thiếu hoặc quá chung | Chọn policy ban đầu |
| `Content-Disposition: filename` | Có | **Có** | Tên hiển thị sau khi lọc; không dùng làm đường dẫn |
| SOAP `originalFileName` | Có | Tùy XSD | Metadata nghiệp vụ đã khai báo |
| SOAP `expectedSize` | Có | Tùy XSD | Đối chiếu; **không thay giới hạn thực đọc** |
| SOAP `sha256` | Có | Tùy XSD | Kiểm tra integrity sau khi đọc, nếu giá trị được xác thực đúng nguồn |
| Dung lượng bytes thực đọc | Không phụ thuộc khai báo | Không | Áp quota/limit |
| Magic bytes / decoder thực tế | Do bytes quyết định | Không | Kiểm tra định dạng, không thay kiểm tra nội dung độc hại |

## 5. Hợp đồng XSD: đặt tên, loại dự kiến và tham chiếu part

Giả sử dịch vụ quản lý chứng từ nhận một tệp PDF. Để tránh phụ thuộc vào MIME filename tùy chọn, contract XML có thể mang metadata rõ ràng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:documents:v1"
    targetNamespace="urn:example:documents:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="DocumentNameType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
            <xs:maxLength value="120"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="UploadDocumentRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="documentId" type="xs:string"/>
                <xs:element name="originalFileName"
                            type="tns:DocumentNameType"/>
                <xs:element name="declaredContentType"
                            type="xs:string"/>
                <xs:element name="attachmentRef" type="xs:anyURI"/>
                <xs:element name="declaredSize"
                            type="xs:nonNegativeInteger"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="UploadDocumentResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="receiptId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Một SOAP payload hợp schema:

~~~xml
<d:UploadDocumentRequest
    xmlns:d="urn:example:documents:v1">
    <d:documentId>DOC-1001</d:documentId>
    <d:originalFileName>invoice-1001.pdf</d:originalFileName>
    <d:declaredContentType>application/pdf</d:declaredContentType>
    <d:attachmentRef>cid:invoice-1001@example.test</d:attachmentRef>
    <d:declaredSize>32456</d:declaredSize>
</d:UploadDocumentRequest>
~~~

**Đây là contract SwA có tham chiếu MIME do ứng dụng quy định**, không phải XSD MTOM chuẩn cho một field `xs:base64Binary`. Với MTOM/XOP, chọn thiết kế schema/binding phù hợp và để marshaller/MTOM stack làm việc với binary field.

Các ràng buộc cần triển khai ngoài XSD:

- `attachmentRef` phải là `cid:` hợp lệ theo contract, không phải URL tùy ý.
- MIME part được tham chiếu phải **tồn tại chính xác và không gây mơ hồ**.
- Media type trên MIME part và trong SOAP metadata phải tương thích theo chính sách.
- Bytes thực đọc phải không vượt giới hạn, có định dạng cho phép và đáp ứng xử lý nghiệp vụ.
- `originalFileName` không chứa đường dẫn, ký tự điều khiển hoặc tên gây nguy hiểm.
- `declaredSize` chỉ là dữ liệu khai báo để đối chiếu, không thay thế counter khi stream.

### 5.1. XSD validation kiểm tra được gì?

`PayloadValidatingInterceptor` có thể kiểm tra:

- QName `UploadDocumentRequest` theo namespace.
- Thứ tự phần tử trong `xs:sequence`.
- Kiểu `xs:anyURI`, `xs:nonNegativeInteger`.
- Giới hạn độ dài của `originalFileName`.

Nhưng XSD không tự mở MIME part theo `cid:`, không xác minh định dạng PDF, không loại tệp malware, không áp quota của người dùng và không biết tên file có đường dẫn nguy hiểm theo hệ điều hành. **Phải có bước kiểm tra attachment riêng**.

### 5.2. Sơ đồ validation theo contract

~~~mermaid
flowchart TD
    A["SOAP request + MIME attachments"] --> B["Kiểm tra transport, size và XML parser"]
    B --> C["Validate SOAP payload theo XSD"]
    C --> D["Lấy cid, filename, type từ hợp đồng"]
    D --> E["Tìm MIME part được tham chiếu"]
    E --> F["Kiểm tra metadata, số lượng và quota"]
    F --> G["Đọc stream với giới hạn bytes"]
    G --> H["Kiểm tra định dạng/scan/quy tắc nghiệp vụ"]
    H --> I["Lưu bằng storage key do server sinh"]
    I --> J["Tạo receipt SOAP response"]
    B --> K["Từ chối khi lỗi"]
    C --> K
    E --> K
    F --> K
    G --> K
    H --> K
~~~

Thứ tự chi tiết phụ thuộc kiến trúc: một số giới hạn cần được thực thi **ngay tại servlet/message factory trước khi parse**, trong khi correlation/authorization có thể được làm trước khi quyết định cho phép lưu.

## 6. API Spring-WS để duyệt tệp đính kèm

Các abstraction thường gặp:

| API | Vai trò |
| --- | --- |
| `WebServiceMessage` | Request/response message nền tảng |
| `org.springframework.ws.mime.MimeMessage` | Khả năng thêm/đọc MIME attachments |
| `org.springframework.ws.mime.Attachment` | Một MIME attachment, gồm Content-ID, Content-Type, dữ liệu |
| `org.springframework.ws.soap.SoapMessage` | SOAP Envelope/Body/Header và Fault |
| `MessageContext` | Request/response và dữ liệu xử lý một lần gọi server |
| `WebServiceTemplate` | Gửi/nhận SOAP client, có thể dùng callback thêm attachments |
| `DataHandler` | Tham chiếu nguồn nội dung khi dùng Activation/JAXB/MTOM |

**Một object message có thể vừa biểu diễn SOAP vừa hỗ trợ MIME**, tùy message factory/implementation. Trước khi cast, kiểm tra `instanceof MimeMessage` và cấu hình message factory thích hợp. Không dựa vào assumption rằng mọi `WebServiceMessage` đều có attachments.

### 6.1. Đọc một attachment trong interceptor

Ví dụ minh họa phía server, dùng `EndpointInterceptor` để truy cập request khi đã được endpoint mapping chọn:

~~~java
import java.io.InputStream;
import java.util.Iterator;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.mime.Attachment;
import org.springframework.ws.mime.MimeMessage;
import org.springframework.ws.server.EndpointInterceptor;

public final class AttachmentAuditInterceptor
        implements EndpointInterceptor {

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint)
            throws Exception {

        if (!(context.getRequest() instanceof MimeMessage mime)) {
            throw new IllegalArgumentException(
                    "Message does not expose MIME attachments");
        }

        Iterator<Attachment> items = mime.getAttachments();
        int count = 0;
        while (items.hasNext()) {
            Attachment item = items.next();
            count++;

            String contentId = item.getContentId();
            String declaredType = item.getContentType();

            // Chỉ là bước audit metadata. Chưa chấp nhận dữ liệu!
            // Việc đọc stream/giới hạn bytes sẽ thực hiện trong
            // dịch vụ tiếp nhận chuyên trách.
        }

        if (count > 3) {
            throw new IllegalArgumentException(
                    "Too many attachments");
        }
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        // Dọn tài nguyên theo chính sách nếu interceptor đã sở hữu.
    }
}
~~~

Ví dụ cố ý **không** xử lý tên tệp hoặc gọi `getInputStream()` ngay trong audit, vì mục tiêu là phân biệt API metadata với bước kiểm tra bytes. Để thực sự chặn file độc hại, cần một **acceptance policy** và quy trình đọc/lưu được kiểm soát (mục 9).

**Chú ý:** ném `IllegalArgumentException` trong interceptor **không tự bảo đảm** server tạo SOAP Fault chi tiết giống lỗi nghiệp vụ từ endpoint. Trong triển khai thực, dùng cơ chế Fault/error mapping của đường interceptor đúng phiên bản và contract đã công bố, tránh phản hồi stack trace.

### 6.2. Truy xuất theo Content-ID

Khi payload đã có `attachmentRef=cid:invoice-1001@example.test`, có thể dùng:

~~~java
Attachment document =
        mimeMessage.getAttachment("invoice-1001@example.test");
~~~

Đây là **ví dụ hình thức truy vấn**. Quy tắc chính xác của content ID, bao gồm dấu `<...>`, escaping trong URI `cid:` và case/normalization, phải được xác định theo API/parser/stack đang triển khai. Trước khi dùng:

1. Parse và kiểm tra scheme `cid:`.
2. Đối chiếu với Content-ID của MIME part theo quy tắc hợp đồng.
3. Kiểm tra part thực sự tồn tại.
4. Kiểm tra không có nhiều part cùng một ID gây mơ hồ.
5. Từ chối tham chiếu đến part không được phép hoặc bị thiếu.

Không tự chấp nhận `http:`/`file:` trong `attachmentRef` rồi tải từ mạng/filesystem. `cid:` được dùng để **tham chiếu nội bộ MIME message**, không phải yêu cầu remote fetch.

### 6.3. Content-ID không đại diện tên tệp

~~~text
Content-ID: <invoice-1001@example.test>
Content-Disposition: attachment; filename="../../invoice.pdf"
~~~

Hai giá trị thuộc **hai mục đích khác nhau**. Nếu lấy `Content-ID` làm storage key trực tiếp thì vẫn phải kiểm soát định dạng và phạm vi lưu; nếu lấy filename làm đường dẫn thì có thể gặp path traversal. An toàn nhất là server sinh **storage key** riêng và chỉ lưu hai metadata sau khi validate, phục vụ hiển thị/đối soát.

## 7. Kiểm tra tên tệp nhận được

Tên tệp là dữ liệu do bên ngoài kiểm soát, dù nằm trong `Content-Disposition`, tham số `name` hay SOAP payload `originalFileName`.

### 7.1. Các dạng tên có rủi ro

| Dữ liệu client gửi | Nguy cơ | Phản ứng phù hợp |
| --- | --- | --- |
| `../../config.yml` | Path traversal | Từ chối, không tạo đường dẫn từ input |
| `C:\\Windows\\system.ini` | Đường dẫn Windows | Từ chối dấu phân cách đường dẫn và ký tự đặc biệt |
| `invoice.pdf.exe` | Giả dạng phần mở rộng | Không suy MIME từ đuôi đầu tiên |
| `.env` hoặc `.ssh` | Trùng tên file ẩn/cấu hình | Từ chối theo chính sách nghiệp vụ |
| `CON.pdf`, `NUL.txt` | Tên đặc biệt trên một số OS | Chặn khi có thể tương tác với filesystem Windows |
| Tên có byte NUL/ký tự điều khiển | Gây lỗi xử lý/ghi log | Từ chối |
| Tên có Unicode bidi override | Giả hiển thị phần mở rộng | Loại bỏ/từ chối ký tự định dạng nguy hiểm |
| `report.pdf   ` | Gây khác biệt giữa hiển thị và filesystem | Chuẩn hóa hoặc từ chối rõ ràng |
| Chuỗi dài hàng trăm KB | Tấn công tài nguyên/log/UI | Giới hạn độ dài sớm |
| Không có filename | Hợp lệ với một số attachment | Áp dụng policy: có thể sinh tên hiển thị |

Không nên giải quyết bằng cách lấy tên có sẵn và cắt bỏ `../` rồi dùng tiếp. Những cách biểu diễn khác nhau, URL encoding, Unicode normalization và hệ điều hành có thể khiến tên tưởng đã sạch trở nên nguy hiểm.

### 7.2. Ví dụ kiểm tra tên dùng để hiển thị

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.Set;

public final class DisplayFileNamePolicy {
    private static final Set<String> RESERVED =
            Set.of("CON", "PRN", "AUX", "NUL",
                   "COM1", "COM2", "LPT1", "LPT2");

    public static String validate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing filename");
        }
        String name = Normalizer.normalize(
                raw, Normalizer.Form.NFC);

        if (name.isBlank() || name.length() > 120
                || !name.equals(name.strip())
                || name.equals(".") || name.equals("..")
                || name.startsWith(".") || name.endsWith(".")) {
            throw new IllegalArgumentException("Invalid filename");
        }

        for (int i = 0; i < name.length();) {
            int cp = name.codePointAt(i);
            if (cp == '/' || cp == '\\' || cp == ':'
                    || Character.isISOControl(cp)
                    || Character.getType(cp) == Character.FORMAT) {
                throw new IllegalArgumentException("Invalid filename");
            }
            i += Character.charCount(cp);
        }

        String stem = name.split("\\.", 2)[0]
                .toUpperCase(Locale.ROOT);
        if (RESERVED.contains(stem)) {
            throw new IllegalArgumentException("Reserved filename");
        }
        return name;
    }
}
~~~

Đây là **một policy minh họa**, không phải thuật toán an toàn hoàn chỉnh cho mọi hệ điều hành và mọi ngôn ngữ. Trong thực tế cần cân nhắc thêm tên dành riêng khác, Unicode confusables, separators khác, danh sách extension cho phép và cách hiển thị HTML an toàn.

Hàm trả về **tên hiển thị**, không phải tên dùng tạo `Path` trên server. Storage key phải do server sinh độc lập; nếu hiển thị tên trong giao diện web, vẫn áp dụng HTML escaping của tầng UI.

### 7.3. Lưu file bằng tên do server tạo

Không làm:

~~~java
// SAI: client kiểm soát đường dẫn.
Path target = uploadRoot.resolve(originalFileName);
Files.copy(attachment.getInputStream(), target);
~~~

Cách phù hợp:

~~~text
originalFileName (validated) = "invoice-1001.pdf"
storageKey (server-generated) = "6e93e9c3-...-4c72"
quarantinePath = /private/quarantine/<server-generated-id>.part
businessDocumentId = DOC-1001
~~~

Đường dẫn quarantine và storage phải được tạo từ các thành phần **server kiểm soát**, không lấy từ `Content-Disposition` hoặc `cid:`. Ngoài path traversal, cần tránh ghi đè, symlink attack, public execution directory và truy cập chéo tenant.

### 7.4. Khi dùng filename từ MIME header

`Content-Disposition` có grammar MIME riêng, có thể chứa quoting, escaping hoặc encoding theo các biến thể RFC. Không tách header bằng:

~~~java
String filename = contentDisposition.split("filename=")[1];
~~~

vì tham số có thể đặt theo thứ tự khác, có dấu chấm phẩy trong quoted string, sử dụng charset/encoding, hoặc không tồn tại. Nếu cần đọc, dùng parser MIME phù hợp framework và xác định nguồn metadata ưu tiên.

Với Spring-WS/SAAJ, đường truy cập raw MIME headers là **implementation-specific**. API `Attachment` chuẩn trong Spring-WS không nên bị diễn giải như `MultipartFile` có sẵn `getOriginalFilename()`.

## 8. Kiểm tra `Content-Type` và định dạng thực tế

### 8.1. Chỉ nhìn extension là không đủ

Ví dụ một request:

~~~text
originalFileName = customer-id.pdf
Content-Type     = application/pdf
bytes            = 4D 5A 90 00 ...  (dấu hiệu phần đầu của PE executable)
~~~

Trường hợp này **không nên được chấp nhận** như PDF chỉ vì hai metadata trùng nhau. Cần kiểm tra chữ ký định dạng (magic bytes), parser/decoder thực tế và chính sách nội dung.

Tương tự:

~~~text
originalFileName = photo.png
Content-Type     = image/png
bytes            = 25 50 44 46 2D ...  (bắt đầu bằng %PDF-)
~~~

có sự **mâu thuẫn** giữa declared type và dữ liệu.

### 8.2. Các lớp xác minh nên kết hợp

| Bước | Phát hiện được gì? | Giới hạn |
| --- | --- | --- |
| Check MIME allowlist | Loại khai báo không được phép | Client có thể tự khai loại khác |
| Check file extension | Phát hiện mâu thuẫn tên/loại | Extension giả mạo rất dễ |
| Magic bytes | Nhận diện signature sơ bộ | File polyglot và dữ liệu hỏng vẫn có thể qua |
| Parse/decoder thực | Kiểm tra cú pháp/cấu trúc định dạng | Parser cần được harden; có thể tốn tài nguyên |
| Quét malware/content policy | Tìm nội dung độc hại theo quy tắc scanner | Không bảo đảm phát hiện mọi loại |
| Giới hạn bytes/quota | Giảm DoS do kích thước | Không tự ngăn ZIP bomb khi giải nén |
| Kiểm tra XML/XSD cho tài liệu XML | Đối chiếu contract tài liệu | Không thay parser security/XXE prevention |
| Đối chiếu hash nếu có | Phát hiện thay đổi bytes so với expected digest | Digest do attacker tự công bố không tạo tính xác thực |

**Không có một magic-byte check duy nhất nào chứng nhận file an toàn.** Ví dụ PDF có thể chứa nội dung active và ZIP có thể có tỉ lệ nén rất lớn; cần chọn mức xác minh tương xứng nguy cơ của định dạng được phép.

### 8.3. MIME allowlist thay vì denylist

Với hệ thống chỉ nhận chứng từ PDF/PNG:

~~~text
Cho phép:
  application/pdf
  image/png

Từ chối:
  application/x-msdownload
  application/javascript
  text/html
  application/octet-stream (nếu không có quy tắc xử lý riêng)
  mọi loại chưa được công bố
~~~

Một MIME type như `application/pdf; name="invoice.pdf"` cần được parse thành **media type chính** và tham số. Trong production, dùng parser MIME phù hợp thay vì chỉ tìm `string.contains("pdf")`.

## 9. Đọc stream có giới hạn và kiểm tra bytes trong Spring-WS

**Điểm quan trọng nhất của bảo vệ tài nguyên:** server phải đếm **bytes thực sự đọc**, không chỉ tin `Content-Length`, `Attachment.getSize()` hoặc `declaredSize` trong SOAP payload.

Ví dụ dưới đây nhận một Spring-WS `Attachment`, giới hạn **10 MiB**, chỉ cho phép PDF/PNG theo declared MIME và signature đầu file, ghi vào **vùng quarantine do server sở hữu**. Dữ liệu vẫn phải trải qua quét và xử lý nghiệp vụ trước khi được chấp nhận chính thức.

~~~java
package example.documents.security;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.Locale;
import org.springframework.ws.mime.Attachment;

public final class IncomingAttachmentPolicy {
    private static final long MAX_BYTES = 10L * 1024 * 1024;

    private static final byte[] PNG_SIGNATURE = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };
    private static final byte[] PDF_PREFIX = {
        0x25, 0x50, 0x44, 0x46, 0x2D
    };

    public record CheckedPart(
            Path quarantinePath,
            String mediaType,
            long actualBytes) {}

    public static CheckedPart copyToQuarantine(
            Attachment attachment, Path trustedQuarantineDir)
            throws IOException {

        String mime = baseMediaType(
                attachment.getContentType());
        if (!mime.equals("application/pdf")
                && !mime.equals("image/png")) {
            throw new IllegalArgumentException(
                    "Attachment media type not allowed");
        }

        // Directory phải tồn tại, thuộc server và không
        // cho client quyền thay thế file/symlink.
        Path temp = Files.createTempFile(
                trustedQuarantineDir, "incoming-", ".part");
        long total = 0L;

        try (InputStream raw = attachment.getInputStream();
             BufferedInputStream input =
                     new BufferedInputStream(raw);
             OutputStream output = Files.newOutputStream(
                     temp,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING)) {

            input.mark(8);
            byte[] prefix = input.readNBytes(8);
            input.reset();

            if (!matchesSignature(mime, prefix)) {
                throw new IllegalArgumentException(
                        "Attachment content does not match type");
            }

            byte[] buffer = new byte[8192];
            int n;
            while ((n = input.read(buffer)) != -1) {
                if (n > MAX_BYTES - total) {
                    throw new IllegalArgumentException(
                            "Attachment too large");
                }
                output.write(buffer, 0, n);
                total += n;
            }

            if (total == 0) {
                throw new IllegalArgumentException(
                        "Empty attachment");
            }
        } catch (IOException | RuntimeException e) {
            try {
                Files.deleteIfExists(temp);
            } catch (IOException cleanup) {
                e.addSuppressed(cleanup);
            }
            throw e;
        }

        // Chỉ trả đường dẫn quarantine; CHƯA promote
        // vào storage chính hoặc coi file đã an toàn.
        return new CheckedPart(temp, mime, total);
    }

    private static String baseMediaType(String raw) {
        if (raw == null) {
            return "";
        }
        // Demo đơn giản: production dùng MIME parser
        // xử lý đầy đủ grammar và tham số.
        return raw.split(";", 2)[0]
                .trim()
                .toLowerCase(Locale.ROOT);
    }

    private static boolean matchesSignature(
            String mime, byte[] prefix) {
        byte[] magic = mime.equals("application/pdf")
                ? PDF_PREFIX : PNG_SIGNATURE;
        if (prefix.length < magic.length) {
            return false;
        }
        return Arrays.equals(
                Arrays.copyOf(prefix, magic.length), magic);
    }
}
~~~

### 9.1. Điều gì làm ví dụ này an toàn hơn cách đọc toàn bộ?

- **Giới hạn 10 MiB** được kiểm tra trong vòng lặp đọc, không tin con số khai báo.
- Chỉ giữ buffer vài KiB, không tạo `byte[]` lớn bằng kích thước file.
- Kiểm tra chữ ký sơ bộ trước khi ghi toàn bộ.
- Tạo temp file bằng **API của server** thay vì tên tệp client gửi.
- Dọn temp file khi đọc bị lỗi, quá kích thước hoặc không khớp signature.
- Đóng input/output streams qua `try-with-resources`.
- Không đưa file trực tiếp vào web root hoặc thư mục có thể thực thi.

### 9.2. Những giới hạn còn phải bổ sung

Đoạn mã là **công đoạn kiểm tra sơ bộ**, không phải bộ tiếp nhận tệp đủ tiêu chuẩn production:

1. **PDF:** cần kiểm tra bằng parser/sandbox và chính sách về active content, embedded objects, JavaScript, số trang, mã hóa, mật khẩu.
2. **PNG:** cần decoder kiểm tra cấu trúc, chiều rộng/cao, số pixel và bộ nhớ cần giải mã; signature đúng không chứng minh ảnh hợp lệ.
3. **Nhiều attachment:** tổng dung lượng request và số parts cũng phải được giới hạn **trước** khi đọc hết vào memory.
4. **Quarantine permissions:** directory phải riêng tư, file không được thực thi, quota đĩa và cleanup stale files.
5. **Scanner/approval:** chỉ sau quét/kiểm tra nội dung mới chuyển file vào kho chính một cách nguyên tử và kiểm soát quyền.
6. **Hash:** có thể tính SHA-256 **khi streaming**, lưu digest thực tế và đối chiếu digest bên gửi nếu hợp đồng yêu cầu.
7. **Response:** không trả receipt `ACCEPTED` theo nghĩa nghiệp vụ trước khi đạt mốc tiếp nhận đã cam kết.

Nếu scan thực hiện bất đồng bộ, trạng thái phù hợp có thể là `QUARANTINED` hoặc `PENDING_VALIDATION` thay vì `READY`. Client cần biết trạng thái trong response hoặc operation tra cứu, tránh coi SOAP response 200 là bằng chứng file an toàn.

### 9.3. Chặn tại nhiều tầng

~~~text
API gateway:         tổng kích thước HTTP body
Servlet/transport:   timeout và giới hạn request
SOAP/MIME parser:    số lượng parts, header sizes, resource limits
Application:        số part cho phép và quyền upload
Attachment stream:  bytes thực đọc mỗi part
Format decoder:     pixel/page/entry/decompressed size
Storage:            quota tenant, quarantine, retention
~~~

Giới hạn 10 MiB trên application stream **không đủ** nếu SOAP parser đã buffer 2 GiB vào memory trước khi tạo `Attachment`. Phải kiểm tra đặc tính buffering/streaming của message factory và giới hạn ở gateway/Servlet.

## 10. Kiểm tra tính nhất quán giữa SOAP payload và MIME parts

Ví dụ contract yêu cầu mỗi `UploadDocumentRequest` tham chiếu **đúng một** tài liệu bằng `attachmentRef`. Một request có thể có ba trạng thái:

~~~text
SOAP attachmentRef = cid:invoice-1001@example.test

MIME parts:
  A: Content-ID invoice-1001@example.test, application/pdf
  B: Content-ID extra-0001@example.test, application/octet-stream
~~~

Part A đúng reference nhưng part B là **phần dư**. Nếu policy cho phép đúng một tệp, server nên từ chối hoặc có quy tắc xử lý part dư rõ ràng; không âm thầm lưu mọi attachment được gửi thêm.

### 10.1. Quy tắc đối chiếu tối thiểu

1. **Đếm parts** và giới hạn số lượng trước khi bắt đầu nghiệp vụ.
2. Kiểm tra **Content-ID** không trùng lặp theo quy tắc MIME parser.
3. Với mỗi tham chiếu `cid:` hợp đồng, xác nhận có **đúng một part** tương ứng.
4. Từ chối các tham chiếu `cid:` không tìm thấy, không đúng cú pháp hoặc thuộc message khác.
5. Đối chiếu `declaredContentType` trong XML với `Content-Type` ở MIME part theo quy tắc đã công bố.
6. Đối chiếu `declaredSize` với **số byte thực đọc**, không dùng để cấp phép dung lượng.
7. Nếu có digest, đối chiếu hash tính từ **bytes thực tế**, chỉ coi là xác thực nguồn nếu metadata digest được bảo vệ đủ mạnh theo policy.
8. Sau khi đạt validation và authorization, gán attachment vào **documentId/tenant** đã xác minh.

### 10.2. Vì sao phải kiểm tra part dư?

Một request có thể chứa SOAP Body hợp XSD, tham chiếu đúng một attachment PDF, nhưng thêm nhiều MIME parts lớn không được nghiệp vụ dùng đến. Nếu message factory vẫn đọc/buffer tất cả, hệ thống có thể chịu tấn công **memory/disk exhaustion** mặc dù payload nghiệp vụ hợp lệ.

Do đó số lượng MIME parts, tổng dung lượng và chính sách **unreferenced attachments** phải được công bố/kiểm thử, không chỉ tin rằng hệ thống sẽ bỏ qua phần dư miễn phí.

### 10.3. Hash và xác thực nguồn

Giả sử SOAP payload khai báo:

~~~xml
<d:sha256>03a8...c4f0</d:sha256>
~~~

Server tính digest từ bytes trong MIME part rồi so sánh. Phép đối chiếu đó phát hiện **không nhất quán giữa hai trường**; nhưng nếu attacker kiểm soát cả tệp và `sha256`, họ có thể tạo digest khớp cho tệp độc hại.

Để có bằng chứng **tính toàn vẹn và nguồn gửi**, cần một cơ chế đã xác thực, chẳng hạn WS-Security signature bảo vệ đúng dữ liệu/header hoặc một digest được ký theo contract, cùng kiểm tra danh tính người gửi. Không tự suy “SHA-256 khớp” là “an toàn” hoặc “đã được ký”.

## 11. Tạo SOAP attachment từ Spring-WS client

Spring-WS `WebServiceTemplate` có thể chuẩn bị SOAP message qua `WebServiceMessageCallback`. Nếu message factory hỗ trợ MIME, callback có thể thêm attachment bằng `MimeMessage.addAttachment(...)`.

Ví dụ gửi một tài liệu PDF được server ứng dụng biết rõ:

~~~java
package example.documents.client;

import java.io.File;
import jakarta.activation.DataHandler;
import jakarta.activation.FileDataSource;
import javax.xml.transform.TransformerFactory;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.mime.MimeMessage;
import org.springframework.xml.transform.StringSource;

public final class DocumentSoapClient {
    private final WebServiceTemplate template;

    public DocumentSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object upload(File file) {
        String cid = "invoice-1001@example.test";

        String payload =
                "<d:UploadDocumentRequest " +
                "xmlns:d=\"urn:example:documents:v1\">" +
                "<d:documentId>DOC-1001</d:documentId>" +
                "<d:originalFileName>invoice-1001.pdf</d:originalFileName>" +
                "<d:declaredContentType>application/pdf</d:declaredContentType>" +
                "<d:attachmentRef>cid:" + cid + "</d:attachmentRef>" +
                "</d:UploadDocumentRequest>";

        return template.sendAndReceive(
                "https://partner.example.test/ws/documents",
                message -> {
                    TransformerFactory.newInstance()
                            .newTransformer()
                            .transform(
                                new StringSource(payload),
                                message.getPayloadResult());

                    if (!(message instanceof MimeMessage mime)) {
                        throw new IllegalStateException(
                                "MIME attachments unsupported");
                    }

                    FileDataSource source = new FileDataSource(file) {
                        @Override
                        public String getContentType() {
                            return "application/pdf";
                        }
                    };
                    mime.addAttachment(cid, new DataHandler(source));
                },
                response -> {
                    // Ví dụ: response được xử lý theo SOAP contract.
                    // Ở production phải đọc/validate receipt payload.
                    return response.getPayloadSource() != null;
                });
    }
}
~~~

**Phạm vi ví dụ:** API `DataHandler`/`FileDataSource` dùng namespace **Jakarta Activation** trong stack mới; project Spring-WS/Java EE cũ có thể dùng `javax.activation`. Hãy chọn nhất quán dependency SOAP/JAXB/Activation của phiên bản đang chạy, không trộn namespace hai thế hệ.

Các điểm cần chú ý:

- `cid` trong SOAP payload và Content-ID của attachment được đặt nhất quán theo contract.
- `FileDataSource` có thể đoán MIME type theo file name/system mapping; ví dụ override `getContentType()` để khai báo minh họa rõ ràng, **không phải xác thực PDF**.
- Object `File` phải trỏ tới nguồn dữ liệu **ứng dụng đã cho phép**; không nhận path tùy ý từ request khác rồi gửi đi.
- `DataHandler` có thể đọc từ file khi SOAP message được serialize; giữ file có thể đọc được cho tới khi gửi xong, tránh xóa quá sớm.
- Nếu cần SOAP Action hoặc WS-Security, phải phối hợp callback/interceptor phù hợp; ví dụ trên không tự cấu hình chúng.
- Response extractor trả boolean minh họa việc có payload, **không phải xác nhận tài liệu đã được lưu an toàn**.

### 11.1. Tên tệp có tự được gửi cùng `DataHandler` không?

**Không nên giả định.** `DataHandler` có thể liên hệ với `DataSource.getName()`, nhưng việc SOAP implementation có thêm `Content-Disposition: filename` hay không phụ thuộc serializer/provider và cấu hình. Nếu bên nhận cần tên file ổn định, **đặt nó trong SOAP payload theo XSD** (như `originalFileName`) và kiểm chứng metadata thực tế trên dây.

Không suy rằng `mime.addAttachment(cid, dataHandler)` bảo đảm part nhận được có tên file; **Content-ID**, **Content-Type** và **filename** là các thuộc tính khác nhau.

### 11.2. Hành vi streaming phụ thuộc message factory

Đưa `DataHandler` vào message **không bảo đảm** toàn bộ đường truyền hoàn toàn streaming. SOAP message factory, SAAJ, transport sender và security interceptor có thể cần buffer nội dung để xây dựng, ký hoặc serialize. Khi gửi file lớn, cần đo memory/latency của stack thực tế và áp giới hạn client/server phù hợp.

## 12. Trường hợp MTOM/JAXB: `DataHandler` thay vì tự quản MIME part

Nếu contract biểu diễn nội dung tài liệu bằng `xs:base64Binary`, MTOM/JAXB có thể là cách tự nhiên hơn so với thiết kế `attachmentRef` thủ công:

~~~xml
<xs:element name="UploadDocumentRequest">
    <xs:complexType>
        <xs:sequence>
            <xs:element name="documentId" type="xs:string"/>
            <xs:element name="content" type="xs:base64Binary"/>
        </xs:sequence>
    </xs:complexType>
</xs:element>
~~~

Một binding JAXB có thể biểu diễn `content` bằng `byte[]` hoặc `DataHandler`, tùy schema/binding/generated code và tùy chọn MIME:

~~~java
// Mã minh họa hình dạng property JAXB.
@jakarta.xml.bind.annotation.XmlMimeType("application/pdf")
protected jakarta.activation.DataHandler content;
~~~

Ví dụ cấu hình OXM:

~~~java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("example.documents.generated");
marshaller.setMtomEnabled(true);
~~~

`setMtomEnabled(true)` kích hoạt hỗ trợ MTOM của `Jaxb2Marshaller` theo môi trường tương ứng. Nhưng:

- **Không bảo đảm mọi field binary luôn được tách thành MIME part**; điều đó còn phụ thuộc binding JAXB, kích thước/loại nội dung và provider.
- **Không bảo đảm tên file** tự được truyền theo `DataHandler`.
- **Không chứng minh dữ liệu an toàn**; receiver vẫn phải kiểm tra bytes, quota, định dạng và quyền.
- XSD `xs:base64Binary` mô tả **giá trị nhị phân logic**, không tự ràng buộc định dạng file PDF.
- Nếu client đã sinh JAXB từ WSDL, hãy giữ schema/binding tương thích; không tự thay thế `xs:base64Binary` thành `cid:` text trong contract.

### 12.1. SwA reference khác XOP include

| Đặc điểm | SwA tham chiếu thủ công | MTOM/XOP |
| --- | --- | --- |
| Contract payload | Có thể dùng `cid:` trong element riêng theo quy ước | Thường là một field `xs:base64Binary` |
| Tương quan attachment | Ứng dụng xác minh `cid:` với Content-ID | Framework MTOM xử lý `xop:Include` và MIME part |
| API Java | `MimeMessage` / `Attachment` rõ ràng | JAXB/MTOM và `DataHandler` khi phù hợp |
| Filename | Không bảo đảm có sẵn | Cũng **không** bảo đảm có sẵn |
| Validation bytes | Bắt buộc bổ sung | **Vẫn** bắt buộc bổ sung |
| Tương thích | Theo WSDL/binding và profile đối tác | Theo MTOM/XOP support của hai phía |

Không trộn hai chiến lược trong cùng operation nếu chưa xác định rõ XML contract và packaging. Một SOAP client chỉ gửi multipart/related không chứng minh nó đã dùng MTOM đúng chuẩn.

## 13. Tổ chức tiếp nhận: tách metadata, nội dung và trạng thái xử lý

Một pipeline production nên phân tách:

~~~mermaid
flowchart TD
    A["SOAP request MIME"] --> B["Transport + SOAP/XML hardening"]
    B --> C["Authentication / authorization"]
    C --> D["Validate XSD payload + CID references"]
    D --> E["Check allowed MIME/filename/count"]
    E --> F["Bounded copy to quarantine"]
    F --> G["Deep inspection / malware scan"]
    G --> H{"Đạt policy?"}
    H -->|"Có"| I["Promote bằng server-generated key"]
    H -->|"Không"| J["Xóa/cách ly, trả lỗi theo contract"]
    I --> K["Receipt + status"]
~~~

Không có yêu cầu mọi bước đều nằm trong `@Endpoint`. Một thiết kế có thể dùng:

- Gateway/Servlet filter cho HTTP size/timeouts.
- SOAP message factory cho parsing MIME/SOAP.
- `PayloadValidatingInterceptor` cho XSD của **payload XML**.
- WS-Security interceptor và authorization policy.
- **Attachment acceptance service** chuyên đọc/đánh giá bytes.
- Quarantine/antivirus/content scanner và object storage.
- Business service tạo receipt/trạng thái, transaction và audit log.

### 13.1. Cẩn thận khi đặt logic vào `EndpointInterceptor`

Nếu interceptor đọc `Attachment.getInputStream()` để kiểm tra trước endpoint, stream có thể bị tiêu thụ. Một endpoint khác đọc lại part đó có thể nhận stream rỗng hoặc phải dựa vào khả năng replay/buffering cụ thể của provider.

Hai chiến lược rõ ràng:

1. **Ownership một lần:** interceptor đọc, kiểm tra, lưu quarantine rồi truyền một **validated handle/receipt** qua context/service cho endpoint; endpoint không đọc lại raw stream.
2. **Xử lý tại service nghiệp vụ:** interceptor chỉ kiểm tra header/permission, endpoint nhận message theo API phù hợp và gọi một acceptance service duy nhất sở hữu lần đọc stream.

Không mặc định `Attachment.getInputStream()` lúc nào cũng trả một stream replayable hoặc có thể gọi nhiều lần không tốn bộ nhớ. Cần đọc hợp đồng provider và kiểm thử với payload thực tế.

### 13.2. Quarantine không phải kho public

File vừa tải đến nên ở vùng có:

- Thư mục riêng, không public HTTP/static serving.
- Quyền filesystem hạn chế, không cho thực thi.
- Giới hạn quota, thời gian lưu và cleanup task.
- Metadata về request ID, tenant, scan status, SHA-256, bytes thực đọc.
- Quy trình chuyển vào kho chính **chỉ sau khi đạt policy**.

Khi upload thất bại giữa chừng, phải dọn temp và ghi trạng thái để tránh tệp mồ côi. Khi upload thành công nhưng scan bất đồng bộ, SOAP response phải nói đúng mốc xử lý (ví dụ `PENDING_SCAN`), không tự tuyên bố đã sẵn sàng cho download.

## 14. Threat model khi tiếp nhận attachment

Các rủi ro đến từ **dữ liệu nhị phân**, **metadata**, **SOAP/XML parser** và **quy trình lưu/trả file**.

### 14.1. Tấn công thông qua bytes

**File polyglot:** một file có thể được chế tạo để được diễn giải như nhiều định dạng. Magic bytes sơ bộ không đủ; cần decoder và policy định dạng thực.

**Malformed PDF/image:** parser dễ bị lỗi khi đọc cấu trúc hỏng, dữ liệu lồng sâu hoặc metadata rất lớn. Dùng thư viện được bảo trì, sandbox và giới hạn tài nguyên.

**Archive bomb:** ZIP nén nhỏ nhưng giải nén ra dung lượng cực lớn hoặc số file khổng lồ. Nếu cho phép archive, đặt giới hạn **tổng bytes sau giải nén**, số entry, độ sâu lồng nhau, path trong archive và thời gian xử lý. Kiểm tra kích thước file ZIP trên wire là chưa đủ.

**ZIP Slip:** entry tên `../../outside/file` có thể ghi ra khỏi extraction root nếu code dùng trực tiếp tên entry. Chỉ extract với path validation và policy rõ ràng, hoặc không cho phép archive khi nghiệp vụ không cần.

**SVG/HTML/script:** một số định dạng nhìn như “ảnh” nhưng có thể chứa script hoặc nội dung active. Không cho phép `image/svg+xml` chỉ vì người dùng muốn gửi hình ảnh nếu ứng dụng không có sanitizer và cách phục vụ file an toàn.

**Office/PDF active content:** có thể chứa macro, liên kết ngoài, nhúng object. Cần scan và profile xử lý/chuyển đổi phù hợp.

### 14.2. Tấn công qua metadata

- **Header injection/log injection** từ filename, Content-ID hoặc Content-Type dài và có ký tự điều khiển.
- **Path traversal** khi lưu file theo `filename` từ client.
- **Extension spoofing**: `invoice.pdf.exe`, Unicode bidi override hoặc double extension.
- **Content-Type spoofing**: khai `image/png` nhưng bytes khác.
- **Duplicate Content-ID** gây reference ambiguity.
- **Quota bypass** bằng nhiều MIME parts nhỏ, multipart header lớn hoặc stream chunked không có Content-Length đáng tin.
- **SSRF** nếu hệ thống biến `cid:` thành URL để tải, hoặc cho SOAP payload chứa đường dẫn `file:`/`http:` được fetch tùy ý.

### 14.3. Tấn công vào XML và SOAP stack

XML parser có thể gặp:

- **XXE** hoặc external DTD/schema resolution.
- SOAP Envelope cực lớn hoặc XML nesting sâu.
- `xop:Include`/MIME reference sai, trùng hoặc không được giải quyết.
- MIME boundary/header không hợp lệ làm parser tốn tài nguyên.
- Attachment nội dung không khớp XML infoset hợp đồng.

Những nguy cơ này cần **XML parser security, request limits và thư viện SOAP/MIME được cập nhật**, không thể chặn bằng một hàm kiểm tra extension.

### 14.4. Security header và attachment integrity

Một SOAP Body được ký theo WS-Security **không tự động chứng minh bytes của mọi MIME attachment đã được ký**. Hệ thống cần xác định:

1. Policy yêu cầu ký phần **SOAP Body**, **SOAP Header**, **attachment bytes** hay tất cả?
2. WSS4J/Spring-WS trong phiên bản triển khai có hỗ trợ đúng profile ký attachments được đối tác sử dụng không?
3. Chữ ký có bảo vệ liên kết giữa attachment reference và MIME part không?
4. Client/server có cùng cách xử lý encoding/canonicalization và các thay đổi MIME headers không?
5. Đường SOAP Fault và attachment response có cần xác minh chữ ký không?

Không thay thế attachment signature bằng cách tự hash bytes rồi lưu giá trị hash trong **một trường SOAP không được bảo vệ**. Xác thực nguồn và integrity là thuộc tính của cơ chế bảo mật đã được hai bên thống nhất.

## 15. Phân loại lỗi thành SOAP Fault và trạng thái tiếp nhận

Trong dịch vụ contract-first, **lỗi file** không nên xuất hiện dưới dạng một Java stack trace trong SOAP response. Có thể định nghĩa một fault contract như:

~~~xml
<err:AttachmentError
    xmlns:err="urn:example:documents:errors:v1">
    <err:code>ATTACHMENT_TYPE_NOT_ALLOWED</err:code>
    <err:correlationId>REQ-2005</err:correlationId>
</err:AttachmentError>
~~~

Đây là **XML chi tiết lỗi nghiệp vụ minh họa**, không phải output mặc định của Spring-WS. Muốn client nhận typed Fault, cần công bố XSD/WSDL tương ứng và cấu hình writer/resolver tạo Fault detail đúng QName.

### 15.1. Bảng lỗi đề xuất

| Lỗi phát hiện | Mã công khai tham khảo | Phân loại |
| --- | --- | --- |
| Thiếu `attachmentRef` hoặc sai XSD | `INVALID_DOCUMENT_REQUEST` | Lỗi request/schema |
| Không tìm thấy Content-ID tương ứng | `ATTACHMENT_REFERENCE_NOT_FOUND` | Lỗi request |
| Có nhiều part trùng ID | `DUPLICATE_ATTACHMENT_ID` | Lỗi request |
| Content-Type không nằm trong allowlist | `ATTACHMENT_TYPE_NOT_ALLOWED` | Lỗi request |
| Declared type không khớp magic/decoder | `ATTACHMENT_CONTENT_MISMATCH` | Lỗi request |
| Filename không đáp ứng policy | `INVALID_ATTACHMENT_FILENAME` | Lỗi request |
| Quá quota hoặc giới hạn bytes | `ATTACHMENT_TOO_LARGE` | Lỗi request/quota |
| File bị scanner phát hiện độc hại | `ATTACHMENT_REJECTED` | Lỗi an toàn nội dung |
| Scanner đang xử lý bất đồng bộ | `PENDING_SCAN` (response/status, không nhất thiết Fault) | Trạng thái nghiệp vụ |
| Dịch vụ lưu trữ không sẵn sàng | `STORAGE_TEMPORARILY_UNAVAILABLE` | Lỗi phía server |
| MIME parser quá tải | Mã lỗi được kiểm soát | Có thể xảy ra trước endpoint |
| TLS handshake lỗi | Không có SOAP Fault ứng dụng | Transport |

### 15.2. SOAP 1.1 và SOAP 1.2 Fault

Với SOAP 1.1, lỗi do client gửi dữ liệu sai thường được mô tả bằng `soap:Client`, lỗi server bằng `soap:Server`. SOAP 1.2 dùng `Sender`/`Receiver` tương ứng về mặt phân loại chung. Tuy nhiên mã Fault, HTTP status và format detail thực tế phụ thuộc SOAP binding và framework configuration.

**Không mặc định** một exception ở `EndpointInterceptor` sẽ đi qua cùng `SoapFaultMappingExceptionResolver` như exception được ném từ `@Endpoint`. Nếu muốn lỗi attachment có mã typed Fault ổn định, thiết kế rõ interceptor/service/resolver path và kiểm thử SOAP Envelope thực tế.

### 15.3. Giữ nội dung lỗi công khai tối thiểu

Client cần biết **mã lỗi**, **correlation ID** và hướng sửa phù hợp; không cần biết:

- Absolute path của quarantine hoặc storage root.
- Stack trace của SAAJ/MIME parser.
- Nội dung thực của file hoặc virus signature chi tiết.
- Internal object-storage bucket, credentials, key identifier.
- Toàn bộ `Content-Disposition` có dữ liệu lạ do attacker đưa vào.

Log nội bộ nên lưu error category, tenant được xác thực, content ID đã được làm sạch hoặc hash, số byte nhận và correlation ID, áp dụng masking và giới hạn kích thước.

### 15.4. Không phản hồi thành công quá sớm

Sau khi SOAP service nhận request:

~~~text
RECEIVED -> QUARANTINED -> SCANNING -> ACCEPTED -> AVAILABLE
                              \-> REJECTED
~~~

Nếu response `UploadDocumentResponse` chỉ xác nhận **tiếp nhận vào quarantine**, đừng đặt status `AVAILABLE`. Nếu xử lý đồng bộ và đã scan thành công, response có thể biểu diễn `ACCEPTED` theo contract. Định nghĩa rõ các mốc trạng thái để client không dùng một HTTP 200 làm chứng nhận tài liệu được phép tải xuống.

## 16. Chiến lược kiểm thử

Không nên chỉ viết unit test cho hàm `DisplayFileNamePolicy.validate(...)` rồi coi SOAP attachment upload đã an toàn. Cần test theo tầng và dữ liệu thực:

~~~mermaid
flowchart LR
    U["Unit: tên/MIME/bytes policy"] --> M["Spring-WS mock: SOAP + MIME"]
    M --> H["HTTP wire: multipart/related và MTOM"]
    H --> S["Security: scan/XXE/signature/quota"]
    S --> I["Interop: Java/.NET/đối tác thật"]
~~~

### 16.1. Unit test kiểm tra filename

Một vài test JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class DisplayFileNamePolicyTest {
    @Test
    void acceptsOrdinaryName() {
        assertEquals(
                "invoice-1001.pdf",
                DisplayFileNamePolicy.validate(
                        "invoice-1001.pdf"));
    }

    @Test
    void rejectsPathTraversal() {
        assertThrows(IllegalArgumentException.class, () ->
                DisplayFileNamePolicy.validate(
                        "../../config.yml"));
    }

    @Test
    void rejectsWindowsPath() {
        assertThrows(IllegalArgumentException.class, () ->
                DisplayFileNamePolicy.validate(
                        "C:\\\\private\\\\secret.pdf"));
    }
}
~~~

Đây là **test lớp policy**, chưa kiểm tra MIME parsing và SOAP request. Nếu dữ liệu filename đến từ header có encoding, cần parse header trước khi truyền vào policy, rồi kiểm thử cả các trường hợp có dấu nháy/charset/chuỗi không chuẩn.

### 16.2. Unit test stream policy

Với `IncomingAttachmentPolicy`, tạo các fixture chứa bytes kiểm soát:

~~~text
valid-pdf.bin:      25 50 44 46 2D ...
valid-png.bin:      89 50 4E 47 0D 0A 1A 0A ...
spoofed-png.bin:    25 50 44 46 2D ... (declared image/png)
invalid-random.bin: 00 FF 11 22 ...
large-file.bin:     > 10 MiB
empty.bin:          0 bytes
~~~

Test nên xác minh:

1. Chỉ nội dung có declared MIME **và signature sơ bộ** phù hợp mới qua bước check.
2. Tệp lớn bị từ chối dựa trên **bytes thực đọc**, dù metadata báo nhỏ.
3. Không có tệp temp mồ côi khi lỗi.
4. File nhỏ dưới 8 bytes bị từ chối, không gây lỗi out-of-bounds.
5. Stream đầu vào/đầu ra được đóng kể cả khi xảy ra exception.
6. Kết quả thành công **chỉ là quarantine handle**, không tự được public.

Việc tạo một `Attachment` giả tùy thuộc interface/provider/version Spring-WS đang dùng. Trong một bộ test thực tế, có thể dùng mock phù hợp hoặc tạo SOAP/MIME message với message factory để bao phủ parser, thay vì tự chế một implementation sai hợp đồng.

### 16.3. Spring-WS test và wire test

`MockWebServiceClient` hữu ích cho `@Endpoint` và interceptor ở server; `MockWebServiceServer` hữu ích cho client `WebServiceTemplate`. Nhưng **khả năng mock attachment/MTOM và cách tạo MIME response** thay đổi theo thư viện test và message factory.

Cần thêm **HTTP integration test gửi MIME thật** để kiểm chứng:

- Outer `multipart/related` và root SOAP part.
- `Content-ID`/`cid:` reference resolving.
- `Content-Type` attachment part có đúng giá trị được client gửi.
- Filename có/không có trong `Content-Disposition`.
- Trường hợp MTOM/XOP được unmarshal đúng từ JAXB `DataHandler`/`byte[]`.
- Server chặn payload/part lỗi trước khi lưu chính thức.
- HTTP status và SOAP Fault thực tế được client đọc đúng.

Không chỉ assert `getAttachments().hasNext()` rồi kết luận nội dung đã được validate.

### 16.4. Ma trận kiểm thử chi tiết

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Một PDF hợp lệ, MIME `application/pdf`, CID khớp | Qua bước validation sơ bộ; scan và lưu theo policy |
| PDF khai `image/png` | Từ chối mismatch |
| File thực thi khai `application/pdf` | Từ chối dựa trên bytes/decoder |
| `application/octet-stream` không có chính sách | Từ chối hoặc xử lý theo ngoại lệ hợp đồng |
| Filename `../../etc/passwd` | Từ chối; không tạo path từ client input |
| Filename chứa NUL/điều khiển/Unicode bidi | Từ chối hoặc làm sạch theo policy rõ |
| MIME part không có filename nhưng XSD cho phép | Sinh tên hiển thị an toàn hoặc xử lý theo hợp đồng |
| MIME filename khác `originalFileName` | Phát hiện mâu thuẫn, chọn nguồn chuẩn được công bố |
| SOAP `attachmentRef` không có MIME part | Lỗi reference |
| Hai MIME parts trùng Content-ID | Lỗi duplicate ID |
| Có MIME part dư không được tham chiếu | Từ chối nếu contract chỉ cho phép một tệp |
| `declaredSize=100` nhưng bytes 10000 | Phát hiện và áp giới hạn thực đọc |
| Stream vượt 10 MiB | Dừng đọc, dọn temp và phản hồi lỗi |
| Attachment rỗng | Từ chối nếu nghiệp vụ yêu cầu non-empty |
| PDF magic đúng nhưng file bị hỏng | Parser/scan sâu phát hiện |
| PNG có kích thước ảnh cực lớn | Giới hạn dimensions/pixels/decoder memory |
| ZIP có tỉ lệ nén cao | Không giải nén vô giới hạn |
| MTOM request với `xop:Include` đúng | Nhận đúng bytes theo contract |
| `xop:Include` trỏ CID thiếu | Từ chối/không unmarshal được |
| SOAP Body hợp XSD nhưng attachment độc hại | **Không chấp nhận tệp** |
| WS-Security chỉ ký Body, attachment bị đổi | Phát hiện thiếu coverage từ policy/test chữ ký |
| User chưa được cấp quyền upload | Authorization từ chối dù metadata đúng |
| HTTP body vượt gateway limit | Từ chối sớm, không phụ thuộc app stream quota |
| Upload thành công nhưng scanner offline | Trạng thái rõ ràng `PENDING` hoặc lỗi server theo contract |
| Lỗi lưu trữ sau khi copy quarantine | Dọn/đối soát, không báo `AVAILABLE` |
| HTTP 502 HTML từ gateway | Client xử lý transport, không coi là SOAP Fault |

### 16.5. Test tương thích đa nền tảng

Đối tác dùng Java, .NET hoặc một SOAP stack cũ có thể serialize MTOM/SwA khác nhau về:

- Content-ID có dấu `<...>` và dạng `cid:` đã escape.
- Header `Content-Disposition` có/không, cách encode filename.
- MIME boundary, root part, transfer encoding.
- `application/xop+xml`, `start-info` và SOAP 1.1/1.2.
- Cách biểu diễn JAXB `byte[]` vs `DataHandler`.
- WS-Security attachment signature profile.

Kiểm thử nên tập trung vào **ngữ nghĩa XML/MIME hợp đồng**, không yêu cầu hai thư viện phát ra byte-for-byte cùng một multipart body. Nhưng phải xác minh bytes attachment sau khi giải mã **không bị biến đổi ngoài ý muốn**.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| SOAP payload nhận được nhưng không thấy attachment | Không gửi multipart, message factory không hỗ trợ MIME, sai packaging | HTTP Content-Type, SOAP factory, root part |
| `getAttachment(contentId)` trả null | CID sai, escape/angle bracket khác, part thiếu | `Content-ID` thực, `cid:` href, parser |
| JAXB nhận `byte[]` inline thay vì MIME | MTOM chưa bật hoặc binding provider chọn inline | `setMtomEnabled`, WSDL/XSD, wire |
| Filename luôn null | MIME header không gửi, API không cung cấp | SOAP metadata và raw MIME headers có kiểm soát |
| File `.pdf` nhưng decoder lỗi | Bytes không phải PDF hoặc dữ liệu bị hỏng | Magic, stream, content encoding |
| File nhỏ nhưng hết RAM | SOAP parser buffer, decoder expand, số parts nhiều | Gateway limits, factory behavior, memory profiling |
| File lớn được chấp nhận khi Content-Length nhỏ | Tin metadata thay vì bytes thực | Vòng lặp giới hạn bytes và total quota |
| Temp file mồ côi sau Fault | Không cleanup khi exception hoặc timeout | Quarantine lifecycle/finally và recovery job |
| Attachment được lưu ở path lạ | Filename/Content-ID dùng làm path | Storage key do server sinh |
| Client thấy SOAP Fault không đúng XSD | Fault detail không theo contract | XSD/WSDL fault, resolver và wire response |
| HTTP 413 nhưng không có SOAP Fault | Gateway/Servlet chặn trước SOAP dispatcher | HTTP error contract, client transport handler |
| Security signature hợp lệ nhưng file đã bị thay | Không ký attachment part/metadata | WS-Security signed parts/attachment policy |
| PDF scan pass nhưng client tải bản khác | Storage promotion/race, thiếu hash/authorization | Immutable object key, atomic promote và digest |

### 17.1. Quy trình debug từ ngoài vào trong

1. **HTTP:** Content-Type có phải `multipart/related` theo binding? Có bị chặn ở gateway không?
2. **SOAP:** Envelope/version, root part và Content-ID có parse được?
3. **Schema:** SOAP Body có hợp XSD?
4. **Reference:** `cid:` trong payload/XOP có map tới đúng MIME part?
5. **Metadata:** Content-Type, filename, số lượng parts có hợp policy?
6. **Bytes:** thực tế đã đọc bao nhiêu byte, magic/decoder có khớp?
7. **Security:** authentication, signed parts, WS-Security policy và quota?
8. **Storage:** file có vào quarantine, scanner có hoàn thành, promote có atomic?
9. **Fault:** client nhận SOAP Fault hợp đồng hay HTTP transport error?
10. **Observability:** correlation ID có nối được request, scan status và storage object?

Tránh bật log nguyên MIME body để debug: file có thể chứa PII, dữ liệu hợp đồng bảo mật hoặc nội dung gây tấn công log/parser. Ghi metadata đã lọc và hash/size khi cần.

## 18. Bài tập tình huống: chứng từ được lưu sai tên và sai định dạng

Hệ thống kế toán dùng Spring-WS để nhận SOAP request `UploadDocumentRequest`. Một đối tác gửi:

~~~xml
<d:UploadDocumentRequest
    xmlns:d="urn:example:documents:v1">
    <d:documentId>DOC-8821</d:documentId>
    <d:originalFileName>../../exports/invoice.pdf</d:originalFileName>
    <d:declaredContentType>application/pdf</d:declaredContentType>
    <d:attachmentRef>cid:doc-8821@example.test</d:attachmentRef>
    <d:declaredSize>1024</d:declaredSize>
</d:UploadDocumentRequest>
~~~

MIME part:

~~~text
Content-ID: <doc-8821@example.test>
Content-Type: application/pdf
Content-Disposition: attachment; filename="../../exports/invoice.pdf"
Content-Transfer-Encoding: binary

[bytes bắt đầu bằng 50 4B 03 04 ... và tổng dung lượng 15 MiB]
~~~

Đội phát triển hiện đang dùng:

~~~java
String name = uploadRequest.getOriginalFileName();
Path target = storageRoot.resolve(name);
Files.copy(attachment.getInputStream(), target);
return "ACCEPTED";
~~~

**Câu hỏi:**

1. Những dữ liệu nào trong request có thể bị giả mạo?
2. `attachmentRef` có khớp MIME part không, và khớp CID có đủ để chấp nhận không?
3. Vì sao đường dẫn `../../exports/invoice.pdf` nguy hiểm?
4. Vì sao file không nên được coi là PDF mặc dù tên và Content-Type cùng kết thúc bằng PDF?
5. `declaredSize=1024` có giúp giảm dung lượng thực đã đọc?
6. Khi nào được trả `ACCEPTED` hoặc `AVAILABLE` cho client?
7. Nếu SOAP Body được WS-Security ký, bytes MIME attachment đã chắc chắn có tính toàn vẹn chưa?
8. Nếu file quá lớn bị gateway chặn bằng HTTP 413, client có nhất thiết nhận SOAP Fault không?

**Đáp án gợi ý:**

1. `originalFileName`, `declaredContentType`, `declaredSize`, `attachmentRef` và MIME headers đều là dữ liệu do client kiểm soát; phải được kiểm tra.
2. CID có thể khớp sau khi parse đúng, nhưng server vẫn phải xác minh media type, bytes, quota, quyền và scanner.
3. Dấu `../` có thể đi ra khỏi thư mục đích. Không dùng tên client làm storage path; tạo key riêng phía server.
4. Bytes `50 4B 03 04` thường là ZIP signature, **không phải** PDF prefix `25 50 44 46 2D`. Vẫn cần parser/scan sâu ngay cả khi magic đúng.
5. **Không.** Đây chỉ là số khai báo. Server phải giới hạn dựa trên 15 MiB bytes thực nhận, đồng thời giới hạn gateway/MIME parser từ sớm.
6. Theo mốc được contract quy định: nếu mới quarantine thì trả trạng thái chờ scan; chỉ trả sẵn sàng sau khi validation/scan và storage promotion hoàn tất.
7. **Chưa chắc.** Cần policy ký/kiểm tra attachment bytes hoặc digest/metadata đã xác thực theo profile WS-Security sử dụng.
8. **Không.** Lỗi HTTP trước khi vào SOAP dispatcher có thể chỉ là response HTTP không có SOAP Envelope; client phải xử lý transport error riêng.

### 18.1. Nhiệm vụ thực hành

Hãy xây dựng `DocumentUploadService` đáp ứng:

- XSD định nghĩa `UploadDocumentRequest` với filename, declared type, CID reference và documentId.
- SOAP server Spring-WS đọc một MIME attachment qua `MimeMessage`.
- Kiểm tra chính xác một part, CID đúng, MIME allowlist chỉ `application/pdf` và `image/png`.
- Từ chối filename có path separator, control/bidi và độ dài vượt giới hạn.
- Stream vào quarantine bằng buffer 8 KiB và giới hạn 10 MiB thực đọc.
- Quét/parse định dạng trong môi trường có giới hạn tài nguyên.
- Dùng storage key do server sinh, không dùng client filename.
- Trả receipt và status đúng lifecycle; định nghĩa Fault detail ổn định khi bị từ chối.
- Ghi log an toàn và kiểm thử các ca trong mục 16.

**Tiêu chí hoàn thành:** một SOAP request hợp XSD nhưng MIME attachment sai kiểu/độc hại vẫn bị từ chối, không có path traversal, không có quota bypass, không có tệp mồ côi và client phân biệt được lỗi SOAP với lỗi HTTP.

## 19. Checklist trước khi triển khai tiếp nhận SOAP attachment

1. **Contract:** xác định SwA reference hay MTOM/XOP; XSD/WSDL mô tả payload đúng format.
2. **Version:** SOAP 1.1/1.2, MIME root Content-Type và MTOM binding tương thích.
3. **Content-ID:** tham chiếu `cid:` hợp lệ, duy nhất, được gắn đúng MIME part.
4. **Filename:** biết metadata đến từ SOAP field hay `Content-Disposition`; không giả định `Attachment` có `getOriginalFilename()`.
5. **Validation filename:** giới hạn độ dài, ký tự điều khiển, path separators, Unicode và reserved names theo policy.
6. **Storage key:** luôn do server sinh; quarantine riêng, không public/thực thi.
7. **MIME allowlist:** chỉ cho phép media type nghiệp vụ cần, không tin tên/extension.
8. **Binary inspection:** kiểm tra signature, decoder/format parser và malware scan theo mức rủi ro.
9. **Quota:** giới hạn bytes **thực đọc**, số lượng parts, tổng request và dung lượng sau giải nén nếu có archive.
10. **Streaming:** đo buffering của SOAP/MIME factory, SAAJ/JAXB/MTOM, security sender và memory thực tế.
11. **Input stream ownership:** đóng stream, không đọc lại một nguồn đã bị tiêu thụ nếu provider không bảo đảm.
12. **Integrity:** tính hash bytes thực tế; khi cần xác thực nguồn, dùng chữ ký/policy được kiểm chứng.
13. **Security:** XML parser hardening, XSD, WS-Security, certificate/TLS và authorization độc lập.
14. **Fault:** trả lỗi ổn định cho MIME/file violations, không lộ stack trace hoặc dữ liệu nhạy cảm.
15. **Async scan:** response phân biệt `QUARANTINED`, `PENDING_SCAN`, `ACCEPTED`, `AVAILABLE`.
16. **Cleanup:** dọn temp file khi lỗi, timeout hoặc request bị hủy; có recovery job cho file mồ côi.
17. **Observability:** correlation ID, tenant, mã lỗi, byte count, hash và scan result được ghi an toàn.
18. **Test:** gửi MIME body thật với CID đúng/sai, type spoofing, filename độc hại, file quá lớn, MTOM và SOAP Fault.
19. **Compatibility:** chạy test với SOAP/JAXB implementation của đối tác, không chỉ Spring-WS mock.
20. **Governance:** đánh giá retention, privacy, quyền tải về và chính sách xóa tài liệu sau khi lưu.

## 20. Ghi nhớ

- **SOAP attachments** thường được đóng gói bằng MIME `multipart/related`, khác HTTP `multipart/form-data` dùng cho upload qua Spring MVC.
- **`Content-Type` là loại được khai báo, không phải bằng chứng của bytes thực tế**. Chỉ chấp nhận allowlist và kiểm tra magic/decoder/scanner phù hợp.
- **Filename không phải thuộc tính bắt buộc của MIME attachment**; Spring-WS `Attachment` không có semantics `getOriginalFilename()` của `MultipartFile`. Nếu cần tên file ổn định, định nghĩa trong SOAP XSD hoặc đọc header theo provider với parser chuẩn.
- **`Content-ID` dùng để tham chiếu MIME part**, không phải filename, đường dẫn lưu trữ, hash hay danh tính của client.
- **MTOM/XOP** tối ưu cách gửi `xs:base64Binary` và liên kết MIME bytes, nhưng không tự kiểm tra tính an toàn, kích thước hay tên tệp.
- **SOAP payload hợp XSD không chứng minh attachment an toàn**; cần kiểm tra part count, CID, MIME, filename, bytes, quota, định dạng và nghiệp vụ.
- **Giới hạn dung lượng phải đếm bytes thực đọc**, đồng thời áp giới hạn sớm ở gateway, Servlet và SOAP/MIME parser.
- **Không dùng filename hoặc CID do client gửi làm đường dẫn lưu file**. Dùng server-generated key và quarantine, chỉ đưa vào kho chính sau khi đạt chính sách.
- **WS-Security ký SOAP Body không mặc nhiên bao phủ MIME attachment bytes**; phải cấu hình/kiểm thử signed parts và integrity policy thực tế.
- **SOAP Fault khác HTTP/TLS failure**; phản hồi phải diễn đạt đúng trạng thái nhận, quét, lưu và đối soát tài liệu.
- Kiểm thử thành công cần bao phủ **MIME trên dây, Content-Type, tên tệp, dữ liệu thực, SOAP 1.1/1.2, SwA/MTOM, XSD/JAXB, WS-Security và khả năng tương thích với đối tác**.




