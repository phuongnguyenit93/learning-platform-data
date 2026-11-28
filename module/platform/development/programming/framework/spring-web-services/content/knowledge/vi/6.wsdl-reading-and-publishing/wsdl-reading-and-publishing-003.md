# SOAP binding, transport, action và địa chỉ dịch vụ

## 1. Bốn thông tin quyết định cách gọi một dịch vụ SOAP

Khi nhận một tài liệu **WSDL**, SOAP client cần xác định không chỉ dịch vụ cung cấp operation nào mà còn phải biết **dùng giao thức gì, đóng gói thông điệp ra sao, gửi action nào và kết nối đến địa chỉ nào**. Đây là trọng tâm của phần **Đọc và công bố WSDL** trong học phần **Spring Web Services (Spring-WS)** theo hướng **contract-first**.

Ví dụ một hệ thống cần gọi operation `GetOrder` của dịch vụ đơn hàng. Bốn phần thông tin phải phối hợp:

| Thông tin | Vị trí điển hình trong WSDL 1.1 | Trả lời câu hỏi |
| --- | --- | --- |
| **SOAP binding** | `wsdl:binding` và `soap:binding` | Operation trừu tượng được truyền qua SOAP với kiểu tài liệu nào? |
| **Transport** | `soap:binding/@transport` | SOAP sử dụng cơ chế truyền tải nào, chẳng hạn SOAP qua HTTP? |
| **Action** | `soap:operation/@soapAction` | Thao tác SOAP này công bố giá trị action nào cho client? |
| **Địa chỉ dịch vụ** | `wsdl:service/wsdl:port/soap:address/@location` | Gửi HTTP POST đến URL thực tế nào? |

**Đừng đồng nhất ba chuỗi URI sau:** `transport="http://schemas.xmlsoap.org/soap/http"` là định danh SOAP-over-HTTP, `soapAction="urn:example:orders:GetOrder"` là định danh action, còn `location="https://api.example.test/soap/orders"` là địa chỉ mạng để kết nối. Chúng có mục đích riêng.

Trong thiết kế dịch vụ theo hợp đồng, WSDL xác định phần giao tiếp công khai, XSD mô tả cấu trúc XML, JAXB ánh xạ sang Java, endpoint Spring-WS xử lý nghiệp vụ và SOAP client gửi thông điệp đúng binding. Khi một trong bốn thông tin trên sai, client có thể nhận HTTP 404/415, SOAP Fault, không tìm thấy operation hoặc không kết nối được.

## 2. Từ mô tả trừu tượng tới cấu hình cụ thể trong WSDL 1.1

WSDL 1.1 tách **dịch vụ làm được gì** khỏi **cách và nơi để gọi**:

~~~mermaid
flowchart TD
    A["wsdl:types — XSD request/response"] --> B["wsdl:message — phần tử dữ liệu"]
    B --> C["wsdl:portType — operation trừu tượng"]
    C --> D["wsdl:binding — SOAP + transport + action"]
    D --> E["wsdl:service / wsdl:port — binding và endpoint URL"]
    E --> F["SOAP client: tạo XML và gửi request"]
~~~

| Phần tử WSDL 1.1 | Vai trò | Có phải URL endpoint? |
| --- | --- | --- |
| `wsdl:types` | Định nghĩa/nhúng hoặc tham chiếu XSD cho payload | Không |
| `wsdl:message` | Khai báo thông điệp của input/output/fault | Không |
| `wsdl:portType` | Tập hợp operation độc lập transport | Không |
| `wsdl:binding` | Ánh xạ portType sang chi tiết SOAP và transport | Không |
| `wsdl:service` | Nhóm các cổng dịch vụ liên quan | Không |
| `wsdl:port` | Ghép một binding cụ thể với một endpoint | Chứa địa chỉ trong phần tử mở rộng |
| `soap:address` | Địa chỉ URL mà SOAP client truy cập | **Có** |

Một `portType` có thể có nhiều `binding` (ví dụ SOAP 1.1 và SOAP 1.2); một binding có thể được dùng bởi nhiều `port` ở các URL khác nhau. **Operation name**, **SOAP action** và **endpoint URL** là ba khái niệm khác nhau dù tên hoặc đường dẫn có thể tương tự.

Bài học sử dụng **WSDL 1.1** vì đây là định dạng phổ biến trong tích hợp Spring-WS. WSDL 2.0 có mô hình thành phần và cú pháp khác; không áp dụng trực tiếp đường dẫn `wsdl:portType` và `wsdl:port` của WSDL 1.1 sang tài liệu WSDL 2.0.

## 3. Ví dụ WSDL 1.1 hoàn chỉnh: OrderService

