# Action, To, MessageID, ReplyTo, FaultTo và RelatesTo

**WS-Addressing** bổ sung thông tin **địa chỉ, ý nghĩa và mối liên hệ giữa các thông điệp** vào SOAP Header. Thay vì chỉ nhìn địa chỉ HTTP nơi request được gửi tới, các bên tích hợp có thể biết request **muốn thực hiện hành động nào** (`Action`), **được gửi đến đâu** (`To`), **là thông điệp nào** (`MessageID`), **câu trả lời và lỗi cần được gửi tới đâu** (`ReplyTo`/`FaultTo`), và **một response đang trả lời thông điệp nào** (`RelatesTo`).

Bài học thuộc chương **WS-Addressing** của module `SPRING_WEB_SERVICES`. Trong kiến trúc **contract-first** sử dụng XSD/WSDL, JAXB, `@Endpoint` và `WebServiceTemplate`, WS-Addressing không thay payload nghiệp vụ: nó bổ sung metadata ở tầng SOAP để định tuyến và liên kết các trao đổi, nhất là khi có gateway, queue, callback bất đồng bộ hoặc hệ thống đối tác nhiều nền tảng. Các yếu tố SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích vẫn cần được tổ chức riêng nhưng phối hợp với chính sách addressing.

Bài sử dụng **WS-Addressing 1.0 (W3C, namespace `http://www.w3.org/2005/08/addressing`)** làm chuẩn minh họa chính, Spring-WS 4.1.x và Java 17+. **WS-Addressing August 2004** có namespace, một số cardinality/default và mô hình tương thích khác; không ghép header từ hai phiên bản trong một SOAP Envelope. Các đoạn Java mang tính cấu trúc ở nơi cần XSD-generated classes hoặc application beans.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc và giải thích sáu header `wsa:Action`, `wsa:To`, `wsa:MessageID`, `wsa:ReplyTo`, `wsa:FaultTo` và `wsa:RelatesTo`.
2. Phân biệt **WS-Addressing Action**, HTTP `SOAPAction`, payload QName và WS-Addressing reply action.
3. Giải thích `ReplyTo`/`FaultTo` chứa **Endpoint Reference (EPR)** chứ không chỉ là chuỗi URL tùy ý.
4. Mô tả luồng request → reply → fault, cách dùng `MessageID` và `RelatesTo` để correlation, bao gồm anonymous và non-anonymous replies.
5. Sử dụng `ActionCallback` trong Spring-WS client và `@Action`/`@Address` với `AnnotationActionEndpointMapping` ở server.
6. Tránh nhầm định danh thông điệp với **idempotency key** hoặc danh tính người dùng đã xác thực.
7. Nhận diện các rủi ro **SSRF**, callback injection, rò dữ liệu, sai namespace phiên bản và WS-Security/XML Signature.
8. Xây ma trận kiểm thử tương thích SOAP 1.1/1.2, WS-Addressing 1.0/2004, WSDL và client Java/.NET.

## 1. Vì sao SOAP cần WS-Addressing?

Một SOAP client có thể gửi request như sau:

~~~text
POST https://partner.example.test/ws/orders
Content-Type: application/soap+xml

SOAP Envelope
  Header: Action, To, MessageID, ReplyTo, FaultTo
  Body:   SubmitOrderRequest
~~~

**HTTP endpoint URL** nói về nơi vận chuyển message hiện tại. **WS-Addressing** thêm metadata cho message mà các SOAP intermediaries, gateways và processors có thể hiểu khi chuyển tiếp, trả lời hoặc phát Fault.

Ví dụ đối tác có một gateway nhận tất cả operation tại `/ws/orders`:

- `SubmitOrder` và `GetOrderStatus` đều được POST tới cùng URL.
- `wsa:Action` phân biệt ý nghĩa thông điệp; `wsa:To` định danh đích mà message nhắm tới.
- `wsa:MessageID` định danh request để bên nhận biết đây là message nào; response dùng `wsa:RelatesTo` để trỏ về nó.
- `wsa:ReplyTo` cho biết đích nhận response; `wsa:FaultTo` chọn đích cho Fault nếu có.
- Trong kịch bản đồng bộ thông thường, `ReplyTo=anonymous` cho phép response về **cùng HTTP request-response exchange**.

Nếu không dùng WS-Addressing, SOAP vẫn có thể thực hiện nhiều request-response qua SOAP Body, SOAPAction và WSDL binding. Vì vậy WS-Addressing là **lớp khả năng bổ sung**, cần được thống nhất với đối tác, không phải thuộc tính bắt buộc của mọi SOAP service.

### 1.1. Ba câu hỏi khác nhau của một SOAP call

| Câu hỏi | Đáp án do đâu cung cấp? | Ví dụ |
| --- | --- | --- |
| **Đang kết nối mạng tới đâu?** | Transport URL / message sender | `https://partner.example.test/ws/orders` |
| **Thông điệp nhắm đến đích logic nào?** | `wsa:To` | `https://partner.example.test/ws/orders` hoặc logical destination URI theo hợp đồng |
| **Thông điệp có nghĩa gì?** | `wsa:Action` (và payload/WSDL) | `urn:example:orders:v1:SubmitOrder` |

Trong ứng dụng đơn giản, transport URL và `wsa:To` có thể trùng nhau. Sau proxy/gateway, chúng có thể khác vì một bên là địa chỉ transport thực tế và bên kia là logical address được cấu hình. **Không** mặc nhiên coi khác nhau là hợp lệ hoặc bất hợp lệ: phải có routing/addressing policy và kiểm thử với gateway.

## 2. Sáu Message Addressing Properties cốt lõi

WS-Addressing 1.0 định nghĩa các **message addressing properties** trừu tượng rồi biểu diễn chúng thành SOAP Header.

| Header | Dữ liệu | Ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `wsa:Action` | IRI tuyệt đối | Nhận diện semantics/loại thông điệp | `urn:example:orders:v1:SubmitOrder` |
| `wsa:To` | IRI đích | Địa chỉ logic của message | `https://partner.example.test/ws/orders` |
| `wsa:MessageID` | IRI định danh | Định danh riêng của **message** | `urn:uuid:11111111-2222-4333-8444-555555555555` |
| `wsa:ReplyTo` | Endpoint Reference | Nơi nhận **reply thông thường** | EPR có Address là URI `anonymous` |
| `wsa:FaultTo` | Endpoint Reference | Nơi nhận **SOAP Fault** liên quan request | EPR có Address là callback URI |
| `wsa:RelatesTo` | IRI + `RelationshipType` | Message hiện tại liên quan một message trước | Response chứa MessageID của request |

### 2.1. Cardinality theo WS-Addressing 1.0

Phân biệt **thuộc tính trừu tượng** với **thẻ XML biểu diễn**:

- `Action` là thuộc tính **bắt buộc** của một addressed message; header `wsa:Action` thể hiện nó.
- `To` có thể **vắng mặt trong XML**; WS-Addressing 1.0 xác định default destination là URI `anonymous`. Trong trao đổi HTTP client-server thực tế, thường nên ghi `To` rõ ràng để dễ kiểm định routing và tương thích policy.
- `MessageID` là thuộc tính **tùy chọn** về cardinality, nhưng cần được cung cấp khi phải tạo một reply có `RelatesTo` theo mô hình WS-Addressing request/reply. Nhiều stack/policy bắt buộc `MessageID` trên mọi request-response; hãy làm theo binding và đối tác.
- `ReplyTo` có thể vắng trong SOAP Header; **reply endpoint mặc định** của 1.0 là EPR tại URI `anonymous`.
- `FaultTo` có thể vắng; với fault response, cơ chế chọn đích sẽ dùng `FaultTo` nếu có, nếu không dùng reply endpoint theo quy tắc chuẩn.
- `RelatesTo` là thuộc tính có thể lặp để mô tả quan hệ với nhiều thông điệp; với **reply thông thường**, cần liên kết request đã tạo reply bằng `RelatesTo` khi tham gia WS-Addressing reply MEP.

