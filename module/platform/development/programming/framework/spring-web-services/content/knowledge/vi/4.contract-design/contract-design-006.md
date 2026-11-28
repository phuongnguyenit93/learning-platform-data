# Đặt tên namespace, phần tử và thao tác có tính ổn định

## 1. Vì sao tên trong hợp đồng SOAP là quyết định kiến trúc?

Trong Spring Web Services (Spring-WS), một dịch vụ SOAP không được nhận diện chỉ bằng tên method Java. Hệ thống bên ngoài đọc **WSDL/XSD**, gửi XML chứa những **tên có namespace (QName)**, rồi chờ response hoặc SOAP Fault đúng cấu trúc hợp đồng. Nếu đổi tên một phần tử, thay URI namespace hoặc đổi tên thao tác WSDL, client đã sinh mã từ hợp đồng trước đó có thể ngừng hoạt động, ngay cả khi nghiệp vụ phía server không đổi.

Ví dụ một đối tác đang gửi:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:types:v1">
    <ord:orderId>ORD-2026-1042</ord:orderId>
</ord:GetOrderRequest>
~~~

Nếu phía server tự đổi `GetOrderRequest` thành `FindOrderRequest` hoặc đổi namespace thành `urn:example:orders:types:v2`, hai XML không còn cùng QName. Với endpoint Spring-WS định tuyến bằng `@PayloadRoot`, request cũ có thể không còn khớp endpoint. Với client JAXB, metadata sinh ra từ XSD cũng có thể không chấp nhận payload mới.

Vì vậy, **tên trong hợp đồng công khai là một phần của giao diện tích hợp**, cần được thiết kế, quản trị phiên bản và kiểm thử tương thích như một API.

Bài học này thuộc chương **Thiết kế hợp đồng** của module **SPRING_WEB_SERVICES**. Trọng tâm là thiết kế SOAP **contract-first**: chọn namespace, đặt tên element/type/operation trong XSD/WSDL, kết nối với JAXB và endpoint Spring-WS, và duy trì tính ổn định khi hệ thống doanh nghiệp phát triển.

Sau bài học, bạn có thể:

- Phân biệt tên prefix, local name, QName, `targetNamespace`, tên operation và `SOAPAction`.
- Đặt tên nhất quán cho request, response, kiểu XSD, WSDL `message`, `portType`, `binding` và `service`.
- Thiết kế namespace có chủ sở hữu, có quy tắc versioning và độc lập với địa chỉ triển khai.
- Phân tích thay đổi nào sẽ ảnh hưởng đến SOAP client/JAXB, định tuyến endpoint hoặc validation.
- Đề xuất quy trình thay đổi hợp đồng có kiểm thử tương thích với các đối tác hiện có.

## 2. Nền tảng: QName khác tên chuỗi thông thường

### 2.1. QName gồm namespace URI và local name

QName (qualified name) có thể hiểu là cặp:

~~~text
QName = {namespace URI}localName
~~~

Ví dụ:

~~~text
{urn:example:orders:types:v1}GetOrderRequest
{urn:example:payments:types:v1}GetOrderRequest
~~~

Hai QName này **khác nhau**, dù cùng có local name `GetOrderRequest`.

Trong XML, prefix chỉ là bí danh giúp viết ngắn:

~~~xml
<a:GetOrderRequest xmlns:a="urn:example:orders:types:v1"/>
<b:GetOrderRequest xmlns:b="urn:example:orders:types:v1"/>
~~~

Hai phần tử trên có **cùng QName** vì prefix `a` và `b` cùng trỏ về URI namespace. Đổi prefix không làm đổi hợp đồng; đổi namespace URI hoặc local name thì có.

Một ví dụ với default namespace cũng có cùng ý nghĩa:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:types:v1"/>
~~~

Ngược lại, hai namespace URI chỉ khác dấu `/`, chữ hoa hoặc ký tự cuối vẫn được coi là khác nhau:

~~~text
urn:example:orders:types:v1
urn:example:orders:types:v1/
URN:example:orders:types:v1
~~~

**Không được chuẩn hóa, thêm dấu gạch chéo hay đổi chữ hoa/thường URI namespace theo cảm tính.** Các hệ thống XML so khớp tên theo namespace name và local name, không dựa trên việc hai URI trông có vẻ cùng ý nghĩa.

### 2.2. Namespace URI không phải endpoint URL

Một namespace có thể là URI dạng HTTP:

~~~text
https://schemas.example.com/orders/v1
~~~

hoặc URN:

~~~text
urn:example:orders:types:v1
~~~

Với XML namespace, URI được dùng làm **định danh**; parser XML không cần truy cập mạng tới URI đó để xác định QName. Một tổ chức có thể chọn URI HTTP ổn định do mình kiểm soát và, nếu muốn, cung cấp tài liệu/schema ở địa chỉ đó. Đây là tiện ích quản trị, **không phải yêu cầu rằng mọi namespace URI phải tải được qua HTTP**.

Phân biệt ba loại địa chỉ:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Namespace URI | `urn:example:orders:types:v1` | Định danh tên element/type XML |
| Vị trí công bố WSDL | `https://docs.example.test/wsdl/orders-v1.wsdl` | Nơi đối tác tải hợp đồng |
| SOAP endpoint address | `https://api.example.test/soap/orders` | URL mà client gửi request HTTP |

Endpoint có thể chuyển từ máy chủ này sang máy chủ khác mà **không cần đổi namespace**. Ngược lại, một namespace được thay đổi là thay đổi nhận dạng XML dù URL SOAP endpoint không đổi.

### 2.3. Default namespace ảnh hưởng element, không tự áp dụng cho attribute

Ví dụ:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:types:v1" trackingId="T-123">
    <orderId>ORD-2026-1042</orderId>
</GetOrderRequest>
~~~

Ở đây:

- `GetOrderRequest` thuộc `urn:example:orders:types:v1`.
- `orderId` cũng thuộc namespace mặc định.
- Attribute `trackingId` **không có namespace** vì attribute không có prefix không chịu tác động của default namespace.