Hãy xem một hợp đồng document/literal cho operation `GetOrder`. Ví dụ dưới đây dùng chung namespace `urn:example:orders:v1` cho định nghĩa WSDL và các phần tử nghiệp vụ để tiện theo dõi; trong hệ thống thực tế, hai target namespace có thể khác nhau.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    name="OrderService"
    targetNamespace="urn:example:orders:v1">

    <wsdl:types>
        <xs:schema
            targetNamespace="urn:example:orders:v1"
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
                        <xs:element name="status" type="xs:string"/>
                    </xs:sequence>
                </xs:complexType>
            </xs:element>
        </xs:schema>
    </wsdl:types>

    <wsdl:message name="GetOrderInput">
        <wsdl:part name="parameters"
                   element="tns:GetOrderRequest"/>
    </wsdl:message>

    <wsdl:message name="GetOrderOutput">
        <wsdl:part name="parameters"
                   element="tns:GetOrderResponse"/>
    </wsdl:message>

    <wsdl:portType name="OrderPortType">
        <wsdl:operation name="GetOrder">
            <wsdl:input message="tns:GetOrderInput"/>
            <wsdl:output message="tns:GetOrderOutput"/>
        </wsdl:operation>
    </wsdl:portType>

    <wsdl:binding name="OrderSoap11Binding"
                  type="tns:OrderPortType">
        <soap:binding
            style="document"
            transport="http://schemas.xmlsoap.org/soap/http"/>

        <wsdl:operation name="GetOrder">
            <soap:operation
                soapAction="urn:example:orders:GetOrder"/>
            <wsdl:input>
                <soap:body use="literal"/>
            </wsdl:input>
            <wsdl:output>
                <soap:body use="literal"/>
            </wsdl:output>
        </wsdl:operation>
    </wsdl:binding>

    <wsdl:service name="OrderService">
        <wsdl:port
            name="OrderSoap11Port"
            binding="tns:OrderSoap11Binding">
            <soap:address
                location="https://api.example.test/soap/orders"/>
        </wsdl:port>
    </wsdl:service>
</wsdl:definitions>
~~~

**Luồng đọc hợp đồng:**

1. `GetOrderRequest` và `GetOrderResponse` là **global elements** của XSD. Cấu trúc XML được mô tả trong `wsdl:types`.
2. `GetOrderInput` và `GetOrderOutput` là các **WSDL messages**, mỗi message trỏ đến một global XSD element.
3. `OrderPortType` định nghĩa operation tên `GetOrder` với input và output tương ứng.
4. `OrderSoap11Binding` tham chiếu `tns:OrderPortType`, xác định **SOAP 1.1 document/literal qua HTTP** và action của `GetOrder`.
5. `OrderSoap11Port` trỏ đến binding đó và khai báo **URL gọi thực tế**.

Khi phân tích lỗi, đọc chuỗi phụ thuộc theo thứ tự `service → port → binding → portType → message → XSD`. Nếu chỉ mở `wsdl:portType`, bạn thấy tên operation nhưng **chưa thấy transport, action hoặc endpoint URL**.

## 4. `wsdl:binding` liên kết operation với SOAP cụ thể

Đoạn then chốt:

~~~xml
<wsdl:binding name="OrderSoap11Binding"
              type="tns:OrderPortType">
    <soap:binding
        style="document"
        transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetOrder">
        <soap:operation soapAction="urn:example:orders:GetOrder"/>
        <wsdl:input>
            <soap:body use="literal"/>
        </wsdl:input>
        <wsdl:output>
            <soap:body use="literal"/>
        </wsdl:output>
    </wsdl:operation>
</wsdl:binding>
~~~

### 4.1. Phân biệt hai phần tử đều có tên “binding”

- `wsdl:binding` thuộc namespace **`http://schemas.xmlsoap.org/wsdl/`**. Nó định nghĩa một binding có tên, liên kết tới portType qua `type="tns:OrderPortType"`.
- `soap:binding` thuộc namespace **`http://schemas.xmlsoap.org/wsdl/soap/`**. Đây là **phần tử mở rộng SOAP 1.1 của WSDL**, cung cấp `style` và `transport` cho binding.

Tên prefix có thể đổi từ `wsdl` sang `w` hoặc từ `soap` sang `s` mà không đổi ý nghĩa, miễn namespace URI đúng.

### 4.2. `style="document"` và `style="rpc"`

`soap:binding/@style` cho biết hình thức biểu diễn thông điệp SOAP:

| Style | Ý nghĩa chính | Hệ quả với payload |
| --- | --- | --- |
| `document` | SOAP Body chứa tài liệu XML theo schema/hợp đồng | Thường dùng một phần tử request/response được mô tả bằng XSD |
| `rpc` | SOAP Body được diễn giải theo quy ước lời gọi thủ tục, với cấu trúc wrapper/parameter của RPC | Cách biểu diễn tham số và tên wrapper theo quy tắc RPC |

`soap:operation` cũng có thể khai báo `style` để ghi đè kiểu chung của binding cho từng operation. Đừng chỉ đoán style từ tên `GetOrderRequest`.

### 4.3. `use="literal"` khác `use="encoded"`

`soap:body/@use` mô tả cách biểu diễn nội dung SOAP Body:

- **`literal`:** các phần tử/kiểu XML được diễn đạt theo định nghĩa schema trực tiếp; phù hợp thiết kế contract-first và khả năng tương tác liên nền tảng.
- **`encoded`:** sử dụng quy tắc SOAP encoding; từng xuất hiện trong các dịch vụ đời cũ nhưng thường gây khó khăn cho tương thích và không phù hợp các quy tắc WS-I Basic Profile phổ biến cho document/literal.

Trong dự án Spring-WS mới, nên thiết kế **document/literal** với phần tử request/response có cấu trúc XSD rõ ràng. Tuy vậy, `document` và `literal` là **hai thuộc tính độc lập**; chỉ thấy một trong hai chưa đủ kết luận cả mô hình.

## 5. `transport`: định danh cơ chế truyền tải, không phải địa chỉ máy chủ

Ví dụ:

~~~xml
<soap:binding
    style="document"
    transport="http://schemas.xmlsoap.org/soap/http"/>
~~~

Chuỗi `http://schemas.xmlsoap.org/soap/http` là **URI chuẩn định danh SOAP HTTP transport binding** trong WSDL SOAP 1.1. Nó **không phải đường dẫn để gửi request**, không phải URL tải WSDL và không cần mở được trên trình duyệt.

### 5.1. HTTPS vẫn sử dụng cùng transport URI

Hai giá trị:

~~~xml
transport="http://schemas.xmlsoap.org/soap/http"
~~~

và:

~~~xml
<soap:address
    location="https://api.example.test/soap/orders"/>
~~~

**Không mâu thuẫn**. Trường `transport` chỉ định cơ chế SOAP-over-HTTP; địa chỉ `https://...` cho biết HTTP được bảo vệ bằng TLS trên đường truyền. Không thay `transport` bằng `https://api.example.test/soap/orders`, và không tự “nâng cấp” transport URI thành một chuỗi `https://schemas.xmlsoap.org/...` vì endpoint sử dụng HTTPS.

### 5.2. Transport không mô tả toàn bộ bảo mật

URL `https://...` cho biết client dự kiến dùng TLS, nhưng **không tự bảo đảm** chứng chỉ hợp lệ, hệ thống xác thực được client hoặc thông điệp có chữ ký WS-Security. Những vấn đề đó có thể được quy định thêm bằng cấu hình TLS/mTLS, WS-SecurityPolicy hoặc hợp đồng vận hành.

Ví dụ, lỗi `SSLHandshakeException` vì truststore không tin cậy chứng chỉ xảy ra **trước khi endpoint Spring-WS đọc SOAP Body**. Đây là lỗi kết nối TLS, không thể suy ra có SOAP Fault chỉ từ hiện tượng đó.

## 6. `soapAction`: định danh ý định của operation

Trong WSDL 1.1 với SOAP 1.1 binding:

~~~xml
<wsdl:operation name="GetOrder">
    <soap:operation soapAction="urn:example:orders:GetOrder"/>
    <!-- input / output ... -->
</wsdl:operation>
~~~

`soapAction` mô tả giá trị **SOAPAction HTTP header** được công bố cho operation tương ứng khi dùng SOAP 1.1 over HTTP. Nó có thể là một URI `urn:...`, một HTTP URI hoặc giá trị rỗng theo hợp đồng. Đó là **định danh action**, không nhất thiết là địa chỉ URL có thể truy cập.

SOAPAction **không phải**:

- URL được client POST đến. URL nằm tại `soap:address/@location`.
- QName của phần tử gốc request. QName được xác định trong XSD/WSDL message.
- Tên Java method của Spring-WS endpoint.
- Một cơ chế xác thực hoặc phân quyền; server phải kiểm tra bảo mật độc lập.
- Đồng nghĩa tự động với `wsa:Action` của WS-Addressing, dù chúng có thể được cấu hình liên hệ theo hợp đồng.

### 6.1. Ví dụ HTTP SOAP 1.1 request

~~~http
POST /soap/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:GetOrder"
~~~

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:o="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Ba giá trị cần đối chiếu là:

| Thành phần trên dây | Giá trị | Được xác định bởi |
| --- | --- | --- |
| HTTP request target | `/soap/orders` tại host `api.example.test` | `soap:address/@location` |
| HTTP `SOAPAction` | `"urn:example:orders:GetOrder"` | `soap:operation/@soapAction` |
| Root của SOAP Body | `{urn:example:orders:v1}GetOrderRequest` | XSD global element tham chiếu từ `wsdl:message` |

Spring-WS có thể ánh xạ endpoint dựa trên **QName của payload** với `@PayloadRoot` hoặc theo action với `@SoapAction` khi cơ chế mapping tương ứng được dùng. Vì vậy không nên giả định cứ đổi HTTP `SOAPAction` thì `@PayloadRoot` sẽ chọn endpoint khác: phải hiểu cách ứng dụng cấu hình endpoint mappings.

### 6.2. Action rỗng, thiếu action và khác biệt giữa các đối tác

Trong SOAP 1.1 HTTP binding, `SOAPAction` là header được giao thức định nghĩa. Một số biến thể thường được gặp:

~~~http
SOAPAction: "urn:example:orders:GetOrder"
~~~

~~~http
SOAPAction: ""
~~~

~~~http
SOAPAction:
~~~

Theo ý nghĩa SOAP 1.1, **chuỗi có URI**, **chuỗi rỗng có dấu ngoặc kép** và **header không có giá trị** là những tình huống có thể mang ý nghĩa khác nhau. Với SOAP 1.1, client HTTP cần tuân thủ quy tắc header trong binding và hợp đồng WSDL; đồng thời một số stack cũ yêu cầu định dạng giá trị rất cụ thể. Khi WSDL công bố action rỗng, đừng tự suy diễn rằng gửi một URI bất kỳ sẽ tương thích.

Các lỗi thực tế có thể xuất hiện khi action không khớp:

- Proxy hoặc gateway áp dụng quy tắc route theo action không tìm thấy operation.
- Service framework yêu cầu action cụ thể và trả HTTP error/SOAP Fault.
- Client cũ so khớp action khác với WSDL vừa công bố.
- Nội dung SOAP Body đúng QName nhưng hệ thống đã được cấu hình định tuyến theo action nên lời gọi vẫn thất bại.

