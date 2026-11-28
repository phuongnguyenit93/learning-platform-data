# Ảnh hưởng của interceptor đến streaming, chữ ký và dữ liệu nhạy cảm

> **Chương:** Interceptor  
> **Phạm vi:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP contract-first bằng Spring Web Services (Spring-WS), từ XSD/WSDL, JAXB/OXM, endpoint và SOAP client đến SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tích hợp doanh nghiệp.

## 1. Mục tiêu: interceptor quan sát thông điệp mà không phá hợp đồng

Một SOAP interceptor có thể kiểm tra, ghi nhận hoặc biến đổi message ở đường vào/ra endpoint. Đây là công cụ hữu ích để triển khai validation, security, tracing và một số chính sách xuyên suốt. Tuy nhiên, những hành động tưởng như vô hại — “đọc SOAP Body để log”, “lấy chuỗi XML để đo kích thước”, “chỉnh header cho dễ debug” — có thể làm thay đổi **khả năng streaming**, phá **chữ ký XML**, hoặc để lộ **dữ liệu nhạy cảm**.

Trong Spring-WS, phải phân biệt ít nhất ba vấn đề:

1. **Streaming:** message đã nằm hết trong bộ nhớ, hay một phần vẫn được đọc/ghi qua stream? Interceptor có buộc dữ liệu được materialize thành DOM/byte array hay không?
2. **Tính toàn vẹn và an toàn:** message có được ký, mã hóa và xác thực theo WS-Security? Một thay đổi ở Body/Header có khiến bên nhận không xác minh được chữ ký?
3. **Quyền riêng tư và an ninh vận hành:** logger, tracer, metrics hoặc exception handler có vô tình ghi token, thông tin khách hàng, dữ liệu cá nhân, tài liệu đính kèm, private key hay không?

Sau bài học, bạn sẽ:

- Hiểu vị trí `EndpointInterceptor` và `ClientInterceptor` trong pipeline.
- Phân biệt “đọc được `Source`” với “đọc được nhiều lần không làm mất streaming”.
- Biết vì sao SOAP Signature/XML Encryption phải được xử lý theo thứ tự và policy được chốt.
- Viết interceptor thu thập **metadata an toàn**, không log SOAP Body.
- Thiết kế logging/redaction, giới hạn tài nguyên, kiểm thử với MTOM/XOP và WS-Security.
- Kiểm chứng bằng test rằng một interceptor không làm hỏng SOAP response, chữ ký và client tương thích.

**Nguyên tắc tổng quát:** interceptor càng gần nội dung SOAP thì càng cần hợp đồng rõ về **thời điểm chạy, trạng thái đã xác thực, chi phí bộ nhớ và dữ liệu được phép giữ lại**.

## 2. Vị trí của interceptor trong Spring-WS

Spring-WS nhận SOAP qua transport, thường là `MessageDispatcherServlet` trên HTTP, rồi dùng `MessageDispatcher` để tìm endpoint và xử lý. `EndpointInterceptor` được áp dụng quanh việc gọi endpoint theo cấu hình mapping/interceptor chain tương ứng.

~~~mermaid
flowchart TD
    Client["SOAP client"]
    Http["HTTP / TLS / proxy"]
    Factory["SOAP message factory / parsing"]
    Mapping["EndpointMapping: payload QName / action"]
    Chain["EndpointInterceptor chain"]
    Adapter["EndpointAdapter / JAXB-OXM"]
    Endpoint["&#64;Endpoint"]
    Business["Business service"]
    Client --> Http --> Factory --> Mapping --> Chain --> Adapter --> Endpoint --> Business
    Business --> Endpoint --> Adapter --> Chain --> Factory --> Http --> Client
    Factory -. "Có lỗi trước mapping" .-> Fault["Protocol/transport Fault hoặc lỗi HTTP"]
    Chain -. "Validation / security Fault" .-> Fault
~~~

Sơ đồ mô tả trách nhiệm, không phải cam kết thứ tự nội bộ cho mọi phiên bản Spring-WS/message factory. Đặc biệt, một request XML không well-formed hoặc SOAP version không được hỗ trợ có thể bị từ chối **trước khi endpoint interceptor chạy**.

### 2.1. Các callback quan trọng

Với `org.springframework.ws.server.EndpointInterceptor`, các bước phổ biến gồm:

| Callback | Ý nghĩa ở mức hợp đồng | Điều cần lưu ý |
|---|---|---|
| `handleRequest(MessageContext, Object endpoint)` | Trước khi gọi endpoint đã được ánh xạ | Có thể trả `false` để không tiếp tục chuỗi/gọi endpoint |
| `handleResponse(MessageContext, Object endpoint)` | Xử lý khi có SOAP response bình thường | Không mặc định có ở mọi đường lỗi/không có response |
| `handleFault(MessageContext, Object endpoint)` | Xử lý khi response là SOAP Fault | Không phải mọi lỗi parser/transport đều tới đây |
| `afterCompletion(MessageContext, Object endpoint, Exception ex)` | Dọn dẹp/ghi nhận sau khi xử lý endpoint theo contract framework | Không xem là cơ chế thay thế cho đóng stream/tài nguyên ở mọi tầng |

Trong một số phiên bản có adapter hỗ trợ phương thức mặc định hoặc class convenience, nhưng với code triển khai nên kiểm tra JavaDoc **đúng version** của `EndpointInterceptor`. Các method có thể ném `Exception` và không nên ép swallow mọi lỗi.

Phía client Spring-WS có `ClientInterceptor` trong `WebServiceTemplate`, nhưng **lifecycle và tham số callback không đồng nhất hoàn toàn** với interceptor server. Không sao chép nguyên xi class server sang client.

### 2.2. Interceptor không giống servlet filter

| Cơ chế | Lớp xử lý | Thường thấy dữ liệu nào? |
|---|---|---|
| Servlet filter | HTTP transport | URL, headers, content length, raw body nếu chủ động đọc |
| SOAP message factory | SOAP message construction | SOAP Envelope và MIME/MTOM theo implementation |
| Endpoint mapping | Spring-WS dispatch | Payload root QName, SOAPAction hoặc WS-Addressing Action |
| Endpoint interceptor | Bao quanh handler sau mapping | `MessageContext` và `WebServiceMessage` |
| JAXB/OXM adapter | Chuyển payload XML ↔ Java | Object model từ XSD |
| Business service | Nghiệp vụ | DTO/domain model đã được kiểm soát |
| Client interceptor | Phía `WebServiceTemplate` | Request/response SOAP khi marshal/gửi/nhận |

Một filter đọc raw request body để log có thể tiêu thụ `ServletInputStream` trước khi Spring-WS parser nhận nó. Một `EndpointInterceptor` đọc `SoapMessage` đã parse vẫn có thể gây buffering, serialization hoặc đọc attachments. **Không có tầng nào mặc nhiên an toàn để log toàn bộ payload.**

## 3. Streaming: không phải mọi message đều được đọc nhiều lần

### 3.1. Khái niệm streaming

**Streaming** nghĩa là có thể xử lý dữ liệu tuần tự mà không bắt buộc giữ nguyên toàn bộ nội dung trong bộ nhớ tại cùng thời điểm. Với SOAP, cần phân biệt:

- HTTP request/response stream từ transport.
- XML parser/serializer (SAX, StAX, DOM hoặc cấu trúc trung gian).
- SOAP message implementation, có thể xây mô hình đầy đủ hoặc xử lý theo nhu cầu.
- MIME attachments/MTOM, có thể đi theo stream, spool ra file hoặc được giữ trong RAM.
- Các interceptor/adapter yêu cầu biến toàn bộ message thành XML string, DOM hay byte array.

Không nên khẳng định “dùng `Source` = có streaming” hoặc “bật MTOM = zero-copy”. `Source` chỉ là một abstraction JAXP; `DOMSource` đã có cây DOM, còn `StreamSource` có thể dựa trên một stream chỉ đọc được một lượt. Kết quả còn phụ thuộc SOAP message factory và đường xử lý cụ thể.

### 3.2. Anti-pattern: serialize toàn bộ message chỉ để debug

Đây là ví dụ **không nên triển khai** trên production:

~~~java
// Ví dụ nguy hiểm: chỉ để cho thấy điều không nên làm.
ByteArrayOutputStream buffer = new ByteArrayOutputStream();
messageContext.getRequest().writeTo(buffer);
String xml = buffer.toString(StandardCharsets.UTF_8);
logger.info("SOAP request: {}", xml);
~~~

Rủi ro:

1. `writeTo(...)` có thể buộc message được serialize hoặc materialize toàn bộ.
2. `ByteArrayOutputStream` giữ thêm bản sao byte trong heap; chuyển sang `String` tạo một bản khác, đôi khi lớn hơn nhiều.
3. Với SOAP có attachment, thao tác serialize có thể làm thay đổi hành vi đọc/tạo MIME part hoặc tốn I/O; khả năng gọi lại phụ thuộc implementation.
4. Toàn bộ token, chữ ký, dữ liệu cá nhân và XML nhạy cảm bị đưa vào log.
5. Nếu request rất lớn, nguy cơ memory pressure, garbage collection và hết heap tăng mạnh.

Ngay cả khi message factory có thể serialize lặp lại, **chi phí vẫn tồn tại**. Nếu stream/attachment chỉ đọc một lần, thao tác debug có thể làm endpoint hoặc client nhận message không còn đầy đủ.

### 3.3. Một bảng quyết định

| Hành vi interceptor | Có khả năng phá streaming? | Có thể làm lộ thông tin? |
|---|---|---|
| Ghi một tên operation cố định, outcome và thời gian xử lý | Thấp, nếu không đọc payload | Thấp hơn, vẫn phải giới hạn metadata |
| Đọc payload như DOM toàn bộ | Có thể materialize toàn bộ XML | Có nếu log/giữ cây lâu |
| Gọi `writeTo(ByteArrayOutputStream)` | Có thể tăng memory/serialization I/O đáng kể | Rất cao nếu ghi buffer |
| Tính hash qua raw SOAP payload | Có thể cần đọc mọi byte hoặc buffer | Có thể lộ fingerprint/correlation, tùy mục đích |
| Thử đọc MIME attachment để xác định loại file | Có thể tiêu thụ stream, spool thêm file | Có nếu log tên file, MIME parts |
| Thêm header mới không liên quan chữ ký | Có thể yêu cầu mutate SOAP model | Có rủi ro integrity/policy nếu không thỏa thuận |
| Đọc HTTP content length (nếu có) qua transport đáng tin cậy | Thường không đọc body | Có thể ghi nhận metadata, nhưng length không phải kích thước decoded |

**Bài học:** chỉ thu thập metadata thực sự cần thiết. Khi phải đọc payload để validation/security, hãy dùng thành phần chuyên dụng và kiểm tra chính xác cơ chế parsing/streaming.

## 4. Interceptor và bộ nhớ: vì sao đọc một lần có thể trở thành copy nhiều lần?

Giả sử một SOAP request có 20 MiB XML đã mã hóa Base64. Trên wire, Base64 có overhead xấp xỉ 33% so với byte gốc, chưa tính cấu trúc XML. Khi log raw payload:

~~~text
HTTP/MIME bytes
      ↓
SOAP parser/model
      ↓
serialization into byte[]
      ↓
String for logger
      ↓
async logging queue / log encoder
      ↓
log storage / indexing
~~~

Có thể tồn tại nhiều bản dữ liệu đồng thời. Với Java `String`, kích thước thực phụ thuộc ký tự/JVM; không nên dùng một hệ số cứng để tuyên bố memory. Nhưng về nguyên lý, **bản sao dữ liệu lớn được tạo ở nhiều tầng** và số lượng request đồng thời làm tác động tăng lên.

### 4.1. Bài toán người vận hành hay bỏ sót

Ví dụ một server nhận 100 request đồng thời, mỗi request mang tài liệu nhị phân lớn. Nếu interceptor lưu cả body để so sánh request/response hoặc để log lỗi, tải memory có thể tăng đột biến ngay cả khi business service chỉ cần đọc một trường.

Cần xác minh:

- Tỷ lệ peak concurrent requests và kích thước p95/p99 payload.
- Heap/direct memory/spool files và giới hạn disk.
- Multipart limits, số MIME parts, kích thước decoded Base64.
- Số lần XML bị parse/serialize/canonicalize khi WS-Security và validation chạy.
- Logging queue/backpressure; một logger async không xóa chi phí tạo string ban đầu.
- GC pauses, memory allocation rate, request latency và thời gian giữ stream.

Các giá trị định lượng phụ thuộc implementation và workload; hãy benchmark **đường xử lý thật** thay vì gắn nhãn “streaming” dựa trên một class name.

## 5. MTOM/XOP: attachment có thể mất lợi ích streaming do interceptor

### 5.1. Base64 inline và MTOM khác nhau trên wire

Trong XSD contract-first, một phần tử nhị phân thường được khai báo:

~~~xml
<xs:element name="signedDocument"
            type="xs:base64Binary"
            minOccurs="0"
            xmlns:xs="http://www.w3.org/2001/XMLSchema"/>
~~~

Nếu gửi inline, XML Body có thể mang Base64 text. Nếu hai phía hỗ trợ **MTOM/XOP**, dữ liệu nhị phân có thể được đóng gói trong các MIME parts và SOAP XML tham chiếu bằng `xop:Include`:

~~~xml
<d:signedDocument
    xmlns:d="urn:example:documents:v1"
    xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <xop:Include href="cid:attachment-001@example.test"/>
</d:signedDocument>
~~~

Đây là **mảnh XML của một SOAP package tối ưu hóa MTOM**, không phải SOAP request hoàn chỉnh để gửi độc lập với `Content-Type: text/xml`. Transport thực có MIME boundary, root part và binary parts tương ứng.

Một interceptor làm những điều sau có thể ảnh hưởng MTOM:

- Gọi phương thức ghi/serialize toàn bộ message thành byte array để quan sát.
- Thao tác XML như chuỗi, thay thế `xop:Include` mà không hiểu MIME package.
- Đọc `DataHandler` hoặc attachment `InputStream` nhằm tính hash rồi **không thể đọc lại**.
- Sao chép SOAP message nhưng quên MIME attachments hoặc Content-ID.
- Đụng `Content-Type`/boundary theo cách không phù hợp với message factory.

`DataHandler` hoặc `byte[]` ở JAXB model cũng chưa bảo đảm streaming end-to-end. Runtime có thể materialize nội dung trong quá trình marshalling, signing, encrypting, validating hoặc logging.

### 5.2. Checklist cho interceptor gặp binary

| Hạng mục | Câu hỏi kiểm chứng |
|---|---|
| Byte gốc | Byte sau nhận có đúng byte trước gửi? So checksum trong test |
| MIME | Các part, Content-ID, Content-Type và boundary còn hợp lệ? |
| MTOM optimization | Binary vẫn đi attachment hay bị inline toàn bộ? Việc đó có được contract/policy cho phép? |
| Streaming | Peak memory không tăng tuyến tính theo kích thước attachments chỉ vì interceptor? |
| Cleanup | Temporary files/streams được đóng, xóa và xử lý lỗi đúng? |
| Security | Chữ ký, mã hóa và profile bảo vệ attachments có còn đúng? |
| Giới hạn | Server có ngăn requests vượt quota khi raw XML nhỏ nhưng attachment lớn? |

Không nên log tên file do caller cung cấp mà không lọc: tên file có thể chứa dữ liệu cá nhân, chuỗi điều khiển, newline hoặc thông tin nhạy cảm. Nếu cần observability, lưu **kích thước theo nhóm**, số part và kết quả kiểm tra an toàn, không lưu nội dung.

### 5.3. Ví dụ tích hợp hợp đồng SOAP

Giả sử endpoint nhận:

~~~xml
<d:UploadDocumentRequest xmlns:d="urn:example:documents:v1">
  <d:documentId>DOC-1001</d:documentId>
  <d:content>...</d:content>
</d:UploadDocumentRequest>
~~~

Trên wire, phần `content` có thể được biểu diễn inline Base64 hoặc tối ưu thành MTOM package nếu binding và stack hỗ trợ. Interceptor muốn kiểm tra `documentId` không nhất thiết cần đọc `content`. Nếu `content` lớn, cách ít tác động hơn là:

1. Cấu hình XSD validation, authentication, authorization và limits theo policy.
2. Chỉ lấy metadata đã được hệ thống **cho phép** đo/truy vết.
3. Giao việc kiểm tra bytes/file type/hash cho một thành phần được thiết kế để xử lý stream, có giới hạn và cleanup.
4. Thử trực tiếp với request MTOM thật, không dùng test XML string nhỏ làm bằng chứng.

## 6. XML Signature: tính toàn vẹn phụ thuộc nội dung được ký

### 6.1. Chữ ký XML không phải chỉ là một header trang trí

WS-Security có thể dùng **XML Signature** để ký SOAP Body, một số SOAP Header và các reference theo security policy. Chữ ký chứa thông tin như `SignedInfo`, `Reference URI`, digest, transform/canonicalization, algorithm và `SignatureValue`.

Mảnh SOAP Header minh họa — **không phải chữ ký hợp lệ để sử dụng**:

~~~xml
<wsse:Security
    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
  <ds:Signature>
    <ds:SignedInfo>
      <!-- Canonicalization, SignatureMethod và các Reference -->
    </ds:SignedInfo>
    <!-- SignatureValue và KeyInfo -->
  </ds:Signature>
</wsse:Security>
~~~

Đây chỉ là khung cấu trúc: chữ ký thực phải có đầy đủ `SignedInfo`, `SignatureValue` và tham chiếu phù hợp, được tạo/xác minh bởi **thư viện WS-Security/XML Signature** đã được cấu hình, không phải XML thủ công.

### 6.2. Interceptor có thể phá chữ ký bằng cách nào?

Một SOAP interceptor có thể:

- Thêm/bớt element hoặc attribute bên trong **phần dữ liệu được ký**.
- Đổi namespace declarations, prefix hoặc whitespace có ý nghĩa với canonicalization/transform cụ thể.
- Tái serialize message theo cách làm biến đổi biểu diễn mà reference digest đang bảo vệ.
- Đổi `wsu:Id`, `Id` hoặc các reference identifiers được dùng để xác định phần tử đã ký.
- Xóa `wsse:Security`, `ds:Signature` hoặc SOAP Header được ký.
- Chạm attachment được ký, làm thay byte hoặc cách reference tới MIME part.
- Di chuyển phần tử giữa các vị trí mà việc xác minh reference/ID không còn nhận đúng.

Hậu quả thường là **digest mismatch** hoặc không xác minh được Signature, nhưng không phải **mọi** khác biệt text/XML đều chắc chắn phá chữ ký. XML Signature dùng canonicalization và transforms để chuẩn hóa theo quy tắc cụ thể; những thay đổi ngoài phạm vi reference hoặc bị transform loại trừ có thể không ảnh hưởng digest. **Cần kiểm tra policy, reference list và canonicalization thực tế**.

### 6.3. “Log rồi serialize lại nguyên XML” không bảo đảm vô hại

Giả sử interceptor nhận XML đã ký, đọc thành DOM, normalize whitespace rồi serialize lại. Ngay cả khi người phát triển “không sửa giá trị nghiệp vụ”, một số node/namespace/whitespace được ký có thể thay đổi.

Ví dụ minh họa:

~~~xml
<ord:amount xmlns:ord="urn:example:orders:v1">100.00</ord:amount>
~~~

Không thể tùy ý biến thành:

~~~xml
<ord:amount xmlns:ord="urn:example:orders:v1">100</ord:amount>
~~~

rồi lập luận đây là “cùng giá trị decimal”. Về mặt XSD, chúng có thể biểu diễn cùng số học; về mặt XML Signature, thay text node có thể làm sai digest. Tương tự, đổi `dateTime` từ `+07:00` sang `Z` có thể giữ instant nhưng **đổi byte ký**.

**Đây là khác biệt giữa semantic equality của business data và integrity của XML đã ký.** Một adapter JAXB, normalization interceptor hay “XML sanitizer” phải được đặt vào đúng giai đoạn và không được tùy ý rewrite message sau khi ký.

### 6.4. Canonicalization không cho phép chỉnh XML tùy tiện

Canonical XML chuẩn hóa những khía cạnh được specification định nghĩa; nó **không** “miễn nhiễm mọi thay đổi DOM”. Ví dụ:

- Sửa text trong node được reference thường đổi digest.
- Thêm child element vào Body được ký có thể đổi digest.
- Thay namespace context có thể có ảnh hưởng khác nhau tùy inclusive/exclusive canonicalization và nội dung reference.
- Thay đổi thứ tự siblings thường thay thứ tự canonical representation.
- Thêm một header **ngoài** tập được ký có thể không đổi digest Body, nhưng vẫn có thể vi phạm WS-SecurityPolicy hoặc làm hỏng xử lý nghiệp vụ.

Không viết một “interceptor sửa XML sau verify” như biện pháp xử lý chung. Nếu có nhu cầu biến đổi message, hãy xác định **message state** (chưa ký, đã ký, đã mã hóa, đã verify, đã decrypt) và policy trước khi cho phép biến đổi.

## 7. WS-Security: thứ tự security, validation và logging quan trọng

### 7.1. Xác minh chữ ký khác việc đọc một header

Một SOAP Header có `wsse:Security` không chứng minh message an toàn. Trường `UsernameToken`, certificate reference và `SignatureValue` do bên gửi cung cấp phải được **xác minh** bằng WSS4J/WS-Security stack theo key/trust policy trước khi được coi là đáng tin.

Trong Spring-WS, thư viện WSS4J và các security interceptors có thể xử lý:

- Chữ ký: xác minh integrity của các parts được tham chiếu, thuật toán, key material.
- Encryption: giải mã phần tử/attachment theo profile.
- Timestamp: kiểm tra hạn dùng và tolerance, có thể cần chống replay.
- Token: kiểm tra danh tính/chứng chỉ/trust policy.
- Chữ ký trên một số Header/Body và cách security elements được canonicalize.

Tuy nhiên, **không có một thứ tự “verify → decrypt → validate” đúng cho mọi WS-SecurityPolicy**. Tùy ký trước mã hóa hay mã hóa trước ký, message parts và policy, các bước có thể khác. Hãy để security stack thực hiện theo **policy chính xác**, không tự giải mã rồi xác minh bằng XPath hoặc tự tái cấu trúc SOAP.

### 7.2. Câu hỏi cần trả lời khi đặt interceptor

| Interceptor/chức năng | Cần xác định rõ |
|---|---|
| Authentication/WS-Security | Lúc nào message được coi là đã xác minh? Phần nào được ký/mã hóa? |
| Schema validation | Đang validate XML đã decrypt chưa? Schema có biết kiểu payload không? |
| Logging/tracing | Có đang đọc **plaintext** trước khi auth? Có lọc PII và token? |
| XML transformation | Có sửa node nằm trong signed references? Biến đổi trước hay sau sign? |
| Business authorization | Caller đã được xác thực và có quyền truy cập resource cụ thể chưa? |
| Error handling | Lỗi signature/certificate có bị ghi raw payload hoặc tạo Fault lộ bí mật không? |

Một cấu hình dễ sai là gắn interceptor log toàn bộ SOAP request **trước security validation**. Nó không chỉ làm lộ payload nhạy cảm; nó còn có thể tạo một **log injection** từ dữ liệu chưa xác thực.

### 7.3. Không biến thứ tự danh sách thành giả định an ninh

`WsConfigurer#addInterceptors(...)` đăng ký nhiều interceptor. Thứ tự request/response/fault callbacks có thể ảnh hưởng thực thi, nhưng **thứ tự gọi thực tế phải được kiểm thử theo phiên bản/config đang dùng**, bao gồm các đường exception.

Ví dụ cấu hình thuần ý tưởng:

~~~java
@Override
public void addInterceptors(
        List<EndpointInterceptor> interceptors) {
    interceptors.add(securityInterceptor);
    interceptors.add(schemaValidator);
    interceptors.add(metadataAuditInterceptor);
}
~~~

