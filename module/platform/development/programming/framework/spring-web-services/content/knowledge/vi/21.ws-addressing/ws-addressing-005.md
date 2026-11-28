# @Address và điều kiện liên quan đến địa chỉ nhận

## 1. Bài toán: HTTP URL đúng nhưng endpoint vẫn không được chọn

Một ứng dụng **Spring Web Services (Spring-WS)** tiếp nhận SOAP request qua URL `https://gateway.example.test/ws/orders`. Client gửi XML hợp lệ theo XSD, đặt WS-Addressing `wsa:Action` đúng operation `GetOrder`, nhưng server lại không tìm thấy endpoint tương ứng.

Khi kiểm tra, đội phát triển thấy lớp endpoint có:

~~~java
@Endpoint
@Address("https://services.example.test/soap/orders/v1")
public class OrderEndpoint {
    @Action("urn:example:orders:v1:GetOrder")
    // ...
}
~~~

Trong khi SOAP Header của client ghi:

~~~xml
<wsa:To xmlns:wsa="http://www.w3.org/2005/08/addressing">
    https://gateway.example.test/ws/orders
</wsa:To>
~~~

Vấn đề không nhất thiết nằm ở XSD, JAXB hay HTTP route. Khi Spring-WS sử dụng **`AnnotationActionEndpointMapping`**, annotation **`@Address` trên lớp** là một điều kiện bổ sung: giá trị của nó được so sánh với **destination** (thường lấy từ `wsa:To`) của request. `@Action` có thể khớp, nhưng `To` không khớp `@Address` thì mapping này không chọn method đó.

Đây là điểm khác biệt giữa **địa chỉ kết nối vật lý** và **địa chỉ nhận ở mức thông điệp**.

Trong chương **WS-Addressing**, bài học tập trung vào:

- Hiểu đúng `@Address`: vị trí khai báo, ý nghĩa, và điều kiện khớp với `wsa:To`.
- Phân biệt `@Address` với `@Action`, `@PayloadRoot`, HTTP endpoint URL, `soap:address` trong WSDL và `wsa:ReplyTo`.
- Cấu hình Spring-WS server/client theo hướng **contract-first** với XSD/WSDL và endpoint thực tế.
- Xử lý proxy, gateway, multi-tenant, các phiên bản WS-Addressing và xung đột endpoint mapping.
- Kiểm soát WS-Security, SOAP Fault, endpoint reference, callback không đồng bộ và kiểm thử tương thích.

**Kết luận cốt lõi:** `@Address` không tạo một HTTP route; nó **ràng buộc địa chỉ đích trong SOAP Header** khi một WS-Addressing endpoint mapping đang tham gia lựa chọn endpoint.

## 2. WS-Addressing tách định tuyến thông điệp khỏi transport

WS-Addressing định nghĩa một nhóm **Message Addressing Properties (MAPs)** thường được biểu diễn bằng các phần tử SOAP Header. Thay vì chỉ dựa trên transport URL, message có thể chỉ rõ **đích logic**, **ý định operation** và **địa chỉ nhận phản hồi**.

Một SOAP request minh họa với WS-Addressing 1.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">

    <env:Header>
        <wsa:To env:mustUnderstand="true">https://services.example.test/soap/orders/v1</wsa:To>
        <wsa:Action env:mustUnderstand="true">urn:example:orders:v1:GetOrder</wsa:Action>
        <wsa:MessageID>urn:uuid:3a19d520-8196-4bd7-9301-4a7ac3340b12</wsa:MessageID>
        <wsa:ReplyTo>
            <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
        </wsa:ReplyTo>
    </env:Header>

    <env:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

Ở đây:

- SOAP **Envelope** mang nội dung theo SOAP 1.2.
- WS-Addressing **Header** dùng namespace `http://www.w3.org/2005/08/addressing`.
- `wsa:To` xác định địa chỉ đích **của thông điệp**, có thể khác URL kết nối tới reverse proxy.
- `wsa:Action` chỉ ý định/operation mà thông điệp yêu cầu.
- `wsa:MessageID` giúp tương quan các thông điệp và hỗ trợ quan sát/đối soát khi tích hợp.
- `wsa:ReplyTo` cho biết nơi gửi phản hồi; địa chỉ `anonymous` thường gắn với phản hồi trên kênh request hiện tại.
- Phần `ord:GetOrderRequest` nằm trong SOAP Body, theo **XSD nghiệp vụ**, độc lập với namespace WS-Addressing.

XML ví dụ không đồng nghĩa rằng mọi đối tác đều phải gửi đủ các header theo chính xác cách đó. Những thuộc tính bắt buộc và ngữ nghĩa mặc định phụ thuộc **phiên bản WS-Addressing, message exchange pattern, binding và policy** đã thống nhất.

### 2.1. Bảng MAP quan trọng

| Thuộc tính | Phần tử SOAP Header điển hình | Ý nghĩa | Có trực tiếp quyết định `@Address`? |
| --- | --- | --- | --- |
| Destination | `wsa:To` | Địa chỉ đích của message | **Có**, khi annotation hiện diện và Action mapping được sử dụng |
| Action | `wsa:Action` | Ý định của message/operation | Không; liên quan `@Action` trên method |
| Reply endpoint | `wsa:ReplyTo/wsa:Address` | Đích của phản hồi thường | **Không** |
| Fault endpoint | `wsa:FaultTo/wsa:Address` | Đích xử lý Fault | **Không** |
| Message ID | `wsa:MessageID` | Định danh message | Không |
| Relationship | `wsa:RelatesTo` | Liên hệ response với message khác | Không |
| From endpoint | `wsa:From/wsa:Address` | Thông tin nguồn thông điệp | Không |

`@Address` **không** kiểm tra `ReplyTo`, `FaultTo` hoặc `MessageID`. Những thuộc tính đó có những trách nhiệm bảo mật và xử lý đáp ứng riêng.

### 2.2. Đường đi hai lớp địa chỉ

~~~mermaid
flowchart LR
    C["SOAP client"] -->|"HTTPS POST: gateway URL"| G["API Gateway"]
    G -->|"forward /ws/orders"| S["MessageDispatcherServlet"]
    S --> M["AnnotationActionEndpointMapping"]
    H["SOAP Header: To + Action"] --> M
    M -->|"Action và To phù hợp"| E["@Endpoint method"]
    M -->|"To không khớp @Address"| N["Mapping không chọn method này"]
~~~

Hai lớp **HTTP forwarding** và **WS-Addressing matching** không tự điều chỉnh lẫn nhau. Gateway đưa request đến servlet thành công không chứng minh `wsa:To` đúng; `wsa:To` đúng cũng không tự mở một kết nối tới URL đó.

## 3. `@Address` thực sự là annotation gì?

Tên đầy đủ:

~~~java
org.springframework.ws.soap.addressing.server.annotation.Address
~~~

Annotation này có đặc điểm:

- Áp dụng ở **cấp lớp** (`@Target(TYPE)`), không phải parameter hoặc method.
- Có một giá trị bắt buộc dạng chuỗi (`String value()`) đại diện địa chỉ WS-Addressing mà lớp endpoint xử lý.
- Khi dùng `AnnotationActionEndpointMapping`, giá trị `@Address` được đối chiếu với **destination** của incoming message.
- Nếu không khai báo `@Address`, mapping theo `@Action` có thể **bỏ qua điều kiện destination** đối với endpoint method đó.

Mẫu:

~~~java
@Endpoint
@Address("https://services.example.test/soap/orders/v1")
public class OrderEndpoint {
    // Các method @Action trong lớp này chịu điều kiện địa chỉ.
}
~~~

Không nên hiểu rằng đặt `@Address` trên lớp tự tạo servlet tại URL đó hoặc tự cập nhật `soap:address` trong WSDL.

### 3.1. Kết hợp với `@Action` ở method

Tên đầy đủ:

~~~java
org.springframework.ws.soap.addressing.server.annotation.Action
~~~

`@Action` áp dụng ở **cấp method** và ánh xạ giá trị của WS-Addressing `Action` tới handler.

~~~java
@Endpoint
@Address("https://services.example.test/soap/orders/v1")
public class OrderEndpoint {

    @Action("urn:example:orders:v1:GetOrder")
    public Source getOrder(/* ... */) {
        // ...
    }

    @Action("urn:example:orders:v1:CancelOrder")
    public Source cancelOrder(/* ... */) {
        // ...
    }
}
~~~

Với `AnnotationActionEndpointMapping`, hai method có hai `Action` khác nhau nhưng **cùng điều kiện địa chỉ đích** từ annotation ở lớp. Trong cùng hệ thống, một endpoint khác có thể dùng `@Address` khác để mô tả một đích logic khác.