Phải xem cả **WSDL đã công bố**, header HTTP **thực tế gửi đi** và cấu hình routing của server. Action có thể chỉ là metadata đối với một endpoint định tuyến theo payload; lỗi action không phải lúc nào cũng gây thất bại.

## 7. `soap:address/@location`: URL của endpoint

Trong WSDL 1.1:

~~~xml
<wsdl:service name="OrderService">
    <wsdl:port
        name="OrderSoap11Port"
        binding="tns:OrderSoap11Binding">
        <soap:address
            location="https://api.example.test/soap/orders"/>
    </wsdl:port>
</wsdl:service>
~~~

Đây là nơi **`wsdl:port` ghép binding với URL endpoint**. Một SOAP client sinh từ WSDL thường dùng giá trị `location` làm địa chỉ gửi request mặc định, dù nhiều client library cho phép đổi URL qua cấu hình runtime.

**Phân biệt:**

| Khái niệm | Ví dụ | Mục đích |
| --- | --- | --- |
| URL tải WSDL | `https://api.example.test/ws/orders.wsdl` | Tải mô tả hợp đồng |
| SOAP endpoint URL | `https://api.example.test/soap/orders` | Nhận POST SOAP messages |
| SOAP transport URI | `http://schemas.xmlsoap.org/soap/http` | Định danh kiểu transport |
| SOAP action URI | `urn:example:orders:GetOrder` | Định danh action |
| Namespace nghiệp vụ | `urn:example:orders:v1` | Định danh XML elements và types |

Đường dẫn WSDL và endpoint **có thể khác nhau**, và thường khác nhau. Không POST SOAP request vào URL `.wsdl` chỉ vì đó là địa chỉ mà công cụ sinh client đã đọc. Tương tự, không mặc định rằng truy cập endpoint bằng GET sẽ trả về WSDL.

### 7.1. Một service có nhiều port hoặc URL

Một WSDL có thể mô tả nhiều `wsdl:port`, ví dụ:

~~~xml
<wsdl:service name="OrderService">
    <wsdl:port name="OrderSoap11Port"
               binding="tns:OrderSoap11Binding">
        <soap:address
            location="https://api.example.test/soap/orders"/>
    </wsdl:port>

    <wsdl:port name="OrderSoap11BackupPort"
               binding="tns:OrderSoap11Binding">
        <soap:address
            location="https://backup.example.test/soap/orders"/>
    </wsdl:port>
</wsdl:service>
~~~

Hai port này dùng cùng binding nhưng khác endpoint URL. Việc có nhiều port **không tự động** mang nghĩa failover: client cần có chính sách chọn hoặc chuyển port. Trong môi trường thực tế, không nên đưa URL backup chưa sẵn sàng hoặc URL nội bộ vào WSDL công khai.

### 7.2. Reverse proxy và địa chỉ bị công bố sai

Khi Spring-WS chạy sau API gateway, ingress hoặc reverse proxy, địa chỉ nội bộ có thể khác địa chỉ public:

~~~text
Client
  -> https://api.example.test/soap/orders
  -> gateway / reverse proxy
  -> http://orders-service:8080/ws/orders
  -> Spring-WS MessageDispatcherServlet
~~~

Nếu WSDL lại chứa:

~~~xml
<soap:address location="http://orders-service:8080/ws/orders"/>
~~~

thì client bên ngoài có thể không gọi được, dù trang WSDL tải thành công. Khi công bố WSDL cần bảo đảm `soap:address/@location` là **URL mà client mục tiêu thực sự truy cập được**, đúng scheme HTTPS, domain, port và path.

Spring-WS có cơ chế **chuyển đổi địa chỉ WSDL theo request** thông qua cấu hình `MessageDispatcherServlet`, chẳng hạn `setTransformWsdlLocations(true)`. Tuy nhiên kết quả còn phụ thuộc servlet mapping, cách server/proxy cung cấp host/scheme/context và cấu hình xử lý forwarded headers. Kiểm tra WSDL bằng **URL public thực tế qua gateway**, không chỉ truy cập trực tiếp container nội bộ. Không tin cậy mù quáng giá trị Host/Forwarded header từ nguồn chưa được kiểm soát khi tạo địa chỉ công bố.

## 8. SOAP 1.1 và SOAP 1.2 có WSDL binding khác nhau

WSDL 1.1 có thể dùng phần tử mở rộng riêng cho SOAP 1.1 và SOAP 1.2. Tên prefix thường thấy:

| Nội dung | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Namespace mở rộng binding WSDL | `http://schemas.xmlsoap.org/wsdl/soap/` | `http://schemas.xmlsoap.org/wsdl/soap12/` |
| Phần tử khai báo binding | `soap:binding` | `soap12:binding` |
| Phần tử operation SOAP | `soap:operation` | `soap12:operation` |
| Địa chỉ endpoint | `soap:address` | `soap12:address` |
| Namespace SOAP Envelope | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Media type HTTP điển hình | `text/xml` | `application/soap+xml` |
| Action điển hình qua HTTP | `SOAPAction` header | Tham số `action` của `application/soap+xml` khi được dùng |

**Namespace mở rộng WSDL binding không phải namespace SOAP Envelope.** Ví dụ, `xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"` trong WSDL **khác** `xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"` trong SOAP message.

### 8.1. Fragment SOAP 1.2 binding trong WSDL 1.1