`securityInterceptor`, `schemaValidator` và `metadataAuditInterceptor` ở đây là các bean giả định. Đoạn code **không xác nhận** đây là thứ tự tối ưu cho mọi WS-SecurityPolicy, bởi một số interceptor có thể cần thông tin trước/sau giải mã hoặc chỉ được áp dụng trên endpoint mapping cụ thể. Đặc biệt, response security (ký/mã hóa) và response validation có thể cần thứ tự khác đường request.

**Quy tắc vận hành:** với một bộ request chuẩn và lỗi (đúng/sai signature, thiếu token, sai XSD, endpoint khác), đo callback nào chạy và dữ liệu nào có thể bị đọc trong mỗi trạng thái.

## 8. Dữ liệu nhạy cảm có thể rò rỉ tại nhiều vị trí

Thông điệp SOAP doanh nghiệp thường chứa dữ liệu thuộc phạm vi bảo vệ:

- `UsernameToken`, password digest, token xác thực và session identifiers.
- Thông tin khách hàng, số tài khoản, chứng từ, mã số thuế, địa chỉ, số điện thoại.
- Nội dung tài liệu nhị phân, chữ ký số và certificate identifiers.
- Metadata nghiệp vụ được phép chia sẻ với đối tác nhưng **không** được ghi vào log tập trung.
- Một số giá trị request ID hoặc correlation ID cũng có thể định danh người dùng hoặc tiết lộ quan hệ giao dịch.

Đường rò rỉ không chỉ là `logger.info(...)`. Dữ liệu có thể đi vào:

~~~mermaid
flowchart TB
  SOAP["SOAP Body + Header + attachments"]
  SOAP --> A["Interceptor log hoặc trace"]
  SOAP --> B["Exception message / stack trace"]
  SOAP --> C["Metrics label / tracing attributes"]
  SOAP --> D["APM auto-instrumentation"]
  SOAP --> E["Async log queue"]
  SOAP --> F["Support dumps / debug artifacts"]
  A --> G["Log aggregation / SIEM"]
  B --> G
  C --> G
  D --> G
  E --> G
  F --> G
~~~

Các hệ thống lưu log/trace có thể có thời gian lưu lâu hơn dữ liệu giao dịch gốc và nhiều người truy cập hơn. Vì vậy phải áp dụng chính sách **data minimization** tại nguồn, thay vì hy vọng redaction ở downstream luôn chính xác.

### 8.1. Bảng quyết định ghi log

| Dữ liệu | Khuyến nghị |
|---|---|
| Tên operation đã được định nghĩa/allowlist, trạng thái thành công/Fault | Có thể ghi sau khi cân nhắc mức nhạy cảm |
| Thời gian xử lý, payload size range, số attachment | Có thể ghi nếu giới hạn cardinality và không lộ nghiệp vụ |
| Correlation ID do gateway đáng tin tạo | Có thể ghi nếu không chứa PII/token; vẫn cần giới hạn và sanitize |
| Raw SOAP Header | Không log mặc định; có thể chứa WS-Security |
| Raw SOAP Body | Không log mặc định; dữ liệu nghiệp vụ và PII |
| Base64/MTOM binary bytes | Không ghi log |
| Full certificate, private key, shared secret | Không ghi; chỉ metadata đã được policy cho phép |
| Exception message từ XML parser/client input | Không đưa nguyên xi vào log/metrics không kiểm soát |
| Hash của payload hoặc tên file | Chỉ sau đánh giá privacy/threat model; hash vẫn có thể là fingerprint nhạy cảm |

### 8.2. “Chỉ che thẻ password” chưa đủ

Một bộ lọc dựa trên chuỗi:

~~~text
replace("<Password>...</Password>", "<Password>***</Password>")
~~~

dễ bị bỏ qua bởi XML prefix, namespace, chữ hoa/thường, thay đổi thứ tự attributes, line breaks, CDATA, SOAP faults hoặc binary parts. Thậm chí một field `notes` cũng có thể chứa token/mật khẩu không theo cấu trúc dự kiến.

Các lựa chọn tốt hơn:

1. **Không ghi payload ngay từ đầu** đối với log vận hành mặc định.
2. Khi cần audit giá trị nghiệp vụ, trích **những field nằm trong allowlist** sau validation và authorization rồi áp dụng masking/hashing theo chính sách.
3. Audit event nên có schema riêng, ví dụ `operationCode`, `resultCode`, `durationMs`, `trustedTraceId`, **không** nhận một SOAP XML string.
4. Nếu cần packet capture phục vụ sự cố, sử dụng quy trình kiểm soát riêng: xác nhận mục đích, giới hạn thời gian, mã hóa lưu trữ, kiểm soát quyền, TTL/xóa và phê duyệt phù hợp.
5. Test redaction với prefix khác, default namespace, nested elements, XML comments, SOAP faults và attachments.

Không gắn raw request/response làm exception detail chỉ để dễ debug; SOAP Fault cũng là một kênh đưa dữ liệu nội bộ ra bên ngoài.

## 9. Ví dụ Spring-WS: interceptor audit chỉ ghi metadata

Một thiết kế tốt cho bài toán tracing là **không truy cập SOAP Body/attachments nếu không cần**. Ví dụ dưới đây ghi kết quả và thời gian xử lý của endpoint, không gọi `writeTo(...)`, không chuyển `Source` thành chuỗi và không đụng `wsse:Security`.

### 9.1. Implement EndpointInterceptor

~~~java
package com.example.orders.audit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public final class SafeSoapAuditInterceptor
        implements EndpointInterceptor {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeSoapAuditInterceptor.class);

    private static final String START =
            SafeSoapAuditInterceptor.class.getName() + ".start";
    private static final String OUTCOME =
            SafeSoapAuditInterceptor.class.getName() + ".outcome";

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        context.setProperty(START, System.nanoTime());
        context.setProperty(OUTCOME, "not_completed");
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        context.setProperty(OUTCOME, "response");
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        context.setProperty(OUTCOME, "soap_fault");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint, Exception ex) {
        Object startValue = context.getProperty(START);
        long durationMs = -1;

        if (startValue instanceof Long startNanos) {
            durationMs =
                    (System.nanoTime() - startNanos) / 1_000_000L;
        }

        Object statusValue = context.getProperty(OUTCOME);
        String status = statusValue instanceof String s
                ? s : "unknown";

        if (ex != null) {
            status = "exception";
        }

        // "orders" là mã operation nhóm do server định nghĩa sẵn.
        // Không đặt payload, token, certificate hay user input vào log.
        LOG.info("soap_audit group={} outcome={} duration_ms={}",
                "orders", status, durationMs);
    }
}
~~~

**Những tính chất được thiết kế:**

- `MessageContext` giữ metadata của **một lượt xử lý**; không lưu request-specific state trong instance field của interceptor singleton.
- `System.nanoTime()` là đồng hồ đơn điệu hữu ích đo elapsed time trong cùng JVM, không dùng làm timestamp nghiệp vụ.
- `group` là **giá trị cố định từ server**, không phải `invoiceId`, SOAPAction hay URI bất kỳ do client gửi.
- `handleResponse` và `handleFault` ghi outcome khác nhau; `afterCompletion` là nơi xuất audit event một lần trong đường callback được framework hoàn tất.
- Mọi đường lỗi **trước interceptor** (parser, transport, authentication ở tầng khác) cần observability ở lớp phù hợp; không tuyên bố event này bao phủ 100% requests.
- Chưa xác nhận authentication ở đây; log không có trường `authenticated=true` chỉ vì request đã tới method.
- Không nên dùng duration label có cardinality lớn trong metrics; histogram bucket và operation enum là lựa chọn kiểm soát tốt hơn.

`afterCompletion` được gọi theo lifecycle của interceptor đã tham gia xử lý; với một interceptor trước đó chặn request, hoặc lỗi ở tầng chưa vào chain, audit này có thể không chạy. Cần kiểm tra chính xác behavior qua integration tests, không xem đoạn code là “audit toàn hệ thống” không thể bỏ sót.

### 9.2. Đăng ký qua WsConfigurer

~~~java
package com.example.orders.audit;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@Configuration
@EnableWs
public class SoapInterceptorsConfig implements WsConfigurer {

    @Bean
    public SafeSoapAuditInterceptor safeSoapAuditInterceptor() {
        return new SafeSoapAuditInterceptor();
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(safeSoapAuditInterceptor());
    }
}
~~~

