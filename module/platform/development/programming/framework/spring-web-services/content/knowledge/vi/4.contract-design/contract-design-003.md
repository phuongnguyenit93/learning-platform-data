# Hợp đồng dữ liệu và hợp đồng dịch vụ bổ sung cho nhau

Khi tích hợp một dịch vụ SOAP giữa hai hệ thống doanh nghiệp, câu hỏi “**Dữ liệu phải có hình dạng nào?**” và “**Dịch vụ cho phép thực hiện thao tác nào, gửi và nhận dữ liệu ra sao?**” là hai câu hỏi liên quan nhưng không đồng nhất. Một hệ thống có thể tạo ra XML hoàn toàn hợp lệ nhưng vẫn không gọi được dịch vụ vì chọn sai operation, sai SOAP binding hoặc gửi đến sai địa chỉ. Ngược lại, một WSDL được công bố đầy đủ không bảo đảm mọi payload mà client tạo ra đều hợp lệ với XSD.

Trong module **SPRING_WEB_SERVICES** (Spring Web Services), cách tiếp cận **contract-first** đặt những hợp đồng này ở vị trí trung tâm. Chúng là nền tảng để sinh lớp **JAXB**, viết **SOAP endpoint** và **SOAP client**, xử lý **SOAP Fault**, cấu hình **interceptor**, triển khai **XML security / WS-Security** với chứng chỉ và kiểm thử khả năng tương thích giữa các nền tảng. Bài học này tập trung giải thích **hợp đồng dữ liệu (XSD)** và **hợp đồng dịch vụ (WSDL)** bổ sung nhau thế nào, qua một ví dụ nhất quán từ thiết kế đến vận hành.

## 1. Hai hợp đồng trả lời hai nhóm câu hỏi khác nhau

### Hợp đồng dữ liệu: XSD

**XML Schema Definition (XSD)** mô tả những tài liệu hoặc phần tử XML nào là hợp lệ:

- **Tên và namespace** của phần tử, thuộc tính.
- **Kiểu dữ liệu**: `xs:string`, `xs:decimal`, `xs:dateTime` hoặc các kiểu do mình định nghĩa.
- **Cấu trúc và thứ tự**: `xs:sequence`, `xs:choice`, phần tử lồng nhau, danh sách.
- **Ràng buộc xuất hiện**: `minOccurs`, `maxOccurs`, `nillable`.
- **Miền giá trị**: `xs:enumeration`, `xs:pattern`, `xs:minInclusive`…

XSD không trực tiếp nói dịch vụ có URL nào, có những operation nào, dùng SOAP version/binding nào, hoặc client cần gọi operation vào thời điểm nào.

### Hợp đồng dịch vụ: WSDL

**Web Services Description Language (WSDL)** mô tả giao diện mà một client cần để tương tác với dịch vụ. Với **WSDL 1.1** thường dùng trong tích hợp Spring-WS/SOAP, những thành phần chính là:

| Thành phần WSDL 1.1 | Câu hỏi nó trả lời |
| --- | --- |
| `types` | Các kiểu dữ liệu/phần tử cần dùng được mô tả hoặc tham chiếu ở đâu? |
| `message` | Mỗi request, response hoặc fault được cấu thành từ những phần nào? |
| `portType` | Dịch vụ cung cấp những operation và kiểu trao đổi thông điệp nào? |
| `binding` | Operation được truyền qua giao thức nào, theo cách đóng gói nào? |
| `service` / `port` | Binding được công bố ở địa chỉ cụ thể nào? |

WSDL có thể mang hoặc tham chiếu XSD trong `types`. **WSDL định nghĩa cách sử dụng dữ liệu trong dịch vụ; XSD định nghĩa dữ liệu đó hợp lệ ra sao.**

| Tình huống cần xác minh | Hợp đồng quyết định |
| --- | --- |
| `orderId` có được phép rỗng? | XSD, cùng quy tắc nghiệp vụ nếu chặt hơn |
| Response phải có `status` và đúng thứ tự không? | XSD |
| Có operation `GetOrder` không? | WSDL |
| Operation `GetOrder` sử dụng request/response nào? | WSDL tham chiếu các phần tử từ XSD |
| Gửi theo SOAP 1.1 document/literal hay SOAP 1.2? | Binding trong WSDL và triển khai tương ứng |
| Client kết nối vào URL nào? | WSDL `service/port` (có thể được cấu hình lại ở môi trường triển khai) |
| Người gọi có quyền xem đơn hàng không? | Quy tắc bảo mật/nghiệp vụ, không chỉ XSD hay WSDL cơ bản |

> **Phân biệt cấp độ:** XML instance là một thông điệp thực tế; XSD là hợp đồng **hình dạng của XML**; WSDL là hợp đồng **giao diện dịch vụ**. Mỗi cấp độ có kiểm thử riêng.

## 2. Quan hệ bổ sung trong một giao dịch SOAP

