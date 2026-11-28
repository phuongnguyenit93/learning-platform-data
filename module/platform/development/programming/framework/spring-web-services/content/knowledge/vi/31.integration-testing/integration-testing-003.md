# Ma trận SOAP 1.1, SOAP 1.2, Content-Type và action

Khi tích hợp SOAP giữa Spring-WS client và server, XML Body có thể hợp lệ nhưng request vẫn bị từ chối vì dùng sai SOAP version, HTTP Content-Type hoặc action metadata. Lỗi có thể xuất hiện trước khi endpoint được gọi, tại HTTP message converter, SOAP message factory, dispatcher hoặc endpoint mapping.

Kiểm thử tích hợp cần xác minh đồng thời **SOAP Envelope version**, **HTTP media type**, **SOAP 1.1 SOAPAction header**, **SOAP 1.2 action media-type parameter** và **WS-Addressing Action** nếu ứng dụng bật WS-Addressing. Các giá trị này đều có thể tham gia định tuyến operation nhưng thuộc những lớp giao thức khác nhau.

Trong module **SPRING_WEB_SERVICES**, ma trận này giúp kiểm tra interoperability giữa Spring-WS client/server và SOAP stacks của đối tác. Cần xác nhận thông điệp trên đường truyền HTTP thực, không chỉ kiểm JAXB object hoặc gọi endpoint trực tiếp.

> **Nguyên tắc:** SOAP 1.1 thường dùng HTTP Content-Type `text/xml` cùng HTTP `SOAPAction`; SOAP 1.2 dùng `application/soap+xml`, trong đó `action` có thể được biểu diễn bằng tham số media type. WS-Addressing Action là một SOAP Header riêng. Không hoán đổi ba loại action metadata này.

## 1. Ba lớp cần phân biệt

| Lớp | SOAP 1.1 | SOAP 1.2 | Ý nghĩa |
| --- | --- | --- | --- |
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` | Xác định SOAP version |
| HTTP Content-Type | `text/xml` | `application/soap+xml` | Định dạng SOAP trên HTTP |
| HTTP action metadata | `SOAPAction` header | `action` parameter trong Content-Type khi dùng | Action theo HTTP binding |
| WS-Addressing Action | SOAP Header `wsa:Action` nếu bật | SOAP Header `wsa:Action` nếu bật | Action ở tầng WS-Addressing |

SOAP version được xác định bởi Envelope namespace và binding, không phải chỉ nhìn Content-Type. Các lớp cần nhất quán. Content-Type nói SOAP 1.1 nhưng Body dùng SOAP 1.2 Envelope là một version mismatch có thể bị reject trước endpoint mapping.

## 2. SOAP 1.1: text/xml và SOAPAction

SOAP 1.1 over HTTP thường có dạng:

```http
POST /services/orders HTTP/1.1
Host: soap.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "https://example.test/orders/GetOrder"
Content-Length: ...

<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="https://example.test/orders/v1">
  <soap:Header/>
  <soap:Body>
    <ord:GetOrderRequest>
      <ord:orderId>42</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
```

Điểm cần kiểm:
- Media type là `text/xml`; charset phải phù hợp encoding thực của bytes.
- SOAPAction là HTTP header riêng, không phải XML element trong Envelope.
- URI action cần khớp WSDL binding/client/server configuration.
- SOAP 1.1 HTTP binding định nghĩa SOAPAction header; nhiều stack yêu cầu header có mặt, kể cả khi value rỗng theo contract.
- Không tự thêm hoặc bỏ dấu quote tùy tiện; kiểm cú pháp header mà stack thực sự phát ra và chấp nhận.

Giá trị empty action có dạng `SOAPAction: ""`. Empty, missing và URI cụ thể là ba tình huống phải phân biệt.

### Test SOAPAction

Xác minh client phát đúng SOAPAction theo WSDL binding; URI không bị encode sai; empty action được xử lý theo contract; unknown action không route nhầm operation; request body đúng nhưng SOAPAction sai không âm thầm dispatch sang operation khác nếu action là tiêu chí mapping.

## 3. SOAP 1.2: application/soap+xml và action parameter

SOAP 1.2 over HTTP dùng media type `application/soap+xml`:

```http
POST /services/orders HTTP/1.1
Host: soap.example.test
Content-Type: application/soap+xml; charset=utf-8;
              action="https://example.test/orders/GetOrder"