Điều này quan trọng khi bạn thay đổi `elementFormDefault`, `attributeFormDefault` hoặc annotation JAXB. Tên trong Java có thể giống nhau nhưng XML được phát ra lại không hợp XSD.

## 3. Những loại tên cần thiết kế trong SOAP contract

Một hệ thống contract-first có nhiều loại tên; chúng phục vụ những vai trò riêng:

| Thành phần | Ví dụ | Vai trò chính |
|---|---|---|
| XSD `targetNamespace` | `urn:example:orders:types:v1` | Không gian tên của element/type toàn cục |
| Global request element | `GetOrderRequest` | Root element trong SOAP Body của lời gọi |
| Global response element | `GetOrderResponse` | Root element trong SOAP Body phản hồi |
| XSD complex type | `GetOrderRequestType` | Định nghĩa cấu trúc dữ liệu, có thể tái sử dụng |
| Local child element | `orderId` | Field XML trong request/response |
| WSDL `operation` | `GetOrder` | Hành động logic của dịch vụ |
| WSDL `message` | `GetOrderInput`, `GetOrderOutput` | Khai báo các phần thông điệp |
| WSDL `portType` | `OrderPortType` | Giao diện gồm các operation |
| WSDL `binding` | `OrderSoap11Binding` | Quy tắc truyền, SOAP style và transport |
| WSDL `service` / `port` | `OrderService` / `OrderSoap11Port` | Điểm công bố dịch vụ và địa chỉ |
| HTTP `SOAPAction` | `urn:example:orders:actions:GetOrder` | Giá trị action của binding SOAP 1.1 qua HTTP |
| Spring `@PayloadRoot` | namespace + `GetOrderRequest` | Chọn endpoint theo QName payload |

Điểm cần nhớ: `GetOrder` (operation) và `GetOrderRequest` (root element) là **hai tên khác nhau** dù thường được thiết kế có liên hệ rõ ràng. HTTP `SOAPAction` cũng không tự động là tên operation, local name của root element hoặc URI namespace.

Trong kiến trúc ổn định, nhóm phát triển nên quản lý tất cả những tên này như **tài sản của hợp đồng** chứ không phụ thuộc vào tên package, class, method hoặc đường dẫn API nội bộ.

## 4. Đặt tên namespace bền vững

### 4.1. Gán namespace theo miền nghiệp vụ và chủ sở hữu

Ví dụ tổ chức vận hành ba miền nghiệp vụ:

~~~text
urn:example:orders:types:v1
urn:example:billing:types:v1
urn:example:customers:types:v1
~~~

Các miền được tách ra vì chúng có trách nhiệm sở hữu và chu kỳ thay đổi riêng. Điều này giúp hạn chế xung đột tên `id`, `status`, `Customer` giữa các nhóm.

Một cách khác là dùng miền DNS do tổ chức kiểm soát:

~~~text
https://schemas.example.com/orders/v1
https://schemas.example.com/billing/v1
~~~

Cả hai cách đều có thể hợp lý. Quan trọng là có **quy tắc được thống nhất**, duy trì được quyền kiểm soát tên và không vô tình tái sử dụng định danh cho những ý nghĩa khác nhau.

Không nên dùng namespace tạm bợ như:

~~~text
http://localhost:8080/orders
http://dev-machine/orders
http://com.mycompany.impl.service
~~~

Địa chỉ máy phát triển hoặc cấu trúc package Java là chi tiết triển khai dễ đổi. Khi được nhúng vào QName của XML công khai, chúng trở thành chi phí chuyển đổi cho tất cả client.

### 4.2. Chọn một chiến lược versioning minh bạch

Hai lựa chọn thường gặp:

**A. Namespace có phiên bản lớn**

~~~text
urn:example:orders:types:v1
urn:example:orders:types:v2
~~~

Cách này làm ranh giới giữa các phiên bản hợp đồng rõ ràng. Đối với thay đổi phá vỡ tương thích, v2 dùng QName riêng, cho phép server/client hỗ trợ v1 và v2 song song.

**B. Namespace ổn định không ghi số phiên bản**

~~~text
urn:example:orders:types
~~~

Một số tổ chức cố định namespace trong nhiều lần phát hành và dùng chính sách thay đổi tương thích, phiên bản tài liệu hoặc WSDL để quản trị. Điều đó giảm số lượng QName nhưng đòi hỏi kiểm soát cực chặt: không được thay cấu trúc theo cách làm các client cũ bị lỗi mà vẫn giữ danh tính cũ.

Không có chiến lược nào đúng cho mọi hệ thống. Với SOAP tích hợp nhiều đối tác và XSD validation chặt, **tách namespace v1/v2 khi có thay đổi phá vỡ tương thích** là một lựa chọn dễ kiểm soát. Nhưng cũng không nên tăng số phiên bản namespace cho từng thay đổi nhỏ nếu nó buộc toàn bộ client đổi QName không cần thiết.

### 4.3. Namespace của kiểu dữ liệu và namespace của dịch vụ

Có thể dùng cùng một namespace cho XSD và WSDL để đơn giản hóa. Nếu nhiều dịch vụ chia sẻ kiểu nghiệp vụ hoặc có nhóm sở hữu khác nhau, có thể tách rõ:

~~~text
urn:example:orders:types:v1
urn:example:orders:service:v1
~~~

Khi tách, cần khai báo prefix rõ ràng:

~~~xml
xmlns:ord="urn:example:orders:types:v1"
xmlns:tns="urn:example:orders:service:v1"
~~~

Trong ví dụ này:

- `ord:GetOrderRequest` là element thuộc XSD nghiệp vụ.
- `tns:OrderPortType` là thành phần WSDL của dịch vụ.

Cách tách chỉ có lợi nếu có nhu cầu thực sự, vì nó tăng số namespace mà client, WSDL, schema import và tài liệu phải quản lý. Nếu dùng một namespace, cần đảm bảo các nhóm không vô tình định nghĩa trùng QName.

### 4.4. Quy tắc đặt tên namespace cần được ghi lại

Một chính sách thực tế nên xác định:

- Ai có quyền tạo và thay đổi namespace cho từng miền.
- Cấu trúc URI chuẩn, ví dụ `urn:<organization>:<domain>:types:v<major>`.
- Khi nào phải tạo namespace phiên bản mới.
- Cách khai báo namespace cho type dùng chung và fault detail.
- Quy tắc deprecation, thời gian duy trì endpoint v1 và nơi lưu bản WSDL/XSD đã phát hành.

Tránh để mỗi nhóm tự tạo một namespace mới chỉ vì đổi deployment, repo hoặc tên package.

## 5. Đặt tên element và type XSD theo ý nghĩa ổn định

### 5.1. Request/response là thông điệp nghiệp vụ, không phải method Java

Một quy ước dễ đọc cho dịch vụ order:

| Chức năng | Operation | Root request element | Root response element |
|---|---|---|---|
| Tra cứu đơn | `GetOrder` | `GetOrderRequest` | `GetOrderResponse` |
| Gửi đơn mới | `SubmitOrder` | `SubmitOrderRequest` | `SubmitOrderResponse` |
| Hủy đơn | `CancelOrder` | `CancelOrderRequest` | `CancelOrderResponse` |
| Liệt kê đơn | `ListOrders` | `ListOrdersRequest` | `ListOrdersResponse` |

Quy ước động từ + đối tượng giúp dễ kết nối WSDL operation với payload, nhưng không phải luật bắt buộc của SOAP. Hợp đồng hiện hữu có thể dùng tên khác; khi đã công bố, **đừng đổi chỉ vì muốn chỉnh lại cách viết**.

Nên dùng từ ngữ nghiệp vụ nhất quán. Ví dụ, nếu “đơn hàng” trong toàn hệ thống là `Order`, tránh cùng lúc dùng `Purchase`, `Transaction` và `Order` cho cùng khái niệm mà không có khác biệt ý nghĩa.

### 5.2. Dùng global element cho thông điệp công khai

Ví dụ XSD cho tra cứu đơn hàng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:types:v1"
    targetNamespace="urn:example:orders:types:v1"
    elementFormDefault="qualified">

    <xs:element name="GetOrderRequest" type="ord:GetOrderRequestType"/>
    <xs:element name="GetOrderResponse" type="ord:GetOrderResponseType"/>

    <xs:complexType name="GetOrderRequestType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:complexType name="GetOrderResponseType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
            <xs:element name="status" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

Đặc điểm của thiết kế này:

1. `GetOrderRequest` và `GetOrderResponse` là **global elements**, thích hợp để WSDL tham chiếu bằng QName.
2. `GetOrderRequestType` và `GetOrderResponseType` là **complex types** định nghĩa hình dạng dữ liệu. Tên type không nhất thiết trùng tên element.
3. `elementFormDefault="qualified"` yêu cầu các local element như `orderId` và `status` thuộc target namespace của schema (trừ khi có khai báo `form` riêng).
4. Client biết chính xác QName của root request: `{urn:example:orders:types:v1}GetOrderRequest`.

Bài toán contract-first không kết thúc ở việc chọn những tên dễ đọc. Phải bảo đảm mỗi tên biểu diễn một khái niệm ổn định và có thể dùng trong vòng đời hợp đồng.

### 5.3. Đặt tên field theo dữ liệu, không theo cột database

Ví dụ trong payload:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:types:v1">
    <ord:orderId>ORD-2026-1042</ord:orderId>
</ord:GetOrderRequest>
~~~

`orderId` là ý nghĩa nghiệp vụ. Nếu hệ thống đổi cột từ `order_no` sang `order_external_ref`, tên element XML vẫn có thể giữ nguyên; mapper trong Java chịu trách nhiệm chuyển đổi.

Các nguyên tắc thực dụng:

- Dùng `PascalCase` cho global message element, complex type và operation nếu nhóm đã chọn quy ước đó; dùng `camelCase` cho field con.
- Tên rõ nghĩa hơn tên viết tắt như `id1`, `a`, `data`, `param`.
- Gắn hậu tố `Request`, `Response`, `Type` nhất quán khi có giá trị phân biệt; không dùng hậu tố chỉ để che đi một mô hình rối.
- Không đưa thông tin chi tiết của class Java (`OrderEntity`, `JpaOrder`, `GetOrderDtoImpl`) vào tên hợp đồng công khai.
- Khi đã phát hành, giữ nguyên chính tả, số ít/số nhiều và chữ hoa/thường của element.
- Tránh những tên gắn với quy trình tạm thời như `NewGetOrderRequest` hoặc `GetOrderV2Fix`; nếu thực sự có một thay đổi phá vỡ tương thích, hãy xử lý qua versioning có chủ đích.

### 5.4. Element QName và type QName không giống nhau

Với XSD trên, hai định danh khác nhau là:

~~~text
Element: {urn:example:orders:types:v1}GetOrderRequest
Type:    {urn:example:orders:types:v1}GetOrderRequestType
~~~

Element có thể được gán một type tái sử dụng; type không nhất thiết là phần tử xuất hiện trực tiếp trong SOAP Body. Khi viết WSDL document/literal, `wsdl:part` thường tham chiếu **global element** của request/response. Do đó, thiết kế phần tử gốc ổn định quan trọng không kém thiết kế các kiểu dữ liệu bên trong.

## 6. Đặt tên operation trong WSDL và nối với XSD