Giả sử `wsdl:definitions` còn khai báo:

~~~xml
xmlns:soap12="http://schemas.xmlsoap.org/wsdl/soap12/"
~~~

Ta có thể định nghĩa **một binding khác** cho cùng `OrderPortType`:

~~~xml
<wsdl:binding name="OrderSoap12Binding"
              type="tns:OrderPortType">
    <soap12:binding
        style="document"
        transport="http://schemas.xmlsoap.org/soap/http"/>

    <wsdl:operation name="GetOrder">
        <soap12:operation
            soapAction="urn:example:orders:GetOrder"/>
        <wsdl:input>
            <soap12:body use="literal"/>
        </wsdl:input>
        <wsdl:output>
            <soap12:body use="literal"/>
        </wsdl:output>
    </wsdl:operation>
</wsdl:binding>
~~~

Binding này chỉ có thể được gọi khi có `wsdl:port` tham chiếu nó và dùng `soap12:address`, chẳng hạn:

~~~xml
<wsdl:port name="OrderSoap12Port"
           binding="tns:OrderSoap12Binding">
    <soap12:address
        location="https://api.example.test/soap12/orders"/>
</wsdl:port>
~~~

Đây là **các đoạn mở rộng bổ sung**, không phải một WSDL hoàn chỉnh độc lập. Nếu tích hợp vào ví dụ mục 3, khai báo prefix `soap12` ở `wsdl:definitions`, thêm binding mới ở cấp định nghĩa và thêm port vào `wsdl:service` sẵn có.

### 8.2. HTTP request SOAP 1.2 minh họa

~~~http
POST /soap12/orders HTTP/1.1
Host: api.example.test
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:GetOrder"
~~~

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:o="urn:example:orders:v1">
    <env:Body>
        <o:GetOrderRequest>
            <o:orderId>ORD-1001</o:orderId>
        </o:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

Ở SOAP 1.2, action khi có thể được truyền bằng tham số `action` của media type `application/soap+xml`, không áp dụng máy móc quy tắc HTTP `SOAPAction` của SOAP 1.1 cho mọi client. Mối quan hệ action, WSDL và chính sách đích cần được kiểm tra với binding/framework cụ thể.

**Không đủ chỉ đổi Content-Type để chuyển SOAP 1.1 thành SOAP 1.2.** Namespace Envelope, binding WSDL, cơ chế xử lý Fault và khả năng hỗ trợ của server/client cũng phải tương thích.

## 9. Spring-WS công bố WSDL từ XSD bằng `DefaultWsdl11Definition`

Trong Spring-WS, mô hình contract-first thường bắt đầu bằng XSD chứa các global elements như `GetOrderRequest` và `GetOrderResponse`. Ứng dụng có thể công bố WSDL 1.1 được tạo từ XSD và các tham số cấu hình.

Ví dụ cấu hình Java (minh họa):

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@EnableWs
@Configuration
public class OrderWsConfig {

    private static final String NS = "urn:example:orders:v1";

    @Bean
    public XsdSchema orderSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("order.xsd")
        );
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema orderSchema) {
        DefaultWsdl11Definition definition =
            new DefaultWsdl11Definition();

        definition.setPortTypeName("OrderPortType");
        definition.setServiceName("OrderService");
        definition.setTargetNamespace(NS);
        definition.setLocationUri("/ws/orders");
        definition.setSchema(orderSchema);
        definition.setCreateSoap11Binding(true);
        definition.setCreateSoap12Binding(false);

        Properties actions = new Properties();
        actions.setProperty("GetOrder", "urn:example:orders:GetOrder");
        definition.setSoapActions(actions);

        return definition;
    }
}
~~~

Các giả định đi cùng ví dụ:

- File `order.xsd` có thực trên classpath, khai báo namespace tương ứng và các phần tử `GetOrderRequest`/`GetOrderResponse`; đây là tên mẫu cần thay bằng contract thực tế.
- Spring-WS sử dụng quy ước tên suffix `Request`/`Response` mặc định để suy ra operation khi tạo WSDL; cần kiểm tra WSDL kết quả để chắc chắn operation tên `GetOrder` đã được sinh theo mong muốn.
- `setLocationUri("/ws/orders")` xác định **địa chỉ được công bố trong SOAP binding**, không tự tạo một HTTP route mới. Đường dẫn POST phải được cấu hình và phục vụ thực sự bởi servlet/ứng dụng.
- `setSoapActions` là cách đặt action khi tạo binding. Tên operation trong `Properties` phải trùng operation được sinh.
- Cấu hình minh họa chưa bao gồm cách đăng ký `MessageDispatcherServlet` và các handler của dự án; đường dẫn WSDL công bố tùy servlet mapping.

Nếu `MessageDispatcherServlet` được đăng ký dưới `/ws/*`, bean WSDL tên `orders` thường được truy cập ở `/ws/orders.wsdl`. **URL trả WSDL** vẫn khác **`/ws/orders` là URL gửi thông điệp SOAP**. Tùy ứng dụng có thêm context path/gateway, hãy kiểm tra địa chỉ public thực tế.

### 9.1. Cấu hình cập nhật địa chỉ công bố sau proxy

Trong cấu hình Servlet:

~~~java
MessageDispatcherServlet servlet =
    new MessageDispatcherServlet();
servlet.setApplicationContext(applicationContext);
servlet.setTransformWsdlLocations(true);
~~~

