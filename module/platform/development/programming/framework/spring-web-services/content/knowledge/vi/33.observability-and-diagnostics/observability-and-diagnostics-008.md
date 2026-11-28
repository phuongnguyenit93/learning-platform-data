# Lỗi SOAP version, Content-Type, charset và nội dung HTML từ proxy

> **Chương:** Quan sát và chẩn đoán  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp ổn định.

## 1. Vì sao client SOAP nhận lỗi Content-Type hoặc HTML?

Một SOAP client thường mong đợi HTTP response chứa SOAP Envelope. Tuy nhiên, thực tế response có thể là HTTP 415, 404, 502 hoặc 503; Content-Type không đúng SOAP version; charset không tương thích; hoặc body là một trang HTML từ reverse proxy, WAF, load balancer, SSO gateway hay trang lỗi của servlet container.

Các lỗi này thường xuất hiện dưới dạng:
- SOAP message factory không nhận dạng được response.
- Client báo không thể parse message hoặc không tìm thấy SOAP Envelope.
- XML parser gặp ký tự '<' nhưng root là html thay vì Envelope.
- SOAP 1.1 client nhận response SOAP 1.2 hoặc ngược lại.
- HTTP 415 do request Content-Type không khớp binding endpoint.
- XML parser báo malformed character/encoding hoặc ký tự không hợp lệ đầu file.
- WSDL hoạt động trong browser nhưng SOAP POST bị redirect sang login page.
- Proxy trả HTML 502/504 dù upstream SOAP server chưa nhận request.

Điều quan trọng là không coi tất cả các lỗi này là “SOAP Fault”. HTTP error, transport response, XML parsing failure, SOAP protocol fault và business fault thuộc các tầng khác nhau. Cần giữ raw evidence đủ để xác định tầng tạo lỗi trước khi sửa cấu hình.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt SOAP 1.1 và SOAP 1.2 trên wire.
2. Đối chiếu HTTP Content-Type, SOAPAction và action parameter với WSDL binding.
3. Chẩn đoán charset, XML declaration, BOM và encoding mismatch.
4. Nhận biết gzip/decompression và lỗi body bị cắt.
5. Phân biệt SOAP XML với HTML do proxy/gateway/WAF/SSO trả về.
6. Thu thập HTTP status, headers và body an toàn để tái lập lỗi.
7. Kiểm tra Spring-WS WebServiceTemplate, MessageSender và SOAP MessageFactory.
8. Thiết kế retry, timeout và error mapping theo nguyên nhân.
9. Tạo test matrix và observability để lỗi được phát hiện sớm.

**Nguyên tắc:** Trước khi parse body như SOAP, hãy xác định HTTP status, Content-Type, charset và loại nội dung thực tế. Một response HTML không trở thành SOAP Fault chỉ vì request ban đầu là SOAP.

## 2. Phân tầng lỗi trước khi điều tra

Một request/response SOAP đi qua nhiều tầng. Xác định tầng đầu tiên tạo ra sai lệch sẽ rút ngắn thời gian điều tra.

| Tầng | Dấu hiệu | Câu hỏi chẩn đoán |
|---|---|---|
| DNS/TCP/TLS | Connection refused, reset, handshake failure | Đã kết nối đúng host/certificate chưa? |
| HTTP routing | 301/302/404/401/403/407/502/503/504 | Request tới đúng proxy/upstream/path chưa? |
| HTTP representation | 400/415, Content-Type không đúng | Media type/SOAP version có khớp không? |
| Compression/charset | Gzip error, invalid byte sequence, mojibake | Body có giải nén/decode đúng không? |
| XML parsing | Malformed XML, unexpected character | Bytes có phải XML well-formed không? |
| SOAP protocol | VersionMismatch, MustUnderstand, SOAP Fault | Envelope namespace/header có hợp lệ không? |
| XSD/JAXB | Unmarshal/schema validation failure | Payload QName/type/sequence có đúng contract không? |
| Business | Modeled fault hoặc domain rejection | Request hợp contract nhưng có vi phạm nghiệp vụ không? |