WSDL 1.1 định nghĩa một thao tác logic trong `wsdl:portType` và cách truyền thực tế trong `wsdl:binding`. Ví dụ hoàn chỉnh tối giản cho một operation SOAP 1.1:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:tns="urn:example:orders:service:v1"
    xmlns:ord="urn:example:orders:types:v1"
    targetNamespace="urn:example:orders:service:v1"
    name="OrderService">

    <wsdl:types>
        <xs:schema
            targetNamespace="urn:example:orders:types:v1"
            elementFormDefault="qualified">

            <xs:element name="GetOrderRequest">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="orderId" type="xs:string"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>

            <xs:element name="GetOrderResponse">
                <xs:complexType>
                    <xs:sequence>
                        <xs:element name="orderId" type="xs:string"/>
                        <xs:element name="status" type="xs:string"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
        </xs:schema>
    </wsdl:types>

    <wsdl:message name="GetOrderInput">
        <wsdl:part name="parameters" element="ord:GetOrderRequest"/>
    </wsdl:message>

    <wsdl:message name="GetOrderOutput">
        <wsdl:part name="parameters" element="ord:GetOrderResponse"/>
    </wsdl:message>

    <wsdl:portType name="OrderPortType">
        <wsdl:operation name="GetOrder">
            <wsdl:input message="tns:GetOrderInput"/>
            <wsdl:output message="tns:GetOrderOutput"/>
        </wsdl:operation>
    </wsdl:portType>

    <wsdl:binding name="OrderSoap11Binding" type="tns:OrderPortType">
        <soap:binding
            style="document"
            transport="http://schemas.xmlsoap.org/soap/http"/>
        <wsdl:operation name="GetOrder">
            <soap:operation
                soapAction="urn:example:orders:actions:GetOrder"/>
            <wsdl:input>
                <soap:body use="literal"/>
            </wsdl:input>
            <wsdl:output>
                <soap:body use="literal"/>
            </wsdl:output>
        </wsdl:operation>
    </wsdl:binding>

    <wsdl:service name="OrderService">
        <wsdl:port name="OrderSoap11Port"
                   binding="tns:OrderSoap11Binding">
            <soap:address
                location="https://api.example.test/soap/orders"/>
        </wsdl:port>
    </wsdl:service>
</wsdl:definitions>
~~~

Ví dụ nhúng schema trực tiếp trong `wsdl:types` để có thể đọc độc lập. Khi dự án lưu XSD ở một file riêng, WSDL thường khai báo `xs:import` với `namespace` và `schemaLocation` thích hợp; cần kiểm tra đường dẫn import có thể được công cụ sinh client phân giải ở môi trường phân phối hợp đồng.

### 6.1. Mối quan hệ giữa các tên trong ví dụ

~~~mermaid
flowchart TD
    A["WSDL service: OrderService"] --> B["WSDL port: OrderSoap11Port"]
    B --> C["Binding: OrderSoap11Binding"]
    C --> D["Port type: OrderPortType"]
    D --> E["Operation: GetOrder"]
    E --> F["Input message: GetOrderInput"]
    E --> G["Output message: GetOrderOutput"]
    F --> H["XSD element: ord:GetOrderRequest"]
    G --> I["XSD element: ord:GetOrderResponse"]
    C --> J["SOAPAction: urn:example:orders:actions:GetOrder"]
    B --> K["Endpoint URL: /soap/orders"]
~~~

Giải thích:

- `wsdl:operation name="GetOrder"` đặt tên thao tác trong giao diện WSDL.
- `wsdl:message` nối input/output với global element được mô tả trong XSD.
- `soap:operation soapAction="..."` khai báo action của binding SOAP 1.1; giá trị là URI do contract lựa chọn.
- `soap:address location="..."` là địa chỉ gửi request, có thể khác giữa môi trường kiểm thử và sản xuất.
- `wsdl:binding` mô tả kiểu truyền SOAP và có thể có biến thể SOAP 1.2 riêng nếu nhà cung cấp và client hỗ trợ.

**Không đồng nhất bốn giá trị** `GetOrder`, `GetOrderRequest`, `urn:example:orders:actions:GetOrder` và `https://api.example.test/soap/orders`. Chúng có liên hệ nhưng thuộc bốn lớp tên khác nhau.

### 6.2. SOAPAction có cần trùng tên operation?

Không. Với SOAP 1.1 HTTP binding, `SOAPAction` là giá trị action được công bố trong WSDL/binding, không phải quy tắc XML bắt buộc phải bằng operation name hoặc QName của payload. Một gateway hay phía server có thể dựa vào action để định tuyến, vì vậy đổi action có thể phá vỡ client dù request element giữ nguyên.

Ví dụ:

~~~http
POST /soap/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:actions:GetOrder"
~~~

Với SOAP 1.2 qua HTTP, thông tin hành động có thể xuất hiện trong tham số `action` của media type `application/soap+xml` theo binding tương ứng. Cần kiểm tra riêng binding SOAP 1.2; không bê nguyên quy tắc header `SOAPAction` của SOAP 1.1.

### 6.3. Đặt tên operation theo năng lực nghiệp vụ

Tên tốt nên trả lời câu hỏi “hành động này thực hiện điều gì?” mà không tiết lộ workflow nội bộ. Ví dụ:

| Tên dễ thay đổi/khó hiểu | Tên gợi ý nếu đang thiết kế mới | Lý do |
|---|---|---|
| `ExecuteOrder2` | `SubmitOrder` | Động từ phản ánh hành động nghiệp vụ |
| `ProcessSomething` | `CancelOrder` | Xác định đối tượng và ý định |
| `GetData` | `GetOrder` | Cho biết dữ liệu được truy xuất |
| `UpdateOrderDb` | `UpdateOrder` | Không gắn hợp đồng với thao tác cơ sở dữ liệu |
| `GetOrdersByStatusPageNew` | `ListOrders` với tiêu chí lọc rõ trong XSD | Giữ operation ổn định khi bổ sung bộ lọc phù hợp |

Đây là gợi ý **khi tạo contract mới**. Nếu đối tác đang gọi `ExecuteOrder2` trong sản xuất, tự động đổi sang `SubmitOrder` chỉ vì tên đẹp hơn có thể là một thay đổi phá vỡ tương thích. Cần có kế hoạch migration.

## 7. Tên trong Spring-WS và JAXB: code có thể đổi, contract phải được kiểm soát

### 7.1. Spring-WS định tuyến bằng QName payload

Giả sử request trong SOAP Body là:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:types:v1">
    <ord:orderId>ORD-2026-1042</ord:orderId>
</ord:GetOrderRequest>
~~~