**Không ghi nhớ máy móc** rằng tất cả sáu header đều luôn phải xuất hiện. WSDL metadata, WS-Addressing version, message exchange pattern (MEP), gateway/security policy và quy tắc của đối tác quyết định những trường nào bắt buộc trong một trường hợp cụ thể.

### 2.2. Đây là các IRI, không phải tên Java method

Một `Action` hợp lệ là định danh IRI có ý nghĩa trong hợp đồng, ví dụ:

~~~text
urn:example:orders:v1:SubmitOrder
~~~

Không nên dùng `"submitOrder"` không có namespace/version trong một hợp đồng liên tổ chức dài hạn. Cũng không suy ra Action từ local part `SubmitOrderRequest` nếu WSDL đã công bố URI khác. Giá trị `Action` được so sánh như identifier theo quy tắc chuẩn, **không phải URL bắt buộc phải truy cập được qua HTTP**.

## 3. Ví dụ SOAP request có Action, To, MessageID, ReplyTo, FaultTo

Request SOAP 1.2 gửi thao tác `SubmitOrder`, muốn nhận reply và fault trên **cùng HTTP exchange**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <s:Header>
    <wsa:Action s:mustUnderstand="true">urn:example:orders:v1:SubmitOrder</wsa:Action>
    <wsa:To s:mustUnderstand="true">https://partner.example.test/ws/orders</wsa:To>
    <wsa:MessageID>urn:uuid:11111111-2222-4333-8444-555555555555</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsa:FaultTo>
      <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
    </wsa:FaultTo>
  </s:Header>
  <s:Body>
    <ord:SubmitOrderRequest>
      <ord:requestId>REQ-01</ord:requestId>
      <ord:orderId>ORD-42</ord:orderId>
    </ord:SubmitOrderRequest>
  </s:Body>
</s:Envelope>
~~~

Đây là **XML minh họa WS-Addressing**, giả định XSD `SubmitOrderRequest` chứa hai trường `requestId`, `orderId` theo thứ tự đang dùng. Schema này cần được định nghĩa trong ứng dụng; XML không tự trở thành contract nếu chưa có XSD/WSDL. Giá trị IRI trong các header được viết **trên một dòng** để tránh whitespace ngoài ý muốn trong simple content; trong ứng dụng thật nên dùng serializer của framework.

**`s:mustUnderstand="true"`** là thuộc tính của SOAP 1.2. Nó yêu cầu SOAP node ở role tương ứng phải hiểu/xử lý header; việc tự bật nó mà server không cấu hình WS-Addressing có thể dẫn đến `MustUnderstand` fault. Với SOAP 1.1, namespace Envelope và giá trị/biểu diễn của thuộc tính `mustUnderstand` khác. **Không** trộn SOAP 1.1 Envelope với quy tắc 1.2.

### 3.1. Đâu là payload, đâu là metadata?

~~~text
SOAP Envelope
├── Header
│   ├── wsa:Action        → định danh intent / message type
│   ├── wsa:To            → destination URI
│   ├── wsa:MessageID     → ID của request message
│   ├── wsa:ReplyTo       → EPR của normal response
│   └── wsa:FaultTo       → EPR của fault
└── Body
    └── ord:SubmitOrderRequest
        ├── requestId     → idempotency key nghiệp vụ
        └── orderId       → dữ liệu nghiệp vụ
~~~

**Điểm then chốt:** `wsa:MessageID` (định danh message) và `ord:requestId` (định danh ý định nghiệp vụ dùng chống trùng nếu có) giải quyết **hai bài toán khác nhau**. Một request có thể được gửi lại với MessageID mới mà vẫn thể hiện cùng một ý định nghiệp vụ.

## 4. Action: loại thông điệp, không phải HTTP URL

`wsa:Action` là absolute IRI **xác định semantics** của message. Ví dụ hợp đồng có thể công bố:

| Message | WS-Addressing Action |
| --- | --- |
| Input `SubmitOrderRequest` | `urn:example:orders:v1:SubmitOrder` |
| Output `SubmitOrderResponse` | `urn:example:orders:v1:SubmitOrderResponse` |
| Fault `OrderFault` | `urn:example:orders:v1:OrderFault` |

Đây là **giá trị do hợp đồng lựa chọn**, không phải quy tắc mọi WSDL đều sử dụng các suffix này. Action của input, output và fault có thể khác nhau; đừng mặc định client gửi cùng một Action ở mọi message của MEP.

### 4.1. Ba khái niệm dễ bị đồng nhất

| Thành phần | Vị trí | Ý nghĩa |
| --- | --- | --- |
| `wsa:Action` | XML SOAP Header, QName `{http://www.w3.org/2005/08/addressing}Action` | Semantics của message WS-Addressing |
| HTTP `SOAPAction` | HTTP header trong SOAP 1.1 binding | Intent/action hint ở transport; có quy tắc đồng bộ với WS-A |
| Payload root QName | Phần tử gốc trong SOAP Body | Đối tượng XML contract-first mà adapter/JAXB đọc |

Một server Spring-WS có thể định tuyến qua `@PayloadRoot`, `@SoapAction` hoặc `@Action` tùy `EndpointMapping` và thứ tự được cấu hình. **Có cùng `wsa:Action` chưa chứng minh payload hợp XSD**; ngược lại, **payload hợp QName** chưa chứng minh WS-Addressing Action phù hợp WSDL.

### 4.2. SOAP 1.1 HTTP SOAPAction và wsa:Action

Theo **WS-Addressing 1.0 SOAP Binding**, khi dùng **SOAP 1.1/HTTP** với WS-Addressing:

- HTTP `SOAPAction` field phải tồn tại theo binding.
- Giá trị được phép là **`wsa:Action` trong dấu ngoặc kép** hoặc **chuỗi rỗng `""`** theo điều kiện đặc tả.
- Một `SOAPAction` khác `wsa:Action` không đáp ứng binding và có thể gây `ActionMismatch`/`InvalidAddressingHeader` Fault.

Do đó không giả định “HTTP SOAPAction và wsa:Action có thể đặt tùy ý khác nhau”; nếu WSDL/đối tác chọn chính sách 1.0 binding, phải tuân thủ nó. Với SOAP 1.2/HTTP, action thường được thể hiện trong `Content-Type: application/soap+xml` qua parameter `action` theo SOAP binding; nên kiểm tra policy và mức nhất quán với `wsa:Action`.

### 4.3. Action dùng cho endpoint mapping

Ở server Spring-WS, `AnnotationActionEndpointMapping` có thể chọn method qua `@Action`. Bất đồng `Action` giữa client, gateway và endpoint có thể khiến **không tìm được handler** dù XML Body hợp lệ. Hãy kiểm tra URI của input message được WSDL công bố, namespace WS-A và mapping `@Action` trước khi đổ lỗi cho JAXB.

## 5. To: nơi message muốn tới

`wsa:To` là **destination property** của addressed message:

~~~xml
<wsa:To xmlns:wsa="http://www.w3.org/2005/08/addressing">
  https://partner.example.test/ws/orders
</wsa:To>
~~~

Một client Spring-WS dùng `ActionCallback` thường để `To` phản ánh **URI của connection** nếu không chỉ định khác. Tuy nhiên, WS-Addressing là mô hình transport-neutral: trong hệ thống có reverse proxy hoặc gateway, `To` cũng có thể là một URI logic theo policy của đối tác.

### 5.1. To không phải ReplyTo hay transport URL

~~~mermaid
flowchart LR
    C["Client HTTP sender"] -->|"POST /ws/orders"| G["SOAP Gateway"]
    G -->|"Forward theo policy"| S["Order service"]
    C -. "wsa:To = URI logic" .-> G
    G -. "Destination validation" .-> S
~~~

- **Transport URI:** nơi sender thực sự mở kết nối.
- **`wsa:To`:** đích mà message khẳng định đang nhắm tới.
- **`wsa:ReplyTo`:** nơi nhận **reply**, không phải đích request.
- **`wsa:FaultTo`:** nơi nhận **fault**, có thể khác `ReplyTo`.