Một HTTP 500 không tự chứng minh upstream SOAP endpoint đã được gọi. Proxy cũng có thể trả 500/502 với HTML. Một HTTP 200 cũng không chứng minh body là SOAP: SSO portal hoặc proxy lỗi có thể trả login HTML với status 200.

### 2.1. Sơ đồ triage

~~~mermaid
flowchart TD
  A["SOAP client receives response"] --> B["Inspect status and headers"]
  B --> C{"Content-Type indicates SOAP/XML?"}
  C -->|No| D["Classify HTTP/proxy/auth response"]
  C -->|Yes| E["Inspect raw bytes and charset"]
  E --> F{"XML well-formed?"}
  F -->|No| G["Encoding/truncation/compression diagnosis"]
  F -->|Yes| H{"SOAP Envelope namespace matches client?"}
  H -->|No| I["SOAP version/binding mismatch"]
  H -->|Yes| J{"SOAP Fault present?"}
  J -->|Yes| K["Map protocol/security/business fault"]
  J -->|No| L["Validate payload and JAXB mapping"]
~~~

## 3. SOAP 1.1 và SOAP 1.2 có wire format khác nhau

Không thể chuyển SOAP 1.1 thành SOAP 1.2 chỉ bằng thay header HTTP. Hai version có Envelope namespace, HTTP media type, action convention và Fault model khác nhau.

| Thành phần | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | http://schemas.xmlsoap.org/soap/envelope/ | http://www.w3.org/2003/05/soap-envelope |
| HTTP Content-Type thường dùng | text/xml | application/soap+xml |
| Action | SOAPAction HTTP header | action parameter của application/soap+xml theo binding |
| Fault code | faultcode | Code và Subcode |
| Fault reason | faultstring | Reason/Text |
| Detail | detail | Detail |

SOAP 1.1 thường sử dụng text/xml và SOAPAction; SOAP 1.2 sử dụng application/soap+xml, trong đó action có thể được truyền như media type parameter. Quy tắc chính xác phải theo binding và phiên bản protocol đang dùng.

### 3.1. Nhận diện Envelope namespace

SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header/>
  <soap:Body>
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

SOAP 1.2:

~~~xml
<soap:Envelope
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Header/>
  <soap:Body>
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Prefix soap có thể đổi; namespace URI mới quyết định version. Không so chuỗi prefix để xác định SOAP version.

### 3.2. VersionMismatch

Nếu server/client không hỗ trợ Envelope namespace nhận được, SOAP có thể trả VersionMismatch hoặc framework có thể từ chối message ở tầng message factory. Không đổi namespace thủ công rồi gửi lại mà chưa kiểm tra WSDL binding, partner configuration và endpoint message factory.

## 4. Content-Type phải khớp SOAP binding

Content-Type mô tả loại message HTTP đang mang. Một số tình huống thường gặp:

| Request/response | Dấu hiệu |
|---|---|
| SOAP 1.1 đúng | text/xml; charset=UTF-8 (có thể có biến thể hợp lệ) |
| SOAP 1.2 đúng | application/soap+xml; charset=UTF-8 |
| Server trả XML thường | application/xml hoặc text/xml nhưng body không có SOAP Envelope |
| Server trả HTML | text/html |
| Proxy trả JSON error | application/json |
| Request gửi sai SOAP version | HTTP 415 hoặc SOAP protocol error |
| MIME/MTOM | multipart/related với parameters mô tả root SOAP part và type |

Không chỉ kiểm tra media type prefix. Với MTOM, Content-Type có thể là multipart/related; client cần hiểu MIME parameters, root part và SOAP subtype. Không ép tất cả response Content-Type thành text/xml.

### 4.1. HTTP 415 Unsupported Media Type

Các nguyên nhân có thể:
- SOAP 1.1 client gửi application/soap+xml tới endpoint chỉ nhận SOAP 1.1.
- SOAP 1.2 client gửi text/xml tới endpoint chỉ nhận SOAP 1.2.
- Gateway route có allowlist Content-Type khác.
- Multipart/MTOM không được enable hoặc proxy không hỗ trợ.
- Charset/media type parameters bị gateway parse sai.
- Client gửi JSON/XML payload tới path SOAP.