<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="https://example.test/orders/v1">
  <env:Header/>
  <env:Body>
    <ord:GetOrderRequest>
      <ord:orderId>42</ord:orderId>
    </ord:GetOrderRequest>
  </env:Body>
</env:Envelope>
```

Điểm cần kiểm:
- Media type là `application/soap+xml`.
- `action` là Content-Type parameter, không phải HTTP header SOAPAction.
- Action parameter có thể vắng theo SOAP 1.2 HTTP binding; nếu contract/client stack yêu cầu phát nó thì phải đúng URI.
- Không giả định SOAP 1.1 SOAPAction và SOAP 1.2 action parameter có cùng behavior ở mọi server/library.
- Parser phải xử lý Content-Type parameters không phụ thuộc thứ tự và phân biệt charset với action.

Hành vi Spring-WS thực tế còn phụ thuộc message factory, HTTP sender/receiver và endpoint mapping. Test wire-level nên capture Content-Type đầy đủ và SOAP Envelope namespace.

## 4. WS-Addressing Action là một SOAP Header

WS-Addressing định nghĩa Action trong SOAP Header, thường dùng namespace `http://www.w3.org/2005/08/addressing`:

```xml
<soap:Header
    xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Action>https://example.test/orders/GetOrder</wsa:Action>
  <wsa:MessageID>urn:uuid:8c7d5d30-3b71-4cf6-a1f6-22d157acd251</wsa:MessageID>
</soap:Header>
```

WS-Addressing Action không đồng nghĩa HTTP SOAPAction, SOAP 1.2 action parameter hoặc SOAP Body root QName. Có thể dùng cùng URI cho cả ba lớp nhưng đó là mapping theo contract, không phải quy tắc tự động. Nếu binding/profile quy định quan hệ cụ thể, test đúng WSDL/policy.

| Metadata | Vị trí | Consumer |
| --- | --- | --- |
| SOAPAction | HTTP header | SOAP 1.1 HTTP binding |
| action parameter | HTTP Content-Type parameter | SOAP 1.2 HTTP binding |
| wsa:Action | SOAP Header | WS-Addressing processing |
| Body QName | SOAP Body | Payload-based endpoint mapping |

## 5. Hai SOAP Envelope namespace không thể trộn

SOAP 1.1:

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header/>
  <soap:Body>
    <m:GetOrderRequest xmlns:m="https://example.test/orders/v1"/>
  </soap:Body>
</soap:Envelope>
```

SOAP 1.2:

```xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Header/>
  <env:Body>
    <m:GetOrderRequest xmlns:m="https://example.test/orders/v1"/>
  </env:Body>