Nếu client gửi HTTP đến gateway A nhưng `wsa:To` lại chỉ backend B, điều đó **chỉ hợp lệ khi gateway và backend có thỏa thuận routing rõ**. Đừng tự thay `To` để vượt address validation.

### 5.2. Vì sao To cần được kiểm tra chính sách?

Một request không đáng tin có thể đưa `wsa:To` đến hostname ngoài hệ thống, hoặc dùng giá trị gây confusion giữa gateway và endpoint. Hãy xác minh target URI thuộc phạm vi service được phép, đối chiếu routing contract/`@Address` nếu dùng, và tránh cho các thành phần khác tự mở kết nối mới tới URI chưa được kiểm duyệt.

WS-Addressing 1.0 định nghĩa `To` **tùy chọn trên wire** với default destination anonymous khi vắng. Nhưng trong những hệ thống cần match địa chỉ cụ thể, vắng `To` có thể bị policy từ chối. **“Optional theo syntax” không đồng nghĩa “service đối tác bắt buộc phải chấp nhận”.**

## 6. MessageID: định danh một message, không tự chống trùng nghiệp vụ

Ví dụ:

~~~xml
<wsa:MessageID xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:11111111-2222-4333-8444-555555555555
</wsa:MessageID>
~~~

Giá trị là một **absolute IRI**, thường dùng `urn:uuid:...`. Khi có MessageID, bên gửi chịu trách nhiệm tạo ID duy nhất cho mỗi message theo chính sách WS-Addressing. Khi một phản hồi cần tương quan tới request, response đặt request MessageID trong `RelatesTo`.

### 6.1. MessageID và requestId không thay nhau

| Khái niệm | `wsa:MessageID` | Business `requestId` |
| --- | --- | --- |
| Cấp giao thức | WS-Addressing SOAP Header | XML Body / application contract |
| Định danh | Một message instance/identity | Một **ý định nghiệp vụ** |
| Tự tạo uniqueness | Client/message-id strategy | Client + DB unique constraint theo policy |
| Dùng để nối response | `wsa:RelatesTo` | Có thể dùng query idempotency status |
| Có bảo đảm exactly-once không? | **Không** | **Cũng không tự động**, cần server-side enforcement |
| Có thể thay khi retry? | Theo chính sách retransmission; spec cho phép retransmission cùng MessageID | Nên **giữ nguyên cho cùng ý định** |

WS-Addressing 1.0 **không định nghĩa behavior của receiver** khi hai messages có cùng MessageID theo cách đủ để bảo đảm nghiệp vụ exactly-once. Đừng dùng `MessageID` làm “khóa duy nhất tuyệt đối” của đơn hàng nếu đối tác chưa thống nhất chính sách duplicate detection và persistence.

### 6.2. Retry, timeout và kết quả không rõ

Giả sử `SubmitOrder` commit DB nhưng response thất lạc:

~~~text
Request A: wsa:MessageID = urn:uuid:A
           Body.requestId  = REQ-01
Server:    Commit order ORD-42
Network:   Response lost
Client:    Timeout
Retry B:   wsa:MessageID = urn:uuid:B  (có thể là message mới)
           Body.requestId  = REQ-01   (giữ ý định cũ)
~~~

Server phải có idempotency storage/unique constraint cho `REQ-01` theo business identity để tránh tạo thêm order, bất kể retry dùng lại hay đổi WS-Addressing MessageID. Một implementation có thể chọn giữ MessageID khi retransmission để phục vụ giao thức; chính sách đó **không thay thế** kho deduplication nghiệp vụ.

## 7. ReplyTo: Endpoint Reference của normal response

`wsa:ReplyTo` không phải text URL đơn:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
</wsa:ReplyTo>
~~~

Nó là **Endpoint Reference (EPR)**. EPR có `Address`, và tùy mô hình có thể chứa **reference parameters** để nhận diện resource/instance logic ở đích. Trong Spring-WS, `org.springframework.ws.soap.addressing.core.EndpointReference` biểu diễn EPR; không nên tự biến nó thành một String duy nhất rồi bỏ qua reference parameters nếu hợp đồng cần chúng.

### 7.1. Anonymous: trả về cùng request-response exchange

WS-Addressing 1.0 xác định địa chỉ:

~~~text
http://www.w3.org/2005/08/addressing/anonymous
~~~

Với SOAP request-response thông dụng trên HTTP, `ReplyTo=anonymous` ngụ ý sử dụng cùng kênh HTTP response cho reply. Khi `ReplyTo` vắng trong WS-A 1.0, default của reply endpoint là EPR có Address `anonymous`. Điều này phù hợp các SOAP client đồng bộ dùng `WebServiceTemplate.marshalSendAndReceive(...)`.

**Anonymous không có nghĩa là HTTP URL `/anonymous`**. Đó là một **well-known IRI mang semantics** do WS-Addressing định nghĩa, không phải đích có thể POST tùy tiện.

### 7.2. Non-anonymous: có thể chuyển reply qua kênh khác

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>https://client.example.test/callback/orders</wsa:Address>
</wsa:ReplyTo>
~~~

Đây là đích nhận response độc lập. Nếu binding/partner hỗ trợ **out-of-band reply**, server có thể gửi SOAP response tới callback URI qua một exchange mới. Nhưng **việc gửi Header không tự tạo callback server**:

- Client phải có endpoint HTTPS nhận callback, xác thực bên gửi và parse SOAP.
- Server phải có message sender/phương thức gửi phù hợp.
- Message exchange pattern/WSDL và timeout/callback policy phải cho phép.
- Response thường mang `RelatesTo` để client ghép với request cũ.
- Phải có durable correlation state nếu callback tới sau hoặc service restart.
- Không mặc định `marshalSendAndReceive(...)` của client sẽ nhận callback qua connection ban đầu.

**Không dùng ReplyTo như URL do caller tự chọn rồi server tự POST tới**, nếu chưa có kiểm soát security; đó là nguy cơ **SSRF** nghiêm trọng (xem mục 14.2).

### 7.3. WS-Addressing none khác anonymous

WS-A 1.0 còn có IRI:

~~~text
http://www.w3.org/2005/08/addressing/none
~~~

`none` diễn tả một EPR không nhận message theo quy tắc gửi đến EPR. Nó **không đồng nghĩa** `anonymous`; `anonymous` dùng kênh phù hợp của message exchange. Nếu hợp đồng cần no-response/one-way hoặc suppress callback, cần thiết kế đúng MEP và `none` semantics thay vì chỉ thay URI theo cảm tính.


## 8. FaultTo: nơi nhận lỗi SOAP

`wsa:FaultTo` là **Endpoint Reference (EPR)** được dùng cho Fault liên quan đến request:

~~~xml
<wsa:FaultTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>https://client.example.test/callback/faults</wsa:Address>
</wsa:FaultTo>
~~~

Ví dụ, một tích hợp muốn normal reply về `/callback/orders` nhưng SOAP Fault về `/callback/faults`. `ReplyTo` và `FaultTo` có thể khác nhau; hai đích này phải được kiểm soát an toàn và server cần có khả năng **out-of-band messaging**.

### 8.1. Chọn destination cho reply và fault

Theo WS-Addressing 1.0:

- Với **normal reply**, chọn `ReplyTo` EPR; nếu không có header `ReplyTo`, default là `anonymous`.
- Với **fault reply**, chọn `FaultTo` EPR nếu có; nếu không, fallback sang reply endpoint theo quy tắc Core.
- Với `anonymous` trên HTTP request-response thích hợp, reply/fault có thể về **cùng HTTP exchange**.
- Với **non-anonymous** address, cần kênh gửi khác nếu binding hỗ trợ; không mặc nhiên rằng mọi Spring-WS application hỗ trợ callback.
- `none` không phải một HTTP URL để POST; gửi tới EPR `none` có semantics không phát message theo Core.