Quy trình:
1. Capture request HTTP thực tế.
2. Xem method, path và Content-Type.
3. Đối chiếu SOAP version với Envelope namespace.
4. Đọc WSDL binding và endpoint address.
5. Kiểm cấu hình proxy/ingress Content-Type allowlist.
6. Lặp lại bằng request tối thiểu qua cùng route.
7. So response từ upstream trực tiếp với response đi qua gateway.

### 4.2. SOAPAction không thay Content-Type

SOAPAction thường quan trọng cho SOAP 1.1 operation routing. Header này không đổi message thành SOAP 1.2 và cũng không xác định charset. Kiểm tra action theo WSDL binding, nhưng đừng dùng SOAPAction làm chứng cứ authentication.

## 5. Charset, XML declaration và encoding mismatch

XML bytes phải được giải mã theo encoding thực tế. Các nguồn thông tin có thể gồm HTTP charset parameter và XML declaration. Nếu chúng mâu thuẫn, parser có thể báo lỗi hoặc diễn giải sai ký tự.

Ví dụ XML UTF-8:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:customerName>Nguyễn An</ord:customerName>
</ord:GetOrderRequest>
~~~

HTTP response có thể khai báo:

~~~http
Content-Type: text/xml; charset=UTF-8
~~~

### 5.1. Lỗi thường gặp

- Bytes UTF-8 nhưng HTTP header khai báo ISO-8859-1.
- XML declaration nói UTF-16 trong khi body được encode UTF-8.
- Client chuyển bytes thành String bằng charset hệ thống mặc định rồi encode lại.
- Proxy decode/re-encode body và làm mất byte sequence.
- Server gửi BOM hoặc byte order không khớp với declaration.
- Body bị truncate giữa một ký tự multibyte.
- Logging filter đọc InputStream rồi wrap lại không đúng encoding.

### 5.2. Quy tắc xử lý

- Chốt UTF-8 cho contract nếu các bên thống nhất hỗ trợ.
- Serialize XML trực tiếp từ marshaller/message factory thành bytes; tránh chuyển qua String trung gian không cần thiết.
- Khi phải đọc body, dùng charset được protocol/header chỉ định và kiểm declaration consistency.
- Không dùng Charset.defaultCharset() cho wire protocol.
- Không tự xóa BOM hoặc ký tự đầu file nếu chưa xác định nguồn và encoding.
- Kiểm tra raw bytes bằng hex view trong môi trường an toàn.
- Có fixtures cho tiếng Việt, emoji hợp lệ theo XML version, ký tự combining và payload bị cắt.

### 5.3. Ví dụ lỗi double-encoding

Một client nhận UTF-8 bytes, decode sai thành String bằng charset single-byte, sau đó marshal lại UTF-8. Kết quả thường hiển thị mojibake như ký tự có dấu bị biến thành chuỗi ký tự lạ. Sửa bằng cách giữ nguyên bytes/encoding xuyên suốt hoặc decode đúng một lần theo charset xác định.

## 6. BOM và byte đầu của XML

Một số XML documents có Byte Order Mark. BOM có thể hợp lệ tùy encoding, nhưng cách xử lý phải phù hợp parser/provider và message factory. Không nên strip ba bytes đầu một cách vô điều kiện vì:
- Body có thể không phải UTF-8.
- BOM có thể mang ý nghĩa byte order cho UTF-16/UTF-32.
- Data có thể bị cắt/truncate khiến byte pattern giống BOM ngẫu nhiên.
- Multipart MIME có boundaries/headers trước XML root part.

Nếu parse error chỉ xuất hiện sau một gateway, so sánh raw bytes trước/sau gateway trong test environment. Kiểm Content-Type charset, XML declaration, BOM và byte length. Không ghi raw body nhạy cảm ra logs.

## 7. Compression và body bị cắt