</env:Envelope>
```

Prefix `soap` hay `env` không quyết định version; namespace URI mới quyết định. Server dùng SOAP 1.1 message factory không nên được kỳ vọng xử lý SOAP 1.2 Envelope chỉ vì Body QName giống nhau.

Nếu ứng dụng hỗ trợ cả hai version, cấu hình message factory/transport thích hợp và test từng version riêng. Không tuyên bố dual-version support chỉ vì một test của một version pass.

## 6. Ma trận hợp lệ và không hợp lệ

| Envelope | Content-Type | Action metadata | Kỳ vọng |
| --- | --- | --- | --- |
| SOAP 1.1 | text/xml | SOAPAction đúng | Request hợp lệ |
| SOAP 1.1 | text/xml | SOAPAction empty nếu contract cho phép | Empty-action policy đúng |
| SOAP 1.2 | application/soap+xml | action đúng hoặc vắng nếu được phép | Request hợp lệ |
| SOAP 1.1 | application/soap+xml | action parameter | Version/media mismatch, reject theo policy |
| SOAP 1.2 | text/xml | SOAPAction | Version/media mismatch, reject theo policy |
| SOAP 1.1 | text/xml | SOAPAction sai operation | Reject/Fault, không route sai |
| SOAP 1.2 | application/soap+xml | action sai | Reject/Fault theo policy |
| SOAP 1.2 | application/soap+xml | SOAPAction nhưng thiếu action parameter | Không giả định SOAPAction thay thế |
| Bất kỳ | Thiếu/unsupported Content-Type | bất kỳ | HTTP/message parsing failure |
| Bất kỳ | Media type đúng, Envelope namespace sai | bất kỳ | Version mismatch |

Status/Fault cụ thể phụ thuộc SOAP binding, Spring-WS version, message factory và exception resolver. Test cần ghi behavior đã chọn thay vì áp một status code chung cho mọi implementation.

## 7. Charset và encoding: header phải khớp bytes

Content-Type có thể khai báo charset, XML declaration cũng có thể chỉ encoding. Test không nên chỉ kiểm string Java trước khi gửi; phải xác minh bytes thực trên HTTP.

Các tình huống:
- Header UTF-8 và payload bytes UTF-8: round-trip hợp lệ.
- Header khai UTF-8 nhưng bytes dùng charset khác: receiver có thể parse sai hoặc reject.
- XML declaration mâu thuẫn HTTP charset: xác định parser behavior và policy.
- Non-ASCII characters trong tên/ghi chú: kiểm round-trip để phát hiện mojibake.
- Content-Type thiếu charset: kiểm default/encoding thực tế.
- Unsupported charset: client/server báo lỗi rõ.

Không kiểm encoding bằng string trước serialization. Capture HTTP bytes/headers ở integration boundary và parse lại response.

## 8. Message factory và Spring-WS version

Spring-WS nhận biết SOAP version qua message factory/configuration. Những điểm cần xác minh:
- SOAP 1.1 hay 1.2 factory/soapVersion được chọn.
- HTTP sender/receiver chọn media type phù hợp.
- Servlet/message dispatcher nhận đúng Content-Type.
- WSDL binding công bố SOAP version nào.
- WebServiceTemplate dùng message factory tương ứng.
- Test dùng cùng factory config production.
- Nếu hỗ trợ hai version, route/factory không mơ hồ.

Ví dụ SOAP 1.2 với SAAJ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
class Soap12MessageConfiguration {
    @Bean
    SaajSoapMessageFactory soap12MessageFactory() {
        SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
        factory.setSoapVersion(SoapVersion.SOAP_12);
        return factory;
    }
}
```

Kiểm tra class/package và SAAJ provider theo version. Nếu application có auto-configuration hoặc factory bean riêng, test đúng bean đó thay vì tự tạo factory khác chỉ để test pass.

## 9. Kiểm thử client wire format với HTTP integration

MockWebServiceServer hữu ích để kiểm request/message và client behavior ở abstraction Spring-WS. Để chứng minh HTTP headers thực tế, gửi request qua embedded server hoặc HTTP test endpoint có thể capture raw request.

Ghi nhận:
- HTTP method và request URI.
- Content-Type media type.
- Charset/action parameters.
- SOAPAction header presence/value.
- SOAP Envelope namespace.
- WS-Addressing Action nếu bật.
- Response status, Content-Type và Envelope version.
- Payload được parse đúng.

Một mock matcher ở message layer không chứng minh reverse proxy, servlet container và HTTP transport phát header ngoài wire như production. Cần integration path qua HTTP stack thực tế.

## 10. SOAP client: kiểm tra Content-Type và action

Một client thường gọi qua WebServiceTemplate. Message factory và sender quyết định wire representation. Test nên tạo client dùng template production, gửi request tới mock hoặc embedded HTTP server, capture headers/raw bytes, so Content-Type/action với binding, parse Envelope namespace/Body QName, trả response/Fault đúng version và assert unmarshalling/error handling.

Nếu client hỗ trợ nhiều SOAP versions, tạo fixture riêng cho từng version. Không chỉ đổi header trên cùng XML payload; phải đổi Envelope namespace và message factory tương ứng.

## 11. SOAP response và Fault theo version

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Envelope namespace | SOAP 1.1 URI | SOAP 1.2 URI |
| HTTP Content-Type | text/xml | application/soap+xml |
| Fault element | soap:Fault theo cấu trúc 1.1 | env:Fault theo cấu trúc 1.2 |
| Fault code | faultcode | Code/Value và Subcode |
| Reason/detail | faultstring, detail | Reason/Text, Detail |