Endpoint có thể khai báo:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {

    private static final String CONTRACT_NS =
        "urn:example:orders:types:v1";

    private final OrderApplicationService service;

    public OrderEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = CONTRACT_NS,
        localPart = "GetOrderRequest"
    )
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        return service.getOrder(request);
    }
}
~~~

Ví dụ này giả định JAXB binding đã tạo được kiểu root request/response tương ứng và ứng dụng có cơ chế marshalling thích hợp. **Cách sinh lớp từ XSD quyết định chữ ký Java thực tế.** Với một schema dùng global element tham chiếu đến named complex type, XJC có thể sinh `JAXBElement<GetOrderRequestType>` thông qua `ObjectFactory` thay vì lớp root tên `GetOrderRequest` có `@XmlRootElement`. Khi đó, tham số/giá trị trả về cần được điều chỉnh theo binding đã sinh.

Điểm chính: Spring-WS dùng **namespace + localPart của request payload** để chọn endpoint. Đổi tên Java method từ `getOrder` sang `loadOrder` thường không đổi hợp đồng nếu giữ nguyên QName, output và các quy tắc công bố. Nhưng đổi `@PayloadRoot(localPart="GetOrderRequest")` sang `localPart="FindOrderRequest"` sẽ ảnh hưởng định tuyến với client cũ.

### 7.2. JAXB package/class không phải XML namespace

Một namespace XML có thể được ánh xạ đến package Java thông qua cấu hình JAXB. Ví dụ lớp `package-info.java`:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:types:v1",
    elementFormDefault = jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package com.example.integration.orders.v1;
~~~

Package `com.example.integration.orders.v1` là lựa chọn bên Java. Hợp đồng bên XML vẫn dùng `urn:example:orders:types:v1`. Bạn có thể tổ chức lại package hoặc tầng service trong Java mà vẫn giữ QName XML nếu binding được cấu hình chính xác.

Ví dụ một global element dùng `@XmlRootElement`:

~~~java
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
    name = "GetOrderRequest",
    namespace = "urn:example:orders:types:v1"
)
@XmlType(
    name = "GetOrderRequestType",
    propOrder = {"orderId"}
)
public class GetOrderRequest {

    private String orderId;

    // Getter/setter hoặc access strategy JAXB tương ứng.
}
~~~

Mã này chỉ minh họa metadata liên quan đến QName; muốn marshal/unmarshal chuẩn còn cần cấu hình accessor, constructor và mapping của thuộc tính theo JAXB. Với dự án thực tế, ưu tiên sinh binding từ XSD rồi ánh xạ sang domain model riêng.

Lưu ý về phiên bản thư viện: Spring-WS hiện đại trong hệ Jakarta có thể dùng `jakarta.xml.bind.*`; các dự án cũ có thể vẫn dùng `javax.xml.bind.*`. Chọn đúng bộ dependency theo version framework đang triển khai, không trộn hai API.

### 7.3. Giữ tên SOAP ổn định dù domain Java thay đổi

Ví dụ domain chuyển từ `OrderEntity` sang `PurchaseOrder`, hoặc từ một service đơn thành nhiều microservice. Ranh giới chuyển đổi có thể giữ:

~~~text
SOAP request GetOrderRequest (QName ổn định)
                |
       Spring-WS @Endpoint
                |
     JAXB -> domain mapper
                |
          Application service
                |
       Domain model mới
                |
     domain -> JAXB mapper
                |
SOAP response GetOrderResponse (QName ổn định)
~~~

Kiến trúc này tránh để việc tái cấu trúc bên trong làm đối tác phải sinh lại client. Tuy nhiên, nếu **ngữ nghĩa nghiệp vụ** thay đổi đến mức contract cũ không còn diễn tả đúng, không nên cố giữ tên cũ và âm thầm đổi ý nghĩa. Khi đó cần định nghĩa phiên bản contract mới.

## 8. Những thay đổi tên nào phá vỡ tương thích?

Với SOAP, tương thích không chỉ có nghĩa là XML parse được. Một thay đổi có thể phá vỡ mã JAXB, validation theo XSD, WSDL-generated client, định tuyến theo QName hoặc ý nghĩa nghiệp vụ.

| Thay đổi | Rủi ro tương thích | Vì sao? |
|---|---|---|
| Đổi prefix `ord` thành `o`, giữ URI | Thường không phá vỡ về QName | QName không phụ thuộc prefix; ngoại lệ có thể nằm ở xử lý sai chuẩn hoặc chữ ký/chuỗi XML phụ thuộc cách biểu diễn |
| Đổi `targetNamespace` | **Phá vỡ QName** | Global element/type nhận định danh mới |
| Đổi local name `GetOrderRequest` | **Phá vỡ QName** | Endpoint và client tìm tên cũ |
| Đổi `orderId` thành `id` | **Phá vỡ cấu trúc XSD** | Client/server cũ chờ child element khác |
| Đổi tên `wsdl:operation` | Thường phá vỡ WSDL-based client | Stub/API và metadata operation thay đổi |
| Đổi `SOAPAction` của SOAP 1.1 | Có thể phá vỡ request | Gateway/server có thể kiểm tra action |
| Đổi namespace/version SOAP Envelope | Phá vỡ nếu client/server không hỗ trợ phiên bản mới | Đây là đổi giao thức/binding |
| Đổi `wsdl:service`, `port`, `binding` | Có thể phá vỡ client sinh từ WSDL | Tên và binding là một phần contract mà công cụ có thể dựa vào |
| Đổi địa chỉ `soap:address` | Ảnh hưởng kết nối/triển khai | Client dùng URL cũ có thể không tới server |
| Đổi package hay tên method Java nội bộ | Thường không ảnh hưởng XML nếu binding giữ nguyên | Tên nội bộ không quyết định QName công khai |
| Thêm request field `minOccurs="0"` ở cuối `xs:sequence` | **Tương thích có điều kiện** | Client cũ gửi request cũ thường được server mới chấp nhận; client mới gửi field mới có thể bị server cũ reject |
| Thêm response field mới | **Tương thích có điều kiện** | Client cũ có schema validator chặt có thể reject response chứa element lạ |
| Đổi kiểu field, ví dụ `xs:string` sang `xs:integer` | Có thể phá vỡ | Giá trị và generated binding/type validation thay đổi |
| Xóa một enum value hoặc đổi nghĩa value | Có thể phá vỡ cả nghiệp vụ lẫn validation | Client cũ có thể tiếp tục dùng giá trị đã hợp lệ trước đó |