HTTP compression có thể dùng Content-Encoding: gzip hoặc deflate. Lỗi xảy ra nếu:
- Server gửi compressed bytes nhưng thiếu Content-Encoding.
- Proxy giải nén nhưng giữ nguyên header Content-Encoding.
- Response bị cắt ở giữa gzip stream.
- Client không bật compression nhưng gateway đã nén.
- Body quá lớn sau giải nén hoặc bị giới hạn ở một hop.

Kiểm riêng:
- Content-Encoding.
- Content-Length nếu có.
- Transfer-Encoding/chunking.
- Bytes thực nhận sau giải nén.
- Timeout/reset trong lúc đọc.
- Gateway max body size và buffering limits.

Không suy ra body đầy đủ từ Content-Length một mình khi transfer encoding/compression thay đổi. Nếu body bị truncate, XML parser có thể báo unexpected EOF nhưng nguyên nhân gốc là transport/proxy chứ không phải XSD.

## 8. Khi body là HTML từ proxy, WAF hoặc SSO

Đây là dấu hiệu quan trọng: client gọi SOAP endpoint nhưng nhận document có root html, title trang đăng nhập hoặc error page. Nguồn thường gặp:

- Reverse proxy không tìm thấy upstream, trả 502/503.
- Gateway route sai path và trả 404 HTML.
- WAF chặn request vì rule/size/content pattern.
- SSO gateway redirect request chưa xác thực sang login page.
- Proxy trả trang session expired hoặc maintenance.
- Load balancer route tới web frontend khác SOAP backend.
- Upstream timeout và proxy tạo HTML 504.
- Authentication challenge được xử lý bởi portal thay vì SOAP endpoint.

### 8.1. Vì sao status 200 vẫn có thể là HTML?

Một gateway/login portal có thể redirect rồi cuối cùng trả login page với HTTP 200. SOAP client nhìn status 200 rồi đưa HTML vào SOAP message factory, dẫn đến parse error. Do đó cần kiểm status **và** Content-Type/body root, không chỉ status code.

### 8.2. Dấu hiệu trong body

Các dấu hiệu thường thấy:
- <!DOCTYPE html>
- <html>, <head>, <title>
- Trang login/SSO.
- Proxy branding hoặc request/reference ID.
- Trang WAF block/captcha.
- Web server stack page.

Đừng đưa toàn HTML response vào ticket/log nếu có cookie, CSRF token, internal hostname hoặc request details. Ghi status, Content-Type, server/via/request ID và một đoạn đã redaction hoặc hash body.

### 8.3. Không parse HTML như SOAP Fault

SOAP Fault phải nằm trong SOAP Envelope và có Fault element theo SOAP version. HTML proxy error không phải SOAP Fault, kể cả status 500. Client adapter nên phân biệt transport/non-SOAP response với SOAP fault đã parse.

## 9. Quy trình thu thập HTTP evidence

Khi lỗi xảy ra, thu một bộ evidence tối thiểu, có timestamp và correlation ID:

1. Target URL đã redaction credentials/query secrets.
2. HTTP method/path.
3. Status code và redirect chain.
4. Request/response Content-Type và charset.
5. Content-Encoding và transfer headers.
6. SOAP version dự kiến và Envelope namespace thực.
7. SOAPAction/action parameter.
8. Response body classification: SOAP XML, XML không SOAP, HTML, JSON, binary hoặc empty.
9. Proxy/gateway request ID, Server/Via headers nếu có.
10. Thời điểm, operation, client version và partner environment.
11. Request/response byte counts và duration.
12. Correlation ID giữa client, gateway và server logs.

### 9.1. Dùng curl để kiểm tra gateway

Có thể gửi request fixture qua cùng route:

~~~bash
curl --include --verbose   --request POST   --header 'Content-Type: text/xml; charset=UTF-8'   --header 'SOAPAction: "urn:example:orders:v1/GetOrder"'   --data-binary @get-order-soap11.xml   https://soap.example.test/ws
~~~

Với SOAP 1.2, thay Content-Type/action theo binding được công bố. Bảo vệ output vì verbose mode có thể in headers/cookies. Không đặt password/token trực tiếp trong command history hoặc chia sẻ capture chưa redaction.

Để kiểm tra WSDL:

~~~bash
curl --include --verbose   https://soap.example.test/ws/orders.wsdl
~~~

Kết quả WSDL GET không chứng minh SOAP POST route cũng đi đến cùng upstream. Test cả WSDL GET và operation POST.

### 9.2. So sánh direct-upstream và gateway

Trong test environment được phép:
- Gọi trực tiếp upstream service bằng URL nội bộ hợp lệ.
- Gọi qua public gateway.
- So status, Content-Type, charset, body hash và request ID.
- Nếu direct upstream SOAP nhưng gateway trả HTML, khoanh vùng proxy/auth/WAF/routing.
- Nếu cả hai cùng lỗi, kiểm server binding/message factory/endpoint.

Không bypass production security hoặc truy cập network nội bộ ngoài quyền được cấp. So sánh phải dùng endpoint/test account được phê duyệt.

## 10. Kiểm tra Spring-WS client configuration

WebServiceTemplate dùng MessageSender để thực hiện HTTP exchange và message factory để tạo SOAP message. Cần kiểm:
- SOAP version/message factory client dùng.
- Default URI/endpoint URL.
- HTTP message sender implementation/version.
- Timeout connect/read/connection request.
- HTTP authentication/proxy configuration.
- SOAPAction callback và custom headers.
- Compression/decompression support.
- MTOM/MIME support nếu contract dùng.
- Client interceptors/error handling.
- Whether client follows redirects automatically.

Đặc biệt, redirects có thể làm POST SOAP chuyển sang login page hoặc thay method/body tùy redirect status/client behavior. Không tự động follow redirect sang host khác nếu không kiểm security implications.

### 10.1. Cấu hình SOAP 1.1/1.2 nhất quán

Trong Spring-WS, message factory phải khớp SOAP version cần dùng; client và endpoint binding phải nhất quán với WSDL. Cấu hình cụ thể phụ thuộc implementation (SAAJ hoặc message factory khác) và Spring-WS version. Kiểm actual Envelope namespace và HTTP Content-Type ở wire, không chỉ nhìn bean property.

### 10.2. Error mapping ở adapter

Adapter có thể phân loại:
- HTTP/transport errors.
- Non-SOAP body hoặc Content-Type mismatch.
- SOAP Fault parse được.
- XML/JAXB response mapping failure.
- Business error.

Không catch mọi exception rồi trả null hoặc empty response. Giữ nguyên cause, correlation ID và partner request ID để chẩn đoán.

## 11. Kiểm tra Spring-WS server và servlet mapping

Khi client nhận HTML, server SOAP có thể chưa được gọi. Kiểm:
- MessageDispatcherServlet mapping.
- Context path và endpoint path.
- WSDL soap:address.
- Reverse proxy path rewriting.
- Upstream service/port mapping.
- Authentication filters và SSO exclusions cho machine-to-machine route.
- WAF body size/rule matching.
- Ingress request/response buffering and timeouts.

Nếu proxy expose /api/orders nhưng servlet listen /ws, ingress rewrite phải đúng. GET WSDL có thể route đúng static page trong khi POST lại bị route sang frontend do rule method/path khác nhau.

### 11.1. Correlate logs qua các hops

Dùng một correlation/request ID được propagation qua proxy, HTTP headers và application logs. Server log nên ghi request ID khi message được dispatch. Nếu gateway có request ID riêng, ghi mapping giữa gateway ID và application trace ID.

Đừng log Authorization, cookies, WS-Security UsernameToken, BinarySecurityToken, SignatureValue hoặc raw SOAP Body.

## 12. Kiểm tra Content-Type của MTOM/MIME

Khi SOAP contract sử dụng MTOM, request/response có thể dùng multipart/related. Những trường thường cần xem:
- boundary.
- type.
- start.
- start-info.
- Content-ID của root part.
- Content-Type của SOAP root part.
- Content-ID được tham chiếu bởi xop:Include.
- Content-Transfer-Encoding/attachment metadata nếu implementation sử dụng.

Proxy có thể:
- Remove/normalize MIME headers.
- Buffer multipart rồi rewrite boundary.
- Cắt body do max request size.
- Không hỗ trợ Content-Type multipart/related.
- Thay đổi Content-Length hoặc chunked transfer.