Fault SOAP 1.2 không chỉ đổi namespace prefix từ SOAP 1.1; cấu trúc con khác. Test client cần xác minh SOAP version, Fault code/reason/detail và cách exception resolver map sang client exception.

HTTP status của Fault phải kiểm theo SOAP binding/server configuration đang hỗ trợ. Không hard-code 500 cho mọi trường hợp mà không xác định version/profile; cũng không coi HTTP 200 là bằng chứng response không phải Fault nếu profile cho phép Fault ở dạng khác.

## 12. Action và endpoint mapping

Spring-WS có thể định tuyến theo payload root, SOAPAction hoặc WS-Addressing Action tùy mapping/configuration:

| Cơ chế | Điều cần kiểm |
| --- | --- |
| @PayloadRoot | Namespace URI và localPart |
| @SoapAction | Action URI theo SOAPAction mapping |
| @Action | WS-Addressing Action nếu bật |
| Custom EndpointMapping | Priority, fallback và route coverage |

Không giả định HTTP SOAPAction tự tạo WS-Addressing Action. Không giả định Body QName sẽ bù cho action sai nếu mapping ưu tiên action. Dùng dispatcher/configuration thật của ứng dụng trong test.

## 13. Dual-version support và version mismatch

Server có thể chỉ hỗ trợ SOAP 1.1, chỉ hỗ trợ SOAP 1.2, hỗ trợ cả hai qua factory/config rõ ràng hoặc expose hai binding/port riêng trong WSDL.

Nếu hỗ trợ cả hai, kiểm:
- WSDL publish đúng binding cho mỗi version.
- Client chọn đúng port/binding.
- Hai media types được chấp nhận theo policy.
- Envelope namespace khớp Content-Type.
- Action mapping không dùng nhầm giữa bindings.
- Fault response đúng version.
- Security interceptors hoạt động trên cả hai message types.
- Request version sai không route qua fallback thiếu kiểm soát.

## 14. Security và action routing

Action URI là metadata định tuyến, **không phải credential**. Không dùng action để xác thực caller/phân quyền operation. Caller có thể tự đặt action; server vẫn phải xác minh authentication/authorization và payload.

Kiểm action không bypass HTTP Security; WS-Addressing Action được ký trong SOAP Header nếu integrity policy yêu cầu; SOAPAction HTTP header nằm ngoài Envelope nên không được XML Signature bảo vệ; unknown action không lộ stack trace; duplicate/conflicting HTTP headers được xử lý theo policy. Nếu cần integrity của HTTP metadata, đánh giá TLS hoặc cơ chế bảo vệ transport phù hợp.

## 15. Tổ chức test matrix theo dimensions

| Dimension | Giá trị |
| --- | --- |
| SOAP version | 1.1 / 1.2 |
| Content-Type | text/xml / application/soap+xml / unsupported |
| Action location | SOAPAction / media-type action / wsa:Action / none |
| Action value | Expected / empty / unknown / mismatch |
| Envelope namespace | 1.1 / 1.2 / wrong |
| Charset | UTF-8 / supported alternative / unsupported / mismatch |
| Body QName | Expected / unknown / wrong namespace |
| Fault | Success / Sender-Client / Receiver-Server |
| Transport | HTTP / HTTPS / proxy |
| Client stack | Spring-WS version / partner fixture |

Không cần chạy toàn bộ Cartesian product nếu nhiều tổ hợp vô nghĩa; có thể dùng pairwise cộng với negative cases rõ ràng. Nhưng phải có positive case cho mỗi version được tuyên bố hỗ trợ và test các mismatch rủi ro cao.

## 16. Test fixtures riêng cho từng version

```text
src/test/resources/soap/
  soap11/
    get-order-request.xml
    get-order-response.xml
    get-order-fault.xml
  soap12/
    get-order-request.xml
    get-order-response.xml
    get-order-fault.xml
  invalid/
    soap11-envelope-with-soap12-content-type.txt
    soap12-envelope-with-soap11-content-type.txt
    unknown-action.txt
```