`FaultTo` chỉ chỉ định **đích nhận Fault**, không chọn `Sender`/`Receiver` hoặc `Client`/`Server` fault code. Mã lỗi, nguyên nhân, detail, destination, security policy là những quyết định khác nhau.

### 8.2. Action dành cho Fault

Với WS-Addressing 1.0 SOAP Binding, một action định danh WS-Addressing Fault là:

~~~text
http://www.w3.org/2005/08/addressing/fault
~~~

Các SOAP-defined faults và application-defined faults có thể dùng Action riêng theo đặc tả/WSDL. Đừng tự gắn cùng một Action cho mọi fault nếu đối tác công bố chính sách khác. Fault response vẫn nên liên kết request bằng `RelatesTo` khi được tạo theo WS-A reply rules.

## 9. RelatesTo: nối reply/fault với request

`wsa:RelatesTo` cho biết **message hiện tại liên quan tới message nào trước đó**. Một reply thường chứa:

~~~xml
<wsa:RelatesTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:11111111-2222-4333-8444-555555555555
</wsa:RelatesTo>
~~~

Đó là `MessageID` của **request gốc**, không phải MessageID mới của reply và không phải business requestId.

### 9.1. Ba loại ID riêng biệt

| Trường | Request | Reply |
| --- | --- | --- |
| `wsa:Action` | `...:SubmitOrder` | `...:SubmitOrderResponse` |
| `wsa:MessageID` | `urn:uuid:11111111-2222-4333-8444-555555555555` | Có thể có `urn:uuid:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee` |
| `wsa:RelatesTo` | Thường vắng | `urn:uuid:11111111-2222-4333-8444-555555555555` |
| Body `requestId` | `REQ-01` | Có thể echo `REQ-01` |
| Body `orderId` | Dữ liệu lệnh | Kết quả nghiệp vụ |

SOAP 1.2 reply mẫu:

~~~xml
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <s:Header>
    <wsa:Action>urn:example:orders:v1:SubmitOrderResponse</wsa:Action>
    <wsa:To>http://www.w3.org/2005/08/addressing/anonymous</wsa:To>
    <wsa:MessageID>urn:uuid:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee</wsa:MessageID>
    <wsa:RelatesTo>urn:uuid:11111111-2222-4333-8444-555555555555</wsa:RelatesTo>
  </s:Header>
  <s:Body>
    <ord:SubmitOrderResponse>
      <ord:requestId>REQ-01</ord:requestId>
      <ord:orderId>ORD-42</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
    </ord:SubmitOrderResponse>
  </s:Body>
</s:Envelope>
~~~

`wsa:To=anonymous` trong reply này phù hợp request-response dùng cùng HTTP exchange. Với ReplyTo non-anonymous, To của reply thường mang địa chỉ callback. MessageID của reply, nếu có, **là ID mới**; `RelatesTo` giữ ID request.

### 9.2. RelationshipType theo WS-A 1.0

~~~xml
<wsa:RelatesTo
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    RelationshipType="http://www.w3.org/2005/08/addressing/reply">
  urn:uuid:11111111-2222-4333-8444-555555555555
</wsa:RelatesTo>
~~~

`RelationshipType` của WS-Addressing 1.0 là **absolute IRI**; vắng thuộc tính nghĩa là relationship type mặc định `http://www.w3.org/2005/08/addressing/reply`. Một message có thể có nhiều `RelatesTo` nếu cần chỉ ra các loại quan hệ khác.

**Đừng dùng** `RelationshipType="wsa:Reply"` kiểu QName của August 2004 cho một message WS-A 1.0.

### 9.3. Callback có thể về khác thứ tự

~~~mermaid
sequenceDiagram
    participant C as Callback receiver
    participant S as SOAP Partner
    C->>S: A MessageID=A
    C->>S: B MessageID=B
    C->>S: C MessageID=C
    S-->>C: Reply C RelatesTo=C
    S-->>C: Fault B RelatesTo=B
    S-->>C: Reply A RelatesTo=A
~~~

Các chữ A/B/C trong sơ đồ chỉ là **ký hiệu**, không phải URI để gửi trên wire. Client cần correlation store `MessageID → trạng thái request`, TTL, deduplication, xử lý unknown IDs và khả năng phục hồi sau restart. `RelatesTo` không tự xác thực người gửi callback; phải dùng TLS/mTLS/WS-Security và policy riêng.

## 10. Luồng request-response đồng bộ và bất đồng bộ

### 10.1. ReplyTo và FaultTo anonymous

~~~mermaid
sequenceDiagram
    participant C as WebServiceTemplate
    participant S as Spring-WS Server
    C->>S: Request Action=SubmitOrder, MessageID=req-1
    Note over C,S: ReplyTo=anonymous / FaultTo=anonymous
    alt Thành công
        S-->>C: HTTP SOAP Reply / RelatesTo=req-1
    else Lỗi
        S-->>C: HTTP SOAP Fault / RelatesTo=req-1
    end
~~~

Đây là mô hình phù hợp `WebServiceTemplate.marshalSendAndReceive(...)`: client nhận response qua cùng HTTP exchange.

### 10.2. Out-of-band response và fault

~~~mermaid
sequenceDiagram
    participant C as SOAP Client sender
    participant S as SOAP Server
    participant R as Reply callback
    participant F as Fault callback
    C->>S: Request / MessageID=req-1
    Note over C,S: ReplyTo=R / FaultTo=F
    S-->>C: Transport acknowledgment nếu binding cho phép
    alt Thành công
        S->>R: SOAP Reply / RelatesTo=req-1
        R-->>S: Transport acknowledgment
    else Lỗi
        S->>F: SOAP Fault / RelatesTo=req-1
        F-->>S: Transport acknowledgment
    end
~~~

HTTP acknowledgment ban đầu **không tương đương `SubmitOrderResponse`**. Cần receiver riêng, bảo mật callback, durable state, khả năng retry/idempotent consumer và agreement về MEP. Một client chờ đồng bộ trên `marshalSendAndReceive` không tự nhận được callback được gửi sau bằng HTTP request khác.

### 10.3. Correlation không phải exactly-once

`MessageID`/`RelatesTo` giúp liên kết messages, không phải cơ chế giao dịch hoặc exactly-once. Với `SubmitOrder` có side effect, cần business `requestId` + unique constraint, outbox/workflow và retry có giới hạn. Không sinh requestId nghiệp vụ mới mỗi khi client thấy timeout.


## 11. Spring-WS client: `ActionCallback`

Spring-WS cung cấp `org.springframework.ws.soap.addressing.client.ActionCallback`, một `WebServiceMessageCallback` đặt WS-Addressing headers. API hỗ trợ constructors cho `Action`, `AddressingVersion`, `To` và setter cho `ReplyTo`/`FaultTo` và chiến lược sinh `MessageID`.

### 11.1. Gửi request đồng bộ với ActionCallback

Giả sử đã có JAXB classes từ XSD và bean `WebServiceTemplate` cấu hình `Jaxb2Marshaller`:

~~~java
import java.net.URI;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

public final class OrdersSoapClient {
    private final WebServiceTemplate template;

    public OrdersSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object submit(SubmitOrderRequest request) {
        URI endpoint = URI.create(
            "https://partner.example.test/ws/orders");
        URI action = URI.create(
            "urn:example:orders:v1:SubmitOrder");

        ActionCallback addressing = new ActionCallback(
            action, new Addressing10(), endpoint);

        return template.marshalSendAndReceive(
            endpoint.toString(),
            request,
            addressing);
    }
}
~~~

`SubmitOrderRequest` được giả định là JAXB root hoặc `JAXBElement` được binding hỗ trợ. `WebServiceTemplate` phải có marshaller/unmarshaller/sender thích hợp và ứng dụng cần xử lý SOAP Fault, timeout riêng. Constructor `ActionCallback(URI, AddressingVersion, URI)` thuộc Spring-WS 4.1.x. Nếu không chỉ định `To`, callback mặc định dùng **connection URI**; khi không truyền `AddressingVersion`, mặc định là `Addressing10`.