### 3.2. Đọc đúng điều kiện ánh xạ

Khi mapping dựa trên WS-Addressing này được chọn:

~~~text
Action của incoming message có method @Action tương ứng?
    |
    +-- Không -> mapping không chọn method
    |
    +-- Có -> class endpoint có @Address?
                  |
                  +-- Không -> không áp điều kiện To từ @Address
                  |
                  +-- Có -> incoming destination (To) có khớp địa chỉ?
                                   |
                                   +-- Có -> method là ứng viên hợp lệ
                                   |
                                   +-- Không -> mapping không chọn method
~~~

Đây là logic **chọn handler**, không phải mô tả mọi validation/protocol check khác của WS-Addressing. Bên cạnh đó, Spring-WS có thể có **nhiều `EndpointMapping`**; việc mapping này không chọn handler **không loại trừ** một mapping khác hoặc một default endpoint có thể được thử sau đó.

### 3.3. Không nhầm với một annotation bảo mật

`@Address` không kiểm tra:

- Người gọi đã xác thực bằng certificate, HTTP auth hoặc WS-Security hay chưa.
- SOAP Header có được ký và chống sửa đổi hay chưa.
- Người dùng/tenant có quyền gọi `CancelOrder` hay không.
- XML Body có hợp XSD và chữ ký hợp lệ không.
- `ReplyTo`/`FaultTo` có trỏ về host an toàn hay không.

Client có thể tự đặt `wsa:To` nếu không có cơ chế xác thực/tính toàn vẹn thích hợp. Vì vậy **không dùng riêng `@Address` làm hàng rào phân quyền đa tenant hoặc ranh giới bảo mật**.

## 4. Điều kiện cốt lõi: khớp `wsa:To`, không phải HTTP URL

Giả sử topology:

~~~text
Client gọi HTTPS:
  https://api.example.test/partner/orders

Gateway rewrite:
  http://orders-service:8080/ws/orders

WS-Addressing To logic:
  https://services.example.test/soap/orders/v1

@Address trên endpoint:
  https://services.example.test/soap/orders/v1
~~~

Đây có thể là **một cấu hình hợp lệ** nếu gateway, SOAP stack và policy của đối tác cho phép tách địa chỉ transport và message destination. Trong trường hợp đó, HTTP POST vẫn đi đến gateway; `@Address` so sánh với đích logic.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| URL client kết nối | `https://api.example.test/partner/orders` | Địa chỉ mạng/HTTP thực |
| URL container nội bộ | `http://orders-service:8080/ws/orders` | Địa chỉ sau proxy rewrite |
| `soap:address location` trong WSDL | Có thể là URL public mà client kết nối | Mô tả transport endpoint |
| `wsa:To` | `https://services.example.test/soap/orders/v1` | Destination trong thông điệp |
| `@Address` | `https://services.example.test/soap/orders/v1` | Điều kiện đối với destination |
| `wsa:Action` | `urn:example:orders:v1:GetOrder` | Chọn method qua `@Action` |

Không có quy tắc “`@Address` luôn phải bằng `soap:address`”. **Nhưng nếu không có lý do cần đích logic khác, giữ chúng thống nhất là cách cấu hình đơn giản, giảm lỗi.** Nếu cố ý khác, phải giải thích trong tài liệu tích hợp và kiểm thử chính xác cả HTTP URL lẫn WS-Addressing To.

### 4.1. Các khác biệt URI dễ gây mismatch

Trong ví dụ:

~~~text
Đúng:   https://services.example.test/soap/orders/v1
Sai:    https://services.example.test/soap/orders/v1/
Sai:    http://services.example.test/soap/orders/v1
Sai:    https://services.example.test/soap/orders/v2
Sai:    https://api.example.test/partner/orders
~~~

Khác `http`/`https`, path, version hoặc dấu `/` cuối có thể khiến URI không bằng giá trị `@Address`. **Không nên dựa vào việc proxy hoặc endpoint mapping tự chuẩn hóa mọi URI tương đương.** Spring-WS xét kiểu `URI` và so sánh theo logic implementation; trong thực tế hãy dùng một URI đã thống nhất và test chính giá trị trên dây.

Các chi tiết khác cần kiểm tra: explicit port `:443`, query string, percent-encoding, host alias, context path, và hostname đã biến đổi bởi proxy. Không áp dụng một bộ “chuẩn hóa” tùy tiện làm thay đổi contract.

### 4.2. Nếu thiếu `wsa:To`?

Không thể khẳng định một kết quả chung cho mọi profile. WS-Addressing version và SOAP stack có quy tắc xử lý message addressing properties, mặc định và Fault riêng.

Tại điểm so sánh `@Address`, nếu incoming destination **không cung cấp giá trị khớp**, method có điều kiện địa chỉ thường không được mapping này chọn. Nhưng trước đó có thể:

- Message bị xử lý lỗi WS-Addressing vì thiếu MAP bắt buộc theo policy.
- Một cơ chế lấy destination từ transport được áp dụng theo implementation.
- Mapping khác không yêu cầu `To` được thử.

Vì vậy **test request thiếu `To`** phải quan sát cả endpoint thực sự chạy, SOAP Fault và HTTP status theo đúng phiên bản đang dùng. Không xem “đường dẫn đúng” là phép thay thế chắc chắn cho `To`.

### 4.3. Nếu lớp không có `@Address`?

Theo ý nghĩa của `AnnotationActionEndpointMapping`, khi annotation không hiện diện, điều kiện địa chỉ từ annotation có thể được **bỏ qua** cho endpoint đó: ánh xạ theo `@Action` vẫn có thể thành công dù `wsa:To` khác.

Đây là một lựa chọn thiết kế có chủ đích, không phải hành vi nên dựa vào để bỏ qua policy WS-Addressing. Nếu hợp đồng bắt buộc một destination cố định, hãy khai báo `@Address` và kiểm thử, đồng thời kiểm tra security và mapping precedence.

## 5. Ví dụ contract-first với XSD đơn hàng

Một service theo hướng contract-first định nghĩa payload trong XSD; header WS-Addressing tồn tại **bên ngoài** schema nghiệp vụ.