Ví dụ là **một phương án cấu hình** trong application context. Nếu dự án đã có `@EnableWs`, hãy tích hợp `WsConfigurer` vào cấu hình chủ quản, tránh đăng ký trùng infrastructure. Nếu có WS-Security hoặc schema validator, phải kiểm chứng **order và scope** của chúng với audit interceptor, không tự mặc định đoạn code này đang nằm sau bước xác thực.

### 9.3. Khi cần nhiều operation codes

Không gắn trực tiếp giá trị XML tự do vào log label. Một số cách:

- Map endpoint method/class đã được server đăng ký sang **operation code allowlist** như `GET_ORDER`, `CANCEL_ORDER`.
- Gắn operation code vào context qua infrastructure đáng tin cậy và không lấy từ SOAP payload chưa xác thực.
- Dùng nhãn `UNKNOWN` khi chưa xác định được endpoint, tránh log raw action URI.
- Giữ cardinality thấp: service, operation, outcome, bounded duration bucket.
- Nếu audit bắt buộc một request ID, chỉ dùng ID **đã được chuẩn hóa/xác thực theo trust boundary**, đặt giới hạn ký tự/độ dài, bảo vệ nó như dữ liệu có thể liên kết giao dịch.

## 10. Anti-pattern và mẫu thay thế

| Anti-pattern | Vì sao nguy hiểm | Phương án thay thế |
|---|---|---|
| Ghi `message.writeTo(buffer)` trong `handleRequest` | Buffer toàn bộ request, lộ SOAP Body/Header/attachments | Log event đã được định nghĩa, không serialize payload |
| Lấy `payloadSource` → chuỗi rồi parse lại | Tăng I/O/memory, có thể tiêu thụ stream hoặc khác canonicalization | Đọc tối thiểu qua API phù hợp, không tạo XML copy khi không cần |
| Sửa `wsu:Id` hoặc namespace của SOAP Body sau khi ký | Có thể phá digest/reference resolution | Không mutate signed parts; dùng security stack theo policy |
| Thêm SOAP Header tùy ý sau bước ký | Có thể vi phạm policy, làm hỏng signature nếu header được ký | Thêm header ở vị trí đã thiết kế trước signing |
| Redact bằng regex trên raw SOAP string | Dễ lọt PII qua prefix, CDATA, nested XML và MIME | Không log payload; allowlist structured audit |
| Log mọi `SoapFault` detail | Detail có thể chứa giá trị user gửi hoặc hệ thống nội bộ | Log fault category/code đã kiểm soát |
| Lấy toàn bộ attachment vào `byte[]` để “quét nhanh” | Tăng heap và mất streaming, nguy cơ OOM | Stream scanning có limits/quarantine, kiểm thử I/O |
| Thêm WS-Security interceptor nhưng không kiểm chứng thứ tự | Message có thể được dùng trước verify hoặc response chưa ký đúng | Test negative signatures, token expiry, policy thực |
| Tắt XSD validation để giảm overhead | Có thể đẩy XML sai vào business service | Đo hiệu năng, cache compiled schema, tối ưu contract có giới hạn |
| Đặt logger DEBUG bật dài ngày ở production | Rò rỉ/retention payload, chi phí vận hành | Sampling an toàn, mức metadata, thời gian bật có kiểm soát |

### 10.1. XML transformation: trước hay sau khi ký?

Nếu có nghiệp vụ cần chuẩn hóa SOAP request — chẳng hạn chuyển một trường legacy sang dạng mới — cách làm an toàn **không phải** chỉnh sửa message ở vị trí bất kỳ.

Một phương án kiến trúc rõ ràng hơn:

1. Giữ nguyên SOAP message theo hợp đồng đã ký và xác minh nó theo policy tương ứng.
2. Sau khi xác minh, chuyển **dữ liệu đã tin cậy** sang domain DTO/command ở lớp nghiệp vụ mà không tự thay signed XML trên wire.
3. Nếu phía server phải tạo response theo format mới, build JAXB/DOM response theo XSD, áp dụng security signing/encryption tại chặng phù hợp theo policy.
4. Nếu thật sự phải thay đổi SOAP Body trước/sau security, mô tả rõ trust boundary, signatures, reference scope và kiểm thử đầu cuối với đối tác.

Chuyển đổi ở **domain layer** thường ít rủi ro hơn interceptor thao tác trực tiếp với XML đã được ký. Trong một số tích hợp gateway có chức năng transform-and-resign, đó phải là một dịch vụ tin cậy có key/trust policy và audit độc lập; không coi nó là một interceptor log đơn giản.

## 11. Kết hợp validation, marshalling và data classification

### 11.1. Schema validation có thể tăng chi phí xử lý

`PayloadValidatingInterceptor` kiểm tra payload theo XSD, ví dụ constraint `xs:pattern`, `xs:sequence`, kiểu ngày giờ, decimal và các namespace nhập qua `xs:import`. Đây là kiểm tra hữu ích nhưng cần biết:

- XML phải được đọc/kiểm tra bởi validator; chi phí phụ thuộc kích thước và độ phức tạp schema.
- Nếu phía sau JAXB unmarshalling hoặc business layer lại parse toàn bộ XML, có thể có overhead lặp lại.
- Một số kiểu schema/regex và payload có thể tạo chi phí cao; cần giới hạn resource và kiểm thử biên.
- XSD validation **không** chứng minh chữ ký hợp lệ, không phát hiện mã độc trong binary, không xác nhận quyền truy cập.
- Nếu schema nhập từ URL ngoài, policy resolution phải tránh XXE/SSRF và dependency network không tin cậy.

Đừng bỏ validation chỉ vì lo performance mà chưa đo; hãy compile schema đúng, cấu hình một lần theo lifecycle thích hợp và chọn message factory/adapter phù hợp sau benchmark.

### 11.2. JAXB/OXM và chữ ký

Khi `@RequestPayload` được JAXB unmarshal thành object:

- Java object có thể mất cách biểu diễn lexical ban đầu của XML (ví dụ `125.00` so với `125`; timezone representation).
- Marshal lại object ra XML có thể tạo prefix, whitespace hoặc thứ tự namespace declarations khác.
- Không nên coi “round trip JAXB tạo object tương đương” là bằng chứng rằng XML Signature trên original SOAP Body còn hợp lệ sau reserialization.
- Đặc biệt với `xs:base64Binary`, inline Base64 và MTOM/XOP representation cần được xử lý bởi security stack đúng profile.

**Đúng XSD ≠ cùng bytes/chữ ký.** Validation, marshalling và signature verification là các kiểm tra khác nhau với những khái niệm tính đúng khác nhau.

### 11.3. Gắn nhãn dữ liệu trước khi quyết định log

Một bảng phân loại đơn giản trong thiết kế SOAP:

| Loại dữ liệu | Ví dụ | Chính sách mặc định |
|---|---|---|
| Public contract metadata | Tên operation allowlist, SOAP version | Có thể ghi ở mức tối thiểu |
| Internal operational metadata | Latency, outcome, server-generated trace ID | Có thể ghi với retention và quyền truy cập giới hạn |
| Business-sensitive | Order ID, invoice ID, giá, trạng thái thanh toán | Không log theo mặc định; chỉ theo audit policy |
| Personal/sensitive | Họ tên, số định danh, thông tin sức khỏe, nội dung chứng từ | Không log |
| Secret/security material | Token, password, private key, session cookie, raw signature input | Không log |
| Binary content | PDF, XML attachment, Base64 body | Không log; xử lý qua dịch vụ chuyên trách |

Một mã `orderId` có thể là thông tin nghiệp vụ nhạy cảm; đừng coi nó “vô hại” chỉ vì không chứa tên người. Ngay cả `traceId` do caller cung cấp cũng có thể bị lợi dụng để chèn ký tự xuống dòng hoặc khiến metrics có cardinality không kiểm soát.

## 12. SOAP Fault và response logging không được tiết lộ chi tiết

Không phải mọi exception đều nên biến thành SOAP Fault giống nhau.