Hãy xét bài toán một đối tác muốn truy vấn trạng thái đơn hàng. Phía cung cấp dịch vụ hỗ trợ thao tác `GetOrder`, nhận `GetOrderRequest`, trả `GetOrderResponse`. Đối tác cần biết **cả dữ liệu hợp lệ lẫn cách gửi chúng**.

~~~mermaid
flowchart LR
    X["XSD<br/>Định nghĩa GetOrderRequest / GetOrderResponse"] -->|Được tham chiếu| W["WSDL<br/>operation GetOrder, message, binding, port"]
    X -->|Sinh / ánh xạ| J["JAXB classes<br/>Java request / response"]
    W -->|Mô tả cách gọi| C["SOAP client"]
    J --> C
    C -->|SOAP Envelope| E["Spring-WS endpoint"]
    E -->|Đọc và trả payload theo XSD| J
~~~

Trong luồng điển hình này:

1. Nhóm thiết kế thống nhất **XSD** cho payload.
2. **WSDL** tham chiếu các global elements từ XSD, gắn chúng với operation và binding.
3. Client dùng WSDL/XSD để sinh hoặc cấu hình mã gọi dịch vụ; server dùng XSD để sinh lớp JAXB tương thích.
4. Khi chạy, client gửi một **SOAP Envelope**. Spring-WS định tuyến dựa trên payload hoặc cấu hình endpoint mapping; JAXB chuyển payload sang đối tượng Java.
5. Hai phía kiểm thử XML thực sự trao đổi theo XSD, operation/binding/địa chỉ theo WSDL và ngữ nghĩa nghiệp vụ theo tài liệu đi kèm.

Lưu ý quan trọng: **WSDL không phải là SOAP message** được gửi ở mọi lần gọi. Nó là mô tả hợp đồng mà client thường đọc trước khi tích hợp hoặc dùng trong quá trình sinh mã. Tương tự, XSD không phải dữ liệu nghiệp vụ; nó là tập luật để thẩm định cấu trúc dữ liệu.

## 3. Ví dụ contract-first: bắt đầu từ hợp đồng dữ liệu

Ta sử dụng hai namespace cố ý tách biệt:

- Dữ liệu đơn hàng: `urn:example:orders:data:v1`.
- Giao diện dịch vụ: `urn:example:orders:service:v1`.

Việc tách namespace không phải bắt buộc, nhưng giúp phân biệt **tài liệu dữ liệu có thể dùng lại** với **giao diện dịch vụ cụ thể**. Trong ví dụ, tệp `orders.xsd` định nghĩa hai phần tử gốc được phép xuất hiện trong SOAP Body.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:data:v1"
           targetNamespace="urn:example:orders:data:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
            <xs:pattern value="[A-Z0-9-]+"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="ord:OrderIdType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="ord:OrderIdType"/>
                <xs:element name="status" type="ord:OrderStatusType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Ở đây, hợp đồng dữ liệu xác định:

- Root QName của request là **`{urn:example:orders:data:v1}GetOrderRequest`** và của response là **`{urn:example:orders:data:v1}GetOrderResponse`**.
- Mỗi request bắt buộc có **chính xác một** `orderId` vì `minOccurs` và `maxOccurs` mặc định của `xs:element` là 1.
- `orderId` có ít nhất một ký tự và chỉ nhận chữ hoa ASCII, chữ số hoặc dấu `-` theo pattern ví dụ.
- Response yêu cầu `orderId` **trước** `status` vì `xs:sequence`; `status` chỉ nhận một trong ba giá trị liệt kê.
- Do `elementFormDefault="qualified"`, các phần tử cục bộ `orderId` và `status` cũng thuộc namespace dữ liệu khi xuất hiện trong instance XML.

XSD chỉ biết `PENDING` là một giá trị hợp lệ, **không biết** trường hợp nghiệp vụ nào cần trả trạng thái đó; quy tắc này thuộc service/domain.

### Kiểu XML hợp lệ và không hợp lệ

Payload hợp lệ:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:data:v1">
    <ord:orderId>O-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

Payload sai schema do thiếu namespace trên phần tử con:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:data:v1">
    <orderId>O-1024</orderId>
</ord:GetOrderRequest>
~~~

Hai XML nhìn gần giống nhau, nhưng `orderId` ở ví dụ thứ hai thuộc **namespace rỗng**, trái với `elementFormDefault="qualified"`. Trong tích hợp SOAP, lỗi namespace/qualified name thường gây lỗi tương thích ngay cả khi nội dung text chính xác.

### Vì sao dùng global element?

Với **document/literal** thông dụng, WSDL thường dùng `wsdl:part` trỏ đến **global element** của XSD, chẳng hạn `ord:GetOrderRequest`. Điều này giúp client và server thống nhất root element xuất hiện trong SOAP Body, thay vì mỗi bên tự chọn một cách bao bọc dữ liệu.

`xs:complexType` định nghĩa **kiểu cấu trúc**; `xs:element` định nghĩa **phần tử XML có QName cụ thể**. WSDL có thể tham chiếu theo `element` hoặc `type` tùy thiết kế, nhưng `element` đặc biệt quan trọng với phong cách document/literal khi chú trọng tương thích giữa các stack.