Hai kết luận quan trọng:

1. **Cùng namespace không đảm bảo tương thích.** Nếu thay đổi cấu trúc hoặc ý nghĩa dữ liệu dưới cùng QName, client vẫn có thể lỗi.
2. **Thêm element optional không bảo đảm tương thích hai chiều.** Cần xét client cũ gọi server mới, client mới gọi server cũ, và chiều response từ server đến client.

### 8.1. Trường hợp bổ sung field optional

XSD v1:

~~~xml
<xs:complexType name="GetOrderRequestType">
    <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
    </xs:sequence>
</xs:complexType>
~~~

XSD sau khi bổ sung:

~~~xml
<xs:complexType name="GetOrderRequestType">
    <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="includeHistory"
                    type="xs:boolean"
                    minOccurs="0"/>
    </xs:sequence>
</xs:complexType>
~~~

Nếu server mới xử lý trường vắng mặt như `false`, request cũ có thể vẫn hợp lệ. Tuy nhiên:

- Client mới gửi `includeHistory` cho server cũ có thể bị từ chối khi server validate theo XSD cũ.
- Client cũ sẽ không biết field mới.
- Nếu cách xử lý trường mặc định làm kết quả khác trước, ngay cả request cũ cũng có thể bị ảnh hưởng nghiệp vụ.
- Nếu đổi thứ tự hoặc thêm vào `xs:sequence` không đúng vị trí, tác động tương thích có thể lớn hơn.

Bởi vậy, muốn công bố một thay đổi là compatible phải **kiểm thử cả các hướng giao tiếp thật**, thay vì chỉ nhìn thấy `minOccurs="0"`.

### 8.2. Đổi tên nhưng giữ nội dung tương đương vẫn là thay đổi contract

Giả sử nhóm muốn đổi `GetOrderRequest` thành `LookupOrderRequest` để chuẩn hóa thuật ngữ. Một SOAP client đã sinh ra có thể đang gửi:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:types:v1">
    <ord:orderId>ORD-2026-1042</ord:orderId>
</ord:GetOrderRequest>
~~~

Server mới chỉ đăng ký:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:types:v1",
    localPart = "LookupOrderRequest"
)
~~~

Request cũ không khớp. Cách migration an toàn hơn là tiếp tục hỗ trợ QName cũ trong thời gian chuyển đổi, hoặc công bố version mới và cấu hình đầu mối thích hợp cho đối tác.

Không được “âm thầm rename” vì hai tên diễn đạt cùng ý nghĩa đối với con người.

## 9. Một chiến lược tiến hóa contract theo phiên bản

Giả sử OrderService v1 đang phục vụ nhiều đối tác. Yêu cầu mới buộc dữ liệu tra cứu phải bao gồm `tenantId` bắt buộc và response thay đổi đáng kể. Đây có thể là thay đổi phá vỡ tương thích vì client cũ không gửi trường mới.

Một chiến lược:

~~~mermaid
flowchart TD
    A["Contract Order v1 đang dùng"] --> B{"Thay đổi có phá vỡ client hiện có?"}
    B -- "Không rõ" --> C["Chạy contract/interoperability test"]
    C --> B
    B -- "Không" --> D["Cân nhắc cập nhật cùng namespace<br/>theo chính sách tương thích"]
    B -- "Có" --> E["Định nghĩa contract v2"]
    E --> F["XSD namespace v2 + WSDL binding/port rõ ràng"]
    F --> G["Spring-WS endpoint/adapter hỗ trợ v2"]
    G --> H["Chạy song song v1 và v2 trong giai đoạn migration"]
    H --> I["Di chuyển đối tác và quản lý deprecation"]
~~~

Ví dụ định danh:

~~~text
v1: {urn:example:orders:types:v1}GetOrderRequest
v2: {urn:example:orders:types:v2}GetOrderRequest
~~~

Có thể giữ local name `GetOrderRequest` vì hành động nghiệp vụ về bản chất vẫn là “tra cứu đơn”; namespace khác phân biệt contract. Nếu ngữ nghĩa hành động thay đổi rõ rệt, có thể chọn operation mới phù hợp.

Dịch vụ có thể công bố hai WSDL hoặc hai binding/port và định tuyến qua các endpoint tương ứng. Trong Spring-WS, mỗi handler phải nhận QName đúng version. Không nên hy vọng một endpoint có namespace v2 tự nhận được payload v1; việc chuyển đổi cần được thiết kế tường minh.

### 9.1. Có cần đổi tên Java class theo version?

Không có một quy tắc bắt buộc, nhưng hai version XSD có cùng local type name nên được phân cách rõ trong Java binding, thường qua package khác nhau:

~~~text
com.example.integration.orders.v1.GetOrderRequestType
com.example.integration.orders.v2.GetOrderRequestType
~~~

Cách này tránh class collision và giúp migration có kiểm soát. Domain service bên trong có thể dùng chung model nghiệp vụ nếu adapter v1/v2 ánh xạ đúng semantics.

### 9.2. Những thứ nên bất biến trong một major contract

Sau khi công bố một phiên bản, cần đặc biệt thận trọng với:

- Namespace URI và QName của global elements/types được đối tác tham chiếu.
- Tên, input/output và thông điệp Fault của WSDL operation.
- Schema constraints có thể làm XML trước đây hợp lệ trở nên không hợp lệ.
- Giá trị SOAPAction/action mà bên gọi hoặc hạ tầng phụ thuộc.
- Quy ước về optional/nil, giá trị enum, tiền tệ, timezone và semantics.
- SOAP version và yêu cầu bảo mật liên quan Header/WS-Security.