File `src/main/resources/xsd/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:pattern value="ORD-[0-9]{4,12}"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="tns:OrderIdType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Global element `GetOrderRequest` có QName `{urn:example:orders:v1}GetOrderRequest`. Nó **không phải** `wsa:Action` và không phải `wsa:To`. Ba giá trị được xác định ở ba nơi:

~~~text
XSD:
  {urn:example:orders:v1}GetOrderRequest

WS-Addressing header:
  To     = https://services.example.test/soap/orders/v1
  Action = urn:example:orders:v1:GetOrder

HTTP:
  POST https://api.example.test/partner/orders
~~~

### 5.1. WSDL: phần công bố transport và operation

WSDL 1.1 mô tả operation, message và SOAP binding. Một fragment `wsdl:service`:

~~~xml
<wsdl:service name="OrderService">
    <wsdl:port name="OrdersSoapPort"
               binding="tns:OrdersSoapBinding">
        <soap:address
            location="https://api.example.test/partner/orders"/>
    </wsdl:port>
</wsdl:service>
~~~

Đây là **đoạn trích WSDL**, giả định `wsdl:definitions` có khai báo prefix `wsdl`, `tns` và `soap` cùng port/binding/message hoàn chỉnh.

**`soap:address` ở đây là transport endpoint** được công bố. Nó không phải annotation Java `@Address`. Nếu đối tác yêu cầu một `wsa:To` logic khác HTTP URL, yêu cầu đó phải được công bố rõ qua tài liệu/metadata/policy tương thích WS-Addressing; không để client tự đoán.

`DefaultWsdl11Definition` có thể giúp tạo WSDL từ XSD theo quy ước nhưng **không được giả định** nó tự khai báo toàn bộ WS-Addressing metadata/policy hoặc đồng bộ `@Address` với `soap:address`. Với tích hợp nghiêm ngặt, cần kiểm tra WSDL tĩnh/động thực sự được xuất bản.

### 5.2. QName payload không tự bị thay bởi `To`

Một SOAP Body:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

không trở thành operation `CancelOrder` khi chỉ đổi `wsa:To`. Nếu `AnnotationActionEndpointMapping` chọn method theo `@Action`, muốn đổi operation đúng phải dùng Action phù hợp và Body hợp contract. Đừng dùng `To` như một “tham số nghiệp vụ ngầm” để thay thế schema.

## 6. Server Spring-WS: `@EnableWs`, `@Endpoint`, `@Action` và `@Address`

Trong nhiều thế hệ Spring-WS hỗ trợ Java configuration, `@EnableWs` nạp hạ tầng annotation endpoint thông qua `WsConfigurationSupport`. Các mapping thường được đăng ký:

| EndpointMapping | Điều kiện để chọn method | Thứ tự mặc định thường thấy |
| --- | --- | --- |
| `PayloadRootAnnotationMethodEndpointMapping` | `@PayloadRoot` và root QName | 0 |
| `SoapActionAnnotationMethodEndpointMapping` | `@SoapAction` và HTTP SOAPAction | 1 |
| **`AnnotationActionEndpointMapping`** | **`@Action`, có thể thêm `@Address`/destination** | **2** |

Thứ tự này được tài liệu Java configuration Spring-WS mô tả; nếu ứng dụng **tự thay thế/customize mapping hoặc dùng một thế hệ khác**, hãy kiểm tra bean và `order` runtime. Mapping có giá trị order nhỏ hơn thường được thử trước.

### 6.1. Điểm khởi động và cấu hình

~~~java
package example.orders.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderSoapApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderSoapApplication.class, args);
    }
}
~~~

~~~java
package example.orders.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;

@Configuration
@EnableWs
public class SpringWsConfig {
    // Spring-WS annotation endpoint infrastructure.
}
~~~

Khi Boot quản lý đăng ký SOAP servlet và phiên bản hỗ trợ property liên quan, có thể dùng:

~~~properties
server.port=8080
spring.webservices.path=/ws
~~~

Nếu ứng dụng tự khai báo `ServletRegistrationBean<MessageDispatcherServlet>`, cần xác minh mapping thực tế và cơ chế Boot back-off; không đăng ký hai SOAP servlet chồng nhau chỉ để cấu hình WS-Addressing.

### 6.2. Endpoint dùng duy nhất chiến lược WS-Addressing trong ví dụ

~~~java
package example.orders.ws;

import javax.xml.transform.Source;
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.addressing.server.annotation.Action;
import org.springframework.ws.soap.addressing.server.annotation.Address;
import org.springframework.xml.transform.StringSource;

@Endpoint
@Address("https://services.example.test/soap/orders/v1")
public class OrderAddressingEndpoint {

    @Action(
        value = "urn:example:orders:v1:GetOrder",
        output = "urn:example:orders:v1:GetOrderResponse",
        fault = "urn:example:orders:v1:GetOrderFault"
    )
    @ResponsePayload
    public Source getOrder(@RequestPayload Source request) {
        // Demo định tuyến; chưa đọc/truy vấn dữ liệu trong request.
        return new StringSource(
                "<o:GetOrderResponse " +
                "xmlns:o=\"urn:example:orders:v1\">" +
                "<o:status>FOUND</o:status>" +
                "</o:GetOrderResponse>");
    }
}
~~~

Giải thích:

1. `@Endpoint` đánh dấu class là Spring-WS endpoint.
2. **`@Address` trên class** giới hạn địa chỉ đích logic mà class nhận.
3. **`@Action.value` trên method** định danh WS-Addressing request Action.
4. `@Action.output` khai báo WS-Addressing Action cho response.
5. `@Action.fault` khai báo WS-Addressing Action cho fault response theo cơ chế framework.
6. `@RequestPayload`/`@ResponsePayload` ánh xạ XML payload với Java argument/return.

`output` và `fault` là các thuộc tính tùy chọn của `@Action`. Chúng liên quan **WS-Addressing header của thông điệp trả về**, không tự tạo response XSD hay typed SOAP Fault detail. Phần response/fault contract vẫn cần được thiết kế và kiểm thử riêng.

Đây là **endpoint kiểm tra routing**, không phải nghiệp vụ hoàn chỉnh: method trả XML cố định. Hệ thống thật phải parse/validate XML, dùng JAXB khi phù hợp và áp dụng authentication, authorization, validation, SOAP Fault mapping theo contract.

**Chủ ý trong ví dụ:** không gắn thêm `@PayloadRoot` hoặc `@SoapAction` vào cùng method, để tránh mapping khác chọn method trước khi `AnnotationActionEndpointMapping` kịp áp dụng điều kiện `@Address`.

### 6.3. Nếu vừa có `@PayloadRoot` vừa có `@Action`?

Ví dụ dễ gây hiểu nhầm:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
@Action("urn:example:orders:v1:GetOrder")
public Source getOrder(/* ... */) {
    // ...
}
~~~

Khi `@EnableWs` tạo các endpoint mappings theo thứ tự mặc định, **`PayloadRootAnnotationMethodEndpointMapping` có thứ tự cao hơn `AnnotationActionEndpointMapping`**. Nếu root QName khớp và mapping đầu chọn method, điều kiện `@Address` của addressing mapping có thể **không được dùng để quyết định lựa chọn handler**.

Đây là rủi ro nếu nhóm phát triển dựa vào `@Address` để đảm bảo message To đúng. Để có một chính sách chắc chắn:

- Chọn **một routing strategy chính** cho operation quan trọng.
- Nếu cần cả Action, To và QName cùng hợp lệ, hãy **kiểm tra các điều kiện bổ sung bằng policy/interceptor phù hợp** và test, thay vì trông chờ thứ tự annotation tự biến thành phép AND.
- Xem danh sách `EndpointMapping` thực tế và thứ tự của chúng trong context.
- Không coi `@Address` là authorization; validate signed header và quyền caller độc lập.

### 6.4. Không tạo thêm addressing mapping trùng khi không cần

Với `@EnableWs`, hạ tầng Java configuration thường đã đăng ký `AnnotationActionEndpointMapping`. Không tự tạo thêm một `@Bean AnnotationActionEndpointMapping` trùng chức năng chỉ vì endpoint có `@Address`: việc đó có thể sinh nhiều mapping và cấu hình interceptor/versions khác nhau.

Nếu triển khai trên XML/WAR hoặc custom infrastructure, hãy xác minh mapping đã được kích hoạt theo phiên bản hiện tại, rồi mới khai báo thủ công nếu cần. **Bean tồn tại** và **bean thực sự tham gia dispatcher** là hai điều cần kiểm chứng riêng.

## 7. Phía client: `ActionCallback` và địa chỉ `To` tường minh

Spring-WS có callback dành cho **WS-Addressing**:

~~~java
org.springframework.ws.soap.addressing.client.ActionCallback
~~~

Không nhầm với callback SOAP Action:

~~~java
org.springframework.ws.soap.client.core.SoapActionCallback
~~~

| Callback | Thứ được đặt | Vai trò |
| --- | --- | --- |
| `ActionCallback` | WS-Addressing `wsa:Action`, `wsa:To` và một số MAP liên quan | Điều khiển addressing headers trong SOAP Envelope |
| `SoapActionCallback` | SOAP action theo binding/transport | Header/action của SOAP binding, không tự tạo đầy đủ WS-Addressing MAP |

Khi server dùng `@Action` + `@Address`, **`ActionCallback`** là điểm bắt đầu phù hợp để client khai báo đúng message destination.

### 7.1. Callback chỉ truyền Action: `To` thường lấy từ URI kết nối

~~~java
import org.springframework.ws.soap.addressing.client.ActionCallback;

ActionCallback callback = new ActionCallback(
        "urn:example:orders:v1:GetOrder");
~~~

Theo API Spring-WS, constructor nhận Action như trên sử dụng **WS-Addressing 1.0** và mặc định khởi tạo `To` từ **connection URI**.

Nếu client gọi:

~~~text
https://api.example.test/partner/orders
~~~

thì `To` mặc định có thể trở thành chính URI đó. Nếu server đặt:

~~~java
@Address("https://services.example.test/soap/orders/v1")
~~~

thì request có Action đúng nhưng **To khác**; `AnnotationActionEndpointMapping` có thể không chọn method.

Đây là lỗi dễ gặp sau reverse proxy: lập trình viên thử thay URL HTTP mà không kiểm tra WS-Addressing Header cũng đã thay đổi.

### 7.2. Callback có `Action`, phiên bản và `To` rõ ràng

`ActionCallback` hỗ trợ constructor cung cấp riêng **Action**, **AddressingVersion** và **To**:

~~~java
package example.orders.client;

import java.net.URI;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.addressing.client.ActionCallback;
import org.springframework.ws.soap.addressing.version.Addressing10;

public final class OrderSoapGateway {

    private final WebServiceTemplate template;

    public OrderSoapGateway(WebServiceTemplate template) {
        this.template = template;
    }

    public Object getOrder(Object jaxbRequest) {
        URI action = URI.create(
                "urn:example:orders:v1:GetOrder");
        URI logicalTo = URI.create(
                "https://services.example.test/soap/orders/v1");
        String transportUri =
                "https://api.example.test/partner/orders";

        ActionCallback callback =
                new ActionCallback(
                        action,
                        new Addressing10(),
                        logicalTo);

        return template.marshalSendAndReceive(
                transportUri,
                jaxbRequest,
                callback);
    }
}
~~~

Ví dụ giả định:

- `WebServiceTemplate` đã cấu hình JAXB `Marshaller`/`Unmarshaller` và SOAP binding.
- `jaxbRequest` là object JAXB hoặc `JAXBElement` mang root QName `GetOrderRequest` đúng XSD.
- Gateway có route từ `transportUri` tới dịch vụ SOAP.
- Đối tác chấp nhận `logicalTo` và phiên bản `Addressing10`.
- TLS/WS-Security, timeout, retry và Fault handling được cấu hình riêng.

**URI transport** dùng để mở kết nối, còn **logicalTo** là destination gửi trong SOAP Header. Không dùng `logicalTo` làm URL kết nối nếu hệ thống mạng không cung cấp route tới địa chỉ đó.

### 7.3. Các MAP khác ở client

`ActionCallback` còn có API liên quan `ReplyTo`, `FaultTo`, `From` và chiến lược tạo `MessageID`, tùy phiên bản.

Tuy nhiên:

- `ReplyTo` **không phải** `To` và không được `@Address` so sánh.
- `FaultTo` là đích nhận thông điệp lỗi, không phải cơ chế ánh xạ exception Java.
- `MessageID` hỗ trợ correlation, **không bảo đảm idempotency** nếu server không có logic chống trùng.
- Địa chỉ do client cung cấp có thể khiến server mở kết nối outbound, nên phải kiểm soát SSRF và quyền truy cập.

Không tự thêm header sau khi SOAP message đã được ký nếu thao tác đó làm chữ ký WS-Security mất hiệu lực.

### 7.4. Vô hiệu hóa `To` mặc định là một lựa chọn cần kiểm thử

Một số phiên bản `ActionCallback` có `setShouldInitializeTo(false)`. Nếu tắt khởi tạo `To`, đừng mặc định endpoint có `@Address` sẽ chấp nhận request: thiếu destination hoặc destination không khớp vẫn có thể dẫn tới mapping failure hoặc WS-Addressing Fault.

Chỉ dùng tùy chọn này khi có thành phần khác **được kiểm soát rõ** thiết lập To hoặc profile cho phép, và kiểm tra SOAP Header cuối cùng sau toàn bộ callback/interceptor.

## 8. Ba kiểu “địa chỉ” trong cùng một SOAP request

Một request có thể gửi đến:

~~~http
POST /partner/orders HTTP/1.1
Host: api.example.test
Content-Type: application/soap+xml; charset=utf-8
~~~

Và có SOAP Header:

~~~xml
<env:Header
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:To>https://services.example.test/soap/orders/v1</wsa:To>
    <wsa:Action>urn:example:orders:v1:GetOrder</wsa:Action>
    <wsa:ReplyTo>
        <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
    </wsa:ReplyTo>
</env:Header>
~~~

Fragment trên chỉ minh họa SOAP Header, không phải Envelope hoàn chỉnh.

| Tên | Ví dụ | Câu hỏi nó trả lời |
| --- | --- | --- |
| HTTP destination | `api.example.test/partner/orders` | Request kết nối host/path nào? |
| WS-Addressing `To` | `services.example.test/soap/orders/v1` | Thông điệp dành cho đích logic nào? |
| WS-Addressing `ReplyTo` | URI `anonymous` | Response thường gửi tới đâu? |

`@Address` so sánh với **dòng thứ hai**, không phải HTTP URL hoặc ReplyTo. Việc định tuyến response/fault theo `ReplyTo`/`FaultTo` là trách nhiệm khác của addressing stack và transport.

### 8.1. `To` khác `ReplyTo`

~~~xml
<wsa:To>https://services.example.test/soap/orders/v1</wsa:To>
<wsa:ReplyTo>
    <wsa:Address>https://client.example.test/callback</wsa:Address>
</wsa:ReplyTo>
~~~

- `To` vẫn là giá trị kiểm tra với `@Address` server.
- `ReplyTo` yêu cầu hướng phản hồi tới callback theo profile hỗ trợ.
- Server có thể cần **kết nối outbound mới** thay vì trả trên HTTP response hiện tại.
- Server phải kiểm tra URI do client cung cấp trước khi kết nối.

Không đổi `@Address` thành callback URL của client: đó là hai chiều giao tiếp khác nhau.

### 8.2. `FaultTo` khác `To`

`wsa:FaultTo` chỉ định địa chỉ định tuyến thông điệp lỗi trong một số kiểu trao đổi. Nó không thay đổi điều kiện nhận request của `@Address` và không bảo đảm Fault được gửi thành công qua mạng.

Khi dùng `SoapFaultMappingExceptionResolver` để tạo Fault nghiệp vụ, cần kiểm tra riêng **Fault Action**, `RelatesTo` và đích `FaultTo`. Ánh xạ exception Java thành Fault XML và định tuyến Fault ra ngoài là **hai công đoạn khác nhau**.

## 9. Phiên bản WS-Addressing khác phiên bản SOAP

Spring-WS hỗ trợ các phiên bản WS-Addressing phổ biến, nhưng namespace/header semantics có thể khác:

| Phiên bản | Namespace header thường dùng | Spring-WS abstraction |
| --- | --- | --- |
| WS-Addressing 1.0 (W3C, 2005/08) | `http://www.w3.org/2005/08/addressing` | `Addressing10` |
| Bản nháp 2004/08 | `http://schemas.xmlsoap.org/ws/2004/08/addressing` | `Addressing200408` |