Đừng sửa boundary bằng tay hoặc parse MIME bằng split string tùy tiện. Dùng MIME parser và test qua cùng HTTP route. Kiểm attachment bytes bằng length/checksum ở hai phía.

## 13. Response có HTML: cách phân loại an toàn trong code

Không nhất thiết log toàn body. Có thể phân loại theo status, Content-Type và một prefix rất ngắn đã redaction trước khi đưa vào error handling. Minh họa khái niệm:

~~~java
public enum ResponseKind {
    SOAP_XML,
    OTHER_XML,
    HTML,
    JSON,
    EMPTY,
    UNKNOWN
}
~~~

Một classifier production phải xử lý:
- Content-Type thiếu/sai.
- Parameters/charset.
- Multipart/related.
- Body empty.
- BOM/whitespace trước root.
- Gzip already decompressed bởi sender.
- Byte limit cho diagnostic prefix.
- Redaction của HTML/body.
- Không parse XML không tin cậy với parser tắt DTD/external entities.

Không dùng một regex đơn giản trên toàn body làm parser. Content-Type là hint; body bytes và SOAP envelope QName cần được xác minh theo giới hạn an toàn.

## 14. SOAP Fault khác HTTP error và proxy error

| Loại | Biểu diễn | Client xử lý |
|---|---|---|
| Transport failure | Không có response hợp lệ/connection exception | Timeout/retry policy |
| HTTP error HTML | Status HTTP + text/html | Gateway/proxy/auth/routing diagnosis |
| HTTP error SOAP Fault | Status + SOAP Envelope/Fault | Parse Fault và map code |
| SOAP Fault trong response | SOAP Envelope chứa Fault | Protocol/security/business fault mapping |
| XML parse failure | XML malformed/charset/truncated | Encoding/transport/parser diagnosis |
| XSD/JAXB failure | Envelope đúng nhưng payload không map | Contract/schema/version diagnosis |

SOAP binding có quy tắc status/Fault riêng; không giả định mọi SOAP Fault trả cùng HTTP status. Hãy kiểm SOAP version, server framework và WSDL binding.

## 15. Retry, redirect và authentication

### 15.1. Không retry HTML proxy response một cách mù quáng

HTML 502/503 có thể là transient gateway issue, nhưng HTML login page/403/404 thường là configuration/auth/routing error. Phân loại theo status, Content-Type, gateway request ID và retry policy. Không retry lặp lại login redirect hoặc WAF block.

### 15.2. Redirects

SOAP POST redirect có thể:
- 301/302/303: client có thể đổi POST thành GET theo implementation/policy.
- 307/308: thường giữ method/body, nhưng cần kiểm client behavior.
- Redirect sang SSO host: response cuối cùng có thể là HTML.

Đối với machine-to-machine SOAP, dùng endpoint service URL chuyên biệt và authentication phù hợp, không phụ thuộc browser login session/cookie. Không bật follow-redirect vô điều kiện sang cross-host.

### 15.3. HTTP authentication và WS-Security

HTTP Basic/Bearer/mTLS là transport/HTTP-layer authentication; WS-Security là message-level policy. Đừng trộn chúng trong debug:
- 401/407 có thể là HTTP auth/proxy auth.
- 403 có thể là authorization/WAF.
- SOAP Fault security có thể do WS-Security validation ở service.
- HTML login page thường là portal/SSO/proxy behavior.

Xác định credential được gửi tới đúng host, không forward token sang redirected host ngoài trust boundary.

## 16. Test matrix cho lỗi version, header, charset và proxy

