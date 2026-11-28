# Phản hồi cùng kênh, phản hồi khác kênh và phạm vi hỗ trợ theo phiên bản

## 1. Bài toán: SOAP response quay về đâu?

Trong Spring Web Services (Spring-WS), dịch vụ SOAP thường được xây **contract-first**: XSD/WSDL xác định cấu trúc thông điệp và operation, JAXB/OXM xử lý ánh xạ XML–Java, `@Endpoint` và `WebServiceTemplate` đảm nhiệm phía server/client. Trong tích hợp doanh nghiệp, thông điệp còn phải tuân SOAP Fault, interceptor, WS-Security, chứng chỉ và các quy tắc tương thích giữa hai bên.

HTTP request–response thông thường có một luồng rất dễ hiểu:

~~~text
Client --HTTP POST SOAP request--> Server
Client <--HTTP response SOAP Body-- Server
~~~

Nhưng một số hệ thống cần tiếp nhận yêu cầu rồi trả kết quả qua **địa chỉ callback khác**:

~~~text
Client --HTTP POST request--> Server
Client <--HTTP 202 Accepted-- Server

Client callback listener <--HTTP POST SOAP result-- Server
Client callback listener --HTTP acknowledgment--> Server
~~~

Hai kiểu này liên quan đến **WS-Addressing**, đặc biệt là địa chỉ `ReplyTo` và `FaultTo` trong SOAP Header. Tuy nhiên, WS-Addressing chỉ cung cấp **metadata định tuyến và liên hệ thông điệp**; nó không tự làm `WebServiceTemplate` trở thành máy chủ nhận callback, không tự tạo hàng đợi bền vững và không tự bảo đảm một callback sẽ đến.

Bài thuộc chương **WS-Addressing**, với chủ đề **“Phản hồi cùng kênh, phản hồi khác kênh và phạm vi hỗ trợ theo phiên bản”**. Trọng tâm là nhận diện hai mô hình transport, quyết định phạm vi hỗ trợ trong một triển khai Spring-WS cụ thể và tránh nhầm giữa các revision của WS-Addressing.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **same-channel reply** và **out-of-band reply**.
2. Đọc `To`, `Action`, `MessageID`, `ReplyTo`, `FaultTo` và `RelatesTo` theo đúng namespace.
3. Hiểu `anonymous` và địa chỉ callback không ẩn danh; không nhầm với endpoint SOAP HTTP.
4. Liên hệ WS-Addressing 1.0 (W3C 2005/08) và bản 2004/08 bằng bảng namespace/URI.
5. Biết giới hạn giữa WS-Addressing Header, SOAP 1.1/1.2 HTTP binding và khả năng của framework.
6. Tổ chức Spring-WS client/server để nhận hoặc gửi callback có correlation.
7. Kiểm tra WS-Addressing action, routing, reply/fault channels, bảo mật và tính tương thích.
8. Thiết kế bài kiểm thử cho success response, SOAP Fault, callback đến muộn, trùng lặp và sai version.

## 2. WS-Addressing định nghĩa thông tin gì?

WS-Addressing là tập đặc tả bổ sung **message addressing properties (MAPs)** và **endpoint references (EPRs)** cho SOAP. Nó cho phép thông điệp mô tả:

- Nó được gửi **đến đâu**?
- Nó đại diện **hành động/operation** nào?
- Nó có **định danh duy nhất** không?
- Khi cần trả kết quả, **gửi đến đâu**?
- Nếu lỗi, **gửi Fault đến đâu**?
- Một response liên hệ với **request nào**?

Các thuộc tính thường thấy:

| WS-Addressing property | SOAP Header điển hình | Ý nghĩa |
|---|---|---|
| Destination | `wsa:To` | Đích logic của message hiện tại |
| Action | `wsa:Action` | Action URI định danh ý nghĩa thông điệp |
| Message ID | `wsa:MessageID` | Định danh của message để liên hệ/khử trùng lặp |
| Reply endpoint | `wsa:ReplyTo` | Endpoint reference nhận reply |
| Fault endpoint | `wsa:FaultTo` | Endpoint reference nhận Fault |
| Relationship | `wsa:RelatesTo` | Liên hệ reply/Fault với message trước |
| From | `wsa:From` | Nguồn logic, khi contract/policy sử dụng |

Không phải mọi property đều bắt buộc trong mọi MEP và mọi revision. **Yêu cầu bắt buộc thực tế** phụ thuộc WS-Addressing Core, SOAP binding, WSDL/policy, action mapping và dạng response.

### 2.1. Endpoint reference không chỉ là một URL string

Một `ReplyTo` thường là một **EPR**:

~~~xml
<wsa:ReplyTo
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>
        https://client.example.test/soap/callbacks/orders
    </wsa:Address>
</wsa:ReplyTo>
~~~

EPR có thể còn mang **reference parameters** và metadata, tùy revision/contract. Vì vậy không nên thiết kế parser bằng cách lấy text của toàn bộ `ReplyTo` rồi cho rằng đó chỉ là URL; cần đọc đúng `Address` và chính sách về các tham số kèm theo.

### 2.2. SOAP Envelope và WS-Addressing Header là hai namespace khác nhau

Ví dụ SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header>
        <wsa:Action>urn:example:orders:action:GetOrder</wsa:Action>
    </soap:Header>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Có ba lớp QName:

1. SOAP Envelope/Body: `http://schemas.xmlsoap.org/soap/envelope/`.
2. WS-Addressing MAPs: `http://www.w3.org/2005/08/addressing`.
3. Business payload: `urn:example:orders:v1`.

Đổi prefix `wsa` thành `a` mà giữ namespace URI không đổi là thay đổi cách biểu diễn, không đổi QName. Nhưng đổi namespace từ WS-Addressing 1.0 sang 2004/08 **là đổi một revision giao thức**, không được coi là đổi prefix bình thường.

## 3. Bảng thuật ngữ: kênh, kết nối, endpoint và operation

Trong bài này:

| Khái niệm | Cách hiểu |
|---|---|
| **Same-channel** | Reply đi qua HTTP response của **request hiện tại** |
| **Different-channel / out-of-band** | Reply gửi thành một **SOAP message mới** đến endpoint khác, thường qua HTTP POST mới |
| **Anonymous ReplyTo** | Reply endpoint biểu thị kênh phản hồi cùng kênh theo quy tắc binding hỗ trợ |
| **Non-anonymous ReplyTo** | Reply endpoint có địa chỉ riêng như HTTPS callback URL |
| **FaultTo** | Địa chỉ logic nhận Fault; có thể khác ReplyTo theo chính sách |
| **MEP** | Message Exchange Pattern: mô hình trao đổi message, ví dụ request–response |
| **Callback listener** | Dịch vụ phía client nhận SOAP reply đến qua kết nối riêng |
| **Correlation** | Ghép response/Fault với request theo `MessageID` và `RelatesTo` |
| **Business async** | Xử lý nghiệp vụ lâu, được chạy qua job/queue; không đồng nghĩa tự động dùng khác kênh |

**Kênh** ở đây là quan hệ giữa request và response HTTP/SOAP, không phải channel của RabbitMQ hay JMS. Một response khác kênh thường dùng kết nối HTTP mới, không dựa trên TCP socket mà phía caller đã mở từ lần gửi yêu cầu đầu tiên.

### 3.1. Phản hồi cùng kênh có thể được xử lý bất đồng bộ bên trong server

Một server có thể dùng thread pool xử lý request rồi trả HTTP response trên kết nối ban đầu. Đối với phía client, nó vẫn là **same-channel reply**.

Ngược lại, một server nhận request, trả HTTP 202 và gửi callback 10 giây sau là **different-channel reply**. Việc này cần endpoint đón callback và correlation state riêng.

### 3.2. HTTP 202 không tự chứng minh xử lý bất đồng bộ thành công

`202 Accepted` thường được dùng trong mô hình một chiều/nhận việc và trả kết quả sau, nhưng:

- Không chứng minh server đã thực hiện nghiệp vụ thành công.
- Không chứng minh callback sẽ đến.
- Không chứng minh message đã được lưu bền vững.
- Không tự tương đương với SOAP success payload.
- Có thể cũng xuất hiện trong mô hình transport khác tùy contract.

Ứng dụng cần phân biệt **“request đã được chấp nhận để xử lý”** và **“nghiệp vụ đã hoàn tất”**.

## 4. Same-channel: ReplyTo anonymous

Trong WS-Addressing 1.0, địa chỉ anonymous thường dùng là:

~~~text
http://www.w3.org/2005/08/addressing/anonymous
~~~

Khi request–response exchange sử dụng anonymous reply endpoint, SOAP reply được trả trên **kênh phản hồi sẵn có** của transport. Với HTTP, đó là HTTP response cho request POST.

~~~mermaid
sequenceDiagram
    participant C as Spring-WS SOAP client
    participant S as SOAP server
    C->>S: HTTP POST + SOAP Request / wsa:ReplyTo anonymous
    S->>S: Validate XSD, xử lý nghiệp vụ
    S-->>C: HTTP response + SOAP Response / wsa:RelatesTo
    C->>C: JAXB unmarshal và kiểm tra correlation
~~~

### 4.1. Request SOAP minh họa

Ví dụ theo WS-Addressing **1.0**, SOAP 1.1 Envelope:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header>
        <wsa:To>
            https://partner.example.test/ws/orders
        </wsa:To>
        <wsa:Action>
            urn:example:orders:action:GetOrder
        </wsa:Action>
        <wsa:MessageID>
            urn:uuid:9ef4cf3a-8ab7-4e27-8f36-252ed852b581
        </wsa:MessageID>
        <wsa:ReplyTo>
            <wsa:Address>
                http://www.w3.org/2005/08/addressing/anonymous
            </wsa:Address>
        </wsa:ReplyTo>
    </soap:Header>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

`wsa:To` là địa chỉ logic của request; URI trong `wsa:ReplyTo/wsa:Address` là token anonymous đặc biệt, **không phải** HTTP URL mà client phải cố POST đến.