Không trộn namespace hai phiên bản trong cùng message rồi kỳ vọng framework xử lý như một bộ MAP hợp lệ.

### 9.1. Cấu hình phiên bản hai phía

Ở client:

~~~java
new ActionCallback(
        URI.create("urn:example:orders:v1:GetOrder"),
        new Addressing10(),
        URI.create("https://services.example.test/soap/orders/v1"));
~~~

Server `AnnotationActionEndpointMapping` có thuộc tính `versions` để cấu hình các WS-Addressing versions được hỗ trợ. Trong nhiều phiên bản Spring-WS, mặc định có `Addressing10` và `Addressing200408`. Nếu dự án yêu cầu một phiên bản duy nhất, hãy xác định từ policy và kiểm thử runtime.

Không thay bean mapping tùy chỉnh vào context `@EnableWs` một cách máy móc; tránh tạo duplicate mapping hoặc danh sách interceptor khác mong đợi.

### 9.2. SOAP Envelope namespace không phải addressing namespace

SOAP 1.1:

~~~xml
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"/>
~~~

SOAP 1.2:

~~~xml
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"/>
~~~

Đó là **SOAP Envelope namespaces**; WS-Addressing dùng namespace khác cho Header. Không suy rằng `Addressing10` chỉ dùng được với một SOAP version cụ thể.

HTTP `SOAPAction` của SOAP 1.1, tham số `action` của `application/soap+xml` trong SOAP 1.2 và `wsa:Action` là những vị trí dữ liệu khác nhau. Khi contract yêu cầu nhất quán, kiểm tra cả các giá trị đó.

## 10. Những trường hợp `@Address` không được áp dụng như mong đợi

### 10.1. Mapping khác chọn method trước

Nếu một method vừa có:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest")
@Action("urn:example:orders:v1:GetOrder")
public Source getOrder(/* ... */) {
    // ...
}
~~~

thì trong Java configuration mặc định `PayloadRootAnnotationMethodEndpointMapping` có độ ưu tiên cao hơn `AnnotationActionEndpointMapping`. Nếu root QName khớp và mapping đầu chọn method, **`@Address` có thể không được kiểm tra trong bước mapping đó**.

Do vậy, phát biểu “cứ có `@Address` là request có To khác chắc chắn không đến được method” không đúng với mọi ứng dụng. Nếu doanh nghiệp bắt buộc kiểm tra cả To, Action, root QName và quyền caller:

- Chọn routing strategy chính có chủ đích.
- Kiểm tra các điều kiện khác trong security/validation mechanism phù hợp.
- Test request “Body hợp lệ + WS-Addressing Action đúng + To sai”.
- Xem các bean `EndpointMapping` và giá trị `order` runtime.