| Lỗi | Nơi có thể phát sinh | Cần bảo đảm |
|---|---|---|
| XML không well-formed | Parser/message factory | Không echo raw XML, giới hạn resource |
| Request không khớp `@PayloadRoot` | Dispatcher/mapping | Fault hoặc HTTP error phù hợp, không lộ endpoint nội bộ |
| Vi phạm XSD | Validation interceptor | SOAP fault code/detail theo contract, không dump toàn bộ input |
| Sai chữ ký hoặc cert | Security interceptor | Không tiết lộ private key/truststore nội bộ hay raw token |
| Authorization thất bại | Business security | Không tiết lộ nội dung tài nguyên bị từ chối |
| Không marshal được response | Adapter/serializer | Không gửi exception/stack trace Java thô |
| Kết nối client bị gián đoạn | Transport | Không coi là SOAP Fault từ endpoint nếu chưa tạo được response |

Spring-WS có các `EndpointExceptionResolver` và SOAP Fault mapping facilities; một số lỗi xảy ra trước khi chúng được gọi. Với logging interceptor, **`handleFault` chỉ chạy cho những đường có SOAP Fault mà chain xử lý nhìn thấy**; nó không đủ để ghi nhận mọi lỗi handshake TLS hoặc request bị chặn tại proxy.

Một SOAP Fault có thể chứa `faultstring`/`Reason`/`Detail`; những trường này không được tự động copy nguyên vào log hay metrics label. Nên chuẩn hóa thành **fault category/operation code** được định nghĩa trước và giữ nội dung chi tiết ở tầng xử lý có quyền.

## 13. ClientInterceptor: cùng rủi ro ở phía gửi và nhận SOAP

`WebServiceTemplate` có `ClientInterceptor`; nó có thể bổ sung tracing/security nhưng cũng có thể làm hỏng thông điệp:

- **Request:** sau khi JAXB marshal, interceptor có thể được gọi trước HTTP transport; đọc/serialize toàn bộ request có thể buffer Body và attachments.
- **Signature outbound:** nếu message đã được ký, một interceptor phía sau sửa phần đã ký có thể làm signature không còn hợp lệ.
- **Response inbound:** nếu một interceptor ghi raw response trước khi validation/security, nó có thể để lộ thông tin đối tác gửi và dữ liệu chưa đáng tin cậy.
- **Fault:** fault detail có thể chứa chuỗi do đối tác hoặc attacker kiểm soát; không tự copy vào log.
- **Retry:** mỗi attempt có thể tạo thêm bản log chứa cùng dữ liệu và tăng nguy cơ rò rỉ; SOAP operation có side effects cần xử lý idempotency.

| Khía cạnh | Server EndpointInterceptor | ClientInterceptor |
|---|---|---|
| Điểm tích hợp | `MessageDispatcher` quanh endpoint | `WebServiceTemplate` |
| Request | Từ caller gửi vào | Từ hệ thống của mình gửi đi |
| Response/Fault | Từ server trả đi | Từ đối tác trả về |
| Rủi ro khi log XML | Lộ dữ liệu caller, buffering | Lộ dữ liệu cả hai phía, buffering |
| Rủi ro ký số | Sửa signed Body/Header inbound/outbound | Sửa request sau sign hoặc response trước/ sau verify |
| Lỗi nằm ngoài callback | Proxy, TLS, parser sớm | DNS, TCP/TLS handshake, timeout |

**Không sao chép một interceptor server sang client chỉ vì tên callback giống nhau.** Các interface có tham số khác nhau, và thứ tự/security profile phải được thử với `WebServiceTemplate` thực tế.

### 13.1. Định nghĩa rõ per-attempt observability

Một attempt log có thể chứa:

~~~text
service=orders
operation=GET_ORDER
attempt=2
outcome=timeout
duration_ms=1200
~~~

Đây là các **label giới hạn**. Nếu có trace ID, nên do hạ tầng tin cậy tạo, kiểm tra đầu vào và áp dụng retention policy. Không đặt `orderId`, `invoiceId`, SOAPAction tùy ý hoặc exception message làm metric labels.

## 14. Kiểm thử interceptor không truy cập SOAP payload

### 14.1. Unit test ví dụ với Mockito

Với `SafeSoapAuditInterceptor` ở mục 9, có thể kiểm tra rằng interceptor chỉ gọi `MessageContext` để lưu metadata, không lấy `WebServiceMessage`:

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.springframework.ws.context.MessageContext;

class SafeSoapAuditInterceptorTest {
    private final SafeSoapAuditInterceptor interceptor =
            new SafeSoapAuditInterceptor();

    @Test
    void successAuditDoesNotAccessMessage() throws Exception {
        MessageContext context = mock(MessageContext.class);
        Object endpoint = new Object();

        interceptor.handleRequest(context, endpoint);
        interceptor.handleResponse(context, endpoint);
        interceptor.afterCompletion(context, endpoint, null);

        verify(context, never()).getRequest();
        verify(context, never()).getResponse();
    }

    @Test
    void faultAuditDoesNotAccessMessage() throws Exception {
        MessageContext context = mock(MessageContext.class);
        Object endpoint = new Object();

        interceptor.handleRequest(context, endpoint);
        interceptor.handleFault(context, endpoint);
        interceptor.afterCompletion(context, endpoint, null);

        verify(context, never()).getRequest();
        verify(context, never()).getResponse();
    }
}
~~~

Cần dependency JUnit/Mockito và Spring-WS ở test classpath. `mock(MessageContext.class)` trong test trên **không lưu thật properties** giữa `setProperty` và `getProperty`, nên ví dụ này chỉ chứng minh “không truy cập SOAP message”, không kiểm tra duration/outcome được ghi đúng. Muốn kiểm tra log values, dùng context test có lưu thuộc tính và một log appender kiểm soát.

Đồng thời, interceptor này không đọc Body **không có nghĩa cả stack** đang streaming: parser, validator, JAXB, WSS4J hoặc message factory vẫn có thể materialize payload.

### 14.2. Test không lộ dữ liệu vào log/trace

Dùng các chuỗi giả trong fixtures:

~~~text
SYNTHETIC_SECRET_DO_NOT_LOG_987
SYNTHETIC_CUSTOMER_00000000
SYNTHETIC_ATTACHMENT_CONTENT
~~~

Khi chạy test, capture những nơi được cấu hình thu thập logs/traces/metrics trong môi trường test, và kiểm tra:

1. Không xuất hiện ba chuỗi trên ở success, SOAP Fault hoặc exception.
2. Không xuất hiện raw `wsse:Security`, tokens hay Base64 attachments.
3. Không có full request/response XML string trong log.
4. Chỉ có field allowlist như operation code, result code, duration.
5. Test payload prefix khác, CDATA, XML whitespace, lỗi parsing và lỗi signature.
6. Test các nhánh lỗi trước/ngoài endpoint interceptor để bảo đảm logging ở tầng transport cũng không làm lộ dữ liệu.

Một logger **không đọc payload** giúp thiết kế dễ chứng minh an toàn hơn bộ regex mask XML không thể bao phủ mọi biến thể. Ngoài interceptor tự viết, phải kiểm tra APM auto-capture, proxy access logs và hệ thống exception logging.

### 14.3. Concurrent requests và state

Với interceptor singleton, không đặt `currentRequest`, `lastToken`, `ByteArrayOutputStream` hoặc mutable DOM vào instance fields. `MessageContext` là nơi thích hợp hơn cho state của một request **trong phạm vi interceptor lifecycle**, nhưng vẫn cần test:

- Kết quả response/Fault không bị gán nhầm request khác.
- Duration không lẫn giữa các lời gọi đồng thời.
- Khi xử lý lỗi sớm, có tuyến observability phù hợp dù callback không chạy.
- Log queue có backpressure, không giữ dữ liệu lớn lâu.
- Metadata label bounded cardinality và không mang giá trị do caller tùy ý đặt.

## 15. Ma trận kiểm thử chữ ký, MTOM và streaming

Không thể xác nhận security bằng cách tự đặt một thẻ `<ds:Signature>` giả vào SOAP. Phải tạo/xác minh chữ ký bằng stack thực, certificate/key **test** và profile được chốt.