Đừng hiểu anonymous là “không có người gửi” hoặc “không xác thực”. Nó nói về **địa chỉ phản hồi gắn với transport**, không quyết định authentication.

### 4.2. Response thường nằm ngay trong HTTP response

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header>
        <wsa:Action>
            urn:example:orders:action:GetOrderResponse
        </wsa:Action>
        <wsa:RelatesTo>
            urn:uuid:9ef4cf3a-8ab7-4e27-8f36-252ed852b581
        </wsa:RelatesTo>
    </soap:Header>
    <soap:Body>
        <ord:GetOrderResponse>
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:status>PAID</ord:status>
        </ord:GetOrderResponse>
    </soap:Body>
</soap:Envelope>
~~~

Response này có `wsa:RelatesTo` trỏ về request `MessageID`. Khi một response cần được correlate, không dùng riêng `orderId` hoặc HTTP connection ID để chứng minh nó liên hệ với request nào.

### 4.3. Ưu điểm và hạn chế

**Ưu điểm:**

- Dễ tích hợp với `WebServiceTemplate.marshalSendAndReceive(...)`.
- Không cần client mở HTTP listener nhận callback từ Internet.
- SOAP Fault có thể đi trên cùng HTTP response.
- Vận hành, TLS egress và proxy đơn giản hơn.

**Hạn chế:**

- Caller chờ response trong suốt thời gian server xử lý.
- Dễ gặp response/read timeout khi operation lâu.
- Một lượt gọi đồng bộ giữ thread/kết nối cho đến khi hoàn tất.
- Không giải quyết được “nhận việc xong, trả kết quả hàng giờ sau” trừ khi thay đổi MEP/protocol.

### 4.4. ReplyTo vắng mặt có phải anonymous?

Trong WS-Addressing 1.0 Core, với request–response exchange, `ReplyTo` vắng mặt có quy tắc mặc định dùng anonymous endpoint theo ngữ cảnh. Tuy nhiên, **không được dựa vào quy tắc này khi WSDL/policy hoặc stack cụ thể yêu cầu Header có mặt rõ ràng**. Một số cổng tích hợp kiểm tra chặt bộ MAPs và yêu cầu `ReplyTo` explicit.

Việc omit header, dùng anonymous URI 1.0, hay dùng URI anonymous 2004/08 là **ba hình thức cần đối chiếu revision/policy**, không nên coi luôn tương đương trên mọi đối tác.

## 5. SOAP Fault cùng kênh: một reply nhưng là lỗi

Same-channel không bắt buộc response có business payload thành công. Nếu server phát hiện request sai hợp đồng, nó có thể trả SOAP Fault qua HTTP response hiện tại.

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <soap:Header>
        <wsa:Action>
            http://www.w3.org/2005/08/addressing/fault
        </wsa:Action>
        <wsa:RelatesTo>
            urn:uuid:9ef4cf3a-8ab7-4e27-8f36-252ed852b581
        </wsa:RelatesTo>
    </soap:Header>
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>GetOrderRequest không hợp lệ</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Đây là **Fault minh họa** cho WS-Addressing 1.0 với SOAP 1.1. `Action` của lỗi trong hệ thống thực tế phải phù hợp loại Fault và các quy tắc WS-A/WSDL/binding; không được mặc định mọi SOAP Fault của mọi service dùng một action nếu có khai báo Fault action riêng.

SOAP 1.2 Fault dùng `Code`, `Reason` và cú pháp khác. Không đưa XML Fault SOAP 1.1 cho client chỉ chấp nhận SOAP 1.2 rồi kết luận hệ thống WS-Addressing sai.

### 5.1. FaultTo có thể ảnh hưởng điểm đến lỗi

Nếu request có `FaultTo` explicit và hợp lệ, contract/policy có thể hướng Fault tới endpoint đó thay vì `ReplyTo`. Nếu không có `FaultTo`, WS-A có quy tắc mặc định về reply endpoint theo revision. Vì vậy **không thể luôn giả định lỗi được gửi đến cùng nơi với success reply**.

Đối với Spring-WS client, `FaultMessageResolver` và `ClientInterceptor.handleFault` có thể xử lý Fault **nhận trên kênh của WebServiceTemplate**. Nếu Fault được gửi qua callback khác kênh, cần một **receiver endpoint** riêng, không thể trông chờ lời gọi `marshalSendAndReceive` cũ tự nhận được nó.

## 6. Different-channel: ReplyTo có URL callback

Trong một yêu cầu cần trả kết quả khác kênh, client có thể gửi:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>
        https://client.example.test/ws/callback/orders
    </wsa:Address>
</wsa:ReplyTo>
~~~

Đây là **non-anonymous reply endpoint**. Trong mô hình hỗ trợ callback thực sự, server gửi SOAP response như một thông điệp mới tới URL đó, thường qua một HTTP POST mới.

~~~mermaid
sequenceDiagram
    participant A as Client gửi yêu cầu
    participant S as Partner SOAP server
    participant Q as Job store / queue
    participant C as Callback SOAP endpoint của client
    A->>S: POST GetOrderRequest / MessageID / ReplyTo callback
    S->>Q: Lưu job và correlation
    S-->>A: HTTP 202 / acknowledgment theo contract
    Q-->>S: Hoàn tất xử lý
    S->>C: POST GetOrderResponse / RelatesTo MessageID
    C->>C: Xác thực, đối chiếu correlation, xử lý kết quả
    C-->>S: HTTP acknowledgment
~~~

**Sơ đồ là một kiến trúc khả thi, không phải chức năng tự động có sẵn chỉ vì đã đặt `ReplyTo` trong SOAP Header.** Nhiều Spring-WS installations chỉ vận hành anonymous/same-channel request–response; non-anonymous reply đòi thêm phần mềm định tuyến, HTTP listener và chính sách bảo mật.

### 6.1. Request minh họa

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header>
        <wsa:To>
            https://partner.example.test/ws/orders
        </wsa:To>
        <wsa:Action>
            urn:example:orders:action:ProcessOrder
        </wsa:Action>
        <wsa:MessageID>
            urn:uuid:4073d98d-47da-4ff6-b8a0-5d509f60f594
        </wsa:MessageID>
        <wsa:ReplyTo>
            <wsa:Address>
                https://client.example.test/ws/callback/orders
            </wsa:Address>
        </wsa:ReplyTo>
        <wsa:FaultTo>
            <wsa:Address>
                https://client.example.test/ws/callback/faults
            </wsa:Address>
        </wsa:FaultTo>
    </soap:Header>
    <soap:Body>
        <ord:ProcessOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:ProcessOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

`ProcessOrderRequest` và các action URI trong ví dụ chỉ là **hợp đồng giả định của tình huống này**. Trong một project thật phải có XSD/WSDL định nghĩa rõ chúng; đừng lắp tùy ý `ReplyTo` vào operation `GetOrder` nếu đối tác chỉ hỗ trợ phản hồi cùng kênh.

### 6.2. Phản hồi callback minh họa

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header>
        <wsa:To>
            https://client.example.test/ws/callback/orders
        </wsa:To>
        <wsa:Action>
            urn:example:orders:action:ProcessOrderResponse
        </wsa:Action>
        <wsa:RelatesTo>
            urn:uuid:4073d98d-47da-4ff6-b8a0-5d509f60f594
        </wsa:RelatesTo>
        <wsa:MessageID>
            urn:uuid:8c707bb5-22a4-4273-b7c6-b0b016768090
        </wsa:MessageID>
    </soap:Header>
    <soap:Body>
        <ord:ProcessOrderResponse>
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:status>COMPLETED</ord:status>
        </ord:ProcessOrderResponse>
    </soap:Body>
</soap:Envelope>
~~~

Để XML này **schema-valid**, XSD phải khai báo `ProcessOrderResponse` và các child elements với đúng QName/type, điều không được tự suy ra từ minh họa `GetOrder` ở mục 4.

**Trọng tâm correlation:** callback response `wsa:RelatesTo` chứa **MessageID của request**, không phải MessageID của response. `MessageID` riêng của response dùng để nhận diện response message, hỗ trợ tracking/khử trùng lặp theo policy.

### 6.3. Callback receiver nằm phía “client”, nhưng là SOAP server

Ứng dụng gửi request ban đầu đồng thời có thể phải **cung cấp SOAP endpoint**:

~~~text
Application A:
   Outbound: WebServiceTemplate -> Partner B
   Inbound:  MessageDispatcherServlet/@Endpoint <- Partner B callback
~~~

Về trách nhiệm, A là **consumer của ProcessOrder** và **provider của callback endpoint**. Hai vai trò này không tự hình thành từ một object `WebServiceTemplate`.

Nếu callback listener không reachable từ partner (firewall/NAT/DNS/TLS), server B không thể gửi kết quả đến, dù request outbound được chấp nhận.

## 7. Same-channel vs different-channel: ma trận quyết định

| Tiêu chí | Same-channel | Different-channel |
|---|---|---|
| `ReplyTo` | Anonymous theo revision/contract | URL/EPR non-anonymous |
| HTTP response ban đầu | Chứa SOAP response hoặc Fault | Có thể chỉ acknowledgment (ví dụ 202) |
| Ai mở kết nối nhận kết quả? | Client đã mở HTTP request | Server/partner mở kết nối mới đến callback |
| Có cần callback listener? | Không | Có, nếu callback qua HTTP |
| Correlation | Có thể dùng MessageID/RelatesTo | **Thiết yếu**, gắn request và callback tách thời gian |
| Thời gian xử lý dài | Caller phải chờ hoặc timeout | Dễ trả acknowledgment sớm |
| Firewall/NAT | Chủ yếu cần outbound connectivity | Cần inbound callback reachability |
| TLS/security | HTTPS cho request/response cùng kênh | Xác thực/bảo vệ cả **hai kết nối** |
| SOAP Fault | Thường nằm trên HTTP response | Có thể gửi đến `FaultTo` khác |
| Khả năng retry | Cần idempotency nếu side effect | Cần cả retry callback và deduplication |
| Spring-WS | Phù hợp `marshalSendAndReceive` thông thường | Cần kiểm chứng/cài thêm hạ tầng; không mặc định tự callback |
| Quan sát vận hành | Một lượt HTTP dễ đo | Nhiều message, queue/job và correlation qua thời gian |