Đây chỉ là phần liên quan đến **chuyển đổi địa chỉ trong WSDL**. Mã cần được đặt trong cấu hình đăng ký servlet phù hợp Spring Boot/Spring-WS đang dùng; `applicationContext` là biến ứng dụng cung cấp. Cơ chế này không thay thế cấu hình URL public, forwarded headers và routing của reverse proxy.

Khi dùng dynamic WSDL, phải kiểm tra WSDL được công bố **sau lần triển khai cuối**, nhất là lúc đổi host, context path, TLS hoặc đường dẫn gateway. Client đã sinh mã từ WSDL cũ có thể vẫn giữ endpoint URL cũ; cập nhật phía server không nhất thiết làm client tự nhận địa chỉ mới.

## 10. Endpoint Spring-WS và SOAP client dùng binding như thế nào?

### 10.1. Endpoint nhận request theo payload QName

Một endpoint có thể chọn operation dựa trên phần tử gốc của SOAP Body:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService orderService;

    public OrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return orderService.findById(request.getOrderId());
    }
}
~~~

`OrderService`, `GetOrderRequest` và `GetOrderResponse` là các kiểu ứng dụng giả định, thường được triển khai/sinh từ XSD và nghiệp vụ. Mã minh họa **cách ánh xạ payload QName**; việc unmarshalling JAXB thực tế còn yêu cầu các bean/adapter phù hợp với runtime dự án.

Ở đây, `@PayloadRoot` sử dụng **namespace và local name của XSD global element**, không dùng `soapAction` làm giá trị của tham số `namespace`. Nếu client gửi root thuộc namespace khác, endpoint mapping có thể không nhận ra request dù HTTP URL và action đúng.

Spring-WS cũng có annotation `@SoapAction` để ánh xạ theo action khi cơ chế mapping phù hợp được cấu hình. Chọn ánh xạ theo payload hay theo action cần nhất quán với hợp đồng và phương thức quản lý endpoint của dự án.

### 10.2. Client gửi action với `WebServiceTemplate`

Ở phía Java SOAP client, ví dụ dùng `WebServiceTemplate`:

~~~java
import org.springframework.ws.soap.client.core.SoapActionCallback;

GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1001");

GetOrderResponse response = (GetOrderResponse)
    webServiceTemplate.marshalSendAndReceive(
        "https://api.example.test/soap/orders",
        request,
        new SoapActionCallback("urn:example:orders:GetOrder")
    );
~~~

`webServiceTemplate` phải được cấu hình message factory, marshaller và unmarshaller phù hợp; các lớp request/response được lấy từ contract của dự án. Ví dụ sử dụng overload có **endpoint URL**, **request object** và **message callback**, phù hợp minh họa SOAP 1.1.

Ý nghĩa ba nguồn cấu hình:

| Phía client | Giá trị trong ví dụ | Liên hệ với WSDL |
| --- | --- | --- |
| URL truyền cho `marshalSendAndReceive` | `https://api.example.test/soap/orders` | `soap:address/@location` |
| `SoapActionCallback` | `urn:example:orders:GetOrder` | `soap:operation/@soapAction` |
| Object `GetOrderRequest` sau JAXB marshal | Phần tử XML `{urn:example:orders:v1}GetOrderRequest` | `wsdl:message` và XSD |

`SoapActionCallback` chỉ lo phần action ở tầng thông điệp. Nó không tự biến object sai schema thành đúng, không tự bảo đảm HTTP status thành công và không sửa một endpoint URL không truy cập được. Với SOAP 1.2, cần cấu hình message factory/version và kiểm tra cách HTTP sender biểu diễn action thực tế.

### 10.3. WSDL không phải runtime router tự động

Việc công bố WSDL **không tự động triển khai nghiệp vụ**. Endpoint cần chạy thật, URL phải được servlet/gateway map đúng và cấu hình SOAP messages phải tương thích. Tương tự, sửa `soap:address` trong WSDL không nhất thiết đổi đường dẫn servlet đang lắng nghe; hai cấu hình phải được đồng bộ.

## 11. Phân biệt sai binding, sai action, sai URL và sai payload

Các lỗi thường gặp có biểu hiện gần nhau nhưng yêu cầu cách khắc phục khác:

| Hiện tượng | Nguyên nhân có thể | Kiểm tra trước |
| --- | --- | --- |
| HTTP 404 | SOAP request gửi tới URL WSDL, sai path hoặc proxy không route | `soap:address/@location`, HTTP request target và gateway route |
| HTTP 405 | Gửi GET tới endpoint POST-only, hoặc sai method | HTTP method và servlet mapping |
| HTTP 415 | `Content-Type` không khớp SOAP version/binding | SOAP 1.1 `text/xml` hay SOAP 1.2 `application/soap+xml` |
| HTTP 401/403 | Auth HTTP, gateway hoặc TLS policy chặn | Header xác thực, access policy và proxy |
| SOAP Fault `VersionMismatch` | Envelope namespace không đúng SOAP version | SOAP 1.1/1.2 binding và Envelope |
| SOAP Fault `MustUnderstand` | SOAP Header bắt buộc không được xử lý | Header, WS-Security/Addressing và policy |
| Không tìm được endpoint mapping | Root QName không khớp `@PayloadRoot` hoặc action mapping không khớp | Payload root QName, action và mappings |
| Client không giải mã được response | Response element/type khác XSD hoặc SOAP version sai | `wsdl:output`, XSD, unmarshalling |
| Lỗi DNS/connect/TLS | Host không phân giải, port không mở, chứng chỉ không hợp lệ | URL endpoint, DNS, mạng, truststore/mTLS |
| WSDL tải được nhưng client không gọi được | `soap:address` chứa URL nội bộ hoặc không đúng scheme | Bản WSDL tải qua public gateway, địa chỉ được công bố |