Fixture tách biệt giúp review rõ SOAP version và tránh test đổi header nhưng quên Envelope. Mỗi fixture nên ghi mục đích, expected status/message result và WSDL/contract version.

## 17. Wire test SOAP 1.1

```http
POST /ws/orders HTTP/1.1
Content-Type: text/xml; charset=utf-8
SOAPAction: "https://example.test/orders/GetOrder"

<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:ord="https://example.test/orders/v1">
  <soap:Body>
    <ord:GetOrderRequest><ord:orderId>42</ord:orderId></ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
```

Kiểm server nhận đúng version/action và trả SOAP 1.1 response Content-Type. Thêm negative fixture thiếu header, unknown action và Envelope namespace sai. Expected status/Fault phụ thuộc HTTP binding/application mapping; ghi assertion theo behavior đã chọn.

## 18. Wire test SOAP 1.2

```http
POST /ws/orders HTTP/1.1
Content-Type: application/soap+xml; charset=utf-8;
              action="https://example.test/orders/GetOrder"

<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:ord="https://example.test/orders/v1">
  <env:Body>
    <ord:GetOrderRequest><ord:orderId>42</ord:orderId></ord:GetOrderRequest>
  </env:Body>
</env:Envelope>
```

Kiểm action parameter nếu binding dùng nó; response phải dùng SOAP 1.2 Envelope/Content-Type và Fault structure 1.2. Negative cases gồm content type 1.1, SOAPAction-only, action sai và Envelope SOAP 1.1.

## 19. Content negotiation không tự chuyển SOAP version

HTTP Accept mô tả response media type client có thể nhận; request Content-Type mô tả body đang gửi. Thay Accept từ text/xml sang application/soap+xml không tự chuyển SOAP Envelope hoặc binding.

Kiểm request Content-Type tương ứng bytes; Accept phù hợp response version; server không silently convert Envelope; unsupported media type có behavior được xác định; proxy không rewrite/drop Content-Type; charset không bị chỉnh sai.

## 20. Spring-WS server integration tests

Để test server ở HTTP boundary:
1. Khởi động application và HTTP server test.
2. Gửi raw SOAP 1.1/1.2 tới đúng servlet mapping.
3. Capture status, Content-Type và body.
4. Kiểm Envelope namespace và response payload.
5. Kiểm action mapping đến đúng endpoint.
6. Gửi mismatch/unknown action và xác nhận không gọi nhầm business service.
7. Gửi malformed/unsupported content type và xác nhận lỗi trước endpoint.
8. Test HTTP security/filter qua đúng server path.

MockWebServiceClient kiểm message processing nhưng không đủ xác minh HTTP header/wire transport. MockWebServiceServer kiểm client exchange nhưng không chứng minh server servlet xử lý header như production.

## 21. Chẩn đoán Content-Type và action

| Triệu chứng | Nguyên nhân có thể | Điều tra |
| --- | --- | --- |
| HTTP 415 | Unsupported Content-Type | Media type, factory, proxy |
| XML parse/version fault | Envelope namespace mismatch | SOAP version/message factory |
| Client gọi sai operation | Action mapping lệch | WSDL binding/endpoint mapping |
| Body QName đúng nhưng không match | Action mapping ưu tiên | PayloadRoot/SoapAction/Action |
| SOAP 1.2 bị coi là SOAP 1.1 | Client factory/sender sai | Content-Type và Envelope bytes |
| SOAPAction thiếu | HTTP sender config | Capture raw headers |
| Action parameter mất sau gateway | Proxy rewrite | Compare trước/sau proxy |
| wsa:Action khác HTTP action | Mapping hai lớp chưa rõ | Contract/policy |
| Charset lỗi dấu tiếng Việt | Header/bytes/XML declaration lệch | Capture bytes/decode |
| Fault parse fail | Response version/content type lệch | Fault namespace/structure |
| Local pass, partner fail | Partner stack/profile khác | Raw request/response |
| Duplicate action header | Proxy/client gửi nhiều giá trị | HTTP parser/policy |