### 10.2. Chỉ khai báo `@Address`, không có `@Action`

`@Address` ở lớp là **điều kiện destination**, không tự tạo ánh xạ method. Ví dụ:

~~~java
@Endpoint
@Address("https://services.example.test/soap/orders/v1")
public class OrderEndpoint {
    public Source getOrder(/* ... */) {
        // Không có @Action hoặc mapping strategy khác.
    }
}
~~~

không đủ để `AnnotationActionEndpointMapping` chọn method theo WS-Addressing Action. Cần annotation method hoặc một chiến lược mapping khác mà dispatcher hỗ trợ.

### 10.3. Servlet, component scan hoặc context sai

Khi request chưa tới `MessageDispatcherServlet`, **không có điều kiện `@Address` nào được đánh giá**. Không sửa To nếu gateway trả HTTP 404 trước khi vào server. Tương tự, nếu `@Endpoint` ngoài package scan hoặc mapping bean không được nạp vào đúng application context, To đúng vẫn không giải quyết được.

### 10.4. Hai endpoint dùng cùng `@Action` nhưng `@Address` khác

Giả sử hai tenant:

~~~java
@Endpoint
@Address("https://tenant-a.example.test/ws/orders")
class TenantAEndpoint {
    @Action("urn:example:orders:GetOrder")
    // ...
}
~~~

và:

~~~java
@Endpoint
@Address("https://tenant-b.example.test/ws/orders")
class TenantBEndpoint {
    @Action("urn:example:orders:GetOrder")
    // ...
}
~~~

Không nên mặc định `AnnotationActionEndpointMapping` tạo khóa compound **(Action, To)** rồi xử lý được hai handler trùng Action. Hạ tầng `AbstractActionEndpointMapping` chủ yếu **lookup theo Action URI**, sau đó mới xét destination của endpoint đã được chọn; Action trùng có thể gây xung đột registration hoặc không dispatch theo ý định.

Các hướng xử lý:

1. Dùng Action URI khác nhau nếu đó thực sự là hai operation/hợp đồng.
2. Tách SOAP servlet hoặc application context khi cần cô lập độc lập.
3. Dùng một endpoint nhận Action rồi xác thực tenant và định tuyến nghiệp vụ theo identity đã kiểm chứng.
4. Chỉ xây dựng custom mapping theo cặp Action+To khi có yêu cầu thực, có contract và kiểm thử cụ thể.

**`@Address` không phải cơ chế multi-tenant routing tự động cho nhiều class cùng Action.**

### 10.5. WSDL được công bố nhưng client không gửi WS-Addressing

Nếu WSDL chỉ công bố `soap:address` và `soapAction` theo SOAP 1.1, client sinh từ WSDL có thể gửi SOAP request với **HTTP SOAPAction** mà không có `wsa:To`/`wsa:Action`. Khi server chỉ đăng ký handler `@Action`, request có thể không tìm thấy method.

Đây là lỗi **hợp đồng/khả năng tương thích**, không chỉ là annotation sai. Client phải được hướng dẫn sử dụng WS-Addressing theo WSDL metadata/policy hoặc thỏa thuận tích hợp. `SoapActionCallback` và `ActionCallback` không thay thế nhau.

## 11. WSDL, endpoint reference và policy dành cho đối tác

Trong WSDL 1.1:

- `wsdl:portType` mô tả các operation trừu tượng.
- `wsdl:binding` mô tả SOAP transport/binding.
- `wsdl:service/wsdl:port/soap:address` xác định transport endpoint.
- WS-Addressing có thể được thể hiện qua **metadata, policy hoặc Endpoint Reference (EPR)** theo chuẩn/profile áp dụng.

Một EPR WS-Addressing 1.0:

~~~xml
<wsa:EndpointReference
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
    <wsa:Address>https://services.example.test/soap/orders/v1</wsa:Address>
</wsa:EndpointReference>
~~~

Giá trị `wsa:Address` trong EPR mô tả địa chỉ endpoint; nó không phải annotation Java `@Address`, dù hai giá trị có thể được thiết kế tương ứng.

**Không nhầm** `EndpointReference/wsa:Address` với `ReplyTo/wsa:Address`: chúng dùng cùng tên phần tử nhưng ở hai ngữ cảnh và chiều giao tiếp khác nhau.

### 11.1. Những gì policy tích hợp cần chốt

Đối tác doanh nghiệp có thể yêu cầu:

- WS-Addressing 1.0 bắt buộc.
- `wsa:Action` và `wsa:To` có giá trị URI cố định.
- Response chứa `wsa:RelatesTo` tham chiếu `MessageID` của request.
- `ReplyTo` chỉ cho phép anonymous hoặc callback host đã được duyệt.
- WS-Security bảo vệ header và Body theo signed-parts policy.
- SOAP Fault có WS-Addressing Action, QName/detail đúng contract.

Một XSD business payload không mô tả đủ các điều kiện Header này; `@Address` cũng không tự công bố chúng vào WSDL. Nếu dùng WSDL động như `DefaultWsdl11Definition`, phải đọc **WSDL thực tế**, không giả định metadata WS-Addressing đã được sinh tự động.

### 11.2. URI logic qua local, staging và production

Một hệ thống có thể có:

~~~text
local:       http://localhost:8080/ws/orders
staging:     https://staging-api.example.test/ws/orders
production:  https://api.example.test/ws/orders
~~~

Trong khi To logic giữ cố định hoặc biến thiên theo môi trường. Cần chọn chiến lược rõ:

1. **Stable logical To:** mọi môi trường dùng một URI logic theo hợp đồng, dù transport URL khác.
2. **To theo môi trường:** endpoint/mapping của staging/prod được cấu hình và test riêng.
3. **To trùng public URL:** đơn giản và thuận tiện khi không có yêu cầu đích logic tách biệt.

Giá trị `@Address` là **literal annotation tại compile time**. Không thể giả định Spring tự thay giá trị trong annotation bằng placeholder property khi khởi động. Nếu phải cấu hình URI động, chọn giải pháp configuration/mapping phù hợp hoặc dùng một địa chỉ logic cố định được quản lý đúng.

### 11.3. Version XSD và version logical address

Khi nâng `urn:example:orders:v1` lên v2:

- Root QName và JAXB schema có thể thay đổi.
- WS-Addressing Action URI có thể thay đổi theo contract.
- `@Address` cũng có thể trỏ tới đường dẫn logical v2 nếu thiết kế yêu cầu.
- Gateway/WSDL public URL có thể thay đổi hoặc được giữ nguyên với rule routing rõ ràng.

Không thay đồng thời mọi URI chỉ vì chúng có chuỗi `v1`: mỗi URI có vai trò khác nhau. Thay đổi bất kỳ một trong những giá trị thuộc hợp đồng đều cần regression test với client hiện tại.

## 12. `ReplyTo` và `FaultTo`: rủi ro khi server gọi ngược ra ngoài

Đối với `wsa:ReplyTo` hoặc `wsa:FaultTo` **không anonymous**, server có thể phải mở kết nối riêng để gửi response hoặc SOAP Fault tới endpoint do client khai báo:

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant S as Spring-WS Server
    participant R as Reply Endpoint
    C->>S: SOAP request (To, Action, ReplyTo=R)
    Note over S: @Address kiểm tra To khi action mapping chọn
    S-->>C: HTTP acknowledgment theo binding
    S->>R: Out-of-band SOAP response
~~~

Đây là sơ đồ **minh họa mô hình out-of-band**, không phải cam kết mọi Spring-WS application tự động gửi callback. Cần cấu hình `messageSenders` trên addressing endpoint mapping, transport và policy bảo mật phù hợp; không có sender/hợp đồng phù hợp thì phản hồi ngoài băng có thể không gửi được.

### 12.1. SSRF và phản hồi đến địa chỉ do đối tác cung cấp

Một attacker có thể đặt:

~~~xml
<wsa:FaultTo>
    <wsa:Address>
        http://127.0.0.1:8080/internal-admin
    </wsa:Address>
</wsa:FaultTo>
~~~

Nếu server mở kết nối ra địa chỉ này mà không kiểm soát, có nguy cơ **Server-Side Request Forgery (SSRF)**. `@Address` đúng ở inbound request **không làm `FaultTo` an toàn**.

Phòng vệ cần có:

- Chỉ hỗ trợ out-of-band replies khi thật sự được hợp đồng yêu cầu.
- Áp dụng **destination policy/allowlist** cho các host/URI callback được phép, kết hợp kiểm tra DNS/IP/port và scheme.
- Chặn địa chỉ loopback, link-local, mạng nội bộ nhạy cảm và metadata endpoints, trừ trường hợp được thiết kế rõ, bảo vệ chặt.
- Hạn chế redirects và kiểm tra lại đích sau DNS resolution khi thiết kế transport.
- Bảo đảm **xác thực người gửi request trước khi thực hiện outbound callback/fault**.
- Giới hạn timeout, kích thước message, concurrency và số lần retry callback.
- Không đưa credential hoặc token của server vào endpoint do client cung cấp nếu policy không cho phép.

Các phiên bản Spring-WS mới có cơ chế `DestinationPolicy` trên message sender dùng out-of-band replies. **Hành vi mặc định và API cấu hình cần được kiểm tra theo phiên bản đang triển khai**; không mặc định một message sender bất kỳ đã an toàn trước URI do đối tác điều khiển.

### 12.2. WS-Security, SOAP Fault và callback order

Nếu request chưa xác thực nhưng server đã gửi Fault tới địa chỉ `FaultTo` do client cung cấp, hệ thống có thể bị lợi dụng để phát request outbound. Do đó **thứ tự security và addressing interceptors quan trọng**. Hãy kiểm tra lớp WS-Security phù hợp phiên bản có chạy trước cơ chế out-of-band dispatch hay không và viết test âm tính.

Một WS-Security interceptor có thể kiểm tra token/chữ ký/timestamp, nhưng **điều đó không thay thế allowlist callback destination**. Ngay cả caller được xác thực vẫn có thể gửi URI callback không được phép.

## 13. SOAP Fault khi địa chỉ không khớp

Khi `wsa:Action` đúng nhưng `wsa:To` khác `@Address`, hãy phân biệt:

1. **Mapping không chọn endpoint** do điều kiện destination không khớp.
2. **WS-Addressing processor báo lỗi protocol** do header thiếu/sai, tùy version/profile.
3. **Một mapping khác được chọn** (nếu cấu hình cho phép).
4. **Lỗi HTTP hoặc transport sớm hơn** (chưa đến addressing mapping).

Không thể khẳng định mọi trường hợp sai To đều trả cùng một Fault code như `wsa:DestinationUnreachable`. Phản hồi cụ thể phụ thuộc Spring-WS version, mapping chain, SOAP version và Fault resolver.

### 13.1. Phân loại lỗi trong quá trình chẩn đoán

| Triệu chứng | Nơi cần xem | Có thể liên quan `@Address`? |
| --- | --- | --- |
| HTTP 404 từ gateway | Host/path/route | Thường chưa đến WS-Addressing mapping |
| HTTP 415 | Content-Type hoặc SOAP binding | Không phải điều kiện To trực tiếp |
| SOAP `VersionMismatch` | SOAP Envelope namespace | Không phải To |
| Lỗi WS-Addressing header | MAP version/mustUnderstand/format | Có thể liên quan To/Action nhưng không chỉ `@Address` |
| “No endpoint mapping found” | Action, To, mapping order và endpoint scan | **Có** |
| SOAP Fault nghiệp vụ | Endpoint/Fault resolver | Có thể đã qua mapping thành công |
| Không gửi được callback | `ReplyTo/FaultTo`, message sender, destination policy | Không phải điều kiện inbound `@Address` |
| TLS handshake failure | Chứng chỉ/transport | Không phải To |

### 13.2. Fault Action và `RelatesTo`

Với request có `wsa:MessageID`, response hoặc Fault có thể dùng `wsa:RelatesTo` để chỉ ra message gốc. `@Action(fault="...")` giúp mô tả WS-Addressing Fault Action mà method cung cấp qua hạ tầng tương ứng.

Tuy nhiên, **Fault Action không phải SOAP Fault code**:

- SOAP Fault Code: `Client/Server` (SOAP 1.1) hoặc `Sender/Receiver` (SOAP 1.2), v.v.
- Fault Action: URI trong WS-Addressing Header.
- Fault detail: XML nghiệp vụ có QName/structure theo XSD/WSDL.

Không chỉ đổi `@Action.fault` rồi kỳ vọng `SoapFaultMappingExceptionResolver` tự tạo typed Fault detail. Ba phần phải được cấu hình/kiểm thử riêng.

### 13.3. Không tiết lộ topology qua Fault

Nếu To sai, Fault công khai không nên chép:

~~~text
Internal target is http://orders-db:8080/admin
~~~

hoặc stack trace, đường dẫn class Java và thông tin firewall. Trả mã lỗi theo contract và correlation ID, giữ cấu hình topology trong log nội bộ được bảo vệ.

## 14. Kiểm thử `@Address` bằng cùng một HTTP URL và hai giá trị `To`

Đây là bài kiểm tra có sức phân biệt cao nhất:

- **Giữ nguyên** HTTP URL, HTTP method, SOAP version, Action và Body.
- **Chỉ đổi** giá trị `wsa:To`.
- Quan sát endpoint mapping nào chọn method, có SOAP Fault hay không, và nghiệp vụ có chạy không.

### 14.1. Tệp `valid-to.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:o="urn:example:orders:v1">
    <env:Header>
        <wsa:To env:mustUnderstand="true">https://services.example.test/soap/orders/v1</wsa:To>
        <wsa:Action env:mustUnderstand="true">urn:example:orders:v1:GetOrder</wsa:Action>
        <wsa:MessageID>urn:uuid:127b08a6-34bb-4e3f-a9e8-9c7f6d2005b9</wsa:MessageID>
        <wsa:ReplyTo>
            <wsa:Address>http://www.w3.org/2005/08/addressing/anonymous</wsa:Address>
        </wsa:ReplyTo>
    </env:Header>
    <env:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

Với endpoint `@Action("urn:example:orders:v1:GetOrder")` và `@Address("https://services.example.test/soap/orders/v1")`, message có giá trị **Action và To phù hợp**. Nếu application context, servlet, security và SOAP version đã đúng, addressing mapping có cơ sở chọn method.

### 14.2. Tệp `wrong-to.xml`

Chỉ thay:

~~~xml
<wsa:To env:mustUnderstand="true">https://api.example.test/partner/orders</wsa:To>
~~~

Action và Body giữ nguyên. Với `AnnotationActionEndpointMapping`, To không khớp điều kiện `@Address`; nếu không có mapping fallback, request có thể không được chọn vào handler dự kiến.

**Không** khẳng định HTTP response luôn là 404 hay một SOAP Fault code cố định. Kết quả cần quan sát tại runtime; điều bắt buộc là method không bị gọi **thông qua addressing mapping không khớp**.

### 14.3. Gửi vào cùng SOAP servlet bằng `curl`

~~~bash
curl -i -X POST "http://localhost:8080/ws/orders" \
  -H 'Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1:GetOrder"' \
  --data-binary @valid-to.xml
~~~

~~~bash
curl -i -X POST "http://localhost:8080/ws/orders" \
  -H 'Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1:GetOrder"' \
  --data-binary @wrong-to.xml
~~~

Đây là lệnh **hướng dẫn thực hành**, không phải kết quả test đã thực thi. Nó giả định server lắng nghe `localhost:8080`, có servlet path `/ws/*` và `SoapMessageFactory` hỗ trợ SOAP 1.2. Nếu server chỉ hỗ trợ SOAP 1.1, đổi Envelope, Content-Type và SOAPAction theo binding thật trước khi thử. Trên Windows PowerShell có thể dùng `curl.exe` nếu `curl` bị ánh xạ thành lệnh khác.

Tại sao HTTP local và To public logic vẫn có thể dùng trong test? Vì `To` là **địa chỉ trong SOAP Header**, còn HTTP URL đưa request tới server thử nghiệm. Tuy nhiên server vẫn có thể triển khai kiểm tra bổ sung ràng buộc transport URL với To; khi đó cần đưa vào expected behavior của bài kiểm thử.

### 14.4. Ma trận routing theo từng trường

| HTTP URL | `wsa:Action` | `wsa:To` | Payload QName | Kỳ vọng khi chỉ dùng Action+Address mapping |
| --- | --- | --- | --- | --- |
| Đúng servlet | Đúng | Đúng | Đúng | Chọn endpoint, sau đó xử lý/validate payload |
| Đúng servlet | Đúng | Sai | Đúng | Không chọn method này qua addressing mapping |
| Đúng servlet | Sai | Đúng | Đúng | Không chọn method này qua addressing mapping |
| Đúng servlet | Đúng | Thiếu | Đúng | Không được giả định khớp; kiểm tra protocol/mapping |
| Đúng servlet | Thiếu | Đúng | Đúng | Không đủ Action để map method theo `@Action` |
| Sai servlet | Đúng | Đúng | Đúng | Thường thất bại tại HTTP/servlet, trước addressing mapping |
| Đúng servlet | Đúng | Đúng | Sai | Có thể chọn method theo Action rồi payload validation/JAXB thất bại |
| Đúng servlet | Đúng | Đúng | Đúng nhưng sai child field | Endpoint mapping có thể thành công; XSD validation phải chặn cấu trúc sai |
| Đúng servlet | Đúng | Đúng | Đúng, WS-Security sai | Security policy phải từ chối độc lập với routing |