Một SOAP Fault có thể đi kèm HTTP 500 trong SOAP 1.1. **HTTP 500 không đủ để kết luận** server đã tạo SOAP Fault, vì gateway hoặc web server có thể trả HTML. Tương tự, lỗi kết nối không có phản hồi HTTP không thể quy thành một Fault code nếu chưa thấy SOAP Envelope.

### 11.1. Ba tình huống dễ nhầm

**Tình huống A — URL đúng, action sai:** HTTP request đi đến `/soap/orders`, root XML đúng `GetOrderRequest` nhưng header `SOAPAction: "urn:example:orders:CancelOrder"`. Nếu server route bằng action, operation có thể không khớp; nếu route bằng payload QName, request có thể vẫn vào endpoint. Phải kiểm tra cấu hình thực tế.

**Tình huống B — action đúng, URL sai:** client gửi `SOAPAction: "urn:example:orders:GetOrder"` nhưng POST đến `/ws/orders.wsdl`. Máy chủ có thể trả 405/404/HTML; header action **không biến URL WSDL thành SOAP endpoint**.

**Tình huống C — URL và action đúng, SOAP version sai:** client gửi SOAP 1.2 Envelope nhưng binding mong SOAP 1.1. Kết quả có thể là 415, SOAP Fault hoặc lỗi parse tùy framework. Đổi action một mình không khắc phục được: cần đồng bộ binding, media type và Envelope namespace.

## 12. Kiểm thử contract-first trước khi tích hợp doanh nghiệp

Kiểm thử cần bao phủ không chỉ object Java mà cả **WSDL được công bố, HTTP transport và XML trên dây**. Với Spring-WS, có thể kiểm thử endpoint bằng `MockWebServiceClient` và client bằng `MockWebServiceServer`; để kiểm tra reverse proxy, TLS và URL public, phải có bài thử tích hợp qua mạng thực tế hoặc môi trường giả lập phù hợp.

| Ca kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| GET URL WSDL công khai | Trả WSDL 1.1 hợp lệ, không có URL nội bộ ngoài ý muốn |
| Tra cứu `wsdl:service/wsdl:port` | Mỗi port trỏ đúng binding và địa chỉ client dùng được |
| Tra cứu `wsdl:binding/@type` | Tham chiếu đúng `wsdl:portType` theo QName |
| Kiểm tra `soap:binding` | `style="document"` và transport URI đúng hợp đồng |
| Kiểm tra `soap:operation` | Operation có action đúng; nếu rỗng, client được cấu hình nhất quán |
| Gửi SOAP 1.1 hợp lệ | `text/xml`, Envelope SOAP 1.1, SOAPAction đúng, response hợp XSD |
| Gửi SOAP 1.2 hợp lệ vào port riêng nếu hỗ trợ | `application/soap+xml`, Envelope SOAP 1.2, action đúng |
| Đổi prefix payload nhưng giữ URI | Server tiếp nhận như cũ nếu QName không đổi |
| Root QName khác target namespace | Validation hoặc routing phát hiện sai theo cấu hình |
| Gửi POST nhầm URL `.wsdl` | Nhận diện lỗi URL/method rõ ràng |
| Thay SOAPAction không đúng | Hành vi phù hợp cơ chế routing/policy đã công bố |
| Chạy phía sau HTTPS reverse proxy | WSDL công bố HTTPS host/path public và endpoint thực sự truy cập được |
| Chứng chỉ TLS/mTLS không đúng | Client báo lỗi kết nối/xác thực rõ ràng; không nhầm là SOAP Fault nghiệp vụ |
| SOAP Fault từ service | Client nhận diện Fault ở SOAP Body và HTTP status phù hợp binding |
| Client được sinh từ WSDL | Gọi được operation thực tế, marshal/unmarshal đúng namespace |

Khi ghi log cho tích hợp, nên có **correlation ID**, tên operation, HTTP status, endpoint host/path, SOAP version, giá trị action và **QName phần tử gốc**. Không ghi tràn lan password, token, toàn bộ SOAP Body chứa dữ liệu cá nhân hoặc nội dung WS-Security Header. Mã lỗi HTTP, SOAP Fault và lỗi DNS/TLS cần được phân loại riêng.

## 13. Quy trình đọc WSDL khi nhận một hệ thống đối tác

Khi đối tác giao URL WSDL, hãy thực hiện lần lượt:

1. **Lấy bản WSDL thật** qua URL mà client sẽ sử dụng và xác nhận đây là WSDL 1.1. Kiểm tra cả XSD import/include liên quan có truy cập hoặc resolve được.
2. **Tìm `wsdl:service` và `wsdl:port`** phù hợp, đọc `binding` QName và `soap:address/@location`. Đừng bỏ qua lựa chọn giữa port SOAP 1.1/1.2 nếu cả hai được công bố.
3. **Đi theo `binding/@type` tới `wsdl:portType`**, xác định tên operation cần gọi, tên input/output messages và Fault nếu có.
4. **Đọc extension binding `soap:binding`/`soap12:binding`** để xác định style và transport; đọc `soap:body/@use` để nhận diện literal/encoded.
5. **Đọc action của operation** tại `soap:operation`/`soap12:operation`, ghi lại chính xác kể cả giá trị rỗng.
6. **Theo `wsdl:message/wsdl:part` đến global XSD elements**, xác định root QName, các phần tử con, namespace và kiểu dữ liệu.
7. **Sinh/cấu hình SOAP client** theo WSDL, xác định rõ endpoint URL, message factory/phiên bản SOAP, marshaller và action.
8. **Gửi request mẫu trên môi trường thử nghiệm**, kiểm tra HTTP method, Content-Type, action, Envelope và SOAP Body thực tế; đối chiếu response/Fault với hợp đồng.
9. **Xác nhận vận hành ngoài môi trường nội bộ:** host/path công khai, TLS certificate, gateway routing, giới hạn timeout, xác thực và WS-Security khi hợp đồng yêu cầu.

Đối với một dịch vụ có yêu cầu ổn định lâu dài, lưu một bản WSDL/XSD đã được **version hóa**, theo dõi thay đổi URI namespace, operation, binding, action và endpoint; không giả định WSDL được sinh động hôm nay giống bản mà client đối tác đã dùng để sinh mã từ nhiều tháng trước.

## 14. Bài tập tình huống

Đối tác cung cấp WSDL có đoạn:

~~~xml
<wsdl:binding name="InvoiceSoapBinding"
              type="tns:InvoicePortType">
    <soap:binding
        style="document"
        transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="CreateInvoice">
        <soap:operation
            soapAction="urn:example:invoice:CreateInvoice"/>
        <wsdl:input>
            <soap:body use="literal"/>
        </wsdl:input>
        <wsdl:output>
            <soap:body use="literal"/>
        </wsdl:output>
    </wsdl:operation>
</wsdl:binding>

<wsdl:service name="InvoiceService">
    <wsdl:port name="InvoiceSoapPort"
               binding="tns:InvoiceSoapBinding">
        <soap:address
            location="https://partners.example.test/soap/invoices"/>
    </wsdl:port>
</wsdl:service>
~~~

*Đây là đoạn trích trong `wsdl:definitions`; các prefix `wsdl`, `soap` và `tns` được giả định đã khai báo đúng.*

**Câu hỏi:**

1. SOAP client phải POST tới URL nào?
2. Giá trị `transport` có phải URL gửi request không? Vì sao?
3. Với SOAP 1.1, giá trị `SOAPAction` tương ứng là gì?
4. Body gửi theo style/use nào?
5. Nếu một client gửi đúng action nhưng POST tới `https://partners.example.test/ws/invoices.wsdl`, action có bảo đảm operation thực thi không?
6. Nếu endpoint trả `HTTP 500`, có thể kết luận chắc chắn đây là SOAP Fault không?

**Đáp án gợi ý:**

1. `https://partners.example.test/soap/invoices`.
2. **Không.** `http://schemas.xmlsoap.org/soap/http` chỉ định SOAP-over-HTTP transport, không định danh máy chủ dịch vụ.
3. `"urn:example:invoice:CreateInvoice"` trong HTTP `SOAPAction` header theo binding SOAP 1.1 và yêu cầu tương thích của đối tác.
4. `document/literal` theo `style="document"` và `use="literal"`.
5. **Không.** URL `.wsdl` có thể chỉ cho phép GET tài liệu WSDL, không nhận SOAP POST. Client phải dùng địa chỉ của `soap:address` hoặc endpoint đã được cấu hình tương đương.
6. **Không.** Cần đọc `Content-Type`, SOAP Envelope và phần tử `Fault`; một HTTP 500 có thể là lỗi hạ tầng trả HTML.

## 15. Ghi nhớ

- **`wsdl:portType`** mô tả operation trừu tượng, còn **`wsdl:binding`** cung cấp cách gọi SOAP cụ thể và **`wsdl:service/wsdl:port`** chỉ tới địa chỉ.
- **`soap:binding/@transport`** là định danh cơ chế SOAP-over-HTTP, **không phải URL endpoint**; HTTPS endpoint vẫn có thể dùng transport URI `http://schemas.xmlsoap.org/soap/http`.
- **`soap:operation/@soapAction`** là action ở tầng SOAP 1.1 HTTP binding; không tự đồng nhất nó với tên operation, QName payload, WS-Addressing action hoặc địa chỉ dịch vụ.
- **`soap:address/@location`** là nơi client gửi SOAP request. URL tải WSDL `.wsdl` có thể khác hoàn toàn URL nhận SOAP POST.
- **SOAP 1.1 và SOAP 1.2** khác extension binding, Envelope namespace và HTTP media type; client phải chọn đúng port/binding và cách biểu diễn action.
- Trong **Spring-WS contract-first**, công bố WSDL từ XSD qua `DefaultWsdl11Definition` là một lựa chọn; cần kiểm tra bản WSDL thực tế, endpoint mapping, JAXB payload, cấu hình client và URL công khai sau reverse proxy.
- Khi chẩn đoán tích hợp, kiểm tra **địa chỉ → SOAP version/Content-Type → action → root QName → schema/operation → response/Fault** để xác định đúng tầng lỗi và tránh sửa sai chỗ.