Quy trình:
1. Capture raw HTTP request/response an toàn, loại credential.
2. Đọc method, URI, Content-Type đầy đủ.
3. Kiểm Envelope namespace từ body bytes.
4. Kiểm SOAPAction hoặc action parameter theo version.
5. Kiểm wsa:Action riêng trong SOAP Header.
6. So action với WSDL binding và endpoint mapping.
7. Xác định lỗi ở HTTP parser, message factory hay mapping.
8. Kiểm response Content-Type, Envelope và Fault.
9. So sánh đường trực tiếp và qua proxy nếu có.
10. Tạo regression fixture cho tổ hợp gây lỗi.

## 22. Ma trận 40 ca kiểm thử SOAP version, Content-Type và action

| Mã | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| A01 | SOAP 1.1 + text/xml + SOAPAction đúng | Dispatch đúng operation |
| A02 | SOAP 1.1 + SOAPAction empty theo contract | Empty-action behavior đúng |
| A03 | SOAP 1.1 thiếu SOAPAction | Reject hoặc theo profile |
| A04 | SOAP 1.1 + unknown SOAPAction | Không route nhầm |
| A05 | SOAP 1.1 + SOAPAction operation khác | Mapping mismatch phát hiện |
| A06 | SOAP 1.2 + application/soap+xml | Parse SOAP 1.2 |
| A07 | SOAP 1.2 + action parameter đúng | Action mapping đúng |
| A08 | SOAP 1.2 không action parameter | Behavior đúng khi optional |
| A09 | SOAP 1.2 + action unknown | Reject/Fault theo policy |
| A10 | SOAP 1.2 + SOAPAction, thiếu action parameter | Không giả định thay thế |
| A11 | SOAP 1.1 Envelope + application/soap+xml | Version/media mismatch reject |
| A12 | SOAP 1.2 Envelope + text/xml | Version/media mismatch reject |
| A13 | Content-Type 1.1, Envelope 1.2 | Factory xử lý mismatch đúng |
| A14 | Content-Type 1.2, Envelope 1.1 | Factory xử lý mismatch đúng |
| A15 | Content-Type unsupported | HTTP/message error đúng |
| A16 | Content-Type thiếu | Reject/default behavior rõ |
| A17 | Content-Type parameters đổi thứ tự | Parser không phụ thuộc order |
| A18 | UTF-8 header và bytes | Round-trip đúng |
| A19 | Charset header lệch bytes | Reject/behavior rõ |
| A20 | XML declaration lệch HTTP charset | Không mojibake |
| A21 | Payload tiếng Việt | Marshal/unmarshal đúng |
| A22 | SOAP 1.1 response Content-Type | Client nhận text/xml |
| A23 | SOAP 1.2 response Content-Type | Client nhận application/soap+xml |
| A24 | SOAP 1.1 Fault | Parse faultcode/faultstring/detail |
| A25 | SOAP 1.2 Fault | Parse Code/Reason/Detail |
| A26 | Fault HTTP status | Nhất quán binding/policy |
| A27 | wsa:Action đúng | WS-A mapping đúng |
| A28 | wsa:Action khác SOAPAction | Mapping hai lớp rõ |
| A29 | Thiếu wsa:Action bắt buộc | Reject/Fault đúng |
| A30 | Action đúng nhưng Body QName sai | Không dispatch sai |
| A31 | SOAPAction đúng nhưng WS-A sai | Không nhầm metadata |
| A32 | Hai action URI cùng value | Hai lớp xử lý độc lập |
| A33 | Server chỉ SOAP 1.1 nhận SOAP 1.2 | Reject rõ |
| A34 | Endpoint dual-version | Cả hai version đúng |
| A35 | SOAP qua reverse proxy | Header không bị rewrite |
| A36 | SOAP qua HTTPS | Header/body giữ nguyên |
| A37 | WSDL binding snapshot | Version/action đúng |
| A38 | Unsupported action | Không có business side effect |
| A39 | Duplicate/conflicting action header | Parser/policy xử lý rõ |
| A40 | Java và partner stacks | Interoperability đúng |

Negative cases phải assert cả status/Fault và side effect: request sai version/action không được gọi operation khác.