Kỳ vọng chỉ áp dụng **khi không có mapping strategy khác can thiệp trước** và không có cấu hình fallback khác. Hãy thêm ma trận riêng cho profile WS-Addressing/WS-Security và SOAP version của đối tác.

## 15. Kiểm thử Spring-WS ở cấp application context

`MockWebServiceClient` có thể kiểm thử đường endpoint mapping/interceptor trong Spring context mà không khởi động HTTP listener. Đối với `@Address`, test phải gửi **SOAP Header thực sự có wsa:To/wsa:Action**, không chỉ `withPayload(...)`.

Một test kế hoạch:

~~~text
Given:
  - Context có @EnableWs, @Endpoint, @Address và @Action.
  - Không có mapping thứ hai chọn GetOrderRequest trước.

When:
  - Gửi SOAP Envelope với To đúng + Action đúng.
Then:
  - Handler GetOrder được gọi đúng một lần.

When:
  - Gửi Envelope có To sai, giữ Action và Body.
Then:
  - Handler GetOrder không được gọi qua addressing mapping.

When:
  - Gửi To đúng + Action sai.
Then:
  - Handler GetOrder không được chọn qua Action mapping.
~~~

Để làm được vậy, có thể dùng `MockWebServiceClient` cùng `RequestCreator` tùy chỉnh có khả năng tạo SOAP message với Header hoặc dùng HTTP integration test gửi Envelope hoàn chỉnh. **Một test chỉ kiểm tra bean `OrderAddressingEndpoint` tồn tại không chứng minh `@Address` đã được áp dụng.**

### 15.1. Client-side mock không tương đương server-side mock

- `MockWebServiceClient`: kiểm thử endpoint, mapping, interceptor ở phía **server**.
- `MockWebServiceServer`: kiểm thử request được `WebServiceTemplate` tạo ở phía **client** và phản hồi được mock.

Với `ActionCallback`, phía client cần test rằng message gửi đi có:

~~~text
WS-Addressing namespace = 2005/08
To     = https://services.example.test/soap/orders/v1
Action = urn:example:orders:v1:GetOrder
Body   = {urn:example:orders:v1}GetOrderRequest
~~~

Khi chỉ gọi `new ActionCallback(action)`, test phải kiểm tra To mặc định **bằng URI transport**; sau đó thay bằng constructor có To rõ ràng để xác nhận khác biệt.

### 15.2. Kiểm thử qua HTTP(S) thực

Mock thường không bao phủ:

- Public host/path và proxy rewrite.
- TLS/mTLS, truststore, hostname verification.
- HTTP status, content type và behavior của gateway.
- Kết nối outbound tới ReplyTo/FaultTo.
- Cơ chế giới hạn outbound destinations và chống SSRF.

Vì vậy cần **ít nhất một bài thử tích hợp qua endpoint public** trong staging khi làm việc với đối tác. Tải WSDL công khai, ghi lại `soap:address`, gửi request có Header theo policy và xác minh handler/response.

## 16. Bảo mật: xác minh `To` không đồng nghĩa cấp quyền

Một attacker có thể gửi:

~~~xml
<wsa:To>https://services.example.test/soap/orders/v1</wsa:To>
<wsa:Action>urn:example:orders:v1:CancelOrder</wsa:Action>
~~~

Khi các giá trị này đúng, `@Address`/`@Action` giúp chọn operation nhưng **không xác nhận attacker là ai**. Không được suy từ To rằng client thuộc tenant hợp lệ hoặc có quyền hủy đơn.

Các lớp bảo vệ nên có:

1. **Authentication**: kiểm tra HTTP credentials, mTLS hoặc WS-Security identity phù hợp.
2. **Message integrity**: nếu policy yêu cầu, xác minh chữ ký trên các Header/Body có ảnh hưởng tới routing và nghiệp vụ.
3. **Authorization**: kiểm tra danh tính được phép gọi operation và truy cập orderId cụ thể.
4. **XSD validation**: kiểm tra XML Body đúng contract, không thay authentication.
5. **Replay/idempotency**: kiểm tra MessageID/token timestamp và khóa giao dịch để tránh xử lý trùng.
6. **Transport policy**: kiểm tra URL/host/path, certificate và outbound callback destination.

**Một `To` nằm trong SOAP Header chưa được ký là dữ liệu có thể bị giả mạo.** Ngay cả khi To được ký hợp lệ, ứng dụng vẫn phải kiểm tra **quyền** của danh tính đã ký đối với operation và tài nguyên.

### 16.1. Phân quyền theo tenant

Giả sử tenant A và B cùng gửi request tới một HTTP endpoint nhưng đặt To khác:

~~~text
Tenant A To = urn:example:orders:tenant:A
Tenant B To = urn:example:orders:tenant:B
~~~

`@Address` có thể mô tả một địa chỉ logic, nhưng **không thể thay thế phép đối chiếu tenant ID với authenticated principal**. Nếu tenant A biết URI của tenant B, việc tự viết To của B không được cấp quyền truy cập dữ liệu B.

Nếu dùng custom tenant routing dựa trên WS-Addressing, cần kiểm tra:

- Principal thực sự là ai, đến từ certificate/token nào?
- Principal được phép dùng To/Action nào?
- Body có tham chiếu order/tenant đúng quyền không?
- Header To có được bảo vệ khỏi sửa đổi theo policy không?
- Khi không có mapping hoặc không khớp, có lộ thông tin tenant khác không?

### 16.2. XXE, XML Security và xử lý header

WS-Addressing là một phần SOAP Header; framework vẫn phải parse XML. Việc dùng `@Address` không bảo vệ hệ thống khỏi:

- XML External Entity/DTD.
- Payload quá lớn hoặc cấu trúc XML cực sâu.
- Lỗi schema validation.
- SOAP Header `mustUnderstand` không được xử lý.
- SOAP version hoặc namespace addressing không phù hợp.

Hãy harden parser/message factory, cấu hình giới hạn tài nguyên và kiểm thử input độc hại **trước** khi dựa vào endpoint mapping để xử lý.

## 17. Chẩn đoán tình huống “To đúng mà vẫn không map”

Đặt câu hỏi theo thứ tự từ ngoài vào trong:

1. **HTTP:** request có đến đúng SOAP servlet hay bị gateway/Servlet container trả 404?
2. **SOAP:** Envelope là SOAP 1.1 hay 1.2, Content-Type tương thích không?
3. **WS-Addressing version:** namespace `wsa` có thuộc phiên bản server hỗ trợ?
4. **Action:** giá trị thực tế có khớp `@Action.value` trên method?
5. **To:** destination có khớp `@Address.value` trên class?
6. **Mapping order:** `@PayloadRoot` hoặc `@SoapAction` có chọn handler trước không?
7. **Component scan:** `@Endpoint`/`@EnableWs` có nằm trong đúng Spring context?
8. **Security:** SOAP Header có được xác minh và có interceptor chặn trước khi gọi method?
9. **Payload:** QName và dữ liệu có hợp XSD/JAXB không?
10. **Response:** lỗi xảy ra khi xử lý nghiệp vụ, tạo Fault hay gửi ReplyTo/FaultTo?

### 17.1. Những thông tin nên ghi log

Trong môi trường cho phép observability, ghi:

~~~text
correlationId
messageId (đã kiểm soát/giới hạn)
httpHostAndPath (được làm sạch)
soapVersion
addressingVersion
wsaTo (được lọc/giới hạn)
wsaAction
payloadQName
endpointMappingName
operationName
faultCode / errorCategory
elapsedMillis
~~~

Không log mặc định toàn bộ SOAP Header/Body: chúng có thể chứa UsernameToken, chữ ký, PII và dữ liệu thanh toán. Thông tin `wsa:ReplyTo` hoặc `FaultTo` do client gửi cũng phải được xử lý như dữ liệu không tin cậy trước khi ghi log hoặc đưa vào metrics label.

### 17.2. Một phép thử có tính quyết định

