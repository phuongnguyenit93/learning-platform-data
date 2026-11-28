# Phiên bản WS-Addressing và yêu cầu tương thích giữa hai phía

Trong một hệ thống tích hợp doanh nghiệp, hai dịch vụ có thể cùng sử dụng **SOAP 1.1**, trao đổi XML đúng **XSD/WSDL** và thậm chí dùng cùng URI `CreateOrder`, nhưng vẫn thất bại vì **khác phiên bản WS-Addressing**. Client gửi `wsa:Action` thuộc namespace tháng 8/2004, trong khi server chỉ xử lý WS-Addressing 1.0 với namespace tháng 8/2005; kết quả có thể là không tìm được endpoint, lỗi xử lý SOAP Header hoặc một SOAP Fault liên quan addressing.

Đó là vấn đề chính của bài **“Phiên bản WS-Addressing và yêu cầu tương thích giữa hai phía”**, thuộc chương **WS-Addressing** của module `SPRING_WEB_SERVICES`. Chủ đề được đặt trong bối cảnh phát triển dịch vụ SOAP **contract-first** với XSD/WSDL, ánh xạ JAXB, xây dựng `@Endpoint` và SOAP client, xử lý interceptor, SOAP Fault, XML security, WS-Security, chứng chỉ và kiểm thử tương thích.

**Mục tiêu sau bài học:** người học nhận diện được các phiên bản WS-Addressing qua namespace; phân biệt chúng với SOAP/WSDL/HTTP versions; cấu hình client và endpoint mapping Spring-WS nhất quán; đọc `Action`, `To`, `MessageID`, `RelatesTo`, `ReplyTo` và `FaultTo` đúng ý nghĩa; xử lý khác biệt chính sách response, security và Fault; xây dựng ma trận kiểm thử hai đầu trước khi triển khai.

Các ví dụ Java/XML bên dưới dùng tên miền và đơn hàng giả định. Chúng mô tả API có trong tài liệu **Spring-WS 4.1.4**, không bảo đảm tương ứng mọi phiên bản Spring-WS/Java/JAXB. Nếu dự án đang chạy bản khác, cần kiểm tra Javadoc và JAR thực tế trước khi áp dụng.

## 1. WS-Addressing là gì và giải quyết vấn đề nào?

**WS-Addressing (WS-A)** là tập quy tắc biểu diễn **địa chỉ đích**, **ý nghĩa hành động**, **định danh bản tin** và **quan hệ request–response** ở dạng thông tin không lệ thuộc một HTTP connection cụ thể. Thay vì chỉ để HTTP URL hoặc HTTP `SOAPAction` quyết định luồng xử lý, WS-Addressing mô tả các **Message Addressing Properties (MAPs)** bằng SOAP Header.

Ví dụ một SOAP request có thể mang:

~~~xml
<wsa:To>https://orders.example.test/ws</wsa:To>
<wsa:Action>urn:example:orders:v1/CreateOrder</wsa:Action>
<wsa:MessageID>urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321</wsa:MessageID>
~~~

Ý nghĩa tóm tắt:

| Message Addressing Property | Dạng SOAP Header thường gặp | Câu hỏi nó trả lời |
| --- | --- | --- |
| Destination | `wsa:To` | Bản tin được gửi đến endpoint logic nào? |
| Action | `wsa:Action` | Bản tin thể hiện hành động/operation gì? |
| Message ID | `wsa:MessageID` | Đây là thông điệp nào? |
| Relationship | `wsa:RelatesTo` | Thông điệp này phản hồi/liên quan thông điệp nào? |
| Reply endpoint | `wsa:ReplyTo` | Khi có response, gửi về đâu? |
| Fault endpoint | `wsa:FaultTo` | Nếu có Fault, gửi về đâu? |
| Reference parameters | `wsa:ReferenceParameters` trong EPR và các header tương ứng khi sử dụng | Định danh/định tuyến thêm cho một endpoint reference cụ thể? |

Các SOAP headers không thay thế `soap:Body`: dữ liệu đơn hàng vẫn thuộc XSD của nghiệp vụ. Chúng cũng không tự tạo cơ chế **idempotency**, xác thực người gửi hay gửi bất đồng bộ. Mỗi khả năng đó cần hợp đồng và thành phần triển khai riêng.

### 1.1. Một request có nhiều lớp metadata

~~~mermaid
flowchart LR
    A["JAXB CreateOrderRequest"] --> B["SOAP Body theo XSD"]
    C["WS-A Action/To/MessageID/ReplyTo"] --> D["SOAP Header"]
    E["WS-Security token/signature"] --> D
    B --> F["SOAP Envelope 1.1 hoặc 1.2"]
    D --> F
    F --> G["HTTP POST + Content-Type/SOAPAction"]
    G --> H["TLS/mTLS, proxy, gateway"]
    H --> I["Spring-WS server"]
~~~

**Kiểm tra tương thích WS-A** không thể tách khỏi toàn pipeline. Nhưng cần xác định chính xác trục nào sai: SOAP version, namespace addressing, URI `Action`, HTTP `SOAPAction`, WSDL/WS-Policy, địa chỉ `To` hay WS-Security.

### 1.2. WS-Addressing không bắt buộc cho mọi SOAP service

Một Spring-WS endpoint chỉ dùng `@PayloadRoot` và SOAP Body QName có thể hoạt động mà **không cần WS-Addressing**. WS-A trở nên cần thiết khi hợp đồng/policy yêu cầu routing theo `Action`, định danh message, endpoint references hoặc quản lý reply/fault destination.

Vì vậy, không nên thêm WS-A Header vào tất cả SOAP clients chỉ vì framework hỗ trợ. Điều đúng là **hai bên thỏa thuận có dùng WS-A hay không, dùng phiên bản nào, các Header nào bắt buộc và reply policy là gì**.

## 2. Dòng phiên bản: August 2004 và W3C WS-Addressing 1.0

Các tài liệu kỹ thuật và SOAP stack có thể dùng tên **WS-Addressing 2004/08**, **WS-Addressing 1.0**, **W3C WS-A 2005/08**, **May 2006** hoặc chỉ ghi mơ hồ **WS-A enabled**. Một số tên đang chỉ cùng bản, một số chỉ các bản không tương thích về XML QName.

### 2.1. Hai phiên bản phải nhận diện rõ

| Tiêu chí | WS-Addressing August 2004 | WS-Addressing 1.0 của W3C |
| --- | --- | --- |
| Lịch sử | **W3C Member Submission**, ngày **10/08/2004**. | **W3C Recommendation**, Core/SOAP Binding ngày **09/05/2006**. |
| Namespace của SOAP Addressing elements | `http://schemas.xmlsoap.org/ws/2004/08/addressing` | `http://www.w3.org/2005/08/addressing` |
| Tên triển khai Spring-WS | `Addressing200408` | `Addressing10` |
| Ví dụ Header | `wsa:Action` trong namespace 2004/08. | `wsa:Action` trong namespace 2005/08. |
| Anonymous reply URI | `http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous` | `http://www.w3.org/2005/08/addressing/anonymous` |
| Nơi thường gặp | SOAP stacks/khách hàng legacy như WSE 3.0. | Các stack tuân WS-A 1.0/W3C hiện đại. |
| Rủi ro tương thích | Server chỉ nhận 1.0 có thể không xử lý Header 2004. | Client legacy chỉ phát 2004 có thể không chấp nhận Header 1.0. |