| Kịch bản | Kết quả cần có |
|---|---|
| SOAP XML nhỏ, không ký | Audit chỉ ghi metadata; endpoint/response hoạt động |
| Request có signature hợp lệ | Security verify pass, vào endpoint sau khi policy đã được đáp ứng |
| Request bị đổi text node đã ký | Verify signature fail, business service không chạy |
| Request token sai/hết hạn | Bị từ chối, không log token |
| Request XSD sai nhưng signature đúng | Validation reject đúng profile, không echo XML nhạy cảm |
| Response cần chữ ký | Client xác minh response signature thành công |
| Response bị sửa sau ký | Client verify fail |
| MTOM attachment 10 KiB | MIME package hợp lệ, bytes không đổi |
| MTOM attachment lớn | Không OOM, không log binary, cleanup đúng |
| MTOM attachment bị thay bytes và có signature bảo vệ | Verify thất bại theo security profile |
| Multipart Content-ID hỏng | Bị từ chối có kiểm soát |
| Request vượt quota | Chặn ở transport/parser trước business layer |
| SOAP Fault có detail nhạy cảm | Không sao chép raw detail vào logs hoặc metrics |
| Chạy qua reverse proxy TLS | Security và endpoint URL hoạt động theo hợp đồng |

### 15.1. Kiểm tra attachment integrity

Test có thể so SHA-256 trên **byte gốc** và **byte được giải mã sau nhận**, thay vì so XML string hoặc MIME boundary.

~~~java
import java.security.MessageDigest;
import java.util.Arrays;

byte[] before = readFixtureBytes(); // Helper của test.
byte[] after = readReceivedBytes(); // Helper của test.

byte[] expected =
        MessageDigest.getInstance("SHA-256").digest(before);
byte[] actual =
        MessageDigest.getInstance("SHA-256").digest(after);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Attachment bytes changed");
}
~~~

Đây là đoạn minh họa, không phải chương trình Java độc lập; hai helper cần được dự án định nghĩa. Với file lớn, nên tính digest **theo stream** trong test để không nạp toàn bộ file. SHA-256 ở đây dùng để đối chiếu dữ liệu, **không** thay thế chữ ký WS-Security hay xác thực người gửi.

### 15.2. Đo memory, disk và throughput

Một benchmark hữu ích so sánh:

- Không có audit interceptor.
- Chỉ có metadata audit interceptor.
- Cấu hình thật: audit + schema validation + WS-Security.
- Cấu hình thật với MTOM attachments ở kích thước biên.
- Phương án unsafe logging **chỉ trên fixtures giả trong môi trường cô lập**, để đo overhead nếu cần chứng minh tác hại.

Đo peak heap, allocation rate, garbage collection, temporary disk, p95/p99 latency, throughput và lỗi. Thử nhiều kích thước payload và số lượng concurrent requests. Không khẳng định “streaming hiệu quả” bằng một lần gửi XML 2 KB.

## 16. Tình huống thực tế: interceptor “debug” làm hỏng SOAP upload đã ký

### 16.1. Bối cảnh

Một hệ thống trao đổi hóa đơn điện tử giữa bên bán và hệ thống lưu trữ đối tác:

- WSDL 1.1 document/literal, input `{urn:example:invoice:v1}SubmitInvoiceRequest`.
- XSD có `invoiceId`, `issuedAt`, `amount` và `document` kiểu `xs:base64Binary`.
- Client Java dùng JAXB/OXM và MTOM khi tài liệu lớn.
- WS-Security yêu cầu ký SOAP Body và Timestamp bằng certificate của bên gửi.
- Spring-WS server có WSS4J security interceptor, schema validation interceptor và endpoint lưu tài liệu.

Một developer thêm interceptor “debug”:

~~~java
// Chỉ dùng để nhận diện anti-pattern, KHÔNG dùng ở production.
ByteArrayOutputStream copy = new ByteArrayOutputStream();
messageContext.getRequest().writeTo(copy);
log.debug("incoming soap={}", copy.toString("UTF-8"));
~~~

Ngay sau thay đổi, có ba nhóm triệu chứng:

1. Khi bật DEBUG, memory tăng mạnh và request upload 50 MiB đôi khi timeout/OutOfMemoryError.
2. Một số request MTOM không còn đi qua trơn tru; transport/attachment handler gặp lỗi hoặc phải đọc lại stream.
3. Hệ thống phát hiện token và tài liệu khách hàng bị ghi vào log tập trung. Một số đối tác đồng thời thấy lỗi signature verification sau những thay đổi khác trong pipeline.

Không nên khẳng định **chỉ một dòng `writeTo(...)` chắc chắn làm hỏng mọi chữ ký**. Có thể nguyên nhân signature nằm ở interceptor khác đã sửa Body hoặc cách serializer/message factory hoạt động. Phải phân tích từng trục: buffering, replayability, canonicalization, signed references và cấu hình security.

### 16.2. Chẩn đoán theo lớp

| Bước | Bằng chứng cần lấy | Điều muốn xác định |
|---|---|---|
| 1. Tắt raw body logging trong môi trường test | So latency/memory và request success rate | Có overhead do log/copy toàn bộ payload? |
| 2. Thử payload nhỏ và lớn | Heap, GC, temp disk, network | Ngưỡng mất streaming/spooling |
| 3. Gửi MTOM thật | MIME parts và checksum bytes | Có mất Content-ID, thay đổi attachment hoặc đọc stream hai lần? |
| 4. Thử request ký hợp lệ | WS-Security validation result | Signature verify pass/fail ở cấu hình baseline |
| 5. Thử signature tampering có kiểm soát | Request lỗi phải bị từ chối | Security interceptor có hoạt động đúng hay bị bỏ qua? |
| 6. Quan sát callback order | Trạng thái trước/sau security và validation | Interceptor nào đọc/mutate khi message chưa được xác minh? |
| 7. Kiểm tra log output | Synthetic tokens/PII không xuất hiện | Loại bỏ đường rò rỉ |
| 8. Chạy regression từ client độc lập | WSDL/XSD/Fault/WS-Security interoperability | Không chỉ làm hết lỗi ở một client Java |

### 16.3. Thiết kế lại

Một phương án:

1. **Gỡ bỏ raw payload log** khỏi interceptor thông thường. Thay bằng event kiểu `operationCode`, `outcome`, `durationMs` và mã sự cố nội bộ đã kiểm soát.
2. **Không tự parse/serialize lại SOAP** trong interceptor chỉ để logging. Với nội dung nghiệp vụ cần validate, dùng XSD/JAXB/DOM được cấu hình đúng mức và tránh copy dữ liệu không cần thiết.
3. **Giao WS-Security cho security stack**, không tự cắt/ghép `wsse:Security` hoặc đổi signed XML.
4. **Xử lý binary ở lớp phù hợp**, có streaming policy, giới hạn MIME part và kiểm tra file theo nghiệp vụ, không nạp toàn bộ vào log.
5. **Thiết kế đường sự cố có phê duyệt** nếu thật sự cần packet capture: chỉ test/sandbox hoặc quy trình production khẩn cấp với kiểm soát truy cập, mã hóa, TTL và redaction.
6. **Kiểm thử lại chữ ký request và response**, đảm bảo không có custom interceptor thay đổi signed parts ở thời điểm không hợp lệ.
7. **Đặt resource limits** tại gateway/container/message parser để chống request khổng lồ trước khi vào endpoint.

### 16.4. Phân biệt ba kết luận

- “Không còn OOM sau khi bỏ debug log” là bằng chứng về **memory pressure do logging**, không tự chứng minh MTOM đã đạt streaming tối ưu.
- “SOAP request thành công” không tự chứng minh **chữ ký được xác minh** nếu chưa thử request tampered/unsigned.
- “Không thấy token trong application log” chưa đủ nếu gateway, APM, reverse proxy hoặc trace exporter đang tự thu raw messages.

Phải có **evidence riêng** cho performance, integrity/security và privacy.

## 17. Bài tập tự luyện kèm đáp án

### Bài 1 — Read-only interceptor có luôn an toàn?

Một interceptor chỉ gọi `message.writeTo(ByteArrayOutputStream)`, không sửa object nào. Có thể khẳng định không ảnh hưởng streaming không?