## 4. Bổ sung WSDL: biến dữ liệu thành giao diện dịch vụ có thể gọi

Sau khi có `orders.xsd`, tệp `orders.wsdl` sau minh họa WSDL 1.1 với **SOAP 1.1 document/literal**. Tệp XSD nằm ở đường dẫn tương đối `orders.xsd` so với WSDL; trong dự án thật, phải bảo đảm công cụ và server có thể resolve đường dẫn đó.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:service:v1"
    xmlns:ord="urn:example:orders:data:v1"
    targetNamespace="urn:example:orders:service:v1"
    name="OrderService">

    <wsdl:types>
        <xs:schema targetNamespace="urn:example:orders:service:v1">
            <xs:import namespace="urn:example:orders:data:v1"
                       schemaLocation="orders.xsd"/>
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

    <wsdl:binding name="OrderSoap11Binding"
                  type="tns:OrderPortType">
        <soap:binding style="document"
                      transport="http://schemas.xmlsoap.org/soap/http"/>
        <wsdl:operation name="GetOrder">
            <soap:operation
                soapAction="urn:example:orders:service:v1/GetOrder"/>
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
                location="https://api.example.org/soap/orders"/>
        </wsdl:port>
    </wsdl:service>
</wsdl:definitions>
~~~

Nhìn vào bản WSDL này, ta thấy từng mối nối cụ thể:

| Thành phần | Giá trị ví dụ | Quan hệ với XSD |
| --- | --- | --- |
| `xs:import` trong `types` | `urn:example:orders:data:v1` | Nạp phần tử/kiểu dữ liệu đã định nghĩa ở `orders.xsd` |
| `GetOrderInput` | `ord:GetOrderRequest` | Request trỏ đến **global element** của XSD |
| `GetOrderOutput` | `ord:GetOrderResponse` | Response trỏ đến **global element** của XSD |
| `OrderPortType` | Operation `GetOrder` | Đặt yêu cầu và phản hồi vào một thao tác logic |
| `OrderSoap11Binding` | `document` + `literal` + SOAP/HTTP | Quy định cách đóng gói/gửi các message |
| `OrderSoap11Port` | `https://api.example.org/soap/orders` | Địa chỉ triển khai của binding |

Lưu ý ba tên thường bị nhầm:

1. **`GetOrder`** là **tên operation** trong WSDL.
2. **`GetOrderRequest`** là **tên global element** trong XSD.
3. **`GetOrderInput`** là **tên message** của WSDL tham chiếu element.

Các tên này được kết nối qua định nghĩa WSDL, nhưng **không phải cùng một khái niệm**. Một công cụ sinh mã client có thể tạo method tên `getOrder` dựa trên operation, trong khi đối tượng JAXB mô tả `GetOrderRequest`.

### Document/literal khác với việc “dùng XML” đơn thuần

`style="document"` và `use="literal"` có ý nghĩa ở **SOAP binding**: SOAP Body chứa XML theo các phần tử/kiểu được mô tả trong schema. Với mô hình document/literal wrapped phổ biến, thường có một global element đại diện cho request và một global element cho response của operation.

Không nên suy ra rằng **tất cả** dịch vụ SOAP đều dùng document/literal hoặc SOAP 1.1. Đối tác có thể dùng SOAP 1.2, cách thiết kế message khác hoặc chính sách tương tác riêng. Client phải đọc **binding thực tế**, bao gồm namespace SOAP Envelope, content type, SOAPAction khi áp dụng, và cách xử lý Fault.

## 5. Thông điệp thực tế kết nối hai hợp đồng

Với WSDL/XSD ở trên, SOAP 1.1 request có thể là:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:data:v1">
    <soapenv:Header/>
    <soapenv:Body>
        <ord:GetOrderRequest>
            <ord:orderId>O-1024</ord:orderId>
        </ord:GetOrderRequest>
    </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP 1.1 response:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:data:v1">
    <soapenv:Body>
        <ord:GetOrderResponse>
            <ord:orderId>O-1024</ord:orderId>
            <ord:status>CONFIRMED</ord:status>
        </ord:GetOrderResponse>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Hai phần tử trong `soapenv:Body` có QName khớp XSD. WSDL đặt chúng vào quan hệ **input/output của operation `GetOrder`**, định nghĩa binding và endpoint. **SOAP Envelope** bổ sung cấu trúc giao thức để vận chuyển payload.

Ở SOAP 1.1 qua HTTP, ví dụ client gửi:

~~~http
POST /soap/orders HTTP/1.1
Host: api.example.org
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:service:v1/GetOrder"
~~~

Phần sau các HTTP header là SOAP Envelope ở ví dụ trước. Đây là **một binding minh họa**, không phải yêu cầu cho mọi dịch vụ SOAP. SOAP 1.2 có namespace Envelope và quy tắc content type khác; điều kiện của WSDL/binding đang sử dụng phải là nguồn quyết định.