| Test case | Request/response setup | Kỳ vọng |
|---|---|---|
| SOAP 1.1 happy path | text/xml + SOAP 1.1 Envelope | Client parse response |
| SOAP 1.2 happy path | application/soap+xml + SOAP 1.2 Envelope | Client parse response |
| Version mismatch | Content-Type và Envelope không cùng version | Reject rõ ràng |
| HTTP 415 | Proxy/server không nhận media type | Phân loại HTTP error |
| Wrong SOAPAction | Action khác binding | Routing/dispatch error được chẩn đoán |
| UTF-8 Vietnamese | Bytes/declaration/header UTF-8 | Text đúng |
| Charset mismatch | Header và bytes/declaration xung đột | Parse failure được phân loại |
| BOM | Fixture có/không BOM hợp lệ | Parser behavior nhất quán |
| Truncated body | Cắt XML/MIME trước EOF | Transport/XML failure |
| Gzip response | Content-Encoding gzip đúng/sai | Decompress đúng hoặc error rõ |
| HTML 200 | Login page với status 200 | Non-SOAP response |
| HTML 502/504 | Proxy error page | Gateway error, không SOAP Fault |
| Redirect | 302 tới login portal | Redirect/auth classification |
| MTOM multipart | boundary/root part/Content-ID đúng | Attachment parse thành công |
| Wrong MIME boundary | Multipart malformed | MIME parse failure |
| Empty response | Body rỗng | Non-SOAP/empty response |
| XML SOAP Fault | Envelope + Fault | Fault mapping đúng |

## 17. Case study: SOAP client nhận trang HTML dù endpoint hoạt động

### 17.1. Hiện tượng

Spring-WS client gọi operation GetOrder. WSDL tải được qua browser, nhưng client báo lỗi parse SOAP response. HTTP capture cho thấy status 200, Content-Type text/html và body là trang đăng nhập SSO.

### 17.2. Giả thuyết

- Endpoint URL đang trỏ tới browser-facing gateway.
- Gateway yêu cầu session cookie thay vì service credential.
- Redirect 302 sang SSO được HTTP client tự follow.
- SOAP POST route không nằm trong machine-to-machine allowlist.
- Client gửi authentication tới host ban đầu nhưng redirect sang host khác.
- Ingress route GET WSDL và POST operation khác nhau.

### 17.3. Quy trình điều tra

1. Ghi lại URL cuối cùng sau redirects và request method.
2. Capture status, Content-Type, Location, Server/Via và gateway request ID.
3. Xác minh body thực là HTML, không parse như SOAP.
4. Gọi service URL chính thức theo contract từ môi trường test được phép.
5. So route direct-upstream và gateway.
6. Xác nhận service authentication (mTLS/HTTP auth/WS-Security) đúng policy.
7. Cập nhật ingress route/SSO exclusion/service identity theo owner hạ tầng.
8. Thêm integration test xác minh response là SOAP Envelope.
9. Theo dõi gateway ID và application trace ID trong logs.

### 17.4. Tiêu chí đóng

- Client gọi đúng machine-to-machine SOAP URL.
- Redirect không đưa SOAP POST sang HTML login flow.
- HTTP Content-Type và Envelope SOAP version đúng binding.
- Authentication được áp dụng tại trust boundary đúng.
- Response/Fault parse đúng.
- Logs có correlation IDs và không có secrets.
- Regression test đi qua route thực tế đã cấu hình.

## 18. Bài tập tự luyện

**Bài 1 — SOAP 1.2:** Client gửi SOAP 1.1 Envelope với Content-Type application/soap+xml. Vấn đề là gì?

**Đáp án:** HTTP media type và Envelope version không khớp. Phải đồng bộ client message factory, binding và server endpoint.

**Bài 2 — HTTP 415:** Nên kiểm gì đầu tiên?

**Đáp án:** Capture method/path/Content-Type/SOAP version, đối chiếu WSDL binding và gateway allowlist.

**Bài 3 — HTML 200:** Client nhận status 200 nhưng SOAP parser thất bại. Vì sao?

**Đáp án:** Có thể đã follow redirect tới SSO/login page. Kiểm Content-Type, final URL, redirect chain và body classification.

**Bài 4 — Charset:** Bytes UTF-8 nhưng header nói ISO-8859-1. Triệu chứng có thể là gì?

**Đáp án:** Mojibake hoặc parse/decode inconsistency. Chốt encoding và tránh decode/encode nhiều lần.

**Bài 5 — BOM:** Có nên luôn strip bytes EF BB BF?