Không có mô hình nào “cao cấp hơn” một cách tuyệt đối. Nếu nghiệp vụ phản hồi trong 100 ms, simple request–response same-channel có thể hợp lý hơn. Nếu xử lý mất 30 phút và client không thể giữ socket mở, callback hoặc mô hình polling/job status thường thích hợp hơn.

## 8. MessageID và RelatesTo: ghép hai chiều trao đổi

WS-Addressing thường dùng cặp:

~~~text
Request:  wsa:MessageID = urn:uuid:req-123...
Response: wsa:RelatesTo = urn:uuid:req-123...
Response: wsa:MessageID = urn:uuid:res-456...
~~~

Đừng nhầm:

- `MessageID` trong request: định danh request message.
- `MessageID` trong response: định danh **response message** riêng.
- `RelatesTo` trong response: chỉ quan hệ với request gốc.
- `orderId`: business identifier, có thể trùng ở nhiều request và không thay MessageID.
- HTTP request ID hoặc TCP connection ID: metadata transport, không thay được correlation khi callback đến bằng kết nối khác.

### 8.1. Lưu trạng thái pending trước khi gửi request

Một thiết kế có callback cần giữ bảng/trạng thái tương tự:

| Field | Ví dụ | Tác dụng |
|---|---|---|
| request_message_id | `urn:uuid:4073...` | Khóa đối chiếu `RelatesTo` |
| business_key | `ORD-2048` | Tìm domain operation |
| expected_action | `...:ProcessOrderResponse` | Xác nhận loại callback |
| contract_version | `wsa-1.0; orders-v1` | Chống mix version |
| callback_endpoint | `/ws/callback/orders` | Policy routing |
| state | `PENDING`/`COMPLETED`/`FAILED` | Lifecycle |
| expires_at | Thời hạn ứng dụng | Xử lý callback đến trễ |
| idempotency_key | ID ổn định nếu có | Khử trùng lặp/side effects |
| error_code | Mã lỗi đã chuẩn hóa | Audit/support |

Lưu trạng thái **bền vững** nếu callback có thể đến sau khi process của client restart. Một `HashMap` singleton trong memory có thể hữu ích khi demo, nhưng không đủ cho integration dài hạn.

### 8.2. Kiểm tra correlation và authorization cùng nhau

Một callback có `RelatesTo` trùng request là **điều kiện correlation, không phải bằng chứng xác thực**. Kẻ gửi không tin cậy có thể giả mạo value nếu transport/message security yếu.

Quy trình nhận callback nên:

1. Xác minh TLS/mTLS hoặc WS-Security theo policy trước khi tin cậy nội dung.
2. Parse SOAP/WS-A Header bằng namespace-aware API.
3. Kiểm tra `To`/`Action`/revision và phiên bản hợp đồng.
4. Tra `RelatesTo` đến request pending đã tồn tại.
5. Kiểm tra authorization và expected partner identity.
6. Kiểm tra XSD của payload, trạng thái và tính nhất quán nghiệp vụ.
7. Thực thi idempotent completion và lưu dấu callback đã xử lý.

Không dựa vào việc `RelatesTo` “trông như UUID” để cho phép cập nhật giao dịch.

### 8.3. Callback đến trước khi caller lưu pending state

Một race có thể xảy ra nếu server xử lý cực nhanh:

~~~text
Client gửi SOAP request
Partner nhận và tạo callback ngay
Callback đến listener
Client mới lưu bản ghi pending
~~~

Để tránh, ứng dụng cần **tạo/lưu pending state và MessageID trước khi gửi request**. Với hệ thống có transactional outbox/queue, có thể dùng cơ chế gửi message sau khi commit bản ghi pending.

## 9. FaultTo: lỗi đi cùng hay khác kênh?

WS-Addressing cho phép chỉ định một địa chỉ nhận Fault khác với success reply endpoint. Ví dụ:

~~~xml
<wsa:ReplyTo
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>
        https://client.example.test/ws/callback/orders
    </wsa:Address>
</wsa:ReplyTo>
<wsa:FaultTo
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>
        https://client.example.test/ws/callback/faults
    </wsa:Address>
</wsa:FaultTo>
~~~

Khi service hỗ trợ `FaultTo` non-anonymous, lỗi có thể được phát dưới dạng **SOAP Fault message mới** đến receiver lỗi.

### 9.1. Hai nhánh callback

~~~mermaid
flowchart TD
    A["ProcessOrder request"] --> B["Server xử lý bất đồng bộ"]
    B --> C{"Kết quả"}
    C -->|"Thành công"| D["SOAP response đến ReplyTo"]
    C -->|"Lỗi"| E["SOAP Fault đến FaultTo"]
    D --> F["Client callback handler"]
    E --> G["Client fault callback handler"]
    F --> H["Ghép RelatesTo / cập nhật state"]
    G --> H
~~~

Đây là flow khi hai bên **đã hỗ trợ và thỏa thuận** callback routing. Nó không khẳng định `ReplyTo` hoặc `FaultTo` tùy ý luôn được mọi SOAP endpoint thực thi.

### 9.2. Nếu FaultTo vắng mặt?

Không suy ra một cách máy móc rằng mọi lỗi luôn về cùng HTTP response ban đầu. WS-Addressing revision và binding có các quy tắc mặc định cho reply/fault endpoint; ngoài ra WSDL/policy và framework có thể hạn chế tập địa chỉ được chấp nhận.

Trong contract cụ thể cần xác định:

- `FaultTo` có được phép không?
- `FaultTo` vắng mặt thì lỗi đi đâu?
- Lỗi phát sinh trước khi server lưu job có thể trả same-channel không?
- Lỗi sau khi gửi HTTP 202 sẽ được gửi qua callback Fault hay đưa vào status polling?
- Nếu callback Fault thất bại, server có retry/DLQ hay không?

### 9.3. HTTP 202 không thể chứa “kết quả cuối cùng” đã hứa callback

Nếu server đã trả `202 Accepted` và đóng lượt HTTP đầu tiên, một lỗi nghiệp vụ phát sinh sau đó không thể tự xuất hiện trong HTTP response đã kết thúc. Nó phải được báo qua callback, status resource, queue/event hoặc một cơ chế đã thống nhất. Client không nên đánh dấu operation **COMPLETED** chỉ vì nhận 202.

## 10. WS-Addressing ≠ business job asynchronous

Ba trường hợp cần phân biệt:

1. **Đồng bộ nghiệp vụ, phản hồi cùng kênh:** server tính kết quả trước khi trả HTTP.
2. **Xử lý background nhưng vẫn phản hồi cùng kênh:** server nhận job, trả một `AcceptedResponse` trong HTTP response; client sau đó polling trạng thái. `ReplyTo` vẫn có thể anonymous.
3. **Phản hồi khác kênh:** server gửi SOAP response/Fault về callback endpoint non-anonymous khi kết quả sẵn sàng.

WS-Addressing mô tả nơi gửi và mối liên hệ message, không quyết định server lưu job ra sao. Một hệ thống muốn “async” mà không cần mở inbound HTTPS có thể chọn **submit + query status/polling**. Đừng áp `ReplyTo` non-anonymous khi firewall, security policy và framework không cho phép callback.

### 10.1. Chọn mô hình theo điều kiện vận hành

| Điều kiện | Thiết kế đáng cân nhắc |
|---|---|
| Trả kết quả trong vài trăm ms | Same-channel |
| Xử lý vài phút, phía client có endpoint công khai | Non-anonymous ReplyTo + callback |
| Xử lý lâu, client ở mạng chỉ cho outbound | Submit + polling |
| Đối tác yêu cầu event integration có bảo đảm | Job/queue + callback có retry/DLQ |
| Client có thể tắt hoặc restart trước khi kết quả đến | Pending state bền vững + retry/dedup |
| Cần độ tin cậy cao cho payment/order | Idempotency, reconciliation và audit ngoài WS-A |

Không thể lựa chọn chỉ dựa trên ý muốn gửi HTTP 202; phải xét mô hình vận hành, hợp đồng và khả năng nhận kết quả.

## 11. Hai revision: WS-Addressing 2004/08 và WS-Addressing 1.0

Trong các tích hợp SOAP có thể gặp **hai họ XML namespace khác nhau** của WS-Addressing. Đây là sự khác biệt về revision của giao thức, không phải khác prefix.

| Thuộc tính | Bản 2004/08 (legacy) | WS-Addressing 1.0 (W3C 2005/08) |
|---|---|---|
| Namespace của `Action`, `To`, `ReplyTo`... | `http://schemas.xmlsoap.org/ws/2004/08/addressing` | `http://www.w3.org/2005/08/addressing` |
| Anonymous reply address phổ biến | `http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous` | `http://www.w3.org/2005/08/addressing/anonymous` |
| Special URI `none` của 1.0 | Không suy diễn từ 1.0 | `http://www.w3.org/2005/08/addressing/none` |
| QName của SOAP Header | Thuộc namespace 2004/08 | Thuộc namespace 2005/08 |
| Quy tắc binding | Theo revision legacy | Theo W3C Core/SOAP binding/Metadata |
| Tương thích tự động | Không | Không |

Ví dụ hai elements đều có local name `Action` nhưng **không cùng QName**:

~~~xml
<a:Action
    xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
    urn:example:orders:action:GetOrder
</a:Action>
~~~

~~~xml
<a:Action
    xmlns:a="http://www.w3.org/2005/08/addressing">
    urn:example:orders:action:GetOrder
</a:Action>
~~~

Nếu partner hỗ trợ 2004/08, việc client sử dụng `Action`/`ReplyTo` trong namespace 1.0 có thể bị từ chối hoặc không được nhận diện. **Đổi prefix `a` thành `wsa` không giải quyết được sai revision.**

### 11.1. ReplyTo anonymous theo từng revision

WS-Addressing 2004/08:

~~~xml
<a:ReplyTo
    xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing">
    <a:Address>
        http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous
    </a:Address>