Nguồn chuẩn để tự kiểm tra: [WS-Addressing Member Submission 2004](https://www.w3.org/submissions/ws-addressing/) và [WS-Addressing 1.0 SOAP Binding Recommendation](https://www.w3.org/TR/ws-addr-soap/).

**Lưu ý về cách gọi:** **“2005/08”** trong namespace WS-A 1.0 **không có nghĩa bản Recommendation được ban hành tháng 8/2005**. Đây là namespace URI của đặc tả 1.0; bản Core/SOAP Binding chính thức đạt W3C Recommendation vào **tháng 5/2006**. Spring-WS dùng tên `Addressing10` và tài liệu nhắc tới “May 2006 edition”.

### 2.2. Còn các namespace lịch sử khác?

Trong giai đoạn chuẩn hóa có các bản dự thảo với namespace khác, ví dụ:

~~~text
http://www.w3.org/2004/12/addressing
~~~

Đó là namespace trong các W3C Working Draft tháng 12/2004, **không phải** bản Member Submission August 2004 hoặc bản W3C 1.0 Recommendation cuối cùng. Không suy rằng Spring-WS hỗ trợ mọi working draft chỉ vì tài liệu nói “support WS-Addressing”.

Đối với Spring-WS 4.1.4, tài liệu/Javadoc công bố rõ hai implementation `Addressing200408` và `Addressing10` trong package `org.springframework.ws.soap.addressing.version`. Nếu gặp namespace khác, **phải xác minh adapter/version được hỗ trợ**, không tự thay prefix hoặc sửa một URI là đủ.

### 2.3. Một header có local name giống nhưng QName khác

~~~xml
<!-- WS-Addressing August 2004 -->
<a:Action xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  urn:example:orders:v1/CreateOrder
</a:Action>
~~~

~~~xml
<!-- W3C WS-Addressing 1.0 -->
<wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:example:orders:v1/CreateOrder
</wsa:Action>
~~~

Hai element đều có local name `Action` và text URI giống hệt, nhưng **QName khác**:

~~~text
{http://schemas.xmlsoap.org/ws/2004/08/addressing}Action
{http://www.w3.org/2005/08/addressing}Action
~~~

Một server chỉ nhận `Addressing10` không được coi Header August 2004 là đúng chỉ vì có từ `Action`. Prefix `a`/`wsa` lại **không quyết định tương thích**: đổi prefix nhưng giữ namespace thì QName không đổi.

### 2.4. Phân biệt bốn “version” độc lập

| Trục | Ví dụ | Chịu trách nhiệm chính |
| --- | --- | --- |
| **SOAP version** | SOAP 1.1 / SOAP 1.2. | SOAP Envelope namespace, Content-Type, Fault structure và binding. |
| **WS-Addressing version** | August 2004 / W3C 1.0. | Namespace và semantics của `Action`/`To`/`ReplyTo`, EPR, Fault addressing. |
| **WSDL/XSD contract version** | `orders:v1` / `orders:v2`. | XML Body QName, schema, operation, Fault detail. |
| **HTTP version** | HTTP/1.1 / HTTP/2. | Vận chuyển, connection management, proxies. |

Ví dụ SOAP **1.1** vẫn có thể mang WS-Addressing **1.0**; W3C WS-A 1.0 SOAP Binding hỗ trợ SOAP 1.2 và tương thích SOAP 1.1. Không lập quy tắc “SOAP 1.1 chỉ được dùng WS-A 2004” hoặc “SOAP 1.2 tự động bật WS-A 1.0”.

## 3. So sánh SOAP request giữa hai phiên bản

Giả sử client muốn gọi operation `CreateOrder` với payload nghiệp vụ giống nhau.

### 3.1. WS-Addressing 1.0 trong SOAP 1.1

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <wsa:To>https://orders.example.test/ws</wsa:To>
    <wsa:Action>urn:example:orders:v1/CreateOrder</wsa:Action>
    <wsa:MessageID>
      urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
    </wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
    </wsa:ReplyTo>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Trong mô hình request-response HTTP thông thường, URI **anonymous** thể hiện phản hồi trả trên kênh kết nối yêu cầu, không cần máy chủ tạo một HTTP request khác tới client. Đây là ví dụ dữ liệu giả; XSD thực tế còn phải khai báo các element trong Body.

### 3.2. August 2004 trong SOAP 1.1

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa04="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <wsa04:To>https://orders.example.test/ws</wsa04:To>
    <wsa04:Action>urn:example:orders:v1/CreateOrder</wsa04:Action>
    <wsa04:MessageID>
      urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
    </wsa04:MessageID>
    <wsa04:ReplyTo>
      <wsa04:Address>
        http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
      </wsa04:Address>
    </wsa04:ReplyTo>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
      <ord:amount>1250000.00</ord:amount>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

**Hai ví dụ không khác nhau về XSD của `CreateOrderRequest`**, nhưng **khác namespace SOAP Header** và **anonymous reply URI**. Chính khác biệt này có thể quyết định endpoint mapping và response dispatch có hoạt động không.

### 3.3. Bảng “chỉ sửa prefix” là sai

| Thao tác | Có đổi WS-A version không? | Hệ quả |
| --- | --- | --- |
| Đổi `wsa` thành `a` nhưng giữ nguyên URI 2005/08. | **Không**. | QName không đổi; hợp lệ về XML namespace. |
| Đổi namespace 2004/08 sang 2005/08. | **Có**. | Phải đánh giá toàn bộ headers, EPR, anonymous URI, Fault, WSDL/policy. |
| Đổi HTTP `SOAPAction` nhưng giữ `wsa:Action`. | **Không**. | Có thể tạo action mismatch thay vì sửa WS-A version. |
| Đổi SOAP Envelope 1.1 sang SOAP 1.2. | **Không tự động**. | Phải đổi Content-Type, SOAP Fault, message factory/binding. |
| Đổi payload namespace `orders:v1` thành `orders:v2`. | **Không**. | Là thay đổi contract nghiệp vụ, không phải WS-A Header. |

## 4. MessageID, RelatesTo và response cần cùng phiên bản

Ngoài việc **request được route đúng**, hai phía phải thống nhất cách tạo **response** và **Fault**. Việc server đọc được `wsa:Action` 2004/08 nhưng gửi response theo 2005/08 có thể khiến client không nhận diện được `RelatesTo`, ngay cả khi nội dung nghiệp vụ hoàn toàn đúng XSD.

### 4.1. Response 1.0 có MessageID mới và RelatesTo request

Giả sử request ở mục 3.1 có `MessageID`:

~~~text
urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
~~~

Response SOAP 1.1 theo WS-A 1.0 có thể là:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <soap:Header>
    <wsa:To>http://www.w3.org/2005/08/addressing/anonymous</wsa:To>
    <wsa:Action>urn:example:orders:v1/CreateOrderResponse</wsa:Action>
    <wsa:MessageID>
      urn:uuid:547b192a-ae0a-4b9f-8f6b-24882e12f457
    </wsa:MessageID>
    <wsa:RelatesTo>
      urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321
    </wsa:RelatesTo>
  </soap:Header>
  <soap:Body>
    <ord:CreateOrderResponse>
      <ord:orderId>ORD-000184</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
    </ord:CreateOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

**Đây là mẫu minh họa**, giả định contract quy định output action `urn:example:orders:v1/CreateOrderResponse` và mô hình anonymous response. Không mặc định Spring-WS luôn ghi mọi phần tử giống mẫu, vì header cần có hay không phụ thuộc WS-A spec, exchange pattern, version, endpoint mapping, client/server configuration và policy.

Các nguyên tắc phân biệt:

- **`MessageID`** của response mới là định danh **response message**; không dùng lại request MessageID nếu đang tạo thông điệp khác.
- **`RelatesTo`** liên kết response tới request `MessageID`. Với WS-A 1.0, relationship mặc định của một reply có IRI `http://www.w3.org/2005/08/addressing/reply`.
- **`CorrelationId` nghiệp vụ**, nếu contract có custom header, có thể giữ nguyên xuyên nhiều SOAP calls; nó không thay thế `RelatesTo`.
- `wsa:Action` của **response** thường khác action của request. Phải đối chiếu WSDL/WS-A metadata và mapping output.

### 4.2. Nếu phía nhận chỉ nhận August 2004

Một client legacy có thể đòi response header nằm trong namespace:

~~~text
http://schemas.xmlsoap.org/ws/2004/08/addressing
~~~

và sử dụng anonymous reply URI:

~~~text
http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
~~~

Khi server trả phần tử `RelatesTo` theo namespace 2005/08, client có thể bỏ qua hoặc từ chối nó, tùy SOAP processing policy. **Hỗ trợ nhận request hai version không đủ** nếu response serializer lại cố định một version.

Từ đây xuất hiện yêu cầu kiểm thử hai chiều: **client gửi đúng version → server parse/route → server trả response/Fault cùng addressing semantics → client kiểm tra được quan hệ message**.

### 4.3. MessageID không phải khóa idempotency

Một yêu cầu tạo đơn bị timeout có thể đã được server commit. WS-Addressing `MessageID` giúp nhận diện message; ở một số mô hình retransmission, phiên bản/protocol có thể cho phép gửi lại cùng ID. Nhưng **không có nghĩa Spring-WS tự chống tạo đơn trùng**.

Nếu operation có side effect:

~~~text
CorrelationId:    corr-27a       (workflow)
MessageID:        urn:uuid:...   (SOAP message)
IdempotencyKey:   create-op-42   (một ý định tạo đơn)
AttemptId:        attempt-02    (lần thử mới)
~~~

Mỗi ID có semantics riêng. Bên server phải có chính sách **idempotency store/atomic checks** khi retry; không lấy `MessageID` hoặc `RelatesTo` làm bằng chứng chống duplicate giao dịch nếu hợp đồng chưa quy định rõ.

## 5. WSDL, WS-Policy và Action: yêu cầu hợp đồng rõ ràng

Một dịch vụ contract-first thường công bố WSDL 1.1 với XSD mô tả request/response. WS-Addressing bổ sung **metadata/binding/policy** để client generator biết nó phải gửi Header gì và action values nào là đúng.

### 5.1. SOAPAction, WS-A Action và tên operation là ba giá trị có thể liên quan nhưng khác nhau

| Khái niệm | Ví dụ | Nơi xuất hiện |
| --- | --- | --- |
| Tên WSDL operation | `CreateOrder` | `wsdl:portType/wsdl:operation` và `wsdl:binding`. |
| HTTP SOAPAction của SOAP 1.1 | `"urn:example:orders:v1/CreateOrder"` | HTTP header `SOAPAction`. |
| WS-A Action | `urn:example:orders:v1/CreateOrder` | SOAP Header `wsa:Action` trong namespace WS-A được chọn. |
| Body root QName | `{urn:example:orders:v1}CreateOrderRequest` | XML element trong SOAP Body. |

Chúng có thể được thiết kế nhất quán, nhưng **không đồng nghĩa** và không nằm ở cùng tầng.

WS-Addressing 1.0 Metadata và SOAP Binding có quy tắc về cách liên hệ action với WSDL và SOAP action. Nếu hợp đồng yêu cầu WS-A, việc để `wsa:Action`, `wsam:Action` trong WSDL và HTTP `SOAPAction` mâu thuẫn có thể gây lỗi interoperability, thậm chí trong trường hợp SOAP Body QName khớp.

**Không đặt `wsa:Action` thành tên Java method như `"createOrder"` nếu contract đang dùng URI tuyệt đối khác.**

### 5.2. WSDL 1.1 khai báo rõ WS-A input/output Action

Một trích đoạn WSDL 1.1 dùng metadata namespace của **WS-Addressing 1.0**:

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:wsam="http://www.w3.org/2007/05/addressing/metadata"
    xmlns:tns="urn:example:orders:wsdl:v1"
    targetNamespace="urn:example:orders:wsdl:v1">

  <wsdl:portType name="OrdersPortType">
    <wsdl:operation name="CreateOrder">
      <wsdl:input
          message="tns:CreateOrderInput"
          wsam:Action="urn:example:orders:v1/CreateOrder"/>
      <wsdl:output
          message="tns:CreateOrderOutput"
          wsam:Action="urn:example:orders:v1/CreateOrderResponse"/>
      <wsdl:fault
          name="OrderFault"
          message="tns:OrderFaultMessage"
          wsam:Action="urn:example:orders:v1/OrderFault"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrdersSoapBinding"
                type="tns:OrdersPortType">
    <soap:binding
        style="document"
        transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="CreateOrder">
      <soap:operation
          soapAction="urn:example:orders:v1/CreateOrder"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
      <wsdl:fault name="OrderFault">
        <soap:fault name="OrderFault" use="literal"/>
      </wsdl:fault>
    </wsdl:operation>
  </wsdl:binding>
</wsdl:definitions>
~~~

Đây là **trích đoạn**, không phải WSDL độc lập: chưa khai báo `wsdl:message`, `wsdl:types`/XSD imports, `wsdl:service`/`soap:address`, policy attachment và namespaces của các XSD tương ứng. Nó tập trung vào `wsam:Action` trên input/output/fault và `soapAction` trong binding.

**Điểm đặc biệt:** có `wsam:Action` không tự động có nghĩa endpoint **bắt buộc** dùng WS-A. Theo W3C WS-A 1.0 Metadata, chỉ riêng action attribute có tính thông tin nếu không có addressing policy assertion phù hợp. Cần khai báo/thỏa thuận **support/requirement** thông qua WS-Policy, ví dụ `wsam:Addressing` hoặc contract ngoài WSDL khi cần.

### 5.3. Phân biệt wsam và wsaw, đừng coi là phiên bản message

Các namespace thường gặp:

~~~text
WS-A message headers (1.0):
  http://www.w3.org/2005/08/addressing

WS-A 1.0 Metadata (WSDL/Policy):
  http://www.w3.org/2007/05/addressing/metadata

WS-A WSDL Binding ở giai đoạn tài liệu khác:
  http://www.w3.org/2006/05/addressing/wsdl
  http://www.w3.org/2006/02/addressing/wsdl
~~~

Tên prefix như `wsa`, `wsam`, `wsaw` có thể xuất hiện với **các đặc tả/bản metadata khác nhau**. Hãy luôn xem namespace URI và mục đích tài liệu, không so prefix. `wsam:Action` ở WSDL **không phải element SOAP Header** được gửi trên wire; SOAP Header 1.0 dùng `wsa:Action` namespace 2005/08.

Các hệ thống legacy có thể dùng `wsaw:UsingAddressing`, WS-Policy thế hệ cũ hoặc WCF policy assertion khác. **Không đổi chuỗi namespace metadata bằng search/replace rồi coi WSDL đã tương thích**. Cần xác minh generation của client, profile và policy parser ở hai phía.

### 5.4. Policy thể hiện anonymous và non-anonymous responses

Trong WS-Addressing 1.0 Metadata, các policy assertions có thể mô tả yêu cầu sử dụng addressing, bao gồm:

- `wsam:Addressing`: endpoint sử dụng/yêu cầu WS-Addressing theo cách được policy biểu đạt.
- `wsam:AnonymousResponses`: chính sách phản hồi anonymous.
- `wsam:NonAnonymousResponses`: chính sách cho phép hoặc yêu cầu đáp ứng non-anonymous theo mô tả của assertion.

**Không mặc định mọi server hỗ trợ non-anonymous reply** chỉ vì nó biết `wsa:ReplyTo`. Nếu service request-response chỉ có HTTP đồng bộ và không hỗ trợ callback riêng, hợp đồng nên nói rõ anonymous responses. Khi gateway/partner dùng callback, phải xác định địa chỉ, transport, security và routing theo policy.

Với WSDL của hệ thống khác công nghệ, hãy kiểm tra cả **effective policy sau import/attachment**, không chỉ nhìn vài dòng ở WSDL chính.

### 5.5. WSDL được sinh từ XSD không tự bao trọn WS-A policy

`DefaultWsdl11Definition` có thể sinh WSDL từ XSD/operation naming convention. Nhưng **không được giả định nó tự tạo đầy đủ WS-Addressing WSDL metadata/WS-Policy của đối tác**. Với hợp đồng bắt buộc WS-A, có thể cần WSDL tĩnh đã version hóa và được các bên kiểm chứng.

Khi client tool như JAX-WS `wsimport`, Apache Axis, WCF/.NET đọc WSDL, nó có thể suy ra hoặc cấu hình WS-A theo policy **khác nhau**. Tài liệu hợp đồng phải xác nhận những thiết lập cần thiết thay vì dựa vào mặc định không được kiểm thử.

## 6. Tương thích giữa HTTP SOAPAction và wsa:Action

Một lỗi liên hệ hay gặp là client gửi đúng `wsa:Action` nhưng HTTP `SOAPAction` sai hoặc rỗng không như WSDL.

### 6.1. Ví dụ hai loại action trên cùng request SOAP 1.1

~~~http
POST /ws HTTP/1.1
Host: orders.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
~~~

Bên trong SOAP Header:

~~~xml
<wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:example:orders:v1/CreateOrder
</wsa:Action>
~~~

Hai giá trị trùng nhau trong mẫu này vì contract chọn như thế. Tuy nhiên:

- **HTTP SOAPAction** là một HTTP header thuộc SOAP 1.1 binding, có thể được gateway/WAF hoặc `@SoapAction` mapping kiểm tra.
- **WS-A Action** là một SOAP header được `AnnotationActionEndpointMapping` và `@Action` sử dụng.
- **Body QName** vẫn do JAXB/XSD xác định và có thể được `@PayloadRoot` dùng để map endpoint.

Các endpoint mappings có thể khác thứ tự ưu tiên; không giả định ba cách chọn handler luôn suy ra cùng một method. Hãy giữ chúng nhất quán theo WSDL và kiểm tra conflict.

### 6.2. Trường hợp chỉ có SOAPAction mà thiếu WS-A Action

Nếu SOAP endpoint chỉ dùng `@SoapAction`/`@PayloadRoot`, request có thể hoạt động bình thường. Nhưng nếu phía server đã bật routing theo WS-A và **yêu cầu** `wsa:Action`, HTTP `SOAPAction` đúng **không đủ**.

Ngược lại, nếu phía client thêm `wsa:Action` nhưng dùng sai HTTP `Content-Type`/SOAP version, server có thể từ chối trước cả khi xử lý addressing. Phải kiểm tra thứ tự từ transport đến SOAP parser rồi addressing.

### 6.3. SOAP 1.2 không dùng cách diễn giải HTTP header giống SOAP 1.1

SOAP 1.2 qua HTTP thường dùng media type:

~~~http
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1/CreateOrder"
~~~

Giá trị action trong media type **không phải** một SOAP Header `wsa:Action`. Với một binding/policy yêu cầu WS-A, client vẫn phải tạo message addressing properties phù hợp. Không copy nguyên header `SOAPAction` SOAP 1.1 vào một SOAP 1.2 service mà không xem WSDL.

**Bảng chẩn đoán:**

| Dấu hiệu | Nên kiểm tra trước |
| --- | --- |
| `ActionNotSupported` | WS-A namespace đúng chưa? URI action có match operation/policy không? |
| SOAP `VersionMismatch` | SOAP Envelope namespace và Content-Type có đúng không? |
| Server không gọi endpoint | Action mapping, SOAPAction mapping, Body QName mapping có xung đột không? |
| HTTP `415` | SOAP 1.1/1.2 Content-Type/binding mismatch trước WS-A. |
| `MustUnderstand` | WS-A Header đang được target tới role/actor nào và có processor xử lý không? |
| Client nhận response nhưng bỏ qua header | Response dùng addressing namespace khác request? Output Action/RelatesTo đúng chưa? |

## 7. Spring-WS client: ActionCallback chọn phiên bản nào?

Spring-WS hỗ trợ WS-Addressing phía client thông qua `org.springframework.ws.soap.addressing.client.ActionCallback`. Đó là **callback thêm Message Addressing Properties**, khác với `SoapActionCallback` chuyên điều chỉnh HTTP SOAPAction.

Javadoc **Spring-WS 4.1.4** công bố các constructor:

~~~java
ActionCallback(String action)
ActionCallback(URI action)
ActionCallback(URI action, AddressingVersion version)
ActionCallback(URI action, AddressingVersion version, URI to)
~~~

Trong các constructor **chỉ cung cấp action**, version mặc định là **`Addressing10`**. Đây là chỗ dễ gây lỗi với đối tác legacy dùng WS-A 2004/08.

### 7.1. Khách hàng dùng WS-Addressing 1.0

~~~java
import java.net.URI;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

public final class OrdersClient {
    private static final URI CREATE_ACTION =
        URI.create("urn:example:orders:v1/CreateOrder");

    private final WebServiceTemplate template;

    public OrdersClient(WebServiceTemplate template) {
        this.template = template;
    }

    public Object createOrder(Object request) {
        ActionCallback callback =
            new ActionCallback(CREATE_ACTION, new Addressing10());

        return template.marshalSendAndReceive(request, callback);
    }
}
~~~

Ví dụ giả định `template` đã có JAXB marshaller/unmarshaller, message factory, sender/TLS/WS-Security phù hợp và `request` là JAXB root object hợp lệ. Trong project thật, thay `Object` bằng DTO sinh từ XSD và xử lý `JAXBElement` nếu schema dùng named complex types.

**Kết quả quan trọng:** callback tạo WS-A Headers trong namespace `http://www.w3.org/2005/08/addressing`. Với constructor hai đối số này, `To` mặc định phản ánh **connection URI** theo tài liệu Spring-WS, trừ khi cấu hình cách khác.

### 7.2. Khách hàng legacy dùng August 2004

Đối tác có thể yêu cầu namespace WS-A August 2004. Chọn phiên bản **rõ ràng**, không mong framework tự đoán theo response:

~~~java
import java.net.URI;

import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing200408;

URI action = URI.create("urn:example:orders:v1/CreateOrder");

ActionCallback legacyCallback =
        new ActionCallback(action, new Addressing200408());

// Chỉ gọi khi WebServiceTemplate đã cấu hình đúng transport/contract.
// Object response = template.marshalSendAndReceive(request, legacyCallback);
~~~

Đây là trích đoạn minh họa. **Khác biệt trọng tâm nằm ở `new Addressing200408()`**: nó chọn namespace và semantics tương ứng với bản August 2004. **Không chỉ đổi HTTP SOAPAction** hoặc thay prefix `wsa` sang `wsa04` để mô phỏng.

### 7.3. Khi To là địa chỉ logic khác URL transport

Ví dụ SOAP request được gửi qua gateway:

~~~text
HTTP POST transport URI: https://gateway.example.test/integration/orders
WS-A To logical URI:    https://orders.example.test/ws
~~~

Nếu policy phía đối tác yêu cầu `wsa:To` là logical endpoint URI, sử dụng constructor có `to`:

~~~java
import java.net.URI;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

ActionCallback callback = new ActionCallback(
    URI.create("urn:example:orders:v1/CreateOrder"),
    new Addressing10(),
    URI.create("https://orders.example.test/ws")
);
~~~

Thành công phụ thuộc WSDL/policy/routing phía server: `@Address` hoặc To validation có thể so To với giá trị logical đã khai báo. **Không đặt `To` tùy ý để bypass routing**, và không dùng giá trị do user nhập mà chưa được kiểm soát để tạo endpoint đích.

Nếu không cần To khác physical connection URI, **cấu hình mặc định** thường ít phức tạp và dễ tương thích hơn.

### 7.4. HTTP SOAPAction vẫn cần xử lý riêng

Mặc dù `ActionCallback` thêm WS-A `Action`, một số SOAP 1.1 server hoặc gateway còn kiểm tra HTTP `SOAPAction` theo WSDL. Có thể kết hợp ở một `WebServiceMessageCallback` khi contract yêu cầu:

~~~java
import java.net.URI;

import org.springframework.ws.WebServiceMessageCallback;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

URI addressingAction = URI.create(
    "urn:example:orders:v1/CreateOrder"
);

WebServiceMessageCallback callback = message -> {
    // Tạo WS-Addressing Header theo version 1.0.
    new ActionCallback(addressingAction, new Addressing10())
        .doWithMessage(message);

    // SOAP 1.1 HTTP SOAPAction theo WSDL.
    ((SoapMessage) message).setSoapAction(
        "urn:example:orders:v1/CreateOrder"
    );
};

// template.marshalSendAndReceive(createOrderRequest, callback);
~~~

Đoạn code giả định message là `SoapMessage` (SOAP client thực), và `ActionCallback#doWithMessage(...)` có thể ném các checked exceptions được khai báo bởi `WebServiceMessageCallback`. Không áp dụng cách ghép thủ công này nếu SOAP 1.2 binding/policy có quy tắc khác.

**Đừng dùng lẫn hai class callback:**

| Callback | Package | Thay đổi |
| --- | --- | --- |
| `ActionCallback` | `org.springframework.ws.soap.addressing.client` | WS-A `Action` và những MAPs liên quan. |
| `SoapActionCallback` | `org.springframework.ws.soap.client.core` | SOAP Action ở transport/binding SOAP message. |

### 7.5. ReplyTo, FaultTo, MessageID strategy cần phù hợp version

Javadoc của `ActionCallback` còn công bố các phương thức như `setReplyTo(...)`, `setFaultTo(...)` và `setMessageIdStrategy(...)`. Mặc định strategy phát sinh MessageID của Spring-WS là `UuidMessageIdStrategy` theo tài liệu.

Tuy nhiên, không tự bật non-anonymous `ReplyTo` hoặc đặt custom MessageID strategy chỉ để “đầy đủ Header”. Khi dùng callback địa chỉ khác:

- Phải đối chiếu **anonymous/non-anonymous policy**, message exchange pattern và HTTP sender.
- Địa chỉ ReplyTo/FaultTo có thể khiến server gửi **request mới sang một URL do client chỉ định**; cần ranh giới bảo mật rõ.
- Khi dùng WS-Security, đảm bảo header được ký/xác minh theo policy nếu cần.
- MessageID không phải idempotency key hoặc token bảo mật.
- Kiểm tra Javadoc constructors của `EndpointReference` và setters phù hợp với đúng phiên bản thay vì đoán API.

## 8. Spring-WS server: AnnotationActionEndpointMapping hỗ trợ những bản nào?

Spring-WS triển khai WS-Addressing phía server qua endpoint mapping, đặc biệt **`AnnotationActionEndpointMapping`**. Nó định tuyến bằng **WS-A `Action` SOAP Header**, không phải HTTP `SOAPAction` transport header.

Trong Spring-WS **4.1.4**, reference và Javadoc của `AbstractAddressingEndpointMapping` xác nhận rằng mapping mặc định có thể xử lý **`Addressing200408` và `Addressing10`**. Đây là **khả năng được triển khai**, không có nghĩa mọi SOAP request đều tự được áp dụng WS-A nếu ứng dụng chưa dùng mapping/policy thích hợp.

### 8.1. Endpoint dùng @Action

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;

@Endpoint
public class OrdersEndpoint {

    private final OrderApplicationService orderService;

    public OrdersEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @Action(
        value = "urn:example:orders:v1/CreateOrder",
        output = "urn:example:orders:v1/CreateOrderResponse",
        fault = "urn:example:orders:v1/OrderFault"
    )
    @ResponsePayload
    public CreateOrderResponse createOrder(
            @RequestPayload CreateOrderRequest request) {
        return orderService.createOrder(request);
    }
}
~~~

`CreateOrderRequest`, `CreateOrderResponse` và `OrderApplicationService` là **loại ứng dụng được giả định**. Để chạy, dự án phải có JAXB model từ XSD, endpoint adapter, message factory và endpoint mappings phù hợp. API `@Action` với `value`, `output` và `fault` được công bố trong Javadoc 4.1.4.

Mục đích ba URI trong annotation:

- `value`: Action của request.
- `output`: Action gắn lên response khi mapping hỗ trợ và operation trả response.
- `fault`: Action gắn lên SOAP Fault response theo khả năng mapping/resolver.

Không bỏ qua action của response/fault nếu **WSDL/partner yêu cầu exact values**. Một server có thể route request thành công nhưng client vẫn từ chối response do output action không khớp contract.

### 8.2. Giới hạn @Address theo To

Ngoài `@Action`, Spring-WS có annotation `@Address` ở **class**, dùng để so với `To` destination:

~~~java
import org.springframework.ws.soap.addressing.server.annotation.Address;
import org.springframework.ws.server.endpoint.annotation.Endpoint;

@Endpoint
@Address("https://orders.example.test/ws")
public class OrdersEndpoint {
    // Các @Action methods được rút gọn.
}
~~~

Không nên đặt `@Address` với hostname public trong khi gateway chuyển `To` thành URI nội bộ, trừ khi routing đã được thống nhất. Nếu client gửi `wsa:To` khác, method có thể không được chọn dù `Action` và Body đúng.

Khi một hệ thống có nhiều môi trường dev/staging/prod, cần quản trị To address theo contract, reverse proxy và endpoint references, không hardcode hostname của production vào mọi runtime.

### 8.3. Giới hạn version server tiếp nhận

Javadoc `AbstractAddressingEndpointMapping` công bố phương thức `setVersions(AddressingVersion[])`. Nếu đối tác chỉ dùng W3C 1.0 và bạn muốn từ chối WS-A legacy, có thể giới hạn:

~~~java
import org.springframework.ws.soap.addressing.server.AnnotationActionEndpointMapping;
import org.springframework.ws.soap.addressing.version.Addressing10;
import org.springframework.ws.soap.addressing.version.AddressingVersion;

AnnotationActionEndpointMapping mapping =
        new AnnotationActionEndpointMapping();

mapping.setVersions(
    new AddressingVersion[]{ new Addressing10() }
);
~~~

**Ví dụ tạo đối tượng cấu hình, không phải đoạn application chạy độc lập.** Phải tích hợp đối tượng này **đúng vào Spring ApplicationContext/WS configuration**. Một số cấu hình như `@EnableWs`/`WsConfigurationSupport` có thể đã tạo sẵn `AnnotationActionEndpointMapping`. **Không thêm bean mapping thứ hai** rồi để hai mapping trùng lặp/ưu tiên mâu thuẫn; hãy điều chỉnh mapping đang được sử dụng theo cách mà phiên bản framework hỗ trợ.

Nếu cần chỉ nhận August 2004, dùng implementation `Addressing200408` trong phiên bản cho phép. Nếu cần hỗ trợ cả hai, có thể giữ mặc định ở những bản Spring-WS công bố hỗ trợ. Không mở thêm namespace Working Draft chưa được hỗ trợ bằng cách tự thêm một chuỗi URI vào array: `setVersions` nhận các **AddressingVersion implementations**, không chỉ string.

### 8.4. Không nhầm route theo Action với route theo Body QName

Một endpoint class có thể được ánh xạ qua `@PayloadRoot`, `@SoapAction` hoặc `@Action` tùy endpoint mapping đang chạy:

| Annotation | Định tuyến dựa trên | Dùng khi |
| --- | --- | --- |
| `@PayloadRoot` | SOAP Body root QName. | Contract-first payload-centric. |
| `@SoapAction` | SOAP Action transport/binding. | Operation được chọn theo SOAPAction. |
| `@Action` | WS-Addressing `Action` SOAP Header. | Hợp đồng WS-A yêu cầu routing bằng Action. |

Không được giả định phương thức `createOrder` Java quyết định mọi mapping. Khi cùng bean có nhiều annotations, phải xác định **order/priority** của các endpoint mappings và test xem request thực tế chọn handler nào. Trong Spring-WS configuration hỗ trợ `@EnableWs`, tài liệu 4.1.4 mô tả `annotationActionEndpointMapping()` là mapping chuyên trách cho `@Action`; kiểm tra application context đúng version thay vì tự suy từ import.

### 8.5. Interceptor implicit của addressing mapping

Javadoc `AbstractAddressingEndpointMapping` nêu rằng nó có **interceptor WS-A nội bộ** trong `EndpointInvocationChain`. Vì vậy mapping không dùng cấu hình `interceptors` tiêu chuẩn theo đúng kiểu thông thường mà có **`preInterceptors`** và **`postInterceptors`** và quy tắc sắp xếp với các interceptors được tự phát hiện.

Đối với dịch vụ dùng WS-Security, validation và logging:

- Không đoán interceptor security sẽ chạy **trước** hay **sau** WS-A chỉ từ thứ tự `List` mà không xem implementation.
- Kiểm tra thứ tự thực tế ở framework version triển khai.
- Bảo đảm **security validation xảy ra trước hành động nhạy cảm**, đặc biệt nếu có non-anonymous `ReplyTo`/`FaultTo`.
- Không log raw Header chứa UsernameToken, SAML assertion hoặc dữ liệu ký nếu không có chính sách bảo mật rõ.

## 9. Quy trình thương lượng phiên bản: không có “auto-negotiation” mặc định

WS-Addressing không tự làm HTTP-style content negotiation giữa hai namespace. Client phải tạo một message đúng version, server phải nhận và tạo response/Fault đúng semantics. Khả năng server **hỗ trợ hai version** không có nghĩa client tự biết nên chọn bản nào trong mỗi call.

### 9.1. Ma trận client–server tối thiểu

| Client phát | Server chỉ 2004/08 | Server chỉ 1.0 | Server hỗ trợ cả hai |
| --- | --- | --- | --- |
| **August 2004** | Có thể tương thích, cần test policy. | **Không tương thích** WS-A theo namespace nếu không có adapter. | Có thể tương thích, phải kiểm tra response phiên bản 2004. |
| **W3C 1.0** | **Không tương thích** WS-A theo namespace nếu không có adapter. | Có thể tương thích, cần test policy. | Có thể tương thích, phải kiểm tra response phiên bản 1.0. |
| **Không có WS-A Header** | Tùy hợp đồng có bắt buộc WS-A hay không. | Tùy hợp đồng có bắt buộc WS-A hay không. | Hỗ trợ hai version **không có nghĩa** WS-A optional. |
| **WS-A Working Draft namespace khác** | Không mặc định. | Không mặc định. | Không mặc định trừ khi có implementation/adapter riêng. |

Cụm **“có thể tương thích”** là chủ đích: cùng addressing namespace **chưa đủ**. Hai phía còn phải khớp Action URI, WSDL/WS-Policy, anonymous response policy, Header mustUnderstand, EPR/reference parameters, SOAP version, TLS/WS-Security và Fault mappings.

### 9.2. Cách xác định version của một đối tác

Không hỏi chung “có WS-A không?”. Cần thu thập:

1. **Một SOAP request thật hoặc test fixture**, bao gồm namespace của `wsa:Action`/`To`.
2. **WSDL**, các `wsam:Action` hoặc `wsaw:Action`, WS-Policy assertions và tài liệu profile.
3. **SOAP version, HTTP headers và `soap:address`**.
4. **Quy tắc ReplyTo/FaultTo**: anonymous only, non-anonymous callback, hoặc `none`.
5. **Danh sách Action URI** cho input, output và Fault.
6. **Quy tắc MessageID/RelatesTo** và policy retry/correlation.
7. **WS-Security/mTLS requirements** và chữ ký có bao phủ WS-A Header không.
8. **SOAP client stack/version** (Spring-WS, JAX-WS/Metro, Apache CXF, Axis, WCF) và các cấu hình WS-A thực tế.

Chỉ sau khi có bằng chứng từ **hai phía**, mới đặt client `Addressing10` hay `Addressing200408` và giới hạn server mapping. **Tên sản phẩm** không đủ: WCF hoặc Apache CXF có thể được cấu hình hỗ trợ các profile khác nhau.

### 9.3. Không nên thử gửi hai phiên bản Header trong một Envelope

Một giải pháp tạm thường bị đề xuất là đưa cả:

~~~xml
<wsa04:Action xmlns:wsa04="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  urn:example:orders:v1/CreateOrder
</wsa04:Action>
<wsa10:Action xmlns:wsa10="http://www.w3.org/2005/08/addressing">
  urn:example:orders:v1/CreateOrder
</wsa10:Action>
~~~

vào cùng SOAP Header. **Không khuyến nghị**: có thể gây mơ hồ về phiên bản, duplicate addressing semantics, `mustUnderstand` Fault và chính sách chữ ký khó kiểm soát.

Cách phù hợp hơn là **một hợp đồng phiên bản rõ cho từng kết nối/partner**, hoặc một **gateway adapter có kiểm chứng** chuyển đổi toàn bộ WS-A metadata giữa các phiên bản, bao gồm EPR, response và Fault. Không coi chuyển đổi là đổi namespace string đơn giản.

## 10. Anonymous ReplyTo, non-anonymous ReplyTo và FaultTo

**Một trong những sai khác liên phiên bản dễ bỏ sót nhất** không nằm ở `wsa:Action` mà nằm ở **Endpoint References (EPR)** cho đường phản hồi. Cả hai phiên bản đều có khái niệm reply endpoint, nhưng **URI anonymous khác nhau**, và hệ thống còn có thể áp chính sách chỉ chấp nhận trả phản hồi trên HTTP connection gốc.

### 10.1. Anonymous response: mô hình request-response thông thường

Với WS-A 1.0:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
</wsa:ReplyTo>
~~~

Với August 2004:

~~~xml
<wsa04:ReplyTo
    xmlns:wsa04="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  <wsa04:Address>
    http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
  </wsa04:Address>
</wsa04:ReplyTo>
~~~

**Đừng chỉ thay namespace của `ReplyTo` mà giữ anonymous URI của phiên bản cũ**. Cả element QName lẫn value của `Address` cần theo addressing version.

Trong mô hình anonymous thông thường, SOAP server trả response hoặc Fault trên **HTTP response của request ban đầu**. Khi không có `ReplyTo`, ý nghĩa mặc định theo đặc tả/binding và cách framework triển khai phải được đối chiếu; không yêu cầu client tự chèn mọi Header nếu thư viện đã hỗ trợ mặc định.

### 10.2. Non-anonymous ReplyTo: server có thể gửi thông điệp mới

Ví dụ WS-A 1.0:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>https://callback.partner.example.test/soap/replies</wsa:Address>
</wsa:ReplyTo>
~~~

Với địa chỉ này, server có thể cần tạo **kết nối outbound riêng** đến callback endpoint, thay vì ghi normal response vào HTTP response của request ban đầu. Điều đó thay đổi kiến trúc:

~~~mermaid
sequenceDiagram
    participant C as Partner SOAP Client
    participant S as Orders SOAP Server
    participant O as Outbound Message Sender
    participant R as Partner Callback Endpoint

    C->>S: SOAP request / wsa:ReplyTo non-anonymous
    Note over S: Validate addressing + security + policy
    S-->>C: HTTP acknowledgement theo binding/policy
    S->>O: Tạo reply SOAP message
    O->>R: POST SOAP response / wsa:RelatesTo
    R-->>O: HTTP acknowledgement
~~~

Sơ đồ mô tả **một kiểu triển khai** callback, không cố định mọi status HTTP hoặc thời điểm xử lý. Với một số SOAP stacks, server có thể từ chối non-anonymous ReplyTo theo policy; không phải cứ thêm `ReplyTo` là có callback. Khi server gửi out-of-band, cần message sender, egress permission, TLS trust, retry/reliability strategy và endpoint availability ở callback side.

### 10.3. FaultTo là một đích riêng

`wsa:FaultTo` có thể quy định nơi nhận SOAP Fault, khác với `ReplyTo`. Nếu bị bỏ qua, Fault destination mặc định phụ thuộc spec/policy và reply properties đang có. Vì vậy phải kiểm tra **cả success response lẫn Fault**.

Ví dụ:

~~~xml
<wsa:FaultTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>https://callback.partner.example.test/soap/faults</wsa:Address>
</wsa:FaultTo>
~~~

Đối tác có thể chấp nhận success callback nhưng không có endpoint nhận Fault. Hoặc server chỉ cho phép anonymous Fault; khi đó request nêu FaultTo non-anonymous có thể bị từ chối do policy. Tương thích yêu cầu **đường thành công và đường lỗi cùng được thống nhất**.

### 10.4. URI none của WS-A 1.0 khác anonymous

WS-A 1.0 có URI đặc biệt:

~~~text
http://www.w3.org/2005/08/addressing/none
~~~

Giá trị **none** không phải một URL callback thông thường và **không tương đương anonymous**. Việc sử dụng nó phụ thuộc message exchange pattern và WS-A Metadata policy. Đừng đặt `ReplyTo=none` trong một operation có output bắt buộc rồi mong HTTP response chứa `CreateOrderResponse`.

Cũng đừng sao chép `none` URI của 1.0 sang August 2004 khi đối tác legacy không hỗ trợ semantics đó.

## 11. Ranh giới bảo mật: ReplyTo/FaultTo có thể tạo SSRF

Một SOAP request đến từ mạng có thể chỉ định một địa chỉ ReplyTo hoặc FaultTo ngoài ý muốn:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>http://127.0.0.1:9999/internal</wsa:Address>
</wsa:ReplyTo>
~~~

**Đây là ví dụ địa chỉ cần từ chối**, không phải đích để gọi thử trên hệ thống thật. Nếu server tự gửi SOAP response/Fault đến mọi URI do client cung cấp, nó có thể bị lợi dụng để truy cập mạng nội bộ, metadata service, loopback hoặc các hệ thống không liên quan, gây **server-side request forgery (SSRF)** và rò dữ liệu.

### 11.1. Security policy đối với địa chỉ callback

| Kiểm soát | Mục đích |
| --- | --- |
| Allowlist hostname/scheme/port | Chỉ gửi callback tới endpoint hợp đồng đã duyệt. |
| HTTPS và xác minh hostname/chứng chỉ | Bảo vệ kết nối, chống gửi response tới peer giả. |
| Kiểm tra IP/resolution/redirect | Chống loopback, private/link-local, DNS rebinding và chuyển hướng đến đích cấm. |
| Authentication/authorization | Chỉ đối tác có quyền mới được yêu cầu callback; sender có identity phù hợp. |
| Giới hạn outbound connections/timeouts | Tránh lạm dụng tài nguyên hoặc DoS. |
| Quản lý FaultTo tách biệt | Không gửi Fault detail chứa thông tin nhạy cảm sang đích không đáng tin. |
| MessageID/RelatesTo tracing | Ghép response async với request đúng, không dùng ID như credential. |
| Egress firewall/network policy | Một lớp phòng vệ độc lập với XML validation. |

Theo Javadoc Spring-WS 4.1.4, `AbstractAddressingEndpointMapping` có thuộc tính **`messageSenders`** cho out-of-band replies. Các sender kiểm tra `WebServiceMessageSender.supports(URI, UriSource.REMOTE)` khi xử lý ReplyTo/FaultTo do bên ngoài đưa vào. Reference 4.1.4 còn mô tả **`DestinationPolicy`** để kết hợp rule của ứng dụng với kiểm tra mặc định ở sender thích hợp.

**Không tắt kiểm tra URI remote để “cho callback chạy được”**. Nếu quy tắc mặc định không khớp môi trường, cần thiết kế allowlist cụ thể, kiểm thử mọi trường hợp và chỉ sau đó điều chỉnh destination policy.

### 11.2. WS-Security phải chạy trước phản hồi out-of-band nhạy cảm

Một request không được xác thực có thể chứa `ReplyTo`/`FaultTo` do attacker chọn. Nếu server cố gửi SOAP Fault hoặc response đến địa chỉ đó trước khi kiểm tra danh tính/quyền, nó có thể trở thành proxy gửi dữ liệu ra ngoài.

Reference Spring-WS 4.1.4 lưu ý tương tác giữa **WS-Security interceptors** và **WS-Addressing interceptor** khi có out-of-band sender; thứ tự xử lý phải bảo đảm security được áp dụng trước việc kích hoạt gửi tới destination do peer cung cấp.

Bên cạnh đó:

- **TLS/mTLS** xác thực peer ở tầng kết nối, không tự xác minh mọi SOAP Header đã được ký.
- **WS-Security XML Signature** chỉ bảo vệ những phần tử nằm trong phạm vi signed references/policy. `ReplyTo`, `FaultTo` và `To` phải được bảo vệ nếu ứng dụng dùng chúng cho quyết định nhạy cảm.
- **MessageID** là metadata định danh thông điệp, không được dùng một mình làm credential hoặc authorization.
- **XML parser** cần ngăn XXE/external entities/oversized messages; địa chỉ callback còn cần **network egress controls**, không giải quyết chỉ bằng XSD.

### 11.3. Đổi phiên bản WS-A không được phá chữ ký XML

Nếu một SOAP Header đã được ký trong WS-Security, đổi:

~~~text
{http://schemas.xmlsoap.org/ws/2004/08/addressing}To
~~~

thành:

~~~text
{http://www.w3.org/2005/08/addressing}To
~~~

có thể làm thay đổi dữ liệu được ký, ảnh hưởng canonicalization và xác minh chữ ký. **Không chèn một bộ lọc thay namespace sau bước ký** rồi mong chữ ký vẫn hợp lệ.

Một gateway chuyển đổi phiên bản WS-A phải là thành phần được **ủy quyền**: hiểu semantics, giữ/đổi MessageID và RelatesTo có chủ đích, xác thực inbound message, xây lại outbound message và ký/bảo vệ theo policy của chặng mới nếu cần. Không để lớp log/transformer vô tình thay signed XML.

## 12. SOAP Fault do WS-Addressing version và routing

Không phải mọi lỗi WS-A đều tạo một Fault code giống nhau. SOAP version, addressing version, endpoint mapping, security interceptor và vị trí từ chối quyết định hình thức phản hồi.

### 12.1. Các nhóm Fault trong WS-A 1.0

Theo W3C WS-Addressing 1.0 SOAP Binding, các trường hợp có thể gặp:

| Nhóm Fault | Ý nghĩa | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| `wsa:InvalidAddressingHeader` | Header addressing không hợp lệ. | Sai cú pháp, trùng/thiếu thuộc tính theo policy, namespace/EPR không khớp. |
| `wsa:MessageAddressingHeaderRequired` | Thiếu Header addressing bắt buộc. | Client không bật WS-A hoặc Header bị gateway/handler bỏ. |
| `wsa:ActionNotSupported` | Action không được hỗ trợ tại endpoint. | Sai URI action, mapping, WSDL/policy hoặc WS-A namespace. |
| `wsa:DestinationUnreachable` | Destination không thể được định tuyến tới đích. | `To`, callback URI, resolver/transport; một số Fault là optional. |
| `wsa:EndpointUnavailable` | Endpoint tạm hoặc vĩnh viễn không sẵn sàng. | Availability, policy; Fault có thể có `RetryAfter` tùy implementation. |

Một số Fault ở chuẩn được đánh dấu **optional** về việc triển khai. Vì vậy không viết client theo giả định mọi Spring-WS server luôn trả chính xác tất cả các Fault code này. Nếu lỗi xảy ra trước addressing mapping (HTTP proxy, XML parser, TLS), client có thể chỉ nhận HTTP error hoặc network exception.

### 12.2. Ví dụ SOAP 1.2 ActionNotSupported

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
        <env:Subcode>
          <env:Value>wsa:ActionNotSupported</env:Value>
        </env:Subcode>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="vi">
          WS-Addressing Action không được hỗ trợ
        </env:Text>
      </env:Reason>
      <env:Detail>
        <wsa:ProblemAction>
          <wsa:Action>urn:example:orders:v1/Unknown</wsa:Action>
        </wsa:ProblemAction>
      </env:Detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

Đây là **mẫu giáo dục theo hình thức SOAP 1.2**, không phải output bảo đảm của Spring-WS. Với SOAP 1.1, cấu trúc `faultcode/faultstring/detail` khác; WS-A August 2004 có semantics/namespace Fault khác. Đừng ép client SOAP 1.1 đọc `env:Subcode` của SOAP 1.2.

### 12.3. Khi sai version nhưng server không báo ActionNotSupported

Client gửi Header `wsa04:Action` August 2004, server chỉ chấp nhận 1.0:

- Server có thể không tạo được **Message Addressing Properties** đúng version.
- Endpoint mapping có thể không tìm thấy handler.
- SOAP processor có thể trả `MustUnderstand` nếu Header bắt buộc không được xử lý.
- Security stack có thể từ chối trước mapping.
- Client có thể nhận SOAP Fault chung hoặc HTTP error, không có Fault chuyên biệt.

Do đó, **không xuất hiện `ActionNotSupported` không loại trừ mismatch version**. Phải xem namespace thực tế, mapping/version policy và vị trí failure trong pipeline.

### 12.4. Đọc Fault phía Spring-WS client

Spring-WS `WebServiceTemplate` dùng fault resolver để xử lý SOAP Fault; mặc định thường có `SoapFaultClientException`. Một pattern minh họa:

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.soap.client.SoapFaultClientException;

try {
    Object response = template.marshalSendAndReceive(
        request,
        callback
    );
    // Kiểm tra JAXB response và business status.
} catch (SoapFaultClientException ex) {
    QName code = ex.getFaultCode();

    // Ghi mã QName đã được kiểm soát; tránh dump raw SOAP
    // chứa WS-Security tokens hoặc dữ liệu nhạy cảm.
    logger.warn("SOAP Fault code={}", code);

    // Custom mapper của ứng dụng phân loại WS-A / security /
    // business Fault bằng QName + detail đã khai báo.
    throw mapRemoteFault(ex);
}
~~~

`template`, `request`, `callback`, `logger` và `mapRemoteFault` là các thành phần ứng dụng giả định. `javax.xml.namespace.QName` vẫn là API Java SE, không có `jakarta.xml.namespace.QName` tương đương.

Không so `faultstring`/`Reason` chứa câu tiếng Anh hoặc tiếng Việt để quyết định version; **Fault code QName, namespace và detail schema** bền hơn. Cũng không coi mọi HTTP `500` thành SOAP Fault: gateway có thể trả HTML/empty body, TLS failure có thể không có HTTP response.

## 13. Tương thích với SOAP client công nghệ khác

Spring-WS có thể tích hợp với JAX-WS/Metro, Apache CXF, Axis, WCF/.NET và các SOAP client khác, nhưng **mỗi stack có cấu hình WS-A riêng**.

| Stack phía đối tác | Những thông tin phải xác minh | Điều không nên suy đoán |
| --- | --- | --- |
| JAX-WS/Metro | WS-A feature/annotation, WSDL policy, phiên bản addressing, Action input/output/Fault. | Dùng JAX-WS thì chắc chắn bật WS-A 1.0 ở mọi operation. |
| Apache CXF | WS-A interceptors/features và policy, EPR, SOAP version, security chain. | Tự động hỗ trợ mọi working draft namespace. |
| Apache Axis 1/2 | Module/addressing version và serializer. | Cùng tên `Action` là cùng QName. |
| WCF/.NET | MessageVersion/AddressingVersion, binding type, WS-Policy, anonymous callbacks. | Tên WCF bảo đảm cùng version với Spring-WS mặc định. |
| Legacy WSE 3.0 | August 2004 support, reply/address behavior, WS-Security configuration. | Chỉ cần chuyển SOAPAction là đủ. |
| Spring-WS client | `ActionCallback` phiên bản nào, transport, WS-Security interceptors. | Default callback tự đàm phán với server. |
| Spring-WS server | `AnnotationActionEndpointMapping`, `setVersions`, `@Action`/`@Address`, interceptor order. | Có mapping trong thư viện nghĩa là đã được đăng ký/chọn trong ứng dụng. |

### 13.1. Tài liệu “supported” chưa chứng minh wire-level tương thích

Hai vendor cùng công bố “supports WS-Addressing 1.0” nhưng có thể khác:

- Mức độ bắt buộc `MessageID` và `ReplyTo` theo MEP.
- Action URI được công bố hoặc được tính theo default pattern.
- Anonymous/non-anonymous response policy.
- ReferenceParameters và EndpointReference metadata.
- Cách xử lý SOAP 1.1/1.2 và HTTP SOAPAction.
- Fault code/detail và WS-Security signatures.

Vì vậy phải có **mẫu SOAP request/response/Fault thực** và test hai đầu. Tương thích không thể được xác minh chỉ bằng việc constructor `new Addressing10()` compile được.

## 14. Ma trận kiểm thử tương thích hai phía

**Một ca SOAP Body đúng và HTTP `200` chưa chứng minh WS-A tương thích.** Bộ test cần kiểm tra **namespace request**, **routing**, **output Action**, **RelatesTo**, **anonymous/non-anonymous semantics**, **Fault**, SOAP version và WS-Security.

### 14.1. Bộ ca kiểm thử bắt buộc

| Ca thử | Request / điều kiện | Kỳ vọng cần xác nhận |
| --- | --- | --- |
| WS-A 1.0 đúng | `{http://www.w3.org/2005/08/addressing}Action`, To, MessageID đúng. | Server chọn endpoint; response/Fault dùng 1.0 nếu hợp đồng yêu cầu. |
| August 2004 đúng | `{http://schemas.xmlsoap.org/ws/2004/08/addressing}Action`. | Được chấp nhận chỉ khi mapping hỗ trợ 2004; response theo semantics 2004. |
| Client 2004 → server chỉ 1.0 | Header 2004 với Action URI chính xác. | **Không bị xử lý nhầm** như request WS-A 1.0; trả lỗi theo pipeline/policy. |
| Client 1.0 → server chỉ 2004 | Header 2005/08. | Không được nhận nhầm dựa trên local name đơn thuần. |
| Đổi prefix | `wsa` thành `a`, namespace không đổi. | Vẫn cùng QName; routing không phụ thuộc prefix. |
| Header bị thiếu | SOAP Body hợp lệ, không có WS-A Action. | Nếu WS-A required thì từ chối; nếu optional thì xử lý theo contract. |
| Có hai phiên bản Action | Header 2004 và 1.0 cùng Envelope. | Không tự chọn ngẫu nhiên; chính sách duplicate/unsupported xử lý rõ. |
| Sai Action URI | WS-A version đúng, URI `UnknownOperation`. | Fault/không tìm endpoint như hợp đồng; không vào business method sai. |
| Sai To URI | Action đúng, To khác address được cho phép. | `@Address`/To validation từ chối hoặc routing theo policy. |
| SOAPAction mâu thuẫn | HTTP SOAPAction khác WS-A Action. | Kết quả xác định theo WSDL/SOAP binding; không silent misroute. |
| Sai SOAP version | SOAP 1.2 Envelope gửi vào binding chỉ SOAP 1.1. | Lỗi version/transport thích hợp, không nhầm với WS-A 2004. |
| Anonymous ReplyTo 1.0 | `.../2005/08/addressing/anonymous`. | Response cùng HTTP exchange theo contract. |
| Anonymous ReplyTo 2004 | `.../2004/08/addressing/role/anonymous`. | Response đúng version 2004 khi hỗ trợ. |
| Non-anonymous ReplyTo hợp lệ | Callback URI đã allowlist, peer xác thực. | Callback được gửi đúng destination, có RelatesTo và action mong đợi. |
| Non-anonymous ReplyTo không hợp lệ | Loopback/private host, redirect cấm. | Server không gửi outbound request, Fault/error theo policy. |
| FaultTo khác ReplyTo | Cả hai được khai báo. | Fault đi đúng địa chỉ đã cho phép, không bị gửi lạc. |
| MessageID/RelatesTo | Request ID A, response ID B. | Response RelatesTo = A, B khác A khi là message mới. |
| WS-Security đã ký WS-A Header | Chữ ký bao phủ Action/To/ReplyTo theo policy. | Pass khi chưa sửa; fail khi sửa dữ liệu ký. |
| WS-Security sai | Chữ ký/token/tenant identity không hợp lệ. | Không thực thi nghiệp vụ hoặc callback nhạy cảm. |
| XSD response đúng | Body JAXB theo XSD, Header WS-A đúng. | Client unmarshal output và liên kết reply. |
| SOAP Fault | Sai Action/To hoặc business exception. | Client phân loại đúng SOAP 1.1/1.2 Fault, không lấy faultstring làm key. |
| Retry/timeouts | Request có side effect bị mất response. | Không tạo đơn trùng; idempotency xử lý riêng khỏi WS-A. |
| Load/concurrency | Nhiều request có MessageIDs khác nhau. | Không trộn RelatesTo/ReplyTo và metadata giữa request đồng thời. |

**Kết quả đạt phải được định nghĩa cho từng đối tác**. Đừng cho rằng test 2004/08 phải pass nếu server cố tình chỉ chấp nhận WS-A 1.0, hoặc ngược lại. Test đúng là chứng minh server **chấp nhận/không chấp nhận theo policy đã công bố**, không phải cố pass mọi phiên bản.

### 14.2. Test server với MockWebServiceClient và full SOAP Envelope

Một test chỉ dùng `withPayload(...)` thường không tạo đầy đủ WS-A Header. Nếu mục tiêu là kiểm tra **Action namespace và MessageID**, hãy tạo full SOAP Envelope với `RequestCreators.withSoapEnvelope(...)` của Spring-WS Test (có trong API 4.1.4).

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withSoapEnvelope;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

// applicationContext phải chứa @Endpoint, AnnotationActionEndpointMapping,
// JAXB adapter, SOAP message factory và service stub cần thiết.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

String soapXml = """
    <soap:Envelope
        xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:wsa="http://www.w3.org/2005/08/addressing"
        xmlns:ord="urn:example:orders:v1">
      <soap:Header>
        <wsa:To>http://localhost/ws</wsa:To>
        <wsa:Action>urn:example:orders:v1/CreateOrder</wsa:Action>
        <wsa:MessageID>urn:uuid:3d2d8d01-a914-4f25-a63f-c7400825f321</wsa:MessageID>
      </soap:Header>
      <soap:Body>
        <ord:CreateOrderRequest>
          <ord:clientOrderId>WEB-20261127-0042</ord:clientOrderId>
          <ord:amount>1250000.00</ord:amount>
          <ord:currency>VND</ord:currency>
        </ord:CreateOrderRequest>
      </soap:Body>
    </soap:Envelope>
    """;

client.sendRequest(withSoapEnvelope(new StringSource(soapXml)))
      .andExpect(noFault());
~~~

Đây là **đoạn test minh họa** với Java text block (JDK 15+), Spring-WS Test, JUnit/context tương ứng và JAXB DTO theo contract; không phải chương trình Java độc lập. `noFault()` chỉ xác nhận không có SOAP Fault. Cần bổ sung assertions cho **response Header QName, output Action, RelatesTo và Body schema** để khẳng định tương thích đầy đủ.

Đặc biệt, `<wsa:To>http://localhost/ws</wsa:To>` phải phù hợp `@Address`/mapping của test. Nếu server có policy To khác, thay bằng URI được thỏa thuận thay vì bỏ kiểm tra To cho test pass.

Để kiểm thử August 2004, tạo fixture tương ứng, đổi **cả namespace header và anonymous URI** khi có `ReplyTo`. Đừng dùng một đoạn string replace qua toàn bộ XML rồi tự nhận đã test được semantics của phiên bản khác.

### 14.3. Test client với MockWebServiceServer

Phía client, `MockWebServiceServer` có thể kiểm tra `WebServiceTemplate` tạo đúng WS-A `Action`. Các matchers của Spring-WS Test hỗ trợ kiểm tra sự tồn tại của SOAP Header theo QName.

~~~java
import java.net.URI;
import javax.xml.namespace.QName;

import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

import static org.springframework.ws.test.client.RequestMatchers.soapHeader;
import static org.springframework.ws.test.client.RequestMatchers.anything;

// template và JAXB request đã được cấu hình trong test.
MockWebServiceServer server =
    MockWebServiceServer.createServer(template);

server.expect(soapHeader(new QName(
    "http://www.w3.org/2005/08/addressing", "Action"
)));

// Cần cấu hình .andRespond(...) bằng response SOAP hợp lệ
// trước khi thực thi request; đoạn này chỉ nêu matcher cần dùng.
~~~

**Không chạy đoạn test này độc lập**: test thực phải có response creator (`withPayload` hoặc `withSoapEnvelope`), callback, lời gọi gửi và `server.verify()`. `soapHeader(QName)` chỉ xác nhận Header tồn tại; muốn kiểm tra giá trị Action URI, dùng matcher XPath namespace-aware hoặc so XML message trong test phù hợp, không chỉ assert local name.

**Lưu ý quan trọng:** `MockWebServiceServer` thường thay sender thật bằng mock sender, vì vậy không chứng minh HTTP/TLS/proxy hoặc non-anonymous callback network hoạt động. Những phần đó cần integration test qua transport thật.

### 14.4. Test HTTP và SOAP message thực tế

Với một SOAP service test được công bố ở `http://localhost:8080/ws`, lưu bản tin **đầy đủ** ở mục 3 vào file `request.xml` UTF-8 và dùng:

~~~powershell
curl.exe --include --request POST --header 'Content-Type: text/xml; charset=utf-8' --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' --data-binary '@request.xml' "http://localhost:8080/ws"
~~~

URL, SOAPAction và cả SOAP Envelope đều là **minh họa**; hãy đối chiếu WSDL `soap:address`, SOAP binding và XSD của server test. Lệnh curl không tự tạo WS-A headers: chúng phải nằm **trong SOAP Header của file request.xml**.

Kiểm tra **cả HTTP status, SOAP Envelope, response/Fault headers và log correlation**. Nếu nhận HTTP `500` với SOAP Fault, phân loại theo Fault QName; nếu nhận HTML `502`/`504` từ gateway, đó chưa chắc là SOAP Fault. Nếu mTLS/TLS handshake fail, có thể chưa có SOAP response.

### 14.5. Test non-anonymous ReplyTo cần kiểm tra egress thực

Đối với out-of-band callback, mock endpoint test không đủ. Tạo callback receiver do test kiểm soát, giới hạn destination trong allowlist và xác minh:

1. ReplyTo non-anonymous được chấp nhận **chỉ khi** policy cho phép.
2. Server thực hiện outbound call đến đúng URI đã thỏa thuận.
3. SOAP callback có đúng addressing version, output Action và `RelatesTo`.
4. Callback receiver xác minh WS-Security/TLS phù hợp và nhận đúng payload schema.
5. `FaultTo` đi theo đường riêng khi business/validation Fault phát sinh.
6. URI loopback, private, link-local, redirects bị cấm đều **không được gửi**.
7. Thất bại khi callback network down được log và retry/queue theo contract mà không phát sinh side effect lặp.

**Không dùng địa chỉ ngoài Internet của một bên thứ ba để test callback**; hãy sử dụng test receiver được kiểm soát và thông tin giả.

## 15. Troubleshooting: phát hiện sai version trước khi sửa code

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra cụ thể |
| --- | --- | --- |
| `@Action` không gọi vào method | WS-A namespace khác version, Action URI không match, mapping không đăng ký. | Capture Header QName; xem `AnnotationActionEndpointMapping` và `setVersions`. |
| Client phát Action 1.0 khi đối tác đòi 2004 | Dùng constructor `new ActionCallback(String)` mặc định `Addressing10`. | Dùng explicit `new Addressing200408()` và test outgoing Header. |
| Chỉ sửa prefix vẫn lỗi | Prefix không thay namespace URI. | So `{namespace}Action`, không so chữ `wsa`. |
| SOAP Body hợp lệ nhưng WS-A Fault | Sai Action/To/MessageID/ReplyTo hoặc policy yêu cầu Header. | Xem SOAP Header, WSDL action metadata và response policy. |
| HTTP SOAPAction đúng nhưng WS-A Action thiếu | Hai cơ chế action ở tầng khác nhau. | Kiểm tra `ActionCallback`, không chỉ `SoapActionCallback`. |
| Header 2004 parse được, response bị client bỏ | Server tạo output Header 1.0 hoặc RelatesTo sai. | Capture response SOAP Envelope, so namespace + output Action. |
| `MustUnderstand` Fault | Receiver không xử lý Header bắt buộc/role. | QName, actor/role, endpoint mapping, security processors. |
| `ActionNotSupported` Fault | Action URI không được map hoặc WS-A version sai. | So URI exact, SOAPAction, WSDL/policy và mapping order. |
| `DestinationUnreachable` | To/callback EPR URI sai hoặc network/policy chặn. | Tách logical To và HTTP address, kiểm tra egress. |
| Callback gửi tới URI không mong muốn | Tin non-anonymous ReplyTo/FaultTo chưa validate. | Dừng outbound, kiểm tra policy allowlist, security và audit. |
| Server trả XML thành công nhưng client timeout | Non-anonymous policy khác kỳ vọng đồng bộ hoặc network mất response. | Check ReplyTo, HTTP status, callback logs và message correlation. |
| `RelatesTo` không tìm được request | MessageID mới không được ghi hoặc namespace version không thống nhất. | Compare request MessageID và response RelatesTo cùng version. |
| SOAP 1.2 Fault parser lỗi | Client đang parse `faultcode` của SOAP 1.1. | SOAP message factory, Content-Type và Fault Code/Subcode. |
| WSDL có `wsam:Action` nhưng client không gửi WS-A | Action attribute không tự đồng nghĩa WS-A required. | WS-Policy `wsam:Addressing`, generator configuration/feature. |
| WCF/Axis không tương thích | Vendor default WS-A version hoặc metadata dialect khác. | Lấy full captured SOAP messages, không suy từ tên stack. |
| WS-Security fail sau upgrade WS-A | Header đã ký đổi QName/URI, WS-Security references không khớp. | Verify signed parts/policy, ký lại tại đúng trust boundary. |
| HTTP `404/415` trước SOAP mapping | Sai URL, Content-Type hoặc SOAP version. | WSDL `soap:address` và HTTP transport; không sửa WS-A trước. |
| Retry tạo đơn trùng | Nhầm MessageID/correlation với idempotency key. | Chống trùng ở tầng nghiệp vụ với transaction store. |

### 15.1. Quy trình debug từ ngoài vào trong

~~~text
1. HTTP endpoint, TLS/certificate, Content-Type và SOAP version
2. SOAP Envelope có parse được không?
3. WS-A Header namespace 2004/08 hay 2005/08?
4. Action URI và To có khớp WSDL/policy/server mapping?
5. MessageID, ReplyTo, FaultTo, anonymous URI có đúng version?
6. @Action/@Address/AnnotationActionEndpointMapping và order?
7. WS-Security/validation/interceptor có từ chối trước method?
8. Response/Fault dùng version nào, output Action và RelatesTo gì?
9. Client có parse được response và nối với request không?
10. Nếu có retry/async: callback, idempotency và tracing ra sao?
~~~

Ghi lại **tầng cuối cùng còn đúng** thay vì sửa ngẫu nhiên nhiều giá trị: HTTP SOAPAction, SOAP Body QName, WS-A Action và WSDL policy cùng lúc. Thay một nhóm yếu tố tại một thời điểm giúp xác định nguyên nhân thực.

## 16. Bài thực hành theo tình huống

### Bài A — Cùng URI Action, khác namespace

Client A gửi:

~~~xml
<a:Action xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  urn:example:orders:v1/CreateOrder
</a:Action>
~~~

Client B gửi:

~~~xml
<b:Action xmlns:b="http://www.w3.org/2005/08/addressing">
  urn:example:orders:v1/CreateOrder
</b:Action>
~~~

**Câu hỏi:** hai client có gửi cùng WS-A Action Header không?

**Đáp án:** Không, vì QName gồm **namespace + local name**, dù text của action URI và local name giống nhau. Client A dùng August 2004; client B dùng W3C 1.0. Đổi prefix `a`/`b` không làm chúng tương thích; cần chọn đúng `AddressingVersion` ở client và đảm bảo server hỗ trợ bản đó.

### Bài B — Spring-WS client dùng callback mặc định

Code:

~~~java
new ActionCallback("urn:example:orders:v1/CreateOrder")
~~~

Đối tác WSE 3.0 yêu cầu namespace `http://schemas.xmlsoap.org/ws/2004/08/addressing`.

**Đáp án:** Theo Javadoc Spring-WS 4.1.4, constructor chỉ có action **mặc định `Addressing10`**, nên sẽ tạo Header W3C 1.0. Sửa thành `new ActionCallback(URI.create(action), new Addressing200408())`, rồi kiểm thử Header XML trên wire và response headers. Không chỉ sửa HTTP SOAPAction.

### Bài C — SOAP 1.1 + WS-A 1.0

Một nhóm nói rằng “SOAP Envelope 1.1 thì phải dùng WS-A 2004”. Nhóm khác đề xuất SOAP 1.1 Envelope với Header `http://www.w3.org/2005/08/addressing`.

**Đáp án:** WS-A 1.0 SOAP Binding được thiết kế tương thích với SOAP 1.1 và SOAP 1.2; đây là **hai trục phiên bản độc lập**. Cần xem WSDL SOAP binding, media type và WS-A policy thực, không suy version WS-A chỉ từ Envelope namespace.

### Bài D — WSDL có wsam:Action nhưng client bỏ Header

WSDL có:

~~~xml
<wsdl:input
    message="tns:CreateOrderInput"
    wsam:Action="urn:example:orders:v1/CreateOrder"/>
~~~

nhưng không có policy nào cho biết WS-A là bắt buộc. Client JAX-WS phát Body đúng, không có WS-A Header.

**Đáp án:** Chỉ có `wsam:Action` không mặc định đồng nghĩa WS-A **required**. Phải xem **WS-Policy assertion `wsam:Addressing`**, binding profile và hợp đồng đã thỏa thuận. Nếu server thật sự yêu cầu WS-A, cần công bố/cấu hình rõ và kiểm thử client generator.

### Bài E — ReplyTo có anonymous URI của bản cũ

Client tạo `wsa:ReplyTo` QName 2005/08 nhưng con `wsa:Address` vẫn chứa:

~~~text
http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
~~~

**Đáp án:** Đây là **trộn semantics hai phiên bản**. WS-A 1.0 anonymous URI là `http://www.w3.org/2005/08/addressing/anonymous`. Không chỉ đổi QName Header; phải cập nhật EPR address và các phần liên quan theo version mới.

### Bài F — Response trả nhầm phiên bản

Server hỗ trợ hai version ở inbound mapping. Client August 2004 gửi request thành công, server trả response đúng XML Body nhưng `RelatesTo` lại ở namespace 2005/08.

**Đáp án:** **Tương thích chưa hoàn chỉnh**. Phải xác minh response WS-A version, output Action, RelatesTo, anonymous URI và client correlation. Dùng test client legacy thật hoặc fixture SOAP response từ đối tác để bắt lỗi outbound mapping.

### Bài G — Out-of-band callback tới địa chỉ nội bộ

Một request chưa được xác thực có:

~~~xml
<wsa:FaultTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>http://127.0.0.1:8081/private</wsa:Address>
</wsa:FaultTo>
~~~

**Đáp án:** Không gửi Fault đến địa chỉ đó. Đây là **destination không đáng tin** và có nguy cơ SSRF. Cần authenticate/authorize và áp allowlist, URL/IP/redirect/egress policy theo implementation Spring-WS, trước khi gửi out-of-band message. XML schema validation một mình không đủ.

### Bài H — Retry sau timeout

Một request `CreateOrder` gửi với `MessageID=A`, server tạo đơn nhưng response bị mất. Client muốn retry với `MessageID=B` và **idempotency key mới**, vì cho rằng “message mới thì nghiệp vụ mới”.

**Đáp án:** Phải tách **message identity** khỏi **business intent**. Retry cùng ý định cần giữ idempotency key và tra cứu/lưu kết quả trên server để tránh tạo đơn trùng. MessageID mới hay giữ nguyên theo quy tắc retransmission/contract, nhưng không thay thế idempotency protection.

## 17. Kế hoạch nâng cấp từ August 2004 sang W3C 1.0

Nâng phiên bản WS-A trong một hệ thống đang hoạt động không phải thay một dòng namespace trên SOAP XML. Nên tiến hành theo các giai đoạn sau:

### 17.1. Khảo sát trạng thái hiện tại

Xác định toàn bộ:

- Client nào gửi August 2004, client nào đã gửi WS-A 1.0.
- Hệ thống backend nào bắt buộc anonymous response và hệ thống nào dùng callback.
- Input/output/Fault Action URIs; WSDL bindings và WS-Policy dialects đang được công bố.
- `@Action`, `@Address`, `AnnotationActionEndpointMapping`, `setVersions` ở Spring-WS server.
- Client `ActionCallback` constructors/configuration, WCF binding và các SOAP handler của đối tác.
- Thứ tự WS-Security/WS-A interceptors và phần Header nào nằm trong XML Signature references.
- Test fixtures bản tin **success và Fault** của cả hai phiên bản.
- Các log correlation/MessageID/RelatesTo đang được sử dụng để điều tra sự cố.

Không dùng bản WSDL được lưu trên máy phát triển làm bằng chứng duy nhất; lấy **WSDL được công bố tại môi trường đích** và policy/imports đi kèm.

### 17.2. Xác định chiến lược rollout

| Chiến lược | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Server tạm hỗ trợ cả 2004 và 1.0 | Nhiều client migrate theo đợt; mapping hỗ trợ hai version. | Response version/policy phải đúng từng client; bảo mật không bị nới lỏng. |
| Hai logical endpoints hoặc gateway routes | Cần phân tách khách hàng legacy và mới. | Tăng cấu hình, WSDL/certificate/monitoring cần quản trị. |
| Gateway chuyển đổi WS-A có kiểm chứng | Không thể sửa ngay client legacy. | Phải hiểu EPR, MessageID, RelatesTo, signature, non-anonymous callback; rủi ro bảo mật cao nếu chỉ rewrite XML. |
| Big-bang switch một phiên bản | Tất cả đối tác đã được kiểm thử và có khả năng đổi đồng thời. | Dễ gây downtime nếu còn một client chưa nâng cấp. |

Chọn một chiến lược theo số đối tác, mức độ phụ thuộc legacy, chính sách WS-Security, callback và độ rủi ro được chấp nhận.

### 17.3. Kiểm thử trước khi chuyển

Các bước cụ thể:

1. Giữ snapshot hợp đồng WSDL/XSD và captured SOAP fixtures **đã che dữ liệu nhạy cảm**.
2. Thêm test W3C 1.0 với input/output/Fault Action, MessageID/RelatesTo, To và ReplyTo.
3. Thêm test negative để đảm bảo namespace 2004 chỉ được nhận nếu policy cho phép.
4. Kiểm tra client Spring-WS, JAX-WS/Metro, CXF, WCF/.NET với WSDL/Policy thật.
5. Kiểm tra SOAP 1.1/1.2 và HTTP status/Fault classification.
6. Kiểm tra WS-Security ký đúng Header sau khi thay version; không sửa signed XML.
7. Kiểm tra callback out-of-band, egress allowlist, TLS/mTLS và FaultTo.
8. Giữ timeout/retry/idempotency semantics, không để chuyển WS-A gây side effect lặp.
9. Deploy canary/partner opt-in nếu phù hợp, theo dõi tỷ lệ Fault và lỗi endpoint mapping.
10. Có rollback route/version theo trạng thái đã được kiểm thử.

### 17.4. Tiêu chí hoàn thành migration

Migration **chỉ được coi là hoàn tất** khi:

- Tất cả client theo hợp đồng mới gửi đúng namespace WS-A 1.0.
- Server đọc được request và phát response/Fault đúng version, output Action và RelatesTo.
- WSDL/policy public phản ánh hành vi thật, không mâu thuẫn với HTTP SOAPAction.
- Không còn logic bảo mật cho phép URI ReplyTo/FaultTo không đáng tin.
- Các client legacy đã được chuyển, được giữ trên route riêng hoặc có thời hạn sunset rõ.
- Logs/metrics có thể phân biệt WS-A version mismatch với SOAP Fault nghiệp vụ và transport errors.
- Các bài test XSD/WSDL/JAXB/WS-Security/certificate/interoperability đều pass trong môi trường đại diện.

## 18. Checklist cuối bài và tài liệu chuẩn

### 18.1. Checklist xác nhận hai phía đã tương thích

| Câu hỏi kiểm tra | Điều kiện đạt |
| --- | --- |
| Phiên bản WS-A đã thống nhất? | Chọn **2004/08** hoặc **W3C 1.0**, không ghi chung chung “WS-A enabled”. |
| Namespace Header chính xác? | `Action/To/MessageID/RelatesTo/ReplyTo/FaultTo` có QName đúng version. |
| Không nhầm prefix? | Parser/mapping so QName namespace URI, không so chữ `wsa`. |
| WSDL/WS-Policy phản ánh hợp đồng? | Action input/output/fault, addressing requirement và reply policy rõ ràng. |
| SOAP version khác trục WS-A? | SOAP 1.1/1.2, Content-Type, Fault structure đúng binding. |
| HTTP SOAPAction có nhất quán? | So với `wsa:Action` và WSDL SOAP binding khi cần. |
| Spring-WS client chọn version? | `ActionCallback` dùng `Addressing10`/`Addressing200408` rõ ràng. |
| Spring-WS server chọn version? | `AnnotationActionEndpointMapping` và `setVersions` tương thích với partner. |
| Không có mapping cạnh tranh? | `@Action`, `@PayloadRoot`, `@SoapAction` không misroute do order. |
| To và endpoint address hợp lệ? | Logical `To` khớp policy/reverse proxy/`@Address` nếu dùng. |
| Message correlation đúng? | Reply có output Action/RelatesTo; MessageID khác theo message identity. |
| Anonymous URI theo đúng bản? | 2004/08 và 1.0 không bị trộn. |
| Callback chỉ gửi tới đích tin cậy? | Allowlist/destination policy, egress control, TLS/mTLS và auth. |
| WS-Security bảo vệ Header cần thiết? | Chữ ký được xác minh đúng scope; không mutate signed Header sau ký. |
| SOAP Fault được phân loại? | Fault QName/Code/Detail theo version, không lệ thuộc faultstring. |
| Idempotency độc lập WS-A? | Timeout/retry không tạo giao dịch trùng nhờ logic nghiệp vụ. |
| Test hai chiều đã chạy? | Request, response, Fault, negative version và client khác công nghệ. |
| Có kế hoạch migration/rollback? | Nếu đổi version, có canary, monitoring và đường quay lại. |

### 18.2. Tài liệu kỹ thuật nên đối chiếu

Những nguồn chính thức này giúp kiểm chứng namespace, semantics và API theo đúng phiên bản:

- **W3C — [WS-Addressing Member Submission, 10/08/2004](https://www.w3.org/submissions/ws-addressing/)**: namespace August 2004, anonymous URI và các message properties lịch sử.
- **W3C — [WS-Addressing 1.0 Core](https://www.w3.org/TR/ws-addr-core/)**: endpoint references và Message Addressing Properties.
- **W3C — [WS-Addressing 1.0 SOAP Binding](https://www.w3.org/TR/ws-addr-soap/)**: biểu diễn SOAP Headers, processing rules và addressing Faults.
- **W3C — [WS-Addressing 1.0 Metadata](https://www.w3.org/TR/ws-addr-wsdl/)**: `wsam:Action`, WSDL 1.1/2.0, `wsam:Addressing` và policy response.
- **Spring-WS — [Reference 4.1.4, WS-Addressing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: `AnnotationActionEndpointMapping`, `@Action`, `ActionCallback` và out-of-band replies.
- **Spring-WS — [ActionCallback API 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/addressing/client/ActionCallback.html)**: constructors, version mặc định, To/ReplyTo/FaultTo và MessageID strategy.
- **Spring-WS — [AddressingVersion package 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/version/package-summary.html)**: `Addressing10` và `Addressing200408`.
- **Spring-WS — [AbstractAddressingEndpointMapping API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/addressing/server/AbstractAddressingEndpointMapping.html)**: `setVersions`, callback messageSenders và interceptor order.
- **Spring-WS — [RequestCreators API 4.1.x](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/test/server/RequestCreators.html)**: `withSoapEnvelope` để test full SOAP Header.

Các liên kết tham chiếu ghi rõ phiên bản Spring-WS vì API và defaults có thể thay đổi. Đối với hệ thống cụ thể, **JAR, WSDL và SOAP message thực tế tại môi trường chạy** mới quyết định điều gì cần được kiểm thử.

### Ghi nhớ

- **WS-Addressing August 2004** có namespace `http://schemas.xmlsoap.org/ws/2004/08/addressing`; **W3C WS-Addressing 1.0 (May 2006)** có namespace `http://www.w3.org/2005/08/addressing`. Hai QName `wsa:Action` khác phiên bản **không tương đương**.
- **SOAP 1.1/1.2, WS-A 2004/1.0, WSDL/XSD và HTTP là bốn trục độc lập**. Đừng suy WS-A version từ SOAP version, HTTP status hoặc tên operation.
- **Tương thích phải hai chiều**: client gửi đúng `Action/To/MessageID/ReplyTo`, server xử lý đúng rồi trả output/Fault với `Action/RelatesTo`, anonymous URI và security policy phù hợp phiên bản.
- **Spring-WS `ActionCallback` mặc định dùng `Addressing10`** khi chỉ chỉ định action; dùng `new Addressing200408()` rõ ràng cho đối tác August 2004. Server `AnnotationActionEndpointMapping` trong phiên bản được tài liệu hóa có thể hỗ trợ cả hai, nhưng cần xác nhận configuration đang chạy.
- **`wsam:Action` trong WSDL không tự biến WS-A thành bắt buộc**; phải kiểm tra WS-Policy, HTTP SOAPAction, binding và client generator.
- **Non-anonymous `ReplyTo`/`FaultTo` là một trust boundary**: phải kiểm tra destination allowlist, WS-Security/TLS, egress và SSRF trước khi gửi callback.
- **MessageID/RelatesTo hỗ trợ liên kết thông điệp, không thay thế idempotency hoặc authorization**. Kiểm thử response, SOAP Fault, timeout/retry và client đa công nghệ là phần bắt buộc khi nâng cấp phiên bản.