Nếu cùng HTTP URL và cùng SOAP Body nhưng **đổi duy nhất To** khiến handler chạy hoặc không chạy, và đã loại trừ các mapping khác, đó là bằng chứng tốt rằng điều kiện `@Address` đang tham gia routing.

Nếu cả To đúng lẫn To sai đều thành công, **không vội xóa @Address**. Hãy kiểm tra thứ tự `EndpointMapping` và khả năng `@PayloadRoot` được chọn trước, hoặc có endpoint fallback.

## 18. Bài tập tình huống: gateway đổi host sau triển khai

Hệ thống ban đầu chạy:

~~~text
Public URL:
  https://service.example.test/soap/orders

@Address:
  https://service.example.test/soap/orders

Client:
  ActionCallback("urn:example:orders:v1:GetOrder")
~~~

Sau khi triển khai gateway mới:

~~~text
New public URL:
  https://api.example.test/partners/orders

New upstream:
  http://orders:8080/ws/orders

@Address trên server:
  vẫn là https://service.example.test/soap/orders
~~~

Client cập nhật HTTP URI sang `https://api.example.test/partners/orders` nhưng không thay callback. Server bắt đầu báo không tìm thấy endpoint cho một số request.

**Câu hỏi:**

1. Client `ActionCallback(action)` mặc định lấy To từ đâu?
2. `@Address` đang so sánh với URI upstream nội bộ hay HTTP public URL mới?
3. Có bắt buộc đổi `@Address` thành URL gateway mới không?
4. Nếu muốn giữ To logic cũ, client phải làm gì?
5. Vì sao request không có `wsa:Action` có thể không được chọn dù Body hợp XSD?
6. Nếu endpoint có cả `@PayloadRoot` và `@Action`, tại sao một số request vẫn thành công khi To sai?
7. Có thể dùng `@Address` thay authorization của tenant không?

**Đáp án gợi ý:**

1. Mặc định lấy To từ URI kết nối khi dùng callback constructor chỉ có Action.
2. Điều kiện `@Address` kiểm tra destination trong WS-Addressing message, thường từ `wsa:To`, không trực tiếp kiểm tra URL upstream.
3. **Không bắt buộc.** Có thể giữ một địa chỉ logic ổn định nếu contract/policy được thống nhất.
4. Dùng `ActionCallback(action, Addressing10, explicitTo)` với To đã được công bố; vẫn kết nối tới HTTP public URL mới.
5. `AnnotationActionEndpointMapping` cần `Action` để map method, nếu không có mapping khác thì root QName một mình không chọn `@Action`.
6. `PayloadRootAnnotationMethodEndpointMapping` có thể chọn handler trước, do thứ tự mapping mặc định.
7. **Không.** To có thể bị giả mạo nếu không được xác thực/tin cậy; vẫn phải authn/authz và bảo vệ signed parts.

### 18.1. Bài thực hành

Tạo endpoint `@Endpoint`/`@Address`/`@Action` cùng XSD `GetOrderRequest`. Viết hai client calls tới cùng một HTTP URI:

- Callback 1 dùng constructor chỉ nhận `Action`.
- Callback 2 dùng constructor với `Action`, `Addressing10` và `To` tường minh.

Trước tiên đặt `@Address` trùng HTTP URI, sau đó đổi thành logical URI khác và ghi nhận:

1. `wsa:To` mà client gửi thực tế.
2. Mapping nào đã chọn handler.
3. SOAP Fault/HTTP status khi To không khớp.
4. Sự khác biệt khi thêm `@PayloadRoot` vào method.
5. XML Body có đúng XSD và SOAP version không.
6. Kết quả khi client gửi URI To khác một dấu `/`.

**Tiêu chí đạt:** giải thích được vì sao HTTP URL đúng không đồng nghĩa To đúng, biết chọn client callback để sửa đúng tầng và không coi `@Address` là cơ chế phân quyền.

## 19. Checklist đưa WS-Addressing `@Address` vào production

1. **Contract:** xác định địa chỉ To logic và Action URI được công bố chính thức.
2. **WSDL/XSD:** kiểm tra transport `soap:address` và QName payload; không trộn ba ý nghĩa URI.
3. **Server:** `@Address` đặt trên class, `@Action` đặt trên method, `@EnableWs` được nạp đúng context.
4. **EndpointMappings:** kiểm tra `PayloadRoot`, `SoapAction`, `AnnotationAction` order; không để mapping khác vô tình bypass điều kiện To.
5. **Client:** dùng `ActionCallback` đúng AddressingVersion và explicit To khi public transport URI khác logical destination.
6. **WS-Addressing version:** kiểm tra namespace 2005/08 hoặc 2004/08 đúng hợp đồng.
7. **SOAP version:** SOAP Envelope, Content-Type và action binding đồng bộ.
8. **Security:** xác minh signed To/Action theo policy, authentication và authorization từng operation.
9. **Outbound callbacks:** giới hạn ReplyTo/FaultTo bằng destination policy, không mở SSRF.
10. **Fault:** phân biệt WS-Addressing protocol lỗi, endpoint mapping lỗi và nghiệp vụ lỗi; kiểm tra Fault Action/RelatesTo.
11. **Gateway:** kiểm tra host/path rewrite và WSDL public được tải qua đúng địa chỉ của đối tác.
12. **Multi-tenancy:** không dùng To như identity; không giả định Action trùng được dispatch theo To tự động.
13. **Logging:** correlation ID và MAP metadata được làm sạch; không log token hoặc SOAP Body nhạy cảm.
14. **Tests:** thực hiện ca To đúng/sai, Action đúng/sai, mapping khác, SOAP versions và WS-Security.
15. **Interoperability:** thử với client implementation thực tế của đối tác, không chỉ unit tests Java.

## 20. Tóm tắt

- **`@Address`** thuộc package `org.springframework.ws.soap.addressing.server.annotation`, đặt trên **lớp endpoint**, để ràng buộc **destination (`wsa:To`)** khi `AnnotationActionEndpointMapping` xử lý.
- **`@Action`** đặt trên **method**, chọn operation theo WS-Addressing Action; có thể mô tả thêm Action cho response/fault.
- **`@Address` không tạo HTTP route, không sửa `soap:address` WSDL và không so sánh `ReplyTo`/`FaultTo`.**
- `ActionCallback` phía client mặc định có thể lấy `To` từ URI kết nối; khi transport URL qua gateway khác địa chỉ logic của `@Address`, hãy **khai báo To tường minh** và kiểm thử Header thực tế.
- **Mapping precedence rất quan trọng**: khi `@PayloadRoot` hoặc `@SoapAction` chọn handler trước, điều kiện `@Address` của WS-Addressing mapping có thể không được áp dụng.
- **Không dùng `@Address` làm authorization**: To chỉ là dữ liệu SOAP Header, phải có authentication, signature/integrity và quyền nghiệp vụ.
- **Không đồng nhất To với ReplyTo/FaultTo**: callback bất đồng bộ cần message sender, policy đích an toàn và kiểm soát SSRF.
- **SOAP 1.1/1.2, WS-Addressing versions, XSD/WSDL, JAXB, SOAP Fault và WS-Security** phải được cấu hình/kiểm thử phù hợp nhau.
- Khi chẩn đoán, giữ nguyên HTTP URL và Body, chỉ đổi `wsa:To` là cách hiệu quả để chứng minh điều kiện destination đang được áp dụng.

## 21. Tài liệu tham khảo kỹ thuật

- [Spring Web Services Reference — WS-Addressing và AnnotationActionEndpointMapping](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): cách Action/To tham gia endpoint mapping, xử lý phản hồi ngoài băng và kiểm thử.
- [Javadoc `@Address`](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/soap/addressing/server/annotation/Address.html): annotation đặt trên class và so sánh với incoming destination.
- [Javadoc `@Action`](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/soap/addressing/server/annotation/Action.html): Action cho request, output và fault.
- [Javadoc `AnnotationActionEndpointMapping`](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/soap/addressing/server/AnnotationActionEndpointMapping.html): mapping theo Action và ràng buộc Address.
- [Javadoc `ActionCallback`](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/soap/addressing/client/ActionCallback.html): constructor Action/AddressingVersion/To, ReplyTo, FaultTo và MessageID.
- [Javadoc `WsConfigurationSupport`](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/config/annotation/WsConfigurationSupport.html): các EndpointMapping mặc định trong Java configuration và thứ tự của chúng.

Các liên kết trên là tài liệu tham khảo API/thiết kế; **đối chiếu phiên bản Spring-WS/Spring Boot cụ thể** của dự án khi triển khai, vì khả năng cấu hình, bảo vệ callback và behavior của message sender có thể thay đổi giữa các thế hệ.