</a:ReplyTo>
~~~

WS-Addressing 1.0:

~~~xml
<a:ReplyTo
    xmlns:a="http://www.w3.org/2005/08/addressing">
    <a:Address>
        http://www.w3.org/2005/08/addressing/anonymous
    </a:Address>
</a:ReplyTo>
~~~

Hai URI anonymous là **special address values**, không phải URL mà client cần thực hiện POST. Không thể dùng phép thay chuỗi raw XML để “nâng” mọi message 2004/08 lên 1.0; còn phải kiểm tra EPR/reference parameters, Fault actions, SOAP binding và WSDL/policy.

### 11.2. Đừng khẳng định một framework tự hỗ trợ tất cả revisions

Một bản Spring-WS có thể cung cấp API cho WS-Addressing 1.0 và/hoặc legacy, nhưng cách cấu hình, các overload và runtime support có thể thay đổi theo release/dependencies. Khi chuẩn bị tích hợp phải ghi rõ:

- Phiên bản Spring-WS client/server đang sử dụng.
- Revision WS-A mà partner yêu cầu.
- SOAP 1.1/1.2 message factory/binding đang bật.
- Những MAP headers và anonymous/non-anonymous routes đã **thực sự kiểm thử**.

Một câu “Spring-WS hỗ trợ WS-Addressing” không đủ để chứng minh **different-channel reply** hoặc 2004/08 interoperability.

## 12. ReplyTo vắng mặt, anonymous, non-anonymous và none

Với WS-Addressing 1.0, có những trường hợp cần phân biệt:

| `ReplyTo` | Ngữ nghĩa reply endpoint | Hành vi client cần dự kiến |
|---|---|---|
| Vắng mặt | Có thể mặc định anonymous theo WS-A Core trong MEP phù hợp; WSDL/policy có thể yêu cầu explicit | Xác minh contract thực tế |
| Anonymous | Reply trên response channel của transport | HTTP SOAP response/Fault |
| Non-anonymous HTTPS EPR | Reply đến callback endpoint riêng nếu binding/server hỗ trợ | Callback listener và correlation |
| `none` (1.0) | Special address biểu thị không có reply endpoint | Không chờ một normal success response như anonymous |

Special address `none`:

~~~text
http://www.w3.org/2005/08/addressing/none
~~~

**Không phải URL HTTP** và không phải cách “bật callback”. Với request–response contract, sử dụng `ReplyTo=none` cần phù hợp MEP/binding/policy; không làm một caller `marshalSendAndReceive` thông thường tự nhận được kết quả cuối cùng.

### 12.1. Vắng ReplyTo chưa chắc giống explicit anonymous trong sản phẩm

WS-Addressing 1.0 có quy tắc mặc định anonymous theo ngữ cảnh, nhưng:

- Một WSDL/WS-Policy có thể đòi header xuất hiện rõ.
- Một gateway có thể xác nhận chính xác `ReplyTo` và `MessageID`.
- WS-Security có thể yêu cầu ký các headers cụ thể.
- Revision 2004/08 có URI và quy tắc binding cần đối chiếu riêng.

Hãy có XML fixtures cho cả **không có ReplyTo** và **ReplyTo anonymous explicit** nếu đối tác công bố hỗ trợ cả hai; đừng tự coi mọi cách biểu diễn tương đương.

### 12.2. ReplyTo none không đồng nghĩa HTTP 202

`none` là thông tin định tuyến reply ở WS-Addressing. `202 Accepted` là status của HTTP response ban đầu. Một server có thể trả 202 khi nhận job có `ReplyTo` non-anonymous; HTTP 202 không tự biểu thị `none`. Cũng không dùng `FaultTo=none` như cách bỏ trách nhiệm xử lý lỗi.

## 13. SOAP 1.1 và SOAP 1.2 là một trục version khác

Cần quản lý **hai trục độc lập**:

1. SOAP Envelope/binding version.
2. WS-Addressing revision của MAP headers.

| Thuộc tính | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Content-Type thường gặp | `text/xml` | `application/soap+xml` |
| Action transport | HTTP `SOAPAction` | Tham số `action` khi binding sử dụng |
| Fault structure | `faultcode`/`faultstring` | `Code`/`Reason`/`Detail` |
| WS-Addressing Header | Namespace WS-A theo revision | Namespace WS-A theo revision |
| Anonymous/non-anonymous routing | Theo MEP, binding và policy | Theo MEP, binding và policy |

### 13.1. WS-A Action khác SOAPAction

Ví dụ:

~~~text
WS-A Action:
  urn:example:orders:action:GetOrder

SOAP 1.1 HTTP SOAPAction:
  "urn:example:orders:action:GetOrder"
~~~

- `wsa:Action` là SOAP Header trong namespace WS-A.
- `SOAPAction` là HTTP-level metadata của SOAP 1.1.
- SOAP 1.2 có `action` parameter của `application/soap+xml` nếu binding yêu cầu.

Các giá trị có thể cần đồng nhất theo SOAP WS-A binding/policy. **Không giả định** `SoapActionCallback` tự đặt `wsa:Action` hoặc một WS-A callback luôn cài đủ mọi HTTP action metadata cho mọi binding mà không kiểm thử.

Một server có thể từ chối hoặc phát Addressing ActionMismatch Fault nếu action header và binding không phù hợp. Chẩn đoán cả Header, media type, SOAPAction và WSDL action metadata.

### 13.2. Đúng Body QName nhưng sai WS-A revision vẫn có thể lỗi

Client có thể gửi `GetOrderRequest` đúng `urn:example:orders:v1`, nhưng WS-A Header ở namespace 2004/08 thay vì 1.0. Server có thể không nhận Action/ReplyTo và từ chối vì mustUnderstand hoặc policy.

Ba điều phải đúng cùng lúc:

~~~text
Business payload QName + SOAP binding + WS-Addressing revision
~~~

Không dùng “XSD validate payload thành công” để kết luận toàn bộ SOAP integration tương thích.

## 14. WSDL và WS-Addressing metadata/policy

XSD chỉ định XML business payload. WSDL và WS-Policy có thể mô tả thêm:

- Input/output messages và SOAP binding.
- Action URIs của request, response và Fault.
- WS-Addressing revision cần sử dụng.
- `ReplyTo` anonymous có bắt buộc/được phép/bị cấm hay không.
- Non-anonymous callback có được server hỗ trợ không.
- `FaultTo` có thể khác `ReplyTo` không.
- Header signatures và TLS/mTLS requirements.
- Response ban đầu là SOAP business result hay chỉ acknowledgment.

### 14.1. Một ví dụ metadata Action trong WSDL

Một WSDL 1.1 contract có thể dùng `wsam:Action` của WS-Addressing Metadata 1.0:

~~~xml
<!-- Fragment minh họa, không phải WSDL đầy đủ. -->
<wsdl:operation name="GetOrder">
    <wsdl:input
        message="tns:GetOrderInput"
        wsam:Action="urn:example:orders:action:GetOrder"/>
    <wsdl:output
        message="tns:GetOrderOutput"
        wsam:Action="urn:example:orders:action:GetOrderResponse"/>
</wsdl:operation>
~~~

Namespace metadata 1.0:

~~~text
http://www.w3.org/2007/05/addressing/metadata
~~~

**Không đồng nhất** WSDL metadata extension namespace với SOAP runtime WS-A 1.0 Header namespace `http://www.w3.org/2005/08/addressing`. Các extension `wsaw:UsingAddressing`, WS-Policy assertions và metadata `Anonymous` còn tùy WSDL/WS-A version cụ thể.

### 14.2. Anonymous restriction của binding quan trọng hơn ý muốn của client

Nếu contract yêu cầu anonymous reply, client không thể tự chọn non-anonymous `ReplyTo` chỉ bằng cách đặt một URL. Nếu binding yêu cầu non-anonymous replies, client cần có khả năng nhận callback thật sự; `marshalSendAndReceive` mặc định chờ HTTP response có thể không phải cách gọi phù hợp.

Một port có thể hỗ trợ SOAP 1.1 với WS-A 1.0 và anonymous only; port khác cho non-anonymous. Cần lấy đúng WSDL port/binding thay vì suy từ tên operation.

### 14.3. Những lớp phải kiểm tra độc lập

~~~text
XSD payload QName và kiểu
  + WSDL operation/binding
  + WS-A revision, Action, ReplyTo, FaultTo
  + SOAP 1.1/1.2, Content-Type, transport action
  + Security policy, certificates, mustUnderstand
  + Runtime callback/reliability topology
~~~

Một WSDL có WS-A action metadata **không chứng minh** server tự biết gửi reply khác kênh. Điều đó cần một HTTP callback sender và receiver vận hành đúng.

## 15. Phạm vi hỗ trợ của Spring-WS: Header API khác callback runtime

Spring-WS có các thành phần WS-Addressing cho những phiên bản tương thích, nhưng cần tách:

| Năng lực | Cần kiểm tra ở đâu? |
|---|---|
| Tạo `wsa:Action` cho outbound request | Client addressing callback/API |
| Chọn endpoint theo WS-A Action | Addressing endpoint mapping/annotation support |
| Đọc `MessageID`/`ReplyTo`/`FaultTo` | WS-A Header parser theo revision |
| Same-channel reply | `WebServiceTemplate` và SOAP endpoint adapter |
| Non-anonymous callback | Application/pipeline có outbound callback sender + inbound callback listener |
| Correlation qua restart | Durable store/queue do ứng dụng triển khai |
| Callback Fault processing | Callback listener, SOAP Fault handling |
| WS-Security cho callback | WSS4J/TLS, trust, signed parts |
| Revision support | Spring-WS dependency/API và partner stack |
| WSDL policy compliance | Contract tests cùng đối tác |

**Cần tránh tuyên bố sai:** chỉ thêm `ReplyTo` non-anonymous vào SOAP Header **không** làm `WebServiceTemplate` tự mở một endpoint nhận HTTP POST callback hoặc tự duy trì pending future qua nhiều giờ.

### 15.1. Kiểm tra khả năng theo ba chiều