## 23. Bài tập: đối tác gửi sai action

**Bối cảnh:** Orders server publish binding SOAP 1.1 và 1.2. Đối tác gửi SOAP 1.1 Envelope nhưng Content-Type application/soap+xml; Body QName là GetOrderRequest, HTTP SOAPAction lại là CancelOrder. Client khác dùng SOAP 1.2 đúng media type nhưng wsa:Action khác URI trong action parameter.

**Yêu cầu:** phân loại lỗi theo lớp và lập test.

**Hướng giải quyết:**
1. Request thứ nhất có version/media mismatch; xác định parser/factory từ chối trước endpoint.
2. SOAPAction lại chỉ operation khác Body QName; nếu message parse được, mapping phải reject/route theo contract, không gọi nhầm CancelOrder.
3. Request thứ hai có SOAP 1.2 action và WS-Addressing Action khác nhau; kiểm WSDL/policy có quy định mapping không.
4. Nếu profile yêu cầu hai action đồng nhất, reject mismatch. Nếu hai lớp độc lập, test semantics đã công bố.
5. Capture raw HTTP headers/bytes.
6. Assert business service không được gọi cho mismatch.
7. Tạo positive fixtures SOAP 1.1/1.2.
8. Kiểm response version, Content-Type và Fault structure.
9. Chạy test qua reverse proxy nếu production có proxy.
10. Ghi regression case và partner interoperability result.

**Tiêu chí đạt:** media type, Envelope version và action metadata được kiểm theo binding; mismatch không gọi nhầm operation; client/server xử lý response/Fault đúng SOAP version.

## 24. Checklist phát hành ma trận SOAP 1.1/1.2

1. **Ghi rõ SOAP version/binding** của từng endpoint và WSDL port.
2. **SOAP 1.1 dùng text/xml** và kiểm SOAPAction theo binding.
3. **SOAP 1.2 dùng application/soap+xml** và kiểm action parameter nếu contract dùng.
4. **Kiểm Envelope namespace**, không dựa prefix hoặc Body QName.
5. **Tách SOAPAction, media-type action và wsa:Action** trong code/log/test.
6. **Không giả định ba action URI luôn bằng nhau**; document mapping.
7. **Kiểm empty/missing/unknown action** theo profile.
8. **Test mismatch** giữa Content-Type và Envelope.
9. **Kiểm charset header, XML declaration và bytes** nhất quán.
10. **Test response và SOAP Fault** đúng version.
11. **Kiểm endpoint mapping** không dispatch sai khi action và Body QName mâu thuẫn.
12. **Dùng HTTP wire integration** để capture headers và bytes.
13. **Dùng MockWebServiceClient/MockWebServiceServer** đúng giới hạn message-level.
14. **Kiểm WSDL binding** publish version/action đúng.
15. **Test WS-Addressing** riêng khi bật.
16. **Kiểm WSS signed parts** nếu action header cần integrity.
17. **Không dùng action để xác thực caller**.
18. **Test reverse proxy/gateway** không rewrite/drop Content-Type/action.
19. **Kiểm HTTPS/TLS** ở integration layer.
20. **Pin Spring-WS/SAAJ/JDK versions** và message factory config.
21. **Test Java và partner stack** theo contract.
22. **Assert không có business side effect** khi version/action invalid.
23. **Ghi expected HTTP status/Fault policy**, tránh hard-code theo assumption.
24. **Lưu fixture và test matrix** theo contract version.

**Kết luận:** Interoperability SOAP không chỉ phụ thuộc XML Body. SOAP 1.1 và SOAP 1.2 có Envelope namespace và HTTP media type khác nhau; action cũng nằm ở vị trí khác: SOAP 1.1 dùng SOAPAction header, SOAP 1.2 có action parameter trong application/soap+xml, còn WS-Addressing Action nằm trong SOAP Header. Spring-WS client/server cần dùng message factory và binding tương ứng, đồng thời test positive/negative combinations ở HTTP wire boundary. Khi version, Content-Type, action và Body QName được kiểm tra cùng nhau, hệ thống phát hiện sớm mismatch từ partner, proxy hoặc configuration mà không dispatch nhầm operation.