### Spring-WS chọn endpoint dựa vào điều gì?

Ví dụ Java (giả định lớp JAXB đã được sinh từ XSD và Spring-WS được cấu hình):

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String DATA_NS = "urn:example:orders:data:v1";
    private final OrderService orderService;

    public OrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = DATA_NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse handle(@RequestPayload GetOrderRequest request) {
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(orderService.findStatus(request.getOrderId()));
        return response;
    }
}
~~~

`@PayloadRoot` ánh xạ request theo QName của **root XML trong SOAP Body**, không phải tự động theo tên operation WSDL `GetOrder` hay theo URL giống Spring MVC. Đối tượng `GetOrderRequest`/`GetOrderResponse` đến từ XML binding; cấu hình JAXB và các lớp Java cụ thể phụ thuộc công cụ code generation.

**Điều kiện để cả hai hợp đồng nhất quán:**

- XSD định nghĩa `GetOrderRequest`; WSDL `GetOrderInput` trỏ đến đúng QName đó.
- SOAP client gửi Body có root QName tương ứng; endpoint Spring-WS có mapping khớp QName.
- Response do endpoint/JAXB tạo ra hợp lệ với `GetOrderResponse` và được mô tả trong `GetOrderOutput` của WSDL.
- SOAP stack sử dụng đúng SOAP version, transport và endpoint mà binding/port yêu cầu.

Nếu đổi root XSD thành `FindOrderRequest` nhưng giữ nguyên WSDL tham chiếu `GetOrderRequest`, lỗi không chỉ thuộc về một lớp JAXB: **hai tài liệu hợp đồng đã mất đồng bộ**.

## 6. Cái gì được kiểm tra ở mỗi lớp?

Một hệ thống có thể đi qua nhiều bước kiểm tra độc lập:

~~~mermaid
flowchart TD
    A["HTTP / Transport<br/>đúng URL, TLS, authentication"] --> B["SOAP Envelope<br/>đúng version / header"]
    B --> C["Operation / binding<br/>hợp WSDL"]
    C --> D["Payload XML<br/>hợp XSD"]
    D --> E["JAXB binding<br/>XML ↔ Java objects"]
    E --> F["Business rules<br/>quyền xem và trạng thái đơn hàng"]
    F --> G["SOAP response / fault<br/>đúng hợp đồng"]
~~~

Sơ đồ là cách **phân tích trách nhiệm**, không khẳng định Spring-WS bắt buộc thi hành các bước theo đúng thứ tự này hoặc tự động validate tất cả bước. Ví dụ, một endpoint mapping có thể dispatch theo payload QName trước khi application-level XSD validation diễn ra; việc bật schema validation phải được cấu hình riêng.

| Trường hợp | XSD | WSDL | Kết luận |
| --- | --- | --- | --- |
| `orderId` chứa ký tự thường `o-1024` | Không hợp pattern ví dụ | Vẫn mô tả operation | Cần từ chối hoặc xử lý lỗi validation |
| `orderId` đúng mẫu nhưng request gửi sai SOAP version | Hợp lệ về cấu trúc payload | Không hợp binding SOAP 1.1 | Lỗi giao thức/binding |
| Payload `GetOrderRequest` đúng nhưng gửi đến URL không tồn tại | Hợp lệ | Địa chỉ/triển khai không khớp | Lỗi kết nối/routing |
| XML hợp XSD nhưng người dùng không có quyền xem đơn | Hợp lệ | Có operation phù hợp | Bị từ chối bởi chính sách bảo mật/nghiệp vụ |
| Client gửi phần tử có namespace `v2` | Không khớp XSD v1 | Message vẫn trỏ namespace v1 | Có thể không map được endpoint hoặc bị từ chối |
| Response XML đúng schema nhưng trạng thái nghiệp vụ sai | Hợp lệ | Giao diện hợp lệ | Lỗi logic nghiệp vụ cần kiểm thử riêng |

**Một điều kiện cần không phải điều kiện đủ:** validate XSD thành công chưa bảo đảm invocation thành công; sinh client từ WSDL thành công cũng chưa bảo đảm XML runtime đúng với hợp đồng hoặc phù hợp quy tắc nghiệp vụ.

## 7. Hợp đồng còn bao gồm lỗi và ngữ nghĩa tương tác

### SOAP Fault không phải response nghiệp vụ thông thường

Nếu `orderId` không tồn tại, dịch vụ cần phân biệt với trường hợp `GetOrderResponse` trả một trạng thái hợp lệ. Với SOAP, các tình huống lỗi thường được truyền bằng **SOAP Fault**. Ví dụ minh họa SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Order ID không hợp lệ</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

SOAP 1.2 dùng cấu trúc Fault khác (`Code`, `Reason`, `Detail`…). Hợp đồng có thể định nghĩa **typed fault** bằng phần tử XSD cho fault detail và khai báo `wsdl:fault` cho operation trong WSDL 1.1, kèm binding tương ứng. Lúc đó client code generation có cơ sở để nhận biết dạng lỗi đã khai báo.