Khi hỏi “có hỗ trợ phiên bản không?”, hãy ghi:

1. **Spring-WS version** thực tế, kèm module/major dependencies.
2. **WS-A revision** 2004/08 hay W3C 1.0.
3. **SOAP version** 1.1 hay 1.2, đồng thời phân loại same-channel/non-anonymous.

Không ghi một boolean `supportsWsAddressing=true` rồi suy ra tất cả 2×2×2 tổ hợp chạy đúng.

### 15.2. Các extension points thường gặp

Tên API liên quan trong nhiều dòng Spring-WS bao gồm:

- `org.springframework.ws.soap.addressing.client.ActionCallback`.
- WS-Addressing version/endpoint reference APIs (chữ ký tùy release).
- `@Action` hoặc action-based endpoint mapping trên server khi cấu hình.
- `WebServiceTemplate` để gửi/nhận SOAP thông thường.
- `MessageDispatcherServlet`, `@Endpoint` để xây listener nhận callback.
- `ClientInterceptor`/`EndpointInterceptor` và WS-Security integration.
- `Jaxb2Marshaller`/DOM/Source để xử lý XML payload.

Không đoán setter, enum constant hay default revision từ một bài viết của phiên bản khác. Đối chiếu dependency/API đúng release và **assert XML headers thực sự** trong test.

### 15.3. Ma trận hỗ trợ cần được xác minh

| Tổ hợp | Cần test |
|---|---|
| WS-A 1.0 + SOAP 1.1 + anonymous | Reply về HTTP response đúng Action/QName |
| WS-A 1.0 + SOAP 1.2 + anonymous | Content-Type, action và Fault SOAP 1.2 |
| WS-A 2004/08 + SOAP 1.1 + anonymous | Namespace/special URI legacy |
| WS-A 1.0 + non-anonymous ReplyTo | HTTP 202/acknowledgment và callback POST |
| WS-A 1.0 + non-anonymous FaultTo | Fault callback và correlation |
| Non-anonymous + mTLS/Signature | TLS, message signature và authorization |

Bảng này là **test plan**, không phải tuyên bố mọi bản Spring-WS đều hỗ trợ toàn bộ các cấu hình trên.

## 16. Spring-WS client: dùng ActionCallback cho WS-Addressing

Đối với lời gọi SOAP client, Spring-WS thường cung cấp `ActionCallback` để tạo các header WS-Addressing trong các phiên bản hỗ trợ.

Ví dụ đơn giản:

~~~java
import java.net.URI;

import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;

ActionCallback addressing = new ActionCallback(
    URI.create("urn:example:orders:action:GetOrder")
);

Object raw = template.marshalSendAndReceive(
    "https://partner.example.test/ws/orders",
    jaxbRequestRoot,
    addressing
);
~~~

Các giả định của snippet:

- `template` đã có `Jaxb2Marshaller` và SOAP message factory/binding đúng.
- `jaxbRequestRoot` mang QName global element từ XSD, có thể là `JAXBElement<T>`.
- `ActionCallback` của Spring-WS version đang dùng hỗ trợ API tương ứng.
- Action URI phải lấy từ WSDL/policy, không tự suy từ tên Java method.

**Mặc định của callback không phải tuyên bố về mọi revision.** Cần kiểm tra message sinh ra thực sự có `wsa:Action`, `wsa:To`, `wsa:ReplyTo` và `wsa:MessageID` nào, trong namespace 2004/08 hay 1.0, bằng test outbound SOAP Header.

### 16.1. Request–response anonymous thường phù hợp marshalSendAndReceive

Khi request có `ReplyTo` anonymous hoặc binding mặc định anonymous, `marshalSendAndReceive` có thể dùng HTTP response để nhận SOAP response bình thường và unmarshal JAXB data. Nếu response là SOAP Fault, `FaultMessageResolver`/`ClientInterceptor.handleFault` xử lý theo cấu hình.

Khi partner yêu cầu explicit anonymous EPR, đừng giả định `ActionCallback` tự đặt nó theo đúng contract; đối chiếu API version và test Header.

### 16.2. Non-anonymous ReplyTo cần cấu hình nhiều thành phần

Muốn gửi `ReplyTo` có callback URL, logic triển khai (pseudocode) bao gồm:

~~~java
// PSEUDOCODE: tên helper/method không phải Spring-WS API.
//
// String id = generateUniqueMessageId();
// savePending(id, expectedResponseAction, businessId);
//
// ActionCallback callback = addressingCallbackFor(
//     addressingRevision,
//     processOrderAction
// );
//
// callback.setReplyTo(callbackEndpointReference);
// callback.setFaultTo(faultEndpointReference);
// callback.setMessageId(id);
//
// sendInitialSoapRequest(requestRoot, callback);
//
// // Phần nhận callback chạy ở SOAP @Endpoint khác.
// // Nó đọc wsa:RelatesTo=id và hoàn tất pending state.
~~~

Điều phải làm rõ: `ActionCallback` và endpoint reference APIs có thể khác tên constructor/setter theo phiên bản framework; **không copy pseudocode như code chạy được**. Cần dùng API chính xác và chứng minh headers thực tế.

Ngay cả khi đã gửi đúng EPR, client vẫn cần **callback listener** để nhận reply sau đó. Một `WebServiceTemplate.marshalSendAndReceive` đồng bộ thông thường không tự trả về future được giải quyết bằng HTTP POST callback đến sau 15 giây.

### 16.3. Không dùng raw XML string để thay Action/ReplyTo

Không tạo Header bằng nối chuỗi SOAP XML rồi tìm–thay `wsa:` prefix; thao tác đó có thể:

- Bỏ sót namespace declarations/reference parameters.
- Phá XML escaping.
- Tạo WS-A revision không nhất quán.
- Vô tình thay signed elements và làm signature fail.
- Dẫn đến XML Injection nếu ghép input không tin cậy.

Dùng API SOAP/WS-A namespace-aware phù hợp hoặc một handler XML chuyên dụng được XSD/WS-A test.

## 17. Spring-WS server: Action mapping và same-channel reply

`@PayloadRoot` định tuyến endpoint theo QName của payload; Spring-WS còn có các cơ chế mapping theo WS-Addressing Action khi được cấu hình.

Một endpoint skeleton:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;

@Endpoint
public class GetOrderAddressingEndpoint {

    private final OrderService service;

    public GetOrderAddressingEndpoint(OrderService service) {
        this.service = service;
    }

    @Action("urn:example:orders:action:GetOrder")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        return service.getOrder(request);
    }
}
~~~

Đây là ví dụ **minh họa kiến trúc**. `OrderService` và JAXB types là thành phần ứng dụng tự tạo; mapping `@Action` cần registration tương ứng và API/package tương thích Spring-WS version. Nếu XJC tạo named type không có `@XmlRootElement`, method signature phải dùng đúng JAXB wrapper/binding.

### 17.1. Mapping theo Action không có nghĩa đã hỗ trợ callback

Endpoint trên trả một object Java và server có thể marshal nó vào HTTP response hiện tại. Dù có `@Action`, điều đó **không bảo đảm** server tự hoãn reply theo `ReplyTo` non-anonymous.

Một server muốn hỗ trợ different-channel phải bổ sung:

- Quy tắc kiểm tra và chấp nhận ReplyTo/FaultTo.
- Lưu job và MessageID.
- Initial HTTP acknowledgment.
- Worker xử lý nghiệp vụ.
- Outbound SOAP client tạo response callback đến EPR hợp lệ.
- Retry/DLQ, XSD/WSDL validation và WS-Security cho callback.

Việc bật WS-A parsing/mapping chỉ giải quyết một phần đường đi request.

### 17.2. Nếu vừa có @Action vừa có @PayloadRoot

Cần hiểu cấu hình endpoint mappings nào được Spring-WS ưu tiên và kiểm thử khi Action/header mâu thuẫn với root payload QName. Một request có `Action=ProcessOrder` nhưng Body là `CancelOrderRequest` không được phép làm server chọn handler sai hoặc bỏ qua validation/authorization.

Với SOAP Header `mustUnderstand`, phải có processor/addressing support thực sự hiểu header; chỉ tồn tại annotation endpoint không bảo đảm mọi mandatory header đã được xử lý đúng.

## 18. Tổ chức SOAP callback receiver ở phía client

Ứng dụng client muốn nhận callback phải cung cấp một HTTP SOAP endpoint riêng, có thể là `MessageDispatcherServlet`/`@Endpoint` trong cùng ứng dụng hoặc một service khác có URL công bố cho partner.

~~~mermaid
flowchart TD
    A["Partner HTTP POST callback"] --> B["TLS / WS-Security verification"]
    B --> C["SOAP và WS-A header checks"]
    C --> D["Callback endpoint mapping"]
    D --> E["Payload XSD validation"]
    E --> F["Correlate RelatesTo với pending store"]
    F --> G{"Known request / allowed state?"}
    G -->|"Có"| H["Idempotent completion transaction"]
    G -->|"Không"| I["Reject hoặc quarantine/audit"]
    H --> J["Persist result và receipt"]
    J --> K["HTTP acknowledgment"]
~~~

Sơ đồ nêu **những trách nhiệm phải có**, không khẳng định thứ tự pipeline tuyệt đối trong mọi Spring-WS version. Cần bảo đảm callback chưa được xác thực không thể làm phát sinh side effects.

### 18.1. Callback receiver là một server SOAP mới

Một lượt callback HTTP POST có các thành phần riêng:

- SOAP Envelope và business callback root QName.
- WS-A `Action` của callback response.
- WS-A `RelatesTo` trỏ request MessageID trước đó.
- HTTP Content-Type/SOAP version riêng.
- TLS/mTLS connection mới.
- WS-Security token/signature/timestamp theo callback policy.
- XSD/WSDL của callback operation.

Không lấy `WebServiceTemplate` đang chờ initial response làm nơi “tự đón” callback này.

### 18.2. Pending store và durable inbox

Một thiết kế robust:

1. Trước khi gửi initial SOAP request, tạo `MessageID` và **persist pending state**.
2. Gửi request đến partner với ReplyTo/FaultTo theo policy.
3. Callback listener xác thực nguồn và đọc Action/RelatesTo.
4. Kiểm tra `RelatesTo` có record pending, đúng partner và expected Action.
5. Lưu message vào inbox có khóa dedup; cập nhật pending state trong transaction.
6. Chỉ acknowledgment sau khi đã bảo đảm dữ liệu được lưu bền vững theo hợp đồng.
7. Sử dụng outbox/event để tiếp tục xử lý domain khi cần.

Nếu callback tới trước khi pending state được commit, listener có thể không tìm thấy request. Đây là lý do nên persist correlation **trước khi gửi**. Nếu callback tới sau khi application restart, durable store vẫn cho phép khớp kết quả.

### 18.3. Callback không nhất thiết theo đúng thứ tự initial requests

~~~text
T0: Gửi request A (MessageID A)
T1: Gửi request B (MessageID B)
T2: Nhận callback cho B (RelatesTo B)
T3: Nhận callback cho A (RelatesTo A)
~~~

Không ghép bằng FIFO hay “request vừa gửi gần nhất”. Dùng `RelatesTo`, expected Action và authorization để nhận diện chính xác, đặc biệt khi nhiều SOAP operations của cùng businessId được gửi đồng thời.

### 18.4. Callback acknowledgment khác business response ban đầu

Khi listener nhận callback, nó có thể trả HTTP 200/202 hoặc SOAP acknowledgment tùy WSDL/binding. Đó là phản hồi cho **lượt HTTP callback**, không phải response của initial ProcessOrder HTTP request đã kết thúc trước đó.

Không thiết kế một chuỗi callback lặp vô tận chỉ vì mọi SOAP request có `ReplyTo`.

## 19. Security: ReplyTo và FaultTo có thể là bề mặt SSRF

Một server đọc `ReplyTo` URL do client cung cấp rồi tự động HTTP POST kết quả về đó có thể bị lợi dụng cho **SSRF** hoặc phát tán dữ liệu nhạy cảm nếu URL không được kiểm soát.

Các kiểm soát phía server:

- Chỉ chấp nhận callback URLs đã đăng ký hoặc nằm trong allowlist/host policy.
- Xác thực caller identity và quyền sử dụng callback destination.
- Không tự động gửi đến loopback, link-local, metadata endpoints, mạng nội bộ không được phép.
- Kiểm soát DNS rebinding và redirect, route policies/egress restrictions.
- Xác minh TLS server certificate; mTLS nếu contract yêu cầu.
- Không tự gửi SOAP response/tokens đến URL không đáng tin.
- Hạn chế số attempts, tốc độ, kích thước và timeout khi gửi callback.
- Audit callback routing và bất thường ở cấp partner.

Không coi EPR là “đáng tin” chỉ vì nó nằm trong SOAP Envelope đã parse thành công.

### 19.1. WS-Security cần bảo vệ addressing headers phù hợp

Một SOAP message có chữ ký chỉ trên Body chưa chắc bảo vệ `To`, `ReplyTo`, `FaultTo` và `MessageID`. Nếu attacker có thể thay header routing, reply có thể bị chuyển hướng trong một threat model không có end-to-end integrity.

Chính sách WS-Security nên chỉ rõ **signed parts**, xác minh certificate/trust và quy tắc authorization cho callback URI.

Nhưng ngay cả một `ReplyTo` đã ký bởi client tin cậy cũng chưa chứng minh client **có quyền** gửi response tới bất kỳ HTTPS URL nào. Vẫn cần allowlist hoặc pre-registration.

### 19.2. Bảo vệ callback listener ở phía client

Khi ứng dụng client mở một endpoint nhận inbound HTTPS:

- Bật TLS/mTLS với certificate trust/hostname policy.
- Xác minh WS-Security signature/timestamp/replay protection khi cần.
- Chỉ chấp nhận Action/QName/contract version đã công bố.
- Validate XSD callback payload và Fault.
- Chặn XXE/DTD/external entity/schema access không đáng tin.
- Giới hạn SOAP body size, XML depth, rate limit và concurrency.
- Kiểm tra `RelatesTo`, state transition và idempotency.
- Tránh log raw SOAP payload/token/private key và dữ liệu cá nhân.

`RelatesTo` là correlation field, **không phải** credential. Một UUID khó đoán không thay được authentication.

## 20. WS-Addressing không cung cấp reliable delivery tự động

Các thuộc tính WS-A không tự triển khai:

- Exactly-once processing.
- Durable queue/pending store.
- Retry backoff hoặc dead-letter queue.
- Distributed transaction.
- Reconciliation khi callback bị mất.
- Idempotency cho business operation.
- Bảo đảm callback được gửi trước một deadline.
- Authentication/authorization cho callback URI.

Một hệ thống non-anonymous replies phải bổ sung các cơ chế đó hoặc dựa vào các platform/protocol bảo đảm vận chuyển mà hai bên đã thống nhất.

### 20.1. Ba thời điểm thất bại khác nhau

| Thời điểm | Sự kiện | Cách xử lý |
|---|---|---|
| Trước khi trả initial acknowledgment | XSD sai, không được quyền | SOAP Fault/HTTP error theo binding |
| Sau initial 202, đang xử lý job | Nghiệp vụ thất bại | Fault callback, status polling hoặc event theo contract |
| Sau khi có kết quả, đang gửi callback | Listener down, TLS fail, timeout | Retry notification và DLQ/reconciliation |

**Retry callback không đồng nghĩa chạy lại business operation**. Với thanh toán/tạo đơn, business work có thể đã thành công; cần retry việc **thông báo kết quả** thay vì thực hiện lại thanh toán.

### 20.2. Callback có thể được gửi lại

Nếu callback listener đã lưu kết quả nhưng HTTP acknowledgment bị mất, partner có thể retry. Một thuật toán khái quát:

~~~text
if callback MessageID đã được xử lý:
    acknowledge again safely

else if RelatesTo thuộc pending operation
    và action/version/partner hợp lệ:
    validate và commit completion idempotently
    record callback identity
    acknowledge

else:
    reject / quarantine / audit theo policy
~~~

Partner có thể gửi lại **cùng MessageID**, hoặc tạo message khác `MessageID` nhưng cùng `RelatesTo` tùy protocol của họ. Do đó, deduplication cần kết hợp message ID, correlation, expected action và **business state**, không chỉ một UUID.

### 20.3. Callback mất hoặc đến sau timeout

Khi không có callback sau thời hạn:

- Đánh dấu pending operation `TIMED_OUT`/`UNKNOWN` theo policy.
- Không mặc định business operation chưa xảy ra.
- Query/reconcile trạng thái với partner nếu contract hỗ trợ.
- Giữ đủ correlation state cho callback tới muộn.
- Có quy tắc handling late/duplicate callback.
- Quan sát queue age, DLQ, fault rate và callback delivery attempts.

**Hết thời gian đợi không chứng minh job ban đầu thất bại.** Điều này đặc biệt quan trọng khi operation có side effect như `SubmitPayment`.

## 21. Kiểm thử same-channel bằng Spring-WS client

Với `ReplyTo` anonymous, `MockWebServiceServer` có thể giúp test phần **SOAP client** mà không cần HTTP server thật. Nó nhận request từ `WebServiceTemplate` và trả SOAP response/Fault giả lập.

### 21.1. Test một round-trip đơn giản

Giả sử `ordersTemplate` được cấu hình JAXB/OXM phù hợp và request root đã được tạo từ `ObjectFactory`:

~~~java
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

class OrdersAddressingClientTest {

    private final WebServiceTemplate template;

    OrdersAddressingClientTest(WebServiceTemplate template) {
        this.template = template;
    }

    @Test
    void receivesSameChannelSoapResponse() {
        MockWebServiceServer mock =
            MockWebServiceServer.createServer(template);

        String requestXml = """
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
            </ord:GetOrderRequest>
            """;

        String responseXml = """
            <ord:GetOrderResponse
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
                <ord:status>PAID</ord:status>
            </ord:GetOrderResponse>
            """;

        mock.expect(payload(new StringSource(requestXml)))
            .andRespond(withPayload(new StringSource(responseXml)));

        // requestRoot được sinh từ JAXB ObjectFactory
        // của contract orders v1.
        Object result = template.marshalSendAndReceive(
            requestRoot,
            new ActionCallback(
                URI.create("urn:example:orders:action:GetOrder")
            )
        );

        // Assert result đúng JAXBElement / JAXB response type.
        // Bổ sung kiểm tra wsa:Action, wsa:ReplyTo bằng
        // custom SOAP Header RequestMatcher.

        mock.verify();
    }
}
~~~

Đây là **test skeleton**: `requestRoot` là fixture cần tạo trong test, Spring test configuration cần được chuẩn bị và `WebServiceTemplate` phải có marshaller/unmarshaller. Đừng copy code như một class JUnit độc lập đã hoàn chỉnh.

`MockWebServiceServer` có thể kiểm tra payload XML. Để kiểm tra **WS-Addressing**, phải bổ sung matcher truy cập SOAP Header và đối chiếu namespace URI/local name, không chỉ dựa trên test body.

### 21.2. Những assertion phải có cho anonymous reply

- Outbound SOAP Envelope là 1.1 hoặc 1.2 đúng WSDL.
- `wsa:Action` dùng WS-A namespace/revision đúng.
- `wsa:To` tương thích destination policy.
- `wsa:ReplyTo` là anonymous URI đúng revision, nếu contract yêu cầu explicit.
- `wsa:MessageID` có mặt nếu flow/policy yêu cầu và định dạng hợp lệ.
- SOAP response có `wsa:Action` và `wsa:RelatesTo` phù hợp nếu partner đã thỏa thuận.
- JAXB response root QName đúng XSD.
- SOAP Fault đi vào Fault handling, không unmarshal thành business response.
- Prefix khác nhưng namespace URI giống vẫn được chấp nhận.

Không viết test chỉ assert SOAPAction HTTP header rồi cho rằng `wsa:Action` đã được sinh đúng. Đây là hai trường khác nhau.

### 21.3. Test sai WS-Addressing namespace