**Đáp án:** Không. Chỉ xử lý theo encoding và parser policy; multipart hoặc UTF-16 không thể xử lý bằng giả định UTF-8.

**Bài 6 — SOAP Fault:** HTML 502 có phải Receiver Fault?

**Đáp án:** Không. Đó là HTTP/proxy response không phải SOAP Envelope/Fault.

**Bài 7 — GET WSDL:** GET WSDL pass có chứng minh SOAP POST route pass?

**Đáp án:** Không. GET và POST có thể đi qua ingress rules/upstreams khác nhau.

**Bài 8 — SOAPAction:** SOAPAction sai có thể sửa bằng đổi Content-Type?

**Đáp án:** Không. Content-Type chỉ mô tả media type/SOAP version; action phải khớp binding.

**Bài 9 — MTOM:** Response multipart bị 415, kiểm gì?

**Đáp án:** Partner/proxy hỗ trợ multipart/related, MIME parameters, boundary, root part và MTOM configuration.

**Bài 10 — Retry:** Có nên retry trang HTML login 200?

**Đáp án:** Không. Đó là authentication/routing/configuration failure cho tới khi chứng minh là transient.

## 19. Checklist quan sát và chẩn đoán

### HTTP và transport
- [ ] Capture status, method, path và redirect chain.
- [ ] Ghi Content-Type, charset, Content-Encoding và transfer headers.
- [ ] Kiểm TLS hostname/certificate và proxy authentication khi liên quan.
- [ ] Lưu request IDs từ gateway/proxy/load balancer.
- [ ] So direct upstream và gateway trên environment được phép.

### SOAP protocol
- [ ] Kiểm Envelope namespace thực tế.
- [ ] Đồng bộ SOAP 1.1/1.2 với WSDL binding.
- [ ] Kiểm SOAPAction/action parameter.
- [ ] Kiểm SOAP Header/body QName và Fault structure.
- [ ] Kiểm MIME multipart/MTOM nếu sử dụng.

### XML encoding
- [ ] Chốt UTF-8/encoding contract.
- [ ] So HTTP charset với XML declaration và byte stream.
- [ ] Kiểm BOM và double-encoding.
- [ ] Kiểm body truncation và compression.
- [ ] Có fixtures cho tiếng Việt và ký tự đa byte.

### Proxy/gateway
- [ ] Xác minh body có phải HTML/JSON thay SOAP không.
- [ ] Kiểm SSO redirect, login page và final host.
- [ ] Kiểm WAF block, body size, timeout và path rewrite.
- [ ] Phân biệt lỗi GET WSDL với POST operation.
- [ ] Không retry vô hạn HTML auth/config failures.

### Spring-WS và client behavior
- [ ] MessageFactory khớp SOAP version.
- [ ] WebServiceTemplate dùng đúng MessageSender/URI.
- [ ] Redirect policy được kiểm soát.
- [ ] Timeout/error mapping phân biệt HTTP, SOAP Fault và XML errors.
- [ ] Không catch mọi Exception rồi trả null/success giả.

### Observability và security
- [ ] Correlation ID được propagation qua client/gateway/server.
- [ ] Logs chỉ lưu metadata và prefix đã redaction/size cap.
- [ ] Không log Authorization, Cookie, UsernameToken, signatures hoặc raw payload nhạy cảm.
- [ ] Parser tắt DTD/external entities theo policy.
- [ ] Metrics labels có cardinality thấp.
- [ ] Có test matrix SOAP version/charset/proxy/MTOM.

**Ghi nhớ:** Lỗi SOAP version, Content-Type, charset và HTML từ proxy phải được phân loại theo wire evidence. Xác định HTTP status, redirect chain, media type, encoding và nội dung body trước; sau đó mới kiểm SOAP Envelope/Fault, WSDL binding, JAXB hay business logic. Khi body là HTML, hãy điều tra gateway, authentication, routing và WAF thay vì cố parse nó như SOAP. Dùng correlation IDs, captures đã redaction và regression tests qua đúng route để lỗi có thể tái lập mà không làm lộ credentials hay dữ liệu SOAP.