Khả năng tương thích cần đánh giá từ góc nhìn **client tồn tại trong thực tế**, không chỉ dựa trên hướng “server hiện tại vẫn build được”.

## 10. Lỗi thiết kế thường gặp

### Lỗi 1: Namespace thay đổi theo môi trường

~~~text
DEV:  http://dev.example.test/orders
TEST: http://test.example.test/orders
PROD: http://api.example.test/orders
~~~

Nếu mỗi môi trường phát hành một QName khác nhau, client có thể phải sinh code riêng hoặc cấu hình rắc rối. Nên dùng namespace nghiệp vụ ổn định cho cùng một version contract và chỉ thay SOAP endpoint URL theo môi trường.

### Lỗi 2: Tên contract phụ thuộc refactor Java

~~~text
OrderControllerImplV2
OrderJpaEntity
GetOrderHandlerNew
~~~

Những tên này thường thuộc code nội bộ, không có lợi ích khi xuất hiện trong XSD/WSDL công khai. Khi refactor class/service, đối tác không nên chịu thay đổi QName.

### Lỗi 3: Đổi namespace nhưng không đồng bộ XSD và WSDL

Ví dụ XSD đổi target namespace sang `urn:example:orders:types:v2` nhưng WSDL vẫn viết:

~~~xml
<wsdl:part name="parameters" element="ord:GetOrderRequest"/>
~~~

với `ord` trỏ tới namespace v1. WSDL lúc đó có thể tham chiếu sai phần tử hoặc tạo hợp đồng không nhất quán. Cần cập nhật các QName được tham chiếu trong `wsdl:types`, `message`, `portType`, `binding` và kiểm tra XSD import phù hợp.

### Lỗi 4: Cho rằng operation name tự quyết định định tuyến Spring-WS

WSDL nói operation `GetOrder`, nhưng endpoint Spring-WS dùng:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:types:v1",
    localPart = "GetOrderRequest"
)
~~~

Nếu chỉ đổi WSDL operation thành `FindOrder`, runtime @PayloadRoot có thể vẫn nhận cùng QName XML, nhưng client sinh từ WSDL có thể thay method/API; metadata tích hợp không còn thống nhất. **Khả năng định tuyến server** và **tính ổn định hợp đồng WSDL** là hai phép kiểm tra riêng.

### Lỗi 5: Coi prefix XML là một phần version

~~~xml
<v1:GetOrderRequest xmlns:v1="urn:example:orders:types:v1"/>
<ord:GetOrderRequest xmlns:ord="urn:example:orders:types:v1"/>
~~~

Hai phần tử này cùng QName. Nếu hệ thống kiểm tra string `<v1:GetOrderRequest>` thay vì QName, đó là logic phụ thuộc cách viết XML, dễ gây lỗi interoperability.

### Lỗi 6: Tái sử dụng một tên cho ý nghĩa mới

Nếu `CancelOrder` trước đây nghĩa là hủy đơn chưa thanh toán, nhưng sau refactor được dùng cho cả yêu cầu hoàn tiền của đơn đã hoàn thành, bên gọi có thể hiểu sai tác động. Dù QName không đổi, **semantics đã thay đổi**. Cần xác định có thể bổ sung option an toàn hay nên tạo operation/use case mới.

## 11. Kiểm thử và quản trị tên hợp đồng

Đặt tên tốt chỉ có giá trị nếu được thực thi trong quy trình phát hành. Một bộ kiểm tra contract-first nên bao phủ những điểm sau.

### 11.1. So sánh bản XSD/WSDL trước và sau thay đổi

Trước khi phát hành, thu thập danh sách:

~~~text
XSD targetNamespace
Global element QNames
Global type QNames
WSDL targetNamespace
WSDL operation names
Input/output message references
Binding names, SOAP version
SOAPAction/action values
Service/port names
Endpoint location (ở từng môi trường)
~~~

So sánh với phiên bản đã công bố. **Xem mỗi khác biệt là một quyết định cần giải thích**, đặc biệt với QName, SOAPAction và operation name.

### 11.2. Kiểm thử QName đúng cả khi đổi prefix

Hai request sau phải được SOAP/XML stack hiểu cùng một element theo XSD:

~~~xml
<x:GetOrderRequest xmlns:x="urn:example:orders:types:v1">
    <x:orderId>ORD-2026-1042</x:orderId>
</x:GetOrderRequest>
~~~

~~~xml
<GetOrderRequest xmlns="urn:example:orders:types:v1">
    <orderId>ORD-2026-1042</orderId>
</GetOrderRequest>
~~~

Trường hợp kiểm thử này phát hiện phần code nào vô tình so sánh chuỗi prefix hay XPath không có namespace context.

Ngược lại, request thuộc `urn:example:orders:types:v2` phải được đối xử đúng với chính sách version v2. Nếu endpoint chỉ công bố v1, không nên giả định request v2 có thể được nhận mà không có cấu hình/adapter.

### 11.3. Dùng request/response mẫu để khóa hợp đồng

Lưu các SOAP message mẫu theo từng phiên bản như fixture kiểm thử; ví dụ SOAP 1.1:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:types:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2026-1042</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Các kiểm thử tích hợp cần xác nhận:

- Root payload thực sự có QName `{urn:example:orders:types:v1}GetOrderRequest`.
- SOAP version và `Content-Type` hợp binding.
- Operation/action được định tuyến đúng theo WSDL và cấu hình.
- Request/response hợp XSD, bao gồm order của child elements.
- SOAP Fault, chi tiết lỗi nghiệp vụ và policy bảo mật vẫn nhất quán.
- Client sinh từ WSDL đã phát hành vẫn gửi được request và đọc được response hợp lệ.

### 11.4. Kiểm thử interoperability thay vì chỉ test hai phía cùng Java

Nếu client và server đều dùng chung thư viện JAXB được cập nhật cùng lúc, một lỗi đổi QName có thể khó phát hiện vì cả hai phía đã cùng “chấp nhận” tên mới. Hãy giữ fixture của **phiên bản đã phát hành** và chạy ít nhất một client sinh từ WSDL cũ hoặc công cụ SOAP độc lập.