Tạo hai SOAP Header fixtures:

~~~xml
<!-- Đúng nếu contract yêu cầu WS-Addressing 1.0. -->
<wsa:Action
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    urn:example:orders:action:GetOrder
</wsa:Action>
~~~

~~~xml
<!-- Sai revision nếu đối tác chỉ nhận WS-Addressing 1.0. -->
<wsa:Action
    xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
    urn:example:orders:action:GetOrder
</wsa:Action>
~~~

Cả hai có cùng local name, nhưng `QName` khác. Trong test hãy xác nhận Header parser/mapping của hệ thống theo chính sách **không âm thầm nhận một revision chưa hỗ trợ**.

## 22. Kiểm thử non-anonymous callback cần HTTP integration thật

`MockWebServiceServer` có thể mô phỏng request/response client nhưng không tự chứng minh **HTTP callback sẽ được partner POST về một endpoint khác**. Một test cho different-channel phải khởi động hoặc mô phỏng **hai chiều HTTP**:

~~~mermaid
flowchart LR
    A["Test harness"] --> B["Application SOAP client"]
    B --> C["Fake Partner SOAP server"]
    C --> D["Job/notification scheduler"]
    D --> E["Application callback SOAP endpoint"]
    E --> F["Pending state/assertions"]
~~~

Một chiến lược:

1. Chạy SOAP client được kiểm thử với endpoint URL của fake partner.
2. Fake partner đọc WS-A `Action`, `ReplyTo`, `MessageID`.
3. Fake partner trả initial HTTP 202/acknowledgment đúng binding.
4. Fake partner gửi SOAP response thành **HTTP POST mới** đến callback listener local.
5. Callback handler xác minh Action, To, RelatesTo và XSD.
6. Test assert pending state chuyển `PENDING → COMPLETED`.
7. Test assert callback acknowledgment được trả và duplicate callback được xử lý an toàn.

Các chi tiết HTTP status và WSDL callback operation phải được chọn theo contract đang triển khai. Không coi việc fake partner trả 202 là đã kiểm chứng full callback flow.

### 22.1. Ma trận callback bắt buộc

| Ca | Tình huống | Kỳ vọng |
|---|---|---|
| C1 | ReplyTo hợp lệ, callback đúng RelatesTo | Completion thành công |
| C2 | Callback đến trước một request khác đã gửi | Ghép đúng MessageID, không FIFO |
| C3 | Callback sai RelatesTo | Reject/quarantine, không cập nhật giao dịch |
| C4 | Callback sai Action | Từ chối theo expected Action |
| C5 | Callback sai WS-A revision | Không nhận nhầm namespace |
| C6 | Callback sai SOAP version | Lỗi binding; không xử lý nghiệp vụ |
| C7 | Callback có payload sai XSD | Reject/Fault theo contract |
| C8 | Callback đến hai lần cùng message identity | Idempotent acknowledgment, không nhân side effects |
| C9 | Duplicate có MessageID khác nhưng cùng business result | Idempotency theo operation state |
| C10 | Callback đến sau expiration | Xử lý late callback theo policy, không tự đổi state sai |
| C11 | Callback đến sau process restart | Durable pending/inbox vẫn hoạt động |
| C12 | Callback TLS certificate sai | Không chấp nhận |
| C13 | Callback WS-Security signature bị sửa | Không tin cậy nội dung |
| C14 | Fault đi vào FaultTo khác ReplyTo | Fault handler lưu FAILED state |
| C15 | FaultTo unreachable | Retry/DLQ/alert, không im lặng mất lỗi |
| C16 | ReplyTo chỉ định localhost/metadata host trái policy | Chặn SSRF |
| C17 | Callback listener trả 500 sau commit | Retry nhận dạng duplicate, không chạy lại nghiệp vụ |
| C18 | Initial HTTP 202 nhưng không có callback | Timeout/reconciliation, không đánh dấu success |

### 22.2. Kiểm tra initial HTTP status và callback riêng

Có thể có hai metrics độc lập:

~~~text
initial_transport_outcome = ACCEPTED
callback_delivery_outcome = FAILED
business_operation_state = PENDING
~~~

Đừng gộp chúng thành một `success=true` khi nhận HTTP 202. Hãy thiết kế một operation lifecycle:

~~~text
NEW -> SENT -> ACCEPTED -> PENDING
                          -> COMPLETED
                          -> FAILED
                          -> UNKNOWN / RECONCILE
~~~

Thay đổi trạng thái phải idempotent. Nếu sau `FAILED` có callback success trễ, ứng dụng cần chính sách reconcile rõ; không ghi đè tùy tiện trạng thái đã quyết toán.

## 23. Ma trận phiên bản để kiểm thử interoperability

Dữ liệu thực tế có ít nhất ba trục: SOAP version, WS-Addressing revision và reply mode. Có thể tạo test case matrix:

| SOAP | WS-Addressing | Reply mode | Điều cần xác minh |
|---|---|---|---|
| 1.1 | 1.0 | Anonymous | Envelope, SOAPAction, wsa:Action, HTTP reply |
| 1.2 | 1.0 | Anonymous | Media type action, SOAP 1.2 Fault/Action |
| 1.1 | 2004/08 | Anonymous | Legacy header/anonymous URI |
| 1.2 | 2004/08 | Anonymous | Chỉ test nếu partner/runtime công bố hỗ trợ |
| 1.1 | 1.0 | Non-anonymous | HTTP 202, reply POST, RelatesTo |
| 1.2 | 1.0 | Non-anonymous | SOAP 1.2 binding + callback POST |
| 1.1 | 1.0 | Separate FaultTo | Fault routing, signed headers |
| 1.1 | 2004/08 | Non-anonymous | Chỉ hỗ trợ khi có contract/implementation xác nhận |

Không cần cài tất cả các tổ hợp nếu hệ thống không dùng. Điều quan trọng là **ghi rõ phạm vi được hỗ trợ**, chỉ coi tổ hợp nào đã kiểm chứng là supported.

### 23.1. Có thể có hạn chế theo WSDL/WS-Policy ngay cả khi framework parse được

Ví dụ Spring-WS server có thể parse WS-A 1.0 headers và định tuyến theo Action, nhưng WSDL binding của service lại **yêu cầu anonymous**. Client gửi non-anonymous ReplyTo vẫn không nằm trong phạm vi contract, dù header syntactically hợp lệ.

Tương tự, một runtime có thể sinh WS-A 2004/08 headers nhưng partner đã bỏ revision đó. Không kết luận tương thích chỉ từ việc marshalling/parsing không ném exception.

### 23.2. Khi nâng cấp Spring-WS hoặc Spring Boot

Cần chạy lại tests cho:

- Namespace/revision của headers được tạo mặc định.
- Action callback/endpoint mapping registration.
- SOAP message factory 1.1/1.2.
- WSDL action metadata và HTTP SOAPAction.
- SOAP Fault routing và exception handling.
- WS-Security library, certificate trust và canonicalization.
- Same-channel JAXB response.
- Non-anonymous callback receiver/retries.
- `MessageID`/`RelatesTo` correlation và duplicate handling.

Không dùng một happy-path anonymous request để kết luận nâng cấp an toàn cho cả callback topology.

## 24. Observability và timeout theo từng phase

Same-channel operation có thể được đo bằng một HTTP round trip. Different-channel operation có nhiều thời gian khác nhau:

| Chỉ số | Ý nghĩa |
|---|---|
| Initial request latency | Từ POST đến HTTP acceptance/ack |
| Callback wait duration | Thời gian từ accepted đến callback đầu tiên |
| Business completion latency | Từ tạo operation đến kết quả cuối cùng |
| Callback delivery attempts | Số lần partner gửi notification |
| Callback validation failures | Sai signature, Action, QName, XSD, RelatesTo |
| Pending operations age | Số job chưa có kết quả và tuổi |
| Callback duplicate count | Tỷ lệ gửi lặp |
| Dead-letter/reconciliation count | Kết quả chưa giao/không đồng bộ |
| SOAP Fault by action/version | Lỗi theo loại thông điệp |
| TLS/WS-Security failures | Bất thường certificate/trust/signature |

### 24.1. Deadline của initial HTTP call khác deadline của job

Ví dụ:

~~~text
Initial HTTP request budget: 3 giây
Business job deadline: 15 phút
Callback delivery retry window: 1 giờ
Retention pending/correlation state: theo chính sách
~~~

Nếu initial POST đã nhận 202 trong 200 ms, client có thể đóng HTTP connection. Nhưng business operation vẫn ở `PENDING` cho đến callback/status. Không áp read timeout 3 giây của `WebServiceTemplate` như deadline tổng 15 phút của job.

Nếu sau 15 phút không nhận callback, trạng thái có thể là `UNKNOWN` và cần reconciliation; việc gửi một `SOAP Fault` vào HTTP response đã kết thúc là bất khả thi.

### 24.2. Tracing và correlation qua hai kết nối

Có thể dùng một trace hoặc operation correlation riêng để nối:

~~~text
Initial SOAP outbound span
   -> MessageID A
   -> Async job / partner processing
   -> Callback inbound span
   -> RelatesTo A
   -> Domain completion
~~~

Trong môi trường nhiều tổ chức, distributed tracing context không nhất thiết đi xuyên WS-A tự động; cần chính sách trao đổi headers và bảo mật. `MessageID` hỗ trợ correlation nghiệp vụ, nhưng không thay OpenTelemetry trace ID và không phải authorization credential.

### 24.3. Logging không làm lộ dữ liệu

Không ghi nguyên SOAP request/response hoặc Fault Detail có thông tin khách hàng, tokens, private key hay certificate secrets. Metric labels nên dùng partner alias, operation, WS-A revision, SOAP version và outcome đã chuẩn hóa. Tránh dùng MessageID/UUID từng request làm metric labels vì cardinality cao.