Không phải lỗi nào cũng được biểu diễn đầy đủ bằng `wsdl:fault`; lỗi hạ tầng, bảo mật hoặc dispatch có thể phát sinh ở lớp giao thức. Vì vậy:

- XSD quy định cấu trúc của **fault detail** nếu dịch vụ công bố kiểu lỗi.
- WSDL có thể khai báo những fault thuộc hợp đồng của **operation**.
- Spring-WS dùng exception resolver/handler để ánh xạ exception thành SOAP Fault thích hợp; chính sách xử lý lỗi cần được định nghĩa rõ.
- API contract và tài liệu nghiệp vụ phải nói khi nào lỗi phát sinh, có retry hay không, đâu là lỗi phía gọi và đâu là lỗi hệ thống.

### Những gì XSD/WSDL không diễn đạt đủ

Hai hợp đồng là nền tảng để máy hiểu dữ liệu và giao diện, nhưng không thay thế:

- **Business invariants**: chỉ chủ đơn hàng mới xem được trạng thái, đơn hàng đã hủy không được xác nhận lại.
- **Idempotency và giao dịch**: một lệnh có thể gọi lại an toàn không, cần khóa định danh giao dịch không.
- **SLA và vận hành**: timeout, giới hạn lưu lượng, retry/backoff, sự cố mạng.
- **Quy tắc thời gian**: giá trị datetime hợp XSD nhưng timezone hay cách diễn giải có thể khác ý nghĩa.
- **Quyền truy cập**: điều kiện xác thực/ủy quyền, cơ chế cấp chứng chỉ và quản lý vòng đời khóa.

Những quy tắc này cần được mô tả, thử nghiệm và quản lý cùng contract. Với các yêu cầu tiêu chuẩn có thể dùng thêm WS-Policy/WS-SecurityPolicy khi đối tác hỗ trợ; không mặc định rằng chỉ có WSDL/XSD thì toàn bộ quy tắc bảo mật đã được diễn đạt.

## 8. Thiết kế hợp đồng tốt: tách biệt nhưng nhất quán

### 8.1. Định nghĩa dữ liệu để có thể tái sử dụng

Thay vì lặp lại một `OrderIdType` ở mọi request/response, ta đưa nó thành kiểu dùng chung trong XSD. Các kiểu đơn giản có thể chứa rule dữ liệu ổn định như pattern, giới hạn độ dài, enumerations. Kiểu phức tạp dùng lại được khi các cấu trúc thực sự có cùng ý nghĩa.

Tuy nhiên, **không cố gắng dùng một kiểu `Order` duy nhất cho mọi thao tác** nếu request và response có ngữ nghĩa khác nhau. Ví dụ, `CreateOrderRequest` có thể chỉ chứa các trường người dùng cung cấp, còn `GetOrderResponse` có thêm mã hệ thống và trạng thái. Chia tách giúp tránh vô tình mở quyền ghi dữ liệu mà client không nên kiểm soát.

### 8.2. Đặt tên operation theo khả năng dịch vụ

Một operation trong WSDL nên đại diện cho một hành vi rõ ràng: `GetOrder`, `CreateOrder`, `CancelOrder`. Không nên để mỗi message request mang một dạng XML tùy ý và sau đó phân tích bằng chuỗi để đoán chức năng.

Các kiểu request/response nên phù hợp với operation và quy tắc business, dù công cụ sinh WSDL có thể áp dụng quy ước tên. Quan trọng hơn tên là mối nối chính xác **message → XSD element → operation → binding**.

### 8.3. Namespace là danh tính kỹ thuật

Namespace URI có thể trông giống URL hoặc URN, nhưng được dùng như **định danh**, không nhất thiết là địa chỉ tải tài nguyên. Thay prefix không đổi QName nếu URI và local name giữ nguyên; thay URI sẽ đổi QName. Với SOAP contract-first, đây là thay đổi có thể phá vỡ mapping ở endpoint và client.

### 8.4. Phân biệt optional, nil và chuỗi rỗng

Ba tình huống sau có thể khác nhau về ngữ nghĩa:

~~~xml
<!-- Không có phần tử note -->

<ord:note xmlns:ord="urn:example:orders:data:v1"/>

<ord:note xmlns:ord="urn:example:orders:data:v1"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:nil="true"/>
~~~

- **Vắng mặt:** chỉ hợp lệ nếu khai báo tương ứng cho phép, thường qua `minOccurs="0"`.
- **Phần tử rỗng:** phần tử vẫn hiện diện; nội dung là chuỗi rỗng hoặc giá trị XML tương ứng, cần kiểm tra kiểu XSD.
- **`xsi:nil="true"`:** chỉ hợp lệ khi khai báo phần tử cho phép `nillable="true"`.

JAXB có thể thể hiện khác nhau giữa absence và nil tùy lớp sinh, `JAXBElement` và cấu hình binding. Một sự thay đổi XSD nhìn có vẻ nhỏ có thể làm thay đổi serialization và hành vi client.