Không nhầm:

- `ActionCallback` (package `soap.addressing.client`) tạo WS-Addressing message headers.
- `SoapActionCallback` (package `soap.client.core`) đặt SOAPAction ở lớp SOAP transport.
- Với SOAP 1.1 và WS-Addressing 1.0, `SOAPAction` HTTP header có ràng buộc với `wsa:Action`. Cần kiểm tra header thực trên wire trong cấu hình sender/message factory của dự án.

### 11.2. Chọn ReplyTo và FaultTo bằng EndpointReference

~~~java
import java.net.URI;

import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.core.EndpointReference;
import org.springframework.ws.soap.addressing.version.Addressing10;

URI action = URI.create("urn:example:orders:v1:SubmitOrder");
URI to = URI.create("https://partner.example.test/ws/orders");

ActionCallback callback = new ActionCallback(
    action, new Addressing10(), to);

// Chỉ khi đã thiết kế out-of-band MEP và receiver:
callback.setReplyTo(new EndpointReference(
    URI.create("https://client.example.test/callback/orders")));
callback.setFaultTo(new EndpointReference(
    URI.create("https://client.example.test/callback/faults")));
~~~

`EndpointReference(URI)` là constructor tạo EPR với address; nếu đối tác sử dụng reference parameters hoặc metadata, phải sử dụng binding EPR phù hợp để không làm mất chúng. Những URLs chỉ là ví dụ.

**Không** bật non-anonymous `ReplyTo` chỉ vì API có setter. Server phải có message sender/transport cho reply khác kênh; client cần endpoint HTTPS nhận callback, xác thực người gửi và lưu trạng thái correlation bền vững nếu cần.

### 11.3. MessageID strategy

`ActionCallback` có `setMessageIdStrategy(MessageIdStrategy)`; mặc định Spring-WS dùng `UuidMessageIdStrategy`. Điều đó tạo định danh message thuận tiện cho correlation, **không** tạo idempotency key nghiệp vụ.

Một custom strategy phục vụ kiểm thử/đối tác phải đảm bảo tính duy nhất, format IRI và thread safety; không dùng MessageID cố định cho mọi invocation. Callback có setter là mutable, vì vậy nên **tạo callback theo mỗi lần gọi** thay vì cho các threads thay đổi `ReplyTo`/`FaultTo` của cùng một object.

## 12. Spring-WS server: `@Action` và `@Address`

`org.springframework.ws.soap.addressing.server.AnnotationActionEndpointMapping` chọn endpoint method theo `wsa:Action`. Một endpoint có thể dùng:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;
import org.springframework.ws.soap.addressing.server.annotation.Address;

@Endpoint
@Address("https://partner.example.test/ws/orders")
public class SubmitOrderEndpoint {
    private final SubmitOrderUseCase useCase;

    public SubmitOrderEndpoint(SubmitOrderUseCase useCase) {
        this.useCase = useCase;
    }

    @Action(
        value = "urn:example:orders:v1:SubmitOrder",
        output = "urn:example:orders:v1:SubmitOrderResponse",
        fault = "urn:example:orders:v1:OrderFault")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        return useCase.submitSoap(request);
    }
}
~~~

`SubmitOrderUseCase`, `submitSoap` và JAXB classes là kiểu ứng dụng minh họa; endpoint production nên map JAXB → application command → transactional use case → response DTO. `@Action.value` là **input Action**; `output` và `fault` là Actions của response/fault nếu mapping phát chúng.

`@Address` trên class, nếu được khai báo, dùng để đối chiếu **WS-Addressing destination/`To`**, **không** phải Spring MVC servlet URL mapping. Khi deploy qua gateway/reverse proxy, cần thống nhất địa chỉ logic/transport để `To` khớp policy.

### 12.1. Điều kiện để @Action hoạt động

Chỉ gắn annotation **không bảo đảm** dispatcher đã sử dụng nó. Spring-WS phải có `AnnotationActionEndpointMapping`/hạ tầng WS-Addressing phù hợp. Cấu hình phụ thuộc cách setup `@EnableWs`, message dispatcher, Spring Boot và bean mappings; cần kiểm tra trong test context.

Nếu ứng dụng đồng thời có `@PayloadRoot` hoặc `@SoapAction` handlers, phải review **thứ tự EndpointMapping** và xung đột định tuyến. Mapping chọn method từ addressing headers; `EndpointAdapter`/JAXB vẫn đọc Body theo hợp đồng. Một `Action` đúng chưa chứng minh Body có QName và nội dung hợp lệ.

~~~text
SOAP Header wsa:Action, wsa:To
      │
      ▼
AnnotationActionEndpointMapping    ← chọn method
      │
      ▼
EndpointAdapter / JAXB/OXM         ← XML Body → Java contract DTO
      │
      ▼
@Endpoint                         ← mapper → application service
      │
      ▼
JAXB response / SOAP Fault         ← response action, RelatesTo
~~~

### 12.2. Đọc properties qua API có kiểu

Spring-WS `AddressingVersion` có API đọc `MessageAddressingProperties` từ `SoapMessage`:

~~~java
import java.net.URI;

import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.addressing.core.EndpointReference;
import org.springframework.ws.soap.addressing.core.MessageAddressingProperties;
import org.springframework.ws.soap.addressing.version.Addressing10;
import org.springframework.ws.soap.addressing.version.AddressingVersion;

// Giả định soapMessage lấy từ đúng lượt xử lý WS-A 1.0:
AddressingVersion version = new Addressing10();
MessageAddressingProperties props =
    version.getMessageAddressingProperties(soapMessage);

URI action = props.getAction();
URI to = props.getTo();
URI messageId = props.getMessageId();
EndpointReference replyTo = props.getReplyTo();
EndpointReference faultTo = props.getFaultTo();
URI relatesTo = props.getRelatesTo();
~~~

Đây là **fragment minh họa** trong class/method đã có `soapMessage`, không phải Java top-level code độc lập. `getRelatesTo()` của `MessageAddressingProperties` biểu diễn mối liên hệ reply được abstraction này hỗ trợ; WS-A 1.0 cho phép nhiều relationships nên nếu ứng dụng phải xử lý toàn bộ quan hệ mở rộng, hãy kiểm tra XML/binding model tương ứng.

Không dùng `wsa:ReplyTo` như chuỗi URL đọc từ XML rồi gửi trực tiếp bằng HTTP client: EPR và policy gửi cần được kiểm tra riêng.

## 13. WSDL/WS-Policy: công bố message actions

Contract-first gồm nhiều lớp:

| Lớp | Xác định điều gì? |
| --- | --- |
| XSD | Payload `SubmitOrderRequest/SubmitOrderResponse`, fault detail data |
| WSDL | Operation, input/output/fault, SOAP binding và endpoint |
| WS-Addressing Metadata | `Action` của từng input/output/fault |
| WS-Policy và thỏa thuận đối tác | Bắt buộc WS-Addressing, anonymous/non-anonymous policy, security |
| Spring-WS runtime | `@Action`/`ActionCallback`/mappings/interceptors/senders |

Theo W3C WS-Addressing 1.0 Metadata, WSDL 1.1 có thể dùng `wsam:Action` trong namespace `http://www.w3.org/2007/05/addressing/metadata`:

~~~xml
<!-- Fragment WSDL 1.1; tns và messages được định nghĩa bên ngoài. -->
<wsdl:operation name="SubmitOrder"
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:wsam="http://www.w3.org/2007/05/addressing/metadata">
  <wsdl:input message="tns:SubmitOrderInput"
              wsam:Action="urn:example:orders:v1:SubmitOrder"/>
  <wsdl:output message="tns:SubmitOrderOutput"
               wsam:Action="urn:example:orders:v1:SubmitOrderResponse"/>
  <wsdl:fault name="OrderFault"
              message="tns:OrderFaultMessage"
              wsam:Action="urn:example:orders:v1:OrderFault"/>
</wsdl:operation>
~~~