**Đáp án:** Không. “Read-only” về mặt logic không đồng nghĩa không gây materialization, copy, I/O hoặc đọc stream một lần. Nó cũng có thể làm rò rỉ dữ liệu nếu buffer được log. Phải kiểm tra message factory, attachment semantics và memory.

### Bài 2 — Cùng giá trị decimal, chữ ký có còn đúng?

Client ký XML:

~~~xml
<o:amount xmlns:o="urn:example:orders:v1">100.00</o:amount>
~~~

Một interceptor đổi text node thành `100` sau bước ký, rồi server xác minh chữ ký. Có thể nói đây là thay đổi vô hại vì hai số bằng nhau?

**Đáp án:** Không. XSD `xs:decimal` có thể coi cùng giá trị, nhưng XML Signature xác minh dữ liệu theo transforms/canonicalization được ký. Thay text node của phần tử đã được reference thường dẫn tới digest mismatch.

### Bài 3 — Thêm SOAP Header sau bước signing

Một interceptor thêm `<m:traceId>...` vào Header sau signing. Chữ ký chắc chắn fail trong mọi trường hợp?

**Đáp án:** Không thể khẳng định “mọi trường hợp” nếu không biết các references và policy. Header mới ngoài phạm vi signed references có thể không làm đổi digest hiện có, **nhưng** có thể vi phạm WS-SecurityPolicy, làm thay namespace context/serialization hoặc gây lỗi interop. Cách đúng là đặt tracing header ở giai đoạn đã thiết kế và test signature/policy.

### Bài 4 — Log trước verify có vấn đề gì?

Một request có `wsse:Security` và `CustomerAccount` trong Body. Logging interceptor chạy trước WS-Security validation rồi ghi toàn bộ XML. Vì sao đây là rủi ro kép?

**Đáp án:** Body/Token chưa được xác minh vẫn bị đưa vào log, tạo đường rò rỉ dữ liệu và log injection từ input chưa đáng tin. Interceptor còn có thể buffer message trước khi verify. Nên log metadata tối thiểu, áp dụng security theo policy và cấm raw payload logs.

### Bài 5 — MTOM có luôn stream không?

Client bật MTOM và server nhận `DataHandler`. Có thể kết luận file 100 MiB không nằm trong heap?

**Đáp án:** Không. Runtime có thể buffer/spool, JAXB/validation/security có thể materialize dữ liệu. Phải đo memory/temp files và kiểm tra attachment bytes thực tế.

### Bài 6 — Các đường lỗi nào không đi qua handleFault?

Một request bị lỗi TLS handshake hoặc SOAP Envelope không well-formed ngay lúc parsing. Có thể tin `EndpointInterceptor#handleFault` luôn ghi audit lỗi đó?

**Đáp án:** Không. Các lỗi xảy ra trước endpoint mapping/interceptor chain có thể không bao giờ gọi `handleFault`. Cần quan sát ở đúng transport/parser/security layers mà không log dữ liệu nhạy cảm.

### Bài 7 — Redaction bằng regex

Một SOAP logger thay chuỗi `<Password>abc</Password>` nhưng client gửi:

~~~xml
<wsse:Password
    xmlns:wsse="urn:demo:security">abc</wsse:Password>
~~~

Có thể coi logger đã che mật khẩu?

**Đáp án:** Không. Regex phụ thuộc tên tag cố định có thể bỏ sót prefix/namespace, whitespace và các dạng XML khác. Ưu tiên không log Body/Header; khi bắt buộc audit, dùng allowlist dữ liệu có cấu trúc và policy che dữ liệu đã được kiểm thử.

### Bài 8 — Retry và dữ liệu nhạy cảm

SOAP client gửi thanh toán, request timeout, tự retry ba lần; interceptor log mỗi lần cả SOAP Body. Có những vấn đề nào?

**Gợi ý:** Nhiều bản ghi PII, memory/log cost tăng, nguy cơ chạy payment trùng nếu không có idempotency, thiếu chứng cứ endpoint đã xử lý lần đầu. Cần retry policy, correlation, request ID phù hợp và metadata-only audit.

### Bài 9 — Thứ tự ký/mã hóa

Có thể hardcode quy tắc “luôn verify trước decrypt” cho mọi WS-SecurityPolicy?

**Đáp án:** Không. Signing/encryption order, references và profile của hai phía quyết định cách xử lý. Dùng security stack tương thích, cấu hình policy và test tích hợp với message thật.

### Bài 10 — Test gì để chứng minh an toàn?

Một PR sửa interceptor từ raw-body log sang metadata-only. Những nhóm test nào phải cập nhật?

**Đáp án:** Unit test không truy cập message; tests không rò rỉ synthetic secret trong logs/traces; signed/tampered message tests; MTOM checksum/memory benchmark; SOAP Fault và negative security tests; regression với client độc lập cùng policy.

## 18. Checklist trước khi triển khai interceptor

### Thiết kế và luồng xử lý

- [ ] Đã phân biệt `EndpointInterceptor` với `ClientInterceptor` và servlet filter.
- [ ] Biết chính xác interceptor nào chạy ở request, response, fault, completion.
- [ ] Không coi các lỗi trước mapping/transport như luôn đi qua endpoint callbacks.
- [ ] Đã xác định rõ trust boundary: dữ liệu ở thời điểm này đã được xác thực/giải mã hay chưa?
- [ ] Không đặt state riêng của request trong singleton interceptor field.
- [ ] Đã kiểm tra thứ tự các interceptors theo behavior thực tế, không chỉ theo danh sách Java.

### Streaming và MTOM

- [ ] Không serialize toàn bộ SOAP request/response chỉ để logging/tracing.
- [ ] Không tự đọc một attachment stream rồi giả định có thể đọc lại.
- [ ] Đã test Base64 inline, MTOM/XOP package, MIME Content-ID và checksum bytes.
- [ ] Có HTTP/MIME/body size limits, giới hạn decoded bytes, thời gian và temp disk.
- [ ] Đã đo peak memory/GC/disk và p95/p99 latency khi bật security + validation.
- [ ] Nếu cần xử lý file lớn, dùng thành phần streaming/spooling có cleanup và backpressure rõ.

### Chữ ký và WS-Security

- [ ] Không sửa nội dung đã ký mà không hiểu references/transforms/canonicalization.
- [ ] Không tự thay `wsu:Id`/SOAP Header/Body sau signing.
- [ ] Signing, encryption, verification, decryption theo đúng policy; không hardcode một thứ tự cho mọi đối tác.
- [ ] Có test request signature hợp lệ và request bị tamper/thiếu chữ ký.
- [ ] Có test outbound SOAP response đã ký và client xác minh được.
- [ ] Có test security trên attachments nếu WS-SecurityPolicy yêu cầu.
- [ ] TLS, keystore/truststore, certificates và quyền nghiệp vụ được xác minh riêng.

### Dữ liệu nhạy cảm và vận hành

- [ ] Logging/metrics chỉ dùng fields trong allowlist, không chứa SOAP Body/Header raw.
- [ ] Không log password, token, private key, signed XML raw, PII hoặc MIME attachments.
- [ ] Tracing ID/operation labels được chuẩn hóa và giới hạn cardinality.
- [ ] Log retention, quyền truy cập, encryption at rest và quy trình incident được quy định.
- [ ] SOAP Fault không echo exception stack trace, raw XML hoặc security material.
- [ ] Unit/integration tests quét synthetic secrets trên logs, traces, metrics và fault responses.
- [ ] Có test ở các lớp ngoài endpoint: HTTP filters, proxy/APM và transport errors.
- [ ] Có bộ test hồi quy với client Spring-WS và ít nhất một client độc lập theo WSDL/XSD đã phát hành.

**Ghi nhớ:** Interceptor trong Spring Web Services là điểm mở rộng mạnh nhưng **không trung tính** với chi phí xử lý, tính toàn vẹn XML hay an toàn dữ liệu. Đọc hoặc serialize payload có thể phá streaming; sửa XML sau ký có thể phá SOAP Signature; log Body/Header có thể để lộ PII, token và attachments. Hãy ưu tiên **metadata-only observability**, giao WS-Security cho stack chuyên dụng, giữ contract XSD/WSDL ổn định và kiểm chứng bằng các bài test hiệu năng, chữ ký, MTOM và không rò rỉ dữ liệu.