## 25. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Khả năng | Kiểm tra |
|---|---|---|
| Server trả MustUnderstand Fault | Không xử lý WS-A Header revision/role đúng | Namespace, SOAP Header processing |
| Không match endpoint | `wsa:Action` sai hoặc mapping chưa bật | Action URI, endpoint mapping, WSDL |
| Body hợp XSD nhưng call fail | WS-A version/binding/action mismatch | Header QName và SOAPAction |
| Client chờ mãi sau HTTP 202 | Đang dùng same-channel API cho callback design | MEP, ReplyTo, callback listener |
| Callback không đến | Endpoint không reachable/TLS/firewall/DNS | Callback URL registration, egress/inbound |
| Callback đến nhưng không tìm pending request | RelatesTo khác MessageID hoặc pending chưa commit | Correlation store |
| Callback cập nhật nhầm order | Ghép theo business key/FIFO, không theo RelatesTo | State machine và identity |
| Callback trùng gây side effect | Thiếu inbox/deduplication | Message ID + state + idempotency |
| Fault bị mất | FaultTo không reachable hoặc không có handler | Fault routing, retries/DLQ |
| Client báo SOAPAction mismatch | wsa:Action khác action binding | HTTP header/media type/WSDL |
| Namespace 2004/08 bị từ chối | Partner chỉ hỗ trợ 1.0 | Revision URIs |
| Non-anonymous ReplyTo bị từ chối | Binding yêu cầu anonymous | WSDL/WS-Policy capability |
| Callback signature sai | Signed parts, cert hoặc header bị sửa | WS-Security policy |
| Callback gửi đến đích nguy hiểm | ReplyTo URL không được kiểm soát | SSRF allowlist/egress policy |
| SOAP 1.2 Fault parse sai | Client xử lý như SOAP 1.1 | Message factory, Fault format |
| Callback tới sau timeout | Business job chậm hoặc retry | Reconciliation, late callback policy |

### 25.1. Quy trình xử lý một lỗi callback cụ thể

Nếu đối tác nói “đã xử lý request, đã gửi callback”, nhưng ứng dụng không có kết quả:

1. Xác nhận initial request MessageID và thời điểm HTTP acceptance.
2. Kiểm tra `ReplyTo`/`FaultTo` full EPR và namespace revision.
3. Kiểm tra callback URL reachable theo chiều mạng từ đối tác.
4. Kiểm tra chứng chỉ TLS/mTLS và WS-Security của callback POST.
5. Kiểm tra raw SOAP metadata **trong môi trường bảo mật**, không công khai payload.
6. Kiểm tra `wsa:RelatesTo` và expected pending MessageID.
7. Kiểm tra Action/To/QName, callback WSDL/XSD và SOAP version.
8. Kiểm tra đã commit inbox/pending state trước acknowledgment hay chưa.
9. Kiểm tra duplicate/late messages và lỗi handling.
10. Đối soát kết quả business ở partner nếu không thể xác định tình trạng, không tự gửi lại operation có side effect.

## 26. Bài thực hành: ProcessOrder với anonymous và callback

Giả sử hệ thống có hai operation:

~~~text
GetOrder:
  Request/response nhanh
  WS-Addressing 1.0
  SOAP 1.1
  ReplyTo anonymous

ProcessOrder:
  Có xử lý nền dài
  WS-Addressing 1.0
  SOAP 1.1
  ReplyTo callback HTTPS
  FaultTo callback HTTPS khác
~~~

### Yêu cầu triển khai

1. Thiết kế XSD cho GetOrderRequest/Response và ProcessOrderRequest/Response.
2. Viết WSDL action metadata, binding và mô tả response mode cho từng operation.
3. Tạo `GetOrder` client bằng `WebServiceTemplate`/`ActionCallback`.
4. Viết XML fixture có `ReplyTo` anonymous 1.0, MessageID và expected RelatesTo.
5. Test HTTP same-channel SOAP response và SOAP Fault.
6. Tạo một pending store với request MessageID, expected action, partner identity, TTL và state.
7. Tạo outbound ProcessOrder request với non-anonymous ReplyTo/FaultTo đúng policy.
8. Giả lập server trả HTTP 202 mà không trả ProcessOrderResponse trên HTTP response đầu tiên.
9. Tạo callback receiver dùng Spring-WS `@Endpoint`/`MessageDispatcherServlet`.
10. Xác minh callback Action, To, RelatesTo, XSD, TLS/WS-Security trước khi cập nhật state.
11. Test callback thành công, Fault callback và callback đến trễ.
12. Test callback bị gửi hai lần, không thực hiện side effects trùng.
13. Test sai revision 2004/08 trong một luồng chỉ hỗ trợ 1.0.
14. Test client dùng SOAP 1.2 Envelope vào endpoint chỉ hỗ trợ SOAP 1.1.
15. Thử một non-anonymous ReplyTo trỏ đến localhost/đích không được phép và xác nhận server chặn.
16. Giả lập callback listener down và kiểm tra retry/DLQ/reconciliation.
17. Thêm metrics cho initial latency và business completion latency riêng.
18. Ghi lại support matrix chính xác cho Spring-WS/SOAP/WS-A versions đang dùng.

**Tiêu chí đạt:** Không nhầm 202 với business success, không dùng `marshalSendAndReceive` để chờ callback khác kênh, ghép đúng `RelatesTo`, chặn sai version/SSRF và có cơ chế idempotency khi callback trùng.

### 26.1. Hai câu hỏi tình huống

**Tình huống A:** Một SOAP client dùng WS-A 1.0, đặt `ReplyTo` anonymous nhưng server trả HTTP 202 không Body và 30 giây sau thử POST kết quả tới một URL không khai báo. Thiết kế đang mâu thuẫn ở đâu? Cần thống nhất contract và kiểm thử điều gì?

**Tình huống B:** Một callback `ProcessOrderResponse` có `RelatesTo` chính xác, nhưng WS-Security signature không hợp lệ. Có được cập nhật order sang COMPLETED không? Tại sao correlation không thay authentication?

## 27. Checklist trước khi công bố hỗ trợ WS-Addressing

- [ ] Đã ghi rõ WS-A revision 1.0 hay 2004/08 cho mỗi client/server.
- [ ] Đã xác minh SOAP 1.1/1.2 binding riêng với WS-A revision.
- [ ] `wsa:Action`/`To`/`MessageID`/`ReplyTo`/`FaultTo`/`RelatesTo` có QName và value đúng.
- [ ] Anonymous URI đúng revision, không bị coi là HTTP destination thật.
- [ ] WSDL/Policy công bố rõ anonymous required/optional/prohibited nếu áp dụng.
- [ ] HTTP SOAPAction hoặc media-type action phù hợp Action policy.
- [ ] Same-channel request–response được kiểm tra với SOAP response và SOAP Fault.
- [ ] Không nhầm initial HTTP 202 với completed operation.
- [ ] Non-anonymous callback có listener reachable, TLS và URL được cho phép.
- [ ] Pending request/MessageID được persist trước khi gửi request.
- [ ] Callback dùng `RelatesTo` để correlate, không dựa vào FIFO/business ID đơn lẻ.
- [ ] WS-Security bảo vệ những addressing headers cần integrity.
- [ ] Callback handler xác thực nguồn và kiểm tra quyền, không tin chỉ vào UUID.
- [ ] ReplyTo/FaultTo có allowlist/egress policy chống SSRF.
- [ ] Callback XSD, Action, SOAP version và expected contract đều được kiểm tra.
- [ ] Có durable inbox, idempotency và xử lý callback đến trễ/trùng.
- [ ] Có FaultTo routing, retry/DLQ hoặc reconciliation khi callback lỗi.
- [ ] Đã kiểm tra hành vi sau restart và network outage.
- [ ] Có support matrix cho Spring-WS version × WS-A revision × SOAP binding × reply mode.
- [ ] Không log raw SOAP secrets, keys hoặc dữ liệu nhạy cảm.
- [ ] Có interoperability tests với đối tác/stack khác Java.

## 28. Ghi nhớ

- **Same-channel reply** nghĩa là phản hồi qua HTTP response của SOAP request hiện tại; với WS-A 1.0 thường dùng `ReplyTo` anonymous.
- **Different-channel reply** nghĩa là server gửi SOAP message mới tới callback EPR; cần callback listener và correlation store, không chỉ một Header.
- **`MessageID` định danh message, `RelatesTo` ghép response/Fault với request**; không nên ghép theo HTTP connection hoặc thứ tự gửi.
- **`FaultTo` có thể khác `ReplyTo`**, nên lỗi phát sinh sau initial 202 cần được gửi/ghi nhận theo đường đã thống nhất.
- **WS-Addressing 2004/08 và 1.0 khác namespace lẫn anonymous URI**; không thể sửa bằng đổi prefix.
- **SOAP 1.1/1.2 là một trục version khác** với revision WS-Addressing.
- **`ActionCallback` và action endpoint mapping là các điểm mở rộng Spring-WS**, nhưng không tự cung cấp full asynchronous callback routing, durable delivery hoặc idempotency.
- **HTTP 202 chỉ xác nhận một mức nhận request theo contract**, không bảo đảm business operation thành công hay callback đã được gửi.
- **WS-Security, TLS, authorization và chống SSRF** là bắt buộc khi cho phép routing tới ReplyTo/FaultTo ngoài hệ thống.
- **Hỗ trợ theo phiên bản phải được kiểm chứng** bằng WSDL/Policy, SOAP Header/QName và integration tests cho từng tổ hợp thực tế.

**Câu hỏi tự kiểm tra:** Hệ thống A gọi SOAP service B bằng `WebServiceTemplate`, dùng WS-Addressing 1.0 với `ReplyTo=https://a.example.test/ws/callback` và `FaultTo=https://a.example.test/ws/faults`. B trả HTTP 202 sau 100 ms, rồi gửi `ProcessOrderResponse` sau 15 giây. A đang chờ `marshalSendAndReceive` để nhận trực tiếp `ProcessOrderResponse` và báo timeout. Hãy giải thích điểm sai của thiết kế A, nêu vai trò `MessageID`/`RelatesTo`, liệt kê các thành phần cần bổ sung để nhận callback bền vững, và chỉ ra cách kiểm thử khi callback bị gửi lại hoặc mang WS-A namespace 2004/08 thay vì 1.0.