Đây **không phải WSDL hoàn chỉnh**; `tns` và các `wsdl:message`, `wsdl:types`/XSD, binding/service/port phải được khai báo. `wsam:Action` là metadata; **chỉ khai báo nó không tự yêu cầu mọi client gửi WS-A headers**. Yêu cầu bắt buộc cần một WS-Policy/addressing assertion hoặc thỏa thuận tương đương.

### 13.1. Không tự đoán Action từ tên Java method

W3C Metadata có quy tắc **default Action** khi không khai báo rõ; chuỗi có thể phụ thuộc targetNamespace, portType và message labels. Không nên tự suy ra một giá trị từ `SubmitOrderRequest` hay `submit` rồi coi đó là WSDL contract.

Kiểm tra WSDL đã công bố, so `wsam:Action` input/output/fault với `@Action` và headers trên wire. Với SOAP 1.1, kiểm tra thêm HTTP SOAPAction và `soap:operation/@soapAction` binding.

### 13.2. WS-Addressing 1.0 và August 2004 là hai phiên bản khác nhau

| Yếu tố | WS-A 1.0 | August 2004 |
| --- | --- | --- |
| Namespace | `http://www.w3.org/2005/08/addressing` | `http://schemas.xmlsoap.org/ws/2004/08/addressing` |
| Anonymous URI | `http://www.w3.org/2005/08/addressing/anonymous` | `http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous` |
| `RelatesTo/@RelationshipType` | Absolute IRI, mặc định `.../reply` | QName, mặc định `wsa:Reply` |
| Header cardinality/default | Theo WS-A Core 1.0 + MEP | Theo submission 2004/08 |
| Spring-WS version class | `Addressing10` | `Addressing200408` |

Không đổi phiên bản chỉ bằng cách sửa prefix `wsa` hoặc dán một namespace mới: cần đúng class `AddressingVersion`, anonymous URI, relationship type, MEP/binding semantics và các tests. `AnnotationActionEndpointMapping` có thể hỗ trợ nhiều versions theo cấu hình nhưng đối tác có thể chỉ hỗ trợ một.


## 14. Lỗi WS-Addressing, bảo mật và nội dung có thể công bố

### 14.1. Các lỗi addressing quan trọng

WS-Addressing 1.0 SOAP Binding định nghĩa những fault conditions riêng cho Addressing properties, có thể được biểu diễn thành SOAP Fault 1.1 hoặc SOAP Fault 1.2 tùy binding:

| Tình huống | Nguyên nhân | Cách chẩn đoán an toàn |
| --- | --- | --- |
| Thiếu header bắt buộc theo binding/MEP | `Action` hoặc metadata cần thiết vắng | Kiểm WSDL policy/headers, không chỉ payload |
| `InvalidAddressingHeader` | Header sai cấu trúc/giá trị | So namespace WS-A, kiểu EPR, duplicate headers |
| `ActionMismatch` | `wsa:Action` không nhất quán với SOAPAction theo binding | So SOAPAction HTTP với wsa:Action thực |
| `InvalidCardinality` | Có nhiều header vượt cardinality | Kiểm `Action`/`To`/`MessageID` trùng |
| `DuplicateMessageID` | MessageID bị xử lý là trùng theo addressing policy | Không suy thành idempotency nghiệp vụ |
| `MessageAddressingHeaderRequired` | Thiếu property được yêu cầu | Kiểm MEP, `ReplyTo`, `MessageID` |
| `OnlyAnonymousAddressSupported` | Server chỉ hỗ trợ anonymous reply endpoint | Dùng ReplyTo anonymous hoặc đổi binding |
| `OnlyNonAnonymousAddressSupported` | Profile chỉ hỗ trợ callback ngoài kênh | Cần receiver và chính sách callback |
| Action đúng nhưng payload QName sai | Mismatch hợp đồng XML | XSD/JAXB validation; không chỉ lỗi WS-A |
| `wsa:To` không khớp địa chỉ endpoint | Đích logic sai | Kiểm `@Address`/gateway routing |
| WS-A 1.0 client gửi namespace 2004 | Hai phiên bản khác nhau | Chọn `AddressingVersion` đúng |

Không phải mọi trường hợp sẽ tạo **cùng một QName SOAP Fault** trong mọi phiên bản hoặc mọi stack. Có thể lỗi bị gateway/transport từ chối **trước** khi Spring-WS handler được gọi. Khi kiểm thử, lấy **wire XML thực tế**, SOAP version, subcode và HTTP status để phân loại.

### 14.2. ReplyTo và FaultTo không đáng tin: nguy cơ SSRF

Giả sử kẻ tấn công gửi:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>http://127.0.0.1:8080/admin</wsa:Address>
</wsa:ReplyTo>
~~~

Nếu server mở một HTTP connection đến URI do caller cung cấp mà không kiểm tra, nó có thể truy cập tài nguyên nội bộ, metadata endpoints hoặc lộ dữ liệu/credentials ra ngoài. **WS-Addressing không phải một cơ chế xác thực destination**.

Với Spring-WS **4.1.4**, tài liệu reference có phần kiểm soát **out-of-band destination** tại HTTP message sender. Các sender có kiểm tra mặc định đối với một số literal IP loopback/link-local/private và đích có host không hợp lệ; nhưng **hostname thông thường có thể không được DNS-resolve trong kiểm tra mặc định** vì chi phí hiệu năng. Vì vậy hostname độc hại trỏ tới IP nội bộ có thể không bị chặn chỉ dựa trên literal-IP checks.

Hãy thực hiện **defense in depth**:

1. Chỉ cho phép **scheme** an toàn, thường là HTTPS, và những host/port đã duyệt.
2. Cấu hình **`DestinationPolicy` allowlist** trên message sender phù hợp khi hỗ trợ out-of-band replies; không chỉ dựa vào kiểm tra IP mặc định.
3. Có chính sách DNS resolution/DNS rebinding và chống truy cập IP nội bộ theo threat model; kiểm tra cả đích sau redirect hoặc tắt redirect nếu không cần.
4. Bắt buộc xác thực caller và quyền dùng callback URL/profile; không tin `ReplyTo`/`FaultTo` chỉ vì SOAP XML hợp schema.
5. Dùng **khóa/credential riêng** theo đối tác, không gửi WS-Security tokens hoặc dữ liệu nhạy cảm đến callback không thuộc đối tác.
6. Giới hạn timeout, retry count, response size, concurrency và log host sau chuẩn hóa.
7. Kiểm tra reference parameters (nếu có) không chứa payload điều khiển luồng hoặc token không đáng tin.
8. Có telemetry khi callback destination bị từ chối, nhưng public fault không tiết lộ topology nội bộ.

Một ví dụ **policy mô tả**:

~~~text
allowed callback schemes: https
allowed callback hosts: callbacks.partner-a.example, callbacks.partner-b.example
allowed ports: 443
redirects: deny unless explicitly reviewed
private / loopback / link-local destinations: deny
max callback attempts: bounded, with backoff
sender credentials: per partner profile
~~~

Đừng coi đây là `DestinationPolicy` Java API đã triển khai; cần viết/đăng ký policy theo sender Spring-WS thực tế, không phỏng đoán setter name. Việc allowlist nên độc lập với đầu vào SOAP; nếu caller được phép đăng ký callback URL động, phải có quy trình xác minh/activation rõ.

### 14.3. WS-Security và Addressing headers

WS-Addressing nói **gửi tới đâu và liên kết thế nào**; nó không tự đảm bảo tính toàn vẹn hoặc xác thực. Một kẻ tấn công có thể sửa:

- `wsa:Action` → route sang operation khác nếu header không được bảo vệ;
- `wsa:To` → thay đổi destination routing;
- `wsa:ReplyTo`/`wsa:FaultTo` → chuyển reply chứa dữ liệu sang nơi khác;
- `wsa:MessageID`/`wsa:RelatesTo` → giả mạo correlation hoặc gắn kết sai.