### 8.5. Tránh vòng phụ thuộc giữa các schema

Khi tách XSD thành nhiều tệp và namespace, dùng `xs:include` cho schema cùng target namespace và `xs:import` cho schema khác namespace theo quy tắc XML Schema. Bảo đảm đường dẫn schema được công bố và có thể resolve trong môi trường phát triển lẫn production.

Không nên đưa toàn bộ định nghĩa vào một WSDL khổng lồ nếu có nhiều schema dùng lại; đồng thời không chia thành quá nhiều import phức tạp làm đối tác không tải được hợp đồng. Bản phát hành phải bao gồm **toàn bộ tập WSDL + XSD phụ thuộc**.

## 9. Thay đổi hợp đồng và tương thích phiên bản

Với contract-first, **hợp đồng là giao diện công khai của tích hợp**, nên mỗi thay đổi cần đánh giá tác động đến cả data contract lẫn service contract.

| Thay đổi | Tầng bị ảnh hưởng | Rủi ro tương thích |
| --- | --- | --- |
| Thêm trường optional `minOccurs="0"` trong response | XSD, JAXB classes | Có thể tương thích về schema nhưng client cũ có thể bỏ qua hoặc từ chối field ngoài dự kiến; phải test |
| Thêm giá trị enum `REFUNDED` vào `OrderStatusType` | XSD, JAXB binding và logic xử lý | Client cũ có thể dùng enum đóng và không hiểu giá trị mới |
| Đổi `GetOrderRequest` thành `FindOrderRequest` | XSD, WSDL message, endpoint mapping | Thường là thay đổi phá vỡ contract |
| Đổi namespace v1 thành v2 | XSD và các tham chiếu WSDL | QName mới; thường cần endpoint/contract version mới |
| Thêm operation `CancelOrder` | WSDL, XSD mới cho request/response | Có thể là mở rộng tương thích cho client cũ nếu không ảnh hưởng operation cũ |
| Đổi SOAP 1.1 sang SOAP 1.2 | WSDL binding, SOAP stack/client | Thay đổi giao thức, thường không tương thích trực tiếp |
| Chỉ đổi URL endpoint giữa staging/production | `service/port` hoặc cấu hình client | Thay đổi deployment; cần kiểm tra kết nối/TLS, chưa nhất thiết đổi data contract |
| Bắt buộc ký SOAP Body mà trước đây không cần | Security policy/interceptor, client | Thay đổi điều kiện gọi dịch vụ dù payload XSD giữ nguyên |

Không có quy tắc rằng **thêm field optional luôn an toàn**: một số client sinh mã dùng validator chặt hoặc binding dựa trên schema cũ, và ngữ nghĩa của thông điệp có thể thay đổi. Kết luận về tương thích cần được xác nhận bằng thử nghiệm với các client đang hoạt động.

### Quy trình thay đổi an toàn

1. **Xác định tầng thay đổi:** chỉ XSD, chỉ WSDL, binding, endpoint, fault hay security policy.
2. **Đánh giá client hiện có:** có sinh mã lại không, có phụ thuộc namespace/enum/thứ tự trường không.
3. **Chạy kiểm thử với hợp đồng cũ và mới:** request/response mẫu, positive/negative, SOAP Fault, signature và certificates.
4. **Quản lý phiên bản:** nếu thay đổi phá vỡ giao diện, công bố v2 với namespace/WSDL hoặc endpoint phù hợp, duy trì v1 một thời gian khi cần.
5. **Công bố trọn bộ artifact:** WSDL và tất cả XSD/import đi kèm; kiểm tra địa chỉ public thực tế.

Một release chứa XSD v2 nhưng WSDL vẫn tham chiếu QName v1 là **hợp đồng lỗi**. Tương tự, cập nhật WSDL trước khi endpoint có mapping tương ứng khiến client sinh theo hợp đồng mới nhưng không gọi được server.

## 10. Vai trò của JAXB trong hệ hợp đồng

**JAXB là cầu nối XML ↔ đối tượng Java**, không phải nguồn định nghĩa dịch vụ độc lập:

~~~text
orders.xsd
    └── công cụ sinh mã JAXB → GetOrderRequest / GetOrderResponse / ...

orders.wsdl
    └── công cụ sinh SOAP client → mô hình service/port, gọi operation
        └── có thể sử dụng các lớp dữ liệu sinh từ schema

SOAP Body ↔ JAXB marshal/unmarshal ↔ Java endpoint/client
~~~

Trong Spring-WS, `Jaxb2Marshaller` là một lựa chọn phổ biến để ánh xạ giữa XML và Java. Trong một số dự án, lớp JAXB được sinh từ XSD riêng; ở các toolchain khác, việc sinh SOAP client từ WSDL cũng sinh luôn model JAXB dựa trên schema tham chiếu. Cần kiểm tra cấu hình để tránh sinh trùng kiểu với package khác nhưng cùng namespace.

Ví dụ lỗi sai kỳ vọng:

> Đã có lớp Java `GetOrderRequest` nên có thể đổi tên field `orderId` thành `orderCode` và build vẫn xanh.

Không nhất thiết đúng. Nếu annotation hoặc mã JAXB được đổi nhưng XSD/WSDL công khai không đổi, XML runtime có thể không còn khớp contract. Ở chiều ngược lại, nếu XSD thay đổi mà không tái sinh classes, client/server có thể xử lý dữ liệu sai hoặc bị lỗi unmarshal.

**Ưu tiên quy trình:** thiết kế và rà soát XSD/WSDL → sinh mã JAXB/client → triển khai endpoint/service → kiểm tra XML thực tế. Không sửa lớp sinh mã như một cách thay thế thay đổi hợp đồng.

Lưu ý về môi trường Java: các stack hiện đại dựa trên Jakarta JAXB thường dùng package `jakarta.xml.bind`, trong khi một số dự án cũ dùng `javax.xml.bind`. API, runtime và mã sinh phải cùng thế hệ tương thích. Sự khác biệt này thuộc cấu hình code generation/runtime, **không phải lý do tự ý đổi cấu trúc hợp đồng XSD**.

## 11. SOAP Fault, interceptor, WS-Security và chứng chỉ đặt ở đâu?

Hợp đồng SOAP trong doanh nghiệp thường đòi hỏi nhiều hơn hai tệp XSD/WSDL:

| Khía cạnh | Nơi định nghĩa/kiểm soát | Liên hệ với hợp đồng |
| --- | --- | --- |
| Cấu trúc payload request/response | XSD | Phải khớp elements được WSDL tham chiếu |
| Operation, message, SOAP binding, endpoint | WSDL | Chỉ ra cách trao đổi payload theo service interface |
| Fault detail có kiểu tường minh | XSD + `wsdl:fault` khi công bố | Client có thể hiểu dạng lỗi mà operation đã khai báo |
| Xác thực/ủy quyền | Chính sách ứng dụng và bảo mật kết nối | Có thể đòi hỏi token, mTLS hoặc cơ chế khác |
| Ký, mã hóa SOAP message | WS-Security/WS-SecurityPolicy, interceptor | Tác động tới SOAP Header và phần thông điệp phải bảo vệ |
| Chứng chỉ và khóa | Keystore/truststore, chính sách vận hành | Dùng cho TLS/mTLS, chữ ký hoặc mã hóa tùy yêu cầu |
| Schema validation | Spring-WS interceptor hoặc bộ kiểm tra XML | Kiểm soát payload runtime so với XSD |

**HTTPS/mTLS** bảo vệ kênh truyền, còn **WS-Security** có thể ký hoặc mã hóa các phần SOAP message và cung cấp các cơ chế token ở cấp thông điệp. Hai lớp giải quyết nhu cầu khác nhau; XSD/WSDL cơ bản **không tự động triển khai** chúng. Cần cấu hình Spring-WS interceptor, chẳng hạn giải pháp dựa trên WSS4J, và kiểm thử các chính sách thực tế với đối tác.

Đặc biệt, nếu SOAP Body được ký, việc thay đổi dữ liệu/namespace sau khi ký có thể làm chữ ký không còn hợp lệ. Những phép chuẩn hóa XML, XSLT hoặc ánh xạ JAXB cần được đặt đúng vị trí trong pipeline nhận/gửi, phù hợp cách xác minh/ký thông điệp của hệ thống.

Trong Spring-WS, `PayloadValidatingInterceptor` thường được dùng để kiểm tra payload theo XSD khi được cấu hình; không nên suy ra có XSD là **mọi message mặc định đã được validate**. Tương tự, SOAP Fault mapping và WS-Security đều phải được cấu hình riêng theo yêu cầu hợp đồng.

## 12. Kiểm thử hợp đồng ở nhiều lớp

Kiểm thử contract-first cần chứng minh cả hai điều: **tài liệu hợp đồng có thể được sử dụng** và **dịch vụ thực thi đúng tài liệu đó**.

| Cấp kiểm thử | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **XSD validation** | XML đúng QName, thứ tự, kiểu, cardinality | `GetOrderResponse` phải có `status` thuộc enum |
| **WSDL resolve/parse** | Các import, message, portType, binding, port hợp lệ và tham chiếu đúng | Mọi `wsdl:part` element đều resolve được tới XSD |
| **Code generation** | Client/JAXB tool đọc trọn contract | Sinh lớp từ XSD, client từ WSDL không lỗi |
| **Endpoint mapping** | SOAP Body root được ánh xạ đúng Spring-WS endpoint | `GetOrderRequest` đi vào handler `handle` |
| **Message integration** | Server trả đúng Envelope, payload, Fault | SOAP 1.1 document/literal request/response |
| **Business contract** | Quy tắc nghiệp vụ và lỗi được bảo đảm | Đơn hàng không tồn tại trả lỗi đã định nghĩa |
| **Security/interoperability** | WS-Security, chữ ký, chứng chỉ, SOAP stack đối tác tương thích | Gọi qua client .NET/Java và thử chữ ký sai |
| **Regression/versioning** | Client cũ tiếp tục hoạt động khi thay đổi được công bố tương thích | Kiểm thử v1 với server đã nâng cấp |