Nếu có WS-Security, cần kiểm tra thêm Header namespace, chữ ký XML, tham chiếu phần tử được ký và certificate trust. Thay namespace hoặc cấu trúc element có thể ảnh hưởng dữ liệu được ký, dù nghiệp vụ không đổi. Không sửa thủ công XML sau khi ký để “đổi tên” message.

## 12. Tình huống thực tế: hợp nhất hai hệ thống đơn hàng

Một doanh nghiệp có hệ thống bán hàng nội bộ A dùng `FindOrder` và đối tác B đang gọi `GetOrder` qua SOAP. Nhóm phát triển quyết định thay database, hợp nhất domain model và đổi service backend thành `PurchaseService`.

Yêu cầu là không làm đứt tích hợp với B.

**Thiết kế phù hợp:**

1. Giữ `urn:example:orders:types:v1` và các QName `GetOrderRequest`, `GetOrderResponse` nếu ngữ nghĩa hợp đồng B đang dùng không thay đổi.
2. Giữ WSDL operation `GetOrder` và `SOAPAction` đã công bố nếu binding vẫn cần giá trị đó.
3. Thay lớp ánh xạ từ JAXB binding sang domain mới; có thể đổi Java class, method hay service nội bộ.
4. Kiểm thử bằng request mẫu và WSDL client hiện có của B.
5. Nếu yêu cầu mới bắt buộc thay cấu trúc, công bố `urn:example:orders:types:v2` với kế hoạch hỗ trợ song song v1/v2.

**Thiết kế dễ gây lỗi:** Đổi tất cả tên SOAP theo tên `PurchaseService` vừa refactor, rồi yêu cầu đối tác B “generate lại client” trong khi không có thỏa thuận thay phiên bản. Đây là một thay đổi contract có tác động triển khai thật, không phải refactor vô hại.

## 13. Bài thực hành thiết kế

Cho yêu cầu: “Dịch vụ đối tác phải tra cứu trạng thái vận đơn theo mã vận đơn; trong tương lai có thể bổ sung lọc theo kênh giao hàng.”

Hãy đề xuất:

| Hạng mục | Gợi ý thiết kế |
|---|---|
| Namespace | `urn:example:shipping:types:v1` |
| Operation | `GetShipmentStatus` |
| Request element | `GetShipmentStatusRequest` |
| Response element | `GetShipmentStatusResponse` |
| Request fields | `shipmentId` bắt buộc; `channel` optional nếu được hỗ trợ ngay từ đầu |
| Response fields | `shipmentId`, `status`, `updatedAt` với kiểu và timezone được quy định rõ |
| WSDL portType | `ShippingPortType` |
| WSDL binding | `ShippingSoap11Binding` hoặc binding SOAP 1.2 được lựa chọn nhất quán |
| Test bắt buộc | QName, schema validation, client sinh từ WSDL, lỗi không tìm thấy vận đơn |

Nếu chưa biết `channel` sẽ hoạt động thế nào, không nên đưa vào contract như một trường tùy tiện chỉ để “phòng tương lai”. Hãy xác định rõ ý nghĩa và khả năng tương thích khi bổ sung sau. Nếu sau này thay đổi bắt buộc `shipmentId` thành một ID phức hợp hoàn toàn khác, cần đánh giá breaking change và chiến lược v2.

## 14. Checklist trước khi công bố WSDL/XSD

- [ ] Namespace có chủ sở hữu, không phụ thuộc máy chủ hoặc đường dẫn source code.
- [ ] `targetNamespace` của XSD/WSDL và các prefix được khai báo nhất quán.
- [ ] Mỗi global element/type có tên rõ nghĩa và QName không xung đột.
- [ ] Root request/response dùng tên ổn định, gắn với use case nghiệp vụ.
- [ ] `wsdl:operation`, `message`, `portType`, `binding`, `service`, `port` tuân thủ quy ước đặt tên thống nhất.
- [ ] `wsdl:part` tham chiếu đúng XSD element; SOAPAction/action và binding phù hợp SOAP version.
- [ ] Java/JAXB được sinh hoặc cấu hình theo contract, không để tên class nội bộ quyết định QName công khai.
- [ ] Thay đổi XSD/WSDL được so sánh với bản đã phát hành và phân loại tác động tương thích.
- [ ] Có test bằng XML/QName và client độc lập, bao gồm message mẫu của đối tác cũ.
- [ ] Có chính sách phát hành v2, hỗ trợ song song, deprecation và hướng dẫn migration khi bắt buộc đổi hợp đồng.

## 15. Ghi nhớ

- **QName = namespace URI + local name**. Prefix chỉ là ký hiệu trong tài liệu XML.
- **Namespace URI không phải SOAP endpoint URL**; không nên thay namespace chỉ vì đổi môi trường hoặc cách triển khai.
- **Element/type XSD, operation WSDL, SOAPAction và Java method** là những tên có mục đích khác nhau; không tự động đồng nghĩa.
- Trong Spring-WS, `@PayloadRoot` thường dựa vào **QName của phần tử payload trong SOAP Body**; tên method Java có thể thay đổi mà không ảnh hưởng hợp đồng nếu mapping và hành vi giữ nguyên.
- **Tên đã công bố là cam kết tương thích với đối tác.** Đổi namespace, root element, operation name hoặc ý nghĩa dữ liệu cần được đánh giá như thay đổi API.
- Khi có breaking change, dùng chiến lược versioning và kiểm thử interoperability; khi refactor nội bộ, giữ XML contract ổn định thông qua tầng JAXB/mapper.

**Câu hỏi tự kiểm tra:** Một nhóm đổi package Java, đổi tên method `getOrder()` thành `lookupOrder()`, chuyển endpoint URL sang máy chủ mới và đổi XSD namespace từ `urn:example:orders:types:v1` sang `urn:example:orders:types:v2`. Thay đổi nào bắt buộc phía client SOAP phải điều chỉnh, và thay đổi nào có thể giữ nguyên giao diện XML? Hãy giải thích dựa trên QName, WSDL binding và địa chỉ kết nối.