Trong môi trường có WS-Security (ví dụ `Wss4jSecurityInterceptor`), xác minh signature, timestamp và token theo policy. Cần bảo đảm **những addressing headers quan trọng và SOAP Body đã được bảo vệ theo threat model**, và endpoint sử dụng **đúng các XML nodes đã được xác thực**; tránh XML Signature wrapping.

**Có WS-Security Header không đồng nghĩa signature đã hợp lệ**. TLS/mTLS bảo vệ kênh và xác minh certificate ở transport nhưng không tự mang thông tin XML signature qua các SOAP intermediaries. Quyết định dùng transport security, message security hay cả hai phụ thuộc đường đi thông điệp và yêu cầu bảo mật.

### 14.4. MessageID không phải credential hay chống replay tự động

`MessageID` thường có dạng UUID URI để correlation. Nó **không phải session token, password, authorization grant hoặc chứng chỉ**. Một request có thể được phát lại với cùng MessageID hoặc MessageID mới; nếu cần chống replay, phải có policy riêng về chữ ký, timestamp, nonce, window, duplicate detection và trạng thái bền vững. Nếu thao tác có tác dụng phụ, **server-side idempotency** vẫn là lớp riêng.

### 14.5. SOAP Fault phải công bố an toàn

Khi `wsa:Action` sai hoặc `To` bị từ chối, public SOAP Fault nên chứa thông tin đủ để client sửa cấu hình, nhưng không chứa:

- stack trace, Java class hoặc SQL;
- private key, token, SOAP signatures;
- nội bộ hostname/IP hoặc URL admin bị chặn;
- toàn bộ XML Header/Body có dữ liệu nhạy cảm.

Sử dụng mã lỗi chuẩn theo SOAP/WS-A, fault detail đã được WSDL/XSD công bố nếu đối tác cần, và correlation ID vô hại. Với lỗi ở tầng TLS/HTTP trước SOAP parser, có thể **không có SOAP Fault**; client phải xử lý transport error riêng.

## 15. Kiểm thử và gỡ lỗi WS-Addressing

### 15.1. Ma trận bắt buộc

| Ca kiểm thử | Kỳ vọng | Điều được xác minh |
| --- | --- | --- |
| Input Action đúng + payload QName đúng | Map đúng `@Action` handler | Action mapping + JAXB |
| Input Action đúng, payload root sai | XSD/adapter từ chối | Không nhầm Action với Body |
| Đổi Action URI, giữ payload | Không route nhầm operation | EndpointMapping |
| Đổi To, giữ Action | Từ chối hoặc route theo gateway policy | `@Address`/destination |
| To vắng trong profile bắt buộc | Fault/từ chối theo policy | Optional syntax ≠ required MEP |
| Request MessageID có URI hợp lệ | Response RelatesTo đúng ID | Correlation |
| Response mang MessageID mới | Không ghi đè request ID | Hai ID riêng |
| ReplyTo vắng (WS-A 1.0) | Default anonymous theo policy | Reply endpoint default |
| ReplyTo anonymous | Reply đi cùng exchange | HTTP request-response |
| ReplyTo non-anonymous | Out-of-band khi có capability | Callback transport |
| FaultTo non-anonymous | Fault tới đúng receiver | Fault routing |
| FaultTo vắng | Fallback ReplyTo theo quy tắc | Default fault endpoint |
| ReplyTo none | Không phát như callback thường | EPR none semantics |
| RelatesTo sai/unknown ID | Không ghép nhầm request | Correlation store |
| RelatesTo ở response thiếu khi profile yêu cầu | Test fault/validation thất bại | MEP compliance |
| RelationshipType 1.0 mặc định | Reply IRI đúng | Không dùng QName 2004 |
| WS-A 2004 header vào server 1.0-only | Bị từ chối đúng | Namespace/version |
| SOAP 1.1 SOAPAction lệch Action | ActionMismatch/invalid addressing behavior | Binding compliance |
| SOAP 1.2 action parameter lệch | Bị xử lý theo binding/policy | SOAP 1.2 action consistency |
| Callback URL loopback/private | Bị chặn | SSRF default/policy |
| Callback host redirect sang private IP | Bị chặn theo threat model | Redirect/DNS policy |
| Callback thiếu chữ ký/token hợp lệ | Không xử lý nghiệp vụ | WS-Security/TLS |
| Hai callbacks về ngược thứ tự | Cùng request được correlation chính xác | Multi-request consistency |
| Client Java và .NET | Hiểu Action/To/RelatesTo đồng nhất | Interoperability |
| SOAP Fault sau DB commit | Client retry không tạo effect trùng | Idempotency |

### 15.2. Test server với Spring-WS test

`MockWebServiceClient` đưa payload qua dispatcher trong test context và phù hợp để kiểm tra mapping `@Action`, khi request creator có khả năng gắn WS-Addressing Header vào `SoapMessage`. Một khung test hợp lệ về nguyên tắc:

~~~java
// Pseudocode test setup:
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

// 1. Tạo request payload XML SubmitOrderRequest.
// 2. Trong RequestCreator/callback, gắn
//    wsa:Action, wsa:To, wsa:MessageID của WS-A 1.0.
// 3. Gửi qua client.sendRequest(requestCreator).
// 4. Expect SOAP success hoặc Fault theo policy.
// 5. Dùng SOAP-aware ResponseMatcher để kiểm
//    wsa:RelatesTo bằng request MessageID và Action output.
~~~

Khung trên có comment chứ không cung cấp một `RequestCreator` hoàn chỉnh; tránh sao chép giả lập APIs không tồn tại. `withPayload(...)` chuẩn chỉ mô tả payload Body; **đừng** kết luận WS-Addressing Header đã được tạo nếu test không thực sự thêm nó. Khi mapping/adapter/validators khác nhau, cấu hình test context phải tương ứng server production.

### 15.3. Test Spring-WS client với MockWebServiceServer

`MockWebServiceServer` có thể kiểm tra `WebServiceTemplate` cùng `ActionCallback` đã marshal Body và thêm headers phù hợp. Với các ca cần đọc SOAP Header:

- Kiểm `wsa:Action` QName và text URI chính xác.
- Kiểm `wsa:To` theo connection URI hoặc override.
- Kiểm `wsa:MessageID` là URI tuyệt đối và được tạo riêng.
- Kiểm `ReplyTo`/`FaultTo` EPR Address theo profile.
- Trả XML response có `RelatesTo` và kiểm correlation.
- Tạo Fault WS-A và kiểm client phân loại SOAP Fault, không ép thành JAXB success DTO.

Một mock server dùng cho kiểm thử tuần tự không tự chứng minh callback dispatcher đa luồng hoặc HTTP sender an toàn. Với asynchronous callbacks, cần test HTTP receiver thật, SSL, allowlist, worker/queue, restart và retry.

### 15.4. Test QName/namespace-aware, không so raw prefix

Không viết:

~~~java
// Fragile: serializer có thể đổi prefix wsa thành ns4.
assertTrue(xml.contains("<wsa:RelatesTo>urn:uuid:..."));
~~~

Hãy parse SOAP XML bằng parser an toàn, so QName `{http://www.w3.org/2005/08/addressing}RelatesTo`, kiểm text IRI, và kiểm mỗi `wsa:ReplyTo`/`wsa:FaultTo` chứa đúng `wsa:Address`. Với WS-A 1.0, `RelationshipType` phải là absolute IRI theo chuẩn; không parse như QName của 2004.

### 15.5. Các bước chẩn đoán theo thứ tự

1. Xác minh **SOAP Envelope version** và Content-Type/HTTP SOAPAction.
2. Kiểm namespace **WS-Addressing 1.0 hay August 2004**.
3. Đọc `wsa:Action` input và so WSDL metadata/`@Action`.
4. Đọc `wsa:To` và so endpoint URI/`@Address`/gateway policy.
5. Kiểm `wsa:MessageID` hiện diện/format theo MEP.
6. Kiểm `ReplyTo`, `FaultTo`, anonymous/none/non-anonymous và receiver capability.
7. Nếu lỗi, xem SOAP Fault/subcode nhưng **không** suy DB rollback.
8. Nếu reply không ghép được, so `wsa:RelatesTo` với request MessageID.
9. Kiểm WS-Security signature/timestamp/certificate và policy callback.
10. So raw wire XML (được che thông tin nhạy cảm), tests Java/.NET và WSDL thực tế.