### Kiểm tra thí dụ XSD bằng dữ liệu phản ví dụ

Bắt đầu với response hợp lệ:

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:data:v1">
    <ord:orderId>O-1024</ord:orderId>
    <ord:status>CONFIRMED</ord:status>
</ord:GetOrderResponse>
~~~

Lần lượt thay `CONFIRMED` thành `UNKNOWN`, bỏ `orderId`, đảo thứ tự hai element hoặc đổi namespace v1 thành v2. Một validator XSD cấu hình đúng phải từ chối những ví dụ đó theo schema đã nêu.

Sau đó giữ payload đúng nhưng đổi SOAP Envelope từ 1.1 sang 1.2 trong khi client/server đang yêu cầu binding 1.1. Trường hợp này minh họa vì sao **XSD validation có thể PASS nhưng kiểm thử giao thức phải FAIL**.

### Công cụ kiểm thử trong Spring-WS

- **`MockWebServiceClient`** giúp gửi SOAP request tới endpoint trong môi trường kiểm thử và đối chiếu response, schema hoặc Fault phù hợp.
- **`MockWebServiceServer`** giúp kiểm tra ứng dụng client dùng `WebServiceTemplate` đã tạo đúng SOAP request và xử lý response từ server mô phỏng.
- Công cụ SOAP client hoặc công cụ sinh mã từ **WSDL** giúp kiểm thử khả năng tiêu thụ dịch vụ từ một bên độc lập; thử trên cả SOAP stack dự kiến của đối tác khi có yêu cầu tương thích.

Không dừng ở unit test phương thức Java. Một method có thể trả đúng `GetOrderResponse` trong bộ nhớ nhưng lại marshal sai namespace, trả sai SOAP version hoặc bị chính sách WS-Security từ chối trên đường truyền.

### Checklist kiểm thử khi chuẩn bị bàn giao hợp đồng

1. WSDL mở được từ môi trường tích hợp và resolve đủ XSD import, không phụ thuộc đường dẫn máy phát triển.
2. Client sinh mã từ **bộ artifact công bố** thành công, không cần chỉnh tay để sửa QName.
3. Request/response mẫu validate XSD; những payload sai schema bị từ chối theo quy ước lỗi rõ ràng.
4. Operation, SOAP version, HTTP headers liên quan, binding và endpoint khớp WSDL.
5. SOAP Fault của các tình huống nghiệp vụ và kỹ thuật có dạng thích hợp; không lộ nội dung nhạy cảm.
6. Token, TLS/mTLS, chứng chỉ, ký/mã hóa SOAP được kiểm tra đúng chính sách; không giả định WSDL tự bật bảo mật.
7. Client đã triển khai và phiên bản trước đó được kiểm thử theo kế hoạch tương thích.

## 13. Bài tập thiết kế để tự đánh giá

**Tình huống:** Hợp đồng `GetOrder` cần bổ sung một trường thông tin ngày cập nhật `updatedAt` vào response và một operation `CancelOrder`.

1. Xác định trường `updatedAt` cần được thêm ở **XSD**, **WSDL** hay cả hai. Nếu thêm optional, quy định rõ trường vắng mặt có ý nghĩa gì và kiểm tra ảnh hưởng tới client cũ.
2. Thiết kế `CancelOrderRequest`, `CancelOrderResponse` trong XSD; thêm `wsdl:message` và operation `CancelOrder` vào `portType`. Đừng quên binding tương ứng.
3. Liệt kê các bước để chứng minh SOAP client sinh từ WSDL gọi được cả `GetOrder` và `CancelOrder`.
4. Nếu đối tác yêu cầu ký SOAP Body và dùng chứng chỉ X.509, giải thích vì sao XSD/WSDL chưa đủ để bảo đảm yêu cầu bảo mật và phải cấu hình interceptor/chính sách nào.
5. Giả sử response `CancelOrderResponse` hoàn toàn hợp lệ theo XSD nhưng server trả trạng thái `CANCELLED` cho đơn hàng không thuộc quyền người gọi. Xác định lỗi thuộc tầng nào và cần thêm bộ kiểm thử gì.

**Kết luận:** **XSD bảo vệ cấu trúc và kiểu dữ liệu XML; WSDL đưa các phần tử đó vào giao diện dịch vụ có operation, message, binding và endpoint rõ ràng.** Hai hợp đồng hợp thành trục chính của SOAP contract-first, nhưng không thay thế SOAP runtime, JAXB, chính sách bảo mật hay kiểm thử nghiệp vụ. Thiết kế chúng cùng nhau, phát hành chúng đồng bộ và kiểm thử cả dữ liệu lẫn cách gọi là điều kiện quan trọng để một tích hợp Spring Web Services ổn định và tương thích lâu dài.