## 16. Anti-patterns và bài tập vận dụng

### 16.1. Thiết kế nên tránh

| Anti-pattern | Vì sao nguy hiểm | Thiết kế tốt hơn |
| --- | --- | --- |
| Coi Action = SOAPAction = payload QName | Ba cơ chế khác nhau | Đối chiếu theo WSDL/binding |
| So prefix `wsa` thay vì namespace URI | XML serializer đổi prefix làm fail | So expanded QName |
| Gửi WS-A 2004 namespace vào endpoint 1.0 | Header không cùng chuẩn | Khai báo `AddressingVersion` đúng |
| Thay To cho mọi lời gọi từ untrusted input | Routing confusion, SSRF | Allowlist/gateway policy |
| Cho arbitrary ReplyTo/FaultTo URL | SSRF, exfiltration | DestinationPolicy + TLS/auth |
| Hiểu anonymous như HTTP endpoint thực | Sai nghĩa IRI đặc biệt | Dùng cùng MEP response channel |
| Dùng MessageID làm business idempotency duy nhất | Không có exactly-once guarantee | Business requestId + uniqueness |
| Coi RelatesTo là danh tính đã xác thực | Spoofing callback | WS-Security/TLS + correlation store |
| Không duy trì state cho callback lâu | Reply tới sau không nhận diện được | Durable correlation state |
| Chọn non-anonymous ReplyTo nhưng chờ synchronous response | Client có thể treo/timeout | Thiết kế callback MEP rõ |
| Hardcode cùng Action input/output/fault | Routing sai | Định nghĩa riêng trong WSDL |
| Chỉ có `@Action` mà chưa cấu hình mapping | Method không được định tuyến | Test AnnotationActionEndpointMapping |
| Tưởng ActionCallback cấu hình WS-Security | Signature/token không được tự thêm | Security interceptor/policy riêng |
| Không kiểm SOAPAction mismatch | WS-A protocol fault | Kiểm binding SOAP 1.1 |
| Log toàn bộ header token/PII | Rò dữ liệu | Logging được giới hạn, che secret |
| Chỉ test success Body | Bỏ qua reply/fault correlation | SOAP-aware tests + interoperability |

### 16.2. Bài tập

**Bài 1 — Action và To.** Hai request tới cùng `/ws/orders` nhưng một request dùng Action `SubmitOrder`, request kia dùng `GetOrderStatus`. Giải thích Action giúp gì và To xác định điều gì.

**Bài 2 — MessageID.** Client retry `SubmitOrder` sau timeout và tạo MessageID mới. Vì sao server vẫn phải dựa vào business requestId/idempotency store để ngăn trùng đơn?

**Bài 3 — ReplyTo.** Một request có `ReplyTo=anonymous`. Response đi qua kênh nào? Nếu đổi sang `https://client.example.test/replies`, phía client/server phải thêm gì?

**Bài 4 — FaultTo.** Khi `FaultTo` vắng nhưng `ReplyTo` có, Fault được định tuyến theo quy tắc nào? `FaultTo` có thể tự thay đổi `Sender` thành `Receiver` hay không?

**Bài 5 — RelatesTo.** Request có MessageID `urn:uuid:11111111-2222-4333-8444-555555555555`; response tạo MessageID `urn:uuid:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee`. Header `RelatesTo` của response cần có giá trị nào?

**Bài 6 — RelationshipType.** Tại sao `RelationshipType="wsa:Reply"` hợp với một profile 2004/08 không nên tự đem vào WS-A 1.0?

**Bài 7 — Spring-WS.** Viết ví dụ `new ActionCallback(URI, new Addressing10(), to)`. So sánh với `SoapActionCallback` và kiểm tra SOAPAction 1.1 nếu cả hai được cấu hình.

**Bài 8 — @Action.** Server định tuyến theo `@Action("urn:...:SubmitOrder")` nhưng client gửi đúng QName payload và sai Action. Lỗi nên được chẩn đoán ở đâu?

**Bài 9 — Callback security.** Một client đưa `FaultTo=http://169.254.169.254/...` và một client khác đưa hostname DNS trỏ tới IP đó. Vì sao cả hai đều phải bị kiểm tra chặt?

**Bài 10 — Fault sau commit.** Client nhận SOAP Fault/timeout sau `SubmitOrder` và muốn gửi requestId nghiệp vụ mới. Vì sao điều này nguy hiểm?

### 16.3. Gợi ý đáp án ngắn

- Bài 1: Action định danh semantics; To chỉ destination. Chúng không thay thế payload QName/XSD.
- Bài 2: MessageID chỉ định danh message; server vẫn cần trạng thái chống trùng của ý định nghiệp vụ.
- Bài 3: Anonymous dùng response channel thích hợp; non-anonymous cần callback receiver, binding, security và durable correlation.
- Bài 4: Dùng reply endpoint theo Core khi FaultTo vắng; faultcode phản ánh loại lỗi, không phụ thuộc destination.
- Bài 5: RelatesTo lấy **request MessageID** `urn:uuid:11111111-2222-4333-8444-555555555555`.
- Bài 6: Version 1.0 dùng IRI RelationshipType; 2004 dùng QName.
- Bài 7: ActionCallback tạo WS-Addressing headers; SoapActionCallback đặt transport action, phải tuân binding.
- Bài 8: Kiểm WS-A Action, addressing namespace/version, mapping/`@Action`, thứ tự mappings, rồi Body/XSD.
- Bài 9: Chặn cả literal IP và DNS host trỏ đến đích nội bộ; allowlist/redirect/DNS controls.
- Bài 10: Request đầu có thể đã commit; giữ cùng idempotency key và tra trạng thái thay vì tạo intent mới.

## Tài liệu tham khảo

- [W3C — WS-Addressing 1.0 Core](https://www.w3.org/TR/ws-addr-core/): sáu addressing properties, EPR, anonymous/none, reply rules và `RelatesTo`.
- [W3C — WS-Addressing 1.0 SOAP Binding](https://www.w3.org/TR/ws-addr-soap/): SOAP 1.1/1.2, SOAPAction matching và addressing faults.
- [W3C — WS-Addressing 1.0 Metadata](https://www.w3.org/TR/ws-addr-wsdl/): `wsam:Action`, WSDL/WS-Policy và MEP.
- [WS-Addressing August 2004 Submission](https://www.w3.org/submissions/ws-addressing/): phiên bản `2004/08` và khác biệt namespace.
- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): WS-Addressing client/server và bảo vệ out-of-band destinations.
- [Spring-WS API — ActionCallback](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/client/ActionCallback.html): constructors, `setReplyTo`, `setFaultTo` và MessageID strategy.
- [Spring-WS API — AnnotationActionEndpointMapping](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/server/AnnotationActionEndpointMapping.html): định tuyến `@Action`/`@Address`.
- [Spring-WS API — @Action](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/server/annotation/Action.html): `value`, `output`, `fault`.
- [Spring-WS API — EndpointReference](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/core/EndpointReference.html): EPR `Address` và reference parameters.
- [Spring-WS API — AddressingVersion](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/version/AddressingVersion.html): đọc/thêm Message Addressing Properties theo phiên bản.

**Ghi nhớ:** **`Action` nói message muốn làm gì; `To` nói message nhắm tới đâu; `MessageID` định danh request message; `ReplyTo`/`FaultTo` chọn nơi nhận trả lời hoặc lỗi; `RelatesTo` nối reply/fault với request gốc.** Hãy thống nhất namespace phiên bản, SOAP binding, XSD/WSDL và Spring-WS mappings; kiểm soát destination của non-anonymous callbacks bằng security policy; không coi MessageID là idempotency hoặc authorization; kiểm thử cả success, Fault, timeout và reply khác kênh.
